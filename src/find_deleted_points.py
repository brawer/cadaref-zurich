# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

# Finds deleted points in GEOS Pro mutations, by extracting
# deletion records from OCR embedded in scan PDFs.
# Scans before GEOS (sadly) do not contain deletion records,
# so this script does not process those.

import csv
import os
import re
import subprocess


TITLE_WORDS = {
    "Geomatik",
    "ORTHOGONALE",
    "Messdatenimport",
    "GeoZ",
    "Einrechnen",
    "Basis",
    "SCHNITT",
    "LISTE",
    "Liste",
    "Mutation",
    "MUTATION",
    "alte",
}


def find_deleted_points(mutation, path):
    out_path = os.path.join("deleted_points", f"{mutation}.csv")
    if os.path.exists(out_path):
        return
    #print(path)
    proc = subprocess.run(
        ["pdftotext", "-layout", path, "-"],
        capture_output=True,
    )
    assert proc.returncode == 0, (mutation, proc.returncode)
    text = proc.stdout.decode("utf-8")
    parts = text.split("GELÖSCHTEN PUNKTE")

    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as fp:
        writer = csv.writer(fp)
        for part in parts[1:]:
            part = part.split("\u000C")[0]
            for line in part.splitlines():
                cols = line.split()
                cols = [c for c in cols if c != "-"]
                cols = [c for c in cols if c != "0.000"]
                if len(cols) < 1:
                    continue
                id = cols[0]
                if id == "Nummer":
                    continue
                if id in TITLE_WORDS:
                    break
                if not is_valid_id(id):
                    print(id, path, cols)
                    break
                for i in range(len(cols) - 2):
                    if y := cleanup_coord(cols[i]):
                        if x := cleanup_coord(cols[i + 1]):
                            cols[i] = y
                            cols[i + 1] = x
                            break
                writer.writerow([mutation] + cols)

    os.rename(tmp_path, out_path)


_COORD_RE = re.compile(r"\d{6}\.\d{3}")
_POINT_ID_RE = re.compile(r"\d+|[A-Z]{2,3}\d+")


def is_valid_id(id):
    return _POINT_ID_RE.match(id) is not None


def cleanup_coord(c):
    c = c.replace("-", "")
    if _COORD_RE.match(c) and c[0] != "0":
        return c
    else:
        return None


if __name__ == "__main__":
    # Only mutations from GEOS Pro contain deletion records.
    paths = [
        os.path.join("scanned/GEOS_Pro", p)
        for p in os.listdir("scanned/GEOS_Pro")
        if p.endswith(".pdf")
    ]
    paths.sort()
    # paths = ['scanned/GEOS_Pro/AL_Mut_23299_Kat_AL8579_j2009.pdf']
    os.makedirs("deleted_points", exist_ok=True)
    for path in paths:
        mut = re.match(r".+_Mut_(\d+)_.+", path).group(1)
        find_deleted_points(mut, path)
