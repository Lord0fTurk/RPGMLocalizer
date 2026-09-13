# RPGMLocalizer 🎮✨

<p align="center">
  <strong>Autonomous, engine-aware translation and localization suite for RPG Maker games.</strong><br>
  <em>From classic Ruby titles (XP, VX, VX Ace) to modern JavaScript engines (MV, MZ).</em>
</p>

<p align="center">
  <a href="https://github.com/Lord0fTurk/RPGMLocalizer/releases"><img src="https://img.shields.io/badge/Release-v0.8.0-blue.svg?style=flat-square" alt="Version"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"></a>
  <a href="#-supported-rpg-maker-engines"><img src="https://img.shields.io/badge/Engines-XP%20%7C%20VX%20%7C%20VXA%20%7C%20MV%20%7C%20MZ-orange.svg?style=flat-square" alt="Supported Engines"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL%20v3-green.svg?style=flat-square" alt="License"></a>
  <a href="https://www.patreon.com/cw/LordOfTurk"><img src="https://img.shields.io/badge/Support-Patreon-FF424D.svg?style=flat-square&logo=patreon" alt="Patreon"></a>
</p>

---

## 🌟 Why RPGMLocalizer?

Translating RPG Maker games is notorious for breaking them. Generic translation tools treat game files as plain text, accidentally corrupting:
- **Game Control Codes** (`\C[2]`, `\V[10]`, `\N[1]`, `\I[45]`, `\!`, `\.`...) causing crashes, missing variables, or visual glitches.
- **Engine Script Calls & Formulas** inside event commands and database items.
- **Plugin Parameters & Note Tags** inside `js/plugins.js`.
- **Audio & Image Filenames** leading to missing asset game freezes.

**RPGMLocalizer solves this completely.** It is built from the ground up with deep understanding of RPG Maker data structures. It isolates translatable text from all engine internals, translates the text safely, and rebuilds the game without corrupting save files, plugin logic, or scripts.

---

## ⚡ 3-Step Quick Start (For Players & Translators)

You don't need any programming knowledge to translate your favorite games:

```
┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│  1. Select Game Folder  │ ──> │ 2. Choose Target Lang   │ ──> │ 3. Click Translate!     │
│  (or Game.exe directly) │     │ (and Translation Engine)│     │ Enjoy in your language! │
└─────────────────────────┘     └─────────────────────────┘     └─────────────────────────┘
```

1. **Select Game**: Launch RPGMLocalizer, click **Browse**, and select your game directory (or `Game.exe` / `index.html`).
2. **Configure**: Select the game's original language and your desired **Target Language**. Pick a translation engine (Google Web is free & unlimited; OpenAI/DeepSeek/Gemini offer human-like literary prose).
3. **Translate**: Click **Start Localization**. The tool creates an automated backup, protects all engine codes, translates dialogues and database terms, formats message boxes, and rebuilds the game files. Once complete, launch the game and play!

---

## 🚀 Key Features at a Glance

| Feature | Description |
| :--- | :--- |
| 🛡️ **SyntaxGuard™ Protection** | Segment-based protection separates all control codes (`\C[n]`, `\V[n]`, note tags, icons) before sending text to translators. Zero chance of engine code corruption. |
| 🎭 **Theatrical Scene Mode** | Groups consecutive dialogue lines into dramatic scenes with speaker attribution (`[0] Harold: ...`). AI translators understand context, banter, and tone instead of translating isolated sentences. |
| 🤖 **Multi-Engine AI Suite** | Native support for **OpenAI** (GPT-4o), **DeepSeek**, **Google Gemini**, and **100% Free Offline Local LLMs** (via Ollama or LM Studio). |
| 🌐 **Ultra-Resilient Google Engine** | Free built-in Google Web translation with multi-mirror automatic failover (`clients5` → `batchexecute` RPC → Lingva) and smart 429 rate-limit backoff. |
| 💾 **Project-Aware Smart Cache** | Translations are saved locally per game. If you stop and resume, or re-translate an updated game, already translated lines load instantly without costing API tokens or time. |
| 📏 **Auto Word-Wrapping** | Eliminates text overflow outside message boxes! Injects VisuStella `<WordWrap>` tags for compatible MZ games or applies intelligent character-boundary wrapping. |
| 📚 **Glossary & Regex Blacklist** | Lock character names, locations, and special terms so they are translated consistently across the entire game. |
| 📦 **Safe Atomic Backups** | Full automated backup of original `data/` files before any modifications. Roll back with one click if needed. |
| 🎨 **Modern Windows Fluent UI** | Clean, intuitive dark/light interface built with PyQt6 and Fluent Design. |

---

## 🕹️ Supported RPG Maker Engines

RPGMLocalizer seamlessly auto-detects and supports the entire RPG Maker lineage:

| Engine | Data Format | What Gets Localized | Status |
| :--- | :--- | :--- | :---: |
| **RPG Maker MZ** | JSON (`.json`) & JavaScript (`plugins.js`) | Dialogue, Choices, System terms, Database (Skills, Items, Enemies), Plugins, VisuStella WordWrap | ✅ Full Support |
| **RPG Maker MV** | JSON (`.json`) & JavaScript (`plugins.js`) | Dialogue, Choices, System terms, Database, Common Events, Plugin parameters | ✅ Full Support |
| **RPG Maker VX Ace** | Ruby Marshal (`.rvdata2`) | Dialogue, System terms, Descriptions, RGSS3 Scripts, Choices | ✅ Full Support |
| **RPG Maker VX** | Ruby Marshal (`.rvdata`) | Dialogue, Database, Terms, Legacy Shift-JIS/CP932 decodings | ✅ Full Support |
| **RPG Maker XP** | Ruby Marshal (`.rxdata`) | Classic 2004 titles: Maps, Events, Scripts, Database | ✅ Full Support |

