# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\baseview.py
import importlib, sciter
from lib.util.template import Template, TIScriptTemplate
from lib.util.sciter.events import Event
from lib.util.event import Observable

class BaseView(Observable):

    def __init__(self, id, frame):
        super().__init__()
        self.id = id
        self.frame = frame
        self.resource_relative_path = self.__module__[self.__module__.find("view.")[:None]]
        self.resource_relative_path = self.resource_relative_path.replace(".", "/")
        self.template = Template(self, file=(self.resource_relative_path + "/view.html"))
        self.template.add_template("view_script", TIScriptTemplate(self, file=(self.resource_relative_path + "/view.tis")))
        self.template.set("view_id", id)

    def call_function(self, name: str, *args):
        return (self.frame.call_function)(name, *args)

    def get_controllers(self):
        from lib.controller import ControllerManager
        return ControllerManager.get().get_controllers()

    def get_views(self):
        from lib.gui.view import ViewManager
        return ViewManager.get().get_views()

    @sciter.script
    def get_relative_resource_path(self, resource):
        return self.resource_relative_path + "/" + resource

    def load_content(self):
        self.frame.load_html(bytes((self.template.generate()), encoding="utf-8"))

    def get_content(self):
        return bytes((self.template.generate()), encoding="utf-8")

    def on_document_ready(self, source, target):
        return

    def on_event(self, source, source_element, target, code, phase, reason):
        if Event.is_document_complete(source, target, code, phase, reason):
            telement = sciter.Element(target)
            selement = sciter.Element(source)
            self.on_document_ready(source, target)

    def get_callables(self):
        result = {}
        for method_name in dir(self):
            method = getattr(self, method_name)
            try:
                if method._from_sciter is not None:
                    result[method_name] = method
            except AttributeError:
                pass

        return result

    def find_element(self, selector):
        return self.frame.root.find_first(selector)

    def find_elements(self, selector):
        return self.frame.root.find_all(selector)

    def find_element_by_id(self, id):
        return self.frame.find_element_by_id(id)

    def get_view_element(self):
        return self.find_element_by_id(self.id)

    def get_template(self, file=None, content=None):
        template = Template(self, file, content)
        return template

    def refresh(self):
        return


def get_view(view_class_path, id, frame=None):
    ViewClass = getattr(importlib.import_module("lib.gui.view." + view_class_path), "View")
    return ViewClass(id, frame)

# okay decompiling pyz_out/lib/gui/view/baseview.pyc
