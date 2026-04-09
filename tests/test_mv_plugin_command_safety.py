import json
import os
import tempfile
import unittest

from src.core.parsers.json_parser import JsonParser


class TestMvPluginCommandSafety(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = JsonParser()

    def test_loadbgm_command_is_not_extracted(self) -> None:
        data = [
            {
                "code": 356,
                "parameters": [
                    "LoadBGM innovation-3794 alias=TutorialMusic loopstart=188410 looplength=4586084"
                ],
                "indent": 0,
            }
        ]

        self.parser.extracted = []
        self.parser._process_list(data, "events.1.list")

        self.assertEqual(self.parser.extracted, [])

    def test_mv_plugin_command_extracts_only_quoted_payload(self) -> None:
        data = [
            {
                "code": 356,
                "parameters": ['ShowHint "Welcome to campus" top'],
                "indent": 0,
            }
        ]

        self.parser.extracted = []
        self.parser._process_list(data, "events.1.list")

        self.assertEqual(len(self.parser.extracted), 1)
        path, text, context = self.parser.extracted[0]
        self.assertEqual(path, "events.1.list.0.parameters.0.@MVCMD0")
        self.assertEqual(text, "Welcome to campus")
        self.assertEqual(context, "dialogue_block")

    def test_advload_command_is_not_extracted(self) -> None:
        data = [
            {
                "code": 356,
                "parameters": ["AdvLoad chapter_001"],
                "indent": 0,
            }
        ]

        self.parser.extracted = []
        self.parser._process_list(data, "events.1.list")

        self.assertEqual(self.parser.extracted, [])

    def test_choicepos_command_is_not_extracted(self) -> None:
        data = [
            {
                "code": 356,
                "parameters": ["ChoicePos 404 248"],
                "indent": 0,
            }
        ]

        self.parser.extracted = []
        self.parser._process_list(data, "events.1.list")

        self.assertEqual(self.parser.extracted, [])

    def test_apply_translation_only_updates_quoted_payload(self) -> None:
        data = [
            {
                "code": 356,
                "parameters": ['ShowHint "Welcome to campus" top'],
                "indent": 0,
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Map001.json")
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False)

            result = self.parser.apply_translation(
                file_path,
                {"0.parameters.0.@MVCMD0": "Kampuse hos geldin"},
            )

        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["parameters"][0], 'ShowHint "Kampuse hos geldin" top')


if __name__ == "__main__":
    unittest.main()
