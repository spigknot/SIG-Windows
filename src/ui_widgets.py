"""Widgets Tk reutilizaveis (tooltip, botao-icone e slider de nos).

Sem regra de negocio; usado por sig_app.py e ffmpeg_tools_panel.py.

O `NodeSlider` e uma porta do slider do projeto TurboCore
(`turbocore/nodeslider.py`): traco fino + um no por opcao + bolinha azul, com
atracao magnetica. Mantido igual para as duas aplicacoes terem o mesmo visual.
"""

from tkinter import Canvas, Toplevel, ttk

import math

from PIL import Image, ImageDraw

MAGIC_WAND_SIZE = 20
MAGIC_WAND_SCALE = 8
MAGIC_WAND_SHAFT = (16, 17, 8, 9)
MAGIC_WAND_SHAFT_WIDTH = 2
MAGIC_WAND_STAR_CENTER = (6, 5)
MAGIC_WAND_STAR_RADIUS = 5.5
MAGIC_WAND_COLOR = "#16833a"
MAGIC_WAND_STAR_COLOR = "#f2c200"
# Ícone do USUÁRIO (assets/varinha_magica.png, cópia de
# D:\Projetos\Icones\varinha_03.png). Preferido ao desenho vetorial acima
# (pedido de 28/09): é o traço do próprio usuário, com a estrela de 5 pontas e
# os 8 raios de brilho. `ui_widgets` nao importa `resource_path` para não
# depender do empacotamento; quem monta o caminho passa o `Path`/`str` pronto.
MAGIC_WAND_ASSET = "assets/varinha_magica.png"
# O botão tem 24 px; o PNG é quadrado e o desenho já encosta nas bordas, então
# cabe inteiro apenas se for REDUZIDO. Nunca ampliar: um PNG de 64 px esticado
# para cima seria pior que o desenho vetorial.
MAGIC_WAND_ASSET_SIZE = 20
# Pedido do usuário (28/09): a estrela e os raios estavam dificeis de ver, e
# ele APLICOU a troca do AMARELO pela MESMA cor da haste — gostou da estrela
# verde. Feito em tempo de CARREGAMENTO, sem alterar o arquivo do usuário: o
# asset segue sendo a cópia fiel do desenho original, e trocar a cor de destino
# abaixo já produz outra variante.
#
# O que o MEDIR mostrou: pintar a estrela com o verde da haste (23,95,36) tira
# a separação de cor entre haste e estrela, e a silhueta do desenho é feita
# justamente por esse contraste — a estrela fica mais difícil de ler. Como o
# usuário gostou do verde, o alvo padrão passou a ser um verde CLARO, que dá
# unidade de cor (tudo verde) e mantém a separação por LUMINOSIDADE.
#
# Faixa do amarelo no PNG (medida): hue 49-50, saturacao 1.00 -> o criterio e
# "hue entre 40 e 70 e saturacao alta", que pega o amarelo e nao toca no verde
# da haste (hue 131) nem no transparente.
MAGIC_WAND_RECOLOR = True
MAGIC_WAND_YELLOW_HUE_MIN = 40.0
MAGIC_WAND_YELLOW_HUE_MAX = 70.0
MAGIC_WAND_YELLOW_SAT_MIN = 0.35
# Alvo padrao: verde claro, bem acima da luminancia da haste (23,95,36) para a
# estrela e os raios se destacarem sem sair da paleta verde.
MAGIC_WAND_TARGET_COLOR = (120, 210, 90)
# Verde da haste, mantido para as variantes (o desenho em si ja e esse tom).
MAGIC_WAND_SHAFT_GREEN = (23, 95, 36)
# Amarelo original do PNG, para voltar ao desenho como o usuario fez.
MAGIC_WAND_ORIGINAL_YELLOW = (255, 212, 0)


