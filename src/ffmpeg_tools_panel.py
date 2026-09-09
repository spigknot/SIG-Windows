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
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
import webbrowser
from PIL import Image, ImageTk
from app_env import app_base_dir
from dataclasses import dataclass
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


VIDEO_QUALITY_LEVELS = ("Máxima", "Muito alta", "Alta", "Média", "Econômica")
VIDEO_QUALITY_MENU_LABELS = {
    "Máxima": "Máxima",
    "Muito alta": "Muito alta",
    "Alta": "Alta (Recomendado)",
    "Média": "Média",
    "Econômica": "Econômica",
}


@dataclass(frozen=True)
class VideoAcceleration:
    key: str
    label: str
    encoder: str


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

    # Mantém compatibilidade com as rotinas existentes que tratam o perfil como tupla.
    def __iter__(self):
        yield from (self.duration, self.has_audio, self.width, self.height, self.fps)

    def __getitem__(self, index: int):
        return (self.duration, self.has_audio, self.width, self.height, self.fps)[index]


class RangeTimeline(Canvas):
    """Linha do tempo simples com playhead e marcadores de início/fim arrastáveis."""

    def __init__(self, parent, on_change, **kwargs):
        super().__init__(parent, height=52, highlightthickness=0, background="#ffffff", **kwargs)
        self.duration = 0.0
        self.start = 0.0
        self.end = 0.0
        self.position = 0.0
        self.on_change = on_change
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
        self.draw()

    def set_range(self, start: float, end: float) -> None:
        if self.duration <= 0:
            return
        self.start = max(0.0, min(start, self.duration))
        self.end = max(self.start, min(end, self.duration))
        self.draw()

    def set_position(self, position: float) -> None:
        self.position = max(0.0, min(position, self.duration))
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
            self.create_text(self.winfo_width() / 2, center, text="Selecione uma mídia para carregar a linha do tempo", fill="#667371", font=("Segoe UI", 9))
            return
        start_x, end_x, position_x = self._x_for(self.start), self._x_for(self.end), self._x_for(self.position)
        self.create_line(start_x, center, end_x, center, fill="#4b9d79", width=6, capstyle="round")
        self.create_polygon(start_x, 8, start_x - 7, 19, start_x + 7, 19, fill="#2e7d5a", outline="")
        self.create_polygon(end_x, 46, end_x - 7, 35, end_x + 7, 35, fill="#c64a42", outline="")
        self.create_line(position_x, 7, position_x, 47, fill="#243230", width=2)
        self.create_text(left, 48, text="0:00", anchor="w", fill="#667371", font=("Consolas", 8))
        self.create_text(right, 48, text=self._format_time(self.duration), anchor="e", fill="#667371", font=("Consolas", 8))

    def _press(self, event) -> None:
        if self.duration <= 0:
            return
        # Os triângulos são os únicos pontos que movem o recorte. Um clique
        # normal na faixa sempre reposiciona a cabeça de reprodução.
        marker_radius = 9
        if event.y <= 23 and abs(self._x_for(self.start) - event.x) <= marker_radius:
            self.drag_target = "start"
        elif event.y >= 31 and abs(self._x_for(self.end) - event.x) <= marker_radius:
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
            self.position = value
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
        self._draw_wave(left, first_end if self.inserted_duration else right, top + 4, bottom - 4, "#5edaf2", self._seed(self.main_name))
        if self.inserted_duration > 0:
            self._draw_wave(first_end, inserted_end, top + 4, bottom - 4, "#ffc24a", self._seed(self.inserted_name))
            self._draw_wave(inserted_end, right, top + 4, bottom - 4, "#5edaf2", self._seed(self.main_name) + 7919)
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

    def _draw_wave(self, left: float, right: float, top: float, bottom: float, color: str, seed: int) -> None:
        if right - left < 2:
            return
        center = (top + bottom) / 2
        count = max(2, int((right - left) / 5))
        gap = (right - left) / count
        value = seed or 1
        for index in range(count):
            value = (value * 1103515245 + 12345) & 0x7FFFFFFF
            amplitude = (bottom - top) * (0.10 + (value % 1000) / 1000 * 0.38)
            x = left + gap * (index + 0.5)
            self.create_line(x, center - amplitude, x, center + amplitude, fill=color, width=2)

    @staticmethod
    def _seed(value: str) -> int:
        return sum((index + 1) * ord(char) for index, char in enumerate(value)) or 1

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
        self.acceleration_var = StringVar(value="Detectando opções...")
        self.encoder_help: dict[str, str] = {}
        self.video_quality_var = StringVar(value="Alta")
        self.output_dir = app_base_dir() / "temp" / "ffmpeg"
        self.output_dir_var = StringVar(value=str(self.output_dir))
        self.status_var = StringVar(value="Escolha uma ferramenta e os arquivos de entrada.")
        self.progress_var = IntVar(value=0)
        self.max_progress_seen = 0
        self.active_tool_var = StringVar(value="Cortar")

        self.cut_input: Path | None = None
        self.cut_media_profile: MediaProfile | None = None
        self.cut_input_var = StringVar(value="Nenhum arquivo selecionado")
        self.cut_start_var = StringVar(value="0")
        self.cut_end_var = StringVar(value="")
        self.cut_current_var = StringVar(value="0:00")
        self.cut_mode_var = StringVar(value="Preciso (reencodar)")
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
        self.join_profile_var = StringVar(value="Primeiro clipe")
        self.join_stream_policy_var = StringVar(value="Primeira faixa (MP4)")
        self.join_audio_policy_var = StringVar(value="Preservar áudio e preencher silêncio")
        self.join_orientation_mode_var = StringVar(value="bake")  # bake | preserve
        self.join_orientation_reference_var = StringVar(value="")
        self._join_rotation_answer: dict | None = None
        self.join_seconds_var.trace_add("write", lambda *_: self._on_join_seconds_changed())

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
        self.clean_output_profile_var = StringVar(value="Transcrição (mono, 16 kHz)")
        self.preview_player = EmbeddedMediaPlayer()
        self.preview_context: dict | None = None
        self.preview_playing = False
        self.preview_speed = 1.0
        self.preview_speed_var = StringVar(value="1.0x")
        self.preview_after_id = None
        self.preview_image_refs: dict[Canvas, object] = {}
        self.external_preview_process: subprocess.Popen | None = None
        self.external_preview_started_at = 0.0
        self.external_preview_offset = 0.0
        self.frame_preview_process: subprocess.Popen | None = None
        self.frame_preview_thread: threading.Thread | None = None
        self.frame_preview_stop_event = threading.Event()
        self.preview_frame_queue: queue.Queue = queue.Queue(maxsize=3)
        self.preview_generation = 0

        self._build(parent)
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
        self.ffmpeg_scroll_canvas = Canvas(outer, highlightthickness=0, background="#f4f7f6")
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=self.ffmpeg_scroll_canvas.yview)
        self.ffmpeg_scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.ffmpeg_scroll_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        frame = ttk.Frame(self.ffmpeg_scroll_canvas)
        self.ffmpeg_scroll_window = self.ffmpeg_scroll_canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", self._update_ffmpeg_scroll_region)
        self.ffmpeg_scroll_canvas.bind("<Configure>", self._resize_ffmpeg_scroll_content)
        self.ffmpeg_scroll_canvas.bind("<Enter>", lambda _event: self.ffmpeg_scroll_canvas.bind_all("<MouseWheel>", self._scroll_ffmpeg_panel))
        self.ffmpeg_scroll_canvas.bind("<Leave>", lambda _event: self.ffmpeg_scroll_canvas.unbind_all("<MouseWheel>"))

        tool_tab_bar = self.tk.Frame(frame, background="#f4f7f6")
        tool_tab_bar.pack(fill=X, pady=(0, 8))

        # Pack right-to-left so the encoder label is visually before its selector.
        self.acceleration_combo = ttk.Combobox(
            tool_tab_bar,
            textvariable=self.acceleration_var,
            state="disabled",
            width=20,
        )
        self.acceleration_combo.pack(side=RIGHT, padx=(0, 4), pady=(2, 0))
        self.acceleration_label = ttk.Label(tool_tab_bar, text="Encoder de vídeo:", style="Muted.TLabel")
        self.acceleration_label.pack(side=RIGHT, padx=(12, 4), pady=(4, 0))
        self.quality_help_button = ttk.Button(tool_tab_bar, text="?", width=3, command=self._show_video_quality_help)
        self.quality_help_button.pack(side=RIGHT, padx=(4, 0), pady=(2, 0))
        self.quality_menu_button = ttk.Menubutton(tool_tab_bar, textvariable=self.video_quality_var, width=11)
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
                tool_tab_bar,
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

        output_row = ttk.Frame(frame)
        output_row.pack(fill=X, pady=(10, 0))
        ttk.Label(output_row, text="Pasta de saída:", style="Muted.TLabel").pack(side=LEFT)
        ttk.Label(output_row, textvariable=self.output_dir_var, style="Muted.TLabel").pack(side=LEFT, fill=X, expand=True, padx=(6, 8))
        ttk.Button(output_row, text="Escolher pasta", command=self.choose_output_dir).pack(side=RIGHT)
        ttk.Button(output_row, text="Abrir pasta", command=self.open_output_dir).pack(side=RIGHT, padx=(0, 8))

        bottom = ttk.Frame(frame)
        bottom.pack(fill=X, pady=(10, 0))
        self.progress = ttk.Progressbar(bottom, maximum=100, variable=self.progress_var)
        self.progress.pack(fill=X)
        ttk.Label(bottom, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(5, 0))

        actions = ttk.Frame(frame)
        actions.pack(fill=X, pady=(8, 0))
        self.run_button = ttk.Button(actions, text="Executar", style="Execute.TButton", command=self.run_current_tool)
        self.run_button.pack(side=LEFT)
        self.cancel_button = ttk.Button(actions, text="Cancelar", command=self.cancel, state="disabled")
        self.cancel_button.pack(side=LEFT, padx=(8, 0))


    def _update_ffmpeg_scroll_region(self, _event=None) -> None:
        self.ffmpeg_scroll_canvas.configure(scrollregion=self.ffmpeg_scroll_canvas.bbox("all"))

    def _resize_ffmpeg_scroll_content(self, event) -> None:
        self.ffmpeg_scroll_canvas.itemconfigure(self.ffmpeg_scroll_window, width=event.width)

    def _scroll_ffmpeg_panel(self, event) -> None:
        self.ffmpeg_scroll_canvas.yview_scroll(-max(1, event.delta // 120), "units")

    def _section_title(self, parent, title: str, detail: str) -> None:
        ttk.Label(parent, text=title, font=("Segoe UI Semibold", 14)).pack(anchor="w")
        ttk.Label(parent, text=detail, style="Muted.TLabel", wraplength=850).pack(anchor="w", pady=(3, 14))

    def _file_row(self, parent, variable: StringVar, command, label: str = "Selecionar arquivo") -> None:
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=(0, 12))
        ttk.Button(row, text=label, command=command).pack(side=LEFT)
        ttk.Label(row, textvariable=variable, style="Muted.TLabel", wraplength=720).pack(side=LEFT, padx=(10, 0), fill=X, expand=True)

    def _create_stable_preview(self, parent, message: str, size: int = 312) -> Canvas:
        """Área quadrada fixa: a orientação da mídia não altera o layout."""
        holder = ttk.Frame(parent, width=size, height=size)
        holder.pack(anchor="center", pady=(0, 6))
        holder.pack_propagate(False)
        canvas = Canvas(holder, highlightthickness=0, background="#f4f7f6")
        canvas.pack(fill=BOTH, expand=True)
        canvas.create_text(size // 2, size // 2, text=message, fill="#667371", font=("Segoe UI", 10))
        return canvas

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
        values = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0)
        index = min(range(len(values)), key=lambda item: abs(values[item] - self.preview_speed))
        self.preview_speed = values[max(0, min(len(values) - 1, index + direction))]
        self.preview_speed_var.set(f"{self.preview_speed:.2g}x")
        if self.preview_playing:
            self._toggle_preview()
            self._toggle_preview()

    def _build_cut_tab(self) -> None:
        self._section_title(self.cut_tab, "Cortar áudio/vídeo", "Escolha entre corte preciso com reencode e corte rápido sem reencode, alinhado a keyframes/pacotes do codec.")
        self._file_row(self.cut_tab, self.cut_input_var, self.select_cut_input)
        self.cut_preview = self._create_stable_preview(self.cut_tab, "Selecione uma mídia para visualizar")
        self.cut_preview.bind("<Configure>", lambda _event: self.preview_player.resize(self.cut_preview))
        self.cut_play_button = self._add_preview_speed_controls(self.cut_tab)
        self.cut_timeline = RangeTimeline(self.cut_tab, self._cut_timeline_changed)
        self.cut_timeline.pack(fill=X, pady=(0, 4))
        self._add_preview_time_label(self.cut_tab, self.cut_current_var)
        values = ttk.Frame(self.cut_tab)
        values.pack(anchor="w")
        ttk.Label(values, text="Início (segundos):").grid(row=0, column=0, sticky="w")
        cut_start_entry = ttk.Entry(values, textvariable=self.cut_start_var, width=12)
        cut_start_entry.grid(row=0, column=1, padx=(8, 20))
        ttk.Label(values, text="Fim (segundos):").grid(row=0, column=2, sticky="w")
        cut_end_entry = ttk.Entry(values, textvariable=self.cut_end_var, width=12)
        cut_end_entry.grid(row=0, column=3, padx=(8, 0))
        cut_start_entry.bind("<FocusOut>", lambda _event: self._sync_cut_range_from_entries())
        cut_end_entry.bind("<FocusOut>", lambda _event: self._sync_cut_range_from_entries())
        mode = ttk.Frame(self.cut_tab)
        mode.pack(anchor="w", pady=(10, 0))
        ttk.Label(mode, text="Modo:").pack(side=LEFT)
        self.cut_mode_combo = ttk.Combobox(
            mode,
            textvariable=self.cut_mode_var,
            values=("Preciso (reencodar)", "Rápido (sem reencodar)"),
            state="readonly",
            width=25,
        )
        self.cut_mode_combo.pack(side=LEFT, padx=(6, 0))
        self.cut_mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_cut_controls())
        ttk.Label(mode, text="Áudio do vídeo:").pack(side=LEFT, padx=(18, 0))
        self.cut_audio_policy_combo = ttk.Combobox(
            mode,
            textvariable=self.cut_audio_policy_var,
            values=("Precisão máxima (AAC)", "Copiar áudio (limites por pacote)"),
            state="readonly",
            width=29,
        )
        self.cut_audio_policy_combo.pack(side=LEFT, padx=(6, 0))
        streams = ttk.Frame(self.cut_tab)
        streams.pack(anchor="w", pady=(6, 0))
        ttk.Label(streams, text="Streams:").pack(side=LEFT)
        self.cut_stream_policy_combo = ttk.Combobox(
            streams,
            textvariable=self.cut_stream_policy_var,
            values=("Vídeo e áudio", "Todos os streams (somente modo rápido)"),
            state="readonly",
            width=39,
        )
        self.cut_stream_policy_combo.pack(side=LEFT, padx=(6, 0))
        ttk.Label(
            self.cut_tab,
            text="O modo rápido preserva os codecs, mas início e fim podem variar até o keyframe/pacote disponível.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(self.cut_tab, text="Exemplo: início 12.5 e fim 47.0. O arquivo é salvo com o sufixo _cortado.", style="Muted.TLabel").pack(anchor="w", pady=(10, 0))
        self._update_cut_controls()

    def _build_extract_tab(self) -> None:
        self._section_title(self.extract_tab, "Extrair áudio", "Extrai o primeiro áudio de um ou mais vídeos/áudios. Os parâmetros são os mesmos usados no Android.")
        self._file_row(self.extract_tab, self.extract_summary_var, self.select_extract_inputs, "Selecionar arquivos")
        self.extract_preview = self._create_stable_preview(self.extract_tab, "Escolha um arquivo para visualizar ou ouvir")
        self.extract_preview.bind("<Configure>", lambda _event: self.preview_player.resize(self.extract_preview))
        self.extract_play_button = self._add_preview_speed_controls(self.extract_tab)
        self.extract_timeline = RangeTimeline(self.extract_tab, self._extract_timeline_changed)
        self.extract_timeline.pack(fill=X, pady=(0, 4))
        self._add_preview_time_label(self.extract_tab, self.extract_current_var)
        presets = ttk.Frame(self.extract_tab)
        presets.pack(anchor="w", pady=(0, 10))
        ttk.Checkbutton(
            presets,
            text="Padrão para transcrição",
            variable=self.extract_transcription_preset_var,
            command=lambda: self._set_extract_preset("transcription"),
        ).pack(side=LEFT)
        ttk.Checkbutton(
            presets,
            text="Padrão compacto",
            variable=self.extract_compact_preset_var,
            command=lambda: self._set_extract_preset("compact"),
        ).pack(side=LEFT, padx=(16, 0))
        settings = ttk.Frame(self.extract_tab)
        settings.pack(anchor="w")
        fields = (
            ("Formato:", self.extract_extension_var, ("wav", "m4a", "mp3", "aac", "ogg", "opus", "flac")),
            ("Hz:", self.extract_rate_var, ("8000", "16000", "22050", "44100", "48000")),
            ("Canais:", self.extract_channels_var, ("1", "2")),
            ("Bitrate:", self.extract_bitrate_var, ("32k", "48k", "64k", "96k", "128k", "192k", "256k")),
        )
        self.extract_custom_widgets = []
        for column, (label, variable, choices) in enumerate(fields):
            ttk.Label(settings, text=label).grid(row=0, column=column * 2, sticky="w", padx=(0 if column == 0 else 12, 5))
            combo = ttk.Combobox(settings, textvariable=variable, values=choices, state="readonly", width=8)
            combo.grid(row=0, column=column * 2 + 1)
            self.extract_custom_widgets.append(combo)
        self.extract_extension_combo = self.extract_custom_widgets[0]
        self.extract_rate_combo = self.extract_custom_widgets[1]
        self.extract_channels_combo = self.extract_custom_widgets[2]
        self.extract_bitrate_combo = self.extract_custom_widgets[3]
        self.extract_extension_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_extract_format_changed())
        self.extract_rate_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_extract_bitrate_choices())
        self.extract_channels_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_extract_bitrate_choices())
        self._on_extract_format_changed()
        trim = ttk.Frame(self.extract_tab)
        trim.pack(anchor="w", pady=(12, 0))
        ttk.Label(trim, text="Recorte opcional - início (s):").grid(row=0, column=0, sticky="w")
        extract_start_entry = ttk.Entry(trim, textvariable=self.extract_start_var, width=10)
        extract_start_entry.grid(row=0, column=1, padx=(6, 16))
        ttk.Label(trim, text="fim (s):").grid(row=0, column=2, sticky="w")
        extract_end_entry = ttk.Entry(trim, textvariable=self.extract_end_var, width=10)
        extract_end_entry.grid(row=0, column=3, padx=(6, 0))
        extract_start_entry.bind("<FocusOut>", lambda _event: self._sync_extract_range_from_entries())
        extract_end_entry.bind("<FocusOut>", lambda _event: self._sync_extract_range_from_entries())

    def _build_rotate_tab(self) -> None:
        self._section_title(self.rotate_tab, "Girar e cortar vídeo", "Gira a imagem, permite recortar o intervalo e preserva o áudio. A opção de metadados evita reencodar a imagem.")
        self._file_row(self.rotate_tab, self.rotate_input_var, self.select_rotate_input, "Selecionar vídeo")
        self.rotate_preview = self._create_stable_preview(self.rotate_tab, "Selecione um vídeo para visualizar")
        self.rotate_preview.bind("<Configure>", lambda _event: self.preview_player.resize(self.rotate_preview))
        self.rotate_play_button = self._add_preview_speed_controls(self.rotate_tab)
        self.rotate_timeline = RangeTimeline(self.rotate_tab, self._rotate_timeline_changed)
        self.rotate_timeline.pack(fill=X, pady=(0, 4))
        self._add_preview_time_label(self.rotate_tab, self.rotate_current_var)
        trim = ttk.Frame(self.rotate_tab)
        trim.pack(anchor="w", pady=(0, 10))
        ttk.Label(trim, text="Início (segundos):").grid(row=0, column=0, sticky="w")
        rotate_start_entry = ttk.Entry(trim, textvariable=self.rotate_start_var, width=12)
        rotate_start_entry.grid(row=0, column=1, padx=(6, 18))
        ttk.Label(trim, text="Fim (segundos):").grid(row=0, column=2, sticky="w")
        rotate_end_entry = ttk.Entry(trim, textvariable=self.rotate_end_var, width=12)
        rotate_end_entry.grid(row=0, column=3, padx=(6, 0))
        rotate_start_entry.bind("<FocusOut>", lambda _event: self._sync_rotate_range_from_entries())
        rotate_end_entry.bind("<FocusOut>", lambda _event: self._sync_rotate_range_from_entries())
        row = ttk.Frame(self.rotate_tab)
        row.pack(anchor="w")
        ttk.Label(row, text="Giro:").pack(side=LEFT)
        rotate_combo = ttk.Combobox(row, textvariable=self.rotate_degrees_var, values=("-90", "0", "90", "180"), state="readonly", width=7)
        rotate_combo.pack(side=LEFT, padx=(6, 18))
        rotate_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_rotate_transform_changed())
        self.rotate_hflip_check = ttk.Checkbutton(row, text="Espelhar horizontal", variable=self.rotate_hflip_var, command=self._on_rotate_transform_changed)
        self.rotate_hflip_check.pack(side=LEFT, padx=(0, 12))
        self.rotate_vflip_check = ttk.Checkbutton(row, text="Espelhar vertical", variable=self.rotate_vflip_var, command=self._on_rotate_transform_changed)
        self.rotate_vflip_check.pack(side=LEFT, padx=(0, 12))
        rotate_options = ttk.Frame(self.rotate_tab)
        rotate_options.pack(anchor="w", pady=(12, 0))
        self.rotate_metadata_check = ttk.Checkbutton(
            rotate_options,
            text="Somente metadados de rotação (rápido, sem reencodar)",
            variable=self.rotate_metadata_var,
            command=self._update_rotate_control_state,
        )
        self.rotate_metadata_check.pack(side=LEFT)
        self.rotate_parallel_check = ttk.Checkbutton(
            rotate_options,
            text="Processar trechos em paralelo",
            variable=self.rotate_parallel_var,
            command=self._update_rotate_control_state,
        )
        self.rotate_parallel_check.pack(side=LEFT, padx=(18, 0))
        self.rotate_parallel_frame = ttk.Frame(self.rotate_tab)
        ttk.Label(self.rotate_parallel_frame, text="Trechos:").pack(side=LEFT)
        self.rotate_segments_entry = ttk.Entry(self.rotate_parallel_frame, textvariable=self.rotate_segments_var, width=8)
        self.rotate_segments_entry.pack(side=LEFT, padx=(6, 4))
        ttk.Button(
            self.rotate_parallel_frame,
            text="?",
            width=3,
            command=lambda: messagebox.showinfo(
                "Trechos em paralelo",
                "O valor define quantos trechos serão criados e quantos poderão ser processados simultaneamente. "
                "Mais trechos podem acelerar vídeos longos, mas valores altos consomem RAM, aquecem o PC e podem saturar o encoder de hardware. "
                "Em vídeos curtos, o overhead pode piorar o tempo. Deixe vazio para usar todos os núcleos lógicos em CPU; "
                "com encoder de hardware (NVENC/QSV/AMF), o padrão é limitado a 3 processos simultâneos por segurança das sessões do driver.",
            ),
        ).pack(side=LEFT)
        self.rotate_device_limit_var = StringVar(value="")
        self.rotate_device_limit_label = ttk.Label(self.rotate_tab, textvariable=self.rotate_device_limit_var, foreground="#b3261e")
        self._update_rotate_control_state()

    def _build_join_tab(self) -> None:
        self._section_title(
            self.join_tab,
            "Juntar áudios/vídeos",
            "Junta arquivos do mesmo tipo. O SmartJoin (Experimental) copia sem transição e reencoda a saída inteira quando há transição.",
        )
        controls = ttk.Frame(self.join_tab)
        controls.pack(fill=X)
        ttk.Button(controls, text="Adicionar áudios/vídeos", command=self.add_join_inputs).pack(side=LEFT)
        ttk.Button(controls, text="Remover", command=self.remove_join_input).pack(side=LEFT, padx=(8, 0))
        ttk.Button(controls, text="Subir", command=lambda: self.move_join_input(-1)).pack(side=LEFT, padx=(8, 0))
        ttk.Button(controls, text="Descer", command=lambda: self.move_join_input(1)).pack(side=LEFT, padx=(8, 0))
        list_frame = ttk.Frame(self.join_tab)
        list_frame.pack(fill=BOTH, expand=True, pady=(10, 12))
        self.join_list = self.tk.Listbox(list_frame, height=6, activestyle="none", font=("Segoe UI", 9))
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.join_list.yview)
        self.join_list.configure(yscrollcommand=scroll.set)
        self.join_list.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        join_checks = ttk.Frame(self.join_tab)
        join_checks.pack(anchor="w")
        self.join_reencode_check = ttk.Checkbutton(
            join_checks,
            text="Reencode Completo",
            variable=self.join_reencode_var,
            command=self._on_toggle_join_reencode,
        )
        self.join_reencode_check.pack(side=LEFT)
        self.join_smart_check = ttk.Checkbutton(
            join_checks,
            text="SmartJoin (Experimental)",
            variable=self.join_smart_var,
            command=self._on_toggle_join_smart,
        )
        self.join_smart_check.pack(side=LEFT, padx=(18, 0))
        options = ttk.Frame(self.join_tab)
        options.pack(anchor="w", pady=(8, 0))
        ttk.Label(options, text="Transição:").grid(row=0, column=0, sticky="w")
        self.join_transition_combo = ttk.Combobox(options, textvariable=self.join_transition_var, values=self.TRANSITIONS, state="readonly", width=15)
        self.join_transition_combo.grid(row=0, column=1, padx=(6, 16))
        ttk.Label(options, text="Tempo (s):").grid(row=0, column=2, sticky="w")
        self.join_seconds_entry = ttk.Entry(options, textvariable=self.join_seconds_var, width=7)
        self.join_seconds_entry.grid(row=0, column=3, padx=(6, 0))
        policies = ttk.Frame(self.join_tab)
        policies.pack(anchor="w", pady=(8, 0))
        ttk.Label(policies, text="Perfil de saída:").grid(row=0, column=0, sticky="w")
        self.join_profile_combo = ttk.Combobox(
            policies,
            textvariable=self.join_profile_var,
            values=("Primeiro clipe", "Maior resolução", "Menor resolução (sem upscale)"),
            state="readonly",
            width=28,
        )
        self.join_profile_combo.grid(row=0, column=1, padx=(6, 16))
        ttk.Label(policies, text="Streams:").grid(row=0, column=2, sticky="w")
        self.join_stream_policy_combo = ttk.Combobox(
            policies,
            textvariable=self.join_stream_policy_var,
            values=("Primeira faixa (MP4)", "Todas as faixas (MKV, sem transição)"),
            state="readonly",
            width=34,
        )
        self.join_stream_policy_combo.grid(row=0, column=3, padx=(6, 0))
        self.join_stream_policy_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_join_controls())
        ttk.Label(policies, text="Áudio ausente:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.join_audio_policy_combo = ttk.Combobox(
            policies,
            textvariable=self.join_audio_policy_var,
            values=("Preservar áudio e preencher silêncio", "Gerar saída sem áudio"),
            state="readonly",
            width=32,
        )
        self.join_audio_policy_combo.grid(row=1, column=1, columnspan=2, sticky="w", padx=(6, 0), pady=(6, 0))
        self.join_audio_policy_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_join_controls())
        self._update_join_controls()

    def _build_insert_tab(self) -> None:
        self._section_title(
            self.insert_tab,
            "Inserir áudio",
            "Insere um segundo áudio no ponto escolhido do áudio principal. Smart Insert preserva o máximo possível do áudio original (as curvas de transição, incluindo 'Fade in/out', suavizam apenas o áudio inserido); Reencode Completo também oferece 'Fade in/out' e as demais curvas com sobreposição (crossfade) e cortes precisos.",
        )
        select_row = ttk.Frame(self.insert_tab)
        select_row.pack(anchor="w", pady=(0, 6))
        self.insert_main_button = ttk.Button(select_row, text="+ Áudio principal", command=self.select_insert_main_input)
        self.insert_main_button.pack(side=LEFT)
        self.insert_secondary_button = ttk.Button(select_row, text="+ Inserir áudio", command=self.select_insert_secondary_input, state="disabled")
        self.insert_secondary_button.pack(side=LEFT, padx=(10, 0))
        names = ttk.Frame(self.insert_tab)
        names.pack(fill=X, pady=(0, 8))
        ttk.Label(names, textvariable=self.insert_main_var, style="Muted.TLabel", wraplength=780).pack(anchor="w")
        self.insert_secondary_label = ttk.Label(names, textvariable=self.insert_secondary_var, style="Muted.TLabel", wraplength=780)
        self.insert_secondary_label.pack(anchor="w", pady=(2, 0))

        self.insert_play_button = self._add_preview_speed_controls(self.insert_tab)
        self.insert_timeline = InsertAudioTimeline(
            self.insert_tab,
            self._insert_timeline_changed,
            self._insert_position_changed,
        )
        self.insert_timeline.pack(fill=X, pady=(2, 4))
        self._add_preview_time_label(self.insert_tab, self.insert_current_var)

        time_row = ttk.Frame(self.insert_tab)
        time_row.pack(anchor="w", pady=(0, 8))
        ttk.Label(time_row, text="Ponto de inserção no áudio principal:").pack(side=LEFT)
        self.insert_time_entry = ttk.Entry(time_row, textvariable=self.insert_time_var, width=14)
        self.insert_time_entry.pack(side=LEFT, padx=(8, 0))
        self.insert_time_entry.bind("<FocusOut>", lambda _event: self._apply_insert_time())
        self.insert_time_entry.bind("<Return>", lambda _event: self._apply_insert_time())

        self.insert_options_frame = ttk.Frame(self.insert_tab)
        self.insert_options_frame.pack(anchor="w", pady=(4, 0))
        transition_row = ttk.Frame(self.insert_options_frame)
        transition_row.pack(anchor="w")
        ttk.Label(transition_row, text="Transição:").pack(side=LEFT)
        self.insert_transition_combo = ttk.Combobox(
            transition_row,
            textvariable=self.insert_transition_var,
            values=tuple(label for label, _value in self.AUDIO_TRANSITIONS),
            state="disabled",
            width=30,
        )
        self.insert_transition_combo.pack(side=LEFT, padx=(6, 12))
        self.insert_transition_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_insert_controls())
        ttk.Label(transition_row, text="Tempo (s):").pack(side=LEFT)
        self.insert_seconds_entry = ttk.Entry(transition_row, textvariable=self.insert_seconds_var, width=7, state="disabled")
        self.insert_seconds_entry.pack(side=LEFT, padx=(6, 0))
        checks = ttk.Frame(self.insert_options_frame)
        checks.pack(anchor="w", pady=(8, 0))
        self.insert_reencode_check = ttk.Checkbutton(
            checks,
            text="Reencode Completo",
            variable=self.insert_reencode_var,
            command=self._on_toggle_insert_reencode,
        )
        self.insert_reencode_check.pack(side=LEFT)
        self.insert_smart_check = ttk.Checkbutton(
            checks,
            text="Smart Insert",
            variable=self.insert_smart_var,
            command=self._on_toggle_insert_smart,
        )
        self.insert_smart_check.pack(side=LEFT, padx=(18, 0))
        ttk.Label(
            self.insert_options_frame,
            text="Sem reencodar, o ponto pode variar até o frame/pacote disponível e transições não são aplicadas. Quando uma transição está ativa, a prévia usa o mesmo filtro da saída.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(8, 0))
        self.insert_options_frame.pack_forget()

    def _build_clean_tab(self) -> None:
        self._section_title(self.clean_tab, "Limpar áudio", "Remove ruído e permite gerar áudio para transcrição ou preservar canais e taxa da fonte.")
        self._file_row(self.clean_tab, self.clean_input_var, self.select_clean_input)
        row = ttk.Frame(self.clean_tab)
        row.pack(anchor="w")
        ttk.Label(row, text="Filtro:").pack(side=LEFT)
        ttk.Combobox(row, textvariable=self.clean_mode_var, values=("equilibrado", "forte"), state="readonly", width=15).pack(side=LEFT, padx=(6, 0))
        ttk.Label(row, text="Saída:").pack(side=LEFT, padx=(18, 0))
        ttk.Combobox(
            row,
            textvariable=self.clean_output_profile_var,
            values=("Transcrição (mono, 16 kHz)", "Preservar taxa e canais da fonte"),
            state="readonly",
            width=32,
        ).pack(side=LEFT, padx=(6, 0))

    def _select_ffmpeg_tool(self, selected: str) -> None:
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

    @staticmethod
    def _rotation_uses_video_encoder(metadata_only: bool, degrees: int, hflip: bool, vflip: bool) -> bool:
        # Sem filtro visual (grau 0 e sem espelhamento) o worker usa -c copy: encoder não tem efeito.
        return (not metadata_only) and (degrees % 360 != 0 or hflip or vflip)

    def _update_cut_controls(self) -> None:
        fast = self.cut_mode_var.get().startswith("Rápido")
        profile = getattr(self, "cut_media_profile", None)
        has_video = bool(profile and profile.has_video)
        running = getattr(self, "running", False)
        self.cut_audio_policy_combo.configure(state="readonly" if (has_video and not fast and not running) else "disabled")
        self.cut_stream_policy_combo.configure(state="readonly" if (has_video and fast and not running) else "disabled")
        if not fast:
            self.cut_stream_policy_var.set("Vídeo e áudio")
        self._refresh_encoder_control_state()

    def _current_tool_uses_video_encoder(self) -> bool:
        tool = self.active_tool_var.get()
        if tool == "Cortar":
            if self.cut_mode_var.get().startswith("Rápido"):
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
            return
        self.acceleration_combo.configure(state="readonly")
        if not self.quality_label.winfo_ismapped():
            self.quality_help_button.pack(side=RIGHT, padx=(4, 0), pady=(2, 0))
            self.quality_menu_button.pack(side=RIGHT, pady=(2, 0))
            self.quality_label.pack(side=RIGHT, padx=(12, 4), pady=(4, 0))

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
        enabled = has_mode and not self.running and self.insert_secondary_input is not None

        self.insert_reencode_check.configure(state="normal" if not self.running else "disabled")
        self.insert_smart_check.configure(state="normal" if not self.running else "disabled")
        self.insert_transition_combo.configure(state="readonly" if enabled else "disabled")
        seconds_relevant = enabled and self.insert_transition_var.get() != "Sem transição"
        self.insert_seconds_entry.configure(state="normal" if seconds_relevant else "disabled")

        if smart:
            # Smart Insert: todas as curvas disponíveis — cada uma suaviza
            # apenas o áudio inserido (afade com a curva escolhida).
            choices = tuple(label for label, _value in self.AUDIO_TRANSITIONS)
            self.insert_transition_combo.configure(values=choices)
            if self.insert_transition_var.get() not in choices:
                self.insert_transition_var.set("Fade in/out")
        elif reencode:
            # Reencode Completo: mesmo conjunto do Smart (inclui "Fade in/out",
            # aplicado com afade; as demais curvas usam acrossfade).
            choices = tuple(label for label, _value in self.AUDIO_TRANSITIONS)
            self.insert_transition_combo.configure(values=choices)
            if self.insert_transition_var.get() not in choices:
                self.insert_transition_var.set("Linear")
        else:
            self.insert_transition_var.set("Sem transição")

    def _show_insert_options(self, visible: bool) -> None:
        if visible:
            if not self.insert_options_frame.winfo_ismapped():
                self.insert_options_frame.pack(anchor="w", pady=(4, 0))
        else:
            self.insert_options_frame.pack_forget()
        self._update_insert_controls()

    @staticmethod
    def _clock(seconds: float) -> str:
        milliseconds = max(0, int(seconds * 1000))
        total, millis = divmod(milliseconds, 1000)
        return f"{total // 60}:{total % 60:02d}.{millis:03d}"

    def _activate_preview(self, source: Path, canvas: Canvas, timeline: RangeTimeline, current_var: StringVar, button, tool: str) -> None:
        self._stop_preview()
        media = self._probe_media(source)
        duration = media.duration
        timeline.set_media(duration)
        current_var.set(self._clock(0))
        self.preview_context = {
            "source": source,
            "canvas": canvas,
            "timeline": timeline,
            "current_var": current_var,
            "button": button,
            "duration": duration,
            "tool": tool,
            "audio_only": not media.has_video,
            "has_video": media.has_video,
            "has_audio": media.has_audio,
        }
        if not self.preview_context["audio_only"]:
            self._show_video_thumbnail(canvas, source, 0.0, self._rotate_preview_filter() if tool == "rotate" else "")
        else:
            canvas.delete("all")
            canvas.create_text(
                canvas.winfo_width() // 2,
                canvas.winfo_height() // 2,
                text="Prévia de áudio",
                fill="#d7e2df",
                font=("Segoe UI", 11),
            )

    def _stop_preview(self) -> None:
        self.preview_generation += 1
        self.preview_playing = False
        if self.preview_after_id:
            try:
                self.root.after_cancel(self.preview_after_id)
            except Exception:
                pass
            self.preview_after_id = None
        self.preview_player.close()
        self._terminate_preview_process(self.external_preview_process)
        self.external_preview_process = None
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
                messagebox.showerror("sig", f"Não foi possível reproduzir o áudio:\n{exc}")
            return
        use_canvas = self.preview_speed != 1.0 or (context["tool"] == "rotate" and bool(self._rotate_preview_filter()))
        if use_canvas or not self.preview_player.open(context["source"], context["canvas"]):
            try:
                self._start_canvas_preview(context, position)
            except Exception as exc:
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
        target = max(0.5, min(4.0, float(self.preview_speed)))
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
        if insertion > 0.001:
            neighbors.append(insertion)
        if main_duration - insertion > 0.001:
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

    def _insert_smart_preview_filter(
        self,
        profile: MediaProfile,
        inserted_duration: float,
        insertion: float,
        fade_seconds: float,
        fade_curve: str = "fade",
    ) -> str:
        normalize = (
            f"aresample={profile.audio_rate},"
            f"aformat=sample_fmts=fltp:sample_rates={profile.audio_rate}:channel_layouts={profile.audio_layout}"
        )
        labels: list[str] = []
        parts: list[str] = []
        if insertion > 0.001:
            parts.append(f"[0:a]atrim=0:{self._fmt_seconds(insertion)},{normalize},asetpts=PTS-STARTPTS[a0]")
            labels.append("a0")
        effective = min(fade_seconds, inserted_duration / 2)
        fades = ""
        if effective > 0:
            curve = "" if fade_curve in ("", "fade", "none") else f":curve={fade_curve}"
            fades = (
                f",afade=t=in:st=0:d={self._fmt_seconds(effective)}{curve},"
                f"afade=t=out:st={self._fmt_seconds(max(0.0, inserted_duration - effective))}:d={self._fmt_seconds(effective)}{curve}"
            )
        parts.append(
            f"[1:a]atrim=0:{self._fmt_seconds(inserted_duration)},{normalize},"
            f"asetpts=PTS-STARTPTS{fades}[a1]"
        )
        labels.append("a1")
        if profile.duration - insertion > 0.001:
            parts.append(
                f"[0:a]atrim={self._fmt_seconds(insertion)}:{self._fmt_seconds(profile.duration)},"
                f"{normalize},asetpts=PTS-STARTPTS[a2]"
            )
            labels.append("a2")
        parts.append("".join(f"[{label}]" for label in labels) + f"concat=n={len(labels)}:v=0:a=1[aout]")
        return ";".join(parts)

    def _start_insert_filtered_preview(self, context: dict, composite_position: float) -> bool:
        main = self.insert_main_input
        inserted = self.insert_secondary_input
        if not main or not inserted:
            return False
        transition_label = self.insert_transition_var.get()
        transition_code = dict(self.AUDIO_TRANSITIONS).get(transition_label, "none")
        try:
            requested = float(self.insert_seconds_var.get().replace(",", ".")) if transition_code != "none" else 0.0
        except ValueError:
            return False
        full_reencode = self.insert_reencode_var.get()
        smart_transition = self.insert_smart_var.get() and transition_code != "none" and requested > 0
        if not (full_reencode and transition_code != "none" and requested > 0) and not smart_transition:
            return False

        profile = self._probe_media(main)
        inserted_duration = self._get_duration_only(inserted)
        insertion = self.insert_timeline.insertion
        effective = self._insert_effective_transition(profile.duration, inserted_duration, insertion, requested)
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
            insertion > 0.001,
            profile.duration - insertion > 0.001,
        )
        filter_text += (
            f";[aout]atrim=start={self._fmt_seconds(output_position)},"
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
        context["insert_preview_has_left"] = insertion > 0.001
        context["insert_preview_has_right"] = profile.duration - insertion > 0.001
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
            self.external_preview_process = subprocess.Popen(
                [
                    str(self._ffplay()), "-hide_banner", "-loglevel", "warning", "-autoexit", "-nodisp",
                    "-ss", self._fmt_seconds(offset), "-t", self._fmt_seconds(self._audio_preview_media_duration(timeline.end, offset)), "-af", self._preview_atempo_filter(), str(context["source"]),
                ],
                creationflags=flags | (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
            self.preview_playing = True
            context["button"].configure(text="||")
            self.status_var.set("Reproduzindo áudio dentro da ferramenta.")
            self._audio_preview_tick(context, generation)
            return
        width = max(320, canvas.winfo_width())
        height = max(180, canvas.winfo_height())
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
            self.external_preview_process = subprocess.Popen(
                audio_command,
                creationflags=flags | (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
        else:
            self.external_preview_process = None
        self.preview_playing = True
        context["button"].configure(text="||")
        self.status_var.set("Prévia reproduzida dentro da ferramenta.")

        def render_frames():
            process = self.frame_preview_process
            frame_size = width * height * 3
            index = 0
            started_at = time.monotonic()
            try:
                while process and process.stdout and not self.frame_preview_stop_event.is_set():
                    raw = process.stdout.read(frame_size)
                    if len(raw) != frame_size:
                        break
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
        process = self.external_preview_process
        if not process or process.poll() is not None or position >= timeline.end - 0.03:
            self._terminate_preview_process(process)
            self.external_preview_process = None
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
        try:
            self.root.after(33, self._poll_preview_frames)
        except Exception:
            pass

    def _render_canvas_frame(self, context: dict, generation: int, image: Image.Image, position: float) -> None:
        if self.frame_preview_stop_event.is_set() or context is not self.preview_context or generation != self.preview_generation:
            return
        photo = ImageTk.PhotoImage(image)
        canvas = context["canvas"]
        self.preview_image_refs[canvas] = photo
        canvas.delete("all")
        canvas.create_image(canvas.winfo_width() // 2, canvas.winfo_height() // 2, image=photo, anchor="center")
        context["timeline"].set_position(position)
        context["current_var"].set(self._clock(position))

    def _finish_canvas_preview(self, context: dict, generation: int) -> None:
        if self.frame_preview_stop_event.is_set() or context is not self.preview_context or generation != self.preview_generation:
            return
        self.preview_playing = False
        self.frame_preview_process = None
        self._terminate_preview_process(self.external_preview_process)
        self.external_preview_process = None
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
        self._show_video_thumbnail(
            self.rotate_preview,
            self.rotate_input,
            self.rotate_timeline.position,
            self._rotate_preview_filter(),
        )

    def _show_video_thumbnail(self, canvas: Canvas, source: Path, seconds: float, filters: str) -> None:
        canvas.delete("all")
        context = getattr(self, "preview_context", None)
        context_matches = bool(context and context.get("source") == source)
        has_video = bool(context.get("has_video")) if context_matches else self._probe_media(source).has_video
        if not has_video:
            canvas.create_text(
                max(80, canvas.winfo_width() // 2), max(40, canvas.winfo_height() // 2),
                text=f"{source.name}\nPrévia de áudio", fill="#667371", font=("Segoe UI", 10), justify="center",
            )
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        image_path = self.output_dir / f"preview_{uuid.uuid4().hex}.png"
        command = [str(self._ffmpeg()), "-hide_banner", "-loglevel", "error", "-y", "-ss", self._fmt_seconds(seconds), "-i", str(source), "-frames:v", "1"]
        if filters:
            command += ["-vf", filters]
        command.append(str(image_path))
        try:
            self._record_ffmpeg_command(command, force=True)
            result = subprocess.run(command, capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if result.returncode != 0 or not image_path.exists():
                raise RuntimeError("FFmpeg não gerou a prévia")
            with Image.open(image_path) as image:
                image.thumbnail((max(240, canvas.winfo_width() - 12), max(150, canvas.winfo_height() - 12)), Image.LANCZOS)
                photo = ImageTk.PhotoImage(image.copy())
            self.preview_image_refs[canvas] = photo
            canvas.create_image(canvas.winfo_width() // 2, canvas.winfo_height() // 2, image=photo, anchor="center")
        except Exception:
            canvas.create_text(
                max(80, canvas.winfo_width() // 2), max(40, canvas.winfo_height() // 2),
                text="Não foi possível gerar a prévia deste vídeo", fill="#667371", font=("Segoe UI", 10), justify="center",
            )
        finally:
            image_path.unlink(missing_ok=True)

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
                self.extract_timeline.set_media(0)
                self.extract_preview.delete("all")
                self.extract_preview.create_text(400, 90, text="O recorte com marcadores fica disponível ao selecionar um único arquivo.", fill="#d7e2df", font=("Segoe UI", 10))
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
            self.clean_input = Path(selected)
            self.clean_input_var.set(self.clean_input.name)

    def select_insert_main_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="Selecionar áudio principal",
            filetypes=[("Áudios", "*.wav *.mp3 *.m4a *.ogg *.opus *.flac *.aac *.wma"), ("Todos os arquivos", "*.*")],
        )
        if not selected:
            return
        source = Path(selected)
        media = self._probe_media(source)
        if not media.has_audio:
            messagebox.showerror("sig", "O arquivo selecionado não contém uma faixa de áudio.")
            return
        self._stop_preview()
        self.insert_main_input = source
        self.insert_secondary_input = None
        self.insert_main_var.set(source.name)
        self.insert_secondary_var.set("Nenhum áudio para inserir")
        self.insert_timeline.configure_media(source.name, media.duration)
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
        media = self._probe_media(source)
        if not media.has_audio:
            messagebox.showerror("sig", "O arquivo selecionado não contém uma faixa de áudio.")
            return
        insertion = self.insert_timeline.composite_to_main(self.insert_timeline.position)
        self._stop_preview()
        self.insert_secondary_input = source
        self.insert_secondary_var.set(f"Inserir: {source.name}")
        main_media = self._probe_media(self.insert_main_input)
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
        self.join_list.delete(0, END)
        for index, path in enumerate(self.join_inputs, start=1):
            self.join_list.insert(END, f"{index}. {path.name}")
        if selected_index is not None and self.join_inputs:
            self.join_list.selection_set(selected_index)
        self._update_join_controls()
        self._refresh_encoder_control_state()

    def choose_output_dir(self) -> None:
        chosen = filedialog.askdirectory(title="Selecionar pasta de saída do FFmpeg", initialdir=str(self.output_dir))
        if chosen:
            self.output_dir = Path(chosen)
            self.output_dir_var.set(str(self.output_dir))

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
        # Capture Tk state on the UI thread. Workers use only plain Python values.
        self.selected_acceleration_label = self.acceleration_var.get()
        self.selected_video_quality = self.video_quality_var.get()
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
            "clean_mode": self.clean_mode_var.get(), "clean_output_profile": self.clean_output_profile_var.get(),
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
            if hasattr(self, "selected_acceleration_label"):
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
                self._set_status("Concluído. Arquivo(s) salvo(s) na pasta de saída.", 100)
                elapsed = max(.001, time.monotonic() - self.task_started_at)
                encoder = self.acceleration.encoder if (self.acceleration and tool_uses_video_encoder) else "não aplicável"
                self.task_tracker.success(f"Tempo de processamento: {elapsed:.1f}s\nEncoder: {encoder}") if self.task_tracker else None
        except Cancelled:
            self._set_status("Operação cancelada.")
            if self.task_tracker: self.task_tracker.fail("Operação cancelada pelo usuário.")
        except Exception as exc:
            self._set_status(f"Erro: {exc}")
            if self.task_tracker: self.task_tracker.fail(str(exc))
        finally:
            self.root.after(0, lambda: self._set_running_ui(False))

    def _worker_value(self, name: str, variable):
        options = getattr(self, "worker_options", None)
        if options and name in options:
            return options[name]
        return variable.get()

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
            self.acceleration_combo.configure(values=tuple(profile.label for profile in profiles))
            if self.acceleration_var.get() not in self.acceleration_by_label:
                self.acceleration_var.set(profiles[0].label)
            self._refresh_encoder_control_state()

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
        candidates = (
            VideoAcceleration("nvenc", "NVENC (NVIDIA)", "h264_nvenc"),
            VideoAcceleration("qsv", "QSV (Intel)", "h264_qsv"),
            VideoAcceleration("vaapi", "VAAPI (Linux)", "h264_vaapi"),
            VideoAcceleration("amf", "AMF (AMD)", "h264_amf"),
        )
        available: list[VideoAcceleration] = []
        for candidate in candidates:
            if candidate.encoder not in encoders:
                continue
            if candidate.key == "vaapi" and (os.name == "nt" or not Path("/dev/dri/renderD128").exists()):
                continue
            if self._test_encoder(candidate):
                available.append(candidate)
        available.append(VideoAcceleration("cpu", "CPU (fallback)", "libx264" if "libx264" in encoders else "mpeg4"))
        return available

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
        if profile.encoder == "libx264":
            crf = {"Máxima": 16, "Muito alta": 18, "Alta": 20, "Média": 23, "Econômica": 26}[quality]
            return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf)]
        if profile.encoder == "libx265":
            crf = {"Máxima": 18, "Muito alta": 20, "Alta": 22, "Média": 25, "Econômica": 28}[quality]
            return ["-c:v", "libx265", "-preset", "medium", "-crf", str(crf)]
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
        self._set_status(f"{label} concluído ({progress}/{total})", int(progress * 100 / max(total, 1)))

    def _execute_video(self, label: str, builder, progress: int = 1, total: int = 1, duration_seconds: float = 0.0, progress_callback=None) -> None:
        cpu_fallback = next((acc for acc in getattr(self, "available_accelerations", []) if acc.key == "cpu"), VideoAcceleration("cpu", "CPU (fallback)", "libx264"))
        profile = self.acceleration or cpu_fallback
        try:
            self._execute(builder(profile), label, progress, total, duration_seconds, progress_callback)
        except RuntimeError as exc:
            if profile.key == "cpu" or not self._is_hardware_encoder_error(str(exc)):
                raise
            self._append_log(f"{profile.label} não concluiu a tarefa; repetindo com CPU ({cpu_fallback.encoder}).")
            self.acceleration = cpu_fallback
            if hasattr(self, "root") and hasattr(self, "acceleration_var"):
                self.root.after(0, lambda: self.acceleration_var.set(cpu_fallback.label))
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
        if seconds < 0:
            raise RuntimeError(f"{label} não pode ser negativo")
        return seconds

    @staticmethod
    def _fmt_seconds(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

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
            cut_mode = str(cut_mode_var.get()) if cut_mode_var is not None else "Preciso (reencodar)"
        fast_copy = cut_mode.startswith("Rápido")
        audio_policy = str(self._worker_value_default("cut_audio_policy", "cut_audio_policy_var", "Precisão máxima (AAC)"))
        stream_policy = str(self._worker_value_default("cut_stream_policy", "cut_stream_policy_var", "Vídeo e áudio"))
        preserve_all_streams = fast_copy and stream_policy.startswith("Todos os streams")
        if is_video:
            extension = self._metadata_rotate_output_suffix(source.suffix) if fast_copy else ".mp4"
        else:
            extension = self._audio_only_output_extension(source)
        output = self._safe_output(self.output_dir, f"{source.stem}_cortado", extension)

        if fast_copy:
            self._append_log(
                "Corte rápido: codecs preservados; os limites são aproximados ao keyframe/pacote disponível."
            )
            command = [
                str(self._ffmpeg()), "-hide_banner", "-y", "-ss", self._fmt_seconds(start),
                "-i", str(source), "-t", self._fmt_seconds(duration),
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
        elif is_video:
            self._cut_video_precise(
                source, output, start, end, media,
                copy_audio=audio_policy.startswith("Copiar áudio"),
            )
        else:
            codec_args = self._audio_codec_args_for_source_codec(
                media.audio_codec, extension, media.audio_bitrate
            ) or self._audio_codec_args(extension, media.audio_bitrate)
            command = [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", self._fmt_seconds(start), "-i", str(source), "-t", self._fmt_seconds(duration), "-map", "0:a:0?", "-vn", *codec_args, "-map_metadata", "0", str(output)]
            self._execute(command, "Cortando áudio", 1, 1, duration)

    def _cut_video_precise(
        self,
        source: Path,
        output: Path,
        start: float,
        end: float,
        media: MediaProfile,
        copy_audio: bool = False,
    ) -> None:
        if media.audio_streams > 1:
            action = "copiadas nos limites de pacote" if copy_audio else "preservadas e reencodadas em AAC"
            self._append_log(f"{source.name} possui {media.audio_streams} faixas de áudio; todas serão {action}.")
        if media.subtitle_streams or media.data_streams:
            self._append_log("Legendas, anexos e streams de dados não são preservados no corte MP4.")
        if copy_audio and media.has_audio and media.audio_codec not in self._MP4_SAFE_AUDIO_CODECS:
            raise RuntimeError(
                f"O codec de áudio '{media.audio_codec}' não pode ser copiado para MP4. "
                "Use 'Precisão máxima (AAC)'."
            )
        if copy_audio and media.has_audio:
            self._append_log("O vídeo será cortado com precisão; o áudio será copiado nos limites de pacote disponíveis.")

        def build(profile: VideoAcceleration):
            input_args, filter_args = self._filter_for_profile("null", profile)
            audio_args = ["-c:a", "copy"] if copy_audio else [
                "-c:a", "aac", "-b:a", media.audio_bitrate,
                "-ar", str(media.audio_rate), "-ac", str(media.audio_channels),
            ]
            return [
                str(self._ffmpeg()), "-hide_banner", "-y", *input_args,
                "-ss", self._fmt_seconds(start), "-i", str(source),
                "-t", self._fmt_seconds(end - start),
                "-map", "0:v:0?", "-map", "0:a?", "-sn", "-dn", *filter_args,
                *self._video_args(profile, media.video_bitrate), *audio_args,
                "-map_metadata", "0", "-map_chapters", "-1", "-movflags", "+faststart",
                str(output),
            ]

        self._execute_video("Cortando vídeo com precisão", build, duration_seconds=end - start)

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
            output = self._safe_output(self.output_dir, f"{source.stem}_audio", f".{extension}")
            command = [str(self._ffmpeg()), "-hide_banner", "-y"]
            if has_trim and start is not None:
                command += ["-ss", self._fmt_seconds(start)]
            command += ["-i", str(source)]
            if has_trim and start is not None and effective_end is not None:
                command += ["-t", self._fmt_seconds(effective_end - start)]
            command += ["-vn", "-map", "0:a:0?", "-ar", rate, "-ac", channels, *self._audio_codec_args(extension, bitrate), str(output)]
            target_duration = (effective_end - start) if has_trim and start is not None and effective_end is not None else media.duration
            self._execute(command, f"Extraindo {source.name}", index, total, max(0.0, target_duration))
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
        output = self._safe_output(self.output_dir, suffix, ".mp4")
        seek_args = ["-ss", self._fmt_seconds(start)] if has_trim else []
        duration_args = ["-t", self._fmt_seconds(trim_duration)] if has_trim else []
        if bool(self._worker_value("rotate_metadata", self.rotate_metadata_var)):
            if has_trim:
                self._append_log("Modo somente metadados com recorte: o corte é alinhado aos keyframes mais próximos (sem reencodar).")
            # A UI usa +90 como giro horário (transpose=1), enquanto
            # -display_rotation usa ângulo positivo anti-horário.
            target_rotation = (media.rotation - degrees) % 360
            output = self._safe_output(self.output_dir, suffix, self._metadata_rotate_output_suffix(source.suffix))
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
        if not filters:
            output = self._safe_output(self.output_dir, suffix, self._metadata_rotate_output_suffix(source.suffix))
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
            return [str(self._ffmpeg()), "-hide_banner", "-y", *input_args, *seek_args, "-i", str(source), *duration_args, "-map", "0:v:0", "-map", "0:a?", "-sn", "-dn", *filter_args, *self._video_args(profile, media.video_bitrate), *audio_args, "-map_metadata", "0", "-movflags", "+faststart", str(output)]
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

        work_dir = self.output_dir / f"rotate_parallel_{uuid.uuid4().hex}"
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
            for path in work_dir.glob("*"):
                path.unlink(missing_ok=True)
            work_dir.rmdir()

    # Layouts nomeados que o FFmpeg reporta na linha de áudio ("48000 Hz, 5.1, ...").
    _CHANNEL_LAYOUT_COUNTS = {
        "mono": 1, "stereo": 2, "2.1": 3, "3.0": 3, "3.1": 4, "quad": 4, "4.0": 4,
        "5.0": 5, "5.1": 6, "5.1(side)": 6, "6.0": 6, "6.1": 7, "7.0": 7,
        "7.1": 8, "7.1(wide)": 8, "7.1(wide-side)": 8, "octagonal": 8,
    }

    def _probe_media(self, source: Path) -> MediaProfile:
        command = [str(self._ffmpeg()), "-hide_banner", "-i", str(source)]
        self._record_ffmpeg_command(command, probe=True)
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        text = result.stderr + result.stdout
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
            output = self._safe_output(self.output_dir, "audios_juntos", extension)
            list_file = self.output_dir / f"join_audio_{uuid.uuid4().hex}.txt"
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
        output = self._safe_output(self.output_dir, "audios_juntos", extension)
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
        if all(not item.has_video and item.has_audio for item in clips):
            self._join_audio_worker(clips)
            return
        if any(not item.has_video for item in clips):
            raise RuntimeError("Junte somente áudios ou somente vídeos na mesma tarefa")
        join_reencode = bool(self._worker_value("join_reencode", self.join_reencode_var))
        join_smart = bool(self._worker_value("join_smart", self.join_smart_var))
        profile_choice = str(self._worker_value_default("join_profile", "join_profile_var", "Primeiro clipe"))
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
        if force_silence_reencode:
            join_reencode = True
            join_smart = False
            self._append_log("Há clipes com e sem áudio; a saída será reencodada para preencher silêncio sem deslocar a timeline.")
        output = self._safe_output(self.output_dir, "videos_juntos", ".mkv" if preserve_all_streams else ".mp4")
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
            list_file = self.output_dir / f"join_list_{uuid.uuid4().hex}.txt"
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
        if transition_seconds < 0:
            raise RuntimeError("Tempo de transição não pode ser negativo")
        strategy = "Smart Join" if join_smart else "Reencodar"
        transition_label = str(self._worker_value("join_transition", self.join_transition_var))
        if force_silence_reencode:
            transition_seconds = 0.0
            transition_label = "Fundir"
        transition = self.VIDEO_TRANSITION_CODES.get(transition_label, transition_label)
        if preserve_all_streams and not (join_smart and transition_seconds <= 0.001):
            raise RuntimeError(
                "Preservar todas as faixas está disponível somente no join sem transição, porque transições exigem uma política por faixa."
            )
        if strategy == "Smart Join" and transition_seconds <= 0.001:
            self._validate_video_copy_compatibility(clips, require_mp4=not preserve_all_streams, ignore_audio=not copy_audio)
            if preserve_all_streams:
                topology = {((clip.audio_streams if copy_audio else 0), clip.subtitle_streams, clip.data_streams) for clip in clips}
                if len(topology) != 1:
                    raise RuntimeError("Para preservar todas as faixas sem reencode, todos os clipes precisam ter a mesma quantidade de áudio, legendas e dados/anexos.")
            list_file = self.output_dir / f"join_list_{uuid.uuid4().hex}.txt"
            lines = []
            for path in self.join_inputs:
                lines.append(f"file '{self._concat_escape(str(path.resolve()))}'")
            list_file.write_text("\n".join(lines), encoding="utf-8")
            try:
                mapping = self._join_copy_mapping(preserve_all_streams, copy_audio)
                container_args = [] if preserve_all_streams else ["-movflags", "+faststart"]
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
        if strategy == "Smart Join" and transition_seconds > 0.001:
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

    def _smart_join_video_profile(self, media: MediaProfile) -> "smart_join_planner.VideoProfile":
        try:
            fps = float(media.fps) if media.fps else 30.0
        except (TypeError, ValueError):
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
                f"atrim=duration={self._fmt_seconds(duration)},asetpts=N/SR/TB[{output_label}]"
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
        parts.append(
            f"scale={target['width']}:{target['height']}:force_original_aspect_ratio=decrease"
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

        Segue a regra do app Windows (combo de aceleracao do usuario + fallback
        CPU): se o codec do target casar com o encoder selecionado, usa o
        acceleration escolhido; caso contrario, fallback por software do mesmo
        codec (libx264/libx265). O Android escolhe encoder por mediacodec; aqui
        a parametrizacao e a do Windows (qualidade/crf/rate-control).
        """
        accel = getattr(self, "acceleration", None)
        if accel is not None:
            enc = (accel.encoder or "").lower()
            if codec_family == "h264" and enc.startswith(("libx264", "h264_", "mpeg4")):
                return accel
            if codec_family == "hevc" and enc.startswith(("libx265", "hevc_")):
                return accel
        if codec_family == "hevc":
            return VideoAcceleration("cpu", "CPU (HEVC)", "libx265")
        return VideoAcceleration("cpu", "CPU (fallback)", "libx264")

    def _smart_join_video_args(self, codec_family: str, bitrate: str) -> list[str]:
        """Argumentos de encoder do SmartJoin, delegando ao _video_args do Windows.

        Usa o encoder selecionado no combo (se compativel com o codec do target)
        e a QUALIDADE selecionada (via _video_args). Sem parametrizacao do
        Android (mediacodec/-bf/-profile): o app Windows ja resolve isso no
        _video_args por aceleracao.
        """
        accel = self._smart_join_acceleration_for_codec(codec_family)
        return self._video_args(accel, bitrate)

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
    ) -> list[str]:
        args = [str(self._ffmpeg()), "-hide_banner", "-y"]
        if not copy_video:
            # arquivo incompativel pode carregar edit-list/PTS nao continuos
            args += ["-fflags", "+genpts"]
        # O corpo comeca SEMPRE num keyframe (garantia do planner). Usamos
        # -ss DEPOIS do input (output seek) no stream copy: com -ss antes do
        # input + reencode de audio mono, o FFmpeg desktop nao aplica o -t ao
        # audio copiado e a peca TS sai com a duracao cheia (bug observado).
        # Em output seek o corte em keyframe com -c:v copy e exato.
        args += ["-noautorotate", "-display_rotation:v:0", "0", "-i", str(source)]
        if start_seconds > 0.0005:
            args += ["-ss", self._fmt_seconds(start_seconds)]
        args += ["-t", self._fmt_seconds(duration_seconds)]

        filters: list[str] = []
        if not copy_video:
            filters.append(
                f"[0:v:0]{self._smart_join_video_normalization_filter(media, target)}[vout]"
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

        encoder_name: str | None = None
        encoder_args: list[str] = []
        if copy_video:
            args += ["-c:v", "copy"]
        else:
            # Encoder/qualidade do app Windows (_video_args), com o mesmo tail
            # que o join normal usa (fps + pix_fmt) para o TS ficar consistente
            # com os corpos copiados.
            source_bitrate = media.video_bitrate or "1M"
            args += self._smart_join_video_args(target["codec_family"], source_bitrate)
            args += ["-pix_fmt", "yuv420p", "-r", str(target["fps"])]
        if include_audio:
            args += [
                "-c:a", "aac", "-b:a", str(target["audio_bitrate"]),
                "-ar", str(target["audio_rate"]), "-ac", str(target["audio_channels"]),
            ]
        args += ["-map_metadata", "-1", "-avoid_negative_ts", "make_zero"]
        if output_as_mpeg_ts:
            args += [
                "-bsf:v", self._smart_join_ts_bitstream(target["codec_family"]),
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
        if junction.outgoing_bridge_start_seconds > 0.0005:
            args += ["-ss", self._fmt_seconds(junction.outgoing_bridge_start_seconds)]
        args += ["-noautorotate", "-display_rotation:v:0", "0", "-i", str(first_input)]
        args += ["-noautorotate", "-display_rotation:v:0", "0", "-i", str(second_input)]

        nf_first = self._smart_join_video_normalization_filter(first_media, target)
        nf_second = self._smart_join_video_normalization_filter(second_media, target)
        filters = [
            f"[0:v:0]trim=duration={self._fmt_seconds(outgoing_window)},{nf_first}[ovbase]",
            f"[1:v:0]trim=duration={self._fmt_seconds(incoming_window)},{nf_second}[ivbase]",
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
        args += ["-pix_fmt", "yuv420p", "-r", str(target["fps"])]
        if include_audio:
            args += [
                "-c:a", "aac", "-b:a", str(target["audio_bitrate"]),
                "-ar", str(target["audio_rate"]), "-ac", str(target["audio_channels"]),
            ]
        args += [
            "-t", self._fmt_seconds(max(0.01, expected_duration)),
            "-map_metadata", "-1", "-avoid_negative_ts", "make_zero",
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
    ) -> list[str]:
        args = [str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(input_file), "-map", "0:v:0"]
        if include_audio:
            args += ["-map", "0:a?"]
        args += [
            "-c", "copy",
            "-bsf:v", self._smart_join_ts_bitstream(codec_family),
            "-avoid_negative_ts", "make_zero",
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
    ) -> list[str]:
        manifest_path.write_text(
            "\n".join(f"file '{self._concat_escape(str(path.resolve()))}'" for path in pieces),
            encoding="utf-8",
        )
        args = [
            str(self._ffmpeg()), "-hide_banner", "-y",
            "-display_rotation:v:0", str(target.get("rotation") or 0),
            "-fflags", "+genpts",
            "-f", "concat", "-safe", "0", "-i", str(manifest_path),
            "-map", "0:v:0",
        ]
        if include_audio:
            args += ["-map", "0:a?"]
        args += ["-c", "copy"]
        if include_audio:
            args += ["-bsf:a", "aac_adtstoasc"]
        if target["codec_family"] == "hevc":
            args += ["-tag:v", "hvc1"]
        args += [
            "-avoid_negative_ts", "make_zero",
            "-max_interleave_delta", "0",
            "-video_track_timescale", "90000",
            "-movflags", "+faststart",
            str(output_file),
        ]
        return args

    def _smart_join_execute(
        self,
        paths: list[Path],
        medias: list[MediaProfile],
        output: Path,
        transition_seconds: float,
        transition_label: str,
        include_audio: bool,
    ) -> None:
        """Executa o pipeline SmartJoin hibrido (corpos copy + bridges + concat TS).

        Portado integralmente do Android. Levanta RuntimeError sem reencodar
        tudo quando o plano e inviavel (mesma politica do Android).
        """
        fade_in_out = transition_label == "Fade in/out"
        xfade_name = self.VIDEO_TRANSITION_CODES.get(transition_label, transition_label)
        if fade_in_out:
            xfade_name = "fade"

        self._append_log(f"SmartJoin: analisando perfis e keyframes de {len(paths)} clipe(s).")
        sources: list[smart_join_planner.Source] = []
        for index, (path, media) in enumerate(zip(paths, medias)):
            keyframes = self._extract_keyframes(path)
            if self.cancel_event.is_set():
                raise Cancelled()
            sources.append(
                smart_join_planner.Source(
                    duration_seconds=media.duration,
                    profile=self._smart_join_video_profile(media),
                    keyframes_seconds=keyframes,
                )
            )

        plan_result = smart_join_planner.plan(sources, transition_seconds, fade_in_out)
        if not plan_result.can_smart_join:
            raise RuntimeError(plan_result.ineligibility_reason or "SmartJoin não aplicável.")
        if not any(clip.copy_video for clip in plan_result.clips):
            raise RuntimeError(
                "Nenhum corpo de vídeo pôde ser preservado por stream copy: "
                "o SmartJoin recodificaria tudo e não traria ganho."
            )

        copied_count = sum(1 for clip in plan_result.clips if clip.copy_video)
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

        work_dir = self.output_dir / f"smart_join_{uuid.uuid4().hex}"
        work_dir.mkdir(parents=True, exist_ok=True)
        pieces: list[Path] = []
        total_steps = (
            len([c for c in plan_result.clips if c.body_duration_seconds > 0.020])
            + len(plan_result.junctions) * 2
            + 1
        )
        step = 0
        try:
            for index, clip_plan in enumerate(plan_result.clips):
                if self.cancel_event.is_set():
                    raise Cancelled()
                if clip_plan.body_duration_seconds <= 0.020:
                    continue
                step += 1
                ts_path = work_dir / f"body_{index:03d}.ts"
                if clip_plan.copy_video:
                    self._append_log(f"SmartJoin: copiando corpo {index + 1}/{len(paths)} (stream copy).")
                    body_cmd = self._smart_join_body_arguments(
                        paths[index], medias[index],
                        clip_plan.body_start_seconds, clip_plan.body_duration_seconds,
                        copy_video=True, target=target, include_audio=include_audio,
                        output_file=ts_path, output_as_mpeg_ts=True,
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
                        clip_plan.body_start_seconds, clip_plan.body_duration_seconds,
                        copy_video=False, target=target, include_audio=include_audio,
                        output_file=mp4_path, output_as_mpeg_ts=False,
                    )
                    self._execute(
                        body_cmd, f"SmartJoin recodificando clipe {index + 1}", step, total_steps,
                        clip_plan.body_duration_seconds,
                    )
                    step += 1
                    ts_cmd = self._smart_join_ts_arguments(
                        mp4_path, ts_path, target["codec_family"], include_audio
                    )
                    self._execute(
                        ts_cmd, f"SmartJoin preparando corpo {index + 1}", step, total_steps,
                        clip_plan.body_duration_seconds,
                    )
                pieces.append(ts_path)

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
                    target, junction, fade_in_out, xfade_name, include_audio,
                    mp4_path,
                )
                self._execute(
                    bridge_cmd, f"SmartJoin emenda {j + 1}", step, total_steps,
                    max(0.1, smart_join_planner.junction_duration_seconds(junction, fade_in_out)),
                )
                step += 1
                ts_cmd = self._smart_join_ts_arguments(
                    mp4_path, ts_path, target["codec_family"], include_audio
                )
                self._execute(
                    ts_cmd, f"SmartJoin preparando emenda {j + 1}", step, total_steps,
                    max(0.1, smart_join_planner.junction_duration_seconds(junction, fade_in_out)),
                )
                pieces.append(ts_path)

            if not pieces:
                raise RuntimeError("O SmartJoin não gerou segmentos.")
            step += 1
            manifest_path = work_dir / f"manifest_{uuid.uuid4().hex}.txt"
            concat_cmd = self._smart_join_concat_arguments(
                pieces, output, target, include_audio, manifest_path
            )
            expected = plan_result.expected_duration_seconds([m.duration for m in medias])
            self._execute(concat_cmd, "SmartJoin: unindo segmentos", step, total_steps, expected)
            try:
                manifest_path.unlink(missing_ok=True)
            except OSError:
                pass

            # validacao pos (como Android validateSmartJoinDuration)
            actual = self._get_duration_only(output)
            if actual > 0:
                tolerance = max(0.35, len(plan_result.junctions) * 0.12)
                if abs(actual - expected) > tolerance:
                    raise RuntimeError(
                        f"Duração inesperada: {actual:.3f}s; esperado {expected:.3f}s."
                    )
            self._append_log(f"SmartJoin concluído: {expected:.2f}s em {len(pieces)} segmento(s).")
        finally:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

    def _insert_worker(self) -> None:
        main = self.insert_main_input
        inserted = self.insert_secondary_input
        if not main or not main.exists():
            raise RuntimeError("Selecione o áudio principal")
        if not inserted or not inserted.exists():
            raise RuntimeError("Selecione o áudio que será inserido")
        main_profile = self._probe_media(main)
        inserted_profile = self._probe_media(inserted)
        if not main_profile.has_audio or not inserted_profile.has_audio:
            raise RuntimeError("Os dois arquivos precisam conter áudio")
        insertion = max(0.0, min(self.insert_timeline.insertion, main_profile.duration))
        transition_label = str(self._worker_value("insert_transition", self.insert_transition_var))
        transition_code = dict(self.AUDIO_TRANSITIONS).get(transition_label, "none")
        if transition_code == "none":
            transition_seconds = 0.0
        else:
            try:
                transition_seconds = float(str(self._worker_value("insert_seconds", self.insert_seconds_var)).replace(",", "."))
            except ValueError as exc:
                raise RuntimeError("Tempo de transição inválido") from exc
        if transition_seconds < 0:
            raise RuntimeError("Tempo de transição não pode ser negativo")

        full_reencode = bool(self._worker_value("insert_reencode", self.insert_reencode_var))
        use_smart = bool(self._worker_value("insert_smart", self.insert_smart_var))
        extension = main.suffix.lower() if main.suffix.lower() in AUDIO_EXTENSIONS else ".m4a"
        output = self._safe_output(self.output_dir, f"{main.stem}_com_audio", extension)
        total_duration = main_profile.duration + inserted_profile.duration
        if full_reencode and transition_code not in {"none", "fade"} and transition_seconds > 0:
            effective = self._insert_effective_transition(
                main_profile.duration, inserted_profile.duration, insertion, transition_seconds
            )
            boundaries = int(insertion > 0.001) + int(main_profile.duration - insertion > 0.001)
            total_duration = max(0.01, total_duration - effective * boundaries)
        mode = "Reencode Completo" if full_reencode else ("Smart Insert" if use_smart else "Sem reencodar")
        self._set_status(f"Inserindo áudio ({mode})", 0)
        self._append_log(
            f"Inserção: ponto {self._clock(insertion)}, áudio principal {main_profile.audio_rate} Hz/"
            f"{main_profile.audio_channels} canal(is), inserido {inserted_profile.audio_rate} Hz/"
            f"{inserted_profile.audio_channels} canal(is)."
        )
        if full_reencode:
            command = self._insert_full_reencode_arguments(
                main, inserted, output, main_profile, insertion, transition_seconds, transition_code
            )
            self._execute(command, "Inserindo áudio (Reencode Completo)", 1, 1, total_duration)
            return
        if use_smart:
            self._append_log("Smart Insert preserva o corpo do áudio, mas o ponto de corte é aproximado ao frame/pacote do codec.")
            if self._audio_codec_args_for_source_codec(
                main_profile.audio_codec, extension, main_profile.audio_bitrate
            ) is None:
                self._append_log(
                    f"Smart Insert não pode preservar o codec '{main_profile.audio_codec}'; "
                    "usando reencode completo para gerar uma saída válida."
                )
                fallback_transition = transition_code if transition_code != "none" else "none"
                command = self._insert_full_reencode_arguments(
                    main, inserted, output, main_profile, insertion, transition_seconds, fallback_transition
                )
                self._execute(command, "Inserindo áudio (compatibilização completa)", 1, 1, total_duration)
                return
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
        work_dir = self.output_dir / f"insert_copy_{uuid.uuid4().hex}"
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
            for path in work_dir.glob("*"):
                path.unlink(missing_ok=True)
            work_dir.rmdir()

    def _insert_smart_worker(
        self,
        main: Path,
        inserted: Path,
        output: Path,
        profile: MediaProfile,
        insertion: float,
        total_duration: float,
        transition_code: str = "none",
        transition_seconds: float = 0.5,
    ) -> None:
        work_dir = self.output_dir / f"smart_insert_{uuid.uuid4().hex}"
        work_dir.mkdir(parents=True, exist_ok=True)
        extension = output.suffix or ".m4a"
        pieces: list[Path] = []
        try:
            step = 0
            if insertion > 0.001:
                step += 1
                left = work_dir / f"{len(pieces):03d}{extension}"
                self._execute(
                    [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", "0", "-i", str(main), "-t", self._fmt_seconds(insertion), "-map", "0:a:0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(left)],
                    "Smart Insert: trecho inicial",
                    step,
                    4,
                    insertion,
                )
                pieces.append(left)
            step += 1
            middle = work_dir / f"{len(pieces):03d}{extension}"
            inserted_dur = self._get_duration_only(inserted)
            eff_fade = (
                min(transition_seconds, inserted_dur / 2)
                if transition_code != "none" and transition_seconds > 0
                else 0.0
            )

            fade_filters: list[str] = []
            if eff_fade > 0:
                # "Fade in/out" (código "fade") usa a curva padrão do afade; as
                # demais curvas (Linear, Seno, Logarítmica...) são aplicadas
                # com a mesma forma escolhida — sempre apenas no áudio inserido.
                curve = "" if transition_code == "fade" else f":curve={transition_code}"
                fade_filters.append(f"afade=t=in:st=0:d={self._fmt_seconds(eff_fade)}{curve}")
                fade_out_st = max(0.0, inserted_dur - eff_fade)
                fade_filters.append(f"afade=t=out:st={self._fmt_seconds(fade_out_st)}:d={self._fmt_seconds(eff_fade)}{curve}")

            middle_cmd = [
                str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(inserted), "-map", "0:a:0",
                "-ar", str(profile.audio_rate), "-ac", str(profile.audio_channels),
            ]
            if fade_filters:
                middle_cmd += ["-af", ",".join(fade_filters)]

            codec_args = self._audio_codec_args_for_source_codec(
                profile.audio_codec, extension, profile.audio_bitrate
            )
            if codec_args is None:
                raise RuntimeError(
                    f"Smart Insert não consegue preservar com segurança o codec '{profile.audio_codec}'. "
                    "Use Reencode Completo."
                )
            middle_cmd += codec_args
            middle_cmd.append(str(middle))

            self._execute(
                middle_cmd,
                "Smart Insert: compatibilizando áudio inserido",
                step,
                4,
                inserted_dur,
            )
            pieces.append(middle)
            main_duration = self._get_duration_only(main)
            if insertion < main_duration - 0.001:
                step += 1
                right = work_dir / f"{len(pieces):03d}{extension}"
                self._execute(
                    [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", self._fmt_seconds(insertion), "-i", str(main), "-map", "0:a:0", "-c", "copy", str(right)],
                    "Smart Insert: trecho final",
                    step,
                    4,
                    max(0.1, main_duration - insertion),
                )
                pieces.append(right)
            self._concat_insert_pieces(pieces, output, "Smart Insert: juntando áudio", 4, 4, total_duration)
        finally:
            for path in work_dir.glob("*"):
                path.unlink(missing_ok=True)
            work_dir.rmdir()

    def _concat_insert_pieces(self, pieces: list[Path], output: Path, label: str, progress: int, total: int, duration: float) -> None:
        if not pieces:
            raise RuntimeError("Nenhum trecho foi criado para a inserção")
        list_file = output.parent / f"{output.stem}_pieces_{uuid.uuid4().hex}.txt"
        list_file.write_text(
            "\n".join(f"file '{self._concat_escape(str(piece.resolve()))}'" for piece in pieces),
            encoding="utf-8",
        )
        try:
            concat_cmd = [str(self._ffmpeg()), "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy"]
            if output.suffix.lower() == ".m4a":
                concat_cmd += ["-movflags", "+faststart"]
            concat_cmd += ["-avoid_negative_ts", "make_zero", str(output)]
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
        self,
        main: Path,
        inserted: Path,
        output: Path,
        profile: MediaProfile,
        insertion: float,
        transition_seconds: float,
        transition_code: str,
        log_adjustment: bool = True,
    ) -> list[str]:
        main_end = profile.duration
        inserted_duration = self._get_duration_only(inserted)
        neighbors = [inserted_duration]
        if insertion > 0:
            neighbors.append(insertion)
        if main_end > insertion:
            neighbors.append(main_end - insertion)
        effective = min(transition_seconds, max(0.0, min(neighbors) / 2 if neighbors else 0.0))
        if log_adjustment and effective + 0.001 < transition_seconds:
            self._append_log(
                f"Tempo de transição ajustado de {transition_seconds:.2f}s para {effective:.2f}s para caber nos trechos."
            )
        has_left = insertion > 0.001
        has_right = main_end - insertion > 0.001
        use_fade = transition_code == "fade" and effective > 0
        use_crossfade = transition_code not in {"none", "fade"} and effective > 0
        layout = profile.audio_layout
        normalize = f"aresample={profile.audio_rate},aformat=sample_fmts=fltp:sample_rates={profile.audio_rate}:channel_layouts={layout}"
        filters: list[str] = []
        labels: list[str] = []
        if has_left:
            fade_out = f",afade=t=out:st={self._fmt_seconds(max(0.0, insertion - effective))}:d={self._fmt_seconds(effective)}" if use_fade else ""
            filters.append(f"[0:a]atrim=start=0:end={self._fmt_seconds(insertion)},{normalize},asetpts=PTS-STARTPTS{fade_out}[a0]")
            labels.append("a0")
        inserted_fades = ""
        if use_fade and has_left:
            inserted_fades += f",afade=t=in:st=0:d={self._fmt_seconds(effective)}"
        if use_fade and has_right:
            inserted_fades += f",afade=t=out:st={self._fmt_seconds(max(0.0, inserted_duration - effective))}:d={self._fmt_seconds(effective)}"
        filters.append(f"[1:a]atrim=start=0:end={self._fmt_seconds(inserted_duration)},{normalize},asetpts=PTS-STARTPTS{inserted_fades}[a1]")
        labels.append("a1")
        if has_right:
            fade_in = f",afade=t=in:st=0:d={self._fmt_seconds(effective)}" if use_fade else ""
            filters.append(f"[0:a]atrim=start={self._fmt_seconds(insertion)}:end={self._fmt_seconds(main_end)},{normalize},asetpts=PTS-STARTPTS{fade_in}[a2]")
            labels.append("a2")
        if use_crossfade and len(labels) > 1:
            previous = labels[0]
            for index in range(1, len(labels)):
                output_label = f"ax{index}"
                filters.append(f"[{previous}][{labels[index]}]acrossfade=d={self._fmt_seconds(effective)}:c1={transition_code}:c2={transition_code}[{output_label}]")
                previous = output_label
            filters.append(f"[{previous}]anull[aout]")
        else:
            filters.append("".join(f"[{label}]" for label in labels) + f"concat=n={len(labels)}:v=0:a=1[aout]")
        ext = output.suffix.lower().lstrip(".")
        codec_args = self._audio_codec_args(ext, profile.audio_bitrate)
        return [
            str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(main), "-i", str(inserted),
            "-filter_complex", ";".join(filters), "-map", "[aout]", "-vn",
            "-ar", str(profile.audio_rate), "-ac", str(profile.audio_channels),
            *codec_args, "-map_metadata", "0", str(output),
        ]

    def _clean_worker(self) -> None:
        source = self.clean_input
        if not source or not source.exists():
            raise RuntimeError("Selecione o áudio para limpar")
        media = self._probe_media(source)
        if not media.has_audio:
            raise RuntimeError("O arquivo selecionado não possui trilha de áudio.")
        clean_mode = str(self._worker_value("clean_mode", self.clean_mode_var))
        filter_value = "afftdn=nf=-25" if clean_mode == "equilibrado" else "afftdn=nr=18:nf=-35:tn=1"
        output_profile = str(self._worker_value_default(
            "clean_output_profile", "clean_output_profile_var", "Transcrição (mono, 16 kHz)"
        ))
        output = self._safe_output(self.output_dir, f"{source.stem}_limpo", ".wav")
        format_args = ["-ar", "16000", "-ac", "1"] if output_profile.startswith("Transcrição") else ["-ar", str(media.audio_rate), "-ac", str(media.audio_channels)]
        command = [str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(source), "-vn", "-map", "0:a:0", "-af", filter_value, "-c:a", "pcm_s16le", *format_args, "-f", "wav", str(output)]
        self._execute(command, "Limpando áudio", 1, 1, media.duration)
