Changelog
---------

*unreleased*
~~~~~~~~~~~~

No unreleased changes.

26.1 - 2026-04-14
~~~~~~~~~~~~~~~~~

Features:

* PEP 783: add handling for Emscripten wheel tags in (:pull:`804`)
* PEP 803: add handling for the ``abi3.abi3t`` free-threading tag in (:pull:`1099`)
* PEP 723: add ``packaging.dependency_groups`` module, based on the ``dependency-groups`` package in (:pull:`1065`)
* Add the ``packaging.direct_url`` module in (:pull:`944`)
* Add the ``packaging.errors`` module in (:pull:`1071`)
* Add ``SpecifierSet.is_unsatisfiable`` using ranges (new internals that will be expanded in future versions) in (:pull:`1119`)
* Add ``create_compatible_tags_selector`` to select compatible tags in (:pull:`1110`)
* Add a ``key`` argument to ``SpecifierSet.filter()`` in (:pull:`1068`)
* Support ``&`` and ``|`` for ``Marker``'s in (:pull:`1146`)
* Normalize ``Version.__replace__`` and add ``Version.from_parts`` in (:pull:`1078`)
* Add an option to validate compressed tag set sort order in ``parse_wheel_filename`` in (:pull:`1150`)

Behavior adaptations:

* Narrow exclusion of pre-releases for ``<V.postN`` to match spec in (:pull:`1140`)
* Narrow exclusion of post-releases for ``>V`` to match spec in (:pull:`1141`)
* Rename ``format_full_version`` to ``_format_full_version`` to make it visibly private in (:pull:`1125`)
* Restrict local version to ASCII in (:pull:`1102`)

Pylock (PEP 751) updates:

* Add pylock ``select`` function in (:pull:`1092`)
* Document pylock ``select()`` method and ``PylockSelectError`` in (:pull:`1153`)
* Add ``filename`` property to ``PackageSdist`` and ``PackageWheel``, more validation in (:pull:`1095`)
* Give preference to path over url in (:pull:`1128`)
* Validate name/version consistency in file names in (:pull:`1114`)

Fixes:

* Fix ``>`` comparison for versions with dev+local segments in (:pull:`1097`)
* Fix incorrect self-comparison for ``InfinityType`` and ``NegativeInfinityType`` in (:pull:`1093`)
* Canonicalize when deduplicating specifiers in ``SpecifierSet`` in (:pull:`1109`)
* Fix charset error message formatting in (:pull:`1121`)
* Handle the ``key`` parameter in ``SpecifierSet.filter`` when specifiers are empty and prerelease is ``False`` in (:pull:`1096`)
* Standardize inner components of ``repr`` output in (:pull:`1090`)
* ``Specifier``'s ``===`` uses original string, not normalized, when available in (:pull:`1124`)
* Propagate int-max-str-digits ``ValueError`` in (:pull:`1155`)

Performance:

* Add fast path for parsing simple versions (digits and dots only) in (:pull:`1082`)
* Add fast path for ``Version`` to ``Version`` comparison by skipping ``_key`` property in (:pull:`1083`)
* Cache ``Version`` hash value in dedicated slot in (:pull:`1118`)
* Overhaul ``_cmpkey`` to remove use of custom objects in (:pull:`1116`)
* Skip ``__replace__`` in Specifier comparison if not needed in (:pull:`1081`)
* ``SpecifierSet`` use ``tuple`` instead of ``frozenset`` for ``_specs`` in (:pull:`1108`)
* Speed up complex ``SpecifierSet`` filtering by implementing cost-based ordering in (:pull:`1105`)
* Speed up wildcard comparison in (:pull:`1111`)
* Stream PEP440 filtering in ``SpecifierSet.filter`` in (:pull:`1076`)
* Add ``__slots__`` to ``Marker`` in (:pull:`1147`)
* Simply ``Specifier`` regex in (:pull:`1106`)
* Skip using the hash property internally in (:pull:`1115`)

Internal:

