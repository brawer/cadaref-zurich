# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

import csv
import os
import os.path

import cv2
import numpy
import PIL.Image

from classify import detect_map_symbols


def detect_symbols(mutation):
    thresh_path = os.path.join("thresholded", f"{mutation}.tif")
    symbols_path = os.path.join("symbols", f"{mutation}.csv")
    if os.path.exists(symbols_path):
        return
    rows = []
    print("detecting symbols in", thresh_path)
    with PIL.Image.open(thresh_path) as thresh:
        for page_num in range(thresh.n_frames):
            thresh.seek(page_num)
            img = numpy.asarray(thresh).astype(numpy.uint8) * 255
            cv2.rectangle(
                img,
                (0, 0),
                (thresh.width - 1, thresh.height - 1),
                color=255,
                thickness=1,
            )
            for x, y, symbol in detect_map_symbols(img):
                rows.append([page_num, x / 2, y / 2, symbol])
    tmp_path = symbols_path + ".tmp"
    with open(tmp_path, "w") as fp:
        writer = csv.writer(fp)
        writer.writerow(["page_num", "x", "y", "symbol"])
        for row in rows:
            writer.writerow(row)
    os.rename(tmp_path, symbols_path)


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    os.makedirs("symbols", exist_ok=True)
    for root, dirs, files in os.walk("thresholded"):
        for f in sorted(files):
            mutation = f.split(".")[0]
            detect_symbols(mutation)
