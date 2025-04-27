from __future__ import annotations

import os.path
import sys
from io import BytesIO
from pathlib import Path, PurePath
from textwrap import dedent
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pytest import MonkeyPatch, TempPathFactory

from packaging.utils import InvalidWheelFilename
from packaging.wheelfile import WheelError, WheelReader, WheelWriter


@pytest.fixture
def wheel_path(tmp_path: Path) -> Path:
    return tmp_path / "test-1.0-py2.py3-none-any.whl"


class TestWheelReader:
    @pytest.fixture(scope="class")
    def valid_wheel(self, tmp_path_factory: TempPathFactory) -> Path:
        path = tmp_path_factory.mktemp("reader") / "test-1.0-py2.py3-none-any.whl"
        with ZipFile(path, "w") as zf:
            zf.writestr("hello/héllö.py", 'print("Héllö, world!")\n')
            zf.writestr(
                "test-1.0.dist-info/RECORD",
                "hello/héllö.py,sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25",
            )

        return path

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

        with pytest.raises(
            WheelError,
            match=(
                r"^Cannot find a valid .dist-info directory. Is this really a wheel "
                r"file\?$"
            ),
        ):
            with WheelReader(wheel_path):
                pass

    def test_unsupported_hash_algorithm(self, wheel_path: Path) -> None:
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')
            zf.writestr(
                "test-1.0.dist-info/RECORD",
                "hello/héllö.py,sha000=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25",
            )

        with pytest.raises(WheelError, match="^Unsupported hash algorithm: sha000$"):
            with WheelReader(wheel_path):
                pass

    @pytest.mark.parametrize(
        "algorithm, digest",
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

        with pytest.raises(
            WheelError,
            match=rf"^Weak hash algorithm \({algorithm}\) is not permitted by PEP 427$",
        ):
            with WheelReader(wheel_path):
                pass

    @pytest.mark.parametrize(
        "algorithm, digest",
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
            exc = pytest.raises(WheelError, wf.validate_record)
            exc.match("^No hash found for file 'hello/héllö.py'$")

    def test_validate_record_bad_hash(self, wheel_path: Path) -> None:
        with ZipFile(wheel_path, "w") as zf:
            zf.writestr("hello/héllö.py", 'print("Héllö, w0rld!")\n')
            zf.writestr(
                "test-1.0.dist-info/RECORD",
                "hello/héllö.py,sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25",
            )

        with WheelReader(wheel_path) as wf:
            exc = pytest.raises(WheelError, wf.validate_record)
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

        with WheelReader(wheel_path):
            pass

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

        with pytest.raises(
            WheelError,
            match=(
                "^hello/héllö.py: hash mismatch: "
                "6eff9057745c8900b6bf7ccbf14be177f6aba78d09e40f719b2b9b377e0e570a in "
                "RECORD, "
                "1eac82375d38fdb8a4c653c6c2b3c363058d5c193cf24bafcd1df040d344597e in "
                "archive$"
            ),
        ), WheelReader(wheel_path) as wf, wf.open("hello/héllö.py") as f:
            assert repr(f) == "WheelArchiveFile('hello/héllö.py')"
            while f.read(amount):
                pass

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

        with pytest.raises(
            WheelError,
            match=(
                "^hello/héllö.py: file size mismatch: 24 bytes in RECORD, 25 bytes in "
                "archive$"
            ),
        ), WheelReader(wheel_path) as wf, wf.open("hello/héllö.py") as f:
            while f.read(amount):
                pass

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
        self, valid_wheel: Path, tmp_path_factory: TempPathFactory
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
            Path(dirpath).joinpath(filenames[0]).read_text()
            == 'print("Héllö, world!")\n'
        )

        dirpath, dirnames, filenames = next(iterator)
        assert dirpath.endswith("test-1.0.dist-info")
        assert filenames == ["RECORD"]
        assert Path(dirpath).joinpath(filenames[0]).read_text() == (
            "hello/héllö.py,sha256=bv-QV3RciQC2v3zL8Uvhd_arp40J5A9xmyubN34OVwo,25"
        )


class TestWheelWriter:
    @pytest.mark.parametrize(
        "filename, reason",
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
        tmp_path_factory: TempPathFactory,
        wheel_path: Path,
        monkeypatch: MonkeyPatch,
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
        self, tmp_path_factory: TempPathFactory, wheel_path: Path
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
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            with pytest.raises(WheelError, match=f"{source_dir} does not exist"):
                wf.write_files_from_directory(source_dir)

    def test_write_files_from_dir_source_not_dir(
        self, wheel_path: Path, tmp_path: Path
    ) -> None:
        source_dir = tmp_path / "file"
        source_dir.touch()
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            with pytest.raises(WheelError, match=f"{source_dir} is not a directory"):
                wf.write_files_from_directory(source_dir)

    def test_repr(self, wheel_path: Path) -> None:
        with WheelWriter(wheel_path, generator="generator 1.0") as wf:
            assert repr(wf) == f"WheelWriter({wheel_path}, generator='generator 1.0')"
