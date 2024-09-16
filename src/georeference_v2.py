# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

from collections import namedtuple
import csv
import io
import json
import os
import re

import cv2
import json
import numpy
import PIL.Image
import quads

from classify import detect_map_symbols
from threshold import threshold

Mutation = namedtuple("Mutation", "id date min_x max_x min_y max_y")
Parcel = namedtuple("Parcel", "id min_x max_x min_y max_y")
DeletedPoint = namedtuple("DeletedPoint", "id style x y created_by deleted_by")
BorderPoint = namedtuple("BorderPoint", "id style x y created")
FixedPoint = namedtuple("FixedPoint", "id style x y created")


# Map from point classes in survey_data/border_points.csv to cartographic
# styles. Style IDs are the same as returned by detect_map_symbols()
# in src/classify.py.
BORDER_POINT_STYLES = {
    "unversichert": "black_dot",
    "Bolzen": "white_circle",
    "Stein": "white_circle",
}


# Map from point classes in src/deleted_points.csv to cartographic styles.
# Cartographic style IDs are the same as returned by detect_map_symbols()
# in src/classify.py.
DELETED_POINT_STYLES = {
    "2": "double_white_circle",
    "4": "white_circle",
}


# The PDFs with the scanned mutation files indicate as part of their
# file names which parcels have been created by each mutation. For
# georeferencing, we use these parcel numbers to find an approximate
# bounding box for the scanned plan (we can't work on the entire city
# because it's too big, and there might also be a risk of wildly wrong
# mismatches).
#
# However, the more we step back into history, the likelier it gets
# that those parcels have been modified again by later mutations.
# In that case, the parcels get new IDs, and we don't see their old ID
# in today's land survey database. Therefore, we enrich the manually
# annotated parcel identifiers with other parcel IDs in the scanned plan,
# as recognized by Optical Character Recognition (OCR). Typically these
# belong to parcels in the close neighborhood of the mutation.
#
# By having more parcel IDs to work on, we have a higher chance that
# at least one or two of them are still in existence today, allowing
# us to find an approximate location for the scanned mutation plan.
#
# This regular expression is used for extracting parcel identifiers
# such as "HG3099" or "EN123" from the OCRed plaintext. We
# intentionally do not look for GEOS Pro identifiers such as "27123",
# since these numbers also occur in other context (not as parcel
# identifiers) in the mutation files.
PARCEL_RE = re.compile(
    r"\s((AA|AF|AL|AR|AU|EN|FL|HG|HI|HO|LE|OB|OE|RI|SE|SW|UN|WD|WI|WO|WP)\d{1,4})\s"
)


# Regular expression for extracting the map/plan scale from OCRed plaintext.
PLAN_SCALE_RE = re.compile(r"\b1\s*:\s*(100|200|250|500|1000|2000)\b")


