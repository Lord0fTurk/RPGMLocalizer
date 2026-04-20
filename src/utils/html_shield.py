import logging
import re
from typing import Dict, Tuple
from src.core.lexer import RPGLexer

logger = logging.getLogger(__name__)

class HTMLShield:
    """
    Unicode Token Shield for RPG Maker code protection.
    
    Uses ⟦Tn⟧ (Mathematical Angle Brackets, U+27E6/U+27E7) tokens
    which are translation-engine-safe across all Google endpoints
    without requiring format=html mode.
    
    Adapted from RenLocalizer's battle-tested ⟦RLPH⟧ token system.
    """
    
    def __init__(self):
        self.lexer = RPGLexer()
        
    def shield_with_map(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Replaces RPG Maker codes with ⟦Tn⟧ tokens, returns (protected_text, token_map)."""
        if not text:
            return "", {}

        from src.core.constants import TOKEN_LINE_BREAK
        processed_text = text.replace('\n', TOKEN_LINE_BREAK)

        try:
            segments = self.lexer.tokenize(processed_text)
        except Exception as e:
            logger.error(f"Lexer failed. Error: {e}")
            return processed_text, {}

        token_map: Dict[str, str] = {}
        parts: list[str] = []
        token_counter = 0

        for seg in segments:
            if seg.is_code:
                token = f"⟦T{token_counter}⟧"
                token_map[token] = seg.content
                parts.append(token)
                token_counter += 1
            else:
                parts.append(seg.content)
        
        return "".join(parts), token_map

    def unshield_with_map(self, shielded_text: str, token_map: Dict[str, str]) -> str:
        """Restores ⟦Tn⟧ tokens back to original RPG Maker codes."""
        if not shielded_text:
            return ""
            
        if not token_map:
            return shielded_text

        # 1. Fuzzy Repair: Fix space-mangled and bracket-substituted tokens
        from src.utils.placeholder import fuzzy_repair_tokens
        result_text = fuzzy_repair_tokens(shielded_text, token_map)

        # 2. Sequential Restoration (longest tokens first to avoid partial matches)
        tokens = sorted(token_map.keys(), key=len, reverse=True)
        for token in tokens:
            original = token_map[token]
            result_text = result_text.replace(token, original)

        # 3. Final Line Break Restoration
        from src.core.constants import TOKEN_LINE_BREAK
        result_text = result_text.replace(TOKEN_LINE_BREAK, '\n')
            
        return result_text
