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

# ---------------- Settings keys ----------------

KEY_LANGUAGE_MODE = {
    "deepgram": "deepgram_language_mode",
    "assemblyai": "assemblyai_language_mode",
    "elevenlabs": "elevenlabs_language_mode",
    "grok": "grok_language_mode",
}
KEY_LANGUAGE_CUSTOM = {
    "deepgram": "deepgram_language_custom",
    "assemblyai": "assemblyai_language_custom",
    "elevenlabs": "elevenlabs_language_custom",
    "grok": "grok_language_custom",
}
DEFAULT_MODE = {
    "deepgram": "pt-BR",
    "assemblyai": "pt",
    "elevenlabs": "pt",
    "grok": "pt",
}
MENU_OPTIONS = {
    "deepgram": ["multi", "pt-BR", "en", "es", "custom"],
    "assemblyai": ["multi", "pt", "es", "en", "custom"],
    "elevenlabs": ["multi", "pt", "es", "en", "custom"],
    "grok": ["multi", "pt", "en", "es", "custom"],
}

# Labels de exibição (SOMENTE cosmético): o que o usuário vê nos menus e
# botões. Os valores reais (as chaves) continuam sendo enviados nas
# requisições — nunca mude os valores, apenas estas labels.
LANGUAGE_LABELS = {"multi": "auto"}


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


# ---------------- Diarização: parâmetros por provedor ----------------

def supports_diarize(provider: str, is_live: bool) -> bool:
    return provider in ("deepgram", "assemblyai", "elevenlabs", "grok")


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
