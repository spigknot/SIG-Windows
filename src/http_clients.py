"""Clientes HTTP do aplicativo (uploads e modelos de texto).

GraniteUploader = upload multipart/streaming para STT + WebSocket de resultados.
TextModelClient = chamadas REST aos modelos de texto (IA) com streaming SSE.
Toda a rede fica AQUI: timeout, retry, headers e parsing de stream."""

import http.client
import json
import socket
import threading
import urllib.request
import uuid
from domain_models import Cancelled
from pathlib import Path
from providers import GROK_NON_REASONING_TEXT_NAME, GROK_TEXT_NAME, SERVER_GEMMA_MODEL
from text_models import extract_text_model_output
from transcription_parsing import (
    ParsedTranscription,
    extract_text_from_response,
    parse_transcription_response,
)
from urllib.parse import urlparse


class GraniteUploader:
    def __init__(
        self,
        cancel_event: threading.Event,
        form_fields: dict | None = None,
        extra_headers: dict[str, str] | None = None,
        file_field: str = "files",
        raw_body: bool = False,
    ):
        self.cancel_event = cancel_event
        self.form_fields = dict(form_fields or {})
        self.extra_headers = dict(extra_headers or {})
        self.file_field = file_field
        self.raw_body = bool(raw_body)
        self._lock = threading.Lock()
        self._connections: set[http.client.HTTPConnection] = set()

    def cancel(self):
        with self._lock:
            connections = list(self._connections)
        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass

    def post_file(
        self,
        url: str,
        file_path: Path,
        mime_type: str,
        raw_path: Path,
        form_fields: dict | None = None,
    ) -> tuple[int, str]:
        status, raw, _headers = self.post_file_raw(url, file_path, mime_type, raw_path, form_fields)
        return status, extract_text_from_response(raw)

    def post_file_parsed(
        self,
        url: str,
        file_path: Path,
        mime_type: str,
        raw_path: Path,
        form_fields: dict | None = None,
    ) -> tuple[int, ParsedTranscription]:
        status, raw, _headers = self.post_file_raw(url, file_path, mime_type, raw_path, form_fields)
        return status, parse_transcription_response(raw)

    def post_file_raw(
        self,
        url: str,
        file_path: Path,
        mime_type: str,
        raw_path: Path,
        form_fields: dict | None = None,
        accept: str = "application/json",
    ) -> tuple[int, bytes, dict[str, str]]:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise RuntimeError("Servidor precisa começar com http:// ou https://")
        boundary = f"----sig-{uuid.uuid4().hex}"
        filename = file_path.name
        parts = []
        merged_fields = self.form_fields.copy()
        merged_fields.update(form_fields or {})
        if self.raw_body:
            # Deepgram (e APIs de áudio cru): o arquivo vai como body direto,
            # sem multipart; os parâmetros viajam na query da URL.
            preamble = b""
            ending = b""
            content_type = mime_type
            content_length = file_path.stat().st_size
        else:
            for key, value in merged_fields.items():
                if key.lower() in ("file", "files") or value is None:
                    continue
                # Valor em LISTA = campo REPETIDO no multipart (ex.: `keyterm`
                # do xAI). Sem isto o parâmetro sairia como JSON, que nenhum
                # provedor aceita para termos repetidos.
                values = value if isinstance(value, (list, tuple)) else (value,)
                for item in values:
                    if item is None:
                        continue
                    clean_value = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                    parts.append(
                        (
                            f"--{boundary}\r\n"
                            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                            f"{clean_value}\r\n"
                        ).encode("utf-8")
                    )
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{self.file_field}"; filename="{filename}"\r\n'
                    f"Content-Type: {mime_type}\r\n\r\n"
                ).encode("utf-8")
            )
            preamble = b"".join(parts)
            ending = f"\r\n--{boundary}--\r\n".encode("utf-8")
            content_type = f"multipart/form-data; boundary={boundary}"
            content_length = len(preamble) + file_path.stat().st_size + len(ending)
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        conn = connection_cls(parsed.netloc, timeout=60 * 60)
        with self._lock:
            self._connections.add(conn)
        try:
            if self.cancel_event.is_set():
                raise Cancelled()
            conn.putrequest("POST", path)
            conn.putheader("accept", accept)
            conn.putheader("Content-Type", content_type)
            conn.putheader("Content-Length", str(content_length))
            for header, value in self.extra_headers.items():
                conn.putheader(header, value)
            conn.endheaders()
            conn.send(preamble)
            with file_path.open("rb") as handle:
                while True:
                    if self.cancel_event.is_set():
                        raise Cancelled()
                    chunk = handle.read(1024 * 128)
                    if not chunk:
                        break
                    conn.send(chunk)
            conn.send(ending)
            if self.cancel_event.is_set():
                raise Cancelled()
            response = conn.getresponse()
            chunks = []
            while True:
                if self.cancel_event.is_set():
                    raise Cancelled()
                chunk = response.read(1024 * 128)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
            raw_path.write_bytes(raw)
            return response.status, raw, dict(response.getheaders())
        except (OSError, socket.timeout) as exc:
            if self.cancel_event.is_set():
                raise Cancelled() from exc
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._connections.discard(conn)


