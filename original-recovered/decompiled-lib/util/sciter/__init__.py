# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\sciter\__init__.py
import ctypes, sciter.dom, sciter.error, sciter.capi.scdef
import sciter.capi.sctypes as sctypes
import ctypes
from sciter.capi.scdom import *
from sciter.capi.screquest import SciterResourceType
from sciter.capi.scbehavior import BEHAVIOR_EVENTS, CLICK_REASON
_api = sciter.dom._api

class SciterUtil:

    @staticmethod
    def create_node(text, kind=NODE_TYPE.NT_TEXT):
        """
        This is taken from the create class method defined in sciter.dom which seems to
        have a bug in it (referring to self when it doesn't exist). This is basically a copy
        of the method but without references to self.

        :param text:
        :return:
        """
        if text is None:
            text = ""
        else:
            rv = HNODE()
            if kind == NODE_TYPE.NT_TEXT:
                ok = _api.SciterCreateTextNode(text, len(text), ctypes.byref(rv))
            else:
                if kind == NODE_TYPE.NT_COMMENT:
                    ok = _api.SciterCreateCommentNode(text, len(text), ctypes.byref(rv))
        return sciter.dom.Node(rv)

    @staticmethod
    def _set_element_html(element, html, where=SET_ELEMENT_HTML.SIH_REPLACE_CONTENT):
        """
        This is a replacement for the set_html method on sciter's Element class which insists on the
        HTML being bytes but the external function requires a LP_c_byte type which bytes is not.

        Wasted a lot of time trying to figure out how to convert given html as a string into a type
        acceptable by the external function.

        Thanks to:
        https://stackoverflow.com/questions/1413851/expected-lp-c-double-instance-instead-of-c-double-array-python-ctypes-error

        :param element:
        :param html:
        :return:
        """
        if not isinstance(element, sciter.Element):
            raise ValueError("Given element must be an instance of sciter.Element")
        node = SciterUtil.create_node(html)
        bhtml = bytes(html, encoding="utf-8")
        try:
            buffer = ctypes.c_buffer(bhtml, len(bhtml))
            buffer_pointer = ctypes.POINTER(ctypes.c_byte)(buffer)
            ok = _api.SciterSetElementHtml(element, buffer_pointer, len(bhtml), where)
        except Exception as e:
            try:
                print(e)
            finally:
                e = None
                del e

    @staticmethod
    def set_element_html(element, html):
        SciterUtil._set_element_html(element, html, SET_ELEMENT_HTML.SIH_REPLACE_CONTENT)

    @staticmethod
    def append_element_html(element, html):
        SciterUtil._set_element_html(element, html, SET_ELEMENT_HTML.SIH_APPEND_AFTER_LAST)

    @staticmethod
    def toggleClass(element, class_name):
        classes = element.attribute("class")
        if classes is None:
            classes = ""
        parts = classes.split(" ")
        existing = -1
        index = 0
        for part_class_name in parts:
            if part_class_name == class_name:
                existing = index
            index += 1

        if existing > -1:
            new_classes = ""
            index = 0
            for part_class_name in parts:
                if index != existing:
                    if index > 0:
                        new_classes += " "
                    new_classes += part_class_name
                index += 1

        else:
            new_classes = classes + " " + class_name
        element.set_attribute("class", new_classes)

# okay decompiling pyz_out/lib/util/sciter/__init__.pyc
