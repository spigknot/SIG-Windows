"""Persistência local dos valores compartilhados da aba Diárias."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from app_env import settings_path


def _holerite_data_path() -> Path:
    """Arquivo de dados fica na pasta de usuário do SIG, fora do projeto."""
    return settings_path().parent / "diarias_holerite.json"


def _holerite_pdf_dir() -> Path:
    return settings_path().parent / "diarias_holerites"


def _read_holerite_data() -> dict:
    try:
        data = json.loads(_holerite_data_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_holerite_data(data: dict) -> None:
    path = _holerite_data_path()
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_holerite() -> tuple[str, str]:
    """Devolve `(total_vencimentos, mes)` ou strings vazias se não houver dados."""
    data = _read_holerite_data()
    total = data.get("total_vencimentos")
    mes = data.get("mes")
    return (
        total if isinstance(total, str) else "",
        mes if isinstance(mes, str) else "",
    )


def load_ufesp() -> str:
    """Devolve o último valor UFESP salvo, ou uma string vazia."""
    value = _read_holerite_data().get("ufesp")
    return value if isinstance(value, str) else ""


def save_ufesp(value: str) -> None:
    """Persiste UFESP sem alterar os dados ou o anexo do holerite."""
    data = _read_holerite_data()
    data["ufesp"] = str(value or "")
    _write_holerite_data(data)


def load_holerite_pdf() -> tuple[str, str]:
    """Devolve o caminho e nome do holerite ativo, se a cópia ainda existir."""
    data = _read_holerite_data()
    stored_name = data.get("pdf_filename")
    if not isinstance(stored_name, str) or Path(stored_name).name != stored_name:
        return "", ""
    path = _holerite_pdf_dir() / stored_name
    if not path.is_file():
        return "", ""
    display_name = data.get("pdf_display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = path.name
    return str(path), display_name


def save_holerite(total_vencimentos: str, mes: str) -> None:
    """Salva os valores sem alterar os metadados do PDF anexado."""
    data = _read_holerite_data()
    data["total_vencimentos"] = str(total_vencimentos or "")
    data["mes"] = str(mes or "")
    _write_holerite_data(data)


def attach_holerite_pdf(
    source_path: str | Path, total_vencimentos: str, mes: str
) -> tuple[str, str]:
    """Copia o holerite para o perfil do SIG e o define como anexo ativo."""
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(source)

    directory = _holerite_pdf_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"holerite_{uuid.uuid4().hex}.pdf"
    destination = directory / stored_name
    temporary = directory / f".{stored_name}.tmp"

    data = _read_holerite_data()
    old_name = data.get("pdf_filename")
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
        data["total_vencimentos"] = str(total_vencimentos or "")
        data["mes"] = str(mes or "")
        data["pdf_filename"] = stored_name
        data["pdf_display_name"] = source.name
        try:
            _write_holerite_data(data)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    finally:
        if temporary.exists():
            temporary.unlink()

    if (
        isinstance(old_name, str)
        and old_name != stored_name
        and Path(old_name).name == old_name
        and old_name.startswith("holerite_")
        and old_name.endswith(".pdf")
    ):
        try:
            (_holerite_pdf_dir() / old_name).unlink(missing_ok=True)
        except OSError:
            pass

    return str(destination), source.name
