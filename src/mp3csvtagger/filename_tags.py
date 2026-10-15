"""Capture tag values from filenames and paths.

Many libraries already carry the information that belongs in their tags
in the file *names* themselves::

    Rage Against the Machine - Township Rebellion.mp3
    Rage Against the Machine/Rage Against the Machine/01 - Township Rebellion.mp3

A *pattern* describes that layout in plain terms, with tag names in
braces wherever a value sits::

    {Lead Performer} - {Title}
    {Lead Performer}/{Album}/{Track Number} - {Title}

:func:`capture` turns a pattern and a piece of text into a ``{tag: value}``
dict (or ``None`` when the text does not fit the pattern), and
:func:`capture_for_file` applies a pattern to a file's name — or, with
``use_path=True``, to its path relative to a library root, which is how
the folder-per-album layout above is captured.

This module is a pure *source* of tag values, in keeping with the rest of
the project: a filename or path is never written to, only read from.
Nothing here touches the filesystem — :func:`capture_for_file` works on
path strings alone, so it can be previewed on files that do not exist.
"""

from __future__ import annotations

import os
import re

#: One piece of a parsed pattern: ``("lit", text)`` for literal text that
#: must appear verbatim, or ``("tag", name)`` for a ``{Name}`` placeholder.
Token = tuple[str, str]


def parse_pattern(pattern: str) -> list[Token]:
    """Split *pattern* into literal and tag tokens.

    Tag names appear in braces, e.g. ``"{Lead Performer} - {Title}"``
    parses to ``[("tag", "Lead Performer"), ("lit", " - "),
    ("tag", "Title")]``. Tag names are stripped of surrounding
    whitespace (``"{ Title }"`` is the tag ``"Title"``). Literal text is
    kept exactly as written — including a stray ``}``, which has no
    special meaning outside a tag.

    Raises:
        ValueError: if a tag is empty (``"{}"`` or ``"{ }"``), if a
            ``{`` is never closed, if the pattern contains no tag tokens
            at all (there would be nothing to capture), or if two tags
            sit directly next to each other with no literal text between
            them — adjacent tags are ambiguous, because there is no
            delimiter in the text to say where one value ends and the
            next begins.
    """
    if not pattern:
        raise ValueError("pattern is empty: it contains no tag tokens")

    tokens: list[Token] = []
    literal: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char != "{":
            literal.append(char)
            index += 1
            continue
        close = pattern.find("}", index + 1)
        if close == -1:
            raise ValueError(
                f"unclosed brace in pattern {pattern!r}: "
                f"'{{' at position {index} has no matching '}}'"
            )
        name = pattern[index + 1 : close].strip()
        if not name:
            raise ValueError(f"empty tag in pattern {pattern!r} at position {index}")
        if literal:
            tokens.append(("lit", "".join(literal)))
            literal = []
        elif tokens and tokens[-1][0] == "tag":
            raise ValueError(
                f"adjacent tags in pattern {pattern!r}: tags must be "
                "separated by literal text, otherwise there is no "
                "delimiter to split their values on"
            )
        tokens.append(("tag", name))
        index = close + 1
    if literal:
        tokens.append(("lit", "".join(literal)))

    if not any(kind == "tag" for kind, _text in tokens):
        raise ValueError(f"pattern {pattern!r} contains no tag tokens")
    return tokens


def capture(pattern: str, text: str) -> dict[str, str] | None:
    """Capture tag values from *text* according to *pattern*.

    The whole of *text* must match the pattern (the match is anchored at
    both ends). Literal parts must appear verbatim; each tag captures the
    text between the literals around it, stripped of surrounding
    whitespace. Returns ``None`` when the text does not match, or when
    any tag would capture an empty value.

    Raises:
        ValueError: if *pattern* is invalid — see :func:`parse_pattern`.
    """
    tokens = parse_pattern(pattern)

    # Build one regex group per tag, in token order, and remember which
    # tag each group belongs to (unnamed groups, so a pattern may even
    # repeat a tag name without breaking the regex).
    #
    # WHY capture lazily (".+?" rather than ".+"): a greedy group would
    # swallow the delimiters it is meant to stop at. For
    # "{Lead Performer} - {Title}" against "A - B - C", a greedy first
    # group takes "A - B" as the performer and leaves only "C" as the
    # title; a lazy group stops at the FIRST " - ", giving performer
    # "A" and title "B - C" — the value runs up to its delimiter, the
    # rest belongs to what follows. The lazy group still expands as far
    # as the anchored match requires, so a trailing tag ends up
    # capturing the rest of the text and a leading tag captures
    # everything up to the first literal.
    parts: list[str] = []
    names: list[str] = []
    for kind, value in tokens:
        if kind == "lit":
            parts.append(re.escape(value))
        else:
            parts.append("(.+?)")
            names.append(value)
    regex = re.compile("".join(parts), re.DOTALL)

    match = regex.fullmatch(text)
    if match is None:
        return None
    result: dict[str, str] = {}
    for name, raw in zip(names, match.groups()):
        value = raw.strip()
        if not value:
            # A capture of only whitespace is no value at all: treat the
            # text as not matching rather than inventing an empty tag.
            return None
        result[name] = value
    return result


def capture_for_file(
    pattern: str,
    path: str,
    root: str | None = None,
    use_path: bool = False,
) -> dict[str, str] | None:
    """Capture tag values from a file's name or path.

    By default the text matched against *pattern* is the file's name
    without its extension (the "stem"): ``"/music/01 Song.mp3"`` is
    matched as ``"01 Song"``.

    With ``use_path=True`` the text is the whole path with its extension
    removed and directory separators converted to ``"/"``, so one
    pattern can capture from the folder structure as well as the name,
    e.g. ``"{Lead Performer}/{Album}/{Track Number} - {Title}"``. When
    *root* is given, the path is first made relative to it (patterns
    should not have to name the library's own folder); when *root* is
    ``None`` the full path is used.

    Returns ``None`` when the name/path does not match *pattern*.

    Raises:
        ValueError: if *pattern* is invalid — see :func:`parse_pattern`.
    """
    if use_path:
        text = os.path.relpath(path, root) if root is not None else path
        text = os.path.splitext(text)[0].replace(os.sep, "/")
    else:
        text = os.path.splitext(os.path.basename(path))[0]
    return capture(pattern, text)
