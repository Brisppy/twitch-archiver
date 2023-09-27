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
    def __init__(self, args):
        self.__args = {}
        self.setup_args(args)

    def setup_args(self, args):
        """Sets up and formats provided arguments.

        :param args: arguments object to create parameters from
        """
        for argument in args:
            self.set(argument, args[argument])

        if self.get('show_config'):
            try:
                with open(Path(self.get('config_dir'), 'config.ini'), 'r', encoding='utf8') as config:
                    print(config.read())
                    sys.exit(0)
            except FileNotFoundError:
                sys.exit('Config not found. Run Twitch-Archiver once with your Client ID and Secret to generate one.')

        # validate mutual exclusivity of arguments passed via CLI and environment variables
        # required as values set via environment variables bypass argparse mutex handling
        for mutex_args in (("vod_id", "channel"), ("live_only", "archive_only")):
            mutex_arg_0, mutex_arg_1 = self.get(mutex_args[0]), self.get(mutex_args[1])
            # check if both mutex args have a value (including empty string)
            if mutex_arg_0 is not None and mutex_arg_1 is not None:
                raise ValueError("Cannot accept both of the following mutually exclusive arguments: '"
                                 f"{mutex_args[0]}={mutex_arg_0}' and '{mutex_args[1]}={mutex_arg_1}'")

        # get both video and chat logs if neither selected
        if not self.get('chat') and not self.get('video'):
            self.set('chat', True)
            self.set('video', True)

        # generate list from comma-separated vods
        if self.get('vod_id'):
            self.parse_vods_or_channels('vod_id')

        # generate list from comma-separated channels
        elif self.get('channel'):
            self.parse_vods_or_channels('channel')

        # split quality into [resolution, framerate]
        if self.get('quality') not in ['best', 'worst']:
            self.set('quality', self.get('quality').split('p'))

        if self.get('watch'):
            print('Launching Twitch-Archiver in watch mode.')

    def set(self, name, value):
        """Set a specified class attribute.

        :param name: name of attribute to change
        :param value: value to set attribute to
        """
        self.__args[name] = value

    def get(self, name=None):
        """Retrieve a specified attribute.

        :param name: name of attribute to retrieve value of or none to return all
        :return: value of requested attribute, or all attributes if none provided
        """
        if name is None:
            return self.__args

        return self.__args[name]

    def parse_vods_or_channels(self, arg_name: str):
        """
        Parses the provided `-c | --channel` or `-v | --vod-id` argument and interprets the value.

        :param arg_name: either 'channel' or 'vod' to denote which argument to parse
        :type arg_name: str
        :return: list of channels or VOD IDs
        :rtype list
        """
        # separate comma-separated values
        parsed_args = list(self.get(arg_name).split(','))

        # format urls to just vod ids or channel names
        for idx, arg in enumerate(parsed_args):
            # test match and replace
            if '/videos/' in arg:
                match = re.findall(r"(?<=twitch\.tv/videos/)[0-9]*", arg)
            else:
                match = re.findall(r"(?<=twitch\.tv/)[a-zA-Z]*", arg)

            if match:
                parsed_args[idx] = match[0]

        if self.get('from-file'):
            # convert list to Path() variables
            parsed_args = [Path(arg) for arg in parsed_args]

        self.set(arg_name, parsed_args)
