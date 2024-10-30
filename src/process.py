# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

import argparse
import csv
import datetime
import io
import json
import multiprocessing
import os
import re
import subprocess
import tempfile
import traceback

import cv2
import numpy
import PIL.Image

from classify import detect_map_symbols
from mutation_dates import dates as mutation_dates
import survey_data
from threshold import threshold
from util import din_format

# Regular expression to extract mutaton dates.
DATE_PATTERN = re.compile(r".+_[jJ](\d{4})([-_](\d{2})[-_](\d{2}))?.*\.pdf$")


class Mutation(object):
    def __init__(self, id, date, scans, workdir):
        self.id = id
        self.date = date
        self.scans = scans
        self.workdir = workdir
        self.log = io.StringIO()

    def process(self):
        # Allow images of arbitrary size. The Python multiprocessing library
        # spawns its worker processes without going through our main method,
        # so we need to set this global configuration here, in the per-process
        # runner.
        PIL.Image.MAX_IMAGE_PIXELS = None
        print(f"START {self.id}")
        status = self.do_process()
        print(f"FINISHED {self.id} {status}")
        self.write_log(status)

    def do_process(self):
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        self.log.write("MutationID: %s\n" % self.id)
        self.log.write("MutationDate: %s\n" % (self.date if self.date else "None"))
        self.log.write("Started: t=%s\n" % self.start_time.isoformat())
        try:
            text = self.pdf_to_text()
            self.pdf_to_tiff(text)  # modifies text in case of split pages
            self.threshold()

            scales = self.extract_map_scales(text)
            bounds = self.estimate_bounds(text, scales)
            if bounds == None:
                return "BoundsNotFound"
            points_path = self.extract_survey_points(bounds, self.date)

            screenshots = self.detect_screenshots(text)
            symbols = self.detect_symbols(screenshots)
            if len(symbols) == 0:
                return "NotEnoughSymbols"

            # TODO: Call georeferencing tool
            self.log_stage_completion("all")
            return "OK"
        except Exception as e:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            traceback.print_exception(e, file=self.log)
            self.log.write("\n\n\n")
            return "Crashed"

    def log_stage_completion(self, stage):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.log.write(f"Stage: t={now} stage={stage}\n")

    def write_log(self, status):
        self.log.write(f"Status: {status}\n")
        path = os.path.join(self.workdir, "logs", f"{self.id}.txt")
        with open(path + ".tmp", "w") as fp:
            fp.write(self.log.getvalue())  # not atomic
        os.rename(path + ".tmp", path)  # atomic

    def pdf_to_text(self):
        text_path = os.path.join(self.workdir, "text", f"{self.id}.txt")
        if not os.path.exists(text_path):
            pages = []
            for pdf_path in self.scans:
                proc = subprocess.run(
                    ["pdftotext", "-layout", pdf_path, "-"],
                    capture_output=True,
                )
                assert proc.returncode == 0, (pdf_path, proc.returncode)
                text = proc.stdout.decode("utf-8").rstrip("\u000C")
                pages.extend(text.split("\u000C"))
            with open(text_path + ".tmp", "w") as fp:
                fp.write("\u000C".join(pages))  # not an atomic operation
            os.rename(text_path + ".tmp", text_path)  # atomic operation
        with open(text_path, "r") as fp:
            text = fp.read()
            pages = text.split("\u000C")
        self.log.write("Text: %d characters, %d pages\n" % (len(text), len(pages)))
        self.log_stage_completion("text")
        return pages

    def pdf_to_tiff(self, text):
        tiff_path = os.path.join(self.workdir, "rendered", f"{self.id}.tif")
        if os.path.exists(tiff_path):
            return tiff_path
        tmp_dir = os.path.join(self.workdir, "tmp")
        with tempfile.TemporaryDirectory(dir=tmp_dir) as temp:
            for i, pdf_path in enumerate(self.scans):
                target = os.path.join(temp, f"S{i+1}")
                proc = subprocess.run(
                    ["pdftocairo", "-tiff", "-r", "300", pdf_path, target]
                )
                assert proc.returncode == 0, (pdf_path, proc.returncode)
            pages = list_rendered_pages(temp)
            self.log.write("Rendered: %d pages\n" % len(pages))
            if self.date:
                for page in pages:
                    self.set_tiff_date(page)
            assert len(pages) == len(text), self.id
            split_pages, split_text = [], []
            for page_path, page_text in zip(pages, text):
                split = maybe_split_page(page_path, page_text)
                split_pages.extend(split)
                split_text.extend([page_text] * len(split))
            text[:] = split_text
            cmd = [
                "tiffcp",
                "-m",  # no memory restrictions
                "0",
                "-t",  # 512x512 pixel tiles
                "-w",
                "512",
                "-l",
                "512",
                "-c",  # deflate/zip compression
                "zip",
            ]
            cmd.extend(split_pages)
            cmd.append(tiff_path + ".tmp")
            proc = subprocess.run(cmd)  # output file not atomically written
            assert proc.returncode == 0, (cmd, proc.returncode)
            os.rename(tiff_path + ".tmp", tiff_path)  # atomically renamed
        self.log_stage_completion("rendered")
        return tiff_path

    def set_tiff_date(self, path):
        tiff_date = self.date.replace("-", ":") + " 00:00:00"
        proc = subprocess.run(["tiffset", "-s", "306", tiff_date, path])
        assert proc.returncode == 0, (path, proc.returncode)

    def threshold(self):
        path = os.path.join(self.workdir, "thresholded", f"{self.id}.tif")
        if os.path.exists(path):
            return path
        in_path = os.path.join(self.workdir, "rendered", f"{self.id}.tif")
        tmp_dir = os.path.join(self.workdir, "tmp")
        threshold(in_path, tmp_dir, path + ".tmp")  # not atomic
        os.rename(path + ".tmp", path)  # atomic
        self.log_stage_completion("thresholded")
        return path

    def extract_map_scales(self, text):
        result = []
        scale_re = re.compile(r"\s+1\s*:(200|500|1000|2000|5000)\s+")
        all_scales = list(sorted(set(scale_re.findall(" ".join(text)))))
        if len(all_scales) == 0:
            all_scales = [200, 500]  # defaults if OCR cannot find scale
        for page in text:
            page_scales = list(sorted(set(scale_re.findall(page))))
            page_scales = page_scales or all_scales
            result.append(page_scales)
        for page_num, scales in enumerate(result):
            sc = ",".join([f"1:{s}" for s in scales])
            self.log.write(f"MapScale: page={page_num+1} scales={sc}\n")
        return result

    def extract_parcels(self, text):
        p = set(re.findall(r"\b([23]\d{4}|[A-Z]{2}\d+)\b", "\n".join(text)))
        for path in self.scans:
            p.update(set(re.findall(r"[A-Z]{2}\d+", path)))
        self.log.write("Parcels: %s\n" % ",".join(sorted(p)))
        return p

    def extract_survey_points(self, bounds, map_date):
        path = os.path.join(self.workdir, "points", f"{self.id}.csv")
        if os.path.exists(path):
            return path

        min_x, min_y, max_x, max_y = bounds

        if map_date:
            map_date = datetime.date.fromisoformat((map_date + "-01-01")[:10])
            map_date = map_date + datetime.timedelta(days=365)
        else:
            max_date = None

        tmp_path = path + ".tmp"
        with open(tmp_path, "w") as fp:  # writing to a file is not atomic
            writer = csv.writer(fp)
            writer.writerow(["id", "x", "y", "symbol"])
            it = survey_data.read_points(min_x, min_y, max_x, max_y, map_date)
            for id, x, y, symbol in it:
                writer.writerow([id, "%.3f" % x, "%.3f" % y, symbol])
        os.rename(tmp_path, path)  # renaming a file is an atomic operation
        return path

    # Detect scanned pages that are screenshots of a Microsoft Windows
    # tool, probably an Access database which the City of Zürich used
    # in the late 1990s and early 2000s.  Our map symbol classifier
    # sometimes gets confused by those print-outs and wrongly claims
    # that those are scanned cadastral plans, but we can easily detect
    # such screenshots by checking for a text marker in the OCRed
    # page.
    #
    # For example, pages 12 and 13 of scan WO_Mut_20003_Kat_WO6495_j2005.pdf
    # are screenhots of that Windows tool, and the result of calling this
    # method on that scan is {12, 13}.
    def detect_screenshots(self, pages):
        keywords = ("User:", " VAZ-LB ")
        screenshots = set()
        for page_num, page_text in enumerate(pages):
            if any(k in page_text for k in keywords):
                screenshots.add(page_num + 1)
        if len(screenshots) > 0:
            self.log.write(
                "Screenshots: pages %s\n" % ",".join(sorted(map(str, screenshots)))
            )
        return screenshots

    def detect_symbols(self, screenshots):
        sym_path = os.path.join(self.workdir, "symbols", f"{self.id}.csv")
        if os.path.exists(sym_path):
            return self.read_symbols(sym_path)
        symbols = []
        r_path = os.path.join(self.workdir, "rendered", f"{self.id}.tif")
        t_path = os.path.join(self.workdir, "thresholded", f"{self.id}.tif")
        with PIL.Image.open(r_path) as rendered:
            with PIL.Image.open(t_path) as thresholded:
                for page_num in range(rendered.n_frames):
                    # Skip screenshots. page_num is 0-based.
                    if page_num + 1 in screenshots:
                        continue
                    rendered.seek(page_num)
                    thresholded.seek(page_num)
                    rendered_dpi = float(rendered.info["dpi"][0])
                    thresholded_dpi = float(thresholded.info["dpi"][0])
                    scale = rendered_dpi / thresholded_dpi
                    s = self.detect_map_symbols_on_page(thresholded, scale)
                    for x, y, sym in s:
                        symbols.append((page_num + 1, x, y, sym))
                    self.log.write(f"Symbols: page={page_num+1} n={len(s)}\n")
        symbols.sort()
        tmp_path = sym_path + ".tmp"
        with open(tmp_path, "w") as fp:
            out = csv.writer(fp)
            out.writerow(["page", "x", "y", "symbol"])
            for page, x, y, symbol in symbols:
                out.writerow([str(page), str(x), str(y), symbol])
        os.rename(tmp_path, sym_path)
        self.log_stage_completion("symbols")
        return self.read_symbols(sym_path)

    def read_symbols(self, path):
        syms = {}
        with open(path) as fp:
            for row in csv.DictReader(fp):
                page = int(row["page"])
                x, y = float(row["x"]), float(row["y"])
                symbol = row["symbol"]
                if "white" in symbol:
                    syms.setdefault(page, []).append([x, y, symbol])
        return {page: syms for page, syms in syms.items() if len(syms) >= 4}

    def detect_map_symbols_on_page(self, image, scale):
        page = numpy.asarray(image).astype(numpy.uint8) * 255

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

    # Estimate a bounding box (min_x, max_x, min_y, max_y) for a mutation.
    # The implementation looks at parcel numbers extracted from OCR text,
    # and at the current (2007) survey data in the hope that the mutation
    # has left a trace in today’s data.
    def estimate_bounds(self, text, scales):
        path = os.path.join(self.workdir, "bounds", f"{self.id}.geojson")
        if os.path.exists(path):
            with open(path) as fp:
                geojson = json.load(fp)
            bounds = tuple(geojson["bbox"])
            self.log.write(f"MutationBounds: {bounds}\n")
            return bounds
        bbox, bbox_source = None, None

        # 1. Try to use parcel numbers found on the plan by means of OCR.
        parcels = [survey_data.parcels.get(p) for p in self.extract_parcels(text)]
        parcels = [
            p for p in parcels if p and p.min_x and p.max_x and p.min_y and p.max_y
        ]
        features = [survey_data.make_geojson(p) for p in parcels]

        # 2. In addition, try to find a trace of the mutation in 2007 data.
        #    For example, when a mutation created a parcel that still exists,
        #    the script in src/extract_survey_data.py will be able to recover
        #    the mutation from the historical records available in today’s
        #    survey data, and emit a bounding box in survey_data/mutations.csv.
        if mut := survey_data.mutations.get(self.id):
            if mut.min_x and mut.min_y and mut.max_x and mut.max_y:
                features.append(survey_data.make_geojson(mut))

        if len(features) == 0:
            self.log.write("MutationBounds: not found\n")
            return None

        coords = []
        for f in features:
            for c in f["geometry"]["coordinates"]:
                coords.append(c)

        min_x, min_y = min(c[0] for c in coords), min(c[1] for c in coords)
        max_x, max_y = max(c[0] for c in coords), max(c[1] for c in coords)
        bbox = [min_x, min_y, max_x, max_y]
        self.log.write(f"MutationBounds: {bbox}\n")
        geojson = {
            "type": "FeatureCollection",
            "bbox": bbox,
            "crs": {
                "type": "name",
                "properties": {
                    "name": "urn:ogc:def:crs:EPSG::2056",
                },
            },
            "features": features,
        }

        tmp_path = path + ".tmp"
        with open(tmp_path, "w") as fp:
            json.dump(geojson, fp, indent=4, sort_keys=True)  # not atomic
        os.rename(tmp_path, path)  # atomic operation

        self.log_stage_completion("bounds")
        return tuple(bbox)


