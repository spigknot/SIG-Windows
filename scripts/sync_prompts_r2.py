#!/usr/bin/env python3
"""Publica a pasta prompts/ no bucket R2 `prompts`.

DOIS escopos distintos (decisao do dono, 29/09/2026):

* UPLOAD — TODOS os `.txt` de `prompts/`, incluindo `prompts_antigos/`:
  o bucket tambem serve de backup dos prompts antigos e de fonte para o
  SIG Windows, que vai consumir os demais prompts de la.
* DOWNLOAD no app (SIG Windows, tela Configuracoes > Prompts) — TODOS os
  `.txt` da RAIZ de `prompts/` (9: historico, oitiva, qualificacao e partes);
  a subpasta `prompts_antigos/` e ignorada.

Este script tambem publica `manifest.json` (sha256 de cada arquivo da raiz).
Com ele o botao "baixar prompts atualizados" do app decide em UM request se
ha versao nova; sem manifesto ele so descobre baixando os 9 e comparando.

Importante: o manifesto e sempre reescrito a partir do que esta sendo
publicado agora. Um manifesto envelhecido faria o app responder "ja esta
atualizado" e NAO baixar um prompt novo — por isso ele nunca e enviado sozinho.

A verificacao final baixa de volta por `public_base` e confere o sha256 de
TUDO que foi publicado — um upload que o app nao consegue ler nao e PASS.

Uso:
    python scripts/sync_prompts_r2.py            # sobe o que mudou + verifica
    python scripts/sync_prompts_r2.py --check    # so compara (nada sobe)
    python scripts/sync_prompts_r2.py --quiet    # uma linha de resumo

Credenciais em release/r2_prompts_config.json (NUNCA commitar).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Contrato de download do app: TODOS os .txt da RAIZ de prompts/ (a subpasta
# prompts_antigos/ e backup e nunca chega ao app).
APP_PROMPT_FILES = (
    "historico_system.txt",
    "historico_user.txt",
    "oitiva_system.txt",
    "oitiva_user.txt",
    "qualificacao_system.txt",
    "qualificacao_user.txt",
    "partes_system.txt",
    "partes_user_botao_historico.txt",
    "partes_user_botao_detectar.txt",
)

#: Nome do manifesto de hashes publicado junto dos prompts.
MANIFEST_NAME = "manifest.json"

# Marcadores que o app substitui a cada requisicao: sem eles o prompt baixado
# quebraria o fluxo em silencio (o texto chegaria com o marcador cru).
REQUIRED_MARKERS = {
    "historico_user.txt": "{{conteudo_caixa_transcricao}}",
    "oitiva_user.txt": "{{{conteudo_caixa_historico}}}",
    "qualificacao_user.txt": "{{{TEXTO_DA_CAIXA_AQUI}}}",
}

MAX_PROMPT_BYTES = 64 * 1024

# O r2.dev bloqueia o UA padrao do urllib (HTTP 1010 — pitfall do UPDATE.md).
PUBLIC_UA = "SIG-PromptsSync/1.0 (+https://github.com/spigknot/SIG-Windows)"


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_prompt(key: str, data: bytes) -> str:
    """Retorna '' quando o prompt e publicavel, senao o motivo."""
    if not data:
        return "arquivo vazio"
    if len(data) > MAX_PROMPT_BYTES:
        return f"tamanho {len(data)} acima do limite de {MAX_PROMPT_BYTES} bytes"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return f"nao e UTF-8 valido ({exc})"
    if not text.strip():
        return "conteudo em branco"
    # O marcador so e exigido na raiz (chave exata): os arquivos da subpasta
    # prompts_antigos/ sao backup e nao passam pelo contrato do app.
    marker = REQUIRED_MARKERS.get(key)
    if marker and marker not in text:
        return f"falta o marcador {marker}"
    return ""


def load_config(path: pathlib.Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"{path} nao encontrado (credenciais do bucket prompts)")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    missing = [key for key in ("endpoint", "access_key_id", "secret_access_key", "bucket", "public_base") if not cfg.get(key)]
    if missing:
        raise SystemExit(f"{path}: chaves obrigatorias ausentes: {', '.join(missing)}")
    return cfg


def collect_prompts(prompts_dir: pathlib.Path) -> dict[str, bytes]:
    """Todos os .txt da pasta; a chave e o caminho relativo posix (subpasta preservada).

    O conteudo e gravado em LF: o Windows pode ter CRLF no disco, e publicar
    assim faria o app ver "prompts alterados" num PC recem instalado, quando
    o texto e exatamente o mesmo. O `manifest.json` e calculado sobre estes
    mesmos bytes, entao manifesto e conteudo nunca divergem.
    """
    if not prompts_dir.is_dir():
        raise SystemExit(f"pasta de prompts nao encontrada: {prompts_dir}")
    files: dict[str, bytes] = {}
    for path in sorted(prompts_dir.rglob("*.txt"), key=lambda item: item.as_posix().casefold()):
        if path.is_file():
            texto = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            files[path.relative_to(prompts_dir).as_posix()] = texto
    missing = [name for name in APP_PROMPT_FILES if name not in files]
    if missing:
        raise SystemExit(f"prompts do app ausentes: {', '.join(missing)}")
    return files


def build_manifest(local: dict[str, bytes]) -> bytes:
    """`manifest.json` com o sha256 de cada arquivo da RAIZ que o app baixa.

    E sempre derivado dos bytes que estao sendo publicados agora — um manifesto
    escrito a mao e o jeito mais facil de o app recusar uma versao nova.
    """
    payload = {
        "schema": 1,
        "bucket": "prompts",
        "descricao": "Hashes dos prompts da raiz; a subpasta prompts_antigos/ nao entra (backup).",
        "files": {name: sha256_hex(local[name]) for name in APP_PROMPT_FILES if name in local},
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def fetch_public(public_base: str, name: str) -> bytes:
    request = urllib.request.Request(f"{public_base.rstrip('/')}/{name}", headers={"User-Agent": PUBLIC_UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="so compara local x R2 (nao sobe nada)")
    parser.add_argument("--quiet", action="store_true", help="uma unica linha de resumo")
    args = parser.parse_args()

    cfg = load_config(ROOT / "release" / "r2_prompts_config.json")
    local = collect_prompts(ROOT / "prompts")

    problems = {name: error for name, data in local.items() if (error := validate_prompt(name, data))}
    if problems:
        detail = "; ".join(f"{name}: {error}" for name, error in problems.items())
        raise SystemExit(f"prompts locais reprovados na validacao: {detail}")

    # Importado aqui (e não no topo) para que os testes rodem sem boto3 instalado.
    import boto3  # noqa: PLC0415

    s3 = boto3.client(
        "s3",
        endpoint_url=cfg["endpoint"],
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        region_name="auto",
    )
    bucket = cfg["bucket"]
    if bucket != "prompts":
        raise SystemExit(f"bucket inesperado em release/r2_prompts_config.json: {bucket!r} (esperado 'prompts')")

    remote_etags: dict[str, str] = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            remote_etags[str(obj["Key"])] = str(obj.get("ETag") or "").strip('"')

    to_upload = [key for key in local if remote_etags.get(key) != md5_hex(local[key])]
    uploaded = 0
    if not args.check:
        for name in to_upload:
            s3.put_object(
                Bucket=bucket,
                Key=name,
                Body=local[name],
                ContentType="text/plain; charset=utf-8",
            )
            uploaded += 1
        # O manifesto vai SEMPRE, mesmo sem prompt alterado: ele e o que permite
        # ao app responder "ja atualizado" em um request. Reenviar um manifesto
        # identico nao muda nada no bucket.
        manifest = build_manifest(local)
        s3.put_object(
            Bucket=bucket,
            Key=MANIFEST_NAME,
            Body=manifest,
            ContentType="application/json; charset=utf-8",
            CacheControl="no-cache",
        )

    # Verificacao publica: o app le por public_base; se nao voltar igual, nao serve.
    failures: list[str] = []
    if not args.check:
        for key in local:
            try:
                served = fetch_public(cfg["public_base"], key)
            except Exception as exc:  # noqa: BLE001 - qualquer erro aqui e bloqueio
                failures.append(f"{key}: download publico falhou ({exc})")
                continue
            if sha256_hex(served) != sha256_hex(local[key]):
                failures.append(f"{key}: conteudo publicado difere do local")
    if failures:
        raise SystemExit("verificacao publica reprovada: " + "; ".join(failures))

    unchanged = len(local) - uploaded
    if args.check:
        pending = ", ".join(to_upload) if to_upload else "nenhum"
        if args.quiet:
            print(f"CHECK: sync-prompts pendentes={len(to_upload)} de {len(local)} ({pending})")
        else:
            print(f"pendentes de upload ({len(to_upload)} de {len(local)}): {pending}")
        return
    if args.quiet:
        print(
            f"PASS: sync-prompts bucket={bucket} uploaded={uploaded} unchanged={unchanged} "
            f"verified={len(local)} app_files={len(APP_PROMPT_FILES)}"
        )
    else:
        print(f"subir: {uploaded}")
        for key in to_upload:
            print(f"  enviado {key} sha256={sha256_hex(local[key])[:16]}…")
        print(f"inalterados: {unchanged}")
        print(f"verificado no URL publico: {len(local)}/{len(local)}")
        print(f"escopo de download do app: {', '.join(APP_PROMPT_FILES)}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: sync-prompts: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
