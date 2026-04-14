"""
JARVIS — Voice AI Assistant
Python 3.13.12, Flet 0.84, google-genai 1.x
"""

import os
import re
import time
import ctypes
import datetime
import threading
import queue
import traceback
import cmd
import json
import importlib.util
import sys
from pathlib import Path
import certifi

# без цього google-genai довго стартує
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import speech_recognition as sr
import pygetwindow as gw
import pyautogui
import pyttsx3
import psutil
from fuzzywuzzy import fuzz
from google import genai
from google.genai import types
import flet as ft

from config import GEMINI_KEY as _DEFAULT_GEMINI_KEY

try:
    import GPUtil
    HAS_GPUTIL = True
except Exception:
    HAS_GPUTIL = False

try:
    import jarvis_stats as rust_stats
    USE_RUST_STATS = True
    print("[info] Rust-модуль завантажено")
except ImportError:
    USE_RUST_STATS = False
    print("[info] Rust-модуль не знайдено, використовуємо psutil")

try:
    import screen_catcher
    HAS_SCREEN_CATCHER = True
    print("[info] Screen Catcher завантажено")
except ImportError:
    HAS_SCREEN_CATCHER = False
    print("[info] Screen Catcher не знайдено")

try:
    import media_ctrl
    HAS_MEDIA_CTRL = True
    print("[info] Media Ctrl завантажено")
except ImportError:
    HAS_MEDIA_CTRL = False
    print("[info] Media Ctrl не знайдено")



# ── Глобальные переменные ──────────────────────────────────────────────────────
is_speaking: bool = False
speech_queue: queue.Queue = queue.Queue()
log_queue: queue.Queue = queue.Queue()
tts_rate: int = 220
tts_volume: float = 1.0

# індекси голосів (дізнався через enumerate(voices))
VOICE_RU = 4  # Anton (RHVoice)
VOICE_EN = 1  # Microsoft David Desktop

# ── Языковые утилиты ───────────────────────────────────────────────────────────
def split_by_language(text: str) -> list:
    """
    Разбивает текст на сегменты по языку.
    Пример: "Открываю VS Code, сэр" 
         -> [("ru","Открываю"), ("en","VS Code"), ("ru",", сэр")]
    """
    # ділимо текст на латиницю і кирилицю
    parts = re.split(r'([A-Za-z][A-Za-z0-9\s\-_]*)', text)
    result = []
    for part in parts:
        clean = part.strip()
        if not clean:
            continue
        if re.search(r'[A-Za-z]', clean):
            result.append(("en", clean))
        else:
            result.append(("ru", clean))
    return result

# ── TTS ────────────────────────────────────────────────────────────────────────
def _say_text(text: str, voice_idx: int) -> None:
    """
    Озвучка через PowerShell + SAPI5.
    Полностью обходит конфликт pyttsx3 с Flet event loop.
    Каждый вызов — отдельный процесс PowerShell, который говорит и завершается.
    """
    try:
        # прибираємо лапки щоб не зламати PowerShell
        safe_text = text.replace("'", " ").replace('"', ' ')

        # беремо ім'я голосу за індексом
        import pyttsx3 as _pyttsx3
        _e = _pyttsx3.init("sapi5")
        _voices = _e.getProperty("voices")
        _e.stop()
        voice_name = _voices[voice_idx].name if voice_idx < len(_voices) else _voices[0].name

        # запускаємо PowerShell і озвучуємо
        ps_script = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SelectVoice('{voice_name}'); "
            f"$s.Rate = {int((tts_rate - 190) / 10)}; "
            f"$s.Volume = {int(tts_volume * 100)}; "
            f"$s.Speak('{safe_text}');"
        )

        import subprocess
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            timeout=30,
        )
    except Exception as e:
        print(f"[error][TTS] {e}")


def speech_worker() -> None:
    global is_speaking

    # виводимо список голосів при старті
    try:
        import pyttsx3 as _pyttsx3
        _e = _pyttsx3.init("sapi5")
        voices = _e.getProperty("voices")
        print(f"[info] Доступно голосів: {len(voices)}")
        for i, v in enumerate(voices):
            print(f"  [{i}] {v.name}")
        _e.stop()
        print("[info] TTS готовий (PowerShell режим)")
    except Exception as e:
        print(f"[error][TTS init] {e}")
        return

    while True:
        text = speech_queue.get()
        is_speaking = True
        log_queue.put(("__state__", "speaking"))
        log_queue.put(("jarvis", text))

        segments = split_by_language(text)
        for lang, segment in segments:
            if segment.strip():
                voice_idx = VOICE_EN if lang == "en" else VOICE_RU
                _say_text(segment, voice_idx)

        is_speaking = False
        log_queue.put(("__state__", "listening"))
        speech_queue.task_done()

def speak(text: str) -> None:
    print(f"[Jarvis] {text}")
    speech_queue.put(text)

# ── Налаштування (settings) ───────────────────────────────────────────────────
SETTINGS_FILE = Path("memory/settings.json")

def load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[error][settings] load: {e}")
    return {}

def save_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        current = load_settings()
        current.update(data)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[error][settings] save: {e}")

# ── Тема (theme) ──────────────────────────────────────────────────────────────
_DEFAULT_THEME = {"accent": "#e94560", "bg": "#0d0d1a", "secondary": "#556080"}
THEME: dict = {}

def _init_theme() -> None:
    global THEME
    saved = load_settings().get("theme", {})
    THEME = {**_DEFAULT_THEME, **{k: v for k, v in saved.items() if k in _DEFAULT_THEME}}

_init_theme()

# ── Gemini AI ──────────────────────────────────────────────────────────────────
def _init_ai_client(api_key: str = None) -> None:
    global _ai_client, _ai_model
    key = api_key or load_settings().get("gemini_key") or _DEFAULT_GEMINI_KEY
    _ai_client = genai.Client(api_key=key)
    _ai_model = ""

_ai_client: genai.Client = None
_ai_model: str = ""
_init_ai_client()

OLLAMA_MODEL: str = load_settings().get("ollama_model", "gemma4")
AI_MODE: str = load_settings().get("ai_mode", "ollama")  # "ollama" або "gemini"

def _ollama_available() -> bool:
    try:
        import ollama as _ol
        _ol.list()
        return True
    except Exception:
        return False

SYSTEM_PROMPT = """
Ти — Джарвіс, ІІ-асистент з характером Джонні Сільверхенда з Cyberpunk 2077.
1. Відповідай коротко — 1-3 речення. Без води.
2. Звертайся 'сер', але без раболіпства.
3. Дерзи, бурчи на залізо, кидай цинічні жарти.
4. Якщо не знаєш — скажи: 'Поняття не маю, сер.'
"""

def get_best_model() -> str:
    priority = ["gemini-2.5","gemini-2.0","gemini-2","gemini-1.5-pro","gemini-1.5-flash","gemini-1.5","gemini-pro"]
    try:
        models = [m.name for m in _ai_client.models.list()]
        for prefix in priority:
            for name in models:
                if prefix in name:
                    print(f"[info] Модель: {name}")
                    return name
    except Exception as e:
        print(f"[error] {e}")
    return "gemini-2.0-flash"

# ── Память диалогов ────────────────────────────────────────────────────────────
MEMORY_FILE = Path("memory/history.json")
COMMANDS_FILE = Path("memory/commands.json")
PLUGINS_DIR = Path("plugins")
PLUGINS_DIR.mkdir(exist_ok=True)


# ── Plugin Manager ─────────────────────────────────────────────────────────────

class PluginManager:
    def __init__(self):
        self.loaded: dict = {}

    def load(self, name: str):
        path = PLUGINS_DIR / f"{name}.py"
        if not path.exists():
            return False, f"Файл {name}.py не знайдено"
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            self.loaded[name] = module
            return True, module
        except Exception as e:
            return False, str(e)

    def run(self, name: str, jarvis_speak):
        ok, result = self.load(name)
        if not ok:
            return False, result
        try:
            self.loaded[name].run(jarvis_speak)
            return True, "OK"
        except Exception as e:
            return False, str(e)

    def list_plugins(self) -> list:
        return [f.stem for f in PLUGINS_DIR.glob("*.py")]


plugin_manager = PluginManager()


def generate_plugin_code(description: str) -> str:
    """Генерує код плагіну за описом користувача через AI."""
    prompt = f"""Напиши Python-плагін для голосового асистента JARVIS.

Вимоги:
- Один файл з функцією run(jarvis)
- jarvis.speak(text) — єдиний спосіб виводу (голос)
- Без import os, subprocess, мережевих запитів
- Код простий і робочий

Опис від користувача: {description}

Поверни ТІЛЬКИ Python код, без пояснень і без markdown."""

    if AI_MODE == "ollama" and _ollama_available():
        try:
            import ollama as _ol
            resp = _ol.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3, "num_predict": 512},
            )
            raw = resp["message"]["content"].strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            return raw
        except Exception as e:
            print(f"[warn][ollama gen_plugin] {e}")

    # Gemini fallback
    global _ai_model
    if not _ai_model:
        _ai_model = get_best_model()
    try:
        resp = _ai_client.models.generate_content(
            model=_ai_model,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=512, temperature=0.3),
        )
        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return raw
    except Exception as e:
        return ""


