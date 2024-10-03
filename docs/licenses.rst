Licenses
=========

.. currentmodule:: packaging.licenses


Helper for canonicalizing SPDX
`License-Expression metadata <https://peps.python.org/pep-0639/#term-license-expression>`__
as `defined in PEP 639 <https://peps.python.org/pep-0639/#spdx>`__.


Reference
---------

.. class:: NormalizedLicenseExpression

    A :class:`typing.NewType` of :class:`str`, representing a normalized
    License-Expression.


.. exception:: InvalidLicenseExpression

    Raised when a License-Expression is invalid.


.. function:: canonicalize_license_expression(raw_license_expression)

    This function takes a valid License-Expression, and returns the normalized form of it.

    The return type is typed as :class:`NormalizedLicenseExpression`. This allows type
    checkers to help require that a string has passed through this function
    before use.

    :param str raw_license_expression: The License-Expression to canonicalize.
    :raises InvalidLicenseExpression: If the License-Expression is invalid due to an
        invalid/unknown license identifier or invalid syntax.

    .. doctest::

        >>> from packaging.licenses import canonicalize_license_expression
        >>> canonicalize_license_expression("mit")
        'MIT'
        >>> canonicalize_license_expression("mit and (apache-2.0 or bsd-2-clause)")
        'MIT AND (Apache-2.0 OR BSD-2-Clause)'
        >>> canonicalize_license_expression("(mit")
        Traceback (most recent call last):
          ...
        InvalidLicenseExpression: Invalid license expression: '(mit'
        >>> canonicalize_license_expression("Use-it-after-midnight")
        Traceback (most recent call last):
          ...
        InvalidLicenseExpression: Unknown license: 'Use-it-after-midnight'
