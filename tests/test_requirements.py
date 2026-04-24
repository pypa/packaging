# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import pickle

import pytest

from packaging.markers import Marker
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet

EQUAL_DEPENDENCIES = [
    ("packaging>20.1", "packaging>20.1"),
    (
        'requests[security, tests]>=2.8.1,==2.8.*;python_version<"2.7"',
        'requests [security,tests] >= 2.8.1, == 2.8.* ; python_version < "2.7"',
    ),
    (
        'importlib-metadata; python_version<"3.8"',
        "importlib-metadata; python_version<'3.8'",
    ),
    (
        'appdirs>=1.4.4,<2; os_name=="posix" and extra=="testing"',
        "appdirs>=1.4.4,<2; os_name == 'posix' and extra == 'testing'",
    ),
]

EQUIVALENT_DEPENDENCIES = [
    ("scikit-learn==1.0.1", "scikit_learn==1.0.1"),
]

DIFFERENT_DEPENDENCIES = [
    ("package_one", "package_two"),
    ("packaging>20.1", "packaging>=20.1"),
    ("packaging>20.1", "packaging>21.1"),
    ("packaging>20.1", "package>20.1"),
    (
        'requests[security,tests]>=2.8.1,==2.8.*;python_version<"2.7"',
        'requests [security,tests] >= 2.8.1 ; python_version < "2.7"',
    ),
    (
        'importlib-metadata; python_version<"3.8"',
        "importlib-metadata; python_version<'3.7'",
    ),
    (
        'appdirs>=1.4.4,<2; os_name=="posix" and extra=="testing"',
        "appdirs>=1.4.4,<2; os_name == 'posix' and extra == 'docs'",
    ),
]


@pytest.mark.parametrize(
    "name",
    [
        "package",
        "pAcKaGe",
        "Package",
        "foo-bar.quux_bAz",
        "installer",
        "android12",
    ],
)
@pytest.mark.parametrize(
    "extras",
    [
        set(),
        {"a"},
        {"a", "b"},
        {"a", "B", "CDEF123"},
    ],
)
@pytest.mark.parametrize(
    ("url", "specifier"),
    [
        (None, ""),
        ("https://example.com/packagename.zip", ""),
        ("ssh://user:pass%20word@example.com/packagename.zip", ""),
        ("https://example.com/name;v=1.1/?query=foo&bar=baz#blah", ""),
        ("git+ssh://git.example.com/MyProject", ""),
        ("git+ssh://git@github.com:pypa/packaging.git", ""),
        ("git+https://git.example.com/MyProject.git@master", ""),
        ("git+https://git.example.com/MyProject.git@v1.0", ""),
        ("git+https://git.example.com/MyProject.git@refs/pull/123/head", ""),
        ("gopher:/foo/com", ""),
        (None, "==={ws}arbitrarystring"),
        (None, "({ws}==={ws}arbitrarystring{ws})"),
        (None, "=={ws}1.0"),
        (None, "({ws}=={ws}1.0{ws})"),
        (None, "=={ws}1.0-alpha"),
        (None, "<={ws}1!3.0.0.rc2"),
        (None, ">{ws}2.2{ws},{ws}<{ws}3"),
        (None, "(>{ws}2.2{ws},{ws}<{ws}3)"),
    ],
)
@pytest.mark.parametrize(
    "marker",
    [
        None,
        "python_version{ws}>={ws}'3.3'",
        '({ws}python_version{ws}>={ws}"3.4"{ws}){ws}and extra{ws}=={ws}"oursql"',
        (
            "sys_platform{ws}!={ws}'linux' and(os_name{ws}=={ws}'linux' or "
            "python_version{ws}>={ws}'3.3'{ws}){ws}"
        ),
    ],
)
@pytest.mark.parametrize("whitespace", ["", " ", "\t"])
def test_basic_valid_requirement_parsing(
    name: str,
    extras: set[str],
    specifier: str,
    url: str | None,
    marker: str,
    whitespace: str,
) -> None:
    # GIVEN
    parts = [name]
    if extras:
        parts.append("[")
        parts.append("{ws},{ws}".format(ws=whitespace).join(sorted(extras)))
        parts.append("]")
    if specifier:
        parts.append(specifier.format(ws=whitespace))
    if url is not None:
        parts.append("@")
        parts.append(url.format(ws=whitespace))
    if marker is not None:
        if url is not None:
            parts.append(" ;")
        else:
            parts.append(";")
        parts.append(marker.format(ws=whitespace))

    to_parse = whitespace.join(parts)

    # WHEN
    req = Requirement(to_parse)

    # THEN
    assert req.name == name
    assert req.extras == extras
    assert req.url == url
    assert req.specifier == specifier.format(ws="").strip("()")
    assert req.marker == (Marker(marker.format(ws="")) if marker else None)


