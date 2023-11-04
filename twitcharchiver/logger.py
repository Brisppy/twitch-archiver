# reference
#   https://stackoverflow.com/questions/7621897/python-logging-module-globally

"""
Logging class used by Twitch Archiver.
"""

import sys
import logging
import logging.handlers

class Logger:
    """
    Sets up logging for the script.
    """
    @staticmethod
    def setup_logger(log_file=None):
        """Sets up logging module.

        :param log_file: location of log file if provided
        :return: python logging object
        """
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        # set up time, date, log format
        console_formatter = logging.Formatter('%(asctime)s [%(levelname)8s] %(message)s', '%Y-%m-%d %H:%M:%S')
        file_formatter = logging.Formatter('%(asctime)s [%(filename)s:%(lineno)s - %(funcName)s()] %(message)s',
                                           '%Y-%m-%d %H:%M:%S')

        # setup console logging
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(console_formatter)
        if not len(logger.handlers):
            logger.addHandler(console)

        # if log file passed is provided, output to given file
        if log_file:
            # use rotating file handler with max size of 100MB * 5
            file = logging.handlers.RotatingFileHandler(log_file, maxBytes=100000000, backupCount=5)
            file.setLevel(logging.DEBUG)
            file.setFormatter(file_formatter)
            logger.addHandler(file)

        # supress other messages
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('charset_normalizer').setLevel(logging.WARNING)

        return logger
