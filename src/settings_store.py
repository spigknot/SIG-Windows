"""Persistencia de settings.json: carregar, normalizar (com defaults), salvar.

Chaves persistidas sao COMPATIVEIS: nomes e defaults vem de providers.DEFAULT_SETTINGS
e nunca devem ser renomeados sem migracao."""

import json
from app_env import settings_path
from providers import (
    DEEPSEEK_API_NAMES,
    DEEPSEEK_TEXT_NAME,
    DEFAULT_SETTINGS,
    ELEVENLABS_API_NAME,
    GROK_API_NAME,
    GROK_NON_REASONING_LEGACY_NAME,
    GROK_NON_REASONING_TEXT_NAME,
    GROK_TEXT_API_NAMES,
    GROK_TEXT_NAME,
    IA_PROXY_NAME,
    PARTS_EXTRACTION_LABELS,
    SERVER_GEMMA_NAME,
    TEXT_TASK_KEYS,
    fallback_transcription_server_for_missing_api_key,
    plausible_deepseek_api_key,
    plausible_xai_api_key,
    read_text_models,
    read_transcription_servers,
    selected_text_model_config,
    selected_transcription_server,
)


def load_settings() -> dict:
    data = DEFAULT_SETTINGS.copy()
    path = settings_path()
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update({key: loaded[key] for key in data.keys() & loaded.keys()})
        except Exception:
            pass
    return normalize_settings(data)


