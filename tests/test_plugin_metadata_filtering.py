import json
import os
import tempfile
import unittest

from src.core.parsers.json_parser import JsonParser


class TestPluginMetadataFiltering(unittest.TestCase):
    def _write_plugin_fixture(
        self,
        tmpdir: str,
        plugin_name: str,
        plugin_source: str,
        plugins_js: str,
    ) -> str:
        js_dir = os.path.join(tmpdir, "js")
        plugins_dir = os.path.join(js_dir, "plugins")
        os.makedirs(plugins_dir, exist_ok=True)

        with open(os.path.join(plugins_dir, f"{plugin_name}.js"), "w", encoding="utf-8") as handle:
            handle.write(plugin_source)
        plugins_js_path = os.path.join(js_dir, "plugins.js")
        with open(plugins_js_path, "w", encoding="utf-8") as handle:
            handle.write(plugins_js)
        return plugins_js_path

    def test_file_parameter_is_skipped_but_text_parameter_is_extracted(self) -> None:
        parser = JsonParser()
        plugin_name = "ExamplePlugin"
        plugin_source = """/*:
 * @plugindesc Example plugin.
 * @param Picture
 * @type file
 * @dir img/pictures/
 * @require 1
 * @default Window
 *
 * @param Loading Text
 * @type string
 * @default Loading %1
 */"""
        plugins_js = (
            'var $plugins = [{"name":"ExamplePlugin","status":true,"description":"",'
            '"parameters":{"Picture":"Window","Loading Text":"Loading %1"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertIn("Loading %1", values)
        self.assertNotIn("Window", values)

    def test_combo_asset_registry_is_skipped_but_completion_text_survives(self) -> None:
        parser = JsonParser()
        plugin_name = "PreloadPlugin"
        plugin_source = """/*:
 * @plugindesc Preload test plugin.
 * @param Preload System
 * @type combo
 * @option all
 * @option important
 * @option custom:
 * @option none
 * @desc Determines which system images are preloaded.
 * Type in "custom: f1, f2, ..." to use custom files.
 * @default none
 *
 * @param Complete Text
 * @type string
 * @desc The text used when all loading is complete.
 * @default Load Complete!
 */"""
        plugins_js = (
            'var $plugins = [{"name":"PreloadPlugin","status":true,"description":"",'
            '"parameters":{"Preload System":"custom: Window, IconSet","Complete Text":"Load Complete!"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertIn("Load Complete!", values)
        self.assertNotIn("custom: Window, IconSet", values)

    def test_struct_nested_file_field_is_skipped_but_nested_label_is_extracted(self) -> None:
        parser = JsonParser()
        plugin_name = "StructPlugin"
        plugin_source = """/*:
 * @plugindesc Struct-aware test plugin.
 * @param Entries
 * @type struct<Entry>[]
 * @default []
 *
 * @param Header Text
 * @type string
 * @default Header
 */
/*~struct~Entry:
 * @param FileName
 * @type file
 * @dir img/system/
 * @require 1
 * @default Window
 *
 * @param Label Text
 * @type string
 * @default Open Window
 */"""
        nested_value = json.dumps([
            json.dumps({"FileName": "Window", "Label Text": "Open Window"}, ensure_ascii=False)
        ], ensure_ascii=False)
        plugin_payload = [
            {
                "name": "StructPlugin",
                "status": True,
                "description": "",
                "parameters": {
                    "Entries": nested_value,
                    "Header Text": "Header",
                },
            }
        ]
        plugins_js = f"var $plugins = {json.dumps(plugin_payload, ensure_ascii=False)};\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertIn("Header", values)
        self.assertIn("Open Window", values)
        self.assertNotIn("Window", values)

    def test_note_text_parameter_is_extracted_but_note_code_parameter_is_skipped(self) -> None:
        parser = JsonParser()
        plugin_name = "NoteAwarePlugin"
        plugin_source = """/*:
 * @plugindesc Note-aware plugin.
 * @param HelpDesc
 * @text Help Description
 * @type note
 * @desc The help description shown to the player.
 * @default "A list of all settings."
 *
 * @param ShowHide
 * @text Show/Hide
 * @type note
 * @desc The code used to determine if this option is visible.
 * @default "show = true;"
 */"""
        plugins_js = (
            'var $plugins = [{"name":"NoteAwarePlugin","status":true,"description":"",'
            '"parameters":{"HelpDesc":"\\"A list of all settings.\\"","ShowHide":"\\"show = true;\\""}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertIn('"A list of all settings."', values)
        self.assertNotIn('"show = true;"', values)

    def test_combo_and_select_tokens_are_skipped_as_technical_options(self) -> None:
        parser = JsonParser()
        plugin_name = "TokenOptionPlugin"
        plugin_source = """/*:
 * @plugindesc Token option plugin.
 * @param triggerButton
 * @type combo[]
 * @option shift
 * @option control
 * @option tab
 * @default ["shift"]
 *
 * @param Clipping Mode
 * @type select
 * @option ON
 * @option Pc Only
 * @option OFF
 * @default Pc Only
 *
 * @param Menu Label
 * @type string
 * @default Options
 */"""
        plugins_js = (
            'var $plugins = [{"name":"TokenOptionPlugin","status":true,"description":"",'
            '"parameters":{"triggerButton":"[\\"shift\\", \\"tab\\"]","Clipping Mode":"Pc Only","Menu Label":"Options"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertIn("Options", values)
        self.assertNotIn('["shift", "tab"]', values)
        self.assertNotIn("Pc Only", values)

    def test_orientation_string_without_explicit_type_is_skipped(self) -> None:
        parser = JsonParser()
        plugin_name = "LegacyOrientationPlugin"
        plugin_source = """/*:
 * @plugindesc Legacy orientation plugin.
 * @param ActionBtn Orientation
 * @desc left or right; top or bottom
 * @default right; bottom
 *
 * @param Button Text
 * @type string
 * @default Confirm
 */"""
        plugins_js = (
            'var $plugins = [{"name":"LegacyOrientationPlugin","status":true,"description":"",'
            '"parameters":{"ActionBtn Orientation":"right; bottom","Button Text":"Confirm"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertIn("Confirm", values)
        self.assertNotIn("right; bottom", values)

    def test_metadata_path_skips_spaced_se_csv_parameter(self) -> None:
        parser = JsonParser()
        plugin_name = "GalvLikePlugin"
        plugin_source = """/*:
 * @plugindesc Galv-like sound setting.
 * @param Default Talk SE
 * @desc Sound effect for text blip.
 * @default Cursor1,80,150
 *
 * @param Message Text
 * @type string
 * @default Press any key
 */"""
        plugins_js = (
            'var $plugins = [{"name":"GalvLikePlugin","status":true,"description":"",'
            '"parameters":{"Default Talk SE":"Cursor1,80,150","Message Text":"Press any key"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertIn("Press any key", values)
        self.assertNotIn("Cursor1,80,150", values)

    def test_metadata_text_hint_does_not_extract_asset_filename(self) -> None:
        parser = JsonParser()
        plugin_name = "OverlayLikePlugin"
        plugin_source = """/*:
 * @plugindesc Overlay-like filename config.
 * @param Ground Layer Filename
 * @desc Image filename without extension.
 * @default ground38
 *
 * @param Display Text
 * @type string
 * @default Welcome hero
 */"""
        plugins_js = (
            'var $plugins = [{"name":"OverlayLikePlugin","status":true,"description":"",'
            '"parameters":{"Ground Layer Filename":"ground38","Display Text":"Welcome hero"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertIn("Welcome hero", values)
        self.assertNotIn("ground38", values)

    def test_metadata_symbol_key_is_treated_as_technical(self) -> None:
        parser = JsonParser()
        plugin_name = "MenuSymbolPlugin"
        plugin_source = """/*:
 * @plugindesc Menu symbol plugin.
 * @param Menu 90 Name
 * @default Options
 *
 * @param Menu 90 Symbol
 * @default options
 */"""
        plugins_js = (
            'var $plugins = [{"name":"MenuSymbolPlugin","status":true,"description":"",'
            '"parameters":{"Menu 90 Name":"Options","Menu 90 Symbol":"options"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertIn("Options", values)
        self.assertNotIn("options", values)

    def test_metadata_type_order_registry_labels_are_skipped(self) -> None:
        parser = JsonParser()
        plugin_name = "QuestOrderPlugin"
        plugin_source = """/*:
 * @plugindesc Quest order plugin.
 * @param Quest List Window
 * @type struct<ListWindow>
 * @default {}
 */
/*~struct~ListWindow:
 * @param Type Order
 * @type string[]
 * @default ["\\c[6]Main Quests","\\c[4]Side Quests"]
 */
/*~struct~Quest:
 * @param Type
 * @type combo
 * @option Main Quests
 * @option Side Quests
 * @default Main Quests
 */"""
        plugins_js = (
            'var $plugins = [{"name":"QuestOrderPlugin","status":true,"description":"",'
            '"parameters":{"Quest List Window":"{\"Type Order\":\"[\\\"\\\\c[6]Main Quests\\\",\\\"\\\\c[4]Side Quests\\\"]\"}"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertNotIn("\\c[6]Main Quests", values)
        self.assertNotIn("\\c[4]Side Quests", values)

    def test_metadata_console_comment_block_is_skipped(self) -> None:
        parser = JsonParser()
        plugin_name = "LunaticCodePlugin"
        plugin_source = """/*:
 * @plugindesc Lunatic code plugin.
 * @param Lunatic Mode
 * @type struct<LunaticMode>
 * @default {}
 */
/*~struct~LunaticMode:
 * @param Change Subtext
 * @default "// Variables:\n//   questId - ID of the quest whose subtext is changed\n// console.log('Quest ' + questId)"
 */"""
        plugins_js = (
            'var $plugins = [{"name":"LunaticCodePlugin","status":true,"description":"",'
            '"parameters":{"Lunatic Mode":"{\"Change Subtext\":\"\\\"// Variables:\\n//   questId - ID of the quest whose subtext is changed\\n// console.log(\'Quest \' + questId)\\\"\"}"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertFalse(any("console.log" in value for value in values))

    def test_metadata_input_binding_value_is_skipped_even_if_translated(self) -> None:
        parser = JsonParser()
        plugin_name = "ChronoLikePlugin"
        plugin_source = """/*:
 * @plugindesc Input binding plugin.
 * @param Attack Button
 * @desc Button used for attack. ( x , c , a , s , d , ok , pagedown , pageup , shift )
 * @default ok
 *
 * @param Attack Text
 * @type string
 * @default Attack
 */"""
        plugins_js = (
            'var $plugins = [{"name":"ChronoLikePlugin","status":true,"description":"",'
            '"parameters":{"Attack Button":"tamam","Attack Text":"Attack"}}];\n'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = self._write_plugin_fixture(tmpdir, plugin_name, plugin_source, plugins_js)
            extracted = parser.extract_text(file_path)

        values = {text for _path, text, _ctx in extracted}
        self.assertIn("Attack", values)
        self.assertNotIn("tamam", values)


if __name__ == "__main__":
    unittest.main()
