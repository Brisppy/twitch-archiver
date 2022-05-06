import logging
import m3u8
import os
import requests
import tempfile

from datetime import datetime
from math import floor
from pathlib import Path
from time import sleep

from src.api import Api
from src.exceptions import TwitchAPIErrorNotFound
from src.twitch import Twitch
from src.utils import Utils


class Stream:
    def __init__(self, client_id, client_secret, oauth_token):

        self.log = logging.getLogger()

        self.callTwitch = Twitch(client_id, client_secret, oauth_token)

    def get_stream(self, channel, output_dir, quality='best'):
        """Retrieves a stream for a specified channel.

        :param channel: name of twitch channel to download
        :param output_dir: location to place downloaded .ts chunks
        :param quality: desired quality in the format [resolution]p[framerate] or 'best', 'worst'
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        try:
            index_uri = self.callTwitch.get_channel_hls_index(channel, quality)
            user_id = self.callTwitch.get_api(f'users?login={channel}')['data'][0]['id']
            latest_vod_created_time = self.callTwitch.get_api(f'videos?user_id={user_id}')['data'][0]['created_at']
            latest_vod_created_time = datetime.strptime(latest_vod_created_time, '%Y-%m-%dT%H:%M:%SZ')

        # raised when channel goes offline
        except TwitchAPIErrorNotFound:
            self.log.error('Stream offline.')
            return

        buffer = []
        segment_ids = {}
        downloaded_segments = []
        completed_segments = []
        bad_segments = []

        while True:
            start_timestamp = int(datetime.utcnow().timestamp())

            try:
                incoming_segments = m3u8.loads(Api.get_request(index_uri).text).data

            except TwitchAPIErrorNotFound:
                self.log.info('Stream has ended.')
                # rename most recent downloaded .ts file if stream ends before final segment is meets requirements
                try:
                    last_id = seg_id
                except NameError:
                    return

                if not Path(output_dir, str('{:05d}'.format(last_id)) + '.ts').exists():
                    Utils.safe_move(Path(tempfile.gettempdir(), segment_ids[seg_id]),
                                    Path(output_dir, str('{:05d}'.format(last_id)) + '.ts'))

                return

            for segment in incoming_segments['segments']:
                self.log.debug(f'Processing part: {segment}')

                # skip ad segments
                if segment['title'] != 'live':
                    self.log.debug('Ad detected, skipping.')
                    continue

                # catch streams with dynamic part length
                if len(bad_segments) > 1:
                    self.log.error('Multiple parts with varying duration found - These cannot be accurately '
                                   'combined so are not supported. Falling back to VOD archiver only.')
                    return

                if segment['duration'] != 2.0 and segment not in bad_segments:
                    self.log.debug(f'Part has invalid duration ({segment[-1]}).')
                    bad_segments.append(segment)
                    continue

                # get time between vod start and segment time
                time_since_start = \
                    segment['program_date_time'].replace(tzinfo=None).timestamp() - latest_vod_created_time.timestamp()

                # manual offset of 4 seconds is added - it just works
                segment_id = floor((4 + time_since_start) / 10)
                if segment_id not in segment_ids.keys():
                    self.log.debug(f'New live segment found: {segment_id}')
                    segment_ids.update({segment_id: os.urandom(24).hex()})
                segment = tuple((segment['uri'], segment['program_date_time'].replace(tzinfo=None),
                                 segment_id, segment['duration']))

                # append if part hasn't been added to buffer yet or downloaded
                if segment not in buffer and segment not in downloaded_segments:
                    self.log.debug(f'New part added to buffer: {segment}')
                    buffer.append(segment)

            # iterate over buffer segments which aren't yet downloaded
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

                            # write part to file
                            for chunk in _r.iter_content(chunk_size=1024):
                                tmp_ts_file.write(chunk)

                            buffer.remove(segment)
                            downloaded_segments.append(segment)

                            break

                        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ReadTimeout) as e:
                            self.log.debug(f'Error downloading VOD part, retrying. {e}')
                            continue

            # rename .tmp segments when they are finished
            for seg_id in [seg for seg in segment_ids.keys() if seg not in completed_segments]:
                # get segments with matching id
                segments = [seg for seg in downloaded_segments if seg[2] == seg_id]

                # rename file if 5 chunks found and combined length is 10s
                if len(segments) == 5 and sum([seg[3] for seg in segments]) == 10.0:
                    # move finished ts file to destination storage
                    try:
                        Utils.safe_move(Path(tempfile.gettempdir(), segment_ids[seg_id]),
                                        Path(output_dir, str('{:05d}'.format(seg_id) + '.ts')))
                        self.log.debug(f'Live piece: {seg_id} completed.')
                        completed_segments.append(seg_id)

                    except Exception as e:
                        self.log.debug(f'Exception while moving stream segment {seg_id}. {e}')
                        pass

            # sleep if processing time < 4s before checking for new segments
            if (remaining_time := int(datetime.utcnow().timestamp() - start_timestamp)) < 4:
                sleep(remaining_time)
