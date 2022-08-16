import json
import logging
import multiprocessing
import m3u8
import re
import sys

from math import floor
from pathlib import Path
from time import sleep

from src.api import Api
from src.database import Database, create_vod, __db_version__
from src.downloader import Downloader
from src.exceptions import VodDownloadError, ChatDownloadError, ChatExportError, VodMergeError, UnlockingError, \
    TwitchAPIErrorNotFound, TwitchAPIErrorForbidden, RequestError
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

            # retrieve available vods
            available_vods = []
            cursor = ''
            try:
                while True:
                    _r = self.callTwitch.get_api(f'videos?user_id={user_id}&first=100&type=archive&after={cursor}')
                    if not _r['pagination']:
                        break

                    available_vods.extend([vod['id'] for vod in _r['data']])
                    cursor = _r['pagination']['cursor']
            except Exception as e:
                self.log.error(f'Error retrieving VODs from Twitch. Error: {e}')
                continue

            self.log.info(f'Online vods: {available_vods}' if self.debug
                          else f'Online vods: {len(available_vods)}')

            # retrieve downloaded vods
            with Database(Path(self.config_dir, 'vods.db')) as db:
                downloaded_vods = \
                    [str(i[0]) for i in db.execute_query(f'select * from vods where user_id is {user_id}')]
            self.log.info(f'Downloaded vods: {downloaded_vods}' if self.debug
                          else f'Downloaded vods: {len(downloaded_vods)}')

            # generate vod queue using downloaded and available vods
            vod_queue = [vod_id for vod_id in available_vods if vod_id not in downloaded_vods]
            if not available_vods or not vod_queue:
                self.log.info('No new VODs were found.')
                continue

            self.log.info(f'{len(vod_queue)} VOD(s) in download queue.')
            self.log.debug(f'VOD queue: {vod_queue}')

            for vod_id in vod_queue:
                self.log.debug(f'Processing VOD {vod_id} by {user_name}')
                self.log.debug('Creating lock file for VOD.')

                if Utils.create_lock(self.config_dir, vod_id):
                    self.log.info(f'Lock file present for VOD {vod_id}, skipping.')
                    continue

                # check if vod in database
                with Database(Path(self.config_dir, 'vods.db')) as db:
                    downloaded_vods = \
                        [str(i[0]) for i in db.execute_query(f'select * from vods where user_id is {user_id}')]

                if vod_id in downloaded_vods:
                    self.log.info('VOD has been downloaded since database was last checked, skipping.')
                    continue

                vod_json = self.get_vod_connector([vod_id])

                if vod_json:
                    # add to database
                    self.log.debug('Adding VOD info to database.')
                    with Database(Path(self.config_dir, 'vods.db')) as db:
                        db.execute_query(create_vod, vod_json)

                    # remove lock
                    self.log.debug('Removing lock file.')
                    if Utils.remove_lock(self.config_dir, vod_id):
                        raise UnlockingError(vod_id)

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
                ['id', 'stream_id', 'user_id', 'user_login', 'user_name', 'title', 'description', 'created_at',
                 'published_at', 'url', 'thumbnail_url', 'viewable', 'view_count', 'language', 'type', 'duration',
                 'muted_segments', 'store_directory', 'duration_seconds']
            stream_json = {k: None for k in stream_json_keys}

            stream_json.update(
                {'stream_id': channel_data['id'], 'user_id': channel_data['user_id'],
                 'user_login': channel_data['user_login'], 'user_name': channel_data['user_name'],
                 'title': channel_data['title'], 'created_at': channel_data['started_at'],
                 'published_at': channel_data['started_at'], 'language': channel_data['language'],
                 'type': channel_data['type']})

            stream_json['store_directory'] = \
                str(Path(self.vod_directory, f'{Utils.sanitize_date(stream_json["created_at"])} - '
                                             f'{Utils.sanitize_text(stream_json["title"])} - NO_VOD'))

            stream = Stream(self.client_id, self.client_secret, self.oauth_token)

            stream.get_stream(
                stream_json['user_name'], Path(stream_json['store_directory'], 'parts'), self.quality, False)

            # insert duration into json using stream created datetime
            created_at = int((datetime.datetime.strptime(stream_json['created_at'], '%Y-%m-%dT%H:%M:%SZ').timestamp()))
            stream_json['duration_seconds'] = datetime.datetime.now().timestamp() - created_at
            stream_json['duration'] = Utils.convert_to_hms(['duration_seconds'])

            # merge stream segments and convert to mp4
            try:
                Utils.combine_vod_parts(stream_json, print_progress=False if self.quiet else True)
                Utils.convert_vod(stream_json, print_progress=False if self.quiet else True)

            except Exception as e:
                raise VodMergeError(e)

            self.log.debug('Cleaning up temporary files...')
            Utils.cleanup_vod_parts(stream_json['store_directory'])

            return stream_json

        except KeyboardInterrupt:
            self.log.debug('User requested stop, halting stream downloader.')
            if Path(self.config_dir, f'.lock.{stream_json["display_name"]}').exists():
                Utils.remove_lock(self.config_dir, stream_json["display_name"])

            sys.exit(0)

        except (RequestError, VodMergeError) as e:
            self.log.debug('Exception downloading or merging stream.\n{e}', exc_info=True)
            Utils.send_push(self.pushbullet_key, 'Exception encountered while downloading or merging downloaded stream '
                                                 f'by {stream_json["display_name"]}', str(e))
            return

        except Exception as e:
            self.log.error(f'Unexpected exception encountered while downloading live-only stream.\n{e}', exc_info=True)
            Utils.send_push(self.pushbullet_key, 'Unexpected exception encountered while downloading live-only stream'
                                                 f'by {stream_json["display_name"]}', str(e))
            return

    def get_vod_connector(self, vods):
        """Download a single vod or list of vod IDs.

        :param vods: list of vod ids
        :return: dict containing current vod information returned by get_vod
        """
        self.log.info(f'Archiving VOD(s) "{vods}".')
        vod_json = False

        for vod_id in vods:
            self.log.info(f'Now processing VOD: {vod_id}')
            vod_json = self.callTwitch.get_api(f'videos?id={vod_id}')['data'][0]
            vod_json['muted_segments'] = str(vod_json['muted_segments'])
            vod_json['store_directory'] = \
                str(Path(self.vod_directory, f'{Utils.sanitize_date(vod_json["created_at"])} - '
                                             f'{Utils.sanitize_text(vod_json["title"])} - {vod_id}'))
            vod_json['duration_seconds'] = Utils.convert_to_seconds(vod_json['duration'])

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
                    if self.video:
                        workers.append(multiprocessing.Process(target=stream.get_stream, args=(
                            vod_json['user_name'], Path(vod_json['store_directory'], 'parts'), self.quality)))

                    workers.append(multiprocessing.Process(target=self.get_vod, args=(vod_json, vod_live)))

                    for worker in workers:
                        worker.start()

                    for worker in workers:
                        worker.join()

                else:
                    self.get_vod(vod_json, vod_live)

                # return imported json rather than returning from get_vod process as there were issues with returning
                # values via multiprocessing
                vod_json = Utils.import_json(vod_json)

                # combine vod segments
                if self.video:
                    # combine all the 10s long .ts parts into a single file, then convert to .mp4
                    try:
                        Utils.combine_vod_parts(vod_json, print_progress=False if self.quiet else True)
                        Utils.convert_vod(vod_json, print_progress=False if self.quiet else True)

                    except Exception as e:
                        raise VodMergeError(e)

                    # verify vod length is equal to what is grabbed from twitch
                    if Utils.verify_vod_length(vod_json):
                        raise VodMergeError('VOD length outside of acceptable range. If error persists delete '
                                            "'vod/parts' directory if VOD still available.")

                if self.chat:
                    with open(Path(vod_json['store_directory'], 'verbose_chat.json'), 'r') as chat_file:
                        chat_log = json.loads(chat_file.read())

                    # generate and export the readable chat log
                    if chat_log:
                        try:
                            self.log.debug('Generating readable chat log and saving to disk...')
                            r_chat_log = Utils.generate_readable_chat_log(chat_log)
                            Utils.export_readable_chat_log(r_chat_log, vod_json['store_directory'])

                        except Exception as e:
                            raise ChatExportError(e)

                    else:
                        self.log.info('No chat messages found.')

                if self.video:
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

                if Path(self.config_dir, f'.lock.{vod_id}').exists():
                    Utils.remove_lock(self.config_dir, vod_id)

                sys.exit(1)

            # catch halting errors, send notification and remove lock file
            except (RequestError, VodDownloadError, ChatDownloadError, VodMergeError, ChatExportError) as e:
                if vod_live:
                    self.log.debug('Exception encountered, terminating download workers...')
                    for worker in workers:
                        worker.terminate()
                        worker.join()

                self.log.error(f'Error downloading VOD {vod_id}.', exc_info=True)
                Utils.send_push(self.pushbullet_key, f'Error downloading VOD {vod_id}', str(e))
                # remove lock file if archiving channel
                if Path(self.config_dir, f'.lock.{vod_id}').exists():
                    Utils.remove_lock(self.config_dir, vod_id)

                # set to False so that channel function knows download failed
                vod_json = False

            # catch unhandled exceptions
            except Exception as e:
                if vod_live:
                    self.log.debug('Exception encountered, terminating download workers...')
                    for worker in workers:
                        worker.terminate()
                        worker.join()

                Utils.send_push(self.pushbullet_key, f'Exception encountered while downloading VOD {vod_id}', str(e))
                self.log.error(f'Exception encountered while downloading VOD {vod_id}.', exc_info=True)

                vod_json = False

        # this is only used when archiving a channel
        return vod_json

    def get_vod(self, vod_json, vod_live=False):
        """Retrieves a specified VOD.

        :param vod_json: dict of vod parameters retrieved from twitch
        :param vod_live: boolean true if vod currently live, false otherwise
        :return: dict containing current vod information
        """
        # create vod dir
        Path(vod_json['store_directory']).mkdir(parents=True, exist_ok=True)

        # wait if vod recently created
        if Utils.time_since_date(vod_json['created_at']) < 300:
            self.log.info('Waiting 5m to download initial VOD parts as it was created very recently. Live archiving '
                          'will still function.')
            sleep(300)

        if Utils.time_since_date(vod_json['created_at']) < (vod_json['duration_seconds'] + 360):
            self.log.debug('Time since VOD was created + its duration is a point in time < 10 minutes ago. '
                           'Running in live mode in case not all parts are available yet.')
            vod_live = True

        # import chat log if it has been partially downloaded
        try:
            with open(Path(vod_json['store_directory'], 'verbose_chat.json'), 'r') as chat_file:
                chat_log = json.loads(chat_file.read())

        except FileNotFoundError:
            chat_log = []

        # loop for processing live vods
        while True:
            try:
                _r = self.callTwitch.get_api(f'videos?id={vod_json["id"]}')

                vod_json = _r['data'][0]
                vod_json['muted_segments'] = str(vod_json['muted_segments'])
                vod_json['store_directory'] = \
                    str(Path(self.vod_directory, f'{Utils.sanitize_date(vod_json["created_at"])} - '
                                                 f'{Utils.sanitize_text(vod_json["title"])} - {vod_json["id"]}'))
                vod_json['duration_seconds'] = Utils.convert_to_seconds(vod_json['duration'])

                Utils.export_json(vod_json)

            except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
                self.log.warning('Error retrieving VOD json - VOD was likely deleted.')
                with open(Path(vod_json['store_directory'], '.ignorelength'), 'w') as _:
                    pass

                vod_live = False

            if self.video:
                # download all available vod parts
                self.log.info('Grabbing video...')
                try:
                    vod_index = self.callTwitch.get_vod_index(vod_json['id'], self.quality)

                    vod_playlist = Api.get_request(vod_index).text

                    # update vod json with m3u8 duration - more accurate than twitch API
                    _m = re.findall('(?<=#EXT-X-TWITCH-TOTAL-SECS:).*(?=\n)', vod_playlist)[0]
                    vod_json['duration_seconds'] = floor(float(_m))
                    Utils.export_json(vod_json)

                    # replace extra chars in base_url like /chunked/index[-muted-JU07DEVBNK.m3u8]
                    _m = re.findall('(?<=\/)(index.*)', vod_index)[0]
                    vod_base_url = vod_index.replace(_m, '')

                    self.download.get_m3u8_video(m3u8.loads(vod_playlist), vod_base_url, vod_json['store_directory'])

                except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
                    self.log.warning('Error 403 or 404 returned when downloading VOD parts - VOD was likely deleted.')
                    with open(Path(vod_json['store_directory'], '.ignorelength'), 'w') as _:
                        pass

                    vod_live = False

                except Exception as e:
                    raise VodDownloadError(e)

            if self.chat:
                # download all available chat segments
                self.log.info('Grabbing chat logs...')
                try:
                    if not chat_log:
                        chat_log = self.download.get_chat(vod_json)

                    # only try to grab more chat logs if we aren't past vod length
                    elif int(chat_log[-1]['content_offset_seconds']) < vod_json['duration_seconds']:
                        self.log.debug(f'Grabbing chat logs from offset: {chat_log[-1]["content_offset_seconds"]}')
                        chat_log.extend(
                            [n for n in
                             self.download.get_chat(vod_json, floor(int(chat_log[-1]['content_offset_seconds'])))
                             if n['_id'] not in [m['_id'] for m in chat_log]])

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
