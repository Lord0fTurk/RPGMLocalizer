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
            (re.compile(r"^khas", re.IGNORECASE), PluginFamilyProfile(
                name="Khas",
                allow_single_word_text=False,
                asset_heavy=True,
                code_heavy=True,
                embedded_json_heavy=False,
                text_hints=("message", "text", "label", "title"),
                technical_hints=("image", "file", "folder", "shader", "light", "speed", "size", "color", "opacity"),
            )),
            (re.compile(r"^rs_", re.IGNORECASE), PluginFamilyProfile(
                name="RS",
                allow_single_word_text=True,
                asset_heavy=True,
                code_heavy=True,
                embedded_json_heavy=True,
                text_hints=("message", "text", "label", "name", "title", "help"),
                technical_hints=("image", "file", "font", "color", "opacity", "size", "scale", "position", "eval", "code"),
            )),
            (re.compile(r"^nuun_", re.IGNORECASE), PluginFamilyProfile(
                name="NUUN",
                allow_single_word_text=True,
                asset_heavy=False,
                code_heavy=True,
                embedded_json_heavy=True,
                text_hints=("name", "text", "label", "title", "help", "message", "description"),
                technical_hints=("symbol", "eval", "code", "icon", "color", "align", "font", "image", "file"),
            )),
            (re.compile(r"^dk_", re.IGNORECASE), PluginFamilyProfile(
                name="DK",
                allow_single_word_text=True,
                asset_heavy=False,
                code_heavy=True,
                embedded_json_heavy=True,
                text_hints=("text", "name", "label", "title", "message", "description", "help"),
                technical_hints=("eval", "code", "symbol", "icon", "file", "image", "color"),
            )),
            (re.compile(r"^nk_", re.IGNORECASE), PluginFamilyProfile(
                name="NK",
                allow_single_word_text=True,
                asset_heavy=True,
                code_heavy=False,
                embedded_json_heavy=False,
                text_hints=("text", "name", "label", "title", "message", "help"),
                technical_hints=("image", "file", "icon", "position", "offset", "folder", "color"),
            )),
            (re.compile(r"^alt_", re.IGNORECASE), PluginFamilyProfile(
                name="ALT",
                allow_single_word_text=True,
                asset_heavy=False,
                code_heavy=True,
                embedded_json_heavy=True,
                text_hints=("text", "name", "label", "message", "title", "description"),
                technical_hints=("eval", "code", "symbol", "file", "image", "color", "font"),
            )),
            # TRP_ family: mostly technical (particle, etc.) but some UI plugins exist.
            # Particle subsets are handled by NON_TRANSLATABLE_PLUGIN_PATTERNS; remaining TRP_
            # plugins get a conservative profile.
            (re.compile(r"^trp_", re.IGNORECASE), PluginFamilyProfile(
                name="TRP",
                allow_single_word_text=False,
                asset_heavy=True,
                code_heavy=True,
                embedded_json_heavy=True,
                text_hints=("text", "name", "label", "title", "message"),
                technical_hints=("particle", "emitter", "image", "file", "speed", "color", "opacity", "scale", "eval", "code"),
            )),
            # CGMZ plugin suite — rich text content (achievements, lore, etc.)
            (re.compile(r"^cgmz_", re.IGNORECASE), PluginFamilyProfile(
                name="CGMZ",
                allow_single_word_text=True,
                asset_heavy=False,
                code_heavy=False,
                embedded_json_heavy=True,
                text_hints=("name", "description", "text", "title", "label", "toast", "reward", "popup", "help"),
                technical_hints=("switch", "variable", "category", "points", "difficulty", "image", "file", "sound", "eval", "code"),
            )),
            # VisuStella MZ (VisuMZ_*) — heavily structured, Vocab params contain UI labels
            (re.compile(r"^visumz_", re.IGNORECASE), PluginFamilyProfile(
                name="VisuStella MZ",
                allow_single_word_text=True,
                asset_heavy=False,
                code_heavy=True,
                embedded_json_heavy=True,
                text_hints=("vocab", "text", "name", "label", "title", "message", "description", "help", "command"),
                technical_hints=("bind", "eval", "script", "code", "symbol", "file", "font", "icon", "switch", "variable"),
            )),
            # Third-party community authors — permissive: single-word UI labels common
            (re.compile(r"^(irina|ramza|szyu|hakuen|cae_|eli_|aerosys|krd_|ossra|chaucer|salted)_?", re.IGNORECASE), PluginFamilyProfile(
                name="Community_Permissive",
                allow_single_word_text=True,
                asset_heavy=False,
                code_heavy=False,
                embedded_json_heavy=False,
                text_hints=("text", "name", "label", "title", "message", "help", "description", "command"),
                technical_hints=("file", "image", "sound", "eval", "code", "symbol", "icon", "color"),
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
