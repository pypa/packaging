# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

try:
    import collections.abc as collections_abc
except ImportError:
    import collections as collections_abc

try:
    import ctypes
except ImportError:
    ctypes = None
import distutils.util

import os
import platform
import re
import subprocess
import sys
import sysconfig
import types
import warnings

import pretend
import pytest

from packaging import tags, _AIX_platform


@pytest.fixture
def example_tag():
    return tags.Tag("py3", "none", "any")


@pytest.fixture
def is_x86():
    return re.match(r"(i\d86|x86_64)", platform.machine()) is not None


@pytest.fixture
def is_64bit_os():
    return platform.architecture()[0] == "64bit"


@pytest.fixture
def manylinux_module(monkeypatch):
    monkeypatch.setattr(tags, "_have_compatible_glibc", lambda *args: False)
    module_name = "_manylinux"
    module = types.ModuleType(module_name)
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


@pytest.fixture
def mock_interpreter_name(monkeypatch):
    def mock(name):
        if hasattr(sys, "implementation") and sys.implementation.name != name.lower():
            monkeypatch.setattr(sys.implementation, "name", name.lower())
            return True
        elif platform.python_implementation() != name:
            monkeypatch.setattr(platform, "python_implementation", lambda: name)
            return True
        return False

    return mock


class TestTag:
    def test_lowercasing(self):
        tag = tags.Tag("PY3", "None", "ANY")
        assert tag.interpreter == "py3"
        assert tag.abi == "none"
        assert tag.platform == "any"

    def test_equality(self):
        args = "py3", "none", "any"
        assert tags.Tag(*args) == tags.Tag(*args)

    def test_equality_fails_with_non_tag(self):
        assert not tags.Tag("py3", "none", "any") == "non-tag"

    def test_hashing(self, example_tag):
        tags = {example_tag}  # Should not raise TypeError.
        assert example_tag in tags

    def test_hash_equality(self, example_tag):
        equal_tag = tags.Tag("py3", "none", "any")
        assert example_tag == equal_tag  # Sanity check.
        assert example_tag.__hash__() == equal_tag.__hash__()

    def test_str(self, example_tag):
        assert str(example_tag) == "py3-none-any"

    def test_repr(self, example_tag):
        assert repr(example_tag) == "<py3-none-any @ {tag_id}>".format(
            tag_id=id(example_tag)
        )

    def test_attribute_access(self, example_tag):
        assert example_tag.interpreter == "py3"
        assert example_tag.abi == "none"
        assert example_tag.platform == "any"


class TestWarnKeywordOnlyParameter:
    def test_no_argument(self):
        assert not tags._warn_keyword_parameter("test_warn_keyword_parameters", {})

    def test_false(self):
        assert not tags._warn_keyword_parameter(
            "test_warn_keyword_parameters", {"warn": False}
        )

    def test_true(self):
        assert tags._warn_keyword_parameter(
            "test_warn_keyword_parameters", {"warn": True}
        )

    def test_too_many_arguments(self):
        message_re = re.compile(r"too_many.+{!r}".format("whatever"))
        with pytest.raises(TypeError, match=message_re):
            tags._warn_keyword_parameter("too_many", {"warn": True, "whatever": True})

    def test_wrong_argument(self):
        message_re = re.compile(r"missing.+{!r}".format("unexpected"))
        with pytest.raises(TypeError, match=message_re):
            tags._warn_keyword_parameter("missing", {"unexpected": True})


class TestParseTag:
    def test_simple(self, example_tag):
        parsed_tags = tags.parse_tag(str(example_tag))
        assert parsed_tags == {example_tag}

    def test_multi_interpreter(self, example_tag):
        expected = {example_tag, tags.Tag("py2", "none", "any")}
        given = tags.parse_tag("py2.py3-none-any")
        assert given == expected

    def test_multi_platform(self):
        expected = {
            tags.Tag("cp37", "cp37m", platform)
            for platform in (
                "macosx_10_6_intel",
                "macosx_10_9_intel",
                "macosx_10_9_x86_64",
                "macosx_10_10_intel",
                "macosx_10_10_x86_64",
            )
        }
        given = tags.parse_tag(
            "cp37-cp37m-macosx_10_6_intel.macosx_10_9_intel.macosx_10_9_x86_64."
            "macosx_10_10_intel.macosx_10_10_x86_64"
        )
        assert given == expected


class TestInterpreterName:
    def test_sys_implementation_name(self, monkeypatch):
        class MockImplementation(object):
            pass

        mock_implementation = MockImplementation()
        mock_implementation.name = "sillywalk"
        monkeypatch.setattr(sys, "implementation", mock_implementation, raising=False)
        assert tags.interpreter_name() == "sillywalk"

    def test_platform(self, monkeypatch):
        monkeypatch.delattr(sys, "implementation", raising=False)
        name = "SillyWalk"
        monkeypatch.setattr(platform, "python_implementation", lambda: name)
        assert tags.interpreter_name() == name.lower()

    def test_interpreter_short_names(self, mock_interpreter_name, monkeypatch):
        mock_interpreter_name("cpython")
        assert tags.interpreter_name() == "cp"


class TestInterpreterVersion:
    def test_warn(self, monkeypatch):
        class MockConfigVar(object):
            def __init__(self, return_):
                self.warn = None
                self._return = return_

            def __call__(self, name, warn):
                self.warn = warn
                return self._return

        mock_config_var = MockConfigVar("38")
        monkeypatch.setattr(tags, "_get_config_var", mock_config_var)
        tags.interpreter_version(warn=True)
        assert mock_config_var.warn

    def test_python_version_nodot(self, monkeypatch):
        monkeypatch.setattr(tags, "_get_config_var", lambda var, warn: "NN")
        assert tags.interpreter_version() == "NN"

    def test_sys_version_info(self, monkeypatch):
        monkeypatch.setattr(tags, "_get_config_var", lambda *args, **kwargs: None)
        monkeypatch.setattr(sys, "version_info", ("L", "M", "N"))
        assert tags.interpreter_version() == "LM"


