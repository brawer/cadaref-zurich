# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

import json
import os
import re
import subprocess
from collections import namedtuple

import cv2
import numpy
import pdf2image
import PIL.Image

from util import din_format

# We do not render these mutations; these will have to be handled manually.
BLACKLISTED_MUTATIONS = {
    "21841",  # too big
}

# For these mutations, we do not complain if the year in the PDF file name
# is old.
OLD_MUTATIONS = {
    "WO1938",
}

MISNAMED_SCANS = {
    "AA_Mut_3006_Kat_Keine_j1994.pdf": "AA_Mut_3006_Kat_AA7201_j1994.pdf",
    "AF_Mut_1539_Kat_0410_j1992.pdf": "AF_Mut_1539_Kat_AF410_j1992.pdf",
    "AF_Mut_1540_Kat_4958_j1992.pdf": "AF_Mut_1540_Kat_AF4958_j1992.pdf",
    "AF_Mut_1541_Kat_4650_j1992.pdf": "AF_Mut_1541_Kat_AF4650_j1992.pdf",
    "AF_Mut_1542_Kat_4238_j1992.pdf": "AF_Mut_1542_Kat_AF4238_j1992.pdf",
    "AR_Mut_2464_Kat_AR2186__AR2187_j1999.pdf": "AR_Mut_2464_Kat_AR2186_AR2187_j1999.pdf",  # noqa: E501
    "AR_Mut_2476_Kat_AR6583_AR6584_AR6585_AR6586_AR6587_AR6588_AR6589_AR6590_AR6591_AR6592_AR653_AR6594_AR6595_AR6596_AR6597_AR6598_AR6599_AR6600_AR6601_AR6602_AR6603_AR6604_AR6605_AR6606_AR6607_AR6608_AR6609.pdf": "AR_Mut_2476_Kat_AR6583_AR6584_AR6585_AR6586_AR6587_AR6588_AR6589_AR6590_AR6591_AR6592_AR653_AR6594_AR6595_AR6596_AR6597_AR6598_AR6599_AR6600_AR6601_AR6602_AR6603_AR6604_AR6605_AR6606_AR6607_AR6608_AR6609_AR6610_AR6611_AR6612_j1999.pdf",  # noqa: E501
    "AR_Mut_2476_Kat_AR6583_AR6584_AR6585_AR6586_AR6587_AR6588_AR6589_AR6590_AR6591_AR6592_AR6593_AR6594_AR6595_AR6596_AR6597_AR6598_AR6599_AR6600_AR6601_AR6602_AR6603_AR6604_AR6605_AR6606_AR6607_AR6608_AR660.pdf": None,  # noqa: E501
    "AU_Mut_3385_Kat_4881_j1998.pdf": "AU_Mut_3385_Kat_AU4881_j1998.pdf",
    "FB_ AF_Mut_1597_Kat_AF4989_AF4990_AF4991_AF4992_j1995_001.pdf": "FB_AF_Mut_1597_Kat_AF4989_AF4990_AF4991_AF4992_j1995_001.pdf",  # noqa: E501
    "FL_Mut_1921B_Kat__j1991.pdf": "FL_Mut_1921B_Kat_keine_j1991.pdf",
    "FL_Mut_1929_Kat_FL3501_FL3502_j1929.pdf": "FL_Mut_1929_Kat_FL3501_FL3502_j1992.pdf",  # noqa: E501
    "FL_Mut_1936_Kat_FL2644_j1936.pdf": "FL_Mut_1936_Kat_FL2644_j1992.pdf",
    "FL_Mut_1939_Kat_FL2996_1992.pdf": "FL_Mut_1939_Kat_FL2996_j1992.pdf",
    "FL_Mut_1961_Kat_FL2893_j1961.pdf": "FL_Mut_1961_Kat_FL2893_j1993.pdf",
    "FL_Mut_1967_Kat_FL3094_FL3139_j1967": "FL_Mut_1967_Kat_FL3094_FL3139_j1994.pdf",  # noqa: E501
    "FL_Mut_1967_Kat_FL3094_FL3139_j1967.pdf": "FL_Mut_1967_Kat_FL3094_FL3139_j1994.pdf",  # noqa: E501
    "FL_Mut_1976_Kat_FL3455_j1955.pdf": "FL_Mut_1976_Kat_FL3455_j1995.pdf",
    "FL_Mut_2217_Kat__FL3550_FL3551_FL3552_j2002.pdf": "FL_Mut_2217_Kat_FL3550_FL3551_FL3552_j2002.pdf",  # noqa: E501
    "HG_Mut_3001_Kat_7518_j1996.pdf": "HG_Mut_3001_Kat_HG7518_j1996.pdf",
    "HO_Mut_2218_Kat_ HO4284_j1997.pdf": "HO_Mut_2218_Kat_HO4284_j1997.pdf",
    "HO_Mut_2206_Kat_HO4351_HO4352__j1996.pdf": "HO_Mut_2206_Kat_HO4351_HO4352_j1996.pdf",
    "HO_Mut_2131_Kat_HO4514_HO4515_j1909.pdf": "HO_Mut_2131_Kat_HO4514_HO4515_j1992.pdf",
    "HO_Mut_2195_Kat_HO4538HO4539_j1995.pdf": "HO_Mut_2195_Kat_HO4538_HO4539_j1995.pdf",
    "HO_Mut_2222_Kat_HO1509_HO1521_HO4459_HO4500__j1997.pdf": "HO_Mut_2222_Kat_HO1509_HO1521_HO4459_HO4500_j1997.pdf",
    "HO_Mut_HO2453_Kat_HO4599_HO4600_HO4601_j2004.pdf": "HO_Mut_2453_Kat_HO4599_HO4600_HO4601_j2004.pdf",
    "RI_Mut_2391RI_Kat_RI5304_RI5305_j1998.pdf": "RI_Mut_2391_Kat_RI5304_RI5305_j1998.pdf",
    "RI_Mut_2216E_Kat_RIkeine_j1991.pdf": "RI_Mut_2216E_Kat_keine_j1991.pdf",
    "FB_RI_Mut_2293_Kat_RI5260_jRI1994.pdf": "FB_RI_Mut_2293_Kat_RI5260_j1994.pdf",
    "RI_Mut_0000_Kat_RI keine_j1991.pdf": "RI_Mut_0000_Kat_keine_j1991.pdf",
    "SE_Mut_2793_Kat_SE6395_SE6396_SE6397_SE6398_SE6399__SE6400_SE6401_SE6402_SE6403_SE6404_SE6405_SE6406_SE6407_SE6408_j2006.pdf": "SE_Mut_2793_Kat_SE6395_SE6396_SE6397_SE6398_SE6399_SE6400_SE6401_SE6402_SE6403_SE6404_SE6405_SE6406_SE6407_SE6408_j2006.pdf",
    "FB_SW_Mut_k-0001_Kat_FL3435_j1999.pdf": "FB_SW_Mut_k_0001_Kat_FL3435_j1999.pdf",
    "SE_Mut_2317_Kat_4395_j1991.pdf": "SE_Mut_2317_Kat_SE4395_j1991.pdf",
    "SW_Mut_24736_Kat_SW6458_SW6459_SW6460__j2011.pdf": "SW_Mut_24736_Kat_SW6458_SW6459_SW6460_j2011.pdf",
    "WI_Mut_1050_Kat_WI3169_jWI1994.pdf": "WI_Mut_1050_Kat_WI3169_j1994.pdf",
    "WP_Mut_WP2164_Kat_WP4742_WP4744_WP4748_WP4280_WP4281_j1995.pdf": "WP_Mut_2164_Kat_WP4742_WP4744_WP4748_WP4280_WP4281_j1995.pdf",
    "WP_Mut_2120_Kat_WPWP2098_j1991.pdf": "WP_Mut_2120_Kat_WP2098_j1991.pdf",
    "WO_Mut_K-0008_Kat_WO5846_j2000.pdf": "WO_Mut_k_0008_Kat_WO5846_j2000.pdf",
    "WO_Mut_k-0004_Kat_WO2397_WO2398_j2000.pdf": "WO_Mut_k_0004_Kat_WO2397_WO2398_j2000.pdf",
    "LE_WD_WO_Mut_22987_Kat_LE1771_LE1772_LE1773_LE1774_LE1775_LE1776_LE1777_WD9045_WD9046_WD9047_WD9048_WD9049_WO6648_WO6649_WO6650_WO6651_WO6652_WO6653_WO6654_WO6655_WO6656_WO6657_WO6658_WO6659_WO6660_WO666.pdf": "LE_WD_WO_Mut_22987_Kat_LE1771_LE1772_LE1773_LE1774_LE1775_LE1776_LE1777_WD9045_WD9046_WD9047_WD9048_WD9049_WO6648_WO6649_WO6650_WO6651_WO6652_WO6653_WO6654_WO6655_WO6656_WO6657_WO6658_WO6659_WO6660_WO6661_WO6662_j2013.pdf",  # noqa: E501
    "WO_Mut_1938_Kat_WO5932_bis_WO6013_j1977.pdf": "WO_Mut_1938_Kat_WO5932_WO5933_WO5934_WO5935_WO5936_WO5937_WO5938_WO5939_WO5940_WO5941_WO5942_WO5943_WO5944_WO5945_WO5946_WO5947_WO5948_WO5949_WO5950_WO5951_WO5952_WO5953_WO5954_WO5955_WO5956_WO5957_WO5958_WO5959_WO5960_WO5961_WO5962_WO5963_WO5964_WO5965_WO5966_WO5967_WO5968_WO5969_WO5970_WO5971_WO5972_WO5973_WO5974_WO5975_WO5976_WO5977_WO5978_WO5979_WO5980_WO5981_WO5982_WO5983_WO5984_WO5985_WO5986_WO5987_WO5988_WO5989_WO5990_WO5991_WO5992_WO5993_WO5994_WO5995_WO5996_WO5997_WO5998_WO5999_WO6000_WO6001_WO6002_WO6003_WO6004_WO6005_WO6006_WO6007_WO6008_WO6009_WO6010_WO6011_WO6012_WO6013_WO6229_WO6244_WO6248_j1977.pdf",  # noqa: E501
}


