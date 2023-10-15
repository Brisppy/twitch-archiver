"""
Class for retrieving and storing a Twitch VOD and its associated information.
"""
import logging
import re
from datetime import datetime, timezone
from math import floor
from random import randrange
from time import sleep

import m3u8

from twitcharchiver.api import Api
from twitcharchiver.channel import Channel
from twitcharchiver.twitch import Category, Chapters, MpegSegment
from twitcharchiver.exceptions import TwitchAPIErrorForbidden
from twitcharchiver.utils import time_since_date, get_stream_id_from_preview_url


class Vod:
    def __init__(self, vod_id: int = 0, vod_info: dict = None):
        self._log = logging.getLogger()
        self._api: Api = Api()

        self.v_id: int = vod_id
        self.s_id: int = 0

        self.category: Category = Category()
        self.channel: Channel = Channel()
        self.created_at: float = 0
        self.description: str = ""
        self.duration: int = 0
        self.published_at: float = 0
        self.thumbnail_url: str = ""
        self.title: str = ""
        self.view_count: int = 0

        self.muted_segments: list = []

        if vod_id != 0:
            self.set(vod_id)

        if vod_info:
            self._parse_dict(vod_info)

    def __eq__(self, other):
        """
        VODs are compared for equality based on their VOD ID (id) alone.

        :return: True if VODs have the same ID
        :rtype: bool
        """
        if isinstance(other, self.__class__):
            return self.v_id == other.v_id

        return False

    def __repr__(self):
        return str(self.get_info())

    def __bool__(self):
        return bool(self.v_id or self.s_id)

    def set(self, vod_id: int):
        """
        Sets the VOD ID and retrieves its information.
        """
        self.v_id = vod_id
        self._fetch_metadata()

    def _parse_dict(self, vod_info: dict):
        _vod = Vod()
        self._log.debug('Parsing provided metadata for VOD %s: %s', self.v_id, vod_info)

        # reformat to database schema
        self.channel = Channel()
        self.category = Category(vod_info['game'])
        self.created_at = \
            datetime.strptime(vod_info['createdAt'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
        self.description = vod_info['description']
        self.duration = vod_info['lengthSeconds']
        self.published_at = \
            datetime.strptime(vod_info['publishedAt'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
        self.thumbnail_url = vod_info['previewThumbnailURL']
        self.title = vod_info['title']
        self.view_count = vod_info['viewCount']

    def _fetch_metadata(self):
        """
        Retrieves metadata for a given VOD ID. Formatting is done to ensure backwards compatibility.
        """
        _channel = self.get_vod_owner()

        _r = self._api.gql_request('VideoMetadata', 'c25707c1e5176320ceac6b447d052480887e23bc794ca1d02becd0bcc91844fe',
                                   {'channelLogin': _channel.name, 'videoID': str(self.v_id)})

        _vod_info = _r.json()[0]['data']['video']
        self._parse_dict(_vod_info)

        self.muted_segments = self.get_muted_segments()

        self._log.debug('Filled metadata for VOD %s: %s', self.v_id, self.get_info())

    def time_since_live(self):
        _seconds_since_start = time_since_date(self.created_at)

        self._log.debug('VOD %s has been live for %s seconds.', self.v_id, _seconds_since_start)
        return _seconds_since_start

    def refresh_vod_metadata(self):
        """
        Refreshes metadata for VOD.
        """
        self._fetch_metadata()

    def get_info(self):
        """
        Returns all relevant VOD information.

        :return: dictionary of stored VOD values
        :rtype: dict
        """
        _vod_info = {'vod_id': self.v_id, 'stream_id': self.s_id, 'channel': self.channel,
                     'title': self.title, 'description': self.description, 'created_at': self.created_at,
                     'published_at': self.published_at, 'thumbnail_url': self.thumbnail_url,
                     'view_count': self.view_count, 'duration': self.duration, 'muted_segments': self.muted_segments}

        self._log.debug('VOD information: %s', _vod_info)
        return _vod_info

    def get_category(self):
        """Retrieves Twitch category for a specified VOD.

        :return: name of category / game
        :rtype: Category
        """
        _r = self._api.gql_request('ComscoreStreamingQuery',
                                   'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                                   {"channel": "", "clipSlug": "", "isClip": False, "isLive": False,
                                    "isVodOrCollection": True, "vodID": str(self.v_id)})

        _vod_category = Category(_r.json()[0]['data']['video']['game'])
        self._log.debug('Category for VOD %s is %s', self.v_id, _vod_category.get_category_info)

        return _vod_category

    def is_live(self):
        """
        Determines whether the VOD is a currently live broadcast.

        :return: True if VOD live
        :rtype: bool
        """
        # wait until 1m has passed since vod created time as the stream api may not have updated yet
        _time_since_created = time_since_date(self.created_at)
        if _time_since_created < 60:
            self._log.debug('VOD for channel with id %s created < 60 seconds ago, delaying status retrieval.',
                            self.channel.name)
            sleep(60 - _time_since_created)

        # check if channel is offline
        _stream_info = self.channel.get_stream_info()

        if _stream_info:
            try:
                # if stream live and vod start time matches
                _stream_created_time = \
                    datetime.strptime(_stream_info['stream']['createdAt'], '%Y-%m-%dT%H:%M:%SZ').timestamp()

                # if vod created within 10s of stream created time
                if 10 >= self.created_at - _stream_created_time >= -10:
                    self._log.debug(
                        'VOD creation time (%s) is within 10s of stream created time (%s), running in live mode.',
                        self.created_at, _stream_created_time)
                    return True

            except IndexError:
                pass

            self._log.debug('Stream status could not be retrieved for %s.', self.channel.name)
            return False

        self._log.debug('%s is offline and so VOD must be offline.', self.channel.name)
        return False

    def get_chapters(self):
        """Retrieves the chapters for a given Twitch VOD.

        :return: Retrieves any chapters for the VOD, or a single chapter with the VOD category otherwise.
        :rtype: list[Chapters]
        """
        _r = self._api.gql_request('VideoPlayer_ChapterSelectButtonVideo',
                                   '8d2793384aac3773beab5e59bd5d6f585aedb923d292800119e03d40cd0f9b41',
                                   {"includePrivate": False, "videoID": str(self.v_id)})

        # extract and return list of moments from returned json
        _chapters = Chapters([node['node'] for node in _r.json()[0]['data']['video']['moments']['edges']])

        try:
            self._log.debug('Chapters for VOD %s: %s', self.v_id, _chapters)
            return _chapters

        except TypeError:
            self._log.debug('No chapters found for VOD %s.', self.v_id)
            # create single chapter out of VOD category
            _category = self.get_category()
            _chapters = Chapters()
            _chapters.create_chapter_from_category(_category, self.duration)

            self._log.debug('Chapters generated for VOD based on %s: %s', _category, self.v_id)
            return _chapters

    def get_muted_segments(self):
        """Retrieves any muted segments for the VOD.

        :return: muted segments
        :rtype: list[MpegSegment]
        """
        _r = self._api.gql_request('VideoPlayer_MutedSegmentsAlertOverlay',
                                   'c36e7400657815f4704e6063d265dff766ed8fc1590361c6d71e4368805e0b49',
                                   {'includePrivate': False, 'vodID': str(self.v_id)})

        _segments = _r.json()[0]['data']['video']['muteInfo']['mutedSegmentConnection']

        if _segments:
            _muted_segments = [MpegSegment(s['offset'], s['duration'], muted=True) for s in _segments['nodes']]
            self._log.debug('Muted segments for VOD %s: %s', self.v_id, _muted_segments)
            return _muted_segments

        self._log.debug('No muted segments found for VOD %s.', self.v_id)
        return []

    def get_vod_owner(self):
        """Retrieves the channel which a given VOD belongs to

        :return: Channel containing `id` and `name` of VOD owner
        :rtype: Channel
        """
        _r = self._api.gql_request('ComscoreStreamingQuery',
                                   'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                                   {"channel": "", "clipSlug": "", "isClip": False, "isLive": False,
                                    "isVodOrCollection": True, "vodID": str(self.v_id)})

        _owner = _r.json()[0]['data']['video']['owner']
        _channel = Channel(_owner['displayName'])
        self._log.debug('Owner of VOD %s is %s.', self.v_id, _channel)

        return _channel

    def get_stream_id(self):
        """Retrieves the associated stream ID for the VOD

        :return: stream id
        :rtype: int
        """
        _r = self._api.gql_request('VideoPlayer_VODSeekbarPreviewVideo',
                                   '07e99e4d56c5a7c67117a154777b0baf85a5ffefa393b213f4bc712ccaf85dd6',
                                   {'includePrivate': False, 'videoID': str(self.v_id)})

        _stream_id = get_stream_id_from_preview_url(_r.json()[0]['data']['video']['seekPreviewsURL'])

        self._log.debug('Stream ID for VOD %s: %s', self.v_id, _stream_id)
        return _stream_id

    def get_index_url(self, quality: str = 'best'):
        """Retrieves an index of m3u8 streams for a given VOD.

        :param quality: desired quality in the format [resolution]p[framerate] or 'best', 'worst'
        :type quality: str
        :return: url of m3u8 playlist
        :rtype: str
        """
        _access_token = self._get_playback_access_token()

        _p = {
            'player': 'twitchweb',
            'nauth': _access_token['value'],
            'nauthsig': _access_token['signature'],
            'allow_source': 'true',
            'playlist_include_framerate': 'true',
            'p': randrange(1000000, 9999999)
        }

        try:
            _r = self._api.get_request(f'https://usher.ttvnw.net/vod/{self.v_id}.m3u8', p=_p)
            _index = m3u8.loads(_r.text)

            # grab 'name' of m3u8 streams - contains [resolution]p[framerate]
            _available_resolutions = [m[0].group_id.split('p') for m in [m.media for m in _index.playlists] if
                                      m[0].group_id != 'chunked']
            # insert 'chunked' stream separately as its named differently
            _available_resolutions.insert(0, _index.media[0].name.split('p'))

            _index_url = _index.playlists[self.get_quality_index(quality, _available_resolutions)].uri
            self._log.debug('Index for VOD %s: %s', self.v_id, _index_url)

            return _index_url

        # catch for sub-only VODs
        except TwitchAPIErrorForbidden:
            self._log.debug('VOD %s is subscriber-only. Generating index URL.', self.v_id)
            # retrieve cloudfront storage location from VOD thumbnail
            _cf_info = self.thumbnail_url.split('/')
            _cf_domain = _cf_info[4]
            _vod_uid = _cf_info[5]

            # parse user-provided quality
            if quality == 'best':
                quality = 'chunked'
            elif quality == 'worst':
                quality = '160p30'
            else:
                quality = 'p'.join(quality)

            # create index url
            _index_url = f'https://{_cf_domain}.cloudfront.net/{_vod_uid}/{quality}/index-dvr.m3u8'
            self._log.debug('Index URL for %s: %s', self.channel.name, _index_url)

            return _index_url

    def _get_playback_access_token(self):
        """
        Gets a playback access token for the VOD.

        :return: dictionary of playback access token values if any
        :rtype: dict
        """
        # only accepts the default client ID for non-authenticated clients
        _h = {'Client-Id': 'ue6666qo983tsx6so1t0vnawi233wa'}
        _q = """
        {{
            videoPlaybackAccessToken(
                id: {vod_id},
                params: {{
                    platform: "web",
                    playerBackend: "mediaplayer",
                    playerType: "site"
                }}
            ) {{
                signature
                value
            }}
        }}
        """.format(vod_id=self.v_id)
        _r = self._api.post_request('https://gql.twitch.tv/gql', j={'query': _q}, h=_h)

        _token = _r.json()['data']['videoPlaybackAccessToken']

        if _token:
            self._log.debug('Token retrieved for VOD %s: %s', self.v_id, _token)
            return _token

        self._log.debug('Token could not be retrieved for VOD %s: %s', self.v_id, _r.text)
        return ""

    def get_index_playlist(self, index_url: str = ""):
        """
        Retrieves the playlist for a given VOD index along with updating the VOD duration.
        """

        _vod_playlist = self._api.get_request(index_url).text

        # update vod json with m3u8 duration - more accurate than twitch API
        _m = re.findall(r'(?<=#EXT-X-TWITCH-TOTAL-SECS:).*(?=\n)', _vod_playlist)[0]
        self.duration = floor(float(_m))

        return _vod_playlist

    def get_quality_index(self, desired_quality, available_qualities):
        """Finds the index of a user defined quality from a list of available stream qualities.

        :param desired_quality: desired quality to search for - best, worst or [resolution, framerate]
        :param available_qualities: list of available qualities as [[resolution, framerate], ...]
        :return: list index of desired quality if found
        """
        if desired_quality not in ['best', 'worst']:
            # look for user defined quality in available streams
            try:
                return available_qualities.index(desired_quality)

            except ValueError:
                self._log.info('User requested quality not found in available streams.')
                # grab first resolution match
                try:
                    return [quality[0] for quality in available_qualities].index(desired_quality[0])

                except ValueError:
                    self._log.info('No match found for user requested resolution. Defaulting to best.')
                    return 0

        elif desired_quality == 'worst':
            return -1

        else:
            return 0

    @staticmethod
    def from_stream_json(stream_json):
        # return empty VOD if no stream
        if not stream_json['stream']:
            return Vod()

        _stream = Vod()
        _stream.s_id = stream_json['stream']['id']

        _stream.category = Category(stream_json['stream']['game'])
        _stream.channel = Channel(stream_json['displayName'])
        _stream.created_at = datetime.strptime(stream_json['stream']['createdAt'],
                                                   '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
        _stream.duration = time_since_date(_stream.created_at)
        _stream.published_at = _stream.created_at
        _stream.title = stream_json['broadcastSettings']['title']

        return _stream


class ArchivedVod(Vod):
    """
    Defines an archive of a VOD. Used for tracking the status of previously archived VODs.
    """
    def __init__(self, vod: Vod, chat_archived: bool = False, video_archived: bool = False):
        super().__init__()
        self._convert_from_vod(vod)
        self.chat_archived: bool = chat_archived
        self.video_archived: bool = video_archived

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.v_id == other.v_id and self.chat_archived == other.chat_archived \
                and self.video_archived == other.video_archived
        return False

    @staticmethod
    def import_from_db(*args):
        """
        Creates a new ArchivedVod with values from the provided database return. We can't fetch this from Twitch as
        they delete the records when the VOD expires or is manually deleted.
        """
        _archived_vod = ArchivedVod(args[4], args[5])
        _archived_vod.v_id = args[0]
        _archived_vod.s_id = args[1]
        _archived_vod.channel = args[2]
        _archived_vod.created_at = args[3]

        return _archived_vod

    def _convert_from_vod(self, vod: Vod):
        """
        Converts an existing VOD into an ArchivedVod.

        :param vod: VOD to create ArchivedVod from
        :type vod: Vod
        """
        for key, value in vars(vod).items():
            setattr(self, key, value)
