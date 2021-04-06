# -*- coding: utf-8 -*-
"""
    Copyright (C) 2021 Tubed (plugin.video.tubed)

    This file is part of plugin.video.tubed

    SPDX-License-Identifier: GPL-2.0-only
    See LICENSES/GPL-2.0-only.txt for more information.
"""

import sys

from six.moves.urllib.parse import parse_qs, unquote, urlencode, urlparse

from xbmcgui import Dialog  # pylint: disable=import-error
import xbmcmediaimport  # pylint: disable=import-error

from .api import API
from .constants import ADDON_ID, MODES
from .constants import settings as csettings
from .dialogs.common import open_dialog
from .dialogs.sign_in import SignInDialog
from .generators.video import video_generator
from .lib.context import Context
from .lib.logger import Log
from .lib.privacy_policy import show_privacy_policy, was_privacy_policy_accepted
from .lib.url_utils import create_addon_path, parse_query
from .storage.favorite_playlists import FavoritePlaylists
from .storage.users import UserStorage

LOG = Log('mediaimporter', __file__)


def media_types_from_options(options):
    if 'mediatypes' not in options and 'mediatypes[]' not in options:
        return None

    media_types = None
    if 'mediatypes' in options:
        media_types = options['mediatypes']
    elif 'mediatypes[]' in options:
        media_types = options['mediatypes[]']

    return media_types


def provider2str(media_provider):
    if not media_provider:
        return 'unknown media provider'

    return '"%s" (%s)' % (media_provider.getFriendlyName(), media_provider.getIdentifier())


def import2str(media_import):
    if not media_import:
        return 'unknown media import'

    return '%s %s' % (provider2str(media_import.getProvider()), media_import.getMediaTypes())


def build_context_api(context):
    if not context:
        raise ValueError('invalid context')

    context.api = API(
        language=context.settings.language,
        region=context.settings.region
    )


def build_context(handle, mode=str(MODES.MAIN), query='', with_api=False):
    context = Context()

    if not query:
        query = '?mode=%s' % str(mode)

    # simulate the arguments
    argv = [
        create_addon_path(parameters={}),
        handle,
        query,
        'resume:false',
        ]
    context.argv = argv
    context.handle = handle

    context.query = parse_query(argv[2])
    context.mode = context.query.get('mode', str(MODES.MAIN))

    if with_api:
        build_context_api(context)

    return context


def login_with_google(handle, _):
    # retrieve the media provider
    media_provider = xbmcmediaimport.getProvider(handle)
    if not media_provider:
        LOG.error('cannot retrieve media provider')
        return

    context = build_context(handle, MODES.SIGN_IN)

    privacy_policy_accepted = show_privacy_policy(context)

    if not privacy_policy_accepted:
        return

    context.api = API(
        language=context.settings.language,
        region=context.settings.region
    )

    # TODO(Montellese): this closes the media provider info dialog
    signed_in = open_dialog(context, SignInDialog)
    if signed_in:
        Dialog().ok(
            context.i18n('Sign in with Google'),
            context.i18n('Sign in with Google was successful'))
    else:
        Dialog().ok(
            context.i18n('Sign in with Google'),
            context.i18n('Sign in with Google failed'))


def test_authentication(handle, _):
    # retrieve the media provider
    media_provider = xbmcmediaimport.getProvider(handle)
    if not media_provider:
        LOG.error('cannot retrieve media provider')
        return

    context = build_context(handle, MODES.SIGN_IN)

    dialog_title = context.i18n('Test authentication')

    if not was_privacy_policy_accepted(context):
        Dialog().ok(dialog_title, context.i18n("Tubed's Privacy Policy hasn't been accepted"))
        return

    context.api = API(
        language=context.settings.language,
        region=context.settings.region
    )

    if context.api.logged_in:
        Dialog().ok(dialog_title, context.i18n('Authentication succeeded'))
    else:
        Dialog().ok(dialog_title, context.i18n('Authentication failed'))


