# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\controller\NavigationController.py
from lib.controller import Controller
import lib.util.session as session
from lib.util.sciter.events import Event
import sciter, sys

class NavigationController(Controller):

    def __init__(self):
        super().__init__()

    @sciter.script
    def exit_confirm_callback(self):
        sys.exit(0)

    @sciter.script
    def on_nav_button_click(self, id, container, ctrl_key):
        if container is not None:
            self.get_views().navigation.set_current_button(id)
            self.get_views().root.show_container(container)
        else:
            if id == "nav-item-new":
                session.new_project()
                self.get_controller_manager().reset()
                self.get_view_manager().refresh()
            else:
                if id == "nav-item-open":
                    self.get_controllers().project.open()
                else:
                    if id == "nav-item-save":
                        self.get_controllers().project.save(ctrl_key)
                    else:
                        if id == "nav-item-run":
                            self.get_controllers().run.run()
                        else:
                            if id == "nav-item-exit":
                                self.get_views().dialogs.show_confirmation_dialog("Are you sure you want to exit?", (self.exit_confirm_callback), title="Exit application")

    @sciter.script
    def show_preview_container(self):
        self.get_views().root.show_preview_container()

# okay decompiling pyz_out/lib/controller/NavigationController.pyc
