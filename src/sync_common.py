"""Protocolo da sincronização por arquivo — compartilhado entre o SIG e o updater.

Esta é a cópia CANÔNICA do protocolo para o SIG (src/). O updater mantém uma
cópia embutida equivalente em ``updater_v2/updater.py`` (compilada no
SigUpdater.exe). Os testes ``tests/test_sync_common.py`` garantem a PARIDADE
entre as duas cópias (canonical e validação) — nunca alterar um sem o outro.

Fonte do design: UPDATE.md.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

R2_PUBLIC_HOST = "pub-abb3913e7d83457bae19e41b1e4020cc.r2.dev"
SYNC_MANIFEST_SCHEMA = 2
SYNC_MANIFEST_MAX_BYTES = 2 * 1024 * 1024
SYNC_MANIFEST_MAX_FILES = 20_000

VERSION_RE = re.compile(r"^\d{8}_\d{3}$")

# Chave pública de verificação (a mesma do latest.json; a privada nunca sai
# da máquina de publicação).
UPDATE_PUBLIC_KEY_E = 65537
UPDATE_PUBLIC_KEY_N = 4776833754672109710666015745718377295826954378034957006723781632230794955188598743370375368759247701138572196632244506341860738985196771222328276471293164426045586502411553661270415658303449836000240060850077943629529298365455842583839584430835872888082421190431050761740593243172708805858229100494995424042846759167936558524923889093025581721886390801543158714477942628958659907698645218405072643039190789807520623959789948760663039915934233343926084287154817842449929074144135976678727267978353880303189583548982201552861178437687569977746462198133228741460769839629249527122404198789341588724117695515639417887297249072695071299249800470626986276226209694407865386128033982643621030612265330884993509358887003353611841249193688390145075540912405754224137641702769971761374974256331506313629217304424829655209764530396523158905317988087656296751937468490602949770457129034644632659661248617309294539893653236376299080388523

SYNC_REQUIRED_FILES = (
    "sig.exe",
    "SigUpdater.exe",
    "build-info.json",
    "_internal/base_library.zip",
    "_internal/python311.dll",
    "_internal/vcruntime140.dll",
    "_internal/vcruntime140_1.dll",
    "_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll",
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

SYNC_MANAGED_TOP_LEVELS = (
    "sig.exe",
    "SigUpdater.exe",
    "build-info.json",
    "_internal",
    "prompts",
    "modelos",
    "ffmpeg.exe",
    "ffplay.exe",
    "vad_worker.py",
    "vad_deps",
)

SYNC_ALLOWED_TOP_LEVELS = (
    "sig.exe",
    "SigUpdater.exe",
    "build-info.json",
    "_internal",
    "prompts",
    "modelos",
    "ffmpeg.exe",
    "ffplay.exe",
    "ffprobe.exe",
    "vad_worker.py",
    "vad_deps",
)


class SyncError(RuntimeError):
    pass


def _verify_rsa_sha256_signature(signature_b64: str, canonical_bytes: bytes) -> bool:
    try:
        signature = base64.b64decode(signature_b64 or "", validate=True)
        key_size = (UPDATE_PUBLIC_KEY_N.bit_length() + 7) // 8
        if len(signature) != key_size:
            return False
        encoded = pow(int.from_bytes(signature, "big"), UPDATE_PUBLIC_KEY_E, UPDATE_PUBLIC_KEY_N)
        encoded_bytes = encoded.to_bytes(key_size, "big")
        digest_info = (
            bytes.fromhex("3031300d060960864801650304020105000420")
            + hashlib.sha256(canonical_bytes).digest()
        )
        padding_size = key_size - len(digest_info) - 3
        if padding_size < 8:
            return False
        expected = b"\x00\x01" + (b"\xff" * padding_size) + b"\x00" + digest_info
        return encoded_bytes == expected
    except (TypeError, ValueError):
        return False


def canonical_sync_manifest(manifest: dict) -> bytes:
    """Payload canônico assinado do manifesto de sincronização (schema 2)."""
    files = manifest.get("files") or []
    canonical_files = sorted(
        (
            {
                "path": str(entry.get("path") or ""),
                "sha256": str(entry.get("sha256") or "").lower(),
                "size": int(entry.get("size") or 0),
                "drive_id": str(entry.get("drive_id") or ""),
                "github_url": str(entry.get("github_url") or ""),
            }
            for entry in files
        ),
        key=lambda item: item["path"],
    )
    signed_payload = {
        "schema": int(manifest.get("schema") or 0),
        "version": str(manifest.get("version") or ""),
        "created_at": str(manifest.get("created_at") or ""),
        "files": canonical_files,
    }
    return json.dumps(
        signed_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_sync_manifest_signature(manifest: dict) -> bool:
    return _verify_rsa_sha256_signature(
        str(manifest.get("signature") or ""),
        canonical_sync_manifest(manifest),
    )


def validate_sync_manifest(manifest: dict) -> dict:
    """Valida estrutura e assinatura; retorna {"version": str, "files": {path: entry}}."""
    if not isinstance(manifest, dict):
        raise SyncError("o manifesto de sincronização não é um objeto JSON")
    if int(manifest.get("schema") or 0) != SYNC_MANIFEST_SCHEMA:
        raise SyncError("o manifesto de sincronização não usa o schema esperado")
    if not verify_sync_manifest_signature(manifest):
        raise SyncError("o manifesto de sincronização não possui uma assinatura digital válida")
    version = str(manifest.get("version") or "")
    if not VERSION_RE.fullmatch(version):
        raise SyncError("o manifesto de sincronização contém uma versão inválida")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise SyncError("o manifesto de sincronização não lista arquivos")
    if len(raw_files) > SYNC_MANIFEST_MAX_FILES:
        raise SyncError("o manifesto de sincronização excede o limite de arquivos")
    files: dict[str, dict] = {}
    for index, entry in enumerate(raw_files):
        if not isinstance(entry, dict):
            raise SyncError(f"entrada {index} do manifesto é inválida")
        path = str(entry.get("path") or "")
        top = path.split("/", 1)[0]
        # Componentes que esta versão do app não conhece (ex.: um runtime asset
        # adicionado numa release mais nova) NÃO podem rejeitar o manifesto
        # inteiro — senão instalações antigas ficam presas sem atualizar.
        # Ignorar a entrada desconhecida; os obrigatórios (SYNC_REQUIRED_FILES)
        # continuam sendo validados abaixo.
        if top not in SYNC_ALLOWED_TOP_LEVELS:
            continue
        if path in files:
            raise SyncError(f"caminho duplicado no manifesto de sincronização: {path}")
        sha256 = str(entry.get("sha256") or "").lower()
        if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
            raise SyncError(f"hash inválido no manifesto para: {path}")
        size = int(entry.get("size") or 0)
        if size < 0:
            raise SyncError(f"tamanho inválido no manifesto para: {path}")
        github_url = str(entry.get("github_url") or "").strip()
        if not github_url:
            raise SyncError(f"manifesto R2 sem URL de download para: {path}")
        import urllib.parse

        parsed = urllib.parse.urlparse(github_url)
        r2_host = R2_PUBLIC_HOST
        allowed_github_path = "/spigknot/SIG-Windows/releases/download/"
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ("github.com", r2_host)
            or (parsed.hostname == "github.com" and not parsed.path.startswith(allowed_github_path))
            or (parsed.hostname == r2_host and not parsed.path.startswith("/"))
        ):
            raise SyncError(f"URL de download inválida no manifesto para: {path}")
        files[path] = {
            "sha256": sha256,
            "size": size,
            "drive_id": "",
            "github_url": github_url,
        }
    missing = sorted(relative for relative in SYNC_REQUIRED_FILES if relative not in files)
    if missing:
        raise SyncError(
            "o manifesto de sincronização não cobre componentes obrigatórios: "
            + ", ".join(missing)
        )
    return {"version": version, "files": files}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_sync_cache_artifact(relpath: str) -> bool:
    """True para artefatos de cache local (__pycache__/*.pyc).

    Estes arquivos são gerados pelo Python em execução, variam de máquina para
    máquina e NUNCA devem ser sincronizados nem removidos pela atualização.
    """
    parts = PurePosixPath(relpath).parts
    return "__pycache__" in parts or parts[-1].endswith(".pyc")


# Espelha INCREMENTAL_FORBIDDEN_TOP_LEVEL do updater: assets de runtime que a
# atualização nunca pode remover (chegam pelo full/instalador).
SYNC_REMOVE_FORBIDDEN_TOP_LEVELS = frozenset(
    {"ffmpeg.exe", "ffplay.exe", "ffprobe.exe", "vad_worker.py", "vad_deps"}
)


def classify_sync_files(target: Path, files: dict[str, dict]) -> dict:
    """Classifica a instalação local contra o manifesto.

    Retorna {"download": [paths], "remove": [paths], "unchanged": int, "total": int}.
    """
    target = Path(target).resolve()
    download: list[str] = []
    unchanged = 0
    for path, entry in sorted(files.items()):
        # Nunca baixar artefatos de cache local (__pycache__/*.pyc) — são
        # lixo de execução e não fazem parte do aplicativo.
        if is_sync_cache_artifact(path):
            continue
        local = target / Path(*PurePosixPath(path).parts)
        if not local.is_file():
            download.append(path)
            continue
        if local.stat().st_size != int(entry["size"]):
            download.append(path)
            continue
        if sha256_file(local) != entry["sha256"]:
            download.append(path)
            continue
        unchanged += 1

    managed_paths: set[str] = set()
    for top in SYNC_MANAGED_TOP_LEVELS:
        candidate = target / Path(*PurePosixPath(top).parts)
        if candidate.is_file():
            managed_paths.add(top)
        elif candidate.is_dir():
            for local in candidate.rglob("*"):
                if local.is_file():
                    managed_paths.add(local.relative_to(target).as_posix())
    remove = sorted(
        path
        for path in managed_paths
        if path not in files
        # Nunca remover artefatos de cache local nem assets de runtime: o
        # updater rejeita remoção de runtime e o cache é lixo que o Python
        # recria sozinho (bug 20260901: .pyc de vad_deps/__pycache__ quebrava
        # a atualização com "removidos.txt não pode remover asset de runtime").
        and not is_sync_cache_artifact(path)
        and path.split("/", 1)[0] not in SYNC_REMOVE_FORBIDDEN_TOP_LEVELS
    )

    return {
        "download": download,
        "remove": remove,
        "unchanged": unchanged,
        "total": len(files),
    }
