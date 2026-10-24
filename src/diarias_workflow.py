"""Validação dos nove campos, geração conjunta e plano de impressão de Diárias."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping
import re
import threading

import diarias_mapa
import documents
from diarias_profiles import validate_diarias_profile

REQUIRED_FIELDS = (
    ("holerite_total", "Total de vencimentos"), ("holerite_mes", "Mês/ano do holerite"),
    ("abertura_data", "Data de ida"), ("abertura_hora", "Hora de ida"),
    ("fechamento_data", "Data de volta"), ("fechamento_hora", "Hora de volta"),
    ("req", "Requerimento"), ("mapa", "Mapa"), ("data", "Data do protocolo"),
)

MISSING_FIELDS_MESSAGE = "Há campos sem preencher."
PRINT_DOCUMENTS = (
    ("holerite", "Holerite", 1), ("escala", "Escala (somente a 1ª página)", 1),
    ("talao", "Talão", 1), ("protocolo", "Protocolo", 2),
    ("requerimento", "Requerimento", 1),
    ("declaracao", "Declaração de meios próprios", 1),
    ("mapa", "Mapa", 2),
)
PRINT_ATTACHMENT_KEYS = ("holerite", "escala", "talao", "protocolo")


class MissingDiariasFields(ValueError):
    def __init__(self, fields):
        self.fields = tuple(fields)
        super().__init__(MISSING_FIELDS_MESSAGE)


class DiariasCancelled(Exception):
    """O usuário cancelou antes de enviar a diária à impressora."""


def validate_fields(fields: Mapping[str, str]) -> dict[str, str]:
    values = {key: str(fields.get(key) or "").strip() for key, _ in REQUIRED_FIELDS}
    missing = [key for key, _label in REQUIRED_FIELDS if not values[key]]
    if missing:
        raise MissingDiariasFields(missing)
    labels = dict(REQUIRED_FIELDS, escala_mes="Mês/ano da escala")
    if str(fields.get("escala_mes") or "").strip():
        values["escala_mes"] = str(fields["escala_mes"]).strip()
    for keys, pattern, date_format, expected in (
        (("holerite_mes", "escala_mes"), r"[0-9]{2}/[0-9]{4}", "%m/%Y", "MM/AAAA"),
        (("abertura_data", "fechamento_data", "data"), r"[0-9]{2}/[0-9]{2}/[0-9]{4}", "%d/%m/%Y", "DD/MM/AAAA"),
        (("abertura_hora", "fechamento_hora"), r"[0-9]{2}:[0-9]{2}", "%H:%M", "HH:MM"),
    ):
        for key in keys:
            if key not in values:
                continue
            try:
                if not re.fullmatch(pattern, values[key]):
                    raise ValueError()
                datetime.strptime(values[key], date_format)
            except ValueError:
                raise ValueError(f"Confira {labels[key].lower()} no formato {expected}.") from None
    if not re.fullmatch(r"(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+),[0-9]{2}", values["holerite_total"]):
        raise ValueError("Confira o total de vencimentos no formato 1.234,56.")
    for key in ("req", "mapa"):
        if not re.fullmatch(r"[0-9]+/[0-9]{4}", values[key]):
            raise ValueError(f"Confira o protocolo de {labels[key].lower()} no formato número/AAAA.")
    return values


@dataclass(frozen=True)
class DiariasBundle:
    fields: dict[str, str]
    template_kind: str
    requerimento: dict[str, str]
    mapa: diarias_mapa.DiariasMapaData
    declaracao: dict[str, str]
    meios_proprios: bool


def prepare_bundle(fields: Mapping[str, str], *, profile: Mapping[str, str],
                   valor_ufesp: str, oitiva_delegacia: str, meios_proprios: bool) -> DiariasBundle:
    values = validate_fields(fields)
    selected = validate_diarias_profile(profile)
    kind, requerimento = documents.prepare_diarias_requerimento(
        data_abertura=values["abertura_data"], hora_abertura=values["abertura_hora"],
        data_fechamento=values["fechamento_data"], hora_fechamento=values["fechamento_hora"],
        total_vencimentos=values["holerite_total"], data_protocolo=values["data"],
        protocolo_requerimento=values["req"], perfil=selected,
    )
    mapa = diarias_mapa.prepare_diarias_mapa(
        total_vencimentos=values["holerite_total"], valor_ufesp=valor_ufesp,
        data_ida=values["abertura_data"], horario_ida=values["abertura_hora"],
        data_volta=values["fechamento_data"], horario_volta=values["fechamento_hora"],
        data_protocolo=values["data"], protocolo_requerimento=values["req"],
        protocolo_mapa=values["mapa"], meios_proprios=meios_proprios,
        profile=selected, oitiva_delegacia=oitiva_delegacia,
    )
    declaracao = documents.prepare_declaracao_meios_proprios(
        data_ida=values["abertura_data"], data_protocolo=values["data"], perfil=selected,
    )
    return DiariasBundle(values, kind, requerimento, mapa, declaracao, bool(meios_proprios))


def _next_path(directory: Path, stem: str, extension: str) -> Path:
    candidate = directory / (stem + extension)
    suffix = 2
    while candidate.exists():
        candidate = directory / f"{stem}_{suffix}{extension}"
        suffix += 1
    return candidate


def generate_bundle(directory: Path, bundle: DiariasBundle, *, pdf: bool,
                    progress: Callable | None = None, cancel: threading.Event | None = None) -> dict[str, Path]:
    """Gera cada documento com nome livre; nunca sobrescreve o arquivo anterior."""
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError("Selecione uma pasta de destino existente.")
    date_ida = bundle.mapa.data_ida.strftime("%d-%m-%Y")
    jobs = [
        ("requerimento", "Gerando requerimento", f"requerimento_{bundle.template_kind}_{date_ida}", ".pdf" if pdf else ".docx"),
        ("mapa", "Gerando mapa", diarias_mapa.diarias_mapa_filename_stem(bundle.mapa.data_ida, bundle.mapa.menos_de_12_horas), ".pdf" if pdf else ".xlsx"),
    ]
    if bundle.meios_proprios:
        jobs.append(("declaracao", "Gerando declaração de meios próprios", f"declaracao_meios_proprios_{date_ida}", ".pdf" if pdf else ".docx"))
    output = {}
    for key, label, stem, extension in jobs:
        if cancel is not None and cancel.is_set():
            raise DiariasCancelled()
        destination = _next_path(directory, stem, extension)
        if progress:
            progress("start", key, label, None)
        try:
            if key == "requerimento":
                generator = documents.generate_diarias_requerimento_pdf if pdf else documents.generate_diarias_requerimento
                generator(bundle.template_kind, destination, bundle.requerimento)
            elif key == "mapa":
                diarias_mapa.generate_diarias_mapa(destination, bundle.mapa)
            else:
                generator = documents.generate_declaracao_meios_proprios_pdf if pdf else documents.generate_declaracao_meios_proprios
                generator(destination, bundle.declaracao)
        except Exception as exc:
            if progress:
                progress("error", key, label, str(exc))
            # Mantém os documentos já concluídos e identifica o arquivo que falhou.
            raise RuntimeError(f"{label}: {exc}") from exc
        output[key] = destination
        if progress:
            progress("finish", key, label, destination.name)
    if cancel is not None and cancel.is_set():
        raise DiariasCancelled()
    return output


@dataclass(frozen=True)
class PrintItem:
    path: Path
    label: str
    copies: int = 1
    first_page_only: bool = False
    duplex_short_edge: bool = False


def print_document_rows(*, meios_proprios: bool):
    """A lista de vias e o plano usam a mesma regra para declaração e talão."""
    return tuple(row for row in PRINT_DOCUMENTS
                 if (row[0] != "declaracao" or meios_proprios)
                 and (row[0] != "talao" or not meios_proprios))


def validate_print_attachments(attachments: Mapping[str, str | Path], *, meios_proprios: bool = False) -> dict[str, Path]:
    """Retorna somente PDFs disponíveis; anexos ausentes não impedem a impressão."""
    result = {}
    for key in PRINT_ATTACHMENT_KEYS:
        if key == "talao" and meios_proprios:
            continue
        path = Path(attachments.get(key) or "")
        if path.suffix.casefold() == ".pdf" and path.is_file():
            result[key] = path
    return result


def validate_print_copies(copies: Mapping[str, object] | None, *, meios_proprios: bool,
                         attachments: Mapping[str, str | Path] | None = None) -> dict[str, int]:
    rows = print_document_rows(meios_proprios=meios_proprios)
    available = None if attachments is None else validate_print_attachments(attachments, meios_proprios=meios_proprios)
    values = {key: "0" if available is not None and key in PRINT_ATTACHMENT_KEYS and key not in available
              else str(default if copies is None else copies.get(key, "")).strip()
              for key, _label, default in rows}
    missing = ["copies:" + key for key, value in values.items() if not value]
    if missing:
        raise MissingDiariasFields(missing)
    result = {}
    for key, label, _default in rows:
        value = values[key]
        if not value.isascii() or not value.isdigit() or not 0 <= int(value) <= 99:
            raise ValueError(f"Informe de 0 a 99 vias para {label.lower()}.")
        result[key] = int(value)
    return result


def build_print_plan(generated: Mapping[str, Path], attachments: Mapping[str, str | Path],
                     *, copies: Mapping[str, object] | None = None) -> list[PrintItem]:
    meios_proprios = "declaracao" in generated
    attached = validate_print_attachments(attachments, meios_proprios=meios_proprios)
    counts = validate_print_copies(copies, meios_proprios=meios_proprios, attachments=attached)
    plan = [PrintItem(generated["mapa"], "Mapa", counts["mapa"], duplex_short_edge=True),
            PrintItem(generated["requerimento"], "Requerimento", counts["requerimento"])]
    if "protocolo" in attached:
        plan.insert(1, PrintItem(attached["protocolo"], "Protocolo", counts["protocolo"]))
    if "declaracao" in generated:
        plan.append(PrintItem(generated["declaracao"], "Declaração de meios próprios", counts["declaracao"]))
    if "talao" in attached:
        plan.append(PrintItem(attached["talao"], "Talão", counts["talao"]))
    for key, label in (("escala", "Escala"), ("holerite", "Holerite")):
        if key in attached:
            plan.append(PrintItem(attached[key], label, counts[key], first_page_only=key == "escala"))
    return [item for item in plan if item.copies > 0]
