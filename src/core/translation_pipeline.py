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
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

from PyQt6.QtCore import QObject, pyqtSignal as Signal

from .translator import GoogleTranslator, TranslationRequest
from .parser_factory import get_parser
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


class TranslationPipeline(QObject):
    """
    Main translation pipeline that orchestrates the entire workflow.
    """
    
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
            max_retries=self.settings.get("max_retries", DEFAULT_MAX_RETRIES)
        )
        self.merger = TextMerger(batch_size=batch_size)
        self.logger = logging.getLogger("Pipeline")
        
        # Optional components
        self.glossary: Optional[Glossary] = None
        self.cache: Optional[TranslationCache] = None
        self.backup_manager: Optional[BackupManager] = None
        
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
        
        # Find Data folder
        data_dir = self._find_data_dir(project_path)
        if not data_dir:
            self.finished.emit(False, "Data folder not found. Is this an RPG Maker project?")
            return

        self.log_message.emit("info", f"Data folder: {data_dir}")
        
        # Collect files
        files = self._collect_files(data_dir)
        if not files:
            self.finished.emit(False, "No translatable files found")
            return

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
            self._export_entries(all_entries, export_path)
            if self.settings.get('export_only', False):
                self.finished.emit(True, f"Exported {total} entries to {export_path}")
                return

        # Check for import file
        import_path = self.settings.get('import_path')
        if import_path and os.path.exists(import_path):
            results_map = self._import_translations(import_path)
            self.log_message.emit("info", f"Imported {len(results_map)} translations from file")
        else:
            # Translate
            self.stage_changed.emit(PipelineStage.TRANSLATING.value, f"Translating {total} entries...")
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
        
        return None

    def _collect_files(self, data_dir: str) -> List[str]:
        """Collect translatable files from data directory and other sources."""
        extensions = ('.json', '.rvdata2', '.rxdata', '.rvdata')
        files = []
        
        # Standard Data folder
        for entry in os.scandir(data_dir):
            if entry.is_file() and entry.name.lower().endswith(extensions):
                files.append(entry.path)
        
        # MV Plugin configuration (js/plugins.js)
        # Search relative to data_dir (e.g. data is www/data, so js is ../js)
        project_root = os.path.dirname(data_dir)
        plugin_js = os.path.join(project_root, "js", "plugins.js")
        if not os.path.exists(plugin_js):
            # Try sibling of Data
            plugin_js = os.path.join(os.path.dirname(project_root), "js", "plugins.js")

        if os.path.exists(plugin_js):
            files.append(plugin_js)
        
        # DKTools Localization / Plugin locale files (locales/*.json)
        # Check both project root and www folder for locales
        locale_candidates = [
            os.path.join(project_root, "locales"),
            os.path.join(os.path.dirname(project_root), "locales"),
        ]
        
        for locales_dir in locale_candidates:
            if os.path.exists(locales_dir) and os.path.isdir(locales_dir):
                for entry in os.scandir(locales_dir):
                    # Only include JSON files from locales folder (skip .pak files)
                    if entry.is_file() and entry.name.lower().endswith('.json'):
                        files.append(entry.path)
                        self.log_message.emit("info", f"Found locale file: {entry.name}")
                break  # Only use the first found locales dir
            
        # Sort for consistent ordering
        files.sort()
        return files

    def _extract_all_text(self, files: List[str]) -> Tuple[List[Tuple], Dict]:
        """Extract text from all files using parallel processing."""
        all_entries = []  # (file, path_key, text)
        parsed_files = {}  # file -> (parser, entries)
        
        from concurrent.futures import ThreadPoolExecutor
        import threading
        
        lock = threading.Lock()
        max_workers = min(os.cpu_count() or 4, 8) # Don't overwhelm IO but use cores
        
        def process_file(file_path):
            if self.should_stop:
                return None
                
            parser = get_parser(file_path, self.settings)
            if not parser:
                return None
            
            # Use a safe way to emit from thread
            filename = os.path.basename(file_path)
            
            try:
                entries = parser.extract_text(file_path)
                if entries:
                    # Filter short text here to reduce memory/overhead
                    # Entries are (path, text, tag)
                    filtered = [(p, t, tag) for p, t, tag in entries if len(t.strip()) > 1]
                    return file_path, parser, filtered
                return None
            except Exception as e:
                self.logger.error(f"Failed to parse {filename}: {e}")
                return None

        self.log_message.emit("info", f"Starting parallel extraction with {max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(process_file, files))
            
        for res in results:
            if res:
                f_path, parser, entries = res
                # Normalize file path for consistent dict keys
                norm_path = os.path.normpath(f_path)
                parsed_files[norm_path] = (parser, entries)
                for path, text, tag in entries:
                    all_entries.append((norm_path, path, text, tag))
        
        self.log_message.emit("info", f"Extraction completed. Found {len(all_entries)} items across {len(parsed_files)} files.")
        return all_entries, parsed_files

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
            
            # Prepare Final Request
            # Add language codes and glossary_map to metadata
            # IMPORTANT: Store original unprotected text in metadata so translator can use it for cache consistency
            meta['glossary_map'] = glossary_map
            meta['source_lang'] = source_lang
            meta['target_lang'] = target_lang
            meta['original_text'] = text  # Store before protection for cache
            
            # We strictly use Dict structure as expected by new Translator
            final_requests.append({
                'text': protected_text,
                'metadata': meta
            })

        if not final_requests:
            self.log_message.emit("info", "All entries found in cache!")
            return results_map

        self.log_message.emit("info", f"Sending {len(final_requests)} requests to translation engine...")

        # 2. Async Execution (Result Pattern)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        async def process_all():
             # Progress Callback
            processed_count = 0
            total_reqs = len(final_requests)
            
            def on_progress(count):
                nonlocal processed_count
                processed_count += count
                self.progress_updated.emit(processed_count, total_reqs, f"Translating... {processed_count}/{total_reqs}")

            # Execute Batch Translation
            # Returns List[TranslationResult]
            results = await self.translator.translate_batch(final_requests, progress_callback=on_progress)
            
            success_count = 0
            fail_count = 0
            
            for res in results:
                if self.should_stop: break
                
                meta = res.metadata
                if not meta: continue
                
                if res.success:
                    translated_text = res.translated_text
                    
                    # Restore Glossary
                    glossary_map = meta.get('glossary_map', {})
                    if self.glossary and glossary_map:
                        translated_text = self.glossary.restore_terms(translated_text, glossary_map)
                    
                    # Cache Save
                    if self.cache and res.original_text:
                        self.cache.set(res.original_text, translated_text, source_lang, target_lang)

                    # Handle Merged vs Single
                    if meta.get('is_merged'):
                         # Lookup original entries for splitting from map
                         lookup_key = f"{meta['file']}::{meta['key']}"
                         original_entries = merged_map.get(lookup_key)
                         
                         if original_entries:
                             split_pairs, mismatch = self.merger.split_merged_result_checked(translated_text, original_entries)
                             if mismatch:
                                 self.logger.warning(
                                     f"Merged translation mismatch for {lookup_key}. Retrying without merge."
                                 )
                                 _queue_retry(meta['file'], original_entries)
                             else:
                                 for sp_key, sp_text in split_pairs:
                                     results_map[(meta['file'], sp_key)] = sp_text
                                 success_count += 1
                         else:
                             self.logger.error(f"Missing merge map for key: {lookup_key}")
                    else:
                        results_map[(meta['file'], meta['key'])] = translated_text
                        success_count += 1
                else:
                    fail_count += 1
                    self.logger.warning(f"Translation Failed: {meta.get('key')} - {res.error}")

            # Retry mismatched merged blocks as single entries
            if retry_entries:
                self.logger.info(f"Retrying {len(retry_entries)} entries without merge...")

                retry_requests = []
                for file_path, path, text, tag in retry_entries:
                    protected_text = text
                    glossary_map = {}
                    if self.glossary:
                        protected_text, glossary_map = self.glossary.protect_terms(text)

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
                            'original_text': text
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

                        if self.cache and res.original_text:
                            self.cache.set(res.original_text, translated_text, source_lang, target_lang)

                        results_map[(meta['file'], meta['key'])] = translated_text
                    else:
                        self.logger.warning(f"Retry Translation Failed: {meta.get('key')} - {res.error}")
            
            self.log_message.emit("info", f"Batch Completed. Success: {success_count}, Failed: {fail_count}")
            
            # Cleanup
            await self.translator.close()

        loop.run_until_complete(process_all())
        
        return results_map

    def _save_translations(self, parsed_files: Dict, results_map: Dict):
        """Apply translations and save files using parallel processing."""
        from concurrent.futures import ThreadPoolExecutor
        
        # Group by file
        file_updates = {}
        for (file_path, path), text in results_map.items():
            if file_path not in file_updates:
                file_updates[file_path] = {}
            file_updates[file_path][path] = text
        
        def save_file(file_path):
            if self.should_stop:
                return
            
            changes = file_updates.get(file_path)
            if not changes or file_path not in parsed_files:
                return
            
            parser, _ = parsed_files[file_path]
            filename = os.path.basename(file_path)
            
            try:
                # Create backup first
                if self.backup_manager:
                    backup_path = self.backup_manager.create_backup(file_path)
                    if not backup_path:
                        self.logger.warning(f"Backup failed for {filename}, skipping")
                        return
                
                # Apply translations
                new_data = parser.apply_translation(file_path, changes)
                
                # Write file
                if file_path.endswith('.json'):
                    with safe_write(file_path, 'w', encoding='utf-8') as f:
                        json.dump(new_data, f, ensure_ascii=False)
                
                elif file_path.endswith('.js'):
                    prefix = getattr(parser, '_js_prefix', "var $plugins = ")
                    suffix = getattr(parser, '_js_suffix', ";")
                    with safe_write(file_path, 'w', encoding='utf-8') as f:
                        f.write(prefix)
                        json.dump(new_data, f, ensure_ascii=False, indent=0)
                        f.write(suffix)
                        
                elif file_path.endswith(('.rvdata2', '.rxdata', '.rvdata')):
                    import rubymarshal.writer
                    with safe_write(file_path, 'wb') as f:
                        rubymarshal.writer.write(f, new_data)
                
                return filename
                
            except Exception as e:
                self.logger.error(f"Failed to save {filename}: {e}")
                # Try to restore from backup
                if self.backup_manager:
                    backups = self.backup_manager.get_backups_for_file(file_path)
                    if backups:
                        self.backup_manager.restore_backup(backups[-1], file_path)
                return None

        self.log_message.emit("info", f"Saving {len(file_updates)} files in parallel...")
        
        max_workers = min(os.cpu_count() or 4, 8)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            saved_filenames = list(executor.map(save_file, file_updates.keys()))
            
        success_count = len([f for f in saved_filenames if f])
        self.log_message.emit("success", f"Successfully saved {success_count} files.")

    def _export_entries(self, entries: List[Tuple], export_path: str):
        """Export extracted entries to file."""
        exporter = TranslationExporter()
        
        # Group by file
        file_entries = {}
        for file_path, path, text, tag in entries:
            if file_path not in file_entries:
                file_entries[file_path] = []
            file_entries[file_path].append((path, text))
        
        for file_path, extractions in file_entries.items():
            exporter.add_entries_from_file(file_path, extractions)
        
        if export_path.endswith('.json'):
            exporter.export_json(export_path)
        else:
            exporter.export_csv(export_path)
        
        self.log_message.emit("info", f"Exported {len(entries)} entries")

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
