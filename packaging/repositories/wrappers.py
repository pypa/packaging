# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import itertools

import attr

from twisted.internet.defer import gatherResults

from .base import BaseRepository


@attr.s(cmp=False, frozen=True, slots=True)
class FilteredRepository(BaseRepository):

    repository = attr.ib()
    _predicate = attr.ib(repr=False, hash=False)

    def fetch(self, project):
        d = self.repository.fetch(project)
        d.addCallback(lambda results: list(filter(self._predicate, results)))

        return d


@attr.s(cmp=False, frozen=True, slots=True)
class MultiRepository(BaseRepository):

    repositories = attr.ib()

    def fetch(self, project):
        d = gatherResults(
            [r.fetch(project) for r in self.repositories],
            consumeErrors=True,
        )
        d.addCallback(lambda r: list(itertools.chain.from_iterable(r)))

        return d
