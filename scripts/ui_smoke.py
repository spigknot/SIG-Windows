"""Smoke test for the main Tk interface without network or user data."""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MAIN_TABS = ("live", "files", "qualification", "imei", "ffmpeg", "diarias", "qrcode")
TAB_BUTTONS = (
    "live_tab_button",
    "files_tab_button",
    "qualification_tab_button",
    "imei_tab_button",
    "ffmpeg_tab_button",
    "diarias_tab_button",
    "qrcode_tab_button",
)


def _destroy_toplevels(root: tk.Tk) -> None:
    for child in root.winfo_children():
        if isinstance(child, tk.Toplevel) and child.winfo_exists():
            child.destroy()


def _check_transcription_language_selector(app) -> None:
    """Seletor de idioma da aba Transcrição (paridade com a aba Ocorrência).

    Vacina da UI: o seletor precisa existir, oferecer exatamente
    auto/pt/en/es (sem custom) e ficar À DIREITA do botão "Modelos".
    """
    button = getattr(app, "files_language_button", None)
    if button is None:
        raise RuntimeError("seletor de idioma da aba Transcricao ausente")
    if button.winfo_manager() != "pack":
        raise RuntimeError("seletor de idioma da aba Transcricao nao esta visivel")
    models_button = getattr(app, "files_models_button", None)
    if models_button is None or models_button.master is not button.master:
        raise RuntimeError("seletor de idioma nao esta na mesma barra do botao Modelos")
    irmaos = list(button.master.winfo_children())
    if irmaos.index(button) < irmaos.index(models_button):
        raise RuntimeError("seletor de idioma nao esta a direita do botao Modelos")
    if button.pack_info().get("side") != "left":
        raise RuntimeError("seletor de idioma nao usa o alinhamento padrao (side=left)")
    menu = button.cget("menu")
    labels = [button.nametowidget(menu).entrycget(index, "label")
              for index in range(button.nametowidget(menu).index("end") + 1)]
    if labels != ["auto", "pt", "en", "es"]:
        raise RuntimeError(f"opcoes do seletor de idioma inesperadas: {labels}")
    if not str(app.files_language_label_var.get()).startswith("Idioma:"):
        raise RuntimeError("rotulo do seletor de idioma fora do padrao 'Idioma: ...'")


def run(*, quiet: bool = False) -> int:
    root: tk.Tk | None = None
    try:
        import sig_app

        root = tk.Tk()
        root.withdraw()
        # The smoke test validates UI construction, not local encoder probing.
        # The probe requires a packaged ffmpeg.exe and is tested by release gates.
        with patch.object(sig_app.FfmpegToolsPanel, "_load_available_accelerations", lambda _self: None):
            app = sig_app.SigApp(root)
            missing = [name for name in TAB_BUTTONS if not hasattr(app, name)]
            if missing:
                raise RuntimeError("main tab widgets missing: " + ", ".join(missing))
            for tab_name in MAIN_TABS:
                app.select_main_tab(tab_name)
                root.update_idletasks()

            _check_transcription_language_selector(app)

            before = set(root.winfo_children())
            app.open_settings()
            root.update_idletasks()
            settings_windows = [
                child
                for child in root.winfo_children()
                if isinstance(child, tk.Toplevel) and child not in before
            ]
            if len(settings_windows) != 1:
                raise RuntimeError(f"expected one settings window, got {len(settings_windows)}")
            settings_windows[0].destroy()
            root.update_idletasks()

        if not quiet:
            print("PASS: interface principal, abas e Configuracoes construidas")
        return 0
    except Exception as exc:
        print(f"FAIL: UI smoke: {exc}")
        return 1
    finally:
        if root is not None:
            try:
                _destroy_toplevels(root)
                root.destroy()
            except tk.TclError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test da interface Tk do SIG Windows")
    parser.add_argument("--quiet", action="store_true", help="ocultar linhas PASS")
    args = parser.parse_args(argv)
    return run(quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
