import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from twitcharchiver import Configuration
from twitcharchiver.api import Api
from twitcharchiver.exceptions import VodMergeError
from twitcharchiver.logger import ProcessWithLogging, ProcessLogger
from twitcharchiver.vod import Vod
from twitcharchiver.downloader import Downloader
from twitcharchiver.downloaders.chat import Chat
from twitcharchiver.downloaders.stream import Stream
from twitcharchiver.downloaders.video import Video

class RealTime(Downloader):
    """
    Class used for downloading currently live broadcasts, using parallel download functions to grab both the stream
    and VOD video and chat.
    """
    # class vars
    _api: Api = Api()
    _quality: str = ''

    def __init__(self, vod: Vod, parent_dir: Path = os.getcwd(), archive_chat: bool = True, quality: str = 'best',
                 threads: int = 20):
        """
        Class constructor.

        :param vod: VOD to be downloaded
        :type vod: Vod
        :param parent_dir: path to parent directory for downloaded files
        :type parent_dir: str
        :param archive_chat: boolean whether the chat logs should also be grabbed
        :type archive_chat: bool
        :param quality: quality to download in the format [resolution]p[framerate], or either 'best' or 'worst'
        :type quality: str
        :param threads: number of worker threads to use when downloading
        :type threads: int
        """
        super().__init__(parent_dir, True)

        self.vod = vod

        self.archive_chat = archive_chat

        self.chat = Chat(vod, parent_dir, True)
        self.stream = Stream(vod.channel, vod, parent_dir, quality, True)
        self.video = Video(vod, parent_dir, quality, threads, True)

    def start(self):
        """
        Starts downloading VOD video / chat segments.
        """
        # log files are stored in either the provided log directory or %TEMP%/STREAM_ID
        # we change to this directory as the multiprocessing logger has difficulties with passing
        # variables into it
        logging_dir = Path(tempfile.gettempdir(), str(self.vod.s_id))
        conf = Configuration.get()
        if conf['log_dir']:
            logging_dir = Path(conf['log_dir'])

        Path(logging_dir).mkdir(exist_ok=True, parents=True)
        os.chdir(logging_dir)

        process_logger = ProcessLogger.create_global_logger()
        process_logger.start()

        _worker_pool = ThreadPoolExecutor(max_workers=3)
        try:
            workers = [ProcessWithLogging(self.stream.start),
                       ProcessWithLogging(self.video.start)]

            if self.archive_chat:
                workers.append(ProcessWithLogging(self.chat.start))

            for _w in workers:
                _w.start()

            for _w in workers:
                _w.join()

            process_logger.stop()
            process_logger.join()

        except KeyboardInterrupt:
            self._log.info('User requested stop, shutting down workers...')
            _worker_pool.shutdown(wait=False)
            process_logger.stop()
            process_logger.join()
            raise KeyboardInterrupt

        finally:
            _worker_pool.shutdown(wait=False)

    def merge(self):
        try:
            self.video.merge()

        except BaseException as e:
            raise VodMergeError(e) from e

    def cleanup_temp_files(self):
        self.chat.cleanup_temp_files()
        self.stream.cleanup_temp_files()
        self.video.cleanup_temp_files()
