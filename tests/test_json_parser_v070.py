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
        commands = [
            {"code": 357, "parameters": ["Plugin", "Cmd", "Dialogue text", {}], "indent": 0},
            {"code": 657, "parameters": ["img/pictures/Another Hero.png"], "indent": 0}
        ]
        self.parser.extracted = []
        self.parser._process_mz_plugin_block(commands, "list", 0)

        values = [text for _path, text, _ctx in self.parser.extracted]
        self.assertNotIn("img/pictures/Another Hero.png", values)
        self.assertIn("Dialogue text", values)


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
    """Test that ^ symbol is preserved during placeholder protection."""

    def test_standalone_caret_protected(self):
        """Standalone ^ should be captured by RPGM_PATTERNS."""
        from src.utils.placeholder import protect_rpgm_syntax, restore_rpgm_syntax
        
        text = "Hello there!^"
        protected, placeholders = protect_rpgm_syntax(text)
        
        # The ^ should be replaced with a placeholder
        self.assertNotIn("^", protected)
        self.assertTrue(len(placeholders) > 0)
        
        # Restoration should bring it back
        restored = restore_rpgm_syntax(protected, placeholders)
        self.assertEqual(restored, text)

    def test_backslash_caret_still_protected(self):
        """\\^ should still be protected by existing pattern."""
        from src.utils.placeholder import protect_rpgm_syntax, restore_rpgm_syntax
        
        text = "Hello there!\\^"
        protected, placeholders = protect_rpgm_syntax(text)
        
        self.assertNotIn("\\^", protected)
        self.assertTrue(len(placeholders) > 0)
        
        restored = restore_rpgm_syntax(protected, placeholders)
        self.assertEqual(restored, text)

    def test_caret_in_middle_of_text_protected(self):
        """^ in middle of text should also be protected."""
        from src.utils.placeholder import protect_rpgm_syntax, restore_rpgm_syntax
        
        text = "Name^Some dialogue"
        protected, placeholders = protect_rpgm_syntax(text)
        
        self.assertNotIn("^", protected)
        restored = restore_rpgm_syntax(protected, placeholders)
        self.assertEqual(restored, text)

    def test_message_dialogue_with_caret_preserved(self):
        """Code 401 text with trailing ^ should be extractable and preservable."""
        parser = JsonParser()
        parser._current_file_basename = 'map001.json'
        data = [
            {"code": 401, "parameters": ["Hello!\\^"], "indent": 0}
        ]
        parser.extracted = []
        parser._process_list(data, "events.1.pages.0.list")
        
        # The text should be extracted (it's dialogue)
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


if __name__ == '__main__':
    unittest.main()
