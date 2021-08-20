# 📁 Twitch Vod Archiver 📁
A python script for archiving past Twitch VODs along with their corresponding chat logs for an entire Twitch channel.

Chat logs are grabbed with [tcd](https://github.com/PetterKraabol/Twitch-Chat-Downloader), with VODs downloaded with [twitch-dl](https://github.com/ihabunek/twitch-dl) before being remuxed with [ffmpeg](https://ffmpeg.org/).

VODs can be downloaded effectively as fast as your Internet speed can handle - See [Notes](#notes).

My recommendation is to run this script on some sort of schedule, allowing it to grab any new VODs on a regular basis.


Table of Contents
=================

  * [Requirements](#requirements)
  * [Installation](#installation)
  * [Usage](#usage)
  * [Retrieving Tokens](#retrieving-tokens)
  * [Notes](#notes)
  * [Extra Info](#extra-info)
    * [How does the script work?](#how-does-the-script-work)
    * [How are the files stored?](#how-are-the-files-stored)
    * [Limitations](#limitations)

# Requirements
* **Python 3.8**
* **[ffmpeg](https://ffmpeg.org/)** (Must be accessible via PATH)
* **[tcd](https://github.com/PetterKraabol/Twitch-Chat-Downloader)** (python -m pip install tcd) (Must be accessible via PATH)
* **[twitch-dl](https://github.com/ihabunek/twitch-dl)** (python -m pip install twitch-dl) (Must be accessible via PATH)

# Installation
1. Clone the repository, download via the 'Code' button on the top of the page, or grab the latest [release](https://github.com/Brisppy/twitch-vod-archiver/releases/latest).

2. Modify the variables in 'variables.py'.

| Variable | Function |
|-------|------|
|```CLIENT_ID```|Twitch account Client ID - (See [Retrieving Tokens](#retrieving-tokens)).
|```OAUTH_TOKEN```|Twitch account OAuth token - (See [Retrieving Tokens](#retrieving-tokens)).
|```APP_CLIENT_ID```|Application Client ID retrieved from dev.twitch.tv - (See [Retrieving Tokens](#retrieving-tokens)).
|```APP_CLIENT_SECRET```|Application Secret retrieved from dev.twitch.tv - (See [Retrieving Tokens](#retrieving-tokens)).
|```VOD_DIRECTORY```|Location in which VODs will be stored, users are stored in separate folders within - **Use TWO backslashes for Windows paths (e.g 'Z:\\\twitch-archive').**
|```SEND_PUSHBULLET```|**OPTIONAL:** 0/1 Whether or not you wish to send a pushbullet notification on download failure. **Do not surround with quotes.**
|```PUSHBULLET_KEY```|**OPTIONAL:** Your Pushbullet API key.

# Usage
Run the script, supplying the channel name. I use a crontab entry to run it nightly to grab any new VODs.

```python ./twitch-vod-archiver.py Brisppy```

# Retrieving Tokens
### To retrieve your CLIENT_ID and OAUTH_TOKEN:
1. Navigate to your twitch.tv channel page
2. Open the developer menu (F12 in Chrome)
3. Select the 'Network' tab and refresh the page
4. Press CTRL+F to bring up the search, and type in 'gql.twitch.tv' followed by ENTER
5. Click on the line beginning with 'URL', and the Headers menu should appear
6. Under 'Request Headers' you should find the line beginning with 'Authorization:', this is used as the OAUTH_TOKEN variable (Only copy the text AFTER 'OAuth'). Below this you will also find 'Client-ID:', this is used as the CLIENT_ID variable.

![Chrome developer menu showing location of CLIENT_ID and OAUTH_TOKEN](https://i.imgur.com/YVHT7EU.jpg)

### To retrieve the APP_CLIENT_ID and APP_CLIENT_SECRET:
1. Navigate to dev.twitch.tv
2. Register a new app called VOD Archiver with any redirect URL and under any Category
3. The provided Client ID is used as the APP_CLIENT_ID variable
4. The provided Client Secret is used as the APP_CLIENT_SECRET

# Notes
* We use the downloaded VOD duration to ensure that the VOD was successfully downloaded and combined properly, this is checked against Twitch's own API, which can show incorrect values. If you come across a VOD with a displayed length in the Twitch player longer than it actually goes for (If the VOD ends before the 'end' is reached), create a file named '.ignorelength' inside of the VOD's directory (Within the 'VOD_DIRECTORY/CHANNEL/DATE-VOD_NAME-VOD_ID' folder), you may also want to verify that the VODs are matching after archiving too.
* If your VOD_DIRECTORY is located on a SMB/CIFS share, you may encounter issues with querying and adding to the sqlite database. This can be resolved by mounting the share with the 'nobrl' option.
* If you wish to speed up (or slow down) the downloading of VOD pieces, edit  'twitch-vod-archiver.py' and find the line with '--max-workers 20' and change the number to however many pieces you wish to download at once.

# Extra Info
### How does the script work?
1. Upon being run, the script imports various Python modules, along with the 'variables.py' and 'src/vod_database_connect.py' files.
2. The main() function is then called which begins by creating directories if required, and setting up the sqlite database (Stored in the VOD_DIRECTORY/CHANNEL folder).
3. The USER_ID is then requested via the Twitch API for later use.
4. Now we check if the channel is live, if so, we ignore the most recent VOD as it is not yet complete.
5. We then get a list of VODs from the Channel via the Twitch API, and compare them with the downloaded VODs acquired from the sqlite database, adding NEW VODs to a queue.
6. Now we process each VOD in the VOD queue, first retrieving the chat via twitch-chat-downloader, then the video via twitch-dl.
7. After downloading the actual video files (Currently in the .ts format), we must concat them (Combine into a single file).
8. After concating all of the .ts files, we use ffmpeg to remux ito into an mp4.
9. We now check the video length against the expected length retrieved from the Twitch API.
9. If the video length matches, we delete any temporary files, add the VOD information to the database and move onto the next VOD.

### How are the files stored?
Downloaded files are stored under one large directory which you provide in 'variables.py' (VOD_DIRECTORY).

    VOD_DIRECTORY ─┬─ CHANNEL#1 ─┬─ VOD#1 ─┬─ CHAT.log
                   │             │         └─ VOD.mp4
                   │             │
                   │             ├─ VOD#2 ─┬─ CHAT.log
                   │             │         └─ VOD.mp4
                   │             │
                   │             └─ vod_db.sqlite
                   │
                   └─ CHANNEL#2 ─┬─ VOD#1 ─┬─ CHAT.log
                                 │         └─ VOD.mp4
                                 │
                                 ├─ VOD#2 ─┬─ CHAT.log
                                 │         └─ VOD.mp4
                                 │
                                 └─ vod_db.sqlite

### Limitations
* Only one VOD can be grabbed at a time PER channel which is being archived, but multiple scripts for different CHANNELS can be run simultaneously.
* VODs cannot be downloaded individually - only a channel may be supplied.
* Subscriber-only VODs cannot be archived yet as it's not supported by [twitch-dl](https://github.com/ihabunek/twitch-dl), the creater has expressed some [interest](https://github.com/ihabunek/twitch-dl/issues/48) in implementing though.
