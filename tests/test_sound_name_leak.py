"""
Comprehensive tests for sound effect name extraction leaks.

These tests simulate every code path that could cause RPG Maker
audio filenames (like "Cursor1") to be accidentally extracted for
translation, causing game crashes when the engine tries to load
a translated filename like "İmleç1.ogg".
"""
import json
import os
import tempfile
import unittest

from src.core.parsers.json_parser import JsonParser


def _make_parser() -> JsonParser:
    p = JsonParser.__new__(JsonParser)
    JsonParser.__init__(p)
    return p


def _extract(data: dict | list, filename: str = "map001.json") -> list[tuple]:
    """Helper: write data to temp file and extract via JsonParser."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Minimal asset root so _get_known_asset_identifiers returns empty set
        # (worst-case: no audio folder → asset registry is empty)
        filepath = os.path.join(tmpdir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f)
        parser = _make_parser()
        return parser.extract_text(filepath)


def _extract_with_audio(data: dict | list, filename: str = "map001.json") -> list[tuple]:
    """Helper: extract with a real Cursor1.ogg asset in the audio/se folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create audio/se/Cursor1.ogg so asset registry catches it
        audio_se = os.path.join(tmpdir, "audio", "se")
        os.makedirs(audio_se)
        open(os.path.join(audio_se, "Cursor1.ogg"), "w").close()
        open(os.path.join(audio_se, "Decision1.ogg"), "w").close()
        open(os.path.join(audio_se, "Cancel1.ogg"), "w").close()
        open(os.path.join(audio_se, "Buzzer1.ogg"), "w").close()
        filepath = os.path.join(tmpdir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f)
        parser = _make_parser()
        return parser.extract_text(filepath)


class TestSoundObjectInWalk(unittest.TestCase):
    """_process_dict path — generic _walk via non-structured files."""

    def _get_values(self, entries):
        return [v for _, v, _ in entries]

    def test_full_sound_object_name_not_extracted(self):
        """Classic {name, volume, pitch, pan} — must never be extracted."""
        data = {"customSE": {"name": "Cursor1", "volume": 90, "pitch": 100, "pan": 0}}
        entries = _extract(data, "customconfig.json")
        self.assertNotIn("Cursor1", self._get_values(entries))

    def test_partial_sound_object_name_pitch_only(self):
        """name + pitch only — plugin may omit volume/pan."""
        data = {"customSE": {"name": "Cursor1", "pitch": 100}}
        entries = _extract(data, "customconfig.json")
        self.assertNotIn("Cursor1", self._get_values(entries))

    def test_partial_sound_object_name_volume_only(self):
        """name + volume only — must still be treated as sound object."""
        data = {"customSE": {"name": "Cursor1", "volume": 90}}
        entries = _extract(data, "customconfig.json")
        self.assertNotIn("Cursor1", self._get_values(entries))

    def test_partial_sound_object_name_pan_only(self):
        """name + pan only — least common but still a sound spec."""
        data = {"customSE": {"name": "Cursor1", "pan": 0}}
        entries = _extract(data, "customconfig.json")
        self.assertNotIn("Cursor1", self._get_values(entries))

    def test_sound_list_names_not_extracted(self):
        """Array of sound objects — all names must be skipped."""
        data = {
            "sounds": [
                {"name": "Cursor1", "volume": 90, "pitch": 100, "pan": 0},
                {"name": "Decision1", "volume": 90, "pitch": 100, "pan": 0},
                {"name": "Cancel1", "volume": 90, "pitch": 100, "pan": 0},
            ]
        }
        entries = _extract(data, "customconfig.json")
        values = self._get_values(entries)
        self.assertNotIn("Cursor1", values)
        self.assertNotIn("Decision1", values)
        self.assertNotIn("Cancel1", values)

    def test_normal_name_field_still_extracted(self):
        """Regular name fields (not sound objects) must still be extracted."""
        data = [{"name": "Hero's Journey", "description": "A brave hero."}]
        entries = _extract(data, "actors.json")
        values = self._get_values(entries)
        self.assertIn("Hero's Journey", values)


