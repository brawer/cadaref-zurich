# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

# Experiment for finding the stamp "Bestandesänderung ohne Grenzänderung".
# Detected stamps (output as of July 22, 2024) are listed below.
# This experiemnt was not super successful, but we're keeping the
# source code around just in case it turns out to be useful later.

import json
import os
import os.path

import cv2
import numpy
import PIL.Image
import PIL.TiffImagePlugin

SRC_DIR = os.path.dirname(__file__)

WITHOUT_BORDER_CHANGE = cv2.imread(
    os.path.join(SRC_DIR, "ohne_grenzaenderung.png"),
    cv2.IMREAD_GRAYSCALE,
)


def find_stamp_ohne_grenzaenderung(tiff, page_num):
    meta = json.loads(tiff.tag_v2.get(270))
    mutation = meta["mutation"]
    # date_time = tiff.tag_v2.get(306, "")
    # dpi = tiff.info["dpi"]
    img = numpy.asarray(tiff)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, (0, 100, 50), (50, 255, 255))
    cv2.dilate(blue, (3, 3))
    masked = cv2.bitwise_and(img, img, mask=blue)
    gray = 255 - cv2.cvtColor(masked, cv2.COLOR_BGR2GRAY)
    t, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU + cv2.THRESH_BINARY)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, (15, 15))
    result = cv2.matchTemplate(thresh, WITHOUT_BORDER_CHANGE, cv2.TM_CCOEFF_NORMED)
    (_, score, _, loc) = cv2.minMaxLoc(result)
    x, y = str(int(loc[0])), str(int(loc[1]))
    if score > 0.3:
        score = "%.3f" % score
        print(",".join([mutation, str(page_num + 1), score, x, y]))


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    print("mutation,page,score,x,y")
    for root, dirs, files in os.walk("rendered"):
        for f in sorted(files):
            # if f != 'AR2381.tif': continue
            # print(f)
            path = os.path.join(root, f)
            with PIL.Image.open(path) as tiff:
                for page_num in range(tiff.n_frames):
                    tiff.seek(page_num)
                    find_stamp_ohne_grenzaenderung(tiff, page_num)


# Output from running this script as of July 22, 2024.
DETECTED_STAMPS = """mutation,page,score,x,y
AA1156,2,0.498,1014,1647
AA1157,1,0.638,3270,1690
AA1159,2,0.655,836,1726
AA1163,2,0.704,969,1554
AA1164,1,0.391,3260,1630
AA3000,1,0.687,3251,1697
AA3001,1,0.756,3271,1799
AA3002,2,0.489,822,1699
AA3002,4,0.653,816,1701
AA3003,2,0.596,971,1784
AA3004,1,0.743,3301,1791
AA3004,3,0.684,1003,1787
AA3004,4,0.724,3282,1795
AA3005,1,0.788,3295,1792
AA3006,1,0.393,3264,1199
AA3009,1,0.691,3061,1642
AA3010,1,0.720,3127,1550
AA3011,1,0.626,3081,1540
AA3012,1,0.727,3259,1623
AA3013,1,0.612,3115,1615
AA445,1,0.744,3102,1552
AA570,2,0.625,803,1226
AA639,1,0.594,3372,1595
AA643,1,0.464,3143,1647
AA644,1,0.645,3192,1648
AA649,1,0.541,3214,1627
AA650,1,0.610,3310,1701
AA661,2,0.510,3116,1462
AA668,3,0.567,821,1223
AR2313,1,0.534,3240,1620
AR2314,1,0.620,3255,1702
AR2319,4,0.562,1004,1629
AR2320,1,0.659,3114,1551
AR2324,1,0.631,3210,1715
AR2325,1,0.539,3166,1617
AR2336,1,0.737,3279,1713
AR2339,1,0.649,3249,1780
AR2349,1,0.692,3286,1207
AR2350,1,0.549,3246,1214
AR2357,1,0.563,3242,1298
AR2358,1,0.380,3306,1723
AR2359,1,0.734,3270,1780
AR2360,1,0.661,3286,1782
AR2362,3,0.719,968,1709
AR2362,5,0.697,980,1787
AR2363,1,0.591,3280,1955
AR2364,1,0.446,3293,1790
AR2381,1,0.808,3267,1691
AR2381,2,0.969,3294,1711
AR2383,1,0.705,3286,1695
AU3211,1,0.689,3211,1718
AU3213,1,0.499,3225,1710
AU3213,2,0.809,3195,1794
AU3214,1,0.345,3265,1785
AU3215,1,0.765,3275,1790
AU3216,1,0.590,3276,1701
AU3218,1,0.748,3264,1783
AU3219,1,0.664,3293,1716
AU3229,2,0.771,3286,1783
AU3229,3,0.647,818,1781
AU3235,1,0.594,3236,1537
AU3240,1,0.724,3232,1623
AU3245,1,0.580,3301,1133
AU3246,1,0.670,3309,1132
AU3248,1,0.512,3247,1148
AU3249,1,0.656,3253,1140
EN1405,1,0.442,910,1640
EN1410,1,0.611,3322,1696
EN1412,2,0.460,3138,1643
EN1417,1,0.617,3123,1719
EN1424,1,0.641,3235,1699
EN1428,1,0.713,3302,1527
EN1429,1,0.705,3365,1518
EN1431,1,0.634,3256,1373
EN1433,2,0.415,1034,1632
EN1434,1,0.449,3273,1601
EN1435,1,0.638,3138,1723
EN1436,1,0.742,3139,1709
EN1440,1,0.625,3287,1695
EN1441,1,0.718,3294,1695
EN1442,1,0.684,3288,1782
EN1443,1,0.731,3287,1699
EN1444,1,0.711,3266,1613
EN1449,2,0.686,805,1708
EN1455,1,0.493,3264,1216
EN1466,1,0.553,3213,1648
EN1619,10,0.305,714,1225
FL1946,1,0.309,3163,1616
FL1950,1,0.355,3146,1590
FL1951,1,0.459,3208,1618
"""