def _recolore_amarelo(image: Image.Image, cor: tuple[int, int, int]) -> Image.Image:
    """Troca o amarelo do ícone por `cor`, preservando o alfa.

    Só os pixels na faixa de hue do amarelo sao trocados (o verde da haste, hue
    131, fica intacto). O alfa e preservado pixel a pixel, entao a
    transparencia do desenho -- e o que faz ele caber inteiro no botao -- nao
    muda. A conversao usa HSV para nao depender do RGB exato: o PNG tem 1009
    cores unicas (variacoes de alpha e antialiasing) e casar por igualdade
    deixaria quase tudo amarelo para tras.
    """
    import colorsys

    r_alvo, g_alvo, b_alvo = cor
    alterado = image.copy()
    destino = alterado.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = destino[x, y]
            if a == 0:
                continue
            hue, sat, _val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            graus = hue * 360
            if (
                MAGIC_WAND_YELLOW_HUE_MIN <= graus <= MAGIC_WAND_YELLOW_HUE_MAX
                and sat >= MAGIC_WAND_YELLOW_SAT_MIN
            ):
                destino[x, y] = (r_alvo, g_alvo, b_alvo, a)
    return alterado


def magic_wand_asset_image(
    caminho,
    size: int = MAGIC_WAND_ASSET_SIZE,
    recolorir: bool | None = None,
    cor: tuple[int, int, int] | None = None,
) -> Image.Image | None:
    """Ícone da varinha do usuário, reduzido para caber inteiro no botão.

    O desenho é REDUZIDO (nunca ampliado) para `size`, preservando o alfa e
    mantendo a proporção: o PNG é quadrado e o conteúdo encosta nas bordas, logo
    ele aparece inteiro. Com `recolorir` (padrão = a constante do módulo) o
    amarelo é repintado com `cor` (padrão = `MAGIC_WAND_TARGET_COLOR`). Com
    `recolorir=False` volta ao amarelo original do desenho. Devolve `None` se o
    arquivo não existir, para o chamador cair no desenho vetorial
    (`magic_wand_image`) sem quebrar o app.
    """
    try:
        with Image.open(caminho) as origem:
            image = origem.convert("RGBA")
    except (OSError, ValueError):
        return None
    if recolorir is None:
        recolorir = MAGIC_WAND_RECOLOR
    if recolorir:
        image = _recolore_amarelo(
            image, cor if cor is not None else MAGIC_WAND_TARGET_COLOR
        )
    if image.size[0] > size or image.size[1] > size:
        image = image.resize((size, size), Image.LANCZOS)
    return image


def _desenha_mascara(escala, desenhar) -> Image.Image:
    """Máscara em escala `escala`x, reduzida com LANCZOS (alpha suavizado).

    Por que máscara e não desenho direto no RGBA: o PIL NÃO faz
    premultiplicação de alpha no `resize`, então reduzir um desenho
    transparente faz a BORDA ESCURECER (o RGB sangra para o preto do fundo) em
    vez de ficar suave — medido: zero pixel de antialiasing no resultado, ou
    seja, a suavização não acontecia. Reduzindo a MASCARA (cinza, sem cor) o
    LANCZOS interpola a cobertura de verdade, e a cor é aplicada depois sobre
    pixels já com alpha correto.
    """
    ALTO = MAGIC_WAND_SIZE * escala
    mascara = Image.new("L", (ALTO, ALTO), 0)
    desenhar(ImageDraw.Draw(mascara))
    if escala == 1:
        return mascara
    return mascara.resize((MAGIC_WAND_SIZE, MAGIC_WAND_SIZE), Image.LANCZOS)


