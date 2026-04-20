"""
Lightweight RPG Maker plugin metadata parser.

Parses MV/MZ plugin header annotations from plugin source files so translation
filters can understand semantic parameter types such as file, combo, struct,
etc. This intentionally stays dependency-free and focuses on the subset needed
for safe plugins.js extraction.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import os
from typing import Dict, Iterable, Optional


PLUGIN_SOURCE_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8", "cp932", "shift_jis")


@dataclass(slots=True)
class PluginParameterMetadata:
    """Metadata for a single plugin parameter."""

    name: str
    type_name: str = ""
    text: str = ""
    description: str = ""
    default_value: str = ""
    parent: str = ""
    dir_path: str = ""
    require: bool = False
    options: list[str] = field(default_factory=list)

    def normalized_type(self) -> str:
        """Return a lowercase, trimmed type string."""
        return self.type_name.strip().lower()

    def base_type(self) -> str:
        """Return the underlying type without array suffixes."""
        type_name = self.normalized_type()
        if type_name.endswith("[]"):
            return type_name[:-2]
        return type_name

    def struct_name(self) -> str | None:
        """Return the referenced struct name when this parameter uses struct<T>."""
        base_type = self.base_type()
        if not base_type.startswith("struct<") or not base_type.endswith(">"):
            return None
        return base_type[len("struct<") : -1].strip()

    def array_item_metadata(self) -> PluginParameterMetadata:
        """Return item-level metadata for array parameters."""
        type_name = self.normalized_type()
        if not type_name.endswith("[]"):
            return self
        return replace(self, type_name=type_name[:-2])

    def combined_hints(self) -> str:
        """Return searchable lowercased hints from metadata fields."""
        parts = [self.name, self.text, self.description, self.parent]
        return " ".join(part for part in parts if part).lower()

    def is_group_header(self, all_params: "dict[str, PluginParameterMetadata]") -> bool:
        """Return True when this parameter acts only as a visual group header.

        A parameter is considered a pure group header when:
        - It has no meaningful type (empty, 'text', or 'note' only used as
          display labels in the editor), AND
        - At least one other parameter references it via @parent, AND
        - Its default value is empty (no real runtime value).
        """
        base = self.base_type()
        if base not in ("", "text", "note"):
            return False
        if self.default_value.strip():
            return False
        name_lower = self.name.lower()
        return any(
            p.parent.lower() == name_lower
            for p in all_params.values()
            if p is not self and p.parent
        )


@dataclass(slots=True)
class PluginFileMetadata:
    """Parsed metadata for a single plugin source file."""

    name: str
    params: Dict[str, PluginParameterMetadata] = field(default_factory=dict)
    structs: Dict[str, Dict[str, PluginParameterMetadata]] = field(default_factory=dict)

    def get_param(self, param_name: str) -> PluginParameterMetadata | None:
        """Return top-level parameter metadata by exact key."""
        return self.params.get(param_name)

    def get_struct_fields(self, struct_name: str | None) -> Dict[str, PluginParameterMetadata] | None:
        """Return field metadata for the given struct name."""
        if not struct_name:
            return None
        return self.structs.get(struct_name.lower())


class PluginMetadataStore:
    """Lazy cache of plugin metadata loaded from js/plugins/*.js."""

    def __init__(self, plugins_dir: str | None) -> None:
        self._plugins_dir = plugins_dir
        self._cache: Dict[str, PluginFileMetadata | None] = {}

    def get(self, plugin_name: str) -> PluginFileMetadata | None:
        """Load and cache metadata for the given plugin name."""
        if not plugin_name:
            return None
        if plugin_name in self._cache:
            return self._cache[plugin_name]

        source_path = self._resolve_plugin_source(plugin_name)
        if not source_path:
            self._cache[plugin_name] = None
            return None

        metadata = self._parse_plugin_source(source_path, plugin_name)
        self._cache[plugin_name] = metadata
        return metadata

    def _resolve_plugin_source(self, plugin_name: str) -> str | None:
        """Find the matching plugin source file inside js/plugins."""
        if not self._plugins_dir or not os.path.isdir(self._plugins_dir):
            return None

        exact_path = os.path.join(self._plugins_dir, f"{plugin_name}.js")
        if os.path.isfile(exact_path):
            return exact_path

        target_name = f"{plugin_name}.js".lower()
        try:
            with os.scandir(self._plugins_dir) as entries:
                for entry in entries:
                    if entry.is_file() and entry.name.lower() == target_name:
                        return entry.path
        except OSError:
            return None
        return None

    def _parse_plugin_source(self, file_path: str, plugin_name: str) -> PluginFileMetadata | None:
        """Parse plugin and struct annotation blocks from a source file."""
        content = self._read_text(file_path)
        if content is None:
            return None

        metadata = PluginFileMetadata(name=plugin_name)
        block_kind: str | None = None
        struct_name: str | None = None
        block_lines: list[str] = []

        for raw_line in content.splitlines():
            stripped = raw_line.lstrip()
            if block_kind is None:
                if stripped.startswith("/*~struct~"):
                    block_kind = "struct"
                    struct_name = stripped[len("/*~struct~") :].split(":", 1)[0].strip()
                    block_lines = []
                    continue
                if stripped.startswith("/*:"):
                    block_kind = "plugin"
                    struct_name = None
                    block_lines = []
                    continue

            if block_kind is None:
                continue

            if "*/" in raw_line:
                block_lines.append(raw_line.split("*/", 1)[0])
                self._parse_block(block_kind, struct_name, block_lines, metadata)
                block_kind = None
                struct_name = None
                block_lines = []
                continue

            block_lines.append(raw_line)

        return metadata

    def _read_text(self, file_path: str) -> str | None:
        """Read a plugin source file with fallback encodings."""
        for encoding in PLUGIN_SOURCE_ENCODINGS:
            try:
                with open(file_path, "r", encoding=encoding) as handle:
                    return handle.read()
            except (OSError, UnicodeDecodeError):
                continue
        return None

    def _parse_block(
        self,
        block_kind: str,
        struct_name: str | None,
        block_lines: Iterable[str],
        metadata: PluginFileMetadata,
    ) -> None:
        """Parse a single annotation block into parameter metadata."""
        if block_kind == "plugin":
            container = metadata.params
        else:
            if not struct_name:
                return
            container = metadata.structs.setdefault(struct_name.lower(), {})

        current: PluginParameterMetadata | None = None
        active_field: str | None = None

        for raw_line in block_lines:
            line = raw_line.strip()
            if line.startswith("*"):
                line = line[1:].lstrip()
            if not line:
                continue

            if line.startswith("@"):
                tag, _, remainder = line[1:].partition(" ")
                value = remainder.strip()
                lower_tag = tag.lower()

                if lower_tag == "param":
                    current = container.setdefault(value, PluginParameterMetadata(name=value))
                    active_field = None
                    continue

                if current is None:
                    active_field = None
                    continue

                if lower_tag == "type":
                    current.type_name = value or current.type_name
                    active_field = None
                elif lower_tag == "text":
                    current.text = _merge_multiline_value(current.text, value)
                    active_field = "text"
                elif lower_tag == "desc":
                    current.description = _merge_multiline_value(current.description, value)
                    active_field = "description"
                elif lower_tag == "default":
                    current.default_value = _merge_multiline_value(current.default_value, value)
                    active_field = "default_value"
                elif lower_tag == "parent":
                    current.parent = value or current.parent
                    active_field = None
                elif lower_tag == "dir":
                    current.dir_path = value or current.dir_path
                    active_field = None
                elif lower_tag == "require":
                    current.require = value in {"1", "true", "True"}
                    active_field = None
                elif lower_tag == "option" and value:
                    current.options.append(value)
                    active_field = None
                else:
                    active_field = None
                continue

            if current is None or active_field is None:
                continue
            current_value = getattr(current, active_field)
            setattr(current, active_field, _merge_multiline_value(current_value, line))


def _merge_multiline_value(current: str, extra: str) -> str:
    """Append continuation text while preserving readability."""
    if not extra:
        return current
    if not current:
        return extra
    return f"{current}\n{extra}"