class TestAssetContextPathHardening(unittest.TestCase):
    """Context-aware guards for asset-like name fields."""

    def _get_values(self, entries):
        return [v for _, v, _ in entries]

    def test_audio_settings_name_not_extracted(self):
        """CamelCase audio context should block extensionless sound names."""
        data = {"audioSettings": {"name": "Town Theme"}}
        entries = _extract(data, "customconfig.json")
        self.assertNotIn("Town Theme", self._get_values(entries))

    def test_battle_bgm_name_not_extracted_without_sound_shape(self):
        """Asset context path should block even when volume/pitch/pan keys are absent."""
        data = {"battleBgm": {"name": "Battle1"}}
        entries = _extract(data, "customconfig.json")
        self.assertNotIn("Battle1", self._get_values(entries))

    def test_non_asset_context_name_still_extracted(self):
        """Unrelated name fields must remain translatable."""
        data = {"npcData": {"name": "Village Elder"}}
        entries = _extract(data, "customconfig.json")
        self.assertIn("Village Elder", self._get_values(entries))

    def test_legacy_database_name_asset_extension_blocked(self):
        """Legacy database name extraction must still reject file-like asset names."""
        data = [{"name": "Cursor1.ogg", "description": "Playable text"}]
        entries = _extract(data, "items.json")
        values = self._get_values(entries)
        self.assertNotIn("Cursor1.ogg", values)
        self.assertIn("Playable text", values)

    def test_percent_encoded_asset_path_is_not_extracted(self):
        """Percent-encoded asset paths must be treated as technical filenames."""
        data = {"graphic": "img/system/sava%C5%9FAttackInfoArrow2.png?ver=12#sprite", "label": "Attack Info"}
        entries = _extract(data, "customconfig.json")
        values = self._get_values(entries)
        self.assertNotIn("img/system/sava%C5%9FAttackInfoArrow2.png?ver=12#sprite", values)
        self.assertIn("Attack Info", values)

    def test_double_encoded_asset_path_is_not_extracted(self):
        """Double-encoded asset paths must still be treated as technical filenames."""
        data = {"graphic": "img\\system\\sava%25C5%259FAttackInfoArrow2.png", "label": "Attack Info"}
        entries = _extract(data, "customconfig.json")
        values = self._get_values(entries)
        self.assertNotIn("img\\system\\sava%25C5%259FAttackInfoArrow2.png", values)
        self.assertIn("Attack Info", values)