@pytest.mark.parametrize(
    ("input_req", "norm_req"),
    [
        (
            'mariadb>=1.0.1; extra == "mariadb_connector"',
            'mariadb>=1.0.1; extra == "mariadb-connector"',
        ),
        (
            'mariadb>=1.0.1; python_version >= "3" and extra == "mariadb_connector"',
            'mariadb>=1.0.1; python_version >= "3" and extra == "mariadb-connector"',
        ),
    ],
)
def test_normalized_requirements(input_req: str, norm_req: str) -> None:
    req = Requirement(input_req)
    assert str(req) == norm_req


class TestRequirementParsing:
    @pytest.mark.parametrize(
        "marker",
        [
            "python_implementation == ''",
            "platform_python_implementation == ''",
            "os.name == 'linux'",
            "os_name == 'linux'",
            "'8' in platform.version",
            "'8' not in platform.version",
        ],
    )
    def test_valid_marker(self, marker: str) -> None:
        # GIVEN
        to_parse = f"name; {marker}"

        # WHEN
        Requirement(to_parse)

    @pytest.mark.parametrize(
        "url",
        [
            "file:///absolute/path",
            "file://.",
            "file:.",
            "file:/.",
        ],
    )
    def test_file_url(self, url: str) -> None:
        # GIVEN
        to_parse = f"name @ {url}"

        # WHEN
        req = Requirement(to_parse)

        # THEN
        assert req.url == url

    def test_empty_extras(self) -> None:
        # GIVEN
        to_parse = "name[]"

        # WHEN
        req = Requirement(to_parse)

        # THEN
        assert req.name == "name"
        assert req.extras == set()

    def test_empty_specifier(self) -> None:
        # GIVEN
        to_parse = "name()"

        # WHEN
        req = Requirement(to_parse)

        # THEN
        assert req.name == "name"
        assert req.specifier == ""

    # ----------------------------------------------------------------------------------
    # Everything below this (in this class) should be parsing failure modes
    # ----------------------------------------------------------------------------------
    # Start all method names with with `test_error_`
    # to make it easier to run these tests with `-k error`

    def test_error_when_empty_string(self) -> None:
        # GIVEN
        to_parse = ""

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected package name at the start of dependency specifier\n"
            "    \n"
            "    ^"
        )

    def test_error_no_name(self) -> None:
        # GIVEN
        to_parse = "==0.0"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected package name at the start of dependency specifier\n"
            "    ==0.0\n"
            "    ^"
        )

    def test_error_when_missing_comma_in_extras(self) -> None:
        # GIVEN
        to_parse = "name[bar baz]"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected comma between extra names\n"
            "    name[bar baz]\n"
            "             ^"
        )

    def test_error_when_trailing_comma_in_extras(self) -> None:
        # GIVEN
        to_parse = "name[bar, baz,]"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected extra name after comma\n"
            "    name[bar, baz,]\n"
            "                  ^"
        )

    def test_error_when_parens_not_closed_correctly(self) -> None:
        # GIVEN
        to_parse = "name (>= 1.0"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected matching RIGHT_PARENTHESIS for LEFT_PARENTHESIS, "
            "after version specifier\n"
            "    name (>= 1.0\n"
            "         ~~~~~~~^"
        )

    def test_error_when_prefix_match_is_used_incorrectly(self) -> None:
        # GIVEN
        to_parse = "black (>=20.*) ; extra == 'format'"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            ".* suffix can only be used with `==` or `!=` operators\n"
            "    black (>=20.*) ; extra == 'format'\n"
            "           ~~~~~^"
        )

    @pytest.mark.parametrize("operator", [">=", "<=", ">", "<", "~="])
    def test_error_when_local_version_label_is_used_incorrectly(
        self, operator: str
    ) -> None:
        # GIVEN
        to_parse = f"name {operator} 1.0+local.version.label"
        op_tilde = len(operator) * "~"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Local version label can only be used with `==` or `!=` operators\n"
            f"    name {operator} 1.0+local.version.label\n"
            f"         {op_tilde}~~~~^"
        )

    def test_error_when_bracket_not_closed_correctly(self) -> None:
        # GIVEN
        to_parse = "name[bar, baz >= 1.0"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected matching RIGHT_BRACKET for LEFT_BRACKET, "
            "after extras\n"
            "    name[bar, baz >= 1.0\n"
            "        ~~~~~~~~~~^"
        )

    def test_error_when_extras_bracket_left_unclosed(self) -> None:
        # GIVEN
        to_parse = "name[bar, baz"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected matching RIGHT_BRACKET for LEFT_BRACKET, "
            "after extras\n"
            "    name[bar, baz\n"
            "        ~~~~~~~~~^"
        )

    def test_error_no_space_after_url(self) -> None:
        # GIVEN
        to_parse = "name @ https://example.com/; extra == 'example'"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected semicolon (after URL and whitespace) or end\n"
            "    name @ https://example.com/; extra == 'example'\n"
            "           ~~~~~~~~~~~~~~~~~~~~~~^"
        )

    def test_error_marker_bracket_unclosed(self) -> None:
        # GIVEN
        to_parse = "name; (extra == 'example'"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected matching RIGHT_PARENTHESIS for LEFT_PARENTHESIS, "
            "after marker expression\n"
            "    name; (extra == 'example'\n"
            "          ~~~~~~~~~~~~~~~~~~~^"
        )

    def test_error_no_url_after_at(self) -> None:
        # GIVEN
        to_parse = "name @ "

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected URL after @\n"
            "    name @ \n"
            "           ^"
        )

    def test_error_invalid_marker_lvalue(self) -> None:
        # GIVEN
        to_parse = "name; invalid_name"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected a marker variable or quoted string\n"
            "    name; invalid_name\n"
            "          ^"
        )

    def test_error_invalid_marker_rvalue(self) -> None:
        # GIVEN
        to_parse = "name; '3.7' <= invalid_name"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected a marker variable or quoted string\n"
            "    name; '3.7' <= invalid_name\n"
            "                   ^"
        )

    def test_error_invalid_marker_notin_without_whitespace(self) -> None:
        # GIVEN
        to_parse = "name; '3.7' notin python_version"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected marker operator, one of <=, <, !=, ==, >=, >, ~=, ===, "
            "in, not in\n"
            "    name; '3.7' notin python_version\n"
            "                ^"
        )

    def test_error_when_no_word_boundary(self) -> None:
        # GIVEN
        to_parse = "name; '3.6'inpython_version"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected marker operator, one of <=, <, !=, ==, >=, >, ~=, ===, "
            "in, not in\n"
            "    name; '3.6'inpython_version\n"
            "               ^"
        )

    def test_error_invalid_marker_not_without_in(self) -> None:
        # GIVEN
        to_parse = "name; '3.7' not python_version"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected 'in' after 'not'\n"
            "    name; '3.7' not python_version\n"
            "                    ^"
        )

    def test_error_invalid_marker_with_invalid_op(self) -> None:
        # GIVEN
        to_parse = "name; '3.7' ~ python_version"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected marker operator, one of <=, <, !=, ==, >=, >, ~=, ===, "
            "in, not in\n"
            "    name; '3.7' ~ python_version\n"
            "                ^"
        )

    def test_error_on_legacy_version_outside_triple_equals(self) -> None:
        # GIVEN
        to_parse = "name==1.0.org1"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected comma (within version specifier), "
            "semicolon (after version specifier) or end\n"
            "    name==1.0.org1\n"
            "        ~~~~~^"
        )

    def test_error_on_missing_version_after_op(self) -> None:
        # GIVEN
        to_parse = "name=="

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected semicolon (after name with no version specifier) or end\n"
            "    name==\n"
            "        ^"
        )

    def test_error_on_missing_op_after_name(self) -> None:
        # GIVEN
        to_parse = "name 1.0"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected semicolon (after name with no version specifier) or end\n"
            "    name 1.0\n"
            "         ^"
        )

    def test_error_on_random_char_after_specifier(self) -> None:
        # GIVEN
        to_parse = "name >= 1.0 #"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected comma (within version specifier), "
            "semicolon (after version specifier) or end\n"
            "    name >= 1.0 #\n"
            "         ~~~~~~~^"
        )

    def test_error_on_missing_comma_in_specifier(self) -> None:
        # GIVEN
        to_parse = "name >= 1.0 <= 2.0"

        # WHEN
        with pytest.raises(InvalidRequirement) as ctx:
            Requirement(to_parse)

        # THEN
        assert ctx.exconly() == (
            "packaging.requirements.InvalidRequirement: "
            "Expected comma (within version specifier), "
            "semicolon (after version specifier) or end\n"
            "    name >= 1.0 <= 2.0\n"
            "         ~~~~~~~^"
        )


