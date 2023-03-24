"""
Module for downloading currently live Twitch broadcasts.
"""

import logging
import os
import tempfile

from datetime import datetime, timezone
from glob import glob
from math import floor
from pathlib import Path
from time import sleep

import m3u8
import requests

from twitcharchiver.api import Api
from twitcharchiver.exceptions import TwitchAPIErrorNotFound, UnsupportedStreamPartDuration
from twitcharchiver.twitch import Twitch
from twitcharchiver.utils import time_since_date, safe_move


class Stream:
    """
    Functions pertaining to grabbing and downloading stream segments.
    """
    def __init__(self, client_id, client_secret, oauth_token):

        self.log = logging.getLogger()

        self.call_twitch = Twitch(client_id, client_secret, oauth_token)

        self.buffer = {}
        self.segment_ids = {}
        self.downloaded_segments = set()
        # track progress for unsynced streams
        self.processed_segments = set()
        self.segment_id = 0

    def unsynced_setup(self, output_dir):
        # get existing parts to resume counting if archiving halted
        existing_parts = [Path(p) for p in sorted(glob(str(Path(output_dir, '*.ts'))))]
        if existing_parts:
            # set to 1 above highest numbered part
            self.segment_id = int(existing_parts[-1].name.strip('.ts')) + 1

        self.buffer[self.segment_id] = []
        self.segment_ids[self.segment_id] = os.urandom(24).hex()

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
        latest_segment = None
        latest_segment_timestamp = None

        # vars for unsynced download - skip if running in synced mode, or setup already performed
        if not sync_vod_segments and not self.segment_ids:
            self.unsynced_setup(output_dir)

        try:
            self.log.debug('Fetching required stream information.')
            index_uri = self.call_twitch.get_channel_hls_index(channel, quality)
            stream_json = self.call_twitch.get_api(f'users?login={channel}')['data'][0]
            user_id = stream_json['id']
            latest_vod_created_time = self.call_twitch.get_api(f'videos?user_id={user_id}')['data'][0]['created_at']
            latest_vod_created_time = datetime.strptime(latest_vod_created_time, '%Y-%m-%dT%H:%M:%SZ')

        # raised when channel goes offline
        except TwitchAPIErrorNotFound:
            self.log.error('Stream offline.')
            return

        while True:
            start_timestamp = int(datetime.utcnow().timestamp())

            # attempt to grab new segments from Twitch
            for attempt in range(6):
                if attempt > 4:
                    return

                try:
                    self.log.debug('Fetching incoming stream segments.')
                    incoming_segments = m3u8.loads(Api.get_request(index_uri).text).data
                    break

                # stream has ended if exception encountered
                except TwitchAPIErrorNotFound:
                    self.get_final_segment(self.buffer, output_dir, self.segment_ids)
                    return

                except requests.exceptions.ConnectTimeout:
                    self.log.debug('Timed out attempting to fetch new stream segments, retrying. (Attempt %s)',
                                   attempt + 1)
                    continue

            # set latest segment and timestamp if new segment found
            if incoming_segments['segments'][-1]['uri'] != latest_segment:
                latest_segment = incoming_segments['segments'][-1]['uri']
                latest_segment_timestamp = int(datetime.now(timezone.utc).timestamp())

            # assume stream has ended once >20s has passed since the last segment was advertised
            if self.buffer and time_since_date(latest_segment_timestamp) > 20:
                self.get_final_segment(self.buffer, output_dir, self.segment_ids)
                return

            if not sync_vod_segments:
                self.build_unsynced_buffer(incoming_segments)

            else:
                self.build_synced_buffer(incoming_segments, latest_vod_created_time)

            # download buffer and store completed segments
            self.download_buffer(output_dir)

            # sleep if processing time < 4s before checking for new segments
            processing_time = int(datetime.utcnow().timestamp() - start_timestamp)
            if processing_time < 4:
                sleep(4 - processing_time)

    def build_synced_buffer(self, incoming_segments, latest_vod_created_time):
        """Creates a buffer of parts to download without syncing with the part timestamping used by Twitch VODs.

        :param incoming_segments: dict of segments advertised by Twitch
        :param latest_vod_created_time: timestamp of vod creation
        """
        # manage incoming segments and create buffer of segments to download
        bad_segments = []
        for segment in incoming_segments['segments']:
            self.log.debug('Processing part: %s', segment)

            # skip ad segments
            if segment['title'] != 'live':
                self.log.debug('Ad detected, skipping.')
                continue

            # catch streams with dynamic part length - set to 2 as often the final 2 segments are < 2s
            if len(bad_segments) > 2:
                raise UnsupportedStreamPartDuration

            if segment['duration'] != 2.0 and segment not in bad_segments:
                self.log.debug("Part has invalid duration (%s).", segment['duration'])
                bad_segments.append(segment)
                continue

            # get time between vod start and segment time
            time_since_start = \
                segment['program_date_time'].replace(
                    tzinfo=None).timestamp() - latest_vod_created_time.timestamp()

            # get segment id based on time since vod start
            # manual offset of 4 seconds is added - it just works
            segment_id = floor((4 + time_since_start) / 10)

            if segment_id in self.downloaded_segments:
                continue

            if segment_id not in self.segment_ids.keys():
                self.log.debug('New live segment found: %s', segment_id)
                # give each segment id a unique id
                self.segment_ids[segment_id] = os.urandom(24).hex()
                self.buffer[segment_id] = []

            segment = tuple(
                (segment['uri'], segment['program_date_time'].replace(tzinfo=None), segment['duration']))

            # only continue processing if segment not yet in buffer for segment id
            if segment in self.buffer[segment_id]:
                continue

            self.log.debug('New part added to buffer: %s <- %s', segment_id, segment)
            self.buffer[segment_id].append(segment)

    def build_unsynced_buffer(self, incoming_segments):
        """Creates a buffer of parts to download without syncing with the part timestamping used by Twitch VODs.

        :param incoming_segments: dict of segments advertised by Twitch
        :return: updated segment id
        """
        # manage incoming segments and create buffer of segments to download
        bad_segments = []
        for segment in incoming_segments['segments']:
            self.log.debug('Processing part: %s', segment)

            # skip ad segments
            if segment['title'] != 'live':
                self.log.debug('Ad detected, skipping.')
                continue

            # catch streams with dynamic part length - set to 2 as often the final 2 segments are < 2s
            if len(bad_segments) > 2:
                raise UnsupportedStreamPartDuration

            segment = tuple(
                (segment['uri'], segment['program_date_time'].replace(tzinfo=None), segment['duration']))

            # skip already processed segments
            if segment in self.processed_segments:
                continue

            self.processed_segments.add(segment)

            # check if segment already completed as id may not have been incremented if current segment is
            # completed before the next pass causing a KeyError
            if self.segment_id in self.downloaded_segments or len(self.buffer[self.segment_id]) == 5:
                self.segment_id += 1

            # add segment id to buffer if not present
            if self.segment_id not in self.buffer.keys():
                self.segment_ids[self.segment_id] = os.urandom(24).hex()
                self.buffer[self.segment_id] = []

            self.log.debug('New part added to buffer: %s <- %s', self.segment_id, segment)
            self.buffer[self.segment_id].append(segment)

    def download_buffer(self, output_dir):
        """Downloads all completed segments (containing 5 parts) from the buffer to the desired directory.

        :param output_dir: path to download buffer to
        """
        for segment_id in [seg_id for seg_id in self.buffer.keys() if len(self.buffer[seg_id]) == 5]:
            for attempt in range(6):
                if attempt > 4:
                    self.log.error('Maximum attempts reached while downloading segment %s.', segment_id)
                    break

                if self.write_buffer_segment(segment_id, output_dir, self.segment_ids[segment_id],
                                             self.buffer[segment_id]):
                    continue

                # clean buffer
                self.buffer.pop(segment_id)
                self.downloaded_segments.add(segment_id)
                break

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
                    for chunk in _r.iter_content(chunk_size=262144):
                        tmp_ts_file.write(chunk)

                except requests.exceptions.RequestException as e:
                    self.log.debug(
                        'Error downloading VOD stream segment %s : %s. Error: %s', segment_id, segment, str(e))
                    return True

        # move finished ts file to destination storage
        try:
            safe_move(Path(tempfile.gettempdir(), tmp_file), Path(output_dir, str(f'{segment_id:05d}' + '.ts')))
            self.log.debug('Live segment: %s completed.', segment_id)

        except BaseException as e:
            self.log.debug('Exception while moving stream segment %s. Error: %s', segment_id, str(e))
            return True

        return False

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

            if not Path(output_dir, str(f'{last_id:05d}') + '.ts').exists():
                self.log.debug('Final part not found in output directory, assuming last segment is complete and'
                               ' downloading.')
                for attempt in range(6):
                    if attempt > 4:
                        self.log.debug('Maximum attempts reached while downloading segment %s.', last_id)
                        break

                    if self.write_buffer_segment(last_id, output_dir, segment_ids[last_id], buffer[last_id]):
                        continue

                    break
