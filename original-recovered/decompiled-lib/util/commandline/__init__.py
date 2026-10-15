# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\commandline\__init__.py
import argparse

class CommandLine:
    instance = None

    def __init__(self):
        parser = argparse.ArgumentParser(description="MP3 Tagging")
        parser.add_argument("--copy_preview_to", help=(argparse.SUPPRESS))
        parser.add_argument("--load_project", help=(argparse.SUPPRESS))
        self.args = parser.parse_args()

    @staticmethod
    def get():
        if CommandLine.instance is None:
            CommandLine.instance = CommandLine()
        return CommandLine.instance

# okay decompiling pyz_out/lib/util/commandline/__init__.pyc