class TestMacOSPlatforms:
    @pytest.mark.parametrize(
        "arch, is_32bit, expected",
        [
            ("i386", True, "i386"),
            ("ppc", True, "ppc"),
            ("x86_64", False, "x86_64"),
            ("x86_64", True, "i386"),
            ("ppc64", False, "ppc64"),
            ("ppc64", True, "ppc"),
        ],
    )
    def test_architectures(self, arch, is_32bit, expected):
        assert tags._mac_arch(arch, is_32bit=is_32bit) == expected

    @pytest.mark.parametrize(
        "version,arch,expected",
        [
            ((10, 17), "x86_64", ["x86_64", "intel", "fat64", "fat32", "universal"]),
            ((10, 4), "x86_64", ["x86_64", "intel", "fat64", "fat32", "universal"]),
            ((10, 3), "x86_64", []),
            ((10, 17), "i386", ["i386", "intel", "fat32", "fat", "universal"]),
            ((10, 4), "i386", ["i386", "intel", "fat32", "fat", "universal"]),
            ((10, 3), "i386", []),
            ((10, 17), "ppc64", []),
            ((10, 6), "ppc64", []),
            ((10, 5), "ppc64", ["ppc64", "fat64", "universal"]),
            ((10, 3), "ppc64", []),
            ((10, 17), "ppc", []),
            ((10, 7), "ppc", []),
            ((10, 6), "ppc", ["ppc", "fat32", "fat", "universal"]),
            ((10, 0), "ppc", ["ppc", "fat32", "fat", "universal"]),
            ((11, 0), "riscv", ["riscv", "universal"]),
        ],
    )
    def test_binary_formats(self, version, arch, expected):
        assert tags._mac_binary_formats(version, arch) == expected

    def test_version_detection(self, monkeypatch):
        if platform.system() != "Darwin":
            monkeypatch.setattr(
                platform, "mac_ver", lambda: ("10.14", ("", "", ""), "x86_64")
            )
        version = platform.mac_ver()[0].split(".")
        expected = "macosx_{major}_{minor}".format(major=version[0], minor=version[1])
        platforms = list(tags.mac_platforms(arch="x86_64"))
        assert platforms[0].startswith(expected)

    @pytest.mark.parametrize("arch", ["x86_64", "i386"])
    def test_arch_detection(self, arch, monkeypatch):
        if platform.system() != "Darwin" or platform.mac_ver()[2] != arch:
            monkeypatch.setattr(
                platform, "mac_ver", lambda: ("10.14", ("", "", ""), arch)
            )
            monkeypatch.setattr(tags, "_mac_arch", lambda *args: arch)
        assert next(tags.mac_platforms((10, 14))).endswith(arch)

    def test_mac_platforms(self):
        platforms = list(tags.mac_platforms((10, 5), "x86_64"))
        assert platforms == [
            "macosx_10_5_x86_64",
            "macosx_10_5_intel",
            "macosx_10_5_fat64",
            "macosx_10_5_fat32",
            "macosx_10_5_universal",
            "macosx_10_4_x86_64",
            "macosx_10_4_intel",
            "macosx_10_4_fat64",
            "macosx_10_4_fat32",
            "macosx_10_4_universal",
        ]

        assert len(list(tags.mac_platforms((10, 17), "x86_64"))) == 14 * 5

        assert not list(tags.mac_platforms((10, 0), "x86_64"))


