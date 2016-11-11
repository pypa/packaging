# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import abc

import attr
import six


@attr.s(cmp=False, frozen=True, slots=True)
class Response(object):

    url = attr.ib()
    content = attr.ib(repr=False)
    headers = attr.ib(default=attr.Factory(dict), repr=False)


class BaseTransport(six.with_metaclass(abc.ABCMeta, object)):

    @abc.abstractmethod
    def get(self, url):
        """
        Gets the data represented by a specific URL.
        """
