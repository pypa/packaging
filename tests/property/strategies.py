# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

from typing import TYPE_CHECKING

from hypothesis import settings
from hypothesis import strategies as st

from packaging.specifiers import SpecifierSet
from packaging.version import Version

if TYPE_CHECKING:
    from packaging.ranges import VersionRange


def eq_versions_only(a: VersionRange, b: VersionRange) -> bool:
    """Compare two ranges ignoring the arbitrary-string and pre-release
    policy slots.

    Complement preserves ``_admit_arbitrary`` (only the universal range
    admits non-version strings, never algebra), so ``r | ~r`` is never
    structurally equal to ``VersionRange.full()`` when neither ``r`` nor
    ``~r`` is empty. The pre-release configured override mirrors
    ``SpecifierSet.__and__`` rather than pure Boolean algebra. Use this
    helper when the property is "same set of versions accepted".
    """
    return a._bounds == b._bounds and a._admit == b._admit and a._reject == b._reject


SETTINGS = settings(max_examples=300, deadline=None)

# PEP 440 versions covering the major forms.
VERSION_POOL = [
    Version("0"),
    Version("0.0"),
    Version("0.1"),
    Version("1.0"),
    Version("1.0.0"),
    Version("1.2.3"),
    Version("2.0"),
    Version("3.0.0.0"),
    Version("10.20.30"),
    Version("1.0a0"),
    Version("1.0a1"),
    Version("1.0b2"),
    Version("1.0rc1"),
    Version("1.0.dev0"),
    Version("1.0.dev1"),
    Version("1.0.post0"),
    Version("1.0.post1"),
    Version("1.0a1.post1"),
    Version("1.0a1.dev1"),
    Version("1.0.post1.dev1"),
    Version("1.0a1.post1.dev1"),
    Version("1.0+local"),
    Version("1.0+abc.1"),
    Version("1.0+abc.def"),
    Version("1!1.0"),
    Version("1!1.0a1"),
    Version("2!0.1"),
]

small_ints = st.integers(min_value=0, max_value=20)
pre_tags = st.sampled_from(["a", "b", "rc"])
ops = st.sampled_from([">=", "<=", ">", "<", "==", "!="])

release_segment = st.lists(small_ints, min_size=1, max_size=4).map(
    lambda parts: ".".join(str(p) for p in parts)
)

local_numeric = st.integers(min_value=0, max_value=100).map(str)
local_text = st.sampled_from(["abc", "ubuntu", "local", "patch", "dev"])
local_segment = st.one_of(local_numeric, local_text)
local_labels = st.lists(local_segment, min_size=1, max_size=3).map(".".join)


@st.composite
def pep440_versions(
    draw: st.DrawFn,
    *,
    include_local: bool = True,
    min_segments: int = 1,
) -> Version:
    """Generate a random PEP 440 version."""
    epoch = draw(st.sampled_from([None, 0, 1, 2, 3]))
    num_segments = draw(st.integers(min_value=min_segments, max_value=4))
    release = tuple(draw(small_ints) for _ in range(num_segments))

    pre = None
    if draw(st.booleans()):
        pre = (draw(pre_tags), draw(small_ints))

    post: int | None = None
    if draw(st.booleans()):
        post = draw(small_ints)

    dev: int | None = None
    if draw(st.booleans()):
        dev = draw(small_ints)

    local: str | None = None
    if include_local and draw(st.booleans()):
        local = draw(local_labels)

    parts: list[str] = []
    if epoch is not None and epoch != 0:
        parts.append(f"{epoch}!")
    parts.append(".".join(str(s) for s in release))
    if pre is not None:
        parts.append(f"{pre[0]}{pre[1]}")
    if post is not None:
        parts.append(f".post{post}")
    if dev is not None:
        parts.append(f".dev{dev}")
    if local is not None:
        parts.append(f"+{local}")

    return Version("".join(parts))


@st.composite
def nonlocal_versions(draw: st.DrawFn) -> Version:
    """Generate a PEP 440 version without a local segment."""
    v: Version = draw(pep440_versions(include_local=False))
    return v


@st.composite
def release_versions(
    draw: st.DrawFn, *, min_segments: int = 1, allow_epoch: bool = False
) -> Version:
    """Generate a final release version (no pre/post/dev/local).

    With ``allow_epoch=True`` the release may carry a non-zero epoch, so a
    zero release becomes a non-zero-epoch zero family (e.g. ``1!0``).
    """
    num_segments = draw(st.integers(min_value=min_segments, max_value=4))
    release = tuple(draw(small_ints) for _ in range(num_segments))
    epoch = draw(st.sampled_from([None, 1, 2])) if allow_epoch else None
    prefix = f"{epoch}!" if epoch else ""
    return Version(prefix + ".".join(str(s) for s in release))


