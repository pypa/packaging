# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import pytest

from packaging.markers import Marker
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet


class TestRequirements:
    def test_string_specifier_marker(self):
        requirement = 'name[bar]>=3; python_version == "2.7"'
        req = Requirement(requirement)
        assert str(req) == requirement

    def test_string_url(self):
        requirement = "name@ http://foo.com"
        req = Requirement(requirement)
        assert str(req) == requirement

    def test_string_url_with_marker(self):
        requirement = 'name@ http://foo.com ; extra == "feature"'
        req = Requirement(requirement)
        assert str(req) == requirement

    def test_repr(self):
        req = Requirement("name")
        assert repr(req) == "<Requirement('name')>"

    def test_installer(self):
        req = Requirement("installer")
        assert repr(req) == "<Requirement('installer')>"

    def test_notabene(self):
        req = Requirement("notabene")
        assert repr(req) == "<Requirement('notabene')>"

    def test_andor(self):
        req = Requirement("andor")
        assert repr(req) == "<Requirement('andor')>"

    def test_orator(self):
        req = Requirement("orator")
        assert repr(req) == "<Requirement('orator')>"

    def test_extractor(self):
        req = Requirement("extractor")
        assert repr(req) == "<Requirement('extractor')>"

    def test_a0(self):
        req = Requirement("a0")
        assert repr(req) == "<Requirement('a0')>"

    def test_v1(self):
        req = Requirement("v1")
        assert repr(req) == "<Requirement('v1')>"

    def test_trailing_space(self):
        req = Requirement("a ")
        assert repr(req) == "<Requirement('a')>"

    def test_preceeding_space(self):
        req = Requirement(" a")
        assert repr(req) == "<Requirement('a')>"

    def _assert_requirement(
        self, req, name, url=None, extras=[], specifier="", marker=None
    ):
        assert req.name == name
        assert req.url == url
        assert sorted(req.extras) == sorted(extras)
        assert str(req.specifier) == specifier
        if marker:
            assert str(req.marker) == marker
        else:
            assert req.marker is None

    def test_simple_names(self):
        for name in ("A", "aa", "name"):
            req = Requirement(name)
            self._assert_requirement(req, name)

    def test_name_with_other_characters(self):
        name = "foo-bar.quux_baz"
        req = Requirement(name)
        self._assert_requirement(req, name)

    def test_invalid_name(self):
        with pytest.raises(InvalidRequirement):
            Requirement("foo!")

    def test_name_with_version(self):
        req = Requirement("name>=3")
        self._assert_requirement(req, "name", specifier=">=3")

    def test_with_legacy_version(self):
        with pytest.raises(InvalidRequirement) as e:
            Requirement("name==1.0.org1")
        assert "Expected semicolon (followed by markers) or end of string" in str(e)

    def test_with_legacy_version_and_marker(self):
        with pytest.raises(InvalidRequirement) as e:
            Requirement("name>=1.x.y;python_version=='2.6'")
        assert "Expected semicolon (followed by markers) or end of string" in str(e)

    def test_missing_name(self):
        with pytest.raises(InvalidRequirement) as e:
            Requirement("@ http://example.com")
        assert "Expression must begin with package name" in str(e)

    def test_name_with_missing_version(self):
        with pytest.raises(InvalidRequirement) as e:
            Requirement("name>=")
        assert "Missing version" in str(e)

    def test_version_with_parens_and_whitespace(self):
        req = Requirement("name (==4)")
        self._assert_requirement(req, "name", specifier="==4")

    def test_version_with_missing_closing_paren(self):
        with pytest.raises(InvalidRequirement) as e:
            Requirement("name(==4")
        assert "Closing right parenthesis is missing" in str(e)

    def test_name_with_multiple_versions(self):
        req = Requirement("name>=3,<2")
        self._assert_requirement(req, "name", specifier="<2,>=3")

    def test_name_with_multiple_versions_and_whitespace(self):
        req = Requirement("name >=2, <3")
        self._assert_requirement(req, "name", specifier="<3,>=2")

    def test_name_with_multiple_versions_in_parenthesis(self):
        req = Requirement("name (>=2,<3)")
        self._assert_requirement(req, "name", specifier="<3,>=2")

    def test_name_with_no_extras_no_versions_in_parenthesis(self):
        req = Requirement("name []()")
        self._assert_requirement(req, "name", specifier="", extras=[])

    def test_name_with_extra_and_multiple_versions_in_parenthesis(self):
        req = Requirement("name [foo, bar](>=2,<3)")
        self._assert_requirement(req, "name", specifier="<3,>=2", extras=["foo", "bar"])

    def test_name_with_no_versions_in_parenthesis(self):
        req = Requirement("name ()")
        self._assert_requirement(req, "name", specifier="")

    def test_extras(self):
        req = Requirement("foobar [quux,bar]")
        self._assert_requirement(req, "foobar", extras=["bar", "quux"])

    def test_empty_extras(self):
        req = Requirement("foo[]")
        self._assert_requirement(req, "foo")

    def test_unclosed_extras(self):
        with pytest.raises(InvalidRequirement) as e:
            Requirement("foo[")
        assert "Closing square bracket is missing" in str(e)

    def test_extras_without_comma(self):
        with pytest.raises(InvalidRequirement) as e:
            Requirement("foobar[quux bar]")
        assert "Missing comma after extra" in str(e)

    def test_url(self):
        url_section = "test @ http://example.com"
        req = Requirement(url_section)
        self._assert_requirement(req, "test", "http://example.com", extras=[])

    def test_url_and_marker(self):
        instring = "test @ http://example.com ; os_name=='a'"
        req = Requirement(instring)
        self._assert_requirement(
            req, "test", "http://example.com", extras=[], marker='os_name == "a"'
        )

    def test_invalid_url(self):
        with pytest.raises(InvalidRequirement) as e:
            Requirement("name @ gopher:/foo/com")
        assert "Invalid URL: " in str(e.value)
        assert "gopher:/foo/com" in str(e.value)

    def test_file_url(self):
        req = Requirement("name @ file:///absolute/path")
        self._assert_requirement(req, "name", "file:///absolute/path")
        req = Requirement("name @ file://.")
        self._assert_requirement(req, "name", "file://.")

    def test_invalid_file_urls(self):
        with pytest.raises(InvalidRequirement):
            Requirement("name @ file:.")
        with pytest.raises(InvalidRequirement):
            Requirement("name @ file:/.")

    def test_extras_and_url_and_marker(self):
        req = Requirement("name [fred,bar] @ http://foo.com ; python_version=='2.7'")
        self._assert_requirement(
            req,
            "name",
            extras=["bar", "fred"],
            url="http://foo.com",
            marker='python_version == "2.7"',
        )

    def test_complex_url_and_marker(self):
        url = "https://example.com/name;v=1.1/?query=foo&bar=baz#blah"
        req = Requirement("foo @ %s ; python_version=='3.4'" % url)
        self._assert_requirement(req, "foo", url=url, marker='python_version == "3.4"')

    def test_multiple_markers(self):
        req = Requirement(
            "name[quux, strange];python_version<'2.7' and " "platform_version=='2'"
        )
        marker = 'python_version < "2.7" and platform_version == "2"'
        self._assert_requirement(req, "name", extras=["strange", "quux"], marker=marker)

    def test_multiple_comparison_markers(self):
        req = Requirement("name; os_name=='a' and os_name=='b' or os_name=='c'")
        marker = 'os_name == "a" and os_name == "b" or os_name == "c"'
        self._assert_requirement(req, "name", marker=marker)

    def test_invalid_marker(self):
        with pytest.raises(InvalidRequirement):
            Requirement("name; foobar=='x'")

    def test_marker_with_missing_semicolon(self):
        with pytest.raises(InvalidRequirement) as e:
            Requirement('name[bar]>=3 python_version == "2.7"')
        assert "Expected semicolon (followed by markers) or end of string" in str(e)

    def test_types(self):
        req = Requirement("foobar[quux]<2,>=3; os_name=='a'")
        assert isinstance(req.name, str)
        assert isinstance(req.extras, set)
        assert req.url is None
        assert isinstance(req.specifier, SpecifierSet)
        assert isinstance(req.marker, Marker)

    def test_types_with_nothing(self):
        req = Requirement("foobar")
        assert isinstance(req.name, str)
        assert isinstance(req.extras, set)
        assert req.url is None
        assert isinstance(req.specifier, SpecifierSet)
        assert req.marker is None

    def test_types_with_url(self):
        req = Requirement("foobar @ http://foo.com")
        assert isinstance(req.name, str)
        assert isinstance(req.extras, set)
        assert isinstance(req.url, str)
        assert isinstance(req.specifier, SpecifierSet)
        assert req.marker is None

    def test_sys_platform_linux_equal(self):
        req = Requirement('something>=1.2.3; sys_platform == "foo"')

        assert req.name == "something"
        assert req.marker is not None
        assert req.marker.evaluate(dict(sys_platform="foo")) is True
        assert req.marker.evaluate(dict(sys_platform="bar")) is False

    def test_sys_platform_linux_in(self):
        req = Requirement("aviato>=1.2.3; 'f' in sys_platform")

        assert req.name == "aviato"
        assert req.marker is not None
        assert req.marker.evaluate(dict(sys_platform="foo")) is True
        assert req.marker.evaluate(dict(sys_platform="bar")) is False

    def test_parseexception_error_msg(self):
        with pytest.raises(InvalidRequirement) as e:
            Requirement("toto 42")
        assert "Expected semicolon (followed by markers) or end of string" in str(e)

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

    DIFFERENT_DEPENDENCIES = [
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

    @pytest.mark.parametrize("dep1, dep2", EQUAL_DEPENDENCIES)
    def test_equal_reqs_equal_hashes(self, dep1, dep2):
        # Requirement objects created from equivalent strings should be equal.
        req1, req2 = Requirement(dep1), Requirement(dep2)
        assert req1 == req2
        # Equal Requirement objects should have the same hash.
        assert hash(req1) == hash(req2)

    @pytest.mark.parametrize("dep1, dep2", DIFFERENT_DEPENDENCIES)
    def test_different_reqs_different_hashes(self, dep1, dep2):
        # Requirement objects created from non-equivalent strings should differ.
        req1, req2 = Requirement(dep1), Requirement(dep2)
        assert req1 != req2
        # Different Requirement objects should have different hashes.
        assert hash(req1) != hash(req2)

    def test_compare_reqs_to_other_objects(self):
        # Requirement objects should not be comparable to other kinds of objects.
        assert Requirement("packaging>=21.3") != "packaging>=21.3"
