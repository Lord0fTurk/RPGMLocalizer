"""
CSV and JSON Export/Import engine for RPG Maker translations.
Optimized for high-volume data, distinct string management, and cross-platform spreadsheet compatibility.
"""
import csv
import json
import os
import logging
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class TranslationEntry:
    """Represents a single translatable text entry with full context."""
    file_path: str
    json_path: str
    original_text: str
    translated_text: str = ""
    status: str = "pending"  # pending, translated, reviewed, skipped
    context: str = ""       # Optional context (e.g., actor name, map name)

class TranslationExporter:
    """
    Exports extracted text to CSV or JSON for external editing.
    Supports unique string grouping to reduce translator workload.
    """
    
    CSV_COLUMNS = ['file', 'path', 'original', 'translated', 'status', 'context']
    
    def __init__(self):
        self.entries: List[TranslationEntry] = []
    
    def add_entry(self, file_path: str, json_path: str, text: str, context: str = ""):
        """Add a single entry with full context."""
        entry = TranslationEntry(
            file_path=file_path,
            json_path=json_path,
            original_text=text,
            context=context
        )
        self.entries.append(entry)

    def add_entries_from_file(self, file_path: str, extractions: List[Tuple]):
        """
        Add extracted text entries from a file.
        Backward compatible with legacy (path, text) tuples or (path, text, context) triples.
        """
        for extraction in extractions:
            path = extraction[0]
            text = extraction[1]
            context = extraction[2] if len(extraction) > 2 else ""
            self.add_entry(file_path, path, text, context)
    
    def _prepare_export_data(self, distinct: bool = False) -> List[TranslationEntry]:
        """Process entries for export, optionally merging duplicates."""
        if not distinct:
            return self.entries
            
        unique_map: Dict[str, TranslationEntry] = {}
        for e in self.entries:
            if e.original_text not in unique_map:
                # Store the first occurrence as the representative
                # We mark the path as [DISTINCT] to signal global application during import
                unique_map[e.original_text] = TranslationEntry(
                    file_path="[DISTINCT]",
                    json_path="[DISTINCT]",
                    original_text=e.original_text,
                    context="Multiple occurrences merged"
                )
        return list(unique_map.values())

    def export_csv(self, output_path: str, distinct: bool = False) -> bool:
        """Export to CSV optimized for Excel/Google Sheets."""
        data_to_export = self._prepare_export_data(distinct)
        try:
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS, quoting=csv.QUOTE_ALL)
                writer.writeheader()
                
                for entry in data_to_export:
                    writer.writerow({
                        'file': entry.file_path,
                        'path': entry.json_path,
                        'original': entry.original_text,
                        'translated': entry.translated_text,
                        'status': entry.status,
                        'context': entry.context
                    })
            
            logger.info(f"Exported {len(data_to_export)} entries to CSV: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            return False

    def export_json(self, output_path: str, distinct: bool = False) -> bool:
        """Export to structured JSON."""
        data_to_export = self._prepare_export_data(distinct)
        try:
            payload = {
                'version': '1.1',
                'type': 'distinct' if distinct else 'full',
                'entries': [
                    {
                        'file': e.file_path,
                        'path': e.json_path,
                        'original': e.original_text,
                        'translated': e.translated_text,
                        'status': e.status,
                        'context': e.context
                    }
                    for e in data_to_export
                ]
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Exported {len(data_to_export)} entries to JSON: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export JSON: {e}")
            return False

class TranslationImporter:
    """
    Robust importer that handles both localized (path-specific) and global (distinct) translations.
    """
    
    def __init__(self):
        self.file_specific: Dict[str, Dict[str, str]] = {}  # file -> {path: translation}
        self.global_map: Dict[str, str] = {}               # original -> translation
        self.stats = {'imported': 0, 'skipped': 0, 'errors': 0}

    def import_file(self, input_path: str) -> bool:
        """Universal importer supporting CSV and JSON."""
        if input_path.endswith('.json'):
            return self.import_json(input_path)
        return self.import_csv(input_path)

    def import_csv(self, input_path: str) -> bool:
        """Robust CSV import using field names."""
        try:
            with open(input_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self._process_row(
                        file_path=row.get('file'),
                        json_path=row.get('path'),
                        original=row.get('original'),
                        translated=row.get('translated'),
                        status=row.get('status', 'translated')
                    )
            return True
        except Exception as e:
            logger.error(f"Failed to import CSV: {e}")
            return False

    def import_json(self, input_path: str) -> bool:
        """JSON import for legacy and new versions."""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            entries = data.get('entries', [])
            for e in entries:
                self._process_row(
                    file_path=e.get('file'),
                    json_path=e.get('path'),
                    original=e.get('original'),
                    translated=e.get('translated'),
                    status=e.get('status', 'translated')
                )
            return True
        except Exception as e:
            logger.error(f"Failed to import JSON: {e}")
            return False

    def _process_row(self, file_path, json_path, original, translated, status):
        """Process a single row from any source and route to specific or global map."""
        # Sanity check: Translated MUST be a string
        if not translated or not isinstance(translated, str):
            self.stats['skipped'] += 1
            return

        # Support path-only translation mapping for legacy data compatibility
        if not original and not json_path:
            self.stats['skipped'] += 1
            return

        status = str(status).lower().strip()
        if status == 'skipped':
            self.stats['skipped'] += 1
            return

        # Handle Distinct/Global translations
        if file_path == "[DISTINCT]" or json_path == "[DISTINCT]":
            self.global_map[original] = translated
            self.stats['imported'] += 1
            return

        # Handle file-specific translations
        if file_path not in self.file_specific:
            self.file_specific[file_path] = {}
        
        self.file_specific[file_path][json_path] = translated
        self.stats['imported'] += 1

    def get_translation(self, file_path: str, json_path: str, original_text: str) -> Optional[str]:
        """
        Lookup translation with Fallback strategy:
        1. Exact file + path match
        2. Global (Distinct) match
        """
        # Step 1: Specific path
        if file_path in self.file_specific:
            if json_path in self.file_specific[file_path]:
                return self.file_specific[file_path][json_path]
        
        # Step 2: Global lookup
        return self.global_map.get(original_text)

    def get_translations_for_file(self, file_path: str) -> Dict[str, str]:
        """Backward compatibility for tests: Get all translations for a specific file."""
        return self.file_specific.get(file_path, {})

    def get_stats(self) -> dict:
        return {
            **self.stats,
            'files_impacted': len(self.file_specific),
            'global_rules': len(self.global_map)
        }
