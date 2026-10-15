"""Desktop app (Tkinter — Python's standard library, nothing to install).

Tkinter starts instantly, and the *engine* underneath (:mod:`.preview`,
:mod:`.apply`) is the same fast code the CLI uses. Slow work (scan /
preview / apply) runs on a worker thread with a progress bar, so the
window never freezes.

Tabs: Files, CSV, Preview, Apply, Setup, Help, About. The Help tab is a
full topic browser; its text lives in :mod:`.helptext` so the GUI, the
printed documentation and future front-ends all show the same words.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

# Round-2 modules are imported as modules (matching cli.py) so a single
# function on them can be replaced in tests without touching this file.
from . import __version__, consistency, coverart, fingerprints
from . import jobs as jobs_mod
from . import musicbrainz, presets
from . import sync as sync_mod
from . import undo
from .apply import apply_preview
from .consistency import check_consistency, render_consistency_csv, render_consistency_text
from .filename_tags import capture_for_file, parse_pattern
from .library_export import append_library_csv, write_library_csv
from .library_report import (
    album_completeness,
    duplicate_groups,
    render_completeness_text,
    render_csv_report,
    render_text_report,
    variant_groups,
)
from .mp3files import scan as scan_files
from .preview import (
    Cell,
    Preview,
    add_value_layer,
    build_preview,
    empty_preview,
    old_value_for,
)
from .project import Project, Role
from .tags import frame_for_tag_name

ROLE_NAMES = {int(role): role.name for role in Role}
NAME_ROLES = {role.name: int(role) for role in Role}

# The Help tab's content lives in helptext.py (one source of truth for the
# GUI, docs/HELP.md and other front-ends). Imported here for the builder.
from . import helptext  # noqa: E402

# Drag & drop is an OPTIONAL extra (the tkinterdnd2 package). It is not
# a hard dependency and is deliberately not in requirements.txt's core
# path: when the package is missing the app must start exactly as
# before, and the Files tab shows a "Paste paths…" fallback instead.
# The App root class is selected from this import below for the same
# reason — a missing package can never break startup.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_AVAILABLE = True
except Exception:  # ImportError, or a broken install: either way, no DnD
    DND_FILES = None
    TkinterDnD = None
    _DND_AVAILABLE = False

#: The window base class: tkinterdnd2's Tk when it imported cleanly
#: (its Tk is a tk.Tk subclass that knows about drop targets), else
#: plain tk.Tk.
_RootBase = TkinterDnD.Tk if _DND_AVAILABLE else tk.Tk


def _split_dnd_data(data: str) -> list[str]:
    """Split a drag-and-drop data string into its paths.

    The drop data is a Tcl-style list: paths are separated by spaces,
    and a path that itself contains spaces is wrapped in braces —
    ``"{/music/My Songs/a.mp3} /music/b.mp3"``. Parsing the braces
    explicitly (instead of a plain ``str.split``) keeps spaced paths
    intact. Pure function, so it is unit-testable without a window.
    """
    paths: list[str] = []
    index, length = 0, len(data or "")
    while index < length:
        while index < length and data[index].isspace():
            index += 1
        if index >= length:
            break
        if data[index] == "{":
            close = data.find("}", index + 1)
            if close == -1:  # unterminated brace: take the rest
                paths.append(data[index + 1:])
                break
            paths.append(data[index + 1:close])
            index = close + 1
        else:
            end = index
            while end < length and not data[end].isspace():
                end += 1
            paths.append(data[index:end])
            index = end
    return [path for path in (p.strip() for p in paths) if path]


def split_pasted_paths(text: str) -> list[str]:
    """Split clipboard text into paths: one per line.

    Blank lines are dropped and one pair of surrounding double quotes
    is stripped per line, because file managers that "copy as path"
    like to quote paths containing spaces. Pure function (see
    :func:`_split_dnd_data` for why that matters).
    """
    paths: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if len(line) >= 2 and line.startswith('"') and line.endswith('"'):
            line = line[1:-1].strip()
        if line:
            paths.append(line)
    return paths


def open_in_player(path: str) -> None:
    """Open *path* in the operating system's default player.

    Strictly read-only: the file is handed to the OS opener
    (``os.startfile`` on Windows, ``open`` on macOS, ``xdg-open``
    elsewhere, via :func:`subprocess.Popen` with no shell) and this
    program never writes to it. Kept as a small module-level function
    so the platform dispatch is unit-testable headless.
    """
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 — opening the user's own file
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class App(_RootBase):
    """Main window and all of its tabs."""

    def __init__(self, project_path: str | None = None):
        super().__init__()
        self.title("MP3 CSV Tagger")
        self.geometry("1120x720")
        self.project = Project()
        self.project_path: str | None = None
        self.preview: Preview | None = None
        self._jobs: queue.Queue = queue.Queue()
        self._busy = False
        # Round-2 state. The last scan is kept because several features
        # work from it (album grouping looks Album values up in it, the
        # completeness dialog reports over it, and inline edits create
        # cells for tags a layer never proposed using its old values).
        self.last_scanned_files: list = []
        self._scanned_by_path: dict = {}
        self._album_by_path: dict = {}
        # The last filename-pattern layer applied this session, as a
        # {"pattern", "root", "use_path"} dict — job saving includes
        # it, and the consistency dialog uses it for its defaults.
        self.last_pattern_layer: dict | None = None
        # A job whose scan is in flight (see _run_job / _on_files_scanned).
        self._pending_job = None
        # The inline preview editor widget, while one is open.
        self._preview_editor = None

        self._build_menu()
        self._build_tabs()
        if project_path:
            self._load_project(project_path)
        self.after(100, self._poll_jobs)

    # ------------------------------------------------------------------ UI
    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="New Project", command=self._new_project)
        file_menu.add_command(label="Open Project…", command=self._open_project)
        file_menu.add_command(label="Save Project", command=self._save_project)
        file_menu.add_command(label="Save Project As…", command=self._save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu.add_cascade(label="Project", menu=file_menu)
        run_menu = tk.Menu(menu, tearoff=0)
        run_menu.add_command(label="Build Preview", command=self._start_preview)
        run_menu.add_command(label="Apply Tags", command=self._start_apply)
        menu.add_cascade(label="Run", menu=run_menu)
        self.config(menu=menu)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=4)
        for label, command in (
            ("New", self._new_project),
            ("Open", self._open_project),
            ("Save", self._save_project),
            ("Build Preview", self._start_preview),
            ("Apply", self._start_apply),
        ):
            ttk.Button(bar, text=label, command=command).pack(side="left", padx=2)
        self.status = ttk.Label(bar, text="Ready")
        self.status.pack(side="right", padx=6)
        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", padx=6)

    def _build_tabs(self) -> None:
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=6, pady=6)
        self._build_files_tab()
        self._build_csv_tab()
        self._build_preview_tab()
        self._build_apply_tab()
        self._build_setup_tab()
        self._build_help_tab()
        self._build_text_tab(
            "About",
            "MP3 CSV Tagger\n\n"
            f"Version {__version__}\n\n"
            "Bulk-edit MP3 ID3 tags from CSV files: match rows to files, "
            "write new tag values, preview everything first, and keep a "
            "change log of every edit.\n\n"
            "Built with Python and the mutagen library. Free and open "
            "source under the MIT license — see the Help tab for the "
            "full guide.",
        )

    def _build_files_tab(self) -> None:
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="Files")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="Add Folder", command=self._add_folder).pack(side="left", padx=2)
        ttk.Button(bar, text="Add File", command=self._add_file).pack(side="left", padx=2)
        ttk.Button(bar, text="Remove Selected", command=self._remove_file).pack(side="left", padx=2)
        self.files_count = ttk.Label(bar, text="")
        self.files_count.pack(side="right")
        bar2 = ttk.Frame(tab)
        bar2.pack(fill="x", pady=(0, 4))
        ttk.Button(bar2, text="Export library to CSV…", command=self._export_library).pack(side="left", padx=2)
        ttk.Button(bar2, text="Tags from filename/path…", command=self._tags_from_filename).pack(side="left", padx=2)
        ttk.Button(bar2, text="Library report…", command=self._library_report).pack(side="left", padx=2)
        ttk.Button(bar2, text="Sync tags…", command=self._sync_tags_dialog).pack(side="left", padx=2)
        ttk.Button(bar2, text="Consistency check…", command=self._consistency_check).pack(side="left", padx=2)
        # Jobs row: a saved job is a whole run (paths + CSV layers +
        # pattern layers) under one name — see _save_current_as_job,
        # _run_job and _delete_job.
        bar3 = ttk.Frame(tab)
        bar3.pack(fill="x", pady=(0, 4))
        ttk.Label(bar3, text="Job:").pack(side="left", padx=(2, 0))
        self.job_combo = ttk.Combobox(bar3, state="readonly", width=28)
        self.job_combo.pack(side="left", padx=2)
        ttk.Button(bar3, text="Save current as job…", command=self._save_current_as_job).pack(side="left", padx=2)
        ttk.Button(bar3, text="Run job", command=self._run_job).pack(side="left", padx=2)
        ttk.Button(bar3, text="Delete job", command=self._delete_job).pack(side="left", padx=2)
        self._refresh_jobs()
        self.files_list = tk.Listbox(tab, selectmode="extended")
        self.files_list.pack(fill="both", expand=True)
        # Drag & drop when tkinterdnd2 is available (the list and the
        # window itself both accept drops); the "Paste paths…" button
        # is the fallback when it is not, so the feature never simply
        # disappears. The Setup tab reports which mode is active.
        if _DND_AVAILABLE:
            for widget in (self, self.files_list):
                try:
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind("<<Drop>>", self._on_drop)
                except Exception:
                    pass  # a failed registration must not break startup
        else:
            ttk.Button(
                tab, text="Paste paths…", command=self._paste_paths
            ).pack(anchor="w", pady=(4, 0))

    def _build_csv_tab(self) -> None:
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="CSV Files")
        left = ttk.Frame(tab)
        left.pack(side="left", fill="y", padx=(0, 6))
        ttk.Button(left, text="Add CSV File", command=self._add_csv).pack(fill="x", pady=2)
        self.csv_list = tk.Listbox(left, width=42, height=12)
        self.csv_list.pack(fill="y", expand=True)
        self.csv_list.bind("<<ListboxSelect>>", lambda _e: self._show_csv_columns())
        ttk.Button(left, text="Move Up", command=lambda: self._move_csv(-1)).pack(fill="x", pady=2)
        ttk.Button(left, text="Move Down", command=lambda: self._move_csv(1)).pack(fill="x", pady=2)
        ttk.Button(left, text="Remove", command=self._remove_csv).pack(fill="x", pady=2)
        self.csv_included = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            left, text="Included in run", variable=self.csv_included,
            command=self._toggle_csv_included,
        ).pack(fill="x", pady=2)

        right = ttk.Frame(tab)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="Columns — double-click a role to change it:").pack(anchor="w")
        self.csv_columns = ttk.Treeview(right, columns=("column", "role"), show="headings")
        self.csv_columns.heading("column", text="CSV Column (tag name)")
        self.csv_columns.heading("role", text="Role")
        self.csv_columns.pack(fill="both", expand=True)
        self.csv_columns.bind("<Double-1>", self._cycle_role)
        bar = ttk.Frame(right)
        bar.pack(fill="x", pady=4)
        ttk.Label(bar, text="Set selected column to:").pack(side="left")
        for name in ("Match", "Write", "Skip"):
            ttk.Button(bar, text=name, command=lambda n=name: self._set_role(n)).pack(side="left", padx=2)
        ttk.Button(bar, text="Refresh columns from file", command=self._refresh_csv_columns).pack(side="left", padx=8)
        bar2 = ttk.Frame(right)
        bar2.pack(fill="x", pady=(0, 4))
        ttk.Label(bar2, text="Role preset:").pack(side="left")
        self.preset_combo = ttk.Combobox(bar2, state="readonly", width=34)
        self.preset_combo.pack(side="left", padx=2)
        ttk.Button(bar2, text="Apply preset", command=self._apply_preset).pack(side="left", padx=2)
        ttk.Button(bar2, text="Save roles as preset…", command=self._save_preset).pack(side="left", padx=2)
        self._refresh_presets()

    def _build_preview_tab(self) -> None:
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="Preview")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="Build Preview", command=self._start_preview).pack(side="left", padx=2)
        ttk.Button(bar, text="Choose value…", command=self._choose_value).pack(side="left", padx=2)
        ttk.Button(bar, text="Export preview CSV…", command=self._export_preview).pack(side="left", padx=2)
        ttk.Button(bar, text="Fill missing tags (MusicBrainz)…", command=self._lookup_musicbrainz).pack(side="left", padx=2)
        self.preview_stats = ttk.Label(bar, text="No preview yet")
        self.preview_stats.pack(side="right")
        bar2 = ttk.Frame(tab)
        bar2.pack(fill="x", pady=(0, 4))
        ttk.Button(bar2, text="Edit value…", command=self._edit_value).pack(side="left", padx=2)
        ttk.Button(bar2, text="Revert edit", command=self._revert_edit).pack(side="left", padx=2)
        ttk.Button(bar2, text="Open in player", command=self._open_selected_in_player).pack(side="left", padx=2)
        ttk.Button(bar2, text="Completeness…", command=self._completeness_dialog).pack(side="left", padx=2)
        # Grouping is a display choice only: the same preview rows are
        # rendered under one parent row per album (see _refresh_preview).
        self.group_by_album = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar2, text="Group by album", variable=self.group_by_album,
            command=self._refresh_preview,
        ).pack(side="left", padx=8)
        self.preview_tree = ttk.Treeview(tab, show="headings")
        self.preview_tree.pack(fill="both", expand=True)
        # Double-clicking a cell opens the inline editor on it.
        self.preview_tree.bind("<Double-1>", self._on_preview_double_click)

    def _build_apply_tab(self) -> None:
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="Apply")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="Apply Tags", command=self._start_apply).pack(side="left", padx=2)
        ttk.Button(bar, text="Undo a run…", command=self._undo_run).pack(side="left", padx=2)
        ttk.Label(bar, text="Log Folder").pack(side="left", padx=(12, 2))
        self.log_folder = tk.StringVar(value=self.project.apply_log_folder)
        ttk.Entry(bar, textvariable=self.log_folder, width=48).pack(side="left")
        ttk.Button(bar, text="Browse", command=self._browse_log_folder).pack(side="left", padx=2)
        self.apply_output = tk.Text(tab, wrap="word")
        self.apply_output.pack(fill="both", expand=True)

    def _build_setup_tab(self) -> None:
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="Setup")
        ttk.Label(tab, text="Tag names — how ID3 frames are shown and matched:").pack(anchor="w", pady=4)
        self.names_tree = ttk.Treeview(tab, columns=("frame", "name"), show="headings")
        self.names_tree.heading("frame", text="ID3 Frame")
        self.names_tree.heading("name", text="Friendly / Alternative Name")
        self.names_tree.pack(fill="both", expand=True)
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="Add", command=self._add_name).pack(side="left", padx=2)
        ttk.Button(bar, text="Edit", command=self._edit_name).pack(side="left", padx=2)
        ttk.Button(bar, text="Remove", command=self._remove_name).pack(side="left", padx=2)
        ttk.Button(bar, text="Reset to defaults", command=self._reset_names).pack(side="left", padx=2)
        self._refresh_names()
        # Fingerprints & AcoustID: fpcalc is an external tool (its
        # status is reported, never assumed), and the AcoustID key is
        # the user's own — it lives in the local settings file and is
        # only ever sent to AcoustID when a lookup button is pressed.
        ttk.Separator(tab).pack(fill="x", pady=8)
        ttk.Label(tab, text="Fingerprints & AcoustID:").pack(anchor="w")
        fpcalc = fingerprints.fpcalc_path()
        self.fpcalc_label = ttk.Label(
            tab, text=f"fpcalc: {fpcalc if fpcalc else 'not detected'}"
        )
        self.fpcalc_label.pack(anchor="w", pady=(2, 0))
        ttk.Label(
            tab,
            text="Install fpcalc — Linux: apt install libchromaprint-tools · "
                 "macOS: brew install chromaprint · Windows: download fpcalc "
                 "from acoustid.org",
            wraplength=980, justify="left",
        ).pack(anchor="w")
        ttk.Label(
            tab,
            text="Drag & drop: "
                 + ("active (tkinterdnd2) — drop files or folders onto the Files tab"
                    if _DND_AVAILABLE else
                    "not available (tkinterdnd2 not installed) — use “Paste paths…” "
                    "on the Files tab instead"),
        ).pack(anchor="w", pady=(2, 0))
        key_bar = ttk.Frame(tab)
        key_bar.pack(fill="x", pady=6)
        ttk.Label(key_bar, text="AcoustID API key:").pack(side="left")
        self.acoustid_key_var = tk.StringVar(value=fingerprints.acoustid_api_key())
        ttk.Entry(key_bar, textvariable=self.acoustid_key_var, width=44).pack(side="left", padx=4)
        ttk.Button(key_bar, text="Save key", command=self._save_acoustid_key).pack(side="left", padx=2)
        ttk.Label(
            tab,
            text="Only used when you press an AcoustID button; stored locally "
                 "in ~/.mp3csvtagger/settings.json",
            wraplength=980, justify="left",
        ).pack(anchor="w")

    def _save_acoustid_key(self) -> None:
        """Save the Setup tab's AcoustID key into the settings file.

        The existing settings are loaded and merged (not replaced), so
        anything else stored there survives; the save itself goes
        through :func:`fingerprints.save_settings`.
        """
        settings = fingerprints.load_settings()
        settings["acoustid_api_key"] = self.acoustid_key_var.get().strip()
        try:
            path = fingerprints.save_settings(settings)
        except Exception as exc:
            messagebox.showerror("AcoustID API key", str(exc))
            return
        self.status.config(text=f"AcoustID API key saved to {path}")

    def _build_help_tab(self) -> None:
        """The Help tab: a topic browser over helptext.TOPICS.

        The text comes from :mod:`.helptext` (never written here) so the
        GUI, docs/HELP.md and other front-ends cannot drift apart.
        """
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="Help")
        self.help_topics = tk.Listbox(tab, width=34)
        self.help_topics.pack(side="left", fill="y")
        for title in helptext.topic_titles():
            self.help_topics.insert("end", title)
        self.help_topics.bind("<<ListboxSelect>>", lambda _e: self._show_help_topic())
        self.help_text = tk.Text(tab, wrap="word")
        self.help_text.pack(side="left", fill="both", expand=True)
        self.help_topics.selection_set(0)
        self._show_help_topic()

    def _show_help_topic(self) -> None:
        selection = self.help_topics.curselection()
        if not selection:
            return
        title = self.help_topics.get(selection[0])
        self.help_text.config(state="normal")
        self.help_text.delete("1.0", "end")
        self.help_text.insert("1.0", helptext.topic_body(title))
        self.help_text.config(state="disabled")

    def _build_text_tab(self, title: str, text: str) -> None:
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text=title)
        widget = tk.Text(tab, wrap="word")
        widget.insert("1.0", text)
        widget.config(state="disabled")
        widget.pack(fill="both", expand=True)

    # -------------------------------------------------------------- project
    def _new_project(self) -> None:
        self.project = Project()
        self.project_path = None
        self.preview = None
        self._refresh_all()

    def _open_project(self) -> None:
        path = filedialog.askopenfilename(
            title="Open project", filetypes=[("MP3 Tagger project", "*.json"), ("All files", "*.*")]
        )
        if path:
            self._load_project(path)

    def _load_project(self, path: str) -> None:
        try:
            self.project = Project.load(path)
            self.project_path = path
            self.preview = None
            self._refresh_all()
            self.status.config(text=f"Opened {path}")
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))

    def _save_project(self) -> None:
        if not self.project_path:
            self._save_project_as()
            return
        self._sync_log_folder()
        self.project.save(self.project_path)
        self.status.config(text=f"Saved {self.project_path}")

    def _save_project_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save project", defaultextension=".mp3p.json",
            filetypes=[("MP3 Tagger project", "*.json")],
        )
        if path:
            self.project_path = path
            self._save_project()

    def _sync_log_folder(self) -> None:
        folder = self.log_folder.get().strip()
        if folder:
            self.project.apply_log_folder = folder

    def _refresh_all(self) -> None:
        self.log_folder.set(self.project.apply_log_folder)
        self.files_list.delete(0, "end")
        for path in self.project.mp3_paths:
            self.files_list.insert("end", path)
        self.files_count.config(text=f"{len(self.project.mp3_paths)} path(s)")
        self.csv_list.delete(0, "end")
        for entry in self.project.csv_entries:
            mark = "" if entry.included else " (excluded)"
            self.csv_list.insert("end", entry.filename + mark)
        self._show_csv_columns()
        self._refresh_names()
        self._refresh_presets()
        self._refresh_jobs()
        self._refresh_preview()

    def _note_scanned(self, files) -> None:
        """Remember a fresh scan: the GUI's lookup maps come from it.

        The album-grouping key and the old values for brand-new
        preview cells both read from these maps (a preview row alone
        does not carry its file's full tag set).
        """
        self.last_scanned_files = list(files)
        self._scanned_by_path = {mp3.path: mp3 for mp3 in files}
        self._album_by_path = {
            mp3.path: mp3.value_for("Album", "TALB") for mp3 in files
        }

    # ---------------------------------------------------------------- files
    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select a folder to include")
        if folder:
            self.project.add_mp3_path(folder)
            self._refresh_all()

    def _add_file(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select MP3 file", filetypes=[("MP3 Files", "*.mp3")]
        )
        for path in paths or []:
            self.project.add_mp3_path(path)
        if paths:
            self._refresh_all()

    def _remove_file(self) -> None:
        for index in reversed(self.files_list.curselection()):
            self.project.remove_mp3_path(self.files_list.get(index))
        self._refresh_all()

    # ------------------------------------------------------------------ csv
    def _selected_entry(self):
        selection = self.csv_list.curselection()
        if not selection:
            return None
        index = selection[0]
        if 0 <= index < len(self.project.csv_entries):
            return self.project.csv_entries[index]
        return None

    def _add_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select CSV file", filetypes=[("CSV Files", "*.csv")]
        )
        if not path:
            return
        try:
            self.project.add_csv_file(path)
        except Exception as exc:
            messagebox.showerror("Unable to add CSV", str(exc))
            return
        self._refresh_all()

    def _remove_csv(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            self.project.csv_entries.remove(entry)
            self._refresh_all()

    def _move_csv(self, direction: int) -> None:
        entry = self._selected_entry()
        if entry is not None:
            self.project.move_csv_entry(entry, direction)
            self._refresh_all()
            self.csv_list.selection_set(self.project.csv_entries.index(entry))

    def _toggle_csv_included(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            entry.included = bool(self.csv_included.get())
            self._refresh_all()

    def _show_csv_columns(self) -> None:
        entry = self._selected_entry()
        self.csv_columns.delete(*self.csv_columns.get_children())
        if entry is None:
            return
        self.csv_included.set(entry.included)
        for tag in entry.tags:
            self.csv_columns.insert("", "end", values=(tag.name, ROLE_NAMES.get(int(tag.role), "Skip")))

    def _selected_tag(self, entry):
        selection = self.csv_columns.selection()
        if not selection or entry is None:
            return None
        index = self.csv_columns.index(selection[0])
        return entry.tags[index] if 0 <= index < len(entry.tags) else None

    def _set_role(self, role_name: str) -> None:
        entry = self._selected_entry()
        tag = self._selected_tag(entry)
        if tag is not None:
            tag.role = NAME_ROLES[role_name]
            self._show_csv_columns()

    def _cycle_role(self, _event=None) -> None:
        entry = self._selected_entry()
        tag = self._selected_tag(entry)
        if tag is not None:
            tag.role = (int(tag.role) % 3) + 1  # Match -> Write -> Skip -> Match
            self._show_csv_columns()

    def _refresh_csv_columns(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            try:
                entry.refresh_tags()
            except Exception as exc:
                messagebox.showerror("Refresh failed", str(exc))
            self._show_csv_columns()

    # -------------------------------------------------------------- preview
    def _preview_cell_text(self, cell) -> str:
        """The tree display text for one preview cell.

        Cover-art values are image paths; show the friendly "[cover
        image: …]" / "[remove cover art]" form. A manual edit is
        marked with a "✎ " prefix and a "(manual edit)" suffix naming
        its source, so a hand-typed value is always recognisable.
        """
        text = (
            coverart.cover_display(cell.value)
            if cell.frame == "APIC"
            else cell.value
        )
        if cell.manual_candidate is not None:
            text = f"✎ {text}  (manual edit)"
        elif cell.has_multiple:
            text += f"  ({len(cell.candidates)} values)"
        if cell.changed:
            text = f"{cell.old_value}  →  {text}" if cell.old_value else text
        return text

    def _album_group_key(self, row) -> str:
        """The album a preview row groups under (see _refresh_preview).

        The row's Album cell wins when the preview has one (its
        selected value is the album the file will end up with);
        otherwise the Album tag from the last scan's lookup map;
        otherwise the file's parent folder name — an untagged file
        still groups with its folder-mates.
        """
        cell = row.cells.get("Album")
        if cell is not None and cell.value:
            return cell.value
        album = self._album_by_path.get(row.path, "")
        if album:
            return album
        return os.path.basename(os.path.dirname(row.path)) or "(no album)"

    def _refresh_preview(self) -> None:
        # A refresh replaces every row, so any open inline editor —
        # which overlays a cell of the old rendering — is finished.
        self._close_preview_editor()
        tree = self.preview_tree
        tree.delete(*tree.get_children())
        if self.preview is None:
            tree["columns"] = ("file",)
            tree.heading("file", text="File")
            self.preview_stats.config(text="No preview yet")
            return
        columns = ["file"] + list(self.preview.write_tags)
        tree["columns"] = columns
        tree.heading("file", text="File")
        for name in self.preview.write_tags:
            tree.heading(name, text=name)

        def row_values(row) -> list[str]:
            values = [row.filename]
            for name in self.preview.write_tags:
                cell = row.cells.get(name)
                values.append("" if cell is None else self._preview_cell_text(cell))
            return values

        group_var = getattr(self, "group_by_album", None)
        grouped = bool(group_var.get()) if group_var is not None else False
        if grouped:
            # One parent row per album (in first-seen order), the
            # files as its children. File rows keep iid=row.path so
            # every selection-based feature works unchanged; group
            # rows get iid "group:<key>" and are skipped by
            # row_for_path lookups (Preview has no such path).
            parents: dict[str, str] = {}
            counts: dict[str, int] = {}
            for row in self.preview.rows:
                key = self._album_group_key(row)
                counts[key] = counts.get(key, 0) + 1
                if key not in parents:
                    parents[key] = tree.insert(
                        "", "end", iid=f"group:{key}",
                        values=[key] + [""] * len(self.preview.write_tags),
                    )
            for key, iid in parents.items():
                tree.item(iid, values=[f"{key}  ({counts[key]} file(s))"]
                          + [""] * len(self.preview.write_tags))
            for row in self.preview.rows:
                tree.insert(
                    parents[self._album_group_key(row)], "end",
                    iid=row.path, values=row_values(row),
                )
        else:
            for row in self.preview.rows:
                tree.insert("", "end", iid=row.path, values=row_values(row))
        self.preview_stats.config(
            text=(
                f"Scanned {self.preview.files_scanned} · matched "
                f"{self.preview.files_matched} · {self.preview.total_changes} change(s)"
            )
        )

    # ------------------------------------------------- preview inline edits
    def _selected_preview_row(self):
        """The preview row for the tree selection, or None (with a hint)."""
        if self.preview is None:
            messagebox.showinfo("Preview", "Build a preview first.")
            return None
        selection = self.preview_tree.selection()
        if not selection:
            messagebox.showinfo("Preview", "Select a file row first.")
            return None
        row = self.preview.row_for_path(selection[0])
        if row is None:  # a "group:<album>" parent row, not a file
            messagebox.showinfo("Preview", "Select a file row, not an album group.")
            return None
        return row

    def _pick_cell(self, row, *, manual_only: bool = False, title: str = "Choose a tag"):
        """Ask which of *row*'s tags to act on; return its Cell or None.

        Lists every write tag of the preview (tags with no cell yet
        show blank — an edit can create the cell). With
        *manual_only*, only cells carrying a manual edit are listed.
        """
        names = []
        for name in self.preview.write_tags:
            cell = row.cells.get(name)
            if manual_only and (cell is None or cell.manual_candidate is None):
                continue
            names.append(name)
        if not names:
            return None
        if len(names) == 1 and manual_only:
            return row.cells[names[0]]
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry("560x300")
        ttk.Label(dialog, text=f"{row.filename} — pick a tag:").pack(
            anchor="w", padx=8, pady=6
        )
        listbox = tk.Listbox(dialog)
        listbox.pack(fill="both", expand=True, padx=8)
        for name in names:
            cell = row.cells.get(name)
            shown = "" if cell is None else (
                coverart.cover_display(cell.value) if cell.frame == "APIC"
                else cell.value
            )
            listbox.insert("end", f"{name}: {shown!r}")
        listbox.selection_set(0)
        result: dict = {}

        def _ok() -> None:
            chosen = listbox.curselection()
            if chosen:
                result["name"] = names[chosen[0]]
            dialog.destroy()

        ttk.Button(dialog, text="OK", command=_ok).pack(side="left", padx=6, pady=6)
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack(side="left", pady=6)
        dialog.grab_set()
        self.wait_window(dialog)
        if "name" not in result:
            return None
        return self._cell_for_edit(row, result["name"])

    def _cell_for_edit(self, row, tag_name: str):
        """The row's cell for *tag_name*, creating it when there is none.

        A tag no layer proposed has no cell; an inline edit still
        needs one, with the file's current value as its old value —
        which comes from the last scan's lookup map. Returns None
        (after explaining) when the file was never scanned here.
        """
        cell = row.cells.get(tag_name)
        if cell is not None:
            return cell
        mp3 = self._scanned_by_path.get(row.path)
        if mp3 is None:
            messagebox.showinfo(
                "Edit value",
                "That tag has no proposed value for this file, and the "
                "file was not part of the last scan, so its current "
                "value is unknown. Rebuild the preview first.",
            )
            return None
        frame = frame_for_tag_name(tag_name, self.project.alternative_names)
        cell = Cell(
            tag_name=tag_name, frame=frame,
            old_value=old_value_for(mp3, tag_name, frame),
        )
        row.cells[tag_name] = cell
        if tag_name not in self.preview.write_tags:
            self.preview.write_tags.append(tag_name)
        return cell

    def _edit_value(self) -> None:
        """The "Edit value…" button: pick a tag, then edit it inline."""
        row = self._selected_preview_row()
        if row is None:
            return
        cell = self._pick_cell(row, title="Edit value")
        if cell is not None:
            self._start_inline_edit(row.path, cell.tag_name)

    def _on_preview_double_click(self, event) -> None:
        """Double-click on a preview cell opens the inline editor on it.

        The row comes from the tree selection (identify_row agrees
        with it for a double-click) and the column from
        ``identify_column`` — column #1 is the file name, which is
        never editable; write tags start at #2.
        """
        if self.preview is None:
            return
        iid = self.preview_tree.identify_row(event.y)
        column_id = self.preview_tree.identify_column(event.x)
        if not iid or iid.startswith("group:"):
            return
        try:
            column_index = int(column_id.lstrip("#")) - 1
        except ValueError:
            return
        columns = ["file"] + list(self.preview.write_tags)
        if column_index <= 0 or column_index >= len(columns):
            return
        self._start_inline_edit(iid, columns[column_index])

    def _close_preview_editor(self) -> None:
        """Destroy the inline editor overlay, if one is open."""
        if self._preview_editor is not None:
            try:
                self._preview_editor.destroy()
            except tk.TclError:
                pass
            self._preview_editor = None

    def _start_inline_edit(self, iid: str, tag_name: str) -> None:
        """Open the editor for one cell of one preview row.

        Normally an Entry overlaid exactly on the cell (its bbox);
        when the cell is not visible (scrolled away, or its album
        group is collapsed) or the cell already carries a manual edit
        — which deserves the fuller dialog with its Revert button —
        the dialog editor is used instead.
        """
        if self.preview is None:
            return
        row = self.preview.row_for_path(iid)
        if row is None:
            return
        cell = self._cell_for_edit(row, tag_name)
        if cell is None:
            return
        if cell.manual_candidate is not None:
            self._edit_cell_dialog(row, cell)
            return
        columns = ["file"] + list(self.preview.write_tags)
        bbox = self.preview_tree.bbox(iid, f"#{columns.index(tag_name) + 1}")
        if not bbox:
            self._edit_cell_dialog(row, cell)
            return
        self._close_preview_editor()
        x, y, width, height = bbox
        entry = tk.Entry(self.preview_tree)
        # The raw value, not the display text: for cover art that is
        # the image path (typing a path is how a cover is set here,
        # exactly like a cover value from a CSV; blank removes art).
        entry.insert(0, cell.value)
        entry.place(x=x, y=y, width=max(width, 140), height=height)
        entry.focus_set()
        entry.select_range(0, "end")
        self._preview_editor = entry
        state = {"done": False}

        def finish(commit: bool) -> None:
            if state["done"]:
                return
            state["done"] = True
            text = entry.get()
            self._close_preview_editor()
            if commit:
                self._commit_manual_edit(row, cell, text)

        entry.bind("<Return>", lambda _e: finish(True))
        entry.bind("<Escape>", lambda _e: finish(False))
        entry.bind("<FocusOut>", lambda _e: finish(False))

    def _edit_cell_dialog(self, row, cell) -> None:
        """Dialog editor for a cell: an Entry plus, when the cell has
        a manual edit, a "Revert to …" button that clears it back to
        the value the layers had selected."""
        dialog = tk.Toplevel(self)
        dialog.title(f"Edit {cell.tag_name}")
        dialog.geometry("520x170")
        ttk.Label(dialog, text=f"{row.filename} — {cell.tag_name}").pack(
            anchor="w", padx=10, pady=(10, 2)
        )
        ttk.Label(
            dialog,
            text="Current value in the file: "
                 + (cell.old_value if cell.old_value else "(empty)"),
        ).pack(anchor="w", padx=10)
        var = tk.StringVar(value=cell.value)
        entry = ttk.Entry(dialog, textvariable=var, width=64)
        entry.pack(fill="x", padx=10, pady=8)
        entry.focus_set()
        entry.select_range(0, "end")
        bar = ttk.Frame(dialog)
        bar.pack(fill="x", padx=10, pady=4)

        def _ok() -> None:
            dialog.destroy()
            self._commit_manual_edit(row, cell, var.get())

        ttk.Button(bar, text="OK", command=_ok).pack(side="left", padx=2)
        if cell.manual_candidate is not None:
            # The value a revert falls back to: the last non-manual
            # candidate, or the file's current value when there is none.
            others = [c for c in cell.candidates if not c.manual]
            fallback = others[-1].value if others else cell.old_value

            def _revert() -> None:
                dialog.destroy()
                cell.clear_manual_edit()
                self._refresh_preview()
                self.status.config(
                    text=f"Reverted {row.filename} {cell.tag_name} to {fallback!r}"
                )

            ttk.Button(
                bar, text=f"Revert to {fallback!r}", command=_revert
            ).pack(side="left", padx=2)
        ttk.Button(bar, text="Cancel", command=dialog.destroy).pack(side="left", padx=2)
        entry.bind("<Return>", lambda _e: _ok())

    def _commit_manual_edit(self, row, cell, text: str) -> None:
        """Record a typed value as the cell's manual edit and re-render.

        The edit is an ordinary selected candidate from here on (see
        :meth:`preview.Cell.set_manual_edit`): Apply writes it, the
        change log records its source as "manual edit", and the
        snapshot undo covers it. For a Cover Art cell the text is an
        image path, like any cover value; a blank value removes art.
        """
        cell.set_manual_edit(text)
        self._refresh_preview()
        self.status.config(
            text=f"Manual edit: {row.filename} {cell.tag_name} → {text!r} "
                 "(written when you Apply)"
        )

    def _revert_edit(self) -> None:
        """The "Revert edit" button: clear the selected row's manual edit."""
        row = self._selected_preview_row()
        if row is None:
            return
        manual = [c for c in row.cells.values() if c.manual_candidate is not None]
        if not manual:
            messagebox.showinfo("Revert edit", "That file has no manual edit.")
            return
        cell = self._pick_cell(row, manual_only=True, title="Revert edit")
        if cell is None:
            return
        cell.clear_manual_edit()
        self._refresh_preview()
        self.status.config(
            text=f"Reverted {row.filename} {cell.tag_name} to {cell.value!r}"
        )

    def _open_selected_in_player(self) -> None:
        """Open the selected file in the OS default player (read-only)."""
        row = self._selected_preview_row()
        if row is None:
            return
        try:
            open_in_player(row.path)
        except Exception as exc:
            messagebox.showerror("Open in player", str(exc))
            return
        self.status.config(text=f"Opened {row.filename} in the default player")

    def _completeness_dialog(self) -> None:
        """Per-album tag completeness over the last scanned files."""
        files = self.last_scanned_files
        if not files:
            messagebox.showinfo(
                "Completeness",
                "Nothing scanned yet — build a preview or use a Files "
                "tab tool first, then try again.",
            )
            return
        dialog = tk.Toplevel(self)
        dialog.title("Album completeness")
        dialog.geometry("720x520")
        text = tk.Text(dialog, wrap="word")
        text.pack(fill="both", expand=True, padx=8, pady=6)
        content = render_completeness_text(
            album_completeness(files, self.project.alternative_names)
        )
        text.insert("1.0", content)
        text.config(state="disabled")
        bar = ttk.Frame(dialog)
        bar.pack(fill="x", padx=8, pady=6)

        def _save() -> None:
            path = filedialog.asksaveasfilename(
                title="Save completeness report", defaultextension=".txt",
                filetypes=[("Text files", "*.txt")],
            )
            if path:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(content)
                self.status.config(text=f"Completeness report saved to {path}")

        ttk.Button(bar, text="Save…", command=_save).pack(side="left", padx=2)
        ttk.Button(bar, text="Close", command=dialog.destroy).pack(side="left", padx=2)

    def _choose_value(self) -> None:
        if self.preview is None:
            return
        selection = self.preview_tree.selection()
        if not selection:
            messagebox.showinfo("Choose value", "Select a file row first.")
            return
        row = self.preview.row_for_path(selection[0])
        if row is None:
            return
        options = []
        for tag_name, cell in row.cells.items():
            if cell.has_multiple:
                for index, candidate in enumerate(cell.candidates):
                    options.append((tag_name, index, candidate))
        if not options:
            messagebox.showinfo("Choose value", "That file has no tag with multiple values.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Select a value")
        dialog.geometry("640x320")
        listbox = tk.Listbox(dialog)
        listbox.pack(fill="both", expand=True)
        for tag_name, _index, candidate in options:
            marker = ""
            cell = row.cells[tag_name]
            if cell.candidates.index(candidate) == cell.selected:
                marker = "  (selected)"
            listbox.insert(
                "end",
                f"{tag_name}: {candidate.value!r}  —  {candidate.csv_name} row "
                f"{candidate.csv_row_index}{marker}",
            )

        def _ok() -> None:
            chosen = listbox.curselection()
            if chosen:
                tag_name, index, _candidate = options[chosen[0]]
                row.cells[tag_name].selected = index
            dialog.destroy()
            self._refresh_preview()

        ttk.Button(dialog, text="OK", command=_ok).pack(side="left", padx=6, pady=6)
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack(side="left", pady=6)

    def _export_preview(self) -> None:
        if self.preview is None:
            return
        path = filedialog.asksaveasfilename(
            title="Export preview", defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if path:
            from .apply import write_preview_csv

            write_preview_csv(self.preview, path)
            self.status.config(text=f"Preview exported to {path}")

    # ------------------------------------------------------- v1.2 features
    def _refresh_presets(self) -> None:
        if not hasattr(self, "preset_combo"):
            return
        names = [preset.name for preset in presets.list_presets()]
        self.preset_combo["values"] = names
        if names and not self.preset_combo.get():
            self.preset_combo.set(names[0])

    def _apply_preset(self) -> None:
        entry = self._selected_entry()
        name = self.preset_combo.get()
        if entry is None or not name:
            messagebox.showinfo("Role preset", "Select a CSV file and a preset first.")
            return
        try:
            preset = presets.load_preset(name)
        except Exception as exc:
            messagebox.showerror("Role preset", str(exc))
            return
        changed = presets.apply_preset(entry, preset)
        self._show_csv_columns()
        self.status.config(text=f"Preset {preset.name!r} set {changed} column(s)")

    def _save_preset(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            messagebox.showinfo("Role preset", "Select a CSV file first.")
            return
        name = simpledialog.askstring("Save role preset", "Preset name:")
        if not name:
            return
        preset = presets.Preset(
            name=name.strip(),
            roles={tag.name: int(tag.role) for tag in entry.tags},
        )
        try:
            path = presets.save_preset(preset)
        except Exception as exc:
            messagebox.showerror("Role preset", str(exc))
            return
        self._refresh_presets()
        self.preset_combo.set(preset.name)
        self.status.config(text=f"Preset saved to {path}")

    def _scan_for(self, purpose: str) -> None:
        """Scan the project's paths on a worker thread for a Files tool."""
        if self._busy:
            return
        if not self.project.mp3_paths:
            messagebox.showinfo("Files", "Add some MP3 files or folders first.")
            return
        self._busy = True
        self.status.config(text="Scanning…")
        paths = list(self.project.mp3_paths)

        def work() -> None:
            """Worker-thread body: does the slow work, posts results to the job queue."""
            try:
                files = scan_files(
                    paths,
                    progress=lambda d, t, _p: self._jobs.put(("progress", (d, t))),
                )
                self._jobs.put(("files_scanned", (purpose, files)))
            except Exception as exc:
                self._jobs.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_files_scanned(self, purpose: str, files) -> None:
        # Every scan refreshes the lookup maps the round-2 features
        # read (album grouping, completeness, inline-edit old values).
        self._note_scanned(files)
        if purpose.startswith("export:"):
            out_path = purpose[len("export:"):]
            columns = write_library_csv(files, out_path)
            self.status.config(
                text=f"Exported {len(files)} file(s), {len(columns)} columns to {out_path}"
            )
        elif purpose.startswith("append:"):
            out_path = purpose[len("append:"):]
            try:
                summary = append_library_csv(files, out_path)
            except Exception as exc:  # missing header, no key column, ...
                messagebox.showerror("Append to CSV failed", str(exc))
                return
            lines = [
                f"Scanned {summary.files_scanned} file(s) into {out_path}:",
                f"Rows added: {summary.rows_added}",
                f"Rows updated: {summary.rows_updated}",
                f"Rows kept: {summary.rows_kept}",
            ]
            if summary.columns_added:
                lines.append(
                    f"Columns added: {', '.join(summary.columns_added)}"
                )
            if summary.warning:
                lines.append(f"Warning: {summary.warning}")
            messagebox.showinfo("Append to CSV", "\n".join(lines))
            self.status.config(
                text=f"Append export: {summary.rows_added} added, "
                f"{summary.rows_updated} updated, {summary.rows_kept} kept"
            )
        elif purpose == "filename":
            self._filename_dialog(files)
        elif purpose == "report":
            self._report_dialog(files)
        elif purpose == "consistency":
            self._consistency_dialog(files)
        elif purpose == "jobrun":
            self._finish_job_run(files)

    def _export_library(self) -> None:
        """Ask whether this export starts a new CSV or appends to one.

        "New" replaces the chosen file with a fresh export. "Append…"
        merges the scan into an existing library CSV (rows keyed by
        FilePath, new tag columns added at the end) — the way a
        library CSV gets built up folder by folder.
        """
        dialog = tk.Toplevel(self)
        dialog.title("Export library to CSV")
        ttk.Label(
            dialog,
            text="Export the scanned library's tags as one row per file.\n"
                 "Start a new CSV, or append this scan into an existing "
                 "library CSV.",
            justify="left",
        ).pack(padx=12, pady=(12, 6), anchor="w")
        bar = ttk.Frame(dialog)
        bar.pack(padx=12, pady=(0, 12), anchor="w")

        def _new() -> None:
            dialog.destroy()
            path = filedialog.asksaveasfilename(
                title="Export library to a new CSV", defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv")],
            )
            if path:
                self._scan_for(f"export:{path}")

        def _append() -> None:
            dialog.destroy()
            path = filedialog.askopenfilename(
                title="Append to an existing CSV",
                filetypes=[("CSV Files", "*.csv")],
            )
            if path:
                self._scan_for(f"append:{path}")

        ttk.Button(bar, text="Export to a new CSV…", command=_new).pack(
            side="left", padx=2
        )
        ttk.Button(bar, text="Append to an existing CSV…", command=_append).pack(
            side="left", padx=2
        )
        ttk.Button(bar, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=2
        )

    def _tags_from_filename(self) -> None:
        self._scan_for("filename")

    def _library_report(self) -> None:
        self._scan_for("report")

    def _consistency_check(self) -> None:
        self._scan_for("consistency")

    # ------------------------------------------------------------ jobs (R6)
    def _refresh_jobs(self) -> None:
        """Reload the Files tab's job combobox from the saved jobs."""
        if not hasattr(self, "job_combo"):
            return
        current = self.job_combo.get()
        names = jobs_mod.list_jobs()
        self.job_combo["values"] = names
        if current in names:
            self.job_combo.set(current)
        elif names:
            self.job_combo.set(names[0])
        else:
            self.job_combo.set("")

    def _save_current_as_job(self) -> None:
        """Save the current project (+ this session's pattern) as a job."""
        name = simpledialog.askstring("Save current as job", "Job name:")
        if not name or not name.strip():
            return
        # The filename dialog's pattern is GUI-side state, tracked in
        # last_pattern_layer when a filename layer is applied; it is
        # part of the run, so it is part of the job.
        pattern_layers = (
            [dict(self.last_pattern_layer)] if self.last_pattern_layer else []
        )
        job = jobs_mod.job_from_project(
            name.strip(), self.project, pattern_layers=pattern_layers
        )
        try:
            path = jobs_mod.save_job(job)
        except Exception as exc:
            messagebox.showerror("Save job", str(exc))
            return
        self._refresh_jobs()
        self.job_combo.set(job.name)
        self.status.config(text=f"Job {job.name!r} saved to {path}")

    def _run_job(self) -> None:
        """Load the chosen job as the project and build its preview.

        The scan runs on the usual worker thread; _finish_job_run
        (reached via the "jobrun" scan purpose) then adds the job's
        pattern layers and shows the Preview tab.
        """
        name = self.job_combo.get().strip() if hasattr(self, "job_combo") else ""
        if not name:
            messagebox.showinfo("Run job", "Save or choose a job first.")
            return
        try:
            job = jobs_mod.load_job(name)
        except Exception as exc:
            messagebox.showerror("Run job", str(exc))
            return
        self.project = jobs_mod.job_to_project(job)
        self.project_path = None
        self.preview = None
        self._pending_job = job
        self._refresh_all()
        self._scan_for("jobrun")

    def _finish_job_run(self, files) -> None:
        """Second half of Run job: preview + the job's pattern layers."""
        job = self._pending_job
        self._pending_job = None
        if job is None:
            return
        preview = (
            build_preview(self.project, files=files)
            if self.project.csv_entries
            else empty_preview(files)
        )
        for layer in job.pattern_layers:
            values: dict[str, dict[str, str]] = {}
            for mp3 in files:
                try:
                    captured = capture_for_file(
                        layer.get("pattern", ""), mp3.path,
                        root=layer.get("root") or None,
                        use_path=bool(layer.get("use_path")),
                    )
                except ValueError as exc:
                    messagebox.showerror("Run job", f"Bad pattern layer: {exc}")
                    return
                if captured:
                    values[mp3.path] = captured
            if values:
                add_value_layer(
                    preview, files, values, "filename pattern",
                    self.project.alternative_names,
                )
        self.preview = preview
        self._refresh_preview()
        self.tabs.select(self._preview_tab_widget())
        self.status.config(text=f"Job {job.name!r} preview built")

    def _delete_job(self) -> None:
        name = self.job_combo.get().strip() if hasattr(self, "job_combo") else ""
        if not name:
            messagebox.showinfo("Delete job", "Choose a job first.")
            return
        if not messagebox.askyesno("Delete job", f"Delete the saved job {name!r}?"):
            return
        if jobs_mod.delete_job(name):
            self._refresh_jobs()
            self.status.config(text=f"Job {name!r} deleted")
        else:
            messagebox.showinfo("Delete job", f"No saved job called {name!r}.")

    # ------------------------------------------- dropped / pasted paths
    def _accept_paths(self, paths) -> None:
        """Add dropped or pasted paths to the project.

        Folders and MP3 files become MP3 paths; ``.csv`` files become
        CSV layers; anything else (missing paths, other file types) is
        counted and reported rather than silently swallowed.
        """
        added_mp3 = added_csv = skipped = 0
        for raw in paths:
            path = str(raw).strip()
            if not path:
                continue
            if os.path.isdir(path) or (
                os.path.isfile(path) and path.lower().endswith(".mp3")
            ):
                self.project.add_mp3_path(path)
                added_mp3 += 1
            elif os.path.isfile(path) and path.lower().endswith(".csv"):
                try:
                    self.project.add_csv_file(path)
                    added_csv += 1
                except Exception as exc:
                    messagebox.showerror("Add CSV", str(exc))
            else:
                skipped += 1
        self._refresh_all()
        self.status.config(
            text=f"Added {added_mp3} MP3 path(s), {added_csv} CSV file(s)"
                 + (f", skipped {skipped}" if skipped else "")
        )

    def _on_drop(self, event) -> str:
        """Handle a tkinterdnd2 drop of files/folders onto the window."""
        self._accept_paths(_split_dnd_data(getattr(event, "data", "")))
        return "copy"

    def _paste_paths(self) -> None:
        """The no-tkinterdnd2 fallback: paths from the clipboard.

        One path per line — the form "copy as path" tools and a plain
        text selection of paths both produce.
        """
        try:
            text = self.clipboard_get()
        except tk.TclError:
            text = ""
        paths = split_pasted_paths(text)
        if not paths:
            messagebox.showinfo(
                "Paste paths",
                "The clipboard holds no paths. Copy one file or folder "
                "path per line, then try again.",
            )
            return
        self._accept_paths(paths)

    # ------------------------------------------------- consistency dialog
    def _consistency_dialog(self, files) -> None:
        """Tags-vs-path consistency over the scanned files. READ-ONLY.

        The dialog can only *report* disagreements — it has no Apply
        path at all, and the engine module behind it imports nothing
        that can write a tag, so a check here can never change a file.
        Its defaults come from the filename-pattern feature: the last
        pattern applied this session when there is one.
        """
        dialog = tk.Toplevel(self)
        dialog.title("Consistency check — tags vs path (read-only)")
        dialog.geometry("780x560")
        last = self.last_pattern_layer or {}
        first_folder = next(
            (p for p in self.project.mp3_paths if os.path.isdir(p)), ""
        )
        pattern_var = tk.StringVar(
            value=last.get("pattern") or "{Lead Performer} - {Title}"
        )
        root_var = tk.StringVar(value=last.get("root") or first_folder)
        use_path_var = tk.BooleanVar(value=bool(last.get("use_path", False)))
        ttk.Label(
            dialog,
            text="Pattern — the values it captures from each file's name "
                 "(or path) are compared with the tags actually stored "
                 "in the file. This check never changes any file.",
        ).pack(anchor="w", padx=8, pady=6)
        ttk.Entry(dialog, textvariable=pattern_var, width=90).pack(fill="x", padx=8)
        root_bar = ttk.Frame(dialog)
        root_bar.pack(fill="x", padx=8, pady=4)
        ttk.Label(root_bar, text="Root folder:").pack(side="left")
        ttk.Entry(root_bar, textvariable=root_var, width=64).pack(side="left", padx=4)
        ttk.Checkbutton(
            root_bar, text="Match against the path (relative to the root)",
            variable=use_path_var,
        ).pack(side="left", padx=4)
        output = tk.Text(dialog, wrap="word", height=20)
        output.pack(fill="both", expand=True, padx=8, pady=6)
        state: dict = {"result": None}

        def run() -> None:
            """Run the check with the current pattern settings."""
            try:
                result = check_consistency(
                    files, pattern_var.get(),
                    root=root_var.get().strip() or None,
                    use_path=bool(use_path_var.get()),
                    alternative_names=self.project.alternative_names,
                )
            except ValueError as exc:
                messagebox.showerror("Consistency check", f"Bad pattern: {exc}")
                return
            state["result"] = result
            output.config(state="normal")
            output.delete("1.0", "end")
            output.insert(
                "1.0", render_consistency_text(result, pattern_var.get())
            )
            output.config(state="disabled")

        def save() -> None:
            """Save the report (.txt, or .csv by extension)."""
            if state["result"] is None:
                run()
            if state["result"] is None:
                return
            path = filedialog.asksaveasfilename(
                title="Save consistency report", defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv")],
            )
            if not path:
                return
            if path.lower().endswith(".csv"):
                content = render_consistency_csv(state["result"])
            else:
                content = render_consistency_text(
                    state["result"], pattern_var.get()
                )
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
            self.status.config(text=f"Consistency report saved to {path}")

        bar = ttk.Frame(dialog)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Button(bar, text="Run check", command=run).pack(side="left", padx=2)
        ttk.Button(bar, text="Save report…", command=save).pack(side="left", padx=2)
        ttk.Button(bar, text="Close", command=dialog.destroy).pack(side="left", padx=2)
        run()

    # ------------------------------------------------------- sync dialog
    def _sync_tags_dialog(self) -> None:
        """Two-library tag sync: pair, compare, then build a preview.

        Building the preview is all this dialog does — the ordinary
        Preview/Apply flow (with its change log and snapshot undo)
        takes it from there, exactly like a sync from the CLI.
        """
        dialog = tk.Toplevel(self)
        dialog.title("Sync tags from another library")
        dialog.geometry("780x580")
        first_folder = next(
            (p for p in self.project.mp3_paths if os.path.isdir(p)), ""
        )
        source_var = tk.StringVar(value="")
        target_var = tk.StringVar(value=first_folder)
        for label, var in (("Source library:", source_var),
                           ("Target library:", target_var)):
            bar = ttk.Frame(dialog)
            bar.pack(fill="x", padx=8, pady=3)
            ttk.Label(bar, text=label, width=16).pack(side="left")

            def _browse(v=var) -> None:
                folder = filedialog.askdirectory(
                    title="Select a library folder", parent=dialog
                )
                if folder:
                    v.set(folder)

            ttk.Entry(bar, textvariable=var, width=64).pack(side="left", padx=2)
            ttk.Button(bar, text="Browse…", command=_browse).pack(side="left", padx=2)
        cover_var = tk.BooleanVar(value=True)
        fp_var = tk.BooleanVar(value=False)
        option_bar = ttk.Frame(dialog)
        option_bar.pack(fill="x", padx=8, pady=3)
        ttk.Checkbutton(
            option_bar, text="Copy cover art", variable=cover_var
        ).pack(side="left", padx=2)
        fp_check = ttk.Checkbutton(
            option_bar, text="Pair leftovers by fingerprint", variable=fp_var
        )
        fp_check.pack(side="left", padx=8)
        if fingerprints.fpcalc_path() is None:
            fp_check.state(["disabled"])
            ttk.Label(
                option_bar, text="(fpcalc not detected — see Setup tab)"
            ).pack(side="left")
        ttk.Label(dialog, text="Tags to copy:").pack(anchor="w", padx=8, pady=(6, 0))
        tags_frame = ttk.Frame(dialog)
        tags_frame.pack(fill="x", padx=8)
        output = tk.Text(dialog, wrap="word", height=14)
        output.pack(fill="both", expand=True, padx=8, pady=6)
        state: dict = {"plan": None, "source_files": [], "target_files": [],
                       "tag_vars": {}}

        def show(text: str) -> None:
            output.config(state="normal")
            output.delete("1.0", "end")
            output.insert("1.0", text)
            output.config(state="disabled")

        def scan_compare() -> None:
            """Scan both libraries, pair them, and report the result."""
            source_root, target_root = source_var.get().strip(), target_var.get().strip()
            if not source_root or not target_root:
                messagebox.showinfo(
                    "Sync tags", "Pick both a source and a target library folder."
                )
                return
            dialog.config(cursor="watch")
            dialog.update_idletasks()
            try:
                source_files = scan_files([source_root])
                target_files = scan_files([target_root])
                plan = sync_mod.pair_libraries(
                    source_root, target_root,
                    source_files=source_files, target_files=target_files,
                )
                if fp_var.get() and fingerprints.fpcalc_path() is not None:
                    leftovers = plan.unpaired_source + plan.unpaired_target
                    if leftovers:
                        fps = fingerprints.fingerprints_for(leftovers)
                        plan = sync_mod.pair_leftovers_by_fingerprint(
                            plan, fps,
                            {p: fp.duration for p, fp in fps.items()},
                        )
            finally:
                dialog.config(cursor="")
            state.update(
                plan=plan, source_files=source_files, target_files=target_files
            )
            # (Re)build the tag checkbox list: the engine's default
            # set (every text tag on the paired sources), all checked.
            for child in tags_frame.winfo_children():
                child.destroy()
            state["tag_vars"] = {}
            defaults = sync_mod.default_sync_tags(plan, source_files)
            for index, tag_name in enumerate(defaults):
                var = tk.BooleanVar(value=True)
                state["tag_vars"][tag_name] = var
                ttk.Checkbutton(
                    tags_frame, text=tag_name, variable=var
                ).grid(row=index // 4, column=index % 4, sticky="w", padx=4)
            differences = sync_mod.tag_differences(
                plan, source_files, target_files, defaults,
                include_cover=bool(cover_var.get()),
            )
            lines = [
                f"Paired files: {len(plan.pairs)}",
                f"Differences with all tags checked: {len(differences)}",
                "",
                f"Unpaired source files ({len(plan.unpaired_source)}):",
                *[f"  {p}" for p in plan.unpaired_source],
                f"Unpaired target files ({len(plan.unpaired_target)}):",
                *[f"  {p}" for p in plan.unpaired_target],
            ]
            show("\n".join(lines) + "\n")

        def build() -> None:
            """Build the sync preview and switch to the Preview tab."""
            if state["plan"] is None:
                scan_compare()
            if state["plan"] is None:
                return
            tags = [name for name, var in state["tag_vars"].items() if var.get()]
            preview = sync_mod.build_sync_preview(
                state["plan"], state["source_files"], state["target_files"],
                tags,
                include_cover=bool(cover_var.get()),
                cover_dir=self.project.apply_log_folder,
                alternative_names=self.project.alternative_names,
            )
            self._note_scanned(state["target_files"])
            self.preview = preview
            dialog.destroy()
            self._refresh_preview()
            self.tabs.select(self._preview_tab_widget())
            self.status.config(
                text="Sync preview built — review it, then Apply as usual"
            )

        bar = ttk.Frame(dialog)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Button(bar, text="Scan & compare", command=scan_compare).pack(side="left", padx=2)
        ttk.Button(bar, text="Build preview", command=build).pack(side="left", padx=2)
        ttk.Button(bar, text="Close", command=dialog.destroy).pack(side="left", padx=2)

    def _layer_values(self, files, values, source: str) -> None:
        """Merge a virtual value layer into the current preview and show it."""
        base = self.preview if self.preview is not None else empty_preview(files)
        add_value_layer(
            base, files, values, source, self.project.alternative_names
        )
        self.preview = base
        self._refresh_preview()
        self.tabs.select(self._preview_tab_widget())
        self.status.config(text=f"Preview updated from {source}")

    def _filename_dialog(self, files) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Tags from filename / path")
        dialog.geometry("760x520")
        ttk.Label(
            dialog,
            text="Pattern — tag names in braces capture values; the rest must "
                 "match literally.\nExample:  {Lead Performer} - {Title}    "
                 "or, with “use path”:  {Lead Performer}/{Album}/{Track Number} - {Title}",
        ).pack(anchor="w", padx=8, pady=6)
        pattern_var = tk.StringVar(value="{Lead Performer} - {Title}")
        ttk.Entry(dialog, textvariable=pattern_var, width=90).pack(fill="x", padx=8)
        use_path_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            dialog, text="Match against the path (relative to the first added folder)",
            variable=use_path_var,
        ).pack(anchor="w", padx=8, pady=4)
        output = tk.Text(dialog, wrap="none", height=18)
        output.pack(fill="both", expand=True, padx=8, pady=6)

        def root_folder():
            """The first added folder, used as the pattern-matching root."""
            for path in self.project.mp3_paths:
                if os.path.isdir(path):
                    return path
            return None

        def captures():
            """Captures for every scanned file with the current pattern."""
            return {
                mp3.path: captured
                for mp3 in files
                if (captured := capture_for_file(
                    pattern_var.get(), mp3.path,
                    root=root_folder(), use_path=bool(use_path_var.get()),
                ))
            }

        def check() -> None:
            """Render a live capture preview for the first matching files."""
            output.delete("1.0", "end")
            try:
                parse_pattern(pattern_var.get())
                found = captures()
            except ValueError as exc:
                output.insert("1.0", f"Bad pattern: {exc}")
                return
            output.insert("end", f"{len(found)} of {len(files)} file(s) match.\n\n")
            for path, captured in list(found.items())[:10]:
                output.insert("end", f"{os.path.basename(path)}\n")
                for tag_name, value in captured.items():
                    output.insert("end", f"    {tag_name} = {value}\n")

        def build() -> None:
            """Turn the captures into a preview layer and close the dialog."""
            try:
                found = captures()
            except ValueError as exc:
                messagebox.showerror("Tags from filename", str(exc))
                return
            if not found:
                messagebox.showinfo("Tags from filename", "The pattern matched no files.")
                return
            # Remember the pattern spec: job saving includes it as a
            # pattern layer, and the consistency dialog defaults to it.
            self.last_pattern_layer = {
                "pattern": pattern_var.get(),
                "root": root_folder() or "",
                "use_path": bool(use_path_var.get()),
            }
            dialog.destroy()
            self._layer_values(files, found, "filename pattern")

        bar = ttk.Frame(dialog)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Button(bar, text="Check pattern", command=check).pack(side="left", padx=2)
        ttk.Button(bar, text="Build preview", command=build).pack(side="left", padx=2)
        ttk.Button(bar, text="Cancel", command=dialog.destroy).pack(side="left", padx=2)
        check()

    def _report_dialog(self, files) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Library report — duplicates, variants, completeness")
        dialog.geometry("820x640")
        duplicates = duplicate_groups(files)
        state = {"variants": [], "tag": "Lead Performer"}
        text = tk.Text(dialog, wrap="word")
        text.pack(fill="both", expand=True, padx=8, pady=6)
        ttk.Label(
            dialog,
            text="Spelling variants — select one spelling, then “Use selected "
                 "spelling” to preview changing every other spelling of that "
                 "value to it. Nothing changes until you Apply.",
        ).pack(anchor="w", padx=8)
        spellings = tk.Listbox(dialog, height=8)
        spellings.pack(fill="x", padx=8, pady=4)
        # Same recordings (by audio fingerprint): files that are the
        # same recording wearing different tags. Finding them needs
        # fpcalc and can be slow over a big library, so it runs when
        # its button is pressed, not when the dialog opens.
        ttk.Label(
            dialog,
            text="Same recordings — select one file of a group, then “Unify "
                 "from this file” to preview copying its tags to the rest "
                 "of its group. Nothing changes until you Apply.",
        ).pack(anchor="w", padx=8)
        same_list = tk.Listbox(dialog, height=6)
        same_list.pack(fill="x", padx=8, pady=4)
        same_state: dict = {"groups": [], "flat": []}

        def full_text() -> str:
            """The report text: duplicates/variants + album completeness."""
            return (
                render_text_report(duplicates, state["variants"])
                + "\n"
                + render_completeness_text(
                    album_completeness(files, self.project.alternative_names)
                )
            )

        def refresh() -> None:
            """Recompute the report display for the chosen variant tag."""
            state["variants"] = variant_groups(files, state["tag"])
            text.delete("1.0", "end")
            text.insert("1.0", full_text())
            spellings.delete(0, "end")
            for group in state["variants"]:
                for spelling, paths in group["spellings"].items():
                    spellings.insert(
                        "end",
                        f"{spelling}  ({len(paths)} file(s))  —  {state['tag']} "
                        f"variants of “{group['normalized']}”",
                    )

        def use_selected() -> None:
            """Preview unifying the group onto the selected spelling."""
            selection = spellings.curselection()
            if not selection:
                messagebox.showinfo("Library report", "Select a spelling first.")
                return
            # Walk the same order refresh() inserted: groups, then spellings.
            flat = [
                (group, spelling)
                for group in state["variants"]
                for spelling in group["spellings"]
            ]
            group, canonical = flat[selection[0]]
            values = {
                path: {state["tag"]: canonical}
                for spelling, paths in group["spellings"].items()
                if spelling != canonical
                for path in paths
            }
            if not values:
                return
            dialog.destroy()
            self._layer_values(files, values, "library report")

        def find_same() -> None:
            """Fingerprint the scanned files and list same-recording groups."""
            same_list.delete(0, "end")
            same_state["groups"] = []
            same_state["flat"] = []
            if fingerprints.fpcalc_path() is None:
                same_list.insert(
                    "end",
                    "fpcalc not detected — install Chromaprint's fpcalc to "
                    "find same recordings (see the Setup tab).",
                )
                return
            same_list.insert("end", "Fingerprinting…")
            dialog.update_idletasks()
            fps = fingerprints.fingerprints_for(files)
            groups = fingerprints.same_recording_groups(files, fps)
            same_state["groups"] = groups
            same_list.delete(0, "end")
            if not groups:
                same_list.insert("end", "(no same-recording groups found)")
            for number, group in enumerate(groups, start=1):
                for path in group["paths"]:
                    same_state["flat"].append((group, path))
                    same_list.insert(
                        "end",
                        f"[Group {number} · {group['duration']:.0f}s] {path}",
                    )

        def unify_same() -> None:
            """Preview copying the selected file's tags to its group."""
            selection = same_list.curselection()
            if not selection or not same_state["flat"]:
                messagebox.showinfo(
                    "Library report", "Find same recordings, then select a file."
                )
                return
            group, source_path = same_state["flat"][selection[0]]
            source = next((f for f in files if f.path == source_path), None)
            if source is None:
                return
            source_tags = {
                name: value for name, value in source.tags.items() if value
            }
            values = {
                path: dict(source_tags)
                for path in group["paths"]
                if path != source_path
            }
            if not values:
                return
            dialog.destroy()
            self._layer_values(files, values, "same recordings")

        def export() -> None:
            """Save the report to a file the user picks (.txt or .csv)."""
            path = filedialog.asksaveasfilename(
                title="Export report", defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv")],
            )
            if path:
                # A .csv path gets the one-row-per-file CSV rendering;
                # anything else gets the text report shown in the dialog.
                if path.lower().endswith(".csv"):
                    content = render_csv_report(duplicates, state["variants"])
                else:
                    content = full_text()
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(content)

        bar = ttk.Frame(dialog)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Label(bar, text="Variant tag:").pack(side="left")
        tag_combo = ttk.Combobox(
            bar, state="readonly", width=20,
            values=["Lead Performer", "Album", "Genre", "Title", "Composer"],
        )
        tag_combo.set("Lead Performer")
        tag_combo.pack(side="left", padx=2)
        tag_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: (state.update(tag=tag_combo.get()), refresh()),
        )
        ttk.Button(bar, text="Use selected spelling", command=use_selected).pack(side="left", padx=2)
        ttk.Button(bar, text="Find same recordings", command=find_same).pack(side="left", padx=2)
        ttk.Button(bar, text="Unify from this file", command=unify_same).pack(side="left", padx=2)
        ttk.Button(bar, text="Export report…", command=export).pack(side="left", padx=2)
        ttk.Button(bar, text="Close", command=dialog.destroy).pack(side="left", padx=2)
        refresh()

    def _lookup_musicbrainz(self) -> None:
        """Opt-in MusicBrainz fill: a dialog picks fields, a thread looks up."""
        if self._busy:
            return
        if not self.project.mp3_paths:
            messagebox.showinfo("MusicBrainz", "Add some MP3 files first.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Fill missing tags (MusicBrainz)")
        dialog.geometry("440x300")
        ttk.Label(
            dialog,
            text="Look up tags that are EMPTY in each file, using its Title\n"
                 "and Lead Performer. Results go to the Preview — nothing is\n"
                 "written until you Apply. Max 1 request per second.",
        ).pack(anchor="w", padx=10, pady=8)
        field_vars = {
            name: tk.BooleanVar(value=name in ("Album", "Year", "Genre"))
            for name in ("Album", "Year", "Recording Date", "Genre")
        }
        for name, var in field_vars.items():
            ttk.Checkbutton(dialog, text=name, variable=var).pack(anchor="w", padx=16)

        def start() -> None:
            """Start the MusicBrainz lookup thread with the chosen fields."""
            fields = [name for name, var in field_vars.items() if var.get()]
            dialog.destroy()
            if not fields:
                return
            self._busy = True
            self.status.config(text="Looking up on MusicBrainz…")
            project = self.project

            def work() -> None:
                """Worker-thread body: does the slow work, posts results to the job queue."""
                try:
                    files = scan_files(project.mp3_paths)
                    self._jobs.put(("scanned_files", files))
                    fills, errors = musicbrainz.fill_missing(
                        files, fields,
                        progress=lambda d, t, _p: self._jobs.put(("progress", (d, t))),
                    )
                    base = (
                        build_preview(project, files=files)
                        if project.csv_entries
                        else empty_preview(files)
                    )
                    add_value_layer(
                        base, files, fills, "MusicBrainz lookup",
                        project.alternative_names,
                    )
                    self._jobs.put(("preview_done", base))
                    if errors:
                        self._jobs.put(("lookup_errors", errors))
                except Exception as exc:
                    self._jobs.put(("error", exc))

            threading.Thread(target=work, daemon=True).start()

        ttk.Button(dialog, text="Look up", command=start).pack(side="left", padx=10, pady=10)
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack(side="left", pady=10)

    def _undo_run(self) -> None:
        if self._busy:
            return
        self._sync_log_folder()
        path = filedialog.askopenfilename(
            title="Undo a run — pick its .undo snapshot",
            initialdir=self.project.apply_log_folder,
            filetypes=[("Undo snapshots", "*.undo"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            info = undo.read_undo_file(path)
            count = len(info.get("files", []))
            created = info.get("created", "?")
        except Exception as exc:
            messagebox.showerror("Undo", str(exc))
            return
        if not messagebox.askyesno(
            "Undo a run",
            f"Restore the tags of {count} file(s) from the run saved "
            f"{created}?\nFiles changed since that run are skipped.",
        ):
            return
        self._busy = True
        self.status.config(text="Undoing…")
        self.tabs.select(self.tabs.tabs()[3])

        def work() -> None:
            """Worker-thread body: does the slow work, posts results to the job queue."""
            try:
                result = undo.undo_run(
                    path,
                    progress=lambda d, t, _p: self._jobs.put(("progress", (d, t))),
                )
                self._jobs.put(("undo_done", result))
            except Exception as exc:
                self._jobs.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()

    # ----------------------------------------------------------- background
    def _poll_jobs(self) -> None:
        try:
            while True:
                kind, payload = self._jobs.get_nowait()
                if kind == "progress":
                    done, total = payload
                    self.progress["maximum"] = max(total, 1)
                    self.progress["value"] = done
                elif kind == "scanned_files":
                    # A worker's scan, kept for the round-2 features
                    # that read the last scan's tags (album grouping,
                    # completeness, inline-edit old values).
                    self._note_scanned(payload)
                elif kind == "preview_done":
                    self.preview = payload
                    self._busy = False
                    self._refresh_preview()
                    self.status.config(text="Preview built")
                    self.tabs.select(self._preview_tab_widget())
                elif kind == "apply_done":
                    result = payload
                    self._busy = False
                    for message in result.messages:
                        self.apply_output.insert("end", message + "\n")
                    for error in result.errors:
                        self.apply_output.insert("end", "ERROR: " + error + "\n")
                    self.apply_output.insert(
                        "end",
                        f"Done: {result.files_written} file(s) written, "
                        f"{result.tags_written} tag(s), {result.files_unchanged} unchanged.\n",
                    )
                    if result.undo_file:
                        self.apply_output.insert(
                            "end", f"Undo snapshot: {result.undo_file}\n"
                        )
                    self.status.config(text="Apply finished")
                elif kind == "files_scanned":
                    purpose, files = payload
                    self._busy = False
                    self._on_files_scanned(purpose, files)
                elif kind == "undo_done":
                    result = payload
                    self._busy = False
                    for message in result.messages:
                        self.apply_output.insert("end", message + "\n")
                    self.apply_output.insert(
                        "end",
                        f"Undo done: {result.restored} file(s) restored, "
                        f"{len(result.skipped)} skipped, "
                        f"{len(result.errors)} error(s).\n",
                    )
                    self.status.config(text="Undo finished")
                elif kind == "lookup_errors":
                    shown = "\n".join(payload[:10])
                    self.apply_output.insert(
                        "end", "MusicBrainz lookup problems:\n" + shown + "\n"
                    )
                elif kind == "error":
                    self._busy = False
                    messagebox.showerror("Error", str(payload))
                    self.status.config(text="Error")
        except queue.Empty:
            pass
        self.after(100, self._poll_jobs)

    def _preview_tab_widget(self):
        return self.tabs.tabs()[2]

    def _start_preview(self) -> None:
        if self._busy:
            return
        if not self.project.mp3_paths or not self.project.csv_entries:
            messagebox.showinfo(
                "Build Preview", "Add some MP3 files and at least one CSV file first."
            )
            return
        self._busy = True
        self.status.config(text="Building preview…")
        project = self.project

        def work() -> None:
            """Worker-thread body: does the slow work, posts results to the job queue."""
            try:
                # Scan explicitly (rather than letting build_preview
                # scan) so the GUI keeps the scanned files for its
                # last-scan lookup maps.
                files = scan_files(
                    project.mp3_paths,
                    progress=lambda d, t, _p: self._jobs.put(("progress", (d, t))),
                )
                self._jobs.put(("scanned_files", files))
                preview = build_preview(project, files=files)
                self._jobs.put(("preview_done", preview))
            except Exception as exc:
                self._jobs.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()

    def _start_apply(self) -> None:
        if self._busy:
            return
        self._sync_log_folder()
        if self.preview is None:
            messagebox.showinfo("Apply", "Build a preview first — Apply writes what the preview shows.")
            return
        if not messagebox.askyesno(
            "Apply tags",
            f"Write {self.preview.total_changes} changed tag(s) in "
            f"{self.preview.files_matched} file(s)? A change log will be saved.",
        ):
            return
        self._busy = True
        self.status.config(text="Applying…")
        preview = self.preview
        log_folder = self.project.apply_log_folder

        def work() -> None:
            """Worker-thread body: does the slow work, posts results to the job queue."""
            try:
                result = apply_preview(
                    preview,
                    log_folder=log_folder,
                    progress=lambda d, t, _p: self._jobs.put(("progress", (d, t))),
                )
                self._jobs.put(("apply_done", result))
            except Exception as exc:
                self._jobs.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()
        self.tabs.select(self.tabs.tabs()[3])

    def _browse_log_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select a log/backup folder")
        if folder:
            self.log_folder.set(folder)
            self._sync_log_folder()

    # ---------------------------------------------------------------- setup
    def _refresh_names(self) -> None:
        if not hasattr(self, "names_tree"):
            return
        self.names_tree.delete(*self.names_tree.get_children())
        for frame, name in sorted(self.project.alternative_names.items()):
            self.names_tree.insert("", "end", iid=frame, values=(frame, name))

    def _add_name(self) -> None:
        frame = simpledialog.askstring("Add Tag Name", "ID3 frame (e.g. TIT2):")
        if not frame:
            return
        name = simpledialog.askstring("Add Tag Name", "Friendly name:")
        if name:
            self.project.alternative_names[frame.strip().upper()] = name.strip()
            self._refresh_names()

    def _edit_name(self) -> None:
        selection = self.names_tree.selection()
        if not selection:
            return
        frame = selection[0]
        name = simpledialog.askstring(
            "Edit Tag Name", "Friendly name:", initialvalue=self.project.alternative_names[frame]
        )
        if name:
            self.project.alternative_names[frame] = name.strip()
            self._refresh_names()

    def _remove_name(self) -> None:
        selection = self.names_tree.selection()
        if selection:
            self.project.alternative_names.pop(selection[0], None)
            self._refresh_names()

    def _reset_names(self) -> None:
        from .tags import DEFAULT_ALTERNATIVE_NAMES

        self.project.alternative_names = dict(DEFAULT_ALTERNATIVE_NAMES)
        self._refresh_names()


def main(project_path: str | None = None) -> int:
    """Entry point: no arguments opens the GUI; otherwise run a command."""
    app = App(project_path)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
