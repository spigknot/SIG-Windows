"""Regras de idioma e diarização por provedor STT — espelho EXATO do app Android.

Cada provedor tem parâmetros e formatos próprios; este módulo concentra a
validação e a tradução da escolha persistida nos parâmetros reais de cada
requisição (REST e WebSocket), evitando vazamento de parâmetros de um
provedor para outro. Mantém paridade com:
- Android: SttLanguageSettings.kt + SttDiarization.kt
"""
from __future__ import annotations

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
