"""
Unit tests for translator configuration.
Tests language setting propagation.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from src.core.translator import GoogleTranslator


class TestTranslatorLanguageConfig(unittest.TestCase):
    """Test that language settings from request metadata actually drive GoogleTranslator.

    Only the network layer (`_try_translate`) is mocked; `translate_batch()` itself
    runs for real so a regression in metadata handling would fail this test.
    """

    def test_translator_uses_metadata_languages(self):
        """Translator should use languages from request metadata."""
        translator = GoogleTranslator()
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

        with patch.object(translator, '_try_translate', new=AsyncMock(return_value=['Merhaba dunya'])) as mock_try:
            results = asyncio.run(translator.translate_batch(requests))

        self.assertEqual(results[0].source_lang, 'en')
        self.assertEqual(results[0].target_lang, 'tr')
        self.assertEqual(results[0].translated_text, 'Merhaba dunya')
        mock_try.assert_awaited_once()
        called_source, called_target = mock_try.await_args.args[1], mock_try.await_args.args[2]
        self.assertEqual(called_source, 'en')
        self.assertEqual(called_target, 'tr')

    def test_translator_defaults_to_auto_and_en(self):
        """Translator should default to 'auto' and 'en' if metadata missing."""
        translator = GoogleTranslator()
        requests = [
            {
                'text': 'Hello world',
                'metadata': {}  # No language in metadata
            }
        ]

        with patch.object(translator, '_try_translate', new=AsyncMock(return_value=['Hello world'])) as mock_try:
            results = asyncio.run(translator.translate_batch(requests))

        self.assertEqual(results[0].source_lang, 'auto')
        self.assertEqual(results[0].target_lang, 'en')
        called_source, called_target = mock_try.await_args.args[1], mock_try.await_args.args[2]
        self.assertEqual(called_source, 'auto')
        self.assertEqual(called_target, 'en')


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
    
    def test_ruby_shift_jis_fallback_decodes_legacy_bytes(self):
        """_safe_decode_ruby_string should recover Shift-JIS text via its manual fallback chain."""
        from src.core.parsers.ruby_parser import _safe_decode_ruby_string

        raw = "テスト".encode("shift_jis")  # invalid as UTF-8, must fall back
        info = _safe_decode_ruby_string(raw)

        self.assertEqual(info.text, "テスト")
        self.assertTrue(info.is_bytes)
        self.assertIn(info.encoding.lower().replace("-", "_"), ("shift_jis", "sjis"))


if __name__ == '__main__':
    unittest.main()
