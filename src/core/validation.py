"""
Validation module for RPGMLocalizer.
Ensures translation integrity and safety before saving files.
"""
import logging
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field
from src.utils.placeholder import validate_restoration

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
        Checks for missing placeholders.
        """
        if not original.strip():
            return True
            
        if not translated:
            # Empty translation for non-empty original is a failure
            return False
            
        # Check Placeholders
        is_valid, missing = validate_restoration(original, translated, placeholders)
        if not is_valid:
            logger.warning(f"Validation Failed: Missing placeholders {missing}")
            logger.debug(f"Original: {original}")
            logger.debug(f"Translated: {translated}")
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
            original_keys = set(original_data.keys())
            translated_keys = set(translated_data.keys())
            
            # All original keys must be present
            if not (original_keys <= translated_keys):
                missing_keys = original_keys - translated_keys
                logger.error(f"Missing keys in translated data: {missing_keys}")
                return False
            
            # Recursively check values for nested structures
            for key in original_keys:
                orig_val = original_data[key]
                trans_val = translated_data.get(key)
                
                if isinstance(orig_val, (dict, list)):
                    if not Validator.validate_json_structure(orig_val, trans_val):
                        logger.error(f"Structure mismatch at key '{key}'")
                        return False
            
            return True
            
        return True
