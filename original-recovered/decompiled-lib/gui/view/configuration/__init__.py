# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\configuration\__init__.py
from lib.gui.view.baseview import BaseView
from lib.util.sciter import SciterUtil
import lib.util.session as session
import sciter

class View(BaseView):

    def __init__(self, id, frame):
        super().__init__(id, frame)

    def on_document_ready(self, source, target):
        self.call_function("configurationHandler.initialize()")

    def refresh_color_key(self, name, color, refresh_color_key_input=True):
        element = self.find_element_by_id("color-" + name)
        if element is not None:
            element.set_attribute("color", color)
            element.set_attribute("style", "background-color: " + color)
        if refresh_color_key_input is True:
            element = self.find_element_by_id("color-" + name + "-input")
            if element is not None:
                element.value = color
        self.refresh()

    def refresh_color_keys(self):
        color_keys = self.find_elements(".color-key")
        for color_key in color_keys:
            name = color_key.attribute("name")
            color = session.get_project().get_tag_color(name)
            color_key.set_attribute("color", color.background)
            color_key.set_attribute("style", "background-color:" + color.background + ";")

    def refresh_tag_names(self):
        self.call_function("refresh_tag_names()")

    def refresh(self):
        self.refresh_color_keys()
        self.refresh_tag_names()

# okay decompiling pyz_out/lib/gui/view/configuration/__init__.pyc
