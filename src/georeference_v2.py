# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

from collections import namedtuple
import csv
import os
import re

import cv2
import json
import numpy
import PIL.Image

from classify import detect_map_symbols
from threshold import threshold

Mutation = namedtuple("Mutation", "id date min_x max_x min_y max_y")
Parcel = namedtuple("Parcel", "id min_x max_x min_y max_y")
DeletedPoint = namedtuple("DeletedPoint", "id style x y created_by deleted_by")


DELETED_POINT_STYLES = {
    "2": "double_white_circle",
    "4": "white_circle",
}

PARCEL_RE = re.compile(
    r"\s((AA|AF|AL|AR|AU|EN|FL|HG|HI|HO|LE|OB|OE|RI|SE|SW|UN|WD|WI|WO|WP)\d{1,4})\s"
)


class Georeferencer(object):
    def __init__(self):
        self.deleted_points = self._read_deleted_points()
        self.mutations = self._read_mutations()
        self.parcels = self._read_parcels()

    def georeference(self, mutation):
        rendered_path = os.path.join("rendered", f"{mutation}.tif")
        thresholded_path = os.path.join("thresholded", f"{mutation}.tif")
        if not os.path.exists(thresholded_path):
            threshold(rendered_path, thresholded_path)
        with open(os.path.join("rendered", f"{mutation}.txt")) as fp:
            ocr_text = fp.read()
            ocr_parcels = set([m[0] for m in PARCEL_RE.findall(ocr_text)])
        with PIL.Image.open(thresholded_path) as thresh:
            bboxes = self._mutation_bboxes(mutation, thresh, ocr_parcels)
            symbols = self._detect_map_symbols(mutation, thresh, scale=0.5)
        if len(bboxes) == 0:
            print(mutation)

    def _read_mutations(self):
        points, dates = {}, {}
        for p in self.deleted_points:
            if p.created_by is not None:
                points.setdefault(p.created_by, []).append((p.x, p.y))
            if p.deleted_by is not None:
                points.setdefault(p.deleted_by, []).append((p.x, p.y))
        with open("survey_data/mutations.csv") as fp:
            for r in csv.DictReader(fp):
                id = r["mutation"]
                if date := r["date"]:
                    dates[id] = date
                min_x, min_y = r["min_x"], r["min_y"]
                pts = points.setdefault(id, [])
                if min_x and min_y:
                    pts.append((float(min_x), float(min_y)))
                max_x, max_y = r["max_x"], r["max_y"]
                if max_x and max_y:
                    pts.append((float(max_x), float(max_y)))
        mutations = {}
        mutation_ids = set(dates.keys()).union(points.keys())
        for id in mutation_ids:
            pts = points[id]
            mutations[id] = Mutation(
                id=id,
                date=dates.get(id),
                min_x=min(x for x, _y in pts) if pts else None,
                max_x=max(x for x, _y in pts) if pts else None,
                min_y=min(y for _x, y in pts) if pts else None,
                max_y=max(y for _x, y in pts) if pts else None,
            )
        return mutations

    @staticmethod
    def _read_parcels():
        parcels = {}
        with open("survey_data/parcels.csv") as fp:
            for r in csv.DictReader(fp):
                id = r["parcel"]
                if r["min_x"] != "":
                    parcels[id] = Parcel(
                        id=id,
                        min_x=float(r["min_x"]),
                        max_x=float(r["max_x"]),
                        min_y=float(r["min_y"]),
                        max_y=float(r["max_y"]),
                    )
        return parcels

    @staticmethod
    def _read_deleted_points():
        points = []
        path = os.path.join(os.path.dirname(__file__), "deleted_points.csv")
        with open(path) as fp:
            for rec in csv.DictReader(fp):
                style = DELETED_POINT_STYLES.get(rec["Kl"], "other")
                points.append(
                    DeletedPoint(
                        id=rec["Punktnummer"],
                        x=float(rec["X [LV95]"]),
                        y=float(rec["Y [LV95]"]),
                        style=style,
                        created_by=rec["Erstellmutation"],
                        deleted_by=rec["Löschmutation"],
                    )
                )
        return points

    def _mutation_parcels(self, tiff):
        parcels = set()
        for page_num in range(tiff.n_frames):
            tiff.seek(page_num)
            meta = json.loads(tiff.tag_v2[270])
            parcels.update(meta.get("parcels", []))
        return parcels

    def _mutation_bboxes(self, mutation, tiff, ocr_parcels):
        boxes = []
        meta = json.loads(tiff.tag_v2[270])
        # Sometimes we know a mutation's coordinates from survey data,
        # such as when the current survey data contains border points
        # that have been created by a mutation.
        if m := self.mutations.get(meta["mutation"]):
            boxes.append(m)
        # Another source for coordinates is the parcels that were
        # created by the mutation; some of the newly created parcels
        # may still exist today.
        for parcel in self._mutation_parcels(tiff):
            if p := self.parcels.get(parcel):
                boxes.append(p)
        # Also, the mutation PDF may contain parcel names which
        # have been extracted from OCR. For example, newer plans
        # conain strings such as "WO3525" which look very much
        # like a parcel name; again, some of those parcels may
        # still exist today so we get a bounding box from survey
        # data.
        for parcel in ocr_parcels:
            if p := self.parcels.get(parcel):
                boxes.append(p)
        return boxes

    @staticmethod
    def _bbox_extent(boxes):
        if boxes is not None and len(boxes) > 0:
            min_x = min(b.min_x for b in boxes if b.min_x)
            max_x = max(b.max_x for b in boxes if b.max_x)
            min_y = min(b.min_y for b in boxes if b.min_y)
            max_y = max(b.max_y for b in boxes if b.max_y)
            return (min_x, max_x, min_y, max_y)
        else:
            return None

    def _detect_map_symbols(self, _mutation, thresh, scale):
        result = []
        for page_num in range(thresh.n_frames):
            thresh.seek(page_num)
            page = numpy.asarray(thresh).astype(numpy.uint8) * 255
            # Our classifier sometimes gets confused if the outermost
            # pixels aren't white. Draw a one-pixel white line around
            # the plan.
            h, w = page.shape[0], page.shape[1]
            cv2.rectangle(page, (0, 0), (w - 1, h - 1), color=255)
            symbols = [
                (x * scale, y * scale, sym) for (x, y, sym) in detect_map_symbols(page)
            ]
            result.append(symbols)
        return result


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    os.makedirs("georeferenced", exist_ok=True)
    ref = Georeferencer()
    mutations = set(f.rsplit(".", 1)[0] for f in os.listdir("rendered"))
    mutations = {m for m in mutations if m[0] not in {"2", "3"}}
    for mut in sorted(mutations):
        ref.georeference(mut)
