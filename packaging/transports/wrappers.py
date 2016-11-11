# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import attr

from six.moves import urllib_parse

from .base import BaseTransport


@attr.s(cmp=False, frozen=True, slots=True)
class Transports(BaseTransport):

    schemes = attr.ib()

    def _transport_for_url(self, url):
        return self.schemes[urllib_parse.urlparse(url).scheme]

    def get(self, url):
        return self._transport_for_url(url).get(url)