def normalize_settings(data: dict) -> dict:
    clean = DEFAULT_SETTINGS.copy()
    clean["convert_parallel"] = max(1, clamp_int(data.get("convert_parallel"), 1, 256, DEFAULT_SETTINGS["convert_parallel"]))
    clean["transcribe_parallel"] = max(1, clamp_int(data.get("transcribe_parallel"), 1, 256, DEFAULT_SETTINGS["transcribe_parallel"]))
    clean["grok_chunk_ms"] = clamp_int(data.get("grok_chunk_ms"), 20, 2000, DEFAULT_SETTINGS["grok_chunk_ms"])
    for language_key, fallback in {
        "deepgram_language_mode": "pt-BR",
        "assemblyai_language_mode": "pt",
        "elevenlabs_language_mode": "pt",
        "metamuse_language_mode": "pt",
        "alibaba_language_mode": "pt",
        "grok_language_mode": "pt",
    }.items():
        value = str(data.get(language_key) or "").strip()
        clean[language_key] = value or fallback
    for custom_key in (
        "deepgram_language_custom",
        "assemblyai_language_custom",
        "elevenlabs_language_custom",
        "metamuse_language_custom",
        "alibaba_language_custom",
        "grok_language_custom",
    ):
        clean[custom_key] = str(data.get(custom_key) or "").strip()
    rest_value = data.get("grok_rest_requests", DEFAULT_SETTINGS["grok_rest_requests"])
    clean["grok_rest_requests"] = (
        rest_value
        if isinstance(rest_value, bool)
        else str(rest_value).strip().casefold() in {"1", "true", "yes", "on"}
    )
    grok_api_key = str(data.get("grok_api_key") or "").strip()
    deepgram_api_key = str(data.get("deepgram_api_key") or "").strip()
    assemblyai_api_key = str(data.get("assemblyai_api_key") or "").strip()
    elevenlabs_api_key = str(data.get("elevenlabs_api_key") or "").strip()
    metamuse_api_key = str(data.get("metamuse_api_key") or "").strip()
    alibaba_api_key = str(data.get("alibaba_api_key") or "").strip()
    deepseek_api_key = str(data.get("deepseek_api_key") or "").strip()
    server_names = {server["name"] for server in read_transcription_servers()}
    transcription_server = str(
        data.get("transcription_server") or DEFAULT_SETTINGS["transcription_server"]
    )
    transcription_server = {
        "Taguai-speech": "servidor",
        "Grok (API)": GROK_API_NAME,
    }.get(transcription_server, transcription_server)
    transcription_server = fallback_transcription_server_for_missing_api_key(
        transcription_server,
        grok_api_key,
        deepgram_api_key,
        assemblyai_api_key,
        elevenlabs_api_key,
        metamuse_api_key,
        alibaba_api_key,
    )
    clean["transcription_server"] = (
        transcription_server
        if transcription_server in server_names
        else selected_transcription_server({})["name"]
    )
    multi_models = data.get("multi_transcription_models")
    if not isinstance(multi_models, (list, tuple)):
        multi_models = []
    normalized_multi_models = []
    for name in multi_models:
        candidate = fallback_transcription_server_for_missing_api_key(
            str(name).strip(),
            grok_api_key,
            deepgram_api_key,
            assemblyai_api_key,
            elevenlabs_api_key,
            metamuse_api_key,
            alibaba_api_key,
        )
        if candidate in server_names and candidate != ELEVENLABS_API_NAME:
            normalized_multi_models.append(candidate)
    clean["multi_transcription_models"] = list(dict.fromkeys(normalized_multi_models))[:3]
    text_model_names = {model["name"] for model in read_text_models()}

    def proxy_model(value, provider):
        candidate = str(value or "").strip()
        if candidate in {GROK_TEXT_NAME, GROK_NON_REASONING_TEXT_NAME, DEEPSEEK_TEXT_NAME}:
            return candidate
        return DEEPSEEK_TEXT_NAME if str(provider or "").casefold() == "deepseek" else GROK_TEXT_NAME

    def normalize_reasoning(value, model_name, *, via_proxy: bool = False):
        candidate = str(value or "").casefold()
        if not model_name:
            return ""
        if model_name == GROK_NON_REASONING_TEXT_NAME:
            return ""
        if via_proxy:
            return "none" if model_name == DEEPSEEK_TEXT_NAME else "low"
        if model_name == DEEPSEEK_TEXT_NAME:
            return candidate if candidate in {"none", "low", "high", "max"} else "none"
        return candidate if candidate in {"low", "medium", "high", "xhigh"} else "low"

    text_model = str(data.get("text_model") or DEFAULT_SETTINGS["text_model"])
    legacy_text_model = text_model.casefold()
    if legacy_text_model in {"taguai-grok", "grok (api)"}:
        text_model = IA_PROXY_NAME if "api" not in legacy_text_model else GROK_TEXT_NAME
    elif legacy_text_model in {GROK_NON_REASONING_LEGACY_NAME, GROK_NON_REASONING_TEXT_NAME}:
        text_model = GROK_NON_REASONING_TEXT_NAME
    elif legacy_text_model.startswith("grok-4."):
        text_model = GROK_TEXT_NAME
    elif legacy_text_model.startswith("deepseek-v4-") or legacy_text_model.startswith("deepseek v4"):
        text_model = DEEPSEEK_TEXT_NAME
    clean["text_model"] = text_model if text_model in text_model_names else selected_text_model_config({})["name"]

    proxy_model_1 = proxy_model(
        data.get("ia_proxy_model"), data.get("ia_proxy_provider") or DEFAULT_SETTINGS["ia_proxy_provider"]
    )
    clean["ia_proxy_model"] = proxy_model_1
    clean["ia_proxy_provider"] = "deepseek" if proxy_model_1 == DEEPSEEK_TEXT_NAME else "grok"
    actual_model = proxy_model_1 if clean["text_model"] == IA_PROXY_NAME else clean["text_model"]
    clean["text_reasoning"] = normalize_reasoning(
        data.get("text_reasoning"),
        actual_model,
        via_proxy=clean["text_model"] == IA_PROXY_NAME,
    )
    extraction = str(data.get("parts_extraction") or DEFAULT_SETTINGS["parts_extraction"])
    clean["parts_extraction"] = (
        extraction if extraction in PARTS_EXTRACTION_LABELS else DEFAULT_SETTINGS["parts_extraction"]
    )
    parts_model = str(data.get("parts_model") or DEFAULT_SETTINGS["parts_model"])
    clean["parts_model"] = (
        parts_model
        if parts_model in {
            IA_PROXY_NAME,
            SERVER_GEMMA_NAME,
            GROK_NON_REASONING_TEXT_NAME,
            GROK_TEXT_NAME,
            DEEPSEEK_TEXT_NAME,
        }
        else DEFAULT_SETTINGS["parts_model"]
    )
    parts_proxy_provider = str(
        data.get("parts_proxy_provider") or DEFAULT_SETTINGS["parts_proxy_provider"]
    ).casefold()
    clean["parts_proxy_model"] = proxy_model(
        data.get("parts_proxy_model"), parts_proxy_provider
    )
    clean["parts_proxy_provider"] = (
        "deepseek"
        if clean["parts_proxy_model"] == DEEPSEEK_TEXT_NAME
        else "grok"
    )
    clean["grok_api_key"] = grok_api_key
    clean["deepgram_api_key"] = deepgram_api_key
    clean["deepgram_keyterms"] = ", ".join(
        term.strip()
        for term in str(data.get("deepgram_keyterms") or "").replace("\n", ",").split(",")
        if term.strip()
    )
    clean["assemblyai_api_key"] = assemblyai_api_key
    clean["elevenlabs_api_key"] = elevenlabs_api_key
    clean["metamuse_api_key"] = metamuse_api_key
    clean["alibaba_api_key"] = alibaba_api_key
    clean["deepseek_api_key"] = deepseek_api_key
    clean["imei_api_key"] = str(data.get("imei_api_key") or "").strip()
    clean["police_name"] = str(data.get("police_name") or "").strip()
    clean["police_role"] = str(data.get("police_role") or "").strip()
    clean["police_station"] = str(data.get("police_station") or "").strip()
    clean["police_delegate"] = str(data.get("police_delegate") or "").strip()
    clean["police_city"] = str(data.get("police_city") or "").strip()
    if clean["text_model"] in GROK_TEXT_API_NAMES and not plausible_xai_api_key(clean["grok_api_key"]):
        clean["text_model"] = SERVER_GEMMA_NAME
    if clean["text_model"] in DEEPSEEK_API_NAMES and not plausible_deepseek_api_key(clean["deepseek_api_key"]):
        clean["text_model"] = SERVER_GEMMA_NAME
    if clean["parts_model"] in GROK_TEXT_API_NAMES and not plausible_xai_api_key(clean["grok_api_key"]):
        clean["parts_model"] = SERVER_GEMMA_NAME
    if clean["parts_model"] == DEEPSEEK_TEXT_NAME and not plausible_deepseek_api_key(clean["deepseek_api_key"]):
        clean["parts_model"] = SERVER_GEMMA_NAME
    # Modelos por tarefa (histórico, oitiva e qualificação) e raciocínio das
    # partes: preservados com fallback para as chaves gerais de texto.
    task_preserved: dict[str, object] = {}
    for task, keys in TEXT_TASK_KEYS.items():
        model_key, reasoning_key, proxy_key = keys
        raw_model = str(data.get(model_key) or "")
        model_value = raw_model if raw_model in text_model_names else clean["text_model"]
        if model_value in GROK_TEXT_API_NAMES and not plausible_xai_api_key(grok_api_key):
            model_value = SERVER_GEMMA_NAME
        elif model_value in DEEPSEEK_API_NAMES and not plausible_deepseek_api_key(deepseek_api_key):
            model_value = SERVER_GEMMA_NAME
        task_preserved[model_key] = model_value
        task_preserved[proxy_key] = proxy_model(data.get(proxy_key), "grok")
        effective_model = task_preserved[proxy_key] if model_value == IA_PROXY_NAME else model_value
        task_preserved[reasoning_key] = normalize_reasoning(
            data.get(reasoning_key),
            effective_model,
            via_proxy=model_value == IA_PROXY_NAME,
        )
    clean.update(task_preserved)
    clean["parts_reasoning"] = normalize_reasoning(
        data.get("parts_reasoning"),
        clean["parts_proxy_model"] if clean["parts_model"] == IA_PROXY_NAME else clean["parts_model"],
        via_proxy=clean["parts_model"] == IA_PROXY_NAME,
    )
    # VAD removido
    return clean


def save_settings(data: dict) -> dict:
    clean = normalize_settings(data)
    settings_path().write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean


def clamp_int(value, minimum: int, maximum: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, number))
