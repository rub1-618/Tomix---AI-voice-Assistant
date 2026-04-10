"""
JARVIS — Voice AI Assistant
Python 3.13.12, Flet 0.84, google-genai 1.x
"""

import os
import re
import time
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

# Фикс SSL — без этого google-genai долго ждёт при первом запросе
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

from config import GEMINI_KEY

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

# ── Глобальные переменные ──────────────────────────────────────────────────────
is_speaking: bool = False
speech_queue: queue.Queue = queue.Queue()
log_queue: queue.Queue = queue.Queue()
tts_rate: int = 220
tts_volume: float = 1.0

# Индексы голосов SAPI5 — узнали командой enumerate(voices)
VOICE_RU = 4  # Vsevolod (RHVoice)
VOICE_EN = 1  # Microsoft David Desktop

# ── Языковые утилиты ───────────────────────────────────────────────────────────
def split_by_language(text: str) -> list:
    """
    Разбивает текст на сегменты по языку.
    Пример: "Открываю VS Code, сэр" 
         -> [("ru","Открываю"), ("en","VS Code"), ("ru",", сэр")]
    """
    # Разделяем по блокам латиницы
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
        # Экранируем кавычки чтобы неломать PowerShell команду
        safe_text = text.replace("'", " ").replace('"', ' ')

        # Получаем имя голоса по индексу через pyttsx3 (только для получения имени)
        import pyttsx3 as _pyttsx3
        _e = _pyttsx3.init("sapi5")
        _voices = _e.getProperty("voices")
        _e.stop()
        voice_name = _voices[voice_idx].name if voice_idx < len(_voices) else _voices[0].name

        # PowerShell скрипт: выбираем голос по имени и озвучиваем
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

    # Получаем список голосов для вывода в лог
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

# ── Gemini AI ──────────────────────────────────────────────────────────────────
_ai_client = genai.Client(api_key=GEMINI_KEY)
_ai_model: str = ""

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


def verify_plugin_code(code: str) -> dict:
    """
    Верифікація коду через Gemini в окремому потоці.
    Повертає {"status": "ok", "code": "..."} або {"status": "error", "reason": "..."}
    """
    global _ai_model
    if not _ai_model:
        _ai_model = get_best_model()

    verify_prompt = f"""Ти — аудитор безпеки коду. Перевір цей Python код.

ЗАБОРОНЕНО: os.remove, os.system, subprocess, shutil.rmtree, __import__, eval, exec, while True без break, відкриття мережевих з'єднань.
ОБОВ'ЯЗКОВО: файл повинен мати функцію run(jarvis) де jarvis.speak() — єдиний спосіб виводу.

Якщо код безпечний — поверни ТІЛЬКИ JSON без markdown:
{{"status": "ok", "code": "<код з функцією run()>"}}

Якщо небезпечний — поверни ТІЛЬКИ JSON:
{{"status": "error", "reason": "<причина>"}}

Код для перевірки:
{code}"""

    try:
        response = _ai_client.models.generate_content(
            model=_ai_model,
            contents=verify_prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=1024,
                temperature=0.1,
            ),
        )
        raw = response.text.strip()
        print(f"[debug][verify] Gemini відповів: {repr(raw[:200])}")
        # Прибираємо markdown якщо Gemini обгорнув відповідь
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]
        if not raw:
            return {"status": "error", "reason": "Порожня відповідь від AI"}
        return json.loads(raw)
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
        # Храним только последние MAX_HISTORY записей
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

def build_gemini_context(new_message: str) -> list:
    """
    Собирает список сообщений для Gemini API.
    Берём последние CONTEXT_SIZE диалогов из истории
    и добавляем новый вопрос — так модель видит контекст разговора.
    """
    history = load_history()[-CONTEXT_SIZE:]
    messages = []
    for entry in history:
        messages.append({"role": "user",  "parts": [entry["user"]]})
        messages.append({"role": "model", "parts": [entry["jarvis"]]})
    messages.append({"role": "user", "parts": [new_message]})
    return messages

