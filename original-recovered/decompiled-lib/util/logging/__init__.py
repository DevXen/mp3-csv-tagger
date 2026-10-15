# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\logging\__init__.py
import logging, os, sys
import lib.util.configuration as configuration
from pathlib import Path

class StreamToLogger(object):
    __doc__ = "\n    This class is used for directing streams like stdout and stderr to a logger.\n    "

    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ""

    def write(self, buf):
        """
        Split the incoming buffer into lines and dump to the logger
        :param buf: the buffer
        :return:
        """
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        """
       Does not do much but is required as will be called and if does not exist an exception
       will occur.
       :return:
       """
        return


def initialize_logging(level=logging.DEBUG, logfile=None, capture_std=True):
    """
    Initializes logging for the application. It will setup logging to write to file
    if a log file is provided.

    :param capture_std:
    :param level: The logging level to use, e.g. logging.DEBUG, logging.WARN, logging.ERROR
    :param logfile: The log file to persist logging information
    :return: None
    """
    if logfile is not None:
        log_file_path = Path(logfile)
        if log_file_path.exists():
            os.remove(logfile)
    logging.basicConfig(filename=logfile, filemode="w", format="%(asctime)s:%(levelname)s:%(name)s:%(message)s")
    logger = logging.getLogger()
    logger.setLevel(level)
    if capture_std is True:
        stdout_logger = logging.getLogger("STDOUT")
        sl = StreamToLogger(stdout_logger, logging.INFO)
        sys.stdout = sl
        stderr_logger = logging.getLogger("STDERR")
        sl = StreamToLogger(stderr_logger, logging.ERROR)
        sys.stderr = sl
    logger = logging.getLogger("chardet.charsetprober")
    logger.setLevel(logging.ERROR)


def enable_debug_logging(logfile=None, capture_std=False):
    """
    A helper method to initialize DEBUG level logging.
    :param capture_std:
    :param logfile: The log file to write logs to
    :return: None
    """
    initialize_logging(logging.DEBUG, logfile, capture_std)


def enable_warn_logging(logfile=None, capture_std=False):
    """
    A helper method to initialize WARN level logging.
    :param capture_std:
    :param logfile: The log file to write logs to
    :return: None
    """
    initialize_logging(logging.WARNING, logfile, capture_std)


def enable_info_logging(logfile=None, capture_std=False):
    """
    A helper method to initialize INFO level logging.
    :param capture_std:
    :param logfile: The log file to write logs to
    :return:
    """
    initialize_logging(logging.INFO, logfile, capture_std)


def enable_error_logging(logfile=None, capture_std=False):
    """
    A helper method to initialize ERROR level logging.
    :param capture_std:
    :param logfile: The log file to write logs to
    :return:
    """
    initialize_logging(logging.ERROR, logfile, capture_std)


logconfig = configuration.logging()
if logconfig is not None:
    valid_levels = [
     "DEBUG", "WARNING", "INFO", "ERROR"]
    level = logconfig.level
    if level in valid_levels:
        log_file = getattr(logconfig, "file", None)
        initialize_logging(getattr(logging, level), log_file, False)

# okay decompiling pyz_out/lib/util/logging/__init__.pyc
