# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

# Compute bilevel (black and white) images from input TIFFs
# by automatic thresholding. To compensate for the relatively
# low scan resolution of 300 spi, we scale the input images
# to 600 dpi using bilinear interpolation; afterwards, we
# apply Otsu’s thresholding algorithm to compute a bilevel
# image.
#
# Alternatively, we could also use Neural Networks for computing
# super-resolution images. However, the old-school approach is
# cheaper to compute, and it seems to work very well with
# the type of input we’re seeing with scanned cadastral plans.

import json
import os
import subprocess
import tempfile

import cv2
import numpy
import PIL.Image
import PIL.TiffImagePlugin

OUTPUT_DPI = 600


def threshold(in_path, out_path):
    # As of July 2024, the pillow library is able to write multi-page TIFFs,
    # but tiling does not seem to be implemented. Therefore we write out
    # an untiled multi-page TIFF and then run the `tiffcp` command to
    # produce a tiled image.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = os.path.join(tmp, "t.tif")
        with open(tmp_path, "w+b") as fp, PIL.TiffImagePlugin.AppendingTiffWriter(
            fp
        ) as out_tiff, PIL.Image.open(in_path) as tiff:
            for page_num in range(tiff.n_frames):
                tiff.seek(page_num)
                page = threshold_page(in_path, tiff, page_num)
                # https://github.com/python-pillow/Pillow/issues/3636#issuecomment-461986355
                PIL.TiffImagePlugin._save(page, out_tiff, tmp_path)
                out_tiff.newFrame()
        cmd = ["tiffcp", "-t", "-w", "512", "-l", "512", tmp_path, out_path]
        proc = subprocess.run(cmd)
        assert proc.returncode == 0, cmd


def threshold_page(in_path, tiff, page_num):
    if d := tiff.tag_v2.get(270):
        meta = json.loads(d)
    else:
        meta = {}
    date_time = tiff.tag_v2.get(306, "")
    x_dpi, y_dpi = tiff.info["dpi"]
    page = numpy.asarray(tiff)
    out_width = int(page.shape[1] * OUTPUT_DPI / x_dpi + 0.5)
    out_height = int(page.shape[0] * OUTPUT_DPI / y_dpi + 0.5)
    out_size = (out_width, out_height)
    scaled = cv2.resize(page, out_size, interpolation=cv2.INTER_LINEAR)
    blurred = cv2.bilateralFilter(scaled, 9, 75, 75)
    gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
    t, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    meta["thresholding"] = {
        "threshold": t,
        "method": "cv2.BINARY|OTSU",
    }

    # For typical good scans, the computed threshold (t) is above 140.
    # However, some scans are very dark, for example the first page
    # of mutation AA3008 with t=83. In those cases, we use a threshold
    # that artificially darkens the image, in the hope that some circles
    # (for border points) stay closed.
    if t < 110:
        # AA3008: 83 -> 98
        # OB2432: 77 -> 92
        new_t = t + 15
        meta["thresholding"] = {
            "value": new_t,
            "otsu_value": t,
            "method": "cv2.BINARY",
        }
        t, thresh = cv2.threshold(gray, new_t, 255, cv2.THRESH_BINARY)

    bw = PIL.Image.fromarray(thresh).convert("1")
    bw.encoderconfig = ()
    bw.encoderinfo = {
        "compression": "group4",
        "date_time": date_time,
        "dpi": (OUTPUT_DPI, OUTPUT_DPI),
        # For custom tags:
        # 'tiffinfo': PIL.TiffImagePlugin.ImageFileDirectory(),
    }

    desc = json.dumps(meta, sort_keys=True, separators=(",", ":"))
    bw.encoderinfo["description"] = desc
    if date_time:
        bw.encoderinfo["date_time"] = date_time
    return bw


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    os.makedirs("thresholded", exist_ok=True)
    for f in sorted(os.listdir("rendered")):
        # mutation = f.split(".")[0]
        # if mutation not in {"AA3008", "AA3009", "FL2005", "FL1929", "OB2432"}:
        #     continue
        in_path = os.path.join("rendered", f)
        out_path = os.path.join("thresholded", f)
        if not os.path.exists(out_path):
            threshold(in_path, out_path)
