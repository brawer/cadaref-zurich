# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

# Provides access to the extracted survey data (derived from the
# cadastral survey of 2007) stored in survey_data.

from collections import namedtuple
import csv
from datetime import date
import os


Mutation = namedtuple(
    "Mutation", [
        "mutation_id", "min_x", "max_x", "min_y", "max_y", "date",
    ]
)

Parcel = namedtuple(
    "Parcel", [
        "parcel_id", "min_x", "max_x", "min_y", "max_y", "created_by", "created",
    ]
)


def _read_mutations():
    mutations = {}
    survey_data = os.path.join(os.path.dirname(__file__), "..", "survey_data")
    with open(os.path.join(survey_data, "mutations.csv")) as fp:
        for row in csv.DictReader(fp):
            mutation = Mutation(
                mutation_id = row["mutation"],
                min_x = float(row["min_x"]) if row["min_x"] else None,
                max_x = float(row["max_x"]) if row["max_x"] else None,
                min_y = float(row["min_y"]) if row["min_y"] else None,
                max_y = float(row["max_y"]) if row["max_y"] else None,
                date=date.fromisoformat(row["date"]))
            mutations[mutation.mutation_id] = mutation
    return mutations


def _read_parcels():
    parcels = {}
    survey_data = os.path.join(os.path.dirname(__file__), "..", "survey_data")
    with open(os.path.join(survey_data, "parcels.csv")) as fp:
        for row in csv.DictReader(fp):
            parcel = Parcel(
                parcel_id = row["parcel"],
                min_x = float(row["min_x"]),
                max_x = float(row["max_x"]),
                min_y = float(row["min_y"]),
                max_y = float(row["max_y"]),
                created_by = row["created_by"],
                created=date.fromisoformat(row["created"]))
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
                [f.min_x, f.min_y],
                [f.max_x, f.min_y],
                [f.max_x, f.max_y],
                [f.min_x, f.max_y],
                [f.min_x, f.min_y],
            ],
        }
    }
    if type(f) == Parcel and f.parcel_id:
        feature["id"] = f.parcel_id
    elif type(f) == Mutation and f.mutation_id:
        feature["id"] = f.mutation_id
    return feature
