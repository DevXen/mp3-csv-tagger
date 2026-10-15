# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\progress-dialog\__init__.py
from lib.gui.view.baseview import BaseView
from lib.util.sciter import SciterUtil
import time, sciter
from memory_profiler import profile

class View(BaseView):

    def __init__(self, id, frame):
        super().__init__(id, frame)
        self.queue = None

    def initialize(self):
        return

    def show(self, dialog_ready_callback, dialog_message_callback):
        self.call_function("show_progress_dialog", dialog_ready_callback, dialog_message_callback)

    def close_dialog(self):
        self.call_function("close_progress_dialog")

    def update_status(self, status):
        self.call_function("update_progress_status", status)

    def update_status_error(self, error):
        self.call_function("update_progress_error", error)

# okay decompiling pyz_out/lib/gui/view/progress-dialog/__init__.pyc
