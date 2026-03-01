"""
Collection of specialized plugin parsers for popular RPG Maker plugins.
"""
import json
import logging
from typing import List, Tuple, Any, Dict
from .plugin_base import PluginParser

logger = logging.getLogger(__name__)

# --- REGISTRY ---

# All plugins now use the generic _walk parser with recursive @JSON string unboxing
_PLUGIN_PARSERS = []

def get_specialized_parser(plugin_name: str) -> PluginParser:
    """Find a specialized parser for the given plugin name."""
    for parser in _PLUGIN_PARSERS:
        if plugin_name in parser.get_plugin_names():
            return parser
    return None
