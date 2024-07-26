# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

import cv2
import numpy as np


def detect_map_symbols(thresh):
    contours, hierarchy = cv2.findContours(
        thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_KCOS
    )
    result = []
    for c, contour in enumerate(contours):
        if klass := classify_contour(thresh, contours, hierarchy, c):
            x, y, w, h = cv2.boundingRect(contour)
            x, y = (x + w / 2, y + h / 2)
            result.append((x, y, klass))
    result.sort(key=lambda s: (s[1], s[0], klass))  # y, x, class
    return result


def classify(png):
    png_array = np.fromstring(png, dtype="uint8")
    gray = cv2.imdecode(png_array, cv2.IMREAD_GRAYSCALE)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    cv2.rectangle(thresh, (0, 0), (255, 255), 255, 1)
    contours, hierarchy = cv2.findContours(
        thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_KCOS
    )
    if False:
        cv2.imwrite("thresh.png", thresh)

    # Find the leaf contour (leaf = without holes) that is closest
    # to the image center at coordinate (128.0, 128.0).
    # That’s the one we want to classify.
    leaves = [i for i, h in enumerate(hierarchy[0]) if h[2] < 0]
    best, best_distance = None, 1e12
    for leaf in leaves:
        rect = cv2.boundingRect(contours[leaf])
        dx, dy = rect[0] + rect[2] / 2 - 128.0, rect[1] + rect[3] / 2 - 128.0
        distance = dx * dx + dy * dy
        if distance < best_distance:
            best, best_distance = leaf, distance
    if best is None:
        return None
    return classify_contour(thresh, contours, hierarchy, best)


def classify_contour(img, contours, hierarchy, c):
    contour = contours[c]
    white = (count_parents(hierarchy, c) % 2) == 0
    has_holes = hierarchy[0][c][2] >= 0
    parent_index = hierarchy[0][c][3]
    parent = contours[parent_index] if parent_index >= 0 else None
    x, y, r = contour_circle(contour)
    if white and not has_holes and between(r, 7.0, 19.0):
        has_black = any(has_circle(img, x, y, r + i, 0) for i in [2])
        has_white = any(has_circle(img, x, y, r + i, 255) for i in [10, 11])
        has_black_2 = any(has_circle(img, x, y, r + i, 0) for i in [15])
        if has_black and has_white and has_black_2:
            return "double_white_circle"
    if white and not has_holes and between(r, 7.5, 15.5):
        pw, ph = cv2.minAreaRect(parent)[1]
        if pw > 150 or ph > 150:
            if not has_circle(img, x, y, r + 10, 0):
                return "white_circle"
    if not white and not has_holes and between(r, 7.0, 10.2):
        any_black = not any(has_circle(img, x, y, r + i, 255) for i in range(8, 20, 4))
        if has_circle(img, x, y, r + 2, 255) and any_black:
            return "black_dot"
    return None


# Given an OpenCV contour hierarchy, count how many parents
# the i-th contour has in that hierarchy.
def count_parents(hierarchy, i):
    num_parents = 0
    p = hierarchy[0][i][3]
    while p >= 0:
        num_parents += 1
        p = hierarchy[0][p][3]
    return num_parents


def between(val, lower, upper):
    return val is not None and val >= lower and val <= upper


def contour_circle(contour):
    x, y, w, h = cv2.boundingRect(contour)
    if w < 8 or w > 35 or h < 8 or h > 35:
        return None, None, None
    box = cv2.minAreaRect(contour)
    box_aspect_ratio = float(box[1][0]) / box[1][1]  # width/height
    if box_aspect_ratio < 0.75 or box_aspect_ratio > 1.25:
        return None, None, None
    (x, y), r = cv2.minEnclosingCircle(contour)
    return x, y, r


# Returns true if all pixel on a circle around (cx, cy) with radius r
# have the given color, ignoring any pixels outside the image.
def has_circle(img, cx, cy, radius, color):
    cx, cy, radius = int(cx + 0.5), int(cy + 0.5), int(radius + 0.5)
    height, width = img.shape[:2]
    for x, y in circle_pixels(cx, cy, radius):
        if 0 <= x < width and 0 <= y < height:
            if img[y, x] != color:
                return False
    return True


# Midpoint circle algorithm
def circle_pixels(cx, cy, radius):
    f = 1 - radius
    ddf_x = 1
    ddf_y = -2 * radius
    x = 0
    y = radius
    yield (cx, cy + radius)
    yield (cx, cy - radius)
    yield (cx + radius, cy)
    yield (cx - radius, cy)
    while x < y:
        if f >= 0:
            y -= 1
            ddf_y += 2
            f += ddf_y
        x += 1
        ddf_x += 2
        f += ddf_x
        yield (cx + x, cy + y)
        yield (cx - x, cy + y)
        yield (cx + x, cy - y)
        yield (cx - x, cy - y)
        yield (cx + y, cy + x)
        yield (cx - y, cy + x)
        yield (cx + y, cy - x)
        yield (cx - y, cy - x)
