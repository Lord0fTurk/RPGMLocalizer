"""
Collection of specialized plugin parsers for popular RPG Maker plugins.

Each parser handles the well-known parameter structure of a specific plugin
family so that extraction is deterministic rather than heuristic.

Adding a new parser:
1. Subclass PluginParser and implement get_plugin_names() + extract_parameters().
2. Register an instance in _PLUGIN_PARSERS at the bottom of this file.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .plugin_base import PluginParser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _safe_str(value: Any) -> str | None:
    """Return stripped string or None for non-string / blank values."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _parse_json_value(value: Any) -> Any | None:
    """Try to parse a string as JSON; return None on failure."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    if s and s[0] in ('{', '['):
        try:
            return json.loads(s)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _is_technical(value: str) -> bool:
    """Quick heuristic: purely symbolic / code-like strings are not translatable."""
    if not value:
        return False
    v = value.strip()
    # JavaScript function-body indicators — match regardless of string length.
    # These appear in VisuMZ ':func' parameters and must never be translated.
    # NOTE: Ambiguous English words (let, return, this., function) are checked
    # via syntax-aware regexes below to avoid false positives on dialogue text
    # like "let me help" or "return to base".
    js_unambiguous = ('const ', 'var ', '=>', '//')
    if any(kw in v for kw in js_unambiguous):
        return True
    # Ambiguous keywords: require JS syntax context
    js_ambiguous_patterns = [
        r'(?:^|[;\n{]\s*)return\s+[a-zA-Z_$]',     # return <identifier>
        r'(?:^|[;\n{]\s*)let\s+[a-zA-Z_$]\w*\s*[=;,\[]',  # let x = ...
        r'(?:^|[;\n{]\s*)function\s*\(',             # function(
        r'\bthis\.[a-zA-Z_$]\w*',                    # this.property
    ]
    if any(re.search(pat, v) for pat in js_ambiguous_patterns):
        return True
    if len(v) > 200:
        return False
    # JS expressions, function calls, numbers
    if re.search(r'[(){};]|^\d+$|^true$|^false$|^null$', v, re.IGNORECASE):
        return True
    # All caps + underscores identifier (e.g. SKILL_TYPE_MAGIC)
    if re.fullmatch(r'[A-Z][A-Z0-9_]{2,}', v):
        return True
    return False


def _looks_translatable(value: str, vocab_context: bool = False) -> bool:
    """Return True when a plain string value looks like player-visible text.
    
    Args:
        value: The string to check.
        vocab_context: If True, accept single capitalized words (Vocab entries like "Attack").
    """
    if not value or len(value.strip()) < 2:
        return False
    if _is_technical(value):
        return False
    # Has space or non-ASCII → likely text, but guard against known engine enum strings
    # that look like natural language (e.g. "All Enemies", "Slow Start") but are
    # technical identifiers used by RPG Maker scope/trigger/blend APIs (FP-15).
    if ' ' in value or any(ord(c) > 127 for c in value):
        # Cheap lowercase lookup against known RPG Maker enum strings
        _lower = value.strip().lower()
        _RPGM_ENUM_QUICK: frozenset[str] = frozenset({
            'none', 'one enemy', 'all enemies', 'one random enemy',
            'two random enemies', 'three random enemies', 'four random enemies',
            'one ally', 'all allies', 'one dead ally', 'all dead allies',
            'the user', 'all party members', 'all battle members',
            'action button', 'player touch', 'event touch', 'autorun', 'parallel',
            'map start', 'battle start', 'common event',
            'linear', 'slow start', 'slow end', 'constant',
            'instant', 'smooth', 'gradual',
            'normal', 'additive', 'multiply', 'screen', 'overlay',
            'hard mode', 'easy mode', 'normal mode',
            'hp rate', 'mp rate', 'tp rate',
            'gauge color 1', 'gauge color 2',
            'dash speed', 'screen x', 'screen y',
            'window skin', 'window color',
        })
        if _lower in _RPGM_ENUM_QUICK:
            return False
        return True
    # Single word: accept if vocab context and starts with uppercase (or short all-caps like "Exp", "TP")
    if vocab_context:
        s = value.strip()
        if re.fullmatch(r'[A-Z][a-z]{1,}', s):
            return True
        # Short all-caps abbreviations (2-4 chars) common in RPG Maker Vocab
        if re.fullmatch(r'[A-Z]{2,4}', s):
            return True
        # Mixed abbreviations like "M.Atk", "S.Param"
        if re.fullmatch(r'[A-Z][a-zA-Z.]{1,8}', s):
            return True
    # Short single word — conservative: skip unless clearly labelled
    return False


# ---------------------------------------------------------------------------
# YEP_QuestJournal  (Yanfly Engine Plugins)
# ---------------------------------------------------------------------------

class YEP_QuestJournalParser(PluginParser):
    """
    Yanfly Engine Plugins — Quest Journal System.

    Parameters ``"Quest 1"`` through ``"Quest 100"`` are JSON-stringified
    objects whose ``Description``, ``Objectives List``, ``Rewards List``, and
    ``Subtext`` fields are themselves JSON-stringified arrays of
    JSON-stringified strings (3 layers of serialization).

    The extraction uses multi-level ``@JSON`` paths so the generic
    ``_apply_nested_json_translation`` mechanism handles re-serialization
    automatically::

        prefix.Quest 1.@JSON.Title             → direct string
        prefix.Quest 1.@JSON.Description.@JSON.0.@JSON → triple-nested text
    """

    # Top-level parameters with directly translatable text
    _TEXT_PARAMS = frozenset({
        'Available Text', 'Completed Text', 'Failed Text', 'All Text',
        'Cancel Text', 'Read Quest', 'Cancel',
        'No Data Text', 'Quest Data Format', 'No Quest Title',
        'Quest Completed Text', 'Quest Failed Text', 'Quest Available Text',
        'Category Window Text',
    })

    # Parameters that are pure numeric, symbolic, or structural identifiers
    _SKIP_PARAMS = frozenset({
        'Quest Order', 'Category Order', 'Quest Switch',
        'Quest Key', 'Category Key',
        # Window / dimension settings
        'Window Settings', 'Category Window', 'List Window',
        'Title Window', 'Data Window', 'Lunatic Mode',
    })

    # Fields inside a quest JSON object that contain translatable text
    _QUEST_TEXT_FIELDS = frozenset({
        'Title', 'Description', 'Objectives List', 'Rewards List', 'Subtext',
    })

    # Quest fields that may be translatable (locations, names)
    # NOTE: 'Type' was removed — it maps to "type" which is in NON_TRANSLATABLE_EXACT_KEYS,
    # so extracted values were always silently dropped at write-time, producing noisy log spam.
    _QUEST_LABEL_FIELDS = frozenset({
        'From', 'Location',
    })

    # Quest fields that are arrays needing inner JSON parsing
    _QUEST_ARRAY_FIELDS = frozenset({
        'Description', 'Objectives List', 'Rewards List', 'Subtext',
    })

    def get_plugin_names(self) -> list[str]:
        return ['YEP_QuestJournal']

    def extract_parameters(self, parameters: dict[str, Any], path_prefix: str) -> list[tuple[str, str, str]]:
        results: list[tuple[str, str, str]] = []
        for key, value in parameters.items():
            if key in self._SKIP_PARAMS:
                continue

            # "Quest N" keys contain JSON-stringified quest objects
            if re.match(r'Quest \d+$', key):
                self._extract_quest_object(key, value, path_prefix, results)
                continue

            # "Type Order" is a JSON array of translatable quest type names
            if key == 'Type Order':
                self._extract_json_string_array(key, value, path_prefix, results)
                continue

            # Standard top-level text parameters
            text = _safe_str(value)
            if text is None:
                continue
            if key in self._TEXT_PARAMS or any(
                hint in key for hint in ('Name', 'Text', 'Desc', 'Title')
            ):
                if _looks_translatable(text) or '\n' in text:
                    results.append((f"{path_prefix}.{key}", text, "dialogue_block"))
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_quest_object(
        self,
        key: str,
        value: Any,
        path_prefix: str,
        results: list[tuple[str, str, str]],
    ) -> None:
        """Parse a ``Quest N`` JSON-stringified object and extract text fields."""
        raw = _safe_str(value)
        if raw is None:
            return
        try:
            quest = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(quest, dict):
            return

        quest_path = f"{path_prefix}.{key}"

        for field, field_value in quest.items():
            if not isinstance(field_value, str):
                continue
            field_str = field_value.strip()
            if not field_str:
                continue

            # Array fields (Description, Objectives, etc.): double-nested JSON
            if field in self._QUEST_ARRAY_FIELDS:
                self._extract_quest_array_field(
                    field, field_str, quest_path, results,
                )
                continue

            # Direct text fields (Title)
            if field in self._QUEST_TEXT_FIELDS:
                clean = self._strip_yep_text_codes(field_str)
                if _looks_translatable(clean, vocab_context=True) or ' ' in clean:
                    results.append(
                        (f"{quest_path}.@JSON.{field}", field_str, "ui_label"),
                    )
                continue

            # Label fields (Type, From, Location)
            if field in self._QUEST_LABEL_FIELDS:
                clean = self._strip_yep_text_codes(field_str)
                if _looks_translatable(clean, vocab_context=True) or ' ' in clean:
                    results.append(
                        (f"{quest_path}.@JSON.{field}", field_str, "ui_label"),
                    )

    def _extract_quest_array_field(
        self,
        field: str,
        value: str,
        quest_path: str,
        results: list[tuple[str, str, str]],
    ) -> None:
        """Extract text from a quest array field (triple-nested JSON).

        Array elements are JSON-stringified strings (e.g. ``'"text"'``).
        We use ``.@JSON`` at each nesting level so the apply phase
        re-serializes correctly.
        """
        try:
            arr = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(arr, list):
            return

        for i, item in enumerate(arr):
            if not isinstance(item, str) or not item.strip():
                continue
            # Each item is a JSON-encoded string: '"actual text"'
            try:
                text = json.loads(item)
            except (json.JSONDecodeError, ValueError):
                # Fallback: use item directly if JSON parsing fails
                text = item.strip().strip('"')
            if not isinstance(text, str) or not text.strip():
                continue
            if _looks_translatable(text) or '\n' in text or '\\n' in text:
                # Triple @JSON path: Quest N → array field → element → decoded string
                results.append(
                    (f"{quest_path}.@JSON.{field}.@JSON.{i}.@JSON", text, "dialogue_block"),
                )

    def _extract_json_string_array(
        self,
        key: str,
        value: Any,
        path_prefix: str,
        results: list[tuple[str, str, str]],
    ) -> None:
        """Extract translatable strings from a JSON array parameter."""
        raw = _safe_str(value)
        if raw is None:
            return
        try:
            arr = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(arr, list):
            return
        for i, item in enumerate(arr):
            if isinstance(item, str) and item.strip():
                clean = self._strip_yep_text_codes(item.strip())
                if _looks_translatable(clean, vocab_context=True) or ' ' in clean:
                    # @JSON marks that the value was parsed from a JSON string so the
                    # apply phase re-serializes it correctly via _apply_nested_json_translation.
                    results.append(
                        (f"{path_prefix}.{key}.@JSON.{i}", item.strip(), "ui_label"),
                    )

    @staticmethod
    def _strip_yep_text_codes(text: str) -> str:
        """Remove RPG Maker text codes for heuristic checks."""
        return re.sub(r'\\+[a-zA-Z]\[[^\]]*\]', '', text).strip()


# ---------------------------------------------------------------------------
# YEP_MessageCore  (Yanfly Engine Plugins)
# ---------------------------------------------------------------------------

class YEP_MessageCoreParser(PluginParser):
    """
    Yanfly Engine Plugins — Message Core.

    This plugin mainly stores UI configuration; very few parameters are
    player-visible text. We cherry-pick only the known text parameters
    to avoid extracting font names, JS expressions, etc.
    """

    _TEXT_PARAMS = frozenset({
        'Default Help Text', 'Closing Key',
    })

    _SKIP_PARAMS = frozenset({
        'Message Rows', 'Message Width', 'Message Speed Display',
        'Message Speed', 'Message Font Size', 'Font Changed Color',
        'Font Name', 'Font Size', 'Fast Forward Key',
        'Enable Word Wrap', 'Word Wrap Space', 'Default WordWrap',
    })

    def get_plugin_names(self) -> list[str]:
        return ['YEP_MessageCore', 'YEP_X_MessageMacros1', 'YEP_X_MessageMacros2',
                'YEP_X_MessageMacros3', 'YEP_X_MessageMacros4', 'YEP_X_MessageMacros5']

    def extract_parameters(self, parameters: dict[str, Any], path_prefix: str) -> list[tuple[str, str, str]]:
        results: list[tuple[str, str, str]] = []
        for key, value in parameters.items():
            if key in self._SKIP_PARAMS:
                continue
            if key in self._TEXT_PARAMS:
                text = _safe_str(value)
                if text and _looks_translatable(text):
                    results.append((f"{path_prefix}.{key}", text, "dialogue_block"))
            # Macro content keys (MacroN Text)
            elif re.match(r'^Macro\d+ Text$', key):
                text = _safe_str(value)
                if text and (_looks_translatable(text) or '\n' in text):
                    results.append((f"{path_prefix}.{key}", text, "dialogue_block"))
        return results


# ---------------------------------------------------------------------------
# VisuMZ_1_MessageCore  (VisuStella MZ)
# ---------------------------------------------------------------------------

class VisuMZ_MessageCoreParser(PluginParser):
    """
    VisuStella MZ — Message Core (VisuMZ_1_MessageCore).

    Parameters are deeply nested JSON structs.  We extract known
    Vocab/Text-containing paths and skip technical config blocks.
    """

    # Top-level parameter keys that contain player-visible text structs
    _TEXT_STRUCT_KEYS = frozenset({
        'Vocab', 'TextMacros', 'TextSpeed',
    })

    # Keys inside structs that are text values
    _INNER_TEXT_KEYS = frozenset({
        'PreloadFiles', 'AutoColor', 'CustomFonts',
        'TextCodeActions', 'TextCodeReplace',
    })

    def get_plugin_names(self) -> list[str]:
        return [
            'VisuMZ_1_MessageCore',
            'VisuMZ_0_CoreEngine',   # Vocab section has player-visible strings
        ]

    def extract_parameters(self, parameters: dict[str, Any], path_prefix: str) -> list[tuple[str, str, str]]:
        results: list[tuple[str, str, str]] = []
        for key, value in parameters.items():
            parsed = _parse_json_value(value)
            if parsed is not None:
                self._walk_struct(parsed, f"{path_prefix}.{key}", results, depth=0)
            elif isinstance(value, str):
                text = _safe_str(value)
                if text and self._key_is_text(key) and _looks_translatable(text, vocab_context=True):
                    results.append((f"{path_prefix}.{key}", text, "dialogue_block"))
        return results

    def _key_is_text(self, key: str) -> bool:
        # Code suffix keys always store JavaScript/formula bodies — never translatable.
        _code_suffixes = (':func', ':eval', ':json', ':code', ':js')
        if any(key.endswith(s) for s in _code_suffixes):
            return False
        key_lower = key.lower()
        return any(h in key_lower for h in ('text', 'name', 'label', 'vocab', 'desc', 'title', 'msg'))

    def _walk_struct(self, obj: Any, path: str, results: list, depth: int) -> None:
        if depth > 10:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                child_path = f"{path}.{k}"
                parsed = _parse_json_value(v)
                if parsed is not None:
                    self._walk_struct(parsed, f"{child_path}.@JSON", results, depth + 1)
                elif isinstance(v, str):
                    text = _safe_str(v)
                    if text and self._key_is_text(k) and _looks_translatable(text, vocab_context=('vocab' in path.lower())):
                        results.append((child_path, text, "dialogue_block"))
                elif isinstance(v, (dict, list)):
                    self._walk_struct(v, child_path, results, depth + 1)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                child_path = f"{path}.{i}"
                parsed = _parse_json_value(item)
                if parsed is not None:
                    self._walk_struct(parsed, f"{child_path}.@JSON", results, depth + 1)
                elif isinstance(item, str):
                    text = _safe_str(item)
                    if text:
                        # FP-16: Skip list items whose parent key context strongly suggests
                        # an enum / option-list (non-translatable identifiers like scope lists,
                        # trigger lists, blend mode option arrays).
                        parent_key = path.rsplit('.', 1)[-1].lower() if '.' in path else path.lower()
                        _ENUM_PARENT_KEYS = frozenset({
                            'scope', 'trigger', 'target', 'blend', 'blendmode',
                            'motion', 'overlay', 'condition', 'elements', 'types',
                            'scopelist', 'triggerlist', 'targetlist', 'modelist',
                        })
                        if parent_key in _ENUM_PARENT_KEYS and _looks_translatable(text) and not any(ord(c) > 127 for c in text):
                            continue  # All-ASCII list items in enum-key context → skip
                        if _looks_translatable(text):
                            results.append((child_path, text, "dialogue_block"))
                elif isinstance(item, (dict, list)):
                    self._walk_struct(item, child_path, results, depth + 1)


# ---------------------------------------------------------------------------
# VisuMZ_1_ItemsEquipsCore  (VisuStella MZ)
# ---------------------------------------------------------------------------

class VisuMZ_ItemsEquipsCoreParser(PluginParser):
    """
    VisuStella MZ — Items & Equips Core.

    Contains Vocab parameters (UI labels) plus numeric/boolean config.
    We extract only the Vocab struct and known text parameters.
    """

    # Code-suffix keys whose values are structured data, not player text.
    _CODE_SUFFIXES = (':func', ':eval', ':json', ':code', ':js')

    def get_plugin_names(self) -> list[str]:
        return ['VisuMZ_1_ItemsEquipsCore']

    def extract_parameters(self, parameters: dict[str, Any], path_prefix: str) -> list[tuple[str, str, str]]:
        results: list[tuple[str, str, str]] = []
        for key, value in parameters.items():
            # Skip code-suffix keys (e.g. "ItemQuantityFmt:func")
            if any(key.endswith(s) for s in self._CODE_SUFFIXES):
                continue
            # Vocab struct — all string values inside are UI labels
            if key in ('Vocab', 'StatusWindow', 'ButtonAssist'):
                parsed = _parse_json_value(value)
                if parsed and isinstance(parsed, dict):
                    for vk, vv in parsed.items():
                        text = _safe_str(vv)
                        if text and _looks_translatable(text, vocab_context=True):
                            results.append((f"{path_prefix}.{key}.{vk}", text, "system"))
            elif isinstance(value, str):
                text = _safe_str(value)
                if text and any(h in key.lower() for h in ('text', 'label', 'name', 'vocab')):
                    if _looks_translatable(text, vocab_context=True):
                        results.append((f"{path_prefix}.{key}", text, "system"))
        return results


# ---------------------------------------------------------------------------
# CGMZ_Achievements  (CGMZ plugin suite)
# ---------------------------------------------------------------------------

class CGMZ_AchievementsParser(PluginParser):
    """
    CGMZ — Achievements plugin.

    Parameters include achievement name, description, and toast notification
    text — all player-visible.  Configuration numbers/switches are skipped.
    """

    _TEXT_KEYS = frozenset({
        'Name', 'Description', 'Toast Text', 'Reward Description',
        'Popup Text', 'Secret Description', 'Fail Description',
    })
    _SKIP_KEYS = frozenset({
        'Switch', 'Variable', 'Category', 'Points', 'Difficulty',
        'Automatic', 'Secret',
    })

    def get_plugin_names(self) -> list[str]:
        return ['CGMZ_Achievements', 'CGMZ_Achievement']

    def extract_parameters(self, parameters: dict[str, Any], path_prefix: str) -> list[tuple[str, str, str]]:
        results: list[tuple[str, str, str]] = []
        for key, value in parameters.items():
            if key in self._SKIP_KEYS:
                continue
            parsed = _parse_json_value(value)
            if parsed is not None:
                # Array of achievement objects
                if isinstance(parsed, list):
                    for i, item in enumerate(parsed):
                        item_parsed = _parse_json_value(item) if isinstance(item, str) else item
                        if isinstance(item_parsed, dict):
                            self._extract_achievement(item_parsed, f"{path_prefix}.{key}.{i}", results)
                elif isinstance(parsed, dict):
                    self._extract_achievement(parsed, f"{path_prefix}.{key}", results)
            elif isinstance(value, str) and key in self._TEXT_KEYS:
                text = _safe_str(value)
                if text and _looks_translatable(text):
                    results.append((f"{path_prefix}.{key}", text, "dialogue_block"))
        return results

    def _extract_achievement(self, obj: dict, path: str, results: list) -> None:
        for k, v in obj.items():
            if k in self._SKIP_KEYS:
                continue
            text = _safe_str(v)
            if text and (k in self._TEXT_KEYS or any(h in k for h in ('Name', 'Desc', 'Text'))):
                if _looks_translatable(text) or '\n' in text:
                    results.append((f"{path}.{k}", text, "dialogue_block"))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_PLUGIN_PARSERS: list[PluginParser] = [
    YEP_QuestJournalParser(),
    YEP_MessageCoreParser(),
    VisuMZ_MessageCoreParser(),
    VisuMZ_ItemsEquipsCoreParser(),
    CGMZ_AchievementsParser(),
]


def get_specialized_parser(plugin_name: str) -> PluginParser | None:
    """Find a specialized parser for the given plugin name."""
    for parser in _PLUGIN_PARSERS:
        if plugin_name in parser.get_plugin_names():
            return parser
    return None