VIEW_KEY_MAP = {
    urlencode({ 'mode': str(MODES.MY_CHANNEL) }): 'My Channel',
    urlencode({ 'mode': str(MODES.LIKED_VIDEOS) }): 'Liked Videos',
    urlencode({
        'mode': str(MODES.PLAYLIST),
        'playlist_id': ''
        }): 'Watch Later',
    # urlencode({
    #     'mode': str(MODES.PLAYLISTS),
    #     'channel_id': 'mine'
    #     }): 'Playlists',
    # urlencode({ 'mode': str(MODES.SUBSCRIPTIONS) }): 'Subscriptions',
    # urlencode({ 'mode': str(MODES.FAVORITE_CHANNELS) }): 'Favorite Channels',
    urlencode({ 'mode': str(MODES.FAVORITE_PLAYLISTS) }): 'Favorite Playlists',
}


def view_key_to_label(context, users, view_key):
    if not context:
        raise ValueError('invalid context')
    if not users:
        raise ValueError('invalid users')
    if not view_key:
        raise ValueError('invalid view_key')

    tmp_view_key_map = VIEW_KEY_MAP.copy()
    for key in tmp_view_key_map.keys():
        view_key_decoded = parse_qs(key)
        if 'playlist_id' in view_key_decoded:
            # get the view's label
            view_label = tmp_view_key_map[key]
            # delete the old view
            del tmp_view_key_map[key]
            # fix the view key
            view_key_decoded['playlist_id'] = users.watchlater_playlist
            # store the fixed view (key)
            tmp_view_key_map[urlencode(view_key_decoded)] = view_label

    if view_key not in tmp_view_key_map:
        return None

    return context.i18n(VIEW_KEY_MAP[view_key])


def get_views(context, users, view_keys):
    if not context:
        raise ValueError('invalid context')
    if not users:
        raise ValueError('invalid users')
    if not view_keys:
        raise ValueError('invalid view_keys')

    views = [ (view_key_to_label(context, users, view_key), view_key) for view_key in view_keys ]
    return [view for view in views if view[0] is not None and view[1] is not None]


def setting_options_filler_views(handle, _):
    # retrieve the media import
    media_import = xbmcmediaimport.getImport(handle)
    if not media_import:
        LOG.error('cannot retrieve media import')
        return

    # prepare and get the media provider settings
    settings = media_import.prepareSettings()
    if not settings:
        LOG.error('cannot prepare media import settings')
        return

    context = build_context(handle)
    users = UserStorage()

    view_keys = [
        urlencode({ 'mode': str(MODES.MY_CHANNEL) }),
        urlencode({ 'mode': str(MODES.LIKED_VIDEOS) }),
        urlencode({
            'mode': str(MODES.PLAYLIST),
            'playlist_id': users.watchlater_playlist
            }),
        # urlencode({
        #     'mode': str(MODES.PLAYLISTS),
        #     'channel_id': 'mine'
        #     }),
        # urlencode({ 'mode': str(MODES.SUBSCRIPTIONS) }),
        # urlencode({ 'mode': str(MODES.FAVORITE_CHANNELS) }),
        urlencode({ 'mode': str(MODES.FAVORITE_PLAYLISTS) }),
    ]

    views = get_views(context, users, view_keys)

    # pass the list of views back to Kodi
    settings.setStringOptions(csettings.MEDIA_IMPORT_SETTINGS_IMPORT_VIEWS, views)


def import_my_channel(handle, context, users, max_items_per_view):
    items = []

    # determine the user's channel
    payload = context.api.channel_by_username('mine')
    channel_id = payload.get('items', [{}])[0].get('id', '')
    if not channel_id:
        LOG.warning('failed to determine channel id of \"My Channel\"')
        return items

    # determine the playlist id of the user's channel
    payload = context.api.channels(channel_id=channel_id)
    channel_item = payload.get('items', [{}])[0]
    upload_playlist_id = channel_item.get('contentDetails', {}) \
        .get('relatedPlaylists', {}).get('uploads', '')

    if not upload_playlist_id:
        LOG.warning('failed to determine playlist id of \"My Channel\" (%s)' % channel_id)
        return items

    return import_playlist(
        handle, context, users, max_items_per_view, upload_playlist_id, mine=True)


