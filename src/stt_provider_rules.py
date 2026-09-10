"""Regras de idioma e diarização por provedor STT — espelho EXATO do app Android.

Cada provedor tem parâmetros e formatos próprios; este módulo concentra a
validação e a tradução da escolha persistida nos parâmetros reais de cada
requisição (REST e WebSocket), evitando vazamento de parâmetros de um
provedor para outro. Mantém paridade com:
- Android: SttLanguageSettings.kt + SttDiarization.kt
"""
from __future__ import annotations

import json

# ---------------- Listas de códigos (idênticas ao Android) ----------------

DEEPGRAM_CODES = {
    "ar", "ar-AE", "ar-DZ", "ar-EG", "ar-IQ", "ar-IR", "ar-JO", "ar-KW", "ar-LB", "ar-MA",
    "ar-PS", "ar-QA", "ar-SA", "ar-SD", "ar-SY", "ar-TD", "ar-TN", "de", "de-CH", "en",
    "en-AU", "en-GB", "en-IN", "en-NZ", "en-US", "es", "es-419", "fr", "fr-CA", "hi", "it",
    "ja", "ko", "ko-KR", "nl", "nl-BE", "pt", "pt-BR", "pt-PT", "ru", "zh", "zh-CN",
    "zh-Hans", "zh-Hant", "zh-HK", "zh-TW",
}

ASSEMBLYAI_CODES = {
    "ar", "da", "de", "en", "es", "fi", "fr", "he", "hi", "it", "ja", "nl", "no", "pt",
    "sv", "tr", "vi", "zh",
}

ELEVENLABS_CODES_2 = {
    "af", "am", "ar", "as", "az", "be", "bg", "bn", "bs", "ca", "cs", "cy", "da", "de",
    "el", "en", "es", "et", "fa", "ff", "fi", "fr", "ga", "gl", "gu", "ha", "he", "hi",
    "hr", "hu", "hy", "id", "ig", "is", "it", "ja", "jv", "ka", "kk", "km", "kn", "ko",
    "ku", "ky", "lb", "lg", "ln", "lo", "lt", "lv", "mi", "mk", "ml", "mn", "mr", "ms",
    "mt", "my", "ne", "nl", "no", "ny", "oc", "or", "pa", "pl", "ps", "pt", "ro", "ru",
    "sd", "sk", "sl", "sn", "so", "sr", "sv", "sw", "ta", "te", "tg", "th", "tr", "uk",
    "ur", "uz", "vi", "wo", "xh", "zh", "zu",
}

ELEVENLABS_CODES_3 = {
    "afr", "amh", "ara", "asm", "ast", "aze", "bel", "ben", "bos", "bul", "cat", "ces",
    "cmn", "cym", "dan", "deu", "ell", "eng", "est", "fas", "fin", "fra", "gle", "glg",
    "guj", "hau", "heb", "hin", "hrv", "hun", "ibo", "ind", "isl", "ita", "jav", "jpn",
    "kat", "kaz", "khm", "kir", "kor", "kur", "lao", "lav", "lit", "ltz", "lug", "mar",
    "mkd", "mlt", "mon", "mri", "msa", "mya", "nep", "nld", "nor", "nso", "oci", "ori",
    "pan", "pol", "por", "pus", "ron", "rus", "snd", "sna", "som", "spa", "srp", "slk",
    "slv", "swa", "swe", "tam", "tel", "tgk", "tha", "tur", "ukr", "urd", "uzb", "vie",
    "wol", "xho", "yor", "zul",
}

GROK_CODES = {
    "af", "ar", "az", "be", "bg", "bn", "bs", "ca", "cs", "cy", "da", "de", "el", "en",
    "es", "et", "fa", "fi", "fr", "gl", "gu", "he", "hi", "hr", "hu", "hy", "id", "is",
    "it", "ja", "kn", "ko", "la", "lt", "lv", "mk", "mr", "ms", "ne", "nl", "no", "pl",
    "pt", "ro", "ru", "sk", "sl", "so", "sq", "sr", "sv", "sw", "ta", "te", "th", "tr",
    "uk", "ur", "vi", "zh", "zu",
}

