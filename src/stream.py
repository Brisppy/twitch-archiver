import logging
import m3u8
import os
import requests
import shutil
import tempfile

from datetime import datetime
from math import floor
from pathlib import Path
from time import sleep

from src.api import Api
from src.exceptions import TwitchAPIErrorNotFound
from src.twitch import Twitch


class Stream:
    def __init__(self, client_id, client_secret, oauth_token):

        self.log = logging.getLogger()

        self.callTwitch = Twitch(client_id, client_secret, oauth_token)

    def get_stream(self, channel, output_dir):
        """Retrieves a stream for a specified channel.

        :param channel: name of twitch channel to download
        :param output_dir: location to place downloaded .ts chunks
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        try:
            index_uri = self.callTwitch.get_channel_hls_index(channel)
            user_id = self.callTwitch.get_api('users?login=' + channel)['data'][0]['id']
            latest_vod_created_time = self.callTwitch.get_api('videos?user_id=' + str(user_id))['data'][0]['created_at']
            latest_vod_created_time = datetime.strptime(latest_vod_created_time, '%Y-%m-%dT%H:%M:%SZ')

        # raised when channel goes offline
        except TwitchAPIErrorNotFound:
            self.log.error('Stream offline.')
            return

        buffer = []
        segment_ids = {}
        downloaded_segments = []
        completed_segments = []

        while True:
            try:
                # retrieve available segments
                incoming_segments = m3u8.loads(Api.get_request(index_uri).text).data

            except TwitchAPIErrorNotFound:
                self.log.info('Stream has ended.')
                # rename most recent downloaded .ts files if they are .ts.tmp parts
                try:
                    last_id = seg_id

                except NameError:
                    return

                # rename most recent segment
                if not Path(output_dir, str('{:05d}'.format(last_id)) + '.ts').exists():
                    shutil.move(Path(tempfile.gettempdir(), segment_ids[seg_id]),
                                Path(output_dir, str('{:05d}'.format(last_id)) + '.ts'))

                return

            for segment in incoming_segments['segments']:
                # skip ad segments
                if segment['title'] != 'live':
                    self.log.debug('Ad segment detected, skipping...')
                    continue

                # get time between vod start and segment time
                time_since_start = \
                    segment['program_date_time'].replace(tzinfo=None).timestamp() - latest_vod_created_time.timestamp()

                # manual offset of 4 seconds is added - it just works
                segment_id = floor((4 + time_since_start) / 10)

                # store any new segment ids
                if segment_id not in segment_ids.keys():
                    self.log.debug('New live segment found: ' + str(segment_id))
                    segment_ids.update({segment_id: os.urandom(24).hex()})

                # store and initialize useful segment info
                segment = tuple((segment['uri'], segment['program_date_time'].replace(tzinfo=None),
                                 segment_id, segment['duration']))

                # append segment if part hasn't yet been added to buffer or downloaded
                if segment not in buffer and segment not in downloaded_segments:
                    self.log.debug('New part added to buffer: ' + str(segment))
                    buffer.append(segment)

            # go through segments in buffer which aren't yet downloaded
            for segment in [seg for seg in buffer if seg not in downloaded_segments]:
                with open(Path(tempfile.gettempdir(), segment_ids[segment[2]]), 'ab') as tmp_ts_file:
                    for attempt in range(6):
                        if attempt > 4:
                            self.log.debug('Maximum retries reach for stream part download.')
                            break

                        try:
                            _r = requests.get(segment[0], stream=True)

                            if _r.status_code != 200:
                                break

                            # write part to temp file
                            for chunk in _r.iter_content(chunk_size=1024):
                                tmp_ts_file.write(chunk)

                            # remove from incoming buffer and add to downloaded segments
                            buffer.remove(segment)
                            downloaded_segments.append(segment)

                            break

                        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ReadTimeout) as e:
                            self.log.debug('Error downloading VOD part, retrying. ' + str(e))
                            continue

            # rename temp segments when they are finished
            for seg_id in [seg for seg in segment_ids.keys() if seg not in completed_segments]:
                # get segments with matching id
                segments = [seg for seg in downloaded_segments if seg[2] == seg_id]

                # rename file if 5 chunks found
                if len(segments) == 5:
                    tmp_ts_file = Path(tempfile.gettempdir(), segment_ids[seg_id])
                    ts_path = Path(output_dir, str('{:05d}'.format(seg_id) + '.ts'))

                    if tmp_ts_file.exists:
                        # remove if matches destination
                        if os.path.exists(ts_path) and os.path.samefile(ts_path, tmp_ts_file):
                            os.remove(tmp_ts_file)

                        else:
                            # first move to temp file
                            shutil.move(tmp_ts_file, ts_path.with_suffix('.ts.tmp'))
                            # rename temp file after it has successfully been moved
                            shutil.move(ts_path.with_suffix('.ts.tmp'), ts_path)
                            self.log.debug('Piece ' + str(Path(ts_path).stem) + ' completed.')

                        self.log.debug('Live piece: ' + str(seg_id) + ' completed.')
                        completed_segments.append(seg_id)

            sleep(4)
