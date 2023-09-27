import logging
import os
from pathlib import Path
from tempfile import tempdir

from twitcharchiver.api import Api


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
    Handles locking, unlocking and database insert for VOD archiving.
    """

    def __init__(self, vod):
        self.vod = vod
        _lf_path = Path(tempdir, str(vod.s_id), '.lock')
        self.lock_file = open(_lf_path, 'rw')

    def __enter__(self):
        # create lock file
        # todo fill this out
        return DownloadHandler()

    def __exit__(self, exc_type, exc_val, exc_tb):
        # remove lock file
        # todo fill this out
        # add to database
        return DownloadHandler()