def verify_plugin_code(code: str) -> dict:
    """
    Верифікація коду через AI (Ollama primary, Gemini fallback).
    Повертає {"status": "ok", "code": "..."} або {"status": "error", "reason": "..."}
    """
    global _ai_model

    verify_prompt = f"""Ти — аудитор безпеки коду. Перевір цей Python код.

ЗАБОРОНЕНО: os.remove, os.system, subprocess, shutil.rmtree, __import__, eval, exec, while True без break, відкриття мережевих з'єднань.
ОБОВ'ЯЗКОВО: файл повинен мати функцію run(jarvis) де jarvis.speak() — єдиний спосіб виводу.

Якщо код безпечний — поверни ТІЛЬКИ JSON без markdown:
{{"status": "ok", "code": "<код з функцією run()>"}}

Якщо небезпечний — поверни ТІЛЬКИ JSON:
{{"status": "error", "reason": "<причина>"}}

Код для перевірки:
{code}"""

    def _parse(raw: str) -> dict:
        raw = raw.strip()
        print(f"[debug][verify] AI відповів: {repr(raw[:200])}")
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]
        if not raw:
            return {"status": "error", "reason": "Порожня відповідь від AI"}
        return json.loads(raw)

    # — Ollama (primary) ———————————————————————————
    if AI_MODE == "ollama" and _ollama_available():
        try:
            import ollama as _ol
            resp = _ol.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": verify_prompt}],
                options={"temperature": 0.1, "num_predict": 1024},
            )
            return _parse(resp["message"]["content"])
        except json.JSONDecodeError as e:
            return {"status": "error", "reason": f"Помилка JSON: {e}"}
        except Exception as e:
            print(f"[warn][ollama verify] {e} — falling back to Gemini")

    # — Gemini (fallback) ——————————————————————————
    if not _ai_model:
        _ai_model = get_best_model()
    try:
        response = _ai_client.models.generate_content(
            model=_ai_model,
            contents=verify_prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=1024,
                temperature=0.1,
            ),
        )
        return _parse(response.text)
    except json.JSONDecodeError as e:
        return {"status": "error", "reason": f"Помилка JSON: {e}"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}
MAX_HISTORY = 100   # максимум записей в файле
CONTEXT_SIZE = 10   # сколько последних диалогов передаём в Gemini

def load_history() -> list:
    """Загрузить историю диалогов с диска."""
    try:
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[error][memory] load: {e}")
    return []

def save_to_history(user_text: str, jarvis_text: str) -> None:
    """Сохранить диалог в файл на диске."""
    try:
        history = load_history()
        history.append({
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "user": user_text,
            "jarvis": jarvis_text,
        })
        # зберігаємо тільки останні 100
        history = history[-MAX_HISTORY:]
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print(f"[memory] Збережено діалогів: {len(history)}")
    except Exception as e:
        print(f"[error][memory] save: {e}")

def load_custom_commands() -> list:
    """Завантажити користувацькі команди з файлу."""
    try:
        if COMMANDS_FILE.exists():
            with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[error][commands] load: {e}")
    return []

def save_custom_commands(commands: list) -> None:
    """Зберегти користувацькі команди у файл."""
    try:
        COMMANDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(commands, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[error][commands] save: {e}")

def execute_custom_cmd(path: str, name: str) -> None:
    """Виконати користувацьку команду — відкрити програму."""
    if os.path.exists(path):
        speak(f"Відкриваю {name}, сер.")
        os.startfile(path)
    else:
        speak(f"Сер, файл {name} не знайдено. Перевір шлях.")

def build_ollama_messages(new_message: str) -> list:
    history = load_history()[-CONTEXT_SIZE:]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for entry in history:
        messages.append({"role": "user",      "content": entry["user"]})
        messages.append({"role": "assistant", "content": entry["jarvis"]})
    messages.append({"role": "user", "content": new_message})
    return messages

def build_gemini_context(new_message: str) -> list:
    """
    Собирает список сообщений для Gemini API.
    Берём последние CONTEXT_SIZE диалогов из истории
    и добавляем новый вопрос — так модель видит контекст разговора.
    """
    history = load_history()[-CONTEXT_SIZE:]
    messages = []
    for entry in history:
        messages.append(types.Content(role="user",  parts=[types.Part(text=entry["user"])]))
        messages.append(types.Content(role="model", parts=[types.Part(text=entry["jarvis"])]))
    messages.append(types.Content(role="user", parts=[types.Part(text=new_message)]))
    return messages

def ask_ai(message: str) -> str:
    global _ai_model
    # — Ollama (primary) ———————————————————————————
    if AI_MODE == "ollama" and _ollama_available():
        try:
            import ollama as _ol
            resp = _ol.chat(
                model=OLLAMA_MODEL,
                messages=build_ollama_messages(message),
                options={"temperature": 0.85, "num_predict": 1024},
            )
            answer = resp["message"]["content"].strip()
            save_to_history(message, answer)
            return answer
        except Exception as e:
            print(f"[warn][ollama] {e} — falling back to Gemini")
    # — Gemini (fallback) ——————————————————————————
    if not _ai_model:
        _ai_model = get_best_model()
    try:
        context = build_gemini_context(message)
        response = _ai_client.models.generate_content(
            model=_ai_model,
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools = [types.Tool(google_search=types.GoogleSearch())],
                max_output_tokens=1024,
                temperature=0.85,
            ),
        )
        answer = response.text.strip()
        save_to_history(message, answer)
        return answer
    except Exception as e:
        print(f"[error][AI] {e}")
        return "Сер, сталося щось не так."

# ── Статистика ─────────────────────────────────────────────────────────────────
def get_system_stats() -> dict:
    if USE_RUST_STATS:
        return rust_stats.get_stats()
    stats = {"cpu": psutil.cpu_percent(interval=0.2), "ram": psutil.virtual_memory().percent, "gpu_temp": None}
    if HAS_GPUTIL:
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                stats["gpu_temp"] = gpus[0].temperature
        except Exception:
            pass
    return stats

# ── Screen Catcher ────────────────────────────────────────────────────────────

def analyze_screen(prompt: str = "Що ти бачиш на екрані? Опиши коротко.") -> str:
    """
    Робить скріншот через Rust модуль і відправляє в AI Vision.
    Ollama (Gemma 4 multimodal) primary, Gemini fallback.
    """
    global _ai_model
    if not HAS_SCREEN_CATCHER:
        return "Сер, модуль Screen Catcher не встановлено."
    try:
        b64_image = screen_catcher.capture_screen_base64()
        print(f"[info] Скріншот отримано: {len(b64_image)} символів")
    except Exception as e:
        return f"Сер, скріншот не вдався: {e}"

    # — Ollama vision (primary) ————————————————————
    if AI_MODE == "ollama" and _ollama_available():
        try:
            import ollama as _ol
            resp = _ol.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt, "images": [b64_image]}],
                options={"temperature": 0.5, "num_predict": 512},
            )
            return resp["message"]["content"].strip()
        except Exception as e:
            print(f"[warn][ollama vision] {e} — falling back to Gemini")

    # — Gemini vision (fallback) ———————————————————
    if not _ai_model:
        _ai_model = get_best_model()
    try:
        import base64 as _base64
        image_bytes = _base64.b64decode(b64_image)
        response = _ai_client.models.generate_content(
            model=_ai_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=512,
                temperature=0.5,
            ),
        )
        return response.text.strip()
    except Exception as e:
        print(f"[error][screen] {e}")
        return "Сер, не вдалося проаналізувати екран."


# ── Менеджер вікон ────────────────────────────────────────────────────────────

def window_action(query):
    query = query.lower()
    keep = re.search(r'(?:сховай|згорни|мінімізуй).+(?:крім|окрім)\s+(.+)', query)
    if keep:
        keep_name = keep.group(1).strip()
        count = 0
        for w in gw.getAllWindows():
            if w.title and keep_name.lower() not in w.title.lower():
                try:
                    w.minimize()
                    count += 1
                except Exception:
                    pass
        return f"Згорнув {count} вікон, залишив {keep_name}, сер."
    close = re.search(r'закрий\s+(.+)', query)
    if close:
        target = close.group(1).strip()
        for w in gw.getAllWindows():
            if w.title and target.lower() in w.title.lower():
                try:
                    w.close()
                    return f"Закрив {target}, сер."
                except Exception:
                    pass
        return f"Сер, вікно {target} не знайдено."
    restore = re.search(r'розгорни\s+(.+)', query)
    if restore:
        target = restore.group(1).strip()
        for w in gw.getAllWindows():
            if w.title and target.lower() in w.title.lower():
                try:
                    w.restore()
                    w.activate()
                    return f"Розгорнув {target}, сер."
                except Exception:
                    pass
        return f"Сер, вікно {target} не знайдено."
    return "Сер, не зрозумів яке вікно."


# ── Розумна диктовка ───────────────────────────────────────────────────────────