def magic_wand_image(
    color: str = MAGIC_WAND_COLOR,
    star_color: str = MAGIC_WAND_STAR_COLOR,
    escala: int = MAGIC_WAND_SCALE,
) -> Image.Image:
    """Icone da varinha magica (ajuste da oitiva), em RGBA 20x20.

    Haste VERDE a 45 graus (mesmo deslocamento em X e em Y), de baixo-DIREITA
    para cima-ESQUERDA, com estrelinha AMARELA de 5 pontas preenchida na ponta.

    SEM SERRILHADO: as duas peças (haste e estrela) são desenhadas em
    `escala`x como MASCARA e reduzidas com LANCZOS, e só então recebem cor.
    Desenhar a diagonal direto em 20x20 produz degraus de 1px visiveis. O fator
    8 foi escolhido comparando 4x/8x/16x em tela: 16x embaca (fica borrado) e
    4x mantem degraus. As pontas da haste recebem um circulo do mesmo raio da
    meia-espessura, para ficarem arredondadas em vez de quadradas (o
    `joint="curve"` so arredonda os vaos internos, nao as pontas).
    """
    x_baixo, y_baixo, x_cima, y_cima = MAGIC_WAND_SHAFT
    largura = MAGIC_WAND_SHAFT_WIDTH
    centro_x, centro_y = MAGIC_WAND_STAR_CENTER
    alcance = MAGIC_WAND_STAR_RADIUS

    def desenha_haste(draw):
        draw.line(
            (x_baixo * escala, y_baixo * escala, x_cima * escala, y_cima * escala),
            fill=255,
            width=largura * escala,
            joint="curve",
        )
        # pontas arredondadas: a diagonal crua terminava em bloco serrilhado
        raio = largura * escala / 2
        for px, py in ((x_baixo, y_baixo), (x_cima, y_cima)):
            draw.ellipse(
                (px * escala - raio, py * escala - raio, px * escala + raio, py * escala + raio),
                fill=255,
            )

    def desenha_estrela(draw):
        pontos = []
        for indice in range(10):
            angulo = math.radians(-90 + indice * 36)
            distancia = (alcance if indice % 2 == 0 else alcance * 0.42) * escala
            pontos.append(
                (
                    centro_x * escala + math.cos(angulo) * distancia,
                    centro_y * escala + math.sin(angulo) * distancia,
                )
            )
        draw.polygon(pontos, fill=255)

    mascara_haste = _desenha_mascara(escala, desenha_haste)
    mascara_estrela = _desenha_mascara(escala, desenha_estrela)

    cor_haste = Image.new("RGBA", (MAGIC_WAND_SIZE, MAGIC_WAND_SIZE), color)
    cor_estrela = Image.new("RGBA", (MAGIC_WAND_SIZE, MAGIC_WAND_SIZE), star_color)
    return _aplica_alpha(cor_haste, cor_estrela, mascara_haste, mascara_estrela)


def _aplica_alpha(
    cor_haste: Image.Image,
    cor_estrela: Image.Image,
    mascara_haste: Image.Image,
    mascara_estrela: Image.Image,
) -> Image.Image:
    """Une as duas máscaras num RGBA: a estrela fica por cima da haste."""
    tamanho = MAGIC_WAND_SIZE
    pixels_haste = cor_haste.load()
    pixels_estrela = cor_estrela.load()
    alpha_haste = mascara_haste.load()
    alpha_estrela = mascara_estrela.load()
    saida = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    destino = saida.load()
    for y in range(tamanho):
        for x in range(tamanho):
            a_haste = alpha_haste[x, y]
            a_estrela = alpha_estrela[x, y]
            if a_estrela >= a_haste:
                if a_estrela:
                    destino[x, y] = (*pixels_estrela[x, y][:3], a_estrela)
            elif a_haste:
                destino[x, y] = (*pixels_haste[x, y][:3], a_haste)
    return saida


# ---------------- Slider de nós (visual do TurboCore) ----------------

SLIDER_HEIGHT = 26      # altura do canvas (traco + bolinhas)
LINE_WIDTH = 2          # espessura do traco horizontal
NODE_RADIUS = 4         # raio do no cinza
THUMB_RADIUS = 7        # raio da bolinha azul (maior: fica sobre o no)
EDGE_PAD = THUMB_RADIUS + 2   # folga para a bolinha nao ser cortada nas pontas

LINE_COLOR = "#c8cdd2"
NODE_COLOR = "#9aa4ad"
NODE_ACTIVE_COLOR = "#5b6672"   # no ate a selecao (progresso)
THUMB_COLOR = "#1f6feb"
THUMB_OUTLINE = "#1553b8"


def node_positions(count: int, width: int, pad: int = EDGE_PAD) -> list[float]:
    """X dos nós, igualmente espaçados entre `pad` e `width - pad`."""
    if count <= 0:
        return []
    usable = max(width - 2 * pad, 1)
    if count == 1:
        return [pad + usable / 2.0]
    step = usable / (count - 1)
    return [pad + step * i for i in range(count)]


