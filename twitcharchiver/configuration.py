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
    # reference:
    #   https://stackoverflow.com/questions/6198372/most-pythonic-way-to-provide-global-configuration-variables-in-config-py/
    __conf = {
        'pushbullet_key': '',
    }

    _log = logging.getLogger()

    def generate_config(self, args):
        """
        Generates the required configuration from provided arguments, overwriting loaded settings.

        :param args: dict of arguments to generate config from
        :type args: dict
        """
        self._log.debug('Generating config from provided arguments.')

        # overwrite configuration with passed args (if set) as they have precedence
        for argument in args:
            # don't copy value if it is empty and config value set
            if args.get(argument) == '' and self.get(argument):
                continue

            self.set(argument, args.get(argument))

    def load_config(self, conf_file):
        """
        Loads the settings stored in the configuration ini file.

        :param conf_file: path to configuration file
        """
        # create conf file if it doesn't exist
        if not os.path.isfile(conf_file):
            self._log.debug('Config file not found - creating one now.')
            self.create_config_file(conf_file)

        self._log.debug('Loading config from file.')

        config = configparser.ConfigParser()
        config.read(conf_file)

        # load individual settings from file
        for setting in config['settings']:
            self.set(setting, config['settings'][setting])

    def create_config_file(self, conf_file):
        """
        Creates a configuration file for the storing of settings.\n

        :param conf_file: path to configuration file
        """
        self._log.debug('Creating directories for configuration file.')
        os.makedirs(conf_file.parent, exist_ok=True)

        config = configparser.ConfigParser()
        config.add_section('settings')
        self._log.debug('Current config: %s', self.get())

        for setting in self.__conf:
            config.set('settings', setting, self.get(setting))

        self._log.debug('Writing config to %s', conf_file)

        with open(conf_file, 'w', encoding='utf8') as _f:
            config.write(_f)

    @classmethod
    def set(cls, name, value):
        """
        Set a specified attribute.

        :param name:  name of attribute to change
        :param value: value to set attribute to
        """
        cls.__conf[name] = value

    @classmethod
    def get(cls, name=None):
        """
        Retrieve a specified attribute.

        :param name: name of attribute to retrieve value of - 'None' returns all attributes
        :return: requested value(s), None if value cannot be found
        """
        if name is None:
            return cls.__conf

        if name not in cls.__conf:
            return None

        return cls.__conf[name]

    @classmethod
    def import_conf(cls, conf_dict: dict):
        """
        Imports config keys and values from a provided dict.

        :param conf_dict: dictionary of values to import
        :type conf_dict: dict
        """
        cls.__conf = conf_dict

    @classmethod
    def get_sanitized(cls, name=None):
        """
        Retrieves a specified attribute, sanitizing secrets.

        :param name: name of attribute to retrieve value of - 'None' returns all attributes
        :return: requested value(s)
        """
        configuration = cls.__conf.copy()
        for key in ['pushbullet_key']:
            if configuration[key]:
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
        self._log.debug('Saving config variable(s) to ini file.')

        # import saved config
        config = configparser.ConfigParser()
        config.read(conf_file)

        # overwrite all vars
        if name is None:
            # overwrite with running config
            for setting in Configuration.get():
                config.set('settings', setting, str(Configuration.get(setting)))

            # save to disk
            with open(conf_file, 'w', encoding='utf8') as _f:
                config.write(_f)

        # overwrite one var
        else:
            config.set('settings', name, str(Configuration.get(name)))

            # save to disk
            with open(conf_file, 'w', encoding='utf8') as _f:
                config.write(_f)
