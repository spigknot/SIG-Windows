"""Gemini 3.5 Transcribe: REST Files/Interactions e Live WebSocket.

Documentação: ai.google.dev/gemini-api/docs/transcribe e
ai.google.dev/gemini-api/docs/live-api/live-transcribe. Sem UI ou credenciais
embutidas; a chave vem exclusivamente dos settings fornecidos pelo chamador.
"""
import base64
import http.client
import json
import queue
import re
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from app_env import app_base_dir
from domain_models import Cancelled
from http_clients import GraniteUploader
from media_probe import audio_duration_seconds
from providers import GEMINI_LIVE_MODEL, GEMINI_STT_MODEL, GEMINI_STT_URL, GEMINI_WEBSOCKET_URL
from stt_provider_rules import invalid_codes, keywords_for_provider, language_custom, language_mode, parse_codes

GOOGLE_ORIGIN = "https://generativelanguage.googleapis.com"
BYTES_PER_SECOND = 32000  # PCM16 little endian, mono, 16 kHz.
SESSION_SECONDS = 540  # Renova antes do limite de aproximadamente 10 minutos.
FINAL_TIMEOUT = 20
END_SILENCE_SECONDS = 2
FINAL_DRAIN_SECONDS = 1


def gemini_error_message(error, api_key: str = "") -> str:
    text = str(error)
    if api_key:
        text = text.replace(api_key, "[chave ocultada]")
    text = re.sub(r"AIza[\w-]{20,}", "[chave ocultada]", text)
    text = re.sub(r"(?i)([?&]key=)[^\s&\"']+", r"\1[chave ocultada]", text)
    return text[:1500] or "Falha na transcrição Gemini."


def gemini_api_key(settings: dict) -> str:
    key = str(settings.get("g_ai_studio_api_key") or "").strip()
    if not key:
        raise ValueError("Insira a chave G AI Studio nas configurações para usar Gemini Transcribe.")
    return key


def gemini_language_codes(settings: dict) -> list[str]:
    mode = language_mode(settings, "gemini")
    codes = parse_codes(language_custom(settings, "gemini")) if mode == "custom" else (
        [] if mode == "multi" else [mode]
    )
    invalid = invalid_codes("gemini", codes)
    if invalid:
        raise ValueError("Gemini não suporta estes códigos de idioma: " + ", ".join(invalid))
    return codes


def gemini_transcription_config(settings: dict, *, live: bool = False) -> dict:
    codes = gemini_language_codes(settings)
    terms = keywords_for_provider(settings, "gemini")
    if len(terms) > 1000:
        raise ValueError("Gemini aceita no máximo 1.000 termos de vocabulário.")
    if live:
        config = {"languageCodes": codes, "mode": "VERBATIM"}
        if terms:
            config["customVocabulary"] = terms
        return config
    diarize = bool(settings.get("diarize") or settings.get("grok_diarize"))
    timestamps = bool(settings.get("gemini_timestamps"))
    if terms and (diarize or timestamps):
        raise ValueError("Gemini REST não combina Keywords com diarização ou timestamps. Desative um deles.")
    mode = {"type": "verbatim"}
    if diarize:
        mode["diarization_mode"] = "speaker"
    if timestamps:
        mode["timestamp_granularities"] = ["word"]
    config = {"language_codes": codes, "mode": mode}
    if terms:
        config["custom_vocabulary"] = terms
    return config


def gemini_setup_payload(settings: dict) -> dict:
    return {"setup": {
        "model": "models/" + GEMINI_LIVE_MODEL,
        "generationConfig": {"responseModalities": ["TEXT"]},
        "inputAudioTranscription": gemini_transcription_config(settings, live=True),
    }}


def gemini_rest_body(settings: dict, uri: str, mime_type: str) -> dict:
    return {
        "model": GEMINI_STT_MODEL,
        "input": [{"type": "audio", "uri": uri, "mime_type": mime_type}],
        "generation_config": {"transcription_config": gemini_transcription_config(settings)},
        "store": False,
    }


