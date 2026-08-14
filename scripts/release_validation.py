"""Executable release gates for SIG Windows.

This module deliberately validates the frozen PyInstaller artifact and the
assembled package.  It does not import the GUI application, so it is safe to
run in CI or on a build machine without opening Tk.
"""

from __future__ import annotations

import base64
import hashlib
import json
import marshal
import re
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable


VERSION_RE = re.compile(r"^\d{8}_\d{3}$")
CRITICAL_WARNING_RE = re.compile(
    r"missing module named(?:\s+['\"]?)?\s*(pypdfium2|pypdfium2_raw|sounddevice|websocket)\b",
    re.IGNORECASE,
)
CRITICAL_MODULES = {"pypdfium2", "pypdfium2_raw", "sounddevice", "websocket"}
REQUIRED_FULL_FILES = (
    "sig.exe",
    "_internal/base_library.zip",
    "_internal/python311.dll",
    "_internal/vcruntime140.dll",
    "_internal/vcruntime140_1.dll",
    "_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll",
    "SigUpdater.exe",
    "ffmpeg.exe",
    "ffplay.exe",
    "vad_worker.py",
    "prompts/historico_system.txt",
    "prompts/historico_user.txt",
    "prompts/oitiva_system.txt",
    "prompts/oitiva_user.txt",
    "prompts/partes_system.txt",
    "prompts/qualificacao_system.txt",
    "prompts/qualificacao_user.txt",
    "modelos/modelo_declaracoes.docx",
    "modelos/modelo_depoimento.docx",
)
REQUIRED_FULL_DIRECTORIES = ("_internal", "vad_deps", "prompts", "modelos")
RUNTIME_ASSET_FILES = ("ffmpeg.exe", "ffplay.exe")
RUNTIME_ASSET_DIRECTORIES = ("vad_deps",)
INCREMENTAL_FORBIDDEN_TOP_LEVEL = {
    "ffmpeg.exe",
    "ffplay.exe",
    "vad_worker.py",
    "vad_deps",
}
REQUIRED_INCREMENTAL_FILES = tuple(
    relative
    for relative in REQUIRED_FULL_FILES
    if relative not in {"ffmpeg.exe", "ffplay.exe", "vad_worker.py"}
)
REQUIRED_INCREMENTAL_DIRECTORIES = ("_internal", "prompts", "modelos")


class ValidationError(RuntimeError):
    """Raised when a release gate fails."""


