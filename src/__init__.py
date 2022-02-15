import argparse
import os
import textwrap

from pathlib import Path

from src.arguments import Arguments
from src.configuration import Configuration
from src.logger import Logger
from src.processing import Processing
from src.twitch import Twitch

__name__ = 'twitch-archiver'
__version__ = '2.0'


def main():
    """
    Main processing for twitch-archiver.
    """
    parser = argparse.ArgumentParser(argument_default=None, description=textwrap.dedent(f"""\
    Twitch Archiver v{__version__} - https://github.com/Brisppy/twitch-archiver

    A fast, platform-independent Python script for downloading past and present Twitch VODs and chat logs.

    By default, both the video and chat of a specified VOD is downloaded.

    requires one of:
        -c CHANNEL, --channel CHANNEL
                Channel(s) to download, comma separated if multiple provided.
        -v VOD_ID, --vod-id VOD_ID
                VOD ID(s) to download, comma separated if multiple provided.

    credentials provided with: (or provided with config file)
        -i CLIENT_ID, --client-id CLIENT_ID
                Client ID retrieved from dev.twitch.tv
        -s CLIENT_SECRET, --client-secret CLIENT_SECRET
                Client secret retrieved from dev.twitch.tv
    """), formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('-c', '--channel', type=str, action='store',
                      help='A single twitch channel to download, or multiple comma-separated channels.')
    mode.add_argument('-v', '--vod-id', type=str, action='store',
                      help='A single VOD ID (-v 12763849), or multiple comma-separated VOD IDs (-v 12763159,12753056)')
    parser.add_argument('-i', '--client-id', action='store', help='Client ID retrieved from dev.twitch.tv')
    parser.add_argument('-s', '--client-secret', action='store', help='Client secret retrieved from dev.twitch.tv')
    parser.add_argument('-d', '--directory', action='store',
                        help='Directory to store archived VOD(s), use TWO slashes for Windows paths. '
                             '(default: %(default)s)',
                        default=Path(os.getcwd()))
    parser.add_argument('-C', '--chat', action='store_true', help='Only save chat logs.')
    parser.add_argument('-V', '--video', action='store_true', help='Only save video.')
    parser.add_argument('-t', '--threads', type=int, action='store',
                        help='Number of video download threads. (default: %(default)s)', default=20)
    parser.add_argument('-p', '--pushbullet-key', action='store',
                        help='Pushbullet key for sending pushes on error. Enabled by supplying key.', default=False)
    parser.add_argument('-Q', '--quiet', action='store_true', help='Disable all log output.', default=False)
    parser.add_argument('-D', '--debug', action='store_true', help='Enable debug logs.', default=False)
    parser.add_argument('-L', '--log-file', action='store', help='Output logs to specified file.', default=False)
    parser.add_argument('-I', '--config-dir', action='store', type=Path,
                        help='Directory to store configuration, VOD database and lock files. (default: %(default)s)',
                        default=Path(os.path.expanduser("~"), '.config', 'twitch-archiver'))
    parser.add_argument('--version', action='version', version=f'{__name__} v{__version__}',
                        help='Show version number and exit.')

    # setup arguments
    args = Arguments()
    args.setup_args(parser.parse_args().__dict__)

    # setup logging
    log = Logger.setupLogger(args.get('debug'), args.get('log_file'))
    log.debug('Debug logging enabled.')
    log.debug('Arguments: ' + str(args.get()))

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
    callTwitch = Twitch(config.get())
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
