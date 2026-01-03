"""
Parser Factory for RPGMLocalizer.
Returns the appropriate parser based on file extension.
"""
import os
from typing import Optional

from .parsers.json_parser import JsonParser
from .parsers.ruby_parser import RubyParser
from .parsers.base import BaseParser


def get_parser(file_path: str, settings: dict = None) -> Optional[BaseParser]:
    """
    Get the appropriate parser for a file based on its extension.
    
    Args:
        file_path: Path to the file to parse
        settings: Pipeline settings
        
    Returns:
        Parser instance or None if no suitable parser found
    """
    ext = os.path.splitext(file_path)[1].lower()
    settings = settings or {}
    
    if ext in [".json", ".js"]:
        return JsonParser(
            translate_notes=settings.get('translate_notes', False),
            translate_comments=settings.get('translate_comments', True),
            regex_blacklist=settings.get('regex_blacklist', [])
        )
    elif ext in [".rvdata2", ".rxdata", ".rvdata"]:
        return RubyParser(
            translate_notes=settings.get('translate_notes', False),
            translate_comments=settings.get('translate_comments', True),
            regex_blacklist=settings.get('regex_blacklist', [])
        )
    
    return None


def get_supported_extensions() -> list:
    """Get list of supported file extensions."""
    return ['.json', '.rvdata2', '.rxdata', '.rvdata', '.js']


def is_supported_file(file_path: str) -> bool:
    """Check if a file is supported for translation."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in get_supported_extensions()
