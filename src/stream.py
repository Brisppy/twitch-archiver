import logging
import m3u8
import os
import requests
import sys

from datetime import datetime
from glob import glob
from math import floor
from pathlib import Path
from time import sleep

from src.api import Api
from src.exceptions import TwitchAPIErrorNotFound
from src.twitch import Twitch


class Stream:
    def __init__(self, client_id, client_secret, oauth_token):

        self.log = logging.getLogger('twitch-archive')

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
        downloaded_segments = []
        completed_segments = []

        while True:
            try:
                incoming_segments = m3u8.loads(Api.get_request(index_uri).text).data

            except TwitchAPIErrorNotFound:
                self.log.info('Stream has ended.')
                # rename most recent downloaded .ts files if they are .ts.tmp parts
                last_ids = [str(Path(p).name).lstrip('0') for p in glob(str(Path(output_dir, '*.ts*')))][-2:-1]
                for last_id in last_ids:
                    if '.tmp' in last_id:
                        os.rename(Path(output_dir, last_id), Path(output_dir, last_id.replace('.tmp', '')))

                sys.exit('Stream has ended.')

            for segment in incoming_segments['segments']:
                # skip ad segments
                if segment['title'] != 'live':
                    self.log.debug('Ad segment detected, skipping...')
                    continue

                # get time between vod start and segment time
                time_since_start = segment['program_date_time'].replace(tzinfo=None).timestamp() \
                                   - latest_vod_created_time.timestamp()

                # manual offset of 4 seconds is added - it just works
                segment_id = str('{:05d}'.format(floor((4 + time_since_start) / 10)))
                segment = tuple((segment['uri'], segment['program_date_time'].replace(tzinfo=None),
                                 segment_id, segment['duration']))

                # append if part hasn't been added to buffer yet or downloaded
                if segment not in buffer and segment not in downloaded_segments:
                    buffer.append(segment)
                    self.log.debug('New segment found: ' + str(segment))

            self.log.debug('Stream buffer: ' + str(buffer))

            # iterate over buffer segments which aren't yet downloaded
            for segment in [seg for seg in buffer if seg not in downloaded_segments]:
                with open(Path(output_dir, segment[2] + '.ts.tmp'), 'ab') as tsfile:
                    _r = requests.get(segment[0], stream=True)
                    if _r.status_code != 200:
                        break

                    # write part to file
                    for chunk in _r.iter_content(chunk_size=1024):
                        tsfile.write(chunk)

                    buffer.remove(segment)
                    downloaded_segments.append(segment)

                    continue

            # extract all unique downloaded segment ids
            segment_ids = set([seg[2] for seg in downloaded_segments])
            self.log.debug('Unique segment ids: ' + str(segment_ids))

            # rename .tmp segments when they are finished
            for seg_id in [seg for seg in segment_ids if seg not in completed_segments]:
                # get segments with matching id
                segments = [seg for seg in downloaded_segments if seg[2] == seg_id]

                # rename file if 5 chunks found
                if len(segments) == 5:
                    os.rename(Path(output_dir, seg_id + '.ts.tmp'), Path(output_dir, seg_id + '.ts'))
                    self.log.debug('Completed segment: ' + str(seg_id))
                    completed_segments.append(seg_id)

            sleep(4)
