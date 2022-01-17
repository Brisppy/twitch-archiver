# 📁 Twitch Vod Archiver 📁
A CLI-based Python3 script for Windows and Linux allowing the scheduled archiving of Twitch VODs (Video + Chat logs) for a specified Twitch channel.

Chat logs are grabbed using [tcd](https://github.com/PetterKraabol/Twitch-Chat-Downloader), with VODs downloaded with [twitch-dl](https://github.com/ihabunek/twitch-dl) before being remuxed with [ffmpeg](https://ffmpeg.org/), with VODs being downloaded effectively as fast as your Internet speed can handle (see [notes](#notes)).  
This script is designed to run on sort sort of schedule, personally I run the script every hour, allowing it to grab VODs as they go live.

Table of Contents
=================

  * [Requirements](#requirements)
  * [Installation](#installation)
  * [Usage](#usage)
  * [Retrieving Tokens](#retrieving-tokens)
  * [Extra Info](#extra-info)
    * [Notes](#notes)
    * [How are the files stored?](#how-are-the-files-stored)
    * [Limitations](#limitations)

# Requirements
* **Python 3.8 (or newer)**
* **[ffmpeg](https://ffmpeg.org/)** (Must be accessible via PATH)
* **[tcd](https://github.com/PetterKraabol/Twitch-Chat-Downloader)** (python -m pip install tcd) (Must be accessible via PATH)
* **[twitch-dl](https://github.com/ihabunek/twitch-dl)** (python -m pip install twitch-dl) (Must be accessible via PATH)

# Installation & Usage
### Install
1. Clone the repository, download via the 'Code' button on the top of the page, or grab the latest [release](https://github.com/Brisppy/twitch-vod-archiver/releases/latest).

2. Install the requirements listed above.

3. Modify the variables in 'variables.py'.

| Variable | Function |
|-------|------|
|```CLIENT_ID```|Application Client ID retrieved from dev.twitch.tv - (See [Retrieving Tokens](#retrieving-tokens)).
|```CLIENT_SECRET```|Application Secret retrieved from dev.twitch.tv - (See [Retrieving Tokens](#retrieving-tokens)).
|```VOD_DIRECTORY```|Location in which VODs will be stored, users are stored in separate folders within - **Use TWO backslashes for Windows paths (e.g 'Z:\\\twitch-archive').**
|```SEND_PUSHBULLET```|**OPTIONAL:** 0/1 Whether or not you wish to send a pushbullet notification on download failure. **Do not surround with quotes.**
|```PUSHBULLET_KEY```|**OPTIONAL:** Your Pushbullet API key.

### Run
Run the script via a terminal or command line, supplying the channel name. I use a crontab entry to run it hourly to grab any new VODs.

```python ./twitch-vod-archiver.py Brisppy```

# Retrieving Tokens
### To retrieve the CLIENT_ID and CLIENT_SECRET:
1. Navigate to [dev.twitch.tv](https://dev.twitch.tv/) and log in
2. Register a new app called Twitch VOD Archiver with any redirect URL and under any Category
3. The provided Client ID is used as the CLIENT_ID variable
4. The provided Client Secret is used as the CLIENT_SECRET variable

# Extra Info
### Notes
* We use the downloaded VOD duration to ensure that the VOD was successfully downloaded and combined properly, this is checked against Twitch's own API, which can show incorrect values. If you come across a VOD with a displayed length in the Twitch player longer than it actually goes for (If the VOD ends before the 'end' is reached), create a file named '.ignorelength' inside of the VOD's directory (Within the ```VOD_DIRECTORY/CHANNEL/DATE-VOD_NAME-VOD_ID``` folder), you may also want to verify that the VODs are matching after archiving too.
* If your VOD_DIRECTORY is located on a SMB/CIFS share, you may encounter issues with querying and adding to the sqlite database. This can be resolved by mounting the share with the 'nobrl' option on linux machines.
* If you wish to speed up (or slow down) the downloading of VOD pieces, edit ```twitch-vod-archiver.py``` and find the line with ```--max-workers 20``` and change the number to however many pieces you wish to download at once.
* As of v1.1, multiple instances of this script can be run (I recommend a small delay inbetween). This is tracked through lock files located at the root of the channel folder. For example, ```Z:\\twitch-archive\\Brisppy\\.lock.1025444786```, which is removed only upon successful download of the VOD. If an error occurs, the VOD will be skipped on future runs of the script until the lock file is removed MANUALLY. I recommend setting up pushbullet so that you can catch issues such as this easily.

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
* VODs cannot be downloaded individually - only a channel may be supplied.
* Subscriber-only VODs cannot be archived yet as it's not supported by [twitch-dl](https://github.com/ihabunek/twitch-dl), the creater has expressed some [interest](https://github.com/ihabunek/twitch-dl/issues/48) in implementing though.
