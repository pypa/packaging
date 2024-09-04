#######################################################################################
#
# Adapted from:
#  https://github.com/pypa/hatch/blob/5352e44/backend/src/hatchling/licenses/parse.py
#
# MIT License
#
# Copyright (c) 2017-present Ofek Lev <oss@ofek.dev>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be included in all copies
# or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
# CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
# OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
#
# With additional allowance of arbitrary `LicenseRef-` identifiers, not just
# `LicenseRef-Public-Domain` and `LicenseRef-Proprietary`.
#
#######################################################################################
from __future__ import annotations

import string
from typing import cast

from packaging.licenses.spdx import EXCEPTIONS, LICENSES

license_ref_allowed = string.ascii_letters + string.digits + "." + "-"


def normalize_license_expression(raw_license_expression: str) -> str | None:
    if not raw_license_expression:
        return None

    license_refs = {
        ref.lower(): "LicenseRef-" + ref[11:]
        for ref in raw_license_expression.split()
        if ref.lower().startswith("licenseref-")
    }

    # First normalize to lower case so we can look up licenses/exceptions
    # and so boolean operators are Python-compatible
    license_expression = raw_license_expression.lower()

    # Then pad parentheses so tokenization can be achieved by merely splitting on
    # white space
    license_expression = license_expression.replace("(", " ( ").replace(")", " ) ")

    # Now we begin parsing
    tokens = license_expression.split()

    # Rather than implementing boolean logic we create an expression that Python can
    # parse. Everything that is not involved with the grammar itself is treated as
    # `False` and the expression should evaluate as such.
    python_tokens = []
    for token in tokens:
        if token not in {"or", "and", "with", "(", ")"}:
            python_tokens.append("False")
        elif token == "with":
            python_tokens.append("or")
        elif token == "(" and python_tokens and python_tokens[-1] not in {"or", "and"}:
            message = f"invalid license expression: {raw_license_expression}"
            raise ValueError(message)
        else:
            python_tokens.append(token)

    python_expression = " ".join(python_tokens)
    try:
        result = eval(python_expression)
    except Exception:
        result = True

    if result is not False:
        message = f"invalid license expression: {raw_license_expression}"
        raise ValueError(message) from None

    # Take a final pass to check for unknown licenses/exceptions
    normalized_tokens = []
    for token in tokens:
        if token in {"or", "and", "with", "(", ")"}:
            normalized_tokens.append(token.upper())
            continue

        if normalized_tokens and normalized_tokens[-1] == "WITH":
            if token not in EXCEPTIONS:
                message = f"unknown license exception: {token}"
                raise ValueError(message)

            normalized_tokens.append(cast(str, EXCEPTIONS[token]["id"]))
        else:
            if token.endswith("+"):
                final_token = token[:-1]
                suffix = "+"
            else:
                final_token = token
                suffix = ""

            if final_token.startswith("licenseref-"):
                if not all(c in license_ref_allowed for c in final_token):
                    message = f"invalid licenseref: {final_token}"
                    raise ValueError(message)
                normalized_tokens.append(license_refs[final_token] + suffix)
            else:
                if final_token not in LICENSES:
                    message = f"unknown license: {final_token}"
                    raise ValueError(message)
                normalized_tokens.append(
                    cast(str, LICENSES[final_token]["id"]) + suffix
                )

    # Construct the normalized expression
    normalized_expression = " ".join(normalized_tokens)

    # Fix internal padding for parentheses
    return normalized_expression.replace("( ", "(").replace(" )", ")")
