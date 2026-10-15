# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\project\preview\__init__.py
import lib.util.session as session
import pickle
from lib.project import Role
from lib.util.mp3 import *
import lib.util.mp3.tagmanager as tagmanager
from lib.util.csv import CSVFile
import lib.util as util
from lib.util import Timing
from lib.util.dict2obj import Dict2Obj
from datetime import datetime
import logging, string
log = logging.getLogger("preview")

class Preview:
    STATUS_STARTING = 1
    STATUS_MP3_FILES = 2
    STATUS_MP3_FILE = 3
    STATUS_CSV_FILES = 4
    STATUS_CSV_FILE = 5
    STATUS_FINISHED = 6
    STATUS_ERROR = 7

    def __init__(self):
        return

    def build(self, listener):
        try:
            listener(self.STATUS_STARTING)
            try:
                project = session.get_project()
                project.prepare_preview()
                listener(self.STATUS_MP3_FILES)
                log.debug("Scanning and importing MP3 files and tags into store.")
                mp3s = Mp3Scanner()
                start = datetime.now()

                def mp3_file_listener(mp3):
                    end = datetime.now()
                    elapsed = int((end - start).seconds / 60)
                    msg = "Processing " + mp3.full_path + ".<br/><br/>Elapsed Time(mins): " + str(elapsed)
                    listener(self.STATUS_MP3_FILE, msg)
                    file = project.add_preview_mp3_file(mp3.full_path)
                    tags = mp3.get_tags()
                    for tag in tags:
                        value = tags[tag]
                        tag_info = tagmanager.get_mp3_tag_info(value)
                        if not tag_info.ignore:
                            ptag = project.add_preview_mp3_tag(file, tag_info.name, tag_info.value, tag_info.frame, value)

                for path in project.get_mp3_paths():
                    mp3s.scan(path, mp3_file_listener)

                end = datetime.now()
                log.debug("Adding mp3 files to project took: {0:d} seconds".format((end - start).seconds))
                start = datetime.now()
                listener(self.STATUS_CSV_FILES)
                write_value_tracking = {}
                for csv_entry in project.get_csv_file_entries():
                    if csv_entry.included is True:
                        csv_file = CSVFile(csv_entry.path)
                        tags = csv_entry.get_tags()
                        match_tags_idxs = []
                        match_tags_comparison_ids = []
                        csv_match_tags = {}
                        write_tags_idxs = []
                        write_tags_comparison_ids = []
                        csv_write_tags = {}
                        skip_tags_idxs = []
                        csv_skip_tags = {}
                        for tag in tags:
                            if tag.role == Role.Match:
                                match_tags_idxs.append(tag.tag_index)
                                csv_tag_instance = project.get_csv_tag_instance_by_index(csv_entry, tag.tag_index)
                                csv_match_tags[tag.tag_index] = csv_tag_instance
                                match_tags_comparison_ids.append(csv_tag_instance.tag_comparison_id)
                            else:
                                if tag.role == Role.Write:
                                    write_tags_idxs.append(tag.tag_index)
                                    csv_tag_instance = project.get_csv_tag_instance_by_index(csv_entry, tag.tag_index)
                                    csv_write_tags[tag.tag_index] = csv_tag_instance
                                    write_tags_comparison_ids.append(csv_tag_instance.tag_comparison_id)

                        mp3_files = project.get_matching_preview_mp3_files(match_tags_comparison_ids, write_tags_comparison_ids)
                        for mp3_file in mp3_files:
                            mp3_file.match_count = 0
                            write_mp3_tags = {}
                            match_tags = {}
                            for mp3_tag in mp3_file.tags:
                                for index in match_tags_idxs:
                                    csv_tag = csv_match_tags[index]
                                    if mp3_tag.tag_comparison_id == csv_tag.tag_comparison_id:
                                        mp3_file.match_count += 1
                                        mp3_file.match_mp3_tags[index] = mp3_tag
                                        mp3_file.match_csv_tags[index] = csv_tag

                                for index in write_tags_idxs:
                                    csv_tag = csv_write_tags[index]
                                    if mp3_tag.tag_comparison_id == csv_tag.tag_comparison_id:
                                        mp3_file.write_mp3_tags[index] = mp3_tag
                                        mp3_file.write_csv_tags[index] = csv_tag

                                if mp3_file.match_count == len(match_tags_idxs):
                                    mp3_file.matched = True
                                for index in skip_tags_idxs:
                                    csv_tag = csv_skip_tags[index]
                                    if mp3_tag.tag_comparison_id == csv_tag.tag_comparison_id:
                                        mp3_file.skip_mp3_tags[index] = mp3_tag
                                        mp3_file.skip_csv_tags[index] = csv_tag

                        def row_listener(csv_row, csv_row_index):
                            if csv_row_index <= 10 or csv_row_index % 150 == 0:
                                end = datetime.now()
                                elapsed = int((end - start).seconds / 60)
                                msg = "Processing " + csv_entry.path + ".<br/><br/> Row " + str(csv_row_index) + "<br/><br/>Elapsed Time(mins): " + str(elapsed)
                                listener(self.STATUS_CSV_FILE, msg)
                            for mp3_file in mp3_files:
                                match_count = 0
                                write_mp3_tags = {}
                                match_tags = {}
                                if mp3_file.matched == True:
                                    for index in mp3_file.match_mp3_tags:
                                        mp3_tag = mp3_file.match_mp3_tags[index]
                                        csv_tag = mp3_file.match_csv_tags[index]
                                        csv_value = csv_row.get_value(index - 1)
                                        csv_value = csv_value.lower()
                                        csv_value = csv_value.translate(str.maketrans("", "", string.punctuation))
                                        wvt_key = (
                                         mp3_file.id, csv_tag.tag_comparison_id)
                                        mp3_value = write_value_tracking.get(wvt_key)
                                        if mp3_value is None:
                                            mp3_value = mp3_tag.value
                                        mp3_value = mp3_value.lower()
                                        mp3_value = mp3_value.translate(str.maketrans("", "", string.punctuation))
                                        if mp3_value == csv_value:
                                            match_count += 1
                                            match_tags[index] = mp3_tag

                                    for index in mp3_file.write_mp3_tags:
                                        mp3_tag = mp3_file.write_mp3_tags[index]
                                        csv_tag = mp3_file.write_csv_tags[index]
                                        csv_value = csv_row.get_value(index - 1)
                                        write_mp3_tags[index] = Dict2Obj({'tag':mp3_tag,  'csv_tag':csv_tag,  'value':csv_value})

                                if match_count == len(match_tags_idxs):
                                    for idx in match_tags:
                                        match_tag = match_tags[idx]
                                        project.add_preview((mp3_file.id), (match_tag.name), None, (match_tag.value), (Role.Match), csv_entry,
                                          csv_row_index, (match_tag.id), tag_group=1)

                                    new_write_mp3_tags = {}
                                    for index in write_tags_idxs:
                                        write_tag = write_mp3_tags.get(index)
                                        if write_tag is None:
                                            csv_tag = project.get_csv_tag_by_index(csv_entry, index)
                                            csv_value = csv_row.get_value(index - 1)
                                            new_write_mp3_tags[index] = Dict2Obj({'tag':csv_tag,  'value':csv_value})
                                            project.add_preview((mp3_file.id), (csv_tag.name), None, csv_value, (Role.Write),
                                              csv_entry,
                                              csv_row_index, None, frame=(tagmanager.get_frame_for_tag_name(csv_tag.name)), tag_group=2)
                                            wvt_key = (
                                             mp3_file.id, csv_tag.tag_comparison_id)
                                            write_value_tracking[wvt_key] = csv_value
                                        else:
                                            project.add_preview((mp3_file.id), (write_tag.tag.name), (write_tag.tag.value), (write_tag.value), (Role.Write),
                                              csv_entry,
                                              csv_row_index, (write_tag.tag.id), frame=(write_tag.tag.frame), tag_group=2)
                                            wvt_key = (
                                             mp3_file.id, write_tag.csv_tag.tag_comparison_id)
                                            write_value_tracking[wvt_key] = csv_value

                                    for idx in mp3_file.skip_csv_tags:
                                        skip_tag = mp3_file.skip_csv_tags[idx]
                                        csv_value = csv_row.get_value(idx - 1)
                                        project.add_preview((mp3_file.id), (skip_tag.name), None, csv_value, (Role.Skip), csv_entry,
                                          csv_row_index, (skip_tag.id), ignore_if_exists=True, tag_group=2)

                        csv_file.rows(row_listener)

            except Exception as e:
                try:
                    util.dump_stack_trace()
                    log.error(e)
                    listener(self.STATUS_ERROR, "Unable to build preview. " + str(e))
                finally:
                    e = None
                    del e

        finally:
            listener(self.STATUS_FINISHED)

# okay decompiling pyz_out/lib/project/preview/__init__.pyc
