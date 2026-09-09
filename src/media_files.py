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
