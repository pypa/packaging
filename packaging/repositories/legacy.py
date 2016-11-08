# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import attr
import html5lib

from six.moves import urllib_parse

from .base import AvailableFile, BaseRepository
from ..utils import canonicalize_name


@attr.s(cmp=False, frozen=True, slots=True)
class _HTMLRepository(BaseRepository):

    # TODO: Determine how we should actually set thse values.
    _ALLOWED_HASHES = frozenset(["md5", "sha256"])

    url = attr.ib()
    transport = attr.ib(hash=False, repr=False)

    def _get_project_url(self, project):
        raise NotImplementedError

    def _get_base_url(self, html):
        bases = [
            x for x in html.findall(".//base")
            if x.get("href") is not None
        ]

        if bases and bases[0].get("href"):
            return bases[0].get("href")
        else:
            return self.url

    def fetch(self, project):
        # TODO: Is there an order that we should be returning from this? Is
        #       that meaningful? Perhaps order of priority?
        # TODO: Do we want this to yield one item per file? One item per
        #       version with multiple files attached to it? what's most
        #       important here?
        #       - I think that we're likely to want to use a single item per
        #         file. This will work better when we combine multiple
        #         repositories into a single stream of files.

        # Fetch the data from the repository
        resp = self.transport.get(self._get_project_url(project))

        # Actually parse the HTML we've gotten now.
        html = html5lib.parse(
            resp.data,
            namespaceHTMLElements=False,
            transport_encoding=resp.encoding,
        )

        for anchor in html.findall(".//a"):
            # TODO: Should we filter out anything that isn't a valid file for
            #       this project? Or should we assume the repository is giving
            #       us correct information.
            href = anchor.get("href")
            if href:
                location = urllib_parse.urljoin(self._get_base_url(html), href)
                hashes = {}

                parsed_location = urllib_parse.urlparse(location)
                if parsed_location.fragment:
                    fragment = urllib_parse.parse_qs(parsed_location.fragment)
                    for key, value in fragment.items():
                        if key.lower() in self._ALLOWED_HASHES and value:
                            # We only support a single value for each type of
                            # hash, this makes sense because the same file
                            # should *always* hash to the same thing.
                            hashes[key.lower()] = value[0]

                yield AvailableFile(
                    project=project,
                    version=None,
                    location=urllib_parse.urldefrag(location).url,
                    hashes=hashes,
                )


class SimpleRepository(_HTMLRepository):

    def _get_project_url(self, project):
        return urllib_parse.urldefrag(
            urllib_parse.urljoin(self.url, canonicalize_name(project) + "/")
        ).url


class FlatHTMLRepository(_HTMLRepository):

    def _get_project_url(self, project):
        return urllib_parse.urldefrag(self.url).url
