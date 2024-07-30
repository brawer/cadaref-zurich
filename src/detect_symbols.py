# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

import csv
import os
import os.path
import tempfile
import subprocess

import cv2
import numpy
import PIL.Image

from classify import detect_map_symbols


def detect_symbols(mutation):
    thresh_path = os.path.join("thresholded", f"{mutation}.tif")
    symbols_path = os.path.join("symbols", f"{mutation}.csv")
    #if os.path.exists(symbols_path):
    #    return
    debug = True
    rows = []
    print(symbols_path)
    with PIL.Image.open(thresh_path) as thresh:
        for page_num in range(thresh.n_frames):
            if page_num != 0: continue
            thresh.seek(page_num)
            img = numpy.asarray(thresh).astype(numpy.uint8) * 255
            cv2.rectangle(
                img,
                (0, 0),
                (thresh.width - 1, thresh.height - 1),
                color=255,
                thickness=1,
            )
            if debug:
                debug_img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            for x, y, symbol in detect_map_symbols(img):
                rows.append([page_num, x / 2, y / 2, symbol])
                if debug:
                    color = {
                        'white_circle': (255, 128, 0),
                        'double_white_circle': (128, 255, 0),
                        'black_dot': (128, 0, 255),
                    }.get(symbol)
                    if color is not None:
                        print(x, y, symbol)
                        cv2.circle(debug_img, (int(x*2+.5), int(y*2+.5)), 45, color, 12)
            if debug:
                tiff_path = os.path.join("symbols", f"{mutation}_{page_num}.tif")
                cv2.imwrite(tiff_path, debug_img)
                png_path = os.path.join("symbols", f"{mutation}_{page_num}.png")
                cmd = [
                    "magick", tiff_path, "-dither", "None", "-colors", "8",
                    png_path,
                ]
                subprocess.run(cmd)
                #os.remove(tiff_path)
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
            if mutation in {"FL1929", "FL2005", "OB2432"}:
                detect_symbols(mutation)