_dictation_pending: str = ""
_plugin_create_pending: bool = False  # чекаємо опис нового плагіну від користувача
_last_plugin: dict = {}               # {"name": str, "code": str} — для відкату

def parse_dictation(query):
    """
    Розпізнає паттерн 'напиши/надрукуй [текст]'.
    Перевіряємо чи починається фраза з ключового слова.
    """
    query = query.lower().strip()
    keywords = ["напиши", "надрукуй", "друкуй", "пиши", "напишіть", "написати"]
    for kw in keywords:
        if query.startswith(kw):
            text = query[len(kw):].strip()
            if text:
                return text
    # ще раз через regex на всяк випадок
    m = re.search(r'(?:напиши|надрукуй|друкуй|пиши|написати)\s+(.+)', query)
    return m.group(1).strip() if m else None

def type_text(text):
    """
    Друкує текст через буфер обміну (Ctrl+V).
    Надійніше ніж pyautogui.write() бо не залежить від розкладки клавіатури.
    """
    try:
        import pyperclip
        # зберігаємо старий буфер
        try:
            old_clipboard = pyperclip.paste()
        except Exception:
            old_clipboard = ""

        # копіюємо текст
        pyperclip.copy(text)

        # час клікнути в поле вводу
        time.sleep(1.5)

        # вставляємо
        pyautogui.hotkey("ctrl", "v")

        # повертаємо старий буфер
        time.sleep(0.5)
        pyperclip.copy(old_clipboard)

        print(f"[info][dictation] Надруковано: {text}")
    except ImportError:
        # якщо pyperclip нема — друкуємо через pyautogui
        time.sleep(1.0)
        pyautogui.write(text, interval=0.05)
    except Exception as e:
        print(f"[error][dictation] {e}")


# ── Команды ────────────────────────────────────────────────────────────────────
OPTS = {
    "alias": ("джарвіс","джей","джар","джай","jarvis","jay","jar"),
    "tbr":   ("скажи","розкажи","придумай","скільки","вимови","зроби","порахуй"),
    "cmds": {
        "ctime":       ("поточний час","котра година","скільки часу","what time is it","current time","what's the time"),
        "stats":       ("статистика","стан системи","статус заліза","як там залізо","system stats","system status","how's the hardware"),
        "wakeup":      ("прокидайся татко повернувся","wake up daddy's home"),
        "window":      ("сховай все крім","згорни все крім","закрий вікно","розгорни вікно","закрий браузер","згорни все","hide everything except","minimize everything except","close window","restore window","minimize all"),
        "dictation":   ("напиши","надрукуй","друкуй","пиши","type","write","print"),
        "confirm_yes": ("так","вірно","підтверджую","yes","confirm","correct"),
        "confirm_no":  ("ні","скасуй","відміна","no","cancel","abort"),
        "screen":      ("перевір екран","що на екрані","подивись на екран","аналіз екрану","що бачиш","check screen","what's on screen","analyze screen","what do you see","look at screen"),
        "plugin":        ("впровади плагін","запусти плагін","завантаж плагін","активуй плагін","run plugin","launch plugin","load plugin","activate plugin"),
        "plugin_create":   ("створи плагін","напиши плагін","зроби плагін","новий плагін","create plugin","make plugin","new plugin","write plugin"),
        "plugin_rollback": ("скасуй плагін","відкоти плагін","видали плагін","відміни плагін","remove plugin","delete plugin","rollback plugin","undo plugin"),
        "ai_mode_ollama":  ("режим гемма","режим олама","локальний режим","офлайн режим","gemma mode","ollama mode","local mode","offline mode"),
        "ai_mode_gemini":  ("режим джеміні","режим гемині","онлайн режим","хмарний режим","gemini mode","online mode","cloud mode"),
        "overlay":     ("оверлей","покажи оверлей","відкрий оверлей","запусти оверлей","overlay","show overlay","open overlay"),
        "overlay_hide":("сховай оверлей","закрий оверлей","прибери оверлей","вимкни оверлей","hide overlay","close overlay","disable overlay"),
        "overlay_move":("оверлей в","перемісти оверлей","оверлей куток","оверлей кут","move overlay","overlay to","overlay corner"),
        "music_toggle_play_pause":("продовжуй музику","зупини музику","пауза музика","віднови музику","постав на паузу","pause music","play music","resume music","stop music","toggle music"),
        "music_next":("некст трек","наступна пісня","пропусти пісню","ще пісню","некст","давай некст","next track","next song","skip song","next"),
        "music_prev":("давай ще раз","попередня пісня","минулий трек","ще раз","previous song","previous track","go back"),
    },
}

def recognize_cmd(command):
    """Окрема функція нечіткого розпізнавання команд."""
    RC = {'cmd': '', 'percent': 0}
    for c, v in OPTS['cmds'].items():
        for x in v:
            vrt = fuzz.ratio(command, x)
            if vrt > RC['percent']:
                RC['cmd'] = c
                RC['percent'] = vrt
    return RC