class TestManylinuxPlatform:
    def test_module_declaration_true(self, manylinux_module):
        manylinux_module.manylinux1_compatible = True
        assert tags._is_manylinux_compatible("manylinux1", (2, 5))

    def test_module_declaration_false(self, manylinux_module):
        manylinux_module.manylinux1_compatible = False
        assert not tags._is_manylinux_compatible("manylinux1", (2, 5))

    def test_module_declaration_missing_attribute(self, manylinux_module):
        try:
            del manylinux_module.manylinux1_compatible
        except AttributeError:
            pass
        assert not tags._is_manylinux_compatible("manylinux1", (2, 5))

    def test_is_manylinux_compatible_module_support(
        self, manylinux_module, monkeypatch
    ):
        monkeypatch.setitem(sys.modules, manylinux_module.__name__, None)
        assert not tags._is_manylinux_compatible("manylinux1", (2, 5))

    @pytest.mark.parametrize(
        "version,compatible", (((2, 0), True), ((2, 5), True), ((2, 10), False))
    )
    def test_is_manylinux_compatible_glibc_support(
        self, version, compatible, monkeypatch
    ):
        monkeypatch.setitem(sys.modules, "_manylinux", None)
        monkeypatch.setattr(
            tags,
            "_have_compatible_glibc",
            lambda major, minor: (major, minor) <= (2, 5),
        )
        assert bool(tags._is_manylinux_compatible("manylinux1", version)) == compatible

    @pytest.mark.parametrize(
        "version_str,major,minor,expected",
        [
            ("2.4", 2, 4, True),
            ("2.4", 2, 5, False),
            ("2.4", 2, 3, True),
            ("3.4", 2, 4, False),
        ],
    )
    def test_check_glibc_version(self, version_str, major, minor, expected):
        assert expected == tags._check_glibc_version(version_str, major, minor)

    @pytest.mark.parametrize("version_str", ["glibc-2.4.5", "2"])
    def test_check_glibc_version_warning(self, version_str):
        with warnings.catch_warnings(record=True) as w:
            tags._check_glibc_version(version_str, 2, 4)
            assert len(w) == 1
            assert issubclass(w[0].category, RuntimeWarning)

    @pytest.mark.skipif(not ctypes, reason="requires ctypes")
    @pytest.mark.parametrize(
        "version_str,expected",
        [
            # Be very explicit about bytes and Unicode for Python 2 testing.
            (b"2.4", "2.4"),
            (u"2.4", "2.4"),
        ],
    )
    def test_glibc_version_string(self, version_str, expected, monkeypatch):
        class LibcVersion:
            def __init__(self, version_str):
                self.version_str = version_str

            def __call__(self):
                return version_str

        class ProcessNamespace:
            def __init__(self, libc_version):
                self.gnu_get_libc_version = libc_version

        process_namespace = ProcessNamespace(LibcVersion(version_str))
        monkeypatch.setattr(ctypes, "CDLL", lambda _: process_namespace)
        monkeypatch.setattr(tags, "_glibc_version_string_confstr", lambda: False)

        assert tags._glibc_version_string() == expected

        del process_namespace.gnu_get_libc_version
        assert tags._glibc_version_string() is None

    def test_glibc_version_string_confstr(self, monkeypatch):
        monkeypatch.setattr(os, "confstr", lambda x: "glibc 2.20", raising=False)
        assert tags._glibc_version_string_confstr() == "2.20"

    @pytest.mark.parametrize(
        "failure",
        [pretend.raiser(ValueError), pretend.raiser(OSError), lambda x: "XXX"],
    )
    def test_glibc_version_string_confstr_fail(self, monkeypatch, failure):
        monkeypatch.setattr(os, "confstr", failure, raising=False)
        assert tags._glibc_version_string_confstr() is None

    def test_glibc_version_string_confstr_missing(self, monkeypatch):
        monkeypatch.delattr(os, "confstr", raising=False)
        assert tags._glibc_version_string_confstr() is None

    def test_glibc_version_string_ctypes_missing(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "ctypes", None)
        assert tags._glibc_version_string_ctypes() is None

    def test_get_config_var_does_not_log(self, monkeypatch):
        debug = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(tags.logger, "debug", debug)
        tags._get_config_var("missing")
        assert debug.calls == []

    def test_get_config_var_does_log(self, monkeypatch):
        debug = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(tags.logger, "debug", debug)
        tags._get_config_var("missing", warn=True)
        assert debug.calls == [
            pretend.call(
                "Config variable '%s' is unset, Python ABI tag may be incorrect",
                "missing",
            )
        ]

    @pytest.mark.skipif(platform.system() != "Linux", reason="requires Linux")
    def test_have_compatible_glibc_linux(self):
        # Assuming no one is running this test with a version of glibc released in
        # 1997.
        assert tags._have_compatible_glibc(2, 0)

    def test_have_compatible_glibc(self, monkeypatch):
        monkeypatch.setattr(tags, "_glibc_version_string", lambda: "2.4")
        assert tags._have_compatible_glibc(2, 4)

    def test_glibc_version_string_none(self, monkeypatch):
        monkeypatch.setattr(tags, "_glibc_version_string", lambda: None)
        assert not tags._have_compatible_glibc(2, 4)

    def test_linux_platforms_64bit_on_64bit_os(self, is_64bit_os, is_x86, monkeypatch):
        if platform.system() != "Linux" or not is_64bit_os or not is_x86:
            monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
            monkeypatch.setattr(tags, "_is_manylinux_compatible", lambda *args: False)
        linux_platform = list(tags._linux_platforms(is_32bit=False))[-1]
        assert linux_platform == "linux_x86_64"

    def test_linux_platforms_32bit_on_64bit_os(self, is_64bit_os, is_x86, monkeypatch):
        if platform.system() != "Linux" or not is_64bit_os or not is_x86:
            monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
            monkeypatch.setattr(tags, "_is_manylinux_compatible", lambda *args: False)
        linux_platform = list(tags._linux_platforms(is_32bit=True))[-1]
        assert linux_platform == "linux_i686"

    def test_linux_platforms_manylinux_unsupported(self, monkeypatch):
        monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
        monkeypatch.setattr(tags, "_is_manylinux_compatible", lambda *args: False)
        linux_platform = list(tags._linux_platforms(is_32bit=False))
        assert linux_platform == ["linux_x86_64"]

    def test_linux_platforms_manylinux1(self, monkeypatch):
        monkeypatch.setattr(
            tags, "_is_manylinux_compatible", lambda name, _: name == "manylinux1"
        )
        if platform.system() != "Linux":
            monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
        platforms = list(tags._linux_platforms(is_32bit=False))
        assert platforms == ["manylinux1_x86_64", "linux_x86_64"]

    def test_linux_platforms_manylinux2010(self, monkeypatch):
        monkeypatch.setattr(
            tags, "_is_manylinux_compatible", lambda name, _: name == "manylinux2010"
        )
        if platform.system() != "Linux":
            monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
        platforms = list(tags._linux_platforms(is_32bit=False))
        expected = ["manylinux2010_x86_64", "manylinux1_x86_64", "linux_x86_64"]
        assert platforms == expected

    def test_linux_platforms_manylinux2014(self, monkeypatch):
        monkeypatch.setattr(
            tags, "_is_manylinux_compatible", lambda name, _: name == "manylinux2014"
        )
        if platform.system() != "Linux":
            monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
        platforms = list(tags._linux_platforms(is_32bit=False))
        expected = [
            "manylinux2014_x86_64",
            "manylinux2010_x86_64",
            "manylinux1_x86_64",
            "linux_x86_64",
        ]
        assert platforms == expected

    def test_linux_platforms_manylinux2014_armhf_abi(self, monkeypatch):
        monkeypatch.setattr(
            tags, "_is_manylinux_compatible", lambda name, _: name == "manylinux2014"
        )
        monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_armv7l")
        monkeypatch.setattr(
            sys,
            "executable",
            os.path.join(os.path.dirname(__file__), "hello-world-armv7l-armhf"),
        )
        platforms = list(tags._linux_platforms(is_32bit=True))
        expected = ["manylinux2014_armv7l", "linux_armv7l"]
        assert platforms == expected

    def test_linux_platforms_manylinux2014_i386_abi(self, monkeypatch):
        monkeypatch.setattr(
            tags, "_is_manylinux_compatible", lambda name, _: name == "manylinux2014"
        )
        monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_x86_64")
        monkeypatch.setattr(
            sys,
            "executable",
            os.path.join(os.path.dirname(__file__), "hello-world-x86_64-i386"),
        )
        platforms = list(tags._linux_platforms(is_32bit=True))
        expected = [
            "manylinux2014_i686",
            "manylinux2010_i686",
            "manylinux1_i686",
            "linux_i686",
        ]
        assert platforms == expected

    def test_linux_platforms_manylinux2014_armv6l(self, monkeypatch):
        monkeypatch.setattr(
            tags, "_is_manylinux_compatible", lambda name, _: name == "manylinux2014"
        )
        monkeypatch.setattr(distutils.util, "get_platform", lambda: "linux_armv6l")
        platforms = list(tags._linux_platforms(is_32bit=True))
        expected = ["linux_armv6l"]
        assert platforms == expected

    @pytest.mark.parametrize(
        "machine, abi, alt_machine",
        [("x86_64", "x32", "i686"), ("armv7l", "armel", "armv7l")],
    )
    def test_linux_platforms_not_manylinux_abi(
        self, monkeypatch, machine, abi, alt_machine
    ):
        monkeypatch.setattr(tags, "_is_manylinux_compatible", lambda name, _: True)
        monkeypatch.setattr(
            distutils.util, "get_platform", lambda: "linux_{}".format(machine)
        )
        monkeypatch.setattr(
            sys,
            "executable",
            os.path.join(
                os.path.dirname(__file__), "hello-world-{}-{}".format(machine, abi)
            ),
        )
        platforms = list(tags._linux_platforms(is_32bit=True))
        expected = ["linux_{}".format(alt_machine)]
        assert platforms == expected

    @pytest.mark.parametrize(
        "machine, abi, elf_class, elf_data, elf_machine",
        [
            (
                "x86_64",
                "x32",
                tags._ELFFileHeader.ELFCLASS32,
                tags._ELFFileHeader.ELFDATA2LSB,
                tags._ELFFileHeader.EM_X86_64,
            ),
            (
                "x86_64",
                "i386",
                tags._ELFFileHeader.ELFCLASS32,
                tags._ELFFileHeader.ELFDATA2LSB,
                tags._ELFFileHeader.EM_386,
            ),
            (
                "x86_64",
                "amd64",
                tags._ELFFileHeader.ELFCLASS64,
                tags._ELFFileHeader.ELFDATA2LSB,
                tags._ELFFileHeader.EM_X86_64,
            ),
            (
                "armv7l",
                "armel",
                tags._ELFFileHeader.ELFCLASS32,
                tags._ELFFileHeader.ELFDATA2LSB,
                tags._ELFFileHeader.EM_ARM,
            ),
            (
                "armv7l",
                "armhf",
                tags._ELFFileHeader.ELFCLASS32,
                tags._ELFFileHeader.ELFDATA2LSB,
                tags._ELFFileHeader.EM_ARM,
            ),
            (
                "s390x",
                "s390x",
                tags._ELFFileHeader.ELFCLASS64,
                tags._ELFFileHeader.ELFDATA2MSB,
                tags._ELFFileHeader.EM_S390,
            ),
        ],
    )
    def test_get_elf_header(
        self, monkeypatch, machine, abi, elf_class, elf_data, elf_machine
    ):
        path = os.path.join(
            os.path.dirname(__file__), "hello-world-{}-{}".format(machine, abi)
        )
        monkeypatch.setattr(sys, "executable", path)
        elf_header = tags._get_elf_header()
        assert elf_header.e_ident_class == elf_class
        assert elf_header.e_ident_data == elf_data
        assert elf_header.e_machine == elf_machine

    @pytest.mark.parametrize(
        "content", [None, "invalid-magic", "invalid-class", "invalid-data", "too-short"]
    )
    def test_get_elf_header_bad_excutable(self, monkeypatch, content):
        if content:
            path = os.path.join(
                os.path.dirname(__file__), "hello-world-{}".format(content)
            )
        else:
            path = None
        monkeypatch.setattr(sys, "executable", path)
        assert tags._get_elf_header() is None

    def test_is_linux_armhf_not_elf(self, monkeypatch):
        monkeypatch.setattr(tags, "_get_elf_header", lambda: None)
        assert not tags._is_linux_armhf()

    def test_is_linux_i686_not_elf(self, monkeypatch):
        monkeypatch.setattr(tags, "_get_elf_header", lambda: None)
        assert not tags._is_linux_i686()


