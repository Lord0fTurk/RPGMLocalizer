"""
Audit-only JavaScript AST extractor for player-visible string candidates.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

from .js_tokenizer import JSStringTokenizer

try:
    from tree_sitter import Language, Parser
    import tree_sitter_javascript
except ImportError:  # pragma: no cover - exercised through fallback behavior
    Language = None
    Parser = None
    tree_sitter_javascript = None


AuditEntry = Tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class JavaScriptAuditCandidate:
    """A scored JS audit candidate."""

    path: str
    text: str
    tag: str
    score: int
    bucket: str


class JavaScriptAstAuditExtractor:
    """Extract likely player-visible strings from raw JS using AST context."""

    MIN_TRANSLATABLE_SCORE = 3
    HIGH_CONFIDENCE_SCORE = 8
    MEDIUM_CONFIDENCE_SCORE = 5
    POSITIVE_CALLEE_HINTS = {
        "printloadingerror",
        "printerror",
        "addtext",
        "drawtext",
        "sethelptext",
        "sethelpwindowitem",
    }
    NEGATIVE_CALLEE_HINTS = {
        "imagemanager.load",
        "audiomanager.play",
        "soundmanager.play",
        "pluginmanager.parameters",
        "storagemanager",
        "require",
    }
    POSITIVE_KEY_HINTS = {
        "title",
        "text",
        "message",
        "description",
        "desc",
        "help",
        "label",
        "caption",
        "header",
        "footer",
        "hint",
        "tooltip",
        "summary",
        "command",
    }
    NEGATIVE_KEY_HINTS = {
        "file",
        "filename",
        "filepath",
        "path",
        "dir",
        "directory",
        "symbol",
        "bgm",
        "bgs",
        "me",
        "se",
        "switch",
        "switchid",
        "variable",
        "variableid",
        "image",
        "img",
        "icon",
        "picture",
        "face",
        "character",
        "tileset",
        "animation",
        "motion",
        "pose",
        "sampleimg",
        "asset",
        "url",
        "id",
        "key",
        "code",
        "locale",
    }
    SAFE_SINK_CALL_HINTS = {
        "$gamemessage.add",
        "addcommand",
        "addtext",
        "drawtext",
        "sethelptext",
        "sethelpwindowitem",
        "setcaption",
        "setlabel",
        "setdescription",
        "settitle",
        "alert",
        "confirm",
        "prompt",
    }
    SAFE_SINK_TEXT_HINTS = {
        "text",
        "message",
        "caption",
        "label",
        "title",
        "description",
        "help",
        "tooltip",
    }

    def __init__(self) -> None:
        self._tokenizer = JSStringTokenizer()
        self._language = self._build_language()
        self._parser = Parser(self._language) if self._language is not None and Parser is not None else None

    @property
    def engine_name(self) -> str:
        """Return the currently active extraction engine."""
        return "tree_sitter" if self._parser is not None else "tokenizer_fallback"

    def extract_text(self, file_path: str) -> tuple[List[AuditEntry], str]:
        """Extract audit-only string candidates from a JS file."""
        candidates, engine = self.extract_audit_candidates(file_path)
        return [(item.path, item.text, item.tag) for item in candidates], engine

    def extract_audit_candidates(self, file_path: str) -> tuple[List[JavaScriptAuditCandidate], str]:
        """Extract scored audit candidates from a JS file."""
        with open(file_path, "r", encoding="utf-8-sig") as handle:
            content = handle.read()
        return self.extract_audit_candidates_from_source(content)

    def extract_text_from_source(self, js_code: str) -> tuple[List[AuditEntry], str]:
        """Extract audit-only string candidates from JS source."""
        candidates, engine = self.extract_audit_candidates_from_source(js_code)
        return [(item.path, item.text, item.tag) for item in candidates], engine

    def extract_safe_sink_entries_from_source(self, js_code: str) -> tuple[List[AuditEntry], str]:
        """Extract strings only from semantically safe JS sinks."""
        if not js_code.strip():
            return [], self.engine_name

        if self._parser is None:
            return self._extract_safe_strings_with_tokenizer(js_code), self.engine_name

        source_bytes = js_code.encode("utf-8")
        tree = self._parser.parse(source_bytes)

        entries: List[AuditEntry] = []
        seen_paths: set[str] = set()

        for node in self._iter_string_nodes(tree.root_node):
            text_value = self._decode_string_value(source_bytes, node)
            if not self._is_safe_sink_string(node, text_value, source_bytes):
                continue

            path = f"@SAFE{node.start_point.row}:{node.start_point.column}"
            if path in seen_paths:
                continue

            seen_paths.add(path)
            entries.append((path, text_value, "js_safe_sink"))

        return entries, self.engine_name

    def extract_audit_candidates_from_source(
        self,
        js_code: str,
    ) -> tuple[List[JavaScriptAuditCandidate], str]:
        """Extract scored audit-only string candidates from JS source."""
        if not js_code.strip():
            return [], self.engine_name

        if self._parser is None:
            return self._extract_with_tokenizer(js_code), self.engine_name

        source_bytes = js_code.encode("utf-8")
        tree = self._parser.parse(source_bytes)

        entries: List[JavaScriptAuditCandidate] = []
        seen_paths: set[str] = set()

        for node in self._iter_string_nodes(tree.root_node):
            text_value = self._decode_string_value(source_bytes, node)
            if not text_value or not text_value.strip():
                continue

            score = self._score_string_candidate(node, text_value, source_bytes)
            if score < self.MIN_TRANSLATABLE_SCORE:
                continue

            path = f"@AST{node.start_point.row}:{node.start_point.column}"
            if path in seen_paths:
                continue

            seen_paths.add(path)
            entries.append(
                JavaScriptAuditCandidate(
                    path=path,
                    text=text_value,
                    tag="js_ast_candidate",
                    score=score,
                    bucket=self._bucket_for_score(score),
                )
            )

        return entries, self.engine_name

    def summarize_candidates(
        self,
        candidates: Iterable[JavaScriptAuditCandidate],
        engine: str,
    ) -> Dict[str, Any]:
        """Summarize audit candidates into confidence buckets and write readiness."""
        candidate_list = list(candidates)
        bucket_counts = Counter(candidate.bucket for candidate in candidate_list)
        high_count = bucket_counts.get("high", 0)
        medium_count = bucket_counts.get("medium", 0)
        low_count = bucket_counts.get("low", 0)
        total_count = sum(bucket_counts.values())

        if total_count == 0:
            write_readiness = "none"
        elif engine != "tree_sitter":
            write_readiness = "unsupported"
        elif high_count > 0 and low_count == 0:
            write_readiness = "promising"
        elif high_count > 0 or medium_count > 0:
            write_readiness = "review"
        else:
            write_readiness = "unsafe"

        return {
            "confidence_buckets": dict(bucket_counts),
            "write_readiness": write_readiness,
            "top_score": max((candidate.score for candidate in candidate_list), default=None),
        }

    def _extract_with_tokenizer(self, js_code: str) -> List[JavaScriptAuditCandidate]:
        strings = self._tokenizer.extract_translatable_strings(js_code)
        return [
            JavaScriptAuditCandidate(
                path=f"@TOK{index}",
                text=value,
                tag="js_tokenizer_candidate",
                score=self.MIN_TRANSLATABLE_SCORE,
                bucket="heuristic",
            )
            for index, (_start, _end, value, _quote) in enumerate(strings)
        ]

    def _extract_safe_strings_with_tokenizer(self, js_code: str) -> List[AuditEntry]:
        strings = self._tokenizer.extract_translatable_strings(js_code)
        return [
            (f"@SAFE_TOK{index}", value, "js_safe_sink_fallback")
            for index, (_start, _end, value, _quote) in enumerate(strings)
        ]

    def _build_language(self):
        if Language is None or tree_sitter_javascript is None:
            return None
        return Language(tree_sitter_javascript.language())

    def _iter_string_nodes(self, node: Any) -> Iterable[Any]:
        if node.type == "string":
            yield node
        elif node.type == "template_string":
            if not any(child.type == "template_substitution" for child in node.named_children):
                yield node

        for child in node.children:
            yield from self._iter_string_nodes(child)

    def _decode_string_value(self, source_bytes: bytes, node: Any) -> str:
        raw_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
        if node.type == "template_string":
            return raw_text[1:-1]

        try:
            return ast.literal_eval(raw_text)
        except (SyntaxError, ValueError):
            return raw_text[1:-1] if len(raw_text) >= 2 else raw_text

    def _score_string_candidate(self, node: Any, text_value: str, source_bytes: bytes) -> int:
        stripped = text_value.strip()
        if not stripped:
            return -99

        score = 0

        if len(stripped) >= 8:
            score += 1
        if " " in stripped:
            score += 2
        if any(char in stripped for char in ".!?:;"):
            score += 1
        if any(ord(char) > 127 for char in stripped):
            score += 1

        if self._tokenizer._is_technical_string(stripped):
            score -= 4

        if self._is_pair_key(node) or self._is_subscript_key(node):
            return -99

        pair_key = self._get_pair_value_key(node, source_bytes)
        if pair_key:
            score += self._score_key_hint(pair_key)

        assignment_key = self._get_assignment_target_key(node, source_bytes)
        if assignment_key:
            score += self._score_key_hint(assignment_key)

        callee_name, arg_index = self._get_call_context(node, source_bytes)
        if callee_name:
            lower_callee = callee_name.lower()
            if any(hint in lower_callee for hint in self.NEGATIVE_CALLEE_HINTS):
                score -= 6
            if any(hint in lower_callee for hint in self.POSITIVE_CALLEE_HINTS):
                score += 5
            if lower_callee.endswith("addcommand"):
                score += 5 if arg_index == 0 else -8
            if lower_callee.endswith("printloadingerror"):
                if arg_index in (0, 1):
                    score += 6
            if lower_callee.endswith("$gamemessage.add"):
                score += 6

        if self._has_ancestor(node, "return_statement"):
            score += 2

        if self._has_ancestor(node, "import_statement") or self._has_ancestor(node, "export_statement"):
            score -= 8

        return score

    def _bucket_for_score(self, score: int) -> str:
        if score >= self.HIGH_CONFIDENCE_SCORE:
            return "high"
        if score >= self.MEDIUM_CONFIDENCE_SCORE:
            return "medium"
        return "low"

    def _is_safe_sink_string(self, node: Any, text_value: str, source_bytes: bytes) -> bool:
        stripped = text_value.strip()
        if not stripped:
            return False

        if self._tokenizer._is_technical_string(stripped):
            return False

        callee_name, arg_index = self._get_call_context(node, source_bytes)
        if callee_name is not None:
            normalized_callee = callee_name.lower()
            if any(hint in normalized_callee for hint in self.SAFE_SINK_CALL_HINTS):
                if arg_index == 0:
                    return self._looks_textual_candidate(stripped)
                if normalized_callee.endswith("addcommand") and arg_index == 1:
                    return False
            if normalized_callee.endswith("setvalue") and arg_index == 1:
                return self._looks_textual_candidate(stripped)
            return False

        pair_key = self._get_pair_value_key(node, source_bytes)
        if pair_key and self._is_positive_text_key(pair_key):
            return self._looks_textual_candidate(stripped)

        assignment_key = self._get_assignment_target_key(node, source_bytes)
        if assignment_key and self._is_positive_text_key(assignment_key):
            return self._looks_textual_candidate(stripped)

        variable_name = self._get_variable_declarator_name(node, source_bytes)
        if variable_name and self._is_positive_text_key(variable_name):
            return self._looks_textual_candidate(stripped)

        return False

    def _is_positive_text_key(self, key_name: str) -> bool:
        normalized = key_name.lower()
        if normalized in self.NEGATIVE_KEY_HINTS:
            return False
        return any(hint in normalized for hint in self.SAFE_SINK_TEXT_HINTS)

    def _looks_textual_candidate(self, text_value: str) -> bool:
        stripped = text_value.strip()
        if not stripped:
            return False
        if len(stripped) >= 4 and (" " in stripped or any(ord(char) > 127 for char in stripped)):
            return True
        return any(mark in stripped for mark in ("!", "?", ".", ":", ";")) and len(stripped) >= 4

    def _score_key_hint(self, key_name: str) -> int:
        lower_key = key_name.lower()
        if lower_key in self.NEGATIVE_KEY_HINTS:
            return -6
        if lower_key in self.POSITIVE_KEY_HINTS:
            return 4
        return 0

    def _is_pair_key(self, node: Any) -> bool:
        parent = node.parent
        if parent is None or parent.type != "pair":
            return False
        return parent.child_by_field_name("key") == node

    def _is_subscript_key(self, node: Any) -> bool:
        parent = node.parent
        if parent is None or parent.type != "subscript_expression":
            return False
        return parent.child_by_field_name("index") == node

    def _get_pair_value_key(self, node: Any, source_bytes: bytes) -> str | None:
        parent = node.parent
        if parent is None or parent.type != "pair":
            return None
        if parent.child_by_field_name("value") != node:
            return None
        key_node = parent.child_by_field_name("key")
        return self._node_text(key_node, source_bytes) if key_node is not None else None

    def _get_assignment_target_key(self, node: Any, source_bytes: bytes) -> str | None:
        current = node
        while current.parent is not None and current.parent.type in {"binary_expression", "parenthesized_expression"}:
            current = current.parent

        parent = current.parent
        if parent is None or parent.type != "assignment_expression":
            return None
        if parent.child_by_field_name("right") != current:
            return None
        left_node = parent.child_by_field_name("left")
        return self._extract_target_key(left_node, source_bytes)

    def _extract_target_key(self, node: Any, source_bytes: bytes) -> str | None:
        if node is None:
            return None
        if node.type in {"identifier", "property_identifier"}:
            return self._node_text(node, source_bytes)
        if node.type == "member_expression":
            property_node = node.child_by_field_name("property")
            return self._extract_target_key(property_node, source_bytes)
        if node.type == "subscript_expression":
            index_node = node.child_by_field_name("index")
            if index_node is None:
                return None
            if index_node.type == "string":
                return self._decode_string_value(source_bytes, index_node)
            return self._node_text(index_node, source_bytes)
        return None

    def _get_variable_declarator_name(self, node: Any, source_bytes: bytes) -> str | None:
        parent = node.parent
        if parent is None or parent.type != "variable_declarator":
            return None
        if parent.child_by_field_name("value") != node:
            return None
        name_node = parent.child_by_field_name("name")
        return self._node_text(name_node, source_bytes) if name_node is not None else None

    def _get_call_context(self, node: Any, source_bytes: bytes) -> tuple[str | None, int | None]:
        current = node
        while current.parent is not None and current.parent.type in {"binary_expression", "parenthesized_expression"}:
            current = current.parent

        parent = current.parent
        if parent is None or parent.type != "arguments":
            return None, None

        call_expression = parent.parent
        if call_expression is None or call_expression.type != "call_expression":
            return None, None

        arg_nodes = list(parent.named_children)
        try:
            arg_index = arg_nodes.index(current)
        except ValueError:
            arg_index = None

        function_node = call_expression.child_by_field_name("function")
        return self._member_expression_name(function_node, source_bytes), arg_index

    def _member_expression_name(self, node: Any, source_bytes: bytes) -> str | None:
        if node is None:
            return None
        if node.type in {"identifier", "property_identifier", "this"}:
            return self._node_text(node, source_bytes)
        if node.type == "member_expression":
            object_node = node.child_by_field_name("object")
            property_node = node.child_by_field_name("property")
            object_name = self._member_expression_name(object_node, source_bytes)
            property_name = self._member_expression_name(property_node, source_bytes)
            if object_name and property_name:
                return f"{object_name}.{property_name}"
            return property_name or object_name
        return self._node_text(node, source_bytes)

    def _has_ancestor(self, node: Any, ancestor_type: str) -> bool:
        current = node.parent
        while current is not None:
            if current.type == ancestor_type:
                return True
            current = current.parent
        return False

    def _node_text(self, node: Any, source_bytes: bytes) -> str:
        raw_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
        if node.type == "string":
            return self._decode_string_value(source_bytes, node)
        return raw_text
