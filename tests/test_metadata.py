# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import dataclasses
import json
import tarfile
from email.policy import compat32
from hashlib import md5
from itertools import chain
from pathlib import Path
from textwrap import dedent
from typing import Iterator, List
from urllib.request import urlopen
from zipfile import ZipFile

import pytest

from packaging.metadata import (
    CoreMetadata,
    DynamicNotAllowed,
    InvalidCoreMetadataField,
    InvalidDynamicField,
    MissingRequiredFields,
    StaticFieldCannotBeDynamic,
)
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

HERE = Path(__file__).parent
EXAMPLES = HERE / "metadata_examples.csv"
DOWNLOADS = HERE / "downloads"


class TestCoreMetadata:
    def test_simple(self):
        example = {"name": "simple", "version": "0.1", "requires_dist": ["appdirs>1.2"]}
        metadata = CoreMetadata(**example)
        req = next(iter(metadata.requires_dist))
        assert isinstance(req, Requirement)

    def test_replace(self):
        example = {
            "name": "simple",
            "dynamic": ["version"],
            "author_email": ["me@example.com"],
            "requires_dist": ["appdirs>1.2"],
        }
        metadata = CoreMetadata(**example)

        # Make sure replace goes through validations and transformations
        attrs = {
            "version": "0.2",
            "dynamic": [],
            "author_email": [("name", "me@example.com")],
            "requires_dist": ["appdirs>1.4"],
        }
        metadata1 = dataclasses.replace(metadata, **attrs)
        req = next(iter(metadata1.requires_dist))
        assert req == Requirement("appdirs>1.4")

        with pytest.raises(InvalidCoreMetadataField):
            dataclasses.replace(metadata, dynamic=["myfield"])
        with pytest.raises(InvalidDynamicField):
            dataclasses.replace(metadata, dynamic=["name"])
        with pytest.raises(StaticFieldCannotBeDynamic):
            dataclasses.replace(metadata, version="0.1")

    PER_VERSION_EXAMPLES = {
        "1.1": {
            "has_dynamic_fields": False,
            "is_final_metadata": True,
            "file_contents": """\
                Metadata-Version: 1.1
                Name: BeagleVote
                Version: 1.0a2
                Platform: ObscureUnix, RareDOS
                Supported-Platform: RedHat 7.2
                Supported-Platform: i386-win32-2791
                Summary: A module for collecting votes from beagles.
                Description: This module collects votes from beagles
                             in order to determine their electoral wishes.
                             Do *not* try to use this module with basset hounds;
                             it makes them grumpy.
                Keywords: dog puppy voting election
                Home-page: http://www.example.com/~cschultz/bvote/
                Author: C. Schultz, Universal Features Syndicate,
                        Los Angeles, CA <cschultz@peanuts.example.com>
                Author-email: "C. Schultz" <cschultz@example.com>
                License: This software may only be obtained by sending the
                         author a postcard, and then the user promises not
                         to redistribute it.
                Classifier: Development Status :: 4 - Beta
                Classifier: Environment :: Console (Text Based)
                Requires: re
                Requires: sys
                Requires: zlib
                Requires: xml.parsers.expat (>1.0)
                Requires: psycopg
                Provides: xml
                Provides: xml.utils
                Provides: xml.utils.iso8601
                Provides: xml.dom
                Provides: xmltools (1.3)
                Obsoletes: Gorgon
            """,  # based on PEP 314
        },
        "2.1": {
            "has_dynamic_fields": False,
            "is_final_metadata": True,
            "file_contents": """\
                Metadata-Version: 2.1
                Name: BeagleVote
                Version: 1.0a2
                Platform: ObscureUnix, RareDOS
                Supported-Platform: RedHat 7.2
                Supported-Platform: i386-win32-2791
                Summary: A module for collecting votes from beagles.
                Description: This project provides powerful math functions
                        |For example, you can use `sum()` to sum numbers:
                        |
                        |Example::
                        |
                        |    >>> sum(1, 2)
                        |    3
                        |
                Keywords: dog puppy voting election
                Home-page: http://www.example.com/~cschultz/bvote/
                Author: C. Schultz, Universal Features Syndicate,
                        Los Angeles, CA <cschultz@peanuts.example.com>
                Author-email: "C. Schultz" <cschultz@example.com>
                Maintainer: C. Schultz, Universal Features Syndicate,
                        Los Angeles, CA <cschultz@peanuts.example.com>
                Maintainer-email: "C. Schultz" <cschultz@example.com>
                License: This software may only be obtained by sending the
                        author a postcard, and then the user promises not
                        to redistribute it.
                Classifier: Development Status :: 4 - Beta
                Classifier: Environment :: Console (Text Based)
                Requires-Dist: pkginfo
                Requires-Dist: PasteDeploy
                Requires-Dist: zope.interface (>3.5.0)
                Provides-Dist: OtherProject
                Provides-Dist: AnotherProject (3.4)
                Provides-Dist: virtual_package
                Obsoletes-Dist: Gorgon
                Obsoletes-Dist: OtherProject (<3.0)
                Requires-Python: 2.5
                Requires-Python: >2.1
                Requires-Python: >=2.3.4
                Requires-Python: >=2.5,<2.7
                Requires-External: C
                Requires-External: libpng (>=1.5)
                Project-URL: Bug Tracker, https://github.com/pypa/setuptools/issues
                Project-URL: Documentation, https://setuptools.readthedocs.io/
                Project-URL: Funding, https://donate.pypi.org
                Requires-Dist: pywin32 (>1.0); sys.platform == 'win32'
                Obsoletes-Dist: pywin31; sys.platform == 'win32'
                Requires-Dist: foo (1,!=1.3); platform.machine == 'i386'
                Requires-Dist: bar; python_version == '2.4' or python_version == '2.5'
                Requires-Dist: baz (>=1,!=1.3); platform.machine == 'i386'
                Requires-External: libxslt; 'linux' in sys.platform
                Provides-Extra: docs
                Description-Content-Type: text/x-rst; charset=UTF-8
            """,  # based on PEP 345 / PEP 566
        },
        "2022-01-16": {
            "has_dynamic_fields": True,
            "is_final_metadata": False,
            "file_contents": """\
                Metadata-Version: 2.2
                Name: BeagleVote
                Version: 1.0a2
                Platform: ObscureUnix
                Platform: RareDOS
                Supported-Platform: RedHat 7.2
                Supported-Platform: i386-win32-2791
                Keywords: dog,puppy,voting,election
                Description-Content-Type: text/markdown; charset=UTF-8; variant=GFM
                Author-email: cschuoltz@example.com, snoopy@peanuts.com
                License: GPL version 3, excluding DRM provisions
                Requires-Dist: pkginfo
                Requires-Dist: PasteDeploy
                Requires-Dist: zope.interface (>3.5.0)
                Requires-Dist: pywin32 >1.0; sys_platform == 'win32'
                Requires-Python: >2.6,!=3.0.*,!=3.1.*
                Requires-External: C
                Requires-External: libpng (>=1.5)
                Requires-External: make; sys_platform != "win32"
                Project-URL: Bug Tracker, http://bitbucket.org/tarek/distribute/issues/
                Provides-Extra: pdf
                Requires-Dist: reportlab; extra == 'pdf'
                Provides-Dist: OtherProject
                Provides-Dist: AnotherProject (3.4)
                Provides-Dist: virtual_package; python_version >= "3.4"
                Obsoletes-Dist: Foo; os_name == "posix"
                Dynamic: Maintainer
                Dynamic: Maintainer-email

                This project provides powerful math functions
                For example, you can use `sum()` to sum numbers:

                Example::

                    >>> sum(1, 2)
                    3

            """,  # https://packaging.python.org/en/latest/specifications/core-metadata
        },
    }

    @pytest.mark.parametrize("spec", PER_VERSION_EXAMPLES.keys())
    def test_parsing(self, spec: str) -> None:
        example = self.PER_VERSION_EXAMPLES[spec]
        text = bytes(dedent(example["file_contents"]), "UTF-8")
        pkg_info = CoreMetadata.from_pkg_info(text)
        if example["is_final_metadata"]:
            metadata = CoreMetadata.from_dist_info_metadata(text)
            assert metadata == pkg_info
        if example["has_dynamic_fields"]:
            with pytest.raises(DynamicNotAllowed):
                CoreMetadata.from_dist_info_metadata(text)
        for field in ("requires_dist", "provides_dist", "obsoletes_dist"):
            for value in getattr(pkg_info, field):
                assert isinstance(value, Requirement)
        desc = pkg_info.description.splitlines()
        for line in desc:
            assert not line.strip().startswith("|")

    @pytest.mark.parametrize("spec", PER_VERSION_EXAMPLES.keys())
    def test_serliazing(self, spec: str) -> None:
        example = self.PER_VERSION_EXAMPLES[spec]
        text = bytes(dedent(example["file_contents"]), "UTF-8")
        pkg_info = CoreMetadata.from_pkg_info(text)
        if example["is_final_metadata"]:
            assert isinstance(pkg_info.to_dist_info_metadata(), bytes)
        if example["has_dynamic_fields"]:
            with pytest.raises(DynamicNotAllowed):
                pkg_info.to_dist_info_metadata()
        pkg_info_text = pkg_info.to_pkg_info()
        assert isinstance(pkg_info_text, bytes)
        # Make sure generated document is not empty
        assert len(pkg_info_text.strip()) > 0
        assert b"Name" in pkg_info_text
        assert b"Metadata-Version" in pkg_info_text
        # Make sure email-specific headers don't leak into the generated document
        assert b"Content-Transfer-Encoding" not in pkg_info_text
        assert b"MIME-Version" not in pkg_info_text

    def test_missing_required_fields(self):
        with pytest.raises(MissingRequiredFields):
            CoreMetadata.from_dist_info_metadata(b"")

        example = {"name": "pkg", "requires_dist": ["appdirs>1.2"]}
        metadata = CoreMetadata(**example)
        serialized = metadata.to_pkg_info()
        with pytest.raises(MissingRequiredFields):
            CoreMetadata.from_dist_info_metadata(serialized)

    def test_empty_fields(self):
        metadata = CoreMetadata.from_pkg_info(b"Name: pkg\nDescription:\n")
        assert metadata.description == ""
        metadata = CoreMetadata.from_pkg_info(b"Name: pkg\nAuthor-email:\n")
        assert metadata.description == ""
        assert len(metadata.author_email) == 0

    def test_single_line_description(self):
        metadata = CoreMetadata.from_pkg_info(b"Name: pkg\nDescription: Hello World")
        assert metadata.description == "Hello World"

    def test_empty_email(self):
        example = {"name": "pkg", "maintainer_email": ["", "", ("", "")]}
        metadata = CoreMetadata(**example)
        serialized = metadata.to_pkg_info()
        assert b"Maintainer-email:" not in serialized


