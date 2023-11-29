"""
Classes related to Downloading methods and managing the downloading of a given VOD.
"""

import logging
import tempfile

from pathlib import Path

from twitcharchiver.configuration import Configuration
from twitcharchiver.exceptions import VodAlreadyCompleted, VodLockedError
from twitcharchiver.database import Database, INSERT_VOD
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
        self._config_dir: Path = _conf['config_dir']
        self._with_database: bool = bool(_conf['channel'])
        self.vod: ArchivedVod = vod

        # build path to lock file based on if vod being archived or not
        if self.vod.v_id == 0:
            self._lock_fp = Path(tempfile.gettempdir(), 'twitch-archiver', str(self.vod.s_id) + '.lock-stream')

        else:
            self._lock_fp = Path(tempfile.gettempdir(), 'twitch-archiver', str(self.vod.v_id) + '.lock')

    def __enter__(self):
        """
        Enable 'with' statement functions. Checks if the VOD has already been completed in the requested formats,
        then creates a lock file (if one doesn't already exist).

        :return: self
        """
        # check if VOD has been completed already
        if self._with_database:
            if self.database_vod_completed():
                raise VodAlreadyCompleted(self.vod)

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
            self._log.debug('Failed to remove lock file.')

        if isinstance(exc_val, BaseException):
            self._log.debug('Exception occurred inside DownloadHandler: %s', exc_val)

        else:
            # add VOD to database if exit not due to exception
            if self._with_database:
                self.insert_into_database()

    def get_downloaded_vod(self):
        """
        Retrieves a VOD with a matching stream_id (if any) from the VOD database.

        :return: VOD retrieved from database
        :rtype: ArchivedVod
        """
        with Database(Path(self._config_dir, 'vods.db')) as _db:
            # use list comprehension to avoid issues with attempting to import VOD when none returned
            downloaded_vod = [ArchivedVod.import_from_db(v) for v in _db.execute_query(
                'SELECT vod_id,stream_id,created_at,chat_archived,video_archived FROM vods WHERE stream_id IS ?',
                {'stream_id': self.vod.s_id})]

            if downloaded_vod:
                return downloaded_vod[0]

            return ArchivedVod()

    def database_vod_completed(self):
        """
        Checks if a given VOD is already downloaded in the desired formats according to the database.

        :return: True if VOD exists in the database with matching video and chat archival flags.
        :rtype: bool
        """
        downloaded_vod = self.get_downloaded_vod()
        if downloaded_vod:
            if downloaded_vod.chat_archived == self.vod.chat_archived \
                    and downloaded_vod.video_archived == self.vod.video_archived:
                self._log.debug('VOD already downloaded in requested format according to database.')
                return True

        return False

    def create_lock(self):
        """
        Creates a lock file for a given VOD.

        :return: True on lock creation failure
        :rtype: bool
        """
        try:
            self._lock_file = open(self._lock_fp, 'x')
            return False

        except FileExistsError:
            self._log.debug('Lock file exists for VOD %s.', self.vod)
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
            self._log.debug('Failed to remove lock file for VOD %s. %s', self.vod, exc)
            return exc

    def insert_into_database(self):
        """
        Inserts (or updates) the VOD in the VOD database.
        """
        # check if VOD already in database
        with Database(Path(self._config_dir, 'vods.db')) as _db:
            downloaded_vod = ArchivedVod.import_from_db(_db.execute_query(
                'SELECT vod_id,stream_id,created_at,chat_archived,video_archived FROM vods WHERE stream_id IS ?',
                {'stream_id': self.vod.s_id}))

            # if already present update it
            if downloaded_vod:
                # set flags for updating
                self.vod.chat_archived = self.vod.chat_archived or downloaded_vod.chat_archived
                self.vod.video_archived = self.vod.video_archived or downloaded_vod.video_archived
                _db.execute_query(INSERT_VOD, self.vod.ordered_db_dict())

            else:
                _db.execute_query(INSERT_VOD, self.vod.ordered_db_dict())
