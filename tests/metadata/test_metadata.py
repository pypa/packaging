# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function
from packaging.metadata import Metadata, check_python_compatability
from .test_metadata_constants import (
    VALID_PACKAGE_2_1_RFC822,
    VALID_PACKAGE_2_1_JSON,
    VALID_PACKAGE_2_1_DICT,
    VALID_PACKAGE_1_0_RFC822,
    VALID_PACKAGE_1_0_DICT,
    VALID_PACKAGE_1_0_JSON,
    VALID_PACKAGE_1_1_RFC822,
    VALID_PACKAGE_1_1_DICT,
    VALID_PACKAGE_1_1_JSON,
    VALID_PACKAGE_1_2_RFC822,
    VALID_PACKAGE_1_2_DICT,
    VALID_PACKAGE_1_2_JSON,
    VALID_PACKAGE_1_0_REPEATED_DESC,
    VALID_PACKAGE_1_0_SINGLE_LINE_DESC,
)

import pytest
import sys


class TestMetaData:
    def test_kwargs_init(self):
        metadata = Metadata(
            name="foo",
            version="1.0",
            keywords=["a", "b", "c"],
            description="Hello\nworld",
        )
        assert metadata._meta_dict == {
            "name": "foo",
            "version": "1.0",
            "keywords": ["a", "b", "c"],
            "description": "Hello\nworld",
        }

    @pytest.mark.parametrize(
        ("metadata_dict", "metadata_json"),
        [
            (VALID_PACKAGE_2_1_DICT, VALID_PACKAGE_2_1_JSON),
            (VALID_PACKAGE_1_0_DICT, VALID_PACKAGE_1_0_JSON),
            (VALID_PACKAGE_1_1_DICT, VALID_PACKAGE_1_1_JSON),
            (VALID_PACKAGE_1_2_DICT, VALID_PACKAGE_1_2_JSON),
        ],
    )
    def test_from_json(self, metadata_dict, metadata_json):
        metadata_1 = Metadata(**metadata_dict)
        metadata_2 = Metadata.from_json(metadata_json)

        assert metadata_1 == metadata_2

    @pytest.mark.parametrize(
        ("metadata_dict", "metadata_rfc822"),
        [
            (VALID_PACKAGE_2_1_DICT, VALID_PACKAGE_2_1_RFC822),
            (VALID_PACKAGE_1_0_DICT, VALID_PACKAGE_1_0_RFC822),
            (VALID_PACKAGE_1_1_DICT, VALID_PACKAGE_1_1_RFC822),
            (VALID_PACKAGE_1_2_DICT, VALID_PACKAGE_1_2_RFC822),
        ],
    )
    def test_from_rfc822(self, metadata_dict, metadata_rfc822):
        metadata_1 = Metadata(**metadata_dict)
        metadata_2 = Metadata.from_rfc822(metadata_rfc822)

        assert metadata_1 == metadata_2

    @pytest.mark.parametrize(
        ("metadata_dict", "metadata_json"),
        [
            (VALID_PACKAGE_2_1_DICT, VALID_PACKAGE_2_1_JSON),
            (VALID_PACKAGE_1_0_DICT, VALID_PACKAGE_1_0_JSON),
            (VALID_PACKAGE_1_1_DICT, VALID_PACKAGE_1_1_JSON),
            (VALID_PACKAGE_1_2_DICT, VALID_PACKAGE_1_2_JSON),
        ],
    )
    def test_from_dict(self, metadata_dict, metadata_json):
        metadata_1 = Metadata.from_dict(metadata_dict)
        metadata_2 = Metadata.from_json(metadata_json)

        assert metadata_1 == metadata_2

    @pytest.mark.parametrize(
        ("expected_json_string", "input_dict"),
        [
            (VALID_PACKAGE_1_2_JSON, VALID_PACKAGE_1_2_DICT),
            (VALID_PACKAGE_1_0_JSON, VALID_PACKAGE_1_0_DICT),
            (VALID_PACKAGE_1_1_JSON, VALID_PACKAGE_1_1_DICT),
            (VALID_PACKAGE_2_1_JSON, VALID_PACKAGE_2_1_DICT),
        ],
    )
    def test_to_json(self, expected_json_string, input_dict):
        metadata_1 = Metadata(**input_dict)
        generated_json_string = metadata_1.to_json()

        assert expected_json_string == generated_json_string

    @pytest.mark.parametrize(
        ("expected_rfc822_string", "input_dict"),
        [
            (VALID_PACKAGE_2_1_RFC822, VALID_PACKAGE_2_1_DICT),
            (VALID_PACKAGE_1_0_RFC822, VALID_PACKAGE_1_0_DICT),
            (VALID_PACKAGE_1_1_RFC822, VALID_PACKAGE_1_1_DICT),
            (VALID_PACKAGE_1_2_RFC822, VALID_PACKAGE_1_2_DICT),
        ],
    )
    def test_to_rfc822(self, expected_rfc822_string, input_dict):
        metadata_1 = Metadata(**input_dict)
        generated_rfc822_string = metadata_1.to_rfc822()

        assert (
            Metadata.from_rfc822(generated_rfc822_string).to_dict()
            == Metadata.from_rfc822(expected_rfc822_string).to_dict()
        )
        assert TestMetaData._compare_rfc822_strings(
            expected_rfc822_string, generated_rfc822_string
        )

    @pytest.mark.parametrize(
        "expected_dict",
        [
            VALID_PACKAGE_1_2_DICT,
            VALID_PACKAGE_1_0_DICT,
            VALID_PACKAGE_1_1_DICT,
            VALID_PACKAGE_2_1_DICT,
        ],
    )
    def test_to_dict(self, expected_dict):
        metadata_1 = Metadata(**expected_dict)
        generated_dict = metadata_1.to_dict()

        assert expected_dict == generated_dict

    def test_metadata_iter(self):
        metadata_1 = Metadata(
            name="foo",
            version="1.0",
            keywords=["a", "b", "c"],
            description="Hello\nworld",
        )

        for key, value in metadata_1.__iter__():
            assert key in metadata_1._meta_dict
            assert metadata_1._meta_dict[key] == value

    def test_repeated_description_in_rfc822(self):
        metadata_1 = Metadata.from_rfc822(VALID_PACKAGE_1_0_REPEATED_DESC)
        expected_description = (
            "# This is the long description\n\n"
            + "This will overwrite the Description field\n"
        )

        assert metadata_1._meta_dict["description"] == expected_description

    def test_single_line_description_in_rfc822(self):
        metdata_1 = Metadata.from_rfc822(VALID_PACKAGE_1_0_SINGLE_LINE_DESC)

        description = metdata_1._meta_dict["description"]

        assert len(description.splitlines()) == 1

    def test_metadata_validation(self):
        # Validation not currently implemented
        with pytest.raises(NotImplementedError):
            metadata = Metadata(
                name="foo",
                version="1.0",
                keywords=["a", "b", "c"],
                description="Hello\nworld",
            )
            metadata.validate()

    def test_metadata_equals_different_order(self):
        metadata_1 = Metadata(
            name="foo",
            version="1.0",
            keywords=["a", "b", "c"],
            description="Hello\nworld",
        )
        metadata_2 = Metadata(
            version="1.0",
            keywords=["a", "b", "c"],
            description="Hello\nworld",
            name="foo",
        )

        assert metadata_1 == metadata_2

    def test_metadata_equals_non_metadata(self):
        metadata_1 = Metadata(
            name="foo",
            version="1.0",
            keywords=["a", "b", "c"],
            description="Hello\nworld",
        )
        assert (
            metadata_1.__eq__(
                {
                    "name": "foo",
                    "version": "1.0",
                    "keywords": ["a", "b", "c"],
                    "description": "Hello\nworld",
                }
            )
            == NotImplemented
        )

    def test_raise_when_python2(self, monkeypatch):
        with pytest.raises(ModuleNotFoundError):
            monkeypatch.setattr(sys, "version_info", (2, 0))
            check_python_compatability()

    @classmethod
    def _compare_rfc822_strings(cls, rfc822_1, rfc822_2):

        rfc822_1_dict = Metadata.from_rfc822(rfc822_1).to_dict()
        rfc822_2_dict = Metadata.from_rfc822(rfc822_2).to_dict()

        return rfc822_1_dict == rfc822_2_dict
