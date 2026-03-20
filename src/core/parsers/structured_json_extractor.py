"""
Deterministic object-mapping extractor for safe RPG Maker JSON surfaces.
"""
from __future__ import annotations

import os
from typing import Any, Callable, List, Sequence, Tuple

from .json_field_rules import (
    EventCommandRule,
    FieldRule,
    get_event_command_rule,
    get_field_rules_for_file,
    is_structured_json_file,
)


ExtractionEntry = Tuple[str, str, str]
LegacyEventExtractor = Callable[[dict[str, Any], str, List[ExtractionEntry]], None]
LegacyScriptExtractor = Callable[[list[dict[str, Any]], str, int, List[ExtractionEntry]], None]
LegacyMZPluginExtractor = Callable[[list[dict[str, Any]], str, int, List[ExtractionEntry]], None]


class StructuredJsonExtractor:
    """Extract only explicitly mapped player-visible JSON fields."""

    def __init__(
        self,
        escape_path_key: Callable[[str], str],
        is_safe_to_translate: Callable[[str, bool], bool],
        legacy_event_extractor: LegacyEventExtractor | None = None,
        legacy_script_extractor: LegacyScriptExtractor | None = None,
        legacy_mz_plugin_extractor: LegacyMZPluginExtractor | None = None,
    ) -> None:
        self._escape_path_key = escape_path_key
        self._is_safe_to_translate = is_safe_to_translate
        self._legacy_event_extractor = legacy_event_extractor
        self._legacy_script_extractor = legacy_script_extractor
        self._legacy_mz_plugin_extractor = legacy_mz_plugin_extractor

    def supports_file(self, file_path: str) -> bool:
        """Return True when structured object mapping is supported."""
        return is_structured_json_file(file_path)

    def extract(
        self,
        file_path: str,
        data: Any,
        entries: List[ExtractionEntry] | None = None,
    ) -> List[ExtractionEntry]:
        """Extract player-visible text from known safe JSON surfaces."""
        if not self.supports_file(file_path):
            return []

        target_entries = entries if entries is not None else []

        for rule in get_field_rules_for_file(file_path):
            self._extract_rule_matches(data, (), rule, target_entries)

        basename = os.path.basename(file_path).lower()
        if basename == "commonevents.json":
            self._extract_common_events(data, target_entries)
        elif basename == "troops.json":
            self._extract_troop_pages(data, target_entries)
        elif basename.startswith("map") and basename.endswith(".json"):
            if isinstance(data, list):
                self._extract_event_list(data, "", target_entries)
            else:
                self._extract_map_events(data, target_entries)

        return target_entries

    def _extract_rule_matches(
        self,
        node: Any,
        path_parts: tuple[str, ...],
        rule: FieldRule,
        entries: List[ExtractionEntry],
    ) -> None:
        self._walk_selector(node, path_parts, rule.selector, rule.tag, rule.is_dialogue, entries)

    def _walk_selector(
        self,
        node: Any,
        path_parts: tuple[str, ...],
        selector: Sequence[str | int],
        tag: str,
        is_dialogue: bool,
        entries: List[ExtractionEntry],
    ) -> None:
        if not selector:
            if isinstance(node, str) and node.strip() and self._is_safe_to_translate(node, is_dialogue):
                entries.append((".".join(path_parts), node, tag))
            return

        token = selector[0]
        rest = selector[1:]

        if token == "*":
            if isinstance(node, list):
                for index, child in enumerate(node):
                    self._walk_selector(child, path_parts + (str(index),), rest, tag, is_dialogue, entries)
            elif isinstance(node, dict):
                for key, child in node.items():
                    escaped_key = self._escape_path_key(str(key))
                    self._walk_selector(child, path_parts + (escaped_key,), rest, tag, is_dialogue, entries)
            return

        if isinstance(token, int):
            if isinstance(node, list) and 0 <= token < len(node):
                self._walk_selector(node[token], path_parts + (str(token),), rest, tag, is_dialogue, entries)
            return

        if isinstance(node, dict) and token in node:
            escaped_key = self._escape_path_key(token)
            self._walk_selector(node[token], path_parts + (escaped_key,), rest, tag, is_dialogue, entries)

    def _extract_map_events(self, data: Any, entries: List[ExtractionEntry]) -> None:
        if not isinstance(data, dict):
            return

        events = data.get("events")
        if not isinstance(events, list):
            return

        for event_index, event in enumerate(events):
            if not isinstance(event, dict):
                continue
            pages = event.get("pages")
            if not isinstance(pages, list):
                continue
            for page_index, page in enumerate(pages):
                if not isinstance(page, dict):
                    continue
                commands = page.get("list")
                if not isinstance(commands, list):
                    continue
                list_path = f"events.{event_index}.pages.{page_index}.list"
                self._extract_event_list(commands, list_path, entries)

    def _extract_common_events(self, data: Any, entries: List[ExtractionEntry]) -> None:
        if not isinstance(data, list):
            return

        for event_index, event in enumerate(data):
            if not isinstance(event, dict):
                continue
            commands = event.get("list")
            if not isinstance(commands, list):
                continue
            self._extract_event_list(commands, f"{event_index}.list", entries)

    def _extract_troop_pages(self, data: Any, entries: List[ExtractionEntry]) -> None:
        if not isinstance(data, list):
            return

        for troop_index, troop in enumerate(data):
            if not isinstance(troop, dict):
                continue
            pages = troop.get("pages")
            if not isinstance(pages, list):
                continue
            for page_index, page in enumerate(pages):
                if not isinstance(page, dict):
                    continue
                commands = page.get("list")
                if not isinstance(commands, list):
                    continue
                list_path = f"{troop_index}.pages.{page_index}.list"
                self._extract_event_list(commands, list_path, entries)

    def _extract_event_list(self, commands: list[Any], list_path: str, entries: List[ExtractionEntry]) -> None:
        index = 0
        while index < len(commands):
            command = commands[index]
            command_path = f"{list_path}.{index}" if list_path else str(index)
            if not isinstance(command, dict):
                index += 1
                continue

            code = command.get("code")
            if code == 355 and self._legacy_script_extractor is not None:
                merged_commands = [command]
                next_index = index + 1
                while next_index < len(commands):
                    candidate = commands[next_index]
                    if not isinstance(candidate, dict) or candidate.get("code") != 655:
                        break
                    merged_commands.append(candidate)
                    next_index += 1
                self._legacy_script_extractor(merged_commands, list_path, index, entries)
                index = next_index
                continue

            if code == 357 and self._legacy_mz_plugin_extractor is not None:
                merged_commands = [command]
                next_index = index + 1
                while next_index < len(commands):
                    candidate = commands[next_index]
                    if not isinstance(candidate, dict) or candidate.get("code") != 657:
                        break
                    merged_commands.append(candidate)
                    next_index += 1
                self._legacy_mz_plugin_extractor(merged_commands, list_path, index, entries)
                index = next_index
                continue

            if code in (356, 108, 408) and self._legacy_event_extractor is not None:
                self._legacy_event_extractor(command, command_path, entries)
                index += 1
                continue

            if code in (655, 657):
                index += 1
                continue

            rule = get_event_command_rule(code) if isinstance(code, int) else None
            if rule is not None:
                self._extract_event_command_fields(command, command_path, rule, entries)

            index += 1

    def _extract_event_command_fields(
        self,
        command: dict[str, Any],
        command_path: str,
        rule: EventCommandRule,
        entries: List[ExtractionEntry],
    ) -> None:
        parameters = command.get("parameters")
        if not isinstance(parameters, list):
            return

        for target_path, value in self._resolve_parameter_targets(parameters, rule.parameter_path, ("parameters",)):
            if not isinstance(value, str) or not value.strip():
                continue
            if not self._is_safe_to_translate(value, rule.is_dialogue):
                continue
            entries.append((f"{command_path}.{'.'.join(target_path)}", value, rule.tag))

    def _resolve_parameter_targets(
        self,
        node: Any,
        selector: Sequence[str | int],
        current_path: tuple[str, ...],
    ) -> List[Tuple[tuple[str, ...], Any]]:
        if not selector:
            return [(current_path, node)]

        token = selector[0]
        rest = selector[1:]

        if token == "*":
            if isinstance(node, list):
                results: List[Tuple[tuple[str, ...], Any]] = []
                for index, child in enumerate(node):
                    results.extend(self._resolve_parameter_targets(child, rest, current_path + (str(index),)))
                return results
            return []

        if isinstance(token, int):
            if isinstance(node, list) and 0 <= token < len(node):
                return self._resolve_parameter_targets(node[token], rest, current_path + (str(token),))
            return []

        if isinstance(node, dict) and token in node:
            escaped_key = self._escape_path_key(str(token))
            return self._resolve_parameter_targets(node[token], rest, current_path + (escaped_key,))

        return []
