import json
import logging
import multiprocessing
import m3u8
import re
import shutil
import sys

from datetime import datetime, timezone
from math import floor
from pathlib import Path
from time import sleep

from src.api import Api
from src.database import Database, create_vod, update_vod, __db_version__
from src.downloader import Downloader
from src.exceptions import VodDownloadError, ChatDownloadError, ChatExportError, VodMergeError, UnlockingError, \
    TwitchAPIErrorNotFound, TwitchAPIErrorForbidden, RequestError, CorruptPartError
from src.stream import Stream
from src.twitch import Twitch
from src.utils import Utils


class Processing:
    """
    Primary processing loops for downloading content.
    """
    def __init__(self, config, args):

        self.log = logging.getLogger()

        self.directory = args['directory']
        self.vod_directory = Path(self.directory)
        self.video = args['video']
        self.chat = args['chat']
        self.quality = args['quality']
        self.stream_only = args['stream_only']
        self.no_stream = args['no_stream']
        self.config_dir = args['config_dir']
        self.quiet = args['quiet']
        self.debug = args['debug']

        self.client_id = config['client_id']
        self.client_secret = config['client_secret']
        self.oauth_token = config['oauth_token']

        self.pushbullet_key = config['pushbullet_key']

        self.callTwitch = Twitch(self.client_id, self.client_secret, self.oauth_token)
        self.download = Downloader(self.client_id, self.oauth_token, args['threads'], args['quiet'])

    def get_channel(self, channels):
        """
        Download all vods from a specified channel or list of channels.
        """
        for channel in channels:
            self.log.info(f"Now archiving channel '{channel}'.")
            self.log.debug('Fetching user data from Twitch.')

            user_data = self.callTwitch.get_api(f'users?login={channel}')['data'][0]
            user_id = user_data['id']
            user_name = user_data['display_name']

            channel_live = False
            live_vod_exists = False

            self.vod_directory = Path(self.directory, user_name)

            # setup database
            with Database(Path(self.config_dir, 'vods.db')) as db:
                # check db version
                version = db.execute_query('pragma user_version')[0][0]

                if version != __db_version__:
                    # incremental database updating based on version number
                    # create the latest db schema if none exists
                    if version == 0:
                        self.log.debug('No schema found, creating database.')
                        db.setup_database()

                    # update version 2 schema to version 3
                    if version == 2:
                        self.log.debug('Performing incremental DB update. Version 2 -> Version 3.')
                        db.update_database(2)
                        version = 3

                    # update version 3 schema to version 4
                    if version == 3:
                        self.log.debug('Performing incremental DB update. Version 3 -> Version 4.')
                        db.update_database(3)

            # retrieve available vods
            available_vods: dict[int: tuple[int]] = {}
            cursor = ''
            try:
                while True:
                    _r = self.callTwitch.get_api(f'videos?user_id={user_id}&first=100&type=archive&after={cursor}')
                    if not _r['pagination']:
                        break

                    # dict containing stream_id: (vod_id)
                    available_vods.update(dict([(int(vod['stream_id']), (vod['id'])) for vod in _r['data']]))
                    cursor = _r['pagination']['cursor']

            except Exception as e:
                self.log.error(f'Error retrieving VODs from Twitch. Error: {e}')
                continue

            self.log.info(f'Online VODs: {available_vods}' if self.debug
                          else f'Online VODs: {len(available_vods)}')

            # retrieve downloaded vods
            with Database(Path(self.config_dir, 'vods.db')) as db:
                # dict containing stream_id: (vod_id, video_downloaded, chat_downloaded)
                downloaded_vods = dict([(i[0], (i[1], i[2], i[3])) for i in db.execute_query(
                    'SELECT stream_id, vod_id, video_archived, chat_archived FROM vods WHERE user_id IS ?',
                    {'user_id' : user_id})])
            self.log.info(f'Downloaded vods: {downloaded_vods}' if self.debug
                          else f'Downloaded vods: {len(downloaded_vods)}')

            # generate vod queue using downloaded and available vods
            vod_queue = {}
            for stream_id in available_vods.keys():
                # add any vods not present in database
                if stream_id not in downloaded_vods.keys():
                    vod_queue.update({stream_id: (available_vods[stream_id], self.video, self.chat)})

                # if vod in database but downloaded as stream, go over it again using backup vod downloader
                # to ensure the vod is properly archived along with the chat which we missed
                elif downloaded_vods[stream_id][0] is None:
                    vod_queue.update({stream_id: (available_vods[stream_id], True, self.chat)})

                # if vod in database, check downloaded formats against requested ones, adding vod with missing formats
                # to queue
                elif not downloaded_vods[stream_id][1] and self.video or \
                        not downloaded_vods[stream_id][2] and self.chat:
                    vod_queue.update({stream_id: (available_vods[stream_id],
                                                  not downloaded_vods[stream_id][1] and self.video,
                                                  not downloaded_vods[stream_id][2] and self.chat)})

            # check if channel is online and stream type is live
            channel_data = self.callTwitch.get_api(f'streams?user_id={user_id}')['data']
            if channel_data and channel_data[0]['type'] == 'live':
                channel_live = True
                # check if most recent vods stream_id matches current live stream id
                live_vod_exists = int(channel_data[0]['id']) in available_vods.keys()

            # move on if channel offline and no vods are available
            if not self.stream_only and not channel_live and not available_vods:
                self.log.info(f'No VODs were found for {user_name}.')
                continue

            elif not channel_live and self.stream_only:
                continue

            # archive stream in non-segmented mode if no paired vod exists
            if not self.no_stream and channel_live and not live_vod_exists and self.video:
                self.log.info('Channel live but not being archived to a VOD, running stream archiver.')
                self.log.debug('Creating lock file for stream.')

                if Utils.create_lock(self.config_dir, channel_data[0]['id'] + '-stream-only'):
                    self.log.info(f'Lock file present for stream by {user_name} (.lock.{channel_data[0]["id"]}'
                                  f'-stream-only), skipping.')
                    pass

                else:
                    # check if stream in database
                    with Database(Path(self.config_dir, 'vods.db')) as db:
                        downloaded_streams = [str(i[0]) for i in db.execute_query(
                            'SELECT stream_id FROM vods WHERE user_id IS ?', {'user_id': user_id})]

                    # Check if stream id in database
                    if channel_data[0]['id'] in downloaded_streams:
                        self.log.info('Stream has already been downloaded.')
                        pass

                    else:
                        try:
                            stream_json = self.get_unsynced_stream(channel_data[0])

                            if stream_json:
                                # add to database
                                self.log.debug('Adding stream info to database.')
                                with Database(Path(self.config_dir, 'vods.db')) as db:
                                    db.execute_query(create_vod, stream_json)

                            else:
                                self.log.debug('No stream information returned to channel function, stream downloader'
                                               ' exited with error.')
                                pass

                        except Exception as e:
                            self.log.error(f'Exception encountered while archiving live-only stream by {user_name}.'
                                           'Error:', e)
                            return

                        finally:
                            # remove lock
                            self.log.debug('Removing lock file.')
                            if Utils.remove_lock(self.config_dir, channel_data[0]['id'] + '-stream-only'):
                                raise UnlockingError(user_name, stream_id=channel_data[0]['id'])

            # exit if vod queue empty
            if not vod_queue:
                self.log.info(f'No new VODs were found for {user_name}.')
                continue

            self.log.info(f'{len(vod_queue)} VOD(s) in download queue.')
            self.log.debug(f'VOD queue: {vod_queue}')

            # begin processing each available vod
            for stream_id in vod_queue:
                vod_id = vod_queue[stream_id][0]
                # skip if we are only after the current stream
                if channel_data and self.stream_only and stream_id != int(channel_data[0]['id']):
                    continue

                elif channel_data and self.no_stream and stream_id == int(channel_data[0]['id']):
                    self.log.info('Skipping VOD as it is live and no-stream argument provided.')
                    continue

                self.log.debug(f'Processing VOD {vod_id} by {user_name}')
                self.log.debug('Creating lock file for VOD.')

                if Utils.create_lock(self.config_dir, stream_id):
                    self.log.info(f'Lock file present for VOD {vod_id} (.lock.{stream_id}), skipping.')
                    continue

                # check if vod in database
                with Database(Path(self.config_dir, 'vods.db')) as db:
                    downloaded_vod = db.execute_query(
                        'SELECT vod_id, video_archived, chat_archived FROM vods WHERE stream_id IS ?',
                        {'stream_id': stream_id})

                # check if vod_id exists in database in the requested format(s)
                if downloaded_vod and vod_queue[stream_id][1] and downloaded_vod[0][1]\
                        and vod_queue[stream_id][2] and downloaded_vod[0][2]:
                    self.log.info('VOD has been downloaded in requested format since download queue was created.')
                    continue

                vod_json = self.get_vod_connector(vod_id, vod_queue[stream_id][1], vod_queue[stream_id][2])

                if vod_json:
                    # insert video, chat archival flags
                    vod_json['video_archived'] = vod_queue[stream_id][1]
                    if 'chat_archived' not in vod_json.keys():
                        vod_json['chat_archived'] = vod_queue[stream_id][2]
                    # null empty values
                    for key in vod_json.keys():
                        if type(vod_json[key]) == str and vod_json[key] == "":
                            vod_json[key] = None

                    try:
                        # add to database
                        self.log.debug('Adding VOD info to database.')
                        with Database(Path(self.config_dir, 'vods.db')) as db:
                            # check if stream already exists and update if so
                            db_vod = db.execute_query(
                                'SELECT stream_id, video_archived, chat_archived FROM vods WHERE stream_id IS ?',
                                {'stream_id': vod_json['stream_id']})
                            if db_vod:
                                # update archived flags using previous and current processing flags
                                vod_json['video_archived'] = db_vod[0][1] or vod_json['video_archived']
                                vod_json['chat_archived'] = db_vod[0][2] or vod_json['chat_archived']
                                vod_json['sid'] = vod_json['stream_id']
                                db.execute_query(update_vod, vod_json)

                            else:
                                db.execute_query(create_vod, vod_json)

                    finally:
                        # remove lock
                        self.log.debug('Removing lock file.')
                        if Utils.remove_lock(self.config_dir, vod_json['stream_id']):
                            raise UnlockingError(vod_json['user_name'], vod_json['stream_id'], vod_id)

                else:
                    self.log.debug('No VOD information returned to channel function, downloader exited with error.')
                    continue

    def get_unsynced_stream(self, channel_data):
        """Archives a live stream without a paired VOD.

        :param channel_data: json retrieved from channel endpoint
        :return: sanitized / formatted stream json
        """
        try:
            # generate stream dict
            stream_json_keys = \
                ['vod_id', 'stream_id', 'user_id', 'user_login', 'user_name', 'title', 'description', 'created_at',
                 'published_at', 'url', 'thumbnail_url', 'viewable', 'view_count', 'language', 'type', 'duration',
                 'muted_segments', 'store_directory', 'video_archived', 'chat_archived']
            stream_json = {k: None for k in stream_json_keys}

            stream_json.update(
                {'stream_id': channel_data['id'], 'user_id': channel_data['user_id'],
                 'user_login': channel_data['user_login'], 'user_name': channel_data['user_name'],
                 'title': channel_data['title'], 'created_at': channel_data['started_at'],
                 'published_at': channel_data['started_at'], 'language': channel_data['language'],
                 'type': channel_data['type'], 'video_archived': 1, 'chat_archived': 0})

            stream_json['store_directory'] = \
                str(Path(self.vod_directory, f'{Utils.sanitize_date(stream_json["created_at"])} - '
                                             f'{Utils.sanitize_text(stream_json["title"])} - STREAM_ONLY'))

            stream = Stream(self.client_id, self.client_secret, self.oauth_token)

            stream.get_stream(
                stream_json['user_name'], Path(stream_json['store_directory'], 'parts'), self.quality, False)

            # insert duration into json using stream created datetime
            created_at = int((datetime.strptime(stream_json['created_at'], '%Y-%m-%dT%H:%M:%SZ').timestamp()))
            stream_json['duration'] = int(datetime.utcnow().timestamp() - created_at)

            # merge stream segments and convert to mp4
            try:
                Utils.combine_vod_parts(stream_json, print_progress=not self.quiet)
                Utils.convert_vod(stream_json, [(0, 99999)], print_progress=not self.quiet)

            except Exception as e:
                raise VodMergeError(e)

            self.log.debug('Cleaning up temporary files...')
            Utils.cleanup_vod_parts(stream_json['store_directory'])

            return stream_json

        except KeyboardInterrupt:
            self.log.debug('User requested stop, halting stream downloader.')
            if Path(self.config_dir, f'.lock.{channel_data["user_name"]}').exists():
                Utils.remove_lock(self.config_dir, channel_data[0]['id'] + '-stream-only')

            sys.exit(0)

        except (RequestError, VodMergeError) as e:
            self.log.debug('Exception downloading or merging stream.\n{e}', exc_info=True)
            Utils.send_push(self.pushbullet_key, 'Exception encountered while downloading or merging downloaded stream '
                                                 f'by {channel_data["user_name"]}', str(e))
            return

        except Exception as e:
            self.log.error(f'Unexpected exception encountered while downloading live-only stream.\n{e}', exc_info=True)
            Utils.send_push(self.pushbullet_key, 'Unexpected exception encountered while downloading live-only stream '
                                                 f'by {channel_data["user_name"]}', str(e))
            return

    def get_vod_connector(self, vod_id, get_video, get_chat):
        """Download a single vod or list of vod IDs.

        :param vod_id: vod id to download
        :param get_video: bool whether to grab video
        :param get_chat: bool whether to grab chat logs
        :return: dict containing current vod information returned by get_vod
        """
        self.log.info(f'Now processing VOD: {vod_id}')
        vod_json = self.callTwitch.get_api(f'videos?id={vod_id}')['data'][0]
        vod_json['vod_id'] = vod_json.pop('id')
        vod_json['muted_segments'] = str(vod_json['muted_segments'])
        vod_json['store_directory'] = \
            str(Path(self.vod_directory, f'{Utils.sanitize_date(vod_json["created_at"])} - '
                                         f'{Utils.sanitize_text(vod_json["title"])} - {vod_id}'))
        vod_json['duration'] = Utils.convert_to_seconds(vod_json['duration'])

        # get vod status
        vod_live = self.callTwitch.get_vod_status(vod_json['user_id'], vod_json['created_at'])

        self.log.info(f"VOD {'currently or recently live. Running in LIVE mode.' if vod_live else 'offline.'}")

        _r = None

        try:
            if vod_live:
                stream = Stream(self.client_id, self.client_secret, self.oauth_token)
                # concurrently grab live pieces and vod chunks

                workers = []

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

            # return imported json rather than returning from get_vod process as there were issues with returning
            # values via multiprocessing
            vod_json = Utils.import_json(vod_json)

            # combine vod segments
            if get_video:
                # combine all the 10s long .ts parts into a single file, then convert to .mp4
                try:
                    # retrieve vod chapters
                    try:
                        vod_chapters = Twitch.get_vod_chapters(vod_id)
                        if vod_chapters:
                            # write chapters to file
                            with open(Path(vod_json['store_directory'], 'chapters.json'), 'w') as chapters_file:
                                chapters_file.write(json.dumps(vod_chapters))

                        else:
                            # get category if no separate chapters found
                            vod_chapters = (Twitch.get_vod_category(vod_id), 0, vod_json['duration'] * 1000)

                        # format and write vod chapters to parts dir
                        with open(Path(vod_json['store_directory'], 'parts', 'chapters.txt'), 'w') as chapters_file:
                            chapters_file.write(Utils.format_vod_chapters(vod_chapters))

                    except Exception as e:
                        self.log.error(f'Failed to retrieve or insert chapters into VOD file. {e}')
                        pass

                    try:
                        Utils.combine_vod_parts(vod_json, print_progress=False if self.quiet else True)
                        # load muted segments if any exists
                        with open(Path(vod_json['store_directory'], 'parts', '.muted'), 'r') as mutefile:
                            muted_segments = json.load(mutefile)
                        Utils.convert_vod(vod_json, muted_segments, print_progress=False if self.quiet else True)

                    except CorruptPartError as c:
                        self.log.error("Corrupt segments found while converting VOD. Attempting to retry parts:"
                                       f"\n{', '.join([str(p) for p in c.parts])}")

                        # check vod still available
                        if not self.callTwitch.get_vod_index(vod_id):
                            raise VodDownloadError("Corrupt segments were found while converting VOD and TA was "
                                                   "unable to re-download the missing segments. Either re-download "
                                                   "the VOD if it is still available, or manually convert 'merged.ts' "
                                                   f"using FFmpeg. Corrupt parts:\n{', '.join(c.f_parts)}")

                        # rename corrupt segments
                        for part in c.parts:
                            # convert part number to segment file
                            part = str('{:05d}'.format(int(part)) + '.ts')

                            # rename part
                            shutil.move(Path(vod_json['store_directory'], 'parts', part),
                                        Path(vod_json['store_directory'], 'parts', part + '.corrupt'))

                        # download and combine vod again
                        try:
                            self.get_vod(vod_json, True, False, False)
                            Utils.combine_vod_parts(vod_json, print_progress=False if self.quiet else True)
                            Utils.convert_vod(vod_json, muted_segments, print_progress=False if self.quiet else True)

                        except CorruptPartError as e:
                            raise VodDownloadError(
                                "Corrupt part(s) still present after retrying VOD download. Ensure VOD is still "
                                "available and either delete the listed #####.ts part(s) from 'parts' folder or entire "
                                f"'parts' folder if issue persists.\n{', '.join(c.f_parts)}")

                except Exception as e:
                    raise VodMergeError(e)

                # verify vod length is equal to what is grabbed from twitch
                if Utils.verify_vod_length(vod_json):
                    raise VodMergeError('VOD length outside of acceptable range. If error persists delete '
                                        "'vod/parts' directory if VOD still available.")

            if get_chat:
                try:
                    with open(Path(vod_json['store_directory'], 'verbose_chat.json'), 'r') as chat_file:
                        chat_log = json.loads(chat_file.read())

                    # generate and export the readable chat log
                    if chat_log:
                        try:
                            self.log.debug('Generating readable chat log and saving to disk...')
                            r_chat_log = Utils.generate_readable_chat_log(chat_log, datetime.strptime(
                                vod_json['created_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc))
                            Utils.export_readable_chat_log(r_chat_log, vod_json['store_directory'])

                        except Exception as e:
                            raise ChatExportError(e)

                    else:
                        self.log.info('No chat messages found.')

                # catch missing chat log and modify database insert
                except FileNotFoundError:
                    self.log.error('No chat log found, download likely failed or log unavailable.')
                    vod_json['chat_archived'] = False

            if get_video:
                # grab thumbnail at 1080p resolution - any resolution can be used but this should be fine for almost
                # every stream
                try:
                    self.log.debug('Downloading VOD thumbnail.')
                    thumbnail = Api.get_request(vod_json['thumbnail_url'].replace('%{width}x%{height}', '1920x1080'))
                    with open(Path(vod_json['store_directory'], 'thumbnail.jpg'), 'wb') as thumbnail_file:
                        thumbnail_file.write(thumbnail.content)

                except Exception as e:
                    self.log.error('Failed to grab thumbnail for VOD.', e)
                    pass

                # delete temporary .ts parts and merged.ts file
                self.log.debug('Cleaning up temporary files...')
                Utils.cleanup_vod_parts(vod_json['store_directory'])

        # catch user exiting and remove lock file
        except KeyboardInterrupt:
            if vod_live:
                self.log.debug('User requested stop, terminating download workers...')
                for worker in workers:
                    worker.terminate()
                    worker.join()

            if Path(self.config_dir, f'.lock.{vod_json["stream_id"]}').exists():
                Utils.remove_lock(self.config_dir, vod_json['stream_id'])

            sys.exit(0)

        # catch halting errors, send notification and remove lock file
        except (RequestError, VodDownloadError, ChatDownloadError, VodMergeError, ChatExportError) as e:
            if vod_live:
                self.log.debug('Exception encountered, terminating download workers...')
                for worker in workers:
                    worker.terminate()
                    worker.join()

            self.log.error(f'Error downloading VOD {vod_id}.', exc_info=True)
            Utils.send_push(self.pushbullet_key, f'Error downloading VOD {vod_id} by {vod_json["user_name"]}', str(e))
            # remove lock file if archiving channel
            if Path(self.config_dir, f'.lock.{vod_json["stream_id"]}').exists():
                Utils.remove_lock(self.config_dir, vod_json['stream_id'])

            # set to None so that channel function knows download failed
            vod_json = None

        # catch unhandled exceptions
        except Exception as e:
            if vod_live:
                self.log.debug('Exception encountered, terminating download workers...')
                for worker in workers:
                    worker.terminate()
                    worker.join()

            Utils.send_push(self.pushbullet_key, f'Exception encountered while downloading VOD {vod_id} by '
                                                 f'{vod_json["user_name"]}', str(e))
            self.log.error(f'Exception encountered while downloading VOD {vod_id}.', exc_info=True)
            return

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

        # wait if vod recently created
        if Utils.time_since_date(datetime.strptime(
                vod_json['created_at'],'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()) < 300:
            self.log.info('Waiting 5m to download initial VOD parts as it was created very recently. Live archiving '
                          'will still function.')
            sleep(300)

        if Utils.time_since_date(datetime.strptime(
                vod_json['created_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()) \
                < (vod_json['duration'] + 360):
            self.log.debug('Time since VOD was created + its duration is a point in time < 10 minutes ago. '
                           'Running in live mode in case not all parts are available yet.')
            vod_live = True

        # import chat log if it has been partially downloaded
        try:
            with open(Path(vod_json['store_directory'], 'verbose_chat.json'), 'r') as chat_file:
                chat_log = json.loads(chat_file.read())

            # ignore chat logs created with older incompatible schema - see v2.2.1 changes
            if chat_log and 'contentOffsetSeconds' not in chat_log[0].keys():
                chat_log = []

        except FileNotFoundError:
            chat_log = []

        # fetch all streams for a particular vod
        if get_video:
            try:
                vod_index = self.callTwitch.get_vod_index(vod_json, self.quality)

                # attempt to fetch playlist for requested stream
                Api.get_request(vod_index).text

            except TwitchAPIErrorForbidden as e:
                raise VodDownloadError('Error retrieving VOD index. VOD may have been deleted or supplied resolution '
                                       f'was invalid. Error: {str(e)}')

        # loop for processing live vods
        while True:
            try:
                _r = self.callTwitch.get_api(f'videos?id={vod_json["vod_id"]}')

                vod_json = _r['data'][0]
                vod_json['vod_id'] = vod_json.pop('id')
                vod_json['muted_segments'] = str(vod_json['muted_segments']) if vod_json['muted_segments'] else None
                vod_json['store_directory'] = \
                    str(Path(self.vod_directory, f'{Utils.sanitize_date(vod_json["created_at"])} - '
                                                 f'{Utils.sanitize_text(vod_json["title"])} - {vod_json["vod_id"]}'))
                vod_json['duration'] = Utils.convert_to_seconds(vod_json['duration'])

                Utils.export_json(vod_json)

            except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
                self.log.warning('Error retrieving VOD json - VOD was likely deleted.')
                with open(Path(vod_json['store_directory'], '.ignorelength'), 'w') as _:
                    pass

                vod_live = False

            if get_video:
                # download all available vod parts
                self.log.info('Grabbing video...')
                try:
                    vod_playlist = Api.get_request(vod_index).text

                    # update vod json with m3u8 duration - more accurate than twitch API
                    _m = re.findall(r'(?<=#EXT-X-TWITCH-TOTAL-SECS:).*(?=\n)', vod_playlist)[0]
                    vod_json['duration'] = floor(float(_m))
                    Utils.export_json(vod_json)

                    # replace extra chars in base_url like /chunked/index[-muted-JU07DEVBNK.m3u8]
                    _m = re.findall(r'(?<=\/)(index.*)', vod_index)[0]
                    vod_base_url = vod_index.replace(_m, '')

                    self.download.get_m3u8_video(m3u8.loads(vod_playlist), vod_base_url, vod_json['store_directory'])

                except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
                    self.log.debug('Error 403 or 404 returned when downloading VOD parts - VOD was likely deleted.')
                    with open(Path(vod_json['store_directory'], '.ignorelength'), 'w') as _:
                        pass

                    vod_live = False

                except Exception as e:
                    raise VodDownloadError(e)

            if get_chat:
                # download all available chat segments
                self.log.info('Grabbing chat logs...')
                try:
                    if not chat_log:
                        chat_log = self.download.get_chat(vod_json)

                    # only try to grab more chat logs if we aren't past vod length
                    elif int(chat_log[-1]['contentOffsetSeconds']) < vod_json['duration']:
                        self.log.debug(f'Grabbing chat logs from offset: {chat_log[-1]["contentOffsetSeconds"]}')
                        chat_log.extend(
                            [n for n in
                             self.download.get_chat(vod_json, floor(int(chat_log[-1]['contentOffsetSeconds'])))
                             if n['id'] not in [m['id'] for m in chat_log]])

                    Utils.export_verbose_chat_log(chat_log, vod_json['store_directory'])

                except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
                    self.log.debug('Error 403 or 404 returned when downloading chat log - VOD was likely deleted.')
                    with open(Path(vod_json['store_directory'], '.ignorelength'), 'w') as _:
                        pass

                    vod_live = False

                except Exception as e:
                    raise ChatDownloadError(e)

            if vod_live:
                # wait up to 10 minutes, checking every minute to verify if vod is still being updated or not
                for _ in range(11):
                    self.log.debug('Waiting 60s to see if VOD changes.')
                    sleep(60)
                    try:
                        # restart while loop if new video segments found
                        if len(m3u8.loads(vod_playlist).segments)\
                                < len(m3u8.loads(Api.get_request(vod_index).text).segments):
                            self.log.debug('New VOD parts found.')
                            vod_live = True
                            break

                        # exit loop if 10 minutes pass without new vod segments being added
                        elif _ > 9:
                            self.log.debug('10m has passed since VOD duration changed - assuming it is no longer live.')
                            vod_live = False

                        else:
                            continue

                    except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
                        self.log.debug('Error 403 or 404 returned when checking for new VOD parts - VOD was likely'
                                       ' deleted.')
                        vod_live = False
                        break

            else:
                break
