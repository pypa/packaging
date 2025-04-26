from __future__ import annotations

__all__ = [
    "WheelArchiveFile",
    "WheelContentElement",
    "WheelError",
    "WheelMetadata",
    "WheelReader",
    "WheelRecordEntry",
    "WheelWriter",
    "write_wheelfile",
]

import csv
import hashlib
import os.path
import stat
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections import OrderedDict
from collections.abc import Iterable, Iterator
from contextlib import ExitStack
from datetime import datetime, timezone
from email.message import Message
from email.policy import EmailPolicy
from io import BytesIO, StringIO, UnsupportedOperation
from os import PathLike
from pathlib import Path, PurePath
from types import TracebackType
from typing import IO, NamedTuple
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from .tags import Tag
from .utils import (
    BuildTag,
    InvalidWheelFilename,
    NormalizedName,
    parse_wheel_filename,
)
from .version import Version

_exclude_filenames = ("RECORD", "RECORD.jws", "RECORD.p7s")
_default_timestamp = datetime(1980, 1, 1, tzinfo=timezone.utc)
_email_policy = EmailPolicy(max_line_length=0, mangle_from_=False, utf8=True)


class WheelMetadata(NamedTuple):
    name: NormalizedName
    version: Version
    build_tag: BuildTag
    tags: frozenset[Tag]

    @classmethod
    def from_filename(cls, fname: str) -> WheelMetadata:
        name, version, build, tags = parse_wheel_filename(fname)
        return cls(name, version, build, tags)


class WheelRecordEntry(NamedTuple):
    hash_algorithm: str
    hash_value: bytes
    filesize: int


class WheelContentElement(NamedTuple):
    path: PurePath
    hash_value: bytes
    size: int
    stream: IO[bytes]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self.path)!r}, size={self.size!r})"


def _encode_hash_value(hash_value: bytes) -> str:
    return urlsafe_b64encode(hash_value).rstrip(b"=").decode("ascii")


def _decode_hash_value(encoded_hash: str) -> bytes:
    pad = b"=" * (4 - (len(encoded_hash) & 3))
    return urlsafe_b64decode(encoded_hash.encode("ascii") + pad)


class WheelError(Exception):
    pass


class WheelArchiveFile:
    def __init__(
        self, fp: IO[bytes], arcname: str, record_entry: WheelRecordEntry | None
    ):
        self._fp = fp
        self._arcname = arcname
        self._record_entry = record_entry
        if record_entry:
            self._hash = hashlib.new(record_entry.hash_algorithm)
            self._num_bytes_read = 0

    def read(self, amount: int = -1) -> bytes:
        data = self._fp.read(amount)
        if self._record_entry is None:
            return data

        if data:
            self._hash.update(data)
            self._num_bytes_read += len(data)

        if amount < 0 or len(data) < amount:
            # The file has been read in full – check that hash and file size match
            # with the entry in RECORD
            if self._num_bytes_read != self._record_entry.filesize:
                raise WheelError(
                    f"{self._arcname}: file size mismatch: "
                    f"{self._record_entry.filesize} bytes in RECORD, "
                    f"{self._num_bytes_read} bytes in archive"
                )
            elif self._hash.digest() != self._record_entry.hash_value:
                raise WheelError(
                    f"{self._arcname}: hash mismatch: "
                    f"{self._record_entry.hash_value.hex()} in RECORD, "
                    f"{self._hash.hexdigest()} in archive"
                )

        return data

    def __enter__(self) -> WheelArchiveFile:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        self._fp.close()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._arcname!r})"


