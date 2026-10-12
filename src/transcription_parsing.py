"""Parsing das respostas de transcricao dos provedores STT (REST e WebSocket).

Converte o JSON/texto cru de cada provedor em ParsedTranscription (texto + marcas
de tempo + palavras). Nao faz rede, nao conhece Tkinter, nao grava arquivos."""

import json
import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedTranscription:
    text: str
    timestamped_text: str = ""


@dataclass(frozen=True)
class TimedTranscriptEntry:
    text: str
    start: float
    end: float
    speaker: str | None = None
    kind: str = "word"


def timestamp_entries(raw: bytes, provider: str) -> list[TimedTranscriptEntry]:
    """Tempos reais de cada API em segundos, sem duração/palavras estimadas.

    Usado para separar um áudio concatenado. Não altera o parser de exibição,
    que pode completar um ``end`` ausente para desenhar marcas no texto.
    """
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("A resposta concatenada precisa ser JSON com timestamps.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Formato de resposta concatenada inválido.")
    kind, scale = "word", 1.0
    if provider == "deepgram":
        channels = (payload.get("results") or {}).get("channels") or []
        alternatives = (channels[0].get("alternatives") or []) if channels else []
        items = alternatives[0].get("words") or [] if alternatives else []
    elif provider == "metamuse":
        items, scale, kind = payload.get("turns") or [], 0.001, "turn"
    elif provider == "alibaba":
        output = payload.get("output") or {}
        if isinstance(output.get("output"), dict):
            output = output["output"]
        sentences = output.get("sentences") or [output.get("sentence") or {}]
        items = [word for sentence in sentences for word in sentence.get("words", [])]
        scale = 0.001
    elif provider == "gemini" and "words" not in payload:
        items = [annotation for step in payload.get("steps", []) if step.get("type") == "model_output"
                 for content in step.get("content", []) for annotation in content.get("annotations", [])
                 if annotation.get("type") == "word_info"]
    else:
        items = payload.get("words") or []
        scale = 0.001 if provider == "assemblyai" else 1.0
    if not isinstance(items, list):
        raise ValueError("A lista de timestamps da API é inválida.")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Um item da API não contém timestamps válidos.")
        if item.get("type") in ("spacing", "audio_event"):
            continue
        text = str(item.get("punctuated_word") or item.get("text") or item.get("word") or item.get("transcript") or "").strip()
        if not text:
            continue
        if provider == "metamuse":
            start, end = item.get("startMs"), item.get("endMs")
        elif provider == "alibaba":
            start, end = item.get("begin_time"), item.get("end_time")
            text += str(item.get("punctuation") or "")
        else:
            start, end = item.get("start", item.get("start_offset")), item.get("end", item.get("end_offset"))
        try:
            start = float(str(start).removesuffix("s")) * scale
            # Alguns Grok REST retornam só start. A origem ainda é conhecida
            # por esse ponto; nunca fabricar uma duração para separar arquivos.
            end = start if end is None and provider == "grok" else float(str(end).removesuffix("s")) * scale
        except (ValueError, TypeError) as exc:
            raise ValueError("A API devolveu texto sem timestamp; não é possível separar os arquivos com segurança.") from exc
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
            raise ValueError("A API devolveu timestamps inválidos para a concatenação.")
        speaker = item.get("speaker", item.get("speaker_id"))
        result.append(TimedTranscriptEntry(text, start, end, str(speaker) if speaker is not None else None, kind))
    return result


def _format_transcription_timestamp(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _timed_entry(value) -> tuple[str, float, float] | None:
    if not isinstance(value, dict):
        return None
    text = next((str(value.get(key) or "").strip() for key in ("text", "word", "transcript") if str(value.get(key) or "").strip()), "")
    if not text:
        return None
    timestamp = value.get("timestamp")
    start = value.get("start", value.get("start_time"))
    end = value.get("end", value.get("end_time"))
    if isinstance(timestamp, list) and len(timestamp) >= 2:
        start = timestamp[0] if start is None else start
        end = timestamp[1] if end is None else end
    try:
        start_value = float(start)
        if end is None and value.get("duration") is not None:
            end = start_value + float(value["duration"])
        end_value = float(end)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(start_value) or not math.isfinite(end_value) or start_value < 0 or end_value < start_value:
        return None
    return text, start_value, end_value


def _timed_word_entries(items, total_duration=None) -> list[tuple[str, float, float]]:
    """Normalize Grok word timestamps, whose final word often lacks ``end``."""
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = next(
            (
                str(item.get(key) or "").strip()
                for key in ("text", "word", "transcript")
                if str(item.get(key) or "").strip()
            ),
            "",
        )
        if not text:
            continue
        timestamp = item.get("timestamp")
        start = item.get("start", item.get("start_time"))
        end = item.get("end", item.get("end_time"))
        if isinstance(timestamp, list) and timestamp:
            start = timestamp[0] if start is None else start
            if len(timestamp) >= 2:
                end = timestamp[1] if end is None else end
        try:
            start_value = float(start)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start_value) or start_value < 0:
            continue
        try:
            end_value = float(end) if end is not None else None
        except (TypeError, ValueError):
            end_value = None
        if end_value is not None and (
            not math.isfinite(end_value) or end_value < start_value
        ):
            end_value = None
        candidates.append([text, start_value, end_value])

    try:
        duration_value = float(total_duration)
        if not math.isfinite(duration_value) or duration_value < 0:
            duration_value = None
    except (TypeError, ValueError):
        duration_value = None

    normalized = []
    for index, (text, start_value, end_value) in enumerate(candidates):
        if end_value is None and index + 1 < len(candidates):
            next_start = candidates[index + 1][1]
            if next_start > start_value:
                end_value = next_start
        if end_value is None and duration_value is not None and duration_value > start_value:
            end_value = duration_value
        if end_value is None:
            end_value = start_value + max(0.08, min(0.6, len(text) * 0.08))
        normalized.append((text, start_value, max(start_value, end_value)))
    return normalized


