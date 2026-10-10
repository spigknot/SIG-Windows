"""Validação dos nove campos, geração conjunta e plano de impressão de Diárias."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping
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
    ("mapa", "Mapa", 2), ("protocolo", "Protocolo", 2),
    ("requerimento", "Requerimento", 1),
    ("declaracao", "Declaração de meios próprios", 1),
    ("talao", "Talão", 1),
    ("escala", "Escala (somente a 1ª página)", 1), ("holerite", "Holerite", 1),
)


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
    try:
        datetime.strptime(values["holerite_mes"], "%m/%Y")
    except ValueError:
        raise ValueError("Confira o mês/ano do holerite (MM/AAAA).") from None
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
        ("mapa", "Gerando mapa", f"mapa_diaria_{date_ida}", ".pdf" if pdf else ".xlsx"),
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


def print_document_rows(*, meios_proprios: bool, talao_anexo: bool = False):
    """A lista de vias e o plano usam a mesma regra para declaração e talão."""
    return tuple(row for row in PRINT_DOCUMENTS
                 if (row[0] != "declaracao" or meios_proprios)
                 and (row[0] != "talao" or (talao_anexo and not meios_proprios)))


def validate_print_attachments(attachments: Mapping[str, str], *, meios_proprios: bool = False) -> dict[str, Path]:
    result, missing = {}, []
    keys = ["protocolo", "escala", "holerite"]
    if not meios_proprios and attachments.get("talao"):
        keys.append("talao")
    for key in keys:
        path = Path(attachments.get(key) or "")
        if path.suffix.casefold() != ".pdf" or not path.is_file():
            missing.append("attachment:" + key)
        result[key] = path
    if missing:
        raise MissingDiariasFields(missing)
    return result


def validate_print_copies(copies: Mapping[str, object] | None, *, meios_proprios: bool, talao_anexo: bool = False) -> dict[str, int]:
    rows = print_document_rows(meios_proprios=meios_proprios, talao_anexo=talao_anexo)
    values = {key: str(default if copies is None else copies.get(key, "")).strip() for key, _label, default in rows}
    missing = ["copies:" + key for key, value in values.items() if not value]
    if missing:
        raise MissingDiariasFields(missing)
    result = {}
    for key, label, _default in rows:
        value = values[key]
        if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 99:
            raise ValueError(f"Informe de 1 a 99 vias para {label.lower()}.")
        result[key] = int(value)
    return result


def build_print_plan(generated: Mapping[str, Path], attachments: Mapping[str, str],
                     *, copies: Mapping[str, object] | None = None) -> list[PrintItem]:
    meios_proprios = "declaracao" in generated
    attached = validate_print_attachments(attachments, meios_proprios=meios_proprios)
    counts = validate_print_copies(copies, meios_proprios=meios_proprios, talao_anexo="talao" in attached)
    plan = [PrintItem(generated["mapa"], "Mapa", counts["mapa"], duplex_short_edge=True),
            PrintItem(attached["protocolo"], "Protocolo", counts["protocolo"]),
            PrintItem(generated["requerimento"], "Requerimento", counts["requerimento"])]
    if "declaracao" in generated:
        plan.append(PrintItem(generated["declaracao"], "Declaração de meios próprios", counts["declaracao"]))
    if "talao" in attached:
        plan.append(PrintItem(attached["talao"], "Talão", counts["talao"]))
    plan.extend((PrintItem(attached["escala"], "Escala", counts["escala"], first_page_only=True),
                 PrintItem(attached["holerite"], "Holerite", counts["holerite"])))
    return plan
