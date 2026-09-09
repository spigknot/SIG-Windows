"""Base de nomes: extracao de nomes proprios, chave fonetica e persistencia JSON.

Base em app_env.settings_path().parent/nomes.json (nome do arquivo em name_database_path).
Sem Tkinter."""

import json
import re
import unicodedata
from app_env import resource_path, settings_path
from pathlib import Path


def parse_assistant_names(raw_text: str) -> list[str]:
    clean = raw_text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean).strip()
    names: list[str] = []

    candidates = []
    array_start, array_end = clean.find("["), clean.rfind("]")
    object_start, object_end = clean.find("{"), clean.rfind("}")
    if array_start >= 0 and array_end > array_start:
        candidates.append(clean[array_start : array_end + 1])
    if object_start >= 0 and object_end > object_start:
        candidates.append(clean[object_start : object_end + 1])

    def collect(value):
        if isinstance(value, str):
            add_assistant_name(names, value)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)

    for candidate in candidates:
        try:
            collect(json.loads(candidate))
            if names:
                break
        except json.JSONDecodeError:
            continue
    if not names:
        for match in re.finditer(r'"([^"\\]+)"', clean):
            add_assistant_name(names, match.group(1))
    if not names:
        for value in re.split(r"[,;\n]", clean):
            add_assistant_name(names, value)
    return distinct_names(names)


def add_assistant_name(names: list[str], value: str):
    clean = value.strip().strip("\"'[]{}").strip()
    if clean and len(clean) <= 80:
        names.append(clean.upper())


def distinct_names(names: list[str]) -> list[str]:
    result = []
    seen = set()
    for name in names:
        key = name.upper()
        if key not in seen:
            seen.add(key)
            result.append(name)
    return result


UPPERCASE_NAME_SEQUENCE = re.compile(
    r"(?<![A-Za-zÀ-ÖØ-öø-ÿ0-9])"
    r"[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'’-]+"
    r"(?:\s+[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'’-]+)*"
    r"(?![A-Za-zÀ-ÖØ-öø-ÿ0-9])"
)


UPPERCASE_WORD = re.compile(r"[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'’-]+")


IGNORED_UPPERCASE_WORDS = {"BO", "CPF", "RG", "IMEI", "SP", "WHATSAPP"}


NAME_CONNECTORS = {"DA", "DE", "DO", "DAS", "DOS", "E"}


def extract_uppercase_names(text: str) -> list[str]:
    names = []
    for match in UPPERCASE_NAME_SEQUENCE.finditer(text):
        candidate = re.sub(r"\s+", " ", match.group(0).strip())
        if len(candidate) >= 2 and candidate not in IGNORED_UPPERCASE_WORDS:
            names.append(candidate)
    return distinct_names(names)


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.strip().upper())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return re.sub(r"[^A-Z'’-]", "", normalized)


def phonetic_name_key(normalized: str) -> str:
    value = normalized
    value = value.replace("PH", "F").replace("TH", "T").replace("Y", "I").replace("W", "V")
    value = re.sub(r"^H", "", value)
    value = value.replace("QU", "C").replace("K", "C").replace("Q", "C")
    value = re.sub(r"C(?=[EI])", "S", value)
    value = re.sub(r"G(?=[EI])", "J", value)
    value = value.replace("Z", "S")
    return re.sub(r"([A-Z])\1+", r"\1", value)


def matching_name_keys(value: str) -> set[str]:
    normalized = normalize_name(value)
    if not normalized:
        return set()
    return {normalized, phonetic_name_key(normalized)}


def load_name_database() -> set[str]:
    path = name_database_path()
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        keys.update(matching_name_keys(line))
    return keys


def name_database_path() -> Path:
    path = settings_path().parent / "Nomes" / "nomes.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        default_path = resource_path("assets/default_nomes.txt")
        path.write_text(
            default_path.read_text(encoding="utf-8", errors="replace") if default_path.exists() else "",
            encoding="utf-8",
        )
    return path


def add_name_to_database(value: str) -> bool:
    name = value.strip().upper()
    if not name or any(char in name for char in "\t\r\n"):
        return False
    path = name_database_path()
    current = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if any(normalize_name(item) == normalize_name(name) for item in current):
        return False
    path.write_text("\n".join([*current, name]).strip() + "\n", encoding="utf-8")
    return True


def remove_name_from_database(value: str) -> bool:
    target = normalize_name(value)
    if not target:
        return False
    path = name_database_path()
    current = path.read_text(encoding="utf-8", errors="replace").splitlines()
    remaining = [item for item in current if normalize_name(item) != target]
    if len(remaining) == len(current):
        return False
    path.write_text("\n".join(remaining).strip() + "\n", encoding="utf-8")
    return True


def extract_names_from_database(text: str, name_database: set[str]) -> list[str]:
    if not name_database:
        return []
    names = []
    for match in UPPERCASE_NAME_SEQUENCE.finditer(text):
        words = UPPERCASE_WORD.findall(match.group(0))
        candidate_words = [word for word in words if normalize_name(word) not in NAME_CONNECTORS]
        if candidate_words and all(matching_name_keys(word) & name_database for word in candidate_words):
            names.append(" ".join(candidate_words))
    return distinct_names(names)