# --- Integration Tests ---


def examples() -> List[List[str]]:
    lines = EXAMPLES.read_text().splitlines()
    return [[v.strip() for v in line.split(",")] for line in lines]


class TestIntegration:
    @pytest.mark.parametrize("pkg, version", examples())
    def test_parse(self, pkg: str, version: str) -> None:
        for dist in download_dists(pkg, version):
            if dist.suffix == ".whl":
                orig = read_metadata(dist)
                from_ = CoreMetadata.from_dist_info_metadata
                to_ = CoreMetadata.to_dist_info_metadata
            else:
                orig = read_pkg_info(dist)
                from_ = CoreMetadata.from_pkg_info
                to_ = CoreMetadata.to_pkg_info

            # Given PKG-INFO or METADATA from existing packages on PyPI
            # - Make sure they can be parsed
            metadata = from_(orig)
            assert metadata.name.lower() == pkg.lower()
            assert str(metadata.version) == version
            # - Make sure they can be converted back into PKG-INFO or METADATA
            recons_file = to_(metadata)
            assert len(recons_file) >= 0
            # - Make sure that the reconstructed file can be parsed and the data
            #   remains unchanged
            recons_data = from_(recons_file)
            description = metadata.description.replace("\r\n", "\n")
            metadata = dataclasses.replace(metadata, description=description)
            assert metadata == recons_data
            # - Make sure the reconstructed file can be parsed with compat32
            attrs = dataclasses.asdict(_Compat32Metadata.from_pkg_info(recons_file))
            assert CoreMetadata(**attrs)
            # - Make sure that successive calls to `to_...` and `from_...`
            #   always return the same result
            file_contents = recons_file
            data = recons_data
            for _ in range(3):
                result_contents = to_(data)
                assert file_contents == result_contents
                result_data = from_(result_contents)
                assert data == result_data
                file_contents, data = result_contents, result_data


