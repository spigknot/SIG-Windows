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
from providers import (  # noqa: E402  (catalogo: quem tem o controle "- t = +")
    ALIBABA_API_NAME,
    ASSEMBLYAI_API_NAME,
    DEEPGRAM_API_NAME,
    ELEVENLABS_API_NAME,
    GROK_API_NAME,
    LOCAL_GRANITE_SERVER_NAME,
    META_MUSE_API_NAME,
)

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

# Provedores de API (todos SEM o controle "- t = +" da tela de Ocorrência:
# so o servidor local Granite NAR transcreve em fatias REST com intervalo).
# Os nomes vem do CATALOGO (providers) — provedor novo entra sozinho na
# varredura deste check.
SERVIDORES_DE_API = (
    GROK_API_NAME,
    DEEPGRAM_API_NAME,
    ASSEMBLYAI_API_NAME,
    ELEVENLABS_API_NAME,
    META_MUSE_API_NAME,
    ALIBABA_API_NAME,
)

# Servidor STT local (Granite NAR): o UNICO que mostra o grupo do intervalo.
SERVIDOR_LOCAL = LOCAL_GRANITE_SERVER_NAME

# Colunas dos microfones da linha de controles: NAO podem se mexer quando o
# grupo do intervalo aparece/some (regra explicita do usuario).
COLUNAS_DE_MICROFONE = ("live_normal_mic_column", "live_pause_column", "live_mic_column")


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


def _check_one_model_checkbox(app) -> None:
    """Checkbox "Um modelo por vez" da aba Transcricao (regra do usuario, 13/09).

    Vacina da UI: fica ENTRE o botao "Modelos" e o seletor de Idioma, com o
    rotulo exato e DESMARCADA por padrao (a marcacao e do lote — nao e
    persistida no settings.json).
    """
    checkbox = getattr(app, "files_one_model_check", None)
    if checkbox is None:
        raise RuntimeError("checkbox 'Um modelo por vez' ausente na aba Transcricao")
    if checkbox.winfo_manager() != "pack":
        raise RuntimeError("checkbox 'Um modelo por vez' nao esta visivel")
    models_button = getattr(app, "files_models_button", None)
    language_button = getattr(app, "files_language_button", None)
    if models_button is None or language_button is None:
        raise RuntimeError("botoes da linha de controles da Transcricao ausentes")
    barra = models_button.master
    if checkbox.master is not barra or language_button.master is not barra:
        raise RuntimeError("checkbox nao esta na mesma barra dos botoes Modelos/Idioma")
    # A ordem que o usuario VÊ é a ordem de `pack` (pack_slaves), não a de
    # criação dos widgets: mover o pack() da checkbox muda a posição na tela
    # sem mudar winfo_children().
    ordem = list(barra.pack_slaves())
    for widget, nome in ((models_button, "botao Modelos"), (checkbox, "checkbox"), (language_button, "seletor de Idioma")):
        if widget not in ordem:
            raise RuntimeError(f"{nome} nao esta empacotado na barra da Transcricao")
    if not ordem.index(models_button) < ordem.index(checkbox) < ordem.index(language_button):
        raise RuntimeError("checkbox nao esta entre o botao Modelos e o seletor de Idioma")
    if str(checkbox.cget("text")) != "Um modelo por vez":
        raise RuntimeError(f"rotulo inesperado na checkbox: {checkbox.cget('text')!r}")
    if str(checkbox.cget("variable")) != str(app.files_one_model_var):
        raise RuntimeError("checkbox nao usa a variavel da aba (files_one_model_var)")
    if checkbox.pack_info().get("side") != "left":
        raise RuntimeError("checkbox fora do alinhamento padrao (side=left)")
    if app.files_one_model_var.get():
        raise RuntimeError("checkbox 'Um modelo por vez' precisa nascer desmarcada")


def _expected_conversion_values(nucleos: int) -> list[int]:
    """Opções do slider de Conversões conforme a especificação.

    Regra do usuário (11/09; 8n e 16n pedidos em 14/09): 1, 2, 3, ..., n,
    3n/2, 2n, 5n/2, 3n, 7n/2, 4n, 8n, 16n, aproximando a conta quebrada para
    cima no empate (4.5 -> 5). Derivado da especificação de propósito: repetir
    a função do app daria falso positivo.
    """
    import math

    valores = list(range(1, nucleos + 1))
    for fator in (3, 4, 5, 6, 7, 8, 16, 32):
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
    if len(sliders) != 3:
        raise RuntimeError(f"esperava 3 sliders de nos, achei {len(sliders)}")
    # Opções do slider conforme a ESPECIFICAÇÃO (não a função do app): as
    # Conversões seguem 1..n, 3n/2, 2n, 5n/2, 3n, 7n/2, 4n, 8n, 16n com n =
    # NÚCLEOS físicos; as Requisições continuam de 2 em 2 até 16 (regra de
    # 31/08 — o gargalo é a rede); o VAD (pedido de 13/09) tem TODAS as opções
    # de 1 até n.
    nucleos = max(1, physical_cpu_count())
    esperado = [
        _expected_conversion_values(nucleos),
        list(range(2, 17, 2)),
        list(range(1, nucleos + 1)),
    ]
    for slider, valores in zip(sliders, esperado):
        if list(slider.values) != valores:
            raise RuntimeError(
                f"opcoes do slider {list(slider.values)[:6]}... diferentes de {valores[:6]}..."
            )
    # Rotulos e ordem: identificados pelo GRID (linha/coluna), nao por pixel —
    # a geometria so existe com a janela desenhada e o canvas do slider nao tem
    # o mesmo `winfo_y` dos labels.
    pai = sliders[0].master
    for slider in sliders:
        if slider.master is not pai:
            raise RuntimeError("os sliders de Paralelismo nao estao no mesmo frame")
    filhos = pai.winfo_children()

    def irmao(slider, coluna: int):
        linha = int(slider.grid_info()["row"])
        for widget in filhos:
            if not isinstance(widget, ttk.Label) or widget.winfo_manager() != "grid":
                continue
            info = widget.grid_info()
            if int(info["row"]) == linha and int(info["column"]) == coluna:
                return widget
        return None

    nomes = []
    for slider in sliders:
        nome = irmao(slider, 0)
        if nome is None:
            raise RuntimeError("slaider sem rotulo na coluna 0")
        nomes.append(nome.cget("text"))
    if nomes != ["Conversões", "Requisições", "VAD"]:
        raise RuntimeError(f"rotulos das sliders fora da ordem esperada: {nomes}")

    # O slider mostra o valor PERSISTIDO (encaixado nas opcoes disponiveis); o
    # padrao n/2 quando a chave nao existe é coberto pelos testes unitarios.
    from ui_widgets import nearest_value as _nearest_value

    padrao = str(_nearest_value(int(app.settings["vad_parallel"]), list(range(1, nucleos + 1))))
    valor_vad = irmao(sliders[-1], 2)
    if valor_vad is None or valor_vad.cget("text") != padrao:
        raise RuntimeError(
            f"o slider VAD nao mostra o valor persistido ({padrao}): "
            f"{valor_vad.cget('text') if valor_vad is not None else 'sem label de valor'!r}"
        )

    # Geometria (pedido do usuario, 10/09): os tres sliders ficam na MESMA
    # coluna, que comeca logo depois da coluna dos rotulos. O vao maior de uma
    # linha com rotulo curto (VAD) e o que sobra da largura dos rotulos maiores
    # — nunca um pulo de coluna (era o bug de 170px).
    mapeado = bool(settings_window.winfo_ismapped())
    try:
        settings_window.deiconify()
        settings_window.update()
        nomes_widget = [irmao(slider, 0) for slider in sliders]
        posicoes = {slider.winfo_x() for slider in sliders}
        if len(posicoes) != 1:
            raise RuntimeError(f"sliders de Paralelismo desalinhados: x = {sorted(posicoes)}")
        largura_maxima = max(nome.winfo_width() for nome in nomes_widget)
        for slider, nome in zip(sliders, nomes_widget):
            vao = slider.winfo_x() - (nome.winfo_x() + nome.winfo_width())
            tolerancia = 40 + (largura_maxima - nome.winfo_width())
            if vao > tolerancia:
                raise RuntimeError(
                    f"slaider {nome.cget('text')!r} longe do rotulo "
                    f"({vao}px de vao, tolerado {tolerancia}px)"
                )
    finally:
        if not mapeado:
            settings_window.withdraw()


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


def _check_api_key_visibility_toggle(app, settings_window) -> None:
    """Botão de olho da aba Chaves API (revelar/esconder as chaves).

    Vacina da UI: existe UM botão com ícone na aba, os campos nascem mascarados
    (são chaves de API), o clique revela TODOS os campos da aba e troca o ícone
    pelo olho cortado; o segundo clique volta a esconder e ao ícone original.
    """
    from tkinter import ttk

    def descendentes(widget):
        for filho in widget.winfo_children():
            yield filho
            yield from descendentes(filho)

    secoes = [w for w in descendentes(settings_window) if isinstance(w, ttk.LabelFrame)]
    imei = next((w for w in secoes if w.cget("text") == "IMEI CHECK"), None)
    if imei is None:
        raise RuntimeError("secao 'IMEI CHECK' ausente na aba Chaves API")
    api_tab = imei.master
    # 7 provedores da secao "Modelos" + a chave do IMEI CHECK.
    campos = [w for w in descendentes(api_tab) if isinstance(w, ttk.Entry)]
    if len(campos) != 8:
        raise RuntimeError(
            f"aba Chaves API deveria ter 8 campos de chave, achou {len(campos)}"
        )
    if {w.cget("show") for w in campos} != {"*"}:
        raise RuntimeError("as chaves API deveriam nascer mascaradas")
    olhos = [
        w
        for w in descendentes(api_tab)
        if isinstance(w, ttk.Button) and str(w.cget("image"))
    ]
    if len(olhos) != 1:
        raise RuntimeError(
            f"botao de olho das chaves API ausente ou duplicado: {len(olhos)}"
        )
    olho = olhos[0]
    if olho.winfo_manager() != "pack":
        raise RuntimeError("botao de olho das chaves API nao esta visivel")
    icone_revelar = str(olho.cget("image"))
    olho.invoke()
    settings_window.update_idletasks()
    revelados = {w.cget("show") for w in campos}
    if revelados != {""}:
        raise RuntimeError(f"o botao de olho nao revelou os campos: {revelados}")
    icone_ocultar = str(olho.cget("image"))
    if icone_ocultar == icone_revelar:
        raise RuntimeError("o icone do botao nao mudou ao revelar as chaves")
    olho.invoke()
    settings_window.update_idletasks()
    if {w.cget("show") for w in campos} != {"*"}:
        raise RuntimeError("o botao de olho nao voltou a esconder as chaves")
    if str(olho.cget("image")) != icone_revelar:
        raise RuntimeError("o icone do botao nao voltou ao olho aberto")


