"""Qualificacao (ocorrencia): parsing do JSON do modelo e formatacao dos campos.

Regras de idade/status ficam aqui. Rotulos da UI: LIVE_QUALIFICATION_FIELD_LABELS em sig_app.py.
Sem rede, sem Tkinter."""

import json
import re
from datetime import date


LIVE_QUALIFICATION_FIELD_IDS = (
    "nome",
    "rg",
    "cpf",
    "nascimento",
    "naturalidade",
    "profissao",
    "pai",
    "mae",
    "endereco",
    "bairro",
    "cidade",
    "telefone",
)


# Campos marcados por padrão na janela da engrenagem: os que já eram usados
# para preencher a caixa + RG (que passa a aparecer logo após o nome).
LIVE_QUALIFICATION_DEFAULT_SELECTED = frozenset(
    {
        "nome",
        "rg",
        "nascimento",
        "naturalidade",
        "profissao",
        "pai",
        "mae",
        "endereco",
        "bairro",
        "cidade",
        "telefone",
    }
)


def parse_qualification_json(
    raw_text: str,
    allowed_ids: list[str],
    field_order: tuple[tuple[str, str], ...],
) -> dict[str, str]:
    """Extrai e normaliza o JSON da IA, sem exibir campos não solicitados."""
    clean = str(raw_text or "").strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean).strip()
    start, end = clean.find("{"), clean.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("A IA não devolveu um JSON válido.")
    try:
        payload = json.loads(clean[start : end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"A IA devolveu um JSON inválido: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("A IA não devolveu um objeto JSON.")
    allowed = set(allowed_ids)
    normalized = {}
    for field_id, _label in field_order:
        if field_id not in allowed or field_id not in payload:
            continue
        value = payload[field_id]
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        value = str(value).strip()
        if value:
            normalized[field_id] = value
    known_ids = {field_id for field_id, _label in field_order}
    for field_id in allowed_ids:
        if field_id in known_ids or field_id not in payload:
            continue
        value = payload[field_id]
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        value = str(value).strip()
        if value:
            normalized[field_id] = value
    return normalized


def _qualification_age_in_years(value: str, today: date | None = None) -> int | None:
    """Calcula a idade completa a partir das datas mais comuns devolvidas pela IA."""
    raw = str(value or "").strip()
    match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", raw)
    if match:
        day, month, year = (int(item) for item in match.groups())
    else:
        match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw)
        if not match:
            return None
        year, month, day = (int(item) for item in match.groups())
    try:
        born = date(year, month, day)
    except ValueError:
        return None
    current = today or date.today()
    if born > current:
        return None
    return current.year - born.year - ((current.month, current.day) < (born.month, born.day))


def format_occurrence_qualification(
    raw_text: str,
    field_order: tuple[tuple[str, str], ...],
    selected_ids: set[str] | None = None,
) -> str:
    """Converte o JSON fixo da Ocorrência no texto narrativo usado pelo policial.

    ``selected_ids`` decide quais campos do JSON entram no texto; quando
    None, usa os campos padrão (LIVE_QUALIFICATION_DEFAULT_SELECTED).
    """
    fields = parse_qualification_json(raw_text, list(LIVE_QUALIFICATION_FIELD_IDS), field_order)
    absent_values = {
        "nao informado",
        "não informado",
        "nao encontrada",
        "não encontrada",
        "nao encontrado",
        "não encontrado",
        "nao disponivel",
        "não disponível",
        "n/a",
        "-",
    }
    fields = {
        field_id: value
        for field_id, value in fields.items()
        if str(value).strip().casefold() not in absent_values
    }
    if selected_ids is None:
        selected = LIVE_QUALIFICATION_DEFAULT_SELECTED
    else:
        selected = set(selected_ids)

    def included(field_id: str) -> bool:
        return field_id in selected and bool(str(fields.get(field_id, "")).strip())

    parts: list[str] = []

    name = fields.get("nome", "").strip()
    if included("nome") and name:
        parts.append(name.upper())

    # RG e CPF aparecem logo após o nome, com a sigla em maiúsculas.
    rg = fields.get("rg", "").strip()
    if included("rg") and rg:
        parts.append(f"RG: {rg}")
    cpf = fields.get("cpf", "").strip()
    if included("cpf") and cpf:
        parts.append(f"CPF: {cpf}")

    mother = fields.get("mae", "").strip() if included("mae") else ""
    father = fields.get("pai", "").strip() if included("pai") else ""
    if mother and father:
        parts.append(f"filho(a) de {mother} e {father}")
    elif mother:
        parts.append(f"filho(a) de {mother}")
    elif father:
        parts.append(f"filho(a) de {father}")

    if included("nascimento"):
        age = _qualification_age_in_years(fields.get("nascimento", ""))
        if age is not None:
            parts.append(f"{age} anos")

    # Nacionalidade Brasileira é parte fixa do modelo solicitado para esta tela.
    parts.append("de nacionalidade Brasileira")
    if included("naturalidade"):
        parts.append(f"natural de {fields['naturalidade'].strip()}")
    if included("profissao"):
        parts.append(f"de profissão {fields['profissao'].strip()}")
    if included("endereco"):
        parts.append(f"residente e domiciliado(a) à {fields['endereco'].strip()}")
    if included("bairro"):
        parts.append(fields["bairro"].strip())
    if included("cidade"):
        parts.append(f"na cidade de {fields['cidade'].strip()}")
    if included("telefone"):
        parts.append(f"Telefone: {fields['telefone'].strip()}")

    return f"{', '.join(parts)}." if parts else ""


def format_qualification_fields(
    payload: dict[str, str],
    field_order: tuple[tuple[str, str], ...],
    selected_ids: set[str] | None = None,
) -> str:
    """Exibe os campos como uma única linha filtrável pelas checkboxes."""
    known_ids = {field_id for field_id, _label in field_order}
    items = [
        f"{label}: {payload[field_id]}"
        for field_id, label in field_order
        if field_id in payload
        and (selected_ids is None or field_id in selected_ids)
    ]
    items.extend(
        f"{qualification_display_label(field_id)}: {value}"
        for field_id, value in payload.items()
        if field_id not in known_ids
    )
    return f"{', '.join(items)}." if items else ""


def qualification_display_label(field_id: str) -> str:
    """Converte um ID personalizado em um rótulo legível para a saída."""
    return " ".join(part.capitalize() for part in str(field_id).split("_") if part)


def history_completion_status(
    history_state: str,
    names_state: str = "idle",
    names_count: int = 0,
) -> str:
    # A extração de partes está temporariamente fora do fluxo. Os argumentos
    # antigos permanecem opcionais para não quebrar consumidores legados, mas
    # nunca mais influenciam o estado exibido após uma requisição de histórico.
    del names_state, names_count
    if history_state == "done":
        return "Histórico concluído."
    if history_state == "running":
        return "Redigindo histórico..."
    if history_state == "error":
        return "Histórico com erro."
    return ""