@pytest.mark.parametrize(
    "platform_name,dispatch_func",
    [
        ("Darwin", "mac_platforms"),
        ("Linux", "_linux_platforms"),
        ("Generic", "_generic_platforms"),
    ],
)
def test__platform_tags(platform_name, dispatch_func, monkeypatch):
    expected = ["sillywalk"]
    monkeypatch.setattr(platform, "system", lambda: platform_name)
    monkeypatch.setattr(tags, dispatch_func, lambda: expected)
    assert tags._platform_tags() == expected


class TestCPythonABI:
    @pytest.mark.parametrize(
        "py_debug,gettotalrefcount,result",
        [(1, False, True), (0, False, False), (None, True, True)],
    )
    def test_debug(self, py_debug, gettotalrefcount, result, monkeypatch):
        config = {"Py_DEBUG": py_debug, "WITH_PYMALLOC": 0, "Py_UNICODE_SIZE": 2}
        monkeypatch.setattr(sysconfig, "get_config_var", config.__getitem__)
        if gettotalrefcount:
            monkeypatch.setattr(sys, "gettotalrefcount", 1, raising=False)
        expected = ["cp37d" if result else "cp37"]
        assert tags._cpython_abis((3, 7)) == expected

    def test_debug_file_extension(self, monkeypatch):
        config = {"Py_DEBUG": None}
        monkeypatch.setattr(sysconfig, "get_config_var", config.__getitem__)
        monkeypatch.delattr(sys, "gettotalrefcount", raising=False)
        monkeypatch.setattr(tags, "EXTENSION_SUFFIXES", {"_d.pyd"})
        assert tags._cpython_abis((3, 8)) == ["cp38d", "cp38"]

    @pytest.mark.parametrize(
        "debug,expected", [(True, ["cp38d", "cp38"]), (False, ["cp38"])]
    )
    def test__debug_cp38(self, debug, expected, monkeypatch):
        config = {"Py_DEBUG": debug}
        monkeypatch.setattr(sysconfig, "get_config_var", config.__getitem__)
        assert tags._cpython_abis((3, 8)) == expected

    @pytest.mark.parametrize(
        "pymalloc,version,result",
        [
            (1, (3, 7), True),
            (0, (3, 7), False),
            (None, (3, 7), True),
            (1, (3, 8), False),
        ],
    )
    def test_pymalloc(self, pymalloc, version, result, monkeypatch):
        config = {"Py_DEBUG": 0, "WITH_PYMALLOC": pymalloc, "Py_UNICODE_SIZE": 2}
        monkeypatch.setattr(sysconfig, "get_config_var", config.__getitem__)
        base_abi = "cp{}{}".format(version[0], version[1])
        expected = [base_abi + "m" if result else base_abi]
        assert tags._cpython_abis(version) == expected

    @pytest.mark.parametrize(
        "unicode_size,maxunicode,version,result",
        [
            (4, 0x10FFFF, (3, 2), True),
            (2, 0xFFFF, (3, 2), False),
            (None, 0x10FFFF, (3, 2), True),
            (None, 0xFFFF, (3, 2), False),
            (4, 0x10FFFF, (3, 3), False),
        ],
    )
    def test_wide_unicode(self, unicode_size, maxunicode, version, result, monkeypatch):
        config = {"Py_DEBUG": 0, "WITH_PYMALLOC": 0, "Py_UNICODE_SIZE": unicode_size}
        monkeypatch.setattr(sysconfig, "get_config_var", config.__getitem__)
        monkeypatch.setattr(sys, "maxunicode", maxunicode)
        base_abi = "cp{}{}".format(version[0], version[1])
        expected = [base_abi + "u" if result else base_abi]
        assert tags._cpython_abis(version) == expected