def _check_api_key_field_layout(app, settings_window) -> None:
    """Aba Chaves API: rótulo curto do IMEI e campos 25% mais longos.

    Vacina do pedido de 11/09 (dois pedidos na mesma tela):
    - o rótulo do campo do IMEI é "IMEI Check" (era "Chave API do IMEI Check");
    - os 8 campos de chave COMEÇAM mais à esquerda do que com a coluna de rótulo
      antiga (190px) e ficaram 25% mais longos.

    A largura "antiga" é medida na hora, com um Entry da largura anterior
    (60 caracteres): em caracteres o ganho acompanha a fonte e a comparação
    continua valendo em DPI diferente — pixels fixos não valeriam.
    """
    from tkinter import ttk

    import sig_app

    def descendentes(widget):
        for filho in widget.winfo_children():
            yield filho
            yield from descendentes(filho)

    secoes = [w for w in descendentes(settings_window) if isinstance(w, ttk.LabelFrame)]
    imei = next((w for w in secoes if w.cget("text") == "IMEI CHECK"), None)
    if imei is None:
        raise RuntimeError("secao 'IMEI CHECK' ausente na aba Chaves API")
    modelos = next((w for w in secoes if w.cget("text") == "Modelos"), None)
    if modelos is None:
        raise RuntimeError("secao 'Modelos' ausente na aba Chaves API")

    rotulos_imei = [
        rotulo.cget("text") for rotulo in descendentes(imei) if isinstance(rotulo, ttk.Label)
    ]
    if rotulos_imei != ["IMEI Check"]:
        raise RuntimeError(f"rotulo do campo do IMEI fora do padrao: {rotulos_imei}")

    # A largura renderizada só existe com a aba EMPACOTADA: clica nela como o
    # usuário faria (a janela assume o tamanho requisitado da aba ativa).
    botoes, _conteudo = _settings_tab_pages(settings_window)
    botoes["Chaves API"].event_generate("<Button-1>", x=1, y=1)
    settings_window.update_idletasks()

    for secao in (modelos, imei):
        campos = [w for w in descendentes(secao) if isinstance(w, ttk.Entry)]
        if not campos:
            raise RuntimeError(f"secao {secao.cget('text')!r} sem campos de chave")
        referencia = ttk.Entry(secao, width=sig_app.API_KEY_ENTRY_WIDTH_LEGACY_CHARS)
        largura_antiga = referencia.winfo_reqwidth()
        referencia.destroy()
        exigido = largura_antiga * sig_app.API_KEY_FIELD_MIN_GROWTH
        # Margem direita da seção (borda + padding): os campos terminam nela, o
        # que prova que TODO o ganho veio da esquerda e não de uma janela maior.
        margem_direita = sig_app.API_KEY_SECTION_HORIZONTAL_MARGIN // 2
        for campo in campos:
            if campo.winfo_width() < exigido:
                raise RuntimeError(
                    f"campo de chave da secao {secao.cget('text')!r} com "
                    f"{campo.winfo_width()}px: os 25% sobre os {largura_antiga}px "
                    f"anteriores exigem {exigido:.0f}px"
                )
            if campo.winfo_x() > sig_app.API_KEY_LABEL_COLUMN_LEGACY_WIDTH:
                raise RuntimeError(
                    f"campo de chave da secao {secao.cget('text')!r} comeca em "
                    f"x={campo.winfo_x()}: deveria comecar antes dos "
                    f"{sig_app.API_KEY_LABEL_COLUMN_LEGACY_WIDTH}px da coluna antiga"
                )
            fim = campo.winfo_x() + campo.winfo_width()
            if abs(fim - (secao.winfo_width() - margem_direita)) > 2:
                raise RuntimeError(
                    f"campo de chave da secao {secao.cget('text')!r} termina em "
                    f"{fim}px numa secao de {secao.winfo_width()}px: a margem "
                    f"direita mudou (o ganho deveria vir so da ESQUERDA)"
                )


def _check_live_local_server_controls(app, root) -> None:
    """Controles exclusivos do servidor local (Granite NAR) na tela de Ocorrencia.

    Vacina do pedido de 11/09. Com o servidor local aparecem SO o grupo
    "- t = +" (TEMPO) e nada mais da linha: Timestamps, Diarizacao, Idioma e
    Keywords ficam ocultos e o grupo do intervalo fica encostado a ESQUERDA.
    Com qualquer provedor de API e o inverso: o intervalo some, o Timestamps
    volta encostado a esquerda e o bloco de idioma/keywords reaparece.

    A janela precisa estar MAPEADA: e a unica forma de o Tk calcular posicoes
    reais (com o root withdrawn todo x e 0). As tres colunas de microfone NAO
    podem se mexer em nenhum dos cenarios.
    """
    import sig_app

    def estado(servidor: str) -> dict:
        app.settings["transcription_server"] = servidor
        app._refresh_live_grok_controls()
        root.update()
        return {
            "intervalo_gerenciado": app.live_interval_controls.winfo_manager(),
            "intervalo_x": app.live_interval_controls.winfo_x(),
            "timestamps_gerenciado": app.live_timestamps_check.winfo_manager(),
            "timestamps_x": app.live_timestamps_check.winfo_x(),
            "idioma_gerenciado": app.live_grok_controls.winfo_manager(),
            "mics": {nome: getattr(app, nome).winfo_x() for nome in COLUNAS_DE_MICROFONE},
        }

    original = app.settings.get("transcription_server")
    app.select_main_tab("live")
    mapeado = bool(root.winfo_ismapped())
    if not mapeado:
        root.deiconify()
        root.update()
    try:
        local = estado(SERVIDOR_LOCAL)
        provedores = {nome: estado(nome) for nome in SERVIDORES_DE_API}
    finally:
        app.settings["transcription_server"] = original
        app._refresh_live_grok_controls()
        if not mapeado:
            root.withdraw()

    if local["intervalo_gerenciado"] != "pack":
        raise RuntimeError(
            "grupo '- t = +' nao esta visivel com o servidor local (Granite NAR) selecionado"
        )
    if local["intervalo_x"] != 0:
        raise RuntimeError(
            f"o grupo '- t = +' nao esta encostado a esquerda: x={local['intervalo_x']}px"
        )
    for campo in ("timestamps", "idioma"):
        if local[f"{campo}_gerenciado"]:
            raise RuntimeError(
                f"'{campo}' continua visivel com o servidor local (Granite NAR) selecionado"
            )
    if app.live_timestamps_var.get():
        raise RuntimeError("o checkbox de Timestamps ficou marcado com o servidor local")

    for nome, dados in provedores.items():
        if dados["intervalo_gerenciado"]:
            raise RuntimeError(f"grupo '- t = +' continua visivel com {nome} selecionado")
        if dados["timestamps_gerenciado"] != "pack":
            raise RuntimeError(f"'Timestamps' nao voltou com {nome} selecionado")
        if dados["timestamps_x"] != 0:
            raise RuntimeError(
                f"o resto da linha nao foi para a esquerda com {nome}: "
                f"Timestamps em x={dados['timestamps_x']}px"
            )
        if dados["idioma_gerenciado"] != "pack":
            raise RuntimeError(f"bloco de idioma/keywords nao voltou com {nome} selecionado")
        for coluna in COLUNAS_DE_MICROFONE:
            if dados["mics"][coluna] != local["mics"][coluna]:
                raise RuntimeError(
                    f"a coluna de microfone {coluna} mudou de lugar com {nome}: "
                    f"{local['mics'][coluna]}px -> {dados['mics'][coluna]}px"
                )


