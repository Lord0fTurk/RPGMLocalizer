"""
Unit tests for placeholder protection and restoration.
Tests XRPYX system for preserving RPG Maker control codes.
"""
import unittest
from src.utils.placeholder import protect_rpgm_syntax, restore_rpgm_syntax


class TestPlaceholderProtection(unittest.TestCase):
    """Test RPG Maker syntax protection."""
    
    def test_variable_code_protection(self):
        """Variable codes like \\V[1] should be protected."""
        text = "You have \\V[1] gold"
        protected, placeholders = protect_rpgm_syntax(text)
        
        # Should contain a placeholder instead of \\V[1]
        self.assertNotIn("\\V[1]", protected)
        self.assertTrue(len(placeholders) > 0)
    
    def test_name_code_protection(self):
        """Name codes like \\N[1] should be protected."""
        text = "\\N[1] is the hero"
        protected, placeholders = protect_rpgm_syntax(text)
        
        self.assertNotIn("\\N[1]", protected)
        self.assertTrue(len(placeholders) > 0)
    
    def test_color_code_protection(self):
        """Color codes like \\C[1] should be protected."""
        text = "\\C[1]Red text\\C[0]"
        protected, placeholders = protect_rpgm_syntax(text)
        
        self.assertNotIn("\\C[1]", protected)
        self.assertTrue(len(placeholders) > 0)
    
    def test_empty_string_returns_empty(self):
        """Empty string should return empty."""
        text = ""
        protected, placeholders = protect_rpgm_syntax(text)
        
        self.assertEqual(protected, "")
        self.assertEqual(placeholders, {})
    
    def test_no_codes_no_placeholders(self):
        """Plain text with no codes shouldn't create placeholders."""
        text = "Simple text without codes"
        protected, placeholders = protect_rpgm_syntax(text)
        
        self.assertEqual(protected, text)
        self.assertEqual(placeholders, {})


class TestPlaceholderRestoration(unittest.TestCase):
    """Test placeholder restoration."""
    
    def test_simple_code_restoration(self):
        """Protected codes should be restored."""
        original = "You have \\V[1] gold"
        protected, placeholders = protect_rpgm_syntax(original)
        
        # Simulate translation (text doesn't change in this case)
        translated = protected
        
        restored = restore_rpgm_syntax(translated, placeholders)
        self.assertEqual(restored, original)
    
    def test_multiple_codes_restoration(self):
        """Multiple codes should be restored correctly."""
        original = "\\N[1] has \\V[5] items"
        protected, placeholders = protect_rpgm_syntax(original)
        translated = protected
        restored = restore_rpgm_syntax(translated, placeholders)
        
        self.assertEqual(restored, original)
    
    def test_no_placeholders_returns_text_unchanged(self):
        """Text with no placeholders should be unchanged."""
        text = "Some translated text"
        result = restore_rpgm_syntax(text, {})
        self.assertEqual(result, text)


if __name__ == '__main__':
    unittest.main()