def ask_ai(message: str) -> str:
    global _ai_model
    if not _ai_model:
        _ai_model = get_best_model()
    try:
        # Передаём историю как контекст
        context = build_gemini_context(message)
        response = _ai_client.models.generate_content(
            model=_ai_model,
            contents=context,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=1024,
                temperature=0.85,
            ),
        )
        answer = response.text.strip()
        # Сохраняем диалог в файл
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
    Робить скріншот через Rust модуль і відправляє в Gemini Vision.
    Повертає текстовий опис того що на екрані.
    """
    global _ai_model
    if not HAS_SCREEN_CATCHER:
        return "Сер, модуль Screen Catcher не встановлено."
    if not _ai_model:
        _ai_model = get_best_model()
    try:
        # Отримуємо Base64 скріншот з Rust модуля
        b64_image = screen_catcher.capture_screen_base64()
        print(f"[info] Скріншот отримано: {len(b64_image)} символів")

        # Відправляємо в Gemini Vision через types.Part
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
    # Також перевіряємо через regex якщо слово не на початку
    m = re.search(r'(?:напиши|надрукуй|друкуй|пиши|написати)\s+(.+)', query)
    return m.group(1).strip() if m else None

def type_text(text):
    """
    Друкує текст через буфер обміну (Ctrl+V).
    Надійніше ніж pyautogui.write() бо не залежить від розкладки клавіатури.
    """
    try:
        import pyperclip
        # Зберігаємо старий вміст буферу
        try:
            old_clipboard = pyperclip.paste()
        except Exception:
            old_clipboard = ""

        # Копіюємо текст в буфер
        pyperclip.copy(text)

        # Чекаємо поки користувач клікне в потрібне поле
        time.sleep(1.5)

        # Вставляємо через Ctrl+V
        pyautogui.hotkey("ctrl", "v")

        # Відновлюємо старий буфер через секунду
        time.sleep(0.5)
        pyperclip.copy(old_clipboard)

        print(f"[info][dictation] Надруковано: {text}")
    except ImportError:
        # Fallback на pyautogui якщо pyperclip не встановлено
        time.sleep(1.0)
        pyautogui.write(text, interval=0.05)
    except Exception as e:
        print(f"[error][dictation] {e}")


# ── Команды ────────────────────────────────────────────────────────────────────
OPTS = {
    "alias": ("джарвіс","джей","джар","джай","jarvis","jay","jar"),
    "tbr":   ("скажи","розкажи","придумай","скільки","вимови","зроби","порахуй"),
    "cmds": {
        "ctime":       ("поточний час","котра година","скільки часу"),
        "stats":       ("статистика","стан системи","статус заліза","як там залізо"),
        "wakeup":      ("прокидайся татко повернувся","wake up daddy's home"),
        "window":      ("сховай все крім","згорни все крім","закрий вікно","розгорни вікно","закрий браузер","згорни все"),
        "dictation":   ("напиши","надрукуй","друкуй","пиши"),
        "confirm_yes": ("так","вірно","підтверджую","yes"),
        "confirm_no":  ("ні","скасуй","відміна","no"),
        "screen":      ("перевір екран","що на екрані","подивись на екран","аналіз екрану","що бачиш"),
        "plugin":      ("впровади плагін","запусти плагін","завантаж плагін","активуй плагін"),
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
    global _dictation_pending
    if cmd == "ctime":
        now = datetime.datetime.now()
        speak(f"Зараз {now.hour}:{now.minute:02d}, сер.")
    elif cmd == "stats":
        s = get_system_stats()
        gpu = f"Відеокарта {round(s['gpu_temp'])}C." if s["gpu_temp"] else "Відеокарту не знайдено."
        speak(f"Процесор {round(s['cpu'])}%, ОЗП {round(s['ram'])}%. {gpu}")
    elif cmd == "wakeup":
        speak("З поверненням, татку.")
        track = r"E:\Programming\JARVIS_COMPONENTS\The_Clash_-_Should_I_Stay_or_Should_I_Go.mp3"
        if os.path.exists(track):
            os.startfile(track)

    elif cmd.startswith("custom_"):
        # Кастомна команда — відкрити програму
        idx = int(cmd.split("_")[1])
        cmds = load_custom_commands()
        if idx < len(cmds):
            execute_custom_cmd(cmds[idx]["path"], cmds[idx]["name"])

    elif cmd == "plugin":
        # Витягуємо назву плагіну з фрази
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
        # Визначаємо промпт залежно від контексту
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
        # Витягуємо назву плагіну з фрази
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
        # Визначаємо промпт залежно від контексту
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
        # Додатковий fallback — якщо fuzz не впіймав команду
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

    elif cmd == "unknown":
        # Перевіряємо кастомні команди через нечітке порівняння
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
            log_queue.put(("user", raw_text))
            speak(ask_ai(raw_text))

# ── Распознавание речи ─────────────────────────────────────────────────────────
def _speech_callback(recognizer, audio) -> None:
    if is_speaking:
        return
    try:
        voice = recognizer.recognize_google(audio, language="uk-UA").lower()
        print(f"[log] Почув: {voice}")
        if not any(voice.startswith(a) for a in OPTS["alias"]):
            return
        query = voice
        for a in OPTS["alias"]:
            query = query.replace(a, "").strip()
        raw_query = query
        for w in OPTS["tbr"]:
            query = query.replace(w, "").strip()
        cmd_res = recognize_cmd(query)
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
    page.window.resizable = False

    CANVAS = 240
    outer_ring = ft.Container(
        width=220, height=220, border_radius=110, bgcolor="#e94560",
        animate=ft.Animation(600, ft.AnimationCurve.EASE_IN_OUT),
        left=10, top=10,
    )
    mid_ring = ft.Container(
        width=170, height=170, border_radius=85, bgcolor="#1a3a1a",
        animate=ft.Animation(500, ft.AnimationCurve.EASE_IN_OUT),
        left=35, top=35,
    )
    inner_circle = ft.Container(
        width=120, height=120, border_radius=60, bgcolor="#0f3460",
        alignment=ft.Alignment(0, 0),
        animate=ft.Animation(400, ft.AnimationCurve.EASE_IN_OUT),
        left=60, top=60,
        content=ft.Text("J", size=48, weight=ft.FontWeight.BOLD,
                        color="#e94560", text_align=ft.TextAlign.CENTER),
    )
    pulse_stack = ft.Stack(width=CANVAS, height=CANVAS,
                           controls=[outer_ring, mid_ring, inner_circle])

    status_label = ft.Text("● СЛУХАЮ ВАС", color="#e94560", size=13,
                           weight=ft.FontWeight.W_600)

    def set_state(state: str) -> None:
        if state == "listening":
            outer_ring.bgcolor="#1a2a1a"; mid_ring.bgcolor="#1a3a1a"; inner_circle.bgcolor="#0a4a0a"
            outer_ring.width=outer_ring.height=230; outer_ring.left=outer_ring.top=5
            mid_ring.width=mid_ring.height=175;     mid_ring.left=mid_ring.top=32
            inner_circle.width=inner_circle.height=125; inner_circle.left=inner_circle.top=57
            status_label.value="● СЛУХАЮ ВАС"; status_label.color="#00ff88"
        elif state == "speaking":
            outer_ring.bgcolor="#1a2a1a"; mid_ring.bgcolor="#1a3a1a"; inner_circle.bgcolor="#0a4a0a"
            outer_ring.width=outer_ring.height=238; outer_ring.left=outer_ring.top=1
            mid_ring.width=mid_ring.height=185;     mid_ring.left=mid_ring.top=27
            inner_circle.width=inner_circle.height=135; inner_circle.left=inner_circle.top=52
            status_label.value="● ГОВОРЮ"; status_label.color="#00ff88"
        else:
            outer_ring.bgcolor="#1a1a2e"; mid_ring.bgcolor="#16213e"; inner_circle.bgcolor="#0f3460"
            outer_ring.width=outer_ring.height=220; outer_ring.left=outer_ring.top=10
            mid_ring.width=mid_ring.height=170;     mid_ring.left=mid_ring.top=35
            inner_circle.width=inner_circle.height=120; inner_circle.left=inner_circle.top=60
            status_label.value="● ОЧІКУВАННЯ"; status_label.color="#556080"
        page.update()

    log_column = ft.Column(spacing=6, height=200, scroll=ft.ScrollMode.HIDDEN)
    log_container = ft.Container(
        content=log_column,
        bgcolor="#0d0d1a",
        border_radius=12,
        padding=ft.Padding(left=12, right=12, top=12, bottom=12),
        border=ft.border.all(1, "#1e1e3a"),
        height=220,
        visible=True,
    )

    def add_log(role: str, text: str) -> None:
        is_user = (role == "user")
        log_column.controls.append(
            ft.Container(
                content=ft.Text(
                    ("Ви: " if is_user else "Jarvis: ") + text,
                    color="#c0c8e0" if is_user else "#e94560",
                    size=12, selectable=True,
                ),
                bgcolor="#131328" if is_user else "#1a0f1f",
                border_radius=8,
                padding=ft.Padding(left=10, right=10, top=6, bottom=6),
                alignment=ft.Alignment(1, 0) if is_user else ft.Alignment(-1, 0),
            )
        )
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
                            ft.Text(cc["name"], color="#e94560", size=13,
                                    weight=ft.FontWeight.BOLD),
                            ft.Text(phrases_str, color="#556080", size=11),
                            ft.Text(cc["path"], color="#333355", size=10),
                        ], expand=True, spacing=2),
                        ft.TextButton("✕", on_click=lambda e, idx=i: delete_cmd(idx),
                            style=ft.ButtonStyle(color="#e94560")),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    bgcolor="#0d0d1a",
                    border_radius=8,
                    padding=ft.Padding(left=12, right=8, top=8, bottom=8),
                    border=ft.border.all(1, "#1e1e3a"),
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
        bgcolor="#0d0d1a", color="#c0c8e0",
        border_color="#1e1e3a", focused_border_color="#e94560",
        label_style=ft.TextStyle(color="#556080"),
    )
    path_field = ft.TextField(
        label="Шлях до програми",
        hint_text=r"C:\Program Files\...pp.exe",
        bgcolor="#0d0d1a", color="#c0c8e0",
        border_color="#1e1e3a", focused_border_color="#e94560",
        label_style=ft.TextStyle(color="#556080"),
    )
    phrases_field = ft.TextField(
        label="Голосові команди (через кому)",
        hint_text="відкрий хром, запусти браузер",
        bgcolor="#0d0d1a", color="#c0c8e0",
        border_color="#1e1e3a", focused_border_color="#e94560",
        label_style=ft.TextStyle(color="#556080"),
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
            ft.Text("КОМАНДИ", color="#556080", size=11),
            cmd_list,
            ft.Divider(color="#1e1e3a", height=10),
            ft.Text("ДОДАТИ КОМАНДУ", color="#556080", size=11),
            name_field,
            path_field,
            phrases_field,
            ft.FilledButton(
                "Додати",
                bgcolor="#e94560", color="#ffffff",
                on_click=add_cmd,
            ),
            ft.Container(height=40),
        ],
    )

    # ── Навігація між екранами (замість ft.Tabs які не працюють в 0.84) ──────
    # Два контейнери — показуємо один, ховаємо інший
    main_view = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=8,
        visible=True,
        controls=[
            ft.Container(height=10),
            ft.Row([pulse_stack], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([status_label], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(color="#1e1e3a", height=20),
            ft.Text("ЛОГ ДІАЛОГУ", color="#e94560", size=11),
            log_container,
            ft.Divider(color="#1e1e3a", height=20),
            ft.Text("ШВИДКІСТЬ МОВЛЕННЯ", color="#e94560", size=11),
            ft.Slider(min=100, max=300, value=190, divisions=20,
                      active_color="#e94560", thumb_color="#ffffff",
                      on_change=on_rate),
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
        bgcolor="#0d0d1a",
        color="#c0c8e0",
        border_color="#1e1e3a",
        focused_border_color="#e94560",
        label_style=ft.TextStyle(color="#556080"),
        hint_text="def run(jarvis): jarvis.speak(...)",
    )
    plugin_name_field = ft.TextField(
        label="Назва плагіну",
        hint_text="Ім'я плагіну",
        bgcolor="#0d0d1a", color="#c0c8e0",
        border_color="#1e1e3a",
        focused_border_color="#e94560",
        label_style=ft.TextStyle(color="#556080"),
    )

    def verify_and_save(e):
        code = plugin_code_field.value.strip()
        name = plugin_name_field.value.strip()
        if not code or not name:
            plugin_status.value = "⚠ Введи назву і код плагіну"
            plugin_status.color = "#e94560"
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
                # Озвучуємо тільки коротке повідомлення без технічних деталей
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
                        ft.Text(p, color="#e94560", size=12),
                        ft.TextButton("▶", on_click=lambda e, name=p: _run_plugin(name),
                            style=ft.ButtonStyle(color="#00ff88")),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    bgcolor="#0d0d1a", border_radius=8,
                    padding=ft.Padding(left=12, right=8, top=6, bottom=6),
                    border=ft.border.all(1, "#1e1e3a"),
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
            ft.Text("ВСТАНОВЛЕНІ ПЛАГІНИ", color="#556080", size=11),
            plugin_list_col,
            ft.Divider(color="#1e1e3a", height=10),
            ft.Text("НОВИЙ ПЛАГІН", color="#556080", size=11),
            plugin_name_field,
            plugin_code_field,
            plugin_status,
            ft.FilledButton(
                "Верифікувати і встановити",
                bgcolor="#e94560", color="#ffffff",
                on_click=verify_and_save,
            ),
            ft.Container(height=40),
        ],
    )

    def switch_to_main(e):
        main_view.visible = True
        commands_view.visible = False
        plugin_lab_view.visible = False
        btn_main.style = ft.ButtonStyle(color="#e94560")
        btn_cmds.style = ft.ButtonStyle(color="#556080")
        btn_lab.style = ft.ButtonStyle(color="#556080")
        page.update()

    def switch_to_cmds(e):
        main_view.visible = False
        commands_view.visible = True
        plugin_lab_view.visible = False
        btn_main.style = ft.ButtonStyle(color="#556080")
        btn_cmds.style = ft.ButtonStyle(color="#e94560")
        btn_lab.style = ft.ButtonStyle(color="#556080")
        page.update()

    def switch_to_lab(e):
        main_view.visible = False
        commands_view.visible = False
        plugin_lab_view.visible = True
        btn_main.style = ft.ButtonStyle(color="#556080")
        btn_cmds.style = ft.ButtonStyle(color="#556080")
        btn_lab.style = ft.ButtonStyle(color="#e94560")
        refresh_plugin_list()
        page.update()

    btn_main = ft.TextButton("JARVIS", on_click=switch_to_main,
                             style=ft.ButtonStyle(color="#e94560"))
    btn_cmds = ft.TextButton("КОМАНДИ", on_click=switch_to_cmds,
                              style=ft.ButtonStyle(color="#556080"))
    btn_lab = ft.TextButton("PLUGIN LAB", on_click=switch_to_lab,
                             style=ft.ButtonStyle(color="#556080"))

    page.add(
        ft.Column(
            spacing=4,
            controls=[
                ft.Row([
                    ft.Text("JARVIS", size=24, weight=ft.FontWeight.BOLD, color="#e94560"),
                    ft.Text("  AI Voice Assistant", size=11, color="#556080"),
                ], alignment=ft.MainAxisAlignment.START),
                ft.Row([btn_main, btn_cmds, btn_lab]),
                ft.Divider(color="#1e1e3a", height=10),
                main_view,
                commands_view,
                plugin_lab_view,
            ],
        )
    )

    refresh_cmd_list()

    set_state("listening")

    def poller():
        while True:
            try:
                # Собираем все накопившиеся сообщения за один проход
                messages = []
                while not log_queue.empty():
                    messages.append(log_queue.get_nowait())
                
                # Обрабатываем — важно сохранить порядок speaking/listening
                for role, text in messages:
                    if role == "__state__":
                        set_state(text)
                    elif role == "__plugin_status__":
                        plugin_status.value = text
                        plugin_status.color = "#00ff88" if text.startswith("✅") else "#e94560"
                        page.update()
                    else:
                        add_log(role, text)
            except Exception as e:
                print(f"[error][poller] {e}")
            time.sleep(0.05)  # 50мс вместо 100мс — быстрее реагирует

    threading.Thread(target=poller, daemon=True).start()
    # Даём UI 1 секунду на инициализацию перед стартом голосового ядра
    threading.Timer(1.0, lambda: threading.Thread(target=_voice_core, daemon=True).start()).start()

# ── Точка входа ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=speech_worker, daemon=True).start()
    ft.app(target=build_ui)
