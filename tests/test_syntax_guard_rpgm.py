"""
Unit Tests for syntax_guard_rpgm.py
Tests protection, restoration, and injection logic for RPG Maker codes
"""
import unittest
from src.core.syntax_guard_rpgm import (
    protect_rpgm_syntax,
    protect_rpgm_syntax_html,
    restore_rpgm_syntax,
    validate_translation_integrity,
    inject_missing_placeholders,
)


class TestProtectRPGMSyntax(unittest.TestCase):
    """Test basic protection of RPG Maker codes"""
    
    def test_color_code_protection(self):
        """Test that color codes are protected"""
        text = r"Hello \c[1]Hero\c[0]!"
        protected, tokens = protect_rpgm_syntax(text)
        
        # Should contain tokens
        self.assertIn('⟦RPGM', protected)
        # Should not contain original codes
        self.assertNotIn(r'\c[1]', protected)
        # Tokens should map back to codes
        self.assertIn(r'\c[1]', tokens.values())
    
    def test_variable_bracket_protection(self):
        """Test [variable] bracket protection"""
        text = "Hello [player_name], you have [gold] gold!"
        protected, tokens = protect_rpgm_syntax(text)
        
        self.assertIn('⟦RPGM', protected)
        self.assertIn('[player_name]', tokens.values())
        self.assertIn('[gold]', tokens.values())
    
    def test_icon_code_protection(self):
        """Test icon codes"""
        text = r"Icon: \i[5] power!"
        protected, tokens = protect_rpgm_syntax(text)
        
        self.assertIn('⟦RPGM', protected)
        self.assertIn(r'\i[5]', tokens.values())
    
    def test_face_image_protection(self):
        """Test face image codes"""
        text = r"Start \f[heroface] speak"
        protected, tokens = protect_rpgm_syntax(text)
        
        self.assertIn('⟦RPGM', protected)
        self.assertIn(r'\f[heroface]', tokens.values())
    
    def test_wordwrap_tag_protection(self):
        """Test WordWrap tag"""
        text = "Long text <WordWrap> here"
        protected, tokens = protect_rpgm_syntax(text)
        
        self.assertIn('⟦RPGM', protected)
        self.assertIn('<WordWrap>', tokens.values())
    
    def test_bracket_flavor_tags_protection(self):
        """Test [sad], [happy], etc. tags"""
        text = "He felt [sad] and [confused]."
        protected, tokens = protect_rpgm_syntax(text)
        
        self.assertIn('⟦RPGM', protected)
        self.assertIn('[sad]', tokens.values())
    
    def test_complex_dialogue(self):
        """Test complex dialogue with multiple codes"""
        text = r"Hero \c[3]says\c[0]: [player]! Use \i[10] potion. <WordWrap>"
        protected, tokens = protect_rpgm_syntax(text)
        
        # Multiple tokens should exist
        token_count = protected.count('⟦RPGM')
        self.assertGreaterEqual(token_count, 3)
        
        # All codes should be in tokens
        self.assertIn(r'\c[3]', tokens.values())
        self.assertIn('[player]', tokens.values())
        self.assertIn(r'\i[10]', tokens.values())


class TestRestoreRPGMSyntax(unittest.TestCase):
    """Test restoration of RPG Maker codes"""
    
    def test_perfect_restoration(self):
        """Test that tokens restore to original codes perfectly"""
        original = r"Hello \c[1]Hero\c[0]!"
        protected, tokens = protect_rpgm_syntax(original)
        restored = restore_rpgm_syntax(protected, tokens)
        
        self.assertEqual(restored, original)
    
    def test_restoration_with_spaces(self):
        """Test fuzzy restoration - spaces added by Google"""
        original = r"Text \i[5] more"
        protected, tokens = protect_rpgm_syntax(original)
        
        # Simulate Google adding spaces
        spaced = protected.replace('⟦', '⟦ ').replace('⟧', ' ⟧')
        restored = restore_rpgm_syntax(spaced, tokens)
        
        self.assertEqual(restored, original)
    
    def test_restoration_with_bracket_mutation(self):
        """Test recovery from bracket substitution"""
        original = r"Use \i[5]"
        protected, tokens = protect_rpgm_syntax(original)
        
        # Simulate Google replacing ⟦⟧ with []
        mutated = protected.replace('⟦', '[').replace('⟧', ']')
        restored = restore_rpgm_syntax(mutated, tokens)
        
        self.assertEqual(restored, original)
    
    def test_multiple_codes_restoration(self):
        """Test restoration of multiple codes"""
        original = r"Hero \c[3]says\c[0]: [player]! \i[10] potion ready."
        protected, tokens = protect_rpgm_syntax(original)
        restored = restore_rpgm_syntax(protected, tokens)
        
        self.assertEqual(restored, original)


