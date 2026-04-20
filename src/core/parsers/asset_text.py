from pathlib import PurePosixPath
import os
import re
import urllib.parse
from typing import Set


def normalize_asset_text(text: str) -> str:
    """Normalize a candidate asset string for path checks."""
    if not isinstance(text, str):
        return ""

    cleaned = text.strip().strip('"\'')
    if not cleaned:
        return ""

    cleaned = cleaned.split("#", 1)[0].split("?", 1)[0]

    decoded = cleaned
    for _ in range(2):
        next_decoded = urllib.parse.unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded

    decoded = decoded.replace("\\", "/")
    decoded = re.sub(r"/{2,}", "/", decoded)
    return decoded


def fuzzy_asset_normalize(text: str) -> str:
    """Super-aggressive normalization for asset matching (strips spaces, underscores, dashes)."""
    return text.replace(" ", "").replace("_", "").replace("-", "").lower()


def contains_explicit_asset_reference(text: str, asset_file_extensions: tuple[str, ...]) -> bool:
    """Return True when text clearly references a real file or asset path."""
    if not isinstance(text, str):
        return False

    cleaned = normalize_asset_text(text)
    if not cleaned:
        return False

    lower_text = cleaned.lower()
    if any(lower_text.endswith(ext) for ext in asset_file_extensions):
        return True

    if re.search(
        r"(?i)(?:^|[\s\\\"'`(=,:])(?:img|audio|movies|fonts|js|data|pictures|faces|characters|battlers|tilesets|parallaxes|sv_actors|sv_enemies|battlebacks[12]?)[/\\]",
        cleaned,
    ):
        return True

    ext_pattern = "|".join(ext.lstrip(".") for ext in asset_file_extensions)
    embedded_pattern = (
        r"(?i)(?:^|[\s\\\"'`(=,:])"
        r"(?:[a-z]:[/\\])?"
        r"(?:[^/\\\r\n\"'`]+[/\\])*"
        r"[^/\\\r\n\"'`]+\.(?:" + ext_pattern + r")(?=$|[^a-zA-Z0-9_])"
    )
    return re.search(embedded_pattern, cleaned) is not None


def contains_asset_tuple_reference(text: str) -> bool:
    """Return True for asset-like values that include numeric coordinates or variants."""
    if not isinstance(text, str):
        return False

    cleaned = normalize_asset_text(text)
    if not cleaned:
        return False

    return re.fullmatch(r"(?i)[A-Za-z0-9_.\- /]+,\s*-?\d+,\s*-?\d+(?:,\s*-?\d+)?", cleaned) is not None


def asset_identifier_candidates(text: str) -> Set[str]:
    """Return normalized variants used to match real asset names."""
    normalized = normalize_asset_text(text).replace("\\", "/").lower()
    if not normalized:
        return set()

    path = PurePosixPath(normalized)
    candidates: Set[str] = set()

    def add_candidate(candidate: str) -> None:
        if not candidate:
            return
        candidates.add(candidate)
        # Add fuzzy variant
        fuzzy = fuzzy_asset_normalize(candidate)
        if fuzzy:
            candidates.add(fuzzy)

    add_candidate(normalized)
    add_candidate(path.name)

    stem = path.stem
    if stem:
        add_candidate(stem)

    without_suffix = path.with_suffix("").as_posix().lower() if path.suffix else normalized
    if without_suffix:
        add_candidate(without_suffix)

    basename = os.path.basename(normalized)
    if basename:
        add_candidate(basename)

    return candidates
