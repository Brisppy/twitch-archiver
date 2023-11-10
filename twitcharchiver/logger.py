# reference
#   https://stackoverflow.com/questions/7621897/python-logging-module-globally

"""
Logging class used by Twitch Archiver.
"""

import sys
import logging
import logging.handlers
from pathlib import Path


class Logger:
    """
    Sets up logging for the script.
    """
    @staticmethod
    def setup_logger(quiet: bool = False, debug: bool = False, log_filepath: str = ""):
        """Sets up logging module.

        :return: python logging object
        """
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        # setup console logging
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(console_formatter)
        if not len(logger.handlers):
            logger.addHandler(console)

        # setup debugging / quiet / file logging
        if quiet:
            logger = Logger._setup_quiet(logger)
        elif debug:
            logger = Logger._setup_debugging(logger)

        if log_filepath:
            logger = Logger._setup_file(logger, log_filepath)

        # supress other messages
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('charset_normalizer').setLevel(logging.WARNING)

        return logger

    @staticmethod
    def _setup_file(logger, log_filepath: str):
        """
        Sets up file logging with given logger and filepath.

        :param logger: logging object to enable file output on
        :param log_filepath: path to desired log file
        :return: logging object
        """
        Path(log_filepath).parent.mkdir(parents=True, exist_ok=True)

        # use rotating file handler with max size of 100MB * 5
        file = logging.handlers.RotatingFileHandler(Path(log_filepath), maxBytes=100000000, backupCount=5, encoding='utf8')
        file.setLevel(logging.DEBUG)
        file.setFormatter(file_formatter)
        logger.addHandler(file)

        return logger

    @staticmethod
    def _setup_debugging(logger):
        logger.setLevel(logging.DEBUG)
        logger.handlers[0].setFormatter(file_formatter)

        return logger

    @staticmethod
    def _setup_quiet(logger):
        logger.setLevel(50)

        return logger

console_formatter = logging.Formatter('%(asctime)s [%(levelname)8s] %(message)s', '%Y-%m-%d %H:%M:%S')
file_formatter = logging.Formatter('%(asctime)s [%(filename)s:%(lineno)s - %(funcName)s()] %(message)s','%Y-%m-%d %H:%M:%S')
