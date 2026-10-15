# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\controller\RunController.py
from lib.controller import Controller
import lib.util.session as session
import sciter, threading, time
from lib.project.preview import Preview

class RunController(Controller):

    def __init__(self):
        super().__init__()

    @sciter.script
    def run(self):
        self.get_views().progress.show(self.dialog_ready, self.dialog_message_callback)

    def dialog_ready(self):
        view = self.get_views().progress
        status_messages = {(Preview.STATUS_STARTING): "Starting", 
         (Preview.STATUS_MP3_FILES): "Reading MP3 files", 
         (Preview.STATUS_CSV_FILES): "Processing CSV files", 
         (Preview.STATUS_FINISHED): "Finished"}
        preview = Preview()

        def listener(status, msg=None):
            if status != Preview.STATUS_MP3_FILE and status != Preview.STATUS_CSV_FILE and status != Preview.STATUS_FINISHED and status != Preview.STATUS_ERROR:
                view.update_status(status_messages.get(status))
            else:
                if status == Preview.STATUS_MP3_FILE:
                    view.update_status(msg)
                else:
                    if status == Preview.STATUS_CSV_FILE:
                        view.update_status(msg)
                    else:
                        if status == Preview.STATUS_FINISHED:
                            view.close_dialog()
                            self.get_controllers().preview.reset()
                            self.get_views().preview.refresh()
                            self.get_views().root.show_preview_container()
                        else:
                            if status == Preview.STATUS_ERROR:
                                view.update_status_error(msg)

        preview.build(listener)

    def dialog_message_callback(self):
        return

# okay decompiling pyz_out/lib/controller/RunController.pyc
