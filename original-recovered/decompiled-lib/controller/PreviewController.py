# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\controller\PreviewController.py
from lib.controller import Controller
from lib.util.dict2obj import Dict2Obj
import lib.util.session as session
import sciter

class PreviewController(Controller):
    ROW_LIMIT = 30
    DEFAULT_LAYER = -1

    def __init__(self):
        super().__init__()
        self.store = None
        self.current_layer = self.DEFAULT_LAYER
        self.column_headings = []
        self.row_offset = 0
        self.row_limit = PreviewController.ROW_LIMIT

    def reset_current_layer(self):
        self.current_layer = self.DEFAULT_LAYER

    @sciter.script
    def set_current_layer(self, layer, refresh=True):
        self.current_layer = layer
        if refresh is True:
            self.refresh()

    @sciter.script
    def get_current_layer(self):
        return self.current_layer

    def get_total_rows(self):
        return session.get_project().get_preview_total_rows(self.current_layer)

    def on_document_ready(self, frame, target):
        return

    @sciter.script
    def refresh(self, refresh_layers=True):
        self.get_views().preview.refresh_preview(refresh_layers)

    @sciter.script
    def get_preview_rows_stats(self):
        result = {'total':(self.get_total_rows)(), 
         'offset':self.row_offset, 
         'limit':self.row_limit}
        return result

    @sciter.script
    def page_up(self):
        self.row_offset -= self.row_limit
        if self.row_offset < 0:
            self.row_offset = 0
        self.refresh(refresh_layers=False)

    @sciter.script
    def page_down(self):
        if self.row_offset < self.get_total_rows() - self.row_limit:
            self.row_offset += self.row_limit
        self.refresh(refresh_layers=False)

    @sciter.script
    def get_preview_headings(self):
        result = ["MP3 File"]
        headings = session.get_project().get_preview_headings(self.current_layer)
        for heading in headings:
            result.append({"title": (heading[0])})

        return result

    @sciter.script
    def get_preview_rows(self):
        result = session.get_project().get_preview_data(self.current_layer, self.row_offset, self.row_limit)
        return result

    @sciter.script
    def get_layers(self):
        layers = session.get_project().get_preview_layers()
        return layers

    @sciter.script
    def get_tag_background(self, name):
        return session.get_project().get_tag_color(name).background

    @sciter.script
    def get_multiple_tag_values(self, preview_id):
        return session.get_project().get_preview_possible_values(int(preview_id))

    @sciter.script
    def set_selected_preview_id(self, old_preview_id, preview_id):
        session.get_project().set_preview_selected_value(old_preview_id, preview_id)

    @sciter.script
    def show_single_old_value(self, preview_id):
        preview = session.get_project().get_preview(preview_id)
        if preview is not None:
            old_value = preview.old_value
            if old_value is None or len(old_value) == 0:
                old_value = "No old value"
            self.get_views().dialogs.show_info_dialog(old_value, "Old value")

    def reset(self):
        self.reset_current_layer()

# okay decompiling pyz_out/lib/controller/PreviewController.pyc
