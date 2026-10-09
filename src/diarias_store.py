"""Persistência local dos valores compartilhados e dos perfis da aba Diárias."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Mapping
from pathlib import Path

from app_env import settings_path
from diarias_profiles import validate_diarias_profile


def _diarias_profiles_path() -> Path:
    return settings_path().parent / "diarias_profiles.json"


def _read_diarias_profiles_data() -> dict:
    try:
        data = json.loads(_diarias_profiles_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"profiles": [], "active_profile_id": ""}
    if not isinstance(data, dict):
        return {"profiles": [], "active_profile_id": ""}

    profiles = []
    seen_ids = set()
    entries = data.get("profiles")
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        profile_id = entry.get("id")
        name = entry.get("profile_name")
        if not isinstance(profile_id, str) or not profile_id or profile_id in seen_ids:
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        try:
            values = validate_diarias_profile(entry)
        except ValueError:
            continue
        profiles.append({**values, "id": profile_id, "profile_name": name.strip()})
        seen_ids.add(profile_id)

    active_id = data.get("active_profile_id")
    if not isinstance(active_id, str) or active_id not in seen_ids:
        active_id = ""
    return {"profiles": profiles, "active_profile_id": active_id}


def _write_diarias_profiles_data(data: dict) -> None:
    path = _diarias_profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps({"version": 1, **data}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def list_diarias_profiles() -> list[dict[str, str]]:
    """Perfis válidos, na ordem em que foram criados."""
    return _read_diarias_profiles_data()["profiles"]


def load_active_diarias_profile_id() -> str:
    return _read_diarias_profiles_data()["active_profile_id"]


def load_diarias_profile(profile_id: str | None = None) -> dict[str, str] | None:
    """Carrega um perfil pelo id; omitindo o id, carrega o perfil ativo."""
    data = _read_diarias_profiles_data()
    if profile_id is None:
        profile_id = data["active_profile_id"]
    return next((profile for profile in data["profiles"] if profile["id"] == profile_id), None)


def save_diarias_profile(
    values: Mapping[str, object], profile_id: str | None = None
) -> dict[str, str]:
    """Cria ou edita um perfil válido e o seleciona para geração de documentos."""
    normalized = validate_diarias_profile(values)
    data = _read_diarias_profiles_data()
    profiles = data["profiles"]
    if profile_id is not None and not any(profile["id"] == profile_id for profile in profiles):
        raise ValueError("O perfil de Diárias selecionado não existe mais.")

    names = {
        profile["profile_name"].casefold()
        for profile in profiles
        if profile["id"] != profile_id
    }
    base_name = normalized["nome"]
    profile_name = base_name
    suffix = 2
    while profile_name.casefold() in names:
        profile_name = f"{base_name} {suffix}"
        suffix += 1

    saved = {
        **normalized,
        "id": profile_id if profile_id is not None else uuid.uuid4().hex,
        "profile_name": profile_name,
    }
    if profile_id is None:
        profiles.append(saved)
    else:
        profiles[:] = [saved if profile["id"] == profile_id else profile for profile in profiles]
    data["active_profile_id"] = saved["id"]
    _write_diarias_profiles_data(data)
    return saved


def select_diarias_profile(profile_id: str | None) -> None:
    """Persiste a seleção ativa; uma string vazia ou None limpa a seleção."""
    data = _read_diarias_profiles_data()
    if profile_id and not any(profile["id"] == profile_id for profile in data["profiles"]):
        raise ValueError("O perfil de Diárias selecionado não existe mais.")
    data["active_profile_id"] = profile_id or ""
    _write_diarias_profiles_data(data)


def delete_diarias_profile(profile_id: str) -> None:
    """Remove um perfil e mantém a seleção válida para os perfis restantes."""
    data = _read_diarias_profiles_data()
    remaining = [profile for profile in data["profiles"] if profile["id"] != profile_id]
    if len(remaining) == len(data["profiles"]):
        raise ValueError("O perfil de Diárias selecionado não existe mais.")
    data["profiles"] = remaining
    if data["active_profile_id"] == profile_id:
        data["active_profile_id"] = remaining[0]["id"] if remaining else ""
    _write_diarias_profiles_data(data)


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
    """Devolve o valor UFESP salvo, usando 38,42 antes da primeira gravação."""
    value = _read_holerite_data().get("ufesp")
    return value if isinstance(value, str) else "38,42"


def _output_preferences_path() -> Path:
    return settings_path().parent / "diarias_output.json"


def load_output_directory() -> Path:
    """A última pasta escolhida, ou a Desktop no primeiro uso."""
    try:
        data = json.loads(_output_preferences_path().read_text(encoding="utf-8"))
        value = data.get("directory") if isinstance(data, dict) else None
        path = Path(value) if isinstance(value, str) and value else None
        if path is not None and path.is_dir():
            return path
    except (OSError, ValueError):
        pass
    return Path.home() / "Desktop"


def save_output_directory(directory: str | Path) -> None:
    """Persiste a pasta compartilhada pelas ações Gerar docx/xlsx e Gerar PDFs."""
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError("A pasta de destino não existe.")
    path = _output_preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps({"directory": str(directory)}, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_ufesp_index() -> str:
    """Devolve o último índice UFESP salvo, ou uma string vazia."""
    value = _read_holerite_data().get("ufesp_index")
    return value if isinstance(value, str) else ""


def save_ufesp(value: str) -> None:
    """Persiste UFESP sem alterar os dados ou o anexo do holerite."""
    data = _read_holerite_data()
    data["ufesp"] = str(value or "")
    _write_holerite_data(data)


def save_ufesp_index(value: str) -> None:
    """Persiste o índice UFESP sem alterar os demais dados de Diárias."""
    data = _read_holerite_data()
    data["ufesp_index"] = str(value or "")
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
