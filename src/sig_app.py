import base64
import concurrent.futures
import ctypes
import hashlib
import importlib
from datetime import date, datetime
from array import array
from collections import deque
import html
import http.client
import json
import math
import mimetypes
import os
import queue
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
import wave
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import BOTH, BOTTOM, END, LEFT, RIGHT, TOP, X, Y, BooleanVar, Button, Canvas, IntVar, PhotoImage, StringVar, Text, Tk, Toplevel
from tkinter import filedialog, messagebox, ttk
from urllib.parse import quote, urlencode, urlparse

from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageTk
import pypdfium2 as pdfium

from assistant_prompts import (
    DEFAULT_HISTORY_SYSTEM_PROMPT,
    DEFAULT_PARTS_PROMPT,
    DEFAULT_QUALIFICATION_SYSTEM_PROMPT,
    history_user_prompt,
    parts_user_prompt_from_history,
    parts_user_prompt_from_transcription,
    qualification_user_prompt,
    statement_prompt,
    statement_user_prompt,
)
import stt_provider_rules
from stt_provider_rules import (
    assemblyai_rest_diarize,
    assemblyai_rest_language,
    assemblyai_ws_diarize_query,
    assemblyai_ws_language_codes,
    codes_for_help,
    deepgram_diarize_query,
    deepgram_language_param,
    elevenlabs_rest_diarize,
    elevenlabs_rest_language_code,
    elevenlabs_ws_diarize_query,
    elevenlabs_ws_language,
    grok_diarize_query,
    grok_language_param,
    grok_rest_diarize,
    invalid_codes,
    language_custom,
    language_mode,
    MENU_OPTIONS,
    parse_codes,
    supports_diarize,
)
from sync_common import (
    SYNC_MANIFEST_FILE_ID,
    UPDATE_PUBLIC_KEY_E,
    UPDATE_PUBLIC_KEY_N,
    SyncError,
    classify_sync_files,
    validate_sync_manifest,
)


APP_NAME = "sig"
APP_VERSION = "20260817_001"
UPDATE_MANIFEST_FILE_ID = "1Gompo26SsyhSdliBGNaedLhEfidB244E"
UPDATE_DOWNLOAD_URL = "https://drive.usercontent.google.com/download"
SUPPORTED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".ogg",
    ".opus",
    ".flac",
    ".aac",
    ".wma",
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
AUDIO_EXTENSIONS = SUPPORTED_EXTENSIONS - VIDEO_EXTENSIONS
VIDEO_QUALITY_LEVELS = ("Máxima", "Muito alta", "Alta", "Média", "Econômica")
VIDEO_QUALITY_MENU_LABELS = {
    "Máxima": "Máxima",
    "Muito alta": "Muito alta",
    "Alta": "Alta (Recomendado)",
    "Média": "Média",
    "Econômica": "Econômica",
}
# API keys are supplied by the user in Settings and are never shipped in source.
IMEI_API_KEY = ""
DEFAULT_SETTINGS = {
    "convert_parallel": 8,
    "transcribe_parallel": 16,
    "grok_chunk_ms": 100,
    "grok_rest_requests": False,
    "transcription_server": "avare",
    "transcription_server_2": "",
    "text_model": "IA-Proxy",
    "text_model_2": "",
    "text_reasoning": "low",
    "text_reasoning_2": "low",
    "ia_proxy_model": "grok-4.6",
    "ia_proxy_model_2": "grok-4.6",
    "ia_proxy_provider": "grok",
    "ia_proxy_provider_2": "grok",
    "history_model": "IA-Proxy",
    "history_model_2": "",
    "history_reasoning": "low",
    "history_reasoning_2": "low",
    "history_proxy_model": "grok-4.6",
    "history_proxy_model_2": "grok-4.6",
    "statement_model": "IA-Proxy",
    "statement_model_2": "",
    "statement_reasoning": "low",
    "statement_reasoning_2": "low",
    "statement_proxy_model": "grok-4.6",
    "statement_proxy_model_2": "grok-4.6",
    "parts_extraction": "uppercase",
    "parts_model": "IA-Proxy",
    "parts_proxy_model": "grok-4.6",
    "parts_proxy_provider": "grok",
    "parts_reasoning": "low",
    "qualification_model": "IA-Proxy",
    "qualification_reasoning": "low",
    "qualification_proxy_model": "grok-4.6",
    "grok_api_key": "",
    "deepseek_api_key": "",
    "deepgram_api_key": "",
    "deepgram_keyterms": "",
    "assemblyai_api_key": "",
    "elevenlabs_api_key": "",
    "deepgram_language_mode": "pt-BR",
    "deepgram_language_custom": "",
    "assemblyai_language_mode": "pt",
    "assemblyai_language_custom": "",
    "elevenlabs_language_mode": "pt",
    "elevenlabs_language_custom": "",
    "grok_language_mode": "pt",
    "grok_language_custom": "",
    "imei_api_key": IMEI_API_KEY,
    "police_name": "",
    "police_role": "",
    "police_station": "",
    "police_delegate": "",
    "police_city": "",
}
GROK_API_NAME = "Grok STT"
GROK_STT_URL = "https://api.x.ai/v1/stt"
GROK_STT_WEBSOCKET_URL = "wss://api.x.ai/v1/stt"
DEEPGRAM_API_NAME = "Deepgram Nova 3"
DEEPGRAM_STT_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_STT_WEBSOCKET_URL = "wss://api.deepgram.com/v1/listen"
ASSEMBLYAI_API_NAME = "AssemblyAI Universal-3.5 Pro"
ASSEMBLYAI_SYNC_URL = "https://sync.assemblyai.com/transcribe"
ASSEMBLYAI_WEBSOCKET_URL = "wss://streaming.assemblyai.com/v3/ws"
ELEVENLABS_API_NAME = "ElevenLabs Scribe v2 Realtime"
ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_WEBSOCKET_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
LIVE_LANGUAGES = (("pt", "Português"), ("en", "Inglês"), ("es", "Espanhol"))
LIVE_QUALIFICATION_FIELD_IDS = (
    "nome",
    "rg",
    "cpf",
    "nascimento",
    "naturalidade",
    "profissao",
    "pai",
    "mae",
    "endereco",
    "bairro",
    "cidade",
    "telefone",
)

GROK_TEXT_URL = "https://api.x.ai/v1/responses"
DEEPSEEK_TEXT_URL = "https://api.deepseek.com/chat/completions"
GROK_TEXT_NAME = "grok-4.6"
GROK_NON_REASONING_TEXT_NAME = "grok-4.20-0309-non-reasoning"
GROK_NON_REASONING_LEGACY_NAME = "grok-4.20-non-reasoning"
DEEPSEEK_TEXT_NAME = "deepseek-v4-flash"
IA_PROXY_NAME = "IA-Proxy"
IA_PROXY_PRIMARY_URL = "http://servidor:8500"
IA_PROXY_FALLBACK_URL = "http://avare:8500"
GROK_TEXT_API_NAMES = {GROK_TEXT_NAME, GROK_NON_REASONING_TEXT_NAME}
DEEPSEEK_API_NAMES = {DEEPSEEK_TEXT_NAME}
DEFAULT_TRANSCRIPTION_SERVER_CONTENT = (
    '*avare\t\t'
    'http://avare:8100\t\t'
    '"model": "granite-speech-4.1-2b-plus-ar"\n'
    'servidor\t\t'
    'http://servidor:8100\t\t'
    '"model": "granite-speech-4.1-2b-nar"\n'
)
TAGUAI_TRANSCRIPTION_SERVER_CONTENT = (
    'servidor\t\t'
    'http://servidor:8100\t\t'
    '"model": "granite-speech-4.1-2b-nar"'
)
TRANSCRIPTION_SERVER_MIGRATION_MARKER = "#sig:taguai-speech-v1"
AVARE_PLUS_AR_MIGRATION_MARKER = "#sig:avare-plus-ar-v1"
TEXT_MODEL_CONFIGS = {}
DEFAULT_TEXT_MODEL_SERVER_CONTENT = ""
PARTS_EXTRACTION_LABELS = {
    "uppercase": "Palavras em maiúsculas",
    "name_database": "Base de nomes",
    "ai": "IA",
}
LIVE_SAMPLE_RATE = 16000
LIVE_CHANNELS = 1
LIVE_SAMPLE_WIDTH = 2
LIVE_FINAL_CHUNK_MILLIS = 30000
DEFAULT_LIVE_DRAFT_INTERVAL_MILLIS = 1000
MIN_LIVE_DRAFT_INTERVAL_MILLIS = 100
MAX_LIVE_DRAFT_INTERVAL_MILLIS = 10000
LIVE_INTERVAL_VALUES_MS = (
    100, 200, 300, 400, 500, 600, 700, 800, 900,
    1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000,
    15000, 20000, 25000, 30000,
)
GROK_RECONNECT_MAX_ATTEMPTS = 8
GROK_RECONNECT_BUFFER_MILLIS = 8000
IMEI_HISTORY_FILE = "imei_history.txt"
IMEI_HISTORY_COLLAPSED_LIMIT = 10
MIME_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".zip": "application/zip",
}


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


def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def is_transcription_ready_wav(path: Path) -> bool:
    """Retorna se o WAV já atende ao formato exigido pelo servidor."""
    if path.suffix.lower() != ".wav":
        return False
    try:
        with wave.open(str(path), "rb") as source:
            return (
                source.getcomptype() == "NONE"
                and source.getnchannels() == 1
                and source.getframerate() == 16000
                and source.getsampwidth() == 2
            )
    except (wave.Error, OSError, EOFError):
        return False


class Cancelled(Exception):
    pass


@dataclass
class AudioJob:
    original_path: Path
    original_name: str
    stem: str
    mode: str
    upload_path: Path | None = None
    converted_path: Path | None = None
    txt_path: Path | None = None
    txt_path_2: Path | None = None
    raw_path: Path | None = None
    raw_path_2: Path | None = None
    log_path: Path | None = None
    vad_output_path: Path | None = None
    vad_input_bytes: int = 0
    vad_output_bytes: int = 0
    vad_elapsed: float = 0.0
    vad_speech_duration: float = 0.0
    vad_total_duration: float = 0.0
    vad_error: str = ""
    conversion_elapsed: float = 0.0
    status: str = "Aguardando"
    transcription: str = ""
    transcription_2: str = ""
    error: str = ""
    error_2: str = ""
    model_name: str = "Modelo 1"
    model_name_2: str = ""


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parents[1] / relative


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        # Uma atualização antiga pode ter deixado o executável dentro de uma
        # subpasta (por exemplo, dist/g). O diretório principal é identificado
        # pelos recursos que o SIG precisa para funcionar.
        runtime_markers = ("ffmpeg.exe", "ffplay.exe", "vad_deps")
        for candidate in (executable_dir, *executable_dir.parents[:4]):
            if any((candidate / marker).exists() for marker in runtime_markers):
                return candidate
        return executable_dir
    return Path(__file__).resolve().parents[1]


DOCUMENT_TEMPLATE_NAMES = {
    "declarations": "modelo_declaracoes.docx",
    "deposition": "modelo_depoimento.docx",
}


def build_cf_html(html_text: str | bytes) -> bytes:
    """Build a Windows CF_HTML payload using UTF-8 byte offsets."""
    if isinstance(html_text, bytes):
        source_bytes = html_text.rstrip(b"\x00")
        charset_match = re.search(
            br"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)",
            source_bytes[:4096],
            flags=re.IGNORECASE,
        )
        source_encoding = (
            charset_match.group(1).decode("ascii", errors="replace")
            if charset_match
            else "utf-8"
        )
        try:
            raw_html = source_bytes.decode(source_encoding)
        except (LookupError, UnicodeDecodeError):
            raw_html = source_bytes.decode("utf-8", errors="replace")
    else:
        raw_html = html_text or ""
    raw_html = raw_html.replace("\x00", "").lstrip("\ufeff")
    html_start = raw_html.lower().find("<html")
    if html_start >= 0:
        raw_html = raw_html[html_start:]
    elif not raw_html.strip():
        raise RuntimeError("O Word não forneceu o conteúdo no formato HTML.")
    else:
        raw_html = f"<html><body>{raw_html}</body></html>"
    raw_html = re.sub(
        r"(charset\s*=\s*[\"']?)[A-Za-z0-9._-]+",
        r"\1utf-8",
        raw_html,
        count=1,
        flags=re.IGNORECASE,
    )

    start_marker = "<!--StartFragment-->"
    end_marker = "<!--EndFragment-->"
    if start_marker not in raw_html:
        body_match = re.search(r"<body\b[^>]*>", raw_html, flags=re.IGNORECASE)
        marker_at = body_match.end() if body_match else 0
        raw_html = raw_html[:marker_at] + start_marker + raw_html[marker_at:]
    if end_marker not in raw_html:
        body_end = raw_html.lower().rfind("</body>")
        marker_at = body_end if body_end >= 0 else len(raw_html)
        raw_html = raw_html[:marker_at] + end_marker + raw_html[marker_at:]

    html_bytes = raw_html.encode("utf-8")
    start_marker_bytes = start_marker.encode("ascii")
    end_marker_bytes = end_marker.encode("ascii")
    fragment_start_in_html = html_bytes.index(start_marker_bytes) + len(start_marker_bytes)
    fragment_end_in_html = html_bytes.index(end_marker_bytes, fragment_start_in_html)

    header_template = (
        "Version:1.0\r\n"
        "StartHTML:{start_html:010d}\r\n"
        "EndHTML:{end_html:010d}\r\n"
        "StartFragment:{start_fragment:010d}\r\n"
        "EndFragment:{end_fragment:010d}\r\n"
    )
    placeholder_header = header_template.format(
        start_html=0,
        end_html=0,
        start_fragment=0,
        end_fragment=0,
    ).encode("ascii")
    start_html = len(placeholder_header)
    end_html = start_html + len(html_bytes)
    header = header_template.format(
        start_html=start_html,
        end_html=end_html,
        start_fragment=start_html + fragment_start_in_html,
        end_fragment=start_html + fragment_end_in_html,
    ).encode("ascii")
    return header + html_bytes


def set_windows_document_clipboard(
    rtf: bytes,
    html_text: str | bytes,
    plain_text: str,
) -> None:
    if os.name != "nt":
        raise RuntimeError("A cópia formatada está disponível somente no Windows.")
    if not rtf:
        raise RuntimeError("O Word não forneceu o conteúdo no formato RTF.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.CloseClipboard.restype = ctypes.c_bool
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.RegisterClipboardFormatW.argtypes = [ctypes.c_wchar_p]
    user32.RegisterClipboardFormatW.restype = ctypes.c_uint
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p

    for _attempt in range(40):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.1)
    else:
        raise ctypes.WinError(ctypes.get_last_error())

    def put(format_id: int, data: bytes) -> None:
        memory = kernel32.GlobalAlloc(0x0002, len(data))
        if not memory:
            raise ctypes.WinError(ctypes.get_last_error())
        target = kernel32.GlobalLock(memory)
        if not target:
            kernel32.GlobalFree(memory)
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.memmove(target, data, len(data))
        kernel32.GlobalUnlock(memory)
        if not user32.SetClipboardData(format_id, memory):
            kernel32.GlobalFree(memory)
            raise ctypes.WinError(ctypes.get_last_error())

    try:
        if not user32.EmptyClipboard():
            raise ctypes.WinError(ctypes.get_last_error())
        rtf_format = user32.RegisterClipboardFormatW("Rich Text Format")
        html_format = user32.RegisterClipboardFormatW("HTML Format")
        put(rtf_format, rtf.rstrip(b"\0") + b"\0")
        put(html_format, build_cf_html(html_text) + b"\0")
        put(13, plain_text.encode("utf-16-le") + b"\0\0")
    finally:
        user32.CloseClipboard()


def export_docx_to_pdf_with_word(document_path: Path, output_path: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("A exportação fiel para PDF está disponível somente no Windows.")
    document_path = Path(document_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    script = r"""
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
$doNotSaveChanges = 0
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($env:SIG_PDF_SOURCE, $false, $true)
    $document.ExportAsFixedFormat($env:SIG_PDF_OUTPUT, 17)
    $document.Close([ref]$doNotSaveChanges)
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    $document = $null
    $word.Quit([ref]$doNotSaveChanges)
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
    $word = $null
} finally {
    if ($null -ne $document) {
        try { $document.Close([ref]$doNotSaveChanges) } catch {}
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) } catch {}
    }
    if ($null -ne $word) {
        try { $word.Quit([ref]$doNotSaveChanges) } catch {}
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) } catch {}
    }
}
"""
    env = os.environ.copy()
    env.update(
        {
            "SIG_PDF_SOURCE": str(document_path),
            "SIG_PDF_OUTPUT": str(output_path),
        }
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Sta", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "falha desconhecida").strip()
        raise RuntimeError(detail)
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError("O Word não gerou o arquivo PDF.")


def _crop_preview_page_to_content(
    page: Image.Image,
    *,
    horizontal_padding: int = 4,
    vertical_padding: int = 14,
) -> Image.Image:
    """Crop printable whitespace while retaining a small reading margin."""
    white = Image.new("RGB", page.size, (255, 255, 255))
    difference = ImageChops.difference(page, white).convert("L")
    # Ignore PDF rasterization noise in the white page background, but retain
    # antialiased text and thin document lines.
    mask = difference.point(lambda value: 255 if value > 8 else 0)
    bounds = mask.getbbox()
    mask.close()
    difference.close()
    white.close()
    cropped = page if not bounds else page.crop(bounds)
    if cropped is not page:
        page.close()
    # Keep roughly one blank text line above and below each page.  The
    # horizontal padding stays intentionally small because the old preview
    # left too much empty space beside the document.
    padded = ImageOps.expand(
        cropped,
        border=(max(0, horizontal_padding), max(0, vertical_padding)),
        fill="#ffffff",
    )
    if padded is not cropped:
        cropped.close()
    return padded


def _window_physical_dpi(root) -> int:
    """DPI físico (painel) do monitor que contém a janela principal.

    O Windows virtualiza o DPI em 96 para processos não-DPI-aware, mas o
    painel real do monitor tem outro valor (ex.: 102 PPI em 21,5" Full HD).
    Para o zoom de 100% da prévia mostrar o documento no tamanho físico de
    impressão, a renderização precisa usar o DPI real do painel — medido
    diretamente via GetDpiForMonitor(MDT_RAW_DPI), que não é virtualizado.
    """
    if os.name != "nt":
        return 96
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        shcore = ctypes.windll.shcore
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        dpi_x = wintypes.UINT()
        dpi_y = wintypes.UINT()
        # MDT_RAW_DPI = 2: valor físico real do painel, ignorando a
        # virtualização de DPI do sistema.
        if shcore.GetDpiForMonitor(monitor, 2, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
            if dpi_x.value:
                return int(dpi_x.value)
    except Exception:
        pass
    return 96


def render_pdf_preview(
    pdf_path: Path,
    output_path: Path,
    zoom_percent: int,
    dpi: int = 96,
) -> tuple[int, list[tuple[int, int]]]:
    """Render pages and return their vertical ranges in the preview image."""
    zoom = max(25, min(200, int(zoom_percent)))
    document = pdfium.PdfDocument(str(Path(pdf_path).resolve()))
    pages: list[Image.Image] = []
    try:
        # Com o DPI físico do painel, 100% corresponde ao tamanho real de
        # impressão: um texto de 15,1 cm no papel ocupa 15,1 cm na tela.
        scale = (dpi / 72) * (zoom / 100)
        for page_index in range(len(document)):
            page = document[page_index]
            bitmap = None
            try:
                bitmap = page.render(scale=scale)
                rendered_page = bitmap.to_pil().convert("RGB").copy()
                pages.append(
                    _crop_preview_page_to_content(
                        rendered_page,
                        # Keep only about 0.2 cm of white breathing room at
                        # 100% (the preview is calibrated to physical size).
                        horizontal_padding=max(2, round(2 * zoom / 100)),
                        vertical_padding=max(2, round(2 * zoom / 100)),
                    )
                )
            finally:
                if bitmap is not None:
                    bitmap.close()
                page.close()
    finally:
        document.close()
    if not pages:
        raise RuntimeError("O PDF não contém páginas para visualizar.")
    # Keep only the rendered document in the preview image. The page's blank
    # printable margin is removed per page before this composite is built.
    # A separação entre páginas ganha respiro: duas linhas em branco antes e
    # duas depois do traço central, para evidenciar a divisão das páginas.
    line_spacing = max(4, round(16 * (dpi / 96) * (zoom / 100)))
    separator_height = line_spacing * 4 + 1
    width = max(page.width for page in pages)
    height = sum(page.height for page in pages) + separator_height * (len(pages) - 1)
    preview = Image.new("RGB", (width, height), "#ffffff")
    separator_draw = ImageDraw.Draw(preview)
    page_regions: list[tuple[int, int]] = []
    y = 0
    for page_index, page in enumerate(pages):
        x = 0
        page_start = y
        preview.paste(page, (x, y))
        y += page.height
        page_regions.append((page_start, y))
        if page_index < len(pages) - 1:
            y += line_spacing * 2
            separator_draw.line(
                (0, y, width - 1, y),
                fill="#aeb8b5",
                width=1,
            )
            y += 1 + line_spacing * 2
        page.close()
    del separator_draw
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    preview.save(output_path, format="PNG", optimize=True)
    preview.close()
    return len(pages), page_regions


PORTUGUESE_MONTHS = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)
PORTUGUESE_CARDINALS = {
    0: "zero", 1: "um", 2: "dois", 3: "três", 4: "quatro",
    5: "cinco", 6: "seis", 7: "sete", 8: "oito", 9: "nove",
    10: "dez", 11: "onze", 12: "doze", 13: "treze", 14: "quatorze",
    15: "quinze", 16: "dezesseis", 17: "dezessete", 18: "dezoito",
    19: "dezenove", 20: "vinte", 30: "trinta", 40: "quarenta",
    50: "cinquenta", 60: "sessenta", 70: "setenta", 80: "oitenta",
    90: "noventa", 100: "cem", 200: "duzentos", 300: "trezentos",
    400: "quatrocentos", 500: "quinhentos", 600: "seiscentos",
    700: "setecentos", 800: "oitocentos", 900: "novecentos",
    1000: "mil", 2000: "dois mil",
}


def portuguese_number_words(value: int) -> str:
    value = int(value)
    if value in PORTUGUESE_CARDINALS:
        return PORTUGUESE_CARDINALS[value]
    if not 0 <= value <= 9999:
        return str(value)
    if value >= 1000:
        thousands, remainder = divmod(value, 1000)
        prefix = "mil" if thousands == 1 else f"{portuguese_number_words(thousands)} mil"
        return prefix if remainder == 0 else f"{prefix} e {portuguese_number_words(remainder)}"
    if value > 100:
        hundreds, remainder = divmod(value, 100)
        prefix = "cento" if hundreds == 1 else PORTUGUESE_CARDINALS[hundreds * 100]
        return prefix if remainder == 0 else f"{prefix} e {portuguese_number_words(remainder)}"
    tens, remainder = divmod(value, 10)
    prefix = PORTUGUESE_CARDINALS[tens * 10]
    return prefix if remainder == 0 else f"{prefix} e {PORTUGUESE_CARDINALS[remainder]}"


WORD_PARAGRAPH_RE = re.compile(r"<w:p(?:\s[^>]*)?>.*?</w:p>", re.DOTALL)
WORD_TEXT_RE = re.compile(r"(<w:t(?:\s[^>]*)?>)(.*?)(</w:t>)", re.DOTALL)
WORD_FLOW_BREAK_RE = re.compile(
    r"<w:(?:br|cr|tab|lastRenderedPageBreak)\b",
    re.IGNORECASE,
)


def _replace_word_paragraph_markers(
    paragraph_xml: str,
    replacements: dict[str, str],
) -> tuple[str, int]:
    matches = list(WORD_TEXT_RE.finditer(paragraph_xml))
    if not matches:
        return paragraph_xml, 0
    text_values = [html.unescape(match.group(2)) for match in matches]
    aliases = []
    for marker, replacement in replacements.items():
        aliases.extend(
            (
                (f"{{{{{marker}}}}}", replacement),
                (f"{{{{{{{marker}}}}}}}", replacement),
            )
        )
    aliases.sort(key=lambda item: len(item[0]), reverse=True)
    changed = 0
    while True:
        joined = "".join(text_values)
        match = None
        for marker, replacement in aliases:
            offset = joined.find(marker)
            if offset >= 0 and (match is None or offset > match[0]):
                match = (offset, marker, str(replacement or ""))
        if match is None:
            break
        start, marker, replacement = match
        end = start + len(marker)
        spans = []
        cursor = 0
        for node_text in text_values:
            spans.append((cursor, cursor + len(node_text)))
            cursor += len(node_text)
        first_index = next(
            index for index, (node_start, node_end) in enumerate(spans)
            if node_start <= start < node_end
        )
        last_position = max(start, end - 1)
        last_index = next(
            index for index, (node_start, node_end) in enumerate(spans)
            if node_start <= last_position < node_end
        )
        first_start, _first_end = spans[first_index]
        last_start, _last_end = spans[last_index]
        prefix = text_values[first_index][: start - first_start]
        suffix = text_values[last_index][end - last_start :]
        preceding_character = joined[start - 1 : start] if start else ""
        following_character = joined[end : end + 1]
        preceding_is_adjacent = True
        if preceding_character and start == first_start:
            previous_index = next(
                (
                    index
                    for index in range(first_index - 1, -1, -1)
                    if text_values[index]
                ),
                None,
            )
            if previous_index is not None:
                bridge = paragraph_xml[
                    matches[previous_index].end() : matches[first_index].start()
                ]
                preceding_is_adjacent = not WORD_FLOW_BREAK_RE.search(bridge)
        following_is_adjacent = True
        if following_character and end - last_start == len(text_values[last_index]):
            next_index = next(
                (
                    index
                    for index in range(last_index + 1, len(text_values))
                    if text_values[index]
                ),
                None,
            )
            if next_index is not None:
                bridge = paragraph_xml[
                    matches[last_index].end() : matches[next_index].start()
                ]
                following_is_adjacent = not WORD_FLOW_BREAK_RE.search(bridge)
        if (
            preceding_is_adjacent
            and preceding_character.isalnum()
            and replacement[:1].isalnum()
        ):
            replacement = " " + replacement
        if (
            following_is_adjacent
            and replacement[-1:].isalnum()
            and following_character.isalnum()
        ):
            replacement += " "
        if first_index == last_index:
            text_values[first_index] = prefix + replacement + suffix
        else:
            text_values[first_index] = prefix + replacement
            for index in range(first_index + 1, last_index):
                text_values[index] = ""
            text_values[last_index] = suffix
        changed += 1
    if changed == 0:
        return paragraph_xml, 0
    pieces = []
    previous_end = 0
    for match, value in zip(matches, text_values):
        pieces.append(paragraph_xml[previous_end:match.start()])
        opening_tag = match.group(1)
        if (value[:1].isspace() or value[-1:].isspace()) and "xml:space=" not in opening_tag:
            opening_tag = opening_tag[:-1] + ' xml:space="preserve">'
        pieces.append(opening_tag)
        pieces.append(html.escape(value, quote=False))
        pieces.append(match.group(3))
        previous_end = match.end()
    pieces.append(paragraph_xml[previous_end:])
    return "".join(pieces), changed


def generate_docx_from_template(
    template_path: Path,
    output_path: Path,
    replacements: dict[str, str],
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_changes = 0
    unresolved: list[str] = []
    with zipfile.ZipFile(template_path, "r") as source:
        with zipfile.ZipFile(output_path, "w") as destination:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                    try:
                        xml_text = data.decode("utf-8")
                    except UnicodeDecodeError:
                        xml_text = ""
                    if xml_text and "<w:t" in xml_text:
                        changes = 0

                        def replace_paragraph(match):
                            nonlocal changes
                            updated, count = _replace_word_paragraph_markers(
                                match.group(0),
                                replacements,
                            )
                            changes += count
                            return updated

                        xml_text = WORD_PARAGRAPH_RE.sub(replace_paragraph, xml_text)
                        if changes:
                            data = xml_text.encode("utf-8")
                            total_changes += changes
                        remaining_text = "".join(
                            html.unescape(match.group(2))
                            for match in WORD_TEXT_RE.finditer(xml_text)
                        )
                        unresolved.extend(
                            marker
                            for marker in re.findall(r"\{\{\{?[^{}]+\}\}\}?", remaining_text)
                            if marker not in unresolved
                        )
                destination.writestr(item, data)
    if unresolved:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("Marcadores sem valor no modelo: " + ", ".join(unresolved))
    if total_changes == 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("O modelo não contém marcadores reconhecidos.")
    return total_changes


def ensure_document_templates() -> dict[str, Path]:
    external_dir = app_base_dir() / "modelos"
    external_dir.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, Path] = {}
    for template_kind, filename in DOCUMENT_TEMPLATE_NAMES.items():
        external_path = external_dir / filename
        bundled_path = resource_path(f"modelos/{filename}")
        if not external_path.exists() and bundled_path.exists():
            shutil.copy2(bundled_path, external_path)
        if not external_path.exists():
            raise FileNotFoundError(f"Modelo não encontrado: {external_path}")
        resolved[template_kind] = external_path
    return resolved


def project_root() -> Path:
    """Raiz do projeto — contém assets/, dist/, src/, sig.spec."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parents[1]


def google_drive_download_url(file_id: str) -> str:
    return f"{UPDATE_DOWNLOAD_URL}?{urlencode({'id': file_id, 'export': 'download', 'confirm': 't'})}"


def canonical_update_manifest(manifest: dict) -> bytes:
    signed_payload = {
        "schema": int(manifest.get("schema") or 0),
        "version": str(manifest.get("version") or ""),
        "zip_file_id": str(manifest.get("zip_file_id") or ""),
        "zip_name": str(manifest.get("zip_name") or ""),
        "sha256": str(manifest.get("sha256") or "").lower(),
        "size": int(manifest.get("size") or 0),
        "created_at": str(manifest.get("created_at") or ""),
    }
    return json.dumps(
        signed_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_update_manifest_signature(manifest: dict) -> bool:
    try:
        signature = base64.b64decode(str(manifest.get("signature") or ""), validate=True)
        key_size = (UPDATE_PUBLIC_KEY_N.bit_length() + 7) // 8
        if len(signature) != key_size:
            return False
        encoded = pow(int.from_bytes(signature, "big"), UPDATE_PUBLIC_KEY_E, UPDATE_PUBLIC_KEY_N)
        encoded_bytes = encoded.to_bytes(key_size, "big")
        digest_info = (
            bytes.fromhex("3031300d060960864801650304020105000420")
            + hashlib.sha256(canonical_update_manifest(manifest)).digest()
        )
        padding_size = key_size - len(digest_info) - 3
        if padding_size < 8:
            return False
        expected = b"\x00\x01" + (b"\xff" * padding_size) + b"\x00" + digest_info
        return encoded_bytes == expected
    except (TypeError, ValueError):
        return False


def _open_google_drive_download(file_id: str):
    request = urllib.request.Request(
        google_drive_download_url(file_id),
        headers={"User-Agent": "sig-updater/1.0"},
    )
    response = urllib.request.urlopen(request, timeout=60)
    content_type = str(response.headers.get("Content-Type") or "").lower()
    if "text/html" not in content_type:
        return response

    page = response.read(1024 * 1024).decode("utf-8", errors="replace")
    response.close()
    form_match = re.search(
        r'<form[^>]+action="([^"]+)"[^>]*>',
        page,
        flags=re.IGNORECASE,
    )
    if not form_match:
        raise RuntimeError("O Google Drive não forneceu o link de download do arquivo.")
    action = html.unescape(form_match.group(1))
    fields = {
        html.unescape(name): html.unescape(value)
        for name, value in re.findall(
            r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"',
            page,
            flags=re.IGNORECASE,
        )
    }
    separator = "&" if "?" in action else "?"
    confirmation_url = f"{action}{separator}{urlencode(fields)}"
    confirmation_request = urllib.request.Request(
        confirmation_url,
        headers={"User-Agent": "sig-updater/1.0"},
    )
    return urllib.request.urlopen(confirmation_request, timeout=60)


def download_google_drive_bytes(file_id: str, maximum_size: int) -> bytes:
    with _open_google_drive_download(file_id) as response:
        payload = response.read(maximum_size + 1)
    if len(payload) > maximum_size:
        raise RuntimeError("O manifesto de atualização excedeu o tamanho permitido.")
    return payload


def download_google_drive_file(file_id: str, destination: Path, progress_callback=None) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with _open_google_drive_download(file_id) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            output.write(chunk)
            digest.update(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total)
    return digest.hexdigest()


def download_github_url(url: str, destination: Path, progress_callback=None) -> str:
    """Baixa um arquivo de uma URL do GitHub releases, devolvendo o sha256."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "sig-updater/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            output.write(chunk)
            digest.update(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total)
    return digest.hexdigest()


_PROTECTED_NAMES = {"assets", "dist", "release", "src", "sig.spec"}


def _clean_project_root() -> None:
    """Remove todos os arquivos/pastas da raiz do projeto exceto os protegidos e dist/temp/."""
    root = project_root()
    # 1 — raiz do projeto
    for entry in sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name)):
        if entry.name in _PROTECTED_NAMES:
            continue
        try:
            if entry.is_file() or entry.is_symlink():
                entry.unlink()
            elif entry.is_dir():
                shutil.rmtree(entry)
        except OSError:
            continue
    # 2 — dist/temp/ (runtime files)
    dist_temp = app_base_dir() / "temp"
    if dist_temp.exists():
        try:
            shutil.rmtree(dist_temp)
        except OSError:
            pass


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

    def __init__(self, parent, on_seek, **kwargs):
        super().__init__(parent, height=96, highlightthickness=0, background="#ffffff", **kwargs)
        self.on_seek = on_seek
        self.main_name = ""
        self.inserted_name = ""
        self.main_duration = 0.0
        self.inserted_duration = 0.0
        self.insertion = 0.0
        self.position = 0.0
        self.dragging = False
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
        self._apply_position(event.x)

    def _drag(self, event) -> None:
        if self.dragging:
            self._apply_position(event.x)

    def _release(self, _event) -> None:
        self.dragging = False

    def _apply_position(self, x: float) -> None:
        self.position = self._time_for(x)
        self.draw()
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


class FfmpegTaskTracker:
    """Versão Tk do rastreador de etapas usado pelas ferramentas FFmpeg do Android."""

    def __init__(self, app: "SigApp", tasks: list[str]):
        self.app = app
        self.tasks: dict[str, dict[str, object]] = {task: {"progress": 0, "state": "pending", "detail": ""} for task in tasks}
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
        "fade",
        "dissolve",
        "wipeleft",
        "wiperight",
        "slideleft",
        "slideright",
        "smoothleft",
        "smoothright",
        "circleopen",
        "circleclose",
    )
    AUDIO_TRANSITIONS = (
        ("No transition", "none"),
        ("Fade in/out", "fade"),
        ("Linear slope (tri)", "tri"),
        ("Quarter sine wave (qsin)", "qsin"),
        ("Exponential sine wave (esin)", "esin"),
        ("Half sine wave (hsin)", "hsin"),
        ("Logarithmic (log)", "log"),
        ("Inverted parabola (ipar)", "ipar"),
        ("Quadratic (qua)", "qua"),
        ("Cubic (cub)", "cub"),
        ("Square root (squ)", "squ"),
        ("Cubic root (cbr)", "cbr"),
        ("Parabola (par)", "par"),
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
        self.cut_input_var = StringVar(value="Nenhum arquivo selecionado")
        self.cut_start_var = StringVar(value="0")
        self.cut_end_var = StringVar(value="")
        self.cut_current_var = StringVar(value="0:00")

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
        self.rotate_metadata_var = BooleanVar(value=True)
        self.rotate_parallel_var = BooleanVar(value=False)
        self.rotate_segments_var = StringVar(value="")
        self.rotate_current_var = StringVar(value="0:00")
        self.rotate_start_var = StringVar(value="0")
        self.rotate_end_var = StringVar(value="")

        self.join_inputs: list[Path] = []
        self.join_reencode_var = BooleanVar(value=False)
        self.join_smart_var = BooleanVar(value=False)
        self.join_transition_var = StringVar(value="Fade in/out")
        self.join_seconds_var = StringVar(value="0.5")

        self.insert_main_input: Path | None = None
        self.insert_secondary_input: Path | None = None
        self.insert_main_var = StringVar(value="Selecione o áudio principal")
        self.insert_secondary_var = StringVar(value="Nenhum áudio para inserir")
        self.insert_current_var = StringVar(value="0:00.000")
        self.insert_time_var = StringVar(value="0:00.000")
        self.insert_reencode_var = BooleanVar(value=False)
        self.insert_smart_var = BooleanVar(value=False)
        self.insert_transition_var = StringVar(value="No transition")
        self.insert_seconds_var = StringVar(value="0.5")
        self.insert_preview_context: dict | None = None
        self.insert_preview_phase_end = 0.0
        self.insert_preview_composite_start = 0.0

        self.clean_input: Path | None = None
        self.clean_input_var = StringVar(value="Nenhum áudio selecionado")
        self.clean_mode_var = StringVar(value="equilibrado")
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
        self._section_title(self.cut_tab, "Cortar áudio/vídeo", "Corte preciso: reencoda apenas quando necessário para respeitar o início e o fim selecionados.")
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
        ttk.Label(self.cut_tab, text="Exemplo: início 12.5 e fim 47.0. O arquivo é salvo com o sufixo _cortado.", style="Muted.TLabel").pack(anchor="w", pady=(10, 0))

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
        rotate_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_rotate_thumbnail())
        self.rotate_hflip_check = ttk.Checkbutton(row, text="Espelhar horizontal", variable=self.rotate_hflip_var, command=self._refresh_rotate_thumbnail)
        self.rotate_hflip_check.pack(side=LEFT, padx=(0, 12))
        self.rotate_vflip_check = ttk.Checkbutton(row, text="Espelhar vertical", variable=self.rotate_vflip_var, command=self._refresh_rotate_thumbnail)
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
                "Em vídeos curtos, o overhead pode piorar o tempo. Deixe vazio para usar todos os núcleos lógicos da máquina.",
            ),
        ).pack(side=LEFT)
        self.rotate_device_limit_var = StringVar(value="")
        self.rotate_device_limit_label = ttk.Label(self.rotate_tab, textvariable=self.rotate_device_limit_var, foreground="#b3261e")
        self._update_rotate_control_state()

    def _build_join_tab(self) -> None:
        self._section_title(self.join_tab, "Juntar áudios/vídeos", "Junta arquivos do mesmo tipo. Smart Join preserva trechos compatíveis; as transições geram uma saída consistente.")
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
            text="Reencodar",
            variable=self.join_reencode_var,
            command=self._update_join_controls,
        )
        self.join_reencode_check.pack(side=LEFT)
        self.join_smart_check = ttk.Checkbutton(
            join_checks,
            text="SmartJoin",
            variable=self.join_smart_var,
            command=self._update_join_controls,
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
        self._update_join_controls()

    def _build_insert_tab(self) -> None:
        self._section_title(
            self.insert_tab,
            "Inserir áudio",
            "Insere um segundo áudio no ponto escolhido do áudio principal. Smart Insert preserva o máximo possível do áudio original; Reencodar libera transições e cortes precisos.",
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
        self.insert_timeline = InsertAudioTimeline(self.insert_tab, self._insert_timeline_changed)
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
        ttk.Label(transition_row, text="Tempo (s):").pack(side=LEFT)
        self.insert_seconds_entry = ttk.Entry(transition_row, textvariable=self.insert_seconds_var, width=7, state="disabled")
        self.insert_seconds_entry.pack(side=LEFT, padx=(6, 0))
        checks = ttk.Frame(self.insert_options_frame)
        checks.pack(anchor="w", pady=(8, 0))
        self.insert_reencode_check = ttk.Checkbutton(
            checks,
            text="Reencodar",
            variable=self.insert_reencode_var,
            command=self._update_insert_controls,
        )
        self.insert_reencode_check.pack(side=LEFT)
        self.insert_smart_check = ttk.Checkbutton(
            checks,
            text="Smart Insert",
            variable=self.insert_smart_var,
            command=self._enable_insert_smart,
        )
        self.insert_smart_check.pack(side=LEFT, padx=(18, 0))
        ttk.Label(
            self.insert_options_frame,
            text="Sem reencodar, a operação tenta manter os codecs originais e não aplica transições.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(8, 0))
        self.insert_options_frame.pack_forget()

    def _build_clean_tab(self) -> None:
        self._section_title(self.clean_tab, "Limpar áudio", "Gera WAV mono, 16 kHz e 16-bit. Equilibrado usa afftdn; Forte usa anlmdn.")
        self._file_row(self.clean_tab, self.clean_input_var, self.select_clean_input)
        row = ttk.Frame(self.clean_tab)
        row.pack(anchor="w")
        ttk.Label(row, text="Filtro:").pack(side=LEFT)
        ttk.Combobox(row, textvariable=self.clean_mode_var, values=("equilibrado", "forte"), state="readonly", width=15).pack(side=LEFT, padx=(6, 0))

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

    def _refresh_encoder_control_state(self) -> None:
        uses_video_encoder = self.active_tool_var.get() in {"Cortar", "Girar vídeo", "Juntar áudios/vídeos"}
        has_encoder = bool(self.available_accelerations)
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
            "A compatibilidade continua sendo H.264/MP4 nos fluxos atuais; a escolha ajusta apenas a forma como o encoder trabalha.",
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

    def _refresh_extract_preset_controls(self) -> None:
        locked = self.extract_transcription_preset_var.get() or self.extract_compact_preset_var.get()
        for widget in self.extract_custom_widgets:
            widget.configure(state="disabled" if locked else "readonly")

    def _update_rotate_control_state(self) -> None:
        metadata_only = self.rotate_metadata_var.get()
        state = "disabled" if metadata_only else "normal"
        self.rotate_parallel_check.configure(state=state)
        self.rotate_hflip_check.configure(state=state)
        self.rotate_vflip_check.configure(state=state)
        show_parallel_options = not metadata_only and self.rotate_parallel_var.get()
        if show_parallel_options:
            self.rotate_parallel_frame.pack(anchor="w", pady=(6, 0))
            self.rotate_device_limit_label.pack(anchor="w", pady=(3, 0))
        else:
            self.rotate_parallel_frame.pack_forget()
            self.rotate_device_limit_label.pack_forget()
        self._refresh_rotate_device_limit()
        self._refresh_rotate_thumbnail()

    def _refresh_rotate_device_limit(self) -> None:
        # FFmpeg não expõe uma API confiável de sessões simultâneas para NVENC,
        # QSV ou AMF. Não estimamos esse número sem uma fonte do driver.
        self.rotate_device_limit_var.set("")

    def _update_join_controls(self) -> None:
        reencode = self.join_reencode_var.get()
        self.join_smart_check.configure(state="normal" if reencode else "disabled")
        self.join_transition_combo.configure(state="readonly" if reencode else "disabled")
        self.join_seconds_entry.configure(state="normal" if reencode else "disabled")
        if not reencode:
            self.join_smart_var.set(False)
            return
        if self.join_smart_var.get():
            choices = tuple(item for item in self.TRANSITIONS if item != "Fade in/out")
            self.join_transition_combo.configure(values=choices)
            if self.join_transition_var.get() == "Fade in/out":
                self.join_transition_var.set("fade")
        else:
            self.join_transition_combo.configure(values=self.TRANSITIONS)

    def _update_insert_controls(self) -> None:
        enabled = bool(self.insert_reencode_var.get()) and not self.running and self.insert_secondary_input is not None
        self.insert_smart_check.configure(state="normal" if self.insert_reencode_var.get() and not self.running else "disabled")
        self.insert_transition_combo.configure(state="readonly" if enabled else "disabled")
        self.insert_seconds_entry.configure(state="normal" if enabled else "disabled")
        if not self.insert_reencode_var.get():
            self.insert_smart_var.set(False)
            self.insert_transition_var.set("No transition")

    def _enable_insert_smart(self) -> None:
        if self.insert_smart_var.get():
            self.insert_reencode_var.set(True)
        self._update_insert_controls()

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
            "audio_only": source.suffix.lower() in AUDIO_EXTENSIONS,
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
        if not self.preview_player.open(context["source"], context["canvas"]):
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

    def _start_insert_preview_segment(self, context: dict, composite_position: float) -> None:
        self.preview_generation += 1
        generation = self.preview_generation
        self._terminate_preview_process(self.external_preview_process)
        self.external_preview_process = None
        timeline = self.insert_timeline
        inserted_duration = timeline.inserted_duration
        insertion = timeline.insertion
        total = timeline.duration
        inserted = self.insert_secondary_input
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
        remaining = max(0.02, (phase_end - composite_position) / max(0.01, self.preview_speed))
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
        position = min(self.insert_preview_phase_end, self.insert_preview_composite_start + elapsed)
        self.insert_timeline.set_position(position)
        main_position = self.insert_timeline.composite_to_main(position)
        context["current_var"].set(self._clock(main_position))
        context["timeline"].set_position(position)
        process = self.external_preview_process
        if process is not None and process.poll() is not None:
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
        self.insert_time_var.set(self._clock(main_position))
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
                    "-ss", self._fmt_seconds(offset), "-t", self._fmt_seconds(play_duration), "-af", self._preview_atempo_filter(), str(context["source"]),
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
        filters += [
            f"setpts=PTS/{self.preview_speed}",
            f"fps={fps}",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        ]
        self.frame_preview_stop_event.clear()
        video_command = [
            str(self._ffmpeg()), "-hide_banner", "-loglevel", "error", "-ss", self._fmt_seconds(offset),
            "-i", str(context["source"]), "-t", self._fmt_seconds(play_duration), "-an", "-vf", ",".join(filters), "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
        ]
        self.frame_preview_process = subprocess.Popen(
            video_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=flags | (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        )
        audio_command = [
            str(self._ffplay()), "-hide_banner", "-loglevel", "warning", "-autoexit", "-nodisp", "-ss", self._fmt_seconds(offset), "-t", self._fmt_seconds(play_duration), "-af", self._preview_atempo_filter(), str(context["source"]),
        ]
        self.external_preview_process = subprocess.Popen(
            audio_command,
            creationflags=flags | (subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        )
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
        position = min(timeline.end, self.external_preview_offset + time.monotonic() - self.external_preview_started_at)
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
            if self.preview_playing and not self.preview_player.opened:
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
        if self.preview_player.opened:
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
        if source.suffix.lower() not in VIDEO_EXTENSIONS:
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
            self.cut_input_var.set(self.cut_input.name)
            self._activate_preview(self.cut_input, self.cut_preview, self.cut_timeline, self.cut_current_var, self.cut_play_button, "cut")
            self.cut_start_var.set("0")
            self.cut_end_var.set(self._fmt_seconds(self.cut_timeline.duration))

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

    def select_rotate_input(self) -> None:
        selected = filedialog.askopenfilename(title="Selecionar vídeo", filetypes=[("Vídeos", "*.mp4 *.mov *.mkv *.avi *.webm"), ("Todos os arquivos", "*.*")])
        if selected:
            self.rotate_input = Path(selected)
            self.rotate_input_var.set(self.rotate_input.name)
            self._activate_preview(self.rotate_input, self.rotate_preview, self.rotate_timeline, self.rotate_current_var, self.rotate_play_button, "rotate")
            self.rotate_start_var.set("0")
            self.rotate_end_var.set(self._fmt_seconds(self.rotate_timeline.duration))

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
        self.insert_timeline.configure_media(source.name, main_media.duration, source.name, media.duration, insertion)
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
        self.insert_time_var.set(self._clock(main_position))
        if self.preview_playing:
            self._jump_to_insert_preview_position(composite_position)

    def _apply_insert_time(self) -> None:
        if not self.insert_main_input:
            return
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
            return
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

    def add_join_inputs(self) -> None:
        selected = filedialog.askopenfilenames(title="Selecionar áudios ou vídeos", filetypes=self._filetypes())
        if selected:
            self.join_inputs.extend(Path(item) for item in selected)
            self._refresh_join_list()

    def remove_join_input(self) -> None:
        selection = self.join_list.curselection()
        if selection:
            del self.join_inputs[selection[0]]
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

    def _append_log(self, message: str) -> None:
        # Diagnóstico completo continua salvo nos arquivos de erro; a UI usa apenas etapas.
        return

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
            self.acceleration = self._selected_acceleration()
            self._set_status(f"Encoder selecionado: {self.acceleration.label}; qualidade: {self.video_quality_var.get()}", 0)
            worker()
            if not self.cancel_event.is_set():
                self._set_status("Concluído. Arquivo(s) salvo(s) na pasta de saída.", 100)
                elapsed = max(.001, time.monotonic() - self.task_started_at)
                encoder = self.acceleration.encoder if self.acceleration else "não informado"
                self.task_tracker.success(f"Tempo de processamento: {elapsed:.1f}s\nEncoder: {encoder}") if self.task_tracker else None
        except Cancelled:
            self._set_status("Operação cancelada.")
            if self.task_tracker: self.task_tracker.fail("Operação cancelada pelo usuário.")
        except Exception as exc:
            self._set_status(f"Erro: {exc}")
            if self.task_tracker: self.task_tracker.fail(str(exc))
        finally:
            self.root.after(0, lambda: self._set_running_ui(False))

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

    def _detect_acceleration(self) -> VideoAcceleration:
        """Compatibilidade para chamadas internas: retorna a opção prioritária."""
        return self._available_accelerations()[0]

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
        command += ["-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1", "-frames:v", "1"]
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
        return f"{max(1, round(float(match.group(1)) * multiplier))}{match.group(2)}"

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

    def _video_args(self, profile: VideoAcceleration, bitrate: str = "1M") -> list[str]:
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
            if self._encoder_supports(profile, "-global_quality"):
                global_quality = {"Máxima": 17, "Muito alta": 20, "Alta": 23, "Média": 26, "Econômica": 29}[quality]
                return ["-c:v", profile.encoder, "-global_quality", str(global_quality)]
            return ["-c:v", profile.encoder, "-preset", "medium", *rate_control]
        if profile.key == "amf":
            if self._encoder_supports(profile, "-qvbr_quality_level") and self._encoder_supports(profile, "-rc"):
                qvbr = {"Máxima": 40, "Muito alta": 34, "Alta": 28, "Média": 22, "Econômica": 16}[quality]
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
        profile = self.acceleration or VideoAcceleration("cpu", "CPU (fallback)", "libx264")
        try:
            self._execute(builder(profile), label, progress, total, duration_seconds, progress_callback)
        except RuntimeError:
            if profile.key == "cpu":
                raise
            fallback = VideoAcceleration("cpu", "CPU (fallback)", "libx264")
            self._append_log(f"{profile.label} não concluiu a tarefa; repetindo com CPU.")
            self.acceleration = fallback
            self._execute(builder(fallback), f"{label} (CPU)", progress, total, duration_seconds, progress_callback)

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
            return ["-c:a", "libmp3lame", "-b:a", bitrate, "-minrate", bitrate, "-maxrate", bitrate]
        if ext == "m4a":
            return ["-c:a", "aac", "-b:a", bitrate, "-movflags", "+faststart"]
        if ext == "aac":
            return ["-c:a", "aac", "-b:a", bitrate]
        if ext == "ogg":
            return ["-c:a", "libvorbis", "-b:a", bitrate]
        if ext == "opus":
            return ["-c:a", "libopus", "-application", "voip", "-b:a", bitrate, "-vbr", "off"]
        if ext == "flac":
            return ["-c:a", "flac"]
        return ["-c:a", "aac", "-b:a", bitrate]

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
        start = self._seconds(self.cut_start_var.get(), "Início") or 0.0
        end = self._seconds(self.cut_end_var.get(), "Fim")
        if end is None or end <= start:
            raise RuntimeError("O fim deve ser maior que o início")
        duration = end - start
        is_video = source.suffix.lower() in VIDEO_EXTENSIONS
        extension = ".mp4" if is_video else source.suffix.lower()
        output = self._safe_output(self.output_dir, f"{source.stem}_cortado", extension)
        media = self._probe_media(source)

        if is_video:
            self._cut_video_hybrid(source, output, start, end, media)
        else:
            command = [str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(source), "-ss", self._fmt_seconds(start), "-t", self._fmt_seconds(duration), "-map", "0:a:0?", "-vn", *self._audio_codec_args(extension, media.audio_bitrate), str(output)]
            self._execute(command, "Cortando áudio", 1, 1)

    def _cut_video_hybrid(self, source: Path, output: Path, start: float, end: float, media: MediaProfile) -> None:
        """Preserva o trecho entre keyframes e recodifica apenas as duas bordas."""
        if not self._is_h264_video(source):
            self._append_log("Vídeo não é H.264; usando corte preciso com recodificação completa.")
            self._cut_video_precise(source, output, start, end, media)
            return

        self._set_status("Localizando keyframes para o corte híbrido...", 0)
        keyframes = self._extract_keyframes(source)
        start_keyframe = next((value for value in keyframes if value >= start - 0.001), None)
        end_keyframe = next((value for value in reversed(keyframes) if value <= end + 0.001), None)
        if start_keyframe is None or end_keyframe is None or start_keyframe >= end_keyframe:
            self._append_log("Não encontrei keyframes adequados; usando corte preciso com recodificação completa.")
            self._cut_video_precise(source, output, start, end, media)
            return

        work_dir = self.output_dir / f"cut_hybrid_{uuid.uuid4().hex}"
        work_dir.mkdir(parents=True, exist_ok=True)
        pieces: list[Path] = []
        try:
            if start_keyframe > start + 0.001:
                start_piece = work_dir / "inicio.ts"
                self._cut_hybrid_edge(source, start_piece, start, start_keyframe, media, "Recodificando início", 1, 4)
                pieces.append(start_piece)

            body_piece = work_dir / "corpo.ts"
            body_command = [
                str(self._ffmpeg()), "-hide_banner", "-y",
                "-ss", self._fmt_seconds(start_keyframe), "-i", str(source),
                "-t", self._fmt_seconds(end_keyframe - start_keyframe),
                "-map", "0:v:0?", "-map", "0:a:0?",
                "-c:v", "copy", "-bsf:v", "h264_mp4toannexb",
                "-c:a", "aac", "-b:a", media.audio_bitrate, "-ar", str(media.audio_rate), "-ac", str(media.audio_channels),
                "-avoid_negative_ts", "make_zero", "-mpegts_flags", "+resend_headers",
                "-f", "mpegts", str(body_piece),
            ]
            self._execute(body_command, "Copiando corpo entre keyframes", 2, 4)
            pieces.append(body_piece)

            if end_keyframe < end - 0.001:
                end_piece = work_dir / "fim.ts"
                self._cut_hybrid_edge(source, end_piece, end_keyframe, end, media, "Recodificando final", 3, 4)
                pieces.append(end_piece)

            list_file = work_dir / "partes.txt"
            lines = [f"file '{str(piece.resolve()).replace(chr(92), '/')}'" for piece in pieces]
            list_file.write_text("\n".join(lines), encoding="utf-8")
            concat_command = [
                str(self._ffmpeg()), "-hide_banner", "-y", "-fflags", "+genpts",
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-c", "copy", "-bsf:a", "aac_adtstoasc",
                "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", str(output),
            ]
            self._execute(concat_command, "Juntando trechos preservados", 4, 4)
        finally:
            for path in work_dir.iterdir():
                path.unlink(missing_ok=True)
            work_dir.rmdir()

    def _cut_hybrid_edge(
        self,
        source: Path,
        destination: Path,
        start: float,
        end: float,
        media: MediaProfile,
        label: str,
        progress: int,
        total: int,
    ) -> None:
        def build(profile: VideoAcceleration):
            input_args, filter_args = self._filter_for_profile("null", profile)
            return [
                str(self._ffmpeg()), "-hide_banner", "-y", *input_args,
                "-i", str(source), "-ss", self._fmt_seconds(start),
                "-t", self._fmt_seconds(end - start),
                "-map", "0:v:0?", "-map", "0:a:0?", *filter_args,
                *self._video_args(profile, media.video_bitrate), "-c:a", "aac", "-b:a", media.audio_bitrate,
                "-ar", str(media.audio_rate), "-ac", str(media.audio_channels),
                "-avoid_negative_ts", "make_zero", "-mpegts_flags", "+resend_headers",
                "-f", "mpegts", str(destination),
            ]
        self._execute_video(label, build, progress, total)

    def _cut_video_precise(self, source: Path, output: Path, start: float, end: float, media: MediaProfile) -> None:
        def build(profile: VideoAcceleration):
            input_args, filter_args = self._filter_for_profile("null", profile)
            return [
                str(self._ffmpeg()), "-hide_banner", "-y", *input_args,
                "-i", str(source), "-ss", self._fmt_seconds(start),
                "-t", self._fmt_seconds(end - start),
                "-map", "0:v:0?", "-map", "0:a:0?", *filter_args,
                *self._video_args(profile, media.video_bitrate), "-c:a", "aac", "-b:a", media.audio_bitrate,
                "-ar", str(media.audio_rate), "-ac", str(media.audio_channels),
                "-map_metadata", "0", "-map_chapters", "0", "-movflags", "+faststart",
                "-avoid_negative_ts", "make_zero", str(output),
            ]
        self._execute_video("Cortando vídeo com precisão", build)

    def _is_h264_video(self, source: Path) -> bool:
        result = subprocess.run(
            [str(self._ffmpeg()), "-hide_banner", "-i", str(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return bool(re.search(r"Video:\s*h264", result.stdout + result.stderr, re.IGNORECASE))

    def _extract_keyframes(self, source: Path) -> list[float]:
        command = [
            str(self._ffmpeg()), "-hide_banner", "-skip_frame", "nokey", "-i", str(source),
            "-vf", "showinfo", "-an", "-f", "null", "-",
        ]
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
        extension = self.extract_extension_var.get().lower()
        start = self._seconds(self.extract_start_var.get(), "Início", True)
        end = self._seconds(self.extract_end_var.get(), "Fim", True)
        if (start is None) != (end is None):
            raise RuntimeError("Informe início e fim para usar o recorte")
        if start is not None and end is not None and end <= start:
            raise RuntimeError("O fim deve ser maior que o início")
        rate = self.extract_rate_var.get()
        channels = self.extract_channels_var.get()
        bitrate = self.extract_bitrate_var.get()
        total = len(self.extract_inputs)
        for index, source in enumerate(self.extract_inputs, start=1):
            if not source.exists():
                raise RuntimeError(f"Arquivo não encontrado: {source.name}")
            output = self._safe_output(self.output_dir, f"{source.stem}_audio", f".{extension}")
            command = [str(self._ffmpeg()), "-hide_banner", "-y"]
            if start is not None:
                command += ["-ss", self._fmt_seconds(start)]
            command += ["-i", str(source)]
            if start is not None and end is not None:
                command += ["-t", self._fmt_seconds(end - start)]
            command += ["-vn", "-map", "0:a:0", "-ar", rate, "-ac", channels, *self._audio_codec_args(extension, bitrate), str(output)]
            self._execute(command, f"Extraindo {source.name}", index, total)

    def _rotate_worker(self) -> None:
        source = self.rotate_input
        if not source or not source.exists():
            raise RuntimeError("Selecione o vídeo para girar")
        try:
            degrees = int(self.rotate_degrees_var.get())
        except ValueError as exc:
            raise RuntimeError("Selecione um giro válido") from exc
        media = self._probe_media(source)
        start = self._seconds(self.rotate_start_var.get(), "Início") or 0.0
        end = self._seconds(self.rotate_end_var.get(), "Fim")
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
        if self.rotate_metadata_var.get():
            command = [str(self._ffmpeg()), "-hide_banner", "-y", *seek_args, "-i", str(source), *duration_args, "-map", "0", "-c", "copy", "-metadata:s:v:0", f"rotate={degrees % 360}", str(output)]
            self._execute(command, "Cortando e atualizando rotação" if has_trim else "Atualizando metadados de rotação", 1, 1, trim_duration)
            return
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
        if not filters:
            command = [str(self._ffmpeg()), "-hide_banner", "-y", *seek_args, "-i", str(source), *duration_args, "-c", "copy", str(output)]
            self._execute(command, "Cortando vídeo" if has_trim else "Copiando vídeo", 1, 1, trim_duration)
            return
        filter_text = ",".join(filters)

        duration = trim_duration
        requested_segments: int | None = None
        requested_text = self.rotate_segments_var.get().strip()
        if requested_text:
            try:
                requested_segments = int(requested_text)
            except ValueError as exc:
                raise RuntimeError("Trechos deve ser um número inteiro positivo ou ficar vazio") from exc
            if requested_segments < 1:
                raise RuntimeError("Trechos deve ser maior que zero")
        if self.rotate_parallel_var.get() and not has_trim and duration >= 6:
            keyframes = [value for value in self._extract_keyframes(source) if 0.1 < value < duration - 0.1]
            if keyframes:
                try:
                    self._rotate_video_parallel(source, output, filter_text, duration, keyframes, media.video_bitrate, requested_segments)
                    return
                except Cancelled:
                    raise
                except Exception as exc:
                    self._append_log(f"Giro paralelo não concluiu ({exc}); repetindo em um único processo.")
        def build(profile):
            input_args, filter_args = self._filter_for_profile(filter_text, profile)
            return [str(self._ffmpeg()), "-hide_banner", "-y", *input_args, *seek_args, "-i", str(source), *duration_args, "-map", "0:v:0", "-map", "0:a?", *filter_args, *self._video_args(profile, media.video_bitrate), "-c:a", "copy", "-map_metadata", "-1", "-metadata:s:v:0", "rotate=0", "-movflags", "+faststart", str(output)]
        self._execute_video("Girando e cortando vídeo" if has_trim else "Girando vídeo", build, duration_seconds=trim_duration)

    def _rotate_video_parallel(
        self,
        source: Path,
        output: Path,
        filters: str,
        duration: float,
        keyframes: list[float],
        video_bitrate: str,
        requested_segments: int | None,
    ) -> None:
        # O valor manual controla tanto a quantidade de partes quanto a de
        # processos simultâneos. Sem valor, usamos todos os núcleos lógicos.
        requested_workers = requested_segments or max(1, os.cpu_count() or 1)
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
            pattern = work_dir / "parte_%05d.mp4"
            split_times = ",".join(self._fmt_seconds(value) for value in sorted(split_points))
            split_command = [
                str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(source), "-map", "0", "-c", "copy",
                "-f", "segment", "-segment_times", split_times, "-reset_timestamps", "1",
                "-segment_format", "mp4", "-avoid_negative_ts", "make_zero", str(pattern),
            ]
            self._execute(split_command, "Dividindo vídeo em trechos", 1, 3)
            segments = sorted(work_dir.glob("parte_*.mp4"))
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
                        "-c:a", "copy", "-map_metadata", "-1", "-metadata:s:v:0", "rotate=0",
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
                lines.append(f"file '{str(path.resolve()).replace(chr(92), '/')}'")
            list_file.write_text("\n".join(lines), encoding="utf-8")
            concat_command = [
                str(self._ffmpeg()), "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-c", "copy", "-map_metadata", "-1", "-metadata:s:v:0", "rotate=0",
                "-movflags", "+faststart", str(output),
            ]
            self._execute(concat_command, "Juntando vídeo final", len(segments) + 2, len(segments) + 2, duration)
            self._append_log(f"Giro paralelo concluído: {len(segments)} trechos, até {worker_count} em paralelo.")
        finally:
            for path in work_dir.glob("*"):
                path.unlink(missing_ok=True)
            work_dir.rmdir()

    def _probe_media(self, source: Path) -> MediaProfile:
        command = [str(self._ffmpeg()), "-hide_banner", "-i", str(source)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        text = result.stderr + result.stdout
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", text)
        duration = 0.0
        if duration_match:
            duration = int(duration_match.group(1)) * 3600 + int(duration_match.group(2)) * 60 + float(duration_match.group(3))
        video_line = next((line for line in text.splitlines() if "Video:" in line), "")
        audio_line = next((line for line in text.splitlines() if "Audio:" in line), "")
        video_match = re.search(r"(\d{2,5})x(\d{2,5}).*?(\d+(?:\.\d+)?) fps", video_line)
        width = int(video_match.group(1)) if video_match else 1280
        height = int(video_match.group(2)) if video_match else 720
        fps = video_match.group(3) if video_match else "30"
        video_rates = re.findall(r"(\d+(?:\.\d+)?)\s*kb/s", video_line)
        audio_rates = re.findall(r"(\d+(?:\.\d+)?)\s*kb/s", audio_line)
        video_bitrate = f"{float(video_rates[-1]):g}k" if video_rates and float(video_rates[-1]) > 0 else "1M"
        audio_bitrate = f"{float(audio_rates[-1]):g}k" if audio_rates and float(audio_rates[-1]) > 0 else "128k"
        rate_match = re.search(r"(\d+)\s*Hz", audio_line)
        audio_rate = int(rate_match.group(1)) if rate_match else 48000
        if re.search(r"\bmono\b", audio_line):
            audio_channels, audio_layout = 1, "mono"
        elif re.search(r"\bstereo\b", audio_line):
            audio_channels, audio_layout = 2, "stereo"
        else:
            channels_match = re.search(r"(\d+)\s*channels", audio_line)
            audio_channels = int(channels_match.group(1)) if channels_match else 2
            audio_layout = {1: "mono", 2: "stereo", 6: "5.1", 8: "7.1"}.get(audio_channels, "stereo")
        return MediaProfile(
            duration, bool(audio_line), width - width % 2, height - height % 2, fps,
            video_bitrate, audio_bitrate, audio_rate, audio_channels, audio_layout,
            bool(video_line),
        )

    def _join_audio_worker(self, clips: list[MediaProfile]) -> None:
        try:
            transition_seconds = float(self.join_seconds_var.get().replace(",", "."))
        except ValueError as exc:
            raise RuntimeError("Tempo de transição inválido") from exc
        if transition_seconds < 0:
            raise RuntimeError("Tempo de transição não pode ser negativo")

        copy_only = not self.join_reencode_var.get() or (self.join_smart_var.get() and transition_seconds == 0)
        if copy_only:
            extension = self.join_inputs[0].suffix.lower() or ".m4a"
            output = self._safe_output(self.output_dir, "audios_juntos", extension)
            list_file = self.output_dir / f"join_audio_{uuid.uuid4().hex}.txt"
            list_file.write_text(
                "\n".join(f"file '{str(path.resolve()).replace(chr(92), '/')}'" for path in self.join_inputs),
                encoding="utf-8",
            )
            try:
                command = [
                    str(self._ffmpeg()), "-hide_banner", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(list_file), "-c", "copy", str(output),
                ]
                self._execute(command, "Juntando áudios sem reencodar", 1, 1, sum(item.duration for item in clips))
                return
            finally:
                list_file.unlink(missing_ok=True)

        shortest = min(item.duration for item in clips)
        transition_seconds = min(transition_seconds, max(0.0, shortest - 0.05))
        output = self._safe_output(self.output_dir, "audios_juntos", ".m4a")
        command = [str(self._ffmpeg()), "-hide_banner", "-y"]
        for path in self.join_inputs:
            command += ["-i", str(path)]
        if transition_seconds > 0:
            filters: list[str] = []
            previous = "0:a"
            for index in range(1, len(self.join_inputs)):
                output_label = f"a{index}out"
                filters.append(
                    f"[{previous}][{index}:a]acrossfade=d={self._fmt_seconds(transition_seconds)}"
                    f":c1=tri:c2=tri[{output_label}]"
                )
                previous = output_label
            filter_text = ";".join(filters)
            command += ["-filter_complex", filter_text, "-map", f"[{previous}]"]
        else:
            inputs = "".join(f"[{index}:a]" for index in range(len(self.join_inputs)))
            command += [
                "-filter_complex", f"{inputs}concat=n={len(self.join_inputs)}:v=0:a=1[aout]",
                "-map", "[aout]",
            ]
        first = clips[0]
        command += [
            "-c:a", "aac", "-b:a", first.audio_bitrate, "-ar", str(first.audio_rate),
            "-ac", str(first.audio_channels), "-movflags", "+faststart", str(output),
        ]
        total_duration = sum(item.duration for item in clips) - transition_seconds * (len(clips) - 1)
        self._execute(command, "Aplicando transições e juntando áudios", 1, 1, max(0.1, total_duration))

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
        output = self._safe_output(self.output_dir, "videos_juntos", ".mp4")
        if not self.join_reencode_var.get():
            list_file = self.output_dir / f"join_list_{uuid.uuid4().hex}.txt"
            lines = []
            for path in self.join_inputs:
                normalized = str(path.resolve()).replace("\\", "/")
                lines.append(f"file '{normalized}'")
            list_file.write_text("\n".join(lines), encoding="utf-8")
            try:
                self._execute(
                    [str(self._ffmpeg()), "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", "-movflags", "+faststart", str(output)],
                    "Juntando sem reencodar",
                    1,
                    1,
                )
                return
            finally:
                list_file.unlink(missing_ok=True)
        try:
            transition_seconds = float(self.join_seconds_var.get().replace(",", "."))
        except ValueError as exc:
            raise RuntimeError("Tempo de transição inválido") from exc
        if transition_seconds < 0:
            raise RuntimeError("Tempo de transição não pode ser negativo")
        strategy = "Smart Join" if self.join_smart_var.get() else "Reencodar"
        transition = self.join_transition_var.get()
        if strategy == "Smart Join" and transition_seconds == 0:
            list_file = self.output_dir / f"join_list_{uuid.uuid4().hex}.txt"
            lines = []
            for path in self.join_inputs:
                normalized = str(path.resolve()).replace("\\", "/")
                lines.append(f"file '{normalized}'")
            list_file.write_text("\n".join(lines), encoding="utf-8")
            try:
                self._execute([str(self._ffmpeg()), "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", "-movflags", "+faststart", str(output)], "Smart Join sem perda", 1, 1)
                return
            finally:
                list_file.unlink(missing_ok=True)
        if any(duration <= 0 for duration, *_rest in clips):
            raise RuntimeError("Não consegui identificar a duração de um dos vídeos")
        shortest = min(duration for duration, *_rest in clips)
        transition_seconds = min(transition_seconds, max(0.0, shortest - 0.1))
        base = clips[0]
        profile = {
            "width": max(2, base.width), "height": max(2, base.height), "fps": base.fps,
            "video_bitrate": base.video_bitrate, "audio_bitrate": base.audio_bitrate,
            "audio_rate": base.audio_rate, "audio_channels": base.audio_channels,
            "audio_layout": base.audio_layout,
        }
        self._append_log(
            f"Perfil de saída: {profile['width']}x{profile['height']} a {profile['fps']} fps, "
            f"vídeo {profile['video_bitrate']}, áudio {profile['audio_bitrate']} "
            f"{profile['audio_rate']} Hz/{profile['audio_channels']} canal(is)."
        )
        if strategy == "Smart Join":
            try:
                if transition == "Fade in/out":
                    self._join_fade_hybrid(self.join_inputs, clips, profile, transition_seconds, output)
                else:
                    self._join_smart_hybrid(self.join_inputs, clips, profile, transition_seconds, transition, output)
                return
            except Cancelled:
                raise
            except Exception as exc:
                self._append_log(f"Smart Join não ficou compatível ({exc}); usando junção completa.")
        if transition == "Fade in/out":
            filters = self._fade_join_filter(clips, profile, transition_seconds)
        else:
            filters = self._xfade_join_filter(clips, profile, transition_seconds, transition)
        def build(acceleration):
            input_args = [str(self._ffmpeg()), "-hide_banner", "-y"]
            for path in self.join_inputs:
                input_args += ["-i", str(path)]
            prefix: list[str] = []
            filter_text = filters
            if acceleration.key == "vaapi":
                prefix = ["-vaapi_device", "/dev/dri/renderD128"]
                filter_text = filter_text + ";[vout]format=nv12,hwupload[vhw]"
                map_video = "[vhw]"
            else:
                map_video = "[vout]"
            return [*input_args[:3], *prefix, *input_args[3:], "-filter_complex", filter_text, "-map", map_video, "-map", "[aout]", *self._video_args(acceleration, profile["video_bitrate"]), "-r", profile["fps"], *self._join_audio_args(profile), "-movflags", "+faststart", str(output)]
        self._execute_video("Juntando vídeos", build)

    def _join_smart_hybrid(
        self,
        inputs: list[Path],
        clips: list[tuple],
        profile: dict,
        transition_seconds: float,
        transition: str,
        output: Path,
    ) -> None:
        if transition_seconds <= 0:
            raise RuntimeError("a transição deve ser maior que zero")
        if not all(self._is_h264_video(path) for path in inputs):
            raise RuntimeError("Smart Join preservado requer vídeos H.264 compatíveis")
        work_dir = self.output_dir / f"smart_join_{uuid.uuid4().hex}"
        work_dir.mkdir(parents=True, exist_ok=True)
        pieces: list[Path] = []
        total_steps = len(inputs) * 2
        step = 0
        try:
            for index, source in enumerate(inputs):
                duration, *_rest = clips[index]
                body_start = 0.0 if index == 0 else transition_seconds
                body_end = duration if index == len(inputs) - 1 else duration - transition_seconds
                body_duration = body_end - body_start
                if body_duration > 0.12:
                    step += 1
                    body = work_dir / f"corpo_{index:03d}.ts"
                    self._join_copy_body(source, clips[index], profile, body, body_start, body_duration, f"Copiando corpo {index + 1}/{len(inputs)}", step, total_steps)
                    pieces.append(body)
                if index < len(inputs) - 1:
                    step += 1
                    transition_file = work_dir / f"transicao_{index:03d}.ts"
                    self._join_transition_piece(
                        source,
                        inputs[index + 1],
                        clips[index],
                        clips[index + 1],
                        profile,
                        transition_seconds,
                        transition,
                        transition_file,
                        f"Gerando transição {index + 1}/{len(inputs) - 1}",
                        step,
                        total_steps,
                    )
                    pieces.append(transition_file)
            if not pieces:
                raise RuntimeError("nenhum trecho foi gerado")
            self._join_ts_concat(pieces, output, "Juntando trechos preservados", total_steps, total_steps)
        finally:
            for path in work_dir.glob("*"):
                path.unlink(missing_ok=True)
            work_dir.rmdir()

    def _join_fade_hybrid(
        self,
        inputs: list[Path],
        clips: list[tuple],
        profile: dict,
        transition_seconds: float,
        output: Path,
    ) -> None:
        if transition_seconds <= 0:
            raise RuntimeError("a transição deve ser maior que zero")
        if not all(self._is_h264_video(path) for path in inputs):
            raise RuntimeError("Fade otimizado requer vídeos H.264 compatíveis")
        work_dir = self.output_dir / f"fade_join_{uuid.uuid4().hex}"
        work_dir.mkdir(parents=True, exist_ok=True)
        pieces: list[Path] = []
        total_steps = len(inputs) * 3
        step = 0
        try:
            for index, source in enumerate(inputs):
                duration, *_rest = clips[index]
                body_start = 0.0 if index == 0 else transition_seconds
                body_end = duration if index == len(inputs) - 1 else duration - transition_seconds
                body_duration = body_end - body_start
                if body_duration > 0.12:
                    step += 1
                    body = work_dir / f"corpo_{index:03d}.ts"
                    self._join_copy_body(source, clips[index], profile, body, body_start, body_duration, f"Copiando corpo {index + 1}/{len(inputs)}", step, total_steps)
                    pieces.append(body)
                if index < len(inputs) - 1:
                    step += 1
                    fade_out = work_dir / f"fade_out_{index:03d}.ts"
                    self._join_fade_piece(
                        source, clips[index], profile, duration - transition_seconds, transition_seconds,
                        False, fade_out, f"Gerando fade-out {index + 1}/{len(inputs) - 1}", step, total_steps,
                    )
                    pieces.append(fade_out)
                    step += 1
                    fade_in = work_dir / f"fade_in_{index:03d}.ts"
                    self._join_fade_piece(
                        inputs[index + 1], clips[index + 1], profile, 0.0, transition_seconds,
                        True, fade_in, f"Gerando fade-in {index + 1}/{len(inputs) - 1}", step, total_steps,
                    )
                    pieces.append(fade_in)
            if not pieces:
                raise RuntimeError("nenhum trecho foi gerado")
            self._join_ts_concat(pieces, output, "Juntando fade in/out", total_steps, total_steps)
        finally:
            for path in work_dir.glob("*"):
                path.unlink(missing_ok=True)
            work_dir.rmdir()

    def _join_copy_body(
        self,
        source: Path,
        clip: tuple,
        profile: dict,
        destination: Path,
        start: float,
        duration: float,
        label: str,
        progress: int,
        total: int,
    ) -> None:
        command = [str(self._ffmpeg()), "-hide_banner", "-y", "-fflags", "+genpts"]
        if start > 0.001:
            command += ["-ss", self._fmt_seconds(start)]
        command += ["-i", str(source), "-t", self._fmt_seconds(duration), "-map", "0:v:0"]
        if clip[1]:
            command += ["-map", "0:a:0?"]
        command += [
            "-c:v", "copy", "-bsf:v", "h264_mp4toannexb", *self._join_audio_args(profile),
            "-avoid_negative_ts", "make_zero",
            "-mpegts_flags", "+resend_headers", "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", str(destination),
        ]
        self._execute(command, label, progress, total)

    def _join_transition_piece(
        self,
        first: Path,
        second: Path,
        first_clip: tuple,
        second_clip: tuple,
        profile: dict,
        transition_seconds: float,
        transition: str,
        destination: Path,
        label: str,
        progress: int,
        total: int,
    ) -> None:
        window = min(transition_seconds * 2, first_clip[0], second_clip[0])
        first_start = max(0.0, first_clip[0] - window)
        filter_text = self._smart_transition_filter(first_clip, second_clip, profile, transition_seconds, window, transition)
        def build(acceleration: VideoAcceleration):
            prefix: list[str] = []
            mapped_video = "[vout]"
            final_filter = filter_text
            if acceleration.key == "vaapi":
                prefix = ["-vaapi_device", "/dev/dri/renderD128"]
                final_filter += ";[vout]format=nv12,hwupload[vhw]"
                mapped_video = "[vhw]"
            return [
                str(self._ffmpeg()), "-hide_banner", "-y", "-fflags", "+genpts", *prefix,
                "-noautorotate", "-ss", self._fmt_seconds(first_start), "-t", self._fmt_seconds(window), "-i", str(first),
                "-noautorotate", "-ss", "0", "-t", self._fmt_seconds(window), "-i", str(second),
                "-filter_complex", final_filter, "-map", mapped_video, "-map", "[aout]",
                *self._video_args(acceleration, profile["video_bitrate"]), "-r", profile["fps"], "-g", "1", "-bf", "0",
                *self._join_audio_args(profile),
                "-avoid_negative_ts", "make_zero", "-mpegts_flags", "+resend_headers", "-muxdelay", "0", "-muxpreload", "0",
                "-f", "mpegts", str(destination),
            ]
        self._execute_video(label, build, progress, total)

    def _join_fade_piece(
        self,
        source: Path,
        clip: tuple,
        profile: dict,
        start: float,
        duration: float,
        fade_in: bool,
        destination: Path,
        label: str,
        progress: int,
        total: int,
    ) -> None:
        fade_type = "in" if fade_in else "out"
        video = (
            f"[0:v]{self._join_normalize_filter(profile)},fade=t={fade_type}:st=0:d={self._fmt_seconds(duration)},"
            "settb=AVTB,setpts=PTS-STARTPTS[vout]"
        )
        if clip[1]:
            audio = (
                f"[0:a]aresample={profile['audio_rate']},aformat=sample_fmts=fltp:sample_rates={profile['audio_rate']}:channel_layouts={profile['audio_layout']},"
                f"afade=t={fade_type}:st=0:d={self._fmt_seconds(duration)},asetpts=N/SR/TB[aout]"
            )
        else:
            audio = f"anullsrc=channel_layout={profile['audio_layout']}:sample_rate={profile['audio_rate']},atrim=0:{self._fmt_seconds(duration)},asetpts=N/SR/TB[aout]"
        filter_text = f"{video};{audio}"
        def build(acceleration: VideoAcceleration):
            prefix: list[str] = []
            mapped_video = "[vout]"
            final_filter = filter_text
            if acceleration.key == "vaapi":
                prefix = ["-vaapi_device", "/dev/dri/renderD128"]
                final_filter += ";[vout]format=nv12,hwupload[vhw]"
                mapped_video = "[vhw]"
            return [
                str(self._ffmpeg()), "-hide_banner", "-y", "-fflags", "+genpts", *prefix,
                "-noautorotate", "-ss", self._fmt_seconds(start), "-i", str(source), "-t", self._fmt_seconds(duration),
                "-filter_complex", final_filter, "-map", mapped_video, "-map", "[aout]",
                *self._video_args(acceleration, profile["video_bitrate"]), "-r", profile["fps"], "-g", self._join_gop(profile), "-bf", "0",
                *self._join_audio_args(profile),
                "-avoid_negative_ts", "make_zero", "-mpegts_flags", "+resend_headers", "-muxdelay", "0", "-muxpreload", "0",
                "-f", "mpegts", str(destination),
            ]
        self._execute_video(label, build, progress, total)

    def _join_ts_concat(self, pieces: list[Path], output: Path, label: str, progress: int, total: int) -> None:
        list_file = pieces[0].parent / "lista.txt"
        lines = [f"file '{str(path.resolve()).replace(chr(92), '/')}'" for path in pieces]
        list_file.write_text("\n".join(lines), encoding="utf-8")
        command = [
            str(self._ffmpeg()), "-hide_banner", "-y", "-fflags", "+genpts", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", "-bsf:a", "aac_adtstoasc", "-avoid_negative_ts", "make_zero",
            "-max_interleave_delta", "0", "-use_editlist", "0", "-video_track_timescale", "90000", "-movflags", "+faststart", str(output),
        ]
        self._execute(command, label, progress, total)

    def _join_normalize_filter(self, profile: dict) -> str:
        return (
            f"scale={profile['width']}:{profile['height']}:force_original_aspect_ratio=decrease,"
            f"pad={profile['width']}:{profile['height']}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={profile['fps']},format=yuv420p"
        )

    def _join_gop(self, profile: dict) -> str:
        try:
            return str(max(1, round(float(profile["fps"]))))
        except (TypeError, ValueError):
            return "30"

    def _smart_transition_filter(
        self,
        first_clip: tuple,
        second_clip: tuple,
        profile: dict,
        transition_seconds: float,
        window: float,
        transition: str,
    ) -> str:
        offset = max(0.0, window - transition_seconds)
        end = offset + transition_seconds
        video0 = f"[0:v]{self._join_normalize_filter(profile)},settb=AVTB,setpts=PTS-STARTPTS[v0]"
        video1 = f"[1:v]{self._join_normalize_filter(profile)},settb=AVTB,setpts=PTS-STARTPTS[v1]"
        if first_clip[1]:
            audio0 = f"[0:a]aresample={profile['audio_rate']},aformat=sample_fmts=fltp:sample_rates={profile['audio_rate']}:channel_layouts={profile['audio_layout']},atrim=start={self._fmt_seconds(offset)}:end={self._fmt_seconds(end)},asetpts=PTS-STARTPTS[a0]"
        else:
            audio0 = f"anullsrc=channel_layout={profile['audio_layout']}:sample_rate={profile['audio_rate']},atrim=0:{self._fmt_seconds(transition_seconds)},asetpts=N/SR/TB[a0]"
        if second_clip[1]:
            audio1 = f"[1:a]aresample={profile['audio_rate']},aformat=sample_fmts=fltp:sample_rates={profile['audio_rate']}:channel_layouts={profile['audio_layout']},atrim=start=0:end={self._fmt_seconds(transition_seconds)},asetpts=PTS-STARTPTS[a1]"
        else:
            audio1 = f"anullsrc=channel_layout={profile['audio_layout']}:sample_rate={profile['audio_rate']},atrim=0:{self._fmt_seconds(transition_seconds)},asetpts=N/SR/TB[a1]"
        xfade = f"[v0][v1]xfade=transition={transition}:duration={self._fmt_seconds(transition_seconds)}:offset={self._fmt_seconds(offset)},trim=start={self._fmt_seconds(offset)}:end={self._fmt_seconds(end)},fps={profile['fps']},settb=AVTB,setpts=N/({profile['fps']}*TB)[vout]"
        audio_mix = f"[a0]afade=t=out:st=0:d={self._fmt_seconds(transition_seconds)}[a0f];[a1]afade=t=in:st=0:d={self._fmt_seconds(transition_seconds)}[a1f];[a0f][a1f]amix=inputs=2:duration=first,volume=2.0,aformat=sample_fmts=fltp:sample_rates={profile['audio_rate']}:channel_layouts={profile['audio_layout']},asetpts=N/SR/TB[aout]"
        return ";".join((video0, video1, audio0, audio1, xfade, audio_mix))

    def _video_normalize_filter(self, index: int, profile: dict) -> str:
        return f"[{index}:v]scale={profile['width']}:{profile['height']}:force_original_aspect_ratio=increase,crop={profile['width']}:{profile['height']},setsar=1,fps={profile['fps']},format=yuv420p,setpts=PTS-STARTPTS[v{index}]"

    def _audio_normalize_filter(self, index: int, clip: tuple, profile: dict) -> str:
        duration, has_audio, *_rest = clip
        if has_audio:
            return f"[{index}:a]aresample={profile['audio_rate']},aformat=sample_fmts=fltp:sample_rates={profile['audio_rate']}:channel_layouts={profile['audio_layout']},asetpts=PTS-STARTPTS[a{index}]"
        return f"anullsrc=channel_layout={profile['audio_layout']}:sample_rate={profile['audio_rate']},atrim=0:{self._fmt_seconds(duration)},asetpts=N/SR/TB[a{index}]"

    def _fade_join_filter(self, clips: list[tuple], profile: dict, seconds: float) -> str:
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
                f"[{index}:v]scale={profile['width']}:{profile['height']}:force_original_aspect_ratio=increase,"
                f"crop={profile['width']}:{profile['height']},setsar=1,fps={profile['fps']},format=yuv420p"
            )
            if video_fades:
                video += "," + ",".join(video_fades)
            video += f",setpts=PTS-STARTPTS[v{index}]"
            parts.append(video)
            audio = self._audio_normalize_filter(index, clip, profile)
            if audio_fades:
                audio = audio.replace(f",asetpts=PTS-STARTPTS[a{index}]", "," + ",".join(audio_fades) + f",asetpts=PTS-STARTPTS[a{index}]")
            parts.append(audio)
        inputs = "".join(f"[v{index}][a{index}]" for index in range(len(clips)))
        parts.append(f"{inputs}concat=n={len(clips)}:v=1:a=1[vout][aout]")
        return ";".join(parts)

    def _xfade_join_filter(self, clips: list[tuple], profile: dict, seconds: float, transition: str) -> str:
        parts = [self._video_normalize_filter(index, profile) for index in range(len(clips))]
        parts.extend(self._audio_normalize_filter(index, clip, profile) for index, clip in enumerate(clips))
        last_video, last_audio = "v0", "a0"
        accumulated = clips[0][0]
        transition_name = "fade" if transition == "Fade in/out" else transition
        for index in range(1, len(clips)):
            video_out, audio_out = f"vx{index}", f"ax{index}"
            offset = max(0.0, accumulated - seconds)
            parts.append(f"[{last_video}][v{index}]xfade=transition={transition_name}:duration={self._fmt_seconds(seconds)}:offset={self._fmt_seconds(offset)}[{video_out}]")
            parts.append(f"[{last_audio}][a{index}]acrossfade=d={self._fmt_seconds(seconds)}[{audio_out}]")
            last_video, last_audio = video_out, audio_out
            accumulated += clips[index][0] - seconds
        parts.append(f"[{last_video}]copy[vout]")
        parts.append(f"[{last_audio}]acopy[aout]")
        return ";".join(parts)

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
        transition_code = dict(self.AUDIO_TRANSITIONS).get(self.insert_transition_var.get(), "none")
        try:
            transition_seconds = float(self.insert_seconds_var.get().replace(",", "."))
        except ValueError as exc:
            raise RuntimeError("Tempo de transição inválido") from exc
        if transition_seconds < 0:
            raise RuntimeError("Tempo de transição não pode ser negativo")

        full_reencode = self.insert_reencode_var.get() and (
            not self.insert_smart_var.get() or transition_code != "none"
        )
        extension = ".m4a" if full_reencode else (main.suffix.lower() if main.suffix.lower() in AUDIO_EXTENSIONS else ".m4a")
        output = self._safe_output(self.output_dir, f"{main.stem}_com_audio", extension)
        total_duration = main_profile.duration + inserted_profile.duration
        mode = "Reencodificação com transição" if full_reencode else ("Smart Insert" if self.insert_smart_var.get() else "Sem reencodar")
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
            self._execute(command, "Inserindo áudio com reencodificação", 1, 1, total_duration)
            return
        if self.insert_smart_var.get():
            self._insert_smart_worker(main, inserted, output, main_profile, insertion, total_duration)
            return
        self._insert_copy_worker(main, inserted, output, insertion, total_duration)

    def _insert_copy_worker(self, main: Path, inserted: Path, output: Path, insertion: float, total_duration: float) -> None:
        work_dir = self.output_dir / f"insert_copy_{uuid.uuid4().hex}"
        work_dir.mkdir(parents=True, exist_ok=True)
        extension = output.suffix or ".m4a"
        pieces: list[Path] = []
        try:
            if insertion > 0.001:
                left = work_dir / f"000{extension}"
                self._execute(
                    [str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(main), "-t", self._fmt_seconds(insertion), "-map", "0:a:0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(left)],
                    "Preparando trecho inicial",
                    1,
                    4,
                    insertion,
                )
                pieces.append(left)
            middle = work_dir / f"{len(pieces):03d}{extension}"
            self._execute(
                [str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(inserted), "-map", "0:a:0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(middle)],
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
                    [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", self._fmt_seconds(insertion), "-i", str(main), "-map", "0:a:0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(right)],
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

    def _insert_smart_worker(self, main: Path, inserted: Path, output: Path, profile: MediaProfile, insertion: float, total_duration: float) -> None:
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
                    [str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(main), "-t", self._fmt_seconds(insertion), "-map", "0:a:0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(left)],
                    "Smart Insert: trecho inicial",
                    step,
                    4,
                    insertion,
                )
                pieces.append(left)
            step += 1
            middle = work_dir / f"{len(pieces):03d}{extension}"
            self._execute(
                [
                    str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(inserted), "-map", "0:a:0",
                    "-ar", str(profile.audio_rate), "-ac", str(profile.audio_channels),
                    *self._audio_codec_args(extension, profile.audio_bitrate), str(middle),
                ],
                "Smart Insert: compatibilizando áudio inserido",
                step,
                4,
                self._get_duration_only(inserted),
            )
            pieces.append(middle)
            main_duration = self._get_duration_only(main)
            if insertion < main_duration - 0.001:
                step += 1
                right = work_dir / f"{len(pieces):03d}{extension}"
                self._execute(
                    [str(self._ffmpeg()), "-hide_banner", "-y", "-ss", self._fmt_seconds(insertion), "-i", str(main), "-map", "0:a:0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(right)],
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
            "\n".join(f"file '{str(piece.resolve()).replace(chr(92), '/')}'" for piece in pieces),
            encoding="utf-8",
        )
        try:
            self._execute(
                [str(self._ffmpeg()), "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", "-avoid_negative_ts", "make_zero", str(output)],
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
    ) -> list[str]:
        main_end = profile.duration
        inserted_duration = self._get_duration_only(inserted)
        neighbors = [inserted_duration]
        if insertion > 0:
            neighbors.append(insertion)
        if main_end > insertion:
            neighbors.append(main_end - insertion)
        effective = min(transition_seconds, max(0.0, min(neighbors) / 2 if neighbors else 0.0))
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
            filters.append(f"[0:a]atrim=start=0:end={self._fmt_seconds(insertion)},{normalize}{fade_out},asetpts=PTS-STARTPTS[a0]")
            labels.append("a0")
        inserted_fades = ""
        if use_fade and has_left:
            inserted_fades += f",afade=t=in:st=0:d={self._fmt_seconds(effective)}"
        if use_fade and has_right:
            inserted_fades += f",afade=t=out:st={self._fmt_seconds(max(0.0, inserted_duration - effective))}:d={self._fmt_seconds(effective)}"
        filters.append(f"[1:a]atrim=start=0:end={self._fmt_seconds(inserted_duration)},{normalize}{inserted_fades},asetpts=PTS-STARTPTS[a1]")
        labels.append("a1")
        if has_right:
            fade_in = f",afade=t=in:st=0:d={self._fmt_seconds(effective)}" if use_fade else ""
            filters.append(f"[0:a]atrim=start={self._fmt_seconds(insertion)}:end={self._fmt_seconds(main_end)},{normalize}{fade_in},asetpts=PTS-STARTPTS[a2]")
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
        return [
            str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(main), "-i", str(inserted),
            "-filter_complex", ";".join(filters), "-map", "[aout]", "-vn",
            "-ar", str(profile.audio_rate), "-ac", str(profile.audio_channels),
            *self._audio_codec_args("m4a", profile.audio_bitrate), "-map_metadata", "-1", str(output),
        ]

    def _clean_worker(self) -> None:
        source = self.clean_input
        if not source or not source.exists():
            raise RuntimeError("Selecione o áudio para limpar")
        filter_value = "afftdn=nf=-25" if self.clean_mode_var.get() == "equilibrado" else "anlmdn=s=0.00003:p=0.002:r=0.002"
        output = self._safe_output(self.output_dir, f"{source.stem}_limpo", ".wav")
        command = [str(self._ffmpeg()), "-hide_banner", "-y", "-i", str(source), "-vn", "-map", "0:a:0", "-af", filter_value, "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", "-f", "wav", str(output)]
        self._execute(command, "Limpando áudio", 1, 1)


def settings_path() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


def transcription_servers_path() -> Path:
    path = settings_path().parent / "Servidores" / "modelos_de_transcricao.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        current = path.read_text(encoding="utf-8") if path.exists() else DEFAULT_TRANSCRIPTION_SERVER_CONTENT
        normalized = normalize_transcription_servers_content(current)
        if not path.exists() or normalized != current:
            write_transcription_servers_content(path, normalized)
    except Exception:
        if not path.exists():
            path.write_text(normalize_transcription_servers_content(DEFAULT_TRANSCRIPTION_SERVER_CONTENT), encoding="utf-8")
    return path


def parse_transcription_server_line(raw_line: str) -> dict | None:
    trimmed = raw_line.strip()
    if not trimmed or trimmed.startswith("#"):
        return None
    selected = trimmed.startswith("*")
    line = trimmed.removeprefix("*").lstrip() if selected else trimmed
    fields = [field.strip() for field in re.split(r"\t{2,}", line)]
    if len(fields) < 3 or not fields[0] or not fields[1]:
        return None
    try:
        parameters = json.loads("{" + ",".join(field for field in fields[2:] if field) + "}")
    except json.JSONDecodeError:
        return None
    if not isinstance(parameters, dict) or "model" not in parameters:
        return None
    return {
        "name": fields[0],
        "url": fields[1],
        "parameters": parameters,
        "selected": selected,
    }


def normalize_transcription_servers_content(content: str) -> str:
    lines = content.splitlines()
    if TRANSCRIPTION_SERVER_MIGRATION_MARKER not in content:
        has_taguai = any(
            (server := parse_transcription_server_line(raw_line))
            and server["name"].casefold() in {"taguai-speech", "servidor"}
            for raw_line in lines
        )
        if not has_taguai:
            lines.append(TAGUAI_TRANSCRIPTION_SERVER_CONTENT)
        lines.append(TRANSCRIPTION_SERVER_MIGRATION_MARKER)

    if AVARE_PLUS_AR_MIGRATION_MARKER not in content:
        for index, raw_line in enumerate(lines):
            server = parse_transcription_server_line(raw_line)
            if not server or server["name"].casefold() not in {"avare-speech", "avare"}:
                continue
            lines[index] = re.sub(
                r'("model"\s*:\s*)"(?:\\.|[^"\\])*"',
                lambda match: match.group(1) + json.dumps(
                    "granite-speech-4.1-2b-plus-ar",
                    ensure_ascii=False,
                ),
                raw_line,
                count=1,
            )
            break
        lines.append(AVARE_PLUS_AR_MIGRATION_MARKER)

    if not any((server := parse_transcription_server_line(raw_line)) and server["selected"] for raw_line in lines):
        for index, raw_line in enumerate(lines):
            if parse_transcription_server_line(raw_line):
                leading_space = raw_line[: len(raw_line) - len(raw_line.lstrip())]
                lines[index] = leading_space + "*" + raw_line.lstrip().removeprefix("*").lstrip()
                break
    return "\n".join(lines).strip() + "\n"


def write_transcription_servers_content(path: Path, content: str) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def read_transcription_servers() -> list[dict]:
    legacy_path = settings_path().parent / "Servidores" / "modelos_de_transcricao.txt"
    try:
        legacy_path.unlink(missing_ok=True)
    except OSError:
        pass
    lines = DEFAULT_TRANSCRIPTION_SERVER_CONTENT.splitlines()
    servers = []
    for raw_line in lines:
        server = parse_transcription_server_line(raw_line)
        if server:
            servers.append(server)
    if not servers:
        servers = [
            {
                "name": "avare",
                "url": "http://avare:8100/transcribe",
                "parameters": {"model": "granite-speech-4.1-2b-plus-ar"},
                "selected": True,
            }
        ]
    grok_selected = any(server["name"] == GROK_API_NAME for server in servers if server["selected"])
    deepgram_selected = any(server["name"] == DEEPGRAM_API_NAME for server in servers if server["selected"])
    assemblyai_selected = any(server["name"] == ASSEMBLYAI_API_NAME for server in servers if server["selected"])
    elevenlabs_selected = any(server["name"] == ELEVENLABS_API_NAME for server in servers if server["selected"])
    api_selected = grok_selected or deepgram_selected or assemblyai_selected or elevenlabs_selected
    plain_servers = [
        {**server, "selected": server["selected"] and not api_selected}
        for server in servers
        if server["name"] not in (GROK_API_NAME, DEEPGRAM_API_NAME, ASSEMBLYAI_API_NAME, ELEVENLABS_API_NAME)
    ]
    return plain_servers + [
        {
            "name": GROK_API_NAME,
            "url": GROK_STT_URL,
            "parameters": {"model": "Speech to Text"},
            "selected": grok_selected,
            "is_grok_api": True,
        },
        {
            "name": DEEPGRAM_API_NAME,
            "url": DEEPGRAM_STT_URL,
            "parameters": {"model": "Nova 3"},
            "selected": deepgram_selected,
            "is_deepgram_api": True,
        },
        {
            "name": ASSEMBLYAI_API_NAME,
            "url": ASSEMBLYAI_SYNC_URL,
            "parameters": {"model": "Universal-3.5 Pro"},
            "selected": assemblyai_selected,
            "is_assemblyai_api": True,
        },
        {
            "name": ELEVENLABS_API_NAME,
            "url": ELEVENLABS_STT_URL,
            "parameters": {"model": "scribe_v2_realtime"},
            "selected": elevenlabs_selected,
            "is_elevenlabs_api": True,
        },
    ]


def add_transcription_server(name: str, url: str, model: str) -> tuple[bool, str]:
    clean_name, clean_url, clean_model = name.strip(), url.strip(), model.strip()
    if not clean_name or not clean_url or not clean_model:
        return False, "Preencha o nome, a URL e o modelo."
    if any("\t" in value or "\n" in value or "\r" in value for value in (clean_name, clean_url, clean_model)):
        return False, "Nome, URL e modelo não podem conter tabulações ou quebras de linha."
    if not clean_url.startswith(("http://", "https://")):
        return False, "A URL deve começar com http:// ou https://."
    if any(server["name"].casefold() == clean_name.casefold() for server in read_transcription_servers()):
        return False, "Já existe um servidor com esse nome."

    path = transcription_servers_path()
    line = f'{clean_name}\t\t{clean_url}\t\t"model": {json.dumps(clean_model, ensure_ascii=False)}'
    content = path.read_text(encoding="utf-8").rstrip() + "\n" + line + "\n"
    write_transcription_servers_content(path, normalize_transcription_servers_content(content))
    return True, ""


def remove_transcription_server(name: str) -> bool:
    if name in (GROK_API_NAME, DEEPGRAM_API_NAME, ASSEMBLYAI_API_NAME, ELEVENLABS_API_NAME):
        return False
    path = transcription_servers_path()
    removed = False
    remaining_lines = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        server = parse_transcription_server_line(raw_line)
        if server and server["name"].casefold() == name.casefold():
            removed = True
            continue
        remaining_lines.append(raw_line)
    if removed:
        write_transcription_servers_content(path, normalize_transcription_servers_content("\n".join(remaining_lines)))
    return removed


def text_models_path() -> Path:
    path = settings_path().parent / "Servidores" / "modelos_de_texto.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        current = path.read_text(encoding="utf-8") if path.exists() else DEFAULT_TEXT_MODEL_SERVER_CONTENT
        normalized = normalize_text_models_content(current)
        if not path.exists() or normalized != current:
            write_transcription_servers_content(path, normalized)
    except Exception:
        if not path.exists():
            path.write_text(normalize_text_models_content(DEFAULT_TEXT_MODEL_SERVER_CONTENT), encoding="utf-8")
    return path


def normalize_text_models_content(content: str) -> str:
    legacy_grok_model = "grok-4." + "3"
    lines = [
        line.replace(f'"model": "{legacy_grok_model}"', '"model": "grok-4.6"')
        .replace('"max_tokens": 5000', '"max_tokens": 10000')
        for line in content.splitlines()
    ]
    lines = [
        raw_line
        for raw_line in lines
        if not (
            (server := parse_transcription_server_line(raw_line))
            and server["name"].casefold() in {"avare-grok", "taguai-grok", "ia-proxy"}
        )
    ]
    if not any((server := parse_transcription_server_line(raw_line)) and server["selected"] for raw_line in lines):
        for index, raw_line in enumerate(lines):
            if parse_transcription_server_line(raw_line):
                leading_space = raw_line[: len(raw_line) - len(raw_line.lstrip())]
                lines[index] = leading_space + "*" + raw_line.lstrip().removeprefix("*").lstrip()
                break
    return "\n".join(lines).strip() + "\n"


def read_text_models() -> list[dict]:
    legacy_path = settings_path().parent / "Servidores" / "modelos_de_texto.txt"
    try:
        legacy_path.unlink(missing_ok=True)
    except OSError:
        pass
    models = [
        {
            "name": name,
            "url": config["url"],
            "parameters": json.loads(json.dumps(config["parameters"], ensure_ascii=False)),
            "selected": False,
        }
        for name, config in TEXT_MODEL_CONFIGS.items()
    ]
    regular_models = [
        {
            **model,
            "selected": model["selected"],
            "is_grok_api": False,
            "is_deepseek_api": False,
            "is_xai_proxy": False,
        }
        for model in models
    ]
    integrated_models = [
        {
            "name": IA_PROXY_NAME,
            "url": IA_PROXY_PRIMARY_URL,
            "fallback_url": IA_PROXY_FALLBACK_URL,
            "parameters": {
                "model": GROK_TEXT_NAME,
                "temperature": 0.0,
                "max_output_tokens": 10000,
                "reasoning": {"effort": "low"},
            },
            "selected": True,
            "provider": "xai",
            "is_grok_api": False,
            "is_deepseek_api": False,
            "is_xai_proxy": True,
        },
        {
            "name": GROK_TEXT_NAME,
            "url": GROK_TEXT_URL,
            "parameters": {
                "model": GROK_TEXT_NAME,
                "temperature": 0.0,
                "max_output_tokens": 10000,
                "reasoning": {"effort": "low"},
            },
            "selected": False,
            "provider": "xai",
            "is_grok_api": True,
            "is_deepseek_api": False,
            "is_xai_proxy": False,
        },
        {
            "name": GROK_NON_REASONING_TEXT_NAME,
            "url": GROK_TEXT_URL,
            "parameters": {
                "model": GROK_NON_REASONING_TEXT_NAME,
                "temperature": 0.0,
                "max_output_tokens": 10000,
            },
            "selected": False,
            "provider": "xai",
            "is_grok_api": True,
            "is_deepseek_api": False,
            "is_xai_proxy": False,
        },
        {
            "name": DEEPSEEK_TEXT_NAME,
            "url": DEEPSEEK_TEXT_URL,
            "parameters": {
                "model": DEEPSEEK_TEXT_NAME,
                "temperature": 0.0,
                "max_tokens": 10000,
                "reasoning_effort": "none",
            },
            "selected": False,
            "provider": "deepseek",
            "is_grok_api": False,
            "is_deepseek_api": True,
            "is_xai_proxy": False,
        },
    ]
    return integrated_models + regular_models


def selected_text_model_config(settings: dict, name_key: str = "text_model") -> dict:
    models = read_text_models()
    name = settings.get(name_key) or settings.get("text_model")
    return (
        next((model for model in models if model["name"] == name), None)
        or next((model for model in models if model["selected"]), None)
        or models[0]
    )


def add_text_model(name: str, url: str, model: str) -> tuple[bool, str]:
    clean_name, clean_url, clean_model = name.strip(), url.strip(), model.strip()
    if not clean_name or not clean_url or not clean_model:
        return False, "Preencha o nome, a URL e o modelo."
    if any("\t" in value or "\n" in value or "\r" in value for value in (clean_name, clean_url, clean_model)):
        return False, "Nome, URL e modelo não podem conter tabulações ou quebras de linha."
    if not clean_url.startswith(("http://", "https://")):
        return False, "A URL deve começar com http:// ou https://."
    if any(item["name"].casefold() == clean_name.casefold() for item in read_text_models()):
        return False, "Já existe um modelo de texto com esse nome."
    path = text_models_path()
    line = f'{clean_name}\t\t{clean_url}\t\t"model": {json.dumps(clean_model, ensure_ascii=False)}'
    write_transcription_servers_content(
        path,
        normalize_text_models_content(path.read_text(encoding="utf-8").rstrip() + "\n" + line + "\n"),
    )
    return True, ""


def remove_text_model(name: str) -> bool:
    if name == IA_PROXY_NAME or name in GROK_TEXT_API_NAMES or name in DEEPSEEK_API_NAMES:
        return False
    path = text_models_path()
    removed = False
    remaining = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        item = parse_transcription_server_line(raw_line)
        if item and item["name"].casefold() == name.casefold():
            removed = True
            continue
        remaining.append(raw_line)
    if removed:
        write_transcription_servers_content(path, normalize_text_models_content("\n".join(remaining)))
    return removed


def selected_transcription_server(settings: dict) -> dict:
    servers = read_transcription_servers()
    name = settings.get("transcription_server")
    return (
        next((server for server in servers if server["name"] == name), None)
        or next((server for server in servers if server["selected"]), None)
        or servers[0]
    )


def transcription_server_label(server: dict) -> str:
    if server["name"] == GROK_API_NAME:
        return GROK_API_NAME
    return f"{server['name']} ({server['parameters'].get('model', 'modelo não informado')})"


def load_settings() -> dict:
    data = DEFAULT_SETTINGS.copy()
    path = settings_path()
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update({key: loaded[key] for key in data.keys() & loaded.keys()})
        except Exception:
            pass
    return normalize_settings(data)


def normalize_settings(data: dict) -> dict:
    clean = DEFAULT_SETTINGS.copy()
    clean["convert_parallel"] = max(1, clamp_int(data.get("convert_parallel"), 1, 256, DEFAULT_SETTINGS["convert_parallel"]))
    clean["transcribe_parallel"] = max(1, clamp_int(data.get("transcribe_parallel"), 1, 256, DEFAULT_SETTINGS["transcribe_parallel"]))
    clean["grok_chunk_ms"] = clamp_int(data.get("grok_chunk_ms"), 20, 2000, DEFAULT_SETTINGS["grok_chunk_ms"])
    for language_key, fallback in {
        "deepgram_language_mode": "pt-BR",
        "assemblyai_language_mode": "pt",
        "elevenlabs_language_mode": "pt",
        "grok_language_mode": "pt",
    }.items():
        value = str(data.get(language_key) or "").strip()
        clean[language_key] = value or fallback
    for custom_key in (
        "deepgram_language_custom",
        "assemblyai_language_custom",
        "elevenlabs_language_custom",
        "grok_language_custom",
    ):
        clean[custom_key] = str(data.get(custom_key) or "").strip()
    rest_value = data.get("grok_rest_requests", DEFAULT_SETTINGS["grok_rest_requests"])
    clean["grok_rest_requests"] = (
        rest_value
        if isinstance(rest_value, bool)
        else str(rest_value).strip().casefold() in {"1", "true", "yes", "on"}
    )
    server_names = {server["name"] for server in read_transcription_servers()}
    transcription_server = str(
        data.get("transcription_server") or DEFAULT_SETTINGS["transcription_server"]
    )
    transcription_server = {
        "Avare-speech": "avare",
        "Taguai-speech": "servidor",
        "Grok (API)": GROK_API_NAME,
    }.get(transcription_server, transcription_server)
    clean["transcription_server"] = (
        transcription_server
        if transcription_server in server_names
        else selected_transcription_server({})["name"]
    )
    transcription_server_2 = str(data.get("transcription_server_2") or "")
    transcription_server_2 = {
        "Avare-speech": "avare",
        "Taguai-speech": "servidor",
        "Grok (API)": GROK_API_NAME,
    }.get(transcription_server_2, transcription_server_2)
    clean["transcription_server_2"] = (
        transcription_server_2
        if transcription_server_2 in server_names
        and transcription_server_2 != clean["transcription_server"]
        else ""
    )
    text_model_names = {model["name"] for model in read_text_models()}

    def proxy_model(value, provider):
        candidate = str(value or "").strip()
        if candidate in {GROK_TEXT_NAME, GROK_NON_REASONING_TEXT_NAME, DEEPSEEK_TEXT_NAME}:
            return candidate
        return DEEPSEEK_TEXT_NAME if str(provider or "").casefold() == "deepseek" else GROK_TEXT_NAME

    def normalize_reasoning(value, model_name):
        candidate = str(value or "").casefold()
        if not model_name:
            return ""
        if model_name == GROK_NON_REASONING_TEXT_NAME:
            return ""
        if model_name == DEEPSEEK_TEXT_NAME:
            return candidate if candidate in {"none", "low", "high", "max"} else "none"
        return candidate if candidate in {"low", "medium", "high", "xhigh"} else "low"

    text_model = str(data.get("text_model") or DEFAULT_SETTINGS["text_model"])
    legacy_text_model = text_model.casefold()
    if legacy_text_model in {"avare-grok", "taguai-grok", "grok (api)"}:
        text_model = IA_PROXY_NAME if "api" not in legacy_text_model else GROK_TEXT_NAME
    elif legacy_text_model in {GROK_NON_REASONING_LEGACY_NAME, GROK_NON_REASONING_TEXT_NAME}:
        text_model = GROK_NON_REASONING_TEXT_NAME
    elif legacy_text_model.startswith("grok-4."):
        text_model = GROK_TEXT_NAME
    elif legacy_text_model.startswith("deepseek-v4-") or legacy_text_model.startswith("deepseek v4"):
        text_model = DEEPSEEK_TEXT_NAME
    clean["text_model"] = text_model if text_model in text_model_names else selected_text_model_config({})["name"]

    text_model_2 = str(data.get("text_model_2") or "")
    if text_model_2.casefold() in {GROK_NON_REASONING_LEGACY_NAME, GROK_NON_REASONING_TEXT_NAME}:
        text_model_2 = GROK_NON_REASONING_TEXT_NAME
    elif text_model_2.casefold().startswith("grok-4."):
        text_model_2 = GROK_TEXT_NAME
    elif text_model_2.casefold().startswith("deepseek-v4-") or text_model_2.casefold().startswith("deepseek v4"):
        text_model_2 = DEEPSEEK_TEXT_NAME
    clean["text_model_2"] = (
        text_model_2
        if text_model_2 in text_model_names
        and (text_model_2 != clean["text_model"] or text_model_2 == IA_PROXY_NAME)
        else ""
    )

    proxy_model_1 = proxy_model(
        data.get("ia_proxy_model"), data.get("ia_proxy_provider") or DEFAULT_SETTINGS["ia_proxy_provider"]
    )
    proxy_model_2 = proxy_model(
        data.get("ia_proxy_model_2"), data.get("ia_proxy_provider_2") or DEFAULT_SETTINGS["ia_proxy_provider_2"]
    )
    clean["ia_proxy_model"] = proxy_model_1
    clean["ia_proxy_model_2"] = proxy_model_2
    clean["ia_proxy_provider"] = "deepseek" if proxy_model_1 == DEEPSEEK_TEXT_NAME else "grok"
    clean["ia_proxy_provider_2"] = "deepseek" if proxy_model_2 == DEEPSEEK_TEXT_NAME else "grok"
    if (
        clean["text_model"] == IA_PROXY_NAME
        and clean["text_model_2"] == IA_PROXY_NAME
        and clean["ia_proxy_model"] == clean["ia_proxy_model_2"]
    ):
        clean["text_model_2"] = ""
    actual_model = proxy_model_1 if clean["text_model"] == IA_PROXY_NAME else clean["text_model"]
    actual_model_2 = proxy_model_2 if clean["text_model_2"] == IA_PROXY_NAME else clean["text_model_2"]
    clean["text_reasoning"] = normalize_reasoning(data.get("text_reasoning"), actual_model)
    clean["text_reasoning_2"] = normalize_reasoning(data.get("text_reasoning_2"), actual_model_2)
    extraction = str(data.get("parts_extraction") or DEFAULT_SETTINGS["parts_extraction"])
    clean["parts_extraction"] = (
        extraction if extraction in PARTS_EXTRACTION_LABELS else DEFAULT_SETTINGS["parts_extraction"]
    )
    parts_model = str(data.get("parts_model") or DEFAULT_SETTINGS["parts_model"])
    clean["parts_model"] = (
        parts_model
        if parts_model in {
            IA_PROXY_NAME,
            GROK_NON_REASONING_TEXT_NAME,
            GROK_TEXT_NAME,
            DEEPSEEK_TEXT_NAME,
        }
        else DEFAULT_SETTINGS["parts_model"]
    )
    parts_proxy_provider = str(
        data.get("parts_proxy_provider") or DEFAULT_SETTINGS["parts_proxy_provider"]
    ).casefold()
    clean["parts_proxy_model"] = proxy_model(
        data.get("parts_proxy_model"), parts_proxy_provider
    )
    clean["parts_proxy_provider"] = (
        "deepseek"
        if clean["parts_proxy_model"] == DEEPSEEK_TEXT_NAME
        else "grok"
    )
    clean["grok_api_key"] = str(data.get("grok_api_key") or "").strip()
    clean["deepgram_api_key"] = str(data.get("deepgram_api_key") or "").strip()
    clean["deepgram_keyterms"] = ", ".join(
        term.strip()
        for term in str(data.get("deepgram_keyterms") or "").replace("\n", ",").split(",")
        if term.strip()
    )
    clean["assemblyai_api_key"] = str(data.get("assemblyai_api_key") or "").strip()
    clean["elevenlabs_api_key"] = str(data.get("elevenlabs_api_key") or "").strip()
    clean["deepseek_api_key"] = str(data.get("deepseek_api_key") or "").strip()
    clean["imei_api_key"] = str(data.get("imei_api_key") or "").strip()
    clean["police_name"] = str(data.get("police_name") or "").strip()
    clean["police_role"] = str(data.get("police_role") or "").strip()
    clean["police_station"] = str(data.get("police_station") or "").strip()
    clean["police_delegate"] = str(data.get("police_delegate") or "").strip()
    clean["police_city"] = str(data.get("police_city") or "").strip()
    if clean["text_model"] in GROK_TEXT_API_NAMES and not plausible_xai_api_key(clean["grok_api_key"]):
        clean["text_model"] = IA_PROXY_NAME
    if clean["text_model_2"] in GROK_TEXT_API_NAMES and not plausible_xai_api_key(clean["grok_api_key"]):
        clean["text_model_2"] = ""
    if clean["text_model"] in DEEPSEEK_API_NAMES and not plausible_deepseek_api_key(clean["deepseek_api_key"]):
        clean["text_model"] = IA_PROXY_NAME
    if clean["text_model_2"] in DEEPSEEK_API_NAMES and not plausible_deepseek_api_key(clean["deepseek_api_key"]):
        clean["text_model_2"] = ""
    if clean["parts_model"] in GROK_TEXT_API_NAMES and not plausible_xai_api_key(clean["grok_api_key"]):
        clean["parts_model"] = IA_PROXY_NAME
    if clean["parts_model"] == DEEPSEEK_TEXT_NAME and not plausible_deepseek_api_key(clean["deepseek_api_key"]):
        clean["parts_model"] = IA_PROXY_NAME
    # Modelos por tarefa (histórico, oitiva e qualificação) e raciocínio das
    # partes: preservados com fallback para as chaves gerais de texto.
    task_preserved: dict[str, object] = {}
    for task, keys in TEXT_TASK_KEYS.items():
        suffixes = ("", "_2") if task in ("history", "statement") else ("",)
        for suffix in suffixes:
            model_key, reasoning_key, proxy_key = (key + suffix for key in keys)
            raw_model = str(data.get(model_key) or "")
            fallback_model = str(clean.get("text_model" + suffix) or clean["text_model"])
            model_value = raw_model if raw_model in text_model_names else fallback_model
            task_preserved[model_key] = model_value
            task_preserved[proxy_key] = proxy_model(data.get(proxy_key), "grok")
            effective_model = (
                task_preserved[proxy_key]
                if model_value == IA_PROXY_NAME
                else model_value
            )
            task_preserved[reasoning_key] = normalize_reasoning(
                data.get(reasoning_key), effective_model
            )
    clean.update(task_preserved)
    clean["parts_reasoning"] = normalize_reasoning(
        data.get("parts_reasoning"),
        clean["parts_proxy_model"] if clean["parts_model"] == IA_PROXY_NAME else clean["parts_model"],
    )
    # VAD removido
    return clean


def settings_for_text_model(settings: dict, model_name: str, secondary: bool = False, task: str | None = None) -> dict:
    selected = dict(settings)
    if task:
        model_key, reasoning_key, proxy_key = TEXT_TASK_KEYS[task]
        suffix = "_2" if secondary else ""
        selected[model_key + suffix] = model_name
        if secondary:
            selected[reasoning_key + suffix] = str(settings.get(reasoning_key + "_2") or "low")
            selected[proxy_key + suffix] = str(
                settings.get(proxy_key + "_2") or settings.get(proxy_key) or GROK_TEXT_NAME
            )
        return selected
    selected["text_model"] = model_name
    if secondary:
        selected["text_reasoning"] = str(settings.get("text_reasoning_2") or "low")
        selected["ia_proxy_provider"] = str(settings.get("ia_proxy_provider_2") or "grok")
        selected["ia_proxy_model"] = str(
            settings.get("ia_proxy_model_2") or settings.get("ia_proxy_model") or GROK_TEXT_NAME
        )
    return selected


def selected_parts_model(settings: dict) -> dict:
    model_name = str(settings.get("parts_model") or IA_PROXY_NAME)
    selected = dict(settings)
    selected["text_model"] = model_name
    proxy_model = str(
        settings.get("parts_proxy_model")
        or (
            DEEPSEEK_TEXT_NAME
            if str(settings.get("parts_proxy_provider") or "grok").casefold() == "deepseek"
            else GROK_TEXT_NAME
        )
    )
    uses_deepseek = model_name == DEEPSEEK_TEXT_NAME or (
        model_name == IA_PROXY_NAME and proxy_model == DEEPSEEK_TEXT_NAME
    )
    if uses_deepseek:
        selected["text_reasoning"] = str(settings.get("parts_reasoning") or "none")
    else:
        selected["text_reasoning"] = str(settings.get("parts_reasoning") or "low")
    if model_name == IA_PROXY_NAME:
        selected["ia_proxy_provider"] = "deepseek" if uses_deepseek else "grok"
        selected["ia_proxy_model"] = proxy_model
    return selected_text_model(selected)


def save_settings(data: dict) -> dict:
    clean = normalize_settings(data)
    settings_path().write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean


def clamp_int(value, minimum: int, maximum: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, number))


def plausible_xai_api_key(value: str) -> bool:
    key = value.strip()
    return len(key) == 84 and key[:4].casefold() == "xai-"


def plausible_deepseek_api_key(value: str) -> bool:
    key = value.strip()
    return len(key) == 35 and key.startswith("sk-")


def imei_history_path() -> Path:
    return settings_path().parent / IMEI_HISTORY_FILE


def compute_imei_luhn_digit(number_only_digits: str) -> int:
    digits = [int(char) for char in number_only_digits if char.isdigit()]
    total = 0
    length = len(digits)
    for index in range(length - 1, -1, -1):
        digit = digits[index]
        pos_from_right_if_check_appended = (length - index) + 1
        if pos_from_right_if_check_appended % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return (10 - (total % 10)) % 10


def read_imei_history_records() -> list[dict]:
    path = imei_history_path()
    if not path.exists() or path.stat().st_size == 0:
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def append_imei_history(record: dict):
    path = imei_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def find_imei_history_record(imei: str) -> dict | None:
    for record in reversed(read_imei_history_records()):
        if str(record.get("imei") or "") == imei:
            return record
    return None


def format_imei_model(record: dict) -> str:
    brand = str(record.get("brand") or "—")
    model = str(record.get("model") or "—")
    name = str(record.get("name") or "—")
    return f"Marca: {brand}\nModelo: {model} ({name})"


def format_imei_time(timestamp_ms) -> str:
    try:
        value = int(timestamp_ms)
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        return "Data indisponível"
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(value / 1000))


def format_imei_history_item(record: dict) -> str:
    return (
        f"{format_imei_time(record.get('time', 0))}\n"
        f"IMEI: {record.get('imei', '')}\n"
        f"{format_imei_model(record)}"
    )


def fetch_imei_info_record(imei: str, api_key: str) -> dict:
    url = (
        "https://alpha.imeicheck.com/api/free_with_key/modelBrandName"
        f"?key={quote(api_key)}&imei={quote(imei)}&format=json"
    )
    parsed = urlparse(url)
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    conn = connection_cls(parsed.netloc, timeout=30)
    try:
        conn.request("GET", path, headers={"accept": "application/json"})
        response = conn.getresponse()
        body = response.read()
    except (OSError, socket.timeout) as exc:
        raise ConnectionError("Cheque sua conexão") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass
    try:
        payload = json.loads(body.decode("utf-8", errors="replace") or "{}")
    except Exception as exc:
        raise ValueError("Erro ao processar resposta") from exc
    if not isinstance(payload, dict) or payload.get("status") != "succes":
        raise LookupError("Modelo não encontrado")
    obj = payload.get("object")
    if not isinstance(obj, dict):
        raise LookupError("Modelo não encontrado")
    return {
        "time": int(time.time() * 1000),
        "imei": imei,
        "brand": obj.get("brand") or "—",
        "model": obj.get("model") or "—",
        "name": obj.get("name") or "—",
    }


def transcribe_url(settings: dict) -> str:
    url = selected_transcription_server(settings)["url"]
    if is_deepgram_transcription(settings):
        url = f"{url}?{deepgram_query_string(settings)}"
    return url


def probe_duration_ms(path: Path) -> int:
    """Duração real do arquivo em ms via ffmpeg (0 se não for possível medir)."""
    try:
        ffmpeg = app_base_dir() / "ffmpeg.exe"
        if not ffmpeg.exists():
            return 0
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-i", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr + result.stdout)
        if not match:
            return 0
        seconds = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
        return int(seconds * 1000)
    except Exception:
        return 0


def deepgram_keyterms_list(settings: dict) -> list[str]:
    """Termos de reforço do Deepgram (keyterm prompting), separados por vírgula."""
    raw = str(settings.get("deepgram_keyterms") or "")
    return [term.strip() for term in raw.replace("\n", ",").split(",") if term.strip()]


def deepgram_query_string(settings: dict, language: str | None = None, diarize: bool = False) -> str:
    """Parâmetros do Deepgram Nova 3 (REST e WS) — espelho do app Android."""
    if language is None:
        language = stt_provider_rules.deepgram_language_param(settings)
    params = ["model=nova-3", f"language={language}", "smart_format=true", "punctuate=true"]
    if diarize or settings.get("diarize") or settings.get("grok_diarize"):
        diarize_param = stt_provider_rules.deepgram_diarize_query(True)
        if diarize_param:
            params.append(diarize_param)
    for term in deepgram_keyterms_list(settings):
        params.append(f"keyterm={urllib.parse.quote(term)}")
    return "&".join(params)


def is_grok_transcription(settings: dict) -> bool:
    return selected_transcription_server(settings).get("is_grok_api", False)


def is_deepgram_transcription(settings: dict) -> bool:
    return selected_transcription_server(settings).get("is_deepgram_api", False)


def is_assemblyai_transcription(settings: dict) -> bool:
    return selected_transcription_server(settings).get("is_assemblyai_api", False)


def is_elevenlabs_transcription(settings: dict) -> bool:
    return selected_transcription_server(settings).get("is_elevenlabs_api", False)


def plausible_elevenlabs_api_key(value: str) -> bool:
    key = (value or "").strip()
    return 20 <= len(key) <= 64 and all(
        char.isalnum() or char in "-_" for char in key
    )


def plausible_assemblyai_api_key(value: str) -> bool:
    key = (value or "").strip()
    return 32 <= len(key) <= 64 and all(
        char in "0123456789abcdefABCDEF" for char in key
    )


def settings_for_transcription_server(settings: dict, server_name: str) -> dict:
    selected = settings.copy()
    selected["transcription_server"] = server_name
    return selected


def transcription_form_fields(settings: dict) -> dict:
    diarize_checked = bool(settings.get("diarize") or settings.get("grok_diarize"))
    if is_grok_transcription(settings):
        fields = {"format": "true", "filler_words": "false"}
        language = stt_provider_rules.grok_language_param(settings)
        if language:
            fields["language"] = language
        if stt_provider_rules.grok_rest_diarize(diarize_checked):
            fields["diarize"] = "true"
        return fields
    if is_deepgram_transcription(settings):
        # No fluxo Deepgram os parâmetros viajam na URL (raw body); o dict
        # fica vazio apenas para manter a assinatura do uploader.
        return {}
    if is_assemblyai_transcription(settings):
        fields: dict = {}
        detection, code = stt_provider_rules.assemblyai_rest_language(settings)
        if detection:
            fields["language_detection"] = "true"
        if code:
            fields["language_code"] = code
        speaker_labels, punctuate = stt_provider_rules.assemblyai_rest_diarize(diarize_checked)
        if speaker_labels:
            fields["speaker_labels"] = "true"
            fields["punctuate"] = "true"
        return fields
    if is_elevenlabs_transcription(settings):
        fields = {}
        code = stt_provider_rules.elevenlabs_rest_language_code(settings)
        if code:
            fields["language_code"] = code
        if stt_provider_rules.elevenlabs_rest_diarize(diarize_checked):
            fields["diarize"] = "true"
        return fields
    return selected_transcription_server(settings)["parameters"].copy()


def create_transcription_uploader(cancel_event: threading.Event, settings: dict) -> "GraniteUploader":
    if is_grok_transcription(settings):
        api_key = str(settings.get("grok_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Insira a chave API do Grok nas configurações.")
        return GraniteUploader(
            cancel_event,
            transcription_form_fields(settings),
            {"Authorization": f"Bearer {api_key}"},
            "file",
        )
    if is_deepgram_transcription(settings):
        api_key = str(settings.get("deepgram_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Insira a chave API do Deepgram nas configurações.")
        return GraniteUploader(
            cancel_event,
            {},
            {"Authorization": f"Token {api_key}"},
            "file",
            raw_body=True,
        )
    if is_assemblyai_transcription(settings):
        api_key = str(settings.get("assemblyai_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Insira a chave API da AssemblyAI nas configurações.")
        return GraniteUploader(
            cancel_event,
            {},
            {
                "Authorization": api_key,
                "X-AAI-Model": "u3-sync-pro",
            },
            "audio",
        )
    if is_elevenlabs_transcription(settings):
        api_key = str(settings.get("elevenlabs_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Insira a chave API da ElevenLabs nas configurações.")
        return GraniteUploader(
            cancel_event,
            {"model_id": "scribe_v2"},
            {"xi-api-key": api_key},
            "file",
        )
    return GraniteUploader(cancel_event, transcription_form_fields(settings))


def safe_stems(paths: list[Path]) -> dict[Path, str]:
    used: dict[str, int] = {}
    result: dict[Path, str] = {}
    for path in paths:
        base = path.stem.strip() or "audio"
        count = used.get(base.casefold(), 0) + 1
        used[base.casefold()] = count
        result[path] = base if count == 1 else f"{base}_{count}"
    return result


def format_bytes(size: int) -> str:
    value = float(max(0, size))
    units = ("B", "KB", "MB", "GB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def format_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}min {rest:.0f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}min"


def mode_label_from_value(mode: str) -> str:
    labels = {
        "ready": "Enviar pronto",
        "compact": "Enviar compactado",
        "as_is": "Enviar como está",
    }
    return labels.get(mode, "Enviar pronto")


@dataclass(frozen=True)
class ParsedTranscription:
    text: str
    timestamped_text: str = ""


def _format_transcription_timestamp(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _timed_entry(value) -> tuple[str, float, float] | None:
    if not isinstance(value, dict):
        return None
    text = next((str(value.get(key) or "").strip() for key in ("text", "word", "transcript") if str(value.get(key) or "").strip()), "")
    if not text:
        return None
    timestamp = value.get("timestamp")
    start = value.get("start", value.get("start_time"))
    end = value.get("end", value.get("end_time"))
    if isinstance(timestamp, list) and len(timestamp) >= 2:
        start = timestamp[0] if start is None else start
        end = timestamp[1] if end is None else end
    try:
        start_value = float(start)
        if end is None and value.get("duration") is not None:
            end = start_value + float(value["duration"])
        end_value = float(end)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(start_value) or not math.isfinite(end_value) or start_value < 0 or end_value < start_value:
        return None
    return text, start_value, end_value


def _timed_word_entries(items, total_duration=None) -> list[tuple[str, float, float]]:
    """Normalize Grok word timestamps, whose final word often lacks ``end``."""
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = next(
            (
                str(item.get(key) or "").strip()
                for key in ("text", "word", "transcript")
                if str(item.get(key) or "").strip()
            ),
            "",
        )
        if not text:
            continue
        timestamp = item.get("timestamp")
        start = item.get("start", item.get("start_time"))
        end = item.get("end", item.get("end_time"))
        if isinstance(timestamp, list) and timestamp:
            start = timestamp[0] if start is None else start
            if len(timestamp) >= 2:
                end = timestamp[1] if end is None else end
        try:
            start_value = float(start)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start_value) or start_value < 0:
            continue
        try:
            end_value = float(end) if end is not None else None
        except (TypeError, ValueError):
            end_value = None
        if end_value is not None and (
            not math.isfinite(end_value) or end_value < start_value
        ):
            end_value = None
        candidates.append([text, start_value, end_value])

    try:
        duration_value = float(total_duration)
        if not math.isfinite(duration_value) or duration_value < 0:
            duration_value = None
    except (TypeError, ValueError):
        duration_value = None

    normalized = []
    for index, (text, start_value, end_value) in enumerate(candidates):
        if end_value is None and index + 1 < len(candidates):
            next_start = candidates[index + 1][1]
            if next_start > start_value:
                end_value = next_start
        if end_value is None and duration_value is not None and duration_value > start_value:
            end_value = duration_value
        if end_value is None:
            end_value = start_value + max(0.08, min(0.6, len(text) * 0.08))
        normalized.append((text, start_value, max(start_value, end_value)))
    return normalized


def _timestamped_text_from_json(value) -> str:
    if isinstance(value, dict):
        for key, group_words in (("segments", False), ("words", True)):
            items = value.get(key)
            if not isinstance(items, list):
                continue
            entries = (
                _timed_word_entries(items, value.get("duration"))
                if group_words
                else [entry for item in items if (entry := _timed_entry(item))]
            )
            if not entries:
                continue
            if group_words:
                phrases: list[tuple[str, float, float]] = []
                words: list[str] = []
                phrase_start = entries[0][1]
                phrase_end = entries[0][2]
                for index, (word, _start, end) in enumerate(entries):
                    if words and not re.fullmatch(r"[,.;:!?]", word):
                        words.append(" ")
                    words.append(word)
                    phrase_end = end
                    if re.search(r"[.!?]$", word) or index == len(entries) - 1:
                        phrases.append(("".join(words).strip(), phrase_start, phrase_end))
                        words = []
                        if index < len(entries) - 1:
                            phrase_start = entries[index + 1][1]
                entries = phrases
            return "\n".join(
                f"[{_format_transcription_timestamp(start)} -> {_format_transcription_timestamp(end)}] {text}"
                for text, start, end in entries
            )
        direct = _timed_entry(value)
        if direct:
            text, start, end = direct
            return f"[{_format_transcription_timestamp(start)} -> {_format_transcription_timestamp(end)}] {text}"
        found = [_timestamped_text_from_json(item) for item in value.values()]
        return "\n".join(item for item in found if item)
    if isinstance(value, list):
        found = [_timestamped_text_from_json(item) for item in value]
        return "\n".join(item for item in found if item)
    return ""


def parse_transcription_response(raw: bytes) -> ParsedTranscription:
    text = raw.decode("utf-8-sig", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ParsedTranscription(text.strip())

    def collect(value):
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, list):
            found = []
            for item in value:
                found.extend(collect(item))
            return found
        if isinstance(value, dict):
            for key in ("text", "transcription", "transcript", "result", "output"):
                if key in value:
                    direct = collect(value[key])
                    if direct:
                        return direct
            for key in ("results", "files", "items", "data", "transcriptions"):
                if key in value:
                    nested = collect(value[key])
                    if nested:
                        return nested
            if "segments" in value:
                segments = collect(value["segments"])
                if segments:
                    return ["".join(segments)]
            found = []
            for item in value.values():
                found.extend(collect(item))
            return found
        return []

    pieces = collect(payload)
    if pieces:
        return ParsedTranscription(
            "\n".join(pieces).strip(),
            _timestamped_text_from_json(payload).strip(),
        )
    return ParsedTranscription(text.strip(), _timestamped_text_from_json(payload).strip())


def extract_text_from_response(raw: bytes) -> str:
    return parse_transcription_response(raw).text


def selected_text_model(
    settings: dict,
    *,
    model_key: str = "text_model",
    reasoning_key: str = "text_reasoning",
    proxy_key: str = "ia_proxy_model",
    model_fallback: str = "text_model",
    reasoning_fallback: str = "text_reasoning",
    proxy_fallback: str = "ia_proxy_model",
) -> dict:
    config = selected_text_model_config(settings, model_key)
    is_proxy = config["name"] == IA_PROXY_NAME
    request_model = (
        str(settings.get(proxy_key) or settings.get(proxy_fallback) or GROK_TEXT_NAME)
        if is_proxy
        else config["name"]
    )
    if request_model not in {GROK_TEXT_NAME, GROK_NON_REASONING_TEXT_NAME, DEEPSEEK_TEXT_NAME}:
        request_model = GROK_TEXT_NAME
    provider = "deepseek" if request_model == DEEPSEEK_TEXT_NAME else "xai"
    reasoning = str(settings.get(reasoning_key) or settings.get(reasoning_fallback) or "").casefold()
    if request_model == DEEPSEEK_TEXT_NAME:
        reasoning = reasoning if reasoning in {"none", "low", "high", "max"} else "none"
        parameters = {
            "model": DEEPSEEK_TEXT_NAME,
            "temperature": 0.0,
            "max_tokens": 10000,
            "reasoning_effort": reasoning,
        }
    elif request_model == GROK_NON_REASONING_TEXT_NAME:
        parameters = {
            "model": GROK_NON_REASONING_TEXT_NAME,
            "temperature": 0.0,
            "max_output_tokens": 10000,
        }
    else:
        reasoning = reasoning if reasoning in {"low", "medium", "high", "xhigh"} else "low"
        parameters = {
            "model": GROK_TEXT_NAME,
            "temperature": 0.0,
            "max_output_tokens": 10000,
            "reasoning": {"effort": reasoning},
        }
    is_grok_api = bool(config.get("is_grok_api", False)) and not is_proxy
    is_deepseek_api = bool(config.get("is_deepseek_api", False)) and not is_proxy
    return {
        "name": config["name"],
        "url": config["url"],
        "fallback_url": config.get("fallback_url"),
        "parameters": parameters,
        "provider": provider,
        "is_grok_api": is_grok_api,
        "is_deepseek_api": is_deepseek_api,
        "is_xai_proxy": is_proxy,
        "request_model": request_model,
        "api_key": str(
            settings.get("deepseek_api_key" if is_deepseek_api else "grok_api_key") or ""
        ).strip(),
    }


TEXT_TASK_KEYS = {
    "history": ("history_model", "history_reasoning", "history_proxy_model"),
    "statement": ("statement_model", "statement_reasoning", "statement_proxy_model"),
    "qualification": ("qualification_model", "qualification_reasoning", "qualification_proxy_model"),
}


def selected_text_model_for(settings: dict, task: str, *, secondary: bool = False) -> dict:
    """Resolve o modelo de uma tarefa específica (histórico, oitiva, qualificação).

    As configurações específicas têm precedência; quando ausentes (settings
    de versões anteriores), as configurações gerais de texto são usadas.
    """
    model_key, reasoning_key, proxy_key = TEXT_TASK_KEYS[task]
    suffix = "_2" if secondary else ""
    return selected_text_model(
        settings,
        model_key=model_key + suffix,
        reasoning_key=reasoning_key + suffix,
        proxy_key=proxy_key + suffix,
        model_fallback="text_model" + suffix,
        reasoning_fallback="text_reasoning" + suffix,
        proxy_fallback="ia_proxy_model" + suffix,
    )


def extract_text_model_output(raw: bytes) -> str:
    body = raw.decode("utf-8-sig", errors="replace")
    try:
        root = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Resposta JSON inválida: {body[:400]}") from exc
    for key in ("response", "output_text", "text"):
        value = root.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    choices = root.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
    output = root.get("output")
    if isinstance(output, list):
        preferred = list(reversed(output))
        for item in preferred:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message" and item.get("role") != "assistant":
                continue
            content = extract_content_text(item.get("content"))
            if content:
                return content
        for item in output:
            if isinstance(item, dict):
                content = extract_content_text(item.get("content"))
                if content:
                    return content
    raise RuntimeError("A resposta não contém output/content/text.")


def extract_content_text(content) -> str:
    if not isinstance(content, list):
        return ""
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type and item_type not in ("output_text", "text"):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def parse_qualification_json(
    raw_text: str,
    allowed_ids: list[str],
    field_order: tuple[tuple[str, str], ...],
) -> dict[str, str]:
    """Extrai e normaliza o JSON da IA, sem exibir campos não solicitados."""
    clean = str(raw_text or "").strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean).strip()
    start, end = clean.find("{"), clean.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("A IA não devolveu um JSON válido.")
    try:
        payload = json.loads(clean[start : end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"A IA devolveu um JSON inválido: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("A IA não devolveu um objeto JSON.")
    allowed = set(allowed_ids)
    normalized = {}
    for field_id, _label in field_order:
        if field_id not in allowed or field_id not in payload:
            continue
        value = payload[field_id]
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        value = str(value).strip()
        if value:
            normalized[field_id] = value
    known_ids = {field_id for field_id, _label in field_order}
    for field_id in allowed_ids:
        if field_id in known_ids or field_id not in payload:
            continue
        value = payload[field_id]
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        value = str(value).strip()
        if value:
            normalized[field_id] = value
    return normalized


def _qualification_age_in_years(value: str, today: date | None = None) -> int | None:
    """Calcula a idade completa a partir das datas mais comuns devolvidas pela IA."""
    raw = str(value or "").strip()
    match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", raw)
    if match:
        day, month, year = (int(item) for item in match.groups())
    else:
        match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw)
        if not match:
            return None
        year, month, day = (int(item) for item in match.groups())
    try:
        born = date(year, month, day)
    except ValueError:
        return None
    current = today or date.today()
    if born > current:
        return None
    return current.year - born.year - ((current.month, current.day) < (born.month, born.day))


def format_occurrence_qualification(
    raw_text: str,
    field_order: tuple[tuple[str, str], ...],
) -> str:
    """Converte o JSON fixo da Ocorrência no texto narrativo usado pelo policial."""
    fields = parse_qualification_json(raw_text, list(LIVE_QUALIFICATION_FIELD_IDS), field_order)
    absent_values = {
        "nao informado",
        "não informado",
        "nao encontrada",
        "não encontrada",
        "nao encontrado",
        "não encontrado",
        "nao disponivel",
        "não disponível",
        "n/a",
        "-",
    }
    fields = {
        field_id: value
        for field_id, value in fields.items()
        if str(value).strip().casefold() not in absent_values
    }
    parts: list[str] = []

    name = fields.get("nome", "").strip()
    if name:
        parts.append(name.upper())

    mother = fields.get("mae", "").strip()
    father = fields.get("pai", "").strip()
    if mother and father:
        parts.append(f"filho(a) de {mother} e {father}")
    elif mother:
        parts.append(f"filho(a) de {mother}")
    elif father:
        parts.append(f"filho(a) de {father}")

    age = _qualification_age_in_years(fields.get("nascimento", ""))
    if age is not None:
        parts.append(f"{age} anos")
    if fields.get("estado_civil"):
        parts.append(f"estado civil {fields['estado_civil'].strip()}")

    # Nacionalidade Brasileira é parte fixa do modelo solicitado para esta tela.
    parts.append("de nacionalidade Brasileira")
    if fields.get("naturalidade"):
        parts.append(f"natural de {fields['naturalidade'].strip()}")
    if fields.get("profissao"):
        parts.append(f"de profissão {fields['profissao'].strip()}")
    if fields.get("endereco"):
        parts.append(f"residente e domiciliado(a) à {fields['endereco'].strip()}")
    if fields.get("bairro"):
        parts.append(fields["bairro"].strip())
    if fields.get("cidade"):
        parts.append(f"na cidade de {fields['cidade'].strip()}")
    if fields.get("telefone"):
        parts.append(f"Telefone: {fields['telefone'].strip()}")

    return f"{', '.join(parts)}." if parts else ""


def format_qualification_fields(
    payload: dict[str, str],
    field_order: tuple[tuple[str, str], ...],
    selected_ids: set[str] | None = None,
) -> str:
    """Exibe os campos como uma única linha filtrável pelas checkboxes."""
    known_ids = {field_id for field_id, _label in field_order}
    items = [
        f"{label}: {payload[field_id]}"
        for field_id, label in field_order
        if field_id in payload
        and (selected_ids is None or field_id in selected_ids)
    ]
    items.extend(
        f"{qualification_display_label(field_id)}: {value}"
        for field_id, value in payload.items()
        if field_id not in known_ids
    )
    return f"{', '.join(items)}." if items else ""


def qualification_display_label(field_id: str) -> str:
    """Converte um ID personalizado em um rótulo legível para a saída."""
    return " ".join(part.capitalize() for part in str(field_id).split("_") if part)


def history_completion_status(
    history_state: str,
    names_state: str,
    names_count: int,
) -> str:
    if history_state == "done" and names_state == "done":
        if names_count:
            return (
                "Histórico e extração de partes concluídos: "
                f"{names_count} parte(s) identificada(s)."
            )
        return "Histórico concluído; nenhuma parte foi identificada."
    if history_state == "done" and names_state == "running":
        return "Histórico concluído. Finalizando a identificação das partes..."
    if history_state == "running" and names_state == "done":
        if names_count:
            return (
                f"Extração de partes concluída: {names_count} parte(s) identificada(s). "
                "Aguardando o histórico..."
            )
        return "Extração de partes concluída. Aguardando o histórico..."
    return ""


def parse_assistant_names(raw_text: str) -> list[str]:
    clean = raw_text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean).strip()
    names: list[str] = []

    candidates = []
    array_start, array_end = clean.find("["), clean.rfind("]")
    object_start, object_end = clean.find("{"), clean.rfind("}")
    if array_start >= 0 and array_end > array_start:
        candidates.append(clean[array_start : array_end + 1])
    if object_start >= 0 and object_end > object_start:
        candidates.append(clean[object_start : object_end + 1])

    def collect(value):
        if isinstance(value, str):
            add_assistant_name(names, value)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)

    for candidate in candidates:
        try:
            collect(json.loads(candidate))
            if names:
                break
        except json.JSONDecodeError:
            continue
    if not names:
        for match in re.finditer(r'"([^"\\]+)"', clean):
            add_assistant_name(names, match.group(1))
    if not names:
        for value in re.split(r"[,;\n]", clean):
            add_assistant_name(names, value)
    return distinct_names(names)


def add_assistant_name(names: list[str], value: str):
    clean = value.strip().strip("\"'[]{}").strip()
    if clean and len(clean) <= 80:
        names.append(clean.upper())


def distinct_names(names: list[str]) -> list[str]:
    result = []
    seen = set()
    for name in names:
        key = name.upper()
        if key not in seen:
            seen.add(key)
            result.append(name)
    return result


UPPERCASE_NAME_SEQUENCE = re.compile(
    r"(?<![A-Za-zÀ-ÖØ-öø-ÿ0-9])"
    r"[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'’-]+"
    r"(?:\s+[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'’-]+)*"
    r"(?![A-Za-zÀ-ÖØ-öø-ÿ0-9])"
)
UPPERCASE_WORD = re.compile(r"[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'’-]+")
IGNORED_UPPERCASE_WORDS = {"BO", "CPF", "RG", "IMEI", "SP", "WHATSAPP"}
NAME_CONNECTORS = {"DA", "DE", "DO", "DAS", "DOS", "E"}


def extract_uppercase_names(text: str) -> list[str]:
    names = []
    for match in UPPERCASE_NAME_SEQUENCE.finditer(text):
        candidate = re.sub(r"\s+", " ", match.group(0).strip())
        if len(candidate) >= 2 and candidate not in IGNORED_UPPERCASE_WORDS:
            names.append(candidate)
    return distinct_names(names)


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.strip().upper())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return re.sub(r"[^A-Z'’-]", "", normalized)


def phonetic_name_key(normalized: str) -> str:
    value = normalized
    value = value.replace("PH", "F").replace("TH", "T").replace("Y", "I").replace("W", "V")
    value = re.sub(r"^H", "", value)
    value = value.replace("QU", "C").replace("K", "C").replace("Q", "C")
    value = re.sub(r"C(?=[EI])", "S", value)
    value = re.sub(r"G(?=[EI])", "J", value)
    value = value.replace("Z", "S")
    return re.sub(r"([A-Z])\1+", r"\1", value)


def matching_name_keys(value: str) -> set[str]:
    normalized = normalize_name(value)
    if not normalized:
        return set()
    return {normalized, phonetic_name_key(normalized)}


def load_name_database() -> set[str]:
    path = name_database_path()
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        keys.update(matching_name_keys(line))
    return keys


def name_database_path() -> Path:
    path = settings_path().parent / "Nomes" / "nomes.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        default_path = resource_path("assets/default_nomes.txt")
        path.write_text(
            default_path.read_text(encoding="utf-8", errors="replace") if default_path.exists() else "",
            encoding="utf-8",
        )
    return path


def add_name_to_database(value: str) -> bool:
    name = value.strip().upper()
    if not name or any(char in name for char in "\t\r\n"):
        return False
    path = name_database_path()
    current = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if any(normalize_name(item) == normalize_name(name) for item in current):
        return False
    path.write_text("\n".join([*current, name]).strip() + "\n", encoding="utf-8")
    return True


def remove_name_from_database(value: str) -> bool:
    target = normalize_name(value)
    if not target:
        return False
    path = name_database_path()
    current = path.read_text(encoding="utf-8", errors="replace").splitlines()
    remaining = [item for item in current if normalize_name(item) != target]
    if len(remaining) == len(current):
        return False
    path.write_text("\n".join(remaining).strip() + "\n", encoding="utf-8")
    return True


def extract_names_from_database(text: str, name_database: set[str]) -> list[str]:
    if not name_database:
        return []
    names = []
    for match in UPPERCASE_NAME_SEQUENCE.finditer(text):
        words = UPPERCASE_WORD.findall(match.group(0))
        candidate_words = [word for word in words if normalize_name(word) not in NAME_CONNECTORS]
        if candidate_words and all(matching_name_keys(word) & name_database for word in candidate_words):
            names.append(" ".join(candidate_words))
    return distinct_names(names)


def job_transcript_text(job: AudioJob) -> str:
    transcript = job.transcription
    if not transcript and job.txt_path and job.txt_path.exists():
        transcript = job.txt_path.read_text(encoding="utf-8", errors="replace")
    return transcript or ""


def job_problem_reason(job: AudioJob, transcript: str) -> str:
    clean = transcript.strip()
    if job.error:
        return "Erro na transcrição/conversão"
    if not clean:
        return "Transcrição vazia"
    sent_name = job.upload_path.name if job.upload_path else ""
    if sent_name:
        first_line = next((line.strip() for line in clean.splitlines() if line.strip()), "")
        if clean == sent_name or first_line == sent_name:
            return "Servidor retornou o nome do arquivo enviado"
    return ""


def job_problem_reason_2(job: AudioJob, transcript: str) -> str:
    clean = transcript.strip()
    if job.error_2:
        return "Erro na transcrição/conversão"
    if not clean:
        return "Transcrição vazia"
    sent_name = job.upload_path.name if job.upload_path else ""
    if sent_name:
        first_line = next((line.strip() for line in clean.splitlines() if line.strip()), "")
        if clean == sent_name or first_line == sent_name:
            return "Servidor retornou o nome do arquivo enviado"
    return ""


def html_document(title: str, rows: list[str], headers: tuple[str, ...], stats: list[tuple[str, str]] | None = None) -> str:
    header_cells = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    stats_html = ""
    if stats:
        stats_html = (
            '<div class="stats">'
            + "".join(
                f"<span><strong>{html.escape(label)}:</strong> {html.escape(value)}</span>"
                for label, value in stats
            )
            + "</div>"
        )
    if not rows:
        rows = [
            "<tr>"
            f"<td colspan=\"{len(headers)}\">Nenhum item nesta tabela.</td>"
            "</tr>"
        ]
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{
  font-family: Arial, sans-serif;
  background: #101417;
  color: #e8f4f2;
  margin: 24px;
}}
h1 {{ font-size: 24px; margin: 0 0 18px; }}
.stats {{
  color: #9aa9ad;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  font-size: 12px;
  margin: -6px 0 14px;
}}
.stats span {{ white-space: nowrap; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{
  border: 1px solid #334047;
  padding: 10px;
  vertical-align: top;
}}
th {{ background: #182127; text-align: left; }}
td:first-child {{
  width: 32%;
  font-family: Consolas, monospace;
  color: #9ee7ff;
  word-break: break-word;
}}
td {{ white-space: pre-wrap; line-height: 1.45; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
{stats_html}
<table>
<thead><tr>{header_cells}</tr></thead>
<tbody>
{os.linesep.join(rows)}
</tbody>
</table>
</body>
</html>
"""


def write_html_report(jobs: list[AudioJob], html_path: Path, stats: list[tuple[str, str]] | None = None) -> Path:
    valid_rows = []
    problem_rows = []
    multi_model = any(job.model_name_2 for job in jobs)
    for job in jobs:
        transcript = job_transcript_text(job)
        transcript_2 = job.transcription_2
        if not transcript_2 and job.txt_path_2 and job.txt_path_2.exists():
            transcript_2 = job.txt_path_2.read_text(encoding="utf-8", errors="replace")
        problem = job_problem_reason(job, transcript)
        problem_2 = job_problem_reason_2(job, transcript_2) if multi_model else ""
        if multi_model:
            if not problem or not problem_2:
                valid_rows.append(
                    "<tr>"
                    f"<td>{html.escape(job.original_name)}</td>"
                    f"<td>{html.escape(transcript) if not problem else '<em>Falhou</em>'}</td>"
                    f"<td>{html.escape(transcript_2) if not problem_2 else '<em>Falhou</em>'}</td>"
                    "</tr>"
                )
            for index, current_problem, current_error, current_text in (
                (1, problem, job.error, transcript),
                (2, problem_2, job.error_2, transcript_2),
            ):
                if current_problem:
                    problem_rows.append(
                        "<tr>"
                        f"<td>{html.escape(job.original_name)}</td>"
                        f"<td>Modelo {index}</td>"
                        f"<td>{html.escape(current_problem)}</td>"
                        f"<td>{html.escape(current_error or current_text or '(sem retorno)')}</td>"
                        "</tr>"
                    )
            continue
        if problem:
            details = job.error or transcript or "(sem retorno)"
            sent_name = job.upload_path.name if job.upload_path else "(não enviado)"
            problem_rows.append(
                "<tr>"
                f"<td>{html.escape(job.original_name)}</td>"
                f"<td>{html.escape(sent_name)}</td>"
                f"<td>{html.escape(problem)}</td>"
                f"<td>{html.escape(details)}</td>"
                "</tr>"
            )
        else:
            valid_rows.append(
                "<tr>"
                f"<td>{html.escape(job.original_name)}</td>"
                f"<td>{html.escape(transcript)}</td>"
                "</tr>"
            )
    headers = (
        ("Arquivo original", jobs[0].model_name if jobs else "Modelo 1", jobs[0].model_name_2 if jobs else "Modelo 2")
        if multi_model
        else ("Arquivo original", "Transcrição")
    )
    html_path.write_text(
        html_document("Transcrições", valid_rows, headers, stats),
        encoding="utf-8",
    )
    problem_path = html_path.with_name("transcricoes_com_problemas.html")
    problem_path.write_text(
        html_document(
            "Transcrições com problemas",
            problem_rows,
            (
                ("Arquivo original", "Modelo", "Motivo", "Retorno")
                if multi_model
                else ("Arquivo original", "Arquivo enviado", "Motivo", "Retorno")
            ),
            stats,
        ),
        encoding="utf-8",
    )
    return problem_path


def build_live_html(text: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Transcrição ao vivo</title>
<style>
body {{
  font-family: Arial, sans-serif;
  background: #101417;
  color: #e8f4f2;
  margin: 24px;
}}
h1 {{ font-size: 24px; margin: 0 0 18px; }}
.box {{
  border: 1px solid #334047;
  background: #182127;
  padding: 16px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}}
</style>
</head>
<body>
<h1>Transcrição ao vivo</h1>
<div class="box">{html.escape(text)}</div>
</body>
</html>
"""


def pcm_bytes_for_millis(millis: int) -> int:
    return LIVE_SAMPLE_RATE * LIVE_CHANNELS * LIVE_SAMPLE_WIDTH * millis // 1000


def write_wav_from_pcm_bytes(path: Path, pcm: bytes):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(LIVE_CHANNELS)
        wav.setsampwidth(LIVE_SAMPLE_WIDTH)
        wav.setframerate(LIVE_SAMPLE_RATE)
        wav.writeframes(pcm)


def write_wav_from_pcm_file(path: Path, pcm_path: Path):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(LIVE_CHANNELS)
        wav.setsampwidth(LIVE_SAMPLE_WIDTH)
        wav.setframerate(LIVE_SAMPLE_RATE)
        with pcm_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 128)
                if not chunk:
                    break
                wav.writeframesraw(chunk)


class GraniteUploader:
    def __init__(
        self,
        cancel_event: threading.Event,
        form_fields: dict | None = None,
        extra_headers: dict[str, str] | None = None,
        file_field: str = "files",
        raw_body: bool = False,
    ):
        self.cancel_event = cancel_event
        self.form_fields = dict(form_fields or {})
        self.extra_headers = dict(extra_headers or {})
        self.file_field = file_field
        self.raw_body = bool(raw_body)
        self._lock = threading.Lock()
        self._connections: set[http.client.HTTPConnection] = set()

    def cancel(self):
        with self._lock:
            connections = list(self._connections)
        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass

    def post_file(
        self,
        url: str,
        file_path: Path,
        mime_type: str,
        raw_path: Path,
        form_fields: dict | None = None,
    ) -> tuple[int, str]:
        status, raw, _headers = self.post_file_raw(url, file_path, mime_type, raw_path, form_fields)
        return status, extract_text_from_response(raw)

    def post_file_parsed(
        self,
        url: str,
        file_path: Path,
        mime_type: str,
        raw_path: Path,
        form_fields: dict | None = None,
    ) -> tuple[int, ParsedTranscription]:
        status, raw, _headers = self.post_file_raw(url, file_path, mime_type, raw_path, form_fields)
        return status, parse_transcription_response(raw)

    def post_file_raw(
        self,
        url: str,
        file_path: Path,
        mime_type: str,
        raw_path: Path,
        form_fields: dict | None = None,
        accept: str = "application/json",
    ) -> tuple[int, bytes, dict[str, str]]:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise RuntimeError("Servidor precisa começar com http:// ou https://")
        boundary = f"----sig-{uuid.uuid4().hex}"
        filename = file_path.name
        parts = []
        merged_fields = self.form_fields.copy()
        merged_fields.update(form_fields or {})
        if self.raw_body:
            # Deepgram (e APIs de áudio cru): o arquivo vai como body direto,
            # sem multipart; os parâmetros viajam na query da URL.
            preamble = b""
            ending = b""
            content_type = mime_type
            content_length = file_path.stat().st_size
        else:
            for key, value in merged_fields.items():
                if key.lower() in ("file", "files") or value is None:
                    continue
                clean_value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                parts.append(
                    (
                        f"--{boundary}\r\n"
                        f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                        f"{clean_value}\r\n"
                    ).encode("utf-8")
                )
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{self.file_field}"; filename="{filename}"\r\n'
                    f"Content-Type: {mime_type}\r\n\r\n"
                ).encode("utf-8")
            )
            preamble = b"".join(parts)
            ending = f"\r\n--{boundary}--\r\n".encode("utf-8")
            content_type = f"multipart/form-data; boundary={boundary}"
            content_length = len(preamble) + file_path.stat().st_size + len(ending)
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        conn = connection_cls(parsed.netloc, timeout=60 * 60)
        with self._lock:
            self._connections.add(conn)
        try:
            if self.cancel_event.is_set():
                raise Cancelled()
            conn.putrequest("POST", path)
            conn.putheader("accept", accept)
            conn.putheader("Content-Type", content_type)
            conn.putheader("Content-Length", str(content_length))
            for header, value in self.extra_headers.items():
                conn.putheader(header, value)
            conn.endheaders()
            conn.send(preamble)
            with file_path.open("rb") as handle:
                while True:
                    if self.cancel_event.is_set():
                        raise Cancelled()
                    chunk = handle.read(1024 * 128)
                    if not chunk:
                        break
                    conn.send(chunk)
            conn.send(ending)
            if self.cancel_event.is_set():
                raise Cancelled()
            response = conn.getresponse()
            chunks = []
            while True:
                if self.cancel_event.is_set():
                    raise Cancelled()
                chunk = response.read(1024 * 128)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
            raw_path.write_bytes(raw)
            return response.status, raw, dict(response.getheaders())
        except (OSError, socket.timeout) as exc:
            if self.cancel_event.is_set():
                raise Cancelled() from exc
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._connections.discard(conn)


class TextModelClient:
    def __init__(self, cancel_event: threading.Event):
        self.cancel_event = cancel_event
        self._lock = threading.Lock()
        self._connections: set[http.client.HTTPConnection] = set()

    def cancel(self):
        with self._lock:
            connections = list(self._connections)
        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass

    def post(self, model_config: dict, system_prompt: str, material: str) -> str:
        url = model_config["url"]
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise RuntimeError("O endereço do modelo precisa começar com http:// ou https://")
        payload = json.loads(json.dumps(model_config["parameters"], ensure_ascii=False))
        is_grok_api = bool(model_config.get("is_grok_api"))
        is_deepseek_api = bool(model_config.get("is_deepseek_api"))
        is_xai_proxy = bool(model_config.get("is_xai_proxy"))
        provider = str(model_config.get("provider") or "").casefold()
        is_non_reasoning_grok = (
            model_config.get("request_model") or payload.get("model")
        ) == GROK_NON_REASONING_TEXT_NAME
        is_xai_request = is_grok_api or (is_xai_proxy and provider == "xai")
        is_deepseek_request = is_deepseek_api or (is_xai_proxy and provider == "deepseek")
        if is_grok_api or is_deepseek_api:
            api_key = str(model_config.get("api_key") or "").strip()
            if not api_key:
                provider = "DeepSeek" if is_deepseek_api else "xAI"
                raise RuntimeError(f"Insira a chave API da {provider} nas configurações.")
        if is_xai_request:
            payload.setdefault("model", GROK_TEXT_NAME)
            payload.setdefault("temperature", 0.0)
            payload.setdefault("max_output_tokens", 10000)
            if is_non_reasoning_grok:
                payload["model"] = GROK_NON_REASONING_TEXT_NAME
                payload.pop("reasoning", None)
            else:
                payload.setdefault("reasoning", {"effort": "low"})
                if str((payload.get("reasoning") or {}).get("effort") or "").casefold() == "none":
                    payload["reasoning"] = {**payload["reasoning"], "effort": "low"}
            payload.pop("max_tokens", None)
        if is_deepseek_request:
            payload["messages"] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": material},
            ]
            payload.pop("input", None)
        elif "/api/generate" in parsed.path.lower():
            payload["system"] = system_prompt
            payload["prompt"] = material
            payload.setdefault("stream", False)
        else:
            payload["input"] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": material},
            ]
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        urls = [url]
        fallback_url = str(model_config.get("fallback_url") or "").strip()
        if fallback_url and fallback_url != url:
            urls.append(fallback_url)
        last_error = None
        for attempt_url in urls:
            attempt_parsed = urlparse(attempt_url)
            if attempt_parsed.scheme not in ("http", "https"):
                last_error = RuntimeError("O endereço do modelo precisa começar com http:// ou https://")
                continue
            path = attempt_parsed.path or "/"
            if attempt_parsed.query:
                path += f"?{attempt_parsed.query}"
            connection_cls = http.client.HTTPSConnection if attempt_parsed.scheme == "https" else http.client.HTTPConnection
            conn = connection_cls(attempt_parsed.netloc, timeout=60 * 60)
            with self._lock:
                self._connections.add(conn)
            try:
                if self.cancel_event.is_set():
                    raise Cancelled()
                headers = {
                    "accept": "application/json",
                    "Content-Type": "application/json; charset=utf-8",
                    "Content-Length": str(len(body)),
                }
                if is_grok_api or is_deepseek_api:
                    headers["Authorization"] = f"Bearer {api_key}"
                conn.request("POST", path, body=body, headers=headers)
                response = conn.getresponse()
                chunks = []
                while True:
                    if self.cancel_event.is_set():
                        raise Cancelled()
                    chunk = response.read(1024 * 128)
                    if not chunk:
                        break
                    chunks.append(chunk)
                raw = b"".join(chunks)
                if response.status < 200 or response.status >= 300:
                    detail = raw.decode("utf-8", errors="replace")
                    raise RuntimeError(f"Servidor respondeu HTTP {response.status}: {detail[:400]}")
                output = extract_text_model_output(raw).strip()
                if not output:
                    raise RuntimeError("O servidor devolveu um texto vazio.")
                return output
            except Cancelled:
                raise
            except (OSError, socket.timeout, RuntimeError) as exc:
                if self.cancel_event.is_set():
                    raise Cancelled() from exc
                last_error = exc
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
                with self._lock:
                    self._connections.discard(conn)
        raise last_error or RuntimeError("Não foi possível consultar o modelo de texto.")


def cpu_parallel_options(cpu_count: int) -> list[int]:
    """Opções de Conversões paralelas: n/2, n, 2n e 4n núcleos (exemplos do
    usuário: 6 núcleos -> 3, 6, 12, 24; Xeon 18 -> 9, 18, 36, 72)."""
    half = max(1, cpu_count // 2)
    return sorted({half, cpu_count, cpu_count * 2, cpu_count * 4})


class SigApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("sig")
        self._apply_window_icon()
        self.root.geometry("1260x960")
        self.root.minsize(1220, 820)
        if os.name == "nt":
            self.root.state("zoomed")
        self.settings = load_settings()
        try:
            self.document_templates = ensure_document_templates()
        except Exception:
            # A geração mostra a causa completa se o recurso for acionado.
            self.document_templates = {}
        self.selected_paths: list[Path] = []
        self.ui_queue: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.grok_expired_retry_lock = threading.Lock()
        self.worker_thread: threading.Thread | None = None
        self.active_processes: set[subprocess.Popen] = set()
        self.process_lock = threading.Lock()
        self.uploader: GraniteUploader | None = None
        self.uploaders: list[GraniteUploader] = []
        self.tree_items: dict[Path, str] = {}
        self.running = False
        self.last_html_path: Path | None = None
        self.live_state = "idle"
        self.live_thread: threading.Thread | None = None
        self.live_finalize_thread: threading.Thread | None = None
        self.live_upload_executor: concurrent.futures.ThreadPoolExecutor | None = None
        self.live_stop_event = threading.Event()
        self.live_abort_event = threading.Event()
        self.live_lock = threading.RLock()
        self.live_uploader: GraniteUploader | None = None
        self.live_full_pcm_path: Path | None = None
        self.live_uses_grok_websocket = False
        self.live_uses_deepgram_websocket = False
        self.live_uses_assemblyai_websocket = False
        self.live_uses_elevenlabs_websocket = False
        self.live_grok_settings: dict | None = None
        self.live_grok_language = "pt"
        self.live_grok_diarize = False
        self.grok_ws_app = None
        self.grok_ws_thread: threading.Thread | None = None
        self.grok_ws_ready_event = threading.Event()
        self.grok_ws_done_event = threading.Event()
        self.grok_ws_lost_event = threading.Event()
        self.grok_ws_intentional_close = False
        self.deepgram_ws_app = None
        self.deepgram_ws_thread: threading.Thread | None = None
        self.deepgram_ws_ready_event = threading.Event()
        self.deepgram_ws_done_event = threading.Event()
        self.deepgram_ws_lost_event = threading.Event()
        self.deepgram_ws_intentional_close = False
        self.assemblyai_ws_app = None
        self.assemblyai_ws_thread: threading.Thread | None = None
        self.assemblyai_ws_ready_event = threading.Event()
        self.assemblyai_ws_done_event = threading.Event()
        self.assemblyai_ws_lost_event = threading.Event()
        self.assemblyai_ws_intentional_close = False
        self.elevenlabs_ws_app = None
        self.elevenlabs_ws_thread: threading.Thread | None = None
        self.elevenlabs_ws_ready_event = threading.Event()
        self.elevenlabs_ws_done_event = threading.Event()
        self.elevenlabs_ws_lost_event = threading.Event()
        self.elevenlabs_ws_intentional_close = False
        self.live_was_grok_websocket = False
        self.live_audio_recovery_available = False
        self.live_recovery_thread: threading.Thread | None = None
        self.live_recovery_cancel_event = threading.Event()
        self.live_capture_finish_waiting = False
        self.live_output_finished = False
        self.live_started_at = 0.0
        self.live_paused_at = 0.0
        self.live_paused_total = 0.0
        self.live_interval_ms = DEFAULT_LIVE_DRAFT_INTERVAL_MILLIS
        self.live_draft_generation = 0
        self.live_committed_text = ""
        self.live_draft_text = ""
        self.last_live_transcript_text = ""
        self.last_live_history_text = ""
        self.last_live_history_text_2 = ""
        self.last_live_statement_text = ""
        self.last_live_statement_text_2 = ""
        self.last_live_qualification_text = ""
        self.last_generated_document_path: Path | None = None
        self.last_generated_document_preview_path: Path | None = None
        self.last_generated_document_preview_image_path: Path | None = None
        self.pending_occurrence_document_generation = False
        self.document_preview_generation = 0
        self.document_preview_photo = None
        self.document_preview_visible = False
        self.live_plain_transcript_text = ""
        self.live_timestamped_transcript_text = ""
        self.live_secondary_active = False
        self.live_secondary_audio_queue: queue.Queue[bytes] | None = None
        self.live_secondary_thread: threading.Thread | None = None
        self.live_secondary_done_event = threading.Event()
        self.live_secondary_done_event.set()
        self.live_secondary_lock = threading.RLock()
        self.live_secondary_committed_text = ""
        self.live_secondary_draft_text = ""
        self.live_secondary_generation = 0
        self.last_live_transcript_text_2 = ""
        self.live_finish_waiting = False
        self.normal_recording = False
        self.normal_record_stop_event = threading.Event()
        self.normal_record_thread: threading.Thread | None = None
        self.normal_record_pcm_path: Path | None = None
        self.normal_record_grok = False
        self.normal_record_language = "pt"
        self.normal_record_diarize = False
        self.normal_record_paused = False
        self.live_waveform_lock = threading.Lock()
        # Keep roughly one envelope sample per visible pixel for a denser waveform.
        self.live_waveform_levels = deque([0.0] * 168, maxlen=168)
        self.live_waveform_last_capture_at = 0.0

        self.live_language_var = StringVar(value="pt")
        self.live_language_label_var = StringVar(value="Idioma: Português")
        self.live_diarize_var = BooleanVar(value=False)
        self.live_timestamps_var = BooleanVar(value=False)
        self.assistant_cancel_event = threading.Event()
        self.assistant_client: TextModelClient | None = None
        self.assistant_thread: threading.Thread | None = None
        self.assistant_generation = 0
        self.assistant_busy = False
        self.assistant_target = "assistant"
        self.assistant_names: list[str] = []
        self.live_assistant_names: list[str] = []
        self.assistant_task_states = {"history": "idle", "names": "idle", "statement": "idle", "document": "idle", "document_copy": "idle", "document_save_docx": "idle", "document_save_pdf": "idle", "qualification_document": "idle"}
        self.assistant_task_elapsed: dict[str, float | None] = {
            "history": None,
            "names": None,
            "statement": None,
            "document": None,
            "document_copy": None,
            "document_save_docx": None,
            "document_save_pdf": None,
            "qualification_document": None,
        }
        self.assistant_task_started_at: dict[str, float | None] = {
            "history": None,
            "names": None,
            "statement": None,
            "document": None,
            "document_copy": None,
            "document_save_docx": None,
            "document_save_pdf": None,
            "qualification_document": None,
        }
        self.assistant_multi_started_at: dict[tuple[str, int], float] = {}
        self.assistant_phase = "idle"
        self.imei_generation = 0
        self.imei_thread: threading.Thread | None = None
        self.imei_last_processed = ""
        self.imei_history_expanded = False
        self.imei_formatting = False
        self.zip_help_after_id = None
        self.zip_help_window = None
        self.zip_help_position = (0, 0)
        self.available_update: dict | None = None
        self.available_update_sync: dict | None = None
        self._sync_file_marks: dict[str, str] = {}
        self.update_check_thread: threading.Thread | None = None
        self.update_install_thread: threading.Thread | None = None
        self.update_installing = False
        self.about_window = None
        self.about_image = None

        self.mode_var = StringVar(value="ready")
        self.convert_only_var = BooleanVar(value=False)
        self.vad_var = StringVar(value="Off")
        self.vad_only_var = BooleanVar(value=False)
        self.transcribe_after_convert_var = BooleanVar(value=False)
        self.send_zip_var = BooleanVar(value=False)
        self.zip_level_var = StringVar(value="1")
        self.status_var = StringVar(value="Escolha arquivos ou uma pasta para começar.")
        self._activity_status_suppressed = 0
        self._activity_steps: dict[str, dict[str, str]] = {}
        self.update_button_var = StringVar(value="Atualização disponível")
        self.server_var = StringVar()
        self.progress_var = IntVar(value=0)
        self.live_interval_var = StringVar(value="1.0")
        self.live_timer_var = StringVar(value="00:00.000")
        self.assistant_status_var = StringVar(value="Cole ou digite uma transcrição para começar.")
        self.assistant_progress_var = StringVar(value="")
        self.assistant_part_var = StringVar(value="Partes")
        self.live_assistant_status_var = StringVar(value="")
        self.live_assistant_progress_var = StringVar(value="")
        self.live_assistant_part_var = StringVar(value="Partes")
        self.live_assistant_part_var_2 = StringVar(value="Partes")
        self.transcription_model_display_var = StringVar()
        self.text_model_display_var = StringVar()
        self.multi_model_var = BooleanVar(value=False)
        self.multi_model_secondary = str(self.settings.get("transcription_server_2") or "")
        self.multi_text_model_var = BooleanVar(value=False)
        self.multi_text_secondary = str(self.settings.get("text_model_2") or "")
        self.imei_tac_var = StringVar()
        self.imei_sn_var = StringVar()
        self.imei_result_var = StringVar(value="Dígito: —")
        self.imei_model_var = StringVar(value="")
        self.imei_status_var = StringVar(value="")
        self.imei_history_var = StringVar(value="")
        self.imei_toggle_var = StringVar(value="")
        self.qualification_status_var = StringVar(value="")
        self.qualification_fields = (
            ("nome", "Nome Completo"),
            ("nascimento", "Data de Nascimento"),
            ("rg", "RG"),
            ("cpf", "CPF"),
            ("naturalidade", "Naturalidade"),
            ("sexo", "Sexo"),
            ("estado_civil", "Estado Civil"),
            ("profissao", "Profissão"),
            ("altura", "Altura"),
            ("pele", "Pele"),
            ("olhos", "Olhos"),
            ("cabelo", "Cabelo"),
            ("pai", "Pai"),
            ("mae", "Mãe"),
            ("instrucao", "Grau de Instrução"),
            ("endereco", "Endereço"),
            ("bairro", "Bairro"),
            ("cidade", "Cidade"),
            ("telefone", "Telefone"),
        )
        self.qualification_output_fields = (
            ("nome", "Nome"),
            ("nascimento", "Data de Nascimento"),
            ("rg", "RG"),
            ("cpf", "CPF"),
            ("naturalidade", "Naturalidade"),
            ("sexo", "Sexo"),
            ("estado_civil", "Estado Civil"),
            ("profissao", "Profissão"),
            ("altura", "Altura"),
            ("pele", "Pele"),
            ("olhos", "Olhos"),
            ("cabelo", "Cabelo"),
            ("pai", "Pai"),
            ("mae", "Mãe"),
            ("instrucao", "Grau de Instrução"),
            ("endereco", "Endereço"),
            ("bairro", "Bairro"),
            ("cidade", "Cidade"),
            ("telefone", "Telefone"),
        )
        self.qualification_field_vars = {
            field_id: BooleanVar(value=True)
            for field_id, _label in self.qualification_fields
        }
        self.qualification_select_all_var = BooleanVar(value=True)
        self.qualification_result_fields: dict[str, str] = {}
        self.qualification_other_ids_var = StringVar()
        self.qualification_declarations_var = BooleanVar(value=True)
        self.qualification_deposition_var = BooleanVar(value=False)
        self.document_preview_zoom_var = StringVar(value="100%")
        self.document_preview_page_var = StringVar(value="")
        self.document_preview_page_regions: list[tuple[int, int]] = []

        self._build_style()
        self.paste_icon = self._make_paste_icon()
        self.copy_icon = self._make_copy_icon()
        self.clear_icon = self._make_clear_icon()
        self.recover_icon = self._make_recover_icon()
        self.recover_audio_icon = self._make_recover_icon("#d39b00")
        self.document_copy_icon = self._make_document_action_icon("copy")
        self.document_save_icon = self._make_document_action_icon("save")
        self.document_view_icon = self._make_document_action_icon("preview")
        self._build_menu()
        self._build_ui()
        self.status_var.trace_add("write", lambda *_args: self._on_status_var_changed())
        self._refresh_server_label()
        self.root.after(100, self._poll_ui_queue)
        self.root.after(100, self._refresh_assistant_progress_clock)
        self.root.after(1200, self._start_update_check)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        settings_surface = style.lookup("TLabelframe", "background") or "#dcdad5"
        style.configure("TFrame", background="#f4f7f6")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("TLabel", background="#f4f7f6", foreground="#1d2b2a", font=("Segoe UI", 10))
        # Keep labels inside the settings sections on the same surface as the
        # label frame instead of inheriting the theme's light label background.
        style.configure("Settings.TFrame", background=settings_surface)
        style.configure("Settings.TLabelframe", background=settings_surface)
        style.configure("Settings.TLabelframe.Label", background=settings_surface)
        style.configure(
            "Settings.TLabel",
            background=settings_surface,
            foreground="#1d2b2a",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Settings.TCheckbutton",
            background=settings_surface,
            foreground="#1d2b2a",
            font=("Segoe UI", 10),
        )
        style.configure("Muted.TLabel", background="#f4f7f6", foreground="#667371", font=("Segoe UI", 9))
        style.configure(
            "DocumentPreview.TLabel",
            background="#f4f7f6",
            foreground="#536565",
            font=("Segoe UI Semibold", 9),
        )
        style.configure("ModelSummary.TLabel", background="#f4f7f6", foreground="#667371", font=("Consolas", 9))
        style.configure("Title.TLabel", background="#f4f7f6", foreground="#10201f", font=("Segoe UI Semibold", 24))
        style.configure("TButton", font=("Segoe UI", 10), padding=(8, -1))
        style.configure("TMenubutton", font=("Segoe UI", 10), padding=(8, -1))
        style.configure(
            "Execute.TButton",
            foreground="#16833a",
            font=("Segoe UI Semibold", 10),
            padding=(8, -1),
            anchor="center",
            justify="center",
        )
        style.configure("Action.TButton", foreground="#16833a", font=("Segoe UI Semibold", 10), padding=(2, -1))
        style.configure("Action.TMenubutton", foreground="#16833a", font=("Segoe UI Semibold", 10), padding=(2, -1))
        style.configure("Recover.TButton", padding=(0, -1))
        style.configure(
            "DocumentAction.TButton",
            foreground="#1d2b2a",
            background="#e8ecea",
            font=("Segoe UI Semibold", 9),
            padding=(3, 4),
        )
        style.map(
            "DocumentAction.TButton",
            background=[("active", "#d9e3df"), ("disabled", "#edf0ef")],
            foreground=[("disabled", "#87918f")],
        )
        style.configure(
            "Update.TButton",
            foreground="#ffffff",
            background="#16833a",
            font=("Segoe UI Semibold", 10),
            padding=(12, 4),
        )
        style.map(
            "Update.TButton",
            background=[("active", "#116b30"), ("disabled", "#7ea98a")],
            foreground=[("disabled", "#f1f4f2")],
        )
        style.configure("TRadiobutton", background="#f4f7f6", foreground="#1d2b2a", font=("Segoe UI", 10))
        style.configure("TCheckbutton", background="#f4f7f6", foreground="#1d2b2a", font=("Segoe UI", 10))
        style.configure(
            "SelectAll.TCheckbutton",
            background="#f4f7f6",
            foreground="#16833a",
            font=("Segoe UI Semibold", 10),
        )
        style.configure("TNotebook", background="#f4f7f6", borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(18, 8))
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))

    def _apply_window_icon(self):
        try:
            self.window_icon = PhotoImage(file=str(resource_path("assets/icon.png")))
            self.root.iconphoto(True, self.window_icon)
        except Exception:
            self.window_icon = None

    @staticmethod
    def _make_paste_icon():
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = "#263735"
        draw.rounded_rectangle((4, 5, 16, 18), radius=1, outline=color, width=2)
        draw.line((7, 5, 7, 4, 8, 3, 12, 3, 13, 4, 13, 5), fill=color, width=2)
        draw.line((7, 10, 13, 10), fill=color, width=2)
        draw.line((7, 14, 12, 14), fill=color, width=2)
        return ImageTk.PhotoImage(image)

    @staticmethod
    def _make_copy_icon():
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = "#263735"
        draw.rounded_rectangle((6, 3, 16, 14), radius=1, outline=color, width=2)
        draw.rounded_rectangle((3, 6, 13, 17), radius=1, outline=color, width=2)
        return ImageTk.PhotoImage(image)

    @staticmethod
    def _make_clear_icon():
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = "#263735"
        draw.line((13, 2, 8, 11), fill=color, width=2)
        draw.polygon(((6, 9), (11, 12), (8, 18), (2, 15)), outline=color)
        draw.line((4, 14, 9, 17), fill=color, width=2)
        draw.line((6, 11, 10, 13), fill=color, width=2)
        return ImageTk.PhotoImage(image)

    @staticmethod
    def _make_recover_icon(color="#263735"):
        image = Image.new("RGBA", (17, 17), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.arc((2, 2, 15, 15), start=45, end=315, fill=color, width=2)
        draw.polygon(((14, 3), (14, 7), (11, 4)), fill=color)
        return ImageTk.PhotoImage(image)

    @staticmethod
    def _make_document_action_icon(kind: str):
        scale = 4
        size = 36
        image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = "#263735"
        width = 2 * scale

        def box(coords, radius=2):
            draw.rounded_rectangle(
                tuple(value * scale for value in coords),
                radius=radius * scale,
                outline=color,
                width=width,
            )

        if kind == "copy":
            box((11, 5, 30, 26), 2)
            box((5, 11, 24, 32), 2)
        elif kind == "preview":
            draw.ellipse(
                tuple(value * scale for value in (5, 4, 25, 24)),
                outline=color,
                width=width,
            )
            draw.line(
                tuple(value * scale for value in (22, 21, 32, 31)),
                fill=color,
                width=3 * scale,
            )
        elif kind == "save":
            box((5, 4, 31, 32), 2)
            draw.rectangle(
                tuple(value * scale for value in (10, 4, 25, 14)),
                outline=color,
                width=width,
            )
            draw.rectangle(
                tuple(value * scale for value in (11, 21, 25, 32)),
                outline=color,
                width=width,
            )
            draw.rectangle(
                tuple(value * scale for value in (21, 6, 24, 12)),
                fill=color,
            )
        else:
            raise ValueError(f"Ícone de documento desconhecido: {kind}")
        image = image.resize((size, size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image)

    @staticmethod
    def _make_editor_icon_button(parent, image, tooltip, command):
        button = ttk.Button(parent, image=image, width=3, command=command)
        create_tooltip(button, tooltip)
        return button

    def _build_menu(self):
        menubar = ttk.Frame(self.root)
        self.root.option_add("*tearOff", False)
        import tkinter as tk

        menu = tk.Menu(self.root)
        menu.add_command(label="Configurações", command=self.open_settings)
        menu.add_command(label="Status", command=self.open_status)
        menu.add_command(label="Verificar Atualizações", command=self.check_updates_now)
        menu.add_command(label="Sobre", command=self.open_about)
        self.root.config(menu=menu)

    def _on_status_var_changed(self):
        if self._activity_status_suppressed:
            return
        self._append_activity_log(self.status_var.get())

    def _set_activity_status(self, message: str, *, log: bool = True):
        if log:
            self.status_var.set(message)
            return
        self._activity_status_suppressed += 1
        try:
            self.status_var.set(message)
        finally:
            self._activity_status_suppressed = max(0, self._activity_status_suppressed - 1)

    def _begin_activity_step(self, key: str, label: str):
        """Insere uma etapa atualizável no log, como as tarefas do FFmpeg."""
        box = getattr(self, "activity_log", None)
        if box is None or not box.winfo_exists():
            return
        box.configure(state="normal")
        for tag, color in (
            ("activity_step_running", "#33403e"),
            ("activity_step_done", "#16833a"),
            ("activity_step_warning", "#a8711a"),
            ("activity_step_error", "#b3261e"),
        ):
            if tag not in box.tag_names():
                box.tag_configure(tag, foreground=color)
        mark = f"activity_step_{uuid.uuid4().hex}"
        started_at = time.strftime("%H:%M:%S")
        box.insert(END, f"{started_at}  {label}\n", "activity_step_running")
        box.mark_set(mark, "end-2l linestart")
        box.mark_gravity(mark, "left")
        box.see(END)
        box.configure(state="disabled")
        self._activity_steps[key] = {"mark": mark, "started_at": started_at, "label": label}

    def _finish_activity_step(
        self,
        key: str,
        elapsed: float,
        *,
        error: str | None = None,
        suffix: str | None = None,
        tag: str | None = None,
    ):
        """Atualiza a linha inicial da etapa sem criar uma segunda mensagem."""
        step = self._activity_steps.pop(key, None)
        if not step:
            # Etapa nunca iniciada (ex.: zoom da prévia ou salvamento, que não
            # produzem log): não registrar linha genérica de conclusão.
            return
        box = getattr(self, "activity_log", None)
        if box is None or not box.winfo_exists():
            return
        mark = step["mark"]
        label = step["label"]
        try:
            box.configure(state="normal")
            start = box.index(mark)
            end = box.index(f"{mark} lineend +1c")
            box.delete(start, end)
            if error:
                text = f"{step['started_at']}  {label} ERRO ({float(elapsed):.1f}s): {str(error).rstrip(' .')}\n"
                tag = "activity_step_error"
            else:
                suffix_text = f" {suffix}" if suffix else ""
                text = f"{step['started_at']}  {label}{suffix_text} ({float(elapsed):.1f}s)\n"
                tag = tag or "activity_step_done"
            box.insert(start, text, tag)
            box.mark_unset(mark)
            box.see(END)
            box.configure(state="disabled")
        except tk.TclError:
            try:
                box.configure(state="disabled")
            except tk.TclError:
                pass

    @staticmethod
    def _compact_activity_message(message: str) -> str:
        """Mantém o log curto, objetivo e sem duplicar etapas concluídas."""
        message = str(message or "").strip()
        if not message:
            return ""

        # Status antigos eram registrados pelo trace de status_var e também
        # diretamente pelo worker. Oculte a segunda linha redundante.
        if message in {
            "Documento e visualização prontos.",
            "Documento e visualização prontos",
            "Documento pronto para copiar",
            "Qualificação gerada.",
            "Qualificação gerada",
            "Qualificação organizada.",
            "Qualificação organizada",
            "Oitiva gerada.",
            "Oitiva gerada",
        } or message.startswith("Documento pronto para copiar:"):
            return ""

        compact_patterns = (
            (r"^Requisição de histórico concluída em ([0-9]+(?:\.[0-9]+)?)s\.?$", "Histórico requisitado"),
            (r"^Requisição de oitiva concluída em ([0-9]+(?:\.[0-9]+)?)s\.?$", "Oitiva requisitada"),
            (r"^Requisição de qualificação concluída em ([0-9]+(?:\.[0-9]+)?)s\.?$", "Qualificação requisitada"),
            (r"^Extração de partes concluída em ([0-9]+(?:\.[0-9]+)?)s\.?$", "Partes requisitadas"),
            (r"^Geração da prévia do documento concluída em ([0-9]+(?:\.[0-9]+)?)s\.?$", "Preview requisitado"),
            (r"^Geração do DOCX preenchido concluída em ([0-9]+(?:\.[0-9]+)?)s\.?$", "Documento requisitado"),
            (r"^Cópia formatada para a área de transferência concluída em ([0-9]+(?:\.[0-9]+)?)s\.?$", "Cópia requisitada"),
            (r"^Salvamento do documento concluído em ([0-9]+(?:\.[0-9]+)?)s\.?$", "Salvamento requisitado"),
        )
        for pattern, label in compact_patterns:
            match = re.match(pattern, message)
            if match:
                return f"{label} ({match.group(1)}s)"

        error_patterns = (
            (r"^Requisição de histórico falhou após ([0-9]+(?:\.[0-9]+)?)s:\s*(.*)$", "Histórico ERRO"),
            (r"^Requisição de oitiva falhou após ([0-9]+(?:\.[0-9]+)?)s:\s*(.*)$", "Oitiva ERRO"),
            (r"^Requisição de qualificação falhou após ([0-9]+(?:\.[0-9]+)?)s:\s*(.*)$", "Qualificação ERRO"),
            (r"^Geração do DOCX preenchido falhou após ([0-9]+(?:\.[0-9]+)?)s:\s*(.*)$", "Documento ERRO"),
            (r"^Geração da prévia falhou após ([0-9]+(?:\.[0-9]+)?)s:\s*(.*)$", "Preview ERRO"),
            (r"^Cópia formatada falhou após ([0-9]+(?:\.[0-9]+)?)s:\s*(.*)$", "Cópia ERRO"),
            (r"^Salvamento do documento falhou após ([0-9]+(?:\.[0-9]+)?)s:\s*(.*)$", "Salvar ERRO"),
        )
        for pattern, label in error_patterns:
            match = re.match(pattern, message)
            if match:
                return f"{label} ({match.group(1)}s): {match.group(2).rstrip(' .')}"

        return message.rstrip(".")

    def _append_activity_log(self, message: str, tag: str | None = None):
        message = self._compact_activity_message(message)
        if not message or not getattr(self, "activity_log", None):
            return
        self.activity_log.configure(state="normal")
        if "vad_total" not in self.activity_log.tag_names():
            self.activity_log.tag_configure("vad_total", foreground="#0a7a2f")
        if "warning" not in self.activity_log.tag_names():
            self.activity_log.tag_configure("warning", foreground="#a65300")
        for part in message.splitlines():
            line = f"{time.strftime('%H:%M:%S')}  {part}\n"
            if tag:
                self.activity_log.insert(END, line, tag)
            else:
                self.activity_log.insert(END, line)
        self.activity_log.see(END)
        self.activity_log.configure(state="disabled")

    def _render_sync_file_line(self, path: str, display: str, tag: str | None) -> None:
        """Atualiza a linha viva de um arquivo do download (padrão do VAD).

        Cria a linha na primeira aparição e substitui no lugar nas
        atualizações seguintes; ao concluir, recebe a tag verde.
        """
        box = getattr(self, "activity_log", None)
        if box is None or not box.winfo_exists():
            return
        box.configure(state="normal")
        if "vad_total" not in box.tag_names():
            box.tag_configure("vad_total", foreground="#0a7a2f")
        mark_name = self._sync_file_marks.get(path)
        if mark_name is None:
            mark_name = f"syncfile:{path}"
            box.mark_set(mark_name, END)
            box.mark_gravity(mark_name, "left")
            self._sync_file_marks[path] = mark_name
        else:
            start = box.index(mark_name)
            end = box.index(f"{mark_name} lineend +1c")
            box.delete(start, end)
        line = f"{time.strftime('%H:%M:%S')}  {path} - {display}\n"
        box.insert(mark_name, line, tag)
        if display == "100%":
            self._sync_file_marks.pop(path, None)
        box.see(END)
        box.configure(state="disabled")

    @staticmethod
    def _format_size(total_bytes: int) -> str:
        size = max(0, int(total_bytes))
        if size < 1000:
            return f"{size} byte" if size == 1 else f"{size} bytes"

        units = ("KB", "MB", "GB", "TB")
        value = float(size)
        unit_index = -1
        while unit_index < len(units) - 1 and value >= 999.95:
            value /= 1000.0
            unit_index += 1
        formatted = f"{value:.1f}".replace(".", ",")
        return f"{formatted} {units[unit_index]}"

    def _start_update_check(self) -> None:
        if self.update_check_thread and self.update_check_thread.is_alive():
            return
        self.update_check_thread = threading.Thread(
            target=self._update_check_worker,
            args=(False,),
            daemon=True,
        )
        self.update_check_thread.start()

    def check_updates_now(self) -> None:
        if self.update_check_thread and self.update_check_thread.is_alive():
            messagebox.showinfo("Atualizações", "A verificação já está em andamento.")
            return
        self._begin_activity_step("update:check", "Verificando atualizações")
        self._update_check_started = time.perf_counter()
        self.update_check_thread = threading.Thread(
            target=self._update_check_worker,
            args=(True,),
            daemon=True,
        )
        self.update_check_thread.start()

    def _update_check_worker(self, manual: bool = False) -> None:
        # Mecanismo principal: sincronização por arquivo (manifesto schema 2).
        try:
            raw = download_google_drive_bytes(SYNC_MANIFEST_FILE_ID, 2 * 1024 * 1024)
            manifest = json.loads(raw.decode("utf-8"))
            sync_state = validate_sync_manifest(manifest)
            version = sync_state["version"]
            if version > APP_VERSION:
                classification = classify_sync_files(app_base_dir(), sync_state["files"])
                self._queue(
                    "update_available_sync",
                    {
                        "version": version,
                        "files": sync_state["files"],
                        "download": classification["download"],
                        "remove": classification["remove"],
                    },
                )
            elif manual:
                self._queue("update_not_found")
            return
        except (SyncError, ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            if manual:
                # Tenta o incremental ZIP (formato antigo) como contingência.
                try:
                    raw = download_google_drive_bytes(UPDATE_MANIFEST_FILE_ID, 1024 * 128)
                    manifest = json.loads(raw.decode("utf-8"))
                    if not verify_update_manifest_signature(manifest):
                        raise RuntimeError("assinatura digital inválida")
                    version = str(manifest.get("version") or "")
                    zip_file_id = str(manifest.get("zip_file_id") or "")
                    zip_name = str(manifest.get("zip_name") or "")
                    digest = str(manifest.get("sha256") or "").lower()
                    size = int(manifest.get("size") or 0)
                    if not re.fullmatch(r"\d{8}_\d{3}", version):
                        raise RuntimeError("versão inválida no manifesto")
                    if not zip_file_id or zip_name != f"{version}.zip":
                        raise RuntimeError("manifesto de atualização inconsistente")
                    if not re.fullmatch(r"[0-9a-f]{64}", digest) or size <= 0:
                        raise RuntimeError("hash ou tamanho inválido no manifesto")
                    if version > APP_VERSION:
                        self._queue("update_available", manifest)
                    else:
                        self._queue("update_not_found")
                except Exception as fallback_error:
                    self._queue("update_check_error", str(fallback_error))
                return
            self._queue("activity", f"Atualização: não foi possível consultar o Drive ({exc}).")

    def install_available_update(self) -> None:
        if (not self.available_update and not self.available_update_sync) or self.update_installing:
            return
        ffmpeg_running = bool(getattr(self, "ffmpeg_tools", None) and self.ffmpeg_tools.running)
        if self.running or self.live_state != "idle" or self.normal_recording or self.assistant_busy or ffmpeg_running:
            messagebox.showinfo("sig", "Aguarde a tarefa em andamento terminar antes de atualizar.")
            return
        self.update_installing = True
        self.update_button.configure(state="disabled")
        self.update_button_var.set("Baixando arquivos...")
        if self.available_update_sync:
            self.update_install_thread = threading.Thread(
                target=self._sync_download_worker,
                args=(self.available_update_sync.copy(),),
                daemon=True,
            )
        else:
            self.update_install_thread = threading.Thread(
                target=self._update_download_worker,
                args=(self.available_update.copy(),),
                daemon=True,
            )
        self.update_install_thread.start()

    def _sync_download_worker(self, sync_state: dict) -> None:
        version = str(sync_state["version"])
        staging_root = Path(tempfile.gettempdir()) / "sig_updater_sync" / version
        staged = staging_root / "staged"
        try:
            if staged.exists():
                shutil.rmtree(staged)
            staged.mkdir(parents=True)
            removals_path = staging_root / "removals.txt"
            removals_path.write_text(
                "\n".join(sync_state["remove"]) + ("\n" if sync_state["remove"] else ""),
                encoding="utf-8",
            )
            downloads = list(sync_state["download"])
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                def _download_one(path: str) -> None:
                    entry = sync_state["files"][path]
                    destination = staged / Path(*PurePosixPath(path).parts)
                    last_report = {"at": 0.0}

                    def on_progress(downloaded: int, total: int) -> None:
                        now = time.monotonic()
                        if now - last_report["at"] >= 0.1 or (total and downloaded >= total):
                            last_report["at"] = now
                            self._queue("update_sync_file_progress", path, downloaded, total)

                    if entry.get("github_url"):
                        digest = download_github_url(
                            entry["github_url"], destination, progress_callback=on_progress
                        )
                    else:
                        digest = download_google_drive_file(
                            entry["drive_id"], destination, progress_callback=on_progress
                        )
                    if digest.lower() != entry["sha256"]:
                        raise RuntimeError(f"SHA-256 divergente ao baixar: {path}")
                    self._queue("update_sync_file_done", path)

                futures = {pool.submit(_download_one, path): path for path in downloads}
                for future in concurrent.futures.as_completed(futures):
                    future.result()  # propaga falha de qualquer arquivo
            self._queue("update_ready_sync", staged, removals_path, version)
        except Exception as exc:
            self._queue("update_error", str(exc))

    def _launch_sync_update(self, staged: Path, removals_path: Path, version: str) -> None:
        """Abre o updater em modo sincronização com rollback protegido."""
        updater_path = app_base_dir() / "SigUpdater.exe"
        if not updater_path.is_file():
            self._queue("update_error", "SigUpdater.exe não foi encontrado ao lado do SIG.")
            return
        temporary_updater = Path(tempfile.gettempdir()) / f"SigUpdater-{uuid.uuid4().hex}.exe"
        flags = 0
        if os.name == "nt":
            flags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        try:
            shutil.copy2(updater_path, temporary_updater)
            subprocess.Popen(
                [
                    str(temporary_updater),
                    "--sync-staged",
                    str(staged),
                    "--sync-removals",
                    str(removals_path),
                    "--sync-version",
                    str(version),
                    "--target",
                    str(app_base_dir()),
                    "--pid",
                    str(os.getpid()),
                    "--log",
                    str(app_base_dir() / "updater.log"),
                ],
                creationflags=flags,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._append_activity_log(
                f"Sincronização {version} pronta. Reiniciando o SIG...", "warning"
            )
            self.root.after(250, self.root.destroy)
        except Exception as exc:
            self._queue("update_error", f"Não foi possível iniciar a sincronização: {exc}")

    def _update_download_worker(self, manifest: dict) -> None:
        version = str(manifest["version"])
        update_root = Path(tempfile.gettempdir()) / "sig_updater" / version
        zip_path = update_root / str(manifest["zip_name"])
        partial_path = zip_path.with_suffix(".zip.part")
        staging_dir = update_root / "staging"
        try:
            update_root.mkdir(parents=True, exist_ok=True)
            if partial_path.exists():
                partial_path.unlink()

            last_percent = -1

            def report_progress(downloaded: int, total: int):
                nonlocal last_percent
                if total > 0:
                    percent = min(100, int(downloaded * 100 / total))
                    if percent != last_percent:
                        last_percent = percent
                        self._queue("update_progress", f"Baixando atualização: {percent}%")
                else:
                    self._queue(
                        "update_progress",
                        f"Baixando atualização: {self._format_size(downloaded)}",
                    )

            digest = download_google_drive_file(
                str(manifest["zip_file_id"]),
                partial_path,
                report_progress,
            )
            expected_size = int(manifest["size"])
            actual_size = partial_path.stat().st_size
            if actual_size != expected_size:
                raise RuntimeError(
                    f"tamanho recebido diferente do manifesto ({actual_size} de {expected_size} bytes)"
                )
            if digest.lower() != str(manifest["sha256"]).lower():
                raise RuntimeError("o hash SHA-256 do pacote não confere")
            partial_path.replace(zip_path)

            self._queue("update_progress", "Validando atualização...")
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            staging_dir.mkdir(parents=True, exist_ok=True)
            self._validate_update_package_archive(zip_path, staging_dir)
            self._queue("update_ready", zip_path, version)
        except Exception as exc:
            shutil.rmtree(update_root, ignore_errors=True)
            self._queue("update_error", str(exc))

    @staticmethod
    def _validate_update_package_archive(zip_path: Path, staging_dir: Path) -> None:
        """Valida e extrai o pacote de atualização baixado.

        Formato diff (incremental v2, presença de ``removidos.txt``) exige
        apenas ``sig.exe``/``build-info.json``/``removidos.txt`` — os demais
        componentes ficam na instalação e são validados pelo updater (com
        rollback). Formato antigo (v1) exige o conjunto completo.

        Importante: esta função é a MESMA validação do updater do lado do
        SIG. Mudanças no formato de pacote precisam atualizar os DOIS lugares
        (veja release/INCREMENTAL_V2.md, seção "Peças afetadas").
        """
        total_uncompressed = 0
        seen_members = set()
        max_entries = 10_000
        max_total_uncompressed = 4 * 1024 * 1024 * 1024
        max_member_uncompressed = 1 * 1024 * 1024 * 1024
        with zipfile.ZipFile(zip_path, "r") as archive:
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise RuntimeError(f"entrada corrompida no pacote: {corrupt_member}")
            members = archive.infolist()
            if len(members) > max_entries:
                raise RuntimeError("o pacote excede o limite de entradas")
            for member in members:
                normalized_name = member.filename.replace("\\", "/").rstrip("/")
                pure_path = PurePosixPath(normalized_name)
                if (
                    pure_path.is_absolute()
                    or ".." in pure_path.parts
                    or not pure_path.parts
                    or member.flag_bits & 0x1
                ):
                    raise RuntimeError(f"entrada inválida no pacote: {member.filename}")
                if any(
                    "\x00" in part
                    or ":" in part
                    or part.endswith((" ", "."))
                    or part.casefold() in {"g", "dist"}
                    or part.casefold().startswith("_mei")
                    for part in pure_path.parts
                ):
                    raise RuntimeError(f"nome incompatível no pacote: {member.filename}")
                key = normalized_name.casefold()
                if key in seen_members:
                    raise RuntimeError(f"entrada duplicada no pacote: {member.filename}")
                seen_members.add(key)
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise RuntimeError(f"link simbólico não permitido: {member.filename}")
                if member.file_size > max_member_uncompressed:
                    raise RuntimeError(f"entrada individual grande demais: {member.filename}")
                total_uncompressed += member.file_size
                if total_uncompressed > max_total_uncompressed:
                    raise RuntimeError("o pacote descompactado excede o limite permitido")
            # Pacotes por diff (incremental v2) trazem apenas o que mudou;
            # os componentes essenciais ficam na instalação e a validação
            # final é feita pelo updater (com rollback).
            if "removidos.txt" in seen_members:
                required_members = {"sig.exe", "build-info.json", "removidos.txt"}
            else:
                required_members = {
                    "sig.exe",
                    "_internal/base_library.zip",
                    "_internal/python311.dll",
                    "_internal/vcruntime140.dll",
                    "_internal/vcruntime140_1.dll",
                    "_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll",
                    "SigUpdater.exe",
                }
            missing = sorted(
                item for item in required_members
                if item.casefold() not in seen_members
            )
            if missing:
                raise RuntimeError("componentes obrigatórios ausentes: " + ", ".join(missing))
            for member in members:
                normalized_name = member.filename.replace("\\", "/").rstrip("/")
                target = (staging_dir / Path(*PurePosixPath(normalized_name).parts)).resolve()
                if not target.is_relative_to(staging_dir.resolve()):
                    raise RuntimeError(f"destino inválido no pacote: {member.filename}")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 256)
        for required in required_members:
            required_path = staging_dir / Path(*PurePosixPath(required).parts)
            if not required_path.is_file():
                raise RuntimeError(f"arquivo obrigatório ausente ou vazio: {required}")
            # removidos.txt vazio é válido (diff sem remoções).
            if required != "removidos.txt" and required_path.stat().st_size <= 0:
                raise RuntimeError(f"arquivo obrigatório ausente ou vazio: {required}")

    @staticmethod
    def _update_script_text() -> str:
        return r'''param(
    [int]$ProcessId,
    [string]$SourceDir,
    [string]$TargetDir,
    [string]$ExeName,
    [string]$LogPath
)
$ErrorActionPreference = "Stop"
$logParent = Split-Path -Parent $LogPath
New-Item -ItemType Directory -Path $logParent -Force | Out-Null
Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format s) Atualizador iniciado."
function Resolve-SigInstallDir([string]$Candidate) {
    $original = [IO.Path]::GetFullPath($Candidate)
    $current = $original
    for ($level = 0; $level -lt 6; $level++) {
        $hasRuntime = (
            (Test-Path -LiteralPath (Join-Path $current "ffmpeg.exe") -PathType Leaf) -or
            (Test-Path -LiteralPath (Join-Path $current "ffplay.exe") -PathType Leaf) -or
            (Test-Path -LiteralPath (Join-Path $current "vad_deps") -PathType Container)
        )
        if ($hasRuntime) {
            return $current
        }
        $parent = Split-Path -Parent $current
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -ieq $current) {
            break
        }
        $current = $parent
    }
    return $original
}
$receivedTargetDir = $TargetDir
$TargetDir = Resolve-SigInstallDir $TargetDir
Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format s) Destino recebido=$receivedTargetDir; destino resolvido=$TargetDir; origem=$SourceDir"
$targetExe = Join-Path $TargetDir $ExeName
$deadline = [DateTime]::UtcNow.AddSeconds(120)
while (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
    if ([DateTime]::UtcNow -ge $deadline) {
        Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format s) Tempo esgotado aguardando o SIG fechar."
        exit 2
    }
    Start-Sleep -Milliseconds 250
}
# A janela do onefile pode pertencer a um processo filho enquanto o bootloader
# continua vivo. Aguarde todos os processos que executam este mesmo sig.exe.
while ($true) {
    $sameExecutable = @(Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($ExeName)) -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -ieq $targetExe } catch { $false }
    })
    if ($sameExecutable.Count -eq 0) { break }
    if ([DateTime]::UtcNow -ge $deadline) {
        Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format s) Tempo esgotado aguardando todos os processos do SIG fecharem."
        exit 3
    }
    Start-Sleep -Milliseconds 250
}
Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format s) Todos os processos do SIG encerrados; aplicando arquivos."
Start-Sleep -Seconds 2
$backupDir = Join-Path ([IO.Path]::GetTempPath()) ("sig_backup_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$copied = New-Object System.Collections.Generic.List[string]
$replacedDirectories = New-Object System.Collections.Generic.List[string]
function Start-SigDetached([string]$Executable, [string]$LogFile) {
    $workDirectory = Split-Path -Parent $Executable
    $process = Start-Process -FilePath $Executable -WorkingDirectory $workDirectory -WindowStyle Hidden -PassThru
    Add-Content -LiteralPath $LogFile -Value "$(Get-Date -Format s) SIG iniciado (PID $($process.Id))."
    return $process
}
function Start-SigAndVerify([string]$Executable, [string]$LogFile) {
    $workDirectory = Split-Path -Parent $Executable
    Add-Content -LiteralPath $LogFile -Value "$(Get-Date -Format s) Iniciando SIG atualizado diretamente."
    $process = Start-Process -FilePath $Executable -WorkingDirectory $workDirectory -WindowStyle Hidden -PassThru
    # O primeiro boot de um onefile pode precisar extrair o Python para %TEMP%.
    # Aguarde essa etapa e confirme que o processo permaneceu vivo antes de
    # apagar o backup que permite voltar à versão anterior.
    Start-Sleep -Seconds 12
    if ($process.HasExited) {
        throw "O SIG atualizado encerrou durante a inicialização (código $($process.ExitCode))."
    }
    $running = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if (-not $running) {
        throw "O SIG atualizado não permaneceu em execução após a inicialização."
    }
    Add-Content -LiteralPath $LogFile -Value "$(Get-Date -Format s) SIG atualizado confirmado em execução (PID $($process.Id))."
    return $process
}
function Install-FileWithRetry([string]$Source, [string]$Target) {
    $lastError = $null
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        try {
            Copy-Item -LiteralPath $Source -Destination $Target -Force
            Remove-Item -LiteralPath $Source -Force -ErrorAction SilentlyContinue
            return
        } catch {
            $lastError = $_.Exception
            Start-Sleep -Milliseconds 250
        }
    }
    throw "Não foi possível substituir $Target após 20 tentativas: $($lastError.Message)"
}
function Write-TargetDiagnostics([string]$Label) {
    $stamp = Get-Date -Format s
    $target = Get-Item -LiteralPath $targetExe -ErrorAction SilentlyContinue
    if ($target) {
        Add-Content -LiteralPath $LogPath -Value "$stamp ${Label}: executável=$($target.FullName), tamanho=$($target.Length) bytes"
    } else {
        Add-Content -LiteralPath $LogPath -Value "$stamp ${Label}: executável ausente=$targetExe"
    }
    $internal = Join-Path $TargetDir "_internal"
    if (Test-Path -LiteralPath $internal -PathType Container) {
        $pythonDll = Join-Path $internal "python311.dll"
        $vcDll = Join-Path $internal "vcruntime140.dll"
        $vc1Dll = Join-Path $internal "vcruntime140_1.dll"
        $fileCount = @(Get-ChildItem -LiteralPath $internal -Recurse -File -ErrorAction SilentlyContinue).Count
        Add-Content -LiteralPath $LogPath -Value "$stamp ${Label}: onedir=_internal presente, arquivos=$fileCount, python311.dll=$([bool](Test-Path -LiteralPath $pythonDll -PathType Leaf)), vcruntime140.dll=$([bool](Test-Path -LiteralPath $vcDll -PathType Leaf)), vcruntime140_1.dll=$([bool](Test-Path -LiteralPath $vc1Dll -PathType Leaf))"
    } else {
        Add-Content -LiteralPath $LogPath -Value "$stamp ${Label}: onedir=_internal ausente"
    }
}
try {
    $newProcess = $null
    # Copy top-level directories as units. This avoids deriving relative paths
    # from mixed Windows short/long names (JOOPAU~1 versus João Paulo).
    foreach ($sourceDirectory in @(Get-ChildItem -LiteralPath $SourceDir -Directory -Force)) {
        $relativeDir = $sourceDirectory.Name
        $targetDirectory = Join-Path $TargetDir $relativeDir
        if (Test-Path -LiteralPath $targetDirectory) {
            $backupDirectory = Join-Path $backupDir $relativeDir
            Copy-Item -LiteralPath $targetDirectory -Destination $backupDirectory -Recurse -Force
            Remove-Item -LiteralPath $targetDirectory -Recurse -Force
        }
        $replacedDirectories.Add($relativeDir)
        Copy-Item -LiteralPath $sourceDirectory.FullName -Destination $TargetDir -Recurse -Force
    }
    Get-ChildItem -LiteralPath $SourceDir -File -Force | ForEach-Object {
        $relative = $_.Name
        $target = Join-Path $TargetDir $relative
        if (Test-Path -LiteralPath $target) {
            $backup = Join-Path $backupDir $relative
            Copy-Item -LiteralPath $target -Destination $backup -Force
        }
        $temporaryTarget = "$target.sig-new"
        Copy-Item -LiteralPath $_.FullName -Destination $temporaryTarget -Force
        Install-FileWithRetry $temporaryTarget $target
        $copied.Add($relative)
    }
    if (-not (Test-Path -LiteralPath $targetExe -PathType Leaf)) {
        throw "Executável atualizado não encontrado: $targetExe"
    }
    Write-TargetDiagnostics "Estrutura após a cópia"
    $sourceInternal = Join-Path $SourceDir "_internal"
    if (Test-Path -LiteralPath $sourceInternal -PathType Container) {
        foreach ($requiredDll in @("python311.dll", "vcruntime140.dll", "vcruntime140_1.dll")) {
            $requiredPath = Join-Path $TargetDir (Join-Path "_internal" $requiredDll)
            if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
                throw "Dependência onedir ausente após a cópia: $requiredPath"
            }
        }
    }
    $newProcess = Start-SigAndVerify $targetExe $LogPath
    Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format s) Atualização aplicada e validada."
    Remove-Item -LiteralPath $SourceDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue
    exit 0
} catch {
    Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format s) Falha na atualização: $($_.Exception.Message)"
    Write-TargetDiagnostics "Estrutura no momento da falha"
    if ($newProcess -and -not $newProcess.HasExited) {
        Stop-Process -Id $newProcess.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
    foreach ($relativeDir in $replacedDirectories) {
        $targetDirectory = Join-Path $TargetDir $relativeDir
        $backupDirectory = Join-Path $backupDir $relativeDir
        Remove-Item -LiteralPath $targetDirectory -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $backupDirectory) {
            Copy-Item -LiteralPath $backupDirectory -Destination $targetDirectory -Recurse -Force
        }
    }
    foreach ($relative in $copied) {
        $backup = Join-Path $backupDir $relative
        $target = Join-Path $TargetDir $relative
        if (Test-Path -LiteralPath $backup) {
            Install-FileWithRetry $backup $target
        }
    }
    $targetExe = Join-Path $TargetDir $ExeName
    if (Test-Path -LiteralPath $targetExe -PathType Leaf) {
        Start-SigDetached $targetExe $LogPath
        Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format s) SIG original/revertido será aberto."
    }
    exit 1
}
'''

    def _launch_prepared_update(self, zip_path: Path, version: str) -> None:
        log_path = settings_path().parent / "updater.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(
                f"{time.strftime('%Y-%m-%dT%H:%M:%S')} "
                "Preparando o atualizador independente.\n"
            )
        staged_updater = zip_path.parent / "staging" / "SigUpdater.exe"
        updater_path = staged_updater if staged_updater.is_file() else app_base_dir() / "SigUpdater.exe"
        if not updater_path.is_file():
            detail = (
                "SigUpdater.exe não foi encontrado ao lado do SIG. "
                "É necessária uma instalação completa para habilitar "
                "as atualizações automáticas."
            )
            self.update_installing = False
            self.update_button.configure(state="normal")
            self.update_button_var.set("Atualização disponível")
            self._append_activity_log(f"Falha ao iniciar o atualizador: {detail}", "warning")
            messagebox.showerror("Atualização do SIG", detail)
            return
        temporary_updater = (
            Path(tempfile.gettempdir()) /
            f"SigUpdater-{uuid.uuid4().hex}.exe"
        )
        flags = 0
        if os.name == "nt":
            flags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        try:
            shutil.copy2(updater_path, temporary_updater)
            with log_path.open("a", encoding="utf-8") as log_file:
                source_label = "pacote baixado" if updater_path == staged_updater else "instalação atual"
                log_file.write(
                    f"{time.strftime('%Y-%m-%dT%H:%M:%S')} "
                    f"Usando SigUpdater.exe da {source_label}.\n"
                )
            subprocess.Popen(
                [
                    str(temporary_updater),
                    "--zip",
                    str(zip_path),
                    "--target",
                    str(app_base_dir()),
                    "--pid",
                    str(os.getpid()),
                    "--log",
                    str(log_path),
                ],
                creationflags=flags,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} Falha ao iniciar o processo auxiliar: {exc}\n")
            self.update_installing = False
            self.update_button.configure(state="normal")
            self.update_button_var.set("Atualização disponível")
            self._append_activity_log(f"Falha ao iniciar o atualizador: {exc}", "warning")
            messagebox.showerror("Atualização do SIG", f"Não foi possível iniciar o atualizador:\n{exc}")
            return
        self._append_activity_log(f"Atualização {version} pronta. Reiniciando o SIG...")
        self.root.after(250, self.root.destroy)

    def _build_ui(self):
        import tkinter as tk
        from tkinter import font as tkfont

        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill=BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=X)
        self.update_button = ttk.Button(
            top,
            textvariable=self.update_button_var,
            style="Update.TButton",
            command=self.install_available_update,
        )
        model_summary = ttk.Frame(top)
        model_summary.pack(side=LEFT, anchor="nw")
        ttk.Label(
            model_summary,
            text="Modelo de transcrição:",
            style="ModelSummary.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            model_summary,
            textvariable=self.transcription_model_display_var,
            style="ModelSummary.TLabel",
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(
            model_summary,
            text="Modelo(s) de texto:",
            style="ModelSummary.TLabel",
        ).grid(row=1, column=0, sticky="w")
        ttk.Label(
            model_summary,
            textvariable=self.text_model_display_var,
            style="ModelSummary.TLabel",
        ).grid(row=1, column=1, sticky="w", padx=(8, 0))
        self.multi_controls = ttk.Frame(top)
        self.multi_transcription_check = ttk.Checkbutton(
            self.multi_controls,
            text="Multi model - transcrição",
            variable=self.multi_model_var,
            command=self._toggle_multi_model,
        )
        self.multi_transcription_check.grid(row=0, column=0, sticky="e")
        ttk.Button(
            self.multi_controls,
            text="?",
            width=2,
            command=self._show_multi_model_help,
        ).grid(row=0, column=1, sticky="w", padx=(4, 0))
        self.multi_text_check = ttk.Checkbutton(
            self.multi_controls,
            text="Multi model - texto",
            variable=self.multi_text_model_var,
            command=self._toggle_multi_text_model,
        )
        self.multi_text_check.grid(row=1, column=0, sticky="w")
        self.multi_text_help_button = ttk.Button(
            self.multi_controls,
            text="?",
            width=2,
            command=self._show_multi_text_help,
        )
        self.multi_text_help_button.grid(row=1, column=1, sticky="w", padx=(4, 0))

        tab_bar = tk.Frame(outer, background="#f4f7f6")
        tab_bar.pack(fill=X, pady=(12, 0))
        tab_font = ("Segoe UI Semibold", 10)
        tab_width = len("Transcrição") + 1
        self.live_tab_button = tk.Label(
            tab_bar,
            text="Ocorrência",
            width=tab_width,
            height=1,
            borderwidth=1,
            relief="solid",
            font=tab_font,
            cursor="hand2",
        )
        self.files_tab_button = tk.Label(
            tab_bar,
            text="Transcrição",
            width=tab_width,
            height=1,
            borderwidth=1,
            relief="solid",
            font=tab_font,
            cursor="hand2",
        )
        self.imei_tab_button = tk.Label(
            tab_bar,
            text="IMEI",
            width=tab_width,
            height=1,
            borderwidth=1,
            relief="solid",
            font=tab_font,
            cursor="hand2",
        )
        self.ffmpeg_tab_button = tk.Label(
            tab_bar,
            text="FFmpeg",
            width=tab_width,
            height=1,
            borderwidth=1,
            relief="solid",
            font=tab_font,
            cursor="hand2",
        )
        self.qualification_tab_button = tk.Label(
            tab_bar,
            text="Qualificação",
            width=tab_width,
            height=1,
            borderwidth=1,
            relief="solid",
            font=tab_font,
            cursor="hand2",
        )
        self.live_tab_button.pack(side=LEFT)
        self.files_tab_button.pack(side=LEFT, padx=(4, 0))
        self.qualification_tab_button.pack(side=LEFT, padx=(4, 0))
        self.imei_tab_button.pack(side=LEFT, padx=(4, 0))
        self.ffmpeg_tab_button.pack(side=LEFT, padx=(4, 0))
        self.live_tab_button.bind("<Button-1>", lambda _event: self.select_main_tab("live"))
        self.files_tab_button.bind("<Button-1>", lambda _event: self.select_main_tab("files"))
        self.imei_tab_button.bind("<Button-1>", lambda _event: self.select_main_tab("imei"))
        self.ffmpeg_tab_button.bind("<Button-1>", lambda _event: self.select_main_tab("ffmpeg"))
        self.qualification_tab_button.bind(
            "<Button-1>", lambda _event: self.select_main_tab("qualification")
        )
        self.root.after_idle(self._align_multi_controls)

        workspace = ttk.Frame(outer)
        workspace.pack(fill=BOTH, expand=True)
        self.tab_content = ttk.Frame(workspace, width=1)
        self.tab_content.pack(side=LEFT, fill=BOTH, expand=True)
        self.tab_content.pack_propagate(False)
        log_font = tkfont.Font(family="Consolas", size=8)
        log_sample = "00:21:11  Multi model ativado: Grok STT + servidor."
        activity_width = log_font.measure(log_sample) + 38
        activity_panel = ttk.Frame(workspace, width=activity_width)
        # Match the bottom edge of the log with the bottom edge of the live
        # occurrence controls, which use the live tab's bottom inset.
        activity_panel.pack(
            side=RIGHT,
            fill=Y,
            expand=False,
            padx=(14, 0),
            pady=(0, 14),
        )
        activity_panel.pack_propagate(False)
        self.live_waveform_canvas = Canvas(
            activity_panel,
            width=activity_width,
            height=44,
            highlightthickness=0,
            background="#f4f7f6",
        )
        self.live_waveform_canvas.pack(side=TOP, fill=X, anchor="w")
        self.live_waveform_canvas.bind(
            "<Configure>", lambda _event: self._draw_live_waveform(), add="+"
        )
        self._draw_live_waveform()
        self.root.after(50, self._refresh_live_waveform)
        activity_box = ttk.Frame(activity_panel)
        activity_box.pack(fill=BOTH, expand=True, pady=(10, 0))
        self.activity_box = activity_box
        self.activity_log = Text(activity_box, width=1, wrap="none", state="disabled", font=("Consolas", 8), background="#ffffff", foreground="#33403e", relief="solid", borderwidth=1, padx=7, pady=7)
        activity_scroll = ttk.Scrollbar(activity_box, orient="vertical", command=self.activity_log.yview)
        activity_hscroll = ttk.Scrollbar(activity_box, orient="horizontal", command=self.activity_log.xview)
        self.activity_log.configure(
            yscrollcommand=activity_scroll.set,
            xscrollcommand=activity_hscroll.set,
        )
        activity_box.columnconfigure(0, weight=1)
        activity_box.rowconfigure(0, weight=1)
        self.activity_log.grid(row=0, column=0, sticky="nsew")
        activity_scroll.grid(row=0, column=1, sticky="ns")
        activity_hscroll.grid(row=1, column=0, sticky="ew")

        self.live_tab = ttk.Frame(self.tab_content, padding=(14, 2, 14, 14))
        self.files_tab = ttk.Frame(self.tab_content, padding=14)
        self.assistant_tab = ttk.Frame(self.tab_content, padding=14)
        self.imei_tab = ttk.Frame(self.tab_content, padding=14)
        self.ffmpeg_tab = ttk.Frame(self.tab_content, padding=14)
        self.qualification_tab = ttk.Frame(self.tab_content, padding=14)

        # The live workflow intentionally keeps transcript, history and statement together,
        # matching the Android screen.  The old assistant frame remains internal only.
        live_frame = ttk.Frame(self.live_tab, width=900)
        live_frame.pack(fill=BOTH, expand=True, anchor="n")
        live_top = ttk.Frame(live_frame)
        live_top.pack(fill=X)
        self.live_top = live_top
        live_top.bind("<Configure>", self._on_live_top_configure, add="+")

        self.live_interval_minus = ttk.Button(live_top, text="-", width=3, command=lambda: self._change_live_interval(-1))
        self.live_interval_minus.pack(side=LEFT)
        ttk.Label(live_top, text=" t =", style="Muted.TLabel").pack(side=LEFT, padx=(6, 2))
        self.live_interval_entry = ttk.Combobox(
            live_top,
            textvariable=self.live_interval_var,
            values=tuple(f"{value / 1000:.1f}" for value in LIVE_INTERVAL_VALUES_MS),
            width=5,
            justify="center",
            state="readonly",
        )
        self.live_interval_entry.pack(side=LEFT)
        self.live_interval_entry.bind("<<ComboboxSelected>>", lambda _event: self._apply_live_interval_entry())
        self.live_interval_plus = ttk.Button(live_top, text="+", width=3, command=lambda: self._change_live_interval(1))
        self.live_interval_plus.pack(side=LEFT, padx=(6, 8))
        self.live_timestamps_check = ttk.Checkbutton(
            live_top,
            text="Timestamps",
            variable=self.live_timestamps_var,
            command=self._toggle_live_timestamps,
            state="disabled",
        )
        self.live_timestamps_check.pack(side=LEFT, padx=(0, 10))
        self.live_grok_controls = ttk.Frame(live_top)
        ttk.Checkbutton(
            self.live_grok_controls,
            text="Diarização",
            variable=self.live_diarize_var,
            command=lambda: self._set_activity_status(
                "Diarização ativada." if self.live_diarize_var.get() else "Diarização desativada.",
                log=False,
            ),
        ).pack(side=LEFT)
        self.live_diarize_help = ttk.Button(self.live_grok_controls, text="?", width=2, command=self.show_live_diarization_help)
        self.live_diarize_help.pack(side=LEFT, padx=(4, 8))
        self.live_language_button = ttk.Menubutton(self.live_grok_controls, textvariable=self.live_language_label_var, width=17)
        self.live_language_menu = tk.Menu(self.live_language_button, tearoff=False)
        for code, label in LIVE_LANGUAGES:
            self.live_language_menu.add_command(label=label, command=lambda selected=code: self._set_live_language(selected))
        self.live_language_button.configure(menu=self.live_language_menu)
        self.live_language_button.pack(side=LEFT)
        self.live_grok_controls.pack(side=LEFT)
        self.live_top_spacer = ttk.Frame(live_top)
        self.live_top_spacer.pack(side=LEFT, fill=X, expand=True)
        self.live_normal_mic_canvas = Canvas(live_top, width=44, height=44, highlightthickness=0, background="#f4f7f6")
        self.live_normal_mic_canvas.pack(side=LEFT, padx=(0, 8))
        self.live_normal_mic_canvas.bind("<Button-1>", lambda _event: self.start_normal_live_recording())
        self._draw_normal_live_mic_button()
        self.live_pause_canvas = Canvas(live_top, width=44, height=44, highlightthickness=0, background="#f4f7f6")
        self.live_pause_canvas.pack(side=LEFT, padx=(0, 8))
        self.live_pause_canvas.bind("<Button-1>", lambda _event: self.toggle_live_mic())
        # Keep the red live microphone at its original row height. The optional
        # integral-audio recovery button is overlaid at the far right below.
        self.live_mic_stack = ttk.Frame(live_top, width=44, height=44)
        self.live_mic_stack.pack(side=LEFT, padx=(0, 8))
        self.live_mic_stack.pack_propagate(False)
        self.live_recover_audio_button = ttk.Button(
            live_top,
            image=self.recover_audio_icon,
            style="Recover.TButton",
            command=self.recover_live_integral_audio,
        )
        create_tooltip(
            self.live_recover_audio_button,
            "Reenviar o áudio integral ao Grok por REST",
        )
        self.live_mic_canvas = Canvas(
            self.live_mic_stack,
            width=44,
            height=44,
            highlightthickness=0,
            background="#f4f7f6",
        )
        self.live_mic_canvas.place(x=0, y=0)
        self.live_mic_canvas.bind("<Button-1>", lambda _event: self.start_live_mic() if self.live_state == "idle" else self.stop_live_mic())
        self.live_timer_label = ttk.Label(
            live_top, textvariable=self.live_timer_var, style="Muted.TLabel"
        )
        self.live_timer_label.pack(side=LEFT)

        self.live_transcript_area = ttk.Frame(live_frame, width=900)
        self.live_transcript_area.pack(fill=X)
        self.live_primary_pane = ttk.Frame(self.live_transcript_area)
        self.live_primary_pane.pack(side=LEFT, fill=X, expand=True)
        self.live_secondary_pane = ttk.Frame(self.live_transcript_area)

        self.live_text = self._make_live_editor(
            self.live_primary_pane,
            "Transcrição",
            "transcript",
            width=900,
            height=150,
            vertical_padding=(0, 0),
        )
        self.live_transcript_actions = ttk.Frame(self.live_primary_pane)
        self.live_transcript_actions.pack(fill=X, pady=(4, 4))
        self.live_recover_button = ttk.Button(
            self.live_transcript_actions,
            image=self.recover_icon,
            style="Recover.TButton",
            command=self.recover_live_transcript,
        )
        create_tooltip(self.live_recover_button, "Recuperar transcrição")
        self.live_history_button = ttk.Button(
            self.live_transcript_actions,
            text="Histórico",
            style="Action.TButton",
            width=9,
            command=self.request_live_history,
        )
        self.live_clear_button = self._make_editor_icon_button(
            self.live_transcript_actions, self.clear_icon, "Limpar", lambda: self.clear_live_editor("transcript")
        )
        self.live_copy_button = self._make_editor_icon_button(
            self.live_transcript_actions, self.copy_icon, "Copiar", lambda: self.copy_live_editor("transcript")
        )
        self.live_paste_button = self._make_editor_icon_button(
            self.live_transcript_actions, self.paste_icon, "Colar", lambda: self.paste_live_editor("transcript")
        )

        self.live_text_2 = self._make_live_editor(
            self.live_secondary_pane,
            "Transcrição 2",
            "transcript2",
            width=440,
            height=150,
            vertical_padding=(0, 0),
        )
        self.live_transcript_actions_2 = ttk.Frame(self.live_secondary_pane)
        self.live_transcript_actions_2.pack(fill=X, pady=(4, 4))
        self.live_recover_button_2 = ttk.Button(
            self.live_transcript_actions_2,
            image=self.recover_icon,
            style="Recover.TButton",
            command=self.recover_live_transcript_2,
        )
        create_tooltip(self.live_recover_button_2, "Recuperar transcrição")
        self.live_history_button_2 = ttk.Button(
            self.live_transcript_actions_2,
            text="Histórico",
            style="Action.TButton",
            width=9,
            command=self.request_live_history_2,
        )
        self.live_clear_button_2 = self._make_editor_icon_button(
            self.live_transcript_actions_2, self.clear_icon, "Limpar", lambda: self.clear_live_editor("transcript2")
        )
        self.live_copy_button_2 = self._make_editor_icon_button(
            self.live_transcript_actions_2, self.copy_icon, "Copiar", lambda: self.copy_live_editor("transcript2")
        )
        self.live_paste_button_2 = self._make_editor_icon_button(
            self.live_transcript_actions_2, self.paste_icon, "Colar", lambda: self.paste_live_editor("transcript2")
        )
        for actions in (self.live_transcript_actions, self.live_transcript_actions_2):
            actions.bind("<Configure>", lambda _event: self._position_live_parts_button(), add="+")
        for part_var in (self.live_assistant_part_var, self.live_assistant_part_var_2):
            part_var.trace_add(
                "write",
                lambda *_args: self.root.after_idle(self._position_live_parts_buttons),
            )
        self._refresh_primary_transcript_actions(False)

        self.live_history_area = ttk.Frame(live_frame, width=900)
        self.live_history_area.pack(fill=X)
        self.live_history_area.columnconfigure(0, weight=1, uniform="live_history_panes")
        self.live_history_area.columnconfigure(1, minsize=10)
        self.live_history_area.columnconfigure(2, weight=1, uniform="live_history_panes")
        self.live_history_primary_pane = ttk.Frame(self.live_history_area)
        self.live_history_primary_pane.grid(row=0, column=0, sticky="ew")
        self.live_history_secondary_pane = ttk.Frame(self.live_history_area)
        self.live_history_text = self._make_live_editor(
            self.live_history_primary_pane,
            "Histórico",
            "history",
            width=900,
            height=150,
            vertical_padding=(0, 0),
        )
        self.live_history_text_2 = self._make_live_editor(
            self.live_history_secondary_pane,
            "Histórico 2",
            "history2",
            width=440,
            height=150,
            vertical_padding=(0, 0),
        )

        def build_history_actions(parent, suffix: str, statement_command, part_var: StringVar):
            actions = ttk.Frame(parent)
            actions.pack(fill=X, pady=(4, 4))
            recover_button = ttk.Button(
                actions,
                image=self.recover_icon,
                style="Recover.TButton",
                command=lambda kind=suffix: self.recover_live_assistant_text(kind),
            )
            create_tooltip(recover_button, "Recuperar histórico")
            parts_button = ttk.Menubutton(
                actions,
                textvariable=part_var,
                style="Action.TMenubutton",
                width=6,
                padding=(5, -1),
            )
            parts_menu = tk.Menu(parts_button, tearoff=False)
            parts_button.configure(menu=parts_menu)
            statement_button = ttk.Button(
                actions, text="Oitiva", style="Action.TButton", width=9, command=statement_command
            )
            statement_button.place(relx=0.5, y=0, anchor="n")
            self._make_editor_icon_button(
                actions, self.paste_icon, "Colar", lambda: self.paste_live_editor(suffix)
            ).pack(side=RIGHT)
            self._make_editor_icon_button(
                actions, self.copy_icon, "Copiar", lambda: self.copy_live_editor(suffix)
            ).pack(side=RIGHT, padx=(0, 4))
            clear_button = self._make_editor_icon_button(
                actions, self.clear_icon, "Limpar", lambda: self.clear_live_editor(suffix)
            )
            clear_button.pack(side=RIGHT, padx=(0, 4))
            actions.bind("<Configure>", lambda _event: self._position_live_parts_buttons(), add="+")
            return recover_button, parts_button, parts_menu, statement_button, clear_button

        (
            self.live_history_recover_button,
            self.live_parts_button,
            self.live_parts_menu,
            self.live_statement_button,
            self.live_history_clear_button,
        ) = build_history_actions(
            self.live_history_primary_pane, "history", self.request_live_statement, self.live_assistant_part_var
        )
        (
            self.live_history_recover_button_2,
            self.live_parts_button_2,
            self.live_parts_menu_2,
            self.live_statement_button_2,
            self.live_history_clear_button_2,
        ) = build_history_actions(
            self.live_history_secondary_pane, "history2", self.request_live_statement_2, self.live_assistant_part_var_2
        )

        self.live_statement_area = ttk.Frame(live_frame, width=900)
        self.live_statement_area.pack(fill=X)
        self.live_statement_area.columnconfigure(0, weight=1, uniform="live_statement_panes")
        self.live_statement_area.columnconfigure(1, minsize=10)
        self.live_statement_area.columnconfigure(2, weight=1, uniform="live_statement_panes")
        self.live_statement_primary_pane = ttk.Frame(self.live_statement_area)
        self.live_statement_primary_pane.grid(row=0, column=0, sticky="ew")
        self.live_statement_secondary_pane = ttk.Frame(self.live_statement_area)
        self.live_statement_text = self._make_live_editor(
            self.live_statement_primary_pane,
            "Oitiva",
            "statement",
            width=900,
            height=150,
            vertical_padding=(0, 0),
        )
        self.live_statement_text_2 = self._make_live_editor(
            self.live_statement_secondary_pane,
            "Oitiva 2",
            "statement2",
            width=440,
            height=150,
            vertical_padding=(0, 0),
        )

        def build_statement_actions(parent, suffix: str, show_progress: bool = False):
            actions = ttk.Frame(parent)
            actions.pack(fill=X, pady=(4, 4))
            recover_button = ttk.Button(
                actions,
                image=self.recover_icon,
                style="Recover.TButton",
                command=lambda kind=suffix: self.recover_live_assistant_text(kind),
            )
            recover_button.place(x=0, y=0)
            create_tooltip(recover_button, "Recuperar oitiva")
            self._make_editor_icon_button(
                actions, self.paste_icon, "Colar", lambda: self.paste_live_editor(suffix)
            ).pack(side=RIGHT)
            self._make_editor_icon_button(
                actions, self.copy_icon, "Copiar", lambda: self.copy_live_editor(suffix)
            ).pack(side=RIGHT, padx=(0, 4))
            self._make_editor_icon_button(
                actions, self.clear_icon, "Limpar", lambda: self.clear_live_editor(suffix)
            ).pack(side=RIGHT, padx=(0, 4))
            if show_progress:
                ttk.Label(
                    actions, textvariable=self.live_assistant_progress_var, style="Muted.TLabel"
                ).pack(side=RIGHT)
            return recover_button

        self.live_statement_recover_button = build_statement_actions(
            self.live_statement_primary_pane, "statement", True
        )
        self.live_statement_recover_button_2 = build_statement_actions(
            self.live_statement_secondary_pane, "statement2"
        )
        self._refresh_multi_text_visibility()

        self.live_qualification_row = ttk.Frame(live_frame, width=900)
        self.live_qualification_row.pack(fill=BOTH, expand=True)
        self.live_qualification_content = ttk.Frame(self.live_qualification_row)
        # The lower occurrence workspace must use all remaining height.  Packing
        # it only at the bottom allowed the A4 preview request to clip the
        # qualification editor on shorter windows.
        self.live_qualification_content.pack(fill=BOTH, expand=True)
        self.live_qualification_content.rowconfigure(0, weight=1)
        self.live_qualification_content.columnconfigure(
            0, minsize=640, weight=0
        )
        self.live_qualification_content.columnconfigure(1, minsize=18, weight=0)
        self.live_qualification_content.columnconfigure(
            2, weight=1
        )
        self.live_qualification_area = ttk.Frame(
            self.live_qualification_content,
            width=640,
        )
        self.live_qualification_area.grid(row=0, column=0, sticky="nsew")
        self.live_qualification_stack = ttk.Frame(self.live_qualification_area)
        self.live_qualification_stack.pack(side="bottom", fill=X)

        def select_qualification_type(selected: str):
            if selected == "declarations":
                if self.qualification_declarations_var.get():
                    self.qualification_deposition_var.set(False)
                else:
                    self.qualification_declarations_var.set(True)
            else:
                if self.qualification_deposition_var.get():
                    self.qualification_declarations_var.set(False)
                else:
                    self.qualification_deposition_var.set(True)

        self.live_qualification_text_row = ttk.Frame(self.live_qualification_stack)
        self.live_qualification_text_row.pack(fill=X)
        self.live_qualification_editor_host = ttk.Frame(
            self.live_qualification_text_row,
            width=346,
            height=135,
        )
        self.live_qualification_editor_host.pack(side=LEFT, fill=Y)
        self.live_qualification_editor_host.pack_propagate(False)
        self.live_qualification_text = self._make_live_editor(
            self.live_qualification_editor_host,
            "Qualificação",
            "qualification",
            width=346,
            height=135,
            vertical_padding=(0, 0),
        )
        self.live_qualification_execute_frame = ttk.Frame(self.live_qualification_content)
        self.live_qualification_declarations_check = ttk.Checkbutton(
            self.live_qualification_execute_frame,
            text="Declarações",
            variable=self.qualification_declarations_var,
            command=lambda: select_qualification_type("declarations"),
        )
        self.live_qualification_declarations_check.pack(anchor="w")
        self.live_qualification_deposition_check = ttk.Checkbutton(
            self.live_qualification_execute_frame,
            text="Depoimento",
            variable=self.qualification_deposition_var,
            command=lambda: select_qualification_type("deposition"),
        )
        self.live_qualification_deposition_check.pack(anchor="w", pady=(2, 6))
        self.live_document_execute_button = ttk.Button(
            self.live_qualification_execute_frame,
            text="Gerar\ndocumento",
            style="Execute.TButton",
            command=self.generate_occurrence_document,
        )
        self.live_document_execute_button.pack()

        self.live_qualification_actions = ttk.Frame(
            self.live_qualification_stack,
            width=346,
            height=31,
        )
        self.live_qualification_actions.pack(anchor="w", pady=(4, 0))
        self.live_qualification_actions.pack_propagate(False)
        self.live_qualification_recover_button = ttk.Button(
            self.live_qualification_actions,
            image=self.recover_icon,
            style="Recover.TButton",
            command=self.recover_live_qualification,
        )
        create_tooltip(
            self.live_qualification_recover_button,
            "Recuperar o último texto de qualificação gerado pelo app",
        )
        self.live_qualification_clear_button = self._make_editor_icon_button(
            self.live_qualification_actions,
            self.clear_icon,
            "Limpar",
            lambda: self.clear_live_editor("qualification"),
        )
        self.live_qualification_copy_button = self._make_editor_icon_button(
            self.live_qualification_actions,
            self.copy_icon,
            "Copiar",
            lambda: self.copy_live_editor("qualification"),
        )
        self.live_qualification_paste_button = self._make_editor_icon_button(
            self.live_qualification_actions,
            self.paste_icon,
            "Colar",
            lambda: self.paste_live_editor("qualification"),
        )
        self.live_document_preview_panel = ttk.Frame(self.live_qualification_content)
        self.live_document_preview_panel.grid(row=0, column=2, sticky="nsew")
        self.live_document_preview_toolbar = ttk.Frame(self.live_document_preview_panel)
        self.live_document_preview_toolbar.pack(anchor="w")
        self.live_document_preview_toolbar.pack_propagate(False)
        # Keep zoom independent from the toolbar. It is positioned below the
        # player, like the action row below the text editors, so it cannot be
        # covered when the preview is resized.
        self.live_document_zoom_frame = ttk.Frame(self.live_document_preview_panel)
        ttk.Label(
            self.live_document_zoom_frame,
            text="Zoom:",
            style="Muted.TLabel",
        ).pack(side=LEFT, padx=(0, 4))
        self.live_document_zoom_combo = ttk.Combobox(
            self.live_document_zoom_frame,
            textvariable=self.document_preview_zoom_var,
            values=("25%", "50%", "100%"),
            width=6,
            justify="center",
            state="disabled",
        )
        self.live_document_zoom_combo.pack(side=LEFT)
        self.live_document_zoom_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._refresh_embedded_document_preview(),
        )
        ttk.Label(
            self.live_document_preview_toolbar,
            textvariable=self.document_preview_page_var,
            style="DocumentPreview.TLabel",
        ).pack(side=LEFT, padx=(0, 10))

        # A área do preview mantém a proporção de uma página A4 em retrato.
        self.live_document_preview_stage = ttk.Frame(
            self.live_document_preview_panel,
            width=1120,
            height=520,
        )
        # The stage is positioned explicitly after the qualification editor is
        # laid out.  Packing it here would let it consume the same bottom space
        # needed by the document action buttons on shorter windows.
        self.live_document_preview_stage.place(
            x=0,
            y=24,
            width=1120,
            height=520,
        )
        self.live_document_preview_stage.pack_propagate(False)
        self.live_document_preview_viewport = ttk.Frame(
            self.live_document_preview_stage,
        )
        self.live_document_preview_viewport.pack(fill=BOTH, expand=True)
        self.live_document_preview_viewport.columnconfigure(0, weight=1)
        self.live_document_preview_viewport.rowconfigure(0, weight=1)
        self.live_document_preview_canvas = Canvas(
            self.live_document_preview_viewport,
            highlightthickness=0,
            borderwidth=1,
            relief="solid",
            background="#ffffff",
        )
        self.live_document_preview_yscroll = ttk.Scrollbar(
            self.live_document_preview_viewport,
            orient="vertical",
            command=self.live_document_preview_canvas.yview,
        )
        self.live_document_preview_canvas.configure(
            yscrollcommand=self._update_document_preview_scroll,
        )
        # O canvas é posicionado por _position_embedded_document_preview para
        # que a caixa da prévia abrace o documento (margens laterais mínimas)
        # em vez de esticar pelo viewport inteiro.
        self.live_document_preview_viewport.bind(
            "<Configure>",
            lambda _event: self._position_embedded_document_preview(),
            add="+",
        )
        self.live_document_preview_canvas.place(x=0, y=0)
        self.live_document_preview_yscroll.place(x=0, y=0)
        self.live_document_preview_canvas.bind(
            "<Configure>",
            lambda _event: self._position_embedded_document_preview(),
            add="+",
        )
        self.live_document_preview_canvas.bind(
            "<MouseWheel>",
            lambda event: self.live_document_preview_canvas.yview_scroll(
                -1 if event.delta > 0 else 1,
                "units",
            ),
            add="+",
        )
        self._set_embedded_document_preview_message("")

        self.live_document_actions_frame = ttk.Frame(
            self.live_document_preview_panel,
            width=222,
            height=66,
        )
        self.live_document_actions_frame.pack_propagate(False)
        self.live_document_copy_progress = ttk.Progressbar(
            self.live_document_preview_panel,
            mode="indeterminate",
        )
        self.live_document_copy_progress.place_forget()

        def document_action_button(text, image, command):
            holder = ttk.Frame(
                self.live_document_actions_frame,
                width=66,
                height=66,
            )
            holder.pack(side=LEFT, padx=(8, 0))
            holder.pack_propagate(False)
            button = ttk.Button(
                holder,
                text=text,
                image=image,
                compound=TOP,
                style="DocumentAction.TButton",
                command=command,
            )
            button.pack(fill=BOTH, expand=True)
            return button

        self.live_document_copy_button = document_action_button(
            "Copiar",
            self.document_copy_icon,
            self.copy_generated_occurrence_document,
        )
        self.live_document_view_button = document_action_button(
            "Visualizar",
            self.document_view_icon,
            self.open_document_viewer,
        )
        self.live_document_save_button = document_action_button(
            "Salvar",
            self.document_save_icon,
            self.save_generated_occurrence_document,
        )
        self.live_document_actions_frame.pack_forget()
        self.live_qualification_actions.bind(
            "<Configure>",
            lambda _event: self._position_live_document_controls(),
            add="+",
        )
        self.live_qualification_row.bind(
            "<Configure>",
            self._fit_live_document_preview,
            add="+",
        )
        self.live_document_preview_panel.bind(
            "<Configure>",
            lambda _event: self._position_live_document_preview(),
            add="+",
        )
        self._set_live_document_preview_visible(False)
        self.root.after_idle(self._position_live_document_controls)
        self.root.after_idle(self._fit_live_document_preview)

        self._draw_live_mic_button()
        self._draw_live_pause_button()
        self._refresh_live_grok_controls()

        assistant_frame = ttk.Frame(self.assistant_tab)
        assistant_frame.pack(fill=BOTH, expand=True)

        assistant_actions = ttk.Frame(assistant_frame)
        assistant_actions.pack(fill=X)
        self.assistant_history_button = ttk.Button(
            assistant_actions,
            text="Histórico",
            command=self.request_assistant_history,
        )
        self.assistant_history_button.pack(side=LEFT, padx=(0, 8))
        self.assistant_parts_button = ttk.Menubutton(
            assistant_actions,
            textvariable=self.assistant_part_var,
        )
        self.assistant_parts_menu = tk.Menu(self.assistant_parts_button, tearoff=False)
        self.assistant_parts_button.configure(menu=self.assistant_parts_menu)
        self.assistant_parts_button.pack(side=LEFT, padx=(0, 8))
        self.assistant_statement_button = ttk.Button(
            assistant_actions,
            text="Oitiva",
            command=self.request_assistant_statement,
        )
        self.assistant_statement_button.pack(side=LEFT)

        assistant_utilities = ttk.Frame(assistant_frame)
        assistant_utilities.pack(fill=X, pady=(10, 8))
        ttk.Button(assistant_utilities, text="Colar", command=self.paste_assistant_text).pack(side=LEFT, padx=(0, 8))
        ttk.Button(assistant_utilities, text="Copiar", command=self.copy_assistant_text).pack(side=LEFT, padx=(0, 8))
        ttk.Button(assistant_utilities, text="Salvar", command=self.save_assistant_text).pack(side=LEFT, padx=(0, 8))
        ttk.Button(assistant_utilities, text="Limpar", command=self.clear_assistant_text).pack(side=LEFT)
        ttk.Label(
            assistant_utilities,
            textvariable=self.assistant_progress_var,
            style="Muted.TLabel",
        ).pack(side=RIGHT)

        assistant_text_frame = ttk.Frame(assistant_frame)
        assistant_text_frame.pack(fill=BOTH, expand=True)
        self.assistant_text = Text(
            assistant_text_frame,
            height=22,
            wrap="word",
            undo=True,
            font=("Segoe UI", 10),
            background="#ffffff",
            foreground="#10201f",
            insertbackground="#10201f",
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=10,
        )
        assistant_scroll = ttk.Scrollbar(
            assistant_text_frame,
            orient="vertical",
            command=self.assistant_text.yview,
        )
        self.assistant_text.configure(yscrollcommand=assistant_scroll.set)
        self.assistant_text.pack(side=LEFT, fill=BOTH, expand=True)
        assistant_scroll.pack(side=RIGHT, fill=Y)
        ttk.Label(
            assistant_frame,
            textvariable=self.assistant_status_var,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(8, 0))
        self._set_assistant_names([])
        self._set_live_assistant_names([])
        self.root.after(100, self._position_live_parts_button)
        self._refresh_assistant_model_label()

        imei_frame = ttk.Frame(self.imei_tab)
        imei_frame.pack(fill=BOTH, expand=True)
        ttk.Label(imei_frame, text="IMEI", style="Muted.TLabel").pack(anchor="w", pady=(16, 4))

        imei_inputs = ttk.Frame(imei_frame, width=900)
        imei_inputs.pack(anchor="w")
        tac_box = ttk.Frame(imei_inputs)
        tac_box.pack(side=LEFT, padx=(0, 7))
        self.imei_tac_entry = ttk.Entry(
            tac_box,
            textvariable=self.imei_tac_var,
            font=("Consolas", 16),
            justify="center",
            width=48,
        )
        self.imei_tac_entry.pack()
        ttk.Label(tac_box, text="tac", style="Muted.TLabel").pack(anchor="center", pady=(3, 0))

        sn_box = ttk.Frame(imei_inputs)
        sn_box.pack(side=LEFT, padx=(7, 0))
        self.imei_sn_entry = ttk.Entry(
            sn_box,
            textvariable=self.imei_sn_var,
            font=("Consolas", 16),
            justify="center",
            width=36,
        )
        self.imei_sn_entry.pack()
        ttk.Label(sn_box, text="sn", style="Muted.TLabel").pack(anchor="center", pady=(3, 0))

        self.imei_tac_var.trace_add("write", lambda *_args: self._update_imei_inputs())
        self.imei_sn_var.trace_add("write", lambda *_args: self._update_imei_inputs())
        self.imei_sn_entry.bind("<BackSpace>", self._imei_sn_backspace)

        ttk.Label(
            imei_frame,
            textvariable=self.imei_result_var,
            foreground="#c48a00",
            font=("Segoe UI Semibold", 18),
        ).pack(anchor="center", pady=(18, 0))
        self._make_editor_icon_button(
            imei_frame,
            self.copy_icon,
            "Copiar IMEI completo",
            self.copy_full_imei,
        ).pack(anchor="center", pady=(4, 0))
        ttk.Label(
            imei_frame,
            textvariable=self.imei_model_var,
            font=("Segoe UI", 11),
            justify="center",
        ).pack(fill=X, pady=(10, 0))
        ttk.Label(
            imei_frame,
            textvariable=self.imei_status_var,
            style="Muted.TLabel",
        ).pack(anchor="center", pady=(4, 0))

        self.imei_history_container = ttk.Frame(imei_frame, width=900)
        self.imei_history_container.pack(anchor="w", pady=(28, 0))
        history_header = ttk.Frame(self.imei_history_container)
        history_header.pack(fill=X)
        ttk.Button(history_header, text="Limpar histórico", command=self.clear_imei_history).pack(side=RIGHT)

        history_frame = ttk.Frame(self.imei_history_container)
        history_frame.pack(fill=X, pady=(10, 0))
        self.imei_history_text = Text(
            history_frame,
            width=126,
            height=10,
            wrap="word",
            font=("Segoe UI", 10),
            background="#ffffff",
            foreground="#10201f",
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=10,
        )
        imei_history_scroll = ttk.Scrollbar(history_frame, orient="vertical", command=self.imei_history_text.yview)
        self.imei_history_text.configure(yscrollcommand=imei_history_scroll.set, state="disabled")
        self.imei_history_text.pack(side=LEFT)
        imei_history_scroll.pack(side=RIGHT, fill=Y)

        self.imei_toggle_button = ttk.Button(
            self.imei_history_container,
            textvariable=self.imei_toggle_var,
            command=self.toggle_imei_history,
        )
        self.imei_toggle_button.pack(anchor="e", pady=(8, 0))
        self.refresh_imei_history()

        self.ffmpeg_tools = FfmpegToolsPanel(self.ffmpeg_tab, self)
        self._build_qualification_tab()

        file_top = ttk.Frame(self.files_tab)
        file_top.pack(fill=X)

        self.action_canvas = Canvas(file_top, width=74, height=74, highlightthickness=0, background="#f4f7f6")
        self.action_canvas.pack(side=RIGHT, padx=(16, 2))
        self.action_canvas.bind("<Button-1>", lambda _event: self.toggle_run())
        self._draw_action_button()

        self.folder_canvas = Canvas(file_top, width=56, height=56, highlightthickness=0, background="#f4f7f6")
        self.folder_canvas.bind("<Button-1>", lambda _event: self._open_temp_folder())
        self._draw_folder_button()  # some ao limpar

        self.save_canvas = Canvas(file_top, width=56, height=56, highlightthickness=0, background="#f4f7f6")
        self.save_canvas.bind("<Button-1>", lambda _event: self.save_html_report())
        self._draw_save_button()
        self.save_canvas.pack(side=RIGHT, padx=(16, 0), pady=(9, 0))
        # pasta à esquerda do disquete
        self.folder_canvas.pack(side=RIGHT, padx=(4, 0), pady=(9, 0))

        self.files_controls_frame = ttk.Frame(file_top)
        self.files_controls_frame.pack(side=LEFT, fill=X, expand=True)

        controls = ttk.Frame(self.files_controls_frame)
        controls.pack(fill=X, pady=(0, 10))
        ttk.Button(controls, text="Adicionar arquivos", command=self.add_files).pack(side=LEFT, padx=(0, 8))
        ttk.Button(controls, text="Selecionar pasta", command=self.add_folder).pack(side=LEFT, padx=(0, 8))
        ttk.Button(controls, text="Limpar", command=self.clear_files).pack(side=LEFT)

        # VAD dropdown (ao lado do Limpar)
        vad_options = ["Off", "WebRTC - 0", "WebRTC - 1", "WebRTC - 2", "WebRTC - 3",
                       "Silero - 0", "Silero - 1", "Silero - 2", "Silero - 3"]
        ttk.Label(controls, text="VAD:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(24, 4))
        self.vad_combo = ttk.Combobox(controls, textvariable=self.vad_var, values=vad_options,
                                      state="readonly", width=13, font=("Segoe UI", 9))
        self.vad_combo.pack(side=LEFT, padx=(0, 4))
        self.vad_combo.bind("<<ComboboxSelected>>", lambda _e: self._vad_changed())
        self._vad_tooltip_label = tk.Label(controls, text="?", fg="#889493",
                                           font=("Segoe UI", 9, "bold"), cursor="hand2",
                                           background="#f4f7f6")
        self._vad_tooltip_label.pack(side=LEFT)
        self._vad_tooltip_label.bind("<Enter>", lambda _e: self._show_vad_tooltip())
        self._vad_tooltip_label.bind("<Leave>", lambda _e: self._hide_vad_tooltip())
        self._vad_tooltip_label.bind("<Button-1>", lambda _e: self._show_vad_info())

        options = ttk.Frame(self.files_controls_frame)
        options.pack(fill=X, pady=(4, 12))
        self.ready_radio = ttk.Radiobutton(
            options, text="Enviar pronto", value="ready", variable=self.mode_var, command=self._refresh_tree_modes
        )
        self.compact_radio = ttk.Radiobutton(
            options, text="Enviar compactado", value="compact", variable=self.mode_var, command=self._refresh_tree_modes
        )
        self.as_is_radio = ttk.Radiobutton(
            options, text="Enviar como está", value="as_is", variable=self.mode_var, command=self._refresh_tree_modes
        )
        self.ready_radio.pack(side=LEFT, padx=(0, 18))
        self.compact_radio.pack(side=LEFT, padx=(0, 18))
        self.as_is_radio.pack(side=LEFT, padx=(0, 26))
        ttk.Checkbutton(
            options,
            text="Apenas converter",
            variable=self.convert_only_var,
            command=self._convert_only_changed,
        ).pack(side=LEFT, padx=(0, 18))
        self.vad_only_check = ttk.Checkbutton(
            options,
            text="Apenas VAD",
            variable=self.vad_only_var,
            command=self._vad_only_changed,
        )
        self.vad_only_check.pack(side=LEFT)
        self._refresh_vad_only_visibility()

        options2 = ttk.Frame(self.files_controls_frame)
        options2.pack(fill=X, pady=(0, 12))
        ttk.Checkbutton(
            options2,
            text="Transcrever logo após converter",
            variable=self.transcribe_after_convert_var,
        ).pack(side=LEFT)
        self.zip_check = ttk.Checkbutton(
            options2,
            text="Enviar como zip",
            variable=self.send_zip_var,
            command=self._refresh_zip_controls,
        )
        self.zip_check.pack(side=LEFT, padx=(24, 4))
        self.zip_check.bind("<Enter>", self._schedule_zip_help)
        self.zip_check.bind("<Motion>", self._schedule_zip_help)
        self.zip_check.bind("<Leave>", self._hide_zip_help)
        self.zip_level_frame = ttk.Frame(options2)
        ttk.Label(self.zip_level_frame, text="Nível:").pack(side=LEFT, padx=(0, 4))
        self.zip_level_combo = ttk.Combobox(
            self.zip_level_frame,
            textvariable=self.zip_level_var,
            values=("Sem compactação", "1", "2", "3", "4", "5", "6", "7", "8", "9"),
            state="readonly",
            width=16,
        )
        self.zip_level_combo.pack(side=LEFT)

        # VAD removido da tela principal (teste na aba própria)
        self.zip_level_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_tree_modes())
        self._refresh_zip_controls()

        list_frame = ttk.Frame(self.files_tab)
        list_frame.pack(fill=BOTH, expand=True)
        columns = ("arquivo", "tamanho", "status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("arquivo", text="Arquivo original")
        self.tree.heading("tamanho", text="Tamanho")
        self.tree.heading("status", text="Status")
        self.tree.column("arquivo", width=440, anchor="w")
        self.tree.column("tamanho", width=90, anchor="center")
        self.tree.column("status", width=230, anchor="w")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", self._open_selected_original)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        bottom = ttk.Frame(self.files_tab)
        bottom.pack(fill=X, pady=(12, 0))
        progress_row = ttk.Frame(bottom)
        progress_row.pack(fill=X)
        self.progress = ttk.Progressbar(progress_row, maximum=100, variable=self.progress_var)
        self.progress.pack(side=LEFT, fill=X, expand=True)
        ttk.Label(bottom, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        self.root.after_idle(self._align_activity_log)
        self.select_main_tab("live")

    def _build_qualification_tab(self) -> None:
        """Monta a área de entrada e saída da ferramenta Qualificação."""
        frame = ttk.Frame(self.qualification_tab, width=900)
        frame.pack(fill=X, anchor="n")

        self.qualification_select_all_check = ttk.Checkbutton(
            frame,
            text="Selecionar todas",
            variable=self.qualification_select_all_var,
            command=self._toggle_qualification_select_all,
            style="SelectAll.TCheckbutton",
        )
        self.qualification_select_all_check.pack(anchor="w", pady=(0, 4))

        fields_frame = ttk.Frame(frame)
        fields_frame.pack(anchor="w", pady=(0, 8))
        self.qualification_fields_frame = fields_frame
        self.qualification_field_checks = []
        for column in range(4):
            fields_frame.columnconfigure(column, minsize=180)
        for index, (field_id, label) in enumerate(self.qualification_fields):
            row, column = divmod(index, 4)
            check = ttk.Checkbutton(
                fields_frame,
                text=label,
                variable=self.qualification_field_vars[field_id],
                command=self._qualification_field_changed,
            )
            check.grid(row=row, column=column, sticky="w", padx=(0, 18), pady=(0, 4))
            self.qualification_field_checks.append(check)

        other_data_frame = ttk.Frame(fields_frame)
        other_data_frame.grid(row=0, column=4, rowspan=5, sticky="n", padx=(14, 0))
        ttk.Label(other_data_frame, text="Outros dados:").pack(side=LEFT)
        self.qualification_other_ids_entry = ttk.Entry(
            other_data_frame,
            textvariable=self.qualification_other_ids_var,
            width=30,
        )
        self.qualification_other_ids_entry.pack(side=LEFT, padx=(6, 4))
        self.qualification_other_help_button = ttk.Button(
            other_data_frame,
            text="?",
            width=2,
            command=self._show_qualification_other_help,
        )
        self.qualification_other_help_button.pack(side=LEFT)

        self.qualification_input_text = self._make_live_editor(
            frame, "Texto", "qualification_input", width=900
        )
        input_actions = ttk.Frame(frame)
        input_actions.pack(fill=X, pady=(4, 10))
        self.qualification_organize_button = ttk.Button(
            input_actions,
            text="Organizar",
            style="Action.TButton",
            width=9,
            command=self._organize_qualification,
        )
        self.qualification_organize_button.place(relx=0.5, y=0, anchor="n")
        self._make_qualification_editor_buttons(input_actions, "input")

        self.qualification_output_text = self._make_live_editor(
            frame, "Texto organizado", "qualification_output", width=900
        )
        output_actions = ttk.Frame(frame)
        output_actions.pack(fill=X, pady=(4, 10))
        self._make_qualification_editor_buttons(output_actions, "output")

        ttk.Label(
            frame,
            textvariable=self.qualification_status_var,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))

    def _toggle_qualification_select_all(self) -> None:
        selected = bool(self.qualification_select_all_var.get())
        for field_var in self.qualification_field_vars.values():
            field_var.set(selected)
        self._refresh_qualification_output_from_fields()

    def _qualification_field_changed(self) -> None:
        self.qualification_select_all_var.set(
            all(field_var.get() for field_var in self.qualification_field_vars.values())
        )
        self._refresh_qualification_output_from_fields()

    def _refresh_qualification_output_from_fields(self) -> None:
        if not self.qualification_result_fields:
            return
        selected_ids = set(self._selected_qualification_field_ids())
        self._set_qualification_output(
            format_qualification_fields(
                self.qualification_result_fields,
                self.qualification_output_fields,
                selected_ids,
            )
        )

    def _make_qualification_editor_buttons(self, parent, target: str) -> None:
        self._make_editor_icon_button(
            parent,
            self.paste_icon,
            "Colar",
            lambda selected=target: self._paste_qualification_text(selected),
        ).pack(side=RIGHT)
        self._make_editor_icon_button(
            parent,
            self.copy_icon,
            "Copiar",
            lambda selected=target: self._copy_qualification_text(selected),
        ).pack(side=RIGHT, padx=(0, 4))
        self._make_editor_icon_button(
            parent,
            self.clear_icon,
            "Limpar",
            lambda selected=target: self._clear_qualification_text(selected),
        ).pack(side=RIGHT, padx=(0, 4))

    def _qualification_editor(self, target: str):
        return self.qualification_input_text if target == "input" else self.qualification_output_text

    def _qualification_editor_value(self, target: str) -> str:
        return self._qualification_editor(target).get("1.0", END).strip()

    def _set_qualification_output(self, text: str) -> None:
        editor = self.qualification_output_text
        editor.configure(state="normal")
        editor.delete("1.0", END)
        if text:
            editor.insert("1.0", text)
        if self.assistant_busy:
            editor.configure(state="disabled")

    def _refresh_qualification_editors_state(self) -> None:
        state = "disabled" if self.assistant_busy else "normal"
        self.qualification_input_text.configure(state=state)
        self.qualification_output_text.configure(state=state)
        self.qualification_other_ids_entry.configure(state=state)
        self.qualification_other_help_button.configure(state=state)
        self.qualification_organize_button.configure(
            state="disabled" if self.assistant_busy else "normal"
        )
        self.qualification_select_all_check.configure(state=state)
        for check in self.qualification_field_checks:
            check.configure(state=state)

    def _selected_qualification_field_ids(self) -> list[str]:
        return [
            field_id
            for field_id, _label in self.qualification_fields
            if self.qualification_field_vars[field_id].get()
        ]

    def _qualification_other_ids(self) -> list[str]:
        return [
            item.strip()
            for item in self.qualification_other_ids_var.get().split(",")
            if item.strip()
        ]

    def _show_qualification_other_help(self) -> None:
        messagebox.showinfo(
            "Outros dados",
            "Use este campo para solicitar outros atributos além das opções padrão. "
            "Digite os IDs desejados separados por vírgula, por exemplo: nome_social, placa, observacao.",
            parent=self.root,
        )

    def _clear_qualification_text(self, target: str) -> None:
        if self.assistant_busy:
            return
        editor = self._qualification_editor(target)
        if self._qualification_editor_value(target) and not messagebox.askyesno(
            "sig", "Deseja limpar o texto atual?", parent=self.root
        ):
            return
        editor.delete("1.0", END)
        if target == "output":
            self.qualification_result_fields = {}
        self._set_activity_status(f"Caixa de {('entrada' if target == 'input' else 'saída')} da qualificação limpa.", log=False)

    def _copy_qualification_text(self, target: str) -> None:
        text = self._qualification_editor_value(target)
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self._set_activity_status(f"Texto da qualificação ({'entrada' if target == 'input' else 'saída'}) copiado.", log=False)

    def _paste_qualification_text(self, target: str) -> None:
        if self.assistant_busy:
            return
        try:
            pasted = self.root.clipboard_get().strip()
        except Exception:
            return
        if not pasted:
            return
        if self._qualification_editor_value(target) and not messagebox.askyesno(
            "sig", "Deseja sobrescrever o texto atual?", parent=self.root
        ):
            return
        editor = self._qualification_editor(target)
        editor.delete("1.0", END)
        editor.insert("1.0", pasted)
        if target == "output":
            self.qualification_result_fields = {}
        self._set_activity_status(f"Texto colado na qualificação ({'entrada' if target == 'input' else 'saída'}).", log=False)

    def _organize_qualification(self) -> None:
        raw_text = self._qualification_editor_value("input")
        if not raw_text:
            self.status_var.set("Digite ou cole um texto para organizar.")
            return
        field_ids = self._selected_qualification_field_ids() + self._qualification_other_ids()
        field_ids = list(dict.fromkeys(field_ids))
        if not field_ids:
            messagebox.showinfo(
                "sig",
                "Selecione pelo menos uma informação para extrair.",
                parent=self.root,
            )
            return
        if self.running or self.live_state != "idle" or self.assistant_busy:
            messagebox.showinfo(
                "sig",
                "Conclua a tarefa em andamento antes de organizar a qualificação.",
                parent=self.root,
            )
            return
        self.settings = load_settings()
        generation, settings = self._begin_assistant_request("qualification", "qualification")
        self._begin_activity_step("assistant:qualification", "Qualificação requisitada")
        self.qualification_status_var.set("Organizando qualificação...")
        self._set_activity_status("Qualificação requisitada", log=False)
        self.qualification_result_fields = {}
        self._set_qualification_output("")
        self.assistant_thread = threading.Thread(
            target=self._qualification_worker,
            args=(generation, settings, raw_text, field_ids),
            daemon=True,
        )
        self.assistant_thread.start()

    def _qualification_worker(
        self,
        generation: int,
        settings: dict,
        raw_text: str,
        field_ids: list[str],
    ) -> None:
        client = self.assistant_client
        if not client:
            return
        started = time.monotonic()
        try:
            result = client.post(
                selected_text_model_for(settings, "qualification"),
                DEFAULT_QUALIFICATION_SYSTEM_PROMPT,
                qualification_user_prompt(field_ids, raw_text),
            )
            self._queue(
                "qualification_result",
                generation,
                result,
                field_ids,
                time.monotonic() - started,
            )
        except Cancelled:
            pass
        except Exception as exc:
            self._queue(
                "qualification_error",
                generation,
                str(exc),
                time.monotonic() - started,
            )
        finally:
            self._queue("assistant_finished", generation)

    def _align_activity_log(self):
        activity_box = getattr(self, "activity_box", None)
        live_top = getattr(self, "live_top", None)
        waveform = getattr(self, "live_waveform_canvas", None)
        if not activity_box or not live_top or not waveform:
            return
        try:
            live_top.update_idletasks()
            waveform.update_idletasks()
            waveform_height = max(0, waveform.winfo_reqheight())
            live_top_height = max(0, live_top.winfo_reqheight())
            transcript_area = getattr(self, "live_transcript_area", None)
            if transcript_area is not None:
                transcript_area.update_idletasks()
                # Align the log's top edge with the actual transcript frame,
                # accounting for the waveform already occupying the panel top.
                target_top = transcript_area.winfo_rooty() - activity_box.master.winfo_rooty()
                top_padding = max(0, target_top - waveform_height)
            else:
                top_padding = max(0, live_top_height - waveform_height)
            activity_box.pack_configure(pady=(top_padding, 0))
            self._position_live_audio_recovery_button()
        except Exception:
            pass

    def _on_live_top_configure(self, _event=None):
        self._align_activity_log()
        self._position_live_audio_recovery_button()

    def _position_live_audio_recovery_button(self):
        button = getattr(self, "live_recover_audio_button", None)
        timer_label = getattr(self, "live_timer_label", None)
        live_top = getattr(self, "live_top", None)
        if not button or not timer_label or not live_top:
            return
        try:
            if not button.winfo_ismapped():
                return
            live_top.update_idletasks()
            timer_label.update_idletasks()
            button.update_idletasks()
            button_width = max(1, button.winfo_reqwidth())
            desired_x = timer_label.winfo_x() + timer_label.winfo_width() + 6
            max_x = max(0, live_top.winfo_width() - button_width - 4)
            button.place(x=min(max(0, desired_x), max_x), y=0, anchor="nw")
        except Exception:
            pass

    def select_main_tab(self, tab_name: str):
        active_bg = "#ffffff"
        inactive_bg = "#d6d2c7"
        active_fg = "#10201f"
        inactive_fg = "#111111"
        for frame in (
            getattr(self, "live_tab", None),
            getattr(self, "files_tab", None),
            getattr(self, "assistant_tab", None),
            getattr(self, "imei_tab", None),
            getattr(self, "ffmpeg_tab", None),
            getattr(self, "qualification_tab", None),
        ):
            if frame is not None:
                frame.pack_forget()
        if tab_name == "files":
            self.files_tab.pack(fill=BOTH, expand=True)
            self.live_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.files_tab_button.configure(background=active_bg, foreground=active_fg)
            self.imei_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.ffmpeg_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qualification_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
        elif tab_name == "imei":
            self.imei_tab.pack(fill=BOTH, expand=True)
            self.live_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.files_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.imei_tab_button.configure(background=active_bg, foreground=active_fg)
            self.ffmpeg_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qualification_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
        elif tab_name == "ffmpeg":
            self.ffmpeg_tab.pack(fill=BOTH, expand=True)
            self.live_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.files_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.imei_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.ffmpeg_tab_button.configure(background=active_bg, foreground=active_fg)
            self.qualification_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
        elif tab_name == "qualification":
            self.qualification_tab.pack(fill=BOTH, expand=True)
            self.live_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.files_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.imei_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.ffmpeg_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qualification_tab_button.configure(background=active_bg, foreground=active_fg)
        else:
            self.live_tab.pack(fill=BOTH, expand=True)
            self.live_tab_button.configure(background=active_bg, foreground=active_fg)
            self.files_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.imei_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.ffmpeg_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qualification_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.root.after_idle(self._position_live_parts_button)

    def _refresh_assistant_model_label(self):
        transcription = selected_transcription_server(self.settings)
        transcription_model = transcription["parameters"].get("model", "modelo não informado")
        text = selected_text_model_for(self.settings, "qualification")
        text_model = text["parameters"].get("model", "modelo não informado")
        transcription_display = transcription_server_label(transcription)
        secondary_name = str(getattr(self, "multi_model_secondary", "") or "")
        if getattr(self, "multi_model_var", None) is not None and self.multi_model_var.get() and secondary_name:
            secondary_settings = settings_for_transcription_server(self.settings, secondary_name)
            secondary = selected_transcription_server(secondary_settings)
            secondary_model = secondary["parameters"].get("model", "modelo não informado")
            transcription_display += f" + {transcription_server_label(secondary)}"
        self.transcription_model_display_var.set(transcription_display)
        if text.get("is_grok_api") or text.get("is_deepseek_api"):
            text_display = text["name"]
        else:
            text_display = f"{text['name']} ({text_model})"
        secondary_text_name = str(getattr(self, "multi_text_secondary", "") or "")
        multi_text_enabled = bool(
            getattr(self, "multi_text_model_var", None) is not None
            and self.multi_text_model_var.get()
        )
        if multi_text_enabled and secondary_text_name:
            secondary_text = selected_text_model_for(self.settings, "qualification", secondary=True)
            secondary_model = secondary_text["parameters"].get("model", "modelo não informado")
            secondary_display = (
                secondary_text["name"]
                if secondary_text.get("is_grok_api") or secondary_text.get("is_deepseek_api")
                else f"{secondary_text['name']} ({secondary_model})"
            )
            text_display += f" + {secondary_display}"
        self.text_model_display_var.set(text_display)

    def _update_imei_inputs(self):
        if self.imei_formatting:
            return
        tac_digits = "".join(char for char in self.imei_tac_var.get() if char.isdigit())
        sn_digits = "".join(char for char in self.imei_sn_var.get() if char.isdigit())
        new_tac_digits = tac_digits[:8]
        new_sn_digits = sn_digits[:6]
        move_focus_to_sn = False

        if self.root.focus_get() == self.imei_tac_entry and len(tac_digits) > 8:
            combined = (tac_digits + sn_digits)[:14]
            new_tac_digits = combined[:8]
            new_sn_digits = combined[8:14]
            move_focus_to_sn = True

        if new_tac_digits != self.imei_tac_var.get() or new_sn_digits != self.imei_sn_var.get():
            self.imei_formatting = True
            self.imei_tac_var.set(new_tac_digits)
            self.imei_sn_var.set(new_sn_digits)
            if move_focus_to_sn:
                self.imei_sn_entry.focus_set()
                self.imei_sn_entry.icursor(END)
            elif self.root.focus_get() == self.imei_tac_entry:
                self.imei_tac_entry.icursor(END)
            else:
                self.imei_sn_entry.icursor(END)
            self.imei_formatting = False
        elif move_focus_to_sn:
            self.imei_sn_entry.focus_set()
            self.imei_sn_entry.icursor(END)

        self.process_imei_digits(new_tac_digits + new_sn_digits)

    def _imei_sn_backspace(self, _event):
        if self.imei_sn_var.get() or not self.imei_tac_var.get():
            return None
        tac_digits = "".join(char for char in self.imei_tac_var.get() if char.isdigit())[:-1]
        self.imei_formatting = True
        self.imei_tac_var.set(tac_digits)
        self.imei_formatting = False
        self.imei_tac_entry.focus_set()
        self.imei_tac_entry.icursor(END)
        self.process_imei_digits(tac_digits)
        return "break"

    def copy_full_imei(self):
        digits = "".join(char for char in (self.imei_tac_var.get() + self.imei_sn_var.get()) if char.isdigit())
        if len(digits) != 14:
            self.status_var.set("Preencha TAC e Serial Number para copiar o IMEI completo.")
            return
        full_imei = f"{digits}{compute_imei_luhn_digit(digits)}"
        self.root.clipboard_clear()
        self.root.clipboard_append(full_imei)
        self.status_var.set(f"IMEI completo copiado: {full_imei}.")

    def process_imei_digits(self, digits: str):
        if len(digits) < 14:
            self.imei_result_var.set("Dígito: —")
            self.imei_model_var.set("")
            self.imei_status_var.set("")
            self.imei_last_processed = ""
            return
        if len(digits) > 14:
            self.imei_result_var.set("Dígitos demais!")
            self.imei_model_var.set("")
            self.imei_status_var.set("")
            self.imei_last_processed = ""
            return

        check = compute_imei_luhn_digit(digits)
        full_imei = f"{digits}{check}"
        self.imei_result_var.set(f"Dígito: {check}")
        if full_imei == self.imei_last_processed:
            return
        self.imei_last_processed = full_imei

        cached = find_imei_history_record(full_imei)
        if cached:
            self.imei_model_var.set(format_imei_model(cached))
            self.imei_status_var.set("")
            return

        self.imei_generation += 1
        generation = self.imei_generation
        self.imei_model_var.set("Consultando modelo...")
        self.imei_status_var.set("")
        self.imei_thread = threading.Thread(
            target=self._imei_lookup_worker,
            args=(generation, full_imei),
            daemon=True,
        )
        self.imei_thread.start()

    def _imei_lookup_worker(self, generation: int, imei: str):
        try:
            record = fetch_imei_info_record(
                imei,
                str(self.settings.get("imei_api_key") or "").strip(),
            )
            append_imei_history(record)
            self._queue("imei_result", generation, imei, record)
        except (ConnectionError, LookupError, ValueError) as exc:
            self._queue("imei_error", generation, imei, str(exc))
        except Exception:
            self._queue("imei_error", generation, imei, "Erro ao processar resposta")

    def refresh_imei_history(self):
        records = read_imei_history_records()
        if not records:
            self.imei_history_container.pack_forget()
            text = ""
            self.imei_toggle_var.set("")
            self.imei_toggle_button.configure(state="disabled")
        else:
            if not self.imei_history_container.winfo_ismapped():
                self.imei_history_container.pack(fill=BOTH, expand=True, pady=(28, 0))
            reversed_records = list(reversed(records))
            visible = (
                reversed_records
                if self.imei_history_expanded
                else reversed_records[:IMEI_HISTORY_COLLAPSED_LIMIT]
            )
            text = "\n\n".join(format_imei_history_item(record) for record in visible)
            if len(reversed_records) > IMEI_HISTORY_COLLAPSED_LIMIT:
                self.imei_toggle_var.set("ver menos" if self.imei_history_expanded else "ver mais")
                if not self.imei_toggle_button.winfo_ismapped():
                    self.imei_toggle_button.pack(anchor="e", pady=(8, 0))
                self.imei_toggle_button.configure(state="normal")
            else:
                self.imei_toggle_var.set("")
                self.imei_toggle_button.pack_forget()
        self.imei_history_text.configure(state="normal")
        self.imei_history_text.delete("1.0", END)
        if text:
            self.imei_history_text.insert("1.0", text)
        self.imei_history_text.configure(state="disabled")

    def toggle_imei_history(self):
        self.imei_history_expanded = not self.imei_history_expanded
        self.refresh_imei_history()

    def clear_imei_history(self):
        if not messagebox.askyesno("sig", "limpar histórico?"):
            return
        imei_history_path().write_text("", encoding="utf-8")
        self.imei_last_processed = ""
        self.imei_model_var.set("")
        self.imei_status_var.set("")
        self.imei_history_expanded = False
        self.refresh_imei_history()

    def _assistant_text_value(self) -> str:
        return self.assistant_text.get("1.0", END).strip()

    def _set_assistant_text(self, text: str):
        self.assistant_text.delete("1.0", END)
        self.assistant_text.insert("1.0", text.strip())

    def _live_text_value(self) -> str:
        return self.live_text.get("1.0", END).strip()

    def _replace_live_text(self, text: str):
        clean = text.strip()
        with self.live_lock:
            self.live_committed_text = clean
            self.live_draft_text = ""
            self.live_draft_generation += 1
        self._set_live_text(clean)
        if self.last_html_path and self.last_html_path.name == "transcricao_ao_vivo.html":
            try:
                temp_dir = app_base_dir() / "temp"
                txt_path = temp_dir / "transcricao_ao_vivo.txt"
                txt_path.write_text(clean + "\n", encoding="utf-8")
                self.last_html_path.write_text(build_live_html(clean), encoding="utf-8")
            except Exception:
                pass

    def paste_live_text(self):
        if self.live_state != "idle":
            self.live_assistant_status_var.set("Pare a escuta antes de colar texto.")
            return
        try:
            pasted = self.root.clipboard_get().strip()
        except Exception:
            self.live_assistant_status_var.set("A área de transferência não contém texto.")
            return
        if not pasted:
            return
        if self._live_text_value() and not messagebox.askyesno("sig", "Deseja sobrescrever o texto atual?"):
            return
        self._replace_live_text(pasted)
        self.live_assistant_status_var.set("Texto colado.")

    def copy_live_text(self):
        text = self._live_text_value()
        if not text:
            self.live_assistant_status_var.set("Ainda não há texto para copiar.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.live_assistant_status_var.set("Texto copiado.")

    def save_live_text(self):
        text = self._live_text_value()
        if not text:
            self.live_assistant_status_var.set("Ainda não há texto para salvar.")
            return
        destination = filedialog.asksaveasfilename(
            title="Salvar transcrição ao vivo",
            defaultextension=".txt",
            filetypes=[("Arquivo de texto", "*.txt"), ("Todos os arquivos", "*.*")],
            initialfile="transcricao_ao_vivo.txt",
        )
        if not destination:
            return
        try:
            Path(destination).write_text(text + "\n", encoding="utf-8")
            self.live_assistant_status_var.set(f"Texto salvo em {destination}")
        except Exception as exc:
            messagebox.showerror("sig", f"Não foi possível salvar o texto:\n{exc}")

    def clear_live_text(self):
        if self.live_state != "idle":
            self.live_assistant_status_var.set("Pare a escuta antes de limpar o texto.")
            return
        if self.assistant_busy:
            self.live_assistant_status_var.set("Aguarde a tarefa atual terminar.")
            return
        if self._live_text_value() and not messagebox.askyesno("sig", "Deseja limpar o texto?"):
            return
        self._replace_live_text("")
        self._set_live_assistant_names([])
        self.live_assistant_progress_var.set("")
        self.live_assistant_status_var.set("Caixa de texto limpa.")

    def paste_assistant_text(self):
        try:
            pasted = self.root.clipboard_get().strip()
        except Exception:
            self.assistant_status_var.set("A área de transferência não contém texto.")
            return
        if not pasted:
            return
        if self._assistant_text_value() and not messagebox.askyesno("sig", "Deseja sobrescrever o texto atual?"):
            return
        self._set_assistant_text(pasted)
        self.assistant_status_var.set("Texto colado.")

    def copy_assistant_text(self):
        text = self._assistant_text_value()
        if not text:
            self.assistant_status_var.set("Ainda não há texto para copiar.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.assistant_status_var.set("Texto copiado.")

    def save_assistant_text(self):
        text = self._assistant_text_value()
        if not text:
            self.assistant_status_var.set("Ainda não há texto para salvar.")
            return
        destination = filedialog.asksaveasfilename(
            title="Salvar histórico ou oitiva",
            defaultextension=".txt",
            filetypes=[("Arquivo de texto", "*.txt"), ("Todos os arquivos", "*.*")],
            initialfile="historico_oitiva.txt",
        )
        if not destination:
            return
        try:
            Path(destination).write_text(text + "\n", encoding="utf-8")
            self.assistant_status_var.set(f"Texto salvo em {destination}")
        except Exception as exc:
            messagebox.showerror("sig", f"Não foi possível salvar o texto:\n{exc}")

    def clear_assistant_text(self):
        if self.assistant_busy:
            self.assistant_status_var.set("Aguarde a tarefa atual terminar.")
            return
        if self._assistant_text_value() and not messagebox.askyesno("sig", "Deseja limpar o texto?"):
            return
        self._set_assistant_text("")
        self._set_assistant_names([])
        self.assistant_phase = "idle"
        self.assistant_progress_var.set("")
        self.assistant_status_var.set("Caixa de texto limpa.")

    def _set_live_assistant_names(self, names: list[str]):
        self.live_assistant_names = distinct_names([name.strip().upper() for name in names if name.strip()])
        menus = (
            (self.live_parts_menu, self.live_assistant_part_var),
            (self.live_parts_menu_2, self.live_assistant_part_var_2),
        )
        for menu, variable in menus:
            menu.delete(0, END)
        if not self.live_assistant_names:
            for menu, variable in menus:
                variable.set("Partes")
                menu.add_command(label="Nenhuma parte identificada", state="disabled")
                menu.add_separator()
                menu.add_command(label="Detectar", command=self.detect_live_parts_from_history)
            return
        for menu, variable in menus:
            variable.set(self.live_assistant_names[0])
            for name in self.live_assistant_names:
                menu.add_command(
                    label=name,
                    command=lambda selected=name, target=variable: (
                        target.set(selected), self.status_var.set(f"Parte selecionada: {selected}.")
                    ),
                )
            menu.add_separator()
            menu.add_command(label="Detectar", command=self.detect_live_parts_from_history)

    def _position_live_parts_buttons(self):
        pairs = (
            (
                getattr(self, "live_history_recover_button", None),
                getattr(self, "live_history_button", None),
                getattr(self, "live_parts_button", None),
                getattr(self, "live_assistant_part_var", None),
                getattr(self, "live_statement_button", None),
                getattr(self, "live_history_clear_button", None),
            ),
            (
                getattr(self, "live_history_recover_button_2", None),
                getattr(self, "live_history_button_2", None),
                getattr(self, "live_parts_button_2", None),
                getattr(self, "live_assistant_part_var_2", None),
                getattr(self, "live_statement_button_2", None),
                getattr(self, "live_history_clear_button_2", None),
            ),
        )
        for (
            recover_button,
            history_button,
            parts_button,
            part_var,
            statement_button,
            clear_button,
        ) in pairs:
            if (
                not recover_button
                or not history_button
                or not parts_button
                or not part_var
                or not statement_button
                or not clear_button
                or not statement_button.winfo_exists()
            ):
                continue
            actions = statement_button.master
            actions.update_idletasks()
            transcript_actions = history_button.master
            transcript_actions.update_idletasks()
            part_label = part_var.get().strip() or "Partes"
            # Menubutton reserves part of its character width for the arrow;
            # long labels need one extra character beyond the normal margin.
            desired_part_width = max(
                6, len(part_label) + (2 if len(part_label) > 6 else 0)
            )
            if int(parts_button.cget("width")) != desired_part_width:
                parts_button.configure(width=desired_part_width)
                actions.update_idletasks()
            recover_button.place(x=0, y=0)
            parts_button.place(x=recover_button.winfo_reqwidth() + 4, y=0)
            left_edge = parts_button.winfo_x() + parts_button.winfo_width()
            right_edge = clear_button.winfo_x()
            statement_half = statement_button.winfo_reqwidth() / 2
            midpoint = (left_edge + right_edge) / 2
            midpoint = min(
                max(statement_half, midpoint),
                max(statement_half, actions.winfo_width() - statement_half),
            )
            statement_button.place_forget()
            statement_button.place(x=midpoint, y=0, anchor="n")
            statement_center = statement_button.winfo_x() + (statement_button.winfo_width() / 2)
            target_width = max(1, transcript_actions.winfo_width())
            source_width = max(1, actions.winfo_width())
            history_center = statement_center * target_width / source_width
            history_half = history_button.winfo_reqwidth() / 2
            history_center = min(
                max(history_half, history_center),
                max(history_half, target_width - history_half),
            )
            history_button.place_forget()
            history_button.place(x=history_center, y=0, anchor="n")
        self._position_live_document_controls()
        self._position_live_document_preview()

    def _position_live_document_controls(self):
        actions = getattr(self, "live_qualification_actions", None)
        if not actions or not actions.winfo_exists():
            return
        actions.update_idletasks()
        width = max(1, actions.winfo_width())
        center_y = actions.winfo_height() / 2

        self.live_qualification_recover_button.place(x=0, y=center_y, anchor="w")
        right_x = width
        for button in (
            self.live_qualification_paste_button,
            self.live_qualification_copy_button,
            self.live_qualification_clear_button,
        ):
            right_x -= button.winfo_reqwidth()
            button.place(x=right_x, y=center_y, anchor="w")
            right_x -= 4

    def _fit_live_document_preview(self, _event=None):
        """Use the lower workspace for a wide, vertically scrollable A4 preview."""
        row = getattr(self, "live_qualification_row", None)
        content = getattr(self, "live_qualification_content", None)
        panel = getattr(self, "live_document_preview_panel", None)
        stage = getattr(self, "live_document_preview_stage", None)
        statement = getattr(self, "live_statement_button", None)
        qualification_editor = getattr(self, "live_qualification_editor_host", None)
        execute_frame = getattr(self, "live_qualification_execute_frame", None)
        widgets = (row, content, panel, stage, statement, qualification_editor, execute_frame)
        if not all(widget and widget.winfo_exists() for widget in widgets):
            return
        content.update_idletasks()
        available_height = row.winfo_height()
        if available_height <= 1:
            return
        qualification_right = (
            qualification_editor.winfo_rootx()
            + qualification_editor.winfo_width()
            - content.winfo_rootx()
        )
        # Reserva um vão fixo entre a qualificação e o player para o botão
        # "Gerar documento" (equidistante das duas caixas).
        reserved_gap = 116
        target_left = max(0, round(qualification_right + reserved_gap))
        available_width = max(220, content.winfo_width() - target_left)
        # The qualification stack is anchored at the bottom of its column. Its
        # editor therefore must fit between its action row and the top of the
        # row. Both boxes (qualification and player) share EXACTLY the same
        # height, including the 1,3 cm preview bonus, so their top and bottom
        # edges stay perfectly aligned on resize or restore.
        action_height = max(31, self.live_qualification_actions.winfo_height())
        extra_height = self._document_preview_extra_height()
        stage_height = max(
            180,
            min(520, available_height - action_height - 4 - extra_height),
        )
        # Keep the document preview comfortably sized without letting the
        # player occupy all of the lower workspace.  The surrounding panel
        # remains in place so the other occurrence controls do not shift.
        stage_width = max(220, min(1120, round(available_width * 0.77 * 0.92)))
        stage.configure(
            width=stage_width,
            height=stage_height + extra_height,
        )
        self.live_document_preview_toolbar.configure(width=stage_width)
        # Keep the qualification editor the same height as the document
        # player, including when the window is resized or maximized.
        self.live_qualification_editor_host.configure(height=stage_height + extra_height)
        self.live_qualification_text._editor_frame.configure(height=stage_height + extra_height)
        self.root.after_idle(self._position_live_document_preview)

    def _document_preview_extra_height(self) -> int:
        """~1,3 cm físicos extras na altura da caixa da prévia (pelo DPI real)."""
        return max(0, round(13 * _window_physical_dpi(self.root) / 25.4))

    def _position_document_execute_controls(self, content, qualification_editor) -> None:
        """Centraliza o botão Gerar documento no vão entre as duas caixas.

        O CENTRO do botão fica no centro vertical das caixas e no centro
        horizontal do vão (equidistante da qualificação e do player). As
        checkboxes ficam empilhadas exatamente acima do botão.
        """
        frame = getattr(self, "live_qualification_execute_frame", None)
        button = getattr(self, "live_document_execute_button", None)
        if not frame or not button or not frame.winfo_exists():
            return
        frame.update_idletasks()
        qualification_right = (
            qualification_editor.winfo_rootx()
            + qualification_editor.winfo_width()
            - content.winfo_rootx()
        )
        gap_center_x = round(qualification_right + 116 / 2)
        editor_top = max(0, qualification_editor.winfo_rooty() - content.winfo_rooty())
        editor_height = max(1, qualification_editor.winfo_height())
        box_center_y = editor_top + editor_height // 2
        button_height = max(1, button.winfo_height())
        frame_width = max(1, frame.winfo_reqwidth())
        frame_height = max(1, frame.winfo_reqheight())
        frame.place(
            x=round(gap_center_x - frame_width / 2),
            y=round(box_center_y - (frame_height - button_height / 2)),
            width=frame_width,
            height=frame_height,
        )

    def _position_live_document_preview(self):
        """Align the preview's left edge with the right edge of Oitiva."""
        content = getattr(self, "live_qualification_content", None)
        panel = getattr(self, "live_document_preview_panel", None)
        stage = getattr(self, "live_document_preview_stage", None)
        statement = getattr(self, "live_statement_button", None)
        qualification_editor = getattr(self, "live_qualification_editor_host", None)
        execute_frame = getattr(self, "live_qualification_execute_frame", None)
        if not content or not panel or not stage or not statement:
            return
        if not all(
            widget.winfo_exists()
            for widget in (
                content,
                panel,
                stage,
                statement,
                qualification_editor,
                execute_frame,
            )
        ):
            return
        # O botão "Gerar documento" (e as checkboxes acima dele) fica sempre
        # posicionado no vão entre as caixas, mesmo sem prévia gerada.
        self._position_document_execute_controls(content, qualification_editor)
        if not getattr(self, "document_preview_visible", False):
            if panel.winfo_manager() == "place":
                panel.place_forget()
            elif panel.winfo_manager() == "grid":
                panel.grid_remove()
            return
        content.update_idletasks()
        stage.update_idletasks()
        qualification_right = (
            qualification_editor.winfo_rootx()
            + qualification_editor.winfo_width()
            - content.winfo_rootx()
        )
        target_left = max(0, round(qualification_right + 116))
        panel_width = max(300, content.winfo_width() - target_left)
        content_height = max(1, content.winfo_height())
        # The grid column begins too far right on restored windows.  Let the
        # preview panel float over the unused lower workspace so its visible
        # page starts exactly after the Oitiva button.
        if panel.winfo_manager() == "grid":
            panel.grid_remove()
        panel.place(
            x=target_left,
            y=0,
            width=panel_width,
            height=content_height,
        )
        panel.update_idletasks()
        qualification_top = max(
            0,
            qualification_editor.winfo_rooty() - panel.winfo_rooty(),
        )
        # Qualification box and player share exactly the same height and top:
        # perfectly aligned edges (the 1,3 cm bonus applies to both).
        stage_y = qualification_top
        stage_height = max(1, qualification_editor.winfo_height())
        # Do not read stage.winfo_width() here: while the panel is being moved
        # Tk can report its transient pre-layout width as 1 px. Recompute the
        # approved 23% reduction from the panel's real available width.
        stage_width = max(220, min(1120, round(panel_width * 0.77 * 0.92)))
        stage.place(
            x=0,
            y=stage_y,
            width=stage_width,
            height=stage_height,
        )
        self.live_document_preview_toolbar.configure(width=stage_width)

        zoom = self.live_document_zoom_frame
        zoom.update_idletasks()
        zoom_width = max(1, zoom.winfo_reqwidth())
        zoom_height = max(1, zoom.winfo_reqheight())
        zoom.place(
            x=max(0, stage_width - zoom_width),
            y=stage_y + stage_height + 4,
            width=zoom_width,
            height=zoom_height,
        )

        # Keep the document actions in the free strip between the player and
        # the log. Explicit placement prevents the player from squeezing them
        # to a few pixels when the window is not maximized.
        actions = getattr(self, "live_document_actions_frame", None)
        if actions and actions.winfo_ismapped():
            actions.update_idletasks()
            actions_width = max(148, actions.winfo_reqwidth())
            actions_height = max(66, actions.winfo_reqheight())
            action_x = stage_width + 8
            if action_x + actions_width > panel_width:
                action_x = max(0, panel_width - actions_width)
            action_y = stage_y + max(0, (stage_height - actions_height) // 2)
            actions.place(
                x=action_x,
                y=action_y,
                width=actions_width,
                height=actions_height,
            )
            copy_progress = getattr(self, "live_document_copy_progress", None)
            if copy_progress and copy_progress.winfo_ismapped():
                progress_y = min(
                    max(0, panel.winfo_height() - 8),
                    action_y + actions_height + 4,
                )
                copy_progress.place(
                    x=action_x,
                    y=progress_y,
                    width=actions_width,
                    height=7,
                )

    def _set_document_copy_progress(self, active: bool) -> None:
        progress = getattr(self, "live_document_copy_progress", None)
        if progress is None or not progress.winfo_exists():
            return
        if active:
            progress.place(x=0, y=0, width=1, height=7)
            progress.start(80)
            self.root.after_idle(self._position_live_document_preview)
        else:
            progress.stop()
            progress.place_forget()

    def _set_live_document_preview_visible(self, visible: bool) -> None:
        """Show the document preview only after the user requests generation."""
        self.document_preview_visible = bool(visible)
        panel = getattr(self, "live_document_preview_panel", None)
        if panel is None or not panel.winfo_exists():
            return
        if not self.document_preview_visible:
            if panel.winfo_manager() == "place":
                panel.place_forget()
            elif panel.winfo_manager() == "grid":
                panel.grid_remove()
            return
        self.root.after_idle(self._position_live_document_preview)

    def _set_embedded_document_preview_message(self, message: str) -> None:
        canvas = getattr(self, "live_document_preview_canvas", None)
        if canvas is None or not canvas.winfo_exists():
            return
        canvas.delete("all")
        self.document_preview_photo = None
        self.live_document_preview_image_id = None
        self.live_document_preview_message_id = None
        if message:
            self.live_document_preview_message_id = canvas.create_text(
                0,
                0,
                text=message,
                fill="#536565",
                width=max(120, canvas.winfo_width() - 28),
                justify="center",
                anchor="center",
            )
        canvas.configure(scrollregion=(0, 0, max(1, canvas.winfo_width()), max(1, canvas.winfo_height())))
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)
        self._position_embedded_document_preview()

    def _position_embedded_document_preview(self) -> None:
        canvas = getattr(self, "live_document_preview_canvas", None)
        if canvas is None or not canvas.winfo_exists():
            return
        viewport = canvas.master
        viewport.update_idletasks()
        viewport_width = max(1, viewport.winfo_width())
        viewport_height = max(1, viewport.winfo_height())
        scrollbar = getattr(self, "live_document_preview_yscroll", None)
        scrollbar_width = 14
        if scrollbar is not None and scrollbar.winfo_exists():
            scrollbar.update_idletasks()
            scrollbar_width = max(12, scrollbar.winfo_reqwidth())
        available_width = max(40, viewport_width - scrollbar_width)
        photo = self.document_preview_photo
        # A caixa da prévia abraça o documento: largura = imagem + 2px de cada
        # lado (mesma margem discreta usada na vertical pelo crop).
        if photo:
            target_width = min(available_width, photo.width() + 4)
        else:
            target_width = available_width
        canvas_x = max(0, (available_width - target_width) // 2)
        canvas.place(
            x=canvas_x,
            y=0,
            width=target_width,
            height=viewport_height,
        )
        if scrollbar is not None and scrollbar.winfo_exists():
            # A barra de rolagem fica colada na lateral direita da caixa da
            # prévia (não na borda distante do viewport).
            scrollbar_x = min(
                canvas_x + target_width,
                viewport_width - scrollbar_width,
            )
            scrollbar.place(
                x=scrollbar_x,
                y=0,
                width=scrollbar_width,
                height=viewport_height,
            )
        canvas.update_idletasks()
        canvas_width = max(1, canvas.winfo_width())
        canvas_height = max(1, canvas.winfo_height())
        message_id = getattr(self, "live_document_preview_message_id", None)
        if message_id:
            canvas.coords(message_id, canvas_width / 2, canvas_height / 2)
            canvas.itemconfigure(message_id, width=max(120, canvas_width - 28))
        image_id = getattr(self, "live_document_preview_image_id", None)
        if image_id and photo:
            image_width = photo.width()
            image_height = photo.height()
            side_inset = 2
            top_inset = 2
            bottom_inset = 2
            x = max(canvas_width / 2, image_width / 2 + side_inset)
            canvas.coords(image_id, x, top_inset)
            canvas.configure(
                # Include both the image's top offset and a bottom safety
                # margin, otherwise the last rendered line can be clipped.
                scrollregion=(
                    0,
                    0,
                    max(canvas_width, image_width + side_inset * 2),
                    image_height + top_inset + bottom_inset,
                )
            )

    def _update_document_preview_scroll(self, first: str, last: str) -> None:
        scrollbar = getattr(self, "live_document_preview_yscroll", None)
        if scrollbar is not None and scrollbar.winfo_exists():
            scrollbar.set(first, last)
        canvas = getattr(self, "live_document_preview_canvas", None)
        regions = getattr(self, "document_preview_page_regions", [])
        if canvas is None or not canvas.winfo_exists() or not regions:
            return
        top = canvas.canvasy(0)
        current_page = len(regions)
        for index, (_start, end) in enumerate(regions):
            if top < end:
                current_page = index + 1
                break
        self.document_preview_page_var.set(
            f"Página {current_page}/{len(regions)}"
        )

    def _document_preview_zoom_percent(self) -> int:
        raw = self.document_preview_zoom_var.get().strip().rstrip("%")
        try:
            return max(25, min(200, int(raw)))
        except ValueError:
            return 100

    def _refresh_embedded_document_preview(self) -> None:
        document_path = self.last_generated_document_path
        if document_path and document_path.exists():
            self._start_embedded_document_preview(document_path)

    def _start_embedded_document_preview(
        self,
        document_path: Path,
        *,
        open_after: bool = False,
    ) -> None:
        self.document_preview_generation += 1
        generation = self.document_preview_generation
        zoom = self._document_preview_zoom_percent()
        dpi = _window_physical_dpi(self.root)
        self.document_preview_page_regions = []
        self.live_document_zoom_combo.configure(state="disabled")
        self.document_preview_page_var.set("Preparando prévia...")
        self._set_embedded_document_preview_message("Preparando visualização do documento...")
        threading.Thread(
            target=self._embedded_document_preview_worker,
            args=(generation, document_path, zoom, dpi, open_after),
            daemon=True,
        ).start()

    def _embedded_document_preview_worker(
        self,
        generation: int,
        document_path: Path,
        zoom: int,
        dpi: int,
        open_after: bool,
    ) -> None:
        preview_started = time.perf_counter()
        try:
            preview_path = document_path.with_name(f"{document_path.stem}_visualizacao.pdf")
            if (
                not preview_path.exists()
                or preview_path.stat().st_mtime_ns < document_path.stat().st_mtime_ns
            ):
                export_docx_to_pdf_with_word(document_path, preview_path)
            image_path = document_path.with_name(
                f"{document_path.stem}_visualizacao_{zoom}.png"
            )
            pages, page_regions = render_pdf_preview(preview_path, image_path, zoom, dpi)
            self._queue(
                "document_preview_render_ready",
                generation,
                preview_path,
                image_path,
                pages,
                page_regions,
                open_after,
                time.perf_counter() - preview_started,
            )
        except Exception as exc:
            self._queue(
                "document_preview_render_error",
                generation,
                str(exc),
                open_after,
                time.perf_counter() - preview_started,
            )

    def _show_embedded_document_preview(
        self,
        image_path: Path,
        pages: int,
        page_regions: list[tuple[int, int]],
    ) -> None:
        with Image.open(image_path) as source:
            source_image = source.convert("RGB")
        canvas = self.live_document_preview_canvas
        canvas.update_idletasks()
        # The rendered page is already calibrated for the selected zoom.
        # Never resize it again in the UI: resizing a raster after rendering
        # changes the physical scale and makes text blurry at 100%.
        display_scale = 1.0
        preview_image = source_image
        self.document_preview_photo = ImageTk.PhotoImage(preview_image)
        preview_image.close()
        canvas.delete("all")
        self.document_preview_page_regions = [
            (
                round(start * display_scale),
                round(end * display_scale),
            )
            for start, end in page_regions
        ]
        self.live_document_preview_message_id = None
        self.live_document_preview_image_id = canvas.create_image(
            0,
            0,
            image=self.document_preview_photo,
            anchor="n",
        )
        self.document_preview_page_var.set(f"Página 1/{pages}")
        self._position_embedded_document_preview()
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

    def _position_live_parts_button(self):
        self._position_live_parts_buttons()

    def _select_live_part(self, name: str):
        self.live_assistant_part_var.set(name)
        self.status_var.set(f"Parte selecionada: {name}.")

    def detect_live_parts_from_history(self):
        material = self._live_editor_value("history")
        if not material or self.assistant_busy or self.live_state != "idle":
            return
        self._begin_activity_step("assistant:names", "Partes requisitadas")
        self._set_activity_status("Partes requisitadas", log=False)
        generation, settings = self._begin_assistant_request("history", "live")
        self._set_live_assistant_names([])
        self.live_assistant_status_var.set("Identificando partes no histórico atual...")
        def worker():
            started = time.monotonic()
            try:
                if settings["parts_extraction"] == "name_database":
                    names = extract_names_from_database(material, load_name_database())
                elif settings["parts_extraction"] == "uppercase":
                    names = extract_uppercase_names(material)
                else:
                    names = parse_assistant_names(
                        self.assistant_client.post(
                            selected_parts_model(settings),
                            DEFAULT_PARTS_PROMPT,
                            parts_user_prompt_from_history(material),
                        )
                    )
                self._queue(
                    "assistant_names_result",
                    generation,
                    "live",
                    names,
                    time.monotonic() - started,
                )
            except Exception as exc:
                self._queue(
                    "assistant_task_error",
                    generation,
                    "live",
                    "names",
                    str(exc),
                    time.monotonic() - started,
                )
            finally:
                self._queue("assistant_finished", generation)
        self.assistant_thread = threading.Thread(target=worker, daemon=True)
        self.assistant_thread.start()

    def _set_assistant_names(self, names: list[str]):
        self.assistant_names = distinct_names([name.strip().upper() for name in names if name.strip()])
        self.assistant_parts_menu.delete(0, END)
        if not self.assistant_names:
            self.assistant_part_var.set("Partes")
            self.assistant_parts_menu.add_command(label="Nenhuma parte identificada", state="disabled")
            return
        self.assistant_part_var.set(self.assistant_names[0])
        for name in self.assistant_names:
            self.assistant_parts_menu.add_command(
                label=name,
                command=lambda selected=name: self.assistant_part_var.set(selected),
            )

    def _render_assistant_progress(self):
        progress_var = (
            self.live_assistant_progress_var
            if self.assistant_target == "live"
            else self.assistant_progress_var
        )
        multi_live = bool(
            self.assistant_target == "live"
            and self.multi_text_model_var.get()
            and self.multi_text_secondary
            and self.assistant_phase in ("history", "statement")
        )
        if multi_live:
            task_label = "histórico" if self.assistant_phase == "history" else "oitiva"
            rendered = []
            for index, model_label in enumerate(self.assistant_multi_model_labels, start=1):
                key = (self.assistant_phase, index)
                elapsed = self.assistant_multi_elapsed.get(key)
                if elapsed is None:
                    started = self.assistant_multi_started_at.get(key)
                    elapsed = max(0.0, time.monotonic() - started) if started is not None else None
                suffix = f" ({elapsed:.1f}s)" if elapsed is not None else ""
                if key in self.assistant_multi_errors:
                    rendered.append(f"ERRO Redigindo {task_label} - {model_label}{suffix}")
                elif key in self.assistant_multi_results:
                    rendered.append(f"100% Redigindo {task_label} - {model_label}{suffix}")
                else:
                    rendered.append(f"0% Redigindo {task_label} - {model_label}{suffix}")
            if self.assistant_phase == "history":
                names_state = self.assistant_task_states["names"]
                names_elapsed = self.assistant_task_elapsed.get("names")
                if names_elapsed is None:
                    started = self.assistant_task_started_at.get("names")
                    names_elapsed = max(0.0, time.monotonic() - started) if started is not None else None
                names_suffix = f" ({names_elapsed:.1f}s)" if names_elapsed is not None else ""
                rendered.append(
                    f"100% Extraindo partes{names_suffix}"
                    if names_state == "done"
                    else f"ERRO Extraindo partes{names_suffix}"
                    if names_state == "error"
                    else f"0% Extraindo partes{names_suffix}"
                )
            progress_var.set("\n".join(rendered))
            return
        task_labels = {
            "qualification_document": "Qualificando e gerando documento",
            "history": "Redigindo histórico",
            "names": "Extraindo partes",
            "statement": "Redigindo oitiva",
            "document": "Gerando documento",
            "document_copy": "Copiando documento",
            "document_save_docx": "Salvando docx",
            "document_save_pdf": "Salvando pdf",
        }
        task_priority = (
            "qualification_document",
            "history",
            "statement",
            "document",
            "names",
            "document_copy",
            "document_save_docx",
            "document_save_pdf",
        )
        # Apenas uma tarefa por vez no painel: a em execução mais prioritária
        # ou, sem nada rodando, a última concluída. O log guarda o histórico.
        running = [
            task
            for task in task_labels
            if self.assistant_task_states[task] == "running"
        ]
        if running:
            task = min(running, key=lambda item: task_priority.index(item))
        else:
            finished = [
                task
                for task in task_labels
                if self.assistant_task_states[task] in ("done", "error")
            ]
            if not finished:
                progress_var.set("")
                return
            task = max(
                finished,
                key=lambda item: self.assistant_task_started_at.get(item) or 0,
            )
        state = self.assistant_task_states[task]
        elapsed = self.assistant_task_elapsed[task]
        if elapsed is None:
            started = self.assistant_task_started_at.get(task)
            elapsed = max(0.0, time.monotonic() - started) if started is not None else None
        suffix = f" ({elapsed:.1f}s)" if elapsed is not None else ""
        label = task_labels[task]
        if state == "error":
            rendered = f"ERRO {label}{suffix}"
        elif state == "done":
            rendered = f"100% {label}{suffix}"
        else:
            rendered = f"0% {label}{suffix}"
        progress_var.set(rendered)

    def _refresh_assistant_progress_clock(self):
        """Refresh active text-task timers without adding repeated log entries."""
        document_active = any(
            self.assistant_task_states[task] == "running"
            for task in ("document", "document_copy", "document_save_docx", "document_save_pdf")
        )
        if self.assistant_busy or document_active:
            self._render_assistant_progress()
        try:
            self.root.after(100, self._refresh_assistant_progress_clock)
        except self.tk.TclError:
            pass

    def _set_assistant_buttons_state(self, state: str):
        for button_name in (
            "assistant_history_button",
            "assistant_statement_button",
            "live_history_button",
            "live_history_button_2",
            "live_statement_button",
            "live_statement_button_2",
            "live_document_execute_button",
        ):
            button = getattr(self, button_name, None)
            if button is not None:
                button.configure(state=state)
        if hasattr(self, "qualification_organize_button"):
            self.qualification_organize_button.configure(state=state)
        if hasattr(self, "qualification_field_checks"):
            for check in self.qualification_field_checks:
                check.configure(state=state)
        if hasattr(self, "qualification_select_all_check"):
            self.qualification_select_all_check.configure(state=state)

    def _assistant_target_text_value(self, target: str) -> str:
        return self._live_text_value() if target == "live" else self._assistant_text_value()

    def _set_assistant_target_text(self, target: str, text: str):
        if target == "live":
            self._set_live_editor("history" if self.assistant_phase == "history" else "statement", text)
        else:
            self._set_assistant_text(text)

    def _set_assistant_target_names(self, target: str, names: list[str]):
        if target == "live":
            self._set_live_assistant_names(names)
        else:
            self._set_assistant_names(names)

    def _assistant_target_status(self, target: str) -> StringVar:
        return self.live_assistant_status_var if target == "live" else self.assistant_status_var

    def _refresh_history_completion_status(self, target: str) -> None:
        names = self.live_assistant_names if target == "live" else self.assistant_names
        message = history_completion_status(
            self.assistant_task_states["history"],
            self.assistant_task_states["names"],
            len(names),
        )
        if not message:
            return
        self._assistant_target_status(target).set(message)

    def _assistant_target_part(self, target: str) -> str:
        if target == "live":
            selected_name = self.live_assistant_part_var.get().strip()
        else:
            selected_name = self.assistant_part_var.get().strip()
        return "" if selected_name == "Partes" else selected_name

    def _begin_assistant_request(self, phase: str, target: str) -> tuple[int, dict]:
        self.assistant_generation += 1
        generation = self.assistant_generation
        self.assistant_cancel_event = threading.Event()
        self.assistant_client = TextModelClient(self.assistant_cancel_event)
        self.assistant_busy = True
        self.assistant_phase = phase
        self.assistant_target = target
        self.assistant_multi_results: set[tuple[str, int]] = set()
        self.assistant_multi_elapsed: dict[tuple[str, int], float] = {}
        self.assistant_multi_errors: dict[tuple[str, int], str] = {}
        self.assistant_multi_started_at = {}
        self._set_assistant_buttons_state("disabled")
        self._refresh_live_editors_state()
        self._refresh_qualification_editors_state()
        self.settings = load_settings()
        secondary_name = str(self.multi_text_secondary or "")
        if target == "live" and self.multi_text_model_var.get() and secondary_name:
            primary_config = selected_text_model_for(self.settings, "history")
            secondary_config = selected_text_model_for(self.settings, "history", secondary=True)
            self.assistant_multi_model_labels = (
                str(primary_config.get("name") or "Modelo 1"),
                str(secondary_config.get("name") or "Modelo 2"),
            )
        else:
            self.assistant_multi_model_labels = ("Modelo 1", "Modelo 2")
        self._refresh_assistant_model_label()
        return generation, self.settings.copy()

    def request_assistant_history(self):
        self._request_history_for_target("assistant")

    def request_live_history(self):
        self._request_history_for_target("live")

    def request_live_history_2(self):
        self._request_history_for_target("live", self._live_editor_value("transcript2"))

    def _request_history_for_target(self, target: str, material_override: str | None = None):
        material = material_override if material_override is not None else self._assistant_target_text_value(target)
        status_var = self._assistant_target_status(target)
        if not material:
            messagebox.showinfo("sig", "Cole, digite ou grave uma transcrição antes de gerar o histórico.")
            return
        if self.running or (target != "live" and self.live_state != "idle"):
            messagebox.showinfo("sig", "Conclua a transcrição em andamento antes de gerar o histórico.")
            return
        if target == "live" and self.live_state != "idle":
            messagebox.showinfo("sig", "Pare a escuta ao vivo antes de gerar o histórico.")
            return
        if self.assistant_busy:
            return
        generation, settings = self._begin_assistant_request("history", target)
        self._set_assistant_target_names(target, [])
        self.assistant_task_states.update(history="running", names="running", statement="idle")
        self.assistant_task_elapsed.update(history=None, names=None, statement=None)
        request_started = time.monotonic()
        self.assistant_task_started_at.update(
            history=request_started,
            names=request_started,
            statement=None,
        )
        if target == "live" and self.multi_text_model_var.get() and self.multi_text_secondary:
            self.assistant_multi_started_at[("history", 1)] = request_started
            self.assistant_multi_started_at[("history", 2)] = request_started
            self._begin_activity_step("assistant:history:1", "Histórico 1 requisitado")
            self._begin_activity_step("assistant:history:2", "Histórico 2 requisitado")
        else:
            self._begin_activity_step("assistant:history", "Histórico requisitado")
        self._begin_activity_step("assistant:names", "Partes requisitadas")
        self._set_activity_status("Histórico e Partes requisitados", log=False)
        self._render_assistant_progress()
        if target == "live" and self.multi_text_model_var.get() and self.multi_text_secondary:
            self.assistant_thread = threading.Thread(
                target=self._assistant_multi_history_worker,
                args=(generation, settings, material),
                daemon=True,
            )
            self.assistant_thread.start()
            return
        self.assistant_thread = threading.Thread(
            target=self._assistant_history_worker,
            args=(generation, target, settings, material),
            daemon=True,
        )
        self.assistant_thread.start()

    def _assistant_history_worker(self, generation: int, target: str, settings: dict, material: str):
        client = self.assistant_client
        if not client:
            return
        model_config = selected_text_model_for(settings, "history")
        parts_model_config = selected_parts_model(settings)
        extraction_method = settings["parts_extraction"]
        history_request = history_user_prompt(material)
        try:
            if extraction_method == "ai":
                started = {"history": time.monotonic(), "names": time.monotonic()}
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    futures = {
                        executor.submit(
                            client.post,
                            model_config,
                            DEFAULT_HISTORY_SYSTEM_PROMPT,
                            history_request,
                        ): "history",
                        executor.submit(
                            client.post,
                            parts_model_config,
                            DEFAULT_PARTS_PROMPT,
                            parts_user_prompt_from_transcription(material),
                        ): "names",
                    }
                    for future in concurrent.futures.as_completed(futures):
                        task = futures[future]
                        try:
                            result = future.result()
                            elapsed = time.monotonic() - started[task]
                            if task == "history":
                                self._queue("assistant_text_result", generation, target, task, result, elapsed)
                            else:
                                names = parse_assistant_names(result)
                                if not names:
                                    raise RuntimeError("O servidor não devolveu nomes reconhecíveis.")
                                self._queue("assistant_names_result", generation, target, names, elapsed)
                        except Cancelled:
                            pass
                        except Exception as exc:
                            elapsed = time.monotonic() - started[task]
                            self._queue("assistant_task_error", generation, target, task, str(exc), elapsed)
            else:
                history_started = time.monotonic()
                try:
                    history = client.post(
                        model_config,
                        DEFAULT_HISTORY_SYSTEM_PROMPT,
                        history_request,
                    )
                    history_elapsed = time.monotonic() - history_started
                    self._queue("assistant_text_result", generation, target, "history", history, history_elapsed)
                except Cancelled:
                    return
                except Exception as exc:
                    elapsed = time.monotonic() - history_started
                    self._queue("assistant_task_error", generation, target, "history", str(exc), elapsed)
                    self._queue("assistant_task_error", generation, target, "names", str(exc), 0.0)
                    return

                names_started = time.monotonic()
                if extraction_method == "name_database":
                    names = extract_names_from_database(history, load_name_database())
                else:
                    names = extract_uppercase_names(history)
                self._queue(
                    "assistant_names_result",
                    generation,
                    target,
                    names,
                    time.monotonic() - names_started,
                )
        finally:
            self._queue("assistant_finished", generation)

    def _assistant_multi_history_worker(self, generation: int, settings: dict, material: str):
        client = self.assistant_client
        if not client:
            return
        models = [
            selected_text_model_for(settings, "history"),
            selected_text_model_for(settings, "history", secondary=True),
        ]
        extraction_method = settings["parts_extraction"]
        primary_history = ""
        history_request = history_user_prompt(material)
        try:
            started = time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_map = {
                    executor.submit(
                        client.post,
                        model,
                        DEFAULT_HISTORY_SYSTEM_PROMPT,
                        history_request,
                    ): index
                    for index, model in enumerate(models, start=1)
                }
                for future in concurrent.futures.as_completed(future_map):
                    index = future_map[future]
                    try:
                        result = future.result()
                        if index == 1:
                            primary_history = result
                        self._queue(
                            "assistant_multi_text_result",
                            generation,
                            "history",
                            index,
                            result,
                            time.monotonic() - started,
                        )
                    except Exception as exc:
                        self._queue(
                            "assistant_multi_error",
                            generation,
                            "history",
                            index,
                            str(exc),
                            time.monotonic() - started,
                        )
            if primary_history:
                names_started = time.monotonic()
                if extraction_method == "ai":
                    names = parse_assistant_names(
                        client.post(
                            selected_parts_model(settings),
                            DEFAULT_PARTS_PROMPT,
                            parts_user_prompt_from_transcription(material),
                        )
                    )
                elif extraction_method == "name_database":
                    names = extract_names_from_database(primary_history, load_name_database())
                else:
                    names = extract_uppercase_names(primary_history)
                self._queue(
                    "assistant_names_result",
                    generation,
                    "live",
                    names,
                    time.monotonic() - names_started,
                )
        finally:
            self._queue("assistant_finished", generation)

    def request_assistant_statement(self):
        self._request_statement_for_target("assistant")

    def request_live_statement(self):
        self._request_statement_for_target("live", "history", self.live_assistant_part_var.get())

    def request_live_statement_2(self):
        self._request_statement_for_target("live", "history2", self.live_assistant_part_var_2.get())

    def _request_statement_for_target(
        self,
        target: str,
        live_source: str = "history",
        selected_name_override: str | None = None,
    ):
        material = self._live_editor_value(live_source) if target == "live" else self._assistant_target_text_value(target)
        status_var = self._assistant_target_status(target)
        if not material:
            messagebox.showinfo("sig", "Ainda não há texto para redigir a oitiva.")
            return
        if self.running or (target != "live" and self.live_state != "idle"):
            messagebox.showinfo("sig", "Conclua a transcrição em andamento antes de redigir a oitiva.")
            return
        if target == "live" and self.live_state != "idle":
            messagebox.showinfo("sig", "Pare a escuta ao vivo antes de redigir a oitiva.")
            return
        if self.assistant_busy:
            return
        selected_name = (
            selected_name_override.strip()
            if selected_name_override is not None
            else self._assistant_target_part(target)
        )
        if selected_name == "Partes":
            selected_name = ""
        generation, settings = self._begin_assistant_request("statement", target)
        self.assistant_task_states.update(history="idle", names="idle", statement="running")
        self.assistant_task_elapsed.update(history=None, names=None, statement=None)
        request_started = time.monotonic()
        self.assistant_task_started_at.update(
            history=None,
            names=None,
            statement=request_started,
        )
        if target == "live" and self.multi_text_model_var.get() and self.multi_text_secondary:
            self.assistant_multi_started_at[("statement", 1)] = request_started
            self.assistant_multi_started_at[("statement", 2)] = request_started
            self._begin_activity_step("assistant:statement:1", "Oitiva 1 requisitada")
            self._begin_activity_step("assistant:statement:2", "Oitiva 2 requisitada")
        else:
            self._begin_activity_step("assistant:statement", "Oitiva requisitada")
        self._set_activity_status("Oitiva requisitada", log=False)
        self._render_assistant_progress()
        if target == "live" and self.multi_text_model_var.get() and self.multi_text_secondary:
            self.assistant_thread = threading.Thread(
                target=self._assistant_multi_statement_worker,
                args=(generation, settings, material, selected_name),
                daemon=True,
            )
            self.assistant_thread.start()
            return
        self.assistant_thread = threading.Thread(
            target=self._assistant_statement_worker,
            args=(generation, target, settings, material, selected_name),
            daemon=True,
        )
        self.assistant_thread.start()

    def _assistant_statement_worker(
        self,
        generation: int,
        target: str,
        settings: dict,
        material: str,
        selected_name: str,
    ):
        client = self.assistant_client
        if not client:
            return
        started = time.monotonic()
        try:
            result = client.post(
                selected_text_model_for(settings, "statement"),
                statement_prompt(selected_name),
                statement_user_prompt(selected_name, material),
            )
            self._queue(
                "assistant_text_result",
                generation,
                target,
                "statement",
                result,
                time.monotonic() - started,
            )
        except Cancelled:
            pass
        except Exception as exc:
            self._queue(
                "assistant_task_error",
                generation,
                target,
                "statement",
                str(exc),
                time.monotonic() - started,
            )
        finally:
            self._queue("assistant_finished", generation)

    def _assistant_multi_statement_worker(
        self,
        generation: int,
        settings: dict,
        material: str,
        selected_name: str,
    ):
        client = self.assistant_client
        if not client:
            return
        models = [
            selected_text_model_for(settings, "statement"),
            selected_text_model_for(settings, "statement", secondary=True),
        ]
        started = time.monotonic()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_map = {
                    executor.submit(
                        client.post,
                        model,
                        statement_prompt(selected_name),
                        statement_user_prompt(selected_name, material),
                    ): index
                    for index, model in enumerate(models, start=1)
                }
                for future in concurrent.futures.as_completed(future_map):
                    index = future_map[future]
                    try:
                        self._queue(
                            "assistant_multi_text_result",
                            generation,
                            "statement",
                            index,
                            future.result(),
                            time.monotonic() - started,
                        )
                    except Exception as exc:
                        self._queue(
                            "assistant_multi_error",
                            generation,
                            "statement",
                            index,
                            str(exc),
                            time.monotonic() - started,
                        )
        finally:
            self._queue("assistant_finished", generation)

    def cancel_assistant_request(self):
        if not self.assistant_busy:
            return
        self.pending_occurrence_document_generation = False
        self.assistant_generation += 1
        self.assistant_cancel_event.set()
        if self.assistant_client:
            self.assistant_client.cancel()
        self.assistant_busy = False
        self._set_assistant_buttons_state("normal")
        self._refresh_live_editors_state()
        self._refresh_qualification_editors_state()
        self._assistant_target_status(self.assistant_target).set("Tarefa de texto cancelada.")
        self.qualification_status_var.set("Organização cancelada.")

    def _draw_action_button(self):
        canvas = self.action_canvas
        canvas.delete("all")
        canvas.create_oval(5, 5, 69, 69, fill="#13201e", outline="#2c403d", width=2)
        if self.running:
            canvas.create_line(25, 24, 49, 50, fill="#ff4b4b", width=7, capstyle="round")
            canvas.create_line(49, 24, 25, 50, fill="#ff4b4b", width=7, capstyle="round")
        else:
            canvas.create_polygon(
                42,
                12,
                22,
                41,
                36,
                41,
                29,
                62,
                53,
                30,
                38,
                30,
                fill="#ffd21f",
                outline="#ffe789",
                width=2,
            )

    def _draw_save_button(self):
        canvas = self.save_canvas
        canvas.delete("all")
        enabled = bool(self.last_html_path and self.last_html_path.exists())
        outer = "#1f3d52" if enabled else "#d6dddd"
        body = "#2f8fcc" if enabled else "#aab5b5"
        detail = "#f4fbff" if enabled else "#dbe1e1"
        notch = "#103044" if enabled else "#879191"
        canvas.create_oval(4, 4, 52, 52, fill=outer, outline="")
        canvas.create_rectangle(16, 13, 40, 42, fill=body, outline=detail, width=2)
        canvas.create_rectangle(20, 15, 35, 24, fill=detail, outline="")
        canvas.create_rectangle(33, 15, 37, 24, fill=notch, outline="")
        canvas.create_rectangle(21, 32, 35, 42, fill=detail, outline="")
        canvas.create_line(23, 35, 33, 35, fill=notch, width=2)

    def _draw_folder_button(self):
        """Desenha (ou esconde) o botão de pasta, redondo como o disquete."""
        canvas = self.folder_canvas
        canvas.delete("all")
        visible = getattr(self, "folder_button_visible", False)
        if not visible:
            return
        outer = "#1f3d52"
        body = "#d6a22b"
        light = "#fdf3d6"
        # círculo externo
        canvas.create_oval(4, 4, 52, 52, fill=outer, outline="")
        # corpo da pasta
        canvas.create_rectangle(15, 20, 44, 46, fill=body, outline=light, width=2)
        # aba
        canvas.create_polygon(15, 20, 31, 20, 33, 14, 19, 14, fill=body, outline=light, width=2)
        # recorte no canto superior
        canvas.create_rectangle(16, 16, 30, 18, fill=outer, outline="")
        # detalhe do centro
        canvas.create_line(17, 33, 42, 33, fill=light, width=1)
        canvas.create_line(17, 38, 42, 38, fill=light, width=1)

    def _show_folder_button(self, *, visible: bool = True):
        """Mostra ou esconde o botão de pasta (limpa ao perder a referência)."""
        self.folder_button_visible = visible
        self._draw_folder_button()

    def _open_temp_folder(self):
        """Abre a pasta temp/ no explorador de arquivos (só se o botão estiver visível)."""
        if not getattr(self, "folder_button_visible", False):
            return
        try:
            temp_dir = app_base_dir() / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(temp_dir)
        except Exception as exc:
            messagebox.showerror("sig", f"Não foi possível abrir a pasta:\\n{exc}")

    def _draw_live_mic_button(self):
        canvas = self.live_mic_canvas
        canvas.delete("all")
        state = self.live_state
        if state == "finalizing":
            canvas.create_oval(4, 4, 40, 40, fill="#d6dddd", outline="#879191", width=2)
            canvas.create_arc(16, 14, 28, 30, start=20, extent=300, outline="#5d6868", width=3, style="arc")
            return
        canvas.create_oval(4, 4, 40, 40, fill="#13201e", outline="#2c403d", width=2)
        if state in ("listening", "paused"):
            canvas.create_line(15, 15, 29, 29, fill="#ff4b4b", width=5, capstyle="round")
            canvas.create_line(29, 15, 15, 29, fill="#ff4b4b", width=5, capstyle="round")
        else:
            canvas.create_oval(17, 10, 27, 26, fill="#ff4b4b", outline="#ffd0d0", width=2)
            canvas.create_line(22, 26, 22, 33, fill="#ff4b4b", width=3, capstyle="round")
            canvas.create_arc(13, 18, 31, 34, start=200, extent=140, outline="#ff4b4b", width=3, style="arc")
            canvas.create_line(16, 34, 28, 34, fill="#ff4b4b", width=3, capstyle="round")

    def _set_live_audio_recovery_visible(self, visible: bool):
        button = getattr(self, "live_recover_audio_button", None)
        if button is None or not button.winfo_exists():
            return
        button.place_forget()
        if visible and self.live_audio_recovery_available:
            # This placement does not participate in geometry management, so
            # showing the button cannot move the microphone row or timer.
            button.place(x=0, y=0, anchor="nw")
            self._position_live_audio_recovery_button()

    def _clear_live_integral_audio(self):
        self.live_audio_recovery_available = False
        self._set_live_audio_recovery_visible(False)
        path = self.live_full_pcm_path
        if path:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        self.live_full_pcm_path = None

    def _draw_live_pause_button(self):
        canvas = self.live_pause_canvas
        canvas.delete("all")
        normal_active = self.normal_recording
        if self.live_state not in ("listening", "paused") and not normal_active:
            return
        canvas.create_oval(4, 4, 40, 40, fill="#f2cf37", outline="#c49d00", width=2)
        is_paused = self.live_state == "paused" or (normal_active and self.normal_record_paused)
        if not is_paused:
            canvas.create_rectangle(15, 13, 19, 31, fill="#1b5b92", outline="")
            canvas.create_rectangle(25, 13, 29, 31, fill="#1b5b92", outline="")
        else:
            canvas.create_polygon(17, 13, 17, 31, 31, 22, fill="#1b5b92", outline="#16466f")

    def _draw_normal_live_mic_button(self):
        canvas = self.live_normal_mic_canvas
        canvas.delete("all")
        if self.normal_recording:
            canvas.create_oval(4, 4, 40, 40, fill="#3d1515", outline="#5a2424", width=2)
            canvas.create_line(15, 15, 29, 29, fill="#ff4b4b", width=5, capstyle="round")
            canvas.create_line(29, 15, 15, 29, fill="#ff4b4b", width=5, capstyle="round")
            return
        canvas.create_oval(4, 4, 40, 40, fill="#ffffff", outline="#768282", width=2)
        canvas.create_oval(17, 10, 27, 26, fill="#536565", outline="")
        canvas.create_line(22, 26, 22, 33, fill="#536565", width=3, capstyle="round")
        canvas.create_arc(13, 18, 31, 34, start=200, extent=140, outline="#536565", width=3, style="arc")

    def _reset_live_waveform(self):
        with self.live_waveform_lock:
            self.live_waveform_levels.clear()
            self.live_waveform_levels.extend([0.0] * 168)
            self.live_waveform_last_capture_at = 0.0

    def _push_live_waveform_chunk(self, chunk: bytes):
        if not chunk:
            return
        try:
            usable = chunk[: len(chunk) - (len(chunk) % 2)]
            samples = array("h")
            samples.frombytes(usable)
            if sys.byteorder != "little":
                samples.byteswap()
            if not samples:
                return
            # Break each callback into short envelopes so the display has more
            # detail than one bar per audio callback.
            target_samples = max(160, LIVE_SAMPLE_RATE // 40)  # about 25 ms
            bin_count = max(1, min(8, math.ceil(len(samples) / target_samples)))
            bin_size = max(1, math.ceil(len(samples) / bin_count))
            levels = []
            for start in range(0, len(samples), bin_size):
                window = samples[start : start + bin_size]
                if not window:
                    continue
                peak = max(abs(value) for value in window)
                rms = math.sqrt(sum(value * value for value in window) / len(window))
                # A little RMS gain keeps quieter speech visibly moving while
                # the peak still preserves consonants and transient sounds.
                raw_level = max(peak * 0.90, rms * 2.20) / 16384.0
                levels.append(min(1.0, raw_level) ** 0.62)
            if not levels:
                return
            with self.live_waveform_lock:
                self.live_waveform_levels.extend(levels)
                self.live_waveform_last_capture_at = time.monotonic()
        except Exception:
            # The waveform is only diagnostic; a malformed block must never stop capture.
            pass

    def _draw_live_waveform(self):
        canvas = getattr(self, "live_waveform_canvas", None)
        if canvas is None or not canvas.winfo_exists():
            return
        width = max(40, canvas.winfo_width())
        height = max(24, canvas.winfo_height())
        center = height / 2
        with self.live_waveform_lock:
            levels = list(self.live_waveform_levels)
            active = (
                self.live_state == "listening"
                or (
                    self.normal_recording
                    and not self.normal_record_paused
                    and not self.normal_record_stop_event.is_set()
                )
            )
            if not active or time.monotonic() - self.live_waveform_last_capture_at > 0.15:
                self.live_waveform_levels.append(0.0)
                levels = list(self.live_waveform_levels)
        canvas.delete("all")
        canvas.create_line(4, center, width - 4, center, fill="#c6d2d0", width=1)
        color = "#3f948b" if active else "#a8b8b5"
        usable_width = max(1, width - 8)
        upper_points = []
        lower_points = []
        for index, level in enumerate(levels):
            x = 4 + usable_width * index / max(1, len(levels) - 1)
            amplitude = (
                min(center - 3, max(1.0, (level ** 0.75) * (height - 8) * 0.62))
                if level
                else 0.0
            )
            upper_points.append((x, center - amplitude))
            lower_points.append((x, center + amplitude))
        if len(upper_points) > 1:
            polygon_points = upper_points + list(reversed(lower_points))
            polygon_coords = [value for point in polygon_points for value in point]
            canvas.create_polygon(
                *polygon_coords,
                fill="#b7ddd4" if active else "#d5dfdd",
                outline="",
            )
            upper_coords = [value for point in upper_points for value in point]
            lower_coords = [value for point in lower_points for value in point]
            canvas.create_line(*upper_coords, fill=color, width=2, smooth=True)
            canvas.create_line(*lower_coords, fill=color, width=2, smooth=True)

    def _refresh_live_waveform(self):
        try:
            self._draw_live_waveform()
        except Exception:
            pass
        try:
            self.root.after(50, self._refresh_live_waveform)
        except Exception:
            pass

    def _make_live_editor(
        self,
        parent,
        _label: str,
        _kind: str,
        width: int = 900,
        height: int = 180,
        vertical_padding: tuple[int, int] = (8, 0),
    ):
        frame = ttk.Frame(parent, width=width, height=height)
        frame.pack(fill=X, expand=True, pady=vertical_padding)
        frame.pack_propagate(False)
        text = Text(frame, width=1, height=8, wrap="word", undo=True, font=("Segoe UI", 10), background="#ffffff", foreground="#10201f", relief="solid", borderwidth=1, padx=8, pady=7)
        placeholder_text = {
            "transcript": "A transcrição da entrevista será gerada aqui.",
            "transcript2": "A transcrição da entrevista será gerada aqui.",
            "history": "O histórico do Boletim de Ocorrência será gerado aqui.",
            "history2": "O histórico do Boletim de Ocorrência será gerado aqui.",
            "statement": "A oitiva da parte selecionada será gerada aqui.",
            "statement2": "A oitiva da parte selecionada será gerada aqui.",
            "qualification": "Cole aqui a qualificação do declarante/depoente.",
        }.get(_kind)
        text._placeholder_active = False
        text._placeholder_text = placeholder_text
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        text._editor_frame = frame
        text.bind("<FocusIn>", lambda _event, widget=text: self._clear_live_placeholder(widget), add="+")
        text.bind("<FocusOut>", lambda _event, widget=text: self._restore_live_placeholder(widget), add="+")
        self._restore_live_placeholder(text)
        return text

    @staticmethod
    def _is_live_placeholder(widget) -> bool:
        return bool(getattr(widget, "_placeholder_active", False))

    def _restore_live_placeholder(self, widget) -> None:
        placeholder = getattr(widget, "_placeholder_text", None)
        if not placeholder or widget.get("1.0", END).strip():
            return
        state = str(widget.cget("state"))
        if state == "disabled":
            widget.configure(state="normal")
        widget.delete("1.0", END)
        widget.insert("1.0", placeholder)
        widget.configure(foreground="#879491")
        widget._placeholder_active = True
        if state == "disabled":
            widget.configure(state="disabled")

    def _clear_live_placeholder(self, widget) -> None:
        if not self._is_live_placeholder(widget):
            return
        state = str(widget.cget("state"))
        if state == "disabled":
            return
        widget.delete("1.0", END)
        widget.configure(foreground="#10201f")
        widget._placeholder_active = False

    def _live_editor(self, kind: str):
        return {
            "transcript": self.live_text,
            "transcript2": self.live_text_2,
            "history": self.live_history_text,
            "history2": self.live_history_text_2,
            "statement": self.live_statement_text,
            "statement2": self.live_statement_text_2,
            "qualification": self.live_qualification_text,
        }[kind]

    def _live_editor_value(self, kind: str) -> str:
        widget = self._live_editor(kind)
        if self._is_live_placeholder(widget):
            return ""
        return widget.get("1.0", END).strip()

    def _set_live_editor(self, kind: str, text: str):
        widget = self._live_editor(kind)
        at_end = widget.yview()[1] >= .98
        top = widget.yview()[0]
        widget.configure(state="normal")
        widget.delete("1.0", END)
        if text:
            widget.insert("1.0", text.strip())
            widget.configure(foreground="#10201f")
            widget._placeholder_active = False
        else:
            self._restore_live_placeholder(widget)
        if self.live_state != "idle" or self.assistant_busy:
            widget.configure(state="disabled")
        if kind in ("transcript", "transcript2") and self.live_state != "idle":
            widget.see(END)
        elif at_end:
            widget.see(END)
        else:
            widget.yview_moveto(top)

    def _remember_live_assistant_result(self, task: str, index: int, text: str):
        if task not in ("history", "statement"):
            return
        kind = task if index == 1 else f"{task}2"
        setattr(self, f"last_live_{kind}_text", (text or "").strip())

    def _refresh_live_editors_state(self):
        state = "disabled" if self.live_state != "idle" or self.assistant_busy else "normal"
        for kind in (
            "transcript",
            "transcript2",
            "history",
            "history2",
            "statement",
            "statement2",
            "qualification",
        ):
            self._live_editor(kind).configure(state=state)

    def clear_live_editor(self, kind: str):
        if self.live_state != "idle" or self.assistant_busy:
            return
        if self._live_editor_value(kind) and not messagebox.askyesno("sig", "Deseja limpar o texto atual?"):
            return
        self._set_live_editor(kind, "")
        if kind == "transcript":
            self._replace_live_text("")
        elif kind == "transcript2":
            self.live_secondary_committed_text = ""
            self.live_secondary_draft_text = ""
        self._set_activity_status(f"Caixa de {self._live_editor_label(kind)} limpa.", log=False)

    def copy_live_editor(self, kind: str):
        text = self._live_editor_value(kind)
        if text:
            self.root.clipboard_clear(); self.root.clipboard_append(text)
            self._set_activity_status(f"Conteúdo de {self._live_editor_label(kind)} copiado.", log=False)

    def paste_live_editor(self, kind: str):
        if self.live_state != "idle" or self.assistant_busy:
            return
        try:
            pasted = self.root.clipboard_get().strip()
        except Exception:
            return
        if pasted and (not self._live_editor_value(kind) or messagebox.askyesno("sig", "Deseja sobrescrever o texto atual?")):
            self._set_live_editor(kind, pasted)
            if kind == "transcript":
                self._replace_live_text(pasted)
            elif kind == "transcript2":
                with self.live_secondary_lock:
                    self.live_secondary_committed_text = pasted
                    self.live_secondary_draft_text = ""
            self._set_activity_status(f"Texto colado em {self._live_editor_label(kind)}.", log=False)

    def recover_live_assistant_text(self, kind: str):
        saved = getattr(self, f"last_live_{kind}_text", "")
        if self.live_state != "idle" or self.assistant_busy or not saved:
            return
        if self._live_editor_value(kind) and not messagebox.askyesno(
            "sig", "Deseja sobrescrever o texto atual?"
        ):
            return
        self._set_live_editor(kind, saved)
        self._set_activity_status(f"Último {self._live_editor_label(kind)} recuperado.", log=False)

    def recover_live_qualification(self):
        if not self.last_live_qualification_text:
            self.status_var.set("Ainda não há uma qualificação gerada pelo app.")
            return
        self.recover_live_assistant_text("qualification")

    def _occurrence_document_replacements(self) -> dict[str, str]:
        now = datetime.now()
        qualification = self._live_editor_value("qualification")
        statement = self._live_editor_value("statement")
        first_qualification_item = qualification.split(",", 1)[0].strip()
        if ":" in first_qualification_item:
            label, value = first_qualification_item.split(":", 1)
            if label.strip().casefold() in ("nome", "nome completo"):
                first_qualification_item = value.strip()
        # Os marcadores usados nos modelos devem entrar em minúsculas,
        # inclusive quando aparecem no início da frase.
        year_words = portuguese_number_words(now.year).lower()
        month_words = PORTUGUESE_MONTHS[now.month - 1].lower()
        replacements = {
            "dia_do_mes_atual_em_numero": str(now.day),
            "mês_atual_por_extenso": month_words,
            # Os modelos originais usam este mesmo marcador com "ę".
            "męs_atual_por_extenso": month_words,
            "ano_atual_por_extenso": year_words,
            "cidade": str(self.settings.get("police_city") or "").strip(),
            "delegacia": str(self.settings.get("police_station") or "").strip(),
            "delegado": str(self.settings.get("police_delegate") or "").strip(),
            "cargo": str(self.settings.get("police_role") or "").strip(),
            "conteúdo_da_caixa_de_qualificacao": qualification,
            "conteúdo_da_caixa_de_oitiva": statement,
            "nome": first_qualification_item,
            "usuario": str(self.settings.get("police_name") or "").strip(),
            "usuário": str(self.settings.get("police_name") or "").strip(),
            "horário_atual_no_formato_12:34:56": now.strftime("%H:%M:%S"),
            "ano_atual_no_formato_yyyy": str(now.year),
        }
        return replacements

    def generate_occurrence_document(self):
        if self.live_state != "idle" or self.assistant_busy or self.running:
            return
        qualification = self._live_editor_value("qualification")
        statement = self._live_editor_value("statement")
        missing = []
        if not qualification:
            missing.append("qualificação")
        if not statement:
            missing.append("oitiva")
        if missing:
            messagebox.showwarning(
                "Gerar documento",
                "Preencha a caixa de " + " e ".join(missing) + " antes de executar.",
                parent=self.root,
            )
            return
        self._set_live_document_preview_visible(True)
        self._set_embedded_document_preview_message(
            "Aguardando a geração do documento..."
        )
        self.request_live_qualification(generate_document=True)

    def _generate_occurrence_document_from_current_text(self):
        qualification = self._live_editor_value("qualification")
        statement = self._live_editor_value("statement")
        if not qualification or not statement:
            self.status_var.set(
                "Não consegui gerar o documento porque faltou a qualificação ou a oitiva."
            )
            return
        document_kind = (
            "declarations" if self.qualification_declarations_var.get() else "deposition"
        )
        document_started = time.perf_counter()
        self._begin_activity_step("document", "Documento requisitado")
        combined = self.assistant_task_states.get("qualification_document") == "running"
        if combined:
            # Fluxo "Qualificando e gerando documento": a linha única do painel
            # continua cobrindo as duas etapas; o log mantém uma linha por etapa.
            self.assistant_task_states["document"] = "idle"
            self.assistant_task_elapsed["document"] = None
        else:
            for task in ("document", "document_copy", "document_save_docx", "document_save_pdf"):
                self.assistant_task_states[task] = "idle"
                self.assistant_task_elapsed[task] = None
            self.assistant_task_states["document"] = "running"
            self.assistant_task_started_at["document"] = time.monotonic()
        self._render_assistant_progress()
        try:
            template_path = ensure_document_templates()[document_kind]
            output_dir = app_base_dir() / "temp" / "documentos"
            output_name = (
                f"{'declaracoes' if document_kind == 'declarations' else 'depoimento'}_"
                f"{datetime.now():%Y%m%d_%H%M%S}.docx"
            )
            output_path = output_dir / output_name
            marker_count = generate_docx_from_template(
                template_path,
                output_path,
                self._occurrence_document_replacements(),
            )
            document_elapsed = time.perf_counter() - document_started
            self._finish_activity_step("document", document_elapsed)
            if combined:
                total_elapsed = time.monotonic() - (
                    self.assistant_task_started_at.get("qualification_document") or time.monotonic()
                )
                self.assistant_task_states["qualification_document"] = "done"
                self.assistant_task_elapsed["qualification_document"] = total_elapsed
            else:
                self.assistant_task_states["document"] = "done"
                self.assistant_task_elapsed["document"] = document_elapsed
            self._render_assistant_progress()
            self.last_generated_document_path = output_path
            self.last_generated_document_preview_path = None
            for button in (
                self.live_document_copy_button,
                self.live_document_view_button,
                self.live_document_save_button,
            ):
                button.configure(state="normal")
            if not self.live_document_actions_frame.winfo_ismapped():
                self.live_document_actions_frame.place(
                    x=0,
                    y=0,
                    width=222,
                    height=66,
                )
            self.root.after_idle(self._position_live_document_preview)
            self._begin_activity_step("preview", "Preview requisitado")
            self._start_embedded_document_preview(output_path)
            self._set_activity_status(f"Documento requisitado ({document_elapsed:.1f}s)", log=False)
        except Exception as exc:
            document_elapsed = time.perf_counter() - document_started
            self._finish_activity_step("document", document_elapsed, error=str(exc))
            if combined:
                total_elapsed = time.monotonic() - (
                    self.assistant_task_started_at.get("qualification_document") or time.monotonic()
                )
                self.assistant_task_states["qualification_document"] = "error"
                self.assistant_task_elapsed["qualification_document"] = total_elapsed
            else:
                self.assistant_task_states["document"] = "error"
                self.assistant_task_elapsed["document"] = document_elapsed
            self._render_assistant_progress()
            self.last_generated_document_path = None
            self.last_generated_document_preview_path = None
            self.last_generated_document_preview_image_path = None
            self.document_preview_generation += 1
            self.live_document_actions_frame.place_forget()
            self.live_document_zoom_combo.configure(state="disabled")
            self.document_preview_page_var.set("Não foi possível gerar a prévia.")
            self._set_embedded_document_preview_message(
                "Não foi possível gerar o documento."
            )
            messagebox.showerror(
                "Gerar documento",
                f"Não consegui gerar o documento.\n\nDetalhe: {exc}",
                parent=self.root,
            )
            self._set_activity_status(f"Documento ERRO ({document_elapsed:.1f}s): {exc}", log=False)

    def copy_generated_occurrence_document(self):
        document_path = self.last_generated_document_path
        if not document_path or not document_path.exists():
            messagebox.showwarning(
                "Copiar documento",
                "Execute a geração do documento antes de copiar.",
                parent=self.root,
            )
            return
        copy_started = time.perf_counter()
        self._begin_activity_step("document:copy", "Cópia requisitada")
        self.assistant_task_states["document_copy"] = "running"
        self.assistant_task_elapsed["document_copy"] = None
        self.assistant_task_started_at["document_copy"] = time.monotonic()
        self._render_assistant_progress()
        self.live_document_copy_button.configure(state="disabled")
        self._set_document_copy_progress(True)
        self._set_activity_status("Copiando documento", log=False)
        threading.Thread(
            target=self._copy_generated_occurrence_document_worker,
            args=(document_path, copy_started),
            daemon=True,
        ).start()

    def _copy_generated_occurrence_document_worker(
        self,
        document_path: Path,
        copy_started: float,
    ):
        copy_elapsed = lambda: time.perf_counter() - copy_started
        if os.name != "nt":
            self._queue(
                "document_clipboard_error",
                "A cópia formatada deste documento está disponível no Windows.",
                copy_elapsed(),
            )
            return
        script = r"""
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
$doNotSaveChanges = 0
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($env:SIG_GENERATED_DOCX, $false, $true)
    $plainText = [string]$document.Content.Text
    $document.SaveAs2($env:SIG_CLIPBOARD_RTF, 6)
    $document.Close([ref]$doNotSaveChanges)
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    $document = $null

    $document = $word.Documents.Open($env:SIG_GENERATED_DOCX, $false, $true)
    $document.SaveAs2($env:SIG_CLIPBOARD_HTML, 10)
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($env:SIG_CLIPBOARD_TEXT, $plainText, $utf8)
    $document.Close([ref]$doNotSaveChanges)
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    $document = $null
    $word.Quit([ref]$doNotSaveChanges)
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
    $word = $null
} finally {
    if ($null -ne $document) {
        try { $document.Close([ref]$doNotSaveChanges) } catch {}
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) } catch {}
    }
    if ($null -ne $word) {
        try { $word.Quit([ref]$doNotSaveChanges) } catch {}
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) } catch {}
    }
}
"""
        try:
            with tempfile.TemporaryDirectory(prefix="sig-word-clipboard-") as temporary:
                clipboard_dir = Path(temporary)
                rtf_path = clipboard_dir / "document.rtf"
                html_path = clipboard_dir / "document.htm"
                text_path = clipboard_dir / "document.txt"
                env = os.environ.copy()
                env.update(
                    {
                        "SIG_GENERATED_DOCX": str(document_path),
                        "SIG_CLIPBOARD_RTF": str(rtf_path),
                        "SIG_CLIPBOARD_HTML": str(html_path),
                        "SIG_CLIPBOARD_TEXT": str(text_path),
                    }
                )
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Sta", "-Command", script],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    timeout=45,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode != 0:
                    detail = (result.stderr or result.stdout or "falha desconhecida").strip()
                    raise RuntimeError(detail)
                set_windows_document_clipboard(
                    rtf_path.read_bytes(),
                    html_path.read_bytes(),
                    text_path.read_text(encoding="utf-8"),
                )
            self._queue("document_clipboard_ready", document_path, copy_elapsed())
        except Exception as exc:
            self._queue("document_clipboard_error", str(exc), copy_elapsed())

    def save_generated_occurrence_document(self):
        document_path = self.last_generated_document_path
        if not document_path or not document_path.exists():
            messagebox.showwarning(
                "Salvar documento",
                "Gere o documento antes de salvar.",
                parent=self.root,
            )
            return
        save_type_var = StringVar(value="Documento do Word")
        documents_dir = Path.home() / "Documents"
        if not documents_dir.is_dir():
            documents_dir = Path.home()
        destination = filedialog.asksaveasfilename(
            parent=self.root,
            title="Salvar documento",
            initialdir=str(documents_dir),
            initialfile=document_path.stem,
            defaultextension=".docx",
            filetypes=(
                ("Documento do Word", "*.docx"),
                ("Documento PDF", "*.pdf"),
            ),
            typevariable=save_type_var,
        )
        if not destination:
            return
        destination_path = Path(destination)
        desired_suffix = (
            ".pdf"
            if "pdf" in save_type_var.get().casefold()
            else ".docx"
        )
        if destination_path.suffix.casefold() != desired_suffix:
            destination_path = destination_path.with_suffix(desired_suffix)
        suffix = destination_path.suffix.casefold()
        if suffix not in {".docx", ".pdf"}:
            messagebox.showerror(
                "Salvar documento",
                "Escolha o tipo Documento do Word (.docx) ou Documento PDF (.pdf).",
                parent=self.root,
            )
            return
        save_started = time.perf_counter()
        save_task = "document_save_docx" if suffix == ".docx" else "document_save_pdf"
        self._active_document_save_task = save_task
        self.assistant_task_states[save_task] = "running"
        self.assistant_task_elapsed[save_task] = None
        self.assistant_task_started_at[save_task] = time.monotonic()
        self._render_assistant_progress()
        self._begin_activity_step(
            "document:save:docx" if suffix == ".docx" else "document:save:pdf",
            "Docx requisitado" if suffix == ".docx" else "Pdf requisitado",
        )
        self.live_document_save_button.configure(state="disabled")
        self._set_activity_status("Salvando documento", log=False)
        threading.Thread(
            target=self._save_generated_occurrence_document_worker,
            args=(document_path, destination_path, save_started),
            daemon=True,
        ).start()

    def _save_generated_occurrence_document_worker(
        self,
        document_path: Path,
        destination_path: Path,
        save_started: float,
    ):
        try:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            if destination_path.suffix.casefold() == ".pdf":
                with tempfile.TemporaryDirectory(prefix="sig-word-pdf-") as temporary:
                    temporary_pdf = Path(temporary) / destination_path.name
                    export_docx_to_pdf_with_word(document_path, temporary_pdf)
                    shutil.copy2(temporary_pdf, destination_path)
            elif document_path.resolve() != destination_path.resolve():
                shutil.copy2(document_path, destination_path)
            self._queue(
                "document_save_ready",
                destination_path,
                time.perf_counter() - save_started,
            )
        except Exception as exc:
            self._queue(
                "document_save_error",
                str(exc),
                time.perf_counter() - save_started,
            )

    def open_document_viewer(self) -> None:
        """Abre uma janela própria do app com a prévia grande (zoom 100)."""
        document_path = self.last_generated_document_path
        if not document_path or not document_path.exists():
            messagebox.showwarning(
                "Visualizar documento",
                "Gere o documento antes de visualizar.",
                parent=self.root,
            )
            return
        viewer = Toplevel(self.root)
        viewer.title(f"Visualizar documento — {document_path.stem}")
        viewer.transient(self.root)
        viewer.geometry("640x480")
        viewer_frame = ttk.Frame(viewer, padding=(10, 10))
        viewer_frame.pack(fill=BOTH, expand=True)
        canvas = Canvas(
            viewer_frame,
            background="#ffffff",
            highlightthickness=0,
            borderwidth=1,
            relief="solid",
        )
        scrollbar = ttk.Scrollbar(viewer_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        canvas._viewer_photo = None
        canvas.update_idletasks()
        canvas.create_text(
            max(120, canvas.winfo_width() / 2),
            max(90, canvas.winfo_height() / 2),
            text="Preparando visualização...",
            fill="#879491",
            width=max(200, canvas.winfo_width() - 60),
        )
        dpi = _window_physical_dpi(self.root)
        threading.Thread(
            target=self._document_viewer_worker,
            args=(viewer, canvas, document_path, dpi),
            daemon=True,
        ).start()

    def _document_viewer_worker(
        self,
        viewer,
        canvas,
        document_path: Path,
        dpi: int,
    ) -> None:
        try:
            preview_path = document_path.with_name(f"{document_path.stem}_visualizacao.pdf")
            if (
                not preview_path.exists()
                or preview_path.stat().st_mtime_ns < document_path.stat().st_mtime_ns
            ):
                export_docx_to_pdf_with_word(document_path, preview_path)
            image_path = document_path.with_name(f"{document_path.stem}_visualizacao_100.png")
            pages, page_regions = render_pdf_preview(preview_path, image_path, 100, dpi)
            self._queue(
                "document_viewer_ready",
                viewer,
                canvas,
                image_path,
                list(page_regions),
            )
        except Exception as exc:
            self._queue("document_viewer_error", viewer, canvas, str(exc))

    def request_live_qualification(self, *, generate_document: bool = False):
        raw_text = self._live_editor_value("qualification")
        if not raw_text:
            messagebox.showwarning(
                "sig",
                "Não há texto na caixa de qualificação.",
                parent=self.root,
            )
            self.status_var.set("Cole ou digite uma qualificação antes de organizar.")
            self.live_assistant_status_var.set("Aguardando o texto da qualificação.")
            return
        if self.live_state != "idle" or self.assistant_busy or self.running:
            return
        self.pending_occurrence_document_generation = bool(generate_document)
        generation, settings = self._begin_assistant_request("qualification", "live")
        if generate_document:
            self.assistant_task_states["qualification_document"] = "running"
            self.assistant_task_elapsed["qualification_document"] = None
            self.assistant_task_started_at["qualification_document"] = time.monotonic()
            self._render_assistant_progress()
        self._begin_activity_step("assistant:qualification", "Qualificação requisitada")
        self.live_assistant_status_var.set("Organizando qualificação...")
        self._set_activity_status("Qualificação requisitada", log=False)
        self.assistant_thread = threading.Thread(
            target=self._live_qualification_worker,
            args=(generation, settings, raw_text),
            daemon=True,
        )
        self.assistant_thread.start()

    def _live_qualification_worker(self, generation: int, settings: dict, raw_text: str) -> None:
        client = self.assistant_client
        if not client:
            return
        started = time.monotonic()
        try:
            result = client.post(
                selected_text_model_for(settings, "qualification"),
                DEFAULT_QUALIFICATION_SYSTEM_PROMPT,
                qualification_user_prompt(list(LIVE_QUALIFICATION_FIELD_IDS), raw_text),
            )
            self._queue(
                "live_qualification_result",
                generation,
                result,
                time.monotonic() - started,
            )
        except Cancelled:
            pass
        except Exception as exc:
            self._queue(
                "live_qualification_error",
                generation,
                str(exc),
                time.monotonic() - started,
            )
        finally:
            self._queue("assistant_finished", generation)

    def recover_live_transcript(self):
        if self.live_state != "idle" or self.assistant_busy or not self.last_live_transcript_text:
            return
        if self._live_editor_value("transcript") and not messagebox.askyesno("sig", "Deseja sobrescrever o texto atual?"):
            return
        self._replace_live_text(self.last_live_transcript_text)
        self.status_var.set("Última transcrição recuperada.")

    def recover_live_integral_audio(self):
        if (
            self.live_state != "idle"
            or self.assistant_busy
            or not self.live_audio_recovery_available
            or not self.live_full_pcm_path
            or not self.live_full_pcm_path.exists()
        ):
            return
        confirmed = messagebox.askyesno(
            "Reenviar áudio integral",
            "O áudio integral gravado durante o streaming será enviado ao Grok por REST.\n\n"
            "A transcrição atual da caixa de texto será substituída pela resposta dessa nova requisição.\n\n"
            "Deseja continuar?",
            parent=self.root,
        )
        if not confirmed:
            return
        pcm_path = self.live_full_pcm_path
        self.live_audio_recovery_available = False
        self._set_live_audio_recovery_visible(False)
        self._replace_live_text("")
        self.live_recovery_cancel_event.clear()
        self._set_live_state("finalizing")
        self.status_var.set("Enviando áudio integral do streaming ao Grok por REST...")
        self.live_recovery_thread = threading.Thread(
            target=self._recover_live_integral_audio_worker,
            args=(pcm_path,),
            daemon=True,
        )
        self.live_recovery_thread.start()

    def _recover_live_integral_audio_worker(self, pcm_path: Path):
        temp_live = app_base_dir() / "temp" / "live"
        raw_dir = temp_live / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        wav_path = temp_live / f"live_grok_integral_{int(time.time() * 1000)}.wav"
        raw_path = raw_dir / f"{wav_path.stem}.json"
        try:
            if not pcm_path.exists() or pcm_path.stat().st_size < 1024:
                raise RuntimeError("o áudio integral não está disponível")
            settings = (self.live_grok_settings or load_settings()).copy()
            api_key = str(settings.get("grok_api_key") or "").strip()
            if not api_key:
                raise RuntimeError("chave API do Grok não configurada")
            write_wav_from_pcm_file(wav_path, pcm_path)
            fields = {
                "language": self.live_grok_language or "pt",
                "format": "true",
                "filler_words": "false",
            }
            if self.live_grok_diarize:
                fields["diarize"] = "true"
            uploader = GraniteUploader(
                self.live_recovery_cancel_event,
                fields,
                {"Authorization": f"Bearer {api_key}"},
                "file",
            )
            status, parsed = uploader.post_file_parsed(
                GROK_STT_URL,
                wav_path,
                "audio/wav",
                raw_path,
            )
            if status != 200:
                raw = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else ""
                raise RuntimeError(f"HTTP {status}\n{raw}")
            if not parsed.text.strip():
                raise RuntimeError("o Grok retornou uma transcrição vazia")
            self._queue("live_recovery_result", parsed.text, parsed.timestamped_text)
            self._queue("status", "Transcrição do áudio integral concluída.")
        except Cancelled:
            self._queue("live_recovery_error", "Envio do áudio integral cancelado.")
        except Exception as exc:
            self._queue("live_recovery_error", f"Não foi possível transcrever o áudio integral: {exc}")
        finally:
            wav_path.unlink(missing_ok=True)

    def recover_live_transcript_2(self):
        if self.live_state != "idle" or self.assistant_busy or not self.last_live_transcript_text_2:
            return
        if self._live_editor_value("transcript2") and not messagebox.askyesno("sig", "Deseja sobrescrever o texto atual?"):
            return
        self._set_live_editor("transcript2", self.last_live_transcript_text_2)
        self.status_var.set("Última transcrição do modelo 2 recuperada.")

    @staticmethod
    def _live_editor_label(kind: str) -> str:
        return {
            "transcript": "transcrição",
            "transcript2": "transcrição 2",
            "history": "histórico",
            "history2": "histórico 2",
            "statement": "oitiva",
            "statement2": "oitiva 2",
            "qualification": "qualificação",
        }[kind]

    def show_live_diarization_help(self):
        messagebox.showinfo("Diarização", "A diarização tenta identificar interlocutores diferentes. O Grok rotula as falas como Interlocutor 1, Interlocutor 2 e assim por diante.")

    def _current_stt_provider(self) -> str | None:
        if is_deepgram_transcription(self.settings):
            return "deepgram"
        if is_assemblyai_transcription(self.settings):
            return "assemblyai"
        if is_elevenlabs_transcription(self.settings):
            return "elevenlabs"
        if is_grok_transcription(self.settings):
            return "grok"
        return None

    def _rebuild_live_language_menu(self):
        provider = self._current_stt_provider()
        menu = self.live_language_menu
        menu.delete(0, "end")
        if provider is None:
            self.live_language_label_var.set("Idioma")
            return
        for option in MENU_OPTIONS[provider]:
            menu.add_command(label=option, command=lambda selected=option: self._set_live_language(selected))
        self.live_language_button.configure(menu=menu)
        mode = language_mode(self.settings, provider)
        custom = language_custom(self.settings, provider)
        shown = custom if mode == "custom" and custom else mode
        self.live_language_label_var.set(f"Idioma: {shown}")

    def _set_live_language(self, code: str):
        provider = self._current_stt_provider()
        if provider is None:
            return
        if code == "custom":
            self._show_custom_language_dialog(provider)
            return
        self.settings[stt_provider_rules.KEY_LANGUAGE_MODE[provider]] = code
        save_settings(self.settings)
        self.live_language_var.set(code)
        self.live_language_label_var.set(f"Idioma: {code}")
        self._set_activity_status(f"Idioma selecionado: {code}.", log=False)

    def _show_custom_language_dialog(self, provider: str):
        win = tk.Toplevel(self.root)
        win.title("Código do idioma")
        win.configure(background="#101418")
        win.resizable(False, False)
        win.transient(self.root)
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=BOTH, expand=True)
        entry = ttk.Entry(frame, width=28)
        entry.insert(0, language_custom(self.settings, provider))
        entry.pack(fill=X, pady=(0, 8))
        hint = ttk.Label(
            frame,
            text="Digite um ou mais códigos, separados por vírgula.\nEx: en, es, pt",
            justify="left",
        )
        hint.pack(anchor="w", pady=(0, 8))

        def apply_codes():
            raw = entry.get().strip()
            codes = parse_codes(raw)
            invalid = invalid_codes(provider, codes)
            if not codes:
                messagebox.showinfo("Código do idioma", "Digite pelo menos um código de idioma.", parent=win)
                return
            if invalid:
                messagebox.showinfo(
                    "Código do idioma",
                    f"O modelo não suporta: {', '.join(invalid)}.\nCorrija e tente novamente.",
                    parent=win,
                )
                return
            self.settings[stt_provider_rules.KEY_LANGUAGE_MODE[provider]] = "custom"
            self.settings[stt_provider_rules.KEY_LANGUAGE_CUSTOM[provider]] = ",".join(codes)
            save_settings(self.settings)
            self.live_language_label_var.set(f"Idioma: {','.join(codes)}")
            self._set_activity_status("Idioma custom salvo.", log=False)
            win.destroy()

        def show_help():
            messagebox.showinfo(
                "Códigos aceitos",
                codes_for_help(provider),
                parent=win,
            )

        buttons = ttk.Frame(frame)
        buttons.pack(fill=X, pady=(4, 0))
        ttk.Button(buttons, text="Voltar", command=win.destroy).pack(side=LEFT)
        ttk.Button(buttons, text="?", width=3, command=show_help).pack(side=LEFT, padx=6)
        ttk.Button(buttons, text="OK", command=apply_codes).pack(side=RIGHT)

    def _format_grok_diarized_transcript(self, payload: dict, fallback: str) -> str:
        if not self.live_diarize_var.get() or not isinstance(payload.get("words"), list):
            return fallback
        output, speaker = [], None
        for word in payload["words"]:
            if not isinstance(word, dict):
                continue
            text = str(word.get("text") or word.get("word") or "").strip()
            if not text:
                continue
            next_speaker = word.get("speaker")
            if next_speaker != speaker:
                speaker = next_speaker
                try:
                    label = int(speaker) + 1
                except (TypeError, ValueError):
                    label = 1
                output.append(f"\nInterlocutor {label}: {text}")
            elif output:
                output.append(("" if text in ",.;:!?" else " ") + text)
        return "".join(output).strip() or fallback

    def _refresh_live_grok_controls(self):
        diarize_supported = (
            is_grok_transcription(self.settings)
            or is_deepgram_transcription(self.settings)
            or is_assemblyai_transcription(self.settings)
            or is_elevenlabs_transcription(self.settings)
        )
        if diarize_supported:
            self.live_grok_controls.pack(side=LEFT, before=self.live_top_spacer)
        else:
            self.live_grok_controls.pack_forget()
            self.live_diarize_var.set(False)
        self._rebuild_live_language_menu()
        interval_state = "disabled" if self.live_state != "idle" else "readonly"
        for widget in (self.live_interval_entry, self.live_interval_minus, self.live_interval_plus):
            widget.configure(state=interval_state)

    def start_normal_live_recording(self):
        if self.normal_recording:
            self.normal_record_stop_event.set()
            self.status_var.set("Enviando a gravação para transcrição...")
            return
        if self.normal_recording:
            self.normal_record_stop_event.set()
        if self.running or self.live_state != "idle" or self.normal_recording or self.assistant_busy:
            messagebox.showinfo("sig", "Conclua a tarefa em andamento antes de gravar.")
            return
        self.settings = load_settings()
        if is_grok_transcription(self.settings) and not self.settings.get("grok_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Grok nas configurações antes de gravar.")
            return
        if is_deepgram_transcription(self.settings) and not self.settings.get("deepgram_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Deepgram nas configurações antes de gravar.")
            return
        self.normal_record_grok = is_grok_transcription(self.settings)
        self.normal_record_deepgram = is_deepgram_transcription(self.settings)
        self.normal_record_language = (
            deepgram_language_param(self.settings)
            if is_deepgram_transcription(self.settings)
            else grok_language_param(self.settings) or "pt"
        )
        self.normal_record_diarize = (self.normal_record_grok or self.normal_record_deepgram) and bool(
            self.live_diarize_var.get()
        )
        self.normal_record_paused = False
        self.normal_recording = True
        self.normal_record_stop_event.clear()
        self._reset_live_waveform()
        temp = app_base_dir() / "temp" / "live"; temp.mkdir(parents=True, exist_ok=True)
        self.normal_record_pcm_path = temp / f"gravacao_{int(time.time() * 1000)}.pcm"
        self._draw_normal_live_mic_button()
        self._draw_live_pause_button()
        self.status_var.set("Gravando. Clique novamente no microfone branco para enviar.")
        self.normal_record_thread = threading.Thread(target=self._normal_live_record_worker, daemon=True)
        self.normal_record_thread.start()

    def _normal_live_record_worker(self):
        try:
            import sounddevice as sd
            pcm_path = self.normal_record_pcm_path
            if not pcm_path:
                return
            with pcm_path.open("wb") as output:
                def callback(indata, *_args):
                    if not self.normal_record_stop_event.is_set() and not self.normal_record_paused:
                        chunk = bytes(indata)
                        self._push_live_waveform_chunk(chunk)
                        output.write(chunk)
                with sd.RawInputStream(samplerate=LIVE_SAMPLE_RATE, channels=1, dtype="int16", callback=callback):
                    while not self.normal_record_stop_event.wait(.1):
                        pass
            if not pcm_path.exists() or not pcm_path.stat().st_size:
                self._queue("status", "Gravação vazia."); return
            wav_path = pcm_path.with_suffix(".wav")
            write_wav_from_pcm_file(wav_path, pcm_path)
            cancel = threading.Event()
            grok = self.normal_record_grok
            api_provider = (
                getattr(self, "normal_record_deepgram", False)
                or is_assemblyai_transcription(self.settings)
                or is_elevenlabs_transcription(self.settings)
            )
            if api_provider:
                record_settings = self.settings.copy()
                if getattr(self, "normal_record_deepgram", False) and self.normal_record_diarize:
                    record_settings["diarize"] = True
                uploader = create_transcription_uploader(cancel, record_settings)
                url = transcribe_url(record_settings)
            else:
                fields = {"language": self.normal_record_language, "format": "true", "filler_words": "false"}
                if self.normal_record_diarize:
                    fields["diarize"] = "true"
                uploader = GraniteUploader(
                    cancel,
                    fields,
                    {"Authorization": f"Bearer {self.settings['grok_api_key']}"} if grok else {},
                    "file" if grok else "files",
                )
                url = GROK_STT_URL if grok else transcribe_url(self.settings)
            status, parsed = uploader.post_file_parsed(
                url,
                wav_path,
                "audio/wav",
                wav_path.with_suffix(".raw"),
            )
            if status != 200: raise RuntimeError(f"HTTP {status}")
            self._queue("live_payload", parsed.text, parsed.timestamped_text, grok)
            self._queue("status", "Transcrição concluída.")
        except Exception as exc:
            self._queue("status", f"Erro na gravação: {exc}")
        finally:
            self.normal_recording = False
            self.normal_record_paused = False
            self.root.after(0, self._draw_normal_live_mic_button)
            self.root.after(0, self._draw_live_pause_button)

    def _set_live_state(self, state: str):
        self.live_state = state
        self._draw_live_mic_button()
        self._draw_live_pause_button()
        self._set_live_audio_recovery_visible(
            state == "idle" and self.live_audio_recovery_available
        )
        locked = state != "idle"
        interval_state = "disabled" if locked else "readonly"
        for widget in (self.live_interval_entry, self.live_interval_minus, self.live_interval_plus):
            widget.configure(state=interval_state)
        self._refresh_live_editors_state()

    def _change_live_interval(self, direction: int):
        if self.live_state != "idle":
            return
        if self._live_text_value() and not messagebox.askyesno("sig", "A transcrição atual será sobrescrita. Deseja continuar?"):
            return
        values = LIVE_INTERVAL_VALUES_MS
        try:
            index = values.index(self.live_interval_ms)
        except ValueError:
            index = min(range(len(values)), key=lambda item: abs(values[item] - self.live_interval_ms))
        index = max(0, min(len(values) - 1, index + (1 if direction > 0 else -1)))
        self._set_live_interval_ms(values[index])

    def _set_live_interval_ms(self, value: int):
        self.live_interval_ms = min(LIVE_INTERVAL_VALUES_MS, key=lambda item: abs(item - value))
        self.live_interval_var.set(f"{self.live_interval_ms / 1000:.1f}")

    def _apply_live_interval_entry(self):
        raw = self.live_interval_var.get().replace(",", ".").strip()
        try:
            value = float(raw)
        except ValueError:
            value = self.live_interval_ms / 1000
        self._set_live_interval_ms(int(value * 1000))

    def _set_live_text(self, text: str):
        self._set_live_editor("transcript", text)

    def _current_live_text_locked(self) -> str:
        committed = self.live_committed_text.strip()
        draft = self.live_draft_text.strip()
        if committed and draft:
            return f"{committed}\n{draft}"
        return committed or draft

    def _queue_live_display(self):
        with self.live_lock:
            text = self._current_live_text_locked()
        self._queue("live_display", text)

    def _show_save_hint(self):
        if self.last_html_path and self.last_html_path.exists():
            self.status_var.set("Salvar uma cópia do HTML em outra pasta.")
        else:
            self.status_var.set("O botão de salvar ficará disponível ao final da transcrição.")

    def _refresh_server_label(self):
        self.server_var.set("")
        self._refresh_assistant_model_label()

    def _show_multi_model_help(self):
        messagebox.showinfo(
            "Multi model",
            "Ferramenta experimental. O SIG envia o mesmo áudio simultaneamente para os dois endpoints "
            "de transcrição definidos nas Configurações e mostra os resultados lado a lado.",
            parent=self.root,
        )

    def _show_multi_text_help(self):
        messagebox.showinfo(
            "Multi model - texto",
            "Quando esta opção está ativa, o SIG envia o conteúdo da transcrição para os dois modelos "
            "de texto definidos nas Configurações. As respostas são mantidas na mesma ordem: o Modelo "
            "de texto 1 preenche a primeira caixa e o Modelo de texto 2 preenche a segunda. O mesmo "
            "critério é usado na geração de Histórico e Oitiva.",
            parent=self.root,
        )

    def _align_multi_controls(self):
        if not getattr(self, "multi_controls", None) or not self.multi_controls.winfo_exists():
            return
        top = self.multi_controls.master
        top.update_idletasks()
        self.multi_controls.update_idletasks()
        top.configure(height=max(top.winfo_reqheight(), self.multi_controls.winfo_reqheight()))
        top.pack_propagate(False)
        self.multi_controls.place(
            relx=0.66,
            x=0,
            y=0,
            anchor="n",
        )

    def _toggle_multi_text_model(self):
        self.settings = load_settings()
        self.multi_text_secondary = str(self.settings.get("text_model_2") or "")
        if self.multi_text_model_var.get() and not self.multi_text_secondary:
            self.multi_text_model_var.set(False)
            messagebox.showinfo(
                "Multi model - texto",
                "Selecione primeiro o Modelo de texto 2 nas Configurações.",
                parent=self.root,
            )
            return
        if self.assistant_busy:
            self.multi_text_model_var.set(not self.multi_text_model_var.get())
            return
        self._refresh_multi_text_layout()

    def _refresh_multi_text_visibility(self):
        available = bool(self.multi_text_secondary)
        if available:
            self.multi_text_check.grid()
            self.multi_text_help_button.grid()
        else:
            self.multi_text_model_var.set(False)
            self.multi_text_check.grid_remove()
            self.multi_text_help_button.grid_remove()
        self._refresh_multi_text_layout()
        self.root.after_idle(self._align_multi_controls)

    def _toggle_multi_model(self):
        if self.live_state != "idle":
            self.multi_model_var.set(self.live_secondary_active)
            messagebox.showinfo(
                "Multi model",
                "Pare a transcrição ao vivo antes de ativar ou desativar o Multi model.",
                parent=self.root,
            )
            return
        self.settings = load_settings()
        self.multi_model_secondary = str(self.settings.get("transcription_server_2") or "")
        if self.multi_model_var.get() and not self.multi_model_secondary:
            self.multi_model_var.set(False)
            messagebox.showinfo(
                "Multi model",
                "Selecione primeiro o Modelo de transcrição 2 nas Configurações.",
                parent=self.root,
            )
            return
        self._refresh_multi_model_layout()

    def _refresh_multi_model_layout(self):
        enabled = bool(self.multi_model_var.get() and self.multi_model_secondary)
        if enabled:
            self.live_text._editor_frame.configure(width=440)
            if not self.live_secondary_pane.winfo_manager():
                self.live_secondary_pane.pack(side=LEFT, fill=X, expand=True, padx=(10, 0))
        else:
            self.live_secondary_pane.pack_forget()
            self.live_text._editor_frame.configure(width=900)
        self._refresh_primary_transcript_actions(enabled)
        self._refresh_assistant_model_label()

    def _refresh_multi_text_layout(self):
        if not getattr(self, "live_history_primary_pane", None):
            return
        enabled = bool(self.multi_text_model_var.get() and self.multi_text_secondary)
        pairs = (
            (
                self.live_history_text,
                self.live_history_secondary_pane,
            ),
            (
                self.live_statement_text,
                self.live_statement_secondary_pane,
            ),
        )
        for primary_text, secondary_pane in pairs:
            area = secondary_pane.master
            if enabled:
                area.columnconfigure(0, weight=1, uniform="live_multi_text_panes")
                area.columnconfigure(1, minsize=10)
                area.columnconfigure(2, weight=1, uniform="live_multi_text_panes")
                primary_text._editor_frame.configure(width=440)
                if not secondary_pane.winfo_manager():
                    secondary_pane.grid(row=0, column=2, sticky="ew")
            else:
                secondary_pane.grid_remove()
                area.columnconfigure(0, weight=1, uniform="")
                area.columnconfigure(1, minsize=0)
                area.columnconfigure(2, weight=0, uniform="")
                primary_text._editor_frame.configure(width=900)
        self._refresh_assistant_model_label()

    def _refresh_primary_transcript_actions(self, compact: bool):
        action_sets = (
            (
                self.live_recover_button,
                self.live_history_button,
                self.live_clear_button,
                self.live_copy_button,
                self.live_paste_button,
            ),
            (
                self.live_recover_button_2,
                self.live_history_button_2,
                self.live_clear_button_2,
                self.live_copy_button_2,
                self.live_paste_button_2,
            ),
        )
        for recover, history, clear, copy, paste in action_sets:
            for button in (recover, history, clear, copy, paste):
                button.pack_forget()
                button.place_forget()
            recover.pack(side=LEFT)
            paste.pack(side=RIGHT)
            copy.pack(side=RIGHT, padx=(0, 4))
            clear.pack(side=RIGHT, padx=(0, 4))
        self.root.after_idle(self._position_live_parts_buttons)
        self.root.after(50, self._position_live_parts_buttons)

    def _set_live_timestamp_payload(
        self, plain: str, timestamped: str = "", allow_timestamps: bool = False
    ):
        self.live_plain_transcript_text = (plain or "").strip()
        if allow_timestamps:
            parsed_timestamped = (timestamped or "").strip()
            if parsed_timestamped:
                self.live_timestamped_transcript_text = parsed_timestamped
        else:
            self.live_timestamped_transcript_text = ""
        if not self.live_timestamped_transcript_text:
            self.live_timestamps_var.set(False)
        self.live_timestamps_check.configure(
            state="normal" if self.live_timestamped_transcript_text else "disabled"
        )
        displayed = (
            self.live_timestamped_transcript_text
            if self.live_timestamps_var.get() and self.live_timestamped_transcript_text
            else self.live_plain_transcript_text
        )
        self.last_live_transcript_text = displayed
        self._set_live_text(displayed)

    def _set_live_timestamp_data(self, timestamped: str):
        timestamped = (timestamped or "").strip()
        if not timestamped:
            return
        self.live_timestamped_transcript_text = timestamped
        self.live_timestamps_check.configure(state="normal")
        if self.live_timestamps_var.get():
            self.last_live_transcript_text = timestamped
            self._set_live_text(timestamped)

    def _toggle_live_timestamps(self):
        if self.live_timestamps_var.get() and not self.live_timestamped_transcript_text:
            self.live_timestamps_var.set(False)
            return
        displayed = (
            self.live_timestamped_transcript_text
            if self.live_timestamps_var.get()
            else self.live_plain_transcript_text
        )
        self.last_live_transcript_text = displayed
        self._set_live_text(displayed)

    def _convert_only_changed(self):
        if self.convert_only_var.get() and self.mode_var.get() == "as_is":
            self.mode_var.set("ready")
        if self.convert_only_var.get():
            self.vad_only_var.set(False)
        state = "disabled" if self.convert_only_var.get() else "normal"
        self.as_is_radio.configure(state=state)
        self._refresh_zip_controls()
        self._refresh_tree_modes()

    def _vad_changed(self):
        self._refresh_vad_only_visibility()

    def _vad_only_changed(self):
        if self.vad_only_var.get():
            self.convert_only_var.set(False)
            self._convert_only_changed()
        self._refresh_vad_only_visibility()

    def _refresh_vad_only_visibility(self):
        if not hasattr(self, "vad_only_check"):
            return
        if self.vad_var.get() == "Off":
            self.vad_only_check.pack_forget()
            self.vad_only_var.set(False)
        else:
            self.vad_only_check.pack(side=LEFT, padx=(0, 0))

    _vad_tooltip_window = None

    def _show_vad_info(self):
        messagebox.showinfo(
            "Sobre VAD",
            "VAD (Voice Activity Detection) detecta trechos de voz em áudios.\n\n"
            "Níveis de agressividade:\n"
            "  0 = menos agressivo (detecta mais voz)\n"
            "  3 = mais agressivo (filtra mais, só voz clara)\n\n"
            "WebRTC — rápido, baseado em frames de 30ms\n"
            "Silero  — rede neural ONNX, mais preciso\n\n"
            "O VAD é aplicado após a conversão para WAV 16kHz mono 16-bit.\n"
            "Marque 'Apenas VAD' para converter, aplicar o filtro e não transcrever."
        )

    def _show_vad_tooltip(self):
        if self._vad_tooltip_window:
            return
        tw = tk.Toplevel(self.root)
        tw.wm_overrideredirect(True)
        x = self.root.winfo_pointerx() + 16
        y = self.root.winfo_pointery() + 16
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text="0 = menos agressivo (detecta mais voz)\n3 = mais agressivo (filtra mais)",
                         background="#ffffcc", relief="solid", borderwidth=1,
                         font=("Segoe UI", 9), justify="left", padx=6, pady=4)
        label.pack()
        self._vad_tooltip_window = tw

    def _hide_vad_tooltip(self):
        if self._vad_tooltip_window:
            self._vad_tooltip_window.destroy()
            self._vad_tooltip_window = None

    def _refresh_zip_controls(self):
        if hasattr(self, "zip_level_frame"):
            if self.send_zip_var.get() and not self.convert_only_var.get():
                self.zip_level_frame.pack(side=LEFT)
            else:
                self.zip_level_frame.pack_forget()
        if hasattr(self, "tree"):
            self._refresh_tree_modes()

    def _zip_help_text(self) -> str:
        return (
            "Junta os arquivos já preparados em um único ZIP e faz uma só requisição ao servidor.\n\n"
            "Pode ser mais rápido em lotes grandes, porque reduz várias idas e voltas pela rede. Em compensação, "
            "o app precisa criar o ZIP, o servidor precisa descompactar e compactar a resposta, e um erro no ZIP "
            "pode afetar o lote inteiro.\n\n"
            "O nível 1 costuma ter o melhor benefício: reduz bastante o tamanho com pouco custo de tempo. "
            "O nível 9 pode compactar um pouco mais, mas em áudio e vídeo normalmente a diferença é pequena. "
            "Sem compactação cria o ZIP mais rápido, mas envia um arquivo maior."
        )

    def _schedule_zip_help(self, event):
        self.zip_help_position = (event.x_root + 14, event.y_root + 18)
        if self.zip_help_after_id:
            self.root.after_cancel(self.zip_help_after_id)
        self.zip_help_after_id = self.root.after(700, self._show_zip_help)

    def _show_zip_help(self):
        self.zip_help_after_id = None
        if self.zip_help_window or not self.zip_check.winfo_exists():
            return
        import tkinter as tk

        x, y = self.zip_help_position
        win = Toplevel(self.root)
        win.withdraw()
        win.overrideredirect(True)
        win.configure(background="#172024")
        frame = tk.Frame(win, background="#172024", borderwidth=1, relief="solid")
        frame.pack(fill=BOTH, expand=True)
        tk.Label(
            frame,
            text=self._zip_help_text(),
            background="#172024",
            foreground="#edf7f5",
            justify="left",
            wraplength=420,
            padx=12,
            pady=10,
            font=("Segoe UI", 9),
        ).pack()
        win.geometry(f"+{x}+{y}")
        win.deiconify()
        self.zip_help_window = win

    def _hide_zip_help(self, _event=None):
        if self.zip_help_after_id:
            self.root.after_cancel(self.zip_help_after_id)
            self.zip_help_after_id = None
        if self.zip_help_window:
            try:
                self.zip_help_window.destroy()
            except Exception:
                pass
            self.zip_help_window = None

    def add_files(self):
        files = filedialog.askopenfilenames(
            title="Selecionar arquivos de áudio ou vídeo",
            filetypes=[
                ("Áudio e vídeo", "*.wav *.mp3 *.m4a *.ogg *.opus *.flac *.aac *.wma *.mp4 *.mov *.mkv *.avi *.webm"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        self._add_paths([Path(item) for item in files])

    def add_folder(self):
        folder = filedialog.askdirectory(title="Selecionar pasta")
        if not folder:
            return
        paths = [
            item
            for item in Path(folder).iterdir()
            if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        self._add_paths(paths)
        if not paths:
            messagebox.showinfo("sig", "Nenhum áudio ou vídeo compatível foi encontrado nessa pasta.")

    def _add_paths(self, paths: list[Path]):
        existing = {path.resolve() for path in self.selected_paths}
        added = False
        for path in paths:
            if not path.exists() or not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in existing:
                continue
            self.selected_paths.append(path)
            existing.add(resolved)
        # Reordena por tamanho (crescente)
        self.selected_paths.sort(key=lambda p: p.stat().st_size)
        # Remove itens antigos da árvore e reinsere em ordem
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_items.clear()
        for i, path in enumerate(self.selected_paths):
            kb = path.stat().st_size // 1024
            item = self.tree.insert("", END, values=(path.name, f"{kb} KB", "Aguardando"))
            self.tree_items[path] = item
            added = True
        if added:
            self.status_var.set(f"{len(self.selected_paths)} arquivo(s) na fila.")

    def _open_selected_original(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        item = selected[0]
        path = next((path for path, tree_item in self.tree_items.items() if tree_item == item), None)
        if not path:
            return
        try:
            os.startfile(path)
            self.status_var.set(f"Abrindo {path.name}")
        except Exception as exc:
            messagebox.showerror("sig", f"Não foi possível abrir o arquivo:\n{exc}")

    def clear_files(self):
        if self.running:
            return
        self.selected_paths.clear()
        self.tree_items.clear()
        self.last_html_path = None
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.progress_var.set(0)
        self._draw_save_button()
        self._show_folder_button(visible=False)
        self.status_var.set("Fila limpa.")

    def _update_tree_size(self, tree_item, size_str: str):
        """Atualiza a coluna de Tamanho (chamado da thread)."""
        try:
            if self.tree.exists(tree_item):
                values = list(self.tree.item(tree_item, "values"))
                if len(values) >= 2:
                    values[1] = size_str
                    self.tree.item(tree_item, values=values)
        except Exception:
            pass

    # _compute_and_update_duration removida — coluna agora é Tamanho (KB), definida na inserção

    def _format_duration(self, path: Path) -> str:
        """Usa ffprobe preferencialmente (rápido e preciso)."""
        try:
            if hasattr(self, "ffmpeg_tools") and self.ffmpeg_tools is not None:
                secs = int(round(self.ffmpeg_tools._get_duration_only(path) or 0))
                if secs > 0:
                    return f"{secs}s"
            return "—"
        except Exception:
            return "—"

    def _refresh_tree_modes(self):
        # Modo não é mais exibido na lista (substituído por Duração).
        # Mantemos o método para compatibilidade com os callbacks dos radios,
        # mas não atualizamos mais a coluna da árvore.
        pass

    def _mode_label(self) -> str:
        base = mode_label_from_value(self.mode_var.get())
        if self.convert_only_var.get():
            return f"{base} / apenas converter"
        if self.send_zip_var.get():
            return f"{base} / zip nível {self.zip_level_var.get()}"
        return base

    def open_settings(self):
        if self.running or self.live_state != "idle" or self.assistant_busy or (getattr(self, "ffmpeg_tools", None) and self.ffmpeg_tools.running):
            messagebox.showinfo("sig", "Conclua ou cancele a tarefa em andamento antes de alterar as configurações.")
            return
        win = Toplevel(self.root)
        win.title("Configurações")
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=18)
        frame.pack(fill=BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        conv_var = IntVar(value=self.settings["convert_parallel"])
        req_var = IntVar(value=self.settings["transcribe_parallel"])
        transcription_labels = {}
        transcription_server_var = StringVar()
        transcription_server_2_labels = {"Nenhum": ""}
        transcription_server_2_var = StringVar(value="Nenhum")
        refreshing_transcription_servers = False
        history_model_labels = {}
        history_model_var = StringVar()
        history_model_2_labels = {"Nenhum": ""}
        history_model_2_var = StringVar(value="Nenhum")
        history_reasoning_var = StringVar(value=self.settings.get("history_reasoning", "low"))
        history_proxy_model_var = StringVar(value=self.settings.get("history_proxy_model", GROK_TEXT_NAME))
        history_reasoning_2_var = StringVar(value=self.settings.get("history_reasoning_2", "low"))
        history_proxy_model_2_var = StringVar(value=self.settings.get("history_proxy_model_2", GROK_TEXT_NAME))
        statement_model_labels = {}
        statement_model_var = StringVar()
        statement_model_2_labels = {"Nenhum": ""}
        statement_model_2_var = StringVar(value="Nenhum")
        statement_reasoning_var = StringVar(value=self.settings.get("statement_reasoning", "low"))
        statement_proxy_model_var = StringVar(value=self.settings.get("statement_proxy_model", GROK_TEXT_NAME))
        statement_reasoning_2_var = StringVar(value=self.settings.get("statement_reasoning_2", "low"))
        statement_proxy_model_2_var = StringVar(value=self.settings.get("statement_proxy_model_2", GROK_TEXT_NAME))
        extraction_var = StringVar(value=PARTS_EXTRACTION_LABELS[self.settings["parts_extraction"]])
        parts_model_var = StringVar(value=self.settings.get("parts_model", IA_PROXY_NAME))
        parts_proxy_model_var = StringVar(
            value=self.settings.get("parts_proxy_model", GROK_TEXT_NAME)
        )
        parts_reasoning_var = StringVar(value=self.settings.get("parts_reasoning", "low"))
        parts_model_labels: dict[str, str] = {}
        qualification_model_var = StringVar(value=self.settings.get("qualification_model", IA_PROXY_NAME))
        qualification_proxy_model_var = StringVar(
            value=self.settings.get("qualification_proxy_model", GROK_TEXT_NAME)
        )
        qualification_reasoning_var = StringVar(value=self.settings.get("qualification_reasoning", "low"))
        qualification_model_labels: dict[str, str] = {}
        grok_api_key_var = StringVar(value=self.settings.get("grok_api_key", ""))
        deepseek_api_key_var = StringVar(value=self.settings.get("deepseek_api_key", ""))
        deepgram_api_key_var = StringVar(value=self.settings.get("deepgram_api_key", ""))
        deepgram_keyterms_var = StringVar(value=self.settings.get("deepgram_keyterms", ""))
        assemblyai_api_key_var = StringVar(value=self.settings.get("assemblyai_api_key", ""))
        elevenlabs_api_key_var = StringVar(value=self.settings.get("elevenlabs_api_key", ""))
        imei_api_key_var = StringVar(value=self.settings.get("imei_api_key", ""))
        police_name_var = StringVar(value=self.settings.get("police_name", ""))
        police_role_var = StringVar(value=self.settings.get("police_role", ""))
        police_station_var = StringVar(value=self.settings.get("police_station", ""))
        police_delegate_var = StringVar(value=self.settings.get("police_delegate", ""))
        police_city_var = StringVar(value=self.settings.get("police_city", ""))
        grok_chunk_ms_var = StringVar(value=str(self.settings.get("grok_chunk_ms", 100)))
        grok_rest_var = BooleanVar(value=bool(self.settings.get("grok_rest_requests", False)))

        import tkinter as tk
        # Duas colunas: a primeira com os dados gerais, a segunda com os
        # modelos de texto por tarefa.
        columns = []
        for col_index, titles in enumerate(
            (
                ("Policial", "Chaves API", "Transcrição", "Paralelismo"),
                ("Histórico", "Oitiva", "Extração de partes", "Qualificação"),
            )
        ):
            column = ttk.Frame(frame)
            column.grid(
                row=0,
                column=col_index,
                sticky="n",
                padx=(0, 9) if col_index == 0 else (9, 0),
            )
            column_sections = []
            for title in titles:
                section = ttk.LabelFrame(
                    column,
                    text=title,
                    padding=(12, 8),
                    style="Settings.TLabelframe",
                )
                section.grid(row=len(column_sections), column=0, sticky="ew", pady=(0, 8))
                section.columnconfigure(0, minsize=170)
                section.columnconfigure(1, weight=1)
                column_sections.append(section)
            columns.append(column_sections)
        (
            police_frame,
            api_frame,
            transcription_frame,
            parallel_frame,
        ) = columns[0]
        (
            history_frame,
            statement_frame,
            extraction_frame,
            qualification_frame,
        ) = columns[1]

        cpu_count = max(1, os.cpu_count() or 1)

        def parallel_selector(
            row: int,
            label: str,
            variable: IntVar,
            maximum: int,
            values: list[int] | None = None,
        ):
            ttk.Label(parallel_frame, text=label).grid(
                row=row, column=0, sticky="w", pady=5, padx=(0, 12)
            )
            label_var = StringVar(value=str(variable.get()))
            button = ttk.Menubutton(parallel_frame, textvariable=label_var, width=3)
            menu = tk.Menu(button, tearoff=False)
            options = values if values is not None else list(range(1, maximum + 1))
            for value in options:
                menu.add_command(
                    label=str(value),
                    command=lambda selected=value: (variable.set(selected), label_var.set(str(selected))),
                )
            button.configure(menu=menu)
            button.grid(row=row, column=1, sticky="w", pady=5)
            return button

        cpu_options = cpu_parallel_options(cpu_count)
        if conv_var.get() not in cpu_options:
            conv_var.set(cpu_count)
        parallel_selector(0, "Conversões paralelas", conv_var, cpu_count * 4, values=cpu_options)
        parallel_selector(1, "Requisições paralelas", req_var, 16)

        grok_key_row = 0
        ttk.Label(api_frame, text="Chave API da xAI").grid(
            row=grok_key_row, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        grok_key_entry = ttk.Entry(api_frame, textvariable=grok_api_key_var, show="*", width=44)
        grok_key_entry.grid(row=grok_key_row, column=1, sticky="ew", pady=5)
        create_tooltip(grok_key_entry, "Obrigatória para selecionar modelos da xAI em transcrição ou texto.")

        deepseek_key_row = grok_key_row + 1
        ttk.Label(api_frame, text="Chave API do Deepseek").grid(
            row=deepseek_key_row, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        deepseek_key_entry = ttk.Entry(api_frame, textvariable=deepseek_api_key_var, show="*", width=44)
        deepseek_key_entry.grid(row=deepseek_key_row, column=1, sticky="ew", pady=5)
        create_tooltip(
            deepseek_key_entry,
            "Obrigatória para selecionar DeepSeek V4 Flash ou DeepSeek V4 Pro.",
        )

        imei_key_row = deepseek_key_row + 1
        ttk.Label(api_frame, text="Chave API do IMEI Check").grid(
            row=imei_key_row, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        imei_key_entry = ttk.Entry(api_frame, textvariable=imei_api_key_var, show="*", width=44)
        imei_key_entry.grid(row=imei_key_row, column=1, sticky="ew", pady=5)

        deepgram_key_row = imei_key_row + 1
        ttk.Label(api_frame, text="Chave API do Deepgram").grid(
            row=deepgram_key_row, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        deepgram_key_entry = ttk.Entry(
            api_frame, textvariable=deepgram_api_key_var, show="*", width=44
        )
        deepgram_key_entry.grid(row=deepgram_key_row, column=1, sticky="ew", pady=5)
        create_tooltip(
            deepgram_key_entry,
            "Preencha para liberar o modelo Nova 3 do Deepgram na lista de transcrição.",
        )

        deepgram_keyterms_row = deepgram_key_row + 1
        ttk.Label(api_frame, text="Palavras-chave do Deepgram").grid(
            row=deepgram_keyterms_row, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        deepgram_keyterms_entry = ttk.Entry(
            api_frame, textvariable=deepgram_keyterms_var, width=44
        )
        deepgram_keyterms_entry.grid(row=deepgram_keyterms_row, column=1, sticky="ew", pady=5)
        create_tooltip(
            deepgram_keyterms_entry,
            "Termos que o Nova 3 deve priorizar na transcrição, separados por vírgula "
            "(ex.: Taguaí, Fartura, ruas e nomes locais). Limite: 500 tokens no total.",
        )

        assemblyai_key_row = deepgram_keyterms_row + 1
        ttk.Label(api_frame, text="Chave API da AssemblyAI").grid(
            row=assemblyai_key_row, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        assemblyai_key_entry = ttk.Entry(
            api_frame, textvariable=assemblyai_api_key_var, show="*", width=44
        )
        assemblyai_key_entry.grid(row=assemblyai_key_row, column=1, sticky="ew", pady=5)
        create_tooltip(
            assemblyai_key_entry,
            "Preencha para liberar o modelo AssemblyAI Universal-3.5 Pro na lista de transcrição.",
        )

        elevenlabs_key_row = assemblyai_key_row + 1
        ttk.Label(api_frame, text="Chave API da ElevenLabs").grid(
            row=elevenlabs_key_row, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        elevenlabs_key_entry = ttk.Entry(
            api_frame, textvariable=elevenlabs_api_key_var, show="*", width=44
        )
        elevenlabs_key_entry.grid(row=elevenlabs_key_row, column=1, sticky="ew", pady=5)
        create_tooltip(
            elevenlabs_key_entry,
            "Preencha para liberar o Scribe v2 Realtime da ElevenLabs na lista de transcrição.",
        )

        transcription_server_row = 0
        ttk.Label(transcription_frame, text="Modelo de transcrição 1").grid(
            row=transcription_server_row,
            column=0,
            sticky="w",
            pady=5,
            padx=(0, 12),
        )
        transcription_server_combo = ttk.Combobox(
            transcription_frame,
            textvariable=transcription_server_var,
            state="readonly",
            width=44,
        )
        transcription_server_combo.grid(row=transcription_server_row, column=1, sticky="ew", pady=5)

        def refresh_transcription_servers(preferred_name: str | None = None):
            nonlocal transcription_labels, transcription_server_2_labels, refreshing_transcription_servers
            if refreshing_transcription_servers:
                return
            refreshing_transcription_servers = True
            transcription_servers = [
                server
                for server in read_transcription_servers()
                if (server["name"] != GROK_API_NAME or plausible_xai_api_key(grok_api_key_var.get()))
                and (
                    server["name"] != DEEPGRAM_API_NAME
                    or bool(deepgram_api_key_var.get().strip())
                )
                and (
                    server["name"] != ASSEMBLYAI_API_NAME
                    or plausible_assemblyai_api_key(assemblyai_api_key_var.get())
                )
                and (
                    server["name"] != ELEVENLABS_API_NAME
                    or plausible_elevenlabs_api_key(elevenlabs_api_key_var.get())
                )
            ]
            transcription_labels = {
                transcription_server_label(server): server["name"]
                for server in transcription_servers
            }
            transcription_server_combo.configure(values=list(transcription_labels))
            target_name = preferred_name or selected_transcription_server(self.settings)["name"]
            selected_label = next(
                (label for label, name in transcription_labels.items() if name == target_name),
                next(iter(transcription_labels), ""),
            )
            transcription_server_var.set(selected_label)
            primary_name = transcription_labels.get(selected_label, "")
            transcription_server_2_labels = {"Nenhum": ""}
            transcription_server_2_labels.update(
                {
                    transcription_server_label(server): server["name"]
                    for server in transcription_servers
                    if server["name"] != primary_name
                }
            )
            transcription_server_2_combo.configure(values=list(transcription_server_2_labels))
            target_secondary = str(self.settings.get("transcription_server_2") or "")
            current_secondary = transcription_server_2_labels.get(transcription_server_2_var.get(), "")
            wanted_secondary = current_secondary or target_secondary
            secondary_label = next(
                (label for label, name in transcription_server_2_labels.items() if name == wanted_secondary),
                "Nenhum",
            )
            transcription_server_2_var.set(secondary_label)
            refreshing_transcription_servers = False

        def add_server():
            dialog = Toplevel(win)
            dialog.title("Adicionar servidor de transcrição")
            dialog.resizable(False, False)
            dialog.transient(win)
            dialog.grab_set()
            dialog_frame = ttk.Frame(dialog, padding=16)
            dialog_frame.pack(fill=BOTH, expand=True)
            name_var = StringVar()
            url_var = StringVar()
            model_var = StringVar()
            for row, (label, variable) in enumerate(
                (("Nome do servidor", name_var), ("URL", url_var), ("Nome do modelo", model_var))
            ):
                ttk.Label(dialog_frame, text=label).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
                entry = ttk.Entry(dialog_frame, textvariable=variable, width=46)
                entry.grid(row=row, column=1, sticky="ew", pady=4)
                if row == 0:
                    entry.focus_set()

            dialog_buttons = ttk.Frame(dialog_frame)
            dialog_buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))

            def confirm_add():
                added, reason = add_transcription_server(name_var.get(), url_var.get(), model_var.get())
                if not added:
                    messagebox.showerror("sig", reason, parent=dialog)
                    return
                current_name = transcription_labels.get(transcription_server_var.get())
                refresh_transcription_servers(current_name)
                dialog.destroy()

            ttk.Button(dialog_buttons, text="Cancelar", command=dialog.destroy).pack(side=LEFT, padx=(0, 8))
            ttk.Button(dialog_buttons, text="Adicionar", command=confirm_add).pack(side=LEFT)
            dialog.bind("<Return>", lambda _event: confirm_add())
            dialog.bind("<Escape>", lambda _event: dialog.destroy())

        def remove_server():
            server_name = transcription_labels.get(transcription_server_var.get())
            if not server_name:
                messagebox.showinfo("sig", "Selecione um servidor para remover.", parent=win)
                return
            if server_name == GROK_API_NAME:
                messagebox.showinfo("sig", "Grok STT é uma opção integrada e não pode ser removida.", parent=win)
                return
            if not messagebox.askyesno("sig", f"Remover o servidor {server_name}?", parent=win):
                return
            if not remove_transcription_server(server_name):
                messagebox.showerror("sig", "Não consegui remover o servidor.", parent=win)
                return
            refresh_transcription_servers()
            if self.settings.get("transcription_server") == server_name:
                replacement = transcription_labels.get(transcription_server_var.get())
                if replacement:
                    self.settings = save_settings({**self.settings, "transcription_server": replacement})
                    self._refresh_server_label()

        transcription_server_2_row = transcription_server_row + 1
        transcription_server_2_label = ttk.Label(transcription_frame, text="Modelo de transcrição 2")
        transcription_server_2_label.grid(
            row=transcription_server_2_row, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        transcription_server_2_combo = ttk.Combobox(
            transcription_frame,
            textvariable=transcription_server_2_var,
            state="readonly",
            width=44,
        )
        transcription_server_2_combo.grid(row=transcription_server_2_row, column=1, sticky="ew", pady=5)

        def primary_server_changed(*_args):
            refresh_transcription_servers(transcription_labels.get(transcription_server_var.get()))
            refresh_chunk_visibility()

        chunk_size_row = transcription_server_row + 2
        chunk_controls = ttk.Frame(transcription_frame, style="Settings.TFrame")
        chunk_label = ttk.Label(
            chunk_controls,
            text="Chunk size:",
            width=12,
            anchor="w",
            style="Settings.TLabel",
        )
        chunk_label.pack(side=LEFT, padx=(0, 10))
        grok_chunk_entry = ttk.Combobox(
            chunk_controls,
            textvariable=grok_chunk_ms_var,
            values=("50", "100", "200", "500", "1000"),
            state="readonly",
            width=8,
        )
        grok_chunk_entry.pack(side=LEFT)

        def show_chunk_help():
            messagebox.showinfo(
                "Chunk size do Grok",
                "Define, em milissegundos, o tamanho de cada pedaço de áudio enviado ao streaming do Grok.\n\n"
                "O valor recomendado pela xAI é 100 ms. Não altere esta configuração se não souber exatamente "
                "o que está fazendo.",
                parent=win,
            )

        chunk_help = ttk.Button(chunk_controls, text="?", width=2, command=show_chunk_help)
        chunk_help.pack(side=LEFT, padx=(5, 0))
        chunk_controls.grid(row=chunk_size_row, column=1, columnspan=3, sticky="w", pady=5)

        rest_controls = ttk.Frame(transcription_frame, style="Settings.TFrame")

        def confirm_grok_rest():
            if not grok_rest_var.get():
                return
            confirmed = messagebox.askyesno(
                "Requisições REST do Grok",
                "Esta opção desativa o streaming WebSocket do Grok e envia o áudio em janelas REST, "
                "como no Granite NAR.\n\n"
                "Os rascunhos seguirão o intervalo t= selecionado, mas a atualização poderá ter mais atraso "
                "e o consumo de requisições será maior.\n\n"
                "Tem certeza que deseja usar Requisições REST?",
                parent=win,
            )
            if not confirmed:
                grok_rest_var.set(False)

        rest_check = ttk.Checkbutton(
            rest_controls,
            text="Requisições REST",
            variable=grok_rest_var,
            command=confirm_grok_rest,
            style="Settings.TCheckbutton",
        )
        rest_check.pack(side=LEFT)

        def refresh_chunk_visibility(*_args):
            selected_name = transcription_labels.get(transcription_server_var.get(), "")
            selected_name_2 = transcription_server_2_labels.get(transcription_server_2_var.get(), "")
            if selected_name == GROK_API_NAME:
                chunk_row = transcription_server_2_row
                rest_row = chunk_row + 1
                secondary_row = rest_row + 1
                chunk_controls.grid_configure(row=chunk_row, column=1)
                rest_controls.grid_configure(row=rest_row, column=1, sticky="w")
                transcription_server_2_label.grid_configure(row=secondary_row)
                transcription_server_2_combo.grid_configure(row=secondary_row)
                chunk_controls.grid()
                rest_controls.grid()
            elif selected_name_2 == GROK_API_NAME:
                chunk_row = chunk_size_row
                rest_row = chunk_row + 1
                chunk_controls.grid_configure(row=chunk_row, column=1)
                rest_controls.grid_configure(row=rest_row, column=1, sticky="w")
                transcription_server_2_label.grid_configure(row=transcription_server_2_row)
                transcription_server_2_combo.grid_configure(row=transcription_server_2_row)
                chunk_controls.grid()
                rest_controls.grid()
            else:
                transcription_server_2_label.grid_configure(row=transcription_server_2_row)
                transcription_server_2_combo.grid_configure(row=transcription_server_2_row)
                chunk_controls.grid_remove()
                rest_controls.grid_remove()

        refresh_transcription_servers()
        transcription_server_var.trace_add("write", primary_server_changed)
        transcription_server_2_var.trace_add("write", refresh_chunk_visibility)
        refresh_chunk_visibility()

        proxy_model_options = (
            GROK_NON_REASONING_TEXT_NAME,
            GROK_TEXT_NAME,
            DEEPSEEK_TEXT_NAME,
        )

        def set_menu_value(variable: StringVar, display: StringVar, value: str):
            variable.set(value)
            display.set(value)

        def configure_menu(menu, variable: StringVar, display: StringVar, values: tuple[str, ...]):
            menu.delete(0, tk.END)
            selected_value = variable.get()
            if selected_value not in values:
                selected_value = values[0]
                variable.set(selected_value)
            display.set(selected_value)
            for value in values:
                menu.add_command(
                    label=value,
                    command=lambda selected=value, target=variable, label_var=display: set_menu_value(
                        target, label_var, selected
                    ),
                )

        def refresh_model_reasoning_controls(
            selected_name: str,
            proxy_model_var: StringVar,
            proxy_model_frame,
            proxy_model_menu,
            proxy_model_display: StringVar,
            reasoning_var: StringVar,
            current_reasoning_frame,
            reasoning_menu,
            reasoning_display: StringVar,
            proxy_model_row: int,
            current_reasoning_row: int,
        ):
            is_proxy = selected_name == IA_PROXY_NAME
            if is_proxy:
                proxy_model_frame.grid(row=proxy_model_row, column=1, columnspan=3, sticky="w", pady=5)
                configure_menu(proxy_model_menu, proxy_model_var, proxy_model_display, proxy_model_options)
                actual_model = proxy_model_var.get()
            else:
                proxy_model_frame.grid_remove()
                actual_model = selected_name
            if actual_model == DEEPSEEK_TEXT_NAME:
                reasoning_options = ("none", "low", "high", "max")
            elif actual_model == GROK_TEXT_NAME:
                reasoning_options = ("low", "medium", "high", "xhigh")
            else:
                current_reasoning_frame.grid_remove()
                return
            configure_menu(reasoning_menu, reasoning_var, reasoning_display, reasoning_options)
            current_reasoning_frame.grid(
                row=current_reasoning_row, column=1, columnspan=3, sticky="w", pady=5
            )

        def make_two_model_section(
            section_frame,
            *,
            model_var,
            model_2_var,
            reasoning_var,
            reasoning_2_var,
            proxy_var,
            proxy_2_var,
            settings_model_key,
            settings_model_2_key,
            settings_reasoning_key,
            settings_reasoning_2_key,
            settings_proxy_key,
            settings_proxy_2_key,
            label_first,
            label_second,
        ):
            model_labels = {}
            model_2_labels = {"Nenhum": ""}
            model_row = 0
            ttk.Label(section_frame, text=label_first).grid(
                row=model_row,
                column=0,
                sticky="w",
                pady=5,
                padx=(0, 12),
            )
            model_combo = ttk.Combobox(
                section_frame,
                textvariable=model_var,
                state="readonly",
                width=44,
            )
            model_combo.grid(row=model_row, column=1, sticky="ew", pady=5)
            model_2_row = model_row + 3
            ttk.Label(section_frame, text=label_second).grid(
                row=model_2_row, column=0, sticky="w", pady=5, padx=(0, 12)
            )
            model_2_combo = ttk.Combobox(
                section_frame, textvariable=model_2_var, state="readonly", width=44
            )
            model_2_combo.grid(row=model_2_row, column=1, sticky="ew", pady=5)

            proxy_model_row = model_row + 1
            proxy_model_frame = ttk.Frame(section_frame, style="Settings.TFrame")
            ttk.Label(
                proxy_model_frame,
                text="Modelo",
                width=12,
                anchor="w",
                style="Settings.TLabel",
            ).pack(
                side=LEFT, padx=(0, 10)
            )
            proxy_model_display_var = StringVar(value=proxy_var.get())
            proxy_model_button = ttk.Menubutton(
                proxy_model_frame, textvariable=proxy_model_display_var, width=30
            )
            proxy_model_menu = tk.Menu(proxy_model_button, tearoff=False)
            proxy_model_button.configure(menu=proxy_model_menu)
            proxy_model_button.pack(side=LEFT)

            reasoning_row = model_row + 2
            reasoning_frame = ttk.Frame(section_frame, style="Settings.TFrame")
            reasoning_label = ttk.Label(
                reasoning_frame,
                text="Raciocínio:",
                width=12,
                anchor="w",
                style="Settings.TLabel",
            )
            reasoning_label.pack(side=LEFT, padx=(0, 10))
            reasoning_display_var = StringVar(value=reasoning_var.get())
            reasoning_button = ttk.Menubutton(
                reasoning_frame, textvariable=reasoning_display_var, width=12
            )
            reasoning_menu = tk.Menu(reasoning_button, tearoff=False)
            reasoning_button.configure(menu=reasoning_menu)
            reasoning_button.pack(side=LEFT)

            proxy_model_2_row = model_2_row + 1
            proxy_model_2_frame = ttk.Frame(section_frame, style="Settings.TFrame")
            ttk.Label(
                proxy_model_2_frame,
                text="Modelo",
                width=12,
                anchor="w",
                style="Settings.TLabel",
            ).pack(
                side=LEFT, padx=(0, 10)
            )
            proxy_model_2_display_var = StringVar(value=proxy_2_var.get())
            proxy_model_2_button = ttk.Menubutton(
                proxy_model_2_frame, textvariable=proxy_model_2_display_var, width=30
            )
            proxy_model_2_menu = tk.Menu(proxy_model_2_button, tearoff=False)
            proxy_model_2_button.configure(menu=proxy_model_2_menu)
            proxy_model_2_button.pack(side=LEFT)

            reasoning_2_row = model_2_row + 2
            reasoning_2_frame = ttk.Frame(section_frame, style="Settings.TFrame")
            reasoning_2_label = ttk.Label(
                reasoning_2_frame,
                text="Raciocínio:",
                width=12,
                anchor="w",
                style="Settings.TLabel",
            )
            reasoning_2_label.pack(side=LEFT, padx=(0, 10))
            reasoning_2_display_var = StringVar(value=reasoning_2_var.get())
            reasoning_2_button = ttk.Menubutton(
                reasoning_2_frame, textvariable=reasoning_2_display_var, width=12
            )
            reasoning_2_menu = tk.Menu(reasoning_2_button, tearoff=False)
            reasoning_2_button.configure(menu=reasoning_2_menu)
            reasoning_2_button.pack(side=LEFT)

            def refresh(preferred_name: str | None = None):
                available_models = [
                    model
                    for model in read_text_models()
                    if (
                        (
                            model["name"] not in GROK_TEXT_API_NAMES
                            or plausible_xai_api_key(grok_api_key_var.get())
                        )
                        and (
                            model["name"] not in DEEPSEEK_API_NAMES
                            or plausible_deepseek_api_key(deepseek_api_key_var.get())
                        )
                    )
                ]
                model_labels.clear()
                model_labels.update(
                    {
                        (
                            model["name"]
                            if model["name"] == IA_PROXY_NAME or model["name"] in GROK_TEXT_API_NAMES or model["name"] in DEEPSEEK_API_NAMES
                            else f"{model['name']} ({model['parameters'].get('model', 'modelo não informado')})"
                        ): model["name"]
                        for model in available_models
                    }
                )
                model_combo.configure(values=list(model_labels))
                target_name = preferred_name or str(self.settings.get(settings_model_key) or "")
                if not target_name:
                    target_name = selected_text_model_config(self.settings)["name"]
                selected_label = next(
                    (label for label, name in model_labels.items() if name == target_name),
                    next(iter(model_labels), ""),
                )
                model_var.set(selected_label)
                primary_name = model_labels.get(selected_label, "")
                model_2_labels.clear()
                model_2_labels["Nenhum"] = ""
                model_2_labels.update(
                    {
                        label: name
                        for label, name in model_labels.items()
                        if name != primary_name or name == IA_PROXY_NAME
                    }
                )
                model_2_combo.configure(values=list(model_2_labels))
                wanted_secondary = (
                    model_2_labels.get(model_2_var.get(), "")
                    or str(self.settings.get(settings_model_2_key) or "")
                )
                secondary_label = next(
                    (label for label, name in model_2_labels.items() if name == wanted_secondary),
                    "Nenhum",
                )
                model_2_var.set(secondary_label)

            def refresh_reasoning_controls(*_args):
                refresh_model_reasoning_controls(
                    model_labels.get(model_var.get(), ""),
                    proxy_var,
                    proxy_model_frame,
                    proxy_model_menu,
                    proxy_model_display_var,
                    reasoning_var,
                    reasoning_frame,
                    reasoning_menu,
                    reasoning_display_var,
                    proxy_model_row,
                    reasoning_row,
                )

            def refresh_reasoning_2_controls(*_args):
                refresh_model_reasoning_controls(
                    model_2_labels.get(model_2_var.get(), ""),
                    proxy_2_var,
                    proxy_model_2_frame,
                    proxy_model_2_menu,
                    proxy_model_2_display_var,
                    reasoning_2_var,
                    reasoning_2_frame,
                    reasoning_2_menu,
                    reasoning_2_display_var,
                    proxy_model_2_row,
                    reasoning_2_row,
                )

            refresh()
            model_var.trace_add("write", refresh_reasoning_controls)
            model_2_var.trace_add("write", refresh_reasoning_2_controls)
            model_combo.bind(
                "<<ComboboxSelected>>",
                lambda _event: refresh(model_labels.get(model_var.get(), "")),
            )
            proxy_var.trace_add("write", refresh_reasoning_controls)
            proxy_2_var.trace_add("write", refresh_reasoning_2_controls)
            refresh_reasoning_controls()
            refresh_reasoning_2_controls()
            return {
                "labels": model_labels,
                "labels_2": model_2_labels,
                "refresh": refresh,
            }

        history_ui = make_two_model_section(
            history_frame,
            model_var=history_model_var,
            model_2_var=history_model_2_var,
            reasoning_var=history_reasoning_var,
            reasoning_2_var=history_reasoning_2_var,
            proxy_var=history_proxy_model_var,
            proxy_2_var=history_proxy_model_2_var,
            settings_model_key="history_model",
            settings_model_2_key="history_model_2",
            settings_reasoning_key="history_reasoning",
            settings_reasoning_2_key="history_reasoning_2",
            settings_proxy_key="history_proxy_model",
            settings_proxy_2_key="history_proxy_model_2",
            label_first="Modelo de histórico 1",
            label_second="Modelo de histórico 2",
        )
        statement_ui = make_two_model_section(
            statement_frame,
            model_var=statement_model_var,
            model_2_var=statement_model_2_var,
            reasoning_var=statement_reasoning_var,
            reasoning_2_var=statement_reasoning_2_var,
            proxy_var=statement_proxy_model_var,
            proxy_2_var=statement_proxy_model_2_var,
            settings_model_key="statement_model",
            settings_model_2_key="statement_model_2",
            settings_reasoning_key="statement_reasoning",
            settings_reasoning_2_key="statement_reasoning_2",
            settings_proxy_key="statement_proxy_model",
            settings_proxy_2_key="statement_proxy_model_2",
            label_first="Modelo de oitiva 1",
            label_second="Modelo de oitiva 2",
        )

        def make_single_model_section(
            section_frame,
            *,
            model_var,
            reasoning_var,
            proxy_var,
            settings_model_key,
            settings_reasoning_key,
            settings_proxy_key,
            model_labels_holder,
            start_row: int = 0,
        ):
            model_row = start_row
            model_label = ttk.Label(section_frame, text="Modelo:")
            model_label.grid(row=model_row, column=0, sticky="w", pady=5, padx=(0, 12))
            model_combo = ttk.Combobox(
                section_frame,
                textvariable=model_var,
                state="readonly",
                width=44,
            )
            model_combo.grid(row=model_row, column=1, sticky="ew", pady=5)

            proxy_model_row = model_row + 1
            proxy_model_frame = ttk.Frame(section_frame, style="Settings.TFrame")
            ttk.Label(
                proxy_model_frame,
                text="Modelo",
                width=12,
                anchor="w",
                style="Settings.TLabel",
            ).pack(
                side=LEFT, padx=(0, 10)
            )
            proxy_model_display_var = StringVar(value=proxy_var.get())
            proxy_model_button = ttk.Menubutton(
                proxy_model_frame, textvariable=proxy_model_display_var, width=30
            )
            proxy_model_menu = tk.Menu(proxy_model_button, tearoff=False)
            proxy_model_button.configure(menu=proxy_model_menu)
            proxy_model_button.pack(side=LEFT)

            reasoning_row = model_row + 2
            reasoning_frame = ttk.Frame(section_frame, style="Settings.TFrame")
            ttk.Label(
                reasoning_frame,
                text="Raciocínio:",
                width=12,
                anchor="w",
                style="Settings.TLabel",
            ).pack(side=LEFT, padx=(0, 10))
            reasoning_display_var = StringVar(value=reasoning_var.get())
            reasoning_button = ttk.Menubutton(
                reasoning_frame, textvariable=reasoning_display_var, width=12
            )
            reasoning_menu = tk.Menu(reasoning_button, tearoff=False)
            reasoning_button.configure(menu=reasoning_menu)
            reasoning_button.pack(side=LEFT)

            def refresh():
                model_labels_holder.clear()
                model_labels_holder.update(history_ui["labels"])
                model_combo.configure(values=list(model_labels_holder))
                current = model_var.get() or str(self.settings.get(settings_model_key) or IA_PROXY_NAME)
                target = current if current in model_labels_holder else IA_PROXY_NAME
                if model_var.get() != target:
                    model_var.set(target)
                configure_menu(
                    proxy_model_menu,
                    proxy_var,
                    proxy_model_display_var,
                    proxy_model_options,
                )
                refresh_reasoning_controls()

            def refresh_reasoning_controls(*_args):
                refresh_model_reasoning_controls(
                    model_labels_holder.get(model_var.get(), ""),
                    proxy_var,
                    proxy_model_frame,
                    proxy_model_menu,
                    proxy_model_display_var,
                    reasoning_var,
                    reasoning_frame,
                    reasoning_menu,
                    reasoning_display_var,
                    proxy_model_row,
                    reasoning_row,
                )

            refresh()
            model_var.trace_add("write", refresh_reasoning_controls)
            proxy_var.trace_add("write", refresh_reasoning_controls)
            refresh_reasoning_controls()
            return {
                "labels": model_labels_holder,
                "refresh": refresh,
                "label": model_label,
                "combo": model_combo,
                "hideable": [model_label, model_combo, proxy_model_frame, reasoning_frame],
            }

        extraction_row = 0
        ttk.Label(extraction_frame, text="Método").grid(
            row=extraction_row,
            column=0,
            sticky="w",
            pady=5,
            padx=(0, 12),
        )
        extraction_combo = ttk.Combobox(
            extraction_frame,
            textvariable=extraction_var,
            values=list(PARTS_EXTRACTION_LABELS.values()),
            state="readonly",
            width=25,
        )
        extraction_combo.grid(row=extraction_row, column=1, sticky="ew", pady=5)

        extraction_ui = make_single_model_section(
            extraction_frame,
            model_var=parts_model_var,
            reasoning_var=parts_reasoning_var,
            proxy_var=parts_proxy_model_var,
            settings_model_key="parts_model",
            settings_reasoning_key="parts_reasoning",
            settings_proxy_key="parts_proxy_model",
            model_labels_holder=parts_model_labels,
            start_row=1,
        )

        def refresh_extraction_visibility(*_args):
            extraction_key = next(
                (
                    key
                    for key, label in PARTS_EXTRACTION_LABELS.items()
                    if label == extraction_var.get()
                ),
                DEFAULT_SETTINGS["parts_extraction"],
            )
            if extraction_key == "ai":
                extraction_ui["refresh"]()
                # Apenas o rótulo e o seletor do modelo são mostrados aqui; o
                # refresh_reasoning_controls decide sozinho a visibilidade do
                # seletor de modelo do IA-Proxy e do raciocínio.
                extraction_ui["label"].grid()
                extraction_ui["combo"].grid()
            else:
                for widget in extraction_ui["hideable"]:
                    widget.grid_remove()

        extraction_var.trace_add("write", refresh_extraction_visibility)
        parts_model_var.trace_add("write", refresh_extraction_visibility)
        refresh_extraction_visibility()

        qualification_ui = make_single_model_section(
            qualification_frame,
            model_var=qualification_model_var,
            reasoning_var=qualification_reasoning_var,
            proxy_var=qualification_proxy_model_var,
            settings_model_key="qualification_model",
            settings_reasoning_key="qualification_reasoning",
            settings_proxy_key="qualification_proxy_model",
            model_labels_holder=qualification_model_labels,
        )

        ttk.Label(police_frame, text="Nome").grid(
            row=0, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        ttk.Entry(police_frame, textvariable=police_name_var, width=44).grid(
            row=0, column=1, sticky="ew", pady=5
        )
        ttk.Label(police_frame, text="Cargo").grid(
            row=1, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        ttk.Entry(police_frame, textvariable=police_role_var, width=44).grid(
            row=1, column=1, sticky="ew", pady=5
        )
        ttk.Label(police_frame, text="Delegacia").grid(
            row=2, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        police_station_entry = ttk.Entry(
            police_frame,
            textvariable=police_station_var,
            width=44,
        )
        police_station_entry.grid(row=2, column=1, sticky="ew", pady=5)

        def restore_station_placeholder(_event=None):
            if police_station_entry.get().strip():
                return
            police_station_entry.insert(0, "Ex: DEL.POL.TAGUAI")
            police_station_entry.configure(foreground="#879491")
            police_station_entry._placeholder_active = True

        def clear_station_placeholder(_event=None):
            if getattr(police_station_entry, "_placeholder_active", False):
                police_station_entry.delete(0, END)
                police_station_entry.configure(foreground="#1d2b2a")
                police_station_entry._placeholder_active = False

        police_station_entry._placeholder_active = False
        police_station_entry.bind("<FocusIn>", clear_station_placeholder, add="+")
        police_station_entry.bind("<FocusOut>", restore_station_placeholder, add="+")
        restore_station_placeholder()

        ttk.Label(police_frame, text="Delegado").grid(
            row=3, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        ttk.Entry(police_frame, textvariable=police_delegate_var, width=44).grid(
            row=3, column=1, sticky="ew", pady=5
        )
        ttk.Label(police_frame, text="Cidade").grid(
            row=4, column=0, sticky="w", pady=5, padx=(0, 12)
        )
        police_city_entry = ttk.Entry(
            police_frame,
            textvariable=police_city_var,
            width=44,
        )
        police_city_entry.grid(row=4, column=1, sticky="ew", pady=5)

        def restore_city_placeholder(_event=None):
            if police_city_entry.get().strip():
                return
            police_city_entry.insert(0, "Ex: TAGUAI")
            police_city_entry.configure(foreground="#879491")
            police_city_entry._placeholder_active = True

        def clear_city_placeholder(_event=None):
            if getattr(police_city_entry, "_placeholder_active", False):
                police_city_entry.delete(0, END)
                police_city_entry.configure(foreground="#1d2b2a")
                police_city_entry._placeholder_active = False

        police_city_entry._placeholder_active = False
        police_city_entry.bind("<FocusIn>", clear_city_placeholder, add="+")
        police_city_entry.bind("<FocusOut>", restore_city_placeholder, add="+")
        restore_city_placeholder()

        def edit_part_name(add: bool):
            dialog = Toplevel(win)
            dialog.title("Adicionar nome à base" if add else "Remover nome da base")
            dialog.resizable(False, False)
            dialog.transient(win)
            dialog.grab_set()
            dialog_frame = ttk.Frame(dialog, padding=16)
            dialog_frame.pack(fill=BOTH, expand=True)
            ttk.Label(
                dialog_frame,
                text="A base é usada quando a opção Base de nomes está selecionada.",
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
            name_var = StringVar()
            entry = ttk.Entry(dialog_frame, textvariable=name_var, width=38)
            entry.grid(row=1, column=0, columnspan=2, sticky="ew")
            entry.focus_set()
            dialog_buttons = ttk.Frame(dialog_frame)
            dialog_buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))

            def confirm_edit():
                changed = add_name_to_database(name_var.get()) if add else remove_name_from_database(name_var.get())
                if changed:
                    messagebox.showinfo("sig", "Nome adicionado à base." if add else "Nome removido da base.", parent=dialog)
                    dialog.destroy()
                else:
                    messagebox.showerror(
                        "sig",
                        "O nome já existe na base." if add else "Nome não encontrado na base.",
                        parent=dialog,
                    )

            ttk.Button(dialog_buttons, text="Cancelar", command=dialog.destroy).pack(side=LEFT, padx=(0, 8))
            ttk.Button(dialog_buttons, text="Adicionar" if add else "Remover", command=confirm_edit).pack(side=LEFT)
            dialog.bind("<Return>", lambda _event: confirm_edit())
            dialog.bind("<Escape>", lambda _event: dialog.destroy())

        def grok_api_key_changed(*_args):
            primary_name = transcription_labels.get(transcription_server_var.get(), "")
            refresh_transcription_servers(primary_name)
            history_ui["refresh"](history_ui["labels"].get(history_model_var.get(), ""))
            statement_ui["refresh"](statement_ui["labels"].get(statement_model_var.get(), ""))
            extraction_ui["refresh"]()
            qualification_ui["refresh"]()
            refresh_chunk_visibility()

        grok_api_key_var.trace_add("write", grok_api_key_changed)

        def deepseek_api_key_changed(*_args):
            history_ui["refresh"](history_ui["labels"].get(history_model_var.get(), ""))
            statement_ui["refresh"](statement_ui["labels"].get(statement_model_var.get(), ""))
            extraction_ui["refresh"]()
            qualification_ui["refresh"]()

        deepseek_api_key_var.trace_add("write", deepseek_api_key_changed)

        buttons = ttk.Frame(frame)
        buttons.grid(row=1, column=0, columnspan=2, sticky="e", pady=(6, 0))

        def save_and_close():
            selected_transcription = transcription_labels.get(transcription_server_var.get(), "")
            selected_transcription_2 = transcription_server_2_labels.get(transcription_server_2_var.get(), "")
            selected_history = history_ui["labels"].get(history_model_var.get(), "")
            selected_history_2 = history_ui["labels_2"].get(history_model_2_var.get(), "")
            selected_statement = statement_ui["labels"].get(statement_model_var.get(), "")
            selected_statement_2 = statement_ui["labels_2"].get(statement_model_2_var.get(), "")
            api_key = grok_api_key_var.get().strip()
            deepseek_api_key = deepseek_api_key_var.get().strip()
            deepgram_api_key = deepgram_api_key_var.get().strip()
            deepgram_keyterms = deepgram_keyterms_var.get().strip()
            assemblyai_api_key = assemblyai_api_key_var.get().strip()
            elevenlabs_api_key = elevenlabs_api_key_var.get().strip()
            imei_api_key = imei_api_key_var.get().strip()
            police_name = police_name_var.get().strip()
            police_role = police_role_var.get().strip()
            police_station = (
                ""
                if getattr(police_station_entry, "_placeholder_active", False)
                else police_station_var.get().strip()
            )
            police_delegate = police_delegate_var.get().strip()
            police_city = (
                ""
                if getattr(police_city_entry, "_placeholder_active", False)
                else police_city_var.get().strip()
            )
            if api_key and not plausible_xai_api_key(api_key):
                messagebox.showerror(
                    "sig",
                    "A chave API da xAI deve começar com xai- e possuir exatamente 84 caracteres.",
                    parent=win,
                )
                return
            if deepseek_api_key and not plausible_deepseek_api_key(deepseek_api_key):
                messagebox.showerror(
                    "sig",
                    "A chave API do Deepseek deve começar com sk- e possuir exatamente 35 caracteres.",
                    parent=win,
                )
                return
            selected_models = (
                selected_transcription,
                selected_transcription_2,
                selected_history,
                selected_history_2,
                selected_statement,
                selected_statement_2,
            )
            if any(model in GROK_TEXT_API_NAMES for model in selected_models) and not api_key:
                messagebox.showerror("sig", "Insira uma chave API válida da xAI para selecionar este modelo.", parent=win)
                return
            if any(model in DEEPSEEK_API_NAMES for model in selected_models) and not deepseek_api_key:
                messagebox.showerror(
                    "sig",
                    "Insira uma chave API válida do Deepseek para selecionar este modelo.",
                    parent=win,
                )
                return
            for section_name, model_1, model_2, proxy_1, proxy_2 in (
                ("Histórico", selected_history, selected_history_2, history_proxy_model_var.get(), history_proxy_model_2_var.get()),
                ("Oitiva", selected_statement, selected_statement_2, statement_proxy_model_var.get(), statement_proxy_model_2_var.get()),
            ):
                if (
                    model_1 == IA_PROXY_NAME
                    and model_2 == IA_PROXY_NAME
                    and proxy_1 == proxy_2
                ):
                    messagebox.showerror(
                        "sig",
                        f"Ao selecionar IA-Proxy duas vezes em {section_name}, escolha modelos diferentes nos dois seletores.",
                        parent=win,
                    )
                    return
            try:
                grok_chunk_ms = int(grok_chunk_ms_var.get().strip())
            except ValueError:
                messagebox.showerror("sig", "Chunk size deve ser um número inteiro em milissegundos.", parent=win)
                return
            if not 20 <= grok_chunk_ms <= 2000:
                messagebox.showerror("sig", "Chunk size deve ficar entre 20 e 2000 ms.", parent=win)
                return
            extraction_key = next(
                (
                    key
                    for key, label in PARTS_EXTRACTION_LABELS.items()
                    if label == extraction_var.get()
                ),
                DEFAULT_SETTINGS["parts_extraction"],
            )
            selected_parts_model_name = parts_model_labels.get(
                parts_model_var.get(), IA_PROXY_NAME
            )
            selected_parts_proxy_model = parts_proxy_model_var.get()
            if (
                extraction_key == "ai"
                and selected_parts_model_name in GROK_TEXT_API_NAMES
                and not plausible_xai_api_key(api_key)
            ):
                messagebox.showerror(
                    "sig", "Insira uma chave API válida da xAI para usar Grok na extração de partes.", parent=win
                )
                return
            if (
                extraction_key == "ai"
                and selected_parts_model_name in DEEPSEEK_API_NAMES
                and not plausible_deepseek_api_key(deepseek_api_key)
            ):
                messagebox.showerror(
                    "sig", "Insira uma chave API válida do Deepseek para usar DeepSeek na extração de partes.", parent=win
                )
                return
            selected_qualification_model = qualification_model_labels.get(
                qualification_model_var.get(), IA_PROXY_NAME
            )
            if (
                selected_qualification_model in GROK_TEXT_API_NAMES
                and not plausible_xai_api_key(api_key)
            ):
                messagebox.showerror(
                    "sig", "Insira uma chave API válida da xAI para usar Grok na qualificação.", parent=win
                )
                return
            if (
                selected_qualification_model in DEEPSEEK_API_NAMES
                and not plausible_deepseek_api_key(deepseek_api_key)
            ):
                messagebox.showerror(
                    "sig", "Insira uma chave API válida do Deepseek para usar DeepSeek na qualificação.", parent=win
                )
                return
            self.settings = save_settings(
                {
                    "convert_parallel": conv_var.get(),
                    "transcribe_parallel": req_var.get(),
                    "grok_chunk_ms": grok_chunk_ms,
                    "grok_rest_requests": bool(grok_rest_var.get()),
                    "transcription_server": selected_transcription,
                    "transcription_server_2": selected_transcription_2,
                    "history_model": selected_history,
                    "history_model_2": selected_history_2,
                    "history_reasoning": history_reasoning_var.get(),
                    "history_reasoning_2": history_reasoning_2_var.get(),
                    "history_proxy_model": history_proxy_model_var.get(),
                    "history_proxy_model_2": history_proxy_model_2_var.get(),
                    "statement_model": selected_statement,
                    "statement_model_2": selected_statement_2,
                    "statement_reasoning": statement_reasoning_var.get(),
                    "statement_reasoning_2": statement_reasoning_2_var.get(),
                    "statement_proxy_model": statement_proxy_model_var.get(),
                    "statement_proxy_model_2": statement_proxy_model_2_var.get(),
                    "parts_extraction": extraction_key,
                    "parts_model": selected_parts_model_name,
                    "parts_proxy_model": selected_parts_proxy_model,
                    "parts_proxy_provider": (
                        "deepseek"
                        if selected_parts_proxy_model == DEEPSEEK_TEXT_NAME
                        else "grok"
                    ),
                    "parts_reasoning": parts_reasoning_var.get(),
                    "qualification_model": selected_qualification_model,
                    "qualification_reasoning": qualification_reasoning_var.get(),
                    "qualification_proxy_model": qualification_proxy_model_var.get(),
                    "grok_api_key": api_key,
                    "deepseek_api_key": deepseek_api_key,
                    "deepgram_api_key": deepgram_api_key,
                    "deepgram_keyterms": deepgram_keyterms,
                    "assemblyai_api_key": assemblyai_api_key,
                    "elevenlabs_api_key": elevenlabs_api_key,
                    "imei_api_key": imei_api_key,
                    "police_name": police_name,
                    "police_role": police_role,
                    "police_station": police_station,
                    "police_delegate": police_delegate,
                    "police_city": police_city,
                }
            )
            self._refresh_server_label()
            self._refresh_assistant_model_label()
            self._refresh_live_grok_controls()
            self.multi_model_secondary = selected_transcription_2
            self.multi_text_secondary = selected_history_2
            if self.multi_model_var.get() and not selected_transcription_2:
                self.multi_model_var.set(False)
            self._refresh_multi_model_layout()
            self._refresh_multi_text_visibility()
            win.destroy()

        ttk.Button(buttons, text="Cancelar", command=win.destroy).pack(side=LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Salvar", command=save_and_close).pack(side=LEFT)

        def normalize_settings_surface(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Label):
                    child.configure(style="Settings.TLabel")
                elif isinstance(child, ttk.Checkbutton):
                    child.configure(style="Settings.TCheckbutton")
                elif isinstance(child, ttk.Frame):
                    child.configure(style="Settings.TFrame")
                normalize_settings_surface(child)

        for column_sections in columns:
            for section in column_sections:
                normalize_settings_surface(section)
        win.transient(self.root)
        win.grab_set()
        win.wait_visibility()
        win.focus()
    def open_about(self):
        if self.about_window is not None:
            try:
                if self.about_window.winfo_exists():
                    self.about_window.deiconify()
                    self.about_window.lift()
                    self.about_window.focus_force()
                    return
            except Exception:
                pass
            self.about_window = None
            self.about_image = None

        win = Toplevel(self.root)
        self.about_window = win
        win.title("Sobre")
        win.resizable(False, False)
        win.transient(self.root)
        win.configure(background="#000000")
        canvas = Canvas(win, width=420, height=650, highlightthickness=0, background="#000000")
        canvas.pack(fill=BOTH, expand=True)

        image_path = resource_path("assets/appwin.png")
        try:
            with Image.open(image_path) as source:
                source = source.convert("RGBA")
                image_width = 415
                image_height = round(source.height * image_width / source.width)
                source = source.resize((image_width, image_height), Image.Resampling.LANCZOS)
                self.about_image = ImageTk.PhotoImage(source)
            canvas.create_image(210, 0, anchor="n", image=self.about_image)
        except Exception:
            canvas.create_rectangle(0, 0, 420, 556, fill="#14201f", outline="")

        canvas.create_text(
            210,
            586,
            text="Delegacia de Taguaí",
            fill="#ffffff",
            font=("Segoe UI Semibold", 13),
        )
        canvas.create_text(
            210,
            612,
            text="Setor de Investigações Gerais",
            fill="#e1f0ef",
            font=("Segoe UI", 10),
        )
        canvas.create_text(
            210,
            628,
            text=f"Versão: {APP_VERSION}",
            fill="#9bb3b0",
            font=("Segoe UI", 9),
        )

        def close_about():
            self.about_window = None
            self.about_image = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close_about)
        win.geometry("420x638")
        win.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - win.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - win.winfo_height()) // 2)
        win.geometry(f"420x638+{x}+{y}")
        win.wait_visibility()
        win.lift()
        win.focus_force()

    def open_status(self):
        """Abre uma tela com status de cada servidor Granite (HTTP GET em http://host:8100)."""
        import json as _json
        import http.client as _http
        from urllib.parse import urlparse as _urlparse

        win = Toplevel(self.root)
        win.title("Status dos servidores")
        win.resizable(False, False)
        canvas = Canvas(win, width=1200, height=1200, highlightthickness=0, background="#000000")
        canvas.pack(fill=BOTH, expand=True)

        # Título
        canvas.create_text(
            600, 24,
            text="Status dos servidores",
            fill="#d6a22b",
            font=("Segoe UI Semibold", 15),
        )

        # Busca servidores
        try:
            servers = read_transcription_servers()
        except Exception:
            servers = []
        granite_servers = [s for s in servers if s.get("url", "").startswith("http") and "api.x.ai" not in s.get("url", "")]

        if not granite_servers:
            canvas.create_text(
                600, 280,
                text="Nenhum servidor Granite configurado.",
                fill="#ffffff",
                font=("Segoe UI", 12),
            )
            content_height = 340
        else:
            max_y = 58
            for i, server in enumerate(granite_servers):
                center_x = 300 + (i * 600)
                y = 58
                name = server.get("name", f"Servidor {i+1}")
                url_full = server.get("url", "")

                try:
                    parsed = _urlparse(url_full)
                    status_url = f"http://{parsed.hostname}:8100/health"
                except Exception:
                    status_url = url_full

                # Nome do servidor
                canvas.create_text(
                    center_x, y,
                    text=name,
                    fill="#d6a22b",
                    font=("Segoe UI Semibold", 11),
                )
                y += 20

                # URL
                canvas.create_text(
                    center_x, y,
                    text=status_url,
                    fill="#889493",
                    font=("Consolas", 9),
                )
                y += 18

                # Requisição HTTP
                try:
                    conn = _http.HTTPConnection(parsed.hostname, 8100, timeout=5)
                    conn.request("GET", "/health")
                    resp = conn.getresponse()
                    raw = resp.read().decode("utf-8", errors="replace")
                    conn.close()

                    try:
                        data = _json.loads(raw)
                    except _json.JSONDecodeError:
                        data = raw

                    if isinstance(data, dict):
                        gpu_data = data.get("gpu") if isinstance(data.get("gpu"), dict) else data
                        try:
                            vram_used = float(gpu_data.get("memory_used_mb", 0) or 0)
                            vram_total = float(gpu_data.get("memory_total_mb", 0) or 0)
                        except (TypeError, ValueError):
                            vram_used = vram_total = 0.0

                        # Extrai stats se existir
                        stats = data.pop("stats", None)

                        # Campos normais (linha por linha)
                        for key, value in data.items():
                            canvas.create_text(
                                center_x, y,
                                text=f"{key}: {_json.dumps(value, ensure_ascii=False)}",
                                fill="#2ecc71",
                                font=("Consolas", 9),
                            )
                            y += 16

                        # Stats destacados
                        if isinstance(stats, dict) and stats:
                            y += 4
                            canvas.create_text(
                                center_x, y,
                                text="─ Estatísticas ─",
                                fill="#d6a22b",
                                font=("Segoe UI Semibold", 10),
                            )
                            y += 20
                            for sk, sv in stats.items():
                                canvas.create_text(
                                    center_x, y,
                                    text=f"  {sk}: {sv}",
                                    fill="#ffffff",
                                    font=("Consolas", 10),
                                )
                                y += 17

                        if vram_total > 0:
                            vram_percent = max(0.0, min(100.0, (vram_used / vram_total) * 100.0))
                            bar_width = 420
                            bar_height = 14
                            bar_left = center_x - (bar_width / 2)
                            bar_top = y + 12
                            bar_color = (
                                "#2ecc71" if vram_percent < 70
                                else "#f1c40f" if vram_percent < 90
                                else "#e74c3c"
                            )
                            canvas.create_text(
                                center_x,
                                bar_top,
                                text=(
                                    f"VRAM: {vram_used / 1024:.1f} GB / "
                                    f"{vram_total / 1024:.1f} GB ({vram_percent:.1f}%)"
                                ),
                                fill="#ffffff",
                                font=("Segoe UI", 10),
                                anchor="s",
                            )
                            bar_top += 7
                            canvas.create_rectangle(
                                bar_left,
                                bar_top,
                                bar_left + bar_width,
                                bar_top + bar_height,
                                fill="#202827",
                                outline="#52605e",
                                width=1,
                            )
                            fill_width = bar_width * (vram_percent / 100.0)
                            if fill_width > 0:
                                canvas.create_rectangle(
                                    bar_left,
                                    bar_top,
                                    bar_left + fill_width,
                                    bar_top + bar_height,
                                    fill=bar_color,
                                    outline=bar_color,
                                    width=0,
                                )
                            y = int(bar_top + bar_height + 14)
                    else:
                        for line in str(data).split("\n")[:15]:
                            canvas.create_text(
                                center_x, y,
                                text=line[:80],
                                fill="#2ecc71",
                                font=("Consolas", 9),
                            )
                            y += 16
                except Exception as exc:
                    canvas.create_text(
                        center_x, y,
                        text=f"Erro: {exc}",
                        fill="#e74c3c",
                        font=("Consolas", 9),
                    )
                    y += 16

                y += 12
                max_y = max(max_y, y)

            content_height = max_y + 24

        height = min(max(content_height, 200), 1200)
        canvas.configure(height=height)
        status_width = 1200 if len(granite_servers) >= 2 else 600
        canvas.configure(width=status_width)
        win.geometry(f"{status_width}x{height}")

        win.transient(self.root)
        win.wait_visibility()
        win.focus()

    def toggle_run(self):
        if self.running:
            self.cancel_current_run()
        else:
            self.start_run()

    def toggle_live_mic(self):
        if self.normal_recording:
            if self.normal_record_paused:
                self.resume_normal_live_recording()
            else:
                self.pause_normal_live_recording()
            return
        if self.live_state == "idle":
            self.start_live_mic()
        elif self.live_state == "listening":
            self.pause_live_mic()
        elif self.live_state == "paused":
            self.resume_live_mic()
        elif self.live_state == "finalizing":
            self.status_var.set("Aguarde a transcrição definitiva terminar.")

    def start_live_mic(self):
        if self.normal_recording:
            messagebox.showinfo("sig", "Finalize a gravação do microfone branco antes de iniciar o streaming.")
            return
        if self.running:
            messagebox.showinfo("sig", "Pare a transcrição de arquivos antes de usar o microfone ao vivo.")
            return
        if getattr(self, "ffmpeg_tools", None) and self.ffmpeg_tools.running:
            messagebox.showinfo("sig", "Aguarde o processamento FFmpeg terminar antes de usar o microfone ao vivo.")
            return
        if self.assistant_busy:
            messagebox.showinfo("sig", "Aguarde a geração de histórico ou oitiva terminar.")
            return
        if self.live_state != "idle":
            return
        try:
            import sounddevice  # noqa: F401
        except Exception as exc:
            messagebox.showerror(
                "sig",
                "Não consegui carregar a captura de microfone.\n"
                "Reinstale o app com a dependência sounddevice embutida.\n\n"
                f"Detalhe: {exc}",
            )
            return
        self.settings = load_settings()
        self.multi_model_secondary = str(self.settings.get("transcription_server_2") or "")
        self._refresh_multi_model_layout()
        self._refresh_live_grok_controls()
        secondary_settings = (
            settings_for_transcription_server(self.settings, self.multi_model_secondary)
            if self.multi_model_var.get() and self.multi_model_secondary
            else None
        )
        if (
            is_grok_transcription(self.settings)
            or (secondary_settings is not None and is_grok_transcription(secondary_settings))
        ) and not self.settings.get("grok_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Grok nas configurações antes de iniciar.")
            return
        if (
            is_deepgram_transcription(self.settings)
            or (secondary_settings is not None and is_deepgram_transcription(secondary_settings))
        ) and not self.settings.get("deepgram_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Deepgram nas configurações antes de iniciar.")
            return
        if (
            is_assemblyai_transcription(self.settings)
            or (secondary_settings is not None and is_assemblyai_transcription(secondary_settings))
        ) and not self.settings.get("assemblyai_api_key"):
            messagebox.showerror("sig", "Insira a chave API da AssemblyAI nas configurações antes de iniciar.")
            return
        if (
            is_elevenlabs_transcription(self.settings)
            or (secondary_settings is not None and is_elevenlabs_transcription(secondary_settings))
        ) and not self.settings.get("elevenlabs_api_key"):
            messagebox.showerror("sig", "Insira a chave API da ElevenLabs nas configurações antes de iniciar.")
            return
        self.live_stop_event.clear()
        self.live_abort_event.clear()
        self.live_uses_grok_websocket = is_grok_transcription(self.settings) and not self.settings.get(
            "grok_rest_requests", False
        )
        self.live_uses_deepgram_websocket = is_deepgram_transcription(self.settings) and not self.settings.get(
            "grok_rest_requests", False
        )
        self.live_uses_assemblyai_websocket = is_assemblyai_transcription(self.settings) and not self.settings.get(
            "grok_rest_requests", False
        )
        self.live_uses_elevenlabs_websocket = is_elevenlabs_transcription(self.settings) and not self.settings.get(
            "grok_rest_requests", False
        )
        self.live_grok_settings = self.settings.copy() if self.live_uses_grok_websocket else None
        self.live_grok_language = grok_language_param(self.settings) or ""
        self.live_grok_diarize = bool(self.live_diarize_var.get())
        self.grok_ws_ready_event.clear()
        self.grok_ws_done_event.clear()
        self.grok_ws_lost_event.clear()
        self.grok_ws_intentional_close = False
        self.grok_ws_app = None
        self.deepgram_ws_ready_event.clear()
        self.deepgram_ws_done_event.clear()
        self.deepgram_ws_lost_event.clear()
        self.deepgram_ws_intentional_close = False
        self.deepgram_ws_app = None
        self.assemblyai_ws_ready_event.clear()
        self.assemblyai_ws_done_event.clear()
        self.assemblyai_ws_lost_event.clear()
        self.assemblyai_ws_intentional_close = False
        self.assemblyai_ws_app = None
        self.elevenlabs_ws_ready_event.clear()
        self.elevenlabs_ws_done_event.clear()
        self.elevenlabs_ws_lost_event.clear()
        self.elevenlabs_ws_intentional_close = False
        self.elevenlabs_ws_app = None
        streaming_websocket = (
            self.live_uses_grok_websocket
            or self.live_uses_deepgram_websocket
            or self.live_uses_assemblyai_websocket
            or self.live_uses_elevenlabs_websocket
        )
        self.live_uploader = None if streaming_websocket else create_transcription_uploader(self.live_abort_event, self.settings)
        temp_live = app_base_dir() / "temp" / "live"
        temp_live.mkdir(parents=True, exist_ok=True)
        self._clear_live_integral_audio()
        self.live_full_pcm_path = temp_live / f"live_full_{int(time.time() * 1000)}.pcm"
        self.live_was_grok_websocket = streaming_websocket
        self.live_recovery_cancel_event.clear()
        self.live_capture_finish_waiting = False
        self.live_output_finished = False
        with self.live_lock:
            self.live_committed_text = ""
            self.live_draft_text = ""
            self.live_draft_generation = 0
        self.last_live_transcript_text = ""
        self.live_plain_transcript_text = ""
        self.live_timestamped_transcript_text = ""
        self.live_timestamps_var.set(False)
        self.live_timestamps_check.configure(state="disabled")
        self.live_secondary_active = secondary_settings is not None
        if self.live_secondary_active:
            self.live_secondary_done_event.clear()
        else:
            self.live_secondary_done_event.set()
        self.live_secondary_audio_queue = queue.Queue() if self.live_secondary_active else None
        with self.live_secondary_lock:
            self.live_secondary_committed_text = ""
            self.live_secondary_draft_text = ""
            self.live_secondary_generation = 0
        self.last_live_transcript_text_2 = ""
        self.live_finish_waiting = False
        self._reset_live_waveform()
        self.live_started_at = time.time()
        self.live_paused_at = 0.0
        self.live_paused_total = 0.0
        self._set_live_text("")
        self._set_live_editor("transcript2", "")
        self.live_upload_executor = (
            None
            if (
                self.live_uses_grok_websocket
                or self.live_uses_deepgram_websocket
                or self.live_uses_assemblyai_websocket
                or self.live_uses_elevenlabs_websocket
            )
            else concurrent.futures.ThreadPoolExecutor(max_workers=1)
        )
        self._set_live_state("listening")
        if secondary_settings is not None:
            self.live_secondary_thread = threading.Thread(
                target=self._secondary_live_worker,
                args=(secondary_settings,),
                daemon=True,
            )
            self.live_secondary_thread.start()
        if (
            not self.live_uses_grok_websocket
            and not self.live_uses_deepgram_websocket
            and not self.live_uses_assemblyai_websocket
            and not self.live_uses_elevenlabs_websocket
        ):
            self.status_var.set("Ouvindo e transcrevendo ao vivo...")
        if self.live_uses_elevenlabs_websocket:
            target = self._elevenlabs_live_capture_loop
        elif self.live_uses_assemblyai_websocket:
            target = self._assemblyai_live_capture_loop
        elif self.live_uses_deepgram_websocket:
            target = self._deepgram_live_capture_loop
        elif self.live_uses_grok_websocket:
            target = self._grok_live_capture_loop
        else:
            target = self._live_capture_loop
        self.live_thread = threading.Thread(target=target, args=(self.settings.copy(),), daemon=True)
        self.live_thread.start()
        self._tick_live_timer()

    def pause_live_mic(self):
        if self.live_state != "listening":
            return
        self.live_paused_at = time.time()
        self._set_live_state("paused")
        self.status_var.set("Transcrição ao vivo pausada.")

    def resume_live_mic(self):
        if self.live_state != "paused":
            return
        if self.live_paused_at:
            self.live_paused_total += time.time() - self.live_paused_at
        self.live_paused_at = 0.0
        self._set_live_state("listening")
        self.status_var.set("Ouvindo e transcrevendo ao vivo...")

    def pause_normal_live_recording(self):
        if not self.normal_recording or self.normal_record_paused:
            return
        self.normal_record_paused = True
        self._draw_live_pause_button()
        self._draw_live_waveform()
        self.status_var.set("Gravação do microfone pausada.")

    def resume_normal_live_recording(self):
        if not self.normal_recording or not self.normal_record_paused:
            return
        self.normal_record_paused = False
        self._draw_live_pause_button()
        self.status_var.set("Gravando pelo microfone branco...")

    def stop_live_mic(self):
        if self.live_state not in ("listening", "paused"):
            return
        if self.live_state == "paused" and self.live_paused_at:
            self.live_paused_total += time.time() - self.live_paused_at
            self.live_paused_at = 0.0
        self._set_live_state("finalizing")
        if self.live_uses_elevenlabs_websocket:
            self.elevenlabs_ws_intentional_close = True
            self.status_var.set("Recebendo a transcrição final do Scribe...")
            self.live_stop_event.set()
            app = self.elevenlabs_ws_app
            if not app:
                self._queue("status", "Streaming finalizado; não havia conexão ativa para confirmar o áudio final.")
                self._finish_live_output()
                return
            try:
                # Força a finalização com um chunk de silêncio commitado (a VAD
                # fecharia sozinha, mas o commit garante o último segmento).
                silence = base64.b64encode(bytes(3200)).decode("ascii")
                app.send(json.dumps({
                    "message_type": "input_audio_chunk",
                    "audio_base_64": silence,
                    "commit": True,
                    "sample_rate": LIVE_SAMPLE_RATE,
                }))
                threading.Thread(target=self._wait_for_elevenlabs_final_event, daemon=True).start()
            except Exception:
                self._queue("status", "Streaming finalizado; não foi possível confirmar o áudio final no servidor.")
                self._finish_live_output()
            return
        if self.live_uses_assemblyai_websocket:
            self.assemblyai_ws_intentional_close = True
            self.status_var.set("Recebendo a transcrição final da AssemblyAI...")
            self.live_stop_event.set()
            app = self.assemblyai_ws_app
            if not app:
                self._queue("status", "Streaming finalizado; não havia conexão ativa para confirmar o áudio final.")
                self._finish_live_output()
                return
            try:
                app.send(json.dumps({"type": "Terminate"}))
                threading.Thread(target=self._wait_for_assemblyai_final_event, daemon=True).start()
            except Exception:
                self._queue("status", "Streaming finalizado; não foi possível confirmar o áudio final no servidor.")
                self._finish_live_output()
            return
        if self.live_uses_deepgram_websocket:
            self.deepgram_ws_intentional_close = True
            self.status_var.set("Recebendo a transcrição final do Deepgram...")
            self.live_stop_event.set()
            app = self.deepgram_ws_app
            if not app:
                self._queue("status", "Streaming finalizado; não havia conexão ativa para confirmar o áudio final.")
                self._finish_live_output()
                return
            try:
                app.send(json.dumps({"type": "CloseStream"}))
                threading.Thread(target=self._wait_for_deepgram_final_event, daemon=True).start()
            except Exception:
                self._queue("status", "Streaming finalizado; não foi possível confirmar o áudio final no servidor.")
                self._finish_live_output()
            return
        if self.live_uses_grok_websocket:
            self.grok_ws_intentional_close = True
            self.status_var.set("Recebendo a transcrição final do Grok...")
            self.live_stop_event.set()
            app = self.grok_ws_app
            if not app:
                self._queue("status", "Streaming finalizado; não havia conexão ativa para confirmar o áudio final.")
                self._finish_live_output()
                return
            try:
                # websocket-client returns the number of bytes sent, which may be 0/None
                # depending on the transport. An exception, not that return value, means failure.
                app.send(json.dumps({"type": "audio.done"}))
                threading.Thread(target=self._wait_for_grok_final_event, daemon=True).start()
            except Exception:
                # The user deliberately stopped the stream. Keep the partial text and finish
                # cleanly instead of routing this through the cancellation/error path.
                self._queue("status", "Streaming finalizado; não foi possível confirmar o áudio final no servidor.")
                self._finish_live_output()
            return
        self.status_var.set("Enviando áudio integral para a transcrição definitiva...")
        self.live_stop_event.set()
        with self.live_lock:
            self.live_draft_generation += 1
        if self.live_uploader:
            self.live_uploader.cancel()
        executor = self.live_upload_executor
        self.live_upload_executor = None
        if executor:
            executor.shutdown(wait=False, cancel_futures=True)
        self.live_finalize_thread = threading.Thread(target=self._finish_live_transcription, daemon=True)
        self.live_finalize_thread.start()

    def _wait_for_elevenlabs_final_event(self):
        if self.elevenlabs_ws_done_event.wait(20):
            return
        if self.live_state == "finalizing" and not self.live_abort_event.is_set():
            self.elevenlabs_ws_intentional_close = True
            app = self.elevenlabs_ws_app
            if app:
                try:
                    app.close()
                except Exception:
                    pass
            self._queue(
                "status",
                "O Scribe não enviou uma confirmação final; mantive a transcrição recebida durante o streaming.",
            )
            self._finish_live_output()

    def _wait_for_assemblyai_final_event(self):
        if self.assemblyai_ws_done_event.wait(20):
            return
        if self.live_state == "finalizing" and not self.live_abort_event.is_set():
            self.assemblyai_ws_intentional_close = True
            app = self.assemblyai_ws_app
            if app:
                try:
                    app.close()
                except Exception:
                    pass
            self._queue(
                "status",
                "A AssemblyAI não enviou uma confirmação final; mantive a transcrição recebida durante o streaming.",
            )
            self._finish_live_output()

    def _wait_for_deepgram_final_event(self):
        if self.deepgram_ws_done_event.wait(20):
            return
        if self.live_state == "finalizing" and not self.live_abort_event.is_set():
            self.deepgram_ws_intentional_close = True
            app = self.deepgram_ws_app
            if app:
                try:
                    app.close()
                except Exception:
                    pass
            self._queue(
                "status",
                "O Deepgram não enviou uma confirmação final; mantive a transcrição recebida durante o streaming.",
            )
            self._finish_live_output()

    def _wait_for_grok_final_event(self):
        if self.grok_ws_done_event.wait(20):
            return
        if self.live_state == "finalizing" and not self.live_abort_event.is_set():
            self.grok_ws_intentional_close = True
            app = self.grok_ws_app
            if app:
                try:
                    app.close()
                except Exception:
                    pass
            self._queue(
                "status",
                "O Grok não enviou uma confirmação final; mantive a transcrição recebida durante o streaming.",
            )
            self._finish_live_output()

    def cancel_live_mic(self):
        if self.live_state == "idle":
            return
        self.live_stop_event.set()
        self.live_abort_event.set()
        self.live_recovery_cancel_event.set()
        self.live_audio_recovery_available = False
        self.live_output_finished = True
        self._set_live_audio_recovery_visible(False)
        self.grok_ws_intentional_close = True
        self.deepgram_ws_intentional_close = True
        self.assemblyai_ws_intentional_close = True
        self.elevenlabs_ws_intentional_close = True
        if self.live_uploader:
            self.live_uploader.cancel()
        if self.grok_ws_app:
            try:
                self.grok_ws_app.close(status=1000, reason="Cancelado")
            except Exception:
                pass
        self.grok_ws_app = None
        if self.deepgram_ws_app:
            try:
                self.deepgram_ws_app.close(status=1000, reason="Cancelado")
            except Exception:
                pass
        self.deepgram_ws_app = None
        if self.assemblyai_ws_app:
            try:
                self.assemblyai_ws_app.close(status=1000, reason="Cancelado")
            except Exception:
                pass
        self.assemblyai_ws_app = None
        if self.elevenlabs_ws_app:
            try:
                self.elevenlabs_ws_app.close(status=1000, reason="Cancelado")
            except Exception:
                pass
        self.elevenlabs_ws_app = None
        self.live_uses_grok_websocket = False
        self.live_uses_deepgram_websocket = False
        self.live_uses_assemblyai_websocket = False
        self.live_uses_elevenlabs_websocket = False
        executor = self.live_upload_executor
        self.live_upload_executor = None
        if executor:
            executor.shutdown(wait=False, cancel_futures=True)
        self._set_live_state("idle")
        self.status_var.set("Transcrição ao vivo cancelada.")

    def _tick_live_timer(self):
        if self.live_state == "idle":
            self.live_timer_var.set("00:00.000")
            return
        paused_now = 0.0
        if self.live_state == "paused" and self.live_paused_at:
            paused_now = time.time() - self.live_paused_at
        elapsed = max(0.0, time.time() - self.live_started_at - self.live_paused_total - paused_now)
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        millis = int((elapsed - int(elapsed)) * 1000)
        self.live_timer_var.set(f"{minutes:02d}:{seconds:02d}.{millis:03d}")
        self.root.after(200, self._tick_live_timer)

    def _queue_secondary_audio(self, chunk: bytes):
        audio_queue = self.live_secondary_audio_queue
        if not self.live_secondary_active or audio_queue is None or self.live_state == "paused":
            return
        audio_queue.put(chunk)

    def _secondary_live_worker(self, settings: dict):
        try:
            if is_grok_transcription(settings) and not settings.get("grok_rest_requests", False):
                self._secondary_grok_live_worker(settings)
            else:
                self._secondary_http_live_worker(settings)
        except Exception as exc:
            if not self.live_abort_event.is_set():
                self._queue("status", f"Modelo de transcrição 2 falhou: {exc}")
        finally:
            self.live_secondary_done_event.set()

    def _secondary_grok_live_worker(self, settings: dict):
        try:
            import websocket
        except Exception as exc:
            raise RuntimeError(f"streaming do Grok indisponível: {exc}") from exc
        api_key = str(settings.get("grok_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("chave API do Grok não configurada")
        ready = threading.Event()
        done = threading.Event()
        failed = threading.Event()
        final_text = {"value": ""}

        def on_message(_app, raw_event):
            try:
                event = json.loads(raw_event)
            except Exception:
                failed.set()
                return
            event_type = str(event.get("type") or "")
            if event_type == "transcript.created":
                ready.set()
            elif event_type == "transcript.partial":
                text = self._format_grok_diarized_transcript(event, str(event.get("text") or "").strip())
                if text:
                    self._update_secondary_transcript(text, bool(event.get("is_final")))
            elif event_type == "transcript.done":
                text = self._format_grok_diarized_transcript(event, str(event.get("text") or "").strip())
                final_text["value"] = text
                done.set()
            elif event_type == "error":
                failed.set()

        def on_error(_app, _error):
            failed.set()

        def on_close(_app, _status_code, _message):
            if not done.is_set() and not self.live_stop_event.is_set():
                failed.set()

        language = grok_language_param(self.settings)
        query = "sample_rate=16000&encoding=pcm&interim_results=true"
        if language:
            query += f"&language={language}"
        query += "&format=true&smart_turn=0.65&endpointing=900&filler_words=false"
        if grok_diarize_query(bool(self.live_diarize_var.get())):
            query += "&diarize=true"
        app = websocket.WebSocketApp(
            f"{GROK_STT_WEBSOCKET_URL}?{query}",
            header=[f"Authorization: Bearer {api_key}"],
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        ws_thread = threading.Thread(
            target=lambda: app.run_forever(ping_interval=30, ping_timeout=10), daemon=True
        )
        ws_thread.start()
        deadline = time.monotonic() + 15
        while not ready.wait(0.1):
            if failed.is_set() or self.live_abort_event.is_set() or time.monotonic() >= deadline:
                app.close()
                raise RuntimeError("não foi possível conectar ao streaming do Grok")

        audio_queue = self.live_secondary_audio_queue
        while not self.live_abort_event.is_set():
            if self.live_stop_event.is_set() and (audio_queue is None or audio_queue.empty()):
                break
            try:
                chunk = audio_queue.get(timeout=0.2) if audio_queue is not None else b""
            except queue.Empty:
                continue
            if chunk:
                app.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
        if not self.live_abort_event.is_set():
            app.send(json.dumps({"type": "audio.done"}))
            done.wait(20)
            if final_text["value"]:
                self._set_secondary_definitive(final_text["value"])
        app.close()

    def _secondary_http_live_worker(self, settings: dict):
        audio_queue = self.live_secondary_audio_queue
        if audio_queue is None:
            return
        all_pcm = bytearray()
        window_pcm = bytearray()
        final_chunk_bytes = pcm_bytes_for_millis(LIVE_FINAL_CHUNK_MILLIS)
        window_index = 1
        last_sent_draft_ms = 0
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            while not self.live_abort_event.is_set():
                if self.live_stop_event.is_set() and audio_queue.empty():
                    break
                try:
                    chunk = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if not chunk:
                    continue
                all_pcm.extend(chunk)
                window_pcm.extend(chunk)
                while len(window_pcm) >= final_chunk_bytes:
                    final_pcm = bytes(window_pcm[:final_chunk_bytes])
                    del window_pcm[:final_chunk_bytes]
                    with self.live_secondary_lock:
                        generation = self.live_secondary_generation
                    executor.submit(
                        self._send_secondary_http_snapshot,
                        settings,
                        final_pcm,
                        True,
                        generation,
                        window_index,
                    )
                    window_index += 1
                    last_sent_draft_ms = 0
                draft_interval = max(
                    MIN_LIVE_DRAFT_INTERVAL_MILLIS,
                    min(MAX_LIVE_DRAFT_INTERVAL_MILLIS, self.live_interval_ms),
                )
                current_ms = len(window_pcm) * 1000 // (LIVE_SAMPLE_RATE * LIVE_SAMPLE_WIDTH)
                current_draft_ms = (current_ms // draft_interval) * draft_interval
                if current_draft_ms > last_sent_draft_ms:
                    last_sent_draft_ms = current_draft_ms
                    with self.live_secondary_lock:
                        self.live_secondary_generation += 1
                        generation = self.live_secondary_generation
                    executor.submit(
                        self._send_secondary_http_snapshot,
                        settings,
                        bytes(window_pcm),
                        False,
                        generation,
                        window_index,
                    )
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
        if not self.live_abort_event.is_set() and len(all_pcm) >= 1024:
            self._transcribe_secondary_definitive(settings, bytes(all_pcm))

    def _send_secondary_http_snapshot(
        self, settings: dict, pcm: bytes, is_final: bool, generation: int, window_index: int
    ):
        if len(pcm) < 1024 or self.live_abort_event.is_set():
            return
        with self.live_secondary_lock:
            if not is_final and generation != self.live_secondary_generation:
                return
        temp_live = app_base_dir() / "temp" / "live"
        raw_dir = temp_live / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        wav_path = temp_live / f"live_secondary_{stamp}_{window_index}.wav"
        raw_path = raw_dir / f"{wav_path.stem}.json"
        try:
            write_wav_from_pcm_bytes(wav_path, pcm)
            uploader = create_transcription_uploader(self.live_abort_event, settings)
            status, transcript = uploader.post_file(transcribe_url(settings), wav_path, "audio/wav", raw_path)
            if status != 200:
                raise RuntimeError(f"HTTP {status}")
            self._update_secondary_transcript(transcript, is_final, generation)
        except Cancelled:
            pass
        except Exception as exc:
            if self.live_state in ("listening", "paused"):
                self._queue("status", f"Falha no modelo de transcrição 2: {exc}")
        finally:
            wav_path.unlink(missing_ok=True)

    def _transcribe_secondary_definitive(self, settings: dict, pcm: bytes):
        temp_live = app_base_dir() / "temp" / "live"
        raw_dir = temp_live / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        wav_path = temp_live / f"live_secondary_definitive_{int(time.time() * 1000)}.wav"
        raw_path = raw_dir / f"{wav_path.stem}.json"
        try:
            write_wav_from_pcm_bytes(wav_path, pcm)
            uploader = create_transcription_uploader(self.live_abort_event, settings)
            status, transcript = uploader.post_file(transcribe_url(settings), wav_path, "audio/wav", raw_path)
            if status != 200 or not transcript.strip():
                raise RuntimeError(f"HTTP {status}" if status != 200 else "resposta vazia")
            self._set_secondary_definitive(transcript)
        except Cancelled:
            pass
        except Exception as exc:
            self._queue("status", f"Não consegui finalizar a transcrição do modelo 2: {exc}")
        finally:
            wav_path.unlink(missing_ok=True)

    def _update_secondary_transcript(self, text: str, is_final: bool, generation: int | None = None):
        clean = (text or "").strip()
        if not clean:
            return
        with self.live_secondary_lock:
            if generation is not None and not is_final and generation != self.live_secondary_generation:
                return
            if is_final:
                if self.live_secondary_committed_text and not self.live_secondary_committed_text.endswith("\n"):
                    self.live_secondary_committed_text += "\n"
                if not self.live_secondary_committed_text.endswith(clean + "\n"):
                    self.live_secondary_committed_text += clean + "\n"
                self.live_secondary_draft_text = ""
            else:
                self.live_secondary_draft_text = clean
            committed = self.live_secondary_committed_text.strip()
            draft = self.live_secondary_draft_text.strip()
            display = f"{committed}\n{draft}" if committed and draft else committed or draft
        self._queue("live_display_2", display)

    def _set_secondary_definitive(self, text: str):
        clean = (text or "").strip()
        with self.live_secondary_lock:
            self.live_secondary_committed_text = clean
            self.live_secondary_draft_text = ""
        self._queue("live_display_2", clean)

    def _elevenlabs_live_capture_loop(self, settings: dict):
        try:
            import sounddevice as sd
            import websocket
        except Exception as exc:
            self._queue("live_error", f"Streaming do Scribe indisponível: {exc}")
            return

        api_key = str(settings.get("elevenlabs_api_key") or "").strip()
        if not api_key:
            self._queue("live_error", "Insira a chave API da ElevenLabs nas configurações.")
            return

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        buffered_pcm: deque[bytes] = deque()
        buffered_bytes = 0
        buffer_limit = pcm_bytes_for_millis(GROK_RECONNECT_BUFFER_MILLIS)
        buffer_lock = threading.Lock()
        full_pcm_lock = threading.Lock()
        full_pcm = None

        def remember(chunk: bytes) -> None:
            nonlocal buffered_bytes
            with buffer_lock:
                buffered_pcm.append(chunk)
                buffered_bytes += len(chunk)
                while buffered_pcm and buffered_bytes > buffer_limit:
                    buffered_bytes -= len(buffered_pcm.popleft())

        def buffered_snapshot() -> list[bytes]:
            with buffer_lock:
                return list(buffered_pcm)

        def send_chunk(app, chunk: bytes, commit: bool) -> bool:
            payload = json.dumps({
                "message_type": "input_audio_chunk",
                "audio_base_64": base64.b64encode(chunk).decode("ascii"),
                "commit": commit,
                "sample_rate": LIVE_SAMPLE_RATE,
            })
            return bool(app.send(payload))

        def on_open(_app):
            if _app is self.elevenlabs_ws_app:
                self.elevenlabs_ws_ready_event.set()
                self._queue("status", "Conectado ao Scribe. Ouvindo e transcrevendo ao vivo...")

        def on_message(_app, raw_event):
            if _app is not self.elevenlabs_ws_app:
                return
            try:
                event = json.loads(raw_event)
            except Exception:
                self.elevenlabs_ws_lost_event.set()
                self._queue("status", "Reconectando: resposta inválida do Scribe.")
                return
            event_type = str(event.get("message_type") or "")
            if event_type == "session_started":
                self.elevenlabs_ws_ready_event.set()
                return
            if event_type == "partial_transcript":
                text = str(event.get("text") or "").strip()
                if text and not self.elevenlabs_ws_done_event.is_set():
                    with self.live_lock:
                        self.live_draft_text = text
                        display = self._current_live_text_locked()
                    self._queue("live_display", display)
                return
            if event_type == "final_transcript":
                text = str(event.get("text") or "").strip()
                if text and not self.elevenlabs_ws_done_event.is_set():
                    with self.live_lock:
                        committed = self.live_committed_text.strip()
                        if not committed:
                            self.live_committed_text = text
                        elif text not in committed:
                            self.live_committed_text = f"{committed}\n{text}"
                        self.live_draft_text = ""
                        display = self._current_live_text_locked()
                    self._queue("live_display", display)
                return
            if event_type == "committed_transcript_with_timestamps":
                words = event.get("words") or []
                normalized = []
                for word in words:
                    if isinstance(word, dict) and word.get("type") == "word":
                        normalized.append(
                            {"word": word.get("text"), "start": word.get("start"), "end": word.get("end")}
                        )
                timestamped = _timestamped_text_from_json({"words": normalized}).strip()
                if timestamped:
                    self._queue("live_timestamp_data", timestamped)
                return
            if event_type == "committed_transcript":
                if self.elevenlabs_ws_intentional_close and not self.elevenlabs_ws_done_event.is_set():
                    self._finish_elevenlabs_session()
                return
            if event_type.startswith("scribe_") and "error" in event_type:
                self.elevenlabs_ws_lost_event.set()
                self._queue(
                    "status",
                    f"Reconectando: {str(event.get('message') or event_type)}",
                )

        def _finish_elevenlabs_session():
            with self.live_lock:
                text = self.live_committed_text.strip() or self._current_live_text_locked().strip()
                self.live_committed_text = text
                self.live_draft_text = ""
            timestamped = (self.live_timestamped_transcript_text or "").strip()
            self.elevenlabs_ws_done_event.set()
            self.elevenlabs_ws_app = None
            self.live_uses_elevenlabs_websocket = False
            if not text:
                self._queue("status", "Transcrição ao vivo finalizada sem conteúdo.")
            self._queue("live_display", text)
            if timestamped:
                self._queue("live_payload", text, timestamped, True)
            self._queue("status", "Transcrição definitiva concluída.")
            self._finish_live_output()

        def on_error(_app, _error):
            if (
                _app is self.elevenlabs_ws_app
                and not self.elevenlabs_ws_intentional_close
                and not self.live_abort_event.is_set()
                and not self.elevenlabs_ws_done_event.is_set()
            ):
                self._queue("status", "Desconectado do Scribe; reconectando...")
                self.elevenlabs_ws_lost_event.set()

        def on_close(_app, _status_code, _message):
            if _app is not self.elevenlabs_ws_app:
                return
            if self.elevenlabs_ws_intentional_close and not self.elevenlabs_ws_done_event.is_set():
                self._finish_elevenlabs_session()
                return
            if (
                not self.elevenlabs_ws_intentional_close
                and not self.live_abort_event.is_set()
                and not self.elevenlabs_ws_done_event.is_set()
            ):
                self._queue("status", "Desconectado do Scribe; reconectando...")
                self.elevenlabs_ws_lost_event.set()

        def connect() -> bool:
            previous = self.elevenlabs_ws_app
            self.elevenlabs_ws_app = None
            if previous:
                try:
                    previous.close()
                except Exception:
                    pass
            self.elevenlabs_ws_ready_event.clear()
            self.elevenlabs_ws_lost_event.clear()
            primary, secondary = elevenlabs_ws_language(self.settings)
            query = "model_id=scribe_v2_realtime&audio_format=pcm_16000"
            if primary:
                query += f"&language_code={primary}"
            for code in secondary:
                query += f"&secondary_languages={code}"
            query += "&commit_strategy=vad"
            query += "&vad_silence_threshold_secs=1.0&include_timestamps=true"
            self._queue("status", f"Parâmetros Scribe: {query}")
            app = websocket.WebSocketApp(
                f"{ELEVENLABS_WEBSOCKET_URL}?{query}",
                header=[f"xi-api-key: {api_key}"],
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            self.elevenlabs_ws_app = app
            self.elevenlabs_ws_thread = threading.Thread(
                target=lambda: app.run_forever(ping_interval=30, ping_timeout=10),
                daemon=True,
            )
            self.elevenlabs_ws_thread.start()
            deadline = time.monotonic() + 15
            while not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                if self.elevenlabs_ws_ready_event.wait(0.1):
                    return True
                if self.elevenlabs_ws_lost_event.is_set() or time.monotonic() >= deadline:
                    return False
            return False

        def reconnect(attempt: int) -> bool:
            delay = min(8.0, 0.5 * (2 ** max(0, attempt - 1))) + random.uniform(0.0, 0.25)
            self._queue("status", f"Reconectando ao Scribe ({attempt}/{GROK_RECONNECT_MAX_ATTEMPTS}) em {delay:.1f}s...")
            if self.live_abort_event.wait(delay) or self.live_stop_event.is_set():
                return False
            if not connect():
                return False
            chunks = buffered_snapshot()
            try:
                for chunk in chunks:
                    if not send_chunk(self.elevenlabs_ws_app, chunk, commit=False):
                        raise RuntimeError("envio falhou")
                self._queue("status", f"Reconectou com sucesso; reenviados {len(chunks)} bloco(s) dos últimos 8 segundos.")
            except Exception:
                self._queue("status", "Reconectou, mas não foi possível reenviar parte do buffer de áudio.")
            return True

        def audio_callback(indata, _frames, _time_info, _status):
            if self.live_stop_event.is_set() or self.live_abort_event.is_set() or self.live_state == "paused":
                return
            chunk = bytes(indata)
            self._push_live_waveform_chunk(chunk)
            self._queue_secondary_audio(chunk)
            with full_pcm_lock:
                if full_pcm is not None:
                    full_pcm.write(chunk)
            remember(chunk)
            try:
                audio_queue.put_nowait(chunk)
            except queue.Full:
                try:
                    audio_queue.get_nowait()
                    audio_queue.put_nowait(chunk)
                    self._queue("status", "Parte do áudio ao vivo foi descartada por atraso local.")
                except queue.Empty:
                    pass

        try:
            pcm_path = self.live_full_pcm_path
            if not pcm_path:
                raise RuntimeError("não foi possível criar o áudio integral do streaming")
            pcm_path.parent.mkdir(parents=True, exist_ok=True)
            full_pcm = pcm_path.open("wb")
            with sd.RawInputStream(
                samplerate=LIVE_SAMPLE_RATE,
                channels=LIVE_CHANNELS,
                dtype="int16",
                blocksize=max(
                    1,
                    LIVE_SAMPLE_RATE * int(settings.get("grok_chunk_ms", 100)) // 1000,
                ),
                callback=audio_callback,
            ):
                attempts = 0
                connected = False
                while not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                    if not connected or self.elevenlabs_ws_lost_event.is_set():
                        reconnecting = connected or self.elevenlabs_ws_lost_event.is_set() or attempts > 0
                        attempts += 1
                        self._queue("status", "Reconectando ao streaming do Scribe..." if reconnecting else "Conectando ao streaming do Scribe...")
                        connected = reconnect(attempts) if reconnecting else connect()
                        if connected:
                            attempts = 0
                            continue
                        if attempts >= GROK_RECONNECT_MAX_ATTEMPTS:
                            self._queue("live_error", "Falhou: reconexão do Scribe esgotada após 8 tentativas.")
                            return
                        continue
                    try:
                        chunk = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if self.live_state == "paused" or not chunk:
                        continue
                    try:
                        if not send_chunk(self.elevenlabs_ws_app, chunk, commit=False):
                            raise RuntimeError("envio falhou")
                    except Exception:
                        self.elevenlabs_ws_lost_event.set()
                        connected = False
        except Exception as exc:
            if not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                self._queue("live_error", f"Falhou: erro no microfone ao vivo: {exc}")
        finally:
            with full_pcm_lock:
                if full_pcm is not None:
                    full_pcm.close()
                    full_pcm = None

    def _assemblyai_live_capture_loop(self, settings: dict):
        try:
            import sounddevice as sd
            import websocket
        except Exception as exc:
            self._queue("live_error", f"Streaming da AssemblyAI indisponível: {exc}")
            return

        api_key = str(settings.get("assemblyai_api_key") or "").strip()
        if not api_key:
            self._queue("live_error", "Insira a chave API da AssemblyAI nas configurações.")
            return

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        buffered_pcm: deque[bytes] = deque()
        buffered_bytes = 0
        buffer_limit = pcm_bytes_for_millis(GROK_RECONNECT_BUFFER_MILLIS)
        buffer_lock = threading.Lock()
        full_pcm_lock = threading.Lock()
        full_pcm = None
        speaker_labels: dict[str, int] = {}

        def speaker_prefix(label) -> str:
            if not label:
                return ""
            label = str(label)
            number = speaker_labels.get(label)
            if number is None:
                number = len(speaker_labels) + 1
                speaker_labels[label] = number
            return f"Interlocutor {number}: "

        def remember(chunk: bytes) -> None:
            nonlocal buffered_bytes
            with buffer_lock:
                buffered_pcm.append(chunk)
                buffered_bytes += len(chunk)
                while buffered_pcm and buffered_bytes > buffer_limit:
                    buffered_bytes -= len(buffered_pcm.popleft())

        def buffered_snapshot() -> list[bytes]:
            with buffer_lock:
                return list(buffered_pcm)

        def on_open(_app):
            # A sessão da AssemblyAI aceita áudio assim que o socket abre.
            if _app is self.assemblyai_ws_app:
                self.assemblyai_ws_ready_event.set()
                self._queue("status", "Conectado à AssemblyAI. Ouvindo e transcrevendo ao vivo...")

        def on_message(_app, raw_event):
            if _app is not self.assemblyai_ws_app:
                return
            try:
                event = json.loads(raw_event)
            except Exception:
                self.assemblyai_ws_lost_event.set()
                self._queue("status", "Reconectando: resposta inválida da AssemblyAI.")
                return
            event_type = str(event.get("type") or "")
            if event_type == "Begin":
                self.assemblyai_ws_ready_event.set()
                return
            if event_type == "Turn":
                text = str(event.get("transcript") or "").strip()
                if not text or self.assemblyai_ws_done_event.is_set():
                    return
                if self.live_grok_diarize:
                    text = speaker_prefix(event.get("speaker_label")) + text
                if bool(event.get("end_of_turn")):
                    with self.live_lock:
                        committed = self.live_committed_text.strip()
                        if not committed:
                            self.live_committed_text = text
                        elif text not in committed:
                            self.live_committed_text = f"{committed}\n{text}"
                        self.live_draft_text = ""
                        display = self._current_live_text_locked()
                else:
                    with self.live_lock:
                        self.live_draft_text = text
                        display = self._current_live_text_locked()
                self._queue("live_display", display)
                return
            if event_type == "Termination":
                if not self.assemblyai_ws_done_event.is_set():
                    with self.live_lock:
                        text = self.live_committed_text.strip() or self._current_live_text_locked().strip()
                        self.live_committed_text = text
                        self.live_draft_text = ""
                    self.assemblyai_ws_done_event.set()
                    self.assemblyai_ws_app = None
                    self.live_uses_assemblyai_websocket = False
                    if not text:
                        self._queue("status", "Transcrição ao vivo finalizada sem conteúdo.")
                    self._queue("live_display", text)
                    self._queue("status", "Transcrição definitiva concluída.")
                    self._finish_live_output()
                return
            if event_type == "Error":
                self.assemblyai_ws_lost_event.set()
                self._queue(
                    "status",
                    f"Reconectando: {str(event.get('message') or 'erro da AssemblyAI')}",
                )

        def on_error(_app, _error):
            if (
                _app is self.assemblyai_ws_app
                and not self.assemblyai_ws_intentional_close
                and not self.live_abort_event.is_set()
                and not self.assemblyai_ws_done_event.is_set()
            ):
                self._queue("status", "Desconectado da AssemblyAI; reconectando...")
                self.assemblyai_ws_lost_event.set()

        def on_close(_app, _status_code, _message):
            if _app is not self.assemblyai_ws_app:
                return
            if self.assemblyai_ws_intentional_close and not self.assemblyai_ws_done_event.is_set():
                with self.live_lock:
                    text = self.live_committed_text.strip() or self._current_live_text_locked().strip()
                    self.live_committed_text = text
                    self.live_draft_text = ""
                self.assemblyai_ws_done_event.set()
                self.assemblyai_ws_app = None
                self.live_uses_assemblyai_websocket = False
                if not text:
                    self._queue("status", "Transcrição ao vivo finalizada sem conteúdo.")
                self._queue("live_display", text)
                self._queue("status", "Transcrição definitiva concluída.")
                self._finish_live_output()
                return
            if (
                not self.assemblyai_ws_intentional_close
                and not self.live_abort_event.is_set()
                and not self.assemblyai_ws_done_event.is_set()
            ):
                self._queue("status", "Desconectado da AssemblyAI; reconectando...")
                self.assemblyai_ws_lost_event.set()

        def connect() -> bool:
            previous = self.assemblyai_ws_app
            self.assemblyai_ws_app = None
            if previous:
                try:
                    previous.close()
                except Exception:
                    pass
            self.assemblyai_ws_ready_event.clear()
            self.assemblyai_ws_lost_event.clear()
            query = (
                "speech_model=universal-3-5-pro&encoding=pcm_s16le"
                "&sample_rate=16000&continuous_partials=true"
            )
            # language_codes como parâmetro REPETIDO (lista vazia = multi).
            for code in assemblyai_ws_language_codes(self.settings):
                query += f"&language_codes={code}"
            diarize_param = assemblyai_ws_diarize_query(bool(self.live_grok_diarize))
            if diarize_param:
                query += f"&{diarize_param}"
            self._queue("status", f"Parâmetros AssemblyAI: {query}")
            app = websocket.WebSocketApp(
                f"{ASSEMBLYAI_WEBSOCKET_URL}?{query}",
                header=[f"Authorization: {api_key}"],
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            self.assemblyai_ws_app = app
            self.assemblyai_ws_thread = threading.Thread(
                target=lambda: app.run_forever(ping_interval=30, ping_timeout=10),
                daemon=True,
            )
            self.assemblyai_ws_thread.start()
            deadline = time.monotonic() + 15
            while not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                if self.assemblyai_ws_ready_event.wait(0.1):
                    return True
                if self.assemblyai_ws_lost_event.is_set() or time.monotonic() >= deadline:
                    return False
            return False

        def reconnect(attempt: int) -> bool:
            delay = min(8.0, 0.5 * (2 ** max(0, attempt - 1))) + random.uniform(0.0, 0.25)
            self._queue("status", f"Reconectando à AssemblyAI ({attempt}/{GROK_RECONNECT_MAX_ATTEMPTS}) em {delay:.1f}s...")
            if self.live_abort_event.wait(delay) or self.live_stop_event.is_set():
                return False
            if not connect():
                return False
            chunks = buffered_snapshot()
            try:
                for chunk in chunks:
                    self.assemblyai_ws_app.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                self._queue("status", f"Reconectou com sucesso; reenviados {len(chunks)} bloco(s) dos últimos 8 segundos.")
            except Exception:
                self._queue("status", "Reconectou, mas não foi possível reenviar parte do buffer de áudio.")
            return True

        def audio_callback(indata, _frames, _time_info, _status):
            if self.live_stop_event.is_set() or self.live_abort_event.is_set() or self.live_state == "paused":
                return
            chunk = bytes(indata)
            self._push_live_waveform_chunk(chunk)
            self._queue_secondary_audio(chunk)
            with full_pcm_lock:
                if full_pcm is not None:
                    full_pcm.write(chunk)
            remember(chunk)
            try:
                audio_queue.put_nowait(chunk)
            except queue.Full:
                try:
                    audio_queue.get_nowait()
                    audio_queue.put_nowait(chunk)
                    self._queue("status", "Parte do áudio ao vivo foi descartada por atraso local.")
                except queue.Empty:
                    pass

        try:
            pcm_path = self.live_full_pcm_path
            if not pcm_path:
                raise RuntimeError("não foi possível criar o áudio integral do streaming")
            pcm_path.parent.mkdir(parents=True, exist_ok=True)
            full_pcm = pcm_path.open("wb")
            with sd.RawInputStream(
                samplerate=LIVE_SAMPLE_RATE,
                channels=LIVE_CHANNELS,
                dtype="int16",
                blocksize=max(
                    1,
                    LIVE_SAMPLE_RATE * int(settings.get("grok_chunk_ms", 100)) // 1000,
                ),
                callback=audio_callback,
            ):
                attempts = 0
                connected = False
                while not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                    if not connected or self.assemblyai_ws_lost_event.is_set():
                        reconnecting = connected or self.assemblyai_ws_lost_event.is_set() or attempts > 0
                        attempts += 1
                        self._queue("status", "Reconectando ao streaming da AssemblyAI..." if reconnecting else "Conectando ao streaming da AssemblyAI...")
                        connected = reconnect(attempts) if reconnecting else connect()
                        if connected:
                            attempts = 0
                            continue
                        if attempts >= GROK_RECONNECT_MAX_ATTEMPTS:
                            self._queue("live_error", "Falhou: reconexão da AssemblyAI esgotada após 8 tentativas.")
                            return
                        continue
                    try:
                        chunk = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if self.live_state == "paused" or not chunk:
                        continue
                    try:
                        self.assemblyai_ws_app.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                    except Exception:
                        self.assemblyai_ws_lost_event.set()
                        connected = False
        except Exception as exc:
            if not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                self._queue("live_error", f"Falhou: erro no microfone ao vivo: {exc}")
        finally:
            with full_pcm_lock:
                if full_pcm is not None:
                    full_pcm.close()
                    full_pcm = None

    def _deepgram_live_capture_loop(self, settings: dict):
        try:
            import sounddevice as sd
            import websocket
        except Exception as exc:
            self._queue("live_error", f"Streaming do Deepgram indisponível: {exc}")
            return

        api_key = str(settings.get("deepgram_api_key") or "").strip()
        if not api_key:
            self._queue("live_error", "Insira a chave API do Deepgram nas configurações.")
            return

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        buffered_pcm: deque[bytes] = deque()
        buffered_bytes = 0
        buffer_limit = pcm_bytes_for_millis(GROK_RECONNECT_BUFFER_MILLIS)
        buffer_lock = threading.Lock()
        full_pcm_lock = threading.Lock()
        full_pcm = None

        def remember(chunk: bytes) -> None:
            nonlocal buffered_bytes
            with buffer_lock:
                buffered_pcm.append(chunk)
                buffered_bytes += len(chunk)
                while buffered_pcm and buffered_bytes > buffer_limit:
                    buffered_bytes -= len(buffered_pcm.popleft())

        def buffered_snapshot() -> list[bytes]:
            with buffer_lock:
                return list(buffered_pcm)

        def on_open(_app):
            # O handshake do Deepgram está aberto assim que o socket sobe; o
            # Metadata pode demorar ~12s, então o "pronto" é o on_open.
            if _app is self.deepgram_ws_app:
                self.deepgram_ws_ready_event.set()
                self._queue("status", "Conectado ao Deepgram. Ouvindo e transcrevendo ao vivo...")

        def on_message(_app, raw_event):
            if _app is not self.deepgram_ws_app:
                return
            try:
                event = json.loads(raw_event)
            except Exception:
                self.deepgram_ws_lost_event.set()
                self._queue("status", "Reconectando: resposta inválida do Deepgram.")
                return
            event_type = str(event.get("type") or "")
            if event_type == "Metadata":
                self.deepgram_ws_ready_event.set()
                return
            if event_type != "Results":
                return
            channel = event.get("channel") or {}
            alternatives = channel.get("alternatives") or []
            text = str(alternatives[0].get("transcript") or "").strip() if alternatives else ""
            if self.live_grok_diarize:
                text = self._format_grok_diarized_transcript(
                    {"words": (alternatives[0].get("words") or []) if alternatives else []},
                    text,
                )
            is_final = bool(event.get("is_final"))
            speech_final = bool(event.get("speech_final"))
            if text and not self.deepgram_ws_done_event.is_set():
                if is_final or speech_final:
                    # O Deepgram manda SEGMENTOS (cada final é um trecho novo),
                    # diferente do Grok que revisa o texto cumulativo. Acumular
                    # os finais, sem repetir o mesmo segmento.
                    with self.live_lock:
                        committed = self.live_committed_text.strip()
                        if not committed:
                            self.live_committed_text = text
                        elif text not in committed:
                            self.live_committed_text = f"{committed}\n{text}"
                        self.live_draft_text = ""
                        display = self._current_live_text_locked()
                else:
                    with self.live_lock:
                        self.live_draft_text = text
                        display = self._current_live_text_locked()
                self._queue("live_display", display)
            timestamped = _timestamped_text_from_json(event).strip()
            if timestamped:
                self._queue("live_timestamp_data", timestamped)

        def on_error(_app, _error):
            if (
                _app is self.deepgram_ws_app
                and not self.deepgram_ws_intentional_close
                and not self.live_abort_event.is_set()
                and not self.deepgram_ws_done_event.is_set()
            ):
                self._queue("status", "Desconectado do Deepgram; reconectando...")
                self.deepgram_ws_lost_event.set()

        def on_close(_app, _status_code, _message):
            if _app is not self.deepgram_ws_app:
                return
            if self.deepgram_ws_intentional_close and not self.deepgram_ws_done_event.is_set():
                with self.live_lock:
                    text = self.live_committed_text.strip() or self._current_live_text_locked().strip()
                    self.live_committed_text = text
                    self.live_draft_text = ""
                timestamped = (self.live_timestamped_transcript_text or "").strip()
                self.deepgram_ws_done_event.set()
                self.deepgram_ws_app = None
                self.live_uses_deepgram_websocket = False
                if not text:
                    self._queue("status", "Transcrição ao vivo finalizada sem conteúdo.")
                self._queue("live_display", text)
                if timestamped:
                    self._queue("live_payload", text, timestamped, True)
                self._queue("status", "Transcrição definitiva concluída.")
                self._finish_live_output()
                return
            if (
                not self.deepgram_ws_intentional_close
                and not self.live_abort_event.is_set()
                and not self.deepgram_ws_done_event.is_set()
            ):
                self._queue("status", "Desconectado do Deepgram; reconectando...")
                self.deepgram_ws_lost_event.set()

        def connect() -> bool:
            previous = self.deepgram_ws_app
            self.deepgram_ws_app = None
            if previous:
                try:
                    previous.close()
                except Exception:
                    pass
            self.deepgram_ws_ready_event.clear()
            self.deepgram_ws_lost_event.clear()
            language = deepgram_language_param(settings)
            query = deepgram_query_string(settings, language, diarize=self.live_grok_diarize)
            query += (
                "&encoding=linear16&sample_rate=16000&channels=1"
                "&interim_results=true&endpointing=900"
            )
            if self.live_diarize_var.get():
                query += "&diarize=true"
            self._queue("status", f"Parâmetros Deepgram: {query}")
            app = websocket.WebSocketApp(
                f"{DEEPGRAM_STT_WEBSOCKET_URL}?{query}",
                header=[f"Authorization: Token {api_key}"],
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            self.deepgram_ws_app = app
            self.deepgram_ws_thread = threading.Thread(
                target=lambda: app.run_forever(ping_interval=30, ping_timeout=10),
                daemon=True,
            )
            self.deepgram_ws_thread.start()
            deadline = time.monotonic() + 15
            while not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                if self.deepgram_ws_ready_event.wait(0.1):
                    return True
                if self.deepgram_ws_lost_event.is_set() or time.monotonic() >= deadline:
                    return False
            return False

        def reconnect(attempt: int) -> bool:
            delay = min(8.0, 0.5 * (2 ** max(0, attempt - 1))) + random.uniform(0.0, 0.25)
            self._queue("status", f"Reconectando ao Deepgram ({attempt}/{GROK_RECONNECT_MAX_ATTEMPTS}) em {delay:.1f}s...")
            if self.live_abort_event.wait(delay) or self.live_stop_event.is_set():
                return False
            if not connect():
                return False
            chunks = buffered_snapshot()
            try:
                for chunk in chunks:
                    self.deepgram_ws_app.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                self._queue("status", f"Reconectou com sucesso; reenviados {len(chunks)} bloco(s) dos últimos 8 segundos.")
            except Exception:
                self._queue("status", "Reconectou, mas não foi possível reenviar parte do buffer de áudio.")
            return True

        def audio_callback(indata, _frames, _time_info, _status):
            if self.live_stop_event.is_set() or self.live_abort_event.is_set() or self.live_state == "paused":
                return
            chunk = bytes(indata)
            self._push_live_waveform_chunk(chunk)
            self._queue_secondary_audio(chunk)
            with full_pcm_lock:
                if full_pcm is not None:
                    full_pcm.write(chunk)
            remember(chunk)
            try:
                audio_queue.put_nowait(chunk)
            except queue.Full:
                try:
                    audio_queue.get_nowait()
                    audio_queue.put_nowait(chunk)
                    self._queue("status", "Parte do áudio ao vivo foi descartada por atraso local.")
                except queue.Empty:
                    pass

        try:
            pcm_path = self.live_full_pcm_path
            if not pcm_path:
                raise RuntimeError("não foi possível criar o áudio integral do streaming")
            pcm_path.parent.mkdir(parents=True, exist_ok=True)
            full_pcm = pcm_path.open("wb")
            with sd.RawInputStream(
                samplerate=LIVE_SAMPLE_RATE,
                channels=LIVE_CHANNELS,
                dtype="int16",
                blocksize=max(
                    1,
                    LIVE_SAMPLE_RATE * int(settings.get("grok_chunk_ms", 100)) // 1000,
                ),
                callback=audio_callback,
            ):
                attempts = 0
                connected = False
                while not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                    if not connected or self.deepgram_ws_lost_event.is_set():
                        reconnecting = connected or self.deepgram_ws_lost_event.is_set() or attempts > 0
                        attempts += 1
                        self._queue("status", "Reconectando ao streaming do Deepgram..." if reconnecting else "Conectando ao streaming do Deepgram...")
                        connected = reconnect(attempts) if reconnecting else connect()
                        if connected:
                            attempts = 0
                            continue
                        if attempts >= GROK_RECONNECT_MAX_ATTEMPTS:
                            self._queue("live_error", "Falhou: reconexão do Deepgram esgotada após 8 tentativas.")
                            return
                        continue
                    try:
                        chunk = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if self.live_state == "paused" or not chunk:
                        continue
                    try:
                        self.deepgram_ws_app.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                    except Exception:
                        self.deepgram_ws_lost_event.set()
                        connected = False
        except Exception as exc:
            if not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                self._queue("live_error", f"Falhou: erro no microfone ao vivo: {exc}")
        finally:
            with full_pcm_lock:
                if full_pcm is not None:
                    full_pcm.close()
                    full_pcm = None

    def _grok_live_capture_loop(self, settings: dict):
        try:
            import sounddevice as sd
            import websocket
        except Exception as exc:
            self._queue("live_error", f"Streaming do Grok indisponível: {exc}")
            return

        api_key = str(settings.get("grok_api_key") or "").strip()
        if not api_key:
            self._queue("live_error", "Insira a chave API do Grok nas configurações.")
            return

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        buffered_pcm: deque[bytes] = deque()
        buffered_bytes = 0
        buffer_limit = pcm_bytes_for_millis(GROK_RECONNECT_BUFFER_MILLIS)
        buffer_lock = threading.Lock()
        full_pcm_lock = threading.Lock()
        full_pcm = None

        def remember(chunk: bytes) -> None:
            nonlocal buffered_bytes
            with buffer_lock:
                buffered_pcm.append(chunk)
                buffered_bytes += len(chunk)
                while buffered_pcm and buffered_bytes > buffer_limit:
                    buffered_bytes -= len(buffered_pcm.popleft())

        def buffered_snapshot() -> list[bytes]:
            with buffer_lock:
                return list(buffered_pcm)

        def on_message(_app, raw_event):
            if _app is not self.grok_ws_app:
                return
            try:
                event = json.loads(raw_event)
            except Exception:
                self.grok_ws_lost_event.set()
                self._queue("status", "Reconectando: resposta inválida do Grok.")
                return
            event_type = str(event.get("type") or "")
            if event_type == "transcript.created":
                self.grok_ws_ready_event.set()
                self._queue("status", "Conectado. Ouvindo e transcrevendo ao vivo...")
            elif event_type == "transcript.partial":
                text = self._format_grok_diarized_transcript(event, str(event.get("text") or "").strip())
                if text:
                    self._update_live_transcript_window(text, bool(event.get("is_final")), self.live_draft_generation)
                timestamped = _timestamped_text_from_json(event).strip()
                if timestamped:
                    self._queue("live_timestamp_data", timestamped)
            elif event_type == "transcript.done":
                text = self._format_grok_diarized_transcript(event, str(event.get("text") or "").strip())
                timestamped = _timestamped_text_from_json(event).strip()
                if not text:
                    with self.live_lock:
                        text = self._current_live_text_locked().strip()
                    if not text:
                        self._queue("status", "Transcrição ao vivo finalizada sem conteúdo.")
                with self.live_lock:
                    self.live_committed_text = text
                    self.live_draft_text = ""
                self.grok_ws_done_event.set()
                self.grok_ws_app = None
                self.live_uses_grok_websocket = False
                self._queue("live_display", text)
                if timestamped:
                    self._queue("live_payload", text, timestamped, True)
                self._queue("status", "Transcrição definitiva concluída.")
                self._finish_live_output()
            elif event_type == "error":
                self.grok_ws_lost_event.set()
                self._queue("status", f"Reconectando: {str(event.get('message') or 'erro do Grok')}")

        def on_error(_app, _error):
            if _app is self.grok_ws_app and not self.grok_ws_intentional_close and not self.live_abort_event.is_set() and not self.grok_ws_done_event.is_set():
                self._queue("status", "Desconectado do Grok; reconectando...")
                self.grok_ws_lost_event.set()

        def on_close(_app, _status_code, _message):
            if _app is self.grok_ws_app and not self.grok_ws_intentional_close and not self.live_abort_event.is_set() and not self.grok_ws_done_event.is_set():
                self._queue("status", "Desconectado do Grok; reconectando...")
                self.grok_ws_lost_event.set()

        def connect() -> bool:
            previous = self.grok_ws_app
            self.grok_ws_app = None
            if previous:
                try:
                    previous.close()
                except Exception:
                    pass
            self.grok_ws_ready_event.clear()
            self.grok_ws_lost_event.clear()
            language = grok_language_param(self.settings)
            query = "sample_rate=16000&encoding=pcm&interim_results=true"
            if language:
                query += f"&language={language}"
            query += "&format=true&smart_turn=0.65&endpointing=900&filler_words=false"
            if self.live_grok_diarize:
                query += "&diarize=true"
            self._queue("status", f"Parâmetros: {query}")
            app = websocket.WebSocketApp(
                f"{GROK_STT_WEBSOCKET_URL}?{query}",
                header=[f"Authorization: Bearer {api_key}"],
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            self.grok_ws_app = app
            self.grok_ws_thread = threading.Thread(
                target=lambda: app.run_forever(ping_interval=30, ping_timeout=10),
                daemon=True,
            )
            self.grok_ws_thread.start()
            deadline = time.monotonic() + 15
            while not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                if self.grok_ws_ready_event.wait(0.1):
                    return True
                if self.grok_ws_lost_event.is_set() or time.monotonic() >= deadline:
                    return False
            return False

        def reconnect(attempt: int) -> bool:
            delay = min(8.0, 0.5 * (2 ** max(0, attempt - 1))) + random.uniform(0.0, 0.25)
            self._queue("status", f"Reconectando ({attempt}/{GROK_RECONNECT_MAX_ATTEMPTS}) em {delay:.1f}s...")
            if self.live_abort_event.wait(delay) or self.live_stop_event.is_set():
                return False
            if not connect():
                return False
            chunks = buffered_snapshot()
            try:
                for chunk in chunks:
                    self.grok_ws_app.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                self._queue("status", f"Reconectou com sucesso; reenviados {len(chunks)} bloco(s) dos últimos 8 segundos.")
            except Exception:
                self._queue("status", "Reconectou, mas não foi possível reenviar parte do buffer de áudio.")
            return True

        def audio_callback(indata, _frames, _time_info, _status):
            if self.live_stop_event.is_set() or self.live_abort_event.is_set() or self.live_state == "paused":
                return
            chunk = bytes(indata)
            self._push_live_waveform_chunk(chunk)
            self._queue_secondary_audio(chunk)
            with full_pcm_lock:
                if full_pcm is not None:
                    full_pcm.write(chunk)
            remember(chunk)
            try:
                audio_queue.put_nowait(chunk)
            except queue.Full:
                try:
                    audio_queue.get_nowait()
                    audio_queue.put_nowait(chunk)
                    self._queue("status", "Parte do áudio ao vivo foi descartada por atraso local.")
                except queue.Empty:
                    pass

        try:
            pcm_path = self.live_full_pcm_path
            if not pcm_path:
                raise RuntimeError("não foi possível criar o áudio integral do streaming")
            pcm_path.parent.mkdir(parents=True, exist_ok=True)
            full_pcm = pcm_path.open("wb")
            with sd.RawInputStream(
                samplerate=LIVE_SAMPLE_RATE,
                channels=LIVE_CHANNELS,
                dtype="int16",
                blocksize=max(
                    1,
                    LIVE_SAMPLE_RATE * int(settings.get("grok_chunk_ms", 100)) // 1000,
                ),
                callback=audio_callback,
            ):
                attempts = 0
                connected = False
                while not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                    if not connected or self.grok_ws_lost_event.is_set():
                        reconnecting = connected or self.grok_ws_lost_event.is_set() or attempts > 0
                        attempts += 1
                        self._queue("status", "Reconectando ao streaming do Grok..." if reconnecting else "Conectando ao streaming do Grok...")
                        connected = reconnect(attempts) if reconnecting else connect()
                        if connected:
                            attempts = 0
                            continue
                        if attempts >= GROK_RECONNECT_MAX_ATTEMPTS:
                            self._queue("live_error", "Falhou: reconexão do Grok esgotada após 8 tentativas.")
                            return
                        continue
                    try:
                        chunk = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if self.live_state == "paused" or not chunk:
                        continue
                    try:
                        self.grok_ws_app.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                    except Exception:
                        self.grok_ws_lost_event.set()
                        connected = False
        except Exception as exc:
            if not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                self._queue("live_error", f"Falhou: erro no microfone ao vivo: {exc}")
        finally:
            with full_pcm_lock:
                if full_pcm is not None:
                    full_pcm.close()
                    full_pcm = None

    def _live_capture_loop(self, settings: dict):
        try:
            import sounddevice as sd
        except Exception as exc:
            self._queue("live_error", f"Microfone indisponível: {exc}")
            return

        audio_queue: queue.Queue[bytes] = queue.Queue()

        def audio_callback(indata, frames, time_info, status):
            if self.live_stop_event.is_set() or self.live_abort_event.is_set():
                return
            chunk = bytes(indata)
            self._push_live_waveform_chunk(chunk)
            self._queue_secondary_audio(chunk)
            audio_queue.put(chunk)

        final_chunk_bytes = pcm_bytes_for_millis(LIVE_FINAL_CHUNK_MILLIS)
        window_pcm = bytearray()
        window_index = 1
        last_sent_draft_ms = 0

        try:
            with self.live_full_pcm_path.open("wb") as full_pcm:
                with sd.RawInputStream(
                    samplerate=LIVE_SAMPLE_RATE,
                    channels=LIVE_CHANNELS,
                    dtype="int16",
                    callback=audio_callback,
                ):
                    while not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                        try:
                            chunk = audio_queue.get(timeout=0.2)
                        except queue.Empty:
                            continue
                        if self.live_state == "paused":
                            continue
                        if not chunk:
                            continue
                        full_pcm.write(chunk)
                        window_pcm.extend(chunk)

                        while len(window_pcm) >= final_chunk_bytes:
                            final_pcm = bytes(window_pcm[:final_chunk_bytes])
                            del window_pcm[:final_chunk_bytes]
                            self._submit_live_snapshot(final_pcm, window_index, LIVE_FINAL_CHUNK_MILLIS, True, settings)
                            window_index += 1
                            last_sent_draft_ms = 0

                        draft_interval = max(
                            MIN_LIVE_DRAFT_INTERVAL_MILLIS,
                            min(MAX_LIVE_DRAFT_INTERVAL_MILLIS, self.live_interval_ms),
                        )
                        draft_window_ms = min(
                            len(window_pcm) * 1000 // (LIVE_SAMPLE_RATE * LIVE_SAMPLE_WIDTH),
                            LIVE_FINAL_CHUNK_MILLIS - draft_interval,
                        )
                        current_draft_ms = (draft_window_ms // draft_interval) * draft_interval
                        if current_draft_ms > last_sent_draft_ms:
                            last_sent_draft_ms = current_draft_ms
                            self._submit_live_snapshot(bytes(window_pcm), window_index, current_draft_ms, False, settings)
        except Exception as exc:
            if not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                self._queue("live_error", f"Erro no microfone ao vivo: {exc}")

    def _submit_live_snapshot(self, pcm: bytes, window_index: int, millis_in_window: int, is_final: bool, settings: dict):
        if len(pcm) < 1024 or self.live_abort_event.is_set():
            return
        with self.live_lock:
            if is_final:
                generation = self.live_draft_generation
            else:
                self.live_draft_generation += 1
                generation = self.live_draft_generation
        executor = self.live_upload_executor
        if executor:
            executor.submit(self._send_live_snapshot, pcm, window_index, millis_in_window, is_final, generation, settings)

    def _send_live_snapshot(
        self,
        pcm: bytes,
        window_index: int,
        millis_in_window: int,
        is_final: bool,
        generation: int,
        settings: dict,
    ):
        with self.live_lock:
            if not is_final and generation != self.live_draft_generation:
                return
        temp_live = app_base_dir() / "temp" / "live"
        raw_dir = temp_live / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        wav_path = temp_live / f"live_mic_{int(time.time() * 1000)}_{window_index}_{millis_in_window}.wav"
        raw_path = raw_dir / f"{wav_path.stem}.json"
        try:
            write_wav_from_pcm_bytes(wav_path, pcm)
            uploader = self.live_uploader or create_transcription_uploader(self.live_abort_event, settings)
            status, transcript = uploader.post_file(transcribe_url(settings), wav_path, "audio/wav", raw_path)
            if status != 200:
                raw = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else ""
                raise RuntimeError(f"HTTP {status}\n{raw}")
            self._update_live_transcript_window(transcript, is_final, generation)
        except Cancelled:
            pass
        except Exception as exc:
            obsolete = False
            with self.live_lock:
                obsolete = not is_final and generation != self.live_draft_generation
            if self.live_state in ("listening", "paused") and not obsolete:
                self._queue("status", f"Falha na transcrição ao vivo: {exc}")
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _update_live_transcript_window(self, text: str, is_final: bool, generation: int):
        clean = (text or "").strip()
        if not clean:
            return
        with self.live_lock:
            if not is_final and generation != self.live_draft_generation:
                return
            if is_final:
                committed = self.live_committed_text.strip()
                draft = self.live_draft_text.strip()
                # O Grok pode devolver uma revisão de uma parcial já exibida.
                # Preferimos a revisão completa e evitamos acrescentar o mesmo texto.
                if clean == committed or clean == draft or committed.endswith(clean):
                    pass
                elif committed and clean.startswith(committed):
                    self.live_committed_text = clean + "\n"
                else:
                    if self.live_committed_text and not self.live_committed_text.endswith("\n"):
                        self.live_committed_text += "\n"
                    self.live_committed_text += clean + "\n"
                self.live_draft_text = ""
            else:
                self.live_draft_text = clean
            display = self._current_live_text_locked()
        self._queue("live_display", display)

    def _finish_live_transcription(self):
        try:
            if self.live_thread:
                self.live_thread.join(timeout=5)
            pcm_path = self.live_full_pcm_path
            if self.live_abort_event.is_set():
                return
            if not pcm_path or not pcm_path.exists() or pcm_path.stat().st_size < 1024:
                self._queue("status", "Nenhum áudio foi gravado.")
                self._finish_live_output()
                return
            temp_dir = app_base_dir() / "temp"
            temp_live = temp_dir / "live"
            raw_dir = temp_live / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            wav_path = temp_live / f"live_definitive_{int(time.time() * 1000)}.wav"
            raw_path = raw_dir / f"{wav_path.stem}.json"
            try:
                write_wav_from_pcm_file(wav_path, pcm_path)
                definitive_settings = load_settings()
                self.live_uploader = create_transcription_uploader(self.live_abort_event, definitive_settings)
                status, parsed = self.live_uploader.post_file_parsed(
                    transcribe_url(definitive_settings),
                    wav_path,
                    "audio/wav",
                    raw_path,
                )
                if status != 200:
                    raw = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else ""
                    raise RuntimeError(f"HTTP {status}\n{raw}")
                definitive = parsed.text.strip()
                if not definitive:
                    raise RuntimeError("A transcrição definitiva voltou vazia.")
                with self.live_lock:
                    self.live_committed_text = definitive
                    self.live_draft_text = ""
                    display = self._current_live_text_locked()
                self._queue(
                    "live_payload",
                    display,
                    parsed.timestamped_text,
                    is_grok_transcription(definitive_settings),
                )
                self._queue("status", "Transcrição definitiva concluída.")
            except Exception as exc:
                self._queue("status", f"Não consegui gerar a transcrição definitiva. Mantive o texto parcial. Detalhe: {exc}")
            finally:
                try:
                    wav_path.unlink(missing_ok=True)
                except Exception:
                    pass
            self._finish_live_output()
        finally:
            try:
                if self.live_full_pcm_path:
                    self.live_full_pcm_path.unlink(missing_ok=True)
            except Exception:
                pass
            self.live_full_pcm_path = None

    def _finish_live_output(self):
        if self.live_output_finished:
            return
        live_thread = self.live_thread
        if live_thread and live_thread is not threading.current_thread() and live_thread.is_alive():
            if not self.live_capture_finish_waiting:
                self.live_capture_finish_waiting = True
                threading.Thread(target=self._wait_for_live_capture, daemon=True).start()
            return
        self.live_capture_finish_waiting = False
        if self.live_secondary_active and not self.live_secondary_done_event.is_set():
            if not self.live_finish_waiting:
                self.live_finish_waiting = True
                threading.Thread(target=self._wait_for_secondary_live_output, daemon=True).start()
            return
        self.live_finish_waiting = False
        self.live_audio_recovery_available = bool(
            self.live_was_grok_websocket
            and self.live_full_pcm_path
            and self.live_full_pcm_path.exists()
            and self.live_full_pcm_path.stat().st_size >= 1024
        )
        self.live_output_finished = True
        self._queue("live_state", "idle")
        self._queue("status", "Transcrição ao vivo finalizada.")

    def _wait_for_live_capture(self):
        live_thread = self.live_thread
        if live_thread and live_thread is not threading.current_thread():
            live_thread.join()
        self.live_capture_finish_waiting = False
        if not self.live_abort_event.is_set():
            self._finish_live_output()

    def _wait_for_secondary_live_output(self):
        self.live_secondary_done_event.wait(45)
        self.live_finish_waiting = False
        self._finish_live_output()
        if self.live_secondary_done_event.is_set():
            self._queue("status", "Transcrição ao vivo finalizada nos dois modelos.")
        else:
            self._queue("status", "O modelo 2 não concluiu dentro do tempo esperado; o texto recebido foi mantido.")

    def save_html_report(self):
        if not self.last_html_path or not self.last_html_path.exists():
            self.status_var.set("Nenhum HTML disponível para salvar ainda.")
            return
        folder = filedialog.askdirectory(title="Selecionar pasta para salvar o HTML")
        if not folder:
            return
        destination = Path(folder) / self.last_html_path.name
        if destination.exists() and not messagebox.askyesno("sig", f"O arquivo {destination.name} já existe. Deseja substituir?"):
            return
        try:
            shutil.copy2(self.last_html_path, destination)
            self.status_var.set(f"HTML salvo em {destination}")
            messagebox.showinfo("sig", f"HTML salvo em:\n{destination}")
        except Exception as exc:
            messagebox.showerror("sig", f"Não foi possível salvar o HTML:\n{exc}")

    def start_run(self):
        if self.running:
            return
        if getattr(self, "ffmpeg_tools", None) and self.ffmpeg_tools.running:
            messagebox.showinfo("sig", "Aguarde o processamento FFmpeg terminar antes de transcrever arquivos.")
            return
        if self.live_state != "idle":
            messagebox.showinfo("sig", "Pare a transcrição ao vivo antes de transcrever arquivos.")
            return
        if self.assistant_busy:
            messagebox.showinfo("sig", "Aguarde a geração de histórico ou oitiva terminar.")
            return
        if not self.selected_paths:
            messagebox.showinfo("sig", "Selecione pelo menos um arquivo ou uma pasta.")
            return
        self.settings = load_settings()
        multi_transcription = bool(
            self.multi_model_var.get() and self.settings.get("transcription_server_2")
        )
        if is_grok_transcription(self.settings) and not self.settings.get("grok_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Grok nas configurações antes de transcrever.")
            return
        if is_grok_transcription(self.settings) and self.send_zip_var.get():
            self.send_zip_var.set(False)
            self._refresh_zip_controls()
            self.status_var.set("Grok STT envia os arquivos individualmente por REST; o envio ZIP foi desativado.")
        if multi_transcription and self.send_zip_var.get():
            self.send_zip_var.set(False)
            self._refresh_zip_controls()
            self.status_var.set("Multi model usa requisições individuais; o envio ZIP foi desativado.")
        self.cancel_event.clear()
        self.uploader = create_transcription_uploader(self.cancel_event, self.settings)
        self.uploaders = [self.uploader]
        self.running = True
        self.last_html_path = None
        self.progress_var.set(0)
        self._draw_action_button()
        self._draw_save_button()
        self._set_controls_state("disabled")
        self.status_var.set("Preparando fila...")
        paths = list(self.selected_paths)
        mode = self.mode_var.get()
        convert_only = self.convert_only_var.get()
        vad_only = self.vad_only_var.get()
        vad_mode = self.vad_var.get()
        transcribe_after_convert = self.transcribe_after_convert_var.get()
        send_zip = self.send_zip_var.get() and not convert_only and not vad_only
        zip_level = self.zip_level_var.get()
        workflow_settings = self.settings.copy()
        workflow_settings["_multi_transcription"] = multi_transcription
        self.worker_thread = threading.Thread(
            target=self._workflow,
            args=(paths, mode, convert_only, vad_only, vad_mode, transcribe_after_convert, send_zip, zip_level, workflow_settings),
            daemon=True,
        )
        self.worker_thread.start()

    def cancel_current_run(self):
        self.status_var.set("Cancelando...")
        self.cancel_event.set()
        if self.uploader:
            self.uploader.cancel()
        for uploader in self.uploaders:
            uploader.cancel()
        with self.process_lock:
            processes = list(self.active_processes)
        for process in processes:
            try:
                process.terminate()
            except Exception:
                pass

    def _set_controls_state(self, state: str):
        for child in self.files_tab.winfo_children():
            self._set_child_state(child, state)
        self.action_canvas.configure(state="normal")

    def _set_child_state(self, widget, state: str):
        for child in widget.winfo_children():
            try:
                if child is not self.action_canvas:
                    child.configure(state=state)
            except Exception:
                pass
            self._set_child_state(child, state)

    def _workflow(
        self,
        paths: list[Path],
        mode: str,
        convert_only: bool,
        vad_only: bool,
        vad_mode: str,
        transcribe_after_convert: bool,
        send_zip: bool,
        zip_level: str,
        settings: dict,
    ):
        process_started = time.perf_counter()
        temp_dir = app_base_dir() / "temp"
        raw_dir = temp_dir / "raw"
        log_dir = temp_dir / "logs"
        temp_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

        # Arquivos menores entram primeiro para a fila começar a avançar rapidamente.
        paths = sorted(paths, key=lambda p: p.stat().st_size)
        stems = safe_stems(paths)
        jobs = []
        primary_server = selected_transcription_server(settings)
        secondary_server_name = str(settings.get("transcription_server_2") or "")
        multi_transcription = bool(settings.get("_multi_transcription") and secondary_server_name)
        use_vad = vad_mode != "Off" and not convert_only
        for path in paths:
            stem = stems[path]
            job = AudioJob(
                original_path=path,
                original_name=path.name,
                stem=stem,
                mode=mode,
                txt_path=temp_dir / f"{stem}.txt",
                txt_path_2=temp_dir / f"{stem}.modelo_2.txt" if multi_transcription else None,
                raw_path=raw_dir / f"{stem}.json",
                raw_path_2=raw_dir / f"{stem}.modelo_2.json" if multi_transcription else None,
                log_path=log_dir / f"{stem}.ffmpeg.log",
                model_name=primary_server["name"],
                model_name_2=secondary_server_name if multi_transcription else "",
            )
            if use_vad or vad_only:
                # Todo VAD recebe exatamente WAV PCM 16 kHz, mono e 16-bit.
                job.mode = "ready"
                job.converted_path = temp_dir / f"{stem}.vad_entrada.wav"
                job.vad_output_path = temp_dir / f"{stem}.vad.wav"
            elif is_video_file(path):
                job.mode = "ready"
                job.converted_path = temp_dir / f"{stem}.wav"
            elif mode == "ready":
                job.converted_path = temp_dir / f"{stem}.wav"
            elif mode == "compact":
                job.converted_path = temp_dir / f"{stem}.ogg"
            else:
                job.upload_path = path
            jobs.append(job)

        try:
            zip_stats = None
            needs_conversion = any(job.converted_path for job in jobs)
            if (
                needs_conversion
                and transcribe_after_convert
                and not convert_only
                and not send_zip
                and not use_vad
                and not is_grok_transcription(settings)
                and not settings.get("_multi_transcription")
            ):
                self._run_pipelined_conversions_and_transcriptions(jobs, settings)
            elif needs_conversion:
                self._run_conversions(jobs, settings, next_stage_vad=(use_vad or vad_only))
                if self.cancel_event.is_set():
                    raise Cancelled()
                if use_vad or vad_only:
                    self._run_vad_on_jobs(jobs, vad_mode, settings)
                    if self.cancel_event.is_set():
                        raise Cancelled()
                if convert_only and not vad_only:
                    self._queue("status", "Convertido.")
                    self._queue("progress", 100)
                    self._show_folder_button(visible=True)
                    return
                if vad_only:
                    self._queue("status", "VAD concluído.")
                    self._queue("progress", 100)
                    self._show_folder_button(visible=True)
                    return
                if send_zip:
                    zip_stats = self._run_zip_transcription(jobs, settings, temp_dir, raw_dir, zip_level)
                else:
                    self._run_transcriptions(jobs, settings)
            else:
                if self.cancel_event.is_set():
                    raise Cancelled()
                if convert_only and not vad_only:
                    self._queue("status", "Nada para converter no modo Enviar como está.")
                    return
                if vad_only:
                    self._queue("status", "VAD concluído.")
                    self._queue("progress", 100)
                    self._show_folder_button(visible=True)
                    return
                if send_zip:
                    zip_stats = self._run_zip_transcription(jobs, settings, temp_dir, raw_dir, zip_level)
                else:
                    self._run_transcriptions(jobs, settings)
            if self.cancel_event.is_set():
                raise Cancelled()
            html_path = temp_dir / "transcricoes.html"
            stats = self._batch_report_stats(jobs, mode, settings, process_started, send_zip, zip_level, zip_stats)
            write_html_report(jobs, html_path, stats)
            self._queue("html_ready", str(html_path))
            self._queue("status", f"Concluído. HTML gerado em {html_path}")
            self._queue("progress", 100)
            self._show_folder_button(visible=True)
        except Cancelled:
            for job in jobs:
                if not job.transcription and not job.error:
                    job.error = "Cancelado pelo usuário."
                    if job.txt_path:
                        job.txt_path.write_text(job.error, encoding="utf-8")
                    self._queue("job", job.original_path, "Cancelado")
            self._queue("status", "Cancelado.")
        except Exception as exc:
            self._queue("status", f"Erro: {exc}")
        finally:
            self._queue("done")

    # ── VAD ──────────────────────────────────────────────────────────

    def _run_vad_on_jobs(self, jobs: list, vad_mode: str, settings: dict):
        """Gera WAVs filtrados e os define como arquivos de upload."""
        if vad_mode.startswith("Silero"):
            vad_type = "silero"
        elif vad_mode.startswith("WebRTC"):
            vad_type = "webrtc"
        else:
            return
        level = vad_mode.split("-")[-1].strip()

        eligible = [
            job for job in jobs
            if not job.error and job.converted_path and job.converted_path.exists() and job.vad_output_path
        ]
        if not eligible:
            raise RuntimeError("nenhum WAV convertido ficou disponível para o VAD")
        for job in eligible:
            self._queue("job", job.original_path, "Aplicando VAD")
        self._queue("progress", 0)

        worker = app_base_dir() / "vad_worker.py"
        deps = app_base_dir() / "vad_deps"
        python_exe = shutil.which("python") or shutil.which("python3")
        if not worker.exists():
            raise RuntimeError(f"vad_worker.py não encontrado: {worker}")
        if not deps.is_dir():
            raise RuntimeError(f"dependências do VAD não encontradas: {deps}")
        if not python_exe:
            raise RuntimeError("Python não encontrado para executar o VAD")

        payload = {
            "vad_type": vad_type,
            "level": level,
            "vad_deps": str(deps),
            "files": [
                {"input": str(job.converted_path), "output": str(job.vad_output_path)}
                for job in eligible
            ],
        }
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            [python_exe, str(worker)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            creationflags=creationflags,
        )
        with self.process_lock:
            self.active_processes.add(process)

        output_events: queue.Queue = queue.Queue()
        stderr_lines: list[str] = []

        def read_stdout():
            assert process.stdout is not None
            for line in process.stdout:
                output_events.put(line)
            output_events.put(None)

        def read_stderr():
            assert process.stderr is not None
            for line in process.stderr:
                stderr_lines.append(line)

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        jobs_by_input = {str(job.converted_path): job for job in eligible}
        completed_inputs: set[str] = set()
        diagnostics: list[str] = []
        completed = 0

        def accept_result(item: dict):
            nonlocal completed
            input_path = str(item.get("input", ""))
            job = jobs_by_input.get(input_path)
            if job is None or input_path in completed_inputs:
                return
            completed_inputs.add(input_path)
            if item.get("ok"):
                job.vad_input_bytes = int(item.get("input_bytes", 0))
                job.vad_output_bytes = int(item.get("output_bytes", 0))
                job.vad_elapsed = float(item.get("elapsed_ms", 0.0)) / 1000.0
                job.vad_speech_duration = float(item.get("speech_duration", 0.0))
                job.vad_total_duration = float(item.get("total_duration", 0.0))
                if job.vad_output_path.exists() and job.vad_output_path.stat().st_size > 44:
                    job.upload_path = job.vad_output_path
                    self._queue("job", job.original_path, "VAD aplicado")
                else:
                    job.error = "ERRO VAD: arquivo filtrado vazio"
                    self._queue("job", job.original_path, "Erro no VAD")
            else:
                detail = str(item.get("error", "erro não informado pelo worker"))
                job.vad_error = detail
                job.error = f"ERRO VAD: {detail}"
                if job.txt_path:
                    job.txt_path.write_text(job.error, encoding="utf-8")
                self._queue("job", job.original_path, "Erro no VAD")
            completed += 1
            self._queue_phase_progress("Aplicando VAD", completed, len(eligible))

        try:
            assert process.stdin is not None
            process.stdin.write(json.dumps(payload, ensure_ascii=False))
            process.stdin.close()
            stdout_finished = False
            while process.poll() is None or not stdout_finished or not output_events.empty():
                if self.cancel_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise Cancelled()
                try:
                    line = output_events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    stdout_finished = True
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    item = json.loads(stripped)
                except json.JSONDecodeError:
                    diagnostics.append(stripped)
                    continue
                if isinstance(item, dict):
                    accept_result(item)
            process.wait()
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
        finally:
            with self.process_lock:
                self.active_processes.discard(process)

        worker_error = "".join(stderr_lines).strip()
        if diagnostics:
            worker_error = "\n".join([worker_error, *diagnostics]).strip()
        for job in eligible:
            input_path = str(job.converted_path)
            if input_path in completed_inputs:
                continue
            detail = worker_error or f"worker encerrado sem resultado (código {process.returncode})"
            job.vad_error = detail
            job.error = f"ERRO VAD: {detail}"
            if job.txt_path:
                job.txt_path.write_text(job.error, encoding="utf-8")
            self._queue("job", job.original_path, "Erro no VAD")
            completed += 1
            self._queue_phase_progress("Aplicando VAD", completed, len(eligible))
        if all(job.error for job in eligible):
            raise RuntimeError("o VAD falhou em todos os arquivos")

    def _queue_phase_progress(self, label: str, done: int, total: int):
        percent = int((done / max(total, 1) * 100) + 0.5)
        self._queue("progress", percent)
        self._queue("status", f"{label}: {done}/{total} ({percent}%)")

    def _queue_pipeline_progress(self, converted_done: int, total: int, transcribed_done: int):
        convert_percent = int((converted_done / max(total, 1) * 100) + 0.5)
        transcribe_percent = int((transcribed_done / max(total, 1) * 100) + 0.5)
        current_percent = convert_percent if converted_done < total else transcribe_percent
        self._queue("progress", current_percent)
        self._queue(
            "status",
            " | ".join(
                [
                    f"Convertendo arquivos: {converted_done}/{total} ({convert_percent}%)",
                    f"Transcrevendo arquivos: {transcribed_done}/{total} ({transcribe_percent}%)",
                ]
            ),
        )

    def _batch_report_stats(
        self,
        jobs: list[AudioJob],
        mode: str,
        settings: dict,
        process_started: float,
        send_zip: bool,
        zip_level: str,
        zip_stats: list[tuple[str, str]] | None,
    ) -> list[tuple[str, str]]:
        valid_count = 0
        for job in jobs:
            if not job_problem_reason(job, job_transcript_text(job)):
                valid_count += 1
        upload_paths = {
            job.upload_path.resolve(): job.upload_path
            for job in jobs
            if job.upload_path and job.upload_path.exists()
        }
        stats = [
            ("Método", "ZIP" if send_zip else "Requisições individuais"),
            ("Arquivos", str(len(jobs))),
            ("Modo", mode_label_from_value(mode)),
            ("Servidor", selected_transcription_server(settings)["name"]),
        ]
        if settings.get("_multi_transcription") and settings.get("transcription_server_2"):
            stats.append(("Servidor 2", str(settings["transcription_server_2"])))
        if send_zip:
            stats.append(("Nível ZIP", zip_level))
            if zip_stats:
                stats.extend(zip_stats)
        else:
            stats.extend(
                [
                    ("Requisições paralelas", str(settings["transcribe_parallel"])),
                    ("Total enviado", format_bytes(sum(path.stat().st_size for path in upload_paths.values()))),
                ]
            )
        vad_jobs = [j for j in jobs if j.vad_input_bytes > 0 and j.vad_output_bytes > 0]
        if vad_jobs:
            total_vad_speech = sum(j.vad_speech_duration for j in vad_jobs)
            total_vad_dur = sum(j.vad_total_duration for j in vad_jobs)
            total_vad_input = sum(j.vad_input_bytes for j in vad_jobs)
            total_vad_output = sum(j.vad_output_bytes for j in vad_jobs)
            total_vad_elapsed = sum(j.vad_elapsed for j in vad_jobs)
            if total_vad_dur > 0:
                vad_pct = total_vad_speech / total_vad_dur * 100
                stats.append(("VAD — voz detectada", f"{total_vad_speech:.1f}s / {total_vad_dur:.1f}s ({vad_pct:.0f}%)"))
            reduction = (1.0 - (total_vad_output / total_vad_input)) * 100
            stats.extend(
                [
                    ("VAD — entrada", format_bytes(total_vad_input)),
                    ("VAD — saída", format_bytes(total_vad_output)),
                    ("VAD — redução", f"{max(0.0, reduction):.1f}%"),
                    ("VAD — processamento", format_duration(total_vad_elapsed)),
                ]
            )
        stats.extend(
            [
                ("Na tabela", str(valid_count)),
                ("Com problemas", str(max(0, len(jobs) - valid_count))),
                ("Tempo", format_duration(time.perf_counter() - process_started)),
            ]
        )
        return stats

    def _zip_options(self, level_label: str) -> tuple[int, int | None, str]:
        if level_label == "Sem compactação":
            return zipfile.ZIP_STORED, None, "Sem compactação"
        try:
            level = int(level_label)
        except (TypeError, ValueError):
            level = 9
        level = max(1, min(9, level))
        return zipfile.ZIP_DEFLATED, level, str(level)

    def _mark_zip_failure(self, jobs: list[AudioJob], detail: str):
        for job in jobs:
            job.error = f"ERRO ZIP: {detail}"
            if job.txt_path:
                job.txt_path.write_text(job.error, encoding="utf-8")
            self._queue("job", job.original_path, "Erro no ZIP")

    def _run_zip_transcription(
        self,
        jobs: list[AudioJob],
        settings: dict,
        temp_dir: Path,
        raw_dir: Path,
        zip_level: str,
    ) -> list[tuple[str, str]]:
        candidates = [job for job in jobs if not job.error]
        total = len(candidates)
        if total == 0:
            return [("Arquivos no ZIP", "0")]

        zip_jobs = []
        for job in candidates:
            if job.upload_path and job.upload_path.exists():
                zip_jobs.append(job)
            else:
                job.error = "arquivo para envio não definido"
                if job.txt_path:
                    job.txt_path.write_text(job.error, encoding="utf-8")
                self._queue("job", job.original_path, "Erro na transcrição")
        if not zip_jobs:
            return [("Arquivos no ZIP", "0")]

        input_zip_path = temp_dir / "envio_transcricoes.zip"
        response_zip_path = raw_dir / "resposta_transcricoes.zip"
        extract_dir = temp_dir / "zip_resposta"
        input_zip_path.unlink(missing_ok=True)
        response_zip_path.unlink(missing_ok=True)
        shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True, exist_ok=True)

        compression, compresslevel, normalized_level = self._zip_options(zip_level)
        zip_kwargs = {"compression": compression}
        if compresslevel is not None:
            zip_kwargs["compresslevel"] = compresslevel

        uncompressed_size = 0
        create_started = time.perf_counter()
        self._queue("status", f"Criando ZIP para envio: 0/{len(zip_jobs)} (0%)")
        self._queue("progress", 0)
        used_names: set[str] = set()
        try:
            with zipfile.ZipFile(input_zip_path, "w", **zip_kwargs) as archive:
                for index, job in enumerate(zip_jobs, 1):
                    if self.cancel_event.is_set():
                        raise Cancelled()
                    assert job.upload_path is not None
                    suffix = job.upload_path.suffix or ".bin"
                    arcname = f"{job.stem}{suffix}"
                    if arcname.casefold() in used_names:
                        arcname = f"{job.stem}_{index}{suffix}"
                    used_names.add(arcname.casefold())
                    archive.write(job.upload_path, arcname)
                    uncompressed_size += job.upload_path.stat().st_size
                    percent = int((index / max(len(zip_jobs), 1) * 100) + 0.5)
                    self._queue("status", f"Criando ZIP para envio: {index}/{len(zip_jobs)} ({percent}%)")
                    self._queue("progress", min(30, int(percent * 0.3)))
            create_elapsed = time.perf_counter() - create_started
        except Cancelled:
            raise
        except Exception as exc:
            detail = str(exc)
            self._mark_zip_failure(zip_jobs, detail)
            return [
                ("Arquivos no ZIP", str(len(zip_jobs))),
                ("Descompactado", format_bytes(uncompressed_size)),
                ("Erro ZIP", detail[:160]),
            ]

        zip_size = input_zip_path.stat().st_size if input_zip_path.exists() else 0
        request_elapsed = 0.0
        response_size = 0
        extract_elapsed = 0.0
        returned_count = 0
        url = transcribe_url(settings)
        try:
            if not self.uploader:
                raise RuntimeError("uploader não inicializado")
            self._queue("status", f"Enviando ZIP ({format_bytes(zip_size)}) e aguardando resposta do servidor...")
            self._queue("progress", 35)
            request_started = time.perf_counter()
            status, raw, _headers = self.uploader.post_file_raw(
                url,
                input_zip_path,
                "application/zip",
                response_zip_path,
                accept="application/zip, application/octet-stream, application/json, text/plain, */*",
            )
            request_elapsed = time.perf_counter() - request_started
            response_size = len(raw)
            if status != 200:
                preview = raw.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"HTTP {status}: {preview[:500]}")
            if not zipfile.is_zipfile(response_zip_path):
                preview = raw.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"o servidor não retornou um ZIP válido: {preview[:500]}")

            self._queue("status", "Extraindo ZIP retornado pelo servidor...")
            self._queue("progress", 75)
            extract_started = time.perf_counter()
            texts_by_stem: dict[str, str] = {}
            with zipfile.ZipFile(response_zip_path, "r") as archive:
                for member in archive.infolist():
                    if self.cancel_event.is_set():
                        raise Cancelled()
                    if member.is_dir():
                        continue
                    name = Path(member.filename.replace("\\", "/")).name
                    if Path(name).suffix.lower() != ".txt":
                        continue
                    with archive.open(member) as source:
                        content = source.read().decode("utf-8-sig", errors="replace")
                    texts_by_stem[Path(name).stem.casefold()] = content
                    returned_count += 1
            extract_elapsed = time.perf_counter() - extract_started

            done = 0
            for job in zip_jobs:
                if self.cancel_event.is_set():
                    raise Cancelled()
                transcript = texts_by_stem.get(job.stem.casefold())
                if transcript is None:
                    job.error = "TXT não retornado no ZIP."
                    if job.txt_path:
                        job.txt_path.write_text(job.error, encoding="utf-8")
                    self._queue("job", job.original_path, "Erro na transcrição")
                else:
                    job.transcription = transcript.strip()
                    if job.txt_path:
                        job.txt_path.write_text(job.transcription, encoding="utf-8")
                    self._queue("job", job.original_path, "Transcrição vazia" if not job.transcription else "Transcrito")
                done += 1
                percent = int((done / max(len(zip_jobs), 1) * 100) + 0.5)
                self._queue("status", f"Processando resposta ZIP: {done}/{len(zip_jobs)} ({percent}%)")
                self._queue("progress", min(98, 75 + int(percent * 0.23)))
        except Cancelled:
            raise
        except Exception as exc:
            self._mark_zip_failure(zip_jobs, str(exc))

        return [
            ("Arquivos no ZIP", str(len(zip_jobs))),
            ("ZIP enviado", format_bytes(zip_size)),
            ("Descompactado", format_bytes(uncompressed_size)),
            ("Resposta ZIP", format_bytes(response_size)),
            ("TXT retornados", str(returned_count)),
            ("Criar ZIP", format_duration(create_elapsed)),
            ("Aguardar ZIP", format_duration(request_elapsed)),
            ("Extrair ZIP", format_duration(extract_elapsed)),
            ("Nível usado", normalized_level),
        ]

    def _run_conversions(self, jobs: list[AudioJob], settings: dict, next_stage_vad: bool = False):
        total = len(jobs)
        done = 0
        self._queue_phase_progress("Convertendo arquivos", done, total)
        with concurrent.futures.ThreadPoolExecutor(max_workers=settings["convert_parallel"]) as executor:
            future_map = {executor.submit(self._convert_job, job): job for job in jobs}
            for future in concurrent.futures.as_completed(future_map):
                job = future_map[future]
                if self.cancel_event.is_set():
                    raise Cancelled()
                try:
                    future.result()
                    self._queue(
                        "job",
                        job.original_path,
                        "Aplicando VAD" if next_stage_vad else "Convertido",
                    )
                except Cancelled:
                    raise
                except Exception as exc:
                    job.error = f"ERRO conversão: {exc}"
                    job.txt_path.write_text(job.error, encoding="utf-8")
                    self._queue("job", job.original_path, "Erro na conversão")
                done += 1
                self._queue_phase_progress("Convertendo arquivos", done, total)

    def _run_pipelined_conversions_and_transcriptions(self, jobs: list[AudioJob], settings: dict):
        total = len(jobs)
        converted_done = 0
        transcribed_done = 0
        progress_lock = threading.Lock()
        converted_queue: queue.Queue = queue.Queue()
        sentinel = object()
        url = transcribe_url(settings)

        self._queue_pipeline_progress(converted_done, total, transcribed_done)

        def update_progress(convert_delta: int = 0, transcribe_delta: int = 0):
            nonlocal converted_done, transcribed_done
            with progress_lock:
                converted_done += convert_delta
                transcribed_done += transcribe_delta
                current_converted = converted_done
                current_transcribed = transcribed_done
            self._queue_pipeline_progress(current_converted, total, current_transcribed)

        def convert_runner(job: AudioJob):
            if self.cancel_event.is_set():
                raise Cancelled()
            try:
                self._convert_job(job)
                self._queue("job", job.original_path, "Convertido")
                update_progress(convert_delta=1)
                converted_queue.put(job)
            except Cancelled:
                raise
            except Exception as exc:
                job.error = f"ERRO conversão: {exc}"
                job.txt_path.write_text(job.error, encoding="utf-8")
                self._queue("job", job.original_path, "Erro na conversão")
                update_progress(convert_delta=1, transcribe_delta=1)

        def transcribe_worker():
            while True:
                item = converted_queue.get()
                try:
                    if item is sentinel:
                        return
                    if self.cancel_event.is_set():
                        raise Cancelled()
                    job = item
                    try:
                        self._transcribe_job(job, url)
                        self._queue("job", job.original_path, "Transcrito")
                    except Cancelled:
                        raise
                    except Exception as exc:
                        job.error = f"ERRO transcrição: {exc}"
                        job.txt_path.write_text(job.error, encoding="utf-8")
                        self._queue("job", job.original_path, "Erro na transcrição")
                    finally:
                        update_progress(transcribe_delta=1)
                finally:
                    converted_queue.task_done()

        with concurrent.futures.ThreadPoolExecutor(max_workers=settings["transcribe_parallel"]) as transcribe_executor:
            transcribe_futures = [
                transcribe_executor.submit(transcribe_worker)
                for _ in range(settings["transcribe_parallel"])
            ]
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=settings["convert_parallel"]) as convert_executor:
                    convert_futures = [convert_executor.submit(convert_runner, job) for job in jobs]
                    for future in concurrent.futures.as_completed(convert_futures):
                        if self.cancel_event.is_set():
                            raise Cancelled()
                        future.result()
                for _ in transcribe_futures:
                    converted_queue.put(sentinel)
                converted_queue.join()
                for future in concurrent.futures.as_completed(transcribe_futures):
                    future.result()
            except Cancelled:
                self.cancel_event.set()
                for _ in transcribe_futures:
                    converted_queue.put(sentinel)
                raise

    def _convert_job(self, job: AudioJob):
        if self.cancel_event.is_set():
            raise Cancelled()
        if not job.converted_path:
            return
        self._queue("job", job.original_path, "Convertendo")
        conversion_started = time.perf_counter()

        # Evita recodificar WAV PCM 16 kHz mono/16-bit que já está pronto.
        if job.mode == "ready" and is_transcription_ready_wav(job.original_path):
            job.converted_path.parent.mkdir(parents=True, exist_ok=True)
            if job.converted_path.exists():
                job.converted_path.unlink()
            try:
                os.link(job.original_path, job.converted_path)
                preparation = "Arquivo já pronto | sem recodificação (link local)"
            except OSError:
                shutil.copy2(job.original_path, job.converted_path)
                preparation = "Arquivo já pronto | sem recodificação (cópia local)"
            job.conversion_elapsed = time.perf_counter() - conversion_started
            job.upload_path = job.converted_path
            conversion_summary = (
                f"{preparation} | {format_bytes(job.original_path.stat().st_size)} | "
                f"{format_duration(job.conversion_elapsed)}"
            )
            if job.log_path:
                try:
                    job.log_path.write_text(conversion_summary + "\n", encoding="utf-8")
                except OSError:
                    pass
            self._queue("status", f"{job.original_name}: {conversion_summary}")
            return

        ffmpeg = app_base_dir() / "ffmpeg.exe"
        if not ffmpeg.exists():
            raise RuntimeError(f"ffmpeg.exe não encontrado: {ffmpeg}")
        if job.mode == "ready":
            command = [
                str(ffmpeg),
                "-hide_banner",
                "-y",
                "-i",
                str(job.original_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(job.converted_path),
            ]
        else:
            command = [
                str(ffmpeg),
                "-hide_banner",
                "-y",
                "-i",
                str(job.original_path),
                "-vn",
                "-af",
                "aresample=16000",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "libopus",
                "-application",
                "voip",
                "-b:a",
                "32k",
                str(job.converted_path),
            ]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with job.log_path.open("wb") as log:
            process = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            with self.process_lock:
                self.active_processes.add(process)
            try:
                while process.poll() is None:
                    if self.cancel_event.is_set():
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        raise Cancelled()
                    time.sleep(0.15)
            finally:
                with self.process_lock:
                    self.active_processes.discard(process)
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg retornou código {process.returncode}")
        if not job.converted_path.exists():
            raise RuntimeError("arquivo convertido não foi criado")
        job.conversion_elapsed = time.perf_counter() - conversion_started
        job.upload_path = job.converted_path
        conversion_summary = (
            f"Conversão local | {format_bytes(job.original_path.stat().st_size)} -> "
            f"{format_bytes(job.converted_path.stat().st_size)} | {format_duration(job.conversion_elapsed)}"
        )
        if job.log_path:
            try:
                with job.log_path.open("a", encoding="utf-8", errors="replace") as log:
                    log.write(f"\n{conversion_summary}\n")
            except OSError:
                pass
        self._queue("status", f"{job.original_name}: {conversion_summary}")
        # VAD removido da pipeline principal


    def _run_transcriptions(self, jobs: list[AudioJob], settings: dict):
        if settings.get("_multi_transcription") and settings.get("transcription_server_2"):
            self._run_multi_transcriptions(jobs, settings)
            return
        candidates = [job for job in jobs if not job.error]
        total = len(candidates)
        if total == 0:
            return
        url = transcribe_url(settings)
        done = 0
        self._queue_phase_progress("Transcrevendo arquivos", done, total)

        def run_group(group: list[AudioJob], parallelism: int):
            nonlocal done
            if not group:
                return
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, parallelism)) as executor:
                future_map = {executor.submit(self._transcribe_job, job, url): job for job in group}
                for future in concurrent.futures.as_completed(future_map):
                    job = future_map[future]
                    if self.cancel_event.is_set():
                        raise Cancelled()
                    try:
                        future.result()
                        self._queue("job", job.original_path, "Transcrito")
                    except Cancelled:
                        raise
                    except Exception as exc:
                        job.error = f"ERRO transcrição: {exc}"
                        job.txt_path.write_text(job.error, encoding="utf-8")
                        self._queue("job", job.original_path, "Erro na transcrição")
                    done += 1
                    self._queue_phase_progress("Transcrevendo arquivos", done, total)

        configured_parallelism = max(1, int(settings["transcribe_parallel"]))
        if not is_grok_transcription(settings):
            run_group(candidates, configured_parallelism)
            return

        candidates.sort(key=lambda job: job.upload_path.stat().st_size if job.upload_path else 0)
        forty_mb = 40 * 1024 * 1024
        sixty_mb = 60 * 1024 * 1024
        small = [job for job in candidates if job.upload_path and job.upload_path.stat().st_size < forty_mb]
        medium = [
            job
            for job in candidates
            if job.upload_path and forty_mb <= job.upload_path.stat().st_size < sixty_mb
        ]
        large = [job for job in candidates if job.upload_path and job.upload_path.stat().st_size >= sixty_mb]

        run_group(small, configured_parallelism)
        if medium:
            medium_parallelism = min(configured_parallelism, 2)
            notice = (
                "Grok: restam somente arquivos de 40 MB ou mais; "
                f"paralelismo limitado a {medium_parallelism}."
            )
            self._queue("activity", notice, "warning")
            run_group(medium, medium_parallelism)
        if large:
            notice = (
                "Grok: restam somente arquivos de 60 MB ou mais; "
                "os envios serão feitos individualmente."
            )
            self._queue("activity", notice, "warning")
            run_group(large, 1)

    def _run_multi_transcriptions(self, jobs: list[AudioJob], settings: dict):
        candidates = [job for job in jobs if not job.error]
        total = len(candidates)
        if total == 0:
            return
        secondary_settings = settings_for_transcription_server(
            settings, str(settings["transcription_server_2"])
        )
        model_settings = (settings, secondary_settings)
        uploaders = [
            create_transcription_uploader(self.cancel_event, item_settings)
            for item_settings in model_settings
        ]
        self.uploaders = uploaders
        done = [0, 0]
        progress_lock = threading.Lock()

        def update_progress(index: int):
            with progress_lock:
                done[index - 1] += 1
                first, second = done
            self._queue("progress", int(((first + second) / (total * 2)) * 100 + 0.5))
            self._queue("status", f"Modelo 1: {first}/{total}  |  Modelo 2: {second}/{total}")

        self._queue("status", f"Modelo 1: 0/{total}  |  Modelo 2: 0/{total}")

        def model_runner(index: int):
            current_settings = model_settings[index - 1]
            uploader = uploaders[index - 1]
            url = transcribe_url(current_settings)
            configured_parallelism = max(1, int(settings["transcribe_parallel"]))

            def run_group(group: list[AudioJob], parallelism: int):
                if not group:
                    return
                with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, parallelism)) as executor:
                    future_map = {
                        executor.submit(
                            self._transcribe_job,
                            job,
                            url,
                            uploader,
                            current_settings,
                            index,
                        ): job
                        for job in group
                    }
                    for future in concurrent.futures.as_completed(future_map):
                        job = future_map[future]
                        if self.cancel_event.is_set():
                            raise Cancelled()
                        try:
                            future.result()
                        except Cancelled:
                            raise
                        except Exception as exc:
                            detail = f"ERRO transcrição modelo {index}: {exc}"
                            if index == 1:
                                job.error = detail
                                if job.txt_path:
                                    job.txt_path.write_text(detail, encoding="utf-8")
                            else:
                                job.error_2 = detail
                                if job.txt_path_2:
                                    job.txt_path_2.write_text(detail, encoding="utf-8")
                        finally:
                            update_progress(index)

            ordered = sorted(
                candidates,
                key=lambda job: job.upload_path.stat().st_size if job.upload_path else 0,
            )
            if not is_grok_transcription(current_settings):
                run_group(ordered, configured_parallelism)
                return
            forty_mb, sixty_mb = 40 * 1024 * 1024, 60 * 1024 * 1024
            small = [job for job in ordered if job.upload_path and job.upload_path.stat().st_size < forty_mb]
            medium = [
                job for job in ordered
                if job.upload_path and forty_mb <= job.upload_path.stat().st_size < sixty_mb
            ]
            large = [job for job in ordered if job.upload_path and job.upload_path.stat().st_size >= sixty_mb]
            run_group(small, configured_parallelism)
            run_group(medium, min(configured_parallelism, 2))
            run_group(large, 1)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(model_runner, index) for index in (1, 2)]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        for job in candidates:
            if job.error and job.error_2:
                self._queue("job", job.original_path, "Erro nos dois modelos")
            elif job.error or job.error_2:
                self._queue("job", job.original_path, "Transcrito parcialmente")
            else:
                self._queue("job", job.original_path, "Transcrito nos dois modelos")

    def _transcribe_job(
        self,
        job: AudioJob,
        url: str,
        uploader: GraniteUploader | None = None,
        request_settings: dict | None = None,
        model_index: int = 1,
    ):
        if self.cancel_event.is_set():
            raise Cancelled()
        if not job.upload_path:
            raise RuntimeError("arquivo para envio não definido")
        self._queue("job", job.original_path, "Enviando")
        mime_type = MIME_TYPES.get(job.upload_path.suffix.lower()) or mimetypes.guess_type(job.upload_path.name)[0]
        if not mime_type:
            mime_type = "application/octet-stream"
        uploader = uploader or self.uploader
        request_settings = request_settings or self.settings
        if not uploader:
            raise RuntimeError("uploader não inicializado")
        raw_path = job.raw_path if model_index == 1 else job.raw_path_2
        txt_path = job.txt_path if model_index == 1 else job.txt_path_2
        if raw_path is None or txt_path is None:
            raise RuntimeError(f"arquivos de saída do modelo {model_index} não definidos")
        # AssemblyAI: áudios com 2 minutos ou mais vão pelo fluxo assíncrono
        # (v2/upload -> v2/transcript -> polling a cada 3s).
        if (
            is_assemblyai_transcription(request_settings)
            and probe_duration_ms(job.upload_path) >= 120000
        ):
            result = self._assemblyai_async_transcribe(job, request_settings)
            if model_index == 1:
                job.transcription = result
            else:
                job.transcription_2 = result
            txt_path.write_text(result, encoding="utf-8")
            return
        status, transcript = uploader.post_file(url, job.upload_path, mime_type, raw_path)
        if status != 200 and is_grok_transcription(request_settings):
            raw = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else ""
            if "auth context expired" in raw.casefold():
                self._queue("job", job.original_path, "Aguardando reenvio")
                with self.grok_expired_retry_lock:
                    if self.cancel_event.is_set():
                        raise Cancelled()
                    for attempt in range(1, 3):
                        self._queue("job", job.original_path, f"Reenviando ({attempt}/2)")
                        status, transcript = uploader.post_file(
                            url,
                            job.upload_path,
                            mime_type,
                            raw_path,
                        )
                        if status == 200:
                            break
                        raw = (
                            raw_path.read_text(encoding="utf-8", errors="replace")
                            if raw_path.exists()
                            else ""
                        )
                        if "auth context expired" not in raw.casefold():
                            break
        if status != 200:
            raw = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else ""
            raise RuntimeError(f"HTTP {status}\n{raw}")
        result = transcript or "(sem transcrição)"
        if model_index == 1:
            job.transcription = result
        else:
            job.transcription_2 = result
        txt_path.write_text(result, encoding="utf-8")

    def _assemblyai_async_transcribe(self, job: AudioJob, request_settings: dict) -> str:
        """Fluxo async da AssemblyAI (espelho do Android): upload -> submit ->
        polling GET /v2/transcript/{id} a cada 3 segundos."""
        api_key = str(request_settings.get("assemblyai_api_key") or "").strip()
        if not api_key:
            raise RuntimeError("Insira a chave API da AssemblyAI nas configurações.")
        diarize_checked = bool(request_settings.get("diarize") or request_settings.get("grok_diarize"))
        detection, code = assemblyai_rest_language(request_settings)
        speaker_labels, punctuate = assemblyai_rest_diarize(diarize_checked)

        def http_request(host: str, path: str, *, headers=None, payload=None, method="GET"):
            if self.cancel_event.is_set():
                raise Cancelled()
            conn = http.client.HTTPSConnection(host, timeout=180)
            try:
                conn.request(method, path, body=payload, headers=headers or {})
                response = conn.getresponse()
                return response.status, response.read()
            finally:
                conn.close()

        if not job.upload_path:
            raise RuntimeError("arquivo para envio não definido")
        self._queue("job", job.original_path, "AssemblyAI upload")
        upload_payload = job.upload_path.read_bytes()
        status, body = http_request(
            "api.assemblyai.com",
            "/v2/upload",
            headers={"Authorization": api_key, "Content-Type": "application/octet-stream"},
            payload=upload_payload,
            method="POST",
        )
        if status != 200:
            raise RuntimeError(f"AssemblyAI upload HTTP {status}\n{body[:400]!r}")
        upload_url = json.loads(body.decode("utf-8", errors="replace") or "{}").get("upload_url")
        if not upload_url:
            raise RuntimeError("AssemblyAI não retornou upload_url.")

        params: dict = {
            "audio_url": upload_url,
            "speech_models": ["universal-3-5-pro", "universal-2"],
        }
        if detection:
            params["language_detection"] = True
        if code:
            params["language_code"] = code
        if speaker_labels:
            params["speaker_labels"] = True
            params["punctuate"] = True
        status, body = http_request(
            "api.assemblyai.com",
            "/v2/transcript",
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            payload=json.dumps(params).encode("utf-8"),
            method="POST",
        )
        if status != 200:
            raise RuntimeError(f"AssemblyAI async HTTP {status}\n{body[:400]!r}")
        transcript_id = json.loads(body.decode("utf-8", errors="replace") or "{}").get("id")
        if not transcript_id:
            raise RuntimeError("AssemblyAI não retornou id.")

        attempt = 0
        while True:
            if self.cancel_event.is_set():
                raise Cancelled()
            attempt += 1
            self._queue("job", job.original_path, f"AssemblyAI async ({attempt})")
            status, body = http_request(
                "api.assemblyai.com",
                f"/v2/transcript/{transcript_id}",
                headers={"Authorization": api_key},
            )
            if status != 200:
                raise RuntimeError(f"AssemblyAI poll HTTP {status}")
            payload = json.loads(body.decode("utf-8", errors="replace") or "{}")
            state = payload.get("status")
            if state == "completed":
                text = str(payload.get("text") or "").strip()
                if not text:
                    raise RuntimeError("A AssemblyAI retornou uma transcrição vazia (async).")
                return text
            if state == "error":
                raise RuntimeError(f"AssemblyAI async falhou: {payload.get('error') or 'erro desconhecido'}")
            # Espera 3 segundos em fatias para respeitar o cancelamento.
            for _ in range(6):
                if self.cancel_event.wait(0.5):
                    raise Cancelled()

    def _queue(self, *items):
        self.ui_queue.put(items)

    def _poll_ui_queue(self):
        try:
            while True:
                message = self.ui_queue.get_nowait()
                kind = message[0]
                if kind == "job":
                    path, status = message[1], message[2]
                    item = self.tree_items.get(path)
                    if item:
                        values = list(self.tree.item(item, "values"))
                        if len(values) >= 3:
                            values[2] = status
                            self.tree.item(item, values=values)






                elif kind == "status":
                    self.status_var.set(message[1])
                elif kind == "activity":
                    tag = message[2] if len(message) > 2 else None
                    self._append_activity_log(message[1], tag)
                elif kind == "progress":
                    value = max(0, min(100, int(message[1])))
                    self.progress_var.set(value)
                elif kind == "html_ready":
                    self.last_html_path = Path(message[1])
                    self._draw_save_button()
                elif kind == "live_display":
                    self.last_live_transcript_text = message[1]
                    self.live_plain_transcript_text = message[1]
                    self._set_live_text(message[1])
                elif kind == "live_timestamp_data":
                    self._set_live_timestamp_data(message[1])
                elif kind == "live_payload":
                    allow_timestamps = len(message) > 3 and bool(message[3])
                    self._set_live_timestamp_payload(
                        message[1], message[2], allow_timestamps
                    )
                elif kind == "live_recovery_result":
                    self._set_live_timestamp_payload(message[1], message[2], True)
                    self.live_audio_recovery_available = bool(
                        self.live_full_pcm_path
                        and self.live_full_pcm_path.exists()
                        and self.live_full_pcm_path.stat().st_size >= 1024
                    )
                    self.live_output_finished = True
                    self._set_live_state("idle")
                elif kind == "live_recovery_error":
                    self.live_audio_recovery_available = bool(
                        self.live_full_pcm_path
                        and self.live_full_pcm_path.exists()
                        and self.live_full_pcm_path.stat().st_size >= 1024
                    )
                    self.live_output_finished = True
                    self._set_live_state("idle")
                    self.status_var.set(message[1])
                elif kind == "live_display_2":
                    self.last_live_transcript_text_2 = message[1]
                    self._set_live_editor("transcript2", message[1])
                elif kind == "live_state":
                    self._set_live_state(message[1])
                elif kind == "live_error":
                    self.cancel_live_mic()
                    self.status_var.set(message[1])
                elif kind == "assistant_text_result":
                    generation, target, task, text, elapsed = message[1:]
                    if generation == self.assistant_generation:
                        self._set_assistant_target_text(target, text)
                        if target == "live":
                            self._remember_live_assistant_result(task, 1, text)
                        self.assistant_task_states[task] = "done"
                        self.assistant_task_elapsed[task] = elapsed
                        status_var = self._assistant_target_status(target)
                        if task == "statement":
                            status_var.set(f"Oitiva requisitada ({float(elapsed):.1f}s)")
                            self._finish_activity_step(
                                "assistant:statement",
                                float(elapsed),
                            )
                            if target == "live":
                                self._set_activity_status(
                                    f"Oitiva requisitada ({float(elapsed):.1f}s)",
                                    log=False,
                                )
                        else:
                            status_var.set(f"Histórico requisitado ({float(elapsed):.1f}s)")
                            self._finish_activity_step(
                                "assistant:history",
                                float(elapsed),
                            )
                            if target == "live":
                                self._set_activity_status(
                                    f"Histórico requisitado ({float(elapsed):.1f}s)",
                                    log=False,
                                )
                            self._refresh_history_completion_status(target)
                        self._render_assistant_progress()
                elif kind == "qualification_result":
                    generation, raw_result, allowed_ids, elapsed = message[1:]
                    if generation == self.assistant_generation:
                        try:
                            fields = parse_qualification_json(
                                raw_result,
                                allowed_ids,
                                self.qualification_fields,
                            )
                            self.qualification_result_fields = fields
                            self._refresh_qualification_output_from_fields()
                            self._finish_activity_step("assistant:qualification", float(elapsed))
                            self.qualification_status_var.set(
                                f"Qualificação concluída em {float(elapsed):.1f}s."
                            )
                            self._set_activity_status(
                                f"Qualificação requisitada ({float(elapsed):.1f}s)",
                                log=False,
                            )
                        except Exception as exc:
                            self._finish_activity_step(
                                "assistant:qualification",
                                float(elapsed),
                                error=str(exc),
                            )
                            self.qualification_status_var.set(f"Resposta inválida: {exc}")
                            self._set_activity_status(f"Qualificação ERRO ({float(elapsed):.1f}s): {exc}", log=False)
                elif kind == "qualification_error":
                    generation, detail, elapsed = message[1:]
                    if generation == self.assistant_generation:
                        self._finish_activity_step(
                            "assistant:qualification",
                            float(elapsed),
                            error=detail,
                        )
                        self.qualification_status_var.set(
                            f"Falha após {float(elapsed):.1f}s: {detail}"
                        )
                        self._set_activity_status(f"Qualificação ERRO ({float(elapsed):.1f}s): {detail}", log=False)
                elif kind == "live_qualification_result":
                    generation, raw_result, elapsed = message[1:]
                    if generation == self.assistant_generation:
                        generate_document = self.pending_occurrence_document_generation
                        self.pending_occurrence_document_generation = False
                        try:
                            formatted = format_occurrence_qualification(
                                raw_result,
                                self.qualification_fields,
                            )
                            if not formatted:
                                raise ValueError("a IA não devolveu informações utilizáveis")
                            self.last_live_qualification_text = formatted
                            self._set_live_editor("qualification", formatted)
                            self._finish_activity_step("assistant:qualification", float(elapsed))
                            self.live_assistant_status_var.set(
                                f"Qualificação concluída em {float(elapsed):.1f}s."
                            )
                            self._set_activity_status(
                                f"Qualificação requisitada ({float(elapsed):.1f}s)",
                                log=False,
                            )
                            if generate_document:
                                self.root.after_idle(
                                    self._generate_occurrence_document_from_current_text
                                )
                        except Exception as exc:
                            self._finish_activity_step(
                                "assistant:qualification",
                                float(elapsed),
                                error=str(exc),
                            )
                            self.live_assistant_status_var.set(
                                f"Resposta inválida após {float(elapsed):.1f}s: {exc}"
                            )
                            self._set_activity_status(f"Qualificação ERRO ({float(elapsed):.1f}s): {exc}", log=False)
                elif kind == "live_qualification_error":
                    generation, detail, elapsed = message[1:]
                    if generation == self.assistant_generation:
                        self._finish_activity_step(
                            "assistant:qualification",
                            float(elapsed),
                            error=detail,
                        )
                        self.pending_occurrence_document_generation = False
                        self.live_assistant_status_var.set(
                            f"Falha após {float(elapsed):.1f}s: {detail}"
                        )
                        self._set_activity_status(f"Qualificação ERRO ({float(elapsed):.1f}s): {detail}", log=False)
                elif kind == "document_clipboard_ready":
                    _, elapsed = message[1:]
                    self._set_document_copy_progress(False)
                    self.live_document_copy_button.configure(state="normal")
                    self._finish_activity_step("document:copy", float(elapsed))
                    self.assistant_task_states["document_copy"] = "done"
                    self.assistant_task_elapsed["document_copy"] = float(elapsed)
                    self._render_assistant_progress()
                    self._set_activity_status(f"Cópia requisitada ({float(elapsed):.1f}s)", log=False)
                elif kind == "document_clipboard_error":
                    detail, elapsed = message[1:]
                    self._set_document_copy_progress(False)
                    self.live_document_copy_button.configure(state="normal")
                    self._finish_activity_step("document:copy", float(elapsed), error=detail)
                    self.assistant_task_states["document_copy"] = "error"
                    self.assistant_task_elapsed["document_copy"] = float(elapsed)
                    self._render_assistant_progress()
                    self._set_activity_status(
                        f"Cópia ERRO ({float(elapsed):.1f}s): {detail}",
                        log=False,
                    )
                    messagebox.showerror(
                        "Copiar documento",
                        "Não consegui copiar mantendo a formatação do Word.\n\n"
                        f"Detalhe: {detail}",
                        parent=self.root,
                    )
                elif kind == "document_preview_render_ready":
                    generation, preview_path, image_path, pages, page_regions, open_after, elapsed = message[1:]
                    if generation == self.document_preview_generation:
                        preview_path = Path(preview_path)
                        image_path = Path(image_path)
                        self.last_generated_document_preview_path = preview_path
                        self.last_generated_document_preview_image_path = image_path
                        self.live_document_zoom_combo.configure(state="readonly")
                        self._show_embedded_document_preview(
                            image_path,
                            int(pages),
                            list(page_regions),
                        )
                        self._finish_activity_step("preview", float(elapsed))
                        self._set_activity_status(f"Preview requisitado ({float(elapsed):.1f}s)", log=False)
                        if open_after:
                            try:
                                preview_url = preview_path.resolve().as_uri() + "#zoom=100"
                                opened = webbrowser.open_new(preview_url)
                                if not opened and os.name == "nt":
                                    os.startfile(preview_path)
                            except Exception as exc:
                                messagebox.showerror(
                                    "Visualizar documento",
                                    f"Não consegui abrir a visualização.\n\nDetalhe: {exc}",
                                    parent=self.root,
                                )
                elif kind == "document_preview_render_error":
                    generation, detail, open_after, elapsed = message[1:]
                    if generation == self.document_preview_generation:
                        self._finish_activity_step("preview", float(elapsed), error=detail)
                        self.live_document_zoom_combo.configure(state="disabled")
                        self.document_preview_page_var.set("Prévia indisponível.")
                        self._set_embedded_document_preview_message(
                            "Não foi possível carregar a visualização."
                        )
                        self._set_activity_status(
                            f"Preview ERRO ({float(elapsed):.1f}s): {detail}",
                            log=False,
                        )
                        if open_after:
                            messagebox.showerror(
                                "Visualizar documento",
                                f"Não consegui gerar a visualização.\n\nDetalhe: {detail}",
                                parent=self.root,
                            )
                elif kind == "document_save_ready":
                    destination_path, elapsed = message[1:]
                    self.live_document_save_button.configure(state="normal")
                    destination_path = Path(destination_path)
                    save_task = getattr(self, "_active_document_save_task", "document_save_docx")
                    step_key = "document:save:docx" if save_task == "document_save_docx" else "document:save:pdf"
                    self._finish_activity_step(step_key, float(elapsed))
                    self.assistant_task_states[save_task] = "done"
                    self.assistant_task_elapsed[save_task] = float(elapsed)
                    self._render_assistant_progress()
                    self._set_activity_status(f"Salvamento requisitado ({float(elapsed):.1f}s)", log=False)
                elif kind == "document_save_error":
                    detail, elapsed = message[1:]
                    self.live_document_save_button.configure(state="normal")
                    save_task = getattr(self, "_active_document_save_task", "document_save_docx")
                    step_key = "document:save:docx" if save_task == "document_save_docx" else "document:save:pdf"
                    self._finish_activity_step(step_key, float(elapsed), error=detail)
                    self.assistant_task_states[save_task] = "error"
                    self.assistant_task_elapsed[save_task] = float(elapsed)
                    self._render_assistant_progress()
                    self._set_activity_status(
                        f"Salvar ERRO ({float(elapsed):.1f}s): {detail}",
                        log=False,
                    )
                    messagebox.showerror(
                        "Salvar documento",
                        f"Não consegui salvar o documento.\n\nDetalhe: {detail}",
                        parent=self.root,
                    )
                elif kind == "document_viewer_ready":
                    viewer, canvas, image_path, page_regions = message[1:]
                    if not viewer.winfo_exists():
                        return
                    try:
                        with Image.open(image_path) as source:
                            source_image = source.convert("RGB")
                        photo = ImageTk.PhotoImage(source_image)
                        source_image.close()
                        canvas.delete("all")
                        canvas.create_image(2, 2, image=photo, anchor="nw")
                        canvas._viewer_photo = photo
                        canvas.configure(
                            scrollregion=(0, 0, photo.width() + 4, photo.height() + 4)
                        )
                        viewer.update_idletasks()
                        first_page_height = (
                            page_regions[0][1] - page_regions[0][0]
                            if page_regions
                            else photo.height()
                        )
                        screen_w = viewer.winfo_screenwidth()
                        screen_h = viewer.winfo_screenheight()
                        target_w = min(screen_w - 80, photo.width() + 34)
                        target_h = min(screen_h - 120, first_page_height + 30)
                        viewer.geometry(f"{max(320, target_w)}x{max(240, target_h)}")
                    except Exception as exc:
                        canvas.delete("all")
                        canvas.create_text(
                            300,
                            230,
                            text=f"Não foi possível abrir a visualização.\n{exc}",
                            fill="#b3261e",
                            width=420,
                        )
                elif kind == "document_viewer_error":
                    viewer, canvas, detail = message[1:]
                    if viewer.winfo_exists():
                        canvas.delete("all")
                        canvas.create_text(
                            300,
                            230,
                            text=f"Não foi possível gerar a visualização.\n\n{detail}",
                            fill="#b3261e",
                            width=420,
                        )
                elif kind == "assistant_multi_text_result":
                    generation, task, index, text, elapsed = message[1:]
                    if generation == self.assistant_generation:
                        editor = task if index == 1 else f"{task}2"
                        self._set_live_editor(editor, text)
                        self._remember_live_assistant_result(task, index, text)
                        self.assistant_multi_results.add((task, index))
                        self.assistant_multi_elapsed[(task, index)] = elapsed
                        if (task, 1) in self.assistant_multi_results and (task, 2) in self.assistant_multi_results:
                            self.assistant_task_states[task] = "done"
                        self.assistant_task_elapsed[task] = elapsed
                        task_label = "Histórico" if task == "history" else "Oitiva"
                        self._finish_activity_step(
                            f"assistant:{task}:{index}",
                            float(elapsed),
                        )
                        self._set_activity_status(
                            f"{task_label} {index} requisitado ({float(elapsed):.1f}s)",
                            log=False,
                        )
                        self._render_assistant_progress()
                elif kind == "assistant_multi_error":
                    generation, task, index, detail, elapsed = message[1:]
                    if generation == self.assistant_generation:
                        self.assistant_multi_errors[(task, index)] = detail
                        task_label = "Histórico" if task == "history" else "Oitiva"
                        self._finish_activity_step(
                            f"assistant:{task}:{index}",
                            float(elapsed),
                            error=detail,
                        )
                        self._set_activity_status(
                            f"{task_label} {index} ERRO ({float(elapsed):.1f}s): {detail}",
                            log=False,
                        )
                elif kind == "assistant_names_result":
                    generation, target, names, elapsed = message[1:]
                    if generation == self.assistant_generation:
                        self._set_assistant_target_names(target, names)
                        self.assistant_task_states["names"] = "done"
                        self.assistant_task_elapsed["names"] = elapsed
                        self._finish_activity_step("assistant:names", float(elapsed))
                        if target == "live":
                            self._set_activity_status(
                                f"Partes requisitadas ({float(elapsed):.1f}s)",
                                log=False,
                            )
                        self._refresh_history_completion_status(target)
                        self._render_assistant_progress()
                elif kind == "assistant_task_error":
                    generation, target, task, detail, elapsed = message[1:]
                    if generation == self.assistant_generation:
                        self.assistant_task_states[task] = "error"
                        self.assistant_task_elapsed[task] = elapsed
                        status_var = self._assistant_target_status(target)
                        labels = {
                            "history": "gerar o histórico",
                            "names": "identificar as partes",
                            "statement": "redigir a oitiva",
                        }
                        self._finish_activity_step(
                            "assistant:names" if task == "names" else f"assistant:{task}",
                            float(elapsed),
                            error=detail,
                        )
                        status_var.set(f"Não consegui {labels[task]}: {detail}")
                        self._render_assistant_progress()
                elif kind == "assistant_finished":
                    generation = message[1]
                    if generation == self.assistant_generation:
                        if self.assistant_phase == "qualification":
                            self.pending_occurrence_document_generation = False
                        self.assistant_busy = False
                        self.assistant_client = None
                        self._set_assistant_buttons_state("normal")
                        self._refresh_live_editors_state()
                        self._refresh_qualification_editors_state()
                        self._render_assistant_progress()
                elif kind == "imei_result":
                    generation, imei, record = message[1:]
                    if generation == self.imei_generation and imei == self.imei_last_processed:
                        self.imei_model_var.set(format_imei_model(record))
                        self.imei_status_var.set("")
                        self.refresh_imei_history()
                elif kind == "imei_error":
                    generation, imei, detail = message[1:]
                    if generation == self.imei_generation and imei == self.imei_last_processed:
                        self.imei_model_var.set(detail)
                        self.imei_status_var.set("")
                elif kind == "update_available":
                    self.available_update = dict(message[1])
                    self.update_button_var.set("Atualização disponível")
                    self.update_button.configure(state="normal")
                    if not self.update_button.winfo_ismapped():
                        self.update_button.pack(side=RIGHT, anchor="n")
                    self._finish_activity_step(
                        "update:check",
                        time.perf_counter() - getattr(self, "_update_check_started", time.perf_counter()),
                        suffix="- Encontrada!",
                        tag="activity_step_warning",
                    )
                    self._append_activity_log(
                        f"Nova versão disponível: {self.available_update['version']}.",
                        "warning",
                    )
                elif kind == "update_available_sync":
                    state = dict(message[1])
                    self.available_update_sync = state
                    self.available_update = None
                    self.update_button_var.set("Atualizar")
                    self.update_button.configure(state="normal")
                    if not self.update_button.winfo_ismapped():
                        self.update_button.pack(side=RIGHT, anchor="n")
                    self._finish_activity_step(
                        "update:check",
                        time.perf_counter() - getattr(self, "_update_check_started", time.perf_counter()),
                        suffix="- Encontrada!",
                        tag="activity_step_warning",
                    )
                    count = len(state["download"])
                    size = sum(int(state["files"][path]["size"]) for path in state["download"])
                    self._append_activity_log(
                        f"Nova versão {state['version']}: {count} arquivo(s) para baixar "
                        f"({self._format_size(size)}), {len(state['remove'])} para remover.",
                        "warning",
                    )
                elif kind == "update_sync_file_progress":
                    path, downloaded, total = message[1], int(message[2]), int(message[3])
                    if total and total > 0:
                        percent = min(100, round(downloaded * 100 / total))
                        display = f"{percent}%"
                    else:
                        display = self._format_size(downloaded)
                    self._render_sync_file_line(path, display, None)
                elif kind == "update_sync_file_done":
                    self._render_sync_file_line(str(message[1]), "100%", "vad_total")
                elif kind == "update_not_found":
                    self._finish_activity_step(
                        "update:check",
                        time.perf_counter() - getattr(self, "_update_check_started", time.perf_counter()),
                        suffix="- Não tem!",
                    )
                elif kind == "update_check_error":
                    detail = str(message[1])
                    self._finish_activity_step(
                        "update:check",
                        time.perf_counter() - getattr(self, "_update_check_started", time.perf_counter()),
                        error=detail,
                    )
                elif kind == "update_progress":
                    self.update_button_var.set(message[1])
                elif kind == "update_error":
                    self.update_installing = False
                    self.update_button.configure(state="normal")
                    self.update_button_var.set("Atualização disponível")
                    detail = str(message[1])
                    self._append_activity_log(f"Falha ao atualizar: {detail}", "warning")
                    messagebox.showerror("Atualização do SIG", f"Não foi possível atualizar:\n{detail}")
                elif kind == "update_ready":
                    self.update_button_var.set("Reiniciando...")
                    self._launch_prepared_update(Path(message[1]), str(message[2]))
                elif kind == "update_ready_sync":
                    self.update_button_var.set("Reiniciando...")
                    count_done = len([
                        p for p in self.available_update_sync.get("download", [])
                        if p not in self._sync_file_marks
                    ]) if self.available_update_sync else 0
                    total_count = len(self.available_update_sync.get("download", [])) if self.available_update_sync else 0
                    self._append_activity_log(
                        f"Download concluído: {count_done}/{total_count} arquivo(s) baixados.",
                        "vad_total",
                    )
                    self._launch_sync_update(
                        Path(message[1]), Path(message[2]), str(message[3])
                    )
                elif kind == "done":
                    self.running = False
                    self._set_controls_state("normal")
                    self._convert_only_changed()
                    self._draw_action_button()
                    self._draw_save_button()
        except queue.Empty:
            pass
        except Exception as exc:
            try:
                self._append_activity_log(f"UI queue erro: {exc}")
            except Exception:
                pass
        finally:
            try:
                self.root.after(100, self._poll_ui_queue)
            except Exception:
                pass

    def _on_close(self):
        self.live_recovery_cancel_event.set()
        self.live_audio_recovery_available = False
        self._set_live_audio_recovery_visible(False)
        path = self.live_full_pcm_path
        if path and self.live_state == "idle":
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        if getattr(self, "ffmpeg_tools", None):
            self.ffmpeg_tools.shutdown()
        if self.running or self.live_state != "idle" or self.assistant_busy:
            self.cancel_current_run()
            self.cancel_live_mic()
            self.cancel_assistant_request()
            self.root.after(500, self.root.destroy)
        else:
            self.root.destroy()


class CanvasImage:
    def __init__(self, path: Path):
        import tkinter as tk

        source = tk.PhotoImage(file=str(path))
        self.image = source.subsample(2, 2)


def main():
    root = Tk()
    app = SigApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
