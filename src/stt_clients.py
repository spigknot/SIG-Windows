"""Protocolo de cada provedor STT: URLs, campos de formulario, handshake e
chamadas REST/WebSocket especificos (Grok, Deepgram, AssemblyAI, ElevenLabs,
MetaMuse, Alibaba).

Regra: diferencas entre provedores sao intencionais e NAO devem ser unificadas.
Para adicionar campos novos, edite transcription_form_fields (um lugar so).
Constantes do provedor: providers.py. Parsing da resposta: transcription_parsing.py."""

import base64
import http.client
import json
import os
import re
import subprocess
import threading
import urllib.request
import uuid
from app_env import app_base_dir
from domain_models import Cancelled
from http_clients import GraniteUploader
from pathlib import Path
from providers import (
    ALIBABA_REST_MODEL,
    ALIBABA_REST_URL,
    ALIBABA_WS_MODEL,
    META_MUSE_MODEL,
    META_MUSE_STT_URL,
    selected_transcription_server,
)
from stt_provider_rules import alibaba_language_hints, metamuse_language_bias, metamuse_mode
from transcription_parsing import extract_text_from_response
from urllib.parse import urlparse
import stt_provider_rules


def transcribe_url(settings: dict) -> str:
    url = selected_transcription_server(settings)["url"]
    if is_deepgram_transcription(settings):
        url = f"{url}?{deepgram_query_string(settings)}"
    return url


def probe_duration_ms(path: Path) -> int:
    """Duração real do arquivo em ms via ffmpeg (0 se não for possível medir)."""
    try:
        ffmpeg = app_base_dir() / "ffmpeg.exe"
        if not ffmpeg.exists():
            return 0
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-i", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr + result.stdout)
        if not match:
            return 0
        seconds = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
        return int(seconds * 1000)
    except Exception:
        return 0


def deepgram_keyterms_list(settings: dict) -> list[str]:
    """Termos de reforço do Deepgram (keyterm prompting), separados por vírgula."""
    raw = str(settings.get("deepgram_keyterms") or "")
    return [term.strip() for term in raw.replace("\n", ",").split(",") if term.strip()]


def deepgram_query_string(settings: dict, language: str | None = None, diarize: bool = False) -> str:
    """Parâmetros do Deepgram Nova 3 (REST e WS) — espelho do app Android."""
    if language is None:
        language = stt_provider_rules.deepgram_language_param(settings)
    params = ["model=nova-3", f"language={language}", "smart_format=true", "punctuate=true"]
    if diarize or settings.get("diarize") or settings.get("grok_diarize"):
        diarize_param = stt_provider_rules.deepgram_diarize_query(True)
        if diarize_param:
            params.append(diarize_param)
    for term in deepgram_keyterms_list(settings):
        params.append(f"keyterm={urllib.parse.quote(term)}")
    return "&".join(params)


def is_grok_transcription(settings: dict) -> bool:
    return selected_transcription_server(settings).get("is_grok_api", False)


def is_deepgram_transcription(settings: dict) -> bool:
    return selected_transcription_server(settings).get("is_deepgram_api", False)


def is_assemblyai_transcription(settings: dict) -> bool:
    return selected_transcription_server(settings).get("is_assemblyai_api", False)


def is_elevenlabs_transcription(settings: dict) -> bool:
    return selected_transcription_server(settings).get("is_elevenlabs_api", False)


def is_metamuse_transcription(settings: dict) -> bool:
    return selected_transcription_server(settings).get("is_metamuse_api", False)


def is_alibaba_transcription(settings: dict) -> bool:
    return selected_transcription_server(settings).get("is_alibaba_api", False)