class Georeferencer(object):
    def __init__(self):
        self.deleted_points = self._read_deleted_points()
        self.mutations = self._read_mutations()
        self.parcels = self._read_parcels()
        points = list(self._read_fixed_points())
        points.extend(self._read_border_points())
        points.extend(self.deleted_points)
        self.quad_tree = self._build_quad_tree(points)

    def georeference(self, mutation):
        log = io.StringIO()
        rendered_path = os.path.join("rendered", f"{mutation}.tif")
        thresholded_path = os.path.join("thresholded", f"{mutation}.tif")
        if not os.path.exists(thresholded_path):
            threshold(rendered_path, thresholded_path)
        with open(os.path.join("rendered", f"{mutation}.txt")) as fp:
            ocr_text = fp.read()
            ocr_parcels = set([m[0] for m in PARCEL_RE.findall(ocr_text)])
            ocr_scales = self._extract_scales(ocr_text)
            screenshots = self._screenshot_pages(ocr_text)
        with PIL.Image.open(rendered_path) as rend:
            with PIL.Image.open(thresholded_path) as thresh:
                bbox = self._mutation_bbox(mutation, thresh, ocr_parcels)
                for page_num in range(thresh.n_frames):
                    rend.seek(page_num)
                    thresh.seek(page_num)
                    meta_json = thresh.tag_v2[270]
                    meta = json.loads(meta_json)
                    log.write(f"#### Cadaref {meta_json}\n")
                    log.write(f"ocr_parcels: {ocr_parcels}\n")
                    log.write(f"bbox: {bbox}\n")
                    if not bbox:
                        log.write("status: cannot guess approx location\n")
                        continue

                    rendered_dpi = float(rend.info["dpi"][0])
                    thresholded_dpi = float(thresh.info["dpi"][0])
                    symbols = self._detect_map_symbols(
                        mutation, thresh, scale=rendered_dpi / thresholded_dpi
                    )
                    log.write("num_symbols: %d\n" % len(symbols))
                    log.write("symbols: %s\n" % symbols)
                    if len(symbols) < 4:
                        log.write("status: not enough symbols\n")
                        continue

                    # Our rendering phase in src/render.py tries to
                    # find A3 pages that have (perhaps mistakenly)
                    # been glued together during scanning, and splits
                    # them in a left and right half based on a
                    # page-splitting heuristics. However, OCR does not
                    # know about this page splitting. Therefore, for
                    # the OCR-derived heuristics, we need to
                    # reconstruct the page kay before splitting. For
                    # example, pages "7L" and "7R" both have page
                    # number 7 in the view of OCR.
                    scan, scan_page = meta["scan"], meta["scan_page"]
                    if scan_page[-1] in {"L", "R"}:
                        page_key = (scan, int(scan_page[:-1]))
                    else:
                        page_key = (scan, int(scan_page))

                    if page_key in screenshots:
                        log.write("status: screenshot\n")
                        continue

                    # Find an approximate area for the scanned plan.
                    # In this area, we look for geo points that might
                    # be matchable against the detected map symbols.
                    scale = ocr_scales.get(page_key)
                    width_cm = (thresh.width / thresholded_dpi) * 2.54
                    height_cm = (thresh.height / thresholded_dpi) * 2.54
                    if scale is not None:
                        width_m = (width_cm / 100.0) * scale
                        height_m = (height_cm / 100.0) * scale
                    else:
                        width_m = (width_cm / 100.0) * 2000
                        height_m = (height_cm / 100.0) * 2000
                    min_x, max_x, min_y, max_y = bbox
                    width_m = max(width_m, max_x - min_x)
                    height_m = max(height_m, max_y - min_y)
                    center_x = min_x + (max_x - min_y) / 2
                    center_y = min_y + (max_y - min_y) / 2
                    # We don't know the plan rotation, so we take the max
                    # of width and height. Typical search radius is ~3.5 km.
                    search_radius = max(width_m, height_m) / 2
                    search_bbox = quads.BoundingBox(
                        min_x=center_x - search_radius,
                        max_x=center_x + search_radius,
                        min_y=center_y - search_radius,
                        max_y=center_y + search_radius,
                    )
                    log.write(f"search_radius: {search_radius}\n")
                    log.write(f"search_bbox: {search_bbox}\n")
                    # TODO: Look up search_bbox in quadtree
                    # TODO: Pass everything to cadaref tool
                    print("*** ZEBRA-B", mutation, search_bbox, scale, len(symbols))

                    log.write(f"scale: {scale}\n")

                    # print(scan, scan_page, scale, len(symbols), max_x - min_x, max_y-min_y)

            self._write_log(mutation, log.getvalue())

    @staticmethod
    def _write_log(mutation, message):
        # We write the log to a temporary file (with a different name),
        # which is not an atomic operation and could be interrupted.
        # Once the log file is completely written to disk, we rename
        # the temporary file to the final file name in an atomic operation.
        # This ensures we don't end up with partially written log files.
        log_path = os.path.join("georeferenced", f"{mutation}.log")
        tmp_path = log_path + ".tmp"
        with open(tmp_path, "w") as f:
            f.write(message)
        os.rename(tmp_path, log_path)

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

    @staticmethod
    def _read_border_points():
        path = os.path.join("survey_data", "border_points.csv")
        with open(path) as fp:
            for rec in csv.DictReader(fp):
                if style := BORDER_POINT_STYLES.get(rec["type"]):
                    yield BorderPoint(
                        id=rec["point"],
                        style=style,
                        x=float(rec["x"]),
                        y=float(rec["y"]),
                        created=rec["created"],
                    )

    @staticmethod
    def _read_fixed_points():
        path = os.path.join("survey_data", "fixed_points.csv")
        with open(path) as fp:
            for rec in csv.DictReader(fp):
                yield FixedPoint(
                    id=rec["point"],
                    style="double_white_circle",
                    x=float(rec["x"]),
                    y=float(rec["y"]),
                    created=rec["created"],
                )

    @staticmethod
    def _build_quad_tree(points):
        min_x, max_x = min(p.x for p in points), max(p.x for p in points)
        min_y, max_y = min(p.y for p in points), max(p.y for p in points)
        width, height = max_x - min_x, max_y - min_y
        center_x, center_y = min_x + width / 2.0, min_y + height / 2.0
        tree = quads.QuadTree(
            center=(center_x, center_y),
            width=width + 1.0,
            height=height + 1.0,
        )
        for p in points:
            tree.insert((p.x, p.y), data=p)
        return tree

    def _mutation_parcels(self, tiff):
        parcels = set()
        for page_num in range(tiff.n_frames):
            tiff.seek(page_num)
            meta = json.loads(tiff.tag_v2[270])
            parcels.update(meta.get("parcels", []))
        return parcels

    def _mutation_bbox(self, mutation, tiff, ocr_parcels):
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
        # data. However, since OCR is less reliable than manual
        # annotations, we the OCRed parcel names only if we have
        # no better data source.
        if len(boxes) == 0:
            for parcel in ocr_parcels:
                if p := self.parcels.get(parcel):
                    boxes.append(p)

        if len(boxes) > 0:
            min_x = min(b.min_x for b in boxes if b.min_x)
            max_x = max(b.max_x for b in boxes if b.max_x)
            min_y = min(b.min_y for b in boxes if b.min_y)
            max_y = max(b.max_y for b in boxes if b.max_y)
            return (min_x, max_x, min_y, max_y)
        else:
            return None

    # Extract the plan/map scales from OCRed plaintext.
    #
    # The result is a map from (scan, page_num) to scale, for example
    #   {('HG_Mut_21853_Kat_HG8332_HG8333_j2007.pdf', 1): 500}
    # meaning page 1 of that pdf file contains the string "1:500".
    #
    # Caveats:
    #
    # * Some scans do not indicate their scale at all, but this is rare.
    #
    # * Sometimes, OCR fails to read the plan indicator.
    #
    # * Some scans have multiple plans with different scales, but always
    #   on different pages.
    #
    # * OCR runs independent of page splitting, so we might return
    #   a scale for page 7 whereas in the rendered TIFF file the plan
    #   is on page "7L" or "7R" depending on whether the plan is
    #   located on the left or right half of an A3 page.
    def _extract_scales(self, ocr_text):
        scales = {}
        for page in ocr_text.split("#### Cadaref ")[1:]:
            meta_json, page_text = page.split("\n", 1)
            meta = json.loads(meta_json)
            scan, scan_page = meta["scan"], meta["scan_page"]
            if m := PLAN_SCALE_RE.search(page_text):
                scales[(scan, scan_page)] = int(m.group(1))
        return scales

    # Some mutation files contain pages with screenshots of a Windows tool
    # that confuse our symbol detection. We can identify these through OCR.
    #
    # For example, pages 12 and 13 of scan WO_Mut_20003_Kat_WO6495_j2005.pdf
    # are screenhots of that Windows tool, and the result of calling this
    # method on that scan is the following Python set.
    #
    # {
    #     ('WO_Mut_20003_Kat_WO6495_j2005.pdf', 12),
    #     ('WO_Mut_20003_Kat_WO6495_j2005.pdf', 13)
    # }
    @staticmethod
    def _screenshot_pages(ocr_text):
        screenshots = set()
        for page in ocr_text.split("#### Cadaref ")[1:]:
            meta_json, page_text = page.split("\n", 1)
            if " VAZ-LB " in page_text:
                meta = json.loads(meta_json)
                scan, scan_page = meta["scan"], meta["scan_page"]
                screenshots.add((scan, scan_page))
        return screenshots

    def _detect_map_symbols(self, _mutation, thresh, scale):
        page = numpy.asarray(thresh).astype(numpy.uint8) * 255
        # Our classifier sometimes gets confused if the outermost
        # pixels aren't white. Draw a one-pixel white line around
        # the plan.
        h, w = page.shape[0], page.shape[1]
        cv2.rectangle(page, (0, 0), (w - 1, h - 1), color=255)
        # At the moment, detection of white symbols is much
        # more reliable than detection of black symbols (mainly
        # because small black dots get confused with text and
        # dotted lines), so we restrict ourselves to white.
        # It still generates enough fodder for matching,
        # because black dots stand for unverified border points
        # which are relatively rare in practice, at least within
        # a city like Zürich.
        return [
            (x * scale, y * scale, sym)
            for (x, y, sym) in detect_map_symbols(page)
            if "white" in sym
        ]


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    os.makedirs("georeferenced", exist_ok=True)
    ref = Georeferencer()
    mutations = set(f.rsplit(".", 1)[0] for f in os.listdir("rendered"))
    # mutations = {m for m in mutations if m[0] not in {"2", "3"}}
    for mut in sorted(mutations):
        ref.georeference(mut)
