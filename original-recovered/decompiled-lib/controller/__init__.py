# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\controller\__init__.py
import sciter
from lib.util.sciter.events import Event
from lib.gui.view import ViewManager
from lib.util.dict2obj import Dict2Obj
from lib.util.event import Observable

class Controller(Observable):

    def __init__(self):
        super().__init__()

    def reset(self):
        """
        Do nothing by default, extendinded classes can implement their own.

        This is similar to the View's reset() method which can be called to ask the controller
        to "reset" / "refresh" after e.g. starting a new project, loading another project etc.

        ControllerManager.refresh() in turn calls refresh() on each controller.

        :return:
        """
        return

    def get_view_manager(self):
        return ViewManager.get()

    def get_controller_manager(self):
        return ControllerManager.get()

    def get_views(self):
        return ViewManager.get().get_views()

    def get_controllers(self):
        return ControllerManager.get().get_controllers()

    def on_event(self, frame, source, source_element, target, code, phase, reason):
        return

    def on_load_data(self, frame, nm, uri):
        return

    def on_data_loaded(self, frame, nm, uri):
        return

    def on_script_call(self, frame, name, args):
        return

    def on_document_ready(self, frame, target):
        return

    def get_callables(self):
        """
        Scan myself for methods decorated with @sciter.script. Methods decorated like this
        will have a _from_sciter or _sciter_cfg attribute/property, that is what we're checking for.

        :return:
        """
        result = {}
        for method_name in dir(self):
            method = getattr(self, method_name)
            try:
                if method._from_sciter is not None:
                    result[method_name] = method
            except AttributeError:
                pass

        return result


class ControllerManager:
    instance = None

    def __init__(self):
        self.controllers = {}
        return

    def add(self, id, controller):
        if isinstance(controller, Controller):
            self.controllers[id] = controller

    def get_callables(self):
        """
        This allows TIScripts to call controller methods decorated with @sciter.script, e.g.:

        view.controllers().<controller id>.<method>(....)

        :return:
        """
        all_callables = {}
        for id in self.controllers:
            controller = self.controllers[id]
            callables = controller.get_callables()
            all_callables[id] = sciter.Value(callables)

        return sciter.Value(all_callables)

    def get_controllers(self):
        return Dict2Obj(self.controllers)

    def on_event_handler(self, frame, source, target, code, phase, reason):
        """
        This is not called automatically, it is called by the base frame class' onevent method
        :param source:
        :param target:
        :param code:
        :param phase:
        :param reason:
        :return:
        """
        source_element = sciter.Element(source)
        response = None
        for vi in self.controllers:
            controller = self.controllers[vi]
            controller_response = controller.on_event(frame, source, source_element, target, code, phase, reason)
            if controller_response is not None and response is None:
                response = controller_response

        return response

    def on_load_data(self, frame, nm, uri):
        """
        This is called by the base frame to let controllers handle loading sciter content / data.

        Controllers should populate nm.outData ( bytes / bytesarray(?) ) and nm.outDataSize and then
        return True if handled. REMEMBER: Be very careful with trying to get the length
        of a byte array to set nm.outDataSize, len(bytes) doesn't work with binary bytes/bytearrays such as images.

        :param nm:
        :param uri:
        :return:
        """
        for vi in self.controllers:
            controller = self.controllers[vi]
            if controller.on_load_data(frame, nm, uri) is True:
                return True

        return False

    def on_data_loaded(self, frame, nm, uri):
        """
        This is called by the base frame to let controllers handle loading sciter content / data.

        This will be called once data has been loaded for the uri, this will be after on_load_data.

        Nothing to return here.
        """
        for vi in self.controllers:
            controller = self.controllers[vi]
            controller.on_data_loaded(frame, nm, uri)

    def on_script_call(self, frame, name, args):
        """
        This is called by the base frame to let controllers handle script execution requests from sciter.

        If a controller handles the request, it should return a response for the caller that is not None
        so that the base frame will not handle the call itself
        """
        for vi in self.controllers:
            controller = self.controllers[vi]
            response = controller.on_script_call(frame, name, args)
            if response is not None:
                return response

        return

    def on_document_ready(self, frame, target):
        """
        This is called by the base frame to let controllers handle the document ready event.

        This returns nothing.

        :param target:
        :return:
        """
        for vi in self.controllers:
            controller = self.controllers[vi]
            controller.on_document_ready(frame, target)

    def reset(self):
        """
        Similar to the ViewManager's refresh() method, it can be called to ask all controllers to
        "reset" / "refresh" after e.g. starting a new project, loading another project etc.
        :return:
        """
        for vi in self.controllers:
            controller = self.controllers[vi]
            controller.reset()

    @staticmethod
    def get():
        if ControllerManager.instance is None:
            ControllerManager.instance = ControllerManager()
        return ControllerManager.instance

# okay decompiling pyz_out/lib/controller/__init__.pyc
