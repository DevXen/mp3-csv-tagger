# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\gui.py
from lib.gui.baseframe import Frame
import lib.gui.view.baseview as baseview
from lib.controller import ControllerManager
import lib.controller.TestController as TestController
import lib.controller.PreviewController as PreviewController
import lib.controller.CSVController as CSVController
import lib.controller.RunController as RunController
import lib.controller.ProjectController as ProjectController
import lib.controller.NavigationController as NavigationController
import lib.controller.FilesController as FilesController
import lib.controller.ConfigurationController as ConfigurationController
import lib.controller.ApplyController as ApplyController

class MP3AppFrame(Frame):

    def __init__(self):
        super().__init__(debug=True)
        self.set_view(baseview.get_view("root", "root", self))
        ControllerManager.get().add("preview", PreviewController())
        ControllerManager.get().add("csv", CSVController())
        ControllerManager.get().add("run", RunController())
        ControllerManager.get().add("project", ProjectController())
        ControllerManager.get().add("navigation", NavigationController())
        ControllerManager.get().add("files", FilesController())
        ControllerManager.get().add("configuration", ConfigurationController())
        ControllerManager.get().add("apply", ApplyController())


def start():
    frame = MP3AppFrame()
    frame.run_app()


if __name__ == "__main__":
    start()

# okay decompiling pyz_out/lib/gui/gui.pyc
