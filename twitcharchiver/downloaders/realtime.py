import os
from multiprocessing import Queue
from pathlib import Path
from time import sleep

from twitcharchiver import Configuration
from twitcharchiver.api import Api
from twitcharchiver.downloader import Downloader
from twitcharchiver.downloaders.chat import Chat
from twitcharchiver.downloaders.stream import Stream
from twitcharchiver.downloaders.video import Video
from twitcharchiver.logger import ProcessWithLogging, ProcessLogger
from twitcharchiver.utils import get_temp_dir
from twitcharchiver.vod import Vod, ArchivedVod


class RealTime(Downloader):
    """
    Class used for downloading currently live broadcasts, using parallel download functions to grab both the stream
    and VOD video and chat.
    """

    # class vars
    _api: Api = Api()
    _quality: str = ""

    def __init__(
        self,
        vod: Vod,
        parent_dir: Path = os.getcwd(),
        archive_chat: bool = True,
        quality: str = "best",
        threads: int = 20,
    ):
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
        logging_dir = Path(get_temp_dir(), str(self.vod.s_id))
        conf = Configuration.get()
        if conf["log_dir"]:
            logging_dir = Path(conf["log_dir"])

        _q = Queue()

        # create downloaders
        self.chat = Chat(self.vod, self.parent_dir, True)
        self.stream = Stream(
            self.vod.channel, self.vod, self.parent_dir, self.quality, True
        )
        self.video = Video(self.vod, self.parent_dir, self.quality, self.threads, True)

        Path(logging_dir).mkdir(exist_ok=True, parents=True)
        # logging directory is used and moved into as Windows doesn't properly share the global logger, so it is
        # reconfigured using a relative path as it is much easier than passing a designated file to the
        # processlogger instance.
        os.chdir(logging_dir)

        process_logger = ProcessLogger.create_global_logger()
        process_logger.start()

        workers = [
            ProcessWithLogging(target=self.stream.start),
            ProcessWithLogging(target=self.video.start, args=[_q]),
        ]

        if self.archive_chat:
            workers.append(ProcessWithLogging(target=self.chat.start))

        try:
            for _w in workers:
                _w.start()

            # get returned video downloader
            self.video: Video = _q.get()

            # wait until all workers are done
            for _w in workers:
                _w.join()

        finally:
            sleep(1)
            # kill any still running workers
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    self._log.error(
                        f"Worker %s failed to exit and was terminated.", worker
                    )

            self._handle_errors(workers)

            _q.close()
            _q.join_thread()

            if process_logger:
                process_logger.stop()
                process_logger.join()

    def _handle_errors(self, workers):
        errors = []

        # discover errors based on exit codes of archivers
        # [0] is stream worker
        if workers[0].exitcode == 1:
            self._log.error("Real-time stream archiver exited with error.")
            errors.append(Stream)

        # [1] is video worker
        if workers[1].exitcode == 1:
            self._log.error("Real-time video archiver exited with error.")
            errors.append(Video)

        # [2] is chat worker
        if len(workers) > 2:
            if workers[2].exitcode == 1:
                self._log.error("Real-time chat archiver exited with error.")
                errors.append(Chat)

        # handle various error cases. stream archiver failing is recoverable as long as video archiver finishes
        # successfully.
        if Video in errors:
            self._log.error(
                "Real-time archiver failed as video archiver exited with error. "
                "See log for details."
            )
        else:
            if isinstance(self.vod, ArchivedVod):
                self.vod.video_archived = True

        if Chat in errors:
            self._log.error(
                "Real-time archiver failed as chat archiver exited with error. "
                "See log for details."
            )
        else:
            if self.archive_chat and isinstance(self.vod, ArchivedVod):
                self.vod.chat_archived = True

    def export_metadata(self):
        self.video.export_metadata()

    def merge(self):
        self.video.merge()

    def cleanup_temp_files(self):
        self.chat.cleanup_temp_files()
        self.stream.cleanup_temp_files()
        self.video.cleanup_temp_files()
