"""
Various utility functions for modifying, retrieving and saving information.
"""

import hashlib
import json
import logging
import os
import re
import shutil

from datetime import datetime, timezone
from itertools import groupby
from math import ceil, floor
from pathlib import Path
from textwrap import dedent

import requests

from twitcharchiver.twitch import Chapters

log = logging.getLogger()


def build_output_dir_name(title: str, created_at: float, vod_id: int = 0):
    """
    Builds a directory name based on a title, a timestamp and VOD ID.

    :param title: name of VOD or stream
    :type title: str
    :param created_at: timestamp
    :type created_at: float
    :param vod_id: ID of VOD
    :type vod_id: int
    :return: name of output folder for given VOD or stream parameters
    :rtype: str
    """
    if vod_id != 0:
        _dir_name = ' - '.join([format_timestamp(created_at), sanitize_text(title), str(vod_id)])
    else:
        _dir_name = ' - '.join([format_timestamp(created_at), sanitize_text(title), 'STREAM_ONLY'])
    return _dir_name


def format_timestamp(timestamp: float):
    """
    Formats a given UTC timestamp to the YYYY-MM-DD_HH-MM-SS format.

    :param timestamp: UTC timestamp to convert
    :return: timestamp in YYYY-MM-DD_HH-MM-SS format
    """
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d_%H-%M-%S")


def export_json(vod_json: dict):
    """Exports all VOD information to a file.

    :param vod_json: dict of vod parameters retrieved from twitch
    """
    with open(Path(vod_json['store_directory'], 'vod.json'), 'w', encoding='utf8') as json_out_file:
        json_out_file.write(json.dumps(vod_json))


def import_json(vod_json: dict):
    """Imports all VOD information from a file.

    :param vod_json: dict of vod parameters retrieved from twitch
    """
    if Path(vod_json['store_directory'], 'vod.json').exists():
        with open(Path(vod_json['store_directory'], 'vod.json'), 'r', encoding='utf8') as json_in_file:
            return json.loads(json_in_file.read())

    return []


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


def sanitize_text(string: str):
    """Sanitize a given string removing unwanted characters which aren't allowed in directories, file names.

    :param string: string of characters to sanitize
    :return: sanitized string
    """
    return re.sub(r'[/\\:|<>"?*\0-\x1f]', '_', string)


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

    return int()


def convert_to_hms(seconds):
    """Converts a given time in seconds to the format HHhMMmSSs.

    :param seconds: time in seconds
    :return: time in HHhMMmSSs format
    """
    minutes = seconds // 60
    hours = minutes // 60

    return f"{hours:02d}h{minutes % 60:02d}m{seconds % 60:02d}s"


def time_since_date(timestamp: float):
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

    return end_time - start_time


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
    """
    Convert dotted version number to tuple for comparison.

    :param v: dotted version number
    :return: tuple of version numbers
    """
    return tuple(map(int, (v.split("."))))


def check_update_available(local_version, remote_version):
    """
    Compares two software versions.

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


# todo : needs to be re implemented
def send_push(pushbullet_key, title, body=''):
    """
    Sends a push to an account based on a given pushbullet key.

    :param pushbullet_key: key for destination pushbullet account. 'False' to not send.
    :param title: title to send with push
    :param body: body to send with push
    """
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

    except Exception as exc:
        log.error('Error sending push. Error: %s', exc)


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
        dst_exists = os.path.exists(dst_file)
        if dst_exists and os.path.samefile(src_file, dst_file):
            log.debug('%s already exists and matches %s.', dst_file, src_file)
            os.remove(src_file)
        else:
            if dst_exists:
                os.remove(dst_file)

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

    # default return
    return val


def format_vod_chapters(chapters: Chapters):
    """Formats vod chapters retrieved from Twitch into an FFmpeg insertable format

    :param chapters: Chapters which make up the VOD
    :type chapters: Chapters
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

    # some chapters have no game attached and so the 'description' is used instead
    for chapter in chapters:
        formatted_chapters += chapter_base.format(
            start=chapter.segment.position * 1000,
            end=(chapter.segment.position + chapter.segment.duration) * 1000,
            title=chapter.description)

    return formatted_chapters


def write_file(data: str, file: Path):
    """
    Writes data to the provided file.

    :param data: string to write to file
    :type data: str
    :param file: Path of output file (will be overwritten)
    :type file: Path
    """
    try:
        with open(Path(file), 'w', encoding='utf8') as _f:
            _f.write(data)

    except Exception as exc:
        log.error('Failed to write data to "%s". Error: %s', Path(file), exc)


def write_file_line_by_line(data: list, file: Path):
    """
    Writes data to the provided file with each list element on a new line.

    :param data: list to write to file
    :type data: list
    :param file: Path of output file (will be overwritten)
    :type file: Path
    """
    try:
        # delete existing file as we must append to it
        if Path(file).is_file():
            Path(file).unlink()

        # write each message line by line to readable log
        with open(Path(file), 'a+', encoding="utf-8") as _f:
            for _element in data:
                _f.write(f'{_element}\n')

    except Exception as exc:
        log.error('Failed to write data to "%s". Error: %s', Path(file), exc)


def write_json_file(data, file: Path):
    """
    Writes data to the provided file.

    :param data: dict to write to file
    :type data: dict | list
    :param file: Path of output file (will be overwritten)
    :type file: Path
    """
    try:
        with open(Path(file), 'w', encoding='utf8') as _f:
            _f.write(json.dumps(data))

    except Exception as exc:
        log.error('Failed to write json data to "%s". Error: %s', Path(file), exc)


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
            self.start_time = int(datetime.now(timezone.utc).timestamp())

    # reference:
    #   https://stackoverflow.com/questions/63865536/how-to-convert-seconds-to-hhmmss-format-without-failing-if-hour-more-than-24
    @staticmethod
    def to_hms(s: int):
        """Converts a given time in seconds to HHhMMmSSs.

        :param s: time in seconds
        :return: time formatted as HHhMMmSSs
        """
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f'{h:0>2}:{m:0>2}:{s:0>2}'

    def print_progress(self, cur: int, total: int):
        """Prints and updates a nice progress bar.

        :param cur: current progress out of total
        :param total: highest value of progress bar
        """
        last_frame = cur == total
        percent = floor(100 * (cur / total))
        progress = floor((0.25 * percent)) * '#' + ceil(25 - (0.25 * percent)) * ' '
        if cur == 0 or self.start_time == 0:
            remaining_time = '?'

        else:
            remaining_time = self.to_hms(
                ceil(((int(datetime.now(timezone.utc).timestamp()) - self.start_time) / cur) * (total - cur)))

        if len(str(percent)) < 3:
            percent = ' ' * (3 - len(str(percent))) + str(percent)

        if len(str(cur)) < len(str(total)):
            cur = ' ' * (len(str(total)) - len(str(cur))) + str(cur)

        # end with newline rather than return
        if last_frame:
            print(f'  100%  -  [#########################]  -  {cur} / {total}  -  ETA: 00:00:00', end='\n')

        else:
            print(f'  {percent}%  -  [{progress}]  -  {cur} / {total}  -  ETA: {remaining_time}', end='\r')