* Add downstream testing in (:pull:`1049`)
* Benchmarking suite in (:pull:`1059`)
* Benchmark variance reduction in (:pull:`1107`)
* Add property-based tests for PEP 440 in (:pull:`1144`)
* Clean up a few ``collections.namedtuple`` in tests in (:pull:`1070`)
* Do not reload the tags module in tests in (:pull:`1152`)
* Limit ``dir()`` / tab-completion in REPL in (:pull:`1011`)
* Add more ``__all__`/`__dir__`` in (:pull:`1069`)
* Cleanup pre-commit a bit in (:pull:`1080`)
* Pin pre-commit file, use dependabot in (:pull:`1133`)
* Remove sphinx-toolbox in (:pull:`1135`)
* Use docs group, faster readthedocs in (:pull:`1061`)
* Add free-threaded Python to CI in (:pull:`1098`)
* Simplify combining ``SpecifierSet.prereleases`` in (:pull:`1073`)
* Use direct operator methods in ``_compare_compatible`` in (:pull:`1100`)
* Remove unnecessary if statement in ``Specifier.prereleases`` in (:pull:`1074`)
* Remove unneeded nesting in ``Specifier.prereleases`` in (:pull:`1072`)

Documentation:

* Fix documentation: grammar, typos, formatting, and outdated references in (:pull:`1084`)
* Fix versionadded for ``Version.from_parts()`` in (:pull:`1134`)
* Document ``&`` and ``|`` operators for combining ``Marker`` objects in (:pull:`1151`)
* Expand and clean up ``Version`` documentation in (:pull:`1089`)
* Move license docs inline in (:pull:`1131`)
* Move markers inline in (:pull:`1104`)
* Move tags docs to inline in (:pull:`1130`)
* Move utilities inline, like other modules in (:pull:`1103`)

26.0 - 2026-01-20
~~~~~~~~~~~~~~~~~

Features:

* PEP 751: support pylock (:pull:`900`)
* PEP 794: import name metadata (:pull:`948`)
* Support for writing metadata to a file (:pull:`846`)
* Support ``__replace__`` on Version (:pull:`1003`)
* Support positional pattern matching for ``Version`` and ``SpecifierSet`` (:pull:`1004`)

Behavior adaptations:

* PEP 440 handling of prereleases for ``Specifier.contains``, ``SpecifierSet.contains``, and ``SpecifierSet.filter`` (:pull:`897`)
* Handle PEP 440 edge case in ``SpecifierSet.filter`` (:pull:`942`)
* Adjust arbitrary equality intersection preservation in ``SpecifierSet`` (:pull:`951`)
* Return ``False`` instead of raising for ``.contains`` with invalid version (:pull:`932`)
* Support arbitrary equality on arbitrary strings for ``Specifier`` and ``SpecifierSet``'s ``filter`` and ``contains`` method. (:pull:`954`)
* Only try to parse as ``Version`` on certain marker keys, return ``False`` on unequal ordered comparisons (:pull:`939`)

Fixes:

* Update ``_hash`` when unpickling ``Tag()`` (:pull:`860`)
* Correct comment and simplify implicit prerelease handling in ``Specifier.prereleases`` (:pull:`896`)
* Use explicit ``_GLibCVersion`` ``NamedTuple`` in ``_manylinux`` (:pull:`868`)
* Detect invalid license expressions containing ``()`` (:pull:`879`)
* Correct regex for metadata ``'name'`` format (:pull:`925`)
* Improve the message around expecting a semicolon (:pull:`833`)
* Support nested parens in license expressions (:pull:`931`)
* Add space before at symbol in ``Requirements`` string (:pull:`953`)
* A root logger use found, use a ``packaging`` logger instead (:pull:`965`)
* Better support for subclassing ``Marker`` and ``Requirement`` (:pull:`1022`)
* Normalize all extras, not just if it comes first (:pull:`1024`)
* Don't produce a broken repr if ``Marker`` fails to construct (:pull:`1033`)

Performance:

