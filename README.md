﻿```
 _______ ___ ___ ___ _______ _______ ___ ___  _______ _______ _______ ___ ___ ___ ___ ___ _______ _______ 
|       |   Y   |   |       |   _   |   Y   ||   _   |   _   |   _   |   Y   |   |   Y   |   _   |   _   \
|.|   | |.  |   |.  |.|   | |.  1___|.  1   ||.  1   |.  l   |.  1___|.  1   |.  |.  |   |.  1___|.  l   /
`-|.  |-|. / \  |.  `-|.  |-|.  |___|.  _   ||.  _   |.  _   |.  |___|.  _   |.  |.  |   |.  __)_|.  _   1
  |:  | |:      |:  | |:  | |:  1   |:  |   ||:  |   |:  |   |:  1   |:  |   |:  |:  1   |:  1   |:  |   |
  |::.| |::.|:. |::.| |::.| |::.. . |::.|:. ||::.|:. |::.|:. |::.. . |::.|:. |::.|\:.. ./|::.. . |::.|:. |
  `---' `--- ---`---' `---' `-------`--- ---'`--- ---`--- ---`-------`--- ---`---' `---' `-------`--- ---'
```
<p align="center"><b>
A simple, fast, platform-independent Python script for downloading past and present Twitch VODs and chat logs.</b><br/>
<br>
Primarily focused on data preservation, this script can be used to archive an entire Twitch channel at once, or to quickly grab the chat log from a single VOD. Both archived, and live VODs can be downloaded with this script.
</p>

## Table of Contents

  * [Features](#features)
  * [Requirements](#requirements)
  * [Installation & Usage](#installation--usage)
    * [Installation](#installation)
    * [Usage](#usage)
    * [Arguments](#arguments)
    * [Configuration](#configuration)
  * [Retrieving Tokens](#retrieving-tokens)
  * [Extra Info](#extra-info)
    * [Notes](#notes)
    * [How files are stored](#how-files-are-stored)
    * [Planned Features](#planned-features)
    * [Why?](#why)
  * [Disclaimer](#disclaimer)

## Features
* Allows any number of VODs or channel to be downloaded simultaneously.
* VODs can be downloaded as fast as your Internet connection (and storage) can handle[^1].
* Allows the downloading of **live**[^2] VODs *before copyrighted audio is detected and muted*.
* Generates and saves a readable chat log with timestamps and user badges.
* Allows the specifying of downloading only the video, chat or both.
* Error reporting via pushbullet.
* Supports automated archiving without any sort of user interaction.
* Requires minimal setup or external programs.

[^1]: If you wish to speed up (or slow down) the downloading of VOD pieces, supply the '--threads NUMBER' argument to the script. This changes how many download threads are used to grab the individual video files. With the default of 20, I can max out my gigabit Internet while downloading to an M.2 drive.
[^2]: If a VOD is being archived while it is live and deleted, the archived video will contain everything up to a couple of minutes before the deletion point. This is because streams are *currently* downloaded via their associated VOD which is a couple of minutes behind.


## Requirements
* **Python >= 3.7**
* Python **requests** and **m3u8** modules - `pip install requests m3u8`
* **[ffmpeg](https://ffmpeg.org/)** (Accessible via $PATH - see [Installation](#installation))

## Installation & Usage
### Installation
1. Download the most recent release via the green "Code" button on the top right, or grab the latest stable [release](https://github.com/Brisppy/twitch-vod-archiver/releases/latest).

2. Download [ffmpeg](https://ffmpeg.org/) and add to your PATH. See [this](https://www.wikihow.com/Install-FFmpeg-on-Windows) article if you are unsure how to do this.

3. Install Python requirements `python -m pip install -r requirements.txt`.

### Usage
Run the script via your terminal of choice. Use ```python ./twitch-vod-archiver.py -h``` to view help text.

#### Examples
```python ./twitch-vod-archiver.py -c Brisppy -i {client_id} -s {client_secret} -d "Z:\\twitch-archive"```

Would download **video and chat** of all VODs from the channel **Brisppy**, using the provided **client_id** and **client_secret**, to the directory **Z:\twitch-archive**.

```python ./twitch-vod-archiver.py -v 1276315849,1275305106 -d "Z:\\twitch-archive" -V -t 10```

Would download VODs **1276315849 and 1275305106** to the directory **Z:\twitch-archive**, only saving the **video**  using **10 download threads**.

### Arguments
```
usage: twitch-archiver.py [-h] (-c CHANNEL | -v VOD_ID) [-i CLIENT_ID]
                          [-s CLIENT_SECRET] [-C] [-V] [-t THREADS]
                          [-d DIRECTORY] [-L LOG_FILE] [-I CONFIG_DIR]
                          [-p PUSHBULLET_KEY] [-Q | -D] [--version]
                          [--show-config]

requires one of:
    -c CHANNEL, --channel CHANNEL
            Channel(s) to download, comma separated if multiple provided.
    -v VOD_ID, --vod-id VOD_ID
            VOD ID(s) to download, comma separated if multiple provided.

credentials are grabbed from stored config, OR provided with:
    -i CLIENT_ID, --client-id CLIENT_ID
            Client ID retrieved from dev.twitch.tv
    -s CLIENT_SECRET, --client-secret CLIENT_SECRET
            Client secret retrieved from dev.twitch.tv

Both the video and chat logs are grabbed if neither are specified.

