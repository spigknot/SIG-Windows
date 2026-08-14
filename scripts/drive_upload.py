#!/usr/bin/env python3
"""Publicação do SIG Windows no Google Drive via API (nunca pela unidade X:).

Uso:
    python scripts/drive_upload.py upload <zip>            # -> imprime o file ID
    python scripts/drive_upload.py publish <latest.json>   # atualiza o manifesto existente
    python scripts/drive_upload.py verify <file_id> <sha256> [--name <esperado>]

Credenciais: D:/Projetos/credentials.json (client OAuth) e D:/Projetos/token.json
(token de autorização). A chave privada do manifesto nunca sai da máquina.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

DRIVE_FOLDER_ID = "1-yrsmFu_lAe0dMPo4sK70QRYGqMFcHJK"
MANIFEST_FILE_ID = "1Gompo26SsyhSdliBGNaedLhEfidB244E"
SCOPES = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_PATH = Path("D:/Projetos/credentials.json")
TOKEN_PATH = Path("D:/Projetos/token.json")


def _get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.is_file():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.is_file():
                raise SystemExit(f"credentials.json ausente: {CREDENTIALS_PATH}")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent")
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=creds)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cmd_upload(args: argparse.Namespace) -> int:
    from googleapiclient.http import MediaFileUpload

    zip_path = Path(args.zip).resolve()
    if not zip_path.is_file():
        raise SystemExit(f"ZIP não encontrado: {zip_path}")
    service = _get_service()
    media = MediaFileUpload(str(zip_path), mimetype="application/zip", resumable=True)
    created = service.files().create(
        body={"name": zip_path.name, "parents": [DRIVE_FOLDER_ID]},
        media_body=media,
        fields="id,name,size,md5Checksum",
    ).execute()
    file_id = created["id"]
    check = service.files().get(fileId=file_id, fields="id,name,size,md5Checksum").execute()
    if int(check["size"]) != zip_path.stat().st_size:
        raise SystemExit(f"tamanho divergente após upload: API={check['size']} local={zip_path.stat().st_size}")
    print(f"UPLOAD OK: id={file_id} name={check['name']} size={check['size']} md5={check['md5Checksum']}")
    print(file_id)
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    from googleapiclient.http import MediaFileUpload

    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.is_file():
        raise SystemExit(f"manifesto não encontrado: {manifest_path}")
    service = _get_service()
    media = MediaFileUpload(str(manifest_path), mimetype="application/json")
    updated = service.files().update(
        fileId=MANIFEST_FILE_ID, media_body=media, fields="id,name,size"
    ).execute()
    check = service.files().get(fileId=MANIFEST_FILE_ID, fields="id,name,size").execute()
    if int(check["size"]) != manifest_path.stat().st_size:
        raise SystemExit("tamanho divergente após publicação do manifesto")
    print(f"MANIFESTO atualizado: id={check['id']} name={check['name']} size={check['size']}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from googleapiclient.http import MediaIoBaseDownload

    service = _get_service()
    meta = service.files().get(fileId=args.file_id, fields="id,name,size,md5Checksum").execute()
    print(f"API: id={meta['id']} name={meta['name']} size={meta['size']} md5={meta['md5Checksum']}")
    if args.name and meta["name"] != args.name:
        raise SystemExit(f"nome divergente: API={meta['name']} esperado={args.name}")
    tmp = Path(tempfile.gettempdir()) / f"sig_drive_verify_{meta['name']}"
    request = service.files().get_media(fileId=args.file_id)
    with tmp.open("wb") as handle:
        downloader = MediaIoBaseDownload(handle, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    actual = _sha256(tmp)
    tmp.unlink(missing_ok=True)
    if actual != args.sha256.lower():
        raise SystemExit(f"SHA-256 divergente: baixado={actual} esperado={args.sha256.lower()}")
    print(f"VERIFY OK: sha256={actual}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Publicação do SIG Windows no Google Drive")
    sub = parser.add_subparsers(dest="command", required=True)
    upload = sub.add_parser("upload", help="fazer upload do ZIP incremental")
    upload.add_argument("zip", help="caminho do ZIP (YYYYMMDD_NNN.zip)")
    publish = sub.add_parser("publish", help="atualizar o latest.json assinado")
    publish.add_argument("manifest", help="caminho do latest.json assinado")
    verify = sub.add_parser("verify", help="conferir arquivo publicado pela API (tamanho + sha256)")
    verify.add_argument("file_id", help="ID do arquivo no Drive")
    verify.add_argument("sha256", help="sha256 esperado")
    verify.add_argument("--name", help="nome esperado do arquivo")
    args = parser.parse_args()
    try:
        if args.command == "upload":
            return cmd_upload(args)
        if args.command == "publish":
            return cmd_publish(args)
        if args.command == "verify":
            return cmd_verify(args)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
