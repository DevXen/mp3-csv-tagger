# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\controller\ApplyController.py
from lib.controller import Controller
import lib.util.session as session
from lib.util.mp3 import MP3File
from lib.util.csv import CSVFile
import lib.util as util
import lib.util.mp3.tagmanager as tagmanager
import logging, os, time
from lib.util.sciter.events import Event
import sciter
log = logging.getLogger("apply-controller")

class ApplyController(Controller):

    def __init__(self):
        super().__init__()

    @sciter.script
    def get_apply_logback_folder(self):
        return session.get_project().get_project_info().apply_log_folder

    @sciter.script
    def set_apply_logback_folder(self, folder):
        folder = folder.replace("/", os.path.sep)
        session.get_project().update_apply_logback_folder(folder)
        return folder

    @sciter.script
    def run(self):
        self.get_views().apply.clear_updates()
        try:
            logback_folder = self.get_apply_logback_folder()
            log_file = "mp3tag_" + time.strftime("%Y%m%d_%H%M%S") + ".log.csv"
            log_file = os.path.join(logback_folder, log_file)

            def csv_writer_listener(writer):
                log_headers = [
                 'Timestamp', 'File', 'Tag Name', 
                 'ID3 Frame', 'Original/Old Value', 'New Value']
                writer.writerow(log_headers)
                current_file = None

                def on_file(file):
                    global current_file
                    current_file = MP3File(file.path)
                    msg = "Applying tags to " + file.path
                    log.debug(msg)
                    self.get_views().apply.update(msg)

                def on_tag(tag):
                    _tag = tagmanager.create_tag(tag.tag_name, tag.value)
                    msg = "Writing tag {0:s} => {1:s}".format(tag.tag_name, tag.value)
                    timestamp = time.strftime("%Y/%m/%d %H:%M:%S")
                    log_values = [timestamp, current_file.full_path, tag.tag_name, tag.frame, session.get_project().get_original_old_value(tag), tag.value]
                    writer.writerow(log_values)
                    current_file.add_tag(_tag)
                    log.debug(msg)

                def on_file_complete(tag):
                    current_file.save()

                session.get_project().get_preview_tags_for_writing(on_file, on_tag, on_file_complete)

            CSVFile.writer(log_file, csv_writer_listener)
            self.get_views().apply.update("Completed. Log of old and new values: {0:s}".format(log_file))
        except Exception as e:
            try:
                stack = util.get_stack_trace()
                msg = "An error occurred trying to apply tags to files. There may be more information in the log file. {0:s}.\n\n{1:s}".format(str(e), stack)
                self.get_views().apply.update(msg)
                log.error(msg)
            finally:
                e = None
                del e

# okay decompiling pyz_out/lib/controller/ApplyController.pyc