def _timestamped_text_from_json(value) -> str:
    if isinstance(value, dict):
        for key, group_words in (("segments", False), ("words", True)):
            items = value.get(key)
            if not isinstance(items, list):
                continue
            entries = (
                _timed_word_entries(items, value.get("duration"))
                if group_words
                else [entry for item in items if (entry := _timed_entry(item))]
            )
            if not entries:
                continue
            if group_words:
                phrases: list[tuple[str, float, float]] = []
                words: list[str] = []
                phrase_start = entries[0][1]
                phrase_end = entries[0][2]
                for index, (word, _start, end) in enumerate(entries):
                    if words and not re.fullmatch(r"[,.;:!?]", word):
                        words.append(" ")
                    words.append(word)
                    phrase_end = end
                    if re.search(r"[.!?]$", word) or index == len(entries) - 1:
                        phrases.append(("".join(words).strip(), phrase_start, phrase_end))
                        words = []
                        if index < len(entries) - 1:
                            phrase_start = entries[index + 1][1]
                entries = phrases
            return "\n".join(
                f"[{_format_transcription_timestamp(start)} -> {_format_transcription_timestamp(end)}] {text}"
                for text, start, end in entries
            )
        direct = _timed_entry(value)
        if direct:
            text, start, end = direct
            return f"[{_format_transcription_timestamp(start)} -> {_format_transcription_timestamp(end)}] {text}"
        found = [_timestamped_text_from_json(item) for item in value.values()]
        return "\n".join(item for item in found if item)
    if isinstance(value, list):
        found = [_timestamped_text_from_json(item) for item in value]
        return "\n".join(item for item in found if item)
    return ""


def parse_transcription_response(raw: bytes) -> ParsedTranscription:
    text = raw.decode("utf-8-sig", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ParsedTranscription(text.strip())

    # O Deepgram marca "transaction_key": "deprecated" em TODA resposta
    # (inclusive nas normais, com transcript). Então a regra certa é:
    # 1) se existe transcript real -> usa (o aviso no metadata é ruído);
    # 2) sem transcript, se a resposta é aviso/erro -> vazio (não vazar metadados);
    # 3) campo de transcript presente, mas vazio -> vazio;
    # 4) formato sem campos conhecidos e sem aviso -> texto cru (compatibilidade).
    def _find_transcript(value):
        """Primeiro conteúdo não vazio sob chaves de transcrição conhecidas."""
        if isinstance(value, dict):
            for key in ("text", "transcription", "transcript", "result", "output"):
                if key in value:
                    item = value[key]
                    if isinstance(item, str) and item.strip():
                        return item.strip()
            for item in value.values():
                found = _find_transcript(item)
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = _find_transcript(item)
                if found:
                    return found
        return None

    _WARNING_KEYS = ("deprecated", "error", "message", "detail", "warn", "warning", "status")
    _WARNING_VALUE_MARKERS = ("deprecated", "unauthorized")

    def _is_warning(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in _WARNING_KEYS:
                    return True
                if isinstance(item, str) and any(marker in item.casefold() for marker in _WARNING_VALUE_MARKERS):
                    return True
            return any(_is_warning(item) for item in value.values())
        if isinstance(value, list):
            return any(_is_warning(item) for item in value)
        return False

    recognized_transcript = False

    def collect(value):
        nonlocal recognized_transcript
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, list):
            found = []
            for item in value:
                found.extend(collect(item))
            return found
        if isinstance(value, dict):
            has_direct_field = False
            for key in ("text", "transcription", "transcript", "result", "output"):
                if key in value:
                    if isinstance(value[key], str) or value[key] is None:
                        has_direct_field = True
                        recognized_transcript = True
                    direct = collect(value[key])
                    if direct:
                        return direct
            for key in ("results", "files", "items", "data", "transcriptions"):
                if key in value:
                    nested = collect(value[key])
                    if nested:
                        return nested
            if "segments" in value:
                segments = collect(value["segments"])
                if segments:
                    return ["".join(segments)]
            if has_direct_field:
                return []
            found = []
            for item in value.values():
                if isinstance(item, (dict, list)):
                    found.extend(collect(item))
            return found
        return []

    pieces = collect(payload)
    if pieces and _find_transcript(payload):
        return ParsedTranscription(
            "\n".join(pieces).strip(),
            _timestamped_text_from_json(payload).strip(),
        )
    # Um campo vazio é uma resposta STT válida, não texto cru de compatibilidade.
    if recognized_transcript or _is_warning(payload):
        return ParsedTranscription("")
    return ParsedTranscription(text.strip(), _timestamped_text_from_json(payload).strip())


def extract_text_from_response(raw: bytes) -> str:
    return parse_transcription_response(raw).text
