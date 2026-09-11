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

    # Os seletores "Keywords" (perfis) ficam nas duas telas, com o "?" ao lado.
    # Lê o rótulo pelo objeto Python (não por `root.getvar`): no preflight a
    # suíte anterior deixa o `_default_root` do Tkinter apontando para outro
    # interpretador, e o nome Tcl do var não existe no root do smoke (o objeto
    # Python continua válido — é ele que o app usa).
    for atributo, var_atributo, onde in (
        ("files_keywords_button", "files_keywords_label_var", "aba Transcricao"),
        ("live_keywords_button", "live_keywords_label_var", "tela de Ocorrencia"),
    ):
        botao = getattr(app, atributo, None)
        if botao is None:
            raise RuntimeError(f"seletor Keywords ausente na {onde}")
        if botao.winfo_manager() != "pack":
            raise RuntimeError(f"seletor Keywords nao esta visivel na {onde}")
        variavel = getattr(app, var_atributo, None)
        if variavel is None or not str(variavel.get()).startswith("Keywords: "):
            valor = variavel.get() if variavel is not None else "-"
            raise RuntimeError(f"rotulo do seletor Keywords fora do padrao: {valor!r}")
    if not str(app.files_keywords_label_var.get()).startswith("Keywords: "):
        raise RuntimeError("rotulo do seletor Keywords da Transcricao fora do padrao")
    # O menu do seletor precisa ter sempre a opcao "desligado" ("Nao").
    menu = app.files_keywords_button.nametowidget(app.files_keywords_button.cget("menu"))
    opcoes = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)]
    if not opcoes or opcoes[0] != "Não":
        raise RuntimeError(f"seletor Keywords sem a opcao 'Nao' primeiro: {opcoes}")
    # O "?" (limites por modelo + aviso de falso positivo) acompanha os dois
    # seletores e a tela de Keywords — SEMPRE como o marcador padrão (tk.Label
    # discreto, igual ao do VAD), nunca como botão.
    for atributo, onde in (
        ("files_keywords_help", "aba Transcricao"),
        ("live_keywords_help", "tela de Ocorrencia"),
        ("live_diarize_help", "tela de Ocorrencia (diarizacao)"),
    ):
        marcador = getattr(app, atributo, None)
        if marcador is None:
            raise RuntimeError(f"marcador '?' ausente na {onde}")
        if not isinstance(marcador, tk.Label) or marcador.cget("text") != "?":
            raise RuntimeError(f"marcador '?' da {onde} nao segue o padrao do VAD (tk.Label)")

    def descendentes(widget):
        for filho in widget.winfo_children():
            yield filho
            yield from descendentes(filho)

    def textos(tipo):
        return [w.cget("text") for w in descendentes(settings_window) if isinstance(w, tipo)]

    botoes = textos(ttk.Button)
    # A seção de Keywords vive na aba Avançado (o botão KEYWORDS foi removido):
    # o conteúdo está num LabelFrame "Keywords", logo abaixo de "Paralelismo".
    if "KEYWORDS" in botoes:
        raise RuntimeError("o botao KEYWORDS deveria ter sido removido")
    secoes_avancado = [
        w for w in descendentes(settings_window) if isinstance(w, ttk.LabelFrame)
    ]
    keywords_secao = next((w for w in secoes_avancado if w.cget("text") == "Keywords"), None)
    if keywords_secao is None:
        raise RuntimeError("secao 'Keywords' ausente na aba Avancado")
    paralelismo = next((w for w in secoes_avancado if w.cget("text") == "Paralelismo"), None)
    if paralelismo is None:
        raise RuntimeError("secao 'Paralelismo' ausente na aba Avancado")
    if paralelismo.master is not keywords_secao.master:
        raise RuntimeError("Paralelismo e Keywords deveriam estar na mesma aba")
    irmaos = list(keywords_secao.master.winfo_children())
    if irmaos.index(keywords_secao) < irmaos.index(paralelismo):
        raise RuntimeError("a secao Keywords deveria ficar ABAIXO de Paralelismo")
    # Os controles dos perfis precisam estar dentro da seção de Keywords.
    botoes_secao = [
        b.cget("text") for b in descendentes(keywords_secao) if isinstance(b, ttk.Button)
    ]
    for rotulo in ("+ Perfil", "Renomear", "Excluir", "+", "\u2212"):
        if rotulo not in botoes_secao:
            raise RuntimeError(f"controle {rotulo!r} ausente na secao Keywords")
    if not any(isinstance(w, ttk.Treeview) for w in descendentes(keywords_secao)):
        raise RuntimeError("tabela de termos ausente na secao Keywords")
    marcadores = [
        w for w in descendentes(settings_window)
        if isinstance(w, tk.Label) and w.cget("text") == "?"
    ]
    if not marcadores:
        raise RuntimeError("marcador '?' ausente na tela de Keywords")
    # O texto de ajuda precisa citar os limites reais (para o usuario saber que
    # so os primeiros termos sao enviados e que ha risco de falso positivo).
    ajuda = app._keywords_help_text()
    for trecho in ("SÓ OS PRIMEIROS TERMOS SÃO ENVIADOS", "500 tokens", "TRANSCRIÇÃO POLICIAL"):
        if trecho not in ajuda:
            raise RuntimeError(f"texto de ajuda das keywords sem o trecho: {trecho}")
    # Tela de keywords: botao "+ Perfil" (dialogo de nome) alem de Renomear/Excluir.
    if "+ Perfil" not in botoes:
        raise RuntimeError("botao '+ Perfil' ausente na tela de Keywords")
    for rotulo in ("Renomear", "Excluir"):
        if rotulo not in botoes:
            raise RuntimeError(f"botao {rotulo!r} ausente na tela de Keywords")

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
