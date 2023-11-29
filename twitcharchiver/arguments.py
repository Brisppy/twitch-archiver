"""
Handles parsing and storage of arguments passed to twitch-archiver.
"""
import logging
import re
import sys

from pathlib import Path


class Arguments:
    """
    Function for parsing arguments for access later.
    """
    __args = {}
    _log = logging.getLogger()

    @classmethod
    def setup_args(cls, args):
        """
        Sets up and formats provided arguments.

        :param args: arguments object to create parameters from
        """
        for argument in args:
            cls.set(argument, args[argument])

        if cls.get('show_config'):
            try:
                with open(Path(cls.get('config_dir'), 'config.ini'), 'r', encoding='utf8') as config:
                    print(config.read())
                    sys.exit(0)
            except FileNotFoundError:
                sys.exit('Config not found. Run Twitch-Archiver once with your Client ID and Secret to generate one.')

        # validate mutual exclusivity of arguments passed via CLI and environment variables
        # required as values set via environment variables bypass argparse mutex handling
        for mutex_args in (("vod", "channel"), ("live_only", "archive_only")):
            mutex_arg_0, mutex_arg_1 = cls.get(mutex_args[0]), cls.get(mutex_args[1])
            # check if both mutex args have been set
            if mutex_arg_0 and mutex_arg_1:
                raise ValueError("Cannot accept both of the following mutually exclusive arguments: '"
                                 f"{mutex_args[0]}={mutex_arg_0}' and '{mutex_args[1]}={mutex_arg_1}'")

        # get both video and chat logs if neither selected
        if not cls.get('chat') and not cls.get('video'):
            cls.set('chat', True)
            cls.set('video', True)

        # generate list from comma-separated VODs
        try:
            if cls.get('vod'):
                cls.extract_vods_and_channels('vod')

            # generate list from comma-separated channels
            elif cls.get('channel'):
                cls.extract_vods_and_channels('channel')
        except TypeError:
            print('Error parsing provided channel or VOD argument.')

        # split quality into [resolution, framerate]
        if cls.get('quality') not in ['best', 'worst']:
            cls.set('quality', cls.get('quality').split('p'))

        if cls.get('watch'):
            print('Launching Twitch-Archiver in watch mode.')

    @classmethod
    def set(cls, name, value):
        """
        Set a specified class attribute.

        :param name: name of attribute to change
        :param value: value to set attribute to
        """
        cls.__args[name] = value

    @classmethod
    def get(cls, name=None):
        """
        Retrieve a specified attribute.

        :param name: name of attribute to retrieve value of or none to return all
        :return: value of requested attribute, or all attributes if none provided
        """
        if name is None:
            return cls.__args

        return cls.__args[name]

    @classmethod
    def extract_vods_and_channels(cls, arg_name: str):
        """
        Parses the provided `-c | --channel` or `-v | --vod-id` argument and interprets the value.

        :param arg_name: either 'channel' or 'vod' to denote which argument to parse
        :type arg_name: str
        :return: list of channels or VOD IDs
        :rtype list
        """
        # separate comma-separated values
        parsed_args: list = []

        # extract vods ids if file being passed
        if cls.get('file'):
            collected: list = []
            for arg in cls.get(arg_name).split(','):
                # convert list to Path() variables and store for further processing
                collected.extend(Arguments.load_file_line_by_line(Path(arg)))

            cls.set(arg_name, ','.join(collected))

        # format urls to just vod ids or channel names
        for arg in cls.get(arg_name).split(','):
            # skip empty args
            if arg == '':
                continue

            # extract VOD ID or channel name if url passed
            if '/videos/' in arg:
                match = re.findall(r"(?<=twitch\.tv/videos/)[0-9]*", arg)
            else:
                match = re.findall(r"(?<=twitch\.tv/)[a-zA-Z]*", arg)

            # store the extracted value or simply pass to passed args if no match found
            if match:
                parsed_args.append(match[0])

            else:
                parsed_args.append(arg)

        cls.set(arg_name, parsed_args)

    @classmethod
    def load_file_line_by_line(cls, file_path: Path):
        """
        Loads a given file line by line into the provided configuration variable.

        :return: list containing all file lines
        :rtype: list[str]
        """
        try:
            with open(Path(file_path), 'r') as _fp:
                return [line.rstrip() for line in _fp]

        except Exception as exc:
            cls._log.error('Failed to read from provided input file. %s', exc)
            return None
