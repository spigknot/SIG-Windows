"""Widgets Tk reutilizaveis (tooltip, botao-icone e slider de nos).

Sem regra de negocio; usado por sig_app.py e ffmpeg_tools_panel.py.

O `NodeSlider` e uma porta do slider do projeto TurboCore
(`turbocore/nodeslider.py`): traco fino + um no por opcao + bolinha azul, com
atracao magnetica. Mantido igual para as duas aplicacoes terem o mesmo visual.
"""

from tkinter import Canvas, Toplevel, ttk

import math


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

    Regra do usuário (11/09): 1, 2, 3, ..., n, 3n/2, 2n, 5n/2, 3n, 7n/2, 4n —
    ou seja, n + 6 opções. Conta que não dá exato aproxima para o inteiro mais
    próximo, com o empate subindo (4.5 -> 5, 7.5 -> 8, 12.5 -> 13); a lista é
    sempre crescente e sem repetições (com n = 1 as seis frações caem em
    1/2/3/4 e sobram 4 opções — não existem 7 inteiros distintos até 4n).

    Vantagem sobre a lista antiga (só múltiplos do passo): o valor recomendado
    n/2 passa a existir como nó — antes, num 4 núcleos, o recomendado 2 era
    encaixado à força em 4.
    """
    nucleos = max(1, int(cpu_count))
    valores = list(range(1, nucleos + 1))
    for fator in (3, 4, 5, 6, 7, 8):        # 3n/2, 2n, 5n/2, 3n, 7n/2, 4n
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
