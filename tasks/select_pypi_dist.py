# Select a subset of specifiers

import random
import sqlite3
import json

from packaging.requirements import Requirement, InvalidRequirement

# Get data with:
# curl -L
# https://github.com/pypi-data/pypi-json-data/releases/download/latest/pypi-data.sqlite.gz
# | gzip -d > pypi-data.sqlite

def valid_requirement(req: str) -> bool:
    try:
        Requirement(req)
    except InvalidRequirement:
        return False
    return True

with sqlite3.connect("pypi-data.sqlite") as conn:
    NESTED_DIST = (
        sublist
        for row in conn.execute("SELECT requires_dist FROM projects")
        if (sublist := json.loads(row[0]))
    )
    ALL_DIST_W_INVALID = {item for sublist in NESTED_DIST for item in sublist}
    ALL_DIST = {r for r in ALL_DIST_W_INVALID if valid_requirement(r)}

dist = random.sample(list(ALL_DIST), 500)
with open("dist_sample.txt", "w") as f:
    f.writelines(f"{v}\n" for v in dist)
