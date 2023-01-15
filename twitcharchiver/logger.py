# reference
#   https://stackoverflow.com/questions/7621897/python-logging-module-globally

"""
Logging class used by Twitch Archiver.
"""


import sys
import logging

class Logger:
    """
    Sets up logging for the script.
    """
    @staticmethod
    def setup_logger(level, log_file=None):
        """Sets up logging module.

        :param level: numeric log level
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
        console.setLevel(20 if not level else level)
        console.setFormatter(console_formatter)
        logger.addHandler(console)

        # if log file passed is provided, output to given file
        if log_file:
            file = logging.FileHandler(log_file)
            file.setLevel(logging.DEBUG)
            file.setFormatter(file_formatter)
            logger.addHandler(file)

        # supress other messages
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('charset_normalizer').setLevel(logging.WARNING)

        return logger
