# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\csv\__init__.py
from lib.gui.view.baseview import BaseView
from lib.util.sciter import SciterUtil
from lib.util.dict2obj import Dict2Obj
from lib.project import Role
import lib.util.session as session
import sciter

class View(BaseView):

    def __init__(self, id, frame):
        super().__init__(id, frame)

    def refresh_entries_header(self):
        return

    def build_entry_templates(self, entry):
        """
        It appears that loading html into an element in Python, like below, does not execute/trigger
        scripts embedded in the html.

        To work around, we'll have a template for the script as well and eval it using the element.

        """
        template = self.get_template(file=(self.get_relative_resource_path("entry.html")))
        template.set("entry", entry)
        template.set("csv_file", entry.get_file_name())
        template.set("csv_path", entry.get_file_directory())
        template.set("tags", entry.get_tags())
        roles = Role.to_dict()
        options = {}
        for name in roles:
            value = roles[name]
            lname = name.lower()
            values = {'value':value,  'color':(session.get_project().get_tag_color(lname)).background,  'caption':name}
            options[lname] = values

        template.set("options", options)
        script_template = self.get_template(file=(self.get_relative_resource_path("entry.tis")))
        script_template.set("entry", entry)
        script_template.set("csv_file", entry.get_file_name())
        script_template.set("csv_path", entry.get_file_directory())
        script_template.set("tags", entry.get_tags())
        return Dict2Obj({'html':template,  'script':script_template})

    def update_entries(self):
        entries = session.get_project().get_csv_file_entries()
        for entry in entries:
            element = self.find_element_by_id("entry_" + str(entry.id))
            excluded_class = element.attribute("excluded-class")
            current_classes = element.attribute("class")
            if entry.included:
                current_classes = current_classes.replace(excluded_class, "")
            else:
                if current_classes.find(excluded_class) == -1:
                    current_classes += " " + excluded_class
            element.set_attribute("class", current_classes)

    def refresh_entries(self, update_tags=False):
        """
        This completely refreshes the CSV entries, it removes the existing HTML and rebuilds the list.
        This is opposed to update_entries() which updates existing CSV entry HTML.

        :param update_tags:
        :return:
        """
        element = self.find_element_by_id("csv-entries")
        entries = session.get_project().get_csv_file_entries()
        SciterUtil.set_element_html(element, " ")
        for entry in entries:
            templates = self.build_entry_templates(entry)
            templates.html.append_element_html(element)
            element.eval_script(templates.script.generate())

    def on_event(self, source, source_element, target, code, phase, reason):
        super().on_event(source, source_element, target, code, phase, reason)

    def on_document_ready(self, source, target):
        """
        Refresh view when screen is loaded.
        :param source:
        :param target:
        :return:
        """
        self.refresh_entries()

        def on_color_key_change(color_key):
            self.refresh_entries()

        self.get_controllers().configuration.listen(self.ObservableEvents.COLOR_KEY_EVENTS.Change, on_color_key_change)

    def refresh(self):
        self.refresh_entries()

# okay decompiling pyz_out/lib/gui/view/csv/__init__.pyc
