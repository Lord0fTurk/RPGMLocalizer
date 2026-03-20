"""
Structured field rules for safe RPG Maker JSON extraction.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import TypeAlias


SelectorToken: TypeAlias = str | int


@dataclass(frozen=True, slots=True)
class FieldRule:
    """A deterministic field selector for player-visible JSON text."""

    selector: tuple[SelectorToken, ...]
    tag: str
    is_dialogue: bool = False


@dataclass(frozen=True, slots=True)
class EventCommandRule:
    """A deterministic selector for player-visible RPG Maker event command text."""

    code: int
    parameter_path: tuple[SelectorToken, ...]
    tag: str
    is_dialogue: bool = True


STRUCTURED_DATABASE_FILENAMES = frozenset(
    {
        "actors.json",
        "animations.json",
        "armors.json",
        "classes.json",
        "commonevents.json",
        "enemies.json",
        "items.json",
        "mapinfos.json",
        "qsprite.json",
        "skills.json",
        "states.json",
        "system.json",
        "tilesets.json",
        "troops.json",
        "weapons.json",
    }
)

PROTECTED_STRUCTURED_NOOP_FILENAMES = frozenset(
    {
        "animations.json",
        "mapinfos.json",
        "qsprite.json",
        "tilesets.json",
    }
)

STRUCTURED_MAP_PATTERN = re.compile(r"^map\d+\.json$", re.IGNORECASE)


DATABASE_FIELD_RULES: dict[str, tuple[FieldRule, ...]] = {
    "actors.json": (
        FieldRule(("*", "name"), "name"),
        FieldRule(("*", "nickname"), "name"),
        FieldRule(("*", "profile"), "dialogue_block", is_dialogue=True),
    ),
    "classes.json": (
        FieldRule(("*", "name"), "name"),
    ),
    "skills.json": (
        FieldRule(("*", "name"), "name"),
        FieldRule(("*", "description"), "dialogue_block", is_dialogue=True),
        FieldRule(("*", "message1"), "dialogue_block", is_dialogue=True),
        FieldRule(("*", "message2"), "dialogue_block", is_dialogue=True),
    ),
    "items.json": (
        FieldRule(("*", "name"), "name"),
        FieldRule(("*", "description"), "dialogue_block", is_dialogue=True),
        FieldRule(("*", "message1"), "dialogue_block", is_dialogue=True),
        FieldRule(("*", "message2"), "dialogue_block", is_dialogue=True),
    ),
    "weapons.json": (
        FieldRule(("*", "name"), "name"),
        FieldRule(("*", "description"), "dialogue_block", is_dialogue=True),
    ),
    "armors.json": (
        FieldRule(("*", "name"), "name"),
        FieldRule(("*", "description"), "dialogue_block", is_dialogue=True),
    ),
    "enemies.json": (
        FieldRule(("*", "name"), "name"),
    ),
    "states.json": (
        FieldRule(("*", "name"), "name"),
        FieldRule(("*", "message1"), "dialogue_block", is_dialogue=True),
        FieldRule(("*", "message2"), "dialogue_block", is_dialogue=True),
        FieldRule(("*", "message3"), "dialogue_block", is_dialogue=True),
        FieldRule(("*", "message4"), "dialogue_block", is_dialogue=True),
    ),
    "system.json": (
        FieldRule(("gameTitle",), "name"),
        FieldRule(("currencyUnit",), "name"),
        FieldRule(("terms", "basic", "*"), "system", is_dialogue=True),
        FieldRule(("terms", "commands", "*"), "system", is_dialogue=True),
        FieldRule(("terms", "params", "*"), "system", is_dialogue=True),
        FieldRule(("terms", "messages", "*"), "system", is_dialogue=True),
        FieldRule(("terms", "types", "*"), "system", is_dialogue=True),
        FieldRule(("elements", "*"), "system", is_dialogue=True),
        FieldRule(("skillTypes", "*"), "system", is_dialogue=True),
        FieldRule(("weaponTypes", "*"), "system", is_dialogue=True),
        FieldRule(("armorTypes", "*"), "system", is_dialogue=True),
        FieldRule(("equipTypes", "*"), "system", is_dialogue=True),
        FieldRule(("etypeNames", "*"), "system", is_dialogue=True),
        FieldRule(("stypeNames", "*"), "system", is_dialogue=True),
        FieldRule(("wtypeNames", "*"), "system", is_dialogue=True),
        FieldRule(("atypeNames", "*"), "system", is_dialogue=True),
    ),
}

MAP_FIELD_RULES: tuple[FieldRule, ...] = (
    FieldRule(("displayName",), "name"),
)

EVENT_COMMAND_RULES: dict[int, EventCommandRule] = {
    101: EventCommandRule(101, (4,), "name"),
    102: EventCommandRule(102, (0, "*"), "choice"),
    105: EventCommandRule(105, (2,), "system"),
    320: EventCommandRule(320, (1,), "name"),
    324: EventCommandRule(324, (1,), "name"),
    325: EventCommandRule(325, (1,), "name"),
    401: EventCommandRule(401, (0,), "message_dialogue"),
    402: EventCommandRule(402, (1,), "choice"),
    405: EventCommandRule(405, (0,), "message_dialogue"),
}


def is_structured_json_file(file_path: str) -> bool:
    """Return True when the file can use deterministic structured extraction."""
    basename = os.path.basename(file_path).lower()
    return basename in STRUCTURED_DATABASE_FILENAMES or STRUCTURED_MAP_PATTERN.match(basename) is not None


def get_field_rules_for_file(file_path: str) -> tuple[FieldRule, ...]:
    """Return path rules for a specific RPG Maker JSON file."""
    basename = os.path.basename(file_path).lower()
    if STRUCTURED_MAP_PATTERN.match(basename):
        return MAP_FIELD_RULES
    return DATABASE_FIELD_RULES.get(basename, ())


def get_event_command_rule(code: int) -> EventCommandRule | None:
    """Return the structured extraction rule for an event command code."""
    return EVENT_COMMAND_RULES.get(code)


def is_protected_structured_noop_file(file_path: str) -> bool:
    """Return True when the structured surface is intentionally extraction-free."""
    return os.path.basename(file_path).lower() in PROTECTED_STRUCTURED_NOOP_FILENAMES
