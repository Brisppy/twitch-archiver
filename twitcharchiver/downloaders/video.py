"""
Module used for downloading the video for a given Twitch VOD.
"""
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from math import floor
from pathlib import Path
from requests import adapters
from time import sleep

import m3u8
import requests

from twitcharchiver.api import Api
from twitcharchiver.downloader import Downloader
from twitcharchiver.twitch import MpegSegment
from twitcharchiver.exceptions import VodPartDownloadError, TwitchAPIErrorNotFound, TwitchAPIErrorForbidden, \
    VodDownloadError, VodConvertError, CorruptPartError, VodMergeError, VodVerificationError
from twitcharchiver.utils import Progress, safe_move, build_output_dir_name, get_hash, format_vod_chapters
from twitcharchiver.vod import Vod, ArchivedVod

# time in seconds between checking for new VOD parts if VOD is currently live and being updated
CHECK_INTERVAL = 60

# the number of times the check interval has to pass before a VOD is considered offline.
# the total time which must pass can be calculated as CHECK_INTERVAL * VOD_OFFLINE_TIME
VOD_OFFLINE_LOOPS = 10

class Video(Downloader):
    """
    Class used for downloading the video for a given Twitch VOD.
    """
    # class vars
    _api: Api = Api()
    _quality: str = ''

    def __init__(self, vod: Vod, parent_dir: Path = os.getcwd(), quality: str = 'best', threads: int = 20,
                 quiet: bool = False):
        """
        Class used for downloading the video for a given Twitch VOD.

        :param vod: VOD to be downloaded
        :param parent_dir: path to parent directory for downloaded files
        :param quality: quality to download in the format [resolution]p[framerate], or either 'best' or 'worst'
        :param quiet: boolean whether to print progress
        :param threads: number of worker threads to use when downloading
        """
        # init downloader
        super().__init__(parent_dir, quiet)

        self.threads = threads

        # set quality
        self.__setattr__('_quality', quality)

        # vod-specific vars
        self.vod: Vod = vod
        self.output_dir = Path(self._parent_dir,
                               build_output_dir_name(self.vod.title, self.vod.created_at, self.vod.v_id))

        # buffers and progress tracking
        # collect previously downloaded segments (if any)
        self._completed_segments: set[MpegSegment] = self.get_completed_segments(self.output_dir)
        self._muted_segments: set[MpegSegment] = set()

        # expand download https session pool
        self._s: requests.Session = requests.session()
        _a = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self._s.mount('https://', _a)

        # video segment containers and required params
        self._index_url: str = ""
        self._base_url: str = ""
        self._index_playlist: m3u8 = None
        self._prev_index_playlist: m3u8 = None

    @staticmethod
    def get_completed_segments(directory):
        """
        Fetches all segments which have been downloaded to the output directory.

        :param directory: directory containing *.ts files
        :type directory: str or Path
        :return: set of segments inside directory
        :rtype: set[MpegSegment]
        """
        return {MpegSegment(int(Path(p).name.removesuffix('.ts')), 10)
                for p in list(Path(directory, 'parts').glob('*.ts'))}

    def start(self, _q=None):
        """
        Begin downloading video segments for given VOD until all parts downloaded and stream has ended (if live).

        :param _q: multiprocessing queue used for returning the class after completion
        :type _q: multiprocessing.Queue
        """
        try:
            # create output directories
            Path(self.output_dir, 'parts').mkdir(parents=True, exist_ok=True)
            Path(tempfile.gettempdir(), 'twitch-archiver', str(self.vod.v_id)).mkdir(parents=True, exist_ok=True)

            # delay archival start for new vods (started less than 5m ago)
            _time_since_start = self.vod.time_since_live()
            if _time_since_start < 300:
                self._log.info('Delaying archival of VOD %s as VOD has been live for less than 5 minutes.',
                               self.vod.v_id)
                sleep(300 - _time_since_start)

            self._index_url = self.vod.get_index_url(self._quality)
            self._base_url = self._extract_base_url(self._index_url)

            # begin download
            self._download_loop()

            # put self into mp queue if provided
            if _q:
                _q.put(self, block=False)

            # set archival flag if ArchivedVod provided
            if isinstance(self.vod, ArchivedVod):
                self.vod.video_archived = True

        except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
            self._log.warning('HTTP code 403 or 404 encountered, VOD %s was likely deleted.', self.vod.v_id)
            with open(Path(self.output_dir, '.ignorelength'), 'w', encoding='utf8') as _:
                pass

            self.vod.status = 'offline'

        except Exception as exc:
            raise VodDownloadError(exc) from exc

    def refresh_playlist(self):
        """
        Fetch new segments for video (if any).
        """
        self._prev_index_playlist = self._index_playlist
        self._index_playlist = m3u8.loads(self.vod.get_index_playlist(self._index_url))

    def _download_loop(self):
        """
        Begin downloading segments, fetching new segments as they come out (if VOD live) until stream/VOD ends.
        """
        self.refresh_playlist()
        self.download_m3u8_playlist()

        # while VOD live, check for new parts every CHECK_INTERVAL seconds. if no new parts discovered after CHECK_INTERVAL * VOD_OFFLINE_TIME seconds, or error
        # returned when trying to check VOD status, stream is assumed to be offline and we break loop.
        while self.vod.is_live():
            for _ in range(VOD_OFFLINE_LOOPS + 1):
                if _ >= VOD_OFFLINE_LOOPS:
                    self._log.debug(f'{VOD_OFFLINE_LOOPS * CHECK_INTERVAL}s has passed since VOD duration changed - assuming it is no longer live.')
                    return

                # todo : find a way to confirm the VOD is offline so we dont needs to wait 10 minutes
                # if VOD is live check for new parts every 60s
                self._log.debug(f'Waiting {CHECK_INTERVAL}s to see if VOD changes.')
                sleep(CHECK_INTERVAL)

                try:
                    # refresh mpegts segment playlist
                    self.refresh_playlist()

                    # fetch downloaded files in-case being run in parallel with stream archiver so we don't try and
                    # download anything already completed
                    self._completed_segments = self.get_completed_segments(self.output_dir)

                    # if new segments found, download them
                    if len(self._prev_index_playlist.segments) < len(self._index_playlist.segments):
                        self._log.debug('New VOD parts found.')
                        self.download_m3u8_playlist()
                        # new segments downloaded - restart loop
                        break

                except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
                    self._log.debug(
                        'Error 403 or 404 returned when checking for new VOD parts - VOD was likely deleted.')
                    return

    @staticmethod
    def _extract_base_url(index_url: str):
        """
        Extracts a URL from which TS segment IDs are appended to generate the URL which segments are stored.

        :param index_url: index url used to create base url
        :return: base url for TS segments
        """
        _m = re.findall(r'(?<=\/)(index.*)', index_url)[0]
        return index_url.replace(_m, '')

    def download_m3u8_playlist(self):
        """Downloads the video for a specified m3u8 playlist.

        :raises vodPartDownloadError: error returned when downloading vod parts
        """
        _buffer: set[MpegSegment] = set()

        # process all segments in playlist
        for segment in [MpegSegment.convert_m3u8_segment(_s, self._base_url) for _s in self._index_playlist.segments]:
            # add segment to download buffer if it isn't completed
            if segment not in self._completed_segments:
                _buffer.add(segment)

            if segment.muted:
                self._muted_segments.add(segment)

        if _buffer:
            _worker_pool = ThreadPoolExecutor(max_workers=self.threads)
            download_error = []
            futures = []
            try:
                # add orders to worker pool
                for segment in _buffer:
                    futures.append(_worker_pool.submit(self._get_ts_segment, segment))

                progress = Progress()

                # complete orders in worker pool
                for future in futures:
                    if future.exception():
                        # append any returned errors
                        download_error.append(future.exception())

                    if not self._quiet:
                        progress.print_progress(
                            len(self._completed_segments), len(self._index_playlist.segments))

                if download_error:
                    raise VodPartDownloadError(download_error)

            except KeyboardInterrupt as exc:
                self._log.debug('M3U8 playlist downloader caught interrupt, shutting down workers...')
                _worker_pool.shutdown(wait=False, cancel_futures=True)
                raise KeyboardInterrupt from exc

            finally:
                _worker_pool.shutdown(wait=False, cancel_futures=True)

    def _get_ts_segment(self, segment: MpegSegment):
        """Retrieves a specific ts file.

        :param segment: MPEGTS segment to download
        :type segment: Segment
        :return: error on failure
        :rtype: str
        """
        _segment_path = segment.generate_path(Path(self.output_dir, 'parts'))
        self._log.debug('Downloading segment %s to %s', segment.url, _segment_path)

        # don't bother if piece already downloaded
        if os.path.exists(_segment_path):
            return

        # files are downloaded to $TMP, then moved to final destination
        # takes 3:32 to download an hour long VOD to NAS, compared to 5:00 without using $TMP as download cache
        #   a better method would be to have 20 workers downloading, and 20 moving temp
        #   files from storage avoiding any downtime downloading

        # create temporary file for downloading to
        with (open(Path(tempfile.gettempdir(), 'twitch-archiver', str(self.vod.v_id), f'{segment.id}.ts'), 'wb')
              as _tmp_ts_file):
            for _ in range(6):
                if _ > 4:
                    raise VodPartDownloadError(f'Maximum retries for segment {segment.id} reached.')

                try:
                    _r = self._s.get(segment.url, stream=True, timeout=10)

                    # break on non 200 status code
                    if _r.status_code != 200:
                        self._log.error('HTTP status %s received. %s', _r.status_code, _r.text)
                        continue

                    # write downloaded chunks to temporary file
                    for _chunk in _r.iter_content(chunk_size=262144):
                        _tmp_ts_file.write(_chunk)

                    self._log.debug('Segment %s download completed.', Path(_segment_path).stem)
                    self._completed_segments.add(segment)

                    break

                except requests.exceptions.RequestException as exc:
                    self._log.debug('Segment %s download failed (Attempt %s). Error: %s)',
                                    Path(_segment_path).stem, _ + 1, str(exc))
                    continue

        try:
            # move part to destination storage
            safe_move(_tmp_ts_file.name, _segment_path)
            self._log.debug('Segment %s completed and moved to %s.', Path(_segment_path).stem, _segment_path)

        except FileNotFoundError as exc:
            raise VodPartDownloadError(f'MPEG-TS segment did not download correctly. Piece: {segment.url}') from exc

        except Exception as exc:
            raise VodPartDownloadError(
                f'Exception encountered while moving downloaded MPEG-TS segment {segment.id}.') from exc

    def repair_vod_corruptions(self, corruption: list[MpegSegment]):
        """
        Repairs segments which have been declared as corrupt by VOD merger.

        :param corruption: list of corrupt MpegSegments retrieved from CorruptVodError exception.
        """
        # check vod still available
        if not self._index_url:
            raise VodDownloadError(
                "Corrupt segments were found while converting VOD and TA was unable to re-download the missing "
                "segments. Either re-download the VOD if it is still available, or manually convert 'merged.ts' using "
                f"FFmpeg. Corrupt parts:\n{str(sorted(corruption))}")

        # rename corrupt segments
        for segment in corruption:
            # convert segment number to segment file
            segment_fp = str(f'{segment.id:05d}' + '.ts')

            # rename part
            shutil.move(Path(self.output_dir, 'parts', segment_fp),
                        Path(self.output_dir, 'parts', segment_fp + '.corrupt'))

            # remove from completed segments
            self._completed_segments.remove(segment)

        # download and combine vod again
        try:
            self.refresh_playlist()
            self.download_m3u8_playlist()

            # compare downloaded .ts to corrupt parts - corrupt parts SHOULD have different hashes,
            # so we can work out if a segment is corrupt on twitch's end or ours
            for segment in corruption:
                segment_fp = str(f'{segment.id:05d}' + '.ts')

                # compare hash of redownloaded segment and corrupt one
                try:
                    if get_hash(Path(self.output_dir, 'parts', segment_fp)) == \
                            get_hash(Path(self.output_dir, 'parts', segment_fp + '.corrupt')):
                        self._log.debug("Re-downloaded .ts segment %s matches corrupt one, "
                                        "assuming corruption is on Twitch's end and ignoring.", segment.id)
                        segment.muted = True
                        self._muted_segments.add(segment)

                    else:
                        self._log.error('Re-downloaded .ts segment %s does not match corrupt one.')

                # occasionally the last few pieces of a stream may not be archived to the VOD and so won't be
                # re-downloaded. instead we just assume the corrupt segment is OK.
                except FileNotFoundError:
                    self._log.debug("Segment %s could not be re-downloaded - it may no longer be available so the "
                                    "potentially corrupt segment will be used.")
                    shutil.move(Path(self.output_dir, 'parts', segment_fp + '.corrupt'),
                                Path(self.output_dir, 'parts', segment_fp))
                    segment.muted = True
                    self._muted_segments.add(segment)

        except CorruptPartError as exc:
            raise VodDownloadError(
                "Corrupt part(s) still present after retrying VOD download. Ensure VOD is still "
                "available and either delete the listed #####.ts part(s) from 'parts' folder or entire "
                f"'parts' folder if issue persists.\n{str(sorted(corruption))}") from exc

    def merge(self):
        """
        Attempt to merge downloaded VOD parts and verify them.
        """
        merger = Merger(self.vod, self.output_dir, self._completed_segments, self._muted_segments, self._quiet)

        # attempt to merge
        try:
            merger.merge()

        # corrupt part(s) encountered - redownload them and reattempt merge
        except CorruptPartError as _c:
            self.repair_vod_corruptions(_c.parts)
            merger.merge()

        except Exception as exc:
            raise VodMergeError('Exception raised while merging VOD.') from exc

        # verify VOD based on its length
        if merger.verify_length():
            merger.cleanup_temp_files()

        else:
            raise VodMergeError('VOD verification failed as VOD length is outside the acceptable range.')

    def cleanup_temp_files(self):
        """
        Deletes temporary and transitional files used for archiving VOD video.
        """
        self._log.debug('Deleting VOD parts - this may take a while.')
        shutil.rmtree(Path(self.output_dir, 'parts'), ignore_errors=True)
        shutil.rmtree(Path(tempfile.gettempdir(), 'twitch-archiver', str(self.vod.v_id)), ignore_errors=True)


