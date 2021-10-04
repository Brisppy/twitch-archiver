#!/usr/bin/python3
# A Python script for archiving Twitch VODs along with their corresponding chat logs.
# Created by https://github.com/Brisppy
# Variables MUST be set within the 'variables.py' file before use.

# ARGUMENTS:
# 1: Channel name (e.g Brisppy)

# Import DB functions
from typing_extensions import final
from src.vod_database_connect import *
from pathlib import Path
# Retrieve variables from supplied file
from variables import *
import subprocess
import requests
import shutil
import time
import math
import glob
import json
import copy
import sys
import os
import re

# Check if channel has been supplied
if not sys.argv[1]:
    print('ERROR: No channel supplied.')
    sys.exit(1)

# Check if VOD directory was set
if not VOD_DIRECTORY:
    print('ERROR: VOD directory not supplied.')
    sys.exit(1)

# DO NOT MODIFY
CHANNEL = sys.argv[1] # Channel name


# This function is used for retrieving information from the Twitch API, returning an array containing the retrieved
# information.
# Takes 'api_path' as a variable, defining the API endpoint to call.
def CallTwitch(api_path, pagination=0, live_mode=0):
    url = 'https://api.twitch.tv/helix/'
    headers = {'Authorization': 'Bearer ' + OAUTH_TOKEN, 'Client-Id': CLIENT_ID}
    try:
        # Loop for grabbing more than 100 VODs
        if pagination:
            cursor = ''
            vods = {'data': []}
            while True:
                r = requests.get(url + api_path + cursor, headers=headers)
                if r.status_code != 200:
                    print('ERROR: Status code ' + r.status_code + ' received from Twitch.')
                    print('ERROR:', r.text)
                    sys.exit(1)
                # If data is returned, add the returned VODs to the list
                if json.loads(r.text)['data']:
                    vods['data'].extend(json.loads(r.text)['data'][:])
                    # Grab the cursor value from the data, which is used to grab the next page of VODs
                    cursor = '&after=' + json.loads(r.text)['pagination']['cursor']
                # If no data is returned, end the loop and return the VOD information
                else:
                    print('INFO: All VODs have been grabbed from Twitch.')
                    return vods
        else:
            r = requests.get(url + api_path, headers=headers)
            if r.status_code != 200:
                print('ERROR: Status code ' + str(r.status_code) + ' received from Twitch.')
                print('ERROR:', r.text)
                # If operating in live mode, we must move onto combining the VOD which was most likely deleted.
                if live_mode and r.status_code == 404:
                    return 404
                print('ERROR: Twitch API returned an unexpected value.')
                print('ERROR:', r.text)
                if SEND_PUSHBULLET:
                    SendPushbullet(PUSHBULLET_KEY, 'Twitch API returned an unexpected value. Check logs for more info.')
                sys.exit(1)
            return json.loads(r.text)
    except requests.exceptions.RequestException as e:
        print('ERROR: Twitch API call failed.')
        print('ERROR:', e)
        if SEND_PUSHBULLET:
            SendPushbullet(PUSHBULLET_KEY, 'Twitch API call failed. Check logs for more info.')
        sys.exit(1)


# This function is used to retrieve the chat logs for a particular VOD.
# Takes VOD_INFO, APP_CLIENT_ID, APP_CLIENT_SECRET and VOD_SUBDIR
def RetrieveVODChat(VOD_INFO, APP_CLIENT_ID, APP_CLIENT_SECRET, VOD_SUBDIR, LIVE_MODE):
    ATTEMPT = 0
    while True:
        ATTEMPT += 1
        if ATTEMPT > 5:
            print('ERROR: Failed to download chat log after', ATTEMPT, 'attempts.')
            if SEND_PUSHBULLET:
                SendPushbullet(PUSHBULLET_KEY, VOD_INFO, 'Failed to Download Chat Log. This may be corrected on next '
                                                         'run')
            sys.exit(1)
        # Call twitch-chat-downloader
        p = subprocess.run('tcd --video ' + VOD_INFO['id'] + ' --format irc --client-id ' + APP_CLIENT_ID + 
                           ' --client-secret ' + APP_CLIENT_SECRET + ' --output ' + '"' + str(VOD_SUBDIR) + '"',
                           shell=True)
        # Check if tcd returned an error
        if p.returncode:
            if not LIVE_MODE:
                print('ERROR: twitch-chat-downloader exited with error.')
                continue
            else:
                print('INFO: Chat failed to download, but we are running in LIVE mode. The VOD (and chat) may have '
                      'been deleted.')
                return
        else:
            print('INFO: Chat downloaded successfully.')
            return


