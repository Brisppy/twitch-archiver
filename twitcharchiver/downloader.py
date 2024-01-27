"""
Classes related to Downloading methods and managing the downloading of a given VOD.
"""

import logging
import traceback
from pathlib import Path

from twitcharchiver.configuration import Configuration
from twitcharchiver.database import Database, INSERT_VOD
from twitcharchiver.exceptions import VodLockedError
from twitcharchiver.utils import get_temp_dir
from twitcharchiver.vod import ArchivedVod, Vod


class Downloader:
    """
    Strategy pattern for downloading methods.
    """

    def __init__(self, parent_dir: Path, quiet: bool):
        """
        Class Constructor.

        :param parent_dir: path to output downloaded VOD(s) to
        :param quiet: whether progress should be printed
        """
        self._parent_dir: Path = parent_dir
        self._quiet: bool = quiet

        self.vod = Vod()

        self._log = logging.getLogger()

    def start(self):
        """
        Start downloader functions.
        """
        return

    def merge(self):
        """
        Merge downloaded files.
        """
        return

    def export_metadata(self):
        """
        Export metadata for the stored VOD.
        """
        return

    def cleanup_temp_files(self):
        """
        Delete all temporary files.
        """
        return


class DownloadHandler:
    """
    Handles file locking and database insertion for VOD archiving.
    """

    def __init__(self, vod: ArchivedVod):
        """
        Class constructor.

        :param vod: VOD to be managed by download handler
        :type vod: ArchivedVod
        :raises VodAlreadyCompleted: if VOD is already completed in the requested formats according to the database
        :raises VodLockedError: if VOD is locked by another instance
        """
        self._log = logging.getLogger()

        _conf: dict = Configuration.get()
        self._lock_file = None
        self._config_dir: Path = _conf["config_dir"]
        self._with_database: bool = bool(_conf["channel"])
        self.vod: ArchivedVod = vod

        # build path to lock file based on if vod being archived or not
        if self.vod.v_id == 0:
            self._lock_fp = Path(
                get_temp_dir(),
                str(self.vod.s_id) + ".lock-stream",
            )

        else:
            self._lock_fp = Path(get_temp_dir(), str(self.vod.v_id) + ".lock")

    def __enter__(self):
        """
        Enable 'with' statement functions. Creates a lock file (if one doesn't already exist) for the VOD.

        :return: self
        """
        # attempt to create lock file
        if self.create_lock():
            raise VodLockedError(self.vod)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Enable 'with' statement functions. Removes the VOD lock file and inserts / updates the VOD database with VOD
        information.
        """
        # attempt to delete lock file
        if self.remove_lock():
            self._log.debug("Failed to remove lock file.")

        # don't bother adding to database if exception occurs
        if isinstance(exc_val, BaseException):
            self._log.error(
                "Exception occurred inside DownloadHandler. %s",
                traceback.format_tb(exc_tb),
            )

        else:
            # add VOD to database if exit not due to exception
            if self._with_database:
                self.insert_into_database()

    def create_lock(self):
        """
        Creates a lock file for a given VOD.

        :return: True on lock creation failure
        :rtype: bool
        """
        try:
            self._lock_file = open(self._lock_fp, "x")
            return False

        except FileExistsError:
            self._log.debug("Lock file exists for VOD %s.", self.vod)
            return True

    def remove_lock(self):
        """
        Removes a given lock file.

        :return: Exception string on failure
        """
        try:
            self._lock_file.close()
            self._lock_fp.unlink()
            return None

        except Exception as exc:
            self._log.debug("Failed to remove lock file for VOD %s. %s", self.vod, exc)
            return exc

    def insert_into_database(self):
        """
        Inserts (or updates) the VOD in the VOD database.
        """
        # check if VOD already in database
        with Database(Path(self._config_dir, "vods.db")) as _db:
            downloaded_vod = ArchivedVod.import_from_db(
                _db.execute_query(
                    "SELECT vod_id,stream_id,created_at,chat_archived,video_archived FROM vods WHERE stream_id IS ?",
                    {"stream_id": self.vod.s_id},
                )
            )

            # if already present update it
            if downloaded_vod:
                # set flags for updating
                self.vod.chat_archived = (
                    self.vod.chat_archived or downloaded_vod.chat_archived
                )
                self.vod.video_archived = (
                    self.vod.video_archived or downloaded_vod.video_archived
                )
                _db.execute_query(INSERT_VOD, self.vod.ordered_db_dict())

            else:
                _db.execute_query(INSERT_VOD, self.vod.ordered_db_dict())
