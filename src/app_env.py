"""Identidade, caminhos e capacidade da maquina.

Responsabilidade unica: responder 'onde fica isto' (pastas, arquivos de
configuracao, host da maquina) e 'quanto esta maquina aguenta' (opcoes de
paralelismo por numero de nucleos). Nao le nem grava dados; nao conhece Tkinter.
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


def cpu_parallel_options(cpu_count: int) -> list[int]:
    """Opções de Conversões paralelas: n/2, n, 2n e 4n núcleos (exemplos do
    usuário: 6 núcleos -> 3, 6, 12, 24; Xeon 18 -> 9, 18, 36, 72)."""
    half = max(1, cpu_count // 2)
    return sorted({half, cpu_count, cpu_count * 2, cpu_count * 4})


def default_parallelism(cpu_count: int) -> int:
    """Valor padrão das slidebars de paralelismo: metade dos núcleos (n/2).

    Tratamento inteligente para número ímpar de núcleos (regra do usuário):
    - arredonda n/2 para o inteiro mais próximo, sem nunca zerar;
    - 1 núcleo  -> 1 (n/2 = 0.5 -> 1, nunca 0);
    - 3 núcleos -> 2 (n/2 = 1.5 -> 2, não 1);
    - 5 núcleos -> 3 (n/2 = 2.5 -> 3);
    - 18 núcleos -> 9 (n/2 = 9).
    """
    return max(1, (cpu_count + 1) // 2)
