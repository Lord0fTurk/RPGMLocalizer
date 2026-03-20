"""
Unit tests for the Validator module.
Tests validation logic for translation integrity.
"""
import unittest
from src.core.validation import Validator


class TestValidationEntry(unittest.TestCase):
    """Test single translation entry validation."""
    
    def test_empty_original_returns_true(self):
        """Empty original text should pass validation."""
        result = Validator.validate_translation_entry("", "some translation", {})
        self.assertTrue(result)
    
    def test_empty_translation_returns_false(self):
        """Empty translation for non-empty original should fail."""
        result = Validator.validate_translation_entry("Hello", "", {})
        self.assertFalse(result)
    
    def test_whitespace_original_returns_true(self):
        """Whitespace-only original should pass."""
        result = Validator.validate_translation_entry("   ", "translation", {})
        self.assertTrue(result)


class TestJsonStructureValidation(unittest.TestCase):
    """Test JSON structure validation."""
    
    def test_dict_missing_keys_fails(self):
        """Missing keys in translated dict should fail."""
        original = {'name': 'John', 'age': 30}
        translated = {'name': 'Juan'}  # Missing 'age'
        result = Validator.validate_json_structure(original, translated)
        self.assertFalse(result)
    
    def test_dict_all_keys_present_passes(self):
        """Dict with all keys should pass."""
        original = {'name': 'John', 'age': 30}
        translated = {'name': 'Juan', 'age': 30, 'extra': 'ok'}
        result = Validator.validate_json_structure(original, translated)
        self.assertTrue(result)
    
    def test_list_length_mismatch_fails(self):
        """List length mismatch should fail."""
        original = [1, 2, 3]
        translated = [1, 2]
        result = Validator.validate_json_structure(original, translated)
        self.assertFalse(result)
    
    def test_list_length_match_passes(self):
        """List with matching length should pass."""
        original = [1, 2, 3]
        translated = [10, 20, 30]
        result = Validator.validate_json_structure(original, translated)
        self.assertTrue(result)
    
    def test_nested_dict_missing_keys_fails(self):
        """Nested dict with missing keys should fail."""
        original = {
            'player': {'name': 'John', 'level': 10}
        }
        translated = {
            'player': {'name': 'Juan'}  # Missing 'level'
        }
        result = Validator.validate_json_structure(original, translated)
        self.assertFalse(result)
    
    def test_type_mismatch_fails(self):
        """Type mismatch should fail."""
        original = {'key': 'value'}
        translated = ['value']
        result = Validator.validate_json_structure(original, translated)
        self.assertFalse(result)
    
    def test_empty_dict_passes(self):
        """Empty dicts should pass."""
        original = {}
        translated = {}
        result = Validator.validate_json_structure(original, translated)
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