# This function is used to retrieve the actual video files for the VOD and combine them.
# Takes VOD_INFO, VOD_SUBDIR and VOD_NAME.
def RetrieveVODVideo(VOD_INFO, VOD_SUBDIR, VOD_NAME, LIVE_MODE):
    # This must be set to choose where the VOD is downloaded to before merging
    d = dict(os.environ)
    d['TMPDIR'] = str(VOD_SUBDIR)
    final_pass = 0
    # We grab the current duration of the VOD first to check against later.
    CUR_VOD_DURATION = VOD_INFO['duration']
    while True:
        # If VOD is live and under 5m long, we wait to ensure the VOD is ready for download
        if LIVE_MODE and ConvertToSeconds(CallTwitch('videos?id=' + str(VOD_INFO['id']))['data'][0]['duration']) < 300:
            print('INFO: VOD is not currently long enough to download, pausing for 5 minutes.')
            time.sleep(300)
            continue
        # Actual command for downloading the VOD
        p = subprocess.run('twitch-dl download --max-workers 20 --no-join -q source ' + VOD_INFO['id'], shell=True,
                                                                                                        env=d)
        # Catch any exit code other than 0
        if p.returncode:
            print('ERROR: VOD download exited with error.')
            print('ERROR:', p.stdout)
            if SEND_PUSHBULLET:
                SendPushbullet(PUSHBULLET_KEY, VOD_INFO, 'VOD download exited with error. Check log and remove .lock.' +
                               str(VOD_INFO['id']) + ' file.')
            sys.exit(1)
        if LIVE_MODE:
            # Fetch the current VOD duration again. Sleep first to allow the Twitch servers to adjust duration.
            print('INFO: Waiting 3 minutes for VOD length to update on Twitch servers.')
            time.sleep(180)
            NEW_VOD_INFO = CallTwitch('videos?id=' + str(VOD_INFO['id']), False, True)
            # If a 404 is returned, the VOD no longer exists, we continue as if we have the entire VOD saved
            if NEW_VOD_INFO == 404:
                print('INFO: 404 Returned from Twitch, VOD was most likely deleted. Creating .ignorelength file as '
                      'duration will most likely be incorrect.')
                with open(Path(VOD_SUBDIR, '.ignorelength'), 'w') as ignorelength:
                    pass
                # Also add the most recently grabbed duration to the RAW_VOD_DATA array
                RAW_VOD_INFO['duration'] = CUR_VOD_DURATION
                break
            else: 
                NEW_VOD_DURATION = NEW_VOD_INFO['data'][0]['duration']
            # Compare the original duration to the newly fetched duration
            if CUR_VOD_DURATION != NEW_VOD_DURATION:
                print('INFO: VOD Duration has changed (Probably live) - attempting to download VOD again.')
                print('DEBUG: Previous duration:', CUR_VOD_DURATION, 'New duration:', NEW_VOD_DURATION)
                CUR_VOD_DURATION = NEW_VOD_DURATION
                # Reset final pass in case the VOD duration changes after it meets the requirements for the stream
                # ending, this can happen in error.
                final_pass = 0
                continue
            # If the duration matches, we attempt to download the VOD one final time.
            elif CUR_VOD_DURATION == NEW_VOD_DURATION and not final_pass:
                print('INFO: VOD Duration has not changed, attempting to download once more then continuing.')
                time.sleep(120)
                final_pass = 1
                continue
            elif final_pass:
                print('INFO: VOD download successful.')
                break
        else:
            print('INFO: VOD download successful.')
            break
    # Create a list containing all VOD .ts files - requires glob as the pathnames are difficult to decipher, and so
    # a wildcard is the preferred choice.
    VOD_PARTS = [Path(p) for p in sorted(glob.glob(str(VOD_SUBDIR) + '/twitch-dl/*/chunked/*.ts'))]
    # Combine the TS files with ffmpeg into a single .ts file
    print('INFO: Combining downloaded VOD files... (This may take a while)')
    try:
        with open(str(Path(VOD_SUBDIR, 'merged.ts')), 'wb') as merged:
            progress = 0
            for ts_file in VOD_PARTS:
                progress += 1
                print('Processing ', progress, '/', len(VOD_PARTS), ' | {}% complete.'.format(
                                                        math.floor(100 * progress / len(VOD_PARTS))), sep='', end='\r')
                with open(ts_file, 'rb') as mergefile:
                    shutil.copyfileobj(mergefile, merged)
    except BaseException as e:
        print('ERROR: Combining of downloaded .ts files failed.')
        print('ERROR:', e)
        if SEND_PUSHBULLET:
            SendPushbullet(PUSHBULLET_KEY, VOD_INFO, 'Error Combining .ts Files. Check log and remove .lock.' +
                           str(VOD_INFO['id']) + ' file.')
        sys.exit(1)
    # Remux the combined .ts file into a .mp4
    print('INFO: Remuxing VOD file into to a .mp4 file.')
    p = subprocess.run('ffmpeg -v quiet -y -i ' + '"' + str(Path(VOD_SUBDIR, 'merged.ts')) + '"' +
                       ' -c:a copy -c:v copy ' + '"' + str(Path(VOD_SUBDIR, VOD_NAME + '.mp4')) + '"', shell=True)
    # Catch any non-zero exit code
    if p.returncode:
        print('ERROR: VOD remuxing exited with error.')
        if SEND_PUSHBULLET:
            SendPushbullet(PUSHBULLET_KEY, VOD_INFO, 'Error Remuxing Merged File. Check log and remove .lock.' +
                           str(VOD_INFO['id']) + ' file.')
        sys.exit(1)
    else:
        print('INFO: VOD combined successfully.')
    return