def gemini_normalize_response(payload: dict, *, diarize: bool = False) -> dict:
    """Só conteúdo de saída, nunca usage, IDs ou eco dos parâmetros de entrada."""
    texts, words = [], []
    for step in payload.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for content in step.get("content", []):
            if content.get("type") == "text" and content.get("text"):
                texts.append(content["text"])
            for annotation in content.get("annotations", []):
                if annotation.get("type") != "word_info":
                    continue
                word = {"text": str(annotation.get("text") or "")}
                for source, target in (("start_offset", "start"), ("end_offset", "end")):
                    value = annotation.get(source)
                    if value is not None:
                        try:
                            word[target] = float(str(value).removesuffix("s"))
                        except ValueError:
                            pass
                if annotation.get("speaker"):
                    word["speaker"] = annotation["speaker"]
                words.append(word)
    # Algumas versões devolvem outputs em vez de steps.
    if not texts:
        texts = [str(item["text"]) for item in payload.get("outputs", [])
                 if item.get("type") == "text" and item.get("text")]
    text = "\n".join(texts).strip()
    if not text and isinstance(payload.get("output_text"), str):
        text = payload["output_text"].strip()
    if diarize and words and all(word.get("speaker") for word in words):
        turns, previous, labels = [], None, {}
        for word in words:
            speaker = word["speaker"]
            labels.setdefault(speaker, len(labels) + 1)
            if speaker != previous:
                turns.append(f"Interlocutor {labels[speaker]}: {word['text']}")
            elif word["text"]:
                turns[-1] += ("" if word["text"] in ",.;:!?" else " ") + word["text"]
            previous = speaker
        text = "\n".join(turns)
    return {"text": text, "words": words, "status": payload.get("status", "completed")}


