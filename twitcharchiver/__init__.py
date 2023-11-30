r"""
 _______ ___ ___ ___ _______ _______ ___ ___  _______ _______ _______ ___ ___ ___ ___ ___ _______ _______
|       |   Y   |   |       |   _   |   Y   ||   _   |   _   |   _   |   Y   |   |   Y   |   _   |   _   \
|.|   | |.  |   |.  |.|   | |.  1___|.  1   ||.  1   |.  l   |.  1___|.  1   |.  |.  |   |.  1___|.  l   /
`-|.  |-|. / \  |.  `-|.  |-|.  |___|.  _   ||.  _   |.  _   |.  |___|.  _   |.  |.  |   |.  __)_|.  _   1
  |:  | |:      |:  | |:  | |:  1   |:  |   ||:  |   |:  |   |:  1   |:  |   |:  |:  1   |:  1   |:  |   |
  |::.| |::.|:. |::.| |::.| |::.. . |::.|:. ||::.|:. |::.|:. |::.. . |::.|:. |::.|\:.. ./|::.. . |::.|:. |
  `---' `--- ---`---' `---' `-------`--- ---'`--- ---`--- ---`-------`--- ---`---' `---' `-------`--- ---'
Created by:
    https://github.com/Brisppy
Inspired by:
    https://github.com/PetterKraabol/Twitch-Chat-Downloader/
    https://github.com/ihabunek/twitch-dl
    https://github.com/streamlink/streamlink
Twitch Archiver - A simple, fast, platform-independent tool for downloading Twitch streams, videos, and chat logs.
Copyright (C) 2023 https://github.com/Brisppy

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.
You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import argparse
import os
import sys
import tempfile
import textwrap

from pathlib import Path
from time import sleep

from twitcharchiver.arguments import Arguments
from twitcharchiver.channel import Channel
from twitcharchiver.configuration import Configuration
from twitcharchiver.logger import Logger
from twitcharchiver.processing import Processing
from twitcharchiver.utils import getenv, check_update_available, get_latest_version

__version__ = '4.0.0.rc3'

from twitcharchiver.vod import Vod, ArchivedVod


def main():
    """
    Main processing for twitch-archiver.
    """
    parser = argparse.ArgumentParser(argument_default=None, description=textwrap.dedent(f"""\
    Twitch Archiver v{__version__} - https://github.com/Brisppy/twitch-archiver

    A fast, platform-independent Python script for downloading past and present Twitch VODs and chat logs.

    requires one of:
        -c CHANNEL, --channel CHANNEL / URL
                Channel(s) to download, separated with commas or a file path with `-f | --file` arg.
        -v VOD, --vod VOD_ID / URL
                VOD ID(s) to download, separated with commas or a file path with `-f | --file` arg.
                
    Both the video and chat logs are grabbed if neither are specified.
    """), formatter_class=argparse.RawTextHelpFormatter)
    mode = parser.add_mutually_exclusive_group(
        required=not (('--show-config' in sys.argv) or
                      (
                              (getenv("TWITCH_ARCHIVER_CHANNEL")) is not None) or
                      (getenv("TWITCH_ARCHIVER_VOD") is not None)
                      ))
    stream = parser.add_mutually_exclusive_group(required=False)
    loglevel = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument('-c', '--channel', type=str, action='store',
                      help='A single twitch channel to download, or multiple comma-separated channels.',
                      default=getenv("TWITCH_ARCHIVER_CHANNEL"))
    mode.add_argument('-v', '--vod', '--vod-id', type=str, action='store',
                      help='A single VOD (e.g 12763849) or many comma-separated IDs (e.g 12763159,12753056).',
                      default=getenv("TWITCH_ARCHIVER_VOD_ID"))
    parser.add_argument('-f', '--file', action='store_true',
                        help='Denotes that the value provided to `-c | --channel` or `-v | --vod` is a\n'
                             'path to a file. Each line should contain a VOD ID or channel name.', default=False)
    parser.add_argument('-C', '--chat', action='store_true', help='Only save chat logs.',
                        default=getenv("TWITCH_ARCHIVER_CHAT", False, True))
    parser.add_argument('-V', '--video', action='store_true', help='Only save video.',
                        default=getenv("TWITCH_ARCHIVER_VIDEO", False, True))
    parser.add_argument('-t', '--threads', type=int, action='store',
                        help='Number of video download threads. (default: %(default)s)',
                        default=getenv("TWITCH_ARCHIVER_THREADS", 20))
    parser.add_argument('-q', '--quality', type=str, action='store',
                        help="Quality to download. Options are 'best', 'worst' or a custom value.\n"
                             'Format for custom values is [resolution]p[framerate], (e.g 1080p60, 720p30).\n'
                             '(default: best)', default='best')
    parser.add_argument('-d', '--directory', action='store',
                        help='Directory to store archived VOD(s), use TWO slashes for Windows paths.\n'
                             '(default: current directory)', type=Path,
                        default=getenv('TWITCH_ARCHIVER_DIRECTORY', Path(os.getcwd())))
    parser.add_argument('-w', '--watch', action='store_true',
                        help='Continually check every 10 seconds for new streams/VODs from a specified channel.',
                        default=getenv('TWITCH_ARCHIVER_WATCH', False, True))
    stream.add_argument('-l', '--live-only', action='store_true',
                        default=getenv('TWITCH_ARCHIVER_LIVE_ONLY', False, True),
                        help='Only download streams / VODs which are currently live.')
    stream.add_argument('-a', '--archive-only', action='store_true',
                        help="Don't download streams / VODs which are currently live.",
                        default=getenv("TWITCH_ARCHIVER_ARCHIVE_ONLY", False, True))
    parser.add_argument('-R', '--real-time-archiver', action='store_true',
                        help="Enable real-time stream archiver.\n"
                             "Read https://github.com/Brisppy/twitch-archiver/wiki/Wiki#real-time-archiver.",
                        default=getenv('TWITCH_ARCHIVER_REAL_TIME_ARCHIVER', False, True))
    parser.add_argument('-L', '--log-dir', action='store', help='Output logs to specified directory.', type=Path,
                        default=getenv("TWITCH_ARCHIVER_LOG_FILE", False))
    parser.add_argument('-I', '--config-dir', action='store', type=Path,
                        help='Directory to store configuration and VOD database.\n(default: %(default)s)',
                        default=getenv('TWITCH_ARCHIVER_CONFIG_DIR',
                                       Path(os.path.expanduser("~"), '.config', 'twitch-archiver')))
    parser.add_argument('-p', '--pushbullet-key', action='store',
                        help='Pushbullet key for sending pushes on error. Enabled by supplying key.',
                        default=getenv("TWITCH_ARCHIVER_PUSHBULLET_KEY", default_val=''))
    loglevel.add_argument('-Q', '--quiet', action='store_true', help='Disable all log output.')
    loglevel.add_argument('-D', '--debug', action='store_true', help='Enable debug logs.')
    parser.add_argument('--version', action='version', version=f'Twitch Archiver v{__version__}',
                        help='Show version number and exit.')
    parser.add_argument('--show-config', action='store_true', help='Show saved config and exit.', default=False)

    # setup arguments
    args = Arguments()
    args.setup_args(parser.parse_args().__dict__)

    # setup logging
    log = Logger.setup_logger(args.get('quiet'), args.get('debug'), args.get('log_dir'))
    log.debug('Debug logging enabled.')

    # debug only: output sanitized version of arguments
    args_sanitized = args.get().copy()
    for key in ['pushbullet_key']:
        if args_sanitized[key]:
            args_sanitized.update({key: 24 * '*' + args_sanitized[key][24:]})

    log.debug('Arguments: %s', args_sanitized)

    # compare with current git version
    latest_version, release_notes = get_latest_version()
    if check_update_available(__version__, latest_version):
        log.warning('New version of Twitch-Archiver available - Version %s:\n'
                    'https://github.com/Brisppy/twitch-archiver/releases/latest\nRelease notes:\n\n%s\n',
                    latest_version, release_notes)
    else:
        log.info('Twitch Archiver v%s - https://github.com/Brisppy/twitch-archiver', __version__)

    # load configuration from ini
    config = Configuration()
    config.load_config(Path(args.get('config_dir'), 'config.ini'))
    log.debug('Settings prior to loading config: %s', config.get_sanitized())

    # overwrite different or missing configuration variables
    config.generate_config(args.get())
    log.debug('Settings after loading config: %s', config.get_sanitized())

    # create temp dir for downloads and lock files
    Path(tempfile.gettempdir(), 'twitch-archiver').mkdir(exist_ok=True)

    process = Processing(Configuration.get())

    if args.get('channel') is not None:
        channels = [Channel(c) for c in args.get('channel')]

        while True:
            process.get_channel(channels)

            if args.get('watch'):
                sleep(10)

            else:
                break

    elif args.get('vod') is not None:
        vods = [ArchivedVod.convert_from_vod(Vod(v)) for v in args.get('vod')]

        process.vod_downloader(vods)


if __name__ == '__main__':
    main()