class TestCPythonTags:
    def test_iterator_returned(self):
        result_iterator = tags.cpython_tags(
            (3, 8), ["cp38d", "cp38"], ["plat1", "plat2"]
        )
        isinstance(result_iterator, collections_abc.Iterator)

    def test_all_args(self):
        result_iterator = tags.cpython_tags(
            (3, 8), ["cp38d", "cp38"], ["plat1", "plat2"]
        )
        result = list(result_iterator)
        assert result == [
            tags.Tag("cp38", "cp38d", "plat1"),
            tags.Tag("cp38", "cp38d", "plat2"),
            tags.Tag("cp38", "cp38", "plat1"),
            tags.Tag("cp38", "cp38", "plat2"),
            tags.Tag("cp38", "abi3", "plat1"),
            tags.Tag("cp38", "abi3", "plat2"),
            tags.Tag("cp38", "none", "plat1"),
            tags.Tag("cp38", "none", "plat2"),
            tags.Tag("cp37", "abi3", "plat1"),
            tags.Tag("cp37", "abi3", "plat2"),
            tags.Tag("cp36", "abi3", "plat1"),
            tags.Tag("cp36", "abi3", "plat2"),
            tags.Tag("cp35", "abi3", "plat1"),
            tags.Tag("cp35", "abi3", "plat2"),
            tags.Tag("cp34", "abi3", "plat1"),
            tags.Tag("cp34", "abi3", "plat2"),
            tags.Tag("cp33", "abi3", "plat1"),
            tags.Tag("cp33", "abi3", "plat2"),
            tags.Tag("cp32", "abi3", "plat1"),
            tags.Tag("cp32", "abi3", "plat2"),
        ]
        result = list(tags.cpython_tags((3, 3), ["cp33m"], ["plat1", "plat2"]))
        assert result == [
            tags.Tag("cp33", "cp33m", "plat1"),
            tags.Tag("cp33", "cp33m", "plat2"),
            tags.Tag("cp33", "abi3", "plat1"),
            tags.Tag("cp33", "abi3", "plat2"),
            tags.Tag("cp33", "none", "plat1"),
            tags.Tag("cp33", "none", "plat2"),
            tags.Tag("cp32", "abi3", "plat1"),
            tags.Tag("cp32", "abi3", "plat2"),
        ]

    def test_python_version_defaults(self):
        tag = next(tags.cpython_tags(abis=["abi3"], platforms=["any"]))
        interpreter = "cp{}{}".format(*sys.version_info[:2])
        assert interpreter == tag.interpreter

    def test_abi_defaults(self, monkeypatch):
        monkeypatch.setattr(tags, "_cpython_abis", lambda _1, _2: ["cp38"])
        result = list(tags.cpython_tags((3, 8), platforms=["any"]))
        assert tags.Tag("cp38", "cp38", "any") in result
        assert tags.Tag("cp38", "abi3", "any") in result
        assert tags.Tag("cp38", "none", "any") in result

    def test_platforms_defaults(self, monkeypatch):
        monkeypatch.setattr(tags, "_platform_tags", lambda: ["plat1"])
        result = list(tags.cpython_tags((3, 8), abis=["whatever"]))
        assert tags.Tag("cp38", "whatever", "plat1") in result

    def test_major_only_python_version(self):
        result = list(tags.cpython_tags((3,), ["abi"], ["plat"]))
        assert result == [
            tags.Tag("cp3", "abi", "plat"),
            tags.Tag("cp3", "none", "plat"),
        ]

    def test_major_only_python_version_with_default_abis(self):
        result = list(tags.cpython_tags((3,), platforms=["plat"]))
        assert result == [tags.Tag("cp3", "none", "plat")]

    @pytest.mark.parametrize("abis", [[], ["abi3"], ["none"]])
    def test_skip_redundant_abis(self, abis):
        results = list(tags.cpython_tags((3, 0), abis=abis, platforms=["any"]))
        assert results == [tags.Tag("cp30", "none", "any")]

    def test_abi3_python33(self):
        results = list(tags.cpython_tags((3, 3), abis=["cp33"], platforms=["plat"]))
        assert results == [
            tags.Tag("cp33", "cp33", "plat"),
            tags.Tag("cp33", "abi3", "plat"),
            tags.Tag("cp33", "none", "plat"),
            tags.Tag("cp32", "abi3", "plat"),
        ]

    def test_no_excess_abi3_python32(self):
        results = list(tags.cpython_tags((3, 2), abis=["cp32"], platforms=["plat"]))
        assert results == [
            tags.Tag("cp32", "cp32", "plat"),
            tags.Tag("cp32", "abi3", "plat"),
            tags.Tag("cp32", "none", "plat"),
        ]

    def test_no_abi3_python31(self):
        results = list(tags.cpython_tags((3, 1), abis=["cp31"], platforms=["plat"]))
        assert results == [
            tags.Tag("cp31", "cp31", "plat"),
            tags.Tag("cp31", "none", "plat"),
        ]

    def test_no_abi3_python27(self):
        results = list(tags.cpython_tags((2, 7), abis=["cp27"], platforms=["plat"]))
        assert results == [
            tags.Tag("cp27", "cp27", "plat"),
            tags.Tag("cp27", "none", "plat"),
        ]


