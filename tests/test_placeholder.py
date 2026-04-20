"""
Unit tests for syntax_guard_rpgm — the motor-aware token shield system.
Tests ⟦RPGM...⟧ token protection and 4-phase fuzzy restoration for RPG Maker codes.
"""
import unittest
from src.core.syntax_guard_rpgm import protect_for_translation, restore_from_translation


class TestPlaceholderProtection(unittest.TestCase):
    """Test RPG Maker syntax protection via syntax_guard_rpgm."""

    def test_variable_code_protection(self):
        """Variable codes like \\V[1] should be protected (bracket portion tokenized)."""
        text = "You have \\V[1] gold"
        protected, token_map = protect_for_translation(text)

        # [1] bracket portion is tokenized — full \V[1] no longer present
        self.assertNotIn("\\V[1]", protected)
        self.assertTrue(len(token_map) > 0)

        restored = restore_from_translation(protected, token_map)
        self.assertEqual(restored, text)

    def test_name_code_protection(self):
        """Name codes like \\N[1] should be protected (bracket portion tokenized)."""
        text = "\\N[1] is the hero"
        protected, token_map = protect_for_translation(text)

        self.assertNotIn("\\N[1]", protected)
        self.assertTrue(len(token_map) > 0)

        restored = restore_from_translation(protected, token_map)
        self.assertEqual(restored, text)

    def test_color_code_protection(self):
        """Color codes like \\C[1] should be protected (bracket portion tokenized)."""
        text = "\\C[1]Red text\\C[0]"
        protected, token_map = protect_for_translation(text)

        self.assertNotIn("\\C[1]", protected)
        self.assertTrue(len(token_map) > 0)

    def test_icon_code_protection(self) -> None:
        """Icon codes like \\i[4] should be fully protected."""
        text = "\\i[4] Sword of Destiny"
        protected, token_map = protect_for_translation(text)

        self.assertNotIn("\\i[4]", protected)
        self.assertIn("⟦", protected)

        restored = restore_from_translation(protected, token_map)
        self.assertEqual(restored, text)

    def test_wait_code_protection(self) -> None:
        """Wait code \\^ should be protected."""
        text = "Hello!\\^"
        protected, token_map = protect_for_translation(text)

        self.assertNotIn("\\^", protected)
        self.assertTrue(len(token_map) > 0)

        restored = restore_from_translation(protected, token_map)
        self.assertEqual(restored, text)

    def test_empty_string_returns_empty(self):
        """Empty string should return empty."""
        text = ""
        protected, token_map = protect_for_translation(text)

        self.assertEqual(protected, "")
        self.assertEqual(token_map, {})

    def test_no_codes_no_tokens(self):
        """Plain text with no RPG Maker codes should not create tokens."""
        text = "Simple text without codes"
        protected, token_map = protect_for_translation(text)

        self.assertEqual(protected, text)
        self.assertEqual(token_map, {})

    def test_note_and_meta_text_are_not_protected(self) -> None:
        """Plain note/meta prose should not be tokenized."""
        note_text = "note: This is a reminder"
        meta_text = "meta: Visible text"

        protected_note, map_note = protect_for_translation(note_text)
        protected_meta, map_meta = protect_for_translation(meta_text)

        self.assertEqual(protected_note, note_text)
        self.assertEqual(map_note, {})
        self.assertEqual(protected_meta, meta_text)
        self.assertEqual(map_meta, {})


class TestPlaceholderRestoration(unittest.TestCase):
    """Test token restoration via syntax_guard_rpgm."""

    def test_simple_code_restoration(self):
        """Protected codes should be restored."""
        original = "You have \\V[1] gold"
        protected, token_map = protect_for_translation(original)

        restored = restore_from_translation(protected, token_map)
        self.assertEqual(restored, original)

    def test_multiple_codes_restoration(self):
        """Multiple codes should be restored correctly."""
        original = "\\N[1] has \\i[5] items and \\C[4]power\\C[0]"
        protected, token_map = protect_for_translation(original)
        restored = restore_from_translation(protected, token_map)

        self.assertEqual(restored, original)

    def test_wait_code_restoration(self) -> None:
        """Wait code \\^ should survive protection and restore cleanly."""
        original = "Look out!\\^"
        protected, token_map = protect_for_translation(original)
        restored = restore_from_translation(protected, token_map)

        self.assertEqual(restored, original)

    def test_no_tokens_returns_text_unchanged(self):
        """Text with no tokens should be unchanged after restore."""
        text = "Some translated text"
        result = restore_from_translation(text, {})
        self.assertEqual(result, text)


if __name__ == '__main__':
    unittest.main()
