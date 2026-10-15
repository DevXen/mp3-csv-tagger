# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\resource\__init__.py
import os, sys, json
from lib.util.dict2obj import Dict2Obj
from lib.util.resource.container import ResourceContainer
container = ResourceContainer()

def load_file_content(filepath):
    content = None
    with open(filepath, "rb") as binary_file:
        content = b''
        while True:
            chunk = binary_file.read()
            if not chunk:
                break
            content += bytes(chunk)

    if content is None:
        return
    return Dict2Obj({'content':content, 
     'size':(os.path.getsize)(filepath)})


def load_resource_from_path(path, resource):
    if os.path.isdir(path):
        full_path = path + "/" + resource
        full_path = full_path.replace("/", os.sep)
        content = load_file_content(full_path)
        if content is not None:
            return content
    return


def load_resource_from_path_tree(path, resources_folder, resource):
    current = path
    content = None
    old = None
    while not current == old:
        if os.path.isdir(current):
            content = load_resource_from_path(current + "/" + resources_folder, resource)
            if content is not None:
                return content
            old = current
            current = os.path.dirname(current)

    return


def load(resource):
    global container
    if container.exists():
        content = container.load(resource)
        if content is not None:
            return content
    resources_folder = "resources"
    if os.path.isfile(resource):
        return load_file_content(resource)
    path = os.path.dirname(sys.argv[0])
    content = load_resource_from_path_tree(path, resources_folder, resource)
    if content is not None:
        return content
    path = os.path.dirname(sys.executable)
    content = load_resource_from_path_tree(path, resources_folder, resource)
    if content is not None:
        return content
    return


def load_json(resource):
    content = load(resource)
    if content is not None:
        return json.loads(content.content)
    return


def load_json_object(resource):
    json = load_json(resource)
    return Dict2Obj(json)

# okay decompiling pyz_out/lib/util/resource/__init__.pyc
