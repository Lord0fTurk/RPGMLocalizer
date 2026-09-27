"""Checks for structural review and durable Hy-MT2 progress."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.core.cache import reset_cache
from src.core.translation_pipeline import TranslationPipeline
from src.core.translation_quality import translation_issues
from src.core.translators.services import HyMT2Translator


class FakeHyMT2(HyMT2Translator):
    def __init__(self, *, break_after: int = -1, corrupt_first: bool = False, always_corrupt: bool = False) -> None:
        super().__init__(model="test-model", base_url="http://127.0.0.1:1234/v1", batch_size=1)
        self.calls = 0
        self.break_after = break_after
        self.corrupt_first = corrupt_first
        self.always_corrupt = always_corrupt

    async def verify_connection(self) -> None:
        return

    async def _translate_clean_texts(self, clean_texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        self.calls += 1
        if self.calls == self.break_after:
            raise RuntimeError("simulated server interruption")
        if self.always_corrupt or (self.corrupt_first and self.calls == 1):
            return ["Çeviri \\V[999]" for _ in clean_texts]
        return ["Çeviri " + text for text in clean_texts]


class QualityAndResumeTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_cache()

    def test_quality_detects_codes_placeholders_and_line_breaks(self) -> None:
        self.assertFalse(translation_issues("Hello \\V[1] {name}\nNext", "Merhaba \\V[1] {name}\nSonraki"))
        issues = translation_issues("Hello \\V[1] {name}\nNext", "Merhaba \\V[2] {other} Sonraki")
        self.assertEqual(len(issues), 3)

    def test_resumes_from_saved_window_after_interruption(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = {
                "engine": "hy_mt2", "hy_mt2_model": "test-model",
                "project_path": temp_dir, "cache_dir": str(Path(temp_dir) / "cache"),
                "target_lang": "tr", "source_lang": "en", "batch_size": 1,
            }
            entries = [(str(Path(temp_dir) / "Map001.json"), f"key{i}", f"Line {i}", "dialogue") for i in range(3)]
            first = TranslationPipeline(settings)
            first.translator = FakeHyMT2(break_after=2)
            with self.assertRaisesRegex(RuntimeError, "simulated server interruption"):
                first._translate_entries(entries, "en", "tr")
            reset_cache()

            resumed = TranslationPipeline(settings)
            translator = FakeHyMT2()
            resumed.translator = translator
            results = resumed._translate_entries(entries, "en", "tr")
            self.assertEqual(translator.calls, 2)
            self.assertEqual(len(results), 3)
            report = Path(settings["cache_dir"]) / "quality_review.json"
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["issues"], [])

    def test_corrupt_code_is_retried_before_caching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = {
                "engine": "hy_mt2", "hy_mt2_model": "test-model",
                "project_path": temp_dir, "cache_dir": str(Path(temp_dir) / "cache"),
                "target_lang": "tr", "source_lang": "en", "batch_size": 1,
            }
            pipeline = TranslationPipeline(settings)
            translator = FakeHyMT2(corrupt_first=True)
            pipeline.translator = translator
            entry = (str(Path(temp_dir) / "Map001.json"), "dialogue", "Hello \\V[1]", "dialogue")
            results = pipeline._translate_entries([entry], "en", "tr")
            self.assertEqual(translator.calls, 2)
            self.assertEqual(results[(entry[0], entry[1])].count("\\V[1]"), 1)
            self.assertNotIn("\\V[999]", results[(entry[0], entry[1])])

    def test_persistent_bad_result_is_listed_and_not_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = {
                "engine": "hy_mt2", "hy_mt2_model": "test-model",
                "project_path": temp_dir, "cache_dir": str(Path(temp_dir) / "cache"),
                "target_lang": "tr", "source_lang": "en", "batch_size": 1,
            }
            pipeline = TranslationPipeline(settings)
            pipeline.translator = FakeHyMT2(always_corrupt=True)
            entry = (str(Path(temp_dir) / "Map001.json"), "dialogue", "Hello \\V[1]", "dialogue")
            results = pipeline._translate_entries([entry], "en", "tr")
            self.assertEqual(results, {})
            report = json.loads((Path(settings["cache_dir"]) / "quality_review.json").read_text(encoding="utf-8"))
            self.assertEqual(report["issues"][0]["key"], "dialogue")
            self.assertIn("game codes", report["issues"][0]["reason"])
