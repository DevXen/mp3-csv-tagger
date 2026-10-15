# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\template\__init__.py
import jinja2, os, inspect, html, logging
import lib.util.session as session
import lib.util.resource as resource
from lib.util.sciter import SciterUtil
log = logging.getLogger("template")

class Template:

    def __init__(self, owner, file=None, content=None, prepend_content=None, append_content=None):
        self.prepend_content = prepend_content
        self.content = content
        self.append_content = append_content
        self.child_templates = {}
        self.values = {}
        self.file = file
        if self.content is None:
            if file is not None:
                binary_content = resource.load(file)
                if binary_content is None:
                    raise FileNotFoundError("Cannot find template file: " + file)
                self.content = str((binary_content.content), encoding="utf-8")
        if self.content is None:
            self.content = ""

    def add_template(self, id, template, auto_append_variable=False):
        self.child_templates[id] = template
        if auto_append_variable:
            self.content += "{{" + id + "}}"

    def generate(self, add_params={}):
        if self.file is not None:
            log.debug("Generating file: " + self.file)
        template = jinja2.Template((self.content), autoescape=False)
        merged_values = {**(self.values), **add_params}
        for ti in self.child_templates:
            ct = self.child_templates[ti]
            child_content = ct.generate(add_params=merged_values)
            merged_values[ti] = child_content

        merged_values["session"] = session
        merged_values["project"] = session.get_project()
        merged_values["configuration"] = session.get_configuration()
        content = template.render(merged_values)
        if self.prepend_content is not None:
            content = self.prepend_content + content
        if self.append_content is not None:
            content = content + self.append_content
        return content

    def set_element_html(self, element):
        content = self.generate()
        SciterUtil.set_element_html(element, content)

    def append_element_html(self, element):
        content = self.generate()
        SciterUtil.append_element_html(element, content)

    def set(self, name, value):
        self.values[name] = value


class TIScriptTemplate(Template):
    __doc__ = "\n    This is a template for inserting TIScript templates into html templates (as a template chhild).\n    It wraps the template output in <script...></script> tags automatically so html template does\n    not need to remember to do it. (Not wrapping in <script/> tag just adds TIScript as text to html)\n    "

    def __init__(self, owner, file=None, content=None):
        super().__init__(owner, file, content, '<script type="text/tiscript">', "</script>")

# okay decompiling pyz_out/lib/util/template/__init__.pyc
