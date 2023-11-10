import logging
import tempfile

from pathlib import Path

from twitcharchiver.configuration import Configuration
from twitcharchiver.exceptions import VodAlreadyCompleted, VodLockedError
from twitcharchiver.database import Database, INSERT_VOD
from twitcharchiver.vod import ArchivedVod, Vod


class Downloader:
    _log = logging.getLogger()
    def __init__(self, parent_dir: Path, quiet: bool):
        """
        Class Constructor.

        :param parent_dir: path to output downloaded VOD(s) to
        :type parent_dir: Path
        """
        self._parent_dir: Path = parent_dir
        self._quiet: bool = quiet

        self.vod = Vod()

    def start(self):
        return

    def merge(self):
        return

    def cleanup_temp_files(self):
        return


class DownloadHandler:
    """
    Handles file locking and database insertion for VOD archiving.
    """

    def __init__(self, vod: ArchivedVod):
        """
        Class constructor.

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
        # check if VOD has been completed already
        if self._with_database:
            if self.database_vod_completed():
                raise VodAlreadyCompleted(self.vod)

        # attempt to create lock file
        if self.create_lock():
            raise VodLockedError(self.vod)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
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
        with Database(Path(self._config_dir, 'vods.db')) as db:
            # use list comprehension to avoid issues with attempting to import VOD when none returned
            downloaded_vod = [ArchivedVod.import_from_db(v) for v in db.execute_query(
                'SELECT vod_id,stream_id,created_at,chat_archived,video_archived FROM vods WHERE stream_id IS ?',
                {'stream_id': self.vod.s_id})]

            if downloaded_vod:
                return downloaded_vod[0]

            return ArchivedVod()

    def database_vod_completed(self):
        """
        Checks if a given VOD is already downloaded in the desired formats according to the database.
        """
        downloaded_vod = self.get_downloaded_vod()
        if downloaded_vod:
            if downloaded_vod.chat_archived == self.vod.chat_archived \
                    and downloaded_vod.video_archived == self.vod.video_archived:
                self._log.debug('VOD already downloaded in requested format according to database.')
                return True

        return False

    def create_lock(self):
        """Creates a lock file for a given VOD.

        :raises FileExistsError:
        """
        try:
            self._lock_file = open(self._lock_fp, 'x')

        except FileExistsError:
            self._log.debug('Lock file exists for VOD %s.', self.vod)
            return 1

    def remove_lock(self):
        """Removes a given lock file.

        :return: boolean for success
        """
        try:
            self._lock_file.close()
            self._lock_fp.unlink()

        except BaseException as e:
            self._log.debug('Failed to remove lock file for VOD %s. %s', self.vod, e)
            return e

    def insert_into_database(self):
        # check if VOD already in database
        with Database(Path(self._config_dir, 'vods.db')) as db:
            downloaded_vod = ArchivedVod.import_from_db(db.execute_query(
                'SELECT vod_id,stream_id,created_at,chat_archived,video_archived FROM vods WHERE stream_id IS ?',
                {'stream_id': self.vod.s_id}))

            # set appropriate chat and video flags
            self.vod.chat_archived = self.vod.chat_archived
            self.vod.video_archived = self.vod.video_archived

            # if already present update it
            if downloaded_vod:
                # set flags for updating
                self.vod.chat_archived = self.vod.chat_archived or downloaded_vod.chat_archived
                self.vod.video_archived = self.vod.video_archived or downloaded_vod.video_archived
                db.execute_query(INSERT_VOD, self.vod.ordered_db_dict())

            else:
                db.execute_query(INSERT_VOD, self.vod.ordered_db_dict())