@st.composite
def multi_segment_versions(draw: st.DrawFn) -> Version:
    """Generate a version with at least 2 release segments (for ~=)."""
    v: Version = draw(pep440_versions(include_local=False, min_segments=2))
    return v


@st.composite
def versions_with_local(draw: st.DrawFn) -> Version:
    """Generate a PEP 440 version that always has a local segment."""
    base = draw(pep440_versions(include_local=False))
    local_part = draw(local_labels)
    return Version(f"{base}+{local_part}")


@st.composite
def specifier_sets(
    draw: st.DrawFn,
    *,
    vary_prereleases: bool = False,
) -> SpecifierSet:
    """Random SpecifierSet over ``>= <= > < == !=`` and ``major.minor``.

    Narrow on purpose. Tests that need wildcards, locals, pre/post/dev
    on the RHS, epochs, or ``===`` should use :func:`rich_specifier_sets`.

    With ``vary_prereleases=True`` the configured pre-release policy is
    drawn from ``(None, True, False)``; otherwise it is left as ``None``
    (autodetect).
    """
    num = draw(st.integers(min_value=1, max_value=3))
    parts: list[str] = []
    for _ in range(num):
        op = draw(ops)
        major = draw(small_ints)
        minor = draw(small_ints)
        parts.append(f"{op}{major}.{minor}")

    prereleases = (
        draw(st.sampled_from([None, True, False])) if vary_prereleases else None
    )

    return SpecifierSet(",".join(parts), prereleases=prereleases)


_ordered_ops = st.sampled_from([">=", "<=", ">", "<"])
_equality_ops = st.sampled_from(["==", "!="])


@st.composite
def pep440_specifier_strings(
    draw: st.DrawFn,
    *,
    include_arbitrary: bool = False,
) -> str:
    """One specifier string covering the full PEP 440 surface.

    Includes pre/post/dev/local-bearing RHS versions, epochs, multi-
    segment release tuples, ``==V.*`` / ``!=V.*`` wildcards, and
    optionally ``===L``.
    """
    shape = draw(st.sampled_from(["ordered", "equality", "wildcard", "compatible"]))
    if include_arbitrary and draw(st.booleans()):
        shape = "arbitrary"

    if shape == "ordered":
        # ``>= <= > <`` reject ``+local`` on the RHS.
        return f"{draw(_ordered_ops)}{draw(pep440_versions(include_local=False))}"

    if shape == "equality":
        return f"{draw(_equality_ops)}{draw(pep440_versions())}"

    if shape == "wildcard":
        # ``==V.*`` / ``!=V.*`` take a release-only RHS; epochs reach the
        # epoch-zero family floor (``==1!0.*``).
        return f"{draw(_equality_ops)}{draw(release_versions(allow_epoch=True))}.*"

    if shape == "compatible":
        return f"~={draw(multi_segment_versions())}"

    # ``===L`` with a parseable literal. Unparsable literals like
    # ``===wat`` are skipped: De Morgan can fail when an unparsable
    # ``===`` interacts with a non-full rangelike, since the bound
    # universe is parseable Versions but the literal universe is
    # all strings.
    return f"==={draw(pep440_versions())}"


@st.composite
def rich_specifier_sets(
    draw: st.DrawFn,
    *,
    include_arbitrary: bool = False,
) -> SpecifierSet:
    """1-3 specifiers from :func:`pep440_specifier_strings`, joined."""
    num = draw(st.integers(min_value=1, max_value=3))
    parts = [
        draw(pep440_specifier_strings(include_arbitrary=include_arbitrary))
        for _ in range(num)
    ]
    return SpecifierSet(",".join(parts))


@st.composite
def related_version_triple(
    draw: st.DrawFn,
) -> tuple[Version, Version, Version]:
    """Three versions sharing a release segment with different suffixes."""
    num_segments = draw(st.integers(min_value=1, max_value=3))
    release = tuple(draw(small_ints) for _ in range(num_segments))
    base = ".".join(str(s) for s in release)

    def _build(draw: st.DrawFn) -> Version:
        pre = draw(st.sampled_from([None, None, "a0", "b1", "rc1"]))
        post = draw(st.sampled_from([None, None, ".post0", ".post1"]))
        dev = draw(st.sampled_from([None, None, None, ".dev0"]))
        return Version(f"{base}{pre or ''}{post or ''}{dev or ''}")

    return (_build(draw), _build(draw), _build(draw))
