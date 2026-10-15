# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\sciter\events.py
import sciter

class Event:

    @staticmethod
    def dump(source, target, code, phase, reason):
        if phase == sciter.event.PHASE_MASK.SINKING:
            if code in sciter.event.BEHAVIOR_EVENTS:
                name = sciter.event.BEHAVIOR_EVENTS(code)
        if code in sciter.event.MOUSE_EVENTS:
            name = sciter.event.MOUSE_EVENTS(code)

    @staticmethod
    def is_selection_change(source, target, code, phase, reason):
        if phase == sciter.event.PHASE_MASK.SINKING:
            if code in sciter.event.BEHAVIOR_EVENTS:
                if code == sciter.event.BEHAVIOR_EVENTS.SELECT_SELECTION_CHANGED:
                    element = sciter.Element(target)
                    if element.tag == "select":
                        return True
        return False

    @staticmethod
    def is_document_complete(source, target, code, phase, reason):
        if phase == sciter.event.PHASE_MASK.SINKING:
            if code in sciter.event.BEHAVIOR_EVENTS:
                if code == sciter.event.BEHAVIOR_EVENTS.DOCUMENT_COMPLETE:
                    return True
        return False

# okay decompiling pyz_out/lib/util/sciter/events.pyc
