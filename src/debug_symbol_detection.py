# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

# Tool for debugging the detection of cartographic symbols
# on scanned cadastral maps.
#
# Input: a rendered multi-page TIFF file, for example like those
# generated by process.py (our main pipeline) into workdir/rendered.
# You can also create an input TIFF from any PDF file like this:
#
# pdftocairo -tiff -r 300 path/to/input.pdf
#
# Usage: venv/bin/python3 src/debug_symbol_detection.py --rendered=image.tif
#
# The tool will generate a (multi-page) TIFF file that has the recognized
# symbol locations highlighted.

import argparse
import os
import tempfile

import cv2
import numpy
from PIL import Image, ImageDraw

from classify import detect_map_symbols
from threshold import threshold


COLORS = {
    "white_circle": (128, 128, 60),
    "double_white_circle": (128, 60, 128),
    "black_dot": (60, 128, 128),
}

if __name__ == "__main__":
    Image.MAX_IMAGE_PIXELS = None
    ap = argparse.ArgumentParser()
    ap.add_argument("--rendered", help="path to rendered tiff file")
    args = ap.parse_args()
    rendered_path = args.rendered
    output_path = os.path.splitext(os.path.basename(rendered_path))[0] + ".symbols.tif"
    images = []
    with tempfile.TemporaryDirectory() as temp_dir:
        thresholded_path = os.path.join(temp_dir, "thresholded.tif")
        threshold(rendered_path, temp_dir, thresholded_path)
        with Image.open(thresholded_path) as thresholded:
            for page_num in range(thresholded.n_frames):
                thresholded.seek(page_num)
                page = numpy.asarray(thresholded).astype(numpy.uint8) * 255
                symbols = detect_map_symbols(page)
                print(f"page {page_num + 1}: found {len(symbols)} symbols")
                image = thresholded.convert("RGB")
                canvas = ImageDraw.Draw(image, "RGBA")
                for x, y, symbol in symbols:
                    c = COLORS[symbol]
                    canvas.circle((x, y), 50, fill=(c[0], c[1], c[2], 128))
                images.append(image)
    images[0].save(
        output_path,
        compression="tiff_deflate",
        save_all=True,
        append_images=images[1:],
    )
