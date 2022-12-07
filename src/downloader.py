from glob import glob
import logging
import os
import requests
import tempfile

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.api import Api
from src.exceptions import VodPartDownloadError, TwitchAPIErrorNotFound
from src.utils import Utils, Progress


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

        # collect ids of all downloaded parts
        downloaded_ids = [str(Path(p).name)[:4].lstrip('0') + str(Path(p).name)[4:]
                          for p in glob(str(Path(store_directory, 'parts', '*.ts')))]

        # process all ids in playlist
        for ts_id in [s.uri.replace('-muted', '') for s in m3u8_playlist.segments]:
            # append ts_id to to-download list if it isn't already downloaded
            if ts_id not in downloaded_ids:
                # create a tuple with (TS_URL, TS_PATH)
                ts_url_list.append(m3u8_base_url + ts_id)
                ts_path_list.append(Path(store_directory, 'parts',
                                         str('{:05d}'.format(int(ts_id.split('.')[0])) + '.ts')))

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
        self.log.debug(f'Downloading segment {ts_url} to {ts_path}')

        # don't bother if piece already downloaded
        if os.path.exists(ts_path):
            return

        # files are downloaded to $TMP, then moved to final destination
        # takes 3:32 to download an hour long VOD to NAS, compared to 5:00 without using $TMP as download cache
        #   a better method would be to have 20 workers downloading, and 20 moving temp
        #   files from storage avoiding any downtime downloading

        # create temporary file for downloading to
        with open(Path(tempfile.gettempdir(), os.urandom(24).hex()), 'wb') as tmp_ts_file:
            for _ in range(6):
                if _ > 4:
                    self.log.debug(f'Maximum retries for segment {Path(ts_path).stem} reached.')
                    return f'Maximum retries for segment {Path(ts_path).stem} reached.'

                try:
                    _r = requests.get(ts_url, stream=True, timeout=10)

                    # break on non 200 status code
                    if _r.status_code != 200:
                        self.log.error('Code other than 200 received when trying to download segment.')
                        continue

                    # write downloaded chunks to temporary file
                    for chunk in _r.iter_content(chunk_size=1024):
                        tmp_ts_file.write(chunk)

                    self.log.debug(f'Segment {Path(ts_path).stem} download completed.')

                    break

                except requests.exceptions.RequestException as e:
                    self.log.debug(f'Segment {Path(ts_path).stem} download failed (Attempt {_ + 1}). {e})')
                    continue

        try:
            # move part to destination storage
            Utils.safe_move(tmp_ts_file.name, ts_path)
            self.log.debug(f'Segment {Path(ts_path).stem} completed.')

        except FileNotFoundError:
            raise VodPartDownloadError(f'MPEG-TS segment did not download correctly. Piece: {ts_url}')

        except Exception as e:
            self.log.error(f'Exception encountered while moving downloaded MPEG-TS segment {ts_url}.', exc_info=True)
            return e

    def get_chat(self, vod_json, offset=0):
        """Downloads the chat for a specified VOD, returning comments beginning from offset (if provided).

        :param vod_json: dict of vod information
        :param offset: offset in seconds to begin chat retrieval from - none to begin at start
        """
        chat_log = []

        _s = requests.session()
        _s.headers.update({'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko'})

        # grab initial chat segment containing cursor
        initial_segment, cursor = self.get_chat_segment(_s, vod_json['vod_id'], offset=offset)
        chat_log.extend(initial_segment)

        progress = Progress()

        while True:
            if not cursor:
                break

            try:
                # grab next chat segment along with cursor for next segment
                segment, cursor = self.get_chat_segment(_s, vod_json['vod_id'], cursor=cursor)
                chat_log.extend(segment)
                # vod duration in seconds is used as the total for progress bar
                # comment offset is used to track what's been done
                # could be done properly if there was a way to get the total number of comments
                if not self.quiet:
                    progress.print_progress(int(segment[-1]['content_offset_seconds']),
                                            vod_json['duration'], False if cursor else True)

            except TwitchAPIErrorNotFound:
                break

            finally:
                _s.close()

        self.log.info(f'Found {len(chat_log)} messages.')

        return chat_log

    @staticmethod
    def get_chat_segment(session, vod_id, offset=None, cursor=None):
        """Retrieves a single chat segment.

        :param session: requests session to link request to
        :param vod_id: id of vod to retrieve segment from
        :param offset: offset in seconds to begin retrieval from
        :param cursor: cursor returned by a previous call of this function
        :return: list of comments and cursor if one is returned from twitch
        """
        if not cursor or offset:
            u = f'https://api.twitch.tv/v5/videos/{vod_id}/comments?content_offset_seconds={offset}'

        else:
            u = f'https://api.twitch.tv/v5/videos/{vod_id}/comments?cursor={cursor}'

        _r = Api.get_request_with_session(u, session).json()

        try:
            return _r['comments'], _r['_next']

        except KeyError:
            return _r['comments'], None