* Avoid recompiling regexes in the tokenizer for a 3x speedup (:pull:`1019`)
* Improve performance in ``_manylinux.py`` (:pull:`869`)
* Minor cleanups to ``Version`` (:pull:`913`)
* Skip redundant creation of ``Version``'s in specifier comparison (:pull:`986`)
* Cache the ``Specifier``'s ``Version`` (:pull:`985`)
* Make ``Version`` a little faster (:pull:`987`)
* Minor ``Version`` regex cleanup (:pull:`990`)
* Faster regex on Python 3.11.5+ for ``Version`` (:pull:`988`, :pull:`1055`)
* Lazily calculate ``_key`` in ``Version`` (:pull:`989`, :pull:`1048`)
* Faster ``canonicalize_version`` (:pull:`993`)
* Use ``re.fullmatch`` in a couple more places (:pull:`992`, :pull:`1029`)
* Use ``map`` instead of generator (:pull:`996`)
* Deprecate ``._version`` (``_Version``, a ``NamedTuple``) (:pull:`995`, :pull:`1062`)
* Avoid duplicate ``Version`` creation in ``canonicalize_version`` (:pull:`994`)
* Add ``__slots__`` to core classes  (:pull:`1001`, :pull:`1002`, :pull:`1032`)
* Use ``Version.__replace__`` in specifier comparison (:pull:`999`)
* Use ``_get_spec_version`` in more places in ``Specifier`` (:pull:`1005`)
* Pull ``set`` construction out of function (:pull:`1012`)
* Letter normalization dict for prereleases and the like (:pull:`1014`)
* Use ``str.partition`` in ``_parse_project_urls`` (:pull:`1013`)
* Avoid normalizing extras again when comparing (:pull:`1028`)
* Speed up ``Version.__str__`` by about 10% (:pull:`997`)
* Much faster ``canonicalize_name`` by avoiding a regex (:pull:`1030`, :pull:`1047`, :pull:`1064`)
* Faster zero stripping (:pull:`1058`)

Type annotations:

* Fix a type annotation (:pull:`907`)
* Fix type hint of function used with ``contextlib.contextmanager`` (:pull:`1046`)
* Fix tags return type in ``parse_wheel_filename`` docs (:pull:`973`)
* Add type hint for ``_version`` in ``.version.Version`` (:pull:`927`)
* Changed static type annotations in prereleases setter method in ``specifier.py`` (:pull:`930`)
* Statically type our test suite (:pull:`982`)

Internal:

* Test and declare support for Python 3.14 (:pull:`901`)
* Change our license metadata to use an SPDX license expression (:pull:`881`, :pull:`924`)
* Expand the Ruff checks run on our codebase (:pull:`835`, :pull:`957`, :pull:`959`,
  :pull:`963`, :pull:`956`, :pull:`961`, :pull:`964`, :pull:`958`, :pull:`960`, :pull:`968`,
  :pull:`967`, :pull:`966`, :pull:`969`, :pull:`980`, :pull:`979`, :pull:`962`, :pull:`984`,
  :pull:`972`)
* Add spell checking (:pull:`904`, :pull:`910`, :pull:`1015`)
* Improve links back to source in the documentation (:pull:`991`)
* Add case insensitivity tests for arbitrary equality (:pull:`975`)
* Fix incorrectly implicitly concatenated string in specifiers test (:pull:`946`)
* Simpler else instead of assert in a check (:pull:`1027`, :pull:`1031`)
* Synchronize documentation and code for markers (:pull:`1008`)
* Use the GitHub Actions slim runner for the all pass check (:pull:`1021`)
* Use ``actionlint`` to check CI workflows (:pull:`1052`)
* Use Trusted Publishing (:pull:`893`, :pull:`1043`, :pull:`1045`, :pull:`1051`)
* Use zizmor to check CI (:pull:`1035`)
* Test on first public release of CPython 3.11 and newer (:pull:`1056`)


Since the final release candidate: Faster ``canonicalize_name``, especially on
Python 3.12 and 3.13, where performance regressed previously (:pull:`1064`),
and reintroduce (deprecated) support for ``Version._.version`` (:pull:`1062`).

26.0rc3 - 2026-01-15
~~~~~~~~~~~~~~~~~~~~

Third release candidate for 26.0. Avoid bug in CPython 3.11.0-3.11.4 and older
PyPy 3.11 (:pull:`1055`).

26.0rc2 - 2026-01-12
~~~~~~~~~~~~~~~~~~~~

Second release candidate for 26.0. Fixed a regression in (private)
``Version._key`` for ``packaging_legacy`` (:pull:`1048`), and speed up
stripping zeros a little more (:pull:`1058`).

26.0rc1 - 2026-01-09
~~~~~~~~~~~~~~~~~~~~

First release candidate for 26.0.

25.0 - 2025-04-19
~~~~~~~~~~~~~~~~~

* PEP 751: Add support for ``extras`` and ``dependency_groups`` markers. (:issue:`885`)
* PEP 738: Add support for Android platform tags. (:issue:`880`)

24.2 - 2024-11-08
~~~~~~~~~~~~~~~~~

