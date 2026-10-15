# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\session\__init__.py
import lib.project
import lib.util.logging as logging
from lib.util.commandline import CommandLine
configuration = lib.util.configuration.get()
load_project = CommandLine.get().args.load_project
if load_project is not None:
    current_project = lib.project.Project.load(load_project)
else:
    current_project = lib.project.Project.load()

def get_configuration():
    global configuration
    return configuration


def get_project():
    global current_project
    return current_project


def new_project():
    global current_project
    current_project = lib.project.Project.load()
    print(current_project)


def open_project(path):
    global current_project
    current_project = lib.project.Project.load(path)

# okay decompiling pyz_out/lib/util/session/__init__.pyc
