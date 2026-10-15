# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\mp3\__init__.py
import mutagen, os, json, time, logging, datetime
from mutagen.id3 import ID3
from mutagen.id3 import PRIV, TXXX
from lib.util.resource import load, load_json, load_json_object
log = logging.getLogger("mp3-scanning")

class MP3File:

    def __init__(self, *argv):
        if len(argv) == 2:
            self.path = argv[0]
            self.file = argv[1]
            self.full_path = self.path + "/" + self.file
        else:
            if len(argv) == 1:
                self.full_path = argv[0]
                self.path = os.path.dirname(self.full_path)
                self.file = os.path.basename(self.full_path)
        self.id3 = ID3(self.full_path)

    def get_tags(self):
        tags = {}
        keys = self.id3.keys()
        for key in keys:
            value = self.id3[key]
            tags[key] = value

        return tags

    def add_tag(self, tag):
        self.id3.add(tag)

    def add_custom_tag(self, name, value):
        self.id3.add(TXXX(desc=name, text=value))

    def remove_tag(self, name):
        """

        Examples:
            self.remove_tag("PRIV:custom1")
            self.remove_tag("TXXX:custom1")
            self.remove_tag("PRIV:mp3-tagger-subgenre")
        :param name:
        :return:
        """
        self.id3.delall(name)

    def dump(self):
        log.debug(self.full_path)
        log.debug("---------------------------------------")
        keys = self.id3.keys()
        for key in keys:
            log.debug("Key: {0:s}    Value: {1:s}".format(key, str(self.id3[key])))

    def save(self):
        self.id3.save()


class DummyMp3File:

    def __init__(self, path, file):
        self.path = path
        self.file = file
        self.full_path = path + "/" + file
        self.id3 = ID3("D:/Temp/music/Rage Against the Machine/Rage Against the Machine/09 Township Rebellion.mp3")

    def get_tags(self):
        tags = {}
        keys = self.id3.keys()
        for key in keys:
            tags[key] = self.id3[key]

        return tags


class Mp3Scanner:

    def __init__(self):
        return

    def scan(self, path, listener):
        if os.path.isfile(path):
            listener(MP3File(os.path.dirname(path), os.path.basename(path)))
        else:
            if os.path.isdir(path):
                for dir_name, sub_dirs, files in os.walk(path, topdown=False):
                    for fname in files:
                        if fname.lower().find(".mp3") > -1:
                            mp3 = MP3File(dir_name, fname)
                            listener(mp3)


class DummyMp3Scanner:

    def __init__(self, folders, sub_folders, files, delay):
        self.folders = folders
        self.sub_folders = sub_folders
        self.files = files
        self.delay = delay

    def scan(self, folder, listener):
        for fi in range(1, self.folders + 1):
            log.debug("fi={0:d}".format(fi))
            for sfi in range(1, self.sub_folders + 1):
                for ffi in range(1, self.files + 1):
                    if self.delay > 0:
                        time.sleep(self.delay)
                    path = "c:\\dummy\\dummy\\dummy\\dummy\\dummy\\dummy\\music_folder_" + str(fi) + "\\sub_folder_" + str(sfi)
                    file = "music_file_" + str(ffi) + ".mp3"
                    listener(DummyMp3File(path, file))


return

# okay decompiling pyz_out/lib/util/mp3/__init__.pyc