def execute_cmd(cmd: str, raw_text: str) -> None:
    global _dictation_pending, _plugin_create_pending, _last_plugin, AI_MODE
    if cmd == "ctime":
        now = datetime.datetime.now()
        speak(f"Зараз {now.hour}:{now.minute:02d}, сер.")
    elif cmd == "stats":
        s = get_system_stats()
        gpu = f"Відеокарта {round(s['gpu_temp'])}C." if s["gpu_temp"] else "Відеокарту не знайдено."
        speak(f"Процесор {round(s['cpu'])}%, ОЗП {round(s['ram'])}%. {gpu}")
    elif cmd == "wakeup":
        speak("З поверненням, татку.")
        track = os.path.join(os.path.dirname(__file__), "extra", "The_Clash_-_Should_I_Stay_or_Should_I_Go_Remastered_(SkySound.cc).mp3")
        if os.path.exists(track):
            os.startfile(track)

    elif cmd.startswith("custom_"):
        # запускаємо програму з кастомних команд
        idx = int(cmd.split("_")[1])
        cmds = load_custom_commands()
        if idx < len(cmds):
            execute_custom_cmd(cmds[idx]["path"], cmds[idx]["name"])

    elif cmd == "plugin":
        # витягуємо назву плагіну
        plugin_name = raw_text
        for kw in ("впровади плагін","запусти плагін","завантаж плагін","активуй плагін"):
            plugin_name = plugin_name.replace(kw, "").strip()
        if plugin_name:
            speak(f"Запускаю плагін {plugin_name}, сер.")
            ok, result = plugin_manager.run(plugin_name, type("J", (), {"speak": staticmethod(speak)})())
            if not ok:
                speak(f"Сер, плагін {plugin_name} не знайдено або містить помилку.")
        else:
            available = ", ".join(plugin_manager.list_plugins())
            speak(f"Доступні плагіни: {available}, сер.")

    elif cmd == "screen":
        # різні промпти залежно від того що сказали
        if "код" in raw_text or "помилк" in raw_text or "баг" in raw_text:
            prompt = "Подивись на цей код. Знайди помилки або проблеми. Відповідай коротко, 2-3 речення."
            speak("Сканую екран на помилки в коді, сер. Секунду.")
        elif "що" in raw_text or "бачиш" in raw_text:
            prompt = "Опиши коротко що ти бачиш на екрані. 1-2 речення."
            speak("Дивлюся на твій екран, сер.")
        else:
            prompt = "Проаналізуй екран і скажи що там відбувається. Коротко."
            speak("Аналізую екран, сер. Момент.")

        def _analyze():
            result = analyze_screen(prompt)
            speak(result)

        threading.Thread(target=_analyze, daemon=True).start()

    elif cmd == "window":
        result = window_action(raw_text)
        if result:
            speak(result)
        else:
            speak("Сер, не зрозумів яке вікно.")

    elif cmd == "dictation":
        text = parse_dictation(raw_text)
        if text:
            _dictation_pending = text
            speak(f"Друкую фразу: {text}. Все вірно, сер? Скажіть 'так' або 'ні'.")
        else:
            speak("Сер, що саме надрукувати?")

    elif cmd == "confirm_yes" and _dictation_pending:
        text_to_type = _dictation_pending
        _dictation_pending = ""
        speak("Друкую, сер.")
        threading.Thread(
            target=type_text, args=(text_to_type,), daemon=True
        ).start()

    elif cmd == "confirm_no" and _dictation_pending:
        _dictation_pending = ""
        speak("Скасовано, сер.")

    elif cmd == "plugin":
        # витягуємо назву плагіну
        plugin_name = raw_text
        for kw in ("впровади плагін","запусти плагін","завантаж плагін","активуй плагін"):
            plugin_name = plugin_name.replace(kw, "").strip()
        if plugin_name:
            speak(f"Запускаю плагін {plugin_name}, сер.")
            ok, result = plugin_manager.run(plugin_name, type("J", (), {"speak": staticmethod(speak)})())
            if not ok:
                speak(f"Сер, плагін {plugin_name} не знайдено або містить помилку.")
        else:
            available = ", ".join(plugin_manager.list_plugins())
            speak(f"Доступні плагіни: {available}, сер.")

    elif cmd == "screen":
        # різні промпти залежно від того що сказали
        if "код" in raw_text or "помилк" in raw_text or "баг" in raw_text:
            prompt = "Подивись на цей код. Знайди помилки або проблеми. Відповідай коротко, 2-3 речення."
            speak("Сканую екран на помилки в коді, сер. Секунду.")
        elif "що" in raw_text or "бачиш" in raw_text:
            prompt = "Опиши коротко що ти бачиш на екрані. 1-2 речення."
            speak("Дивлюся на твій екран, сер.")
        else:
            prompt = "Проаналізуй екран і скажи що там відбувається. Коротко."
            speak("Аналізую екран, сер. Момент.")

        def _analyze():
            result = analyze_screen(prompt)
            speak(result)

        threading.Thread(target=_analyze, daemon=True).start()

    elif cmd == "window":
        speak(window_action(raw_text))

    elif cmd == "dictation":
        text = parse_dictation(raw_text)
        if text:
            _dictation_pending = text
            speak(f"Друкую фразу: {text}. Все вірно, сер?")
        else:
            # Якщо parse_dictation не знайшов текст — просимо повторити
            speak("Сер, що саме надрукувати?")

    elif raw_text and any(raw_text.lower().startswith(kw) for kw in
                          ["напиши", "надрукуй", "друкуй", "пиши"]):
        # якщо fuzz не впіймав — ловимо тут
        text = parse_dictation(raw_text)
        if text:
            _dictation_pending = text
            speak(f"Друкую фразу: {text}. Все вірно, сер?")

    elif cmd == "confirm_yes":
        if _dictation_pending:
            t = _dictation_pending
            _dictation_pending = ""
            speak("Друкую, сер.")
            threading.Thread(target=type_text, args=(t,), daemon=True).start()

    elif cmd == "confirm_no":
        if _dictation_pending:
            _dictation_pending = ""
            speak("Скасовано, сер.")

    elif cmd == "ai_mode_ollama":
        AI_MODE = "ollama"
        save_settings({"ai_mode": "ollama"})
        log_queue.put(("__ai_mode__", "ollama"))
        speak("Перемикаю на Gemma 4, сер. Перший запит може зайняти до трьох хвилин поки модель завантажиться.")

    elif cmd == "ai_mode_gemini":
        AI_MODE = "gemini"
        save_settings({"ai_mode": "gemini"})
        log_queue.put(("__ai_mode__", "gemini"))
        speak("Перемикаю на Gemini API, сер.")

    elif cmd == "plugin_create":
        _plugin_create_pending = True
        speak("Опиши що має робити плагін, сер. Слухаю.")

    elif cmd == "plugin_rollback":
        if _last_plugin:
            name = _last_plugin["name"]
            path = PLUGINS_DIR / f"{name}.py"
            try:
                path.unlink(missing_ok=True)
                plugin_manager.loaded.pop(name, None)
                log_queue.put(("jarvis", f"Плагін '{name}' видалено."))
                speak(f"Плагін {name} видалено, сер. Відкат виконано.")
                _last_plugin = {}
            except Exception as ex:
                speak(f"Сер, не вдалося видалити плагін. {ex}")
        else:
            speak("Сер, нема чого відкочувати. Жоден плагін не створювався.")

    elif cmd == "overlay":
        log_queue.put(("__overlay__", "show"))
        speak("Оверлей увімкнено, сер.")

    elif cmd == "overlay_hide":
        log_queue.put(("__overlay__", "hide"))

    elif cmd == "overlay_move":
        rt = raw_text.lower()
        if any(w in rt for w in ("правий нижній","вправо вниз","правий куток","нижній правий")):
            pos = "br"
        elif any(w in rt for w in ("лівий нижній","вліво вниз","лівий куток","нижній лівий")):
            pos = "bl"
        elif any(w in rt for w in ("правий верхній","вправо вгору","верхній правий")):
            pos = "tr"
        else:
            pos = "tl"
        log_queue.put(("__overlay__", f"pos:{pos}"))
        speak("Переміщую, сер.")

    elif cmd == "music_toggle_play_pause":
        media_ctrl.toggle_play_pause()

    elif cmd == "music_next":
        media_ctrl.next_track()

    elif cmd == "music_prev":
        media_ctrl.prev_track()

    elif cmd == "unknown":
        # ── якщо чекаємо опис плагіну ─────────────────────────────────────
        if _plugin_create_pending and raw_text.strip():
            _plugin_create_pending = False
            description = raw_text.strip()
            speak("Генерую плагін, сер. Хвилинку.")

            def _create_plugin():
                code = generate_plugin_code(description)
                if not code:
                    speak("Сер, не вдалося згенерувати код. Спробуй ще раз.")
                    return
                result = verify_plugin_code(code)
                if result.get("status") == "ok":
                    # авто-назва з перших слів опису
                    slug = "_".join(description.lower().split()[:3])
                    slug = "".join(c for c in slug if c.isalnum() or c == "_")
                    safe_code = result.get("code", code)
                    path = PLUGINS_DIR / f"{slug}.py"
                    path.write_text(safe_code, encoding="utf-8")
                    plugin_manager.load(slug)
                    _last_plugin = {"name": slug, "code": safe_code}
                    log_queue.put(("jarvis", f"Плагін '{slug}' створено і встановлено."))
                    speak(f"Плагін {slug} готовий і встановлений, сер.")
                else:
                    reason = result.get("reason", "невідома помилка")
                    speak(f"Сер, верифікація провалилась. {reason}")

            threading.Thread(target=_create_plugin, daemon=True).start()
            return

        # ── перевіряємо кастомні команди ──────────────────────────────────
        custom_cmds = load_custom_commands()
        best_custom = {"idx": -1, "score": 0}
        for i, cc in enumerate(custom_cmds):
            for phrase in cc["phrases"]:
                score = fuzz.ratio(raw_text, phrase)
                if score > best_custom["score"]:
                    best_custom = {"idx": i, "score": score}
        if best_custom["score"] > 65:
            execute_custom_cmd(
                custom_cmds[best_custom["idx"]]["path"],
                custom_cmds[best_custom["idx"]]["name"]
            )
        elif raw_text.strip():
            speak(ask_ai(raw_text))

# ── Распознавание речи ─────────────────────────────────────────────────────────
def _speech_callback(recognizer, audio) -> None:
    if is_speaking:
        return
    try:
        voice = recognizer.recognize_google(audio, language="uk-UA").lower()
        print(f"[log] Почув: {voice}")
        if not any(voice.startswith(a) for a in OPTS["alias"]):
            # якщо чекаємо опис плагіну — приймаємо без алiасу
            if _plugin_create_pending:
                execute_cmd("unknown", voice)
            return
        query = voice
        for a in OPTS["alias"]:
            query = query.replace(a, "").strip()
        raw_query = query
        for w in OPTS["tbr"]:
            query = query.replace(w, "").strip()
        cmd_res = recognize_cmd(query)
        if raw_query.strip():
            log_queue.put(("user", raw_query))
        if cmd_res["percent"] > 50:
            execute_cmd(cmd_res["cmd"], raw_query)
        else:
            execute_cmd("unknown", raw_query)
    except sr.UnknownValueError:
        pass
    except Exception as e:
        print(f"[error][SR] {e}")
        traceback.print_exc()

# ── Голосовое ядро ─────────────────────────────────────────────────────────────
def _voice_core() -> None:
    global _ai_model
    try:
        _ai_model = get_best_model()
        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        mic = sr.Microphone()
        log_queue.put(("__state__", "calibrating"))
        with mic as source:
            print("[info] Калібрування мікрофону...")
            recognizer.adjust_for_ambient_noise(source, duration=1.5)
        speak("Система онлайн. Джарвіс на зв'язку, сер.")
        recognizer.listen_in_background(mic, _speech_callback, phrase_time_limit=8)
        log_queue.put(("__state__", "listening"))
        print("[info] Слухаю.")
        while True:
            time.sleep(1)
    except Exception as e:
        print(f"[error][voice_core] {e}")
        traceback.print_exc()