class Merger:
    """
    Class used for merging downloaded .ts segments into a single file and performing verification.
    """
    _log = logging.getLogger()
    _api = Api()

    def __init__(self, vod, output_dir, completed_segments, muted_segments, quiet):
        """
        Class constructor.
        """
        self.vod = vod
        self._output_dir = output_dir
        self._completed_segments = completed_segments
        self._completed_parts = self.get_completed_parts()
        self._muted_segment_ids = [s.id for s in muted_segments]
        self._quiet = quiet

    def merge(self):
        """
        Merges downloaded TS segments into a single .mp4

        :raises CorruptPartError: when corruptions are found outside muted segments
        :raises VodConvertError: unrecoverable error ocurred when trying to convert VOD
        """
        # export vod chapters
        self._write_chapters()

        # export vod thumbnail
        if self.vod.thumbnail_url:
            self._write_thumbnail()

        # merge and remux mpegts segments to single mp4
        self._log.info('Merging VOD parts. This may take a while.')
        self._combine_vod_parts()

        self._log.info('Converting VOD to mp4. This may take a while.')
        self._convert_vod()

    def _write_chapters(self):
        # retrieve vod chapters
        try:
            vod_chapters = self.vod.get_chapters()
            # write chapters to file
            with open(Path(self._output_dir, 'chapters.json'), 'w', encoding='utf8') as chapters_file:
                chapters_file.write(str(vod_chapters))

            # format and write vod chapters to parts dir
            with open(Path(self._output_dir, 'parts', 'chapters.txt'), 'w', encoding='utf8') as chapters_file:
                chapters_file.write(str(format_vod_chapters(vod_chapters)))

        except Exception as exc:
            self._log.error('Failed to retrieve or insert chapters into VOD file. %s', exc)

    def _combine_vod_parts(self):
        """
        Combines the downloaded VOD .ts parts.
        """
        _progress = Progress()

        # concat files if all pieces present, otherwise fall back to using ffmpeg
        _final_part_id = max([_s.id for _s in self._completed_segments])

        _dicontinuity = \
            set([i for i in range(_final_part_id + 1)]).difference([_s.id for _s in self._completed_segments])
        if not _dicontinuity:
            # merge all .ts files by concatenating them
            with open(str(Path(self._output_dir, 'merged.ts')), 'wb') as _merged_file:
                _pt = 0
                for _part in self._completed_parts:
                    _pt += 1
                    # append part to merged file
                    with open(Path(self._output_dir, 'parts', _part), 'rb') as _ts_part:
                        shutil.copyfileobj(_ts_part, _merged_file)

                    if not self._quiet:
                        _progress.print_progress(_pt, len(self._completed_segments))

        else:
            # merge all .ts files with ffmpeg concat demuxer as missing segments can cause corruption with
            # other method

            self._log.debug('Discontinuity found, merging with ffmpeg.\n Discontinuity: %s', _dicontinuity)

            # create file with list of parts for ffmpeg
            with open(Path(self._output_dir, 'parts', 'segments.txt'), 'w', encoding='utf8') as _segment_file:
                for _part in self._completed_parts:
                    _segment_file.write(f"file '{_part}'\n")

            with subprocess.Popen(f'ffmpeg -hide_banner -fflags +genpts -f concat -safe 0 -y -i '
                                  f'"{str(Path(self._output_dir, "parts", "segments.txt"))}"'
                                  f' -c copy "{str(Path(self._output_dir, "merged.ts"))}"',
                                  shell=True, stderr=subprocess.PIPE, universal_newlines=True, encoding='cp437') as _p:
                # get progress from ffmpeg output and print progress bar
                if not self._quiet:
                    for _line in _p.stderr:
                        if 'time=' in _line.rstrip():
                            # extract current timestamp from output
                            _cur_time = re.search('(?<=time=).*(?= bitrate=)', _line).group(0).split(':')
                            _cur_time = int(_cur_time[0]) * 3600 + int(_cur_time[1]) * 60 + int(_cur_time[2][:2])

                            _progress.print_progress(int(_cur_time), self.vod.duration)

                if _p.returncode:
                    self._log.error('VOD merger exited with error. Command: %s.', _p.args)
                    raise VodConvertError(f'VOD merger exited with error. Command: {_p.args}.')

    def _convert_vod(self):
        """Converts the VOD from a .ts format to .mp4.

        :raises vodConvertError: error encountered during conversion process
        """
        _progress = Progress()
        _corrupt_parts: set[MpegSegment] = set()

        # get dts offset of first part
        _dts_offset = self._get_dts_offset()

        # create ffmpeg command
        _ffmpeg_cmd = f'ffmpeg -hide_banner -y -i "{Path(self._output_dir, "merged.ts")}" '
        # insert metadata if present
        if Path(self._output_dir, 'parts', 'chapters.txt').exists():
            _ffmpeg_cmd += f'-i "{Path(self._output_dir, "parts", "chapters.txt")}" -map_metadata 1 '

        _ffmpeg_cmd += f'-c:a copy -c:v copy "{Path(self._output_dir, "vod.mp4")}"'

        # convert merged .ts file to .mp4
        with subprocess.Popen(_ffmpeg_cmd, shell=True, stderr=subprocess.PIPE, universal_newlines=True,
                              encoding='cp437') as _p:
            # get progress from ffmpeg output and catch corrupt segments
            _ffmpeg_log = ''
            for line in _p.stderr:
                _ffmpeg_log += line.rstrip()
                if 'time=' in line:
                    # extract current timestamp from output
                    _cur_time = re.search(r'(?<=time=).*(?= bitrate=)', line).group(0).split(':')
                    _cur_time = int(_cur_time[0]) * 3600 + int(_cur_time[1]) * 60 + int(_cur_time[2][:2])

                    if not self._quiet:
                        _progress.print_progress(int(_cur_time), self.vod.duration)

                elif 'Packet corrupt' in line:
                    try:
                        _dts_timestamp = int(re.search(r'(?<=dts = ).*(?=\).)', line).group(0))

                    # Catch corrupt parts without timestamp, shows up as 'NOPTS'
                    except ValueError as exc:
                        raise VodConvertError("Corrupt packet encountered at unknown timestamp while converting VOD. "
                                              "Delete 'parts' folder and re-download VOD.") from exc

                    _corrupt_part = MpegSegment(floor((_dts_timestamp - _dts_offset) / 90000 / 10), 10)

                    # ignore if corrupt packet within ignore_corruptions range
                    if _corrupt_part.id in self._muted_segment_ids:
                        _corrupt_part.muted = True
                        self._log.debug('Ignoring corrupt packet as part in whitelist. Part: %s', _corrupt_part)

                    else:
                        _corrupt_parts.add(_corrupt_part)
                        self._log.error('Corrupt packet encountered. Part: %s', _corrupt_part)

        if _p.returncode:
            self._log.debug('FFmpeg exited with error code, output dumped to VOD directory.')
            with open(Path(self._output_dir, 'parts', 'ffmpeg.log'), 'w', encoding='utf8') as _ffout:
                _ffout.write(_ffmpeg_log)

            raise VodConvertError("VOD converter exited with error. Delete 'parts' directory and re-download VOD.")

        if _corrupt_parts:
            # raise error so we can try to recover
            raise CorruptPartError(_corrupt_parts)

    def _get_dts_offset(self):
        with subprocess.Popen(f'ffprobe -v quiet -print_format json -show_format -show_streams '
                              f'"{Path(self._output_dir, "parts", "00000.ts")}"', shell=True,
                              stdout=subprocess.PIPE, universal_newlines=True, encoding='cp437') as _p:
            _ts_file_data = ''
            for _line in _p.stdout:
                _ts_file_data += _line.rstrip()

            return float(json.loads(_ts_file_data)['format']['start_time']) * 90000

    def verify_length(self):
        """Verifies the length of the downloaded VOD.

        :return: True if VOD length within the acceptable range
        :rtype: bool
        :raises VodVerificationError: if error occurs when verifying
        """
        self._log.debug('Verifying length of VOD file.')

        # skip verification if .ignorelength present
        if Path(self._output_dir, '.ignorelength').is_file():
            self._log.debug('.ignorelength file present - skipping verification.')
            return True

        # retrieve vod file duration
        _p = subprocess.run(f'ffprobe -v quiet -i "{Path(self._output_dir, "vod.mp4")}" '
                            f'-show_entries format=duration -of default=noprint_wrappers=1:nokey=1',
                            shell=True, capture_output=True, encoding='cp437')

        if _p.returncode:
            raise VodVerificationError(f'VOD length verification exited with error. Command: {_p.args}.')

        try:
            downloaded_length = int(float(_p.stdout.rstrip()))

        except Exception as exc:
            raise VodVerificationError('Failed to fetch downloaded VOD length. See log for details.') from exc

        self._log.debug('Downloaded VOD length is %s. Expected length is %s.', downloaded_length, self.vod.duration)

        # pass verification if downloaded file is within 2s of expected length
        if 2 >= downloaded_length - self.vod.duration >= -2:
            return True

        return False

    def _write_thumbnail(self):
        """
        Downloads and stores the thumbnail for the VOD.
        """
        try:
            self._log.debug('Downloading VOD thumbnail.')
            thumbnail = self._api.get_request(self.vod.thumbnail_url.replace('%{width}x%{height}', '1920x1080'))
            with open(Path(self._output_dir, 'thumbnail.jpg'), 'wb') as thumbnail_file:
                thumbnail_file.write(thumbnail.content)

        except Exception as exc:
            self._log.error('Failed to grab thumbnail for VOD. Error: %s', str(exc))

    def get_completed_parts(self):
        """
        Generates a list of segments based on the completed IDs.

        :return: list of segments padded to 5 digits with .ts extension
        """
        return [f'{seg.id:05d}.ts' for seg in self._completed_segments]

    def cleanup_temp_files(self):
        """
        Deletes temporary and transitional files used for archiving VOD video.
        """
        Path(self._output_dir, 'merged.ts').unlink()
