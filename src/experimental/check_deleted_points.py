# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

import csv
import os
import re

DELETED = re.compile(r"^2\d{4}|[A-Z]{2}\d{3,4}$")
CREATED = re.compile(r"^2\d{4}|[A-Z]{2}\d{3,4}|PV[A-Z]{2}\d?$")
POINT_ID = re.compile(r"^[12]\d{4}|[A-Z]{3}\d{4}$")
AC = re.compile(r"^\d{2}$")


# TODO: Review "todo-check-deleted-points"
# (a) Compare list of points against deleted_points.csv.
#     Make sure to manually review any points in deleted_points.csv
#     but not in deleted_points/*.csv
# (b) Look at todo-check-deleted-points for weird mutations.

# TODO: Check mutation IDs against list of known mutations
# from survey data (and possibly rendered mutations)

# TODO: Check format and range of X and Y coordinates.

# TODO: Check that supposedly deleted points aren't present
# in survey data (either by coord or by id; best to check both).


def created_ok(s):
    if s in ("", "51153", "2VAR"):
        return True
    else:
        return CREATED.match(s) is not None


def deleted_ok(s):
    return DELETED.match(s) is not None


def point_id_ok(s):
    return POINT_ID.match(s) is not None


def ac_ok(s):
    return AC.match(s) is not None


def kl_ok(s):
    return s in ("3", "4", "5")


if __name__ == "__main__":
    src_dir = os.path.join(os.path.dirname(__file__))
    path = os.path.join(src_dir, "deleted_points.csv")
    with open(path, "r") as fp:
        for row in csv.DictReader(fp):
            if not created_ok(row["Gelöscht"]):
                print(row)
                continue
            if not point_id_ok(row["Punktnummer"]):
                print(row)
                continue
            if not ac_ok(row["AC"]):
                print(row)
                continue
            if not kl_ok(row["Kl"]):
                print(row)
                continue
            if not created_ok(row["Erstellt"]):
                print(row)
                continue
