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

    def test_brace_placeholder_protection(self) -> None:
        """Simple brace placeholders like {name} should be protected."""
        text = "\\i[4]{name}"
        protected, placeholders = protect_rpgm_syntax(text)

        self.assertNotIn("{name}", protected)
        self.assertTrue(len(placeholders) > 0)

    def test_percent_placeholder_protection(self) -> None:
        """Numbered percent placeholders like %1 should be protected."""
        text = "Loading %1"
        protected, placeholders = protect_rpgm_syntax(text)

        self.assertNotIn("%1", protected)
        self.assertTrue(len(placeholders) > 0)

    def test_printf_style_placeholder_protection(self) -> None:
        """Printf-style placeholders like %s and %0.2f should be protected."""
        text = "HP: %d / %s, Rate: %0.2f"
        protected, placeholders = protect_rpgm_syntax(text)

        self.assertNotIn("%d", protected)
        self.assertNotIn("%s", protected)
        self.assertNotIn("%0.2f", protected)
        self.assertTrue(len(placeholders) >= 3)
    
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

    def test_note_and_meta_text_are_not_protected(self) -> None:
        """Plain note/meta prose should not be protected as technical code."""
        note_text = "note: This is a reminder"
        meta_text = "meta: Visible text"

        protected_note, placeholders_note = protect_rpgm_syntax(note_text)
        protected_meta, placeholders_meta = protect_rpgm_syntax(meta_text)

        self.assertEqual(protected_note, note_text)
        self.assertEqual(placeholders_note, {})
        self.assertEqual(protected_meta, meta_text)
        self.assertEqual(placeholders_meta, {})


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

    def test_brace_placeholder_restoration(self) -> None:
        """Brace placeholders should survive translation and restore cleanly."""
        original = "\\i[4]{name}"
        protected, placeholders = protect_rpgm_syntax(original)
        translated = protected
        restored = restore_rpgm_syntax(translated, placeholders)

        self.assertEqual(restored, original)

    def test_percent_placeholder_restoration(self) -> None:
        """Percent placeholders should survive translation and restore cleanly."""
        original = "Loading %1"
        protected, placeholders = protect_rpgm_syntax(original)
        translated = protected
        restored = restore_rpgm_syntax(translated, placeholders)

        self.assertEqual(restored, original)

    def test_printf_style_placeholder_restoration(self) -> None:
        """Printf-style placeholders should survive translation and restore cleanly."""
        original = "HP: %d / %s, Rate: %0.2f"
        protected, placeholders = protect_rpgm_syntax(original)
        translated = protected
        restored = restore_rpgm_syntax(translated, placeholders)

        self.assertEqual(restored, original)

    def test_mixed_placeholder_stress_restoration(self) -> None:
        """Mixed RPG Maker placeholders should survive together without collisions."""
        original = "\\i[4]{name} - Loading %1 - HP: %d - Rate: %0.2f - \\C[4]Ready\\C[0]"
        protected, placeholders = protect_rpgm_syntax(original)
        translated = protected
        restored = restore_rpgm_syntax(translated, placeholders)

        self.assertEqual(restored, original)

    def test_extreme_mixed_placeholder_stress_restoration(self) -> None:
        """Multiple placeholder families should restore without interfering."""
        original = (
            "\\i[4]{name} - Loading %1 - HP: %d - Rate: %0.2f - "
            "\\C[4]Ready\\C[0] - #{questId} - ${playerName}"
        )
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