def process_batch(scans, workdir):
    os.makedirs(workdir, exist_ok=True)
    for dirname in (
        "bounds",
        "georeferenced",
        "logs",
        "points",
        "rendered",
        "symbols",
        "text",
        "thresholded",
        "tmp",
    ):
        os.makedirs(os.path.join(workdir, dirname), exist_ok=True)
    work = find_work(scans, workdir)
    with multiprocessing.Pool() as pool:
        for _ in pool.imap_unordered(Mutation.process, work):
            pass


# Returns a list of Mutations where we will need to do some work.
def find_work(scans, workdir):
    logs_path = os.path.join(workdir, "logs")
    done = {os.path.splitext(f)[0] for f in os.listdir(logs_path)}
    work = []
    unexpected_filenames = set()
    dates = {}  # mutation id -> date
    paths = {}  # mutation id -> [path to pdf, path to pdf, ...]
    for dirpath, _, filenames in os.walk(scans):
        for name in filenames:
            path = os.path.join(dirpath, name)
            if not name.endswith(".pdf"):
                continue
            id = extract_mutation_id(name)
            if not id:
                unexpected_filenames.add(path)
                continue
            paths.setdefault(id, []).append(path)
            date = mutation_dates.get(id, extract_mutation_date(name))
            dates.setdefault(id, date)
    for id in sorted(paths.keys()):
        if id not in done:
            work.append(Mutation(id, dates.get(id), paths[id], workdir))
    dateless = {mut for mut in paths if not dates.get(mut)}
    with open(os.path.join(workdir, "logs", "bad_filenames.txt"), "w") as errs:
        errs.write("Unexpected filenames: %d\n" % len(unexpected_filenames))
        for path in sorted(unexpected_filenames):
            errs.write("- %s\n" % path)
        errs.write("Without date: %d\n" % len(dateless))
        for mut in sorted(dateless):
            errs.write("- %s\n" % mut)
    return work


