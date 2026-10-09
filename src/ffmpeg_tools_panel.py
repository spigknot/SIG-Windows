"""Painel de ferramentas FFmpeg (aba 'FFmpeg'): conversao, corte, juncao,
aceleracao (NVENC/CPU), player embutido e linha do tempo.

Estrutura:
  VideoAcceleration/MediaProfile = dados de midia/aceleracao (dataclasses)
  RangeTimeline/InsertAudioTimeline = widgets de linha do tempo
  EmbeddedMediaPlayer = player de previa embutido
  FfmpegTaskTracker = estado/agregacao de tarefas em lote
  FfmpegToolsPanel = a aba (UI + orquestracao; nao contem regra de negocio de STT)

Logs de comando: log_formatting.py. Tipos de arquivo: media_files.py.
NAO contem transcricao/STT (ver stt_clients.py)."""

import concurrent.futures
import ctypes
import json
import math
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
import webbrowser
from array import array
from PIL import Image, ImageTk
from app_env import app_base_dir
from dataclasses import dataclass, replace
from fractions import Fraction
from domain_models import Cancelled
from log_formatting import (
    FFMPEG_COMMAND_BLOCK_TAG,
    format_ffmpeg_command_for_log,
    format_ffmpeg_commands_for_log,
)
from media_files import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from pathlib import Path
from tkinter import (
    BOTH,
    BOTTOM,
    BooleanVar,
    Canvas,
    END,
    IntVar,
    LEFT,
    RIGHT,
    StringVar,
    Toplevel,
    X,
    Y,
    filedialog,
    messagebox,
    ttk,
)
from ui_widgets import PreviewIconButton, create_tooltip
import smart_join_planner
import smart_cut_planner
import smart_insert_planner
import smart_insert_flac
import smart_insert_wave
from ffmpeg_recovery import RecoveryJob
from video_encoders import (
    CATALOG,
    ENCODER_ADVANCED_AUTO,
    ENCODER_PATH_CPU,
    ENCODER_PATH_GPU,
    PATH_LABELS,
    SHORT_JOB_SECONDS,
    EncoderOption,
    available_keys,
    catalog_options,
    hevc_tag_arguments,
    normalize_codec,
    options_from_tuples,
    options_to_tuples,
    resolve_encoder,
)


VIDEO_QUALITY_LEVELS = ("Máxima", "Muito alta", "Alta", "Média", "Econômica")
# T18: velocidade e qualidade são eixos SEPARADOS (regra do plano). O preset do
# x264/x265 troca tamanho por tempo sem mexer na escala de qualidade (CRF).
VIDEO_SPEED_LEVELS = ("Rápida", "Equilibrada", "Máxima qualidade")
VIDEO_SPEED_PRESETS = {"Rápida": "veryfast", "Equilibrada": "fast", "Máxima qualidade": "medium"}
VIDEO_SPEED_MENU_LABELS = {
    "Rápida": "Rápida (arquivos maiores, processa antes)",
    "Equilibrada": "Equilibrada (recomendada)",
    "Máxima qualidade": "Máxima qualidade (arquivos menores, mais lenta)",
}


VIDEO_QUALITY_MENU_LABELS = {
    "Máxima": "Máxima",
    "Muito alta": "Muito alta",
    "Alta": "Alta (Recomendado)",
    "Média": "Média",
    "Econômica": "Econômica",
}


# --- Palco de prévia (players das ferramentas FFmpeg) ------------------------
# Regras do usuário: o vídeo ocupa TODO o espaço disponível da aba (sem perder a
# proporção e sem ficar em cima dos controles), a roda do mouse dá zoom (para
# cima aproxima, para baixo afasta) e o arrasto com o botão esquerdo move o
# quadro quando ele está ampliado.
PREVIEW_STAGE_BACKGROUND = "#f4f7f6"
# Zoom: 1.0 = o vídeo INTEIRO no palco (não tem zoom out além disso) e até 5x
# para aproximar detalhes.
PREVIEW_ZOOM_MIN = 1.0
PREVIEW_ZOOM_MAX = 5.0
PREVIEW_ZOOM_STEP = 1.25
PREVIEW_ZOOM_RESTART_MS = 250
PREVIEW_SPEED_VALUES = (0.25, 0.5, 1.0, 2.0, 4.0)
FFMPEG_SIDEBAR_WIDTH = 252
WAVEFORM_POINTS = 1200
WAVEFORM_SAMPLE_RATE = 8000

# Modos de corte da aba Cortar (na ordem exibida; SmartCut é o padrão).
CUT_MODE_SMART = "SmartCut"
CUT_MODE_REENCODE = "Reencode Completo"
CUT_MODE_COPY = "Sem Reencode"
CUT_MODES = (CUT_MODE_SMART, CUT_MODE_REENCODE, CUT_MODE_COPY)
CUT_MODE_HELP = (
    "SmartCut: corte preciso e rápido, mas EXPERIMENTAL — copia os trechos que já começam em "
    "keyframe e reencoda apenas as bordas até os tempos exatos. O áudio é cortado em uma "
    "passagem contínua para evitar emendas e perda de sincronização.\n\n"
    "Em áudio puro, SmartCut usa o mesmo processamento do Reencode Completo para manter "
    "a precisão. Recodificar áudio costuma ser muito mais leve que recodificar vídeo.\n\n"
    "Reencode Completo: reencoda todo o trecho — lento e preciso.\n\n"
    "Sem Reencode: copia os streams sem reencodar — rápido e menos preciso, porque início e fim "
    "escorregam até o keyframe/pacote disponível."
)
PREVIEW_STAGE_MIN_WIDTH = 240
PREVIEW_STAGE_MIN_HEIGHT = 135
PREVIEW_STAGE_MAX_HEIGHT = 760
PREVIEW_STAGE_MARGIN = 8
# Orçamentos medidos nesta máquina (FFmpeg rawvideo + PIL + PhotoImage, 15 fps de
# alvo): 1200x675 ~= 40 quadros/s, 1600x900 ~= 22, 1920x1080 ~= 16. Renderizar o
# pipeline acima de 1600x900 derruba a taxa da prévia sem ganho de imagem.
PREVIEW_RENDER_MAX_PIXELS = 1600 * 900
# Limite da imagem exibida (zoom): evita PhotoImage gigante na memória.
PREVIEW_DISPLAY_MAX_PIXELS = 2600 * 1500


@dataclass
class PreviewViewport:
    """Zoom e deslocamento de um palco de prévia (um por ferramenta)."""

    zoom: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    media_width: int = 0
    media_height: int = 0
    stage_width: int = 0
    stage_height: int = 0
    drag_origin: tuple[int, int] | None = None
    drag_offsets: tuple[float, float] = (0.0, 0.0)


def preview_aspect(media_width: int, media_height: int) -> float:
    """Proporção exibida da mídia (16:9 quando as dimensões não são conhecidas)."""
    if media_width > 0 and media_height > 0:
        return media_width / media_height
    return 16.0 / 9.0


def parse_tk_padding(value) -> tuple[int, ...]:
    """Valores numéricos de um 'pady'/'padding' do Tk.

    O Tk devolve objetos de pixel como "<pixel object: '12'>" e listas como
    "{12 12 12 12}" — por isso a extração é por dígitos, não por split cru.
    """
    if isinstance(value, (tuple, list)):
        partes = [str(item) for item in value]
    else:
        partes = [str(value)]
    valores: list[int] = []
    for parte in partes:
        encontrados = re.findall(r"-?\d+", parte)
        if not encontrados:
            return ()
        valores.extend(int(numero) for numero in encontrados)
    return tuple(valores)


def vertical_padding_total(value) -> int:
    """Soma do espaçamento vertical de um 'pady' do pack (topo + base)."""
    return sum(parse_tk_padding(value))


def frame_vertical_padding(value) -> int:
    """Soma do padding vertical interno de um frame ttk (1, 2 ou 4 valores)."""
    valores = parse_tk_padding(value)
    if len(valores) == 1:
        return valores[0] * 2
    if len(valores) == 2:
        return valores[0] * 2
    if len(valores) >= 4:
        return valores[0] + valores[2]
    return 0


def preview_stage_size(
    available_width: float,
    available_height: float,
    media_width: int,
    media_height: int,
) -> tuple[int, int]:
    """Maior palco com a proporção da mídia que cabe no espaço disponível.

    Ele encosta em pelo menos um dos limites (largura ou altura): é isso que faz
    o vídeo preencher todo o espaço sem barras sobrando e sem distorcer. Os
    mínimos utilizáveis (PREVIEW_STAGE_MIN_*) vencem a caixa — numa janela
    pequena o palco mantém o tamanho mínimo e a aba rola.
    """
    aspect = preview_aspect(media_width, media_height)
    width = max(PREVIEW_STAGE_MIN_WIDTH, int(available_width))
    height = width / aspect
    limit = max(PREVIEW_STAGE_MIN_HEIGHT, int(available_height))
    if height > limit:
        height = limit
        width = height * aspect
    if width < PREVIEW_STAGE_MIN_WIDTH:
        width = PREVIEW_STAGE_MIN_WIDTH
        height = width / aspect
    if height < PREVIEW_STAGE_MIN_HEIGHT:
        height = PREVIEW_STAGE_MIN_HEIGHT
        width = height * aspect
    return max(4, int(round(width))), max(4, int(round(height)))


def preview_zoom_clamped(zoom: float) -> float:
    return max(PREVIEW_ZOOM_MIN, min(PREVIEW_ZOOM_MAX, float(zoom)))


def preview_drawn_size(stage_width: int, stage_height: int, zoom: float) -> tuple[int, int, float]:
    """Tamanho desenhado do quadro (par) e zoom efetivo, limitado pelo orçamento."""
    stage_width = max(2, int(stage_width))
    stage_height = max(2, int(stage_height))
    budget = (PREVIEW_DISPLAY_MAX_PIXELS / max(1, stage_width * stage_height)) ** 0.5
    effective = min(preview_zoom_clamped(zoom), max(PREVIEW_ZOOM_MIN, budget))
    width = max(2, int(round(stage_width * effective)))
    height = max(2, int(round(stage_height * effective)))
    # O scale/pad do FFmpeg exige dimensões pares.
    return width - width % 2, height - height % 2, effective


def preview_render_size(
    drawn_width: int,
    drawn_height: int,
    media_width: int,
    media_height: int,
) -> tuple[int, int]:
    """Resolução que o pipeline de quadros produz: no máximo a nativa e o orçamento."""
    width = max(2, int(drawn_width))
    height = max(2, int(drawn_height))
    scale = 1.0
    if media_width > 0:
        scale = min(scale, media_width / width)
    pixels = width * height
    if pixels > PREVIEW_RENDER_MAX_PIXELS:
        scale = min(scale, (PREVIEW_RENDER_MAX_PIXELS / pixels) ** 0.5)
    width = max(2, int(round(width * scale)))
    height = max(2, int(round(height * scale)))
    return width - width % 2, height - height % 2


def preview_clamped_offset(stage: int, drawn: int, offset: float) -> float:
    """Deslocamento válido: nunca deixa aparecer fundo no palco enquanto ampliado."""
    if drawn <= stage:
        return 0.0
    return float(min(0, max(int(stage) - int(drawn), int(round(offset)))))


def preview_view_rect(
    stage_width: int,
    stage_height: int,
    drawn_width: int,
    drawn_height: int,
    offset_x: float,
    offset_y: float,
) -> tuple[int, int]:
    """Canto superior esquerdo do quadro no palco (centralizado quando menor)."""
    if drawn_width <= stage_width:
        x = (int(stage_width) - int(drawn_width)) // 2
    else:
        x = int(preview_clamped_offset(stage_width, drawn_width, offset_x))
    if drawn_height <= stage_height:
        y = (int(stage_height) - int(drawn_height)) // 2
    else:
        y = int(preview_clamped_offset(stage_height, drawn_height, offset_y))
    return x, y


def preview_zoom_offsets(
    stage_width: int,
    stage_height: int,
    drawn_width: int,
    drawn_height: int,
    offset_x: float,
    offset_y: float,
    zoomed_width: int,
    zoomed_height: int,
    cursor_x: float,
    cursor_y: float,
) -> tuple[float, float]:
    """Deslocamentos que mantêm sob o cursor o mesmo ponto da imagem."""
    origin_x, origin_y = preview_view_rect(
        stage_width, stage_height, drawn_width, drawn_height, offset_x, offset_y
    )
    ratio_x = (cursor_x - origin_x) / max(1, drawn_width)
    ratio_y = (cursor_y - origin_y) / max(1, drawn_height)
    return cursor_x - ratio_x * zoomed_width, cursor_y - ratio_y * zoomed_height


# --- Seleção de área no palco (recorte por pixels) ---------------------------
# Quadro congelado da previa: espera curta para agrupar o arrasto da linha do tempo
# (o log mostrou um FFmpeg por passo) e cache dos ultimos quadros extraidos.
PREVIEW_STILL_DEBOUNCE_MS = 120
PREVIEW_STILL_CACHE_SIZE = 8


PREVIEW_SELECTION_OUTLINE = "#ffd700"
PREVIEW_SELECTION_HANDLE_FILL = "#ffd700"
PREVIEW_SELECTION_TAG = "preview_selection"
PREVIEW_SELECTION_WIDTH = 1
PREVIEW_SELECTION_MIN_SIZE = 8
PREVIEW_SELECTION_HANDLE = 7
PREVIEW_SELECTION_HANDLE_SIZE = 4
# Movimento mínimo para o botão direito virar um desenho (abaixo disso é clique).
PREVIEW_SELECTION_DRAG_THRESHOLD = 4
PREVIEW_SELECTION_CURSORS = {
    "n": "sb_v_double_arrow",
    "s": "sb_v_double_arrow",
    "e": "sb_h_double_arrow",
    "w": "sb_h_double_arrow",
    "nw": "sizing",
    "ne": "sizing",
    "sw": "sizing",
    "se": "sizing",
    "move": "hand2",
}


@dataclass
class PreviewSelection:
    """Área escolhida pelo usuário, em FRAÇÕES (0..1) do quadro.

    Guardar em frações faz a seleção sobreviver ao zoom, ao arrasto e ao
    redimensionamento da janela: ela continua exatamente sobre os mesmos pixels.
    """

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    def to_view(self, drawn_width: int, drawn_height: int, origin_x: float, origin_y: float) -> tuple[float, float, float, float]:
        """Retângulo na tela (view) sobre o quadro desenhado, que já inclui o zoom."""
        escala_x = max(1, int(drawn_width))
        escala_y = max(1, int(drawn_height))
        return (
            self.left * escala_x + origin_x,
            self.top * escala_y + origin_y,
            self.right * escala_x + origin_x,
            self.bottom * escala_y + origin_y,
        )


def preview_fraction_from_view(
    x: float,
    y: float,
    drawn_width: int,
    drawn_height: int,
    origin_x: float,
    origin_y: float,
) -> tuple[float, float]:
    """Fração (0..1) do quadro para um ponto da tela, limitada ao vídeo.

    O tamanho recebido é o do quadro DESENHADO (que já inclui o zoom): assim o
    desenho e o recorte em pixels usam exatamente o mesmo referencial.
    """
    escala_x = max(1, int(drawn_width))
    escala_y = max(1, int(drawn_height))
    fracao_x = (x - origin_x) / escala_x
    fracao_y = (y - origin_y) / escala_y
    return min(1.0, max(0.0, fracao_x)), min(1.0, max(0.0, fracao_y))


def selection_from_drag(
    start: tuple[float, float],
    end: tuple[float, float],
    minimum_fraction_x: float,
    minimum_fraction_y: float,
) -> PreviewSelection | None:
    """Seleção a partir de dois cantos (frações) — None quando é pequena demais."""
    left, right = sorted((start[0], end[0]))
    top, bottom = sorted((start[1], end[1]))
    left = min(1.0, max(0.0, left))
    top = min(1.0, max(0.0, top))
    right = min(1.0, max(0.0, right))
    bottom = min(1.0, max(0.0, bottom))
    if right - left < minimum_fraction_x or bottom - top < minimum_fraction_y:
        return None
    return PreviewSelection(left, top, right, bottom)


def selection_handle_at(rect: tuple[float, float, float, float], x: float, y: float, tolerance: int = PREVIEW_SELECTION_HANDLE) -> str | None:
    """Handle sob o ponteiro (coords de tela): n/s/e/w/cantos, 'move' ou None."""
    left, top, right, bottom = rect
    nos_x = (abs(x - left) <= tolerance, abs(x - right) <= tolerance)
    nos_y = (abs(y - top) <= tolerance, abs(y - bottom) <= tolerance)
    dentro_x = left - tolerance <= x <= right + tolerance
    dentro_y = top - tolerance <= y <= bottom + tolerance
    if not (dentro_x and dentro_y):
        return None
    if nos_x[0] and nos_y[0]:
        return "nw"
    if nos_x[1] and nos_y[0]:
        return "ne"
    if nos_x[0] and nos_y[1]:
        return "sw"
    if nos_x[1] and nos_y[1]:
        return "se"
    if nos_y[0]:
        return "n"
    if nos_y[1]:
        return "s"
    if nos_x[0]:
        return "w"
    if nos_x[1]:
        return "e"
    if left <= x <= right and top <= y <= bottom:
        return "move"
    return None


def selection_resized(
    selection: PreviewSelection,
    handle: str,
    fracao_x: float,
    fracao_y: float,
    minimum_fraction_x: float,
    minimum_fraction_y: float,
) -> PreviewSelection:
    """Novo retângulo ao arrastar um lado/canto (respeita tamanho mínimo e limites)."""
    left, top, right, bottom = selection.left, selection.top, selection.right, selection.bottom
    fracao_x = min(1.0, max(0.0, fracao_x))
    fracao_y = min(1.0, max(0.0, fracao_y))
    if "w" in handle:
        left = min(fracao_x, right - minimum_fraction_x)
    if "e" in handle:
        right = max(fracao_x, left + minimum_fraction_x)
    if "n" in handle:
        top = min(fracao_y, bottom - minimum_fraction_y)
    if "s" in handle:
        bottom = max(fracao_y, top + minimum_fraction_y)
    return PreviewSelection(
        min(1.0, max(0.0, left)),
        min(1.0, max(0.0, top)),
        min(1.0, max(0.0, right)),
        min(1.0, max(0.0, bottom)),
    )


def selection_moved(
    selection: PreviewSelection,
    delta_x: float,
    delta_y: float,
) -> PreviewSelection:
    """Move a seleção sem deixá-la sair do quadro."""
    largura, altura = selection.width, selection.height
    left = min(max(0.0, selection.left + delta_x), 1.0 - largura)
    top = min(max(0.0, selection.top + delta_y), 1.0 - altura)
    return PreviewSelection(left, top, left + largura, top + altura)


def selection_crop_pixels(
    selection: PreviewSelection,
    video_width: int,
    video_height: int,
) -> tuple[int, int, int, int] | None:
    """(x, y, largura, altura) em PIXELS do vídeo, par e dentro do quadro.

    O FFmpeg (e o yuv420p) trabalham melhor com valores pares; o mínimo é 2x2.
    """
    if video_width <= 0 or video_height <= 0:
        return None
    if selection.width <= 0 or selection.height <= 0:
        return None
    x0 = int(round(selection.left * video_width))
    y0 = int(round(selection.top * video_height))
    x1 = int(round(selection.right * video_width))
    y1 = int(round(selection.bottom * video_height))
    x0 = min(max(0, x0), max(0, video_width - 2))
    y0 = min(max(0, y0), max(0, video_height - 2))
    x1 = min(max(x0 + 2, x1), video_width)
    y1 = min(max(y0 + 2, y1), video_height)
    # A grade de croma (yuv420p) exige origem E tamanho PARES: com a origem
    # ímpar o FFmpeg entrega o retângulo deslocado um pixel (medido: pedir y=87
    # entregou a linha 86). Alinhar para BAIXO faz o filtro, o diálogo e o
    # rótulo anunciarem exatamente o retângulo que sai no arquivo.
    x0 -= x0 % 2
    y0 -= y0 % 2
    largura = (x1 - x0) - (x1 - x0) % 2
    altura = (y1 - y0) - (y1 - y0) % 2
    largura = max(2, largura)
    altura = max(2, altura)
    return x0, y0, largura, altura


def selection_crop_filter(crop: tuple[int, int, int, int]) -> str:
    """Filtro de recorte do FFmpeg para a seleção."""
    x, y, largura, altura = crop
    return f"crop={largura}:{altura}:{x}:{y}"


def audio_offset_warning(
    audio_start_seconds: float,
    container_start_seconds: float = 0.0,
    tolerance_ms: float = 60.0,
) -> str | None:
    """Aviso quando o áudio da fonte começa deslocado do vídeo (T12).

    A comparação é com o início do CONTÊINER (o começo do vídeo), não com zero:
    um arquivo com PTS inicial deslocado tem os dois streams juntos e não é um
    offset de A/V. Um offset pequeno é ancoragem de pacote; um grande costuma ser
    intencional — e a saída deste app normaliza os dois streams no início.
    Medido: fonte com o áudio 176 ms depois do vídeo saiu com os dois em 0.000.
    """
    try:
        atraso_ms = (float(audio_start_seconds) - float(container_start_seconds)) * 1000.0
    except (TypeError, ValueError):
        return None
    if abs(atraso_ms) <= tolerance_ms:
        return None
    return (
        f"Na fonte, o áudio começa {atraso_ms:.0f} ms depois do vídeo: a saída "
        "normaliza os dois streams no início e o deslocamento não é mantido."
    )


def variable_rate_warning(fps: str, average_rate: str) -> str | None:
    """Aviso quando a fonte tem taxa de quadros VARIÁVEL (T12).

    O banner do ffmpeg mostra 'r_frame_rate fps' e 'tbr' (a taxa média). Quando
    diferem, a fonte é VFR — e reencodar converte para taxa fixa. Medido: uma
    fonte de avg 18,7 fps saiu com avg 21,3 fps sem nenhum aviso.
    """
    try:
        fixa = float(str(fps).replace(",", "."))
        media = float(str(average_rate).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if fixa <= 0 or media <= 0:
        return None
    if abs(fixa - media) / fixa <= 0.02:
        return None
    return (
        f"Fonte com taxa de quadros variável ({fps} fps médios, {average_rate} tbr nominais): "
        "a saída reencodada sai em taxa fixa. Para preservar a taxa original, use o modo Sem Reencode."
    )


def color_depth_warning(pixel_format: str) -> str | None:
    """Aviso quando a fonte tem mais de 8 bits por componente.

    Reencodar 10/12 bits (yuv420p10le, p010le, …) para yuv420p reduz a
    profundidade de cor — e sem aviso isso acontece em SILÊNCIO. O padrão desta
    rodada é avisar (bloquear fica para quando houver suporte real a 10 bits).
    """
    formato = (pixel_format or "").lower()
    if not formato:
        return None
    marcadores = ("10le", "10be", "12le", "12be", "16le", "16be", "p010", "p016",
                  "y210", "y410", "x2rgb10", "rgb48", "rgba64")
    if any(marcador in formato for marcador in marcadores):
        return (
            f"Fonte em {pixel_format}: o reencode grava em 8 bits (yuv420p) e a "
            "profundidade de cor será reduzida — o modo Sem Reencode preserva o original."
        )
    return None


def copy_effective_start_seconds(start: float, keyframes: list[float]) -> float:
    """Início EFETIVO de um corte em stream copy: o último keyframe <= início.

    Copiar streams não corta em qualquer ponto: o FFmpeg recua até o keyframe
    disponível. Declarar isso é o contrato do modo Sem Reencode (a promessa tem
    que ser exatamente a entrega).
    """
    anteriores = [valor for valor in keyframes if valor <= start + 0.001]
    return max(anteriores) if anteriores else 0.0


def copy_interval_message(
    requested_start: float,
    requested_end: float,
    effective_start: float,
) -> str:
    """Texto do intervalo pedido x efetivo do modo Sem Reencode."""
    pedido = max(0.0, requested_end - requested_start)
    efetivo = max(0.0, requested_end - effective_start)
    recuo = requested_start - effective_start
    if recuo <= 0.001:
        return (
            f"Sem Reencode: intervalo efetivo {effective_start:.3f}–{requested_end:.3f} s "
            f"({efetivo:.3f} s) — igual ao pedido."
        )
    return (
        f"Sem Reencode: intervalo efetivo {effective_start:.3f}–{requested_end:.3f} s "
        f"({efetivo:.3f} s); pedido {requested_start:.3f}–{requested_end:.3f} s ({pedido:.3f} s) — "
        f"o início recua {recuo:.3f} s até o keyframe anterior."
    )


def smart_join_segment_order(
    clip_count: int,
    has_body: list[bool],
    junction_indexes: list[int],
) -> list[tuple[str, int]]:
    """Ordem dos segmentos do SmartJoin: corpo j, emenda j, corpo j, … 

    A junção j fica ENTRE o corpo j e o corpo j+1 (é o contrato do plano). O
    Android já montava assim (corpo e emenda no mesmo laço); o port para o
    Windows separou em dois laços e as emendas caíam todas no fim — medido no
    N4: a linha do tempo saía 2>3>4>5>1 em vez de 1>2>3>4>5.
    """
    juncoes = set(junction_indexes)
    ordem: list[tuple[str, int]] = []
    for index in range(clip_count):
        if index < len(has_body) and has_body[index]:
            ordem.append(("body", index))
        if index in juncoes:
            ordem.append(("bridge", index))
    return ordem


def selection_crop_label(crop: tuple[int, int, int, int]) -> str:
    """Texto do recorte EFETIVO (os mesmos números que o filtro aplica).

    Existe para o rótulo nunca divergir do que sai no arquivo: o retângulo já
    vem alinhado à grade par por selection_crop_pixels.
    """
    x, y, largura, altura = crop
    return f"{largura} x {altura} pixels a partir de ({x}, {y})"


def selection_filter_atoms(filters: str) -> list[str]:
    """Operações atômicas de giro/espelhamento na ordem em que são aplicadas."""
    atomos = []
    for parte in str(filters or "").split(","):
        parte = parte.strip()
        if parte in ("transpose=1", "transpose=2", "hflip", "vflip"):
            atomos.append(parte)
    return atomos


def selection_after_filter_atom(selection: PreviewSelection, atom: str) -> PreviewSelection:
    """Seleção reexpressa depois de UMA operação (em frações do quadro resultante).

    As operações suportadas (giro em múltiplos de 90° e espelhamentos) levam
    retângulos alinhados em retângulos alinhados — por isso a conta é exata.
    """
    left, top, right, bottom = selection.left, selection.top, selection.right, selection.bottom
    if atom == "hflip":
        return PreviewSelection(1.0 - right, top, 1.0 - left, bottom)
    if atom == "vflip":
        return PreviewSelection(left, 1.0 - bottom, right, 1.0 - top)
    if atom == "transpose=1":
        return PreviewSelection(1.0 - bottom, left, 1.0 - top, right)
    if atom == "transpose=2":
        return PreviewSelection(top, 1.0 - right, bottom, 1.0 - left)
    return selection


def selection_between_filters(
    selection: PreviewSelection,
    old_filters: str,
    new_filters: str,
) -> PreviewSelection:
    """Reexpressa a seleção quando o giro muda: ela continua sobre os MESMOS pixels.

    Desfaz o giro antigo (ordem inversa, operações invertidas) e aplica o novo —
    o resultado é a mesma região da imagem original na nova orientação exibida.
    """
    invertidos = {
        "hflip": "hflip",
        "vflip": "vflip",
        "transpose=1": "transpose=2",
        "transpose=2": "transpose=1",
    }
    atual = selection
    for atomo in reversed(selection_filter_atoms(old_filters)):
        atual = selection_after_filter_atom(atual, invertidos[atomo])
    for atomo in selection_filter_atoms(new_filters):
        atual = selection_after_filter_atom(atual, atomo)
    return atual


@dataclass(frozen=True)
class VideoAcceleration:
    key: str
    label: str
    encoder: str


@dataclass(frozen=True)
class AudioTrackProfile:
    """Perfil de UMA faixa de áudio da entrada (uma por stream).

    Motivo: o MediaProfile único expõe só a primeira faixa, e usá-lo para
    reencodar todas impõe taxa, canais e bitrate errados às demais (medido:
    faixa B estéreo/48 kHz saía mono/44,1 kHz).
    """

    index: int
    codec: str
    bitrate: str
    rate: int
    channels: int
    layout: str
    default: bool = False
    language: str = ""


@dataclass(frozen=True)
class MediaProfile:
    """Características da mídia usadas quando uma operação precisa reencodar."""

    duration: float
    has_audio: bool
    width: int
    height: int
    fps: str
    video_bitrate: str
    audio_bitrate: str
    audio_rate: int
    audio_channels: int
    audio_layout: str
    has_video: bool = True
    rotation: int = 0
    audio_codec: str = ""
    video_codec: str = ""
    pix_fmt: str = ""
    timebase: str = ""
    sar: str = ""
    audio_streams: int = 0
    subtitle_streams: int = 0
    data_streams: int = 0
    audio_tracks: tuple["AudioTrackProfile", ...] = ()
    # F-roteiro (T12): taxa media (`tbr`) da fonte. Quando difere do `fps`
    # (r_frame_rate), a fonte tem taxa VARIAVEL — e reencodar a converte em taxa
    # fixa; isso precisa ser avisado, nunca silencioso.
    average_rate: str = ""
    # F-roteiro (T12): atraso do audio em relacao ao video na FONTE (o banner
    # mostra "start X" na linha do audio). Um offset intencional nao pode
    # desaparecer sem aviso quando a saida normaliza os dois streams.
    audio_start_seconds: float = 0.0
    container_start_seconds: float = 0.0
    audio_sample_fmt: str = ""
    audio_bits_per_raw_sample: int = 0

    # Mantém compatibilidade com as rotinas existentes que tratam o perfil como tupla.
    def __iter__(self):
        yield from (self.duration, self.has_audio, self.width, self.height, self.fps)

    def __getitem__(self, index: int):
        return (self.duration, self.has_audio, self.width, self.height, self.fps)[index]


# Codecs que podem ser COPIADOS (sem reencodar) ao extrair áudio, por
# extensão aceita pelo app. Espelha o canCopyAudioWithoutConversion do Android.
EXTRACT_COPY_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "aac": ("m4a", "aac"),
    "mp3": ("mp3",),
    "opus": ("opus",),
    "vorbis": ("ogg",),
    "flac": ("flac",),
}


def extract_can_copy(
    media: MediaProfile,
    extension: str,
    rate: str,
    channels: str,
    has_trim: bool,
) -> bool:
    """Cópia sem perdas só quando o pedido é o PRÓPRIO stream.

    Mesmo codec (extensão compatível), mesma taxa e mesmos canais e SEM recorte
    — recorte exige reencodar (stream copy não corta por amostras com precisão).
    Era o comportamento do Android; no Windows o Extrair sempre reencodava.
    """
    if has_trim:
        return False
    codec = (media.audio_codec or "").lower()
    if not codec:
        return False
    if codec.startswith("pcm_"):
        compativeis: tuple[str, ...] = ("wav",)
    else:
        compativeis = EXTRACT_COPY_EXTENSIONS.get(codec, ())
    if not compativeis or extension.lower() not in compativeis:
        return False
    try:
        if rate and int(str(rate)) != int(media.audio_rate):
            return False
        if channels and int(str(channels)) != int(media.audio_channels):
            return False
    except (TypeError, ValueError):
        return False
    return True


def waveform_amplitudes(levels: tuple[float, ...], start: float, end: float, count: int) -> list[float]:
    """Picos por barra, preservando os transientes ao reduzir a resolução."""
    if not levels or count <= 0:
        return [0.0] * max(0, count)
    first = max(0.0, min(1.0, start)) * len(levels)
    last = max(first, min(1.0, end) * len(levels))
    values = []
    for index in range(count):
        left = min(len(levels) - 1, int(first + (last - first) * index / count))
        right = min(len(levels), max(left + 1, math.ceil(first + (last - first) * (index + 1) / count)))
        values.append(max(levels[left:right], default=0.0))
    return values


class RangeTimeline(Canvas):
    """Linha do tempo simples com playhead e marcadores de início/fim arrastáveis."""

    def __init__(self, parent, on_change, select_range: bool = True, **kwargs):
        super().__init__(parent, height=52, highlightthickness=0, background="#ffffff", **kwargs)
        self.duration = 0.0
        self.start = 0.0
        self.end = 0.0
        self.position = 0.0
        self.on_change = on_change
        self.select_range = select_range
        self.transition_points: tuple[float, ...] = ()
        self.transition_label = ""
        self.drag_target: str | None = None
        self.bind("<Configure>", lambda _event: self.draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.draw()

    def set_media(self, duration: float) -> None:
        self.duration = max(0.0, duration)
        self.start = 0.0
        self.end = self.duration
        self.position = 0.0
        self.transition_points = ()
        self.transition_label = ""
        self.draw()

    def set_range(self, start: float, end: float) -> None:
        if self.duration <= 0:
            return
        self.start = max(0.0, min(start, self.duration))
        self.end = max(self.start, min(end, self.duration))
        # A cabeça de reprodução vive DENTRO do trecho marcado: se os marcadores
        # se moveram por cima dela, ela vai junto.
        self.position = min(max(self.position, self.start), self.end)
        self.draw()

    def set_position(self, position: float) -> None:
        """Posição da cabeça de reprodução, sempre entre os marcadores verde e vermelho."""
        if self.duration <= 0:
            self.position = 0.0
        else:
            self.position = min(max(self.start, min(position, self.duration)), self.end)
        self.draw()

    def set_transition_points(self, points: tuple[float, ...], label: str = "") -> None:
        points = tuple(point for point in points if math.isfinite(point) and 0 < point < self.duration)
        if points != self.transition_points or label != self.transition_label:
            self.transition_points = points
            self.transition_label = label
            self.draw()

    def _left(self) -> int:
        return 18

    def _right(self) -> int:
        return max(self._left() + 1, self.winfo_width() - 18)

    def _x_for(self, seconds: float) -> float:
        if self.duration <= 0:
            return float(self._left())
        return self._left() + (self._right() - self._left()) * seconds / self.duration

    def _time_for(self, x: float) -> float:
        if self.duration <= 0:
            return 0.0
        fraction = (x - self._left()) / max(1, self._right() - self._left())
        return max(0.0, min(self.duration, fraction * self.duration))

    def draw(self) -> None:
        self.delete("all")
        left, right, center = self._left(), self._right(), 27
        self.create_line(left, center, right, center, fill="#c8d0cd", width=6, capstyle="round")
        if self.duration <= 0:
            return
        start_x, end_x, position_x = self._x_for(self.start), self._x_for(self.end), self._x_for(self.position)
        self.create_line(start_x, center, end_x, center, fill="#4b9d79", width=6, capstyle="round")
        # Os dois triângulos apontam PARA A BARRA (o de início para baixo, o de
        # fim para cima): a ponta marca exatamente o tempo na régua.
        if self.select_range:
            self.create_polygon(start_x, 19, start_x - 7, 8, start_x + 7, 8, fill="#2e7d5a", outline="")
            self.create_polygon(end_x, 35, end_x - 7, 46, end_x + 7, 46, fill="#c64a42", outline="")
        for seconds in self.transition_points:
            x = self._x_for(seconds)
            self.create_line(x, 17, x, center + 7, fill="#b1842d", width=2, tags="transition_marker")
            self.create_polygon(x, 7, x + 5, 12, x, 17, x - 5, 12,
                                fill="#e5b747", outline="#9b7426", tags="transition_marker")
        self.create_line(position_x, 7, position_x, 47, fill="#243230", width=2)
        self.create_text(left, 48, text="0:00", anchor="w", fill="#667371", font=("Consolas", 8))
        self.create_text(right, 48, text=self._format_time(self.duration), anchor="e", fill="#667371", font=("Consolas", 8))

    def _press(self, event) -> None:
        if self.duration <= 0:
            return
        # Os triângulos são os únicos pontos que movem o recorte. Um clique
        # normal na faixa sempre reposiciona a cabeça de reprodução.
        marker_radius = 9
        if self.select_range and event.y <= 23 and abs(self._x_for(self.start) - event.x) <= marker_radius:
            self.drag_target = "start"
        elif self.select_range and event.y >= 31 and abs(self._x_for(self.end) - event.x) <= marker_radius:
            self.drag_target = "end"
        else:
            self.drag_target = "position"
        self._apply_drag(event.x)

    def _drag(self, event) -> None:
        if self.drag_target:
            self._apply_drag(event.x)

    def _release(self, _event) -> None:
        self.drag_target = None

    def _apply_drag(self, x: float) -> None:
        value = self._time_for(x)
        if self.drag_target == "start":
            self.start = min(value, max(0.0, self.end - 0.01))
            value = self.start
        elif self.drag_target == "end":
            self.end = max(value, min(self.duration, self.start + 0.01))
            value = self.end
        else:
            # A cabeça de reprodução não passa dos marcadores verde e vermelho.
            self.position = min(max(value, self.start), self.end)
            value = self.position
        self.draw()
        self.on_change(self.drag_target or "position", value)

    @staticmethod
    def _format_time(value: float) -> str:
        total = max(0, int(value))
        return f"{total // 60}:{total % 60:02d}"


class InsertAudioTimeline(Canvas):
    """Timeline da inserção, dividida em ondas do áudio principal e inserido."""

    def __init__(self, parent, on_seek, on_insert=None, **kwargs):
        super().__init__(parent, height=96, highlightthickness=0, background="#ffffff", **kwargs)
        self.on_seek = on_seek
        self.on_insert = on_insert
        self.main_name = ""
        self.inserted_name = ""
        self.main_levels: tuple[float, ...] = ()
        self.inserted_levels: tuple[float, ...] = ()
        self.main_duration = 0.0
        self.inserted_duration = 0.0
        self.insertion = 0.0
        self.position = 0.0
        self.dragging = False
        self.drag_target = "position"
        self.bind("<Configure>", lambda _event: self.draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.draw()

    @property
    def duration(self) -> float:
        return max(0.0, self.main_duration + self.inserted_duration)

    def configure_media(self, main_name: str, main_duration: float, inserted_name: str = "", inserted_duration: float = 0.0, insertion: float = 0.0) -> None:
        self.main_name = main_name
        self.inserted_name = inserted_name
        self.main_duration = max(0.0, main_duration)
        self.inserted_duration = max(0.0, inserted_duration)
        self.insertion = max(0.0, min(insertion, self.main_duration))
        self.position = max(0.0, min(self.position, self.duration))
        self.draw()

    def set_position(self, position: float) -> None:
        self.position = max(0.0, min(position, self.duration))
        self.draw()

    def composite_to_main(self, position: float) -> float:
        if self.inserted_duration <= 0:
            return max(0.0, min(position, self.main_duration))
        if position < self.insertion:
            return max(0.0, min(position, self.main_duration))
        if position < self.insertion + self.inserted_duration:
            return self.insertion
        return max(0.0, min(position - self.inserted_duration, self.main_duration))

    def _left(self) -> float:
        return 16.0

    def _right(self) -> float:
        return max(self._left() + 1.0, float(self.winfo_width() - 16))

    def _x_for(self, seconds: float) -> float:
        if self.duration <= 0:
            return self._left()
        return self._left() + (self._right() - self._left()) * seconds / self.duration

    def _time_for(self, x: float) -> float:
        if self.duration <= 0:
            return 0.0
        fraction = (x - self._left()) / max(1.0, self._right() - self._left())
        return max(0.0, min(self.duration, fraction * self.duration))

    def draw(self) -> None:
        self.delete("all")
        left, right = self._left(), self._right()
        top, bottom = 12.0, max(30.0, float(self.winfo_height() - 24))
        self.create_rectangle(left, top, right, bottom, outline="#aebbb7", width=1)
        if self.duration <= 0:
            self.create_text(self.winfo_width() / 2, (top + bottom) / 2, text="Selecione o áudio principal", fill="#667371", font=("Segoe UI", 9))
            return
        first_end = self._x_for(self.insertion)
        inserted_end = self._x_for(self.insertion + self.inserted_duration)
        split = self.insertion / self.main_duration if self.main_duration > 0 else 0.0
        self._draw_wave(left, first_end if self.inserted_duration else right, top + 4, bottom - 4,
                        "#5edaf2", self.main_levels, 0.0, split if self.inserted_duration else 1.0)
        if self.inserted_duration > 0:
            self._draw_wave(first_end, inserted_end, top + 4, bottom - 4, "#ffc24a", self.inserted_levels)
            self._draw_wave(inserted_end, right, top + 4, bottom - 4, "#5edaf2", self.main_levels, split, 1.0)
            self.create_line(first_end, top, first_end, bottom, fill="#596966", width=1)
            self.create_line(inserted_end, top, inserted_end, bottom, fill="#596966", width=1)
            self.create_polygon(
                first_end, bottom + 3, first_end - 6, bottom + 11, first_end + 6, bottom + 11,
                fill="#7a4fb5", outline="",
            )
        marker = self._x_for(self.position)
        self.create_line(marker, top - 3, marker, bottom + 3, fill="#e0a72e", width=2)
        self.create_polygon(marker, top - 3, marker - 5, top - 10, marker + 5, top - 10, fill="#e0a72e", outline="")
        self.create_text(left, bottom + 12, text="0:00.000", anchor="w", fill="#667371", font=("Consolas", 8))
        self.create_text(right, bottom + 12, text=self._format_time(self.duration), anchor="e", fill="#667371", font=("Consolas", 8))
        if self.inserted_duration > 0:
            self.create_text((first_end + inserted_end) / 2, top + 2, text="áudio inserido", anchor="s", fill="#9a741f", font=("Segoe UI", 8))

    def _draw_wave(self, left: float, right: float, top: float, bottom: float, color: str,
                   levels: tuple[float, ...], start: float = 0.0, end: float = 1.0) -> None:
        if right - left < 2:
            return
        center = (top + bottom) / 2
        count = max(2, int((right - left) / 4))
        gap = (right - left) / count
        for index, peak in enumerate(waveform_amplitudes(levels, start, end, count)):
            amplitude = max(1.0, (bottom - top) * 0.43 * math.sqrt(peak))
            x = left + gap * (index + 0.5)
            self.create_line(x, center - amplitude, x, center + amplitude, fill=color, width=2)

    @staticmethod
    def _format_time(value: float) -> str:
        milliseconds = max(0, int(value * 1000))
        total, millis = divmod(milliseconds, 1000)
        return f"{total // 60}:{total % 60:02d}.{millis:03d}"

    def _press(self, event) -> None:
        if self.duration <= 0:
            return
        self.dragging = True
        insertion_x = self._x_for(self.insertion)
        self.drag_target = "insertion" if self.inserted_duration > 0 and abs(event.x - insertion_x) <= 10 else "position"
        self._apply_position(event.x)

    def _drag(self, event) -> None:
        if self.dragging:
            self._apply_position(event.x)

    def _release(self, _event) -> None:
        self.dragging = False
        self.drag_target = "position"

    def _apply_position(self, x: float) -> None:
        value = self._time_for(x)
        if self.drag_target == "insertion":
            self.insertion = max(0.0, min(value, self.main_duration))
            self.position = self.insertion
        else:
            self.position = value
        self.draw()
        if self.drag_target == "insertion" and self.on_insert:
            self.on_insert(self.insertion)
        else:
            self.on_seek(self.position)


class EmbeddedMediaPlayer:
    """Player MCI nativo do Windows, usado para prévias sem nova dependência externa."""

    def __init__(self):
        self.alias = "sig_ffmpeg_preview"
        self.opened = False

    def _send(self, command: str, result: bool = False) -> str:
        if os.name != "nt":
            return ""
        buffer = ctypes.create_unicode_buffer(256) if result else None
        code = ctypes.windll.winmm.mciSendStringW(command, buffer, len(buffer) if buffer else 0, 0)
        if code:
            return ""
        return buffer.value if buffer else "ok"

    def open(self, source: Path, canvas: Canvas) -> bool:
        self.close()
        if os.name != "nt":
            return False
        canvas.update_idletasks()
        filename = str(source.resolve()).replace('"', "'")
        if not self._send(f'open "{filename}" type mpegvideo alias {self.alias}'):
            return False
        self.opened = True
        self._send(f"set {self.alias} time format milliseconds")
        if not self._send(f"window {self.alias} handle {canvas.winfo_id()}"):
            self.close()
            return False
        self.resize(canvas)
        return True

    def resize(self, canvas: Canvas) -> None:
        if self.opened:
            self._send(f"put {self.alias} destination at 0 0 {max(1, canvas.winfo_width())} {max(1, canvas.winfo_height())}")

    def play(self, position_seconds: float) -> bool:
        return bool(self.opened and self._send(f"play {self.alias} from {max(0, int(position_seconds * 1000))}"))

    def pause(self) -> None:
        if self.opened:
            self._send(f"pause {self.alias}")

    def seek(self, position_seconds: float) -> None:
        if self.opened:
            self._send(f"seek {self.alias} to {max(0, int(position_seconds * 1000))}")

    def position(self) -> float:
        value = self._send(f"status {self.alias} position", result=True) if self.opened else ""
        try:
            return int(value) / 1000.0
        except ValueError:
            return 0.0

    def close(self) -> None:
        if self.opened:
            self._send(f"close {self.alias}")
        self.opened = False


class FfmpegTaskTracker:
    """Versão Tk do rastreador de etapas usado pelas ferramentas FFmpeg do Android."""

    def __init__(self, app: "SigApp", tasks: list[str]):
        self.app = app
        self.tasks: dict[str, dict[str, object]] = {task: {"progress": 0, "state": "pending", "detail": ""} for task in tasks}
        self.commands: list[tuple[list[object], bool]] = []
        self.live_status = ""
        self.success_message = ""
        self.error_message = ""
        self._lock = threading.Lock()
        self._scheduled = False
        self._render_later()

    def start(self, label: str, progress: int = 0, detail: str = ""):
        with self._lock:
            item = self.tasks.setdefault(label, {"progress": 0, "state": "pending", "detail": ""})
            if item["state"] != "completed":
                item.update(progress=max(0, min(100, progress)), state="running", detail=detail)
        self._render_later()

    def append(self, labels: list[str]):
        with self._lock:
            for label in labels:
                self.tasks.setdefault(label, {"progress": 0, "state": "pending", "detail": ""})
        self._render_later()

    def fail_task(self, label: str, detail: str):
        with self._lock:
            item = self.tasks.setdefault(label, {"progress": 0, "state": "pending", "detail": ""})
            item.update(state="failed", detail=detail)
        self._render_later()

    def complete(self, label: str):
        with self._lock:
            item = self.tasks.setdefault(label, {"progress": 0, "state": "pending", "detail": ""})
            item.update(progress=100, state="completed", detail="")
        self._render_later()

    def live(self, text: str):
        with self._lock:
            self.live_status = text
        self._render_later()

    def success(self, text: str):
        with self._lock:
            for item in self.tasks.values():
                item.update(progress=100, state="completed", detail="")
            self.live_status = ""
            self.success_message = text
        self._render_later()

    def fail(self, text: str):
        with self._lock:
            self.error_message = text
        self._render_later()

    def command(self, command: list[object], *, probe: bool = False) -> None:
        """Mantem cada comando FFmpeg executado visivel durante os updates.

        Guarda o comando CRU (argumentos reais) para que a numeração
        input/output e o agrupamento de sondas sejam aplicados na renderização,
        quando a sequência completa já é conhecida."""
        with self._lock:
            self.commands.append((list(command), bool(probe)))
        self._render_later()

    def _render_later(self):
        with self._lock:
            if self._scheduled:
                return
            self._scheduled = True
        self.app.root.after(100, self._render)

    def _render(self):
        with self._lock:
            self._scheduled = False
            tasks = [(name, dict(data)) for name, data in self.tasks.items()]
            commands = list(self.commands)
            live, success, error = self.live_status, self.success_message, self.error_message
        box = self.app.activity_log
        if not box.winfo_exists():
            return
        box.configure(state="normal")
        box.delete("1.0", END)
        box.tag_configure("done", foreground="#16833a")
        box.tag_configure("active", foreground="#1d2b2a")
        box.tag_configure("pending", foreground="#667371")
        box.tag_configure("error", foreground="#b3261e")
        box.tag_configure("ffmpeg_command", foreground="#c99a2e")
        box.tag_configure(FFMPEG_COMMAND_BLOCK_TAG, foreground="#c99a2e")
        for name, item in tasks:
            state, progress, detail = item["state"], int(item["progress"]), str(item["detail"])
            if state == "completed":
                line, tag = f"{name} 100%\n", "done"
            elif state == "failed":
                line, tag = f"{name}: FALHOU ({detail})\n", "error"
            elif state == "running":
                suffix = f" ({detail})" if detail else ""
                line, tag = f"{name} - {progress}%{suffix}\n", "active"
            else:
                line, tag = f"{name}\n", "pending"
            box.insert(END, line, tag)
        if commands:
            block_tags = ("ffmpeg_command", FFMPEG_COMMAND_BLOCK_TAG)
            box.insert(END, "\nComandos FFmpeg:\n", block_tags)
            raw_commands = [command for command, _probe in commands]
            probe_flags = [probe for _command, probe in commands]
            rendered_entries = format_ffmpeg_commands_for_log(raw_commands, probe_flags)
            previous_probe = False
            for position, (rendered_command, probe) in enumerate(rendered_entries):
                # Linha em branco apenas para isolar comandos que ALTERAM
                # arquivos; sondas consecutivas ficam em um único bloco.
                if position and not (previous_probe and probe):
                    box.insert(END, "\n", block_tags)
                box.insert(END, f"$ {rendered_command}\n", block_tags)
                previous_probe = probe
        if live:
            box.insert(END, f"{live}\n", "active")
        if error:
            box.insert(END, f"\nErro: {error}\n", "error")
        elif success:
            box.insert(END, f"\nEstatísticas:\n{success}\n", "done")
        box.configure(state="disabled")


class FfmpegToolsPanel:
    """Ferramentas locais do FFmpeg, independentes da fila de transcricao."""

    TRANSITIONS = (
        "Fade in/out",
        "Fundir",
        "Dissolver",
        "Varredura para a esquerda",
        "Varredura para a direita",
        "Deslizar para a esquerda",
        "Deslizar para a direita",
        "Suave para a esquerda",
        "Suave para a direita",
        "Círculo abrindo",
        "Círculo fechando",
    )
    VIDEO_TRANSITION_CODES = {
        "Fade in/out": "fade",
        "Fundir": "fade",
        "Dissolver": "dissolve",
        "Varredura para a esquerda": "wipeleft",
        "Varredura para a direita": "wiperight",
        "Deslizar para a esquerda": "slideleft",
        "Deslizar para a direita": "slideright",
        "Suave para a esquerda": "smoothleft",
        "Suave para a direita": "smoothright",
        "Círculo abrindo": "circleopen",
        "Círculo fechando": "circleclose",
    }
    AUDIO_TRANSITIONS = (
        ("Sem transição", "none"),
        ("Fade in/out", "fade"),
        ("Linear", "tri"),
        ("Seno de quarto de onda", "qsin"),
        ("Seno exponencial", "esin"),
        ("Meia onda senoidal", "hsin"),
        ("Logarítmica", "log"),
        ("Parábola invertida", "ipar"),
        ("Quadrática", "qua"),
        ("Cúbica", "cub"),
        ("Raiz quadrada", "squ"),
        ("Raiz cúbica", "cbr"),
        ("Parábola", "par"),
        ("Exponential (exp)", "exp"),
        ("Inverted quarter sine wave (iqsin)", "iqsin"),
        ("Inverted half sine wave (ihsin)", "ihsin"),
        ("Double-exponential seat (dese)", "dese"),
        ("Double-exponential sigmoid (desi)", "desi"),
        ("Logistic sigmoid (losi)", "losi"),
        ("Sine cardinal function (sinc)", "sinc"),
        ("Inverted sine cardinal function (isinc)", "isinc"),
        ("Quartic (quat)", "quat"),
        ("Quartic root (quatr)", "quatr"),
        ("Squared quarter sine wave (qsin2)", "qsin2"),
        ("Squared half sine wave (hsin2)", "hsin2"),
        ("No fade (nofade)", "nofade"),
    )

    @classmethod
    def insert_transition_labels(cls, smart: bool) -> tuple[str, ...]:
        """Rótulos do Inserir, por MODO — o mesmo par (rótulo, curva) tem efeito
        diferente em cada um.

        Smart Insert: cada curva suaviza apenas o trecho INSERIDO (afade).
        Reencode Completo: as curvas viram CROSSFADE nas emendas (o
        "Fade in/out" continua sendo afade no inserido).

        Medido (T08): "Linear" 0,2 s no Smart = 12,03 s (fade só no inserido)
        contra 11,60 s no integral (crossfade). O rótulo diz o EFEITO, não só a
        curva — era o defeito: o mesmo nome prometia efeitos diferentes.
        """
        rotulos: list[str] = []
        for label, _valor in cls.AUDIO_TRANSITIONS:
            if label in ("Sem transição", "Fade in/out"):
                rotulos.append(label)
            elif smart:
                rotulos.append(f"{label} (fade só no trecho inserido)")
            else:
                rotulos.append(f"Crossfade {label.lower()}")
        return tuple(rotulos)

    @classmethod
    def insert_transition_code(cls, label: str) -> str:
        """Curva a partir do rótulo do combo (aceita os rótulos NOVOS e os
        antigos, para uma preferência já salva continuar valendo)."""
        if not label or label == "Sem transição":
            return "none"
        if label == "Fade in/out":
            return "fade"
        base = label
        if base.startswith("Crossfade "):
            base = base[len("Crossfade "):]
        base = base.replace(" (fade só no trecho inserido)", "").strip()
        for nome, valor in cls.AUDIO_TRANSITIONS:
            if nome.lower() == base.lower():
                return valor
        return "none"

    VORBIS_VALID_BITRATES = {
        1: {
            8000: ("32k",),
            16000: ("32k", "48k", "64k", "96k"),
            22050: ("32k", "48k", "64k"),
            44100: ("32k", "48k", "64k", "96k", "128k", "192k"),
            48000: ("32k", "48k", "64k", "96k", "128k", "192k"),
        },
        2: {
            8000: ("32k", "48k", "64k"),
            16000: ("32k", "48k", "64k", "96k", "128k", "192k"),
            22050: ("32k", "48k", "64k", "96k", "128k"),
            44100: ("48k", "64k", "96k", "128k", "192k", "256k"),
            48000: ("48k", "64k", "96k", "128k", "192k", "256k"),
        },
    }

    def __init__(self, parent, app: "SigApp"):
        import tkinter as tk

        self.app = app
        self.root = app.root
        self.parent = parent
        self.tk = tk
        self.running = False
        self.task_tracker: FfmpegTaskTracker | None = None
        self.task_started_at = 0.0
        self.cancel_event = threading.Event()
        self.current_process: subprocess.Popen | None = None
        self.process_lock = threading.Lock()
        self.acceleration: VideoAcceleration | None = None
        self.selected_acceleration_label = ""
        self.selected_video_quality = "Alta"
        self.worker_tool_uses_video_encoder = False
        self.worker_options: dict[str, object] = {}
        self.available_accelerations: list[VideoAcceleration] = []
        self.acceleration_by_label: dict[str, VideoAcceleration] = {}
        self.acceleration_var = StringVar(value=PATH_LABELS[ENCODER_PATH_GPU])
        self.encoder_advanced_var = StringVar(value=self.ENCODER_ADVANCED_AUTO_LABEL)
        self.encoder_effective_var = StringVar(value="Encoder de vídeo: detectando opções...")
        self.available_encoder_options: list[EncoderOption] = []
        self.worker_acceleration: VideoAcceleration | None = None
        self.encoder_help: dict[str, str] = {}
        self.video_quality_var = StringVar(value="Alta")
        self.video_speed_var = StringVar(value="Equilibrada")
        self.output_dir = app_base_dir() / "temp" / "ffmpeg"
        self.output_dir_var = StringVar(value=str(self.output_dir))
        self.output_dir_chosen = False
        self.status_var = StringVar(value="")
        self.progress_var = IntVar(value=0)
        self.max_progress_seen = 0
        self.active_tool_var = StringVar(value="Cortar")

        self.cut_input: Path | None = None
        self.cut_media_profile: MediaProfile | None = None
        self.cut_input_var = StringVar(value="Nenhum arquivo selecionado")
        self.cut_start_var = StringVar(value="0")
        self.cut_end_var = StringVar(value="")
        self.cut_current_var = StringVar(value="0:00")
        self.cut_mode_var = StringVar(value=CUT_MODE_SMART)
        self.cut_audio_policy_var = StringVar(value="Precisão máxima (AAC)")
        self.cut_stream_policy_var = StringVar(value="Vídeo e áudio")

        self.extract_inputs: list[Path] = []
        self.extract_summary_var = StringVar(value="Nenhum arquivo selecionado")
        self.extract_extension_var = StringVar(value="wav")
        self.extract_rate_var = StringVar(value="16000")
        self.extract_channels_var = StringVar(value="1")
        self.extract_bitrate_var = StringVar(value="64k")
        self.extract_start_var = StringVar(value="")
        self.extract_end_var = StringVar(value="")
        self.extract_current_var = StringVar(value="0:00")
        self.extract_transcription_preset_var = BooleanVar(value=False)
        self.extract_compact_preset_var = BooleanVar(value=False)
        self.extract_preset_sync = False

        self.rotate_input: Path | None = None
        self.rotate_media_profile: MediaProfile | None = None
        self.rotate_input_var = StringVar(value="Nenhum vídeo selecionado")
        self.rotate_degrees_var = StringVar(value="90")
        self.rotate_hflip_var = BooleanVar(value=False)
        self.rotate_vflip_var = BooleanVar(value=False)
        self.rotate_metadata_var = BooleanVar(value=False)
        self.rotate_parallel_var = BooleanVar(value=False)
        self.rotate_segments_var = StringVar(value="")
        self.rotate_current_var = StringVar(value="0:00")
        self.rotate_start_var = StringVar(value="0")
        self.rotate_end_var = StringVar(value="")

        self.join_inputs: list[Path] = []
        self.join_media_profiles: dict[Path, MediaProfile] = {}
        self.join_reencode_var = BooleanVar(value=False)
        self.join_smart_var = BooleanVar(value=False)
        self.join_transition_var = StringVar(value="Fade in/out")
        self.join_seconds_var = StringVar(value="0.5")
        self.join_profile_var = StringVar(value="Automático (preservar mais vídeo)")
        self.join_advanced_var = BooleanVar(master=self.root, value=False)
        self.join_stream_policy_var = StringVar(value="Primeira faixa (MP4)")
        self.join_audio_policy_var = StringVar(value="Preservar áudio e preencher silêncio")
        self.join_orientation_mode_var = StringVar(value="bake")  # bake | preserve
        self.join_orientation_reference_var = StringVar(value="")
        self._join_rotation_answer: dict | None = None
        self.join_seconds_var.trace_add("write", lambda *_: self._on_join_seconds_changed())
        self.join_transition_var.trace_add("write", lambda *_: self._update_join_transition_markers())

        self.insert_main_input: Path | None = None
        self.insert_secondary_input: Path | None = None
        self.insert_main_var = StringVar(value="Selecione o áudio principal")
        self.insert_secondary_var = StringVar(value="Nenhum áudio para inserir")
        self.insert_current_var = StringVar(value="0:00.000")
        self.insert_time_var = StringVar(value="0:00.000")
        self.insert_reencode_var = BooleanVar(value=False)
        self.insert_smart_var = BooleanVar(value=False)
        self.insert_transition_var = StringVar(value="Sem transição")
        self.insert_seconds_var = StringVar(value="0.5")
        self.insert_preview_context: dict | None = None
        self.insert_preview_phase_end = 0.0
        self.insert_preview_composite_start = 0.0

        self.clean_input: Path | None = None
        self.clean_input_var = StringVar(value="Nenhum áudio selecionado")
        self.clean_mode_var = StringVar(value="equilibrado")
        self.clean_current_var = StringVar(value="0:00")
        self.join_current_var = StringVar(value="0:00")
        self.join_preview_name_var = StringVar(value="")
        self.tool_preview_contexts: dict[str, dict] = {}
        self.preview_waveforms: dict[Canvas, dict] = {}
        self.waveform_requests: dict[object, tuple] = {}
        self.waveform_cache: dict[tuple, tuple[float, ...]] = {}
        self.waveform_pending: set[tuple] = set()
        self.waveform_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="sig-waveform")
        self.waveform_queue: queue.Queue = queue.Queue()
        self.waveform_stop_event = threading.Event()
        self.waveform_processes: set[subprocess.Popen] = set()
        self.waveform_lock = threading.Lock()
        self.preview_player = EmbeddedMediaPlayer()
        self.preview_context: dict | None = None
        self.preview_playing = False
        self.preview_speed = 1.0
        self.preview_speed_var = StringVar(value="1.0x")
        self.preview_after_id = None
        self.preview_image_refs: dict[Canvas, object] = {}
        self.preview_viewports: dict[Canvas, PreviewViewport] = {}
        self.preview_holders: dict[Canvas, object] = {}
        self.preview_parents: dict[Canvas, object] = {}
        self.preview_stills: dict[Canvas, object] = {}
        self.preview_frames: dict[Canvas, object] = {}
        self.preview_frame_items: dict[Canvas, int] = {}
        self.preview_hint_text: dict[Canvas, str] = {}
        self.preview_still_after_id = None
        self.preview_still_pending: dict | None = None
        self.preview_still_running = False
        self.preview_still_cache: dict[tuple, object] = {}
        self.preview_still_key: dict[Canvas, tuple] = {}
        self.preview_still_queue: queue.Queue = queue.Queue(maxsize=4)
        self.preview_selections: dict[Canvas, PreviewSelection] = {}
        self.preview_selection_drag: dict[Canvas, dict] = {}
        self.preview_selection_filters: dict[Canvas, str] = {}
        self.preview_restart_id = None
        self.audio_preview_process: subprocess.Popen | None = None
        self.external_preview_process: subprocess.Popen | None = None
        self.external_preview_started_at = 0.0
        self.external_preview_offset = 0.0
        self.frame_preview_process: subprocess.Popen | None = None
        self.frame_preview_thread: threading.Thread | None = None
        self.frame_preview_stop_event = threading.Event()
        self.preview_frame_queue: queue.Queue = queue.Queue(maxsize=3)
        self.preview_generation = 0

        self._build(parent)
        self.recovery_job = None
        self.root.after(600, self._offer_ffmpeg_recovery)
        self.root.after(33, self._poll_preview_frames)
        threading.Thread(target=self._load_available_accelerations, daemon=True).start()

    @staticmethod
    def _filetypes():
        return [
            ("Mídias", "*.wav *.mp3 *.m4a *.ogg *.opus *.flac *.aac *.wma *.mp4 *.mov *.mkv *.avi *.webm"),
            ("Todos os arquivos", "*.*"),
        ]

    def _build(self, parent) -> None:
        outer = ttk.Frame(parent)
        outer.pack(fill=BOTH, expand=True)
        style = ttk.Style(self.root)
        style.configure("Ffmpeg.Sidebar.TButton", font=("Segoe UI", 9), padding=(6, -1))
        frame = ttk.Frame(outer)
        frame.pack(fill=BOTH, expand=True)
        frame.pack_propagate(False)
        frame.bind("<Configure>", lambda _event: self._fit_visible_preview_stages())

        tool_tabs = self.tk.Frame(frame, background="#f4f7f6")
        tool_tabs.pack(fill=X, pady=(0, 6))
        tool_tab_bar = self.tk.Frame(frame, background="#f4f7f6")
        tool_tab_bar.pack(fill=X, pady=(0, 8))
        encoder_message = ttk.Frame(frame)
        encoder_message.pack(fill=X)

        # Pack right-to-left so the encoder label is visually before its selector.
        self.acceleration_combo = ttk.Combobox(
            tool_tab_bar,
            textvariable=self.acceleration_var,
            values=(PATH_LABELS[ENCODER_PATH_GPU], PATH_LABELS[ENCODER_PATH_CPU]),
            state="disabled",
            width=6,
        )
        self.acceleration_combo.pack(side=RIGHT, padx=(0, 4), pady=(2, 0))
        self.acceleration_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_encoder_path_changed())
        self.encoder_advanced_combo = ttk.Combobox(
            tool_tab_bar,
            textvariable=self.encoder_advanced_var,
            state="readonly",
            width=12,
        )
        self.encoder_advanced_label = ttk.Label(tool_tab_bar, text="Avançado:", style="Muted.TLabel")
        self.encoder_help_button = ttk.Button(tool_tab_bar, text="?", width=3, command=self._show_encoder_help)
        self.encoder_effective_label = ttk.Label(encoder_message, textvariable=self.encoder_effective_var, style="Muted.TLabel", wraplength=730)
        self.acceleration_label = ttk.Label(tool_tab_bar, text="Encoder de vídeo:", style="Muted.TLabel")
        self.acceleration_label.pack(side=RIGHT, padx=(12, 4), pady=(4, 0))
        self.quality_help_button = ttk.Button(tool_tab_bar, text="?", width=3, command=self._show_video_quality_help)
        self.quality_help_button.pack(side=RIGHT, padx=(4, 0), pady=(2, 0))
        self.quality_menu_button = ttk.Menubutton(tool_tab_bar, textvariable=self.video_quality_var, width=9)
        self.quality_menu = self.tk.Menu(self.quality_menu_button, tearoff=False)
        for quality in VIDEO_QUALITY_LEVELS:
            self.quality_menu.add_radiobutton(
                label=VIDEO_QUALITY_MENU_LABELS[quality],
                value=quality,
                variable=self.video_quality_var,
            )
        self.quality_menu_button.configure(menu=self.quality_menu)
        self.quality_menu_button.pack(side=RIGHT, pady=(2, 0))
        self.quality_label = ttk.Label(tool_tab_bar, text="Qualidade:", style="Muted.TLabel")
        self.quality_label.pack(side=RIGHT, padx=(12, 4), pady=(4, 0))
        self.speed_help_button = ttk.Button(tool_tab_bar, text="?", width=3, command=self._show_video_speed_help)
        self.speed_help_button.pack(side=RIGHT, padx=(4, 0), pady=(2, 0))
        self.speed_menu_button = ttk.Menubutton(tool_tab_bar, textvariable=self.video_speed_var, width=13)
        self.speed_menu = self.tk.Menu(self.speed_menu_button, tearoff=False)
        for speed in VIDEO_SPEED_LEVELS:
            self.speed_menu.add_radiobutton(
                label=VIDEO_SPEED_MENU_LABELS[speed],
                value=speed,
                variable=self.video_speed_var,
            )
        self.speed_menu_button.configure(menu=self.speed_menu)
        self.speed_menu_button.pack(side=RIGHT, pady=(2, 0))
        self.speed_label = ttk.Label(tool_tab_bar, text="Velocidade:", style="Muted.TLabel")
        self.speed_label.pack(side=RIGHT, padx=(12, 4), pady=(4, 0))

        self.ffmpeg_tab_buttons = {}
        ffmpeg_tab_width = len("Inserir") + 1
        tab_specs = (
            ("Cortar", "Cortar"),
            ("Extrair áudio", "Extrair"),
            ("Girar vídeo", "Girar"),
            ("Juntar áudios/vídeos", "Juntar"),
            ("Inserir áudio", "Inserir"),
            ("Limpar áudio", "Limpar"),
        )
        for name, display_name in tab_specs:
            button = self.tk.Label(
                tool_tabs,
                text=display_name,
                width=ffmpeg_tab_width,
                height=1,
                borderwidth=1,
                relief="solid",
                font=("Segoe UI Semibold", 10),
                cursor="hand2",
            )
            button.pack(side=LEFT, padx=(0 if name == "Cortar" else 4, 0))
            button.bind("<Button-1>", lambda _event, selected=name: self._select_ffmpeg_tool(selected))
            self.ffmpeg_tab_buttons[name] = button

        self.tool_content = ttk.Frame(frame)
        self.tool_content.pack(fill=BOTH, expand=True)
        self.cut_tab = ttk.Frame(self.tool_content, padding=12)
        self.extract_tab = ttk.Frame(self.tool_content, padding=12)
        self.rotate_tab = ttk.Frame(self.tool_content, padding=12)
        self.join_tab = ttk.Frame(self.tool_content, padding=12)
        self.insert_tab = ttk.Frame(self.tool_content, padding=12)
        self.clean_tab = ttk.Frame(self.tool_content, padding=12)
        self.ffmpeg_tool_frames = {
            "Cortar": self.cut_tab,
            "Extrair áudio": self.extract_tab,
            "Girar vídeo": self.rotate_tab,
            "Juntar áudios/vídeos": self.join_tab,
            "Inserir áudio": self.insert_tab,
            "Limpar áudio": self.clean_tab,
        }

        self._build_cut_tab()
        self._build_extract_tab()
        self._build_rotate_tab()
        self._build_join_tab()
        self._build_insert_tab()
        self._build_clean_tab()
        self._select_ffmpeg_tool("Cortar")

        bottom = ttk.Frame(frame)
        bottom.pack(side=BOTTOM, fill=X, pady=(8, 0), before=self.tool_content)
        self.progress = ttk.Progressbar(bottom, maximum=100, variable=self.progress_var)
        self.progress.pack(fill=X)
        ttk.Label(bottom, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(5, 0))

        actions = ttk.Frame(frame)
        actions.pack(side=BOTTOM, fill=X, pady=(8, 0), before=bottom)
        self.run_button = ttk.Button(actions, text="Executar", style="Execute.TButton", command=self.run_current_tool)
        self.run_button.pack(side=LEFT)
        self.cancel_button = ttk.Button(actions, text="Cancelar", command=self.cancel, state="disabled")
        self.cancel_button.pack(side=LEFT, padx=(8, 0))


    def _tool_columns(self, tab):
        """Coluna fixa de opções e área de prévia que recebe o espaço restante."""
        body = ttk.Frame(tab)
        body.pack(fill=BOTH, expand=True)
        body.grid_propagate(False)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(2, weight=1)
        sidebar = ttk.Frame(body, width=FFMPEG_SIDEBAR_WIDTH, padding=(0, 0, 12, 0))
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.pack_propagate(False)
        ttk.Separator(body, orient="vertical").grid(row=0, column=1, sticky="ns", padx=(0, 16))
        workspace = ttk.Frame(body)
        workspace.grid(row=0, column=2, sticky="nsew")
        workspace.pack_propagate(False)
        output = ttk.Frame(sidebar)
        output.pack(side=BOTTOM, fill=X, pady=(10, 0))
        ttk.Separator(output).pack(fill=X, pady=(0, 8))
        return sidebar, workspace, output

    @staticmethod
    def _option_row(parent, label: str):
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=(0, 8))
        ttk.Label(row, text=label, style="Muted.TLabel").pack(anchor="w", pady=(0, 3))
        return row

    def _file_row(self, parent, variable: StringVar, command, label: str = "Selecionar arquivo") -> None:
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=(0, 14))
        ttk.Button(row, text=label, command=command, style="Ffmpeg.Sidebar.TButton").pack(fill=X)
        name = ttk.Label(row, textvariable=variable, style="Muted.TLabel", width=1, anchor="w")
        name.pack(fill=X, pady=(6, 0))
        create_tooltip(name, variable.get)

    def _output_buttons(self, row) -> None:
        button = ttk.Button(row, text="Abrir Pasta", command=self.open_or_choose_output_dir,
                            style="Ffmpeg.Sidebar.TButton")
        button.pack(fill=X)
        create_tooltip(button, lambda: (
            "Abrir a pasta escolhida. Botão direito para trocar."
            if self.output_dir_chosen else "Escolher a pasta de saída."
        ))
        menu = self.tk.Menu(button, tearoff=False)
        menu.add_command(label="Alterar pasta…", command=self.choose_output_dir)
        def show_menu(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        button.bind("<Button-3>", show_menu)

    def _output_path_row(self, parent) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=(2, 0))
        ttk.Label(row, text="Pasta de saída:", style="Muted.TLabel").pack(anchor="w")
        path = ttk.Label(row, textvariable=self.output_dir_var, style="Muted.TLabel", width=1, anchor="w")
        path.pack(fill=X, pady=(2, 0))
        create_tooltip(path, self.output_dir_var.get)

    def _create_preview_stage(self, parent, message: str) -> Canvas:
        """Palco do player: o canvas abraça a proporção da mídia e preenche a aba.

        O palco é um widget empacotado com altura própria (recalculada em
        _fit_preview_stage), então ele nunca fica por cima dos controles. A roda
        do mouse dá zoom e o arrasto com o botão esquerdo move o quadro ampliado.
        """
        holder = ttk.Frame(parent)
        holder.pack(anchor="center", pady=(0, 6))
        holder.pack_propagate(False)
        canvas = Canvas(holder, highlightthickness=0, background=PREVIEW_STAGE_BACKGROUND, cursor="crosshair")
        canvas.pack(fill=BOTH, expand=True)
        view = PreviewViewport()
        self.preview_viewports[canvas] = view
        self.preview_holders[canvas] = holder
        self.preview_parents[canvas] = parent
        canvas.bind("<Configure>", lambda _event, target=canvas: self._fit_preview_stage(target))
        # A aba também avisa: enquanto ela não é mapeada o Tk não sabe a largura
        # real (o palco nasceria no tamanho mínimo e ficaria parado ali).
        parent.bind("<Configure>", lambda _event, target=canvas: self._fit_preview_stage(target), add="+")
        canvas.bind("<MouseWheel>", lambda event, target=canvas: self._preview_wheel(target, event))
        canvas.bind("<Button-4>", lambda event, target=canvas: self._preview_wheel(target, event))
        canvas.bind("<Button-5>", lambda event, target=canvas: self._preview_wheel(target, event))
        canvas.bind("<ButtonPress-1>", lambda event, target=canvas: self._preview_press(target, event))
        canvas.bind("<B1-Motion>", lambda event, target=canvas: self._preview_motion(target, event))
        canvas.bind("<ButtonRelease-1>", lambda event, target=canvas: self._preview_release(target, event))
        canvas.bind("<Motion>", lambda event, target=canvas: self._preview_hover(target, event))
        # Botão DIREITO desenha/ajusta a seleção; clique simples sobre a seleção
        # abre o menu "Desfazer seleção" (o esquerdo ficou para arrastar o vídeo).
        canvas.bind("<ButtonPress-3>", lambda event, target=canvas: self._preview_select_press(target, event))
        canvas.bind("<B3-Motion>", lambda event, target=canvas: self._preview_select_motion(target, event))
        canvas.bind("<ButtonRelease-3>", lambda event, target=canvas: self._preview_select_release(target, event))
        # Botão do meio também move o vídeo ampliado.
        canvas.bind("<ButtonPress-2>", lambda event, target=canvas: self._preview_pan_start(target, event))
        canvas.bind("<B2-Motion>", lambda event, target=canvas: self._preview_pan_move(target, event))
        canvas.bind("<ButtonRelease-2>", lambda _event, target=canvas: self._preview_pan_end(target))
        self._preview_show_hint(canvas, message)
        self.root.after_idle(lambda: self._fit_preview_stage(canvas))
        return canvas

    def _preview_show_hint(self, canvas: Canvas, message: str, width: int | None = None, height: int | None = None) -> None:
        """Mensagem centralizada no palco (nenhuma mídia carregada ainda).

        `width`/`height` permitem centrar já no tamanho que o palco VAI ter: logo
        após um `holder.configure` o `winfo_width()` do canvas ainda é o antigo.
        """
        self.preview_hint_text[canvas] = message
        self.preview_waveforms.pop(canvas, None)
        self.waveform_requests.pop(canvas, None)
        canvas.delete("all")
        self.preview_frame_items.pop(canvas, None)
        self.preview_frames.pop(canvas, None)
        self.preview_stills.pop(canvas, None)
        self._clear_preview_selection(canvas)
        stage_width = max(1, int(width or canvas.winfo_width()))
        stage_height = max(1, int(height or canvas.winfo_height()))
        canvas.create_text(
            stage_width // 2,
            stage_height // 2,
            text=message,
            fill="#667371",
            font=("Segoe UI", 10),
            justify="center",
            width=max(160, stage_width - 24),
        )

    def _refresh_preview_hint(self, canvas: Canvas) -> None:
        """Redesenha a dica CENTRALIZADA no tamanho atual do palco.

        Sem isso a dica criada no tamanho inicial (mínimo) ficava parada nas
        coordenadas antigas quando o palco crescia — sobrava um pedaço do texto
        (ex.: "lizar") no meio da tela, como se fosse um texto solto.
        """
        message = self.preview_hint_text.get(canvas)
        if canvas in self.preview_waveforms or not message:
            return
        if self.preview_frames.get(canvas) is not None or self.preview_stills.get(canvas) is not None:
            return
        view = self.preview_viewports.get(canvas)
        if view is not None and view.stage_width > 0 and view.stage_height > 0:
            self._preview_show_hint(canvas, message, view.stage_width, view.stage_height)
        else:
            self._preview_show_hint(canvas, message)

    def _preview_available_box(self, parent, holder) -> tuple[int, int]:
        """Usa a altura real da coluna e reserva as linhas dos controles."""
        available_width = parent.winfo_width()
        reserved = 0
        for widget in parent.winfo_children():
            if widget is holder or not widget.winfo_manager():
                continue
            reserved += max(0, int(widget.winfo_reqheight()))
            if widget.winfo_manager() == "pack":
                reserved += vertical_padding_total(widget.pack_info().get("pady", 0))
        reserved += frame_vertical_padding(parent.cget("padding"))
        available_height = parent.winfo_height() - reserved - 8
        return max(PREVIEW_STAGE_MIN_WIDTH, available_width), max(
            PREVIEW_STAGE_MIN_HEIGHT, min(PREVIEW_STAGE_MAX_HEIGHT, available_height)
        )

    def _fit_preview_stage(self, canvas: Canvas) -> None:
        """Recalcula o tamanho do palco para ocupar todo o espaço disponível."""
        view = self.preview_viewports.get(canvas)
        holder = self.preview_holders.get(canvas)
        parent = self.preview_parents.get(canvas)
        if view is None or holder is None or parent is None:
            return
        available_width, available_height = self._preview_available_box(parent, holder)
        if canvas in self.preview_waveforms:
            width, height = available_width, available_height
        else:
            width, height = preview_stage_size(
                available_width, available_height, view.media_width, view.media_height
            )
        # Em retrato, a altura disponível vence o mínimo de largura do vídeo.
        scale = min(1.0, available_width / width, available_height / height)
        width, height = max(4, round(width * scale)), max(4, round(height * scale))
        changed = (width, height) != (view.stage_width, view.stage_height)
        if changed:
            view.stage_width, view.stage_height = width, height
            holder.configure(width=width, height=height)
            self.preview_player.resize(canvas)
        if changed or not self.preview_frame_items.get(canvas):
            self._paint_preview_view(canvas)
        if changed:
            self._refresh_preview_hint(canvas)
            self._schedule_preview_restart(canvas)

    def _preview_drawn_size(self, view: PreviewViewport) -> tuple[int, int]:
        width, height, _zoom = preview_drawn_size(view.stage_width, view.stage_height, view.zoom)
        return width, height

    def _preview_scaled_image(self, image, width: int, height: int):
        if (image.width, image.height) == (width, height):
            return image
        shrinking = width * height < image.width * image.height
        return image.resize((width, height), Image.LANCZOS if shrinking else Image.BILINEAR)

    def _paint_preview_view(self, canvas: Canvas) -> None:
        """Desenha o quadro atual (vivo ou congelado) na geometria de zoom/deslocamento."""
        view = self.preview_viewports.get(canvas)
        if view is None or view.stage_width <= 0 or view.stage_height <= 0:
            return
        if canvas in getattr(self, "preview_waveforms", {}):
            self._draw_audio_waveform(canvas)
            return
        source = self.preview_frames.get(canvas) or self.preview_stills.get(canvas)
        if source is None:
            return
        drawn_width, drawn_height = self._preview_drawn_size(view)
        image = self._preview_scaled_image(source, drawn_width, drawn_height)
        photo = ImageTk.PhotoImage(image, master=self.root)
        self.preview_image_refs[canvas] = photo
        canvas.delete("all")
        x, y = preview_view_rect(
            view.stage_width,
            view.stage_height,
            drawn_width,
            drawn_height,
            view.offset_x,
            view.offset_y,
        )
        self.preview_frame_items[canvas] = canvas.create_image(x, y, image=photo, anchor="nw")
        # A seleção é redesenhada por último: ela fica sempre sobre os pixels
        # escolhidos, com o zoom/deslocamento atuais.
        self._draw_preview_selection(canvas)

    def _preview_move_item(self, canvas: Canvas) -> None:
        """Arrasta o quadro sem redesenhar (o canvas recorta o que passa das bordas)."""
        view = self.preview_viewports.get(canvas)
        item = self.preview_frame_items.get(canvas)
        if view is None or item is None:
            return
        drawn_width, drawn_height = self._preview_drawn_size(view)
        x, y = preview_view_rect(
            view.stage_width,
            view.stage_height,
            drawn_width,
            drawn_height,
            view.offset_x,
            view.offset_y,
        )
        canvas.coords(item, x, y)
        # A seleção acompanha o arrasto do quadro (mesmos pixels, outra posição).
        self._redraw_preview_selection(canvas)

    def _preview_can_pan(self, view: PreviewViewport) -> bool:
        drawn_width, drawn_height = self._preview_drawn_size(view)
        return drawn_width > view.stage_width or drawn_height > view.stage_height

    @staticmethod
    def _preview_wheel_steps(event) -> float:
        """Passos da roda do mouse; campos ausentes chegam do Tk como '??'."""

        def numero(valor) -> float:
            try:
                return float(valor)
            except (TypeError, ValueError):
                return 0.0

        button = numero(getattr(event, "num", 0))
        if button in (4.0, 5.0):
            return 1.0 if button == 4.0 else -1.0
        delta = numero(getattr(event, "delta", 0))
        return delta / 120.0 if delta else 0.0

    def _preview_wheel(self, canvas: Canvas, event) -> str:
        """Roda para cima aproxima, para baixo afasta (nunca rola o painel)."""
        steps = self._preview_wheel_steps(event)
        view = self.preview_viewports.get(canvas)
        if view is None or not steps or not self.preview_stills.get(canvas) and not self.preview_frames.get(canvas):
            return "break"
        self._preview_zoom_at(canvas, event.x, event.y, PREVIEW_ZOOM_STEP ** steps)
        return "break"

    def _preview_zoom_at(self, canvas: Canvas, cursor_x: float, cursor_y: float, factor: float) -> None:
        """Aproxima/afasta mantendo sob o cursor o mesmo ponto do quadro."""
        view = self.preview_viewports.get(canvas)
        if view is None or view.stage_width <= 0:
            return
        drawn_width, drawn_height = self._preview_drawn_size(view)
        zoomed = preview_zoom_clamped(view.zoom * factor)
        zoomed_width, zoomed_height, effective = preview_drawn_size(
            view.stage_width, view.stage_height, zoomed
        )
        if (zoomed_width, zoomed_height) == (drawn_width, drawn_height):
            return
        offset_x, offset_y = preview_zoom_offsets(
            view.stage_width,
            view.stage_height,
            drawn_width,
            drawn_height,
            view.offset_x,
            view.offset_y,
            zoomed_width,
            zoomed_height,
            cursor_x,
            cursor_y,
        )
        view.zoom = effective
        view.offset_x = preview_clamped_offset(view.stage_width, zoomed_width, offset_x)
        view.offset_y = preview_clamped_offset(view.stage_height, zoomed_height, offset_y)
        self._paint_preview_view(canvas)
        self._schedule_preview_restart(canvas)

    def _preview_pan_start(self, canvas: Canvas, event) -> str:
        view = self.preview_viewports.get(canvas)
        if view is None:
            return "break"
        view.drag_origin = (int(event.x), int(event.y))
        view.drag_offsets = (view.offset_x, view.offset_y)
        if self._preview_can_pan(view):
            canvas.configure(cursor="fleur")
        return "break"

    def _preview_pan_move(self, canvas: Canvas, event) -> str:
        view = self.preview_viewports.get(canvas)
        if view is None or view.drag_origin is None or not self._preview_can_pan(view):
            return "break"
        drawn_width, drawn_height = self._preview_drawn_size(view)
        origin_x, origin_y = view.drag_origin
        view.offset_x = preview_clamped_offset(
            view.stage_width, drawn_width, view.drag_offsets[0] + (event.x - origin_x)
        )
        view.offset_y = preview_clamped_offset(
            view.stage_height, drawn_height, view.drag_offsets[1] + (event.y - origin_y)
        )
        self._preview_move_item(canvas)
        return "break"

    def _preview_pan_end(self, canvas: Canvas) -> str:
        view = self.preview_viewports.get(canvas)
        if view is not None:
            view.drag_origin = None
        canvas.configure(cursor="crosshair")
        return "break"

    def _preview_frame_transform(self, canvas: Canvas) -> tuple[float, float, int, int]:
        """(origem_x, origem_y, largura, altura) do quadro desenhado no palco."""
        view = self.preview_viewports.get(canvas)
        if view is None:
            return 0.0, 0.0, 1, 1
        drawn_width, drawn_height = self._preview_drawn_size(view)
        origin_x, origin_y = preview_view_rect(
            view.stage_width, view.stage_height, drawn_width, drawn_height, view.offset_x, view.offset_y
        )
        return float(origin_x), float(origin_y), max(1, drawn_width), max(1, drawn_height)

    def _preview_fraction_at(self, canvas: Canvas, x: float, y: float) -> tuple[float, float]:
        origin_x, origin_y, drawn_w, drawn_h = self._preview_frame_transform(canvas)
        return preview_fraction_from_view(x, y, drawn_w, drawn_h, origin_x, origin_y)

    def _preview_minimum_fractions(self, canvas: Canvas) -> tuple[float, float]:
        _ox, _oy, drawn_w, drawn_h = self._preview_frame_transform(canvas)
        return PREVIEW_SELECTION_MIN_SIZE / drawn_w, PREVIEW_SELECTION_MIN_SIZE / drawn_h

    def _preview_selection_view_rect(self, canvas: Canvas) -> tuple[float, float, float, float] | None:
        selection = self.preview_selections.get(canvas)
        if selection is None:
            return None
        origin_x, origin_y, drawn_w, drawn_h = self._preview_frame_transform(canvas)
        return selection.to_view(drawn_w, drawn_h, origin_x, origin_y)

    def _draw_preview_selection(self, canvas: Canvas) -> None:
        """Traço fino amarelo + alças, sempre exatamente sobre os pixels escolhidos."""
        rect = self._preview_selection_view_rect(canvas)
        if rect is None:
            return
        left, top, right, bottom = rect
        canvas.create_rectangle(
            left, top, right, bottom,
            outline=PREVIEW_SELECTION_OUTLINE, width=PREVIEW_SELECTION_WIDTH,
            tags=PREVIEW_SELECTION_TAG,
        )
        size = PREVIEW_SELECTION_HANDLE_SIZE
        for centro_x in (left, (left + right) / 2, right):
            for centro_y in (top, (top + bottom) / 2, bottom):
                canvas.create_rectangle(
                    centro_x - size / 2, centro_y - size / 2,
                    centro_x + size / 2, centro_y + size / 2,
                    outline=PREVIEW_SELECTION_HANDLE_FILL, fill=PREVIEW_SELECTION_HANDLE_FILL,
                    width=0, tags=PREVIEW_SELECTION_TAG,
                )

    def _redraw_preview_selection(self, canvas: Canvas) -> None:
        canvas.delete(PREVIEW_SELECTION_TAG)
        self._draw_preview_selection(canvas)

    def _clear_preview_selection(self, canvas: Canvas) -> None:
        self.preview_selections.pop(canvas, None)
        self.preview_selection_drag.pop(canvas, None)
        self.preview_selection_filters.pop(canvas, None)
        canvas.delete(PREVIEW_SELECTION_TAG)

    def _preview_selection_filters_for(self, canvas: Canvas) -> str:
        """Filtros de giro/espelho em vigor no palco (o corte não tem nenhum)."""
        if canvas is getattr(self, "rotate_preview", None):
            return self._rotate_preview_filter()
        return ""

    def _preview_remember_selection_filters(self, canvas: Canvas) -> None:
        self.preview_selection_filters[canvas] = self._preview_selection_filters_for(canvas)

    def _preview_selection_crop(self, canvas: Canvas, video_width: int, video_height: int) -> tuple[int, int, int, int] | None:
        selection = self.preview_selections.get(canvas)
        if selection is None:
            return None
        return selection_crop_pixels(selection, video_width, video_height)

    def _preview_press(self, canvas: Canvas, event) -> str:
        """Botão esquerdo: percorre o áudio ou arrasta o vídeo ampliado."""
        if canvas in self.preview_waveforms:
            return self._seek_waveform(canvas, event.x)
        return self._preview_pan_start(canvas, event)

    def _preview_motion(self, canvas: Canvas, event) -> str:
        """Arrasto com o botão esquerdo: seek de áudio ou pan de vídeo."""
        if canvas in self.preview_waveforms:
            return self._seek_waveform(canvas, event.x)
        return self._preview_pan_move(canvas, event)

    def _preview_release(self, canvas: Canvas, event) -> str:
        return self._preview_pan_end(canvas)

    def _preview_select_press(self, canvas: Canvas, event) -> str:
        """Botão DIREITO: desenha a seleção (ou pega uma alça / move a seleção).

        Um clique SEM arrastar sobre a seleção abre o menu "Desfazer seleção" —
        é o que decide entre desenhar e abrir o menu.
        """
        if canvas in self.preview_waveforms:
            return "break"
        view = self.preview_viewports.get(canvas)
        if view is None:
            return "break"
        rect = self._preview_selection_view_rect(canvas)
        handle = selection_handle_at(rect, event.x, event.y) if rect is not None else None
        if handle == "move":
            self.preview_selection_drag[canvas] = {
                "mode": "move",
                "selection": self.preview_selections[canvas],
                "start": self._preview_fraction_at(canvas, event.x, event.y),
                "press": (int(event.x), int(event.y)),
            }
            return "break"
        if handle:
            self.preview_selection_drag[canvas] = {
                "mode": "resize",
                "handle": handle,
                "selection": self.preview_selections[canvas],
                "press": (int(event.x), int(event.y)),
            }
            return "break"
        # Sem alça: guarda o ponto e só começa a desenhar quando o mouse andar
        # (clique parado no vazio não cria seleção nenhuma).
        self.preview_selection_drag[canvas] = {
            "mode": "pending",
            "start": self._preview_fraction_at(canvas, event.x, event.y),
            "press": (int(event.x), int(event.y)),
            "previous": self.preview_selections.get(canvas),
        }
        return "break"

    def _preview_select_motion(self, canvas: Canvas, event) -> str:
        drag = self.preview_selection_drag.get(canvas)
        if drag is None:
            return "break"
        mode = drag["mode"]
        if mode == "pending":
            inicio_x, inicio_y = drag["press"]
            if abs(event.x - inicio_x) < PREVIEW_SELECTION_DRAG_THRESHOLD and abs(event.y - inicio_y) < PREVIEW_SELECTION_DRAG_THRESHOLD:
                return "break"
            # O arrasto começou: vira um desenho (a seleção anterior sai do lugar).
            drag["mode"] = "draw"
            self.preview_selections.pop(canvas, None)
            mode = "draw"
        if mode == "draw":
            selecao = selection_from_drag(
                drag["start"], self._preview_fraction_at(canvas, event.x, event.y), 0.0, 0.0
            )
            self.preview_selections[canvas] = selecao
        elif mode == "resize":
            minimo_x, minimo_y = self._preview_minimum_fractions(canvas)
            fracao_x, fracao_y = self._preview_fraction_at(canvas, event.x, event.y)
            self.preview_selections[canvas] = selection_resized(
                drag["selection"], drag["handle"], fracao_x, fracao_y, minimo_x, minimo_y
            )
        elif mode == "move":
            agora = self._preview_fraction_at(canvas, event.x, event.y)
            self.preview_selections[canvas] = selection_moved(
                drag["selection"], agora[0] - drag["start"][0], agora[1] - drag["start"][1]
            )
        self._redraw_preview_selection(canvas)
        return "break"

    def _preview_select_release(self, canvas: Canvas, event) -> str:
        drag = self.preview_selection_drag.pop(canvas, None)
        if drag is None:
            return "break"
        mode = drag["mode"]
        if mode == "pending":
            # Clique parado sobre a seleção: abre o menu de desfazer.
            return self._preview_open_selection_menu(canvas, event, drag.get("press"))
        if mode == "move":
            inicio_x, inicio_y = drag["press"]
            if abs(event.x - inicio_x) < PREVIEW_SELECTION_DRAG_THRESHOLD and abs(event.y - inicio_y) < PREVIEW_SELECTION_DRAG_THRESHOLD:
                return self._preview_open_selection_menu(canvas, event, drag.get("press"))
            self._redraw_preview_selection(canvas)
            return "break"
        if mode == "draw":
            minimo_x, minimo_y = self._preview_minimum_fractions(canvas)
            selecao = selection_from_drag(
                drag["start"], self._preview_fraction_at(canvas, event.x, event.y), minimo_x, minimo_y
            )
            self.preview_selections[canvas] = selecao or drag.get("previous")
        if self.preview_selections.get(canvas) is not None:
            self._preview_remember_selection_filters(canvas)
        self._redraw_preview_selection(canvas)
        return "break"

    def _preview_open_selection_menu(self, canvas: Canvas, event, press) -> str:
        """Menu do botão direito na seleção (só para clique parado)."""
        rect = self._preview_selection_view_rect(canvas)
        if rect is None:
            return "break"
        ponto_x, ponto_y = press if press else (event.x, event.y)
        left, top, right, bottom = rect
        if not (left <= ponto_x <= right and top <= ponto_y <= bottom):
            return "break"
        menu = self.tk.Menu(canvas, tearoff=False)
        menu.add_command(
            label="Desfazer seleção",
            command=lambda: self._clear_preview_selection(canvas),
        )
        try:
            menu.tk_popup(getattr(event, "x_root", 0), getattr(event, "y_root", 0))
        finally:
            menu.grab_release()
        return "break"

    def _preview_hover(self, canvas: Canvas, event) -> str:
        """Feedback do cursor: alças para redimensionar, mãozinha para mover."""
        if canvas in self.preview_waveforms:
            canvas.configure(cursor="hand2")
            return "break"
        rect = self._preview_selection_view_rect(canvas)
        if rect is None:
            canvas.configure(cursor="crosshair")
            return "break"
        handle = selection_handle_at(rect, event.x, event.y)
        canvas.configure(cursor=PREVIEW_SELECTION_CURSORS.get(handle or "", "crosshair"))
        return "break"

    def _reset_preview_view(self, canvas: Canvas, media_width: int, media_height: int) -> None:
        """Nova mídia no palco: volta ao enquadramento que preenche o espaço."""
        view = self.preview_viewports.get(canvas)
        if view is None:
            return
        view.zoom = 1.0
        view.offset_x = 0.0
        view.offset_y = 0.0
        view.media_width = max(0, int(media_width))
        view.media_height = max(0, int(media_height))
        view.drag_origin = None
        self._clear_preview_selection(canvas)
        self.preview_still_cache.clear()
        self.preview_still_key.pop(canvas, None)
        self._fit_preview_stage(canvas)

    def _preview_view_is_fitted(self, canvas: Canvas) -> bool:
        """Sem zoom/deslocamento: o player nativo (MCI) ainda pode ser usado."""
        view = self.preview_viewports.get(canvas)
        if view is None:
            return True
        return (
            abs(view.zoom - 1.0) < 1e-6
            and abs(view.offset_x) < 0.5
            and abs(view.offset_y) < 0.5
        )

    def _preview_pipeline_size(self, canvas: Canvas) -> tuple[int, int]:
        """Resolução dos quadros do FFmpeg: o tamanho desenhado, dentro do orçamento."""
        view = self.preview_viewports.get(canvas)
        if view is None or view.stage_width <= 0 or view.stage_height <= 0:
            return max(320, canvas.winfo_width()), max(180, canvas.winfo_height())
        drawn_width, drawn_height = self._preview_drawn_size(view)
        return preview_render_size(drawn_width, drawn_height, view.media_width, view.media_height)

    def _preview_live_position(self, context: dict) -> float:
        timeline = context["timeline"]
        if self.external_preview_started_at <= 0:
            return max(timeline.start, timeline.position)
        elapsed = (time.monotonic() - self.external_preview_started_at) * self.preview_speed
        return min(timeline.end, max(timeline.start, self.external_preview_offset + elapsed))

    def _schedule_preview_restart(self, canvas: Canvas) -> None:
        """O pipeline de quadros é recriado na resolução do novo zoom (com atraso)."""
        context = self.preview_context
        if (
            not context
            or context.get("canvas") is not canvas
            or not self.preview_playing
            or context.get("audio_only")
        ):
            return
        if self.preview_restart_id:
            try:
                self.root.after_cancel(self.preview_restart_id)
            except Exception:
                pass
            self.preview_restart_id = None
        self.preview_restart_id = self.root.after(
            PREVIEW_ZOOM_RESTART_MS, lambda: self._restart_canvas_preview(canvas)
        )

    def _restart_canvas_preview(self, canvas: Canvas) -> None:
        """Reinicia a prévia viva mantendo a posição (zoom/deslocamento mudaram)."""
        self.preview_restart_id = None
        context = self.preview_context
        if (
            not context
            or context.get("canvas") is not canvas
            or not self.preview_playing
            or context.get("audio_only")
        ):
            return
        position = self._preview_live_position(context)
        timeline = context["timeline"]
        if position >= timeline.end - 0.02:
            position = timeline.start
        self.preview_player.close()
        self.frame_preview_stop_event.set()
        self._terminate_preview_process(self.external_preview_process)
        self.external_preview_process = None
        self._terminate_preview_process(getattr(self, "audio_preview_process", None))
        self.audio_preview_process = None
        self._terminate_preview_process(self.frame_preview_process)
        self.frame_preview_process = None
        self.preview_playing = False
        self._start_canvas_preview(context, position)

    def _add_preview_speed_controls(self, parent):
        """Monta o conjunto de controles comum aos players de áudio e vídeo."""
        controls = self.tk.Frame(parent, background="#f4f7f6")
        controls.pack(fill=X, pady=(0, 3))
        icon_row = self.tk.Frame(controls, background="#f4f7f6")
        icon_row.pack(anchor="center")

        slower = PreviewIconButton(
            icon_row,
            "slower",
            lambda: self._change_preview_speed(-1),
            width=58,
            height=48,
        )
        slower.pack(side=LEFT, padx=(0, 18))
        play = PreviewIconButton(
            icon_row,
            "play",
            self._toggle_preview,
            width=76,
            height=60,
        )
        play.pack(side=LEFT)
        faster = PreviewIconButton(
            icon_row,
            "faster",
            lambda: self._change_preview_speed(1),
            width=58,
            height=48,
        )
        faster.pack(side=LEFT, padx=(18, 0))
        create_tooltip(slower, "Diminuir velocidade")
        create_tooltip(play, "Reproduzir ou pausar")
        create_tooltip(faster, "Aumentar velocidade")

        ttk.Label(controls, textvariable=self.preview_speed_var, style="Muted.TLabel").pack(anchor="center", pady=(0, 2))
        return play

    @staticmethod
    def _add_preview_time_label(parent, current_var: StringVar) -> None:
        ttk.Label(parent, textvariable=current_var, style="Muted.TLabel").pack(anchor="center", pady=(0, 8))

    def _change_preview_speed(self, direction: int) -> None:
        values = PREVIEW_SPEED_VALUES
        index = min(range(len(values)), key=lambda item: abs(values[item] - self.preview_speed))
        self.preview_speed = values[max(0, min(len(values) - 1, index + direction))]
        self.preview_speed_var.set(f"{self.preview_speed:g}x")
        if self.preview_playing:
            self._toggle_preview()
            self._toggle_preview()

    def _build_cut_tab(self) -> None:
        sidebar, workspace, output = self._tool_columns(self.cut_tab)
        self._file_row(sidebar, self.cut_input_var, self.select_cut_input)
        self.cut_preview = self._create_preview_stage(workspace, "")
        self.cut_play_button = self._add_preview_speed_controls(workspace)
        self.cut_timeline = RangeTimeline(workspace, self._cut_timeline_changed)
        self.cut_timeline.pack(fill=X, pady=(0, 4))
        self._add_preview_time_label(workspace, self.cut_current_var)
        values = ttk.Frame(workspace)
        values.pack(anchor="center", pady=(2, 0))
        ttk.Label(values, text="Início (s):").grid(row=0, column=0, sticky="w")
        cut_start_entry = ttk.Entry(values, textvariable=self.cut_start_var, width=10)
        cut_start_entry.grid(row=0, column=1, padx=(6, 14))
        ttk.Label(values, text="Fim (s):").grid(row=0, column=2, sticky="w")
        cut_end_entry = ttk.Entry(values, textvariable=self.cut_end_var, width=10)
        cut_end_entry.grid(row=0, column=3, padx=(6, 0))
        cut_start_entry.bind("<FocusOut>", lambda _event: self._sync_cut_range_from_entries())
        cut_end_entry.bind("<FocusOut>", lambda _event: self._sync_cut_range_from_entries())
        mode = self._option_row(sidebar, "Modo de corte")
        mode_controls = ttk.Frame(mode)
        mode_controls.pack(fill=X)
        self.cut_mode_combo = ttk.Combobox(mode_controls, textvariable=self.cut_mode_var,
                                          values=CUT_MODES, state="readonly", width=18)
        self.cut_mode_combo.pack(side=LEFT, fill=X, expand=True)
        self.cut_mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_cut_controls())
        self.cut_mode_help_button = ttk.Button(mode_controls, text="?", width=3, command=self._show_cut_mode_help)
        self.cut_mode_help_button.pack(side=LEFT, padx=(4, 0))
        audio = self._option_row(sidebar, "Áudio do vídeo")
        self.cut_audio_policy_combo = ttk.Combobox(
            audio, textvariable=self.cut_audio_policy_var,
            values=("Precisão máxima (AAC)", "Copiar áudio (limites por pacote)"),
            state="readonly", width=20,
        )
        self.cut_audio_policy_combo.pack(fill=X)
        create_tooltip(self.cut_audio_policy_combo, self.cut_audio_policy_var.get)
        streams = self._option_row(sidebar, "Streams")
        self.cut_stream_policy_combo = ttk.Combobox(
            streams, textvariable=self.cut_stream_policy_var,
            values=("Vídeo e áudio", "Todos os streams (somente modo rápido)"),
            state="readonly", width=20,
        )
        self.cut_stream_policy_combo.pack(fill=X)
        create_tooltip(self.cut_stream_policy_combo, self.cut_stream_policy_var.get)
        self.cut_audio_hint_var = StringVar(master=self.root, value="")
        ttk.Label(sidebar, textvariable=self.cut_audio_hint_var, style="Muted.TLabel",
                  wraplength=FFMPEG_SIDEBAR_WIDTH - 16).pack(fill=X, pady=(4, 0))
        self._output_buttons(output)
        self._output_path_row(output)
        self._update_cut_controls()

    def _build_extract_tab(self) -> None:
        sidebar, workspace, output = self._tool_columns(self.extract_tab)
        self._file_row(sidebar, self.extract_summary_var, self.select_extract_inputs, "Selecionar arquivos")
        self.extract_preview = self._create_preview_stage(workspace, "")
        self.extract_play_button = self._add_preview_speed_controls(workspace)
        self.extract_timeline = RangeTimeline(workspace, self._extract_timeline_changed)
        self.extract_timeline.pack(fill=X, pady=(0, 4))
        self._add_preview_time_label(workspace, self.extract_current_var)
        trim = ttk.Frame(workspace)
        trim.pack(anchor="center", pady=(2, 0))
        ttk.Label(trim, text="Início (s):").grid(row=0, column=0, sticky="w")
        extract_start_entry = ttk.Entry(trim, textvariable=self.extract_start_var, width=10)
        extract_start_entry.grid(row=0, column=1, padx=(6, 14))
        ttk.Label(trim, text="Fim (s):").grid(row=0, column=2, sticky="w")
        extract_end_entry = ttk.Entry(trim, textvariable=self.extract_end_var, width=10)
        extract_end_entry.grid(row=0, column=3, padx=(6, 0))
        extract_start_entry.bind("<FocusOut>", lambda _event: self._sync_extract_range_from_entries())
        extract_end_entry.bind("<FocusOut>", lambda _event: self._sync_extract_range_from_entries())
        presets = ttk.Frame(sidebar)
        presets.pack(fill=X, pady=(0, 12))
        ttk.Checkbutton(
            presets, text="Padrão para transcrição", variable=self.extract_transcription_preset_var,
            command=lambda: self._set_extract_preset("transcription"),
        ).pack(anchor="w", pady=(0, 4))
        ttk.Checkbutton(
            presets, text="Padrão compacto", variable=self.extract_compact_preset_var,
            command=lambda: self._set_extract_preset("compact"),
        ).pack(anchor="w")
        fields = (
            ("Formato", self.extract_extension_var, ("wav", "m4a", "mp3", "aac", "ogg", "opus", "flac")),
            ("Taxa de amostragem (Hz)", self.extract_rate_var, ("8000", "16000", "22050", "44100", "48000")),
            ("Canais", self.extract_channels_var, ("1", "2")),
            ("Bitrate", self.extract_bitrate_var, ("32k", "48k", "64k", "96k", "128k", "192k", "256k")),
        )
        self.extract_custom_widgets = []
        for label, variable, choices in fields:
            row = self._option_row(sidebar, label)
            combo = ttk.Combobox(row, textvariable=variable, values=choices, state="readonly", width=20)
            combo.pack(fill=X)
            self.extract_custom_widgets.append(combo)
        self.extract_extension_combo, self.extract_rate_combo, self.extract_channels_combo, self.extract_bitrate_combo = self.extract_custom_widgets
        self.extract_extension_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_extract_format_changed())
        self.extract_rate_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_extract_bitrate_choices())
        self.extract_channels_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_extract_bitrate_choices())
        self._on_extract_format_changed()
        self._output_buttons(output)
        self._output_path_row(output)

    def _build_rotate_tab(self) -> None:
        sidebar, workspace, output = self._tool_columns(self.rotate_tab)
        self._file_row(sidebar, self.rotate_input_var, self.select_rotate_input, "Selecionar vídeo")
        self.rotate_preview = self._create_preview_stage(workspace, "")
        self.rotate_play_button = self._add_preview_speed_controls(workspace)
        self.rotate_timeline = RangeTimeline(workspace, self._rotate_timeline_changed)
        self.rotate_timeline.pack(fill=X, pady=(0, 4))
        self._add_preview_time_label(workspace, self.rotate_current_var)
        trim = ttk.Frame(workspace)
        trim.pack(anchor="center", pady=(2, 0))
        ttk.Label(trim, text="Início (s):").grid(row=0, column=0, sticky="w")
        rotate_start_entry = ttk.Entry(trim, textvariable=self.rotate_start_var, width=10)
        rotate_start_entry.grid(row=0, column=1, padx=(6, 14))
        ttk.Label(trim, text="Fim (s):").grid(row=0, column=2, sticky="w")
        rotate_end_entry = ttk.Entry(trim, textvariable=self.rotate_end_var, width=10)
        rotate_end_entry.grid(row=0, column=3, padx=(6, 0))
        rotate_start_entry.bind("<FocusOut>", lambda _event: self._sync_rotate_range_from_entries())
        rotate_end_entry.bind("<FocusOut>", lambda _event: self._sync_rotate_range_from_entries())
        row = self._option_row(sidebar, "Giro (graus)")
        rotate_combo = ttk.Combobox(row, textvariable=self.rotate_degrees_var,
                                    values=("-90", "0", "90", "180"), state="readonly", width=20)
        rotate_combo.pack(fill=X)
        rotate_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_rotate_transform_changed())
        self.rotate_hflip_check = ttk.Checkbutton(sidebar, text="Espelhar horizontal", variable=self.rotate_hflip_var, command=self._on_rotate_transform_changed)
        self.rotate_hflip_check.pack(anchor="w", pady=(0, 6))
        self.rotate_vflip_check = ttk.Checkbutton(sidebar, text="Espelhar vertical", variable=self.rotate_vflip_var, command=self._on_rotate_transform_changed)
        self.rotate_vflip_check.pack(anchor="w", pady=(0, 12))
        self.rotate_metadata_check = ttk.Checkbutton(
            sidebar, text="Somente metadados de rotação", variable=self.rotate_metadata_var,
            command=self._update_rotate_control_state,
        )
        self.rotate_metadata_check.pack(anchor="w", pady=(0, 6))
        create_tooltip(self.rotate_metadata_check, "Rápido, sem reencodar. Aplica apenas a orientação do vídeo.")
        self.rotate_parallel_check = ttk.Checkbutton(
            sidebar, text="Processar trechos em paralelo", variable=self.rotate_parallel_var,
            command=self._update_rotate_control_state,
        )
        self.rotate_parallel_check.pack(anchor="w")
        self.rotate_parallel_frame = ttk.Frame(sidebar)
        ttk.Label(self.rotate_parallel_frame, text="Trechos:", style="Muted.TLabel").pack(side=LEFT)
        self.rotate_segments_entry = ttk.Entry(self.rotate_parallel_frame, textvariable=self.rotate_segments_var, width=8)
        self.rotate_segments_entry.pack(side=LEFT, padx=(6, 4))
        ttk.Button(
            self.rotate_parallel_frame, text="?", width=3,
            command=lambda: messagebox.showinfo(
                "Trechos em paralelo",
                "O valor define quantos trechos serão criados e quantos poderão ser processados simultaneamente. "
                "Mais trechos podem acelerar vídeos longos, mas valores altos consomem RAM, aquecem o PC e podem saturar o encoder de hardware. "
                "Em vídeos curtos, o overhead pode piorar o tempo. Deixe vazio para usar todos os núcleos lógicos em CPU; "
                "com encoder de hardware (NVENC/QSV/AMF), o padrão é limitado a 3 processos simultâneos por segurança das sessões do driver.",
            ),
        ).pack(side=LEFT)
        self.rotate_device_limit_var = StringVar(value="")
        self.rotate_device_limit_label = ttk.Label(sidebar, textvariable=self.rotate_device_limit_var,
                                                   foreground="#b3261e", wraplength=FFMPEG_SIDEBAR_WIDTH - 16)
        self._output_buttons(output)
        self._output_path_row(output)
        self._update_rotate_control_state()

    def _build_join_tab(self) -> None:
        sidebar, workspace, output = self._tool_columns(self.join_tab)
        ttk.Button(sidebar, text="Adicionar áudios/vídeos", command=self.add_join_inputs,
                   style="Ffmpeg.Sidebar.TButton").pack(fill=X, pady=(0, 2))
        self.join_sidebar = sidebar
        self.join_list_frame = list_frame = ttk.Frame(sidebar)
        list_frame.pack(fill=X, pady=(0, 2))
        sidebar.bind("<Configure>", lambda _event: self._fit_join_list())
        self.join_list = self.tk.Listbox(
            list_frame, height=3, activestyle="none", font=("Segoe UI", 9), exportselection=False,
            background="#ffffff", foreground="#243230", selectbackground="#dceee6",
            selectforeground="#193d32", relief="flat", highlightthickness=1, highlightbackground="#d7e1dc",
        )
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.join_list.yview)
        self.join_list.configure(yscrollcommand=scroll.set)
        self.join_list.pack(side=LEFT, fill=X, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        self.join_list.bind("<<ListboxSelect>>", lambda _event: self._select_join_preview())
        create_tooltip(self.join_list, self.join_preview_name_var.get)
        self.join_preview = self._create_preview_stage(workspace, "")
        self.join_play_button = self._add_preview_speed_controls(workspace)
        self.join_timeline = RangeTimeline(workspace, self._join_timeline_changed, select_range=False)
        self.join_timeline.pack(fill=X, pady=(0, 2))
        create_tooltip(self.join_timeline, "Losangos dourados indicam as transições entre os clipes.")
        self._add_preview_time_label(workspace, self.join_current_var)
        clip_actions = ttk.Frame(sidebar)
        clip_actions.pack(fill=X, pady=(0, 5))
        for column, (label, command) in enumerate((
            ("Remover", self.remove_join_input),
            ("Subir", lambda: self.move_join_input(-1)),
            ("Descer", lambda: self.move_join_input(1)),
        )):
            clip_actions.columnconfigure(column, weight=1, uniform="clip_actions")
            ttk.Button(clip_actions, text=label, command=command, width=1,
                       style="Ffmpeg.Sidebar.TButton").grid(row=0, column=column, sticky="ew",
                                                          padx=(0, 4) if column < 2 else 0)
        self.join_reencode_check = ttk.Checkbutton(
            sidebar, text="Reencode Completo", variable=self.join_reencode_var, command=self._on_toggle_join_reencode,
        )
        self.join_reencode_check.pack(anchor="w", pady=(0, 2))
        self.join_smart_check = ttk.Checkbutton(
            sidebar, text="SmartJoin (Experimental)", variable=self.join_smart_var, command=self._on_toggle_join_smart,
        )
        self.join_smart_check.pack(anchor="w", pady=(0, 2))
        create_tooltip(
            self.join_smart_check,
            "Copia os corpos compatíveis e recodifica as emendas e os clipes incompatíveis com o perfil escolhido. "
            "Qualidade e velocidade afetam apenas as partes recodificadas. Fade in/out mantém a duração; "
            "as demais transições sobrepõem o tempo escolhido. Se não houver um plano seguro com ganho de cópia, "
            "a tarefa será interrompida, sem trocar automaticamente para Reencode Completo.",
        )
        options = ttk.Frame(sidebar)
        options.pack(fill=X, pady=(0, 2))
        ttk.Label(options, text="Transição:", style="Muted.TLabel", width=9).pack(side=LEFT)
        self.join_transition_combo = ttk.Combobox(options, textvariable=self.join_transition_var,
                                                 values=self.TRANSITIONS, state="readonly", width=20)
        self.join_transition_combo.pack(side=LEFT, fill=X, expand=True)
        seconds = ttk.Frame(sidebar)
        seconds.pack(fill=X, pady=(0, 4))
        ttk.Label(seconds, text="Tempo (s):", style="Muted.TLabel").pack(side=LEFT)
        self.join_seconds_entry = ttk.Entry(seconds, textvariable=self.join_seconds_var, width=8)
        self.join_seconds_entry.pack(side=RIGHT)
        self.join_advanced_check = ttk.Checkbutton(
            sidebar, text="Avançado", variable=self.join_advanced_var, command=self._update_join_controls,
        )
        self.join_advanced_check.pack(anchor="w")
        self.join_policies_frame = ttk.Frame(sidebar)
        self.join_policies_frame.pack(fill=X)
        self.join_profile_row = ttk.Frame(self.join_policies_frame)
        ttk.Label(self.join_profile_row, text="Perfil:", style="Muted.TLabel", width=7).pack(side=LEFT)
        self.join_profile_combo = ttk.Combobox(
            self.join_profile_row, textvariable=self.join_profile_var,
            values=("Automático (preservar mais vídeo)", "Primeiro clipe", "Maior resolução", "Menor resolução (sem upscale)"),
            state="readonly", width=20,
        )
        self.join_profile_combo.pack(side=LEFT, fill=X, expand=True)
        self.join_stream_row = ttk.Frame(self.join_policies_frame)
        ttk.Label(self.join_stream_row, text="Faixas:", style="Muted.TLabel", width=7).pack(side=LEFT)
        self.join_stream_policy_combo = ttk.Combobox(
            self.join_stream_row, textvariable=self.join_stream_policy_var,
            values=("Primeira faixa (MP4)", "Todas as faixas (MKV, sem transição)"), state="readonly", width=20,
        )
        self.join_stream_policy_combo.pack(side=LEFT, fill=X, expand=True)
        self.join_stream_policy_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_join_controls())
        self.join_audio_row = ttk.Frame(self.join_policies_frame)
        ttk.Label(self.join_audio_row, text="Áudio:", style="Muted.TLabel", width=7).pack(side=LEFT)
        self.join_audio_policy_combo = ttk.Combobox(
            self.join_audio_row, textvariable=self.join_audio_policy_var,
            values=("Preservar áudio e preencher silêncio", "Gerar saída sem áudio"), state="readonly", width=20,
        )
        self.join_audio_policy_combo.pack(side=LEFT, fill=X, expand=True)
        self.join_audio_policy_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_join_controls())
        for combo, variable in (
            (self.join_profile_combo, self.join_profile_var),
            (self.join_stream_policy_combo, self.join_stream_policy_var),
            (self.join_audio_policy_combo, self.join_audio_policy_var),
        ):
            create_tooltip(combo, variable.get)
        self._output_buttons(output)
        self._output_path_row(output)
        self._update_join_controls()

    def _build_insert_tab(self) -> None:
        sidebar, workspace, output = self._tool_columns(self.insert_tab)
        self.insert_main_button = ttk.Button(sidebar, text="+ Áudio principal", command=self.select_insert_main_input)
        self.insert_main_button.pack(fill=X)
        main_name = ttk.Label(sidebar, textvariable=self.insert_main_var, style="Muted.TLabel", width=1)
        main_name.pack(fill=X, pady=(6, 12))
        create_tooltip(main_name, self.insert_main_var.get)
        self.insert_secondary_button = ttk.Button(
            sidebar, text="+ Inserir áudio", command=self.select_insert_secondary_input, state="disabled",
        )
        self.insert_secondary_button.pack(fill=X)
        self.insert_secondary_label = ttk.Label(sidebar, textvariable=self.insert_secondary_var, style="Muted.TLabel", width=1)
        self.insert_secondary_label.pack(fill=X, pady=(6, 16))
        create_tooltip(self.insert_secondary_label, self.insert_secondary_var.get)
        self.insert_timeline = InsertAudioTimeline(
            workspace, self._insert_timeline_changed, self._insert_position_changed,
        )
        self.insert_timeline.pack(fill=BOTH, expand=True, pady=(0, 8))
        self.insert_play_button = self._add_preview_speed_controls(workspace)
        self._add_preview_time_label(workspace, self.insert_current_var)
        time_row = self._option_row(sidebar, "Ponto de inserção no principal")
        self.insert_time_entry = ttk.Entry(time_row, textvariable=self.insert_time_var, width=14)
        self.insert_time_entry.pack(fill=X)
        self.insert_time_entry.bind("<FocusOut>", lambda _event: self._apply_insert_time())
        self.insert_time_entry.bind("<Return>", lambda _event: self._apply_insert_time())
        self.insert_options_frame = ttk.Frame(sidebar)
        checks = ttk.Frame(self.insert_options_frame)
        checks.pack(fill=X, pady=(2, 12))
        self.insert_reencode_check = ttk.Checkbutton(
            checks, text="Reencode Completo", variable=self.insert_reencode_var, command=self._on_toggle_insert_reencode,
        )
        self.insert_reencode_check.pack(anchor="w", pady=(0, 4))
        self.insert_smart_check = ttk.Checkbutton(
            checks, text="Smart Insert", variable=self.insert_smart_var, command=self._on_toggle_insert_smart,
        )
        self.insert_smart_check.pack(anchor="w")
        transition_row = self._option_row(self.insert_options_frame, "Transição")
        self.insert_transition_combo = ttk.Combobox(
            transition_row, textvariable=self.insert_transition_var,
            values=self.insert_transition_labels(True), state="disabled", width=20,
        )
        self.insert_transition_combo.pack(fill=X)
        self.insert_transition_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_insert_controls())
        create_tooltip(self.insert_transition_combo, self.insert_transition_var.get)
        seconds = ttk.Frame(self.insert_options_frame)
        seconds.pack(fill=X, pady=(0, 8))
        ttk.Label(seconds, text="Tempo (s):", style="Muted.TLabel").pack(side=LEFT)
        self.insert_seconds_entry = ttk.Entry(seconds, textvariable=self.insert_seconds_var, width=8, state="disabled")
        self.insert_seconds_entry.pack(side=RIGHT)
        self.insert_processing_hint_var = StringVar(master=self.root, value="")
        ttk.Label(
            self.insert_options_frame, textvariable=self.insert_processing_hint_var,
            style="Muted.TLabel", wraplength=FFMPEG_SIDEBAR_WIDTH - 16,
        ).pack(fill=X, pady=(4, 0))
        create_tooltip(
            self.insert_reencode_check,
            "Sem reencodar, o ponto pode variar até o frame/pacote disponível e transições não são aplicadas. "
            "Quando uma transição está ativa, a prévia usa o mesmo filtro da saída.",
        )
        self._output_buttons(output)
        self._output_path_row(output)

    def _build_clean_tab(self) -> None:
        sidebar, workspace, output = self._tool_columns(self.clean_tab)
        self._file_row(sidebar, self.clean_input_var, self.select_clean_input)
        self.clean_preview = self._create_preview_stage(workspace, "")
        self.clean_play_button = self._add_preview_speed_controls(workspace)
        self.clean_timeline = RangeTimeline(workspace, self._clean_timeline_changed, select_range=False)
        self.clean_timeline.pack(fill=X, pady=(0, 4))
        self._add_preview_time_label(workspace, self.clean_current_var)
        row = self._option_row(sidebar, "Filtro de limpeza")
        ttk.Combobox(row, textvariable=self.clean_mode_var, values=("equilibrado", "forte"),
                     state="readonly", width=20).pack(fill=X)
        # A limpeza preserva a taxa e os canais da fonte.
        ttk.Label(
            sidebar, text="Saída: WAV PCM\nTaxa e canais preservados da fonte.",
            style="Muted.TLabel", wraplength=FFMPEG_SIDEBAR_WIDTH - 16, justify="left",
        ).pack(fill=X, pady=(6, 0))
        self._output_buttons(output)
        self._output_path_row(output)

    PREVIEW_TOOL_KEYS = {
        "Cortar": "cut", "Extrair áudio": "extract", "Girar vídeo": "rotate",
        "Juntar áudios/vídeos": "join", "Inserir áudio": "insert_audio", "Limpar áudio": "clean",
    }

    def _select_ffmpeg_tool(self, selected: str) -> None:
        if selected != self.active_tool_var.get():
            self._stop_preview()
        self.preview_context = self.tool_preview_contexts.get(self.PREVIEW_TOOL_KEYS[selected])
        active_bg = "#ffffff"
        inactive_bg = "#d6d2c7"
        active_fg = "#10201f"
        inactive_fg = "#111111"
        for name, frame in self.ffmpeg_tool_frames.items():
            frame.pack_forget()
            button = self.ffmpeg_tab_buttons[name]
            button.configure(
                background=active_bg if name == selected else inactive_bg,
                foreground=active_fg if name == selected else inactive_fg,
            )
        self.ffmpeg_tool_frames[selected].pack(fill=BOTH, expand=True)
        self.active_tool_var.set(selected)
        self._refresh_encoder_control_state()
        self._fit_visible_preview_stages()
        self._refresh_effective_encoder_label()

    def _fit_visible_preview_stages(self) -> None:
        """Reencaixa os palcos da aba visível (largura/altura só existem mapeadas)."""
        active = self.ffmpeg_tool_frames.get(self.active_tool_var.get())
        if active is None:
            return
        for canvas, parent in list(self.preview_parents.items()):
            if parent.winfo_toplevel() is active.winfo_toplevel() and str(parent).startswith(str(active) + "."):
                self.root.after_idle(lambda target=canvas: self._fit_preview_stage(target))

    @staticmethod
    def _rotation_uses_video_encoder(metadata_only: bool, degrees: int, hflip: bool, vflip: bool) -> bool:
        # Sem filtro visual (grau 0 e sem espelhamento) o worker usa -c copy: encoder não tem efeito.
        return (not metadata_only) and (degrees % 360 != 0 or hflip or vflip)

    def _cut_mode_is_copy(self) -> bool:
        """Modo Sem Reencode (cópia dos streams)."""
        return str(self.cut_mode_var.get()).startswith(CUT_MODE_COPY)

    def _show_cut_mode_help(self) -> None:
        messagebox.showinfo("Modos de corte", CUT_MODE_HELP)

    def _update_cut_controls(self) -> None:
        fast = self._cut_mode_is_copy()
        profile = getattr(self, "cut_media_profile", None)
        has_video = bool(profile and profile.has_video)
        hint = getattr(self, "cut_audio_hint_var", None)
        if hint is not None:
            hint.set(
                "Áudio puro: SmartCut usa o mesmo corte preciso do Reencode Completo. "
                "Recodificar áudio costuma ser muito mais leve que recodificar vídeo."
                if profile and not has_video and str(self.cut_mode_var.get()) == CUT_MODE_SMART else ""
            )
        running = getattr(self, "running", False)
        self.cut_audio_policy_combo.configure(state="readonly" if (has_video and not fast and not running) else "disabled")
        self.cut_stream_policy_combo.configure(state="readonly" if (has_video and fast and not running) else "disabled")
        if not fast:
            self.cut_stream_policy_var.set("Vídeo e áudio")
        self._refresh_encoder_control_state()
        self._refresh_effective_encoder_label()

    def _current_tool_uses_video_encoder(self) -> bool:
        tool = self.active_tool_var.get()
        if tool == "Cortar":
            if self._cut_mode_is_copy():
                return False
            if self.cut_input is None:
                return False
            cut_profile = getattr(self, "cut_media_profile", None)
            if cut_profile is not None:
                return cut_profile.has_video
            return self.cut_input.suffix.lower() in VIDEO_EXTENSIONS
        if tool == "Girar vídeo":
            try:
                degrees = int(self.rotate_degrees_var.get() or 0)
            except (ValueError, TypeError):
                degrees = 0
            return self._rotation_uses_video_encoder(
                self.rotate_metadata_var.get(), degrees,
                self.rotate_hflip_var.get(), self.rotate_vflip_var.get(),
            )
        if tool == "Juntar áudios/vídeos":
            profiles = getattr(self, "join_media_profiles", {})
            is_audio_only = bool(getattr(self, "join_inputs", [])) and all(
                (profiles[path].has_audio and not profiles[path].has_video)
                if path in profiles else path.suffix.lower() in AUDIO_EXTENSIONS
                for path in self.join_inputs
            )
            if self.join_reencode_var.get():
                has_reencode = True
            elif self.join_smart_var.get():
                try:
                    sec = float(self.join_seconds_var.get().replace(",", "."))
                    has_reencode = sec > 0.001
                except (ValueError, AttributeError):
                    has_reencode = False
            else:
                has_reencode = False
            return not is_audio_only and has_reencode
        return False

    ENCODER_ADVANCED_AUTO_LABEL = "Automático"

    def _encoder_path(self) -> str:
        var = getattr(self, "acceleration_var", None)
        valor = var.get() if var is not None else PATH_LABELS[ENCODER_PATH_GPU]
        return ENCODER_PATH_CPU if valor == PATH_LABELS[ENCODER_PATH_CPU] else ENCODER_PATH_GPU

    def _advanced_key(self) -> str:
        var = getattr(self, "encoder_advanced_var", None)
        escolhido = var.get() if var is not None else ""
        if not escolhido or escolhido == self.ENCODER_ADVANCED_AUTO_LABEL:
            return ENCODER_ADVANCED_AUTO
        for option in getattr(self, "available_encoder_options", []):
            if option.path == ENCODER_PATH_GPU and option.label == escolhido:
                return option.key
        return ENCODER_ADVANCED_AUTO

    def _advanced_labels(self) -> tuple[str, ...]:
        """Uma entrada por VENDOR (o codec quem decide é a tarefa, não o usuário)."""
        rotulos: list[str] = []
        for option in getattr(self, "available_encoder_options", []):
            if option.path == ENCODER_PATH_GPU and option.label not in rotulos:
                rotulos.append(option.label)
        return (self.ENCODER_ADVANCED_AUTO_LABEL,) + tuple(rotulos)

    def _on_encoder_path_changed(self) -> None:
        self._refresh_encoder_control_state()

    def _show_encoder_help(self) -> None:
        messagebox.showinfo(
            "Encoder de vídeo",
            "GPU: usa o encoder de hardware (NVENC/QSV/AMF) sempre que ele existir para o codec "
            "necessário — em geral é bem mais rápido. Se a GPU falhar (driver, sessão ocupada), a "
            "tarefa é repetida na CPU e o app avisa no log.\n\n"
            "CPU: reencoda sempre no processador (libx264/libx265). Mais lento, porém menor arquivo "
            "para o mesmo bitrate e sem depender do driver da placa.\n\n"
            "Avançado (só no modo GPU): " + self.ENCODER_ADVANCED_AUTO_LABEL + " deixa o app escolher "
            "sozinho entre os encoders de hardware disponíveis — e usar a CPU quando a GPU não tiver "
            "o codec pedido ou quando o trecho a reencodar for curto demais para a inicialização do "
            "hardware compensar. Escolher um encoder específico força aquela placa; se ela não "
            "estiver disponível, o app cai na CPU avisando no log.",
        )

    def _log_encoder_choice(self, message: str) -> None:
        """Informa a escolha do encoder no log de atividade (cor automática)."""
        try:
            app = getattr(self, "app", None)
            if app is not None and hasattr(app, "_append_activity_log"):
                app._append_activity_log(message)
        except Exception:
            pass

    @staticmethod
    def _preserved_codec(media) -> str:
        """Codec do arquivo quando dá para preservá-lo; senão H.264 (compatível)."""
        return normalize_codec(getattr(media, "video_codec", "") or "") or "h264"

    def _cut_job_seconds(self) -> float:
        """Duração do trecho a reencodar no corte (0 quando não dá para saber)."""
        if self._cut_mode_is_copy():
            return 0.0
        try:
            inicio = float(str(self.cut_start_var.get()).replace(",", ".") or 0)
            fim = float(str(self.cut_end_var.get()).replace(",", ".") or 0)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, fim - inicio)

    def _rotate_job_seconds(self) -> float:
        media = getattr(self, "rotate_media_profile", None)
        duracao = float(getattr(media, "duration", 0.0) or 0.0)
        try:
            inicio = float(str(self.rotate_start_var.get()).replace(",", ".") or 0)
            fim = float(str(self.rotate_end_var.get()).replace(",", ".") or duracao)
        except (TypeError, ValueError):
            return duracao
        if fim > inicio:
            trecho = min(fim, duracao or fim) - inicio
            return trecho if trecho > 0 else duracao
        return duracao

    def _task_codec_and_seconds(self, tool: str) -> tuple[str, float]:
        """Codec exigido pela tarefa e duração do vídeo a reencodar."""
        if tool == "Cortar":
            return self._preserved_codec(getattr(self, "cut_media_profile", None)), self._cut_job_seconds()
        if tool == "Girar vídeo":
            media = getattr(self, "rotate_media_profile", None)
            return self._preserved_codec(media), self._rotate_job_seconds()
        return "h264", 0.0

    def _resolve_task_encoder(self, tool: str) -> VideoAcceleration | None:
        """Escolhe o encoder da tarefa (GPU/CPU + codec + duração) e explica no log."""
        codec, segundos = self._task_codec_and_seconds(tool)
        escolha = resolve_encoder(
            codec=codec,
            path=self._encoder_path(),
            available=list(self.available_encoder_options),
            advanced=self._advanced_key(),
            seconds=segundos,
        )
        if escolha is None:
            self._log_encoder_choice(
                "Nenhum encoder de vídeo disponível para esta tarefa; mantendo a escolha anterior."
            )
            return None
        self._log_encoder_choice(
            f"Encoder de vídeo: {escolha.option.label} ({escolha.option.encoder}) — {escolha.reason}"
        )
        return VideoAcceleration(escolha.option.key, escolha.option.label, escolha.option.encoder)

    def _refresh_effective_encoder_label(self) -> None:
        """Mostra no topo quando a escolha automática não é a "esperada" (ex.: CPU no modo GPU)."""
        if not hasattr(self, "encoder_effective_label"):
            return
        etiqueta = self._encoder_extra("encoder_effective_label")
        if etiqueta is None:
            return
        if self._encoder_path() != ENCODER_PATH_GPU:
            etiqueta.pack_forget()
            return
        codec, segundos = self._task_codec_and_seconds(self.active_tool_var.get())
        escolha = resolve_encoder(
            codec=codec,
            path=ENCODER_PATH_GPU,
            available=list(self.available_encoder_options),
            advanced=self._advanced_key(),
            seconds=segundos,
        )
        if escolha is None or escolha.option.path == ENCODER_PATH_GPU:
            etiqueta.pack_forget()
            return
        self.encoder_effective_var.set(f"→ {escolha.option.label} ({escolha.option.encoder}): {escolha.reason}")
        if not etiqueta.winfo_ismapped():
            etiqueta.pack(side=RIGHT, padx=(12, 4), pady=(4, 0))

    def _refresh_encoder_control_state(self) -> None:
        uses_video_encoder = self._current_tool_uses_video_encoder()

        has_encoder = bool(self.available_accelerations)
        if not hasattr(self, "acceleration_combo") or not hasattr(self, "quality_label"):
            return
        if not uses_video_encoder or not has_encoder:
            self.acceleration_combo.configure(state="disabled")
            self.quality_menu_button.pack_forget()
            self.quality_label.pack_forget()
            self.quality_help_button.pack_forget()
            self._forget_encoder_extras()
            return
        self.acceleration_combo.configure(state="readonly")
        if not self.quality_label.winfo_ismapped():
            self.quality_help_button.pack(side=RIGHT, padx=(4, 0), pady=(2, 0))
            self.quality_menu_button.pack(side=RIGHT, pady=(2, 0))
            self.quality_label.pack(side=RIGHT, padx=(12, 4), pady=(4, 0))
        ajuda = self._encoder_extra("encoder_help_button")
        if ajuda is not None and not ajuda.winfo_ismapped():
            ajuda.pack(side=RIGHT, padx=(4, 0), pady=(2, 0))
        self._refresh_encoder_advanced_controls()

    ENCODER_EXTRA_WIDGETS = (
        "encoder_help_button",
        "encoder_advanced_combo",
        "encoder_advanced_label",
        "encoder_effective_label",
    )

    def _encoder_extra(self, nome: str):
        """Widget do seletor de encoder; tolerante a paineis sem UI (testes)."""
        return getattr(self, nome, None)

    def _forget_encoder_extras(self) -> None:
        for nome in self.ENCODER_EXTRA_WIDGETS:
            widget = self._encoder_extra(nome)
            if widget is not None:
                widget.pack_forget()

    def _refresh_encoder_advanced_controls(self) -> None:
        """O Avançado só aparece no modo GPU, com o que passou na sondagem."""
        combo = self._encoder_extra("encoder_advanced_combo")
        rotulo = self._encoder_extra("encoder_advanced_label")
        if self._encoder_path() != ENCODER_PATH_GPU or combo is None or rotulo is None:
            for widget in (combo, rotulo):
                if widget is not None:
                    widget.pack_forget()
            return
        rotulos = self._advanced_labels()
        combo.configure(values=rotulos, state="readonly")
        if self.encoder_advanced_var.get() not in rotulos:
            self.encoder_advanced_var.set(self.ENCODER_ADVANCED_AUTO_LABEL)
        if len(rotulos) > 1 and not combo.winfo_ismapped():
            combo.pack(side=RIGHT, padx=(6, 0), pady=(2, 0))
            rotulo.pack(side=RIGHT, padx=(12, 4), pady=(4, 0))

    @staticmethod
    def _show_video_speed_help(self) -> None:
        messagebox.showinfo(
            "Velocidade",
            "Velocidade e qualidade são eixos separados: a Qualidade manda no CRF "
            "(quanto de detalhe se preserva), a Velocidade manda no esforço que o encoder "
            "faz para chegar lá.\n\n"
            "Rápida: processa antes e gera arquivos maiores.\n\n"
            "Equilibrada (recomendada): o melhor equilíbrio entre tempo e tamanho nos "
            "encoders de CPU (x264/x265).\n\n"
            "Máxima qualidade: arquivos menores para o mesmo CRF, processando mais lento.\n\n"
            "Nos encoders por hardware (NVENC/QSV/AMF) a velocidade não se aplica: eles têm "
            "os próprios presets.",
        )

    @staticmethod
    def _show_video_quality_help() -> None:
        messagebox.showinfo(
            "Qualidade do vídeo",
            "Máxima prioriza a imagem e tende a gerar arquivos maiores e processar mais lentamente.\n\n"
            "Muito alta mantém excelente qualidade com menor uso de espaço.\n\n"
            "Alta (Recomendado) equilibra imagem, tamanho e velocidade; nos encoders por hardware usa o bitrate do original como referência.\n\n"
            "Média reduz espaço com perda visual moderada.\n\n"
            "Econômica prioriza arquivos menores.\n\n"
            "A saída normalmente usa H.264/MP4. Se a instalação não oferecer libx264, o fallback CPU pode usar MPEG-4 Part 2; o status e o log mostram o encoder efetivo.",
        )

    def _set_extract_preset(self, preset: str) -> None:
        if self.extract_preset_sync:
            return
        self.extract_preset_sync = True
        try:
            if preset == "transcription" and self.extract_transcription_preset_var.get():
                self.extract_compact_preset_var.set(False)
                self.extract_extension_var.set("wav")
                self.extract_rate_var.set("16000")
                self.extract_channels_var.set("1")
                self.extract_bitrate_var.set("256k")
            elif preset == "compact" and self.extract_compact_preset_var.get():
                self.extract_transcription_preset_var.set(False)
                self.extract_extension_var.set("ogg")
                self.extract_rate_var.set("16000")
                self.extract_channels_var.set("1")
                self.extract_bitrate_var.set("32k")
        finally:
            self.extract_preset_sync = False
        self._refresh_extract_preset_controls()
        self._on_extract_format_changed()

    def _on_extract_format_changed(self) -> None:
        fmt = self.extract_extension_var.get().lower()
        if hasattr(self, "extract_rate_combo"):
            if fmt == "opus":
                allowed_rates = ("8000", "12000", "16000", "24000", "48000")
                self.extract_rate_combo.configure(values=allowed_rates)
                if self.extract_rate_var.get() not in allowed_rates:
                    self.extract_rate_var.set("48000")
            else:
                standard_rates = ("8000", "16000", "22050", "44100", "48000")
                self.extract_rate_combo.configure(values=standard_rates)
                if self.extract_rate_var.get() not in standard_rates:
                    self.extract_rate_var.set("48000")
        self._refresh_extract_bitrate_choices()

    def _refresh_extract_bitrate_choices(self) -> None:
        if not hasattr(self, "extract_bitrate_combo"):
            return
        locked = self.extract_transcription_preset_var.get() or self.extract_compact_preset_var.get()
        fmt = self.extract_extension_var.get().lower()
        is_lossless = fmt in {"wav", "flac"}
        if locked or is_lossless:
            self.extract_bitrate_combo.configure(state="disabled")
            return
        all_bitrates = ("32k", "48k", "64k", "96k", "128k", "192k", "256k")
        if fmt == "ogg":
            try:
                rate = int(self.extract_rate_var.get())
            except ValueError:
                rate = 48000
            try:
                channels = int(self.extract_channels_var.get())
            except ValueError:
                channels = 2
            channel_map = self.VORBIS_VALID_BITRATES.get(channels, self.VORBIS_VALID_BITRATES[2])
            allowed = channel_map.get(rate, ("48k", "64k", "96k", "128k"))
            self.extract_bitrate_combo.configure(state="readonly", values=allowed)
            if self.extract_bitrate_var.get() not in allowed:
                self.extract_bitrate_var.set(allowed[0] if allowed else "64k")
        else:
            self.extract_bitrate_combo.configure(state="readonly", values=all_bitrates)

    def _refresh_extract_preset_controls(self) -> None:
        locked = self.extract_transcription_preset_var.get() or self.extract_compact_preset_var.get()
        for widget in self.extract_custom_widgets:
            widget.configure(state="disabled" if locked else "readonly")
        if not locked:
            self._refresh_extract_bitrate_choices()

    def _update_rotate_control_state(self) -> None:
        metadata_only = self.rotate_metadata_var.get()
        if metadata_only:
            if self.rotate_hflip_var.get() or self.rotate_vflip_var.get():
                self._append_log("Espelhamentos foram desativados: o modo somente metadados não aplica filtros de imagem.")
            self.rotate_hflip_var.set(False)
            self.rotate_vflip_var.set(False)
        has_trim = False
        try:
            duration = self.rotate_timeline.duration
            start = self._seconds(self.rotate_start_var.get(), "Início") or 0.0
            end = self._seconds(self.rotate_end_var.get(), "Fim", True)
            has_trim = duration > 0 and (start > 0.001 or (end is not None and end < duration - 0.05))
        except RuntimeError:
            pass
        state = "disabled" if metadata_only else "normal"
        self.rotate_parallel_check.configure(state="disabled" if (metadata_only or has_trim) else "normal")
        self.rotate_hflip_check.configure(state=state)
        self.rotate_vflip_check.configure(state=state)
        show_parallel_options = not metadata_only and not has_trim and self.rotate_parallel_var.get()
        if show_parallel_options:
            self.rotate_parallel_frame.pack(anchor="w", pady=(6, 0))
            self.rotate_device_limit_label.pack(anchor="w", pady=(3, 0))
        else:
            self.rotate_parallel_frame.pack_forget()
            self.rotate_device_limit_label.pack_forget()
        self._refresh_rotate_device_limit()
        self._refresh_rotate_thumbnail()
        self._refresh_encoder_control_state()

    def _on_rotate_transform_changed(self) -> None:
        self._refresh_rotate_thumbnail()
        self._refresh_encoder_control_state()

    def _refresh_rotate_device_limit(self) -> None:
        # FFmpeg não expõe uma API confiável de sessões simultâneas para NVENC,
        # QSV ou AMF. Não estimamos esse número sem uma fonte do driver.
        self.rotate_device_limit_var.set("")

    def _on_toggle_join_reencode(self) -> None:
        if self.join_reencode_var.get():
            self.join_smart_var.set(False)
        self._update_join_controls()
        self._refresh_encoder_control_state()

    def _on_join_seconds_changed(self) -> None:
        if hasattr(self, "join_stream_policy_combo"):
            self._update_join_controls()
        self._refresh_encoder_control_state()

    def _on_toggle_join_smart(self) -> None:
        if self.join_smart_var.get():
            self.join_reencode_var.set(False)
        self._update_join_controls()
        self._refresh_encoder_control_state()

    def _update_join_controls(self) -> None:
        reencode = self.join_reencode_var.get()
        smart = self.join_smart_var.get()
        has_mode = reencode or smart

        self.join_reencode_check.configure(state="normal" if not self.running else "disabled")
        self.join_smart_check.configure(state="normal" if not self.running else "disabled")
        self.join_transition_combo.configure(state="readonly" if (has_mode and not self.running) else "disabled")
        self.join_seconds_entry.configure(state="normal" if (has_mode and not self.running) else "disabled")

        profiles = getattr(self, "join_media_profiles", {})
        is_audio_only = bool(getattr(self, "join_inputs", [])) and all(
            (profiles[path].has_audio and not profiles[path].has_video)
            if path in profiles else path.suffix.lower() in AUDIO_EXTENSIONS
            for path in self.join_inputs
        )
        try:
            transition_seconds = float(self.join_seconds_var.get().replace(",", "."))
        except ValueError:
            transition_seconds = 0.0
        copy_without_transition = (not reencode and not smart) or (smart and transition_seconds <= 0.001)
        known_profiles = [profiles[path] for path in self.join_inputs if path in profiles]
        mixed_audio = bool(known_profiles) and any(item.has_audio for item in known_profiles) and any(not item.has_audio for item in known_profiles)
        fill_silence = self.join_audio_policy_var.get().startswith("Preservar áudio")
        all_streams_available = copy_without_transition and not (mixed_audio and fill_silence)
        unlocked = not self.running
        self.join_profile_combo.configure(state="readonly" if (unlocked and not is_audio_only and not copy_without_transition) else "disabled")
        self.join_audio_policy_combo.configure(state="readonly" if (unlocked and not is_audio_only) else "disabled")
        if is_audio_only:
            self.join_audio_policy_var.set("Preservar áudio e preencher silêncio")
        stream_choices = (
            ("Primeira faixa (MP4)", "Todas as faixas (MKV, sem transição)")
            if all_streams_available else ("Primeira faixa (MP4)",)
        )
        self.join_stream_policy_combo.configure(
            values=stream_choices,
            state="readonly" if unlocked else "disabled",
        )
        if self.join_stream_policy_var.get() not in stream_choices:
            self.join_stream_policy_var.set("Primeira faixa (MP4)")

        if is_audio_only:
            if smart:
                choices = ("Fade in/out",)
                self.join_transition_combo.configure(values=choices)
                if self.join_transition_var.get() not in choices:
                    self.join_transition_var.set("Fade in/out")
            elif reencode:
                choices = tuple(
                    label for label, _value in self.AUDIO_TRANSITIONS
                    if label != "Fade in/out" and label != "Sem transição"
                )
                self.join_transition_combo.configure(values=choices)
                if self.join_transition_var.get() not in choices:
                    self.join_transition_var.set("Linear")
        else:
            if smart:
                self.join_transition_combo.configure(values=self.TRANSITIONS)
                if self.join_transition_var.get() not in self.TRANSITIONS:
                    self.join_transition_var.set("Fade in/out")
            elif reencode:
                choices = tuple(item for item in self.TRANSITIONS if item != "Fade in/out")
                self.join_transition_combo.configure(values=choices)
                if self.join_transition_var.get() == "Fade in/out" or self.join_transition_var.get() not in choices:
                    self.join_transition_var.set("Fundir")

        self._update_join_advanced_controls(known_profiles, is_audio_only)
        self._update_join_transition_markers()
        if hasattr(self, "join_sidebar"):
            self.root.after_idle(self._fit_join_list)

    def _update_join_transition_markers(self) -> None:
        if not hasattr(self, "join_timeline"):
            return
        try:
            seconds = float(self.join_seconds_var.get().replace(",", "."))
        except ValueError:
            seconds = 0.0
        label = self.join_transition_var.get()
        enabled = (self.join_reencode_var.get() or self.join_smart_var.get()) and (
            math.isfinite(seconds) and seconds > 0.001 and label != "Sem transição"
        )
        boundaries = []
        if enabled:
            elapsed = 0.0
            for path in self.join_inputs[:-1]:
                media = self.join_media_profiles.get(path)
                if media is None:
                    boundaries.clear()
                    break
                elapsed += media.duration
                boundaries.append(elapsed)
        self.join_timeline.set_transition_points(tuple(boundaries), label if boundaries else "")

    def _update_join_advanced_controls(self, profiles: list[MediaProfile], is_audio_only: bool) -> None:
        if not hasattr(self, "join_policies_frame"):
            return
        advanced = self.join_advanced_var.get()
        videos = [profile for profile in profiles if profile.has_video]
        # O banner de câmeras VFR pode mostrar médias diferentes para gravações
        # com a mesma taxa nominal. Isso sozinho não deve abrir outro controle.
        video_profiles = [self._smart_join_video_profile(
            replace(profile, fps=profile.average_rate or profile.fps)
        ) for profile in videos]
        mixed_profiles = bool(videos) and any(
            smart_join_planner.video_incompatibility(video_profiles[0], profile) is not None
            for profile in video_profiles[1:]
        )
        multiple_tracks = any(
            profile.audio_streams > 1 or profile.subtitle_streams or profile.data_streams
            for profile in profiles
        )
        rows = (
            (self.join_profile_row, not is_audio_only and (advanced or mixed_profiles)),
            (self.join_stream_row, advanced and multiple_tracks),
            (self.join_audio_row, advanced and not is_audio_only),
        )
        for row, _visible in rows:
            row.pack_forget()
        for row, visible in rows:
            if visible:
                row.pack(fill=X, pady=(6, 0))

    def _fit_join_list(self) -> None:
        """A lista cresce na folga da coluna, preservando as opções e a saída."""
        from tkinter import font
        sidebar = self.join_sidebar
        reserved = 0
        for widget in sidebar.winfo_children():
            if widget is self.join_list_frame or not widget.winfo_manager():
                continue
            reserved += widget.winfo_reqheight() + vertical_padding_total(widget.pack_info().get("pady", 0))
        line_height = max(1, font.Font(font=self.join_list.cget("font")).metrics("linespace"))
        available = sidebar.winfo_height() - reserved - 10
        rows = max(2, min(8, available // line_height))
        if int(self.join_list.cget("height")) != rows:
            self.join_list.configure(height=rows)

    def _on_toggle_insert_reencode(self) -> None:
        if self.insert_reencode_var.get():
            self.insert_smart_var.set(False)
        self._update_insert_controls()

    def _on_toggle_insert_smart(self) -> None:
        if self.insert_smart_var.get():
            self.insert_reencode_var.set(False)
        self._update_insert_controls()

    def _update_insert_controls(self) -> None:
        reencode = self.insert_reencode_var.get()
        smart = self.insert_smart_var.get()
        has_mode = reencode or smart
        hint = getattr(self, "insert_processing_hint_var", None)
        if hint is not None:
            profile = getattr(self, "_insert_main_profile", None)
            codec = profile.audio_codec if profile else ""
            path = getattr(self, "insert_main_input", None)
            partial = profile and path and self._insert_partial_supported(profile, path, path)
            if not smart or not profile:
                hint.set("")
            elif partial and codec.startswith("pcm_"):
                hint.set("Smart Insert: o principal será copiado por amostras; somente o áudio inserido será recodificado.")
            elif partial:
                hint.set("Smart Insert: o principal será copiado; somente o inserido e a emenda serão recodificados.")
            else:
                hint.set(f"Smart Insert: {codec} exige recodificação contínua para evitar erros nas emendas. "
                         "O efeito selecionado será mantido; recodificar áudio costuma ser leve.")
        enabled = has_mode and not self.running and self.insert_secondary_input is not None

        self.insert_reencode_check.configure(state="normal" if not self.running else "disabled")
        self.insert_smart_check.configure(state="normal" if not self.running else "disabled")
        self.insert_transition_combo.configure(state="readonly" if enabled else "disabled")
        seconds_relevant = enabled and self.insert_transition_var.get() != "Sem transição"
        self.insert_seconds_entry.configure(state="normal" if seconds_relevant else "disabled")

        if smart:
            # Smart Insert: todas as curvas disponíveis — cada uma suaviza
            # apenas o áudio inserido (afade com a curva escolhida).
            choices = self.insert_transition_labels(True)
            self.insert_transition_combo.configure(values=choices)
            if self.insert_transition_var.get() not in choices:
                self.insert_transition_var.set("Fade in/out")
        elif reencode:
            # Reencode Completo: mesmo conjunto do Smart (inclui "Fade in/out",
            # aplicado com afade; as demais curvas usam acrossfade).
            choices = self.insert_transition_labels(False)
            self.insert_transition_combo.configure(values=choices)
            if self.insert_transition_var.get() not in choices:
                self.insert_transition_var.set("Crossfade linear")
        else:
            self.insert_transition_var.set("Sem transição")

    def _show_insert_options(self, visible: bool) -> None:
        if visible:
            if not self.insert_options_frame.winfo_ismapped():
                self.insert_options_frame.pack(fill=X, pady=(4, 0))
        else:
            self.insert_options_frame.pack_forget()
        self._update_insert_controls()

    @staticmethod
    def _clock(seconds: float) -> str:
        milliseconds = max(0, int(seconds * 1000))
        total, millis = divmod(milliseconds, 1000)
        return f"{total // 60}:{total % 60:02d}.{millis:03d}"

    def _request_waveform(self, target, source: Path, duration: float) -> None:
        """Cache por arquivo; a extração nunca roda no thread do Tk."""
        self.waveform_requests.pop(target, None)
        try:
            stat = source.stat()
        except OSError:
            self._apply_waveform(target, None)
            return
        key = (str(source), stat.st_mtime_ns, stat.st_size, duration)
        self.waveform_requests[target] = key
        if key in self.waveform_cache:
            self._apply_waveform(target, self.waveform_cache[key])
        elif key not in self.waveform_pending:
            self.waveform_pending.add(key)
            self.waveform_executor.submit(self._waveform_worker, key, source, duration)

    def _waveform_worker(self, key: tuple, source: Path, duration: float) -> None:
        process = None
        levels = None
        try:
            if self.waveform_stop_event.is_set():
                return
            command = [
                str(self._ffmpeg()), "-hide_banner", "-loglevel", "error", "-i", str(source),
                "-map", "0:a:0", "-vn", "-ac", "2", "-ar", str(WAVEFORM_SAMPLE_RATE),
                "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1",
            ]
            self._record_ffmpeg_command(command, probe=True)
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            with self.waveform_lock:
                self.waveform_processes.add(process)
            samples_per_bin = max(1, math.ceil(max(0.0, duration) * WAVEFORM_SAMPLE_RATE / WAVEFORM_POINTS))
            peaks = []
            started = time.monotonic()
            while not self.waveform_stop_event.is_set():
                raw = process.stdout.read(samples_per_bin * 4)
                if not raw:
                    break
                samples = array("h")
                samples.frombytes(raw[:len(raw) - len(raw) % 2])
                if samples:
                    peaks.append(max(abs(min(samples)), abs(max(samples))) / 32768.0)
                if time.monotonic() - started > 90:
                    raise TimeoutError("Tempo excedido ao carregar waveform")
            if not self.waveform_stop_event.is_set() and process.wait(timeout=5) == 0:
                levels = tuple(peaks)
        except Exception:
            levels = None
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                if process.stdout:
                    process.stdout.close()
                with self.waveform_lock:
                    self.waveform_processes.discard(process)
            self.waveform_queue.put((key, levels))

    def _apply_pending_waveforms(self) -> None:
        try:
            while True:
                key, levels = self.waveform_queue.get_nowait()
                self.waveform_pending.discard(key)
                if levels is not None:
                    self.waveform_cache[key] = levels
                    while len(self.waveform_cache) > 8:
                        self.waveform_cache.pop(next(iter(self.waveform_cache)))
                for target, requested in list(self.waveform_requests.items()):
                    if requested == key:
                        self._apply_waveform(target, levels)
        except queue.Empty:
            pass

    def _apply_waveform(self, target, levels: tuple[float, ...] | None) -> None:
        if target == "insert_main":
            self.insert_timeline.main_levels = levels or ()
            self.insert_timeline.draw()
        elif target == "insert_secondary":
            self.insert_timeline.inserted_levels = levels or ()
            self.insert_timeline.draw()
        elif isinstance(target, tuple) and target[0] == "join":
            data = self.preview_waveforms.get(self.join_preview)
            if data and "segments" in data and target[1] < len(data["segments"]):
                data["segments"][target[1]]["levels"] = levels or ()
                self._draw_audio_waveform(self.join_preview)
        elif target in self.preview_waveforms:
            self.preview_waveforms[target]["levels"] = levels or ()
            self._draw_audio_waveform(target)

    def _draw_audio_waveform(self, canvas: Canvas) -> None:
        data = self.preview_waveforms.get(canvas)
        if not data:
            return
        view = self.preview_viewports[canvas]
        width, height = max(1, view.stage_width), max(1, view.stage_height)
        left, right, center = 18, max(19, width - 18), height / 2
        canvas.delete("all")
        canvas.configure(background="#ffffff", cursor="hand2")
        canvas.create_line(left, center, right, center, fill="#dce7e2")
        levels = data["levels"]
        segments = data.get("segments")
        if segments:
            elapsed = 0.0
            for segment in segments:
                segment_left = left + (right - left) * elapsed / max(0.01, data["duration"])
                elapsed += segment["duration"]
                segment_right = left + (right - left) * elapsed / max(0.01, data["duration"])
                count = max(1, int((segment_right - segment_left) / 4))
                for index, peak in enumerate(waveform_amplitudes(segment["levels"] or (), 0, 1, count)):
                    x = segment_left + (segment_right - segment_left) * (index + 0.5) / count
                    amplitude = max(1.0, (height - 48) * 0.43 * math.sqrt(peak))
                    canvas.create_line(x, center - amplitude, x, center + amplitude, fill="#5edaf2", width=2)
                if elapsed < data["duration"]:
                    canvas.create_line(segment_right, 24, segment_right, height - 24, fill="#dce7e2")
        elif levels:
            count = max(2, int((right - left) / 4))
            for index, peak in enumerate(waveform_amplitudes(levels, 0, 1, count)):
                x = left + (right - left) * (index + 0.5) / count
                amplitude = max(1.0, (height - 48) * 0.43 * math.sqrt(peak))
                canvas.create_line(x, center - amplitude, x, center + amplitude, fill="#5edaf2", width=2)
        else:
            canvas.create_text(
                width / 2, center, text="Carregando waveform…" if levels is None else "Waveform indisponível",
                fill="#667371", font=("Segoe UI", 10),
            )
        context = next((item for item in self.tool_preview_contexts.values() if item.get("canvas") is canvas), None)
        if context:
            self._update_waveform_position(context)

    def _update_waveform_position(self, context: dict) -> None:
        canvas = context.get("canvas")
        data = getattr(self, "preview_waveforms", {}).get(canvas)
        if not data or data["duration"] <= 0:
            return
        width = self.preview_viewports[canvas].stage_width
        height = self.preview_viewports[canvas].stage_height
        x = 18 + max(1, width - 36) * context["timeline"].position / data["duration"]
        canvas.delete("waveform_position")
        canvas.create_line(x, 16, x, height - 16, fill="#dca42a", width=2, tags="waveform_position")
        canvas.create_polygon(x, 16, x - 5, 8, x + 5, 8, fill="#dca42a", outline="", tags="waveform_position")

    def _seek_waveform(self, canvas: Canvas, x: float) -> str:
        context = self.preview_context
        if not context or context.get("canvas") is not canvas:
            return "break"
        data = self.preview_waveforms[canvas]
        width = self.preview_viewports[canvas].stage_width
        seconds = max(0, min(1, (x - 18) / max(1, width - 36))) * data["duration"]
        context["timeline"].set_position(seconds)
        self._timeline_changed("position", context["timeline"].position, context["current_var"])
        return "break"

    def _activate_preview(self, source: Path, canvas: Canvas, timeline: RangeTimeline,
                          current_var: StringVar, button, tool: str, media: MediaProfile | None = None) -> None:
        self._stop_preview()
        media = media or self._probe_media(source)
        duration = media.duration
        timeline.set_media(duration)
        current_var.set(self._clock(0))
        audio_only = not media.has_video or tool == "clean"
        self.preview_context = {
            "source": source, "canvas": canvas, "timeline": timeline, "current_var": current_var,
            "button": button, "duration": duration, "tool": tool, "audio_only": audio_only,
            "has_video": not audio_only, "has_audio": media.has_audio,
        }
        self.tool_preview_contexts[tool] = self.preview_context
        display_width, display_height = self._cut_display_size(media)
        if tool == "rotate":
            self.rotate_media_profile = media
            display_width, display_height = self._rotated_media_size(media, self._rotate_preview_filter())
        elif tool == "cut":
            self.cut_media_profile = media
        self._preview_show_hint(canvas, "Carregando waveform…" if audio_only else "Carregando prévia…")
        if audio_only:
            self.preview_waveforms[canvas] = {"source": source, "duration": duration, "levels": None}
            self._reset_preview_view(canvas, 0, 0)
            self._request_waveform(canvas, source, duration)
        else:
            self._reset_preview_view(canvas, display_width, display_height)
            self._show_video_thumbnail(canvas, source, 0.0, self._rotate_preview_filter() if tool == "rotate" else "")

    @staticmethod
    def _rotated_media_size(media: MediaProfile, filters: str) -> tuple[int, int]:
        """Proporção EXIBIDA da mídia: 90/270 giram o quadro (largura <-> altura)."""
        if "transpose=1" in filters or "transpose=2" in filters:
            return media.height, media.width
        return media.width, media.height

    @staticmethod
    def _cut_display_size(media: MediaProfile) -> tuple[int, int]:
        """Tamanho EXIBIDO no corte: o FFmpeg autorrota o quadro antes dos filtros.

        (Comprovado com um arquivo de matriz 90°: o quadro decodificado sai
        transposto — por isso o recorte e a proporção usam este tamanho.)
        """
        if media.rotation % 180:
            return media.height, media.width
        return media.width, media.height

    def _stop_preview(self) -> None:
        self.preview_generation += 1
        self.preview_playing = False
        if self.preview_still_after_id:
            try:
                self.root.after_cancel(self.preview_still_after_id)
            except Exception:
                pass
            self.preview_still_after_id = None
        if self.preview_restart_id:
            try:
                self.root.after_cancel(self.preview_restart_id)
            except Exception:
                pass
            self.preview_restart_id = None
        for canvas, view in self.preview_viewports.items():
            view.drag_origin = None
            self.preview_selection_drag.pop(canvas, None)
            try:
                canvas.configure(cursor="crosshair")
            except Exception:
                pass
        if self.preview_after_id:
            try:
                self.root.after_cancel(self.preview_after_id)
            except Exception:
                pass
            self.preview_after_id = None
        self.preview_player.close()
        self._terminate_preview_process(self.external_preview_process)
        self.external_preview_process = None
        self._terminate_preview_process(getattr(self, "audio_preview_process", None))
        self.audio_preview_process = None
        self.frame_preview_stop_event.set()
        self._terminate_preview_process(self.frame_preview_process)
        self.frame_preview_process = None
        if self.preview_context:
            self.preview_context["button"].configure(text=">")

    def _toggle_preview(self) -> None:
        context = self.preview_context
        if not context or context["duration"] <= 0:
            return
        if context.get("tool") == "insert_audio":
            self._toggle_insert_preview()
            return
        if self.preview_playing:
            self.preview_player.pause()
            self._terminate_preview_process(self.external_preview_process)
            self.external_preview_process = None
            self._terminate_preview_process(getattr(self, "audio_preview_process", None))
            self.audio_preview_process = None
            self.frame_preview_stop_event.set()
            self._terminate_preview_process(self.frame_preview_process)
            self.frame_preview_process = None
            self.preview_playing = False
            context["button"].configure(text=">")
            return
        position = context["timeline"].position
        if position < context["timeline"].start or position >= context["timeline"].end:
            position = context["timeline"].start
        if context["audio_only"]:
            try:
                self._start_canvas_preview(context, position)
            except Exception as exc:
                self._stop_preview()
                messagebox.showerror("sig", f"Não foi possível reproduzir o áudio:\n{exc}")
            return
        use_canvas = (
            self.preview_speed != 1.0
            or context["tool"] == "join"
            or (context["tool"] == "rotate" and bool(self._rotate_preview_filter()))
            or not self._preview_view_is_fitted(context["canvas"])
        )
        if use_canvas or not self.preview_player.open(context["source"], context["canvas"]):
            try:
                self._start_canvas_preview(context, position)
            except Exception as exc:
                self._stop_preview()
                messagebox.showerror("sig", f"Não foi possível reproduzir a mídia:\n{exc}")
            return
        if self.preview_player.play(position):
            self.preview_playing = True
            context["button"].configure(text="||")
            self._preview_tick()

    def _toggle_insert_preview(self) -> None:
        context = self.preview_context
        if not context or not self.insert_main_input:
            return
        if self.preview_playing:
            self.preview_generation += 1
            if self.preview_after_id:
                try:
                    self.root.after_cancel(self.preview_after_id)
                except Exception:
                    pass
                self.preview_after_id = None
            self._terminate_preview_process(self.external_preview_process)
            self.external_preview_process = None
            self._terminate_preview_process(getattr(self, "audio_preview_process", None))
            self.audio_preview_process = None
            self._terminate_preview_process(self.frame_preview_process)
            self.frame_preview_process = None
            self.preview_playing = False
            context["button"].configure(text=">")
            return
        position = max(0.0, min(self.insert_timeline.position, self.insert_timeline.duration))
        if position >= self.insert_timeline.duration - 0.01:
            position = 0.0
            self.insert_timeline.set_position(position)
        self._start_insert_preview_segment(context, position)

    def _preview_atempo_filter(self) -> str:
        """Converte a velocidade escolhida em uma cadeia aceita pelo atempo.

        O filtro aceita apenas fatores entre 0.5 e 2.0 por instância; por isso
        3x e 4x são compostos por mais de uma etapa.
        """
        target = max(PREVIEW_SPEED_VALUES[0], min(PREVIEW_SPEED_VALUES[-1], float(self.preview_speed)))
        factors: list[float] = []
        while target > 2.0:
            factors.append(2.0)
            target /= 2.0
        while target < 0.5:
            factors.append(0.5)
            target /= 0.5
        factors.append(target)
        return ",".join(f"atempo={factor:.6g}" for factor in factors)

    @staticmethod
    def _audio_preview_media_duration(end: float, offset: float) -> float:
        # O -t do FFplay é tempo de MÍDIA (o atempo já acelera a saída): não dividir por velocidade.
        return max(0.01, end - offset)

    @staticmethod
    def _preview_video_filters(width: int, height: int, fps: int, speed: float) -> list[str]:
        # setsar=1 evita distorção de vídeos anamórficos (SAR != 1:1) na prévia.
        return [
            f"setpts=PTS/{speed}",
            f"fps={fps}",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "setsar=1",
        ]

    @staticmethod
    def _insert_effective_transition(
        main_duration: float,
        inserted_duration: float,
        insertion: float,
        requested: float,
    ) -> float:
        neighbors = [inserted_duration]
        if insertion > 0:
            neighbors.append(insertion)
        if main_duration - insertion > 0:
            neighbors.append(main_duration - insertion)
        return min(requested, max(0.0, min(neighbors) / 2 if neighbors else 0.0))

    @staticmethod
    def _insert_composite_to_output_position(
        composite_position: float,
        insertion: float,
        inserted_duration: float,
        effective: float,
        crossfade: bool,
        has_left: bool,
        has_right: bool,
    ) -> float:
        if not crossfade or effective <= 0:
            return composite_position
        if composite_position < insertion:
            return composite_position
        shift = effective if has_left else 0.0
        if composite_position >= insertion + inserted_duration and has_right:
            shift += effective
        return max(0.0, composite_position - shift)

    @staticmethod
    def _insert_output_to_composite_position(
        output_position: float,
        insertion: float,
        inserted_duration: float,
        effective: float,
        crossfade: bool,
        has_left: bool,
        has_right: bool,
    ) -> float:
        if not crossfade or effective <= 0:
            return output_position
        shift = 0.0
        if has_left and output_position >= insertion - effective:
            shift += effective
        right_start = insertion + inserted_duration - shift - (effective if has_right else 0.0)
        if has_right and output_position >= right_start:
            shift += effective
        return output_position + shift

    def _insert_smart_preview_filter(self, profile: MediaProfile, inserted_duration: float,
                                     insertion: float, fade_seconds: float, fade_curve: str = "fade") -> str:
        return self._insert_audio_filter(profile, inserted_duration, insertion, fade_seconds,
                                         fade_curve if fade_seconds > 0 else "none", True)[0]

    def _start_insert_filtered_preview(self, context: dict, composite_position: float) -> bool:
        main = self.insert_main_input
        inserted = self.insert_secondary_input
        if not main or not inserted:
            return False
        transition_label = self.insert_transition_var.get()
        transition_code = self.insert_transition_code(transition_label)
        try:
            requested = float(self.insert_seconds_var.get().replace(",", ".")) if transition_code != "none" else 0.0
        except ValueError:
            return False
        if not math.isfinite(requested) or requested < 0:
            return False
        full_reencode = self.insert_reencode_var.get()
        smart_transition = self.insert_smart_var.get() and transition_code != "none" and requested > 0
        if not (full_reencode and transition_code != "none" and requested > 0) and not smart_transition:
            return False

        profile = self._insert_probe_profile(main)
        inserted_duration = self._insert_duration(inserted)
        rate = profile.audio_rate
        insertion = max(0, min(round(self.insert_timeline.insertion * rate), round(profile.duration * rate))) / rate
        inserted_duration = round(inserted_duration * rate) / rate
        effective = (min(requested, inserted_duration / 2) if smart_transition and not full_reencode else
                     self._insert_effective_transition(profile.duration, inserted_duration, insertion, requested))
        effective = round(effective * rate) / rate
        if full_reencode:
            preview_args = self._insert_full_reencode_arguments(
                main, inserted, Path("preview.wav"), profile, insertion, requested, transition_code,
                log_adjustment=False,
            )
            filter_text = preview_args[preview_args.index("-filter_complex") + 1]
        else:
            filter_text = self._insert_smart_preview_filter(
                profile, inserted_duration, insertion, effective, transition_code
            )
        crossfade = full_reencode and transition_code not in {"none", "fade"} and effective > 0
        output_position = self._insert_composite_to_output_position(
            composite_position,
            insertion,
            inserted_duration,
            effective,
            crossfade,
            insertion > 0,
            round(profile.duration * rate) / rate - insertion > 0,
        )
        filter_text += (
            f";[aout]atrim=start={self._precise_seconds(output_position)},"
            "asetpts=PTS-STARTPTS[apreview]"
        )
        command = [
            str(self._ffmpeg()), "-hide_banner", "-loglevel", "error",
            "-i", str(main), "-i", str(inserted),
            "-filter_complex", filter_text, "-map", "[apreview]",
            "-c:a", "pcm_s16le", "-f", "wav", "pipe:1",
        ]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self._record_ffmpeg_command(command, force=True)
        try:
            self.frame_preview_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=flags | (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
            assert self.frame_preview_process.stdout is not None
            self.external_preview_process = subprocess.Popen(
                [
                    str(self._ffplay()), "-hide_banner", "-loglevel", "warning", "-autoexit", "-nodisp",
                    "-af", self._preview_atempo_filter(), "pipe:0",
                ],
                stdin=self.frame_preview_process.stdout,
                creationflags=flags | (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
            self.frame_preview_process.stdout.close()
        except Exception as exc:
            self._terminate_preview_process(self.frame_preview_process)
            self.frame_preview_process = None
            messagebox.showerror("sig", f"Não foi possível renderizar a transição da prévia:\n{exc}")
            return False
        self.insert_preview_composite_start = composite_position
        self.insert_preview_phase_end = self.insert_timeline.duration
        context["insert_filtered_preview"] = True
        context["insert_preview_output_start"] = output_position
        context["insert_preview_effective"] = effective
        context["insert_preview_crossfade"] = crossfade
        context["insert_preview_has_left"] = insertion > 0
        context["insert_preview_has_right"] = round(profile.duration * rate) / rate - insertion > 0
        self.external_preview_started_at = time.monotonic()
        self.preview_playing = True
        context["button"].configure(text="||")
        self._insert_preview_tick(context, self.preview_generation)
        return True

    def _start_insert_preview_segment(self, context: dict, composite_position: float) -> None:
        self.preview_generation += 1
        generation = self.preview_generation
        self._terminate_preview_process(self.external_preview_process)
        self.external_preview_process = None
        self._terminate_preview_process(getattr(self, "audio_preview_process", None))
        self.audio_preview_process = None
        self._terminate_preview_process(self.frame_preview_process)
        self.frame_preview_process = None
        if self._start_insert_filtered_preview(context, composite_position):
            return
        timeline = self.insert_timeline
        inserted_duration = timeline.inserted_duration
        insertion = timeline.insertion
        total = timeline.duration
        inserted = self.insert_secondary_input
        context["insert_filtered_preview"] = False
        if inserted and inserted_duration > 0 and composite_position < insertion:
            source = self.insert_main_input
            source_offset = composite_position
            phase_end = insertion
        elif inserted and inserted_duration > 0 and composite_position < insertion + inserted_duration:
            source = inserted
            source_offset = composite_position - insertion
            phase_end = insertion + inserted_duration
        else:
            source = self.insert_main_input
            source_offset = composite_position - inserted_duration if inserted and composite_position >= insertion + inserted_duration else composite_position
            phase_end = total
        remaining = max(0.02, phase_end - composite_position)
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.external_preview_process = subprocess.Popen(
                [
                    str(self._ffplay()), "-hide_banner", "-loglevel", "warning", "-autoexit", "-nodisp",
                    "-ss", self._fmt_seconds(max(0.0, source_offset)), "-t", self._fmt_seconds(remaining),
                    "-af", self._preview_atempo_filter(), str(source),
                ],
                creationflags=flags | (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
        except Exception as exc:
            messagebox.showerror("sig", f"Não foi possível reproduzir a inserção:\n{exc}")
            return
        self.insert_preview_composite_start = composite_position
        self.insert_preview_phase_end = phase_end
        self.external_preview_started_at = time.monotonic()
        self.preview_playing = True
        context["button"].configure(text="||")
        self._insert_preview_tick(context, generation)

    def _insert_preview_tick(self, context: dict, generation: int) -> None:
        if (
            not self.preview_playing
            or context is not self.preview_context
            or generation != self.preview_generation
        ):
            return
        elapsed = (time.monotonic() - self.external_preview_started_at) * self.preview_speed
        if context.get("insert_filtered_preview"):
            output_position = float(context.get("insert_preview_output_start", 0.0)) + elapsed
            position = self._insert_output_to_composite_position(
                output_position,
                self.insert_timeline.insertion,
                self.insert_timeline.inserted_duration,
                float(context.get("insert_preview_effective", 0.0)),
                bool(context.get("insert_preview_crossfade")),
                bool(context.get("insert_preview_has_left")),
                bool(context.get("insert_preview_has_right")),
            )
            position = min(self.insert_preview_phase_end, position)
        else:
            position = min(self.insert_preview_phase_end, self.insert_preview_composite_start + elapsed)
        self.insert_timeline.set_position(position)
        main_position = self.insert_timeline.composite_to_main(position)
        context["current_var"].set(self._clock(main_position))
        context["timeline"].set_position(position)
        process = self.external_preview_process
        if process is not None and process.poll() is not None:
            if context.get("insert_filtered_preview"):
                self._finish_insert_preview(context)
                return
            if position < self.insert_timeline.duration - 0.03:
                self._start_insert_preview_segment(context, position)
                return
            self._finish_insert_preview(context)
            return
        if position >= self.insert_preview_phase_end - 0.03:
            if position < self.insert_timeline.duration - 0.03:
                self._start_insert_preview_segment(context, position)
            else:
                self._finish_insert_preview(context)
            return
        self.preview_after_id = self.root.after(60, lambda: self._insert_preview_tick(context, generation))

    def _finish_insert_preview(self, context: dict) -> None:
        self._terminate_preview_process(self.external_preview_process)
        self.external_preview_process = None
        self._terminate_preview_process(getattr(self, "audio_preview_process", None))
        self.audio_preview_process = None
        self._terminate_preview_process(self.frame_preview_process)
        self.frame_preview_process = None
        self.preview_playing = False
        self.insert_timeline.set_position(self.insert_timeline.duration)
        context["current_var"].set(self._clock(self.insert_timeline.composite_to_main(self.insert_timeline.duration)))
        context["button"].configure(text=">")

    def _jump_to_insert_preview_position(self, composite_position: float) -> None:
        if not self.preview_context or self.preview_context.get("tool") != "insert_audio":
            return
        self.insert_timeline.set_position(composite_position)
        main_position = self.insert_timeline.composite_to_main(composite_position)
        self.insert_current_var.set(self._clock(main_position))
        if self.preview_playing:
            self._start_insert_preview_segment(self.preview_context, composite_position)

    def _preview_tick(self) -> None:
        context = self.preview_context
        if not self.preview_playing or not context:
            return
        position = self.preview_player.position()
        timeline = context["timeline"]
        end = timeline.end
        context["timeline"].set_position(position)
        context["current_var"].set(self._clock(position))
        if position >= end - 0.05:
            self.preview_player.pause()
            self.preview_player.seek(end)
            timeline.set_position(end)
            context["current_var"].set(self._clock(end))
            self.preview_playing = False
            context["button"].configure(text=">")
            return
        self.preview_after_id = self.root.after(100, self._preview_tick)

    @staticmethod
    def _terminate_preview_process(process: subprocess.Popen | None) -> None:
        if not process or process.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                process.terminate()
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _start_canvas_preview(self, context: dict, offset: float) -> None:
        self.preview_generation += 1
        generation = self.preview_generation
        canvas = context["canvas"]
        canvas.update_idletasks()
        timeline = context["timeline"]
        if offset < timeline.start or offset > timeline.end:
            offset = timeline.start
        play_duration = max(0.01, (timeline.end - offset) / self.preview_speed)
        timeline.set_position(offset)
        context["current_var"].set(self._clock(offset))
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        if context.get("audio_only"):
            self.frame_preview_stop_event.clear()
            self.external_preview_started_at = time.monotonic()
            self.external_preview_offset = offset
            if context["tool"] == "join":
                self._start_join_audio_preview(context, offset)
            else:
                self.external_preview_process = subprocess.Popen(
                    [
                        str(self._ffplay()), "-hide_banner", "-loglevel", "warning", "-autoexit", "-nodisp",
                        "-ss", self._fmt_seconds(offset), "-t", self._fmt_seconds(self._audio_preview_media_duration(timeline.end, offset)),
                        "-af", self._preview_atempo_filter(), str(context["source"]),
                    ],
                    creationflags=flags | (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
                )
            self.preview_playing = True
            context["button"].configure(text="||")
            self.status_var.set("Reproduzindo áudio dentro da ferramenta.")
            self._audio_preview_tick(context, generation)
            return
        width, height = self._preview_pipeline_size(canvas)
        fps = 15
        filters = []
        if context["tool"] == "rotate":
            rotate_filter = self._rotate_preview_filter()
            if rotate_filter:
                filters.append(rotate_filter)
        filters += self._preview_video_filters(width, height, fps, self.preview_speed)
        self.frame_preview_stop_event.clear()
        video_command = [
            str(self._ffmpeg()), "-hide_banner", "-loglevel", "error", "-ss", self._fmt_seconds(offset),
            "-i", str(context["source"]), "-t", self._fmt_seconds(play_duration), "-an", "-vf", ",".join(filters), "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
        ]
        if context["tool"] == "join":
            video_command = self._join_preview_arguments(context, offset, video=True, width=width, height=height, fps=fps)
        self._record_ffmpeg_command(video_command, force=True)
        self.frame_preview_process = subprocess.Popen(
            video_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=flags | (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        )
        if context.get("has_audio", True):
            audio_command = [
                str(self._ffplay()), "-hide_banner", "-loglevel", "warning", "-autoexit", "-nodisp", "-ss", self._fmt_seconds(offset), "-t", self._fmt_seconds(self._audio_preview_media_duration(timeline.end, offset)), "-af", self._preview_atempo_filter(), str(context["source"]),
            ]
            if context["tool"] == "join":
                self._start_join_audio_preview(context, offset)
            else:
                self.external_preview_process = subprocess.Popen(
                    audio_command,
                    creationflags=flags | (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
                )
        else:
            self.external_preview_process = None
        self.preview_playing = True
        context["button"].configure(text="||")
        self.status_var.set("Prévia reproduzida dentro da ferramenta.")

        frame_process = self.frame_preview_process
        def render_frames():
            process = frame_process
            frame_size = width * height * 3
            index = 0
            started_at = None
            try:
                while process and process.stdout and not self.frame_preview_stop_event.is_set():
                    raw = process.stdout.read(frame_size)
                    if len(raw) != frame_size:
                        break
                    if started_at is None:
                        started_at = time.monotonic()
                    target_time = started_at + index / fps
                    remaining = target_time - time.monotonic()
                    if remaining > 0 and self.frame_preview_stop_event.wait(remaining):
                        break
                    image = Image.frombytes("RGB", (width, height), raw)
                    position = offset + index / fps * self.preview_speed
                    if position > timeline.end + 0.001:
                        break
                    index += 1
                    try:
                        self.preview_frame_queue.put_nowait((context, generation, image, position, False))
                    except queue.Full:
                        try:
                            self.preview_frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            self.preview_frame_queue.put_nowait((context, generation, image, position, False))
                        except queue.Full:
                            pass
            finally:
                if started_at is not None and index:
                    remaining = started_at + index / fps - time.monotonic()
                    if remaining > 0:
                        self.frame_preview_stop_event.wait(remaining)
                while True:
                    try:
                        self.preview_frame_queue.put_nowait((context, generation, None, 0.0, True))
                        break
                    except queue.Full:
                        try:
                            self.preview_frame_queue.get_nowait()
                        except queue.Empty:
                            break

        self.frame_preview_thread = threading.Thread(target=render_frames, daemon=True)
        self.frame_preview_thread.start()

    def _audio_preview_tick(self, context: dict, generation: int) -> None:
        if (
            not self.preview_playing
            or context is not self.preview_context
            or generation != self.preview_generation
            or self.frame_preview_stop_event.is_set()
        ):
            return
        timeline = context["timeline"]
        elapsed = (time.monotonic() - self.external_preview_started_at) * self.preview_speed
        position = min(timeline.end, self.external_preview_offset + elapsed)
        timeline.set_position(position)
        context["current_var"].set(self._clock(position))
        self._update_waveform_position(context)
        process = self.external_preview_process
        if not process or process.poll() is not None or position >= timeline.end - 0.03:
            self._terminate_preview_process(process)
            self.external_preview_process = None
            self._terminate_preview_process(getattr(self, "audio_preview_process", None))
            self.audio_preview_process = None
            self.preview_playing = False
            context["button"].configure(text=">")
            return
        self.preview_after_id = self.root.after(80, lambda: self._audio_preview_tick(context, generation))

    def _poll_preview_frames(self) -> None:
        try:
            while True:
                context, generation, image, position, finished = self.preview_frame_queue.get_nowait()
                if finished:
                    self._finish_canvas_preview(context, generation)
                elif image is not None:
                    self._render_canvas_frame(context, generation, image, position)
        except queue.Empty:
            pass
        self._apply_pending_stills()
        self._apply_pending_waveforms()
        try:
            self.root.after(33, self._poll_preview_frames)
        except Exception:
            pass

    def _render_canvas_frame(self, context: dict, generation: int, image: Image.Image, position: float) -> None:
        if self.frame_preview_stop_event.is_set() or context is not self.preview_context or generation != self.preview_generation:
            return
        canvas = context["canvas"]
        self.preview_frames[canvas] = image
        self._paint_preview_view(canvas)
        context["timeline"].set_position(position)
        context["current_var"].set(self._clock(position))

    def _finish_canvas_preview(self, context: dict, generation: int) -> None:
        if self.frame_preview_stop_event.is_set() or context is not self.preview_context or generation != self.preview_generation:
            return
        self.preview_playing = False
        self.frame_preview_process = None
        self._terminate_preview_process(self.external_preview_process)
        self.external_preview_process = None
        self._terminate_preview_process(getattr(self, "audio_preview_process", None))
        self.audio_preview_process = None
        if context["tool"] == "join":
            context["timeline"].set_position(context["timeline"].end)
            context["current_var"].set(self._clock(context["timeline"].end))
        context["button"].configure(text=">")

    def _seek_preview(self, seconds: float, current_var: StringVar, restart_playback: bool = False) -> None:
        current_var.set(self._clock(seconds))
        if self.preview_player.opened:
            if restart_playback and self.preview_playing:
                self.preview_player.pause()
            self.preview_player.seek(seconds)
            if restart_playback and self.preview_playing:
                self.preview_player.play(seconds)

    def _timeline_changed(self, target: str, seconds: float, current_var: StringVar) -> None:
        context = self.preview_context
        if not context:
            current_var.set(self._clock(seconds))
            return
        timeline = context["timeline"]
        self._update_waveform_position(context)
        if target == "position":
            is_canvas = bool(self.frame_preview_process or self.external_preview_process)
            if self.preview_playing and (is_canvas or not self.preview_player.opened):
                self._jump_to_preview_position(context, seconds)
                return
            self._seek_preview(seconds, current_var, restart_playback=True)
            return
        if not self.preview_playing:
            return
        if target == "start" and seconds > timeline.position:
            self._jump_to_preview_position(context, seconds)
        elif target == "end" and seconds < timeline.position:
            self._jump_to_preview_position(context, seconds)

    def _jump_to_preview_position(self, context: dict, seconds: float) -> None:
        timeline = context["timeline"]
        timeline.set_position(seconds)
        context["current_var"].set(self._clock(seconds))
        if seconds >= timeline.end:
            self._stop_preview()
            self._update_waveform_position(context)
            return
        is_canvas = bool(self.frame_preview_process or self.external_preview_process)
        if self.preview_player.opened and not is_canvas:
            self.preview_player.pause()
            self.preview_player.seek(seconds)
            self.preview_player.play(seconds)
            return
        # A prévia por FFmpeg/FFplay não oferece seek durante a execução;
        # reiniciamos os dois fluxos no novo ponto para áudio e vídeo seguirem juntos.
        self.frame_preview_stop_event.set()
        self._terminate_preview_process(self.external_preview_process)
        self.external_preview_process = None
        self._terminate_preview_process(getattr(self, "audio_preview_process", None))
        self.audio_preview_process = None
        self._terminate_preview_process(self.frame_preview_process)
        self.frame_preview_process = None
        self.preview_playing = False
        self._start_canvas_preview(context, seconds)

    def _ffplay(self) -> Path:
        path = app_base_dir() / "ffplay.exe"
        if not path.exists():
            raise RuntimeError("ffplay.exe não foi encontrado na pasta do aplicativo")
        return path

    def _cut_timeline_changed(self, target: str, seconds: float) -> None:
        if target == "start":
            self.cut_start_var.set(self._fmt_seconds(seconds))
        elif target == "end":
            self.cut_end_var.set(self._fmt_seconds(seconds))
        self._timeline_changed(target, seconds, self.cut_current_var)

    def _extract_timeline_changed(self, target: str, seconds: float) -> None:
        if target == "start":
            self.extract_start_var.set(self._fmt_seconds(seconds))
        elif target == "end":
            self.extract_end_var.set(self._fmt_seconds(seconds))
        self._timeline_changed(target, seconds, self.extract_current_var)

    def _rotate_timeline_changed(self, target: str, seconds: float) -> None:
        if target == "start":
            self.rotate_start_var.set(self._fmt_seconds(seconds))
        elif target == "end":
            self.rotate_end_var.set(self._fmt_seconds(seconds))
        self._timeline_changed(target, seconds, self.rotate_current_var)
        if not self.preview_player.opened and self.rotate_input:
            self._show_video_thumbnail(self.rotate_preview, self.rotate_input, seconds, self._rotate_preview_filter())

    def _sync_cut_range_from_entries(self) -> None:
        if self.cut_timeline.duration <= 0:
            return
        try:
            start = self._seconds(self.cut_start_var.get(), "Início") or 0.0
            end = self._seconds(self.cut_end_var.get(), "Fim")
            if end is not None and end > start:
                self.cut_timeline.set_range(start, end)
        except RuntimeError:
            pass

    def _sync_extract_range_from_entries(self) -> None:
        if self.extract_timeline.duration <= 0:
            return
        try:
            start = self._seconds(self.extract_start_var.get(), "Início", True)
            end = self._seconds(self.extract_end_var.get(), "Fim", True)
            if start is not None and end is not None and end > start:
                self.extract_timeline.set_range(start, end)
        except RuntimeError:
            pass

    def _sync_rotate_range_from_entries(self) -> None:
        if self.rotate_timeline.duration <= 0:
            return
        try:
            start = self._seconds(self.rotate_start_var.get(), "Início") or 0.0
            end = self._seconds(self.rotate_end_var.get(), "Fim")
            if end is not None and end > start:
                self.rotate_timeline.set_range(start, end)
                self._update_rotate_control_state()
        except RuntimeError:
            pass

    def _rotate_preview_filter(self) -> str:
        try:
            degrees = int(self.rotate_degrees_var.get())
        except ValueError:
            degrees = 0
        filters: list[str] = []
        if degrees == -90:
            filters.append("transpose=2")
        elif degrees == 90:
            filters.append("transpose=1")
        elif abs(degrees) == 180:
            filters.extend(("hflip", "vflip"))
        if self.rotate_hflip_var.get():
            filters.append("hflip")
        if self.rotate_vflip_var.get():
            filters.append("vflip")
        return ",".join(filters)

    def _refresh_rotate_thumbnail(self) -> None:
        if not self.rotate_input:
            return
        self._stop_preview()
        self._rotate_selection_with_filters()
        self._apply_rotate_media_size()
        self._show_video_thumbnail(
            self.rotate_preview,
            self.rotate_input,
            self.rotate_timeline.position,
            self._rotate_preview_filter(),
        )

    def _rotate_selection_with_filters(self) -> None:
        """Seleção desenhada + giro novo: ela gira junto para cobrir os mesmos pixels."""
        canvas = getattr(self, "rotate_preview", None)
        selecao = self.preview_selections.get(canvas)
        if selecao is None:
            return
        antigos = self.preview_selection_filters.get(canvas, "")
        novos = self._rotate_preview_filter()
        if antigos == novos:
            return
        self.preview_selections[canvas] = selection_between_filters(selecao, antigos, novos)
        self.preview_selection_filters[canvas] = novos

    def _apply_rotate_media_size(self) -> None:
        """A aba Girar muda a proporção exibida: 90/270 trocam largura e altura."""
        media = self.rotate_media_profile
        view = self.preview_viewports.get(getattr(self, "rotate_preview", None))
        if media is None or view is None:
            return
        width, height = self._rotated_media_size(media, self._rotate_preview_filter())
        if (width, height) != (view.media_width, view.media_height):
            view.media_width, view.media_height = width, height
            self._fit_preview_stage(self.rotate_preview)

    def _preview_still_key(self, source: Path, seconds: float, filters: str) -> tuple:
        """Chave do quadro congelado: arquivo (+mtime), tempo e filtros."""
        try:
            mtime = source.stat().st_mtime_ns
        except OSError:
            mtime = 0
        return (str(source), mtime, round(max(0.0, float(seconds)), 2), str(filters or ""))

    def _show_video_thumbnail(self, canvas: Canvas, source: Path, seconds: float, filters: str) -> None:
        """Quadro congelado da prévia: agrupado, com cache e SEM travar a interface.

        Antes: um FFmpeg SÍNCRONO por movimento da linha do tempo — a interface
        congelava durante a extração e o log era inundado (um comando por passo do
        arrasto). Agora o pedido é agrupado (debounce curto), reaproveitado quando
        já foi extraído antes (cache por arquivo+tempo+filtros) e extraído em
        segundo plano, entregue pelo mesmo laço de UI que pinta os quadros vivos.
        """
        self.preview_frames.pop(canvas, None)
        self.preview_frame_items.pop(canvas, None)
        context = getattr(self, "preview_context", None)
        context_matches = bool(context and context.get("source") == source)
        has_video = bool(context.get("has_video")) if context_matches else self._probe_media(source).has_video
        if not has_video:
            self._preview_show_hint(canvas, f"{source.name}\nPrévia de áudio")
            return
        chave = self._preview_still_key(source, seconds, filters)
        self.preview_still_key[canvas] = chave
        guardado = self.preview_still_cache.get(chave)
        if guardado is not None:
            self.preview_stills[canvas] = guardado
            self._paint_preview_view(canvas)
            return
        self.preview_still_pending = {
            "canvas": canvas, "source": source, "seconds": seconds, "filters": filters, "key": chave,
        }
        if self.preview_still_after_id:
            try:
                self.root.after_cancel(self.preview_still_after_id)
            except Exception:
                pass
            self.preview_still_after_id = None
        # Sem quadro nenhum ainda (primeira carga): extrai quase na hora; com
        # quadro na tela (arrasto da linha do tempo), agrupa para não inundar.
        atraso = PREVIEW_STILL_DEBOUNCE_MS if self.preview_stills.get(canvas) is not None else 1
        self.preview_still_after_id = self.root.after(atraso, self._start_pending_still)

    def _start_pending_still(self) -> None:
        """Dispara a extração do último pedido — uma de cada vez, fora da UI."""
        self.preview_still_after_id = None
        if self.preview_still_running or not self.preview_still_pending:
            return
        pedido = self.preview_still_pending
        self.preview_still_pending = None
        self.preview_still_running = True
        threading.Thread(target=self._extract_still_worker, args=(pedido,), daemon=True).start()

    def _extract_still_worker(self, pedido: dict) -> None:
        """Extrai o quadro em segundo plano (sem tocar em Tk) e devolve pela fila."""
        imagem = None
        image_path = self.output_dir / f"preview_{uuid.uuid4().hex}.png"
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            command = [
                str(self._ffmpeg()), "-hide_banner", "-loglevel", "error", "-y",
                "-ss", self._fmt_seconds(float(pedido["seconds"])), "-i", str(pedido["source"]),
                "-frames:v", "1", "-an",
            ]
            if pedido["filters"]:
                command += ["-vf", str(pedido["filters"])]
            command.append(str(image_path))
            # Prévia NÃO é trabalho da ferramenta: registra como sonda para não
            # inundar o log de atividade (o rastreador da tarefa continua vendo).
            self._record_ffmpeg_command(command, probe=True)
            result = subprocess.run(
                command, capture_output=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if result.returncode == 0 and image_path.exists():
                with Image.open(image_path) as image:
                    imagem = image.copy()
        except Exception:
            imagem = None
        finally:
            image_path.unlink(missing_ok=True)
        try:
            self.preview_still_queue.put_nowait({"pedido": pedido, "image": imagem})
        except queue.Full:
            try:
                self.preview_still_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.preview_still_queue.put_nowait({"pedido": pedido, "image": imagem})
            except queue.Full:
                pass

    def _apply_pending_stills(self) -> None:
        """Aplica (na UI) os quadros congelados que ficaram prontos no segundo plano."""
        try:
            while True:
                pronto = self.preview_still_queue.get_nowait()
                self.preview_still_running = False
                pedido = pronto["pedido"]
                canvas = pedido["canvas"]
                imagem = pronto["image"]
                if imagem is None:
                    if self.preview_still_key.get(canvas) == pedido["key"]:
                        canvas.create_text(
                            max(80, canvas.winfo_width() // 2), max(40, canvas.winfo_height() // 2),
                            text="Não foi possível gerar a prévia deste vídeo",
                            fill="#667371", font=("Segoe UI", 10), justify="center",
                        )
                else:
                    self.preview_still_cache[pedido["key"]] = imagem
                    while len(self.preview_still_cache) > PREVIEW_STILL_CACHE_SIZE:
                        self.preview_still_cache.pop(next(iter(self.preview_still_cache)))
                    if self.preview_still_key.get(canvas) == pedido["key"]:
                        self.preview_stills[canvas] = imagem
                        self._paint_preview_view(canvas)
                self._start_pending_still()
        except queue.Empty:
            pass

    def select_cut_input(self) -> None:
        selected = filedialog.askopenfilename(title="Selecionar mídia para cortar", filetypes=self._filetypes())
        if selected:
            self.cut_input = Path(selected)
            self.cut_media_profile = self._probe_media(self.cut_input)
            self.cut_input_var.set(self.cut_input.name)
            self._activate_preview(self.cut_input, self.cut_preview, self.cut_timeline, self.cut_current_var, self.cut_play_button, "cut")
            self.cut_start_var.set("0")
            self.cut_end_var.set(self._fmt_seconds(self.cut_timeline.duration))
            self._update_cut_controls()

    def select_extract_inputs(self) -> None:
        selected = filedialog.askopenfilenames(title="Selecionar mídias", filetypes=self._filetypes())
        if selected:
            self.extract_inputs = [Path(item) for item in selected]
            self.extract_summary_var.set(f"{len(self.extract_inputs)} arquivo(s): {self.extract_inputs[0].name}")
            if len(self.extract_inputs) == 1:
                source = self.extract_inputs[0]
                self._activate_preview(source, self.extract_preview, self.extract_timeline, self.extract_current_var, self.extract_play_button, "extract")
                self.extract_start_var.set("0")
                self.extract_end_var.set(self._fmt_seconds(self.extract_timeline.duration))
            else:
                self._stop_preview()
                self.tool_preview_contexts.pop("extract", None)
                self.preview_context = None
                self.extract_timeline.set_media(0)
                self._reset_preview_view(self.extract_preview, 0, 0)
                self._preview_show_hint(
                    self.extract_preview,
                    "O recorte com marcadores fica disponível ao selecionar um único arquivo.",
                )
                self.extract_start_var.set("")
                self.extract_end_var.set("")

    def select_rotate_input(self) -> None:
        selected = filedialog.askopenfilename(title="Selecionar vídeo", filetypes=[("Vídeos", "*.mp4 *.mov *.mkv *.avi *.webm"), ("Todos os arquivos", "*.*")])
        if selected:
            self.rotate_input = Path(selected)
            self.rotate_input_var.set(self.rotate_input.name)
            self._activate_preview(self.rotate_input, self.rotate_preview, self.rotate_timeline, self.rotate_current_var, self.rotate_play_button, "rotate")
            self.rotate_start_var.set("0")
            self.rotate_end_var.set(self._fmt_seconds(self.rotate_timeline.duration))
            self._update_rotate_control_state()

    def select_clean_input(self) -> None:
        selected = filedialog.askopenfilename(title="Selecionar áudio", filetypes=self._filetypes())
        if selected:
            source = Path(selected)
            media = self._probe_media(source)
            if not media.has_audio:
                messagebox.showerror("sig", "O arquivo selecionado não contém uma faixa de áudio.")
                return
            self.clean_input = source
            self.clean_input_var.set(source.name)
            self._activate_preview(source, self.clean_preview, self.clean_timeline,
                                   self.clean_current_var, self.clean_play_button, "clean", media)

    def select_insert_main_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="Selecionar áudio principal",
            filetypes=[("Áudios", "*.wav *.mp3 *.m4a *.ogg *.opus *.flac *.aac *.wma"), ("Todos os arquivos", "*.*")],
        )
        if not selected:
            return
        source = Path(selected)
        media = self._insert_probe_profile(source)
        if not media.has_audio:
            messagebox.showerror("sig", "O arquivo selecionado não contém uma faixa de áudio.")
            return
        self._stop_preview()
        self.insert_main_input = source
        self._insert_main_profile = media
        self.insert_secondary_input = None
        self.insert_main_var.set(source.name)
        self.insert_secondary_var.set("Nenhum áudio para inserir")
        self.insert_timeline.main_levels = ()
        self.insert_timeline.inserted_levels = ()
        self.waveform_requests.pop("insert_secondary", None)
        self.insert_timeline.configure_media(source.name, media.duration)
        self._request_waveform("insert_main", source, media.duration)
        self.insert_timeline.configure(state="normal")
        self.insert_current_var.set(self._clock(0.0))
        self.insert_time_var.set(self._clock(0.0))
        self.insert_secondary_button.configure(state="normal")
        self._show_insert_options(False)
        self._set_insert_preview_context()

    def select_insert_secondary_input(self) -> None:
        if not self.insert_main_input:
            return
        selected = filedialog.askopenfilename(
            title="Selecionar áudio para inserir",
            filetypes=[("Áudios", "*.wav *.mp3 *.m4a *.ogg *.opus *.flac *.aac *.wma"), ("Todos os arquivos", "*.*")],
        )
        if not selected:
            return
        source = Path(selected)
        media = self._insert_probe_profile(source)
        if not media.has_audio:
            messagebox.showerror("sig", "O arquivo selecionado não contém uma faixa de áudio.")
            return
        insertion = self.insert_timeline.composite_to_main(self.insert_timeline.position)
        self._stop_preview()
        self.insert_secondary_input = source
        self.insert_timeline.inserted_levels = ()
        self._request_waveform("insert_secondary", source, media.duration)
        self.insert_secondary_var.set(f"Inserir: {source.name}")
        main_media = self._insert_probe_profile(self.insert_main_input)
        self.insert_timeline.configure_media(self.insert_main_input.name, main_media.duration, source.name, media.duration, insertion)
        self.insert_timeline.set_position(insertion)
        self.insert_current_var.set(self._clock(insertion))
        self.insert_time_var.set(self._clock(insertion))
        self._show_insert_options(True)
        self._set_insert_preview_context()

    def _set_insert_preview_context(self) -> None:
        if not self.insert_main_input:
            self.preview_context = None
            return
        self.preview_context = {
            "source": self.insert_main_input,
            "main_source": self.insert_main_input,
            "inserted_source": self.insert_secondary_input,
            "timeline": self.insert_timeline,
            "current_var": self.insert_current_var,
            "button": self.insert_play_button,
            "duration": self.insert_timeline.duration,
            "audio_only": True,
            "tool": "insert_audio",
            "insertion": self.insert_timeline.insertion,
            "inserted_duration": self.insert_timeline.inserted_duration,
        }
        self.tool_preview_contexts["insert_audio"] = self.preview_context

    def _insert_timeline_changed(self, composite_position: float) -> None:
        if not self.preview_context or self.preview_context.get("tool") != "insert_audio":
            return
        main_position = self.insert_timeline.composite_to_main(composite_position)
        self.insert_current_var.set(self._clock(main_position))
        if self.preview_playing:
            self._jump_to_insert_preview_position(composite_position)

    def _insert_position_changed(self, main_position: float) -> None:
        self.insert_current_var.set(self._clock(main_position))
        self.insert_time_var.set(self._clock(main_position))
        self._set_insert_preview_context()
        if self.preview_playing:
            self._jump_to_insert_preview_position(main_position)

    def _apply_insert_time(self) -> bool:
        if not self.insert_main_input:
            return False
        raw = self.insert_time_var.get().strip().replace(",", ".")
        try:
            parts = raw.split(":")
            if len(parts) == 1:
                seconds = float(parts[0])
            elif len(parts) == 2:
                seconds = float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                seconds = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            else:
                raise ValueError
        except ValueError as exc:
            self.insert_time_var.set(self._clock(self.insert_timeline.composite_to_main(self.insert_timeline.position)))
            messagebox.showerror("sig", "O ponto de inserção deve ser um número ou um tempo no formato HH:MM:SS.mmm")
            return False
        main_position = max(0.0, min(seconds, self.insert_timeline.main_duration))
        self.insert_timeline.configure_media(
            self.insert_main_input.name,
            self.insert_timeline.main_duration,
            self.insert_secondary_input.name if self.insert_secondary_input else "",
            self.insert_timeline.inserted_duration,
            main_position,
        )
        self.insert_timeline.set_position(main_position)
        self.insert_current_var.set(self._clock(main_position))
        self.insert_time_var.set(self._clock(main_position))
        self._set_insert_preview_context()
        if self.preview_playing:
            self._jump_to_insert_preview_position(main_position)
        return True

    def _ask_join_rotation(self) -> bool:
        """Pergunta (modal) como tratar o giro dos vídeos antes do join com reencode.

        Devolve False se o usuário cancelou; a resposta fica em `_join_rotation_answer`
        e é copiada para `worker_options` pelo `run_current_tool`.
        """
        self._join_rotation_answer = None
        if self.active_tool_var.get() != "Juntar áudios/vídeos":
            return True
        inputs = list(getattr(self, "join_inputs", None) or [])
        profiles = getattr(self, "join_media_profiles", None) or {}
        if len(inputs) < 2 or any(path not in profiles for path in inputs):
            return True
        clips = [profiles[path] for path in inputs]
        # O diálogo aplica-se ao Reencode Completo (caminho que normaliza e
        # "assa" a rotação). O SmartJoin híbrido (com transição) copia corpos em
        # stream copy e não oferece o modo de preservar formato.
        reencode = bool(self.join_reencode_var.get())
        mp4_output = not str(self.join_stream_policy_var.get()).startswith("Todas")
        question = self._join_rotation_question(inputs, clips, bool(reencode) and mp4_output)
        if question is None:
            return True
        return self._show_join_rotation_dialog(inputs, question)

    def _show_join_rotation_dialog(self, paths: list[Path], question: dict) -> bool:
        """Janela modal com as opções da pergunta de orientação. True = prosseguir."""
        answer = {"cancelled": True}
        win = Toplevel(self.root)
        win.title("Giro nos vídeos")
        win.configure(background="#101418")
        win.resizable(False, False)
        win.transient(self.root)
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=BOTH, expand=True)
        ttk.Label(frame, text=question["message"], justify="left", wraplength=480).pack(
            anchor="w", pady=(0, 10)
        )
        choice = StringVar(value=question["default"])
        for option in question["options"]:
            row = ttk.Frame(frame)
            row.pack(fill=X, pady=(2, 0))
            ttk.Radiobutton(
                row,
                text=option["label"],
                value=option["key"],
                variable=choice,
            ).pack(anchor="w")
            ttk.Label(
                row,
                text=option["detail"],
                foreground="#8fa3a0",
                wraplength=440,
            ).pack(anchor="w", padx=(24, 0))

        def confirm(_event=None):
            key = str(choice.get())
            if key == "bake" or not key.startswith("preserve:"):
                self._join_rotation_answer = {"mode": "bake", "reference": ""}
            else:
                try:
                    index = int(key.partition(":")[2])
                    reference = str(paths[index])
                except (ValueError, IndexError):
                    self._join_rotation_answer = {"mode": "bake", "reference": ""}
                else:
                    self._join_rotation_answer = {"mode": "preserve", "reference": reference}
            answer["cancelled"] = False
            win.destroy()

        buttons = ttk.Frame(frame)
        buttons.pack(fill=X, pady=(10, 0))
        ttk.Button(buttons, text="Cancelar", command=win.destroy).pack(side=LEFT)
        ttk.Button(buttons, text="Juntar", command=confirm).pack(side=RIGHT)
        win.bind("<Return>", confirm)
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()
        self.root.wait_window(win)
        return not answer["cancelled"]

    def add_join_inputs(self) -> None:
        selected = filedialog.askopenfilenames(title="Selecionar áudios ou vídeos", filetypes=self._filetypes())
        if selected:
            new_paths = [Path(item) for item in selected]
            self.join_inputs.extend(new_paths)
            for path in new_paths:
                self.join_media_profiles[path] = self._probe_media(path)
            self._refresh_join_list()

    def remove_join_input(self) -> None:
        selection = self.join_list.curselection()
        if selection:
            removed = self.join_inputs.pop(selection[0])
            self.join_media_profiles.pop(removed, None)
            self._refresh_join_list()

    def move_join_input(self, direction: int) -> None:
        selection = self.join_list.curselection()
        if not selection:
            return
        index = selection[0]
        other = index + direction
        if not 0 <= other < len(self.join_inputs):
            return
        self.join_inputs[index], self.join_inputs[other] = self.join_inputs[other], self.join_inputs[index]
        self._refresh_join_list(other)

    def _refresh_join_list(self, selected_index: int | None = None) -> None:
        selection = self.join_list.curselection()
        if selected_index is None:
            selected_index = selection[0] if selection else 0
        self.join_list.delete(0, END)
        for index, path in enumerate(self.join_inputs, start=1):
            self.join_list.insert(END, f"{index}. {path.name}")
        if self.join_inputs:
            selected_index = min(selected_index, len(self.join_inputs) - 1)
            self.join_list.selection_set(selected_index)
            self.join_list.activate(selected_index)
            self.join_list.see(selected_index)
        self._rebuild_join_preview(selected_index)
        self._update_join_controls()
        self._refresh_encoder_control_state()

    def _rebuild_join_preview(self, selected_index: int = 0) -> None:
        self._stop_preview()
        self.tool_preview_contexts.pop("join", None)
        if not self.join_inputs:
            self.preview_context = None
            self.join_timeline.set_media(0)
            self.join_current_var.set(self._clock(0))
            self.join_preview_name_var.set("")
            self._preview_show_hint(self.join_preview, "")
            self.preview_still_key.pop(self.join_preview, None)
            return
        playlist = tuple((path, self.join_media_profiles[path]) for path in self.join_inputs)
        duration = sum(media.duration for _path, media in playlist)
        has_video = any(media.has_video for _path, media in playlist)
        has_audio = any(media.has_audio for _path, media in playlist)
        self.join_timeline.set_media(duration)
        self.preview_context = {
            "source": playlist[0][0], "canvas": self.join_preview, "timeline": self.join_timeline,
            "current_var": self.join_current_var, "button": self.join_play_button, "duration": duration,
            "tool": "join", "audio_only": not has_video, "has_video": has_video, "has_audio": has_audio,
            "playlist": playlist,
        }
        self.tool_preview_contexts["join"] = self.preview_context
        self._preview_show_hint(self.join_preview, "")
        # Clear obsolete waveform requests before installing the new order.
        for target in list(self.waveform_requests):
            if isinstance(target, tuple) and target[0] == "join":
                self.waveform_requests.pop(target)
        if not has_video:
            self.preview_waveforms[self.join_preview] = {
                "duration": duration, "levels": None,
                "segments": [{"source": path, "duration": media.duration, "levels": None} for path, media in playlist],
            }
            self._reset_preview_view(self.join_preview, 0, 0)
            for index, (path, media) in enumerate(playlist):
                self._request_waveform(("join", index), path, media.duration)
        else:
            media = next(media for _path, media in playlist if media.has_video)
            self._reset_preview_view(self.join_preview, *self._cut_display_size(media))
        seconds = sum(media.duration for _path, media in playlist[:selected_index])
        self.join_timeline.set_position(seconds)
        self.join_current_var.set(self._clock(seconds))
        self._show_join_position(self.preview_context, seconds)

    @staticmethod
    def _join_preview_clips(context: dict, offset: float) -> list[tuple[Path, MediaProfile, float, float]]:
        """Sufixo da sequência a partir do marcador, sem aplicar transições."""
        clips = []
        elapsed = 0.0
        for path, media in context["playlist"]:
            start = max(0.0, offset - elapsed)
            remaining = media.duration - start
            if remaining > 0.000001:
                clips.append((path, media, start, remaining))
            elapsed += media.duration
        return clips

    def _show_join_position(self, context: dict, seconds: float) -> None:
        clips = self._join_preview_clips(context, seconds)
        if not clips:
            path, media = context["playlist"][-1]
            local = max(0, media.duration - 0.04)
        else:
            path, media, local, _remaining = clips[0]
        self.join_preview_name_var.set(path.name)
        context["source"] = path
        if context["audio_only"]:
            self._draw_audio_waveform(self.join_preview)
        elif media.has_video:
            self._show_video_thumbnail(self.join_preview, path, local, "")
        else:
            self._preview_show_hint(self.join_preview, "")

    def _join_preview_arguments(self, context: dict, offset: float, *, video: bool = False,
                                width: int = 0, height: int = 0, fps: int = 15) -> list[str]:
        """Um fluxo contínuo FFmpeg, inclusive entre arquivos de formatos diferentes."""
        clips = self._join_preview_clips(context, offset)
        if not clips:
            raise RuntimeError("Não há mídia para reproduzir nesta posição.")
        command = [str(self._ffmpeg()), "-hide_banner", "-loglevel", "error"]
        filters = []
        for index, (path, media, start, remaining) in enumerate(clips):
            if start > 0:
                command += ["-ss", self._precise_seconds(start)]
            command += ["-i", str(path)]
            duration = self._precise_seconds(remaining)
            if video:
                if media.has_video:
                    stream = f"[{index}:v:0]setpts=PTS-STARTPTS,"
                    stream += f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    stream += f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,"
                    stream += f"tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration},setpts=PTS-STARTPTS"
                elif media.has_audio:
                    stream = f"[{index}:a:0]showwaves=s={width}x{height}:r={fps}:mode=line:colors=0x5edaf2,"
                    stream += f"format=yuv420p,tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration},setpts=PTS-STARTPTS"
                else:
                    stream = f"color=c=0xf4f7f6:s={width}x{height}:r={fps}:d={duration}"
                filters.append(f"{stream}[v{index}]")
            else:
                if media.has_audio:
                    stream = f"[{index}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    stream += f"asetpts=PTS-STARTPTS,apad,atrim=duration={duration}"
                else:
                    stream = f"anullsrc=r=48000:cl=stereo,atrim=duration={duration}"
                filters.append(f"{stream}[a{index}]")
        if video:
            labels = "".join(f"[v{i}]" for i in range(len(clips)))
            filters.append(f"{labels}concat=n={len(clips)}:v=1:a=0,setpts=PTS/{self.preview_speed},fps={fps}[preview]")
            command += ["-filter_complex", ";".join(filters), "-map", "[preview]", "-an",
                        "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
        else:
            labels = "".join(f"[a{i}]" for i in range(len(clips)))
            filters.append(f"{labels}concat=n={len(clips)}:v=0:a=1[preview]")
            command += ["-filter_complex", ";".join(filters), "-map", "[preview]",
                        "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"]
        return command

    def _start_join_audio_preview(self, context: dict, offset: float) -> None:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        command = self._join_preview_arguments(context, offset)
        self._record_ffmpeg_command(command, probe=True)
        self.audio_preview_process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=flags,
        )
        try:
            self.external_preview_process = subprocess.Popen(
                [str(self._ffplay()), "-hide_banner", "-loglevel", "warning", "-autoexit", "-nodisp",
                 "-af", self._preview_atempo_filter(), "pipe:0"],
                stdin=self.audio_preview_process.stdout, creationflags=flags,
            )
        except Exception:
            self._terminate_preview_process(self.audio_preview_process)
            self.audio_preview_process = None
            raise
        finally:
            if self.audio_preview_process and self.audio_preview_process.stdout:
                self.audio_preview_process.stdout.close()

    def _select_join_preview(self) -> None:
        selection = self.join_list.curselection()
        context = self.tool_preview_contexts.get("join")
        if not selection or not context:
            return
        seconds = sum(media.duration for _path, media in context["playlist"][:selection[0]])
        self.join_timeline.set_position(seconds)
        self._join_timeline_changed("position", seconds)

    def _join_timeline_changed(self, target: str, seconds: float) -> None:
        context = self.preview_context
        if not context or context.get("tool") != "join":
            return
        self._timeline_changed(target, seconds, self.join_current_var)
        if not self.preview_playing:
            self._show_join_position(context, seconds)

    def _clean_timeline_changed(self, target: str, seconds: float) -> None:
        self._timeline_changed(target, seconds, self.clean_current_var)

    def choose_output_dir(self) -> None:
        chosen = filedialog.askdirectory(title="Selecionar pasta de saída do FFmpeg", initialdir=str(self.output_dir))
        if chosen:
            self.output_dir = Path(chosen)
            self.output_dir_var.set(str(self.output_dir))
            self.output_dir_chosen = True

    def open_or_choose_output_dir(self) -> None:
        if self.output_dir_chosen:
            self.open_output_dir()
        else:
            self.choose_output_dir()

    def open_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(self.output_dir)
            else:
                webbrowser.open(self.output_dir.as_uri())
        except Exception as exc:
            messagebox.showerror("sig", f"Não foi possível abrir a pasta:\n{exc}")

    def _set_running_ui(self, running: bool) -> None:
        self.running = running
        self.run_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")
        if hasattr(self, "insert_main_button"):
            self.insert_main_button.configure(state="disabled" if running else "normal")
            self.insert_secondary_button.configure(state="disabled" if running or not self.insert_main_input else "normal")
            self._update_insert_controls()
        if hasattr(self, "cut_mode_combo"):
            self.cut_mode_combo.configure(state="disabled" if running else "readonly")
            self._update_cut_controls()
        if hasattr(self, "join_reencode_check"):
            self._update_join_controls()

    def _append_log(self, message: str) -> None:
        # Avisos de ajuste automático (transição reduzida, fallback de paralelo, etc.)
        # voltam a aparecer no log de atividade como aviso (amarelo).
        try:
            app = getattr(self, "app", None)
            if app is not None and hasattr(app, "_append_activity_log"):
                app._append_activity_log(message, tag="warning")
        except Exception:
            pass

    def _record_ffmpeg_command(self, command: list[object], *, force: bool = False, probe: bool = False) -> None:
        """Registra a linha real antes de iniciar um processo FFmpeg.

        Com o rastreador ativo (ferramenta em execução) guarda o comando cru
        para a renderização numerada/agrupada. Fora da execução, ``force`` grava
        direto no log de atividade com a formatação de comando único."""
        if self.running and self.task_tracker:
            self.task_tracker.command(command, probe=probe)
        elif force:
            rendered_command = format_ffmpeg_command_for_log(command)
            self.app._append_activity_log(
                rendered_command,
                "ffmpeg_command",
                raw=True,
            )

    def _set_status(self, message: str, progress: int | None = None) -> None:
        def apply():
            self.status_var.set(message)
            if progress is not None:
                safe_progress = max(0, min(100, progress))
                if self.running:
                    self.max_progress_seen = max(self.max_progress_seen, safe_progress)
                    safe_progress = self.max_progress_seen
                self.progress_var.set(safe_progress)
        self.root.after(0, apply)

    def _log_saved_output(self) -> None:
        """Conclusão da ferramenta: só no log de atividade (padrão verde automático)."""
        def apply():
            try:
                app = getattr(self, "app", None)
                if app is not None and hasattr(app, "_append_activity_log"):
                    app._append_activity_log(f"Concluído. Arquivos salvos em {self.output_dir}")
            except Exception:
                pass
            self.progress_var.set(100)
        self.root.after(0, apply)

    def _selection_crops(self) -> dict[str, tuple[int, int, int, int] | None]:
        """Recorte (x, y, largura, altura) por ferramenta, vindo da seleção desenhada."""
        crops: dict[str, tuple[int, int, int, int] | None] = {"cut_crop": None, "rotate_crop": None}
        cut_media = self.cut_media_profile
        if cut_media is not None and cut_media.has_video:
            largura, altura = self._cut_display_size(cut_media)
            crops["cut_crop"] = self._preview_selection_crop(self.cut_preview, largura, altura)
        rotate_media = self.rotate_media_profile
        if rotate_media is not None and rotate_media.has_video:
            largura, altura = self._rotated_media_size(rotate_media, self._rotate_preview_filter())
            crops["rotate_crop"] = self._preview_selection_crop(self.rotate_preview, largura, altura)
        return crops

    def _confirm_preview_selection(self, tool: str) -> bool:
        """Confirma o recorte por pixels antes de executar (regra do usuário).

        Salvar com uma seleção desenhada significa: o arquivo terá SÓ os pixels
        dentro da seleção (resolução n x m); o resto do quadro é descartado.
        """
        if tool not in ("Cortar", "Girar vídeo"):
            return True
        crop = self._selection_crops()["cut_crop" if tool == "Cortar" else "rotate_crop"]
        if crop is None:
            return True
        x, y, largura, altura = crop
        extra = ""
        if tool == "Cortar" and self._cut_mode_is_copy():
            self.cut_mode_var.set(CUT_MODE_REENCODE)
            self._update_cut_controls()
            extra = "\n\nA seleção exige reencodar: o modo foi alterado para 'Reencode Completo'."
        elif tool == "Girar vídeo" and (
            self.rotate_metadata_var.get() or not self._rotate_preview_filter()
        ):
            extra = "\n\nA seleção exige reencodar: o arquivo será regerado."
        message = (
            f"Será salvo apenas o que está DENTRO da seleção: "
            f"{selection_crop_label(crop)}.\n"
            "O restante do quadro será descartado." + extra
        )
        return bool(messagebox.askokcancel("sig", message))

    def _confirm_clean_strong(self) -> bool:
        """F9: o modo forte altera mais o áudio — confirmar antes de rodar.

        Mesma regra do SIG Android (que já confirma), agora também aqui.
        """
        if self.active_tool_var.get() != "Limpar áudio":
            return True
        if str(self.clean_mode_var.get()) != "forte":
            return True
        return bool(
            messagebox.askokcancel(
                "sig",
                "Limpeza forte: o filtro é bem mais agressivo e pode alterar um pouco a voz.\n"
                "Deseja continuar?",
            )
        )

    def run_current_tool(self) -> None:
        if self.running:
            return
        if self.app.running or self.app.live_state != "idle" or self.app.assistant_busy:
            messagebox.showinfo("sig", "Aguarde a tarefa atual de transcrição terminar antes de usar o FFmpeg.")
            return
        tool = self.active_tool_var.get()
        if tool == "Inserir áudio" and not self._apply_insert_time():
            return
        if tool == "Juntar áudios/vídeos" and not self._ask_join_rotation():
            return
        if not self._confirm_preview_selection(tool):
            return
        if not self._confirm_clean_strong():
            return
        selection_crops = self._selection_crops()
        # Capture Tk state on the UI thread. Workers use only plain Python values.
        self.worker_acceleration = self._resolve_task_encoder(tool)
        self.selected_acceleration_label = self.acceleration_var.get()
        self.selected_video_quality = self.video_quality_var.get()
        self.selected_video_speed = self.video_speed_var.get()
        self.worker_tool_uses_video_encoder = self._current_tool_uses_video_encoder()
        rotation_answer = self._join_rotation_answer or {}
        self.join_orientation_mode_var.set(str(rotation_answer.get("mode") or "bake"))
        self.join_orientation_reference_var.set(str(rotation_answer.get("reference") or ""))
        self.worker_options = {
            "cut_start": self.cut_start_var.get(), "cut_end": self.cut_end_var.get(), "cut_mode": self.cut_mode_var.get(),
            "cut_audio_policy": self.cut_audio_policy_var.get(), "cut_stream_policy": self.cut_stream_policy_var.get(),
            "extract_extension": self.extract_extension_var.get(), "extract_rate": self.extract_rate_var.get(),
            "extract_channels": self.extract_channels_var.get(), "extract_bitrate": self.extract_bitrate_var.get(),
            "extract_start": self.extract_start_var.get(), "extract_end": self.extract_end_var.get(),
            "rotate_degrees": self.rotate_degrees_var.get(), "rotate_metadata": self.rotate_metadata_var.get(),
            "rotate_hflip": self.rotate_hflip_var.get(), "rotate_vflip": self.rotate_vflip_var.get(),
            "rotate_parallel": self.rotate_parallel_var.get(), "rotate_segments": self.rotate_segments_var.get(),
            "rotate_start": self.rotate_start_var.get(), "rotate_end": self.rotate_end_var.get(),
            "join_reencode": self.join_reencode_var.get(), "join_smart": self.join_smart_var.get(),
            "join_transition": self.join_transition_var.get(), "join_seconds": self.join_seconds_var.get(),
            "join_profile": self.join_profile_var.get(), "join_stream_policy": self.join_stream_policy_var.get(),
            "join_audio_policy": self.join_audio_policy_var.get(),
            "join_orientation_mode": str(rotation_answer.get("mode") or "bake"),
            "join_orientation_reference": str(rotation_answer.get("reference") or ""),
            "insert_reencode": self.insert_reencode_var.get(), "insert_smart": self.insert_smart_var.get(),
            "insert_transition": self.insert_transition_var.get(), "insert_seconds": self.insert_seconds_var.get(),
            "clean_mode": self.clean_mode_var.get(),
            "cut_crop": selection_crops["cut_crop"], "rotate_crop": selection_crops["rotate_crop"],
            "encoder_path": self._encoder_path(),
            "encoder_advanced": self._advanced_key(),
            "encoder_options": [
                (option.key, option.label, option.path, option.codec, option.encoder, option.priority)
                for option in self.available_encoder_options
            ],
        }
        workers = {
            "Cortar": self._cut_worker,
            "Extrair áudio": self._extract_worker,
            "Girar vídeo": self._rotate_worker,
            "Juntar áudios/vídeos": self._join_worker,
            "Inserir áudio": self._insert_worker,
            "Limpar áudio": self._clean_worker,
        }
        worker = workers.get(tool)
        if worker is None:
            return
        from app_env import settings_path
        fields = {}
        for name in ("cut_input", "rotate_input", "insert_main_input", "insert_secondary_input", "clean_input"):
            value = getattr(self, name, None)
            fields[name] = str(value) if value else None
        fields["extract_inputs"] = [str(p) for p in self.extract_inputs]
        fields["join_inputs"] = [str(p) for p in self.join_inputs]
        selected_inputs = {
            "Cortar": [self.cut_input], "Extrair áudio": self.extract_inputs,
            "Girar vídeo": [self.rotate_input], "Juntar áudios/vídeos": self.join_inputs,
            "Inserir áudio": [self.insert_main_input, self.insert_secondary_input], "Limpar áudio": [self.clean_input],
        }[tool]
        request = {"tool": tool, "output_dir": str(self.output_dir), "fields": fields,
                   "options": self.worker_options, "insertion": self.insert_timeline.insertion,
                   "quality": self.selected_video_quality, "speed": self.selected_video_speed,
                   "encoder_label": self.selected_acceleration_label,
                   "acceleration": vars(self.worker_acceleration) if self.worker_acceleration else None,
                   "uses_encoder": self.worker_tool_uses_video_encoder}
        self.recovery_job = RecoveryJob.create(settings_path().parent / "ffmpeg_recovery", request,
                                              [Path(p) for p in selected_inputs if p])
        self._launch_ffmpeg_worker(worker, tool)

    def _launch_ffmpeg_worker(self, worker, tool) -> None:
        self.cancel_event.clear()
        self.progress_var.set(0)
        self.max_progress_seen = 0
        self.task_started_at = time.monotonic()
        self.task_tracker = FfmpegTaskTracker(self.app, [tool])
        self.task_tracker.start(tool)
        self._set_running_ui(True)
        threading.Thread(target=self._worker_wrapper, args=(worker,), daemon=True).start()

    def _worker_wrapper(self, worker) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            escolhido = getattr(self, "worker_acceleration", None)
            if escolhido is not None:
                # Encoder decidido na UI thread (GPU/CPU + codec + duracao).
                self.acceleration = escolhido
            elif hasattr(self, "selected_acceleration_label"):
                selected_label = self.selected_acceleration_label
                self.acceleration = getattr(self, "acceleration_by_label", {}).get(selected_label)
                if self.acceleration is None:
                    self.acceleration = self._available_accelerations()[0]
            else:
                self.acceleration = self._selected_acceleration()
            # F-16: só informa encoder de vídeo quando a ferramenta ativa realmente
            # produz um -c:v. Operações só de áudio/cópia não devem sugerir o contrário.
            tool_uses_video_encoder = getattr(self, "worker_tool_uses_video_encoder", None)
            if tool_uses_video_encoder is None:
                tool_uses_video_encoder = self._current_tool_uses_video_encoder()
            if tool_uses_video_encoder:
                quality = getattr(self, "selected_video_quality", None) or self.video_quality_var.get()
                self._set_status(f"Encoder selecionado: {self.acceleration.label}; qualidade: {quality}", 0)
            else:
                self._set_status("Encoder de vídeo: não aplicável", 0)
            worker()
            if not self.cancel_event.is_set():
                if getattr(self, "recovery_job", None): self.recovery_job.finish("complete")
                # Regra do usuário: a barra de status não repete "arquivo salvo";
                # a conclusão (verde) vai para o log de atividade.
                self._log_saved_output()
                elapsed = max(.001, time.monotonic() - self.task_started_at)
                encoder = self.acceleration.encoder if (self.acceleration and tool_uses_video_encoder) else "não aplicável"
                self.task_tracker.success(f"Tempo de processamento: {elapsed:.1f}s\nEncoder: {encoder}") if self.task_tracker else None
        except Cancelled:
            if getattr(self, "recovery_job", None): self.recovery_job.finish("cancelled")
            self._set_status("Operação cancelada.")
            if self.task_tracker: self.task_tracker.fail("Operação cancelada pelo usuário.")
        except Exception as exc:
            if getattr(self, "recovery_job", None): self.recovery_job.finish("failed")
            self._set_status(f"Erro: {exc}")
            if self.task_tracker: self.task_tracker.fail(str(exc))
        finally:
            self.root.after(0, lambda: self._set_running_ui(False))
            self.recovery_job = None

    def _offer_ffmpeg_recovery(self) -> None:
        from app_env import settings_path
        pending = RecoveryJob.pending(settings_path().parent / "ffmpeg_recovery")
        if self.running or not pending:
            return
        if not messagebox.askyesno("Retomar FFmpeg", "Há uma tarefa interrompida. Retomar reutiliza as etapas concluídas "
                                  "e refaz somente a etapa interrompida. Deseja retomar?"):
            return
        try:
            job = RecoveryJob.load(pending[0])
            request = job.state["request"]
            workers = {"Cortar": self._cut_worker, "Extrair áudio": self._extract_worker, "Girar vídeo": self._rotate_worker,
                       "Juntar áudios/vídeos": self._join_worker, "Inserir áudio": self._insert_worker, "Limpar áudio": self._clean_worker}
            worker = workers[request["tool"]]
            for name in ("cut_input", "rotate_input", "insert_main_input", "insert_secondary_input", "clean_input"):
                raw = request["fields"].get(name)
                setattr(self, name, Path(raw) if raw else None)
            self.extract_inputs = [Path(p) for p in request["fields"].get("extract_inputs", [])]
            self.join_inputs = [Path(p) for p in request["fields"].get("join_inputs", [])]
            self.join_media_profiles = {}
            self.cut_media_profile = self.rotate_media_profile = None
            self.worker_options = request["options"]
            self.insert_timeline.insertion = request["insertion"]
            self.selected_video_quality, self.selected_video_speed = request["quality"], request["speed"]
            self.selected_acceleration_label = request["encoder_label"]
            self.worker_acceleration = VideoAcceleration(**request["acceleration"]) if request.get("acceleration") else None
            self.worker_tool_uses_video_encoder = request["uses_encoder"]
            self.output_dir = Path(request["output_dir"])
            self.active_tool_var.set(request["tool"])
            self.output_dir_var.set(str(self.output_dir))
            self.recovery_job = job
            self._launch_ffmpeg_worker(worker, request["tool"])
        except (KeyError, OSError, ValueError) as error:
            messagebox.showerror("Retomar FFmpeg", f"Não foi possível retomar: {error}")

    def _work_directory(self, prefix: str, parent: Path) -> Path:
        job = getattr(self, "recovery_job", None)
        return job.directory(prefix + str(parent)) if job else parent / f"{prefix}_{uuid.uuid4().hex}"

    def _remove_work_directory(self, directory: Path) -> None:
        job = getattr(self, "recovery_job", None)
        if job and directory.resolve().is_relative_to(job.work_root.resolve()):
            return
        shutil.rmtree(directory, ignore_errors=True)

    def _work_file(self, parent: Path, prefix: str, extension: str) -> Path:
        job = getattr(self, "recovery_job", None)
        if job:
            return job.allocate("file:" + str(parent) + prefix + extension,
                                lambda: job.directory("manifests") / f"{prefix}{extension}")
        return parent / f"{prefix}_{uuid.uuid4().hex}{extension}"

    def _recoverable_output(self, base: Path, suffix: str, extension: str) -> Path:
        job = getattr(self, "recovery_job", None)
        factory = lambda: self._safe_output(base, suffix, extension)
        return job.allocate("output:" + str(base) + suffix + extension, factory) if job else factory()

    def _publish_completed_output(self, staged: Path, output: Path) -> None:
        job = getattr(self, "recovery_job", None)
        if job:
            job.publish(staged, output)
        else:
            staged.replace(output)

    def _validate_completed_output(self, path: Path, validate) -> None:
        """Uma saída concluída fica disponível mesmo com divergências na validação."""
        if self.cancel_event.is_set():
            raise Cancelled()
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError("O processamento não produziu um arquivo final utilizável.")
        try:
            validate()
        except Cancelled:
            raise
        except Exception as error:
            if self.cancel_event.is_set():
                raise Cancelled()
            warning = (f"Arquivo concluído com aviso: {error}\n"
                       "O arquivo será salvo. Confira o trecho indicado antes de usá-lo ou compartilhá-lo.")
            self._append_log(warning)
            self.root.after(0, lambda message=warning: messagebox.showwarning("Verificação do arquivo", message))

    def _worker_value(self, name: str, variable):
        options = getattr(self, "worker_options", None)
        if options and name in options:
            return options[name]
        return variable.get()

    def _worker_crop(self, key: str) -> tuple[int, int, int, int] | None:
        """Recorte por seleção capturado na UI thread (o worker usa valores simples)."""
        options = getattr(self, "worker_options", None) or {}
        raw = options.get(key)
        if not raw:
            return None
        try:
            x, y, largura, altura = (int(valor) for valor in raw)
        except (TypeError, ValueError):
            return None
        if largura < 2 or altura < 2:
            return None
        return x, y, largura, altura

    def _worker_value_default(self, name: str, variable_name: str, default):
        options = getattr(self, "worker_options", None)
        if options and name in options:
            return options[name]
        variable = getattr(self, variable_name, None)
        return variable.get() if variable is not None else default

    def cancel(self) -> None:
        if not self.running:
            return
        self.cancel_event.set()
        self._set_status("Cancelando...")
        with self.process_lock:
            process = self.current_process
        if process:
            try:
                process.terminate()
            except Exception:
                pass

    def shutdown(self) -> None:
        self.cancel()
        self._stop_preview()
        self.waveform_stop_event.set()
        self.waveform_executor.shutdown(wait=False, cancel_futures=True)
        with self.waveform_lock:
            processes = list(self.waveform_processes)
        for process in processes:
            if process.poll() is None:
                process.terminate()

    def _ffmpeg(self) -> Path:
        path = app_base_dir() / "ffmpeg.exe"
        if not path.exists():
            raise RuntimeError("ffmpeg.exe não foi encontrado na pasta do aplicativo")
        return path

    def _get_ffprobe(self) -> "Path | None":
        try:
            ffmpeg = self._ffmpeg()
            candidate = ffmpeg.parent / "ffprobe.exe"
            if candidate.exists():
                return candidate
            # Instalações antigas recebem o runtime interno pelo sync, mas
            # não recebem novos componentes na raiz (compatibilidade updater).
            candidate = ffmpeg.parent / "_internal" / "tools" / "ffprobe.exe"
            if candidate.is_file():
                return candidate
        except Exception:
            pass
        return None

    def _get_duration_only(self, path: "Path") -> float:
        ffprobe = self._get_ffprobe()
        if ffprobe:
            try:
                cmd = [
                    str(ffprobe), "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path)
                ]
                res = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    timeout=25
                )
                out = (res.stdout or "").strip()
                if out:
                    return float(out)
            except Exception:
                pass
        try:
            return self._probe_media(path).duration
        except Exception:
            return 0.0

    def _load_available_accelerations(self) -> None:
        profiles = self._available_accelerations()

        def apply() -> None:
            self.available_accelerations = profiles
            self.acceleration_by_label = {profile.label: profile for profile in profiles}
            # O combo principal agora escolhe ONDE processar (GPU/CPU); o encoder
            # concreto sai do catalogo sondado, por tarefa.
            if self.acceleration_var.get() not in PATH_LABELS.values():
                self.acceleration_var.set(PATH_LABELS[ENCODER_PATH_GPU])
            self._refresh_encoder_control_state()
            self._refresh_effective_encoder_label()

        self.root.after(0, apply)

    def _selected_acceleration(self) -> VideoAcceleration:
        selected = self.acceleration_by_label.get(self.acceleration_var.get())
        if selected:
            return selected
        profiles = self._available_accelerations()
        return profiles[0]


    def _available_accelerations(self) -> list[VideoAcceleration]:
        ffmpeg = self._ffmpeg()
        try:
            result = subprocess.run([str(ffmpeg), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            encoders = (result.stdout + result.stderr).lower()
        except Exception:
            encoders = ""
        return [self._catalog_video_acceleration(option) for option in self._probe_catalog(encoders)]

    def _probe_catalog(self, encoders: str) -> list[EncoderOption]:
        """Catalogo sondado de verdade: so entra o encoder que compila E funciona aqui."""
        opcoes: list[EncoderOption] = []
        for option in CATALOG:
            if option.encoder not in encoders:
                continue
            if option.key == "vaapi" and (os.name == "nt" or not Path("/dev/dri/renderD128").exists()):
                continue
            if not self._test_encoder(option):
                continue
            opcoes.append(option)
        self.available_encoder_options = opcoes
        return opcoes

    @staticmethod
    def _catalog_video_acceleration(option: EncoderOption) -> VideoAcceleration:
        chave = "cpu" if option.path == ENCODER_PATH_CPU else option.key
        return VideoAcceleration(chave, option.label, option.encoder)

    def _test_encoder(self, profile: VideoAcceleration) -> bool:
        command = [str(self._ffmpeg()), "-hide_banner", "-loglevel", "error"]
        if profile.key == "vaapi":
            command += ["-vaapi_device", "/dev/dri/renderD128"]
        command += ["-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1", "-frames:v", "1"]
        if profile.key == "vaapi":
            command += ["-vf", "format=nv12,hwupload"]
        command += ["-c:v", profile.encoder, "-f", "null", "-"]
        try:
            result = subprocess.run(command, capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _buffer_for_bitrate(bitrate: str) -> str:
        match = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmM])", bitrate.strip())
        if not match:
            return "2M"
        return f"{float(match.group(1)) * 2:g}{match.group(2)}"

    @staticmethod
    def _scaled_bitrate(bitrate: str, multiplier: float) -> str:
        match = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmM])", bitrate.strip())
        if not match:
            return bitrate
        value = float(match.group(1))
        unit = match.group(2).lower()
        if unit == "m":
            value *= 1000  # normaliza para kilobits antes de arredondar (evita colapso de "1M")
            unit = "k"
        return f"{max(1, round(value * multiplier))}{unit}"

    @staticmethod
    def _concat_escape(path_str: str) -> str:
        # Normaliza barras e escapa apóstrofos para o demuxer concat (`file '...'`).
        return path_str.replace(chr(92), "/").replace("'", "'\\''")

    def _encoder_help(self, encoder: str) -> str:
        cached = self.encoder_help.get(encoder)
        if cached is not None:
            return cached
        try:
            result = subprocess.run(
                [str(self._ffmpeg()), "-hide_banner", "-h", f"encoder={encoder}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            cached = (result.stdout + result.stderr).lower()
        except Exception:
            cached = ""
        self.encoder_help[encoder] = cached
        return cached

    def _encoder_supports(self, profile: VideoAcceleration, option: str) -> bool:
        return option.lower() in self._encoder_help(profile.encoder)

    # QVBR da AMD usa escala tipo QP: MENOR valor = MELHOR qualidade.
    AMF_QVBR_LEVELS = {"Máxima": 16, "Muito alta": 22, "Alta": 28, "Média": 34, "Econômica": 40}

    def _video_args(self, profile: VideoAcceleration, bitrate: str = "1M") -> list[str]:
        quality = getattr(self, "selected_video_quality", None)
        if not quality:
            quality = self.video_quality_var.get()
        hardware_scale = {"Máxima": 1.60, "Muito alta": 1.25, "Alta": 1.00, "Média": 0.70, "Econômica": 0.45}[quality]
        target_bitrate = self._scaled_bitrate(bitrate, hardware_scale)
        rate_control = ["-b:v", target_bitrate, "-maxrate", target_bitrate, "-bufsize", self._buffer_for_bitrate(target_bitrate)]
        speed = getattr(self, "selected_video_speed", None)
        if not speed:
            speed = self.video_speed_var.get() if hasattr(self, "video_speed_var") else "Equilibrada"
        preset = VIDEO_SPEED_PRESETS.get(speed, "fast")
        if profile.encoder == "libx264":
            crf = {"Máxima": 16, "Muito alta": 18, "Alta": 20, "Média": 23, "Econômica": 26}[quality]
            return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
        if profile.encoder == "libx265":
            crf = {"Máxima": 18, "Muito alta": 20, "Alta": 22, "Média": 25, "Econômica": 28}[quality]
            return ["-c:v", "libx265", "-preset", preset, "-crf", str(crf)]
        if profile.key == "nvenc":
            if self._encoder_supports(profile, "-cq") and self._encoder_supports(profile, "-rc"):
                cq = {"Máxima": 16, "Muito alta": 19, "Alta": 22, "Média": 25, "Econômica": 28}[quality]
                return ["-c:v", profile.encoder, "-preset", "p4", "-rc", "vbr", "-cq", str(cq), *rate_control]
            return ["-c:v", profile.encoder, "-preset", "p4", *rate_control]
        if profile.key == "qsv":
            # -global_quality é opção genérica do libavcodec (não aparece em `-h encoder=`),
            # então a detecção anterior nunca a encontrava. Emitir direto + rate_control.
            global_quality = {"Máxima": 17, "Muito alta": 20, "Alta": 23, "Média": 26, "Econômica": 29}[quality]
            return ["-c:v", profile.encoder, "-global_quality", str(global_quality), *rate_control]
        if profile.key == "amf":
            if self._encoder_supports(profile, "-qvbr_quality_level") and self._encoder_supports(profile, "-rc"):
                qvbr = self.AMF_QVBR_LEVELS[quality]
                return ["-c:v", profile.encoder, "-quality", "balanced", "-rc", "qvbr", "-qvbr_quality_level", str(qvbr), *rate_control]
            return ["-c:v", profile.encoder, "-quality", "balanced", *rate_control]
        if profile.key == "vaapi":
            return ["-c:v", profile.encoder, *rate_control]
        return ["-c:v", "mpeg4", *rate_control]

    def _filter_for_profile(self, filters: str, profile: VideoAcceleration) -> tuple[list[str], list[str]]:
        if profile.key == "vaapi":
            return ["-vaapi_device", "/dev/dri/renderD128"], ["-vf", f"{filters},format=nv12,hwupload"]
        return [], ["-vf", filters]

    def _execute(self, command: list[str], label: str, progress: int, total: int, duration_seconds: float = 0.0, progress_callback=None) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()
        job = getattr(self, "recovery_job", None)
        if job and job.can_reuse(command):
            self._append_log(f"Retomada: reutilizando {label} já concluído.")
            if self.task_tracker: self.task_tracker.complete(re.sub(r"/\d+", "", label))
            if progress_callback: progress_callback(100, "retomado")
            return
        if job: job.begin_step(command)
        tracker = self.task_tracker
        tracker_label = re.sub(r"/\d+", "", label)
        if tracker:
            tracker.start(tracker_label)
        self._set_status(f"{label} ({progress}/{total}) - {self.acceleration.label if self.acceleration else 'FFmpeg'}", int((progress - 1) * 100 / max(total, 1)))
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        output: list[str] = []
        # Every process has its own FFmpeg progress stream. There is no shared
        # callback pool, history buffer, or artificial ten-process ceiling.
        progress_command = [command[0], "-stats_period", "0.1", "-progress", "pipe:1", "-nostats", *command[1:]]
        self._record_ffmpeg_command(progress_command)
        process = subprocess.Popen(
            progress_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=flags,
        )
        stderr_lines: list[str] = []
        def read_stderr():
            if process.stderr:
                stderr_lines.extend(process.stderr.readlines())
        stderr_reader = threading.Thread(target=read_stderr, daemon=True)
        stderr_reader.start()
        try:
            with self.process_lock:
                self.current_process = process
            with self.app.process_lock:
                self.app.active_processes.add(process)
            fields: dict[str, str] = {}
            while process.poll() is None or (process.stdout and not process.stdout.closed):
                if self.cancel_event.is_set():
                    process.terminate()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired: process.kill()
                    raise Cancelled()
                line = process.stdout.readline() if process.stdout else ""
                if not line:
                    if process.poll() is not None: break
                    continue
                key, _, value = line.strip().partition("=")
                if key:
                    fields[key] = value
                if key == "progress":
                    raw_time = fields.get("out_time_us") or fields.get("out_time_ms") or "0"
                    try:
                        seconds = float(raw_time) / 1_000_000.0
                    except ValueError:
                        seconds = 0.0
                    percent = min(99, int(seconds * 100 / duration_seconds)) if duration_seconds else 0
                    speed = fields.get("speed", "").strip()
                    if tracker: tracker.start(tracker_label, percent, speed)
                    if progress_callback: progress_callback(percent, speed)
                    fields.clear()
            process.wait()
            stderr_reader.join(timeout=2)
            output = [line.rstrip() for line in stderr_lines]
        finally:
            with self.process_lock:
                self.current_process = None
            with self.app.process_lock:
                self.app.active_processes.discard(process)
            stderr_reader.join(timeout=2)
            if process.poll() is not None:
                if process.stdout: process.stdout.close()
                if process.stderr: process.stderr.close()
        if process.returncode != 0:
            detail = "\n".join(output[-8:]) or f"FFmpeg retornou código {process.returncode}"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            diagnostic = self.output_dir / f"ffmpeg_erro_{uuid.uuid4().hex}.log"
            try:
                diagnostic.write_text("\n".join(output), encoding="utf-8", errors="replace")
                detail += f"\n\nLog completo: {diagnostic}"
            except Exception:
                pass
            raise RuntimeError(detail)
        if tracker:
            tracker.complete(tracker_label)
        if job: job.complete_step(command)
        self._set_status(f"{label} concluído ({progress}/{total})", int(progress * 100 / max(total, 1)))

    def _cpu_encoder_for(self, encoder: str) -> VideoAcceleration:
        """CPU equivalente ao codec do encoder que falhou (HEVC -> libx265)."""
        codec = "hevc" if str(encoder or "").lower().startswith(("libx265", "hevc_")) else "h264"
        opcoes = [
            option for option in self.available_encoder_options
            if option.path == ENCODER_PATH_CPU and option.codec == codec
        ]
        if opcoes:
            return self._catalog_video_acceleration(opcoes[0])
        return next(
            (acc for acc in getattr(self, "available_accelerations", []) if acc.key == "cpu"),
            VideoAcceleration("cpu", "CPU", "libx264"),
        )

    def _execute_video(self, label: str, builder, progress: int = 1, total: int = 1, duration_seconds: float = 0.0, progress_callback=None, profile: VideoAcceleration | None = None) -> None:
        profile = profile or self.acceleration or self._cpu_encoder_for("libx264")
        try:
            self._execute(builder(profile), label, progress, total, duration_seconds, progress_callback)
        except RuntimeError as exc:
            if str(profile.key).startswith("cpu") or not self._is_hardware_encoder_error(str(exc)):
                raise
            cpu_fallback = self._cpu_encoder_for(profile.encoder)
            motivo = str(exc).strip().splitlines()[0] if str(exc).strip() else "erro do encoder"
            # NÃO troca a preferência do usuário: a próxima tarefa volta a tentar a GPU.
            self._log_encoder_choice(
                f"{profile.label} falhou ({motivo}); repetindo na CPU ({cpu_fallback.encoder}) SOMENTE nesta tarefa."
            )
            self._execute(builder(cpu_fallback), f"{label} (CPU)", progress, total, duration_seconds, progress_callback)

    @staticmethod
    def _is_hardware_encoder_error(message: str) -> bool:
        lower = message.lower()
        markers = (
            "nvenc", "cuda", "qsv", "mfx", "amf", "vaapi", "d3d11", "d3d12",
            "hardware device", "device setup failed", "encoder initialization",
            "initializing output stream", "no capable devices", "session limit",
        )
        return any(marker in lower for marker in markers)

    @staticmethod
    def _seconds(value: str, label: str, allow_empty: bool = False) -> float | None:
        value = value.strip().replace(",", ".")
        if not value and allow_empty:
            return None
        try:
            seconds = float(value)
        except ValueError as exc:
            raise RuntimeError(f"{label} deve ser um número em segundos") from exc
        if not math.isfinite(seconds):
            raise RuntimeError(f"{label} deve ser um número finito")
        if seconds < 0:
            raise RuntimeError(f"{label} não pode ser negativo")
        return seconds

    @staticmethod
    def _fmt_seconds(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    @staticmethod
    def _precise_seconds(value: float) -> str:
        return f"{value:.9f}".rstrip("0").rstrip(".") or "0"

    @staticmethod
    def _safe_output(base: Path, suffix: str, extension: str) -> Path:
        candidate = base / f"{suffix}{extension}"
        index = 2
        while candidate.exists():
            candidate = base / f"{suffix}_{index}{extension}"
            index += 1
        return candidate

    def _audio_codec_args(self, extension: str, bitrate: str) -> list[str]:
        ext = extension.lower().lstrip(".")
        if ext == "wav":
            return ["-c:a", "pcm_s16le", "-f", "wav"]
        if ext == "mp3":
            return ["-c:a", "libmp3lame", "-b:a", bitrate]
        if ext == "m4a":
            return ["-c:a", "aac", "-b:a", bitrate, "-movflags", "+faststart"]
        if ext == "aac":
            return ["-c:a", "aac", "-b:a", bitrate]
        if ext == "ogg":
            return ["-c:a", "libvorbis", "-b:a", bitrate]
        if ext == "opus":
            return ["-c:a", "libopus", "-application", "audio", "-b:a", bitrate, "-vbr", "on"]
        if ext == "flac":
            return ["-c:a", "flac"]
        if ext == "wma":
            return ["-c:a", "wmav2", "-b:a", bitrate]
        return ["-c:a", "aac", "-b:a", bitrate]

    @staticmethod
    def _audio_only_output_extension(source: Path) -> str:
        extension = source.suffix.lower()
        return extension if extension in AUDIO_EXTENSIONS else ".m4a"

    def _audio_codec_args_for_source_codec(self, codec: str, extension: str, bitrate: str) -> list[str] | None:
        codec = codec.lower()
        if codec == "aac":
            args = ["-c:a", "aac", "-b:a", bitrate]
            if extension.lower() == ".m4a":
                args += ["-movflags", "+faststart"]
            return args
        if codec == "mp3":
            return ["-c:a", "libmp3lame", "-b:a", bitrate]
        if codec == "alac":
            return ["-c:a", "alac", "-movflags", "+faststart"]
        if codec in {"vorbis", "libvorbis"}:
            return ["-c:a", "libvorbis", "-b:a", bitrate]
        if codec in {"opus", "libopus"}:
            return ["-c:a", "libopus", "-application", "audio", "-b:a", bitrate, "-vbr", "on"]
        if codec == "flac":
            return ["-c:a", "flac"]
        if codec == "wmav2":
            return ["-c:a", "wmav2", "-b:a", bitrate]
        if codec.startswith("pcm_") and extension.lower() == ".wav":
            return ["-c:a", codec, "-f", "wav"]
        return None

    @staticmethod
    def _join_audio_args(profile: dict) -> list[str]:
        return [
            "-c:a", "aac", "-b:a", profile["audio_bitrate"],
            "-ar", str(profile["audio_rate"]), "-ac", str(profile["audio_channels"]),
        ]

    def _cut_worker(self) -> None:
        source = self.cut_input
        if not source or not source.exists():
            raise RuntimeError("Selecione o arquivo para cortar")
        start = self._seconds(str(self._worker_value("cut_start", self.cut_start_var)), "Início") or 0.0
        end = self._seconds(str(self._worker_value("cut_end", self.cut_end_var)), "Fim")
        if end is None or end <= start:
            raise RuntimeError("O fim deve ser maior que o início")
        duration = end - start
        media = self._probe_media(source)
        if media.duration > 0 and (start >= media.duration - 0.001 or end > media.duration + 0.05):
            raise RuntimeError(f"O intervalo excede a duração do arquivo ({self._clock(media.duration)}).")
        is_video = media.has_video
        cut_mode_var = getattr(self, "cut_mode_var", None)
        if getattr(self, "worker_options", None) and "cut_mode" in self.worker_options:
            cut_mode = str(self.worker_options["cut_mode"])
        else:
            cut_mode = str(cut_mode_var.get()) if cut_mode_var is not None else CUT_MODE_SMART
        fast_copy = cut_mode.startswith(CUT_MODE_COPY)
        smart_cut = not fast_copy and not cut_mode.startswith(CUT_MODE_REENCODE)
        crop = self._worker_crop("cut_crop")
        if crop and fast_copy:
            # A seleção de área exige reencodar (copiar streams não recorta pixels).
            self._append_log("A seleção de área exige reencodar: usando o Reencode Completo.")
            fast_copy = False
            smart_cut = False
        elif crop and smart_cut:
            # O miolo copiado não pode ser recortado: com seleção, reencoda tudo.
            self._append_log("A seleção de área exige reencodar todo o trecho: usando o Reencode Completo.")
            smart_cut = False
        audio_policy = str(self._worker_value_default("cut_audio_policy", "cut_audio_policy_var", "Precisão máxima (AAC)"))
        stream_policy = str(self._worker_value_default("cut_stream_policy", "cut_stream_policy_var", "Vídeo e áudio"))
        preserve_all_streams = fast_copy and stream_policy.startswith("Todos os streams")
        if is_video:
            extension = self._metadata_rotate_output_suffix(source.suffix) if fast_copy else ".mp4"
        else:
            extension = self._audio_only_output_extension(source)
        output = self._recoverable_output(self.output_dir, f"{source.stem}_cortado", extension)

        if not fast_copy and is_video:
            aviso_cor = color_depth_warning(getattr(media, "pix_fmt", ""))
            if aviso_cor and not smart_cut:
                self._append_log(aviso_cor)
        if fast_copy:
            self._append_log(
                "Corte rápido: codecs preservados; os limites são aproximados ao keyframe/pacote disponível."
            )
            # F6: declarar o intervalo EFETIVO (pedido x entregue) E ancorar o
            # seek no keyframe: cortar no meio do GOP deixa o começo do arquivo
            # sem keyframe (medido: os primeiros quadros saíam P, com o primeiro
            # keyframe em 0,6 s). Copiar streams só é fiel a partir de um keyframe.
            inicio_efetivo = start
            if is_video:
                try:
                    keyframes = self._extract_keyframes(source)
                except Exception:
                    keyframes = []
                inicio_efetivo = copy_effective_start_seconds(start, keyframes)
                self._append_log(
                    copy_interval_message(start, start + duration, inicio_efetivo)
                )
            duracao_efetiva = max(0.01, (start + duration) - inicio_efetivo)
            command = [
                str(self._ffmpeg()), "-hide_banner", "-y", "-ss", self._fmt_seconds(inicio_efetivo),
                "-i", str(source), "-t", self._fmt_seconds(duracao_efetiva),
            ]
            if is_video:
                if preserve_all_streams:
                    command += ["-map", "0", "-c", "copy"]
                else:
                    command += [
                        "-map", "0:v:0", "-map", "0:a?", "-sn", "-dn", "-c", "copy",
                    ]
                if output.suffix.lower() in {".mp4", ".mov", ".m4v"}:
                    command += ["-movflags", "+faststart"]
            else:
                command += ["-map", "0:a:0", "-vn", "-c", "copy"]
            command.append(str(output))
            self._execute(command, "Cortando sem reencodar", 1, 1, duration)
        elif is_video and smart_cut:
            self._cut_video_smartcut(
                source, output, start, end, media,
                audio_precise=not audio_policy.startswith("Copiar áudio"),
            )
        elif is_video:
            self._cut_video_precise(
                source, output, start, end, media,
                copy_audio=audio_policy.startswith("Copiar áudio"),
                crop=crop,
            )
        else:
            if smart_cut:
                self._append_log("SmartCut de áudio: mesmo corte por amostras do Reencode Completo; uma passagem contínua, sem emendas.")
            self._cut_audio_precise(source, output, start, end, media)

    @staticmethod
    def _smartcut_codec_family(media: MediaProfile) -> str | None:
        """Família de codec aceita pelo SmartCut (concat por TS exige mp4toannexb)."""
        codec = (media.video_codec or "").lower()
        if codec in ("h264", "avc1", "avc"):
            return "h264"
        if codec in ("hevc", "h265", "hvc1", "hev1"):
            return "hevc"
        return None

    def _worker_encoder_inputs(self) -> tuple[str, str, list[EncoderOption]]:
        """Preferência (GPU/CPU + Avançado) e catálogo sondado, vindos da UI thread."""
        options = getattr(self, "worker_options", None) or {}
        path = str(options.get("encoder_path") or ENCODER_PATH_GPU)
        advanced = str(options.get("encoder_advanced") or ENCODER_ADVANCED_AUTO)
        return path, advanced, options_from_tuples(options.get("encoder_options"))

    def _smartcut_edge_encoder(self, codec_family: str, segundos: float = 0.0) -> VideoAcceleration | None:
        """Encoder das bordas: tem que produzir o MESMO codec do trecho copiado.

        O miolo copiado manda no codec; a escolha GPU/CPU segue a mesma regra do
        resto do app (preferência do usuário, Avançado e o custo de inicialização
        da GPU no tamanho DESTE trecho).
        """
        path, advanced, disponiveis = self._worker_encoder_inputs()
        if disponiveis:
            escolha = resolve_encoder(
                codec=codec_family,
                path=path,
                available=disponiveis,
                advanced=advanced,
                seconds=segundos,
            )
            if escolha is not None:
                if segundos:
                    self._log_encoder_choice(
                        f"Encoder da borda ({segundos:.2f}s): {escolha.option.encoder} — {escolha.reason}"
                    )
                return VideoAcceleration(escolha.option.key, escolha.option.label, escolha.option.encoder)
        aceleracao = self._smart_join_acceleration_for_codec(codec_family)
        encoder = (aceleracao.encoder or "").lower()
        if codec_family == "h264" and not encoder.startswith(("libx264", "h264_")):
            return None
        if codec_family == "hevc" and not encoder.startswith(("libx265", "hevc_")):
            return None
        return aceleracao

    def _cut_audio_precise(self, source: Path, output: Path, start: float, end: float, media: MediaProfile) -> None:
        """SmartCut e Reencode Completo de áudio compartilham o mesmo corte.

        Emendas de áudio comprimido podem acrescentar priming/padding e exigir
        novos parâmetros de decoder. Uma passagem contínua evita essas perdas.
        """
        work = self._work_directory("audio_cut", output.parent)
        work.mkdir(parents=True, exist_ok=True)
        staged = work / output.name
        try:
            codec = self._audio_codec_args_for_source_codec(media.audio_codec, output.suffix, media.audio_bitrate)
            codec = codec or self._audio_codec_args(output.suffix, media.audio_bitrate)
            samples = max(1, round((end - start) * media.audio_rate))
            command = [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", self._precise_seconds(start),
                       "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn",
                       "-af", f"apad,atrim=end_sample={samples},asetpts=N/SR/TB",
                       *codec, "-map_metadata", "0", "-map_chapters", "-1", str(staged)]
            self._execute(command, "Cortando áudio com precisão", 1, 1, end - start)
            if self._get_ffprobe():
                self._validate_completed_output(staged, lambda: self._smartcut_validate_audio(self._smart_join_probe(staged), end - start, 1))
            if self.cancel_event.is_set():
                raise Cancelled()
            self._publish_completed_output(staged, output)
        finally:
            self._remove_work_directory(work)

    @staticmethod
    def _smartcut_validate_audio(info: dict, duration: float, tracks: int, copied: bool = False) -> None:
        streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
        if len(streams) != tracks:
            raise RuntimeError("SmartCut: a quantidade de faixas de áudio mudou.")
        for stream in streams:
            rate = int(stream.get("sample_rate") or 48000)
            codec = stream.get("codec_name", "")
            lossless = codec.startswith("pcm_") or codec in {"alac", "flac"}
            tolerance = max(.002, (1 if lossless else 4096) / rate)
            actual = float(stream.get("duration") or info.get("format", {}).get("duration") or 0)
            offset = float(stream.get("start_time") or 0)
            valid = (offset >= -.1 and actual > 0 and offset + actual <= duration + .1) if copied else (
                abs(actual - duration) <= tolerance and abs(offset) <= tolerance
            )
            if not math.isfinite(actual) or not math.isfinite(offset) or not valid:
                raise RuntimeError(f"SmartCut: duração ou início incorretos na faixa de áudio ({offset:.3f}s / {actual:.3f}s).")

    def _smartcut_segment_arguments(
        self, source: Path, segment: Path, start: float, duration: float,
        media: MediaProfile, codec_family: str, reencode: bool,
        audio_precise: bool = True, encoder: VideoAcceleration | None = None,
        frame_count: int | None = None, b_frames: int = 0,
        seek_offset: float = 0.0, leading_frames: int = 0,
        color: dict | None = None,
        decode_seek: float | None = None, packet_start: int | None = None,
    ) -> list[str]:
        """Vídeo somente: pacotes exatos no corpo; timestamps originais nas bordas."""
        seek = start if decode_seek is None else decode_seek
        args = [str(self._ffmpeg()), "-hide_banner", "-y", "-noautorotate", "-display_rotation:v:0", "0"]
        if packet_start is None:
            args += ["-ss", self._precise_seconds(seek + seek_offset)]
        args += ["-i", str(source), "-map", "0:v:0", "-an"]
        if frame_count is not None:
            args += ["-frames:v", str(frame_count)]
        else:
            args += ["-t", self._precise_seconds(duration)]
        if reencode:
            chosen = encoder or self._smartcut_edge_encoder(codec_family) or self._smart_join_acceleration_for_codec(codec_family)
            args += self._video_args(chosen, media.video_bitrate)
            filters = ["settb=AVTB",
                       f"trim=start={self._precise_seconds(start - seek)}:end={self._precise_seconds(start - seek + duration)}",
                       "setpts=PTS-STARTPTS"]
            if media.sar and media.sar not in ("1:1", "0:1", "N/A", ""):
                filters.append(f"setsar={media.sar.replace(':', '/')}")
            args += ["-vf", ",".join(filters), "-pix_fmt", media.pix_fmt or "yuv420p",
                     "-fps_mode", "passthrough", "-enc_time_base", "1/90000", "-bf", str(b_frames)]
            if frame_count:
                args += ["-force_key_frames", f"expr:eq(n,{frame_count - 1})"]
                if codec_family == "hevc":
                    if chosen.encoder in {"libx265", "hevc_nvenc"}:
                        args += ["-forced-idr", "1"]
                    elif chosen.encoder in {"hevc_qsv", "hevc_amf"}:
                        args += ["-forced_idr", "1"]
            for key in ("color_primaries", "color_trc", "colorspace", "color_range"):
                value = (color or {}).get(key)
                if value and value not in {"unknown", "unspecified", "reserved"}:
                    args += [f"-{key}", str(value)]
        else:
            args += ["-c:v", "copy"]
        args += ["-map_metadata", "-1", "-avoid_negative_ts", "disabled"]
        if segment.suffix.lower() == ".ts":
            bsf = self._smart_join_ts_bitstream(codec_family)
            if packet_start is not None:
                bsf += f",noise=drop='lt(n,{packet_start})',setts=pts=PTS-{self._precise_seconds(start + seek_offset)}/TB:dts=DTS-{self._precise_seconds(start + seek_offset)}/TB"
            if leading_frames:
                bsf += ",noise=drop='lt(pts,0)'"
            args += ["-bsf:v", bsf, "-mpegts_flags", "+resend_headers+initial_discontinuity",
                     "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts"]
        else:
            args += ["-video_track_timescale", "90000", "-movflags", "+faststart"]
        return args + [str(segment)]

    def _cut_video_smartcut(
        self, source: Path, output: Path, start: float, end: float,
        media: MediaProfile, audio_precise: bool = True,
    ) -> None:
        """Copia GOPs completos; recodifica bordas e valida antes de publicar."""
        family = self._smartcut_codec_family(media)
        def full(reason):
            self._append_log(f"SmartCut: {reason}; usando Reencode Completo.")
            self._cut_video_precise(source, output, start, end, media, copy_audio=not audio_precise)
        if not family:
            full("o codec não permite emendas em stream copy")
            return
        if not self._get_ffprobe():
            full("FFprobe não está disponível para planejar a cópia com segurança")
            return
        info = self._smart_join_probe(source, packets=True)
        stream = info["streams"][0]
        fps = float(Fraction(stream.get("r_frame_rate") or media.fps))
        try:
            plan = smart_cut_planner.plan(info, start, end, fps)
        except ValueError as exc:
            raise RuntimeError(f"SmartCut: {exc}") from exc
        if not any(s.copy for s in plan.segments):
            full("o intervalo não contém um GOP completo copiável")
            return
        if any(not s.copy for s in plan.segments) and self._smartcut_edge_encoder(family) is None:
            full("o encoder selecionado não produz o mesmo codec do arquivo")
            return
        delay = max(s.decode_delay for s in plan.segments if s.copy)
        b_frames = int(stream.get("has_b_frames") or 0)
        if family == "hevc":
            b_frames = max(b_frames, math.ceil(delay * fps - 1e-6))
        media = replace(media, fps=stream.get("r_frame_rate") or media.fps,
                        pix_fmt=stream.get("pix_fmt") or media.pix_fmt)
        copied = sum(s.frames for s in plan.segments if s.copy)
        self._append_log(f"SmartCut: {copied}/{len(plan.timestamps)} quadros em cópia; somente as bordas serão recodificadas.")
        if media.has_audio:
            self._append_log("SmartCut: áudio contínuo da fonte, " + ("cortado por amostras em AAC." if audio_precise else "copiado nos limites de pacote."))
        work = self._work_directory("smartcut", output.parent)
        work.mkdir(parents=True, exist_ok=True)
        staged = work / output.name
        steps = len(plan.segments) * 2 + 1
        try:
            prepared = []
            step = 0
            # Primeiro codificar as bordas: o maior atraso realmente produzido
            # também participa do alinhamento DTS dos corpos copiados.
            for i, segment in enumerate(plan.segments):
                if self.cancel_event.is_set():
                    raise Cancelled()
                path = work / f"{i:02d}.mp4"
                if not segment.copy:
                    step += 1
                    encoder = self._smartcut_edge_encoder(family, segment.end - segment.start)
                    def build_edge(candidate):
                        return self._smartcut_segment_arguments(
                            source, path, segment.start, segment.end - segment.start, media, family, True,
                            encoder=candidate, frame_count=segment.frames, b_frames=b_frames,
                            seek_offset=plan.seek_offset, decode_seek=segment.decode_seek,
                            color={"colorspace": stream.get("color_space"), "color_trc": stream.get("color_transfer"),
                                   **{k: stream.get(k) for k in ("color_primaries", "color_range")}},
                        )
                    self._execute_video("Reencodando a borda inicial" if i == 0 else "Reencodando a borda final",
                                        build_edge, step, steps, segment.end - segment.start, profile=encoder)
                    encoded_delay = self._smart_join_encoded_delay(path)
                    delay = max(delay, encoded_delay)
                else:
                    encoded_delay = segment.decode_delay
                prepared.append((segment, path, encoded_delay))
            pieces = []
            for i, (segment, path, piece_delay) in enumerate(prepared):
                step += 1
                ts = work / f"{i:02d}.ts"
                if segment.copy:
                    cmd = self._smartcut_segment_arguments(
                        source, ts, segment.start, segment.end - segment.start, media, family, False,
                        frame_count=segment.frames, seek_offset=plan.seek_offset, leading_frames=segment.leading,
                    )
                    shift = delay - piece_delay
                    if shift > 1e-6:
                        ix = cmd.index("-bsf:v") + 1
                        cmd[ix] += f",setts=pts=PTS:dts=DTS-{self._precise_seconds(shift)}/TB"
                    label = "Copiando o miolo"
                else:
                    cmd = self._smart_join_ts_arguments(path, ts, family, False, decode_delay=delay - piece_delay)
                    label = "Preparando a borda"
                self._execute(cmd, label, step, steps, segment.end - segment.start)
                if segment.copy:
                    expected_piece = [t - segment.start for t in plan.timestamps
                                      if segment.start - 1e-6 <= t < segment.end - 1e-6]
                    actual_piece = sorted(float(p["pts_time"]) for p in self._smart_join_probe(ts, packets=True).get("packets", []))
                    if len(actual_piece) != len(expected_piece) or any(abs(a - b) > .0001 for a, b in zip(actual_piece, expected_piece)):
                        # Alguns índices MP4/VFR fazem seek no GOP anterior.
                        # Refazer a cópia por índice de pacote evita recodificar
                        # o corpo ou aceitar conteúdo errado com PTS rebased.
                        self._append_log("SmartCut: índice de seek impreciso; copiando pelos índices reais dos pacotes.")
                        cmd = self._smartcut_segment_arguments(
                            source, ts, segment.start, segment.end - segment.start, media, family, False,
                            frame_count=segment.frames, seek_offset=plan.seek_offset,
                            leading_frames=segment.leading, packet_start=segment.packet_start,
                        )
                        if delay - piece_delay > 1e-6:
                            ix = cmd.index("-bsf:v") + 1
                            cmd[ix] += f",setts=pts=PTS:dts=DTS-{self._precise_seconds(delay - piece_delay)}/TB"
                        self._execute(cmd, label, step, steps, segment.end - segment.start)
                self._smart_join_validate_piece(ts, {"codec_family": family, "width": media.width, "height": media.height})
                pieces.append(ts)
            manifest = work / "lista.txt"
            manifest.write_text("\n".join(
                f"file '{self._concat_escape(str(path.resolve()))}'\nduration {self._precise_seconds(s.end - s.start)}"
                for path, s in zip(pieces, plan.segments)), encoding="utf-8")
            total = end - start
            gap = self._precise_seconds(plan.first_gap)
            limit = self._precise_seconds(total)
            audio_origin = float(info.get("format", {}).get("start_time", 0)) + start
            concat = [str(self._ffmpeg()), "-hide_banner", "-y", "-copyts"]
            if not audio_precise:
                concat += ["-itsoffset", self._precise_seconds(-audio_origin)]
            concat += ["-ss", self._precise_seconds(start), "-i", str(source),
                      "-display_rotation:v:0", str(media.rotation or 0),
                      "-f", "concat", "-safe", "0", "-i", str(manifest), "-map", "1:v:0"]
            if media.has_audio:
                concat += ["-map", "0:a?"]
                if audio_precise:
                    concat += ["-af", f"asetpts=PTS-{self._precise_seconds(audio_origin)}/TB,aresample=async=1:first_pts=0,apad,atrim=duration={limit},asetpts=N/SR/TB",
                               *self._precise_audio_args(media)]
                else:
                    concat += ["-c:a", "copy"]
            else:
                concat += ["-an"]
            concat += ["-c:v", "copy", "-bsf:v",
                       f"setts=pts=PTS+{gap}/TB:dts='if(eq(N,0),DTS+{gap}/TB,max(DTS+{gap}/TB,PREV_OUTDTS+1))':duration='min(DURATION,max(1,{limit}/TB-(PTS+{gap}/TB)))'",
                       "-avoid_negative_ts", "disabled", "-t", limit,
                       "-max_interleave_delta", "0", "-video_track_timescale", "90000",
                       "-movie_timescale", "90000",
                       "-movflags", "+faststart", "-map_metadata", "0", "-map_chapters", "-1"]
            if family == "hevc":
                concat += ["-tag:v", "hev1"]
            self._execute(concat + [str(staged)], "Montando o arquivo final", steps, steps, total)
            def validate_final():
                result = self._smart_join_probe(staged, packets=True)
                actual = sorted(float(p["pts_time"]) for p in result.get("packets", []))
                expected = [t - start for t in plan.timestamps]
                if len(actual) != len(expected) or any(abs(a - b) > .0001 for a, b in zip(actual, expected)):
                    raise RuntimeError("SmartCut: a saída não contém exatamente os quadros e timestamps escolhidos.")
                dts = [float(p["dts_time"]) for p in result["packets"]]
                if any(b <= a for a, b in zip(dts, dts[1:])):
                    raise RuntimeError("SmartCut: timestamps de decodificação fora de ordem.")
                self._smartcut_validate_audio(self._smart_join_probe(staged), total,
                                              (media.audio_streams or 1) if media.has_audio else 0, not audio_precise)
                position = plan.first_gap
                for s in plan.segments:
                    if not s.copy:
                        self._smart_join_validate_decoded_junction(staged, position, s.end - s.start, fps)
                    position += s.end - s.start
            self._validate_completed_output(staged, validate_final)
            if self.cancel_event.is_set():
                raise Cancelled()
            self._publish_completed_output(staged, output)
        finally:
            self._remove_work_directory(work)

    def _cut_video_precise(
        self, source: Path, output: Path, start: float, end: float, media: MediaProfile,
        copy_audio: bool = False, crop: tuple[int, int, int, int] | None = None,
    ) -> None:
        """Corte integral com os mesmos limites de apresentação do SmartCut."""
        if crop:
            self._append_log(f"Recorte por seleção: {selection_crop_label(crop)}.")
        if media.audio_streams > 1:
            action = "copiadas nos limites de pacote" if copy_audio else "preservadas e reencodadas em AAC"
            self._append_log(f"{source.name} possui {media.audio_streams} faixas de áudio; todas serão {action}.")
        if media.subtitle_streams or media.data_streams:
            self._append_log("Legendas, anexos, streams de dados e capítulos não são preservados no corte MP4.")
        if copy_audio and media.has_audio:
            self._append_log("O vídeo será cortado com precisão; o áudio será copiado nos limites de pacote disponíveis.")
        info = self._smart_join_probe(source, packets=True) if self._get_ffprobe() else None
        anchor, seek_offset = 0.0, 0.0
        plan = None
        if info:
            stream = info["streams"][0]
            fps = float(Fraction(stream.get("r_frame_rate") or media.fps))
            try:
                plan = smart_cut_planner.plan(info, start, end, fps)
            except ValueError as exc:
                raise RuntimeError(f"Corte: {exc}") from exc
            origin = float(stream.get("start_time", 0))
            anchor = max((float(p["pts_time"]) - origin for p in info["packets"]
                          if "K" in p.get("flags", "") and float(p["pts_time"]) - origin < start - 1e-6), default=0.0)
            seek_offset = plan.seek_offset
        delta = start - anchor
        limit = self._precise_seconds(end - start)
        work = self._work_directory("precise_cut", output.parent)
        work.mkdir(parents=True, exist_ok=True)
        staged = work / output.name
        def build(profile: VideoAcceleration):
            filters = ["settb=AVTB",
                       f"trim=start={self._precise_seconds(delta)}:end={self._precise_seconds(delta + end - start)}",
                       f"setpts=PTS-{self._precise_seconds(delta)}/TB"]
            if crop:
                filters.append(selection_crop_filter(crop))
            input_args, filter_args = self._filter_for_profile(",".join(filters), profile)
            command = [str(self._ffmpeg()), "-hide_banner", "-y", *input_args,
                       "-ss", self._precise_seconds(anchor + seek_offset), "-i", str(source),
                       "-ss", self._precise_seconds(start), "-i", str(source),
                       "-map", "0:v:0", "-map", "1:a?", "-sn", "-dn", *filter_args,
                       *self._video_args(profile, media.video_bitrate),
                       *hevc_tag_arguments(profile.encoder, output.suffix),
                       "-fps_mode", "passthrough", "-enc_time_base", "1/90000",
                       "-bsf:v", f"setts=pts=PTS:dts=DTS:duration='min(DURATION,max(1,{limit}/TB-PTS))'"]
            if copy_audio:
                command += ["-c:a", "copy"]
            elif media.has_audio:
                command += ["-af", f"aresample=async=1:first_pts=0,apad,atrim=duration={limit},asetpts=N/SR/TB",
                            *self._precise_audio_args(media)]
            else:
                command += ["-an"]
            return command + ["-t", limit, "-avoid_negative_ts", "disabled", "-map_metadata", "0",
                              "-map_chapters", "-1", "-video_track_timescale", "90000", "-movie_timescale", "90000",
                              "-movflags", "+faststart", str(staged)]
        try:
            self._execute_video("Cortando vídeo com precisão", build, duration_seconds=end - start)
            def validate_final():
                if info:
                    result = self._smart_join_probe(staged, packets=True)
                    actual = sorted(float(p["pts_time"]) for p in result.get("packets", []))
                    expected = [t - start for t in plan.timestamps]
                    if len(actual) != len(expected) or any(abs(a - b) > .0001 for a, b in zip(actual, expected)):
                        raise RuntimeError("Corte: o encoder não preservou os quadros/timestamps escolhidos.")
                    self._smartcut_validate_audio(self._smart_join_probe(staged), end - start,
                                                  (media.audio_streams or 1) if media.has_audio else 0, copy_audio)
            self._validate_completed_output(staged, validate_final)
            if self.cancel_event.is_set():
                raise Cancelled()
            self._publish_completed_output(staged, output)
        finally:
            self._remove_work_directory(work)

    def _extract_keyframes(self, source: Path) -> list[float]:
        command = [str(self._ffmpeg()), "-hide_banner", "-skip_frame", "nokey", "-i", str(source),
            "-vf", "showinfo", "-an", "-f", "null", "-",
        ]
        self._record_ffmpeg_command(command, probe=True)
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if self.cancel_event.is_set():
            raise Cancelled()
        keyframes = [float(value) for value in re.findall(r"pts_time:([\d.]+)", result.stdout + result.stderr)]
        return sorted(set(keyframes))

    def _extract_worker(self) -> None:
        if not self.extract_inputs:
            raise RuntimeError("Selecione ao menos um arquivo")
        extension = str(self._worker_value("extract_extension", self.extract_extension_var)).lower()
        start = self._seconds(str(self._worker_value("extract_start", self.extract_start_var)), "Início", True)
        end = self._seconds(str(self._worker_value("extract_end", self.extract_end_var)), "Fim", True)
        if (start is None) != (end is None):
            raise RuntimeError("Informe início e fim para usar o recorte")
        if start is not None and end is not None and end <= start:
            raise RuntimeError("O fim deve ser maior que o início")
        rate = str(self._worker_value("extract_rate", self.extract_rate_var))
        channels = str(self._worker_value("extract_channels", self.extract_channels_var))
        bitrate = str(self._worker_value("extract_bitrate", self.extract_bitrate_var))
        if extension == "opus" and rate not in {"8000", "12000", "16000", "24000", "48000"}:
            rate = "48000"
        if extension == "ogg":
            try:
                r_int = int(rate)
                c_int = int(channels)
            except ValueError:
                r_int, c_int = 48000, 2
            channel_map = self.VORBIS_VALID_BITRATES.get(c_int, self.VORBIS_VALID_BITRATES[2])
            allowed = channel_map.get(r_int, ("48k", "64k", "96k", "128k"))
            if bitrate not in allowed:
                self._append_log(
                    f"Bitrate Vorbis ajustado de {bitrate} para {allowed[0]} para {rate} Hz/{channels} canal(is)."
                )
                bitrate = allowed[0]
        total = len(self.extract_inputs)
        processed = 0
        audio_candidates = 0
        for index, source in enumerate(self.extract_inputs, start=1):
            if not source.exists():
                raise RuntimeError(f"Arquivo não encontrado: {source.name}")
            media = self._probe_media(source)
            if not media.has_audio:
                self._append_log(f"{source.name} não possui trilha de áudio e foi ignorado.")
                continue
            audio_candidates += 1
            effective_end = end
            if start is not None and end is not None:
                dur = media.duration
                if dur > 0 and start >= dur - 0.001:
                    self._append_log(f"{source.name} foi ignorado: o início do recorte excede sua duração ({self._clock(dur)}).")
                    continue
                effective_end = min(end, dur) if dur > 0 else end
                if effective_end + 0.001 < end:
                    self._append_log(
                        f"{source.name}: fim ajustado de {self._clock(end)} para {self._clock(effective_end)}."
                    )
            has_trim = start is not None and end is not None and (
                start > 0.001 or media.duration <= 0 or effective_end < media.duration - 0.05
            )
            output = self._recoverable_output(self.output_dir, f"{source.stem}_audio", f".{extension}")
            # F4b: quando o pedido é o próprio stream, extrair é COPIAR (sem
            # perdas) — o Android já fazia assim; aqui sempre reencodava.
            copiar = extract_can_copy(media, extension, rate, channels, has_trim=has_trim)
            command = [str(self._ffmpeg()), "-hide_banner", "-y"]
            if has_trim and start is not None:
                command += ["-ss", self._fmt_seconds(start)]
            command += ["-i", str(source)]
            if has_trim and start is not None and effective_end is not None:
                command += ["-t", self._fmt_seconds(effective_end - start)]
            if copiar:
                self._append_log(
                    f"{source.name}: cópia sem reencodar (mesmo codec, taxa e canais do original)."
                )
                command += ["-vn", "-map", "0:a:0?", "-c:a", "copy", str(output)]
            else:
                command += ["-vn", "-map", "0:a:0?", "-ar", rate, "-ac", channels, *self._audio_codec_args(extension, bitrate), str(output)]
            target_duration = (effective_end - start) if has_trim and start is not None and effective_end is not None else media.duration
            rotulo = "Copiando áudio sem reencodar" if copiar else f"Extraindo {source.name}"
            self._execute(command, rotulo, index, total, max(0.0, target_duration))
            processed += 1
        if processed == 0:
            if audio_candidates:
                raise RuntimeError("Nenhum arquivo coube no intervalo de recorte solicitado.")
            raise RuntimeError("Nenhum dos arquivos selecionados possui trilha de áudio.")

    @staticmethod
    def _metadata_rotate_output_suffix(input_suffix: str) -> str:
        # Preserva o container de origem no modo "somente metadados", evitando que
        # -map 0 -c copy quebre no muxer MP4 com legendas/áudio incompatíveis (MKV/WebM).
        s = input_suffix.lower()
        return s if s in {".mp4", ".mkv", ".webm", ".mov", ".m4v"} else ".mp4"

    def _validate_mp4_copy_codecs(self, media: MediaProfile) -> None:
        video_ok = media.video_codec in self._MP4_SAFE_VIDEO_CODECS or not media.video_codec
        audio_ok = media.audio_codec in self._MP4_SAFE_AUDIO_CODECS or not media.has_audio
        if not (video_ok and audio_ok):
            raise RuntimeError(
                f"Os codecs do arquivo ({media.video_codec or 'sem vídeo'}/"
                f"{media.audio_codec or 'sem áudio'}) não podem ser copiados para MP4 sem reencodar. "
                "Aplique um giro/espelhamento com reencode ou use um container compatível."
            )

    def _rotate_worker(self) -> None:
        source = self.rotate_input
        if not source or not source.exists():
            raise RuntimeError("Selecione o vídeo para girar")
        try:
            degrees = int(self._worker_value("rotate_degrees", self.rotate_degrees_var))
        except ValueError as exc:
            raise RuntimeError("Selecione um giro válido") from exc
        media = self._probe_media(source)
        aviso_cor = color_depth_warning(getattr(media, "pix_fmt", ""))
        if aviso_cor:
            self._append_log(aviso_cor)
        if not media.has_video:
            raise RuntimeError("O arquivo selecionado não possui uma faixa de vídeo.")
        start = self._seconds(str(self._worker_value("rotate_start", self.rotate_start_var)), "Início") or 0.0
        end = self._seconds(str(self._worker_value("rotate_end", self.rotate_end_var)), "Fim")
        if end is None:
            end = media.duration
        if start < 0 or end <= start or (media.duration > 0 and end > media.duration + 0.05):
            raise RuntimeError("O intervalo de recorte é inválido")
        has_trim = start > 0.001 or (media.duration > 0 and end < media.duration - 0.05)
        trim_duration = end - start
        suffix = f"{source.stem}_girado_cortado" if has_trim else f"{source.stem}_girado"
        output = self._recoverable_output(self.output_dir, suffix, ".mp4")
        seek_args = ["-ss", self._fmt_seconds(start)] if has_trim else []
        duration_args = ["-t", self._fmt_seconds(trim_duration)] if has_trim else []
        crop = self._worker_crop("rotate_crop")
        if crop:
            self._append_log(
                f"Recorte por seleção: {selection_crop_label(crop)}."
            )
        metadata_mode = bool(self._worker_value("rotate_metadata", self.rotate_metadata_var))
        if crop and metadata_mode:
            self._append_log("A seleção de área exige reencodar: o modo somente metadados não será usado.")
            metadata_mode = False
        if metadata_mode:
            if has_trim:
                self._append_log("Modo somente metadados com recorte: o corte é alinhado aos keyframes mais próximos (sem reencodar).")
            # A UI usa +90 como giro horário (transpose=1), enquanto
            # -display_rotation usa ângulo positivo anti-horário.
            target_rotation = (media.rotation - degrees) % 360
            output = self._recoverable_output(self.output_dir, suffix, self._metadata_rotate_output_suffix(source.suffix))
            # F-02/F-03: -metadata:s:v:0 rotate=N não grava display matrix em MP4 (falha
            # silenciosa no FFmpeg 8). Usar -display_rotation ANTES de -i, que o muxer MP4
            # converte em display matrix de verdade. Para containers com codecs sem tag no
            # MP4 (ex.: AVI+WMA), recusar com orientação em vez de falhar no meio do mux.
            if output.suffix.lower() == ".mp4":
                self._validate_mp4_copy_codecs(media)
            command = [str(self._ffmpeg()), "-hide_banner", "-y"]
            command += ["-display_rotation:v:0", str(target_rotation)]
            timestamp_args = [] if has_trim else ["-avoid_negative_ts", "make_zero"]
            command += [*seek_args, "-i", str(source), *duration_args, "-map", "0", "-c", "copy", *timestamp_args, str(output)]
            self._execute(command, "Cortando e atualizando rotação" if has_trim else "Atualizando metadados de rotação", 1, 1, trim_duration)
            return
        filters: list[str] = []
        if degrees == -90:
            filters.append("transpose=2")
        elif degrees == 90:
            filters.append("transpose=1")
        elif abs(degrees) == 180:
            filters.extend(("hflip", "vflip"))
        if bool(self._worker_value("rotate_hflip", self.rotate_hflip_var)):
            filters.append("hflip")
        if bool(self._worker_value("rotate_vflip", self.rotate_vflip_var)):
            filters.append("vflip")
        if crop:
            filters.append(selection_crop_filter(crop))
        if not filters:
            output = self._recoverable_output(self.output_dir, suffix, self._metadata_rotate_output_suffix(source.suffix))
            if output.suffix.lower() == ".mp4":
                self._validate_mp4_copy_codecs(media)
            timestamp_args = [] if has_trim else ["-avoid_negative_ts", "make_zero"]
            command = [str(self._ffmpeg()), "-hide_banner", "-y", *seek_args, "-i", str(source), *duration_args, "-map", "0", "-c", "copy", *timestamp_args, str(output)]
            self._execute(command, "Cortando vídeo" if has_trim else "Copiando vídeo", 1, 1, trim_duration)
            return
        filter_text = ",".join(filters)
        if media.subtitle_streams or media.data_streams:
            self._append_log("Legendas, anexos e streams de dados não são preservados no giro com reencode.")

        duration = trim_duration
        requested_segments: int | None = None
        requested_text = str(self._worker_value("rotate_segments", self.rotate_segments_var)).strip()
        if requested_text:
            try:
                requested_segments = int(requested_text)
            except ValueError as exc:
                raise RuntimeError("Trechos deve ser um número inteiro positivo ou ficar vazio") from exc
            if requested_segments < 1:
                raise RuntimeError("Trechos deve ser maior que zero")
        rotate_parallel = bool(self._worker_value("rotate_parallel", self.rotate_parallel_var))
        if rotate_parallel and (has_trim or duration < 6):
            self._append_log("Processamento paralelo indisponível para recorte ou vídeo curto; usando um único processo.")
        if rotate_parallel and not has_trim and duration >= 6:
            keyframes = [value for value in self._extract_keyframes(source) if 0.1 < value < duration - 0.1]
            if keyframes:
                try:
                    self._rotate_video_parallel(source, output, filter_text, duration, keyframes, media.video_bitrate, requested_segments, media)
                    return
                except Cancelled:
                    raise
                except Exception as exc:
                    self._append_log(f"Giro paralelo não concluiu ({exc}); repetindo em um único processo.")
            else:
                self._append_log("Nenhum keyframe interno encontrado; processamento paralelo indisponível.")
        def build(profile):
            input_args, filter_args = self._filter_for_profile(filter_text, profile)
            audio_args = self._rotate_audio_args(media)
            return [str(self._ffmpeg()), "-hide_banner", "-y", *input_args, *seek_args, "-i", str(source), *duration_args, "-map", "0:v:0", "-map", "0:a?", "-sn", "-dn", *filter_args, *self._video_args(profile, media.video_bitrate), *hevc_tag_arguments(profile.encoder, output.suffix), *audio_args, "-map_metadata", "0", "-movflags", "+faststart", str(output)]
        self._execute_video("Girando e cortando vídeo" if has_trim else "Girando vídeo", build, duration_seconds=trim_duration)

    def _rotate_audio_args(self, media: MediaProfile) -> list[str]:
        if media.audio_codec in {"aac", "mp3", "ac3", "eac3", ""}:
            return ["-c:a", "copy"]
        return ["-c:a", "aac", "-b:a", media.audio_bitrate, "-ar", str(media.audio_rate), "-ac", str(media.audio_channels)]

    def _rotate_video_parallel(
        self,
        source: Path,
        output: Path,
        filters: str,
        duration: float,
        keyframes: list[float],
        video_bitrate: str,
        requested_segments: int | None,
        media: MediaProfile,
    ) -> None:
        # O valor manual controla tanto a quantidade de partes quanto a de
        # processos simultâneos. Sem valor manual, hardware encoders (NVENC/QSV/AMF)
        # são limitados a 3 para respeitar limites de sessões do driver.
        is_hw = bool(self.acceleration and self.acceleration.key in {"nvenc", "qsv", "amf"})
        default_workers = min(3, max(1, os.cpu_count() or 1)) if is_hw else max(1, os.cpu_count() or 1)
        requested_workers = requested_segments or default_workers
        if len(keyframes) < 1:
            raise RuntimeError("não há keyframes suficientes para dividir o vídeo")
        if len(keyframes) < requested_workers - 1:
            split_points = keyframes
            self._append_log(
                f"Foram encontrados apenas {len(keyframes)} keyframes internos; "
                f"o vídeo será dividido em {len(keyframes) + 1} trecho(s)."
            )
        else:
            used: set[float] = set()
            split_points = []
            for index in range(1, requested_workers):
                target = duration * index / requested_workers
                candidate = min((item for item in keyframes if item not in used), key=lambda item: abs(item - target), default=None)
                if candidate is not None:
                    used.add(candidate)
                    split_points.append(candidate)
        if not split_points:
            raise RuntimeError("não foi possível escolher pontos de divisão")

        work_dir = self._work_directory("rotate_parallel", self.output_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            pattern = work_dir / "parte_%05d.mkv"
            split_times = ",".join(self._fmt_seconds(value) for value in sorted(split_points))
            split_command = [
                str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
                "-f", "segment", "-segment_times", split_times, "-reset_timestamps", "1",
                "-segment_format", "matroska", "-avoid_negative_ts", "make_zero", str(pattern),
            ]
            self._execute(split_command, "Dividindo vídeo em trechos", 1, 3)
            segments = sorted(work_dir.glob("parte_*.mkv"))
            if len(segments) < 2:
                raise RuntimeError("a divisão do vídeo não gerou segmentos suficientes")

            tracker = self.task_tracker
            segment_labels = [f"Girando trecho {index + 1}" for index in range(len(segments))]
            if tracker:
                tracker.append(segment_labels + ["Juntando vídeo final"])
            speeds: dict[int, float] = {}
            speeds_lock = threading.Lock()

            def rotate_segment(index: int, segment: Path) -> Path:
                destination = work_dir / f"girado_{index:05d}.mp4"
                task_label = f"Girando trecho {index + 1}"
                segment_duration = self._probe_media(segment).duration
                def build(profile: VideoAcceleration):
                    input_args, filter_args = self._filter_for_profile(filters, profile)
                    return [
                        str(self._ffmpeg()), "-hide_banner", "-y", *input_args, "-i", str(segment),
                        "-map", "0:v:0", "-map", "0:a?", *filter_args, *self._video_args(profile, video_bitrate),
                        *self._rotate_audio_args(media), "-map_metadata", "0",
                        "-movflags", "+faststart", str(destination),
                    ]
                def on_progress(percent: int, speed_text: str):
                    try:
                        speed = float(speed_text.rstrip("x"))
                    except ValueError:
                        speed = 0.0
                    with speeds_lock:
                        if speed > 0: speeds[index] = speed
                        combined = sum(speeds.values())
                    if tracker:
                        tracker.start(task_label, percent, speed_text)
                        if combined > 0:
                            tracker.live(f"Velocidade real estimada: {combined:.1f}x")
                try:
                    self._execute_video(task_label, build, index + 1, len(segments) + 2, segment_duration, on_progress)
                except Exception as exc:
                    if tracker: tracker.fail_task(task_label, str(exc).splitlines()[0][:160])
                    raise
                return destination

            worker_count = min(requested_workers, len(segments))
            self._append_log(f"Giro paralelo: {len(segments)} trecho(s), até {worker_count} simultâneo(s).")
            with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = [executor.submit(rotate_segment, index, segment) for index, segment in enumerate(segments)]
                rotated = [future.result() for future in futures]
            if self.cancel_event.is_set():
                raise Cancelled()

            list_file = work_dir / "partes.txt"
            lines = []
            for path in rotated:
                lines.append(f"file '{self._concat_escape(str(path.resolve()))}'")
            list_file.write_text("\n".join(lines), encoding="utf-8")
            concat_command = [
                str(self._ffmpeg()), "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-c", "copy", "-map_metadata", "0",
                "-movflags", "+faststart", str(output),
            ]
            self._execute(concat_command, "Juntando vídeo final", len(segments) + 2, len(segments) + 2, duration)
            self._append_log(f"Giro paralelo concluído: {len(segments)} trechos, até {worker_count} em paralelo.")
        finally:
            self._remove_work_directory(work_dir)

    # Layouts nomeados que o FFmpeg reporta na linha de áudio ("48000 Hz, 5.1, ...").
    _CHANNEL_LAYOUT_COUNTS = {
        "mono": 1, "stereo": 2, "2.1": 3, "3.0": 3, "3.1": 4, "quad": 4, "4.0": 4,
        "5.0": 5, "5.1": 6, "5.1(side)": 6, "6.0": 6, "6.1": 7, "7.0": 7,
        "7.1": 8, "7.1(wide)": 8, "7.1(wide-side)": 8, "octagonal": 8,
    }

    def _parse_audio_tracks(self, text: str) -> tuple[AudioTrackProfile, ...]:
        """Um AudioTrackProfile por faixa de áudio, na ordem da entrada.

        O perfil único (o da primeira faixa) impõe taxa, canais e bitrate à
        faixa errada quando o arquivo tem mais de um áudio: este inventário é
        a fonte do reencode por faixa.
        """
        tracks: list[AudioTrackProfile] = []
        for line in text.splitlines():
            if "Audio:" not in line or not re.search(r"Stream #\d+:\d+", line):
                continue
            codec_match = re.search(r"Audio:\s*([a-zA-Z0-9_]+)", line)
            codec = codec_match.group(1).lower() if codec_match else ""
            rate_match = re.search(r"(\d+)\s*Hz", line)
            rate = int(rate_match.group(1)) if rate_match else 48000
            layout_match = re.search(r"(\d+)\s*Hz,\s*([a-zA-Z0-9][a-zA-Z0-9.()]*)", line)
            layout_token = layout_match.group(2) if layout_match else ""
            if layout_token in self._CHANNEL_LAYOUT_COUNTS:
                layout = layout_token
                channels = self._CHANNEL_LAYOUT_COUNTS[layout_token]
            else:
                channels_match = re.search(r"(\d+)\s*channels", line)
                channels = int(channels_match.group(1)) if channels_match else 2
                layout = {1: "mono", 2: "stereo", 6: "5.1", 8: "7.1"}.get(channels, "stereo")
            rates = re.findall(r"(\d+(?:\.\d+)?)\s*kb/s", line)
            bitrate = f"{float(rates[-1]):g}k" if rates and float(rates[-1]) > 0 else "128k"
            language_match = re.search(r"Stream #\d+:\d+(?:\[[^\]]*\])?\(([^)]*)\)", line)
            tracks.append(
                AudioTrackProfile(
                    index=len(tracks),
                    codec=codec,
                    bitrate=bitrate,
                    rate=rate,
                    channels=channels,
                    layout=layout,
                    default="(default)" in line,
                    language=language_match.group(1) if language_match else "",
                )
            )
        return tuple(tracks)

    def _precise_audio_args(self, media: MediaProfile) -> list[str]:
        """Reencoda o áudio com o perfil de CADA faixa.

        Os especificadores :N valem para a SAÍDA: como a seleção mapeia todas
        as faixas de áudio na ordem da entrada (-map 0:a?), a faixa N da saída
        corresponde à faixa N da entrada. Sem inventário (probe sem faixas),
        mantém o comportamento anterior em vez de regredir.
        """
        if not media.audio_tracks:
            return [
                "-c:a", "aac", "-b:a", media.audio_bitrate,
                "-ar", str(media.audio_rate), "-ac", str(media.audio_channels),
            ]
        args: list[str] = []
        for track in media.audio_tracks:
            # Especificador QUALIFICADO (a:N): o nu (-ar:0) casa por indice
            # GLOBAL de stream e o stream 0 e o video — medido (14/09): a faixa
            # A saia com a taxa da B (48000/2 em vez de 44100/1).
            args += [
                f"-c:a:{track.index}", "aac",
                f"-b:a:{track.index}", track.bitrate,
                f"-ar:a:{track.index}", str(track.rate),
                f"-ac:a:{track.index}", str(track.channels),
            ]
        return args

    def _probe_media(self, source: Path) -> MediaProfile:
        command = [str(self._ffmpeg()), "-hide_banner", "-i", str(source)]
        self._record_ffmpeg_command(command, probe=True)
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        text = result.stderr + result.stdout
        container_start_match = re.search(r"Duration: [^,]+, start: (-?\d+(?:\.\d+)?)", text)
        container_start = float(container_start_match.group(1)) if container_start_match else 0.0
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", text)
        duration = 0.0
        if duration_match:
            duration = int(duration_match.group(1)) * 3600 + int(duration_match.group(2)) * 60 + float(duration_match.group(3))
        video_line = next((line for line in text.splitlines() if "Video:" in line and "attached pic" not in line), "")
        audio_line = next((line for line in text.splitlines() if "Audio:" in line), "")
        video_match = re.search(r"(\d{2,5})x(\d{2,5}).*?(\d+(?:\.\d+)?) fps", video_line)
        if video_match:
            width = int(video_match.group(1))
            height = int(video_match.group(2))
            fps = video_match.group(3)
        else:
            dim_match = re.search(r"(\d{2,5})x(\d{2,5})", video_line)
            width = int(dim_match.group(1)) if dim_match else 1280
            height = int(dim_match.group(2)) if dim_match else 720
            fps_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:fps|tbr)", video_line)
            fps = fps_match.group(1) if fps_match else "30"

        video_rates = re.findall(r"(\d+(?:\.\d+)?)\s*kb/s", video_line)
        audio_start_match = re.search(r"start\s+(-?\d+(?:\.\d+)?)", audio_line)
        audio_start = float(audio_start_match.group(1)) if audio_start_match else 0.0
        audio_rates = re.findall(r"(\d+(?:\.\d+)?)\s*kb/s", audio_line)
        audio_bitrate = f"{float(audio_rates[-1]):g}k" if audio_rates and float(audio_rates[-1]) > 0 else "128k"
        if video_rates and float(video_rates[-1]) > 0:
            video_bitrate = f"{float(video_rates[-1]):g}k"
        else:
            container_rate = re.search(r"bitrate:\s*(\d+(?:\.\d+)?)\s*kb/s", text)
            if container_rate and float(container_rate.group(1)) > 0:
                total_kbps = float(container_rate.group(1))
                audio_kbps = float(audio_rates[-1]) if (audio_rates and float(audio_rates[-1]) > 0) else 128.0
                est_video_kbps = max(100.0, total_kbps - audio_kbps if bool(audio_line) else total_kbps)
                video_bitrate = f"{round(est_video_kbps)}k"
            else:
                video_bitrate = "1M"

        rate_match = re.search(r"(\d+)\s*Hz", audio_line)
        audio_rate = int(rate_match.group(1)) if rate_match else 48000
        layout_match = re.search(r"(\d+)\s*Hz,\s*([a-zA-Z0-9][a-zA-Z0-9.()]*)", audio_line)
        layout_token = layout_match.group(2) if layout_match else ""
        if layout_token in self._CHANNEL_LAYOUT_COUNTS:
            audio_layout = layout_token
            audio_channels = self._CHANNEL_LAYOUT_COUNTS[layout_token]
        else:
            channels_match = re.search(r"(\d+)\s*channels", audio_line)
            audio_channels = int(channels_match.group(1)) if channels_match else 2
            audio_layout = {1: "mono", 2: "stereo", 6: "5.1", 8: "7.1"}.get(audio_channels, "stereo")

        rotate_match = re.search(r"rotation of\s*(-?\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if not rotate_match:
            rotate_match = re.search(r"rotate\s*:\s*(-?\d+(?:\.\d+)?)", text, re.IGNORECASE)
        rotation = round(float(rotate_match.group(1))) % 360 if rotate_match else 0

        audio_codec_match = re.search(r"Audio:\s*([a-zA-Z0-9_]+)", audio_line)
        audio_codec = audio_codec_match.group(1).lower() if audio_codec_match else ""

        video_codec_match = re.search(r"Video:\s*([a-zA-Z0-9_]+)", video_line)
        video_codec = video_codec_match.group(1).lower() if video_codec_match else ""

        pix_fmt_match = re.search(r"Video:\s*[^,]+,\s*([a-zA-Z0-9_]+)", video_line)
        pix_fmt = pix_fmt_match.group(1).lower() if pix_fmt_match else ""

        tbr_match = re.search(r"(\d+(?:\.\d+)?)\s*tbr", video_line)
        average_rate = tbr_match.group(1) if tbr_match else ""
        tbn_match = re.search(r"(\d+(?:\.\d+)?k?)\s*tbn", video_line)
        timebase = tbn_match.group(1).lower() if tbn_match else ""
        sar_match = re.search(r"SAR\s+(\d+[:/]\d+)", video_line, re.IGNORECASE)
        sar = sar_match.group(1).replace("/", ":") if sar_match else ""

        stream_lines = [line for line in text.splitlines() if re.search(r"Stream #\d+:\d+", line)]
        audio_streams = sum("Audio:" in line for line in stream_lines)
        subtitle_streams = sum("Subtitle:" in line for line in stream_lines)
        data_streams = sum("Data:" in line or "Attachment:" in line for line in stream_lines)

        return MediaProfile(
            duration, bool(audio_line), width - width % 2, height - height % 2, fps,
            video_bitrate, audio_bitrate, audio_rate, audio_channels, audio_layout,
            bool(video_line), rotation, audio_codec,
            video_codec, pix_fmt, timebase, sar,
            audio_streams, subtitle_streams, data_streams,
            audio_tracks=self._parse_audio_tracks(text),
            average_rate=average_rate,
            audio_start_seconds=audio_start,
            container_start_seconds=container_start,
        )

    def _max_audio_transition(self, clips) -> float:
        # Clipes internos recebem duas transições (uma em cada extremidade); os das
        # pontas recebem apenas uma. O limite deve respeitar todos.
        limits = []
        for i, clip in enumerate(clips):
            factor = 2.05 if (0 < i < len(clips) - 1) else 1.05
            limits.append(clip.duration / factor)
        return min(limits) if limits else 0.0

    @staticmethod
    def _select_join_base(clips: list[MediaProfile], choice: str) -> MediaProfile:
        if choice.startswith("Automático"):
            sources = [smart_join_planner.Source(
                clip.duration, FfmpegToolsPanel._smart_join_video_profile(clip), []
            ) for clip in clips]
            return clips[smart_join_planner.choose_target_index(sources)]
        if choice.startswith("Maior"):
            return max(clips, key=lambda clip: clip.width * clip.height)
        if choice.startswith("Menor"):
            return min(clips, key=lambda clip: clip.width * clip.height)
        return clips[0]

    @staticmethod
    def _rotation_display_angle(rotation: int) -> int:
        """Ângulo amigável para exibir (intervalo -179..180): 270 aparece como -90."""
        value = int(rotation) % 360
        return value - 360 if value > 180 else value

    @staticmethod
    def _rotation_storage_transpose(rotation: int) -> str:
        """Filtro que devolve um vídeo já exibido em pé (frames autorotacionados)
        para a orientação de armazenamento que, combinada com a display matrix de
        `rotation`, é exibida igual ao original.

        Validação empírica com o FFmpeg 8 do dist (set/2026, MAE 0 em frames reais):
        a volta exibido -> armazenado é transpose=1 para rotation=90 e transpose=2
        para rotation=270; 180° é rotação pura (hflip+vflip).
        """
        value = int(rotation) % 360
        if value == 90:
            return "transpose=1"
        if value == 270:
            return "transpose=2"
        if value == 180:
            return "hflip,vflip"
        return ""

    @classmethod
    def _join_display_size(cls, clip: MediaProfile) -> tuple[int, int]:
        """Tamanho de EXIBIÇÃO (após o player aplicar o giro do metadado)."""
        width, height = clip.width, clip.height
        if clip.rotation % 360 in {90, 270} and width != height:
            width, height = height, width
        return width, height

    def _join_rotation_question(
        self,
        paths: list[Path],
        clips: list[MediaProfile],
        reencode_mp4: bool,
    ) -> dict | None:
        """Monta a pergunta de orientação do join (None = não perguntar).

        Dispara quando o join vai reencodar para MP4 e ao menos um vídeo carrega
        giro no metadado. Cada forma de armazenamento com giro vira uma opção
        'manter o formato' (o arquivo escolhido vira a referência); a opção padrão
        aplica o giro nos frames (saída sem metadado, comportamento histórico).
        """
        if not reencode_mp4:
            return None
        video_clips = [clip for clip in clips if clip.has_video]
        if len(video_clips) != len(clips):
            return None
        rotated = [clip for clip in clips if clip.rotation % 360 != 0]
        if not rotated:
            return None
        display_orientations = {
            display_width > display_height
            for display_width, display_height in (self._join_display_size(clip) for clip in clips)
        }
        mixed_display = len(display_orientations) > 1
        lines = []
        for path, clip in zip(paths, clips):
            if clip.rotation % 360 == 0:
                continue
            lines.append(
                f"• {path.name} — {clip.width}x{clip.height} com giro de "
                f"{self._rotation_display_angle(clip.rotation)}° "
                f"(exibido {self._join_display_size(clip)[0]}x{self._join_display_size(clip)[1]})"
            )
        message = "Estes vídeos têm giro gravado nos metadados:\n" + "\n".join(lines) + "\n\nComo deseja gerar a saída?"
        if mixed_display:
            message += (
                "\n\nAtenção: há vídeos em orientações de exibição diferentes; "
                "os que não seguirem a referência entram com barras."
            )
        first = video_clips[0]
        display_width, display_height = self._join_display_size(first)
        options: list[dict] = [
            {
                "key": "bake",
                "label": "Aplicar giro nos vídeos (recomendado)",
                "detail": (
                    f"Saída {display_width}x{display_height} com o giro aplicado aos frames; "
                    "arquivo sem metadado de giro, igual ao que os players mostram."
                ),
            }
        ]
        seen: set[tuple[int, int, int]] = set()
        for path, clip in zip(paths, clips):
            rotation = clip.rotation % 360
            if rotation == 0 or not clip.has_video:
                continue
            if rotation in {90, 270} and clip.width == clip.height:
                continue  # giro de 90° em vídeo quadrado não muda o armazenamento
            form = (clip.width, clip.height, rotation)
            if form in seen:
                continue
            seen.add(form)
            options.append(
                {
                    "key": f"preserve:{paths.index(path)}",
                    "label": (
                        f"Manter o formato de {path.name}: {clip.width}x{clip.height} "
                        f"com giro de {self._rotation_display_angle(rotation)}°"
                    ),
                    "detail": (
                        "Como o original: o arquivo guarda a resolução e o giro; "
                        "os players giram ao exibir."
                    ),
                }
            )
        return {
            "message": message,
            "options": options,
            "default": "bake",
            "mixed_display": mixed_display,
        }

    @staticmethod
    def _join_copy_mapping(preserve_all_streams: bool, include_audio: bool) -> list[str]:
        if preserve_all_streams:
            return ["-map", "0"] + ([] if include_audio else ["-map", "-0:a?"])
        return ["-map", "0:v:0"] + (["-map", "0:a:0?"] if include_audio else ["-an"]) + ["-sn", "-dn"]

    @staticmethod
    def _join_requires_silence_reencode(
        clips: list[MediaProfile],
        include_audio: bool,
        join_reencode: bool,
        join_smart: bool,
        transition_seconds: float,
    ) -> bool:
        mixed_audio = any(clip.has_audio for clip in clips) and any(not clip.has_audio for clip in clips)
        copy_without_transition = (not join_reencode and not join_smart) or (join_smart and transition_seconds <= 0.001)
        return mixed_audio and include_audio and copy_without_transition

    def _join_audio_worker(self, clips: list[MediaProfile]) -> None:
        try:
            transition_seconds = float(str(self._worker_value("join_seconds", self.join_seconds_var)).replace(",", "."))
        except ValueError as exc:
            raise RuntimeError("Tempo de transição inválido") from exc
        if not math.isfinite(transition_seconds):
            raise RuntimeError("Tempo de transição inválido")
        if transition_seconds < 0:
            raise RuntimeError("Tempo de transição não pode ser negativo")

        join_reencode = bool(self._worker_value("join_reencode", self.join_reencode_var))
        join_smart = bool(self._worker_value("join_smart", self.join_smart_var))
        stream_policy = str(self._worker_value_default("join_stream_policy", "join_stream_policy_var", "Primeira faixa (MP4)"))
        preserve_all_streams = stream_policy.startswith("Todas")
        copy_only = (not join_reencode and not join_smart) or (join_smart and transition_seconds <= 0.001)
        if copy_only:
            extension = ".mkv" if preserve_all_streams else (self.join_inputs[0].suffix.lower() or ".m4a")
            first = clips[0]
            for idx, clip in enumerate(clips[1:], start=2):
                if clip.audio_rate != first.audio_rate or clip.audio_channels != first.audio_channels or clip.audio_codec != first.audio_codec or clip.audio_layout != first.audio_layout:
                    raise RuntimeError(
                        f"Os áudios possuem taxas, canais, codecs ou layouts distintos ({first.audio_rate}Hz/{first.audio_channels}ch/{first.audio_codec}/{first.audio_layout} "
                        f"vs {clip.audio_rate}Hz/{clip.audio_channels}ch/{clip.audio_codec}/{clip.audio_layout}). "
                        "Marque 'Reencode Completo' ou o modo automático para compatibilizá-las."
                    )
            if preserve_all_streams and len({clip.audio_streams for clip in clips}) != 1:
                raise RuntimeError("Para preservar todas as faixas, todos os arquivos precisam ter a mesma quantidade de streams de áudio.")
            output = self._recoverable_output(self.output_dir, "audios_juntos", extension)
            list_file = self._work_file(self.output_dir, "join_audio", ".txt")
            list_file.write_text(
                "\n".join(f"file '{self._concat_escape(str(path.resolve()))}'" for path in self.join_inputs),
                encoding="utf-8",
            )
            try:
                command = [
                    str(self._ffmpeg()), "-hide_banner", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(list_file), "-map", "0" if preserve_all_streams else "0:a:0", "-c", "copy", str(output),
                ]
                self._execute(command, "Juntando áudios sem reencodar", 1, 1, sum(item.duration for item in clips))
                return
            finally:
                list_file.unlink(missing_ok=True)

        if preserve_all_streams:
            raise RuntimeError("Preservar todas as faixas está disponível somente sem transição e sem reencode.")

        max_transition = self._max_audio_transition(clips)
        if transition_seconds > max_transition:
            transition_seconds = max(0.01, max_transition)
            self._append_log(f"Tempo de transição de áudio ajustado para {transition_seconds:.2f}s para caber nos clipes sem perda.")

        transition_choice = str(self._worker_value("join_transition", self.join_transition_var))
        transition_code = dict(self.AUDIO_TRANSITIONS).get(transition_choice, "tri")
        extension = self._audio_only_output_extension(self.join_inputs[0])
        output = self._recoverable_output(self.output_dir, "audios_juntos", extension)
        command = [str(self._ffmpeg()), "-hide_banner", "-y"]
        for path in self.join_inputs:
            command += ["-i", str(path)]
        filters: list[str] = []
        first = clips[0]
        target_rate = first.audio_rate
        for idx in range(len(self.join_inputs)):
            filters.append(f"[{idx}:a]aresample={target_rate},aformat=sample_rates={target_rate}:channel_layouts={first.audio_layout}[a{idx}_norm]")

        if transition_seconds > 0:
            if transition_choice == "Fade in/out" or transition_code == "fade":
                faded_labels: list[str] = []
                for idx, clip in enumerate(clips):
                    fade_dur = min(transition_seconds, clip.duration / 2)
                    fade_filters: list[str] = []
                    if idx > 0:
                        fade_filters.append(f"afade=t=in:st=0:d={self._fmt_seconds(fade_dur)}")
                    if idx < len(clips) - 1:
                        fade_out_st = max(0.0, clip.duration - fade_dur)
                        fade_filters.append(f"afade=t=out:st={self._fmt_seconds(fade_out_st)}:d={self._fmt_seconds(fade_dur)}")
                    lbl = f"af{idx}"
                    fade_str = ("," + ",".join(fade_filters)) if fade_filters else ""
                    filters.append(f"[a{idx}_norm]{fade_str.lstrip(',')}[{lbl}]" if fade_filters else f"[a{idx}_norm]anull[{lbl}]")
                    faded_labels.append(lbl)
                concat_inputs = "".join(f"[{lbl}]" for lbl in faded_labels)
                filters.append(f"{concat_inputs}concat=n={len(clips)}:v=0:a=1[aout]")
                command += ["-filter_complex", ";".join(filters), "-map", "[aout]"]
            else:
                previous = "a0_norm"
                curve = transition_code if transition_code not in {"none", "fade"} else "tri"
                for index in range(1, len(self.join_inputs)):
                    output_label = f"a{index}out"
                    filters.append(
                        f"[{previous}][a{index}_norm]acrossfade=d={self._fmt_seconds(transition_seconds)}"
                        f":c1={curve}:c2={curve}[{output_label}]"
                    )
                    previous = output_label
                filter_text = ";".join(filters)
                command += ["-filter_complex", filter_text, "-map", f"[{previous}]"]
        else:
            inputs = "".join(f"[a{index}_norm]" for index in range(len(self.join_inputs)))
            filters.append(f"{inputs}concat=n={len(self.join_inputs)}:v=0:a=1[aout]")
            command += [
                "-filter_complex", ";".join(filters),
                "-map", "[aout]",
            ]
        first = clips[0]
        command += [
            "-ar", str(first.audio_rate), "-ac", str(first.audio_channels),
            *self._audio_codec_args(extension, first.audio_bitrate), str(output),
        ]
        total_duration = sum(item.duration for item in clips) - (transition_seconds * (len(clips) - 1) if transition_choice != "Fade in/out" else 0.0)
        self._execute(command, "Aplicando transições e juntando áudios", 1, 1, max(0.1, total_duration))

    # Codecs de áudio que o container MP4 aceita em fluxo -c copy.
    _MP4_SAFE_AUDIO_CODECS = {"aac", "mp3", "ac3", "eac3", "alac", "flac", "opus"}
    # Codecs de vídeo que o container MP4 aceita em fluxo -c copy.
    _MP4_SAFE_VIDEO_CODECS = {"h264", "hevc", "mpeg4", "mjpeg", "h263"}

    def _validate_video_copy_compatibility(self, clips: list[MediaProfile], require_mp4: bool = True, ignore_audio: bool = False) -> None:
        first = clips[0]
        if require_mp4 and first.video_codec and first.video_codec not in self._MP4_SAFE_VIDEO_CODECS:
            raise RuntimeError(
                f"O codec de vídeo '{first.video_codec}' do primeiro arquivo não é compatível com o container MP4. "
                "Marque 'Reencode Completo' ou use transição no modo automático para convertê-lo."
            )
        if not ignore_audio and require_mp4 and first.has_audio and first.audio_codec and first.audio_codec not in self._MP4_SAFE_AUDIO_CODECS:
            raise RuntimeError(
                f"O codec de áudio '{first.audio_codec}' do primeiro arquivo não é compatível com o container MP4. "
                "Marque 'Reencode Completo' para convertê-lo."
            )
        for idx, clip in enumerate(clips[1:], start=2):
            if require_mp4 and clip.video_codec and clip.video_codec not in self._MP4_SAFE_VIDEO_CODECS:
                raise RuntimeError(
                    f"O codec de vídeo '{clip.video_codec}' não é compatível com o container MP4. "
                    "Marque 'Reencode Completo' ou use transição no modo automático para convertê-lo."
                )
            if clip.video_codec and first.video_codec and clip.video_codec != first.video_codec:
                raise RuntimeError(
                    f"As mídias possuem codecs de vídeo distintos ({first.video_codec} vs {clip.video_codec}). "
                    "Marque 'Reencode Completo' ou use transição no modo automático para compatibilizá-las."
                )
            if clip.width != first.width or clip.height != first.height:
                raise RuntimeError(
                    f"As mídias possuem resoluções distintas ({first.width}x{first.height} vs {clip.width}x{clip.height}). "
                    "Marque 'Reencode Completo' ou use transição no 'SmartJoin' para compatibilizá-las."
                )
            if clip.fps != first.fps:
                raise RuntimeError(
                    f"As mídias possuem taxas de quadros distintas ({first.fps} fps vs {clip.fps} fps). "
                    "Marque 'Reencode Completo' ou use transição no 'SmartJoin' para compatibilizá-las."
                )
            if clip.pix_fmt and first.pix_fmt and clip.pix_fmt != first.pix_fmt:
                raise RuntimeError(
                    f"As mídias possuem formatos de pixel distintos ({first.pix_fmt} vs {clip.pix_fmt}). "
                    "Marque 'Reencode Completo' ou use transição no 'SmartJoin' para compatibilizá-las."
                )
            if clip.timebase and first.timebase and clip.timebase != first.timebase:
                raise RuntimeError(
                    f"As mídias possuem bases de tempo distintas ({first.timebase} tbn vs {clip.timebase} tbn). "
                    "Marque 'Reencode Completo' ou use transição no 'SmartJoin' para compatibilizá-las."
                )
            if clip.sar and first.sar and clip.sar != first.sar:
                raise RuntimeError(
                    f"As mídias possuem proporções de pixel distintas ({first.sar} SAR vs {clip.sar} SAR). "
                    "Marque 'Reencode Completo' ou use transição no 'SmartJoin' para compatibilizá-las."
                )
            if clip.rotation != first.rotation:
                raise RuntimeError(
                    f"As mídias possuem rotações de exibição distintas ({first.rotation}° vs {clip.rotation}°). "
                    "Marque 'Reencode Completo' ou use o modo automático com transição para normalizar a orientação."
                )
            if not ignore_audio and clip.has_audio != first.has_audio:
                raise RuntimeError(
                    "Algumas mídias possuem áudio e outras não. "
                    "Marque 'Reencode Completo' ou use transição no 'SmartJoin' para compatibilizá-las."
                )
            if not ignore_audio and clip.has_audio and (clip.audio_codec != first.audio_codec or clip.audio_rate != first.audio_rate or clip.audio_channels != first.audio_channels or clip.audio_layout != first.audio_layout):
                raise RuntimeError(
                    f"As trilhas de áudio possuem formatos divergentes ({first.audio_codec}/{first.audio_rate}Hz/{first.audio_layout} vs {clip.audio_codec}/{clip.audio_rate}Hz/{clip.audio_layout}). "
                    "Marque 'Reencode Completo' ou use transição no 'SmartJoin' para compatibilizá-las."
                )
            if not ignore_audio and require_mp4 and clip.has_audio and clip.audio_codec and clip.audio_codec not in self._MP4_SAFE_AUDIO_CODECS:
                raise RuntimeError(
                    f"O codec de áudio '{clip.audio_codec}' não é compatível com o container MP4. "
                    "Marque 'Reencode Completo' para convertê-lo."
                )

    def _join_worker(self) -> None:
        if len(self.join_inputs) < 2:
            raise RuntimeError("Selecione pelo menos dois áudios ou vídeos")
        if any(not path.exists() for path in self.join_inputs):
            raise RuntimeError("Uma das mídias selecionadas não foi encontrada")
        clips = [self._probe_media(path) for path in self.join_inputs]
        for clip in clips:
            aviso_cor = color_depth_warning(getattr(clip, "pix_fmt", ""))
            if aviso_cor:
                self._append_log(aviso_cor)
                break
        if all(not item.has_video and item.has_audio for item in clips):
            self._join_audio_worker(clips)
            return
        if any(not item.has_video for item in clips):
            raise RuntimeError("Junte somente áudios ou somente vídeos na mesma tarefa")
        join_reencode = bool(self._worker_value("join_reencode", self.join_reencode_var))
        join_smart = bool(self._worker_value("join_smart", self.join_smart_var))
        profile_choice = str(self._worker_value_default("join_profile", "join_profile_var", "Automático (preservar mais vídeo)"))
        stream_policy = str(self._worker_value_default("join_stream_policy", "join_stream_policy_var", "Primeira faixa (MP4)"))
        audio_policy = str(self._worker_value_default("join_audio_policy", "join_audio_policy_var", "Preservar áudio e preencher silêncio"))
        preserve_all_streams = stream_policy.startswith("Todas")
        copy_audio = any(clip.has_audio for clip in clips) and not audio_policy.startswith("Gerar saída sem áudio")
        try:
            requested_transition_seconds = float(str(self._worker_value("join_seconds", self.join_seconds_var)).replace(",", ".") or 0)
        except ValueError:
            requested_transition_seconds = 0.0
        force_silence_reencode = self._join_requires_silence_reencode(
            clips, copy_audio, join_reencode, join_smart, requested_transition_seconds
        )
        # SmartJoin pode copiar o vídeo e montar apenas o áudio/silêncio.
        smart_audio_only_reencode = join_smart and force_silence_reencode
        if smart_audio_only_reencode:
            force_silence_reencode = False
        if force_silence_reencode:
            join_reencode = True
            join_smart = False
            self._append_log("Há clipes com e sem áudio; a saída será reencodada para preencher silêncio sem deslocar a timeline.")
        output = self._recoverable_output(self.output_dir, "videos_juntos", ".mkv" if preserve_all_streams else ".mp4")
        extra_streams = any(item.audio_streams > 1 or item.subtitle_streams or item.data_streams for item in clips)
        if extra_streams:
            self._append_log(
                "Streams detectados: "
                + "; ".join(
                    f"{path.name}: {clip.audio_streams} áudio, {clip.subtitle_streams} legenda, {clip.data_streams} dados/anexos"
                    for path, clip in zip(self.join_inputs, clips)
                )
            )
        if not join_reencode and not join_smart:
            self._validate_video_copy_compatibility(clips, require_mp4=not preserve_all_streams, ignore_audio=not copy_audio)
            if preserve_all_streams:
                topology = {((clip.audio_streams if copy_audio else 0), clip.subtitle_streams, clip.data_streams) for clip in clips}
                if len(topology) != 1:
                    raise RuntimeError("Para preservar todas as faixas sem reencode, todos os clipes precisam ter a mesma quantidade de áudio, legendas e dados/anexos.")
            if extra_streams and not preserve_all_streams:
                self._append_log("O join sem reencode preserva o primeiro vídeo e o primeiro áudio; faixas extras, legendas e dados não são incluídos.")
            list_file = self._work_file(self.output_dir, "join_list", ".txt")
            lines = []
            for path in self.join_inputs:
                lines.append(f"file '{self._concat_escape(str(path.resolve()))}'")
            list_file.write_text("\n".join(lines), encoding="utf-8")
            try:
                mapping = self._join_copy_mapping(preserve_all_streams, copy_audio)
                container_args = [] if preserve_all_streams else ["-movflags", "+faststart"]
                self._execute(
                    [str(self._ffmpeg()), "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), *mapping, "-c", "copy", *container_args, str(output)],
                    "Juntando sem reencodar",
                    1,
                    1,
                    sum(item.duration for item in clips),
                )
                return
            finally:
                list_file.unlink(missing_ok=True)
        try:
            transition_seconds = float(str(self._worker_value("join_seconds", self.join_seconds_var)).replace(",", "."))
        except ValueError as exc:
            raise RuntimeError("Tempo de transição inválido") from exc
        if not math.isfinite(transition_seconds):
            raise RuntimeError("Tempo de transição inválido")
        if transition_seconds < 0:
            raise RuntimeError("Tempo de transição não pode ser negativo")
        strategy = "Smart Join" if join_smart else "Reencodar"
        transition_label = str(self._worker_value("join_transition", self.join_transition_var))
        if force_silence_reencode:
            transition_seconds = 0.0
            transition_label = "Fundir"
        transition = self.VIDEO_TRANSITION_CODES.get(transition_label, transition_label)
        if preserve_all_streams and (smart_audio_only_reencode or not (join_smart and transition_seconds <= 0.001)):
            raise RuntimeError(
                "Preservar todas as faixas exige cópia sem transição e faixas compatíveis. "
                "Transições ou preenchimento de silêncio exigem uma política por faixa; escolha Primeira faixa (MP4)."
            )
        if strategy == "Smart Join" and transition_seconds <= smart_join_planner.NO_TRANSITION_SECONDS and not smart_audio_only_reencode and preserve_all_streams:
            self._validate_video_copy_compatibility(clips, require_mp4=not preserve_all_streams, ignore_audio=not copy_audio)
            if preserve_all_streams:
                topology = {((clip.audio_streams if copy_audio else 0), clip.subtitle_streams, clip.data_streams) for clip in clips}
                if len(topology) != 1:
                    raise RuntimeError("Para preservar todas as faixas sem reencode, todos os clipes precisam ter a mesma quantidade de áudio, legendas e dados/anexos.")
            list_file = self._work_file(self.output_dir, "join_list", ".txt")
            lines = []
            for path in self.join_inputs:
                lines.append(f"file '{self._concat_escape(str(path.resolve()))}'")
            list_file.write_text("\n".join(lines), encoding="utf-8")
            try:
                mapping = self._join_copy_mapping(preserve_all_streams, copy_audio)
                container_args = [] if preserve_all_streams else ["-movflags", "+faststart"]
                # O concat usa o início mais antigo de todas as faixas. O
                # priming AAC pode então deslocar o primeiro vídeo em 21 ms.
                # Rebasear só os timestamps conserva os pacotes e B-frames.
                container_args += ["-avoid_negative_ts", "disabled", "-bsf:v", "setts=pts=PTS-STARTPTS:dts=DTS-STARTPTS"]
                if copy_audio:
                    # Priming dos áudios pode dar DTS repetido na emenda. Uma
                    # correção de no máximo 1 ms mantém os pacotes em cópia,
                    # sem duplicar timestamps no MKV ou recodificar faixas.
                    container_args += ["-bsf:a", "setts=ts='if(eq(PREV_OUTPTS,NOPTS),PTS,max(PTS,PREV_OUTPTS+0.001/TB))'"]
                self._execute([str(self._ffmpeg()), "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), *mapping, "-c", "copy", *container_args, str(output)], "Join automático sem perda", 1, 1, sum(item.duration for item in clips))
                return
            finally:
                list_file.unlink(missing_ok=True)
        if any(duration <= 0 for duration, *_rest in clips):
            raise RuntimeError("Não consegui identificar a duração de um dos vídeos")
        shortest = min(duration for duration, *_rest in clips)
        if len(clips) > 2 and strategy == "Smart Join":
            max_safe_transition = min((clips[i].duration - 0.12) / 2.0 for i in range(1, len(clips) - 1))
            max_safe_transition = min(max_safe_transition, clips[0].duration - 0.1, clips[-1].duration - 0.1)
        else:
            max_safe_transition = shortest / 2.0 if strategy == "Smart Join" else shortest - 0.1
        max_safe_transition = max(0.0, max_safe_transition)
        if transition_seconds > max_safe_transition:
            transition_seconds = max_safe_transition
            self._append_log(f"Tempo de transição ajustado para {transition_seconds:.2f}s para evitar perda de quadros nos clipes.")
        preserve_rotation = False
        orientation_mode = str(self._worker_value_default("join_orientation_mode", "join_orientation_mode_var", "bake"))
        orientation_reference = str(self._worker_value_default("join_orientation_reference", "join_orientation_reference_var", ""))
        if orientation_mode == "preserve" and orientation_reference and not preserve_all_streams:
            reference = next(
                (clip for path, clip in zip(self.join_inputs, clips) if str(path) == orientation_reference),
                None,
            )
            if reference is None or reference.rotation % 360 not in {90, 180, 270}:
                self._append_log("Não foi possível manter o formato original com giro; aplicando o giro nos frames.")
            else:
                preserve_rotation = True
        base = self._select_join_base(clips, profile_choice) if not preserve_rotation else reference
        visual_width, visual_height = base.width, base.height
        if base.rotation % 360 in {90, 270}:
            visual_width, visual_height = visual_height, visual_width
        profile = {
            "width": max(2, visual_width), "height": max(2, visual_height), "fps": base.fps,
            "video_bitrate": base.video_bitrate, "audio_bitrate": base.audio_bitrate,
            "audio_rate": base.audio_rate, "audio_channels": base.audio_channels,
            "audio_layout": base.audio_layout,
        }
        if preserve_rotation:
            self._append_log(
                f"Perfil de saída: {base.width}x{base.height} com giro de "
                f"{self._rotation_display_angle(base.rotation)}° (exibido {profile['width']}x{profile['height']}), "
                f"a {profile['fps']} fps, vídeo {profile['video_bitrate']}, áudio {profile['audio_bitrate']} "
                f"{profile['audio_rate']} Hz/{profile['audio_channels']} canal(is)."
            )
        else:
            self._append_log(
                f"Perfil de saída: {profile['width']}x{profile['height']} a {profile['fps']} fps, "
                f"vídeo {profile['video_bitrate']}, áudio {profile['audio_bitrate']} "
                f"{profile['audio_rate']} Hz/{profile['audio_channels']} canal(is)."
            )
        normalized = [
            f"{index}: {clip.width}x{clip.height}/{clip.fps}fps/rotação {clip.rotation}°"
            for index, clip in enumerate(clips, start=1)
            if (clip.width, clip.height, clip.fps, clip.rotation) != (base.width, base.height, base.fps, base.rotation)
        ]
        if normalized:
            self._append_log("Clipes normalizados para o perfil de saída: " + "; ".join(normalized))
        include_audio = any(clip.has_audio for clip in clips) and not audio_policy.startswith("Gerar saída sem áudio")
        if strategy == "Smart Join":
            # SmartJoin hibrido portado do Android: copia os corpos entre
            # keyframes em stream copy e recodifica apenas as emendas. Se o
            # plano for inviavel, interrompe com diagnostico (sem reencodar
            # o arquivo inteiro em silencio).
            self._smart_join_execute(
                [path for path in self.join_inputs],
                clips,
                output,
                transition_seconds,
                transition_label,
                include_audio,
            )
            return
        if transition_label == "Fade in/out":
            filters = self._fade_join_filter(clips, profile, transition_seconds, include_audio)
        else:
            filters = self._xfade_join_filter(clips, profile, transition_seconds, transition, include_audio)
        def build(acceleration):
            input_args = [str(self._ffmpeg()), "-hide_banner", "-y"]
            for path in self.join_inputs:
                input_args += ["-i", str(path)]
            prefix: list[str] = []
            filter_text = filters
            rotation_filter = self._rotation_storage_transpose(base.rotation) if preserve_rotation else ""
            if acceleration.key == "vaapi":
                prefix = ["-vaapi_device", "/dev/dri/renderD128"]
                if rotation_filter:
                    filter_text = filter_text + f";[vout]{rotation_filter}[vstore];[vstore]format=nv12,hwupload[vhw]"
                else:
                    filter_text = filter_text + ";[vout]format=nv12,hwupload[vhw]"
                map_video = "[vhw]"
            else:
                if rotation_filter:
                    filter_text = filter_text + f";[vout]{rotation_filter}[vstore]"
                    map_video = "[vstore]"
                else:
                    map_video = "[vout]"
            audio_output_args = ["-map", "[aout]", *self._join_audio_args(profile)] if include_audio else ["-an"]
            return [*input_args[:3], *prefix, *input_args[3:], "-filter_complex", filter_text, "-map", map_video, *audio_output_args, *self._video_args(acceleration, profile["video_bitrate"]), "-r", profile["fps"], "-movflags", "+faststart", str(encode_target)]
        output_duration = sum(item.duration for item in clips)
        if transition_label != "Fade in/out":
            output_duration -= transition_seconds * (len(clips) - 1)
        if preserve_rotation:
            # Passo 1: codifica na orientação de ARMAZENAMENTO (o autorotate dos
            # inputs consome a display matrix e o muxer não escreveria rotação).
            encode_target = self.output_dir / f"{output.stem}_tmp{output.suffix}"
            try:
                self._execute_video("Juntando vídeos", build, duration_seconds=max(0.1, output_duration))
                # Passo 2: remux rápido (-c copy) gravando a display matrix de
                # verdade no MP4 (mesmo mecanismo F-03 da ferramenta Girar).
                self._execute(
                    [
                        str(self._ffmpeg()), "-hide_banner", "-y",
                        "-display_rotation:v:0", str(base.rotation % 360),
                        "-i", str(encode_target), "-c", "copy", "-movflags", "+faststart", str(output),
                    ],
                    "Gravando giro de exibição no arquivo final",
                    1,
                    1,
                    max(0.1, output_duration),
                )
            finally:
                encode_target.unlink(missing_ok=True)
        else:
            encode_target = output
            self._execute_video("Juntando vídeos", build, duration_seconds=max(0.1, output_duration))

    def _video_normalize_filter(self, index: int, profile: dict) -> str:
        return f"[{index}:v]scale={profile['width']}:{profile['height']}:force_original_aspect_ratio=decrease,pad={profile['width']}:{profile['height']}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={profile['fps']},format=yuv420p,setpts=PTS-STARTPTS[v{index}]"

    def _audio_normalize_filter(self, index: int, clip: tuple, profile: dict) -> str:
        duration, has_audio, *_rest = clip
        if has_audio:
            return f"[{index}:a]aresample={profile['audio_rate']},aformat=sample_fmts=fltp:sample_rates={profile['audio_rate']}:channel_layouts={profile['audio_layout']},asetpts=PTS-STARTPTS[a{index}]"
        return f"anullsrc=channel_layout={profile['audio_layout']}:sample_rate={profile['audio_rate']},atrim=0:{self._fmt_seconds(duration)},asetpts=N/SR/TB[a{index}]"

    def _fade_join_filter(self, clips: list[tuple], profile: dict, seconds: float, include_audio: bool = True) -> str:
        parts: list[str] = []
        for index, clip in enumerate(clips):
            duration = clip[0]
            fade_duration = min(seconds, max(0.1, duration / 2))
            fade_out = max(0.0, duration - fade_duration)
            video_fades: list[str] = []
            audio_fades: list[str] = []
            if index > 0:
                video_fades.append(f"fade=t=in:st=0:d={self._fmt_seconds(fade_duration)}")
                audio_fades.append(f"afade=t=in:st=0:d={self._fmt_seconds(fade_duration)}")
            if index < len(clips) - 1:
                video_fades.append(f"fade=t=out:st={self._fmt_seconds(fade_out)}:d={self._fmt_seconds(fade_duration)}")
                audio_fades.append(f"afade=t=out:st={self._fmt_seconds(fade_out)}:d={self._fmt_seconds(fade_duration)}")
            video = (
                f"[{index}:v]scale={profile['width']}:{profile['height']}:force_original_aspect_ratio=decrease,"
                f"pad={profile['width']}:{profile['height']}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={profile['fps']},format=yuv420p,setpts=PTS-STARTPTS"
            )
            if video_fades:
                video += "," + ",".join(video_fades)
            video += f"[v{index}]"
            parts.append(video)
            if include_audio:
                audio = self._audio_normalize_filter(index, clip, profile)
                if audio_fades:
                    audio = audio.removesuffix(f"[a{index}]") + "," + ",".join(audio_fades) + f"[a{index}]"
                parts.append(audio)
        if include_audio:
            inputs = "".join(f"[v{index}][a{index}]" for index in range(len(clips)))
            parts.append(f"{inputs}concat=n={len(clips)}:v=1:a=1[vout][aout]")
        else:
            inputs = "".join(f"[v{index}]" for index in range(len(clips)))
            parts.append(f"{inputs}concat=n={len(clips)}:v=1:a=0[vout]")
        return ";".join(parts)

    def _xfade_join_filter(self, clips: list[tuple], profile: dict, seconds: float, transition: str, include_audio: bool = True) -> str:
        parts = [self._video_normalize_filter(index, profile) for index in range(len(clips))]
        if include_audio:
            parts.extend(self._audio_normalize_filter(index, clip, profile) for index, clip in enumerate(clips))
        if seconds <= 0.001:
            if include_audio:
                inputs = "".join(f"[v{index}][a{index}]" for index in range(len(clips)))
                parts.append(f"{inputs}concat=n={len(clips)}:v=1:a=1[vout][aout]")
            else:
                inputs = "".join(f"[v{index}]" for index in range(len(clips)))
                parts.append(f"{inputs}concat=n={len(clips)}:v=1:a=0[vout]")
            return ";".join(parts)
        last_video, last_audio = "v0", "a0"
        accumulated = clips[0][0]
        transition_name = "fade" if transition == "Fade in/out" else transition
        for index in range(1, len(clips)):
            video_out, audio_out = f"vx{index}", f"ax{index}"
            offset = max(0.0, accumulated - seconds)
            parts.append(f"[{last_video}][v{index}]xfade=transition={transition_name}:duration={self._fmt_seconds(seconds)}:offset={self._fmt_seconds(offset)},format=yuv420p[{video_out}]")
            if include_audio:
                parts.append(f"[{last_audio}][a{index}]acrossfade=d={self._fmt_seconds(seconds)}[{audio_out}]")
                last_audio = audio_out
            last_video = video_out
            accumulated += clips[index][0] - seconds
        parts.append(f"[{last_video}]copy[vout]")
        if include_audio:
            parts.append(f"[{last_audio}]acopy[aout]")
        return ";".join(parts)

    # =====================================================================
    # SmartJoin (portado do Android - SmartJoinPlanner.kt + FfmpegJoinVideosActivity)
    # Copia os corpos entre keyframes em stream copy e recodifica apenas as
    # emendas (bridges). NUNCA reencoda o arquivo inteiro silenciosamente.
    # =====================================================================

    @staticmethod
    def _smart_rotation_filters(degrees: int) -> list[str]:
        degrees = ((degrees % 360) + 360) % 360
        if degrees == 270:  # -90 -> transpose=1
            return ["transpose=1"]
        if degrees == 90:
            return ["transpose=2"]
        if degrees == 180:
            return ["hflip", "vflip"]
        return []

    @staticmethod
    def _smart_join_video_profile(media: MediaProfile) -> "smart_join_planner.VideoProfile":
        try:
            fps = float(Fraction(media.fps)) if media.fps else 30.0
        except (TypeError, ValueError, ZeroDivisionError):
            fps = 30.0
        return smart_join_planner.VideoProfile(
            codec_family=(media.video_codec or "h264"),
            width=media.width,
            height=media.height,
            fps=fps,
            rotation_degrees=media.rotation,
            pixel_format=(media.pix_fmt or None),
            sample_aspect_ratio=(media.sar or None),
            codec_profile=None,
        )

    def _smart_join_target_dict(self, target_media: MediaProfile) -> dict:
        """Perfil de saida normalizado a partir do clipe target do planner."""
        sar = (target_media.sar or "1:1")
        sar_filter = sar if sar and sar.replace(":", "/").count("/") == 1 else "1"
        return {
            "width": target_media.width or 1280,
            "height": target_media.height or 720,
            "fps": target_media.fps or "30",
            "rotation": target_media.rotation or 0,
            "codec_family": (target_media.video_codec or "h264"),
            "sar": sar_filter.replace(":", "/"),
            "audio_rate": target_media.audio_rate or 48000,
            "audio_channels": target_media.audio_channels or 2,
            "audio_layout": target_media.audio_layout or "stereo",
            "audio_bitrate": target_media.audio_bitrate or "128k",
        }

    def _smart_join_audio_window_filter(
        self,
        input_spec: str,
        clip_media: MediaProfile | None,
        duration: float,
        target: dict,
        output_label: str,
    ) -> str:
        rate = target["audio_rate"]
        layout = target["audio_layout"]
        if clip_media is not None and clip_media.has_audio:
            return (
                f"[{input_spec}]aresample={rate}:async=1:first_pts=0,"
                f"aformat=sample_fmts=fltp:sample_rates={rate}:channel_layouts={layout},"
                f"apad,atrim=duration={self._fmt_seconds(duration)},asetpts=N/SR/TB[{output_label}]"
            )
        return (
            f"anullsrc=channel_layout={layout}:sample_rate={rate},"
            f"atrim=duration={self._fmt_seconds(duration)},asetpts=N/SR/TB[{output_label}]"
        )

    def _smart_join_video_normalization_filter(
        self,
        source_media: MediaProfile,
        target: dict,
    ) -> str:
        parts = ["setpts=PTS-STARTPTS"]
        src_rot = ((source_media.rotation or 0) % 360 + 360) % 360
        tgt_rot = ((target.get("rotation") or 0) % 360 + 360) % 360
        if src_rot != tgt_rot:
            parts += self._smart_rotation_filters(src_rot)
            parts += self._smart_rotation_filters((-tgt_rot) % 360)
        # Ajustar pela proporção de EXIBIÇÃO também quando os SARs diferem.
        # Só setsar após scale esticaria os clipes normalizados.
        sar = target.get("sar") or "1"
        parts.append(
            f"scale=w='max(2,trunc(min({target['width']},{target['height']}*dar/({sar}))/2)*2)':"
            f"h='max(2,trunc(min({target['height']},{target['width']}*({sar})/dar)/2)*2)'"
        )
        parts.append(f"pad={target['width']}:{target['height']}:(ow-iw)/2:(oh-ih)/2")
        parts.append(f"setsar={target.get('sar') or '1'}")
        parts.append(f"fps={target['fps']}")
        parts.append("format=yuv420p")
        parts.append("settb=AVTB")
        parts.append("setpts=PTS-STARTPTS")
        return ",".join(parts)

    def _smart_join_acceleration_for_codec(self, codec_family: str) -> VideoAcceleration:
        """Devolve o VideoAcceleration do Windows adequado ao codec do target.

        Respeita a preferência CPU/GPU e resolve a variante do codec de saída
        no catálogo sondado. Não troca por CPU apenas porque a emenda é curta.
        Sem catálogo, usa o encoder selecionado compatível ou libx264/libx265.
        """
        path, advanced, available = self._worker_encoder_inputs()
        # O codec vem do perfil de saída. Preferir a variante da GPU sondada
        # para esse codec, sem aplicar fallback por trecho curto no SmartJoin.
        if available:
            choice = resolve_encoder(codec=codec_family, path=path, advanced=advanced,
                                     available=[option for option in available if option.encoder != "mpeg4"])
            if choice is not None:
                return self._catalog_video_acceleration(choice.option)
        accel = getattr(self, "acceleration", None)
        if accel is not None:
            enc = (accel.encoder or "").lower()
            if codec_family == "h264" and enc.startswith(("libx264", "h264_")):
                return accel
            if codec_family == "hevc" and enc.startswith(("libx265", "hevc_")):
                return accel
        if codec_family == "hevc":
            return VideoAcceleration("cpu", "CPU (HEVC)", "libx265")
        return VideoAcceleration("cpu", "CPU (fallback)", "libx264")

    def _smart_join_video_args(self, codec_family: str, bitrate: str) -> list[str]:
        """Argumentos de encoder do SmartJoin, delegando ao _video_args do Windows.

        Usa qualidade e velocidade do app com o codec do perfil escolhido.
        A pipeline ajusta a reordenação dos quadros às partes copiadas; em HEVC,
        o keyframe forçado no fim da emenda precisa ser IDR.
        """
        accel = self._smart_join_acceleration_for_codec(codec_family)
        args = self._video_args(accel, bitrate)
        if codec_family == "hevc":
            if accel.encoder in {"libx265", "hevc_nvenc"}:
                args += ["-forced-idr", "1"]
            elif accel.encoder in {"hevc_qsv", "hevc_amf"}:
                args += ["-forced_idr", "1"]
        return args

    def _smart_join_ts_bitstream(self, codec_family: str) -> str:
        return "hevc_mp4toannexb" if codec_family == "hevc" else "h264_mp4toannexb"

    def _smart_join_body_arguments(
        self,
        source: Path,
        media: MediaProfile,
        start_seconds: float,
        duration_seconds: float,
        copy_video: bool,
        target: dict,
        include_audio: bool,
        output_file: Path,
        output_as_mpeg_ts: bool = True,
        frame_count: int | None = None,
        decode_delay: float = 0.0,
        seek_offset: float = 0.0,
        leading_frames: int = 0,
    ) -> list[str]:
        args = [str(self._ffmpeg()), "-hide_banner", "-y"]
        if not copy_video:
            # arquivo incompativel pode carregar edit-list/PTS nao continuos
            args += ["-fflags", "+genpts"]
        # Seek de entrada preserva o IDR mesmo quando seu DTS precede o PTS.
        # Limitar também os pacotes evita incluir o próximo GOP por causa dos
        # B-frames. Áudio usa essa mesma janela, sem outro seek de saída.
        seek = start_seconds + seek_offset
        if abs(seek) > 0.000001:
            args += ["-ss", self._fmt_seconds(seek)]
        args += ["-noautorotate", "-display_rotation:v:0", "0", "-i", str(source)]
        if not copy_video or frame_count is None:
            args += ["-t", self._fmt_seconds(duration_seconds)]
        if frame_count is not None:
            args += ["-frames:v", str(frame_count + (leading_frames if copy_video else 0))]

        filters: list[str] = []
        if not copy_video:
            filters.append(
                f"[0:v:0]{self._smart_join_video_normalization_filter(media, target)},"
                f"tpad=stop_mode=clone:stop_duration={self._fmt_seconds(duration_seconds)},"
                f"trim=duration={self._fmt_seconds(duration_seconds)}[vout]"
            )
        audio_filter = ""
        if include_audio:
            audio_filter = self._smart_join_audio_window_filter(
                "0:a:0", media, duration_seconds, target, "aout0"
            )
            filters.append(audio_filter)
        if filters:
            args += ["-filter_complex", ";".join(filters)]
        args += ["-map", "0:v:0" if copy_video else "[vout]"]
        if include_audio:
            args += ["-map", "[aout0]"]

        if copy_video:
            args += ["-c:v", "copy"]
        else:
            # Encoder/qualidade do app Windows (_video_args), com o mesmo tail
            # que o join normal usa (fps + pix_fmt) para o TS ficar consistente
            # com os corpos copiados.
            source_bitrate = media.video_bitrate or "1M"
            args += self._smart_join_video_args(target["codec_family"], source_bitrate)
            args += ["-pix_fmt", "yuv420p", "-r", str(target["fps"]), "-bf", str(target.get("b_frames", 0))]
        if include_audio:
            args += [
                "-c:a", "aac", "-b:a", str(target["audio_bitrate"]),
                "-ar", str(target["audio_rate"]), "-ac", str(target["audio_channels"]),
            ]
        else:
            args += ["-an"]
        args += ["-map_metadata", "-1", "-avoid_negative_ts", "disabled"]
        if output_as_mpeg_ts:
            shift = max(0.0, target.get("decode_delay", 0.0) - decode_delay)
            bitstream = self._smart_join_ts_bitstream(target["codec_family"])
            if leading_frames:
                bitstream += ",noise=drop='lt(pts,0)'"
            if shift > 0.000001:
                bitstream += f",setts=pts=PTS:dts=DTS-{self._fmt_seconds(shift)}/TB"
            args += [
                "-bsf:v", bitstream,
                "-mpegts_flags", "+resend_headers+initial_discontinuity",
                "-muxdelay", "0", "-muxpreload", "0",
                "-f", "mpegts",
            ]
        else:
            args += ["-video_track_timescale", "90000", "-movflags", "+faststart"]
        args += [str(output_file)]
        return args

    def _smart_join_bridge_arguments(
        self,
        first_input: Path,
        second_input: Path,
        first_media: MediaProfile,
        second_media: MediaProfile,
        target: dict,
        junction: "smart_join_planner.JunctionPlan",
        fade_in_out: bool,
        xfade_transition: str,
        include_audio: bool,
        output_file: Path,
        frame_count: int | None = None,
        first_seek_offset: float = 0.0,
        second_seek_offset: float = 0.0,
    ) -> list[str]:
        transition = junction.incoming_transition_end_seconds
        outgoing_window = junction.outgoing_duration_seconds - junction.outgoing_bridge_start_seconds
        outgoing_prefix = junction.outgoing_transition_start_seconds - junction.outgoing_bridge_start_seconds
        incoming_window = junction.incoming_bridge_end_seconds
        incoming_suffix = incoming_window - transition
        min_seg = 0.020
        expected_duration = (
            outgoing_window + incoming_window
            if fade_in_out
            else outgoing_window + incoming_window - transition
        )

        args = [str(self._ffmpeg()), "-hide_banner", "-y", "-fflags", "+genpts"]
        # A bridge reencoda (sem stream copy) e o seek do 1o input e feito
        # antes dos inputs (input seek) - igual ao Android. A bridge nao sofre
        # do bug de -t ignorado (que so afeta stream copy de audio mono).
        seek = junction.outgoing_bridge_start_seconds + first_seek_offset
        if abs(seek) > 0.000001:
            args += ["-ss", self._fmt_seconds(seek)]
        args += ["-noautorotate", "-display_rotation:v:0", "0", "-i", str(first_input)]
        if abs(second_seek_offset) > 0.000001:
            args += ["-ss", self._fmt_seconds(second_seek_offset)]
        args += ["-noautorotate", "-display_rotation:v:0", "0", "-i", str(second_input)]

        nf_first = self._smart_join_video_normalization_filter(first_media, target)
        nf_second = self._smart_join_video_normalization_filter(second_media, target)
        filters = [
            f"[0:v:0]trim=duration={self._fmt_seconds(outgoing_window)},{nf_first},"
            f"tpad=stop_mode=clone:stop_duration={self._fmt_seconds(outgoing_window)},"
            f"trim=duration={self._fmt_seconds(outgoing_window)}[ovbase]",
            f"[1:v:0]trim=duration={self._fmt_seconds(incoming_window)},{nf_second},"
            f"tpad=stop_mode=clone:stop_duration={self._fmt_seconds(incoming_window)},"
            f"trim=duration={self._fmt_seconds(incoming_window)}[ivbase]",
        ]
        if fade_in_out:
            filters.append(
                f"[ovbase]fade=t=out:st={self._fmt_seconds(max(0.0, outgoing_window - transition))}:"
                f"d={self._fmt_seconds(transition)}[ovfade]"
            )
            filters.append(f"[ivbase]fade=t=in:st=0:d={self._fmt_seconds(transition)}[ivfade]")
            filters.append("[ovfade][ivfade]concat=n=2:v=1:a=0[vout]")
        else:
            video_sequence: list[str] = []
            if outgoing_prefix > min_seg:
                filters.append("[ovbase]split=2[ovprefixsrc][ovtailsrc]")
                filters.append(
                    f"[ovprefixsrc]trim=duration={self._fmt_seconds(outgoing_prefix)},"
                    "setpts=PTS-STARTPTS[ovprefix]"
                )
                filters.append(
                    f"[ovtailsrc]trim=start={self._fmt_seconds(outgoing_prefix)}:"
                    f"duration={self._fmt_seconds(transition)},setpts=PTS-STARTPTS[ovtail]"
                )
                video_sequence += ["ovprefix"]
            else:
                filters.append(
                    f"[ovbase]trim=duration={self._fmt_seconds(transition)},setpts=PTS-STARTPTS[ovtail]"
                )
            if incoming_suffix > min_seg:
                filters.append("[ivbase]split=2[ivheadsrc][ivsuffixsrc]")
                filters.append(
                    f"[ivheadsrc]trim=duration={self._fmt_seconds(transition)},setpts=PTS-STARTPTS[ivhead]"
                )
                filters.append(
                    f"[ivsuffixsrc]trim=start={self._fmt_seconds(transition)}:"
                    f"duration={self._fmt_seconds(incoming_suffix)},setpts=PTS-STARTPTS[ivsuffix]"
                )
            else:
                filters.append(
                    f"[ivbase]trim=duration={self._fmt_seconds(transition)},setpts=PTS-STARTPTS[ivhead]"
                )
            filters.append(
                f"[ovtail][ivhead]xfade=transition={xfade_transition}:"
                f"duration={self._fmt_seconds(transition)}:offset=0[vxfade]"
            )
            video_sequence += ["vxfade"]
            if incoming_suffix > min_seg:
                video_sequence += ["ivsuffix"]
            filters.append(
                (f"[{video_sequence[0]}]null[vout]"
                 if len(video_sequence) == 1
                 else "".join(f"[{label}]" for label in video_sequence)
                       + f"concat=n={len(video_sequence)}:v=1:a=0[vout]")
            )

        if include_audio:
            outgoing_base = "oabase0"
            incoming_base = "iabase0"
            filters.append(
                self._smart_join_audio_window_filter(
                    "0:a:0", first_media, outgoing_window, target, outgoing_base
                )
            )
            filters.append(
                self._smart_join_audio_window_filter(
                    "1:a:0", second_media, incoming_window, target, incoming_base
                )
            )
            if fade_in_out:
                filters.append(
                    f"[{outgoing_base}]afade=t=out:st={self._fmt_seconds(max(0.0, outgoing_window - transition))}:"
                    f"d={self._fmt_seconds(transition)}[oafade0]"
                )
                filters.append(
                    f"[{incoming_base}]afade=t=in:st=0:d={self._fmt_seconds(transition)}[iafade0]"
                )
                filters.append("[oafade0][iafade0]concat=n=2:v=0:a=1[aout0]")
            else:
                audio_sequence: list[str] = []
                if outgoing_prefix > min_seg:
                    filters.append(f"[{outgoing_base}]asplit=2[oaprefixsrc0][oatailsrc0]")
                    filters.append(
                        f"[oaprefixsrc0]atrim=duration={self._fmt_seconds(outgoing_prefix)},"
                        "asetpts=N/SR/TB[oaprefix0]"
                    )
                    filters.append(
                        f"[oatailsrc0]atrim=start={self._fmt_seconds(outgoing_prefix)}:"
                        f"duration={self._fmt_seconds(transition)},asetpts=N/SR/TB[oatail0]"
                    )
                    audio_sequence += ["oaprefix0"]
                else:
                    filters.append(
                        f"[{outgoing_base}]atrim=duration={self._fmt_seconds(transition)},"
                        "asetpts=N/SR/TB[oatail0]"
                    )
                if incoming_suffix > min_seg:
                    filters.append(f"[{incoming_base}]asplit=2[iaheadsrc0][iasuffixsrc0]")
                    filters.append(
                        f"[iaheadsrc0]atrim=duration={self._fmt_seconds(transition)},asetpts=N/SR/TB[iahead0]"
                    )
                    filters.append(
                        f"[iasuffixsrc0]atrim=start={self._fmt_seconds(transition)}:"
                        f"duration={self._fmt_seconds(incoming_suffix)},asetpts=N/SR/TB[iasuffix0]"
                    )
                else:
                    filters.append(
                        f"[{incoming_base}]atrim=duration={self._fmt_seconds(transition)},asetpts=N/SR/TB[iahead0]"
                    )
                filters.append(
                    f"[oatail0][iahead0]acrossfade=d={self._fmt_seconds(transition)}:c1=tri:c2=tri[axfade0]"
                )
                audio_sequence += ["axfade0"]
                if incoming_suffix > min_seg:
                    audio_sequence += ["iasuffix0"]
                filters.append(
                    (f"[{audio_sequence[0]}]anull[aout0]"
                     if len(audio_sequence) == 1
                     else "".join(f"[{label}]" for label in audio_sequence)
                           + f"concat=n={len(audio_sequence)}:v=0:a=1[aout0]")
                )

        args += ["-filter_complex", ";".join(filters), "-map", "[vout]"]
        if include_audio:
            args += ["-map", "[aout0]"]
        # Encoder/qualidade do app Windows (mesma politica do join normal).
        args += self._smart_join_video_args(
            target["codec_family"], first_media.video_bitrate or "1M"
        )
        args += ["-pix_fmt", "yuv420p", "-r", str(target["fps"]), "-bf", str(target.get("b_frames", 0))]
        if frame_count is not None:
            # Fechar a emenda com IDR esvazia os quadros pendentes antes do
            # GOP copiado seguinte, sem recodificar esse corpo.
            args += ["-frames:v", str(frame_count), "-force_key_frames", f"expr:eq(n,{frame_count - 1})"]
        if include_audio:
            args += [
                "-c:a", "aac", "-b:a", str(target["audio_bitrate"]),
                "-ar", str(target["audio_rate"]), "-ac", str(target["audio_channels"]),
            ]
        else:
            args += ["-an"]
        args += [
            "-t", self._fmt_seconds(max(0.01, expected_duration)),
            "-map_metadata", "-1", "-avoid_negative_ts", "disabled",
            "-video_track_timescale", "90000", "-movflags", "+faststart",
            str(output_file),
        ]
        return args

    def _smart_join_ts_arguments(
        self,
        input_file: Path,
        output_file: Path,
        codec_family: str,
        include_audio: bool,
        decode_delay: float = 0.0,
    ) -> list[str]:
        args = [str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(input_file), "-map", "0:v:0"]
        if include_audio:
            args += ["-map", "0:a?"]
        bitstream = self._smart_join_ts_bitstream(codec_family)
        if decode_delay > 0.000001:
            bitstream += f",setts=pts=PTS:dts=DTS-{self._fmt_seconds(decode_delay)}/TB"
        args += [
            "-c", "copy",
            "-bsf:v", bitstream,
            "-avoid_negative_ts", "disabled",
            "-mpegts_flags", "+resend_headers+initial_discontinuity",
            "-muxdelay", "0", "-muxpreload", "0",
            "-f", "mpegts",
            str(output_file),
        ]
        return args

    def _smart_join_concat_arguments(
        self,
        pieces: list[Path],
        output_file: Path,
        target: dict,
        include_audio: bool,
        manifest_path: Path,
        durations: list[float] | None = None,
        paths: list[Path] | None = None,
        medias: list[MediaProfile] | None = None,
        transition_seconds: float = 0.0,
        fade_in_out: bool = False,
        input_offsets: list[float] | None = None,
    ) -> list[str]:
        if durations is not None and len(durations) != len(pieces):
            raise ValueError("Durações dos segmentos não correspondem ao manifesto")
        manifest_path.write_text(
            "\n".join(
                f"file '{self._concat_escape(str(path.resolve()))}'"
                + (f"\nduration {self._fmt_seconds(durations[index])}" if durations is not None else "")
                for index, path in enumerate(pieces)
            ),
            encoding="utf-8",
        )
        args = [
            str(self._ffmpeg()), "-hide_banner", "-y",
            "-display_rotation:v:0", str(target.get("rotation") or 0),
            "-fflags", "+genpts",
            "-f", "concat", "-safe", "0", "-i", str(manifest_path),
        ]
        if include_audio and paths and medias:
            # Áudio é decodificado/codificado uma única vez. Não há AAC delay
            # acumulado em corpos/emendas nem lacunas quando falta uma faixa.
            for index, path in enumerate(paths):
                if input_offsets and abs(input_offsets[index]) > 0.000001:
                    args += ["-ss", self._fmt_seconds(input_offsets[index])]
                args += ["-i", str(path)]
            filters = []
            labels = []
            for index, media in enumerate(medias):
                label = f"aj{index}"
                filters.append(self._smart_join_audio_window_filter(
                    f"{index + 1}:a:0", media, media.duration, target, label
                ))
                if fade_in_out and transition_seconds > 0:
                    fades = []
                    if index > 0:
                        fades.append(f"afade=t=in:st=0:d={self._fmt_seconds(transition_seconds)}")
                    if index < len(medias) - 1:
                        fades.append(f"afade=t=out:st={self._fmt_seconds(media.duration - transition_seconds)}:d={self._fmt_seconds(transition_seconds)}")
                    filters.append(f"[{label}]{','.join(fades)}[{label}f]")
                    label += "f"
                labels.append(label)
            if not fade_in_out and transition_seconds > 0:
                previous = labels[0]
                for index, label in enumerate(labels[1:], 1):
                    output_label = f"axj{index}"
                    filters.append(f"[{previous}][{label}]acrossfade=d={self._fmt_seconds(transition_seconds)}:c1=tri:c2=tri[{output_label}]")
                    previous = output_label
                filters.append(f"[{previous}]anull[aout]")
            else:
                filters.append(''.join(f"[{label}]" for label in labels) + f"concat=n={len(labels)}:v=0:a=1[aout]")
            args += ["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[aout]",
                     "-c:v", "copy", "-c:a", "aac", "-b:a", str(target["audio_bitrate"]),
                     "-ar", str(target["audio_rate"]), "-ac", str(target["audio_channels"])]
        else:
            args += ["-map", "0:v:0", "-c:v", "copy", "-an"]
        if target["codec_family"] == "hevc":
            # hev1 sinaliza VPS/SPS/PPS dentro do stream: as emendas podem
            # usar parâmetros distintos dos corpos copiados.
            args += ["-tag:v", "hev1"]
        args += [
            "-avoid_negative_ts", "disabled",
            "-max_interleave_delta", "0",
            "-video_track_timescale", "90000",
            "-movflags", "+faststart",
            str(output_file),
        ]
        return args

    def _smart_join_probe(self, path: Path, packets: bool = False, first_packets: bool = False,
                          frames_interval: tuple[float, float] | None = None,
                          packet_stream: str = "v:0") -> dict:
        """Sonda pacotes sem decodificar vídeo; permite cancelar arquivos longos."""
        ffprobe = self._get_ffprobe()
        if not ffprobe:
            raise RuntimeError("FFprobe não foi encontrado; não é possível validar o SmartJoin.")
        command = [str(ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json"]
        if packets:
            command += ["-select_streams", packet_stream, "-show_packets", "-show_entries",
                        "packet=pts_time,dts_time,duration_time,flags,pos,size:packet_side_data=skip_samples,discard_padding:stream=codec_type,codec_name,width,height,pix_fmt,sample_aspect_ratio,r_frame_rate,avg_frame_rate,has_b_frames,start_time,duration,duration_ts,time_base,sample_rate,channels,channel_layout,sample_fmt,bits_per_raw_sample,color_primaries,color_transfer,color_space,color_range:format=start_time,duration"]
            if first_packets:
                command += ["-read_intervals", "%+0.1"]
        if frames_interval is not None:
            start, end = frames_interval
            command += ["-select_streams", "v:0", "-show_frames", "-show_entries",
                        "frame=pts_time,best_effort_timestamp_time", "-read_intervals",
                        f"{self._fmt_seconds(start)}%{self._fmt_seconds(end)}"]
        command += [str(path)]
        self._record_ffmpeg_command(command, probe=True)
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0) as process:
            while True:
                if self.cancel_event.is_set():
                    process.kill()
                    process.communicate()
                    raise Cancelled()
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
        if process.returncode or (frames_interval is not None and stderr.strip()):
            raise RuntimeError(f"Não consegui analisar {path.name}: {stderr.decode('utf-8', 'replace')[-600:]}")
        try:
            return json.loads(stdout)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"Sonda inválida para {path.name}") from exc

    def _smart_join_validate_video(self, path: Path, expected: float, frame_count: int,
                                   fps: float, max_source_gap: float = 0.0) -> None:
        info = self._smart_join_probe(path, packets=True)
        packets = info.get("packets", [])
        times = sorted(float(p["pts_time"]) for p in packets if "pts_time" in p)
        tolerance = max(0.002, 1.1 / fps)
        if len(times) != frame_count or not times:
            raise RuntimeError(f"SmartJoin: vídeo incompleto em {path.name} ({len(times)}/{frame_count} quadros).")
        end = max(float(p["pts_time"]) + float(p.get("duration_time", 1 / fps))
                  for p in packets if "pts_time" in p)
        if abs(times[0]) > tolerance or abs(end - expected) > tolerance:
            raise RuntimeError(f"SmartJoin: janela de vídeo incorreta em {path.name} ({times[0]:.3f}–{end:.3f}s; esperado 0–{expected:.3f}s).")
        gap_limit = max(2.1 / fps, max_source_gap + 1.1 / fps)
        if any(b - a > gap_limit or b - a <= 0 for a, b in zip(times, times[1:])):
            raise RuntimeError(f"SmartJoin: descontinuidade nos quadros de {path.name}.")

    def _smart_join_validate_piece(self, path: Path, target: dict) -> None:
        # Um TS de poucos quadros pode ser confundido com MPEG-PS no probing
        # automático do concat. Pacotes null tornam o container identificável,
        # sem adicionar quadros, som ou tempo à peça.
        if path.stat().st_size < 4096:
            null_packet = b"\x47\x1f\xff\x10" + b"\xff" * 184
            with path.open("ab") as stream:
                stream.write(null_packet * 32)
        info = self._smart_join_probe(path)
        videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
        if not videos or any(
            (v.get("codec_name"), v.get("width"), v.get("height"))
            != (target["codec_family"], target["width"], target["height"])
            for v in videos
        ):
            raise RuntimeError(f"SmartJoin: segmento inválido ({path.name}).")

    def _smart_join_encoded_delay(self, path: Path) -> float:
        packets = self._smart_join_probe(path, packets=True, first_packets=True).get("packets", [])
        if not packets:
            raise RuntimeError(f"SmartJoin: a recodificação não gerou quadros em {path.name}.")
        first = packets[0]
        return max(0.0, float(first["pts_time"]) - float(first.get("dts_time", first["pts_time"])))

    def _smart_join_validate_decoded_junction(self, path: Path, start: float, duration: float,
                                             fps: float) -> None:
        # Só decodifica a emenda e alguns quadros seguintes. Pacotes podem ter
        # PTS válidos enquanto um GOP aberto/SPS causa saída fora de ordem no
        # decoder; não justificaríamos decodificar todos os corpos copiados.
        info = self._smart_join_probe(path, frames_interval=(start + .5 / fps, start + duration + 4 / fps))
        times = [float(frame.get("pts_time", frame.get("best_effort_timestamp_time", "nan")))
                 for frame in info.get("frames", [])]
        if not times or any(not math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
            raise RuntimeError("SmartJoin: o decoder encontrou quadros fora de ordem em uma emenda.")

    def _smart_join_execute(
        self,
        paths: list[Path],
        medias: list[MediaProfile],
        output: Path,
        transition_seconds: float,
        transition_label: str,
        include_audio: bool,
    ) -> None:
        """Copia corpos, codifica emendas e monta áudio uma única vez.

        Valida a timeline antes de publicar o arquivo. Nunca substitui um plano
        inviável por recodificação completa silenciosa.
        """
        fade_in_out = transition_label == "Fade in/out"
        xfade_name = self.VIDEO_TRANSITION_CODES.get(transition_label, transition_label)
        if fade_in_out:
            xfade_name = "fade"

        self._append_log(f"SmartJoin: analisando perfis e keyframes de {len(paths)} clipe(s).")
        sources: list[smart_join_planner.Source] = []
        packet_infos = []
        prepared_sources = {}
        max_source_gap = 0.0
        for index, (path, media) in enumerate(zip(paths, medias)):
            if path in prepared_sources:
                cached_media, cached_source, cached_packets, cached_gap = prepared_sources[path]
                medias[index] = cached_media
                sources.append(cached_source)
                packet_infos.append(cached_packets)
                max_source_gap = max(max_source_gap, cached_gap)
                continue
            info = self._smart_join_probe(path, packets=True)
            packets = info.get("packets", [])
            if not packets or not info.get("streams"):
                raise RuntimeError(f"Não consegui identificar os quadros de {path.name}.")
            stream = info["streams"][0]
            origin = float(stream.get("start_time", 0))
            if any("pts_time" not in p or not math.isfinite(float(p["pts_time"])) for p in packets):
                raise RuntimeError(f"Há quadros sem timestamp válido em {path.name}.")
            ordered_times = [float(p["pts_time"]) - origin for p in packets]
            visible_indices = [i for i,p in enumerate(packets) if "D" not in p.get("flags", "") and ordered_times[i] >= -0.000001]
            times = sorted(ordered_times[i] for i in visible_indices)
            if not times:
                raise RuntimeError(f"Não há quadros visíveis em {path.name}.")
            key_indices = [i for i,p in enumerate(packets) if "K" in p.get("flags", "")]
            keyframes = [ordered_times[i] for i in key_indices if "D" not in packets[i].get("flags", "")]
            safe_ends, leading, key_delays = [], {}, {}
            tail_repair = None
            hidden_reference = next((i for i,p in enumerate(packets) if i < max(visible_indices) and "D" in p.get("flags", "") and ordered_times[i] >= -0.000001), None)
            if hidden_reference is not None:
                group_start = max((i for i in key_indices if i <= hidden_reference),default=0)
                group_end = next((i for i in key_indices if i > group_start),len(packets))
                tail_repair = max(0.0,min(ordered_times[group_start:group_end]))
            for number, packet_index in enumerate(key_indices):
                if "D" in packets[packet_index].get("flags", ""):
                    continue
                key_time = ordered_times[packet_index]
                next_index = key_indices[number + 1] if number + 1 < len(key_indices) else len(packets)
                group = ordered_times[packet_index:next_index]
                safe_ends.append((key_time, min(group)))
                leading[key_time] = sum(t < key_time - 0.000001 for t in group)
                packet = packets[packet_index]
                key_delays[key_time] = max(0.0, float(packet["pts_time"]) - float(packet.get("dts_time", packet["pts_time"])))
            source_gap = max((b - a for a, b in zip(times, times[1:])), default=0.0)
            max_source_gap = max(max_source_gap, source_gap)
            seek_offset = origin - float(info.get("format", {}).get("start_time", 0))
            try:
                duration = float(stream.get("duration") or media.duration)
            except (TypeError, ValueError):
                duration = media.duration
            # Não arredondar 30000/1001 para 29.97 nem a duração para centésimos.
            media = replace(media, fps=stream.get("r_frame_rate") or media.fps,
                            duration=duration if abs(duration - media.duration) < 0.05 else media.duration)
            medias[index] = media
            packet_infos.append((times, key_delays, seek_offset, leading, int(stream.get("has_b_frames", 0))))
            sources.append(
                smart_join_planner.Source(
                    duration_seconds=media.duration,
                    profile=self._smart_join_video_profile(media),
                    keyframes_seconds=keyframes,
                    safe_copy_ends=safe_ends,
                    tail_repair_start_seconds=tail_repair,
                )
            )
            prepared_sources[path] = (media, sources[-1], packet_infos[-1], source_gap)
            # Guardar apenas PTS/chaves compactos. O JSON completo de pacotes
            # de vários vídeos longos consumiria centenas de MB desnecessários.
            del info, packets

        choice = str(self._worker_value_default("join_profile", "join_profile_var", "Automático (preservar mais vídeo)"))
        base = self._select_join_base(medias, choice)
        target_index = next(index for index, media in enumerate(medias) if media is base)
        fps = float(Fraction(base.fps))
        if not math.isfinite(fps) or fps <= 0:
            raise RuntimeError("Não consegui identificar a taxa de quadros do perfil escolhido.")
        if 0 < transition_seconds < 0.5 / fps:
            transition_seconds = 0.0
            self._append_log("A transição é menor que meio quadro; os clipes serão unidos sem efeito.")
        plan_result = smart_join_planner.plan(sources, transition_seconds, fade_in_out, target_index=target_index)
        if not plan_result.can_smart_join:
            raise RuntimeError(plan_result.ineligibility_reason or "SmartJoin não aplicável.")
        if not any(clip.copy_video and clip.body_duration_seconds > 0.000001 for clip in plan_result.clips):
            raise RuntimeError(
                "Nenhum corpo de vídeo pôde ser preservado por stream copy: "
                "o SmartJoin recodificaria tudo e não traria ganho. "
                "Escolha outro perfil de saída ou use Reencode Completo."
            )
        decode_delay = max(
            packet_infos[clip.index][1].get(clip.body_start_seconds, 0.0)
            for clip in plan_result.clips if clip.copy_video and clip.body_duration_seconds > 0.000001
        )

        copied_count = sum(1 for clip in plan_result.clips if clip.copy_video and clip.body_duration_seconds > 0.000001)
        self._append_log(
            f"SmartJoin: {copied_count}/{len(plan_result.clips)} corpos em stream copy; "
            f"target = clipe {plan_result.target_index + 1} "
            f"({plan_result.target_profile.width}x{plan_result.target_profile.height})."
        )
        for clip_plan in plan_result.clips:
            self._append_log(
                f"SmartJoin plano clipe {clip_plan.index + 1}: copy={clip_plan.copy_video} "
                f"corpo=[{clip_plan.body_start_seconds:.3f},{clip_plan.body_end_seconds:.3f}] "
                f"({clip_plan.body_duration_seconds:.3f}s)"
                + (f" motivo={clip_plan.incompatibility_reason}" if clip_plan.incompatibility_reason else "")
            )
        for junction in plan_result.junctions:
            self._append_log(
                f"SmartJoin emenda {junction.index + 1}: bridge_start="
                f"{junction.outgoing_bridge_start_seconds:.3f} trans_start="
                f"{junction.outgoing_transition_start_seconds:.3f} incoming_end="
                f"{junction.incoming_bridge_end_seconds:.3f}"
            )
        target_media = medias[plan_result.target_index]
        target = self._smart_join_target_dict(target_media)
        target["codec_family"] = (
            "hevc" if smart_join_planner._normalize_codec(plan_result.target_profile.codec_family) == "hevc" else "h264"
        )
        acceleration = self._smart_join_acceleration_for_codec(target["codec_family"])
        self._append_log(f"SmartJoin: encoder das partes recodificadas: {acceleration.label} ({acceleration.encoder}).")
        target["decode_delay"] = decode_delay
        fps = float(Fraction(target["fps"]))
        # Manter a profundidade de reordenação do vídeo copiado evita que o
        # decoder HEVC solte o CRA seguinte antes dos últimos quadros da emenda.
        target["b_frames"] = max(
            packet_infos[clip.index][4] for clip in plan_result.clips
            if clip.copy_video and clip.body_duration_seconds > 0.000001
        )
        if target["codec_family"] == "hevc":
            # O CRA de um GOP aberto pode exigir um quadro a mais de atraso
            # que o IDR inicial. As emendas seguem a maior janela realmente
            # usada pelos GOPs que entram em cópia.
            target["b_frames"] = max(target["b_frames"], math.ceil(decode_delay * fps - .000001))
        order = smart_join_segment_order(
            len(plan_result.clips), [c.body_duration_seconds > 0.000001 for c in plan_result.clips],
            [j.index for j in plan_result.junctions],
        )
        order = [entry for original in order for entry in
                 ([original, ("tail", original[1])] if original[0] == "body" and plan_result.clips[original[1]].tail_duration_seconds > 0.000001 else [original])]
        # A clip with no copied body can still contribute a repaired tail.
        for clip in plan_result.clips:
            if clip.body_duration_seconds <= 0.000001 and clip.tail_duration_seconds > 0.000001:
                before = next((i for i,(kind,index) in enumerate(order) if kind == "bridge" and index == clip.index),len(order))
                order.insert(before,("tail",clip.index))
        durations = {}
        counts = {}
        logical_end = 0.0
        scheduled_end = 0.0
        for kind, index in order:
            if kind == "body":
                clip = plan_result.clips[index]
                duration = clip.body_duration_seconds
            elif kind == "tail":
                duration = plan_result.clips[index].tail_duration_seconds
            else:
                duration = smart_join_planner.junction_duration_seconds(plan_result.junctions[index], fade_in_out)
            logical_end += duration
            if kind == "body" and clip.copy_video:
                times = packet_infos[index][0]
                count = sum(clip.body_start_seconds - 0.000001 <= t < clip.body_end_seconds - 0.000001 for t in times)
            else:
                count = max(1, round((logical_end - scheduled_end) * fps))
                duration = count / fps
            if count <= 0:
                raise RuntimeError("SmartJoin: um corpo planejado não contém quadros copiáveis.")
            durations[kind, index] = duration
            counts[kind, index] = count
            scheduled_end += duration

        work_dir = self._work_directory("smart_join", self.output_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        pieces: list[Path] = []
        total_steps = sum(1 if c.copy_video else 2 for c in plan_result.clips if c.body_duration_seconds > 0.000001) + len(plan_result.junctions) * 2 + sum(c.tail_duration_seconds > 0.000001 for c in plan_result.clips) * 2 + 1
        staged_output = work_dir / "resultado.mp4"
        step = 0
        try:
            for index, clip_plan in enumerate(plan_result.clips):
                if self.cancel_event.is_set():
                    raise Cancelled()
                if clip_plan.body_duration_seconds <= 0.000001:
                    continue
                step += 1
                ts_path = work_dir / f"body_{index:03d}.ts"
                if clip_plan.copy_video:
                    self._append_log(f"SmartJoin: copiando corpo {index + 1}/{len(paths)} (stream copy).")
                    body_cmd = self._smart_join_body_arguments(
                        paths[index], medias[index],
                        clip_plan.body_start_seconds, durations["body", index],
                        copy_video=True, target=target, include_audio=False,
                        output_file=ts_path, output_as_mpeg_ts=True,
                        frame_count=counts["body", index], decode_delay=packet_infos[index][1].get(clip_plan.body_start_seconds, 0.0),
                        seek_offset=packet_infos[index][2],
                        leading_frames=packet_infos[index][3].get(clip_plan.body_start_seconds, 0),
                    )
                    self._execute(
                        body_cmd, f"SmartJoin corpo {index + 1} (copy)", step, total_steps,
                        clip_plan.body_duration_seconds,
                    )
                else:
                    self._append_log(f"SmartJoin: recodificando clipe {index + 1}/{len(paths)} incompatível.")
                    mp4_path = work_dir / f"body_{index:03d}.mp4"
                    body_cmd = self._smart_join_body_arguments(
                        paths[index], medias[index],
                        clip_plan.body_start_seconds, durations["body", index],
                        copy_video=False, target=target, include_audio=False,
                        output_file=mp4_path, output_as_mpeg_ts=False,
                        frame_count=counts["body", index], seek_offset=packet_infos[index][2],
                    )
                    self._execute(
                        body_cmd, f"SmartJoin recodificando clipe {index + 1}", step, total_steps,
                        clip_plan.body_duration_seconds,
                    )
                    step += 1
                    ts_cmd = self._smart_join_ts_arguments(
                        mp4_path, ts_path, target["codec_family"], False,
                        decode_delay=max(0.0, decode_delay - self._smart_join_encoded_delay(mp4_path)),
                    )
                    self._execute(
                        ts_cmd, f"SmartJoin preparando corpo {index + 1}", step, total_steps,
                        clip_plan.body_duration_seconds,
                    )
                self._smart_join_validate_piece(ts_path, target)

            for junction in plan_result.junctions:
                if self.cancel_event.is_set():
                    raise Cancelled()
                step += 1
                j = junction.index
                self._append_log(f"SmartJoin: recodificando emenda {j + 1}/{len(plan_result.junctions)}.")
                mp4_path = work_dir / f"bridge_{j:03d}.mp4"
                ts_path = work_dir / f"bridge_{j:03d}.ts"
                bridge_cmd = self._smart_join_bridge_arguments(
                    paths[j], paths[j + 1],
                    medias[j], medias[j + 1],
                    target, junction, fade_in_out, xfade_name, False,
                    mp4_path,
                    frame_count=counts["bridge", j],
                    first_seek_offset=packet_infos[j][2], second_seek_offset=packet_infos[j + 1][2],
                )
                self._execute(
                    bridge_cmd, f"SmartJoin emenda {j + 1}", step, total_steps,
                    max(0.1, smart_join_planner.junction_duration_seconds(junction, fade_in_out)),
                )
                step += 1
                ts_cmd = self._smart_join_ts_arguments(
                    mp4_path, ts_path, target["codec_family"], False,
                    decode_delay=max(0.0, decode_delay - self._smart_join_encoded_delay(mp4_path)),
                )
                self._execute(
                    ts_cmd, f"SmartJoin preparando emenda {j + 1}", step, total_steps,
                    max(0.1, smart_join_planner.junction_duration_seconds(junction, fade_in_out)),
                )
                self._smart_join_validate_piece(ts_path, target)

            for clip in plan_result.clips:
                if clip.tail_duration_seconds <= 0.000001:
                    continue
                index = clip.index
                mp4_path, ts_path = work_dir / f"tail_{index:03d}.mp4", work_dir / f"tail_{index:03d}.ts"
                command = self._smart_join_body_arguments(paths[index],medias[index],clip.tail_start_seconds,durations["tail",index],
                    copy_video=False,target=target,include_audio=False,output_file=mp4_path,output_as_mpeg_ts=False,
                    frame_count=counts["tail",index],seek_offset=packet_infos[index][2])
                step += 1
                self._execute(command,f"SmartJoin reparando último GOP do clipe {index+1}",step,total_steps,clip.tail_duration_seconds)
                step += 1
                self._execute(self._smart_join_ts_arguments(mp4_path,ts_path,target["codec_family"],False,
                    decode_delay=max(0.0,decode_delay-self._smart_join_encoded_delay(mp4_path))),
                    f"SmartJoin preparando cauda {index+1}",step,total_steps,clip.tail_duration_seconds)
                self._smart_join_validate_piece(ts_path,target)

            # F7: a ORDEM dos segmentos é o que define o arquivo final. Os dois
            # laços acima só criam os arquivos; aqui eles entram intercalados —
            # corpo 1, emenda 1, corpo 2, emenda 2, … (a junção j fica entre o
            # corpo j e o corpo j+1, como no plano). Antes as emendas iam todas
            # para o fim e o SmartJoin com transição saía fora de ordem:
            # medido no N4, a linha do tempo foi 2>3>4>5>1.
            pieces = []
            for tipo, index in order:
                arquivo = work_dir / f"{tipo}_{index:03d}.ts"
                if not arquivo.exists():
                    raise RuntimeError(f"SmartJoin: segmento ausente ({arquivo.name}).")
                pieces.append(arquivo)
            if not pieces:
                raise RuntimeError("O SmartJoin não gerou segmentos.")
            step += 1
            manifest_path = self._work_file(work_dir, "manifest", ".txt")
            concat_cmd = self._smart_join_concat_arguments(
                pieces, staged_output, target, include_audio, manifest_path,
                durations=[durations[key] for key in order], paths=paths, medias=medias,
                transition_seconds=plan_result.transition_seconds, fade_in_out=fade_in_out,
                input_offsets=[info[2] for info in packet_infos],
            )
            expected = plan_result.expected_duration_seconds([m.duration for m in medias])
            self._execute(concat_cmd, "SmartJoin: unindo segmentos", step, total_steps, expected)
            try:
                manifest_path.unlink(missing_ok=True)
            except OSError:
                pass

            def validate_final():
                self._smart_join_validate_video(staged_output, expected, sum(counts.values()), fps, max_source_gap)
                position = 0.0
                for key in order:
                    if key[0] in {"bridge", "tail"}:
                        self._smart_join_validate_decoded_junction(staged_output, position, durations[key], fps)
                    position += durations[key]
                final_info = self._smart_join_probe(staged_output)
                audio_streams = [s for s in final_info.get("streams", []) if s.get("codec_type") == "audio"]
                if include_audio:
                    if len(audio_streams) != 1:
                        raise RuntimeError("SmartJoin: a faixa de áudio final está ausente.")
                    audio = audio_streams[0]
                    tolerance = max(1.1 / fps, 2048 / target["audio_rate"])
                    if abs(float(audio.get("start_time", 0))) > tolerance or abs(float(audio.get("duration", 0)) - expected) > tolerance:
                        raise RuntimeError("SmartJoin: a duração do áudio não acompanha o vídeo.")
                elif audio_streams:
                    raise RuntimeError("SmartJoin: a saída deveria estar sem áudio.")
            self._validate_completed_output(staged_output, validate_final)
            if self.cancel_event.is_set():
                raise Cancelled()
            self._publish_completed_output(staged_output, output)
            self._append_log(f"SmartJoin concluído: {expected:.2f}s em {len(pieces)} segmento(s).")
        finally:
            try:
                self._remove_work_directory(work_dir)
            except Exception:
                pass

    def _insert_worker(self) -> None:
        main = self.insert_main_input
        inserted = self.insert_secondary_input
        if not main or not main.exists():
            raise RuntimeError("Selecione o áudio principal")
        if not inserted or not inserted.exists():
            raise RuntimeError("Selecione o áudio que será inserido")
        main_profile = self._insert_probe_profile(main)
        inserted_profile = self._insert_probe_profile(inserted)
        if not main_profile.has_audio or not inserted_profile.has_audio:
            raise RuntimeError("Os dois arquivos precisam conter áudio")
        if not math.isfinite(self.insert_timeline.insertion):
            raise RuntimeError("Ponto de inserção inválido")
        insertion = max(0.0, min(self.insert_timeline.insertion, main_profile.duration))
        transition_label = str(self._worker_value("insert_transition", self.insert_transition_var))
        transition_code = self.insert_transition_code(transition_label)
        if transition_code == "none":
            transition_seconds = 0.0
        else:
            try:
                transition_seconds = float(str(self._worker_value("insert_seconds", self.insert_seconds_var)).replace(",", "."))
            except ValueError as exc:
                raise RuntimeError("Tempo de transição inválido") from exc
        if transition_seconds < 0:
            raise RuntimeError("Tempo de transição não pode ser negativo")

        if not math.isfinite(transition_seconds):
            raise RuntimeError("Tempo de transição inválido")
        full_reencode = bool(self._worker_value("insert_reencode", self.insert_reencode_var))
        use_smart = bool(self._worker_value("insert_smart", self.insert_smart_var))
        extension = main.suffix.lower() if main.suffix.lower() in AUDIO_EXTENSIONS else ".m4a"
        output = self._recoverable_output(self.output_dir, f"{main.stem}_com_audio", extension)
        total_duration = main_profile.duration + inserted_profile.duration
        if full_reencode and transition_code not in {"none", "fade"} and transition_seconds > 0:
            effective = self._insert_effective_transition(
                main_profile.duration, inserted_profile.duration, insertion, transition_seconds
            )
            boundaries = int(insertion > 0) + int(main_profile.duration - insertion > 0)
            total_duration = max(0.01, total_duration - effective * boundaries)
        mode = "Reencode Completo" if full_reencode else ("Smart Insert" if use_smart else "Sem reencodar")
        self._set_status(f"Inserindo áudio ({mode})", 0)
        self._append_log(
            f"Inserção: ponto {self._clock(insertion)}, áudio principal {main_profile.audio_rate} Hz/"
            f"{main_profile.audio_channels} canal(is), inserido {inserted_profile.audio_rate} Hz/"
            f"{inserted_profile.audio_channels} canal(is)."
        )
        if full_reencode:
            self._insert_render_continuous(main, inserted, output, main_profile, insertion, transition_seconds, transition_code, False)
            return
        if use_smart:
            self._insert_smart_worker(
                main, inserted, output, main_profile, insertion, total_duration,
                transition_code if transition_seconds > 0 else "none", transition_seconds,
            )
            return
        self._append_log("Inserção sem reencode usa cortes aproximados ao frame/pacote do codec; use Reencode Completo para precisão de amostra.")
        self._insert_copy_worker(main, inserted, output, main_profile, inserted_profile, insertion, total_duration)

    def _insert_copy_worker(self, main: Path, inserted: Path, output: Path, main_profile: MediaProfile, inserted_profile: MediaProfile, insertion: float, total_duration: float) -> None:
        if main.suffix.lower() != inserted.suffix.lower():
            raise RuntimeError(
                f"Os formatos dos arquivos são diferentes ({main.suffix} vs {inserted.suffix}). "
                "Para juntar formatos distintos, marque 'Smart Insert' ou 'Reencode Completo'."
            )
        if (
            main_profile.audio_rate != inserted_profile.audio_rate
            or main_profile.audio_channels != inserted_profile.audio_channels
            or main_profile.audio_codec != inserted_profile.audio_codec
            or main_profile.audio_layout != inserted_profile.audio_layout
        ):
            raise RuntimeError(
                f"Os áudios possuem taxas de amostragem, canais, layouts ou codecs distintos "
                f"({main_profile.audio_rate}Hz/{main_profile.audio_channels}ch/{main_profile.audio_layout}/{main_profile.audio_codec} "
                f"vs {inserted_profile.audio_rate}Hz/{inserted_profile.audio_channels}ch/{inserted_profile.audio_layout}/{inserted_profile.audio_codec}). "
                "Para inseri-los sem distorção, marque 'Smart Insert' ou 'Reencode Completo'."
            )
        work_dir = self._work_directory("insert_copy", self.output_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        extension = output.suffix or ".m4a"
        pieces: list[Path] = []
        try:
            if insertion > 0.001:
                left = work_dir / f"000{extension}"
                self._execute(
                    [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", "0", "-i", str(main), "-t", self._fmt_seconds(insertion), "-map", "0:a:0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(left)],
                    "Preparando trecho inicial",
                    1,
                    4,
                    insertion,
                )
                pieces.append(left)
            middle = work_dir / f"{len(pieces):03d}{extension}"
            self._execute(
                [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", "0", "-i", str(inserted), "-map", "0:a:0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(middle)],
                "Preparando áudio inserido",
                2 if insertion > 0.001 else 1,
                4,
                self._get_duration_only(inserted),
            )
            pieces.append(middle)
            main_duration = self._get_duration_only(main)
            if insertion < main_duration - 0.001:
                right = work_dir / f"{len(pieces):03d}{extension}"
                self._execute(
                    [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", self._fmt_seconds(insertion), "-i", str(main), "-map", "0:a:0", "-c", "copy", str(right)],
                    "Preparando trecho final",
                    3,
                    4,
                    max(0.1, main_duration - insertion),
                )
                pieces.append(right)
            self._concat_insert_pieces(pieces, output, "Juntando áudio inserido", 4, 4, total_duration)
        finally:
            self._remove_work_directory(work_dir)

    def _insert_probe_profile(self, path: Path) -> MediaProfile:
        key = (str(path.resolve()), path.stat().st_mtime_ns, path.stat().st_size)
        cache = getattr(self, "_insert_profiles", {})
        if key in cache:
            return cache[key]
        profile = self._probe_media(path)
        if profile.has_audio and self._get_ffprobe():
            info = self._smart_join_probe(path)
            audio = next(s for s in info["streams"] if s.get("codec_type") == "audio")
            if audio.get("codec_name") == "opus":
                info = self._smart_join_probe(path, packets=True, first_packets=True, packet_stream="a:0")
            duration = smart_insert_planner.audio_duration(info, profile.duration)
            profile = replace(profile, duration=duration, audio_sample_fmt=audio.get("sample_fmt", ""),
                              audio_bits_per_raw_sample=int(audio.get("bits_per_raw_sample") or 0))
        cache[key] = profile
        self._insert_profiles = cache
        return profile

    def _insert_duration(self, path: Path) -> float:
        return self._insert_probe_profile(path).duration if path.exists() else self._get_duration_only(path)

    def _insert_codec_args(self, profile: MediaProfile, extension: str) -> list[str]:
        args = self._audio_codec_args_for_source_codec(profile.audio_codec, extension, profile.audio_bitrate)
        args = args or self._audio_codec_args(extension, profile.audio_bitrate)
        if profile.audio_codec == "alac" and profile.audio_sample_fmt in {"s16p", "s32p"}:
            args += ["-sample_fmt", profile.audio_sample_fmt]
        if profile.audio_codec == "flac" and profile.audio_sample_fmt in {"s16", "s32"}:
            args += ["-sample_fmt", profile.audio_sample_fmt]
            if profile.audio_bits_per_raw_sample:
                args += ["-bits_per_raw_sample", str(profile.audio_bits_per_raw_sample)]
        return args

    def _insert_validate(self, path: Path, profile: MediaProfile, samples: int) -> None:
        # Estes containers declaram a contagem exata de amostras. Ler o header
        # evita iniciar FFprobe repetidamente para peças já verificadas na montagem.
        if profile.audio_codec == "flac" and path.suffix.lower() == ".flac":
            stream = smart_insert_flac.metadata(path)[0][1]
            packed = int.from_bytes(stream[10:18], "big")
            rate, channels, bits, actual = packed >> 44, ((packed >> 41) & 7) + 1, ((packed >> 36) & 31) + 1, packed & ((1 << 36) - 1)
            if (rate != profile.audio_rate or channels != profile.audio_channels or actual != samples or
                (profile.audio_bits_per_raw_sample and bits != profile.audio_bits_per_raw_sample)):
                raise RuntimeError("Inserir áudio: formato ou contagem de amostras FLAC incorretos.")
            return
        if (profile.audio_codec in {"pcm_u8", "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_f64le"}
            and path.suffix.lower() == ".wav"):
            data = smart_insert_wave.inspect(path)
            if (data.signature[1:3] != (profile.audio_channels, profile.audio_rate) or data.size // data.align != samples):
                raise RuntimeError("Inserir áudio: formato ou contagem de amostras WAV incorretos.")
            return
        if not self._get_ffprobe():
            return
        info = self._smart_join_probe(path)
        self._smartcut_validate_audio(info, samples / profile.audio_rate, 1)
        audio = next(s for s in info["streams"] if s.get("codec_type") == "audio")
        if int(audio.get("sample_rate") or 0) != profile.audio_rate or int(audio.get("channels") or 0) != profile.audio_channels:
            raise RuntimeError("Inserir áudio: a taxa de amostragem ou a quantidade de canais mudou.")
        if audio.get("codec_name", "").startswith("pcm_") or audio.get("codec_name") in {"alac", "flac"}:
            actual = round(smart_insert_planner.audio_duration(info, 0) * profile.audio_rate)
            if abs(actual - samples) > 1:
                raise RuntimeError(f"Inserir áudio: contagem incorreta de amostras ({actual}/{samples}).")

    def _insert_audio_filter(self, profile: MediaProfile, inserted_duration: float, insertion: float,
                             seconds: float, code: str, smart: bool = False) -> tuple[str, int]:
        rate = profile.audio_rate
        main = round(profile.duration * rate)
        inserted = round(inserted_duration * rate)
        cut = max(0, min(round(insertion * rate), main))
        effective = min(seconds, inserted_duration / 2) if smart else self._insert_effective_transition(
            main / rate, inserted / rate, cut / rate, seconds)
        fade = max(0, round(effective * rate)) if code != "none" else 0
        normalize = (f"asetpts=PTS-STARTPTS,aresample={rate},"
                     f"aformat=sample_fmts=dblp:sample_rates={rate}:channel_layouts={profile.audio_layout},apad")
        def window(source, start, end):
            return f"[{source}]{normalize},atrim=start_sample={start}:end_sample={end},asetpts=PTS-STARTPTS"
        def fade_filter(direction, start=0, curve="fade"):
            curve_arg = "" if curve == "fade" else f":curve={curve}"
            return f",afade=t={direction}:st={self._precise_seconds(start / rate)}:d={self._precise_seconds(fade / rate)}{curve_arg}"
        use_fade = fade > 0 and (smart or code == "fade")
        crossfade = fade > 0 and not smart and code not in {"none", "fade"}
        parts, labels = [], []
        if cut:
            tail_fade = fade_filter("out", cut - fade) if use_fade and not smart else ""
            parts.append(window("0:a:0", 0, cut) + tail_fade + "[a0]")
            labels.append("a0")
        fades = ""
        if use_fade:
            if smart or cut:
                fades += fade_filter("in", curve=code)
            if smart or cut < main:
                fades += fade_filter("out", inserted - fade, code)
        parts.append(window("1:a:0", 0, inserted) + fades + "[a1]")
        labels.append("a1")
        if cut < main:
            head_fade = fade_filter("in") if use_fade and not smart else ""
            parts.append(window("0:a:0", cut, main) + head_fade + "[a2]")
            labels.append("a2")
        if crossfade:
            previous = labels[0]
            for i, label in enumerate(labels[1:], 1):
                parts.append(f"[{previous}][{label}]acrossfade=d={self._precise_seconds(fade / rate)}:c1={code}:c2={code}[ax{i}]")
                previous = f"ax{i}"
            parts.append(f"[{previous}]anull[aout]")
        else:
            parts.append("".join(f"[{label}]" for label in labels) + f"concat=n={len(labels)}:v=0:a=1[aout]")
        return ";".join(parts), main + inserted - (fade * (len(labels) - 1) if crossfade else 0)

    def _insert_render_continuous(self, main: Path, inserted: Path, output: Path, profile: MediaProfile,
                                   insertion: float, seconds: float, code: str, smart: bool) -> None:
        work = self._work_directory("insert_encode", output.parent)
        work.mkdir(parents=True, exist_ok=True)
        staged = work / output.name
        try:
            command = self._insert_full_reencode_arguments(main, inserted, staged, profile, insertion, seconds, code,
                                                          smart_semantics=smart)
            _, samples = self._insert_audio_filter(profile, self._insert_duration(inserted), insertion, seconds, code, smart)
            self._execute(command, "Inserindo áudio (compatibilização contínua)" if smart else "Inserindo áudio (Reencode Completo)",
                          1, 1, samples / profile.audio_rate)
            self._validate_completed_output(staged, lambda: self._insert_validate(staged, profile, samples))
            if self.cancel_event.is_set():
                raise Cancelled()
            self._publish_completed_output(staged, output)
        finally:
            self._remove_work_directory(work)

    @staticmethod
    def _insert_partial_supported(profile: MediaProfile, main: Path, output: Path) -> bool:
        return ((profile.audio_codec == "alac" and output.suffix.lower() == ".m4a") or
                (profile.audio_codec in {"pcm_u8", "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_f64le"}
                 and output.suffix.lower() == ".wav") or
                (profile.audio_codec == "flac" and output.suffix.lower() == ".flac" and main.suffix.lower() == ".flac"))

    def _insert_smart_worker(self, main: Path, inserted: Path, output: Path, profile: MediaProfile,
                             insertion: float, total_duration: float, transition_code: str = "none",
                             transition_seconds: float = 0.5) -> None:
        supported = self._insert_partial_supported(profile, main, output)
        if not supported or not self._get_ffprobe():
            reasons = {"aac": "priming e padding em emendas AAC", "mp3": "reservatório e atraso do encoder MP3",
                       "opus": "pre-skip e padding em emendas Opus", "vorbis": "parâmetros e granule positions Vorbis",
                       "flac": "cabeçalho e posições dos frames FLAC", "wmav2": "atraso e dependências dos frames WMA"}
            reason = reasons.get(profile.audio_codec, "codec sem cópia parcial validada") if self._get_ffprobe() else "FFprobe indisponível"
            self._append_log(f"Smart Insert: {reason}; usando uma recodificação contínua, mantendo o efeito selecionado.")
            self._insert_render_continuous(main, inserted, output, profile, insertion, transition_seconds, transition_code, True)
            return
        if profile.audio_codec.startswith("pcm_"):
            self._insert_pcm_worker(main, inserted, output, profile, insertion, transition_seconds, transition_code)
            return
        info = self._smart_join_probe(main, packets=True, packet_stream="a:0")
        try:
            plan = smart_insert_planner.plan(info, profile.duration, self._insert_duration(inserted), insertion, profile.audio_rate,
                                             16 if profile.audio_codec == "flac" else 0)
        except ValueError as exc:
            self._append_log(f"Smart Insert: {exc}; usando recodificação contínua.")
            self._insert_render_continuous(main, inserted, output, profile, insertion, transition_seconds, transition_code, True)
            return
        rate = plan.rate
        self._append_log(f"Smart Insert: {(plan.tail_start - plan.right + plan.left - plan.head_end) / rate:.6f}s do principal em cópia; "
                         f"somente o inserido e {(plan.right - plan.left) / rate:.6f}s da emenda serão recodificados.")
        work = self._work_directory("smart_insert", output.parent)
        work.mkdir(parents=True, exist_ok=True)
        staged = work / output.name
        pieces, durations = [], []
        def copy_piece(start, samples, packets, label):
            path = work / f"{len(pieces):03d}{output.suffix}"
            command = [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", self._precise_seconds(start / rate + plan.seek_offset),
                       "-i", str(main), "-ss", "0", "-map", "0:a:0", "-c:a", "copy", "-frames:a", str(packets),
                       "-bsf:a", "setts=pts=PTS-STARTPTS:dts=DTS-STARTPTS", "-avoid_negative_ts", "disabled", str(path)]
            self._execute(command, label, len(pieces) + 1, 4, samples / rate)
            self._insert_validate(path, profile, samples)
            pieces.append(path)
            durations.append(samples / rate)
        def encode_edge(start, samples):
            path = work / f"{len(pieces):03d}{output.suffix}"
            command = [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", self._precise_seconds(start / rate + plan.seek_offset),
                       "-i", str(main), "-map", "0:a:0", "-vn", "-af", f"apad,atrim=end_sample={samples},asetpts=N/SR/TB",
                       "-ar", str(rate), "-ac", str(profile.audio_channels), *self._insert_codec_args(profile, output.suffix), str(path)]
            self._execute(command, "Smart Insert: preservando borda da edit-list", len(pieces)+1, 6, samples / rate)
            self._insert_validate(path, profile, samples)
            pieces.append(path); durations.append(samples / rate)
        try:
            if plan.head_end:
                encode_edge(0, plan.head_end)
            if plan.prefix_packets and profile.audio_codec != "flac":
                copy_piece(plan.head_end, plan.left-plan.head_end, plan.prefix_packets, "Smart Insert: trecho inicial")
            middle = work / f"{len(pieces):03d}{output.suffix}"
            bridge_profile = replace(profile, duration=(plan.right - plan.left) / rate)
            filters, samples = self._insert_audio_filter(bridge_profile, plan.inserted_samples / rate,
                                                        (plan.insertion - plan.left) / rate,
                                                        transition_seconds, transition_code, True)
            middle_cmd = [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", self._precise_seconds(plan.left / rate + plan.seek_offset),
                          "-i", str(main), "-i", str(inserted), "-filter_complex", filters, "-map", "[aout]", "-vn",
                          "-ar", str(rate), "-ac", str(profile.audio_channels), *self._insert_codec_args(profile, output.suffix),
                          "-map_metadata", "0", "-map_chapters", "-1", str(middle)]
            self._execute(middle_cmd, "Smart Insert: compatibilizando áudio inserido", len(pieces) + 1, 4, samples / rate)
            self._insert_validate(middle, profile, samples)
            pieces.append(middle)
            durations.append(samples / rate)
            if plan.suffix_packets and profile.audio_codec != "flac":
                copy_piece(plan.right, plan.tail_start-plan.right, plan.suffix_packets, "Smart Insert: trecho final")
            if plan.tail_start < plan.main_samples:
                encode_edge(plan.tail_start, plan.main_samples-plan.tail_start)
            if profile.audio_codec == "flac":
                parts = []
                if plan.prefix_packets:
                    parts.append((main, info["packets"][:plan.prefix_packets]))
                parts.append((middle, self._smart_join_probe(middle, packets=True, packet_stream="a:0")["packets"]))
                if plan.suffix_packets:
                    parts.append((main, info["packets"][-plan.suffix_packets:]))
                def check_cancelled():
                    if self.cancel_event.is_set():
                        raise Cancelled()
                smart_insert_flac.assemble(parts, staged, main, plan.total_samples, check_cancelled)
            else:
                self._concat_insert_pieces(pieces, staged, "Smart Insert: juntando áudio", 4, 4, plan.total_samples / rate,
                                           durations=durations, metadata_source=main)
            self._validate_completed_output(staged, lambda: self._insert_validate(staged, profile, plan.total_samples))
            if self.cancel_event.is_set():
                raise Cancelled()
            self._publish_completed_output(staged, output)
        finally:
            self._remove_work_directory(work)

    def _insert_pcm_worker(self, main: Path, inserted: Path, output: Path, profile: MediaProfile,
                           insertion: float, seconds: float, code: str) -> None:
        rate = profile.audio_rate
        cut = max(0, min(round(insertion * rate), round(profile.duration * rate)))
        middle_samples = round(self._insert_duration(inserted) * rate)
        total = round(profile.duration * rate) + middle_samples
        work = self._work_directory("smart_insert", output.parent)
        work.mkdir(parents=True, exist_ok=True)
        staged, middle = work / output.name, work / "inserted.wav"
        try:
            smart_insert_wave.inspect(main)
            filters, _ = self._insert_audio_filter(replace(profile, duration=0), middle_samples / rate, 0, seconds, code, True)
            command = [str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(inserted),
                       "-filter_complex", filters.replace("[1:a:0]", "[0:a:0]"), "-map", "[aout]", "-vn",
                       "-ar", str(rate), "-ac", str(profile.audio_channels), *self._insert_codec_args(profile, ".wav"),
                       str(middle)]
            self._execute(command, "Smart Insert: compatibilizando áudio inserido", 1, 2, middle_samples / rate)
            self._append_log("Smart Insert: principal WAV/PCM em cópia por amostras; somente o áudio inserido foi recodificado.")
            def check_cancelled():
                if self.cancel_event.is_set():
                    raise Cancelled()
            smart_insert_wave.assemble(main, middle, staged, cut, total, check_cancelled)
            self._validate_completed_output(staged, lambda: self._insert_validate(staged, profile, total))
            check_cancelled()
            self._publish_completed_output(staged, output)
        except ValueError as exc:
            self._append_log(f"Smart Insert: {exc}; usando compatibilização contínua para este WAV.")
            self._insert_render_continuous(main, inserted, output, profile, insertion, seconds, code, True)
        finally:
            self._remove_work_directory(work)

    def _concat_insert_pieces(self, pieces: list[Path], output: Path, label: str, progress: int, total: int, duration: float,
                              durations: list[float] | None = None, metadata_source: Path | None = None) -> None:
        if not pieces:
            raise RuntimeError("Nenhum trecho foi criado para a inserção")
        list_file = self._work_file(output.parent, output.stem + "_pieces", ".txt")
        list_file.write_text(
            "\n".join(f"file '{self._concat_escape(str(piece.resolve()))}'" +
                      (f"\nduration {self._precise_seconds(durations[i])}" if durations else "")
                      for i, piece in enumerate(pieces)),
            encoding="utf-8",
        )
        try:
            concat_cmd = [str(self._ffmpeg()), "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file)]
            if metadata_source is not None:
                concat_cmd += ["-i", str(metadata_source), "-map", "0:a:0", "-map_metadata", "1", "-map_chapters", "-1"]
            concat_cmd += ["-c", "copy"]
            if output.suffix.lower() == ".m4a":
                concat_cmd += ["-movflags", "+faststart"]
            concat_cmd += ["-avoid_negative_ts", "disabled" if durations else "make_zero", str(output)]
            self._execute(
                concat_cmd,
                label,
                progress,
                total,
                duration,
            )
        finally:
            list_file.unlink(missing_ok=True)

    def _insert_full_reencode_arguments(
        self, main: Path, inserted: Path, output: Path, profile: MediaProfile,
        insertion: float, transition_seconds: float, transition_code: str,
        log_adjustment: bool = True, smart_semantics: bool = False,
    ) -> list[str]:
        inserted_duration = self._insert_duration(inserted)
        effective = min(transition_seconds, inserted_duration / 2) if smart_semantics else self._insert_effective_transition(
            profile.duration, inserted_duration, insertion, transition_seconds)
        if log_adjustment and effective + 1 / profile.audio_rate < transition_seconds:
            self._append_log(f"Tempo de transição ajustado de {transition_seconds:.3f}s para {effective:.3f}s para caber nos trechos.")
        filters, _ = self._insert_audio_filter(profile, inserted_duration, insertion, transition_seconds, transition_code, smart_semantics)
        return [str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(main), "-i", str(inserted),
                "-filter_complex", filters, "-map", "[aout]", "-vn", "-sn", "-dn",
                "-ar", str(profile.audio_rate), "-ac", str(profile.audio_channels),
                *self._insert_codec_args(profile, output.suffix), "-map_metadata", "0", "-map_chapters", "-1", str(output)]

    def _clean_worker(self) -> None:
        source = self.clean_input
        if not source or not source.exists():
            raise RuntimeError("Selecione o áudio para limpar")
        media = self._probe_media(source)
        if not media.has_audio:
            raise RuntimeError("O arquivo selecionado não possui trilha de áudio.")
        clean_mode = str(self._worker_value("clean_mode", self.clean_mode_var))
        filter_value = "afftdn=nf=-25" if clean_mode == "equilibrado" else "afftdn=nr=18:nf=-35:tn=1"
        output = self._recoverable_output(self.output_dir, f"{source.stem}_limpo", ".wav")
        # F9: a saída preserva a taxa e os canais da FONTE (o perfil que forçava
        # 16 kHz mono saiu; reduzir canais/taxa é outra decisão, não "limpar").
        format_args = ["-ar", str(media.audio_rate), "-ac", str(media.audio_channels)]
        command = [str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(source), "-vn", "-map", "0:a:0", "-af", filter_value, "-c:a", "pcm_s16le", *format_args, "-f", "wav", str(output)]
        self._execute(command, "Limpando áudio", 1, 1, media.duration)
