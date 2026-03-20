"""
Technical invariant verification for structured translation surfaces.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Set


@dataclass(frozen=True, slots=True)
class InvariantViolation:
    """A changed path outside the translator's allowed surface."""

    path: str
    reason: str


class JsonTechnicalInvariantVerifier:
    """Verify that structured translation only mutates approved JSON paths."""

    def __init__(self, escape_path_key: Callable[[str], str]) -> None:
        self._escape_path_key = escape_path_key

    def build_allowed_paths(self, translation_paths: Iterable[str]) -> Set[str]:
        """Normalize translation keys into concrete writable JSON leaf paths."""
        allowed_paths: Set[str] = set()
        for path in translation_paths:
            allowed_paths.update(self._normalize_translation_path(path))
        return allowed_paths

    def find_unexpected_changes(
        self,
        original: Any,
        updated: Any,
        allowed_paths: Set[str],
    ) -> List[InvariantViolation]:
        """Return all structural or scalar changes outside the approved path set."""
        violations: List[InvariantViolation] = []
        self._walk_differences(original, updated, "", allowed_paths, violations)
        return violations

    def _walk_differences(
        self,
        original: Any,
        updated: Any,
        current_path: str,
        allowed_paths: Set[str],
        violations: List[InvariantViolation],
    ) -> None:
        if type(original) is not type(updated):
            if current_path not in allowed_paths:
                violations.append(InvariantViolation(current_path or "<root>", "type_changed"))
            return

        if isinstance(original, dict):
            original_keys = set(original.keys())
            updated_keys = set(updated.keys())
            if original_keys != updated_keys and current_path not in allowed_paths:
                violations.append(InvariantViolation(current_path or "<root>", "dict_keys_changed"))

            for key in sorted(original_keys & updated_keys):
                escaped_key = self._escape_path_key(str(key))
                child_path = escaped_key if not current_path else f"{current_path}.{escaped_key}"
                self._walk_differences(original[key], updated[key], child_path, allowed_paths, violations)
            return

        if isinstance(original, list):
            if len(original) != len(updated):
                if current_path not in allowed_paths:
                    violations.append(InvariantViolation(current_path or "<root>", "list_length_changed"))
                return

            for index, (left, right) in enumerate(zip(original, updated)):
                child_path = str(index) if not current_path else f"{current_path}.{index}"
                self._walk_differences(left, right, child_path, allowed_paths, violations)
            return

        if original != updated and current_path not in allowed_paths:
            violations.append(InvariantViolation(current_path or "<root>", "value_changed"))

    def _normalize_translation_path(self, path: str) -> Set[str]:
        if ".@JSON" in path:
            return {path.split(".@JSON", 1)[0]}

        if ".@MVCMD" in path:
            return {path.split(".@MVCMD", 1)[0]}

        if ".@NOTEBLOCK_" in path:
            return {path.split(".@NOTEBLOCK_", 1)[0]}

        if ".@NOTEINLINE_" in path:
            return {path.split(".@NOTEINLINE_", 1)[0]}

        if ".@SCRIPTMERGE" in path:
            base_path, merge_suffix = path.split(".@SCRIPTMERGE", 1)
            merge_count_raw = merge_suffix.split(".@JS", 1)[0]
            try:
                merge_count = int(merge_count_raw)
            except ValueError:
                return {base_path}

            list_path, _, command_index_raw = base_path.rpartition(".")
            try:
                command_index = int(command_index_raw)
            except ValueError:
                return {base_path}

            return {
                f"{list_path}.{command_index + offset}.parameters.0"
                for offset in range(merge_count + 1)
            }

        if ".@JS" in path:
            return {path.split(".@JS", 1)[0]}

        return {path}


class JsonAssetInvariantVerifier:
    """Verify that known asset identifiers and asset references never change."""

    def __init__(
        self,
        escape_path_key: Callable[[str], str],
        is_asset_text: Callable[[str], bool],
    ) -> None:
        self._escape_path_key = escape_path_key
        self._is_asset_text = is_asset_text

    def find_mutated_assets(self, original: Any, updated: Any) -> List[InvariantViolation]:
        """Return violations where an original asset/path-like string was changed."""
        violations: List[InvariantViolation] = []
        self._walk_asset_differences(original, updated, "", violations)
        return violations

    def _walk_asset_differences(
        self,
        original: Any,
        updated: Any,
        current_path: str,
        violations: List[InvariantViolation],
    ) -> None:
        if isinstance(original, str):
            if self._is_asset_text(original) and original != updated:
                violations.append(InvariantViolation(current_path or "<root>", "asset_reference_changed"))
            return

        if type(original) is not type(updated):
            return

        if isinstance(original, dict):
            for key in sorted(set(original.keys()) & set(updated.keys())):
                escaped_key = self._escape_path_key(str(key))
                child_path = escaped_key if not current_path else f"{current_path}.{escaped_key}"
                self._walk_asset_differences(original[key], updated[key], child_path, violations)
            return

        if isinstance(original, list):
            for index, (left, right) in enumerate(zip(original, updated)):
                child_path = str(index) if not current_path else f"{current_path}.{index}"
                self._walk_asset_differences(left, right, child_path, violations)
