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


def _check_transcription_models_menu(app) -> None:
    """Menu "Modelos" da aba Transcrição (hermético: servidor local online).

    Vacina do pedido de 10/09: nenhum modelo exclusivo de WebSocket (Meta Muse
    Voice, ElevenLabs Scribe realtime) pode ser oferecido na Transcrição, e a
    seleção padrão é apenas o `servidor` (Granite NAR local).
    """
    import sig_app

    with patch.object(sig_app, "hostname_online", lambda _host: True), patch.object(
        sig_app, "load_settings", lambda: dict(sig_app.DEFAULT_SETTINGS)
    ):
        app._populate_models_menu()

    offered = dict(app.multi_transcription_model_vars)
    if not offered:
        raise RuntimeError("menu Modelos vazio no smoke test")
    for name in offered:
        if sig_app.is_realtime_only_transcription_server(name):
            raise RuntimeError(f"modelo so-websocket oferecido na Transcricao: {name}")
    checked = sorted(name for name, variable in offered.items() if variable.get())
    if checked != ["servidor"]:
        raise RuntimeError(f"selecao padrao do menu Modelos inesperada: {checked}")


def _check_keywords_and_settings_tabs(app, settings_window) -> None:
    """Checkbox Keywords (Transcrição/Ocorrência) + aba Modelos das chaves.

    Vacinas do pedido de 10/09:
    - as duas telas têm a checkbox "Keywords" (mesma chave de settings);
    - a aba "Chaves API" tem UMA seção "Modelos" com os 7 provedores na ordem
      Deepseek, xAI, Meta, ElevenLabs, Deepgram, AssemblyAI, Alibaba;
    - a aba "Avançado" tem o botão KEYWORDS.
    """
    from tkinter import ttk

    if getattr(app, "files_keywords_check", None) is None:
        raise RuntimeError("checkbox Keywords da aba Transcricao ausente")
    if app.files_keywords_check.winfo_manager() != "pack":
        raise RuntimeError("checkbox Keywords da aba Transcricao nao esta visivel")
    if getattr(app, "live_keywords_check", None) is None:
        raise RuntimeError("checkbox Keywords da tela de Ocorrencia ausente")
    # O "?" (limites por modelo + aviso de falso positivo) acompanha as duas
    # checkboxes e a tela de Keywords.
    for atributo, onde in (
        ("files_keywords_help", "aba Transcricao"),
        ("live_keywords_help", "tela de Ocorrencia"),
    ):
        botao = getattr(app, atributo, None)
        if botao is None:
            raise RuntimeError(f"botao '?' das keywords ausente na {onde}")
        if botao.cget("text") != "?":
            raise RuntimeError(f"botao das keywords na {onde} nao e '?'")

    def descendentes(widget):
        for filho in widget.winfo_children():
            yield filho
            yield from descendentes(filho)

    def textos(tipo):
        return [w.cget("text") for w in descendentes(settings_window) if isinstance(w, tipo)]

    botoes = textos(ttk.Button)
    if "KEYWORDS" not in botoes:
        raise RuntimeError("botao KEYWORDS ausente na aba Avancado")
    if botoes.count("?") < 1:
        raise RuntimeError("botao '?' das keywords ausente nas Configuracoes")
    # O texto de ajuda precisa citar os limites reais (para o usuario saber que
    # so os primeiros termos sao enviados e que ha risco de falso positivo).
    ajuda = app._keywords_help_text()
    for trecho in ("SÓ OS PRIMEIROS TERMOS SÃO ENVIADOS", "500 tokens", "FALSO POSITIVO"):
        if trecho not in ajuda:
            raise RuntimeError(f"texto de ajuda das keywords sem o trecho: {trecho}")

    secoes = [w for w in descendentes(settings_window) if isinstance(w, ttk.LabelFrame)]
    imei = next((w for w in secoes if w.cget("text") == "IMEI CHECK"), None)
    if imei is None:
        raise RuntimeError("secao 'IMEI CHECK' ausente na aba Chaves API")
    # Escopo: a própria aba "Chaves API" (a aba Modelos também tem uma seção
    # chamada "Transcrição" — não pode ser confundida com a das chaves).
    api_tab = imei.master
    secoes_da_aba = [w for w in descendentes(api_tab) if isinstance(w, ttk.LabelFrame)]
    modelos = next((w for w in secoes_da_aba if w.cget("text") == "Modelos"), None)
    if modelos is None:
        raise RuntimeError("secao 'Modelos' ausente na aba Chaves API")
    if any(w.cget("text") in {"Transcrição", "Texto"} for w in secoes_da_aba):
        raise RuntimeError("secoes 'Transcricao'/'Texto' deveriam ter sido fundidas em 'Modelos'")
    labels = [
        rotulo.cget("text")
        for rotulo in descendentes(modelos)
        if isinstance(rotulo, ttk.Label)
    ]
    esperado = ["Deepseek", "xAI", "Meta", "ElevenLabs", "Deepgram", "AssemblyAI", "Alibaba"]
    if labels != esperado:
        raise RuntimeError(f"linhas da secao Modelos fora de ordem: {labels}")


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
            _check_transcription_models_menu(app)

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
            # A janela de Configurações também é exercitada (seções, ordem das
            # chaves e botão KEYWORDS) antes de ser destruída.
            settings_window = settings_windows[0]
            _check_keywords_and_settings_tabs(app, settings_window)
            settings_window.destroy()
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
