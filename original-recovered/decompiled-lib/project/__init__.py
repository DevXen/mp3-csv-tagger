# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\project\__init__.py
import os, enum, sqlite3, logging, tempfile, shutil, pickle
import lib.util.configuration as configuration
import lib.util as util
from lib.util.csv import CSVFile
import lib.util.resource as resource
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Sequence, Index
from sqlalchemy import Column, Integer, String, Boolean, LargeBinary
from sqlalchemy import ForeignKey, UniqueConstraint, PrimaryKeyConstraint
from sqlalchemy.orm import relationship, scoped_session, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy import func, text, or_
log = logging.getLogger("project")
Base = declarative_base()

class ProjectInfo(Base):
    __tablename__ = "project"
    version = Column(Integer, (Sequence("version_seq")), primary_key=True)
    description = Column(String)
    apply_log_folder = Column(String)


class TagColor(Base):
    __tablename__ = "tag_color"
    id = Column(Integer, (Sequence("folder_seq")), primary_key=True)
    name = Column(String)
    background = Column(String)
    foreground = Column(String)
    __table_args__ = (
     UniqueConstraint("name", name="tag_color_ux"),)


class AlternativeName(Base):
    __tablename__ = "alternative_name"
    id = Column(Integer, (Sequence("alt_name_seq")), primary_key=True)
    name = Column(String)
    alternative_name = Column(String)
    __table_args__ = (
     UniqueConstraint("alternative_name", name="alt_name_pk"),)


class Mp3Folder(Base):
    __tablename__ = "mp3_folder"
    id = Column(Integer, (Sequence("folder_seq")), primary_key=True)
    path = Column(String)
    __table_args__ = (
     UniqueConstraint("path", name="folder_path_ux"),)


class Mp3File(Base):
    __tablename__ = "mp3_file"
    id = Column(Integer, (Sequence("file_seq")), primary_key=True)
    path = Column(String)
    folder_id = Column(Integer, ForeignKey("mp3_folder.id"))
    folder = relationship("Mp3Folder", back_populates="files")


Mp3Folder.files = relationship("Mp3File", order_by=(Mp3File.id), back_populates="folder")

class TagsForComparison(Base):
    __tablename__ = "tag_for_comparison"
    id = Column(Integer, (Sequence("tagcmp_seq")), primary_key=True)
    name = Column(String)
    __table_args__ = (
     UniqueConstraint("name", name="tagcmp_uk"),)


class CsvEntry(Base):
    __tablename__ = "csv_entry"
    id = Column(Integer, (Sequence("file_seq")), primary_key=True)
    path = Column(String)
    apply_index = Column(Integer)
    included = Column(Boolean, default=True)
    __table_args__ = (
     UniqueConstraint("path", name="csv_entry_uk"),)

    def get_file_name(self):
        return os.path.basename(self.path)

    def get_file_directory(self):
        return os.path.dirname(self.path)

    def get_tags(self):
        return self.tags


class CsvEntryTag(Base):
    __tablename__ = "csv_entry_tag"
    id = Column(Integer, (Sequence("file_seq")), primary_key=True)
    name = Column(String)
    tag_index = Column(Integer)
    role = Column(Integer)
    tag_comparison_id = Column(Integer)
    csv_entry_id = Column(Integer, ForeignKey("csv_entry.id"))
    csv_entry = relationship("CsvEntry", back_populates="tags")


CsvEntry.tags = relationship("CsvEntryTag", order_by=(CsvEntryTag.tag_index), back_populates="csv_entry")

class PreviewMp3File(Base):
    __tablename__ = "preview_mp3_file"
    id = Column(Integer, (Sequence("prev_mp3file_seq")), primary_key=True)
    path = Column(String)


class PreviewMp3FileTag(Base):
    __tablename__ = "preview_mp3_tag"
    id = Column(Integer, (Sequence("prev_mp3filetag_seq")), primary_key=True)
    name = Column(String)
    value = Column(String)
    frame = Column(String)
    tag_data = Column(LargeBinary)
    tag_comparison_id = Column(Integer)
    mp3_file_id = Column(Integer, ForeignKey("preview_mp3_file.id"))
    mp3_file = relationship("PreviewMp3File", back_populates="tags")


