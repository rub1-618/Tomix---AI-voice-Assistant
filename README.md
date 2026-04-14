 - Tomix — My Personal AI Assistant
Welcome! This is my pet project that I am actively developing. Tomix isn't just another chatbot. It’s an ambitious attempt to bring the iconic AI assistant from the Marvel movies into real-life workflows.
"Everyone deserves an easier life!" - the slogan of the project.

🛠 What’s under the hood?
I decided to go with a hybrid architecture to get the best of both worlds:
Python: The "brain" of the project. It handles the Gemini API integration, natural language processing, and the core logic.
Rust: The "muscles." I use Rust for high-performance system modules where memory safety and speed are critical (like screen capturing and system monitoring).

 * Key Features

> Gemini Intelligence: Powered by Google's Gemini API, Tomix understands complex context and maintains natural conversations.
> Vision Capabilities: Tomix can "see" your screen, analyze what's happening, and provide real-time assistance.
> System Mastery: Controls windows, monitors hardware stats (CPU/RAM/GPU), and automates repetitive tasks.
> Extensibility (The Best Part): The project is fully modular. Anyone can write their own Python methods and import them as plugins to customize Tomix for their specific needs.

 => Getting Started

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

**2. Install Python dependencies**
```bash
pip install -r requirements.txt
```

**3. Create `config.py` with your Gemini API key**
```python
GEMINI_KEY = "your_key_here"
```

**4. Compile Rust modules**
```bash
cd plugins_rust/media_ctrl && python -m maturin build --release --out ../../dist && cd ../..
cd plugins_rust/jarvis_stats && python -m maturin build --release --out ../../dist && cd ../..
cd plugins_rust/screen_catcher && python -m maturin build --release --out ../../dist && cd ../..
pip install dist/media_ctrl-0.1.0-cp313-cp313-win_amd64.whl dist/jarvis_stats-0.1.0-cp313-cp313-win_amd64.whl dist/screen_catcher-0.1.0-cp313-cp313-win_amd64.whl --force-reinstall
```

**5. Run**
```bash
python main.py
```

 => Roadmap
Currently in Early Beta. Here is the plan:

1. Finalize core features and optimize the Python-Rust bridge.
2. Release a portable build for easier installation.
3. The Big Goal: Launch a dedicated website with a license system and a Community Hub where users can share their own modules and ideas.
4. Rebranding (to avoid any legal issues with Marvel, haha).

P.S. I’m still a student and learning every day. There might be some "creative" workarounds in the code, but I'm striving for best practices. If you have any ideas, feel free to reach out!
