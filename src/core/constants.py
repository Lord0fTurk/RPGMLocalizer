from dataclasses import dataclass, field
from typing import Dict, Any, Optional

# --- Constants ---

# Separator Tokens
# CRITICAL: Must be stable through Google Translate web endpoints
# Web-based translation (not API) requires simple, unique text patterns
# Format: Pipes + unique ID = minimal corruption risk
TOKEN_BATCH_SEPARATOR = "\n|||XYZ|||\n"
# IMPORTANT: TOKEN_LINE_BREAK must NOT match any pattern in RPGM_PATTERNS (placeholder.py)
# Previous formats:
# - [[XRPYX_LB_XRPYX]]: matched by \[\[[^\]]+\]\] regex (corrupted by placeholder system)
# - |||XRPYXLB|||: too long, Google sometimes adds spaces
# - <XRPYX_LB>: XML tags don't work well with web-based translate endpoints
# Current: Short pipe format for maximum stability
TOKEN_LINE_BREAK = "|||XLB|||"

# Regex Patterns (Pre-compiled elsewhere, documented here)
# Used to split batch responses from Google
REGEX_BATCH_SPLIT = r'\s*\|\|\|XYZ\|\|\|\s*'

# Used to split merged dialogue lines
REGEX_LINE_SPLIT = r'\s*\|\|\|XLB\|\|\|\s*'

# Default Configuration
DEFAULT_BATCH_SIZE = 1  # Disable merge for maximum stability (slower but safer)
DEFAULT_CONCURRENCY = 20
DEFAULT_TIMEOUT = 15
DEFAULT_MAX_CHARS = 2000
DEFAULT_USE_MULTI_ENDPOINT = True
DEFAULT_ENABLE_LINGVA_FALLBACK = True
DEFAULT_REQUEST_DELAY_MS = 150
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_RETRIES = 3
DEFAULT_MIRROR_MAX_FAILURES = 5
DEFAULT_MIRROR_BAN_TIME = 120
DEFAULT_RACING_ENDPOINTS = 2

# Translator-specific limits
TRANSLATOR_MAX_SAFE_CHARS = 4500  # Safe limit for single request batch
TRANSLATOR_MAX_SLICE_CHARS = 2000  # Fallback slice limit
TRANSLATOR_RECURSION_MAX_DEPTH = 100  # Max recursion depth for parsers

# Text Merger Configuration
TEXT_MERGER_MAX_SAFE_CHARS = 4000  # Safe limit for merged requests (slightly lower than TRANSLATOR_MAX_SAFE_CHARS)

# Ruby Parser Configuration
RUBY_ENCODING_FALLBACK_LIST = ['utf-8', 'shift_jis', 'cp1252', 'latin-1']
RUBY_KEY_ENCODING_FALLBACK_LIST = ['utf-8', 'shift_jis', 'cp1252']

# --- Data Transfer Objects (DTOs) ---

@dataclass
class TranslationTask:
    """Represents a single unit of work for the translator."""
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Metadata includes: file, path, original, tag, is_merged, block_size, glossary_map

@dataclass
class TranslationResult:
    """Represents the outcome of a translation task."""
    original_text: str
    translated_text: str
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    source_lang: str = "auto"
    target_lang: str = "en"
