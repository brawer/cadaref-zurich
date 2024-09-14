# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

from collections import namedtuple
import csv
import os

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


class Georeferencer(object):
    def __init__(self):
        self.deleted_parcels = self._read_deleted_parcels()
        self.deleted_points = self._read_deleted_points()
        self.mutations = self._read_mutations()
        self.parcels = self._read_parcels()

    def georeference(self, mutation):
        rendered_path = os.path.join("rendered", f"{mutation}.tif")
        thresholded_path = os.path.join("thresholded", f"{mutation}.tif")
        if not os.path.exists(thresholded_path):
            threshold(rendered_path, thresholded_path)
        with PIL.Image.open(thresholded_path) as thresh:
            bbox = self._mutation_bbox(thresh)
            if bbox is None:
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
        print("*** GIRAFFE", mutations["22315"])
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
                        created_by=rec["Erstellt"],
                        deleted_by=rec["Gelöscht"],
                    )
                )
        return points

    @staticmethod
    def _read_deleted_parcels():
        delp = {}
        path = os.path.join(os.path.dirname(__file__), "deleted_parcels.csv")
        with open(path) as fp:
            for rec in csv.DictReader(fp):
                mut = rec["Mutation"]
                parcels = set(rec["Gelöschte Parzellen"].split())
                delp[mut] = parcels
        return delp

    def _mutation_parcels(self, tiff):
        parcels = set()
        for page_num in range(tiff.n_frames):
            tiff.seek(page_num)
            meta = json.loads(tiff.tag_v2[270])
            parcels.update(meta.get("parcels", []))
            if delp := self.deleted_parcels.get(meta["mutation"]):
                parcels.update(delp)
        return parcels

    def _mutation_bbox(self, tiff):
        boxes = []
        meta = json.loads(tiff.tag_v2[270])
        if m := self.mutations.get(meta["mutation"]):
            boxes.append(m)
        for parcel in self._mutation_parcels(tiff):
            if p := self.parcels.get(parcel):
                boxes.append(p)
        if len(boxes) == 0:
            return None
        min_x = min(box.min_x for box in boxes)
        max_x = max(box.max_x for box in boxes)
        min_y = min(box.min_y for box in boxes)
        max_y = max(box.max_y for box in boxes)
        return (min_x, max_x, min_y, max_y)


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    os.makedirs("georeferenced", exist_ok=True)
    ref = Georeferencer()
    # TODO --- should be listdir("rendered")
    for f in sorted(os.listdir("thresholded")):
        ref.georeference(f.rsplit(".tif", 1)[0])
        continue

        rendered_path = os.path.join("rendered", f)
        thresholded_path = os.path.join("thresholded", f)
        out_path = os.path.join("georeferenced", f)
        if not os.path.exists(thresholded_path):
            threshold(rendered_path, thresholded_path)

        num_plans = 0
        with PIL.Image.open(thresholded_path) as thresh:
            parcels = set()
            for page_num in range(thresh.n_frames):
                thresh.seek(page_num)
                meta = json.loads(thresh.tag_v2[270])
                mutation = meta["mutation"]
                bbox = find_mutation_bbox(meta["mutation"], mutations)
                if not bbox:
                    print(mutation)
                continue
                page = numpy.asarray(thresh).astype(numpy.uint8) * 255
                h, w = page.shape[0], page.shape[1]
                cv2.line(page, (0, 0), (w - 1, h - 1), color=255, thickness=1)
                symbols = [
                    (x / 2, y / 2, sym) for (x, y, sym) in detect_map_symbols(page)
                ]
                white_symbols = [s for s in symbols if "white" in s[2]]
                if len(white_symbols) > 4:
                    print(f, page_num + 1, len(white_symbols))
                    num_plans += 1
        if num_plans == 0:
            print(f, "---")