# Meta Muse Voice: o seletor do app exibe a sigla, mas o parâmetro
# `languageBias` leva o idioma por extenso entre colchetes.
METAMUSE_LANGUAGE_NAMES = {
    "ar": "Arabic",
    "bn": "Bengali",
    "nl": "Dutch",
    "en": "English",
    "fr": "French",
    "de": "German",
    "he": "Hebrew",
    "hi": "Hindi",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "kn": "Kannada",
    "ko": "Korean",
    "ms": "Malay",
    "zh": "Mandarin Chinese",
    "mr": "Marathi",
    "pl": "Polish",
    "pt": "Portuguese",
    "es": "Spanish",
    "tl": "Tagalog",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tr": "Turkish",
    "vi": "Vietnamese",
}

METAMUSE_CODES = set(METAMUSE_LANGUAGE_NAMES)

# Alibaba Fun ASR/Qwen: códigos cobertos pelos modelos fun-asr-flash (REST)
# e qwen-audio-3.0-asr-flash-streaming (WS). O app exibe a sigla; o parâmetro
# centralizado `language_hints` leva a sigla em array — ou é omitido (auto).
ALIBABA_CODES = {
    "zh", "en", "ja", "ko", "vi", "th", "id", "ms", "tl", "hi", "ar", "fr",
    "de", "es", "pt", "ru", "it", "nl", "sv", "da", "fi", "no", "el", "pl",
    "cs", "hu", "ro", "bg", "hr", "sk",
}

# ---------------- Settings keys ----------------

KEY_LANGUAGE_MODE = {
    "deepgram": "deepgram_language_mode",
    "assemblyai": "assemblyai_language_mode",
    "elevenlabs": "elevenlabs_language_mode",
    "grok": "grok_language_mode",
    "metamuse": "metamuse_language_mode",
    "alibaba": "alibaba_language_mode",
}
KEY_LANGUAGE_CUSTOM = {
    "deepgram": "deepgram_language_custom",
    "assemblyai": "assemblyai_language_custom",
    "elevenlabs": "elevenlabs_language_custom",
    "grok": "grok_language_custom",
    "metamuse": "metamuse_language_custom",
    "alibaba": "alibaba_language_custom",
}
DEFAULT_MODE = {
    "deepgram": "pt-BR",
    "assemblyai": "pt",
    "elevenlabs": "pt",
    "grok": "pt",
    "metamuse": "pt",
    "alibaba": "pt",
}
MENU_OPTIONS = {
    "deepgram": ["multi", "pt-BR", "en", "es", "custom"],
    "assemblyai": ["multi", "pt", "es", "en", "custom"],
    "elevenlabs": ["multi", "pt", "es", "en", "custom"],
    "grok": ["multi", "pt", "en", "es", "custom"],
    "metamuse": ["multi", "pt", "en", "es", "custom"],
    "alibaba": ["multi", "pt", "en", "es", "custom"],
}

# Labels de exibição (SOMENTE cosmético): o que o usuário vê nos menus e
# botões. Os valores reais (as chaves) continuam sendo enviados nas
# requisições — nunca mude os valores, apenas estas labels.
LANGUAGE_LABELS = {"multi": "auto"}

# ---------------- Seletor de idioma da aba Transcrição ----------------
#
# A aba Transcrição escolhe VÁRIOS modelos ao mesmo tempo, então o seletor
# guarda uma opção genérica (auto/pt/en/es) e o valor REAL de cada provedor é
# montado na hora da requisição. Regra permanente: NUNCA traduzir a opção em
# um parâmetro único e enviá-lo a todos os modelos — cada provedor recebe o
# formato que ele próprio entende (mesma regra da aba Ocorrência).
KEY_TRANSCRIPTION_LANGUAGE = "transcription_language"
TRANSCRIPTION_LANGUAGE_OPTIONS = ("auto", "pt", "en", "es")
DEFAULT_TRANSCRIPTION_LANGUAGE = "pt"
# Opção -> valor de modo do provedor. "auto" é o "multi" interno (detecção
# nativa); "pt" usa "pt-BR" no Deepgram (único provedor que distingue a
# variante); o servidor local (Granite NAR) não tem parâmetro de idioma e por
# isso não aparece nesta tabela.
TRANSCRIPTION_OPTION_MODES = {
    "deepgram": {"auto": "multi", "pt": "pt-BR", "en": "en", "es": "es"},
    "assemblyai": {"auto": "multi", "pt": "pt", "en": "en", "es": "es"},
    "elevenlabs": {"auto": "multi", "pt": "pt", "en": "en", "es": "es"},
    "grok": {"auto": "multi", "pt": "pt", "en": "en", "es": "es"},
    "metamuse": {"auto": "multi", "pt": "pt", "en": "en", "es": "es"},
    "alibaba": {"auto": "multi", "pt": "pt", "en": "en", "es": "es"},
}