def _check_ffmpeg_preview_stage(app, root) -> None:
    """Palco da prévia das ferramentas FFmpeg (pedido de 11/09).

    Com geometria REAL (janela mapeada): o palco abraça a proporção da mídia,
    ocupa o espaço que sobra dos controles, nao encosta no widget seguinte, e o
    zoom da roda + arrasto do mouse funcionam sobre o quadro.
    """
    from PIL import Image

    from ffmpeg_tools_panel import MediaProfile, preview_drawn_size, preview_view_rect

    panel = app.ffmpeg_tools
    app.select_main_tab("ffmpeg")
    mapeado = bool(root.winfo_ismapped())
    if not mapeado:
        root.deiconify()
        root.update()
    try:
        palcos = {
            "Cortar": (panel.cut_tab, panel.cut_preview, (1920, 1080)),
            "Extrair áudio": (panel.extract_tab, panel.extract_preview, (1920, 1080)),
            "Girar vídeo": (panel.rotate_tab, panel.rotate_preview, (1280, 720)),
        }
        for ferramenta, (aba, canvas, midia) in palcos.items():
            panel._select_ffmpeg_tool(ferramenta)
            largura, altura = midia
            panel._reset_preview_view(canvas, largura, altura)
            root.update()

            view = panel.preview_viewports[canvas]
            holder = panel.preview_holders[canvas]
            disponivel_largura, disponivel_altura = panel._preview_available_box(aba, holder)
            # 0) a aba inteira continua visível: o palco não empurra os controles
            #    para baixo da dobra (o desconto inclui pady e padding da aba).
            painel_altura = panel.ffmpeg_scroll_canvas.winfo_height()
            if aba.winfo_reqheight() > painel_altura + 6:
                raise RuntimeError(
                    f"[{ferramenta}] conteudo da aba ({aba.winfo_reqheight()}px) passa do painel "
                    f"({painel_altura}px): o palco comeu a folga dos controles"
                )
            # 1) o palco tem tamanho próprio (nao e' um quadrado fixo nem o canvas inteiro)
            if (holder.winfo_width(), holder.winfo_height()) != (view.stage_width, view.stage_height):
                raise RuntimeError(
                    f"[{ferramenta}] holder {holder.winfo_width()}x{holder.winfo_height()} difere do palco "
                    f"{view.stage_width}x{view.stage_height}"
                )
            # 2) proporcao da midia preservada dentro do arredondamento
            proporcao_palco = view.stage_width / view.stage_height
            proporcao_midia = largura / altura
            if abs(proporcao_palco - proporcao_midia) > 0.02:
                raise RuntimeError(
                    f"[{ferramenta}] palco {view.stage_width}x{view.stage_height} perdeu a proporcao "
                    f"da midia ({proporcao_palco:.3f} vs {proporcao_midia:.3f})"
                )
            # 3) aproveita todo o espaco: encosta na LARGURA ou na ALTURA disponivel
            if (
                abs(view.stage_width - disponivel_largura) > 2
                and abs(view.stage_height - disponivel_altura) > 2
            ):
                raise RuntimeError(
                    f"[{ferramenta}] palco {view.stage_width}x{view.stage_height} nao aproveita o espaco "
                    f"disponivel ({disponivel_largura:.0f}x{disponivel_altura:.0f})"
                )
            # 4) nunca fica em cima do widget seguinte da aba
            irmaos = [filho for filho in aba.winfo_children() if filho is not holder]
            abaixo = [filho for filho in irmaos if filho.winfo_y() >= holder.winfo_y()]
            if abaixo:
                primeiro = min(abaixo, key=lambda filho: filho.winfo_y())
                if holder.winfo_y() + holder.winfo_height() > primeiro.winfo_y():
                    raise RuntimeError(
                        f"[{ferramenta}] o palco invade o controle seguinte "
                        f"({holder.winfo_y() + holder.winfo_height()} > {primeiro.winfo_y()})"
                    )

            # 5) o quadro preenche o palco e o zoom/arrasto respeitam os limites
            panel.preview_stills[canvas] = Image.new("RGB", (largura, altura), (0, 0, 255))
            panel._paint_preview_view(canvas)
            root.update()
            bbox = canvas.bbox("all")
            # O quadro desenhado é arredondado para par (exigência do FFmpeg),
            # então a cobertura do palco pode ficar 1px menor de cada lado.
            if bbox is None or bbox[0] > 0 or bbox[1] > 0 or bbox[2] < view.stage_width - 2 or bbox[3] < view.stage_height - 2:
                raise RuntimeError(
                    f"[{ferramenta}] quadro nao preenche o palco no zoom 1.0: "
                    f"{bbox} vs palco {view.stage_width}x{view.stage_height}"
                )

            if panel._preview_wheel(canvas, _preview_event(view.stage_width // 2, view.stage_height // 2, 120)) != "break":
                raise RuntimeError(f"[{ferramenta}] a roda nao foi consumida pelo palco (rolaria a aba)")
            root.update()
            if view.zoom <= 1.0:
                raise RuntimeError(f"[{ferramenta}] roda para cima nao aproximou (zoom={view.zoom})")

            # Roda de VERDADE pelo Tk (o evento real manda '??' nos campos que não
            # existem — foi assim que o log recebeu "int() with base 10: '??'").
            erros: list = []
            handler_original = root.report_callback_exception
            root.report_callback_exception = lambda *args: erros.append(args)
            zoom_antes = view.zoom
            try:
                for delta in (120, 120, -120):
                    canvas.event_generate(
                        "<MouseWheel>",
                        delta=delta,
                        x=view.stage_width // 2,
                        y=view.stage_height // 2,
                    )
                    root.update()
            finally:
                root.report_callback_exception = handler_original
            if erros:
                raise RuntimeError(f"[{ferramenta}] a roda do mouse gerou erro interno: {erros[0][1]!r}")
            if abs(view.zoom - zoom_antes) < 1e-6:
                raise RuntimeError(f"[{ferramenta}] a roda real do Tk nao mudou o zoom ({zoom_antes})")
            desenhado = preview_drawn_size(view.stage_width, view.stage_height, view.zoom)[:2]
            origem = preview_view_rect(
                view.stage_width, view.stage_height, desenhado[0], desenhado[1], view.offset_x, view.offset_y
            )
            if (
                origem[0] > 0
                or origem[1] > 0
                or origem[0] + desenhado[0] < view.stage_width
                or origem[1] + desenhado[1] < view.stage_height
            ):
                raise RuntimeError(
                    f"[{ferramenta}] com zoom o fundo do palco aparece: origem={origem} desenhado={desenhado}"
                )

            antes = (view.offset_x, view.offset_y)
            panel._preview_pan_start(canvas, _preview_event(view.stage_width // 2, view.stage_height // 2))
            panel._preview_pan_move(canvas, _preview_event(0, 0))
            panel._preview_pan_end(canvas)
            if (view.offset_x, view.offset_y) == antes:
                raise RuntimeError(f"[{ferramenta}] mover o vídeo ampliado nao mudou o quadro")
            if view.offset_x > 0 or view.offset_y > 0:
                raise RuntimeError(
                    f"[{ferramenta}] o movimento deixou fundo aparecer no palco: {view.offset_x}, {view.offset_y}"
                )
            panel._preview_pan_move(canvas, _preview_event(-9000, -9000))
            limite = (view.stage_width - desenhado[0], view.stage_height - desenhado[1])
            if (view.offset_x, view.offset_y) != limite:
                raise RuntimeError(
                    f"[{ferramenta}] arrasto passou do limite: {view.offset_x}, {view.offset_y} vs {limite}"
                )

            panel._reset_preview_view(canvas, largura, altura)
            panel.preview_stills.pop(canvas, None)
            root.update()

        # 6) girar 90 graus troca a proporcao do palco
        panel._select_ffmpeg_tool("Girar vídeo")
        view = panel.preview_viewports[panel.rotate_preview]
        panel._reset_preview_view(panel.rotate_preview, 1920, 1080)
        paisagem = (view.stage_width, view.stage_height)
        panel.rotate_media_profile = MediaProfile(10.0, True, 1920, 1080, "30", "1M", "128k", 48000, 2, "stereo")
        panel.rotate_degrees_var.set("90")
        panel._apply_rotate_media_size()
        root.update()
        retrato = (view.stage_width, view.stage_height)
        if retrato[0] >= retrato[1] or retrato == paisagem:
            raise RuntimeError(f"girar 90 graus nao trocou a proporcao do palco: {paisagem} -> {retrato}")
        panel.rotate_media_profile = None
        panel._select_ffmpeg_tool("Cortar")
        root.update()
    finally:
        if not mapeado:
            root.withdraw()


def _check_ffmpeg_output_rows(app, root) -> None:
    """Pasta de saída dentro de cada ferramenta (pedido de 12/09).

    Botões "Abrir pasta"/"Escolher pasta" na MESMA linha de opções da ferramenta
    e o caminho da pasta na linha de baixo. E, no Cortar, os campos Início/Fim
    centralizados na mesma coluna do botão PLAY.
    """
    from tkinter import ttk

    panel = app.ffmpeg_tools
    app.select_main_tab("ffmpeg")
    mapeado = bool(root.winfo_ismapped())
    if not mapeado:
        root.deiconify()
        root.update()

    def descendentes(widget):
        for filho in widget.winfo_children():
            yield filho
            yield from descendentes(filho)

    def por_texto(aba, textos, classe):
        return [
            widget
            for widget in descendentes(aba)
            if isinstance(widget, classe) and widget.cget("text") in textos
        ]

    try:
        for ferramenta, aba in (
            ("Cortar", panel.cut_tab),
            ("Extrair áudio", panel.extract_tab),
            ("Girar vídeo", panel.rotate_tab),
            ("Juntar áudios/vídeos", panel.join_tab),
            ("Inserir áudio", panel.insert_tab),
            ("Limpar áudio", panel.clean_tab),
        ):
            panel._select_ffmpeg_tool(ferramenta)
            root.update()
            botoes = por_texto(aba, ("Abrir pasta", "Escolher pasta"), ttk.Button)
            caminhos = por_texto(aba, ("Pasta de saída:",), ttk.Label)
            if len(botoes) != 2:
                raise RuntimeError(f"[{ferramenta}] esperava 2 botões de pasta, achei {len(botoes)}")
            if len(caminhos) != 1:
                raise RuntimeError(f"[{ferramenta}] esperava 1 linha de caminho, achei {len(caminhos)}")
            abrir, escolher = sorted(botoes, key=lambda widget: widget.winfo_rootx())
            if abs(abrir.winfo_rooty() - escolher.winfo_rooty()) > 2:
                raise RuntimeError(f"[{ferramenta}] os dois botões de pasta não estão na mesma linha")
            pai = abrir.master
            if escolher.master is not pai:
                raise RuntimeError(f"[{ferramenta}] os botões de pasta estão em linhas diferentes")
            # Mesma linha das OPÇÕES: algum controle da ferramenta divide a linha
            # com os botões (nas abas com grade os botões ficam numa célula própria).
            topo = abrir.winfo_rooty()
            base = topo + abrir.winfo_height()
            dividem = [
                widget
                for widget in descendentes(aba)
                if isinstance(widget, (ttk.Label, ttk.Combobox, ttk.Checkbutton, ttk.Entry))
                and widget.winfo_ismapped()
                and widget is not abrir
                and widget is not escolher
                and widget.winfo_rooty() < base - 2
                and widget.winfo_rooty() + widget.winfo_height() > topo + 2
            ]
            if not dividem:
                raise RuntimeError(
                    f"[{ferramenta}] os botões de pasta não estão na linha das opções"
                )
            if caminhos[0].winfo_rooty() <= abrir.winfo_rooty():
                raise RuntimeError(f"[{ferramenta}] o caminho da pasta não está na linha de baixo")
            # Adjacência exata onde o usuário pediu (Cortar): o caminho vem na
            # linha imediatamente seguinte à dos botões.
            if ferramenta == "Cortar" and caminhos[0].master.winfo_rooty() >= abrir.winfo_rooty() + abrir.winfo_height() + 6:
                raise RuntimeError(f"[{ferramenta}] o caminho da pasta ficou longe dos botões")

        # Início/Fim do Cortar alinhados com o botão PLAY (centro horizontal).
        panel._select_ffmpeg_tool("Cortar")
        root.update()
        inicio = por_texto(panel.cut_tab, ("Início (segundos):",), ttk.Label)[0]
        linha = inicio.master
        centro_linha = linha.winfo_rootx() + linha.winfo_width() / 2
        play = panel.cut_play_button
        centro_play = play.winfo_rootx() + play.winfo_width() / 2
        if abs(centro_linha - centro_play) > 4:
            raise RuntimeError(
                f"os campos Início/Fim não estão alinhados com o botão PLAY: "
                f"centro dos campos={centro_linha:.0f}px, centro do PLAY={centro_play:.0f}px"
            )
    finally:
        if not mapeado:
            root.withdraw()


def _check_live_mic_icons(app, root) -> None:
    """Os botoes da aba Ocorrencia desenham os PNGs de assets/ (pedido de 12/09).

    Em repouso, os dois microfones e o botao de pausar (quando ativo) mostram o
    icone PNG — um unico item de imagem no canvas. Durante a gravacao o desenho
    vetorial (check verde / circulo amarelo com triangulo) volta a valer.
    """
    import sig_app

    def itens(canvas):
        return [canvas.type(item) for item in canvas.find_all()]

    estado = (
        app.live_state,
        app.normal_recording,
        app.normal_record_paused,
    )
    try:
        for kind, canvas in (
            ("mic_vermelho", app.live_mic_canvas),
            ("mic_branco", app.live_normal_mic_canvas),
        ):
            if itens(canvas) != ["image"]:
                raise RuntimeError(
                    f"{kind}: canvas em repouso com itens {itens(canvas)} "
                    "(esperado o PNG)"
                )
            photo = app._live_icon_photo(kind)
            if (photo.width(), photo.height()) != (sig_app.LIVE_ICON_SIZE,) * 2:
                raise RuntimeError(
                    f"{kind}: icone {photo.width()}x{photo.height()}px "
                    f"(esperado {sig_app.LIVE_ICON_SIZE}px)"
                )
            item = canvas.find_all()[0]
            if canvas.itemcget(item, "image") != str(photo):
                raise RuntimeError(f"{kind}: o canvas nao usa a imagem carregada")

        if itens(app.live_pause_canvas):
            raise RuntimeError("pause: o botao tem que ficar vazio quando nao ha gravacao")

        app.live_state = "listening"
        app._draw_live_mic_button()
        app.normal_recording = True
        app._draw_normal_live_mic_button()
        app._draw_live_pause_button()
        if itens(app.live_mic_canvas) != ["oval", "line", "line"]:
            raise RuntimeError("gravando: o microfone vermelho perdeu o check verde")
        if itens(app.live_normal_mic_canvas) != ["oval", "line", "line"]:
            raise RuntimeError("gravando: o microfone branco perdeu o check verde")
        if itens(app.live_pause_canvas) != ["image"]:
            raise RuntimeError("gravando: o botao de pausar nao mostra o icone de pausa")

        app.normal_record_paused = True
        app._draw_live_pause_button()
        if itens(app.live_pause_canvas) != ["oval", "polygon"]:
            raise RuntimeError("pausado: o botao nao mostra o triangulo de retomar")
    finally:
        app.live_state, app.normal_recording, app.normal_record_paused = estado
        app._draw_live_mic_button()
        app._draw_normal_live_mic_button()
        app._draw_live_pause_button()
        root.update_idletasks()


def _check_ffmpeg_stage_hints(app, root) -> None:
    """Dica do palco: única, completa e centralizada no tamanho ATUAL (12/09).

    Bug relatado: sobrava um pedaço do texto no meio da tela ("lizar" no Girar,
    "ou ouvir" no Extrair) porque a dica era criada no tamanho mínimo do palco e
    nunca redesenhada quando ele crescia.
    """
    panel = app.ffmpeg_tools
    app.select_main_tab("ffmpeg")
    mapeado = bool(root.winfo_ismapped())
    if not mapeado:
        root.deiconify()
        root.update()
    esperado = {
        "Cortar": "Selecione uma mídia para visualizar",
        "Extrair áudio": "Escolha um arquivo para visualizar ou ouvir",
        "Girar vídeo": "Selecione um vídeo para visualizar",
    }
    try:
        for ferramenta, texto in esperado.items():
            panel._select_ffmpeg_tool(ferramenta)
            root.update()
            canvas = {
                "Cortar": panel.cut_preview,
                "Extrair áudio": panel.extract_preview,
                "Girar vídeo": panel.rotate_preview,
            }[ferramenta]
            # cenário real do bug: palco SEM mídia e que acabou de crescer
            panel.preview_frames.pop(canvas, None)
            panel.preview_stills.pop(canvas, None)
            panel.preview_frame_items.pop(canvas, None)
            panel.preview_viewports[canvas].stage_width = 0   # força reencaixe
            panel._reset_preview_view(canvas, 1920, 1080)
            root.update()
            textos = [item for item in canvas.find_all() if canvas.type(item) == "text"]
            if len(textos) != 1:
                raise RuntimeError(
                    f"[{ferramenta}] esperava UMA dica no palco, achei {len(textos)}: "
                    f"{[canvas.itemcget(item, 'text') for item in textos]}"
                )
            conteudo = str(canvas.itemcget(textos[0], "text"))
            if conteudo != texto:
                raise RuntimeError(f"[{ferramenta}] dica diferente do esperado: {conteudo!r}")
            coords = canvas.coords(textos[0])
            centro_x, centro_y = canvas.winfo_width() / 2, canvas.winfo_height() / 2
            if abs(coords[0] - centro_x) > 3 or abs(coords[1] - centro_y) > 3:
                raise RuntimeError(
                    f"[{ferramenta}] dica fora do centro do palco: {coords} x centro "
                    f"({centro_x:.0f}, {centro_y:.0f})"
                )
            # o texto tem que caber: a dica do Extrair é a mais longa
            bbox = canvas.bbox(textos[0])
            if bbox and (bbox[0] < 0 or bbox[2] > canvas.winfo_width() + 2):
                raise RuntimeError(f"[{ferramenta}] dica cortada nas laterais: {bbox}")
    finally:
        if not mapeado:
            root.withdraw()


def _check_ffmpeg_timeline_markers(app, root) -> None:
    """Marcadores da linha do tempo: orientação e limites da cabeça (12/09)."""
    import tkinter as tk

    panel = app.ffmpeg_tools
    app.select_main_tab("ffmpeg")
    mapeado = bool(root.winfo_ismapped())
    if not mapeado:
        root.deiconify()
        root.update()
    try:
        panel._select_ffmpeg_tool("Cortar")
        root.update()
        linha = panel.cut_timeline
        linha.set_media(20.0)
        linha.set_range(4.0, 12.0)
        root.update()

        # 1) orientação real dos triângulos (geometria do canvas)
        def triangulo(cor: str):
            for item in linha.find_all():
                if linha.type(item) == "polygon" and str(linha.itemcget(item, "fill")) == cor:
                    coords = linha.coords(item)
                    return [(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)]
            return None

        verde = triangulo("#2e7d5a")
        vermelho = triangulo("#c64a42")
        if not verde or not vermelho:
            raise RuntimeError("não encontrei os triângulos verde e vermelho na linha do tempo")
        ponta_verde = verde[0][1]
        base_verde = verde[1][1]
        if ponta_verde <= base_verde:
            raise RuntimeError(f"o triângulo verde (início) não aponta para baixo: {verde}")
        ponta_vermelha = vermelho[0][1]
        base_vermelha = vermelho[1][1]
        if ponta_vermelha >= base_vermelha:
            raise RuntimeError(f"o triângulo vermelho (fim) não aponta para cima: {vermelho}")

        # 2) a cabeça não passa dos marcadores — nem forçada pela API...
        linha.set_position(999.0)
        if linha.position != 12.0:
            raise RuntimeError(f"set_position passou do marcador vermelho: {linha.position}")
        linha.set_position(-50.0)
        if linha.position != 4.0:
            raise RuntimeError(f"set_position passou do marcador verde: {linha.position}")

        # ...nem pelo arrasto do usuário (eventos de verdade do Tk)
        largura = max(200, linha.winfo_width())
        altura = linha.winfo_height() or 52
        centro_y = altura // 2
        linha.event_generate("<Button-1>", x=largura - 2, y=centro_y)
        root.update()
        linha.event_generate("<B1-Motion>", x=largura - 2, y=centro_y)
        root.update()
        linha.event_generate("<ButtonRelease-1>", x=largura - 2, y=centro_y)
        root.update()
        if linha.position > linha.end + 0.001:
            raise RuntimeError(f"arrasto para a direita passou do marcador vermelho: {linha.position}")
        linha.event_generate("<Button-1>", x=0, y=centro_y)
        root.update()
        linha.event_generate("<B1-Motion>", x=0, y=centro_y)
        root.update()
        linha.event_generate("<ButtonRelease-1>", x=0, y=centro_y)
        root.update()
        if linha.position < linha.start - 0.001:
            raise RuntimeError(f"arrasto para a esquerda passou do marcador verde: {linha.position}")

        # 3) mover os marcadores por cima da cabeça empurra a cabeça para dentro
        linha.set_position(11.0)
        linha.set_range(2.0, 5.0)
        root.update()
        if not (5.0 - 0.001 <= linha.position <= 5.0 + 0.001):
            raise RuntimeError(f"a cabeça não foi empurrada para dentro do trecho: {linha.position}")
    finally:
        if not mapeado:
            root.withdraw()


def _check_ffmpeg_encoder_selector(app, root) -> None:
    """Seletor de encoder: GPU/CPU no principal e Avançado só no modo GPU (12/09)."""
    from video_encoders import ENCODER_PATH_CPU, ENCODER_PATH_GPU, PATH_LABELS

    panel = app.ffmpeg_tools
    app.select_main_tab("ffmpeg")
    mapeado = bool(root.winfo_ismapped())
    if not mapeado:
        root.deiconify()
        root.update()
    try:
        panel._select_ffmpeg_tool("Cortar")
        root.update()
        combo = panel.acceleration_combo
        if tuple(combo.cget("values")) != (PATH_LABELS[ENCODER_PATH_GPU], PATH_LABELS[ENCODER_PATH_CPU]):
            raise RuntimeError(f"o seletor principal nao e GPU/CPU: {combo.cget('values')}")
        if panel._encoder_path() != ENCODER_PATH_GPU:
            raise RuntimeError(f"o padrao deveria ser GPU: {panel._encoder_path()}")
        # Avancado visivel no modo GPU e escondido no modo CPU
        panel._refresh_encoder_control_state()
        root.update()
        gpu_avancado = panel.encoder_advanced_combo.winfo_manager()
        disponiveis = panel._advanced_labels()
        if len(disponiveis) > 1 and gpu_avancado != "pack":
            raise RuntimeError("o Avancado nao apareceu no modo GPU")
        if disponiveis[0] != panel.ENCODER_ADVANCED_AUTO_LABEL:
            raise RuntimeError(f"o Avancado nao comeca pelo Automático: {disponiveis}")
        for rotulo in disponiveis[1:]:
            if rotulo not in [option.label for option in panel.available_encoder_options]:
                raise RuntimeError(f"o Avancado oferece encoder que nao passou na sondagem: {rotulo}")
        panel.acceleration_var.set(PATH_LABELS[ENCODER_PATH_CPU])
        panel._on_encoder_path_changed()
        root.update()
        if panel.encoder_advanced_combo.winfo_manager():
            raise RuntimeError("o Avancado continuou visivel no modo CPU")
        if panel.encoder_advanced_var.get() != panel.ENCODER_ADVANCED_AUTO_LABEL:
            raise RuntimeError("o Avancado perdeu o Automático ao trocar para CPU")
        panel.acceleration_var.set(PATH_LABELS[ENCODER_PATH_GPU])
        panel._on_encoder_path_changed()
        root.update()
        # o "?" abre a explicacao dos dois caminhos
        with patch("ffmpeg_tools_panel.messagebox.showinfo") as aviso:
            panel.encoder_help_button.invoke()
        if not aviso.called:
            raise RuntimeError("o '?' do encoder nao abriu a explicacao")
        texto = aviso.call_args[0][1]
        for trecho in ("GPU", "CPU", "Avançado"):
            if trecho not in texto:
                raise RuntimeError(f"a explicacao do encoder nao fala de {trecho!r}")
    finally:
        if not mapeado:
            root.withdraw()


def _check_ffmpeg_cut_modes(app, root) -> None:
    """Seletor de modos de corte: três opções, ordem, padrão e o "?" (12/09)."""
    from ffmpeg_tools_panel import CUT_MODE_HELP, CUT_MODES

    panel = app.ffmpeg_tools
    app.select_main_tab("ffmpeg")
    mapeado = bool(root.winfo_ismapped())
    if not mapeado:
        root.deiconify()
        root.update()
    try:
        panel._select_ffmpeg_tool("Cortar")
        root.update()
        combo = panel.cut_mode_combo
        if tuple(combo.cget("values")) != CUT_MODES:
            raise RuntimeError(f"opções do seletor de corte fora de ordem: {combo.cget('values')}")
        if tuple(CUT_MODES) != ("SmartCut", "Reencode Completo", "Sem Reencode"):
            raise RuntimeError(f"rótulos inesperados: {CUT_MODES}")
        if panel.cut_mode_var.get() != "SmartCut":
            raise RuntimeError(f"o padrão do corte não é SmartCut: {panel.cut_mode_var.get()}")
        if combo.winfo_reqwidth() < 10:
            raise RuntimeError("o seletor de corte não está visível")
        # o "?" fica logo à direita do seletor e explica os três modos
        ajuda = panel.cut_mode_help_button
        if not ajuda.winfo_ismapped():
            raise RuntimeError("o botão '?' dos modos de corte não está visível")
        if ajuda.winfo_rootx() < combo.winfo_rootx():
            raise RuntimeError("o '?' ficou à esquerda do seletor de corte")
        with patch("ffmpeg_tools_panel.messagebox.showinfo") as aviso:
            ajuda.invoke()
        if not aviso.called:
            raise RuntimeError("o '?' não abriu a explicação dos modos")
        texto = aviso.call_args[0][1] if len(aviso.call_args[0]) > 1 else ""
        if texto != CUT_MODE_HELP:
            raise RuntimeError("a explicação dos modos não é a esperada")
        for trecho in ("SmartCut", "EXPERIMENTAL", "Reencode Completo", "Sem Reencode"):
            if trecho not in texto:
                raise RuntimeError(f"a explicação dos modos não fala de {trecho!r}")
        # trocar o modo não pode quebrar o controle de encoder
        for modo in CUT_MODES:
            panel.cut_mode_var.set(modo)
            panel._update_cut_controls()
            root.update()
        panel.cut_mode_var.set("SmartCut")
        panel._update_cut_controls()
        root.update()
    finally:
        if not mapeado:
            root.withdraw()


def _check_ffmpeg_area_selection(app, root) -> None:
    """Seleção de área com eventos REAIS do Tk (pedido de 12/09).

    Desenha o quadro com o botão esquerdo, confere que ele fica sobre os pixels
    escolhidos (acompanha o zoom), que os cantos redimensionam, que o botão
    direito oferece "Desfazer seleção" e que o recorte em pixels sai certo.
    """
    from PIL import Image

    from ffmpeg_tools_panel import MediaProfile, PreviewSelection, selection_handle_at

    panel = app.ffmpeg_tools
    app.select_main_tab("ffmpeg")
    mapeado = bool(root.winfo_ismapped())
    if not mapeado:
        root.deiconify()
        root.update()
    try:
        panel._select_ffmpeg_tool("Cortar")
        canvas = panel.cut_preview
        panel._reset_preview_view(canvas, 1920, 1080)
        panel.preview_stills[canvas] = Image.new("RGB", (1920, 1080), (0, 0, 255))
        panel._paint_preview_view(canvas)
        root.update()
        view = panel.preview_viewports[canvas]
        largura, altura = view.stage_width, view.stage_height

        # 1) desenhar com o botão DIREITO (eventos de verdade do Tk)
        erros: list = []
        handler_original = root.report_callback_exception
        root.report_callback_exception = lambda *args: erros.append(args)
        try:
            canvas.event_generate("<ButtonPress-3>", x=int(largura * 0.25), y=int(altura * 0.25))
            root.update()
            canvas.event_generate("<B3-Motion>", x=int(largura * 0.45), y=int(altura * 0.45))
            root.update()
            canvas.event_generate("<B3-Motion>", x=int(largura * 0.75), y=int(altura * 0.75))
            root.update()
            canvas.event_generate("<ButtonRelease-3>", x=int(largura * 0.75), y=int(altura * 0.75))
            root.update()
        finally:
            root.report_callback_exception = handler_original
        if erros:
            raise RuntimeError(f"a seleção de área gerou erro interno: {erros[0][1]!r}")
        selecao = panel.preview_selections.get(canvas)
        if selecao is None:
            raise RuntimeError("arrastar com o botão direito não criou a seleção")
        if abs(selecao.left - 0.25) > 0.02 or abs(selecao.right - 0.75) > 0.02:
            raise RuntimeError(f"a seleção não ficou onde foi desenhada: {selecao}")

        # 1b) o botão ESQUERDO continua arrastando o vídeo (não cria seleção)
        panel._preview_wheel(canvas, _preview_event(largura // 2, altura // 2, 120))
        root.update()
        deslocamento_antes = (view.offset_x, view.offset_y)
        canvas.event_generate("<ButtonPress-1>", x=largura // 2, y=altura // 2)
        root.update()
        canvas.event_generate("<B1-Motion>", x=largura // 2 - 40, y=altura // 2 - 20)
        root.update()
        canvas.event_generate("<ButtonRelease-1>", x=largura // 2 - 40, y=altura // 2 - 20)
        root.update()
        if (view.offset_x, view.offset_y) == deslocamento_antes:
            raise RuntimeError("o botão esquerdo não arrastou o vídeo ampliado")
        if panel.preview_selections.get(canvas) != selecao:
            raise RuntimeError("o arrasto com o botão esquerdo mexeu na seleção")

        # 2) o recorte em pixels bate com o desenho (metade central do quadro).
        #    Tolerância de 3px: largura do palco varia com a janela do gate.
        crop = panel.preview_selections and panel._preview_selection_crop(canvas, 1920, 1080)
        esperado = (480, 270, 960, 540)
        if crop is None or any(abs(atual - alvo) > 3 for atual, alvo in zip(crop, esperado)):
            raise RuntimeError(f"recorte em pixels inesperado: {crop} (esperado ~{esperado})")

        # 3) a seleção segue o zoom (mesmos pixels, outra escala)
        from ffmpeg_tools_panel import preview_fraction_from_view

        def fracao_do_canto():
            ox, oy, dw, dh = panel._preview_frame_transform(canvas)
            rect = panel._preview_selection_view_rect(canvas)
            return preview_fraction_from_view(rect[0], rect[1], dw, dh, ox, oy)

        antes = panel._preview_selection_view_rect(canvas)
        fracao_antes = fracao_do_canto()
        zoom_antes = view.zoom
        panel._preview_wheel(canvas, _preview_event(largura // 2, altura // 2, 240))
        root.update()
        depois = panel._preview_selection_view_rect(canvas)
        fracao_depois = fracao_do_canto()
        if view.zoom <= zoom_antes:
            raise RuntimeError("a roda não aproximou o vídeo")
        if depois == antes:
            raise RuntimeError("a seleção não acompanhou o zoom")
        if abs(fracao_antes[0] - fracao_depois[0]) > 0.02 or abs(fracao_antes[1] - fracao_depois[1]) > 0.02:
            raise RuntimeError(
                f"o zoom deslocou a seleção dos pixels escolhidos: {fracao_antes} -> {fracao_depois}"
            )

        # 4) redimensionar por um canto (arrastando a alça sudeste com o direito)
        rect = panel._preview_selection_view_rect(canvas)
        if selection_handle_at(rect, rect[2], rect[3]) != "se":
            raise RuntimeError("a alça do canto sudeste não foi reconhecida")
        panel._preview_select_press(canvas, _preview_event(rect[2], rect[3]))
        panel._preview_select_motion(canvas, _preview_event(rect[2] + 40, rect[3] + 20))
        panel._preview_select_release(canvas, _preview_event(rect[2] + 40, rect[3] + 20))
        root.update()
        redimensionada = panel.preview_selections.get(canvas)
        if redimensionada is None or redimensionada.right <= selecao.right:
            raise RuntimeError("a seleção não foi redimensionada pela alça")
        if redimensionada.right > 1.0 or redimensionada.bottom > 1.0:
            raise RuntimeError(f"a seleção saiu do vídeo: {redimensionada}")

        # 5) clique PARADO com o direito sobre a seleção abre o menu (e ele apaga)
        menus: list = []
        menu_original = tk.Menu.tk_popup
        tk.Menu.tk_popup = lambda self, *_args: menus.append(self)
        try:
            root.report_callback_exception = lambda *args: erros.append(args)
            rect = panel._preview_selection_view_rect(canvas)
            centro_x = int((rect[0] + rect[2]) / 2)
            centro_y = int((rect[1] + rect[3]) / 2)
            canvas.event_generate("<ButtonPress-3>", x=centro_x, y=centro_y)
            root.update()
            canvas.event_generate("<ButtonRelease-3>", x=centro_x, y=centro_y)
            root.update()
            if erros:
                raise RuntimeError(f"o clique direito gerou erro interno: {erros[0][1]!r}")
        finally:
            tk.Menu.tk_popup = menu_original
            root.report_callback_exception = handler_original
        if not menus:
            raise RuntimeError("o clique direito sobre a seleção não abriu o menu")
        rotulos = [menus[-1].entrycget(indice, "label") for indice in range(menus[-1].index("end") + 1)]
        if "Desfazer seleção" not in rotulos:
            raise RuntimeError(f"o menu do botão direito não tem 'Desfazer seleção': {rotulos}")
        if panel.preview_selections.get(canvas) is None:
            raise RuntimeError("o clique parado do botão direito apagou a seleção sem passar pelo menu")
        panel._clear_preview_selection(canvas)
        root.update()
        if panel.preview_selections.get(canvas) is not None:
            raise RuntimeError("a seleção não foi apagada")
        if canvas.find_withtag("preview_selection"):
            raise RuntimeError("o desenho da seleção continuou no palco")

        # 6) aviso do Executar: com seleção, cancelar não executa
        panel.cut_media_profile = MediaProfile(
            10.0, True, 1920, 1080, "30", "1M", "128k", 48000, 2, "stereo"
        )
        panel.preview_selections[canvas] = PreviewSelection(0.25, 0.25, 0.75, 0.75)
        with patch("ffmpeg_tools_panel.messagebox.askokcancel", return_value=False) as aviso:
            panel.run_current_tool()
            if not aviso.called:
                raise RuntimeError("Executar com seleção não avisou o usuário")
            mensagem = aviso.call_args[0][1]
            if "960 x 540" not in mensagem:
                raise RuntimeError(f"o aviso não informou a resolução da seleção: {mensagem!r}")
        if panel.running:
            raise RuntimeError("o app executou mesmo com o usuário cancelando o aviso")

        # 7) Girar: a seleção desenhada gira junto para cobrir os MESMOS pixels
        panel._select_ffmpeg_tool("Girar vídeo")
        root.update()
        girar = panel.rotate_preview
        panel.rotate_media_profile = MediaProfile(
            10.0, True, 1920, 1080, "30", "1M", "128k", 48000, 2, "stereo"
        )
        panel.rotate_degrees_var.set("0")
        panel._reset_preview_view(girar, 1920, 1080)
        panel.preview_stills[girar] = Image.new("RGB", (1920, 1080), (0, 200, 0))
        panel._paint_preview_view(girar)
        root.update()
        view_girar = panel.preview_viewports[girar]
        panel._preview_select_press(girar, _preview_event(view_girar.stage_width * 0.2, view_girar.stage_height * 0.1))
        panel._preview_select_motion(girar, _preview_event(view_girar.stage_width * 0.6, view_girar.stage_height * 0.3))
        panel._preview_select_release(girar, _preview_event(view_girar.stage_width * 0.6, view_girar.stage_height * 0.3))
        root.update()
        antes_da_selecao = panel.preview_selections.get(girar)
        corte_antes = panel._selection_crops()["rotate_crop"]
        if antes_da_selecao is None or corte_antes is None:
            raise RuntimeError("não consegui desenhar a seleção na aba Girar")
        if panel.preview_selection_filters.get(girar, None) != "":
            raise RuntimeError("a seleção não guardou os filtros de giro em vigor")

        panel.rotate_degrees_var.set("90")
        # Só a parte do giro (sem gerar miniatura: o check não pode depender de ffmpeg).
        # A ligação com _refresh_rotate_thumbnail é coberta pelo teste AST.
        panel._rotate_selection_with_filters()
        panel._apply_rotate_media_size()
        root.update()
        depois_da_selecao = panel.preview_selections.get(girar)
        corte_depois = panel._selection_crops()["rotate_crop"]
        if depois_da_selecao == antes_da_selecao:
            raise RuntimeError("girar 90 graus não girou a seleção junto")
        if panel.preview_selection_filters.get(girar) != "transpose=1":
            raise RuntimeError("a seleção não passou a registrar o giro novo")
        # o palco virou retrato (proporção trocada) e a seleção acompanhou
        if view_girar.stage_height <= view_girar.stage_width:
            raise RuntimeError(
                f"o palco não trocou de proporção ao girar: {view_girar.stage_width}x{view_girar.stage_height}"
            )
        if corte_depois is None or corte_depois[2] >= corte_antes[2]:
            raise RuntimeError(
                f"o recorte não acompanhou o giro: {corte_antes} -> {corte_depois}"
            )
        # a área (em pixels) tem que ser a mesma, só trocada de eixos
        if abs(corte_depois[2] - corte_antes[3]) > 4 or abs(corte_depois[3] - corte_antes[2]) > 4:
            raise RuntimeError(
                f"o recorte girado não cobre os mesmos pixels: {corte_antes} -> {corte_depois}"
            )
        panel.rotate_media_profile = None
        panel.rotate_degrees_var.set("0")
        panel._clear_preview_selection(girar)
        panel.preview_stills.pop(girar, None)
        panel._select_ffmpeg_tool("Cortar")
        root.update()
        panel._clear_preview_selection(canvas)
        panel.preview_stills.pop(canvas, None)
        panel.cut_media_profile = None
        root.update()
    finally:
        if not mapeado:
            root.withdraw()


def _preview_event(x: int, y: int, delta: int = 0):
    evento = tk.Event()
    evento.x = x
    evento.y = y
    evento.delta = delta
    evento.num = 0
    return evento


def _check_activity_log_scroll(app, root) -> None:
    """Vacina do pedido de 13/09: a atualizacao do log nao pode mover a barra.

    Antes, cada atualizacao (inclusive a linha viva "Convertendo/Transcrevendo
    arquivos: N/M") puxava a vista para o fim — com o usuario lendo mais acima
    nao dava para usar o log com o app trabalhando. Agora o log acompanha o fim
    so enquanto o usuario esta no fim; rolando para cima, nada mais se mexe;
    voltando ao fim, o acompanhamento volta.
    """
    log = app.activity_log
    mapeado = bool(root.winfo_ismapped())
    try:
        root.deiconify()
        root.update()

        def limpar() -> None:
            log.configure(state="normal")
            log.delete("1.0", "end")
            log.configure(state="disabled")

        limpar()
        app._activity_log_tail_following = True
        linhas = max(40, (log.winfo_height() // 12) + 10)
        for indice in range(linhas):
            app._append_activity_log(f"linha {indice} do log de atividade")
        root.update()
        if log.dlineinfo(log.index("end-1c linestart")) is None:
            raise RuntimeError("o log nao acompanhou o fim com a barra no fim")

        # O usuario rola para cima (pela barra, como no relato).
        app._activity_log_scrollbar_command("moveto", "0.1")
        root.update()
        if app._activity_log_tail_following:
            raise RuntimeError("a barra nao registrou a leitura mais acima")
        topo = log.index("@0,0")

        # Atualizacoes do fluxo real: linha viva + linhas novas + etapa.
        app._update_activity_line("convert", "Convertendo arquivos: 3/10 (30%)")
        app._update_activity_line("transcribe", "Transcrevendo arquivos: 3/10 (30%)")
        app._append_activity_log("mensagem nova com a leitura em andamento")
        app._begin_activity_step("smoke:etapa", "Etapa de teste")
        app._finish_activity_step("smoke:etapa", 0.5)
        root.update()
        if log.index("@0,0") != topo:
            raise RuntimeError(
                f"a atualizacao moveu a barra: topo {topo} -> {log.index('@0,0')}"
            )
        if log.dlineinfo(log.index("end-1c linestart")) is not None:
            raise RuntimeError("a atualizacao arrastou a vista para o fim do log")

        # Voltando ao fim, o log volta a acompanhar.
        app._activity_log_scrollbar_command("moveto", "1.0")
        root.update()
        app._append_activity_log("mensagem depois de voltar ao fim")
        root.update()
        if log.dlineinfo(log.index("end-1c linestart")) is None:
            raise RuntimeError("o log nao voltou a acompanhar depois de voltar ao fim")

        # Roda do mouse para cima (delta positivo no Tk/Windows): o
        # acompanhamento tem que cair, senao a proxima escrita puxaria a vista.
        log.event_generate("<MouseWheel>", delta=120)
        root.update()
        if app._activity_log_tail_following:
            raise RuntimeError("a roda do mouse para cima nao marcou a leitura mais acima")

        limpar()
        app._activity_log_tail_following = True
    finally:
        if not mapeado:
            root.withdraw()
        root.update_idletasks()


def _check_batch_log_lines(app, root) -> None:
    """Erros agregados por tipo + arquivos ja prontos no log (pedido de 13/09).

    Com o Tk de verdade: cada tipo de erro tem UMA linha (com a contagem), a
    linha de arquivos prontos NAO e vermelha, o horario continua o da primeira
    ocorrencia e a atualizacao NAO embaralha a ordem das linhas vivas (marca +
    deslocamento — antes cada atualizacao jogava a linha para o fim).
    """
    log = app.activity_log
    mapeado = bool(root.winfo_ismapped())
    try:
        root.deiconify()
        root.update()
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        app._activity_log_tail_following = True
        app._run_sequence = 999
        app._batch_error_entries = {}
        app._error_line_raw = {}
        app._prep_counts = {}

        def linha_como(numero: int) -> str:
            return log.get(f"{numero}.0", f"{numero}.0 lineend")

        def achar(trecho: str):
            for numero, conteudo in enumerate(log.get("1.0", "end").splitlines(), start=1):
                if trecho in conteudo:
                    return numero, conteudo
            return 0, ""

        app._update_activity_line("convert", "Convertendo arquivos: 3/10 (30%)")
        app._register_batch_error("sem áudio (código 4294967274)", "a.mp4")
        app._register_batch_error("com erro no VAD", "b.wav")
        app._register_preparation("pronto", 50)
        root.update()
        numero_sem_audio, texto_sem_audio = achar("arquivo(s) sem áudio")
        numero_vad, _ = achar("arquivo(s) com erro no VAD")
        numero_prontos, _ = achar("arquivos já estavam prontos")
        if not (numero_sem_audio and numero_vad and numero_prontos):
            raise RuntimeError("as linhas do lote nao apareceram no log")
        if numero_sem_audio >= numero_vad:
            raise RuntimeError("a ordem de criacao das linhas de erro nao foi respeitada")
        if "activity_step_error" not in log.tag_names(f"{numero_sem_audio}.0"):
            raise RuntimeError("a linha de erro agregada perdeu a cor vermelha")
        if "activity_step_error" in log.tag_names(f"{numero_prontos}.0"):
            raise RuntimeError("a linha de arquivos prontos ficou vermelha")
        horario = texto_sem_audio.split("  ", 1)[0]

        # Atualizacoes em ordem DIFERENTE da criacao: com o comportamento antigo
        # (cada atualizacao joga a linha para o fim) a ordem das linhas vivas se
        # inverte e o check quebra; com o Text.replace por tag a ordem nao muda.
        app._register_preparation("pronto", 50)
        app._register_batch_error("com erro no VAD", "e.wav")
        app._register_batch_error("sem áudio (código 4294967274)", "c.mp4")
        app._register_batch_error("sem áudio (código 4294967274)", "d.mp4")
        app._update_activity_line("convert", "Convertendo arquivos: 4/10 (40%)")
        root.update()
        numero_sem_audio, texto_sem_audio = achar("arquivo(s) sem áudio")
        numero_vad, _ = achar("arquivo(s) com erro no VAD")
        numero_prontos, texto_prontos = achar("arquivos já estavam prontos")
        horario_depois = log.get(
            f"{numero_sem_audio}.0", f"{numero_sem_audio}.0 lineend"
        ).split("  ", 1)[0]
        if horario_depois != horario:
            raise RuntimeError(f"o horario da linha mudou: {horario} -> {horario_depois}")
        if "3 arquivo(s) sem áudio" not in texto_sem_audio:
            raise RuntimeError(f"a contagem do tipo nao subiu: {texto_sem_audio}")
        if "2 arquivo(s) com erro no VAD" not in linha_como(numero_vad):
            raise RuntimeError("a contagem do VAD nao subiu")
        if "2/50 arquivos já estavam prontos" not in texto_prontos:
            raise RuntimeError(f"a contagem de prontos nao subiu: {texto_prontos}")
        if numero_sem_audio >= numero_vad or numero_vad >= numero_prontos:
            raise RuntimeError(
                f"as atualizacoes embaralharam as linhas de erro "
                f"(sem audio {numero_sem_audio}, VAD {numero_vad}, prontos {numero_prontos})"
            )
        conteudo_final = log.get("1.0", "end").splitlines()
        if any("activity_step_error" in linha or "phase:" in linha for linha in conteudo_final):
            raise RuntimeError(f"nome de tag vazou como texto no log: {conteudo_final}")
        # Só as linhas DO LOTE entram na contagem: o app continua escrevendo
        # sozinho durante os `root.update()` deste check (ex.: "Verificando
        # atualizações", que nasce de um `after` do proprio app) — exigir o log
        # inteiro com 4 linhas era uma corrida que falhava de vez em quando.
        do_lote = [
            linha
            for linha in conteudo_final
            if linha.strip()
            and (
                "arquivo(s)" in linha
                or "arquivos já estavam prontos" in linha
                or "Convertendo arquivos" in linha
            )
        ]
        if len(do_lote) != 4:
            raise RuntimeError(f"o log ganhou/perdeu linhas do lote: {conteudo_final}")
        if not any("Convertendo arquivos: 4/10" in linha for linha in conteudo_final):
            raise RuntimeError("a linha de progresso nao foi atualizada")

        # Clique na linha agregada copia o cabecalho + os arquivos do tipo.
        app.root.clipboard_clear()
        app.root.clipboard_append("vazio")
        app._copy_error_line_text(f"phase:r999err1")
        copiado = app.root.clipboard_get()
        if "a.mp4" not in copiado or not copiado.startswith("3 arquivo(s) sem áudio"):
            raise RuntimeError(f"o clique nao copiou a lista do tipo: {copiado!r}")

        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        app._run_sequence = 0
        app._batch_error_entries = {}
        app._error_line_raw = {}
        app._prep_counts = {}
        app._activity_log_tail_following = True
    finally:
        if not mapeado:
            root.withdraw()
        root.update_idletasks()


def _check_live_line_chronology(app, root) -> None:
    """Vacina do pedido de 16/09: linha viva NAO herda o horario da execucao anterior.

    O caso relatado: numa segunda execucao a linha "Transcrevendo arquivos"
    nascia com o horario da PRIMEIRA (a tag `phase:transcribe` era reusada) e
    ainda apagava a linha anterior do lugar — o log ficava fora de ordem
    cronologica. Aqui a fila da UI e drenada com o Tk de verdade entre as duas
    execucoes, com o relogio congelado para o horario de cada linha ser
    verificavel.
    """
    log = app.activity_log
    mapeado = bool(root.winfo_ismapped())
    horarios = ["10:00:01", "10:00:02"]
    try:
        root.deiconify()
        root.update()
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        app._activity_log_tail_following = True

        def relogio(*_args, **_kwargs):
            return horarios.pop(0) if horarios else "10:00:03"

        with patch("time.strftime", side_effect=relogio):
            app._run_sequence = 901
            app._queue("activity_line", "convert", "Convertendo arquivos: 1/1 (2.4s)")
            app._poll_ui_queue()
            app._run_sequence = 902
            app._queue(
                "activity_line", "transcribe", "Transcrevendo arquivos: 1/1 (1min 32s)"
            )
            app._poll_ui_queue()
        root.update()

        linhas = [
            linha
            for linha in log.get("1.0", "end").splitlines()
            if "Convertendo arquivos" in linha or "Transcrevendo arquivos" in linha
        ]
        if linhas != [
            "10:00:01  Convertendo arquivos: 1/1 (2.4s)",
            "10:00:02  Transcrevendo arquivos: 1/1 (1min 32s)",
        ]:
            raise RuntimeError(
                "linhas vivas fora de ordem ou com horario da execucao anterior: "
                f"{linhas}"
            )
        conteudo = log.get("1.0", "end").splitlines()
        if any("phase:" in linha for linha in conteudo):
            raise RuntimeError(f"nome de tag vazou como texto no log: {conteudo}")

        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        app._run_sequence = 0
        app._activity_log_tail_following = True
    finally:
        if not mapeado:
            root.withdraw()
        root.update_idletasks()


def _check_batch_summary_block(app, root) -> None:
    """Vacina do pedido de 16/09: o bloco final do lote sai entre separadores.

        Iniciando envio:                    (no comeco do envio)
        ==========
        Total de arquivos: 1
        Total audio: 1s
        Tamanho total: <bytes>
        Eficiencia geral: 0.5x (2.0s)       (clique -> HTML)
        Eficiencia do servidor: 25.0x (12.0s)
        Eficiencia da GPU: 30.0x (10.0s)
        ==========

    Verifica a ORDEM, as cores (estatisticas verdes, separadores sem cor) e que
    o "Concluido." do app vem depois (aqui o bloco e o ultimo escrito pelo
    check).
    """
    import tempfile
    import wave

    from domain_models import AudioJob

    log = app.activity_log
    mapeado = bool(root.winfo_ismapped())
    try:
        root.deiconify()
        root.update()
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        app._activity_log_tail_following = True

        with tempfile.TemporaryDirectory() as pasta:
            wav = Path(pasta) / "a.wav"
            with wave.open(str(wav), "wb") as destino:
                destino.setnchannels(1)
                destino.setsampwidth(2)
                destino.setframerate(16000)
                destino.writeframes(b"\0" * 32000)  # 1 segundo
            job = AudioJob(
                original_path=wav,
                original_name="a.wav",
                stem="a",
                mode="ready",
                upload_path=wav,
            )
            app._run_sequence = 903
            app._begin_batch_send([job])
            app._report_batch_summary([job], elapsed=2.0, server=(300.0, 10.0, 12.0))
        app._poll_ui_queue()
        root.update()

        linhas = [linha for linha in log.get("1.0", "end").splitlines() if linha.strip()]
        inicio = next(
            (n for n, linha in enumerate(linhas, start=1) if linha.endswith("Iniciando envio:")),
            0,
        )
        if not inicio:
            raise RuntimeError(f"o marcador do inicio do envio nao saiu: {linhas}")
        esperado_prefixos = [
            "==========",
            "Total de arquivos: 1",
            "Total áudio: 1s",
            "Tamanho total: ",
            "Eficiência geral: 0.5x (2.0s)",
            "Eficiência do servidor: 25.0x (12.0s)",
            "Eficiência da GPU: 30.0x (10.0s)",
            "==========",
        ]
        bloco = linhas[inicio : inicio + len(esperado_prefixos)]
        if len(bloco) != len(esperado_prefixos) or any(
            not linha[10:].startswith(prefixo)
            for linha, prefixo in zip(bloco, esperado_prefixos)
        ):
            raise RuntimeError(f"bloco final fora do formato pedido: {bloco}")

        for numero, _prefixo in enumerate(esperado_prefixos, start=inicio + 1):
            tags = log.tag_names(f"{numero}.0")
            if numero in (inicio + 1, inicio + len(esperado_prefixos)):
                if "vad_total" in tags:
                    raise RuntimeError("o separador nao pode sair verde")
            elif "vad_total" not in tags:
                raise RuntimeError(f"linha {numero} do bloco nao ficou verde")

        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        app._run_sequence = 0
        app._activity_log_tail_following = True
    finally:
        if not mapeado:
            root.withdraw()
        root.update_idletasks()


def _check_queue_count_line_color(app, root) -> None:
    """Vacina do pedido de 13/09: "N arquivo(s) na fila." sai VERDE no log.

    Escreve pela MESMA porta do app (`status_var` -> trace ->
    `_append_activity_log`) e confere a tag da ultima linha no Tk de verdade.
    """
    log = app.activity_log
    mapeado = bool(root.winfo_ismapped())
    anterior = app.status_var.get()
    try:
        root.deiconify()
        root.update()
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        app._activity_status_suppressed = 0
        app._activity_log_tail_following = True
        app.status_var.set("1405 arquivo(s) na fila.")
        root.update()
        # A linha e localizada pelo CONTEUDO: os temporizadores do app
        # (poll da fila, relogio do assistente) podem escrever depois dela.
        linhas = log.get("1.0", "end").splitlines()
        encontradas = [
            numero
            for numero, conteudo in enumerate(linhas, start=1)
            if "1405 arquivo(s) na fila" in conteudo
        ]
        if not encontradas:
            raise RuntimeError(f"a mensagem da fila nao apareceu no log: {linhas}")
        for numero in encontradas:
            tags = log.tag_names(f"{numero}.0")
            if "activity_step_done" not in tags:
                raise RuntimeError(
                    f"a linha da fila ({numero}) nao saiu verde (tags: {tags})"
                )
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
    finally:
        # Restaura a barra de status SEM passar pelo log de atividade.
        app._set_activity_status(anterior, log=False)
        if not mapeado:
            root.withdraw()
        root.update_idletasks()


def _check_settings_window_fills_its_content(app, root) -> None:
    """Vacina do bug de 13/09 (i5-8400): a janela nao pode ficar presa pequena.

    A janela de Configuracoes e mapeada no MEIO da construcao (o
    `update_idletasks` da medicao do botao de olho acontece com o conteudo ainda
    parcial, ~1 linha por aba) e com `resizable(False, False)` ja aplicado. Num
    PC o gerenciador de janelas nao aceitou o crescimento posterior: cada aba
    ficou mostrando so a primeira linha, SEM nenhum erro no log.

    Aqui o estado ruim e SIMULADO (janela pequena) e o app precisa devolve-la ao
    tamanho do conteudo — na abertura e a cada troca de aba.
    """
    antes = set(root.winfo_children())
    app.open_settings()
    root.update_idletasks()
    janelas = [
        filho for filho in root.winfo_children()
        if isinstance(filho, tk.Toplevel) and filho not in antes
    ]
    if len(janelas) != 1:
        raise RuntimeError(f"esperava uma janela de Configuracoes, achei {len(janelas)}")
    janela = janelas[0]
    try:
        botoes, conteudo = _settings_tab_pages(janela)
        if len(botoes) != 4:
            raise RuntimeError(f"esperava 4 abas, achei {list(botoes)}")

        def pagina_ativa():
            return next(
                (w for w in conteudo.winfo_children() if w.winfo_manager() == "pack"),
                None,
            )

        pagina = pagina_ativa()
        if pagina is None:
            raise RuntimeError("nenhuma pagina ativa logo depois de abrir")
        if janela.winfo_height() < pagina.winfo_reqheight():
            raise RuntimeError(
                f"a janela abriu com {janela.winfo_width()}x{janela.winfo_height()}px, "
                f"menor que a aba ativa ({pagina.winfo_reqwidth()}x{pagina.winfo_reqheight()}px)"
            )

        # O caso do PC: janela presa no tamanho do primeiro mapeamento.
        janela.geometry("416x110")
        janela.update_idletasks()
        for nome, botao in botoes.items():
            botao.event_generate("<Button-1>", x=1, y=1)
            janela.update_idletasks()
            pagina = pagina_ativa()
            if pagina is None:
                raise RuntimeError(f"aba {nome} sem pagina ativa")
            if (
                janela.winfo_height() < pagina.winfo_reqheight()
                or janela.winfo_width() < pagina.winfo_reqwidth()
            ):
                raise RuntimeError(
                    f"a janela ficou presa em {janela.winfo_width()}x{janela.winfo_height()}px "
                    f"com a aba {nome} ({pagina.winfo_reqwidth()}x{pagina.winfo_reqheight()}px)"
                )
    finally:
        janela.destroy()
        root.update_idletasks()


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
            # Vacina do pedido de 13/09: a checkbox "Um modelo por vez" fica
            # entre o botao "Modelos" e o seletor de Idioma, desmarcada.
            _check_one_model_checkbox(app)
            _check_live_local_server_controls(app, root)
            # Vacina do pedido de 12/09: os botoes da linha de controles da aba
            # Ocorrencia usam os PNGs de assets/ (microfones vermelho/branco e
            # pausar) no lugar dos desenhos vetoriais.
            _check_live_mic_icons(app, root)
            # Vacina do pedido de 13/09: a atualizacao do log de atividade nao
            # pode mover a barra de rolagem (linha viva "Convertendo/
            # Transcrevendo arquivos: N/M") enquanto o usuario le mais acima.
            _check_activity_log_scroll(app, root)
            # Vacina do pedido de 13/09: erros do lote em UMA linha por tipo (com
            # contagem) e a linha de arquivos ja prontos, sem embaralhar a ordem.
            _check_batch_log_lines(app, root)
            # Vacina do pedido de 16/09: linha viva de uma execucao NAO herda o
            # horario da anterior (o "Transcrevendo arquivos" aparecia fora de
            # ordem no log) e o bloco final do lote sai entre separadores,
            # verde, antes do "Concluido.".
            _check_live_line_chronology(app, root)
            _check_batch_summary_block(app, root)
            # Vacina do pedido de 13/09: "N arquivo(s) na fila." sai verde no log
            # assim que aparece (mesmo caminho: status_var -> trace -> log).
            _check_queue_count_line_color(app, root)
            # Vacina do pedido de 11/09: o palco da previa das ferramentas
            # FFmpeg preenche o espaco disponivel, com zoom (roda) e arrasto.
            _check_ffmpeg_preview_stage(app, root)
            _check_ffmpeg_output_rows(app, root)
            _check_ffmpeg_cut_modes(app, root)
            _check_ffmpeg_encoder_selector(app, root)
            _check_ffmpeg_timeline_markers(app, root)
            _check_ffmpeg_stage_hints(app, root)
            _check_ffmpeg_area_selection(app, root)

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
            _check_api_key_visibility_toggle(app, settings_window)
            _check_api_key_field_layout(app, settings_window)
            _check_parallel_sliders(app, settings_window)
            settings_window.destroy()
            root.update_idletasks()

            # Vacina do bug de 11/09: as Configurações precisam nascer
            # inteiras também em máquinas com poucos núcleos (aqui a máquina
            # tem núcleos de sobra, então o cenário é simulado).
            _check_settings_window_on_low_core_machines(app, root)
            # Vacina do pedido de 13/09 (PC i5-8400): a janela de Configuracoes
            # nao pode ficar presa no tamanho do PRIMEIRO mapeamento (ela e
            # mapeada no meio da construcao, com o conteudo parcial).
            _check_settings_window_fills_its_content(app, root)

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