* PEP 639: Implement License-Expression and License-File (:issue:`828`)
* Use ``!r`` formatter for error messages with filenames (:issue:`844`)
* Add support for PEP 730 iOS tags (:issue:`832`)
* Fix prerelease detection for ``>`` and ``<`` (:issue:`794`)
* Fix uninformative error message (:issue:`830`)
* Refactor ``canonicalize_version`` (:issue:`793`)
* Patch python_full_version unconditionally (:issue:`825`)
* Fix doc for ``canonicalize_version`` to mention ``strip_trailing_zero`` and a typo in a docstring (:issue:`801`)
* Fix typo in Version ``__str__`` (:issue:`817`)
* Support creating a ``SpecifierSet`` from an iterable of ``Specifier`` objects (:issue:`775`)

24.1 - 2024-06-10
~~~~~~~~~~~~~~~~~

* Document ``markers.default_environment()`` (:issue:`753`).
* Add support for Python 3.13 (:issue:`783`).
* Modernise type annotations (:issue:`785`).
* Work around ``platform.python_version()`` returning non PEP 440 compliant version
  for non-tagged CPython builds (:issue:`802`).

24.0 - 2024-03-10
~~~~~~~~~~~~~~~~~

* Do specifier matching correctly when the specifier contains an epoch number
  and has more components than the version (:issue:`683`)
* Support the experimental ``--disable-gil`` builds in packaging.tags
  (:issue:`727`)
* BREAKING: Make optional ``metadata.Metadata`` attributes default to ``None`` (:issue:`733`)
* Fix errors when trying to access the ``description_content_type``, ``keywords``,
  and ``requires_python`` attributes on ``metadata.Metadata`` when those values
  have not been provided (:issue:`733`)
* Fix a bug preventing the use of the built in ``ExceptionGroup`` on versions of
  Python that support it (:issue:`725`)

23.2 - 2023-10-01
~~~~~~~~~~~~~~~~~

* Document calendar-based versioning scheme (:issue:`716`)
* Enforce that the entire marker string is parsed (:issue:`687`)
* Requirement parsing no longer automatically validates the URL (:issue:`120`)
* Canonicalize names for requirements comparison (:issue:`644`)
* Introduce ``metadata.Metadata`` (along with ``metadata.ExceptionGroup`` and ``metadata.InvalidMetadata``; :issue:`570`)
* Introduce the ``validate`` keyword parameter to ``utils.normalize_name()`` (:issue:`570`)
* Introduce ``utils.is_normalized_name()`` (:issue:`570`)
* Make ``utils.parse_sdist_filename()`` and ``utils.parse_wheel_filename()``
  raise ``InvalidSdistFilename`` and ``InvalidWheelFilename``, respectively,
  when the version component of the name is invalid
* Remove support for Python 3.7 (:issue:`783`)

23.1 - 2023-04-12
~~~~~~~~~~~~~~~~~

* Parse raw metadata (:issue:`671`)
* Import underlying parser functions as an underscored variable (:issue:`663`)
* Improve error for local version label with unsupported operators (:issue:`675`)
* Add dedicated error for specifiers with incorrect ``.*`` suffix
* Replace spaces in platform names with underscores (:issue:`620`)
* Relax typing of ``_key`` on ``_BaseVersion`` (:issue:`669`)
* Handle prefix match with zeros at end of prefix correctly (:issue:`674`)

23.0 - 2023-01-08
~~~~~~~~~~~~~~~~~

* Allow ``"extra"`` to be ``None`` in the marker environment (:issue:`650`)
* Refactor ``tags._generic_api`` to use ``EXT_SUFFIX`` (:issue:`607`)
* Correctly handle trailing whitespace on URL requirements (:issue:`642`)
* Fix typing for ``specifiers.BaseSpecifier.filter()`` (:issue:`643`)
* Use stable Python 3.11 in tests (:issue:`641`)
* Correctly handle non-normalised specifiers in requirements (:issue:`634`)
* Move to ``src/`` layout (:issue:`626`)
* Remove ``__about__`` file, in favour of keeping constants in ``__init__`` (:issue:`626`)

22.0 - 2022-12-07
~~~~~~~~~~~~~~~~~

