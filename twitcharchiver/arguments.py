"""
Handles parsing and storage of arguments passed to twitch-archiver.
"""

import re
import sys

from pathlib import Path


class Arguments:
    """
    Function for parsing arguments for access later.
    """
    __args = {}

    @staticmethod
    def setup_args(args):
        """Sets up and formats provided arguments.

        :param args: arguments object to create parameters from
        """
        for argument in args:
            Arguments.set(argument, args[argument])

        if Arguments.get('show_config'):
            try:
                with open(Path(Arguments.get('config_dir'), 'config.ini'), 'r', encoding='utf8') as config:
                    print(config.read())
                    sys.exit(0)
            except FileNotFoundError:
                sys.exit('Config not found. Run Twitch-Archiver once with your Client ID and Secret to generate one.')

        # validate mutual exclusivity of arguments passed via CLI and environment variables
        # required as values set via environment variables bypass argparse mutex handling
        for mutex_args in (("vod_id", "channel"), ("live_only", "archive_only")):
            mutex_arg_0, mutex_arg_1 = Arguments.get(mutex_args[0]), Arguments.get(mutex_args[1])
            # check if both mutex args have a value (including empty string)
            if mutex_arg_0 is not None and mutex_arg_1 is not None:
                raise ValueError("Cannot accept both of the following mutually exclusive arguments: '"
                                 f"{mutex_args[0]}={mutex_arg_0}' and '{mutex_args[1]}={mutex_arg_1}'")

        # get both video and chat logs if neither selected
        if not Arguments.get('chat') and not Arguments.get('video'):
            Arguments.set('chat', True)
            Arguments.set('video', True)

        # generate list from comma-separated vods
        if Arguments.get('vod_id'):
            # generate vod list
            vod_ids = list(Arguments.get('vod_id').split(','))

            # format urls to just vod ids
            for idx, vod_id in enumerate(vod_ids):
                # test match and replace
                match = re.findall(r"(?<=twitch\.tv/videos/)[0-9]*", vod_id)
                if match:
                    vod_ids[idx] = match[0]

            # insert formatted vods
            Arguments.set('vod_id', vod_ids)

        # generate list from comma-separated channels
        elif Arguments.get('channel'):
            # generate channel list
            channels = list(Arguments.get('channel').split(','))

            # format urls to just channel name
            for idx, channel in enumerate(channels):
                # test and replace
                match = re.findall(r"(?<=twitch\.tv/)[a-zA-Z0-9]*", channel)
                if match:
                    channels[idx] = match[0]

            # insert formatted channels
            Arguments.set('channel', channels)

        # split quality into [resolution, framerate]
        if Arguments.get('quality') not in ['best', 'worst']:
            Arguments.set('quality', Arguments.get('quality').split('p'))

        if Arguments.get('watch'):
            print('Launching Twitch-Archiver in watch mode.')

    @staticmethod
    def set(name, value):
        """Set a specified class attribute.

        :param name: name of attribute to change
        :param value: value to set attribute to
        """
        Arguments.__args[name] = value

    @staticmethod
    def get(name=None):
        """Retrieve a specified attribute.

        :param name: name of attribute to retrieve value of or none to return all
        :return: value of requested attribute, or all attributes if none provided
        """
        if name is None:
            return Arguments.__args

        return Arguments.__args[name]
