# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

import json
import os
import re
import subprocess
from collections import namedtuple

import pdf2image

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
}


Scan = namedtuple("Scan", ["pdf_path", "parcels", "year"])


class Mutation(object):
    def __init__(self, id, scans):
        self.id = id
        self.scans = scans

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
                pages.append(page)
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
                    "scan_page": page_num + 1,
                }
                if len(scan.parcels) > 0:
                    meta["parcels"] = sorted(list(scan.parcels))
                tags[270] = json.dumps(
                    meta,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                page_tags.append(tags)
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


def cleanup_mutation_id(neighborhood, s):
    if s.startswith("k_"):  # eg. "AA_k_0001"
        return f"{neighborhood}_{s}"
    m = re.match(r"(\d+)([A-ha-h]?)", s)
    assert m is not None, (neighborhood, s)
    num = int(m.group(1))
    suffix = m.group(2).upper()
    return f"{neighborhood}{num}{suffix}"


def list_mutations():
    mutations = {}
    mut_re = re.compile(r"^(FB_)?([A-Z]{2})_Mut_((k_)?(\d+)[A-Fa-f]?)_.+")
    for hood in os.listdir("scanned"):
        hood_dir = os.path.join("scanned", hood)
        for scan in os.listdir(hood_dir):
            scan_path = os.path.join(hood_dir, scan)
            if scan.endswith(".pdf"):
                fixed = MISNAMED_SCANS.get(scan, scan)
                if fixed is None:
                    continue
                if "__" in fixed:
                    print("Bad filename:", scan_path)
                    continue
                mut_match = mut_re.match(fixed)
                if mut_match is None:
                    print("Bad filename:", scan_path)
                    continue
                mutation_id = cleanup_mutation_id(
                    mut_match.group(2), mut_match.group(3)
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
                if year and year < 1990:
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
    for id, mut in sorted(list_mutations().items()):
        mut.render_to_tiff()
