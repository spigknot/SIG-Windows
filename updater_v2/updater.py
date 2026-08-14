"""Transactional updater for the SIG Windows onedir app.

The helper keeps the legacy command-line contract, but validates and stages
every update before touching the installation.  It also keeps a transaction
journal so an interrupted replacement can be rolled back safely on the next
run.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
from contextlib import contextmanager
import hashlib
import html
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath


VERSION_RE = re.compile(r"^\d{8}_\d{3}$")
UPDATE_MANIFEST_FILE_ID = "1Gompo26SsyhSdliBGNaedLhEfidB244E"
UPDATE_DOWNLOAD_URL = "https://drive.usercontent.google.com/download"
UPDATE_PUBLIC_KEY_E = 65537
UPDATE_PUBLIC_KEY_N = 4776833754672109710666015745718377295826954378034957006723781632230794955188598743370375368759247701138572196632244506341860738985196771222328276471293164426045586502411553661270415658303449836000240060850077943629529298365455842583839584430835872888082421190431050761740593243172708805858229100494995424042846759167936558524923889093025581721886390801543158714477942628958659907698645218405072643039190789807520623959789948760663039915934233343926084287154817842449929074144135976678727267978353880303189583548982201552861178437687569977746462198133228741460769839629249527122404198789341588724117695515639417887297249072695071299249800470626986276226209694407865386128033982643621030612265330884993509358887003353611841249193688390145075540912405754224137641702769971761374974256331506313629217304424829655209764530396523158905317988087656296751937468490602949770457129034644632659661248617309294539893653236376299080388523
FULL_RELEASE_API_URL = "https://api.github.com/repos/spigknot/SIG-Windows/releases/latest"
HTTP_USER_AGENT = "SigUpdater/2.0 (+https://github.com/spigknot/SIG-Windows)"
MAX_MANIFEST_BYTES = 128 * 1024
MAX_ZIP_ENTRIES = 10_000
MAX_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
MAX_MEMBER_UNCOMPRESSED_BYTES = 1 * 1024 * 1024 * 1024
REQUIRED_CORE_FILES = (
    "sig.exe",
    "_internal/base_library.zip",
    "_internal/python311.dll",
    "_internal/vcruntime140.dll",
    "_internal/vcruntime140_1.dll",
    "_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll",
)
REQUIRED_RUNTIME_FILES = (
    "ffmpeg.exe",
    "ffplay.exe",
    "vad_worker.py",
)
REQUIRED_UPDATE_FILES = REQUIRED_CORE_FILES + ("SigUpdater.exe",)
REQUIRED_DIRECTORIES = ("_internal", "vad_deps")
INCREMENTAL_FORBIDDEN_TOP_LEVEL = {
    "ffmpeg.exe",
    "ffplay.exe",
    "vad_worker.py",
    "vad_deps",
}
MUTABLE_TOP_LEVEL_NAMES = {"temp", "cache", "logs"}
ALLOWED_TOP_LEVEL_NAMES = {
    "sig.exe",
    "_internal",
    "SigUpdater.exe",
    "ffmpeg.exe",
    "ffplay.exe",
    "vad_worker.py",
    "vad_deps",
    "prompts",
    "modelos",
    "build-info.json",
    "updater.log",
    # These directories are created by the running application and are not
    # part of an update package.
    "temp",
    "cache",
    "logs",
}
REQUIRED_FILES = REQUIRED_UPDATE_FILES + REQUIRED_RUNTIME_FILES
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class UpdateError(RuntimeError):
    pass


def canonical_update_manifest(manifest: dict) -> bytes:
    signed_payload = {
        "schema": int(manifest.get("schema") or 0),
        "version": str(manifest.get("version") or ""),
        "zip_file_id": str(manifest.get("zip_file_id") or ""),
        "zip_name": str(manifest.get("zip_name") or ""),
        "sha256": str(manifest.get("sha256") or "").lower(),
        "size": int(manifest.get("size") or 0),
        "created_at": str(manifest.get("created_at") or ""),
    }
    return json.dumps(
        signed_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_update_manifest_signature(manifest: dict) -> bool:
    try:
        signature = base64.b64decode(str(manifest.get("signature") or ""), validate=True)
        key_size = (UPDATE_PUBLIC_KEY_N.bit_length() + 7) // 8
        if len(signature) != key_size:
            return False
        encoded = pow(int.from_bytes(signature, "big"), UPDATE_PUBLIC_KEY_E, UPDATE_PUBLIC_KEY_N)
        encoded_bytes = encoded.to_bytes(key_size, "big")
        digest_info = (
            bytes.fromhex("3031300d060960864801650304020105000420")
            + hashlib.sha256(canonical_update_manifest(manifest)).digest()
        )
        padding_size = key_size - len(digest_info) - 3
        if padding_size < 8:
            return False
        expected = b"\x00\x01" + (b"\xff" * padding_size) + b"\x00" + digest_info
        return encoded_bytes == expected
    except (TypeError, ValueError):
        return False


def _validate_incremental_manifest(manifest: dict) -> dict:
    if not isinstance(manifest, dict) or not verify_update_manifest_signature(manifest):
        raise UpdateError("o manifesto incremental não possui uma assinatura digital válida")
    version = str(manifest.get("version") or "")
    zip_name = str(manifest.get("zip_name") or "")
    file_id = str(manifest.get("zip_file_id") or "")
    digest = str(manifest.get("sha256") or "").lower()
    size = int(manifest.get("size") or 0)
    if not VERSION_RE.fullmatch(version):
        raise UpdateError("o manifesto incremental contém uma versão inválida")
    if not file_id or zip_name != f"{version}.zip":
        raise UpdateError("o manifesto incremental é inconsistente")
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or not 0 < size <= MAX_UNCOMPRESSED_BYTES:
        raise UpdateError("o manifesto incremental contém hash ou tamanho inválido")
    return dict(manifest)


def _google_drive_download_url(file_id: str) -> str:
    query = urllib.parse.urlencode({"id": file_id, "export": "download", "confirm": "t"})
    return f"{UPDATE_DOWNLOAD_URL}?{query}"


def _urlopen(request: urllib.request.Request, timeout: int = 60):
    return urllib.request.urlopen(request, timeout=timeout)


def _open_google_drive_download(file_id: str):
    request = urllib.request.Request(
        _google_drive_download_url(file_id),
        headers={"User-Agent": HTTP_USER_AGENT},
    )
    response = _urlopen(request)
    content_type = str(response.headers.get("Content-Type") or "").lower()
    if "text/html" not in content_type:
        return response
    page = response.read(1024 * 1024).decode("utf-8", errors="replace")
    response.close()
    form_match = re.search(r'<form[^>]+action="([^"]+)"[^>]*>', page, re.IGNORECASE)
    if not form_match:
        raise UpdateError("o Google Drive não forneceu o link de download")
    action = html.unescape(form_match.group(1))
    fields = {
        html.unescape(name): html.unescape(value)
        for name, value in re.findall(
            r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"',
            page,
            flags=re.IGNORECASE,
        )
    }
    separator = "&" if "?" in action else "?"
    confirmation = urllib.request.Request(
        f"{action}{separator}{urllib.parse.urlencode(fields)}",
        headers={"User-Agent": HTTP_USER_AGENT},
    )
    return _urlopen(confirmation)


def fetch_incremental_manifest() -> dict:
    with _open_google_drive_download(UPDATE_MANIFEST_FILE_ID) as response:
        payload = response.read(MAX_MANIFEST_BYTES + 1)
    if len(payload) > MAX_MANIFEST_BYTES:
        raise UpdateError("o manifesto incremental excede o tamanho permitido")
    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("o manifesto incremental não contém JSON válido") from exc
    return _validate_incremental_manifest(manifest)


def select_full_release_asset(release: dict) -> dict:
    version = str(release.get("tag_name") or release.get("tagName") or "")
    if not VERSION_RE.fullmatch(version):
        raise UpdateError("a release completa possui uma versão inválida")
    candidates = [
        asset for asset in release.get("assets", [])
        if isinstance(asset, dict)
        and str(asset.get("name") or "").lower().endswith(".zip")
        and int(asset.get("size") or 0) > 0
    ]
    if not candidates:
        raise UpdateError("a release mais recente não possui um pacote ZIP completo")
    candidates.sort(
        key=lambda asset: (
            "full" in str(asset.get("name") or "").casefold(),
            int(asset.get("size") or 0),
        ),
        reverse=True,
    )
    asset = candidates[0]
    digest_field = str(asset.get("digest") or "").lower()
    digest = digest_field.removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise UpdateError("o GitHub não forneceu o SHA-256 do pacote completo")
    url = str(asset.get("browser_download_url") or asset.get("url") or "")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "objects.githubusercontent.com"}:
        raise UpdateError("a release completa contém uma URL de download não confiável")
    return {
        "kind": "full",
        "version": version,
        "zip_name": str(asset["name"]),
        "url": url,
        "sha256": digest,
        "size": int(asset["size"]),
    }


def fetch_full_release() -> dict:
    request = urllib.request.Request(
        FULL_RELEASE_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": HTTP_USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with _urlopen(request) as response:
        payload = response.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024:
        raise UpdateError("a resposta da release completa excedeu o tamanho permitido")
    try:
        return select_full_release_asset(json.loads(payload.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("o GitHub não retornou uma release válida") from exc


def _download_to_file(
    descriptor: dict,
    destination: Path,
    progress_callback=None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    partial.unlink(missing_ok=True)
    digest = hashlib.sha256()
    downloaded = 0
    expected_size = int(descriptor["size"])
    if descriptor.get("zip_file_id"):
        response_context = _open_google_drive_download(str(descriptor["zip_file_id"]))
    else:
        request = urllib.request.Request(
            str(descriptor["url"]),
            headers={"User-Agent": HTTP_USER_AGENT},
        )
        response_context = _urlopen(request)
    try:
        with response_context as response, partial.open("wb") as output:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > expected_size:
                    raise UpdateError("o pacote recebido é maior que o tamanho declarado")
                output.write(chunk)
                digest.update(chunk)
                if progress_callback:
                    progress_callback(downloaded, expected_size)
        if downloaded != expected_size:
            raise UpdateError(
                f"o pacote recebido possui {downloaded} bytes; eram esperados {expected_size}"
            )
        if digest.hexdigest().lower() != str(descriptor["sha256"]).lower():
            raise UpdateError("o SHA-256 do pacote recebido não confere")
        os.replace(partial, destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def _normalized_member_name(name: str) -> str:
    raw = name.replace("\\", "/")
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise UpdateError(f"entrada absoluta ou vazia no ZIP: {name!r}")
    path = PurePosixPath(raw)
    if any(part in ("", ".", "..") for part in path.parts):
        raise UpdateError(f"caminho inseguro no ZIP: {name!r}")
    for part in path.parts:
        if "\x00" in part or ":" in part or part.endswith((" ", ".")):
            raise UpdateError(f"nome incompatível com Windows no ZIP: {name!r}")
        if part.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
            raise UpdateError(f"nome reservado do Windows no ZIP: {name!r}")
        if len(part) > 240:
            raise UpdateError(f"componente de caminho longo demais no ZIP: {name!r}")
        lowered = part.casefold()
        if lowered == "g":
            raise UpdateError("o pacote contém a pasta proibida g")
        if lowered.startswith("_mei"):
            raise UpdateError("o pacote contém artefato _MEI de one-file")
        if lowered == "dist":
            raise UpdateError("o pacote contém o diretório dist; o layout deve estar na raiz")
    return "/".join(path.parts)


def _is_symlink(member: zipfile.ZipInfo) -> bool:
    mode = (member.external_attr >> 16) & 0o170000
    return mode == 0o120000


def _validate_entry_topology(entries: dict[str, bool]) -> None:
    for name, is_directory in entries.items():
        parts = PurePosixPath(name).parts
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index])
            if parent in entries and not entries[parent]:
                raise UpdateError(f"arquivo usado como diretório no ZIP: {parent}")
        if not is_directory and name.endswith("/"):
            raise UpdateError(f"entrada contraditória no ZIP: {name}")


def _validate_required_names(
    file_names: set[str], all_names: set[str], *, full: bool
) -> None:
    required_files = REQUIRED_UPDATE_FILES + (REQUIRED_RUNTIME_FILES if full else ())
    for relative in required_files:
        if relative not in file_names:
            if "portaudio" in relative.casefold():
                raise UpdateError("DLL do PortAudio ausente no pacote")
            raise UpdateError(f"componente obrigatório ausente no pacote: {relative}")
    required_directories = REQUIRED_DIRECTORIES if full else ("_internal",)
    for relative in required_directories:
        if not any(name == relative or name.startswith(relative + "/") for name in all_names):
            raise UpdateError(f"diretório obrigatório ausente no pacote: {relative}")


def _validate_top_level_names(file_names: set[str], all_names: set[str], *, full: bool) -> None:
    top_level = {PurePosixPath(name).parts[0] for name in all_names if name}
    unknown = sorted(top_level - ALLOWED_TOP_LEVEL_NAMES)
    if unknown:
        raise UpdateError("componente desconhecido na raiz do pacote: " + ", ".join(unknown))
    if not full:
        forbidden = sorted(top_level & INCREMENTAL_FORBIDDEN_TOP_LEVEL)
        if forbidden:
            raise UpdateError(
                "pacote incremental não pode substituir recursos de runtime: "
                + ", ".join(forbidden)
            )


def _validate_file_sizes(root: Path, *, full: bool) -> None:
    required = REQUIRED_UPDATE_FILES + (REQUIRED_RUNTIME_FILES if full else ())
    for relative in required:
        path = root / Path(*PurePosixPath(relative).parts)
        if not path.is_file():
            continue
        if path.stat().st_size <= 0:
            raise UpdateError(f"arquivo obrigatório vazio: {relative}")


def validate_zip(zip_path: Path, *, full: bool | None = None) -> bool:
    if not zip_path.is_file():
        raise UpdateError(f"ZIP não encontrado: {zip_path}")
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise UpdateError(f"entrada corrompida no ZIP: {corrupt_member}")
            members = archive.infolist()
            if len(members) > MAX_ZIP_ENTRIES:
                raise UpdateError("o pacote excede o limite de entradas")
            entries: dict[str, bool] = {}
            total_size = 0
            for member in members:
                if member.flag_bits & 0x1:
                    raise UpdateError("ZIP criptografado não é permitido")
                if _is_symlink(member):
                    raise UpdateError(f"link simbólico não permitido: {member.filename}")
                normalized = _normalized_member_name(member.filename.rstrip("/"))
                is_directory = member.is_dir()
                if normalized in entries:
                    raise UpdateError(f"entrada duplicada no ZIP: {normalized}")
                entries[normalized] = is_directory
                total_size += member.file_size
                if member.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                    raise UpdateError(f"entrada individual grande demais: {member.filename}")
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    raise UpdateError("o pacote descompactado excede o limite permitido")
            _validate_entry_topology(entries)
            file_names = {name for name, is_directory in entries.items() if not is_directory}
            all_runtime_present = set(REQUIRED_RUNTIME_FILES) <= file_names
            if full is None:
                full = all_runtime_present
            elif full and not all_runtime_present:
                raise UpdateError("pacote completo não contém todos os recursos de runtime")
            _validate_top_level_names(file_names, set(entries), full=full)
            _validate_required_names(file_names, set(entries), full=full)
            build_info = "build-info.json"
            if build_info in file_names:
                try:
                    with archive.open(build_info) as handle:
                        metadata = json.loads(handle.read().decode("utf-8"))
                    version = str(metadata.get("version") or "")
                    if not VERSION_RE.fullmatch(version):
                        raise UpdateError("build-info.json contém uma versão inválida")
                except UpdateError:
                    raise
                except Exception as exc:
                    raise UpdateError(f"build-info.json inválido: {exc}") from exc
            return bool(full)
    except zipfile.BadZipFile as exc:
        raise UpdateError(f"ZIP inválido: {zip_path}") from exc


def _reject_bad_tree_entries(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise UpdateError(f"link simbólico não permitido na instalação: {path}")
        relative = path.relative_to(root)
        for part in relative.parts:
            lowered = part.casefold()
            if lowered == "g":
                raise UpdateError(f"a instalação contém a pasta proibida g: {path}")
            if lowered.startswith("_mei"):
                raise UpdateError(f"a instalação contém artefato _MEI: {path}")


def validate_install_tree(root: Path, *, full: bool = True) -> None:
    if not root.is_dir():
        raise UpdateError(f"diretório da instalação não encontrado: {root}")
    _reject_bad_tree_entries(root)
    files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    names = {path.relative_to(root).as_posix() for path in root.rglob("*")}
    _validate_required_names(files, names, full=full)
    _validate_file_sizes(root, full=full)


def validate_target_shell(root: Path) -> None:
    """Validate enough of an existing install to repair a partial update."""
    if not root.is_dir():
        raise UpdateError(f"diretório da instalação não encontrado: {root}")
    _reject_bad_tree_entries(root)
    required = {"sig.exe", "_internal", "SigUpdater.exe", "ffmpeg.exe", "ffplay.exe", "vad_deps"}
    present = {path.name for path in root.iterdir()}
    missing = sorted(required - present)
    if missing:
        raise UpdateError("instalação não reconhecida; componentes ausentes: " + ", ".join(missing))


def validate_full_install_destination(root: Path) -> None:
    """Allow a full package to install into an empty or recognizable SIG folder."""
    root.mkdir(parents=True, exist_ok=True)
    _reject_bad_tree_entries(root)
    present = {path.name for path in root.iterdir()}
    recognizable_install = present & {
        "sig.exe", "_internal", "ffmpeg.exe", "ffplay.exe", "vad_deps", "vad_worker.py"
    }
    if recognizable_install:
        # A repair must tolerate logs, shortcuts and user files left beside a
        # damaged installation. The transaction only replaces names that are
        # present in the validated package and leaves everything else intact.
        return
    unknown = sorted(
        name
        for name in present
        if name not in ALLOWED_TOP_LEVEL_NAMES
        and not name.startswith("updater")
        and name != ".sig-update.lock"
    )
    if unknown:
        raise UpdateError(
            "a pasta escolhida não está vazia e não parece ser uma instalação do SIG; "
            "itens desconhecidos: " + ", ".join(unknown[:8])
        )


def _extract_zip(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            normalized = _normalized_member_name(member.filename.rstrip("/"))
            target = (destination / Path(*PurePosixPath(normalized).parts)).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise UpdateError(f"destino inseguro no ZIP: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 256)


def _write_journal(path: Path, data: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _read_journal(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise UpdateError(f"diário de atualização inválido: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("names"), list):
        raise UpdateError(f"diário de atualização incompleto: {path}")
    return data


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=False)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _atomic_move(source: Path, destination: Path) -> None:
    if not _path_exists(source):
        raise UpdateError(f"origem ausente durante a troca: {source}")
    if _path_exists(destination):
        raise UpdateError(f"destino já existe durante a troca: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def _rollback_transaction(transaction: Path, target: Path, log_path: Path) -> None:
    journal_path = transaction / "journal.json"
    if not journal_path.is_file():
        shutil.rmtree(transaction, ignore_errors=True)
        return
    journal = _read_journal(journal_path)
    if os.path.normcase(os.path.abspath(str(journal.get("target") or ""))) != os.path.normcase(os.path.abspath(str(target))):
        raise UpdateError(f"diário aponta para outra instalação: {transaction}")
    backup = transaction / "backup"
    names = {str(name) for name in journal.get("names", []) if isinstance(name, str)}
    if backup.is_dir():
        names.update(path.name for path in backup.iterdir())
    _log(log_path, f"Recuperando transação interrompida: {transaction.name}.")
    for name in sorted(names, key=str.casefold, reverse=True):
        destination = target / name
        old = backup / name
        if _path_exists(old):
            if _path_exists(destination):
                _remove_path(destination)
            _atomic_move(old, destination)
        elif not journal.get("target_existed", {}).get(name, True) and _path_exists(destination):
            _remove_path(destination)
    try:
        validate_install_tree(target, full=True)
        _log(log_path, "Recuperação da instalação anterior concluída.")
    except UpdateError as exc:
        # A previous installation may already have been damaged before this
        # updater started. Preserve it exactly instead of hiding the original
        # failure behind a second rollback error.
        try:
            validate_target_shell(target)
            _log(log_path, f"Versão anterior restaurada, mas já estava incompleta: {exc}")
        except UpdateError:
            if not journal.get("allow_incomplete_target"):
                raise
            validate_full_install_destination(target)
            _log(log_path, "Estado anterior da pasta de instalação foi restaurado.")
    shutil.rmtree(transaction, ignore_errors=True)


def _recover_interrupted_transactions(target: Path, log_path: Path) -> None:
    parent = target.parent
    for transaction in sorted(parent.glob(".sig-updater-v2-*"), key=lambda item: item.name):
        if not transaction.is_dir():
            continue
        journal = transaction / "journal.json"
        if not journal.is_file():
            shutil.rmtree(transaction, ignore_errors=True)
            continue
        journal_path = transaction / "journal.json"
        journal = _read_journal(journal_path)
        if journal.get("phase") == "validated":
            try:
                validate_install_tree(target, full=True)
                _log(log_path, f"Removendo transação já validada: {transaction.name}.")
                shutil.rmtree(transaction, ignore_errors=True)
            except UpdateError:
                _rollback_transaction(transaction, target, log_path)
        else:
            _rollback_transaction(transaction, target, log_path)


@contextmanager
def _installation_lock(target: Path, log_path: Path):
    lock_path = target.parent / f".{target.name}.sig-update.lock"
    handle = lock_path.open("a+b")
    handle.seek(0)
    handle.write(b"0")
    handle.flush()
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError) as exc:
        handle.close()
        raise UpdateError("já existe outra atualização do SIG em andamento") from exc
    try:
        _log(log_path, "Lock exclusivo da instalação adquirido.")
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _process_image_paths() -> dict[int, str]:
    if os.name != "nt":
        return {}
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong),
            ("cntUsage", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", ctypes.c_ulong),
            ("cntThreads", ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_ulong),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32FirstW.restype = ctypes.c_int
    kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32NextW.restype = ctypes.c_int
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot in (0, ctypes.c_void_p(-1).value):
        return {}
    result: dict[int, str] = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        first = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while first:
            pid = int(entry.th32ProcessID)
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                try:
                    size = ctypes.c_ulong(32768)
                    buffer = ctypes.create_unicode_buffer(size.value)
                    if kernel32.QueryFullProcessImageNameW(
                        handle, 0, buffer, ctypes.byref(size)
                    ):
                        result[pid] = buffer.value
                finally:
                    kernel32.CloseHandle(handle)
            first = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return result


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
        os.path.abspath(str(right))
    )


def _wait_for_processes(pid: int, target_exe: Path, timeout: int, log_path: Path) -> None:
    deadline = time.monotonic() + timeout
    while True:
        blockers = []
        if _process_alive(pid):
            blockers.append(f"pid={pid}")
        for process_id, image_path in _process_image_paths().items():
            if process_id != os.getpid() and _same_path(image_path, target_exe):
                blockers.append(f"sig.exe pid={process_id}")
        if not blockers:
            _log(log_path, "Todos os processos do SIG encerrados.")
            return
        if time.monotonic() >= deadline:
            raise UpdateError(
                "tempo esgotado aguardando o SIG fechar: " + ", ".join(blockers)
            )
        time.sleep(0.25)


def _stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _launch_and_verify(target_exe: Path, timeout: int, log_path: Path) -> subprocess.Popen[bytes]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(
            [str(target_exe)],
            cwd=str(target_exe.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception as exc:
        raise UpdateError(f"não foi possível iniciar o SIG atualizado: {exc}") from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise UpdateError(
                f"o SIG atualizado encerrou durante a inicialização (código {process.returncode})"
            )
        time.sleep(0.25)
    if process.poll() is not None:
        raise UpdateError("o SIG atualizado não permaneceu em execução")
    _log(log_path, f"SIG atualizado confirmado em execução (PID {process.pid}).")
    return process


def _apply_transaction(
    staged: Path,
    target: Path,
    transaction: Path,
    startup_timeout: int,
    log_path: Path,
    *,
    allow_incomplete_target: bool = False,
) -> None:
    backup = transaction / "backup"
    backup.mkdir()
    started_process: subprocess.Popen[bytes] | None = None
    # An incremental package replaces only the top-level names it contains;
    # runtime assets omitted from it must remain untouched.
    names = sorted({item.name for item in staged.iterdir()}, key=str.casefold)
    target_existed = {name: _path_exists(target / name) for name in names}
    journal = {
        "schema": 1,
        "target": str(target),
        "phase": "prepared",
        "names": names,
        "target_existed": target_existed,
        "allow_incomplete_target": allow_incomplete_target,
    }
    _write_journal(transaction / "journal.json", journal)
    try:
        for name in names:
            destination = target / name
            if _path_exists(destination):
                _atomic_move(destination, backup / name)
        journal["phase"] = "old-moved"
        _write_journal(transaction / "journal.json", journal)
        for name in sorted((item.name for item in staged.iterdir()), key=str.casefold):
            _atomic_move(staged / name, target / name)
        journal["phase"] = "new-moved"
        _write_journal(transaction / "journal.json", journal)
        validate_install_tree(target)
        _log(log_path, "Estrutura onedir instalada; validando inicialização.")
        started_process = _launch_and_verify(target / "sig.exe", startup_timeout, log_path)
        journal["phase"] = "validated"
        _write_journal(transaction / "journal.json", journal)
        _log(log_path, "Atualização aplicada e validada.")
        shutil.rmtree(transaction, ignore_errors=True)
    except Exception:
        _stop_process(started_process)
        _log(log_path, "Falha na aplicação; iniciando rollback.")
        _rollback_transaction(transaction, target, log_path)
        _log(log_path, "Rollback concluído; a versão anterior foi restaurada.")
        if (target / "sig.exe").is_file():
            try:
                _launch_and_verify(target / "sig.exe", min(startup_timeout, 5), log_path)
            except Exception as restart_error:
                _log(log_path, f"Não foi possível reiniciar a versão anterior: {restart_error}")
        raise


def execute(
    zip_path: Path,
    target: Path,
    pid: int,
    log_path: Path,
    wait_timeout: int = 120,
    startup_timeout: int = 12,
    updater_override: Path | None = None,
) -> None:
    zip_path = zip_path.resolve()
    target = target.resolve()
    log_path = log_path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    _log(log_path, "SigUpdaterV2 iniciado.")
    _log(log_path, f"ZIP={zip_path}; target={target}; pid={pid}")
    with _installation_lock(target, log_path):
        _recover_interrupted_transactions(target, log_path)
        package_is_full = validate_zip(zip_path)
        if not package_is_full:
            validate_target_shell(target)
        else:
            validate_full_install_destination(target)
        _wait_for_processes(pid, target / "sig.exe", wait_timeout, log_path)
        transaction = Path(tempfile.mkdtemp(prefix=".sig-updater-v2-", dir=str(target.parent)))
        staged = transaction / "staged"
        try:
            _extract_zip(zip_path, staged)
            if updater_override is not None:
                updater_override = Path(updater_override).resolve()
                if not updater_override.is_file() or updater_override.stat().st_size <= 0:
                    raise UpdateError("a cópia independente do updater não está disponível")
                shutil.copy2(updater_override, staged / "SigUpdater.exe")
                _log(log_path, "Updater independente atual preservado no pacote aplicado.")
            validate_install_tree(staged, full=package_is_full)
            _log(log_path, "Pacote extraído e layout validado.")
            _apply_transaction(
                staged,
                target,
                transaction,
                startup_timeout,
                log_path,
                allow_incomplete_target=package_is_full,
            )
        except Exception:
            if transaction.exists():
                try:
                    _rollback_transaction(transaction, target, log_path)
                except Exception as rollback_error:
                    _log(log_path, f"Falha crítica no rollback: {rollback_error}")
            raise
        finally:
            if transaction.exists():
                shutil.rmtree(transaction, ignore_errors=True)


def installed_version(target: Path) -> str | None:
    metadata_path = Path(target) / "build-info.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        version = str(metadata.get("version") or "")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return version if VERSION_RE.fullmatch(version) else None


def version_key(version: str) -> tuple[int, int, int]:
    if not VERSION_RE.fullmatch(version):
        return (0, 0, 0)
    return tuple(int(part) for part in version.split("_"))


def _terminate_target_sig_processes(target_exe: Path, log_path: Path) -> None:
    if os.name != "nt":
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel32.TerminateProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    stopped = []
    for pid, image_path in _process_image_paths().items():
        if pid == os.getpid() or not _same_path(image_path, target_exe):
            continue
        handle = kernel32.OpenProcess(0x0001 | 0x00100000, False, pid)
        if not handle:
            raise UpdateError(f"não foi possível fechar o SIG em execução (PID {pid})")
        try:
            if not kernel32.TerminateProcess(handle, 0):
                raise UpdateError(f"não foi possível fechar o SIG em execução (PID {pid})")
            stopped.append(pid)
        finally:
            kernel32.CloseHandle(handle)
    if stopped:
        _log(log_path, "SIG encerrado pelo modo independente: " + ", ".join(map(str, stopped)))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if not any(_process_alive(pid) for pid in stopped):
                return
            time.sleep(0.1)
        raise UpdateError("o SIG não encerrou a tempo para aplicar a atualização")


def _standalone_cache_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path(tempfile.gettempdir())
    return base / "sig" / "updater"


def _standalone_log_path(target: Path) -> Path:
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / f".sig-updater-write-{uuid.uuid4().hex}.tmp"
        probe.write_bytes(b"")
        probe.unlink()
        return target / "updater.log"
    except OSError:
        fallback = _standalone_cache_root() / "updater.log"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback


def _relocate_standalone_updater(origin: Path) -> int:
    helpers_root = _standalone_cache_root() / "helpers"
    helpers_root.mkdir(parents=True, exist_ok=True)
    for previous in helpers_root.iterdir():
        try:
            if previous.is_dir():
                shutil.rmtree(previous)
            else:
                previous.unlink()
        except OSError:
            # Windows keeps a running helper locked. A simultaneous updater
            # remains untouched and the new one uses a unique directory.
            pass
    helper_root = helpers_root / uuid.uuid4().hex
    helper_root.mkdir(parents=True, exist_ok=True)
    helper = helper_root / "SigUpdater.exe"
    shutil.copy2(Path(sys.executable).resolve(), helper)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    subprocess.Popen(
        [
            str(helper),
            "--standalone-worker",
            "--standalone-target",
            str(origin),
        ],
        cwd=str(origin),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    return 0


class StandaloneUpdaterUI:
    def __init__(self, target: Path):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.target = Path(target).resolve()
        self.events: queue.Queue[tuple] = queue.Queue()
        self.incremental: dict | None = None
        self.full: dict | None = None
        self.busy = False

        self.root = tk.Tk()
        self.root.title("Atualizador do SIG")
        self.root.geometry("620x430")
        self.root.minsize(580, 410)
        self.root.option_add("*Font", ("Segoe UI", 10))
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 18))
        style.configure("Accent.TButton", foreground="#13753b")

        container = ttk.Frame(self.root, padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="Atualizador do SIG", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text=(
                "Atualize uma instalação existente ou use o pacote completo para "
                "instalar e reparar o aplicativo."
            ),
            wraplength=570,
        ).pack(anchor="w", pady=(3, 14))

        path_row = ttk.Frame(container)
        path_row.pack(fill="x")
        ttk.Label(path_row, text="Pasta do SIG:").pack(side="left")
        self.path_var = tk.StringVar(value=str(self.target))
        ttk.Entry(path_row, textvariable=self.path_var, state="readonly").pack(
            side="left", fill="x", expand=True, padx=(8, 6)
        )
        self.choose_button = ttk.Button(path_row, text="Escolher...", command=self._choose_target)
        self.choose_button.pack(side="right")

        self.installed_var = tk.StringVar()
        self.available_var = tk.StringVar(value="Consultando versões disponíveis...")
        ttk.Label(container, textvariable=self.installed_var).pack(anchor="w", pady=(14, 2))
        ttk.Label(container, textvariable=self.available_var, wraplength=570).pack(anchor="w")

        self.progress = ttk.Progressbar(container, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(16, 5))
        self.status_var = tk.StringVar(value="Aguardando.")
        ttk.Label(container, textvariable=self.status_var).pack(anchor="w")

        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(16, 10))
        self.check_button = ttk.Button(actions, text="Verificar", command=self.check_updates)
        self.check_button.pack(side="left")
        self.incremental_button = ttk.Button(
            actions,
            text="Atualizar incremental",
            style="Accent.TButton",
            command=lambda: self.install("incremental"),
            state="disabled",
        )
        self.incremental_button.pack(side="left", padx=(8, 0))
        self.full_button = ttk.Button(
            actions,
            text="Instalar / reparar completo",
            command=lambda: self.install("full"),
            state="disabled",
        )
        self.full_button.pack(side="left", padx=(8, 0))

        self.log = tk.Text(
            container,
            height=6,
            state="disabled",
            wrap="word",
            background="#f4f6f5",
            relief="solid",
            borderwidth=1,
        )
        self.log.pack(fill="both", expand=True)
        self._refresh_installed_version()
        self.root.after(80, self._poll_events)
        self.root.after(250, self.check_updates)

    @staticmethod
    def _format_size(value: int) -> str:
        size = float(value)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{size:.1f} GB"

    def _write_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S  ") + message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _refresh_installed_version(self) -> None:
        version = installed_version(self.target)
        if version:
            text = f"Versão instalada: {version}"
        elif (self.target / "sig.exe").is_file():
            text = "Versão instalada: não identificada"
        else:
            text = "SIG ainda não instalado nesta pasta."
        self.installed_var.set(text)

    def _choose_target(self) -> None:
        selected = self.filedialog.askdirectory(
            title="Escolha a pasta de instalação do SIG",
            initialdir=str(self.target if self.target.exists() else self.target.parent),
            mustexist=False,
        )
        if not selected:
            return
        self.target = Path(selected).resolve()
        self.path_var.set(str(self.target))
        self._refresh_installed_version()

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        self.busy = busy
        normal = "disabled" if busy else "normal"
        self.check_button.configure(state=normal)
        self.choose_button.configure(state=normal)
        self.incremental_button.configure(
            state="normal" if not busy and self.incremental else "disabled"
        )
        self.full_button.configure(state="normal" if not busy and self.full else "disabled")
        if status:
            self.status_var.set(status)

    def check_updates(self) -> None:
        if self.busy:
            return
        self.progress["value"] = 0
        self._set_busy(True, "Consultando o Drive e o GitHub...")
        self._write_log("Verificando pacotes disponíveis.")
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self) -> None:
        errors = []
        notice = None
        incremental = None
        full = None
        try:
            incremental = fetch_incremental_manifest()
            incremental["kind"] = "incremental"
            installed = installed_version(self.target)
            if installed and version_key(incremental["version"]) <= version_key(installed):
                notice = (
                    f"Incremental {incremental['version']} ignorado: "
                    f"a versão instalada ({installed}) já é igual ou mais nova."
                )
                incremental = None
        except Exception as exc:
            errors.append(f"incremental: {exc}")
        try:
            full = fetch_full_release()
        except Exception as exc:
            errors.append(f"completo: {exc}")
        self.events.put(("checked", incremental, full, errors, notice))

    def install(self, kind: str) -> None:
        if self.busy:
            return
        descriptor = self.incremental if kind == "incremental" else self.full
        if not descriptor:
            return
        if kind == "incremental":
            try:
                validate_target_shell(self.target)
            except UpdateError as exc:
                self.messagebox.showerror(
                    "Atualização incremental",
                    f"A instalação não pode receber um incremental.\n\n{exc}\n\nUse o pacote completo.",
                )
                return
            warning = (
                f"O SIG será fechado e a versão {descriptor['version']} será aplicada.\n\n"
                "Continuar?"
            )
        else:
            warning = (
                f"O pacote completo {descriptor['version']} ({self._format_size(descriptor['size'])}) "
                "será instalado. Ele pode reparar uma instalação quebrada ou criar uma nova.\n\n"
                "O SIG aberto será fechado. Continuar?"
            )
        if not self.messagebox.askyesno("Atualizador do SIG", warning):
            return
        self.progress["value"] = 0
        self._set_busy(True, "Preparando o download...")
        threading.Thread(
            target=self._install_worker,
            args=(dict(descriptor), kind),
            daemon=True,
        ).start()

    def _install_worker(self, descriptor: dict, kind: str) -> None:
        version = str(descriptor["version"])
        download_root = _standalone_cache_root() / "downloads" / version / kind
        zip_path = download_root / str(descriptor["zip_name"])
        try:
            download_root.mkdir(parents=True, exist_ok=True)

            def progress(downloaded: int, total: int) -> None:
                percent = min(100, int(downloaded * 100 / max(1, total)))
                self.events.put(("progress", percent, downloaded, total))

            self.events.put(("status", f"Baixando {descriptor['zip_name']}..."))
            _download_to_file(descriptor, zip_path, progress)
            self.events.put(("status", "Validando o pacote antes de alterar a instalação..."))
            validate_zip(zip_path, full=(kind == "full"))
            log_path = _standalone_log_path(self.target)
            if getattr(sys, "frozen", False) and _same_path(sys.executable, self.target / "SigUpdater.exe"):
                raise UpdateError("o atualizador não foi realocado para a pasta temporária")
            _terminate_target_sig_processes(self.target / "sig.exe", log_path)
            self.events.put(("status", "Aplicando a atualização com rollback protegido..."))
            execute(
                zip_path,
                self.target,
                0,
                log_path,
                updater_override=Path(sys.executable) if getattr(sys, "frozen", False) else None,
            )
            zip_path.unlink(missing_ok=True)
            self.events.put(("installed", version, log_path))
        except Exception as exc:
            self.events.put(("failed", str(exc)))

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "checked":
                    self.incremental, self.full, errors, notice = event[1], event[2], event[3], event[4]
                    details = []
                    if self.incremental:
                        details.append(
                            f"Incremental: {self.incremental['version']} "
                            f"({self._format_size(int(self.incremental['size']))})"
                        )
                    if self.full:
                        details.append(
                            f"Completo: {self.full['version']} "
                            f"({self._format_size(int(self.full['size']))})"
                        )
                    self.available_var.set(" | ".join(details) or "Nenhum pacote disponível.")
                    for error in errors:
                        self._write_log("Não foi possível consultar o pacote " + error)
                    if notice:
                        self._write_log(notice)
                    if details:
                        self._write_log("Consulta concluída.")
                    self._set_busy(False, "Pronto.")
                elif kind == "progress":
                    _name, percent, downloaded, total = event
                    self.progress["value"] = percent
                    self.status_var.set(
                        f"Baixando: {percent}% ({self._format_size(downloaded)} de "
                        f"{self._format_size(total)})"
                    )
                elif kind == "status":
                    self.status_var.set(event[1])
                    self._write_log(event[1])
                elif kind == "installed":
                    version, log_path = event[1], event[2]
                    self.progress["value"] = 100
                    self._set_busy(False, f"Versão {version} instalada e validada.")
                    self._write_log(f"Instalação concluída. Log: {log_path}")
                    self.messagebox.showinfo(
                        "Atualizador do SIG",
                        f"A versão {version} foi instalada e o SIG foi iniciado.",
                    )
                    self.root.destroy()
                    return
                elif kind == "failed":
                    self._set_busy(False, "A operação falhou; a instalação anterior foi preservada.")
                    self._write_log("Falha: " + event[1])
                    self.messagebox.showerror(
                        "Atualizador do SIG",
                        "Não foi possível concluir a operação.\n\n" + event[1],
                    )
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(80, self._poll_events)

    def _close(self) -> None:
        if self.busy:
            self.messagebox.showinfo(
                "Atualizador do SIG",
                "Aguarde a operação em andamento terminar.",
            )
            return
        self.root.destroy()

    def run(self) -> int:
        self.root.mainloop()
        return 0


def run_standalone(target: Path | None = None, *, worker: bool = False) -> int:
    if target is None:
        if getattr(sys, "frozen", False):
            target = Path(sys.executable).resolve().parent
        else:
            target = Path.cwd()
    target = Path(target).resolve()
    if getattr(sys, "frozen", False) and not worker:
        return _relocate_standalone_updater(target)
    return StandaloneUpdaterUI(target).run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SigUpdaterV2")
    parser.add_argument("--zip", type=Path)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--wait-timeout", type=int, default=120)
    parser.add_argument("--startup-timeout", type=int, default=12)
    parser.add_argument("--standalone-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--standalone-target", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.standalone_worker:
        return run_standalone(args.standalone_target, worker=True)
    legacy_values = (args.zip, args.target, args.pid, args.log)
    if not any(value is not None for value in legacy_values):
        return run_standalone()
    if not all(value is not None for value in legacy_values):
        parser.error("--zip, --target, --pid e --log devem ser informados juntos")
    try:
        execute(
            args.zip,
            args.target,
            args.pid,
            args.log,
            args.wait_timeout,
            args.startup_timeout,
        )
        return 0
    except (UpdateError, OSError, ValueError) as exc:
        try:
            _log(args.log.resolve(), f"Falha na atualização: {exc}")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
