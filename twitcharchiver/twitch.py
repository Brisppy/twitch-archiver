"""
Handler for any requests made to the Twitch API.
"""

import logging

from datetime import datetime, timezone
from random import randrange
from time import sleep

import m3u8

from twitcharchiver.api import Api
from twitcharchiver.exceptions import TwitchAPIErrorForbidden
from twitcharchiver.utils import get_quality_index, time_since_date, get_stream_id_from_preview_url


class Twitch:
    """
    Functions and processes for interacting with the Twitch API.
    """

    def __init__(self):
        """Class constructor.
        """
        self.log = logging.getLogger()

    def get_user_data(self, user_name: str):
        """Retrieve basic user login information.

        :param user_name: Name of user to fetch
        :type user_name: str
        :return: user information if any
        :rtype: dict
        """
        _r = Api.gql_request('ChannelShell', '580ab410bcd0c1ad194224957ae2241e5d252b2c5173d8e0cce9d32d5bb14efe',
                             {"login": f"{user_name.lower()}"})
        _user_data = _r.json()[0]['data']['userOrError']
        self.log.debug('User data for %s: %s', user_name, _user_data)

        # failure return contains "userDoesNotExist" key
        if "userDoesNotExist" not in _user_data.keys():
            return _user_data

        else:
            return dict()

    def get_channel_videos(self, channel: str):
        """Retrieves all available VODs for a given channel.

        :param channel: name channel to retrieve VODs of
        :type channel: str
        :return: list of dictionaries of past channel broadcasts if any
        :rtype: list[dict]
        """
        _channel_videos = []
        _query_vars = {"broadcastType": "ARCHIVE", "channelOwnerLogin": f"{channel.lower()}", "limit": 30,
                       "videoSort": "TIME"}

        while True:
            _r = Api.gql_request('FilterableVideoTower_Videos',
                                 'a937f1d22e269e39a03b509f65a7490f9fc247d7f83d6ac1421523e3b68042cb',
                                 _query_vars)

            # retrieve list of videos from response
            _videos = [v['node'] for v in _r.json()[0]['data']['user']['videos']['edges']]
            self.log.debug('Retrieved videos for %s: %s', channel, _videos)
            _channel_videos.extend(_videos)

            if _r.json()[0]['data']['user']['videos']['pageInfo']['hasNextPage'] is not False:
                # set cursor
                _query_vars['cursor'] = _r.json()[0]['data']['user']['videos']['edges'][-1]['cursor']

            else:
                break

        if _channel_videos:
            self.log.debug('Full list of VODs for %s: %s', channel, _channel_videos)
            return _channel_videos
        else:
            self.log.debug('No VODs found for %s.', channel)
            return list(dict())

    def get_stream_info(self, channel: str):
        """Retrieves information relating to a channel if it is currently live.

        :param channel: name channel to retrieve information for
        :type channel: str
        :return: dictionary of stream information if any
        :rtype: dict
        """
        _query_vars = {"channel": channel, "clipSlug": "", "isClip": False, "isLive": True,
                       "isVodOrCollection": False, "vodID": ""}

        _r = Api.gql_request('ComscoreStreamingQuery',
                             'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                             _query_vars)

        _stream_info = _r.json()[0]['data']['user']

        if _stream_info['stream']:
            self.log.debug('Stream info for %s: %s', channel, _stream_info)
            return _stream_info
        else:
            self.log.debug('No broadcast info found for %s', channel)
            return dict()

    def get_playback_access_token(self, vod_id: int):
        """Gets a playback access token for a specified vod.

        :param vod_id: ID of VOD to retrieve token for
        :type vod_id: int
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
        """.format(vod_id=vod_id)
        _r = Api.post_request('https://gql.twitch.tv/gql', j={'query': _q}, h=_h)

        _token = _r.json()['data']['videoPlaybackAccessToken']

        if _token:
            self.log.debug('Token retrieved for VOD %s: %s', vod_id, _token)
            return _token
        else:
            self.log.debug('Token could not be retrieved for VOD %s: %s', vod_id, _token)
            return ""

    def get_live_broadcast_vod_id(self, channel: str):
        """Fetches the paired VOD ID for the currently live broadcast.

        :param channel: name of channel to retrieve current broadcast VOD ID of
        :type channel: str
        :return: VOD ID
        :rtype: int
        """
        _r = Api.gql_request('ChannelVideoLength', 'ac644fafd686f2cb0e3864075af7cf3bb33f4e0525bf84921b10eabaa4e048b5',
                             {"channelLogin": f"{channel.lower()}"})
        _channel_video_length = _r.json()[0]['data']['user']['videos']['edges']

        if _channel_video_length:
            broadcast_info = _channel_video_length[0]['node']['id']
            self.log.debug('Live broadcast info: %s', broadcast_info)
            return int(broadcast_info)
        else:
            self.log.debug('No data returned by ChannelVideoLength API for %s.', channel)
            return int()

    def get_vod_index(self, vod_json: dict, quality: str = 'best'):
        """Retrieves an index of m3u8 streams for a given VOD.

        :param vod_json: vod information retrieved from Twitch
        :type vod_json: dict
        :param quality: desired quality in the format [resolution]p[framerate] or 'best', 'worst'
        :type quality: str
        :return: url of m3u8 playlist
        :rtype: str
        """
        _access_token = self.get_playback_access_token(vod_json['vod_id'])

        _p = {
            'player': 'twitchweb',
            'nauth': _access_token['value'],
            'nauthsig': _access_token['signature'],
            'allow_source': 'true',
            'playlist_include_framerate': 'true',
            'p': randrange(1000000, 9999999)
        }

        try:
            _r = Api.get_request(f'https://usher.ttvnw.net/vod/{vod_json["vod_id"]}.m3u8', p=_p)
            _index = m3u8.loads(_r.text)

            # grab 'name' of m3u8 streams - contains [resolution]p[framerate]
            _available_resolutions = [m[0].group_id.split('p') for m in [m.media for m in _index.playlists] if
                                      m[0].group_id != 'chunked']
            # insert 'chunked' stream separately as its named differently
            _available_resolutions.insert(0, _index.media[0].name.split('p'))

        # catch for sub-only vods
        except TwitchAPIErrorForbidden:
            self.log.debug('VOD %s is subscriber-only. Generating index URL.', vod_json['vod_id'])
            # retrieve cloudfront storage location from VOD thumbnail
            _cf_info = vod_json['thumbnail_url'].split('/')
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
            self.log.debug('Index URL for %s: %s', vod_json['user_name'])

            return _index_url

        _index_url = _index.playlists[get_quality_index(quality, _available_resolutions)].uri
        self.log.debug('Index for VOD %s: %s', vod_json['vod_id'], _index_url)

        return _index_url

    def get_channel_hls_index(self, channel: str, quality: str = 'best'):
        """Retrieves an index of a live m3u8 stream.

        :param channel: name of channel to retrieve index of
        :type channel: str
        :param quality: desired quality in the format [resolution]p[framerate] or 'best', 'worst'
        :type quality: str
        :return: url of m3u8 playlist
        :rtype: str
        """
        _channel = channel.lower()
        _access_token = self.get_stream_playback_access_token(_channel)

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
        _r = Api.get_request(f'https://usher.ttvnw.net/api/channel/hls/{_channel}.m3u8', p=_p)

        _index = m3u8.loads(_r.text)

        # grab 'name' of m3u8 streams - contains [resolution]p[framerate]
        _available_resolutions = [m[0].group_id.split('p') for m in [m.media for m in _index.playlists] if
                                  m[0].group_id != 'chunked']
        # insert 'chunked' stream separately as its named differently and strip ' (source)' from name
        _available_resolutions.insert(0, _index.media[0].name.strip(' (source)').split('p'))
        self.log.debug('Available resolutions for %s are: %s', _channel, _available_resolutions)

        return _index.playlists[get_quality_index(quality, _available_resolutions)].uri

    def get_stream_playback_access_token(self, channel: str):
        """Gets a stream access token for a specified channel.

        :param channel: name of channel to retrieve access token for
        :type channel: str
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
        """.format(channel=channel.lower())
        _r = Api.post_request('https://gql.twitch.tv/gql', j={'query': _q}, h=_h)

        _access_token = _r.json()['data']['streamPlaybackAccessToken']
        self.log.debug('Access token retrieved for %s. %s', channel, _access_token)

        return _access_token

    def get_vod_category(self, vod_id: int):
        """Retrieves category for a specified VOD.

        :param vod_id: ID of VOD to retrieve category of
        :type vod_id: int
        :return: name of category / game
        :rtype: str
        """
        _r = Api.gql_request('ComscoreStreamingQuery',
                             'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                             {"channel": "", "clipSlug": "", "isClip": False, "isLive": False,
                              "isVodOrCollection": True, "vodID": str(vod_id)})

        _vod_category = _r.json()[0]['data']['video']['game']['name']
        self.log.debug('Category for VOD %s is %s', vod_id, _vod_category)

        return _vod_category

    def get_vod_status(self, channel: str, vod_created_time: str):
        """Determines whether a live stream is paired with a given vod.

        :param channel: name of channel to check status of
        :type channel: str
        :param vod_created_time: time and date a vod was created in the format `%Y-%m-%dT%H:%M:%SZ`
        :type vod_created_time: str
        :return: if vod and stream creation dates match
        :rtype: bool
        """
        # wait until 1m has passed since vod created time as the stream api may not have updated yet
        _time_since_created = time_since_date(
            datetime.strptime(vod_created_time, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())
        if _time_since_created < 60:
            self.log.debug('VOD for channel with id %s created < 60 seconds ago, delaying status retrieval.', channel)
            sleep(60 - _time_since_created)

        # check if channel is offline
        _stream_info = self.get_stream_info(channel)

        if _stream_info:
            try:
                # if stream live and vod start time matches
                _stream_created_time = \
                    datetime.strptime(_stream_info['stream']['createdAt'], '%Y-%m-%dT%H:%M:%SZ').timestamp()
                _vod_created_time = datetime.strptime(vod_created_time, '%Y-%m-%dT%H:%M:%SZ').timestamp()

                # if vod created within 10s of stream created time
                if 10 >= _vod_created_time - _stream_created_time >= -10:
                    self.log.debug(
                        'VOD creation time (%s) is within 10s of stream created time (%s), running in live mode.',
                        _vod_created_time, _stream_created_time)
                    return True

            except IndexError:
                pass

            self.log.debug('Stream status could not be retrieved for %s.', channel)
            return False

        self.log.debug('%s is offline and so VOD status must be offline.', channel)
        return False

    def get_vod_chapters(self, vod_id: int):
        """Retrieves the chapters for a given Twitch VOD.

        :param vod_id: ID of VOD to retrieve chapters for
        :type vod_id: int
        :return: vod chapters
        :rtype: list
        """
        _r = Api.gql_request('VideoPlayer_ChapterSelectButtonVideo',
                             '8d2793384aac3773beab5e59bd5d6f585aedb923d292800119e03d40cd0f9b41',
                             {"includePrivate": False, "videoID": str(vod_id)})

        # extract and return list of moments from returned json
        _chapters = [node['node'] for node in _r.json()[0]['data']['video']['moments']['edges']]

        try:
            self.log.debug('Chapters for VOD %s: %s', vod_id, _chapters)
            return _chapters

        except TypeError:
            self.log.debug('No chapters found for VOD %s', vod_id)
            return list()

    def get_video_muted_segments(self, vod_id: int):
        """Retrieves muted segments for a given VOD.

        :param vod_id: ID of VOD to retrieve muted segments of
        :type vod_id: int
        :return: muted segments
        :rtype: list
        """
        _r = Api.gql_request('VideoPlayer_MutedSegmentsAlertOverlay',
                             'c36e7400657815f4704e6063d265dff766ed8fc1590361c6d71e4368805e0b49',
                             {'includePrivate': False, 'vodID': vod_id})

        _muted_segments = _r.json()[0]['data']['video']['muteInfo']['mutedSegmentConnection']

        if _muted_segments:
            self.log.debug('Muted segments for VOD %s: %s', vod_id, _muted_segments)
            return _muted_segments['nodes']

        else:
            self.log.debug('No muted segments found for VOD %s.', vod_id)
            return list()

    def get_video_metadata(self, vod_id: int):
        """Retrieves metadata for a given VOD. Formatting is used to ensure backwards compatibility.

        :param vod_id: ID of VOD to retrieve metadata of
        :type vod_id: int
        :return: video metadata
        :rtype: list
        """
        _channel_data = self.get_vod_owner(vod_id)

        _r = Api.gql_request('VideoMetadata', 'c25707c1e5176320ceac6b447d052480887e23bc794ca1d02becd0bcc91844fe',
                             {'channelLogin': _channel_data['name'], 'videoID': vod_id})

        _vod_json = _r.json()[0]['data']['video']
        self.log.debug('Retrieved metadata for VOD %s: %s', vod_id, _vod_json)

        # reformat to database schema
        _vod_json['vod_id'] = _vod_json.pop('id')
        _vod_json['stream_id'] = self.get_stream_id_for_vod(_vod_json['vod_id'])
        _vod_json['user_id'] = _channel_data['id']
        _vod_json['user_login'] = _channel_data['name'].lower()
        _vod_json['user_name'] = _channel_data['name']
        _vod_json['game_name'] = _vod_json['game']['displayName']
        _vod_json['game_id'] = _vod_json.pop('game')['id']
        _vod_json['created_at'] = _vod_json.pop('createdAt')
        _vod_json['published_at'] = _vod_json.pop('publishedAt')
        _vod_json['url'] = 'https://twitch.tv/' + _vod_json['user_login'] + '/' + _vod_json['vod_id']
        _vod_json['thumbnail_url'] = _vod_json.pop('previewThumbnailURL')
        _vod_json['view_count'] = _vod_json.pop('viewCount')
        _vod_json['duration'] = _vod_json.pop('lengthSeconds')
        _vod_json['muted_segments'] = self.get_video_muted_segments(_vod_json['vod_id'])
        for _key in ['owner', '__typename', 'broadcastType']:
            _vod_json.pop(_key)

        self.log.debug('Filled metadata for VOD %s: %s', vod_id, _vod_json)
        return _vod_json

    def get_vod_owner(self, vod_id: int):
        """Retrieves the channel which a given VOD belongs to

        :param vod_id: ID of VOD to find owning channel
        :type vod_id: int
        :return: dictionary containing `id` and `name` of VOD owner
        :rtype: dict
        """
        _r = Api.gql_request('ComscoreStreamingQuery',
                             'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                             {"channel": "", "clipSlug": "", "isClip": False, "isLive": False,
                              "isVodOrCollection": True, "vodID": str(vod_id)})

        _owner = _r.json()[0]['data']['video']['owner']
        self.log.debug('Owner of VOD %s is %s.', vod_id, _owner)

        return {'id': _owner['id'], 'name': _owner['displayName']}

    def get_stream_id_for_vod(self, vod_id: int):
        """Retrieves the stream ID for a given VOD

        :param vod_id: ID of VOD to retrieve stream ID
        :type vod_id: int
        :return: stream id
        :rtype: int
        """
        _r = Api.gql_request('VideoPlayer_VODSeekbarPreviewVideo',
                             '07e99e4d56c5a7c67117a154777b0baf85a5ffefa393b213f4bc712ccaf85dd6',
                             {'includePrivate': False, 'videoID': vod_id})

        _stream_id = get_stream_id_from_preview_url(_r.json()[0]['data']['video']['seekPreviewsURL'])

        self.log.debug('Stream ID for VOD %s: %s', vod_id, _stream_id)
        return _stream_id

    def get_latest_video(self, channel: str):
        """Retrieves the latest VOD for a given channel.

        :param channel: channel to fetch latest VOD of
        :type channel: str
        :return: dict of values pertaining to most recent VOD
        :rtype: dict
        """

        _r = Api.gql_request('FilterableVideoTower_Videos',
                             'a937f1d22e269e39a03b509f65a7490f9fc247d7f83d6ac1421523e3b68042cb',
                             {"broadcastType": "ARCHIVE", "channelOwnerLogin": f"{channel.lower()}", "limit": 30,
                              "videoSort": "TIME"})

        _recent_videos = [v['node'] for v in _r.json()[0]['data']['user']['videos']['edges']]

        self.log.debug('Most recent videos for %s: %s', channel, _recent_videos)
        return _recent_videos[0]
