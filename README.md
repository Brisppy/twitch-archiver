﻿```
       ______ __    __ ____ ______   __ __ __       ____ ____     __ __ __ ____ __ __   ___ ____  
      |      |  T__T  l    |      T /  |  T  T     /    |    \   /  |  T  l    |  T  | /  _|    \ 
      |      |  |  |  ||  T|      |/  /|  l  |    Y  o  |  D  ) /  /|  l  ||  T|  |  |/  [_|  D  )
      l_j  l_|  |  |  ||  |l_j  l_/  / |  _  |    |     |    / /  / |  _  ||  ||  |  Y    _|    / 
        |  | l  `  '  !|  |  |  |/   \_|  |  |    |  _  |    \/   \_|  |  ||  |l  :  |   [_|    \ 
        |  |  \      / j  l  |  |\     |  |  |    |  |  |  .  \     |  |  |j  l \   /|     |  .  Y
        l__j   \_/\_/ |____j l__j \____l__j__j    l__j__l__j\_j\____l__j__|____j \_/ l_____l__j\_j
```
<p align="center"><b>
A simple, fast, platform-independent tool for downloading Twitch streams, videos and chat logs.</b>
<br>
Primarily focused on data preservation, this script can be used to archive an entire Twitch channel at once, or quickly grab the chat from a single VOD.
</p>

## Table of Contents

  * [Features](#features)
  * [Requirements](#requirements)
  * [Installation & Usage](#installation--usage)
    * [Installation](#installation)
    * [Usage](#usage)
    * [Arguments](#arguments)
  * [Disclaimer](#disclaimer)

## Features
* Archives both video and chat logs.
* Support for subscriber-only VODs.
* Downloads as fast as your Internet connection (and storage) can handle.[^1]
* Real-time archiving of Twitch streams.[^2]
* Saves both a raw and readable chat log with timestamps and user badges.
* Supports downloading streams which aren't being archived to Twitch.
* Error notifications via pushbullet.
* Supports Twitch Turbo and channel Subscriptions (see [Wiki](https://github.com/Brisppy/twitch-archiver/wiki/Wiki#oauth-token)).

[^1]: If you wish to speed up (or slow down) the downloading of VOD pieces, supply the '--threads NUMBER' argument to the script. This changes how many download threads are used to grab the individual video files. With the default of 20, I can max out my gigabit Internet while downloading to an M.2 drive.
[^2]: There is one caveat with live archiving due to how Twitch presents ads. Ads are not downloaded, BUT while an ad is displayed, the actual stream output is not sent. This can result in missing segments under very rare circumstances, but any missing segments should be filled via a parallel VOD archival function. See the OAuth Token secion of the [wiki](https://github.com/Brisppy/twitch-archiver/wiki/Wiki#oauth-token) for how to avoid this.

## Requirements
* **[Python](https://www.python.org/) >= 3.9**
* **[FFmpeg](https://ffmpeg.org/) >= 4.3.1** and **ffprobe** (Accessible via your PATH - see [Installation](https://phoenixnap.com/kb/ffmpeg-windows))

## Installation & Usage
### Installation
Twitch Archiver can be installed via pip, setup as a docker container or installed manually.\
Make sure to read the [usage](#usage) section after installation.

#### Installing with PIP

1. Ensure you meet the above [requirements](#requirements).
2. Install [pip](https://pip.pypa.io/en/stable/installation/) if you do not already have it.
3. Download and install TA with `python -m pip install twitch-archiver`.

#### Installing Manually

1. Either download the repository via the green code button at the top of the page, or grab the latest release [here](https://github.com/Brisppy/twitch-archiver/releases/latest).
2. Unpack the archive and enter the directory with `cd twitch-archiver`.
3. Install [pip](https://pip.pypa.io/en/stable/installation/) if you do not already have it.
4. Install Python "Build" package with `python -m pip install --upgrade build`.
5. Build the package with `python -m build`, then install with `python -m pip install ./dist/twitch-archiver-*.tar.gz`.

#### Installing as a Docker Container
1. Either download the repository via the green code button at the top of the page, or grab the latest release [here](https://github.com/Brisppy/twitch-archiver/releases/latest).
2. Unpack the archive and enter the directory with `cd twitch-archiver`.
3. Build the container with `docker build . -t twitch-archiver`.
4. Run the container with the following command. *Configuration can also be provided via environment variables (see [wiki]((https://github.com/Brisppy/twitch-archiver/wiki/Wiki#environment-variables)))*.
```bash
docker run -it -v {output_dir}:/output -v {config_dir}:/config twitch-archiver -c Brisppy -d "/output" -I "/config"
```

### Usage
Run via your terminal of choice. Use `twitch-archiver -h` to see help text.

More advanced usage such as watch mode and setting up as a service can be found in the [Wiki](https://github.com/Brisppy/twitch-archiver/wiki/Wiki).

#### Examples
```# twitch-archiver -c Brisppy -d "Z:\\twitch-archive"```