Scan = namedtuple("Scan", ["pdf_path", "parcels", "year"])


class Mutation(object):
    def __init__(self, id, scans):
        self.id = id
        self.scans = scans

    def _make_tags(self, dpi, scan, page):
        tags = {
            296: 2,  # resolution is in dpi
            282: dpi,  # x resolution
            283: dpi,  # y resolution
        }
        if scan.year is not None:
            tags[306] = "%04d:01:01 00:00:00" % scan.year
        meta = {
            "mutation": self.id,
            "scan": os.path.basename(scan.pdf_path),
            "scan_page": page,
        }
        if len(scan.parcels) > 0:
            meta["parcels"] = sorted(list(scan.parcels))
        tags[270] = json.dumps(
            meta,
            sort_keys=True,
            separators=(",", ":"),
        )
        return tags

    def render_to_tiff(self):
        dpi = 300
        path = os.path.join("rendered", "%s.tif" % self.id)
        if os.path.exists(path):
            return path
        os.makedirs("rendered", exist_ok=True)
        pages = []
        page_tags = []
        for scan in self.scans:
            print("Rendering", scan.pdf_path)
            rendered = pdf2image.convert_from_path(
                scan.pdf_path, dpi=dpi, use_pdftocairo=True
            )
            for page_num, page in enumerate(rendered):
                if cut := find_cut_position(page):
                    pages.append(page.crop((0, 0, cut, page.height)))
                    pages.append(page.crop((cut, 0, page.width, page.height)))
                    page_tags.append(self._make_tags(dpi, scan, f"{page_num+1}L"))
                    page_tags.append(self._make_tags(dpi, scan, f"{page_num+1}R"))
                else:
                    pages.append(page)
                    page_tags.append(self._make_tags(dpi, scan, f"{page_num+1}"))
        tmp_path = path + ".tmp.tif"
        pages[0].save(
            tmp_path,
            compression="tiff_deflate",
            save_all=True,
            append_images=pages[1:],
        )
        for page_num, tags in enumerate(page_tags):
            for tag_id, value in sorted(tags.items()):
                subprocess.run(
                    [
                        "tiffset",
                        "-d",
                        str(page_num),
                        "-s",
                        str(tag_id),
                        str(value),
                        tmp_path,
                    ]
                )
        os.rename(tmp_path, path)
        return path


