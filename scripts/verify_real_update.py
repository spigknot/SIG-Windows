"""Teste real da seção 7.4 do UPDATE.md: atualização por sincronização do R2.

Baixa o diff publicado no R2 e o aplica com o `SigUpdater.exe` real numa CÓPIA
de uma instalação existente (por padrão `C:\\Program Files\\SIG`). A instalação
de origem nunca é modificada: o updater roda contra a cópia em `%TEMP%`.

Percorre exatamente o caminho que o app usa:

    sync_common.validate_sync_manifest   valida schema e assinatura digital
    sync_common.classify_sync_files      diff da instalação local x manifesto
    documents.download_github_url        download com retries
    SigUpdater.exe --sync-staged ...     aplica, valida a inicialização e relança

Uso:

    python scripts/verify_real_update.py [--install CAMINHO] [--work DIR]
                                         [--keep] [--timeout SEGUNDOS]

Saída: relatório linha a linha terminando em `RESULTADO: PASS` (exit 0) ou
`RESULTADO: FAIL` (exit 1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "SigUpdater/2.0 (+https://github.com/spigknot/SIG-Windows)"
DEFAULT_INSTALL = Path(r"C:\Program Files\SIG")

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "updater_v2"))
sys.path.insert(0, str(ROOT / "scripts"))

from sync_common import R2_PUBLIC_HOST, classify_sync_files, sha256_file, validate_sync_manifest
from release import frozen_app_version

try:  # mesmo downloader do app; fallback para urllib se o import falhar
    from documents import download_github_url as _app_download
except Exception as exc:  # pragma: no cover - defensivo
    _app_download = None
    _DOWNLOAD_FALLBACK_REASON = str(exc)
else:
    _DOWNLOAD_FALLBACK_REASON = ""


def log(message: str) -> None:
    print(message, flush=True)


def download(url: str, destination: Path) -> str:
    if _app_download is not None:
        return _app_download(url, destination)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return sha256_file(destination)


def settings_hash() -> str:
    """Hash curto do settings.json do usuário, para provar que não foi tocado."""
    path = Path.home() / "AppData" / "Roaming" / "SIG" / "settings.json"
    if not path.is_file():
        return "ausente"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def stop_copy_processes(target: Path) -> None:
    escaped = str(target / "sig.exe").replace("'", "''")
    command = (
        "$t = '" + escaped + "'; "
        "Get-CimInstance Win32_Process -Filter \"Name = 'sig.exe'\" | "
        "Where-Object { $_.ExecutablePath -and $_.ExecutablePath -ieq $t } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        check=False,
        creationflags=getattr(subprocess, "CREATE_WINDOWLESS", 0) or getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--install", type=Path, default=DEFAULT_INSTALL, help="instalação de origem (somente leitura)")
    parser.add_argument("--work", type=Path, default=Path(tempfile.gettempdir()) / "sig_real_update_test")
    parser.add_argument("--keep", action="store_true", help="não apagar o diretório de trabalho no fim")
    parser.add_argument("--timeout", type=int, default=600, help="timeout do updater em segundos")
    args = parser.parse_args()

    install: Path = args.install
    work: Path = args.work
    if not (install / "sig.exe").is_file():
        log(f"FALHOU: instalação de origem inválida (sem sig.exe): {install}")
        return 1

    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq sig.exe"],
        capture_output=True,
        text=True,
        encoding="cp1252",
        errors="replace",
    ).stdout
    log("[0] sig.exe do usuario rodando: " + ("SIM (feche antes do teste)" if "sig.exe" in (out or "").lower() else "nao"))
    log("[0] downloader: " + ("documents.download_github_url (mesma do app)" if _app_download else f"urllib ({_DOWNLOAD_FALLBACK_REASON})"))
    log("[0] hash settings.json antes: " + settings_hash())

    target = work / "target"
    if work.exists():
        shutil.rmtree(work)
    target.parent.mkdir(parents=True, exist_ok=True)
    log(f"[1] copiando {install} -> {target} ...")
    shutil.copytree(install, target)
    log(f"[1] copiados {sum(1 for p in target.rglob('*') if p.is_file())} arquivos")
    log(f"[1] versao antes = {frozen_app_version(target / 'sig.exe')}")

    request = urllib.request.Request(
        f"https://{R2_PUBLIC_HOST}/sync_manifest.json", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        manifest = json.loads(response.read().decode("utf-8"))
    state = validate_sync_manifest(manifest)
    log(f"[2] manifesto R2 validado (assinatura OK): versao={state['version']} arquivos={len(state['files'])}")

    classification = classify_sync_files(target, state["files"])
    log(
        f"[3] diff: download={len(classification['download'])} remove={len(classification['remove'])} "
        f"unchanged={classification['unchanged']} total={classification['total']}"
    )
    for rel in classification["download"]:
        log(f"    baixar: {rel}")
    for rel in classification["remove"]:
        log(f"    remover: {rel}")

    staged = work / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    for rel in classification["download"]:
        entry = state["files"][rel]
        destination = staged.joinpath(*rel.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = download(entry["github_url"], destination)
        if digest.lower() != entry["sha256"]:
            log(f"FALHOU: sha256 divergente em {rel}: {digest} != {entry['sha256']}")
            return 1
        log(f"[4] baixado e verificado: {rel} ({entry['size']} bytes)")

    removals = work / "removals.txt"
    removals.write_text(
        "\n".join(classification["remove"]) + ("\n" if classification["remove"] else ""), encoding="utf-8"
    )

    staged_updater = staged / "SigUpdater.exe"
    updater = staged_updater if staged_updater.is_file() else target / "SigUpdater.exe"
    log_file = target / "updater.log"
    command = [
        str(updater),
        "--sync-staged", str(staged),
        "--sync-removals", str(removals),
        "--sync-version", state["version"],
        "--target", str(target),
        "--log", str(log_file),
        "--startup-timeout", "12",
    ]
    log("[5] executando: " + " ".join(command))
    completed = subprocess.run(command, timeout=args.timeout)
    log(f"[5] exit code do updater: {completed.returncode}")

    text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.is_file() else ""
    ok_log = "Atualização aplicada e validada." in text
    after = frozen_app_version(target / "sig.exe")
    info_version = ""
    info = target / "build-info.json"
    if info.is_file():
        try:
            info_version = str(json.loads(info.read_text(encoding="utf-8")).get("version", ""))
        except Exception as exc:
            info_version = f"erro: {exc}"
    log(f"[6] log contem 'Atualizacao aplicada e validada.': {ok_log}")
    log(f"[6] versao depois = {after} | build-info.json = {info_version}")
    log("[6] trecho do updater.log:")
    for line in text.splitlines()[-6:]:
        log("      " + line)

    stop_copy_processes(target)
    log("[7] copia encerrada")
    log(f"[7] versao da instalacao de origem (intacta): {frozen_app_version(install / 'sig.exe')}")
    log("[7] hash settings.json depois: " + settings_hash())

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)

    passed = (
        completed.returncode == 0
        and ok_log
        and after == state["version"]
        and info_version == state["version"]
    )
    log("RESULTADO: " + ("PASS" if passed else "FAIL"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
