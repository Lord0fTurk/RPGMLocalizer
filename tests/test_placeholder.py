"""
Unit tests for syntax_guard_rpgm — segment-based RPG code protection.

v0.7.0: Tests the new segment-based approach where codes are stripped before
translation and re-inserted after, instead of the old token-based system.
"""
import unittest
from src.core.syntax_guard_rpgm import protect_for_translation, restore_from_translation
from src.core.text_segmenter import SegmentType


class TestPlaceholderProtection(unittest.TestCase):
    """Test RPG Maker syntax protection via syntax_guard_rpgm (segment-based)."""

    def test_variable_code_protection(self):
        """Variable codes like \\V[1] should be in CODE segments, not in clean text."""
        text = "You have \\V[1] gold"
        clean, segments = protect_for_translation(text)

        self.assertNotIn("\\V[1]", clean)
        self.assertTrue(len(segments) > 0)
        self.assertTrue(any(s.type == SegmentType.CODE for s in segments))

        restored = restore_from_translation(clean, segments)
        self.assertEqual(restored, text)

    def test_name_code_protection(self):
        """Name codes like \\N[1] should be in CODE segments."""
        text = "\\N[1] is the hero"
        clean, segments = protect_for_translation(text)

        self.assertNotIn("\\N[1]", clean)
        self.assertTrue(any(s.type == SegmentType.CODE for s in segments))

        restored = restore_from_translation(clean, segments)
        self.assertEqual(restored, text)

    def test_color_code_protection(self):
        """Color codes like \\C[1] should be in CODE segments."""
        text = "\\C[1]Red text\\C[0]"
        clean, segments = protect_for_translation(text)

        self.assertNotIn("\\C[1]", clean)
        self.assertNotIn("\\C[0]", clean)
        self.assertTrue(any(s.type == SegmentType.CODE for s in segments))

        restored = restore_from_translation(clean, segments)
        self.assertEqual(restored, text)

    def test_icon_code_protection(self) -> None:
        """Icon codes like \\i[4] should be in CODE segments."""
        text = "\\i[4] Sword of Destiny"
        clean, segments = protect_for_translation(text)

        self.assertNotIn("\\i[4]", clean)
        self.assertTrue(any(s.type == SegmentType.CODE for s in segments))

        restored = restore_from_translation(clean, segments)
        self.assertEqual(restored, text)

    def test_wait_code_protection(self) -> None:
        """Wait code \\^ should be in CODE segments."""
        text = "Hello!\\^"
        clean, segments = protect_for_translation(text)

        self.assertNotIn("\\^", clean)
        self.assertTrue(any(s.type == SegmentType.CODE for s in segments))

        restored = restore_from_translation(clean, segments)
        self.assertEqual(restored, text)

    def test_empty_string_returns_empty(self):
        """Empty string should return empty."""
        text = ""
        clean, segments = protect_for_translation(text)

        self.assertEqual(clean, "")
        self.assertTrue(len(segments) == 1)
        self.assertEqual(segments[0].type, SegmentType.TEXT)

    def test_no_codes_no_tokens(self):
        """Plain text with no RPG Maker codes should have no CODE segments."""
        text = "Simple text without codes"
        clean, segments = protect_for_translation(text)

        self.assertEqual(clean, text)
        self.assertFalse(any(s.type == SegmentType.CODE for s in segments))

    def test_note_and_meta_text_are_not_protected(self) -> None:
        """Plain note/meta prose should have no CODE segments."""
        note_text = "note: This is a reminder"
        meta_text = "meta: Visible text"

        clean_note, segments_note = protect_for_translation(note_text)
        clean_meta, segments_meta = protect_for_translation(meta_text)

        self.assertEqual(clean_note, note_text)
        self.assertEqual(clean_meta, meta_text)
        self.assertFalse(any(s.type == SegmentType.CODE for s in segments_note))

    def test_roundtrip_with_translated_text(self):
        """Simulate the full pipeline: original → clean → translated → restored."""
        original = r"Hello \c[1]World\c[0]! \i[5]"
        clean, segments = protect_for_translation(original)

        # Clean text has no codes
        self.assertNotIn("\\c[1]", clean)
        self.assertNotIn("\\c[0]", clean)
        self.assertNotIn("\\i[5]", clean)

        # Simulate translation (with separators preserved)
        translated_clean = "Merhaba|||TXTSEG|||Dünya|||TXTSEG|||! |||TXTSEG|||"
        restored = restore_from_translation(translated_clean, segments)

        # Codes are back in their original positions
        self.assertIn("\\c[1]", restored)
        self.assertIn("\\c[0]", restored)
        self.assertIn("\\i[5]", restored)
        self.assertIn("Merhaba", restored)
        self.assertIn("Dünya", restored)


class TestPlaceholderRestoration(unittest.TestCase):
    """Test segment-based restoration via syntax_guard_rpgm."""

    def test_simple_code_restoration(self):
        """Protected codes should be restored via segments."""
        original = "You have \\V[1] gold"
        clean, segments = protect_for_translation(original)

        restored = restore_from_translation(clean, segments)
        self.assertEqual(restored, original)

    def test_multiple_codes_restoration(self):
        """Multiple codes should be restored correctly."""
        original = "\\N[1] has \\i[5] items and \\C[4]power\\C[0]"
        clean, segments = protect_for_translation(original)

        restored = restore_from_translation(clean, segments)
        self.assertEqual(restored, original)

    def test_wait_code_restoration(self) -> None:
        """Wait code \\^ should survive protection and restore cleanly."""
        original = "Look out!\\^"
        clean, segments = protect_for_translation(original)

        restored = restore_from_translation(clean, segments)
        self.assertEqual(restored, original)

    def test_no_segments_returns_text_unchanged(self):
        """Text with no segments should be unchanged after restore."""
        text = "Some translated text"
        result = restore_from_translation(text, [])
        self.assertEqual(result, text)

    def test_separator_lost_fallback(self):
        """When separator is lost, fallback should still preserve codes."""
        original = r"Use \i[5] potion"
        clean, segments = protect_for_translation(original)

        # Simulate Google losing the separator
        mangled = "Use potion"
        restored = restore_from_translation(mangled, segments)

        # Codes should still be present (via proportional fallback)
        self.assertIn("\\i[5]", restored)


if __name__ == '__main__':
    unittest.main()
