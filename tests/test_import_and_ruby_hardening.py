import json
import os
import tempfile
import unittest
from unittest.mock import patch
import zlib

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
    def test_ruby_apply_handles_leading_none_list(self) -> None:
        class FakeRubyParser(RubyParser):
            def _load_ruby_marshal(self, file_path: str) -> object:
                return [None, {"name": "Hero"}]

            def _find_asset_mutations(self, original, updated):
                return []

        parser = FakeRubyParser()
        parser.allow_script_translation = True

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Actors.rvdata2")
            with open(file_path, "wb") as handle:
                handle.write(b"placeholder")

            updated = parser.apply_translation(file_path, {})

        self.assertIsInstance(updated, list)
        self.assertEqual(updated[1]["name"], "Hero")

    def test_ruby_apply_scripts_uses_safe_loader(self) -> None:
        class FakeRubyString:
            def __init__(self, text: str) -> None:
                self.text = text
                self.ruby_class_name = "str"
                self.attributes = {}

            def __str__(self) -> str:
                return self.text

        class FakeRubyParser(RubyParser):
            def _load_ruby_marshal(self, file_path: str) -> object:
                code = 'print("Hello world")'
                compressed = zlib.compress(code.encode("utf-8"))
                return [[1, FakeRubyString("Main"), FakeRubyString(compressed.decode("latin1"))]]

            def _find_asset_mutations(self, original, updated):
                return []

        parser = FakeRubyParser()
        parser.allow_script_translation = True

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Scripts.rvdata2")
            with open(file_path, "wb") as handle:
                handle.write(b"placeholder")

            updated = parser.apply_translation(file_path, {"0.code.string_0": "Hello RPG"})

        self.assertIsInstance(updated, list)
        self.assertEqual(len(updated), 1)
        updated_blob = updated[0][2]
        if isinstance(updated_blob, str):
            updated_blob = updated_blob.encode("latin1")
        restored = zlib.decompress(updated_blob).decode("utf-8")
        self.assertIn("Hello RPG", restored)

    def test_scripts_rvdata2_rubystring_blob_is_extracted(self) -> None:
        class FakeRubyString:
            def __init__(self, text: str) -> None:
                self.text = text
                self.ruby_class_name = "str"
                self.attributes = {}

            def __str__(self) -> str:
                return self.text

        parser = RubyParser()
        parser.extracted = []

        code = 'print("Hello world")'
        compressed = zlib.compress(code.encode("utf-8"))
        entry = [1, FakeRubyString("Main"), FakeRubyString(compressed.decode("latin1"))]

        parser._walk([entry], "", 0)

        values = [text for _path, text, _ctx in parser.extracted]
        self.assertIn("Hello world", values)

    def test_scripts_rvdata2_translation_is_skipped_by_default(self) -> None:
        class FakeRubyParser(RubyParser):
            def _load_ruby_marshal(self, file_path: str) -> object:
                return [[1, "Main", b"compressed"]]

            def _find_asset_mutations(self, original, updated):
                return []

        parser = FakeRubyParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Scripts.rvdata2")
            with open(file_path, "wb") as handle:
                handle.write(b"placeholder")

            updated = parser.apply_translation(file_path, {"0.code.string_0": "Hello RPG"})

        self.assertIsNone(updated)
        self.assertIn("write disabled", parser.last_apply_error or "")

    def test_script_container_skip_is_structure_based_not_filename_based(self) -> None:
        class FakeRubyParser(RubyParser):
            def _load_ruby_marshal(self, file_path: str) -> object:
                return [[1, "Main", b"compressed"]]

            def _find_asset_mutations(self, original, updated):
                return []

        parser = FakeRubyParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "CustomBlob.rvdata2")
            with open(file_path, "wb") as handle:
                handle.write(b"placeholder")

            updated = parser.apply_translation(file_path, {"0.code.string_0": "Hello RPG"})

        self.assertIsNone(updated)
        self.assertIn("write disabled", parser.last_apply_error or "")

    def test_ruby_nested_objects_and_rubystring_extraction(self) -> None:
        class FakeRubyString:
            def __init__(self, text: str) -> None:
                self.text = text
                self.ruby_class_name = "str"
                self.attributes = {}

        class FakeRubyObject:
            def __init__(self, attributes: dict[str, object]) -> None:
                self.attributes = attributes

        parser = RubyParser()
        parser.extracted = []

        command = FakeRubyObject({"@code": 401, "@parameters": [FakeRubyString("Hello world")], "@indent": 0})
        page = FakeRubyObject({"@list": [command]})
        event = FakeRubyObject({"@pages": [page], "@name": FakeRubyString("Morning Scene")})

        parser._walk(event, "@events.1", 0)

        values = [text for _path, text, _ctx in parser.extracted]
        self.assertIn("Hello world", values)
        self.assertIn("Morning Scene", values)

    def test_ruby_surface_aware_attributes_skip_technical_keys(self) -> None:
        class FakeRubyObject:
            def __init__(self, attributes: dict[str, object]) -> None:
                self.attributes = attributes

        parser = RubyParser()
        parser.extracted = []

        obj = FakeRubyObject({"@filename": "Cursor1", "@title": "Main Menu"})
        parser._walk(obj, "@root", 0)

        values = [text for _path, text, _ctx in parser.extracted]
        self.assertIn("Main Menu", values)
        self.assertNotIn("Cursor1", values)

    def test_ruby_list_walk_extracts_shift_jis_bytes(self) -> None:
        parser = RubyParser()
        parser.extracted = []

        item = {"@name": "メニュー".encode("shift_jis")}
        parser._walk([item], "", 0)

        values = [text for _path, text, _ctx in parser.extracted]
        self.assertIn("メニュー", values)

    def test_ruby_script_translation_preserves_detected_encoding(self) -> None:
        parser = RubyParser()
        original_code = 'print("メニュー")'
        compressed_code = zlib.compress(original_code.encode("shift_jis"))

        scripts = [[1, "Main", compressed_code]]
        translated = parser._apply_scripts_translation(scripts, {"0.code.string_0": "メニュー2"})

        self.assertEqual(len(translated), 1)
        updated_code = zlib.decompress(translated[0][2]).decode("shift_jis")
        self.assertIn("メニュー2", updated_code)

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

    def test_ruby_script_string_rejects_percent_encoded_asset_path(self) -> None:
        parser = RubyParser()

        encoded_path = "img/system/sava%C5%9FAttackInfoArrow2.png?ver=12#sprite"

        self.assertTrue(parser._contains_asset_reference(encoded_path))
        self.assertFalse(parser._is_extractable_runtime_text(encoded_path))

    def test_ruby_script_string_rejects_double_encoded_asset_path(self) -> None:
        parser = RubyParser()

        double_encoded_path = "img\\system\\sava%25C5%259FAttackInfoArrow2.png"

        self.assertTrue(parser._contains_asset_reference(double_encoded_path))
        self.assertFalse(parser._is_extractable_runtime_text(double_encoded_path))

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
