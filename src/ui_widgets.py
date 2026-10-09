"""Widgets Tk reutilizaveis (tooltip, botao-icone e slider de nos).

Sem regra de negocio; usado por sig_app.py e ffmpeg_tools_panel.py.

O `NodeSlider` e uma porta do slider do projeto TurboCore
(`turbocore/nodeslider.py`): traco fino + um no por opcao + bolinha azul, com
atracao magnetica. Mantido igual para as duas aplicacoes terem o mesmo visual.
"""

from tkinter import Canvas, Toplevel, ttk

import math
from typing import Callable

from PIL import Image, ImageDraw, ImageTk

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
# ele trocou o AMARELO pela MESMA cor da haste — gostou da estrela verde.
# Feito em tempo de CARREGAMENTO, sem alterar o arquivo do usuário: o asset
# segue sendo a cópia fiel do desenho original.
#
# IMPORTANTE (decisão do usuário, 28/09, mantida mesmo com medição contrária):
# foi mostrado um verde CLARO (120,210,90) como alternativa, mas ele AWARDOU a
# versão de verde ESCURO e pediu para colocar esta. O verde da haste
# (23,95,36) é o alvo; a estrela e o brilho ficam nesse mesmo tom. Uma análise
# automática de legibilidade preferia o verde claro (dá separação por
# luminosidade entre haste e estrela), mas a preferência é do usuário e vale
# mais: o que ele pediu foi verde escuro na estrela e no brilho.
#
# Faixa do amarelo no PNG (medida): hue 49-50, saturacao 1.00 -> o criterio e
# "hue entre 40 e 70 e saturacao alta", que pega o amarelo e nao toca no verde
# da haste (hue 131) nem no transparente.
MAGIC_WAND_RECOLOR = True
MAGIC_WAND_YELLOW_HUE_MIN = 40.0
MAGIC_WAND_YELLOW_HUE_MAX = 70.0
MAGIC_WAND_YELLOW_SAT_MIN = 0.35
# Verde da haste, medido no proprio PNG do usuario. E o alvo da estrela e dos
# raios: mesma cor da haste, por escolha do usuario.
MAGIC_WAND_SHAFT_GREEN = (23, 95, 36)
MAGIC_WAND_TARGET_COLOR = MAGIC_WAND_SHAFT_GREEN
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


def create_tooltip(widget, message: str | Callable[[], str]) -> None:
    tooltip = None

    def show(_event=None):
        nonlocal tooltip
        if tooltip or not widget.winfo_exists():
            return
        tooltip = Toplevel(widget)
        tooltip.overrideredirect(True)
        tooltip.attributes("-topmost", True)
        label = ttk.Label(tooltip, text=message() if callable(message) else message, padding=(7, 4), relief="solid")
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


