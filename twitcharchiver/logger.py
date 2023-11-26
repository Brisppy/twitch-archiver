# reference
#   https://stackoverflow.com/questions/7621897/python-logging-module-globally

"""
Logging class used by Twitch Archiver.
"""
import multiprocessing
import sys
import logging
import logging.handlers
import traceback

from pathlib import Path

CONSOLE_FORMATTER = logging.Formatter('%(asctime)s [%(levelname)8s] %(message)s', '%Y-%m-%d %H:%M:%S')
FILE_FORMATTER = logging.Formatter(
    '%(asctime)s [%(filename)s:%(lineno)s - %(funcName)s()] %(message)s', '%Y-%m-%d %H:%M:%S')


class Logger:
    """
    Sets up logging for the script.
    """
    @staticmethod
    def setup_logger(quiet: bool = False, debug: bool = False, logging_dir: str = ""):
        """Sets up logging module.

        :return: python logging object
        """
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        # setup console logging
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(CONSOLE_FORMATTER)

        # check if stream handler already created - necessary as Windows doesn't properly share the global logger.
        if len(logger.handlers) < 1:
            logger.addHandler(console)

        # setup debugging / quiet / file logging
        if quiet:
            logger = Logger.setup_quiet(logger)
        elif debug:
            logger = Logger.setup_debugging(logger)

        if logging_dir:
            logger = Logger.setup_file(logger, logging_dir)

        Logger.suppress_unnecessary()

        return logger

    @staticmethod
    def setup_file(logger, logging_dir: str):
        """
        Sets up file logging with given logger and filepath.

        :param logger: logging object to enable file output on
        :param logging_dir: directory to store log file(s)
        :return: logging object
        """
        if Path(logging_dir).is_file():
            raise FileExistsError('Error configuring logging, file exists in place of log directory.')

        Path(logging_dir).mkdir(parents=True, exist_ok=True)

        # use rotating file handler with max size of 100MB * 5
        file = logging.handlers.RotatingFileHandler(
            Path(logging_dir, 'debug.log'), maxBytes=100000000, backupCount=5, encoding='utf8')
        file.setLevel(logging.DEBUG)
        file.setFormatter(FILE_FORMATTER)
        logger.addHandler(file)

        return logger

    @staticmethod
    def setup_debugging(logger):
        logger.setLevel(logging.DEBUG)

        return logger

    @staticmethod
    def setup_quiet(logger):
        logger.setLevel(50)

        return logger

    @staticmethod
    def suppress_unnecessary():
        # supress other messages
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('charset_normalizer').setLevel(logging.WARNING)


# logging handler used with realtime archiver
# reference:
#   https://stackoverflow.com/a/60831737
class ProcessLogger(multiprocessing.Process):
    _global_process_logger = None

    def __init__(self):
        super().__init__()
        self.queue = multiprocessing.Queue(-1)

    @classmethod
    def get_global_logger(cls):
        if cls._global_process_logger is not None:
            return cls._global_process_logger
        raise Exception("No global process logger exists.")

    @classmethod
    def create_global_logger(cls):
        cls._global_process_logger = ProcessLogger()
        return cls._global_process_logger

    @staticmethod
    def configure():
        root = Logger.setup_logger()
        # Windows doesn't properly share the global logging instance and so it has to be re-added when we setup
        # multiprocess logging. Linux doesn't have this problem and so the logger configured during `__init__` is all
        # that's needed.
        if not root.handlers:
            # limit to 5x 100MB log files
            h = logging.handlers.RotatingFileHandler('debug.log', 'a', 100*1024**2, 5, encoding='utf8')
            h.setFormatter(FILE_FORMATTER)
            root.addHandler(h)

    def stop(self):
        self.queue.put_nowait(None)

    def run(self):
        self.configure()
        while True:
            try:
                record = self.queue.get()
                if record is None:
                    break
                logger = logging.getLogger(record.name)
                logger.handle(record)
            except Exception:
                print('Multiprocess logger error:', file=sys.stderr)
                traceback.print_exc(file=sys.stderr)


def configure_new_process(log_process_queue):
    h = logging.handlers.QueueHandler(log_process_queue)
    root = logging.getLogger()
    root.addHandler(h)
    # grab level from main logger
    root.setLevel(root.handlers[0].level)
    Logger.suppress_unnecessary()


class ProcessWithLogging(multiprocessing.Process):
    def __init__(self, target, args=None, kwargs=None, log_process=None):
        super().__init__()
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        self.target = target
        self.args = args
        self.kwargs = kwargs
        if log_process is None:
            log_process = ProcessLogger.get_global_logger()
        self.log_process_queue = log_process.queue

    def run(self):
        configure_new_process(self.log_process_queue)
        self.target(*self.args, **self.kwargs)
