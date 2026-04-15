# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [
    ('extra', 'extra'),
    ('plugins', 'plugins'),
]
binaries = []
hiddenimports = []

# Rust extension modules (.pyd) — PyInstaller не находит их автоматически
for pkg in ['jarvis_stats', 'screen_catcher', 'audio_viz', 'media_ctrl', 'file_ops']:
    tmp = collect_all(pkg)
    datas    += tmp[0]
    binaries += tmp[1]
    hiddenimports += tmp[2]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        'jarvis_stats',
        'screen_catcher',
        'audio_viz',
        'media_ctrl',
        'file_ops',
        'fuzzywuzzy',
        'Levenshtein',
        'certifi',
        'speech_recognition',
        'pyaudio',
        'pyttsx3',
        'pyttsx3.drivers',
        'pyttsx3.drivers.sapi5',
        'pygetwindow',
        'pyautogui',
        'keyboard',
        'google.genai',
        'ollama',
        'psutil',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Tomix',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['extra\\icon.png'],
)