def import_liked_videos(handle, context, _, max_items_per_view):
    items = []
    page_token = ''

    while len(items) < max_items_per_view:
        if xbmcmediaimport.shouldCancel(handle, len(items), max_items_per_view):
            return None

        payload = context.api.my_rating(
            rating='like',
            page_token=page_token,
            fields='items(kind,id)'
        )
        retrieved_items = \
            list(video_generator(context, payload.get('items', [])))
        if not retrieved_items:
            break

        items.extend([item[1] for item in retrieved_items])

        # check if there are more items available
        page_token = payload.get('nextPageToken')
        if not page_token:
            break

    return items

def import_playlist(handle, context, users, max_items_per_view, playlist_id, mine=False):
    items = []
    if not playlist_id:
        return items

    if not mine and playlist_id in [users.watchlater_playlist, users.history_playlist]:
        mine = True

    page_token = ''
    while len(items) < max_items_per_view:
        if xbmcmediaimport.shouldCancel(handle, len(items), max_items_per_view):
            return None

        payload = context.api.playlist_items(
            playlist_id,
            page_token=page_token,
            fields='items(kind,id,snippet(playlistId,resourceId/videoId))'
        )
        retrieved_items = list(video_generator(context, payload.get('items', []), mine=mine))
        if not retrieved_items:
            break

        items.extend([item[1] for item in retrieved_items])

        # check if there are more items available
        page_token = payload.get('nextPageToken')
        if not page_token:
            break

    return items

def import_favorite_playlists(handle, context, users, max_items_per_view):
    items = []
    page = 1

    favorite_playlists = FavoritePlaylists(users.uuid, max_items_per_view)
    while len(items) < max_items_per_view:
        if xbmcmediaimport.shouldCancel(handle, len(items), max_items_per_view):
            return None

        playlists = favorite_playlists.list((page - 1) * max_items_per_view, max_items_per_view)
        playlist_ids = [playlist_id for playlist_id, _ in playlists]

        for playlist_id in playlist_ids:
            if xbmcmediaimport.shouldCancel(handle, len(items), max_items_per_view):
                return None

            items.extend(import_playlist(handle, context, users, max_items_per_view, playlist_id))

        if len(items) >= max_items_per_view:
            break

        # check if there are more playlists available
        if favorite_playlists.list(page * max_items_per_view, 1):
            page = page + 1
        else:
            break

    return items


def can_import(handle, options):
    if "path" not in options:
        LOG.info('cannot execute "canimport" without path')
        xbmcmediaimport.setCanImport(handle, False)
        return

    expected_path = 'plugin://%s' % ADDON_ID
    path = unquote(options["path"][0])

    xbmcmediaimport.setCanImport(handle, path == expected_path)


def is_provider_ready(handle, _):
    # retrieve the media provider
    media_provider = xbmcmediaimport.getProvider(handle)
    if not media_provider:
        LOG.error('cannot retrieve media provider')
        xbmcmediaimport.setProviderReady(handle, False)
        return

    # prepare the media provider settings
    if not media_provider.prepareSettings():
        LOG.error('cannot prepare media provider settings')
        xbmcmediaimport.setProviderReady(handle, False)
        return

    context = build_context(handle, MODES.SIGN_IN)

    provider_ready = False
    if was_privacy_policy_accepted(context):
        build_context_api(context)

        provider_ready = context.api.logged_in

    xbmcmediaimport.setProviderReady(handle, provider_ready)


