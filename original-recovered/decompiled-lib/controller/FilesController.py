# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\controller\FilesController.py
from lib.controller import Controller
import lib.util.session as session
from lib.util.sciter.events import Event
import sciter

class FilesController(Controller):

    def __init__(self):
        super().__init__()

    @sciter.script
    def add_file(self, paths):
        for path in paths:
            session.get_project().add_mp3_path(path)

        self.get_views().files.refresh_files()

    @sciter.script
    def add_folder(self, path):
        session.get_project().add_mp3_path(path)
        self.get_views().files.refresh_files()

    @sciter.script
    def get_mp3_paths(self):
        return session.get_project().get_mp3_paths()

    @sciter.script
    def delete_path(self, path):
        session.get_project().delete_mp3_path(path)
        self.get_views().files.refresh_files()

# okay decompiling pyz_out/lib/controller/FilesController.pyc
