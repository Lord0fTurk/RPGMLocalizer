import json
import os
import tempfile
import unittest

from src.core.parser_factory import get_parser
from src.core.parsers.ts_adv_scenario_parser import TsAdvScenarioParser
from src.core.translation_pipeline import TranslationPipeline


def encode_ts(text: str, key: int = 255) -> str:
    return "".join(chr(ord(char) ^ key) for char in text)


TS_SAMPLE_DECODED = (
    "@move_speed spd=3\n"
    "*label_start\n"
    "[Shinji] (Sumiyo... You look beautiful today...)\n"
    "Narration line without prefix\n"
    "; Comment line\n"
    "@jump storage=002\n"
)


class TestTsAdvScenarioParser(unittest.TestCase):
    def test_factory_returns_ts_adv_parser_for_sl_files(self) -> None:
        parser = get_parser("001.sl", {"ts_decode_key": 255, "regex_blacklist": []})
        self.assertIsInstance(parser, TsAdvScenarioParser)

    def test_extracts_dialogue_like_lines_from_decoded_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            scenario_path = os.path.join(tmpdir, "001.sl")
            with open(scenario_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(encode_ts(TS_SAMPLE_DECODED))

            parser = TsAdvScenarioParser(decode_key=255)
            extracted = parser.extract_text(scenario_path)

        values = {text for _path, text, _tag in extracted}
        self.assertIn("[Shinji] (Sumiyo... You look beautiful today...)", values)
        self.assertIn("Narration line without prefix", values)
        self.assertNotIn("@move_speed spd=3", values)
        self.assertNotIn("*label_start", values)

    def test_skips_plain_technical_lines_without_dialogue_markers(self) -> None:
        decoded = (
            "plain_token_without_punctuation\n"
            "[Hero] Hello there!\n"
            "Another narration line.\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            scenario_path = os.path.join(tmpdir, "001.sl")
            with open(scenario_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(encode_ts(decoded))

            parser = TsAdvScenarioParser(decode_key=255)
            extracted = parser.extract_text(scenario_path)

        values = {text for _path, text, _tag in extracted}
        self.assertIn("[Hero] Hello there!", values)
        self.assertIn("Another narration line.", values)
        self.assertNotIn("plain_token_without_punctuation", values)

    def test_apply_translation_preserves_xor_encoded_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            scenario_path = os.path.join(tmpdir, "001.sl")
            with open(scenario_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(encode_ts(TS_SAMPLE_DECODED))

            parser = TsAdvScenarioParser(decode_key=255)
            updated = parser.apply_translation(
                scenario_path,
                {
                    "lines.2": "[Shinji] Turkce satir",
                    "lines.3": "Anlati satiri",
                },
            )

        self.assertIsInstance(updated, str)
        assert isinstance(updated, str)
        decoded = encode_ts(updated)
        self.assertIn("[Shinji] Turkce satir", decoded)
        self.assertIn("Anlati satiri", decoded)
        self.assertIn("@move_speed spd=3", decoded)

    def test_pipeline_collects_ts_scenarios_when_ts_decode_plugin_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "www", "data")
            js_dir = os.path.join(tmpdir, "www", "js")
            scenario_dir = os.path.join(tmpdir, "scenario")
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(js_dir, exist_ok=True)
            os.makedirs(scenario_dir, exist_ok=True)

            with open(os.path.join(data_dir, "System.json"), "w", encoding="utf-8") as handle:
                json.dump({"gameTitle": "Test"}, handle)

            with open(os.path.join(js_dir, "plugins.js"), "w", encoding="utf-8") as handle:
                handle.write(
                    'var $plugins = ['
                    '{"name":"TS_Decode","status":true,"parameters":{"Key":"255"}}'
                    '];\n'
                )

            with open(os.path.join(scenario_dir, "001.sl"), "w", encoding="utf-8", newline="") as handle:
                handle.write(encode_ts(TS_SAMPLE_DECODED))

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            files = pipeline._collect_files(data_dir)

        basenames = {os.path.basename(path).lower() for path in files}
        self.assertIn("001.sl", basenames)


if __name__ == "__main__":
    unittest.main()
