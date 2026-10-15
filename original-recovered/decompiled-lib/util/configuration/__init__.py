# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\configuration\__init__.py
import json, os, sys
import lib.util.commandline as commandline
from lib.util.dict2obj import Dict2Obj
from pathlib import Path
import lib.util.resource as resource
content = resource.load("configuration.json")
if content is None:
    raise EnvironmentError("Unable to load configuration")
configuration = Dict2Obj(json.loads(content.content))

def get(path=None, default=None):
    if path is None:
        return configuration
    parts = path.split("/")
    current = configuration
    total = len(parts)
    idx = 0
    for i in parts:
        idx += 1
        v = current.get(i)
        if v is None:
            return default
        if idx == total:
            return v
        current = v

    return default


def tags():
    return configuration.tags


def logging():
    return configuration.logging

# okay decompiling pyz_out/lib/util/configuration/__init__.pyc
