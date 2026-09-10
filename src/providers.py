"""Catalogo de provedores STT/texto, defaults de configuracao e leitura da selecao atual.

Para adicionar um provedor STT: (1) constantes aqui, (2) DEFAULT_SETTINGS aqui,
(3) campos de formulario em stt_clients.py, (4) rotulo na UI em sig_app.py.
Sem Tkinter; sem I/O proprio (recebe dicts de settings de quem chamou)."""


# API keys are supplied by the user in Settings and are never shipped in source.
IMEI_API_KEY = ""


DEFAULT_SETTINGS = {
    "convert_parallel": 8,
    "transcribe_parallel": 16,
    "grok_chunk_ms": 100,
    "grok_rest_requests": False,
    "transcription_server": "servidor",
    "multi_transcription_models": ["servidor"],
    "transcription_language": "pt",
    # Keywords (termos de reforço) do STT: lista única, montada por PROVIDER na
    # hora da requisição (mesma regra do idioma). Ver stt_provider_rules.
    "stt_keywords": [],
    # Checkbox "Keywords" das telas de Transcrição e Ocorrência (liga/desliga o
    # envio dos termos sem apagar a lista).
    "stt_keywords_enabled": True,
    "text_model": "IA-Proxy",
    "text_reasoning": "low",
    "ia_proxy_model": "grok-4.6",
    "ia_proxy_provider": "grok",
    "history_model": "IA-Proxy",
    "history_reasoning": "low",
    "history_proxy_model": "grok-4.6",
    "statement_model": "IA-Proxy",
    "statement_reasoning": "low",
    "statement_proxy_model": "grok-4.6",
    "parts_extraction": "uppercase",
    "parts_model": "IA-Proxy",
    "parts_proxy_model": "grok-4.6",
    "parts_proxy_provider": "grok",
    "parts_reasoning": "low",
    "qualification_model": "IA-Proxy",
    "qualification_reasoning": "low",
    "qualification_proxy_model": "grok-4.6",
    "grok_api_key": "",
    "deepseek_api_key": "",
    "deepgram_api_key": "",
    "assemblyai_api_key": "",
    "elevenlabs_api_key": "",
    "metamuse_api_key": "",
    "alibaba_api_key": "",
    "deepgram_language_mode": "pt-BR",
    "deepgram_language_custom": "",
    "assemblyai_language_mode": "pt",
    "assemblyai_language_custom": "",
    "elevenlabs_language_mode": "pt",
    "elevenlabs_language_custom": "",
    "metamuse_language_mode": "pt",
    "metamuse_language_custom": "",
    "alibaba_language_mode": "pt",
    "alibaba_language_custom": "",
    "grok_language_mode": "pt",
    "grok_language_custom": "",
    "imei_api_key": IMEI_API_KEY,
    "police_name": "",
    "police_role": "",
    "police_station": "",
    "police_delegate": "",
    "police_city": "",
}


# Identificadores aceitos na PRIMEIRA palavra de cada linha do arquivo de
# importação de chaves (as linhas podem vir em qualquer ordem). O restante da
# linha é a chave. Regra do usuário (10/09): a primeira palavra é sempre o
# identificador, então nomes com espaço das versões antigas ("Meta Muse Voice",
# "Imei Check") deixam de existir como identificador.
API_KEY_IMPORT_FIELDS = {
    "deepseek": "deepseek_api_key",
    "xai": "grok_api_key",
    "meta": "metamuse_api_key",
    "metamuse": "metamuse_api_key",
    "elevenlabs": "elevenlabs_api_key",
    "deepgram": "deepgram_api_key",
    "assemblyai": "assemblyai_api_key",
    "alibaba": "alibaba_api_key",
    "imeicheck": "imei_api_key",
}

# Palavras que denunciam sobra do NOME do serviço depois do identificador
# (linha no formato antigo, com o nome em várias palavras). Sem esta guarda,
# "Meta Muse Voice <chave>" seria lido como identificador "Meta" + chave
# "Muse Voice <chave>" e gravaria uma chave errada em silêncio.
API_KEY_IMPORT_LEFTOVER_WORDS = frozenset(
    {"muse", "voice", "check", "fun", "asr", "qwen", "cloud", "api", "key", "chaves"}
)