optional arguments:
  -h, --help            show this help message and exit
  -c CHANNEL, --channel CHANNEL
                        A single twitch channel to download, or multiple comma-separated channels.
  -v VOD_ID, --vod-id VOD_ID
                        A single VOD ID (12763849) or multiple comma-separated VOD IDs (12763159,12753056)
  -i CLIENT_ID, --client-id CLIENT_ID
                        Client ID retrieved from dev.twitch.tv
  -s CLIENT_SECRET, --client-secret CLIENT_SECRET
                        Client secret retrieved from dev.twitch.tv
  -C, --chat            Only save chat logs.
  -V, --video           Only save video.
  -t THREADS, --threads THREADS
                        Number of video download threads. (default: 20)
  -d DIRECTORY, --directory DIRECTORY
                        Directory to store archived VOD(s), use TWO slashes for Windows paths.
                        (default: C:\Users\HC\Github\twitch-archiver)
  -L LOG_FILE, --log-file LOG_FILE
                        Output logs to specified file.
  -I CONFIG_DIR, --config-dir CONFIG_DIR
                        Directory to store configuration, VOD database and lock files.
                        (default: C:\Users\HC\.config\twitch-archiver)
  -p PUSHBULLET_KEY, --pushbullet-key PUSHBULLET_KEY
                        Pushbullet key for sending pushes on error. Enabled by supplying key.
  -Q, --quiet           Disable all log output.
  -D, --debug           Enable debug logs.
  --version             Show version number and exit.
  --show-config         Show saved config and exit.
```

### Configuration
By default, the configuration directory is `$HOME/.config/twitch-archiver`.

This holds the config (config.ini), VOD database used for archiving channels (vods.db), and is where lock files are stored to prevent multiple instances of TA from overwriting each other.

        CONFIG_DIR ─┬─ config.ini
                    │
                    ├─ vods.db
                    │
                    └─ .lock.xxxxxxx

### config.ini
Authentication tokens are stored in this format:
```
[settings]
client_id = 
client_secret = 
oauth_token = 
pushbullet_key = 
```
These are loaded into TA **first**, before being overwritten by any arguments passed to TA.
This file will be created the first time you use TA and an OAuth token is successfully generated, with the provided credentials then saved in the ini.

## Retrieving Tokens
### To retrieve the CLIENT_ID and CLIENT_SECRET:
1. Navigate to [dev.twitch.tv](https://dev.twitch.tv/) and log in
2. Register a new app called Twitch VOD Archiver with any redirect URL and under any Category
3. The provided Client ID is used as the CLIENT_ID variable
4. The provided Client Secret is used as the CLIENT_SECRET variable

## Extra Info
### Notes
* We use the downloaded VOD duration to ensure that the VOD was successfully downloaded and combined properly, this is checked against Twitch's own API, which can show incorrect values. If you come across a VOD with a displayed length in the Twitch player longer than it actually goes for (If the VOD ends before the 'end' is reached), create a file named '.ignorelength' inside the VOD's directory (Within the ```DIRECTORY/CHANNEL/VOD``` folder), you may also want to verify that the VODs are matching after archiving too.
* If a VOD is deleted while it is being archived, all the vod information will be saved, and the VOD will be combined as-is and chat exported. 
* If your config (and thus vod database) is stored on an SMB/CIFS share, you may encounter issues with querying and adding to the sqlite database. This can be resolved by mounting the share with the 'nobrl' option on linux machines.

### How files are stored
VODs are downloaded to the specified directory. If downloading a channel, an individual folder will be created for that specific channel.
When supplying just VOD ID(s), the vod is downloaded to a folder inside the supplied directory.

        DIRECTORY ─┬─ CHANNEL_a ─┬─ VOD_a ─┬─ vod.mp4
                   │             │         │
                   │             │         ├─ vod.json
                   │             │         │
                   │             │         ├─ verboseChat.json
                   │             │         │
                   │             │         └─ readableChat.log
                   │             │
                   │             └─ VOD_b ─── *
                   │
                   ├─ CHANNEL_b ─┬─ VOD_c ─── *
                   │             │
                   │             └─ VOD_d ─── *
                   │
                   ├─ VOD_e ─┬─ vod.mp4
                   │         │
                   │         ├─ vod.json
                   │         │
                   │         ├─ verboseChat.json
                   │         │
                   │         └─ readableChat.log
                   │
                   └─ VOD_f ─── *

### Planned Features
- [ ] Allow archiving of subscriber-only VODs (need an account with a subscription for development + testing).
- [ ] Improve VOD download speed using separate download and file move workers (may need someone to test with >1Gbit connection).
- [ ] Release python package.
- [x] .ts to .mp4 conversion progress bar.
- [ ] Find a way to directly archive the stream - could be then spliced with downloaded vod parts to capture everything up to the point the VOD is deleted rather than just up to a couple of minutes before. Both video and chat could be done this way.
- [x] Speed up VOD part discovery by finding and removing downloaded parts from the 'to-download' list.

### Why?
To put it simply - **I don't like when data is deleted**.

I originally began work on the first version of this script in response to the copyright storm in which most Twitch streamers purged their old VODs in fear of DMCA.

At the time, and even now I could not find any script which would allow for the AUTOMATED archival of both the video AND chat for a particular VOD, and especially not one which can do this while the VOD is still live.

This script seeks to cover this, while also offers other functionality for those with a penchant for archiving data, or who wish to download VODs for other reasons.

## Disclaimer
This script is intended to be used with the express permission of any involved rights holders, and is not intended to be used to duplicate, download or steal copyrighted content or information. When downloading VODs ensure you have permission from ALL involved rights holders for the content which you are downloading, and if you have the intention to share such content, you should also have explicit permission to do so.

If your intent is to use this script to lazily rip and upload streams to another platform for your own gain without the permission of the streamer, I implore you to stop and think about what you are doing and the possible effect of doing so, and politely request that you find another method with which to steal the work of others.