class TestSoundObjectInMZPluginArgs(unittest.TestCase):
    """Event command 357 args path — MZ plugin command with SE in args."""

    def _get_values(self, entries):
        return [v for _, v, _ in entries]

    def _make_map_with_357_se(self, se_value) -> dict:
        """Map file with a code-357 MZ plugin command that has an SE arg."""
        return {
            "events": [
                {
                    "pages": [
                        {
                            "list": [
                                {
                                    "code": 357,
                                    "parameters": [
                                        "SomePlugin",
                                        "PlaySE",
                                        "",
                                        {"se": se_value},
                                    ],
                                },
                                {"code": 0, "parameters": []},
                            ]
                        }
                    ]
                }
            ]
        }

    def test_357_args_dict_se_string_not_extracted(self):
        """SE as a plain string in args dict — key 'se' must be skipped."""
        data = self._make_map_with_357_se("Cursor1")
        entries = _extract(data, "map001.json")
        self.assertNotIn("Cursor1", self._get_values(entries))

    def test_357_args_dict_se_nested_json_name_not_extracted(self):
        """SE as nested JSON string in args — name must not be extracted."""
        se_json = json.dumps({"name": "Cursor1", "volume": 90, "pitch": 100, "pan": 0})
        data = self._make_map_with_357_se(se_json)
        entries = _extract(data, "map001.json")
        self.assertNotIn("Cursor1", self._get_values(entries))

    def test_357_args_dict_se_partial_nested_json_not_extracted(self):
        """SE as partial nested JSON (no pan) — still must not be extracted."""
        se_json = json.dumps({"name": "Cursor1", "volume": 90})
        data = self._make_map_with_357_se(se_json)
        entries = _extract(data, "map001.json")
        self.assertNotIn("Cursor1", self._get_values(entries))

    def test_357_text_arg_still_extracted(self):
        """Real translatable text in 357 args dict must still be extracted.

        In RPG Maker MZ, plugin commands carry player-visible text in the args
        dict (params[3]), not in params[2] (which is the editor's command-label).
        The args dict key 'text' has TEXT_HINTS membership so it is classified as
        a 'text' surface and extracted correctly.
        """
        data = {
            "events": [
                {
                    "pages": [
                        {
                            "list": [
                                {
                                    "code": 357,
                                    "parameters": [
                                        "TextPlugin",
                                        "ShowText",
                                        "Show Text",  # editor label — NOT extracted
                                        {"text": "Welcome to the dungeon!"},
                                    ],
                                },
                                {"code": 0, "parameters": []},
                            ]
                        }
                    ]
                }
            ]
        }
        entries = _extract(data, "map001.json")
        self.assertIn("Welcome to the dungeon!", self._get_values(entries))
        self.assertNotIn("Show Text", self._get_values(entries))


class TestSoundObjectInPluginsJs(unittest.TestCase):
    """plugins.js path — plugin parameters containing SE sound specs."""

    def _get_values(self, entries):
        return [v for _, v, _ in entries]

    def _make_plugins_js(self, parameters: dict, tmpdir: str) -> str:
        plugin = [{"name": "TestPlugin", "status": True, "parameters": parameters}]
        js_content = f"var $plugins =\n{json.dumps(plugin, ensure_ascii=False)}\n;"
        path = os.path.join(tmpdir, "plugins.js")
        with open(path, "w", encoding="utf-8") as f:
            f.write(js_content)
        return path

    def test_plugins_js_se_string_key_not_extracted(self):
        """Plugin param key='se' with plain filename — must be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            params = {"se": "Cursor1"}
            path = self._make_plugins_js(params, tmpdir)
            parser = _make_parser()
            entries = parser.extract_text(path)
            self.assertNotIn("Cursor1", self._get_values(entries))

    def test_plugins_js_se_nested_json_not_extracted(self):
        """Plugin param 'se' with nested sound JSON — name must be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            se_json = json.dumps({"name": "Cursor1", "volume": 90, "pitch": 100, "pan": 0})
            params = {"se": se_json}
            path = self._make_plugins_js(params, tmpdir)
            parser = _make_parser()
            entries = parser.extract_text(path)
            self.assertNotIn("Cursor1", self._get_values(entries))

    def test_plugins_js_se_partial_nested_json_not_extracted(self):
        """Plugin param 'se' with partial nested JSON (no pitch/pan)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            se_json = json.dumps({"name": "Cursor1", "volume": 90})
            params = {"se": se_json}
            path = self._make_plugins_js(params, tmpdir)
            parser = _make_parser()
            entries = parser.extract_text(path)
            self.assertNotIn("Cursor1", self._get_values(entries))

    def test_plugins_js_se_array_nested_jsons_not_extracted(self):
        """Plugin param 'se' with array of nested sound JSONs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sounds = [
                json.dumps({"name": "Cursor1", "volume": 90, "pitch": 100, "pan": 0}),
                json.dumps({"name": "Decision1", "volume": 90, "pitch": 100, "pan": 0}),
            ]
            params = {"se": json.dumps(sounds)}
            path = self._make_plugins_js(params, tmpdir)
            parser = _make_parser()
            entries = parser.extract_text(path)
            values = self._get_values(entries)
            self.assertNotIn("Cursor1", values)
            self.assertNotIn("Decision1", values)

    def test_plugins_js_soundname_key_not_extracted(self):
        """Plugin param key='soundName' with filename — asset-like name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            params = {"soundName": "Cursor1"}
            path = self._make_plugins_js(params, tmpdir)
            parser = _make_parser()
            entries = parser.extract_text(path)
            self.assertNotIn("Cursor1", self._get_values(entries))

    def test_plugins_js_default_talk_se_csv_not_extracted(self):
        """SE CSV format in spaced key names must be skipped (GALV-like)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            params = {
                "Default Talk SE": "Cursor1,80,150",
                "Default Confirm SE": "Cursor1,0,150",
            }
            path = self._make_plugins_js(params, tmpdir)
            parser = _make_parser()
            entries = parser.extract_text(path)
            values = self._get_values(entries)
            self.assertNotIn("Cursor1,80,150", values)
            self.assertNotIn("Cursor1,0,150", values)

    def test_plugins_js_text_param_still_extracted(self):
        """A real text parameter must still be extracted alongside."""
        with tempfile.TemporaryDirectory() as tmpdir:
            params = {
                "se": json.dumps({"name": "Cursor1", "volume": 90, "pitch": 100, "pan": 0}),
                "messageText": "Press any key to continue!",
            }
            path = self._make_plugins_js(params, tmpdir)
            parser = _make_parser()
            entries = parser.extract_text(path)
            values = self._get_values(entries)
            self.assertNotIn("Cursor1", values)
            self.assertIn("Press any key to continue!", values)


