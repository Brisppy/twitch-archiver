"""
Module used for downloading the video for a given Twitch VOD.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from glob import glob
from math import floor
from pathlib import Path
from time import sleep

import m3u8
import requests

from twitcharchiver.api import Api
from twitcharchiver.downloader import Downloader
from twitcharchiver.twitch import MpegSegment
from twitcharchiver.exceptions import VodPartDownloadError, TwitchAPIErrorNotFound, TwitchAPIErrorForbidden, \
    VodDownloadError, VodConvertError, CorruptPartError, VodMergeError
from twitcharchiver.utils import Progress, safe_move, build_output_dir_name, get_hash, format_vod_chapters
from twitcharchiver.vod import Vod


class Video(Downloader):
    """
    Class used for downloading the video for a given Twitch VOD.
    """
    # class vars
    _api: Api = Api()
    _quality: str = ''
    _s: requests.Session = requests.session()

    def __init__(self, vod: Vod, parent_dir: Path = os.getcwd(), quality: str = 'best', quiet: bool = False,
                 threads: int = 20):
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

        # downloader pool
        self._worker_pool = ThreadPoolExecutor(max_workers=threads)

        # set quality
        self.__setattr__('quality', quality)

        # buffers and progress tracking
        self._completed_segments: set[MpegSegment] = set()
        self._muted_segments: set[MpegSegment] = set()

        # vod-specific vars
        self.output_dir: Path = None
        self.vod: Vod = vod

        # perform various setup tasks
        self._do_setup()

    def _do_setup(self):
        # create output dir and temporary buffer dir
        self.output_dir = build_output_dir_name(self.vod.title, self.vod.created_at, self.vod.v_id)
        Path(self.output_dir, 'parts').mkdir(parents=True, exist_ok=True)
        Path(tempfile.gettempdir(), 'twitch-archiver', str(self.vod.v_id)).mkdir(parents=True, exist_ok=True)

        # collect previously downloaded segments (if any)
        self._completed_segments.update(set([MpegSegment(int(Path(p).name.removesuffix('.ts')), 10)
                                             for p in glob(str(Path(self.output_dir, 'parts', '*.ts')))]))

        # delay archival start for new vods (started less than 5m ago)
        _time_since_start = self.vod.time_since_live()
        if _time_since_start < 300:
            self._log.info('Delaying archival of VOD %s as VOD has been live for less than 5 minutes.', self.vod.v_id)
            sleep(300 - _time_since_start)

    def download(self):
        """Starts download the given VOD."""
        try:
            # begin download
            self._download_loop()

            # merge mpegts segments and convert to mp4
            self._merge()
            self._get_thumbnail()

        except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
            self._log.warning('HTTP code 403 or 404 encountered, VOD %s was likely deleted.', self.vod.v_id)
            with open(Path(self.output_dir, '.ignorelength'), 'w', encoding='utf8') as _:
                pass

            self.vod.status = 'offline'

        except BaseException as e:
            raise VodDownloadError(e) from e

    def _get_thumbnail(self):
        """
        Downloads and stores the thumbnail for the VOD.
        """
        try:
            self._log.debug('Downloading VOD thumbnail.')
            thumbnail = Api.get_request(self.vod.thumbnail_url.replace('%{width}x%{height}', '1920x1080'))
            with open(Path(self.output_dir, 'thumbnail.jpg'), 'wb') as thumbnail_file:
                thumbnail_file.write(thumbnail.content)

        except BaseException as e:
            self._log.error('Failed to grab thumbnail for VOD. Error: %s', str(e))

    def _merge(self):
        """
        Merges downloaded TS segments into a single .mp4
        """
        try:
            # export vod chapters
            self._write_chapters()

            # merge and remux mpegts segments to single mp4
            self._log.info('Merging VOD parts. This may take a while.')
            self._combine_vod_parts()

            self._log.info('Converting VOD to mp4. This may take a while.')
            self._convert_vod()

        except CorruptPartError as c:
            self._log.error("Corrupt segments found while converting VOD. Attempting to retry parts:"
                           "\n%s", ', '.join([str(p) for p in c.parts]))

            self._repair_vod_corruptions(c)

        except BaseException as e:
            raise VodMergeError(e) from e

        self._log.info('Verifying length of the downloaded VOD and cleaning up temporary files.')
        if self.verify_length():
            self._cleanup_temp_files()

        else:
            raise VodMergeError('VOD length outside of acceptable range. If error persists delete '
                                "'vod/parts' directory if VOD still available.")

    def _repair_vod_corruptions(self, corruption):
        # check vod still available
        # todo: test if this works, originally called get_index_playlist()
        if not self.vod.get_index_url(self._quality):
            raise VodDownloadError("Corrupt segments were found while converting VOD and TA was "
                                   "unable to re-download the missing segments. Either re-download "
                                   "the VOD if it is still available, or manually convert 'merged.ts' "
                                   f"using FFmpeg. Corrupt parts:\n{', '.join(corruption.f_parts)}")

        # rename corrupt segments
        for part in corruption.parts:
            # convert part number to segment file
            part = str(f'{int(part):05d}' + '.ts')

            # rename part
            shutil.move(Path(self.output_dir, 'parts', part),
                        Path(self.output_dir, 'parts', part + '.corrupt'))

        # download and combine vod again
        try:
            _index_playlist = m3u8.loads(self.vod.get_index_playlist(self.vod.get_index_url()))
            self._get_m3u8_video(_index_playlist)

            # compare downloaded .ts to corrupt parts - corrupt parts SHOULD have different hashes
            # so we can work out if a segment is corrupt on twitch's end or ours
            for part_num in corruption.parts:
                part = str(f'{int(part_num):05d}' + '.ts')

                # compare hashes
                if get_hash(Path(self.output_dir, 'parts', part)) == \
                        get_hash(Path(self.output_dir, 'parts', part + '.corrupt')):
                    self._log.debug(f"Re-downloaded .ts segment %s matches corrupt one, "
                                   "assuming corruption is on Twitch's end and ignoring.", part_num)
                    self._muted_segments.add(MpegSegment(part_num, muted=True))

            self._merge()

        except CorruptPartError as e:
            raise VodDownloadError(
                "Corrupt part(s) still present after retrying VOD download. Ensure VOD is still "
                "available and either delete the listed #####.ts part(s) from 'parts' folder or entire "
                f"'parts' folder if issue persists.\n{', '.join(c.f_parts)}") from e

    def _write_chapters(self):
        # retrieve vod chapters
        try:
            vod_chapters = self.vod.get_chapters()
            # write chapters to file
            with open(Path(self.output_dir, 'chapters.json'), 'w', encoding='utf8') as chapters_file:
                chapters_file.write(json.dumps(vod_chapters))

            # format and write vod chapters to parts dir
            with open(Path(self.output_dir, 'parts', 'chapters.txt'), 'w', encoding='utf8') as chapters_file:
                chapters_file.write(format_vod_chapters(vod_chapters))

        except BaseException as e:
            self._log.error('Failed to retrieve or insert chapters into VOD file. %s', e)

    def get_completed_parts(self):
        """
        Generates a list of segments based on the completed IDs.

        :return: list of segments padded to 5 digits with .ts extension
        """
        return [f'{_id:05d}' for _id in self._completed_segments]

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
            with open(str(Path(self.output_dir, 'merged.ts')), 'wb') as _merged_file:
                _pt = 0
                for _part in self.get_completed_parts():
                    _pt += 1
                    # append part to merged file
                    with open(_part, 'rb') as _ts_part:
                        shutil.copyfileobj(_ts_part, _merged_file)

                    if not self._quiet:
                        _progress.print_progress(_pt, len(self._completed_segments))

        else:
            # merge all .ts files with ffmpeg concat demuxer as missing segments can cause corruption with
            # other method

            self._log.debug('Discontinuity found, merging with ffmpeg.\n Discontinuity: %s', _dicontinuity)

            # create file with list of parts for ffmpeg
            with open(Path(self.output_dir, 'parts', 'segments.txt'), 'w', encoding='utf8') as _segment_file:
                for _part in self.get_completed_parts():
                    _segment_file.write(f"file '{_part}'\n")

            with subprocess.Popen(f'ffmpeg -hide_banner -fflags +genpts -f concat -safe 0 -y -i '
                                  f'"{str(Path(self.output_dir, "parts", "segments.txt"))}"'
                                  f' -c copy "{str(Path(self.output_dir, "merged.ts"))}"',
                                  shell=True, stderr=subprocess.PIPE, universal_newlines=True) as _p:
                # get progress from ffmpeg output and print progress bar
                if not self._quiet:
                    for _line in _p.stderr:
                        if 'time=' in _line:
                            # extract current timestamp from output
                            _cur_time = re.search('(?<=time=).*(?= bitrate=)', _line).group(0).split(':')
                            _cur_time = \
                                int(_cur_time[0]) * 3600 + int(_cur_time[1]) * 60 + int(_cur_time[2][:2])

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
        _ffmpeg_cmd = f'ffmpeg -hide_banner -y -i "{Path(self.output_dir, "merged.ts")}" '
        # insert metadata if present
        if Path(self.output_dir, 'parts', 'chapters.txt').exists():
            _ffmpeg_cmd += f'-i "{Path(self.output_dir, "parts", "chapters.txt")}" -map_metadata 1 '

        _ffmpeg_cmd += f'-c:a copy -c:v copy "{Path(self.output_dir, "vod.mp4")}"'

        # convert merged .ts file to .mp4
        with subprocess.Popen(_ffmpeg_cmd, shell=True, stderr=subprocess.PIPE, universal_newlines=True) as _p:
            # get progress from ffmpeg output and catch corrupt segments
            _ffmpeg_log = ''
            for line in _p.stderr:
                _ffmpeg_log += line
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
                    except ValueError as e:
                        raise VodConvertError("Corrupt packet encountered at unknown timestamp while converting VOD. "
                                              "Delete 'parts' folder and re-download VOD.") from e

                    _corrupt_part = MpegSegment(floor((_dts_timestamp - _dts_offset) / 90000 / 10), 10)

                    # ignore if corrupt packet within ignore_corruptions range
                    if _corrupt_part in self._muted_segments:
                        self._log.debug('Ignoring corrupt packet as part in whitelist. Part: %s', _corrupt_part)

                    else:
                        _corrupt_parts.add(_corrupt_part)
                        self._log.error('Corrupt packet encountered. Part: %s', _corrupt_part)

        if _p.returncode:
            self._log.debug('FFmpeg exited with error code, output dumped to VOD directory.')
            with open(Path(self.output_dir, 'parts', 'ffmpeg.log'), 'w', encoding='utf8') as _ffout:
                _ffout.write(_ffmpeg_log)

            raise VodConvertError("VOD converter exited with error. Delete 'parts' directory and re-download VOD.")

        if _corrupt_parts:
            # raise error so we can try to recover
            raise CorruptPartError(_corrupt_parts)

    def _get_dts_offset(self):
        with subprocess.Popen(f'ffprobe -v quiet -print_format json -show_format -show_streams '
                              f'"{Path(self.output_dir, "parts", "00000.ts")}"', shell=True,
                              stdout=subprocess.PIPE, universal_newlines=True) as _p:
            _ts_file_data = ''
            for _line in _p.stdout:
                str.join(_ts_file_data, _line)

            return float(json.loads(_ts_file_data)['format']['start_time']) * 90000

    def _download_loop(self):
        _index_playlist = m3u8.loads(self.vod.get_index_playlist(self.vod.get_index_url()))

        while True:
            # refresh mpegts segment playlist
            _prev_index_playlist = _index_playlist
            _index_playlist = m3u8.loads(self.vod.get_index_playlist(self.vod.get_index_url()))

            self._get_m3u8_video(_index_playlist)

            # if the vod is live we check every minute for new parts.
            #   if new parts are found, we go back and download them
            #   if 10 minutes passes without new parts, or we receive a 403 or 404, the stream is over / deleted, and
            #     so we download any remaining parts then return
            if self.vod.status == 'live':
                for _ in range(11):
                    self._log.debug('Waiting 60s to see if VOD changes.')
                    sleep(60)
                    try:
                        if len(_prev_index_playlist.segments < len(_index_playlist)):
                            self._log.debug('New VOD parts found.')
                            self.vod.status = 'live'
                            break

                        if _ > 9:
                            self._log.debug('10m has passed since VOD duration changed - assuming it is no longer live.')
                            self.vod.status = 'archive'

                        else:
                            continue

                    except (TwitchAPIErrorNotFound, TwitchAPIErrorForbidden):
                        self._log.debug('Error 403 or 404 returned when checking for new VOD parts - VOD was likely'
                                       ' deleted.')
                        self.vod.status = 'archive'
                        break

            # vod is not live, download complete
            else:
                break

    def _extract_base_url(self):
        _index_url = self.vod.get_index_url()
        _m = re.findall(r'(?<=\/)(index.*)', _index_url)[0]
        return _index_url.replace(_m, '')

    def _get_m3u8_video(self, index_playlist: m3u8):
        """Downloads the video for a specified m3u8 playlist.

        :param index_playlist: m3u8 playlist retrieved from Twitch
        :type index_playlist: m3u8
        :raises vodPartDownloadError: error returned when downloading vod parts
        """
        _buffer: set[MpegSegment] = set()

        # process all segments in playlist
        for segment in [MpegSegment.convert_m3u8_segment(_s) for _s in index_playlist.segments]:
            # add segment to download buffer if it isn't completed
            if segment not in self._completed_segments:
                _buffer.add(segment)

                if segment.muted:
                    self._muted_segments.add(segment)

        if _buffer:
            download_error = []
            futures = []
            # add orders to worker pool
            for segment in _buffer:
                futures.append(self._worker_pool.submit(self._get_ts_segment, segment))

            progress = Progress()

            # complete orders in worker pool
            for future in futures:
                if future.result():
                    # append any returned errors
                    download_error.append(future.result())
                    continue

                if not self._quiet:
                    progress.print_progress(
                        len(self._completed_segments), len(index_playlist.segments))

            if download_error:
                raise VodPartDownloadError(download_error)

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
        with open(Path(tempfile.gettempdir(), 'twitch-archiver', str(self.vod.v_id)), 'wb') as _tmp_ts_file:
            for _ in range(6):
                if _ > 4:
                    self._log.debug('Maximum retries for segment %s reached.', Path(_segment_path).stem)
                    return f'Maximum retries for segment {Path(_segment_path).stem} reached.'

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

                except requests.exceptions.RequestException as e:
                    self._log.debug('Segment %s download failed (Attempt %s). Error: %s)',
                                    Path(_segment_path).stem, _ + 1, str(e))
                    continue

        try:
            # move part to destination storage
            safe_move(_tmp_ts_file.name, _segment_path)
            self._log.debug('Segment %s completed and moved to %s.', Path(_segment_path).stem, _segment_path)

        except FileNotFoundError as e:
            raise VodPartDownloadError(f'MPEG-TS segment did not download correctly. Piece: {segment.url}') from e

        except BaseException as e:
            self._log.error('Exception encountered while moving downloaded MPEG-TS segment %s.', segment.url,
                            exc_info=True)
            return e

        return

    def verify_length(self):
        """Verifies the length of the downloaded VOD.

        :return: True if verification passed
        :rtype: bool
        """
        self._log.debug('Verifying length of VOD file.')

        # skip verification if .ignorelength present
        if Path(self.output_dir, '.ignorelength').is_file():
            self._log.debug('.ignorelength file present - skipping verification.')
            return False

        # retrieve vod file duration
        p = subprocess.run(f'ffprobe -v quiet -i "{Path(self.output_dir, "vod.mp4")}" '
                           f'-show_entries format=duration -of default=noprint_wrappers=1:nokey=1',
                           shell=True, capture_output=True)

        if p.returncode:
            self._log.error('VOD length verification exited with error. Command: %s.', p.args)
            raise VodConvertError(f'VOD length verification exited with error. Command: {p.args}.')

        try:
            downloaded_length = int(float(p.stdout.decode('ascii').rstrip()))

        except Exception as e:
            self._log.error('Failed to fetch downloaded VOD length. VOD may not have downloaded correctly. %s', str(e))
            raise VodConvertError(str(e)) from e

        self._log.debug('Downloaded VOD length is %s. Expected length is %s.', downloaded_length, self.vod.duration)

        # pass verification if downloaded file is within 2s of expected length
        if 2 >= downloaded_length - self.vod.duration >= -2:
            self._log.debug('VOD passed length verification.')
            return True

        return False

    def _cleanup_temp_files(self):
        """
        Deletes temporary and transitional files used for archiving VOD video.
        """
        Path(self.output_dir, 'merged.ts').unlink()
        shutil.rmtree(Path(self.output_dir, 'parts'))
