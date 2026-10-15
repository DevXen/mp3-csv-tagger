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
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__, coverart, musicbrainz, presets, undo
from .apply import apply_preview
from .filename_tags import capture_for_file, parse_pattern
from .library_export import write_library_csv
from .library_report import (
    duplicate_groups,
    render_csv_report,
    render_text_report,
    variant_groups,
)
from .mp3files import scan as scan_files
from .preview import Preview, add_value_layer, build_preview, empty_preview
from .project import Project, Role

ROLE_NAMES = {int(role): role.name for role in Role}
NAME_ROLES = {role.name: int(role) for role in Role}

# The Help tab's content lives in helptext.py (one source of truth for the
# GUI, docs/HELP.md and other front-ends). Imported here for the builder.
from . import helptext  # noqa: E402


class App(tk.Tk):
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
        self.files_list = tk.Listbox(tab, selectmode="extended")
        self.files_list.pack(fill="both", expand=True)

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
        self.preview_tree = ttk.Treeview(tab, show="headings")
        self.preview_tree.pack(fill="both", expand=True)

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
        self._refresh_preview()

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
    def _refresh_preview(self) -> None:
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
        for row in self.preview.rows:
            values = [row.filename]
            for name in self.preview.write_tags:
                cell = row.cells.get(name)
                if cell is None:
                    values.append("")
                else:
                    # Cover-art values are image paths; show the friendly
                    # "[cover image: …]" / "[remove cover art]" form.
                    text = (
                        coverart.cover_display(cell.value)
                        if cell.frame == "APIC"
                        else cell.value
                    )
                    if cell.has_multiple:
                        text += f"  ({len(cell.candidates)} values)"
                    if cell.changed:
                        text = f"{cell.old_value}  →  {text}" if cell.old_value else text
                    values.append(text)
            tree.insert("", "end", iid=row.path, values=values)
        self.preview_stats.config(
            text=(
                f"Scanned {self.preview.files_scanned} · matched "
                f"{self.preview.files_matched} · {self.preview.total_changes} change(s)"
            )
        )

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
        if purpose.startswith("export:"):
            out_path = purpose[len("export:"):]
            columns = write_library_csv(files, out_path)
            self.status.config(
                text=f"Exported {len(files)} file(s), {len(columns)} columns to {out_path}"
            )
        elif purpose == "filename":
            self._filename_dialog(files)
        elif purpose == "report":
            self._report_dialog(files)

    def _export_library(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export library to CSV", defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if path:
            self._scan_for(f"export:{path}")

    def _tags_from_filename(self) -> None:
        self._scan_for("filename")

    def _library_report(self) -> None:
        self._scan_for("report")

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
        dialog.title("Library report — duplicates & spelling variants")
        dialog.geometry("820x560")
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

        def refresh() -> None:
            """Recompute the report display for the chosen variant tag."""
            state["variants"] = variant_groups(files, state["tag"])
            text.delete("1.0", "end")
            text.insert("1.0", render_text_report(duplicates, state["variants"]))
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
                    content = render_text_report(duplicates, state["variants"])
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
                preview = build_preview(
                    project,
                    progress=lambda d, t, _p: self._jobs.put(("progress", (d, t))),
                )
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