def transcription_form_fields(settings: dict) -> dict:
    diarize_checked = bool(settings.get("diarize") or settings.get("grok_diarize"))
    if is_grok_transcription(settings):
        fields = {"format": "true", "filler_words": "false"}
        language = stt_provider_rules.grok_language_param(settings)
        if language:
            fields["language"] = language
        if stt_provider_rules.grok_rest_diarize(diarize_checked):
            fields["diarize"] = "true"
        return fields
    if is_deepgram_transcription(settings):
        # No fluxo Deepgram os parâmetros viajam na URL (raw body); o dict
        # fica vazio apenas para manter a assinatura do uploader.
        return {}
    if is_assemblyai_transcription(settings):
        fields: dict = {}
        detection, code = stt_provider_rules.assemblyai_rest_language(settings)
        if detection:
            fields["language_detection"] = "true"
        if code:
            fields["language_code"] = code
        speaker_labels, punctuate = stt_provider_rules.assemblyai_rest_diarize(diarize_checked)
        if speaker_labels:
            fields["speaker_labels"] = "true"
            fields["punctuate"] = "true"
        return fields
    if is_elevenlabs_transcription(settings):
        fields = {}
        code = stt_provider_rules.elevenlabs_rest_language_code(settings)
        if code:
            fields["language_code"] = code
        if stt_provider_rules.elevenlabs_rest_diarize(diarize_checked):
            fields["diarize"] = "true"
        return fields
    if is_metamuse_transcription(settings):
        # O Muse monta o corpo REST dedicado (parte JSON "request" + parte
        # "audio"); não há campos de formulário — a assinatura fica vazia
        # apenas para manter o contrato do uploader.
        return {}
    if is_alibaba_transcription(settings):
        # O Alibaba monta o JSON DashScope dedicado; sem form fields.
        return {}
    return selected_transcription_server(settings)["parameters"].copy()


