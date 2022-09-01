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
                with open(Path(Arguments.get('config_dir'), 'config.ini'), 'r') as config:
                    print(config.read())
                    sys.exit(0)
            except FileNotFoundError:
                sys.exit('Config not found. Run Twitch-Archiver once with your Client ID and Secret to generate one.')

        # get both video and chat logs if neither selected
        if not Arguments.get('chat') and not Arguments.get('video'):
            Arguments.set('chat', True)
            Arguments.set('video', True)

        # generate list from comma-separated vods
        if Arguments.get('vod_id'):
            # generate vod list
            vod_ids = [vod_id for vod_id in Arguments.get('vod_id').split(',')]

            # format urls to just vod ids
            for i in range(len(vod_ids)):
                # test match and replace
                match = re.findall("(?<=twitch\.tv\/videos\/)[0-9]*", vod_ids[i])
                if match:
                    vod_ids[i] = match[0]

            # insert formatted vods
            Arguments.set('vod_id', vod_ids)

        # generate list from comma-separated channels
        elif Arguments.get('channel'):
            # generate channel list
            channels = [channel for channel in Arguments.get('channel').split(',')]

            # format urls to just channel name
            for i in range(len(channels)):
                # test and replace
                match = re.findall("(?<=twitch\.tv\/)[a-zA-Z0-9]*", channels[i])
                if match:
                    channels[i] = match[0]

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
