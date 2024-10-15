# SPDX-FileCopyrightText: 2024 Sascha Brawer <sascha@brawer.ch>
# SPDX-License-Identifier: MIT

# Helper to find the date of a cadastral mutation in Zürich.
# Some historical mutations have left a trace in the cadastral survey
# database of 2007 (the earliest digitially available year). Some others
# we take from the configuration file in src/mutation_dates.csv.

import csv
import os


def _read_mutation_dates():
    dates = {}
    root = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(root, "src", "mutation_dates.csv")) as fp:
        for row in csv.DictReader(fp):
            dates[row["mutation"]] = row["date"]
    with open(os.path.join(root, "survey_data", "mutations.csv")) as fp:
        for row in csv.DictReader(fp):
            if d := row["date"]:
                dates[row["mutation"]] = d
    return dates


dates = _read_mutation_dates()
