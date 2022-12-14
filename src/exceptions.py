import logging

log = logging.getLogger()


class RequestError(Exception):
    def __init__(self, url, error):
        self.message = f'API request to {url} failed. Error: {error}'


class TwitchAPIError(Exception):
    def __init__(self, url, status, response):
        self.message = f'Twitch API returned status code {status}. URL: {url}, Response: {response}'


class TwitchAPIErrorForbidden(Exception):
    def __init__(self, url, status, response):
        self.message = f'Twitch API returned status code {status}. URL: {url}, Response: {response}'


class TwitchAPIErrorBadRequest(Exception):
    def __init__(self, url, status, response):
        self.message = f'Twitch API returned status code {status}. URL: {url}, Response: {response}'


class TwitchAPIErrorNotFound(Exception):
    def __init__(self, url, status, response):
        self.message = f'Twitch API returned status code {status}. URL: {url}, Response: {response}'


class VodDownloadError(Exception):
    def __init__(self, error):
        self.message = f'Video download failed. Error: {error}'


class VodPartDownloadError(Exception):
    def __init__(self, error):
        self.message = f'Error occurred while downloading VOD part. Error: {error}'


class VodMergeError(Exception):
    def __init__(self, error):
        self.message = f'Part merging failed. Error: {error}'


class VodConvertError(Exception):
    def __init__(self, error):
        self.message = f'Video conversion failed. Error: {error}'


class ChatDownloadError(Exception):
    def __init__(self, error):
        self.message = f'Chat download failed. Error: {error}'


class ChatExportError(Exception):
    def __init__(self, error):
        self.message = f'Chat export failed. Error: {error}'


class DatabaseError(Exception):
    def __init__(self, error, vod_id=None):
        if vod_id:
            self.message = f'VOD {vod_id} database query failed.'

        else:
            self.message = f'Sqlite database connection failed.'

        self.message = f'{self.message} Error: {error}'


class DatabaseQueryError(Exception):
    def __init__(self, error):
        self.message = f'Error querying database. Error: {error}'


class UnlockingError(Exception):
    def __init__(self, channel_name, stream_id, vod_id=None):
        if vod_id:
            self.message = f"Failed to remove lock file for VOD {vod_id} by {channel_name}. Check VOD downloaded correctly " \
                           f"and remove '.lock.{stream_id}' file from config directory."
        else:
            self.message = f"Failed to remove lock file for stream {stream_id} by {channel_name}. Check strean" \
                           f"downloaded correctly and remove '.lock.{stream_id}-stream-only' file from config directory."