* Explicitly declare support for Python 3.11 (:issue:`587`)
* Remove support for Python 3.6 (:issue:`500`)
* Remove ``LegacySpecifier`` and ``LegacyVersion`` (:issue:`407`)
* Add ``__hash__`` and ``__eq__`` to ``Requirement`` (:issue:`499`)
* Add a ``cpNNN-none-any`` tag (:issue:`541`)
* Adhere to :pep:`685` when evaluating markers with extras (:issue:`545`)
* Allow accepting locally installed prereleases with ``SpecifierSet``  (:issue:`515`)
* Allow pre-release versions in marker evaluation (:issue:`523`)
* Correctly parse ELF for musllinux on Big Endian (:issue:`538`)
* Document ``packaging.utils.NormalizedName`` (:issue:`565`)
* Document exceptions raised by functions in ``packaging.utils`` (:issue:`544`)
* Fix compatible version specifier incorrectly strip trailing ``0`` (:issue:`493`)
* Fix macOS platform tags with old macOS SDK (:issue:`513`)
* Forbid prefix version matching on pre-release/post-release segments (:issue:`563`)
* Normalize specifier version for prefix matching (:issue:`561`)
* Improve documentation for ``packaging.specifiers`` and ``packaging.version``. (:issue:`572`)
* ``Marker.evaluate`` will now assume evaluation environment with empty ``extra``.
  Evaluating markers like ``"extra == 'xyz'"`` without passing any extra in the
  ``environment`` will no longer raise an exception (:issue:`550`)
* Remove dependency on ``pyparsing``, by replacing it with a hand-written parser.
  This package now has no runtime dependencies (:issue:`468`)
* Update return type hint for ``Specifier.filter`` and ``SpecifierSet.filter``
  to use ``Iterator`` instead of ``Iterable`` (:issue:`584`)

21.3 - 2021-11-17
~~~~~~~~~~~~~~~~~

* Add a ``pp3-none-any`` tag (:issue:`311`)
* Replace the blank pyparsing 3 exclusion with a 3.0.5 exclusion (:issue:`481`, :issue:`486`)
* Fix a spelling mistake (:issue:`479`)

21.2 - 2021-10-29
~~~~~~~~~~~~~~~~~

* Update documentation entry for 21.1.

21.1 - 2021-10-29
~~~~~~~~~~~~~~~~~

* Update pin to pyparsing to exclude 3.0.0.

21.0 - 2021-07-03
~~~~~~~~~~~~~~~~~

* PEP 656: musllinux support (:issue:`411`)
* Drop support for Python 2.7, Python 3.4 and Python 3.5.
* Replace distutils usage with sysconfig (:issue:`396`)
* Add support for zip files in ``parse_sdist_filename`` (:issue:`429`)
* Use cached ``_hash`` attribute to short-circuit tag equality comparisons (:issue:`417`)
* Specify the default value for the ``specifier`` argument to ``SpecifierSet`` (:issue:`437`)
* Proper keyword-only "warn" argument in packaging.tags (:issue:`403`)
* Correctly remove prerelease suffixes from ~= check (:issue:`366`)
* Fix type hints for ``Version.post`` and ``Version.dev`` (:issue:`393`)
* Use typing alias ``UnparsedVersion`` (:issue:`398`)
* Improve type inference for ``packaging.specifiers.filter()`` (:issue:`430`)
* Tighten the return type of ``canonicalize_version()`` (:issue:`402`)

20.9 - 2021-01-29
~~~~~~~~~~~~~~~~~

* Run `isort <https://pypi.org/project/isort/>`_ over the code base (:issue:`377`)
* Add support for the ``macosx_10_*_universal2`` platform tags (:issue:`379`)
* Introduce ``packaging.utils.parse_wheel_filename()`` and ``parse_sdist_filename()``
  (:issue:`387` and :issue:`389`)

20.8 - 2020-12-11
~~~~~~~~~~~~~~~~~

* Revert back to setuptools for compatibility purposes for some Linux distros (:issue:`363`)
* Do not insert an underscore in wheel tags when the interpreter version number
  is more than 2 digits (:issue:`372`)

20.7 - 2020-11-28
~~~~~~~~~~~~~~~~~

No unreleased changes.

20.6 - 2020-11-28
~~~~~~~~~~~~~~~~~

.. note:: This release was subsequently yanked, and these changes were included in 20.7.

* Fix flit configuration, to include LICENSE files (:issue:`357`)
* Make ``intel`` a recognized CPU architecture for the ``universal`` macOS platform tag (:issue:`361`)
* Add some missing type hints to ``packaging.requirements`` (issue:`350`)

20.5 - 2020-11-27
~~~~~~~~~~~~~~~~~

