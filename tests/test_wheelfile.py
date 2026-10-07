from __future__ import annotations

import os.path
import re
import stat
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePath
from textwrap import dedent
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from packaging.utils import InvalidWheelFilename
from packaging.wheelfile import (
    WheelArchiveFile,
    WheelError,
    WheelMetadata,
    WheelReader,
    WheelWriter,
    _encode_hash_value,
)


@pytest.fixture
def wheel_path(tmp_path: Path) -> Path:
    return tmp_path / "test-1.0-py2.py3-none-any.whl"


def read_fully(f: WheelArchiveFile, amount: int) -> None:
    while f.read(amount):
        pass


@pytest.fixture(scope="module")
def valid_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("reader") / "test-1.0-py2.py3-none-any.whl"
    with ZipFile(path, "w") as zf:
        zf.writestr("hello/héllö.py", 'print("Héllö, world!")\n')
        zf.writestr(
            "test-1.0.dist-info/RECORD",
            "hello/héllö.py,sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25",
        )

    return path


class TestWheelReader:
    def test_properties(self, valid_wheel: Path) -> None:
        with WheelReader(valid_wheel) as reader:
            assert reader.dist_info_dir == "test-1.0.dist-info"
            assert reader.data_dir == "test-1.0.data"
            assert reader.dist_info_filenames == [PurePath("test-1.0.dist-info/RECORD")]

    def test_bad_wheel_filename(self) -> None:
        with pytest.raises(WheelError, match="Invalid wheel filename"):
            WheelReader("badname")

    def test_str_filename(self, valid_wheel: Path) -> None:
        reader = WheelReader(str(valid_wheel))
        assert reader.path_or_fd == str(valid_wheel)

    def test_pathlike_filename(self, valid_wheel: Path) -> None:
        class Foo:
            def __fspath__(self) -> str:
                return str(valid_wheel)

        foo = Foo()
        with WheelReader(foo) as reader:
            assert reader.path_or_fd is foo

    def test_pass_open_file(self, valid_wheel: Path) -> None:
        with valid_wheel.open("rb") as fp, WheelReader(fp) as reader:
            assert reader.path_or_fd is fp

    def test_missing_record(self, wheel_path: Path) -> None:
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')

        with (
            pytest.raises(
                WheelError,
                match=(
                    r"^Cannot find a valid .dist-info directory. Is this really "
                    r"a wheel file\?$"
                ),
            ),
            WheelReader(wheel_path),
        ):
            pass

    @pytest.mark.parametrize(
        "record",
        [
            pytest.param("onlyonecolumn\n", id="too-few-columns"),
            pytest.param("a,b,c,d\n", id="too-many-columns"),
            pytest.param("m.txt,sha256=ab=cd,4\n", id="malformed-hash"),
        ],
    )
    def test_malformed_record(self, wheel_path: Path, record: str) -> None:
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("test-1.0.dist-info/RECORD", record)

        with (
            pytest.raises(WheelError, match=r"^Invalid RECORD"),
            WheelReader(wheel_path),
        ):
            pass

    def test_unsupported_hash_algorithm(self, wheel_path: Path) -> None:
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')
            zf.writestr(
                "test-1.0.dist-info/RECORD",
                "hello/héllö.py,sha000=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25",
            )

        with (
            pytest.raises(WheelError, match=r"^Unsupported hash algorithm: sha000$"),
            WheelReader(wheel_path),
        ):
            pass

    @pytest.mark.parametrize(
        ("algorithm", "digest"),
        [
            pytest.param("md5", "4J-scNa2qvSgy07rS4at-Q", id="md5"),
            pytest.param("sha1", "QjCnGu5Qucb6-vir1a6BVptvOA4", id="sha1"),
        ],
    )
    def test_weak_hash_algorithm(
        self, wheel_path: Path, algorithm: str, digest: str
    ) -> None:
        hash_string = f"{algorithm}={digest}"
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')
            zf.writestr("test-1.0.dist-info/RECORD", f"hello/héllö.py,{hash_string},25")

        with (
            pytest.raises(
                WheelError,
                match=(
                    rf"^Weak hash algorithm \({algorithm}\) is not permitted "
                    r"by PEP 427$"
                ),
            ),
            WheelReader(wheel_path),
        ):
            pass

    @pytest.mark.parametrize(
        ("algorithm", "digest"),
        [
            ("sha256", "bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo"),
            (
                "sha384",
                "cDXriAy_7i02kBeDkN0m2RIDz85w6pwuHkt2PZ4VmT2PQc1TZs8Ebvf6eKDFcD_S",
            ),
            (
                "sha512",
                "kdX9CQlwNt4FfOpOKO_X0pn_v1opQuksE40SrWtMyP1NqooWVWpzCE3myZTfpy8g2azZON_"
                "iLNpWVxTwuDWqBQ",
            ),
        ],
        ids=["sha256", "sha384", "sha512"],
    )
    def test_validate_record(
        self, wheel_path: Path, algorithm: str, digest: str
    ) -> None:
        hash_string = f"{algorithm}={digest}"
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("hello/héllö.py", 'print("Héllö, world!")\n')
            zf.writestr("test-1.0.dist-info/RECORD", f"hello/héllö.py,{hash_string},25")

        with WheelReader(wheel_path) as wf:
            wf.validate_record()

    def test_validate_record_missing_hash(self, wheel_path: Path) -> None:
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("hello/héllö.py", 'print("Héllö, world!")\n')
            zf.writestr("test-1.0.dist-info/RECORD", "")

        with WheelReader(wheel_path) as wf:
            with pytest.raises(WheelError) as exc:
                wf.validate_record()
            exc.match("^No hash found for file 'hello/héllö.py'$")

    def test_validate_record_bad_hash(self, wheel_path: Path) -> None:
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')
            zf.writestr(
                "test-1.0.dist-info/RECORD",
                "hello/héllö.py,sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25",
            )

        with WheelReader(wheel_path) as wf:
            with pytest.raises(WheelError) as exc:
                wf.validate_record()
            exc.match(
                "hello/héllö.py: hash mismatch: "
                "6eff9057745c8900b6bf7ccbf14be177f6aba78d09e40f719b2b9b377e0e570a in "
                "RECORD, "
                "1eac82375d38fdb8a4c653c6c2b3c363058d5c193cf24bafcd1df040d344597e in "
                "archive$"
            )

    def test_unnormalized_wheel(self, tmp_path: Path) -> None:
        # Previous versions of "wheel" did not correctly normalize the names; test that
        # we can still read such wheels
        wheel_path = tmp_path / "Test_foo_bar-1.0.0-py3-none-any.whl"
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr(
                "Test_foo_bar-1.0.0.dist-info/RECORD",
                "Test_foo_bar-1.0.0.dist-info/RECORD,,\n",
            )

        with WheelReader(wheel_path) as wf:
            assert wf.name == "test-foo-bar"
            assert wf.dist_info_dir == "Test_foo_bar-1.0.0.dist-info"

    def test_hyphenated_name_uses_expected_dist_info_dir(self, tmp_path: Path) -> None:
        # The .dist-info directory uses the underscore form of the name, so it must
        # be found directly instead of via the fallback scan (which would pick the
        # decoy written last).
        wheel_path = tmp_path / "foo_bar-1.0-py3-none-any.whl"
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr(
                "foo_bar-1.0.dist-info/RECORD", "foo_bar-1.0.dist-info/RECORD,,\n"
            )
            zf.writestr("zzz-9.dist-info/RECORD", "zzz-9.dist-info/RECORD,,\n")

        with WheelReader(wheel_path) as wf:
            assert wf.name == "foo-bar"
            assert wf.dist_info_dir == "foo_bar-1.0.dist-info"
            assert wf.data_dir == "foo_bar-1.0.data"

    def test_read_file(self, valid_wheel: Path) -> None:
        with WheelReader(valid_wheel) as wf:
            contents = wf.read_file("hello/héllö.py")

        assert contents == b'print("H\xc3\xa9ll\xc3\xb6, world!")\n'

    @pytest.mark.parametrize(
        "amount",
        [
            pytest.param(-1, id="oneshot"),
            pytest.param(2, id="gradual"),
        ],
    )
    def test_read_file_bad_hash(self, wheel_path: Path, amount: int) -> None:
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')
            zf.writestr(
                "test-1.0.dist-info/RECORD",
                "hello/héllö.py,sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25",
            )

        with WheelReader(wheel_path) as wf, wf.open("hello/héllö.py") as f:
            assert repr(f) == "WheelArchiveFile('hello/héllö.py')"
            expected = (
                r"^hello/héllö\.py: hash mismatch: "
                r"6eff9057745c8900b6bf7ccbf14be177f6aba78d09e40f719b2b9b377e0e570a"
                r" in RECORD, "
                r"1eac82375d38fdb8a4c653c6c2b3c363058d5c193cf24bafcd1df040d344597e"
                r" in archive$"
            )
            with pytest.raises(WheelError, match=expected):
                read_fully(f, amount)

    @pytest.mark.parametrize(
        "amount",
        [
            pytest.param(-1, id="oneshot"),
            pytest.param(2, id="gradual"),
        ],
    )
    def test_read_file_bad_size(self, wheel_path: Path, amount: int) -> None:
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')
            zf.writestr(
                "test-1.0.dist-info/RECORD",
                "hello/héllö.py,sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,24",
            )

        with WheelReader(wheel_path) as wf, wf.open("hello/héllö.py") as f:
            expected = (
                r"^hello/héllö\.py: file size mismatch: 24 bytes in RECORD, "
                r"25 bytes in archive$"
            )
            with pytest.raises(WheelError, match=expected):
                read_fully(f, amount)

    def test_read_data_file(self, wheel_path: Path) -> None:
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("test-1.0.data/héllö.py", 'print("Héllö, world!")\n')
            zf.writestr(
                "test-1.0.dist-info/RECORD",
                "test-1.0.data/héllö.py,"
                "sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25",
            )

        with WheelReader(wheel_path) as wf:
            contents = wf.read_data_file("héllö.py")

        assert contents == b'print("H\xc3\xa9ll\xc3\xb6, world!")\n'

    def test_read_distinfo_file(self, valid_wheel: Path) -> None:
        with WheelReader(valid_wheel) as wf:
            contents = wf.read_distinfo_file("RECORD")

        assert (
            contents == b"hello/h\xc3\xa9ll\xc3\xb6.py,"
            b"sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25"
        )

    def test_iterate_contents(self, valid_wheel: Path) -> None:
        with WheelReader(valid_wheel) as wf:
            for element in wf.iterate_contents():
                assert element.path == PurePath("hello", "héllö.py")
                assert element.size == 25
                assert (
                    element.hash_value.hex()
                    == "6eff9057745c8900b6bf7ccbf14be177f6aba78d09e40f719b2b9b377e0e570"
                    "a"
                )
                assert (
                    element.stream.read() == b'print("H\xc3\xa9ll\xc3\xb6, world!")\n'
                )
                assert repr(element) == "WheelContentElement('hello/héllö.py', size=25)"

    def test_extractall(
        self, valid_wheel: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        dest_dir = tmp_path_factory.mktemp("wheel_contents")
        with WheelReader(valid_wheel) as wf:
            wf.extractall(dest_dir)

        iterator = os.walk(dest_dir)
        dirpath, dirnames, filenames = next(iterator)
        dirnames.sort()
        assert dirnames == ["hello", "test-1.0.dist-info"]
        assert not filenames

        dirpath, dirnames, filenames = next(iterator)
        assert dirpath.endswith("hello")
        assert filenames == ["héllö.py"]
        assert (
            Path(dirpath).joinpath(filenames[0]).read_text(encoding="utf-8")
            == 'print("Héllö, world!")\n'
        )

        dirpath, dirnames, filenames = next(iterator)
        assert dirpath.endswith("test-1.0.dist-info")
        assert filenames == ["RECORD"]
        assert Path(dirpath).joinpath(filenames[0]).read_text(encoding="utf-8") == (
            "hello/héllö.py,sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25"
        )

    @pytest.mark.parametrize(
        "arcname",
        [
            pytest.param("../evil.txt", id="parent"),
            pytest.param("sub/../../evil.txt", id="nested-parent"),
        ],
    )
    def test_extractall_rejects_escaping_paths(
        self, wheel_path: Path, tmp_path_factory: pytest.TempPathFactory, arcname: str
    ) -> None:
        payload = b"pwned\n"
        digest = _encode_hash_value(sha256(payload).digest())
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr(arcname, payload)
            zf.writestr(
                "test-1.0.dist-info/RECORD",
                f"{arcname},sha256={digest},{len(payload)}\n",
            )

        dest_dir = tmp_path_factory.mktemp("extract")
        with (
            WheelReader(wheel_path) as wf,
            pytest.raises(WheelError, match="escapes the destination directory"),
        ):
            wf.extractall(dest_dir)

        assert not (dest_dir.parent / "evil.txt").exists()

    def test_dist_info_dir_without_name_version(self, wheel_path: Path) -> None:
        # A .dist-info directory whose stem has no name-version split cannot be
        # used, so scanning falls through to the "not a wheel" error.
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("noversion.dist-info/RECORD", "")

        with (
            pytest.raises(WheelError, match=r"^Cannot find a valid .dist-info"),
            WheelReader(wheel_path),
        ):
            pass

    def test_filenames(self, valid_wheel: Path) -> None:
        with WheelReader(valid_wheel) as wf:
            assert set(wf.filenames) == {
                PurePath("hello/héllö.py"),
                PurePath("test-1.0.dist-info/RECORD"),
            }

    def test_read_dist_info_missing(self, valid_wheel: Path) -> None:
        with (
            WheelReader(valid_wheel) as wf,
            pytest.raises(WheelError, match=r"not found$"),
        ):
            wf.read_dist_info("NONEXISTENT")

    def test_extractall_dest_missing(self, valid_wheel: Path, tmp_path: Path) -> None:
        dest = tmp_path / "nope"
        with (
            WheelReader(valid_wheel) as wf,
            pytest.raises(WheelError, match="does not exist"),
        ):
            wf.extractall(dest)

    def test_extractall_dest_not_dir(self, valid_wheel: Path, tmp_path: Path) -> None:
        dest = tmp_path / "file"
        dest.touch()
        with (
            WheelReader(valid_wheel) as wf,
            pytest.raises(WheelError, match="is not a directory"),
        ):
            wf.extractall(dest)

    def test_repr(self, valid_wheel: Path) -> None:
        with WheelReader(valid_wheel) as wf:
            assert repr(wf) == f"WheelReader({valid_wheel})"


class TestWheelWriter:
    @pytest.mark.parametrize(
        ("filename", "reason"),
        [
            pytest.param("test.whl", "wrong number of parts"),
            pytest.param("test-1.0.whl", "wrong number of parts"),
            pytest.param("test-1.0-py2.whl", "wrong number of parts"),
            pytest.param("test-1.0-py2-none.whl", "wrong number of parts"),
            pytest.param("test-1.0-py2-none-any", "extension must be '.whl'"),
            pytest.param(
                "test-1.0-py 2-none-any.whl",
                "bad file name",
                marks=[
                    pytest.mark.xfail(
                        reason="parse_wheel_filename() does not fail this yet"
                    )
                ],
            ),
        ],
    )
    def test_bad_wheel_filename(self, filename: str, reason: str) -> None:
        basename = (
            os.path.splitext(filename)[0] if filename.endswith(".whl") else filename
        )
        with pytest.raises(
            InvalidWheelFilename,
            match=rf"^Invalid wheel filename \({reason}\): {basename!r}$",
        ):
            WheelWriter(filename, generator="foo")

    def test_unavailable_hash_algorithm(self, wheel_path: Path) -> None:
        with pytest.raises(
            ValueError,
            match=r"^Hash algorithm 'sha000' is not available$",
        ):
            WheelWriter(wheel_path, generator="generator 1.0", hash_algorithm="sha000")

    @pytest.mark.parametrize(
        "algorithm",
        [
            pytest.param("md5"),
            pytest.param("sha1"),
        ],
    )
    def test_weak_hash_algorithm(self, wheel_path: Path, algorithm: str) -> None:
        with pytest.raises(
            ValueError,
            match=rf"^Weak hash algorithm \({algorithm}\) is not permitted by PEP 427$",
        ):
            WheelWriter(wheel_path, generator="generator 1.0", hash_algorithm=algorithm)

    def test_write_files(self, wheel_path: Path) -> None:
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_file("hello/héllö.py", 'print("Héllö, world!")\n')
            wf.write_file("hello/h,ll,.py", 'print("Héllö, world!")\n')
            wf.write_data_file("mydata.txt", "Dummy")
            wf.write_distinfo_file("LICENSE.txt", "License text")

        with ZipFile(wheel_path, "r") as zf:
            infolist = zf.infolist()
            assert len(infolist) == 6
            assert infolist[0].filename == "hello/héllö.py"
            assert infolist[0].file_size == 25
            assert infolist[1].filename == "hello/h,ll,.py"
            assert infolist[1].file_size == 25
            assert infolist[2].filename == "test-1.0.data/mydata.txt"
            assert infolist[2].file_size == 5
            assert infolist[3].filename == "test-1.0.dist-info/LICENSE.txt"
            assert infolist[4].filename == "test-1.0.dist-info/WHEEL"
            assert infolist[5].filename == "test-1.0.dist-info/RECORD"

            record = zf.read("test-1.0.dist-info/RECORD")
            assert record.decode("utf-8") == (
                "hello/héllö.py,sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25\n"
                '"hello/h,ll,.py",sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,'
                "25\n"
                "test-1.0.data/mydata.txt,"
                "sha256=0mB6s81UJCwa14-jUFK6fIqv1PR4FQPyJ0wxBjqF9WA,5\n"
                "test-1.0.dist-info/LICENSE.txt,"
                "sha256=Bk_bWStYk3YYSmcUeZRgnr3cqIs1oJW485Zb_XBvOgM,12\n"
                "test-1.0.dist-info/WHEEL,"
                "sha256=KzXSdMADLwiK8h1P5UAQ76v3nVuO2ZRU8e9GCHCC6Qs,103\n"
                "test-1.0.dist-info/RECORD,,\n"
            )

    def test_write_metadata(self, wheel_path: Path) -> None:
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_metadata(
                [
                    ("Foo", "Bar"),
                    ("Description", "Long description\nspanning\nthree rows"),
                ]
            )

        with ZipFile(wheel_path, "r") as zf:
            infolist = zf.infolist()
            assert len(infolist) == 3
            assert infolist[0].filename == "test-1.0.dist-info/METADATA"
            assert infolist[1].filename == "test-1.0.dist-info/WHEEL"
            assert infolist[2].filename == "test-1.0.dist-info/RECORD"

            metadata = zf.read("test-1.0.dist-info/METADATA")
            assert metadata.decode("utf-8") == dedent(
                """\
                Foo: Bar
                Metadata-Version: 2.3
                Name: test
                Version: 1.0

                Long description
                spanning
                three rows"""
            )

    def test_timestamp(
        self,
        tmp_path_factory: pytest.TempPathFactory,
        wheel_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # An environment variable can be used to influence the timestamp on
        # TarInfo objects inside the zip.  See issue #143.
        build_dir = tmp_path_factory.mktemp("build")
        for filename in ("one", "two", "three"):
            build_dir.joinpath(filename).write_text(filename + "\n")

        # The earliest date representable in TarInfos, 1980-01-01
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "315576060")

        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_files_from_directory(build_dir)

        with ZipFile(wheel_path, "r") as zf:
            for info in zf.infolist():
                assert info.date_time == (1980, 1, 1, 0, 0, 0)
                assert info.compress_type == ZIP_DEFLATED

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows does not support UNIX-like permissions"
    )
    def test_attributes(
        self, tmp_path_factory: pytest.TempPathFactory, wheel_path: Path
    ) -> None:
        # With the change from ZipFile.write() to .writestr(), we need to manually
        # set member attributes.
        build_dir = tmp_path_factory.mktemp("build")
        files = (("foo", 0o644), ("bar", 0o755))
        for filename, mode in files:
            path = build_dir / filename
            path.write_text(filename + "\n")
            path.chmod(mode)

        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_files_from_directory(build_dir)

        with ZipFile(wheel_path, "r") as zf:
            for filename, mode in files:
                info = zf.getinfo(filename)
                assert info.external_attr == (mode | 0o100000) << 16
                assert info.compress_type == ZIP_DEFLATED

            info = zf.getinfo("test-1.0.dist-info/RECORD")
            permissions = (info.external_attr >> 16) & 0o777
            assert permissions == 0o664

    def test_write_file_from_bytesio(self, wheel_path: Path) -> None:
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            buffer = BytesIO(b"test content")
            wf.write_file("test", buffer)

        with ZipFile(wheel_path, "r") as zf:
            assert zf.open("test", "r").read() == b"test content"

    def test_write_files_from_dir_source_nonexistent(
        self, wheel_path: Path, tmp_path: Path
    ) -> None:
        source_dir = tmp_path / "nonexistent"
        with (
            WheelWriter(wheel_path, generator="generator 1.0") as wf,
            pytest.raises(WheelError, match=re.escape(f"{source_dir} does not exist")),
        ):
            wf.write_files_from_directory(source_dir)

    def test_write_files_from_dir_source_not_dir(
        self, wheel_path: Path, tmp_path: Path
    ) -> None:
        source_dir = tmp_path / "file"
        source_dir.touch()
        with (
            WheelWriter(wheel_path, generator="generator 1.0") as wf,
            pytest.raises(
                WheelError, match=re.escape(f"{source_dir} is not a directory")
            ),
        ):
            wf.write_files_from_directory(source_dir)

    def test_repr(self, wheel_path: Path) -> None:
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            assert repr(wf) == f"WheelWriter({wheel_path}, generator='generator 1.0')"

    def test_explicit_metadata_with_build_tag(self, wheel_path: Path) -> None:
        metadata = WheelMetadata.from_filename("test-1.0-3-py2.py3-none-any.whl")
        with WheelWriter(
            wheel_path, generator="generator 1.0", metadata=metadata
        ) as wf:
            wf.write_file("hello.py", "x = 1\n")

        with ZipFile(wheel_path, "r") as zf:
            wheel = zf.read("test-1.0.dist-info/WHEEL").decode("utf-8")

        assert "Build: 3" in wheel

    def test_no_path_requires_metadata(self) -> None:
        with pytest.raises(WheelError, match="path_or_fd is not a path"):
            WheelWriter(BytesIO(), generator="generator 1.0")

    def test_exception_skips_record(self) -> None:
        # A file object is left as is (minus RECORD), as it cannot be removed.
        buffer = BytesIO()
        metadata = WheelMetadata.from_filename("test-1.0-py2.py3-none-any.whl")

        def build_and_fail() -> None:
            with WheelWriter(
                buffer, generator="generator 1.0", metadata=metadata
            ) as wf:
                wf.write_file("hello.py", "x = 1\n")
                raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            build_and_fail()

        with ZipFile(buffer, "r") as zf:
            assert zf.namelist() == ["hello.py"]

    def test_manual_wheel_file_kept(self, wheel_path: Path) -> None:
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_distinfo_file("WHEEL", "Wheel-Version: 1.0\n")

        with ZipFile(wheel_path, "r") as zf:
            wheel = zf.read("test-1.0.dist-info/WHEEL").decode("utf-8")

        assert wheel == "Wheel-Version: 1.0\n"

    def test_write_metadata_keeps_provided_headers(self, wheel_path: Path) -> None:
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_metadata(
                [
                    ("Metadata-Version", "2.1"),
                    ("Name", "othername"),
                    ("Version", "9.9"),
                ]
            )

        with ZipFile(wheel_path, "r") as zf:
            metadata = zf.read("test-1.0.dist-info/METADATA").decode("utf-8")

        assert "Metadata-Version: 2.1" in metadata
        assert "Name: othername" in metadata
        assert "Version: 9.9" in metadata

    def test_write_files_from_directory_skips_record(
        self, wheel_path: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        build_dir = tmp_path_factory.mktemp("build")
        build_dir.joinpath("test-1.0.dist-info").mkdir()
        build_dir.joinpath("test-1.0.dist-info", "RECORD").write_text("stale\n")
        build_dir.joinpath("hello.py").write_text("x = 1\n")

        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_files_from_directory(build_dir)

        with ZipFile(wheel_path, "r") as zf:
            record = zf.read("test-1.0.dist-info/RECORD").decode("utf-8")

        assert "stale" not in record
        assert "hello.py" in record

    def test_hyphenated_name_dist_info_dir(self, tmp_path: Path) -> None:
        wheel_path = tmp_path / "foo_bar-1.0-py3-none-any.whl"
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_data_file("scripts/tool", b"")

        with ZipFile(wheel_path, "r") as zf:
            assert zf.namelist() == [
                "foo_bar-1.0.data/scripts/tool",
                "foo_bar-1.0.dist-info/WHEEL",
                "foo_bar-1.0.dist-info/RECORD",
            ]

    def test_bytes_member_is_regular_file(self, wheel_path: Path) -> None:
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_file("test", b"test content")

        with ZipFile(wheel_path, "r") as zf:
            for info in zf.infolist():
                assert info.external_attr == (0o664 | stat.S_IFREG) << 16

    def test_stream_size_counts_bytes_read(self, wheel_path: Path) -> None:
        buffer = BytesIO(b"0123456789")
        buffer.read(5)
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_file("test", buffer)

        with ZipFile(wheel_path, "r") as zf:
            record = zf.read("test-1.0.dist-info/RECORD").decode("utf-8")

        assert record.splitlines()[0].endswith(",5")

    def test_write_files_from_directory_sorted(
        self, wheel_path: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        build_dir = tmp_path_factory.mktemp("build")
        for name in ("z.py", "b/x.py", "a.py", "b/a.py", "c/y.py"):
            path = build_dir / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(name)

        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_files_from_directory(build_dir)

        with ZipFile(wheel_path, "r") as zf:
            names = zf.namelist()[:5]

        assert names == ["a.py", "z.py", "b/a.py", "b/x.py", "c/y.py"]

    def test_exception_removes_partial_wheel(self, wheel_path: Path) -> None:
        def build_and_fail() -> None:
            with WheelWriter(wheel_path, generator="generator 1.0") as wf:
                wf.write_file("test", b"test content")
                raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            build_and_fail()

        assert not wheel_path.exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="time.tzset is POSIX only")
    def test_naive_timestamp_is_utc(
        self, wheel_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TZ", "America/New_York")
        time.tzset()
        try:
            with WheelWriter(wheel_path, generator="generator 1.0") as wf:
                wf.write_file(
                    "test",
                    b"x",
                    timestamp=datetime(2020, 1, 2, 12, 30),  # noqa: DTZ001
                )
        finally:
            monkeypatch.undo()
            time.tzset()

        with ZipFile(wheel_path, "r") as zf:
            assert zf.getinfo("test").date_time == (2020, 1, 2, 12, 30, 0)

    @pytest.mark.parametrize(
        ("timestamp", "expected"),
        [
            pytest.param(
                datetime(1970, 1, 1, tzinfo=timezone.utc),
                (1980, 1, 1, 0, 0, 0),
                id="too-early",
            ),
            pytest.param(
                datetime(2200, 1, 1, tzinfo=timezone.utc),
                (2107, 12, 31, 23, 59, 58),
                id="too-late",
            ),
        ],
    )
    def test_timestamp_clamped_to_zip_range(
        self,
        wheel_path: Path,
        timestamp: datetime,
        expected: tuple[int, int, int, int, int, int],
    ) -> None:
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_file("test", b"x", timestamp=timestamp)

        with ZipFile(wheel_path, "r") as zf:
            assert zf.getinfo("test").date_time == expected

    def test_backslash_arcname_normalized(self, wheel_path: Path) -> None:
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_file("pkg\\mod.py", b"x")

        with ZipFile(wheel_path, "r") as zf:
            assert zf.namelist()[0] == "pkg/mod.py"
            record = zf.read("test-1.0.dist-info/RECORD").decode("utf-8")

        assert record.startswith("pkg/mod.py,")

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows does not support UNIX-like permissions"
    )
    def test_write_file_mode(self, wheel_path: Path, tmp_path: Path) -> None:
        source = tmp_path / "source"
        source.write_text("x")
        source.chmod(0o600)
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            wf.write_file("from_bytes", b"x", mode=0o755)
            wf.write_file("from_path", source, mode=0o644)
            wf.write_file("from_path_default", source)
            wf.write_data_file("scripts/tool", b"x", mode=0o755)
            wf.write_distinfo_file("extra", b"x", mode=0o600)

        with ZipFile(wheel_path, "r") as zf:
            modes = {info.filename: info.external_attr >> 16 for info in zf.infolist()}

        assert modes["from_bytes"] == 0o755 | stat.S_IFREG
        assert modes["from_path"] == 0o644 | stat.S_IFREG
        assert modes["from_path_default"] == 0o600 | stat.S_IFREG
        assert modes["test-1.0.data/scripts/tool"] == 0o755 | stat.S_IFREG
        assert modes["test-1.0.dist-info/extra"] == 0o600 | stat.S_IFREG

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows does not support UNIX-like permissions"
    )
    def test_writer_defaults_apply_to_generated_files(
        self, wheel_path: Path, tmp_path: Path
    ) -> None:
        source = tmp_path / "source"
        source.write_text("x")
        source.chmod(0o600)
        timestamp = datetime(2020, 1, 2, 12, 30, tzinfo=timezone.utc)
        with WheelWriter(
            wheel_path, generator="generator 1.0", timestamp=timestamp, mode=0o644
        ) as wf:
            wf.write_file("from_bytes", b"x")
            wf.write_file("from_path", source)
            wf.write_file(
                "explicit",
                b"x",
                timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
                mode=0o755,
            )

        with ZipFile(wheel_path, "r") as zf:
            infos = {info.filename: info for info in zf.infolist()}

        assert set(infos) == {
            "from_bytes",
            "from_path",
            "explicit",
            "test-1.0.dist-info/WHEEL",
            "test-1.0.dist-info/RECORD",
        }
        for name in (
            "from_bytes",
            "test-1.0.dist-info/WHEEL",
            "test-1.0.dist-info/RECORD",
        ):
            assert infos[name].external_attr == (0o644 | stat.S_IFREG) << 16
            assert infos[name].date_time == (2020, 1, 2, 12, 30, 0)

        # A path keeps its own permissions unless a mode is given explicitly.
        assert infos["from_path"].external_attr == (0o600 | stat.S_IFREG) << 16
        assert infos["from_path"].date_time == (2020, 1, 2, 12, 30, 0)
        assert infos["explicit"].external_attr == (0o755 | stat.S_IFREG) << 16
        assert infos["explicit"].date_time == (2021, 1, 1, 0, 0, 0)
