import pytest
from packaging import metadata

_RAW_TO_EMAIL_MAPPING = {
    raw: email for email, raw in metadata._EMAIL_TO_RAW_MAPPING.items()
}


class TestRawMetadata:
    @pytest.mark.parametrize("raw_field", metadata._STRING_FIELDS)
    def test_non_repeating_fields_only_once(self, raw_field):
        data = "VaLuE"
        header_field = _RAW_TO_EMAIL_MAPPING[raw_field]
        single_header = f"{header_field}: {data}"
        raw, unparsed = metadata.parse_email(single_header)
        assert not unparsed
        assert len(raw) == 1
        assert raw_field in raw
        assert raw[raw_field] == data

    @pytest.mark.parametrize("raw_field", metadata._STRING_FIELDS)
    def test_non_repeating_fields_repeated(self, raw_field):
        header_field = _RAW_TO_EMAIL_MAPPING[raw_field]
        data = "VaLuE"
        single_header = f"{header_field}: {data}"
        repeated_header = "\n".join([single_header] * 2)
        raw, unparsed = metadata.parse_email(repeated_header)
        assert not raw
        assert len(unparsed) == 1
        assert header_field in unparsed
        assert unparsed[header_field] == [data] * 2

    @pytest.mark.parametrize("raw_field", metadata._LIST_STRING_FIELDS)
    def test_repeating_fields_only_once(self, raw_field):
        data = "VaLuE"
        header_field = _RAW_TO_EMAIL_MAPPING[raw_field]
        single_header = f"{header_field}: {data}"
        raw, unparsed = metadata.parse_email(single_header)
        assert not unparsed
        assert len(raw) == 1
        assert raw_field in raw
        assert raw[raw_field] == [data]

    @pytest.mark.parametrize("raw_field", metadata._LIST_STRING_FIELDS)
    def test_repeating_fields_repeated(self, raw_field):
        header_field = _RAW_TO_EMAIL_MAPPING[raw_field]
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
        header = f"author: {name}".encode("utf-8")
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
        ["given"], [("hello",), ("description: hello",), ("hello".encode("utf-8"),)]
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


# A single, exhaustive test of every field
