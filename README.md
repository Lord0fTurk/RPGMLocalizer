# RPGMLocalizer

**RPGMLocalizer** is a powerful automated translation tool designed for RPG Maker games. It extracts text from game data, translates it using high-quality machine translation services (Google Translate), and re-inserts it back into the game files, all while preserving game logic, control codes, and scripts.

![RPGMLocalizer Screenshot](https://via.placeholder.com/800x450?text=RPGMLocalizer+Screenshot)

## Features

-   **Wide Support**: Supports RPG Maker **XP**, **VX**, **VX Ace** (Ruby Marshal) and **MV**, **MZ** (JSON).
-   **Smart Translation**: Automatically handles batching, caching, and concurrent requests for optimal speed and quality.
-   **Context Awareness**:
    -   Preserves RPG Maker control codes (e.g., `\V[1]`, `\N[1]`, `\C[1]`).
    -   Extracts and restores "Show Text" speaker names (MZ Code 101).
    -   Handles plugin parameters (`js/plugins.js`) for MV/MZ.
-   **User Control**:
    -   **Regex Filtering**: Define custom blacklist patterns to skip translating specific text (e.g., file paths, internal keys).
    -   **Glossary Support**: Ensure specific terms are translated consistently or left untranslated.
    -   **Translation Memory**: Built-in cache system prevents re-translating previous sentences, saving time and bandwidth.
-   **Safe & Secure**:
    -   **Automatic Backups**: Creates backups of modified files before saving.
    -   **Robust Error Handling**: Prevents pipeline crashes from individual errors.

## Installation

1.  Download the latest release (`.exe`) from the [Releases](https://github.com/LordOfTurk/RPGMLocalizer/releases) page.
2.  Extract the archive to a folder.
3.  Run `RPGMLocalizer.exe`.

> **Note**: No installation is required. The application is portable.

## Usage

1.  **Select Game**: Click the "Browse" button and select the **Game Executable** (e.g., `Game.exe`). The tool will automatically detect the correct data folder.
2.  **Select Languages**:
    -   **Source**: Leave as "Auto Detect" or specify the game's original language.
    -   **Target**: Select the language you want to translate the game into.
3.  **Configure (Optional)**:
    -   Go to **Settings** to enable/disable backups, cache, or add regex filters.
    -   Go to **Export/Import** if you want to export text to CSV/JSON for manual editing.
4.  **Start Translate**: Click the **Run Translate** button on the main screen.
5.  **Wait**: The console will show progress. Once finished, launch the game to see the translation!

## Support

If you find this tool useful, consider supporting development on Patreon:

[![Support on Patreon](https://img.shields.io/badge/Support-Patreon-orange?style=for-the-badge&logo=patreon)](https://www.patreon.com/c/LordOfTurk)

## License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.

Copyright © 2024 LordOfTurk. All rights reserved.
