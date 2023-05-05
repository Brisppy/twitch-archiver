"""
Module used for downloading archived videos and chat logs from Twitch.
"""

from glob import glob
import json
import logging
import os
import tempfile

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from twitcharchiver.api import Api
from twitcharchiver.exceptions import VodPartDownloadError, TwitchAPIErrorNotFound, ChatDownloadError, RequestError
from twitcharchiver.utils import Progress, to_ranges, safe_move


class Downloader:
    """
    Functions used for the downloading of video and chat from Twitch VODs.
    """
    def __init__(self, client_id, oauth_token, threads=20, quiet=False):
        """

        :param client_id: twitch client id
        :param oauth_token: oauth token retrieved with client id and secret
        :param threads: number of download threads
        :param quiet: hide progress bars
        """

        self.log = logging.getLogger()

        self.client_id = client_id
        self.oauth_token = oauth_token

        self.threads = threads
        self.quiet = quiet

    def get_m3u8_video(self, m3u8_playlist, m3u8_base_url, store_directory):
        """Downloads the video for a specified m3u8 playlist.

        :param m3u8_playlist: m3u8 playlist to retrieve video from
        :param m3u8_base_url: url from which .ts files are derived from
        :param store_directory: location to store downloaded segments
        :raises vodPartDownloadError: error returned when downloading vod parts
        """
        Path(store_directory, 'parts').mkdir(parents=True, exist_ok=True)

        ts_url_list = []
        ts_path_list = []
        muted_segments = []

        # collect ids of all downloaded parts
        downloaded_ids = [str(Path(p).name)[:4].lstrip('0') + str(Path(p).name)[4:]
                          for p in glob(str(Path(store_directory, 'parts', '*.ts')))]

        # process all ids in playlist
        for ts_id in [s.uri for s in m3u8_playlist.segments]:
            if '-unmuted' in ts_id:
                # rename segments as their url remains unchanged after being unmuted
                ts_id = ts_id.replace('-unmuted', '-muted')

            # store all muted segments
            if '-muted' in ts_id:
                muted_segments.append(int(ts_id.replace('-muted.ts', '')))

            # append ts_id to to-download list if it isn't already downloaded
            if ts_id.replace('-muted', '') not in downloaded_ids:
                # create a tuple with (TS_URL, TS_PATH)
                ts_url_list.append(m3u8_base_url + ts_id)
                ts_path_list.append(Path(store_directory, 'parts',
                                         str(f'{int(ts_id.split(".")[0].replace("-muted", "")):05d}' + '.ts')))

        # export list of muted ids if present
        with open(Path(store_directory, 'parts', '.muted'), 'w', encoding='utf8') as mutefile:
            json.dump(list(to_ranges(muted_segments)), mutefile)

        if ts_url_list and ts_path_list:
            # create worker pool for downloading vods
            with ThreadPoolExecutor(max_workers=self.threads) as pool:
                download_error = []
                futures = []
                ct = 0
                # append work orders along with args to queue
                for ts_url, ts_path in zip(ts_url_list, ts_path_list):
                    futures.append(pool.submit(self.get_ts_segment, ts_url, ts_path))

                progress = Progress()

                # process queue
                for future in futures:
                    if future.result():
                        # append any returned errors
                        download_error.append(future.result())
                        continue

                    ct += 1
                    if not self.quiet:
                        progress.print_progress(ct, len(ts_url_list))

            if download_error:
                raise VodPartDownloadError(download_error)

    def get_ts_segment(self, ts_url, ts_path):
        """Retrieves a specific ts file.

        :param ts_url: url of .ts file to download
        :param ts_path: destination path for .ts file after downloading
        :return: error on failure
        """
        self.log.debug('Downloading segment %s to %s', ts_url, ts_path)

        # don't bother if piece already downloaded
        if os.path.exists(ts_path):
            return False

        # files are downloaded to $TMP, then moved to final destination
        # takes 3:32 to download an hour long VOD to NAS, compared to 5:00 without using $TMP as download cache
        #   a better method would be to have 20 workers downloading, and 20 moving temp
        #   files from storage avoiding any downtime downloading

        # create temporary file for downloading to
        with open(Path(tempfile.gettempdir(), os.urandom(24).hex()), 'wb') as tmp_ts_file:
            for _ in range(6):
                if _ > 4:
                    self.log.debug('Maximum retries for segment %s reached.', Path(ts_path).stem)
                    return {1, f'Maximum retries for segment {Path(ts_path).stem} reached.'}

                try:
                    _r = requests.get(ts_url, stream=True, timeout=10)

                    # break on non 200 status code
                    if _r.status_code != 200:
                        self.log.error('Code other than 200 received when trying to download segment.')
                        continue

                    # write downloaded chunks to temporary file
                    for chunk in _r.iter_content(chunk_size=262144):
                        tmp_ts_file.write(chunk)

                    self.log.debug('Segment %s download completed.', Path(ts_path).stem)

                    break

                except requests.exceptions.RequestException as e:
                    self.log.debug('Segment %s download failed (Attempt %s). Error: %s)',
                                   Path(ts_path).stem, _ + 1, str(e))
                    continue

        try:
            # move part to destination storage
            safe_move(tmp_ts_file.name, ts_path)
            self.log.debug('Segment %s completed.', Path(ts_path).stem)

        except FileNotFoundError as e:
            raise VodPartDownloadError(f'MPEG-TS segment did not download correctly. Piece: {ts_url}') from e

        except BaseException as e:
            self.log.error('Exception encountered while moving downloaded MPEG-TS segment %s.', ts_url, exc_info=True)
            return e

        return False

    def get_chat(self, vod_json, offset=0):
        """Downloads the chat for a specified VOD, returning comments beginning from offset (if provided).

        :param vod_json: dict of vod information
        :param offset: offset in seconds to begin chat retrieval from
        """
        chat_log = []
        message_ids = set()
        prev_page = None

        _s = requests.session()
        _s.headers.update({'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko'})

        # grab initial chat segment containing cursor
        initial_segment, next_page = self.get_chat_segment(_s, vod_json['vod_id'], offset)
        chat_log.extend(initial_segment)
        message_ids.update([m['id'] for m in chat_log])
        offset = chat_log[-1]['contentOffsetSeconds']

        progress = Progress()

        # we use the contentOffset of the last comment grabbed as a rudimentary cursor as Twitch severely restricted
        # access to the GQL API by implementing 'kasadas' which is far more work to try and bypass than I feel is worth
        while offset <= vod_json['duration'] and next_page:
            # break infinite loops
            if offset == prev_page:
                offset += 1
                continue

            prev_page = offset

            try:
                # grab next chat segment based on offset
                segment, next_page = self.get_chat_segment(_s, vod_json['vod_id'], offset)
                chat_log.extend([m for m in segment if m['id'] not in message_ids])
                message_ids.update([m['id'] for m in chat_log])

                # vod duration in seconds is used as the total for progress bar
                # comment offset is used to track what's been done
                # could be done properly if there was a way to get the total number of comments
                if not self.quiet:
                    progress.print_progress(int(segment[-1]['contentOffsetSeconds']),
                                            vod_json['duration'], not offset)

                # move cursor to offset of most recent message, or increment
                if chat_log[-1]['contentOffsetSeconds'] > offset:
                    offset = chat_log[-1]['contentOffsetSeconds']

                else:
                    offset += 1

            except TwitchAPIErrorNotFound:
                break

        _s.close()

        self.log.info('Found %s messages.', len(chat_log))

        return chat_log

    def get_chat_segment(self, session, vod_id, offset):
        """Retrieves a single chat segment.

        :param session: requests session to link request to
        :param vod_id: id of vod to retrieve segment from
        :param offset: offset in seconds to begin retrieval from
        :return: list of comments and cursor if one is returned from twitch
        :return: True if more pages available
        """
        # build payload
        _p = [{"operationName": "VideoCommentsByOffsetOrCursor",
               "variables": {"videoID": vod_id, "contentOffsetSeconds": offset}}]

        _p[0]['extensions'] = \
            {'persistedQuery': {'version': 1,
                                'sha256Hash': "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"}}

        for attempt in range(6):
            if attempt > 4:
                self.log.error('Maximum attempts reached while downloading chat segment at offset: %s.', offset)
                raise ChatDownloadError

            try:
                _r = Api.post_request_with_session('https://gql.twitch.tv/gql', session, _p).json()

            except RequestError:
                continue

            break

        comments = _r[0]['data']['video']['comments']

        return [c['node'] for c in comments['edges']], comments['pageInfo']['hasNextPage']