PreviewMp3File.tags = relationship("PreviewMp3FileTag", order_by=(PreviewMp3FileTag.id), back_populates="mp3_file")

class Preview(Base):
    __tablename__ = "preview"
    id = Column(Integer, (Sequence("preview_seq")), primary_key=True)
    mp3_file_id = Column(Integer, ForeignKey("preview_mp3_file.id"))
    mp3_file = relationship("PreviewMp3File", back_populates="preview")
    frame = Column(String)
    tag_name = Column(String)
    alt_tag_name = Column(String)
    old_value = Column(String)
    previous_preview_id = Column(Integer)
    next_preview_id = Column(Integer)
    value = Column(String)
    role = Column(Integer)
    layer = Column(Integer)
    tag_group = Column(Integer)
    tag_comparison_id = Column(Integer)
    csv_entry_id = Column(Integer, ForeignKey("csv_entry.id"))
    csv_entry = relationship("CsvEntry", back_populates="preview")
    csv_row_index = Column(Integer)
    selected = Column(Boolean, default=False)
    mp3_file_tag_id = Column(Integer, ForeignKey("preview_mp3_tag.id"))
    mp3_file_tag = relationship("PreviewMp3FileTag", back_populates="preview")


Index("idx_preview_file_tag_comparison", Preview.mp3_file_id, Preview.tag_comparison_id)
CsvEntry.preview = relationship("Preview", order_by=(CsvEntryTag.id), back_populates="csv_entry")
PreviewMp3File.preview = relationship("Preview", back_populates="mp3_file")
PreviewMp3FileTag.preview = relationship("Preview", back_populates="mp3_file_tag")

class Role(enum.IntEnum):
    Match = 1
    Write = 2
    Skip = 3

    @staticmethod
    def to_dict():
        result = {}
        numbers = list(map(int, Role))
        for number in numbers:
            role = Role(number)
            result[role.name] = number

        return result


