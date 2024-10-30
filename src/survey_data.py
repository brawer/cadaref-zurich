# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

# Provides access to the extracted survey data (derived from the
# cadastral survey of 2007) stored in survey_data.

from collections import namedtuple
import csv
from datetime import date, timedelta
import os


# Map from point classes in survey_data/border_points.csv to cartographic
# symbols. Symbol IDs are the same as returned by detect_map_symbols()
# in src/classify.py.
BORDER_POINT_SYMBOLS = {
    "unversichert": "black_dot",
    "Bolzen": "white_circle",
    "Stein": "white_circle",
}


# Map from point classes in survey_data/border_points.csv to cartographic
# symbols. Symbol IDs are the same as returned by detect_map_symbols()
# in src/classify.py.
FIXED_POINT_SYMBOLS = {
    "unversichert": "black_dot",
    "Bolzen": "white_circle",
    "Stein": "white_circle",
}


# Map from point classes in src/deleted_points.csv to cartographic symbols.
# Cartographic symbol IDs are the same as returned by detect_map_symbols()
# in src/classify.py.
DELETED_POINT_SYMBOLS = {
    "2": "double_white_circle",
    "4": "white_circle",
}


Mutation = namedtuple(
    "Mutation",
    [
        "mutation_id",
        "min_x",
        "max_x",
        "min_y",
        "max_y",
        "date",
    ],
)


Parcel = namedtuple(
    "Parcel",
    [
        "parcel_id",
        "min_x",
        "max_x",
        "min_y",
        "max_y",
        "created_by",
        "created",
    ],
)


def _read_mutations():
    mutations = {}

    src_path = os.path.dirname(__file__)
    with open(os.path.join(src_path, "mutation_dates.csv")) as fp:
        for row in csv.DictReader(fp):
            mutation = Mutation(
                mutation_id=row["mutation"],
                min_x=None,
                max_x=None,
                min_y=None,
                max_y=None,
                date=date.fromisoformat(row["date"]),
            )

    survey_data_path = os.path.join(src_path, "..", "survey_data")
    with open(os.path.join(survey_data_path, "mutations.csv")) as fp:
        for row in csv.DictReader(fp):
            mutation = Mutation(
                mutation_id=row["mutation"],
                min_x=float(row["min_x"]) if row["min_x"] else None,
                max_x=float(row["max_x"]) if row["max_x"] else None,
                min_y=float(row["min_y"]) if row["min_y"] else None,
                max_y=float(row["max_y"]) if row["max_y"] else None,
                date=date.fromisoformat(row["date"]),
            )
            mutations[mutation.mutation_id] = mutation
    return mutations


def _read_parcels():
    parcels = {}
    survey_data = os.path.join(os.path.dirname(__file__), "..", "survey_data")
    with open(os.path.join(survey_data, "parcels.csv")) as fp:
        for row in csv.DictReader(fp):
            parcel = Parcel(
                parcel_id=row["parcel"],
                min_x=float(row["min_x"]),
                max_x=float(row["max_x"]),
                min_y=float(row["min_y"]),
                max_y=float(row["max_y"]),
                created_by=row["created_by"],
                created=date.fromisoformat(row["created"]),
            )
            parcels[parcel.parcel_id] = parcel
    return parcels


parcels = _read_parcels()
mutations = _read_mutations()


def make_geojson(f):
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [f.min_x, f.min_y],
                    [f.max_x, f.min_y],
                    [f.max_x, f.max_y],
                    [f.min_x, f.max_y],
                    [f.min_x, f.min_y],
                ]
            ],
        },
    }
    if type(f) == Parcel and f.parcel_id:
        feature["id"] = f.parcel_id
    elif type(f) == Mutation and f.mutation_id:
        feature["id"] = f.mutation_id
    return feature


# Returns the set of survey points (fixed points, boundary points)
# that were present in the given bounding box at the time of map_date.
def read_points(min_x, min_y, max_x, max_y, map_date):
    # We don't really care too much about dates, only roughly.
    # But we would not want to use the location of a survey marker
    # constructed in 1980 when matching a plan from 1921.
    # So we allow for 1 years of slack when comparing dates.
    date_slack = timedelta(days=365)

    survey_data = os.path.join(os.path.dirname(__file__), "..", "survey_data")
    with open(os.path.join(survey_data, "border_points.csv")) as fp:
        for row in csv.DictReader(fp):
            point_id = row["point"]
            symbol = BORDER_POINT_SYMBOLS.get(row["type"], "")
            if "white" not in symbol:
                continue
            x, y = float(row["x"]), float(row["y"])
            if not (min_x <= x <= max_x and min_y <= y <= max_y):
                continue
            if map_date:
                created = date.fromisoformat(row["created"])
                if created > map_date + date_slack:
                    continue
            yield (point_id, x, y, symbol)

    with open(os.path.join(survey_data, "fixed_points.csv")) as fp:
        for row in csv.DictReader(fp):
            point_id = row["point"]
            symbol = FIXED_POINT_SYMBOLS.get(row["type"], "")
            if "white" not in symbol:
                continue
            x, y = float(row["x"]), float(row["y"])
            if not (min_x <= x <= max_x and min_y <= y <= max_y):
                continue
            if map_date:
                created = date.fromisoformat(row["created"])
                if created > map_date + date_slack:
                    continue
            yield (point_id, x, y, symbol)

    src_path = os.path.dirname(__file__)
    with open(os.path.join(src_path, "deleted_points.csv")) as fp:
        for row in csv.DictReader(fp):
            created, deleted = None, None
            if mut := mutations.get(row["Erstellmutation"]):
                created = mut.date
            if mut := mutations.get(row["Löschmutation"]):
                deleted = mut.date
            point_id = row["Punktnummer"]
            symbol = DELETED_POINT_SYMBOLS.get(row["Kl"], "")
            if "white" not in symbol:
                continue
            x, y = float(row["X [LV95]"]), float(row["Y [LV95]"])
            if not (min_x <= x <= max_x and min_y <= y <= max_y):
                continue
            if created and map_date and created > map_date + date_slack:
                continue
            if deleted and map_date and deleted < map_date - date_slack:
                continue
            yield (point_id, x, y, symbol)
