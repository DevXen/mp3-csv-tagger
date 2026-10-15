# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\event\__init__.py
import enum
from lib.util.dict2obj import Dict2Obj

class CONTAINER_EVENTS(enum.IntEnum):
    Show = 1
    Hide = 2


class COLOR_KEY_EVENTS(enum.IntEnum):
    Change = 1


class ObservableEvents:
    CONTAINER_EVENTS = CONTAINER_EVENTS
    COLOR_KEY_EVENTS = COLOR_KEY_EVENTS


class Observable:

    def __init__(self):
        self.listeners = {}
        self.ObservableEvents = ObservableEvents
        return

    def listen(self, event, listener, priority=9999):
        event_listeners = self.listeners.get(event)
        if event_listeners is None:
            event_listeners = {}
            self.listeners[event] = event_listeners
        priority_listeners = event_listeners.get(priority)
        if priority_listeners is None:
            priority_listeners = []
            event_listeners[priority] = priority_listeners
        priority_listeners.append(listener)

    def notify(self, event, data=None):
        event_listeners = self.listeners.get(event)
        if event_listeners is not None:
            for priority in sorted(event_listeners.keys()):
                listeners = event_listeners[priority]
                for l in listeners:
                    if isinstance(data, dict):
                        l(Dict2Obj(data))
                    else:
                        l(data)


class GlobalEvents:
    instance = None

    @staticmethod
    def notify(event, data=None):
        if GlobalEvents.instance is None:
            GlobalEvents.instance = Observable()
        GlobalEvents.instance.notify(event, data)

    @staticmethod
    def listen(event, listener, priority=9999):
        if GlobalEvents.instance is None:
            GlobalEvents.instance = Observable()
        GlobalEvents.instance.listen(event, listener, priority)

# okay decompiling pyz_out/lib/util/event/__init__.pyc