class GeminiTranscriptionUploader(GraniteUploader):
    """Contrato GraniteUploader; upload em blocos, cancelamento e limpeza remota."""
    def __init__(self, cancel_event: threading.Event, settings: dict):
        super().__init__(cancel_event)
        self.settings = settings.copy()
        self.api_key = gemini_api_key(settings)
        gemini_transcription_config(settings)

    def _request(self, method, url, body=b"", headers=None, *, cleanup=False):
        parsed = urlparse(url)
        # URLs de upload vêm da API. Não encaminhar a chave para outros hosts.
        if parsed.scheme != "https" or parsed.netloc != "generativelanguage.googleapis.com":
            raise RuntimeError("O Google devolveu uma URL de upload inválida.")
        if self.cancel_event.is_set() and not cleanup:
            raise Cancelled()
        conn = http.client.HTTPSConnection(parsed.netloc, timeout=10 if cleanup else 20)
        with self._lock:
            self._connections.add(conn)
        try:
            conn.connect()
            if self.cancel_event.is_set() and not cleanup:
                raise Cancelled()
            conn.sock.settimeout(10 if cleanup else 180)
            request_headers = {"x-goog-api-key": self.api_key, "Accept": "application/json"}
            request_headers.update(headers or {})
            length = body.stat().st_size if isinstance(body, Path) else len(body)
            request_headers["Content-Length"] = str(length)
            path = parsed.path + ("?" + parsed.query if parsed.query else "")
            conn.putrequest(method, path)
            for name, value in request_headers.items():
                conn.putheader(name, value)
            conn.endheaders()
            if isinstance(body, Path):
                with body.open("rb") as source:
                    while chunk := source.read(128 * 1024):
                        if self.cancel_event.is_set():
                            raise Cancelled()
                        conn.send(chunk)
            elif body:
                conn.send(body)
            response = conn.getresponse()
            chunks = []
            while chunk := response.read(128 * 1024):
                if self.cancel_event.is_set() and not cleanup:
                    raise Cancelled()
                chunks.append(chunk)
            raw = b"".join(chunks)
            raw = gemini_error_message(raw.decode("utf-8"), self.api_key).encode("utf-8") if response.status >= 400 else raw
            return response.status, raw, {key.lower(): value for key, value in response.getheaders()}
        except Exception as exc:
            if self.cancel_event.is_set() and not cleanup:
                raise Cancelled() from exc
            raise RuntimeError(gemini_error_message(exc, self.api_key)) from None
        finally:
            conn.close()
            with self._lock:
                self._connections.discard(conn)

    @staticmethod
    def _checked(result):
        status, raw, headers = result
        if not 200 <= status < 300:
            raise RuntimeError(f"Gemini HTTP {status}: {gemini_error_message(raw.decode('utf-8', errors='replace'))}")
        return json.loads(raw or b"{}"), headers

    def post_file_raw(self, url, file_path, mime_type, raw_path, form_fields=None, accept="application/json"):
        path = Path(file_path)
        settings = {**self.settings, **(form_fields or {})}
        config = gemini_transcription_config(settings)
        annotations = bool(settings.get("diarize") or settings.get("grok_diarize") or settings.get("gemini_timestamps"))
        duration = audio_duration_seconds(path, ffprobe=app_base_dir() / "ffprobe.exe", ffmpeg=app_base_dir() / "ffmpeg.exe")
        limit = 1800 if annotations else 3600
        if duration is not None and duration > limit:
            raise ValueError(f"Gemini REST aceita até {limit // 60} minutos por arquivo. Divida o áudio antes de enviar.")
        if path.stat().st_size > 2 * 1024 ** 3:
            raise ValueError("A Files API aceita arquivos de até 2 GB.")
        file_name = ""
        try:
            _, headers = self._checked(self._request("POST", GOOGLE_ORIGIN + "/upload/v1beta/files",
                json.dumps({"file": {"display_name": "SIG transcription"}}).encode(), {
                    "Content-Type": "application/json", "X-Goog-Upload-Protocol": "resumable",
                    "X-Goog-Upload-Command": "start", "X-Goog-Upload-Header-Content-Type": mime_type,
                    "X-Goog-Upload-Header-Content-Length": str(path.stat().st_size),
                }))
            upload_url = headers.get("x-goog-upload-url")
            if not upload_url:
                raise RuntimeError("Google não devolveu a URL para enviar o áudio.")
            payload, _ = self._checked(self._request("POST", upload_url, path, {
                "Content-Type": mime_type, "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            }))
            file_info = payload.get("file", {})
            file_name = file_info.get("name", "")
            if not re.fullmatch(r"files/[a-zA-Z0-9_-]+", file_name):
                raise RuntimeError("Google não devolveu um identificador de arquivo válido.")
            deadline = time.monotonic() + 180
            while file_info.get("state") == "PROCESSING":
                if time.monotonic() >= deadline:
                    raise TimeoutError("Google demorou demais para preparar o áudio enviado.")
                if self.cancel_event.wait(.5):
                    raise Cancelled()
                file_info, _ = self._checked(self._request("GET", GOOGLE_ORIGIN + "/v1beta/" + file_name))
            if file_info.get("state") == "FAILED" or not file_info.get("uri"):
                raise RuntimeError("Google não conseguiu preparar o áudio enviado.")
            body = gemini_rest_body(settings, file_info["uri"], mime_type)
            body["generation_config"]["transcription_config"] = config
            status, raw, headers = self._request("POST", GEMINI_STT_URL,
                json.dumps(body).encode(), {"Content-Type": "application/json"})
            Path(raw_path).write_bytes(raw)
            if status != 200:
                return status, raw, headers
            payload = json.loads(raw)
            if payload.get("status") not in (None, "completed"):
                raise RuntimeError("Gemini não concluiu a transcrição: " + str(payload.get("status")))
            normalized = gemini_normalize_response(payload, diarize=bool(settings.get("diarize") or settings.get("grok_diarize")))
            return status, json.dumps(normalized, ensure_ascii=False).encode(), headers
        finally:
            if file_name and re.fullmatch(r"files/[a-zA-Z0-9_-]+", file_name):
                try:
                    self._request("DELETE", GOOGLE_ORIGIN + "/v1beta/" + file_name, cleanup=True)
                except Exception:
                    pass  # A Files API também expira automaticamente o arquivo.


class GeminiStreamingClient:
    """PCM em JSON/base64, rascunhos substituíveis e confirmações por fala."""
    def __init__(self, settings: dict, abort_event: threading.Event):
        self.api_key = gemini_api_key(settings)
        self.setup = gemini_setup_payload(settings)
        self.abort_event = abort_event
        self._cancelled = threading.Event()
        self._ws = None
        self._lock = threading.Lock()

    def _close(self):
        with self._lock:
            ws, self._ws = self._ws, None
        self._close_websocket(ws)

    @staticmethod
    def _close_websocket(ws):
        if ws is not None:
            try:
                if ws.sock is not None:
                    ws.sock.shutdown(socket.SHUT_RDWR)
            except (OSError, ValueError):
                pass
            try:
                ws.close(timeout=0)
            except (OSError, ValueError):
                pass

    def cancel(self):
        self._cancelled.set()
        self._close()

    def _is_cancelled(self):
        return self.abort_event.is_set() or self._cancelled.is_set()

    def connect(self):
        import websocket
        if self._is_cancelled():
            raise Cancelled()
        ws = None
        try:
            # O header foi validado na API real; a chave não vai na URL/logs.
            ws = websocket.WebSocket(enable_multithread=True)
            with self._lock:
                self._ws = ws
            ws.connect(GEMINI_WEBSOCKET_URL, header=["x-goog-api-key: " + self.api_key], timeout=20)
            if self._is_cancelled():
                raise Cancelled()
            ws.send(json.dumps(self.setup))
            response = json.loads(ws.recv())
            if "setupComplete" not in response:
                raise RuntimeError("Gemini não confirmou a conexão: " + json.dumps(response))
            ws.settimeout(.5)
            if self._is_cancelled():
                raise Cancelled()
        except Exception as exc:
            self._close()
            self._close_websocket(ws)  # cancel pode ter retirado _ws durante connect.
            if self._is_cancelled():
                raise Cancelled() from exc
            raise RuntimeError(gemini_error_message(exc, self.api_key)) from None

    def transcribe(self, audio_queue, stop_event, receive, status=lambda _text: None):
        try:
            while not self._is_cancelled():
                if self._ws is None:
                    self.connect()
                rotated = self._session(audio_queue, stop_event, receive)
                self._close()
                if not rotated or (stop_event.is_set() and audio_queue.empty()):
                    return
                status("Renovando a conexão Gemini Transcribe...")
            raise Cancelled()
        finally:
            self._close()

    def _session(self, audio_queue, stop_event, receive):
        import websocket
        ws = self._ws
        done, rotate, end_sent = threading.Event(), threading.Event(), threading.Event()
        errors, ended_at = [], []
        started = time.monotonic()
        draft = ""
        activity_seen = False
        completion_seen = False
        speech_seen = False

        def send_audio():
            next_send = time.monotonic()

            def send_chunk(chunk, pace=1):
                nonlocal next_send
                if self.abort_event.wait(max(0, next_send - time.monotonic())):
                    raise Cancelled()
                if done.is_set() or self._is_cancelled():
                    raise Cancelled()
                ws.send(json.dumps({"realtimeInput": {"audio": {
                    "data": base64.b64encode(chunk).decode("ascii"),
                    "mimeType": "audio/pcm;rate=16000",
                }}}))
                next_send = max(next_send, time.monotonic()) + len(chunk) / BYTES_PER_SECOND / pace

            try:
                while not done.is_set() and not self._is_cancelled():
                    if rotate.is_set() or time.monotonic() - started >= SESSION_SECONDS:
                        rotate.set()
                        break
                    if stop_event.is_set() and audio_queue.empty():
                        break
                    try:
                        chunk = audio_queue.get(timeout=.1)
                    except queue.Empty:
                        continue
                    if not chunk:
                        continue
                    # Recupera o atraso acumulado durante a renovação da
                    # conexão, para a fila não crescer a cada sessão.
                    send_chunk(chunk, pace=1.25 if audio_queue.qsize() > 10 else 1)
                if not done.is_set() and not self._is_cancelled():
                    # A API real pode encerrar sem a última confirmação se
                    # audioStreamEnd chegar durante uma fala. Silêncio PCM
                    # permite ao VAD finalizar a fala antes de fechar o fluxo.
                    for _ in range(round(END_SILENCE_SECONDS * 10)):
                        send_chunk(bytes(BYTES_PER_SECOND // 10))
                    if self.abort_event.wait(max(0, next_send - time.monotonic())) or self._is_cancelled():
                        raise Cancelled()
                    ended_at.append(time.monotonic())
                    end_sent.set()
                    ws.send(json.dumps({"realtimeInput": {"audioStreamEnd": True}}))
            except Exception as exc:
                errors.append(exc)
                done.set()

        sender = threading.Thread(target=send_audio, daemon=True)
        sender.start()
        try:
            while not self._is_cancelled():
                if errors:
                    raise errors[0]
                if (end_sent.is_set() and (completion_seen or not speech_seen) and not draft and not activity_seen
                        and time.monotonic() - ended_at[0] >= FINAL_DRAIN_SECONDS):
                    return rotate.is_set()
                if end_sent.is_set() and time.monotonic() - ended_at[0] >= FINAL_TIMEOUT:
                    if draft or activity_seen:
                        raise TimeoutError("Gemini não confirmou a última fala. O texto parcial e o áudio foram preservados.")
                    return rotate.is_set()  # Silêncio sem fala detectada.
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                except websocket.WebSocketConnectionClosedException:
                    if end_sent.is_set() and completion_seen and not draft and not activity_seen:
                        return rotate.is_set()
                    raise
                if not raw:
                    if end_sent.is_set() and completion_seen and not draft and not activity_seen:
                        return rotate.is_set()
                    raise RuntimeError("A conexão Gemini terminou antes de confirmar a transcrição.")
                message = json.loads(raw)
                if "error" in message:
                    raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
                if "goAway" in message:
                    rotate.set()
                content = message.get("serverContent") or {}
                interim = content.get("interimInputTranscription")
                if isinstance(interim, dict):
                    draft = str(interim.get("text") or "")
                    activity_seen = True
                    completion_seen = False
                    speech_seen = True
                    receive([], draft)
                final = content.get("inputTranscription")
                if isinstance(final, dict):
                    text = str(final.get("text") or "").strip()
                    draft = ""
                    activity_seen = False
                    completion_seen = True
                    speech_seen = True
                    receive([text] if text else [], "")
                if content.get("generationComplete") or content.get("turnComplete"):
                    completion_seen = True
                activity = (message.get("voiceActivity") or {}).get("type")
                if activity == "ACTIVITY_START":
                    activity_seen = True
                    completion_seen = False
                    speech_seen = True
                elif activity == "ACTIVITY_END":
                    activity_seen = False
            raise Cancelled()
        except Exception as exc:
            if self._is_cancelled():
                raise Cancelled() from exc
            raise RuntimeError(gemini_error_message(exc, self.api_key)) from None
        finally:
            done.set()
            self._close()
            sender.join(timeout=2)
