from __future__ import annotations

from pathlib import Path

from packaging.specifiers import Specifier, SpecifierSet
from packaging.version import Version

from . import add_attributes

DIR = Path(__file__).parent.resolve()


class TimeSpecSuite:
    rounds = 4

    SIMPLE_SPEC = ">0.5"
    COMPLEX_SPEC = ">=3.8,!=3.9.*,!=3.10.0,!=3.10.1,~=3.10.2,<3.14,!=3.11.0,!=3.12.0"
    COMPATIBLE_SPEC = "~=3.10"

    def setup(self) -> None:
        with (DIR / "specs_sample.txt").open() as f:
            self.spec_strs = [s.strip() for s in f.readlines()]

        # Build and warm versions
        self.single_version = Version("3.12")
        self.simple_versions = [Version(str(i / 10)) for i in range(1, 11)]
        self.complex_versions = [
            Version(f"3.{minor}.{patch}")
            for minor in range(8, 15)
            for patch in range(15)
        ]
        self.single_version._key  # noqa: B018
        for v in self.simple_versions:
            v._key  # noqa: B018
        for v in self.complex_versions:
            v._key  # noqa: B018

        # Build cold specifiers
        self._cold_specs = [SpecifierSet(s) for s in self.spec_strs]
        self._cold_simple = SpecifierSet(self.SIMPLE_SPEC)
        self._cold_complex = SpecifierSet(self.COMPLEX_SPEC)

        # Build warm specifiers
        self._warm_specs = [SpecifierSet(s) for s in self.spec_strs]
        self._warm_simple = SpecifierSet(self.SIMPLE_SPEC)
        self._warm_complex = SpecifierSet(self.COMPLEX_SPEC)
        self._warm_compatible = SpecifierSet(self.COMPATIBLE_SPEC)
        for s in self._warm_specs:
            for sp in s._specs:
                sp.contains(self.single_version)
        for sp in self._warm_simple._specs:
            sp.contains(self.single_version)
        for sp in self._warm_complex._specs:
            sp.contains(self.complex_versions[0])
        for sp in self._warm_compatible._specs:
            sp.contains(self.complex_versions[0])

        specifier_strs = [str(sp) for s in self._cold_specs for sp in s._specs]
        self._warm_specifiers = [Specifier(s) for s in specifier_strs]
        others = [Specifier(s) for s in specifier_strs]
        for sp in (*self._warm_specifiers, *others):
            hash(sp)
        self._warm_specifier_pairs = list(
            zip(self._warm_specifiers, others, strict=True)
        )

        self._warm_spec_groups = [s._specs for s in self._warm_specs]
        for group in self._warm_spec_groups:
            for sp in group:
                hash(sp)

    def _make_cold(self, spec: SpecifierSet) -> None:
        if hasattr(spec, "_canonicalized"):
            spec._canonicalized = False
        if hasattr(spec, "_resolved_ops"):
            spec._resolved_ops = None
        if hasattr(spec, "_ranges"):
            spec._ranges = None
        if hasattr(spec, "_is_unsatisfiable"):
            spec._is_unsatisfiable = None
        for sp in spec._specs:
            sp._spec_version = None
            if hasattr(sp, "_wildcard_split"):
                sp._wildcard_split = None
            if hasattr(sp, "_ranges"):
                sp._ranges = None
            if hasattr(sp, "_canonical_spec_cache"):
                sp._canonical_spec_cache = None

    @add_attributes(pretty_name="SpecifierSet constructor")
    def time_constructor(self) -> None:
        for s in self.spec_strs:
            SpecifierSet(s)

    @add_attributes(pretty_name="SpecifierSet contains (cold)")
    def time_contains_cold(self) -> None:
        for spec in self._cold_specs:
            self._make_cold(spec)
        for spec in self._cold_specs:
            spec.contains(self.single_version)

    @add_attributes(pretty_name="SpecifierSet contains (warm)")
    def time_contains_warm(self) -> None:
        for spec in self._warm_specs:
            spec.contains(self.single_version)

    @add_attributes(pretty_name="SpecifierSet contains (complex, warm)")
    def time_contains_complex_warm(self) -> None:
        for v in self.complex_versions:
            self._warm_complex.contains(v)

    @add_attributes(pretty_name="SpecifierSet filter (simple, cold)")
    def time_filter_simple_cold(self) -> None:
        self._make_cold(self._cold_simple)
        list(self._cold_simple.filter(self.simple_versions))

    @add_attributes(pretty_name="SpecifierSet filter (simple, warm)")
    def time_filter_simple_warm(self) -> None:
        list(self._warm_simple.filter(self.simple_versions))

    @add_attributes(pretty_name="SpecifierSet filter (complex, cold)")
    def time_filter_complex_cold(self) -> None:
        self._make_cold(self._cold_complex)
        list(self._cold_complex.filter(self.complex_versions))

    @add_attributes(pretty_name="SpecifierSet filter (complex, warm)")
    def time_filter_complex_warm(self) -> None:
        list(self._warm_complex.filter(self.complex_versions))

    # Only warm filter for compatible (~=): cold and contains paths are already
    # well covered by the simple/complex specifier benchmarks above.
    @add_attributes(pretty_name="SpecifierSet filter (compatible, warm)")
    def time_filter_compatible_warm(self) -> None:
        list(self._warm_compatible.filter(self.complex_versions))

    @add_attributes(pretty_name="Specifier hash (warm)")
    def time_hash_specifier_warm(self) -> None:
        for sp in self._warm_specifiers:
            hash(sp)

    @add_attributes(pretty_name="Specifier equality (warm)")
    def time_eq_specifier_warm(self) -> None:
        for a, b in self._warm_specifier_pairs:
            _ = a == b

    # A SpecifierSet caches its deduplication, so construction has to be inside the
    # timed region to reach the sort and dict.fromkeys at all.
    @add_attributes(pretty_name="SpecifierSet construct + dedup (warm)")
    def time_construct_and_dedup_warm(self) -> None:
        for group in self._warm_spec_groups:
            SpecifierSet(group)._canonical_specs()
