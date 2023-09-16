"""
Handler for API requests.
"""
import logging

import requests

from time import sleep

from twitcharchiver.exceptions import RequestError, TwitchAPIError, TwitchAPIErrorNotFound, TwitchAPIErrorForbidden, \
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

    @staticmethod
    def get_request_with_session(url, session):
        """Wrapper for get requests using a session for catching exceptions and status code issues.

        :param url: http/s endpoint to send request to
        :param session: a requests session for sending request
        :return: entire requests response
        """
        try:
            _r = session.get(url, timeout=10)

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

        except requests.exceptions.RequestException as err:
            raise RequestError(url, err) from err

        if _r.status_code != 200:
            raise TwitchAPIError(_r)

        return _r

    @staticmethod
    def post_request_with_session(url, session, j):
        """Wrapper for post requests for catching exceptions and status code issues.

        :param url: http/s endpoint to send request to
        :param session: requests session
        :param j: data to send with request as json
        :return: entire requests response
        """
        try:
            _r = session.post(url, json=j, timeout=10)

        except requests.exceptions.RequestException as err:
            raise RequestError(url, err) from err

        return _r

    @staticmethod
    def gql_request(operation, query_hash, variables):
        """Post a gql query.

        :param operation: name of operation
        :param query_hash: hash of operation
        :param variables: dict of variable to post with request
        :return: request response
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
        attempt = 0
        while True:
            _r = Api.post_request('https://gql.twitch.tv/gql', j=_q, h=_h)

            if attempt >= 5:
                logging.error('Maximum attempts reached while querying GQL API. Error: %s', _r.json())
                raise TwitchAPIError(_r)

            elif 'errors' in _r.json()[0].keys():
                attempt += 1
                logging.error('Error returned when querying GQL API, retrying. Error: %s', _r.json())
                sleep(attempt * 10)
                continue

            break

        return _r
