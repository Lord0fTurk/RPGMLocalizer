"""
CSV Export/Import for translations.
Allows translators to edit translations in spreadsheet software.
"""
import csv
import json
import os
from typing import List, Tuple, Dict, Optional
from pathlib import Path
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class TranslationEntry:
    """Represents a single translatable text entry."""
    file_path: str
    json_path: str
    original_text: str
    translated_text: str = ""
    status: str = "pending"  # pending, translated, reviewed, skipped


class TranslationExporter:
    """
    Exports extracted text to CSV for external editing.
    """
    
    CSV_COLUMNS = ['file', 'path', 'original', 'translated', 'status']
    
    def __init__(self):
        self.entries: List[TranslationEntry] = []
    
    def add_entries_from_file(self, file_path: str, extractions: List[Tuple[str, str]]):
        """
        Add extracted text entries from a file.
        
        Args:
            file_path: Source file path
            extractions: List of (json_path, text) tuples from parser
        """
        for json_path, text in extractions:
            entry = TranslationEntry(
                file_path=file_path,
                json_path=json_path,
                original_text=text
            )
            self.entries.append(entry)
    
    def export_csv(self, output_path: str, include_header: bool = True) -> bool:
        """
        Export all entries to a CSV file.
        
        Args:
            output_path: Path for the output CSV file
            include_header: Whether to include column headers
            
        Returns:
            True if export succeeded
        """
        try:
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                
                if include_header:
                    writer.writerow(self.CSV_COLUMNS)
                
                for entry in self.entries:
                    writer.writerow([
                        entry.file_path,
                        entry.json_path,
                        entry.original_text,
                        entry.translated_text,
                        entry.status
                    ])
            
            logger.info(f"Exported {len(self.entries)} entries to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            return False
    
    def export_json(self, output_path: str) -> bool:
        """
        Export all entries to a JSON file.
        More structured than CSV, preserves data types.
        """
        try:
            data = {
                'version': '1.0',
                'entries': [
                    {
                        'file': e.file_path,
                        'path': e.json_path,
                        'original': e.original_text,
                        'translated': e.translated_text,
                        'status': e.status
                    }
                    for e in self.entries
                ]
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Exported {len(self.entries)} entries to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export JSON: {e}")
            return False
    
    def get_stats(self) -> dict:
        """Get export statistics."""
        status_counts = {}
        for entry in self.entries:
            status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
        
        return {
            'total_entries': len(self.entries),
            'unique_files': len(set(e.file_path for e in self.entries)),
            'status_counts': status_counts
        }


class TranslationImporter:
    """
    Imports translations from CSV or JSON files.
    """
    
    def __init__(self):
        self.translations: Dict[str, Dict[str, str]] = {}  # file_path -> {json_path: translated}
        self.stats = {'imported': 0, 'skipped': 0, 'errors': 0}
    
    def import_csv(self, input_path: str, has_header: bool = True) -> bool:
        """
        Import translations from a CSV file.
        
        Args:
            input_path: Path to the CSV file
            has_header: Whether the CSV has a header row
            
        Returns:
            True if import succeeded
        """
        try:
            with open(input_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                
                if has_header:
                    next(reader)  # Skip header
                
                for row in reader:
                    if len(row) < 4:
                        self.stats['errors'] += 1
                        continue
                    
                    file_path, json_path, original, translated = row[:4]
                    status = row[4] if len(row) > 4 else 'translated'
                    
                    # Skip entries marked as skipped or without translation
                    if status == 'skipped' or not translated.strip():
                        self.stats['skipped'] += 1
                        continue
                    
                    # Store translation
                    if file_path not in self.translations:
                        self.translations[file_path] = {}
                    
                    self.translations[file_path][json_path] = translated
                    self.stats['imported'] += 1
            
            logger.info(f"Imported {self.stats['imported']} translations from {input_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to import CSV: {e}")
            return False
    
    def import_json(self, input_path: str) -> bool:
        """
        Import translations from a JSON file.
        """
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            entries = data.get('entries', [])
            
            for entry in entries:
                file_path = entry.get('file', '')
                json_path = entry.get('path', '')
                translated = entry.get('translated', '')
                status = entry.get('status', 'translated')
                
                if status == 'skipped' or not translated.strip():
                    self.stats['skipped'] += 1
                    continue
                
                if file_path not in self.translations:
                    self.translations[file_path] = {}
                
                self.translations[file_path][json_path] = translated
                self.stats['imported'] += 1
            
            logger.info(f"Imported {self.stats['imported']} translations from {input_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to import JSON: {e}")
            return False
    
    def get_translations_for_file(self, file_path: str) -> Dict[str, str]:
        """Get all translations for a specific file."""
        return self.translations.get(file_path, {})
    
    def get_all_translations(self) -> Dict[str, Dict[str, str]]:
        """Get all imported translations."""
        return self.translations
    
    def get_stats(self) -> dict:
        """Get import statistics."""
        return {
            **self.stats,
            'files_with_translations': len(self.translations)
        }


def merge_translation_files(files: List[str], output_path: str) -> bool:
    """
    Merge multiple translation CSV/JSON files into one.
    Later files take precedence for duplicate entries.
    """
    importer = TranslationImporter()
    
    for file_path in files:
        if file_path.endswith('.json'):
            importer.import_json(file_path)
        else:
            importer.import_csv(file_path)
    
    # Export merged result
    exporter = TranslationExporter()
    for file_path, translations in importer.get_all_translations().items():
        for json_path, translated in translations.items():
            entry = TranslationEntry(
                file_path=file_path,
                json_path=json_path,
                original_text="",  # Original not preserved in merge
                translated_text=translated,
                status='translated'
            )
            exporter.entries.append(entry)
    
    if output_path.endswith('.json'):
        return exporter.export_json(output_path)
    else:
        return exporter.export_csv(output_path)
