Metadata
==========

.. currentmodule:: packaging.metadata

A data representation for `core metadata`_.


Reference
---------

.. class:: DynamicField

    An :class:`enum.Enum` representing fields which can be listed in
    the ``Dynamic`` field of `core metadata`_. Every valid field is
    a name on this enum, upper-cased with any ``-`` replaced with ``_``.
    Each value is the field name lower-cased (``-`` are kept). For
    example, the ``Home-page`` field has a name of ``HOME_PAGE`` and a
    value of ``home-page``.


.. class:: Metadata(name, version, *, platforms=None, summary=None, description=None, keywords=None, home_page=None, author=None, author_emails=None, license=None, supported_platforms=None, download_url=None, classifiers=None, maintainer=None, maintainer_emails=None, requires_dists=None, requires_python=None, requires_externals=None, project_urls=None, provides_dists= None, obsoletes_dists= None, description_content_type=None, provides_extras=None, dynamic_fields=None)

    A class representing the `core metadata`_ for a project.

    Every potential metadata field except for ``Metadata-Version`` is
    represented by a parameter to the class' constructor. The required
    metadata can be passed in positionally or via keyword, while all
    optional metadata can only be passed in via keyword.

    Every parameter has a matching attribute on instances,
    except for *name* (see :attr:`display_name` and
    :attr:`canonical_name`). Any parameter that accepts an
    :class:`~collections.abc.Iterable` is represented as a
    :class:`list` on the corresponding attribute.

    :param str name: ``Name``.
    :param packaging.version.Version version: ``Version`` (note
        that this is different than ``Metadata-Version``).
    :param Iterable[str] platforms: ``Platform``.
    :param str summary: ``Summary``.
    :param str description: ``Description``.
    :param Iterable[str] keywords: ``Keywords``.
    :param str home_page: ``Home-Page``.
    :param str author: ``Author``.
    :param Iterable[tuple[str | None, str]] author_emails: ``Author-Email``
        where the two-item tuple represents the name and email of the author,
        respectively.
    :param str license: ``License``.
    :param Iterable[str] supported_platforms: ``Supported-Platform``.
    :param str download_url: ``Download-URL``.
    :param Iterable[str] classifiers: ``Classifier``.
    :param str maintainer: ``Maintainer``.
    :param Iterable[tuple[str | None, str]] maintainer_emails: ``Maintainer-Email``,
        where the two-item tuple represents the name and email of the maintainer,
        respectively.
    :param Iterable[packaging.requirements.Requirement] requires_dists: ``Requires-Dist``.
    :param packaging.specifiers.SpecifierSet requires_python: ``Requires-Python``.
    :param Iterable[str] requires_externals: ``Requires-External``.
    :param tuple[str, str] project_urls: ``Project-URL``.
    :param Iterable[str] provides_dists: ``Provides-Dist``.
    :param Iterable[str] obsoletes_dists: ``Obsoletes-Dist``.
    :param str description_content_type: ``Description-Content-Type``.
    :param Iterable[packaging.utils.NormalizedName] provides_extras: ``Provides-Extra``.
    :param Iterable[DynamicField] dynamic_fields: ``Dynamic``.

    Attributes not directly corresponding to a parameter are:

    .. attribute:: display_name

        The project name to be displayed to users (i.e. not normalized).
        Initially set based on the *name* parameter.
        Setting this attribute will also update :attr:`canonical_name`.

    .. attribute:: canonical_name

        The normalized project name as per
        :func:`packaging.utils.canonicalize_name`. The attribute is
        read-only and automatically calculated based on the value of
        :attr:`display_name`.


.. _`core metadata`: https://packaging.python.org/en/latest/specifications/core-metadata/
.. _`project metadata`: https://packaging.python.org/en/latest/specifications/declaring-project-metadata/
.. _`source distribution`: https://packaging.python.org/en/latest/specifications/source-distribution-format/
.. _`binary distrubtion`: https://packaging.python.org/en/latest/specifications/binary-distribution-format/
