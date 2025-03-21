"""
Primary processing loops for calling the various download functions using the supplied user variables.
"""

import logging
import shutil
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from twitcharchiver.channel import Channel
from twitcharchiver.database import Database
from twitcharchiver.downloader import DownloadHandler
from twitcharchiver.downloaders.chat import Chat
from twitcharchiver.downloaders.highlight import Highlight
from twitcharchiver.downloaders.realtime import RealTime
from twitcharchiver.downloaders.stream import Stream
from twitcharchiver.downloaders.video import Video
from twitcharchiver.exceptions import (
    VodLockedError,
    VodAlreadyCompleted,
)
from twitcharchiver.utils import send_push, send_discord_notification
from twitcharchiver.vod import Vod, ArchivedVod

TEMP_BUFFER_LEN = 300


class Processing:
    """
    Primary processing loops for downloading content.
    """

    def __init__(self, conf):
        """
        Class constructor.
        """
        self.log = logging.getLogger()
        self.quiet: bool = conf["quiet"]

        self.archive_chat: bool = conf["chat"]
        self.archive_video: bool = conf["video"]
        self.archive_only: bool = conf["archive_only"]
        self.highlights: bool = conf["highlights"]
        self.live_only: bool = conf["live_only"]
        self.real_time: bool = conf["real_time_archiver"]

        self.config_dir: str = conf["config_dir"]
        # store parent dir for creation of channel subdirectories stored in output_dir
        self._parent_dir: str = conf["directory"]
        self.output_dir: Path = Path(self._parent_dir)

        self.discord_webhook: str = conf["discord_webhook"]
        self.pushbullet_key: str = conf["pushbullet_key"]
        self.quality: str = conf["quality"]
        self.threads: int = conf["threads"]

        # debug flags
        self.force_no_archive: bool = conf["force_no_archive"]

        # perform database setup
        with Database(Path(self.config_dir, "vods.db")) as _db:
            _db.setup()

        # create signal handler for graceful removal of lock files
        signal.signal(signal.SIGTERM, signal.default_int_handler)

    def get_channel(self, channels: list[Channel]):
        """
        Download all vods from a specified channel or list of channels.

        :param channels: list of channels to download based on processing configuration
        """
        for channel in channels:
            self.log.info("Now archiving channel '%s'.", channel.name)
            self.log.debug("Channel info: %s", channel)
            # set output directory to subdir of channel name
            self.output_dir = Path(self._parent_dir, channel.name)

            # retrieve available vods and extract required info
            # only need the most recent VOD if running in live-only mode
            channel_videos: list[Vod] = []
            if self.live_only:
                _latest_video: Vod = channel.get_latest_video()
                if _latest_video:
                    channel_videos.append(_latest_video)
            else:
                channel_videos: list[Vod] = channel.get_channel_archives()
                if self.highlights:
                    channel_videos.extend(channel.get_channel_highlights())

            channel_live = channel.is_live(force_refresh=True)
            if channel_live:
                # fetch current stream info
                stream: Stream = Stream(
                    channel, Vod(), self.output_dir, self.quality, self.quiet, False
                )

                # check for debug force no archive flag
                if self.force_no_archive:
                    stream.vod = ArchivedVod.convert_from_vod(stream.vod)
                    self._start_download(stream)
                    continue

                # if stream length is less than TEMP_BUFFER_LEN, archive in stream-only mode for the time being
                # while we wait for twitch's VOD api to update
                if not stream.vod.v_id and stream.vod.duration < TEMP_BUFFER_LEN:
                    self.log.info(
                        "Stream began very recently, buffering initial segments until API updates."
                    )
                    with DownloadHandler(
                        ArchivedVod.convert_from_vod(stream.vod)
                    ) as _dh:
                        # we're not setting either the video_archived or chat_archived flags here because we may want
                        # to archive them from the VOD (if it becomes available). The stream info will be placed into
                        # the database once the buffer is saved
                        stream.archive_for_duration(TEMP_BUFFER_LEN)

                        # stream ended before buffer time reached
                        if stream.has_ended:
                            stream.export_metadata()
                            stream.merge()
                            stream.cleanup_temp_files()

                # don't bother with further checks if stream archive completed
                if not stream.has_ended:
                    # TEMP_BUFFER_LEN has passed, check if stream has paired VOD now...
                    stream.match_to_channel_vod()

                    # if VOD was missed by the channel video fetcher as the stream was too new we add it to the videos.
                    # otherwise we add it to the download queue
                    if stream.vod.v_id:
                        self.log.debug("Current stream has a paired VOD.")

                        # remove downloaded files (if any)
                        stream.cleanup_temp_files()
                        shutil.rmtree(Path(stream.output_dir), ignore_errors=True)

                        if stream.vod.v_id not in [v.v_id for v in channel_videos]:
                            channel_videos.insert(0, Vod(stream.vod.v_id))

                    # no paired VOD exists, so we archive the stream before moving onto VODs
                    elif self.archive_video and not self.archive_only:
                        self.log.debug(
                            "Current stream has no paired VOD - beginning stream downloader."
                        )
                        stream.vod = ArchivedVod.convert_from_vod(stream.vod)
                        self._start_download(stream)

            # move on if channel offline and `live-only` set
            elif self.live_only:
                self.log.info(
                    "%s is offline and `live-only` argument provided.", channel.name
                )
                continue

            self.log.debug(
                "Available VODs: %s",
                [v.v_id for v in channel_videos] if channel_videos else "None",
            )

            # retrieve downloaded vods
            with Database(Path(self.config_dir, "vods.db")) as _db:
                # dict containing stream_id: (vod_id, video_downloaded, chat_downloaded)
                downloaded_vods: list[ArchivedVod] = [
                    ArchivedVod.import_from_db(v)
                    for v in _db.execute_query(
                        "SELECT vod_id,stream_id,created_at,chat_archived,video_archived FROM vods "
                        "WHERE user_id IS ?",
                        {"user_id": channel.id},
                    )
                ]
            self.log.debug("Downloaded VODs: %s", len(downloaded_vods))

            # generate vod queue using downloaded and available vods
            download_queue: list[ArchivedVod] = []
            for _vod in channel_videos:
                self.log.debug("Processing VOD %s.", _vod.v_id)
                # insert channel data
                _vod.channel = channel

                # add any vods not already archived
                if _vod.v_id not in [v.v_id for v in downloaded_vods]:
                    self.log.debug("VOD added to download queue.")
                    download_queue.append(ArchivedVod.convert_from_vod(_vod))

                # if VOD already downloaded, add it to the queue if formats are missing
                else:
                    # get downloaded VOD from list of downloaded VODs
                    _downloaded_vod = downloaded_vods[
                        [v.v_id for v in downloaded_vods].index(_vod.v_id)
                    ]

                    # check if any requested format is missing
                    if (
                        not _downloaded_vod.chat_archived
                        and self.archive_chat
                        or not _downloaded_vod.video_archived
                        and self.archive_video
                    ):
                        self.log.debug(
                            "VOD already archived but requested format(s) missing - adding them to download queue."
                        )
                        download_queue.append(
                            ArchivedVod.convert_from_vod(
                                _vod,
                                _downloaded_vod.chat_archived,
                                _downloaded_vod.video_archived,
                            )
                        )

            # exit if vod queue empty
            if not download_queue:
                self.log.info(
                    "No new VODs are available in the requested formats for %s.",
                    channel.name,
                )

            else:
                self.vod_downloader(download_queue)

    def vod_downloader(self, download_queue: list[ArchivedVod]):
        """
        Downloads a given list of VODs according to the settings stored inside the class.

        :param download_queue: list of ArchivedVod objects
        """
        self.log.info("%s VOD(s) in download queue.", len(download_queue))
        self.log.debug("VOD queue: %s", [v.v_id for v in download_queue])

        _video_download_queue: list = []
        _chat_download_queue: list = []

        # cache channels with associated broadcast VOD IDs
        _channel_cache: list[Channel] = []

        # begin processing each available vod
        for _vod in download_queue:
            self.log.debug("Processing VOD %s from download queue.", _vod.v_id)

            if _vod.channel not in _channel_cache:
                self.log.debug(
                    "Channel '%s' missing from cache - adding now.", _vod.channel
                )
                _channel_cache.append(_vod.channel)

            if self.live_only and not _vod.is_live():
                self.log.debug("Skipping as VOD is offline and `live-only` flag set.")
                continue

            _channel_index = _channel_cache.index(_vod.channel)
            # if channel is live
            if _channel_cache[_channel_index].is_live():
                # check if current VOD ID matches associated broadcast VOD ID
                if _channel_cache[_channel_index].get_broadcast_v_id() == _vod.v_id:
                    # skip if we aren't after currently live streams
                    if self.archive_only:
                        self.log.info(
                            "Skipping VOD as it is live and no-stream argument provided."
                        )
                        continue

                    # run real-time archiver if enabled and current stream is being archived to this VOD
                    if self.real_time:
                        self.log.debug("Archiving VOD with `real-time` archiver.")
                        _real_time_archiver = RealTime(
                            _vod,
                            self.output_dir,
                            self.archive_chat,
                            self.quality,
                            self.threads,
                        )
                        self._start_download(_real_time_archiver)
                        continue

            if not _vod.video_archived and self.archive_video:
                self.log.debug("Adding VOD to video archive queue.")
                if _vod.type == "HIGHLIGHT":
                    _video_download_queue.append(
                        Highlight(
                            _vod,
                            self.output_dir,
                            self.quality,
                            self.threads,
                            self.quiet,
                        )
                    )

                else:
                    _video_download_queue.append(
                        Video(
                            _vod,
                            self.output_dir,
                            self.quality,
                            self.threads,
                            self.quiet,
                        )
                    )

            if not _vod.chat_archived and self.archive_chat:
                self.log.debug("Adding VOD to chat archive queue.")
                _chat_download_queue.append(Chat(_vod, self.output_dir, self.quiet))

        for _downloader in _video_download_queue:
            self._start_download(_downloader)

        if _chat_download_queue:
            _worker_pool = ThreadPoolExecutor(max_workers=self.threads)
            try:
                self.log.debug(
                    "Beginning bulk chat archival with %s threads.", self.threads
                )
                # create threadpool for chat downloads
                futures = []
                for _downloader in _chat_download_queue:
                    futures.append(
                        _worker_pool.submit(self._start_download, _downloader)
                    )

                for future in futures:
                    if future.exception():
                        self.log.debug(
                            "Exception occurred in chat download pool: %s",
                            future.exception(),
                        )

            except KeyboardInterrupt:
                self.log.debug(
                    "Chat downloader caught interrupt, shutting down workers..."
                )
                _worker_pool.shutdown(wait=False, cancel_futures=True)
                sys.exit(0)

            finally:
                _worker_pool.shutdown(wait=False, cancel_futures=True)

    def _start_download(self, _downloader):
        try:
            with DownloadHandler(_downloader.vod) as _dh:
                self.log.debug("Beginning download of VOD %s.", _downloader.vod.v_id)
                _downloader.start()
                _downloader.export_metadata()
                _downloader.merge()
                _downloader.cleanup_temp_files()

        except VodAlreadyCompleted:
            return

        except VodLockedError:
            return

        # catch user exiting and remove lock file
        except KeyboardInterrupt:
            self.log.info("Termination signal received, halting VOD downloader.")
            sys.exit(0)

        # catch unhandled exceptions
        except BaseException as exc:
            self.log.error("Error archiving VOD %s.", _downloader.vod, exc_info=True)
            if self.discord_webhook:
                send_discord_notification(
                    self.discord_webhook,
                    f'Error downloading VOD "{_downloader.vod.v_id or _downloader.vod.s_id}"'
                    f" by {_downloader.vod.channel.name}. {str(exc)}",
                )

            if self.pushbullet_key:
                send_push(
                    self.pushbullet_key,
                    f'Error downloading VOD "{_downloader.vod.v_id or _downloader.vod.s_id}"'
                    f" by {_downloader.vod.channel.name}.",
                    str(exc),
                )
            sys.exit(1)
