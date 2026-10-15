# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\apply\__init__.py
from lib.gui.view.baseview import BaseView

class View(BaseView):

    def __init__(self, id, frame):
        super().__init__(id, frame)

    def on_document_ready(self, source, target):
        self.call_function("initialize_apply()")

    def update(self, msg):
        self.call_function("apply_update", msg)

    def clear_updates(self):
        self.call_function("clear_updates()")

    def refresh_apply_logback_folder(self):
        self.call_function("refresh_apply_logback_folder")

    def refresh(self):
        self.refresh_apply_logback_folder()

# okay decompiling pyz_out/lib/gui/view/apply/__init__.pyc