class WheelReader:
    name: NormalizedName
    version: Version
    _zip: ZipFile
    _dist_info_dir: str
    _data_dir: str
    _record_entries: OrderedDict[str, WheelRecordEntry]

    def __init__(self, path_or_fd: str | PathLike[str] | IO[bytes]):
        self.path_or_fd = path_or_fd

        if isinstance(path_or_fd, (str, PathLike)):
            fname = Path(path_or_fd).name
            try:
                self.name, self.version = parse_wheel_filename(fname)[:2]
            except InvalidWheelFilename as exc:
                raise WheelError(str(exc)) from None

    def __enter__(self) -> WheelReader:
        self._zip = ZipFile(self.path_or_fd, "r")

        # See if the expected .dist-info directory is in place by searching for RECORD
        # in the expected directory. Wheels made with older versions of "wheel" did not
        # properly normalize the names, so the name of the .dist-info directory does not
        # match the expectation there.
        dist_info_dir: str | None = None
        if hasattr(self, "name"):
            dist_info_dir = f"{self.name}-{self.version}.dist-info"
            try:
                self._zip.getinfo(f"{dist_info_dir}/RECORD")
            except KeyError:
                dist_info_dir = None
            else:
                self._dist_info_dir = dist_info_dir
                self._data_dir = f"{self.name}-{self.version}.data"

        # If no .dist-info directory could not be found yet, resort to scanning the
        # archive's file names for any .dist-info directory containing a RECORD file.
        if dist_info_dir is None:
            try:
                for zinfo in reversed(self._zip.infolist()):
                    if zinfo.filename.endswith(".dist-info/RECORD"):
                        dist_info_dir = zinfo.filename.rsplit("/", 1)[0]
                        namever = dist_info_dir.rsplit(".", 1)[0]
                        name, version = namever.rpartition("-")[::2]
                        if name and version:
                            self.name = NormalizedName(name)
                            self.version = Version(version)
                            self._dist_info_dir = dist_info_dir
                            self._data_dir = dist_info_dir.replace(
                                ".dist-info", ".data"
                            )
                            break
                else:
                    raise WheelError(
                        "Cannot find a valid .dist-info directory. "
                        "Is this really a wheel file?"
                    )
            except BaseException:
                self._zip.close()
                raise

        self._record_entries = self._read_record()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        self._zip.close()
        self._record_entries.clear()
        del self._zip

    def _read_record(self) -> OrderedDict[str, WheelRecordEntry]:
        entries = OrderedDict()
        try:
            contents = self.read_dist_info("RECORD")
        except WheelError:
            raise WheelError(f"Missing {self._dist_info_dir}/RECORD file") from None

        reader = csv.reader(
            contents.strip().split("\n"),
            delimiter=",",
            quotechar='"',
            lineterminator="\n",
        )
        for row in reader:
            if not row:
                break

            path, hash_digest, filesize = row
            if hash_digest:
                algorithm, hash_digest = hash_digest.split("=")
                try:
                    hashlib.new(algorithm)
                except ValueError:
                    raise WheelError(
                        f"Unsupported hash algorithm: {algorithm}"
                    ) from None

                if algorithm.lower() in {"md5", "sha1"}:
                    raise WheelError(
                        f"Weak hash algorithm ({algorithm}) is not permitted by PEP 427"
                    )

                entries[path] = WheelRecordEntry(
                    algorithm, _decode_hash_value(hash_digest), int(filesize)
                )

        return entries

    @property
    def dist_info_dir(self) -> str:
        return self._dist_info_dir

    @property
    def data_dir(self) -> str:
        return self._data_dir

    @property
    def dist_info_filenames(self) -> list[PurePath]:
        return [
            PurePath(fname)
            for fname in self._zip.namelist()
            if fname.startswith(self._dist_info_dir)
        ]

    @property
    def filenames(self) -> list[PurePath]:
        return [PurePath(fname) for fname in self._zip.namelist()]

    def read_dist_info(self, filename: str) -> str:
        filename = self.dist_info_dir + "/" + filename
        try:
            contents = self._zip.read(filename)
        except KeyError:
            raise WheelError(f"File {filename!r} not found") from None

        return contents.decode("utf-8")

    def iterate_contents(self) -> Iterator[WheelContentElement]:
        for fname, entry in self._record_entries.items():
            with self._zip.open(fname, "r") as stream:
                yield WheelContentElement(
                    PurePath(fname), entry.hash_value, entry.filesize, stream
                )

    def validate_record(self) -> None:
        """Verify the integrity of the contained files."""
        for zinfo in self._zip.infolist():
            # Ignore signature files
            basename = os.path.basename(zinfo.filename)
            if basename in _exclude_filenames:
                continue

            with self.open(zinfo.filename) as fp:
                while True:
                    if not fp.read(65536):
                        break

    def extractall(self, base_path: str | PathLike[str]) -> None:
        basedir = Path(base_path)
        if not basedir.exists():
            raise WheelError(f"{basedir} does not exist")
        elif not basedir.is_dir():
            raise WheelError(f"{basedir} is not a directory")

        for fname in self._zip.namelist():
            target_path = basedir.joinpath(fname)
            target_path.parent.mkdir(0o755, True, True)
            with self.open(fname) as infile, target_path.open("wb") as outfile:
                while True:
                    data = infile.read(65536)
                    if not data:
                        break

                    outfile.write(data)

    def open(self, archive_name: str) -> WheelArchiveFile:
        basename = os.path.basename(archive_name)
        if basename in _exclude_filenames:
            record_entry = None
        else:
            try:
                record_entry = self._record_entries[archive_name]
            except KeyError:
                raise WheelError(f"No hash found for file {archive_name!r}") from None

        return WheelArchiveFile(
            self._zip.open(archive_name), archive_name, record_entry
        )

    def read_file(self, archive_name: str) -> bytes:
        with self.open(archive_name) as fp:
            return fp.read()

    def read_data_file(self, filename: str) -> bytes:
        archive_path = self._data_dir + "/" + filename.strip("/")
        return self.read_file(archive_path)

    def read_distinfo_file(self, filename: str) -> bytes:
        archive_path = self._dist_info_dir + "/" + filename.strip("/")
        return self.read_file(archive_path)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.path_or_fd})"


