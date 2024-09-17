# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

# Extract datestamps from TIFF images in the "rendered" directory,
# storing their images (on behlaf of OCR) into "datesteamps".

import json
import os

import cv2
import numpy
import PIL.Image
import PIL.TiffImagePlugin


def find_datestamps(tiff, page_num):
    meta = json.loads(tiff.tag_v2.get(270))
    date_time = tiff.tag_v2.get(306, "")
    dpi = tiff.info["dpi"]
    img = numpy.asarray(tiff)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, (0, 100, 50), (50, 255, 255))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(blue, cv2.MORPH_CLOSE, kernel)
    if numpy.count_nonzero(mask) < 1000:
        return None
    k2 = cv2.getStructuringElement(cv2.MORPH_RECT, (51, 1))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k2)
    contours, hierarchy = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if 280 < w < 350 and 50 < h < 70:
            cropped = 255 - blue[y : y + h, x : x + w]
            meta["datestamp_bbox"] = [x, y, w, h]
            return make_bilevel_img(cropped, meta, date_time, dpi)
    return None


def make_bilevel_img(img, meta, date_time, dpi):
    bw = PIL.Image.fromarray(img).convert("1")
    bw.encoderconfig = ()
    meta_json = json.dumps(meta, sort_keys=True, separators=(",", ":"))
    bw.encoderinfo = {
        "compression": "group4",
        "date_time": date_time,
        "description": meta_json,
        "dpi": dpi,
    }
    return bw


def write_multipage_tiff(pages, out_path):
    # https://github.com/python-pillow/Pillow/issues/3636#issuecomment-461986355
    with open(out_path, "w+b") as fp:
        with PIL.TiffImagePlugin.AppendingTiffWriter(fp) as writer:
            for page in pages:
                PIL.TiffImagePlugin._save(page, writer, out_path)
                writer.newFrame()


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    os.makedirs("datestamps", exist_ok=True)
    for root, dirs, files in os.walk("rendered"):
        for f in sorted(files):
            path = os.path.join(root, f)
            out_path = os.path.join("datestamps", f)
            if os.path.exists(out_path):
                continue
            stamps = []
            with PIL.Image.open(path) as tiff:
                for page_num in range(tiff.n_frames):
                    tiff.seek(page_num)
                    if stamp := find_datestamps(tiff, page_num):
                        stamps.append(stamp)
            print(out_path, len(stamps))
            if len(stamps) > 0:
                write_multipage_tiff(stamps, out_path)
