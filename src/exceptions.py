import json
import logging
import requests
import sys

log = logging.getLogger('twitch-archive')


class RequestError(Exception):
    def __init__(self, pushbullet_key, url, error):
        message_title = f'API request to {url} failed.'
        message_body = f'Error: {error}'
        send_push(pushbullet_key, message_title, message_body)
        super(RequestError, self).__init__(f'{message_title} {message_body}')


class TwitchAPIError(Exception):
    def __init__(self, pushbullet_key, url, status, response):
        message_title = f'Twitch API returned status code {status}.'
        message_body = f'URL: {url}, Response: {response}'
        send_push(pushbullet_key, message_title, message_body)
        super(TwitchAPIError, self).__init__(f'{message_title} {message_body}')


class TwitchAPIErrorForbidden(Exception):
    def __init__(self, pushbullet_key, url, status, response):
        message_title = f'Twitch API returned status code {status}.'
        message_body = f'URL: {url}, Response: {response}'
        send_push(pushbullet_key, message_title, message_body)
        super(TwitchAPIErrorForbidden, self).__init__(f'{message_title} {message_body}')


class TwitchAPIErrorBadRequest(Exception):
    def __init__(self, pushbullet_key, url, status, response):
        message_title = f'Twitch API returned status code {status}.'
        message_body = f'URL: {url}, Response: {response}'
        send_push(pushbullet_key, message_title, message_body)
        super(TwitchAPIErrorBadRequest, self).__init__(f'{message_title} {message_body}')


class TwitchAPIErrorNotFound(Exception):
    def __init__(self, pushbullet_key, url, status, response):
        message_title = f'Twitch API returned status code {status}.'
        message_body = f'URL: {url}, Response: {response}'
        send_push(pushbullet_key, message_title, message_body)
        super(TwitchAPIErrorNotFound, self).__init__(f'{message_title} {message_body}')


class VodDownloadError(Exception):
    def __init__(self, pushbullet_key, error, vod_id):
        message_title = f'VOD {vod_id} video download failed.'
        message_body = f'Error: {error}'
        send_push(pushbullet_key, message_title, message_body)
        super(VodDownloadError, self).__init__(f'{message_title} {message_body}')


class VodPartDownloadError(Exception):
    def __init__(self, error):
        super(VodPartDownloadError, self).__init__(f'{error}')


class VodMergeError(Exception):
    def __init__(self, pushbullet_key, error, vod_id):
        message_title = f'VOD {vod_id} part merging failed.'
        message_body = f'Error: {error}'
        send_push(pushbullet_key, message_title, message_body)
        super(VodMergeError, self).__init__(f'{message_title} {message_body}')


class VodConvertError(Exception):
    def __init__(self, error):
        super(VodConvertError, self).__init__(f'{error}')


class ChatDownloadError(Exception):
    def __init__(self, pushbullet_key, error, vod_id):
        message_title = f'VOD {vod_id} chat download failed.'
        message_body = f'Error: {error}'
        send_push(pushbullet_key, message_title, message_body)
        super(ChatDownloadError, self).__init__(f'{message_title} {message_body}')


class ChatExportError(Exception):
    def __init__(self, pushbullet_key, error, vod_id):
        message_title = f'VOD {vod_id} chat export failed.'
        message_body = f'Error: {error}'
        send_push(pushbullet_key, message_title, message_body)
        super(ChatExportError, self).__init__(f'{message_title} {message_body}')


class DatabaseError(Exception):
    def __init__(self, pushbullet_key, error, vod_id=None):
        if vod_id:
            message_title = f'VOD {vod_id} database query failed.'

        else:
            message_title = f'Sqlite database connection failed.'

        message_body = f'Error: {error}'
        send_push(pushbullet_key, message_title, message_body)
        super(DatabaseError, self).__init__(f'{message_title} {message_body}')


class DatabaseQueryError(Exception):
    @staticmethod
    def __init__(self, error):
        super(DatabaseQueryError, self).__init__(f'{error}')


class UnlockingError(Exception):
    @staticmethod
    def __init__(pushbullet_key, vod_id):
        message_title = f'Failed to remove VOD {vod_id}\'s lock file. Check VOD downloaded and remove manually.'
        send_push(pushbullet_key, message_title)


def send_push(pushbullet_key, err_title, err_body=''):
    """Sends a push to an account based on a given pushbullet key.

    :param pushbullet_key: key for destination pushbullet account. 'False' to not send.
    :param err_title: title to send with push
    :param err_body: body to send with push
    """
    if pushbullet_key:
        h = {"content-type": "application/json", "Authorization": 'Bearer ' + pushbullet_key}
        d = {"type": "note", "title": '[twitch-archiver] ' + err_title, "body": err_body}

        try:
            _r = requests.post(url="https://api.pushbullet.com/v2/pushes", headers=h, data=json.dumps(d))

        except Exception as e:
            log.error('Error sending push. ' + err_title + ' ' + err_body + '. ' + str(e))
            sys.exit(1)

        if _r.status_code != 200:
            log.error('Error sending push. ' + err_title + ' ' + err_body)