class Project:
    existing_project = None

    def __init__(self, file_path, loaded_from_file_path=None, is_new=True):
        self.file_path = file_path
        self.loaded_from_file_path = loaded_from_file_path
        self.is_new = is_new
        self._open()
        return

    @staticmethod
    def close():
        if Project.existing_project is not None:
            Project.existing_project._close()
            Project.existing_project = None

    @staticmethod
    def load(path_name=None):
        if path_name is not None:
            path_name = path_name.replace("/", os.sep)
        Project.close()
        temp_file = util.get_temporary_file("mp3_project")
        if path_name is not None:
            if os.path.isfile(path_name):
                shutil.copy(path_name, temp_file)
        Project.existing_project = Project(temp_file, loaded_from_file_path=path_name, is_new=(path_name is None))
        return Project.existing_project

    def save(self, path_name=None):
        if path_name is not None:
            path_name = path_name.replace("/", os.sep)
        if path_name is None:
            if self.loaded_from_file_path is not None:
                path_name = self.loaded_from_file_path
        if path_name is None:
            raise RuntimeError("No path available to save project to.")
        self.getSession().commit()
        shutil.copy(self.file_path, path_name)
        if self.is_new is True:
            self.is_new = False
        self.loaded_from_file_path = path_name

    def _open(self):
        debugSql = False
        echo = False
        if debugSql:
            echo = True
        self.engine = create_engine(("sqlite:///" + self.file_path), echo=echo)
        if debugSql:
            logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
        self.conn = self.engine.connect()
        self.conn.execute("PRAGMA synchronous = OFF")
        self.conn.execute("PRAGMA journal_mode = MEMORY")
        self.session_factory = sessionmaker(bind=(self.conn))
        self.Session = scoped_session(self.session_factory)
        self.session = self.Session()
        self.create_database()
        self.get_project_info()

    def _close(self):
        if getattr(self, "session", None) is not None:
            self.session.flush()
            self.session.expunge_all()
            self.session.close()
            self.session = None
            self.Session.remove()
            self.Session = None
            self.conn.close()
            self.conn = None
            self.session_factory = None
            self.engine = None

    def getSession(self):
        if self.Session is None:
            self._open()
        return self.session

    def get_another_instance(self):
        return Project(self.file_path)

    def create_database(self):
        Base.metadata.create_all(bind=(self.engine))
        for tag_color in configuration.get().tags.colors.default.__dict__:
            tag_config = configuration.get().tags.colors.default.__dict__[tag_color]
            self.set_tag_color(tag_color, background=(tag_config.get("background")), foreground=(tag_config.get("foreground")))

        if self.is_new:
            self.populate_alternative_names_table()

    def get_project_info(self):
        result = self.getSession().query(ProjectInfo).first()
        if result is None:
            result = ProjectInfo()
            result.apply_log_folder = os.path.join(os.path.expanduser("~"), "mp3tagging")
            os.makedirs((result.apply_log_folder), exist_ok=True)
            self.getSession().add(result)
            self.getSession().commit()
        return result

    def update_apply_logback_folder(self, folder):
        project_info = self.get_project_info()
        project_info.apply_log_folder = folder
        self.getSession().add(project_info)
        self.getSession().commit()

    def set_tag_color(self, name, background=None, foreground=None, overwrite=False):
        existing = self.getSession().query(TagColor).filter(TagColor.name == name).first()
        if not existing:
            tag_color = TagColor(name=name, background=background, foreground=foreground)
            existing = self.getSession().add(tag_color)
            self.getSession().commit()
        else:
            if overwrite is True:
                if foreground is not None:
                    existing.foreground = foreground
                if background is not None:
                    existing.background = background
                self.getSession().add(existing)
                self.getSession().commit()
        return existing

    def get_tag_color(self, name):
        existing = self.getSession().query(TagColor).filter(TagColor.name == name).first()
        if existing is None:
            return
        return existing

    def add_comparison_tag_name(self, tag_name):
        alternative = self.getSession().query(AlternativeName).filter(AlternativeName.alternative_name == tag_name).first()
        if alternative is not None:
            tag_name = alternative.name
        tag_name = tag_name.lower()
        existing = self.getSession().query(TagsForComparison).filter(TagsForComparison.name == tag_name).first()
        if existing is None:
            existing = TagsForComparison()
            existing.name = tag_name
            self.getSession().add(existing)
            self.getSession().commit()
        return existing

    def clear_mp3_paths(self):
        self.getSession().query(Mp3File).delete()
        self.getSession().query(Mp3Folder).delete()

    def add_mp3_folder(self, path):
        path = path.replace("/", os.sep)
        if os.path.isfile(path):
            path = os.path.dirname(path)
        if os.path.isdir(path):
            folder = self.getSession().query(Mp3Folder).filter(Mp3Folder.path == path).first()
            if not folder:
                folder = Mp3Folder(path=path)
                result = self.getSession().add(folder)
                self.getSession().commit()
            return folder
        return

    def add_mp3_file(self, path):
        path = path.replace("/", os.sep)
        if not os.path.isfile(path):
            return
        folder = self.add_mp3_folder(path)
        name = os.path.basename(path)
        file = self.getSession().query(Mp3File).filter(Mp3File.path == path, Mp3File.folder_id == folder.id).first()
        if not file:
            file = Mp3File(path=name, folder_id=(folder.id))
            self.getSession().add(file)
            self.getSession().commit()
        return file

    def add_mp3_path(self, path):
        if os.path.isdir(path):
            folder = self.add_mp3_folder(path)
        else:
            if os.path.isfile(path):
                file = self.add_mp3_file(path)

    def delete_mp3_path(self, path):
        folder_path = os.path.dirname(path)
        name = os.path.basename(path)
        folder = self.getSession().query(Mp3Folder).filter(Mp3Folder.path == path).first()
        if folder:
            if folder.files is None or len(folder.files) == 0:
                self.getSession().delete(folder)
                self.getSession().commit()
            return
        folder = self.getSession().query(Mp3Folder).filter(Mp3Folder.path == folder_path).first()
        if folder:
            file = self.getSession().query(Mp3File).filter(Mp3File.folder_id == folder.id, Mp3File.path == name).first()
            if file:
                self.getSession().delete(file)
                self.getSession().commit()
                if folder.files is None or len(folder.files) == 0:
                    self.getSession().delete(folder)
                    self.getSession().commit()

    def get_mp3_paths(self):
        """
        This returns a merged list of folders and files.
        :return:
        """
        result = []
        folders = self.getSession().query(Mp3Folder).all()
        for folder in folders:
            if folder.files is None or len(folder.files) == 0:
                result.append(folder.path)
            else:
                for file in folder.files:
                    result.append(os.path.join(folder.path, file.path))

        return result

    def get_csv_file_entries(self):
        return self.getSession().query(CsvEntry).order_by(CsvEntry.apply_index).all()

    def get_csv_file_entry_highest_apply_index(self):
        result = self.getSession().query(func.max(CsvEntry.apply_index)).scalar()
        if result is None:
            return 0
        return result

    def change_csv_entry_apply_order(self, csv_entry_id, direction):
        entry = self.get_csv_entry_by_id(csv_entry_id)
        if not entry:
            return
        max_apply_index = self.get_csv_file_entry_highest_apply_index()
        if direction == 0:
            if entry.apply_index > 1:
                swap_with = self.getSession().query(CsvEntry).filter(CsvEntry.apply_index == entry.apply_index - 1).first()
                if swap_with:
                    temp = swap_with.apply_index
                    swap_with.apply_index = entry.apply_index
                    entry.apply_index = temp
                    self.getSession().add(swap_with)
                    self.getSession().add(entry)
                    self.getSession().commit()
        else:
            if entry.apply_index < max_apply_index:
                swap_with = self.getSession().query(CsvEntry).filter(CsvEntry.apply_index == entry.apply_index + 1).first()
                if swap_with:
                    temp = swap_with.apply_index
                    swap_with.apply_index = entry.apply_index
                    entry.apply_index = temp
                    self.getSession().add(swap_with)
                    self.getSession().add(entry)
                    self.getSession().commit()

    def add_csv_file_entry(self, file_path):
        existing = self.getSession().query(CsvEntry).filter(CsvEntry.path == file_path).first()
        if existing:
            raise ValueError("Another CSV entry for the same path already exists: " + file_path)
        apply_index = self.get_csv_file_entry_highest_apply_index() + 1
        entry = CsvEntry(path=file_path, apply_index=apply_index)
        tags = self.update_csv_entry_tags(entry, return_only=True)
        self.getSession().add(entry)
        self.getSession().add_all(tags)
        self.getSession().commit()
        return entry

    def delete_csv_file_entry(self, csv_file_id):
        csv_file_entry = self.getSession().query(CsvEntry).filter(CsvEntry.id == csv_file_id).first()
        if csv_file_entry is not None:
            csv_tags = self.getSession().query(CsvEntryTag).filter(CsvEntryTag.csv_entry_id == csv_file_id).all()
            for csv_tag in csv_tags:
                self.getSession().delete(csv_tag)

            self.getSession().query(CsvEntry).filter(CsvEntry.id == csv_file_id).delete()

    def update_all_csv_entry_tags(self):
        entries = self.get_csv_file_entries()
        for entry in entries:
            self.update_csv_entry_tags(entry)

    def update_csv_entry_tags(self, entry, return_only=False):
        if isinstance(entry, CsvEntry):
            old_tags_query = self.getSession().query(CsvEntryTag).filter(CsvEntryTag.csv_entry_id == entry.id)
        else:
            entry = self.get_csv_entry_by_id(entry)
            old_tags_query = self.getSession().query(CsvEntryTag).filter(CsvEntryTag.csv_entry_id == entry.id)
        old_tags = old_tags_query.all()
        if return_only is False:
            old_tags_query.delete()
        csv = CSVFile(entry.path)
        headings = csv.headings()
        index = 1
        tags = []
        for heading in csv.headings():
            comparison = self.add_comparison_tag_name(heading)
            tag = CsvEntryTag(name=heading, tag_index=index, csv_entry=entry, role=(Role.Skip), tag_comparison_id=(comparison.id))
            for old_tag in old_tags:
                if old_tag.name == tag.name and old_tag.tag_index == tag.tag_index:
                    tag.role = old_tag.role

            tags.append(tag)
            index += 1

        if return_only is False:
            self.getSession().add_all(tags)
            self.getSession().commit()
        return tags

    def get_csv_entry_by_id(self, id):
        return self.getSession().query(CsvEntry).filter(CsvEntry.id == id).first()

    def update_csv_entry_included(self, id, included):
        entry = self.get_csv_entry_by_id(id)
        if entry:
            entry.included = included
            self.getSession().add(entry)
            self.getSession().commit()
            return entry
        return

    def get_csv_tag_by_id(self, id):
        return self.getSession().query(CsvEntryTag).filter(CsvEntryTag.id == id).first()

    def set_csv_tag_role(self, id, role):
        tag = self.get_csv_tag_by_id(id)
        if tag:
            tag.role = int(role)
            self.getSession().add(tag)
            self.getSession().commit()

    def get_csv_tag_by_index(self, csv_file, index):
        for tag in csv_file.tags:
            if tag.tag_index == index:
                return tag

        return

    def get_csv_tag_instance_by_index(self, csv_file, index):

        class CsvTag:

            def __init__(self, tag):
                self.id = tag.id
                self.name = tag.name
                self.tag_index = tag.tag_index
                self.role = tag.role
                self.tag_comparison_id = tag.tag_comparison_id

        tag = self.get_csv_tag_by_index(csv_file, index)
        if tag is None:
            return
        return CsvTag(tag)

    def get_tag_alt_name(self, tag_name):
        return tag_name

    def prepare_preview(self):
        self.getSession().query(PreviewMp3File).delete()
        self.getSession().query(PreviewMp3FileTag).delete()
        self.getSession().query(Preview).delete()

    def add_preview_mp3_file(self, path):
        f = PreviewMp3File()
        f.path = path
        self.getSession().add(f)
        self.getSession().commit()
        return f

    def get_preview_mp3_files(self):
        return self.getSession().query(PreviewMp3File).all()

    def get_matching_preview_mp3_files(self, match_tag_ids, write_tag_ids):
        query = self.getSession().query(PreviewMp3File).join(PreviewMp3FileTag).filter(or_(PreviewMp3FileTag.tag_comparison_id.in_(match_tag_ids), PreviewMp3FileTag.tag_comparison_id.in_(write_tag_ids))).all()
        converted = self.convert_mp3_file_instances(query)
        return converted

    def get_matching_preview_mp3_tags(self, match_tag_ids):
        query = self.getSession().query(PreviewMp3FileTag).filter(PreviewMp3FileTag.tag_comparison_id.in_(match_tag_ids)).all()
        converted = self.convert_mp3_tag_instances(query)
        return converted

    def convert_mp3_tag_instances(self, mp3_tags):

        class Mp3Tag:

            def __init__(self):
                self.name = None
                self.id = None
                self.value = None
                self.frame = None
                self.tag_comparison_id = None

        result = []
        for t in mp3_tags:
            y = Mp3Tag()
            result.append(y)
            y.id = t.id
            y.name = t.name
            y.value = t.value
            y.frame = t.frame
            y.tag_comparison_id = t.tag_comparison_id

        return result

    def convert_mp3_file_instances(self, mp3_files):

        class Mp3File:

            def __init__(self):
                self.tags = []
                self.id = None
                self.path = None
                self.match_count = 0
                self.matched = False
                self.match_mp3_tags = {}
                self.match_csv_tags = {}
                self.write_mp3_tags = {}
                self.write_csv_tags = {}
                self.skip_mp3_tags = {}
                self.skip_csv_tags = {}

        result = []
        for f in mp3_files:
            x = Mp3File()
            result.append(x)
            x.id = f.id
            x.path = f.path
            x.tags = self.convert_mp3_tag_instances(f.tags)

        return result

    def add_preview_mp3_tag(self, mp3_file, name, value, frame, original_tag):
        comparison = self.add_comparison_tag_name(name)
        t = PreviewMp3FileTag()
        t.name = name
        t.value = value
        t.frame = frame
        t.tag_comparison_id = comparison.id
        t.tag_data = pickle.dumps(original_tag)
        mp3_file.tags.append(t)
        self.getSession().add(mp3_file)
        self.getSession().commit()
        return t

    def get_preview_mp3_tags(self):
        return self.getSession().query(PreviewMp3FileTag).all()

    def add_preview(self, mp3_file_id, tag_name, old_value, value, role, csv_entry, csv_row_index, mp3_file_tag_id=None, frame=None, ignore_if_exists=False, tag_group=0):
        """
    mp3_file_id = Column(Integer, ForeignKey('preview_mp3_file.id'))
    mp3_file = relationship("PreviewMp3File", back_populates="preview")
    tag_name = Column(String)
    old_value = Column(String)
    value = Column(String)
    role = Column(Integer)
    layer = Column(Integer)
    mp3_file_tag_id = Column(Integer, ForeignKey('preview_mp3_tag.id'))
    mp3_file_tag = relationship("PreviewMp3FileTag", back_populates="preview")
        """
        p = Preview()
        p.mp3_file_id = mp3_file_id
        p.tag_name = tag_name
        p.alt_tag_name = tag_name
        atag = self.get_alternative_tag_names(tag_name, as_string=True)
        if atag is not None:
            p.alt_tag_name = atag
        else:
            atag = self.get_tag_by_alternative_name(tag_name)
            if atag is not None:
                p.tag_name = atag.name
                p.alt_tag_name = self.get_alternative_tag_names((p.tag_name), as_string=True)
            elif ignore_if_exists:
                existing = self.getSession().query(Preview).filter(Preview.mp3_file_id == mp3_file_id, Preview.tag_name == p.tag_name, Preview.layer == csv_entry.apply_index).first()
                if existing is not None:
                    return
            import lib.util.mp3.tagmanager as tagmanager
            p.frame = tagmanager.get_id3_class_for_tag_name(p.tag_name).__name__
            previous = self.getSession().query(Preview).filter(Preview.mp3_file_id == mp3_file_id, Preview.tag_name == p.tag_name).order_by(Preview.id.desc()).first()
            if previous is not None:
                p.old_value = previous.value
                p.previous_preview_id = previous.id
            else:
                p.old_value = old_value
            p.value = value
            p.role = role
            p.layer = csv_entry.apply_index
            p.tag_group = tag_group
            p.tag_comparison_id = self.add_comparison_tag_name(p.tag_name).id
            p.csv_entry_id = csv_entry.id
            p.csv_row_index = csv_row_index
            p.mp3_file_tag_id = mp3_file_tag_id
            if role == Role.Write:
                p.selected = True
            self.getSession().add(p)
            self.getSession().commit()
            if previous is not None:
                previous.selected = False
                previous.next_preview_id = p.id
                self.getSession().add(previous)
                self.getSession().commit()

    def get_preview(self, id):
        return self.getSession().query(Preview).filter(Preview.id == id).first()

    def get_original_old_value(self, preview):
        if not isinstance(preview, Preview):
            return
        if preview.previous_preview_id is None:
            return preview.old_value
        current = preview
        while current is not None and current.previous_preview_id is not None:
            current = self.get_preview(current.previous_preview_id)

        if current is not None:
            return current.old_value
        return

    def get_preview_layers(self):
        result = []
        entries = self.getSession().query(CsvEntry).order_by(CsvEntry.apply_index).all()
        for entry in entries:
            if entry.included is True:
                result.append({'layer':entry.apply_index,  'name':(os.path.basename)(entry.path)})

        return result

    def get_tag_last_written_value(self, mp3_file_id, tag_comparison_id):
        preview = self.getSession().query(Preview).filter(Preview.mp3_file_id == mp3_file_id, Preview.tag_comparison_id == tag_comparison_id).order_by(Preview.id.desc()).first()
        if preview is None:
            return
        return preview.value

    def get_preview_headings(self, layer):
        query = self.getSession().query(Preview.alt_tag_name, Preview.role).distinct(Preview.alt_tag_name, Preview.role)
        if layer > 0:
            query = query.filter(Preview.layer <= layer)
        headings = query.all()
        result = []
        for heading in headings:
            if heading[1] == Role.Skip:
                found = False
                for other in headings:
                    if other[0] == heading[0] and other[1] == Role.Write:
                        found = True

                if not found:
                    result.append(heading)
            else:
                result.append(heading)

        return result

    def get_preview_total_rows(self, layer):
        result = self.getSession().query(PreviewMp3File).join(Preview).distinct(PreviewMp3File.id)
        if layer > 0:
            result = result.filter(Preview.layer <= layer)
        return result.count()

    def get_preview_data(self, layer, offset, limit):
        headings = self.get_preview_headings(layer)
        result = []
        files = self.getSession().query(PreviewMp3File).join(Preview).distinct(PreviewMp3File.id)
        if layer > 0:
            files = files.filter(Preview.layer <= layer)
        files = files.order_by(Preview.mp3_file_id, Preview.id).limit(limit).offset(offset).all()
        for file in files:
            row = []
            tracking = {}
            for key in headings:
                tracking[key] = None

            if layer > 0:
                preview = self.getSession().query(Preview).filter(Preview.mp3_file_id == file.id, Preview.layer <= layer).order_by(Preview.id).all()
            else:
                preview = self.getSession().query(Preview).filter(Preview.mp3_file_id == file.id).order_by(Preview.layer, Preview.id).all()
            if preview is not None:
                path = os.path.dirname(file.path)
                filename = os.path.basename(file.path)
                row.append(filename)
                selected = None
                for p in preview:
                    if p.layer == layer and p.selected:
                        selected = p

                for p in preview:
                    t = tracking.get((p.alt_tag_name, p.role))
                    if t is None:
                        t = {'count':0,  'id':p.id,  'old_id':None,  'value':p.value,  'old_value':p.old_value,  'role':p.role}
                        tracking[(p.alt_tag_name, p.role)] = t
                    if (p.selected is True or p.layer) == layer:
                        if selected is None:
                            t["old_value"] = p.old_value
                            t["value"] = p.value
                        if p.old_value is None:
                            if not (p.value is not None or p.old_value is not None and p.value is None):
                                if p.old_value != p.value:
                                    pass
                                t["count"] += 1
                                t["changed"] = True
                                continue

                for ti in tracking:
                    t = tracking[ti]
                    if t is None and ti[1] == Role.Write:
                        oi = (
                         ti[0], Role.Match)
                        other = tracking.get(oi)
                        if other is not None:
                            t = {'count':0, 
                             'id':other["id"],  'old_id':None,  'value':other["value"],  'old_value':other["old_value"],  'role':Role.Write}
                    include = True
                    if t is not None and ti[1] == Role.Skip:
                        oi = (
                         ti[0], Role.Write)
                        other = tracking.get(oi)
                        if other is not None:
                            include = False
                        if include is True:
                            row.append(t)

                result.append(row)

        return result

    def get_preview_tags_for_writing(self, on_file_listener, on_tag_listener, on_file_complete_listener):
        files = self.getSession().query(PreviewMp3File).join(Preview).filter(Preview.selected == True).order_by(PreviewMp3File.id)
        last_file = None
        for file in files:
            if not last_file is None:
                if last_file.path != file.path:
                    if last_file is not None:
                        on_file_complete_listener(file)
                    last_file = file
                    on_file_listener(file)
                tags = self.getSession().query(Preview).filter(Preview.mp3_file_id == file.id, Preview.selected == True).order_by(Preview.id)
                for tag in tags:
                    on_tag_listener(tag)

        if last_file is not None:
            on_file_complete_listener(file)

    def get_preview_possible_values(self, preview_id):
        result = []
        preview_row = self.getSession().query(Preview).filter(Preview.id == preview_id).first()
        if preview_row is not None:
            rows = self.getSession().query(Preview).filter(Preview.mp3_file_id == preview_row.mp3_file_id, Preview.tag_name == preview_row.tag_name, Preview.role == Role.Write).order_by(Preview.layer).all()
            for row in rows:
                result.append({'id':row.id,  'selected_value':row.selected,  'tag_value':row.value,  'layer':row.layer,  'csv_name':(os.path.basename)(row.csv_entry.path),  'csv_row_index':row.csv_row_index})

            return result
        return

    def set_preview_selected_value(self, old_preview_id, preview_id):
        preview_row = self.getSession().query(Preview).filter(Preview.id == old_preview_id).first()
        if preview_row is not None:
            preview_row.selected = False
            self.getSession().add(preview_row)
            self.getSession().commit()
        preview_row = self.getSession().query(Preview).filter(Preview.id == preview_id).first()
        if preview_row is not None:
            preview_row.selected = True
            self.getSession().add(preview_row)
            self.getSession().commit()

    def populate_alternative_names_table(self):
        names = configuration.tags().alternative_names.to_dict()
        for name in names:
            alt_name = names[name]
            tag = self.getSession().query(AlternativeName).filter(AlternativeName.name == name).first()
            if tag is None:
                tag = AlternativeName()
            tag.name = name
            tag.alternative_name = alt_name
            self.getSession().add(tag)
            self.getSession().commit()

    def get_alternative_tag_names(self, tag_name, as_string=False, tag_string_separator='/'):
        rows = self.getSession().query(AlternativeName).filter(AlternativeName.name == tag_name).all()
        if rows is None:
            return
        else:
            return as_string or rows
        result = None
        for idx, row in enumerate(rows):
            if idx == 0:
                result = ""
            else:
                if idx > 0:
                    result += tag_string_separator
            result += row.alternative_name

        return result

    def match_tag_alternative(self, tag_name, alternative_name):
        row = self.getSession().query(AlternativeName).filter(AlternativeName.name == tag_name, AlternativeName.alternative_name == alternative_name).first()
        return row is not None

    def get_tag_by_alternative_name(self, alternative_name):
        return self.getSession().query(AlternativeName).filter(AlternativeName.alternative_name == alternative_name).first()

    def get_tag_names(self):
        result = []
        tag_names = self.getSession().query(AlternativeName).order_by(AlternativeName.name).all()
        for tag_name in tag_names:
            result.append({'name':tag_name.name,  'alternative_name':tag_name.alternative_name})

        return result

    def add_tag_name(self, tag_name, alternative_name):
        tag = self.getSession().query(AlternativeName).filter(AlternativeName.alternative_name == alternative_name).first()
        if tag is not None:
            raise RuntimeError("Another tag with the same alternative name already exists.")
        tag = AlternativeName()
        tag.name = tag_name
        tag.alternative_name = alternative_name
        self.getSession().add(tag)
        self.getSession().commit()
        return tag

    def update_tag_name(self, old_tag_name, tag_name, old_alternative_tag_name, alternative_name):
        if old_tag_name != tag_name:
            tag = self.getSession().query(AlternativeName).filter(AlternativeName.name == tag_name).first()
            if tag is not None:
                raise RuntimeError("Another tag with the same name already exists.")
        tag = self.getSession().query(AlternativeName).filter(AlternativeName.name != old_tag_name, AlternativeName.alternative_name == alternative_name).first()
        if tag is not None:
            raise RuntimeError("Another tag with the same alternative name already exists.")
        tag = self.getSession().query(AlternativeName).filter(AlternativeName.name == old_tag_name, AlternativeName.alternative_name == old_alternative_tag_name).first()
        if tag is not None:
            tag.name = tag_name
            tag.alternative_name = alternative_name
            self.getSession().add(tag)
            self.getSession().commit()

    def remove_tag_name(self, tag_name, alternative_tag_name):
        self.getSession().query(AlternativeName).filter(AlternativeName.name == tag_name, AlternativeName.alternative_name == alternative_tag_name).delete()
        self.getSession().commit()

# okay decompiling pyz_out/lib/project/__init__.pyc
