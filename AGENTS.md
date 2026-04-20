# AGENTS.md - AI Orientation & Development Guide

## Project Overview
**RPGMLocalizer** is a high-performance, autonomous translation and localization suite for RPG Maker games spanning from the Ruby era (XP, VX, VX Ace) to the modern JS era (MV, MZ). It bridges the gap between raw extraction and engine-aware localization.

### Supported Engines & Data Formats
- **Ruby Era (RGSS 1/2/3)**: 
  - Files: `.rxdata` (XP), `.rvdata` (VX), `.rvdata2` (VX Ace).
  - Logic: Uses `Ruby Marshal` for serialization. Strings are often raw bytes with legacy encodings (Shift-JIS/cp932).
- **JS Era (MV/MZ)**: 
  - Files: `.json`, `.js`.
  - Logic: Standard JSON structures but with complex nested objects for event commands and plugin parameters.

## Core Architecture: The "Tungsten" Pipeline
The project uses a high-fidelity translation pipeline that prioritizes engine stability over simple string replacement.

### 1. Extraction (The Parser Layer)
- **`JsonParser`**: Handles MV/MZ. Uses `StructuredJsonExtractor` for deterministic mapping of core database files and a heuristic recursive walker for plugin parameters.
- **`RubyParser`**: Handles XP/VX/VXA. Walks the Marshal object tree. It uses a custom `RubyStringInfo` wrapper to preserve original byte encodings.
- **`JS_AST_Extractor`**: Uses `tree-sitter-javascript` to perform deep analysis of script files, identifying translatable "safe sinks" (e.g., `drawText`).

### 2. Shielding: Motor-Aware Protection (syntax_guard_rpgm)
Instead of fragile regex placeholders or heavy HTML parsing, we use **4-Phase Fuzzy Recovery**:
- **Unicode Token Shield (`src/core/syntax_guard_rpgm.py`)**: Pure Unicode tokens `⟦RPGM{hash}_{type}_{id}⟧` that are:
  - Lightweight (no HTML wrapping overhead)
  - Google-resistant (survive text-mode translation)
  - Fuzzy-recoverable (handle mutations: spacing, bracket substitution, case changes)
- **4-Phase Restoration (Battle-Tested)**: RenLocalizer v3.3+ architecture adapted to RPG Maker:
  - **Phase 0**: Unicode bracket restoration with case-insensitive suffix matching
  - **Phase 0.1**: Bracket-substituted token recovery (`[...` or `{...` or `(...` mutations)
  - **Phase 1**: Standard longest-first token mapping
  - **Phase 2**: Proportional injection fallback for completely missing tokens
- **Motor-Aware Strategy**:
  - **Google (text-mode)**: Pure tokens, no HTML (default, v0.6.5+)
  - **HTML-Supporting Motors** (DeepL, LibreTranslate, future): `<span translate="no">⟦token⟧</span>` wrapping via `use_html_protection=True`
- **GET-Safe Slicing**: Bypasses 414 errors by automatically partitioning batches into 2000-character URL-safe chunks.
- **Why This Works**: Prevents Google/translators from corrupting game codes while maintaining 28x speed advantage over HTMLShield + <8% accuracy tradeoff (acceptable for game text where code integrity > perfect case match)

### 3. Buffering & Batching
- **`src/core/text_merger.py`**: Merges short lines (choices, name tags) into larger blocks using `<b translate="no">⟦B⟧</b>` as resilient separators. This saves API costs and provides context for the translator.

### 4. Verification & Hardening
- **`is_safe_to_translate`**: A multi-layered heuristic that detects SE/BGM filenames, internal symbols, and technical identifiers.
- **Technical Invariants**: Post-translation checks that ensure the structure (array length, nested object keys) remains identical to the original.
- **Asset Registry**: Scans the project's `audio` and `img` folders to build an allowlist of file names that must NEVER be translated.