# "AF_Mut_20009_Kat_AF5146_AF5147_j2005.pdf" --> "20009"
# "FL_Mut_1303_Kat_588_J1959_01-01.pdf" --> "FL1303"
def extract_mutation_id(filename):
    split = filename.split("_Mut_")
    if len(split) < 2:
        return None
    # "FB" = "Flächenbereinigung" (area correction), not a neighborhood
    neighborhoods = list({x.strip() for x in split[0].split("_") if x != "FB"})
    if m := re.match(r"^([A-Z]{2})?(\d+)", split[1]):
        num = int(m.group(2))
        if num >= 20000:
            return str(num)
        else:
            return "%s%d" % (neighborhoods[0], num)
    if m := re.match(r"^[kK][-_](\d+)", split[1]):
        return "%s-K%d" % (neighborhoods[0], int(m.group(1)))
    return None


# "AF_Mut_20009_Kat_AF5146_AF5147_j2005.pdf" --> "2005-01-01"
# "FL_Mut_1303_Kat_588_J1959_01-01.pdf" --> "1959-01-01"
def extract_mutation_date(filename):
    if m := DATE_PATTERN.match(filename):
        year, _, month, day = m.groups()
        year = int(year)
        month = int(month) if month else 0
        day = int(day) if day else 0
        if 1 <= month <= 12 and 1 <= day <= 31:
            return "%04d-%02d-%02d" % (year, month, day)
        else:
            return "%04d-01-01" % year
    return None


