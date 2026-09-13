"""
Game Registry: identifiers the game resolves by exact name.

Plugins and the engine frequently resolve strings by exact match — string
equality, ``Array.prototype.indexOf``, or a regex pattern — rather than printing
them to the player. A string resolved by name must never be translated: changing
it breaks the lookup and silently corrupts the game (a missed string is
recoverable, a broken lookup is not).

This module builds a project-wide registry of such identifiers from:

  * ``js/plugins/*.js`` sources — string literals and regex-pattern words,
  * ``data/*.json`` object keys — scenario ids and other runtime lookups.

The JSON parser consults it as one additional, purely-additive gate on top of
its existing heuristics. It is lazy and cached per project root: when the layout
cannot be found, the registry is empty and every existing check keeps working.

Matching is deliberately conservative to avoid dropping real prose: a value is
treated as a looked-up identifier only when it *looks* like an identifier (a
single ASCII token with no whitespace or sentence punctuation) and is present
verbatim in the registry (also case-insensitively, because plugins often compare
case-insensitively). Non-ASCII words and anything with spaces are never held
back by this gate.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from typing import Dict, Set

from .js_tokenizer import JSStringTokenizer

# A value is only ever treated as a looked-up identifier when it matches this
# shape: a single ASCII identifier token (letters, digits, and the common
# separators plugins use for keys). Whitespace or sentence punctuation means the
# value is prose the player reads, never a lookup.
_IDENTIFIER_SHAPE = re.compile(r"^[A-Za-z0-9_.\-/]+$")

# Uppercase runs inside a regex pattern are the words a plugin compares against
# (e.g. /SHOW OBJECTIVE/i -> "SHOW", "OBJECTIVE").
_RE_SHOUTED = re.compile(r"[A-Z][A-Z0-9_]+")

# Regex-pattern literals as the plugin writes them:
#   line.match(/pattern/flags)  or  /pattern/flags.test(line)
_RE_PATTERN = re.compile(r"/([^/\n\\]+)/[gimsuy]*")

# Registry cache keyed by normalized project root.
_REGISTRY_CACHE: Dict[str, "GameRegistry"] = {}
_REGISTRY_LOCK = threading.Lock()

# Reused tokenizer for collecting string literals from plugin sources.
_TOKENIZER = JSStringTokenizer()


@dataclass(slots=True)
class GameRegistry:
    """Identifiers a project resolves by exact name."""

    identifiers: Set[str] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not self.identifiers

    def matches_identifier(self, text: str) -> bool:
        """Return True when ``text`` is a looked-up identifier.

        Only values that read as a single identifier token are ever matched, so
        prose (spaces, punctuation, non-ASCII words) is never held back.
        """
        if not isinstance(text, str):
            return False
        bare = text.strip()
        if not bare or not _IDENTIFIER_SHAPE.match(bare):
            return False
        return (
            bare in self.identifiers
            or bare.lower() in self.identifiers
            or bare.upper() in self.identifiers
        )


class GameRegistryStore:
    """Lazy builder of the identifier registry for a project root."""

    def __init__(self, project_root: str | None) -> None:
        self._project_root = project_root
        self._registry: GameRegistry | None = None
        self._loaded = False

    def get(self) -> GameRegistry:
        if not self._loaded:
            self._registry = self._build()
            self._loaded = True
        return self._registry

    def _build(self) -> GameRegistry:
        root = self._project_root
        if not root or not os.path.isdir(root):
            return GameRegistry()

        identifiers: Set[str] = set()
        self._collect_plugins(root, identifiers)
        self._collect_data_keys(root, identifiers)
        return GameRegistry(identifiers=identifiers)

    def _collect_plugins(self, root: str, identifiers: Set[str]) -> None:
        plugins_dir = os.path.join(root, "js", "plugins")
        if not os.path.isdir(plugins_dir):
            return

        try:
            names = os.listdir(plugins_dir)
        except OSError:
            return

        for filename in names:
            if not filename.lower().endswith(".js"):
                continue
            source = _read_text(os.path.join(plugins_dir, filename))
            if source is None:
                continue
            self._collect_from_source(source, identifiers)

    @staticmethod
    def _collect_from_source(source: str, identifiers: Set[str]) -> None:
        # String literals: a plugin compares its own keywords, so they appear
        # spelled out in its source.
        for _start, _end, value, _quote in _TOKENIZER.extract_strings(source):
            value = value.strip()
            if value:
                identifiers.add(value)

        # Regex patterns: words a plugin matches on a command line.
        for match in _RE_PATTERN.finditer(source):
            for word in _RE_SHOUTED.findall(match.group(1)):
                identifiers.add(word)

    @staticmethod
    def _collect_data_keys(root: str, identifiers: Set[str]) -> None:
        data_dir = os.path.join(root, "data")
        if not os.path.isdir(data_dir):
            return

        try:
            names = os.listdir(data_dir)
        except OSError:
            return

        for filename in names:
            if not filename.lower().endswith(".json"):
                continue
            body = _read_text(os.path.join(data_dir, filename))
            if body is None:
                continue
            _collect_json_keys(body, identifiers)


def get_registry(project_root: str | None) -> GameRegistry:
    """Return the cached identifier registry for ``project_root``."""
    if not project_root:
        return GameRegistry()

    normalized = os.path.normpath(project_root)
    with _REGISTRY_LOCK:
        cached = _REGISTRY_CACHE.get(normalized)
        if cached is not None:
            return cached

    registry = GameRegistryStore(normalized).get()
    with _REGISTRY_LOCK:
        _REGISTRY_CACHE[normalized] = registry
    return registry


def find_project_root(file_path: str) -> str | None:
    """Locate the MV/MZ project root (the dir holding ``js/plugins`` or ``data``)."""
    current_dir = os.path.dirname(os.path.abspath(file_path))

    for _ in range(6):
        if _looks_like_project_root(current_dir):
            return current_dir
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir

    return None


def _looks_like_project_root(directory: str) -> bool:
    if not directory or not os.path.isdir(directory):
        return False
    return os.path.isdir(os.path.join(directory, "js", "plugins")) or os.path.isdir(
        os.path.join(directory, "data")
    )


def _collect_json_keys(body: str, identifiers: Set[str]) -> None:
    """Collect object keys from a JSON body (strings on the left of a colon).

    Scans the raw bytes so huge map files are never fully parsed. Only keys
    written plainly (no escape sequences) are taken; a colon inside a string
    value is never mistaken for a key.
    """
    raw = body.encode("utf-8")
    length = len(raw)
    at = 0

    while at < length:
        if raw[at] != 0x22:  # b'"'
            at += 1
            continue

        opened = at + 1
        closed = opened
        plain = True
        while closed < length and raw[closed] != 0x22:
            if raw[closed] == 0x5C:  # b'\\'
                plain = False
                closed += 1
            closed += 1
        if closed >= length:
            return

        after = closed + 1
        while after < length and raw[after] in (0x20, 0x09, 0x0A, 0x0D):
            after += 1
        if plain and after < length and raw[after] == 0x3A:  # b':'
            key = body[opened:closed]
            if key:
                identifiers.add(key)

        at = closed + 1


def _read_text(file_path: str) -> str | None:
    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            with open(file_path, "r", encoding=encoding) as handle:
                return handle.read()
        except (OSError, UnicodeDecodeError):
            continue
    return None