def tool_action_icon_image(kind: str, size: int = 24, *, enabled: bool = True,
                           circular: bool = False, foreground: str | None = None) -> Image.Image:
    """Ícones de ação desenhados em oito vezes o tamanho para bordas suaves."""
    scale = 8
    factor = size * scale / 64
    image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    ink = foreground or ("#315c48" if enabled else "#a0aeaa")
    pale = "#e6f2ec" if enabled else "#eef1ef"
    gold = "#e9b94d" if enabled else "#b9c2bd"
    blue = "#397b9e" if enabled else "#a0aeaa"
    def box(values):
        return tuple(round(value * factor) for value in values)
    def rounded(values, fill=None, outline=ink, radius=4, stroke=2):
        draw.rounded_rectangle(box(values), radius=round(radius * factor),
                               fill=fill, outline=outline, width=max(1, round(stroke * factor)))
    def stroke_path(values, fill=ink, stroke=2.5):
        points = [(round(x * factor), round(y * factor)) for x, y in values]
        draw.line(points, fill=fill, width=max(1, round(stroke * factor)), joint="curve")
        radius = stroke * factor / 2
        for x, y in (points[0], points[-1]):
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=fill)
    if circular:
        dark = kind in ("execute", "cancel")
        draw.ellipse(box((4, 6, 60, 62)), fill="#dce5df")
        draw.ellipse(box((3, 3, 61, 61)), fill="#193d32" if dark else "#eef5f1",
                     outline="#2f5d4a" if dark else "#d5e3da", width=max(1, round(factor)))
    if kind == "execute":
        draw.polygon([box(point) for point in ((37, 10), (19, 35), (30, 35), (26, 54), (46, 27), (34, 27))],
                     fill="#f4cc56", outline="#ffe8a0", width=max(1, round(factor)))
    elif kind == "cancel":
        stroke_path(((23, 23), (41, 41)), fill="#ff817d", stroke=5)
        stroke_path(((41, 23), (23, 41)), fill="#ff817d", stroke=5)
    elif kind == "save":
        rounded((15, 12, 49, 52), fill=blue, outline="#295b78" if enabled else ink, radius=4)
        rounded((21, 13, 42, 28), fill="#edf6fb", outline=None, radius=1)
        rounded((36, 15, 40, 25), fill=blue, outline=None, radius=1)
        rounded((21, 37, 43, 51), fill="#edf6fb", outline=None, radius=2)
        stroke_path(((26, 42), (38, 42)), fill=blue, stroke=1.7)
        stroke_path(((26, 46), (35, 46)), fill=blue, stroke=1.7)
    elif kind == "folder":
        draw.polygon([box(point) for point in ((12, 20), (12, 15), (27, 15), (33, 21), (52, 21), (52, 47), (12, 47))],
                     fill="#d69b32" if enabled else ink)
        rounded((11, 23, 53, 49), fill=gold, outline="#bd8b2e" if enabled else ink, radius=4)
        stroke_path(((18, 30), (46, 30)), fill="#fff0ba", stroke=2)
    elif kind == "copy":
        rounded((23, 10, 53, 42), fill=pale, radius=4)
        rounded((11, 23, 41, 55), fill="#ffffff", radius=4)
        stroke_path(((19, 34), (33, 34)), stroke=2)
        stroke_path(((19, 42), (30, 42)), stroke=2)
    elif kind == "paste":
        rounded((15, 14, 49, 55), fill=pale, radius=4)
        rounded((24, 8, 40, 21), fill="#ffffff", radius=3)
        stroke_path(((23, 31), (41, 31)), stroke=2)
        stroke_path(((23, 39), (41, 39)), stroke=2)
        stroke_path(((23, 47), (35, 47)), stroke=2)
    elif kind == "clear":
        rounded((19, 21, 45, 54), fill=pale, radius=4)
        stroke_path(((14, 19), (50, 19)), stroke=3)
        rounded((25, 10, 39, 19), fill=None, radius=3)
        stroke_path(((28, 29), (28, 45)), stroke=2)
        stroke_path(((36, 29), (36, 45)), stroke=2)
    elif kind == "qrcode":
        for x, y in ((9, 9), (37, 9), (9, 37)):
            rounded((x, y, x+18, y+18), fill=None, radius=2, stroke=3)
            rounded((x+6, y+6, x+12, y+12), fill=ink, outline=None, radius=1)
        for x, y, w, h in ((37, 37, 7, 7), (49, 37, 6, 13), (37, 49, 13, 6), (49, 52, 6, 3)):
            rounded((x, y, x+w, y+h), fill=ink, outline=None, radius=1)
    elif kind == "phone":
        rounded((17, 6, 47, 58), fill=pale, radius=7)
        rounded((24, 7, 40, 13), fill=ink, outline=None, radius=2)
        stroke_path(((27, 50), (37, 50)), stroke=2)
        stroke_path(((25, 24), (39, 24)), stroke=2)
        stroke_path(((25, 31), (35, 31)), stroke=2)
    elif kind == "history":
        draw.arc(box((10, 10, 54, 54)), start=210, end=535, fill=ink, width=max(1, round(3 * factor)))
        stroke_path(((32, 19), (32, 33), (42, 39)), stroke=3)
        stroke_path(((10, 12), (10, 26), (23, 26)), stroke=3)
    else:
        raise ValueError(f"Ícone de ação desconhecido: {kind}")
    return image.resize((size, size), Image.Resampling.LANCZOS)


