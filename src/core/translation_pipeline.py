"""
Translation Pipeline for RPGMLocalizer.
Orchestrates the entire translation workflow including:
- File discovery and parsing
- Text extraction and protection
- Batch translation with caching
- File backup and writing
"""
import os
import shutil
import json
import asyncio
import logging
import re
import time
from collections import Counter
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal as Signal

from .translator import GoogleTranslator, TranslationRequest
from .parser_factory import get_parser
from .parsers.js_ast_extractor import JavaScriptAstAuditExtractor
from .parsers.hendrix_csv_parser import HENDRIX_CSV_FILENAME
from .parsers.plain_text_parser import SUPPORTED_TEXT_FILENAMES
from .parsers.ts_adv_scenario_parser import TS_SCENARIO_EXTENSION
from .glossary import Glossary
from .cache import TranslationCache, get_cache
from .export_import import TranslationExporter, TranslationImporter
from src.utils.backup import BackupManager, get_backup_manager
from .enums import PipelineStage
from src.utils.file_ops import safe_write
from .text_merger import TextMerger
from .constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONCURRENCY,
    DEFAULT_REQUEST_DELAY_MS,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_USE_MULTI_ENDPOINT,
    DEFAULT_ENABLE_LINGVA_FALLBACK
)
from .engine_profiler import EngineProfiler, ProjectProfile


