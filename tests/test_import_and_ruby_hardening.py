import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.core.export_import import TranslationImporter
from src.core.parsers.ruby_parser import RubyParser


class TestTranslationImporterHardening(unittest.TestCase):
    def test_import_json_skips_non_string_translations_without_crashing(self) -> None:
        importer = TranslationImporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "translations.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "entries": [
                            {
                                "file": "Map001.json",
                                "path": "events.1.pages.0.list.0.parameters.0",
                                "translated": {"bad": "value"},
                                "status": "translated",
                            },
                            {
                                "file": "Map001.json",
                                "path": "events.1.pages.0.list.1.parameters.0",
                                "translated": "Merhaba",
                                "status": "translated",
                            },
                        ]
                    },
                    handle,
                    ensure_ascii=False,
                )

            success = importer.import_json(file_path)

        self.assertTrue(success)
        self.assertEqual(
            importer.get_translations_for_file("Map001.json"),
            {"events.1.pages.0.list.1.parameters.0": "Merhaba"},
        )
        self.assertEqual(importer.get_stats()["skipped"], 1)


class TestRubyParserHardening(unittest.TestCase):
    def test_ruby_event_command_skips_known_asset_basename(self) -> None:
        parser = RubyParser()
        parser._known_asset_identifiers = {"cursor1"}
        parser.extracted = []

        parser._extract_event_command(401, ["Cursor1"], "0")

        self.assertEqual(parser.extracted, [])

    def test_ruby_script_string_rejects_known_asset_basename(self) -> None:
        parser = RubyParser()
        parser._known_asset_identifiers = {"cursor1"}

        self.assertFalse(parser._is_valid_script_string("Cursor1"))
        self.assertTrue(parser._is_valid_script_string("Open Menu"))

    def test_ruby_apply_rejects_asset_mutation(self) -> None:
        parser = RubyParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = os.path.join(tmpdir, "www", "audio", "se")
            data_dir = os.path.join(tmpdir, "www", "data")
            os.makedirs(asset_dir, exist_ok=True)
            os.makedirs(data_dir, exist_ok=True)

            with open(os.path.join(asset_dir, "Cursor1.ogg"), "wb") as handle:
                handle.write(b"")

            file_path = os.path.join(data_dir, "Map001.rvdata2")
            with open(file_path, "wb") as handle:
                handle.write(b"placeholder")

            original_payload = {"sound": "Cursor1", "label": "Open Menu"}
            mutable_payload = {"sound": "Cursor1", "label": "Open Menu"}

            with patch("src.core.parsers.ruby_parser.rubymarshal.reader.load", side_effect=[original_payload, mutable_payload]):
                updated = parser.apply_translation(file_path, {"sound": "İmleç1"})

        self.assertIsNone(updated)
        self.assertIn("Asset invariant violation", parser.last_apply_error or "")


if __name__ == "__main__":
    unittest.main()
