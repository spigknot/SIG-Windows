"""Duracao de midia: cabecalho WAV (barato) e sonda externa (ffprobe/ffmpeg).

Regra do usuario (13/09): o resumo antes do envio precisa da soma das duracoes do
AUDIO QUE SERA ENVIADO. O caminho barato — ler o cabecalho do WAV — cobre o
fluxo normal ("Enviar pronto" e a saida do VAD) e custa ~0,09 ms por arquivo
(medido nesta maquina: 76 ms para 830 arquivos). A sonda externa existe para os
arquivos que NAO sao WAV e e CARA (~83 ms com ffprobe, ~127 ms com ffmpeg -i,
medidos): quem chama deve paralelizar e rodar fora da UI.

Sem Tkinter, sem estado: so medicao de arquivo.
"""

import os
import re
import subprocess
import wave
from pathlib import Path


def wav_duration_seconds(path: Path) -> float | None:
    """Duracao de um WAV pelo CABECALHO (nao abre/decodifica o audio).

    Devolve None quando o arquivo nao e WAV ou quando o cabecalho nao pode ser
    lido — quem chama decide se vale a pena a sonda externa.
    """
    if path.suffix.lower() != ".wav":
        return None
    try:
        with wave.open(str(path), "rb") as fonte:
            taxa = fonte.getframerate() or 1
            return fonte.getnframes() / float(taxa)
    except (wave.Error, OSError, EOFError):
        return None


def _run(command: list[str]) -> str:
    resultado = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return (resultado.stderr or "") + (resultado.stdout or "")


def _ffprobe_duration_seconds(path: Path, ffprobe: Path) -> float:
    try:
        texto = _run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ]
        )
        return float(texto.strip().splitlines()[0]) if texto.strip() else 0.0
    except (OSError, ValueError, IndexError):
        return 0.0


def _ffmpeg_duration_seconds(path: Path, ffmpeg: Path) -> float:
    """Reserva quando nao ha ffprobe: o `Duration:` do `ffmpeg -i`."""
    try:
        texto = _run([str(ffmpeg), "-hide_banner", "-i", str(path)])
    except OSError:
        return 0.0
    casamento = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", texto)
    if not casamento:
        return 0.0
    return (
        int(casamento.group(1)) * 3600
        + int(casamento.group(2)) * 60
        + float(casamento.group(3))
    )


def probe_duration_seconds(
    path: Path, *, ffprobe: Path | None = None, ffmpeg: Path | None = None
) -> float:
    """Duracao por sonda externa (ffprobe primeiro, `ffmpeg -i` como reserva).

    Devolve 0.0 quando nenhuma sonda consegue medir — o chamador trata 0.0 como
    "nao medido", nunca como "arquivo vazio".
    """
    if ffprobe is not None and ffprobe.exists():
        segundos = _ffprobe_duration_seconds(path, ffprobe)
        if segundos:
            return segundos
    if ffmpeg is not None and ffmpeg.exists():
        return _ffmpeg_duration_seconds(path, ffmpeg)
    return 0.0


def audio_duration_seconds(
    path: Path, *, ffprobe: Path | None = None, ffmpeg: Path | None = None
) -> float | None:
    """Duracao do arquivo: cabecalho WAV (barato) primeiro, sonda externa depois."""
    direto = wav_duration_seconds(path)
    if direto is not None:
        return direto
    return probe_duration_seconds(path, ffprobe=ffprobe, ffmpeg=ffmpeg) or None