class TestRequirementBehaviour:
    def test_types_with_nothing(self) -> None:
        # GIVEN
        to_parse = "foobar"

        # WHEN
        req = Requirement(to_parse)

        # THEN
        assert isinstance(req.name, str)
        assert isinstance(req.extras, set)
        assert req.url is None
        assert isinstance(req.specifier, SpecifierSet)
        assert req.marker is None

    def test_types_with_specifier_and_marker(self) -> None:
        # GIVEN
        to_parse = "foobar[quux]<2,>=3; os_name=='a'"

        # WHEN
        req = Requirement(to_parse)

        # THEN
        assert isinstance(req.name, str)
        assert isinstance(req.extras, set)
        assert req.url is None
        assert isinstance(req.specifier, SpecifierSet)
        assert isinstance(req.marker, Marker)

    def test_types_with_url(self) -> None:
        req = Requirement("foobar @ http://foo.com")
        assert isinstance(req.name, str)
        assert isinstance(req.extras, set)
        assert isinstance(req.url, str)
        assert isinstance(req.specifier, SpecifierSet)
        assert req.marker is None

    @pytest.mark.parametrize(
        "url_or_specifier",
        ["", " @ https://url ", "!=2.0", "==2.*"],
    )
    @pytest.mark.parametrize("extras", ["", "[a]", "[a,b]", "[a1,b1,b2]"])
    @pytest.mark.parametrize(
        "marker",
        ["", '; python_version == "3.11"', '; "3." not in python_version'],
    )
    def test_str_and_repr(
        self, extras: str, url_or_specifier: str, marker: str
    ) -> None:
        # GIVEN
        to_parse = f"name{extras}{url_or_specifier}{marker}"

        # WHEN
        req = Requirement(to_parse)

        # THEN
        assert str(req) == to_parse.strip()
        assert repr(req) == f"<Requirement({to_parse.strip()!r})>"

    @pytest.mark.parametrize(("dep1", "dep2"), EQUAL_DEPENDENCIES)
    def test_equal_reqs_equal_hashes(self, dep1: str, dep2: str) -> None:
        """Requirement objects created from equal strings should be equal."""
        # GIVEN / WHEN
        req1, req2 = Requirement(dep1), Requirement(dep2)

        assert req1 == req2
        assert hash(req1) == hash(req2)

    @pytest.mark.parametrize(("dep1", "dep2"), EQUIVALENT_DEPENDENCIES)
    def test_equivalent_reqs_equal_hashes_unequal_strings(
        self, dep1: str, dep2: str
    ) -> None:
        """Requirement objects created from equivalent strings should be equal,
        even though their string representation will not."""
        # GIVEN / WHEN
        req1, req2 = Requirement(dep1), Requirement(dep2)

        assert req1 == req2
        assert hash(req1) == hash(req2)
        assert str(req1) != str(req2)

    @pytest.mark.parametrize(("dep1", "dep2"), DIFFERENT_DEPENDENCIES)
    def test_different_reqs_different_hashes(self, dep1: str, dep2: str) -> None:
        """Requirement objects created from non-equivalent strings should differ."""
        # GIVEN / WHEN
        req1, req2 = Requirement(dep1), Requirement(dep2)

        # THEN
        assert req1 != req2
        assert hash(req1) != hash(req2)

    def test_compare_with_string(self) -> None:
        assert Requirement("packaging>=21.3") != "packaging>=21.3"