def create_transcription_uploader(cancel_event: threading.Event, settings: dict) -> "GraniteUploader":
    if is_grok_transcription(settings):
        api_key = str(settings.get("grok_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Insira a chave API do Grok nas configurações.")
        return GraniteUploader(
            cancel_event,
            transcription_form_fields(settings),
            {"Authorization": f"Bearer {api_key}"},
            "file",
        )
    if is_deepgram_transcription(settings):
        api_key = str(settings.get("deepgram_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Insira a chave API do Deepgram nas configurações.")
        return GraniteUploader(
            cancel_event,
            {},
            {"Authorization": f"Token {api_key}"},
            "file",
            raw_body=True,
        )
    if is_assemblyai_transcription(settings):
        api_key = str(settings.get("assemblyai_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Insira a chave API da AssemblyAI nas configurações.")
        return GraniteUploader(
            cancel_event,
            {},
            {
                "Authorization": api_key,
                "X-AAI-Model": "u3-sync-pro",
            },
            "audio",
        )
    if is_elevenlabs_transcription(settings):
        api_key = str(settings.get("elevenlabs_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Insira a chave API da ElevenLabs nas configurações.")
        return GraniteUploader(
            cancel_event,
            {"model_id": "scribe_v2"},
            {"xi-api-key": api_key},
            "file",
        )
    if is_metamuse_transcription(settings):
        api_key = str(settings.get("metamuse_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Insira a chave API do Meta Muse Voice nas configurações.")
        # O REST do Muse usa corpo dedicado (ver metamuse_rest_transcribe);
        # este uploader valida a chave e serve aos fluxos que só precisam
        # de um uploader presente (cancelamento, multi-modelo).
        return GraniteUploader(cancel_event, {}, {}, "file")
    if is_alibaba_transcription(settings):
        api_key = str(settings.get("alibaba_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Insira a chave API do Alibaba Cloud nas configurações.")
        # O REST do Alibaba usa JSON DashScope dedicado (ver
        # alibaba_rest_transcribe); este uploader só valida a chave.
        return GraniteUploader(cancel_event, {}, {}, "file")
    return GraniteUploader(cancel_event, transcription_form_fields(settings))


def metamuse_handshake_payload(api_key: str, diarize_checked: bool, settings: dict) -> dict:
    """Primeiro frame textual do WebSocket do Muse (configuração da sessão).

    A credencial viaja dentro do JSON em ``authorization.accessToken``
    (o handshake não usa header Authorization). Sem diarização o modo é
    ENDPOINTING; com diarização, DIARIZATION.
    """
    payload = {
        "authorization": {"accessToken": api_key},
        "audioEncoding": "PCM_16KHZ",
        "model": META_MUSE_MODEL,
        "mode": metamuse_mode(bool(diarize_checked)),
        "partialMode": "CUMULATIVE",
        "emitAudioProgress": False,
    }
    language_bias = metamuse_language_bias(settings)
    if language_bias:
        payload["languageBias"] = language_bias
    return payload


def metamuse_rest_request_body(diarize_checked: bool, settings: dict) -> dict:
    """Parte JSON \"request\" do REST do Muse (multipart com a parte \"audio\")."""
    body = {
        "mode": metamuse_mode(bool(diarize_checked)),
        "model": META_MUSE_MODEL,
        "audioEncoding": "WAV",
    }
    language_bias = metamuse_language_bias(settings)
    if language_bias:
        body["languageBias"] = language_bias
    return body


def metamuse_format_rest_response(payload: dict, diarize_checked: bool) -> str:
    """Texto final do REST do Muse: turnos diarizados ou transcript único.

    Os rótulos de falante são letras ("A", "B", ...) — viram
    "Interlocutor 1/2/..." na ordem de aparição, como no restante do app.
    """
    if not isinstance(payload, dict):
        return ""
    if diarize_checked:
        turns = payload.get("turns")
        if isinstance(turns, list) and turns:
            order: dict[str, int] = {}
            lines = []
            for turn in turns:
                if not isinstance(turn, dict):
                    continue
                text = str(turn.get("transcript") or "").strip()
                if not text:
                    continue
                label = str(turn.get("speaker") or "").strip()
                if label:
                    if label not in order:
                        order[label] = len(order) + 1
                    lines.append(f"Interlocutor {order[label]}: {text}")
                else:
                    lines.append(text)
            if lines:
                return "\n".join(lines).strip()
    return str(payload.get("transcript") or "").strip()


def metamuse_rest_transcribe(
    cancel_event: threading.Event,
    settings: dict,
    audio_path: Path,
    raw_path: Path | None = None,
) -> str:
    """Transcreve um WAV pelo REST do Muse (POST multipart dedicado)."""
    api_key = str(settings.get("metamuse_api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Insira a chave API do Meta Muse Voice nas configurações.")
    if cancel_event.is_set():
        raise Cancelled()
    size = audio_path.stat().st_size
    if size > 32 * 1024 * 1024:
        raise RuntimeError(
            "O áudio passa de 32 MB; o endpoint REST do Muse aceita no máximo "
            "32 MB (ou 10 minutos). Divida o áudio ou use o streaming ao vivo."
        )
    diarize_checked = bool(settings.get("diarize") or settings.get("grok_diarize"))
    request_body = json.dumps(metamuse_rest_request_body(diarize_checked, settings), ensure_ascii=False)
    boundary = f"----sigmuse-{uuid.uuid4().hex}"
    crlf = chr(13) + chr(10)
    preamble = (
        f"--{boundary}" + crlf
        + 'Content-Disposition: form-data; name="request"' + crlf
        + "Content-Type: application/json" + crlf + crlf
        + f"{request_body}" + crlf
        + f"--{boundary}" + crlf
        + f'Content-Disposition: form-data; name="audio"; filename="{audio_path.name}"' + crlf
        + "Content-Type: audio/wav" + crlf + crlf
    ).encode("utf-8")
    ending = (crlf + f"--{boundary}--" + crlf).encode("utf-8")
    parsed = urlparse(META_MUSE_STT_URL)
    conn = http.client.HTTPSConnection(parsed.netloc, timeout=60 * 60)
    try:
        conn.putrequest("POST", parsed.path or "/")
        conn.putheader("accept", "application/json")
        conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        conn.putheader("Content-Length", str(len(preamble) + size + len(ending)))
        conn.putheader("Authorization", f"Bearer {api_key}")
        conn.endheaders()
        conn.send(preamble)
        with audio_path.open("rb") as handle:
            while True:
                if cancel_event.is_set():
                    raise Cancelled()
                chunk = handle.read(1024 * 128)
                if not chunk:
                    break
                conn.send(chunk)
        conn.send(ending)
        if cancel_event.is_set():
            raise Cancelled()
        response = conn.getresponse()
        raw = response.read()
        status = response.status
    finally:
        conn.close()
    if raw_path is not None:
        try:
            raw_path.write_bytes(raw)
        except OSError:
            pass
    if status != 200:
        raise RuntimeError(f"HTTP {status}\n{raw.decode('utf-8', errors='replace')[:500]}")
    try:
        payload = json.loads(raw.decode("utf-8-sig", errors="replace") or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"resposta inválida do Muse: {exc}") from exc
    return metamuse_format_rest_response(payload, diarize_checked)


ALIBABA_AUTH_ERROR = "API Key do Alibaba Cloud inválida ou incompatível com a região Singapore."

PARAMS_BLOCK_TAG_PREFIX = "params_block:"


def alibaba_rest_body(audio_data_uri: str, settings: dict) -> dict:
    """Corpo JSON do REST DashScope nativo (fun-asr-flash)."""
    parameters: dict = {"format": "wav", "sample_rate": 16000}
    hints = alibaba_language_hints(settings)
    if hints:
        parameters["language_hints"] = hints
    return {
        "model": ALIBABA_REST_MODEL,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": audio_data_uri},
                        }
                    ],
                }
            ]
        },
        "parameters": parameters,
    }


def alibaba_format_rest_response(payload: dict) -> str:
    """Extrai o texto do REST DashScope (output.text, choices ou genérico)."""
    if not isinstance(payload, dict):
        return ""
    output = payload.get("output")
    if isinstance(output, dict):
        text = output.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        choices = output.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message") or {}
                content = message.get("content") if isinstance(message, dict) else None
                if isinstance(content, str) and content.strip():
                    return content.strip()
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            part_text = part.get("text")
                            if isinstance(part_text, str) and part_text.strip():
                                return part_text.strip()
    return extract_text_from_response(json.dumps(payload).encode("utf-8"))


def alibaba_rest_transcribe(
    cancel_event: threading.Event,
    settings: dict,
    audio_path: Path,
    raw_path: Path | None = None,
) -> str:
    """Transcreve um WAV pelo REST DashScope nativo (fun-asr-flash)."""
    api_key = str(settings.get("alibaba_api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Insira a chave API do Alibaba Cloud nas configurações.")
    if cancel_event.is_set():
        raise Cancelled()
    wav_bytes = audio_path.read_bytes()
    data_uri = "data:audio/wav;base64," + base64.b64encode(wav_bytes).decode("ascii")
    body = json.dumps(alibaba_rest_body(data_uri, settings), ensure_ascii=False).encode("utf-8")
    parsed = urlparse(ALIBABA_REST_URL)
    conn = http.client.HTTPSConnection(parsed.netloc, timeout=60 * 60)
    try:
        conn.putrequest("POST", parsed.path or "/")
        conn.putheader("accept", "application/json")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(len(body)))
        conn.putheader("Authorization", f"Bearer {api_key}")
        conn.putheader("X-DashScope-SSE", "disable")
        conn.endheaders()
        for offset in range(0, len(body), 1024 * 128):
            if cancel_event.is_set():
                raise Cancelled()
            conn.send(body[offset:offset + 1024 * 128])
        if cancel_event.is_set():
            raise Cancelled()
        response = conn.getresponse()
        raw = response.read()
        status = response.status
    finally:
        conn.close()
    if raw_path is not None:
        try:
            raw_path.write_bytes(raw)
        except OSError:
            pass
    if status in (401, 403):
        raise RuntimeError(f"{ALIBABA_AUTH_ERROR} (HTTP {status})")
    if status == 429:
        raise RuntimeError("Alibaba Cloud: rate limit / limite de uso excedido (HTTP 429). Aguarde e tente novamente.")
    try:
        payload = json.loads(raw.decode("utf-8-sig", errors="replace") or "{}")
    except json.JSONDecodeError:
        payload = {}
    code = str(payload.get("code") or "") if isinstance(payload, dict) else ""
    message = str(payload.get("message") or "") if isinstance(payload, dict) else ""
    if code in ("InvalidApiKey", "Unauthorized", "Forbidden", "AccessDenied"):
        raise RuntimeError(ALIBABA_AUTH_ERROR)
    if code == "CLIENT_ERROR" and "NO_WORDS" in message:
        # Áudio sem fala reconhecível: equivale a transcrição vazia.
        return ""
    if status != 200:
        raise RuntimeError(f"HTTP {status}\n{raw.decode('utf-8', errors='replace')[:500]}")
    if code:
        raise RuntimeError(f"{code}: {message or 'erro desconhecido'}")
    return alibaba_format_rest_response(payload)


def alibaba_ws_run_task(task_id: str, settings: dict) -> dict:
    """Evento run-task do WebSocket DashScope (qwen-audio-3.0-asr-flash-streaming)."""
    parameters: dict = {"format": "pcm", "sample_rate": 16000, "heartbeat": True}
    hints = alibaba_language_hints(settings)
    if hints:
        parameters["language_hints"] = hints
    return {
        "header": {"action": "run-task", "task_id": task_id, "streaming": "duplex"},
        "payload": {
            "task_group": "audio",
            "task": "asr",
            "function": "recognition",
            "model": ALIBABA_WS_MODEL,
            "parameters": parameters,
            "input": {},
        },
    }


def alibaba_ws_finish_task(task_id: str) -> dict:
    """Evento finish-task do WebSocket DashScope (mesmo task_id do run-task)."""
    return {
        "header": {"action": "finish-task", "task_id": task_id, "streaming": "duplex"},
        "payload": {"input": {}},
    }


def alibaba_ws_sentence_text(event: dict) -> tuple[str, bool]:
    """(texto, é_final) de um evento result-generated.

    Frase com `sentence_end: true` é segmento fechado (commit); o resto é
    parcial (rascunho). Formatos desconhecidos viram rascunho.
    """
    if not isinstance(event, dict):
        return "", False
    try:
        sentence = ((event.get("payload") or {}).get("output") or {}).get("sentence") or {}
    except AttributeError:
        return "", False
    if not isinstance(sentence, dict):
        return "", False
    text = str(sentence.get("text") or "").strip()
    if sentence.get("sentence_end") is True:
        return text, True
    return text, ("end_time" in sentence) and (sentence.get("end_time") is not None)


def metamuse_ws_log_params(settings: dict, diarize_checked: bool) -> dict:
    """Parâmetros efetivos do handshake do Muse para o log (sem segredo)."""
    payload = metamuse_handshake_payload("***", diarize_checked, settings)
    payload.pop("authorization", None)
    bias = payload.pop("languageBias", None)
    payload["languageBias"] = bias if bias else "auto (omitido)"
    return payload


def alibaba_ws_log_params(settings: dict) -> dict:
    """Parâmetros efetivos do run-task do Alibaba para o log (sem segredo)."""
    params: dict = {
        "model": ALIBABA_WS_MODEL,
        "format": "pcm",
        "sample_rate": 16000,
        "heartbeat": True,
    }
    hints = alibaba_language_hints(settings)
    params["language_hints"] = hints if hints else "auto (omitido)"
    return params


def alibaba_rest_log_params(settings: dict) -> dict:
    """Parâmetros do REST Alibaba para o log (sem o áudio base64)."""
    params: dict = {
        "model": ALIBABA_REST_MODEL,
        "format": "wav",
        "sample_rate": 16000,
    }
    hints = alibaba_language_hints(settings)
    params["language_hints"] = hints if hints else "auto (omitido)"
    return params
