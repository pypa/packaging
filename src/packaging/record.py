# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""
Implements functionality for working with the file format described here:

https://packaging.python.org/en/latest/specifications/recording-installed-packages/#the-record-file
"""

from __future__ import annotations

import base64
import csv
import functools
import hashlib
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from io import StringIO


@functools.lru_cache
def _expected_digest_size(algorithm: str) -> int:
    return hashlib.new(algorithm).digest_size


class InvalidRecordHash(ValueError):
    pass


@dataclass(frozen=True)
class RecordHash:
    algorithm: str
    digest: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.algorithm, str):
            raise TypeError("algorithm must have type 'str'")

        if self.algorithm not in hashlib.algorithms_guaranteed:
            raise InvalidRecordHash(
                f"{self.algorithm!r} is not a guaranteed hash algorithm"
            )

        expected_len = _expected_digest_size(self.algorithm)

        if expected_len <= 0:
            # hashlib returns a digest_size of 0 for variable-length hashes,
            # like SHAKE-128. While the spec takes no stance on such algorithms,
            # using one would make it impossible for a reader to calculate its own
            # digest of a file for comparison without first parsing the recorded digest.
            # That seems unreasonable, so we prohibit such algorithms.
            raise InvalidRecordHash(
                f"{self.algorithm!r} does not have fixed length digests"
            )

        if not isinstance(self.digest, bytes):
            raise TypeError("digest must have type 'bytes'")

        if len(self.digest) != expected_len:
            raise InvalidRecordHash(
                f"digest has wrong length: {len(self.digest)} (expected {expected_len})"
            )

    def __str__(self) -> str:
        digest_str = base64.urlsafe_b64encode(self.digest).decode().rstrip("=")
        return f"{self.algorithm}={digest_str}"


_RE_BASE64_URLSAFE = re.compile(r"[0-9A-Za-z_-]*")


def parse_record_hash(hash_str: str, /) -> RecordHash:
    algorithm, sep, digest_str = hash_str.partition("=")

    if not sep:
        raise InvalidRecordHash("'=' not found")

    if not _RE_BASE64_URLSAFE.fullmatch(digest_str):
        raise InvalidRecordHash("invalid Base64 encoding")

    pad_len = 4 - len(digest_str) % 4
    if pad_len == 3:
        raise InvalidRecordHash("invalid Base64 encoding")

    digest = base64.urlsafe_b64decode(digest_str + "=" * pad_len)

    return RecordHash(algorithm, digest)


class InvalidRecord(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    path: str
    hash: RecordHash | None = None
    size: int | None = None

    def __init__(
        self, path: str, *, hash: RecordHash | None = None, size: int | None = None
    ):
        # This constructor emulates kw_only (which isn't available until Python 3.10)
        # for hash and size.
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "hash", hash)
        object.__setattr__(self, "size", size)

    def __post_init__(self) -> None:
        if not isinstance(self.path, str):
            raise TypeError("path must have type 'str'")

        if not self.path:
            raise InvalidRecord("path must not be empty")

        if self.path.endswith((os.sep, os.altsep or os.sep)):
            raise InvalidRecord("path must not be a directory path")

        if self.hash is not None and not isinstance(self.hash, RecordHash):
            raise TypeError("hash must be either None or have type 'RecordHash'")

        if self.size is not None:
            if not isinstance(self.size, int):
                raise TypeError("size must be either None or have type 'int'")

            if self.size < 0:
                raise InvalidRecord("size must not be negative")


class InvalidRecordSet(ValueError):
    pass


class RecordSet:
    _records: dict[str, Record]

    def record_for_path(self, path: str, /) -> Record:
        return self._records[path]

    def __iter__(self) -> Iterator[Record]:
        return iter(self._records.values())

    def to_csv(self) -> str:
        file = StringIO()
        writer = csv.writer(file)

        for record in self:
            writer.writerow(
                (
                    record.path,
                    "" if record.hash is None else str(record.hash),
                    "" if record.size is None else str(record.size),
                )
            )

        return file.getvalue()


def parse_record_csv(data: str, /) -> RecordSet:
    builder = RecordSetBuilder()

    file = StringIO(data)
    reader = csv.reader(file)

    for row in reader:
        if len(row) != 3:
            raise InvalidRecordSet(f"row has {len(row)} fields (expected 3)")

        path, hash_str, size_str = row

        try:
            if hash_str:
                hash = parse_record_hash(hash_str)
            else:
                hash = None

            if size_str:
                size = int(size_str)
            else:
                size = None

            record = Record(path, hash=hash, size=size)
        except ValueError as ex:
            raise InvalidRecordSet(f"invalid record for path {path!r}: {ex}") from ex

        builder.add(record)

    return builder.build()


class RecordSetBuilder:
    def __init__(self) -> None:
        self._records: dict[str, Record] = {}

    def add(self, record: Record, /) -> None:
        if record.path in self._records:
            raise InvalidRecordSet(f"duplicate record path {record.path}")

        self._records[record.path] = record

    def build(self) -> RecordSet:
        rs = RecordSet()
        rs._records = self._records.copy()
        return rs
