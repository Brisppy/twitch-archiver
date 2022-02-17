import logging

log = logging.getLogger('twitch-archive')


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
    def __init__(self, error, vod_id):
        self.message = f'VOD {vod_id} video download failed. Error: {error}'


class VodPartDownloadError(Exception):
    def __init__(self, error, vod_id):
        self.message = f'Error occurred while downloading VOD part. Error: {error}'


class VodMergeError(Exception):
    def __init__(self, error, vod_id):
        self.message = f'VOD {vod_id} part merging failed. Error: {error}'


class VodConvertError(Exception):
    def __init__(self, error, vod_id):
        self.message = f'Error occurred while converting VOD. Error: {error}'


class ChatDownloadError(Exception):
    def __init__(self, error, vod_id):
        self.message = f'VOD {vod_id} chat download failed. Error: {error}'


class ChatExportError(Exception):
    def __init__(self, error, vod_id):
        self.message = f'VOD {vod_id} chat export failed. Error: {error}'


class DatabaseError(Exception):
    def __init__(self, error, vod_id=None):
        if vod_id:
            self.message = f'VOD {vod_id} database query failed.'

        else:
            self.message = f'Sqlite database connection failed.'

        self.message = self.message + f' Error: {error}'


class DatabaseQueryError(Exception):
    def __init__(self, error):
        self.message = f'Error querying database. Error: {error}'


class UnlockingError(Exception):
    def __init__(self, vod_id):
        self.message = f'Failed to remove VOD {vod_id}\'s lock file. Check VOD downloaded correctly and remove manually.'
