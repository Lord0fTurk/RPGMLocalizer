import unittest

from src.core.parsers.js_ast_extractor import JavaScriptAstAuditExtractor


class TestJavaScriptAstAuditExtractor(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = JavaScriptAstAuditExtractor()
        if self.extractor.engine_name != "tree_sitter":
            self.skipTest("tree-sitter audit extractor dependency is unavailable")

    def test_error_and_message_calls_are_extracted(self) -> None:
        source = (
            'Graphics.printLoadingError("Loading Error", "Failed to load: " + url);\n'
            '$gameMessage.add("Hello there");\n'
            'ImageManager.loadSystem("Window");\n'
        )

        candidates, engine = self.extractor.extract_audit_candidates_from_source(source)
        values = {item.text for item in candidates}
        summary = self.extractor.summarize_candidates(candidates, engine)

        self.assertEqual(engine, "tree_sitter")
        self.assertIn("Loading Error", values)
        self.assertIn("Failed to load: ", values)
        self.assertIn("Hello there", values)
        self.assertNotIn("Window", values)
        self.assertGreaterEqual(summary["confidence_buckets"].get("high", 0), 2)
        self.assertEqual(summary["write_readiness"], "promising")

    def test_add_command_extracts_caption_but_skips_symbol(self) -> None:
        source = 'Window_Command.prototype.addCommand("Start", "newGame");\n'

        candidates, engine = self.extractor.extract_audit_candidates_from_source(source)
        values = {item.text for item in candidates}
        summary = self.extractor.summarize_candidates(candidates, engine)

        self.assertIn("Start", values)
        self.assertNotIn("newGame", values)
        self.assertEqual(summary["confidence_buckets"].get("medium", 0), 1)
        self.assertEqual(summary["write_readiness"], "review")

    def test_assignment_and_object_keys_respect_technical_hints(self) -> None:
        source = (
            'var uiConfig = {title: "Game Over", description: "Try again?", file: "Window"};\n'
            'params["file"] = "IconSet";\n'
            'return "cannot move by the numb!";\n'
        )

        candidates, engine = self.extractor.extract_audit_candidates_from_source(source)
        values = {item.text for item in candidates}
        summary = self.extractor.summarize_candidates(candidates, engine)

        self.assertIn("Game Over", values)
        self.assertIn("Try again?", values)
        self.assertIn("cannot move by the numb!", values)
        self.assertNotIn("Window", values)
        self.assertNotIn("IconSet", values)
        self.assertGreaterEqual(summary["confidence_buckets"].get("medium", 0), 1)


if __name__ == "__main__":
    unittest.main()