def _normal(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    if not path.is_dir():
        raise ValidationError(f"diretório de runtime ausente: {path}")
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        if child.is_file():
            relative_path = child.relative_to(path)
            if "__pycache__" in relative_path.parts or child.suffix.casefold() in {".pyc", ".pyo"}:
                continue
            relative = relative_path.as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(child.read_bytes())
    return digest.hexdigest()


def runtime_asset_fingerprint(runtime_root: Path) -> dict:
    files = {}
    for relative in RUNTIME_ASSET_FILES:
        path = runtime_root / relative
        if not path.is_file():
            raise ValidationError(f"asset de runtime ausente: {path}")
        files[relative] = {
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    directories = {}
    for relative in RUNTIME_ASSET_DIRECTORIES:
        path = runtime_root / relative
        directories[relative] = sha256_tree(path)
    return {"files": files, "directories": directories}


def validate_runtime_assets(runtime_root: Path, metadata_path: Path) -> None:
    if not metadata_path.is_file():
        raise ValidationError(f"manifesto de assets de runtime ausente: {metadata_path}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError(f"manifesto de assets de runtime inválido: {exc}") from exc
    expected = {
        "files": metadata.get("files") or {},
        "directories": metadata.get("directories") or {},
    }
    actual = runtime_asset_fingerprint(runtime_root)
    if actual != expected:
        raise ValidationError(
            "assets de runtime não correspondem ao conjunto aprovado em "
            f"{metadata_path}; possível conteúdo antigo ou alterado de dist"
        )


def source_fingerprint(repo_root: Path) -> str:
    digest = hashlib.sha256()
    for relative in (
        "src/sig_app.py",
        "src/vad_worker.py",
        "src/assistant_prompts.py",
        "updater_v2/updater.py",
        "sig.spec",
        "requirements.txt",
        "prompts/historico_system.txt",
        "prompts/historico_user.txt",
        "prompts/oitiva_system.txt",
        "prompts/oitiva_user.txt",
        "prompts/partes_system.txt",
        "prompts/qualificacao_system.txt",
        "prompts/qualificacao_user.txt",
        "modelos/modelo_declaracoes.docx",
        "modelos/modelo_depoimento.docx",
    ):
        path = repo_root / relative
        if not path.is_file():
            raise ValidationError(f"arquivo de build ausente: {relative}")
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def read_app_version(source_path: Path) -> str:
    text = source_path.read_text(encoding="utf-8")
    matches = re.findall(r"^APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    if len(matches) != 1:
        raise ValidationError(
            f"APP_VERSION deve aparecer exatamente uma vez em {_normal(source_path)}"
        )
    version = matches[0]
    if not VERSION_RE.fullmatch(version):
        raise ValidationError(f"APP_VERSION inválida: {version!r}")
    return version


def read_manifest(manifest_path: Path) -> dict:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - error is reported to the user
        raise ValidationError(f"manifesto inválido: {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValidationError("manifesto deve ser um objeto JSON")
    return manifest


def _manifest_payload(manifest: dict) -> bytes:
    payload = {
        "schema": int(manifest.get("schema") or 0),
        "version": str(manifest.get("version") or ""),
        "zip_file_id": str(manifest.get("zip_file_id") or ""),
        "zip_name": str(manifest.get("zip_name") or ""),
        "sha256": str(manifest.get("sha256") or "").lower(),
        "size": int(manifest.get("size") or 0),
        "created_at": str(manifest.get("created_at") or ""),
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_public_key(source_path: Path) -> tuple[int, int]:
    text = source_path.read_text(encoding="utf-8")
    exponent = re.search(r"^UPDATE_PUBLIC_KEY_E\s*=\s*(\d+)", text, re.MULTILINE)
    modulus = re.search(r"^UPDATE_PUBLIC_KEY_N\s*=\s*(\d+)", text, re.MULTILINE)
    if not exponent or not modulus:
        raise ValidationError("chave pública do updater não encontrada no código")
    return int(exponent.group(1)), int(modulus.group(1))


def validate_manifest_signature(manifest: dict, source_path: Path) -> None:
    try:
        signature = base64.b64decode(str(manifest.get("signature") or ""), validate=True)
        exponent, modulus = _read_public_key(source_path)
        key_size = (modulus.bit_length() + 7) // 8
        if len(signature) != key_size:
            raise ValidationError("assinatura do manifesto tem tamanho inválido")
        encoded = pow(int.from_bytes(signature, "big"), exponent, modulus)
        encoded_bytes = encoded.to_bytes(key_size, "big")
        digest_info = (
            bytes.fromhex("3031300d060960864801650304020105000420")
            + hashlib.sha256(_manifest_payload(manifest)).digest()
        )
        padding_size = key_size - len(digest_info) - 3
        expected = b"\x00\x01" + (b"\xff" * padding_size) + b"\x00" + digest_info
        if padding_size < 8 or encoded_bytes != expected:
            raise ValidationError("assinatura do manifesto é inválida")
    except (TypeError, ValueError, base64.binascii.Error) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(f"assinatura do manifesto é inválida: {exc}") from exc


def validate_version_consistency(
    app_version: str,
    manifest: dict,
    zip_path: Path | None = None,
    frozen_version: str | None = None,
) -> None:
    manifest_version = str(manifest.get("version") or "")
    zip_name = str(manifest.get("zip_name") or "")
    if not VERSION_RE.fullmatch(manifest_version):
        raise ValidationError(f"version inválida no manifesto: {manifest_version!r}")
    if app_version != manifest_version:
        raise ValidationError(
            "versão inconsistente: "
            f"APP_VERSION={app_version}, manifesto={manifest_version}"
        )
    if zip_name != f"{manifest_version}.zip":
        raise ValidationError(
            f"nome do ZIP inconsistente: {zip_name!r} != {manifest_version}.zip"
        )
    if frozen_version is not None and frozen_version != app_version:
        raise ValidationError(
            "versão congelada inconsistente: "
            f"sig.exe={frozen_version}, APP_VERSION={app_version}"
        )
    if zip_path is not None:
        if not zip_path.is_file():
            raise ValidationError(f"ZIP de release não encontrado: {zip_path}")
        if zip_path.name != zip_name:
            raise ValidationError(
                f"ZIP selecionado tem nome {zip_path.name!r}, esperado {zip_name!r}"
            )
        expected_size = int(manifest.get("size") or 0)
        expected_hash = str(manifest.get("sha256") or "").lower()
        actual_size = zip_path.stat().st_size
        actual_hash = sha256_file(zip_path)
        if actual_size != expected_size:
            raise ValidationError(
                f"tamanho do ZIP não confere: {actual_size} != {expected_size}"
            )
        if actual_hash != expected_hash:
            raise ValidationError("SHA-256 do ZIP não confere com o manifesto")


def frozen_app_version(executable: Path) -> str:
    """Read APP_VERSION from the frozen sig_app code object.

    PyInstaller stores the top-level script as a marshalled code object in the
    CArchive. This validates the actual executable rather than trusting the
    source file or a separately generated metadata file.
    """

    try:
        from PyInstaller.archive.readers import CArchiveReader
    except ImportError as exc:  # pragma: no cover - exercised on misconfigured envs
        raise ValidationError(
            "PyInstaller não está disponível no Python que executa a validação"
        ) from exc
    if not executable.is_file():
        raise ValidationError(f"executável congelado não encontrado: {executable}")
    try:
        reader = CArchiveReader(str(executable))
        raw_code = reader.extract("sig_app")
        code = marshal.loads(raw_code)
    except Exception as exc:  # pragma: no cover - depends on binary corruption
        raise ValidationError(f"não foi possível ler sig_app de {executable}: {exc}") from exc

    versions: set[str] = set()

    def walk(current) -> None:
        for constant in current.co_consts:
            if isinstance(constant, str) and VERSION_RE.fullmatch(constant):
                versions.add(constant)
            elif hasattr(constant, "co_consts"):
                walk(constant)

    walk(code)
    if len(versions) != 1:
        raise ValidationError(
            f"não foi encontrada uma única versão embutida em {executable}: {sorted(versions)}"
        )
    return next(iter(versions))


def _assert_no_bad_layout(names: Iterable[str]) -> None:
    normalized = [_normal(name).strip("/") for name in names]
    for name in normalized:
        parts = PurePosixPath(name).parts
        if "g" in parts:
            raise ValidationError("pacote contém a pasta proibida g")
        if any(part.startswith("_MEI") for part in parts):
            raise ValidationError("pacote contém artefato de execução one-file _MEI")


def validate_package_layout(package_root: Path, full: bool = True) -> None:
    if not package_root.is_dir():
        raise ValidationError(f"raiz do pacote não encontrada: {package_root}")
    _assert_no_bad_layout(path.relative_to(package_root) for path in package_root.rglob("*"))
    required_files = REQUIRED_FULL_FILES if full else REQUIRED_INCREMENTAL_FILES
    required_dirs = REQUIRED_FULL_DIRECTORIES if full else REQUIRED_INCREMENTAL_DIRECTORIES
    for relative in required_files:
        if not (package_root / Path(relative)).is_file():
            raise ValidationError(f"componente obrigatório ausente: {relative}")
    for relative in required_dirs:
        if not (package_root / relative).is_dir():
            raise ValidationError(f"diretório obrigatório ausente: {relative}")
    if not full:
        forbidden = sorted(
            child.name
            for child in package_root.iterdir()
            if child.name in INCREMENTAL_FORBIDDEN_TOP_LEVEL
        )
        if forbidden:
            raise ValidationError(
                "pacote incremental contém recursos de runtime proibidos: "
                + ", ".join(forbidden)
            )


def validate_zip_layout(zip_path: Path, full: bool = True) -> None:
    if not zip_path.is_file():
        raise ValidationError(f"ZIP não encontrado: {zip_path}")
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = [entry.filename for entry in archive.infolist()]
            _assert_no_bad_layout(names)
            files = {name.rstrip("/") for name in names if not name.endswith("/")}
            dirs = {name.rstrip("/") for name in names if name.endswith("/")}
            required_files = REQUIRED_FULL_FILES if full else REQUIRED_INCREMENTAL_FILES
            for relative in required_files:
                if relative not in files:
                    raise ValidationError(f"componente ausente no ZIP: {relative}")
            required_directories = REQUIRED_FULL_DIRECTORIES if full else REQUIRED_INCREMENTAL_DIRECTORIES
            for relative in required_directories:
                if not any(name == relative or name.startswith(relative + "/") for name in files | dirs):
                    raise ValidationError(f"diretório ausente no ZIP: {relative}")
            if not full:
                forbidden = sorted(
                    name
                    for name in files | dirs
                    if PurePosixPath(name).parts
                    and PurePosixPath(name).parts[0] in INCREMENTAL_FORBIDDEN_TOP_LEVEL
                )
                if forbidden:
                    raise ValidationError(
                        "pacote incremental contém recursos de runtime proibidos: "
                        + ", ".join(forbidden)
                    )
    except zipfile.BadZipFile as exc:
        raise ValidationError(f"ZIP inválido: {zip_path}") from exc


def validate_frozen_dependencies(package_root: Path) -> None:
    executable = package_root / "sig.exe"
    try:
        from PyInstaller.archive.readers import CArchiveReader
        reader = CArchiveReader(str(executable))
        pyz = reader.open_embedded_archive("PYZ.pyz")
        modules = set(pyz.toc)
    except Exception as exc:  # pragma: no cover - binary/environment dependent
        raise ValidationError(f"não foi possível inspecionar dependências congeladas: {exc}") from exc
    missing = sorted(CRITICAL_MODULES - modules)
    if missing:
        raise ValidationError(f"módulos ausentes no PYZ do executável: {', '.join(missing)}")
    for module in ("_sounddevice", "_sounddevice_data", "sounddevice"):
        if module not in modules:
            raise ValidationError(f"módulo ausente no PYZ do executável: {module}")
    portaudio = package_root / "_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll"
    if not portaudio.is_file():
        raise ValidationError(f"DLL do PortAudio ausente: {portaudio}")
    pdfium = package_root / "_internal/pypdfium2_raw/pdfium.dll"
    if not pdfium.is_file():
        raise ValidationError(f"DLL do PDFium ausente: {pdfium}")


def validate_pyinstaller_warnings(warn_path: Path) -> None:
    if not warn_path.is_file():
        raise ValidationError(f"warn-sig.txt não encontrado: {warn_path}")
    critical = [line.strip() for line in warn_path.read_text(encoding="utf-8", errors="replace").splitlines() if CRITICAL_WARNING_RE.search(line)]
    if critical:
        raise ValidationError("warnings críticos do PyInstaller:\n" + "\n".join(critical))


def write_build_info(
    package_root: Path,
    repo_root: Path,
    version: str,
    build_id: str,
    built_at: float,
    runtime_manifest_path: Path | None = None,
) -> Path:
    executable = package_root / "sig.exe"
    updater = package_root / "SigUpdater.exe"
    data = {
        "schema": 1,
        "version": version,
        "build_id": build_id,
        "built_at": built_at,
        "source_fingerprint": source_fingerprint(repo_root),
        "sig_sha256": sha256_file(executable),
        "sig_updater_sha256": sha256_file(updater),
    }
    if runtime_manifest_path is not None:
        data["runtime_manifest_sha256"] = sha256_file(runtime_manifest_path)
    path = package_root / "build-info.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def validate_build_info(
    package_root: Path,
    repo_root: Path,
    version: str,
    minimum_time: float | None = None,
    runtime_manifest_path: Path | None = None,
) -> dict:
    path = package_root / "build-info.json"
    if not path.is_file():
        raise ValidationError("build-info.json ausente; o pacote não veio do clean build oficial")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != version:
        raise ValidationError("build-info.json tem versão diferente da release")
    if data.get("source_fingerprint") != source_fingerprint(repo_root):
        raise ValidationError("build-info.json não corresponde ao código-fonte atual")
    if minimum_time is not None and float(data.get("built_at") or 0) < minimum_time:
        raise ValidationError("build-info.json é anterior ao início deste clean build")
    if data.get("sig_sha256") != sha256_file(package_root / "sig.exe"):
        raise ValidationError("sig.exe foi alterado depois da geração do build-info.json")
    if runtime_manifest_path is not None:
        expected = data.get("runtime_manifest_sha256")
        if expected != sha256_file(runtime_manifest_path):
            raise ValidationError("build-info.json não corresponde ao manifesto de assets atual")
    return data


def validate_updater_artifact(package_root: Path, metadata_path: Path) -> None:
    updater = package_root / "SigUpdater.exe"
    if not updater.is_file():
        raise ValidationError("SigUpdater.exe ausente")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_size = int(metadata.get("size") or 0)
    expected_hash = str(metadata.get("sha256") or "").lower()
    if updater.stat().st_size != expected_size or sha256_file(updater) != expected_hash:
        raise ValidationError(
            "SigUpdater.exe não corresponde ao artefato conhecido como bom; "
            "o código-fonte do updater não está versionado neste projeto"
        )


def validate_manifest_shape(manifest: dict) -> None:
    required = {"schema", "version", "zip_file_id", "zip_name", "sha256", "size", "created_at", "signature"}
    missing = sorted(required - manifest.keys())
    if missing:
        raise ValidationError("campos ausentes no manifesto: " + ", ".join(missing))
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest["sha256"]).lower()):
        raise ValidationError("sha256 inválido no manifesto")
    if int(manifest["size"]) <= 0:
        raise ValidationError("tamanho inválido no manifesto")


def validate_current(
    repo_root: Path,
    package_root: Path,
    manifest_path: Path,
    updater_metadata: Path,
    warn_path: Path | None = None,
    zip_path: Path | None = None,
    require_build_info: bool = False,
    runtime_root: Path | None = None,
    runtime_manifest: Path | None = None,
) -> list[str]:
    source_path = repo_root / "src/sig_app.py"
    app_version = read_app_version(source_path)
    manifest = read_manifest(manifest_path)
    validate_manifest_shape(manifest)
    validate_manifest_signature(manifest, source_path)
    frozen_version = frozen_app_version(package_root / "sig.exe")
    validate_version_consistency(app_version, manifest, zip_path, frozen_version)
    validate_package_layout(package_root, full=True)
    validate_frozen_dependencies(package_root)
    validate_updater_artifact(package_root, updater_metadata)
    if runtime_root is not None and runtime_manifest is not None:
        validate_runtime_assets(runtime_root, runtime_manifest)
        validate_runtime_assets(package_root, runtime_manifest)
    if warn_path is not None:
        validate_pyinstaller_warnings(warn_path)
    if require_build_info:
        validate_build_info(package_root, repo_root, app_version, runtime_manifest_path=runtime_manifest)
    if zip_path is not None:
        validate_zip_layout(zip_path, full=True)
    return [
        f"versão consistente: {app_version}",
        "artefato congelado contém sounddevice, websocket e PortAudio",
        "layout completo do pacote validado",
        "SigUpdater.exe corresponde ao artefato conhecido como bom",
    ]
