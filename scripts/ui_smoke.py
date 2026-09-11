"""Smoke test for the main Tk interface without network or user data."""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_env import physical_cpu_count  # noqa: E402  (nucleos FISICOS da maquina)

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


def _expected_conversion_values(nucleos: int) -> list[int]:
    """Opções do slider de Conversões conforme a especificação.

    Regra do usuário (11/09): 1, 2, 3, ..., n, 3n/2, 2n, 5n/2, 3n, 7n/2, 4n,
    aproximando a conta quebrada para cima no empate (4.5 -> 5). Derivado da
    especificação de propósito: repetir a função do app daria falso positivo.
    """
    import math

    valores = list(range(1, nucleos + 1))
    for fator in (3, 4, 5, 6, 7, 8):
        valores.append(int(math.floor(nucleos * fator / 2 + 0.5)))
    return sorted(set(valores))


def _check_parallel_sliders(app, settings_window) -> None:
    """Sliders de nós da aba Avançado (visual do TurboCore e passos).

    Vacinas do pedido de 10/09: Conversões sobe de 4 em 4 e Requisições de 2
    em 2; o slider começa logo depois do rótulo (sem o vão de 170px) e usa o
    mesmo NodeSlider do TurboCore (não o ttk.Scale, que não tem nós).
    """
    from tkinter import ttk

    from ui_widgets import NodeSlider

    def descendentes(widget):
        for filho in widget.winfo_children():
            yield filho
            yield from descendentes(filho)

    def clicar_aba(nome: str) -> None:
        for rotulo in descendentes(settings_window):
            if isinstance(rotulo, tk.Label) and rotulo.cget("text") == nome:
                rotulo.event_generate("<Button-1>", x=1, y=1)
                settings_window.update_idletasks()
                return
        raise RuntimeError(f"aba {nome!r} nao encontrada")

    clicar_aba("Avançado")
    painel = next(
        (w for w in descendentes(settings_window)
         if isinstance(w, ttk.LabelFrame) and w.cget("text") == "Paralelismo"),
        None,
    )
    if painel is None:
        raise RuntimeError("secao Paralelismo ausente na aba Avancado")
    sliders = [w for w in descendentes(painel) if isinstance(w, NodeSlider)]
    if len(sliders) != 2:
        raise RuntimeError(f"esperava 2 sliders de nos, achei {len(sliders)}")
    # Opções do slider conforme a ESPECIFICAÇÃO (não a função do app): as
    # Conversões seguem 1..n, 3n/2, 2n, 5n/2, 3n, 7n/2, 4n com n = NÚCLEOS
    # físicos; as Requisições continuam de 2 em 2 até 16 (regra de 31/08 — o
    # gargalo é a rede).
    nucleos = max(1, physical_cpu_count())
    esperado = [_expected_conversion_values(nucleos), list(range(2, 17, 2))]
    for slider, valores in zip(sliders, esperado):
        if list(slider.values) != valores:
            raise RuntimeError(
                f"opcoes do slider {list(slider.values)[:6]}... diferentes de {valores[:6]}..."
            )
    # O slider precisa comecar logo depois do rótulo (pedido do usuário).
    for slider in sliders:
        irmaos = [w for w in descendentes(painel) if isinstance(w, ttk.Label)]
        rotulo = max(
            (l for l in irmaos if l.winfo_y() == slider.winfo_y()),
            key=lambda l: l.winfo_x(),
            default=None,
        )
        if rotulo is not None:
            vao = slider.winfo_x() - (rotulo.winfo_x() + rotulo.winfo_width())
            if vao > 40:
                raise RuntimeError(f"slaider longe do rotulo ({vao}px de vao)")


def _settings_tab_pages(settings_window):
    """(botoes das abas, pagina ativa) da janela de Configurações."""
    from tkinter import ttk

    def descendentes(widget):
        for filho in widget.winfo_children():
            yield filho
            yield from descendentes(filho)

    abas = (
        w for w in descendentes(settings_window)
        if isinstance(w, tk.Label)
        and w.cget("text") in {"Modelos", "Policial", "Chaves API", "Avançado"}
        and isinstance(w.master, tk.Frame)
    )
    botoes = {w.cget("text"): w for w in abas}
    if len(botoes) != 4:
        raise RuntimeError(f"esperava 4 abas de Configuracoes, achei {list(botoes)}")
    barra = next(iter(botoes.values())).master
    conteudo = next(
        (w for w in barra.master.winfo_children()
         if w is not barra and len(w.winfo_children()) >= 4),
        None,
    )
    if conteudo is None:
        raise RuntimeError("area de conteudo das Configuracoes nao encontrada")
    return botoes, conteudo


