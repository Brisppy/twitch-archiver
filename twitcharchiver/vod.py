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
from twitcharchiver.utils import time_since_date


class Vod:
    """
    A VOD or Video On Demand is an archive of a livestream which has been saved by Twitch. This class holds various
    functions for storing, fetching and manipulating VOD data.
    """
    def __init__(self, vod_id: int = 0, stream_id: int = 0, vod_info: dict = None):
        """
        Class constructor.

        :param vod_id: Numeric VOD ID of the archive.
        :param stream_id: Numeric stream ID of the archive.
        :param vod_info: Dict of VOD values retrieved from Twitch.
        """
        self._log = logging.getLogger()
        self._api: Api = Api()

        self.v_id: int = int(vod_id)
        self._s_id: int = int(stream_id)
        self.category: Category = Category()
        self.created_at: float = 0
        self.description: str = ""
        self.duration: int = 0
        self.published_at: float = 0
        self.thumbnail_url: str = ""
        self.title: str = ""
        self.view_count: int = 0

        self._channel = Channel()

        if vod_id:
            self._setup(vod_id)

        elif vod_info:
            self._parse_dict(vod_info)

    def __eq__(self, other):
        """
        VODs are compared for equality based on their VOD ID (id) alone.

        :return: True if VODs have the same ID
        :rtype: bool
        """
        if isinstance(other, self.__class__):
            return self.v_id == other.v_id
        raise TypeError

    def __repr__(self):
        """
        Return self as string.

        :return: str containing VOD values
        :rtype: str
        """
        return str(self.to_dict())

    def __bool__(self):
        """
        Check if VOD has been initalized (vod id or stream id exists).

        :return: True if initialization complete
        :rtype: bool
        """
        return bool(self.v_id or self._s_id)

    def _setup(self, vod_id: int):
        """
        Sets the VOD ID and retrieves its information.

        :param vod_id: VOD ID of VOD
        """
        self.v_id = vod_id
        self._fetch_metadata()

    def _parse_dict(self, vod_info: dict):
        """
        Parses a provided dictionary of VOD information retrieve from Twitch.

        :param vod_info: dict of values related to the VOD retrieved from Twitch
        """
        if not self.v_id:
            self.v_id = int(vod_info['id'])
        self.category = Category(vod_info['game'])
        self.duration = vod_info['lengthSeconds']
        self.published_at = \
            datetime.strptime(vod_info['publishedAt'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
        self.thumbnail_url = vod_info['previewThumbnailURL']
        self.title = vod_info['title']
        self.view_count = vod_info['viewCount']

        # use published_at as created_at if not provided
        if 'createdAt' in vod_info.keys():
            self.created_at = datetime.strptime(
                vod_info['createdAt'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
        elif 'publishedAt' in vod_info.keys():
            self.created_at = datetime.strptime(
                vod_info['publishedAt'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()

        # set description if provided
        if 'description' in vod_info.keys():
            self.description = vod_info['description']

    def _fetch_metadata(self):
        """
        Retrieves metadata for a given VOD ID. Formatting is done to ensure backwards compatibility.
        """
        _r = self._api.gql_request('VideoMetadata', 'c25707c1e5176320ceac6b447d052480887e23bc794ca1d02becd0bcc91844fe',
                                   {'channelLogin': self.channel.name, 'videoID': str(self.v_id)})

        _vod_info = _r.json()[0]['data']['video']
        self._parse_dict(_vod_info)

        self._log.debug('Filled metadata for VOD %s: %s', self.v_id, self.to_dict())

    def time_since_live(self):
        """
        Fetches the time since the VOD was created / started.

        :return: seconds since VOD started
        :rtype: int
        """
        _seconds_since_start: int = time_since_date(self.created_at)

        return _seconds_since_start

    def refresh_vod_metadata(self):
        """
        Refreshes metadata for VOD.
        """
        self._fetch_metadata()

    def to_dict(self):
        """
        Returns useful VOD variables.

        :return: dict of VOD attributes
        :rtype: dict
        """
        return {'vod_id': self.v_id, 'stream_id': self._s_id, 'title': self.title, 'description': self.description,
                'created_at': self.created_at, 'published_at': self.published_at, 'thumbnail_url': self.thumbnail_url,
                'duration': self.duration}

    def get_category(self):
        """
        Retrieves Twitch category for a specified VOD.

        :return: name of category / game
        :rtype: Category
        """
        _r = self._api.gql_request('ComscoreStreamingQuery',
                                   'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                                   {"channel": "", "clipSlug": "", "isClip": False, "isLive": False,
                                    "isVodOrCollection": True, "vodID": str(self.v_id)})

        _vod_category = Category(_r.json()[0]['data']['video']['game'])
        self._log.debug('Category for VOD %s is %s', self.v_id, _vod_category)

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

        if _stream_info['stream']:
            try:
                # if stream live and vod start time matches
                _stream_created_time = datetime.strptime(
                    _stream_info['stream']['createdAt'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()

                # if vod created within 10s of stream created time
                if 10 >= self.created_at - _stream_created_time >= -10:
                    self._log.debug('VOD creation time (%s) is within 10s of stream created time (%s).',
                             self.created_at, _stream_created_time)
                    return True

            except IndexError:
                pass

            self._log.debug('VOD is not paired with the current stream by %s.', self.channel.name)
            return False

        self._log.debug('%s is offline and so VOD must be offline.', self.channel.name)
        return False

    def get_chapters(self):
        """
        Retrieves the chapters for a given Twitch VOD.

        :return: Retrieves any chapters for the VOD, or a single chapter with the VOD category otherwise.
        :rtype: Chapters
        """
        if not self.v_id:
            return Chapters()

        _r = self._api.gql_request('VideoPlayer_ChapterSelectButtonVideo',
                                   '8d2793384aac3773beab5e59bd5d6f585aedb923d292800119e03d40cd0f9b41',
                                   {"includePrivate": False, "videoID": str(self.v_id)})

        # extract and return list of moments from returned json
        _chapters = Chapters([node['node'] for node in _r.json()[0]['data']['video']['moments']['edges']])

        if _chapters:
            self._log.debug('Chapters for VOD %s: %s', self.v_id, _chapters)
            return _chapters

        self._log.debug('No chapters found for VOD %s.', self.v_id)
        # create single chapter out of VOD category
        _category = self.get_category()
        _chapters = Chapters.create_chapter_from_category(_category, self.duration)

        self._log.debug('Chapters generated for VOD based on %s: %s', _category, self.v_id)
        return _chapters

    def get_muted_segments(self):
        """
        Retrieves any muted segments for the VOD.

        :return: muted segments
        :rtype: list[MpegSegment]
        """
        if not self.v_id:
            return []

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

    def _get_channel(self):
        """
        Retrieves the channel which a given VOD belongs to

        :return: Channel containing `id` and `name` of VOD owner
        :rtype: Channel
        """
        if not self.v_id:
            return Channel()

        _r = self._api.gql_request('ComscoreStreamingQuery',
                                   'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                                   {"channel": "", "clipSlug": "", "isClip": False, "isLive": False,
                                    "isVodOrCollection": True, "vodID": str(self.v_id)})

        _channel = Channel(_r.json()[0]['data']['video']['owner']['displayName'])
        return _channel

    @property
    def channel(self):
        """
        Fetch, store and return channel for the VOD if it is used.

        :return: channel attribute
        :rtype: Channel
        """
        if not self._channel:
            self._channel = self._get_channel()

        return self._channel

    @channel.setter
    def channel(self, value: Channel):
        """
        Sets the channel attribute.

        :param value: channel to set
        """
        self._channel = value

    @property
    def s_id(self):
        """
        Fetch, store and return stream_id for the VOD if it is used.
        """
        if not self._s_id:
            self._s_id = self._get_stream_id()

        return self._s_id

    @s_id.setter
    def s_id(self, value):
        """
        Sets the stream_id attribute.

        :param value: stream ID of VOD
        """
        self._s_id = value

    def _get_stream_id(self):
        """
        Retrieves the associated stream ID for the VOD

        :return: stream id
        :rtype: int
        """
        if not self.thumbnail_url:
            return 0

        # check for processing thumbnail used by broadcasts
        if '404_processing' not in self.thumbnail_url:
            # use index for end of list as users with '_' in their name will break this
            return int(self.thumbnail_url.split('/')[5].split('_')[-2])

        return int(self._get_seek_url().split('/')[3].split('_')[-2])

    def _get_seek_url(self):
        """
        Retrieves the seek preview URL for the VOD.

        :return: seek preview URL
        :rtype: str
        """
        _r = self._api.gql_request('VideoPlayer_VODSeekbarPreviewVideo',
                                   '07e99e4d56c5a7c67117a154777b0baf85a5ffefa393b213f4bc712ccaf85dd6',
                                   {'includePrivate': False, 'videoID': str(self.v_id)})

        return _r.json()[0]['data']['video']['seekPreviewsURL']

    def get_index_url(self, quality='best'):
        """
        Retrieves an index of m3u8 streams for a given VOD.

        :param quality: desired quality in the format [resolution, framerate] or 'best', 'worst'
        :type quality: list[int, int] or str
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
            if '404_processing' not in self.thumbnail_url:
                _cf_info = self.thumbnail_url.split('/')
                _cf_domain = _cf_info[4]
                _vod_uid = _cf_info[5]

            else:
                _cf_info = self._get_seek_url().split('/')
                _cf_domain = _cf_info[2].split('.')[0]
                _vod_uid = _cf_info[3]

            # parse user-provided quality
            if quality == 'best':
                quality = 'chunked'
            elif quality == 'worst':
                quality = '160p30'
            else:
                quality = 'p'.join(quality)

            # create index url
            _index_url = f'https://{_cf_domain}.cloudfront.net/{_vod_uid}/{quality}/index-dvr.m3u8'
            self._log.debug('Index URL for %s: %s', self.v_id, _index_url)

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

        :param index_url: url for playlist (fetches it if not provided)
        :type index_url: str
        :return: playlist of video segments
        :rtype str:
        """
        if index_url == "":
            index_url = self.get_index_url()

        _vod_playlist = self._api.get_request(index_url).text

        # update vod json with m3u8 duration - more accurate than twitch API
        _m = re.findall(r'(?<=#EXT-X-TWITCH-TOTAL-SECS:).*(?=\n)', _vod_playlist)[0]
        self.duration = floor(float(_m))

        return _vod_playlist

    @staticmethod
    def get_quality_index(desired_quality, available_qualities):
        """Finds the index of a user defined quality from a list of available stream qualities.

        :param desired_quality: desired quality to search for - best, worst or [resolution, framerate]
        :type desired_quality: list[int, int] or str
        :param available_qualities: list of available qualities as [[resolution, framerate], ...]
        :type available_qualities: list[list[int, int]]
        :return: index of desired quality in list if found
        :rtype: int
        """
        _log = logging.getLogger()

        if desired_quality not in ['best', 'worst']:
            # look for user defined quality in available streams
            try:
                return available_qualities.index(desired_quality)

            except ValueError:
                _log.info('User requested quality not found in available streams.')
                # grab first resolution match
                try:
                    return [quality[0] for quality in available_qualities].index(desired_quality[0])

                except ValueError:
                    _log.info('No match found for user requested resolution. Defaulting to best.')
                    return 0

        elif desired_quality == 'worst':
            return -1

        else:
            return 0

    @staticmethod
    def from_stream_json(stream_json: dict):
        """
        Generates a Vod object from a given stream JSON provided by Twitch when fetching channel data.

        :param stream_json: Dict of stream variables
        :return: Vod containing stream information
        :rtype: Vod
        """
        # return empty VOD if no stream
        if not stream_json['stream']:
            return Vod()

        _stream = Vod()
        _stream.s_id = int(stream_json['stream']['id'])

        _stream.category = Category(stream_json['stream']['game'])
        _stream.created_at = (datetime.strptime(
            stream_json['stream']['createdAt'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())
        _stream.duration = time_since_date(_stream.created_at)
        _stream.published_at = _stream.created_at
        _stream.title = stream_json['broadcastSettings']['title']

        return _stream


class ArchivedVod(Vod):
    """
    Defines an archive of a VOD. Used for tracking the status of previously archived VODs.
    """
    def __init__(self, chat_archived: bool = False, video_archived: bool = False):
        """
        Class constructor.

        :param chat_archived: if chat has been archived
        :param video_archived: if video has been archived
        """
        super().__init__()
        self.chat_archived: bool = chat_archived
        self.video_archived: bool = video_archived

    def __eq__(self, other):
        """
        Compare two ArchivedVods based on stream_id or vod_id, and the formats they have been archived in.

        :param other: VOD to compare against
        :type other: ArchivedVod
        :return: True if VODs match
        :rtype: bool
        """
        if isinstance(other, self.__class__):
            return (self.s_id == other.s_id or self.v_id == other.v_id) and self.chat_archived == other.chat_archived \
                and self.video_archived == other.video_archived
        raise TypeError

    def __repr__(self):
        return str(self.to_dict())

    def to_dict(self):
        """
        Returns useful VOD variables.

        :return: dict of VOD attributes
        """
        return {'vod_id': self.v_id, 'stream_id': self._s_id, 'title': self.title, 'description': self.description,
                'created_at': datetime.utcfromtimestamp(self.created_at),
                'published_at': datetime.utcfromtimestamp(self.published_at), 'thumbnail_url': self.thumbnail_url,
                'duration': self.duration, 'chat_archived': self.chat_archived, 'video_archived': self.video_archived}

    def ordered_db_dict(self):
        """
        Retrieves all info related to the VOD including the channel, chapters, and muted segments.

        :return: dict of all VOD information
        :rtype: dict
        """

        return {'vod_id': self.v_id, 'stream_id': self._s_id, 'user_id': self.channel.id,
                'user_name': self.channel.name, 'chapters': str(self.get_chapters()), 'title': self.title,
                'description': self.description, 'created_at': datetime.utcfromtimestamp(self.created_at),
                'published_at': datetime.utcfromtimestamp(self.published_at), 'thumbnail_url': self.thumbnail_url,
                'duration': self.duration, 'muted_segments': str(self.get_muted_segments()),
                'chat_archived': self.chat_archived, 'video_archived': self.video_archived}

    @staticmethod
    def import_from_db(args: tuple):
        """
        Creates a new ArchivedVod with values from the provided database return. We can't fetch this from Twitch as
        they delete the records when the VOD expires or is manually deleted.

        :param args: {vod_id, stream_id, created_at, chat_archived, video_archived}
        :return: VOD based on provided values
        :rtype: ArchivedVod
        """
        if len(args) != 5:
            return None

        _archived_vod = ArchivedVod(args[3], args[4])
        _archived_vod.v_id = args[0]
        _archived_vod.s_id = args[1]

        # format date if using format prior to 4.0.0
        if 'Z' in args[2]:
            _archived_vod.created_at = \
                datetime.strptime(args[2], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()

        else:
            _archived_vod.created_at = \
                datetime.strptime(args[2], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()

        return _archived_vod

    @staticmethod
    def convert_from_vod(vod: Vod, chat_archived: bool = False, video_archived: bool = False):
        """
        Converts an existing VOD into an ArchivedVod.

        :param vod: VOD to create ArchivedVod from
        :param chat_archived: True if chat archived
        :param video_archived: True if video archived
        :return: ArchivedVod created from Vod
        :rtype: ArchivedVod
        """
        _a_vod = ArchivedVod(chat_archived, video_archived)

        for key, value in vars(vod).items():
            setattr(_a_vod, key, value)

        return _a_vod
