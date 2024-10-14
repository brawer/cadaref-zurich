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

from threshold import threshold

# Regular expression to extract mutaton dates.
DATE_PATTERN = re.compile(r".+_[jJ](\d{4})([-_](\d{2})[-_](\d{2}))?.*\.pdf$")


class Mutation(object):
    def __init__(self, id, date, scans, workdir):
        self.id = id
        self.date = date
        self.scans = scans
        self.workdir = workdir

    def process(self):
        print(f"Starting {self.id}")
        text = self.pdf_to_text()
        parcels = self.extract_parcels(text)
        self.pdf_to_tiff()
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
                text = proc.stdout.decode("utf-8")
                pages.extend(text.split("\u000C"))
            with open(text_path + ".tmp", "w") as fp:
                fp.write("\u000C".join(pages))  # not an atomic operation
            os.rename(text_path + ".tmp", text_path)  # atomic operation
        with open(text_path, "r") as fp:
            return fp.read().split("\u000C")

    def pdf_to_tiff(self):
        tiff_path = os.path.join(self.workdir, "rendered", f"{self.id}.tif")
        if os.path.exists(tiff_path):
            return tiff_path
        with tempfile.TemporaryDirectory(delete=False) as temp:
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
            cmd.extend(pages)
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
        threshold(in_path, path + ".tmp")  # not atomic
        os.rename(path + ".tmp", path)  # atomic
        return path

    def extract_parcels(self, text):
        p = set(re.findall(r'\b([23]\d{4}|[A-Z]{2}\d+)\b', '\n'.join(text)))
        for path in self.scans:
            p.update(set(re.findall(r'[A-Z]{2}\d+', path)))
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
    mut_dates_overwrites = read_mutation_dates()
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
            date = mut_dates_overwrites.get(id, extract_mutation_date(name))
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


def read_mutation_dates():
    dates = {}
    path = os.path.join(os.path.dirname(__file__), "mutation_dates.csv")
    with open(path) as fp:
        for row in csv.DictReader(fp):
            dates[row["mutation"]] = row["date"]
    return dates


PDFCAIRO_FILENAME_PATTERN = re.compile(r"^S(\d+)-(\d+)\.tif$")


def list_rendered_pages(dirpath):
    pages = []
    for f in os.listdir(dirpath):
        if m := PDFCAIRO_FILENAME_PATTERN.match(f):
            scan, page = m.groups()
            pages.append((int(scan), int(page), os.path.join(dirpath, f)))
    pages.sort()
    return [f for _scan, _page, f in pages]


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--scans", default="scans", help="path to input scans to be processed"
    )
    ap.add_argument("--workdir", default="workdir", help="path to work dir")
    args = ap.parse_args()
    process_batch(args.scans, args.workdir)