def nearest_index(x: float, positions: list[float]) -> int:
    """Índice do nó mais próximo de `x` (a atração magnética)."""
    if not positions:
        return 0
    best, best_d = 0, abs(x - positions[0])
    for i, px in enumerate(positions[1:], start=1):
        d = abs(x - px)
        if d < best_d:
            best, best_d = i, d
    return best


def step_values(step: int, maximum: int, minimum: int | None = None) -> list[int]:
    """Valores possíveis do slider: múltiplos do passo até `maximum`.

    As configurações usam slider de nós (cada nó é um valor possível), então a
    granularidade é o passo: 4 em 4 nas conversões e 2 em 2 nas requisições.
    O primeiro valor é o próprio passo (nunca 0: paralelismo 0 quebraria o
    executor) — `minimum` permite começar mais alto, se algum dia precisar.
    """
    passo = max(1, int(step))
    limite = int(maximum)
    inicio = max(passo, int(minimum if minimum is not None else passo))
    valores = list(range(inicio, limite + 1, passo)) if limite >= inicio else []
    return valores or [inicio]


def nearest_value(value, values: list[int]) -> int:
    """Valor da lista mais próximo de `value` (para encaixar o valor salvo)."""
    if not values:
        return max(1, int(value or 1))
    try:
        alvo = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return values[0]
    return min(values, key=lambda candidato: (abs(candidato - alvo), candidato))


def parallel_values(cpu_count: int) -> list[int]:
    """Opções do slider de paralelismo para uma máquina de `cpu_count` núcleos.

    Regra do usuário (11/09, estendida em 14/09 com 8n e 16n): 1, 2, 3, ..., n,
    3n/2, 2n, 5n/2, 3n, 7n/2, 4n, 8n, 16n — ou seja, n + 8 opções. Conta que não
    dá exato aproxima para o inteiro mais próximo, com o empate subindo
    (4.5 -> 5, 7.5 -> 8, 12.5 -> 13); a lista é sempre crescente e sem
    repetições (com n = 1 as oito frações caem em 1/2/3/4/8/16 e sobram 6
    opções distintas — não existem 9 inteiros distintos até 16n).

    Vantagem sobre a lista antiga (só múltiplos do passo): o valor recomendado
    n/2 passa a existir como nó — antes, num 4 núcleos, o recomendado 2 era
    encaixado à força em 4.
    """
    nucleos = max(1, int(cpu_count))
    valores = list(range(1, nucleos + 1))
    for fator in (3, 4, 5, 6, 7, 8, 16, 32):   # 3n/2, 2n, 5n/2, 3n, 7n/2, 4n, 8n, 16n
        valores.append(int(math.floor(nucleos * fator / 2 + 0.5)))
    return sorted(set(valores))


def describe_parallel_values(values: list[int], cpu_count: int) -> str:
    """Frase de ajuda com TODAS as opções da máquina (sem índice por posição)."""
    if not values:
        return "Sem valores disponíveis nesta máquina."
    opcoes = ", ".join(str(valor) for valor in values)
    return f"Opções desta máquina (n = {cpu_count} núcleos): {opcoes}."


