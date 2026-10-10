"""Campos e regras dos perfis de policiais usados nos documentos de Diárias."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal


# Uma fonte comum para o formulário, a tabela e a validação dos perfis.
PROFILE_FIELDS = (
    ("nome", "Nome", "João da Silva"),
    ("rg", "RG", "12.345.678-9"),
    ("cpf", "CPF", "123.456.789-01"),
    ("cargo", "Cargo", "Investigador de Polícia"),
    ("classe", "Classe", "1, 2, 3 ou Especial"),
    ("delegacia", "Delegacia", "Delegacia de Polícia de Taguaí"),
    ("cidade_trabalho", "Cidade de trabalho", "Taguaí"),
    ("estado_civil", "Estado civil", "Casado"),
    ("nascimento", "Nascimento", "31/12/1980"),
    ("naturalidade", "Naturalidade", "São Paulo-SP"),
    ("pai", "Pai", "Antônio Domingues da Silva"),
    ("mae", "Mãe", "Maria José da Silva"),
    ("endereco", "Endereço", "Rua João Carniato, 430, Taguaí"),
    ("cidade_plantao", "Cidade do plantão", "Taquarituba"),
    ("banco", "Banco", "Banco do Brasil da cidade de Avaré-SP"),
    ("agencia", "Agência", "123-4"),
    ("conta", "Conta", "123456-7"),
    ("ufesp_index", "Índice UFESP", "9"),
)

PROFILE_CLASSES = ("1", "2", "3", "Especial")
_CLASS_PADRAO = {"1": "III", "2": "II", "3": "I", "Especial": "IV"}
_NAME_PARTICLES = frozenset(
    {"de", "da", "do", "das", "dos", "e", "em", "del", "della", "di", "du", "van", "von"}
)


def classe_padrao(classe: str) -> str:
    """Converte a classe do policial no padrão impresso nos documentos."""
    value = str(classe or "").strip()
    try:
        return _CLASS_PADRAO[value]
    except KeyError:
        raise ValueError("Classe deve ser 1, 2, 3 ou Especial.") from None


def format_profile_cargo(cargo: str, classe: str) -> str:
    """Cargo em maiúsculas com o texto da classe utilizado no mapa."""
    value = str(classe or "").strip()
    classe_padrao(value)
    suffix = "DE CLASSE ESPECIAL" if value == "Especial" else f"DE {value}ª CLASSE"
    return f"{str(cargo or '').strip().upper()} {suffix}"


def format_profile_name(nome: str) -> str:
    """Nome com iniciais maiúsculas e partículas sempre em minúsculas."""
    words = str(nome or "").split()
    return " ".join(
        word.lower() if word.casefold() in _NAME_PARTICLES else word.title()
        for word in words
    )


def validate_diarias_profile(values: Mapping[str, object]) -> dict[str, str]:
    """Valida e normaliza somente os campos editáveis de um perfil."""
    result: dict[str, str] = {}
    for key, label, _example in PROFILE_FIELDS:
        value = values.get(key, "")
        if not isinstance(value, str):
            raise ValueError(f"{label} deve ser preenchido como texto.")
        result[key] = value.strip()
        if key != "pai" and not result[key]:
            raise ValueError(f"Preencha o campo {label}.")

    classe_padrao(result["classe"])

    nascimento = result["nascimento"]
    if not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", nascimento):
        raise ValueError("Nascimento deve ser uma data válida no formato DD/MM/AAAA.")
    try:
        datetime.strptime(nascimento, "%d/%m/%Y")
    except ValueError:
        raise ValueError("Nascimento deve ser uma data válida no formato DD/MM/AAAA.") from None

    index = result["ufesp_index"]
    if not re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", index) or Decimal(index.replace(",", ".")) <= 0:
        raise ValueError("Índice UFESP deve ser um número positivo.")

    return result
