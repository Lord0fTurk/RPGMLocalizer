# --- RPG Maker Specific Tokens (Multilayer Ghost Tokens) ---
import re

# Layer 1: Universal Line Break Protection (Managed by HTMLShield)
TOKEN_LINE_BREAK = "\uE000"
REGEX_LINE_SPLIT = r'\uE000'

# Layer 2: Pipeline Batching (Managed by TranslationPipeline)
TOKEN_BATCH_SEPARATOR = "\uE001"
# ASCII separator — Google-safe (pipe chars survive text-mode translation intact)
# Replaces the old ⟦_S_⟧ Unicode tokens which Google sometimes mangled to '?'
SAFE_BATCH_SEPARATOR = '\n|||RPGMSEP_S|||\n'
# Matches: |||RPGMSEP_S||| (primary) + legacy Unicode variants ⟦_S_⟧/[_S_]/etc. + PUA
REGEX_BATCH_SPLIT = r'\s*\n*\s*\|\|\|RPGMSEP_S\|\|\|\s*\n*\s*|' \
                    r'\s*\n*\s*[?\[(\{【⟦]\s*_\s*[sS]\s*_\s*[?\])\}】⟧]\s*\n*\s*|' \
                    r'\s*\uE001\s*'

# Layer 3: Cross-Event Merging (Managed by TextMerger)
TOKEN_MERGE_SEPARATOR = "\uE002"
# ASCII separator — Google-safe
SAFE_MERGE_SEPARATOR = '\n|||RPGMSEP_M|||\n'
# Matches: |||RPGMSEP_M||| (primary) + legacy Unicode variants + PUA
REGEX_MERGE_SPLIT = r'\s*\n*\s*\|\|\|RPGMSEP_M\|\|\|\s*\n*\s*|' \
                    r'\s*\n*\s*[?\[(\{【⟦]\s*_\s*[mM]\s*_\s*[?\])\}】⟧]\s*\n*\s*|' \
                    r'\s*\uE002\s*'

# Layer 4: Parser-Internal Bundling (Managed by RubyParser/JsonParser)
TOKEN_INTERNAL_MERGE = "\uE003"
# ASCII separator — Google-safe
SAFE_INTERNAL_MERGE = '\n|||RPGMSEP_I|||\n'
# Matches: |||RPGMSEP_I||| (primary) + legacy Unicode variants + PUA
REGEX_INTERNAL_MERGE = r'\s*\n*\s*\|\|\|RPGMSEP_I\|\|\|\s*\n*\s*|' \
                       r'\s*\n*\s*[?\[(\{【⟦]\s*_\s*[iI]\s*_\s*[?\])\}】⟧]\s*\n*\s*|' \
                       r'\s*\uE003\s*'


# --- General Configuration ---
DEFAULT_BATCH_SIZE = 100
DEFAULT_CONCURRENCY = 12  # Reduced from 20: lower IP-pressure on Google endpoints
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_RETRIES = 3
DEFAULT_REQUEST_DELAY_MS = 100
DEFAULT_MAX_CHARS = 10000
TEXT_MERGER_MAX_SAFE_CHARS = 10000

# Security: GET requests have URL length limits (approx 2000-4000 chars)
TRANSLATOR_GET_SAFE_LIMIT = 2000 
TRANSLATOR_MAX_SAFE_CHARS = 12000
TRANSLATOR_MAX_SLICE_CHARS = 2000  # Sync with GET limit
TRANSLATOR_RECURSION_MAX_DEPTH = 50

# --- Endpoint Racing & Mirror Configuration ---
DEFAULT_USE_MULTI_ENDPOINT = True
DEFAULT_ENABLE_LINGVA_FALLBACK = True
DEFAULT_MIRROR_MAX_FAILURES = 5
DEFAULT_MIRROR_BAN_TIME = 120   # 2-minute cooldown (was 3600); mirrors recover quickly after a soft ban
DEFAULT_RACING_ENDPOINTS = 1    # 1 endpoint at a time to prevent cascade bans (was 2)

# --- Google Endpoint Hardening (ported from RenLocalizer v2.8.13) ---
# Per-request headers merged over the session's rotating User-Agent.
# Since Feb 2026 Google rejects bare-UA clients with 429 even at low
# volume; these browser-grade headers are the confirmed minimal set
# that restores access.
GOOGLE_BROWSER_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://translate.google.com/",
    "Cookie": "CONSENT=YES+cb",
}

# Alternate Google endpoint family (/translate_a/t, Chrome-dictionary
# client). Keeps serving traffic while /translate_a/single is IP-range
# blocked. Response shape differs:
#   sl set  -> ["translation"]
#   sl=auto -> [["translation", "detected_lang"]]
GOOGLE_CLIENTS5_ENDPOINT = "https://clients5.google.com/translate_a/t"

# Third Google-family route: TranslateWebserverUi RPC layer (rpcid MkEWBc).
# Fully separate pipeline from both /translate_a/single and clients5.
# Response is a length-prefixed envelope body; translation lives in
# inner[1][0][0][5] sentences, plain strings at inner[1][0][0].
GOOGLE_BATCHEXECUTE_ENDPOINT = (
    "https://translate.google.com/_/TranslateWebserverUi/data/batchexecute"
)

# IP-level 429 circuit breaker: after this many consecutive 429s Google has
# flagged the client IP — all mirror rotation is pointless until the flag
# decays, so requests pause for RATE_LIMIT_LONG_COOLDOWN seconds instead of
# hammering every host in a tight loop.
RATE_LIMIT_CIRCUIT_BREAKER_THRESHOLD = 6
RATE_LIMIT_LONG_COOLDOWN = 300
# While the breaker is active, primaries are retried at most once per this
# interval (a single request probes whether the IP flag has decayed).
RATE_LIMIT_PRIMARY_PROBE_INTERVAL = 300

# --- Safety & Recognition ---
# Non-translatable key patterns
NON_TRANSLATABLE_KEYS = {
    'name', 'id', 'symbol', 'icon_index', 'color', 
    'switch_id', 'variable_id', 'common_event_id',
    'animation_id', 'bgm', 'bgs', 'me', 'se'
}

# --- AI & Translation Constants (ported from RenLocalizer) ---
AI_DEFAULT_TEMPERATURE = 0.3
AI_DEFAULT_TIMEOUT = 120  # seconds
AI_LOCAL_TIMEOUT = 180    # seconds, for local LLMs
AI_DEFAULT_MAX_TOKENS = 2048
AI_MAX_RETRIES = 3
AI_LOCAL_URL = "http://localhost:11434/v1"  # Default Ollama URL

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

