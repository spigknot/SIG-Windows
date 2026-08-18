"""Instalador online do SIG Windows.

Baixa o pacote full da última release do GitHub (fallback: pasta sync do
Drive) e instala em C:\\Program Files\\SIG com atalhos, sem pacote embutido.

Build: PyInstaller --onefile --windowed --uac-admin (o UAC pede admin antes
da janela; a instalação em Program Files exige elevação).
"""

import json
import hashlib
import os
import queue
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
SYNC_MANIFEST_FILE_ID = "1FiuZNZ6Ylub7P10vecwV29UNntoOkySw"
DRIVE_DOWNLOAD_URL = "https://drive.usercontent.google.com/download"
GITHUB_RAW_FALLBACK = "https://raw.githubusercontent.com/spigknot/SIG-Windows/main/updater_v2/updater.py"
APP_DIR = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "SIG"
STAGING_DIR = Path(os.environ.get("TEMP", r"C:\Windows\Temp")) / "sig_installer_online"


def _drive_url(file_id: str) -> str:
    return f"{DRIVE_DOWNLOAD_URL}?id={file_id}&export=download"


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
    request = urllib.request.Request(url, headers={"User-Agent": "sig-installer-online"})
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


def _download_google_drive_file(file_id: str, destination: Path, progress_callback) -> None:
    """Baixa um arquivo da pasta sync do Drive (fallback do GitHub)."""
    url = _drive_url(file_id)
    request = urllib.request.Request(url, headers={"User-Agent": "sig-installer-online"})
    with urllib.request.urlopen(request, timeout=60) as response:
        final_url = response.geturl()
        content_length = int(response.headers.get("Content-Length") or 0)
        # O Google pode redirecionar para a confirmação de virus scan (download).
        if "confirm" in final_url:
            request = urllib.request.Request(final_url, headers={"User-Agent": "sig-installer-online"})
            with urllib.request.urlopen(request, timeout=60) as response2:
                response = response2
                content_length = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        with open(destination, "wb") as output:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if content_length > 0:
                    progress_callback(downloaded, content_length)
                else:
                    progress_callback(downloaded, downloaded or 1)


class InstallerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.staged_zip: Path | None = None
        self.staged_files: list[Path] | None = None
        self.download_ok = False
        self._messages: queue.Queue = queue.Queue()
        root.title("SIG — Instalação online")
        root.geometry("560x260")
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Baixando o SIG...", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.status_var = tk.StringVar(value="Conectando ao GitHub...")
        ttk.Label(frame, textvariable=self.status_var, wraplength=520).pack(anchor="w", pady=(6, 10))
        self.progress = ttk.Progressbar(frame, maximum=100, mode="determinate")
        self.progress.pack(fill="x")
        self.percent_var = tk.StringVar(value="0%")
        ttk.Label(frame, textvariable=self.percent_var).pack(anchor="e", pady=(2, 0))
        self.install_button = ttk.Button(
            frame, text="Instalar", state="disabled", command=self.install
        )
        self.install_button.pack(anchor="e", pady=(14, 0))
        ttk.Label(
            frame,
            text="O download é feito uma única vez e a instalação fica em "
            f"{APP_DIR}.",
            foreground="#555",
        ).pack(anchor="w", pady=(12, 0))
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=self._download_worker, daemon=True).start()
        root.after(100, self._poll)

    def _on_close(self):
        if self.download_ok or messagebox.askyesno(
            "SIG", "Cancelar o download e fechar?"
        ):
            self.root.destroy()

    def _report(self, status: str, percent: float):
        self._messages.put((status, percent))

    def _poll(self):
        try:
            while True:
                message = self._messages.get_nowait()
                if isinstance(message, tuple) and message[0] == "ENABLE":
                    self.install_button.configure(state="normal")
                    continue
                if isinstance(message, tuple) and message[0] == "FAIL":
                    self.install_button.configure(state="disabled")
                    messagebox.showerror(
                        "SIG", f"Não foi possível baixar o pacote:\n{message[1]}"
                    )
                    continue
                status, percent = message
                self.status_var.set(status)
                self.progress["value"] = percent
                self.percent_var.set(f"{round(percent)}%")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _download_worker(self):
        try:
            STAGING_DIR.mkdir(parents=True, exist_ok=True)
            self._report("Localizando o pacote mais recente no GitHub...", 1)
            full_url = _github_full_asset_url()
            self._report("Baixando o pacote do GitHub...", 2)
            self.staged_zip = STAGING_DIR / "sig_full.zip"
            _download_with_progress(
                full_url, self.staged_zip, lambda d, t: self._report(
                    "Baixando o pacote do GitHub...", 2 + 96 * d / t
                )
            )
            self.download_ok = True
            self._report("Download concluído — clique em Instalar.", 100)
            self._messages.put(("ENABLE", 100))
        except Exception as error:
            import traceback
            detail = traceback.format_exc(limit=4)
            self._report(
                f"GitHub indisponível ({type(error).__name__}); tentando o Drive...",
                2,
            )
            print(detail, file=sys.stderr)
            self._fallback_drive()

    def _fallback_drive(self):
        try:
            state = self._download_sync_state(SYNC_MANIFEST_FILE_ID)
            # "files" é uma LISTA de dicts {path, sha256, size, drive_id, github_url}
            entries = state.get("files") or []
            if not entries:
                raise RuntimeError("Manifesto do Drive sem arquivos para baixar.")
            files = {entry.get("path", ""): entry for entry in entries if entry.get("path")}
            downloads = sorted(files.keys())
            self.staged_files = []
            for index, path in enumerate(downloads):
                entry = files[path]
                destination = STAGING_DIR / "sync" / Path(*path.split("/"))
                destination.parent.mkdir(parents=True, exist_ok=True)
                _download_google_drive_file(
                    entry["drive_id"], destination,
                    lambda d, t, p=path, i=index: self._report(
                        f"Baixando do Drive: {p} ({i + 1}/{len(downloads)})",
                        2 + 90 * (i + d / max(t, 1)) / len(downloads),
                    ),
                )
                digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                if digest.lower() != entry["sha256"]:
                    raise RuntimeError(f"SHA-256 divergente ao baixar: {path}")
                self.staged_files.append(destination)
            self.download_ok = True
            self._report("Download concluído — clique em Instalar.", 100)
            self._messages.put(("ENABLE", 100))
        except Exception as error:
            import traceback
            detail = traceback.format_exc(limit=3)
            self._report(f"Falha também no Drive: {error}", 0)
            self._messages.put(("FAIL", f"{error}\n{detail}"))

    @staticmethod
    def _download_sync_state(file_id: str) -> dict:
        request = urllib.request.Request(
            _drive_url(file_id), headers={"User-Agent": "sig-installer-online"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def install(self):
        try:
            self.install_button.configure(state="disabled")
            self._report("Instalando...", 0)
            if STAGING_DIR.exists():
                shutil.rmtree(STAGING_DIR, ignore_errors=True)
            STAGING_DIR.mkdir(parents=True, exist_ok=True)
            self._report("Extraindo os arquivos...", 10)
            if self.staged_zip is not None:
                with zipfile.ZipFile(self.staged_zip) as archive:
                    archive.extractall(STAGING_DIR / "extracted")
                source_root = STAGING_DIR / "extracted"
            else:
                source_root = STAGING_DIR / "sync"
            APP_DIR.mkdir(parents=True, exist_ok=True)
            files = list(source_root.rglob("*"))
            for index, item in enumerate(files):
                if item.is_file():
                    relative = item.relative_to(source_root)
                    target = APP_DIR / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target)
                self._report("Extraindo os arquivos...", 10 + 70 * index / max(len(files), 1))
            self._report("Criando os atalhos...", 85)
            self._create_shortcuts()
            self._report("Instalação concluída!", 100)
            self.status_var.set("SIG instalado com sucesso.")
            try:
                import subprocess
                subprocess.Popen([str(APP_DIR / "sig.exe")], cwd=str(APP_DIR))
            except Exception:
                pass
            messagebox.showinfo("SIG", f"SIG instalado em {APP_DIR}.")
            self.root.destroy()
        except Exception as error:
            self._report(f"Falha na instalação: {error}", 0)
            messagebox.showerror("SIG", f"Não foi possível instalar:\n{error}")

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
