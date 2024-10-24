# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

import argparse
import csv
import multiprocessing
import os
import re
import subprocess
import tempfile

import PIL.Image

from mutation_dates import dates as mutation_dates
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

    def process(self):
        # Allow images of arbitrary size. The Python multiprocessing library
        # spawns its worker processes without going through our main method,
        # so we need to set this global configuration here, in the per-process
        # runner.
        PIL.Image.MAX_IMAGE_PIXELS = None
        print(f"Starting {self.id}")
        text = self.pdf_to_text()
        parcels = self.extract_parcels(text)
        self.pdf_to_tiff(text)
        self.threshold()
        print(f"Finished {self.id}")

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
            return fp.read().split("\u000C")

    def pdf_to_tiff(self, text):
        tiff_path = os.path.join(self.workdir, "rendered", f"{self.id}.tif")
        if os.path.exists(tiff_path):
            return tiff_path
        tmp_dir = os.path.join(self.workdir, "tmp")
        with tempfile.TemporaryDirectory(delete=True, dir=tmp_dir) as temp:
            for i, pdf_path in enumerate(self.scans):
                target = os.path.join(temp, f"S{i+1}")
                proc = subprocess.run(
                    ["pdftocairo", "-tiff", "-r", "300", pdf_path, target]
                )
                assert proc.returncode == 0, (pdf_path, proc.returncode)
            pages = list_rendered_pages(temp)
            if self.date:
                for page in pages:
                    self.set_tiff_date(os.path.join(temp, page))
            assert len(pages) == len(text), self.id
            split_pages = []
            for page_path, page_text in zip(pages, text):
                split_pages.extend(maybe_split_page(page_path, page_text))
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
        return path

    def extract_parcels(self, text):
        p = set(re.findall(r"\b([23]\d{4}|[A-Z]{2}\d+)\b", "\n".join(text)))
        for path in self.scans:
            p.update(set(re.findall(r"[A-Z]{2}\d+", path)))
        return p


def process_batch(scans, workdir):
    os.makedirs(workdir, exist_ok=True)
    for dirname in (
        "text",
        "rendered",
        "georeferenced",
        "logs",
        "thresholded",
        "symbols",
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
    done = {os.path.splitext(f) for f in os.listdir(logs_path)}
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
    # in a different format but still need to be split.
    if "Tabelle" not in text and "tabelle" not in text:
        return [img_path]
    with PIL.Image.open(img_path) as img:
        mid = img.width // 2
        p = os.path.splitext(img_path)[0]
        paths = [f"{p}_left.tif", f"{p}_right.tif"]
        img.crop((0, 0, mid, img.height)).save(paths[0])
        img.crop((mid, 0, img.width, img.height)).save(paths[1])
        return paths


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--scans", default="scans", help="path to input scans to be processed"
    )
    ap.add_argument("--workdir", default="workdir", help="path to work dir")
    args = ap.parse_args()
    process_batch(args.scans, args.workdir)
