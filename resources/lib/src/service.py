# -*- coding: utf-8 -*-
"""
    Copyright (C) 2020 Tubed (plugin.video.tubed)

    This file is part of plugin.video.tubed

    SPDX-License-Identifier: GPL-2.0-only
    See LICENSES/GPL-2.0-only.txt for more information.
"""

import os

import xbmc  # pylint: disable=import-error
import xbmcaddon  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error
import xbmcmediaimport  # pylint: disable=import-error
import xbmcvfs  # pylint: disable=import-error

from .constants import ADDONDATA_PATH, ADDON_ID
from .lib.context import Context
from .lib.logger import Log
from .lib.memoizer import reset_cache
from .lib.playback import CallbackPlayer


LOG = Log('service', __file__)

def invoke():
    reset_cache()

    user_lock = os.path.join(ADDONDATA_PATH, 'users.lock')
    if xbmcvfs.exists(user_lock):
        xbmcvfs.delete(user_lock)

    sleep_time = 10

    context = Context()
    window = xbmcgui.Window(10000)
    player = CallbackPlayer(context=context, window=window)
    monitor = xbmc.Monitor()

    # register media provider
    addon = xbmcaddon.Addon()
    provider_id = 'plugin://%s' % ADDON_ID
    provider_name = addon.getAddonInfo('name')
    provider_icon_url = xbmc.translatePath(addon.getAddonInfo('icon'))
    supported_media_types = set(
        [
            xbmcmediaimport.MediaTypeMusicVideo,
        ]
    )

    # create the media provider
    media_provider = xbmcmediaimport.MediaProvider(
        provider_id, provider_name, provider_icon_url, supported_media_types
    )

    # add the media provider and activate it
    if xbmcmediaimport.addAndActivateProvider(media_provider):
        LOG.info('%s (%s) successfully added as a media provider' % (provider_name, provider_id))
    else:
        LOG.warning('failed to add %s (%s) as a media provider' % (provider_name, provider_id))

    while not monitor.abortRequested():
        if monitor.waitForAbort(sleep_time):
            break

    player.cleanup_threads(only_ended=False)