# --- Helper Functions/Classes ---


class _Compat32Metadata(CoreMetadata):
    """The Core Metadata spec requires the file to be parse-able with compat32.
    The implementation uses a different approach to ensure UTF-8 can be used.
    Therefore it is important to test against compat32 to make sure nothing
    goes wrong.
    """

    _PARSING_POLICY = compat32


def download(url: str, dest: Path, md5_digest: str) -> Path:
    with urlopen(url) as f:
        data = f.read()

    assert md5(data).hexdigest() == md5_digest

    with open(dest, "wb") as f:
        f.write(data)

    assert dest.exists()

    return dest


def download_dists(pkg: str, version: str) -> List[Path]:
    """Either use cached dist file or download it from PyPI"""
    DOWNLOADS.mkdir(exist_ok=True)

    distributions = retrieve_pypi_dist_metadata(pkg, version)
    filenames = {dist["filename"] for dist in distributions}

    # Remove old files to prevent cache to grow indefinitely
    canonical = canonicalize_name(pkg)
    names = [pkg, canonical, canonical.replace("-", "_")]
    for file in chain.from_iterable(DOWNLOADS.glob(f"{n}*") for n in names):
        if file.name not in filenames:
            file.unlink()

    dist_files = []
    for dist in retrieve_pypi_dist_metadata(pkg, version):
        dest = DOWNLOADS / dist["filename"]
        if not dest.exists():
            download(dist["url"], dest, dist["md5_digest"])
        dist_files.append(dest)

    return dist_files


def retrieve_pypi_dist_metadata(package: str, version: str) -> Iterator[dict]:
    # https://warehouse.pypa.io/api-reference/json.html
    id_ = f"{package}/{version}"
    with urlopen(f"https://pypi.org/pypi/{id_}/json") as f:
        metadata = json.load(f)

    if metadata["info"]["yanked"]:
        raise ValueError(f"Release for {package} {version} was yanked")

    version = metadata["info"]["version"]
    for dist in metadata["releases"][version]:
        if any(dist["filename"].endswith(ext) for ext in (".tar.gz", ".whl")):
            yield dist


def read_metadata(wheel: Path) -> bytes:
    with ZipFile(wheel, "r") as zipfile:
        for member in zipfile.namelist():
            if member.endswith(".dist-info/METADATA"):
                return zipfile.read(member)
    raise FileNotFoundError(f"METADATA not found in {wheel}")


def read_pkg_info(sdist: Path) -> bytes:
    with tarfile.open(sdist, mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.name.endswith("PKG-INFO"):
                file = tar.extractfile(member)
                if file is not None:
                    return file.read()
    raise FileNotFoundError(f"PKG-INFO not found in {sdist}")