Would download **video** and **chat** of all VODs from the channel **Brisppy** to the directory **Z:\twitch-archive**.

```# twitch-archiver -v 1276315849,1275305106 -d "/mnt/twitch-archive" -V -t 10```

Would download VODs **1276315849** and **1275305106** to the directory **/mnt/twitch-archive**, only saving the **video**  using **10 download threads**.

#### Arguments
Below is the output of the `--help` or `-h` command. This displays all the available arguments and a brief description of how to use them.
```
usage: __init__.py [-h] (-c CHANNEL | -v VOD) [-f] [-C] [-V] [-t THREADS]
                   [-q QUALITY] [-d DIRECTORY] [-w] [-l | -a] [-H] [-R]
                   [-L LOG_DIR] [-I CONFIG_DIR] [-W DISCORD_WEBHOOK]
                   [-p PUSHBULLET_KEY] [-o OAUTH_TOKEN] [-Q | -D] [--version]
                   [--show-config]

requires one of:
    -c CHANNEL, --channel CHANNEL / URL
            Channel(s) to download, separated with commas or a file path with `-f | --file` arg.
    -v VOD, --vod VOD_ID / URL
            VOD ID(s) to download, separated with commas or a file path with `-f | --file` arg.

Both the video and chat logs are grabbed if neither are specified.

options:
  -h, --help            show this help message and exit
  -c, --channel CHANNEL
                        A single twitch channel to download, or multiple comma-separated channels.
  -v, --vod, --vod-id VOD
                        A single VOD (e.g 12763849) or many comma-separated IDs (e.g 12763159,12753056).
  -f, --file            Denotes that the value provided to `-c | --channel` or `-v | --vod` is a
                        path to a file. Each line should contain a VOD ID or channel name.
  -C, --chat            Only save chat logs.
  -V, --video           Only save video.
  -t, --threads THREADS
                        Number of video download threads. (default: 20)
  -q, --quality QUALITY
                        Quality to download. Options are 'best', 'worst' or a custom value.
                        Format for custom values is [resolution]p[framerate], (e.g 1080p60, 720p30).
                        (default: best)
  -d, --directory DIRECTORY
                        Directory to store archived VOD(s), use TWO slashes for Windows paths.
                        (default: current directory)
  -w, --watch           Continually check every 10 seconds for new streams/VODs from a specified channel.
  -l, --live-only       Only download streams / VODs which are currently live.
  -a, --archive-only    Don't download streams / VODs which are currently live.
  -H, --highlights      Archive highlights with channel.
  -R, --real-time-archiver
                        Enable real-time stream archiver.
                        Read https://github.com/Brisppy/twitch-archiver/wiki/Wiki#real-time-archiver.
  -L, --log-dir LOG_DIR
                        Output logs to specified directory.
  -I, --config-dir CONFIG_DIR
                        Directory to store configuration and VOD database.
                        (default: C:\Users\HC\.config\twitch-archiver)
  -W, --discord-webhook DISCORD_WEBHOOK
                        Webhook URL for sending messages on error.
  -p, --pushbullet-key PUSHBULLET_KEY
                        Pushbullet key for sending pushes on error. Enabled by supplying key.
  -o, --oauth-token OAUTH_TOKEN
                        Run archiver with provided Twitch OAuth token.
  -Q, --quiet           Disable all log output.
  -D, --debug           Enable debug logs.
  --version             Show version number and exit.
  --show-config         Show saved config and exit.
```

## Disclaimer
This script is intended to be used with the express permission of any involved rights holders, and is not intended to be used to duplicate, download or steal copyrighted content or information. When downloading VODs ensure you have permission from ALL involved rights holders for the content which you are downloading, and if you have the intention to share such content, you should also have explicit permission to do so.

If your intent is to use this script to lazily rip and upload streams to another platform for your own gain without the permission of the streamer, I implore you to stop and think about what you are doing and the possible effect of doing so, and politely request that you find another method with which to steal the work of others.
