"""
Restricted Ruby Marshal Unmarshaller (RCE Protection)
=====================================================

Protects RPG Maker XP/VX/VX Ace binary data files (.rxdata, .rvdata, .rvdata2)
against Arbitrary Code Execution (RCE) during Marshal deserialization by enforcing
a strict class allowlist.
"""
from __future__ import annotations

import logging
from typing import Any, Set

logger = logging.getLogger("RestrictedRubyUnmarshaller")

# Strict allowlist of safe RPG Maker classes and RGSS builtin types
SAFE_RPG_CLASSES: Set[str] = {
    # RPG Maker Core Data Classes
    "RPG::Actor",
    "RPG::Class",
    "RPG::Class::Learning",
    "RPG::Skill",
    "RPG::Item",
    "RPG::Weapon",
    "RPG::Armor",
    "RPG::Enemy",
    "RPG::Enemy::Action",
    "RPG::State",
    "RPG::Troop",
    "RPG::Troop::Member",
    "RPG::Troop::Page",
    "RPG::Troop::Page::Condition",
    "RPG::Animation",
    "RPG::Animation::Frame",
    "RPG::Animation::Timing",
    "RPG::Tileset",
    "RPG::CommonEvent",
    "RPG::System",
    "RPG::System::Words",
    "RPG::System::Terms",
    "RPG::System::TestBattler",
    "RPG::System::Vehicle",
    "RPG::Map",
    "RPG::MapInfo",
    "RPG::Event",
    "RPG::Event::Page",
    "RPG::Event::Page::Condition",
    "RPG::Event::Page::Graphic",
    "RPG::EventCommand",
    "RPG::MoveRoute",
    "RPG::MoveCommand",
    "RPG::AudioFile",
    "RPG::BGM",
    "RPG::BGS",
    "RPG::ME",
    "RPG::SE",
    "RPG::BaseItem",
    "RPG::BaseItem::Feature",
    "RPG::UsableItem",
    "RPG::UsableItem::Damage",
    "RPG::UsableItem::Effect",
    "RPG::EquipItem",

    # RGSS Built-in Graphics/Data Structures
    "Table",
    "Color",
    "Tone",
    "Rect",
    "Tone",
}


class RubyDeserializationSecurityError(RuntimeError):
    """Raised when an unapproved class is encountered during Ruby Marshal unmarshalling."""
    pass


def validate_ruby_class_name(class_name: str) -> bool:
    """Check if the Ruby class name is within the allowed safe list.

    Allows standard RPG Maker structures and primitive wrappers,
    while blocking execution vectors like File, Process, IO, Kernel.
    """
    if not class_name:
        return False

    clean_name = class_name.strip()

    # Exact match in safe classes
    if clean_name in SAFE_RPG_CLASSES:
        return True

    # Block well-known exploit gadgets explicitly
    dangerous_roots = ("Kernel", "Process", "File", "IO", "Dir", "Open3", "System", "Eval", "Gem")
    if any(clean_name == root or clean_name.startswith(f"{root}::") for root in dangerous_roots):
        logger.error("RCE Blocked: Attempted deserialization of dangerous Ruby class: %s", clean_name)
        return False

    # Default reject unknown classes to prevent arbitrary object instantiation
    logger.warning("Unrecognized Ruby class encountered: %s", clean_name)
    return False


def assert_safe_ruby_class(class_name: str) -> None:
    """Raise RubyDeserializationSecurityError if class_name is not allowed."""
    if not validate_ruby_class_name(class_name):
        raise RubyDeserializationSecurityError(
            f"Blocked unauthorized Ruby Marshal class deserialization: {class_name}"
        )
