# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT


def din_format(tiff):
    """Returns one of {"A4", "A4R", "A3", "A3R", None} for a TIFF page."""
    formats = (
        ("A4", 21.0, 29.7),
        ("A3", 29.7, 42.0),
    )
    dpi_x, dpi_y = tiff.info["dpi"]
    height_cm = tiff.height / float(dpi_y) * 2.54
    width_cm = tiff.width / float(dpi_x) * 2.54
    for name, w, h in formats:
        if w * 0.95 <= width_cm <= w * 1.05 and h * 0.05 <= height_cm <= h * 1.05:
            return name
        if h * 0.95 <= width_cm <= h * 1.05 and w * 0.05 <= height_cm <= w * 1.05:
            return name + "R"  # rotated by 90 degrees
    return None