# Quite frequently, two independent A4 pages were scanned together,
# forming a roated A3 page. However, we also see actual A3 documents
# in our input (both plans and text pages). By applying some simple
# heuristics, we can decide whether or not a page needs to be cut
# along the fold. This function returns the x position of the cut,
# or None if the page should not be cut in two halves.
def find_cut_position(tiff):
    # All pages in need of cutting are in rotated DIN A3 format.
    if din_format(tiff) != "A3R":
        return False

    downscale_factor = 4
    page = numpy.asarray(tiff.reduce(downscale_factor))
    h, w, _ = page.shape
    mid = w // 2
    fold_w = w // 20
    fold = page[0:h, (mid - fold_w) : (mid + fold_w)]
    gray = cv2.cvtColor(fold, cv2.COLOR_BGR2GRAY)
    gray = erase_punch_holes(gray)
    t, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cv2.erode(thresh, (3, 2), dst=thresh)

    num_black_px = h - numpy.count_nonzero(thresh, axis=0)
    widest_gap_x, widest_gap_width = 0, 0
    x = 0
    while x < fold_w:
        if num_black_px[x] > 0:
            x = x + 1
            continue
        streak_start = x
        while x < fold_w and num_black_px[x] == 0:
            x = x + 1
        streak_width = x - streak_start
        if streak_width > widest_gap_width:
            widest_gap_x = streak_start
            widest_gap_width = streak_width
    if widest_gap_width <= 3:
        return None

    # Always cutting in the exact middle of the A3 page looks gives
    # better results than a heuristic for cutting in the middle of
    # the widest gap.
    if False:
        x = mid - fold_w + widest_gap_x + widest_gap_width // 2
        return x * downscale_factor
    return tiff.width // 2


