# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\controller\ProjectController.py
from lib.controller import Controller
import lib.util.session as session
import sciter

class ProjectController(Controller):

    def __init__(self):
        super().__init__()

    def open(self):
        project = session.get_project()
        load_path = self.get_views().project.load_project_from()
        if load_path is not None:
            session.open_project(load_path)
            self.get_view_manager().refresh()

    def save(self, save_as=False):
        project = session.get_project()
        if project.is_new is True or save_as is True:
            save_path = self.get_views().project.save_project_as()
            if save_path is not None:
                session.get_project().save(save_path)
                self.get_views().project.refresh()
        else:
            session.get_project().save()
            self.get_views().project.refresh()

    def reset(self):
        return

# okay decompiling pyz_out/lib/controller/ProjectController.pyc
