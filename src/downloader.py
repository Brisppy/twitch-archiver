from glob import glob
import logging
import os
import requests
import shutil
import tempfile

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.api import Api
from src.exceptions import VodPartDownloadError, TwitchAPIErrorNotFound
from src.utils import Progress


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

        self.log = logging.getLogger('twitch-archive')

        self.client_id = client_id
        self.oauth_token = oauth_token

        self.threads = threads
        self.quiet = quiet

    def get_video(self, vod_playlist, vod_base_url, vod_json):
        """Downloads the video for a specified VOD m3u8 playlist.

        :param vod_playlist: m3u8 playlist to retrieve video from
        :param vod_base_url: base url of where .ts files are located
        :param vod_json: dict of vod information
        :raises vodPartDownloadError: error returned when downloading vod parts
        """
        self.log.info('Downloading video for VOD ' + str(vod_json['id']))

        Path(vod_json['store_directory'], 'parts').mkdir(parents=True, exist_ok=True)

        ts_url_list = []
        ts_path_list = []
        downloaded_ids = [str(Path(p).name).lstrip('0')
                          for p in glob(str(Path(vod_json['store_directory'], 'parts', '*.ts')))]

        # iterate over segments of vod .m3u8 playlist
        for ts_id in [s.uri for s in vod_playlist.segments]:
            if ts_id not in downloaded_ids:
                # create a tuple with (TS_URL, TS_PATH)
                ts_url_list.append(vod_base_url + ts_id)
                ts_path_list.append(Path(vod_json['store_directory'], 'parts',
                                         str('{:05d}'.format(int(ts_id.split('.')[0])) + '.ts')))

        # create worker pool for downloading vods
        with ThreadPoolExecutor(max_workers=self.threads) as pool:
            download_error = []
            futures = []
            ct = 0
            # append work orders along with args to queue
            for ts_url, ts_path in zip(ts_url_list, ts_path_list):
                futures.append(pool.submit(self.get_vod_part, ts_url, ts_path))

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

    def get_vod_part(self, ts_url, ts_path):
        """Retrieves a specific ts file.

        :param ts_url: url of .ts file to download
        :param ts_path: destination path for .ts file after downloading
        """
        # don't bother if piece already downloaded
        try:
            if os.path.exists(ts_path):
                return

        # files are downloaded to $TMP, then moved to final destination
        # takes 3:32 to download an hour long VOD to NAS, compared to 5:00 without using $TMP as download cache
        #   a better method would be to have 20 workers downloading, and 20 moving temp
        #   files from storage avoiding any downtime downloading

            # create temporary file for downloading to
            with open(Path(tempfile.gettempdir(), os.urandom(24).hex()), 'wb') as tmp_ts_file:
                for attempt in range(6):
                    if attempt > 4:
                        self.log.debug('Maximum retries reach for VOD part download.')
                        return 'Download attempt limit reached.'

                    try:
                        _r = requests.get(ts_url, stream=True)

                        # break on non 200 status code
                        if _r.status_code != 200:
                            self.log.error('Code other than 200 received when trying to download VOD part.')
                            break

                        # write downloaded chunks to temporary file
                        for chunk in _r.iter_content(chunk_size=1024):
                            tmp_ts_file.write(chunk)

                        break

                    except requests.exceptions.ChunkedEncodingError as e:
                        self.log.debug('Error downloading VOD part, retrying. ' + str(e))
                        continue

            # move part to destination storage
            if Path(tmp_ts_file.name).exists:
                # first move to temp file
                shutil.move(tmp_ts_file.name, ts_path.with_suffix('.tmp'))
                # rename temp file after it has successfully been moved
                os.rename(ts_path.with_suffix('.tmp'), ts_path)

            else:
                raise VodPartDownloadError('VOD part did not download correctly. Part: ' + str(ts_url))

        except Exception as e:
            return e

    def get_chat(self, vod_json, offset=0):
        """Downloads the chat for a specified VOD, returning comments beginning from offset (if provided).

        :param vod_json: dict of vod information
        :param offset: offset in seconds to begin chat retrieval from - none to begin at start
        """
        Path(vod_json['store_directory']).mkdir(parents=True, exist_ok=True)

        chat_log = []

        _s = requests.session()
        _s.headers.update({'Authorization': 'Bearer ' + self.oauth_token,
                           'Client-Id': self.client_id})

        # grab initial chat segment containing cursor
        initial_segment, cursor = self.get_chat_segment(_s, vod_json['id'], offset=offset)
        chat_log.extend(initial_segment)

        progress = Progress()

        while True:
            if not cursor:
                break

            try:
                # grab next chat segment along with cursor for next segment
                segment, cursor = self.get_chat_segment(_s, vod_json['id'], cursor=cursor)
                chat_log.extend(segment)
                # vod duration in seconds is used as the total for progress bar
                # comment offset is used to track what's been done
                # could be done properly if there was a way to get the total number of comments
                if not self.quiet:
                    progress.print_progress(int(segment[-1]['content_offset_seconds']), vod_json['duration_seconds'])

            except TwitchAPIErrorNotFound:
                break

            finally:
                _s.close()

        self.log.info('Found ' + str(len(chat_log)) + ' messages.')

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
            u = "https://api.twitch.tv/v5/videos/" + str(vod_id) + "/comments?content_offset_seconds=" + str(offset)

        else:
            u = "https://api.twitch.tv/v5/videos/" + str(vod_id) + "/comments?cursor=" + str(cursor)

        _r = Api.get_request_with_session(u, session).json()

        try:
            return _r['comments'], _r['_next']

        except KeyError:
            return _r['comments'], None
