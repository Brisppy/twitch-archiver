"""
Module used for downloading chat logs for a given Twitch VOD.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import sleep

from twitcharchiver.api import Api
from twitcharchiver.downloader import Downloader
from twitcharchiver.exceptions import (
    TwitchAPIErrorNotFound,
    TwitchAPIErrorForbidden,
)
from twitcharchiver.utils import (
    Progress,
    get_time_difference,
    write_json_file,
    write_file_line_by_line,
    build_output_dir_name,
    time_since_date,
    parse_twitch_timestamp,
)
from twitcharchiver.vod import Vod, ArchivedVod

CHECK_INTERVAL = 60


class Chat(Downloader):
    """
    Class which handles the downloading, updating and importing of chat logs and the subsequent fomatting and archival.
    """

    def __init__(
        self, vod: Vod, parent_dir: Path = Path(os.getcwd()), quiet: bool = False
    ):
        """
        Initialize class variables.

        :param vod: VOD to be downloaded
        :param parent_dir: path to parent directory for downloaded files
        :param quiet: boolean whether to print progress
        """
        # init downloader
        super().__init__(parent_dir, quiet)

        # setup api with required header
        self._api = Api()
        self._api.add_headers({"Client-Id": "ue6666qo983tsx6so1t0vnawi233wa"})

        # vod-specific vars
        self.vod: Vod = vod
        # create output dir
        self.output_dir = Path(
            self._parent_dir,
            build_output_dir_name(self.vod.title, self.vod.created_at, self.vod.v_id),
        )

        # store chat log and seen message ids
        self._chat_log: list = []
        self._chat_message_ids: set = set()

        # load chat from file if a download was attempted previously
        self.load_from_file()

    def export_metadata(self):
        write_json_file(self.vod.to_dict(), Path(self.output_dir, "vod.json"))

    def load_from_file(self):
        """
        Loads the chat log stored in the output directory.
        """
        try:
            with open(
                Path(self.output_dir, "verbose_chat.json"), "r", encoding="utf8"
            ) as chat_file:
                self._log.debug("Loading chat log from file.")
                chat_log = json.loads(chat_file.read())

            # ignore chat logs created with older incompatible schema - see v2.2.1 changes
            if chat_log and "contentOffsetSeconds" not in chat_log[0].keys():
                self._log.debug(
                    "Ignoring chat log loaded from file as it is incompatible."
                )
                return
            self._log.debug("Chat log found for VOD %s.", self.vod)
            self._chat_log = chat_log
            # add chat messages to id set
            self._chat_message_ids.update(m["id"] for m in chat_log)
            return

        except FileNotFoundError:
            return

    def start(self):
        """
        Downloads the chat for the given VOD and exports both a readable and JSON-formatted log to the provided
        directory.

        :return: list of dictionaries containing chat message data
        :rtype: list[dict]
        """
        try:
            # create output dir
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)

            self._download()
            self.export_chat_logs()

            # use while loop for archiving live VODs
            while self.vod.is_live():
                self._log.debug(
                    "VOD is still live, attempting to download new chat segments."
                )
                _start_timestamp: float = datetime.now(timezone.utc).timestamp()

                # refresh VOD metadata
                self.vod.refresh_vod_metadata()

                # begin downloader from offset of previous log
                if self._chat_log:
                    self._download(self._chat_log[-1]["contentOffsetSeconds"])
                else:
                    self._download()
                self.export_chat_logs()

                # sleep if processing time < CHECK_INTERVAL before fetching new messages
                _loop_time = int(
                    datetime.now(timezone.utc).timestamp() - _start_timestamp
                )
                if _loop_time < CHECK_INTERVAL:
                    sleep(CHECK_INTERVAL - _loop_time)

            # delay final archive pass if stream just ended
            self.vod.refresh_vod_metadata()
            if time_since_date(self.vod.created_at + self.vod.duration) < 300:
                self._log.debug(
                    "Stream ended less than 5m ago, delaying before final chat archive attempt."
                )
                sleep(300)

                # refresh VOD metadata
                self.vod.refresh_vod_metadata()
                if self._chat_log:
                    self._download(self._chat_log[-1]["contentOffsetSeconds"])
                else:
                    self._download()

        except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
            self._log.debug(
                "Error 403 or 404 returned when checking for new chat segments - VOD was likely deleted."
            )

        finally:
            self.export_chat_logs()

        # logging
        self._log.info("Found %s chat messages.", len(self._chat_log))

        # set archival flag if ArchivedVod provided
        if isinstance(self.vod, ArchivedVod):
            self.vod.chat_archived = True

    def _download(self, offset: int = 0):
        """
        Downloads the chat log in its entirety.

        :param offset: time to begin archiving from in seconds
        :return: list of all chat messages
        :rtype: list
        """
        _progress = Progress()
        start_len = len(self._chat_log)

        # grab initial chat segment containing cursor
        _initial_segment, _cursor = self._get_chat_segment(offset=offset)
        self._chat_log.extend(
            [m for m in _initial_segment if m["id"] not in self._chat_message_ids]
        )
        self._chat_message_ids.update([m["id"] for m in _initial_segment])

        while True:
            if not _cursor:
                self._log.debug(
                    f"{len(self._chat_log) - start_len} messages retrieved from Twitch."
                )
                break

            self._log.debug("Fetching chat segments at cursor: %s.", _cursor)
            # grab next chat segment along with cursor for next segment
            _segment, _cursor = self._get_chat_segment(cursor=_cursor)
            self._chat_log.extend(
                [m for m in _segment if m["id"] not in self._chat_message_ids]
            )
            self._chat_message_ids.update([m["id"] for m in _segment])
            # vod duration in seconds is used as the total for progress bar
            # comment offset is used to track what's been done
            # could be done properly if there was a way to get the total number of comments
            if not self._quiet:
                _progress.print_progress(
                    int(_segment[-1]["contentOffsetSeconds"]), self.vod.duration
                )

    def _get_chat_segment(self, offset: int = 0, cursor: str = ""):
        """
        Retrieves a chat segment and any subsequent segments from a given offset.

        :param offset: offset in seconds to begin retrieval from
        :type offset: int
        :param cursor: cursor returned by a previous call of this function
        :type cursor: str
        :returns: list of comments, cursor if one is returned from twitch
        :rtype: list, str
        """
        # build payload
        if offset != 0:
            _p = [
                {
                    "operationName": "VideoCommentsByOffsetOrCursor",
                    "variables": {
                        "videoID": str(self.vod.v_id),
                        "contentOffsetSeconds": offset,
                    },
                }
            ]

        else:
            _p = [
                {
                    "operationName": "VideoCommentsByOffsetOrCursor",
                    "variables": {"videoID": str(self.vod.v_id), "cursor": cursor},
                }
            ]

        _p[0]["extensions"] = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a",
            }
        }

        _r = self._api.post_request("https://gql.twitch.tv/gql", j=_p).json()
        _comments = _r[0]["data"]["video"]["comments"]

        # check if next page exists
        if _comments:
            if _comments["pageInfo"]["hasNextPage"]:
                return [c["node"] for c in _comments["edges"]], _comments["edges"][-1][
                    "cursor"
                ]

            return [c["node"] for c in _comments["edges"]], None

        return [], None

    def generate_readable_chat_log(self, chat_log: list):
        """
        Converts the raw chat log into a human-readable format.

        :param chat_log: list of messages to generate log from
        :type chat_log: list
        """
        _r_chat_log = []
        for _comment in chat_log:
            _created_time = parse_twitch_timestamp(_comment["createdAt"])

            _comment_time = (
                f"{get_time_difference(self.vod.created_at, _created_time):.3f}"
            )

            # catch comments without commenter information
            if _comment["commenter"]:
                _user_name = str(_comment["commenter"]["displayName"])
            else:
                _user_name = "~MISSING_COMMENTER_INFO~"

            # catch comments without data
            if _comment["message"]["fragments"]:
                _user_message = str(_comment["message"]["fragments"][0]["text"])
            else:
                _user_message = "~MISSING_MESSAGE_INFO~"

            _user_badges = ""
            try:
                for _badge in _comment["message"]["userBadges"]:
                    if "broadcaster" in _badge["setID"]:
                        _user_badges += "(B)"

                    if "moderator" in _badge["setID"]:
                        _user_badges += "(M)"

                    if "subscriber" in _badge["setID"]:
                        _user_badges += "(S)"

            except KeyError:
                pass

            # FORMAT: [TIME] (B1)(B2)NAME: MESSAGE
            _r_chat_log.append(
                f"[{_comment_time}] {_user_badges}{_user_name}: {_user_message}"
            )

        return _r_chat_log

    def export_chat_logs(self):
        """
        Exports a readable and a JSON-formatted chat log to the output directory.
        """
        write_file_line_by_line(
            self.generate_readable_chat_log(self._chat_log),
            Path(self.output_dir, "readable_chat.txt"),
        )
        write_json_file(self._chat_log, Path(self.output_dir, "verbose_chat.json"))

    def get_message_count(self):
        """
        Fetches the total number of retrieved chat messages.

        :return:
        """
        return len(self._chat_log)
