"""WAV concatenado e agrupamento de arquivos para STT, sem UI ou rede.

Preserva PCM dos arquivos preparados, guarda fronteiras por amostra e nunca
estima a origem de texto sem timestamps. Os limites pertencem ao provedor.
"""
from __future__ import annotations

import json
import re
import wave
from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass
from pathlib import Path

from domain_models import Cancelled
from providers import transcription_provider_for_server
from stt_provider_rules import keywords_for_provider
from transcription_parsing import TimedTranscriptEntry

SAMPLE_RATE = 16000
GEMINI_MAX_AUDIO_SECONDS = 1800
GEMINI_MAX_BATCH_SECONDS = GEMINI_MAX_AUDIO_SECONDS
GAP_FRAMES = 2 * SAMPLE_RATE
EDGE_FRAMES = SAMPLE_RATE
BOUNDARY_TOLERANCE = 0.08
SUPPORTED_PROVIDERS = {"grok", "deepgram", "assemblyai", "gemini", "elevenlabs", "metamuse", "alibaba"}


@dataclass(frozen=True)
class AudioSpan:
    index: int
    name: str
    original_path: str
    prepared_path: str
    start_frame: int
    end_frame: int
    source_index: int | None = None
    source_offset_frames: int = 0

    @property
    def start(self):
        return self.start_frame / SAMPLE_RATE

    @property
    def end(self):
        return self.end_frame / SAMPLE_RATE


@dataclass(frozen=True)
class ConcatenatedAudio:
    path: Path
    manifest: Path
    spans: tuple[AudioSpan, ...]
    frames: int

    @property
    def duration(self):
        return self.frames / SAMPLE_RATE


def concatenation_settings(settings: dict, model_names: list[str]) -> dict:
    for name in model_names:
        provider = transcription_provider_for_server(name)
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"{name}: concatenar exige timestamps na resposta. Escolha um modelo compatível ou desmarque Concatenar áudios.")
        if provider == "gemini" and keywords_for_provider(settings, provider):
            raise ValueError("Gemini: desligue Keywords para concatenar; os timestamps necessários são incompatíveis com vocabulário personalizado.")
    return {**settings, "_concatenate_audio": True, "_request_timestamps": True,
            "gemini_timestamps": True}


def check_limits(audio: ConcatenatedAudio, model_names: list[str]) -> None:
    size = audio.path.stat().st_size
    # Tamanho enviado, incluindo silêncio e header. Um único WAV por lote:
    # nunca iniciar um envio que já exceda o limite de algum modelo marcado.
    limits = {"grok": (None, 500_000_000), "deepgram": (None, 2_000_000_000),
              "assemblyai": (36000, 2_200_000_000), "gemini": (1800, 2 * 1024**3),
              "elevenlabs": (None, 5_000_000_000), "metamuse": (600, 32 * 1024**2),
              "alibaba": (300, 10 * 1024**2)}
    for name in model_names:
        provider = transcription_provider_for_server(name)
        seconds, byte_limit = limits[provider]
        if seconds is not None and audio.duration > seconds:
            raise ValueError(f"{name}: áudio concatenado com {audio.duration:.1f}s; limite de {seconds // 60} minutos, incluindo os silêncios. Reduza o lote.")
        if size > byte_limit:
            raise ValueError(f"{name}: áudio concatenado excede o limite de {byte_limit / 1_000_000:g} MB. Reduza o lote.")