GROK_API_NAME = "Grok STT"


GROK_STT_URL = "https://api.x.ai/v1/stt"


GROK_STT_WEBSOCKET_URL = "wss://api.x.ai/v1/stt"


DEEPGRAM_API_NAME = "Deepgram Nova 3"


DEEPGRAM_STT_URL = "https://api.deepgram.com/v1/listen"


DEEPGRAM_STT_WEBSOCKET_URL = "wss://api.deepgram.com/v1/listen"


ASSEMBLYAI_API_NAME = "AssemblyAI Universal-3.5 Pro"


ASSEMBLYAI_SYNC_URL = "https://sync.assemblyai.com/transcribe"


ASSEMBLYAI_WEBSOCKET_URL = "wss://streaming.assemblyai.com/v3/ws"


ELEVENLABS_API_NAME = "ElevenLabs Scribe v2 Realtime"


ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"


ELEVENLABS_WEBSOCKET_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"


META_MUSE_API_NAME = "Meta Muse Voice"


META_MUSE_STT_URL = "https://api.meta.ai/v1/asr/transcribe"


META_MUSE_STT_WEBSOCKET_URL = "wss://api.meta.ai/v1/asr/realtime"


META_MUSE_MODEL = "muse-voice-transcribe-1.0"


ALIBABA_API_NAME = "Alibaba Fun ASR/Qwen"


ALIBABA_REST_URL = "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


ALIBABA_WEBSOCKET_URL = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"


ALIBABA_REST_MODEL = "fun-asr-flash-2026-06-15"


ALIBABA_WS_MODEL = "qwen-audio-3.0-asr-flash-streaming"


GROK_TEXT_URL = "https://api.x.ai/v1/responses"


DEEPSEEK_TEXT_URL = "https://api.deepseek.com/chat/completions"


GROK_TEXT_NAME = "grok-4.6"


GROK_NON_REASONING_TEXT_NAME = "grok-4.20-0309-non-reasoning"


GROK_NON_REASONING_LEGACY_NAME = "grok-4.20-non-reasoning"


# Nome do modelo DeepSeek usado nas requisições. O provedor recomenda o nome
# "deepseek-flash" (10/09): os nomes legados "deepseek-v4-flash" e
# "deepseek-v4-flash-vision-exp" ainda são ACEITOS, mas os modelos foram
# aposentados — as requisições são servidas pelo DeepSeek-V4.1-Flash e cobradas
# no preço do Flash. Usar o nome atual evita trocar o app a cada modelo novo.
DEEPSEEK_TEXT_NAME = "deepseek-flash"


DEEPSEEK_LEGACY_NAMES = {
    "deepseek-v4-flash",
    "deepseek-v4-flash-vision-exp",
    "deepseek v4 flash",
    "deepseek v4-flash",
}


def migrate_text_model_name(value: str) -> str:
    """Nome de modelo de texto com os legados do DeepSeek já convertidos.

    Necessário antes de comparar com o catálogo (`read_text_models`): sem isto,
    um `history_model` antigo = "deepseek-v4-flash" deixaria de casar com o
    catálogo e cairia silenciosamente no `text_model` geral (IA-Proxy) —
    trocando o provedor que o usuário tinha escolhido.
    """
    candidate = str(value or "").strip()
    folded = candidate.casefold()
    if folded in DEEPSEEK_LEGACY_NAMES or folded.startswith("deepseek-v4-") or folded.startswith("deepseek v4"):
        return DEEPSEEK_TEXT_NAME
    return candidate


IA_PROXY_NAME = "IA-Proxy"


IA_PROXY_PRIMARY_URL = "http://servidor:8500"


SERVER_GEMMA_NAME = "servidor (gemma-4-26B-A4B-abliterated)"


SERVER_GEMMA_MODEL = "gemma4"


SERVER_GEMMA_URL = "http://servidor:8400/v1/chat/completions"


SERVER_GEMMA_NAMES = {SERVER_GEMMA_NAME, SERVER_GEMMA_MODEL}


