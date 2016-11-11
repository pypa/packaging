# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import functools

import attr

from .base import Response


@attr.s(cmp=False)
class _RepositoryFetcher:

    _coro = attr.ib()
    _finished = attr.ib(default=False, init=False)
    _result = attr.ib(default=None, init=False)

    @property
    def finished(self):
        return self._finished

    def pending_requests(self):
        if self.finished:
            return
        yield next(self._coro)

    def add_response(self, req, content, headers=None):
        try:
            self._coro.send(Response(req, content, headers=headers))
        except StopIteration as exc:
            self._finished = True
            self._result = exc.value

    def get_files(self):
        if not self.finished:
            raise RuntimeError(
                "Cannot get files until all data has been fetched."
            )
        return self._result


def as_fetcher(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return _RepositoryFetcher(fn(*args, **kwargs))
    return wrapper
