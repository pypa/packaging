# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import attr
import requests

from .base import BaseTransport, Response


@attr.s(cmp=False, frozen=True, slots=True)
class RequestsTransport(BaseTransport):

    _session = attr.ib(default=attr.Factory(requests.session), repr=False)

    def get(self, url):
        try:
            resp = self._session.get(url)
            resp.raise_for_status()
        except Exception:  # TODO: Better Exception
            # TODO: How should we signal to the caller that there wasn't an
            #       item (either because of connection issues, 404, or
            #       whatever). As an extended bit, do we want to treat things
            #       like 404 errors differently then 500 errors or connection
            #       errors?
            raise

        return Response(url=url, headers=resp.headers, content=resp.content)
