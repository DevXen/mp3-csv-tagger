# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\dialogs\__init__.py
from lib.gui.view.baseview import BaseView
import sciter

class View(BaseView):

    def __init__(self, id, frame):
        super().__init__(id, frame)

    def on_document_ready(self, source, target):
        return

    def refresh(self):
        return

    @sciter.script
    def show_info_dialog(self, content, title='Information'):
        self.call_function("show_info_dialog", content, title)

    @sciter.script
    def show_confirmation_dialog(self, content, yes_callback, title='Confirm'):
        self.call_function("show_confirm_dialog", content, title, yes_callback)

# okay decompiling pyz_out/lib/gui/view/dialogs/__init__.pyc
