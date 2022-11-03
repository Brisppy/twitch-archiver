import requests

from src.exceptions import RequestError, TwitchAPIError, TwitchAPIErrorNotFound, TwitchAPIErrorForbidden, \
    TwitchAPIErrorBadRequest


class Api:
    """
    Sends requests to a specified API endpoint.
    """
    @staticmethod
    def get_request(url, p=None, h=None):
        """
        Wrapper for get requests for catching exceptions and status code issues.\n

            :param url: http/s endpoint to send request to
            :param p: parameter(s) to pass with request
            :param h: header(s) to pass with request
            :return: entire requests response
            :raises requestError: on requests module error
            :raises twitchAPIErrorBadRequest: on http code 400
            :raises twitchAPIErrorForbidden: on http code 403
            :raises twitchAPIErrorNotFound: on http code 404
            :raises twitchAPIError: on any http code other than 400, 403, 404 or 200
        """
        try:
            if p is None:
                _r = requests.get(url, headers=h, timeout=10)

            else:
                _r = requests.get(url, params=p, timeout=10)

        except requests.exceptions.RequestException as e:
            raise RequestError(url, e)

        if _r.status_code == 400:
            raise TwitchAPIErrorBadRequest(url, _r.status_code, _r.text)

        if _r.status_code == 403:
            raise TwitchAPIErrorForbidden(url, _r.status_code, _r.text)

        if _r.status_code == 404:
            raise TwitchAPIErrorNotFound(url, _r.status_code, _r.text)

        if _r.status_code != 200:
            raise TwitchAPIError(url, _r.status_code, _r.text)

        return _r

    @staticmethod
    def get_request_with_session(url, session):
        """Wrapper for get requests using a session for catching exceptions and status code issues.

        :param url: http/s endpoint to send request to
        :param session: a requests session for sending request
        :return: entire requests response
        """
        try:
            _r = session.get(url, timeout=10)

        except requests.exceptions.RequestException as e:
            raise RequestError(url, e)

        if _r.status_code == 400:
            raise TwitchAPIErrorBadRequest(url, _r.status_code, _r.text)

        if _r.status_code == 403:
            raise TwitchAPIErrorForbidden(url, _r.status_code, _r.text)

        if _r.status_code == 404:
            raise TwitchAPIErrorNotFound(url, _r.status_code, _r.text)

        if _r.status_code != 200:
            raise TwitchAPIError(url, _r.status_code, _r.text)

        return _r

    @staticmethod
    def post_request(url, d=None, j=None, h=None):
        """Wrapper for post requests for catching exceptions and status code issues.

        :param url: http/s endpoint to send request to
        :param d: data to send with request
        :param j: data to send with request as json
        :param h: headers to send with request
        :return: entire requests response
        """
        try:
            if j is None:
                _r = requests.post(url, data=d, headers=h, timeout=10)

            elif d is None:
                _r = requests.post(url, json=j, headers=h, timeout=10)

        except requests.exceptions.RequestException as e:
            raise RequestError(url, e)

        if _r.status_code != 200:
            raise TwitchAPIError(url, _r.status_code, _r.text)

        return _r
