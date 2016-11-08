# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import attr

from .base import BaseRepository


@attr.s(cmp=False, frozen=True, slots=True)
class FilteredRepository(BaseRepository):

    repository = attr.ib()
    _predicate = attr.ib(repr=False, hash=False)

    def fetch(self, project):
        for item in filter(self._predicate, self.repository.fetch(project)):
            yield item


@attr.s(cmp=False, frozen=True, slots=True)
class MultiRepository(BaseRepository):

    repositories = attr.ib()

    def fetch(self, project):
        for repository in self.repositories:
            for item in repository.fetch(project):
                yield item
