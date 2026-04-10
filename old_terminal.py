import os
import time
import datetime
import speech_recognition as sr
from fuzzywuzzy import fuzz
import pyttsx3
import webbrowser
import queue
import threading
import pythoncom

# commands conf
opts = {
    "alias": ('джарвис', 'джей', 'джар', 'джай', 'jarvis', 'jay', 'jey', 'jar'),
    "tbr": ('скажи', 'расскажи', 'придумай', 'сколько', 'произнеси',
            'посчитай', 'как', 'зачем', 'почему', 'для чего',
            'каким образом', 'всмысле', 'сделай',
            'say', 'tell', 'think of', 'how many', 'count', 'how', 'why',
            'what for', 'what do you mean', 'do'),
    "cmds": {
        "ctime": ('текущее время', 'сколько времени', 'сколько время', 'который час',
                  'current time', 'how much time', 'what time is it'),
        "spotify": ('открой спотифай', 'open spotify'),
        "radio": ('включи радио', 'turn on the radio'),
        "meme": ('расскажи анекдот', 'рассмеши меня', 'tell me a joke', 'make me laugh'),
        "wakeup": ('просыпайся папочка вернулся', "wake up daddy's home"),
        "VS": ('открой визуал студио', 'open visual studio'),
        "browser": ('открой браузер', 'open browser'),
        "telegram": ('открой телеграм', 'open telegram'),
        "viber": ('открой вайбер', 'open viber'),
        "discord": ('открой дискорд', 'open discord')
    }
}

speech_queue = queue.Queue()
is_speaking = False

def speech_worker():
    global is_speaking
    # Инициализация COM для работы с SAPI5 в отдельном потоке
    pythoncom.CoInitialize()
    
    while True:
        text = speech_queue.get()
        is_speaking = True
        try:
            temp_engine = pyttsx3.init('sapi5')
            temp_engine.setProperty('rate', 180)
            voices = temp_engine.getProperty('voices')
            if len(voices) > 1:
                temp_engine.setProperty('voice', voices[1].id)

            print(f"[Jarvis]: {text}")
            temp_engine.say(text)
            temp_engine.runAndWait()
            del temp_engine
        except Exception as e:
            print(f"[error] Ошибка в потоке озвучки: {e}")
        
        is_speaking = False
        speech_queue.task_done()

def speak(what):
    speech_queue.put(what)

def recognize_cmd(cmd):
    RC = {'cmd': '', 'percent': 0}
    for c, v in opts['cmds'].items():
        for x in v:
            vrt = fuzz.ratio(cmd, x)
            if vrt > RC['percent']:
                RC['cmd'] = c
                RC['percent'] = vrt
    return RC

def execute_cmd(cmd):
    if cmd == 'ctime':
        now = datetime.datetime.now()
        speak(f"The current time is {now.hour}:{now.minute:02d}")
    elif cmd == 'wakeup':
        speak("Waking up, sir.")
        os.startfile(r'E:\Programming\JARVIS_COMPONENTS\The_Clash_-_Should_I_Stay_or_Should_I_Go_Remastered_(SkySound.cc).mp3')
    elif cmd == 'spotify':
        speak("Opening Spotify, sir")
        os.startfile(r"C:\Users\vsevo\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Spotify.lnk")
    elif cmd == 'radio':
        speak("Turning on the radio, sir.")
        webbrowser.open("https://play.tavr.media/radioroks/classicrock/")
    elif cmd == 'browser':
        speak("Opening the browser, sir.")
        os.startfile(r'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Brave.lnk')
    elif cmd == 'telegram':
        speak("Opening Telegram, sir.")
        os.startfile(r'C:\Users\vsevo\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Telegram Desktop\Telegram.lnk')
    elif cmd == 'viber':
        speak("Opening Viber, sir.")
        os.startfile(r'C:\Users\vsevo\AppData\Roaming\Microsoft\Windows\Start Menu\Viber.lnk')
    elif cmd == 'discord':
        speak("Opening Discord, sir.")
        os.startfile(r'C:\Users\vsevo\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Discord Inc\Discord.lnk')
    elif cmd == 'VS':
        speak("Opening Visual Studio, sir.")
        os.startfile(r'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Visual Studio.lnk')
    elif cmd == 'meme':
        speak("I'm not ready to tell jokes yet, sir.")
    else:
        speak("I'm shocked too, sir.")
        os.startfile(r'E:\Programming\JARVIS_COMPONENTS\che_za_huynia.jpg')

def callback(recognizer, audio):
    if is_speaking:
        return

    try:
        voice = recognizer.recognize_google(audio, language="ru-RU").lower()
        print(f"[log] Распознано: {voice}")

        if any(voice.startswith(alias) for alias in opts["alias"]):
            cmd = voice
            for x in opts['alias']:
                cmd = cmd.replace(x, "").strip()
            for x in opts['tbr']:
                cmd = cmd.replace(x, "").strip()
            
            print(f"[debug] Очищенная команда: '{cmd}'")
            cmd_res = recognize_cmd(cmd)

            if cmd_res['percent'] > 50:
                execute_cmd(cmd_res['cmd'])
            else:
                execute_cmd('unknown')
    except sr.UnknownValueError:
        print("[log] Голос не распознан!")
    except sr.RequestError:
        print("[log] Ошибка сети")

# --- Запуск программы ---
# 1. Поток озвучки
t = threading.Thread(target=speech_worker, daemon=True)
t.start()

# 2. Настройка микрофона
r = sr.Recognizer()
m = sr.Microphone(device_index=1)
with m as source:
    r.adjust_for_ambient_noise(source, duration=1)

# 3. Приветствие
speak("Hello, sir.")
speak("I'm listening.")

# 4. Фоновое прослушивание
stop_listening = r.listen_in_background(m, callback)

# 5. Главный цикл
while True:
    time.sleep(0.1)