def concatenate_wavs(jobs, destination: Path, cancel_event, progress=lambda _done, _total: None) -> ConcatenatedAudio:
    """Cópia em blocos: zero resampling, crossfade ou memória proporcional ao lote."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".part.wav")
    manifest = destination.with_suffix(".timeline.json")
    spans = []
    frames = EDGE_FRAMES

    def cancelled():
        if cancel_event.is_set():
            raise Cancelled()

    try:
        with wave.open(str(temporary), "wb") as output:
            output.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
            output.writeframesraw(bytes(EDGE_FRAMES * 2))
            for index, job in enumerate(jobs):
                cancelled()
                path = Path(job.upload_path)
                with wave.open(str(path), "rb") as source:
                    if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, SAMPLE_RATE, "NONE"):
                        raise ValueError(f"{job.original_name}: a concatenação exige WAV PCM 16 kHz mono 16-bit.")
                    count = source.getnframes()
                    if not count:
                        raise ValueError(f"{job.original_name}: WAV vazio.")
                    if (frames + count + EDGE_FRAMES) * 2 > 0xFFFFFFFF - 36:
                        raise ValueError("O WAV concatenado excede o tamanho permitido pelo formato RIFF. Reduza o lote.")
                    spans.append(AudioSpan(index, job.original_name, str(job.original_path), str(path),
                                            frames, frames + count, index, 0))
                    copied = 0
                    while chunk := source.readframes(65536):
                        cancelled()
                        if len(chunk) % 2:
                            raise ValueError(f"{job.original_name}: WAV incompleto; amostra PCM truncada.")
                        output.writeframesraw(chunk)
                        copied += len(chunk) // 2
                    if copied != count:
                        raise ValueError(f"{job.original_name}: WAV incompleto; nenhuma requisição foi enviada.")
                    frames += count
                if index < len(jobs) - 1:
                    output.writeframesraw(bytes(GAP_FRAMES * 2))
                    frames += GAP_FRAMES
                progress(index + 1, len(jobs))
            cancelled()
            output.writeframesraw(bytes(EDGE_FRAMES * 2))
            frames += EDGE_FRAMES
        if not spans:
            raise ValueError("Não há áudios válidos para concatenar.")
        temporary.replace(destination)
        data = {"sample_rate": SAMPLE_RATE, "channels": 1, "sample_width": 2,
                "gap_frames": GAP_FRAMES, "edge_frames": EDGE_FRAMES, "total_frames": frames,
                "audio": str(destination), "files": [
                    {**asdict(span), "start_seconds": span.start, "end_seconds": span.end} for span in spans]}
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return ConcatenatedAudio(destination, manifest, tuple(spans), frames)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def group_concatenated_audio_by_files(audio: ConcatenatedAudio, destination: Path, cancel_event,
                                     max_duration_seconds: int = GEMINI_MAX_BATCH_SECONDS,
                                     progress=lambda _done, _total: None) -> list[ConcatenatedAudio]:
    """Agrupa arquivos inteiros em WAVs dentro do limite do Gemini.

    Os grupos mantêm a ordem original e só terminam entre arquivos. O silêncio
    entre arquivos dentro do mesmo grupo conta para o limite. Nenhum áudio é
    recodificado, cortado ou carregado inteiro na memória.
    """
    max_frames = int(max_duration_seconds * SAMPLE_RATE)
    if max_frames <= 0:
        raise ValueError("A duração máxima dos trechos precisa ser positiva.")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    chunks = []

    with wave.open(str(audio.path), "rb") as source:
        params = source.getparams()
        if (params.nchannels, params.sampwidth, params.framerate, params.comptype) != (1, 2, SAMPLE_RATE, "NONE"):
            raise ValueError("O WAV concatenado do Gemini precisa ser PCM 16 kHz mono 16-bit.")
        total_frames = source.getnframes()
        if total_frames != audio.frames:
            raise ValueError("O WAV concatenado diverge da duração registrada na linha do tempo.")
        groups: list[tuple[int, int, list[AudioSpan]]] = []
        group_start = None
        group_end = None
        group_spans: list[AudioSpan] = []
        for span in audio.spans:
            if cancel_event.is_set():
                raise Cancelled()
            span_duration = span.end_frame - span.start_frame
            if span_duration > max_frames:
                raise ValueError(
                    f"Gemini: o arquivo {span.name} tem {span_duration / SAMPLE_RATE / 60:.1f} min "
                    "e excede o limite de 30 minutos. O arquivo não foi cortado; reduza sua duração."
                )
            candidate_start = span.start_frame if group_start is None else group_start
            if group_spans and span.end_frame - candidate_start > max_frames:
                groups.append((group_start, group_end, group_spans))
                group_start, group_end, group_spans = span.start_frame, span.end_frame, [span]
            elif not group_spans:
                group_start, group_end, group_spans = span.start_frame, span.end_frame, [span]
            else:
                group_end = span.end_frame
                group_spans.append(span)
        if group_spans:
            groups.append((group_start, group_end, group_spans))

        for chunk_index, (start_frame, end_frame, parent_spans) in enumerate(groups):
            if cancel_event.is_set():
                raise Cancelled()
            chunk_path = destination / f"gemini_{chunk_index + 1:03}.wav"
            with wave.open(str(chunk_path), "wb") as output:
                output.setparams(params)
                source.setpos(start_frame)
                remaining = end_frame - start_frame
                while remaining:
                    if cancel_event.is_set():
                        raise Cancelled()
                    count = min(65536, remaining)
                    data = source.readframes(count)
                    if not data:
                        raise ValueError("O WAV concatenado terminou antes do limite registrado.")
                    output.writeframesraw(data)
                    remaining -= len(data) // params.nchannels // params.sampwidth

            spans = []
            for parent_span in parent_spans:
                spans.append(AudioSpan(
                    len(spans), parent_span.name, parent_span.original_path, parent_span.prepared_path,
                    parent_span.start_frame - start_frame, parent_span.end_frame - start_frame,
                    parent_span.source_index if parent_span.source_index is not None else parent_span.index,
                    parent_span.source_offset_frames,
                ))
            manifest = chunk_path.with_suffix(".timeline.json")
            manifest.write_text(json.dumps({
                "sample_rate": SAMPLE_RATE,
                "channels": 1,
                "sample_width": 2,
                "parent_manifest": str(audio.manifest),
                "chunk_index": chunk_index,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "total_frames": end_frame - start_frame,
                "audio": str(chunk_path),
                "files": [{
                    **asdict(span),
                    "start_seconds": span.start,
                    "end_seconds": span.end,
                } for span in spans],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            chunks.append(ConcatenatedAudio(chunk_path, manifest, tuple(spans), end_frame - start_frame))
            progress(chunk_index + 1, len(groups))
    return chunks


def split_entries(audio: ConcatenatedAudio, entries: list[TimedTranscriptEntry]) -> tuple[list[list[TimedTranscriptEntry]], int]:
    """Atribuição por interseção real. Trechos que abrangem arquivos falham."""
    groups = [[] for _ in audio.spans]
    discarded = 0
    starts = [span.start for span in audio.spans]
    ends = [span.end for span in audio.spans]
    for entry in entries:
        if entry.start > audio.duration + BOUNDARY_TOLERANCE or entry.end > audio.duration + BOUNDARY_TOLERANCE:
            raise ValueError("A API devolveu timestamps fora da duração do WAV concatenado.")
        first = bisect_right(ends, entry.start + BOUNDARY_TOLERANCE)
        last = bisect_left(starts, entry.end - BOUNDARY_TOLERANCE)
        if last - first > 1:
            raise ValueError("Um trecho da API atravessa mais de um arquivo. Não é possível separar esse texto com segurança; transcreva o lote individualmente.")
        point = entry.start if entry.end == entry.start else (entry.start + entry.end) / 2
        point_index = bisect_right(starts, point) - 1
        matching = [audio.spans[i] for i in (point_index, point_index + 1) if 0 <= i < len(audio.spans)
                    and starts[i] - BOUNDARY_TOLERANCE <= point <= ends[i] + BOUNDARY_TOLERANCE]
        span = audio.spans[first] if last > first else (matching[0] if matching else None)
        if span is None:
            discarded += 1
            continue
        duration = span.end - span.start
        start = min(duration, max(0, entry.start - span.start))
        end = max(start, min(duration, entry.end - span.start))
        groups[span.index].append(TimedTranscriptEntry(entry.text, start, end, entry.speaker, entry.kind))
    return groups, discarded


def entries_text(entries: list[TimedTranscriptEntry], diarize: bool = False) -> str:
    """Pontuação e rótulos de falante locais ao arquivo, nunca ao lote inteiro."""
    lines, words, previous, speakers = [], [], None, {}

    def flush():
        if words:
            text = " ".join(words)
            text = re.sub(r"\s+([,.;:!?%\]\)])", r"\1", text)
            text = re.sub(r"([\[\(])\s+", r"\1", text)
            lines.append(text)
            words.clear()

    for entry in sorted(entries, key=lambda item: item.start):
        if diarize and entry.speaker is not None and entry.speaker != previous:
            flush()
            speakers.setdefault(entry.speaker, len(speakers) + 1)
            words.append(f"Interlocutor {speakers[entry.speaker]}:")
            previous = entry.speaker
        words.append(entry.text)
        if entry.kind == "turn":
            flush()
    flush()
    return "\n".join(lines).strip()
