# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import abc

import attr
import six


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