GROK_TEXT_API_NAMES = {GROK_TEXT_NAME, GROK_NON_REASONING_TEXT_NAME}


DEEPSEEK_API_NAMES = {DEEPSEEK_TEXT_NAME}


PARTS_EXTRACTION_LABELS = {
    "uppercase": "Palavras em maiúsculas",
    "name_database": "Base de nomes",
    "ai": "IA",
}


def read_transcription_servers() -> list[dict]:
    servers = [
        {
            "name": "servidor",
            "url": "http://servidor:8100",
            "parameters": {"model": "granite-speech-4.1-2b-nar"},
            "selected": True,
        }
    ]
    grok_selected = any(server["name"] == GROK_API_NAME for server in servers if server["selected"])
    deepgram_selected = any(server["name"] == DEEPGRAM_API_NAME for server in servers if server["selected"])
    assemblyai_selected = any(server["name"] == ASSEMBLYAI_API_NAME for server in servers if server["selected"])
    elevenlabs_selected = any(server["name"] == ELEVENLABS_API_NAME for server in servers if server["selected"])
    metamuse_selected = any(server["name"] == META_MUSE_API_NAME for server in servers if server["selected"])
    alibaba_selected = any(server["name"] == ALIBABA_API_NAME for server in servers if server["selected"])
    api_selected = grok_selected or deepgram_selected or assemblyai_selected or elevenlabs_selected or metamuse_selected or alibaba_selected
    plain_servers = [
        {**server, "selected": server["selected"] and not api_selected}
        for server in servers
        if server["name"] not in (GROK_API_NAME, DEEPGRAM_API_NAME, ASSEMBLYAI_API_NAME, ELEVENLABS_API_NAME, META_MUSE_API_NAME, ALIBABA_API_NAME)
    ]
    return plain_servers + [
        {
            "name": GROK_API_NAME,
            "url": GROK_STT_URL,
            "parameters": {"model": "Speech to Text"},
            "selected": grok_selected,
            "is_grok_api": True,
        },
        {
            "name": DEEPGRAM_API_NAME,
            "url": DEEPGRAM_STT_URL,
            "parameters": {"model": "Nova 3"},
            "selected": deepgram_selected,
            "is_deepgram_api": True,
        },
        {
            "name": ASSEMBLYAI_API_NAME,
            "url": ASSEMBLYAI_SYNC_URL,
            "parameters": {"model": "Universal-3.5 Pro"},
            "selected": assemblyai_selected,
            "is_assemblyai_api": True,
        },
        {
            "name": ELEVENLABS_API_NAME,
            "url": ELEVENLABS_STT_URL,
            "parameters": {"model": "scribe_v2_realtime"},
            "selected": elevenlabs_selected,
            "is_elevenlabs_api": True,
        },
        {
            "name": META_MUSE_API_NAME,
            "url": META_MUSE_STT_URL,
            "parameters": {"model": META_MUSE_MODEL},
            "selected": metamuse_selected,
            "is_metamuse_api": True,
        },
        {
            "name": ALIBABA_API_NAME,
            "url": ALIBABA_REST_URL,
            "parameters": {"model": ALIBABA_REST_MODEL},
            "selected": alibaba_selected,
            "is_alibaba_api": True,
        },
    ]