@pytest.mark.parametrize(
    "req_str",
    [
        "requests",
        "requests>=2.0",
        "requests>=2.0,<3.0",
        'requests>=2.0; python_version >= "3.8"',
        "requests[security,socks]>=2.0",
        "my-pkg @ https://example.com",
        'Django>=1.4.2,!=1.5.0,!=1.5.1; python_version < "3"',
    ],
)
def test_pickle_requirement_roundtrip(req_str: str) -> None:
    # Make sure equality and str() work between a pickle/unpickle round trip.
    r = Requirement(req_str)
    loaded = pickle.loads(pickle.dumps(r))
    assert loaded == r
    assert str(loaded) == str(r)


def test_pickle_requirement_setstate_rejects_invalid_state() -> None:
    # Cover the TypeError branches in __setstate__ for invalid input.
    r = Requirement.__new__(Requirement)
    with pytest.raises(TypeError, match="Cannot restore Requirement"):
        r.__setstate__(12345)
    with pytest.raises(TypeError, match="Cannot restore Requirement"):
        r.__setstate__((1, 2, 3))


def test_pickle_requirement_setstate_rejects_invalid_string() -> None:
    # Cover the string branch where Requirement() raises InvalidRequirement.
    r = Requirement.__new__(Requirement)
    with pytest.raises(TypeError, match="Cannot restore Requirement"):
        r.__setstate__("this is not a valid requirement")


