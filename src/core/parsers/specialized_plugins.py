"""
Collection of specialized plugin parsers for popular RPG Maker plugins.
"""
import json
import logging
from typing import List, Tuple, Any, Dict
from .plugin_base import PluginParser

logger = logging.getLogger(__name__)

class YanflyQuestJournalParser(PluginParser):
    """
    Parser for YEP_QuestJournal (Yanfly Quest Journal System).
    Extracts quest titles, descriptions, and objectives.
    """
    
    def get_plugin_names(self) -> List[str]:
        return ["YEP_QuestJournal", "YEP_QuestJournalSystem"]

    def extract_parameters(self, parameters: Dict[str, Any], path_prefix: str) -> List[Tuple[str, str, str]]:
        extracted = []
        
        # Determine strict or loose parsing based on known keys
        # Yanfly parameters are often flat strings that are actually JSON
        
        # 1. Main Menu Text
        menu_keys = ['Quest Journal Text', 'Quest Title Text', 'Quest Description Text', 
                     'Quest Objectives Text', 'Cancel Text', 'Empty Text']
        
        for key in menu_keys:
            if key in parameters:
                val = parameters[key]
                if val and isinstance(val, str):
                    extracted.append((f"{path_prefix}.{key}", val, "system"))
                    
        return extracted    

# --- REGISTRY ---

_PLUGIN_PARSERS = [
    YanflyQuestJournalParser(),
]

def get_specialized_parser(plugin_name: str) -> PluginParser:
    """Find a specialized parser for the given plugin name."""
    for parser in _PLUGIN_PARSERS:
        if plugin_name in parser.get_plugin_names():
            return parser
    return None