class TestValidationIntegrity(unittest.TestCase):
    """Test validation of translation integrity"""
    
    def test_complete_restoration(self):
        """Test that complete restoration passes validation"""
        original = r"Text \c[1]red\c[0]"
        protected, tokens = protect_rpgm_syntax(original)
        restored = restore_rpgm_syntax(protected, tokens)
        
        missing = validate_translation_integrity(restored, tokens)
        self.assertEqual(missing, [])
    
    def test_missing_code_detection(self):
        """Test detection of missing codes"""
        protected, tokens = protect_rpgm_syntax(r"Hello \c[1]red\c[0]!")
        
        # Create text missing the color codes
        incomplete = "Hello red!"
        missing = validate_translation_integrity(incomplete, tokens)
        
        # Should detect missing codes
        self.assertGreater(len(missing), 0)
        self.assertIn(r'\c[1]', missing)
    
    def test_case_insensitive_and_spaced_tolerance(self):
        """Test tolerant validation (spaces and case)"""
        protected, tokens = protect_rpgm_syntax("[player_name]")
        
        # Add spaces and case change
        fuzzy = "[ PLAYER_NAME ]"
        missing = validate_translation_integrity(fuzzy, tokens)
        
        # Should tolerate spaces and case
        self.assertEqual(missing, [])


class TestMissingPlaceholderInjection(unittest.TestCase):
    """Test injection of missing placeholders"""
    
    def test_injection_at_proportional_position(self):
        """Test that missing codes are injected at proportional position"""
        original = r"Start \i[5] middle text end"
        protected, tokens = protect_rpgm_syntax(original)
        
        # Simulate Google deleting the icon code entirely
        translated_without_icon = "Start  middle text end"  # Icon deleted
        
        # Inject missing code
        restored = inject_missing_placeholders(
            translated_without_icon,
            protected,
            tokens,
            [r'\i[5]']
        )
        
        # Should get icon back (not necessarily in exact position,
        # but present and with proper spacing)
        self.assertIn(r'\i[5]', restored)
        # Should not have double spaces
        self.assertNotIn('  ', restored.strip())
    
    def test_multiple_missing_injection(self):
        """Test injection of multiple missing codes"""
        original = r"\c[1]Hello\c[0] \i[5]world"
        protected, tokens = protect_rpgm_syntax(original)
        
        # Simulate complete loss
        partially_translated = "Hello world"
        
        restored = inject_missing_placeholders(
            partially_translated,
            protected,
            tokens,
            [r'\c[1]', r'\c[0]', r'\i[5]']
        )
        
        # All codes should be present
        self.assertIn(r'\c[1]', restored)
        self.assertIn(r'\i[5]', restored)


class TestHTMLProtection(unittest.TestCase):
    """Test HTML-based protection (for future multi-motor support)"""
    
    def test_html_wrapping(self):
        """Test that codes are wrapped in HTML spans"""
        text = r"Text \c[1]red\c[0] text"
        html_protected = protect_rpgm_syntax_html(text)
        
        # Should contain span tags
        self.assertIn('<span translate="no">', html_protected)
        self.assertIn('</span>', html_protected)
        
        # Should contain original codes inside spans
        self.assertIn(r'\c[1]', html_protected)
        self.assertIn(r'\c[0]', html_protected)


class TestComplexScenarios(unittest.TestCase):
    """Test complex real-world scenarios"""
    
    def test_nested_brackets(self):
        """Test handling of nested bracket constructs"""
        text = "[[Old format]] with [new_style]"
        protected, tokens = protect_rpgm_syntax(text)
        restored = restore_rpgm_syntax(protected, tokens)
        
        self.assertEqual(restored, text)
    
    def test_empty_input(self):
        """Test handling of empty input"""
        protected, tokens = protect_rpgm_syntax("")
        self.assertEqual(protected, "")
        self.assertEqual(tokens, {})
    
    def test_no_codes_input(self):
        """Test text without any codes"""
        text = "Just plain text with no codes"
        protected, tokens = protect_rpgm_syntax(text)
        
        self.assertEqual(protected, text)
        self.assertEqual(tokens, {})
    
    def test_plugin_style_face_nameplate(self):
        """Test advanced plugin: face + nameplate"""
        text = r"Start \f[heroface] \n<Artorius>"
        protected, tokens = protect_rpgm_syntax(text)
        restored = restore_rpgm_syntax(protected, tokens)
        
        self.assertEqual(restored, text)


if __name__ == '__main__':
    unittest.main()
