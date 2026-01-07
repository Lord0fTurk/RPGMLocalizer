# Changelog

All notable changes to this project will be documented in this file.

## [v0.5.1] - 2026-01-06

### Added
- **Performance Settings**:
    - Added "Batch Processing Size" slider (50-500) to control translation chunk size.
    - Added "Concurrent Requests" slider (5-50) to control parallel translation threads.
    - **Major Performance Boost**:
    - **Parallel Extraction**: Multi-threaded file parsing to speed up project scanning.
    - **Parallel Save**: Concurrent file saving and backup creation.
    - **Optimized Throughput**: Removed redundant batching, allowing the translation engine to fully utilize concurrency settings.
    - **Dynamic Slicing**: Increased character limit per request to 4500 to reduce total HTTP requests.
    - Zlib decompression support for extracting text from compressed Ruby scripts.
    - Heuristic-based filtering to identify translatable strings (spaces, non-ASCII characters).
    - Automatic exclusion of variable names, file paths, and code identifiers.
- **Extended Text Location Support**:
    - `displayName`: Map display names now extracted and translated.
    - `currencyUnit`: Currency unit from System.json.
    - Code 105: Show Scrolling Text Header support for plugin extensions.
    - Comprehensive coverage of all known RPG Maker MV/MZ text locations.

### Fixed
- **App Crash on Repeated Runs**: Fixed a `RuntimeError: wrapped C/C++ object` crash that occurred when starting a second translation without restarting the app.
- **Filename Translation**: Fixed an issue where filenames (e.g., `PopUp-Arrow`) were incorrectly translated.
- **Script-Based Dialogue Extraction**: Fixed logic to correctly identify and extract dialogue from `$gameVariables.setValue` commands while excluding filenames.
- **Recursive JSON Parsing** (`plugins.js`):
    - Deep parsing of nested JSON strings within plugin parameters.
    - Expanded extraction for VisuMZ, DKTools, and other complex plugins.
- **DKTools Localization Support** (`locales/*.json`):
    - Automatic detection and parsing of locale plugin files.
    - UI terms, menu text, and system messages now properly extracted.
- **Enhanced Technical String Filtering**:
    - Expanded protection for more file extensions: `.gif`, `.bmp`, `.tga`, `.svg`, `.mid`, `.mp4`, `.avi`, `.rpgmvp`, `.rpgmvo`, `.rpgmvm`, `.rpgmvw`.
- **Silent Translation Skips**: Fixed an issue where batches would be silently skipped on failure by implementing item-level retry logic.
- **Stability & Robustness Improvements**:
    - Added recursion depth limits to `RubyParser` (prevents crashes on complex circular data).
    - Improved encoding detection (Shift-JIS prioritization) for older RPG Maker versions.
    - Optimized event loop management for smoother consecutive runs.
    - Enhanced thread lifecycle safety in UI to prevent random crashes.
    - Refined string filtering to prevent false negatives in short localized text.
- Fixed Ruby escape character handling in `_apply_scripts_translation` to prevent syntax errors.
- Fixed `plugins.js` save error caused by deeply nested JSON paths.

## [v0.5.0] - 2024-05-23


### Added
- **Game Engine Support**:
    - Complete support for RPG Maker MV and MZ (`.json` files).
    - Complete support for RPG Maker XP, VX, and VX Ace (`.rvdata2`, `.rxdata` via Ruby Marshal).
- **Text Processing**:
    - Intelligent **Placeholder Protection**: Preserves control codes like `\C[0]`, `\N[1]`, `\V[10]` during translation.
    - **Resume Capability**: Skips already translated sentences using a persistent local cache.
    - **Glossary System**: Define custom term mappings (`glossary.txt`) to enforce specific translations.
    - **Speaker Name Extraction**: Extract and translate speaker names in MZ "Show Text" (Code 101) events.
- **User Interface**:
    - Modern **Fluent Design** UI using PyQt6 and qfluentwidgets.
    - **Regex Blacklist**: Users can define regex patterns in Settings to exclude specific lines from translation (e.g., file paths, internal commands).
    - **Console Log**: Real-time log viewer within the app.
- **System**:
    - **Automatic Backups**: Safely backs up files before modifying.
    - **Export/Import**: Ability to export text to CSV/JSON for manual translation and re-import.

### Fixed
- Fixed issues with `Show Text` commands where speaker names were not being detected.
- Fixed crashes caused by network timeouts or invalid JSON responses from translation services.
- Resolved UI freezing issues by moving heavy processing to background threads.