def is_import_ready(handle, _):
    # retrieve the media import
    media_import = xbmcmediaimport.getImport(handle)
    if not media_import:
        LOG.error('cannot retrieve media import')
        xbmcmediaimport.setImportReady(handle, False)
        return

    # prepare and get the media import settings
    import_settings = media_import.prepareSettings()
    if not import_settings:
        LOG.error('cannot prepare media import settings')
        xbmcmediaimport.setImportReady(handle, False)
        return

    context = build_context(handle, MODES.SIGN_IN)

    import_ready = False
    if was_privacy_policy_accepted(context):
        context.api = API(
            language=context.settings.language,
            region=context.settings.region
        )

        # retrieve all selected import views
        import_views = \
            import_settings.getStringList(csettings.MEDIA_IMPORT_SETTINGS_IMPORT_VIEWS)

        if context.api.logged_in and len(import_views) > 0:
            import_ready = True

    xbmcmediaimport.setImportReady(handle, import_ready)


def load_provider_settings(handle, _):
    # retrieve the media provider
    media_provider = xbmcmediaimport.getProvider(handle)
    if not media_provider:
        LOG.error('cannot retrieve media provider')
        xbmcmediaimport.setProviderSettingsLoaded(handle, False)
        return

    settings = media_provider.getSettings()
    if not settings:
        LOG.error('cannot retrieve media provider settings')
        xbmcmediaimport.setProviderSettingsLoaded(handle, False)
        return

    # register action callbacks
    settings.registerActionCallback(csettings.MEDIA_PROVIDER_SETTINGS_GOOGLE_LOGIN, 'googlelogin')
    settings.registerActionCallback(
        csettings.MEDIA_PROVIDER_SETTINGS_TEST_AUTHENTICATION, 'testauthentication')

    settings.setLoaded()
    xbmcmediaimport.setProviderSettingsLoaded(handle, True)


def load_import_settings(handle, _):
    # retrieve the media import
    media_import = xbmcmediaimport.getImport(handle)
    if not media_import:
        LOG.error('cannot retrieve media import')
        xbmcmediaimport.setImportSettingsLoaded(handle, False)
        return

    settings = media_import.getSettings()
    if not settings:
        LOG.error('cannot retrieve media import settings')
        xbmcmediaimport.setImportSettingsLoaded(handle, False)
        return

    # register a setting options fillers
    settings.registerOptionsFillerCallback(
        csettings.MEDIA_IMPORT_SETTINGS_IMPORT_VIEWS, 'settingoptionsfillerviews')

    settings.setLoaded()
    xbmcmediaimport.setImportSettingsLoaded(handle, True)

def can_update_metadata_on_provider(handle, _):
    xbmcmediaimport.setCanUpdateMetadataOnProvider(handle, False)


def can_update_playcount_on_provider(handle, _):
    xbmcmediaimport.setCanUpdatePlaycountOnProvider(handle, False)


def can_update_last_played_on_provider(handle, _):
    xbmcmediaimport.setCanUpdateLastPlayedOnProvider(handle, False)


def can_update_resume_position_on_provider(handle, _):
    xbmcmediaimport.setCanUpdateResumePositionOnProvider(handle, False)


