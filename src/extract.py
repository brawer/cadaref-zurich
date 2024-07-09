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


def extract_parcels(gpkg):
    cursor = gpkg.connection.execute(
        "SELECT nummer, geom '[Polygon]' FROM 'geoz_2007.av_li_liegenschaft_a'"
    )
    parcels = {}
    for num, geom in cursor.fetchall():
        assert geom.srs_id == 2056  # epsg.io/2056 = Swiss CH1903+/LV95
        e = geom.envelope
        parcels[num] = (
            int(e.min_x),
            int(e.max_x + 0.5),
            int(e.min_y),
            int(e.max_y + 0.5),
        )
    with open("parcels.csv", "w") as out:
        w = csv.writer(out)
        w.writerow(["parcel", "min_x", "max_x", "min_y", "max_y"])
        for key in sorted(parcels, key=sortkey):
            row = [key] + [str(c) for c in parcels[key]]
            w.writerow(row)


def extract_points(gpkg):
    points = {}
    for id, geom, kind in gpkg.connection.execute(
        "SELECT identifikator, geom '[Point]', punktzeichen_txt "
        "FROM 'geoz_2007.av_li_grenzpunkt'"
    ):
        assert id not in points, id
        assert geom.srs_id == 2056, id  # epsg.io/2056 = Swiss CH1903+/LV95
        points[id] = (id, kind, "", geom.x, geom.y)
    for table in ("av_fi_lfp1", "av_fi_lfp2", "av_fi_lfp3"):
        for id, geom, kind, protection in gpkg.connection.execute(
            "SELECT nummer, geom '[Point]', punktzeichen_txt, schutz_txt "
            + "FROM 'geoz_2007.%s'" % table
        ):
            assert id not in points, id
            assert geom.srs_id == 2056, id  # epsg.io/2056 = Swiss CH1903+/LV95
            points[id] = (id, kind, protection, geom.x, geom.y)
    with open("points.csv", "w") as out:
        w = csv.writer(out)
        w.writerow(["point", "type", "protection", "x", "y"])
        for key in sorted(points, key=sortkey):
            id, kind, protection, x, y = points[key]
            if protection == "kein_Schutz":
                protection = ""
            w.writerow([id, kind, protection, "%.3f" % x, "%.3f" % y])


if __name__ == "__main__":
    gpkg = GeoPackage("av2007.gpkg")
    extract_points(gpkg)
    extract_parcels(gpkg)
