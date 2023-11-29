import multiprocessing
import os
import tempfile
from multiprocessing import Queue
from pathlib import Path

from twitcharchiver import Configuration
from twitcharchiver.api import Api
from twitcharchiver.exceptions import VodMergeError
from twitcharchiver.logger import ProcessWithLogging, ProcessLogger
from twitcharchiver.vod import Vod, ArchivedVod
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
        self.parent_dir = parent_dir
        self.archive_chat = archive_chat
        self.quality = quality
        self.threads = threads

        self.chat = None
        self.stream = None
        self.video = None

    def start(self):
        # log files are stored in either the provided log directory or %TEMP%/STREAM_ID
        # we change to this directory as the multiprocessing logger has difficulties with passing
        # variables into it
        logging_dir = Path(tempfile.gettempdir(), str(self.vod.s_id))
        conf = Configuration.get()
        if conf['log_dir']:
            logging_dir = Path(conf['log_dir'])

        _q = Queue()

        # create downloaders
        self.chat = Chat(self.vod, self.parent_dir, True)
        self.stream = Stream(self.vod.channel, self.vod, self.parent_dir, self.quality, True)
        self.video = Video(self.vod, self.parent_dir, self.quality, self.threads, True)

        process_logger = None

        Path(logging_dir).mkdir(exist_ok=True, parents=True)
        # use different logging method on Windows systems
        if os.name == 'nt':
            # logging directory is used and moved into as Windows doesn't properly share the global logger, so it is
            # reconfigured using a relative path as it is much easier than passing a designated file to the
            # processlogger instance.
            os.chdir(logging_dir)

            process_logger = ProcessLogger.create_global_logger()
            process_logger.start()

            workers = [ProcessWithLogging(self.stream.start),
                       ProcessWithLogging(self.video.start, [_q])]

            if self.archive_chat:
                workers.append(ProcessWithLogging(self.chat.start))

        else:
            workers = [multiprocessing.Process(target=self.stream.start),
                       multiprocessing.Process(target=self.video.start, args=[_q])]

            if self.archive_chat:
                workers.append(multiprocessing.Process(target=self.chat.start))

        try:
            for _w in workers:
                _w.start()

            # get returned video downloader
            self.video: Video = _q.get()

            for _w in workers:
                _w.join()

            # set archival flag if ArchivedVod provided
            if isinstance(self.vod, ArchivedVod):
                self.vod.video_archived = True
                if self.archive_chat:
                    self.vod.chat_archived = True

        finally:
            _q.close()
            _q.join_thread()

            if process_logger:
                process_logger.stop()
                process_logger.join()

    def merge(self):
        try:
            self.video.merge()

        except Exception as exc:
            raise VodMergeError('Exception raised while merging VOD.') from exc

    def cleanup_temp_files(self):
        self.chat.cleanup_temp_files()
        self.stream.cleanup_temp_files()
        self.video.cleanup_temp_files()
