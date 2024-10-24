# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

# Script for extracting points and parcels from the official survey data.
#
# To re-generate the contents of the survey_data directory, do this:
#
# 1. Request the earliest available dataset (December 2007) of the
#    Zürich land survey from the city’s open data portal.
#
#     https://www.stadt-zuerich.ch/geodaten/download/
#     Amtliche_Vermessungsdaten_Stadt_Zuerich_Jahresendstand_2007
#
# 2. Choose Ausschnitt="Gesamter Datensatz" and Format="GeoPackage".
#
# 3. Enter your e-mail address into the Open Data portal and wait for
#    the confirmation e-mail. You'll receive a download link.
#
# 4. Save the downloaded GeoPackage as "av2007.gpkg".
#
# 5. Run this script to re-generate the contents of the "survey_data"
#    directory.

import csv
import os
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
        mut = mutations[int(mut)]
        mut.add_point(e.min_x, e.min_y)
        mut.add_point(e.max_x, e.max_y)
        parcels[num] = (
            int(e.min_x),
            int(e.max_x + 0.5),
            int(e.min_y),
            int(e.max_y + 0.5),
            mut.id,
            mut.date,
        )
    with open("survey_data/parcels.csv", "w") as out:
        w = csv.writer(out)
        w.writerow(
            ["parcel", "min_x", "max_x", "min_y", "max_y", "created_by", "created"]
        )
        for key in sorted(parcels, key=sortkey):
            row = [key] + [str(c) for c in parcels[key]]
            w.writerow(row)


class Mutation(object):
    def __init__(self, id, date):
        self.id = id
        self.date = date
        self.min_x = self.max_x = self.min_y = self.max_y = None

    def add_point(self, x, y):
        if self.min_x is None:
            self.min_x = self.max_x = x
            self.min_y = self.max_y = y
        else:
            self.min_x = min(self.min_x, x)
            self.max_x = max(self.min_x, x)
            self.min_y = min(self.min_y, y)
            self.max_y = max(self.min_y, y)


def extract_mutations(gpkg):
    mutations = {}
    for obj_id, mut_id, date in gpkg.connection.execute(
        "SELECT objid, identifikator, gueltigereintrag "
        "FROM 'geoz_2007.av_li_lsnachfuehrung'"
    ):
        date = str(int(date))
        assert len(date) == 8, date
        date = date[:4] + "-" + date[4:6] + "-" + date[6:8]
        mutations[int(obj_id)] = Mutation(mut_id, date)
    return mutations


def extract_border_points(gpkg, mutations):
    points = {}
    for id, geom, kind, mut in gpkg.connection.execute(
        "SELECT identifikator, geom '[Point]', punktzeichen_txt, entstehung "
        "FROM 'geoz_2007.av_li_grenzpunkt'"
    ):
        assert id not in points, id
        assert geom.srs_id == 2056, id  # epsg.io/2056 = Swiss CH1903+/LV95
        mut = mutations[int(mut)]
        mut.add_point(geom.x, geom.y)
        points[id] = (id, kind, geom.x, geom.y, mut.id, mut.date)
    with open("survey_data/border_points.csv", "w") as out:
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
            mut = mutations[int(mut)]
            mut.add_point(geom.x, geom.y)
            points[id] = (id, kind, protection, geom.x, geom.y, mut.id, mut.date)
    with open("survey_data/fixed_points.csv", "w") as out:
        w = csv.writer(out)
        w.writerow(["point", "type", "protection", "x", "y", "created_by", "created"])
        for key in sorted(points, key=sortkey):
            id, kind, protection, x, y, mut_id, mut_date = points[key]
            if protection == "kein_Schutz":
                protection = ""
            w.writerow([id, kind, protection, "%.3f" % x, "%.3f" % y, mut_id, mut_date])


def write_mutations(mutations):
    with open("survey_data/mutations.csv", "w") as out:
        w = csv.writer(out)
        w.writerow(["mutation", "date", "min_x", "max_x", "min_y", "max_y"])
        muts = {m.id: m for m in mutations.values()}
        for key in sorted(muts, key=sortkey):
            m = muts[key]
            if m.min_x is None:
                min_x = max_x = min_y = max_y = ""
            else:
                min_x = "%.3f" % m.min_x
                max_x = "%.3f" % m.max_x
                min_y = "%.3f" % m.min_y
                max_y = "%.3f" % m.max_y
            w.writerow([m.id, m.date, min_x, max_x, min_y, max_y])


if __name__ == "__main__":
    os.makedirs("survey_data", exist_ok=True)
    gpkg = GeoPackage("av2007.gpkg")
    mutations = extract_mutations(gpkg)
    extract_border_points(gpkg, mutations)
    extract_fixed_points(gpkg, mutations)
    extract_parcels(gpkg, mutations)
    write_mutations(mutations)
