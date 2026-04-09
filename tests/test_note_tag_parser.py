"""
Unit tests for NoteTagParser.
Tests extraction of translatable text from RPG Maker note fields.
"""
import unittest
from src.core.parsers.note_tag_parser import NoteTagParser


class TestNoteTagParser(unittest.TestCase):
    """Test note tag parsing and text extraction."""

    def setUp(self):
        self.parser = NoteTagParser()

    def test_value_tag_extraction(self):
        """Simple value tags like <Tag: value> should be parsed."""
        note = "<Description: A powerful sword>"
        parsed = self.parser.parse_note(note)
        self.assertTrue(len(parsed) > 0)
        # 'description' is in TEXT_VALUE_TAGS, so should be translatable
        texts = self.parser.extract_translatable(note)
        self.assertIn("A powerful sword", texts)

    def test_skip_numeric_value_tags(self):
        """Tags with numeric values should not be translatable."""
        note = "<Price: 100>\n<HP: 500>"
        texts = self.parser.extract_translatable(note)
        self.assertEqual(len(texts), 0)

    def test_technical_note_values_are_skipped(self):
        """Identifier-like or asset-like note values should not be treated as text."""
        note = (
            "<Quest Reward: 100>\n"
            "<Display Name: img/system/Window.png>\n"
            "<Summary: Quest_01>"
        )
        texts = self.parser.extract_translatable(note)
        self.assertNotIn("100", texts)
        self.assertNotIn("img/system/Window.png", texts)
        self.assertNotIn("Quest_01", texts)

    def test_block_tag_extraction(self):
        """Multi-line block tags should have their content extracted."""
        note = "<Custom Death Message>\n%1 has been slain!\n</Custom Death Message>"
        texts = self.parser.extract_translatable(note)
        self.assertIn("%1 has been slain!", texts)

    def test_free_text_extraction(self):
        """Free text between tags should be extracted if it looks like text."""
        note = "<SType: Magic>\nThis item restores health.\n<Price: 50>"
        texts = self.parser.extract_translatable(note)
        self.assertIn("This item restores health.", texts)

    def test_mixed_content(self):
        """Notes with mixed tags and text should be parsed correctly."""
        note = "<Element: Fire>\n<Help Text: Cast a fireball>\n<Icon: 128>"
        texts = self.parser.extract_translatable(note)
        self.assertIn("Cast a fireball", texts)

    def test_common_plugin_family_tags(self):
        """Common Yanfly, VisuStella, Galv, and MOG tags should be extractable."""
        note = (
            "<Display Name: Hero Title>\n"
            "<Display Text: Welcome to the forest>\n"
            "<Popup Text: Critical Hit!>\n"
            "<Battle Text: A wild slime appears>\n"
            "<Title: The Lost Relic>"
        )
        texts = self.parser.extract_translatable(note)
        self.assertIn("Hero Title", texts)
        self.assertIn("Welcome to the forest", texts)
        self.assertIn("Critical Hit!", texts)
        self.assertIn("A wild slime appears", texts)
        self.assertIn("The Lost Relic", texts)

    def test_quest_journal_tags(self):
        """Quest/journal style note tags should be extractable."""
        note = (
            "<Quest Name: A Hero's Beginning>\n"
            "<Quest Objective: Find the old sword>\n"
            "<Quest Reward: 100 Gold>\n"
            "<Summary: The village elder needs help>"
        )
        texts = self.parser.extract_translatable(note)
        self.assertIn("A Hero's Beginning", texts)
        self.assertIn("Find the old sword", texts)
        self.assertIn("100 Gold", texts)
        self.assertIn("The village elder needs help", texts)

    def test_empty_note(self):
        """Empty notes should return no segments."""
        self.assertEqual(self.parser.parse_note(""), [])
        self.assertEqual(self.parser.parse_note("   "), [])
        self.assertEqual(self.parser.extract_translatable(""), [])

    def test_technical_tags_skipped(self):
        """Technical tags like <eval>, <formula> should not be translatable."""
        note = "<Eval: $gameVariables.value(1)>"
        texts = self.parser.extract_translatable(note)
        self.assertEqual(len(texts), 0)

    def test_rebuild_replaces_value_tag(self):
        """rebuild_note should replace value tag content."""
        note = "<Description: A powerful sword>"
        translations = {"A powerful sword": "Güçlü bir kılıç"}
        result = self.parser.rebuild_note(note, translations)
        self.assertIn("Güçlü bir kılıç", result)
        self.assertIn("Description", result)  # tag name preserved

    def test_rebuild_replaces_block_tag(self):
        """rebuild_note should replace block tag content."""
        note = "<Custom Death Message>\n%1 has been slain!\n</Custom Death Message>"
        translations = {"%1 has been slain!": "%1 öldürüldü!"}
        result = self.parser.rebuild_note(note, translations)
        self.assertIn("%1 öldürüldü!", result)
        self.assertIn("Custom Death Message", result)

    def test_rebuild_empty_translations(self):
        """rebuild_note with empty dict should return original."""
        note = "<Description: A text>"
        result = self.parser.rebuild_note(note, {})
        self.assertEqual(result, note)


class TestNoteTagParserEdgeCases(unittest.TestCase):
    """Edge case tests for NoteTagParser."""

    def setUp(self):
        self.parser = NoteTagParser()

    def test_nested_angle_brackets(self):
        """Notes with nested < > should not crash."""
        note = "<Description: Use <Potion> to heal>"
        # Should still parse without error
        parsed = self.parser.parse_note(note)
        self.assertIsInstance(parsed, list)

    def test_single_tag(self):
        """Single tags without values should be recognized."""
        note = "<CannotUseInBattle>\nA special item.\n<RemoveOnDeath>"
        texts = self.parser.extract_translatable(note)
        self.assertIn("A special item.", texts)

    def test_non_ascii_text_detected(self):
        """Non-ASCII text should be detected as translatable."""
        self.assertTrue(self.parser._looks_like_text("これは説明です"))

    def test_short_text_not_translatable(self):
        """Very short text without indicators should not be translatable."""
        self.assertFalse(self.parser._looks_like_text("ab"))

    def test_text_with_punctuation(self):
        """Text with punctuation should be translatable."""
        self.assertTrue(self.parser._looks_like_text("Fire!"))
        self.assertTrue(self.parser._looks_like_text("Hello, world."))


if __name__ == '__main__':
    unittest.main()
