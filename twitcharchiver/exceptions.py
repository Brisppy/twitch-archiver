"""
Custom exceptions used by Twitch Archiver.
"""

import logging

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


class VodMergeError(Exception):
    def __init__(self, error):
        message = f'Part merging failed. Error: {error}'

        super().__init__(message)


class VodConvertError(Exception):
    def __init__(self, error):
        message = f'Video conversion failed. Error: {error}'

        super().__init__(message)


class CorruptPartError(Exception):
    def __init__(self, parts, formatted_ranges):
        """Raised when a corrupt part is detected by FFmpeg.

        :param parts: un-formatted list of parts
        :param formatted_ranges: formatted list of parts
        """
        self.parts = parts
        self.f_parts = formatted_ranges

        message = f'Corrupt parts found when converting VOD file. Parts: {formatted_ranges}'

        super().__init__(message)


class ChatDownloadError(Exception):
    def __init__(self, error):
        message = f'Chat download failed. Error: {error}'

        super().__init__(message)


class ChatExportError(Exception):
    def __init__(self, error):
        message = f'Chat export failed. Error: {error}'

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


class UnlockingError(Exception):
    def __init__(self, channel_name, stream_id, vod_id=None):
        if vod_id:
            message = f"Failed to remove lock file for VOD {vod_id} by {channel_name}. Check VOD downloaded " \
                      f"correctly and remove '.lock.{stream_id}' file from config directory."
        else:
            message = f"Failed to remove lock file for stream {stream_id} by {channel_name}. Check stream" \
                      f"downloaded correctly and remove '.lock.{stream_id}-stream-only' file from config directory."

        super().__init__(message)

class UnsupportedStreamPartDuration(Exception):
    def __init__(self):
        message = 'Multiple parts with unsupported duration found which cannot be accurately combined. ' \
                  'Falling back to VOD archiver only.'

        super().__init__(message)