def exec_import(handle, options):
    # parse all necessary options
    media_types = media_types_from_options(options)
    if not media_types:
        LOG.error('cannot execute "import" without media types')
        return

    # retrieve the media import
    media_import = xbmcmediaimport.getImport(handle)
    if not media_import:
        LOG.error('cannot retrieve media import')
        return

    # prepare and get the media import settings
    import_settings = media_import.prepareSettings()
    if not import_settings:
        LOG.error('cannot prepare media import settings')
        return

    # retrieve the media provider
    media_provider = media_import.getProvider()
    if not media_provider:
        LOG.error('cannot retrieve media provider')
        return

    context = build_context(handle)
    users = UserStorage()

    # retrieve the configured views to synchronize
    view_keys = import_settings.getStringList(csettings.MEDIA_IMPORT_SETTINGS_IMPORT_VIEWS)
    views = get_views(context, users, view_keys)
    max_items_per_view = \
        import_settings.getInt(csettings.MEDIA_IMPORT_SETTINGS_MAX_ENTRIES_PER_VIEW)

    LOG.info('importing %s items...' % media_types)

    # loop over all media types to be imported
    progress = 0
    progress_total = len(media_types)
    for media_type in media_types:
        # check if we need to cancel importing items
        if xbmcmediaimport.shouldCancel(handle, progress, progress_total):
            return
        progress += 1

        # loop over all views
        view_progress_total = len(views)
        for view_progress, view in enumerate(views):
            (view_label, view_key) = view
            LOG.info('importing %s items from %s...' % (media_type, view_label))

            # report the progress status
            xbmcmediaimport.setProgressStatus(
                handle,
                context.i18n('Retrieving %s from %s...') % (media_type, view_label)
                )

            if xbmcmediaimport.shouldCancel(handle, view_progress, view_progress_total):
                return

            # get a specific context for the mode
            specific_context = build_context(handle, query=view_key, with_api=True)

            view_mode = specific_context.mode
            if not view_mode:
                LOG.error('failed to build context for view "%s" (%s)' % (view_label, view_key))
                continue

            items = []

            # retrieve items depending on the mode
            if view_mode == str(MODES.MY_CHANNEL):
                items = import_my_channel(handle, specific_context, users, max_items_per_view)
            elif view_mode == str(MODES.LIKED_VIDEOS):
                items = import_liked_videos(handle, specific_context, users, max_items_per_view)
            elif view_mode == str(MODES.PLAYLIST):
                playlist_id = specific_context.query.get('playlist_id')
                items = import_playlist(
                    handle, specific_context, users, max_items_per_view, playlist_id)
            elif view_mode == str(MODES.FAVORITE_PLAYLISTS):
                items = import_favorite_playlists(
                    handle, specific_context, users, max_items_per_view)

            # abort if necessary
            if items is None:
                return

            if len(items) > max_items_per_view:
                items = items[:max_items_per_view]

            if items:
                # pass the imported items back to Kodi
                LOG.info('%d %s items imported from %s' % (len(items), media_type, view_label))
                xbmcmediaimport.addImportItems(handle, items, media_type)

    # finish the import
    xbmcmediaimport.finishImport(handle, isChangeset=False)


def update_on_provider(handle, _):
    # not supported
    xbmcmediaimport.finishUpdateOnProvider(handle)


ACTIONS = {
    # official media import callbacks
    # mandatory
    "canimport": can_import,
    "isproviderready": is_provider_ready,
    "isimportready": is_import_ready,
    "loadprovidersettings": load_provider_settings,
    "loadimportsettings": load_import_settings,
    "canupdatemetadataonprovider": can_update_metadata_on_provider,
    "canupdateplaycountonprovider": can_update_playcount_on_provider,
    "canupdatelastplayedonprovider": can_update_last_played_on_provider,
    "canupdateresumepositiononprovider": can_update_resume_position_on_provider,
    "import": exec_import,
    "updateonprovider": update_on_provider,
    # custom setting callbacks
    'googlelogin': login_with_google,
    'testauthentication': test_authentication,
    # custom setting options fillers
    'settingoptionsfillerviews': setting_options_filler_views,
}


def invoke(argv):
    path = argv[0]
    handle = int(argv[1])

    options = None
    if len(argv) > 2:
        # get the options but remove the leading ?
        params = argv[2][1:]
        if params:
            options = parse_qs(params)

    LOG.debug('path = %s, handle = %s, options =%s' % (path, handle, params))

    url = urlparse(path)
    action = url.path
    if action[0] == "/":
        action = action[1:]

    if action not in ACTIONS:
        LOG.error('cannot process unknown action: %s' % action)
        sys.exit(0)

    action_method = ACTIONS[action]
    if not action_method:
        LOG.warning('action not implemented: %s' % action)
        sys.exit(0)

    LOG.debug('executing action "%s"...' % action)
    action_method(handle, options)
