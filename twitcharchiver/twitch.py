"""
Handler for any requests made to the Twitch API.
"""

import logging

from datetime import datetime, timezone
from random import randrange
from time import sleep

import m3u8

from twitcharchiver.api import Api
from twitcharchiver.exceptions import TwitchAPIErrorForbidden, TwitchAPIErrorNotFound
from twitcharchiver.utils import get_quality_index, time_since_date, get_stream_id_from_preview_url


class Twitch:
    """
    Functions and processes for interacting with the Twitch API.
    """
    def __init__(self):
        """Class constructor.
        """
        self.log = logging.getLogger()

    def get_user_data(self, user):
        """Retrieve basic user login information.

        :param user: user to fetch
        :return: dictionary of user information
        """
        _r = Api.gql_request('ChannelShell', '580ab410bcd0c1ad194224957ae2241e5d252b2c5173d8e0cce9d32d5bb14efe',
                             {"login": f"{user.lower()}"})
        user_data = _r.json()[0]['data']['userOrError']
        self.log.debug('User data for %s: %s', user, user_data)

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
            self.log.debug('Retrieved videos for %s: %s', channel, _videos)
            channel_videos.extend(_videos)

            if _r.json()[0]['data']['user']['videos']['pageInfo']['hasNextPage'] is not False:
                # set cursor
                query_vars['cursor'] = _r.json()[0]['data']['user']['videos']['edges'][-1]['cursor']

            else:
                break

        self.log.debug('Full list of channels for %s: %s', channel, channel_videos)
        return channel_videos

    def get_stream_info(self, channel):
        """Retrieves information relating to a channel if it is currently live.

        :param channel: channel to retrieve information for
        :return: dict of stream info
        """
        query_vars = {"channel": channel, "clipSlug": "", "isClip": False, "isLive": True,
                      "isVodOrCollection": False, "vodID": ""}

        _r = Api.gql_request('ComscoreStreamingQuery',
                             'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                             query_vars)

        stream_info = _r.json()[0]['data']['user']
        self.log.debug('Stream info for %s: %s', channel, stream_info)

        if stream_info['stream']:
            return stream_info

        else:
            self.log.debug('No broadcast info found for %s', channel)

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
            self.log.debug('VOD %s is subscriber-only. Generating index URL.', vod_json['vod_id'])
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
        self.log.debug('Index for VOD %s: %s', vod_json['vod_id'], index)

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

    def get_vod_status(self, channel, vod_created_time):
        """Determines whether a live stream is paired with a given vod.

        :param channel: twitch channel name
        :param vod_created_time: time and date a vod was created
        :return: True if vod and stream creation dates match
        """
        # wait until 1m has passed since vod created time as the stream api may not have updated yet
        time_since_created = time_since_date(
            datetime.strptime(vod_created_time, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())

        if time_since_created < 60:
            self.log.debug('VOD for channel with id %s created < 60 seconds ago, delaying status retrieval.', channel)
            sleep(60 - time_since_created)

        try:
            # if stream live and vod start time matches
            stream_created_time = datetime.strptime(self.get_stream_info(channel)['stream']['createdAt'], '%Y-%m-%dT%H:%M:%SZ').timestamp()
            vod_created_time = datetime.strptime(vod_created_time, '%Y-%m-%dT%H:%M:%SZ').timestamp()
            # if vod created within 10s of stream created time
            if 10 >= vod_created_time - stream_created_time >= -10:
                self.log.debug('VOD creation time (%s) is within 10s of stream created time (%s), running in live mode.',
                               vod_created_time, stream_created_time)
                return True

        except IndexError:
            pass

        self.log.debug('Stream status could not be retrieved for user with id %s.', channel)
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

    def get_video_muted_segments(self, vod_id):
        """Retrieves muted segments for a given VOD.

        :param vod_id: ID of VOD to retrieve muted segments of
        :return: list
        """
        _r = Api.gql_request('VideoPlayer_MutedSegmentsAlertOverlay',
                             'c36e7400657815f4704e6063d265dff766ed8fc1590361c6d71e4368805e0b49',
                             {'includePrivate': False, 'vodID': vod_id})

        muted_segments = _r.json()[0]['data']['video']['muteInfo']['mutedSegmentConnection']

        if muted_segments:
            self.log.debug('Muted segments for VOD %s: %s', vod_id, muted_segments)
            return muted_segments['nodes']

        else:
            self.log.debug('No muted segments found for VOD %s.', vod_id)

    def get_video_metadata(self, vod_id):
        """Retrieves metadata for a given VOD. Formatting is used to ensure backwards compatibility.

        :param vod_id: VOD ID to retrieve metadata of
        :return: dict of data values
        """
        channel_data = self.get_vod_owner(vod_id)

        _r = Api.gql_request('VideoMetadata', 'c25707c1e5176320ceac6b447d052480887e23bc794ca1d02becd0bcc91844fe',
                             {'channelLogin': channel_data['name'], 'videoID': vod_id})

        vod_json = _r.json()[0]['data']['video']
        self.log.debug('Retrieved metadata for VOD %s: %s', vod_id, vod_json)

        # reformat to database schema
        vod_json['vod_id'] = vod_json.pop('id')
        vod_json['stream_id'] = self.get_stream_id_for_vod(vod_json['vod_id'])
        vod_json['user_id'] = channel_data['id']
        vod_json['user_login'] = channel_data['name'].lower()
        vod_json['user_name'] = channel_data['name']
        vod_json['game_name'] = vod_json['game']['displayName']
        vod_json['game_id'] = vod_json.pop('game')['id']
        vod_json['created_at'] = vod_json.pop('createdAt')
        vod_json['published_at'] = vod_json.pop('publishedAt')
        vod_json['url'] = 'https://twitch.tv/' + vod_json['user_login'] + '/' + vod_json['vod_id']
        vod_json['thumbnail_url'] = vod_json.pop('previewThumbnailURL')
        vod_json['view_count'] = vod_json.pop('viewCount')
        vod_json['duration'] = vod_json.pop('lengthSeconds')
        vod_json['muted_segments'] = self.get_video_muted_segments(vod_json['vod_id'])
        for key in ['owner', '__typename']:
            vod_json.pop(key)

        self.log.debug('Filled metadata for VOD %s: %s', vod_id, vod_json)

        return vod_json

    def get_vod_owner(self, vod_id):
        """Retrieves the channel which a given VOD belongs to

        :param vod_id: VOD ID of which to find related channel
        :return: dict of {id: vod_owner_id, name: vod_owner_name}
        """
        _r = Api.gql_request('ComscoreStreamingQuery',
                             'e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01',
                             {"channel": "", "clipSlug": "", "isClip": False, "isLive": False,
                              "isVodOrCollection": True, "vodID": str(vod_id)})

        owner = _r.json()[0]['data']['video']['owner']
        self.log.debug('Owner of VOD %s is %s.', vod_id, owner)

        return {'id': owner['id'], 'name': owner['displayName']}

    def get_stream_id_for_vod(self, vod_id):
        """Retrieves the stream ID for a given VOD

        :param vod_id: id of VOD to retrieve stream ID
        :return: stream id
        """
        _r = Api.gql_request('VideoPlayer_VODSeekbarPreviewVideo',
                             '07e99e4d56c5a7c67117a154777b0baf85a5ffefa393b213f4bc712ccaf85dd6',
                             {'includePrivate': False, 'videoID': vod_id})

        return get_stream_id_from_preview_url(_r.json()[0]['data']['video']['seekPreviewsURL'])