import logging
import m3u8
import os
import requests
import tempfile

from datetime import datetime, timezone
from glob import glob
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

    def get_stream(self, channel, output_dir, quality='best', sync_vod_segments=True):
        """Retrieves a stream for a specified channel.

        :param channel: name of twitch channel to download
        :param output_dir: location to place downloaded .ts chunks
        :param quality: desired quality in the format [resolution]p[framerate] or 'best', 'worst'
        :param sync_vod_segments: create segments for combining with archived VOD parts. If true we will try to recreate
                                  the segment numbering scheme Twitch uses, otherwise we use our own numbering scheme.
                                  Used when archiving a live stream without a VOD.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        buffer = {}
        segment_ids = {}
        completed_segments = set()
        bad_segments = []
        latest_segment = None

        # vars for unsynced download
        if not sync_vod_segments:
            processed_segments = set()
            # get existing parts to resume counting if archiving halted
            existing_parts = [Path(p) for p in sorted(glob(str(Path(output_dir, '*.ts'))))]
            if existing_parts:
                # set to 1 above highest numbered part
                segment_id = int(existing_parts[-1].name.strip('.ts')) + 1
            else:
                segment_id = 0

            buffer[segment_id] = []
            segment_ids[segment_id] = os.urandom(24).hex()

        try:
            self.log.debug('Fetching required stream information.')
            index_uri = self.callTwitch.get_channel_hls_index(channel, quality)
            stream_json = self.callTwitch.get_api(f'users?login={channel}')['data'][0]
            user_id = stream_json['id']
            latest_vod_created_time = self.callTwitch.get_api(f'videos?user_id={user_id}')['data'][0]['created_at']
            latest_vod_created_time = datetime.strptime(latest_vod_created_time, '%Y-%m-%dT%H:%M:%SZ')

        # raised when channel goes offline
        except TwitchAPIErrorNotFound:
            self.log.error('Stream offline.')
            return

        while True:
            start_timestamp = int(datetime.utcnow().timestamp())

            try:
                self.log.debug('Fetching incoming stream segments.')
                incoming_segments = m3u8.loads(Api.get_request(index_uri).text).data

            # stream has ended if exception encountered
            except TwitchAPIErrorNotFound:
                self.get_final_segment(buffer, output_dir, segment_ids)
                return

            # set latest segment and timestamp if new segment found
            if incoming_segments['segments'][-1]['uri'] != latest_segment:
                latest_segment = incoming_segments['segments'][-1]['uri']
                latest_segment_timestamp = int(datetime.now(timezone.utc).timestamp())

            # assume stream has ended once >20s has passed since the last segment was advertised
            if buffer and Utils.time_since_date(latest_segment_timestamp) > 20:
                self.get_final_segment(buffer, output_dir, segment_ids)
                return

            # manage incoming segments and create buffer of segments to download
            for segment in incoming_segments['segments']:
                self.log.debug(f'Processing part: {segment}')

                # skip ad segments
                if segment['title'] != 'live':
                    self.log.debug('Ad detected, skipping.')
                    continue

                # catch streams with dynamic part length - set to 2 as often the final 2 segments are < 2s
                if len(bad_segments) > 2:
                    self.log.error('Multiple parts with unsupported duration found which cannot be accurately '
                                   'combined. Falling back to VOD archiver only.')
                    return

                if sync_vod_segments:
                    if segment['duration'] != 2.0 and segment not in bad_segments:
                        self.log.debug(f"Part has invalid duration ({segment['duration']}).")
                        bad_segments.append(segment)
                        continue

                    # get time between vod start and segment time
                    time_since_start = \
                        segment['program_date_time'].replace(
                            tzinfo=None).timestamp() - latest_vod_created_time.timestamp()

                    # get segment id based on time since vod start
                    # manual offset of 4 seconds is added - it just works
                    segment_id = floor((4 + time_since_start) / 10)

                    if segment_id in completed_segments:
                        continue

                    if segment_id not in segment_ids.keys():
                        self.log.debug(f'New live segment found: {segment_id}')
                        # give each segment id a unique id
                        segment_ids[segment_id] = os.urandom(24).hex()
                        buffer[segment_id] = []

                    segment = tuple(
                        (segment['uri'], segment['program_date_time'].replace(tzinfo=None), segment['duration']))

                    # only continue processing if segment not yet in buffer for segment id
                    if segment in buffer[segment_id]:
                        continue

                else:
                    segment = tuple(
                        (segment['uri'], segment['program_date_time'].replace(tzinfo=None), segment['duration']))

                    # skip already processed segments
                    if segment in processed_segments:
                        continue
                    else:
                        processed_segments.add(segment)

                    # check if segment already completed as id may not have been incremented if current segment is
                    # completed before the next pass causing a KeyError
                    if segment_id in completed_segments or len(buffer[segment_id]) == 5:
                        segment_id += 1

                    # add segment id to buffer if not present
                    if segment_id not in buffer.keys():
                        segment_ids[segment_id] = os.urandom(24).hex()
                        buffer[segment_id] = []

                self.log.debug(f'New part added to buffer: {segment_id} <- {segment}')
                buffer[segment_id].append(segment)

            # download any full segments (contains 5 parts)
            for segment_id in [seg_id for seg_id in buffer.keys() if len(buffer[seg_id]) == 5]:
                for attempt in range(6):
                    if attempt > 4:
                        self.log.debug(f'Maximum attempts reached while downloading segment {segment_id}.')
                        break

                    if self.write_buffer_segment(segment_id, output_dir, segment_ids[segment_id], buffer[segment_id]):
                        continue

                    else:
                        # clean buffer
                        buffer.pop(segment_id)
                        completed_segments.add(segment_id)
                        break

            # sleep if processing time < 4s before checking for new segments
            processing_time = int(datetime.utcnow().timestamp() - start_timestamp)
            if processing_time < 4:
                sleep(4 - processing_time)

    def write_buffer_segment(self, segment_id, output_dir, tmp_file, segment_parts):
        """Downloads and moves a given segment from the buffer.

        :param segment_id: numbered segment to download
        :param output_dir: location to output segment to
        :param tmp_file: name of temporary file
        :param segment_parts: list of parts which make up the segment
        :return: True on error
        """
        with open(Path(tempfile.gettempdir(), tmp_file), 'wb') as tmp_ts_file:
            for segment in segment_parts:
                try:
                    _r = requests.get(segment[0], stream=True, timeout=5)

                    if _r.status_code != 200:
                        return True

                    # write part to file
                    for chunk in _r.iter_content(chunk_size=1024):
                        tmp_ts_file.write(chunk)

                except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ReadTimeout) as e:
                    self.log.debug(f'Error downloading VOD stream segment {segment_id} : {segment}. Error: {e}')
                    return True

        # move finished ts file to destination storage
        try:
            Utils.safe_move(Path(tempfile.gettempdir(), tmp_file),
                            Path(output_dir, str('{:05d}'.format(segment_id) + '.ts')))
            self.log.debug(f'Live segment: {segment_id} completed.')

        except Exception as e:
            self.log.debug(f'Exception while moving stream segment {segment_id}. {e}')
            return True

        return

    def get_final_segment(self, buffer, output_dir, segment_ids):
        """Downloads and stores the final stream segments.

        :param buffer: segments which are available for download
        :param output_dir: location to move completed segment to
        :param segment_ids: segment id(s) to download
        """
        # ensure final segment present
        if buffer.keys():
            # export the highest segment if stream ends before final segment meets requirements
            last_id = max(buffer.keys())

            if not Path(output_dir, str('{:05d}'.format(last_id)) + '.ts').exists():
                self.log.debug('Final part not found in output directory, assuming last segment is complete and'
                               ' downloading.')
                for attempt in range(6):
                    if attempt > 4:
                        self.log.debug(f'Maximum attempts reached while downloading segment {last_id}.')
                        break

                    if self.write_buffer_segment(last_id, output_dir, segment_ids[last_id], buffer[last_id]):
                        continue

                    else:
                        break
