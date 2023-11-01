import multiprocessing
import os
from pathlib import Path

from twitcharchiver.api import Api
from twitcharchiver.exceptions import VodMergeError
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
        workers = [multiprocessing.Process(target=self.stream.start),
                   multiprocessing.Process(target=self.video.start)]

        if self.archive_chat:
            workers.append(multiprocessing.Process(target=self.chat.start))

        for _w in workers:
            _w.start()

        for _w in workers:
            _w.join()

        self.merge()

    def merge(self):
        try:
            self.video.merge()

        except BaseException as e:
            raise VodMergeError(e) from e

    def cleanup_temp_files(self):
        self.chat.cleanup_temp_files()
        self.stream.cleanup_temp_files()
        self.video.cleanup_temp_files()
