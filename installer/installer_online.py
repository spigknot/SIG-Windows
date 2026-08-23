"""Instalador online do SIG Windows.

Abre com um botão "Baixar"; nada é baixado até o usuário clicar. Ao clicar,
baixa os arquivos do Cloudflare R2 (sync_manifest.json schema 2 assinado, um
arquivo por vez com SHA-256 e contador "Arquivo X de N") — fallback: pacote
full da última release do GitHub. Instala em C:\\Program Files\\SIG com
atalhos, sem pacote embutido.

O Google Drive foi APOSENTADO como fonte (desde a versão 20260821_013); o
manifesto e os arquivos vivem no Cloudflare R2.

Build: PyInstaller --onefile --windowed --uac-admin (o UAC pede admin antes
da janela; a instalação em Program Files exige elevação).
"""

import base64
import hashlib
import json
import os
import queue
import re
import shutil
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

GITHUB_API = "https://api.github.com/repos/spigknot/SIG-Windows/releases/latest"
R2_PUBLIC_HOST = "pub-abb3913e7d83457bae19e41b1e4020cc.r2.dev"
R2_MANIFEST_URL = f"https://{R2_PUBLIC_HOST}/sync_manifest.json"
# O R2.dev responde HTTP 1010 para User-Agent de bot (urllib) — usar o mesmo
# UA do SigUpdater, já liberado no bucket.
HTTP_USER_AGENT = "SigUpdater/2.0 (+https://github.com/spigknot/SIG-Windows)"
APP_DIR = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "SIG"
STAGING_DIR = Path(os.environ.get("TEMP", r"C:\Windows\Temp")) / "sig_installer_online"

SYNC_MANIFEST_SCHEMA = 2
SYNC_MANIFEST_MAX_BYTES = 2 * 1024 * 1024
SYNC_MANIFEST_MAX_FILES = 20_000
VERSION_RE = re.compile(r"^\d{8}_\d{3}$")

# Chave pública de verificação do manifesto (a privada nunca sai da máquina de
# publicação). Cópia embutida de propósito: o instalador NÃO importa módulos do
# app/updater (o PyInstaller onefile empacota só o que é importado estaticamente).
UPDATE_PUBLIC_KEY_E = 65537
UPDATE_PUBLIC_KEY_N = 4776833754672109710666015745718377295826954378034957006723781632230794955188598743370375368759247701138572196632244506341860738985196771222328276471293164426045586502411553661270415658303449836000240060850077943629529298365455842583839584430835872888082421190431050761740593243172708805858229100494995424042846759167936558524923889093025581721886390801543158714477942628958659907698645218405072643039190789807520623959789948760663039915934233343926084287154817842449929074144135976678727267978353880303189583548982201552861178437687569977746462198133228741460769839629249527122404198789341588724117695515639417887297249072695071299249800470626986276226209694407865386128033982643621030612265330884993509358887003353611841249193688390145075540912405754224137641702769971761374974256331506313629217304424829655209764530396523158905317988087656296751937468490602949770457129034644632659661248617309294539893653236376299080388523


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
    """Payload canônico assinado do manifesto de sincronização (schema 2).

    Precisa bater byte a byte com src/sync_common.py — qualquer divergência
    quebra a verificação da assinatura.
    """
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


