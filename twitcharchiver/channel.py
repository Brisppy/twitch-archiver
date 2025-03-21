"""
Class for retrieving and storing information related to channels and users.
"""
import logging
import sys
from datetime import datetime, timezone
from random import randrange

import m3u8

from twitcharchiver.api import Api
from twitcharchiver.exceptions import TwitchAPIError
from twitcharchiver.utils import time_since_date


class Channel:
    """
    Class for storing and retrieving data for a single Twitch channel / user.
    """

    def __init__(self, channel_name: str = "", channel_id: int = 0, owner: dict = None):
        """
        Initialize class variables.

        :param channel_name: name of channel
        :type channel_name: str
        :param owner: dict of channel values retrieved from Twitch
        :type owner: dict
        """
        self._api: Api = Api()
        self._log = logging.getLogger()

        self.id: int = channel_id
        self.name: str = channel_name
        self.display_name = ""
        self.stream: dict = {}
        self._broadcast_v_id = int()

        self._last_update: float = 0

        if owner:
            self._parse_dict(owner)

        elif self.name or self.id:
            self._parse_dict(self._fetch_metadata())

    def __repr__(self):
        return str(self.get_info())

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return bool(self.id == other.id)
        raise TypeError

    def __hash__(self):
        return hash(self.id)

    def __bool__(self):
        return bool(self.id)

    def get_info(self):
        """
        Returns a dict of important channel information.

        :return: dict of channel id, name and stream info.
        :rtype: dict
        """
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "stream": self.stream,
        }

    def _parse_dict(self, owner: dict):
        """
        Parses information from 'owner' object returned from Twitch.

        :param owner: channel owner object retrieved from Twitch
        """
        self.id = int(owner["id"])
        self.name = owner["login"]
        self.display_name = owner["displayName"]
        self.stream = owner["stream"]

    def _fetch_metadata(self):
        """
        Fetches metadata from Twitch regarding the channel.

        :return: retrieved user data
        :rtype dict
        """
        if self.id and not self.name:
            self.name = self._user_from_id(self.id)["login"]

        _r = self._api.gql_request(
            "ChannelShell",
            "580ab410bcd0c1ad194224957ae2241e5d252b2c5173d8e0cce9d32d5bb14efe",
            {"login": f"{self.name}"},
        )
        _user_data = _r.json()[0]["data"]["userOrError"]
        self._log.debug("User data for %s: %s", self.name, _user_data)

        # failure return contains "userDoesNotExist" key
        if "userDoesNotExist" not in _user_data.keys():
            self._last_update = datetime.now(timezone.utc).timestamp()
            return _user_data

        return {}

    def _user_from_id(self, channel_id: int):
        """
        Fetch information for the channel with the provided ID.

        :param channel_id: id of channel to fetch
        :return: dict of channel information
        :rtype: dict
        """
        _r = self._api.get_request(
            f"https://api.twitch.tv/helix/users?id={channel_id}",
            h={"Client-ID": "gh70y1spw727ohtgzbhc0hppvq9br2"},
        )

        return _r.json()["data"][0]

    def is_live(self, force_refresh=False):
        """
        Checks if the channel is currently live.

        :param force_refresh: True if cache to be ignored and metadata to be forcefully refreshed
        :type force_refresh: bool
        :return: True if channel live
        :rtype: bool
        """
        # refresh metadata if it was last updated more than 60 seconds ago
        if time_since_date(self._last_update) > 60 or force_refresh:
            self.refresh_metadata()
        return self.stream is not None

    def refresh_metadata(self):
        """
        Refreshes all metadata for the channel.
        """
        self._parse_dict(self._fetch_metadata())

    def get_stream_info(self):
        """Retrieves information relating to a channel if it is currently live.

        :return: dictionary with information about a channel's live stream if any
        :rtype: dict
        """
        _query_vars = {
            "channel": self.name,
            "clipSlug": "",
            "isClip": False,
            "isLive": True,
            "isVodOrCollection": False,
            "vodID": "",
        }

        _r = self._api.gql_request(
            "ComscoreStreamingQuery",
            "e1edae8122517d013405f237ffcc124515dc6ded82480a88daef69c83b53ac01",
            _query_vars,
        )

        _stream_info = _r.json()[0]["data"]["user"]

        if _stream_info:
            self._log.debug("Stream info for %s: %s", self.name, _stream_info)
            return _stream_info

        self._log.debug("No broadcast info found for %s", self.name)
        return {
            "id": "",
            "displayName": "",
            "stream": {},
            "broadcastSettings": {
                "id": "",
                "title": "",
                "__typename": "BroadcastSettings",
            },
            "__typename": "User",
        }

    def get_broadcast_v_id(self):
        """
        Fetches the paired VOD ID for the currently live broadcast.

        :return: VOD ID
        :rtype: int
        """
        _r = self._api.gql_request(
            "ChannelVideoLength",
            "ac644fafd686f2cb0e3864075af7cf3bb33f4e0525bf84921b10eabaa4e048b5",
            {"channelLogin": f"{self.name.lower()}"},
        )
        _channel_video_length = _r.json()[0]["data"]["user"]["videos"]["edges"]

        if _channel_video_length:
            broadcast_info = _channel_video_length[0]["node"]["id"]
            self._log.debug("Live broadcast info: %s", broadcast_info)
            return int(broadcast_info)

        self._log.debug("No data returned by ChannelVideoLength API for %s.", self.name)
        return int()

    def get_stream_index(self, quality: str = "best"):
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
            "player": "twitchweb",
            "fast_bread": "true",
            "token": _access_token["value"],
            "sig": _access_token["signature"],
            "allow_source": "true",
            "playlist_include_framerate": "true",
            "player_backend": "mediaplayer",
            "supported_codecs": "avc1",
            "p": randrange(1000000, 9999999),
        }
        _r = self._api.get_request(
            f"https://usher.ttvnw.net/api/channel/hls/{self.name.lower()}.m3u8", p=_p
        )

        _index = m3u8.loads(_r.text)

        # grab 'name' of m3u8 streams - contains [resolution]p[framerate]
        _available_resolutions = [
            m[0].group_id.split("p")
            for m in [m.media for m in _index.playlists]
            if m[0].group_id != "chunked"
        ]
        # insert 'chunked' stream separately as its named differently and strip ' (source)' from name
        _available_resolutions.insert(
            0, _index.media[0].name.strip(" (source)").split("p")
        )
        self._log.debug(
            "Available resolutions for %s are: %s", self.name, _available_resolutions
        )

        _index_url = _index.playlists[
            Vod.get_quality_index(quality, _available_resolutions)
        ].uri
        self._log.debug("Index for broadcast by %s: %s", self.name, _index_url)

        return _index_url

    def get_stream_playlist(self, index_url: str = ""):
        """
        Retrieves the playlist for a given VOD index along with updating the VOD duration.
        """
        if not index_url:
            index_url = self.get_stream_index()

        _stream_playlist = self._api.get_request(index_url).text

        return _stream_playlist

    def get_stream_playback_access_token(self):
        """
        Gets a stream access token for the channel.

        :return: dictionary of playback access token values
        :rtype: dict
        """
        try:
            _r = self._api.gql_request(
                "PlaybackAccessToken",
                "0828119ded1c13477966434e15800ff57ddacf13ba1911c129dc2200705b0712",
                {
                    "isLive": True,
                    "isVod": False,
                    "login": self.name,
                    "platform": "web",
                    "playerType": "frontpage",
                    "vodID": "",
                },
                include_oauth=True,
            )

        except TwitchAPIError as exc:
            self._log.error(
                "Error retrieving stream playback token, check that the provided OAuth token is valid."
            )
            raise exc

        _access_token = _r.json()[0]["data"]["streamPlaybackAccessToken"]
        self._log.debug("Access token retrieved for %s. %s", self.name, _access_token)

        return _access_token

    def _get_most_recent_videos(self):
        """
        Retrieves all recent broadcasts for the channel.

        :return: list of Vod objects
        :rtype: list[Vod]
        """
        from twitcharchiver.vod import Vod

        _r = self._api.gql_request(
            "FilterableVideoTower_Videos",
            "a937f1d22e269e39a03b509f65a7490f9fc247d7f83d6ac1421523e3b68042cb",
            {
                "broadcastType": "ARCHIVE",
                "channelOwnerLogin": f"{self.name.lower()}",
                "limit": 30,
                "videoSort": "TIME",
            },
        )

        _recent_videos = [
            Vod(vod_info=v["node"])
            for v in _r.json()[0]["data"]["user"]["videos"]["edges"]
        ]

        self._log.debug("Recent videos for %s: %s", self.name, _recent_videos)
        return _recent_videos

    def get_latest_video(self):
        """Retrieves the latest VOD for the channel.

        :return: The most recent VOD for the channel
        :rtype: Vod
        """
        _videos = self._get_most_recent_videos()
        if _videos:
            return _videos[0]

    def get_channel_archives(self):
        """
        Retrieves all available VODs for the channel.

        :return: list of all available VODs for the channel
        :rtype: list[Vod]
        """
        _query_vars = {
            "broadcastType": "ARCHIVE",
            "channelOwnerLogin": f"{self.name.lower()}",
            "limit": 30,
            "videoSort": "TIME",
        }

        videos = self._get_channel_videos(_query_vars)
        # set VOD type as none is provided by this query
        for v in videos:
            v.type = "ARCHIVE"

        self._log.debug("VODs retrieved for %s: %s", self.name, len(videos))

        return videos

    def get_channel_highlights(self):
        """
        Retrieves all available highlights for the channel.

        :return: list of all available highlights for the channel
        :rtype: list[Vod]
        """
        _query_vars = {
            "broadcastType": "HIGHLIGHT",
            "channelOwnerLogin": f"{self.name.lower()}",
            "limit": 30,
            "videoSort": "TIME",
        }

        videos = self._get_channel_videos(_query_vars)
        # set VOD type as none is provided by this query
        for v in videos:
            v.type = "HIGHLIGHT"

        self._log.debug("Highlights retrieved for %s: %s", self.name, len(videos))

        return videos

    def _get_channel_videos(self, _query_vars):
        """
        Retrieves all available videos for the channel.

        :return: list of all available videos for the channel
        :rtype: list[Vod]
        """
        from twitcharchiver import Vod

        _channel_videos = []
        while True:
            _r = self._api.gql_request(
                "FilterableVideoTower_Videos",
                "a937f1d22e269e39a03b509f65a7490f9fc247d7f83d6ac1421523e3b68042cb",
                _query_vars,
            )

            # retrieve list of videos from response
            _videos = [
                Vod(vod_info=v["node"])
                for v in _r.json()[0]["data"]["user"]["videos"]["edges"]
            ]
            _channel_videos.extend(_videos)

            if (
                _r.json()[0]["data"]["user"]["videos"]["pageInfo"]["hasNextPage"]
                is not False
            ):
                # set cursor
                _query_vars["cursor"] = _r.json()[0]["data"]["user"]["videos"]["edges"][
                    -1
                ]["cursor"]

            else:
                break

        return _channel_videos
