# -*- coding: utf-8 -*-
"""
    Copyright (C) 2021 Tubed (plugin.video.tubed)

    This file is part of plugin.video.tubed

    SPDX-License-Identifier: GPL-2.0-only
    See LICENSES/GPL-2.0-only.txt for more information.
"""

import sys

from src import mediaimporter  # pylint: disable=import-error

mediaimporter.invoke(sys.argv)
