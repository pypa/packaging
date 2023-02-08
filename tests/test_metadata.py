import pathlib

import pytest

from packaging import metadata, utils, version


class TestRawMetadata:
    @pytest.mark.parametrize("raw_field", metadata._STRING_FIELDS)
    def test_non_repeating_fields_only_once(self, raw_field: set[str]):
        data = "VaLuE"
        header_field = metadata._RAW_TO_EMAIL_MAPPING[raw_field]
        single_header = f"{header_field}: {data}"
        raw, unparsed = metadata.parse_email(single_header)
        assert not unparsed
        assert len(raw) == 1
        assert raw_field in raw
        assert raw[raw_field] == data

    @pytest.mark.parametrize("raw_field", metadata._STRING_FIELDS)
    def test_non_repeating_fields_repeated(self, raw_field: set[str]):
        header_field = metadata._RAW_TO_EMAIL_MAPPING[raw_field]
        data = "VaLuE"
        single_header = f"{header_field}: {data}"
        repeated_header = "\n".join([single_header] * 2)
        raw, unparsed = metadata.parse_email(repeated_header)
        assert not raw
        assert len(unparsed) == 1
        assert header_field in unparsed
        assert unparsed[header_field] == [data] * 2

    @pytest.mark.parametrize("raw_field", metadata._LIST_STRING_FIELDS)
    def test_repeating_fields_only_once(self, raw_field: set[str]):
        data = "VaLuE"
        header_field = metadata._RAW_TO_EMAIL_MAPPING[raw_field]
        single_header = f"{header_field}: {data}"
        raw, unparsed = metadata.parse_email(single_header)
        assert not unparsed
        assert len(raw) == 1
        assert raw_field in raw
        assert raw[raw_field] == [data]

    @pytest.mark.parametrize("raw_field", metadata._LIST_STRING_FIELDS)
    def test_repeating_fields_repeated(self, raw_field: set[str]):
        header_field = metadata._RAW_TO_EMAIL_MAPPING[raw_field]
        data = "VaLuE"
        single_header = f"{header_field}: {data}"
        repeated_header = "\n".join([single_header] * 2)
        raw, unparsed = metadata.parse_email(repeated_header)
        assert not unparsed
        assert len(raw) == 1
        assert raw_field in raw
        assert raw[raw_field] == [data] * 2

    @pytest.mark.parametrize(
        ["given", "expected"],
        [
            ("A", ["A"]),
            ("A ", ["A"]),
            (" A", ["A"]),
            ("A, B", ["A", "B"]),
            ("A,B", ["A", "B"]),
            (" A, B", ["A", "B"]),
            ("A,B ", ["A", "B"]),
            ("A B", ["A B"]),
        ],
    )
    def test_keywords(self, given, expected):
        header = f"Keywords: {given}"
        raw, unparsed = metadata.parse_email(header)
        assert not unparsed
        assert len(raw) == 1
        assert "keywords" in raw
        assert raw["keywords"] == expected

    @pytest.mark.parametrize(
        ["given", "expected"],
        [
            ("", {"": ""}),
            ("A", {"A": ""}),
            ("A,B", {"A": "B"}),
            ("A, B", {"A": "B"}),
            (" A,B", {"A": "B"}),
            ("A,B ", {"A": "B"}),
            ("A,B,C", {"A": "B,C"}),
        ],
    )
    def test_project_urls_parsing(self, given, expected):
        header = f"project-url: {given}"
        raw, unparsed = metadata.parse_email(header)
        assert not unparsed
        assert len(raw) == 1
        assert "project_urls" in raw
        assert raw["project_urls"] == expected

    def test_duplicate_project_urls(self):
        header = "project-url: A, B\nproject-url: A, C"
        raw, unparsed = metadata.parse_email(header)
        assert not raw
        assert len(unparsed) == 1
        assert "project-url" in unparsed
        assert unparsed["project-url"] == ["A, B", "A, C"]

    def test_str_input(self):
        name = "Tarek Ziadé"
        header = f"author: {name}"
        raw, unparsed = metadata.parse_email(header)
        assert not unparsed
        assert len(raw) == 1
        assert "author" in raw
        assert raw["author"] == name

    def test_bytes_input(self):
        name = "Tarek Ziadé"
        header = f"author: {name}".encode()
        raw, unparsed = metadata.parse_email(header)
        assert not unparsed
        assert len(raw) == 1
        assert "author" in raw
        assert raw["author"] == name

    def test_header_mojibake(self):
        value = "\xc0msterdam"
        header_name = "value"
        header_bytes = f"{header_name}: {value}".encode("latin1")
        raw, unparsed = metadata.parse_email(header_bytes)
        # Sanity check
        with pytest.raises(UnicodeDecodeError):
            header_bytes.decode("utf-8")
        assert not raw
        assert len(unparsed) == 1
        assert header_name in unparsed
        assert unparsed[header_name] == [value]

    @pytest.mark.parametrize(
        ["given"], [("hello",), ("description: hello",), (b"hello",)]
    )
    def test_description(self, given):
        raw, unparsed = metadata.parse_email(given)
        assert not unparsed
        assert len(raw) == 1
        assert "description" in raw
        assert raw["description"] == "hello"

    def test_description_non_utf8(self):
        header = "\xc0msterdam"
        header_bytes = header.encode("latin1")
        raw, unparsed = metadata.parse_email(header_bytes)
        assert not raw
        assert len(unparsed) == 1
        assert "description" in unparsed
        assert unparsed["description"] == [header_bytes]

    @pytest.mark.parametrize(
        ["given", "expected"],
        [
            ("description: 1\ndescription: 2", ["1", "2"]),
            ("description: 1\n\n2", ["1", "2"]),
            ("description: 1\ndescription: 2\n\n3", ["1", "2", "3"]),
        ],
    )
    def test_description_multiple(self, given, expected):
        raw, unparsed = metadata.parse_email(given)
        assert not raw
        assert len(unparsed) == 1
        assert "description" in unparsed
        assert unparsed["description"] == expected

    def test_lowercase_keys(self):
        header = "AUTHOR: Tarek Ziadé\nWhatever: Else"
        raw, unparsed = metadata.parse_email(header)
        assert len(raw) == 1
        assert "author" in raw
        assert len(unparsed) == 1
        assert "whatever" in unparsed

    def test_complete(self):
        """Test all fields (except `Obsoletes-Dist`).

        `Obsoletes-Dist` was sacrificed to provide a value for `Dynamic`.
        """
        path = pathlib.Path(__file__).parent / "metadata" / "everything.metadata"
        with path.open("r", encoding="utf-8") as file:
            metadata_contents = file.read()
        raw, unparsed = metadata.parse_email(metadata_contents)
        assert len(unparsed) == 1
        assert unparsed["thisisnotreal"] == ["Hello!"]
        assert len(raw) == 24
        assert raw["metadata_version"] == "2.3"
        assert raw["name"] == "BeagleVote"
        assert raw["version"] == "1.0a2"
        assert raw["platforms"] == ["ObscureUnix", "RareDOS"]
        assert raw["supported_platforms"] == ["RedHat 7.2", "i386-win32-2791"]
        assert raw["summary"] == "A module for collecting votes from beagles."
        assert (
            raw["description_content_type"]
            == "text/markdown; charset=UTF-8; variant=GFM"
        )
        assert raw["keywords"] == ["dog", "puppy", "voting", "election"]
        assert raw["home_page"] == "http://www.example.com/~cschultz/bvote/"
        assert raw["download_url"] == "…/BeagleVote-0.45.tgz"
        assert raw["author"] == (
            "C. Schultz, Universal Features Syndicate,\n"
            "        Los Angeles, CA <cschultz@peanuts.example.com>"
        )
        assert raw["author_email"] == '"C. Schultz" <cschultz@example.com>'
        assert raw["maintainer"] == (
            "C. Schultz, Universal Features Syndicate,\n"
            "        Los Angeles, CA <cschultz@peanuts.example.com>"
        )
        assert raw["maintainer_email"] == '"C. Schultz" <cschultz@example.com>'
        assert raw["license"] == (
            "This software may only be obtained by sending the\n"
            "        author a postcard, and then the user promises not\n"
            "        to redistribute it."
        )
        assert raw["classifiers"] == [
            "Development Status :: 4 - Beta",
            "Environment :: Console (Text Based)",
        ]
        assert raw["provides_extra"] == ["pdf"]
        assert raw["requires_dist"] == [
            "reportlab; extra == 'pdf'",
            "pkginfo",
            "PasteDeploy",
            "zope.interface (>3.5.0)",
            "pywin32 >1.0; sys_platform == 'win32'",
        ]
        assert raw["requires_python"] == ">=3"
        assert raw["requires_external"] == [
            "C",
            "libpng (>=1.5)",
            'make; sys_platform != "win32"',
        ]
        assert raw["project_urls"] == {
            "Bug Tracker": "http://bitbucket.org/tarek/distribute/issues/",
            "Documentation": "https://example.com/BeagleVote",
        }
        assert raw["provides_dist"] == [
            "OtherProject",
            "AnotherProject (3.4)",
            'virtual_package; python_version >= "3.4"',
        ]
        assert raw["dynamic"] == ["Obsoletes-Dist"]
        assert raw["description"] == "This description intentionally left blank.\n"


