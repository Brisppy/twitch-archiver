"""
Handles communication with the Twitch API.
"""
from time import sleep

import logging
import requests

from twitcharchiver.exceptions import RequestError, TwitchAPIError, TwitchAPIErrorNotFound, TwitchAPIErrorForbidden, \
    TwitchAPIErrorBadRequest


class Api:
    """
    Handles communication with the Twitch API.
    """
    def __init__(self):
        """
        Class constructor.
        """
        self._session = requests.session()
        self._headers = {}
        self.logging = logging.getLogger()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # cleanup
        self.close()

    def close(self):
        self._session.close()

    def add_headers(self, headers: dict):
        """
        Adds desired headers to all calls.
        :param headers: dictionary of header values to add
        :type headers: dict
        :return: updated headers
        :rtype:: dict
        """
        self._headers.update(headers)
        return self._headers

    def get_request(self, url: str, p: dict = None):
        """Wrapper for get requests for catching exceptions and status code issues.\n

            :param url: http/s endpoint to send request to
            :type url: str
            :param p: parameter(s) to pass with request
            :type p: dict
            :return: entire requests response
            :raises requestError: on requests module error
            :raises twitchAPIErrorBadRequest: on http code 400
            :raises twitchAPIErrorForbidden: on http code 403
            :raises twitchAPIErrorNotFound: on http code 404
            :raises twitchAPIError: on any http code other than 400, 403, 404 or 200
        """
        try:
            if p is None:
                _r = self._session.get(url, headers=self._headers, timeout=10)

            else:
                _r = self._session.get(url, params=p, timeout=10)

        except requests.exceptions.RequestException as err:
            raise RequestError(url, err) from err

        if _r.status_code == 400:
            raise TwitchAPIErrorBadRequest(_r)

        if _r.status_code == 403:
            raise TwitchAPIErrorForbidden(_r)

        if _r.status_code == 404:
            raise TwitchAPIErrorNotFound(_r)

        if _r.status_code != 200:
            raise TwitchAPIError(_r)

        return _r

    def post_request(self, url: str, d: dict = None, j: dict = None, h: dict = {}):
        """Wrapper for post requests for catching exceptions and status code issues.

        :param url: http/s endpoint to send request to
        :type url: str
        :param d: formatted data to send with request
        :type d: str
        :param j: json to send with request
        :type j: dict
        :param h: extra headers to send with request
        :type h: dict
        :return: entire requests response
        """
        if not (d or j):
            raise ValueError('Either data (d) or json (j) must be included with request.')

        try:
            if j is None:
                _r = self._session.post(url, data=d, headers=self.add_headers(h), timeout=10)

            elif d is None:
                _r = self._session.post(url, json=j, headers=self.add_headers(h), timeout=10)

        except requests.exceptions.RequestException as err:
            raise RequestError(url, err) from err

        if _r.status_code != 200:
            raise TwitchAPIError(_r)

        return _r

    def gql_request(self, operation: str, query_hash: str, variables: dict):
        """Post a gql query.

        :param operation: name of operation
        :type operation: str
        :param query_hash: hash of operation
        :type query_hash: str
        :param variables: dict of variable to post with request
        :type variables: dict
        :return: entire request response
        """
        # Uses default client header
        _h = {'Client-Id': 'ue6666qo983tsx6so1t0vnawi233wa'}
        _q = [{
            "extensions": {
                "persistedQuery": {
                    "sha256Hash": query_hash,
                    "version": 1
                }
            },
            "operationName": operation,
            "variables": variables
        }]

        # retry loop for 'service error' responses
        _attempt = 0
        while True:
            _r = self.post_request('https://gql.twitch.tv/gql', j=_q, h=_h)

            if _attempt >= 5:
                self.logging.error('Maximum attempts reached while querying GQL API. Error: %s', _r.json())
                raise TwitchAPIError(_r)

            if 'errors' in _r.json()[0].keys():
                _attempt += 1
                self.logging.error('Error returned when querying GQL API, retrying. Error: %s', _r.json())
                sleep(_attempt * 10)
                continue

            break

        return _r
