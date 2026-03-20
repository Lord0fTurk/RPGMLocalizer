import json
import os
import tempfile
import unittest

from src.core.parser_factory import get_parser
from src.core.parsers.json_parser import JsonParser
from src.core.parsers.ruby_parser import RubyParser
from src.core.translation_pipeline import TranslationPipeline


class NullJsonParser:
    def apply_translation(self, file_path: str, translations: dict[str, str]) -> None:
        return None


class TestParserHardening(unittest.TestCase):
    def test_control_code_only_show_text_is_skipped(self) -> None:
        parser = JsonParser()
        data = [
            {
                "code": 401,
                "parameters": [r"\msgposx[955]\msgwidth[380]\msgposy[1000]\ow[0]\fs[25]\hc[000000]"],
                "indent": 0,
            }
        ]

        parser.extracted = []
        parser._process_list(data, "events.1.list")

        self.assertEqual(parser.extracted, [])

    def test_control_code_only_choice_is_skipped(self) -> None:
        parser = JsonParser()
        data = [
            {
                "code": 102,
                "parameters": [[r"\V[1182]", "Real choice"], 0, 0, 0, 0],
                "indent": 0,
            }
        ]

        parser.extracted = []
        parser._process_list(data, "events.1.list")

        values = [text for _path, text, _ctx in parser.extracted]
        self.assertNotIn(r"\V[1182]", values)
        self.assertIn("Real choice", values)

    def test_comment_like_command_is_skipped_when_enabled(self) -> None:
        parser = JsonParser(translate_comments=True)
        data = [{"code": 108, "parameters": ["layer load"], "indent": 0}]

        parser.extracted = []
        parser._process_list(data, "events.1.list")

        self.assertEqual(parser.extracted, [])

    def test_natural_language_comment_is_extracted_when_enabled(self) -> None:
        parser = JsonParser(translate_comments=True)
        data = [{"code": 108, "parameters": ["This room starts the intro scene."], "indent": 0}]

        parser.extracted = []
        parser._process_list(data, "events.1.list")

        self.assertEqual(len(parser.extracted), 1)
        self.assertEqual(parser.extracted[0][1], "This room starts the intro scene.")

    def test_ruby_comment_like_command_is_skipped_when_enabled(self) -> None:
        parser = RubyParser(translate_comments=True)
        parser.extracted = []

        parser._extract_event_command(108, ["Layer load"], "0")

        self.assertEqual(parser.extracted, [])

    def test_parser_factory_disables_comment_translation_by_default(self) -> None:
        json_parser = get_parser("Map001.json", {})
        ruby_parser = get_parser("Actors.rvdata2", {})

        self.assertIsInstance(json_parser, JsonParser)
        self.assertIsInstance(ruby_parser, RubyParser)
        self.assertFalse(json_parser.translate_comments)
        self.assertFalse(ruby_parser.translate_comments)

    def test_locale_non_ascii_single_character_is_extracted(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            locales_dir = os.path.join(tmpdir, "locales")
            os.makedirs(locales_dir, exist_ok=True)
            file_path = os.path.join(locales_dir, "strings.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump({"element_fire": "火"}, handle, ensure_ascii=False)

            extracted = parser.extract_text(file_path)

        values = [text for _path, text, _ctx in extracted]
        self.assertIn("火", values)

    def test_system_locale_identifier_is_not_extracted(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "System.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump({"gameTitle": "Test Game", "locale": "en_US"}, handle, ensure_ascii=False)

            extracted = parser.extract_text(file_path)

        paths = [path for path, _text, _ctx in extracted]
        self.assertIn("gameTitle", paths)
        self.assertNotIn("locale", paths)

    def test_non_json_sidecar_json_file_is_skipped_without_error(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Map036lighting.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write("Lighting config placeholder")

            extracted = parser.extract_text(file_path)

        self.assertEqual(extracted, [])

    def test_translations_json_nested_locale_entries_are_extracted(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Translations.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "menu": {"start": "Start Game"},
                        "metadata": {"file": "audio/bgm/Theme1.ogg"},
                    },
                    handle,
                    ensure_ascii=False,
                )

            extracted = parser.extract_text(file_path)

        values_by_path = {path: text for path, text, _ctx in extracted}
        self.assertEqual(values_by_path.get("menu.start"), "Start Game")
        self.assertNotIn("metadata.file", values_by_path)

    def test_translations_json_nested_locale_apply_updates_path(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Translations.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump({"menu": {"start": "Start Game"}}, handle, ensure_ascii=False)

            translated = parser.apply_translation(file_path, {"menu.start": "Oyunu Baslat"})

        self.assertIsInstance(translated, dict)
        self.assertEqual(translated["menu"]["start"], "Oyunu Baslat")

    def test_generic_text_field_with_dict_value_does_not_raise_or_extract_dict(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "CustomData.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump({"text": {"line": "Hello"}}, handle, ensure_ascii=False)

            extracted = parser.extract_text(file_path)

        self.assertEqual(extracted, [])

    def test_locale_asset_basename_is_skipped_when_real_asset_exists(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = os.path.join(tmpdir, "www", "audio", "se")
            locales_dir = os.path.join(tmpdir, "www", "locales")
            os.makedirs(asset_dir, exist_ok=True)
            os.makedirs(locales_dir, exist_ok=True)

            with open(os.path.join(asset_dir, "Cursor1.ogg"), "wb") as handle:
                handle.write(b"")

            file_path = os.path.join(locales_dir, "Translations.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump({"ui": {"cursor_sound": "Cursor1", "ok_text": "Start"}}, handle, ensure_ascii=False)

            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertNotIn("Cursor1", values)
        self.assertIn("Start", values)

    def test_plugin_sound_parameter_asset_basename_is_skipped_when_real_asset_exists(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = os.path.join(tmpdir, "www", "audio", "se")
            js_dir = os.path.join(tmpdir, "www", "js")
            os.makedirs(asset_dir, exist_ok=True)
            os.makedirs(js_dir, exist_ok=True)

            with open(os.path.join(asset_dir, "Cursor1.ogg"), "wb") as handle:
                handle.write(b"")

            file_path = os.path.join(js_dir, "plugins.js")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(
                    'var $plugins = [{"name":"CustomUi","status":true,"description":"",'
                    '"parameters":{"Cursor SE":"Cursor1","Button Text":"Open Menu"}}];\n'
                )

            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertNotIn("Cursor1", values)
        self.assertIn("Open Menu", values)

    def test_generic_custom_json_name_skips_real_asset_basename(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = os.path.join(tmpdir, "www", "audio", "se")
            data_dir = os.path.join(tmpdir, "www", "data")
            os.makedirs(asset_dir, exist_ok=True)
            os.makedirs(data_dir, exist_ok=True)

            with open(os.path.join(asset_dir, "Cursor1.ogg"), "wb") as handle:
                handle.write(b"")

            file_path = os.path.join(data_dir, "CustomSoundConfig.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump({"name": "Cursor1", "label": "Menu Cursor Sound"}, handle, ensure_ascii=False)

            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertNotIn("Cursor1", values)
        self.assertIn("Menu Cursor Sound", values)

    def test_mz_plugin_command_text_skips_real_asset_basename(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = os.path.join(tmpdir, "www", "audio", "se")
            data_dir = os.path.join(tmpdir, "www", "data")
            os.makedirs(asset_dir, exist_ok=True)
            os.makedirs(data_dir, exist_ok=True)

            with open(os.path.join(asset_dir, "Cursor1.ogg"), "wb") as handle:
                handle.write(b"")

            payload = {
                "events": [
                    None,
                    {
                        "id": 1,
                        "pages": [
                            {
                                "list": [
                                    {"code": 357, "parameters": ["CustomUi", "SetCursor", "Cursor1", {}], "indent": 0},
                                    {"code": 657, "parameters": ["Cursor1"], "indent": 0},
                                ]
                            }
                        ],
                    },
                ]
            }
            file_path = os.path.join(data_dir, "Map001.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertNotIn("Cursor1", values)

    def test_script_string_skips_real_non_ascii_asset_basename(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = os.path.join(tmpdir, "www", "audio", "se")
            data_dir = os.path.join(tmpdir, "www", "data")
            os.makedirs(asset_dir, exist_ok=True)
            os.makedirs(data_dir, exist_ok=True)

            with open(os.path.join(asset_dir, "カーソル1.ogg"), "wb") as handle:
                handle.write(b"")

            payload = {
                "events": [
                    None,
                    {
                        "id": 1,
                        "pages": [
                            {
                                "list": [
                                    {"code": 355, "parameters": ['$gameSystem.playSe("カーソル1");'], "indent": 0},
                                ]
                            }
                        ],
                    },
                ]
            }
            file_path = os.path.join(data_dir, "Map001.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertNotIn("カーソル1", values)

    def test_apply_translation_rejects_asset_id_mutation_in_generic_json(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = os.path.join(tmpdir, "www", "audio", "se")
            data_dir = os.path.join(tmpdir, "www", "data")
            os.makedirs(asset_dir, exist_ok=True)
            os.makedirs(data_dir, exist_ok=True)

            with open(os.path.join(asset_dir, "Cursor1.ogg"), "wb") as handle:
                handle.write(b"")

            file_path = os.path.join(data_dir, "CustomSoundConfig.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump({"sound": "audio/se/Cursor1.ogg", "label": "Open Menu"}, handle, ensure_ascii=False)

            updated = parser.apply_translation(file_path, {"sound": "audio/se/İmleç1.ogg"})

        self.assertIsNone(updated)
        self.assertIn("Asset invariant violation", parser.last_apply_error or "")

    def test_apply_translation_rejects_asset_id_mutation_in_plugins_js(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = os.path.join(tmpdir, "www", "audio", "se")
            js_dir = os.path.join(tmpdir, "www", "js")
            os.makedirs(asset_dir, exist_ok=True)
            os.makedirs(js_dir, exist_ok=True)

            with open(os.path.join(asset_dir, "Cursor1.ogg"), "wb") as handle:
                handle.write(b"")

            file_path = os.path.join(js_dir, "plugins.js")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(
                    'var $plugins = [{"name":"CustomUi","status":true,"description":"",'
                    '"parameters":{"Cursor SE":"audio/se/Cursor1.ogg","Button Text":"Open Menu"}}];\n'
                )

            updated = parser.apply_translation(file_path, {"0.parameters.Cursor SE": "audio/se/İmleç1.ogg"})

        self.assertIsNone(updated)
        self.assertIn("Asset invariant violation", parser.last_apply_error or "")

    def test_note_tag_asset_basename_is_skipped_when_real_asset_exists(self) -> None:
        parser = JsonParser(translate_notes=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir = os.path.join(tmpdir, "www", "audio", "se")
            data_dir = os.path.join(tmpdir, "www", "data")
            os.makedirs(asset_dir, exist_ok=True)
            os.makedirs(data_dir, exist_ok=True)

            with open(os.path.join(asset_dir, "Cursor1.ogg"), "wb") as handle:
                handle.write(b"")

            file_path = os.path.join(data_dir, "Items.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(
                    [None, {"id": 1, "name": "Potion", "note": "<Desc: Cursor1><Description>Open Menu</Description>"}],
                    handle,
                    ensure_ascii=False,
                )

            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertNotIn("Cursor1", values)
        self.assertIn("Open Menu", values)

    def test_plugin_groupname_parameter_is_skipped(self) -> None:
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "plugins.js")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(
                    'var $plugins = [{"name":"OrangeHudLine0","status":true,'
                    '"description":"",'
                    '"parameters":{"GroupName":"main","Pattern":"Day %1"}}];\n'
                )

            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertIn("Day %1", values)
        self.assertNotIn("main", values)

    def test_save_does_not_overwrite_file_when_parser_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Map001.json")
            original_data = {"name": "Hello"}
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(original_data, handle, ensure_ascii=False)

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            parsed_files = {
                file_path: (NullJsonParser(), [("name", "Hello", "name")]),
            }
            results_map = {(file_path, "name"): "Merhaba"}

            pipeline._save_translations(parsed_files, results_map)

            with open(file_path, "r", encoding="utf-8") as handle:
                saved_data = json.load(handle)

        self.assertEqual(saved_data, original_data)


if __name__ == "__main__":
    unittest.main()
