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
import warnings

import cv2
import numpy
import PIL.Image
import PIL.TiffImagePlugin

OUTPUT_DPI = 600


def threshold(in_path, out_path):
    print("thresholding", in_path)
    out_pages = []
    with PIL.Image.open(in_path) as tiff:
        out_pages = []
        for page_num in range(tiff.n_frames):
            tiff.seek(page_num)
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
            if t < 110:  # eg. first page of mutation AA3008 has t=83
                new_t = t + 22
                meta["thresholding"] = {
                    "value": new_t,
                    "otsu_value": t,
                    "method": "cv2.BINARY",
                }
                t, thresh = cv2.threshold(gray, new_t, 255, cv2.THRESH_BINARY)
                warnings.warn("fixing up thresholding: %s" % in_path)

            bw = PIL.Image.fromarray(thresh).convert("1")
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
            out_pages.append(bw)

    # https://github.com/python-pillow/Pillow/issues/3636#issuecomment-461986355
    with open(out_path, "w+b") as fp:
        with PIL.TiffImagePlugin.AppendingTiffWriter(fp) as tiff:
            for page in out_pages:
                page.encoderconfig = ()
                PIL.TiffImagePlugin._save(page, tiff, out_path)
                tiff.newFrame()


if __name__ == "__main__":
    os.makedirs("thresholded", exist_ok=True)
    for f in sorted(os.listdir("rendered")):
        # if f != 'HG3302.tif': continue
        in_path = os.path.join("rendered", f)
        out_path = os.path.join("thresholded", f)
        if not os.path.exists(out_path):
            threshold(in_path, out_path)