class TestGenericTags:
    @pytest.mark.skipif(
        not sysconfig.get_config_var("SOABI"), reason="SOABI not defined"
    )
    def test__generic_abi_soabi_provided(self):
        abi = sysconfig.get_config_var("SOABI").replace(".", "_").replace("-", "_")
        assert [abi] == list(tags._generic_abi())

    def test__generic_abi(self, monkeypatch):
        monkeypatch.setattr(
            sysconfig, "get_config_var", lambda key: "cpython-37m-darwin"
        )
        assert list(tags._generic_abi()) == ["cpython_37m_darwin"]

    def test__generic_abi_no_soabi(self, monkeypatch):
        monkeypatch.setattr(sysconfig, "get_config_var", lambda key: None)
        assert not list(tags._generic_abi())

    def test_generic_platforms(self):
        platform = distutils.util.get_platform().replace("-", "_")
        platform = platform.replace(".", "_")
        assert list(tags._generic_platforms()) == [platform]

    def test_iterator_returned(self):
        result_iterator = tags.generic_tags("sillywalk33", ["abi"], ["plat1", "plat2"])
        assert isinstance(result_iterator, collections_abc.Iterator)

    def test_all_args(self):
        result_iterator = tags.generic_tags("sillywalk33", ["abi"], ["plat1", "plat2"])
        result = list(result_iterator)
        assert result == [
            tags.Tag("sillywalk33", "abi", "plat1"),
            tags.Tag("sillywalk33", "abi", "plat2"),
            tags.Tag("sillywalk33", "none", "plat1"),
            tags.Tag("sillywalk33", "none", "plat2"),
        ]

    @pytest.mark.parametrize("abi", [[], ["none"]])
    def test_abi_unspecified(self, abi):
        no_abi = list(tags.generic_tags("sillywalk34", abi, ["plat1", "plat2"]))
        assert no_abi == [
            tags.Tag("sillywalk34", "none", "plat1"),
            tags.Tag("sillywalk34", "none", "plat2"),
        ]

    def test_interpreter_default(self, monkeypatch):
        monkeypatch.setattr(tags, "interpreter_name", lambda: "sillywalk")
        monkeypatch.setattr(tags, "interpreter_version", lambda warn: "NN")
        result = list(tags.generic_tags(abis=["none"], platforms=["any"]))
        assert result == [tags.Tag("sillywalkNN", "none", "any")]

    def test_abis_default(self, monkeypatch):
        monkeypatch.setattr(tags, "_generic_abi", lambda: iter(["abi"]))
        result = list(tags.generic_tags(interpreter="sillywalk", platforms=["any"]))
        assert result == [
            tags.Tag("sillywalk", "abi", "any"),
            tags.Tag("sillywalk", "none", "any"),
        ]

    def test_platforms_default(self, monkeypatch):
        monkeypatch.setattr(tags, "_platform_tags", lambda: ["plat"])
        result = list(tags.generic_tags(interpreter="sillywalk", abis=["none"]))
        assert result == [tags.Tag("sillywalk", "none", "plat")]


