```
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
* Allows any number of VODs or channels to be downloaded simultaneously.
* VODs can be downloaded as fast as your Internet connection (and storage) can handle.[^1]
* Allows the downloading of **live** VODs *before sections can be muted or deleted*.[^2]
* Generates and saves a readable chat log with timestamps and user badges.
* Allows for the archiving of both video and chat.
* Error notifications sent via pushbullet.
* Supports fully automated archiving.
* Requires minimal setup or external programs.

[^1]: If you wish to speed up (or slow down) the downloading of VOD pieces, supply the '--threads NUMBER' argument to the script. This changes how many download threads are used to grab the individual video files. With the default of 20, I can max out my gigabit Internet while downloading to an M.2 drive.
[^2]: There is one caveat with live archiving due to how Twitch presents ads. Ads are not downloaded, BUT while an ad is displayed, the actual stream output is not sent. This can result in missing segments under very rare circumstances, but any missing segments should be filled via a parallel VOD archival function. 

## Requirements
* **[Python](https://www.python.org/) >= 3.8**
* Python **requests** and **m3u8** modules `python -m pip install requests m3u8` or `python -m pip install -r requirements.txt`
* **[FFmpeg](https://ffmpeg.org/) >= 4.3.1** and **ffprobe** (Accessible via your PATH - see [Installation](#installation))

## Installation & Usage
### Installation
1. Download the most recent release via the green "Code" button on the top right, or grab the latest stable [release](https://github.com/Brisppy/twitch-archiver/releases/latest).

2. Download [FFmpeg](https://ffmpeg.org/download.html) and add to your PATH. See [this](https://www.wikihow.com/Install-FFmpeg-on-Windows) article if you are unsure how to do this.

3. Unpack and open the twitch-archiver folder and install required Python modules `python -m pip install -r requirements.txt`.

### Usage
Run the script via your terminal of choice. Use ```python ./twitch-vod-archiver.py -h``` to view help text.

#### Examples
```# python ./twitch-archiver.py -c Brisppy -i {client_id} -s {client_secret} -d "Z:\\twitch-archive"```

Would download `video` and `chat` of all VODs from the channel `Brisppy`, using the provided `client_id` and `client_secret`, to the directory `Z:\twitch-archive`.

```# python ./twitch-archiver.py -v 1276315849,1275305106 -d "/mnt/twitch-archive" -V -t 10```

Would download VODs `1276315849` and `1275305106` to the directory `/mnt/twitch-archive`, only saving the `video`  using `10 download threads`.

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
                        A single VOD (e.g 12763849) or many comma-separated IDs (e.g 12763159,12753056).
  -i CLIENT_ID, --client-id CLIENT_ID
                        Client ID retrieved from dev.twitch.tv
  -s CLIENT_SECRET, --client-secret CLIENT_SECRET
                        Client secret retrieved from dev.twitch.tv
  -C, --chat            Only save chat logs.
  -V, --video           Only save video.
  -t THREADS, --threads THREADS
                        Number of video download threads. (default: 20)
  -q QUALITY, --quality QUALITY
                        Quality to download. Options are 'best', 'worst' or a custom value.
                        Format for custom values is [resolution]p[framerate], (e.g 1080p60, 720p30).
                        (default: best)
  -d DIRECTORY, --directory DIRECTORY
                        Directory to store archived VOD(s), use TWO slashes for Windows paths.
                        (default: $CURRENT_DIRECTORY)
  -L LOG_FILE, --log-file LOG_FILE
                        Output logs to specified file.
  -I CONFIG_DIR, --config-dir CONFIG_DIR
                        Directory to store configuration, VOD database and lock files.
                        (default: $HOME/.config/twitch-archiver)
  -p PUSHBULLET_KEY, --pushbullet-key PUSHBULLET_KEY
                        Pushbullet key for sending pushes on error. Enabled by supplying key.
  -Q, --quiet           Disable all log output.
  -D, --debug           Enable debug logs.
  --version             Show version number and exit.
  --show-config         Show saved config and exit.
