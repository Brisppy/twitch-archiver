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
            self.log.info("Now archiving channel '" + channel + "'.")
            self.log.debug('Fetching user data from Twitch.')

            user_data = self.callTwitch.get_api('users?login=' + channel)['data'][0]
            user_id = user_data['id']
            user_name = user_data['display_name']

            self.vod_directory = Path(self.directory, user_name)

            # setup database
            with Database(Path(self.config_dir, 'vods.db')) as db:
                db.setup_database()
                version = db.execute_query('pragma user_version')[0][0]

                if version == 0:
                    db.execute_query(f'pragma user_version = {__db_version__}')

            # retrieve available vods
            available_vods = []
            cursor = ''
            try:
                while True:
                    _r = self.callTwitch.get_api('videos?user_id=' + str(user_id) + '&first=100&type=archive&after='
                                                 + cursor)
                    if not _r['pagination']:
                        break

                    available_vods.extend([vod['id'] for vod in _r['data']])
                    cursor = _r['pagination']['cursor']
            except Exception as e:
                self.log.error('Error retrieving VODs from Twitch. Error: ' + str(e))
                continue

            self.log.debug('Available vods: ' + str(available_vods))

            # retrieve downloaded vods
            with Database(Path(self.config_dir, 'vods.db')) as db:
                downloaded_vods = [str(i[0]) for i in db.execute_query('select * from vods where user_id is {}'
                                                                       .format(user_id))]
            self.log.debug('Downloaded vods: ' + str(downloaded_vods))

            # generate vod queue using downloaded and available vods
            vod_queue = [vod_id for vod_id in available_vods if vod_id not in downloaded_vods]
            if not available_vods or not vod_queue:
                self.log.info('No VODs are available for download.')
                continue

            self.log.info(str(len(vod_queue)) + ' VOD(s) in download queue.')
            self.log.debug('VOD queue: ' + str(vod_queue))

            for vod_id in vod_queue:
                self.log.debug('Processing VOD ' + str(vod_id) + ' by ' + user_name)
                self.log.debug('Creating lock file for VOD.')

                if Utils.create_lock(self.config_dir, vod_id):
                    self.log.info('Lock file present for VOD ' + str(vod_id) + ', skipping.')
                    continue

                # check if vod in database
                with Database(Path(self.config_dir, 'vods.db')) as db:
                    downloaded_vods = \
                        [str(i[0]) for i in db.execute_query('select * from vods where user_id is {}'.format(user_id))]

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
                    self.log.debug('No VOD information returned to channel downloader, downloader exited with error.')
                    continue

    def get_vod_connector(self, vods):
        """Download a single vod or list of vod IDs.

        :param vods: list of vod ids
        :return: dict containing current vod information returned by get_vod
        """
        self.log.info("Archiving vod(s) '" + str(vods) + "'.")

        for vod_id in vods:
            self.log.info('Now processing VOD: ' + str(vod_id))
            vod_json = self.callTwitch.get_api('videos?id=' + str(vod_id))['data'][0]
            vod_json['muted_segments'] = str(vod_json['muted_segments'])
            vod_json['store_directory'] = str(Path(self.vod_directory, Utils.sanitize_date(vod_json['created_at'])
                                                   + ' - ' + Utils.sanitize_text(vod_json['title']) + ' - '
                                                   + str(vod_id)))
            vod_json['duration_seconds'] = Utils.convert_to_seconds(vod_json['duration'])

            # get vod status
            vod_live = self.callTwitch.get_vod_status(vod_json)

            self.log.info('VOD ' + ('currently or recently live. Running in LIVE mode.' if vod_live else 'offline.'))

            _r = None

            try:
                if vod_live:
                    stream = Stream(self.client_id, self.client_secret, self.oauth_token)
                    # concurrently grab live pieces and vod chunks
                    multiprocessing.set_start_method('fork')

                    workers = []

                    # the stream module itself has no checks for what to download so this is done here
                    if self.video:
                        workers.append(multiprocessing.Process(target=stream.get_stream, args=(
                                       vod_json['user_name'], Path(vod_json['store_directory'], 'parts'))))

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
                        raise VodMergeError(e, vod_json['id'])

                    # verify vod length is equal to what is grabbed from twitch
                    if Utils.verify_vod_length(vod_json):
                        raise VodMergeError('VOD length less than expected.', vod_json['id'])

                if self.chat:
                    with open(Path(vod_json['store_directory'], 'verboseChat.json'), 'r') as chat_file:
                        chat_log = json.loads(chat_file.read())

                    # generate and export the readable chat log
                    if chat_log:
                        try:
                            self.log.debug('Generating readable chat log and saving to disk...')
                            r_chat_log = Utils.generate_readable_chat_log(chat_log)
                            Utils.export_readable_chat_log(r_chat_log, vod_json['store_directory'])

                        except Exception as e:
                            raise ChatExportError(e, vod_json['id'])

                    else:
                        self.log.info('No chat messages found.')

                if self.video:
                    # delete temporary .ts parts and merged.ts file
                    self.log.debug('Cleaning up temporary files...')
                    Utils.cleanup_vod_parts(vod_json['store_directory'])

            # catch user exiting and remove lock file
            except KeyboardInterrupt:
                if vod_live:
                    for worker in workers:
                        worker.terminate()
                        worker.join()
                if Path(self.config_dir, '.lock.' + str(vod_id)).exists():
                    Utils.remove_lock(self.config_dir, vod_id)
                sys.exit(1)

            # catch halting errors, send notification and remove lock file
            except (RequestError, VodDownloadError, ChatDownloadError, VodMergeError, ChatExportError) as e:
                if vod_live:
                    for worker in workers:
                        worker.terminate()
                        worker.join()
                self.log.error(f'Error downloading VOD {vod_id}. Error:' + str(e))
                Utils.send_push(self.pushbullet_key, f'Error downloading VOD {vod_id}', str(e))
                # remove lock file if archiving channel
                if Path(self.config_dir, '.lock.' + str(vod_id)).exists():
                    Utils.remove_lock(self.config_dir, vod_id)
                continue

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
            with open(Path(vod_json['store_directory'], 'verboseChat.json'), 'r') as chat_file:
                chat_log = json.loads(chat_file.read())

        except FileNotFoundError:
            chat_log = []

        # loop for processing live vods
        while True:
            try:
                _r = self.callTwitch.get_api('videos?id=' + str(vod_json['id']))

                vod_json = _r['data'][0]
                vod_json['muted_segments'] = str(vod_json['muted_segments'])
                vod_json['store_directory'] = str(Path(self.vod_directory,
                                                       Utils.sanitize_date(vod_json['created_at'])
                                                       + ' - ' + Utils.sanitize_text(vod_json['title'])
                                                       + ' - ' + str(vod_json['id'])))
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
                    vod_index = self.callTwitch.get_vod_index(vod_json['id'])
                    vod_playlist = m3u8.loads(Api.get_request(vod_index).text)
                    # replace extra chars in base_url like /chunked/index[-muted-JU07DEVBNK.m3u8]
                    _m = re.findall('(?<=\/chunked\/)(.*)', vod_index)[0]
                    vod_base_url = vod_index.replace(_m, '')

                    self.download.get_video(vod_playlist, vod_base_url, vod_json)

                except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
                    self.log.warning('Error 403 or 404 returned when downloading VOD parts - VOD was likely deleted.')
                    with open(Path(vod_json['store_directory'], '.ignorelength'), 'w') as _:
                        pass

                    vod_live = False

                except Exception as e:
                    raise VodDownloadError(e, vod_json['id'])

            if self.chat:
                # download all available chat segments
                self.log.info('Grabbing chat logs...')
                try:
                    if not chat_log:
                        chat_log = self.download.get_chat(vod_json)

                    # only try to grab more chat logs if we aren't past vod length
                    elif int(chat_log[-1]['content_offset_seconds']) < vod_json['duration_seconds']:
                        self.log.debug('Grabbing chat logs from offset: ' + str(chat_log[-1]['content_offset_seconds']))
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
                    raise ChatDownloadError(e, vod_json['id'])

            if vod_live:
                # wait up to 10 minutes, checking every minute to verify if vod is still being updated or not
                for _ in range(11):
                    self.log.debug('Waiting 60s to see if VOD changes.')
                    sleep(60)
                    try:
                        # restart while loop if new video segments found
                        if len(vod_playlist.segments) != len(m3u8.loads(Api.get_request(vod_index).text).segments):
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