class TestSoundObjectInSystemJson(unittest.TestCase):
    """system.json structured path — sounds array must never be touched."""

    def _get_values(self, entries):
        return [v for _, v, _ in entries]

    def test_system_json_sounds_array_names_not_extracted(self):
        """system.json sounds[] entries must never be extracted."""
        data = {
            "gameTitle": "My Game",
            "currencyUnit": "G",
            "sounds": [
                {"name": "Cursor1", "volume": 90, "pitch": 100, "pan": 0},
                {"name": "Decision1", "volume": 90, "pitch": 100, "pan": 0},
                {"name": "Cancel1", "volume": 90, "pitch": 100, "pan": 0},
                {"name": "Buzzer1", "volume": 90, "pitch": 100, "pan": 0},
                {"name": "Equip1", "volume": 90, "pitch": 100, "pan": 0},
                {"name": "Save1", "volume": 90, "pitch": 100, "pan": 0},
                {"name": "Load1", "volume": 90, "pitch": 100, "pan": 0},
                {"name": "BattleStart1", "volume": 90, "pitch": 100, "pan": 0},
                {"name": "Escape1", "volume": 90, "pitch": 100, "pan": 0},
            ],
            "bgm": {"name": "Field1", "volume": 90, "pitch": 100, "pan": 0},
            "bgs": {"name": "", "volume": 90, "pitch": 100, "pan": 0},
            "battleBgm": {"name": "Battle1", "volume": 90, "pitch": 100, "pan": 0},
            "defeatMe": {"name": "Defeat1", "volume": 90, "pitch": 100, "pan": 0},
            "victoryMe": {"name": "Victory1", "volume": 90, "pitch": 100, "pan": 0},
            "terms": {
                "basic": ["Level", "Lv", "HP", "HP", "MP", "MP", "TP", "TP", "EXP", "EXP"],
                "commands": ["Fight", "Escape", "Attack", "Guard", "Item", "Skill"],
                "params": ["Max HP", "Max MP", "Attack", "Defense", "M.Attack", "M.Defense", "Agility", "Luck"],
                "messages": {},
            },
        }
        entries = _extract(data, "system.json")
        values = self._get_values(entries)
        # Sound names must not be there
        for name in ["Cursor1", "Decision1", "Cancel1", "Buzzer1", "Equip1",
                     "Save1", "Load1", "BattleStart1", "Escape1",
                     "Field1", "Battle1", "Defeat1", "Victory1"]:
            self.assertNotIn(name, values, f"Sound name '{name}' leaked into extraction!")
        # But game title and terms must be there
        self.assertIn("My Game", values)


