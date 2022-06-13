import pytest

from packaging import metadata, utils, version


class TestInit:
    def test_defaults(self):
        specified_attributes = {"display_name", "canonical_name", "version"}
        metadata_ = metadata.Metadata("packaging", version.Version("2023.0.0"))
        for attr in dir(metadata_):
            if attr in specified_attributes or attr.startswith("_"):
                continue
            assert not getattr(metadata_, attr)


class TestNameNormalization:

    version = version.Version("1.0.0")
    display_name = "A--B"
    canonical_name = utils.canonicalize_name(display_name)

    def test_via_init(self):
        metadata_ = metadata.Metadata(self.display_name, self.version)

        assert metadata_.display_name == self.display_name
        assert metadata_.canonical_name == self.canonical_name

    def test_via_display_name_setter(self):
        metadata_ = metadata.Metadata("a", self.version)

        assert metadata_.display_name == "a"
        assert metadata_.canonical_name == "a"

        metadata_.display_name = self.display_name

        assert metadata_.display_name == self.display_name
        assert metadata_.canonical_name == self.canonical_name

    def test_no_canonical_name_setter(self):
        metadata_ = metadata.Metadata("a", self.version)

        with pytest.raises(AttributeError):
            metadata_.canonical_name = "b"  # type: ignore
