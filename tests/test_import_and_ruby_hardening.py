import json
import os
import tempfile
import unittest
from unittest.mock import patch
import zlib

from src.core.export_import import TranslationImporter
from src.core.parsers.ruby_parser import RubyParser
from src.core.constants import TOKEN_INTERNAL_MERGE

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

    def test_ruby_surface_aware_attributes_skip_asset_name_fields(self) -> None:
        class FakeRubyObject:
            def __init__(self, attributes: dict[str, object]) -> None:
                self.attributes = attributes

        parser = RubyParser()
        parser.extracted = []
        parser._current_file_basename = "enemies"

        obj = FakeRubyObject({
            "@animation1_name": "Ruins3",
            "@battler_name": "Slime",
            "@name": "Visible Event Name",
        })
        parser._walk(obj, "@root", 0)

        values = [text for _path, text, _ctx in parser.extracted]
        self.assertIn("Visible Event Name", values)
        self.assertNotIn("Ruins3", values)
        self.assertNotIn("Slime", values)

    def test_ruby_file_allowlist_blocks_actor_asset_fields(self) -> None:
        class FakeRubyObject:
            def __init__(self, attributes: dict[str, object]) -> None:
                self.attributes = attributes

        parser = RubyParser()
        parser.extracted = []
        parser._current_file_basename = "actors"

        obj = FakeRubyObject({
            "@name": "Harold",
            "@nickname": "Hero",
            "@face_name": "Actor1",
            "@character_name": "People1",
        })
        parser._walk(obj, "@root", 0)

        values = [text for _path, text, _ctx in parser.extracted]
        self.assertIn("Harold", values)
        self.assertIn("Hero", values)
        self.assertNotIn("Actor1", values)
        self.assertNotIn("People1", values)

    def test_ruby_protected_files_extract_no_entries(self) -> None:
        class FakeRubyParser(RubyParser):
            def _load_ruby_marshal(self, file_path: str) -> object:
                return {"@animation1_name": "Ruins3", "@name": "Should Not Extract"}

        parser = FakeRubyParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Animations.rvdata2")
            with open(file_path, "wb") as handle:
                handle.write(b"placeholder")

            extracted = parser.extract_text(file_path)

        self.assertEqual(extracted, [])

    def test_ruby_system_terms_and_words_are_extracted_but_asset_refs_are_not(self) -> None:
        class FakeRubyObject:
            def __init__(self, attributes: dict[str, object]) -> None:
                self.attributes = attributes

        parser = RubyParser()
        parser.extracted = []
        parser._current_file_basename = "system"

        system_obj = FakeRubyObject({
            "@game_title": "My Game",
            "@currency_unit": "Gold",
            "@terms": {
                "basic": ["Level", "HP"],
                "messages": {"victory": "Victory!"},
            },
            "@words": {
                "attack": "Attack",
            },
            "@battleback_name": "Ruins3",
        })
        parser._walk(system_obj, "@system", 0)

        values = [text for _path, text, _ctx in parser.extracted]
        self.assertIn("My Game", values)
        self.assertIn("Gold", values)
        self.assertIn("Level", values)
        self.assertIn("HP", values)
        self.assertIn("Victory!", values)
        self.assertIn("Attack", values)
        self.assertNotIn("Ruins3", values)

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

    def test_ruby_event_command_skips_single_token_non_ascii_asset_id(self) -> None:
        parser = RubyParser()
        parser._known_asset_identifiers = {"ゲオルイース"}
        parser.extracted = []

        parser._extract_event_command(401, ["ゲオルイース"], "0")

        self.assertEqual(parser.extracted, [])

    def test_ruby_event_command_keeps_normal_dialogue_even_with_asset_registry(self) -> None:
        parser = RubyParser()
        parser._known_asset_identifiers = {"save"}
        parser.extracted = []

        parser._extract_event_command(401, ["Save the game now!"], "0")

        self.assertEqual(len(parser.extracted), 1)
        self.assertEqual(parser.extracted[0][1], "Save the game now!")

    def test_ruby_dialogue_path_is_whitelisted_by_extracted_tag(self) -> None:
        parser = RubyParser()
        parser._append_extracted("@events.1.@pages.0.@list.4.@parameters.0", "先輩", "message_dialogue")

        self.assertTrue(
            parser._is_whitelisted_text_path("@events.1.@pages.0.@list.4.@parameters.0", "先輩")
        )

    def test_ruby_bundled_dialogue_path_whitelists_member_lines(self) -> None:
        parser = RubyParser()
        # Using the NEW internal merge token
        parser._append_extracted("@events.1.@pages.0.@list.4_bundled_6", f"先輩{TOKEN_INTERNAL_MERGE}『...』", "message_dialogue/hasPicture")

        self.assertTrue(
            parser._is_whitelisted_text_path("@events.1.@pages.0.@list.4.@parameters.0", "先輩")
        )

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

            # Pass original_data directly to apply_translation so it can be compared
            # without needing to reload from file (which would require mock complexity)
            original_payload = {"sound": "Cursor1", "label": "Open Menu"}

            with patch("src.core.parsers.ruby_parser.rubymarshal.reader.load", return_value=original_payload):
                updated = parser.apply_translation(file_path, {"sound": "İmleç1"}, original_data=original_payload)

        self.assertIsNone(updated)
        self.assertIn("Asset invariant violation", parser.last_apply_error or "")


