# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\root\__init__.py
from lib.gui.view.baseview import BaseView
from lib.util.sciter import SciterUtil
import sciter

class View(BaseView):

    def __init__(self, id, frame):
        super().__init__(id, frame)
        self.current_container = None

    def on_document_ready(self, source, target):
        self.current_container = self.find_element(".current-container")

    def hide_current_container(self):
        if self.current_container is not None:
            SciterUtil.toggleClass(self.current_container, "current-container")
            self.notify(self.ObservableEvents.CONTAINER_EVENTS.Hide, {'id':(self.current_container.attribute)("id"),  'container':self.current_container})

    def show_files_container(self):
        return

    def show_container(self, container_id):
        self.hide_current_container()
        container = self.find_element_by_id(container_id)
        if container is not None:
            self.current_container = container
            SciterUtil.toggleClass(self.current_container, "current-container")
            self.notify(self.ObservableEvents.CONTAINER_EVENTS.Show, {'id':container_id,  'element':container})

    def show_preview_container(self):
        self.show_container("preview-container")

# okay decompiling pyz_out/lib/gui/view/root/__init__.pyc
