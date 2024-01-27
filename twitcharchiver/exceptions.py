"""
Custom exceptions used by Twitch Archiver.
"""

import logging
from pathlib import Path

import requests

from twitcharchiver.utils import get_temp_dir

log = logging.getLogger()


# Docstring for exception are used as exception message`.
# reference:
#   https://stackoverflow.com/a/66491013
class TwitchArchiverError(Exception):
    """Subclass exceptions use docstring as default message."""

    def __init__(self, msg=None, *args, **kwargs):
        self.__dict__.update(kwargs)
        super().__init__(msg or (self.__doc__, *args))


class RequestError(TwitchArchiverError):
    def __init__(self, url=None, exception=None):
        """
        :param url: url which returned an error
        :type url: str
        :param exception: exception object
        :type exception: Exception
        """
        message = ""
        if url and exception:
            message = f"API request to {url} failed. Error: {exception}"

        super().__init__(message)


class TwitchAPIError(TwitchArchiverError):
    def __init__(self, response=None):
        """
        :param response: request object
        :type response: requests.Response
        """
        message = ""
        if response:
            message = f"Twitch API returned status code {response.status_code}. URL: {response.url}, Response: {response.text}"

        super().__init__(message)


class TwitchAPIErrorForbidden(TwitchAPIError):
    """Twitch API returned 403 Forbidden."""


class TwitchAPIErrorBadRequest(TwitchAPIError):
    """Twitch API returned 400 Bad Request."""


class TwitchAPIErrorNotFound(TwitchAPIError):
    """Twitch API returned 404 Not Found."""


class StreamFetchError(TwitchArchiverError):
    """Error occurred while fetching stream information."""

    def __init__(self, channel=None):
        message = ""
        if channel:
            message = f"Error occurred while fetching information for stream by {channel.name}."

        super().__init__(message)


class StreamArchiveError(TwitchArchiverError):
    """Error occurred while archiving stream video."""


class StreamDownloadError(StreamArchiveError):
    """Error occurred while downloading stream."""

    def __init__(self, message=None):
        super().__init__(message)


class StreamSegmentDownloadError(StreamDownloadError):
    """Error occurred while downloading stream segment."""

    def __init__(self, segment=None, channel=None):
        message = ""
        if segment and channel:
            message = f"Error occurred while downloading stream segment {segment.id} for {channel.name}."

        super().__init__(message)


class UnsupportedStreamPartDuration(StreamDownloadError):
    def __init__(self):
        message = (
            "Multiple parts with unsupported duration found which cannot be accurately combined. "
            "Falling back to VOD archiver only."
        )

        super().__init__(message)


class StreamOfflineError(StreamArchiveError):
    def __init__(self, channel):
        message = f"Requested stream ({channel.name}) is not currently live."

        super().__init__(message)


class VideoArchiveError(TwitchArchiverError):
    """Error occurred while archiving VOD video."""


class VideoDownloadError(VideoArchiveError):
    """Error occurred while downloading VOD video."""


class VideoPartDownloadError(VideoDownloadError):
    """Error occurred while downloading VOD part."""


class VideoMergeError(VideoArchiveError):
    """Error occurred while merging VOD."""


class VideoVerificationError(VideoMergeError):
    """VOD failed verification check."""


class VideoConvertError(VideoMergeError):
    """Error occurred while converting VOD."""


class CorruptPartError(VideoConvertError):
    """Corrupt part(s) found while converting VOD. Delete VOD and re-download if issue persists."""

    def __init__(self, parts=None):
        """
        :param parts: set of corrupt parts
        :type parts: set[Part]
        """
        message = None
        self.parts = parts
        if parts:
            message = (
                f"Corrupt parts found when converting VOD file. Delete VOD and re-download if issue persists. "
                f"Parts: {[p.id for p in parts]}"
            )

        super().__init__(message)


class UnhandledDownloadError(TwitchArchiverError):
    def __init__(self, vod):
        # handle unsynced stream download (no vod id)
        if vod.v_id == 0:
            message = (
                f"An unhandled exception occurred while downloading stream {vod.s_id} by {vod.channel.name}. "
                f"Check stream downloaded correctly and remove lock file "
                f"({Path(get_temp_dir(), f'.lock.{vod.s_id}-stream-only')})."
            )

        else:
            message = (
                f"An unhandled exception occurred while downloading VOD {vod.v_id} by {vod.channel.name}. "
                f"Check stream downloaded correctly and remove lock file "
                f"({Path(get_temp_dir(), f'.lock.{vod.s_id}')})."
            )

        super().__init__(message)


class ChatArchiveError(TwitchArchiverError):
    """Error occurred while archiving chat for VOD."""


class ChatDownloadError(ChatArchiveError):
    """Error occurred while downloading VOD chat logs."""


class ChatExportError(ChatArchiveError):
    """Error occurred while exporting VOD chat logs."""

    def __init__(self, error):
        message = f"Chat export failed. Error: {error}"

        super().__init__(message)


class ChannelOfflineError(TwitchArchiverError):
    def __init__(self, channel):
        message = f"{channel.name} is offline."

        super().__init__(message)


class DatabaseError(TwitchArchiverError):
    def __init__(self, error, vod_id=None):
        if vod_id:
            message = f"VOD {vod_id} database query failed."

        else:
            message = "Sqlite database connection failed."

        message = f"{message} Error: {error}"

        super().__init__(message)


class DatabaseQueryError(TwitchArchiverError):
    def __init__(self, error):
        message = f"Error querying database. Error: {error}"

        super().__init__(message)


class VodAlreadyCompleted(TwitchArchiverError):
    def __init__(self, vod):
        message = f"VOD {vod.v_id} has already been completed in the requested formats according to the VOD database."

        super().__init__(message)


class VodUnlockingError(TwitchArchiverError):
    def __init__(self, vod):
        if vod.v_id:
            message = (
                f"Failed to remove lock file for stream {vod.v_id} by {vod.channel.name}. Check stream "
                f"downloaded correctly and remove '.lock.{vod.v_id}' file from config directory."
            )
        else:
            message = (
                f"Failed to remove lock file for stream {vod.v_id} by {vod.channel.name}. Check stream "
                f"downloaded correctly and remove '.lock.{vod.s_id}-stream' file from config directory."
            )

        super().__init__(message)


class VodLockedError(TwitchArchiverError):
    def __init__(self, vod):
        if vod.v_id:
            message = f"Lock file (.lock.{vod.v_id}) already present for VOD {vod.v_id} by {vod.channel.name}."
        else:
            message = f"Lock file (.lock.{vod.s_id}-stream) already present for stream {vod.v_id} by {vod.channel.name}."

        super().__init__(message)
