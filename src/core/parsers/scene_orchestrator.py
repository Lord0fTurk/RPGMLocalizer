"""
RPG Maker Scene & Dialogue Orchestrator (Scene Mode)
=====================================================

Groups consecutive Show Text (Code 101/401) event commands into cohesive
dialogue blocks and theatrical scenes for LLM context-aware translation.

Key Features:
- Bi-directional grouping: Code 101 (Speaker) + consecutive 401s into DialogueBlock.
- Theatrical Script formatting for LLM (### SCENE START ### / ### SCENE END ###).
- RPG Maker 4-line message box boundary enforcement & intelligent word reflow.
- Strict Multi-tier Fallback (Scene -> JSON -> Single entry).
- Strict non-translatable filter for script (355/655) & metadata (<meta:...>) tags.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# RPG Maker message box hard limits
DEFAULT_MAX_LINES_PER_BOX = 4
DEFAULT_MAX_CHARS_PER_LINE = 50
SCENE_START_MARKER = "### SCENE START ###"
SCENE_END_MARKER = "### SCENE END ###"

# Filters for technical / script strings
_SCRIPT_CALL_RE = re.compile(
    r'(?:\$game[A-Z]\w*|SceneManager|BattleManager|AudioManager|Input\.isTriggered|'
    r'DataManager|\.setValue\(|\.value\(|\.playSe\(|\.playBgm\(|function\s*\(|=>\s*\{)',
    re.IGNORECASE,
)
_NOTE_META_RE = re.compile(r'<meta:\s*[^>]+>|<[A-Za-z0-9_]+:[^>]*>', re.IGNORECASE)
NAME_TAG_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r'\\(?:n|N|nc|NC|nr|NR|name|NAME)<([^>]+)>'),
    re.compile(r'\\(?:n|N|nc|NC|nr|NR|name|NAME)\[([^\]]+)\]'),
]


@dataclass(slots=True)
class DialogueLine:
    """Individual line within an RPG Maker Show Text command."""
    path: str
    text: str
    code: int = 401


@dataclass(slots=True)
class DialogueBlock:
    """A cohesive dialogue message box associated with a Code 101 header."""
    speaker: str
    face_name: str
    lines: List[DialogueLine] = field(default_factory=list)
    speaker_path: Optional[str] = None
    box_id: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def full_dialogue(self) -> str:
        """Join all dialogue lines into a single coherent paragraph."""
        return "\n".join(l.text for l in self.lines)

    def get_full_text(self) -> str:
        """Join dialogue lines into a single text for theatrical representation."""
        return " ".join(l.text for l in self.lines)


@dataclass(slots=True)
class TheatricalScene:
    """A sequential series of dialogue blocks within an event page."""
    scene_id: str
    blocks: List[DialogueBlock] = field(default_factory=list)
    context_hint: str = ""


# ---------------------------------------------------------------------------
# Filter and Safety Checks
# ---------------------------------------------------------------------------
def is_safe_dialogue_text(text: str) -> bool:
    """Check if dialogue text is safe to translate, rejecting scripts and raw meta tags."""
    if not text or not text.strip():
        return False

    stripped = text.strip()

    # Reject direct JS / Ruby script calls
    if _SCRIPT_CALL_RE.search(stripped):
        return False

    # Reject strict note meta tags
    if _NOTE_META_RE.fullmatch(stripped):
        return False

    # Reject code-only lines
    if stripped.startswith("/*") and stripped.endswith("*/"):
        return False

    return True


# ---------------------------------------------------------------------------
# Grouping Engine (Code 101 + 401 Chain)
# ---------------------------------------------------------------------------
def _flush_block_if_any(current_block: Optional[DialogueBlock], blocks: List[DialogueBlock]) -> None:
    """Commit current dialogue block to blocks list if non-empty."""
    if current_block and current_block.lines:
        blocks.append(current_block)


def _create_dialogue_header_block(cmd: Dict[str, Any], cmd_path: str, box_id: int) -> DialogueBlock:
    """Create a new DialogueBlock from a Show Text header (Code 101)."""
    params = cmd.get("parameters", [])
    face = str(params[0]) if len(params) > 0 and params[0] else ""
    speaker = ""
    speaker_path = None

    if len(params) >= 5 and isinstance(params[4], str) and params[4].strip():
        speaker = params[4].strip()
        speaker_path = f"{cmd_path}.parameters.4"

    return DialogueBlock(
        speaker=speaker,
        face_name=face,
        speaker_path=speaker_path,
        box_id=box_id,
    )


def _append_dialogue_line(
    cmd: Dict[str, Any],
    cmd_path: str,
    current_block: Optional[DialogueBlock],
    box_id: int,
) -> DialogueBlock:
    """Append Code 401 text to current_block, extracting name tags if speaker is missing."""
    params = cmd.get("parameters", [])
    line_text = params[0] if len(params) > 0 and isinstance(params[0], str) else ""
    line_path = f"{cmd_path}.parameters.0"

    block = current_block or DialogueBlock(speaker="", face_name="", box_id=box_id)

    if not block.speaker:
        extracted_name, cleaned_text = _extract_name_tags(line_text)
        if extracted_name:
            block.speaker = extracted_name
            line_text = cleaned_text

    block.lines.append(DialogueLine(path=line_path, text=line_text, code=401))
    return block


def group_event_commands(
    commands: Sequence[Dict[str, Any]],
    base_path: str = "",
) -> List[DialogueBlock]:
    """Scan event command sequence and group consecutive 101/401 commands into DialogueBlocks."""
    blocks: List[DialogueBlock] = []
    current_block: Optional[DialogueBlock] = None
    box_counter = 0

    for idx, cmd in enumerate(commands):
        if not isinstance(cmd, dict):
            continue

        code = cmd.get("code")
        cmd_path = f"{base_path}.{idx}" if base_path else str(idx)

        if code == 101:
            _flush_block_if_any(current_block, blocks)
            current_block = _create_dialogue_header_block(cmd, cmd_path, box_counter)
            box_counter += 1
        elif code == 401:
            if not current_block:
                current_block = _append_dialogue_line(cmd, cmd_path, None, box_counter)
                box_counter += 1
            else:
                _append_dialogue_line(cmd, cmd_path, current_block, box_counter)
        elif code in (102, 108, 111, 118, 119, 201, 230, 231, 355, 356, 357):
            _flush_block_if_any(current_block, blocks)
            current_block = None

    _flush_block_if_any(current_block, blocks)
    return blocks


def _extract_name_tags(text: str) -> Tuple[str, str]:
    """Extract embedded nameplate tags like \\n<Harold> or \\NC<Harold> from line text."""
    for pattern in NAME_TAG_PATTERNS:
        match = pattern.search(text)
        if match:
            speaker_name = match.group(1).strip()
            cleaned_text = pattern.sub("", text).strip()
            return speaker_name, cleaned_text
    return "", text


# ---------------------------------------------------------------------------
# Theatrical Script LLM Serialization & Deserialization
# ---------------------------------------------------------------------------
def format_scene_for_llm(blocks: Sequence[DialogueBlock]) -> str:
    """Format dialogue blocks into a theatrical script for LLM translation."""
    if not blocks:
        return ""

    lines: List[str] = [SCENE_START_MARKER]
    for block in blocks:
        speaker_label = block.speaker if block.speaker else "Narrator"
        utterance = block.get_full_text()
        lines.append(f"[{block.box_id}] {speaker_label}: {utterance}")

    lines.append(SCENE_END_MARKER)
    return "\n".join(lines)


def _extract_translated_utterances(
    llm_output: str,
    orig_map: Dict[int, DialogueBlock],
) -> Dict[int, str]:
    """Extract mapping of box_id -> translated text from LLM script output."""
    utterances: Dict[int, str] = {}
    line_pattern = re.compile(r'^\[(\d+)\]\s*([^:]*?)\s*:\s*(.*)$', re.MULTILINE)
    for m in line_pattern.finditer(llm_output):
        try:
            box_id = int(m.group(1))
            utterance = m.group(3).strip()
            if box_id in orig_map:
                utterances[box_id] = utterance
        except (ValueError, IndexError):
            continue
    return utterances


def _reconstruct_dialogue_block(orig: DialogueBlock, trans_text: str) -> DialogueBlock:
    """Reflow translated text and build a new DialogueBlock preserving structure."""
    max_lines = len(orig.lines) if orig.lines else DEFAULT_MAX_LINES_PER_BOX
    reflowed_lines = reflow_dialogue_to_rpgm_boxes(trans_text, max_lines_per_box=max_lines)

    new_lines: List[DialogueLine] = []
    for i, line_str in enumerate(reflowed_lines):
        target_path = orig.lines[i].path if i < len(orig.lines) else f"{orig.lines[-1].path}_{i}"
        new_lines.append(DialogueLine(path=target_path, text=line_str, code=401))

    while len(new_lines) < len(orig.lines):
        idx = len(new_lines)
        new_lines.append(DialogueLine(path=orig.lines[idx].path, text="", code=401))

    return DialogueBlock(
        speaker=orig.speaker,
        face_name=orig.face_name,
        lines=new_lines,
        speaker_path=orig.speaker_path,
        box_id=orig.box_id,
        metadata=orig.metadata,
    )


def parse_scene_from_llm(
    llm_output: str,
    original_blocks: Sequence[DialogueBlock],
) -> List[DialogueBlock]:
    """Parse LLM theatrical script output back into structured DialogueBlocks with fallback."""
    if not llm_output or not original_blocks:
        return list(original_blocks)

    orig_map = {b.box_id: b for b in original_blocks}
    translated = _extract_translated_utterances(llm_output, orig_map)

    return [
        _reconstruct_dialogue_block(orig, translated[orig.box_id])
        if orig.box_id in translated else orig
        for orig in original_blocks
    ]


# ---------------------------------------------------------------------------
# RPG Maker 4-Line Message Box Reflow
# ---------------------------------------------------------------------------
def reflow_dialogue_to_rpgm_boxes(
    text: str,
    max_lines_per_box: int = DEFAULT_MAX_LINES_PER_BOX,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
) -> List[str]:
    """Split and reflow translated text across message box lines without breaking words."""
    if not text:
        return [""]

    # If text already contains explicit line breaks and fits limits, preserve them
    initial_lines = [l.strip() for l in text.split("\n") if l.strip()]
    if 1 <= len(initial_lines) <= max_lines_per_box:
        if all(len(l) <= max_chars_per_line * 1.3 for l in initial_lines):
            return initial_lines

    words = text.split()
    if not words:
        return [""]

    fitted_lines: List[str] = []
    current_line: List[str] = []
    current_len = 0

    for word in words:
        word_len = len(word)
        if current_line and (current_len + 1 + word_len) > max_chars_per_line:
            fitted_lines.append(" ".join(current_line))
            current_line = [word]
            current_len = word_len
        else:
            current_line.append(word)
            current_len += (word_len + 1) if current_line else word_len

    if current_line:
        fitted_lines.append(" ".join(current_line))

    # Cap lines at max_lines_per_box; combine excess onto the last line if necessary
    if len(fitted_lines) > max_lines_per_box:
        prefix = fitted_lines[:max_lines_per_box - 1]
        remainder = " ".join(fitted_lines[max_lines_per_box - 1:])
        prefix.append(remainder)
        return prefix

    return fitted_lines
