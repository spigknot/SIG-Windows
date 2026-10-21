"""Selecao do modelo de texto (IA) e extracao do texto das respostas.

NAO confundir com domain_models.py (AudioJob) nem com transcricao STT.
Depende de providers.py para o catalogo; sem rede, sem Tkinter."""

import codecs
import json
from providers import (
    DEEPSEEK_TEXT_NAME,
    GROK_NON_REASONING_LEGACY_NAME,
    GROK_NON_REASONING_TEXT_NAME,
    GROK_TEXT_NAME,
    IA_PROXY_NAME,
    LOCAL_SERVER_NAMES,
    TEXT_TASK_KEYS,
    local_server_parameters,
    local_text_model_id,
    local_text_model_label,
    selected_text_model_config,
)


def selected_text_model(
    settings: dict,
    *,
    model_key: str = "text_model",
    reasoning_key: str = "text_reasoning",
    proxy_key: str = "ia_proxy_model",
    model_fallback: str = "text_model",
    reasoning_fallback: str = "text_reasoning",
    proxy_fallback: str = "ia_proxy_model",
) -> dict:
    config = selected_text_model_config(settings, model_key)
    is_proxy = config["name"] == IA_PROXY_NAME
    request_model = (
        str(settings.get(proxy_key) or settings.get(proxy_fallback) or GROK_TEXT_NAME)
        if is_proxy
        else config["name"]
    )
    if request_model not in {GROK_TEXT_NAME, GROK_NON_REASONING_TEXT_NAME, DEEPSEEK_TEXT_NAME} | LOCAL_SERVER_NAMES:
        request_model = GROK_TEXT_NAME
    provider = "deepseek" if request_model == DEEPSEEK_TEXT_NAME else "xai"
    if config.get("provider") == "servidor":
        request_model = local_text_model_id()
        provider = "servidor"
    reasoning = str(settings.get(reasoning_key) or settings.get(reasoning_fallback) or "").casefold()
    if is_proxy:
        reasoning = "none" if request_model == DEEPSEEK_TEXT_NAME else "low"
    if request_model == DEEPSEEK_TEXT_NAME:
        reasoning = reasoning if reasoning in {"none", "low", "high", "max"} else "none"
        parameters = {
            "model": DEEPSEEK_TEXT_NAME,
            "temperature": 0.0,
            "max_tokens": 10000,
            "reasoning_effort": reasoning,
        }
    elif request_model == GROK_NON_REASONING_TEXT_NAME:
        parameters = {
            "model": GROK_NON_REASONING_TEXT_NAME,
            "temperature": 0.0,
            "max_output_tokens": 10000,
        }
    elif provider == "servidor":
        parameters = local_server_parameters(request_model)
    else:
        reasoning = reasoning if reasoning in {"low", "medium", "high", "xhigh"} else "low"
        parameters = {
            "model": GROK_TEXT_NAME,
            "temperature": 0.0,
            "max_output_tokens": 10000,
            "reasoning": {"effort": reasoning},
        }
    is_grok_api = bool(config.get("is_grok_api", False)) and not is_proxy
    is_deepseek_api = bool(config.get("is_deepseek_api", False)) and not is_proxy
    return {
        "name": config["name"],
        "url": config["url"],
        "fallback_url": config.get("fallback_url"),
        "parameters": parameters,
        "provider": provider,
        "is_grok_api": is_grok_api,
        "is_deepseek_api": is_deepseek_api,
        "is_xai_proxy": is_proxy,
        "request_model": request_model,
        "api_key": str(
            settings.get("deepseek_api_key" if is_deepseek_api else "grok_api_key") or ""
        ).strip(),
    }


def selected_text_model_for(settings: dict, task: str, *, secondary: bool = False) -> dict:
    """Resolve o modelo de uma tarefa específica (histórico, oitiva, qualificação).

    As configurações específicas têm precedência; quando ausentes (settings
    de versões anteriores), as configurações gerais de texto são usadas.
    """
    model_key, reasoning_key, proxy_key = TEXT_TASK_KEYS[task]
    return selected_text_model(
        settings,
        model_key=model_key,
        reasoning_key=reasoning_key,
        proxy_key=proxy_key,
        model_fallback="text_model",
        reasoning_fallback="text_reasoning",
        proxy_fallback="ia_proxy_model",
    )


def assistant_request_model_label(model_config: dict) -> str:
    """Retorna o destino curto mostrado nas linhas de requisição de IA."""
    request_model = str(
        model_config.get("request_model")
        or (model_config.get("parameters") or {}).get("model")
        or model_config.get("name")
        or "modelo"
    ).strip()
    provider = str(model_config.get("provider") or "").casefold()

    if provider == "servidor" or request_model in LOCAL_SERVER_NAMES:
        destination = local_text_model_label(str(model_config.get("request_model")
            or (model_config.get("parameters") or {}).get("model") or ""))
    else:
        destination = {
            GROK_TEXT_NAME: "grok-latest",
            GROK_NON_REASONING_TEXT_NAME: "Grok-4.20",
            GROK_NON_REASONING_LEGACY_NAME: "Grok-4.20",
            DEEPSEEK_TEXT_NAME: DEEPSEEK_TEXT_NAME,
        }.get(request_model, request_model)

    if model_config.get("is_xai_proxy"):
        return f"IA-Proxy/{destination}"
    return destination