def read_text_models() -> list[dict]:
    integrated_models = [
        {
            "name": IA_PROXY_NAME,
            "url": IA_PROXY_PRIMARY_URL,
            "parameters": {
                "model": GROK_TEXT_NAME,
                "temperature": 0.0,
                "max_output_tokens": 10000,
                "reasoning": {"effort": "low"},
            },
            "selected": True,
            "provider": "xai",
            "is_grok_api": False,
            "is_deepseek_api": False,
            "is_xai_proxy": True,
        },
        {
            "name": SERVER_GEMMA_NAME,
            "url": SERVER_GEMMA_URL,
            "parameters": {
                "model": SERVER_GEMMA_MODEL,
                "chat_template_kwargs": {"enable_thinking": False},
                "temperature": 0.0,
                "seed": 1,
                "top_k": 1,
                "top_p": 1,
            },
            "selected": False,
            "provider": "servidor",
            "is_grok_api": False,
            "is_deepseek_api": False,
            "is_xai_proxy": False,
        },
        {
            "name": GROK_TEXT_NAME,
            "url": GROK_TEXT_URL,
            "parameters": {
                "model": GROK_TEXT_NAME,
                "temperature": 0.0,
                "max_output_tokens": 10000,
                "reasoning": {"effort": "low"},
            },
            "selected": False,
            "provider": "xai",
            "is_grok_api": True,
            "is_deepseek_api": False,
            "is_xai_proxy": False,
        },
        {
            "name": GROK_NON_REASONING_TEXT_NAME,
            "url": GROK_TEXT_URL,
            "parameters": {
                "model": GROK_NON_REASONING_TEXT_NAME,
                "temperature": 0.0,
                "max_output_tokens": 10000,
            },
            "selected": False,
            "provider": "xai",
            "is_grok_api": True,
            "is_deepseek_api": False,
            "is_xai_proxy": False,
        },
        {
            "name": DEEPSEEK_TEXT_NAME,
            "url": DEEPSEEK_TEXT_URL,
            "parameters": {
                "model": DEEPSEEK_TEXT_NAME,
                "temperature": 0.0,
                "max_tokens": 10000,
                "reasoning_effort": "none",
            },
            "selected": False,
            "provider": "deepseek",
            "is_grok_api": False,
            "is_deepseek_api": True,
            "is_xai_proxy": False,
        },
    ]
    return integrated_models


def selected_text_model_config(settings: dict, name_key: str = "text_model") -> dict:
    models = read_text_models()
    name = settings.get(name_key) or settings.get("text_model")
    return (
        next((model for model in models if model["name"] == name), None)
        or next((model for model in models if model["selected"]), None)
        or models[0]
    )


def selected_transcription_server(settings: dict) -> dict:
    servers = read_transcription_servers()
    name = settings.get("transcription_server")
    return (
        next((server for server in servers if server["name"] == name), None)
        or next((server for server in servers if server["selected"]), None)
        or servers[0]
    )


def transcription_server_label(server: dict) -> str:
    if server["name"] == GROK_API_NAME:
        return GROK_API_NAME
    return f"{server['name']} ({server['parameters'].get('model', 'modelo não informado')})"


def parse_api_keys_text(text: str) -> dict[str, str]:
    """Extrai chaves de linhas no formato ``Identificador chave``.

    A PRIMEIRA palavra é o identificador (Deepseek, xAI, Meta, ElevenLabs,
    Deepgram, AssemblyAI, Alibaba, ImeiCheck) e o restante da linha é a chave —
    as linhas podem vir em qualquer ordem. Espaços dentro da chave são ruído de
    formatação e são removidos (a chave de um provedor nunca tem espaços).
    Linhas vazias, sem chave, de identificador desconhecido ou que ainda tragam
    o nome do serviço em várias palavras (formato antigo) são ignoradas. Quando
    o identificador aparece mais de uma vez, a última chave informada prevalece.
    """
    imported: dict[str, str] = {}
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        identifier, remainder = parts
        field_name = API_KEY_IMPORT_FIELDS.get(identifier.casefold())
        if not field_name:
            continue
        words = remainder.split()
        if not words:
            continue
        # Sobra do nome do serviço (formato antigo) não é chave.
        if words[0].casefold() in API_KEY_IMPORT_LEFTOVER_WORDS:
            continue
        api_key = "".join(words)
        if not api_key:
            continue
        imported[field_name] = api_key
    return imported


def fallback_text_model_for_missing_api_key(
    model_name: str,
    grok_api_key: str,
    deepseek_api_key: str,
) -> str:
    """Retorna o Gemma quando um modelo de texto direto perdeu sua chave."""
    candidate = str(model_name or "").strip()
    if candidate in GROK_TEXT_API_NAMES and not str(grok_api_key or "").strip():
        return SERVER_GEMMA_NAME
    if candidate in DEEPSEEK_API_NAMES and not str(deepseek_api_key or "").strip():
        return SERVER_GEMMA_NAME
    return candidate