def transcription_language_option(settings: dict) -> str:
    """Opção escolhida na aba Transcrição (auto/pt/en/es). Padrão: "auto"."""
    value = str(settings.get(KEY_TRANSCRIPTION_LANGUAGE) or "").strip().casefold()
    return value if value in TRANSCRIPTION_LANGUAGE_OPTIONS else DEFAULT_TRANSCRIPTION_LANGUAGE


def language_mode_for_option(provider: str, option: str) -> str | None:
    """Modo do provedor para a opcao do seletor. None = provedor sem idioma."""
    modes = TRANSCRIPTION_OPTION_MODES.get(provider)
    if not modes:
        return None
    return modes.get(str(option or "").strip().casefold(), modes["auto"])


def apply_transcription_language_option(
    settings: dict, providers, option: str | None = None
) -> dict:
    """Cópia de settings com a opção traduzida para o valor de CADA provedor.

    Recebe a lista de provedores do lote e grava, só na cópia, a chave de modo
    de cada um (o seletor nunca monta o parâmetro da requisição).
    """
    resolved = option or transcription_language_option(settings)
    updated = settings.copy()
    for provider in providers:
        mode = language_mode_for_option(provider, resolved)
        if mode:
            updated[KEY_LANGUAGE_MODE[provider]] = mode
    return updated


def parse_codes(raw: str) -> list[str]:
    """Normaliza a entrada do usuário: ' en ,  es , pt ' -> ['en', 'es', 'pt']."""
    return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]


def language_mode(settings: dict, provider: str) -> str:
    value = str(settings.get(KEY_LANGUAGE_MODE[provider]) or "").strip()
    return value or DEFAULT_MODE[provider]


def language_custom(settings: dict, provider: str) -> str:
    return str(settings.get(KEY_LANGUAGE_CUSTOM[provider]) or "").strip()


def is_valid_code(provider: str, code: str) -> bool:
    if provider == "deepgram":
        return code in DEEPGRAM_CODES
    if provider == "assemblyai":
        return code in ASSEMBLYAI_CODES
    if provider == "elevenlabs":
        return code in ELEVENLABS_CODES_2 or code in ELEVENLABS_CODES_3
    if provider == "grok":
        return code in GROK_CODES
    if provider == "metamuse":
        return code in METAMUSE_CODES
    if provider == "alibaba":
        return code in ALIBABA_CODES
    return False


def invalid_codes(provider: str, codes: list[str]) -> list[str]:
    return [code for code in codes if not is_valid_code(provider, code)]


def codes_for_help(provider: str) -> str:
    if provider == "deepgram":
        return ", ".join(sorted(DEEPGRAM_CODES))
    if provider == "assemblyai":
        return ", ".join(sorted(ASSEMBLYAI_CODES))
    if provider == "grok":
        return ", ".join(sorted(GROK_CODES))
    if provider == "metamuse":
        return ", ".join(sorted(METAMUSE_CODES))
    if provider == "alibaba":
        return ", ".join(sorted(ALIBABA_CODES))
    # ElevenLabs: a tela "?" mostra apenas os códigos de 2 letras.
    return ", ".join(sorted(ELEVENLABS_CODES_2))


# ---------------- Idioma: parâmetros por provedor ----------------

def deepgram_language_param(settings: dict) -> str:
    mode = language_mode(settings, "deepgram")
    if mode == "custom":
        return language_custom(settings, "deepgram")
    return mode


