"""
Custom exceptions used by Twitch Archiver.
"""

import logging
import tempfile
from pathlib import Path

log = logging.getLogger()


class RequestError(Exception):
    def __init__(self, url, error):
        message = f'API request to {url} failed. Error: {error}'

        super().__init__(message)


class TwitchAPIError(Exception):
    def __init__(self, response):
        message = \
            f'Twitch API returned status code {response.status_code}. URL: {response.url}, Response: {response.text}'

        super().__init__(message)


class TwitchAPIErrorForbidden(Exception):
    def __init__(self, response):
        self.response = response
        message = \
            f'Twitch API returned status code {response.status_code}. URL: {response.url}, Response: {response.text}'

        super().__init__(message)


class TwitchAPIErrorBadRequest(Exception):
    def __init__(self, response):
        message = \
            f'Twitch API returned status code {response.status_code}. URL: {response.url}, Response: {response.text}'

        super().__init__(message)


class TwitchAPIErrorNotFound(Exception):
    def __init__(self, response):
        self.response = response
        message = \
            f'Twitch API returned status code {response.status_code}. URL: {response.url}, Response: {response.text}'

        super().__init__(message)


class VodDownloadError(Exception):
    def __init__(self, error):
        message = f'Video download failed. Error: {error}'

        super().__init__(message)


class VodPartDownloadError(Exception):
    def __init__(self, error):
        message = f'Error occurred while downloading VOD part. Error: {error}'

        super().__init__(message)


class StreamFetchError(Exception):
    def __init__(self, channel_name, error):
        message = f'Error occurred while fetching information for stream by {channel_name}. Error: {error}'

        super().__init__(message)


class StreamDownloadError(Exception):
    def __init__(self, channel_name, error):
        message = f'Error occurred while downloading stream by {channel_name}. Error: {error}'

        super().__init__(message)


class StreamSegmentDownloadError(Exception):
    def __init__(self, segment_id, channel_name, error):
        message = f'Error occurred while downloading stream segment {segment_id} for {channel_name}. Error: {error}'

        super().__init__(message)


class VodMergeError(Exception):
    def __init__(self, error):
        message = f'Part merging failed. Error: {error}'

        super().__init__(message)


class VodVerificationError(Exception):
    def __init__(self, error):
        message = f'{error}'

        super().__init__(message)


class VodConvertError(Exception):
    def __init__(self, error):
        message = f'Video conversion failed. Error: {error}'

        super().__init__(message)


class CorruptPartError(Exception):
    def __init__(self, parts):
        """Raised when a corrupt part is detected by FFmpeg.

        :param parts: list of parts
        """
        self.parts = parts

        message = f'Corrupt parts found when converting VOD file. Delete VOD and re-download if issue persists. Parts: {[p.id for p in parts]}'

        super().__init__(message)


class ChatDownloadError(Exception):
    def __init__(self, error):
        message = f'Chat download failed. Error: {error}'

        super().__init__(message)


class ChatExportError(Exception):
    def __init__(self, error):
        message = f'Chat export failed. Error: {error}'

        super().__init__(message)


class ChannelOfflineError(Exception):
    def __init__(self, channel_name):
        message = f'{channel_name} is offline.'

        super().__init__(message)


class DatabaseError(Exception):
    def __init__(self, error, vod_id=None):
        if vod_id:
            message = f'VOD {vod_id} database query failed.'

        else:
            message = 'Sqlite database connection failed.'

        message = f'{message} Error: {error}'

        super().__init__(message)


class DatabaseQueryError(Exception):
    def __init__(self, error):
        message = f'Error querying database. Error: {error}'

        super().__init__(message)


class VodAlreadyCompleted(Exception):
    def __init__(self, vod):
        message = f"VOD {vod.v_id} has already been completed in the requested formats according to the VOD database."

        super().__init__(message)


class VodUnlockingError(Exception):
    def __init__(self, vod):
        if vod.v_id:
            message = f"Failed to remove lock file for stream {vod.v_id} by {vod.channel.name}. Check stream " \
                      f"downloaded correctly and remove '.lock.{vod.v_id}' file from config directory."
        else:
            message = f"Failed to remove lock file for stream {vod.v_id} by {vod.channel.name}. Check stream " \
                      f"downloaded correctly and remove '.lock.{vod.s_id}-stream' file from config directory."

        super().__init__(message)


class VodLockedError(Exception):
    def __init__(self, vod):
        if vod.v_id:
            message = f"Lock file (.lock.{vod.v_id}) already present for VOD {vod.v_id} by {vod.channel.name}."
        else:
            message = f"Lock file (.lock.{vod.s_id}-stream) already present for stream {vod.v_id} by {vod.channel.name}."

        super().__init__(message)


class UnhandledDownloadError(Exception):
    def __init__(self, vod):
        # handle unsynced stream download (no vod id)
        if vod.v_id == 0:
            message = f"An unhandled exception occurred while downloading stream {vod.s_id} by {vod.channel.name}. "\
                      f"Check stream downloaded correctly and remove lock file "\
                      f"({Path(tempfile.gettempdir(), 'twitch-archiver', f'.lock.{vod.s_id}-stream-only')})."

        else:
            message = f"An unhandled exception occurred while downloading VOD {vod.v_id} by {vod.channel.name}. "\
                      f"Check stream downloaded correctly and remove lock file "\
                      f"({Path(tempfile.gettempdir(), 'twitch-archiver', f'.lock.{vod.s_id}')})."

        super().__init__(message)


class UnsupportedStreamPartDuration(Exception):
    def __init__(self):
        message = 'Multiple parts with unsupported duration found which cannot be accurately combined. ' \
                  'Falling back to VOD archiver only.'

        super().__init__(message)


class StreamOfflineError(Exception):
    def __init__(self, channel):
        message = f'Requested stream ({channel.name}) is not currently live.'

        super().__init__(message)
