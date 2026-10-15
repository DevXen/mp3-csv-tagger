# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\controller\ConfigurationController.py
from lib.controller import Controller
import lib.util.session as session
from lib.util.sciter.events import Event
import sciter

class ConfigurationController(Controller):

    def __init__(self):
        super().__init__()

    @sciter.script
    def set_color_key(self, name, new_color, refresh_color_key_input=True):
        session.get_project().set_tag_color(name, background=new_color, overwrite=True)
        self.get_views().configuration.refresh_color_key(name, new_color, refresh_color_key_input)
        self.notify(self.ObservableEvents.COLOR_KEY_EVENTS.Change, {'name':name,  'color':new_color})

    @sciter.script
    def get_tag_names(self):
        return session.get_project().get_tag_names()

    @sciter.script
    def add_tag_name(self, tag_name, alternative_tag_name):
        session.get_project().add_tag_name(tag_name, alternative_tag_name)
        self.get_views().configuration.refresh_tag_names()
        self.refresh_csv_entries()

    @sciter.script
    def update_tag_name(self, old_tag_name, tag_name, old_alternative_tag_name, alternative_tag_name):
        session.get_project().update_tag_name(old_tag_name, tag_name, old_alternative_tag_name, alternative_tag_name)
        self.get_views().configuration.refresh_tag_names()
        self.refresh_csv_entries()

    @sciter.script
    def remove_tag_name(self, tag_name, alternative_tag_name):
        session.get_project().remove_tag_name(tag_name, alternative_tag_name)
        self.get_views().configuration.refresh_tag_names()
        self.refresh_csv_entries()

    @sciter.script
    def reset_tag_names(self):
        session.get_project().populate_alternative_names_table()
        self.get_views().configuration.refresh_tag_names()
        self.refresh_csv_entries()

    def refresh_csv_entries(self):
        self.get_controllers().csv.update_all_csv_entry_tags()

# okay decompiling pyz_out/lib/controller/ConfigurationController.pyc
