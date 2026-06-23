#!/usr/bin/env python3
"""Benchmark script that validates the packaging library's API surface.

Outputs JSON: {"score": <0.0-1.0>}
"""

import json
import sys
import traceback


def test_parse_email():
    from packaging.metadata import parse_email

    raw_meta = (
        "Metadata-Version: 2.1\n"
        "Name: test-pkg\n"
        "Version: 1.0.0\n"
        "Summary: A test package\n"
        "Author: Test Author\n"
    )
    raw, unparsed = parse_email(raw_meta)
    assert raw["name"] == "test-pkg", f"Expected 'test-pkg', got {raw['name']!r}"
    assert raw["version"] == "1.0.0", f"Expected '1.0.0', got {raw['version']!r}"
    assert raw["summary"] == "A test package"
    assert raw["author"] == "Test Author"


def test_metadata_round_trip():
    from packaging.metadata import Metadata, parse_email

    raw_meta = (
        "Metadata-Version: 2.1\n"
        "Name: roundtrip-pkg\n"
        "Version: 2.3.4\n"
        "Summary: Round-trip test\n"
    )
    raw, _ = parse_email(raw_meta)
    metadata = Metadata.from_raw(raw, validate=True)
    assert metadata.name == "roundtrip-pkg"
    assert str(metadata.version) == "2.3.4"

    rfc822 = metadata.as_rfc822()
    serialized = str(rfc822)
    assert "roundtrip-pkg" in serialized
    assert "2.3.4" in serialized


def test_metadata_validation():
    from packaging.metadata import Metadata
    from packaging.errors import ExceptionGroup

    invalid_raw = {
        "metadata_version": "2.1",
        "name": "valid-name",
        "version": "not_a_valid_version!!!",
    }
    try:
        Metadata.from_raw(invalid_raw, validate=True)
        raise AssertionError("Expected ExceptionGroup for invalid metadata")
    except ExceptionGroup:
        pass


def test_requirement_parsing():
    from packaging.requirements import Requirement

    req = Requirement("requests>=2.0,<3.0")
    assert req.name == "requests"
    assert ">=2.0" in str(req.specifier)
    assert req.extras == set()

    req_extras = Requirement("pkg[extra1,extra2]>=1.0")
    assert req_extras.name == "pkg"
    assert "extra1" in req_extras.extras
    assert "extra2" in req_extras.extras
    assert req_extras.specifier is not None


def test_version_parsing():
    from packaging.version import Version

    v1 = Version("1.0")
    v2 = Version("2.0")
    assert v1 < v2

    v_pre = Version("1.0a1")
    v_release = Version("1.0")
    assert v_pre < v_release
    assert v_pre.is_prerelease

    v = Version("3.2.1")
    assert v.major == 3
    assert v.minor == 2
    assert v.micro == 1


def test_specifier_set():
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    spec = SpecifierSet(">=1.0,<2.0")
    assert spec.contains("1.5")
    assert not spec.contains("2.0")
    assert not spec.contains("0.9")

    assert "1.5" in spec
    assert "2.0" not in spec

    v = Version("1.5")
    assert spec.contains(v)


def test_marker_evaluation():
    from packaging.markers import Marker, default_environment

    env = default_environment()
    marker = Marker('python_version >= "3.0"')
    assert marker.evaluate() is True

    marker_false = Marker('python_version < "2.0"')
    assert marker_false.evaluate() is False


def test_rfc822_as_bytes():
    from packaging.metadata import Metadata, parse_email

    raw_meta = (
        "Metadata-Version: 2.1\n"
        "Name: bytes-test\n"
        "Version: 1.0.0\n"
    )
    raw, _ = parse_email(raw_meta)
    metadata = Metadata.from_raw(raw, validate=True)
    rfc822 = metadata.as_rfc822()
    result = rfc822.as_bytes()
    assert isinstance(result, bytes)
    assert b"bytes-test" in result


def test_exception_group():
    from packaging.errors import ExceptionGroup

    exc1 = ValueError("error 1")
    exc2 = TypeError("error 2")
    group = ExceptionGroup("test errors", [exc1, exc2])
    assert group.message == "test errors"
    assert len(group.exceptions) == 2
    r = repr(group)
    assert "test errors" in r


TESTS = [
    ("parse_email", test_parse_email),
    ("metadata_round_trip", test_metadata_round_trip),
    ("metadata_validation", test_metadata_validation),
    ("requirement_parsing", test_requirement_parsing),
    ("version_parsing", test_version_parsing),
    ("specifier_set", test_specifier_set),
    ("marker_evaluation", test_marker_evaluation),
    ("rfc822_as_bytes", test_rfc822_as_bytes),
    ("exception_group", test_exception_group),
]


def main():
    passed = 0
    total = len(TESTS)

    for name, fn in TESTS:
        try:
            fn()
            passed += 1
        except Exception:
            print(f"FAIL: {name}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    score = passed / total if total > 0 else 0.0
    json.dump({"score": score}, sys.stdout)
    print()


if __name__ == "__main__":
    main()
