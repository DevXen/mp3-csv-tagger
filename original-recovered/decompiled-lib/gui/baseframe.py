# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\baseframe.py
import inspect, json, os, sciter
from sciter.capi.scbehavior import *
import ctypes
import lib.util.resource as resource
from lib.gui.view import ViewManager
from lib.controller import ControllerManager
import lib.util.configuration as configuration
from urllib.parse import urlparse
from sciter.capi.scdef import SCRIPT_RUNTIME_FEATURES, SCITER_RT_OPTIONS

class Frame(sciter.Window):

    def __init__(self, debug=False, size=()):
        self.view_manager = ViewManager.get()
        self.controller_manager = ControllerManager.get()
        self.view = None
        self.root_element = None
        options = SCRIPT_RUNTIME_FEATURES.ALLOW_SYSINFO
        if debug:
            options = options | SCRIPT_RUNTIME_FEATURES.ALLOW_SOCKET_IO
        sciter.set_option(SCITER_RT_OPTIONS.SCITER_SET_SCRIPT_RUNTIME_FEATURES, options)
        super().__init__(ismain=True, uni_theme=True, debug=debug, pos=(5, 5), size=(920,
                                                                                     600))
        self.callingPath = os.path.split(inspect.stack(1)[1].filename)[0]
        return

    @sciter.script
    def get_configuration_value(self, path, default=None):
        return configuration.get(path, default)

    @sciter.script
    def controllers(self):
        """
        This allows TIScripts to call controller methods annotated with @sciter.script, e.g.:

        view.controllers().<controller id>.<method>(....)

        :return:
        """
        return self.controller_manager.get_callables()

    @sciter.script
    def views(self):
        """
        This allows TIScripts to call view methods annotated with @sciter.script, e.g.:

        view.view().<view id>.<method>(....)

        :return:
        """
        return self.view_manager.get_callables()

    @sciter.script
    def log(self, msg):
        print(msg)

    def set_view(self, view):
        self.view = view
        self.view_manager.add(view)

    def run_app(self, show=True):
        self.view.load_content()
        super().run_app(show)

    def _document_ready(self, target):
        super()._document_ready(target)
        self.root_element = sciter.Element(target)
        ControllerManager.get().on_document_ready(self, sciter.Element(target))

    def on_subscription(self, groups):
        return EVENT_GROUPS.HANDLE_ALL

    def _element_proc(self, tag, he, evt, params):
        """
        This is EXPERIMENTAL, following sciter code to try capture mouse, key events etc. in Python
        :param tag:
        :param he:
        :param evt:
        :param params:
        :return:
        """
        if evt == EVENT_GROUPS.HANDLE_MOUSE:
            p = ctypes.cast(params, ctypes.POINTER(MOUSE_PARAMS))
            m = p.contents
            code = m.cmd & 4095
        return super()._element_proc(tag, he, evt, params)

    def on_event(self, source, target, code, phase, reason):
        self.controller_manager.on_event_handler(self, source, target, code, phase, reason)
        self.view_manager.on_event_handler(source, target, code, phase, reason)

    def on_script_call(self, name, args):
        response = ControllerManager.get().on_script_call(self, name, args)
        if response is not None:
            return response
        return self.dispatch(name, args)

    def on_load_data(self, nm):
        """"
        nm.dataType=
        1: Image
        2: CSS Stylesheet
        3: Cursor
        4: Script
        5: Raw data of unknown type
        6: HTML

        nm.uri = path (including file:/// etc.)

        nm.outData = content to be returned.
        nm.outDataSize = size of content being returned.

        """
        uri = urlparse(nm.uri)
        response = ControllerManager.get().on_load_data(self, nm, uri)
        if response is True:
            return
        elif uri.scheme == "sciter":
            super().on_load_data(nm)
        else:
            if uri.scheme == "file":
                filepath = uri.netloc + uri.path
                content = resource.load(filepath)
                nm.outData = content.content
                nm.outDataSize = content.size
            else:
                if uri.scheme == "view":
                    view_path = uri.netloc
                    id = uri.path
                    if id is not None:
                        id = id[1[:None]]
                    view = self.view_manager.new(view_path, id, self)
                    content = view.get_content()
                    nm.outData = content
                    nm.outDataSize = len(content)
        return

    def on_data_loaded(self, nm):
        ControllerManager.get().on_data_loaded(self, nm, nm.uri)
        return

    def find_element_by_id(self, id):
        return self.root.find_first("#" + id)

# okay decompiling pyz_out/lib/gui/baseframe.pyc
