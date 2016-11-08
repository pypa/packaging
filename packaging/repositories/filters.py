# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import attr


@attr.s(cmp=False, frozen=True, init=False)
class ProjectFilter:

    projects = attr.ib(default=attr.Factory(list))

    def __init__(self, *projects):
        self.__dict__["projects"] = list(projects)

    @property
    def blacklist(self):
        if not hasattr(self, "_blacklist"):
            self.__dict__["_blacklist"] = [
                p[1:] for p in self.projects if p.startswith("!")
            ]

        return self._blacklist

    @property
    def whitelist(self):
        if not hasattr(self, "_whitelist"):
            self.__dict__["_whitelist"] = [
                p for p in self.projects if not p.startswith("!")
            ]

        return self._whitelist

    def __call__(self, item):
        # If the project is in our blacklist, then we can go ahead and reject
        # it up front because no matter what if it appears here then it is
        # rejected.
        if item.project in self.blacklist:
            return False
        # If the project is in our whitelist, then we can go ahead and allow it
        # now. If it is in both the whitelist and the blacklist, the first
        # conditional will have already rejected it.
        elif item.project in self.whitelist:
            return True
        # If we have any whitelisted projects at all, then we can just blindly
        # reject anything else at this point because we've already checked for
        # the project to exist in our whitelist and it did not pass that.
        elif self.whitelist:
            return False
        # If we do not have a whitelist (e.g. this is a blacklist only filter)
        # and we've gotten to this point, then our first conditional would have
        # ensured that any blacklisted items are already rejected and the
        # check for a whitelist would have ensured we are not filtering to only
        # specific projects, so we can just go ahead and blindly allow.
        else:
            return True


@attr.s(cmp=False, frozen=True, slots=True)
class FormatFilter:

    wheel = attr.ib(default=True)
    sdist = attr.ib(default=True)

    def __call__(self, item):
        # TODO: This should ideally be a lot smarter, but this is good enough
        #       for now.
        if item.location.endswith(".whl"):
            return self.wheel
        elif item.location.endswith((".zip", ".tar.gz")):
            return self.sdist

        return False
