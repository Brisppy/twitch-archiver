import argparse
import os
import sys
import textwrap

from pathlib import Path

from src.arguments import Arguments
from src.configuration import Configuration
from src.logger import Logger
from src.processing import Processing
from src.twitch import Twitch
from src.utils import Utils

__name__ = 'twitch-archiver'
__version__ = '2.0'


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
    loglevel = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument('-c', '--channel', type=str, action='store',
                      help='A single twitch channel to download, or multiple comma-separated channels.')
    mode.add_argument('-v', '--vod-id', type=str, action='store',
                      help='A single VOD ID (12763849) or multiple comma-separated VOD IDs (12763159,12753056)')
    parser.add_argument('-i', '--client-id', action='store', help='Client ID retrieved from dev.twitch.tv')
    parser.add_argument('-s', '--client-secret', action='store', help='Client secret retrieved from dev.twitch.tv')
    parser.add_argument('-C', '--chat', action='store_true', help='Only save chat logs.')
    parser.add_argument('-V', '--video', action='store_true', help='Only save video.')
    parser.add_argument('-t', '--threads', type=int, action='store',
                        help='Number of video download threads. (default: %(default)s)', default=20)
    parser.add_argument('-d', '--directory', action='store',
                        help='Directory to store archived VOD(s), use TWO slashes for Windows paths.\n'
                             '(default: %(default)s)',
                        default=Path(os.getcwd()))
    parser.add_argument('-L', '--log-file', action='store', help='Output logs to specified file.', default=False)
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
    log.debug('Arguments: ' + str(args.get()))

    # compare with current git version
    latest_version, release_notes = Utils.get_latest_version()
    if Utils.version_tuple(__version__) < Utils.version_tuple(latest_version):
        log.warning(f'New update available: {__version__} < {latest_version}'
                    f'. See https://github.com/Brisppy/twitch-archiver/releases/latest.\n'
                    f'Release notes:\n\n'
                    f'{release_notes}')

    # load configuration from ini
    config = Configuration()
    config.load_config(Path(args.get('config_dir'), 'config.ini'))
    log.debug('Settings prior to loading config: ' + str(config.get()))

    # overwrite different or missing configuration variables
    config.generate_config(args.get())
    log.debug('Settings after loading config: ' + str(config.get()))

    # prompt if client id or secret empty
    if config.get('client_id') == '' or config.get('client_secret') == '':
        log.info('No client_id or client_secret passed as argument or found in config file.')
        config.set('client_id', input('Your client ID: '))
        config.set('client_secret', input('Your client secret: '))

    log.debug('Performing Twitch authentication.')
    callTwitch = Twitch(config.get('client_id'), config.get('client_secret'), config.get('oauth_token'))
    # generate oauth token if it is missing, or expires soon
    if config.get('oauth_token') == '' or callTwitch.validate_oauth_token() < 604800:
        log.debug('No OAuth token found, or OAuth token expiring soon - generating a new one.')
        config.set('oauth_token', callTwitch.generate_oauth_token())
        log.debug('New OAuth token is: ' + config.get('oauth_token'))
        # store returned token
        config.save(Path(args.get('config_dir'), 'config.ini'))

    process = Processing(config.get(), args.get())

    if args.get('channel') is not None:
        process.get_channel(args.get('channel'))

    elif args.get('vod_id') is not None:
        process.get_vods(args.get('vod_id'))
