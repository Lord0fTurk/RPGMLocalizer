import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.cache import get_cache, reset_cache
from src.core.parsers.json_parser import JsonParser
from src.core.translation_pipeline import TranslationPipeline
from src.ui.interfaces.home_interface import HomeInterface
from src.utils.backup import get_backup_manager, reset_backup_manager


class SingletonResetTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        reset_cache()
        reset_backup_manager()


class TestPluginsJsRoundTrip(SingletonResetTestCase):
    def test_plugins_js_font_parameters_are_preserved(self) -> None:
        parser = JsonParser()
        plugins_js = (
            'var $plugins = '
            '[{"name":"YEP_LoadCustomFonts","status":true,'
            '"parameters":{"Font Families":"GameFont","Font Filenames":"mplus-1m-regular.ttf"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "plugins.js")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(plugins_js)

            result = parser.apply_translation(file_path, {})

        self.assertIsInstance(result, str)
        self.assertIn('"Font Families":"GameFont"', result)
        self.assertNotIn("Arial, sans-serif", result)

    def test_plugins_js_apply_skips_asset_like_parameter_mutations(self) -> None:
        parser = JsonParser()
        plugins_js = (
            'var $plugins = '
            '[{"name":"OverlayLikePlugin","status":true,"parameters":{'
            '"Ground Layer Filename":"ground38",'
            '"Video File":"IntroMovie",'
            '"Display Text":"Welcome"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "plugins.js")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(plugins_js)

            result = parser.apply_translation(
                file_path,
                {
                    "0.parameters.Ground Layer Filename": "zemin38",
                    "0.parameters.Video File": "giris_film",
                    "0.parameters.Display Text": "Hos geldin",
                },
            )

        self.assertIsInstance(result, str)
        assert isinstance(result, str)
        self.assertIn('"Ground Layer Filename":"ground38"', result)
        self.assertIn('"Video File":"IntroMovie"', result)
        self.assertIn('"Display Text":"Hos geldin"', result)

    def test_plugins_js_apply_skips_symbol_identifier_mutation(self) -> None:
        parser = JsonParser()
        plugins_js = (
            'var $plugins = '
            '[{"name":"MenuSymbolPlugin","status":true,"parameters":{'
            '"Menu 90 Name":"Options",'
            '"Menu 90 Symbol":"options"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "plugins.js")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(plugins_js)

            result = parser.apply_translation(
                file_path,
                {
                    "0.parameters.Menu 90 Name": "Secenekler",
                    "0.parameters.Menu 90 Symbol": "secenekler",
                },
            )

        self.assertIsInstance(result, str)
        assert isinstance(result, str)
        self.assertIn('"Menu 90 Name":"Secenekler"', result)
        self.assertIn('"Menu 90 Symbol":"options"', result)

    def test_plugins_js_apply_repairs_backslash_space_escape_sequences(self) -> None:
        parser = JsonParser()
        plugins_js = (
            'var $plugins = '
            '[{"name":"QuestLikePlugin","status":true,"parameters":{'
            '"Quest Data Format":"<WordWrap>\\\\n<br>\\\\c[4]Aciklama:\\\\c[0]\\\\n<br>%1"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "plugins.js")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(plugins_js)

            result = parser.apply_translation(
                file_path,
                {
                    "0.parameters.Quest Data Format": "<WordWrap>\\ n<br>\\ c[4]Aciklama:\\ c[0]\\ n<br>%1",
                },
            )

        self.assertIsInstance(result, str)
        assert isinstance(result, str)
        self.assertIn('"Quest Data Format":"<WordWrap>\\\\n<br>\\\\c[4]Aciklama:\\\\c[0]\\\\n<br>%1"', result)


    def test_plugins_js_apply_skips_type_order_registry_mutation(self) -> None:
        parser = JsonParser()
        plugins_js = (
            'var $plugins = '
            '[{"name":"QuestOrderPlugin","status":true,"parameters":{'
            '"Quest List Window":"{\\"Type Order\\":\\"[\\\\\\"\\\\\\\\c[6]Main Quests\\\\\\",\\\\\\"\\\\\\\\c[4]Side Quests\\\\\\"]\\"}"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "plugins.js")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(plugins_js)

            result = parser.apply_translation(
                file_path,
                {
                    "0.parameters.Quest List Window.@JSON.Type Order.@JSON.0": "\\c[6]Ana Gorevler",
                    "0.parameters.Quest List Window.@JSON.Type Order.@JSON.1": "\\c[4]Yan Gorevler",
                },
            )

        self.assertIsInstance(result, str)
        assert isinstance(result, str)
        self.assertIn("Main Quests", result)
        self.assertIn("Side Quests", result)

    def test_plugins_js_apply_skips_console_code_mutation(self) -> None:
        parser = JsonParser()
        original_code = '"// Variables:\n//   questId - ID of the quest whose subtext is changed\n// console.log(\'Quest \' + questId)"'
        translated_code = '"// Degiskenler:\n// questId - Gorev kimligi\n// console.log(\'Gorev \' + questId)"'
        plugin_payload = [
            {
                "name": "LunaticCodePlugin",
                "status": True,
                "parameters": {
                    "Lunatic Mode": json.dumps({"Change Subtext": original_code}, ensure_ascii=False),
                },
            }
        ]
        plugins_js = f"var $plugins = {json.dumps(plugin_payload, ensure_ascii=False)};\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "plugins.js")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(plugins_js)

            result = parser.apply_translation(
                file_path,
                {
                    "0.parameters.Lunatic Mode.@JSON.Change Subtext": translated_code,
                },
            )

        self.assertIsInstance(result, str)
        assert isinstance(result, str)
        self.assertIn("console.log", result)
        self.assertIn("questId", result)

    def test_plugins_js_apply_skips_input_binding_mutation(self) -> None:
        parser = JsonParser()
        plugins_js = (
            'var $plugins = '
            '[{"name":"ChronoLikePlugin","status":true,"parameters":{'
            '"Attack Button":"ok",'
            '"Dash Button":"shift",'
            '"Attack Text":"Attack"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "plugins.js")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(plugins_js)

            result = parser.apply_translation(
                file_path,
                {
                    "0.parameters.Attack Button": "tamam",
                    "0.parameters.Dash Button": "vardiya",
                    "0.parameters.Attack Text": "Saldiri",
                },
            )

        self.assertIsInstance(result, str)
        assert isinstance(result, str)
        self.assertIn('"Attack Button":"ok"', result)
        self.assertIn('"Dash Button":"shift"', result)
        self.assertIn('"Attack Text":"Saldiri"', result)

    def test_plugins_js_apply_rejects_unexpected_structural_mutation(self) -> None:
        parser = JsonParser()
        plugins_js = (
            'var $plugins = '
            '[{"name":"MenuGuardPlugin","status":true,"parameters":{'
            '"Menu Label":"Options","Safe Text":"Welcome"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "plugins.js")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(plugins_js)

            original_setter = parser._set_value_at_path

            def bad_setter(data: object, path: str, value: object) -> None:
                original_setter(data, path, value)
                if isinstance(data, list) and path == "0.parameters.Menu Label":
                    data[0]["status"] = False

            parser._set_value_at_path = bad_setter  # type: ignore[assignment]
            result = parser.apply_translation(
                file_path,
                {"0.parameters.Menu Label": "Ana Menu", "0.parameters.Safe Text": "Hos geldin"},
            )

        self.assertIsNone(result)
        self.assertIn("Structured invariant violation", parser.last_apply_error or "")


class TestSingleCharacterExtraction(SingletonResetTestCase):
    def test_non_ascii_single_character_survives_pipeline_filter(self) -> None:
        actor_name = "\u706b"

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Actors.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump([None, {"id": 1, "name": actor_name}], handle, ensure_ascii=False)

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            entries, _ = pipeline._extract_all_text([file_path])

        extracted_texts = [text for _file_path, _path, text, _tag in entries]
        self.assertIn(actor_name, extracted_texts)


class TestSingletonDirectorySwitching(SingletonResetTestCase):
    def test_default_cache_uses_app_path_manager_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.core.cache.get_cache_dir", return_value=Path(tmpdir)):
                reset_cache()
                cache = get_cache()

            self.assertEqual(
                os.path.normcase(os.path.abspath(cache.cache_dir)),
                os.path.normcase(os.path.abspath(tmpdir)),
            )
            reset_cache()

    def test_cache_reinitializes_when_directory_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            first_dir = os.path.join(tmpdir, "cache_a")
            second_dir = os.path.join(tmpdir, "cache_b")

            first_cache = get_cache(first_dir)
            second_cache = get_cache(second_dir)

        self.assertIsNot(first_cache, second_cache)
        self.assertEqual(os.path.normcase(os.path.abspath(second_cache.cache_dir)), os.path.normcase(os.path.abspath(second_dir)))

    def test_backup_manager_reinitializes_when_directory_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            first_dir = os.path.join(tmpdir, "backup_a")
            second_dir = os.path.join(tmpdir, "backup_b")

            first_manager = get_backup_manager(first_dir)
            second_manager = get_backup_manager(second_dir)

        self.assertIsNot(first_manager, second_manager)
        self.assertEqual(
            os.path.normcase(os.path.abspath(second_manager.backup_dir)),
            os.path.normcase(os.path.abspath(second_dir)),
        )


class TestEncryptedArchiveDetection(unittest.TestCase):
    def test_mv_mz_encrypted_audio_extension_is_registered(self) -> None:
        self.assertIn(".rpgmvo", HomeInterface.ENCRYPTED_ARCHIVE_EXTENSIONS)
        self.assertNotIn(".rpgmwo", HomeInterface.ENCRYPTED_ARCHIVE_EXTENSIONS)


if __name__ == "__main__":
    unittest.main()