class TestMetadata:
    def test_valid_version(self):
        version_str = "1.2.3"
        meta = metadata.Metadata.from_email(f"Version: {version_str}")
        assert meta.version == version.parse(version_str)

    def test_missing_version(self):
        meta = metadata.Metadata.from_email("")
        with pytest.raises(metadata.InvalidMetadata) as exc_info:
            meta.version
        assert exc_info.value.field == "version"

    def test_invalid_version(self):
        meta = metadata.Metadata.from_email("Version: a.b.c")
        with pytest.raises(version.InvalidVersion):
            meta.version

    def test_valid_summary(self):
        summary = "Hello"
        meta = metadata.Metadata.from_email(f"Summary: {summary}")
        assert meta.summary == summary

    def test_invalid_summary(self):
        summary = "Hello"
        meta = metadata.Metadata.from_email(f"Summary: {summary}\n    Again")
        with pytest.raises(metadata.InvalidMetadata) as exc_info:
            meta.summary
        assert exc_info.value.field == "summary"

    def test_valid_name(self):
        name = "Hello_World"
        meta = metadata.Metadata.from_email(f"Name: {name}")
        assert meta.name == utils.canonicalize_name(name)

    def test_invalid_name(self):
        name = "-not-legal"
        meta = metadata.Metadata.from_email(f"Name: {name}")
        with pytest.raises(utils.InvalidName):
            meta.name

    def test_supported_platforms(self):
        platform1 = "RedHat 7.2"
        platform2 = "i386-win32-2791"
        meta = metadata.Metadata.from_email(
            f"Supported-Platform: {platform1}\nSupported-Platform: {platform2}"
        )
        assert meta.supported_platforms == [platform1, platform2]

    def test_platforms(self):
        platform1 = "ObscureUnix"
        platform2 = "RareDOS"
        meta = metadata.Metadata.from_email(
            f"Platform: {platform1}\nPlatform: {platform2}"
        )
        assert meta.platforms == [platform1, platform2]
