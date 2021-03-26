#!/usr/bin/python3
# A Python script for archiving Twitch VODs along with their corresponding chat logs.
# Variables MUST be set within the 'variables.py' file before use.

# ARGUMENTS:
# 1: Channel name (e.g Brisppy)

# Import DB functions
from src.vod_database_connect import *
from pathlib import Path
# Retrieve variables from supplied file
from variables import *
import subprocess
import requests
import shutil
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
def CallTwitch(api_path):
	url = 'https://api.twitch.tv/helix/'
	headers = {'Authorization': 'Bearer ' + OAUTH_TOKEN, 'Client-Id': CLIENT_ID}
	try:
		r = requests.get(url + api_path, headers=headers)
		if r.status_code != 200:
			print('ERROR: Status code ' + r.status_code + ' received from Twitch.')
			print('ERROR:', r.text)
			sys.exit(1)
	except requests.exceptions.RequestException as e:
		print('ERROR:', e)
		sys.exit(1)
	return json.loads(r.text)


# This function is used to retrieve the chat logs for a particular VOD.
# Takes VOD_INFO, APP_CLIENT_ID, APP_CLIENT_SECRET and VOD_SUBDIR
def RetrieveVODChat(VOD_INFO, APP_CLIENT_ID, APP_CLIENT_SECRET, VOD_SUBDIR):
	ATTEMPT = 0
	while True:
		ATTEMPT += 1
		if ATTEMPT > 5:
			print('ERROR: Failed to download chat log after', ATTEMPT, 'attempts.')
			if SEND_PUSHBULLET:
				SendPushbullet(PUSHBULLET_KEY, VOD_INFO, 'Failed to Download Chat Log.')
			sys.exit(1)
		# Call twitch-chat-downloader
		p = subprocess.run('tcd --video ' + VOD_INFO['data'][0]['id'] + ' --format irc --client-id ' + APP_CLIENT_ID + 
			' --client-secret ' + APP_CLIENT_SECRET + ' --output ' + '"' + str(VOD_SUBDIR) + '"', shell=True)
		# Check if tcd returned an error
		if p.returncode:
			print('ERROR: twitch-chat-downloader exited with error.')
			continue
		else:
			print('INFO: Chat downloaded successfully.')
			return


# This function is used to retrieve the actual video files for the VOD and combine them.
# Takes VOD_INFO, VOD_SUBDIR and VOD_NAME.
def RetrieveVODVideo(VOD_INFO, VOD_SUBDIR, VOD_NAME):
	# This must be set to choose where the VOD is downloaded to before merging
	d = dict(os.environ)
	d['TMPDIR'] = str(VOD_SUBDIR)
	# Actual command for downloading the VOD
	p = subprocess.run('twitch-dl download --no-join -q source ' + VOD_INFO['data'][0]['id'], shell=True, env=d)
	# Catch any exit code other than 0
	if p.returncode:
		print('ERROR: VOD download exited with error.')
		print('ERROR:', p.stdout)
		if SEND_PUSHBULLET:
			SendPushbullet(PUSHBULLET_KEY, VOD_INFO, 'VOD download exited with error.')
		sys.exit(1)
	else:
		print('INFO: VOD download successful.')
	# Create a list containing all VOD .ts files - requires glob as the pathnames are difficult to decipher, and so
	# a wildcard is the preferred choice.
	VOD_PARTS = [Path(p) for p in glob.glob(str(VOD_SUBDIR) + '/twitch-dl/*/chunked/*.ts')]
	# Create a file with the list of .ts files for ffmpeg to concat
	with open(Path(VOD_SUBDIR, 'tsfile.txt'), mode='wt', encoding='utf-8') as tsfile:
		for part in VOD_PARTS:
			# We append 'file' as its required by ffmpeg...
			tsfile.write("file " + "'" + str(part) + "'" + "\n")
	# Combine the TS files with ffmpeg
	p = subprocess.run('ffmpeg -y -f concat -safe 0 -i ' + '"' + str(Path(VOD_SUBDIR, 'tsfile.txt')) + '"' + 
					   ' -c:a copy -c:v copy ' + '"' + str(Path(VOD_SUBDIR, VOD_NAME + '.mp4')) + '"', shell=True)
	# Catch any non-zero exit code
	if p.returncode:
		print('ERROR: VOD combining exited with error.')
		if SEND_PUSHBULLET:
			SendPushbullet(PUSHBULLET_KEY, VOD_INFO, 'Error Combining .ts Files.')
		sys.exit(1)
	else:
		print('INFO: VOD combined successfully.')
	# Delete the temporary tsfile.txt file
	os.remove(Path(VOD_SUBDIR, 'tsfile.txt'))
	return


