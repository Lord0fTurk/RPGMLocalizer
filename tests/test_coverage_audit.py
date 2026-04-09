import json
import os
import tempfile
import unittest
from pathlib import Path

from src.core.parser_factory import get_parser
from src.core.parsers.plain_text_parser import CreditsTextParser
from src.core.translation_pipeline import TranslationPipeline


CREDITS_SAMPLE = r"""Text outside blocks should stay untouched

<block:-1,-1,10,10,offbot,center,Island>
CREDITS

\c[2]Engine
Degica
RPG Maker MV
</block>

<block:999,0,10,10,300,center,Tower1>
THE END
</block>
"""


class TestCoverageAudit(unittest.TestCase):
    def test_credits_parser_extracts_only_block_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            credits_path = os.path.join(tmpdir, "credits.txt")
            with open(credits_path, "w", encoding="utf-8") as handle:
                handle.write(CREDITS_SAMPLE)

            parser = CreditsTextParser()
            extracted = parser.extract_text(credits_path)

        values = [text for _path, text, _tag in extracted]
        self.assertIn("CREDITS", values)
        self.assertIn(r"\c[2]Engine", values)
        self.assertIn("THE END", values)
        self.assertNotIn("Text outside blocks should stay untouched", values)
        self.assertFalse(any(text.startswith("<block:") for text in values))

    def test_credits_parser_apply_translation_preserves_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            credits_path = os.path.join(tmpdir, "credits.txt")
            with open(credits_path, "w", encoding="utf-8") as handle:
                handle.write(CREDITS_SAMPLE)

            parser = CreditsTextParser()
            extracted = parser.extract_text(credits_path)
            paths_by_text = {text: path for path, text, _tag in extracted}

            updated = parser.apply_translation(
                credits_path,
                {
                    paths_by_text["CREDITS"]: "KREDILER",
                    paths_by_text["THE END"]: "SON",
                },
            )

        self.assertIsInstance(updated, str)
        self.assertIn("<block:-1,-1,10,10,offbot,center,Island>", updated)
        self.assertIn("KREDILER", updated)
        self.assertIn("SON", updated)
        self.assertIn("Text outside blocks should stay untouched", updated)

    def test_pipeline_collects_allowlisted_credits_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = self._create_minimal_mv_project(tmpdir)

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            files = pipeline._collect_files(data_dir)

        basenames = {os.path.basename(path).lower() for path in files}
        self.assertIn("credits.txt", basenames)
        self.assertIsInstance(get_parser("credits.txt", {}), CreditsTextParser)

    def test_pipeline_collect_files_skips_non_json_sidecars_before_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = self._create_minimal_mv_project(tmpdir)
            self._write_file(
                os.path.join(data_dir, "Map036lighting.json"),
                "Lighting config placeholder",
            )

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            files = pipeline._collect_files(data_dir)

        basenames = {os.path.basename(path).lower() for path in files}
        self.assertIn("system.json", basenames)
        self.assertNotIn("map036lighting.json", basenames)

    def test_pipeline_collect_files_skips_non_json_locale_sidecars_before_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = self._create_minimal_mv_project(tmpdir)
            locales_dir = os.path.join(tmpdir, "www", "locales")
            os.makedirs(locales_dir, exist_ok=True)
            self._write_file(os.path.join(locales_dir, "strings.json"), '{"menu":{"start":"Start"}}')
            self._write_file(os.path.join(locales_dir, "plugin_sidecar.json"), "not actually json")

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            files = pipeline._collect_files(data_dir)

        basenames = {os.path.basename(path).lower() for path in files}
        self.assertIn("strings.json", basenames)
        self.assertNotIn("plugin_sidecar.json", basenames)

    def test_pipeline_collect_files_skips_binary_json_sidecars_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = self._create_minimal_mv_project(tmpdir)
            sidecar_path = os.path.join(data_dir, "binary_sidecar.json")
            with open(sidecar_path, "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\nnot json")

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            files = pipeline._collect_files(data_dir)

        basenames = {os.path.basename(path).lower() for path in files}
        self.assertIn("system.json", basenames)
        self.assertNotIn("binary_sidecar.json", basenames)

    def test_pipeline_collect_files_skips_backup_json_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = self._create_minimal_mv_project(tmpdir)
            backup_path = os.path.join(data_dir, "Skills_Backup.json")
            with open(backup_path, "w", encoding="utf-8") as handle:
                handle.write('{"broken": true')

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            files = pipeline._collect_files(data_dir)

        basenames = {os.path.basename(path).lower() for path in files}
        self.assertIn("system.json", basenames)
        self.assertNotIn("skills_backup.json", basenames)

    def test_pipeline_collect_files_skips_copy_json_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = self._create_minimal_mv_project(tmpdir)
            copy_path = os.path.join(data_dir, "CommonEvents - Copy (2).json")
            with open(copy_path, "w", encoding="utf-8") as handle:
                handle.write('{"duplicate": true}')

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            files = pipeline._collect_files(data_dir)

        basenames = {os.path.basename(path).lower() for path in files}
        self.assertIn("system.json", basenames)
        self.assertNotIn("commonevents - copy (2).json", basenames)

    def test_pipeline_saves_translated_credits_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = self._create_minimal_mv_project(tmpdir)
            credits_path = os.path.join(data_dir, "credits.txt")

            parser = CreditsTextParser()
            extracted = parser.extract_text(credits_path)
            credit_path = next(path for path, text, _tag in extracted if text == "CREDITS")

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            pipeline._save_translations(
                {
                    credits_path: (parser, extracted),
                },
                {
                    (credits_path, credit_path): "KREDILER",
                },
            )

            with open(credits_path, "r", encoding="utf-8") as handle:
                updated = handle.read()

        self.assertIn("KREDILER", updated)
        self.assertNotIn("\nCREDITS\n", updated)

    def test_pipeline_preserves_crlf_credits_layout_when_saving(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = self._create_minimal_mv_project(tmpdir, newline="\r\n")
            credits_path = os.path.join(data_dir, "credits.txt")

            parser = CreditsTextParser()
            extracted = parser.extract_text(credits_path)
            credit_path = next(path for path, text, _tag in extracted if text == "CREDITS")

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            pipeline._save_translations(
                {
                    credits_path: (parser, extracted),
                },
                {
                    (credits_path, credit_path): "KREDILER",
                },
            )

            raw_bytes = Path(credits_path).read_bytes()

        self.assertNotIn(b"\r\n\r\n\r\n\r\n<block", raw_bytes)
        self.assertEqual(raw_bytes.count(b"\r\n"), CREDITS_SAMPLE.count("\n"))

    def test_coverage_audit_reports_raw_js_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_minimal_mv_project(tmpdir)
            self._write_file(
                os.path.join(tmpdir, "www", "js", "rpg_core.js"),
                'Graphics.printLoadingError("Loading Error", "Failed to load: " + url);\n',
            )
            self._write_file(
                os.path.join(tmpdir, "www", "js", "plugins", "NumbState.js"),
                'Window_BattleLog.prototype.displayNumbState = function() { return "cannot move by the numb!"; };\n',
            )
            self._write_file(
                os.path.join(tmpdir, "www", "js", "libs", "pixi.js"),
                'throw new Error("Vendor library string");\n',
            )

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            report = pipeline.analyze_project_coverage(tmpdir)

        collected_safe = set(report["safe_text_surfaces"]["collected"])
        raw_js_files = {item["path"] for item in report["raw_js_audit"]["files"]}

        self.assertIn("www/data/credits.txt", collected_safe)
        self.assertIn("www/js/rpg_core.js", raw_js_files)
        self.assertIn("www/js/plugins/NumbState.js", raw_js_files)
        self.assertNotIn("www/js/libs/pixi.js", raw_js_files)
        self.assertGreater(report["raw_js_audit"]["candidate_entries"], 0)
        self.assertGreater(sum(report["raw_js_audit"]["engines"].values()), 0)
        self.assertIn("confidence_buckets", report["raw_js_audit"])
        self.assertIn("write_readiness", report["raw_js_audit"])
        self.assertTrue(all("engine" in item for item in report["raw_js_audit"]["files"]))
        self.assertTrue(all("write_readiness" in item for item in report["raw_js_audit"]["files"]))

    def test_coverage_audit_reports_custom_hendrix_and_ts_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "www", "data")
            js_dir = os.path.join(tmpdir, "www", "js")
            scenario_dir = os.path.join(tmpdir, "scenario")
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(js_dir, exist_ok=True)
            os.makedirs(scenario_dir, exist_ok=True)

            with open(os.path.join(data_dir, "System.json"), "w", encoding="utf-8") as handle:
                json.dump({"gameTitle": "Test Game"}, handle)

            with open(os.path.join(js_dir, "plugins.js"), "w", encoding="utf-8") as handle:
                handle.write(
                    'var $plugins = ['
                    '{"name":"Hendrix_Localization","status":true,"parameters":{"Languages":"[]","Default Language":"en"}},'
                    '{"name":"TS_Decode","status":true,"parameters":{"Key":"255"}}'
                    '];\n'
                )

            with open(os.path.join(tmpdir, "game_messages.csv"), "w", encoding="utf-8", newline="") as handle:
                handle.write("\ufeffChange,Excluded,Name,Original,en\n,,,,Hello\n")

            with open(os.path.join(scenario_dir, "001.sl"), "w", encoding="utf-8") as handle:
                handle.write("sample")

            pipeline = TranslationPipeline({"use_cache": False, "backup_enabled": False})
            report = pipeline.analyze_project_coverage(tmpdir)

        detected = report["custom_surfaces"]["detected"]
        self.assertEqual(detected.get("hendrix_csv"), 1)
        self.assertEqual(detected.get("ts_adv_scenarios"), 1)

    def _create_minimal_mv_project(self, project_root: str, newline: str = "\n") -> str:
        data_dir = os.path.join(project_root, "www", "data")
        js_dir = os.path.join(project_root, "www", "js")
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(js_dir, exist_ok=True)

        with open(os.path.join(data_dir, "System.json"), "w", encoding="utf-8") as handle:
            json.dump({"gameTitle": "Test Game"}, handle, ensure_ascii=False)

        with open(os.path.join(data_dir, "credits.txt"), "w", encoding="utf-8", newline="") as handle:
            handle.write(CREDITS_SAMPLE.replace("\n", newline))

        with open(os.path.join(js_dir, "plugins.js"), "w", encoding="utf-8") as handle:
            handle.write("var $plugins = [];\n")

        return data_dir

    def _write_file(self, path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)


if __name__ == "__main__":
    unittest.main()
