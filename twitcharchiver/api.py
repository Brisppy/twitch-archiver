"""
Handles communication with the Twitch API.
"""
import logging
from time import sleep

import requests

from twitcharchiver.exceptions import (
    RequestError,
    TwitchAPIError,
    TwitchAPIErrorNotFound,
    TwitchAPIErrorForbidden,
    TwitchAPIErrorBadRequest,
)


class Api:
    """
    Handles communication with the Twitch API.
    """

    __instance = None

    def __new__(cls, *args, **kwargs):
        if cls.__instance is None:
            cls.__instance = super(Api, cls).__new__(cls)
            cls.__instance.__initialize()

        return cls.__instance

    def __initialize(self):
        """
        Class constructor.
        """
        self._session = requests.session()
        self._headers = {}
        self.oauth_token = ""
        self.logging = logging.getLogger()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # cleanup
        self.close()

    def close(self):
        """
        Cleanly shutdown requests session.
        """
        self._session.close()

    def add_headers(self, headers: dict):
        """
        Adds desired headers to all calls.

        :param headers: dictionary of header values to add
        :return: updated headers
        :rtype: dict
        """
        self._headers.update(headers)
        return self._headers

    def get_request(self, url: str, p: dict = None, h: dict = None):
        """
        Wrapper for get requests for catching exceptions and status code issues.\n

        :param url: http/s endpoint to send request to
        :param p: parameter(s) to pass with request
        :param h: header to pass with request (overrides class headers)
        :return: entire requests response
        :raises requestError: on requests module error
        :raises TwitchAPIErrorBadRequest: on http code 400
        :raises TwitchAPIErrorForbidden: on http code 403
        :raises TwitchAPIErrorNotFound: on http code 404
        :raises TwitchAPIError: on any http code other than 400, 403, 404 or 200
        """
        _headers = h or self._headers
        _params = p

        # request retry loop
        for _ in range(6):
            try:
                _r = self._session.get(
                    url, headers=_headers, params=_params, timeout=10
                )

                # unrecoverable exceptions
                if _r.status_code == 400:
                    raise TwitchAPIErrorBadRequest(_r)
                if _r.status_code == 403:
                    raise TwitchAPIErrorForbidden(_r)
                if _r.status_code == 404:
                    raise TwitchAPIErrorNotFound(_r)
                if _r.status_code != 200:
                    raise TwitchAPIError(_r)

                return _r

            # recoverable exceptions
            except requests.exceptions.RequestException as err:
                if _ == 5:
                    self.logging.error("Maximum attempts reached for request.")
                    raise RequestError(url, err) from err

                self.logging.error(
                    "Exception encountered during GET request, retrying. Error: %s", err
                )
                sleep(_ * 10)
                continue

    def post_request(self, url, d=None, j=None, h=None):
        """
        Wrapper for post requests for catching exceptions and status code issues.

        :param url: http/s endpoint to send request to
        :type url: str
        :param d: formatted data to send with request
        :type d: str
        :param j: json to send with request
        :type j: dict or list
        :param h: override class headers to send with request
        :type h: dict
        :return: entire requests response
        """
        if not (d or j):
            raise ValueError(
                "Either data (d) or json (j) must be included with request."
            )

        # request retry loop
        for _ in range(6):
            try:
                if j is None:
                    _r = self._session.post(
                        url, data=d, headers=h if h else self._headers, timeout=10
                    )
                elif d is None:
                    _r = self._session.post(
                        url, json=j, headers=h if h else self._headers, timeout=10
                    )

                if _r.status_code != 200:
                    raise TwitchAPIError(_r)

                return _r

            except requests.exceptions.RequestException as err:
                if _ == 5:
                    self.logging.error("Maximum attempts reached for request.")
                    raise RequestError(url, err) from err

                self.logging.error(
                    "Exception encountered during POST request, retrying. Error: %s",
                    err,
                )
                sleep(_ * 10)
                continue

    def gql_request(
        self,
        operation: str,
        query_hash: str,
        variables: dict,
        include_oauth: bool = False,
    ):
        """
        Post a gql query and returns the response.

        :param operation: name of operation
        :param query_hash: hash of operation
        :param variables: dict of variable to post with request
        :param include_oauth: bool whether to include oauth token in header
        :return: entire request response
        :rtype: requests.Response
        """
        # Uses default client header
        _h = {"Client-Id": "ue6666qo983tsx6so1t0vnawi233wa"}

        # set authorization token if requested and configured
        if include_oauth and self.oauth_token:
            _h["Authorization"] = f"OAuth {self.oauth_token}"

        _q = [
            {
                "extensions": {
                    "persistedQuery": {"sha256Hash": query_hash, "version": 1}
                },
                "operationName": operation,
                "variables": variables,
            }
        ]

        # retry loop for 'service error' responses
        for _ in range(6):
            _r = self.post_request("https://gql.twitch.tv/gql", j=_q, h=_h)

            if "errors" in _r.json()[0].keys():
                if _ == 5:
                    self.logging.error(
                        "Maximum attempts reached while querying GQL API. Error: %s",
                        _r.json(),
                    )
                    raise TwitchAPIError(_r)

                self.logging.error(
                    "Error returned when querying GQL API, retrying. Error: %s",
                    _r.json(),
                )
                sleep(_ * 10)
                continue

            return _r