def fallback_transcription_server_for_missing_api_key(
    server_name: str,
    grok_api_key: str,
    deepgram_api_key: str,
    assemblyai_api_key: str,
    elevenlabs_api_key: str,
    metamuse_api_key: str = "",
    alibaba_api_key: str = "",
) -> str:
    """Retorna o Granite NAR quando um servidor STT perdeu sua chave."""
    candidate = str(server_name or "").strip()
    api_keys = {
        GROK_API_NAME: grok_api_key,
        DEEPGRAM_API_NAME: deepgram_api_key,
        ASSEMBLYAI_API_NAME: assemblyai_api_key,
        ELEVENLABS_API_NAME: elevenlabs_api_key,
        META_MUSE_API_NAME: metamuse_api_key,
        ALIBABA_API_NAME: alibaba_api_key,
    }
    if candidate in api_keys and not str(api_keys[candidate] or "").strip():
        return DEFAULT_SETTINGS["transcription_server"]
    return candidate


def plausible_xai_api_key(value: str) -> bool:
    key = value.strip()
    return len(key) == 84 and key[:4].casefold() == "xai-"


def plausible_deepseek_api_key(value: str) -> bool:
    key = value.strip()
    return len(key) == 35 and key.startswith("sk-")


def plausible_elevenlabs_api_key(value: str) -> bool:
    key = (value or "").strip()
    return 20 <= len(key) <= 64 and all(
        char.isalnum() or char in "-_" for char in key
    )


def plausible_assemblyai_api_key(value: str) -> bool:
    key = (value or "").strip()
    return 32 <= len(key) <= 64 and all(
        char in "0123456789abcdefABCDEF" for char in key
    )


def settings_for_transcription_server(settings: dict, server_name: str) -> dict:
    selected = settings.copy()
    selected["transcription_server"] = server_name
    return selected


# Modelos que NÃO podem ser escolhidos na aba Transcrição (arquivos): são de
# WebSocket/ao vivo — quem os usa é a aba Ocorrência (streaming). Regra do
# usuário (10/09): o Meta Muse Voice é apenas websocket.
REALTIME_ONLY_TRANSCRIPTION_SERVERS = frozenset(
    {
        ELEVENLABS_API_NAME,
        META_MUSE_API_NAME,
    }
)


def is_realtime_only_transcription_server(server_name: str) -> bool:
    """True para modelo exclusivo de WebSocket/ao vivo (não aceito em lote)."""
    return str(server_name or "").strip() in REALTIME_ONLY_TRANSCRIPTION_SERVERS


# Nome do servidor STT -> provedor das regras de idioma/diarização
# (stt_provider_rules). O servidor local (Granite NAR) fica de fora: não tem
# parâmetro de idioma (mesma regra da aba Ocorrência e do app Android).
STT_PROVIDER_FLAGS = (
    ("grok", "is_grok_api"),
    ("deepgram", "is_deepgram_api"),
    ("assemblyai", "is_assemblyai_api"),
    ("elevenlabs", "is_elevenlabs_api"),
    ("metamuse", "is_metamuse_api"),
    ("alibaba", "is_alibaba_api"),
)


def transcription_provider_for_server(server_name: str) -> str | None:
    """Provedor de idioma de um servidor STT (None = servidor local/sem idioma)."""
    candidate = str(server_name or "").strip()
    for server in read_transcription_servers():
        if server["name"] != candidate:
            continue
        for provider, flag in STT_PROVIDER_FLAGS:
            if server.get(flag):
                return provider
        return None
    return None


def transcription_providers_for_servers(server_names) -> list[str]:
    """Provedores de idioma do lote, na ordem de entrada e sem repetição."""
    providers: list[str] = []
    for name in server_names or []:
        provider = transcription_provider_for_server(name)
        if provider and provider not in providers:
            providers.append(provider)
    return providers


TEXT_TASK_KEYS = {
    "history": ("history_model", "history_reasoning", "history_proxy_model"),
    "statement": ("statement_model", "statement_reasoning", "statement_proxy_model"),
    "qualification": ("qualification_model", "qualification_reasoning", "qualification_proxy_model"),
}