# This function is used to verify the VOD length.
# Takes VOD_INFO, VOD_NAME and VOD_SUBDIR.
def VerifyVODLength(VOD_INFO, VOD_NAME, VOD_SUBDIR):
	# First we convert the provided time from 00h00m00s to seconds
	VOD_LENGTH = VOD_INFO['data'][0]['duration'].replace('h', ':').replace('m', ':').replace('s', '').split(':')
	if len(VOD_LENGTH) == 1:
		VOD_DURATION_SECONDS = int(VOD_LENGTH[0])
	elif len(VOD_LENGTH) == 2:
		VOD_DURATION_SECONDS = (int(VOD_LENGTH[0]) * 60) + int(VOD_LENGTH[1])
	elif len(VOD_LENGTH) == 3:
		VOD_DURATION_SECONDS = (int(VOD_LENGTH[0]) * 3600) + (int(VOD_LENGTH[1]) * 60) + int(VOD_LENGTH[2])
	# Retrieve the duration of the downloaded VOD
	p = subprocess.run('ffprobe -i ' + '"' + str(Path(VOD_SUBDIR, VOD_NAME + '.mp4')) + '"' + ' -v quiet -show_entries \
					   format=duration -of default=noprint_wrappers=1:nokey=1', shell=True, capture_output=True)
	# The output must be converted to a string, trailing newline removed, then float, then int...
	try:
		DOWNLOADED_VOD_LENGTH = int(float(p.stdout.decode('ascii').rstrip()))
	except BaseException as e:
		print('ERROR: Failed to fetch downloaded VOD length. VOD may not have downloaded correctly.')
		print('ERROR:', e)
		sys.exit(1)
	print('INFO: Downloaded VOD length is ' + str(DOWNLOADED_VOD_LENGTH) + 's. Expected length is ' \
		  + str(VOD_DURATION_SECONDS) + 's.')
	# Check if downloaded VOD is within 10 seconds of the reported VOD length.
	if DOWNLOADED_VOD_LENGTH > (VOD_DURATION_SECONDS - 10) and DOWNLOADED_VOD_LENGTH < (VOD_DURATION_SECONDS + 10):
		print('INFO: Downloaded VOD duration within 10 seconds of reported duration.')
		try:
			shutil.rmtree(Path(VOD_SUBDIR, 'twitch-dl'))
		except BaseException as e:
			print('ERROR: Failed to delete temporary twitch-dl directory.')
			print('ERROR:', e)
		return
	else:
		print('ERROR: Downloaded VOD duration not within 10 seconds of reported duration.')
		# Remove the .mp4
		os.remove(Path(VOD_SUBDIR, VOD_NAME + '.mp4'))
		if SEND_PUSHBULLET:
			SendPushbullet(PUSHBULLET_KEY, VOD_INFO, 'Downloaded VOD duration not within 10 seconds of reported \
													  duration.')
		sys.exit(1)


