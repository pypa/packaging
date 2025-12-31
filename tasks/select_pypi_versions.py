from __future__ import annotations

# Select a representative subset of versions
#
# The numbers from a 2025 PyPI dataset are:
#
# | Bucket  | Count     | Fraction  |
# | ------- | --------- | --------- |
# | release | 7,086,247 | ~87.0%    |
# | pre     | 532,193   | ~6.5%     |
# | dev     | 451,268   | ~5.5%     |
# | post    | 97,508    | ~1.2%     |
# | invalid | 5,422     | ~0.07%    |
# | epoch   | 1,155     | ~0.014%   |
# | local   | 6         | ~0.00007% |
#
# So this selects a representative subset
# keeping those numbers roughly accurate
import random
import sqlite3

from packaging.version import InvalidVersion, Version

# Get data with:
# curl -L
# https://github.com/pypi-data/pypi-json-data/releases/download/latest/pypi-data.sqlite.gz
# | gzip -d > pypi-data.sqlite


def classify(v: str) -> str:
    try:
        ver = Version(v)
    except InvalidVersion:
        return "invalid"

    if ver.epoch != 0:
        return "epoch"
    if ver.local is not None:
        return "local"
    if ver.pre is not None:
        return "pre"
    if ver.post is not None:
        return "post"
    if ver.dev is not None:
        return "dev"
    return "release"


with sqlite3.connect("pypi-data.sqlite") as conn:
    versions = (row[0] for row in conn.execute("SELECT version FROM projects"))

    totals: dict[str, list[str]] = {}
    for version in versions:
        totals.setdefault(classify(version), []).append(version)

VERSIONS = [
    *random.sample(totals["release"], 1000),
    *random.sample(totals["pre"], 100),
    *random.sample(totals["dev"], 80),
    *random.sample(totals["post"], 60),
    *random.sample(totals["invalid"], 40),
    *random.sample(totals["epoch"], 20),
    *random.sample(totals["local"], 5),
]

with open("version_sample.txt", "w") as f:
    f.writelines(f"{v}\n" for v in VERSIONS)