PDFCAIRO_FILENAME_PATTERN = re.compile(r"^S(\d+)-(\d+)\.tif$")


def list_rendered_pages(dirpath):
    pages = []
    for f in os.listdir(dirpath):
        if m := PDFCAIRO_FILENAME_PATTERN.match(f):
            scan, page = m.groups()
            pages.append((int(scan), int(page), os.path.join(dirpath, f)))
    pages.sort()
    return [f for _scan, _page, f in pages]


def maybe_split_page(img_path, text):
    # Quite often, two pages are scanned as one, so we have the plan
    # either on the left or the right half. Initially, we tried all kinds
    # of complicated heuristics to figure out whether the page needs splitting,
    # including layout analysis and detection of punch holes by means of
    # computer vision. However, simply looking for "Tabelle" or "tabelle"
    # in the plaintext (that was extracted through OCR) seems to work best.
    # Initially, we restricted the splitting to DIN A3 pages in landscape
    # orientation, but it turned out that (especially older) scans are
    # in a different format but still need to be split. But we never split
    # a DIN A4 page into two DIN A5 halves.
    keywords = ("Tabelle", "tabelle", "sind übertragen", "Quadrat")
    if not any(k in text for k in keywords):
        return [img_path]
    with PIL.Image.open(img_path) as img:
        if din_format(img) in ("A4", "A4R"):
            return [img_path]
        dpi = img.info["dpi"]
        mid = img.width // 2
        p = os.path.splitext(img_path)[0]
        paths = [f"{p}_left.tif", f"{p}_right.tif"]
        img.crop((0, 0, mid, img.height)).save(paths[0], dpi=dpi)
        img.crop((mid, 0, img.width, img.height)).save(paths[1], dpi=dpi)
        return paths


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--scans", default="scans", help="path to input scans to be processed"
    )
    ap.add_argument("--workdir", default="workdir", help="path to work dir")
    args = ap.parse_args()
    process_batch(args.scans, args.workdir)
