"""
Unit Tests for syntax_guard_rpgm.py (v0.7.0 — Segment-Based)

Tests the new segment-based protection where RPG Maker codes are structurally
separated from translatable text instead of using token-based protection.
"""
import unittest
from src.core.syntax_guard_rpgm import (
    protect_rpgm_syntax,
    protect_rpgm_syntax_html,
    restore_rpgm_syntax,
    validate_translation_integrity,
    inject_missing_placeholders,
)
from src.core.text_segmenter import (
    segment_text,
    clean_text as segmenter_clean,
    reassemble as segmenter_reassemble,
    SegmentType,
)


class TestSegmentBasedProtection(unittest.TestCase):
    """Test the new segment-based code protection (v0.7.0)."""

    def test_color_code_protection(self):
        """Color codes should be in CODE segments, clean text has no codes."""
        text = r"Hello \c[1]Hero\c[0]!"
        clean, segments = segmenter_clean(text)

        self.assertNotIn(r'\c[1]', clean)
        self.assertNotIn(r'\c[0]', clean)
        code_segs = [s for s in segments if s.type == SegmentType.CODE]
        self.assertEqual(len(code_segs), 2)

    def test_variable_bracket_protection(self):
        """[variable] brackets should be CODE segments."""
        text = "Hello [player_name], you have [gold] gold!"
        clean, segments = segmenter_clean(text)

        self.assertNotIn('[player_name]', clean)
        self.assertNotIn('[gold]', clean)
        code_segs = [s for s in segments if s.type == SegmentType.CODE]
        self.assertEqual(len(code_segs), 2)

    def test_icon_code_protection(self):
        """Icon codes should be CODE segments."""
        text = r"Icon: \i[5] power!"
        clean, segments = segmenter_clean(text)

        self.assertNotIn(r'\i[5]', clean)
        code_segs = [s for s in segments if s.type == SegmentType.CODE]
        self.assertGreaterEqual(len(code_segs), 1)

    def test_face_image_protection(self):
        """Face image codes should be CODE segments."""
        text = r"Start \f[heroface] speak"
        clean, segments = segmenter_clean(text)

        self.assertNotIn(r'\f[heroface]', clean)
        code_segs = [s for s in segments if s.type == SegmentType.CODE]
        self.assertGreaterEqual(len(code_segs), 1)

    def test_wordwrap_tag_protection(self):
        """WordWrap tag should be a CODE segment."""
        text = "Long text <WordWrap> here"
        clean, segments = segmenter_clean(text)

        self.assertNotIn('<WordWrap>', clean)
        code_segs = [s for s in segments if s.type == SegmentType.CODE]
        self.assertGreaterEqual(len(code_segs), 1)

    def test_bracket_flavor_tags_protection(self):
        """[sad], [happy] tags should be CODE segments."""
        text = "He felt [sad] and [confused]."
        clean, segments = segmenter_clean(text)

        self.assertNotIn('[sad]', clean)
        self.assertNotIn('[confused]', clean)
        code_segs = [s for s in segments if s.type == SegmentType.CODE]
        self.assertGreaterEqual(len(code_segs), 2)

    def test_complex_dialogue(self):
        """Complex dialogue should correctly separate all codes."""
        text = r"Hero \c[3]says\c[0]: [player]! \i[10] potion. <WordWrap>"
        clean, segments = segmenter_clean(text)

        code_segs = [s for s in segments if s.type == SegmentType.CODE]
        self.assertGreaterEqual(len(code_segs), 4)

        # Verify each code is in a segment
        code_contents = [s.content for s in code_segs]
        self.assertIn(r'\c[3]', code_contents)
        self.assertIn('[player]', code_contents)
        self.assertIn(r'\i[10]', code_contents)
        self.assertIn('<WordWrap>', code_contents)


