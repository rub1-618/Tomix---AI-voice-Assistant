# Tomix — AI Voice Assistant

> "Do it your way!"

Tomix is a personal AI voice assistant with a cyberpunk aesthetic. It combines Google Gemini AI with a local Ollama model, voice recognition, and a set of high-performance Rust system modules — all wrapped in a Flet desktop UI.

---

## Features

- **Voice commands** in Ukrainian, and English and others with fuzzy matching
- **Gemini AI** with Google Search grounding for real-time answers
- **Ollama** local AI for offline mode (no internet required)
- **Screen analysis** — Tomix can see your screen and describe it via Gemini Vision
- **Music control** — play/pause/next/prev, now playing info via WinRT
- **File operations** — read, write, append, list, delete, rename via voice
- **Window management** — minimize, restore, hide all except one app
- **Reminders** — "remind me in 10 minutes"
- **Dictation** — type text anywhere via voice + Ctrl+V
- **Plugin system** — write Python plugins, AI verifies them for security before install
- **Floating overlay** — always-on-top status window
- **Keyboard shortcuts** — Ctrl+1/2/3/4 to switch tabs, Ctrl+Space to stop speech

---

## Architecture

**Python** — app logic, Gemini/Ollama AI, voice recognition (Google Speech API), Flet UI

**Rust modules** (compiled via Maturin):
| Module | Purpose |
|---|---|
| `jarvis_stats` | CPU / RAM / GPU temperature |
| `screen_catcher` | Screenshots to Base64 PNG |
| `audio_viz` | Microphone audio visualization |
| `media_ctrl` | Media keys + GSMTC now-playing info |
| `file_ops` | File operations via std::fs + walkdir |

**License server** — FastAPI + SQLite on Raspberry Pi 3B+, served via nginx + uvicorn

---

## Quick Start (from source)

### Requirements
- Windows 10/11
- Python 3.10+
- Rust toolchain ([rustup.rs](https://rustup.rs))
- Google Gemini API key ([aistudio.google.com](https://aistudio.google.com))

### Installation

**1. Clone the repo**
```bash
git clone https://github.com/rub1-618/Tomix---AI-voice-Assistant.git
cd Tomix---AI-voice-Assistant
```

**2. Install voices (RHVoice — Anatol UA + Aleksandr)**
```bash
python setup/setup.py
```

**3. Install Python dependencies**
```bash
pip install -r requirements.txt
pip install pygetwindow pyautogui certifi keyboard
```

**4. Compile Rust modules**
```bash
cd plugins_rust/jarvis_stats   && maturin develop && cd ../..
cd plugins_rust/screen_catcher && maturin develop && cd ../..
cd plugins_rust/audio_viz      && maturin develop && cd ../..
cd plugins_rust/media_ctrl     && maturin develop && cd ../..
cd plugins_rust/file_ops       && maturin develop && cd ../..
```

**5. Run**
```bash
python main.py
```

Enter your Gemini API key in the Settings tab on first launch.

---

## Download

Get the latest prebuilt `.exe` from [Releases](https://github.com/rub1-618/Tomix---AI-voice-Assistant/releases).

> Run `setup/setup.py` first to install the required TTS voices.

---

## Voice Commands

See [COMMANDS.md](COMMANDS.md) for the full list of voice commands.

---

## Tech Stack

| Layer | Technologies |
|---|---|
| UI | Flet 0.84 |
| AI | Google Gemini, Ollama (Gemma) |
| Voice input | SpeechRecognition + PyAudio (Google Speech API) |
| Voice output | Windows SAPI5 via PowerShell, RHVoice |
| System modules | Rust + PyO3 + Maturin |
| Fuzzy matching | fuzzywuzzy |
| License server | FastAPI, SQLAlchemy, SQLite, nginx, Raspberry Pi 3B+ |
| Tests | pytest + FastAPI TestClient |