## Key Component Directory
- `src/core/lexer.py`: The single source of truth for RPG Maker syntax/codes (Lark grammar).
- `src/core/translator.py`: Concurrent multi-endpoint Google/Lingva racing engine with motor-aware protection branching.
- **`src/core/syntax_guard_rpgm.py` (v0.6.5+)**: 4-phase fuzzy recovery token shield (28x faster, battle-tested RenLocalizer pattern). **Recommended**.
- `src/utils/html_shield.py` (legacy): HTMLShield token system (100% accurate, slower). **Fallback only** (use_syntax_guard=False).
- `src/utils/file_ops.py`: Atomic, cross-platform and safe I/O (`safe_write`).
- `src/utils/paths.py`: Abstracted resource path handling for bundled environments.

## Must-Follow Development Constraints
- **Target Environment**: Python 3.12+. Use modern features like `match-case`, `asyncio.TaskGroup`, and `|` (Union) for type hints.
- **Language Policy**: Logic/Code/Commits: **English** | Rationale/Turkish UI discussions: **Turkish**.
- **Change Policy**: Applies surgical, additive-first edits. Never rewrite entire files unless requested.
- **Type Safety**: ALL function signatures MUST have type hints (Prefer `list`, `dict`, `int | None` over `typing` aliases).
- **Paths & I/O**: 
  - ALL asset/resource loading MUST use `resource_path()` from `src/utils/paths.py`.
  - Use `safe_write` from `src/utils/file_ops.py` for all file writes.
- **Safety Protocol**: Always use `BackupManager` before destructive operations to game data.
- **Naming & UI**: Use the term **"Yerelleştirme"** (never "Türkçeleştirme") for user-facing features. UI uses PyQt6 + `qfluentwidgets`.

## Change Safety Rules
- **Technical Guards**: 
  - Parsers MUST NOT translate technical strings, plugin bindings, CSS font names, or identifiers (e.g., `symbol`, `eval`, `se`, `bgm`).
  - Always enforce `is_safe_to_translate`, `_is_technical_string`, and `NON_TRANSLATABLE_KEY_HINTS` checks.
- **Word-Wrap**: Auto Word-Wrap (`<WordWrap>`) injection MUST target standard dialogue, ignoring scripts and plugin blocks.
- **Unicode Token Separators**: Use `⟦M⟧` or `⟦B⟧` based tags for batch/merge separators. **NEVER** use HTML `<!-- -->` comments; Google strips them in both text and html modes. Tokens are motor-aware (text-mode pure tokens for Google, HTML span-wrapped for DeepL/LibreTranslate).
- **Parsing Priority**: 
  1. `Lexer` identifies segments (Code vs Text).
  2. `syntax_guard_rpgm.protect_for_translation()` converts to tokens (motor-aware: pure tokens or HTML spans).
  3. `Translator` joins items using resilient Unicode separators for Google API.
  4. `syntax_guard_rpgm.restore_from_translation()` applies 4-phase recovery (no BeautifulSoup needed).

## AI Strategy & Gotchas
- **Encoding Crisis**: RPG Maker XP/VX often uses Shift-JIS. Always use `_safe_decode_ruby_string()` to detect encoding.
- **Plugins.js**: It is NOT pure JSON. It's a JS variable declaration (`var $plugins = [...]`). Always use specialized logic to handle it.
- **Single-Bracket Tags**: Codes like `[sad]` are protected by both the Lexer AND `syntax_guard_rpgm`. If the Lexer misses a code, update the grammar in `src/core/lexer.py` rather than creating regex hacks.
- **Performance**: Token restoration via `syntax_guard_rpgm` is 28x faster than BeautifulSoup parsing. Never downgrade to DOM parsing without benchmarking.
- **Fuzzy Recovery Boundaries**: Phase 2 injection uses word boundary detection (±20 char window) to avoid mid-word token placement. Trust the heuristics—they've been battle-tested.

## AI Assistant Protocol
1. **Analyze First**: Check which engine (Ruby vs JS) the task targets.
2. **Grammar First**: If the task involves "protecting" a new tag, check `src/core/lexer.py`.
3. **Safety First**: Prioritize stability over speed; ensure tokens (`⟦RPGM...⟧`) are correctly mapped before restoration.
4. **Use syntax_guard_rpgm**: Never use generic placeholders (`[0]`, `{0}`). Always leverage the motor-aware `syntax_guard_rpgm` token system with 4-phase fuzzy recovery.