# Pickle bytes generated with packaging==26.1, Python 3.13.1, pickle protocol 2.
# Format: plain __dict__ (no __getstate__). Contains nested SpecifierSet and
# Marker objects also pickled in their old format.
_PACKAGING_26_1_PICKLE_REQUESTS_GE_2_0_WITH_MARKER = (
    b"\x80\x02cpackaging.requirements\nRequirement\nq\x00)\x81q\x01}q\x02("
    b"X\x04\x00\x00\x00nameq\x03X\x08\x00\x00\x00requestsq\x04X\x03\x00"
    b"\x00\x00urlq\x05NX\x06\x00\x00\x00extrasq\x06c__builtin__\nset\nq\x07"
    b"]q\x08\x85q\tRq\nX\t\x00\x00\x00specifierq\x0bcpackaging.specifiers\n"
    b"SpecifierSet\nq\x0c)\x81q\rcpackaging.specifiers\nSpecifier\nq\x0e)\x81"
    b"q\x0fX\x02\x00\x00\x00>=q\x10X\x03\x00\x00\x002.0q\x11\x86q\x12N\x86"
    b"q\x13b\x85q\x14N\x86q\x15bX\x06\x00\x00\x00markerq\x16cpackaging."
    b"markers\nMarker\nq\x17)\x81q\x18N}q\x19X\x08\x00\x00\x00_markersq\x1a"
    b"]q\x1bcpackaging._parser\nVariable\nq\x1c)\x81q\x1dN}q\x1eX\x05\x00"
    b"\x00\x00valueq\x1fX\x0e\x00\x00\x00python_versionq s\x86q!b"
    b'cpackaging._parser\nOp\nq")\x81q#N}q$h\x1fX\x02\x00\x00\x00>=q%s'
    b"\x86q&bcpackaging._parser\nValue\nq')\x81q(N}q)h\x1fX\x03\x00\x00"
    b"\x003.8q*s\x86q+b\x87q,as\x86q-bub."
)


