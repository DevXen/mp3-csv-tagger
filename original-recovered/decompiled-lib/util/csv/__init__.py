# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\csv\__init__.py
import csv, os, logging
from lib.util import get_stack_trace
log = logging.getLogger("csv-file")

class CSVRow:

    def __init__(self):
        self.headings = []
        self.values = []

    def add(self, heading, value):
        self.headings.append(heading)
        self.values.append(value)

    def fields(self):
        return len(headings)

    def get_heading(self, index):
        return self.headings[index]

    def get_value(self, index):
        return self.values[index]

    def __str__(self):
        result = "CSVRow("
        for i in range(0, len(self.headings)):
            heading = self.headings[i]
            value = self.values[i]
            if i > 0:
                result += ", "
            result += heading + '="' + value + '"'

        result += ")"
        return result


class CSVFile:
    CHAR_ENCODING = "utf-8"

    def __init__(self, path):
        self.path = path

    def get_file_name(self):
        return os.path.basename(self.path)

    def headings(self):
        with open((self.path), "r", encoding=(CSVFile.CHAR_ENCODING)) as f:
            reader = csv.reader(f)
            headings = next(reader)
            return headings

    def rows(self, listener):
        log.debug("Getting rows for CSV file: {0:s}".format(self.path))
        with open((self.path), "r", encoding=(CSVFile.CHAR_ENCODING)) as f:
            reader = csv.reader(f)
            headings = next(reader)
            if headings is None or headings == "":
                return
            index = 0
            try:
                for row in reader:
                    index += 1
                    if row is not None and len(row) > 0:
                        result = CSVRow()
                        ci = 0
                        for heading in headings:
                            value = row[ci]
                            ci += 1
                            result.add(heading, value)

                        listener(result, index)

            except Exception as e:
                try:
                    st = get_stack_trace()
                    log.error("Unable to read CSV file: {0:s}.".format(self.path))
                    log.error("Error after line: {0:d}.".format(index + 1))
                    log.error(st)
                    raise RuntimeError("Error occurred reading CSV file. Check log file for more information.")
                finally:
                    e = None
                    del e

    @staticmethod
    def writer(path, listener):
        with open(path, "w", newline="") as f:
            writer = csv.writer(f, delimiter=",", quotechar='"', quoting=(csv.QUOTE_MINIMAL))
            listener(writer)

# okay decompiling pyz_out/lib/util/csv/__init__.pyc
