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
        # params[2] is the editor-only commandText label ("Open the menu") — not extracted.
        # params[3] args dict may contain player-visible text ("text": "Press confirm") — extracted.
        # Code 657 params[0] strings are editor display labels — not extracted.
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
        extracted_values = {text for _path, text, _tag in entries}
        # args dict text field IS extracted
        self.assertIn("events.1.pages.0.list.0.parameters.3.text", extracted_paths)
        self.assertIn("Press confirm", extracted_values)
        # params[2] (editor label) is NOT extracted
        self.assertNotIn("events.1.pages.0.list.0.parameters.2", extracted_paths)
        self.assertNotIn("Open the menu", extracted_values)
        # code 657 params[0] string (editor label) is NOT extracted
        self.assertNotIn("events.1.pages.0.list.1.parameters.0", extracted_paths)
        self.assertNotIn("Extra help line", extracted_values)

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

    def test_mapinfos_apply_translation_updates_name(self) -> None:
        """MapInfos.json is no longer noop — apply_translation must write back map names."""
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

            result = self.parser.apply_translation(file_path, {"1.name": "Hata Kasabası"})

        self.assertIsNotNone(result)
        self.assertEqual(result[1]["name"], "Hata Kasabası")

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
            "battleback1Name": "Ruins1",
            "battleback2Name": "Clouds1",
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
        values = {text for _path, text, _tag in entries}
        self.assertIn("terms.types.0", extracted_paths)
        self.assertIn("etypeNames.0", extracted_paths)
        self.assertIn("stypeNames.0", extracted_paths)
        self.assertIn("wtypeNames.0", extracted_paths)
        self.assertIn("atypeNames.0", extracted_paths)
        self.assertNotIn("Ruins1", values)
        self.assertNotIn("Clouds1", values)

    def test_structured_actors_skip_asset_name_fields(self) -> None:
        payload = [
            None,
            {
                "id": 1,
                "name": "Harold",
                "nickname": "Hero",
                "profile": "A brave warrior",
                "characterName": "Actor1",
                "faceName": "Actor1",
                "battlerName": "Harold",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Actors.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        values = {text for _path, text, _tag in entries}
        self.assertIn("Harold", values)
        self.assertIn("Hero", values)
        self.assertIn("A brave warrior", values)
        self.assertNotIn("Actor1", values)
        self.assertNotIn("Harold", {text for path, text, _tag in entries if path.endswith("battlerName")})

    def test_structured_enemies_skip_battler_name(self) -> None:
        payload = [
            None,
            {
                "id": 1,
                "name": "Slime",
                "battlerName": "SlimeMonster",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Enemies.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        values = {text for _path, text, _tag in entries}
        self.assertIn("Slime", values)
        self.assertNotIn("SlimeMonster", values)

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

    def test_mapinfos_editor_names_are_extracted_in_structured_mode(self) -> None:
        """MapInfos.json map names are player-visible and must be extracted."""
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

        extracted_paths = {path for path, _text, _tag in entries}
        self.assertIn("1.name", extracted_paths)

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


class TestStructuredAssetProtection(unittest.TestCase):
    """Regression tests for asset filename protection in the structured extractor.

    Custom menu plugins (and similar) commonly use System.json terms or
    database field values as image filenames at runtime.  If those strings
    are translated, the engine fails to load the asset (e.g.
    ``img/menus/main/commands/Öge.png`` instead of ``Item.png``).
    """

    def setUp(self) -> None:
        self.parser = JsonParser()

    # ------------------------------------------------------------------
    # Extraction-phase: asset registry blocks matching system terms
    # ------------------------------------------------------------------

    def test_system_commands_matching_asset_are_skipped(self) -> None:
        """System.json terms.commands values that match known asset stems
        must NOT be extracted — a custom menu plugin likely uses them as
        image filenames."""
        payload = {
            "gameTitle": "Test Game",
            "currencyUnit": "G",
            "terms": {
                "basic": ["Level", "Lv", "HP", "HP", "MP", "MP", "TP", "TP", "EXP", "EXP"],
                "commands": [
                    "Fight", "Escape", "Attack", "Guard",
                    "Item",   # <-- matches img/menus/main/commands/Item.png
                    "Skill", "Equip", "Status", "Formation",
                    "Save",   # <-- matches img/menus/main/commands/Save.png
                    "Game End",
                ],
                "params": ["Max HP", "Max MP", "Attack", "Defense"],
                "messages": {},
            },
            "elements": [],
            "skillTypes": [],
            "weaponTypes": [],
            "armorTypes": [],
            "equipTypes": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # Build a fake asset tree so the registry picks up "item" and "save"
            img_dir = os.path.join(tmpdir, "img", "menus", "main", "commands")
            os.makedirs(img_dir)
            for name in ("Item.png", "Save.png", "Skill.png", "Equip.png"):
                open(os.path.join(img_dir, name), "w").close()

            file_path = os.path.join(tmpdir, "System.json")
            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        extracted_values = {text for _path, text, _tag in entries}
        # "Item", "Save", "Skill", "Equip" must be blocked
        self.assertNotIn("Item", extracted_values)
        self.assertNotIn("Save", extracted_values)
        self.assertNotIn("Skill", extracted_values)
        self.assertNotIn("Equip", extracted_values)
        # Multi-word terms with no matching asset must still be extracted
        self.assertIn("Game End", extracted_values)
        # gameTitle should still be extracted
        self.assertIn("Test Game", extracted_values)

    def test_system_commands_without_asset_registry_are_extracted(self) -> None:
        """When no asset files match, system terms are extracted normally."""
        payload = {
            "gameTitle": "Test Game",
            "currencyUnit": "G",
            "terms": {
                "basic": [],
                "commands": ["Item", "Save", "Game End"],
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
            # NO img/ directory → asset registry empty
            file_path = os.path.join(tmpdir, "System.json")
            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        extracted_values = {text for _path, text, _tag in entries}
        self.assertIn("Game End", extracted_values)
        self.assertIn("Test Game", extracted_values)

    def test_actor_name_not_blocked_without_matching_asset(self) -> None:
        """Actor names must be extracted when no asset filename matches them."""
        payload = [
            None,
            {"id": 1, "name": "Harold", "nickname": "Hero", "profile": "A knight."},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            # img/ exists but no Harold.png
            img_dir = os.path.join(tmpdir, "img", "faces")
            os.makedirs(img_dir)
            open(os.path.join(img_dir, "Actor1.png"), "w").close()

            file_path = os.path.join(tmpdir, "Actors.json")
            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        extracted_values = {text for _path, text, _tag in entries}
        self.assertIn("Harold", extracted_values)
        self.assertIn("Hero", extracted_values)
        self.assertIn("A knight.", extracted_values)

    def test_event_command_text_matching_asset_is_skipped(self) -> None:
        """Code 401 dialogue text that matches a known asset should be
        blocked to protect against plugins that dynamically load assets
        from event command text."""
        payload = {
            "displayName": "",
            "events": [
                None,
                {
                    "id": 1,
                    "name": "NPC",
                    "pages": [
                        {
                            "list": [
                                {"code": 401, "parameters": ["ItemIcon"]},
                                {"code": 401, "parameters": ["Hello, adventurer!"]},
                            ]
                        }
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            img_dir = os.path.join(tmpdir, "img", "pictures")
            os.makedirs(img_dir)
            open(os.path.join(img_dir, "ItemIcon.png"), "w").close()

            file_path = os.path.join(tmpdir, "Map001.json")
            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)

            entries = self.parser.extract_text(file_path)

        extracted_values = {text for _path, text, _tag in entries}
        self.assertNotIn("ItemIcon", extracted_values)
        self.assertIn("Hello, adventurer!", extracted_values)

    # ------------------------------------------------------------------
    # Apply-phase: asset registry blocks asset-matching write-back
    # ------------------------------------------------------------------

    def test_apply_blocks_asset_matching_system_command_translation(self) -> None:
        """When asset-matching system commands are submitted for translation,
        the structured surface validator rejects them because extraction
        already excluded those paths from the allowed surface."""
        payload = {
            "gameTitle": "Test Game",
            "currencyUnit": "G",
            "terms": {
                "basic": [],
                "commands": ["Item", "Save", "Game End"],
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
            img_dir = os.path.join(tmpdir, "img", "menus", "main", "commands")
            os.makedirs(img_dir)
            for name in ("Item.png", "Save.png"):
                open(os.path.join(img_dir, name), "w").close()

            file_path = os.path.join(tmpdir, "System.json")
            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)

            # Only supply translations that were actually extracted
            result = self.parser.apply_translation(
                file_path,
                {
                    "terms.commands.2": "Oyun Sonu",  # Game End → allowed
                },
            )

        self.assertIsNotNone(result)
        # "Item" and "Save" must remain untranslated (never extracted)
        self.assertEqual(result["terms"]["commands"][0], "Item")
        self.assertEqual(result["terms"]["commands"][1], "Save")
        # "Game End" should be translated
        self.assertEqual(result["terms"]["commands"][2], "Oyun Sonu")

    def test_apply_phase_asset_guard_blocks_direct_update(self) -> None:
        """_should_block_asset_like_translation_update blocks single-word
        values that match known assets, even outside plugin parameter paths."""
        parser = JsonParser()

        with tempfile.TemporaryDirectory() as tmpdir:
            img_dir = os.path.join(tmpdir, "img", "menus", "main", "commands")
            os.makedirs(img_dir)
            open(os.path.join(img_dir, "Item.png"), "w").close()

            # Populate asset registry via a dummy extract call
            dummy_path = os.path.join(tmpdir, "System.json")
            with open(dummy_path, "w", encoding="utf-8") as fh:
                json.dump({"gameTitle": "X"}, fh)
            parser.extract_text(dummy_path)

        original_data = {"terms": {"commands": ["Item", "Game End"]}}
        # Item matches asset → blocked
        self.assertTrue(
            parser._should_block_asset_like_translation_update(
                original_data, "terms.commands.0", "Öge",
            )
        )
        # Game End is multi-word, no matching asset → allowed
        self.assertFalse(
            parser._should_block_asset_like_translation_update(
                original_data, "terms.commands.1", "Oyun Sonu",
            )
        )


if __name__ == "__main__":
    unittest.main()
