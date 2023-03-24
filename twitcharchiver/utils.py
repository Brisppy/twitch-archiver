"""
Various utility functions for modifying, retrieving and saving information.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess

from datetime import datetime, timezone
from glob import glob
from itertools import groupby
from math import ceil, floor
from pathlib import Path
from textwrap import dedent

import requests

from twitcharchiver.exceptions import VodConvertError, CorruptPartError

log = logging.getLogger()


def generate_readable_chat_log(chat_log, stream_start):
    """Converts the raw chat log into a scrollable, readable format.

    :param chat_log: list of chat messages retrieved from twitch which are to be converted
    :param stream_start: stream start utc timestamp
    :return: formatted chat log
    """
    r_chat_log = []
    for comment in chat_log:
        # format comments with / without millisecond timestamp
        if '.' in comment['createdAt']:
            created_time = \
                datetime.strptime(comment['createdAt'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
        else:
            created_time = \
                datetime.strptime(comment['createdAt'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)

        comment_time = f'{get_time_difference(stream_start, created_time):.3f}'

        # catch comments without commenter informations
        if comment['commenter']:
            user_name = str(comment['commenter']['displayName'])
        else:
            user_name = '~MISSING_COMMENTER_INFO~'

        # catch comments without data
        if comment['message']['fragments']:
            user_message = str(comment['message']['fragments'][0]['text'])
        else:
            user_message = '~MISSING_MESSAGE_INFO~'

        user_badges = ''
        try:
            for badge in comment['message']['userBadges']:
                if 'broadcaster' in badge['setID']:
                    user_badges += '(B)'

                if 'moderator' in badge['setID']:
                    user_badges += '(M)'

                if 'subscriber' in badge['setID']:
                    user_badges += '(S)'

        except KeyError:
            pass

        # FORMAT: [TIME] (B1)(B2)NAME: MESSAGE
        r_chat_log.append(f'[{comment_time}] {user_badges}{user_name}: {user_message}')

    return r_chat_log


def export_verbose_chat_log(chat_log, vod_directory):
    """Exports a given chat log to disk.

    :param chat_log: chat log retrieved from twitch to export
    :param vod_directory: directory used to store chat log
    """
    Path(vod_directory).parent.mkdir(parents=True, exist_ok=True)

    with open(Path(vod_directory, 'verbose_chat.json'), 'w+', encoding="utf-8") as chat_file:
        chat_file.write(json.dumps(chat_log))


def export_readable_chat_log(chat_log, vod_directory):
    """Exports the provided readable chat log to disk.

    :param chat_log: chat log retrieved from twitch to export
    :param vod_directory: directory used to store chat log
    """
    if Path(vod_directory, 'readable_chat.log').is_file():
        Path(vod_directory, 'readable_chat.log').unlink()

    with open(Path(vod_directory, 'readable_chat.log'), 'a+', encoding="utf-8") as chat_file:
        for message in chat_log:
            chat_file.write(f'{message}\n')


def export_json(vod_json):
    """Exports all VOD information to a file.

    :param vod_json: dict of vod parameters retrieved from twitch
    """
    with open(Path(vod_json['store_directory'], 'vod.json'), 'w', encoding='utf8') as json_out_file:
        json_out_file.write(json.dumps(vod_json))


def import_json(vod_json):
    """Imports all VOD information from a file.

    :param vod_json: dict of vod parameters retrieved from twitch
    """
    if Path(vod_json['store_directory'], 'vod.json').exists():
        with open(Path(vod_json['store_directory'], 'vod.json'), 'r', encoding='utf8') as json_in_file:
            return json.loads(json_in_file.read())

    return []


def combine_vod_parts(vod_json, print_progress=True):
    """Combines the downloaded VOD .ts parts.

    :param vod_json: dict of vod parameters retrieved from twitch
    :param print_progress: boolean whether to print progress bar
    """
    log.info('Merging VOD parts. This may take a while.')

    # get ordered list of vod parts
    vod_parts = [Path(p) for p in sorted(glob(str(Path(vod_json['store_directory'], 'parts', '*.ts'))))]

    progress = Progress()

    # concat files if all pieces present, otherwise fall back to using ffmpeg
    last_part = int(vod_parts[-1].name.strip('.ts'))
    part_list = [int(i.name.strip('.ts')) for i in vod_parts]

    dicontinuity = set([i for i in range(last_part + 1)]).difference(part_list)
    if not dicontinuity:
        # merge all .ts files by concatenating them
        with open(str(Path(vod_json['store_directory'], 'merged.ts')), 'wb') as merged:
            pr = 0
            for ts_file in vod_parts:
                pr += 1
                # append part to merged file
                with open(ts_file, 'rb') as mergefile:
                    shutil.copyfileobj(mergefile, merged)

                if print_progress:
                    progress.print_progress(pr, len(vod_parts))

    else:
        # merge all .ts files with ffmpeg concat demuxer as missing segments can cause corruption with
        # other method

        log.debug('Discontinuity found, merging with ffmpeg.\n Discontinuity: %s', dicontinuity)

        # create file with list of parts for ffmpeg
        with open(Path(vod_json['store_directory'], 'parts', 'segments.txt'), 'w', encoding='utf8') as segment_file:
            for part in vod_parts:
                segment_file.write(f"file '{part}'\n")

        with subprocess.Popen(f'ffmpeg -hide_banner -fflags +genpts -f concat -safe 0 -y -i '
                              f'"{str(Path(vod_json["store_directory"], "parts", "segments.txt"))}"'
                              f' -c copy "{str(Path(vod_json["store_directory"], "merged.ts"))}"',
                              shell=True, stderr=subprocess.PIPE, universal_newlines=True) as p:
            # get progress from ffmpeg output and print progress bar
            for line in p.stderr:
                if 'time=' in line:
                    # extract current timestamp from output
                    current_time = re.search('(?<=time=).*(?= bitrate=)', line).group(0).split(':')
                    current_time = \
                        int(current_time[0]) * 3600 + int(current_time[1]) * 60 + int(current_time[2][:2])

                    if print_progress:
                        progress.print_progress(int(current_time), vod_json['duration'])

            if p.returncode:
                log.error('VOD merger exited with error. Command: %s.', p.args)
                raise VodConvertError(f'VOD merger exited with error. Command: {p.args}.')


def convert_vod(vod_json, ignore_corruptions=None, print_progress=True):
    """Converts the VOD from a .ts format to .mp4.

    :param vod_json: dict of vod parameters retrieved from twitch
    :param ignore_corruptions: list of tuples containing (min, max) of corrupt segments which will be ignored
    :param print_progress: boolean whether to print progress bar
    :raises vodConvertError: error encountered during conversion process
    """
    log.info('Converting VOD to mp4. This may take a while.')

    progress = Progress()
    corrupt_parts = set()
    corrupt_part_whitelist = set()
    if ignore_corruptions:
        # create corrupt part whitelist form provided (min, max) ranges. The given range is expanded +-2 as the
        # DTS timestamps can still be wonky past them
        [corrupt_part_whitelist.update(r) for r in [range(t[0] - 2, t[1] + 3) for t in ignore_corruptions]]

    # get dts offset of first part
    with subprocess.Popen(f'ffprobe -v quiet -print_format json -show_format -show_streams '
                          f'"{Path(vod_json["store_directory"], "parts", "00000.ts")}"', shell=True,
                          stdout=subprocess.PIPE, universal_newlines=True) as p:
        ts_file_data = ''
        for line in p.stdout:
            ts_file_data += line

        dts_offset = float(json.loads(ts_file_data)['format']['start_time']) * 90000

    # create ffmpeg command
    ffmpeg_cmd = f'ffmpeg -hide_banner -y -i "{Path(vod_json["store_directory"], "merged.ts")}" '
    # insert metadata if present
    if Path(vod_json['store_directory'], 'parts', 'chapters.txt').exists():
        ffmpeg_cmd += f'-i "{Path(vod_json["store_directory"], "parts", "chapters.txt")}" -map_metadata 1 '

    ffmpeg_cmd += f'-c:a copy -c:v copy "{Path(vod_json["store_directory"], "vod.mp4")}"'

    # convert merged .ts file to .mp4
    with subprocess.Popen(ffmpeg_cmd, shell=True, stderr=subprocess.PIPE, universal_newlines=True) as p:
        # get progress from ffmpeg output and catch corrupt segments
        ffmpeg_log = ''
        for line in p.stderr:
            ffmpeg_log += line
            if 'time=' in line:
                # extract current timestamp from output
                current_time = re.search(r'(?<=time=).*(?= bitrate=)', line).group(0).split(':')
                current_time = int(current_time[0]) * 3600 + int(current_time[1]) * 60 + int(current_time[2][:2])

                if print_progress:
                    progress.print_progress(int(current_time), vod_json['duration'])

            elif 'Packet corrupt' in line:
                try:
                    dts_timestamp = int(re.search(r'(?<=dts = ).*(?=\).)', line).group(0))

                # Catch corrupt parts without timestamp, shows up as 'NOPTS'
                except ValueError as e:
                    raise VodConvertError("Corrupt packet encountered at unknown timestamp while converting VOD. "
                                          "Delete 'parts' folder and re-download VOD.") from e

                corrupt_part = floor((dts_timestamp - dts_offset) / 90000 / 10)

                # ignore if corrupt packet within ignore_corruptions range
                if corrupt_part in corrupt_part_whitelist:
                    log.debug('Ignoring corrupt packet as part in whitelist. Part: %s', corrupt_part)

                else:
                    corrupt_parts.add(int(corrupt_part))
                    log.error('Corrupt packet encountered. Part: %s', corrupt_part)

    if p.returncode:
        log.debug('FFmpeg exited with error code, output dumped to VOD directory.')
        with open(Path(vod_json["store_directory"], 'parts', 'ffmpeg.log'), 'w', encoding='utf8') as ffout:
            ffout.write(ffmpeg_log)

        raise VodConvertError("VOD converter exited with error. Delete 'parts' directory and re-download VOD.")

    if corrupt_parts:
        corrupted_ranges = to_ranges(corrupt_parts)
        formatted_ranges = []
        for t in corrupted_ranges:
            if t[0] == t[1]:
                formatted_ranges.append(f'{t[0]}.ts')
            else:
                formatted_ranges.append(f'{t[0]}-{t[1]}.ts')

        # raise error so we can try to recover
        raise CorruptPartError(corrupt_parts, formatted_ranges)


# https://stackoverflow.com/a/43091576
def to_ranges(iterable):
    """Converts a list of integers to iterable sets of (low, high) (e.g [0, 1, 2, 5, 7, 8] -> (0, 2), (5, 5), (7, 8))

    :param iterable: list of integers
    :return: iterable generator of separate integer ranges
    """
    iterable = sorted(set(iterable))
    for key, group in groupby(enumerate(iterable), lambda t: t[1] - t[0]):
        group = list(group)
        yield group[0][1], group[-1][1]


def verify_vod_length(vod_json):
    """Verifies the length of a given VOD.

    :param vod_json: dict of vod parameters retrieved from twitch
    :return: true if verification fails, otherwise false
    """
    log.debug('Verifying length of VOD file.')

    # skip verification if .ignorelength present
    if Path(vod_json['store_directory'], '.ignorelength').is_file():
        log.debug('.ignorelength file present - skipping verification.')
        return False

    # retrieve vod file duration
    p = subprocess.run(f'ffprobe -v quiet -i "{Path(vod_json["store_directory"], "vod.mp4")}" '
                       f'-show_entries format=duration -of default=noprint_wrappers=1:nokey=1',
                       shell=True, capture_output=True)

    if p.returncode:
        log.error('VOD length verification exited with error. Command: %s.', p.args)
        raise VodConvertError(f'VOD length verification exited with error. Command: {p.args}.')

    try:
        downloaded_length = int(float(p.stdout.decode('ascii').rstrip()))

    except Exception as e:
        log.error('Failed to fetch downloaded VOD length. VOD may not have downloaded correctly. %s', str(e))
        raise VodConvertError(str(e)) from e

    log.debug('Downloaded VOD length is %s. Expected length is %s.', downloaded_length, vod_json["duration"])

    # pass verification if downloaded file is within 2s of expected length
    if 2 >= downloaded_length - vod_json['duration'] >= -2:
        log.debug('VOD passed length verification.')
        return False

    return True


def cleanup_vod_parts(vod_directory):
    """Deletes temporary and transitional files used for archiving VOD videos.

    :param vod_directory: directory of downloaded vod which needs to be cleaned up
    """
    Path(vod_directory, 'merged.ts').unlink()
    shutil.rmtree(Path(vod_directory, 'parts'))


def sanitize_text(string):
    """Sanitize a given string removing unwanted characters which aren't allowed in directories, file names.

    :param string: string of characters to sanitize
    :return: sanitized string
    """
    return re.sub('[^A-Za-z0-9.,_\-\(\) ]', '_', string)


def sanitize_date(date):
    """Removes unwanted characters from a timedate structure.

    :param date: date retrieved from twitch to sanitize
    :return: sanitized date
    """
    for r in (('T', '_'), (':', '-'), ('Z', '')):
        date = date.replace(*r)

    return date


def convert_to_seconds(duration):
    """Converts a given time in the format HHhMMmSSs to seconds.

    :param duration: time in HHhMMmSSs format to be converted
    :return: time in seconds
    """
    duration = duration.replace('h', ':').replace('m', ':').replace('s', '').split(':')

    if len(duration) == 1:
        return int(duration[0])

    if len(duration) == 2:
        return (int(duration[0]) * 60) + int(duration[1])

    if len(duration) == 3:
        return (int(duration[0]) * 3600) + (int(duration[1]) * 60) + int(duration[2])


def convert_to_hms(seconds):
    """Converts a given time in seconds to the format HHhMMmSSs.

    :param seconds: time in seconds
    :return: time in HHhMMmSSs format
    """
    minutes = seconds // 60
    hours = minutes // 60

    return f"{hours:02d}h{minutes % 60:02d}m{seconds % 60:02d}s"


def create_lock(ini_path, vod_id):
    """Creates a lock file for a given VOD.

    :param ini_path: path to config directory
    :param vod_id: id of vod which lock file is created for
    :return: true if lock file creation fails
    """
    try:
        with open(Path(ini_path, f'.lock.{vod_id}'), 'x', encoding='utf8') as _:
            pass
        return

    except FileExistsError:
        return True


def remove_lock(config_dir, vod_id):
    """Removes a given lock file.

    :param config_dir: path to config directory
    :param vod_id: id of vod which lock file is created for
    :return: error if lock file removal fails
    """
    try:
        Path(config_dir, f'.lock.{vod_id}').unlink()
        return

    except Exception as e:
        return e


def time_since_date(timestamp):
    """Returns the time in seconds between a given datetime and now.

    :param timestamp: utc timestamp to compare current datetime to
    :return: the time in seconds since the given date
    """
    created_at = int(timestamp)
    current_time = int(datetime.now(timezone.utc).timestamp())

    return current_time - created_at


def get_time_difference(start_time, end_time):
    """Returns the time in seconds between a given datetime and now.

    :param start_time: start utc timestamp
    :param end_time: end utc timestamp
    :return: the time in seconds:milliseconds between the two datetimes
    """

    return (end_time - start_time).total_seconds()


def get_latest_version():
    """Fetches the latest release information from GitHub.

    :return: latest version number
    :return: latest release notes
    """
    try:
        _r = requests.get('https://api.github.com/repos/Brisppy/twitch-vod-archiver/releases/latest', timeout=10)
        # catch error codes such as 403 in case of rate limiting
        if _r.status_code != 200:
            return '0.0.0', ''
        latest_version = _r.json()['tag_name'].replace('v', '')
        release_notes = _r.json()['body']

    # return a dummy value if request fails
    except Exception:
        return '0.0.0', ''

    return latest_version, release_notes


# reference:
#   https://stackoverflow.com/a/11887825
def version_tuple(v):
    """Convert

    :param v:
    :return:
    """
    return tuple(map(int, (v.split("."))))


def check_update_available(local_version, remote_version):
    """Compares two software versions.

    :param local_version: local version in use
    :param remote_version: remote version to compare against
    :return: True if remote version has a higher version number, otherwise False
    """
    # check if local version is 'special', as in a development build or release candidate
    local_version_parts = local_version.split('.')
    if len(local_version_parts) > 3:
        log.warning(
            'Currently using a development or release candidate build. These may be unfinished or contain serious '
            'bugs. Report any issues you encounter to https://github.com/Brisppy/twitch-archiver/issues.')
        # update is available if we are using a dev or release candidate build equal to or prior to
        # the latest stable release
        if version_tuple('.'.join(local_version_parts[:-1])) <= version_tuple(remote_version):
            return True

    elif version_tuple(local_version) < version_tuple(remote_version):
        return True

    return False


def get_quality_index(desired_quality, available_qualities):
    """Finds the index of a user defined quality from a list of available stream qualities.

    :param desired_quality: desired quality to search for - best, worst or [resolution, framerate]
    :param available_qualities: list of available qualities as [[resolution, framerate], ...]
    :return: list index of desired quality if found
    """
    if desired_quality not in ['best', 'worst']:
        # look for user defined quality in available streams
        try:
            return available_qualities.index(desired_quality)

        except ValueError:
            log.info('User requested quality not found in available streams.')
            # grab first resolution match
            try:
                return [quality[0] for quality in available_qualities].index(desired_quality[0])

            except ValueError:
                log.info('No match found for user requested resolution. Defaulting to best.')
                return 0

    elif desired_quality == 'worst':
        return -1

    else:
        return 0


def send_push(pushbullet_key, title, body=''):
    """Sends a push to an account based on a given pushbullet key.

    :param pushbullet_key: key for destination pushbullet account. 'False' to not send.
    :param title: title to send with push
    :param body: body to send with push
    """
    if pushbullet_key:
        h = {'content-type': 'application/json', 'Authorization': f'Bearer {pushbullet_key}'}
        d = {'type': 'note', 'title': f'[twitch-archiver] {title}', 'body': body}

        try:
            _r = requests.post(url="https://api.pushbullet.com/v2/pushes", headers=h, data=json.dumps(d),
                               timeout=10)

            if _r.status_code != 200:
                if _r.json()['error']['code'] == 'pushbullet_pro_required':
                    log.error('Error sending push. Likely rate limited (500/month). '
                              'Error %s: %s', _r.status_code, _r.text)

                else:
                    log.error('Error sending push. Error %s: %s', _r.status_code, _r.text)

        except Exception as e:
            log.error('Error sending push. Error: %s', e)


# reference:
#   https://www.geeksforgeeks.org/compare-two-files-using-hashing-in-python/
def get_hash(file):
    """Retrieves the hash for a given file.

    :param file: path to file to hash
    :return: hash of provided file
    """
    f_hash = hashlib.md5()

    with open(Path(file), 'rb') as f:
        while True:
            # read in next chunk
            _d = f.read(65536)

            if not _d:
                break

            f_hash.update(_d)

        return f_hash.hexdigest()


# reference:
#   https://alexwlchan.net/2019/03/atomic-cross-filesystem-moves-in-python/
def safe_move(src_file, dst_file):
    """Atomically moves src_file to dst_file

    :param src_file: source file to copy
    :param dst_file: path to copy file to
    :raises FileNotFoundError: if src_file does not exist
    """
    log.debug('Moving "%s" to "%s".', src_file, dst_file)

    if Path(src_file).exists():
        # remove source file if it matches destination file
        if os.path.exists(dst_file) and os.path.samefile(src_file, dst_file):
            log.debug('%s already exists and matches %s.', dst_file, src_file)
            os.remove(src_file)
        else:
            # generate temp file path and copy source file to it
            tmp_file = Path(Path(dst_file.parent), os.urandom(6).hex())
            shutil.copyfile(src_file, tmp_file)

            # rename temp file
            os.rename(tmp_file, dst_file)

            # delete source file
            os.remove(src_file)

    else:
        raise FileNotFoundError


def getenv(name, default_val=None, is_bool=False):
    """
    Wrapper around os.getenv to convert empty strings to None type

    :param name: environment variable name
    :param default_val: default value to return if environment variable does not exist
    :param is_bool: handle environment variable as a case-insensitive boolean string ('true' or 'false')
    :return: environment variable value
    """
    val = os.getenv(name, default_val)

    if is_bool and isinstance(val, str):
        if val.upper() == "TRUE":
            return True

        if val.upper() == "FALSE":
            return False

        raise ValueError(f"Invalid boolean value (true or false) received for environment variable: {name}={val}")

    # return empty strings '' as None type
    return val if val else None


def format_vod_chapters(chapters):
    """Formats vod chapters retrieved from Twitch into an FFmpeg insertable format

    :param chapters: either a list of vod chapters or tuple containing (chapter_name, start, end)
    :return: chapters formatted as a string readable by ffmpeg
    """
    formatted_chapters = ";FFMETADATA1\n"
    chapter_base = dedent("""\
    [CHAPTER]
    TIMEBASE=1/1000
    START={start}
    END={end}
    title={title}
    
    """)

    if isinstance(chapters, tuple):
        formatted_chapters += chapter_base.format(
            start=chapters[1],
            end=chapters[2],
            title=chapters[0])

    else:
        # some chapters have no game attached and so the 'description' is used instead
        for chapter in chapters:
            formatted_chapters += chapter_base.format(
                start=chapter['positionMilliseconds'],
                end=chapter['positionMilliseconds'] + chapter['durationMilliseconds'],
                title=chapter['description'])

    return formatted_chapters


class Progress:
    """
    Functions for displaying progress.
    """
    start_time = 0

    def __init__(self):
        """
        Sets the start time used for computing the time remaining.
        """
        if self.start_time == 0:
            self.start_time = int(datetime.utcnow().timestamp())

    # reference:
    #   https://stackoverflow.com/questions/63865536/how-to-convert-seconds-to-hhmmss-format-without-failing-if-hour-more-than-24
    @staticmethod
    def to_hms(s):
        """Converts a given time in seconds to HHhMMmSSs.

        :param s: time in seconds
        :return: time formatted as HHhMMmSSs
        """
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f'{h:0>2}:{m:0>2}:{s:0>2}'

    def print_progress(self, cur, total, last_frame=False):
        """Prints and updates a nice progress bar.

        :param cur: current progress out of total
        :param total: highest value of progress bar
        :param last_frame: boolean if last frame of progress bar
        """
        percent = floor(100 * (cur / total))
        progress = floor((0.25 * percent)) * '#' + ceil(25 - (0.25 * percent)) * ' '
        if cur == 0 or self.start_time == 0:
            remaining_time = '?'

        else:
            remaining_time = self.to_hms(
                ceil(((int(datetime.utcnow().timestamp()) - self.start_time) / cur) * (total - cur)))

        if len(str(percent)) < 3:
            percent = ' ' * (3 - len(str(percent))) + str(percent)

        if len(str(cur)) < len(str(total)):
            cur = ' ' * (len(str(total)) - len(str(cur))) + str(cur)

        # end with newline rather than return
        if last_frame:
            print(f'  100%  -  [#########################]  -  {cur} / {total}  -  ETA: 00:00:00', end='\n')

        else:
            print(f'  {percent}%  -  [{progress}]  -  {cur} / {total}  -  ETA: {remaining_time}', end='\r')
