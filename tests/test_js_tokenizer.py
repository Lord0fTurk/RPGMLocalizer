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

    def test_string_raw_template_is_skipped(self):
        """String.raw tagged templates should be treated as technical."""
        code = r'const p = String.raw`C:\\Temp\\${name}`; var y = "safe";'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertNotIn(r'C:\Temp\${name}', values)
        self.assertIn("safe", values)

    def test_plain_template_literal_can_still_be_extracted(self):
        """Ordinary template literals should still be considered when textual."""
        code = 'const msg = `Hello world`;'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertIn("Hello world", values)

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

    def test_regex_literal_with_quotes_is_skipped(self):
        """Regex literals containing quote characters should not be tokenized as strings."""
        code = 'var r = /"oops"/i; var y = "safe";'
        tokens = self.tok.extract_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "safe")

    def test_regex_literal_with_comment_markers_is_skipped(self):
        """Regex literals containing comment-like markers should not be tokenized as comments or strings."""
        code = r'var r = /\/\* not a comment *\//; var y = "safe";'
        tokens = self.tok.extract_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "safe")

    def test_regex_literal_after_return_is_skipped(self):
        """Regex literals after return should be skipped, not treated as division."""
        code = 'return /abc/.test(value); var y = "safe";'
        tokens = self.tok.extract_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "safe")

    def test_division_operator_is_not_regex(self):
        """Division operators should not trigger regex skipping."""
        code = 'const ratio = a / b; var y = "safe";'
        tokens = self.tok.extract_strings(code)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0][2], "safe")

    def test_regexp_constructor_strings_are_skipped(self):
        """Strings inside RegExp constructors should be treated as technical."""
        code = 'const r = new RegExp("abc", "i"); const s = RegExp("def"); var y = "safe";'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertNotIn("abc", values)
        self.assertNotIn("def", values)
        self.assertIn("safe", values)

    def test_regexp_constructor_translatable_string_is_skipped(self):
        """Even human-looking strings should be skipped inside RegExp constructors."""
        code = 'const r = RegExp("Open Menu"); var y = "safe text";'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertNotIn("Open Menu", values)
        self.assertIn("safe text", values)

    def test_path_join_strings_are_skipped(self):
        """Strings used in path joins should be treated as technical."""
        code = 'const p = path.join("img", "pictures", "Hero Face.png"); var y = "safe text";'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertNotIn("img", values)
        self.assertNotIn("pictures", values)
        self.assertNotIn("Hero Face.png", values)
        self.assertIn("safe text", values)

    def test_new_url_strings_are_skipped(self):
        """Strings used in URL construction should be treated as technical."""
        code = 'const u = new URL("https://example.com/game", base); var y = "safe text";'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertNotIn("https://example.com/game", values)
        self.assertIn("safe text", values)

    def test_eval_and_function_strings_are_skipped(self):
        """Strings inside eval-like code constructors should be treated as technical."""
        code = 'eval("showMenu()") ; Function("return 1") ; setTimeout("doWork()", 1000); var y = "safe text";'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertNotIn("showMenu()", values)
        self.assertNotIn("return 1", values)
        self.assertNotIn("doWork()", values)
        self.assertIn("safe text", values)

    def test_json_and_base64_wrappers_are_skipped(self):
        """JSON/base64 wrapper strings should be treated as technical."""
        code = 'const a = JSON.parse("{\\"x\\":1}"); const b = JSON.stringify("data"); const c = atob("SGVsbG8="); var y = "safe text";'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertNotIn('{"x":1}', values)
        self.assertNotIn("data", values)
        self.assertNotIn("SGVsbG8=", values)
        self.assertIn("safe text", values)

    def test_promise_and_object_assign_wrappers_are_skipped(self):
        """Promise and object merge helpers should be treated as technical."""
        code = 'Promise.resolve("ready"); Promise.reject("fail"); Object.assign(target, { label: "HUD" }); var y = "safe text";'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertNotIn("ready", values)
        self.assertNotIn("fail", values)
        self.assertNotIn("HUD", values)
        self.assertIn("safe text", values)

    def test_transform_helpers_are_skipped(self):
        """Common transform helpers should be treated as technical."""
        code = 'const a = parseInt("42", 10); const c = Number("12"); var y = "safe text";'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertNotIn("42", values)
        self.assertNotIn("12", values)
        self.assertIn("safe text", values)

    def test_text_replace_strings_can_still_be_extracted(self):
        """Human-readable replace strings should still be considered text."""
        code = 'const a = text.replace("Open Menu", "Close Menu"); var y = "safe text";'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertIn("Open Menu", values)
        self.assertIn("Close Menu", values)
        self.assertIn("safe text", values)

    def test_join_separator_is_skipped(self):
        """Join separators should be treated as technical."""
        code = 'const text = items.join(" / "); var y = "safe text";'
        tokens = self.tok.extract_translatable_strings(code)
        values = [token[2] for token in tokens]
        self.assertNotIn(" / ", values)
        self.assertIn("safe text", values)

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
