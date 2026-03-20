import json
import os
import tempfile
import unittest

from src.core.parsers.json_parser import JsonParser
from src.core.parsers.technical_invariants import JsonTechnicalInvariantVerifier


class TestStructuredJsonExtractor(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = JsonParser()

    def test_actor_rules_only_extract_player_visible_fields(self) -> None:
        payload = [
            None,
            {
                "id": 1,
                "name": "Harold",
                "nickname": "The Hero",
                "profile": "A brave knight.",
                "characterName": "Actor1",
                "faceName": "Actor1",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Actors.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        extracted_paths = {path for path, _text, _tag in entries}
        self.assertEqual(
            extracted_paths,
            {"1.name", "1.nickname", "1.profile"},
        )

    def test_map_rules_extract_safe_event_text_and_legacy_safe_segments(self) -> None:
        payload = {
            "displayName": "Forest Road",
            "events": [
                None,
                {
                    "id": 1,
                    "name": "Intro",
                    "pages": [
                        {
                            "list": [
                                {"code": 401, "parameters": ["Welcome home."]},
                                {"code": 102, "parameters": [["Yes", "No"], 0, 0, 0, 0]},
                                {"code": 356, "parameters": ['Quest Add "Find the child"']},
                                {"code": 355, "parameters": ['$gameMessage.add("Script line one")']},
                                {"code": 655, "parameters": ['$gameMessage.add("Script line two")']},
                            ]
                        }
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Map001.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        extracted_paths = {path for path, _text, _tag in entries}
        self.assertIn("displayName", extracted_paths)
        self.assertIn("events.1.pages.0.list.0.parameters.0", extracted_paths)
        self.assertIn("events.1.pages.0.list.1.parameters.0.0", extracted_paths)
        self.assertIn("events.1.pages.0.list.2.parameters.0.@MVCMD0", extracted_paths)
        self.assertIn("events.1.pages.0.list.3.@SCRIPTMERGE1.@JS0", extracted_paths)

    def test_structured_map_keeps_mz_plugin_command_bridge(self) -> None:
        payload = {
            "displayName": "",
            "events": [
                None,
                {
                    "id": 1,
                    "pages": [
                        {
                            "list": [
                                {
                                    "code": 357,
                                    "parameters": [
                                        "MyPlugin",
                                        "ShowHint",
                                        "Open the menu",
                                        {"text": "Press confirm"},
                                    ],
                                },
                                {"code": 657, "parameters": ["Extra help line"]},
                            ]
                        }
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Map002.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        extracted_paths = {path for path, _text, _tag in entries}
        self.assertIn("events.1.pages.0.list.0.parameters.2", extracted_paths)
        self.assertIn("events.1.pages.0.list.0.parameters.3.text", extracted_paths)
        self.assertIn("events.1.pages.0.list.1.parameters.0", extracted_paths)

    def test_structured_invariant_blocks_unexpected_mutation(self) -> None:
        payload = {
            "gameTitle": "Project One",
            "locale": "en_US",
            "terms": {
                "basic": ["Level", "Lv"],
                "commands": [],
                "params": [],
                "messages": {},
            },
            "elements": [],
            "skillTypes": [],
            "weaponTypes": [],
            "armorTypes": [],
            "equipTypes": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "System.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            original_setter = self.parser._set_value_at_path

            def bad_setter(data: object, path: str, value: object) -> None:
                original_setter(data, path, value)
                if isinstance(data, dict) and path == "gameTitle":
                    data["locale"] = "tr_TR"

            self.parser._set_value_at_path = bad_setter  # type: ignore[assignment]
            result = self.parser.apply_translation(file_path, {"gameTitle": "Proje Bir"})

        self.assertIsNone(result)

    def test_protected_structured_surfaces_reject_imported_translation_keys(self) -> None:
        payload = [
            None,
            {
                "id": 1,
                "name": "Debug Town",
                "expanded": True,
                "order": 1,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "MapInfos.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            result = self.parser.apply_translation(file_path, {"1.name": "Translated Name"})

        self.assertIsNone(result)
        self.assertIn("rejected unsupported translation keys", self.parser.last_apply_error or "")

    def test_structured_translate_notes_keeps_note_tag_extraction(self) -> None:
        payload = [
            None,
            {
                "id": 1,
                "name": "Potion",
                "description": "Restores HP",
                "note": "<Description>Player visible note</Description>",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Items.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            parser = JsonParser(translate_notes=True)
            entries = parser.extract_text(file_path)

        extracted_paths = {path for path, _text, _tag in entries}
        self.assertIn("1.note.@NOTEBLOCK_0", extracted_paths)

    def test_structured_system_rules_keep_extended_term_lists(self) -> None:
        payload = {
            "gameTitle": "Game",
            "currencyUnit": "Gold",
            "terms": {
                "basic": ["Level"],
                "commands": ["Fight"],
                "params": ["HP"],
                "messages": {"actionFailure": "Fail"},
                "types": ["Magic"],
            },
            "etypeNames": ["Weapon"],
            "stypeNames": ["Special"],
            "wtypeNames": ["Sword"],
            "atypeNames": ["Shield"],
            "elements": ["Fire"],
            "skillTypes": ["Magic"],
            "weaponTypes": ["Sword"],
            "armorTypes": ["Armor"],
            "equipTypes": ["Weapon"],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "System.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        extracted_paths = {path for path, _text, _tag in entries}
        self.assertIn("terms.types.0", extracted_paths)
        self.assertIn("etypeNames.0", extracted_paths)
        self.assertIn("stypeNames.0", extracted_paths)
        self.assertIn("wtypeNames.0", extracted_paths)
        self.assertIn("atypeNames.0", extracted_paths)

    def test_script_merge_paths_expand_to_all_changed_lines(self) -> None:
        verifier = JsonTechnicalInvariantVerifier(self.parser._escape_path_key)
        allowed = verifier.build_allowed_paths(
            ["events.1.pages.0.list.3.@SCRIPTMERGE1.@JS0"]
        )
        self.assertEqual(
            allowed,
            {
                "events.1.pages.0.list.3.parameters.0",
                "events.1.pages.0.list.4.parameters.0",
            },
        )

    def test_mapinfos_editor_names_are_not_extracted_in_structured_mode(self) -> None:
        payload = [
            None,
            {
                "id": 1,
                "name": "Debug Town",
                "expanded": True,
                "order": 1,
                "parentId": 0,
                "scrollX": 0,
                "scrollY": 0,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "MapInfos.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        self.assertEqual(entries, [])

    def test_troop_pages_use_structured_event_extraction_but_skip_troop_name(self) -> None:
        payload = [
            None,
            {
                "id": 1,
                "name": "Slime Squad",
                "members": [],
                "pages": [
                    {
                        "list": [
                            {"code": 401, "parameters": ["Troop dialogue line"]},
                            {"code": 102, "parameters": [["Fight", "Run"], 0, 0, 0, 0]},
                        ]
                    }
                ],
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Troops.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        extracted_values = {text for _path, text, _tag in entries}
        extracted_paths = {path for path, _text, _tag in entries}
        self.assertNotIn("Slime Squad", extracted_values)
        self.assertIn("1.pages.0.list.0.parameters.0", extracted_paths)
        self.assertIn("1.pages.0.list.1.parameters.0.0", extracted_paths)

    def test_protected_editor_and_plugin_config_files_extract_nothing(self) -> None:
        fixtures = {
            "Animations.json": [
                None,
                {"id": 1, "name": "Big Explosion", "animation1Name": "ExplosionA", "timings": []},
            ],
            "Tilesets.json": [
                None,
                {"id": 1, "name": "Dungeon A", "tilesetNames": ["Dungeon_A1"], "note": "<Tile Flag>"},
            ],
            "QSprite.json": {
                "hero": {
                    "name": "hero",
                    "sampleImg": "img/characters/Q_Hero.png",
                    "poses": {
                        "idle2": {"name": "Idle 2", "pattern": [0]},
                    },
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            for filename, payload in fixtures.items():
                file_path = os.path.join(tmpdir, filename)
                with open(file_path, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False)

                entries = self.parser.extract_text(file_path)
                self.assertEqual(entries, [], filename)


if __name__ == "__main__":
    unittest.main()
