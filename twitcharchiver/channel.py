"""
Class for retrieving and storing information related to channels and users.
"""
import logging
import sys
from random import randrange

import m3u8

from twitcharchiver.api import Api


class Channel:
    def __init__(self, channel_name: str = "", owner: dict = None):
        """
        Initialize class variables.

        :param channel_name: name of channel
        :type channel_name: str
        :param owner: dict of channel values retrieved from Twitch
        :type owner: dict
        """
        self._api: Api = Api()
        self.log = logging.getLogger()

        self.id: int = 0
        self.name: str = channel_name
        self.stream: dict = {}

        if owner:
            self._parse_dict(owner)

        elif self.name:
            self._parse_dict(self._fetch_metadata())

    def __repr__(self):
        return str({'id': self.id, 'name': self.name})

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return bool(self.id == other.id)

        return False

    def __hash__(self):
        return hash(self.id)

    def get_info(self):
        return {'id': self.id, 'name': self.name}

    def _parse_dict(self, owner: dict):
        """
        Parses information from 'owner' object returned from Twitch.
        """
        self.id = owner['id']
        self.name = owner['displayName']
        self.stream = owner['stream']

    def _fetch_metadata(self):
        """
        Fetches metadata from Twitch regarding the channel.
        """
        _r = self._api.gql_request('ChannelShell', '580ab410bcd0c1ad194224957ae2241e5d252b2c5173d8e0cce9d32d5bb14efe',
                                   {"login": f"{self.name.lower()}"})
        _user_data = _r.json()[0]['data']['userOrError']
        self.log.debug('User data for %s: %s', self.name, _user_data)

        # failure return contains "userDoesNotExist" key
        if "userDoesNotExist" not in _user_data.keys():
            return _user_data

        return {}

    def is_live(self):
        """
        Checks if the channel is currently live.
        """
        return self.stream is not None

    def refresh_metadata(self):
        """
        Refreshes all metadata for the channel.
        """
        self._fetch_metadata()

    def get_stream_info(self):
        """Retrieves information relating to a channel if it is currently live.

        :return: dictionary with information about a channel's live stream if any
        :rtype: dict
        """
        _query_vars = {"channel": self.name, "clipSlug": "", "isClip": False, "isLive": True,
                       "isVodOrCollection": False, "vodID": ""}

        _r = self._api.gql_request('ComscoreStreamingQuery',
                                   'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                                   _query_vars)

        _stream_info = _r.json()[0]['data']['user']

        if _stream_info:
            self.log.debug('Stream info for %s: %s', self.name, _stream_info)
            return _stream_info

        self.log.debug('No broadcast info found for %s', self.name)
        return {}

    def get_broadcast_vod_id(self):
        """
        Fetches the paired VOD ID for the currently live broadcast.

        :return: VOD ID
        :rtype: int
        """
        _r = self._api.gql_request('ChannelVideoLength',
                                   'ac644fafd686f2cb0e3864075af7cf3bb33f4e0525bf84921b10eabaa4e048b5',
                                   {"channelLogin": f"{self.name.lower()}"})
        _channel_video_length = _r.json()[0]['data']['user']['videos']['edges']

        if _channel_video_length:
            broadcast_info = _channel_video_length[0]['node']['id']
            self.log.debug('Live broadcast info: %s', broadcast_info)
            return int(broadcast_info)

        self.log.debug('No data returned by ChannelVideoLength API for %s.', self.name)
        return int()

    def get_stream_index(self, quality: str = 'chunked'):
        """
        Retrieves a m3u8 index of the channel's live stream.

        :param quality: desired quality in the format [resolution]p[framerate] or 'best', 'worst'
        :type quality: str
        :return: url of m3u8 playlist
        :rtype: str
        """
        from twitcharchiver.vod import Vod
        _access_token = self.get_stream_playback_access_token()

        _p = {
            'player': 'twitchweb',
            'fast_bread': 'true',
            'token': _access_token['value'],
            'sig': _access_token['signature'],
            'allow_source': 'true',
            'playlist_include_framerate': 'true',
            'player_backend': 'mediaplayer',
            'supported_codecs': 'avc1',
            'p': randrange(1000000, 9999999)
        }
        _r = self._api.get_request(f'https://usher.ttvnw.net/api/channel/hls/{self.name.lower()}.m3u8', p=_p)

        _index = m3u8.loads(_r.text)

        # grab 'name' of m3u8 streams - contains [resolution]p[framerate]
        _available_resolutions = [m[0].group_id.split('p') for m in [m.media for m in _index.playlists] if
                                  m[0].group_id != 'chunked']
        # insert 'chunked' stream separately as its named differently and strip ' (source)' from name
        _available_resolutions.insert(0, _index.media[0].name.strip(' (source)').split('p'))
        self.log.debug('Available resolutions for %s are: %s', self.name, _available_resolutions)

        _index_url = _index.playlists[Vod().get_quality_index(quality, _available_resolutions)].uri
        self.log.debug('Index for broadcast by %s: %s', self.name, _index_url)

        return _index_url

    def get_stream_playlist(self, index_url: str = ""):
        """
        Retrieves the playlist for a given VOD index along with updating the VOD duration.
        """
        if not index_url:
            index_url = self.get_stream_index()

        _stream_playlist = self._api.get_request(index_url).text
        self.log.debug('Playlist for broadcast by %s: %s', self.name, _stream_playlist)

        return _stream_playlist

    def get_stream_playback_access_token(self):
        """
        Gets a stream access token for the channel.

        :return: dictionary of playback access token values
        :rtype: dict
        """
        # only accepts the default client ID for non-authenticated clients
        _h = {'Client-Id': 'ue6666qo983tsx6so1t0vnawi233wa'}
        _q = """
        {{
            streamPlaybackAccessToken(
                channelName: "{channel}",
                params: {{
                    platform: "web",
                    playerBackend: "mediaplayer",
                    playerType: "embed"
                }}
            ) {{
                signature
                value
            }}
        }}
        """.format(channel=self.name.lower())
        _r = self._api.post_request('https://gql.twitch.tv/gql', j={'query': _q}, h=_h)

        _access_token = _r.json()['data']['streamPlaybackAccessToken']
        self.log.debug('Access token retrieved for %s. %s', self.name, _access_token)

        return _access_token

    def _get_most_recent_videos(self):
        """
        Retrieves all recent broadcasts for the channel.

        :return: list of Vod objects
        :rtype: list[Vod]
        """
        from twitcharchiver.vod import Vod
        _r = self._api.gql_request(
            'FilterableVideoTower_Videos', 'a937f1d22e269e39a03b509f65a7490f9fc247d7f83d6ac1421523e3b68042cb',
            {"broadcastType": "ARCHIVE", "channelOwnerLogin": f"{self.name.lower()}", "limit": 30, "videoSort": "TIME"})

        _recent_videos = [Vod(vod_info=v['node']) for v in _r.json()[0]['data']['user']['videos']['edges']]

        self.log.debug('Recent videos for %s: %s', self.name, _recent_videos)
        return _recent_videos

    def get_latest_video(self):
        """Retrieves the latest VOD for the channel.

        :return: The most recent VOD for the channel
        :rtype: Vod
        """
        return self._get_most_recent_videos()[0]

    def get_channel_videos(self):
        """
        Retrieves all available VODs for the channel.

        :return: list of all available VODs for the channel
        :rtype: list[Vod]
        """
        from twitcharchiver.vod import Vod
        _channel_videos = []
        _query_vars = {"broadcastType": "ARCHIVE", "channelOwnerLogin": f"{self.name.lower()}", "limit": 30,
                       "videoSort": "TIME"}

        while True:
            _r = self._api.gql_request('FilterableVideoTower_Videos',
                                       'a937f1d22e269e39a03b509f65a7490f9fc247d7f83d6ac1421523e3b68042cb',
                                       _query_vars)

            # retrieve list of videos from response
            _videos = [Vod(vod_info=v['node']) for v in _r.json()[0]['data']['user']['videos']['edges']]
            self.log.debug('Retrieved videos for %s: %s', self.name, _videos)
            _channel_videos.extend(_videos)

            if _r.json()[0]['data']['user']['videos']['pageInfo']['hasNextPage'] is not False:
                # set cursor
                _query_vars['cursor'] = _r.json()[0]['data']['user']['videos']['edges'][-1]['cursor']

            else:
                break

        if _channel_videos:
            self.log.debug('Full list of VODs for %s: %s', self.name, _channel_videos)
            return _channel_videos

        self.log.debug('No VODs found for %s.', self.name)
        return []
