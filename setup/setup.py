import urllib.request
import subprocess
import os

if not os.path.exists("anatol.exe") or not os.path.exists("alexander.exe"):
    print("Downloading voices...")
    urllib.request.urlretrieve("https://github.com/RHVoice/anatol-ukr/releases/download/4.3/RHVoice-voice-Ukrainian-Anatol-v4.3.1030.22-setup.exe", "anatol.exe")  # скачать файл
    subprocess.run(["anatol.exe", "/S"], check=True, shell=True)
    print("Loading Anatol (UK) voice complete")
    os.remove("anatol.exe")
    urllib.request.urlretrieve("https://github.com/RHVoice/aleksandr-rus/releases/download/4.2/RHVoice-voice-Russian-Aleksandr-v4.2.2017.22-setup.exe", "alexander.exe")  # скачать файл
    subprocess.run(["alexander.exe", "/S"], check=True, shell=True)
    print("Loading Alexander (RU) voice complete")
    os.remove("alexander.exe")
    print("Loading complete!")