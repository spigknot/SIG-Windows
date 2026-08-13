"""Inspeciona o ZIP 006 publicado no Drive (verificação pós-publicação).

Uso: python scripts/inspect_drive_zip.py
    Lê release/latest.json, baixa o ZIP pelo ID via API do Drive,
    confere sha256/tamanho e lista o conteúdo do ZIP.
"""
import hashlib
import io
import json
import os
import sys
import zipfile

from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

CREDENTIALS = r"D:\Projetos\credentials.json"
TOKEN = r"D:\Projetos\token.json"


def verify_download(data: bytes, manifest: dict) -> dict:
    """Confere sha256/tamanho e inspeciona o ZIP. Retorna um relatório."""
    report = {
        "downloaded_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "sha256_matches": hashlib.sha256(data).hexdigest() == manifest["sha256"],
        "size_matches": len(data) == manifest["size"],
    }
    archive = zipfile.ZipFile(io.BytesIO(data))
    names = archive.namelist()
    report["member_count"] = len(names)
    report["members"] = sorted(names)
    report["largest"] = sorted(
        ((info.file_size, info.filename) for info in archive.infolist()),
        reverse=True,
    )[:5]
    return report


def download_zip(service, file_id: str) -> bytes:
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def main() -> int:
    manifest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "release", "latest.json")
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    if not os.path.exists(TOKEN):
        print("token não encontrado em", TOKEN, file=sys.stderr)
        return 2
    creds = Credentials.from_authorized_user_file(TOKEN)
    service = build("drive", "v3", credentials=creds)
    print("manifest version:", manifest["version"])
    print("zip_file_id:", manifest["zip_file_id"])
    print("expected sha256:", manifest["sha256"])
    print("expected size:", manifest["size"])
    try:
        data = download_zip(service, manifest["zip_file_id"])
    except RefreshError as exc:
        print(
            "ERRO: token do Drive expirado/inválido. "
            f"Gere um novo com `drive_upload.py auth` e tente de novo. ({exc})",
            file=sys.stderr,
        )
        return 3
    report = verify_download(data, manifest)
    for key, value in report.items():
        print(f"{key}: {value}")
    return 0 if (report["sha256_matches"] and report["size_matches"]) else 1


if __name__ == "__main__":
    sys.exit(main())
