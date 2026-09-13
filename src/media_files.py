"""Tipos de arquivo de midia suportados: extensoes e MIME.

Fonte unica das extensoes aceitas (dialogs, drag&drop, validacao de WAV)."""

import wave
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".ogg",
    ".opus",
    ".flac",
    ".aac",
    ".wma",
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
}


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


AUDIO_EXTENSIONS = SUPPORTED_EXTENSIONS - VIDEO_EXTENSIONS


MIME_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".zip": "application/zip",
}


def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def is_transcription_ready_wav(path: Path) -> bool:
    """Retorna se o WAV já atende ao formato exigido pelo servidor."""
    if path.suffix.lower() != ".wav":
        return False
    try:
        with wave.open(str(path), "rb") as source:
            return (
                source.getcomptype() == "NONE"
                and source.getnchannels() == 1
                and source.getframerate() == 16000
                and source.getsampwidth() == 2
            )
    except (wave.Error, OSError, EOFError):
        return False


_OPUS_HEAD = b"OpusHead"


def is_transcription_ready_compressed(path: Path) -> bool:
    """Retorna se o arquivo já está no formato compacto que o app envia.

    Mesmo alvo da conversão "Enviar compactado" (Ogg/Opus, 16 kHz, mono): o
    cabeçalho `OpusHead` traz o número de canais (byte 9) e a taxa de entrada
    (4 bytes little-endian, offset 12). Sem isso o arquivo é reconvertido — o
    que é só desperdício, nunca incorreto (regra do usuário, 13/09).
    """
    if path.suffix.lower() not in {".ogg", ".opus"}:
        return False
    try:
        with path.open("rb") as source:
            head = source.read(1024)
    except OSError:
        return False
    pos = head.find(_OPUS_HEAD)
    if pos < 0 or pos + 16 > len(head):
        return False
    channels = head[pos + 9]
    sample_rate = int.from_bytes(head[pos + 12:pos + 16], "little")
    return channels == 1 and sample_rate == 16000
