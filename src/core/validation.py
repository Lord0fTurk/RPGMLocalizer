"""
Validation module for RPGMLocalizer.
Ensures translation integrity and safety before saving files.
"""
import logging
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """
    Result of a validation check with detailed status and error information.
    
    Attributes:
        is_valid: Whether the validation passed
        errors: List of error messages
        warnings: List of warning messages
        metadata: Additional validation metadata
    """
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def success(cls, metadata: Optional[Dict[str, Any]] = None) -> 'ValidationResult':
        """Create a successful validation result."""
        return cls(is_valid=True, metadata=metadata or {})
    
    @classmethod
    def failure(cls, errors: List[str], metadata: Optional[Dict[str, Any]] = None) -> 'ValidationResult':
        """Create a failed validation result."""
        return cls(is_valid=False, errors=errors, metadata=metadata or {})
    
    @classmethod
    def warning(cls, message: str, metadata: Optional[Dict[str, Any]] = None) -> 'ValidationResult':
        """Create a result with a warning (still valid)."""
        return cls(is_valid=True, warnings=[message], metadata=metadata or {})
    
    def add_error(self, error: str) -> None:
        """Add an error message and mark as invalid."""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)

class Validator:
    """Static validation utilities."""

    @staticmethod
    def validate_translation_entry(original: str, translated: str, placeholders: Dict[str, str]) -> bool:
        """
        Validate a single translation line against its original.
        (v0.7.0: placeholder validation is a no-op — codes are never exposed
        to translation in the segment-based system; kept for API compatibility.)
        """
        if not original.strip():
            return True
        if not translated:
            return False
        return True

    @staticmethod
    def validate_json_structure(original_data: Any, translated_data: Any) -> bool:
        """
        Recursively validate that the structure of translated data matches original.
        Checks list lengths and key presence for critical structures.
        """
        if type(original_data) != type(translated_data):
            logger.error(f"Type mismatch: {type(original_data)} vs {type(translated_data)}")
            return False
            
        if isinstance(original_data, list):
            if len(original_data) != len(translated_data):
                logger.error(f"List length mismatch: {len(original_data)} vs {len(translated_data)}")
                return False
            # Check first item's structure if list is not empty
            if len(original_data) > 0:
                return Validator.validate_json_structure(original_data[0], translated_data[0])
            return True
            
        if isinstance(original_data, dict):
            # Check that all original keys are present in translated
            if not (original_data.keys() <= translated_data.keys()):
                missing_keys = set(original_data.keys()) - set(translated_data.keys())
                logger.error(f"Missing keys in translated data: {missing_keys}")
                return False
            
            # Recursively check values for nested structures
            for key, orig_val in original_data.items():
                if isinstance(orig_val, (dict, list)):
                    trans_val = translated_data.get(key)
                    if not Validator.validate_json_structure(orig_val, trans_val):
                        logger.error(f"Structure mismatch at key '{key}'")
                        return False
            
            return True
            
        return True

    @staticmethod
    def validate_json_roundtrip(original_data: Any, translated_data: Any) -> ValidationResult:
        """
        Perform a shadow dry-run serialization & deserialization check on translated JSON data.
        Ensures:
        1. orjson/json can serialize without error.
        2. Deserialized result matches original structure and keys.
        """
        import orjson
        try:
            dumped_bytes = orjson.dumps(translated_data)
        except Exception as exc:
            return ValidationResult.failure([f"JSON serialization failed: {exc}"])

        try:
            reloaded = orjson.loads(dumped_bytes)
        except Exception as exc:
            return ValidationResult.failure([f"JSON deserialization failed: {exc}"])

        if not Validator.validate_json_structure(original_data, reloaded):
            return ValidationResult.failure(["JSON structural invariant verification failed after roundtrip"])

        return ValidationResult.success({"byte_size": len(dumped_bytes), "serialized_bytes": dumped_bytes})

    @staticmethod
    def validate_ruby_roundtrip(translated_data: Any) -> ValidationResult:
        """
        Ensure Ruby Marshal data can be serialized and safely re-read without corruption.
        Performs shadow deserialization on raw bytes or serialized data.
        """
        import io
        import rubymarshal.reader
        import rubymarshal.writer

        serialized: bytes
        if isinstance(translated_data, bytes):
            if len(translated_data) == 0:
                return ValidationResult.failure(["Ruby binary patch result is empty"])
            serialized = translated_data
        else:
            try:
                buffer = io.BytesIO()
                rubymarshal.writer.write(buffer, translated_data)
                serialized = buffer.getvalue()
                if not serialized:
                    return ValidationResult.failure(["Ruby Marshal serialized output is empty"])
            except Exception as exc:
                return ValidationResult.failure([f"Ruby Marshal serialization check failed: {exc}"])

        # Shadow deserialization check: verify that bytes can be re-read into valid Ruby objects
        try:
            verify_buf = io.BytesIO(serialized)
            reloaded = rubymarshal.reader.load(verify_buf)
            if reloaded is None and serialized != b"\x04\x080":
                return ValidationResult.failure(["Ruby Marshal deserialization returned unexpected None"])
        except Exception as verify_exc:
            return ValidationResult.failure([f"Ruby Marshal binary corruption detected on re-read: {verify_exc}"])

        return ValidationResult.success({"byte_size": len(serialized)})

    @staticmethod
    def validate_js_syntax(js_code: str) -> ValidationResult:
        """
        Validate JavaScript syntax using tree-sitter AST parser.
        Ensures modified JavaScript plugin or source files have no syntax errors before writing to disk.
        """
        if not js_code or not js_code.strip():
            return ValidationResult.success()

        try:
            from tree_sitter import Language, Parser
            import tree_sitter_javascript

            lang = Language(tree_sitter_javascript.language())
            parser = Parser(lang)
            tree = parser.parse(js_code.encode("utf-8"))

            if tree.root_node.has_error:
                def _collect_errors(node: Any, limit: int = 3) -> List[str]:
                    errs: List[str] = []
                    if node.has_error:
                        if node.is_error or node.is_missing:
                            errs.append(f"line {node.start_point[0] + 1}, col {node.start_point[1]}")
                        for child in node.children:
                            if len(errs) >= limit:
                                break
                            errs.extend(_collect_errors(child, limit - len(errs)))
                    return errs

                error_locs = _collect_errors(tree.root_node)
                loc_str = f" at {', '.join(error_locs)}" if error_locs else ""
                msg = f"JavaScript syntax error detected in parsed AST{loc_str}"
                logger.error(msg)
                return ValidationResult.failure([msg])

            return ValidationResult.success({"byte_size": len(js_code)})
        except Exception as exc:
            logger.warning(f"Tree-sitter JS validation skipped or encountered an error: {exc}")
            return ValidationResult.success()

    @staticmethod
    def validate_wolf_roundtrip(
        data: bytes,
        file_ext: str,
        original_path: Optional[str] = None,
    ) -> ValidationResult:
        """Validate WOLF RPG Editor binary payload via shadow deserialization.

        Ensures that generated bytes can be re-read into valid WOLF objects
        (WolfMap, WolfCommonEvents, or WolfDatabase) without corruption, magic mismatches,
        or LZ4 decompression errors before writing to disk.
        """
        import os
        from pathlib import Path
        from src.core.parsers.wolf_binary import (
            WolfCommonEvents,
            WolfDatabase,
            WolfFormatError,
            WolfMap,
        )

        if not data:
            return ValidationResult.failure(["WOLF binary payload is empty"])

        ext = file_ext.lower()
        base = os.path.basename(original_path).lower() if original_path else ""

        try:
            if ext == ".mps":
                WolfMap.from_bytes(data, path_for_error=original_path or "memory.mps")
                return ValidationResult.success({"byte_size": len(data), "wolf_type": "map"})

            if ext == ".dat":
                if base == "commonevent.dat":
                    WolfCommonEvents.from_bytes(data, path_for_error=original_path or "CommonEvent.dat")
                    return ValidationResult.success({"byte_size": len(data), "wolf_type": "common_event"})

                if original_path:
                    project_path = os.path.splitext(original_path)[0] + ".project"
                    if os.path.isfile(project_path):
                        proj_bytes = Path(project_path).read_bytes()
                        WolfDatabase.from_bytes(
                            proj_bytes,
                            data,
                            proj_path_for_error=project_path,
                            dat_path_for_error=original_path,
                        )
                        return ValidationResult.success({"byte_size": len(data), "wolf_type": "database"})

                from src.core.parsers.wolf_binary import (
                    ByteReader,
                    _DAT_MAGIC_CP932,
                    _DAT_UTF8_INDEX,
                    _DAT_V35_VERSION,
                )
                r = ByteReader(data)
                r.read_byte()  # 0x00 indicator
                r.verify_magic_utf8_aware(_DAT_MAGIC_CP932, _DAT_UTF8_INDEX)
                version = r.read_byte()
                if version == _DAT_V35_VERSION:
                    r.unpack_lz4(r.tell())
                return ValidationResult.success({"byte_size": len(data), "wolf_type": "database_generic"})

            return ValidationResult.failure([f"Unsupported WOLF extension for validation: {ext}"])

        except WolfFormatError as wfe:
            return ValidationResult.failure([f"WOLF format validation failed: {wfe}"])
        except Exception as exc:
            return ValidationResult.failure([f"WOLF shadow deserialization error: {exc}"])



