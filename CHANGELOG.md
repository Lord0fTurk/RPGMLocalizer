# Changelog

All notable changes to this project will be documented in this file.

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