def preview_control_icon_image(kind: str, width: int, height: int, playing: bool = False,
                               hovered: bool = False, background: str = "#f4f7f6") -> Image.Image:
    """Ícones vetoriais rasterizados em 8x e reduzidos com antialiasing."""
    scale = 8
    image = Image.new("RGB", (width * scale, height * scale), background)
    draw = ImageDraw.Draw(image)
    color = "#16833a" if hovered else "#365b4d"
    def coords(values):
        return tuple(round(value * scale) for value in values)
    center_x, center_y = width / 2, height / 2
    if kind == "play":
        radius = min(width, height) * 0.36
        draw.ellipse(coords((center_x-radius, center_y-radius, center_x+radius, center_y+radius)),
                     fill="#dceee3" if hovered else "#e8f0eb", outline=color, width=2 * scale)
        if playing:
            for x in (center_x - 7, center_x + 3):
                draw.rounded_rectangle(coords((x, center_y - 9, x + 4, center_y + 9)),
                                       radius=scale, fill=color)
        else:
            draw.polygon([coords((center_x - 5, center_y - 10)),
                          coords((center_x + 10, center_y)), coords((center_x - 5, center_y + 10))], fill=color)
    else:
        direction = -1 if kind == "slower" else 1
        for offset in (-7, 7):
            points = [coords((center_x + offset - direction * 6, center_y - 10)),
                      coords((center_x + offset + direction * 6, center_y)),
                      coords((center_x + offset - direction * 6, center_y + 10))]
            draw.line(points, fill=color, width=3 * scale, joint="curve")
            for x, y in points:
                radius = 1.5 * scale
                draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
    return image.resize((width, height), Image.Resampling.LANCZOS)


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
        self._icon_cache = {}
        self.bind("<Configure>", lambda _event: self._draw())
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
        width = self.winfo_width() if self.winfo_width() > 1 else self.winfo_reqwidth()
        height = self.winfo_height() if self.winfo_height() > 1 else self.winfo_reqheight()
        key = (width, height, self.playing, self.hovered)
        if key not in self._icon_cache:
            rendered = preview_control_icon_image(
                self.kind, width, height, self.playing, self.hovered, self._background,
            )
            self._icon_cache[key] = ImageTk.PhotoImage(rendered, master=self)
            while len(self._icon_cache) > 12:
                self._icon_cache.pop(next(iter(self._icon_cache)))
        self._icon_image = self._icon_cache[key]
        self.delete("all")
        self.create_image(width / 2, height / 2, image=self._icon_image)


def diarias_action_icon_image(kind: str, size: int = 26) -> Image.Image:
    """Ícones de arquivo, PDF e impressora com traços suaves em oito vezes o tamanho."""
    scale = 8
    image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    def box(coords):
        return tuple(round(value * scale * size / 28) for value in coords)
    navy, green, red = "#29485b", "#16833a", "#bc4149"
    stroke = max(1, round(1.5 * scale * size / 28))
    if kind == "warning":
        draw.polygon([box((14, 2)), box((27, 26)), box((1, 26))], fill="#f4bb45", outline="#ac751d", width=stroke)
        draw.line(box((14, 9, 14, 17)), fill="#533b0c", width=stroke * 2)
        draw.ellipse(box((13, 20, 15, 22)), fill="#533b0c")
    elif kind == "print":
        draw.rounded_rectangle(box((6, 2, 22, 14)), radius=scale, fill="#ffffff", outline=navy, width=stroke)
        draw.rounded_rectangle(box((2, 10, 26, 22)), radius=2 * scale, fill="#dce9e9", outline=navy, width=stroke)
        draw.ellipse(box((21, 13, 23, 15)), fill=green)
        draw.rectangle(box((7, 18, 21, 27)), fill="#ffffff", outline=navy, width=stroke)
        for y in (21, 24):
            draw.line(box((10, y, 18, y)), fill=navy, width=stroke)
    else:
        color = green if kind == "office" else red
        draw.rounded_rectangle(box((5, 2, 23, 26)), radius=2 * scale, fill="#ffffff", outline=navy, width=stroke)
        draw.polygon([box((17, 2)), box((23, 8)), box((17, 8))], fill="#dce9e9", outline=navy)
        draw.rounded_rectangle(box((2, 10, 20, 20)), radius=scale, fill=color)
        if kind == "office":
            draw.line(box((5, 13, 5, 17, 8, 15, 11, 17, 11, 13)), fill="#ffffff", width=stroke, joint="curve")
            draw.line(box((14, 13, 17, 17)), fill="#ffffff", width=stroke)
            draw.line(box((17, 13, 14, 17)), fill="#ffffff", width=stroke)
        elif kind == "pdf":
            draw.line(box((6, 17, 6, 13, 9, 13, 9, 15, 6, 15)), fill="#ffffff", width=stroke)
            draw.line(box((12, 17, 12, 13, 15, 13, 16, 14, 16, 16, 15, 17, 12, 17)), fill="#ffffff", width=stroke)
        else:
            raise ValueError("Ícone de Diárias desconhecido.")
        draw.line(box((9, 23, 19, 23)), fill=navy, width=stroke)
    return image.resize((size, size), Image.Resampling.LANCZOS)
