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
import textwrap

from pathlib import Path
from time import sleep

from twitcharchiver.arguments import Arguments
from twitcharchiver.configuration import Configuration
from twitcharchiver.exceptions import TwitchAPIError
from twitcharchiver.logger import Logger
from twitcharchiver.processing import Processing
from twitcharchiver.twitch import Twitch
from twitcharchiver.utils import getenv, send_push, get_latest_version, version_tuple, check_update_available

__version__ = '3.0.1'


def main():
    """
    Main processing for twitch-archiver.
    """
    parser = argparse.ArgumentParser(argument_default=None, description=textwrap.dedent(f"""\
    Twitch Archiver v{__version__} - https://github.com/Brisppy/twitch-archiver

    A fast, platform-independent Python script for downloading past and present Twitch VODs and chat logs.

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
    """), formatter_class=argparse.RawTextHelpFormatter)
    mode = parser.add_mutually_exclusive_group(
        required=not (('--show-config' in sys.argv) or
                      (
                      (getenv("TWITCH_ARCHIVER_CHANNEL")) is not None) or
                      (getenv("TWITCH_ARCHIVER_VOD_ID") is not None)
                      ))
    stream = parser.add_mutually_exclusive_group(required=False)
    loglevel = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument('-c', '--channel', type=str, action='store',
                      help='A single twitch channel to download, or multiple comma-separated channels.',
                      default=getenv("TWITCH_ARCHIVER_CHANNEL"))
    mode.add_argument('-v', '--vod-id', type=str, action='store',
                      help='A single VOD (e.g 12763849) or many comma-separated IDs (e.g 12763159,12753056).',
                      default=getenv("TWITCH_ARCHIVER_VOD_ID"))
    parser.add_argument('-i', '--client-id', action='store', help='Client ID retrieved from dev.twitch.tv',
                        default=getenv("TWITCH_ARCHIVER_CLIENT_ID"))
    parser.add_argument('-s', '--client-secret', action='store', help='Client secret retrieved from dev.twitch.tv',
                        default=getenv("TWITCH_ARCHIVER_CLIENT_SECRET"))
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
                             '(default: %(default)s)', type=Path,
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
    stream.add_argument('-R', '--real-time-archiver', action='store_true',
                        help="Enable real-time stream archiver.\n"
                             "Read https://github.com/Brisppy/twitch-archiver/wiki/Wiki#real-time-archiver.",
                        default=getenv('TWITCH_ARCHIVER_REAL_TIME_ARCHIVER', False, True))
    parser.add_argument('-L', '--log-file', action='store', help='Output logs to specified file.', type=Path,
                        default=getenv("TWITCH_ARCHIVER_LOG_FILE", False))
    parser.add_argument('-I', '--config-dir', action='store', type=Path,
                        help='Directory to store configuration, VOD database and lock files.\n(default: %(default)s)',
                        default=getenv('TWITCH_ARCHIVER_CONFIG_DIR',
                                       Path(os.path.expanduser("~"), '.config', 'twitch-archiver')))
    parser.add_argument('-p', '--pushbullet-key', action='store',
                        help='Pushbullet key for sending pushes on error. Enabled by supplying key.',
                        default=getenv("TWITCH_ARCHIVER_PUSHBULLET_KEY", False))
    loglevel.add_argument('-Q', '--quiet', action='store_const', help='Disable all log output.', const=50, default=0)
    loglevel.add_argument('-D', '--debug', action='store_const', help='Enable debug logs.', const=10, default=0)
    parser.add_argument('--version', action='version', version=f'Twitch Archiver v{__version__}',
                        help='Show version number and exit.')
    parser.add_argument('--show-config', action='store_true', help='Show saved config and exit.', default=False)

    # setup arguments
    args = Arguments()
    args.setup_args(parser.parse_args().__dict__)

    # setup logging
    log = Logger.setup_logger(args.get('quiet') + args.get('debug'), args.get('log_file'))
    log.debug('Debug logging enabled.')

    # debug only: output sanitized version of arguments
    args_sanitized = args.get().copy()
    for key in ['client_id', 'client_secret', 'pushbullet_key']:
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

    # prompt if client id or secret empty
    if config.get('client_id') == '' or config.get('client_secret') == '':
        log.info('No client_id or client_secret passed as argument or found in config file.')
        config.set('client_id', input('Your client ID: '))
        config.set('client_secret', input('Your client secret: '))

    log.debug('Performing Twitch authentication.')
    call_twitch = Twitch(config.get('client_id'), config.get('client_secret'), config.get('oauth_token'))
    # generate oauth token if it is missing, is invalid, or expiring soon
    if config.get('oauth_token') == '' or call_twitch.validate_oauth_token() < 604800:
        log.debug('No OAuth token found, or token is invalid or expiring soon - generating a new one.')
        try:
            config.set('oauth_token', call_twitch.generate_oauth_token())
            log.debug('New OAuth token is: %s', config.get_sanitized("oauth_token"))
            # store returned token
            config.save(Path(args.get('config_dir'), 'config.ini'))
        except TwitchAPIError as err:
            log.error('OAuth token generation failed. Error: %s', str(err))
            send_push(config.get('pushbullet_key'), 'OAuth token generation failed.', str(err))
            sys.exit(1)

    process = Processing(config.get(), args.get())

    while True:
        if args.get('channel') is not None:
            process.get_channel(args.get('channel'))

        if args.get('watch'):
            sleep(10)

        else:
            break

    if args.get('vod_id') is not None:
        for vod_id in args.get('vod_id'):
            process.get_vod_connector(vod_id, args.get('video'), args.get('chat'))


if __name__ == '__main__':
    main()
