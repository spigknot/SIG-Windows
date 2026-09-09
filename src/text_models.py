"""Selecao do modelo de texto (IA) e extracao do texto das respostas.

NAO confundir com domain_models.py (AudioJob) nem com transcricao STT.
Depende de providers.py para o catalogo; sem rede, sem Tkinter."""

import json
from providers import (
    DEEPSEEK_TEXT_NAME,
    GROK_NON_REASONING_LEGACY_NAME,
    GROK_NON_REASONING_TEXT_NAME,
    GROK_TEXT_NAME,
    IA_PROXY_NAME,
    SERVER_GEMMA_MODEL,
    SERVER_GEMMA_NAMES,
    TEXT_TASK_KEYS,
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
    if request_model not in {GROK_TEXT_NAME, GROK_NON_REASONING_TEXT_NAME, DEEPSEEK_TEXT_NAME} | SERVER_GEMMA_NAMES:
        request_model = GROK_TEXT_NAME
    provider = "deepseek" if request_model == DEEPSEEK_TEXT_NAME else "xai"
    if request_model in SERVER_GEMMA_NAMES:
        request_model = SERVER_GEMMA_MODEL
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
        parameters = {
            "model": SERVER_GEMMA_MODEL,
            "chat_template_kwargs": {"enable_thinking": False},
            "temperature": 0.0,
            "seed": 1,
            "top_k": 1,
            "top_p": 1,
        }
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

    if provider == "servidor" or request_model in SERVER_GEMMA_NAMES | {SERVER_GEMMA_MODEL}:
        destination = "servidor"
    else:
        destination = {
            GROK_TEXT_NAME: "Grok-4.6",
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
