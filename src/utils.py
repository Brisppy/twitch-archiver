import json
import logging
import re
import requests
import shutil
import subprocess
import sys

from datetime import datetime
from glob import glob
from math import ceil, floor
from pathlib import Path
from time import sleep

from src.exceptions import VodConvertError

log = logging.getLogger()


class Utils:
    """
    Various utility functions for modifying and saving data.
    """
    @staticmethod
    def generate_readable_chat_log(chat_log):
        """Converts the raw chat log into a scrollable, readable format.

        :param chat_log: list of chat messages retrieved from twitch which are to be converted
        :return: formatted chat log
        """
        r_chat_log = []
        for comment in chat_log:
            comment_time = '{:.3f}'.format(comment['content_offset_seconds'])
            user_name = str(comment['commenter']['display_name'])
            user_message = str(comment['message']['body'])
            user_badges = ''
            try:
                for badge in comment['message']['user_badges']:
                    if 'broadcaster' in badge['_id']:
                        user_badges += '(B)'

                    if 'moderator' in badge['_id']:
                        user_badges += '(M)'

                    if 'subscriber' in badge['_id']:
                        user_badges += '(S)'

            except KeyError:
                pass

            # FORMAT: [TIME] (B1)(B2)NAME: MESSAGE
            r_chat_log.append('[' + comment_time + ']' + ' ' + user_badges + user_name + ': ' + user_message)

        return r_chat_log

    @staticmethod
    def export_verbose_chat_log(chat_log, vod_directory):
        """Exports a given chat log to disk.

        :param chat_log: chat log retrieved from twitch to export
        :param vod_directory: directory used to store chat log
        """
        Path(vod_directory).parent.mkdir(parents=True, exist_ok=True)

        with open(Path(vod_directory, 'verboseChat.json'), 'w+', encoding="utf-8") as chat_file:
            chat_file.write(json.dumps(chat_log))

    @staticmethod
    def export_readable_chat_log(chat_log, vod_directory):
        """Exports the provided readable chat log to disk.

        :param chat_log: chat log retrieved from twitch to export
        :param vod_directory: directory used to store chat log
        """
        if Path(vod_directory, 'readableChat.log').is_file():
            Path(vod_directory, 'readableChat.log').unlink()

        with open(Path(vod_directory, 'readableChat.log'), 'a+', encoding="utf-8") as chat_file:
            for message in chat_log:
                chat_file.write(str(message) + '\n')

    @staticmethod
    def export_json(vod_json):
        """Exports all VOD information to a file.

        :param vod_json: dict of vod parameters retrieved from twitch
        """
        with open(Path(vod_json['store_directory'], 'vod.json'), 'w') as json_out_file:
            json_out_file.write(json.dumps(vod_json))

    @staticmethod
    def combine_vod_parts(vod_json, print_progress=True):
        """Combines the downloaded VOD .ts parts.

        :param vod_json: dict of vod parameters retrieved from twitch
        :param print_progress: boolean whether to print progress bar
        """
        log.info('Merging VOD parts. This may take a while.')

        # get ordered list of vod parts
        vod_parts = [Path(p) for p in sorted(glob(str(Path(vod_json['store_directory'], 'parts', '*.ts'))))]

        if print_progress:
            progress = Progress()

        with open(str(Path(vod_json['store_directory'], 'merged.ts')), 'wb') as merged:
            pr = 0
            for ts_file in vod_parts:
                pr += 1
                # append part to merged file
                with open(ts_file, 'rb') as mergefile:
                    shutil.copyfileobj(mergefile, merged)

                if print_progress:
                    progress.print_progress(pr, len(vod_parts))

    @staticmethod
    def convert_vod(vod_json, print_progress=True):
        """Converts the VOD from a .ts format to .mp4.

        :param vod_json: dict of vod parameters retrieved from twitch
        :param print_progress: boolean whether to print progress bar
        :raises vodConvertError: error encountered during conversion process
        """
        log.info('Converting VOD to mp4. This may take a while.')

        total_frames = Utils.get_vod_framecount(vod_json)

        if print_progress:
            progress = Progress()

        # convert merged .ts file to .mp4
        with subprocess.Popen(
                'ffmpeg -hide_banner -y -i ' + '"' + str(Path(vod_json['store_directory'], 'merged.ts')) + '"'
                + ' -c:a copy -c:v copy ' + '"'
                + str(Path(vod_json['store_directory'], Utils.sanitize_text(vod_json['title']) + '.mp4')) + '"',
                shell=True, stderr=subprocess.PIPE, universal_newlines=True) as p:
            # get progress from ffmpeg output and print progress bar
            for line in p.stderr:
                if 'frame=' in line:
                    # extract framerate from output
                    current_frame = re.search('(?<=frame=).*(?= fps=)', line)

                    if print_progress:
                        progress.print_progress(int(current_frame.group(0)), total_frames)

        if p.returncode:
            log.error(str(json.loads(p.output[7:])))
            raise VodConvertError(str(json.loads(p.output[7:])), vod_json['id'])

    @staticmethod
    def get_vod_framecount(vod_json):
        """Estimates the number of frames contained in the downloaded VOD.

        :param vod_json: dict of vod parameters retrieved from twitch
        :return: total number of frames
        """
        # we estimate the total frames based on the framerate and vod length -
        # when it comes to long vods, retrieving the number of frames can take TENS of minutes and
        # is simply not worth the hassle to properly count
        log.debug('Estimating length of VOD file.')

        # retrieve framerate of vod file
        p = subprocess.run('ffprobe -i ' + '"' + str(Path(vod_json['store_directory'], 'merged.ts')) + '"' +
                           ' -v quiet -select_streams v:0 -show_entries stream=avg_frame_rate'
                           ' -of default=noprint_wrappers=1:nokey=1',
                           shell=True, capture_output=True, universal_newlines=True)

        if p.returncode:
            log.error(str(json.loads(p.output[7:])))
            raise VodConvertError(str(json.loads(p.output[7:])), vod_json['id'])

        # retrieve framerate from returned output
        try:
            avg_framerate = eval(p.stdout.split('\n')[0])

        except Exception as e:
            log.error('Failed to fetch VOD framerate. VOD may not have downloaded correctly. ' + str(e))
            raise VodConvertError(str(json.loads(p.output[7:])), vod_json['id'])

        log.debug('Average framerate is ' + str(avg_framerate))

        framecount = int(avg_framerate * vod_json['duration_seconds'])
        log.debug('Estimated framecount: ' + str(framecount))

        return framecount

    @staticmethod
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
        p = subprocess.run('ffprobe -i ' + '"'
                           + str(Path(vod_json['store_directory'], Utils.sanitize_text(vod_json['title']) + '.mp4'))
                           + '"' + ' -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1',
                           shell=True, capture_output=True)

        if p.returncode:
            log.error(str(json.loads(p.output[7:])))
            raise VodConvertError(str(json.loads(p.output[7:])), vod_json['id'])

        try:
            downloaded_length = int(float(p.stdout.decode('ascii').rstrip()))

        except Exception as e:
            log.error('Failed to fetch downloaded VOD length. VOD may not have downloaded correctly. ' + str(e))
            return True

        log.debug('Downloaded VOD length is ' + str(downloaded_length) + '. Expected length is '
                  + str(vod_json['duration_seconds']) + '.')

        # fail verification if downloaded file is > than 2 seconds shorter than expected
        if downloaded_length < vod_json['duration_seconds'] - 2:
            return True

        log.debug('VOD passed length verification.')

        return False

    @staticmethod
    def cleanup_vod_parts(vod_directory):
        """Deletes temporary and transitional files used for archiving VOD videos.

        :param vod_directory: directory of downloaded vod which needs to be cleaned up
        """
        Path(vod_directory, 'merged.ts').unlink()
        shutil.rmtree(Path(vod_directory, 'parts'))

    @staticmethod
    def sanitize_text(string):
        """Sanitize a given string removing unwanted characters which aren't allowed in directories, file names.

        :param string: string of characters to sanitize
        :return: sanitized string
        """
        return re.sub('[^A-Za-z0-9.,_\-\(\)\[\] ]', '_', string)

    @staticmethod
    def sanitize_date(date):
        """Removes unwanted characters from a timedate structure.

        :param date: date retrieved from twitch to sanitize
        :return: sanitized date
        """
        for r in (('T', '_'), (':', '-'), ('Z', '')):
            date = date.replace(*r)

        return date

    @staticmethod
    def convert_to_seconds(duration):
        """Converts a given time in the format HHhMMmSSs to seconds.

        :param duration: time in HHhMMmSSs format to be converted
        :return: time in seconds
        """
        duration = duration.replace('h', ':').replace('m', ':').replace('s', '').split(':')

        if len(duration) == 1:
            return int(duration[0])

        elif len(duration) == 2:
            return (int(duration[0]) * 60) + int(duration[1])

        elif len(duration) == 3:
            return (int(duration[0]) * 3600) + (int(duration[1]) * 60) + int(duration[2])

    @staticmethod
    def create_lock(ini_path, vod_id):
        """Creates a lock file for a given VOD.

        :param ini_path: path to config directory
        :param vod_id: id of vod which lock file is created for
        :return: true if lock file creation fails
        """
        try:
            with open(Path(ini_path, '.lock.' + str(vod_id)), 'x') as _:
                pass

        except FileExistsError:
            return True

    @staticmethod
    def remove_lock(ini_path, vod_id):
        """Removes a given lock file.

        :param ini_path: path to config directory
        :param vod_id: id of vod which lock file is created for
        :return: error if lock file removal fails
        """
        try:
            Path(ini_path, '.lock.' + str(vod_id)).unlink()

        except Exception as e:
            return e

    @staticmethod
    def time_since_date(created_at):
        """Returns the time in seconds between a given date and now.

        :param created_at: timestamp retrieve from twitch to get time since
        :return: the time in seconds since the given date
        """
        created_at = int((datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%SZ').timestamp()))
        current_time = int(datetime.utcnow().timestamp())

        return current_time - created_at

    @staticmethod
    def send_push(pushbullet_key, title, body=''):
        """Sends a push to an account based on a given pushbullet key.

        :param pushbullet_key: key for destination pushbullet account. 'False' to not send.
        :param title: title to send with push
        :param body: body to send with push
        """
        if pushbullet_key:
            h = {"content-type": "application/json", "Authorization": 'Bearer ' + pushbullet_key}
            d = {"type": "note", "title": '[twitch-archiver] ' + title, "body": body}

            try:
                _r = requests.post(url="https://api.pushbullet.com/v2/pushes", headers=h, data=json.dumps(d))

            except Exception as e:
                log.error('Error sending push. ' + title + ' ' + body + '. ' + str(e))
                sys.exit(1)

            if _r.status_code != 200:
                log.error('Error sending push. ' + title + ' ' + body)


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
        return '{:0>2}:{:0>2}:{:0>2}'.format(h, m, s)

    def print_progress(self, cur, total):
        """Prints and updates a nice progress bar.

        :param cur: current progress out of total
        :param total: highest value of progress bar
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

        if int(cur) < total:
            print(f'  {percent}%  -  [{progress}]  -  {cur} / {total}  -  ETA: {remaining_time}', end='\r')

        else:
            print(f'  100%  -  [########################]  -  {cur} / {total}')