def assemblyai_rest_language(settings: dict) -> tuple[bool, str | None]:
    """REST: (language_detection, language_code). detection=True => omitir language_code."""
    mode = language_mode(settings, "assemblyai")
    if mode == "multi":
        return True, None
    if mode == "custom":
        codes = parse_codes(language_custom(settings, "assemblyai"))
        if len(codes) >= 2:
            return True, None
        return False, (codes[0] if codes else None)
    return False, mode


def assemblyai_ws_language_codes(settings: dict) -> list[str]:
    """WS: lista para language_codes (vazia = omitir = multi)."""
    mode = language_mode(settings, "assemblyai")
    if mode == "multi":
        return []
    if mode == "custom":
        return parse_codes(language_custom(settings, "assemblyai"))
    return [mode]


def elevenlabs_rest_language_code(settings: dict) -> str | None:
    """REST: language_code único; multi e custom com vários omitem."""
    mode = language_mode(settings, "elevenlabs")
    if mode == "multi":
        return None
    if mode == "custom":
        codes = parse_codes(language_custom(settings, "elevenlabs"))
        return codes[0] if len(codes) == 1 else None
    return mode


def elevenlabs_ws_language(settings: dict) -> tuple[str | None, list[str]]:
    """WS: (language_code, secondary_languages). O primeiro código é o principal."""
    mode = language_mode(settings, "elevenlabs")
    if mode == "multi":
        return None, []
    if mode == "custom":
        codes = parse_codes(language_custom(settings, "elevenlabs"))
        if not codes:
            return None, []
        return codes[0], codes[1:]
    return mode, []


def grok_language_param(settings: dict) -> str | None:
    """Grok: language=<valor>; multi e custom com 2+ omitem (detecção nativa)."""
    mode = language_mode(settings, "grok")
    if mode == "multi":
        return None
    if mode == "custom":
        codes = parse_codes(language_custom(settings, "grok"))
        return codes[0] if len(codes) == 1 else None
    return mode or None


def metamuse_language_bias(settings: dict) -> list[str] | None:
    """Meta Muse Voice: languageBias por extenso; multi omite (autodetecção).

    pt/en/es diretos e cada sigla do custom viram o nome por extenso
    (ex.: pt -> ["Portuguese"]). Siglas fora da tabela são ignoradas; se
    nenhuma restar, retorna None (equivale a omitir o parâmetro).
    """
    mode = language_mode(settings, "metamuse")
    if mode == "multi":
        return None
    if mode == "custom":
        codes = parse_codes(language_custom(settings, "metamuse"))
    else:
        codes = [mode]
    names = [METAMUSE_LANGUAGE_NAMES[code] for code in codes if code in METAMUSE_LANGUAGE_NAMES]
    return names or None


def metamuse_mode(diarize_checked: bool) -> str:
    """Meta Muse Voice: a diarização é o próprio `mode` (sem flag booleana)."""
    return "DIARIZATION" if diarize_checked else "ENDPOINTING"


def alibaba_language_hints(settings: dict) -> list[str] | None:
    """Alibaba Fun ASR/Qwen: função CENTRALIZADA de idioma (REST e WS).

    Retorna a lista para `language_hints` ou None para omitir a propriedade
    (detecção automática: nunca enviar lista vazia, "auto" ou "automatic").
    Códigos fora da tabela são ignorados; se nenhum restar, retorna None.
    """
    mode = language_mode(settings, "alibaba")
    if mode == "multi":
        return None
    if mode == "custom":
        codes = parse_codes(language_custom(settings, "alibaba"))
    else:
        codes = [mode]
    hints = [code for code in codes if code in ALIBABA_CODES]
    return hints or None


# ---------------- Diarização: parâmetros por provedor ----------------

def supports_diarize(provider: str, is_live: bool) -> bool:
    return provider in ("deepgram", "assemblyai", "elevenlabs", "grok", "metamuse")


def deepgram_diarize_query(checked: bool) -> str | None:
    """Deepgram: diarize_model=latest (o diarize=true é deprecated)."""
    return "diarize_model=latest" if checked else None


