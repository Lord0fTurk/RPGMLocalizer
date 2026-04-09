import json
import os
import tempfile
import unittest

from src.core.parser_factory import get_parser
from src.core.parsers.hendrix_csv_parser import HendrixLocalizationCsvParser
from src.core.translation_pipeline import TranslationPipeline


HENDRIX_SAMPLE = (
    "\ufeffChange,Excluded,Name,Original,jp,en\n"
    ',,,"[Collection Menu]",,\n'
    ',,Reina,Original Thai line,Japanese line,English line\n'
    ',,,"Mission\\n[Go to the tower]",,\n'
)


class TestHendrixCsvParser(unittest.TestCase):
    def test_factory_returns_hendrix_parser_for_game_messages_csv(self) -> None:
        parser = get_parser(
            "game_messages.csv",
            {"source_lang": "en", "target_lang": "tr", "regex_blacklist": []},
        )
        self.assertIsInstance(parser, HendrixLocalizationCsvParser)

    def test_extracts_original_column_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "game_messages.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(HENDRIX_SAMPLE)

            parser = HendrixLocalizationCsvParser(target_lang="tr")
            extracted = parser.extract_text(csv_path)

        values = {text for _path, text, _tag in extracted}
        self.assertIn("[Collection Menu]", values)
        self.assertIn("Original Thai line", values)
        self.assertIn("Mission\\n[Go to the tower]", values)
        self.assertNotIn("English line", values)

    def test_apply_adds_target_language_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "game_messages.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(HENDRIX_SAMPLE)

            parser = HendrixLocalizationCsvParser(target_lang="tr")
            updated = parser.apply_translation(
                csv_path,
                {
                    "rows.1.Original": "Koleksiyon Menusu",
                    "rows.2.Original": "Turkce satir",
                },
            )

        self.assertIsInstance(updated, str)
        assert isinstance(updated, str)
        self.assertIn(",tr\n", updated)
        self.assertIn("Koleksiyon Menusu", updated)
        self.assertIn("Turkce satir", updated)

    def test_pipeline_collects_hendrix_csv_when_plugin_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            js_dir = os.path.join(tmpdir, "js")
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(js_dir, exist_ok=True)

            with open(os.path.join(data_dir, "System.json"), "w", encoding="utf-8") as handle:
                json.dump({"gameTitle": "Test"}, handle)

            with open(os.path.join(js_dir, "plugins.js"), "w", encoding="utf-8") as handle:
                handle.write(
                    'var $plugins = ['
                    '{"name":"Hendrix_Localization","status":true,"parameters":{"Languages":"[]","Default Language":"en"}}'
                    '];\n'
                )

            with open(os.path.join(tmpdir, "game_messages.csv"), "w", encoding="utf-8", newline="") as handle:
                handle.write(HENDRIX_SAMPLE)

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False, "target_lang": "tr"})
            files = pipeline._collect_files(data_dir)

        basenames = {os.path.basename(path).lower() for path in files}
        self.assertIn("game_messages.csv", basenames)

    def test_pipeline_updates_hendrix_plugin_language_config_after_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "data")
            js_dir = os.path.join(tmpdir, "js")
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(js_dir, exist_ok=True)

            csv_path = os.path.join(tmpdir, "game_messages.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(HENDRIX_SAMPLE)

            plugins_path = os.path.join(js_dir, "plugins.js")
            plugin_payload = [
                {
                    "name": "Hendrix_Localization",
                    "status": True,
                    "parameters": {
                        "Languages": json.dumps([
                            json.dumps({"Name": "English", "Symbol": "en", "Font": "", "FontSize": "28"})
                        ]),
                        "Default Language": "en",
                    },
                }
            ]
            with open(plugins_path, "w", encoding="utf-8") as handle:
                handle.write(f"var $plugins = {json.dumps(plugin_payload, ensure_ascii=False)};\n")

            parser = HendrixLocalizationCsvParser(target_lang="tr")
            extracted = parser.extract_text(csv_path)
            parsed_files = {csv_path: (parser, extracted)}
            results_map = {(csv_path, "rows.2.Original"): "Turkce satir"}

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False, "target_lang": "tr"})
            pipeline._save_translations(parsed_files, results_map)

            with open(plugins_path, "r", encoding="utf-8") as handle:
                plugins_text = handle.read()

        start = plugins_text.find("[")
        end = plugins_text.rfind("]")
        plugins = json.loads(plugins_text[start : end + 1])
        params = plugins[0]["parameters"]
        languages = [json.loads(item) for item in json.loads(params["Languages"])]

        self.assertEqual(params["Default Language"], "tr")
        self.assertIn("tr", {entry["Symbol"] for entry in languages})


if __name__ == "__main__":
    unittest.main()