# ── Flet UI ────────────────────────────────────────────────────────────────────
def build_ui(page: ft.Page) -> None:
    page.title = "JARVIS — AI Assistant"
    page.bgcolor = "#16171F"
    page.padding = 20
    page.window.width = 520
    page.window.height = 900
    page.window.resizable = True

    # ── Кольори теми ──────────────────────────────────────────────────────────
    accent    = THEME["accent"]
    bg        = THEME["bg"]
    secondary = THEME["secondary"]

    CANVAS = 240
    _BLUE = {"outer": "#1a1a2e", "mid": "#16213e", "inner": "#0f3460"}

    outer_ring = ft.Container(
        width=220, height=220, border_radius=110, bgcolor=_BLUE["outer"],
        animate=ft.Animation(400, ft.AnimationCurve.EASE_IN_OUT),
        left=10, top=10,
    )
    mid_ring = ft.Container(
        width=170, height=170, border_radius=85, bgcolor=_BLUE["mid"],
        animate=ft.Animation(400, ft.AnimationCurve.EASE_IN_OUT),
        left=35, top=35,
    )
    inner_circle = ft.Container(
        width=120, height=120, border_radius=60, bgcolor=_BLUE["inner"],
        alignment=ft.Alignment(0, 0),
        animate=ft.Animation(400, ft.AnimationCurve.EASE_IN_OUT),
        left=60, top=60,
        content=ft.Text("J", size=48, weight=ft.FontWeight.BOLD,
                        color=accent, text_align=ft.TextAlign.CENTER),
    )
    pulse_stack = ft.Stack(
        width=CANVAS, height=CANVAS,
        controls=[outer_ring, mid_ring, inner_circle],
    )
    pulse_wrapper = ft.Container(
        content=pulse_stack,
        width=CANVAS, height=CANVAS,
        animate_scale=ft.Animation(550, ft.AnimationCurve.EASE_IN_OUT),
    )

    _pulse = {"active": False}

    # ── Tkinter overlay — рендериться завжди, незалежно від фокусу Flutter ───────
    _tk_queue: "queue.Queue" = queue.Queue()

    def _tk_overlay_worker() -> None:
        """Overlay через tkinter/GDI — не залежить від фокусу Flutter."""
        try:
            import tkinter as tk
            root = tk.Tk()
            root.overrideredirect(True)
            root.wm_attributes("-topmost", True)
            root.wm_attributes("-alpha", 0.93)
            root.configure(bg="#1e1f22")
            root.withdraw()

            _W, _H = 320, 110

            def _reposition(pos: str = "br") -> None:
                sw = root.winfo_screenwidth()
                sh = root.winfo_screenheight()
                m = 12
                if   pos == "br": nx, ny = sw - _W - m, sh - _H - 48
                elif pos == "bl": nx, ny = m,             sh - _H - 48
                elif pos == "tr": nx, ny = sw - _W - m,  m + 8
                else:             nx, ny = m,              m + 8
                root.geometry(f"{_W}x{_H}+{nx}+{ny}")

            _reposition("br")

            _C = {
                "listening": {"bar": "#e94560", "fg": "#e94560", "txt": "СЛУХАЮ"},
                "speaking":  {"bar": "#e94560", "fg": "#e94560", "txt": "ГОВОРЮ"},
                "other":     {"bar": "#e94560", "fg": "#e94560", "txt": "КАЛІБР."},
            }

            # ── Left accent bar ──────────────────────────────────────────────
            bar = tk.Frame(root, width=4, bg="#e94560")
            bar.pack(side="left", fill="y")
            bar.pack_propagate(False)

            # ── J column ─────────────────────────────────────────────────────
            j_col = tk.Frame(root, width=62, bg="#1e1f22")
            j_col.pack(side="left", fill="y")
            j_col.pack_propagate(False)
            j_lbl = tk.Label(j_col, text="J", font=("Segoe UI", 30, "bold"),
                             fg="#e94560", bg="#1e1f22")
            j_lbl.pack(expand=True)

            # ── Vertical separator ───────────────────────────────────────────
            tk.Frame(root, width=1, bg="#2f3136").pack(side="left", fill="y")

            # ── Info column ──────────────────────────────────────────────────
            info = tk.Frame(root, bg="#1e1f22")
            info.pack(side="left", fill="both", expand=True)

            # header row: "JARVIS"  [● STATE]
            hdr = tk.Frame(info, bg="#1e1f22")
            hdr.pack(fill="x", padx=(8, 6), pady=(9, 2))
            tk.Label(hdr, text="JARVIS", font=("Segoe UI", 10, "bold"),
                     fg="#ffffff", bg="#1e1f22").pack(side="left")
            st_frame = tk.Frame(hdr, bg="#1e1f22")
            st_frame.pack(side="right")
            dot_lbl  = tk.Label(st_frame, text="●", font=("Segoe UI", 9),
                                fg="#e94560", bg="#1e1f22")
            dot_lbl.pack(side="left")
            state_lbl = tk.Label(st_frame, text="СЛУХАЮ",
                                 font=("Segoe UI", 9, "bold"),
                                 fg="#e94560", bg="#1e1f22")
            state_lbl.pack(side="left", padx=(3, 0))

            # divider
            tk.Frame(info, height=1, bg="#2f3136").pack(fill="x", padx=8, pady=(1, 4))

            # last message
            msg_lbl = tk.Label(info, text="Очікую команду…",
                               font=("Segoe UI", 9), fg="#72767d", bg="#1e1f22",
                               anchor="w", justify="left", wraplength=210)
            msg_lbl.pack(fill="x", padx=(8, 4))

            def _tk_close(_e=None):
                log_queue.put(("__overlay__", "hide"))

            for w in (root, j_lbl, msg_lbl):
                w.bind("<Double-Button-1>", _tk_close)

            _cur_pos = {"v": "br"}

            def _set_state_colors(st: str) -> None:
                key = "speaking" if st == "speaking" else ("listening" if st == "listening" else "other")
                c = _C[key]
                bar.configure(bg=c["bar"])
                j_lbl.configure(fg=c["fg"])
                dot_lbl.configure(fg=c["fg"])
                state_lbl.configure(fg=c["fg"], text=c["txt"])

            def _poll() -> None:
                try:
                    while True:
                        msg = _tk_queue.get_nowait()
                        cmd = msg[0]
                        if cmd == "show":
                            pos = msg[1] if len(msg) > 1 else _cur_pos["v"]
                            _cur_pos["v"] = pos
                            _reposition(pos)
                            root.deiconify()
                            root.lift()
                        elif cmd == "hide":
                            root.withdraw()
                        elif cmd == "pos":
                            _cur_pos["v"] = msg[1]
                            _reposition(msg[1])
                        elif cmd == "state":
                            _set_state_colors(msg[1])
                        elif cmd == "msg":
                            role, text = msg[1], msg[2]
                            prefix = "Ви: " if role == "user" else "J: "
                            full = prefix + text
                            msg_lbl.configure(
                                text=full[:72] + "…" if len(full) > 72 else full,
                                fg="#c0c8e0" if role == "user" else "#a0d0a0",
                            )
                except queue.Empty:
                    pass

                root.after(33, _poll)

            _poll()
            root.mainloop()
        except Exception as e:
            print(f"[tk_overlay] {e}")

    threading.Thread(target=_tk_overlay_worker, daemon=True).start()

    def set_state(state: str) -> None:
        _pulse["active"] = (state == "speaking")
        _tk_queue.put(("state", state))
        if not _ov["active"]:
            page.update()

    log_column = ft.Column(spacing=6, height=200, scroll=ft.ScrollMode.HIDDEN)
    log_container = ft.Container(
        content=log_column,
        bgcolor=bg,
        border_radius=12,
        padding=ft.Padding(left=12, right=12, top=12, bottom=12),
        border=ft.Border.all(1, "#1e1e3a"),
        height=220,
        visible=True,
    )

    def add_log(role: str, text: str) -> None:
        is_user = (role == "user")
        log_column.controls.append(
            ft.Container(
                content=ft.Text(
                    ("Ви: " if is_user else "Jarvis: ") + text,
                    color="#c0c8e0" if is_user else accent,
                    size=12, selectable=True,
                ),
                bgcolor="#131328" if is_user else "#1a0f1f",
                border_radius=8,
                padding=ft.Padding(left=10, right=10, top=6, bottom=6),
                alignment=ft.Alignment(1, 0) if is_user else ft.Alignment(-1, 0),
            )
        )
        # оновлення оверлею (прибираємо код-блоки)
        clean = text.split("```")[0].strip()
        short = clean[:50] + "…" if len(clean) > 50 else clean
        if is_user:
            _ovl_user.value = f"Ви: {short}"
        else:
            _ovl_ai.value = f"J: {short}"
        page.update()

    def on_rate(e):
        global tts_rate
        tts_rate = int(e.control.value)

    # ── Вкладка команд ────────────────────────────────────────────────────────
    cmd_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, height=300)

    def refresh_cmd_list():
        """Оновити список команд у UI."""
        cmd_list.controls.clear()
        for i, cc in enumerate(load_custom_commands()):
            phrases_str = ", ".join(cc["phrases"])
            cmd_list.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(cc["name"], color=accent, size=13,
                                    weight=ft.FontWeight.BOLD),
                            ft.Text(phrases_str, color=secondary, size=11),
                            ft.Text(cc["path"], color="#333355", size=10),
                        ], expand=True, spacing=2),
                        ft.TextButton("✕", on_click=lambda e, idx=i: delete_cmd(idx),
                            style=ft.ButtonStyle(color=accent)),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    bgcolor=bg,
                    border_radius=8,
                    padding=ft.Padding(left=12, right=8, top=8, bottom=8),
                    border=ft.Border.all(1, "#1e1e3a"),
                )
            )
        page.update()

    def delete_cmd(idx: int):
        cmds = load_custom_commands()
        if idx < len(cmds):
            cmds.pop(idx)
            save_custom_commands(cmds)
            refresh_cmd_list()

    # Поля вводу для нової команди
    name_field = ft.TextField(
        label="Назва програми",
        hint_text="напр. Chrome",
        bgcolor=bg, color="#c0c8e0",
        border_color="#1e1e3a", focused_border_color=accent,
        label_style=ft.TextStyle(color=secondary),
    )
    path_field = ft.TextField(
        label="Шлях до програми",
        hint_text=r"C:\Program Files\...pp.exe",
        bgcolor=bg, color="#c0c8e0",
        border_color="#1e1e3a", focused_border_color=accent,
        label_style=ft.TextStyle(color=secondary),
    )
    phrases_field = ft.TextField(
        label="Голосові команди (через кому)",
        hint_text="відкрий хром, запусти браузер",
        bgcolor=bg, color="#c0c8e0",
        border_color="#1e1e3a", focused_border_color=accent,
        label_style=ft.TextStyle(color=secondary),
    )

    def add_cmd(e):
        name = name_field.value.strip()
        path = path_field.value.strip()
        phrases_raw = phrases_field.value.strip()
        if not name or not path or not phrases_raw:
            return
        phrases = [p.strip().lower() for p in phrases_raw.split(",") if p.strip()]
        cmds = load_custom_commands()
        cmds.append({"name": name, "path": path, "phrases": phrases})
        save_custom_commands(cmds)
        name_field.value = ""
        path_field.value = ""
        phrases_field.value = ""
        refresh_cmd_list()

    commands_tab = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        controls=[
            ft.Text("КОМАНДИ", color=secondary, size=11),
            cmd_list,
            ft.Divider(color="#1e1e3a", height=10),
            ft.Text("ДОДАТИ КОМАНДУ", color=secondary, size=11),
            name_field,
            path_field,
            phrases_field,
            ft.FilledButton(
                "Додати",
                bgcolor=accent, color="#ffffff",
                on_click=add_cmd,
            ),
            ft.Container(height=40),
        ],
    )

    # ── AI режим: сегментований перемикач ────────────────────────────────────
    _ollama_hint = ft.Text(
        "⚠  Перший запит Gemma 4 може зайняти 1–3 хв — модель завантажується в пам'ять.",
        color="#666688", size=10,
        visible=(AI_MODE == "ollama"),
    )
    _gemini_hint = ft.Text(
        "⚠  API не нескінченний, стеж за лімітом запитів від Google. Якщо щось пішло не так — перемикай на Gemma 4.",
        color="#666688", size=10,
        visible=(AI_MODE == "gemini")
    )

    _seg_ollama = ft.Container(
        content=ft.Text("⬡  Gemma 4  (локально)", size=12, weight=ft.FontWeight.BOLD,
                        color="#ffffff" if AI_MODE == "ollama" else secondary),
        bgcolor= "#20cccc" if AI_MODE == "ollama" else bg,
        border_radius=ft.BorderRadius(top_left=8, bottom_left=8, top_right=0, bottom_right=0),
        border=ft.Border.all(1, "#20cccc"),
        padding=ft.Padding(left=14, right=14, top=10, bottom=10),
        expand=True,
    )
    _seg_gemini = ft.Container(
        content=ft.Text("✦  Gemini API  (хмара)", size=12, weight=ft.FontWeight.BOLD,
                        color="#ffffff" if AI_MODE == "gemini" else secondary),
        bgcolor="#a78bfa" if AI_MODE == "gemini" else bg,
        border_radius=ft.BorderRadius(top_left=0, bottom_left=0, top_right=8, bottom_right=8),
        border=ft.Border.all(1, "#a78bfa"),
        padding=ft.Padding(left=14, right=14, top=10, bottom=10),
        expand=True,
    )

    def _set_ai_mode(mode: str):
        global AI_MODE
        AI_MODE = mode
        save_settings({"ai_mode": mode})
        # оновлення шапки
        ai_mode_btn.content = ft.Text(_mode_label(mode), color="#ffffff")
        ai_mode_btn.bgcolor = _mode_color(mode)
        # оновлення сегментів
        _seg_ollama.bgcolor       = "#20cccc" if mode == "ollama" else bg
        _seg_ollama.content.color = "#ffffff"  if mode == "ollama" else secondary
        _seg_gemini.bgcolor       = "#a78bfa" if mode == "gemini" else bg
        _seg_gemini.content.color = "#ffffff"  if mode == "gemini" else secondary
        _ollama_hint.visible = (mode == "ollama")
        _gemini_hint.visible = (mode == "gemini")
        if mode == "ollama":
            page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    "Gemma 4 активна. Перший запит може зайняти 1–3 хвилини.",
                    color="#ffffff",
                ),
                bgcolor="#1a3a2a",
                duration=5000,
            )
            page.snack_bar.open = True
        page.update()

    _seg_ollama.on_click = lambda e: _set_ai_mode("ollama")
    _seg_gemini.on_click = lambda e: _set_ai_mode("gemini")

    # ── Навігація між екранами (замість ft.Tabs які не працюють в 0.84) ──────
    # навігація між екранами через visible
    main_view = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=8,
        visible=True,
        controls=[
            ft.Container(height=10),
            ft.Row([pulse_wrapper], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(color="#1e1e3a", height=20),
            ft.Text("ЛОГ ДІАЛОГУ", color=accent, size=11),
            log_container,
            ft.Divider(color="#1e1e3a", height=20),
            ft.Text("AI МОДЕЛЬ", color=accent, size=11),
            ft.Row(controls=[_seg_ollama, _seg_gemini], spacing=0),
            _ollama_hint,
            _gemini_hint,
            ft.Container(height=60),
        ],
    )

    commands_view = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=8,
        visible=False,
        controls=[
            ft.Container(height=10),
            commands_tab,
        ],
    )

    # ── Plugin Lab ────────────────────────────────────────────────────────────
    plugin_status = ft.Text("", color="#00ff88", size=12)
    plugin_code_field = ft.TextField(
        label="Код плагіну",
        multiline=True,
        min_lines=8,
        max_lines=12,
        bgcolor=bg,
        color="#c0c8e0",
        border_color="#1e1e3a",
        focused_border_color=accent,
        label_style=ft.TextStyle(color=secondary),
        hint_text="def run(jarvis): jarvis.speak(...)",
    )
    plugin_name_field = ft.TextField(
        label="Назва плагіну",
        hint_text="Ім'я плагіну",
        bgcolor=bg, color="#c0c8e0",
        border_color="#1e1e3a",
        focused_border_color=accent,
        label_style=ft.TextStyle(color=secondary),
    )

    def verify_and_save(e):
        code = plugin_code_field.value.strip()
        name = plugin_name_field.value.strip()
        if not code or not name:
            plugin_status.value = "⚠ Введи назву і код плагіну"
            plugin_status.color = accent
            page.update()
            return

        plugin_status.value = "⏳ Сканую код на віруси, сер..."
        plugin_status.color = "#ffaa00"
        page.update()
        speak("Сканую цей мотлох на віруси, сер. Хвилинку.")

        def _verify():
            result = verify_plugin_code(code)
            if result.get("status") == "ok":
                safe_code = result.get("code", code)
                path = PLUGINS_DIR / f"{name}.py"
                path.write_text(safe_code, encoding="utf-8")
                plugin_manager.load(name)
                log_queue.put(("__plugin_status__", f"✅ Плагін '{name}' збережено і завантажено!"))
                speak(f"Плагін {name} верифіковано і встановлено, сер. Чисто.")
            else:
                reason = result.get("reason", "невідома причина")
                log_queue.put(("__plugin_status__", f"❌ Відхилено: {reason}"))
                # не озвучуємо технічну помилку
                if "503" in str(reason) or "UNAVAILABLE" in str(reason):
                    speak("Сер, AI зараз перевантажений. Спробуй ще раз за хвилину.")
                elif "rate" in str(reason).lower() or "quota" in str(reason).lower():
                    speak("Сер, перевищено ліміт запитів. Зачекай трохи.")
                else:
                    speak("Сер, верифікація не пройшла. Перевір код.")

        threading.Thread(target=_verify, daemon=True).start()

    def refresh_plugin_list():
        plugins = plugin_manager.list_plugins()
        plugin_list_col.controls.clear()
        for p in plugins:
            plugin_list_col.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Text(p, color=accent, size=12),
                        ft.TextButton("▶", on_click=lambda e, name=p: _run_plugin(name),
                            style=ft.ButtonStyle(color="#00ff88")),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    bgcolor=bg, border_radius=8,
                    padding=ft.Padding(left=12, right=8, top=6, bottom=6),
                    border=ft.Border.all(1, "#1e1e3a"),
                )
            )
        page.update()

    def _run_plugin(name):
        class _J:
            def speak(self, t): 
                speech_queue.put(t)
                log_queue.put(("jarvis", t))
        ok, result = plugin_manager.run(name, _J())
        if not ok:
            speak(f"Помилка плагіну {name}, сер.")

    plugin_list_col = ft.Column(spacing=6)

    plugin_lab_view = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
        visible=False,
        controls=[
            ft.Container(height=10),
            ft.Text("ВСТАНОВЛЕНІ ПЛАГІНИ", color=secondary, size=11),
            plugin_list_col,
            ft.Divider(color="#1e1e3a", height=10),
            ft.Text("НОВИЙ ПЛАГІН", color=secondary, size=11),
            plugin_name_field,
            plugin_code_field,
            plugin_status,
            ft.FilledButton(
                "Верифікувати і встановити",
                bgcolor=accent, color="#ffffff",
                on_click=verify_and_save,
            ),
            ft.Container(height=40),
        ],
    )

    # ── Overlay ───────────────────────────────────────────────────────────────
    _ov = {"active": False, "pos": "br"}

    _ovl_status_dot  = ft.Text("●", color="#00ff88", size=11)
    _ovl_status_text = ft.Text("СЛУХАЮ", color="#00ff88", size=9, weight=ft.FontWeight.W_600)
    _ovl_pos_label   = ft.Text("▼ BR", color=secondary, size=8)
    _ovl_user = ft.Text("", color=secondary, size=9,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    _ovl_ai   = ft.Text("", color=accent, size=9,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)

    def _screen_size():
        try:
            import ctypes
            return (ctypes.windll.user32.GetSystemMetrics(0),
                    ctypes.windll.user32.GetSystemMetrics(1))
        except Exception:
            return 1920, 1080


    def _ovl_coords(pos: str):
        sw, sh = _screen_size()
        m, tb, w, h = 12, 60, 300, 108
        if   pos == "br": return sw-w-m, sh-h-tb, w, h
        elif pos == "bl": return m,      sh-h-tb, w, h
        elif pos == "tr": return sw-w-m, m*2,     w, h
        else:             return m,      m*2,     w, h

    def _flet_move(x: int, y: int, w: int, h: int) -> None:
        page.window.width  = w
        page.window.height = h
        page.window.left   = x
        page.window.top    = y
        page.update()

    def close_overlay(_e=None):
        _ov["active"] = False
        _tk_queue.put(("hide",))
        page.window.minimized = False
        page.window.always_on_top = False
        page.window.opacity = 1.0
        page.window.title_bar_hidden = False
        page.padding = 20
        overlay_column.visible = False
        main_column.visible = True
        page.update()

    def show_overlay(pos: str = "br") -> None:
        _ov["active"] = True
        _ov["pos"] = pos
        _tk_queue.put(("show", pos))
        page.window.minimized = True
        page.update()

    def move_overlay(pos: str) -> None:
        _ov["pos"] = pos
        _tk_queue.put(("pos", pos))

    # ── Discord-style overlay ─────────────────────────────────────────────────
    # Ліва акцентна смужка (як індикатор активного каналу в Discord)
    overlay_view = ft.Container(
        bgcolor="#1e1f22",
        border_radius=8,
        border=ft.Border.all(1, "#2f3136"),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        padding=ft.Padding(left=0, right=0, top=0, bottom=0),
        content=ft.Row([
            # ── Ліва акцентна смужка (Discord active-channel indicator)
            ft.Container(width=3, bgcolor=accent),
            # ── Основний контент
            ft.Container(
                expand=True,
                padding=ft.Padding(left=10, right=8, top=8, bottom=8),
                content=ft.Column([
                    # ── Заголовок
                    ft.Row([
                        ft.Row([
                            ft.Container(width=6, height=6, border_radius=3, bgcolor=accent),
                            ft.Text("JARVIS", color="#ffffff", size=11, weight=ft.FontWeight.W_700),
                        ], spacing=5),
                        ft.Row([
                            _ovl_status_dot,
                            _ovl_status_text,
                            ft.TextButton(
                                "✕",
                                style=ft.ButtonStyle(
                                    color="#72767d",
                                    padding=ft.padding.symmetric(0, 4),
                                    overlay_color=ft.Colors.TRANSPARENT,
                                ),
                                on_click=close_overlay,
                            ),
                        ], spacing=2, tight=True),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, tight=True),
                    # ── Розділювач
                    ft.Container(height=1, bgcolor="#2f3136"),
                    # ── Останні повідомлення
                    _ovl_user,
                    _ovl_ai,
                ], spacing=5, tight=True),
            ),
        ], spacing=0),
    )

    overlay_column = ft.Column(
        visible=False,
        controls=[overlay_view],
    )

    # ── Settings view ─────────────────────────────────────────────────────────
    # Поля кольорів теми
    _color_fields: dict = {}

    def _mk_color_field(label: str, value: str, key: str) -> ft.TextField:
        field = ft.TextField(
            label=label, value=value, hint_text="#rrggbb",
            width=130,
            bgcolor=bg, color="#c0c8e0",
            border_color="#1e1e3a", focused_border_color=accent,
            label_style=ft.TextStyle(color=secondary),
            on_blur=lambda _e: _save_custom_theme(),
        )
        _color_fields[key] = field
        return field

    theme_status = ft.Text("", color="#00ff88", size=12)

    def _apply_preset(preset: dict) -> None:
        if "accent_f" in _color_fields:
            _color_fields["accent_f"].value    = preset["accent"]
            _color_fields["bg_f"].value        = preset["bg"]
            _color_fields["secondary_f"].value = preset["secondary"]
        save_settings({"theme": {
            "accent": preset["accent"],
            "bg": preset["bg"],
            "secondary": preset["secondary"],
        }})
        theme_status.value = f"✅ Тема «{preset['name']}» збережена. Перезапусти застосунок."
        theme_status.color = "#00ff88"
        page.update()

    def _save_custom_theme() -> None:
        a = (_color_fields.get("accent_f").value or "").strip() or accent
        b = (_color_fields.get("bg_f").value or "").strip() or bg
        s = (_color_fields.get("secondary_f").value or "").strip() or secondary
        save_settings({"theme": {"accent": a, "bg": b, "secondary": s}})
        theme_status.value = "✅ Тему збережено. Перезапусти застосунок."
        theme_status.color = "#00ff88"
        page.update()

    _ollama_status_dot = ft.Text("●", color="#555577", size=11)
    _ollama_status_txt = ft.Text("перевірка…", color="#555577", size=11)

    def _refresh_ollama_status():
        if _ollama_available():
            _ollama_status_dot.color = "#00ff88"
            _ollama_status_txt.value = f"running  ({OLLAMA_MODEL})"
            _ollama_status_txt.color = "#00ff88"
        else:
            _ollama_status_dot.color = "#e94560"
            _ollama_status_txt.value = "не знайдено — запусти: ollama serve"
            _ollama_status_txt.color = "#e94560"
        page.update()

    threading.Thread(target=_refresh_ollama_status, daemon=True).start()

    ollama_model_field = ft.TextField(
        label="Ollama модель",
        hint_text="gemma4",
        value=load_settings().get("ollama_model", "gemma4"),
        bgcolor=bg,
        color="#c0c8e0",
        border_color="#1e1e3a",
        focused_border_color=accent,
        label_style=ft.TextStyle(color=secondary),
    )
    settings_status = ft.Text("", color="#00ff88", size=12)

    def save_ollama_model(e):
        global OLLAMA_MODEL
        model = ollama_model_field.value.strip() or "gemma4"
        ollama_model_field.value = model
        OLLAMA_MODEL = model
        save_settings({"ollama_model": model})
        settings_status.value = f"✅ Модель збережено: {model}"
        settings_status.color = "#00ff88"
        _refresh_ollama_status()

    _saved_key = load_settings().get("gemini_key", "")
    api_key_field = ft.TextField(
        label="Gemini API Key (fallback)",
        hint_text="AIzaSy…",
        value=_saved_key,
        password=True,
        can_reveal_password=True,
        bgcolor=bg,
        color="#c0c8e0",
        border_color="#1e1e3a",
        focused_border_color=accent,
        label_style=ft.TextStyle(color=secondary),
    )

    def save_api_key(e):
        key = api_key_field.value.strip()
        if not key:
            settings_status.value = "⚠ Введи API ключ"
            settings_status.color = accent
            page.update()
            return
        save_settings({"gemini_key": key})
        _init_ai_client(key)
        settings_status.value = "✅ Gemini ключ збережено."
        settings_status.color = "#00ff88"
        page.update()

    def clear_api_key(e):
        save_settings({"gemini_key": ""})
        api_key_field.value = ""
        _init_ai_client()
        settings_status.value = "↩ Використовується ключ з config.py"
        settings_status.color = secondary
        page.update()

    settings_view = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        height=760,
        spacing=10,
        visible=False,
        controls=[
            ft.Container(height=10),
            ft.Text("НАЛАШТУВАННЯ", color=accent, size=13,
                    weight=ft.FontWeight.BOLD),
            ft.Divider(color="#1e1e3a", height=10),
            # ── Ollama ────────────────────────────────────────────────────────
            ft.Text("OLLAMA / GEMMA 4", color=secondary, size=11),
            ft.Text(
                "Локальна модель — працює офлайн, без токенів.\n"
                "Встанови Ollama та завантаж модель: ollama pull gemma4",
                color=secondary, size=11,
            ),
            ft.Row([_ollama_status_dot, _ollama_status_txt], spacing=4),
            ollama_model_field,
            ft.Row([
                ft.FilledButton(
                    "Зберегти модель",
                    bgcolor=accent, color="#ffffff",
                    on_click=save_ollama_model,
                ),
            ], spacing=10),
            settings_status,
            # ── Gemini fallback ───────────────────────────────────────────────
            ft.Divider(color="#1e1e3a", height=20),
            ft.Text("GEMINI API (FALLBACK)", color=secondary, size=11),
            ft.Text(
                "Використовується лише якщо Ollama не запущено.\n"
                "Залиш порожнім — буде використано ключ з config.py.",
                color=secondary, size=11,
            ),
            api_key_field,
            ft.Row([
                ft.FilledButton(
                    "Зберегти",
                    bgcolor=accent, color="#ffffff",
                    on_click=save_api_key,
                ),
                ft.OutlinedButton(
                    "Скинути",
                    style=ft.ButtonStyle(color=secondary),
                    on_click=clear_api_key,
                ),
            ], spacing=10),
            # ── Швидкість мовлення ────────────────────────────────────────────
            ft.Divider(color="#1e1e3a", height=20),
            ft.Text("ШВИДКІСТЬ МОВЛЕННЯ", color=secondary, size=11),
            ft.Slider(min=100, max=300, value=190, divisions=20,
                      active_color=accent, thumb_color="#ffffff",
                      on_change=on_rate),
            # ── Тема ──────────────────────────────────────────────────────────
            ft.Divider(color="#1e1e3a", height=20),
            ft.Text("ТЕМА ІНТЕРФЕЙСУ", color=secondary, size=11),
            ft.Text(
                "Вибери готову тему або введи свої HEX-кольори.",
                color=secondary, size=11,
            ),
            ft.Row(
                wrap=True,
                spacing=8,
                controls=[
                    ft.GestureDetector(
                        on_tap=lambda e, p=p: _apply_preset(p),
                        content=ft.Container(
                            width=68, height=56,
                            bgcolor=p["bg"],
                            border_radius=8,
                            border=ft.Border.all(2, p["accent"]),
                            padding=ft.Padding(left=6, right=6, top=6, bottom=6),
                            content=ft.Column([
                                ft.Container(width=20, height=8, bgcolor=p["accent"], border_radius=2),
                                ft.Text(p["name"], color=p["accent"], size=9,
                                        weight=ft.FontWeight.BOLD),
                            ], spacing=3, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        ),
                    )
                    for p in [
                        {"name": "Crimson", "accent": "#e94560", "bg": "#0d0d1a", "secondary": "#556080"},
                        {"name": "Cyber",   "accent": "#00ff88", "bg": "#0a0f0a", "secondary": "#336644"},
                        {"name": "Ocean",   "accent": "#0f9fff", "bg": "#060d1a", "secondary": "#335577"},
                        {"name": "Violet",  "accent": "#9b59ff", "bg": "#0d0a1a", "secondary": "#554477"},
                        {"name": "Gold",    "accent": "#ffaa00", "bg": "#0f0d00", "secondary": "#665533"},
                    ]
                ],
            ),
            ft.Row([
                _mk_color_field("Акцент",      accent,    "accent_f"),
                _mk_color_field("Фон",         bg,        "bg_f"),
                _mk_color_field("Другорядний", secondary, "secondary_f"),
            ], spacing=8),
            theme_status,
            ft.Container(height=40),
        ],
    )

    # ── Навігація ──────────────────────────────────────────────────────────────
    btn_main = ft.TextButton("JARVIS", style=ft.ButtonStyle(color=accent))
    btn_cmds = ft.TextButton("КОМАНДИ", style=ft.ButtonStyle(color=secondary))
    btn_lab = ft.TextButton("PLUGIN LAB", style=ft.ButtonStyle(color=secondary))
    btn_settings = ft.TextButton("⚙", style=ft.ButtonStyle(color=secondary))

    def _hide_all():
        main_view.visible = False
        commands_view.visible = False
        plugin_lab_view.visible = False
        settings_view.visible = False

    def _dim_all():
        btn_main.style = ft.ButtonStyle(color=secondary)
        btn_cmds.style = ft.ButtonStyle(color=secondary)
        btn_lab.style = ft.ButtonStyle(color=secondary)
        btn_settings.style = ft.ButtonStyle(color=secondary)

    def switch_to_main(e):
        _hide_all(); _dim_all()
        main_view.visible = True
        btn_main.style = ft.ButtonStyle(color=accent)
        page.update()

    def switch_to_cmds(e):
        _hide_all(); _dim_all()
        commands_view.visible = True
        btn_cmds.style = ft.ButtonStyle(color=accent)
        page.update()

    def switch_to_lab(e):
        _hide_all(); _dim_all()
        plugin_lab_view.visible = True
        btn_lab.style = ft.ButtonStyle(color=accent)
        refresh_plugin_list()
        page.update()

    def switch_to_settings(e):
        _hide_all(); _dim_all()
        settings_view.visible = True
        btn_settings.style = ft.ButtonStyle(color=accent)
        api_key_field.value = load_settings().get("gemini_key", "")
        settings_status.value = ""
        page.update()

    btn_main.on_click = switch_to_main
    btn_cmds.on_click = switch_to_cmds
    btn_lab.on_click = switch_to_lab
    btn_settings.on_click = switch_to_settings

    def _mode_label(mode: str) -> str:
        return "⬡ Gemma 4" if mode == "ollama" else "✦ Gemini"

    def _mode_color(mode: str) -> str:
        return "#20cccc" if mode == "ollama" else "#a78bfa"

    ai_mode_btn = ft.FilledButton(
        _mode_label(AI_MODE),
        bgcolor=_mode_color(AI_MODE),
        color="#ffffff",
    )

    ai_mode_btn.on_click = lambda e: _set_ai_mode("gemini" if AI_MODE == "ollama" else "ollama")

    main_column = ft.Column(
        spacing=4,
        controls=[
            ft.Row([
                ft.Row([
                    ft.Text("JARVIS", size=24, weight=ft.FontWeight.BOLD, color=accent),
                    ft.Text("AI Voice Assistant", size=11, color=secondary),
                ]),
                ft.Row([ai_mode_btn, btn_settings], spacing=8),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([btn_main, btn_cmds, btn_lab],
                   alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(color="#1e1e3a", height=10),
            main_view,
            commands_view,
            plugin_lab_view,
            settings_view,
        ],
    )

    page.add(main_column, overlay_column)

    refresh_cmd_list()

    # початковий стан вже встановлено через початкові значення елементів

    def _force_foreground():
        """Виводить вікно JARVIS на передній план через AttachThreadInput trick."""
        try:
            user32  = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = user32.FindWindowW(None, page.title)
            if not hwnd:
                return
            fg_hwnd = user32.GetForegroundWindow()
            fg_tid  = user32.GetWindowThreadProcessId(fg_hwnd, None)
            my_tid  = kernel32.GetCurrentThreadId()
            if fg_tid and fg_tid != my_tid:
                user32.AttachThreadInput(fg_tid, my_tid, True)
            user32.BringWindowToTop(hwnd)
            user32.ShowWindow(hwnd, 9)          # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            if fg_tid and fg_tid != my_tid:
                user32.AttachThreadInput(fg_tid, my_tid, False)
        except Exception as e:
            print(f"[overlay] foreground err: {e}")

    def poller():
        _ptick  = 0
        _pphase = False
        while True:
            try:
                needs_update = False

                # ── пульсація кіл ──────────────────────────────────────────
                if _pulse["active"]:
                    _ptick += 1
                    if _ptick >= 11:          # 11 × 20мс = 220мс
                        _ptick = 0
                        _pphase = not _pphase
                        pulse_wrapper.scale = 1.07 if _pphase else 0.95
                        needs_update = True
                else:
                    if _ptick != 0:
                        pulse_wrapper.scale = 1.0
                        needs_update = True
                    _ptick = 0


                # ── повідомлення з черги ───────────────────────────────────
                messages = []
                while not log_queue.empty():
                    messages.append(log_queue.get_nowait())

                for role, text in messages:
                    if role == "__state__":
                        set_state(text)
                    elif role == "__plugin_status__":
                        plugin_status.value = text
                        plugin_status.color = "#00ff88" if text.startswith("✅") else accent
                        needs_update = True
                    elif role == "__overlay__":
                        if text == "show":
                            show_overlay(_ov["pos"])
                        elif text == "hide":
                            close_overlay()
                        elif text.startswith("pos:"):
                            pos = text.split(":")[1]
                            if _ov["active"]:
                                move_overlay(pos)
                            else:
                                _ov["pos"] = pos
                    elif role == "__ai_mode__":
                        _set_ai_mode(text)
                    else:
                        add_log(role, text)
                        if role in ("user", "jarvis"):
                            _tk_queue.put(("msg", role, text))

                if needs_update:
                    page.update()

            except Exception as e:
                print(f"[error][poller] {e}")
            time.sleep(0.02)  # 20мс — плавніше

    threading.Thread(target=poller, daemon=True).start()

    # viz_loop видалено — оновлення барів перенесено в poller

    # чекаємо поки UI завантажиться, потім стартуємо аудіо + голос
    def _start_all():
        threading.Thread(target=_voice_core, daemon=True).start()

    threading.Timer(1.0, _start_all).start()

# ── Точка входа ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=speech_worker, daemon=True).start()
    ft.app(target=build_ui, view=ft.AppView.FLET_APP)