```

### Configuration
By default, configuration files are stored in `$HOME/.config/twitch-archiver`

This holds the config file (config.ini), VOD database used when archiving channels (vods.db), and is where lock files are stored to prevent multiple instances of TA from overwriting each other.

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

If for any reason you need to change your credentials, you can either manually edit the config file, or pass the new credentials to the script, and they will then be saved to the config.

## Retrieving Tokens
### To retrieve the CLIENT_ID and CLIENT_SECRET:
1. Navigate to [dev.twitch.tv](https://dev.twitch.tv/) and log in
2. Register a new app called Twitch VOD Archiver with any redirect URL and under any Category
3. The provided Client ID is used as the `CLIENT_ID` variable
4. The provided Client Secret is used as the `CLIENT_SECRET` variable

## Extra Info
### Notes
* We use the downloaded VOD duration to ensure that the VOD was successfully downloaded and combined properly, this is checked against Twitch's own API, which can show incorrect values. If you come across a VOD with a displayed length in the Twitch player longer than it actually goes for (If the VOD finishes before the timestamp end is reached), create a file named `.ignorelength` inside the VOD's directory (where `vod.json` and `verbose_chat.log` are stored), you may also want to verify that the VOD file matches the Twitch video after archiving too.
* If a VOD is deleted while it is being archived, all the vod information will be saved, and the VOD will be combined as-is and chat exported. 
* If your config (and thus vod database) is stored on an SMB/CIFS share, you may encounter issues with querying and adding to the sqlite database. This can be resolved by mounting the share with the `nobrl` option on linux.
* If you intend to push chat logs to an ELK stack, [this gist](https://gist.github.com/Brisppy/ddcf4d5bbb73f957181743faadb959e3) should have everything you need.
* By default, the highest quality VOD is downloaded. This can be changed via the `-q QUALITY` argument, where quality can be `best`, `worst`, or a custom value in the format `[resolution]p[framerate]`, for example `1080p60` or `720p30` would be valid values. If an exact match for the quality cannot be found, any quality of a matching **resolution** will be downloaded; for example, if you select `720p60`, and only `720p30` is available, `720p30` would be downloaded. Similarly, if you select `1080p30` and only `1080p60` is found, then `1080p60` would be downloaded instead. If no match is found, the highest quality will be downloaded.

### How files are stored
VODs are downloaded to the specified directory. If downloading a channel, an individual folder will be created for that specific channel.
When supplying just VOD ID(s), the vod is downloaded to a folder inside the supplied directory.

        DIRECTORY ─┬─ CHANNEL_a ─┬─ VOD_a ─┬─ vod.mp4
                   │             │         │
                   │             │         ├─ vod.json
                   │             │         │
                   │             │         ├─ verbose_chat.json
                   │             │         │
                   │             │         └─ readable_chat.log
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
                   │         ├─ verbose_chat.json
                   │         │
                   │         └─ readable_chat.log
                   │
                   └─ VOD_f ─── *

### Planned Features
- [x] .ts to .mp4 conversion progress bar.
- [x] Find a way to directly archive the stream - could be then spliced with downloaded vod parts to capture everything up to the point the VOD is deleted rather than just up to a couple of minutes before. Both video and chat could be done this way.
- [x] Speed up VOD part discovery by finding and removing downloaded parts from the 'to-download' list.
- [ ] Allow archiving of subscriber-only VODs (need an account with a subscription for development + testing).
- [ ] Improve VOD download speed using separate download and file move workers (may need someone to test with >1Gbit connection).
- [ ] Release python package.
- [ ] Allow archiving of livestreams without VODs.

### Why?
To put it simply - **I don't like when data is deleted**.

I originally began work on the first version of this script in response to the copyright storm in which most Twitch streamers purged their old VODs in fear of DMCA.

At the time, and even now I could not find any script which would allow for the AUTOMATED archival of both the video AND chat for a particular VOD, and especially not one which can do this while the VOD is still live.

This script seeks to cover this, while also offers other functionality for those with a penchant for archiving data, or who wish to download VODs for other reasons.

## Disclaimer
This script is intended to be used with the express permission of any involved rights holders, and is not intended to be used to duplicate, download or steal copyrighted content or information. When downloading VODs ensure you have permission from ALL involved rights holders for the content which you are downloading, and if you have the intention to share such content, you should also have explicit permission to do so.

If your intent is to use this script to lazily rip and upload streams to another platform for your own gain without the permission of the streamer, I implore you to stop and think about what you are doing and the possible effect of doing so, and politely request that you find another method with which to steal the work of others.