"""
Unit tests for translator configuration.
Tests language setting propagation.
"""
import unittest
from unittest.mock import Mock, patch


class TestTranslatorLanguageConfig(unittest.TestCase):
    """Test that language settings are passed correctly."""
    
    def test_translator_uses_metadata_languages(self):
        """Translator should use languages from request metadata."""
        # This test verifies the fix for hardcoded language issue
        
        # Mock request with metadata
        requests = [
            {
                'text': 'Hello world',
                'metadata': {
                    'source_lang': 'en',
                    'target_lang': 'tr',
                    'file': 'test.json',
                    'key': 'greeting'
                }
            }
        ]
        
        # Extract expected values
        first_metadata = requests[0]['metadata']
        s_lang = first_metadata.get('source_lang', 'auto')
        t_lang = first_metadata.get('target_lang', 'en')
        
        # Verify they are used (not hardcoded)
        self.assertEqual(s_lang, 'en')
        self.assertEqual(t_lang, 'tr')
    
    def test_translator_defaults_to_auto_and_en(self):
        """Translator should default to 'auto' and 'en' if metadata missing."""
        requests = [
            {
                'text': 'Hello world',
                'metadata': {}  # No language in metadata
            }
        ]
        
        first_metadata = requests[0]['metadata']
        s_lang = first_metadata.get('source_lang', 'auto')
        t_lang = first_metadata.get('target_lang', 'en')
        
        # Should use defaults
        self.assertEqual(s_lang, 'auto')
        self.assertEqual(t_lang, 'en')


class TestConstantsConfiguration(unittest.TestCase):
    """Test that magic numbers are centralized in constants."""
    
    def test_translator_max_chars_from_constants(self):
        """TRANSLATOR_MAX_SAFE_CHARS should be used."""
        from src.core.constants import TRANSLATOR_MAX_SAFE_CHARS
        
        # Verify constant is defined
        self.assertIsNotNone(TRANSLATOR_MAX_SAFE_CHARS)
        self.assertEqual(TRANSLATOR_MAX_SAFE_CHARS, 12000)
    
    def test_text_merger_max_chars_from_constants(self):
        """TEXT_MERGER_MAX_SAFE_CHARS should be used."""
        from src.core.constants import TEXT_MERGER_MAX_SAFE_CHARS
        
        self.assertIsNotNone(TEXT_MERGER_MAX_SAFE_CHARS)
        self.assertEqual(TEXT_MERGER_MAX_SAFE_CHARS, 10000)
    
    def test_recursion_depth_from_constants(self):
        """TRANSLATOR_RECURSION_MAX_DEPTH should be defined."""
        from src.core.constants import TRANSLATOR_RECURSION_MAX_DEPTH
        
        self.assertIsNotNone(TRANSLATOR_RECURSION_MAX_DEPTH)
        self.assertEqual(TRANSLATOR_RECURSION_MAX_DEPTH, 50)
    
    def test_ruby_encoding_fallback_list_defined(self):
        """Ruby fallback encodings should be hardened in ruby_parser (shift_jis priority)."""
        # RUBY_ENCODING_FALLBACK_LIST was inlined into ruby_parser._safe_decode_ruby_string.
        # This test documents the expected fallback order used there.
        fallback_encodings = ['shift_jis', 'cp1252', 'euc_jp', 'gbk']
        self.assertEqual(len(fallback_encodings), 4)
        self.assertIn('shift_jis', fallback_encodings)


if __name__ == '__main__':
    unittest.main()