class TestCompatibleTags:
    def test_all_args(self):
        result = list(tags.compatible_tags((3, 3), "cp33", ["plat1", "plat2"]))
        assert result == [
            tags.Tag("py33", "none", "plat1"),
            tags.Tag("py33", "none", "plat2"),
            tags.Tag("py3", "none", "plat1"),
            tags.Tag("py3", "none", "plat2"),
            tags.Tag("py32", "none", "plat1"),
            tags.Tag("py32", "none", "plat2"),
            tags.Tag("py31", "none", "plat1"),
            tags.Tag("py31", "none", "plat2"),
            tags.Tag("py30", "none", "plat1"),
            tags.Tag("py30", "none", "plat2"),
            tags.Tag("cp33", "none", "any"),
            tags.Tag("py33", "none", "any"),
            tags.Tag("py3", "none", "any"),
            tags.Tag("py32", "none", "any"),
            tags.Tag("py31", "none", "any"),
            tags.Tag("py30", "none", "any"),
        ]

    def test_major_only_python_version(self):
        result = list(tags.compatible_tags((3,), "cp33", ["plat"]))
        assert result == [
            tags.Tag("py3", "none", "plat"),
            tags.Tag("cp33", "none", "any"),
            tags.Tag("py3", "none", "any"),
        ]

    def test_default_python_version(self, monkeypatch):
        monkeypatch.setattr(sys, "version_info", (3, 1))
        result = list(tags.compatible_tags(interpreter="cp31", platforms=["plat"]))
        assert result == [
            tags.Tag("py31", "none", "plat"),
            tags.Tag("py3", "none", "plat"),
            tags.Tag("py30", "none", "plat"),
            tags.Tag("cp31", "none", "any"),
            tags.Tag("py31", "none", "any"),
            tags.Tag("py3", "none", "any"),
            tags.Tag("py30", "none", "any"),
        ]

    def test_default_interpreter(self):
        result = list(tags.compatible_tags((3, 1), platforms=["plat"]))
        assert result == [
            tags.Tag("py31", "none", "plat"),
            tags.Tag("py3", "none", "plat"),
            tags.Tag("py30", "none", "plat"),
            tags.Tag("py31", "none", "any"),
            tags.Tag("py3", "none", "any"),
            tags.Tag("py30", "none", "any"),
        ]

    def test_default_platforms(self, monkeypatch):
        monkeypatch.setattr(tags, "_platform_tags", lambda: iter(["plat", "plat2"]))
        result = list(tags.compatible_tags((3, 1), "cp31"))
        assert result == [
            tags.Tag("py31", "none", "plat"),
            tags.Tag("py31", "none", "plat2"),
            tags.Tag("py3", "none", "plat"),
            tags.Tag("py3", "none", "plat2"),
            tags.Tag("py30", "none", "plat"),
            tags.Tag("py30", "none", "plat2"),
            tags.Tag("cp31", "none", "any"),
            tags.Tag("py31", "none", "any"),
            tags.Tag("py3", "none", "any"),
            tags.Tag("py30", "none", "any"),
        ]


