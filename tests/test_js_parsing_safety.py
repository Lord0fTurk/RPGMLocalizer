"""Guard the JS parsing path used by large RPG Maker projects."""
from __future__ import annotations

import tempfile
import threading
import time
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.parsers.js_ast_extractor import JavaScriptAstAuditExtractor
from src.core.parsers.json_parser import JsonParser
from src.core.translation_pipeline import TranslationPipeline


class JsParsingSafetyTests(unittest.TestCase):
    def test_safe_sink_extraction_uses_tree_cursor(self) -> None:
        extractor = JavaScriptAstAuditExtractor()
        entries, _engine = extractor.extract_safe_sink_entries_from_source('window.drawText("Hello world", 0, 0);')
        self.assertTrue(any(text == "Hello world" for _path, text, _tag in entries))

    @unittest.skipUnless(sys.platform == "win32", "Windows native helper")
    def test_native_helper_failure_skips_js_source_without_crashing(self) -> None:
        parser = JsonParser()
        with patch("src.core.parsers.json_parser.subprocess.run", side_effect=OSError("helper failed")):
            self.assertEqual([], parser._filter_js_strings_by_safe_sinks('window.drawText("Hello world", 0, 0);', isolate_native=True))

    @unittest.skipUnless(sys.platform == "win32", "Windows native helper")
    def test_raw_js_helper_keeps_safe_sink_text(self) -> None:
        parser = JsonParser()
        strings = parser._filter_js_strings_by_safe_sinks('window.drawText("Hello world", 0, 0);', isolate_native=True)
        self.assertEqual(["Hello world"], [item[2] for item in strings])

    def test_js_files_are_parsed_one_at_a_time(self) -> None:
        active = 0
        peak = 0
        guard = threading.Lock()

        class FakeParser:
            _listed_entries: list = []
            _last_loaded_data = None

            def extract_text(self, _path: str) -> list[tuple[str, str, str]]:
                nonlocal active, peak
                with guard:
                    active += 1
                    peak = max(peak, active)
                time.sleep(0.03)
                with guard:
                    active -= 1
                return [("key", "Hello world", "dialogue")]

        with tempfile.TemporaryDirectory() as directory:
            files = [str(Path(directory) / name) for name in ("a.js", "b.js", "c.js")]
            for path in files:
                Path(path).write_text("", encoding="utf-8")
            pipeline = TranslationPipeline({"engine": "pseudo", "use_cache": False, "backup_enabled": False})
            updates: list[tuple[int, int]] = []
            with patch("src.core.translation_pipeline.get_parser", return_value=FakeParser()):
                entries, parsed, _listed = pipeline._extract_all_text(
                    files, progress_callback=lambda current, total, _msg: updates.append((current, total))
                )
            self.assertEqual(1, peak)
            self.assertEqual(3, len(entries))
            self.assertEqual(3, len(parsed))
            self.assertEqual((3, 3), updates[-1])