class TestRubyMarshalWriteBackIntegration(unittest.TestCase):
    """End-to-end tests for the extract → apply_translation → write-back cycle."""

    # ------------------------------------------------------------------ helpers
    class _FakeRubyObject:
        def __init__(self, attributes: dict) -> None:
            self.attributes = attributes

    def _make_command(self, code: int, params: list) -> "_FakeRubyObject":
        return self._FakeRubyObject({"@code": code, "@parameters": params, "@indent": 0})

    # ------------------------------------------------------------------ #1 simple name round-trip
    def test_apply_translation_simple_name_roundtrip(self) -> None:
        """apply_translation must overwrite a plain string attribute."""
        class FakeRubyParser(RubyParser):
            def _load_ruby_marshal(self, file_path: str) -> object:
                return [None, {"@name": "ヒーロー"}]

            def _find_asset_mutations(self, original, updated):
                return []

        parser = FakeRubyParser()
        with tempfile.TemporaryDirectory() as tmpdir:
            fp = os.path.join(tmpdir, "Actors.rvdata2")
            open(fp, "wb").close()
            updated = parser.apply_translation(fp, {"1.@name": "Kahraman"})

        self.assertIsNotNone(updated)
        self.assertEqual(updated[1]["@name"], "Kahraman")

    # ------------------------------------------------------------------ #2 bytes round-trip (encoding preserved)
    def test_apply_translation_bytes_encoding_preserved(self) -> None:
        """Byte strings must be re-encoded to the original encoding on write-back."""
        class FakeRubyParser(RubyParser):
            def _load_ruby_marshal(self, file_path: str) -> object:
                return [None, {"@name": "ヒーロー".encode("shift_jis")}]

            def _find_asset_mutations(self, original, updated):
                return []

        parser = FakeRubyParser()
        with tempfile.TemporaryDirectory() as tmpdir:
            fp = os.path.join(tmpdir, "Actors.rvdata2")
            open(fp, "wb").close()
            updated = parser.apply_translation(fp, {"1.@name": "勇者"})

        self.assertIsNotNone(updated)
        result = updated[1]["@name"]
        # Must still be bytes and decodeable as shift_jis
        self.assertIsInstance(result, bytes)
        self.assertEqual(result.decode("shift_jis"), "勇者")

    # ------------------------------------------------------------------ #3 bundled dialogue round-trip
    def test_apply_bundled_dialogue_roundtrip(self) -> None:
        """Bundled multi-line dialogue must be split back across consecutive command params."""
        from src.core.constants import TOKEN_INTERNAL_MERGE

        cmd0 = self._make_command(401, ["Line one."])
        cmd1 = self._make_command(401, ["Line two."])
        cmd2 = self._make_command(401, ["Line three."])
        commands = [cmd0, cmd1, cmd2]

        parser = RubyParser()
        # Simulate bundled path: commands 0_bundled_2 → translate as merged string
        merged_translation = TOKEN_INTERNAL_MERGE.join(["Satır bir.", "Satır iki.", "Satır üç."])
        parser._apply_bundled_translation(commands, f"0{RubyParser.BUNDLED_PATH_MARKER}2", merged_translation)

        self.assertEqual(cmd0.attributes["@parameters"][0], "Satır bir.")
        self.assertEqual(cmd1.attributes["@parameters"][0], "Satır iki.")
        self.assertEqual(cmd2.attributes["@parameters"][0], "Satır üç.")

    # ------------------------------------------------------------------ #4 CommonEvents event commands extracted
    def test_commonevents_event_commands_are_extracted(self) -> None:
        """Dialogue inside CommonEvents must be extracted via _walk_command_list."""
        cmd = self._FakeRubyObject({"@code": 401, "@parameters": ["Common event dialogue."], "@indent": 0})
        common_event = self._FakeRubyObject({"@name": "Intro", "@list": [cmd]})

        parser = RubyParser()
        parser.extracted = []
        parser._current_file_basename = "commonevents"

        parser._walk(common_event, "@commonevents.1", 0)

        values = [text for _path, text, _tag in parser.extracted]
        self.assertIn("Common event dialogue.", values)
        self.assertIn("Intro", values)

    # ------------------------------------------------------------------ #5 Kod 402 (When [Choice]) extracted
    def test_code_402_choice_when_is_extracted(self) -> None:
        """Code 402 (When [Choice]) params[1] must be extracted as a choice."""
        parser = RubyParser()
        parser.extracted = []

        parser._extract_event_command(402, [0, "Yes"], "list.5")

        self.assertEqual(len(parser.extracted), 1)
        _path, text, tag = parser.extracted[0]
        self.assertEqual(text, "Yes")
        self.assertEqual(tag, "choice")

    # ------------------------------------------------------------------ #6 zero-confidence bytes rejected
    def test_zero_confidence_bytes_not_extracted(self) -> None:
        """Bytes with undetermined encoding must not enter the extraction pipeline."""
        # Craft bytes that charset_normalizer cannot reliably detect AND that
        # will not cleanly decode as shift_jis / cp1252 / euc_jp / gbk.
        # We use a random high-byte sequence that defeats the fallback chain.
        bad_bytes = bytes([0x80, 0x81, 0x82, 0x83, 0x84, 0x85])

        parser = RubyParser()
        text, encoding = parser._decode_ruby_bytes(bad_bytes)

        # If every fallback raised UnicodeDecodeError the result is (None, None)
        # OR the normalizer picked something with confidence > 0 — either is OK
        # as long as we never silently accept confidence==0.0.
        if text is None:
            self.assertIsNone(encoding)
        else:
            # If charset_normalizer found a real encoding, confidence must be > 0
            from src.core.parsers.ruby_parser import _safe_decode_ruby_string
            info = _safe_decode_ruby_string(bad_bytes)
            self.assertGreater(info.confidence, 0.0)

    # ------------------------------------------------------------------ #7 asset mutation blocked after apply
    def test_apply_translation_blocks_asset_mutation(self) -> None:
        """apply_translation must return None when an asset filename is mutated."""
        class FakeRubyParser(RubyParser):
            def _load_ruby_marshal(self, file_path: str) -> object:
                return {"sound": "Cursor1", "label": "Open Menu"}

            def _find_asset_mutations(self, original, updated):
                # Simulate detection of a mutated asset key
                if updated.get("sound") != "Cursor1":
                    return ["sound"]
                return []

        parser = FakeRubyParser()
        with tempfile.TemporaryDirectory() as tmpdir:
            fp = os.path.join(tmpdir, "Map001.rvdata2")
            open(fp, "wb").close()
            result = parser.apply_translation(fp, {"sound": "İmleç1"})

        self.assertIsNone(result)
        self.assertIn("Asset invariant violation", parser.last_apply_error or "")


if __name__ == "__main__":
    unittest.main()
