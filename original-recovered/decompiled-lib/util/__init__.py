# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\__init__.py
import os, sys, tempfile, threading
from datetime import datetime
import traceback, logging
_local_thread_container = threading.local()

def get_temporary_file(suffix):
    return os.path.join(tempfile.gettempdir(), next(tempfile._get_candidate_names()) + suffix)


def local_thread_container():
    return _local_thread_container


def get_stack_trace():
    exc_type, exc_value, exc_tb = sys.exc_info()
    tbe = traceback.TracebackException(exc_type, exc_value, exc_tb)
    return "".join(tbe.format())


def dump_stack_trace():
    print(get_stack_trace())


log = logging.getLogger("timing")

class Timing:
    previous_time = None

    @staticmethod
    def mark(caption):
        _time = datetime.now()
        if Timing.previous_time is None:
            log.debug("({0:s}) Timing starting at: {1:s}".format(caption, _time.strftime("%H:%M:%S")))
        else:
            log.debug("({0:s}) Timing mark: {1:s}, duration from previous: {2:s}".format(caption, _time.strftime("%H:%M:%S"), str((_time - Timing.previous_time).total_seconds())))
        Timing.previous_time = _time

    @staticmethod
    def reset():
        Timing.previous_time = None

# okay decompiling pyz_out/lib/util/__init__.pyc