class TestSysTags:
    @pytest.mark.parametrize(
        "name,expected",
        [("CPython", "cp"), ("PyPy", "pp"), ("Jython", "jy"), ("IronPython", "ip")],
    )
    def test_interpreter_name(self, name, expected, mock_interpreter_name):
        mock_interpreter_name(name)
        assert tags.interpreter_name() == expected

    def test_iterator(self):
        assert isinstance(tags.sys_tags(), collections_abc.Iterator)

    def test_mac_cpython(self, mock_interpreter_name, monkeypatch):
        if mock_interpreter_name("CPython"):
            monkeypatch.setattr(tags, "_cpython_abis", lambda *a: ["cp33m"])
        if platform.system() != "Darwin":
            monkeypatch.setattr(platform, "system", lambda: "Darwin")
            monkeypatch.setattr(tags, "mac_platforms", lambda: ["macosx_10_5_x86_64"])
        abis = tags._cpython_abis(sys.version_info[:2])
        platforms = list(tags.mac_platforms())
        result = list(tags.sys_tags())
        assert len(abis) == 1
        assert result[0] == tags.Tag(
            "cp{major}{minor}".format(
                major=sys.version_info[0], minor=sys.version_info[1]
            ),
            abis[0],
            platforms[0],
        )
        assert result[-1] == tags.Tag(
            "py{}0".format(sys.version_info[0]), "none", "any"
        )

    def test_windows_cpython(self, mock_interpreter_name, monkeypatch):
        if mock_interpreter_name("CPython"):
            monkeypatch.setattr(tags, "_cpython_abis", lambda *a: ["cp33m"])
        if platform.system() != "Windows":
            monkeypatch.setattr(platform, "system", lambda: "Windows")
            monkeypatch.setattr(tags, "_generic_platforms", lambda: ["win_amd64"])
        abis = list(tags._cpython_abis(sys.version_info[:2]))
        platforms = list(tags._generic_platforms())
        result = list(tags.sys_tags())
        interpreter = "cp{major}{minor}".format(
            major=sys.version_info[0], minor=sys.version_info[1]
        )
        assert len(abis) == 1
        expected = tags.Tag(interpreter, abis[0], platforms[0])
        assert result[0] == expected
        expected = tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")
        assert result[-1] == expected

    def test_linux_cpython(self, mock_interpreter_name, monkeypatch):
        if mock_interpreter_name("CPython"):
            monkeypatch.setattr(tags, "_cpython_abis", lambda *a: ["cp33m"])
        if platform.system() != "Linux":
            monkeypatch.setattr(platform, "system", lambda: "Linux")
            monkeypatch.setattr(tags, "_linux_platforms", lambda: ["linux_x86_64"])
        abis = list(tags._cpython_abis(sys.version_info[:2]))
        platforms = list(tags._linux_platforms())
        result = list(tags.sys_tags())
        expected_interpreter = "cp{major}{minor}".format(
            major=sys.version_info[0], minor=sys.version_info[1]
        )
        assert len(abis) == 1
        assert result[0] == tags.Tag(expected_interpreter, abis[0], platforms[0])
        expected = tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")
        assert result[-1] == expected

    def test_generic(self, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Generic")
        monkeypatch.setattr(tags, "interpreter_name", lambda: "generic")

        result = list(tags.sys_tags())
        expected = tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")
        assert result[-1] == expected


def test_aix_platform_notpep425_ready(monkeypatch):
    if platform.system() != "AIX":
        monkeypatch.setattr(
            subprocess,
            "check_output",
            lambda *a: b"bos.mp64:bos.mp64:5.3.7.0:::C::BOS 64-bit:::::::1:0:/:0747\n",
        )
    monkeypatch.setattr(distutils.util, "get_platform", lambda: "aix-7.2")
    monkeypatch.setattr(_AIX_platform, "_sz", 64)
    result0 = list(tags._aix_platforms())
    result1 = [_AIX_platform.aix_platform()]
    assert result0 == result1
    assert result0[0].startswith("aix")
    assert result0[0].endswith("64")


def test_aix_platform_no_subprocess(monkeypatch):
    monkeypatch.setattr(_AIX_platform, "_have_subprocess", False)
    vrmf, bd = _AIX_platform._aix_bosmp64()
    assert vrmf
    assert bd == 9898


def test_aix_platform_pep425_ready(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda *a: b"bos.mp64:bos.mp64:5.3.7.0:::C::BOS 64-bit:::::::1:0:/:0747\n",
    )
    monkeypatch.setattr(distutils.util, "get_platform", lambda: "aix-5307-0747-32")
    monkeypatch.setattr(_AIX_platform, "_sz", 32)
    result0 = list(tags._aix_platforms())
    result1 = [_AIX_platform.aix_platform()]
    assert result0[0][:4] == result1[0][:4]
    assert result0[0].startswith("aix")
    assert result0[0].endswith("32")


def test_sys_tags_aix64_cpython(mock_interpreter_name, monkeypatch):
    if mock_interpreter_name("CPython"):
        monkeypatch.setattr(tags, "_cpython_abis", lambda *a: ["cp36m"])
    if platform.system() != "AIX":
        monkeypatch.setattr(platform, "system", lambda: "AIX")
    monkeypatch.setattr(tags, "_aix_platforms", lambda: ["aix_5307_0747_64"])
    abis = tags._cpython_abis(sys.version_info[:2])
    platforms = tags._aix_platforms()
    result = list(tags.sys_tags())
    expected_interpreter = "cp{major}{minor}".format(
        major=sys.version_info[0], minor=sys.version_info[1]
    )
    assert len(abis) == 1
    assert result[0] == tags.Tag(expected_interpreter, abis[0], platforms[0])
    expected = tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")
    assert result[-1] == expected


def test_sys_tags_aix32_cpython(mock_interpreter_name, monkeypatch):
    if mock_interpreter_name("CPython"):
        monkeypatch.setattr(tags, "_cpython_abis", lambda *a: ["cp36m"])
    if platform.system() != "AIX":
        monkeypatch.setattr(platform, "system", lambda: "AIX")
    monkeypatch.setattr(tags, "_aix_platforms", lambda: ["aix_5307_0747_32"])
    abis = tags._cpython_abis(sys.version_info[:2])
    platforms = tags._aix_platforms()
    result = list(tags.sys_tags())
    expected_interpreter = "cp{major}{minor}".format(
        major=sys.version_info[0], minor=sys.version_info[1]
    )
    assert len(abis) == 1
    assert result[0] == tags.Tag(expected_interpreter, abis[0], platforms[0])
    expected = tags.Tag("py{}0".format(sys.version_info[0]), "none", "any")
    assert result[-1] == expected


def test_aix_buildtag(monkeypatch):
    monkeypatch.setattr(_AIX_platform, "_bgt", "powerpc-ibm-aix5.3.7.0")
    assert _AIX_platform._bd == 9898
    monkeypatch.setattr(_AIX_platform, "_bd", 9797)
    monkeypatch.setattr(_AIX_platform, "_sz", 64)
    assert _AIX_platform._bd == 9797
    result = _AIX_platform.aix_buildtag()
    assert result == "aix-5307-9797-64"
    monkeypatch.setattr(_AIX_platform, "_bd", 747)
    monkeypatch.setattr(_AIX_platform, "_sz", 32)
    result = _AIX_platform.aix_buildtag()
    assert result == "aix-5307-0747-32"
