# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\mp3\tagmanager.py
import mutagen
from mutagen import id3
import lib.util.session as session
from lib.util.dict2obj import Dict2Obj
import lib.util.resource as resource
import logging
log = logging.getLogger("tag-manager")

def is_excluded(tag):
    if tag.find("APIC:") == 0:
        return True
    return False


def tag_to_hex(tag):
    if tag is None:
        return
    return tag.encode("UTF-8").hex()


def hex_to_tag(tag_in_hex):
    if tag_in_hex is None:
        return
    try:
        return bytes.fromhex(tag_in_hex)
    except ValueError as ve:
        try:
            return bytes(tag_in_hex, encoding="UTF-8")
        finally:
            ve = None
            del ve


def hex_to_tag_string(tag_in_hex):
    return str((hex_to_tag(tag_in_hex)), encoding="UTF-8")


def hex_to_stripped_tag(tag_in_hex):
    hex = hex_to_tag(tag_in_hex)
    hex = str(hex, encoding="UTF-8")
    hex = hex.replace("\x00", "")
    return hex


def get_tag_text_as_string(tag):
    result = ""
    text = tag.text
    if isinstance(text, list):
        for s in text:
            result += str(s)

    return result


def get_mp3_tag_info(tag):
    frame_id = tag.FrameID
    result = {'frame':frame_id, 
     'ignore':False}
    if frame_id == "PRIV":
        result["ignore"] = True
    if frame_id == "APIC":
        result["ignore"] = True
    if frame_id == "TXXX":
        result["name"] = tag.desc
        result["value"] = get_tag_text_as_string(tag)
        return Dict2Obj(result)
    text = getattr(tag, "text", None)
    result["value"] = None
    if text is not None:
        result["value"] = get_tag_text_as_string(tag)
    result["name"] = frame_id
    return Dict2Obj(result)


def get_frame_for_tag_name(tag_name):
    tag = session.get_project().get_tag_by_alternative_name(tag_name)
    if tag is not None:
        log.debug("get_frame_for_tag_name: {0:s} = {1:s}".format(tag_name, tag.name))
        return tag.name
    log.debug("get_frame_for_tag_name: {0:s} = {1:s}".format(tag_name, "TXXX"))
    return "TXXX"


def get_id3_class_for_tag_name(name):
    tagclass = getattr(id3, name, None)
    if tagclass is None:
        tagclass = id3.TXXX
    return tagclass


def create_tag(name, value):
    log.debug("Creating tag: {0:s} => {1:s}".format(name, value))
    tagclass = getattr(id3, name, None)
    if tagclass is None:
        tagclass = id3.TXXX
    tag = tagclass()
    text = getattr(tag, "text", None)
    if isinstance(tag, id3.TXXX):
        setattr(tag, "desc", name)
    if text is not None:
        log.debug("Setting 'text' attribute on tag: {0:s} to : {0:s}".format(str(tagclass), value))
        setattr(tag, "text", [value])
        return tag
    data = getattr(tag, "data", None)
    if data is not None:
        log.debug("Setting 'data' attribute on tag: {0:s} to : {0:s}".format(str(tagclass), value))
        setattr(tag, "data", bytes(value))
        return tag
    data = getattr(tag, "url", None)
    if data is not None:
        log.debug("Setting 'url' attribute on tag: {0:s} to : {0:s}".format(str(tagclass), value))
        setattr(tag, "url", value)
        return tag
    raise RuntimeError("Cannot find an appropriate attribute for value (tried text, data, url) in tag class: {0:s}".format(str(tagclass)))

# okay decompiling pyz_out/lib/util/mp3/tagmanager.pyc