* Officially support Python 3.9 (:issue:`343`)
* Deprecate the ``LegacyVersion`` and ``LegacySpecifier`` classes (:issue:`321`)
* Handle ``OSError`` on non-dynamic executables when attempting to resolve
  the glibc version string.

20.4 - 2020-05-19
~~~~~~~~~~~~~~~~~

* Canonicalize version before comparing specifiers. (:issue:`282`)
* Change type hint for ``canonicalize_name`` to return
  ``packaging.utils.NormalizedName``.
  This enables the use of static typing tools (like mypy) to detect mixing of
  normalized and un-normalized names.

20.3 - 2020-03-05
~~~~~~~~~~~~~~~~~

* Fix changelog for 20.2.

20.2 - 2020-03-05
~~~~~~~~~~~~~~~~~

* Fix a bug that caused a 32-bit OS that runs on a 64-bit ARM CPU (e.g. ARM-v8,
  aarch64), to report the wrong bitness.

20.1 - 2020-01-24
~~~~~~~~~~~~~~~~~~~

* Fix a bug caused by reuse of an exhausted iterator. (:issue:`257`)

20.0 - 2020-01-06
~~~~~~~~~~~~~~~~~

* Add type hints (:issue:`191`)

* Add proper trove classifiers for PyPy support (:issue:`198`)

* Scale back depending on ``ctypes`` for manylinux support detection (:issue:`171`)

* Use ``sys.implementation.name`` where appropriate for ``packaging.tags`` (:issue:`193`)

* Expand upon the API provided by ``packaging.tags``: ``interpreter_name()``, ``mac_platforms()``, ``compatible_tags()``, ``cpython_tags()``, ``generic_tags()`` (:issue:`187`)

* Officially support Python 3.8 (:issue:`232`)

* Add ``major``, ``minor``, and ``micro`` aliases to ``packaging.version.Version`` (:issue:`225`)

* Properly mark ``packaging`` has being fully typed by adding a ``py.typed`` file (:issue:`226`)

19.2 - 2019-09-18
~~~~~~~~~~~~~~~~~

* Remove dependency on ``attrs`` (:issue:`178`, :issue:`179`)

* Use appropriate fallbacks for CPython ABI tag (:issue:`181`, :issue:`185`)

* Add manylinux2014 support (:issue:`186`)

* Improve ABI detection (:issue:`181`)

* Properly handle debug wheels for Python 3.8 (:issue:`172`)

* Improve detection of debug builds on Windows (:issue:`194`)

19.1 - 2019-07-30
~~~~~~~~~~~~~~~~~

* Add the ``packaging.tags`` module. (:issue:`156`)

* Correctly handle two-digit versions in ``python_version`` (:issue:`119`)


19.0 - 2019-01-20
~~~~~~~~~~~~~~~~~

* Fix string representation of PEP 508 direct URL requirements with markers.

* Better handling of file URLs

  This allows for using ``file:///absolute/path``, which was previously
  prevented due to the missing ``netloc``.

  This allows for all file URLs that ``urlunparse`` turns back into the
  original URL to be valid.


18.0 - 2018-09-26
~~~~~~~~~~~~~~~~~

* Improve error messages when invalid requirements are given. (:issue:`129`)


17.1 - 2017-02-28
~~~~~~~~~~~~~~~~~

* Fix ``utils.canonicalize_version`` when supplying non PEP 440 versions.


17.0 - 2017-02-28
~~~~~~~~~~~~~~~~~

* Drop support for python 2.6, 3.2, and 3.3.

* Define minimal pyparsing version to 2.0.2 (:issue:`91`).

* Add ``epoch``, ``release``, ``pre``, ``dev``, and ``post`` attributes to
  ``Version`` and ``LegacyVersion`` (:issue:`34`).

* Add ``Version().is_devrelease`` and ``LegacyVersion().is_devrelease`` to
  make it easy to determine if a release is a development release.

* Add ``utils.canonicalize_version`` to canonicalize version strings or
  ``Version`` instances (:issue:`121`).


16.8 - 2016-10-29
~~~~~~~~~~~~~~~~~

* Fix markers that utilize ``in`` so that they render correctly.

* Fix an erroneous test on Python RC releases.


16.7 - 2016-04-23
~~~~~~~~~~~~~~~~~

* Add support for the deprecated ``python_implementation`` marker which was
  an undocumented setuptools marker in addition to the newer markers.