def _check_settings_window_on_low_core_machines(app, root) -> None:
    """As Configurações nascem INTEIRAS em máquinas com poucos núcleos.

    Vacina do bug de 11/09 (relatado pelo usuário como "o menu de
    Configurações aparece todo colapsado em outros PCs, só a aba Chaves API
    funciona"): a ajuda do slider de Conversões montava a frase indexando
    `conv_valores[2]` fixo, e `step_values(4, nucleos * 2)` devolve menos de 3
    valores em máquinas com até 5 CPUs lógicas. O `IndexError` abortava
    `open_settings` NO MEIO da construção: a janela abria só com a barra de
    abas e tudo o que é construído depois (as seções da aba Modelos, a aba
    Policial, os sliders) ficava vazio — a aba Chaves API, construída antes,
    era a única que aparecia. O bug passou batido aqui porque a máquina de
    build tem 36 CPUs; por isso este check varre contagens pequenas.
    """
    from tkinter import ttk

    import sig_app

    from ui_widgets import NodeSlider

    # Altura mínima da aba MAIS BAIXA com conteúdo (Policial, ~194px com o
    # layout atual). Construção abortada deixa a página com 1px a 45px.
    altura_minima = 120
    secoes_modelos = ("Transcrição", "Histórico", "Oitiva", "Qualificação", "Extração de partes")

    def descendentes(widget):
        for filho in widget.winfo_children():
            yield filho
            yield from descendentes(filho)

    for nucleos in (1, 2, 3, 4, 5, 6, 8, 18, 36):
        antes = set(root.winfo_children())
        # Imita NÚCLEOS FÍSICOS e, de propósito, threads DIFERENTES (2×), como
        # num processador com SMT: se o app consultasse `os.cpu_count()` a
        # escala sairia 1..2n e a comparação abaixo falharia.
        with patch.object(sig_app.os, "cpu_count", lambda valor=nucleos: valor * 2), \
                patch.object(sig_app, "physical_cpu_count", lambda valor=nucleos: valor):
            app.open_settings()          # qualquer exceção derruba o gate
        root.update_idletasks()
        janelas = [
            filho for filho in root.winfo_children()
            if isinstance(filho, tk.Toplevel) and filho not in antes
        ]
        if len(janelas) != 1:
            raise RuntimeError(f"esperava uma janela de Configuracoes com {nucleos} nucleos")
        janela = janelas[0]
        try:
            root.update_idletasks()
            botoes, conteudo = _settings_tab_pages(janela)
            larguras = {}
            for nome, botao in botoes.items():
                botao.event_generate("<Button-1>", x=1, y=1)
                janela.update_idletasks()
                pagina = next(
                    (w for w in conteudo.winfo_children() if w.winfo_manager() == "pack"),
                    None,
                )
                if pagina is None:
                    raise RuntimeError(f"aba {nome} sem pagina ativa com {nucleos} nucleos")
                if pagina.winfo_reqheight() < altura_minima:
                    raise RuntimeError(
                        f"aba {nome} vazia com {nucleos} nucleos "
                        f"({pagina.winfo_reqheight()}px): a construcao das "
                        "Configuracoes foi interrompida no meio"
                    )
                larguras[nome] = pagina.winfo_reqwidth()
            # A janela é `resizable(False, False)`: ela assume o tamanho
            # requisitado da aba ATIVA. A aba Avançado não pode ficar mais larga
            # que a aba Modelos (quem dita o tamanho é a maior), senão a janela
            # estica quando o usuário clica em Avançado — e é o slider de nós
            # (comprimento adaptativo ao nº de opções) que empurra a largura.
            if larguras["Avançado"] > larguras["Modelos"]:
                raise RuntimeError(
                    f"aba Avancado mais larga que Modelos com {nucleos} nucleos "
                    f"({larguras['Avançado']} vs {larguras['Modelos']}px): "
                    "a janela de Configuracoes vai esticar ao trocar de aba"
                )
            # As seções da aba Modelos não podem ficar colapsadas (foi
            # exatamente esse o sintoma: LabelFrame vazio pede 1x1 px).
            for secao in descendentes(janela):
                if isinstance(secao, ttk.LabelFrame) and secao.cget("text") in secoes_modelos:
                    if secao.winfo_reqheight() < 40:
                        raise RuntimeError(
                            f"secao {secao.cget('text')!r} colapsada "
                            f"({secao.winfo_reqheight()}px) com {nucleos} nucleos"
                        )
            # As Conversões precisam oferecer as opções da especificação nesta
            # máquina (1..n, 3n/2 ... 4n) — e não só um nó, como acontecia com
            # o passo fixo de 4 numa máquina de 2 núcleos.
            valores = _expected_conversion_values(nucleos)
            sliders = [w for w in descendentes(janela) if isinstance(w, NodeSlider)]
            if not sliders:
                raise RuntimeError(f"sliders ausentes com {nucleos} nucleos")
            if list(sliders[0].values) != valores:
                raise RuntimeError(
                    f"opcoes de Conversoes com {nucleos} nucleos diferentes do "
                    f"esperado: {list(sliders[0].values)[:6]}..."
                )
            # O valor mostrado precisa ser um nó real (nada de valor encaixado
            # à força em outro número).
            if sliders[0].get() not in valores:
                raise RuntimeError(
                    f"valor {sliders[0].get()} nao e uma opcao valida "
                    f"({nucleos} nucleos)"
                )
        finally:
            janela.destroy()
            root.update_idletasks()


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
    # A janela das Configurações é `resizable(False, False)`: ela assume o
    # tamanho requisitado da ABA ATIVA, então uma seção larga demais faz a
    # janela crescer ao trocar de aba. A aba Avançado precisa caber no tamanho
    # inicial (o mesmo da aba Modelos), senão a janela estica na cara do usuário
    # (aconteceu: 836px por causa de uma linha de texto longa).
    if keywords_secao.winfo_reqwidth() > 500:
        raise RuntimeError(
            f"secao Keywords larga demais ({keywords_secao.winfo_reqwidth()}px): "
            "vai esticar a janela de Configuracoes"
        )
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
            _check_parallel_sliders(app, settings_window)
            settings_window.destroy()
            root.update_idletasks()

            # Vacina do bug de 11/09: as Configurações precisam nascer
            # inteiras também em máquinas com poucos núcleos (aqui a máquina
            # tem núcleos de sobra, então o cenário é simulado).
            _check_settings_window_on_low_core_machines(app, root)

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
