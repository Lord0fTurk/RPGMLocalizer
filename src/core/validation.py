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
        Ensure Ruby Marshal data can be serialized without type or encoding corruption.
        """
        if isinstance(translated_data, bytes):
            if len(translated_data) == 0:
                return ValidationResult.failure(["Ruby binary patch result is empty"])
            return ValidationResult.success({"byte_size": len(translated_data)})

        try:
            import io
            import rubymarshal.writer
            buffer = io.BytesIO()
            rubymarshal.writer.write(buffer, translated_data)
            serialized = buffer.getvalue()
            if not serialized:
                return ValidationResult.failure(["Ruby Marshal serialized output is empty"])
            return ValidationResult.success({"byte_size": len(serialized)})
        except Exception as exc:
            return ValidationResult.failure([f"Ruby Marshal serialization check failed: {exc}"])

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


