"""Historico das tabelas de transcricao (aba Transcricao -> tela Transcricoes).

Responsabilidade unica (docs/agents/module-map.md): guardar, listar, renomear,
excluir, juntar e exportar os registros de cada tarefa de transcricao, e medir/
limpar a pasta de temporarios. Sem Tkinter, sem rede.

Cada tarefa vira um JSON proprio em `%APPDATA%\\sig\\transcricoes` (fora do
`temp/`, para a limpeza de temporarios nunca apagar o historico). Formato:

    {
      "version": 1, "id": "...", "name": "...", "created_at": "ISO",
      "kind": "task" | "merged", "partial": bool,
      "models": ["Modelo A", "Modelo B"],
      "stats": [["Rotulo", "valor"], ...],
      "sources": ["id", ...],                # so nos registros juntados
      "rows": [{"file": "a.mp3", "size": 123,
                "cells": {"Modelo A": {"text": "...", "problem": ""}}}]
    }
"""

from __future__ import annotations

import csv
import html
import json
import os
import stat
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app_env import settings_path
from domain_models import (
    AudioJob,
    audio_job_attr,
    job_problem_reason_for_model,
    job_transcript_for_model,
)
from reporting import html_document

HISTORY_DIR_NAME = "transcricoes"
RECORD_VERSION = 1


def history_dir() -> Path:
    """Pasta do historico (criada sob demanda)."""
    path = settings_path().parent / HISTORY_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class HistoryRecord:
    id: str
    name: str
    created_at: str
    models: list[str]
    rows: list[dict]
    stats: list[list[str]] = field(default_factory=list)
    kind: str = "task"
    partial: bool = False
    sources: list[str] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.rows)

    @property
    def created_label(self) -> str:
        try:
            return datetime.fromisoformat(self.created_at).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return self.created_at

    def to_dict(self) -> dict:
        return {
            "version": RECORD_VERSION,
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "kind": self.kind,
            "partial": self.partial,
            "models": list(self.models),
            "stats": [list(item) for item in self.stats],
            "sources": list(self.sources),
            "rows": self.rows,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryRecord":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or ""),
            created_at=str(data.get("created_at") or ""),
            models=[str(m) for m in data.get("models") or []],
            rows=list(data.get("rows") or []),
            stats=[list(item) for item in data.get("stats") or []],
            kind=str(data.get("kind") or "task"),
            partial=bool(data.get("partial")),
            sources=[str(s) for s in data.get("sources") or []],
        )


def _new_id(now: datetime) -> str:
    return now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def default_record_name(now: datetime, file_count: int, models: list[str]) -> str:
    arquivos = "arquivo" if file_count == 1 else "arquivos"
    modelos = ", ".join(models) if models else "sem modelo"
    return f"{now.strftime('%d/%m/%Y %H:%M')} · {file_count} {arquivos} · {modelos}"


