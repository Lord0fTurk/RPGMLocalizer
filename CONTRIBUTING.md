# Contributing to RPGMLocalizer

First off, thank you for considering contributing to RPGMLocalizer! It's people like you who make this tool a better resource for the RPG Maker community.

---

## ❤️ Community & Open Source Philosophy

RPGMLocalizer is, and will always be, **open-source, free, and community-driven**. Our goal is to empower everyone to localize the games they love.

*   **Always Free**: This tool is a labor of love for the community. It will never require a paid license to operate.
*   **Fork-Friendly Policy**: You are more than welcome to fork this project and adapt it for your own community (e.g., localizing the source code or UI).
*   **Keep it Open**: If you do fork or reuse this code, we ask you to honor the project's spirit: **every derivative work must also remain free and open-source**. Let's keep the ecosystem accessible for everyone.
*   **Collaborative**: We value feedback and contributions from developers of all skill levels.

---


## 📜 Coding Standards

We follow a strict set of architectural principles to ensure the localization process never corrupts game files.


### 1. Language Policy
*   **Code & Documentation**: All variable names, classes, functions, commits, and technical documentation **MUST** be in English.
*   **User Interface**: User-facing strings (Yerelleştirme) may be localized, but fallback to English is required.

### 2. Modern Python & Type Safety
*   **Type Hints**: **ALL** function signatures MUST include clear type hints. 
    ```python
    def parse_data(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        # Implementation
    ```
*   **Python 3.10+**: Use modern Python features (like `match` statements or `|` for types) where appropriate for readability and performance.

### 3. Surgical Edits & SRP
*   **Surgical Modification**: When editing existing code, apply additive-first changes. Avoid rewriting entire files unless functionally necessary.
*   **Single Responsibility**: Functions should do one thing and do it well. If a logic block grows too large, refactor it into smaller, testable units.

### 4. Cross-Platform & Asset Safety
*   **Path Management**: Never use raw relative paths for assets. Always wrap asset loading in `resource_path()` from `src.utils.paths` to support PyInstaller builds.
*   **Backup Integrity**: Any destructive write operation to external game files **MUST** use the `BackupManager` before execution.
*   **Parser Guards**: Always enforce `is_safe_to_translate`, `_is_technical_string`, and `NON_TRANSLATABLE_KEY_HINTS` checks. Bypassing these guards can cause fatal game crashes.

---

## 🚀 Development Workflow

### 1. Environment Setup
Clone the repository and install development dependencies:
```bash
git clone https://github.com/LordOfTurk/RPGMLocalizer.git
cd RPGMLocalizer
python -m pip install -r requirements.txt
```

### 2. Branching
*   Create a feature branch for your changes: `git checkout -b feature/amazing-new-parser`
*   Use descriptive, English commit messages.

### 3. Testing (Mandatory)
RPGMLocalizer has a heavy regression suite to prevent "breaking the engine". You **must** ensure all tests pass before submitting a Pull Request:
```bash
python -m pytest tests/ -v
```
If you add a new parser or feature, please include corresponding unit tests in the `tests/` directory.

### 4. Submitting a Pull Request
*   Push your branch and open a Pull Request against the `main` branch.
*   Provide a clear summary of what your change does and why it's safe for RPG Maker projects.

---

## 🛠️ Reporting Bugs

If you find a bug, please open an Issue with:
1.  **RPG Maker Engine**: XP, VX/Ace, MV, or MZ.
2.  **Plugin Context**: If the crash is plugin-related, mention the plugin name (e.g., VisuStella, Yanfly).
3.  **Logs**: Attach the console output from the app's Console tab.

Thank you for helping us build the safest localization tool for RPG Maker!