def assemblyai_rest_diarize(checked: bool) -> tuple[bool, bool]:
    """AssemblyAI REST: (speaker_labels, punctuate). speaker_labels exige punctuate=true."""
    return (True, True) if checked else (False, False)


def assemblyai_ws_diarize_query(checked: bool) -> str | None:
    return "speaker_labels=true" if checked else None


def elevenlabs_rest_diarize(checked: bool) -> bool:
    return checked


def elevenlabs_ws_diarize_query(checked: bool) -> str | None:
    # Scribe v2 Realtime não suporta diarização: nunca enviar parâmetros.
    return None


def grok_diarize_query(checked: bool) -> str | None:
    return "diarize=true" if checked else None


def grok_rest_diarize(checked: bool) -> bool:
    return checked


# ---------------- Keywords (termos de reforço) ----------------
#
# A lista é ÚNICA no app (tela "Keywords" das Configurações) e cada provedor
# monta o SEU parâmetro na hora da requisição — nunca um valor único para
# todos, porque nome e formato diferem entre eles (mesma regra do idioma):
#
#   Deepgram    keyterm=...             (repetido: query REST e WS)
#   Grok STT    keyterm=...             (repetido: query WS / campo multipart)
#   ElevenLabs  keyterms=...            (repetido: query WS / campo multipart)
#   AssemblyAI  keyterms_prompt=[...]   (array JSON: query WS / campo REST)
#   Meta Muse   keywords: [...]         (JSON do handshake WS / do corpo REST)
#   Alibaba     vocabulary: {termo: peso}  (parâmetro DashScope REST e WS)
#   servidor    (Granite NAR: não tem biasing — nenhum parâmetro)

KEY_STT_KEYWORDS = "stt_keywords"
# Chave da checkbox "Keywords" das telas de Transcrição (REST) e Ocorrência
# (WS): desligada, NENHUMA requisição leva termos — a lista continua salva.
KEY_STT_KEYWORDS_ENABLED = "stt_keywords_enabled"
MAX_STT_KEYWORDS = 100
# Limite por termo: 20 caracteres = o MENOR limite real entre REST e WebSocket.
# Medido nas APIs (10/09), com um termo longo:
#   ElevenLabs WS (Scribe realtime) -> invalid_request: "Each keyterm must be at
#       most 20 characters"
#   Meta Muse Voice WS -> BadRequestException: "ASR keyword 0 exceeds the
#       maximum length of 20 characters"
#   ElevenLabs REST -> "All keywords must be less than 50 characters" (50)
#   xAI (REST e WS) -> "too long (200 chars). Maximum is 50 chars" (50)
# Como a lista é ÚNICA e alimenta REST e WS, o teto do cadastro é o menor de
# todos: assim um termo cadastrado nunca quebra a Ocorrência (WebSocket).
MAX_STT_KEYWORD_LENGTH = 20
# Peso das hotwords do DashScope (os exemplos oficiais usam 4, 5 e 50).
ALIBABA_KEYWORD_WEIGHT = 5
# Orçamento de tokens dos keyterms do Deepgram. A doc diz 500 tokens por
# requisição e devolve ERRO acima disso — medido ao vivo (10/09):
#   40 termos de 20 chars  -> OK
#   60 termos de 20 chars  -> HTTP 400 "Keyterm limit exceeded. The maximum
#                             number of tokens across all keyterms is 500."
#   50 termos de 15 chars  -> OK
#  100 termos de 15 chars  -> HTTP 400
#  200 termos de  8 chars  -> OK
# Ou seja: o teto é por TOKENS, não por quantidade (termos curtos passam de
# 100). O app usa margem de segurança e envia só os primeiros que couberem.
DEEPGRAM_KEYTERM_TOKEN_BUDGET = 450


