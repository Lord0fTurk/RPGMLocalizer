"""
Unit tests for JSStringTokenizer.
Tests extraction of string literals from JavaScript code.
"""
import unittest
from src.core.parsers.js_tokenizer import JSStringTokenizer


class TestJSStringTokenizer(unittest.TestCase):
    """Test JavaScript string literal extraction."""

    def setUp(self):
        self.tok = JSStringTokenizer()

    # --- extract_strings ---

    def test_double_quoted_string(self):
        tokens = self.tok.extract_strings('var x = "Hello World";')
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "Hello World")
        self.assertEqual(tokens[0][3], '"')

    def test_single_quoted_string(self):
        tokens = self.tok.extract_strings("var x = 'Hello';")
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "Hello")
        self.assertEqual(tokens[0][3], "'")

    def test_template_literal(self):
        tokens = self.tok.extract_strings("var x = `Hello ${name}`;")
        self.assertEqual(len(tokens), 1)
        # Template literal with expression → placeholder
        self.assertIn("Hello ", tokens[0][2])

    def test_escape_sequences(self):
        tokens = self.tok.extract_strings(r'var x = "Line1\nLine2";')
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "Line1\nLine2")

    def test_escaped_quotes(self):
        tokens = self.tok.extract_strings(r'var x = "He said \"hi\"";')
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], 'He said "hi"')

    def test_multiple_strings(self):
        code = '$gameMessage.add("Hello"); $gameMessage.add("World");'
        tokens = self.tok.extract_strings(code)
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0][2], "Hello")
        self.assertEqual(tokens[1][2], "World")

    def test_single_line_comment_skip(self):
        code = '// This is "a comment"\nvar x = "real string";'
        tokens = self.tok.extract_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "real string")

    def test_multi_line_comment_skip(self):
        code = '/* "not a string" */ var x = "real";'
        tokens = self.tok.extract_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "real")

    def test_empty_string(self):
        tokens = self.tok.extract_strings('var x = "";')
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "")

    def test_empty_input(self):
        tokens = self.tok.extract_strings("")
        self.assertEqual(len(tokens), 0)

    def test_no_strings(self):
        tokens = self.tok.extract_strings("var x = 42 + y;")
        self.assertEqual(len(tokens), 0)

    # --- extract_translatable_strings ---

    def test_filters_empty_strings(self):
        code = 'var x = ""; var y = "Hello World";'
        tokens = self.tok.extract_translatable_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "Hello World")

    def test_filters_file_paths(self):
        code = 'var img = "sprites/hero.png"; var text = "The hero arrives";'
        tokens = self.tok.extract_translatable_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "The hero arrives")

    def test_filters_boolean_strings(self):
        code = 'var a = "true"; var b = "Hello World";'
        tokens = self.tok.extract_translatable_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "Hello World")

    def test_filters_comparisons(self):
        code = 'if (x == "SWITCH") { $gameMessage.add("Press the switch"); }'
        tokens = self.tok.extract_translatable_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "Press the switch")

    def test_game_variables_set_value(self):
        code = '$gameVariables.setValue(5, "The quest begins!");'
        tokens = self.tok.extract_translatable_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "The quest begins!")

    def test_game_message_add(self):
        code = '$gameMessage.add("Welcome to the kingdom of Eldoria!");'
        tokens = self.tok.extract_translatable_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "Welcome to the kingdom of Eldoria!")

    def test_css_color_filtered(self):
        code = 'var color = "#FF0000"; var text = "Red is dangerous";'
        tokens = self.tok.extract_translatable_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "Red is dangerous")

    def test_snake_case_filtered(self):
        code = 'var id = "player_sprite"; var msg = "Welcome back";'
        tokens = self.tok.extract_translatable_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "Welcome back")

    # --- replace_string_at ---

    def test_replace_double_quoted(self):
        code = 'var x = "Hello World";'
        tokens = self.tok.extract_strings(code)
        start, end, _, quote = tokens[0]
        result = self.tok.replace_string_at(code, start, end, quote, "Merhaba Dünya")
        self.assertEqual(result, 'var x = "Merhaba Dünya";')

    def test_replace_single_quoted(self):
        code = "var x = 'Hello';"
        tokens = self.tok.extract_strings(code)
        start, end, _, quote = tokens[0]
        result = self.tok.replace_string_at(code, start, end, quote, "Merhaba")
        self.assertEqual(result, "var x = 'Merhaba';")

    def test_replace_preserves_context(self):
        code = '$gameMessage.add("Original text"); var x = 42;'
        tokens = self.tok.extract_strings(code)
        start, end, _, quote = tokens[0]
        result = self.tok.replace_string_at(code, start, end, quote, "Çevrilmiş metin")
        self.assertIn("Çevrilmiş metin", result)
        self.assertIn("var x = 42;", result)

    def test_replace_escapes_quotes(self):
        code = 'var x = "Hello";'
        tokens = self.tok.extract_strings(code)
        start, end, _, quote = tokens[0]
        # Translation contains a double quote
        result = self.tok.replace_string_at(code, start, end, quote, 'He said "hi"')
        self.assertIn('\\"', result)

    # --- Multi-line script merge scenario ---

    def test_multiline_script_extraction(self):
        """Simulates a 355+655 merged script block."""
        lines = [
            '$gameVariables.setValue(10,',
            '"The ancient sword has been found!");'
        ]
        merged = '\n'.join(lines)
        tokens = self.tok.extract_translatable_strings(merged)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "The ancient sword has been found!")

    def test_multiline_multiple_strings(self):
        lines = [
            'if (true) {',
            '  $gameMessage.add("First line");',
            '  $gameMessage.add("Second line");',
            '}'
        ]
        merged = '\n'.join(lines)
        tokens = self.tok.extract_translatable_strings(merged)
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0][2], "First line")
        self.assertEqual(tokens[1][2], "Second line")


class TestJSStringTokenizerEdgeCases(unittest.TestCase):
    """Edge case tests for JSStringTokenizer."""

    def setUp(self):
        self.tok = JSStringTokenizer()

    def test_adjacent_strings(self):
        code = '"Hello""World"'
        tokens = self.tok.extract_strings(code)
        self.assertEqual(len(tokens), 2)

    def test_unterminated_string(self):
        """Unterminated strings should not produce tokens."""
        code = 'var x = "unterminated'
        tokens = self.tok.extract_strings(code)
        self.assertEqual(len(tokens), 0)

    def test_regex_like_pattern(self):
        """Forward slashes in code shouldn't break parsing."""
        code = 'var x = 10 / 2; var y = "text";'
        tokens = self.tok.extract_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "text")

    def test_unicode_string(self):
        code = 'var x = "こんにちは世界";'
        tokens = self.tok.extract_translatable_strings(code, require_non_ascii_or_space=True)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "こんにちは世界")

    def test_number_string_filtered(self):
        code = 'var x = "12345"; var y = "Hello World";'
        tokens = self.tok.extract_translatable_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "Hello World")


if __name__ == '__main__':
    unittest.main()
