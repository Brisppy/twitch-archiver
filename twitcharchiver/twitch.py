"""
Handler for any requests made to the Twitch API.
"""

import logging

from datetime import datetime, timezone
from random import randrange
from time import sleep

import m3u8

from twitcharchiver.api import Api
from twitcharchiver.exceptions import TwitchAPIError, TwitchAPIErrorForbidden
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

    @staticmethod
    def get_playback_access_token(vod_id):
        """Gets a playback access token for a specified vod.

        :param vod_id: id of vod to retrieve token for
        :return: playback access token
        """
        # only accepts the default client ID for non-authenticated clients
        _h = {'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko'}
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

        return _r.json()['data']['videoPlaybackAccessToken']

    @staticmethod
    def get_latest_channel_broadcast(channel):
        """Retrieves most recent archived broadcast. More reliable than helix API for VODs created within the last
        few seconds.

        :param channel: Name of Twitch channel/user
        :return: set of most recent values of (stream_id, vod_id)
        """
        # Uses default client header
        _h = {'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko'}
        _q = [{
            "extensions": {
                "persistedQuery": {
                    "sha256Hash": "8afefb1ed16c4d8e20fa55024a7ed1727f63b6eca47d8d33a28500770bad8479",
                    "version": 1
                }
            },
            "operationName": "ChannelVideoShelvesQuery",
            "variables": {
                "channelLogin": f"{channel.lower()}",
                "first": 5,
            }
        }]

        _r = Api.post_request('https://gql.twitch.tv/gql', j=_q, h=_h)
        _d = _r.json()[0]['data']['user']['videoShelves']['edges']

        # extract vod and stream ids from thumbnail url (stream id isnt provided with this call) and add to id list.
        # _d will be empty if no archives available.
        if _d:
            # iter over edges as the order may change, or LATEST_BROADCASTS not provided if none found
            for edge in _d:
                if edge['node']['type'] == 'LATEST_BROADCASTS':
                    _thumbnail_url = edge['node']['items'][0]['animatedPreviewURL'].split('/')
                    _id = (_thumbnail_url[3].split('_')[2], _thumbnail_url[5].split('-')[0])
                    return _id

        return

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
            return index_url

        return _index.playlists[get_quality_index(quality, available_resolutions)].uri

    @staticmethod
    def get_channel_hls_index(channel, quality='best'):
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

        return _index.playlists[get_quality_index(quality, available_resolutions)].uri

    @staticmethod
    def get_stream_playback_access_token(channel):
        """Gets a stream access token for a specified channel.

        :param channel: channel name to retrieve token for
        :return: playback access token
        """
        # only accepts the default client ID for non-authenticated clients
        _h = {'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko'}
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

        return _r.json()['data']['streamPlaybackAccessToken']

    @staticmethod
    def get_vod_category(vod_id):
        """Retrieves category for a specified VOD.

        :param vod_id: id of twitch vod to retrieve information for
        :return: name of category / game
        """
        _h = {'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko'}
        _q = [{
            "extensions": {
                "persistedQuery": {
                    "sha256Hash": "e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01",
                    "version": 1
                }
            },
            "operationName": "ComscoreStreamingQuery",
            "variables": {
                "channel": "",
                "clipSlug": "",
                "isClip": False,
                "isLive": False,
                "isVodOrCollection": True,
                "vodID": str(vod_id)
            }
        }]

        _r = Api.post_request('https://gql.twitch.tv/gql', j=_q, h=_h)

        return _r.json()[0]['data']['video']['game']['name']

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
            sleep(60 - time_since_created)
        try:
            # if stream live and vod start time matches
            stream_created_time = \
                datetime.strptime(self.get_api(f'streams?user_id={user_id}')['data'][0]['started_at'],
                                  '%Y-%m-%dT%H:%M:%SZ').timestamp()
            vod_created_time = datetime.strptime(vod_created_time, '%Y-%m-%dT%H:%M:%SZ').timestamp()
            # if vod created within 10s of stream created time
            if 10 >= vod_created_time - stream_created_time >= -10:
                self.log.debug('VOD creation time is within 10s of stream created time, running in live mode.')
                return True

        except IndexError:
            pass

        return False

    @staticmethod
    def get_vod_chapters(vod_id):
        """Retrieves the chapters for a given Twitch VOD.

        :param vod_id: id of twitch vod to retrieve chapters for
        :return: list of vod chapters
        """
        _h = {'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko'}
        _q = [{
            "extensions": {
                "persistedQuery": {
                    "sha256Hash": "8d2793384aac3773beab5e59bd5d6f585aedb923d292800119e03d40cd0f9b41",
                    "version": 1
                }
            },
            "operationName": "VideoPlayer_ChapterSelectButtonVideo",
            "variables": {
                "includePrivate": False,
                "videoID": str(vod_id)
            }
        }]

        _r = Api.post_request('https://gql.twitch.tv/gql', j=_q, h=_h)

        # extract and return list of moments from returned json
        try:
            return [node['node'] for node in _r.json()[0]['data']['video']['moments']['edges']]

        except TypeError:
            return []