# This function is used to verify the VOD length.
# Takes VOD_INFO, VOD_NAME and VOD_SUBDIR.
def VerifyVODLength(VOD_INFO, VOD_NAME, VOD_SUBDIR):
    # First we convert the provided time from the format '00h00m00s' to just seconds
    VOD_DURATION_SECONDS = ConvertToSeconds(VOD_INFO['duration'])
    # Retrieve the duration of the downloaded VOD
    p = subprocess.run('ffprobe -i ' + '"' + str(Path(VOD_SUBDIR, VOD_NAME + '.mp4')) + '"' +
                       ' -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1', 
                       shell=True, capture_output=True)
    # The output must be converted to a string, trailing newline removed, then float, then int...
    try:
        DOWNLOADED_VOD_LENGTH = int(float(p.stdout.decode('ascii').rstrip()))
    except BaseException as e:
        print('ERROR: Failed to fetch downloaded VOD length. VOD may not have downloaded correctly.')
        print('ERROR:', e)
        sys.exit(1)
    print('INFO: Downloaded VOD length is ' + str(DOWNLOADED_VOD_LENGTH) + 's. Expected length is ' +
          str(VOD_DURATION_SECONDS) + 's.')
    # Check if downloaded VOD is not shorter than the reported VOD length.
    # This can be caused by various issues - VODs shorter by a lot should be checked, a second or so is fine though.
    if DOWNLOADED_VOD_LENGTH >= (VOD_DURATION_SECONDS -1):
        print('INFO: Downloaded VOD duration is equal to or greater than expected.')
        # Remove temporary twitch-dl directory and merged.ts file
        try:
            shutil.rmtree(Path(VOD_SUBDIR, 'twitch-dl'))
            os.remove(Path(VOD_SUBDIR, 'merged.ts'))
        except BaseException as e:
            print('ERROR: Failed to delete temporary twitch-dl directory or merged.ts file.')
            print('ERROR:', e)
        return
    elif os.path.isfile(Path(VOD_SUBDIR, '.ignorelength')):
        print('INFO: Downloaded VOD duration less than expected duration, but .ignorelength file found.')
        # Remove temporary twitch-dl directory and merged.ts file
        try:
            shutil.rmtree(Path(VOD_SUBDIR, 'twitch-dl'))
            os.remove(Path(VOD_SUBDIR, 'merged.ts'))
        except BaseException as e:
            print('ERROR: Failed to delete temporary twitch-dl directory or merged.ts file.')
            print('ERROR:', e)
        return
    else:
        print('ERROR: Downloaded VOD duration less than expected duration.')
        if SEND_PUSHBULLET:
            SendPushbullet(PUSHBULLET_KEY, VOD_INFO, 'Downloaded VOD duration shorter than expected. Check log '
                          'and remove .lock.' + str(VOD_INFO['id']) + ' file.')
        sys.exit(1)


