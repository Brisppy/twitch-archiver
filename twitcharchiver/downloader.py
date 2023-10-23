import logging
import tempfile

from pathlib import Path

from twitcharchiver.configuration import Configuration
from twitcharchiver.exceptions import VodAlreadyCompleted, VodLockedError
from twitcharchiver.database import Database, UPDATE_VOD, CREATE_VOD
from twitcharchiver.vod import ArchivedVod


class Downloader:
    # class vars
    _log = logging.getLogger()
    _quiet: bool = False
    _parent_dir: Path = Path()

    def __init__(self, parent_dir: Path, quiet: bool):
        """
        Class Constructor.

        :param parent_dir: path to output downloaded VOD(s) to
        :type parent_dir: Path
        """
        self.__setattr__('_parent_dir', parent_dir)
        self.__setattr__('_quiet', quiet)


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

        # build path to lock file based on if stream has an archive or not
        if self.vod.v_id == 0:
            self._lf_path = Path(tempfile.gettempdir(), str(self.vod.s_id), '.lock-stream-only')

        else:
            self._lf_path = Path(tempfile.gettempdir(), str(self.vod.s_id), '.lock')

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
        # add VOD to database
        if self._with_database:
            self.insert_into_database()

        # attempt to delete lock file
        if self.remove_lock():
            pass

        if isinstance(exc_val, Exception):
            self._log.debug('Exception occurred inside DownloadHandler: %s', exc_val)

    def get_downloaded_vod(self):
        with Database(Path(self._config_dir, 'vods.db')) as db:
            downloaded_vod = ArchivedVod.import_from_db(db.execute_query(
                'SELECT vod_id,stream_id,created_at,chat_archived,video_archived FROM vods WHERE stream_id IS ?',
                {'stream_id': self.vod.s_id}))

        if downloaded_vod:
            return downloaded_vod

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
            self._lock_file = open(self._lf_path, 'x')

        except FileExistsError:
            self._log.debug('Lock file exists for VOD %s.', self.vod)
            return 1

    def remove_lock(self):
        """Removes a given lock file.

        :return: boolean for success
        """
        try:
            self._lock_file.close()

        except BaseException as e:
            self._log.debug('Failed to remove lock file for VOD %s. %s', self.vod, e)
            return 1

    def insert_into_database(self):
        # check if VOD already in database
        with Database(Path(self._config_dir, 'vods.db')) as db:
            downloaded_vod = ArchivedVod.import_from_db(db.execute_query(
                'SELECT vod_id,stream_id,created_at,chat_archived,video_archived FROM vods WHERE stream_id IS ?',
                {'stream_id': self.vod.s_id}))

            # set appropriate chat and video flags
            self.vod.chat_archived = self.vod.chat_archived or downloaded_vod.chat_archived
            self.vod.video_archived = self.vod.video_archived or downloaded_vod.video_archived

            # if already present update it
            if downloaded_vod:
                db.execute_query(UPDATE_VOD, self.vod)

            else:
                db.execute_query(CREATE_VOD, self.vod)
