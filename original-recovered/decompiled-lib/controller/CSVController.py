# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\controller\CSVController.py
from lib.controller import Controller
import lib.util.session as session
from lib.util.sciter.events import Event
import sciter, logging
from lib.util import get_stack_trace
log = logging.getLogger("csv-controller")

class CSVController(Controller):

    def __init__(self):
        super().__init__()

    @sciter.script
    def add_csv(self, filename):
        try:
            new_entry = session.get_project().add_csv_file_entry(filename)
        except Exception as e:
            try:
                st = get_stack_trace()
                log.error("Unable to add CSV entry.")
                log.error(st)
                self.get_views().dialogs.show_info_dialog(("Unable to add CSV file, check log file for more information. " + str(e)), title="Error")
            finally:
                e = None
                del e

        self.get_views().csv.refresh_entries()

    @sciter.script
    def tag_changed(self, tag_id, value):
        session.get_project().set_csv_tag_role(tag_id, value)

    @sciter.script
    def include_changed(self, csv_entry_id, included):
        csv_entry = session.get_project().update_csv_entry_included(csv_entry_id, included)
        if csv_entry is not None:
            self.get_views().csv.update_entries()

    @sciter.script
    def delete_csv_entry(self, csv_entry_id):
        session.get_project().delete_csv_file_entry(csv_entry_id)
        self.get_views().csv.refresh_entries()

    @sciter.script
    def move_entry_up(self, csv_entry_id):
        session.get_project().change_csv_entry_apply_order(csv_entry_id, 0)
        self.get_views().csv.refresh_entries()

    @sciter.script
    def move_entry_down(self, csv_entry_id):
        session.get_project().change_csv_entry_apply_order(csv_entry_id, 1)
        self.get_views().csv.refresh_entries()

    @sciter.script
    def update_csv_entry_tags(self, csv_entry_id):
        session.get_project().update_csv_entry_tags(csv_entry_id)
        self.get_views().csv.refresh_entries()

    @sciter.script
    def update_all_csv_entry_tags(self):
        session.get_project().update_all_csv_entry_tags()
        self.get_views().csv.refresh_entries()

# okay decompiling pyz_out/lib/controller/CSVController.pyc
