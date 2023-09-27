"""
Primary processing loops for calling the various download functions using the supplied user variables.
"""

import logging
import multiprocessing
import signal
import sys
import tempfile

from datetime import datetime, timezone
from pathlib import Path

from twitcharchiver.api import Api
from twitcharchiver.channel import Channel
from twitcharchiver.downloader import DownloadHandler
from twitcharchiver.downloaders.chat import Chat
from twitcharchiver.downloaders.stream import Stream
from twitcharchiver.database import Database
from twitcharchiver.downloaders.video import Video
from twitcharchiver.exceptions import UnlockingError, RequestError, ChatDownloadError, VodDownloadError, VodMergeError, ChatExportError
from twitcharchiver.utils import time_since_date, sanitize_date, sanitize_text, remove_lock, send_push
from twitcharchiver.vod import Vod


class ArchivedVod(Vod):
    """
    Defines an archive of a VOD. Used for tracking the status of previously archived VODs.
    """
    def __init__(self, vod: Vod, chat_archived: bool = False, video_archived: bool = False):
        super().__init__()
        self._from_vod(vod)
        self.chat_archived: bool = chat_archived
        self.video_archived: bool = video_archived

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.v_id == other.v_id and self.chat_archived == other.chat_archived and self.video_archived == other.video_archived
        return False

    @staticmethod
    def import_from_db(*args):
        """
        Creates a new ArchivedVod with values from the provided database return. We can't fetch this from Twitch as
        they delete the records when the VOD expires or is manually deleted.
        """
        _archived_vod = ArchivedVod(args[4], args[5])
        _archived_vod.v_id = args[0]
        _archived_vod.s_id = args[1]
        _archived_vod.channel = args[2]
        _archived_vod.created_at = args[3]

        return _archived_vod

    def _from_vod(self, vod: Vod):
        """
        Converts an existing VOD into an ArchivedVod.

        :param vod: VOD to create ArchivedVod of
        :type vod: Vod
        """
        for key, value in vars(vod).items():
            setattr(self, key, value)


