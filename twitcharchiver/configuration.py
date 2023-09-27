"""
Module for generating, saving and retrieving configuration values.
"""

import configparser
import logging
import os


class Configuration:
    """
    Generation, saving and loading of twitch-archive configuration.
    """
    def __init__(self):
        self.__conf = {}
        self.log = logging.getLogger()

    def generate_config(self, args):
        """Generates the required configuration from provided arguments, overwriting loaded settings.

        :param args: dict of arguments to generate config from
        :type args: dict
        """
        self.log.debug('Generating config from provided arguments.')

        # if setting loaded from config differs from passed arg (and arg is not none), overwrite it
        for argument in args:
            if argument in self.get() and args[argument] != self.get(argument) \
                    and args[argument] not in [None, False]:
                self.set(argument, args[argument])

    def load_config(self, conf_file):
        """Loads the settings stored in the configuration ini file.

        :param conf_file: path to configuration file
        """
        # create conf file if it doesn't exist
        if not os.path.isfile(conf_file):
            self.log.debug('Config file not found - creating one now.')
            self.create_config_file(conf_file)

        self.log.debug('Loading config from file.')

        config = configparser.ConfigParser()
        config.read(conf_file)

        # load individual settings from file
        for setting in config['settings']:
            self.set(setting, config['settings'][setting])

    def create_config_file(self, conf_file):
        """Creates a configuration file for the storing of settings.\n

        :param conf_file: path to configuration file
        """
        self.log.debug('Creating directories for configuration file.')
        os.makedirs(conf_file.parent, exist_ok=True)

        config = configparser.ConfigParser()
        config.add_section('settings')
        self.log.debug('Current config: %s', self.get())

        for setting in self.__conf:
            config.set('settings', setting, self.get(setting))

        self.log.debug('Writing config to %s', conf_file)

        with open(conf_file, 'w', encoding='utf8') as f:
            config.write(f)

    def set(self, name, value):
        """Set a specified attribute.

        :param name:  name of attribute to change
        :param value: value to set attribute to
        """
        if name in self.__conf:
            self.__conf[name] = value

        else:
            self.log.debug("Configuration variable %s from file could not be matched to a runtime variable.", name)

    def get(self, name=None):
        """Retrieve a specified attribute.

        :param name: name of attribute to retrieve value of - 'None' returns all attributes
        :return: requested value(s)
        """
        if name is None:
            return self.__conf

        return self.__conf[name]

    def get_sanitized(self, name=None):
        """Retrieves a specified attribute, sanitizing secrets.

        :param name: name of attribute to retrieve value of - 'None' returns all attributes
        :return: requested value(s)
        """
        configuration = self.__conf.copy()
        for key in ['pushbullet_key']:
            if configuration[key] != '':
                configuration.update({key: 24 * '*' + configuration[key][24:]})

        if name is None:
            return configuration

        return configuration[name]

    # reference:
    #   https://stackoverflow.com/questions/35247900/python-creating-an-ini-or-config-file-in-the-users-home-directory
    def save(self, conf_file, name=None):
        """
        Saves the running configuration to the configuration ini.
        """
        self.log.debug('Saving config variable(s) to ini file.')

        # import saved config
        config = configparser.ConfigParser()
        config.read(conf_file)

        # overwrite all vars
        if name is None:
            # overwrite with running config
            for setting in Configuration.get():
                config.set('settings', setting, str(Configuration.get(setting)))

            # save to disk
            with open(conf_file, 'w', encoding='utf8') as f:
                config.write(f)

        # overwrite one var
        else:
            config.set('settings', name, str(Configuration.get(name)))

            # save to disk
            with open(conf_file, 'w', encoding='utf8') as f:
                config.write(f)
