# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import abc
import cgi

import attr
import six

from six.moves import urllib_parse


@attr.s(cmp=False, frozen=True, slots=True)
class AvailableFile(object):

    # TODO: What is the appropiate data structure for this? We need to
    #       correctly support the case where the only things we really know
    #       about the project is the items available in the old legacy/simple
    #       repository API, however we also need to think about the future when
    #       we have more information than that available to us.

    project = attr.ib()
    version = attr.ib()
    location = attr.ib()
    hashes = attr.ib(default=attr.Factory(dict), repr=False, hash=False)


class BaseRepository(six.with_metaclass(abc.ABCMeta, object)):

    @abc.abstractmethod
    def fetch(self, project):
        """
        Find all available distributions in the repository for a project named
        `project`.
        """


@attr.s(cmp=False, frozen=True, slots=True)
class Response(object):

    url = attr.ib()
    data = attr.ib(repr=False)
    encoding = attr.ib(repr=False)


class BaseTransport(six.with_metaclass(abc.ABCMeta, object)):

    @abc.abstractmethod
    def get(self, url):
        """
        Gets the data represented by a specific URL, returning the content as
        a tuple of
        """


class RequestsTransport(BaseTransport):

    def __init__(self, session=None):
        if session is None:
            import requests
            session = requests.session()

        self._session = session

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
            return None

        # Detect what the character set of the transport is.
        _, params = cgi.parse_header(resp.headers.get("Content-Type", ""))
        encoding = params.get("charset")

        return Response(url=url, data=resp.content, encoding=encoding)


@attr.s(cmp=False, frozen=True, slots=True)
class Transports(BaseTransport):

    schemes = attr.ib()

    def _transport_for_url(self, url):
        return self.schemes[urllib_parse.urlparse(url).scheme]

    def get(self, url):
        return self._transport_for_url(url).get(url)
