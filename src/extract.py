# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

# Script for extracting points and parcels from the official survey.
# The data file for the earliest available year (2007( can be retrieved here:
#
#     https://www.stadt-zuerich.ch/geodaten/download/
#     Amtliche_Vermessungsdaten_Stadt_Zuerich_Jahresendstand_2007
#
# Choose Ausschnitt="Gesamter Datensatz" and Format="GeoPackage"
# and enter your e-mail address; you'll receive a download link
# with the full survey data. Rename the data file to "av2007.gpkg"
# and then run this script to produce "points.csv" and "parcels.csv".

import csv
import re

from fudgeo.geopkg import GeoPackage

_re_sortkey = re.compile(r"^([A-Z]*)(\d+)(.*)$")


def sortkey(s):
    if m := _re_sortkey.match(s):
        prefix, num, rest = m.groups()
        return (prefix, int(num), rest)
    else:
        return (s, 0, "")


def extract_parcels(gpkg, mutations):
    cursor = gpkg.connection.execute(
        "SELECT nummer, geom '[Polygon]', entstehung FROM 'geoz_2007.av_li_liegenschaft_a'"
    )
    parcels = {}
    for num, geom, mut in cursor.fetchall():
        assert geom.srs_id == 2056  # epsg.io/2056 = Swiss CH1903+/LV95
        e = geom.envelope
        mut_id, mut_date = mutations[int(mut)]
        parcels[num] = (
            int(e.min_x),
            int(e.max_x + 0.5),
            int(e.min_y),
            int(e.max_y + 0.5),
            mut_id,
            mut_date,
        )
    with open("parcels.csv", "w") as out:
        w = csv.writer(out)
        w.writerow(
            ["parcel", "min_x", "max_x", "min_y", "max_y", "created_by", "created"]
        )
        for key in sorted(parcels, key=sortkey):
            row = [key] + [str(c) for c in parcels[key]]
            w.writerow(row)


def extract_mutations(gpkg):
    mutations = {}
    for obj_id, mut_id, date in gpkg.connection.execute(
        "SELECT objid, identifikator, gueltigereintrag "
        "FROM 'geoz_2007.av_li_lsnachfuehrung'"
    ):
        date = str(int(date))
        assert len(date) == 8, date
        date = date[:4] + "-" + date[4:6] + "-" + date[6:8]
        mutations[int(obj_id)] = (mut_id, date)
    return mutations


def extract_border_points(gpkg, mutations):
    points = {}
    for id, geom, kind, mut in gpkg.connection.execute(
        "SELECT identifikator, geom '[Point]', punktzeichen_txt, entstehung "
        "FROM 'geoz_2007.av_li_grenzpunkt'"
    ):
        assert id not in points, id
        assert geom.srs_id == 2056, id  # epsg.io/2056 = Swiss CH1903+/LV95
        mut_id, mut_date = mutations[int(mut)]
        points[id] = (id, kind, geom.x, geom.y, mut_id, mut_date)
    with open("border_points.csv", "w") as out:
        w = csv.writer(out)
        w.writerow(["point", "type", "x", "y", "created_by", "created"])
        for key in sorted(points, key=sortkey):
            id, kind, x, y, mut_id, mut_date = points[key]
            w.writerow([id, kind, "%.3f" % x, "%.3f" % y, mut_id, mut_date])


def extract_fixed_points(gpkg, mutations):
    points = {}
    for table in ("av_fi_lfp1", "av_fi_lfp2", "av_fi_lfp3"):
        for id, geom, kind, protection, mut in gpkg.connection.execute(
            "SELECT nummer, geom '[Point]', punktzeichen_txt, schutz_txt, entstehung "
            + "FROM 'geoz_2007.%s'" % table
        ):
            assert id not in points, id
            assert geom.srs_id == 2056, id  # epsg.io/2056 = Swiss CH1903+/LV95
            mut_id, mut_date = mutations[int(mut)]
            points[id] = (id, kind, protection, geom.x, geom.y, mut_id, mut_date)
    with open("fixed_points.csv", "w") as out:
        w = csv.writer(out)
        w.writerow(["point", "type", "protection", "x", "y", "created_by", "created"])
        for key in sorted(points, key=sortkey):
            id, kind, protection, x, y, mut_id, mut_date = points[key]
            if protection == "kein_Schutz":
                protection = ""
            w.writerow([id, kind, protection, "%.3f" % x, "%.3f" % y, mut_id, mut_date])


if __name__ == "__main__":
    gpkg = GeoPackage("av2007.gpkg")
    mutations = extract_mutations(gpkg)
    extract_border_points(gpkg, mutations)
    extract_fixed_points(gpkg, mutations)
    extract_parcels(gpkg, mutations)