class TestSegmentBasedRestoration(unittest.TestCase):
    """Test segment-based restoration."""

    def test_perfect_restoration(self):
        """Segment-based restore should perfectly reconstruct original."""
        original = r"Hello \c[1]Hero\c[0]!"
        clean, segments = segmenter_clean(original)
        restored = segmenter_reassemble(clean, segments)
        self.assertEqual(restored, original)

    def test_restoration_with_translated_text(self):
        """Test restoration with actual translated (simulated) clean text."""
        original = r"Text \i[5] more"
        clean, segments = segmenter_clean(original)

        # Simulate translation preserving separator
        translated = "Metin|||TXTSEG|||daha fazla"
        restored = segmenter_reassemble(translated, segments)

        self.assertIn(r'\i[5]', restored)
        self.assertIn("Metin", restored)
        self.assertIn("daha fazla", restored)

    def test_multiple_codes_restoration(self):
        """Test restoration of multiple codes."""
        original = r"Hero \c[3]says\c[0]: [player]! \i[10] potion ready."
        clean, segments = segmenter_clean(original)
        restored = segmenter_reassemble(clean, segments)
        self.assertEqual(restored, original)


class TestNestedBrackets(unittest.TestCase):
    """Test handling of nested/escaped bracket constructs."""

    def test_nested_brackets_restoration(self):
        """[[Old format]] should be preserved."""
        text = "[[Old format]] with [new_style]"
        clean, segments = segmenter_clean(text)
        restored = segmenter_reassemble(clean, segments)
        self.assertEqual(restored, text)

    def test_empty_input(self):
        """Empty input should return empty TEXT segment."""
        segments = segment_text("")
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, SegmentType.TEXT)
        self.assertEqual(segments[0].content, "")

    def test_no_codes_input(self):
        """Plain text should have no CODE segments."""
        text = "Just plain text with no codes"
        clean, segments = segmenter_clean(text)
        self.assertEqual(clean, text)
        self.assertFalse(any(s.type == SegmentType.CODE for s in segments))

    def test_plugin_style_face_nameplate(self):
        """Advanced plugin codes should be CODE segments."""
        text = r"Start \f[heroface] \n<Artorius>"
        clean, segments = segmenter_clean(text)
        restored = segmenter_reassemble(clean, segments)
        self.assertEqual(restored, text)


class TestLegacyWrapper(unittest.TestCase):
    """Test that legacy `protect_rpgm_syntax` / `restore_rpgm_syntax` wrappers
    still provide basic backward-compatible behavior."""

    def test_legacy_protect(self):
        """Legacy protect should return clean text (no codes, no tokens)."""
        original = r"Hello \c[1]Hero\c[0]!"
        protected, tokens = protect_rpgm_syntax(original)

        # Clean text has no codes or tokens
        self.assertNotIn(r'\c[1]', protected)
        self.assertNotIn(r'⟦', protected)
        self.assertNotIn(r'\c[0]', protected)

        # Token map has entries for each code
        self.assertGreaterEqual(len(tokens), 2)

    def test_legacy_no_codes(self):
        """Text without codes should pass through unchanged."""
        text = "Just plain text"
        protected, tokens = protect_rpgm_syntax(text)
        self.assertEqual(protected, text)
        restored = restore_rpgm_syntax(protected, tokens)
        self.assertEqual(restored, text)

    def test_legacy_empty(self):
        """Empty string should work."""
        protected, tokens = protect_rpgm_syntax("")
        self.assertEqual(protected, "")
        self.assertEqual(tokens, {})

    def test_legacy_validate_noop(self):
        """validate_translation_integrity should be a no-op (always empty)."""
        _, tokens = protect_rpgm_syntax(r"Hello \c[1]World\c[0]!")
        missing = validate_translation_integrity("Hello World", tokens)
        self.assertEqual(missing, [])

    def test_legacy_inject_noop(self):
        """inject_missing_placeholders should be a no-op."""
        result = inject_missing_placeholders("Hello World", "", {}, [r'\c[1]'])
        self.assertEqual(result, "Hello World")


if __name__ == '__main__':
    unittest.main()
