"""
Primary processing loops for calling the various download functions using the supplied user variables.
"""

import logging
import signal
import sys
from concurrent.futures import ThreadPoolExecutor

from pathlib import Path

from twitcharchiver.configuration import Configuration
from twitcharchiver.channel import Channel
from twitcharchiver.downloader import DownloadHandler
from twitcharchiver.downloaders.chat import Chat
from twitcharchiver.downloaders.stream import Stream
from twitcharchiver.downloaders.video import Video
from twitcharchiver.database import Database
from twitcharchiver.exceptions import RequestError, VodDownloadError, VodMergeError, VodLockedError
from twitcharchiver.utils import send_push
from twitcharchiver.vod import Vod, ArchivedVod


class Processing:
    """
    Primary processing loops for downloading content.
    """
    def __init__(self):

        self.log = logging.getLogger()
        conf = Configuration.get()

        self.archive_chat = conf['chat']
        self.archive_video = conf['video']
        self.archive_only = conf['archive_only']
        self.config_dir = conf['config_dir']
        self.live_only = conf['live_only']
        self.pushbullet_key = conf['pushbullet_key']
        self.threads = conf['threads']

        # create signal handler for graceful removal of lock files
        signal.signal(signal.SIGTERM, signal.default_int_handler)

    def get_channel(self, channels):
        """
        Download all vods from a specified channel or list of channels.
        """
        for _channel_name in channels:
            self.log.info("Now archiving channel '%s'.", _channel_name)

            channel = Channel(_channel_name)
            self.log.debug('Channel info: %s', channel)

            # retrieve available vods and extract required info
            channel_videos: list[Vod] = channel.get_channel_videos()

            with Database(Path(self.config_dir, 'vods.db')) as db:
                db.setup()

            channel_live = channel.is_live()
            if channel_live:
                # fetch current stream info
                stream: Stream = Stream(channel)

                # if VOD was missed by the channel video fetcher as the stream was too new we add it to the videos.
                # otherwise we add it to the download queue
                if stream.stream.v_id:
                    if stream.stream.v_id not in [v.v_id for v in channel_videos]:
                        channel_videos.insert(0, Vod(stream.stream.v_id))

                # no paired VOD exists, so we archive the stream before moving onto VODs
                elif self.archive_video and not self.archive_only:
                    with DownloadHandler(ArchivedVod.convert_from_vod(stream.stream, video_archived=True)) as _dh:
                        try:
                            stream.start()

                        except BaseException as e:
                            self.log.error('Error downloading live-only stream by %s. Error: %s', channel.name, e)

            # move on if channel offline and `live-only` set
            elif self.live_only:
                self.log.debug('%s is offline and `live-only` argument provided.', channel.name)
                continue

            self.log.debug('Available VODs: %s', [v.v_id for v in channel_videos])

            # retrieve downloaded vods
            with Database(Path(self.config_dir, 'vods.db')) as db:
                # dict containing stream_id: (vod_id, video_downloaded, chat_downloaded)
                downloaded_vods: list[ArchivedVod] = [ArchivedVod.import_from_db(v) for v in db.execute_query(
                    'SELECT vod_id,stream_id,created_at,chat_archived,video_archived FROM vods '
                    'WHERE user_id IS ?', {'user_id': channel.id})]
            self.log.debug('Downloaded VODs: %s', [v.v_id for v in downloaded_vods])

            # generate vod queue using downloaded and available vods
            download_queue: list[ArchivedVod] = []
            for _vod in channel_videos:
                # insert channel data
                _vod.channel = channel

                # add any vods not already archived
                if _vod not in downloaded_vods:
                    download_queue.append(ArchivedVod.convert_from_vod(_vod))

                # if VOD already downloaded, add it to the queue if formats are missing
                else:
                    # get downloaded VOD from list of downloaded VODs
                    _downloaded_vod = downloaded_vods[[v.v_id for v in downloaded_vods].index(_vod.v_id)]

                    # append to queue with already archived formats flagged as done
                    download_queue.append(ArchivedVod.convert_from_vod(
                        _vod, _downloaded_vod.chat_archived, _downloaded_vod.video_archived))

            # exit if vod queue empty
            if not download_queue:
                self.log.info('No new VODs are available in the requested formats for %s.', channel.name)
                continue

            self.vod_downloader(download_queue)

    def vod_downloader(self, download_queue: list[ArchivedVod]):
        """
        Downloads a given list of VODs according to the settings stored inside the class.

        :param download_queue: List of ArchivedVod objects
        :type download_queue: list(ArchivedVod)
        """
        self.log.info('%s VOD(s) in download queue.', len(download_queue))
        self.log.debug('VOD queue: %s', download_queue)

        _video_download_queue = []
        _chat_download_queue = []
        # begin processing each available vod
        for _vod in download_queue:
            # only check if VOD live if channel is live
            if _vod.channel.is_live():
                if _vod.is_live():
                    # skip if we aren't after currently live streams
                    if self.archive_only:
                        self.log.info('Skipping VOD as it is live and no-stream argument provided.')
                        continue

                else:
                    # skip if we are only after currently live streams, and stream_id is not live
                    if self.live_only:
                        continue

            if not _vod.video_archived and self.archive_video:
                _video_download_queue.append(Video(_vod))

            if not _vod.chat_archived and self.archive_chat:
                _chat_download_queue.append(Chat(_vod))

        for _downloader in _video_download_queue:
            self._start_download(_downloader)

        # create threadpool for chat downloads
        _worker_pool = ThreadPoolExecutor(max_workers=self.threads)
        futures = []
        for _downloader in _chat_download_queue:
            futures.append(_worker_pool.submit(_downloader.start))

        for future in futures:
            if future.result():
                continue

    def _start_download(self, _downloader):
        try:
            with DownloadHandler(_downloader.vod) as _dh:
                _downloader.start()
                _downloader.cleanup_temp_files()

        except VodLockedError:
            return

        # catch user exiting and remove lock file
        except KeyboardInterrupt:
            self.log.info('Termination signal received, halting VOD downloader.')
            sys.exit(0)

        # catch halting errors
        except (RequestError, VodDownloadError, VodMergeError) as e:
            self.log.error('Error downloading VOD %s.', _downloader.vod, exc_info=True)
            send_push(self.pushbullet_key, f'Error downloading VOD {_downloader.vod}.', str(e))
            sys.exit(1)

        # catch unhandled exceptions
        except BaseException as e:
            self.log.error('Error downloading VOD %s.', _downloader.vod, exc_info=True)
            send_push(self.pushbullet_key, f'Error downloading VOD {_downloader.vod}.', str(e))
            sys.exit(1)

    def get_stream_without_archive(self, channel: Channel, stream=None):
        """Archives a live stream without a paired VOD.

        :param channel: channel to fetch stream for
        :param stream: optionally provided stream method if existing buffer needs to be kept
        :return: sanitized / formatted stream json
        """
        if not stream:
            stream = Stream(channel)

        # todo : set store_directory to STREAM_ONLY
        #      : make sure the duration and other parts are updated throughout

        with DownloadHandler(ArchivedVod.convert_from_vod(stream.stream)) as _dh:
            try:
                _dh.create_lock()

                stream.start()

                _dh.remove_lock()

                _dh.insert_into_database()

            except KeyboardInterrupt:
                self.log.info('Termination signal received, halting stream downloader.')
                _dh.remove_lock()
                sys.exit(0)

            except (RequestError, VodMergeError) as e:
                self.log.error('Exception encountered while downloading or merging stream.\n{e}', exc_info=True)
                send_push(self.pushbullet_key,
                          f'Error downloading live-only stream by {stream.channel.name}.', str(e))

            except BaseException as e:
                self.log.error('Exception encountered while downloading or merging stream.\n{e}', exc_info=True)
                send_push(self.pushbullet_key,
                          f'Error downloading live-only stream by {stream.channel.name}.', str(e))

            finally:
                _dh.remove_lock()
