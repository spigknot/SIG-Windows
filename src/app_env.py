"""Identidade, caminhos e ambiente do aplicativo.

Responsabilidade unica: responder 'onde fica isto' (pastas, arquivos de
configuracao, host da maquina). Nao le nem grava dados; nao conhece Tkinter.
Extraido de sig_app.py sem alteracao de comportamento (__file__ resolve para
o mesmo src/ de sig_app.py)."""

import os
import socket
import sys
from pathlib import Path, PurePosixPath


APP_NAME = "sig"
IMEI_HISTORY_FILE = "imei_history.txt"
def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parents[1] / relative
def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        # Uma atualização antiga pode ter deixado o executável dentro de uma
        # subpasta (por exemplo, dist/g). O diretório principal é identificado
        # pelos recursos que o SIG precisa para funcionar.
        runtime_markers = ("ffmpeg.exe", "ffplay.exe", "vad_deps")
        for candidate in (executable_dir, *executable_dir.parents[:4]):
            if any((candidate / marker).exists() for marker in runtime_markers):
                return candidate
        return executable_dir
    return Path(__file__).resolve().parents[1]
def project_root() -> Path:
    """Raiz do projeto — contém assets/, dist/, src/, sig.spec."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parents[1]
def settings_path() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"
def hostname_online(hostname: str) -> bool:
    """True se o hostname resolve na rede (ex.: o servidor local 'servidor')."""
    try:
        socket.gethostbyname(hostname)
        return True
    except OSError:
        return False
def imei_history_path() -> Path:
    return settings_path().parent / IMEI_HISTORY_FILE