def workable_step(preferred_step: int, maximum: int, minimum_nodes: int = 2) -> int:
    """Passo utilizável pelo slider: o preferido, quando ele dá nós suficientes.

    O usuário definiu o passo preferido (4 em 4 nas Conversões e 2 em 2 nas
    Requisições). Em máquinas com poucos núcleos esse passo deixa o slider com
    um nó só — 2 núcleos => 2n = 4 => `[4]` com passo 4 — e não há o que
    escolher. Nesse caso o passo cai pela metade (4 -> 2 -> 1) até render
    `minimum_nodes` valores. Máquina com núcleos de sobra continua exatamente
    no passo preferido.
    """
    passo = max(1, int(preferred_step))
    alvo = max(1, int(minimum_nodes))
    while passo > 1:
        if len(step_values(passo, maximum)) >= alvo:
            return passo
        passo = max(1, passo // 2)
    return 1


def describe_step_values(values: list[int], step: int) -> str:
    """Frase de ajuda do slider de nós — segura para QUALQUER tamanho de lista.

    A frase antiga era montada com `values[0]`, `values[1]` e `values[2]`
    fixos. Em máquinas com poucos núcleos a lista tem 1 ou 2 valores: o
    `values[2]` estourava `IndexError` NO MEIO da construção da janela de
    Configurações, e tudo o que era construído depois ficava vazio (a janela
    abria só com a barra de abas). Nunca indexar por posição fixa aqui.
    """
    if not values:
        return "Sem valores disponíveis nesta máquina."
    if len(values) == 1:
        return f"Esta máquina tem um único valor disponível: {values[0]}."
    amostra = ", ".join(str(valor) for valor in values[:3])
    if len(values) == 2:
        return f"O slider sobe de {step} em {step}: {amostra}."
    return f"O slider sobe de {step} em {step}: {amostra}... até {values[-1]}."


class NodeSlider(Canvas):
    """Slider discreto com traço, nós e bolinha azul arrastável (snap por nó).

    A API imita o `ttk.Scale` (`get`/`set`/`command`) para o chamador não mudar
    a lógica: `get()` devolve o VALOR do nó atual, `set(valor)` move sem disparar
    `command` (evita recursão) e `command` só roda em interação real.
    """

    def __init__(self, master, values, length: int = 200, command=None, **kwargs):
        self.values = [int(v) for v in values] or [1]
        kwargs.setdefault("height", SLIDER_HEIGHT)
        kwargs.setdefault("width", length)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        super().__init__(master, **kwargs)
        try:
            self.configure(bg=master.cget("background"))
        except Exception:
            pass
        self._command = command
        self._index = 0
        self._positions: list[float] = []
        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<Left>", self._on_key_left)
        self.bind("<Right>", self._on_key_right)
        self.bind("<Home>", lambda _e: self._select(0, fire=True))
        self.bind("<End>", lambda _e: self._select(len(self.values) - 1, fire=True))
        self.after_idle(self._relayout)

    # -- API -----------------------------------------------
    def get(self) -> int:
        return self.values[self._index]

    def set(self, value) -> None:
        """Move a bolinha para o valor mais próximo, SEM disparar command."""
        alvo = nearest_value(value, self.values)
        self._select(self.values.index(alvo), fire=False)

    # -- desenho -------------------------------------------
    def _relayout(self) -> None:
        self._positions = node_positions(len(self.values), self.winfo_width())
        self._redraw()

    def _on_configure(self, _event) -> None:
        self._relayout()

    def _redraw(self) -> None:
        self.delete("all")
        if not self._positions:
            return
        mid = SLIDER_HEIGHT / 2.0
        first, last = self._positions[0], self._positions[-1]
        self.create_line(
            first, mid, last, mid, fill=LINE_COLOR, width=LINE_WIDTH, capstyle="round"
        )
        for i, px in enumerate(self._positions):
            if i == self._index:
                continue                      # a bolinha azul cobre este nó
            color = NODE_ACTIVE_COLOR if i <= self._index else NODE_COLOR
            self.create_oval(
                px - NODE_RADIUS, mid - NODE_RADIUS, px + NODE_RADIUS, mid + NODE_RADIUS,
                fill=color, outline="",
            )
        tx = self._positions[self._index]
        self.create_oval(
            tx - THUMB_RADIUS, mid - THUMB_RADIUS, tx + THUMB_RADIUS, mid + THUMB_RADIUS,
            fill=THUMB_COLOR, outline=THUMB_OUTLINE, width=1,
        )

    # -- interacao -----------------------------------------
    def _select(self, index: int, fire: bool) -> None:
        index = max(0, min(index, len(self.values) - 1))
        changed = index != self._index
        self._index = index
        self._redraw()
        if fire and self._command is not None:
            self._command(str(self.values[index]))

    def _index_at(self, x: int) -> int:
        return nearest_index(float(x), self._positions)

    def _on_press(self, event) -> None:
        self.focus_set()
        self._select(self._index_at(event.x), fire=True)

    def _on_drag(self, event) -> None:
        self._select(self._index_at(event.x), fire=True)

    def _on_key_left(self, _event) -> str:
        self._select(self._index - 1, fire=True)
        return "break"

    def _on_key_right(self, _event) -> str:
        self._select(self._index + 1, fire=True)
        return "break"


def create_tooltip(widget, message: str) -> None:
    tooltip = None

    def show(_event=None):
        nonlocal tooltip
        if tooltip or not widget.winfo_exists():
            return
        tooltip = Toplevel(widget)
        tooltip.overrideredirect(True)
        tooltip.attributes("-topmost", True)
        label = ttk.Label(tooltip, text=message, padding=(7, 4), relief="solid")
        label.pack()
        tooltip.geometry(f"+{widget.winfo_rootx() + widget.winfo_width() + 4}+{widget.winfo_rooty() + 2}")

    def hide(_event=None):
        nonlocal tooltip
        if tooltip:
            tooltip.destroy()
            tooltip = None

    widget.bind("<Enter>", show, add="+")
    widget.bind("<Leave>", hide, add="+")
    widget.bind("<ButtonPress>", hide, add="+")


class PreviewIconButton(Canvas):
    """Controle compacto de prévia, desenhado para lembrar o player Android."""

    def __init__(self, parent, kind: str, command, width: int, height: int, **kwargs):
        self.kind = kind
        self.command = command
        self.playing = False
        self.hovered = False
        background = kwargs.pop("background", "#f4f7f6")
        super().__init__(
            parent,
            width=width,
            height=height,
            highlightthickness=0,
            borderwidth=0,
            background=background,
            cursor="hand2",
            **kwargs,
        )
        self._background = background
        self.bind("<Button-1>", lambda _event: self.command())
        self.bind("<Enter>", lambda _event: self._set_hover(True))
        self.bind("<Leave>", lambda _event: self._set_hover(False))
        self._draw()

    def configure(self, cnf=None, **kwargs):
        text = kwargs.pop("text", None)
        if isinstance(cnf, dict):
            text = cnf.pop("text", text)
        if text is not None and self.kind == "play":
            self.playing = text in {"||", "pause", "paused"}
            self._draw()
        return super().configure(cnf, **kwargs)

    config = configure

    def _set_hover(self, hovered: bool) -> None:
        self.hovered = hovered
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_reqwidth())
        height = max(1, self.winfo_reqheight())
        color = "#16833a" if self.hovered else "#536565"
        if self.kind == "play":
            center_x, center_y = width / 2, height / 2
            radius = min(width, height) * 0.34
            self.create_oval(
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
                outline=color,
                width=3,
            )
            if self.playing:
                bar_height = radius * 0.82
                self.create_line(center_x - 6, center_y - bar_height / 2, center_x - 6, center_y + bar_height / 2, fill=color, width=4, capstyle="round")
                self.create_line(center_x + 6, center_y - bar_height / 2, center_x + 6, center_y + bar_height / 2, fill=color, width=4, capstyle="round")
            else:
                self.create_polygon(
                    center_x - 6,
                    center_y - 12,
                    center_x + 13,
                    center_y,
                    center_x - 6,
                    center_y + 12,
                    fill=color,
                    outline="",
                )
            return
        direction = -1 if self.kind == "slower" else 1
        center_x, center_y = width / 2, height / 2
        chevron_width = 15
        gap = 8
        for offset in (-gap, gap):
            if direction < 0:
                points = (
                    center_x + offset + chevron_width / 2,
                    center_y - 13,
                    center_x + offset - chevron_width / 2,
                    center_y,
                    center_x + offset + chevron_width / 2,
                    center_y + 13,
                )
            else:
                points = (
                    center_x + offset - chevron_width / 2,
                    center_y - 13,
                    center_x + offset + chevron_width / 2,
                    center_y,
                    center_x + offset - chevron_width / 2,
                    center_y + 13,
                )
            self.create_line(*points, fill=color, width=3, capstyle="round", joinstyle="round")
