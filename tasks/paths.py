# SPDX-FileCopyrightText: 2014-2022 Donald Stufft and individual contributors. All rights reserved.
#
# SPDX-License-Identifier: BSD-2-Clause OR Apache-2.0

# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import os.path

PROJECT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

CACHE = os.path.join(PROJECT, ".cache")
