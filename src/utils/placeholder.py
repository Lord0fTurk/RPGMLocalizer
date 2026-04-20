import re
import logging
from typing import Dict, Tuple, List

from src.core.constants import TOKEN_LINE_BREAK

logger = logging.getLogger(__name__)

# =============================================================================
# UNICODE TOKEN SHIELD: PLACEHOLDER VERIFICATION & RECOVERY
# Adapted from RenLocalizer's battle-tested ⟦⟧ token system
# =============================================================================

def validate_restoration(original: str, restored: str, token_map: Dict[str, str]) -> Tuple[bool, List[str]]:
    """
    Validate that all critical RPG Maker tokens are present in the restored text.
    Uses the ⟦Tn⟧ token structure.
    """
    if not token_map:
        return True, []

    missing_tokens = []
    
    # We check if the CONTENT of the tokens is present in the restored text.
    # Note: tokens were already restored in the unshielding phase.
    for token, original_content in token_map.items():
        # Check if original content is missing from restored
        # We use a normalized check (ignore spaces if it's RM code)
        clean_content = original_content.replace(" ", "").lower()
        clean_restored = restored.replace(" ", "").lower()
        
        if clean_content not in clean_restored:
            # Check if it's a decorative code (don't fail for color/icon changes)
            if original_content.upper().startswith(r'\C[') or original_content.upper().startswith(r'\I['):
                continue
            missing_tokens.append(original_content)
            
    return len(missing_tokens) == 0, missing_tokens


def fuzzy_repair_tokens(restored: str, token_map: Dict[str, str]) -> str:
    """
    Fuzzy Recovery for ⟦Tn⟧ tokens.
    
    Handles common translation engine mangling:
      - Space insertion:    ⟦ T 0 ⟧  → ⟦T0⟧
      - Bracket substitution: [T0], (T0), 【T0】, {T0} → ⟦T0⟧
      - Case change:        ⟦t0⟧     → ⟦T0⟧
    
    Adapted from RenLocalizer's multi-phase recovery system.
    """
    if not restored or not token_map:
        return restored

    result = restored
    
    # Phase 1: Fix space-mangled tokens inside ⟦⟧
    # ⟦ T 0 ⟧ → ⟦T0⟧, ⟦T 10⟧ → ⟦T10⟧
    spaced_pattern = re.compile(r'⟦\s*[tT]\s*(\d+)\s*⟧')
    
    def fix_spaced(match: re.Match) -> str:
        token_id = match.group(1)
        expected_token = f"⟦T{token_id}⟧"
        if expected_token in token_map:
            return expected_token
        return match.group(0)

    result = spaced_pattern.sub(fix_spaced, result)
    
    # Phase 2: Bracket-substituted recovery
    # Google may replace ⟦⟧ with [], (), {}, 【】
    bracket_sub_pattern = re.compile(
        r'[\[(\{【]\s*[tT]\s*(\d+)\s*[\])\}】]'
    )
    
    def fix_bracket_sub(match: re.Match) -> str:
        token_id = match.group(1)
        expected_token = f"⟦T{token_id}⟧"
        if expected_token in token_map:
            return expected_token
        return match.group(0)
    
    result = bracket_sub_pattern.sub(fix_bracket_sub, result)

    return result
