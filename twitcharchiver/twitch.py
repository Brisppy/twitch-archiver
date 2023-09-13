"""
Handler for any requests made to the Twitch API.
"""

import logging

from datetime import datetime, timezone
from random import randrange
from time import sleep

import m3u8

from twitcharchiver.api import Api
from twitcharchiver.exceptions import TwitchAPIError, TwitchAPIErrorForbidden, TwitchAPIErrorNotFound
from twitcharchiver.utils import get_quality_index, time_since_date


class Twitch:
    """
    Functions and processes for interacting with the Twitch API.
    """
    def __init__(self, client_id=None, client_secret=None, oauth_token=None):
        """Class constructor.

        :param client_id: twitch client_id
        :param client_secret: twitch client_secret
        :param oauth_token: twitch oauth_token
        """
        self.log = logging.getLogger()

        self.client_id = client_id
        self.client_secret = client_secret
        self.oauth_token = oauth_token

    def get_api(self, api_path):
        """Retrieves information from the Twitch API.

        :param api_path: twitch api endpoint to send request to
        :return: requests response json
        """
        _h = {'Authorization': f'Bearer {self.oauth_token}', 'Client-Id': self.client_id}
        _r = Api.get_request(f'https://api.twitch.tv/helix/{api_path}', h=_h)

        return _r.json()

    def get_user_data(self, user):
        """Retrieve basic user login information.

        :param user: user to fetch
        :return: dictionary of user information
        """
        _r = Api.gql_request('ChannelShell', '580ab410bcd0c1ad194224957ae2241e5d252b2c5173d8e0cce9d32d5bb14efe',
                             {"login": f"{user.lower()}"})
        user_data = _r.json()[0]['data']['userOrError']

        # failure return contains "userDoesNotExist" key
        if "userDoesNotExist" not in user_data.keys():
            return user_data

        else:
            raise TwitchAPIErrorNotFound(_r)

    def get_channel_videos(self, channel):
        """Retrieves all available VODs for a given channel.

        :param channel: channel to retrieve VODs of
        :return: list of VOD dicts
        """
        channel_videos = []
        query_vars = {"broadcastType": "ARCHIVE", "channelOwnerLogin": f"{channel.lower()}", "limit": 30,
                      "videoSort": "TIME"}

        while True:
            _r = Api.gql_request('FilterableVideoTower_Videos',
                                 'a937f1d22e269e39a03b509f65a7490f9fc247d7f83d6ac1421523e3b68042cb',
                                 query_vars)

            # retrieve list of videos from response
            _videos = [v['node'] for v in _r.json()[0]['data']['user']['videos']['edges']]
            channel_videos.extend(_videos)

            if _r.json()[0]['data']['user']['videos']['pageInfo']['hasNextPage'] is not False:
                # set cursor
                query_vars['cursor'] = _r.json()[0]['data']['user']['videos']['edges'][-1]['cursor']

            else:
                break

        return channel_videos

    def get_stream_info(self, channel):
        """Retrieves information relating to a channel if it is currently live.

        :param channel: channel to retrieve information for
        :return: dict of stream info
        """
        query_vars = {"channel": channel, "clipSlug": "", "isClip": "false", "isLive": "true",
                      "isVodOrCollection": "false", "vodID": ""}

        _r = Api.gql_request('ComscoreStreamingQuery',
                             'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                             query_vars)

        stream_info = _r.json()[0]['data']['user']
        self.log.debug('Stream info for %s: %s', channel, stream_info)

        if stream_info['stream']:
            return stream_info

        else:
            self.log.debug('No broadcast info found for %s', channel)

    def generate_oauth_token(self):
        """Generates an OAuth token from the provided client ID and secret.

        :return: oauth token
        """
        _d = {'client_id': self.client_id, 'client_secret': self.client_secret,
              'grant_type': 'client_credentials'}
        _t = Api.post_request('https://id.twitch.tv/oauth2/token', d=_d).json()['access_token']

        return _t

    def validate_oauth_token(self):
        """Validates a specified OAuth token with Twitch.

        :return: token expiration date
        """
        self.log.debug('Verifying OAuth token.')
        _h = {'Authorization': f'Bearer {self.oauth_token}'}

        try:
            _r = Api.get_request('https://id.twitch.tv/oauth2/validate', h=_h)

            self.log.info('OAuth token verified successfully. Expiring in %s', _r.json()["expires_in"])
            return _r.json()['expires_in']

        except TwitchAPIError as e:
            self.log.debug('OAuth token validation failed. Error: %s', str(e))

        # error on expired or invalid credentials
        return 1

    def get_playback_access_token(self, vod_id):
        """Gets a playback access token for a specified vod.

        :param vod_id: id of vod to retrieve token for
        :return: playback access token
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

        token = _r.json()['data']['videoPlaybackAccessToken']
        self.log.debug('Playback access token retrieved: %s', token)

        return token

    def get_live_broadcast_vod_id(self, channel):
        """Fetches the paired VOD ID for the currently live broadcast.

        :param channel: name of channel
        :return: vod id (if any returned)
        """
        _r = Api.gql_request('ChannelVideoLength', 'ac644fafd686f2cb0e3864075af7cf3bb33f4e0525bf84921b10eabaa4e048b5',
                             {"channelLogin": f"{channel.lower()}"})
        channel_video_length = _r.json()[0]['data']['user']['videos']['edges']

        if channel_video_length:
            broadcast_info = channel_video_length[0]['node']['id']
            self.log.debug('Live broadcast info: %s', broadcast_info)
            return broadcast_info

        self.log.debug('No data returned by ChannelVideoLength API.')

    def get_vod_index(self, vod_json, quality='best'):
        """Retrieves an index of m3u8 streams for a given VOD.

        :param vod_json: vod information retrieved from Twitch
        :param quality: desired quality in the format [resolution]p[framerate] or 'best', 'worst'
        :return: url of m3u8 playlist
        """
        access_token = self.get_playback_access_token(vod_json['vod_id'])

        _p = {
            'player': 'twitchweb',
            'nauth': access_token['value'],
            'nauthsig': access_token['signature'],
            'allow_source': 'true',
            'playlist_include_framerate': 'true',
            'p': randrange(1000000, 9999999)
        }

        try:
            _r = Api.get_request(f'https://usher.ttvnw.net/vod/{vod_json["vod_id"]}.m3u8', p=_p)

            _index = m3u8.loads(_r.text)

            # grab 'name' of m3u8 streams - contains [resolution]p[framerate]
            available_resolutions = [m[0].group_id.split('p') for m in [m.media for m in _index.playlists] if
                                     m[0].group_id != 'chunked']
            # insert 'chunked' stream separately as its named differently
            available_resolutions.insert(0, _index.media[0].name.split('p'))

        # catch for sub-only vods
        except TwitchAPIErrorForbidden as e:
            self.log.debug('VOD %s is subscriber-only. Generating index URL.', vod_json['id'])
            # retrieve cloudfront storage location from VOD thumbnail
            cf_info = vod_json['thumbnail_url'].split('/')
            cf_domain = cf_info[4]
            vod_uid = cf_info[5]

            # parse user-provided quality
            if quality == 'best':
                quality = 'chunked'
            elif quality == 'worst':
                quality = '160p30'
            else:
                quality = 'p'.join(quality)

            # create index url
            index_url = f'https://{cf_domain}.cloudfront.net/{vod_uid}/{quality}/index-dvr.m3u8'
            self.log.debug('Index URL for %s: %s', vod_json['user_name'])

            return index_url

        index = _index.playlists[get_quality_index(quality, available_resolutions)].uri
        self.log.debug('Index for VOD %s: %s', vod_json['id'], index)

        return index

    def get_channel_hls_index(self, channel, quality='best'):
        """Retrieves an index of a live m3u8 stream.

        :param channel: name of channel to retrieve index of
        :param quality: desired quality in the format [resolution]p[framerate] or 'best', 'worst'
        :return: url of m3u8 playlist
        """
        channel = channel.lower()

        access_token = Twitch.get_stream_playback_access_token(channel)

        _p = {
            'player': 'twitchweb',
            'fast_bread': 'true',
            'token': access_token['value'],
            'sig': access_token['signature'],
            'allow_source': 'true',
            'playlist_include_framerate': 'true',
            'player_backend': 'mediaplayer',
            'supported_codecs': 'avc1',
            'p': randrange(1000000, 9999999)
        }
        _r = Api.get_request(f'https://usher.ttvnw.net/api/channel/hls/{channel}.m3u8', p=_p)

        _index = m3u8.loads(_r.text)

        # grab 'name' of m3u8 streams - contains [resolution]p[framerate]
        available_resolutions = [m[0].group_id.split('p') for m in [m.media for m in _index.playlists] if
                                 m[0].group_id != 'chunked']
        # insert 'chunked' stream separately as its named differently and strip ' (source)' from name
        available_resolutions.insert(0, _index.media[0].name.strip(' (source)').split('p'))
        self.log.debug('Available resolutions for %s are: %s', channel, available_resolutions)

        return _index.playlists[get_quality_index(quality, available_resolutions)].uri

    def get_stream_playback_access_token(self, channel):
        """Gets a stream access token for a specified channel.

        :param channel: channel name to retrieve token for
        :return: playback access token
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

        access_token = _r.json()['data']['streamPlaybackAccessToken']
        self.log.debug('Access token retrieved for %s. %s', channel, access_token)

        return access_token

    def get_vod_category(self, vod_id):
        """Retrieves category for a specified VOD.

        :param vod_id: id of twitch vod to retrieve information for
        :return: name of category / game
        """
        _r = Api.gql_request('ComscoreStreamingQuery',
                             'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                             {"channel": "", "clipSlug": "", "isClip": False, "isLive": False,
                              "isVodOrCollection": True, "vodID": str(vod_id)})

        vod_category = _r.json()[0]['data']['video']['game']['name']
        self.log.debug('Category for VOD %s is %s', vod_id, vod_category)

        return vod_category

    def get_vod_status(self, user_id, vod_created_time):
        """Determines whether a live stream is paired with a given vod.

        :param user_id: twitch channel name
        :param vod_created_time: time and date a vod was created
        :return: True if vod and stream creation dates match
        """
        # wait until 1m has passed since vod created time as the stream api may not have updated yet
        time_since_created = time_since_date(
            datetime.strptime(vod_created_time, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())

        if time_since_created < 60:
            self.log.debug('VOD for channel with id %s created < 60 seconds ago, delaying status retrieval.', user_id)
            sleep(60 - time_since_created)

        try:
            # if stream live and vod start time matches
            stream_created_time = \
                datetime.strptime(self.get_api(f'streams?user_id={user_id}')['data'][0]['started_at'],
                                  '%Y-%m-%dT%H:%M:%SZ').timestamp()
            vod_created_time = datetime.strptime(vod_created_time, '%Y-%m-%dT%H:%M:%SZ').timestamp()
            # if vod created within 10s of stream created time
            if 10 >= vod_created_time - stream_created_time >= -10:
                self.log.debug('VOD creation time (%s) is within 10s of stream created time (%s), running in live mode.',
                               vod_created_time, stream_created_time)
                return True

        except IndexError:
            pass

        self.log.debug('Stream status could not be retrieved for user with id %s.', user_id)
        return False

    def get_vod_chapters(self, vod_id):
        """Retrieves the chapters for a given Twitch VOD.

        :param vod_id: id of twitch vod to retrieve chapters for
        :return: list of vod chapters
        """
        _r = Api.gql_request('VideoPlayer_ChapterSelectButtonVideo',
                             '8d2793384aac3773beab5e59bd5d6f585aedb923d292800119e03d40cd0f9b41',
                             {"includePrivate": False, "videoID": str(vod_id)})

        # extract and return list of moments from returned json
        chapters = [node['node'] for node in _r.json()[0]['data']['video']['moments']['edges']]

        self.log.debug('Chapters for VOD %s: %s', vod_id, chapters)

        try:
            return chapters

        except TypeError:
            self.log.debug('No chapters found for VOD %s', vod_id)
            return []

    def get_latest_video(self, channel):
        """Retrieves the latest video for a given channel.

        :param channel: channel to query
        :return: dict of VOD info
        """
        query_vars = {"broadcastType": "ARCHIVE", "channelOwnerLogin": f"{channel.lower()}", "limit": 30,
                      "videoSort": "TIME"}
        _r = Api.gql_request('FilterableVideoTower_Videos',
                             'a937f1d22e269e39a03b509f65a7490f9fc247d7f83d6ac1421523e3b68042cb',
                             query_vars)

        channel_videos = [v['node'] for v in _r.json()[0]['data']['user']['videos']['edges']]
        self.log.debug('Latest VOD for %: %', channel, channel_videos[0])

        return channel_videos[0]