# Pickle bytes generated with packaging==26.0, Python 3.13.1, pickle protocol 2.
# Format: plain __dict__ (no __getstate__).
_PACKAGING_26_0_PICKLE_REQUESTS_GE_2_0 = (
    b"\x80\x02cpackaging.requirements\nRequirement\nq\x00)\x81q\x01}q\x02("
    b"X\x04\x00\x00\x00nameq\x03X\x08\x00\x00\x00requestsq\x04X\x03\x00"
    b"\x00\x00urlq\x05NX\x06\x00\x00\x00extrasq\x06c__builtin__\nset\nq\x07"
    b"]q\x08\x85q\tRq\nX\t\x00\x00\x00specifierq\x0bcpackaging.specifiers\n"
    b"SpecifierSet\nq\x0c)\x81q\rN}q\x0e(X\x0c\x00\x00\x00_prereleasesq\x0f"
    b"NX\x06\x00\x00\x00_specsq\x10c__builtin__\nfrozenset\nq\x11]q\x12cpackag"
    b"ing.specifiers\nSpecifier\nq\x13)\x81q\x14N}q\x15(h\x0fNX\x05\x00\x00"
    b"\x00_specq\x16X\x02\x00\x00\x00>=q\x17X\x03\x00\x00\x002.0q\x18\x86q"
    b"\x19X\r\x00\x00\x00_spec_versionq\x1ah\x18cpackaging.version\nVersion\n"
    b"q\x1b)\x81q\x1cN}q\x1d(X\x04\x00\x00\x00_devq\x1eNX\x06\x00\x00\x00_epo"
    b"chq\x1fK\x00X\n\x00\x00\x00_key_cacheq NX\x06\x00\x00\x00_localq!NX\x05"
    b'\x00\x00\x00_postq"NX\x04\x00\x00\x00_preq#NX\x08\x00\x00\x00_releaseq$'
    b"K\x02K\x00\x86q%u\x86q&b\x86q'u\x86q(b"
    b"a\x85q)Rq*u\x86q+bX\x06\x00\x00"
    b"\x00markerq,Nub."
)


# Pickle bytes generated with packaging==25.0, Python 3.13.1, pickle protocol 2.
# Format: plain __dict__ (no __getstate__).
_PACKAGING_25_0_PICKLE_REQUESTS_GE_2_0 = (
    b"\x80\x02cpackaging.requirements\nRequirement\nq\x00)\x81q\x01}q\x02("
    b"X\x04\x00\x00\x00nameq\x03X\x08\x00\x00\x00requestsq\x04X\x03\x00"
    b"\x00\x00urlq\x05NX\x06\x00\x00\x00extrasq\x06c__builtin__\nset\nq\x07"
    b"]q\x08\x85q\tRq\nX\t\x00\x00\x00specifierq\x0bcpackaging.specifiers\n"
    b"SpecifierSet\nq\x0c)\x81q\r}q\x0e(X\x06\x00\x00\x00_specsq\x0fc__bui"
    b"ltin__\nfrozenset\nq\x10]q\x11cpackaging.specifiers\nSpecifier\nq\x12)\x81"
    b"q\x13}q\x14(X\x05\x00\x00\x00_specq\x15X\x02\x00\x00\x00>=q\x16X\x03\x00"
    b"\x00\x002.0q\x17\x86q\x18X\x0c\x00\x00\x00_prereleasesq\x19Nuba\x85q\x1a"
    b"Rq\x1bh\x19NubX\x06\x00\x00\x00markerq\x1cNub."
)


def test_pickle_requirement_old_format_loads() -> None:
    # Verify that Requirement pickles created with packaging <= 26.1 (plain
    # __dict__, no __getstate__) can be loaded and produce correct objects.
    r = pickle.loads(_PACKAGING_26_1_PICKLE_REQUESTS_GE_2_0_WITH_MARKER)
    assert isinstance(r, Requirement)
    assert r.name == "requests"
    assert r.url is None
    assert r.extras == set()
    assert str(r.specifier) == ">=2.0"
    assert r.marker is not None
    assert str(r.marker) == 'python_version >= "3.8"'
    assert r == Requirement('requests>=2.0; python_version >= "3.8"')


def test_pickle_requirement_26_0_format_loads() -> None:
    # Verify that Requirement pickles created with packaging 26.0 (plain __dict__)
    # can be loaded and produce correct objects.
    r = pickle.loads(_PACKAGING_26_0_PICKLE_REQUESTS_GE_2_0)
    assert isinstance(r, Requirement)
    assert r.name == "requests"
    assert r.url is None
    assert r.extras == set()
    assert str(r.specifier) == ">=2.0"
    assert r.marker is None
    assert r == Requirement("requests>=2.0")


def test_pickle_requirement_25_0_format_loads() -> None:
    # Verify that Requirement pickles created with packaging 25.0 (plain __dict__)
    # can be loaded and produce correct objects.
    r = pickle.loads(_PACKAGING_25_0_PICKLE_REQUESTS_GE_2_0)
    assert isinstance(r, Requirement)
    assert r.name == "requests"
    assert r.url is None
    assert r.extras == set()
    assert str(r.specifier) == ">=2.0"
    assert r.marker is None
    assert r == Requirement("requests>=2.0")
