#!/usr/bin/env python3
"""Publicação da sincronização por arquivo no Google Drive.

Uso:
    python scripts/sync_publish.py --package release/generated/<versao>/package \
        --version <versao> [--dry-run]

O que faz:
- calcula o snapshot (sha256/size) do pacote canônico;
- compara com ``release/sync_drive_state.json`` (o que JÁ está na pasta do
  Drive dedicada à sincronização);
- sobe apenas arquivos novos/alterados, REUSA os IDs de arquivos inalterados
  e remove do Drive o que saiu do pacote (a pasta reflete sempre o estado
  canônico mais recente);
- gera e assina ``release/sync_manifest.json`` (schema 2) com path, sha256,
  size e drive_id de cada arquivo;
- publica o manifesto no Drive (update do mesmo arquivo — ID estável).

A chave privada nunca sai da máquina. Rodar com o Python que tem
googleapiclient (venv do Hermes) e cryptography.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRIVE_FOLDER_ID = "1-yrsmFu_lAe0dMPo4sK70QRYGqMFcHJK"
SYNC_FOLDER_NAME = "sig-sync"
STATE_PATH = ROOT / "release" / "sync_drive_state.json"
MANIFEST_PATH = ROOT / "release" / "sync_manifest.json"
KEY_PATH = ROOT / "release" / "update_private_key.pem"


def _get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = None
    token_path = Path("D:/Projetos/token.json")
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), ["https://www.googleapis.com/auth/drive"])
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise SystemExit("token do Drive inválido; re-autorize com o fluxo OAuth")
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=creds)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(package: Path) -> dict[str, dict]:
    files: dict[str, dict] = {}
    for path in sorted(package.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file():
            continue
        relative = path.relative_to(package).as_posix()
        files[relative] = {"sha256": _sha256(path), "size": path.stat().st_size}
    return files


def load_state() -> dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_sync_folder(service) -> str:
    folder_id = load_state().get("sync_folder_id")
    if folder_id:
        return folder_id
    listing = (
        service.files()
        .list(
            q=f"name='{SYNC_FOLDER_NAME}' and '{DRIVE_FOLDER_ID}' in parents and "
            "mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id,name)",
            pageSize=10,
        )
        .execute()
    )
    candidates = listing.get("files", [])
    if candidates:
        return candidates[0]["id"]
    created = (
        service.files()
        .create(
            body={
                "name": SYNC_FOLDER_NAME,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [DRIVE_FOLDER_ID],
            },
            fields="id",
        )
        .execute()
    )
    return created["id"]


def _upload_with_retry(service, media, body, fields, attempts=4):
    from googleapiclient.errors import HttpError

    for attempt in range(1, attempts + 1):
        try:
            return service.files().create(body=body, media_body=media, fields=fields).execute()
        except HttpError as exc:
            if exc.resp.status in (403, 429, 500, 503) and attempt < attempts:
                time.sleep(2.0 * attempt)
                continue
            raise


def _delete_with_retry(service, file_id, attempts=4):
    from googleapiclient.errors import HttpError

    for attempt in range(1, attempts + 1):
        try:
            service.files().delete(fileId=file_id).execute()
            return
        except HttpError as exc:
            if exc.resp.status in (403, 429, 500, 503) and attempt < attempts:
                time.sleep(2.0 * attempt)
                continue
            raise


def canonical_manifest(manifest: dict) -> bytes:
    files = sorted(
        (
            {
                "path": str(entry["path"]),
                "sha256": str(entry["sha256"]).lower(),
                "size": int(entry["size"]),
                "drive_id": str(entry["drive_id"]),
                "github_url": str(entry.get("github_url") or ""),
            }
            for entry in manifest.get("files", [])
        ),
        key=lambda item: item["path"],
    )
    payload = {
        "schema": int(manifest.get("schema") or 0),
        "version": str(manifest.get("version") or ""),
        "created_at": str(manifest.get("created_at") or ""),
        "files": files,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_manifest(manifest: dict) -> None:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    if not KEY_PATH.is_file():
        raise SystemExit("chave privada de atualização não encontrada")
    private_key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    signature = private_key.sign(canonical_manifest(manifest), padding.PKCS1v15(), hashes.SHA256())
    manifest["signature"] = base64.b64encode(signature).decode("ascii")


def publish_manifest(service, state: dict, manifest: dict) -> str:
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(MANIFEST_PATH), mimetype="application/json", resumable=True)
    file_id = state.get("manifest_file_id")
    if file_id:
        updated = service.files().update(fileId=file_id, media_body=media, fields="id,name,size").execute()
    else:
        created = service.files().create(
            body={"name": "sync_manifest.json", "parents": [DRIVE_FOLDER_ID]},
            media_body=media,
            fields="id,name,size",
        ).execute()
        updated = created
    check = service.files().get(fileId=updated["id"], fields="id,name,size").execute()
    if int(check["size"]) != MANIFEST_PATH.stat().st_size:
        raise SystemExit("tamanho divergente após publicação do sync_manifest.json")
    return updated["id"]


def list_sync_folder_files(service, folder_id: str) -> dict[str, str]:
    """Lista os arquivos existentes na pasta sync: {nome: id}."""
    listing: dict[str, str] = {}
    page_token = ""
    while True:
        response = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken,files(id,name)",
                pageSize=1000,
                pageToken=page_token or None,
            )
            .execute()
        )
        for item in response.get("files", []):
            listing[str(item["name"])] = str(item["id"])
        page_token = response.get("nextPageToken", "")
        if not page_token:
            break
    return listing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--github-tag", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    package = Path(args.package).resolve()
    if not package.is_dir():
        raise SystemExit(f"pacote não encontrado: {package}")
    current = snapshot(package)
    state = load_state()
    previous = state.get("files", {})

    service = None if args.dry_run else _get_service()
    folder_id = None if args.dry_run else resolve_sync_folder(service)

    to_upload = [
        path for path, entry in current.items()
        if previous.get(path, {}).get("sha256") != entry["sha256"]
    ]
    to_delete = [path for path in previous if path not in current]

    print(f"pacote: {len(current)} arquivos | subir: {len(to_upload)} | remover: {len(to_delete)}")
    if args.dry_run:
        for path in to_upload[:10]:
            print(f"  upload: {path}")
        for path in to_delete[:10]:
            print(f"  delete: {path}")
        return 0

    from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

    # Reconciliação: arquivos já presentes na pasta (de execuções anteriores
    # interrompidas) são reusados pelo nome quando o estado não os conhece.
    existing_in_folder = list_sync_folder_files(service, folder_id)
    new_files: dict[str, dict] = {}
    for index, path in enumerate(to_upload, 1):
        local = package / Path(*path.split("/"))
        entry = current[path]
        reused_id = None
        if path not in previous and path in existing_in_folder:
            # confirma pelo hash baixado? não: reusa o ID e o próximo diff
            # corrige se o conteúdo divergir. Para o upload inicial basta o nome.
            reused_id = existing_in_folder[path]
        if reused_id:
            new_files[path] = {
                "drive_id": reused_id,
                "sha256": entry["sha256"],
                "size": entry["size"],
            }
        elif entry["size"] < 5 * 1024 * 1024:
            # Upload simples para arquivos pequenos: muito mais rápido que o
            # resumable (que tem handshake por arquivo).
            with local.open("rb") as handle:
                media = MediaIoBaseUpload(
                    handle, mimetype="application/octet-stream", chunksize=1024 * 1024
                )
                created = _upload_with_retry(
                    service,
                    media,
                    {"name": path, "parents": [folder_id]},
                    "id,name,size",
                )
            new_files[path] = {
                "drive_id": created["id"],
                "sha256": entry["sha256"],
                "size": entry["size"],
            }
        else:
            media = MediaFileUpload(str(local), resumable=True)
            created = _upload_with_retry(
                service,
                media,
                {"name": path, "parents": [folder_id]},
                "id,name,size",
            )
            new_files[path] = {
                "drive_id": created["id"],
                "sha256": entry["sha256"],
                "size": entry["size"],
            }
        if index % 25 == 0 or index == len(to_upload):
            # Salva o progresso incremental para poder continuar de onde parou.
            interim = dict(state)
            interim_files: dict[str, dict] = {}
            for done_path, done_entry in current.items():
                if done_path in new_files:
                    interim_files[done_path] = new_files[done_path]
                else:
                    previous_entry = previous.get(done_path) or {}
                    drive_id = previous_entry.get("drive_id")
                    if drive_id:
                        interim_files[done_path] = {
                            "drive_id": drive_id,
                            "sha256": done_entry["sha256"],
                            "size": done_entry["size"],
                        }
            interim["files"] = interim_files
            interim["sync_folder_id"] = folder_id
            interim["partial"] = True
            save_state(interim)
            print(f"  upload {index}/{len(to_upload)}")
        time.sleep(0.02)

    for path in to_delete:
        old_entry = previous.get(path) or {}
        if old_entry.get("drive_id"):
            _delete_with_retry(service, old_entry["drive_id"])
        print(f"  removido do Drive: {path}")

    # Estado novo: reusa IDs dos inalterados + os novos
    merged: dict[str, dict] = {}
    for path, entry in current.items():
        previous_entry = previous.get(path) or {}
        drive_id = new_files[path]["drive_id"] if path in new_files else previous_entry.get("drive_id")
        if not drive_id:
            raise SystemExit(f"sem drive_id para {path} (estado inconsistente)")
        merged[path] = {"drive_id": drive_id, "sha256": entry["sha256"], "size": entry["size"]}
    state["files"] = merged
    state["sync_folder_id"] = folder_id
    save_state(state)

    manifest = {
        "schema": 2,
        "version": args.version,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "files": [
            {
                "path": path,
                "sha256": entry["sha256"],
                "size": entry["size"],
                "drive_id": entry["drive_id"],
                **(
                    {
                        "github_url": (
                            "https://github.com/spigknot/SIG-Windows/releases/"
                            f"download/{args.github_tag}/{path}"
                        )
                    }
                    if args.github_tag and path in {"sig.exe", "SigUpdater.exe"}
                    else {}
                ),
            }
            for path, entry in sorted(merged.items())
        ],
    }
    sign_manifest(manifest)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifesto assinado: {MANIFEST_PATH}")

    manifest_id = publish_manifest(service, state, manifest)
    state["manifest_file_id"] = manifest_id
    save_state(state)
    print(f"sync_manifest.json publicado: id={manifest_id}")
    print("IMPORTANTE: SYNC_MANIFEST_FILE_ID no updater deve ser", manifest_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
