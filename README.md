# RPGMLocalizer

RPGMLocalizer is a desktop localization tool for RPG Maker games. It extracts translatable text from game data, translates it through web-based translation endpoints, and writes the results back while protecting engine syntax, plugin identifiers, and game-critical structures.

It is built for real RPG Maker projects, not generic JSON translation. That means the parser is aware of control codes, event commands, `plugins.js`, Ruby Marshal data, note tags, nested plugin JSON, and common false-positive cases that can crash games when translated blindly.

## Highlights

- Supports RPG Maker **XP**, **VX**, **VX Ace**, **MV**, and **MZ**
- Handles both **JSON** data and **Ruby Marshal** formats
- Preserves RPG Maker control codes such as `\V[1]`, `\N[1]`, `\C[2]`, and `^`
- Protects technical strings, plugin bindings, asset names, CSS font names, and engine identifiers
- Creates backups before destructive writes
- Includes cache, glossary, regex blacklist, export/import, and word-wrap options
- Ships with a PyQt6 + qfluentwidgets desktop UI

## What It Can Process

RPGMLocalizer currently works with:

- Standard RPG Maker database files such as `Actors.json`, `Items.json`, `Skills.json`, `System.json`
- Map and event data, including dialogue, choices, comments, and many plugin command payloads
- `js/plugins.js` for MV/MZ plugin parameter localization
- `locales/*.json` style localization files used by some plugins
- Ruby Marshal files such as `.rvdata2`, `.rvdata`, and `.rxdata`

## Safety Model

The project is designed around "translate the text, not the engine".

Key protections include:

- Context-aware parser rules for event commands, plugin parameters, and note tags
- Technical string filtering for script code, eval expressions, audio config, and engine internals
- Asset/path detection to prevent image, audio, and filename corruption
- Backup creation before overwriting external game files
- Safe write flow using temporary files and atomic replace
- Strict handling for `plugins.js`, which is JavaScript wrapping a JSON array rather than plain JSON

This is especially important for RPG Maker because translating the wrong field can break:

- event flow
- plugin commands
- particle systems
- audio/image loading
- script evaluation
- map labels and internal references

## Main Features

### Translation workflow

- Project scanning with automatic data folder discovery
- Two-phase translation ordering for better consistency between database terms and map/event text
- Batch merging to reduce request count and improve context
- Multiple Google mirror support with Lingva fallback
- Request delay, timeout, and retry controls from the UI

### Translation consistency

- Persistent translation cache
- Glossary manager with plain-text and regex entries
- Regex blacklist to skip custom patterns
- Export to CSV/JSON for manual editing
- Import from CSV/JSON to reapply curated translations

### Formatting options

- VisuStella `<WordWrap>` injection for compatible MZ projects
- Vanilla auto line-wrap for projects without message plugins

### UI and usability

- Home screen for project/language selection
- Dedicated settings page
- Built-in glossary editor
- Export/import page
- Console page for pipeline logs
- Persisted application settings between runs

## Installation

### End users

Download the latest release artifact from the project's Releases page and use the package that matches your platform.

- Windows: portable executable build
- Linux: AppImage build when available
- macOS: `.app` bundle when available

No separate installer is required for portable builds.

## Run From Source

1. Install a recent Python 3 environment.
2. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

3. Start the application:

```bash
python main.py
```

## Usage

1. Launch the app.
2. Click `Browse` and select the game executable or project folder entry point.
3. Choose source and target languages.
4. Configure optional settings:
   - backups
   - cache
   - glossary
   - regex blacklist
   - export/import
   - network retry and timeout behavior
   - word-wrap behavior
5. Start the localization pipeline.
6. Watch progress in the built-in console.
7. Test the translated game with the generated backups available if rollback is needed.

## Important Notes

- Encrypted games may need to be decrypted first before their data can be localized.
- `note` field translation is optional and risky because many plugins store structured data there.
- `plugins.js` is handled carefully, but plugin-heavy games should still be tested after localization.
- Web-based translation endpoints can change behavior over time, so retry/fallback settings matter.
- This tool focuses on **safe localization**, not literal translation of every string found in a file.

## Development

### Project layout

```text
src/
  core/        Translation pipeline, parser factory, translator, cache, validation
  ui/          PyQt6 windows, interfaces, and UI components
  utils/       Backup, paths, file writing, settings storage, placeholder helpers
tests/         Automated regression and parser safety tests
```

### Test suite

Run the automated tests with:

```bash
python -m pytest -q
```

### Build/runtime dependencies

Core dependencies are declared in `requirements.txt` and currently include:

- `PyQt6`
- `PyQt6-Fluent-Widgets[full]`
- `rubymarshal`
- `deep-translator`
- `requests`
- `aiohttp`
- `pyyaml`

## Scope and Philosophy

RPGMLocalizer is intentionally conservative in high-risk areas. If a field looks like code, a plugin binding, an asset reference, or an engine identifier, the parser prefers to skip it rather than corrupt the game.

That tradeoff is deliberate: a missed string is recoverable, a broken save/load path or plugin command often is not.

## Support

If the project helps you, you can support development here:

- Patreon: https://www.patreon.com/cw/LordOfTurk

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.
