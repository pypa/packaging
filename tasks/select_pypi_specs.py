# Select a subset of specifiers

import random
import sqlite3

from packaging.specifiers import InvalidSpecifier, SpecifierSet

# Get data with:
# curl -L
# https://github.com/pypi-data/pypi-json-data/releases/download/latest/pypi-data.sqlite.gz
# | gzip -d > pypi-data.sqlite


def valid_spec(v: str) -> bool:
    try:
        SpecifierSet(v)
    except InvalidSpecifier:
        return False
    return True


with sqlite3.connect("pypi-data.sqlite") as conn:
    TEST_ALL_SPECS = {
        row[0]
        for row in conn.execute("SELECT requires_python FROM projects")
        if row[0] and valid_spec(row[0])
    }

specs = random.sample(list(TEST_ALL_SPECS), 500)

with open("specs_sample.txt", "w") as f:
    f.writelines(f"{v}\n" for v in specs)
