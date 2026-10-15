"""Named, reusable jobs: a saved run that can be re-run in one step.

A *job* is everything one full tagging run needs, saved under a name:

* the MP3 paths (files and/or folders),
* the CSV layers with their column roles (the project's
  :class:`~mp3csvtagger.project.CsvEntry` objects, reused as-is),
* the filename-pattern layers to apply after the CSVs, as plain dicts
  ``{"pattern", "root", "use_path"}`` (plain dicts because the GUI and
  CLI both build them from form fields, and JSON stores them as-is),
* the alternative tag-name map.

Running a job rebuilds the equivalent :class:`~mp3csvtagger.project.Project`
with :func:`job_to_project`, scans, builds the ordinary preview, then
adds each pattern layer's captures as a value layer — so a job run is
indistinguishable from doing the steps by hand, including its change
log and snapshot undo on apply.

Jobs are stored one JSON file per job in :func:`jobs_dir`
(``~/.mp3csvtagger/jobs`` by default, overridable with the
``MP3CSVTAGGER_JOBS_DIR`` environment variable), following the same
pattern as the user presets in :mod:`mp3csvtagger.presets`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .project import CsvEntry, Project
from .tags import DEFAULT_ALTERNATIVE_NAMES

#: Environment variable that overrides the user jobs directory.
JOBS_DIR_ENV_VAR = "MP3CSVTAGGER_JOBS_DIR"


@dataclass
class Job:
    """One named, reusable run (see the module docstring)."""

    name: str
    mp3_paths: list[str] = field(default_factory=list)
    csv_entries: list[CsvEntry] = field(default_factory=list)
    #: Filename-pattern layers, each ``{"pattern", "root", "use_path"}``.
    pattern_layers: list[dict] = field(default_factory=list)
    #: Frame id -> friendly name, as on a project.
    alternative_names: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_ALTERNATIVE_NAMES)
    )

    def to_dict(self) -> dict:
        """Return a JSON-safe ``dict`` representation of this job."""
        return {
            "name": self.name,
            "mp3_paths": list(self.mp3_paths),
            "csv_entries": [entry.to_dict() for entry in self.csv_entries],
            "pattern_layers": [dict(layer) for layer in self.pattern_layers],
            "alternative_names": dict(self.alternative_names),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        """Build a :class:`Job` from a ``dict`` such as :meth:`to_dict` output."""
        return cls(
            name=str(data["name"]),
            mp3_paths=[str(path) for path in data.get("mp3_paths", [])],
            csv_entries=[
                CsvEntry.from_dict(entry) for entry in data.get("csv_entries", [])
            ],
            pattern_layers=[
                dict(layer) for layer in data.get("pattern_layers", [])
            ],
            alternative_names=dict(
                data.get("alternative_names") or DEFAULT_ALTERNATIVE_NAMES
            ),
        )


def jobs_dir() -> Path:
    """Return the directory holding user job JSON files, creating it.

    The directory is ``$MP3CSVTAGGER_JOBS_DIR`` when that environment
    variable is set and non-empty, otherwise ``~/.mp3csvtagger/jobs``.
    The directory (including parents) is created on demand, mirroring
    :func:`mp3csvtagger.presets.presets_dir`.
    """
    override = os.environ.get(JOBS_DIR_ENV_VAR)
    if override:
        directory = Path(override).expanduser()
    else:
        directory = Path.home() / ".mp3csvtagger" / "jobs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _slugify(name: str) -> str:
    """Turn a job *name* into a safe file-name stem.

    Same rule as the presets slugifier (kept in step deliberately, so
    a name means the same file stem everywhere in this program):
    alphanumerics, ``-`` and ``_`` are kept, spaces become ``-``, every
    other character is dropped, runs of ``-`` collapse, and an empty
    result falls back to ``"job"``.
    """
    chars: list[str] = []
    for char in name.strip():
        if char == " ":
            chars.append("-")
        elif char.isalnum() or char in ("-", "_"):
            chars.append(char)
    slug = "".join(chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "job"


def _load_job_file(path: Path) -> Job:
    """Load a single job JSON file from *path*."""
    with open(path, encoding="utf-8") as handle:
        return Job.from_dict(json.load(handle))


def list_jobs() -> list[str]:
    """Return the names of all saved jobs, in file-name order.

    Unreadable or malformed JSON files are skipped — one bad file in
    the jobs folder must not hide every other job.
    """
    names: list[str] = []
    for path in sorted(jobs_dir().glob("*.json")):
        try:
            names.append(_load_job_file(path).name)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return names


def save_job(job: Job) -> Path:
    """Save *job* as a user job and return the file written.

    The file is ``jobs_dir()/<safe name>.json`` where ``<safe name>``
    is the slugified job name (see :func:`_slugify`). Saving a job
    whose name slugifies to an existing job's file replaces that job.
    """
    directory = jobs_dir()
    target = directory / f"{_slugify(job.name)}.json"
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(job.to_dict(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return target


def load_job(name: str) -> Job:
    """Load the job called *name*.

    *name* may also be a path to a job JSON file. Otherwise the job is
    looked up as ``jobs_dir()/<slugified name>.json``, then by exact
    (and finally case-insensitive) name among the saved jobs, so a job
    whose file stem differs from its display name still loads.

    Raises:
        FileNotFoundError: If no file and no saved job matches, with a
            message listing the available job names.
    """
    candidate = Path(name).expanduser()
    if candidate.is_file():
        return _load_job_file(candidate)

    slug_candidate = jobs_dir() / f"{_slugify(str(name))}.json"
    if slug_candidate.is_file():
        return _load_job_file(slug_candidate)

    for path in sorted(jobs_dir().glob("*.json")):
        try:
            job = _load_job_file(path)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if job.name == name or job.name.lower() == str(name).lower():
            return job

    names = ", ".join(repr(job_name) for job_name in list_jobs()) or "(none)"
    raise FileNotFoundError(
        f"Job not found: {name!r}. Available jobs: {names}."
    )


def delete_job(name: str) -> bool:
    """Delete the saved job called *name*; True when a file was removed.

    The job is resolved the same way :func:`load_job` resolves it
    (including accepting a file path). A name that matches no saved job
    returns ``False`` rather than raising — deleting something that is
    already gone is not an error for the caller to handle.
    """
    candidate = Path(name).expanduser()
    if candidate.is_file() and candidate.parent == jobs_dir():
        candidate.unlink()
        return True

    slug_candidate = jobs_dir() / f"{_slugify(str(name))}.json"
    if slug_candidate.is_file():
        slug_candidate.unlink()
        return True

    for path in sorted(jobs_dir().glob("*.json")):
        try:
            job = _load_job_file(path)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if job.name == name or job.name.lower() == str(name).lower():
            path.unlink()
            return True
    return False


def job_to_project(job: Job) -> Project:
    """Build the :class:`Project` equivalent to *job*.

    The CSV entries are deep-copied (through their dict form), so
    building or running the project can never mutate the saved job.
    A project's ``apply_log_folder`` is not part of a job — it is a
    per-run choice — so the project's default stands.
    """
    project = Project()
    project.mp3_paths = list(job.mp3_paths)
    project.csv_entries = [
        CsvEntry.from_dict(entry.to_dict()) for entry in job.csv_entries
    ]
    project.alternative_names = dict(job.alternative_names)
    return project


def job_from_project(name: str, project: Project, pattern_layers=()) -> Job:
    """Capture *project* (plus its pattern layers) as a job called *name*.

    *pattern_layers* is an iterable of ``{"pattern", "root",
    "use_path"}`` dicts — the pattern layers are a run step the GUI/CLI
    layers on top of the project's CSVs, so they are passed in rather
    than read off the project. The CSV entries are deep-copied, so
    later edits to the project do not rewrite the saved job.
    """
    return Job(
        name=name,
        mp3_paths=list(project.mp3_paths),
        csv_entries=[
            CsvEntry.from_dict(entry.to_dict()) for entry in project.csv_entries
        ],
        pattern_layers=[dict(layer) for layer in pattern_layers],
        alternative_names=dict(project.alternative_names),
    )
