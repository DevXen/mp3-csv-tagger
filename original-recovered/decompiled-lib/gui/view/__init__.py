# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\__init__.py
import sciter, lib.gui.view.baseview
from lib.util.dict2obj import Dict2Obj

class ViewManager:
    instance = None

    def __init__(self):
        self.views = {}

    def add(self, view):
        self.views[view.id] = view

    def new(self, view_path, id, frame):
        view = baseview.get_view(view_path, id, frame)
        self.add(view)
        return view

    def get_views(self):
        """
        This can by used by other python modules to access views

        Returns the views dict as an object
        :return:
        """
        return Dict2Obj(self.views)

    def get_callables(self):
        """
        This allows TIScripts to call view methods, e.g.:

        view.view().<view id>.<method>(....)

        :return:
        """
        all_view_callables = {}
        for vi in self.views:
            view = self.views[vi]
            view_callables = view.get_callables()
            all_view_callables[view.id] = sciter.Value(view_callables)

        return sciter.Value(all_view_callables)

    def on_event_handler(self, source, target, code, phase, reason):
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
        for vi in self.views:
            view = self.views[vi]
            view_response = view.on_event(source, source_element, target, code, phase, reason)
            if view_response is not None and response is None:
                response = view_response

        return response

    def refresh(self):
        """
        Ask each view to refresh
        :return:
        """
        for vi in self.views:
            view = self.views[vi]
            view.refresh()

    @staticmethod
    def get():
        if ViewManager.instance is None:
            ViewManager.instance = ViewManager()
        return ViewManager.instance

# okay decompiling pyz_out/lib/gui/view/__init__.pyc