16.6 - 2016-03-29
~~~~~~~~~~~~~~~~~

* Add support for the deprecated, PEP 345 environment markers in addition to
  the newer markers.


16.5 - 2016-02-26
~~~~~~~~~~~~~~~~~

* Fix a regression in parsing requirements with whitespaces between the comma
  separators.


16.4 - 2016-02-22
~~~~~~~~~~~~~~~~~

* Fix a regression in parsing requirements like ``foo (==4)``.


16.3 - 2016-02-21
~~~~~~~~~~~~~~~~~

* Fix a bug where ``packaging.requirements:Requirement`` was overly strict when
  matching legacy requirements.


16.2 - 2016-02-09
~~~~~~~~~~~~~~~~~

* Add a function that implements the name canonicalization from PEP 503.


16.1 - 2016-02-07
~~~~~~~~~~~~~~~~~

* Implement requirement specifiers from PEP 508.


16.0 - 2016-01-19
~~~~~~~~~~~~~~~~~

* Relicense so that packaging is available under *either* the Apache License,
  Version 2.0 or a 2 Clause BSD license.

* Support installation of packaging when only distutils is available.

* Fix ``==`` comparison when there is a prefix and a local version in play.
  (:issue:`41`).

* Implement environment markers from PEP 508.


15.3 - 2015-08-01
~~~~~~~~~~~~~~~~~

* Normalize post-release spellings for rev/r prefixes. :issue:`35`


15.2 - 2015-05-13
~~~~~~~~~~~~~~~~~

* Fix an error where the arbitrary specifier (``===``) was not correctly
  allowing pre-releases when it was being used.

* Expose the specifier and version parts through properties on the
  ``Specifier`` classes.

* Allow iterating over the ``SpecifierSet`` to get access to all of the
  ``Specifier`` instances.

* Allow testing if a version is contained within a specifier via the ``in``
  operator.


15.1 - 2015-04-13
~~~~~~~~~~~~~~~~~

* Fix a logic error that was causing inconsistent answers about whether or not
  a pre-release was contained within a ``SpecifierSet`` or not.


15.0 - 2015-01-02
~~~~~~~~~~~~~~~~~

* Add ``Version().is_postrelease`` and ``LegacyVersion().is_postrelease`` to
  make it easy to determine if a release is a post release.

* Add ``Version().base_version`` and ``LegacyVersion().base_version`` to make
  it easy to get the public version without any pre or post release markers.

* Support the update to PEP 440 which removed the implied ``!=V.*`` when using
  either ``>V`` or ``<V`` and which instead special cased the handling of
  pre-releases, post-releases, and local versions when using ``>V`` or ``<V``.


14.5 - 2014-12-17
~~~~~~~~~~~~~~~~~

* Normalize release candidates as ``rc`` instead of ``c``.

* Expose the ``VERSION_PATTERN`` constant, a regular expression matching
  a valid version.


14.4 - 2014-12-15
~~~~~~~~~~~~~~~~~

* Ensure that versions are normalized before comparison when used in a
  specifier with a less than (``<``) or greater than (``>``) operator.


14.3 - 2014-11-19
~~~~~~~~~~~~~~~~~

* **BACKWARDS INCOMPATIBLE** Refactor specifier support so that it can sanely
  handle legacy specifiers as well as PEP 440 specifiers.

* **BACKWARDS INCOMPATIBLE** Move the specifier support out of
  ``packaging.version`` into ``packaging.specifiers``.


14.2 - 2014-09-10
~~~~~~~~~~~~~~~~~

* Add prerelease support to ``Specifier``.
* Remove the ability to do ``item in Specifier()`` and replace it with
  ``Specifier().contains(item)`` in order to allow flags that signal if a
  prerelease should be accepted or not.
* Add a method ``Specifier().filter()`` which will take an iterable and returns
  an iterable with items that do not match the specifier filtered out.


14.1 - 2014-09-08
~~~~~~~~~~~~~~~~~

* Allow ``LegacyVersion`` and ``Version`` to be sorted together.
* Add ``packaging.version.parse()`` to enable easily parsing a version string
  as either a ``Version`` or a ``LegacyVersion`` depending on it's PEP 440
  validity.


14.0 - 2014-09-05
~~~~~~~~~~~~~~~~~

* Initial release.


.. _`master`: https://github.com/pypa/packaging/
