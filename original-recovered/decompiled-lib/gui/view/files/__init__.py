# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\files\__init__.py
from lib.gui.view.baseview import BaseView
from lib.util.sciter import SciterUtil
import lib.util.session as session
import sciter

class View(BaseView):

    def __init__(self, id, frame):
        super().__init__(id, frame)

    def on_document_ready(self, source, target):
        self.call_function("initialize_files()")

    def refresh_files(self):
        self.call_function("refresh_files")

    def refresh(self):
        self.call_function("refresh_files")

# okay decompiling pyz_out/lib/gui/view/files/__init__.pyc