def estimate_keyterm_tokens(term: str) -> int:
    """Estimativa CONSERVADORA dos tokens de um keyterm (BPE do Deepgram).

    Não há tokenizador local confiável: a estimativa erra PARA CIMA de
    propósito, porque subestimar significa HTTP 400 e a transcrição do arquivo
    perdida. Calibração com as medições acima (termos de 20 caracteres com
    letras → 11 tokens; 450/11 = 40, que é exatamente o que a API aceitou).
    """
    nucleo = max(1, (len(term) + 2) // 2)
    # Dígito/símbolo costuma virar token próprio em vez de se juntar à palavra.
    nao_alfabeticos = sum(1 for c in term if not c.isalpha())
    return nucleo + nao_alfabeticos


def keywords_for_provider(settings: dict, provider: str) -> list[str]:
    """Termos que REALMENTE vão para o provedor: os PRIMEIROS que cabem.

    A ordem da lista é a prioridade. Para o Deepgram o corte é pelo orçamento
    de tokens; nos demais, pelo teto de quantidade. Nada é alterado no termo
    (nunca truncar texto do usuário sem avisar) — o excedente é apenas não
    enviado, e a tela de ajuda explica isso.
    """
    terms = stt_keywords(settings)
    if not terms:
        return []
    # Provedor sem biasing (servidor/Granite NAR): nunca manda nada.
    if not supports_keywords(provider):
        return []
    if provider != "deepgram":
        return terms[:MAX_STT_KEYWORDS]
    usados: list[str] = []
    gasto = 0
    for term in terms:
        custo = estimate_keyterm_tokens(term)
        if gasto + custo > DEEPGRAM_KEYTERM_TOKEN_BUDGET:
            break
        usados.append(term)
        gasto += custo
    return usados


def keywords_query_params(settings: dict, provider: str) -> list[tuple[str, str]]:
    """Pares (chave, valor) do query string/WS para o provedor.

    Lista vazia = nada a anexar (provedor sem biasing por query: Muse e Alibaba
    levam as keywords no JSON do corpo). O valor sai CRU — quem monta a URL
    faz o quote. Os termos já vêm cortados pelo limite do provedor.
    """
    terms = keywords_for_provider(settings, provider)
    if not terms:
        return []
    if provider in ("deepgram", "grok"):
        return [("keyterm", term) for term in terms]
    if provider == "elevenlabs":
        return [("keyterms", term) for term in terms]
    if provider == "assemblyai":
        # A AssemblyAI espera UM parâmetro com o array em JSON.
        return [("keyterms_prompt", json.dumps(terms, ensure_ascii=False))]
    return []


def metamuse_keywords(settings: dict) -> list[str] | None:
    """Meta Muse Voice: `keywords` (lista); None = omitir o campo."""
    terms = keywords_for_provider(settings, "metamuse")
    return terms or None


def alibaba_vocabulary(settings: dict) -> dict[str, int] | None:
    """Alibaba (DashScope): `vocabulary` como {termo: peso}; None = omitir."""
    terms = keywords_for_provider(settings, "alibaba")
    if not terms:
        return None
    return {term: ALIBABA_KEYWORD_WEIGHT for term in terms}

# Provedores que aceitam algum tipo de termo de reforço (o servidor local não).
KEYWORD_PROVIDERS = ("deepgram", "grok", "elevenlabs", "assemblyai", "metamuse", "alibaba")


def normalize_stt_keywords(raw) -> list[str]:
    """Lista de keywords normalizada: sem vazios, sem repetidas, ordem mantida."""
    if isinstance(raw, str):
        candidates = [part.strip() for part in raw.replace("\n", ",").split(",")]
    elif isinstance(raw, (list, tuple, set)):
        candidates = [str(part).strip() for part in raw]
    else:
        return []
    keywords: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        key = candidate.casefold()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(candidate)
        if len(keywords) >= MAX_STT_KEYWORDS:
            break
    return keywords


def stt_keywords_enabled(settings: dict) -> bool:
    """A checkbox "Keywords" está marcada? (ausente = ligada)."""
    value = settings.get(KEY_STT_KEYWORDS_ENABLED, True)
    if isinstance(value, str):
        return value.strip().casefold() not in {"0", "false", "no", "off", ""}
    return bool(value)


def stt_keywords(settings: dict) -> list[str]:
    """Keywords que devem ir na requisição (vazio se a checkbox estiver off)."""
    if not stt_keywords_enabled(settings):
        return []
    return normalize_stt_keywords(settings.get(KEY_STT_KEYWORDS))


def supports_keywords(provider: str) -> bool:
    return provider in KEYWORD_PROVIDERS