# Function for sending pushbullet notification.
# Created by github.com/mixsoda (https://gist.github.com/mixsoda/4d7eebdf767432f95f4b66ac19f7e310)
# Takes PUSHBULLET_KEY, VOD_INFO and ERROR (Error message to be sent).
def SendPushbullet(PUSHBULLET_KEY, VOD_INFO, ERROR):
	token = PUSHBULLET_KEY
	url = "https://api.pushbullet.com/v2/pushes"
	headers = {"content-type": "application/json", "Authorization": 'Bearer '+token}
	data_send = {"type": "note", "title": 'Error Archiving Twitch VOD ' + VOD_INFO['data'][0]['id'], "body": ERROR}
	_r = requests.post(url, headers=headers, data=json.dumps(data_send))

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
	connection = CreateConnection(str(Path(VOD_DIRECTORY, CHANNEL, 'vod_db.sqlite')))
	# Create the VODs table if it doesn't already exist
	ExecuteQuery(connection, create_vods_table)
	# Retrieve the USER_ID
	USER_ID = CallTwitch('users?login=' + CHANNEL)['data'][0]['id']
	print('INFO: User ' + CHANNEL +' ID is ' + USER_ID + '.')
	# Check if the channel is currently live - if so we must ignore the most recent VOD as it is still being added to.
	CHANNEL_STATUS = CallTwitch('streams?user_id=' + CHANNEL)
	if CHANNEL_STATUS['data']:
		if CHANNEL_STATUS['data'][0]['type'] == 'live':
			print('INFO: Channel is currently live. Assuming the highest numbered VOD is still being generated and \
				ignoring.')
			CHANNEL_LIVE = True
		else:
			print('INFO: Channel is live, but may not be streaming (And creating a VOD).')
			CHANNEL_LIVE = False
	else:
		print('INFO: Channel is currently offline.')
		CHANNEL_LIVE = False
	# Return a list of available VODs from $CHANNEL
	AVAIL_VODS = CallTwitch('videos?user_id=' + USER_ID + '&first=100&type=archive')
	# Create a list of available VODs
	AVAILABLE_VODS = []
	for vod in AVAIL_VODS['data']:
		AVAILABLE_VODS.append(int(vod['id']))
	print('INFO: Available VODs:', AVAILABLE_VODS)
	# Remove highest numbered VOD is channel is currently live
	if CHANNEL_LIVE:
		AVAILABLE_VODS.remove(max(AVAIL_VODS))
	# Retrieve currently downloaded VODs from VOD database
	select_vods = 'SELECT * from vods'
	DOWN_VODS = ExecuteReadQuery(connection, select_vods)
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
		VOD_INFO = CallTwitch('videos?id=' + str(vod_id))
		RAW_VOD_INFO = copy.deepcopy(VOD_INFO)
		# Sanitize the dates
		VOD_INFO['data'][0]['created_at'] = VOD_INFO['data'][0]['created_at'].replace(':', '_')
		VOD_INFO['data'][0]['published_at'] = VOD_INFO['data'][0]['published_at'].replace(':', '_')
		# Sanitize the VOD name - I'm not great with regex, but this works so... ¯\_(ツ)_/¯
		VOD_INFO['data'][0]['title'] = re.sub('[^A-Za-z0-9.,_\-\(\)\[\] ]', '_', VOD_INFO['data'][0]['title'])
		# Sanitize the VOD descripton
		VOD_INFO['data'][0]['description'] = re.sub('[^A-Za-z0-9.,_\-\(\)\[\] ]', '_', VOD_INFO['data'][0]
																							   ['description'])
		# Create a directory for the VOD.
		VOD_SUBDIR = Path(VOD_DIRECTORY, CHANNEL, VOD_INFO['data'][0]['created_at'] + ' - ' + 
												  VOD_INFO['data'][0]['title'] + ' - ' + str(vod_id))
		if not os.path.isdir(Path(VOD_SUBDIR)):
			print('INFO: Creating individual VOD directory.')
			os.mkdir(Path(VOD_SUBDIR))
		# First we download the chat logs
		RetrieveVODChat(VOD_INFO, APP_CLIENT_ID, APP_CLIENT_SECRET, VOD_SUBDIR)
		# Then we grab the video
		#RetrieveVODVideo(VOD_INFO, VOD_SUBDIR, VOD_INFO['data'][0]['title'])
		# Now we make sure the VOD length is within 2 seconds
		VerifyVODLength(VOD_INFO, VOD_INFO['data'][0]['title'], VOD_SUBDIR)
		# If we've made it to this point, all files have been downloaded and the VOD can be added to the database.
		RAW_VOD_INFO['data'][0]['vod_subdirectory'] = VOD_INFO['data'][0]['created_at'] + ' - ' + \
													  VOD_INFO['data'][0]['title'] + ' - ' + str(vod_id)
		RAW_VOD_INFO['data'][0]['vod_title'] = VOD_INFO['data'][0]['title'] + '.mp4'
		create_vod = """
		INSERT INTO
		vods (id, user_id, user_login, user_name, title, description, created_at, published_at, url, thumbnail_url, 
				viewable, view_count, language, type, duration, vod_subdirectory, vod_title)
		VALUES
		(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
		"""
		ExecuteQuery(connection, create_vod, list(RAW_VOD_INFO['data'][0].values()))

main()
