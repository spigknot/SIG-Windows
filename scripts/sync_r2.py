#!/usr/bin/env python3
"""Publica a pasta sync no Cloudflare R2 (S3) e gera o sync_manifest.json (schema 2).

Uso:
    python scripts/sync_r2.py --package release/generated/<VERSAO>/package --version <VERSAO>

Credenciais em release/r2_config.json (NUNCA commitar).
"""
import argparse
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from sync_publish import snapshot, sign_manifest  # noqa: E402

import boto3  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True, help="pasta onedir full (ex.: .../package)")
    ap.add_argument("--version", required=True, help="versão do manifesto (ex.: 20260821_013)")
    args = ap.parse_args()

    cfg_path = ROOT / "release" / "r2_config.json"
    if not cfg_path.is_file():
        raise SystemExit("release/r2_config.json não encontrado (credenciais do R2)")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    package = pathlib.Path(args.package)
    if not package.is_dir():
        raise SystemExit(f"pasta do pacote não encontrada: {package}")

    files = snapshot(package)
    print(f"pacote: {len(files)} arquivos")

    s3 = boto3.client(
        "s3",
        endpoint_url=cfg["endpoint"],
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        region_name="auto",
    )
    bucket = cfg["bucket"]
    public_base = cfg["public_base"].rstrip("/")


    def _md5(path: pathlib.Path) -> str:
        digest = hashlib.md5()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


    def _remote_etag(key: str) -> str:
        try:
            head = s3.head_object(Bucket=bucket, Key=key)
            return str(head.get("ETag") or "").strip('"')
        except s3.exceptions.ClientError:
            return ""


    # Diff por hash: uma única listagem (ETags) vs o MD5 local — sobe só o que mudou
    remote_etags: dict[str, str] = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            remote_etags[str(obj["Key"])] = str(obj.get("ETag") or "").strip('"')
    to_upload = {}
    for path, entry in files.items():
        if remote_etags.get(path) != _md5(package / path):
            to_upload[path] = entry

    print(f"subir: {len(to_upload)}")
    for index, (path, entry) in enumerate(to_upload.items(), 1):
        with (package / path).open("rb") as handle:
            s3.put_object(Bucket=bucket, Key=path, Body=handle)
        if index % 25 == 0 or index == len(to_upload):
            print(f"  upload {index}/{len(to_upload)}")
    print("upload concluído")

    # Manifesto (schema 2 — o formato validado pelo updater)
    manifest = {
        "schema": 2,
        "version": args.version,
        "files": [
            {
                "path": path,
                "sha256": entry["sha256"],
                "size": entry["size"],
                "drive_id": "",
                "github_url": f"{public_base}/{path}",
            }
            for path, entry in files.items()
        ],
    }
    sign_manifest(manifest)
    body = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    s3.put_object(Bucket=bucket, Key="sync_manifest.json", Body=body, ContentType="application/json")
    print("sync_manifest.json publicado no R2")


if __name__ == "__main__":
    main()