def fetch_r2_manifest() -> dict:
    """Baixa e valida o sync_manifest.json (schema 2) publicado no R2."""
    request = urllib.request.Request(R2_MANIFEST_URL, headers={"User-Agent": HTTP_USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(SYNC_MANIFEST_MAX_BYTES + 1)
    if len(body) > SYNC_MANIFEST_MAX_BYTES:
        raise RuntimeError("O manifesto do R2 excede o tamanho permitido.")
    try:
        manifest = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as error:
        raise RuntimeError("O manifesto do R2 não é um JSON válido.") from error
    if not isinstance(manifest, dict):
        raise RuntimeError("O manifesto do R2 não é um objeto JSON.")
    if int(manifest.get("schema") or 0) != SYNC_MANIFEST_SCHEMA:
        raise RuntimeError("O manifesto do R2 não usa o schema esperado.")
    if not _verify_rsa_sha256_signature(
        str(manifest.get("signature") or ""), canonical_sync_manifest(manifest)
    ):
        raise RuntimeError("O manifesto do R2 não possui assinatura válida.")
    version = str(manifest.get("version") or "")
    if not VERSION_RE.fullmatch(version):
        raise RuntimeError("O manifesto do R2 contém uma versão inválida.")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise RuntimeError("O manifesto do R2 não lista arquivos.")
    if len(raw_files) > SYNC_MANIFEST_MAX_FILES:
        raise RuntimeError("O manifesto do R2 excede o limite de arquivos.")
    return manifest


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _github_full_asset_url() -> str:
    """URL do asset ..._full.zip da última release do GitHub."""
    request = urllib.request.Request(
        GITHUB_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "sig-installer-online"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))
    for asset in data.get("assets", []):
        if asset["name"].endswith("_full.zip"):
            return asset["browser_download_url"]
    raise RuntimeError("Nenhum pacote full encontrado na última release do GitHub.")


def _download_with_progress(url: str, destination: Path, progress_callback) -> None:
    """Baixa com barra de progresso (Content-Length quando disponível)."""
    request = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        with open(destination, "wb") as output:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    progress_callback(downloaded, total)
                else:
                    progress_callback(downloaded, downloaded or 1)
    progress_callback(destination.stat().st_size, destination.stat().st_size)


class InstallerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.staged_zip: Path | None = None
        self.staged_files: list[Path] | None = None
        self.source: str = ""  # "r2" | "github"
        self.download_started = False
        self.download_ok = False
        self._messages: queue.Queue = queue.Queue()
        root.title("SIG — Instalação online")
        root.geometry("560x280")
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Instalação do SIG", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.status_var = tk.StringVar(value="Clique em Baixar para iniciar o download.")
        ttk.Label(frame, textvariable=self.status_var, wraplength=520).pack(anchor="w", pady=(6, 10))
        self.progress = ttk.Progressbar(frame, maximum=100, mode="determinate")
        self.progress.pack(fill="x")
        progress_info = ttk.Frame(frame)
        progress_info.pack(fill="x", pady=(2, 0))
        self.counter_var = tk.StringVar(value="")
        ttk.Label(progress_info, textvariable=self.counter_var).pack(side="left")
        self.percent_var = tk.StringVar(value="")
        ttk.Label(progress_info, textvariable=self.percent_var).pack(side="right")
        self.action_button = ttk.Button(frame, text="Baixar", command=self._on_action_button)
        self.action_button.pack(anchor="e", pady=(14, 0))
        ttk.Label(
            frame,
            text="O download é feito uma única vez e a instalação fica em "
            f"{APP_DIR}.",
            foreground="#555",
        ).pack(anchor="w", pady=(12, 0))
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(100, self._poll)

    # -- Botão único: Baixar -> (download) -> Instalar ---------------------

    def _on_action_button(self):
        if self.download_ok:
            self._start_install()
        else:
            self._start_download()

    def _start_download(self):
        self.download_started = True
        self.download_ok = False
        self.source = ""
        self.action_button.configure(state="disabled", text="Baixando...")
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _on_close(self):
        if self.download_started and not self.download_ok:
            if not messagebox.askyesno("SIG", "Cancelar o download e fechar?"):
                return
        self.root.destroy()

    def _report(self, status: str, percent: float, counter: str = ""):
        self._messages.put((status, percent, counter))

    def _poll(self):
        try:
            while True:
                message = self._messages.get_nowait()
                if isinstance(message, tuple) and message[0] == "ENABLE":
                    self.action_button.configure(state="normal", text="Instalar")
                    continue
                if isinstance(message, tuple) and message[0] == "FAIL":
                    self.action_button.configure(state="normal", text="Baixar")
                    messagebox.showerror(
                        "SIG", f"Não foi possível baixar o pacote:\n{message[1]}"
                    )
                    continue
                if isinstance(message, tuple) and message[0] == "FAIL_INSTALL":
                    self.action_button.configure(text="Instalar")
                    self.action_button.configure(state="normal")
                    messagebox.showerror(
                        "SIG", f"Não foi possível instalar:\n{message[1]}"
                    )
                    continue
                if isinstance(message, tuple) and message[0] == "DONE":
                    app_dir = message[1]
                    self.status_var.set("SIG instalado com sucesso.")
                    try:
                        import subprocess
                        subprocess.Popen([str(Path(app_dir) / "sig.exe")], cwd=str(app_dir))
                    except Exception:
                        pass
                    messagebox.showinfo("SIG", f"SIG instalado em {app_dir}.")
                    self.root.destroy()
                    continue
                status, percent, counter = message
                self.status_var.set(status)
                self.progress["value"] = percent
                self.percent_var.set(f"{round(percent)}%")
                self.counter_var.set(counter)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    # -- Download: R2 (por arquivo) com fallback no GitHub (full.zip) ------

    def _download_worker(self):
        if self._download_from_r2():
            return
        self._download_from_github()

    def _download_from_r2(self) -> bool:
        try:
            self._report("Localizando a versão atual no Cloudflare R2...", 1, "")
            manifest = fetch_r2_manifest()
            version = str(manifest.get("version") or "")
            entries = [
                entry for entry in manifest.get("files") or []
                if isinstance(entry, dict)
                and str(entry.get("path") or "")
                and str(entry.get("github_url") or "")
            ]
            if not entries:
                raise RuntimeError("Manifesto do R2 sem arquivos para baixar.")
            entries.sort(key=lambda entry: str(entry["path"]))
            total = len(entries)
            STAGING_DIR.mkdir(parents=True, exist_ok=True)
            self.staged_files = []
            for index, entry in enumerate(entries):
                path = str(entry["path"])
                destination = STAGING_DIR / "sync" / Path(*path.split("/"))
                destination.parent.mkdir(parents=True, exist_ok=True)
                self._download_r2_file(
                    str(entry["github_url"]), destination, path, index, total
                )
                digest = _sha256_file(destination)
                if digest.lower() != str(entry.get("sha256") or "").lower():
                    raise RuntimeError(f"SHA-256 divergente ao baixar: {path}")
                self.staged_files.append(destination)
            self.source = "r2"
            self.download_ok = True
            self._report(
                f"Download concluído (versão {version}) — clique em Instalar.", 100, ""
            )
            self._messages.put(("ENABLE",))
            return True
        except Exception as error:
            import traceback
            detail = traceback.format_exc(limit=4)
            print(detail, file=sys.stderr)
            self._report(
                f"R2 indisponível ({type(error).__name__}); tentando o GitHub...", 2, ""
            )
            return False

    def _download_r2_file(
        self, url: str, destination: Path, path: str, index: int, total: int
    ) -> None:
        def _progress(downloaded: int, file_total: int) -> None:
            fraction = downloaded / max(file_total, 1)
            self._report(
                f"Baixando {path}",
                2 + 96 * (index + fraction) / total,
                f"Arquivo {index + 1}/{total}",
            )

        try:
            _download_with_progress(url, destination, _progress)
        except Exception:
            # Uma tentativa extra por arquivo: com ~1,8 mil downloads, uma
            # falha transitória de rede não deveria abortar a instalação.
            _download_with_progress(url, destination, _progress)

    def _download_from_github(self) -> None:
        try:
            self._report("Localizando o pacote mais recente no GitHub...", 2, "")
            full_url = _github_full_asset_url()
            self._report("Baixando o pacote do GitHub...", 3, "")
            STAGING_DIR.mkdir(parents=True, exist_ok=True)
            self.staged_zip = STAGING_DIR / "sig_full.zip"
            _download_with_progress(
                full_url, self.staged_zip, lambda d, t: self._report(
                    "Baixando o pacote do GitHub...", 3 + 95 * d / t, ""
                )
            )
            self.source = "github"
            self.download_ok = True
            self._report("Download concluído — clique em Instalar.", 100, "")
            self._messages.put(("ENABLE",))
        except Exception as error:
            import traceback
            detail = traceback.format_exc(limit=4)
            print(detail, file=sys.stderr)
            self._report(f"Falha no download: {error}", 0, "")
            self._messages.put(("FAIL", f"{error}\n{detail}"))

    # -- Instalação ---------------------------------------------------------

    def _start_install(self):
        self.action_button.configure(state="disabled")
        self.action_button.configure(text="Instalando...")
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self):
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass
            self._report("Extraindo os arquivos...", 5, "")
            if self.source == "r2":
                source_root = STAGING_DIR / "sync"
            else:
                if self.staged_zip is None or not self.staged_zip.exists():
                    raise RuntimeError("Pacote baixado não encontrado.")
                with zipfile.ZipFile(self.staged_zip) as archive:
                    archive.extractall(STAGING_DIR / "extracted")
                source_root = STAGING_DIR / "extracted"
            APP_DIR.mkdir(parents=True, exist_ok=True)
            files = [item for item in source_root.rglob("*") if item.is_file()]
            total = max(len(files), 1)
            for index, item in enumerate(files):
                relative = item.relative_to(source_root)
                target = APP_DIR / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
                self._report(
                    "Instalando...",
                    5 + 85 * (index + 1) / total,
                    f"Arquivo {index + 1}/{total}",
                )
            self._report("Criando os atalhos...", 92, "")
            self._create_shortcuts()
            self._report("Instalação concluída!", 100, "")
            self._messages.put(("DONE", str(APP_DIR)))
        except Exception as error:
            self._messages.put(("FAIL_INSTALL", str(error)))

    def _create_shortcuts(self):
        import win32com.client  # pywin32

        shell = win32com.client.Dispatch("WScript.Shell")
        desktop = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"
        start_menu = (
            Path(os.environ.get("ProgramData", r"C:\ProgramData"))
            / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "SIG"
        )
        start_menu.mkdir(parents=True, exist_ok=True)
        targets = [
            (APP_DIR / "sig.exe", "SIG"),
            (APP_DIR / "SigUpdater.exe", "SigUpdater"),
        ]
        for executable, label in targets:
            for folder in (desktop, start_menu):
                shortcut = shell.CreateShortCut(str(folder / f"{label}.lnk"))
                shortcut.TargetPath = str(executable)
                shortcut.WorkingDirectory = str(APP_DIR)
                shortcut.Save()
        desktop.mkdir(parents=True, exist_ok=True)


def main():
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
