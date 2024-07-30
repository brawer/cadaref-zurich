# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

import csv
import os

import PIL.Image
from ocrmac import ocrmac


def run_mac_ocr(mutation):
    thresh_path = os.path.join("thresholded", f"{mutation}.tif")
    out_path = os.path.join("mac_ocr", f"{mutation}.csv")
    if os.path.exists(out_path):
        return
    print(out_path)
    tmp_path = out_path + ".tmp"
    boxes = []
    with PIL.Image.open(thresh_path) as thresh:
        for page_num in range(thresh.n_frames):
            thresh.seek(page_num)
            texts = ocrmac.text_from_image(
                image=thresh,
                recognition_level="accurate",
                language_preference=["de-DE"],
                confidence_threshold=0.0,
            )
            for text, _score, bbox in texts:
                # ignoring score because macOS 14.5 always returns 1.0
                x1, y1, x2, y2 = ocrmac.convert_coordinates_pil(
                    bbox,
                    thresh.width,
                    thresh.height,
                )
                x = int(x1)
                y = int(y1)
                w = int(x2 - x1)
                h = int(y2 - y1)
                boxes.append((page_num, text, x, y, w, h))
    boxes.sort(key=lambda b: (b[0], b[3], b[2]))
    with open(tmp_path, "w") as fp:
        writer = csv.writer(fp)
        writer.writerow(["page", "text", "x", "y", "w", "h"])
        for box in boxes:
            writer.writerow([str(field) for field in box])
    os.rename(tmp_path, out_path)


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    os.makedirs("mac_ocr", exist_ok=True)
    for f in sorted(os.listdir("thresholded")):
        mut = f.split(".")[0]
        run_mac_ocr(mut)
