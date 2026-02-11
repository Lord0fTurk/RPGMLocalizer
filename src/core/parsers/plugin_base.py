"""
Base classes for specialized plugin parsers.
"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Any, Dict

class PluginParser(ABC):
    """
    Abstract base class for specialized plugin parsers.
    Handles extraction from specific plugin parameters structure.
    """
    
    @abstractmethod
    def get_plugin_names(self) -> List[str]:
        """Return list of plugin names this parser handles (e.g. ['YEP_QuestJournal'])."""
        pass
        
    @abstractmethod
    def extract_parameters(self, parameters: Dict[str, Any], path_prefix: str) -> List[Tuple[str, str, str]]:
        """
        Extract translatable text from plugin parameters.
        
        Args:
            parameters: The 'parameters' dictionary of the plugin.
            path_prefix: The base path to locate this plugin in the file.
            
        Returns:
            List of (path, text, context_tag)
        """
        pass

class GenericPluginParser(PluginParser):
    """Fallback parser for unknown plugins."""
    
    def get_plugin_names(self) -> List[str]:
        return []
        
    def extract_parameters(self, parameters: Dict[str, Any], path_prefix: str) -> List[Tuple[str, str, str]]:
        # This logic is actually handled by the main JsonParser's generic walk.
        # This class acts as a placeholder or interface definition.
        return []