class Processing:
    """
    Primary processing loops for downloading content.
    """
    def __init__(self, config, args):

        self.log = logging.getLogger()
        self.config = config
        self.args = args

        self.archive_video = args['video']
        self.archive_chat = args['chat']

        self.output_directory = args['output_dir']

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

            with Database(self.args['config_dir']) as db:
                db.setup()

            channel_live = channel.is_live()
            if channel_live:
                # fetch current stream info
                stream: Stream = Stream(channel)

                # if VOD was missed by the chanel video fetcher as the stream was too new we add it to the videos.
                # otherwise we add it to the download queue
                if stream.stream.v_id:
                    if stream.stream.v_id not in [v.v_id for v in channel_videos]:
                        channel_videos.insert(0, Vod(stream.stream.v_id))

                # no paired VOD exists so we archive the entire stream before moving onto VODs
                elif self.archive_video and not self.args['archive-only']:
                    with DownloadHandler as _h:
                        stream.download()

            # move on if channel offline and `live-only` set
            elif self.args['live-only']:
                self.log.debug('%s is offline and `live-only` argument provided.', channel.name)
                continue

            self.log.debug('Available VODs: %s', channel_videos)

            # retrieve downloaded vods
            with Database(Path(self.config.get('config_dir'), 'vods.db')) as db:
                # dict containing stream_id: (vod_id, video_downloaded, chat_downloaded)
                downloaded_vods: list[ArchivedVod] = [ArchivedVod.import_from_db(v) for v in db.execute_query(
                    'SELECT vod_id,stream_id,user_name,created_at,video_archived,chat_archived FROM vods'
                    'WHERE user_id IS ?', {'user_id': channel.id})]
            self.log.debug('Downloaded vods: %s', downloaded_vods)

            # generate vod queue using downloaded and available vods
            download_queue: list[ArchivedVod] = []
            for _vod in channel_videos:
                # add any vods not already archived
                if _vod not in downloaded_vods:
                    download_queue.append(ArchivedVod(_vod))

                # if VOD already downloaded, add it to the queue if formats are missing
                else:
                    # get downloaded VOD from list of downloaded VODs
                    _downloaded_vod = downloaded_vods[[v.v_id for v in downloaded_vods].index(_vod.v_id)]
                    if not _downloaded_vod.chat_archived and self.args['archive_chat']:
                        download_queue.append(_downloaded_vod)

                    elif not _downloaded_vod.video_archived and self.args['archive_video']:
                        download_queue.append(_downloaded_vod)

            #
            # build a queue of VODs
            # iterate through the vods and adding desired chat and video instances to queue
            # queue is assigned n number of threads and is passed to vod and chat downloaders
            # all at once run entire downloader queue
            # wrapper for this needs to handle locking / unlocking as well as DB insertions

            # exit if vod queue empty
            if not download_queue:
                self.log.info('No new VODs are available in the requested formats for %s.', channel.name)
                continue

            self.log.info('%s VOD(s) in download queue.', len(download_queue))
            self.log.debug('VOD queue: %s', download_queue)

            video_download_queue = []
            chat_download_queue = []
            # begin processing each available vod
            for _vod in download_queue:
                if _vod.is_live():
                    # skip if we aren't after currently live streams
                    if self.args['archive_only']:
                        self.log.info('Skipping VOD as it is live and no-stream argument provided.')
                        continue

                else:
                    # skip if we are only after currently live streams, and stream_id is not live
                    if self.args['live-only']:
                        continue

                if not _vod.video_archived and self.args['archive_video']:
                    video_download_queue.append(_vod)

                if not _vod.chat_archived and self.args['archive_chat']:
                    chat_download_queue.append(_vod)

            for _vod in video_download_queue:
                with DownloadHandler as _dh:


                # self.log.debug('Processing VOD %s by %s', _vod.v_id, channel.name)
                # self.log.debug('Creating lock file for VOD.')
                #
                # if create_lock(Path(tempfile.gettempdir(), 'twitch-archiver'), stream_id):
                #     self.log.info('Lock file present for VOD %s (.lock.%s), skipping.', vod_id, stream_id)
                #     continue
                #
                # # check if vod in database
                # with Database(Path(self.config_dir, 'vods.db')) as db:
                #     downloaded_vod = db.execute_query(
                #         'SELECT vod_id, video_archived, chat_archived FROM vods WHERE stream_id IS ?',
                #         {'stream_id': stream_id})
                #
                # # check if vod_id exists in database in the requested format(s)
                # if downloaded_vod and download_queue[stream_id][1] and downloaded_vod[0][1] \
                #         and download_queue[stream_id][2] and downloaded_vod[0][2]:
                #     self.log.info('VOD has been downloaded in requested format since download queue was created.')
                #     continue

                # vod_json = self.get_vod_connector(vod_id, download_queue[stream_id][1], download_queue[stream_id][2])
                #
                # if vod_json:
                #     # insert video, chat archival flags
                #     vod_json['video_archived'] = download_queue[stream_id][1]
                #     if 'chat_archived' not in vod_json.keys():
                #         vod_json['chat_archived'] = download_queue[stream_id][2]
                #     # null empty values
                #     for key in vod_json.keys():
                #         if isinstance(vod_json[key], str) and vod_json[key] == "":
                #             vod_json[key] = None
                #
                #     try:
                #         # add to database
                #         self.log.debug('Adding VOD info to database.')
                #         with Database(Path(self.config_dir, 'vods.db')) as db:
                #             # check if stream already exists and update if so
                #             db_vod = db.execute_query(
                #                 'SELECT stream_id, video_archived, chat_archived FROM vods WHERE stream_id IS ?',
                #                 {'stream_id': vod_json['stream_id']})
                #             if db_vod:
                #                 # update archived flags using previous and current processing flags
                #                 vod_json['video_archived'] = db_vod[0][1] or vod_json['video_archived']
                #                 vod_json['chat_archived'] = db_vod[0][2] or vod_json['chat_archived']
                #                 vod_json['sid'] = vod_json['stream_id']
                #                 db.execute_query(UPDATE_VOD, vod_json)
                #
                #             else:
                #                 db.execute_query(CREATE_VOD, vod_json)
                #
                #     finally:
                #         # remove lock
                #         self.log.debug('Removing lock file.')
                #         if remove_lock(Path(tempfile.gettempdir(), 'twitch-archiver'), vod_json['stream_id']):
                #             raise UnlockingError(vod_json['user_name'], vod_json['stream_id'], vod_id)
                #
                # else:
                #     self.log.debug('No VOD information returned to channel function, downloader exited with error.')
                #     continue

    def download_handler(self, downloader: Video):
        """
        Handles locking and unlocking of VODs along with database insertion.

        :param downloader:
        :return:
        """

    def get_vod_connector(self, vod_id, get_video, get_chat):
        """Download a single vod or list of vod IDs.

        :param vod_id: vod id to download
        :param get_video: bool whether to grab video
        :param get_chat: bool whether to grab chat logs
        :return: dict containing current vod information returned by get_vod
        """
        self.log.info('Now processing VOD: %s', vod_id)
        vod_json = self.twitch.get_vod_metadata(vod_id)
        vod_json['store_directory'] = \
            str(Path(self.vod_directory, f'{sanitize_date(vod_json["created_at"])} - '
                                         f'{sanitize_text(vod_json["title"])} - {vod_id}'))

        workers = []

        # get vod status
        vod_live = self.twitch.get_vod_status(vod_json['user_name'], vod_json['created_at'])

        self.log.info("VOD %s", 'currently or recently live. Running in LIVE mode.' if vod_live else 'offline.')

        _r = None

        try:
            # begin real-time archiver if VOD still live and real-time archiver enabled
            if self.real_time_archiver and vod_live:
                stream = Stream()
                # concurrently grab live pieces and vod chunks

                # the stream module itself has no checks for what to download so this is done here
                if get_video:
                    workers.append(multiprocessing.Process(target=stream.get_stream, args=(
                        vod_json['user_name'], Path(vod_json['store_directory'], 'parts'), self.quality)))

                workers.append(multiprocessing.Process(target=self.get_vod, args=(
                    vod_json, get_video, get_chat, vod_live)))

                for worker in workers:
                    worker.start()

                for worker in workers:
                    worker.join()

            else:
                self.get_vod(vod_json, get_video, get_chat, vod_live)

            # if get_video:
            #     # grab thumbnail at 1080p resolution - any resolution can be used but this should be fine for almost
            #     # every stream
            #     try:
            #         self.log.debug('Downloading VOD thumbnail.')
            #         thumbnail = Api.get_request(vod_json['thumbnail_url'].replace('%{width}x%{height}', '1920x1080'))
            #         with open(Path(vod_json['store_directory'], 'thumbnail.jpg'), 'wb') as thumbnail_file:
            #             thumbnail_file.write(thumbnail.content)
            #
            #     except BaseException as e:
            #         self.log.error('Failed to grab thumbnail for VOD. Error: %s', str(e))
            #
            #     # delete temporary .ts parts and merged.ts file
            #     self.log.debug('Cleaning up temporary files...')
            #     cleanup_vod_parts(vod_json['store_directory'])

        # catch user exiting and remove lock file
        except KeyboardInterrupt:
            if vod_live:
                self.log.debug('Termination signal received, terminating download workers...')
                for worker in workers:
                    worker.terminate()
                    worker.join()

            if remove_lock(Path(tempfile.gettempdir(), 'twitch-archiver'), vod_json['stream_id']):
                raise UnlockingError(vod_json['user_name'], vod_json['stream_id'], vod_id)

            sys.exit(0)

        # catch halting errors, send notification and remove lock file
        except (RequestError, VodDownloadError, ChatDownloadError, VodMergeError, ChatExportError) as e:
            if vod_live:
                self.log.debug('Exception encountered, terminating download workers...')
                for worker in workers:
                    worker.terminate()
                    worker.join()

            self.log.error('Error downloading VOD %s.', vod_id, exc_info=True)
            send_push(self.pushbullet_key, f'Error downloading VOD {vod_id} by {vod_json["user_name"]}', str(e))

            # set to None so that channel function knows download failed
            vod_json = None

        # catch unhandled exceptions
        except BaseException as e:
            if vod_live:
                self.log.debug('Exception encountered, terminating download workers...')
                for worker in workers:
                    worker.terminate()
                    worker.join()

            send_push(self.pushbullet_key, f'Exception encountered while downloading VOD {vod_id} by '
                                           f'{vod_json["user_name"]}', str(e))
            self.log.error('Exception encountered while downloading VOD %s.', vod_id, exc_info=True)

            # set to None so that channel function knows download failed
            vod_json = None

        # this is only used when archiving a channel
        return vod_json

    def get_vod(self, vod_json, get_video=True, get_chat=True, vod_live=False):
        """Retrieves a specified VOD.

        :param vod_json: dict of vod parameters retrieved from twitch
        :param get_video: boolean whether to grab video
        :param get_chat: boolean whether to grab chat logs
        :param vod_live: boolean true if vod currently live, false otherwise
        :return: dict containing current vod information
        """
        # create vod dir
        Path(vod_json['store_directory']).mkdir(parents=True, exist_ok=True)

        if time_since_date(datetime.strptime(
                vod_json['created_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()) \
                < (vod_json['duration'] + 360):
            self.log.debug('Running in live mode as VOD has been updated in the last 10 minutes.')
            vod_live = True

        # # import chat log if it has been partially downloaded
        # try:
        #     with open(Path(vod_json['store_directory'], 'verbose_chat.json'), 'r', encoding='utf8') as chat_file:
        #         chat_log = json.loads(chat_file.read())
        #
        #     # ignore chat logs created with older incompatible schema - see v2.2.1 changes
        #     if chat_log and 'contentOffsetSeconds' not in chat_log[0].keys():
        #         chat_log = []
        #
        # except FileNotFoundError:
        #     chat_log = []
        #
        # # fetch all streams for a particular vod
        # if get_video:
            try:
                vod_index = self.twitch.get_vod_index(vod_json, self.quality)

                # attempt to fetch playlist for requested stream
                Api.get_request(vod_index).text

            except TwitchAPIErrorForbidden as e:
                raise VodDownloadError('Error retrieving VOD index. VOD may have been deleted or supplied resolution '
                                       f'was invalid. Error: {str(e)}') from e

    def get_unsynced_stream(self, stream_info, stream=None):
        """Archives a live stream without a paired VOD.

        :param stream_info: json retrieved from stream endpoint
        :param stream: optionally provided stream method if existing buffer needs to be kept
        :return: sanitized / formatted stream json
        """
        if not stream:
            stream = Stream()

        # generate stream dict
        stream_json_keys = \
            ['vod_id', 'stream_id', 'user_id', 'user_login', 'user_name', 'title', 'description', 'created_at',
             'published_at', 'url', 'thumbnail_url', 'viewable', 'view_count', 'language', 'type', 'duration',
             'muted_segments', 'store_directory', 'video_archived', 'chat_archived']
        stream_json = {k: None for k in stream_json_keys}

        try:
            stream_json.update(
                {'stream_id': stream_info['stream']['id'], 'user_id': stream_info['id'],
                 'user_login': stream_info['displayName'].lower(), 'user_name': stream_info['displayName'],
                 'title': stream_info['broadcastSettings']['title'], 'created_at': stream_info['stream']['createdAt'],
                 'published_at': stream_info['stream']['createdAt'], 'type': 'live',
                 'video_archived': 1, 'chat_archived': 0})

            stream_json['store_directory'] = \
                str(Path(self.vod_directory, f'{sanitize_date(stream_json["created_at"])} - '
                                             f'{sanitize_text(stream_json["title"])} - STREAM_ONLY'))

            stream.get_stream(
                stream_json['user_name'], Path(stream_json['store_directory'], 'parts'), self.quality, False)

            # insert duration into json using stream created datetime
            created_at = int((datetime.strptime(stream_json['created_at'], '%Y-%m-%dT%H:%M:%SZ').timestamp()))
            stream_json['duration'] = int(datetime.utcnow().timestamp() - created_at)

            # merge stream segments and convert to mp4
            try:
                combine_vod_parts(stream_json, print_progress=not self.quiet)
                convert_vod(stream_json, [(0, 99999)], print_progress=not self.quiet)

            except Exception as e:
                raise VodMergeError(e) from e

            self.log.debug('Cleaning up temporary files...')
            cleanup_vod_parts(stream_json['store_directory'])

            return stream_json

        except KeyboardInterrupt:
            self.log.debug('Termination signal received, halting stream downloader.')
            if remove_lock(Path(tempfile.gettempdir(), 'twitch-archiver'), stream_json['stream_id'] + '-stream-only'):
                raise UnlockingError(stream_json['user_name'], stream_json['stream_id'])

            sys.exit(0)

        except (RequestError, VodMergeError) as e:
            self.log.debug('Exception downloading or merging stream.\n{e}', exc_info=True)
            send_push(self.pushbullet_key, 'Exception encountered while downloading or merging downloaded stream '
                                           f'by {stream_json["user_name"]}', str(e))

        except BaseException as e:
            self.log.error('Unexpected exception encountered while downloading live-only stream.\n%s', str(e),
                           exc_info=True)
            send_push(self.pushbullet_key, 'Unexpected exception encountered while downloading live-only stream '
                                           f'by {stream_json["user_name"]}', str(e))

        return False