class TranslationPipeline(QObject):
    """
    Main translation pipeline that orchestrates the entire workflow.
    """

    RAW_JS_AUDIT_EXCLUDED_DIRS = {"libs"}
    RAW_JS_AUDIT_EXCLUDED_FILES = {"plugins.js"}
    RAW_JS_AUDIT_TOP_SAMPLE_LIMIT = 8
    IGNORED_DATA_FILE_SUFFIXES = (
        "_backup.json",
        ".backup.json",
        ".bak.json",
    )
    HENDRIX_PLUGIN_NAME = "Hendrix_Localization"
    TS_DECODE_PLUGIN_NAME = "TS_Decode"
    CUSTOM_SURFACE_KEYS = {
        "hendrix_csv": "Hendrix Localization CSV",
        "ts_adv_scenarios": "TS_ADV scenarios",
    }
    
    # Signals for UI updates
    stage_changed = Signal(str, str)     # stage_value, message
    progress_updated = Signal(int, int, str)  # current, total, text
    log_message = Signal(str, str)       # level, message
    finished = Signal(bool, str)         # success, message

    def __init__(self, settings: dict):
        """
        Initialize the pipeline.
        
        Args:
            settings: Dictionary containing:
                - project_path: Path to RPG Maker project
                - target_lang: Target language code (e.g., 'tr')
                - source_lang: Source language code (e.g., 'en', 'auto')
                - glossary_path: Optional path to glossary file
                - use_cache: Whether to use translation cache
                - backup_enabled: Whether to create backups
        """
        super().__init__()
        self.settings = settings
        self.should_stop = False
        
        # Get performance settings (defaults: 20 concurrent, 15 batch for maximum stability)
        concurrency = self.settings.get("concurrent_requests", DEFAULT_CONCURRENCY)
        batch_size = self.settings.get("batch_size", DEFAULT_BATCH_SIZE)
        
        self.translator = GoogleTranslator(
            concurrency=concurrency,
            batch_size=batch_size,
            use_multi_endpoint=self.settings.get("use_multi_endpoint", DEFAULT_USE_MULTI_ENDPOINT),
            enable_lingva_fallback=self.settings.get("enable_lingva_fallback", DEFAULT_ENABLE_LINGVA_FALLBACK),
            request_delay_ms=self.settings.get("request_delay_ms", DEFAULT_REQUEST_DELAY_MS),
            timeout_seconds=self.settings.get("request_timeout", DEFAULT_TIMEOUT_SECONDS),
            max_retries=self.settings.get("max_retries", DEFAULT_MAX_RETRIES),
            use_syntax_guard=self.settings.get("use_syntax_guard", True)
        )
        self.merger = TextMerger(batch_size=batch_size)
        self.logger = logging.getLogger("Pipeline")
        self.js_ast_audit_extractor = JavaScriptAstAuditExtractor()
        
        # Optional components
        self.glossary: Glossary | None = None
        self.cache: TranslationCache | None = None
        self.backup_manager: BackupManager | None = None
        self.importer: TranslationImporter = TranslationImporter()
        # Progress throttling
        self._last_progress_update: float = 0
        self._progress_throttle_ms: int = self.settings.get("progress_throttle_ms", 100)
        
        # Engine profiling
        self._project_profile: ProjectProfile | None = None
        
        # Store parsed data for deferred backup (avoid re-parsing)
        self._parsed_data_cache: dict[str, Any] = {}
        
        # Initialize optional components based on settings
        self._init_components()

    def _init_components(self):
        """Initialize optional components based on settings."""
        # Glossary
        glossary_path = self.settings.get('glossary_path')
        if glossary_path and os.path.exists(glossary_path):
            self.glossary = Glossary(glossary_path)
            self.logger.info(f"Loaded glossary with {len(self.glossary)} terms")
        
        # Cache
        if self.settings.get('use_cache', True):
            cache_dir = self.settings.get('cache_dir')
            self.cache = get_cache(cache_dir)
            self.logger.info("Translation cache enabled")
        
        # Backup
        if self.settings.get('backup_enabled', True):
            backup_dir = self.settings.get('backup_dir')
            self.backup_manager = get_backup_manager(backup_dir)
            self.logger.info("Backup system enabled")

    def run(self):
        """Main entry point - runs the pipeline."""
        try:
            self.run_pipeline()
        except Exception as e:
            self.logger.exception("Pipeline Error")
            self.finished.emit(False, str(e))

    def stop(self):
        """Request pipeline stop."""
        self.should_stop = True

    def run_pipeline(self):
        """Execute the translation pipeline."""
        project_path = self.settings.get("project_path")
        target_lang = self.settings.get("target_lang", "tr")
        source_lang = self.settings.get("source_lang", "auto")

        # Validation
        if not project_path or not os.path.exists(project_path):
            self.finished.emit(False, "Project path not found")
            return

        self.stage_changed.emit(PipelineStage.VALIDATING.value, "Scanning project...")
        self.log_message.emit("info", f"Project: {project_path}")
        if self.cache:
            self.log_message.emit("info", f"Translation cache directory: {self.cache.cache_dir}")
        
        # Find Data folder
        data_dir = self._find_data_dir(project_path)
        if not data_dir:
            self.finished.emit(False, "Data folder not found. Is this an RPG Maker project?")
            return

        self.log_message.emit("info", f"Data folder: {data_dir}")
        
        # Engine profiling for project analysis
        try:
            self._project_profile = EngineProfiler(project_path).profile()
            self._log_engine_profile()
        except Exception as e:
            self.logger.warning(f"Engine profiling failed: {e}")
        
        # Word-wrap compatibility hint
        if self._project_profile and self._project_profile.has_wordwrap_plugins:
            if not self.settings.get("auto_wordwrap", False) and not self.settings.get("visustella_wordwrap", False):
                self.log_message.emit("info", "💡 Tip: Detected Message/WordWrap plugins. You might want to enable 'Auto Word-Wrap' in settings for better dialogue formatting.")
        
        # Collect files
        files = self._collect_files(data_dir)
        if not files:
            self.finished.emit(False, "No translatable files found")
            return

        self._emit_custom_surface_summary(files)

        coverage_requested = self.settings.get("coverage_audit", False) or bool(self.settings.get("coverage_report_path"))
        if coverage_requested:
            try:
                coverage_report = self._build_coverage_report(project_path, data_dir, files)
                self._emit_coverage_audit(coverage_report)

                coverage_report_path = self.settings.get("coverage_report_path")
                if coverage_report_path:
                    self._write_coverage_report(coverage_report, coverage_report_path)
            except Exception as error:
                self.logger.warning(f"Coverage audit skipped: {error}")
                self.log_message.emit("warning", f"Coverage audit skipped: {error}")

        self.log_message.emit("info", f"Found {len(files)} files to process")

        # Parse all files
        self.stage_changed.emit(PipelineStage.PARSING.value, "Extracting text...")
        all_entries, parsed_files = self._extract_all_text(files)
        
        if not all_entries:
            self.finished.emit(True, "No text found to translate.")
            return

        total = len(all_entries)
        self.log_message.emit("info", f"Extracted {total} text entries")
        
        # Export option (if requested)
        export_path = self.settings.get('export_path')
        if export_path:
            is_distinct = self.settings.get('export_distinct', False)
            self._export_entries(all_entries, export_path, distinct=is_distinct)
            if self.settings.get('export_only', False):
                self.finished.emit(True, f"Exported {total} entries (Distinct: {is_distinct}) to {export_path}")
                return

        # Initialize Importer
        self.importer = TranslationImporter()
        
        # Check for import file
        import_path = self.settings.get('import_path')
        if import_path and os.path.exists(import_path):
            self.importer.import_file(import_path)
            stats = self.importer.get_stats()
            self.log_message.emit("info", f"Imported {stats['imported']} translations (Global rules: {stats['global_rules']})")
        
        # Translate remaining entries
        self.stage_changed.emit(PipelineStage.TRANSLATING.value, f"Processing {total} entries...")
        results_map = self._translate_entries(all_entries, source_lang, target_lang)

        if self.should_stop:
            self.finished.emit(False, "Stopped by user")
            return

        # Apply and Save
        self.stage_changed.emit(PipelineStage.SAVING.value, "Saving files...")
        self._save_translations(parsed_files, results_map)

        # Save cache
        if self.cache:
            self.cache.save()
            stats = self.cache.get_stats()
            self.log_message.emit("info", f"Cache stats: {stats['hits']} hits, {stats['misses']} misses ({stats['hit_rate']})")

        self.stage_changed.emit(PipelineStage.COMPLETED.value, "Done!")
        self.finished.emit(True, f"Translation completed! Processed {total} entries.")

    def _find_child_case_insensitive(self, parent_dir: str, target_name: str, must_be_dir: bool) -> Optional[str]:
        """Find a direct child by name, tolerating case differences on case-sensitive filesystems."""
        if not parent_dir or not os.path.isdir(parent_dir):
            return None

        target_lower = target_name.lower()
        try:
            with os.scandir(parent_dir) as entries:
                for entry in entries:
                    if entry.name.lower() != target_lower:
                        continue
                    if must_be_dir and entry.is_dir():
                        return entry.path
                    if not must_be_dir and entry.is_file():
                        return entry.path
        except OSError:
            return None
        return None

    def _find_file_in_subdir_case_insensitive(self, base_dir: str, subdir_name: str, filename: str) -> Optional[str]:
        """Find `base_dir/subdir_name/filename` using case-insensitive matching for both path segments."""
        subdir_path = self._find_child_case_insensitive(base_dir, subdir_name, must_be_dir=True)
        if not subdir_path:
            return None
        return self._find_child_case_insensitive(subdir_path, filename, must_be_dir=False)

    def _find_data_dir(self, project_path: str) -> Optional[str]:
        """Find the Data directory in an RPG Maker project."""
        # MV/MZ web export structure
        candidates = [
            os.path.join(project_path, "www", "data"),
            os.path.join(project_path, "data"),
            os.path.join(project_path, "Data"),  # VX Ace
        ]
        
        for path in candidates:
            if os.path.exists(path) and os.path.isdir(path):
                return path

        # Case-insensitive fallback for Linux/macOS.
        www_dir = self._find_child_case_insensitive(project_path, "www", must_be_dir=True)
        if www_dir:
            www_data = self._find_child_case_insensitive(www_dir, "data", must_be_dir=True)
            if www_data:
                return www_data

        root_data = self._find_child_case_insensitive(project_path, "data", must_be_dir=True)
        if root_data:
            return root_data
        
        return None

    def _collect_files(self, data_dir: str) -> List[str]:
        """Collect translatable files from data directory and other sources."""
        extensions = ('.json', '.rvdata2', '.rxdata', '.rvdata')
        files = []
        
        # Standard Data folder
        with os.scandir(data_dir) as entries:
            for entry in entries:
                if not entry.is_file() or not entry.name.lower().endswith(extensions):
                    continue
                if self._should_skip_data_file(entry.name):
                    self.logger.debug("Skipping backup data file: %s", entry.name)
                    continue
                if entry.name.lower().endswith('.json') and not self._looks_like_json_document(entry.path):
                    self.logger.debug("Skipping non-JSON sidecar: %s", entry.name)
                    continue
                files.append(entry.path)
        
        # MV Plugin configuration (js/plugins.js)
        # Search relative to data_dir (e.g. data is www/data, so js is ../js)
        project_root = os.path.dirname(data_dir)
        plugin_js = self._find_file_in_subdir_case_insensitive(project_root, "js", "plugins.js")
        if not plugin_js:
            # Try sibling of Data
            plugin_js = self._find_file_in_subdir_case_insensitive(os.path.dirname(project_root), "js", "plugins.js")

        if plugin_js and os.path.exists(plugin_js):
            files.append(plugin_js)
            
            # Plugin JS UI literal extraction: Only scan plugin source files for safe UI strings
            # when project has shop/quest/heavy UI signals (narrow activation).
            # This is controlled by profile analysis to prevent false positives.
            self._maybe_collect_plugin_js_ui_files(project_root, files)

        files.extend(self._collect_custom_translation_files(project_root, plugin_js))
        
        # DKTools Localization / Plugin locale files (locales/*.json)
        # Check both project root and www folder for locales
        locale_roots = [project_root, os.path.dirname(project_root)]

        for root in locale_roots:
            locales_dir = self._find_child_case_insensitive(root, "locales", must_be_dir=True)
            if locales_dir and os.path.exists(locales_dir) and os.path.isdir(locales_dir):
                with os.scandir(locales_dir) as entries:
                    for entry in entries:
                        # Only include JSON files from locales folder (skip .pak files)
                        if not entry.is_file() or not entry.name.lower().endswith('.json'):
                            continue
                        if not self._looks_like_json_document(entry.path):
                            self.logger.debug("Skipping non-JSON locale sidecar: %s", entry.name)
                            continue
                        files.append(entry.path)
                        self.log_message.emit("info", f"Found locale file: {entry.name}")
                break  # Only use the first found locales dir

        files.extend(self._collect_safe_text_files(data_dir))
            
        # Sort files to ensure DB files come first (not strictly necessary but good for logs)
        def _sort_key(f):
            name = os.path.basename(f).lower()
            db_files = ['system.json', 'actors.json', 'classes.json', 'skills.json', 'items.json', 'weapons.json', 'armors.json', 'enemies.json', 'states.json']
            for i, dbf in enumerate(db_files):
                if dbf in name: return i
            return 100
            
        files.sort(key=lambda x: (_sort_key(x), x))
        return files

    def _looks_like_json_document(self, file_path: str) -> bool:
        """Return True when a `.json` file appears to contain a JSON object/array."""
        try:
            with open(file_path, "rb") as handle:
                while True:
                    chunk = handle.read(256)
                    if not chunk:
                        return False
                    if chunk.startswith(b"\xef\xbb\xbf"):
                        chunk = chunk[3:]
                    stripped = chunk.lstrip(b" \t\r\n\x00")
                    if not stripped:
                        continue
                    return stripped.startswith((b"{", b"["))
        except OSError as error:
            self.logger.warning(f"Failed to inspect JSON candidate {file_path}: {error}")
            return False

    def _should_skip_data_file(self, filename: str) -> bool:
        """Return True for obvious backup/duplicate data JSON files."""
        if not isinstance(filename, str):
            return False
        filename_lower = filename.lower()
        if filename_lower.endswith(self.IGNORED_DATA_FILE_SUFFIXES):
            return True
        return bool(re.search(r" - copy(?: \(\d+\))?\.json$", filename_lower))

    def _collect_custom_translation_files(self, project_root: str, plugin_js: Optional[str]) -> List[str]:
        """Collect supported non-standard translation surfaces discovered from plugins."""
        custom_files: List[str] = []
        if not plugin_js or not os.path.exists(plugin_js):
            return custom_files

        if self._has_active_plugin(plugin_js, self.HENDRIX_PLUGIN_NAME):
            for root in (project_root, os.path.dirname(project_root)):
                csv_path = self._find_child_case_insensitive(root, HENDRIX_CSV_FILENAME, must_be_dir=False)
                if not csv_path or not os.path.isfile(csv_path):
                    continue
                custom_files.append(csv_path)
                self.log_message.emit("info", f"Detected Hendrix Localization CSV surface: {os.path.basename(csv_path)}")
                break

        ts_plugin = self._get_active_plugin(plugin_js, self.TS_DECODE_PLUGIN_NAME)
        if ts_plugin is not None:
            scenario_root = self._find_child_case_insensitive(os.path.dirname(project_root), "scenario", must_be_dir=True)
            if not scenario_root:
                scenario_root = self._find_child_case_insensitive(project_root, "scenario", must_be_dir=True)
            if scenario_root and os.path.isdir(scenario_root):
                decode_key = self._read_ts_decode_key(ts_plugin)
                self.settings["ts_decode_key"] = decode_key
                with os.scandir(scenario_root) as entries:
                    for entry in entries:
                        if not entry.is_file() or not entry.name.lower().endswith(TS_SCENARIO_EXTENSION):
                            continue
                        custom_files.append(entry.path)
                if any(path.lower().endswith(TS_SCENARIO_EXTENSION) for path in custom_files):
                    self.log_message.emit("info", f"Detected TS_ADV scenario surface: {os.path.basename(scenario_root)}")

        return custom_files

    def _read_ts_decode_key(self, plugin_entry: Dict[str, Any]) -> int:
        """Read the TS_Decode XOR key from plugin parameters."""
        params = plugin_entry.get("parameters")
        if not isinstance(params, dict):
            return 255
        try:
            return int(params.get("Key", 255))
        except (TypeError, ValueError):
            return 255

    def _get_active_plugin(self, plugin_js_path: str, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Return the active plugin entry from `plugins.js` when present."""
        try:
            with open(plugin_js_path, "r", encoding="utf-8-sig") as handle:
                payload = handle.read()
        except OSError:
            return None

        try:
            start = payload.find("[")
            end = payload.rfind("]")
            if start < 0 or end < 0:
                return None
            plugins = json.loads(payload[start : end + 1])
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return None

        for plugin in plugins:
            if not isinstance(plugin, dict):
                continue
            if plugin.get("name") == plugin_name and plugin.get("status") is True:
                return plugin
        return None

    def _has_active_plugin(self, plugin_js_path: str, plugin_name: str) -> bool:
        """Return True when `plugins.js` contains an enabled plugin entry."""
        return self._get_active_plugin(plugin_js_path, plugin_name) is not None

    def _emit_custom_surface_summary(self, files: List[str]) -> None:
        """Log detected custom translation surfaces for user visibility."""
        counts = self._custom_surface_counts(files)
        if not counts:
            return

        formatted = ", ".join(
            f"{self.CUSTOM_SURFACE_KEYS.get(key, key)}: {count}"
            for key, count in counts.items()
        )
        self.log_message.emit("info", f"Detected custom translation surfaces -> {formatted}")

    def _custom_surface_counts(self, files: List[str]) -> Dict[str, int]:
        """Count known non-standard translation surfaces in the collected file list."""
        counts: Dict[str, int] = {}
        for file_path in files:
            basename = os.path.basename(file_path).lower()
            extension = os.path.splitext(file_path)[1].lower()
            if basename == HENDRIX_CSV_FILENAME:
                counts["hendrix_csv"] = counts.get("hendrix_csv", 0) + 1
            elif extension == TS_SCENARIO_EXTENSION:
                counts["ts_adv_scenarios"] = counts.get("ts_adv_scenarios", 0) + 1
        return counts

    def analyze_project_coverage(self, project_path: str) -> Dict[str, Any]:
        """Analyze which safe and audit-only text surfaces exist in a project."""
        data_dir = self._find_data_dir(project_path)
        if not data_dir:
            raise FileNotFoundError(f"Data folder not found under project path: {project_path}")

        collected_files = self._collect_files(data_dir)
        coverage_report = self._build_coverage_report(project_path, data_dir, collected_files)
        self._emit_coverage_audit(coverage_report)

        coverage_report_path = self.settings.get("coverage_report_path")
        if coverage_report_path:
            self._write_coverage_report(coverage_report, coverage_report_path)

        return coverage_report

    def _collect_safe_text_files(self, data_dir: str) -> List[str]:
        """Collect explicitly allowlisted text files from the data directory."""
        safe_files: List[str] = []

        try:
            with os.scandir(data_dir) as entries:
                for entry in entries:
                    if not entry.is_file():
                        continue
                    if entry.name.lower() in SUPPORTED_TEXT_FILENAMES:
                        safe_files.append(entry.path)
        except OSError as error:
            self.logger.warning(f"Failed to scan safe text files in {data_dir}: {error}")

        return safe_files

    def _maybe_collect_plugin_js_ui_files(self, project_root: str, files: List[str]) -> None:
        """
        Conditionally collect plugin JS files for safe sink UI extraction.
        
        Only activates when project has shop/quest/heavy UI signals to avoid
        false positive extraction from generic plugins.
        """
        enable_ui_extraction = self.settings.get("plugin_js_ui_extraction", False)
        
        if not enable_ui_extraction:
            return
        
        if self._project_profile:
            should_activate = (
                self._project_profile.has_shop_signals or
                self._project_profile.has_quest_signals or
                self._project_profile.is_ui_heavy
            )
            if not should_activate:
                self.log_message.emit("debug", "Plugin JS UI extraction skipped: no shop/quest/UI-heavy signals")
                return
        
        js_dir = self._find_child_case_insensitive(project_root, "js", must_be_dir=True)
        if not js_dir:
            js_dir = self._find_child_case_insensitive(os.path.dirname(project_root), "js", must_be_dir=True)
        if not js_dir:
            return
        
        plugin_js_dir = os.path.join(js_dir, "plugins")
        if not os.path.isdir(plugin_js_dir):
            return
        
        try:
            with os.scandir(plugin_js_dir) as entries:
                for entry in entries:
                    if not entry.is_file() or not entry.name.lower().endswith('.js'):
                        continue
                    if self._is_safe_plugin_js_file(entry.name):
                        files.append(entry.path)
                        self.log_message.emit("debug", f"Added plugin JS for UI extraction: {entry.name}")
        except OSError as error:
            self.logger.warning(f"Failed to scan plugin JS directory: {error}")

    def _is_safe_plugin_js_file(self, filename: str) -> bool:
        """Check if plugin JS file should be scanned for safe UI strings."""
        safe_patterns = [
            r'shop', r'merchant', r'buy', r'sell', r'trade',
            r'quest', r'mission', r'objective', r'journal',
            r'ui_', r'uielement', r'menu',
        ]
        import re
        filename_lower = filename.lower()
        for pattern in safe_patterns:
            if re.search(pattern, filename_lower):
                return True
        return False

    def _build_coverage_report(self, project_path: str, data_dir: str, collected_files: List[str]) -> Dict[str, Any]:
        """Build a coverage report for known text surfaces and audit-only JS files."""
        normalized_project_path = os.path.normpath(project_path)
        collected_set = {os.path.normpath(path) for path in collected_files}

        collected_by_extension: Dict[str, int] = {}
        for file_path in collected_files:
            extension = os.path.splitext(file_path)[1].lower() or "<no_ext>"
            collected_by_extension[extension] = collected_by_extension.get(extension, 0) + 1

        safe_text_files = self._collect_safe_text_files(data_dir)
        raw_js_files = self._collect_raw_js_audit_files(data_dir)
        raw_js_candidates: List[Dict[str, Any]] = []
        total_raw_js_candidates = 0
        raw_js_engines: Dict[str, int] = {}
        raw_js_bucket_totals: Counter[str] = Counter()
        raw_js_readiness: Counter[str] = Counter()
        raw_js_promising_files: List[str] = []

        for js_path in raw_js_files:
            entries, engine, audit_meta = self._extract_entries_for_audit(js_path)
            raw_js_engines[engine] = raw_js_engines.get(engine, 0) + 1
            raw_js_bucket_totals.update(audit_meta.get("confidence_buckets", {}))
            write_readiness = audit_meta.get("write_readiness")
            if write_readiness:
                raw_js_readiness.update([write_readiness])
            if not entries:
                continue

            relative_path = self._to_relative_project_path(normalized_project_path, js_path)
            total_raw_js_candidates += len(entries)
            raw_js_candidates.append({
                "path": relative_path,
                "engine": engine,
                "candidate_entries": len(entries),
                "confidence_buckets": audit_meta.get("confidence_buckets", {}),
                "write_readiness": write_readiness,
                "top_score": audit_meta.get("top_score"),
                "samples": [text[:120] for _path, text, _tag in entries[:3]],
            })
            if write_readiness == "promising":
                raw_js_promising_files.append(relative_path)

        raw_js_candidates.sort(key=lambda item: (-item["candidate_entries"], item["path"]))

        return {
            "project_path": normalized_project_path,
            "data_dir": os.path.normpath(data_dir),
            "collected": {
                "total_files": len(collected_files),
                "by_extension": collected_by_extension,
                "files": [
                    self._to_relative_project_path(normalized_project_path, path)
                    for path in sorted(collected_set)
                ],
            },
            "safe_text_surfaces": {
                "supported_filenames": sorted(SUPPORTED_TEXT_FILENAMES),
                "collected": [
                    self._to_relative_project_path(normalized_project_path, path)
                    for path in sorted(safe_text_files)
                    if os.path.normpath(path) in collected_set
                ],
                "missed": [
                    self._to_relative_project_path(normalized_project_path, path)
                    for path in sorted(safe_text_files)
                    if os.path.normpath(path) not in collected_set
                ],
            },
            "custom_surfaces": {
                "detected": self._custom_surface_counts(collected_files),
            },
            "raw_js_audit": {
                "total_files": len(raw_js_files),
                "engines": raw_js_engines,
                "confidence_buckets": dict(raw_js_bucket_totals),
                "write_readiness": dict(raw_js_readiness),
                "promising_files": sorted(raw_js_promising_files),
                "files_with_candidates": len(raw_js_candidates),
                "candidate_entries": total_raw_js_candidates,
                "files": raw_js_candidates,
            },
        }

    def _collect_raw_js_audit_files(self, data_dir: str) -> List[str]:
        """Collect engine/plugin JS files for audit-only coverage checks."""
        js_dir = self._find_js_dir(data_dir)
        if not js_dir:
            return []

        audit_files: List[str] = []
        for root, dirs, files in os.walk(js_dir):
            dirs[:] = [name for name in dirs if name.lower() not in self.RAW_JS_AUDIT_EXCLUDED_DIRS]
            relative_root = os.path.relpath(root, js_dir).replace("\\", "/")

            for filename in files:
                if not filename.lower().endswith(".js"):
                    continue
                if filename.lower() in self.RAW_JS_AUDIT_EXCLUDED_FILES:
                    continue

                relative_path = filename if relative_root == "." else f"{relative_root}/{filename}"
                lower_relative_path = relative_path.lower()
                lower_filename = filename.lower()

                if lower_relative_path.startswith("plugins/") or lower_filename.startswith("rpg_") or lower_filename == "main.js":
                    audit_files.append(os.path.join(root, filename))

        audit_files.sort()
        return audit_files

    def _find_js_dir(self, data_dir: str) -> Optional[str]:
        """Find the JS directory associated with a data directory."""
        project_root = os.path.dirname(data_dir)
        js_dir = self._find_child_case_insensitive(project_root, "js", must_be_dir=True)
        if js_dir:
            return js_dir
        return self._find_child_case_insensitive(os.path.dirname(project_root), "js", must_be_dir=True)

    def _extract_entries_for_audit(
        self,
        file_path: str,
    ) -> Tuple[List[Tuple[str, str, str]], str, Dict[str, Any]]:
        """Extract entries for coverage auditing without affecting the main pipeline."""
        if file_path.lower().endswith(".js"):
            candidates, engine = self.js_ast_audit_extractor.extract_audit_candidates(file_path)
            filtered_candidates = [
                candidate
                for candidate in candidates
                if self._should_keep_extracted_text(candidate.text)
            ]
            summary = self.js_ast_audit_extractor.summarize_candidates(filtered_candidates, engine)
            return (
                [(item.path, item.text, item.tag) for item in filtered_candidates],
                engine,
                summary,
            )

        parser = get_parser(file_path, self.settings)
        if not parser:
            return [], "none", {"confidence_buckets": {}, "write_readiness": "none", "top_score": None}

        try:
            entries = parser.extract_text(file_path)
        except Exception as error:
            self.logger.warning(f"Coverage audit skipped {os.path.basename(file_path)}: {error}")
            return [], "parser", {"confidence_buckets": {}, "write_readiness": "none", "top_score": None}

        filtered_entries = [
            (path, text, tag)
            for path, text, tag in entries
            if self._should_keep_extracted_text(text)
        ]
        return (
            filtered_entries,
            "parser",
            {
                "confidence_buckets": {"parser": len(filtered_entries)} if filtered_entries else {},
                "write_readiness": "unsupported" if filtered_entries else "none",
                "top_score": None,
            },
        )

    def _emit_coverage_audit(self, coverage_report: Dict[str, Any]) -> None:
        """Log a compact coverage summary for visibility."""
        collected = coverage_report.get("collected", {})
        safe_text = coverage_report.get("safe_text_surfaces", {})
        custom_surfaces = coverage_report.get("custom_surfaces", {})
        raw_js = coverage_report.get("raw_js_audit", {})

        self.log_message.emit(
            "info",
            (
                "Coverage audit: "
                f"{collected.get('total_files', 0)} collected surfaces "
                f"{collected.get('by_extension', {})}"
            ),
        )

        if safe_text.get("collected"):
            self.log_message.emit(
                "info",
                f"Coverage audit: safe text files in pipeline -> {', '.join(safe_text['collected'])}"
            )

        if safe_text.get("missed"):
            self.log_message.emit(
                "warning",
                f"Coverage audit: safe text files still missed -> {', '.join(safe_text['missed'])}"
            )

        if custom_surfaces.get("detected"):
            formatted_custom = ", ".join(
                f"{self.CUSTOM_SURFACE_KEYS.get(key, key)}={value}"
                for key, value in custom_surfaces["detected"].items()
            )
            self.log_message.emit(
                "info",
                f"Coverage audit: custom surfaces -> {formatted_custom}"
            )

        candidate_files = raw_js.get("files", [])
        raw_js_engines = raw_js.get("engines", {})
        if raw_js_engines:
            self.log_message.emit(
                "info",
                f"Coverage audit: raw JS engines -> {raw_js_engines}",
            )
        raw_js_buckets = raw_js.get("confidence_buckets", {})
        if raw_js_buckets:
            self.log_message.emit(
                "info",
                f"Coverage audit: raw JS confidence buckets -> {raw_js_buckets}",
            )
        raw_js_readiness = raw_js.get("write_readiness", {})
        if raw_js_readiness:
            self.log_message.emit(
                "info",
                f"Coverage audit: raw JS write readiness -> {raw_js_readiness}",
            )
        if candidate_files:
            top_candidates = candidate_files[:self.RAW_JS_AUDIT_TOP_SAMPLE_LIMIT]
            formatted = ", ".join(
                (
                    f"{item['path']} [{item.get('engine', 'unknown')}/"
                    f"{item.get('write_readiness', 'unknown')}] ({item['candidate_entries']})"
                )
                for item in top_candidates
            )
            self.log_message.emit(
                "info",
                (
                    "Coverage audit: raw JS candidate surfaces -> "
                    f"{raw_js.get('candidate_entries', 0)} entries across "
                    f"{raw_js.get('files_with_candidates', 0)} files. Top: {formatted}"
                ),
            )
        promising_files = raw_js.get("promising_files", [])
        if promising_files:
            formatted_promising = ", ".join(promising_files[:self.RAW_JS_AUDIT_TOP_SAMPLE_LIMIT])
            self.log_message.emit(
                "info",
                f"Coverage audit: promising JS allowlist candidates -> {formatted_promising}",
            )

    def _log_engine_profile(self) -> None:
        """Log engine detection profile with confidence score and evidence."""
        if not self._project_profile:
            return
        
        profile = self._project_profile
        ep = profile.engine_profile
        
        confidence_pct = ep.confidence * 100
        evidence_count = len(ep.evidence)
        
        self.log_message.emit("info", (
            f"Engine profile: {ep.engine.value.upper()} "
            f"(confidence: {confidence_pct:.0f}%, level: {ep.confidence_level}, "
            f"evidence: {evidence_count})"
        ))
        
        for evidence in ep.evidence[:5]:
            self.log_message.emit("debug", (
                f"  Evidence: [{evidence.source}] {evidence.description} "
                f"(weight: {evidence.weight})"
            ))
        
        if ep.risk_labels:
            sorted_risks = ", ".join(ep.risk_labels[:5])
            self.log_message.emit("info", f"  Risk signals: {sorted_risks}")
        
        if profile.visu_stella_plugins:
            count = len(profile.visu_stella_plugins)
            self.log_message.emit("info", f"  VisuStella plugins: {count}")
        
        self.log_message.emit("info", (
            f"  Project signals: plugins={profile.plugin_count}, "
            f"active={profile.active_plugin_count}, "
            f"ui_heavy={profile.is_ui_heavy}, "
            f"workers={profile.suggested_worker_count}, "
            f"strategy={profile.suggested_batch_strategy}"
        ))

    def _write_coverage_report(self, coverage_report: Dict[str, Any], output_path: str) -> None:
        """Write a JSON coverage report to disk."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with safe_write(output_path, "w", encoding="utf-8") as handle:
            json.dump(coverage_report, handle, ensure_ascii=False, indent=2)

    def _to_relative_project_path(self, project_path: str, file_path: str) -> str:
        """Return a stable project-relative path for reports."""
        return os.path.relpath(file_path, project_path).replace("\\", "/")

    def _extract_all_text(self, files: List[str]) -> Tuple[List[Tuple], Dict]:
        """Extract text from all files using parallel processing."""
        all_entries = []  # (file, path_key, text)
        parsed_files = {}  # file -> (parser, entries)
        
        from concurrent.futures import ThreadPoolExecutor, wait as _cf_wait, ALL_COMPLETED
        import threading
        
        lock = threading.Lock()
        
        # Determine worker count based on project profile
        if self._project_profile:
            max_workers = self._project_profile.suggested_worker_count
        else:
            max_workers = min(os.cpu_count() or 4, 8)
        
        def process_file(file_path):
            if self.should_stop:
                return None
                
            parser = get_parser(file_path, self.settings)
            if not parser:
                return None
            
            filename = os.path.basename(file_path)
            self.logger.debug(f"[extract] start: {filename}")
            t_extract = time.monotonic()
            
            try:
                entries = parser.extract_text(file_path)
                elapsed = time.monotonic() - t_extract
                if entries:
                    filtered = [
                        (path, text, tag)
                        for path, text, tag in entries
                        if self._should_keep_extracted_text(text)
                    ]
                    self.logger.debug(f"[extract] done: {filename} in {elapsed:.2f}s ({len(filtered)} entries)")
                    return file_path, parser, filtered, getattr(parser, '_last_loaded_data', None)
                self.logger.debug(f"[extract] done (empty): {filename} in {elapsed:.2f}s")
                return None
            except Exception as e:
                elapsed = time.monotonic() - t_extract
                self.logger.error(f"[extract] failed: {filename} in {elapsed:.2f}s — {e}")
                return None

        self.log_message.emit("info", f"Starting parallel extraction with {max_workers} workers...")

        # Use submit()+wait(timeout)+shutdown(wait=False) instead of executor.map() +
        # context-manager to avoid hanging forever if any worker thread gets stuck
        # (e.g. a corrupt Marshal file or a very large plugin JSON).
        _EXTRACT_PER_FILE_SEC = 30
        _EXTRACT_TOTAL_SEC = min(_EXTRACT_PER_FILE_SEC * max(len(files), 1), 300)

        _extract_executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            _extract_futures = {_extract_executor.submit(process_file, fp): fp for fp in files}
            _done, _not_done = _cf_wait(_extract_futures, timeout=_EXTRACT_TOTAL_SEC,
                                        return_when=ALL_COMPLETED)
            if _not_done:
                _hung = [os.path.basename(_extract_futures[f]) for f in _not_done]
                self.logger.error(
                    f"Extraction timeout ({_EXTRACT_TOTAL_SEC}s): {len(_not_done)} file(s) stuck "
                    f"— {_hung[:10]}"
                )
                self.log_message.emit(
                    "warning",
                    f"{len(_not_done)} file(s) timed out during extraction and were skipped."
                )
            results = []
            for _future in _done:
                try:
                    results.append(_future.result())
                except Exception as _e:
                    self.logger.error(f"Extraction future error: {_e}")
                    results.append(None)
            for _ in _not_done:
                results.append(None)
        finally:
            _extract_executor.shutdown(wait=False, cancel_futures=True)

        for res in results:
            if res:
                f_path, parser, entries, raw_data = res
                norm_path = os.path.normpath(f_path)
                parsed_files[norm_path] = (parser, entries)
                
                # Store raw data for Ruby files to avoid double-loading
                if raw_data is not None:
                    self._parsed_data_cache[norm_path] = raw_data
                
                for path, text, tag in entries:
                    all_entries.append((norm_path, path, text, tag))
        
        self.log_message.emit("info", f"Extraction completed. Found {len(all_entries)} items across {len(parsed_files)} files.")
        return all_entries, parsed_files

    def _should_keep_extracted_text(self, text: str) -> bool:
        """Filter blank entries without dropping valid single-character localized text."""
        stripped = text.strip()
        if not stripped:
            return False
        if len(stripped) > 1:
            return True
        return any(ord(char) > 127 for char in stripped)

    def _translate_entries(self, entries: List[Tuple], source_lang: str, target_lang: str) -> Dict:
        """Translate all entries using the translation engine with robust error handling."""
        results_map = {}  # (file, path) -> translated_text
        total = len(entries)

        retry_entries: List[Tuple[str, str, str, str]] = []  # (file, path, text, tag)
        retry_seen = set()

        def _queue_retry(file_path: str, original_entries: List[Tuple[str, str, str]]):
            for tag, path, text in original_entries:
                key = (file_path, path)
                if key in retry_seen:
                    continue
                retry_seen.add(key)
                retry_entries.append((file_path, path, text, tag))
        
        # 1. Prepare Request Data (Glossary & Cache Check)
        # We need to construct the list of dicts expected by TextMerger/Translator
        # Format: {'text': str, 'metadata': dict}
        
        raw_requests = []
        
        # Determine efficient batching strategy via TextMerger
        # TextMerger.create_merged_requests returns: (requests_list, merged_map)
        # requests_list is List[Dict] with 'text' and 'metadata'
        requests_list, merged_map = self.merger.create_merged_requests(entries)
        
        final_requests = []
        
        for req in requests_list:
            text = req['text']
            meta = req['metadata']
            
            # Cache Check
            if self.cache:
                cached = self.cache.get(text, source_lang, target_lang)
                if cached:
                    # Handle Cache Hit
                    if meta.get('is_merged'):
                        original_entries = merged_map.get(f"{meta['file']}::{meta['key']}")
                        if original_entries: # Valid merge data
                             split_results, mismatch = self.merger.split_merged_result_checked(cached, original_entries)
                             if mismatch:
                                 self.logger.warning(
                                     f"Merged cache mismatch for {meta['file']}::{meta['key']}. Retrying without merge."
                                 )
                                 _queue_retry(meta['file'], original_entries)
                                 continue
                             for sp_key, sp_text in split_results:
                                 results_map[(meta['file'], sp_key)] = sp_text
                    else:
                        results_map[(meta['file'], meta['key'])] = cached
                    continue

            # Glossary Protection
            protected_text = text
            glossary_map = {}
            if self.glossary:
                protected_text, glossary_map = self.glossary.protect_terms(text)
            
            # RPGM Code Protection: Handled by Translator
            rpgn_codes = []
            
            # Prepare Final Request
            # Add language codes and glossary_map to metadata
            # IMPORTANT: Store original unprotected text in metadata so translator can use it for cache consistency
            meta['glossary_map'] = glossary_map
            meta['source_lang'] = source_lang
            meta['target_lang'] = target_lang
            meta['original_text'] = text  # Store before protection for cache
            meta['rpgn_codes'] = rpgn_codes  # Store RPGM codes for restoration
            
            # We strictly use Dict structure as expected by new Translator
            final_requests.append({
                'text': protected_text,
                'metadata': meta
            })

        if not final_requests:
            self.log_message.emit("info", "All entries found in cache!")
            return results_map

        # PHASE SPLIT (Database first, then Maps/Events)
        db_files = {'system.json', 'actors.json', 'classes.json', 'skills.json', 'items.json', 'weapons.json', 'armors.json', 'enemies.json', 'states.json'}
        phase1_requests = []
        phase2_requests = []
        
        for req in final_requests:
            filename = os.path.basename(req['metadata']['file']).lower()
            if filename in db_files:
                phase1_requests.append(req)
            else:
                phase2_requests.append(req)

        self.log_message.emit("info", f"Execution Plan: Phase 1 (DB): {len(phase1_requests)} reqs | Phase 2 (Maps/Events): {len(phase2_requests)} reqs")

        # 2. Async Execution (Result Pattern)
        async def process_all():
            processed_count = 0
            total_reqs = len(final_requests)
            
            def on_progress(count):
                nonlocal processed_count
                processed_count += count
                current_time = time.time() * 1000
                if current_time - self._last_progress_update >= self._progress_throttle_ms:
                    self._last_progress_update = current_time
                    visible_count = min(processed_count, total_reqs)
                    self.progress_updated.emit(visible_count, total_reqs, f"Translating... {visible_count}/{total_reqs}")

            success_total, fail_total = 0, 0
            dynamic_glossary = {}

            async def process_results_batch(batch_results):
                suc, fal = 0, 0
                for res in batch_results:
                    if self.should_stop: break
                    meta = res.metadata
                    if not meta: continue
                    if res.success:
                        translated_text = res.translated_text
                        glossary_map = meta.get('glossary_map', {})
                        if self.glossary and glossary_map:
                            translated_text = self.glossary.restore_terms(translated_text, glossary_map)
                        # Restoration handled by Translator
                        if self.cache and res.original_text:
                            self.cache.set(res.original_text, translated_text, source_lang, target_lang)

                        if meta.get('is_merged'):
                            lookup_key = f"{meta['file']}::{meta['key']}"
                            original_entries = merged_map.get(lookup_key)
                            if original_entries:
                                split_pairs, mismatch = self.merger.split_merged_result_checked(translated_text, original_entries)
                                if mismatch:
                                    self.logger.warning(f"Merged translation mismatch for {lookup_key}. Retrying without merge.")
                                    _queue_retry(meta['file'], original_entries)
                                else:
                                    for sp_key, sp_text in split_pairs:
                                        results_map[(meta['file'], sp_key)] = sp_text
                                    suc += 1
                            else:
                                self.logger.error(f"Missing merge map for key: {lookup_key}")
                        else:
                            results_map[(meta['file'], meta['key'])] = translated_text
                            suc += 1
                    else:
                        fal += 1
                        self.logger.warning(f"Translation Failed: {meta.get('key')} - {res.error}")
                return suc, fal

            # Execute Phase 1
            if phase1_requests:
                self.log_message.emit("info", "Running Phase 1: Database Lexicon Translation")
                p1_results = await self.translator.translate_batch(phase1_requests, progress_callback=on_progress)
                s1, f1 = await process_results_batch(p1_results)
                success_total += s1
                fail_total += f1
                
                # Build dynamic glossary context from Phase 1 name translations
                for res in p1_results:
                    if res.success and res.original_text and res.metadata:
                        tag = res.metadata.get('description', '')
                        if 'name' in tag or 'system' in tag:
                            clean_orig = res.original_text.strip()
                            clean_trans = res.translated_text.strip()
                            if len(clean_orig) > 1 and len(clean_trans) > 1:
                                dynamic_glossary[clean_orig] = clean_trans
                                
                if dynamic_glossary:
                    self.log_message.emit("info", f"Extracted {len(dynamic_glossary)} context terms for Phase 2!")

            # Inject Dynamic Glossary context into Phase 2 metadata
            if dynamic_glossary and phase2_requests:
                for req in phase2_requests:
                    req['metadata']['dynamic_context'] = dynamic_glossary

            # Execute Phase 2
            if phase2_requests:
                self.log_message.emit("info", "Running Phase 2: Maps and Events Translation")
                p2_results = await self.translator.translate_batch(phase2_requests, progress_callback=on_progress)
                s2, f2 = await process_results_batch(p2_results)
                success_total += s2
                fail_total += f2

            # Retry mismatched merged blocks as single entries
            if retry_entries:
                self.logger.info(f"Retrying {len(retry_entries)} entries without merge...")

                retry_requests = []
                for file_path, path, text, tag in retry_entries:
                    protected_text = text
                    glossary_map = {}
                    if self.glossary:
                        protected_text, glossary_map = self.glossary.protect_terms(text)
                    # RPGM Code Protection: Handled by Translator
                    rpgn_codes = []

                    retry_requests.append({
                        'text': protected_text,
                        'metadata': {
                            'file': file_path,
                            'key': path,
                            'description': tag,
                            'is_merged': False,
                            'glossary_map': glossary_map,
                            'source_lang': source_lang,
                            'target_lang': target_lang,
                            'original_text': text,
                            'rpgn_codes': rpgn_codes
                        }
                    })

                retry_results = await self.translator.translate_batch(retry_requests, progress_callback=on_progress)

                for res in retry_results:
                    meta = res.metadata
                    if not meta:
                        continue
                    if res.success:
                        translated_text = res.translated_text
                        glossary_map = meta.get('glossary_map', {})
                        if self.glossary and glossary_map:
                            translated_text = self.glossary.restore_terms(translated_text, glossary_map)
                        # Restoration handled by Translator

                        if self.cache and res.original_text:
                            self.cache.set(res.original_text, translated_text, source_lang, target_lang)

                        results_map[(meta['file'], meta['key'])] = translated_text
                    else:
                        self.logger.warning(f"Retry Translation Failed: {meta.get('key')} - {res.error}")
                        fail_total += 1
            
            self.log_message.emit("info", f"Batch Completed. Success: {success_total}, Failed: {fail_total}")
            
            # Cleanup
            await self.translator.close()

        asyncio.run(process_all())
        
        return results_map

    def _save_translations(self, parsed_files: Dict, results_map: Dict):
        """Apply translations and save files using parallel processing."""
        from concurrent.futures import ThreadPoolExecutor, wait as _cf_wait, ALL_COMPLETED
        
        # Build updates map using Fallback Strategy:
        # 1. New translations from current run (results_map)
        # 2. Imported translations (self.importer)
        file_updates = {}
        
        # A. Fill from results_map (High Priority - current session changes)
        for (file_path, path), text in results_map.items():
            if file_path not in file_updates:
                file_updates[file_path] = {}
            file_updates[file_path][path] = text
            
        # B. Fill missing entries from Importer (including Global Distinct rules)
        for file_path, (parser, entries) in parsed_files.items():
            if file_path not in file_updates:
                file_updates[file_path] = {}
            
            for path, original_text, tag in entries:
                # Only fill if not already translated in this run
                if path not in file_updates[file_path]:
                    translation = self.importer.get_translation(file_path, path, original_text)
                    if translation:
                        file_updates[file_path][path] = translation
        
        def save_file(file_path):
            if self.should_stop:
                return
            
            filename_early = os.path.basename(file_path)
            self.logger.debug(f"[save] start: {filename_early}")
            t_save = time.monotonic()
            changes = file_updates.get(file_path)
            if not changes or file_path not in parsed_files:
                return
            
            parser, entries = parsed_files[file_path]
            filename = os.path.basename(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()
            
            tag_lookup = {path: tag for path, _t, tag in entries}
            
            visu_wrap = self.settings.get("visustella_wordwrap", False)
            auto_wrap = self.settings.get("auto_wordwrap", False)
            wrap_limit_std = self.settings.get("wordwrap_limit_standard", 54)
            wrap_limit_portrait = self.settings.get("wordwrap_limit_portrait", 44)
            
            for p, text in changes.items():
                tag = tag_lookup.get(p, "")
                if tag.startswith("message_dialogue"):
                    if visu_wrap:
                        if not text.startswith("<WordWrap>"):
                            changes[p] = "<WordWrap>" + text
                    elif auto_wrap and "\n" not in text:
                        # Use portrait limit if the tag indicates a picture is present
                        width = wrap_limit_portrait if "hasPicture" in tag else wrap_limit_std
                        
                        # Calculate visible length (exclude RPG Maker escape codes)
                        import re as _re
                        _CODE_RE = _re.compile(r'\\[A-Za-z]+(?:\[[^\]]*\])?')
                        visible_text = _CODE_RE.sub('', text)
                        if len(visible_text) > width:
                            # Code-aware wrapping: treat escape codes as zero-width atoms
                            # Split text into (code, text) segments, wrap only visible text
                            segments = _CODE_RE.split(text)
                            codes = _CODE_RE.findall(text)
                            # Rebuild with codes as atomic inserts
                            flat_parts: list[tuple[str, bool]] = []  # (content, is_code)
                            for i, seg in enumerate(segments):
                                if seg:
                                    flat_parts.append((seg, False))
                                if i < len(codes):
                                    flat_parts.append((codes[i], True))
                            
                            # Greedy line-break: accumulate visible chars, break at word boundaries
                            lines: list[str] = []
                            current_line = ""
                            current_visible = 0
                            for part, is_code in flat_parts:
                                if is_code:
                                    current_line += part  # Zero visible width
                                else:
                                    words = part.split(' ')
                                    for wi, word in enumerate(words):
                                        space = ' ' if (current_visible > 0 and wi > 0) or (current_visible > 0 and current_line and not current_line.endswith(' ')) else ''
                                        if wi > 0:
                                            space = ' '
                                        word_len = len(word)
                                        if current_visible + len(space) + word_len > width and current_visible > 0:
                                            lines.append(current_line.rstrip())
                                            current_line = word
                                            current_visible = word_len
                                        else:
                                            current_line += space + word if current_visible > 0 or wi > 0 else word
                                            current_visible += len(space) + word_len
                            if current_line.strip():
                                lines.append(current_line.rstrip())
                            if lines:
                                changes[p] = "\n".join(lines)
            
            try:
                # Get pre-loaded data for Ruby files to avoid double-loading
                cached_data = self._parsed_data_cache.get(file_path)
                
                # Apply translations (backup deferred until after success)
                if file_ext in ('.rvdata2', '.rxdata', '.rvdata') and cached_data is not None:
                    new_data = parser.apply_translation(file_path, changes, original_data=cached_data)
                else:
                    new_data = parser.apply_translation(file_path, changes)
                
                if new_data is None:
                    parser_failure_reason = getattr(parser, "last_apply_error", None)
                    if parser_failure_reason and "write disabled" in parser_failure_reason.lower():
                        self.log_message.emit("info", f"{filename}: script writing disabled, preserving original file")
                        self.logger.debug(f"[save] skipped (write disabled): {filename} in {time.monotonic() - t_save:.2f}s")
                        return filename
                    if parser_failure_reason:
                        self.log_message.emit("warning", f"{filename}: {parser_failure_reason}")
                    raise ValueError(
                        parser_failure_reason or f"Parser returned no writable data for {filename}"
                    )
                
                # Write file
                if file_ext == '.json':
                    with safe_write(file_path, 'w', encoding='utf-8') as f:
                        json.dump(new_data, f, ensure_ascii=False)
                
                elif file_ext == '.js':
                    with safe_write(file_path, 'w', encoding='utf-8') as f:
                        if isinstance(new_data, str):
                            f.write(new_data)
                        else:
                            prefix = getattr(parser, '_js_prefix', "var $plugins = \n")
                            suffix = getattr(parser, '_js_suffix', ";\n")
                            f.write(prefix)
                            json.dump(new_data, f, ensure_ascii=False)
                            f.write(suffix)

                elif file_ext == '.txt':
                    if not isinstance(new_data, str):
                        raise ValueError(f"Expected text output for {filename}, got {type(new_data).__name__}")
                    with safe_write(file_path, 'w', encoding='utf-8', newline='') as f:
                        f.write(new_data)

                elif file_ext == '.csv':
                    if not isinstance(new_data, str):
                        raise ValueError(f"Expected CSV text output for {filename}, got {type(new_data).__name__}")
                    with safe_write(file_path, 'w', encoding='utf-8', newline='') as f:
                        f.write(new_data)

                elif file_ext == TS_SCENARIO_EXTENSION:
                    if not isinstance(new_data, str):
                        raise ValueError(f"Expected scenario text output for {filename}, got {type(new_data).__name__}")
                    with safe_write(file_path, 'w', encoding='utf-8', newline='') as f:
                        f.write(new_data)
                          
                elif file_ext in ('.rvdata2', '.rxdata', '.rvdata'):
                    if isinstance(new_data, bytes):
                        # Binary-patched data — write directly
                        with safe_write(file_path, 'wb') as f:
                            f.write(new_data)
                    else:
                        # Legacy path (script containers) — use rubymarshal.writer
                        import rubymarshal.writer
                        with safe_write(file_path, 'wb') as f:
                            rubymarshal.writer.write(f, new_data)
                
                self.logger.debug(f"[save] done: {filename} in {time.monotonic() - t_save:.2f}s")
                return filename
                
            except Exception as e:
                self.logger.error(f"[save] failed: {filename} in {time.monotonic() - t_save:.2f}s — {e}")
                return None

        # Create backups sequentially BEFORE launching parallel workers.
        # Doing backup inside workers caused NTFS directory serialization with
        # 8 concurrent shutil.copy2 calls to the same folder, effectively
        # serializing all workers while also starving each other — producing
        # 10+ minute hangs on large projects.  Sequential backup is safe
        # because the backup is only a read + copy; the translated write
        # happens afterward in the parallel phase.
        if self.backup_manager:
            self.log_message.emit("info", f"Creating backups for {len(file_updates)} files...")
            for file_path in file_updates.keys():
                if file_path in parsed_files:
                    result = self.backup_manager.create_backup(file_path)
                    if not result:
                        self.logger.warning(
                            f"Backup failed for {os.path.basename(file_path)} — "
                            "save will proceed anyway"
                        )

        self.log_message.emit("info", f"Saving {len(file_updates)} files in parallel...")

        # Worker selection based on project profile
        if self._project_profile:
            strategy = self._project_profile.suggested_batch_strategy
            if strategy == "conservative":
                max_workers = 2
            elif strategy == "capped":
                max_workers = min(4, os.cpu_count() or 4)
            else:
                max_workers = min(os.cpu_count() or 4, 8)
        else:
            max_workers = min(os.cpu_count() or 4, 8)
        
        # Submit all save tasks with a per-batch wall-clock timeout.
        # executor.map() / the context-manager shutdown(wait=True) block forever
        # if any worker thread hangs (e.g. rubymarshal.writer on a cyclic object,
        # an antivirus holding a temp file, or a corrupt Ruby Marshal stream).
        # Using submit() + wait(timeout) + shutdown(wait=False) lets us detect and
        # report stuck files instead of hanging the entire application.
        # Cap total timeout at 10 minutes regardless of file count — 246 files × 60s
        # would produce a ~4 hour timeout that looks like an infinite hang to the user.
        # Raised from 300s (5 min) to 600s (10 min) to absorb antivirus scanning delays.
        _PER_FILE_BUDGET_SEC = 30
        _MAX_TOTAL_SEC = 600  # 10-minute hard ceiling (raised from 300 to absorb AV scanning)
        _TOTAL_TIMEOUT_SEC = min(_PER_FILE_BUDGET_SEC * max(len(file_updates), 1), _MAX_TOTAL_SEC)

        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            # Submit .js files (plugins.js etc.) first so they are not starved at the
            # tail of the timeout window when many JSON files are queued ahead of them.
            sorted_paths = sorted(
                file_updates.keys(),
                key=lambda p: (0 if p.lower().endswith(".js") else 1),
            )
            future_to_path = {executor.submit(save_file, fp): fp for fp in sorted_paths}
            done, not_done = _cf_wait(future_to_path, timeout=_TOTAL_TIMEOUT_SEC,
                                      return_when=ALL_COMPLETED)

            saved_filenames: list = []
            for future in done:
                try:
                    saved_filenames.append(future.result())
                except Exception as exc:
                    fp = future_to_path[future]
                    self.logger.error(f"Error saving {os.path.basename(fp)}: {exc}")
                    saved_filenames.append(None)

            if not_done:
                hung_names = [os.path.basename(future_to_path[f]) for f in not_done]
                self.logger.error(
                    f"Save timeout ({_TOTAL_TIMEOUT_SEC}s): {len(not_done)} file(s) did not "
                    f"complete — {hung_names[:10]}"
                )
                self.log_message.emit(
                    "warning",
                    f"{len(not_done)} file(s) timed out during save and were skipped. "
                    "See the log for details."
                )
                for _ in not_done:
                    saved_filenames.append(None)
        finally:
            # shutdown(wait=False) abandons any still-running threads instead of
            # blocking the main thread until they finish (or hang forever).
            executor.shutdown(wait=False, cancel_futures=True)

        success_count = len([f for f in saved_filenames if f])

        if any(os.path.basename(path).lower() == HENDRIX_CSV_FILENAME for path in file_updates):
            self._ensure_hendrix_target_language(file_updates.keys())

        self.log_message.emit("success", f"Successfully saved {success_count} files.")

    def _ensure_hendrix_target_language(self, updated_files: Any) -> None:
        """Ensure Hendrix Localization knows about the active target language."""
        target_lang = str(self.settings.get("target_lang", "tr") or "tr").strip().lower()
        if not target_lang:
            return

        csv_files = [
            path for path in updated_files
            if os.path.basename(path).lower() == HENDRIX_CSV_FILENAME
        ]
        if not csv_files:
            return

        plugin_js_path = self._find_hendrix_plugin_js(csv_files[0])
        if not plugin_js_path or not os.path.exists(plugin_js_path):
            return

        try:
            with open(plugin_js_path, "r", encoding="utf-8-sig") as handle:
                payload = handle.read()
            start = payload.find("[")
            end = payload.rfind("]")
            if start < 0 or end < 0:
                return

            plugins = json.loads(payload[start : end + 1])
            changed = False

            for plugin in plugins:
                if not isinstance(plugin, dict) or plugin.get("name") != self.HENDRIX_PLUGIN_NAME:
                    continue
                params = plugin.get("parameters")
                if not isinstance(params, dict):
                    continue

                raw_languages = params.get("Languages", "[]")
                language_entries = self._parse_hendrix_language_entries(raw_languages)
                known_symbols = {entry.get("Symbol", "").strip().lower() for entry in language_entries}
                if target_lang not in known_symbols:
                    font_size = "28"
                    if language_entries:
                        font_size = str(language_entries[0].get("FontSize", "28") or "28")
                    language_entries.append({
                        "Name": self._display_name_for_language(target_lang),
                        "Symbol": target_lang,
                        "Font": "",
                        "FontSize": font_size,
                    })
                    params["Languages"] = json.dumps(
                        [json.dumps(entry, ensure_ascii=False) for entry in language_entries],
                        ensure_ascii=False,
                    )
                    changed = True

                if params.get("Default Language") != target_lang:
                    params["Default Language"] = target_lang
                    changed = True
                break

            if not changed:
                return

            if self.backup_manager:
                self.backup_manager.create_backup(plugin_js_path)

            rewritten = payload[:start] + json.dumps(plugins, ensure_ascii=False, separators=(",", ":")) + payload[end + 1 :]
            with safe_write(plugin_js_path, 'w', encoding='utf-8') as handle:
                handle.write(rewritten)
            self.log_message.emit("info", f"Updated Hendrix Localization language config for '{target_lang}'")
        except Exception as error:
            self.logger.warning(f"Failed to update Hendrix Localization config: {error}")
            self.log_message.emit("warning", f"Failed to update Hendrix Localization config: {error}")

    def _find_hendrix_plugin_js(self, csv_path: str) -> Optional[str]:
        """Find the `plugins.js` paired with a Hendrix CSV file."""
        csv_dir = os.path.dirname(csv_path)
        candidates = [csv_dir, os.path.dirname(csv_dir)]
        for root in candidates:
            plugin_js = self._find_file_in_subdir_case_insensitive(root, "js", "plugins.js")
            if plugin_js:
                return plugin_js
        return None

    def _parse_hendrix_language_entries(self, raw_languages: Any) -> List[Dict[str, Any]]:
        """Parse Hendrix `Languages` plugin parameter payload."""
        if not isinstance(raw_languages, str) or not raw_languages.strip():
            return []
        try:
            payload = json.loads(raw_languages)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

        parsed_entries: List[Dict[str, Any]] = []
        for entry in payload:
            if not isinstance(entry, str):
                continue
            try:
                value = json.loads(entry)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if isinstance(value, dict):
                parsed_entries.append(value)
        return parsed_entries

    def _display_name_for_language(self, language_symbol: str) -> str:
        """Return a friendly display name for newly added Hendrix languages."""
        names = {
            "tr": "Turkish",
            "en": "English",
            "jp": "Japanese",
            "cn": "Chinese",
            "th": "Thai",
        }
        return names.get(language_symbol.lower(), language_symbol.upper())

    def _export_entries(self, entries: List[Tuple], export_path: str, distinct: bool = False):
        """Export extracted entries to file with support for distinct string mode."""
        try:
            # Ensure target directory exists
            export_dir = os.path.dirname(export_path)
            if export_dir and not os.path.exists(export_dir):
                os.makedirs(export_dir, exist_ok=True)
                
            exporter = TranslationExporter()
            
            for file_path, path, text, tag in entries:
                # Pass tag as context if available
                exporter.add_entry(file_path, path, text, context=str(tag or ""))
            
            success = False
            if export_path.endswith('.json'):
                success = exporter.export_json(export_path, distinct=distinct)
            else:
                success = exporter.export_csv(export_path, distinct=distinct)
            
            if success:
                mode_str = " (Distinct Mode)" if distinct else ""
                self.log_message.emit("info", f"Successfully exported {len(entries)} entries{mode_str} to: {export_path}")
            else:
                self.log_message.emit("error", f"Export failed! Please check if the file '{export_path}' is open in another program.")
        except Exception as e:
            error_msg = f"Critical Export Error: {str(e)}"
            self.logger.error(error_msg)
            self.log_message.emit("error", error_msg)

    def _import_translations(self, import_path: str) -> Dict:
        """Import translations from file."""
        importer = TranslationImporter()
        
        if import_path.endswith('.json'):
            importer.import_json(import_path)
        else:
            importer.import_csv(import_path)
        
        # Convert to results_map format
        results_map = {}
        for file_path, translations in importer.get_all_translations().items():
            for path, translated in translations.items():
                results_map[(file_path, path)] = translated
        
        return results_map
