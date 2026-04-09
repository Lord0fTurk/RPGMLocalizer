"""
Semantic surface registry for RPG Maker extraction decisions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SurfaceRule:
    """A lightweight semantic rule for a text surface."""

    name: str
    text_hints: tuple[str, ...] = ()
    asset_hints: tuple[str, ...] = ()
    technical_hints: tuple[str, ...] = ()


class ExtractionSurfaceRegistry:
    """Classify keys and paths into semantic extraction surfaces."""

    TEXT_HINTS = (
        "text",
        "message",
        "caption",
        "label",
        "title",
        "description",
        "desc",
        "help",
        "tooltip",
        "hint",
        "command",
        "dialogue",
        "name",
    )
    MENU_HINTS = (
        "menu",
        "command",
        "option",
        "button",
        "choice",
        "status",
        "hud",
        "title",
        "help",
        "tooltip",
        "caption",
        "label",
    )
    ASSET_HINTS = (
        "audio",
        "sound",
        "bgm",
        "bgs",
        "se",
        "me",
        "image",
        "img",
        "picture",
        "face",
        "character",
        "tileset",
        "parallax",
        "battleback",
        "sprite",
        "icon",
        "file",
        "filename",
        "path",
        "folder",
        "directory",
        "movie",
        "video",
        "font",
    )
    TECHNICAL_HINTS = (
        "switch",
        "variable",
        "symbol",
        "code",
        "eval",
        "script",
        "bind",
        "index",
        "id",
        "locale",
        "require",
        "regex",
        "opacity",
        "speed",
        "scale",
        "volume",
        "pitch",
        "pan",
    )

    def tokenize(self, key: str) -> set[str]:
        """Tokenize a key/path into semantic words."""
        if not isinstance(key, str) or not key:
            return set()
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
        return {token for token in re.split(r"[^A-Za-z0-9]+", normalized.lower()) if token}

    def is_text_key(self, key: str) -> bool:
        tokens = self.tokenize(key)
        return bool(tokens & set(self.TEXT_HINTS)) and not bool(tokens & set(self.ASSET_HINTS))

    def is_menu_label_key(self, key: str) -> bool:
        tokens = self.tokenize(key)
        if not tokens:
            return False
        if bool(tokens & set(self.ASSET_HINTS)) or bool(tokens & set(self.TECHNICAL_HINTS)):
            return False
        return bool(tokens & set(self.MENU_HINTS))

    def is_asset_key(self, key: str) -> bool:
        tokens = self.tokenize(key)
        return bool(tokens & set(self.ASSET_HINTS))

    def is_technical_key(self, key: str) -> bool:
        tokens = self.tokenize(key)
        return bool(tokens & set(self.TECHNICAL_HINTS))

    def classify_surface(self, key: str) -> str:
        """Return the likely semantic surface for a path or key."""
        if self.is_asset_key(key):
            return "asset_reference"
        if self.is_technical_key(key):
            return "technical_identifier"
        if self.is_menu_label_key(key):
            return "menu_label"
        if self.is_text_key(key):
            return "text"
        return "generic"