def erase_punch_holes(img):
    circles = cv2.HoughCircles(
        img,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=5,
        param1=1,
        param2=20,
        minRadius=8,
        maxRadius=12,
    )
    if circles is None:
        return img
    img = numpy.copy(img)
    for c in circles[0, :]:
        cx, cy, r = int(c[0] + 0.5), int(c[1] + 0.5), int(c[2] + 0.5)
        cv2.circle(img, (cx, cy), r + 3, (255,), -1)
    return img


def cleanup_mutation_id(neighborhood, s):
    if "_" in neighborhood:
        neighborhood = neighborhood.replace("_", "")
    if s.startswith("k_"):  # eg. "AA_k_0001"
        return f"{neighborhood}_{s}"
    m = re.match(r"(\d+)([A-ha-h]?)", s)
    assert m is not None, (neighborhood, s)
    num = int(m.group(1))
    if num >= 20000:
        return str(num)
    suffix = m.group(2).upper()
    return f"{neighborhood}{num}{suffix}"


def list_mutations():
    mutations = {}
    mut_re = re.compile(r"^(FB_)?([A-Z]{2}(_[A-Z]{2})*)_Mut_((k_)?(\d+)[A-Ha-h]?)_.+")
    for hood in os.listdir("scanned"):
        hood_dir = os.path.join("scanned", hood)
        for scan in os.listdir(hood_dir):
            scan_path = os.path.join(hood_dir, scan)
            if scan.endswith(".pdf"):
                fixed = MISNAMED_SCANS.get(scan, scan)
                if fixed is None:
                    continue
                if "__" in fixed:
                    print('Bad filename with "__":', scan_path)
                    continue
                mut_match = mut_re.match(fixed)
                if mut_match is None:
                    print("Bad filename x:", scan_path)
                    continue
                mutation_id = cleanup_mutation_id(
                    mut_match.group(2), mut_match.group(4)
                )
                parcels = re.findall(r"_([A-Z]{2}\d+)_", fixed)
                if not parcels and "_keine_" not in fixed:
                    print("Bad filename:", scan_path)
                    continue
                year = re.findall(r"_j(\d+)", fixed)
                if len(year) != 1 and not fixed.endswith("_j.pdf"):
                    print("Bad filename:", scan_path)
                    continue
                year = None if fixed.endswith("_j.pdf") else int(year[0])
                if year and year < 1990 and mutation_id not in OLD_MUTATIONS:
                    print("Bad filename:", scan_path)
                    continue
                scan_list = mutations.setdefault(mutation_id, [])
                scan_list.append(Scan(scan_path, parcels, year))
    result = {}
    for id, scans in mutations.items():
        scans = sorted(scans, key=lambda s: s.pdf_path.removesuffix(".pdf"))
        mut = Mutation(id, scans)
        result[id] = mut
    return result


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    for id, mut in sorted(list_mutations().items()):
        if id not in BLACKLISTED_MUTATIONS:
            mut.render_to_tiff()
