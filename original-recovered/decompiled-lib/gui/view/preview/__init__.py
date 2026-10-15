# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\gui\view\preview\__init__.py
from lib.gui.view.baseview import BaseView
from lib.util.sciter import SciterUtil
import sciter

class View(BaseView):

    def __init__(self, id, frame):
        super().__init__(id, frame)
        self.controller = self.get_controllers().preview

    def refresh_preview(self, refresh_layers=True):
        headings = self.controller.get_preview_headings()
        rows = self.controller.get_preview_rows()
        layers = self.controller.get_layers()
        if layers is None:
            return
        if refresh_layers is True:
            previewlayer = self.find_element_by_id("preview-layer")
            SciterUtil.set_element_html(previewlayer, " ")
            current_layer = self.controller.get_current_layer()
            html = ""
            for layer in layers:
                selected = ""
                if layer.get("layer") == current_layer:
                    selected = "selected"
                caption = layer.get("name")
                html += '<option value="{0:d}" {1:s}>{2:s}</option>'.format(layer.get("layer"), selected, caption)

            selected = ""
            if current_layer == -1:
                selected = "selected"
            caption = "All Layers"
            html += '<option value="{0:d}" {1:s}>{2:s}</option>'.format(-1, selected, caption)
            SciterUtil.set_element_html(previewlayer, html)
        backgrounds = {'match':(self.controller.get_tag_background)("match"), 
         'skip':(self.controller.get_tag_background)("skip"), 
         'write':(self.controller.get_tag_background)("write"), 
         'multiple':(self.controller.get_tag_background)("multiple"), 
         'nochange':(self.controller.get_tag_background)("nochange")}
        self.call_function("refresh_preview_table", headings, rows, backgrounds)
        return

    def on_document_ready(self, source, target):
        """
        Initialize event handling. There is a TIScript script that needs to be called.
        """
        self.call_function("previewManager.initialize_event_handling()")
        self.refresh_preview()

        def on_color_key_change(color_key):
            self.refresh()

        self.get_controllers().configuration.listen(self.ObservableEvents.COLOR_KEY_EVENTS.Change, on_color_key_change)

    def refresh(self):
        self.refresh_preview()

# okay decompiling pyz_out/lib/gui/view/preview/__init__.pyc
