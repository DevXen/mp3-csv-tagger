# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\project\__init__.py
from lib.gui.view.baseview import BaseView
import lib.util.configuration as configuration
import lib.util.session as session
import sciter

class View(BaseView):

    def __init__(self, id, frame):
        super().__init__(id, frame)

    def set_application_title(self):
        title = configuration.get("application/title", "MP3")
        project = session.get_project()
        if project.is_new is True:
            title += " - New"
        else:
            title += " - " + project.loaded_from_file_path
        self.frame.set_title(title)

    def save_project_as(self):
        result = self.call_function("save_project_as")
        if result is None:
            return
        return result.get_value()

    def load_project_from(self):
        result = self.call_function("load_project_from")
        if result is None:
            return
        return result.get_value()

    def on_document_ready(self, source, target):
        self.set_application_title()

    def refresh(self):
        self.set_application_title()

# okay decompiling pyz_out/lib/gui/view/project/__init__.pyc