def _job_models(jobs: list[AudioJob]) -> list[str]:
    """Modelos na mesma ordem das colunas do HTML (`write_html_report`)."""
    names: list[str] = []
    for job in jobs:
        for name in ([job.model_name] if job.model_name else []) + list(job.model_names):
            name = str(name or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def _original_size(job: AudioJob) -> int:
    try:
        return int(job.original_path.stat().st_size)
    except OSError:
        return 0


def record_from_jobs(
    jobs: list[AudioJob],
    stats: list[tuple[str, str]] | None = None,
    *,
    partial: bool = False,
    now: datetime | None = None,
) -> HistoryRecord:
    now = now or datetime.now()
    models = _job_models(jobs)
    rows = []
    for job in jobs:
        cells = {}
        for index, model in enumerate(models, start=1):
            # No cancelamento, TXT reutilizado pode pertencer a outro lote.
            transcript = (
                str(audio_job_attr(job, "transcription", index) or "")
                if partial else job_transcript_for_model(job, index)
            )
            problem = job_problem_reason_for_model(job, transcript, index)
            cells[model] = {"text": transcript if not problem else "", "problem": problem}
        rows.append({"file": job.original_name, "size": _original_size(job), "cells": cells})
    return HistoryRecord(
        id=_new_id(now),
        name=default_record_name(now, len(rows), models) + (" · parcial" if partial else ""),
        created_at=now.isoformat(timespec="seconds"),
        models=models,
        rows=rows,
        stats=[[str(a), str(b)] for a, b in (stats or [])],
        partial=partial,
    )


def _record_path(record_id: str, directory: Path | None = None) -> Path:
    safe = "".join(ch for ch in record_id if ch.isalnum() or ch in "-_")
    if not safe:
        raise ValueError("id de registro inválido")
    return (directory or history_dir()) / f"{safe}.json"


def save_record(record: HistoryRecord, directory: Path | None = None) -> Path:
    """Grava atomicamente (tmp + replace) para nunca deixar JSON pela metade."""
    path = _record_path(record.id, directory)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_record(record_id: str, directory: Path | None = None) -> HistoryRecord:
    path = _record_path(record_id, directory)
    return HistoryRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_records(directory: Path | None = None) -> list[HistoryRecord]:
    """Todos os registros válidos, do mais recente para o mais antigo."""
    records = []
    for path in (directory or history_dir()).glob("*.json"):
        try:
            records.append(HistoryRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, KeyError, TypeError):
            continue  # arquivo corrompido não derruba a lista
    records.sort(key=lambda r: (r.created_at, r.id), reverse=True)
    return records


def rename_record(record_id: str, name: str, directory: Path | None = None) -> HistoryRecord:
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("O nome não pode ficar vazio.")
    record = load_record(record_id, directory)
    record.name = name
    save_record(record, directory)
    return record


def delete_record(
    record_id: str, directory: Path | None = None, *, preview_directory: Path | None = None
) -> None:
    path = _record_path(record_id, directory)
    caches = [path.parent / "visualizar"]  # compatibilidade com o protótipo
    if preview_directory is not None:
        caches.append(preview_directory)
    for cache in caches:
        if cache.exists() and not _is_reparse(cache) and not _is_reparse(cache.parent):
            (cache / f"{path.stem}.html").unlink(missing_ok=True)
    path.unlink(missing_ok=True)


def _unique_column(name: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    counter = 2
    while f"{name} ({counter})" in taken:
        counter += 1
    return f"{name} ({counter})"


def merge_records(
    records: list[HistoryRecord], *, name: str = "", now: datetime | None = None
) -> HistoryRecord:
    """Une as tabelas pelo NOME DO ARQUIVO.

    - colunas = modelos de todos os registros, na ordem (o registro mais antigo
      primeiro); o mesmo modelo repetido em registros diferentes ganha sufixo
      " (2)" para nenhuma transcrição sobrescrever outra;
    - linhas = união dos arquivos, na ordem da primeira aparição;
    - arquivo ausente num registro fica com a célula vazia.
    """
    if len(records) < 2:
        raise ValueError("Selecione pelo menos dois registros para juntar.")
    now = now or datetime.now()
    ordered = sorted(records, key=lambda r: (r.created_at, r.id))
    for record in ordered:
        seen: set[str] = set()
        for row in record.rows:
            filename = str(row.get("file") or "")
            if filename in seen:
                raise ValueError(
                    f'O registro "{record.name}" contém arquivos homônimos: {filename}. '
                    "A junção por nome seria ambígua; os registros originais foram preservados."
                )
            seen.add(filename)
    columns: list[str] = []
    column_map: list[dict[str, str]] = []  # por registro: modelo -> coluna final
    for record in ordered:
        mapping = {}
        taken = set(columns)
        for model in record.models:
            column = _unique_column(model, taken)
            taken.add(column)
            columns.append(column)
            mapping[model] = column
        column_map.append(mapping)

    rows: dict[str, dict] = {}
    for record, mapping in zip(ordered, column_map):
        for row in record.rows:
            file_name = str(row.get("file") or "")
            target = rows.setdefault(file_name, {"file": file_name, "size": row.get("size", 0), "cells": {}})
            if not target.get("size"):
                target["size"] = row.get("size", 0)
            for model, cell in (row.get("cells") or {}).items():
                column = mapping.get(model)
                if column:
                    target["cells"][column] = dict(cell)
    for row in rows.values():
        for column in columns:
            row["cells"].setdefault(column, {"text": "", "problem": ""})

    total = len(rows)
    record = HistoryRecord(
        id=_new_id(now),
        name=name or f"Junção · {total} {'arquivo' if total == 1 else 'arquivos'} · {', '.join(columns)}",
        created_at=now.isoformat(timespec="seconds"),
        models=columns,
        rows=list(rows.values()),
        stats=[["Registros unidos", str(len(ordered))], ["Arquivos", str(total)]],
        kind="merged",
        sources=[r.id for r in ordered],
    )
    return record


def cell_display(cell: dict | None) -> str:
    cell = cell or {}
    if cell.get("problem"):
        return f"Falhou: {cell['problem']}"
    return str(cell.get("text") or "")


def export_html(record: HistoryRecord, path: Path) -> Path:
    headers = ("Arquivo original", *record.models)
    rows = []
    for row in record.rows:
        cells = [f"<td>{html.escape(str(row.get('file') or ''))}</td>"]
        for model in record.models:
            cell = (row.get("cells") or {}).get(model) or {}
            if cell.get("problem"):
                cells.append("<td><em>Falhou</em></td>")
            else:
                cells.append(f"<td>{html.escape(str(cell.get('text') or ''))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    stats = [(str(a), str(b)) for a, b in record.stats] or None
    path.write_text(html_document(record.name, rows, headers, stats), encoding="utf-8")
    return path


def _csv_text(value: str) -> str:
    text = str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def export_csv(record: HistoryRecord, path: Path) -> Path:
    """CSV com BOM e `;` para abrir direto no Excel em pt-BR."""
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Arquivo original", *[_csv_text(model) for model in record.models]])
        for row in record.rows:
            writer.writerow(
                [_csv_text(row.get("file") or "")]
                + [_csv_text(cell_display((row.get("cells") or {}).get(model))) for model in record.models]
            )
    return path


def safe_filename(name: str, fallback: str = "transcricoes") -> str:
    cleaned = "".join("_" if ch in '<>:"/\\|?*' or ord(ch) < 32 else ch for ch in name).strip(" .")
    return cleaned[:120] or fallback


def _is_reparse(path: Path) -> bool:
    """No Windows, junction não é symlink no Python 3.11: usar atributos lstat."""
    try:
        metadata = path.lstat()
        return stat.S_ISLNK(metadata.st_mode) or bool(
            getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        )
    except OSError:
        return True  # falha de inspeção nunca autoriza atravessar/apagar


def _plain_walk(path: Path):
    """Percorre apenas diretórios reais dentro da raiz, sem links/junctions."""
    if not path.exists():
        return
    if _is_reparse(path):
        raise ValueError("A pasta de temporários é um link/junction; a operação foi bloqueada.")
    base = path.resolve()
    for root, dirs, files in os.walk(path, topdown=True, followlinks=False):
        current = Path(root)
        if _is_reparse(current) or not current.resolve().is_relative_to(base):
            dirs.clear()
            continue
        dirs[:] = [name for name in dirs if not _is_reparse(current / name)]
        yield current, files


def directory_usage(path: Path) -> tuple[int, int]:
    """(bytes, arquivos) reais da pasta; links e junctions não entram na conta."""
    total = count = 0
    for root, files in _plain_walk(path):
        for name in files:
            file_path = root / name
            if _is_reparse(file_path):
                continue
            try:
                total += file_path.stat().st_size
                count += 1
            except OSError:
                pass
    return total, count


def clear_directory(path: Path, keep: set[Path] | None = None) -> tuple[int, int, int]:
    """Apaga só o CONTEÚDO real da pasta. A raiz, links e junctions ficam.

    Retorna (bytes liberados, arquivos apagados, falhas). Arquivos em uso ou
    listados em `keep` ficam; pastas reais vazias são removidas.
    """
    keep_resolved = {Path(p).resolve() for p in (keep or set())}
    freed = removed = failed = 0
    directories = []
    base = path.resolve()
    for root, files in _plain_walk(path):
        directories.append(root)
        for name in files:
            file_path = root / name
            if _is_reparse(file_path) or not file_path.resolve().is_relative_to(base):
                continue
            if file_path.resolve() in keep_resolved:
                continue
            try:
                size = file_path.stat().st_size
                file_path.unlink()
                freed += size
                removed += 1
            except OSError:
                failed += 1
    for directory in reversed(directories):
        if directory != path and not _is_reparse(directory):
            try:
                directory.rmdir()
            except OSError:
                pass
    return freed, removed, failed


__all__ = [
    "HistoryRecord",
    "cell_display",
    "clear_directory",
    "default_record_name",
    "delete_record",
    "directory_usage",
    "export_csv",
    "export_html",
    "history_dir",
    "list_records",
    "load_record",
    "merge_records",
    "record_from_jobs",
    "rename_record",
    "safe_filename",
    "save_record",
]