class TestSoundObjectInCommonEvents(unittest.TestCase):
    """commonevents.json — Play SE (code 250) must not extract name."""

    def _get_values(self, entries):
        return [v for _, v, _ in entries]

    def test_code_250_se_name_not_extracted(self):
        """Play SE command (code 250) — audio filename must not be extracted."""
        data = [
            None,
            {
                "id": 1,
                "name": "EntranceSound",  # This event name should be skipped (commonevents)
                "list": [
                    {
                        "code": 250,
                        "parameters": [
                            {"name": "Cursor1", "volume": 90, "pitch": 100, "pan": 0}
                        ],
                    },
                    {"code": 0, "parameters": []},
                ],
            },
        ]
        entries = _extract(data, "commonevents.json")
        values = self._get_values(entries)
        self.assertNotIn("Cursor1", values)
        self.assertNotIn("EntranceSound", values)  # Common event name must be skipped

    def test_code_241_bgm_name_not_extracted(self):
        """Play BGM (code 241) — audio filename must not be extracted."""
        data = [
            None,
            {
                "id": 1,
                "name": "StartBGM",
                "list": [
                    {
                        "code": 241,
                        "parameters": [
                            {"name": "Field1", "volume": 90, "pitch": 100, "pan": 0}
                        ],
                    },
                    {"code": 0, "parameters": []},
                ],
            },
        ]
        entries = _extract(data, "commonevents.json")
        values = self._get_values(entries)
        self.assertNotIn("Field1", values)


class TestSoundNameWithAssetRegistry(unittest.TestCase):
    """Test that asset registry correctly intercepts known sound names."""

    def _get_values(self, entries):
        return [v for _, v, _ in entries]

    def test_known_audio_basename_blocked_by_registry(self):
        """Even if other guards miss it, asset registry catches it."""
        data = {"someKey": "Cursor1"}
        entries = _extract_with_audio(data, "customconfig.json")
        values = self._get_values(entries)
        self.assertNotIn("Cursor1", values)


class TestSoundObjectHelperMethod(unittest.TestCase):
    """Unit tests for the _is_sound_like_object static method."""

    def test_full_sound_object(self):
        parser = _make_parser()
        self.assertTrue(parser._is_sound_like_object(
            {"name": "Cursor1", "volume": 90, "pitch": 100, "pan": 0}
        ))

    def test_partial_volume_only(self):
        parser = _make_parser()
        self.assertTrue(parser._is_sound_like_object(
            {"name": "Cursor1", "volume": 90}
        ))

    def test_partial_pitch_only(self):
        parser = _make_parser()
        self.assertTrue(parser._is_sound_like_object(
            {"name": "Cursor1", "pitch": 100}
        ))

    def test_partial_pan_only(self):
        parser = _make_parser()
        self.assertTrue(parser._is_sound_like_object(
            {"name": "Cursor1", "pan": 0}
        ))

    def test_name_only_not_sound(self):
        """name alone is not enough — could be any dict with a name."""
        parser = _make_parser()
        self.assertFalse(parser._is_sound_like_object({"name": "Hero"}))

    def test_no_name_not_sound(self):
        parser = _make_parser()
        self.assertFalse(parser._is_sound_like_object(
            {"volume": 90, "pitch": 100, "pan": 0}
        ))

    def test_non_dict_not_sound(self):
        parser = _make_parser()
        self.assertFalse(parser._is_sound_like_object("Cursor1"))
        self.assertFalse(parser._is_sound_like_object(None))
        self.assertFalse(parser._is_sound_like_object([]))

    def test_empty_dict_not_sound(self):
        parser = _make_parser()
        self.assertFalse(parser._is_sound_like_object({}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
