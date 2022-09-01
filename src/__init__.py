import argparse
import os
import sys
import textwrap

from pathlib import Path
from time import sleep

from src.arguments import Arguments
from src.configuration import Configuration
from src.exceptions import TwitchAPIError
from src.logger import Logger
from src.processing import Processing
from src.twitch import Twitch
from src.utils import Utils

__name__ = 'twitch-archiver'
__version__ = '2.1.1'


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
    mode = parser.add_mutually_exclusive_group(required=False if '--show-config' in sys.argv else True)
    stream = parser.add_mutually_exclusive_group(required=False)
    loglevel = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument('-c', '--channel', type=str, action='store',
                      help='A single twitch channel to download, or multiple comma-separated channels.')
    mode.add_argument('-v', '--vod-id', type=str, action='store',
                      help='A single VOD (e.g 12763849) or many comma-separated IDs (e.g 12763159,12753056).')
    parser.add_argument('-i', '--client-id', action='store', help='Client ID retrieved from dev.twitch.tv')
    parser.add_argument('-s', '--client-secret', action='store', help='Client secret retrieved from dev.twitch.tv')
    parser.add_argument('-C', '--chat', action='store_true', help='Only save chat logs.')
    parser.add_argument('-V', '--video', action='store_true', help='Only save video.')
    parser.add_argument('-t', '--threads', type=int, action='store',
                        help='Number of video download threads. (default: %(default)s)', default=20)
    parser.add_argument('-q', '--quality', type=str, action='store',
                        help="Quality to download. Options are 'best', 'worst' or a custom value.\n"
                             'Format for custom values is [resolution]p[framerate], (e.g 1080p60, 720p30).\n'
                             '(default: best)', default='best')
    parser.add_argument('-d', '--directory', action='store',
                        help='Directory to store archived VOD(s), use TWO slashes for Windows paths.\n'
                             '(default: %(default)s)', type=Path, default=Path(os.getcwd()))
    parser.add_argument('-w', '--watch', action='store_true',
                        help='Continually check every 10 seconds for new streams/VODs from a specified channel.')
    stream.add_argument('-S', '--stream-only', action='store_true',
                        help='Only download streams which are currently live.',
                        default=False)
    stream.add_argument('-N', '--no-stream', action='store_true',
                        help="Don't download streams which are currently live.",
                        default=False)
    parser.add_argument('-L', '--log-file', action='store', help='Output logs to specified file.', type=Path,
                        default=False)
    parser.add_argument('-I', '--config-dir', action='store', type=Path,
                        help='Directory to store configuration, VOD database and lock files.\n(default: %(default)s)',
                        default=Path(os.path.expanduser("~"), '.config', 'twitch-archiver'))
    parser.add_argument('-p', '--pushbullet-key', action='store',
                        help='Pushbullet key for sending pushes on error. Enabled by supplying key.', default=False)
    loglevel.add_argument('-Q', '--quiet', action='store_const', help='Disable all log output.', const=50, default=0)
    loglevel.add_argument('-D', '--debug', action='store_const', help='Enable debug logs.', const=10, default=0)
    parser.add_argument('--version', action='version', version=f'{__name__} v{__version__}',
                        help='Show version number and exit.')
    parser.add_argument('--show-config', action='store_true', help='Show saved config and exit.', default=False)

    # setup arguments
    args = Arguments()
    args.setup_args(parser.parse_args().__dict__)

    # setup logging
    log = Logger.setup_logger(args.get('quiet') + args.get('debug'), args.get('log_file'))
    log.debug('Debug logging enabled.')

    args_sanitized = args.get()
    for key in ['client_id', 'client_secret', 'pushbullet_key']:
        if args_sanitized[key]:
            args_sanitized.update({key: 24 * '*' + args_sanitized[key][24:]})

    log.debug(f'Arguments: {args_sanitized}')

    # compare with current git version
    latest_version, release_notes = Utils.get_latest_version()
    if Utils.version_tuple(__version__) < Utils.version_tuple(latest_version):
        log.warning(f'New version of Twitch-Archiver available - Version {latest_version}:\n'
                    f'https://github.com/Brisppy/twitch-archiver/releases/latest\nRelease notes:\n\n{release_notes}\n')
    else:
        log.info(f'Twitch Archiver v{__version__} - https://github.com/Brisppy/twitch-archiver')

    # load configuration from ini
    config = Configuration()
    config.load_config(Path(args.get('config_dir'), 'config.ini'))
    log.debug(f'Settings prior to loading config: {config.get_sanitized()}')

    # overwrite different or missing configuration variables
    config.generate_config(args.get())
    log.debug(f'Settings after loading config: {config.get_sanitized()}')

    # prompt if client id or secret empty
    if config.get('client_id') == '' or config.get('client_secret') == '':
        log.info('No client_id or client_secret passed as argument or found in config file.')
        config.set('client_id', input('Your client ID: '))
        config.set('client_secret', input('Your client secret: '))

    log.debug('Performing Twitch authentication.')
    callTwitch = Twitch(config.get('client_id'), config.get('client_secret'), config.get('oauth_token'))
    # generate oauth token if it is missing, is invalid, or expiring soon
    if config.get('oauth_token') == '' or callTwitch.validate_oauth_token() < 604800:
        log.debug('No OAuth token found, or token is invalid or expiring soon - generating a new one.')
        try:
            config.set('oauth_token', callTwitch.generate_oauth_token())
            log.debug(f'New OAuth token is: {config.get_sanitized("oauth_token")}')
            # store returned token
            config.save(Path(args.get('config_dir'), 'config.ini'))
        except TwitchAPIError as e:
            log.error(f'OAuth token generation failed. Error: {str(e)}')
            Utils.send_push(config.get('pushbullet_key'), 'OAuth token generation failed.', str(e))
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