def extract_text_model_output(raw: bytes) -> str:
    body = raw.decode("utf-8-sig", errors="replace")
    try:
        root = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Resposta JSON inválida: {body[:400]}") from exc
    for key in ("response", "output_text", "text"):
        value = root.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    choices = root.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
    output = root.get("output")
    if isinstance(output, list):
        preferred = list(reversed(output))
        for item in preferred:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message" and item.get("role") != "assistant":
                continue
            content = extract_content_text(item.get("content"))
            if content:
                return content
        for item in output:
            if isinstance(item, dict):
                content = extract_content_text(item.get("content"))
                if content:
                    return content
    # Versões do IA-Proxy que acumulam SSE devolvem o corpo upstream dentro
    # de raw_content. Mantém a resposta utilizável enquanto esse servidor
    # ainda não repassa o stream diretamente ao cliente.
    raw_content = root.get("raw_content")
    if isinstance(raw_content, str) and raw_content.lstrip().startswith(("data:", "event:", ":")):
        stream = TextModelStream("text/event-stream")
        stream.feed(raw_content.encode("utf-8"))
        return stream.finish()[0]
    raise RuntimeError("A resposta não contém output/content/text.")


def extract_content_text(content) -> str:
    if not isinstance(content, list):
        return ""
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type and item_type not in ("output_text", "text"):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


class TextModelStream:
    """Decodifica SSE/NDJSON incrementalmente e aceita JSON sem streaming.

    Só publica texto da resposta: eventos de raciocínio e metadados não
    entram no editor. Um stream interrompido não vira uma resposta concluída.
    """

    def __init__(self, content_type: str = ""):
        self.mode = (
            "sse" if "text/event-stream" in content_type
            else "ndjson" if "ndjson" in content_type else ""
        )
        self.decoder = codecs.getincrementaldecoder("utf-8-sig")()
        self.buffer = ""
        self.event_data: list[str] = []
        self.parts: list[str] = []
        self.completed = False

    def feed(self, chunk: bytes) -> list[str]:
        self.buffer += self.decoder.decode(chunk)
        if not self.mode:
            prefix = self.buffer.lstrip()
            if prefix.startswith(("data:", "event:", ":")):
                self.mode = "sse"
            elif "\n" in prefix and prefix.startswith("{"):
                try:
                    first = json.loads(prefix.split("\n", 1)[0])
                except ValueError:
                    pass
                else:
                    if isinstance(first, dict) and "done" in first:
                        self.mode = "ndjson"
        deltas = []
        if self.mode:
            while "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
                delta = self._line(line.rstrip("\r"))
                if delta:
                    deltas.append(delta)
        return deltas

    def _line(self, line: str) -> str:
        if self.mode == "ndjson":
            return self._event(line) if line.strip() else ""
        if line.startswith("data:"):
            self.event_data.append(line[5:].removeprefix(" "))
        elif not line and self.event_data:
            data = "\n".join(self.event_data)
            self.event_data.clear()
            return self._event(data)
        return ""

    def _event(self, data: str) -> str:
        if data.strip() == "[DONE]":
            self.completed = True
            return ""
        try:
            event = json.loads(data)
        except ValueError as exc:
            raise RuntimeError("O servidor enviou um evento de texto inválido.") from exc
        if not isinstance(event, dict):
            raise RuntimeError("O servidor enviou um evento de texto inválido.")
        event_type = event.get("type", "")
        if event.get("error") or event_type in ("error", "response.failed", "response.incomplete"):
            error = event.get("error") or (event.get("response") or {}).get("error") or event
            detail = error.get("message", event_type) if isinstance(error, dict) else str(error)
            raise RuntimeError(f"Falha no streaming: {detail}")
        delta = ""
        if event_type == "response.output_text.delta":
            delta = event.get("delta", "")
        elif event_type == "response.completed":
            self.completed = True
            if not self.parts:
                delta = extract_text_model_output(json.dumps(event.get("response", {})).encode("utf-8"))
        elif "choices" in event:
            for choice in event["choices"]:
                if choice.get("index", 0) != 0:
                    continue
                delta = (choice.get("delta") or {}).get("content") or ""
                if choice.get("finish_reason") is not None:
                    self.completed = True
                break
        elif "done" in event:
            delta = event.get("response", "")
            self.completed = bool(event.get("done"))
        if isinstance(delta, str) and delta:
            self.parts.append(delta)
            return delta
        return ""

    def finish(self) -> tuple[str, list[str]]:
        self.buffer += self.decoder.decode(b"", final=True)
        if not self.mode:
            output = extract_text_model_output(self.buffer.encode("utf-8"))
            return output, [output]
        deltas = []
        if self.buffer:
            delta = self._line(self.buffer.rstrip("\r"))
            if delta:
                deltas.append(delta)
            self.buffer = ""
        if self.event_data:
            delta = self._line("")
            if delta:
                deltas.append(delta)
        if not self.completed:
            raise RuntimeError("A resposta foi interrompida antes de concluir o texto.")
        return "".join(self.parts).strip(), deltas
