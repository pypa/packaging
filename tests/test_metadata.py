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
