# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\controller\TestController.py
from lib.controller import Controller
import sciter

class TestController(Controller):

    def __init__(self):
        super().__init__()

    def on_load_data(self, frame, nm, uri):
        print("Test Controller.on_load_data: " + str(uri))

    def on_script_call(self, frame, name, args):
        print("Test Controller.Script call: " + name)
        if name == "test_call":
            return "Answer from Test Controller"

    def on_document_ready(self, frame, target):
        print("Test Controller.on_document_ready: " + str(target))

    @sciter.script
    def test(self, arg):
        return {'name_1': '"value_1"', 'name_2': 2, 'name_3': 3.5, 'arg': arg}

# okay decompiling pyz_out/lib/controller/TestController.pyc
