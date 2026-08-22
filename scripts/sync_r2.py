#!/usr/bin/env python3
"""Publica a pasta sync no Cloudflare R2 (S3) e gera o sync_manifest.json (schema 2).

Uso:
    python scripts/sync_r2.py --package release/generated/<VERSAO>/package --version <VERSAO>

Credenciais em release/r2_config.json (NUNCA commitar).
"""
import argparse
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

    # Upload S3 (idempotente — sobrescreve por path)
    for index, (path, entry) in enumerate(files.items(), 1):
        with (package / path).open("rb") as handle:
            s3.put_object(Bucket=bucket, Key=path, Body=handle)
        if index % 25 == 0 or index == len(files):
            print(f"  upload {index}/{len(files)}")
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