> [!NOTE]
> **Encrypted Games**: If a game is packaged with encrypted archives (e.g. `.rgss3a`, `.pck`, or encrypted MV/MZ assets), the data files must be unpacked/decrypted before localization.

---

## 🤖 Supported Translation Engines

Choose the engine that best fits your needs, budget, and privacy preferences:

1. **Google Web (Free & Built-in)**
   - No API key required.
   - Ideal for quick, automated full-game translations.
   - Built with browser-grade headers, connection pooling, and alternate-mirror fallback.
2. **Modern AI / LLM (OpenAI, DeepSeek, Google Gemini)**
   - Delivers novel-quality, culturally nuanced dialogue.
   - Leverages **Scene Mode** to understand character personalities, sarcasm, and relationships.
   - Supports custom system prompts and user-defined translation guidelines.
3. **Local LLM (Ollama & LM Studio - 100% Free & Private)**
   - Translate completely offline on your own GPU without sending data to third parties.
   - Compatible with Llama 3, Qwen 2.5, Mistral, and custom translation fine-tunes.
4. **DeepL & LibreTranslate**
   - Official DeepL API support with tag handling and formality controls.
   - LibreTranslate for self-hosted or public open-source translation servers.

---

<details>
<summary>🇹🇷 <strong>Türkçe Hızlı Başlangıç Kılavuzu (Genişletmek için tıklayın)</strong></summary>

<br>

RPGMLocalizer, RPG Maker oyunlarını bozmadan, tek tıkla Türkçeleştirmeniz ve yerelleştirmeniz için geliştirilmiş gelişmiş bir masaüstü aracıdır.

### 3 Adımda Kolay Çeviri:
1. **Oyunu Seçin**: Programı açın, **Gözat** butonuna basarak oyunun klasörünü veya doğrudan `Game.exe` dosyasını seçin.
2. **Dilleri ve Motoru Belirleyin**: Kaynak dili (genellikle İngilizce veya Japonca) ve Hedef Dili (**Türkçe**) seçin. Çeviri motoru olarak ücretsiz Google'ı veya yüksek kaliteli yapay zeka modellerini (OpenAI, DeepSeek, Gemini, Ollama) seçebilirsiniz.
3. **Çeviriyi Başlatın**: **Yerelleştirmeyi Başlat** butonuna tıklayın. Program otomatik olarak yedek alır, oyun içi kodları koruyarak metinleri çevirir, metin kutusu taşmalarını önlemek için satır kaydırmalarını ayarlar ve oyunu hazır hale getirir.

### Sıkça Sorulan Sorular:
- **Oyunum bozulur mu?** Hayır. RPGMLocalizer, oyun kodlarını (`\C[1]`, `\V[2]`, vb.) ve teknik fonksiyonları çeviriden önce özel olarak ayırır ve korur. Ayrıca işlem öncesi otomatik yedek alır.
- **Yarım kalan çeviriye devam edebilir miyim?** Evet! Dahili akıllı önbellek (cache) sayesinde çevrilmiş hiçbir satır tekrar çevrilmez; elektrik kesilse veya program kapansa bile kaldığınız yerden anında devam eder.
- **Şifreli oyunlar çevrilir mi?** Oyun dosyaları (`.json` veya `.rvdata2`) şifreli arşivler içindeyse, önce standart açıcı araçlarla (decryptor) açılmalı, ardından çevrilmelidir.

</details>

---

## ❓ Frequently Asked Questions (FAQ)

<details>
<summary><strong>Q: Does RPGMLocalizer modify my original game files permanently?</strong></summary>

No. Before any file is modified, RPGMLocalizer creates a complete timestamped backup inside the game directory (e.g. `_backup_original/`). You can restore original files at any time.
</details>

<details>
<summary><strong>Q: Can I manually edit translations?</strong></summary>

Yes! You can use the **Export** feature to save extracted game text into standard CSV or JSON files, edit them in Excel or any text editor, and then **Import** them back into the game.
</details>

<details>
<summary><strong>Q: How does Scene Mode work with AI models?</strong></summary>

Traditional translators translate each dialogue box in isolation, losing who is speaking to whom. RPGMLocalizer's Scene Mode analyzes the game's event commands (Code 101/401) and packages entire conversation sequences together with actor names. The AI model sees the full scene context, producing natural dialogue flow and consistent character pronouns.
</details>

<details>
<summary><strong>Q: Where are settings and translation cache files stored?</strong></summary>

RPGMLocalizer follows standard OS conventions:
- **Windows**: `%APPDATA%\RPGMLocalizer\`
- **Portable Mode**: If a file named `.portable` is placed in the program folder, all cache and configuration files are kept right inside the application directory.
</details>

---

## 🛠️ Run From Source (Developers)

### Requirements
- Python 3.12 or newer
- Git

### Installation
```bash
# Clone repository
git clone https://github.com/Lord0fTurk/RPGMLocalizer.git
cd RPGMLocalizer

# Install dependencies
pip install -r requirements.txt

# Launch application
python main.py
```

### Running Test Suite
RPGMLocalizer features an extensive automated test suite covering all parsers, syntax guards, and translation engines:
```bash
python -m pytest -q
```

---

## 🤝 Support & Community

RPGMLocalizer is an independent open-source project. If it has helped you play or translate your favorite games, please consider supporting development:

- ☕ **Patreon**: [patreon.com/cw/LordOfTurk](https://www.patreon.com/cw/LordOfTurk)
- 🐛 **Issue Tracker**: [GitHub Issues](https://github.com/Lord0fTurk/RPGMLocalizer/issues)

---

## 📄 License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.