def write_wheelfile(
    fp: IO[bytes], /, *, generator: str, metadata: WheelMetadata, root_is_purelib: bool
) -> None:
    msg = Message(policy=_email_policy)
    msg["Wheel-Version"] = "1.0"  # of the spec
    msg["Generator"] = generator
    msg["Root-Is-Purelib"] = str(root_is_purelib).lower()
    if metadata.build_tag:
        msg["Build"] = str(metadata.build_tag[0]) + metadata.build_tag[1]

    for tag in sorted(metadata.tags, key=lambda t: (t.interpreter, t.abi, t.platform)):
        msg["Tag"] = f"{tag.interpreter}-{tag.abi}-{tag.platform}"

    fp.write(msg.as_bytes())


class WheelWriter:
    def __init__(
        self,
        path_or_fd: str | PathLike[str] | IO[bytes],
        /,
        *,
        generator: str,
        metadata: WheelMetadata | None = None,
        root_is_purelib: bool = True,
        compress: bool = True,
        hash_algorithm: str = "sha256",
    ):
        self.path_or_fd = path_or_fd
        self.generator = generator
        self.root_is_purelib = root_is_purelib
        self.hash_algorithm = hash_algorithm
        self._compress_type = ZIP_DEFLATED if compress else ZIP_STORED

        if metadata:
            self.metadata = metadata
        elif isinstance(path_or_fd, (str, PathLike)):
            filename = Path(path_or_fd).name
            self.metadata = WheelMetadata.from_filename(filename)
        else:
            raise WheelError("path_or_fd is not a path, and metadata was not provided")

        if hash_algorithm not in hashlib.algorithms_available:
            raise ValueError(f"Hash algorithm {hash_algorithm!r} is not available")
        elif hash_algorithm in ("md5", "sha1"):
            raise ValueError(
                f"Weak hash algorithm ({hash_algorithm}) is not permitted by PEP 427"
            )

        self._dist_info_dir = f"{self.metadata.name}-{self.metadata.version}.dist-info"
        self._data_dir = f"{self.metadata.name}-{self.metadata.version}.data"
        self._record_path = f"{self._dist_info_dir}/RECORD"
        self._record_entries: dict[str, WheelRecordEntry] = OrderedDict()

    def __enter__(self) -> WheelWriter:
        self._zip = ZipFile(self.path_or_fd, "w", compression=self._compress_type)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        try:
            if not exc_type:
                if f"{self._dist_info_dir}/WHEEL" not in self._record_entries:
                    self._write_wheelfile()

                self._write_record()
        finally:
            self._zip.close()

    def _write_record(self) -> None:
        data = StringIO()
        writer = csv.writer(data, delimiter=",", quotechar='"', lineterminator="\n")
        writer.writerows(
            [
                (
                    fname,
                    entry.hash_algorithm + "=" + _encode_hash_value(entry.hash_value),
                    entry.filesize,
                )
                for fname, entry in self._record_entries.items()
            ]
        )
        writer.writerow((self._record_path, "", ""))
        self.write_distinfo_file("RECORD", data.getvalue())

    def _write_wheelfile(self) -> None:
        buffer = BytesIO()
        write_wheelfile(
            buffer,
            generator=self.generator,
            metadata=self.metadata,
            root_is_purelib=self.root_is_purelib,
        )
        self.write_distinfo_file("WHEEL", buffer.getvalue())

    def write_metadata(self, items: Iterable[tuple[str, str]]) -> None:
        msg = Message(policy=_email_policy)
        for key, value in items:
            key = key.title()
            if key == "Description":
                msg.set_payload(value.encode("utf-8"))
            else:
                msg.add_header(key, value)

        if "Metadata-Version" not in msg:
            msg["Metadata-Version"] = "2.3"
        if "Name" not in msg:
            msg["Name"] = self.metadata.name
        if "Version" not in msg:
            msg["Version"] = str(self.metadata.version)

        self.write_distinfo_file("METADATA", msg.as_bytes())

    def write_file(
        self,
        name: str | PurePath,
        contents: bytes | str | PathLike[str] | IO[bytes],
        *,
        timestamp: datetime = _default_timestamp,
    ) -> None:
        arcname = PurePath(name).as_posix()
        gmtime = time.gmtime(timestamp.timestamp())
        zinfo = ZipInfo(arcname, gmtime[:6])
        zinfo.compress_type = self._compress_type
        zinfo.external_attr = 0o664 << 16
        with ExitStack() as exit_stack:
            fp = exit_stack.enter_context(self._zip.open(zinfo, "w"))
            if isinstance(contents, str):
                contents = contents.encode("utf-8")
            elif isinstance(contents, PathLike):
                contents = exit_stack.enter_context(Path(contents).open("rb"))

            if isinstance(contents, bytes):
                file_size = len(contents)
                fp.write(contents)
                hash_ = hashlib.new(self.hash_algorithm, contents)
            else:
                try:
                    st = os.stat(contents.fileno())
                except (AttributeError, UnsupportedOperation):
                    pass
                else:
                    zinfo.external_attr = (
                        stat.S_IMODE(st.st_mode) | stat.S_IFMT(st.st_mode)
                    ) << 16

                hash_ = hashlib.new(self.hash_algorithm)
                while True:
                    buffer = contents.read(65536)
                    if not buffer:
                        file_size = contents.tell()
                        break

                    hash_.update(buffer)
                    fp.write(buffer)

        self._record_entries[arcname] = WheelRecordEntry(
            self.hash_algorithm, hash_.digest(), file_size
        )

    def write_files_from_directory(self, directory: str | PathLike[str]) -> None:
        basedir = Path(directory)
        if not basedir.exists():
            raise WheelError(f"{basedir} does not exist")
        elif not basedir.is_dir():
            raise WheelError(f"{basedir} is not a directory")

        for root, _dirs, files in os.walk(basedir):
            for fname in files:
                path = Path(root) / fname
                relative = path.relative_to(basedir)
                if relative.as_posix() != self._record_path:
                    self.write_file(relative, path)

    def write_data_file(
        self,
        filename: str,
        contents: bytes | str | PathLike[str] | IO[bytes],
        *,
        timestamp: datetime = _default_timestamp,
    ) -> None:
        archive_path = self._data_dir + "/" + filename.strip("/")
        self.write_file(archive_path, contents, timestamp=timestamp)

    def write_distinfo_file(
        self,
        filename: str,
        contents: bytes | str | IO[bytes],
        *,
        timestamp: datetime = _default_timestamp,
    ) -> None:
        archive_path = self._dist_info_dir + "/" + filename.strip()
        self.write_file(archive_path, contents, timestamp=timestamp)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({self.path_or_fd}, "
            f"generator={self.generator!r})"
        )