class TextModelClient:

    def _count_input_tokens(self, url: str, fallback_url: str, model: str, system_prompt: str, material: str) -> int:
        """max_tokens = tokens do input com a margem do template do chat.

        O servidor é um llama.cpp (vLLM-like): o endpoint /tokenize conta o
        texto CRU via {"content": <texto>} e a resposta traz {"tokens": [...]}.
        O template do chat do modelo (turnos system/user) adiciona ~50% em
        textos curtos, então aplicamos a margem 1.5 — no teste real isso bateu
        exatamente com o usage.prompt_tokens da resposta. Sem o /tokenize,
        estimativa local de 4 caracteres por token (também com a margem).
        """
        text = f"{system_prompt}\n{material}"
        bases = []
        for candidate in (url, fallback_url):
            if not candidate:
                continue
            if "/v1/chat/completions" in candidate:
                candidate = candidate.rsplit("/v1/chat/completions", 1)[0]
            bases.append(candidate.rstrip("/") + "/tokenize")
        for tokenize_url in bases:
            try:
                request = urllib.request.Request(
                    tokenize_url,
                    data=json.dumps({"content": text}, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    root = json.loads(response.read().decode("utf-8", errors="replace"))
                count = root.get("count") if isinstance(root, dict) else None
                if not isinstance(count, int) or count <= 0:
                    tokens = root.get("tokens") if isinstance(root, dict) else None
                    count = len(tokens) if isinstance(tokens, list) else 0
                if isinstance(count, int) and count > 0:
                    return max(1, round(count * 1.5))
            except Exception:
                continue
        return max(1, round((len(text) / 4) * 1.5))

    def __init__(self, cancel_event: threading.Event):
        self.cancel_event = cancel_event
        self._lock = threading.Lock()
        self._connections: set[http.client.HTTPConnection] = set()

    def cancel(self):
        with self._lock:
            connections = list(self._connections)
        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass

    def post(self, model_config: dict, system_prompt: str, material: str) -> str:
        system_prompt = str(system_prompt or "").strip()
        material = str(material or "").strip()
        if not system_prompt:
            raise RuntimeError("Prompt de sistema vazio.")
        if not material:
            raise RuntimeError("Prompt de usuário vazio.")
        url = model_config["url"]
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise RuntimeError("O endereço do modelo precisa começar com http:// ou https://")
        payload = json.loads(json.dumps(model_config["parameters"], ensure_ascii=False))
        is_grok_api = bool(model_config.get("is_grok_api"))
        is_deepseek_api = bool(model_config.get("is_deepseek_api"))
        is_xai_proxy = bool(model_config.get("is_xai_proxy"))
        provider = str(model_config.get("provider") or "").casefold()
        is_non_reasoning_grok = (
            model_config.get("request_model") or payload.get("model")
        ) == GROK_NON_REASONING_TEXT_NAME
        is_xai_request = is_grok_api or (is_xai_proxy and provider == "xai")
        is_deepseek_request = is_deepseek_api or (is_xai_proxy and provider == "deepseek")
        if is_grok_api or is_deepseek_api:
            api_key = str(model_config.get("api_key") or "").strip()
            if not api_key:
                provider = "DeepSeek" if is_deepseek_api else "xAI"
                raise RuntimeError(f"Insira a chave API da {provider} nas configurações.")
        if is_xai_request:
            payload.setdefault("model", GROK_TEXT_NAME)
            payload.setdefault("temperature", 0.0)
            payload.setdefault("max_output_tokens", 10000)
            if is_non_reasoning_grok:
                payload["model"] = GROK_NON_REASONING_TEXT_NAME
                payload.pop("reasoning", None)
            else:
                payload.setdefault("reasoning", {"effort": "low"})
                if str((payload.get("reasoning") or {}).get("effort") or "").casefold() == "none":
                    payload["reasoning"] = {**payload["reasoning"], "effort": "low"}
            payload.pop("max_tokens", None)
        if is_xai_proxy:
            if is_deepseek_request:
                payload["reasoning_effort"] = "none"
                payload.pop("reasoning", None)
            elif is_xai_request:
                if is_non_reasoning_grok:
                    payload.pop("reasoning", None)
                else:
                    payload["reasoning"] = {"effort": "low"}
                payload.pop("reasoning_effort", None)
        # O backend IA-Proxy expõe um contrato Chat Completions comum para
        # ambos os modelos. As APIs diretas permanecem em seus formatos
        # nativos: DeepSeek usa messages e xAI usa input.
        if is_deepseek_request or is_xai_proxy:
            payload["messages"] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": material},
            ]
            payload.pop("input", None)
        elif provider == "servidor":
            payload["messages"] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": material},
            ]
            payload.pop("input", None)
            payload["max_tokens"] = self._count_input_tokens(
                str(model_config.get("url") or ""),
                str(model_config.get("fallback_url") or ""),
                str(payload.get("model") or SERVER_GEMMA_MODEL),
                system_prompt,
                material,
            )
        elif "/api/generate" in parsed.path.lower():
            payload["system"] = system_prompt
            payload["prompt"] = material
            payload.setdefault("stream", False)
        else:
            payload["input"] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": material},
            ]
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        urls = [url]
        fallback_url = str(model_config.get("fallback_url") or "").strip()
        if fallback_url and fallback_url != url:
            urls.append(fallback_url)
        last_error = None
        for attempt_url in urls:
            attempt_parsed = urlparse(attempt_url)
            if attempt_parsed.scheme not in ("http", "https"):
                last_error = RuntimeError("O endereço do modelo precisa começar com http:// ou https://")
                continue
            path = attempt_parsed.path or "/"
            if attempt_parsed.query:
                path += f"?{attempt_parsed.query}"
            connection_cls = http.client.HTTPSConnection if attempt_parsed.scheme == "https" else http.client.HTTPConnection
            conn = connection_cls(attempt_parsed.netloc, timeout=60 * 60)
            with self._lock:
                self._connections.add(conn)
            try:
                if self.cancel_event.is_set():
                    raise Cancelled()
                headers = {
                    "accept": "application/json",
                    "Content-Type": "application/json; charset=utf-8",
                    "Content-Length": str(len(body)),
                }
                if is_grok_api or is_deepseek_api:
                    headers["Authorization"] = f"Bearer {api_key}"
                conn.request("POST", path, body=body, headers=headers)
                response = conn.getresponse()
                chunks = []
                while True:
                    if self.cancel_event.is_set():
                        raise Cancelled()
                    chunk = response.read(1024 * 128)
                    if not chunk:
                        break
                    chunks.append(chunk)
                raw = b"".join(chunks)
                if response.status < 200 or response.status >= 300:
                    detail = raw.decode("utf-8", errors="replace")
                    raise RuntimeError(f"Servidor respondeu HTTP {response.status}: {detail[:400]}")
                output = extract_text_model_output(raw).strip()
                if not output:
                    raise RuntimeError("O servidor devolveu um texto vazio.")
                return output
            except Cancelled:
                raise
            except (OSError, socket.timeout, RuntimeError) as exc:
                if self.cancel_event.is_set():
                    raise Cancelled() from exc
                last_error = exc
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
                with self._lock:
                    self._connections.discard(conn)
        raise last_error or RuntimeError("Não foi possível consultar o modelo de texto.")
