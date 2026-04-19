import sys, os, aifc, random, string, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "../web/server"))
from web.server.db import Base, engine

email = f"test{random.randint(1000,9999)}@test.com"
key = str(uuid.uuid4())
hwid = str(uuid.uuid4())
name = ''.join(random.choices(string.ascii_lowercase, k=8))
description = "test description"
downloads = random.randint(0, 1000)
code = "test code"
author_id = random.randint(1, 9999)
is_verified = False



def setup_module():
    Base.metadata.create_all(bind=engine)


# ── _strip_markdown ────────────────────────────────────────────────────────────

from main import _strip_markdown
def test_strip_markdown():
    text = "**жирний** текст"
    assert _strip_markdown(text) == "жирний текст"

# ── recognize_cmd ──────────────────────────────────────────────────────────────

from main import recognize_cmd
def test_recognize_cmd():
    result = ""
    assert recognize_cmd(result) == {"cmd": "", "percent": 0}

# ── FastAPI ────────────────────────────────────────────────────────────────────

from fastapi.testclient import TestClient
from web.server.main import app

client = TestClient(app)

def test_get_root():
    r = client.get("/")
    assert r.json() == {"status": "ok"}

def test_post_register():
    r = client.post("/register", json={"email": email, "password": "123"})
    assert "key" in r.json()
    assert r.json()["plan"] == "free"

def test_post_login():
    r = client.post("/login", json={"email": email, "password": "123"})
    assert "key" in r.json()
    assert r.json()["plan"] == "free"

def test_get_validate_invalid_key():
    r = client.get("/validate", params={"key": key, "hwid": hwid})
    assert r.status_code == 404

def test_get_plugins():
    r = client.get("/plugins")
    assert isinstance(r.json(), list)

def test_post_plugins():
    r = client.post("/plugins", json={
                                      "name": name, 
                                      "description": description, 
                                      "code": code, 
                                      "author_id": author_id, 
                                      "is_verified": is_verified
                                      })
    assert r.status_code == 200

# ── OPTS ────────────────────────────────────────────────────────────────────

def test_recognize_cmd_commands():

    result = recognize_cmd("стоп")
    assert result["cmd"] == "stop"

    result = recognize_cmd("котра година")
    assert result["cmd"] == "ctime"

    result = recognize_cmd("статистика")
    assert result["cmd"] == "stats"

    result = recognize_cmd("wake up daddy's home")
    assert result["cmd"] == "wakeup"

    result = recognize_cmd("сховай все крім")
    assert result["cmd"] == "window"

    result = recognize_cmd("надрукуй")
    assert result["cmd"] == "dictation"

    result = recognize_cmd("affirmative")
    assert result["cmd"] == "confirm_yes"
    
    result = recognize_cmd("negative")
    assert result["cmd"] == "confirm_no"

    result = recognize_cmd("analyze screen")
    assert result["cmd"] == "screen"

    result = recognize_cmd("запусти плагін")
    assert result["cmd"] == "plugin"

    result = recognize_cmd("створи плагін")
    assert result["cmd"] == "plugin_create"

    result = recognize_cmd("відкоти плагін")
    assert result["cmd"] == "plugin_rollback"

    result = recognize_cmd("ollama mode")
    assert result["cmd"] == "ai_mode_ollama"

    result = recognize_cmd("gemini mode")
    assert result["cmd"] == "ai_mode_gemini"

    result = recognize_cmd("overlay")
    assert result["cmd"] == "overlay"

    # result = recognize_cmd("turn off overlay")
    # assert result["cmd"] == "overlay_hide"

    # result = recognize_cmd("перемісти оверлей")
    # assert result["cmd"] == "overlay_move"

    result = recognize_cmd("toggle music")
    assert result["cmd"] == "music_toggle_play_pause"

    result = recognize_cmd("next")
    assert result["cmd"] == "music_next"

    result = recognize_cmd("prev")
    assert result["cmd"] == "music_prev"

    result = recognize_cmd("music info")
    assert result["cmd"] == "music_info"

    result = recognize_cmd("прочитай файл")
    assert result["cmd"] == "file_read"

    result = recognize_cmd("створи файл")
    assert result["cmd"] == "file_write"

    result = recognize_cmd("додай до файлу")
    assert result["cmd"] == "file_append"

    result = recognize_cmd("що в папці")
    assert result["cmd"] == "file_list"

    result = recognize_cmd("видали файл")
    assert result["cmd"] == "file_delete"

    result = recognize_cmd("зміни назву файлу")
    assert result["cmd"] == "file_rename"