# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

import csv
import os
import os.path
import re

import PIL.Image
import pytesseract


def run_ocr(mutation):
    coords_re = re.compile(r"(\d{6,7}\.\d{3})\s+(\d{6,7}\.\d{3})")
    thresh_path = os.path.join("thresholded", f"{mutation}.tif")
    coords_path = os.path.join("ocr_coords", f"{mutation}.csv")
    if os.path.exists(coords_path):
        return
    print(coords_path)
    tmp_path = coords_path + ".tmp"
    with open(tmp_path, "w") as fp:
        writer = csv.writer(fp)
        writer.writerow(["x", "y"])
        with PIL.Image.open(thresh_path) as thresh:
            for page_num in range(thresh.n_frames):
                thresh.seek(page_num)
                text = pytesseract.image_to_string(
                    thresh, lang="deu", config="--oem 1 --psm 4"
                )
                text = text.replace("°", " ")
                text = text.replace(",", ".")
                for x, y in coords_re.findall(text):
                    x, y = float(x), float(y)
                    writer.writerow(["%.3f" % x, "%.3f" % y])
    os.rename(tmp_path, coords_path)


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    os.makedirs("ocr_coords", exist_ok=True)
    for f in sorted(os.listdir("thresholded")):
        mut = f.split(".")[0]
        run_ocr(mut)
