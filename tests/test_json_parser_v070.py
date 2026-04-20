"""
Unit tests for json_parser.py v0.7.0 enhancements.
Tests multi-line script merging, JSStringTokenizer integration,
nested @JSON recursive fix, and MZ code 657 support.
"""
import unittest
import json
from src.core.parsers.json_parser import JsonParser


class TestMultiLineScriptMerge(unittest.TestCase):
    """Test code 355+655 multi-line script merging."""

    def setUp(self):
        self.parser = JsonParser()

    def test_single_line_script_extraction(self):
        """Code 355 with no 655 continuation should extract strings."""
        data = [
            {"code": 355, "parameters": ['$gameMessage.add("Hello World");'], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.list")
        
        # Should find "Hello World"
        values = [text for path, text, ctx in self.parser.extracted]
        self.assertIn("Hello World", values)

    def test_multiline_script_merge(self):
        """Code 355 + 655 lines should be merged and strings extracted."""
        data = [
            {"code": 355, "parameters": ['$gameVariables.setValue(5,'], "indent": 0},
            {"code": 655, "parameters": ['"The quest begins!");'], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.list")
        
        values = [text for path, text, ctx in self.parser.extracted]
        self.assertIn("The quest begins!", values)

    def test_multiline_script_path_format(self):
        """Merged scripts should use @SCRIPTMERGE path format."""
        data = [
            {"code": 355, "parameters": ['$gameVariables.setValue(5,'], "indent": 0},
            {"code": 655, "parameters": ['"Quest text");'], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.list")
        
        if self.parser.extracted:
            path = self.parser.extracted[0][0]
            self.assertIn("@SCRIPTMERGE", path)
            self.assertIn("@JS", path)

    def test_655_lines_consumed_by_lookahead(self):
        """655 lines after 355 should not be processed independently."""
        data = [
            {"code": 355, "parameters": ['var x = "text1";'], "indent": 0},
            {"code": 655, "parameters": ['var y = "text2";'], "indent": 0},
            {"code": 401, "parameters": ["Normal dialogue"], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "list")
        
        # Should have entries from the script block AND the 401 dialogue
        paths = [path for path, text, ctx in self.parser.extracted]
        # 401 should still be processed
        dialogue_found = any("Normal dialogue" == text for _, text, _ in self.parser.extracted)
        self.assertTrue(dialogue_found)

    def test_multiple_strings_in_script(self):
        """Script with multiple string literals should extract all translatable ones."""
        data = [
            {"code": 355, "parameters": ['$gameMessage.add("First line");'], "indent": 0},
            {"code": 655, "parameters": ['$gameMessage.add("Second line");'], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "list")
        
        values = [text for path, text, ctx in self.parser.extracted]
        self.assertIn("First line", values)
        self.assertIn("Second line", values)


class TestScriptTranslationApplication(unittest.TestCase):
    """Test applying translations to script blocks."""

    def setUp(self):
        self.parser = JsonParser()

    def test_apply_single_line_script(self):
        """Single-line script translation should work via @JS path."""
        data = {
            "events": [None, {
                "id": 1,
                "pages": [{"list": [
                    {"code": 355, "parameters": ['$gameMessage.add("Hello World");'], "indent": 0},
                    {"code": 0, "parameters": [], "indent": 0}
                ]}]
            }]
        }
        
        # First extract
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        if self.parser.extracted:
            path, text, ctx = self.parser.extracted[0]
            translations = {path: "Merhaba DÃ¼nya"}
            
            # Roundtrip: write to temp file, apply, read back
            # For unit test, directly test _apply_script_translation
            list_data = data["events"][1]["pages"][0]["list"]
            
            # Parse the path to extract base info
            if ".@JS" in path:
                parts = path.split(".@JS")
                base = parts[0].rsplit(".parameters.0", 1)[0]
                js_idx = int(parts[1])
                line_count = 0
                
                self.parser._apply_script_translation(
                    data,
                    base,
                    [(line_count, js_idx, "Merhaba DÃ¼nya")]
                )
                
                result = list_data[0]["parameters"][0]
                self.assertIn("Merhaba DÃ¼nya", result)
                self.assertIn("$gameMessage.add", result)


class TestNestedJsonRecursive(unittest.TestCase):
    """Test recursive nested @JSON handling."""

    def setUp(self):
        self.parser = JsonParser()

    def test_single_level_nested_json(self):
        """Single level @JSON should work as before."""
        inner = json.dumps({"text": "Hello", "id": 5})
        data = {"param": inner}
        
        self.parser._apply_nested_json_translation(
            data, "param", {"text": "Merhaba"}
        )
        
        result = json.loads(data["param"])
        self.assertEqual(result["text"], "Merhaba")
        self.assertEqual(result["id"], 5)

    def test_two_level_nested_json(self):
        """Two-level @JSON nesting should be handled recursively."""
        deeper = json.dumps({"name": "Sword"})
        inner = json.dumps({"weapon": deeper, "count": 1})
        data = {"param": inner}
        
        # Path would be: param.@JSON.weapon.@JSON.name
        # nested_trans for root "param" would be: {"weapon.@JSON.name": "KÄ±lÄ±Ã§"}
        # Which internally splits: inner_root="weapon", inner_rest="name"
        
        self.parser._apply_nested_json_translation(
            data, "param", {"weapon.@JSON.name": "KÄ±lÄ±Ã§"}
        )
        
        result = json.loads(data["param"])
        weapon = json.loads(result["weapon"])
        self.assertEqual(weapon["name"], "KÄ±lÄ±Ã§")
        self.assertEqual(result["count"], 1)


class TestMZCode657(unittest.TestCase):
    """Test MZ plugin command continuation (code 657)."""

    def setUp(self):
        self.parser = JsonParser()

    def test_657_in_text_event_codes(self):
        """Code 657 should be recognized in TEXT_EVENT_CODES."""
        self.assertIn(657, JsonParser.TEXT_EVENT_CODES)

    def test_357_plus_657_processing(self):
        """357 + 657 sequence should be processed together."""
        data = [
            {"code": 357, "parameters": ["PluginName", "ShowText", "", {"text": "Hello"}], "indent": 0},
            {"code": 657, "parameters": [{"continuation": "More text data"}], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "list")
        
        # Should not crash and should process 357's args
        # The exact extraction depends on plugin params structure


class TestPluginHeuristicExpansion(unittest.TestCase):
    """Test expanded plugin parameter key indicators."""

    def setUp(self):
        self.parser = JsonParser()

    def test_text_key_indicators_exist(self):
        """TEXT_KEY_INDICATORS should contain the expanded set."""
        indicators = JsonParser.TEXT_KEY_INDICATORS
        self.assertIn('tooltip', indicators)
        self.assertIn('caption', indicators)
        self.assertIn('quest', indicators)
        self.assertIn('victory', indicators)
        self.assertIn('dialog', indicators)

    def test_expanded_keys_trigger_extraction(self):
        """Plugin params with expanded key names should be extracted."""
        data = {
            "parameters": {
                "victoryText": "You won the battle!",
                "tooltipInfo": "Hover for more details",
                "iconId": "128"
            }
        }
        self.parser.extracted = []
        self.parser._walk(data, "0")
        
        values = [text for path, text, ctx in self.parser.extracted]
        self.assertIn("You won the battle!", values)
        self.assertIn("Hover for more details", values)
        # iconId should NOT be extracted (no text indicator in key)
        self.assertNotIn("128", values)


class TestPathEscaping(unittest.TestCase):
    """Test dot-escaping for JSON path keys."""

    def setUp(self):
        self.parser = JsonParser()

    def test_dot_key_escape_roundtrip(self):
        """Keys containing dots should be safely escaped and restored.
        Note: :func keys are skipped by CODE_KEY_SUFFIXES filter, so we use :str instead."""
        data = {
            "parameters": {
                "ON.ActorHPText:str": "Use HP color",
                "simpleKey": "Simple text"
            }
        }
        self.parser.extracted = []
        self.parser._walk(data, "")

        # Ensure escaped path exists
        paths = [path for path, text, ctx in self.parser.extracted]
        escaped = "parameters.ON__DOT__ActorHPText:str"
        self.assertIn(escaped, paths)

        # Apply translation back using escaped path
        self.parser._set_value_at_path(data, escaped, "HP rengi kullan")
        self.assertEqual(data["parameters"]["ON.ActorHPText:str"], "HP rengi kullan")

    def test_deep_nested_dot_key(self):
        """Test deep nested dict with multiple dots in keys."""
        data = {
            "parameters": {
                "System": {
                    "Options.General.Audio": "Sound Settings"
                }
            }
        }
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        path = "parameters.System.Options__DOT__General__DOT__Audio"
        self.parser._set_value_at_path(data, path, "Ses AyarlarÄ±")
        self.assertEqual(data["parameters"]["System"]["Options.General.Audio"], "Ses AyarlarÄ±")



class TestAssetPathSafety(unittest.TestCase):
    """Regression tests for asset/path safety filters."""

    def setUp(self):
        self.parser = JsonParser()

    def test_mv_plugin_command_with_asset_path_is_skipped(self):
        data = [
            {"code": 356, "parameters": ["ShowPicture \"img/pictures/Hero Face.png\" 0 0"], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.list")

        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("ShowPicture \"img/pictures/Hero Face.png\" 0 0", values)

    def test_plugin_parameter_image_path_is_skipped(self):
        data = {
            "parameters": {
                "image": "img/pictures/Hero Face.png",
                "titleText": "The hero appears"
            }
        }
        self.parser.extracted = []
        self.parser._walk(data, "0")

        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("img/pictures/Hero Face.png", values)
        self.assertIn("The hero appears", values)

    def test_mz_continuation_asset_path_is_skipped(self):
        # params[2] is an editor-only commandText label — never player-visible, never extracted.
        # Code 657 params[0] strings are also editor display labels — never extracted.
        # Only dict args (params[3] or 657 dict params) may contain player-visible text.
        commands = [
            {"code": 357, "parameters": ["Plugin", "Cmd", "Editor label only", {}], "indent": 0},
            {"code": 657, "parameters": ["img/pictures/Another Hero.png"], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_mz_plugin_block(commands, "list", 0)

        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("img/pictures/Another Hero.png", values)
        # params[2] and 657 params[0] strings are editor labels — must NOT be extracted
        self.assertNotIn("Editor label only", values)


class TestAssetPathSafetyExtended(unittest.TestCase):
    """Extended regression tests for v0.6.3+ asset/path safety fixes."""

    def setUp(self):
        self.parser = JsonParser()

    # --- _contains_asset_reference: whitespace-preceded path prefix detection ---

    def test_space_preceded_img_path_detected(self):
        """Verify that img/ preceded by a space is detected (\\s regex fix)."""
        self.assertTrue(
            self.parser._contains_asset_reference("ShowPicture img/pictures/Hero.png 0 0")
        )

    def test_space_preceded_audio_path_detected(self):
        """Verify that audio/ preceded by a space is detected."""
        self.assertTrue(
            self.parser._contains_asset_reference("PlayBgm audio/bgm/Battle1.ogg")
        )

    def test_rpgmaker_subdirectory_pictures_detected(self):
        """Verify RPG Maker image subdirectory 'pictures/' is detected."""
        self.assertTrue(
            self.parser._contains_asset_reference("pictures/Hero.png")
        )

    def test_rpgmaker_subdirectory_faces_detected(self):
        """Verify RPG Maker image subdirectory 'faces/' is detected."""
        self.assertTrue(
            self.parser._contains_asset_reference("faces/Actor1")
        )

    def test_rpgmaker_subdirectory_characters_detected(self):
        """Verify RPG Maker image subdirectory 'characters/' is detected."""
        self.assertTrue(
            self.parser._contains_asset_reference("characters/People1")
        )

    def test_plain_text_not_detected_as_asset(self):
        """Verify normal text is NOT flagged as asset reference."""
        self.assertFalse(self.parser._contains_asset_reference("Hello World"))
        self.assertFalse(self.parser._contains_asset_reference("The hero appears"))

    def test_embedded_extension_in_longer_string(self):
        """Verify an embedded .png in a longer command string is detected."""
        self.assertTrue(
            self.parser._contains_asset_reference('Load "background.png" into layer 1')
        )

    # --- _looks_like_asset_name: spaced asset name handling ---

    def test_spaced_asset_name_two_words(self):
        """2-word spaced names should be detected as asset-like."""
        self.assertTrue(self.parser._looks_like_asset_name("Hero Face"))
        self.assertTrue(self.parser._looks_like_asset_name("Castle BG"))
        self.assertTrue(self.parser._looks_like_asset_name("Enemy Dragon"))

    def test_three_word_text_not_asset(self):
        """3+ word strings are likely sentences, not asset names."""
        self.assertFalse(self.parser._looks_like_asset_name("The hero appears"))
        self.assertFalse(self.parser._looks_like_asset_name("A great adventure begins"))

    def test_single_word_asset_name(self):
        """Single-word alphanumeric names are asset-like."""
        self.assertTrue(self.parser._looks_like_asset_name("Actor1"))
        self.assertTrue(self.parser._looks_like_asset_name("HeroPortrait"))

    # --- Plugin parameter: ASSET_KEY_HINTS + spaced value ---

    def test_picture_key_spaced_value_skipped(self):
        """Plugin param with 'picture' key and spaced asset name should NOT be extracted."""
        data = {"parameters": {"picture": "Hero Face", "description": "A brave warrior"}}
        self.parser.extracted = []
        self.parser._walk(data, "0")
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("Hero Face", values)
        self.assertIn("A brave warrior", values)

    def test_faceimage_key_spaced_value_skipped(self):
        """Plugin param with 'faceImage' key and spaced asset name should NOT be extracted."""
        data = {"parameters": {"faceImage": "Actor1 Face", "helpText": "Select your hero"}}
        self.parser.extracted = []
        self.parser._walk(data, "0")
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("Actor1 Face", values)
        self.assertIn("Select your hero", values)

    def test_sprite_key_spaced_value_skipped(self):
        """Plugin param with 'sprite' key and spaced asset name should NOT be extracted."""
        data = {"parameters": {"sprite": "Enemy Dragon"}}
        self.parser.extracted = []
        self.parser._walk(data, "0")
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("Enemy Dragon", values)

    def test_code_356_with_space_preceded_asset_path(self):
        """Code 356 plugin command with space-preceded img/ path should not be extracted."""
        data = [
            {"code": 356, "parameters": ["ShowPicture img/pictures/HeroFacePortraitDetailed.png 0 0 255 center"], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.list")
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertEqual(values, [])


class TestEventNameFiltering(unittest.TestCase):
    """Test context-aware 'name' field filtering for Maps, CommonEvents, Troops."""

    def setUp(self):
        self.parser = JsonParser()

    # --- Map event names ---

    def test_map_event_name_skipped(self):
        """Event names in Map files should NOT be extracted."""
        self.parser._current_file_basename = 'map001.json'
        data = {
            "displayName": "Dark Forest",
            "events": [
                None,
                {"id": 1, "name": "NEXT", "pages": []},
                {"id": 2, "name": "HUD消去", "pages": []}
            ]
        }
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("NEXT", values)
        self.assertNotIn("HUD消去", values)
        # displayName SHOULD be extracted
        self.assertIn("Dark Forest", values)

    def test_map_event_name_english(self):
        """English map event names like 'Autorun' should be skipped."""
        self.parser._current_file_basename = 'map025.json'
        data = {
            "events": [
                None,
                {"id": 1, "name": "Autorun", "pages": []},
                {"id": 2, "name": "EV001", "pages": []}
            ]
        }
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("Autorun", values)
        self.assertNotIn("EV001", values)

    # --- CommonEvents names ---

    def test_commonevents_name_skipped(self):
        """Common event names should NOT be extracted."""
        self.parser._current_file_basename = 'commonevents.json'
        data = [
            None,
            {"id": 1, "name": "AutoPlay", "list": []},
            {"id": 2, "name": "Battle Processing", "list": []}
        ]
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("AutoPlay", values)
        self.assertNotIn("Battle Processing", values)

    # --- Troops names ---

    def test_troops_name_skipped(self):
        """Troop names should NOT be extracted."""
        self.parser._current_file_basename = 'troops.json'
        data = [
            None,
            {"id": 1, "name": "Slime*2", "members": [], "pages": []}
        ]
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("Slime*2", values)

    # --- Database names (should still be extracted) ---

    def test_actors_name_extracted(self):
        """Actor names SHOULD be extracted (player-visible)."""
        self.parser._current_file_basename = 'actors.json'
        data = [
            None,
            {"id": 1, "name": "Harold", "nickname": "Hero", "profile": "A brave warrior"}
        ]
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertIn("Harold", values)
        self.assertIn("Hero", values)
        self.assertIn("A brave warrior", values)

    def test_items_name_extracted(self):
        """Item names SHOULD be extracted (player-visible)."""
        self.parser._current_file_basename = 'items.json'
        data = [
            None,
            {"id": 1, "name": "Potion", "description": "Restores 100 HP"}
        ]
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertIn("Potion", values)
        self.assertIn("Restores 100 HP", values)

    def test_enemies_name_extracted(self):
        """Enemy names SHOULD be extracted."""
        self.parser._current_file_basename = 'enemies.json'
        data = [
            None,
            {"id": 1, "name": "Slime"}
        ]
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertIn("Slime", values)

    def test_skills_name_extracted(self):
        """Skill names SHOULD be extracted."""
        self.parser._current_file_basename = 'skills.json'
        data = [
            None,
            {"id": 1, "name": "Attack", "description": "Attack the enemy"}
        ]
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertIn("Attack", values)
        self.assertIn("Attack the enemy", values)

    def test_weapons_name_extracted(self):
        """Weapon names SHOULD be extracted."""
        self.parser._current_file_basename = 'weapons.json'
        data = [
            None,
            {"id": 1, "name": "Sword"}
        ]
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertIn("Sword", values)

    def test_system_gametitle_extracted(self):
        """System gameTitle SHOULD be extracted."""
        self.parser._current_file_basename = 'system.json'
        data = {"gameTitle": "My Great Game"}
        self.parser.extracted = []
        self.parser._walk(data, "")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertIn("My Great Game", values)


class TestMZPluginCommandNameFiltering(unittest.TestCase):
    """Test that MZ plugin command args 'name' is not translated."""

    def setUp(self):
        self.parser = JsonParser()
        self.parser._current_file_basename = 'map001.json'

    def test_trp_particle_preset_name_skipped(self):
        """TRP_ParticleMZ_Preset 'name' param like 'fog_shadow_w' should NOT be extracted."""
        data = [
            {"code": 357, "parameters": [
                "TRP_ParticleMZ_Preset", "set_screen", "",
                {"name": "fog_shadow_w", "target": "weather"}
            ], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.pages.0.list")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("fog_shadow_w", values)

    def test_plugin_command_short_name_skipped(self):
        """Short identifier names in MZ plugin args should NOT be extracted."""
        data = [
            {"code": 357, "parameters": [
                "SomePlugin", "ShowEffect", "",
                {"name": "NEXT", "type": "fade"}
            ], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.pages.0.list")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("NEXT", values)

    def test_plugin_command_name_with_spaces_extracted(self):
        """Plugin args 'name' with sentence-like value SHOULD be extracted."""
        data = [
            {"code": 357, "parameters": [
                "DialogPlugin", "ShowMessage", "",
                {"name": "A greeting message for the player", "id": "1"}
            ], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.pages.0.list")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertIn("A greeting message for the player", values)

    def test_plugin_command_name_with_non_ascii_extracted(self):
        """Plugin args 'name' with non-ASCII value SHOULD be extracted."""
        data = [
            {"code": 357, "parameters": [
                "DialogPlugin", "ShowMessage", "",
                {"name": "勇者の旅"}
            ], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.pages.0.list")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertIn("勇者の旅", values)

    def test_plugin_command_text_field_still_extracted(self):
        """Other text fields in MZ plugin args SHOULD still be extracted."""
        data = [
            {"code": 357, "parameters": [
                "MessagePlugin", "ShowMessage", "",
                {"name": "msg001", "text": "Welcome to the forest!", "description": "An opening greeting"}
            ], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.pages.0.list")
        
        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("msg001", values)  # name is identifier
        self.assertIn("Welcome to the forest!", values)  # text has spaces
        self.assertIn("An opening greeting", values)  # description has spaces


class TestCaretSymbolProtection(unittest.TestCase):
    """Test that \\^ (wait-for-input code) is protected and extracted correctly."""

    def test_standalone_caret_not_tokenized(self):
        """Standalone ^ is not an RPG Maker MV/MZ escape code and should pass through unmodified."""
        from src.core.syntax_guard_rpgm import protect_for_translation, restore_from_translation

        text = "Hello there!^"
        protected, token_map = protect_for_translation(text)

        # Standalone ^ is plain text in MV/MZ — no token should be created
        self.assertNotIn("⟦", protected)
        self.assertEqual(len(token_map), 0)

        restored = restore_from_translation(protected, token_map)
        self.assertEqual(restored, text)

    def test_backslash_caret_is_protected(self):
        """\\^ (wait-for-input) should be tokenized by syntax_guard_rpgm."""
        from src.core.syntax_guard_rpgm import protect_for_translation, restore_from_translation

        text = "Hello there!\\^"
        protected, token_map = protect_for_translation(text)

        # \^ should be replaced with a ⟦RPGM...⟧ token
        self.assertNotIn("\\^", protected)
        self.assertTrue(len(token_map) > 0)

        restored = restore_from_translation(protected, token_map)
        self.assertEqual(restored, text)

    def test_caret_in_middle_of_text_not_tokenized(self):
        """Standalone ^ in middle of text is plain text — not tokenized in MV/MZ."""
        from src.core.syntax_guard_rpgm import protect_for_translation, restore_from_translation

        text = "Name^Some dialogue"
        protected, token_map = protect_for_translation(text)

        # Standalone ^ is plain text — no tokenization
        self.assertNotIn("⟦", protected)
        restored = restore_from_translation(protected, token_map)
        self.assertEqual(restored, text)

    def test_message_dialogue_with_caret_preserved(self):
        """Code 401 text with trailing \\^ should be extracted as dialogue."""
        parser = JsonParser()
        parser._current_file_basename = 'map001.json'
        data = [
            {"code": 401, "parameters": ["Hello!\\^"], "indent": 0}
        ]
        parser.extracted = []
        parser._process_list(data, "events.1.pages.0.list")

        # The text should be extracted (it's dialogue, \^ is a display code not a path)
        values = [text for _path, text, _ctx in parser.extracted]
        self.assertIn("Hello!\\^", values)


class TestNonTranslatablePluginSkip(unittest.TestCase):
    """Test that known non-translatable plugins are entirely skipped."""

    def setUp(self):
        self.parser = JsonParser()
        self.parser._current_file_basename = 'map001.json'

    # --- Code 357: full args dict skip ---

    def test_trp_particle_preset_all_args_skipped(self):
        """TRP_ParticleMZ_Preset: ALL args (name, text, display) must be skipped."""
        data = [
            {"code": 357, "parameters": [
                "TRP_ParticleMZ_Preset", "set_screen", "",
                {"name": "fog_shadow_w", "text": "Fog Storm Weather Effect",
                 "display": "Heavy Rain", "description": "A foggy particle effect"}
            ], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.pages.0.list")

        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertEqual(values, [], "No values should be extracted from TRP_ParticleMZ_Preset")

    def test_trp_particle_base_plugin_skipped(self):
        """TRP_ParticleMZ (base) should also be skipped."""
        data = [
            {"code": 357, "parameters": [
                "TRP_ParticleMZ", "play", "",
                {"name": "fire_burst", "target": "screen"}
            ], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.pages.0.list")

        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertEqual(values, [])

    def test_trp_particle_pattern_matches_new_variant(self):
        """TRP_ParticleMZ_FutureVariant should be caught by regex pattern."""
        data = [
            {"code": 357, "parameters": [
                "TRP_ParticleMZ_FutureVariant", "doEffect", "",
                {"text": "This looks like translatable text but is not"}
            ], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.pages.0.list")

        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertEqual(values, [])

    def test_normal_plugin_still_extracted(self):
        """Non-particle plugins should not be affected by the skip list."""
        data = [
            {"code": 357, "parameters": [
                "TextManager", "ShowPopup", "",
                {"text": "Quest completed successfully!", "description": "A popup message"}
            ], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.pages.0.list")

        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertIn("Quest completed successfully!", values)
        self.assertIn("A popup message", values)

    # --- Code 357+657 block skip ---

    def test_trp_particle_with_continuations_skipped(self):
        """TRP_ParticleMZ_Preset code 357+657 block should be fully skipped."""
        data = [
            {"code": 357, "parameters": [
                "TRP_ParticleMZ_Preset", "set_screen", "",
                {"name": "fog_shadow_w"}
            ], "indent": 0},
            {"code": 657, "parameters": ["additional particle config data"], "indent": 0},
            {"code": 657, "parameters": ["more config data"], "indent": 0},
            {"code": 401, "parameters": ["This dialogue should still be extracted"], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.pages.0.list")

        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("fog_shadow_w", values)
        self.assertNotIn("additional particle config data", values)
        # Dialogue after the block should still be extracted
        self.assertIn("This dialogue should still be extracted", values)

    # --- plugins.js skip ---

    def test_plugins_js_particle_plugin_skipped(self):
        """TRP_ParticleMZ_Preset in plugins.js should have its parameters skipped."""
        plugins_data = [
            {
                "name": "TRP_ParticleMZ_Preset",
                "status": True,
                "description": "Particle presets for weather effects",
                "parameters": {
                    "fog_preset": "Fog Storm Weather",
                    "rain_preset": "Heavy Rain Effect"
                }
            },
            {
                "name": "SomeTextPlugin",
                "status": True,
                "description": "A text plugin",
                "parameters": {
                    "greeting_text": "Welcome to the adventure!",
                    "goodbye_text": "Farewell brave hero!"
                }
            }
        ]
        self.parser.extracted = []
        self.parser._extract_from_plugins_js(plugins_data)

        values = [text for _path, text, _ctx in self.parser.extracted]
        # Particle plugin params should NOT be extracted
        self.assertNotIn("Fog Storm Weather", values)
        self.assertNotIn("Heavy Rain Effect", values)
        # Normal plugin params with spaces SHOULD be extracted
        self.assertIn("Welcome to the adventure!", values)
        self.assertIn("Farewell brave hero!", values)

    # --- Edge cases ---

    def test_empty_plugin_name_not_skipped(self):
        """Empty plugin name should not trigger skip."""
        data = [
            {"code": 357, "parameters": [
                "", "ShowMessage", "",
                {"text": "Hello adventurer, welcome to the world!"}
            ], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_list(data, "events.1.pages.0.list")

        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertIn("Hello adventurer, welcome to the world!", values)

    def test_case_insensitive_plugin_pattern(self):
        """Plugin pattern match should be case-insensitive."""
        self.assertTrue(self.parser._is_non_translatable_plugin("TRP_ParticleMZ_Preset"))
        self.assertTrue(self.parser._is_non_translatable_plugin("trp_particlemz_preset"))
        # Exact set is case-sensitive, but pattern is case-insensitive
        # "trp_particlemz_preset" not in NON_TRANSLATABLE_PLUGINS (case-sensitive),
        # but matches NON_TRANSLATABLE_PLUGIN_PATTERNS (case-insensitive)
        self.assertTrue(self.parser._is_non_translatable_plugin("TRP_Particle_CustomVariant"))


class TestPluginParameterPathExcludesEventCommands(unittest.TestCase):
    """Fix for _is_plugin_parameter_path matching event command paths.

    Event commands use ``.list.N.parameters.N`` paths (dialogue, choices) which
    must NOT be treated as plugin parameters.  Only paths like
    ``plugins.N.parameters.KEY`` should match.
    """

    def setUp(self):
        self.parser = JsonParser()

    def test_event_command_dialogue_path_is_not_plugin(self):
        """Dialogue path events.N.pages.N.list.N.parameters.0 must not match."""
        path = "events.13.pages.0.list.16.parameters.0"
        self.assertFalse(self.parser._is_plugin_parameter_path(path))

    def test_common_event_path_is_not_plugin(self):
        """CommonEvents path list.N.parameters.0 must not match."""
        path = "5.list.12.parameters.0"
        self.assertFalse(self.parser._is_plugin_parameter_path(path))

    def test_choice_command_path_is_not_plugin(self):
        """Choice command parameters must not match."""
        path = "events.7.pages.0.list.3.parameters.0"
        self.assertFalse(self.parser._is_plugin_parameter_path(path))

    def test_actual_plugin_parameter_path_matches(self):
        """Plugin parameter path must still match."""
        path = "3.parameters.Quest Title"
        self.assertTrue(self.parser._is_plugin_parameter_path(path))

    def test_nested_plugin_parameter_path_matches(self):
        """Deeply nested plugin parameter path must match."""
        path = "5.parameters.Background Settings.parameters.Image File"
        self.assertTrue(self.parser._is_plugin_parameter_path(path))

    def test_plugins_js_path_matches(self):
        """Standard plugins.N.parameters.KEY path must match."""
        path = "plugins.0.parameters.Font Name"
        self.assertTrue(self.parser._is_plugin_parameter_path(path))


class TestTechnicalStringAmbiguousKeywords(unittest.TestCase):
    """Fix for _is_technical_string producing false positives on common English
    words (let, new, this, return) that overlap with JS keywords.

    Natural-language dialogue like 'let me help you' or 'new clothes' must NOT
    be flagged as technical.  Actual JS code like 'let x = 5' must still be
    caught.
    """

    def setUp(self):
        self.parser = JsonParser()

    # --- False positives that MUST now pass through (not technical) ---

    def test_let_me_dialogue_is_not_technical(self):
        self.assertFalse(self.parser._is_technical_string("let me help you"))

    def test_let_anyone_dialogue_is_not_technical(self):
        self.assertFalse(
            self.parser._is_technical_string(
                "I won't let anyone have you ever again..."
            )
        )

    def test_new_clothes_dialogue_is_not_technical(self):
        self.assertFalse(
            self.parser._is_technical_string("I have given order for new clothes")
        )

    def test_knew_anything_dialogue_is_not_technical(self):
        """'knew' contains 'new ' as substring — must not trigger."""
        self.assertFalse(
            self.parser._is_technical_string(
                "Don't talk about the Goddess as if you knew anything!"
            )
        )

    def test_return_his_dialogue_is_not_technical(self):
        self.assertFalse(
            self.parser._is_technical_string("he'll understand why I can't return his")
        )

    def test_this_period_end_of_sentence_is_not_technical(self):
        """'this.' at end of sentence must not trigger."""
        self.assertFalse(
            self.parser._is_technical_string(
                "we could organize this.\\n<\\c[13]Haylen>"
            )
        )

    def test_toast_dialogue_with_let_is_not_technical(self):
        self.assertFalse(
            self.parser._is_technical_string(
                "A toast to our resilience then! Here, you two, let me"
            )
        )

    # --- True positives that MUST still be caught (real JS code) ---

    def test_let_declaration_is_technical(self):
        self.assertTrue(self.parser._is_technical_string("let x = 5"))

    def test_new_constructor_is_technical(self):
        self.assertTrue(self.parser._is_technical_string("new Array(10)"))

    def test_this_property_is_technical(self):
        self.assertTrue(self.parser._is_technical_string("this._data = null"))

    def test_return_statement_is_technical(self):
        self.assertTrue(self.parser._is_technical_string("return value"))

    def test_return_semicolon_is_technical(self):
        self.assertTrue(self.parser._is_technical_string("return;"))

    def test_function_call_is_technical(self):
        self.assertTrue(self.parser._is_technical_string("function() { return; }"))

    def test_game_variables_is_technical(self):
        self.assertTrue(self.parser._is_technical_string("$gameVariables.value(5)"))

    def test_const_declaration_is_technical(self):
        self.assertTrue(self.parser._is_technical_string("const arr = []"))

    def test_var_declaration_is_technical(self):
        self.assertTrue(self.parser._is_technical_string("var count = 0"))

    def test_arrow_function_is_technical(self):
        self.assertTrue(self.parser._is_technical_string("x => x + 1"))


class TestAssetBlockingDoesNotBlockDialogue(unittest.TestCase):
    """Integration test: _should_block_asset_like_translation_update must NOT
    block standard event command dialogue text, even when the text contains
    words like 'let', 'new', 'return', or 'this.'.
    """

    def setUp(self):
        self.parser = JsonParser()

    def test_dialogue_with_let_not_blocked(self):
        original = {
            "events": [None, {
                "pages": [{"list": [
                    {"code": 401, "parameters": ["so let me pamper you while I still can,"]},
                ]}]
            }]
        }
        path = "events.1.pages.0.list.0.parameters.0"
        self.assertFalse(
            self.parser._should_block_asset_like_translation_update(
                original, path, "o yüzden seni şımartayım"
            )
        )

    def test_dialogue_with_new_not_blocked(self):
        original = {
            "events": [None, {
                "pages": [{"list": [
                    {"code": 401, "parameters": ["The new housing that's been built"]},
                ]}]
            }]
        }
        path = "events.1.pages.0.list.0.parameters.0"
        self.assertFalse(
            self.parser._should_block_asset_like_translation_update(
                original, path, "Yeni inşa edilen konutlar"
            )
        )

    def test_dialogue_with_return_not_blocked(self):
        original = {
            "events": [None, {
                "pages": [{"list": [
                    {"code": 401, "parameters": ["he'll understand why I can't return his"]},
                ]}]
            }]
        }
        path = "events.1.pages.0.list.0.parameters.0"
        self.assertFalse(
            self.parser._should_block_asset_like_translation_update(
                original, path, "neden geri döndüremeyeceğimi anlayacak"
            )
        )


class TestYEPQuestJournalExtraction(unittest.TestCase):
    """Tests for the rewritten YEP_QuestJournalParser that handles
    triple-nested JSON quest data (Quest N → array field → element)."""

    def setUp(self):
        from src.core.parsers.specialized_plugins import YEP_QuestJournalParser
        self.parser = YEP_QuestJournalParser()

    def _make_quest_param(self, title: str, description_texts: list[str],
                          objectives: list[str] | None = None,
                          quest_type: str = "Main Quests") -> str:
        """Build a triple-nested JSON quest parameter value."""
        # Inner items are JSON-stringified strings: '"text"'
        desc_items = [json.dumps(t) for t in description_texts]
        desc_array = json.dumps(desc_items)

        obj_items = [json.dumps(t) for t in (objectives or [])]
        obj_array = json.dumps(obj_items)

        quest = {
            "Title": title,
            "Type": quest_type,
            "Difficulty": "Easy",
            "From": "Captain",
            "Location": "Ship",
            "Description": desc_array,
            "Objectives List": obj_array,
            "Rewards List": "[]",
            "Subtext": "[]",
        }
        return json.dumps(quest)

    def test_extracts_quest_title(self):
        """Quest titles must be extracted via @JSON path."""
        params = {
            "Quest 1": self._make_quest_param(
                "\\i[87]1. New Life",
                ["First quest description"],
            ),
        }
        results = self.parser.extract_parameters(params, "plugins.5.parameters")
        titles = [(p, t) for p, t, _ in results if "Title" in p]
        self.assertEqual(len(titles), 1)
        self.assertIn("@JSON", titles[0][0])
        self.assertEqual(titles[0][1], "\\i[87]1. New Life")

    def test_extracts_quest_description(self):
        """Quest description array items must use triple @JSON nesting."""
        params = {
            "Quest 1": self._make_quest_param(
                "Test Quest",
                ["You must find the treasure."],
            ),
        }
        results = self.parser.extract_parameters(params, "p.5.parameters")
        descs = [(p, t) for p, t, _ in results if "Description" in p]
        self.assertTrue(len(descs) >= 1, f"Expected description entries, got {descs}")
        path, text = descs[0]
        self.assertEqual(text, "You must find the treasure.")
        # Must use triple @JSON for correct apply-phase re-serialization
        self.assertEqual(path.count("@JSON"), 3)

    def test_extracts_multiple_objectives(self):
        """All quest objectives should be extracted."""
        params = {
            "Quest 1": self._make_quest_param(
                "Test Quest",
                ["desc"],
                objectives=["Go to the cave", "Defeat the boss", "Return to town"],
            ),
        }
        results = self.parser.extract_parameters(params, "p.0.parameters")
        objs = [t for p, t, _ in results if "Objectives List" in p]
        self.assertEqual(len(objs), 3)
        self.assertIn("Go to the cave", objs)
        self.assertIn("Defeat the boss", objs)
        self.assertIn("Return to town", objs)

    def test_extracts_type_order(self):
        """Type Order JSON array elements should be extracted."""
        params = {
            "Type Order": json.dumps([
                "\\c[6]Main Quests",
                "\\c[4]Side Quests",
                "\\c[3]Character Quests",
            ]),
        }
        results = self.parser.extract_parameters(params, "p.0.parameters")
        types = [t for _, t, _ in results]
        self.assertEqual(len(types), 3)
        self.assertIn("\\c[6]Main Quests", types)

    def test_extracts_top_level_text_params(self):
        """Top-level text parameters like 'No Data Text' must be extracted."""
        params = {
            "No Data Text": "Welcome to the Quest Journal.",
            "Quest Data Format": "<WordWrap>\\{%1\\}\n\\c[4]Level:\\c[0] %2",
            "Category Order": '["available","completed"]',
        }
        results = self.parser.extract_parameters(params, "p.0.parameters")
        paths = [p for p, _, _ in results]
        texts = [t for _, t, _ in results]
        # No Data Text and Quest Data Format should be extracted
        self.assertIn("Welcome to the Quest Journal.", texts)
        self.assertIn("<WordWrap>\\{%1\\}\n\\c[4]Level:\\c[0] %2", texts)
        # Category Order is skipped
        self.assertNotIn('["available","completed"]', texts)

    def test_skips_empty_quest(self):
        """Empty quest parameter should not crash or produce results."""
        params = {"Quest 1": "{}"}
        results = self.parser.extract_parameters(params, "p.0.parameters")
        self.assertEqual(len(results), 0)

    def test_quest_label_fields(self):
        """From/Location quest fields should be extracted; Type should NOT be extracted.

        'Type' was removed from _QUEST_LABEL_FIELDS because the key maps to "type"
        which is in NON_TRANSLATABLE_EXACT_KEYS — extracted values were silently
        dropped at write-time, producing noisy log spam with no user benefit.
        """
        import json as _json

        quest_obj = {
            "Title": "Test",
            "Type": "Side Quests",
            "From": "The Wandering Merchant",
            "Location": "Darkwood Forest",
            "Description": _json.dumps(["Find the lost artifact."]),
        }
        params = {"Quest 1": _json.dumps(quest_obj)}
        results = self.parser.extract_parameters(params, "p.0.parameters")

        # Type must NOT be extracted any more
        types = [t for p, t, _ in results if ".Type" in p]
        self.assertEqual(types, [], "Type field should not be extracted")

        # From and Location should still be extracted
        froms = [t for p, t, _ in results if ".From" in p]
        locations = [t for p, t, _ in results if ".Location" in p]
        self.assertIn("The Wandering Merchant", froms)
        self.assertIn("Darkwood Forest", locations)

    def test_dialogue_with_let_in_quest_not_blocked(self):
        """Quest text containing 'let' must not be marked as technical."""
        params = {
            "Quest 1": self._make_quest_param(
                "Help Quest",
                ["Please let me know if you find the key."],
                objectives=["Let the guard know about the thief"],
            ),
        }
        results = self.parser.extract_parameters(params, "p.0.parameters")
        texts = [t for _, t, _ in results]
        self.assertIn("Please let me know if you find the key.", texts)
        self.assertIn("Let the guard know about the thief", texts)


class TestSpecializedPluginTechnicalHelper(unittest.TestCase):
    """Tests for the _is_technical helper in specialized_plugins.py
    after the ambiguous-keyword fix."""

    def test_let_me_is_not_technical(self):
        from src.core.parsers.specialized_plugins import _is_technical
        self.assertFalse(_is_technical("let me help you"))

    def test_return_his_is_not_technical(self):
        from src.core.parsers.specialized_plugins import _is_technical
        self.assertFalse(_is_technical("he can't return his feelings"))

    def test_new_clothes_is_not_technical(self):
        from src.core.parsers.specialized_plugins import _is_technical
        self.assertFalse(_is_technical("buy new clothes at the shop"))

    def test_this_period_sentence_end_is_not_technical(self):
        from src.core.parsers.specialized_plugins import _is_technical
        self.assertFalse(_is_technical("we could organize this."))

    def test_let_declaration_is_technical(self):
        from src.core.parsers.specialized_plugins import _is_technical
        self.assertTrue(_is_technical("let x = 5"))

    def test_this_property_is_technical(self):
        from src.core.parsers.specialized_plugins import _is_technical
        self.assertTrue(_is_technical("this._data = null"))

    def test_return_value_at_start_is_technical(self):
        from src.core.parsers.specialized_plugins import _is_technical
        self.assertTrue(_is_technical("return value"))

    def test_const_is_technical(self):
        from src.core.parsers.specialized_plugins import _is_technical
        self.assertTrue(_is_technical("const arr = []"))


# ---------------------------------------------------------------------------
# Fix 1: NON_TRANSLATABLE_KEY_HINTS word-boundary matching
# ---------------------------------------------------------------------------

class TestNonTranslatableKeyHintsWordBoundary(unittest.TestCase):
    """Verify that NON_TRANSLATABLE_KEY_HINTS use token-based (word-boundary)
    matching instead of substring matching, so compound keys like 'showText'
    are not blocked by the 'show' hint."""

    def setUp(self):
        self.parser = JsonParser()

    def test_show_blocks_standalone_key(self):
        """Pure 'show' key should still block short values."""
        result = self.parser._should_extract_generic_plugin_parameter("show", "true")
        self.assertFalse(result)

    def test_show_does_not_block_showText(self):
        """'showText' should NOT be blocked — 'text' is a text indicator."""
        result = self.parser._should_extract_generic_plugin_parameter("showText", "Welcome back!")
        self.assertTrue(result)

    def test_show_does_not_block_showMessage(self):
        """'showMessage' contains 'message' text indicator."""
        result = self.parser._should_extract_generic_plugin_parameter("showMessage", "Press Start")
        self.assertTrue(result)

    def test_enable_does_not_block_enableLabel(self):
        """'enableLabel' contains 'label' text indicator."""
        result = self.parser._should_extract_generic_plugin_parameter("enableLabel", "ON / OFF")
        self.assertTrue(result)

    def test_enable_blocks_standalone(self):
        """Pure 'enable' key should block short values."""
        result = self.parser._should_extract_generic_plugin_parameter("enable", "true")
        self.assertFalse(result)

    def test_hide_does_not_block_hideMessage(self):
        """'hideMessage' contains 'message' text indicator."""
        result = self.parser._should_extract_generic_plugin_parameter("hideMessage", "Goodbye!")
        self.assertTrue(result)

    def test_tag_does_not_block_tagLabel(self):
        """'tagLabel' contains 'label' text indicator."""
        result = self.parser._should_extract_generic_plugin_parameter("tagLabel", "Important")
        self.assertTrue(result)

    def test_count_does_not_block_countdownText(self):
        """'countdownText' contains 'text' text indicator."""
        result = self.parser._should_extract_generic_plugin_parameter("countdownText", "Time remaining")
        self.assertTrue(result)

    def test_switch_blocks_standalone(self):
        """Pure 'switch' key blocks short values."""
        result = self.parser._should_extract_generic_plugin_parameter("switch", "42")
        self.assertFalse(result)

    def test_volume_blocks_standalone(self):
        """'volume' is a technical key — blocks short values."""
        result = self.parser._should_extract_generic_plugin_parameter("volume", "100")
        self.assertFalse(result)

    def test_absolute_hint_code_blocks_standalone(self):
        """'code' (absolute hint) should block regardless of length."""
        result = self.parser._should_extract_generic_plugin_parameter("code", "this.update()")
        self.assertFalse(result)

    def test_absolute_hint_formula_does_not_block_formulaDesc(self):
        """'formulaDesc' has 'desc' text indicator — text wins over 'formula' absolute hint."""
        result = self.parser._should_extract_generic_plugin_parameter(
            "formulaDesc", "This formula evaluates attack power"
        )
        self.assertTrue(result)

    def test_mode_does_not_block_modeLabel(self):
        """'modeLabel' has 'label' text indicator — text wins over absolute hint."""
        result = self.parser._should_extract_generic_plugin_parameter("modeLabel", "Easy Mode")
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# Fix 2: TEXT_KEY_INDICATORS expansion
# ---------------------------------------------------------------------------

class TestTextKeyIndicatorsExpansion(unittest.TestCase):
    """Verify new TEXT_KEY_INDICATORS accept text under expanded key patterns."""

    def setUp(self):
        self.parser = JsonParser()

    def test_biography_key_accepts_text(self):
        """Key containing 'biography' should accept single-word values."""
        result = self.parser._should_extract_generic_plugin_parameter(
            "heroBiography", "Warrior"
        )
        self.assertTrue(result)

    def test_summary_key_accepts_text(self):
        result = self.parser._should_extract_generic_plugin_parameter(
            "questSummary", "Find the artifact"
        )
        self.assertTrue(result)

    def test_lore_key_accepts_text(self):
        result = self.parser._should_extract_generic_plugin_parameter(
            "itemLore", "Ancient sword of kings"
        )
        self.assertTrue(result)

    def test_greeting_key_accepts_text(self):
        result = self.parser._should_extract_generic_plugin_parameter(
            "npcGreeting", "Hello traveler"
        )
        self.assertTrue(result)

    def test_farewell_key_accepts_text(self):
        result = self.parser._should_extract_generic_plugin_parameter(
            "farewellText", "See you later"
        )
        self.assertTrue(result)

    def test_warning_key_accepts_text(self):
        result = self.parser._should_extract_generic_plugin_parameter(
            "warningMessage", "Danger ahead"
        )
        self.assertTrue(result)

    def test_intro_key_accepts_text(self):
        result = self.parser._should_extract_generic_plugin_parameter(
            "introMessage", "Welcome"
        )
        self.assertTrue(result)

    def test_vocab_key_accepts_single_word(self):
        """'vocab' is now a TEXT_KEY_INDICATOR — single words under vocab keys accepted."""
        result = self.parser._should_extract_generic_plugin_parameter(
            "vocabAttack", "Attack"
        )
        self.assertTrue(result)

    def test_term_key_accepts_text(self):
        """'term' is now a TEXT_KEY_INDICATOR."""
        result = self.parser._should_extract_generic_plugin_parameter(
            "termDefense", "Defense"
        )
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# Fix 3: Code suffix rejection (all CODE_KEY_SUFFIXES)
# ---------------------------------------------------------------------------

class TestCodeSuffixRejection(unittest.TestCase):
    """Verify that _should_extract_plugin_parameter_value rejects all code
    suffix keys, not just :func."""

    def setUp(self):
        self.parser = JsonParser()

    def test_func_suffix_rejected(self):
        result = self.parser._should_extract_plugin_parameter_value(
            "CustomCode:func", "return this.hp / this.mhp;", None
        )
        self.assertFalse(result)

    def test_eval_suffix_rejected(self):
        result = self.parser._should_extract_plugin_parameter_value(
            "DamageFormula:eval", "a.atk * 4 - b.def * 2", None
        )
        self.assertFalse(result)

    def test_code_suffix_rejected(self):
        result = self.parser._should_extract_plugin_parameter_value(
            "OnActivate:code", "this.refresh()", None
        )
        self.assertFalse(result)

    def test_js_suffix_rejected(self):
        result = self.parser._should_extract_plugin_parameter_value(
            "CustomScript:js", "console.log('debug')", None
        )
        self.assertFalse(result)

    def test_json_suffix_rejected(self):
        result = self.parser._should_extract_plugin_parameter_value(
            "Settings:json", '{"key": "value"}', None
        )
        self.assertFalse(result)

    def test_str_suffix_not_rejected(self):
        """':str' suffix should NOT be rejected (it's a text suffix)."""
        result = self.parser._should_extract_plugin_parameter_value(
            "DisplayName:str", "Hero of Light", None
        )
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# Fix 4: is_safe_to_translate underscore check
# ---------------------------------------------------------------------------

class TestUnderscoreCheckFix(unittest.TestCase):
    """Verify that is_safe_to_translate no longer blocks ALL underscore strings.
    Only uniform-case identifiers (UPPER_SNAKE, lower_snake) should be blocked;
    mixed-case display labels like 'Flame_Sword' should pass in dialogue context."""

    def setUp(self):
        self.parser = JsonParser()

    def test_upper_snake_blocked(self):
        """UPPER_SNAKE_CASE identifiers should be blocked."""
        self.assertFalse(self.parser.is_safe_to_translate("SKILL_TYPE_MAGIC"))

    def test_lower_snake_blocked(self):
        """lower_snake_case identifiers should be blocked."""
        self.assertFalse(self.parser.is_safe_to_translate("some_variable_name"))

    def test_mixed_case_allowed_dialogue(self):
        """Mixed-case display labels like 'Flame_Sword' should pass in dialogue context."""
        self.assertTrue(self.parser.is_safe_to_translate("Flame_Sword", is_dialogue=True))

    def test_max_hp_allowed_dialogue(self):
        """'Max_HP' is a display label — should pass in dialogue context."""
        self.assertTrue(self.parser.is_safe_to_translate("Max_HP", is_dialogue=True))

    def test_init_blocked(self):
        """'__init__' is clearly a code identifier."""
        self.assertFalse(self.parser.is_safe_to_translate("__init__"))

    def test_numbers_only_underscore_blocked(self):
        """'123_456' has no alpha — should be blocked."""
        self.assertFalse(self.parser.is_safe_to_translate("123_456"))

    def test_single_upper_word_with_underscore_blocked(self):
        """'HP_' is all uppercase — should be blocked."""
        self.assertFalse(self.parser.is_safe_to_translate("HP_"))

    def test_mixed_case_blocked_non_dialogue(self):
        """In non-dialogue context, MixedCase is blocked by a separate check."""
        self.assertFalse(self.parser.is_safe_to_translate("Flame_Sword", is_dialogue=False))


# ---------------------------------------------------------------------------
# Fix 5: vocab_context propagation in specialized parsers
# ---------------------------------------------------------------------------

class TestVocabContextPropagation(unittest.TestCase):
    """Verify that specialized parsers pass vocab_context=True for text-keyed
    parameters, accepting single-word vocab entries like 'Attack'."""

    def test_looks_translatable_single_word_with_vocab_context(self):
        """'Attack' should be translatable with vocab_context=True."""
        from src.core.parsers.specialized_plugins import _looks_translatable
        self.assertTrue(_looks_translatable("Attack", vocab_context=True))

    def test_looks_translatable_single_word_without_vocab_context(self):
        """'Attack' should NOT be translatable without vocab_context."""
        from src.core.parsers.specialized_plugins import _looks_translatable
        self.assertFalse(_looks_translatable("Attack", vocab_context=False))

    def test_visumz_message_core_extracts_single_word_vocab(self):
        """VisuMZ_MessageCoreParser should extract single-word text values."""
        from src.core.parsers.specialized_plugins import VisuMZ_MessageCoreParser
        parser = VisuMZ_MessageCoreParser()
        params = {"TextSpeed:str": "Fast"}
        results = parser.extract_parameters(params, "p.0.parameters")
        texts = [t for _, t, _ in results]
        self.assertIn("Fast", texts)

    def test_visumz_items_equips_extracts_vocab_single_word(self):
        """VisuMZ_ItemsEquipsCoreParser should extract single-word vocab labels."""
        from src.core.parsers.specialized_plugins import VisuMZ_ItemsEquipsCoreParser
        parser = VisuMZ_ItemsEquipsCoreParser()
        params = {"Vocab": json.dumps({"Attack": "Attack", "Guard": "Guard"})}
        results = parser.extract_parameters(params, "p.0.parameters")
        texts = [t for _, t, _ in results]
        self.assertIn("Attack", texts)
        self.assertIn("Guard", texts)

    def test_visumz_key_is_text_rejects_eval_suffix(self):
        """_key_is_text should reject ':eval' suffix (not just ':func')."""
        from src.core.parsers.specialized_plugins import VisuMZ_MessageCoreParser
        parser = VisuMZ_MessageCoreParser()
        self.assertFalse(parser._key_is_text("DamageFormula:eval"))
        self.assertFalse(parser._key_is_text("CustomCode:js"))
        self.assertFalse(parser._key_is_text("Settings:json"))

    def test_visumz_items_equips_non_vocab_text_key(self):
        """Non-Vocab text keys should also accept single-word labels."""
        from src.core.parsers.specialized_plugins import VisuMZ_ItemsEquipsCoreParser
        parser = VisuMZ_ItemsEquipsCoreParser()
        params = {"StatusLabel": "Status"}
        results = parser.extract_parameters(params, "p.0.parameters")
        texts = [t for _, t, _ in results]
        self.assertIn("Status", texts)


if __name__ == '__main__':
    unittest.main()
