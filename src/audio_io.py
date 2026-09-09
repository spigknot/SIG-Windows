"""Captura de audio ao vivo: formato PCM e gravacao de WAV.

Constantes de formato usadas pela captura (LIVE_*) e pelos provedores WS."""

import wave
from pathlib import Path


LIVE_SAMPLE_RATE = 16000
LIVE_CHANNELS = 1
LIVE_SAMPLE_WIDTH = 2


def pcm_bytes_for_millis(millis: int) -> int:
    return LIVE_SAMPLE_RATE * LIVE_CHANNELS * LIVE_SAMPLE_WIDTH * millis // 1000


def write_wav_from_pcm_bytes(path: Path, pcm: bytes):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(LIVE_CHANNELS)
        wav.setsampwidth(LIVE_SAMPLE_WIDTH)
        wav.setframerate(LIVE_SAMPLE_RATE)
        wav.writeframes(pcm)


def write_wav_from_pcm_file(path: Path, pcm_path: Path):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(LIVE_CHANNELS)
        wav.setsampwidth(LIVE_SAMPLE_WIDTH)
        wav.setframerate(LIVE_SAMPLE_RATE)
        with pcm_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 128)
                if not chunk:
                    break
                wav.writeframesraw(chunk)