# Function for sending pushbullet notification.
# Created by github.com/mixsoda (https://gist.github.com/mixsoda/4d7eebdf767432f95f4b66ac19f7e310)
# Takes PUSHBULLET_KEY, VOD_INFO and ERROR (Error message to be sent).
def SendPushbullet(PUSHBULLET_KEY, VOD_INFO, ERROR):
    token = PUSHBULLET_KEY
    url = "https://api.pushbullet.com/v2/pushes"
    headers = {"content-type": "application/json", "Authorization": 'Bearer '+token}
    data_send = {"type": "note", "title": 'Error Archiving Twitch VOD ' + VOD_INFO['id'] + ' by ' +
                 VOD_INFO['user_name'], "body": ERROR}
    _r = requests.post(url, headers=headers, data=json.dumps(data_send))


# Convert duration from the format XXhXXmXXs to just seconds.
def ConvertToSeconds(duration):
    duration = duration.replace('h', ':').replace('m', ':').replace('s', '').split(':')
    if len(duration) == 1:
        return int(duration[0])
    elif len(duration) == 2:
        return (int(duration[0]) * 60) + int(duration[1])
    elif len(duration) == 3:
        return (int(duration[0]) * 3600) + (int(duration[1]) * 60) + int(duration[2])


# This is the main function used for retrieving VOD information.
def main():
    # Check if VOD_DIRECTORY exists, if not, create it along with the CHANNEL directory
    if not os.path.isdir(Path(VOD_DIRECTORY)):
        print('INFO: Creating VOD archive directory.')
        os.mkdir(Path(VOD_DIRECTORY))
    if not os.path.isdir(Path(VOD_DIRECTORY, CHANNEL)):
        print('INFO: Creating VOD channel directory.')
        os.mkdir(Path(VOD_DIRECTORY, CHANNEL))
    # Setup database connection
    database_file = str(Path(VOD_DIRECTORY, CHANNEL, 'vod_db.sqlite'))
    # Create the VODs table if it doesn't already exist
    ExecuteQuery(database_file, create_vods_table)
    # Check database columns against what is expected
    CompareDatabase(database_file)
    # Retrieve the USER_ID
    USER_ID = CallTwitch('users?login=' + CHANNEL)['data'][0]['id']
    if not USER_ID:
        print('ERROR: No USER_ID received from Twitch, check your connection to Twitch and spelling of channel name.')
        sys.exit(1)
    print('INFO: User ' + CHANNEL +' ID is ' + USER_ID + '.')
    # Return a list of available VODs from $CHANNEL
    AVAIL_VODS = CallTwitch('videos?user_id=' + USER_ID + '&first=100&type=archive', 1)
    # Create a list of available VODs
    AVAILABLE_VODS = []
    for vod in AVAIL_VODS['data']:
        AVAILABLE_VODS.append(int(vod['id']))
    print('INFO: Available VODs:', AVAILABLE_VODS)
    # Check if the channel is currently live.
    CHANNEL_STATUS = CallTwitch('streams?user_id=' + USER_ID)
    if CHANNEL_STATUS['data']:
        if CHANNEL_STATUS['data'][0]['type'] == 'live':
            print('INFO: Channel is currently live.')
            CHANNEL_LIVE = True
        else:
            print('INFO: Channel is live, but may not be streaming (Could be a rerun).')
            CHANNEL_LIVE = False
    else:
        print('INFO: Channel is currently offline.')
        CHANNEL_LIVE = False
    # Retrieve currently downloaded VODs from VOD database
    select_vods = 'SELECT * from vods'
    DOWN_VODS = ExecuteReadQuery(database_file, select_vods)
    DOWNLOADED_VODS = []
    for vod in DOWN_VODS:
        DOWNLOADED_VODS.append(vod[0])
    print('INFO: Downloaded VODs:', DOWNLOADED_VODS)
    # Create the VOD queue by removing AVAILABLE_VODS which have already been downloaded.
    VOD_QUEUE = []
    for vod in AVAILABLE_VODS:
        if vod not in DOWNLOADED_VODS:
            VOD_QUEUE.append(vod)
    if not VOD_QUEUE:
        print('INFO: No new VODs.')
        sys.exit(0)
    print('INFO: VOD Queue:', VOD_QUEUE)
    # Iterate through each VOD, downloading the individual parts
    for vod_id in VOD_QUEUE:
        print('INFO: Retrieving VOD:', vod_id)
        VOD_INFO = CallTwitch('videos?id=' + str(vod_id))['data'][0]
        # We need to modify the duration if the VOD is live from with in the RetrieveVODVideo function. There is
        # probably a better method of doing this than declaring a global variable.
        global RAW_VOD_INFO
        RAW_VOD_INFO = copy.deepcopy(VOD_INFO)
        # Check if lock file exists and move to the next VOD if it does
        if os.path.isfile(Path(VOD_DIRECTORY, VOD_INFO['user_name'], '.lock.' + str(vod_id))):
            print('INFO: Lock file present for vod ' + str(vod_id) + '. VOD either failed previously with an error, or '
                  'is still being processed by another instance of TVA.')
            continue
        else:
            # Create lock file
            with open(Path(VOD_DIRECTORY, VOD_INFO['user_name'], '.lock.' + str(vod_id)), 'w') as lockfile:
                pass
        if CHANNEL_LIVE and vod_id == VOD_QUEUE[0]:
            print('INFO: Selected VOD is still being updated, running in LIVE mode.')
            LIVE_MODE = True
        else:
            LIVE_MODE = False
        # Sanitize the dates
        VOD_INFO['created_at'] = VOD_INFO['created_at'].replace(':', '_')
        VOD_INFO['published_at'] = VOD_INFO['published_at'].replace(':', '_')
        # Sanitize the VOD name - I'm not great with regex, but this works so... ¯\_(ツ)_/¯
        VOD_INFO['title'] = re.sub('[^A-Za-z0-9.,_\-\(\)\[\] ]', '_', VOD_INFO['title'])
        # Sanitize the VOD descripton
        VOD_INFO['description'] = re.sub('[^A-Za-z0-9.,_\-\(\)\[\] ]', '_', VOD_INFO['description'])
        # Convert the 'muted_segments' field to a string
        RAW_VOD_INFO['muted_segments'] = str(RAW_VOD_INFO['muted_segments'])
        # Create a directory for the VOD.
        VOD_SUBDIR = Path(VOD_DIRECTORY, VOD_INFO['user_name'], VOD_INFO['created_at'] + ' - ' + VOD_INFO['title'] +
                          ' - ' + str(vod_id))
        if not os.path.isdir(Path(VOD_SUBDIR)):
            print('INFO: Creating individual VOD directory.')
            os.mkdir(Path(VOD_SUBDIR))
        # First we grab video
        RetrieveVODVideo(VOD_INFO, VOD_SUBDIR, VOD_INFO['title'], LIVE_MODE)
        # Then we download the chat logs after in case the download is in LIVE mode
        RetrieveVODChat(VOD_INFO, APP_CLIENT_ID, APP_CLIENT_SECRET, VOD_SUBDIR, LIVE_MODE)
        # Now we make sure the VOD length matches what is expected
        VerifyVODLength(VOD_INFO, VOD_INFO['title'], VOD_SUBDIR)
        # If we've made it to this point, all files have been downloaded and the VOD can be added to the database.
        RAW_VOD_INFO['vod_subdirectory'] = VOD_INFO['created_at'] + ' - ' + VOD_INFO['title'] + ' - ' + str(vod_id)
        RAW_VOD_INFO['vod_title'] = VOD_INFO['title'] + '.mp4'
        create_vod = """
        INSERT INTO
        vods (id, stream_id, user_id, user_login, user_name, title, description, created_at, published_at, url,
              thumbnail_url, viewable, view_count, language, type, duration, muted_segments, vod_subdirectory,
              vod_title)
        VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        if ExecuteQuery(database_file, create_vod, list(RAW_VOD_INFO.values())):
            print('ERROR: Failed to add VOD information to database.')
            if SEND_PUSHBULLET:
                SendPushbullet(PUSHBULLET_KEY, VOD_INFO, 'Failed to add VOD information to database. Lock file removed '
                                                         'as the error may correct itself next run.')
            sys.exit(1)
        else:
            print('INFO: VOD ' + VOD_INFO['id'] + ' successfully downloaded.')
            # Remove lock file
            if os.path.isfile(Path(VOD_DIRECTORY, VOD_INFO['user_name'], '.lock.' + str(vod_id))):
                os.remove(Path(VOD_DIRECTORY, VOD_INFO['user_name'], '.lock.' + str(vod_id)))

main()
