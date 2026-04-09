"""
Plugin family classification for common RPG Maker plugin ecosystems.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class PluginFamilyProfile:
    """High-level behavior hints for a plugin family."""

    name: str
    allow_single_word_text: bool = False
    asset_heavy: bool = False
    code_heavy: bool = False
    embedded_json_heavy: bool = False
    text_hints: tuple[str, ...] = ()
    technical_hints: tuple[str, ...] = ()


class PluginFamilyRegistry:
    """Classify well-known plugin ecosystems into extraction profiles."""

    def __init__(self) -> None:
        self._profiles = (
            (re.compile(r"^(visumz|visustella|yep)_", re.IGNORECASE), PluginFamilyProfile(
                name="VisuStella/Yanfly",
                allow_single_word_text=True,
                asset_heavy=False,
                code_heavy=True,
                embedded_json_heavy=True,
                text_hints=("menu", "message", "status", "choice", "help", "title", "command", "text", "label", "description"),
                technical_hints=("bind", "eval", "script", "code", "symbol", "file", "font"),
            )),
            (re.compile(r"^mog_", re.IGNORECASE), PluginFamilyProfile(
                name="MOG",
                allow_single_word_text=True,
                asset_heavy=True,
                code_heavy=False,
                embedded_json_heavy=False,
                text_hints=("hud", "menu", "title", "battle", "message", "label", "text"),
                technical_hints=("image", "picture", "folder", "file", "font", "icon", "position"),
            )),
            (re.compile(r"^srd_", re.IGNORECASE), PluginFamilyProfile(
                name="SRD",
                allow_single_word_text=True,
                asset_heavy=False,
                code_heavy=True,
                embedded_json_heavy=True,
                text_hints=("name", "text", "label", "help", "title", "message", "quest", "menu"),
                technical_hints=("bind", "code", "eval", "file", "image", "sound", "folder"),
            )),
            (re.compile(r"^galv_", re.IGNORECASE), PluginFamilyProfile(
                name="Galv",
                allow_single_word_text=True,
                asset_heavy=True,
                code_heavy=False,
                embedded_json_heavy=False,
                text_hints=("menu", "battle", "hud", "label", "text", "name", "help", "title"),
                technical_hints=("image", "icon", "sprite", "position", "offset", "folder", "file"),
            )),
            (re.compile(r"^(olivia|orange|pxd|tddp|gs)_", re.IGNORECASE), PluginFamilyProfile(
                name="Utility/UI",
                allow_single_word_text=True,
                asset_heavy=True,
                code_heavy=True,
                embedded_json_heavy=True,
                text_hints=("menu", "ui", "hud", "quest", "label", "text", "title", "help", "name"),
                technical_hints=("file", "image", "sound", "font", "bind", "eval", "code", "symbol", "path", "folder"),
            )),
        )
        self._default = PluginFamilyProfile(name="Generic", allow_single_word_text=False)

    def classify(self, plugin_name: str) -> PluginFamilyProfile:
        """Return the best matching family profile for a plugin name."""
        if not plugin_name:
            return self._default
        for pattern, profile in self._profiles:
            if pattern.search(plugin_name):
                return profile
        return self._default
