# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\navigation\__init__.py
from lib.gui.view.baseview import BaseView
from lib.util.sciter import SciterUtil
from lib.util.event import *
import lib.util.session as session
import sciter

class View(BaseView):

    def __init__(self, id, frame):
        super().__init__(id, frame)
        self.selected_button = None

    def on_document_ready(self, source, target):
        self.selected_button = self.find_element(".navigation-bar-item-selected")
        self.call_function("initialize_navigation()")
        self.get_views().root.listen(self.ObservableEvents.CONTAINER_EVENTS.Show, self.on_container_show)

    def on_container_show(self, container):
        buttons = self.find_elements("navigation-bar-button")
        for button in buttons:
            container_id = button.attribute("container", default=None)
            if container_id is not None and container_id == container.id:
                button_id = button.attribute("id", default=None)
                if button_id is not None:
                    self.set_current_button(button_id)

    def unselect_current_button(self):
        if self.selected_button is not None:
            SciterUtil.toggleClass(self.selected_button, "navigation-bar-item-selected")
            self.selected_button = None

    def set_current_button(self, id):
        button = self.find_element_by_id(id)
        if button is not None:
            self.unselect_current_button()
            self.selected_button = button
            SciterUtil.toggleClass(button, "navigation-bar-item-selected")

# okay decompiling pyz_out/lib/gui/view/navigation/__init__.pyc
