"""SIG - janela principal (UI Tkinter) e orquestracao do fluxo de trabalho.

O QUE VIVE AQUI (e so aqui):
  - constantes de interface e defaults que apenas a UI usa;
  - a classe SigApp (janelas, abas, dialogs, threads de conversao/transcricao);
  - main() e o bootstrap (instancia unica, atualizacao, abertura de arquivos).

O QUE NAO VIVE AQUI (implementacao real nos modulos vizinhos):
  app_env ................ caminhos, identidade e capacidade da maquina
  providers.py ........... catalogo de provedores STT/texto + DEFAULT_SETTINGS
  settings_store.py ...... carregar/normalizar/salvar settings.json
  domain_models.py ....... AudioJob, Cancelled e acessores do job
  transcription_parsing .. parsing de respostas STT (JSON/texto/timestamps)
  text_models.py ......... selecao/parse de modelos de texto (IA)
  http_clients.py ........ GraniteUploader, TextModelClient
  stt_clients.py ......... protocolo STT (REST/WS, form fields, provedores)
  log_formatting.py ...... formatacao de comandos FFmpeg e de parametros
  reporting.py ........... HTML de relatorio e de status ao vivo
  documents.py ........... DOCX (modelos Word), PDF via Word, previa
  media_files.py ......... extensoes/MIME e deteccao de tipo de arquivo
  audio_io.py ............ PCM <-> WAV da captura ao vivo
  imei_lookup.py ......... consulta/historico de IMEI
  name_database.py ....... base de nomes (normalizacao/fonetica)
  qualification.py ....... qualificacao de ocorrencias (JSON/labels)
  ui_widgets.py .......... tooltip e botao de icone reutilizaveis
  ffmpeg_tools_panel.py .. aba FFmpeg (conversao/corte/juncao/player)
  qr_encoder / smart_join_planner / stt_provider_rules / assistant_prompts

COMO USAR: os nomes extraidos continuam importaveis daqui (blocos
"API historica" logo apos os imports locais), para nao quebrar testes e
chamadas antigas. Ao alterar comportamento, edite o MODULO de origem -
nunca duplique a implementacao neste arquivo.
Mapa completo, camadas e receitas: docs/agents/module-map.md
"""

import base64
import concurrent.futures
import ctypes
import hashlib
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
import shlex
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
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import BOTH, END, LEFT, RIGHT, TOP, X, Y, BooleanVar, Canvas, IntVar, PhotoImage, StringVar, Text, Tk, Toplevel
from tkinter import filedialog, messagebox, ttk
from urllib.parse import quote, urlencode, urlparse

from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageTk
import pypdfium2 as pdfium

from assistant_prompts import (
    DEFAULT_HISTORY_SYSTEM_PROMPT,
    DEFAULT_QUALIFICATION_SYSTEM_PROMPT,
    history_user_prompt,
    qualification_user_prompt,
    statement_prompt,
    statement_user_prompt,
)
import qr_encoder
import smart_join_planner
import stt_provider_rules
from stt_provider_rules import (
    alibaba_language_hints,
    apply_transcription_language_option,
    assemblyai_rest_diarize,
    assemblyai_rest_language,
    assemblyai_ws_diarize_query,
    assemblyai_ws_language_codes,
    codes_for_help,
    deepgram_diarize_query,
    deepgram_language_param,
    DEEPGRAM_KEYTERM_TOKEN_BUDGET,
    elevenlabs_rest_diarize,
    elevenlabs_rest_language_code,
    elevenlabs_ws_diarize_query,
    elevenlabs_ws_language,
    estimate_keyterm_tokens,
    grok_diarize_query,
    grok_language_param,
    grok_rest_diarize,
    invalid_codes,
    KEYWORDS_OFF_LABEL,
    keyword_profiles,
    keywords_for_provider,
    keywords_profile_label_to_value,
    keywords_selector_label,
    keywords_selector_options,
    language_custom,
    language_mode,
    MAX_STT_KEYWORD_LENGTH,
    MAX_STT_KEYWORDS,
    MENU_OPTIONS,
    metamuse_language_bias,
    metamuse_mode,
    normalize_stt_keywords,
    MAX_KEYWORD_PROFILES,
    DEFAULT_KEYWORD_PROFILE_NAME,
    parse_codes,
    stt_keywords_enabled,
    supports_diarize,
    transcription_language_option,
    TRANSCRIPTION_LANGUAGE_OPTIONS,
)
from sync_common import (
    R2_PUBLIC_HOST,
    SyncError,
    classify_sync_files,
    validate_sync_manifest,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/ffmpeg_tools_panel.py (codigo movido verbatim).
from ffmpeg_tools_panel import (  # noqa: F401
    VIDEO_QUALITY_LEVELS,
    VIDEO_QUALITY_MENU_LABELS,
    VideoAcceleration,
    MediaProfile,
    RangeTimeline,
    InsertAudioTimeline,
    EmbeddedMediaPlayer,
    FfmpegTaskTracker,
    FfmpegToolsPanel,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/documents.py (codigo movido verbatim).
from documents import (  # noqa: F401
    DOCUMENT_TEMPLATE_NAMES,
    build_cf_html,
    set_windows_document_clipboard,
    export_docx_to_pdf_with_word,
    _crop_preview_page_to_content,
    _window_physical_dpi,
    render_pdf_preview,
    PORTUGUESE_MONTHS,
    PORTUGUESE_CARDINALS,
    portuguese_number_words,
    WORD_PARAGRAPH_RE,
    WORD_TEXT_RE,
    WORD_FLOW_BREAK_RE,
    _replace_word_paragraph_markers,
    generate_docx_from_template,
    ensure_document_templates,
    download_github_url,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/ui_widgets.py (codigo movido verbatim).
from ui_widgets import (  # noqa: F401
    create_tooltip,
    PreviewIconButton,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/media_files.py (codigo movido verbatim).
from media_files import (  # noqa: F401
    SUPPORTED_EXTENSIONS,
    VIDEO_EXTENSIONS,
    AUDIO_EXTENSIONS,
    MIME_TYPES,
    is_video_file,
    is_transcription_ready_wav,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/reporting.py (codigo movido verbatim).
from reporting import (  # noqa: F401
    html_document,
    write_html_report,
    build_live_html,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/qualification.py (codigo movido verbatim).
from qualification import (  # noqa: F401
    LIVE_QUALIFICATION_FIELD_IDS,
    LIVE_QUALIFICATION_DEFAULT_SELECTED,
    parse_qualification_json,
    _qualification_age_in_years,
    format_occurrence_qualification,
    format_qualification_fields,
    qualification_display_label,
    history_completion_status,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/name_database.py (codigo movido verbatim).
from name_database import (  # noqa: F401
    parse_assistant_names,
    add_assistant_name,
    distinct_names,
    UPPERCASE_NAME_SEQUENCE,
    UPPERCASE_WORD,
    IGNORED_UPPERCASE_WORDS,
    NAME_CONNECTORS,
    extract_uppercase_names,
    normalize_name,
    phonetic_name_key,
    matching_name_keys,
    load_name_database,
    name_database_path,
    add_name_to_database,
    remove_name_from_database,
    extract_names_from_database,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/imei_lookup.py (codigo movido verbatim).
from imei_lookup import (  # noqa: F401
    compute_imei_luhn_digit,
    read_imei_history_records,
    append_imei_history,
    find_imei_history_record,
    format_imei_model,
    format_imei_time,
    format_imei_history_item,
    fetch_imei_info_record,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/audio_io.py (codigo movido verbatim).
from audio_io import (  # noqa: F401
    LIVE_SAMPLE_RATE,
    LIVE_CHANNELS,
    LIVE_SAMPLE_WIDTH,
    pcm_bytes_for_millis,
    write_wav_from_pcm_bytes,
    write_wav_from_pcm_file,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/stt_clients.py (codigo movido verbatim).
from stt_clients import (  # noqa: F401
    transcribe_url,
    probe_duration_ms,
    deepgram_query_string,
    is_grok_transcription,
    is_deepgram_transcription,
    is_assemblyai_transcription,
    is_elevenlabs_transcription,
    is_metamuse_transcription,
    is_alibaba_transcription,
    transcription_form_fields,
    create_transcription_uploader,
    metamuse_handshake_payload,
    metamuse_rest_request_body,
    metamuse_format_rest_response,
    metamuse_rest_transcribe,
    ALIBABA_AUTH_ERROR,
    PARAMS_BLOCK_TAG_PREFIX,
    alibaba_rest_body,
    alibaba_format_rest_response,
    alibaba_rest_transcribe,
    alibaba_ws_run_task,
    alibaba_ws_finish_task,
    alibaba_ws_sentence_text,
    metamuse_ws_log_params,
    alibaba_ws_log_params,
    alibaba_rest_log_params,
    alibaba_ensure_vocabulary,
    alibaba_create_vocabulary,
    alibaba_delete_vocabulary,
    alibaba_vocabulary_records,
    alibaba_vocabulary_record_update,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/http_clients.py (codigo movido verbatim).
from http_clients import (  # noqa: F401
    GraniteUploader,
    TextModelClient,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/text_models.py (codigo movido verbatim).
from text_models import (  # noqa: F401
    selected_text_model,
    selected_text_model_for,
    assistant_request_model_label,
    extract_text_model_output,
    extract_content_text,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/transcription_parsing.py (codigo movido verbatim).
from transcription_parsing import (  # noqa: F401
    ParsedTranscription,
    _format_transcription_timestamp,
    _timed_entry,
    _timed_word_entries,
    _timestamped_text_from_json,
    parse_transcription_response,
    extract_text_from_response,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/settings_store.py (codigo movido verbatim).
from settings_store import (  # noqa: F401
    clamp_int,
    normalize_settings,
    load_settings,
    save_settings,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/providers.py (codigo movido verbatim).
from providers import (  # noqa: F401
    IMEI_API_KEY,
    GROK_API_NAME,
    GROK_STT_URL,
    GROK_STT_WEBSOCKET_URL,
    DEEPGRAM_API_NAME,
    DEEPGRAM_STT_URL,
    DEEPGRAM_STT_WEBSOCKET_URL,
    ASSEMBLYAI_API_NAME,
    ASSEMBLYAI_SYNC_URL,
    ASSEMBLYAI_WEBSOCKET_URL,
    ELEVENLABS_API_NAME,
    ELEVENLABS_STT_URL,
    ELEVENLABS_WEBSOCKET_URL,
    META_MUSE_API_NAME,
    META_MUSE_STT_URL,
    META_MUSE_STT_WEBSOCKET_URL,
    META_MUSE_MODEL,
    ALIBABA_API_NAME,
    ALIBABA_REST_URL,
    ALIBABA_WEBSOCKET_URL,
    ALIBABA_REST_MODEL,
    ALIBABA_WS_MODEL,
    GROK_TEXT_URL,
    DEEPSEEK_TEXT_URL,
    GROK_TEXT_NAME,
    GROK_NON_REASONING_TEXT_NAME,
    GROK_NON_REASONING_LEGACY_NAME,
    DEEPSEEK_TEXT_NAME,
    IA_PROXY_NAME,
    IA_PROXY_PRIMARY_URL,
    SERVER_GEMMA_NAME,
    SERVER_GEMMA_MODEL,
    SERVER_GEMMA_URL,
    SERVER_GEMMA_NAMES,
    GROK_TEXT_API_NAMES,
    DEEPSEEK_API_NAMES,
    PARTS_EXTRACTION_LABELS,
    TEXT_TASK_KEYS,
    DEFAULT_SETTINGS,
    API_KEY_IMPORT_FIELDS,
    read_transcription_servers,
    read_text_models,
    selected_text_model_config,
    selected_transcription_server,
    transcription_server_label,
    parse_api_keys_text,
    fallback_text_model_for_missing_api_key,
    fallback_transcription_server_for_missing_api_key,
    is_realtime_only_transcription_server,
    plausible_elevenlabs_api_key,
    plausible_assemblyai_api_key,
    plausible_xai_api_key,
    plausible_deepseek_api_key,
    settings_for_transcription_server,
    transcription_providers_for_servers,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/domain_models.py (codigo movido verbatim).
from domain_models import (  # noqa: F401
    Cancelled,
    AudioJob,
    _JOB_LIST_PLURALS,
    job_transcript_text,
    job_problem_reason,
    audio_job_attr,
    audio_job_set,
    job_transcript_for_model,
    job_problem_reason_for_model,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/app_env.py (codigo movido verbatim).
from app_env import (  # noqa: F401
    APP_NAME,
    IMEI_HISTORY_FILE,
    resource_path,
    app_base_dir,
    project_root,
    settings_path,
    hostname_online,
    imei_history_path,
    cpu_parallel_options,
    default_parallelism,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/log_formatting.py (codigo movido verbatim).
from log_formatting import (  # noqa: F401
    FFMPEG_COMMAND_BLOCK_TAG,
    format_process_command,
    _log_path_basename,
    _NUMERIC_LOG_ARG_RE,
    _LOG_FILE_SUFFIX_RE,
    _log_generic_filename,
    _classify_ffmpeg_command_parts,
    _is_structural_probe,
    format_ffmpeg_command_for_log,
    _numbered_log_label,
    format_ffmpeg_commands_for_log,
    safe_stems,
    format_bytes,
    format_duration,
    mode_label_from_value,
    format_ws_params_block,
    params_block_single_line,
)


APP_VERSION = "20260910_002"





















LIVE_LANGUAGES = (("pt", "Português"), ("en", "Inglês"), ("es", "Espanhol"))

# Rótulos usados na janela de seleção de campos da qualificação (engrenagem).
LIVE_QUALIFICATION_FIELD_LABELS = {
    "nome": "Nome",
    "rg": "RG",
    "cpf": "CPF",
    "nascimento": "Nascimento",
    "naturalidade": "Naturalidade",
    "profissao": "Profissão",
    "pai": "Pai",
    "mae": "Mãe",
    "endereco": "Endereço",
    "bairro": "Bairro",
    "cidade": "Cidade",
    "telefone": "Telefone",
}


# Janela de tempo (segundos) em que a qualificação é considerada "recém
# organizada": dentro dela o botão 'Gerar documento' NÃO re-organiza — apenas
# gera o documento com o texto atual. Após expirar, volta a organizar antes.
QUALIFICATION_ORGANIZED_TIMEOUT_S = 60

LIVE_FINAL_CHUNK_MILLIS = 30000
DEFAULT_LIVE_DRAFT_INTERVAL_MILLIS = 1000
MIN_LIVE_DRAFT_INTERVAL_MILLIS = 100
MAX_LIVE_DRAFT_INTERVAL_MILLIS = 10000
LIVE_INTERVAL_VALUES_MS = (
    100, 200, 300, 400, 500, 600, 700, 800, 900,
    1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000,
    15000, 20000, 25000, 30000,
)
# Altura reservada na linha de cima de cada microfone da aba Ocorrência. O
# slot da coluna vermelha abriga o botão de reenvio do áudio integral por
# REST, sempre centralizado na mesma coluna do microfone vermelho.
LIVE_RECOVERY_SLOT_HEIGHT = 26
GROK_RECONNECT_MAX_ATTEMPTS = 8
GROK_RECONNECT_BUFFER_MILLIS = 8000
IMEI_HISTORY_COLLAPSED_LIMIT = 10

























































































































































































































































































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
        self._reset_keywords_off_on_start()
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
        self.live_uses_metamuse_websocket = False
        self.live_uses_alibaba_websocket = False
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
        self.metamuse_ws_app = None
        self.metamuse_ws_thread: threading.Thread | None = None
        self.metamuse_ws_ready_event = threading.Event()
        self.metamuse_ws_done_event = threading.Event()
        self.metamuse_ws_lost_event = threading.Event()
        self.metamuse_ws_intentional_close = False
        self.alibaba_ws_app = None
        self.alibaba_ws_thread: threading.Thread | None = None
        self.alibaba_ws_ready_event = threading.Event()
        self.alibaba_ws_done_event = threading.Event()
        self.alibaba_ws_lost_event = threading.Event()
        self.alibaba_ws_intentional_close = False
        self.alibaba_ws_task_id = ""
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
        self._last_live_qualification_fields: dict[str, str] = {}
        # Instante (monotônico) em que a qualificação foi organizada pela IA;
        # durante QUALIFICATION_ORGANIZED_TIMEOUT_S o 'Gerar documento' usa o
        # texto atual sem re-organizar.
        self._qualification_organized_at: float | None = None
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
        self.microphone_available = False
        self.microphone_check_after_id = None
        self.live_waveform_lock = threading.Lock()
        # Keep roughly one envelope sample per visible pixel for a denser waveform.
        self.live_waveform_levels = deque([0.0] * 168, maxlen=168)
        self.live_waveform_last_capture_at = 0.0

        self.live_language_var = StringVar(value="pt")
        self.live_language_label_var = StringVar(value="Idioma: Português")
        self.live_diarize_var = BooleanVar(value=False)
        self.live_diarize_check = None
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
        self.files_language_label_var = StringVar(value="Idioma: pt")
        self.files_keywords_label_var = StringVar(value=f"Keywords: {KEYWORDS_OFF_LABEL}")
        self.status_var = StringVar(value="Escolha arquivos ou uma pasta para começar.")
        self._activity_status_suppressed = 0
        self._activity_steps: dict[str, dict[str, str]] = {}
        self.live_ws_finalize_pending = False
        self.live_ws_finalize_started: float | None = None
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
        self.multi_transcription_model_vars: dict[str, BooleanVar] = {}
        self.multi_transcription_model_labels: dict[str, str] = {}
        self.multi_text_model_var = BooleanVar(value=False)
        self.multi_text_secondary = ""
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
        self.live_qualification_field_vars = {
            field_id: BooleanVar(value=field_id in LIVE_QUALIFICATION_DEFAULT_SELECTED)
            for field_id in LIVE_QUALIFICATION_FIELD_IDS
        }
        self.live_qualification_fields_win = None
        self.document_preview_zoom_var = StringVar(value="100%")
        self.document_preview_page_var = StringVar(value="")
        self.document_preview_page_regions: list[tuple[int, int]] = []

        self.qrcode_link_var = StringVar()
        self.qrcode_status_var = StringVar(value="Cole um link e gere o QR Code.")
        self.qrcode = None
        self.qrcode_photo = None
        self.qrcode_shorten_var = BooleanVar(value=False)
        self.qrcode_alias_var = StringVar()
        self.qrcode_shortened_var = StringVar()
        self.qrcode_alias_entry = None
        self.qrcode_shortened_row = None
        self.qrcode_shortened_entry = None
        self.qrcode_shortened_copy_button = None
        self.qrcode_content = None
        self.qrcode_shorten_busy = False
        self.qrcode_shorten_started = 0.0

        self._build_style()
        self.paste_icon = self._make_paste_icon()
        self.copy_icon = self._make_copy_icon()
        self.clear_icon = self._make_clear_icon()
        self.gear_icon = self._make_gear_icon()
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
        self.root.after(0, self._refresh_microphone_availability)
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
        # Keep the settings pages on the normal light surface. Each individual
        # settings section owns its gray interior through the LabelFrame and
        # its inner-frame style, instead of creating one continuous gray panel.
        settings_page_surface = "#f4f7f6"
        style.configure("Settings.TFrame", background=settings_page_surface)
        style.configure("Settings.Inner.TFrame", background=settings_surface)
        style.configure("Settings.TLabelframe", background=settings_surface)
        style.configure("Settings.TLabelframe.Label", background=settings_surface)
        style.configure("Disabled.Settings.TFrame", background=settings_surface)
        style.configure("Disabled.Settings.TLabelframe", background=settings_surface)
        style.configure(
            "Disabled.Settings.TLabelframe.Label",
            background=settings_surface,
            foreground="#8a918e",
        )
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
        style.configure(
            "Disabled.Settings.TLabel",
            background=settings_surface,
            foreground="#8a918e",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Disabled.Settings.TCheckbutton",
            background=settings_surface,
            foreground="#8a918e",
            font=("Segoe UI", 10),
        )
        style.configure("Muted.TLabel", background="#f4f7f6", foreground="#667371", font=("Segoe UI", 9))
        style.configure(
            "DocumentPreview.TLabel",
            background="#f4f7f6",
            foreground="#536565",
            font=("Segoe UI Semibold", 9),
        )
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
        # Botões da tela de Keywords: "+" verde e "−" vermelho.
        style.configure(
            "KeywordAdd.TButton",
            foreground="#ffffff",
            background="#16833a",
            font=("Segoe UI Semibold", 13),
            padding=(8, 0),
            anchor="center",
        )
        style.map(
            "KeywordAdd.TButton",
            background=[("active", "#116b30"), ("disabled", "#7ea98a")],
            foreground=[("disabled", "#f1f4f2")],
        )
        style.configure(
            "KeywordRemove.TButton",
            foreground="#ffffff",
            background="#b3261e",
            font=("Segoe UI Semibold", 13),
            padding=(8, 0),
            anchor="center",
        )
        style.map(
            "KeywordRemove.TButton",
            background=[("active", "#8d1d17"), ("disabled", "#c9a19d")],
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

    def _make_paste_icon(self):
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = "#263735"
        draw.rounded_rectangle((4, 5, 16, 18), radius=1, outline=color, width=2)
        draw.line((7, 5, 7, 4, 8, 3, 12, 3, 13, 4, 13, 5), fill=color, width=2)
        draw.line((7, 10, 13, 10), fill=color, width=2)
        draw.line((7, 14, 12, 14), fill=color, width=2)
        return ImageTk.PhotoImage(image, master=self.root)

    def _make_copy_icon(self):
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = "#263735"
        draw.rounded_rectangle((6, 3, 16, 14), radius=1, outline=color, width=2)
        draw.rounded_rectangle((3, 6, 13, 17), radius=1, outline=color, width=2)
        return ImageTk.PhotoImage(image, master=self.root)

    def _make_clear_icon(self):
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = "#263735"
        draw.line((13, 2, 8, 11), fill=color, width=2)
        draw.polygon(((6, 9), (11, 12), (8, 18), (2, 15)), outline=color)
        draw.line((4, 14, 9, 17), fill=color, width=2)
        draw.line((6, 11, 10, 13), fill=color, width=2)
        return ImageTk.PhotoImage(image, master=self.root)

    def _make_gear_icon(self):
        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = "#263735"
        cx, cy = 10, 10
        draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=color)
        draw.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), outline=color, width=2)
        for angle in (0, 45, 90, 135, 180, 225, 270, 315):
            radians = math.radians(angle)
            outer = 9.5
            inner = 6.5
            x1 = cx + math.cos(radians) * inner
            y1 = cy + math.sin(radians) * inner
            x2 = cx + math.cos(radians) * outer
            y2 = cy + math.sin(radians) * outer
            draw.line((x1, y1, x2, y2), fill=color, width=3)
        return ImageTk.PhotoImage(image, master=self.root)

    def _make_recover_icon(self, color="#263735"):
        image = Image.new("RGBA", (17, 17), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.arc((2, 2, 15, 15), start=45, end=315, fill=color, width=2)
        draw.polygon(((14, 3), (14, 7), (11, 4)), fill=color)
        return ImageTk.PhotoImage(image, master=self.root)

    def _make_document_action_icon(self, kind: str):
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
        return ImageTk.PhotoImage(image, master=self.root)

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

    def _log_message_tag(self, message: str) -> str | None:
        """Cor automática da linha do log pelo conteúdo (FFmpeg dourado, erro
        vermelho, aviso amarelo, sucesso verde)."""
        lower = str(message or "").strip().lower()
        if not lower:
            return None
        # Comandos FFmpeg (inclusive a forma renderizada "$ ffmpeg ..." e a
        # forma antiga com caminho completo "...\\ffmpeg.exe").
        ffmpeg_detected = (
            lower.startswith("ffmpeg:")
            or lower.startswith("ffmpeg ")
            or "ffmpeg" in lower.split(" ")[0:2]
            or "ffmpeg.exe" in lower
        )
        if lower.startswith("$ "):
            ffmpeg_detected = "ffmpeg" in lower
        if ffmpeg_detected:
            # Erros que mencionam o FFmpeg (ex.: "FFmpeg retornou código 1",
            # "ffmpeg.exe não foi encontrado") são vermelhos, não amarelos.
            strong_error = (
                r"retornou código",
                r"não foi encontrad",
                r"não foi poss",
                r"\bfalh",
                r"\berro\b",
                r"inválid",
                r"\binvalid",
                r"recusad",
            )
            if any(re.search(pattern, lower) for pattern in strong_error):
                return "activity_step_error"
            return "ffmpeg_command"
        error_patterns = (
            r"\berro\b",
            r"\bfalha\b",
            r"\bfalhou\b",
            r"não consegui",
            r"não foi possível",
            r"não foi possivel",
            r"\brecusad",
            r"inválid",
            r"\binvalid",
            r"^http [45]\d{2}",
            r"falhou",
            r"fechou a conexão",
            r"conexão fechada",
            r"conexao fechada",
            r"retornou código",
            r"resposta vazia",
            r"gravação vazia",
            r"sem conteúdo",
            r"nenhum microfone",
            r"não há microfone",
            r"não foi encontrad",
            r"não foi criad",
            r"não existe",
        )
        if any(re.search(pattern, lower) for pattern in error_patterns):
            return "activity_step_error"
        warning_patterns = (
            r"reconectando",
            r"desconectad",
            r"não enviou uma confirmação",
            r"não havia conexão ativa",
            r"sem áudio foi gravado",
            r"não concluiu dentro do tempo",
            r"mantive o texto parcial",
            r"não foi possível confirmar",
            r"\baguarde\b",
            r"cancelad",
            r"^parâmetros",
        )
        if any(re.search(pattern, lower) for pattern in warning_patterns):
            return "warning"
        success_patterns = (
            r"concluíd",
            r"finalizad",
            r"requisitad",
            r"gerad",
            r"\bpront",
            r"salvamento",
            r"baixad",
            r"atualizad",
            r"^reconectou",
            r"^gravando",
            r"^gravando pelo",
            r"^conectando",
            r"^conectado",
            r"^enviando",
            r"^ouvindo",
            r"pausada",
            r"^transcrição concluída",
        )
        if any(re.search(pattern, lower) for pattern in success_patterns):
            return "activity_step_done"
        return None

    def _append_activity_log(self, message: str, tag: str | None = None, *, raw: bool = False):
        if not raw:
            message = self._compact_activity_message(message)
        if not message or not getattr(self, "activity_log", None):
            return
        self.activity_log.configure(state="normal")
        if "activity_step_done" not in self.activity_log.tag_names():
            self.activity_log.tag_configure("activity_step_done", foreground="#16833a")
        if "activity_step_error" not in self.activity_log.tag_names():
            self.activity_log.tag_configure("activity_step_error", foreground="#b3261e")
        if "vad_total" not in self.activity_log.tag_names():
            self.activity_log.tag_configure("vad_total", foreground="#0a7a2f")
        if "warning" not in self.activity_log.tag_names():
            self.activity_log.tag_configure("warning", foreground="#a65300")
        if "ffmpeg_command" not in self.activity_log.tag_names():
            self.activity_log.tag_configure("ffmpeg_command", foreground="#c99a2e")
        for part in message.splitlines():
            line = f"{time.strftime('%H:%M:%S')}  {part}\n"
            self.activity_log.insert(END, line, tag or self._log_message_tag(part))
        self.activity_log.see(END)
        self.activity_log.configure(state="disabled")

    def _update_activity_line(self, key: str, message: str, tag: str | None = None):
        """Linha viva do activity log: atualiza a MESMA linha (por chave) sem criar novas."""
        box = getattr(self, "activity_log", None)
        if box is None or not box.winfo_exists():
            return
        box.configure(state="normal")
        if "vad_total" not in box.tag_names():
            box.tag_configure("vad_total", foreground="#0a7a2f")
        line_tag = f"phase:{key}"
        line = f"{time.strftime('%H:%M:%S')}  {message}\n"
        try:
            box.delete(f"{line_tag}.first", f"{line_tag}.last")
        except tk.TclError:
            pass
        if tag:
            box.insert("end", line, (line_tag, tag))
        else:
            box.insert("end", line, line_tag)
        box.see("end")
        box.configure(state="disabled")

    def _render_sync_file_line(self, path: str, display: str, tag: str | None) -> None:
        """Atualiza a linha viva de um arquivo do download (padrão do VAD).

        Cada arquivo tem uma TAG única: a atualização remove TODO o texto
        anterior da tag (tag.first/tag.last) e insere a linha nova no fim —
        sem depender da gravidade de marcas, que não segura a linha no
        início. Ao concluir, recebe a tag verde.
        """
        box = getattr(self, "activity_log", None)
        if box is None or not box.winfo_exists():
            return
        box.configure(state="normal")
        if "vad_total" not in box.tag_names():
            box.tag_configure("vad_total", foreground="#0a7a2f")
        line_tag = f"syncfile:{path}"
        if display == "100%":
            line = f"{time.strftime('%H:%M:%S')}  Baixando {path}\n"
        else:
            line = f"{time.strftime('%H:%M:%S')}  Baixando {path} - {display}\n"
        try:
            box.delete(f"{line_tag}.first", f"{line_tag}.last")
        except tk.TclError:
            pass
        box.insert("end", line, (line_tag, tag or ()))
        if display == "100%" and tag:
            self._sync_file_marks.pop(path, None)
        box.see("end")
        box.configure(state="disabled")

    def _copy_ffmpeg_command_block(self, box) -> bool:
        """Copia todos os comandos do bloco FFmpeg do log, um por linha.

        O cabecalho ("Comandos FFmpeg:") e as linhas em branco usadas apenas
        para separacao visual ficam fora da copia; o prefixo "$ " tambem sai.
        """
        ranges = box.tag_ranges(FFMPEG_COMMAND_BLOCK_TAG)
        if len(ranges) < 2:
            return False
        commands = []
        for line in box.get(str(ranges[0]), str(ranges[-1])).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("Comandos FFmpeg"):
                continue
            commands.append(stripped[2:] if stripped.startswith("$ ") else stripped)
        if not commands:
            return False
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(commands))
        return True

    def _copy_params_block(self, box, block_tag: str) -> bool:
        """Copia a requisição inteira do bloco de parâmetros em uma só linha."""
        ranges = box.tag_ranges(block_tag)
        if len(ranges) < 2:
            return False
        single = params_block_single_line(box.get(str(ranges[0]), str(ranges[-1])))
        if not single:
            return False
        self.root.clipboard_clear()
        self.root.clipboard_append(single)
        return True

    def _append_params_block(self, title: str, params) -> None:
        """Insere bloco de parâmetros: tudo amarelo + tag única do bloco.

        A tag única permite copiar a requisição inteira com um clique em
        qualquer linha do bloco (ver _activity_log_click).
        """
        box = getattr(self, "activity_log", None)
        if box is None or not box.winfo_exists():
            return
        self._params_block_seq = int(getattr(self, "_params_block_seq", 0) or 0) + 1
        block_tag = f"{PARAMS_BLOCK_TAG_PREFIX}{self._params_block_seq}"
        if "warning" not in box.tag_names():
            box.tag_configure("warning", foreground="#a65300")
        text = format_ws_params_block(title, params)
        box.configure(state="normal")
        for part in text.splitlines():
            line = f"{time.strftime('%H:%M:%S')}  {part}\n"
            box.insert(END, line, ("warning", block_tag))
        box.see(END)
        box.configure(state="disabled")

    def _activity_log_click(self, event):
        """Clique em linha amarela/vermelha do log copia o texto da mensagem."""
        box = getattr(self, "activity_log", None)
        if box is None or not box.winfo_exists():
            return
        try:
            index = box.index(f"@{event.x},{event.y}")
            tags = set(box.tag_names(index))
            # O bloco de comandos das ferramentas FFmpeg copia inteiro.
            if FFMPEG_COMMAND_BLOCK_TAG in tags and self._copy_ffmpeg_command_block(box):
                return
            # Bloco de parâmetros: qualquer linha copia a requisição inteira.
            block_tags = [tag for tag in tags if tag.startswith(PARAMS_BLOCK_TAG_PREFIX)]
            if block_tags and self._copy_params_block(box, block_tags[0]):
                return
            # Amarelo: warning, activity_step_warning, ffmpeg_command.
            # Vermelho: error, activity_step_error.
            if tags & {
                "activity_step_error",
                "activity_step_warning",
                "warning",
                "ffmpeg_command",
                "error",
            }:
                start = box.index(f"{index} linestart")
                end = box.index(f"{index} lineend")
                text = box.get(start, end).strip()
                if text:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(text)
        except tk.TclError:
            pass

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
            request = urllib.request.Request(
                f"https://{R2_PUBLIC_HOST}/sync_manifest.json",
                headers={"User-Agent": "SigUpdater/2.0 (+https://github.com/spigknot/SIG-Windows)"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
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
                self._queue("update_check_error", f"não foi possível consultar o R2 ({exc})")
            else:
                self._queue("activity", f"Atualização: não foi possível consultar o R2 ({exc}).")

    def install_available_update(self) -> None:
        if not self.available_update_sync or self.update_installing:
            return
        ffmpeg_running = bool(getattr(self, "ffmpeg_tools", None) and self.ffmpeg_tools.running)
        if self.running or self.live_state != "idle" or self.normal_recording or self.assistant_busy or ffmpeg_running:
            messagebox.showinfo("sig", "Aguarde a tarefa em andamento terminar antes de atualizar.")
            return
        self.update_installing = True
        self.update_button.configure(state="disabled")
        self.update_button_var.set("Baixando arquivos...")
        self.update_install_thread = threading.Thread(
            target=self._sync_download_worker,
            args=(self.available_update_sync.copy(),),
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

                    if not entry.get("github_url"):
                        raise RuntimeError(f"manifesto R2 sem URL de download para: {path}")
                    digest = download_github_url(
                        entry["github_url"], destination, progress_callback=on_progress
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
        # Prefira a cópia recém-baixada. Isso é necessário para que correções
        # do próprio updater entrem em vigor durante a mesma atualização que as
        # entrega (bootstrap); usar sempre a cópia instalada deixaria o fluxo
        # preso em bugs já corrigidos antes de ela conseguir substituir-se.
        staged_updater = staged / "SigUpdater.exe"
        updater_path = (
            staged_updater
            if staged_updater.is_file()
            else app_base_dir() / "SigUpdater.exe"
        )
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
        self.diarias_tab_button = tk.Label(
            tab_bar,
            text="Diárias",
            width=tab_width,
            height=1,
            borderwidth=1,
            relief="solid",
            font=tab_font,
            cursor="hand2",
        )
        self.qrcode_tab_button = tk.Label(
            tab_bar,
            text="QR Code",
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
        self.diarias_tab_button.pack(side=LEFT, padx=(4, 0))
        self.qrcode_tab_button.pack(side=LEFT, padx=(4, 0))
        self.live_tab_button.bind("<Button-1>", lambda _event: self.select_main_tab("live"))
        self.files_tab_button.bind("<Button-1>", lambda _event: self.select_main_tab("files"))
        self.imei_tab_button.bind("<Button-1>", lambda _event: self.select_main_tab("imei"))
        self.ffmpeg_tab_button.bind("<Button-1>", lambda _event: self.select_main_tab("ffmpeg"))
        self.qualification_tab_button.bind(
            "<Button-1>", lambda _event: self.select_main_tab("qualification")
        )
        self.diarias_tab_button.bind(
            "<Button-1>", lambda _event: self.select_main_tab("diarias")
        )
        self.qrcode_tab_button.bind(
            "<Button-1>", lambda _event: self.select_main_tab("qrcode")
        )
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
        self.activity_log.bind("<Button-1>", self._activity_log_click)

        self.live_tab = ttk.Frame(self.tab_content, padding=(14, 2, 14, 14))
        self.files_tab = ttk.Frame(self.tab_content, padding=14)
        self.assistant_tab = ttk.Frame(self.tab_content, padding=14)
        self.imei_tab = ttk.Frame(self.tab_content, padding=14)
        self.ffmpeg_tab = ttk.Frame(self.tab_content, padding=14)
        self.qualification_tab = ttk.Frame(self.tab_content, padding=14)
        self.diarias_tab = ttk.Frame(self.tab_content, padding=14)
        self.qrcode_tab = ttk.Frame(self.tab_content, padding=14)
        ttk.Label(
            self.diarias_tab,
            text="Diárias — conteúdo em desenvolvimento.",
            style="Muted.TLabel",
        ).pack(anchor="w")

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
        self.live_diarize_check = ttk.Checkbutton(
            self.live_grok_controls,
            text="Diarização",
            variable=self.live_diarize_var,
            command=lambda: self._set_activity_status(
                "Diarização ativada." if self.live_diarize_var.get() else "Diarização desativada.",
                log=False,
            ),
        )
        self.live_diarize_check.pack(side=LEFT)
        self.live_diarize_help = self._make_help_marker(
            self.live_grok_controls, self.show_live_diarization_help
        )
        self.live_diarize_help.pack(side=LEFT, padx=(4, 8))
        self.live_language_button = ttk.Menubutton(self.live_grok_controls, textvariable=self.live_language_label_var, width=11)
        self.live_language_menu = tk.Menu(self.live_language_button, tearoff=False)
        for code, label in LIVE_LANGUAGES:
            self.live_language_menu.add_command(label=label, command=lambda selected=code: self._set_live_language(selected))
        self.live_language_button.configure(menu=self.live_language_menu)
        self.live_language_button.pack(side=LEFT)
        # Seletor "Keywords" da tela de Ocorrência (WS): "Não" (desligado) ou um
        # dos perfis cadastrados. Mesmo valor da aba Transcrição.
        self.live_keywords_label_var = StringVar(value=f"Keywords: {KEYWORDS_OFF_LABEL}")
        self.live_keywords_button = ttk.Menubutton(
            self.live_grok_controls,
            textvariable=self.live_keywords_label_var,
            width=16,
        )
        self.live_keywords_menu = tk.Menu(self.live_keywords_button, tearoff=False)
        self.live_keywords_button.configure(menu=self.live_keywords_menu)
        self.live_keywords_button.pack(side=LEFT, padx=(10, 0))
        self.live_keywords_help = self._make_help_marker(
            self.live_grok_controls, lambda: self._open_keywords_help()
        )
        self.live_keywords_help.pack(side=LEFT, padx=(4, 0))
        self.live_grok_controls.pack(side=LEFT)
        self.live_top_spacer = ttk.Frame(live_top)
        self.live_top_spacer.pack(side=LEFT, fill=X, expand=True)
        # Cada microfone fica numa coluna vertical com um slot superior de
        # altura fixa, para os três círculos continuarem alinhados. O slot da
        # coluna vermelha abriga o botão de reenvio do áudio integral por
        # REST: ele aparece sempre na linha de cima do microfone vermelho,
        # centralizado na mesma coluna (sem overlay nem place() flutuante).
        self.live_normal_mic_column = ttk.Frame(live_top)
        self.live_normal_mic_column.pack(side=LEFT, padx=(0, 8))
        self.live_normal_mic_top_slot = ttk.Frame(
            self.live_normal_mic_column, width=44, height=LIVE_RECOVERY_SLOT_HEIGHT
        )
        self.live_normal_mic_top_slot.pack(side=TOP)
        self.live_normal_mic_top_slot.pack_propagate(False)
        self.live_normal_mic_canvas = Canvas(self.live_normal_mic_column, width=44, height=44, highlightthickness=0, background="#f4f7f6")
        self.live_normal_mic_canvas.pack(side=TOP)
        self.live_normal_mic_canvas.bind("<Button-1>", lambda _event: self.start_normal_live_recording())
        self._draw_normal_live_mic_button()
        self.live_pause_column = ttk.Frame(live_top)
        self.live_pause_column.pack(side=LEFT, padx=(0, 8))
        self.live_pause_top_slot = ttk.Frame(
            self.live_pause_column, width=44, height=LIVE_RECOVERY_SLOT_HEIGHT
        )
        self.live_pause_top_slot.pack(side=TOP)
        self.live_pause_top_slot.pack_propagate(False)
        self.live_pause_canvas = Canvas(self.live_pause_column, width=44, height=44, highlightthickness=0, background="#f4f7f6")
        self.live_pause_canvas.pack(side=TOP)
        self.live_pause_canvas.bind("<Button-1>", lambda _event: self.toggle_live_mic())
        self.live_mic_column = ttk.Frame(live_top)
        self.live_mic_column.pack(side=LEFT, padx=(0, 8))
        self.live_recover_audio_slot = ttk.Frame(
            self.live_mic_column, width=44, height=LIVE_RECOVERY_SLOT_HEIGHT
        )
        self.live_recover_audio_slot.pack(side=TOP)
        self.live_recover_audio_slot.pack_propagate(False)
        self.live_recover_audio_button = ttk.Button(
            self.live_recover_audio_slot,
            image=self.recover_audio_icon,
            style="Recover.TButton",
            command=self.recover_live_integral_audio,
        )
        create_tooltip(
            self.live_recover_audio_button,
            "Reenviar o áudio integral ao Grok por REST",
        )
        self.live_mic_stack = ttk.Frame(self.live_mic_column, width=44, height=44)
        self.live_mic_stack.pack(side=TOP)
        self.live_mic_stack.pack_propagate(False)
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
        self.live_qualification_organize_button = ttk.Button(
            self.live_qualification_actions,
            text="Organizar",
            style="Action.TButton",
            width=9,
            command=self.request_organize_live_qualification,
        )
        self.live_qualification_clear_button = self._make_editor_icon_button(
            self.live_qualification_actions,
            self.clear_icon,
            "Limpar",
            lambda: self.clear_live_editor("qualification"),
        )
        self.live_qualification_fields_button = self._make_editor_icon_button(
            self.live_qualification_actions,
            self.gear_icon,
            "Campos da qualificação",
            self.open_live_qualification_fields_window,
        )
        self.live_qualification_fields_button.configure(state="disabled")
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
            width=74,
            height=222,
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
            holder.pack(side=TOP, pady=(0, 8))
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
        # A seleção de partes está temporariamente fora da interface.
        self.assistant_parts_button.pack_forget()
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
        self._build_qrcode_tab()

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

        # Botão "Modelos": multi-seleção de modelos de transcrição (menu).
        self.files_models_button = ttk.Menubutton(
            options2,
            text="Modelos",
        )
        self.files_models_menu = tk.Menu(self.files_models_button, tearoff=0, postcommand=self._populate_models_menu)
        self.files_models_button.configure(menu=self.files_models_menu)
        self.files_models_button.pack(side=LEFT, padx=(16, 0))

        # Idioma do lote, logo à direita do botão "Modelos" (mesmo padrão do
        # seletor da aba Ocorrência). Aqui a opção é genérica (auto/pt/en/es):
        # na hora da requisição ela é traduzida para o valor próprio de CADA
        # modelo marcado — nunca um parâmetro único para todos.
        self.files_language_button = ttk.Menubutton(
            options2,
            textvariable=self.files_language_label_var,
            width=11,
        )
        self.files_language_menu = tk.Menu(self.files_language_button, tearoff=False)
        for option in TRANSCRIPTION_LANGUAGE_OPTIONS:
            self.files_language_menu.add_command(
                label=option,
                command=lambda selected=option: self._set_files_language(selected),
            )
        self.files_language_button.configure(menu=self.files_language_menu)
        self.files_language_button.pack(side=LEFT, padx=(8, 0))
        # Seletor "Keywords" da aba Transcrição (REST): "Não" (desligado) ou um
        # dos perfis cadastrados nas Configurações.
        self.files_keywords_button = ttk.Menubutton(
            options2,
            textvariable=self.files_keywords_label_var,
            width=16,
        )
        self.files_keywords_menu = tk.Menu(self.files_keywords_button, tearoff=False)
        self.files_keywords_button.configure(menu=self.files_keywords_menu)
        self.files_keywords_button.pack(side=LEFT, padx=(10, 0))
        # "?" ao lado: limites reais de termos/caracteres por modelo
        # e aviso de falso positivo (contexto forense).
        self.files_keywords_help = self._make_help_marker(
            options2, lambda: self._open_keywords_help()
        )
        self.files_keywords_help.pack(side=LEFT, padx=(4, 0))
        self._rebuild_keywords_menus()
        self._refresh_files_language_label()

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
        self.tree.bind("<Delete>", self._remove_selected_files)
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

    def _build_qrcode_tab(self) -> None:
        """Monta a tela de geracao de QR Code a partir de um link."""
        frame = ttk.Frame(self.qrcode_tab, width=900)
        frame.pack(fill=X, anchor="n")

        ttk.Label(frame, text="QR Code", style="Muted.TLabel").pack(anchor="w", pady=(16, 4))

        link_row = ttk.Frame(frame)
        link_row.pack(fill=X)
        ttk.Label(link_row, text="Link:").pack(side=LEFT, padx=(0, 8))
        self.qrcode_link_entry = ttk.Entry(
            link_row,
            textvariable=self.qrcode_link_var,
            font=("Segoe UI", 10),
        )
        self.qrcode_link_entry.pack(side=LEFT, fill=X, expand=True)
        self.qrcode_link_entry.bind("<Return>", lambda _event: self.generate_qrcode())
        self._make_editor_icon_button(
            link_row, self.paste_icon, "Colar", self.paste_qrcode_link
        ).pack(side=LEFT, padx=(8, 0))
        self._make_editor_icon_button(
            link_row, self.clear_icon, "Limpar", self.clear_qrcode
        ).pack(side=LEFT, padx=(4, 0))
        self.qrcode_generate_button = ttk.Button(
            link_row,
            text="Gerar QR code",
            style="Action.TButton",
            width=15,
            command=self.generate_qrcode,
        )
        self.qrcode_generate_button.pack(side=LEFT, padx=(10, 0))

        shorten_row = ttk.Frame(frame)
        shorten_row.pack(fill=X, pady=(8, 0))
        self.qrcode_shorten_check = ttk.Checkbutton(
            shorten_row,
            text="Encurtar link",
            variable=self.qrcode_shorten_var,
            command=self._qrcode_shorten_toggled,
        )
        self.qrcode_shorten_check.pack(side=LEFT)
        ttk.Label(shorten_row, text="Alias (opcional):").pack(side=LEFT, padx=(14, 6))
        self.qrcode_alias_entry = ttk.Entry(
            shorten_row,
            textvariable=self.qrcode_alias_var,
            font=("Segoe UI", 10),
            width=30,
        )
        self.qrcode_alias_entry.pack(side=LEFT)
        self.qrcode_alias_entry.bind("<Return>", lambda _event: self.generate_qrcode())
        self.qrcode_alias_entry.configure(state="disabled")

        self.qrcode_shortened_row = ttk.Frame(frame)
        ttk.Label(self.qrcode_shortened_row, text="Encurtado:").pack(side=LEFT)
        self.qrcode_shortened_entry = ttk.Entry(
            self.qrcode_shortened_row,
            textvariable=self.qrcode_shortened_var,
            font=("Segoe UI", 10),
            state="readonly",
        )
        self.qrcode_shortened_entry.pack(side=LEFT, fill=X, expand=True, padx=(8, 8))
        self.qrcode_shortened_copy_button = self._make_editor_icon_button(
            self.qrcode_shortened_row, self.copy_icon, "Copiar", self.copy_shortened_link
        )
        self.qrcode_shortened_copy_button.pack(side=LEFT)
        self.qrcode_shortened_copy_button.configure(state="disabled")

        content = ttk.Frame(frame)
        self.qrcode_content = content
        content.pack(anchor="w", pady=(18, 0))

        self.qrcode_canvas = Canvas(
            content,
            width=340,
            height=340,
            highlightthickness=0,
            borderwidth=1,
            relief="solid",
            background="#ffffff",
        )
        self.qrcode_canvas.pack(side=LEFT)

        self.qrcode_actions_frame = ttk.Frame(content)
        self.qrcode_actions_frame.pack(side=LEFT, padx=(16, 0), anchor="n")

        def qrcode_action_button(text, image, command):
            holder = ttk.Frame(self.qrcode_actions_frame, width=66, height=66)
            holder.pack(side=TOP, pady=(0, 8))
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

        self.qrcode_copy_button = qrcode_action_button(
            "Copiar", self.document_copy_icon, self.copy_qrcode_image
        )
        self.qrcode_copy_button.configure(state="disabled")

        ttk.Label(
            frame,
            textvariable=self.qrcode_status_var,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(12, 0))
        self._draw_qrcode_placeholder()

    def _draw_qrcode_placeholder(self, message: str = "O QR Code aparece aqui.") -> None:
        canvas = getattr(self, "qrcode_canvas", None)
        if canvas is None:
            return
        width = int(canvas["width"])
        height = int(canvas["height"])
        canvas.delete("all")
        canvas.create_text(
            width / 2,
            height / 2,
            text=message,
            fill="#8a918e",
            font=("Segoe UI", 10),
            width=width - 40,
            justify="center",
        )

    def _render_qrcode(self) -> None:
        code = self.qrcode
        canvas = self.qrcode_canvas
        if code is None:
            self._draw_qrcode_placeholder()
            return
        canvas_size = int(canvas["width"])
        # Conta as margens brancas para caber inteiro na area de exibicao.
        # Sem piso artificial: versoes altas (v23+) precisam de escala menor
        # para nao estourar o canvas e cortar o QR Code.
        scale = max(1, canvas_size // (code.size + 8))
        image = code.to_image(scale=scale, border=4)
        self.qrcode_photo = ImageTk.PhotoImage(image, master=self.root)
        canvas.delete("all")
        offset = (canvas_size - image.width) // 2
        canvas.create_image(offset, offset, anchor="nw", image=self.qrcode_photo)

    def generate_qrcode(self) -> None:
        link = self.qrcode_link_var.get().strip()
        if not link:
            self._append_activity_log("QR Code solicitado sem link.", "warning")
            messagebox.showwarning(
                "QR Code", "Cole um link antes de gerar o QR Code.", parent=self.root
            )
            self.qrcode_link_entry.focus_set()
            return
        if self.qrcode_shorten_var.get():
            self._start_shorten_flow(link)
            return
        self._generate_qrcode_now(link)

    def _generate_qrcode_now(self, link: str) -> None:
        try:
            code = qr_encoder.QrCode.encode_text(link, "M")
        except qr_encoder.QrCapacityError as exc:
            self._set_activity_status("QR Code não gerado: conteúdo longo demais.", log=False)
            self._append_activity_log(
                "QR Code não gerado: conteúdo longo demais.", "activity_step_error"
            )
            messagebox.showerror("QR Code", str(exc), parent=self.root)
            return
        except Exception as exc:
            self._set_activity_status(f"QR Code ERRO: {exc}", log=False)
            self._append_activity_log(f"QR Code não gerado: {exc}", "activity_step_error")
            messagebox.showerror(
                "QR Code",
                f"Não consegui gerar o QR Code.\n\nDetalhe: {exc}",
                parent=self.root,
            )
            return
        self.qrcode = code
        self._render_qrcode()
        self.qrcode_copy_button.configure(state="normal")
        # Nenhum texto de status abaixo do QR Code: a confirmação fica no log.
        self.qrcode_status_var.set("")
        self._set_activity_status("QR Code solicitado.", log=False)
        self._append_activity_log("QR Code solicitado", "activity_step_done")

    def copy_qrcode_image(self) -> None:
        if self.qrcode is None:
            self._append_activity_log("Gere o QR Code antes de copiar.", "warning")
            messagebox.showwarning(
                "Copiar", "Gere o QR Code antes de copiar.", parent=self.root
            )
            return
        try:
            qr_encoder.copy_image_to_windows_clipboard(self.qrcode.to_image(scale=14, border=4))
        except Exception as exc:
            self._set_activity_status(f"Cópia do QR Code falhou: {exc}", log=False)
            self._append_activity_log(f"QR Code não copiado: {exc}", "activity_step_error")
            messagebox.showerror(
                "Copiar",
                f"Não consegui copiar a imagem.\n\nDetalhe: {exc}",
                parent=self.root,
            )
            return
        self._set_activity_status("QR Code copiado.", log=False)
        self._append_activity_log("QR Code copiado", "activity_step_done")

    def paste_qrcode_link(self) -> None:
        try:
            pasted = self.root.clipboard_get().strip()
        except Exception:
            return
        if not pasted:
            return
        self.qrcode_link_var.set(pasted)
        self._set_activity_status("Link colado.", log=False)
        self._append_activity_log("Link colado", "activity_step_done")

    def clear_qrcode(self) -> None:
        if (
            not self.qrcode_link_var.get().strip()
            and not self.qrcode_alias_var.get().strip()
            and not self.qrcode_shortened_var.get().strip()
            and self.qrcode is None
        ):
            return
        if not messagebox.askyesno(
            "sig", "Deseja limpar o QR Code atual?", parent=self.root
        ):
            return
        self.qrcode_link_var.set("")
        self.qrcode_alias_var.set("")
        self.qrcode_shortened_var.set("")
        self.qrcode = None
        self.qrcode_photo = None
        self._draw_qrcode_placeholder()
        self.qrcode_copy_button.configure(state="disabled")
        if self.qrcode_shortened_copy_button is not None:
            self.qrcode_shortened_copy_button.configure(state="disabled")
            self.qrcode_shortened_row.pack_forget()
        self.qrcode_status_var.set("Cole um link e gere o QR Code.")
        self._set_activity_status("QR Code limpo.", log=False)

    def _qrcode_shorten_toggled(self) -> None:
        state = "normal" if self.qrcode_shorten_var.get() else "disabled"
        if self.qrcode_alias_entry is not None:
            self.qrcode_alias_entry.configure(state=state)

    def copy_shortened_link(self) -> None:
        text = self.qrcode_shortened_var.get().strip()
        if not text:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception as exc:
            self._set_activity_status(f"Cópia do link falhou: {exc}", log=False)
            self._append_activity_log(
                f"Link encurtado não copiado: {exc}", "activity_step_error"
            )
            messagebox.showerror(
                "Copiar",
                f"Não consegui copiar o link.\n\nDetalhe: {exc}",
                parent=self.root,
            )
            return
        self._set_activity_status("Link encurtado copiado.", log=False)
        self._append_activity_log("Link encurtado copiado", "activity_step_done")

    def _start_shorten_flow(self, link: str) -> None:
        parsed = urlparse(link)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            self._append_activity_log(
                "Link não encurtado: use http:// ou https://.", "activity_step_error"
            )
            messagebox.showwarning(
                "Encurtar link",
                "O link precisa começar com http:// ou https:// para ser encurtado.",
                parent=self.root,
            )
            return
        if self.qrcode_shorten_busy:
            self._set_activity_status("Encurtamento em andamento...", log=False)
            return
        alias = self.qrcode_alias_var.get().strip()
        self.qrcode_shorten_busy = True
        self.qrcode_generate_button.configure(state="disabled")
        self._begin_activity_step("qrcode:shorten", "Encurtando link")
        self.qrcode_shorten_started = time.perf_counter()
        threading.Thread(
            target=self._shorten_worker, args=(link, alias), daemon=True
        ).start()

    def _shorten_worker(self, link: str, alias: str) -> None:
        try:
            params = [("url", link)]
            if alias:
                params.append(("alias", alias))
            url = "https://tinyurl.com/api-create.php?" + urlencode(params)
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "SIG-Windows/2.0 (+https://github.com/spigknot/SIG-Windows)"
                },
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read(64 * 1024).decode("utf-8", errors="replace").strip()
            if not body.startswith("http://") and not body.startswith("https://"):
                self._queue("qrcode_shorten_error", "TinyURL não devolveu um link válido.")
                return
            self._queue("qrcode_shortened", body)
        except urllib.error.HTTPError as exc:
            if exc.code == 422:
                detail = "Alias indisponível: escolha outro ou deixe em branco."
            elif exc.code == 400:
                detail = "TinyURL recusou o link (verifique se a URL é válida)."
            else:
                detail = f"TinyURL recusou o pedido (HTTP {exc.code})."
            self._queue("qrcode_shorten_error", detail)
        except Exception as exc:
            self._queue("qrcode_shorten_error", f"Falha ao encurtar: {exc}")

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
        model_config = selected_text_model_for(settings, "qualification")
        self._begin_activity_step(
            "assistant:qualification",
            f"Qualificação requisitada - {assistant_request_model_label(model_config)}",
        )
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
        except Exception:
            pass

    def _on_live_top_configure(self, _event=None):
        self._align_activity_log()

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
            getattr(self, "diarias_tab", None),
            getattr(self, "qrcode_tab", None),
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
            self.diarias_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qrcode_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
        elif tab_name == "imei":
            self.imei_tab.pack(fill=BOTH, expand=True)
            self.live_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.files_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.imei_tab_button.configure(background=active_bg, foreground=active_fg)
            self.ffmpeg_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qualification_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.diarias_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qrcode_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
        elif tab_name == "ffmpeg":
            self.ffmpeg_tab.pack(fill=BOTH, expand=True)
            self.live_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.files_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.imei_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.ffmpeg_tab_button.configure(background=active_bg, foreground=active_fg)
            self.qualification_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.diarias_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qrcode_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
        elif tab_name == "qualification":
            self.qualification_tab.pack(fill=BOTH, expand=True)
            self.live_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.files_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.imei_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.ffmpeg_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qualification_tab_button.configure(background=active_bg, foreground=active_fg)
            self.diarias_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qrcode_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
        elif tab_name == "diarias":
            self.diarias_tab.pack(fill=BOTH, expand=True)
            self.live_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.files_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.imei_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.ffmpeg_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qualification_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.diarias_tab_button.configure(background=active_bg, foreground=active_fg)
            self.qrcode_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
        elif tab_name == "qrcode":
            self.qrcode_tab.pack(fill=BOTH, expand=True)
            self.live_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.files_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.imei_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.ffmpeg_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qualification_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.diarias_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qrcode_tab_button.configure(background=active_bg, foreground=active_fg)
        else:
            self.live_tab.pack(fill=BOTH, expand=True)
            self.live_tab_button.configure(background=active_bg, foreground=active_fg)
            self.files_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.imei_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.ffmpeg_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qualification_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.diarias_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.qrcode_tab_button.configure(background=inactive_bg, foreground=inactive_fg)
            self.root.after_idle(self._position_live_parts_button)

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
        self.live_assistant_names = []
        menus = (
            (self.live_parts_menu, self.live_assistant_part_var),
            (self.live_parts_menu_2, self.live_assistant_part_var_2),
        )
        for menu, variable in menus:
            menu.delete(0, END)
            variable.set("")

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
            # O seletor de partes está fora da interface; mantenha o widget
            # não mapeado para compatibilidade com estados antigos.
            parts_button.place_forget()
            recover_button.place(x=0, y=0)
            left_edge = recover_button.winfo_x() + recover_button.winfo_width()
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
        # O botão de campos (engrenagem) fica imediatamente à esquerda do
        # Limpar: [Colar] [Copiar] [Limpar] [engrenagem] (da direita p/ esquerda).
        for button in (
            self.live_qualification_paste_button,
            self.live_qualification_copy_button,
            self.live_qualification_clear_button,
            self.live_qualification_fields_button,
        ):
            right_x -= button.winfo_reqwidth()
            button.place(x=right_x, y=center_y, anchor="w")
            right_x -= 4
        # Botão verde "Organizar", com o CENTRO na metade da distância
        # horizontal entre o Recuperar (esquerda) e a Engrenagem (direita).
        organize = getattr(self, "live_qualification_organize_button", None)
        if organize is not None and organize.winfo_exists():
            left_edge = (
                self.live_qualification_recover_button.winfo_x()
                + self.live_qualification_recover_button.winfo_width()
            )
            right_edge = self.live_qualification_fields_button.winfo_x()
            organize_half = organize.winfo_reqwidth() / 2
            midpoint = (left_edge + right_edge) / 2
            midpoint = min(
                max(organize_half, midpoint),
                max(organize_half, width - organize_half),
            )
            organize.place_forget()
            organize.place(x=midpoint, y=center_y, anchor="center")

    def _document_preview_max_width(self) -> int:
        """Largura máxima da caixa da prévia.

        O stage não pode passar da borda direita do painel e precisa deixar
        vão suficiente à direita para a coluna de ações ficar no meio do
        espaço entre a preview e o log (74px + 8 de respiro a cada lado).
        """
        panel = getattr(self, "live_document_preview_panel", None)
        log = getattr(self, "activity_box", None)
        if panel is None or log is None or not panel.winfo_exists() or not log.winfo_exists():
            return 1120
        try:
            panel_width = max(1, panel.winfo_width())
            gap_to_log = log.winfo_rootx() - panel.winfo_rootx()
            return max(220, min(panel_width - 8, gap_to_log - 74 - 16))
        except Exception:
            return 1120

    def _document_preview_stage_width(self, available_width: int) -> int:
        """Largura da caixa da prévia — SEMPRE a página A4 no tamanho de 100%.

        A caixa representa a largura FÍSICA do papel (A4: 21 cm) no zoom de
        100%, calculada do DPI real do painel. Assim ela é IDÊNTICA antes de
        gerar o documento, depois de gerar e em QUALQUER zoom — o zoom só
        encolhe o conteúdo renderizado dentro da mesma caixa. Nunca usar a
        largura da imagem re-renderizada (depende do zoom e do estado de
        carregamento, causando o 'pulo' da caixa).
        """
        # Largura física do A4 (21 cm) em pixels a 100% no DPI real do painel.
        dpi = _window_physical_dpi(self.root)
        page_width_100 = round(21 / 2.54 * dpi)
        # Imagem inteira + insets laterais (4) + scrollbar (14) + respiro (4).
        needed = page_width_100 + 22
        return max(220, min(available_width, needed))

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
        # A caixa representa SEMPRE a página a 100% (o zoom só encolhe o
        # conteúdo), limitada pelo vão até o log — que guarda a coluna de ações.
        stage_width = self._document_preview_stage_width(self._document_preview_max_width())
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
        # width from the panel's real available width — the box represents
        # always the page at 100% (zoom only shrinks the content) and is
        # limited by the gap to the log, which hosts the actions column.
        stage_width = self._document_preview_stage_width(self._document_preview_max_width())
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

        # A coluna de ações fica no MEIO do espaço entre a borda direita da
        # caixa de preview (stage) e a borda esquerda da caixa de log, com a
        # borda inferior do botão Salvar na linha da borda inferior do log.
        actions = getattr(self, "live_document_actions_frame", None)
        if actions and actions.winfo_ismapped():
            actions.update_idletasks()
            actions_width = max(74, actions.winfo_reqwidth())
            actions_height = max(214, actions.winfo_reqheight())
            log = getattr(self, "activity_box", None)
            if log is not None and log.winfo_exists():
                stage_right_root = stage.winfo_rootx() + stage.winfo_width()
                log_left_root = log.winfo_rootx()
                mid_x_root = (stage_right_root + log_left_root) / 2
                action_x_root = round(mid_x_root - actions_width / 2)
                lo = stage_right_root + 8
                hi = log_left_root - actions_width - 8
                if hi < lo:
                    hi = lo
                action_x_root = max(lo, min(action_x_root, hi))
                action_x = action_x_root - panel.winfo_rootx()
                log_bottom_root = log.winfo_rooty() + log.winfo_height()
                action_y = log_bottom_root - panel.winfo_rooty() - actions_height
            else:
                action_x = stage_width + 8
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
        # A caixa (canvas) tem LARGURA FIXA — a página a 100% — e o zoom
        # apenas encolhe a imagem desenhada DENTRO dela (comportamento de
        # visualizador: a janela não muda, o conteúdo escala). Antes o canvas
        # abraçava a imagem (photo.width()+4) e a caixa inteira encolhia no
        # zoom 25/50%.
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
        # A imagem renderizada define a largura necessária da caixa: re-posiciona
        # o stage para abraçar a página inteira (margens e bordas) no zoom atual.
        self.root.after_idle(self._position_live_document_preview)
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

    def _position_live_parts_button(self):
        self._position_live_parts_buttons()


    def _set_assistant_names(self, names: list[str]):
        self.assistant_names = []
        self.assistant_parts_menu.delete(0, END)
        self.assistant_part_var.set("")

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
            progress_var.set("\n".join(rendered))
            return
        task_labels = {
            "qualification_document": "Qualificando e gerando documento",
            "history": "Redigindo histórico",
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
            "live_qualification_organize_button",
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
        message = history_completion_status(self.assistant_task_states["history"])
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
        self.assistant_task_states.update(history="running", names="idle", statement="idle")
        self.assistant_task_elapsed.update(history=None, names=None, statement=None)
        request_started = time.monotonic()
        self.assistant_task_started_at.update(
            history=request_started,
            names=None,
            statement=None,
        )
        if target == "live" and self.multi_text_model_var.get() and self.multi_text_secondary:
            self.assistant_multi_started_at[("history", 1)] = request_started
            self.assistant_multi_started_at[("history", 2)] = request_started
            history_models = [
                selected_text_model_for(settings, "history"),
                selected_text_model_for(settings, "history", secondary=True),
            ]
            for index, model_config in enumerate(history_models, start=1):
                self._begin_activity_step(
                    f"assistant:history:{index}",
                    f"Histórico {index} requisitado - {assistant_request_model_label(model_config)}",
                )
        else:
            history_model = selected_text_model_for(settings, "history")
            self._begin_activity_step(
                "assistant:history",
                f"Histórico requisitado - {assistant_request_model_label(history_model)}",
            )
        self._set_activity_status("Histórico requisitado", log=False)
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
        history_request = history_user_prompt(material)
        try:
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
            statement_models = [
                selected_text_model_for(settings, "statement"),
                selected_text_model_for(settings, "statement", secondary=True),
            ]
            for index, model_config in enumerate(statement_models, start=1):
                self._begin_activity_step(
                    f"assistant:statement:{index}",
                    f"Oitiva {index} requisitada - {assistant_request_model_label(model_config)}",
                )
        else:
            statement_model = selected_text_model_for(settings, "statement")
            self._begin_activity_step(
                "assistant:statement",
                f"Oitiva requisitada - {assistant_request_model_label(statement_model)}",
            )
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
            canvas.create_line(15, 21, 20, 27, fill="#3ddc66", width=5, capstyle="round")
            canvas.create_line(20, 27, 30, 15, fill="#3ddc66", width=5, capstyle="round")
        else:
            canvas.create_oval(17, 10, 27, 26, fill="#ff4b4b", outline="#ffd0d0", width=2)
            canvas.create_line(22, 26, 22, 33, fill="#ff4b4b", width=3, capstyle="round")
            canvas.create_arc(13, 18, 31, 34, start=200, extent=140, outline="#ff4b4b", width=3, style="arc")
            canvas.create_line(16, 34, 28, 34, fill="#ff4b4b", width=3, capstyle="round")

    def _set_live_audio_recovery_visible(self, visible: bool):
        button = getattr(self, "live_recover_audio_button", None)
        if button is None or not button.winfo_exists():
            return
        button.pack_forget()
        if visible and self.live_audio_recovery_available:
            # O slot acima do microfone vermelho tem tamanho fixo, então o
            # botão aparece sempre centralizado na mesma coluna do microfone.
            button.pack(expand=True)

    @staticmethod
    def _sounddevice_has_input_device(sounddevice_module) -> bool:
        """Consulta novamente o inventário do PortAudio e procura entradas de áudio."""
        try:
            devices = sounddevice_module.query_devices()
            if isinstance(devices, dict):
                devices = [devices]
            return any(
                int((device.get("max_input_channels", 0) or 0)) > 0
                for device in devices
                if hasattr(device, "get")
            )
        except Exception:
            return False

    def _microphone_is_available(self) -> bool:
        try:
            import sounddevice as sd
        except Exception:
            return False
        return self._sounddevice_has_input_device(sd)

    def _refresh_microphone_availability(self):
        """Atualiza a disponibilidade sem exigir que o microfone existisse ao abrir o app."""
        self.microphone_available = self._microphone_is_available()
        try:
            self.microphone_check_after_id = self.root.after(
                1000, self._refresh_microphone_availability
            )
        except Exception:
            self.microphone_check_after_id = None

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
            canvas.create_line(15, 21, 20, 27, fill="#3ddc66", width=5, capstyle="round")
            canvas.create_line(20, 27, 30, 15, fill="#3ddc66", width=5, capstyle="round")
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
        if _kind == "qualification":
            # Marca que o conteúdo atual é resultado de uma requisição de
            # organização (usada pelo botão 'Gerar documento'); é removida
            # quando o usuário edita a caixa manualmente.
            text._qualification_organized = False
            text.bind("<<Modified>>", self._on_qualification_modified, add="+")
        self._restore_live_placeholder(text)
        try:
            text.edit_modified(False)
        except Exception:
            pass
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

    def _set_live_editor(self, kind: str, text: str, *, qualification_organized: bool | None = None):
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
        try:
            widget.edit_modified(False)
        except Exception:
            pass
        if kind == "qualification" and qualification_organized is not None:
            self._set_qualification_organized(qualification_organized)
        elif kind == "qualification":
            # Qualquer outro preenchimento programático (colar, limpar,
            # recuperar) não é uma organização: remove a tag, a menos que o
            # chamador diga explicitamente que o texto veio de organização.
            self._set_qualification_organized(False)
        if self.live_state != "idle" or self.assistant_busy:
            widget.configure(state="disabled")
        if kind in ("transcript", "transcript2") and self.live_state != "idle":
            widget.see(END)
        elif at_end:
            widget.see(END)
        else:
            widget.yview_moveto(top)

    def _on_qualification_modified(self, _event=None):
        """Edição manual do usuário não é uma organização recente: derruba a
        janela de timeout (o texto deixa de ser o resultado da última IA)."""
        widget = getattr(self, "live_qualification_text", None)
        if not widget:
            return
        try:
            if widget.edit_modified():
                widget.edit_modified(False)
                if not self._is_live_placeholder(widget):
                    widget._qualification_organized = False
                    self._qualification_organized_at = None
        except Exception:
            pass

    def _set_qualification_organized(self, organized: bool = True):
        widget = getattr(self, "live_qualification_text", None)
        if widget is not None:
            widget._qualification_organized = bool(organized)
        if organized:
            self._qualification_organized_at = time.monotonic()
        else:
            self._qualification_organized_at = None
        # A engrenagem (seleção de campos) só faz sentido quando existe um
        # JSON da última organização para filtrar.
        button = getattr(self, "live_qualification_fields_button", None)
        if button is not None and button.winfo_exists():
            button.configure(state="normal" if organized else "disabled")

    def qualification_is_organized(self) -> bool:
        """True se a qualificação foi organizada há menos de 60s (janela em
        que o 'Gerar documento' usa o texto atual sem re-organizar)."""
        widget = getattr(self, "live_qualification_text", None)
        if widget is None or self._is_live_placeholder(widget):
            return False
        stamp = self._qualification_organized_at
        if stamp is None:
            return False
        if time.monotonic() - stamp > QUALIFICATION_ORGANIZED_TIMEOUT_S:
            return False
        return True

    def _live_qualification_selected_ids(self) -> set[str]:
        """IDs selecionados nas checkboxes da engrenagem (campos do JSON)."""
        return {
            field_id
            for field_id in LIVE_QUALIFICATION_FIELD_IDS
            if self.live_qualification_field_vars[field_id].get()
        }

    def _refresh_live_qualification_from_fields(self):
        """Recompõe o texto da caixa de qualificação a partir do JSON da
        última organização, respeitando as checkboxes da engrenagem."""
        fields = getattr(self, "_last_live_qualification_fields", None)
        if not fields:
            return
        # Como a função de formatação aceita texto bruto, serializamos o
        # dict já parseado de volta em JSON para reutilizar o mesmo caminho.
        payload = json.dumps(fields, ensure_ascii=False)
        formatted = format_occurrence_qualification(
            payload,
            self.qualification_fields,
            self._live_qualification_selected_ids(),
        )
        if formatted:
            self._set_live_editor(
                "qualification", formatted, qualification_organized=True
            )
            self.last_live_qualification_text = formatted

    def open_live_qualification_fields_window(self):
        """Abre a janela com as checkboxes dos campos do JSON da qualificação."""
        win = getattr(self, "live_qualification_fields_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_force()
            return
        win = Toplevel(self.root)
        win.title("Campos da qualificação")
        win.geometry("560x520")
        win.minsize(420, 320)
        win.transient(self.root)
        self.live_qualification_fields_win = win

        container = ttk.Frame(win, padding=(16, 12))
        container.pack(fill=BOTH, expand=True)

        ttk.Label(
            container,
            text="Escolha os campos do JSON que compõem a qualificação:",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        fields_frame = ttk.Frame(container)
        fields_frame.pack(fill=BOTH, expand=True)
        for column in range(3):
            fields_frame.columnconfigure(column, minsize=160)

        def on_field_changed(_field_id=None):
            self._refresh_live_qualification_from_fields()

        for index, field_id in enumerate(LIVE_QUALIFICATION_FIELD_IDS):
            row, column = divmod(index, 3)
            check = ttk.Checkbutton(
                fields_frame,
                text=LIVE_QUALIFICATION_FIELD_LABELS.get(field_id, field_id),
                variable=self.live_qualification_field_vars[field_id],
                command=lambda fid=field_id: on_field_changed(fid),
            )
            check.grid(row=row, column=column, sticky="w", padx=(0, 18), pady=(0, 6))

        actions = ttk.Frame(container)
        actions.pack(fill=X, pady=(12, 0))
        ttk.Button(
            actions,
            text="Fechar",
            command=win.destroy,
        ).pack(side=RIGHT)
        win.protocol("WM_DELETE_WINDOW", win.destroy)

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
        saved = self.last_live_qualification_text
        if self.live_state != "idle" or self.assistant_busy:
            return
        if self._live_editor_value("qualification") and not messagebox.askyesno(
            "sig", "Deseja sobrescrever o texto atual?", parent=self.root
        ):
            return
        has_fields = bool(self._last_live_qualification_fields)
        self._set_live_editor(
            "qualification",
            saved,
            qualification_organized=True if has_fields else None,
        )
        self._set_activity_status("Última qualificação recuperada.", log=False)

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
        if self.qualification_is_organized():
            # A qualificação já foi organizada (via botão Organizar ou numa
            # geração anterior); usa o texto atual e apenas gera o documento.
            self._generate_occurrence_document_from_current_text()
            return
        # Qualificação ainda não organizada: organiza primeiro e, ao terminar,
        # o fluxo encadeia a geração do documento automaticamente.
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
                    width=74,
                    height=222,
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

    def request_organize_live_qualification(self):
        """Organiza a qualificação (mesma requisição do 'Gerar documento'),
        mas sem gerar o documento em seguida."""
        # Inicia a janela de 60s no CLIQUE: enquanto a requisição roda e por
        # até 60s após, o 'Gerar documento' não re-organiza (o handler de
        # sucesso re-marca o instante ao concluir; falha limpa a janela).
        self._qualification_organized_at = time.monotonic()
        self.request_live_qualification(generate_document=False)

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
        model_config = selected_text_model_for(settings, "qualification")
        self._begin_activity_step(
            "assistant:qualification",
            f"Qualificação requisitada - {assistant_request_model_label(model_config)}",
        )
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

    def _keywords_help_text(self) -> str:
        """Texto da ajuda das Keywords (limites REAIS medidos).

        Formatado para o `messagebox` padrão (mesmo do VAD): parágrafos curtos
        separados por linha em branco, sem depender de fonte monoespaçada.
        """
        termos_deepgram = DEEPGRAM_KEYTERM_TOKEN_BUDGET // estimate_keyterm_tokens("X" * 20)
        return (
            "As keywords aumentam a chance de o modelo escrever os termos "
            "cadastrados. Cada modelo recebe os termos do seu próprio jeito, "
            "então o app usa sempre o limite MAIS RESTRITO — assim o mesmo "
            "termo funciona em todos.\n"
            "\n"
            f"• Até {MAX_STT_KEYWORD_LENGTH} caracteres por termo: o Realtime da "
            "ElevenLabs e o Meta Muse Voice recusam termos maiores.\n"
            f"• Até {MAX_STT_KEYWORDS} termos por perfil.\n"
            "• SÓ OS PRIMEIROS TERMOS SÃO ENVIADOS. A ordem da tabela é a ordem "
            "de prioridade: mantenha os mais importantes no topo. O excedente "
            "não é enviado (o texto do termo nunca é alterado).\n"
            "\n"
            "LIMITES POR MODELO\n"
            "\n"
            f"• Deepgram Nova 3: teto de 500 tokens por requisição — na prática "
            f"uns {termos_deepgram} termos de 20 caracteres (termos curtos vão "
            "além de 100). Acima do teto a API devolve erro e a transcrição do "
            "arquivo falha.\n"
            "• xAI (Grok STT): 100 termos, 50 caracteres cada.\n"
            "• ElevenLabs: 50 caracteres e 1000 termos por arquivo; 20 "
            "caracteres por termo ao vivo (Realtime).\n"
            "• AssemblyAI: cerca de 1000 palavras (cada palavra de uma frase "
            "conta como uma).\n"
            "• Meta Muse Voice: 20 caracteres por termo.\n"
            "• Alibaba Fun ASR: funciona na Ocorrência (ao vivo), via lista "
            "pré-compilada; na Transcrição (arquivo) enviamos a lista, mas a "
            "medição não mostrou mudança no resultado.\n"
            "• servidor (Granite): não usa keywords — nenhum parâmetro é enviado.\n"
            "\n"
            "ATENÇÃO EM TRANSCRIÇÃO POLICIAL\n"
            "\n"
            "As keywords podem fazer o modelo escrever o termo mesmo quando ele "
            "NÃO foi dito. Use poucos termos e bem específicos (nomes, ruas, "
            "apelidos) e sempre confira o áudio antes de tratar a transcrição "
            "como prova: o termo pode ter sido inserido pelo viés do modelo, "
            "não pela fala."
        )

    def _make_help_marker(self, parent, command):
        """O "?" padrão do app — IDÊNTICO ao do VAD.

        Mesmo rótulo, cor, fonte e cursor do marcador do VAD; o clique abre um
        `messagebox` (sem janela própria, sem barra de rolagem, sem caixa de
        texto). Use sempre este helper para novos "?" para a estética não
        divergir entre as telas.
        """
        marcador = tk.Label(
            parent,
            text="?",
            fg="#889493",
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            background="#f4f7f6",
        )
        marcador.bind("<Button-1>", lambda _event: command())
        return marcador

    def _open_keywords_help(self, parent=None):
        """Ajuda das Keywords — mesmo padrão do "?" do VAD (messagebox)."""
        messagebox.showinfo("Keywords", self._keywords_help_text(), parent=parent)

    def show_live_diarization_help(self):
        message = "A diarização tenta identificar interlocutores diferentes. O Grok rotula as falas como Interlocutor 1, Interlocutor 2 e assim por diante."
        if self._current_stt_provider() == "alibaba":
            message += "\n\nDiarização não disponível para Alibaba Fun ASR/Qwen."
        messagebox.showinfo("Diarização", message)

    def _current_stt_provider(self) -> str | None:
        if is_deepgram_transcription(self.settings):
            return "deepgram"
        if is_assemblyai_transcription(self.settings):
            return "assemblyai"
        if is_elevenlabs_transcription(self.settings):
            return "elevenlabs"
        if is_metamuse_transcription(self.settings):
            return "metamuse"
        if is_alibaba_transcription(self.settings):
            return "alibaba"
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
            label = stt_provider_rules.LANGUAGE_LABELS.get(option, option)
            menu.add_command(label=label, command=lambda selected=option: self._set_live_language(selected))
        self.live_language_button.configure(menu=menu)
        mode = language_mode(self.settings, provider)
        custom = language_custom(self.settings, provider)
        shown = custom if mode == "custom" and custom else stt_provider_rules.LANGUAGE_LABELS.get(mode, mode)
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
        shown = stt_provider_rules.LANGUAGE_LABELS.get(code, code)
        self.live_language_label_var.set(f"Idioma: {shown}")
        self._set_activity_status(f"Idioma selecionado: {shown}.", log=False)

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
        provider = self._current_stt_provider()
        diarize_supported = provider is not None and supports_diarize(provider, True)
        if provider is None:
            self.live_grok_controls.pack_forget()
            self.live_diarize_var.set(False)
        else:
            self.live_grok_controls.pack(side=LEFT, before=self.live_top_spacer)
            if self.live_diarize_check is not None:
                if diarize_supported:
                    self.live_diarize_check.configure(state="normal")
                else:
                    # Ex.: Alibaba Fun ASR/Qwen não tem diarização: o seletor
                    # de idioma continua visível, só o checkbox desliga.
                    self.live_diarize_var.set(False)
                    self.live_diarize_check.configure(state="disabled")
        self._rebuild_live_language_menu()
        self._rebuild_keywords_menus()
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
        try:
            import sounddevice as sd
        except Exception as exc:
            messagebox.showerror(
                "sig",
                "Não consegui carregar a captura de microfone.\n"
                "Reinstale o app com a dependência sounddevice embutida.\n\n"
                f"Detalhe: {exc}",
            )
            return
        if not self._sounddevice_has_input_device(sd):
            self.microphone_available = False
            messagebox.showerror(
                "sig",
                "Nenhum microfone de entrada foi encontrado.\n"
                "Conecte um microfone e tente novamente.",
            )
            self.status_var.set("Nenhum microfone de entrada foi encontrado. Conecte um microfone e tente novamente.")
            return
        self.microphone_available = True
        self.settings = load_settings()
        if is_grok_transcription(self.settings) and not self.settings.get("grok_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Grok nas configurações antes de gravar.")
            return
        if is_deepgram_transcription(self.settings) and not self.settings.get("deepgram_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Deepgram nas configurações antes de gravar.")
            return
        if is_metamuse_transcription(self.settings) and not self.settings.get("metamuse_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Meta Muse Voice nas configurações antes de gravar.")
            return
        if is_alibaba_transcription(self.settings) and not self.settings.get("alibaba_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Alibaba Cloud nas configurações antes de gravar.")
            return
        self.normal_record_grok = is_grok_transcription(self.settings)
        self.normal_record_deepgram = is_deepgram_transcription(self.settings)
        self.normal_record_metamuse = is_metamuse_transcription(self.settings)
        self.normal_record_alibaba = is_alibaba_transcription(self.settings)
        self.normal_record_language = (
            deepgram_language_param(self.settings)
            if is_deepgram_transcription(self.settings)
            else grok_language_param(self.settings) or "pt"
        )
        self.normal_record_diarize = (self.normal_record_grok or self.normal_record_deepgram or self.normal_record_metamuse) and bool(
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
        self.status_var.set("Gravando. Clique no botão verde para encerrar gravação")
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
            if getattr(self, "normal_record_metamuse", False):
                record_settings = self.settings.copy()
                if self.normal_record_diarize:
                    record_settings["diarize"] = True
                self._queue(
                    "params_block",
                    "Parâmetros REST (Muse):",
                    metamuse_rest_request_body(
                        bool(record_settings.get("diarize")), record_settings
                    ),
                )
                text = metamuse_rest_transcribe(
                    cancel, record_settings, wav_path, wav_path.with_suffix(".raw")
                )
                if not text.strip():
                    self._queue("status", "Transcrição ao vivo finalizada sem conteúdo")
                else:
                    self._queue("live_payload", text, "", False)
                    self._queue("status", "Transcrição concluída.")
                return
            if getattr(self, "normal_record_alibaba", False):
                self._queue(
                    "params_block",
                    "Parâmetros REST (Alibaba):",
                    alibaba_rest_log_params(self.settings),
                )
                text = alibaba_rest_transcribe(
                    cancel,
                    self.settings.copy(),
                    wav_path,
                    wav_path.with_suffix(".raw"),
                    self._alibaba_vocabulary_for(self.settings, ALIBABA_REST_MODEL),
                )
                if not text.strip():
                    self._queue("status", "Transcrição ao vivo finalizada sem conteúdo")
                else:
                    self._queue("live_payload", text, "", False)
                    self._queue("status", "Transcrição concluída.")
                return
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
                if getattr(self, "normal_record_deepgram", False):
                    self._queue(
                        "params_block",
                        "Parâmetros REST (Deepgram):",
                        urllib.parse.parse_qsl(
                            deepgram_query_string(record_settings), keep_blank_values=True
                        ),
                    )
                elif is_assemblyai_transcription(self.settings):
                    self._queue(
                        "params_block",
                        "Parâmetros REST (AssemblyAI):",
                        transcription_form_fields(record_settings),
                    )
                elif is_elevenlabs_transcription(self.settings):
                    rest_fields = {"model_id": "scribe_v2"}
                    rest_fields.update(transcription_form_fields(record_settings))
                    self._queue("params_block", "Parâmetros REST (ElevenLabs):", rest_fields)
            else:
                fields = {"language": self.normal_record_language, "format": "true", "filler_words": "false"}
                if self.normal_record_diarize:
                    fields["diarize"] = "true"
                self._queue(
                    "params_block",
                    "Parâmetros REST (Grok):" if grok else "Parâmetros REST (servidor):",
                    dict(fields),
                )
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
            if not parsed.text.strip():
                self._queue("status", "Transcrição ao vivo finalizada sem conteúdo")
            else:
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


    def _refresh_server_label(self):
        self.server_var.set("")


    def _refresh_multi_text_visibility(self):
        self.multi_text_model_var.set(False)
        self._refresh_multi_text_layout()

    def _available_multi_transcription_models(self) -> dict[str, str]:
        settings = load_settings()
        available = {}
        for server in read_transcription_servers():
            name = server["name"]
            # Modelos exclusivos de WebSocket/ao vivo (ElevenLabs Scribe
            # realtime e Meta Muse Voice) não aparecem na aba Transcrição:
            # quem os usa é a aba Ocorrência (regra do usuário, 10/09).
            if is_realtime_only_transcription_server(name):
                continue
            if name in {"servidor", "taguai-speech"} and not hostname_online("servidor"):
                continue
            if name == GROK_API_NAME and not plausible_xai_api_key(settings.get("grok_api_key", "")):
                continue
            if name == DEEPGRAM_API_NAME and not settings.get("deepgram_api_key", "").strip():
                continue
            if name == ASSEMBLYAI_API_NAME and not plausible_assemblyai_api_key(settings.get("assemblyai_api_key", "")):
                continue
            if name == ALIBABA_API_NAME and not str(settings.get("alibaba_api_key") or "").strip():
                continue
            available[transcription_server_label(server)] = name
        return available

    def _selected_multi_transcription_model_names(self) -> list[str]:
        return [
            name for name, variable in self.multi_transcription_model_vars.items()
            if variable.get()
        ]

    def _multi_transcription_model_changed(self, name: str):
        self.settings["multi_transcription_models"] = self._selected_multi_transcription_model_names()

    def _populate_models_menu(self):
        """Popula o menu do Menubutton 'Modelos' (postcommand) com a
        multi-seleção de modelos de transcrição."""
        menu = self.files_models_menu
        menu.delete(0, "end")
        if self.running:
            menu.add_command(
                label="Aguarde o lote atual terminar...",
                state="disabled",
            )
            return
        available = self._available_multi_transcription_models()
        if not available:
            menu.add_command(
                label="Nenhum modelo disponível (verifique chaves/servidor)",
                state="disabled",
            )
            return
        selected = set(self._selected_multi_transcription_model_names())
        if not selected:
            # Primeira montagem do menu desde a abertura do app: retoma a
            # seleção salva da aba Transcrição (padrão: apenas "servidor", o
            # Granite NAR local). Entram só os modelos disponíveis agora —
            # modelos só de WebSocket já foram filtrados de `available`.
            saved_settings = load_settings()
            selected.update(
                name
                for name in (saved_settings.get("multi_transcription_models") or [])
                if name in available.values()
            )
            if not selected:
                default = self._default_transcription_model_name()
                if default in available.values():
                    selected.add(default)
        for label, name in available.items():
            variable = BooleanVar(value=name in selected)
            self.multi_transcription_model_vars[name] = variable
            menu.add_checkbutton(
                label=label,
                variable=variable,
                command=lambda selected_name=name: self._multi_transcription_model_changed(selected_name),
            )

    def _default_transcription_model_name(self) -> str:
        """Modelo padrão da aba Transcrição quando o menu 'Modelos' está vazio.

        Regra do usuário (10/09): o padrão é o `servidor` (Granite NAR local).
        O `transcription_server` NÃO é consultado aqui — ele é compartilhado
        com a aba Ocorrência (que pode estar num modelo exclusivo de WebSocket,
        como o Meta Muse Voice) e não deve definir o que a Transcrição usa.
        """
        for name in self.settings.get("multi_transcription_models") or []:
            candidate = str(name or "").strip()
            if candidate and not is_realtime_only_transcription_server(candidate):
                return candidate
        return str(DEFAULT_SETTINGS["transcription_server"])

    def _reset_keywords_off_on_start(self) -> None:
        """Keywords SEMPRE desligadas ao abrir o app (regra do usuário).

        A escolha feita DENTRO da sessão continua sendo persistida — ela precisa
        sobreviver aos recarregamentos de settings que acontecem no meio de um
        lote (`start_run` chama `load_settings`). Mas ao abrir o app o perfil
        ativo volta para "Não": o usuário ativa manualmente a cada uso.

        Motivo (contexto forense): keyword esquecida ligada enviesa a
        transcrição e pode inserir termos que não foram ditos.
        """
        if not str(self.settings.get("stt_keyword_profile") or "").strip():
            return
        self.settings["stt_keyword_profile"] = ""
        self.settings = save_settings(self.settings)

    def _apply_keywords_selector(self, label: str):
        """Aplica a escolha do seletor "Keywords" (perfil ou desligado).

        O perfil ativo vale para as DUAS telas (REST e WS), como a lista única
        valia antes; a lista de cada perfil continua salva nas Configurações.
        """
        perfil = keywords_profile_label_to_value(self.settings, label)
        self.settings["stt_keyword_profile"] = perfil
        self.settings = save_settings(self.settings)
        self._rebuild_keywords_menus()
        self._set_activity_status(
            "Keywords: " + (perfil or KEYWORDS_OFF_LABEL + " (desligadas)"), log=False
        )

    def _rebuild_keywords_menus(self):
        """Reconstrói os menus dos dois seletores (perfis cadastrados)."""
        opcoes = keywords_selector_options(self.settings)
        atual = keywords_selector_label(self.settings)
        for botao, menu in (
            (getattr(self, "files_keywords_button", None), getattr(self, "files_keywords_menu", None)),
            (getattr(self, "live_keywords_button", None), getattr(self, "live_keywords_menu", None)),
        ):
            if botao is None or menu is None:
                continue
            menu.delete(0, "end")
            for opcao in opcoes:
                menu.add_command(
                    label=opcao,
                    command=lambda escolhido=opcao: self._apply_keywords_selector(escolhido),
                )
            botao.configure(menu=menu)
        self.files_keywords_label_var.set(f"Keywords: {atual}")
        if hasattr(self, "live_keywords_label_var"):
            self.live_keywords_label_var.set(f"Keywords: {atual}")

    def _refresh_files_language_label(self):
        self.files_language_label_var.set(f"Idioma: {transcription_language_option(self.settings)}")

    def _set_files_language(self, option: str):
        """Grava a opção do seletor de idioma da aba Transcrição.

        Só a OPÇÃO genérica (auto/pt/en/es) é persistida: o parâmetro real de
        cada modelo continua sendo montado pelo próprio provedor na hora da
        requisição (mesma regra da aba Ocorrência).
        """
        if option not in TRANSCRIPTION_LANGUAGE_OPTIONS:
            return
        self.settings[stt_provider_rules.KEY_TRANSCRIPTION_LANGUAGE] = option
        self.settings = save_settings(self.settings)
        self.files_language_label_var.set(f"Idioma: {option}")
        self._set_activity_status(f"Idioma selecionado: {option}.", log=False)

    def _transcription_batch_settings(self, model_names: list[str]) -> dict:
        """Cópia de settings do lote com o idioma traduzido por modelo.

        O seletor guarda uma opção única, mas cada provedor recebe o SEU valor
        (ex.: pt -> "pt-BR" no Deepgram e "pt" nos demais); o servidor local
        (Granite NAR) não recebe idioma nenhum. O settings.json e as
        preferências da aba Ocorrência não são tocados.

        O `transcription_server` da cópia passa a ser o PRIMEIRO modelo marcado:
        ele é compartilhado com a aba Ocorrência (e pode estar num modelo só de
        WebSocket), então sem isto o lote de um único modelo usaria o modelo
        da Ocorrência em vez do que está selecionado na Transcrição.
        """
        batch = self.settings.copy()
        batch["_multi_transcription"] = bool(model_names)
        batch["_multi_transcription_models"] = list(model_names)
        if model_names:
            batch["transcription_server"] = model_names[0]
        providers = transcription_providers_for_servers(
            [selected_transcription_server(batch)["name"], *model_names]
        )
        return apply_transcription_language_option(batch, providers)

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

    def _remove_selected_files(self, _event=None):
        """Remove da fila (antes de iniciar) os arquivos selecionados com Delete."""
        if self.running:
            return
        selected = self.tree.selection()
        if not selected:
            return
        selected_set = set(selected)
        # Coleta os caminhos a remover e remove os itens da árvore
        paths_to_remove = []
        for path, tree_item in list(self.tree_items.items()):
            if tree_item in selected_set:
                paths_to_remove.append(path)
                self.tree.delete(tree_item)
                del self.tree_items[path]
        if not paths_to_remove:
            return
        # Remove da lista ordenada mantendo a ordem de tamanho (já está ordenada)
        removed_set = {p.resolve() for p in paths_to_remove}
        self.selected_paths = [p for p in self.selected_paths if p.resolve() not in removed_set]
        self.status_var.set(f"{len(paths_to_remove)} arquivo(s) removido(s). {len(self.selected_paths)} arquivo(s) na fila.")

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


    def _job_size_column_text(self, job) -> str:
        """Texto da coluna Tamanho após conversão/VAD.

        Sem transformação: apenas o tamanho original (ex.: "2523 KB").
        Após converter/VAD: "2523 KB -> 786 KB" — original -> arquivo que
        será enviado para transcrição (eventualmente menor).
        """
        try:
            original_kb = job.original_path.stat().st_size // 1024
        except OSError:
            original_kb = 0
        if job.upload_path and job.upload_path.exists():
            try:
                final_kb = job.upload_path.stat().st_size // 1024
            except OSError:
                final_kb = 0
            if final_kb != original_kb:
                return f"{original_kb} KB -> {final_kb} KB"
        return f"{original_kb} KB"

    # _compute_and_update_duration removida — coluna agora é Tamanho (KB), definida na inserção


    def _refresh_tree_modes(self):
        # Modo não é mais exibido na lista (substituído por Duração).
        # Mantemos o método para compatibilidade com os callbacks dos radios,
        # mas não atualizamos mais a coluna da árvore.
        pass


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
        frame.rowconfigure(1, weight=1)

        import tkinter as tk

        settings_tab_bar = tk.Frame(frame, background="#f4f7f6")
        settings_tab_bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        settings_tab_content = ttk.Frame(frame, style="Settings.TFrame")
        settings_tab_content.grid(row=1, column=0, columnspan=2, sticky="nsew")
        settings_tab_content.columnconfigure(0, weight=1)
        settings_tab_content.rowconfigure(0, weight=1)

        settings_tab_names = ("Modelos", "Policial", "Chaves API", "Avançado")
        settings_tab_buttons = {}
        settings_tab_pages = {}
        settings_active_bg = "#ffffff"
        settings_inactive_bg = "#d6d2c7"
        settings_active_fg = "#10201f"
        settings_inactive_fg = "#111111"
        settings_tab_font = ("Segoe UI Semibold", 10)
        settings_tab_width = len("Chaves API") + 1

        for index, name in enumerate(settings_tab_names):
            settings_tab_pages[name] = ttk.Frame(settings_tab_content, style="Settings.TFrame")
            button = tk.Label(
                settings_tab_bar,
                text=name,
                width=settings_tab_width,
                height=1,
                borderwidth=1,
                relief="solid",
                font=settings_tab_font,
                cursor="hand2",
            )
            settings_tab_buttons[name] = button
            button.pack(side=LEFT, padx=(0 if index == 0 else 4, 0))

        def select_settings_tab(name: str):
            for page in settings_tab_pages.values():
                page.pack_forget()
            settings_tab_pages[name].pack(fill=BOTH, expand=True)
            for tab_name, button in settings_tab_buttons.items():
                button.configure(
                    background=settings_active_bg if tab_name == name else settings_inactive_bg,
                    foreground=settings_active_fg if tab_name == name else settings_inactive_fg,
                )

        for name, button in settings_tab_buttons.items():
            button.bind("<Button-1>", lambda _event, selected=name: select_settings_tab(selected))

        models_tab = settings_tab_pages["Modelos"]
        police_tab = settings_tab_pages["Policial"]
        api_tab = settings_tab_pages["Chaves API"]
        advanced_tab = settings_tab_pages["Avançado"]
        select_settings_tab("Modelos")

        conv_var = IntVar(value=self.settings["convert_parallel"])
        req_var = IntVar(value=self.settings["transcribe_parallel"])
        transcription_labels = {}
        transcription_server_var = StringVar()
        refreshing_transcription_servers = False
        history_model_labels = {}
        history_model_var = StringVar()
        history_reasoning_var = StringVar(value=self.settings.get("history_reasoning", "low"))
        history_proxy_model_var = StringVar(value=self.settings.get("history_proxy_model", GROK_TEXT_NAME))
        statement_model_labels = {}
        statement_model_var = StringVar()
        statement_reasoning_var = StringVar(value=self.settings.get("statement_reasoning", "low"))
        statement_proxy_model_var = StringVar(value=self.settings.get("statement_proxy_model", GROK_TEXT_NAME))
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
        assemblyai_api_key_var = StringVar(value=self.settings.get("assemblyai_api_key", ""))
        elevenlabs_api_key_var = StringVar(value=self.settings.get("elevenlabs_api_key", ""))
        metamuse_api_key_var = StringVar(value=self.settings.get("metamuse_api_key", ""))
        alibaba_api_key_var = StringVar(value=self.settings.get("alibaba_api_key", ""))
        imei_api_key_var = StringVar(value=self.settings.get("imei_api_key", ""))
        police_name_var = StringVar(value=self.settings.get("police_name", ""))
        police_role_var = StringVar(value=self.settings.get("police_role", ""))
        police_station_var = StringVar(value=self.settings.get("police_station", ""))
        police_delegate_var = StringVar(value=self.settings.get("police_delegate", ""))
        police_city_var = StringVar(value=self.settings.get("police_city", ""))
        grok_chunk_ms_var = StringVar(value=str(self.settings.get("grok_chunk_ms", 100)))
        grok_rest_var = BooleanVar(value=bool(self.settings.get("grok_rest_requests", False)))

        # A aba Modelos usa uma única coluna para evitar largura horizontal
        # desperdiçada e manter a leitura das seções em sequência.
        models_column = ttk.Frame(models_tab, style="Settings.TFrame")
        models_column.pack(fill=BOTH, expand=True, anchor="n")
        model_titles = (
            "Transcrição",
            "Histórico",
            "Oitiva",
            "Qualificação",
            "Extração de partes",
        )
        model_sections = []
        for title in model_titles:
            section = ttk.LabelFrame(
                models_column,
                text=title,
                padding=(12, 8),
                style="Settings.TLabelframe",
            )
            section.pack(fill=X, anchor="n", pady=(0, 8))
            section.columnconfigure(0, minsize=170)
            section.columnconfigure(1, weight=1)
            model_sections.append(section)
        # Aba Avançado: a tela inicial (botão KEYWORDS + Paralelismo) e a tela
        # de Keywords trocam entre si DENTRO da aba, sem mexer nas outras.
        advanced_home = ttk.Frame(advanced_tab, style="Settings.TFrame")
        advanced_home.pack(fill=BOTH, expand=True, anchor="n")
        advanced_keywords_bar = ttk.Frame(advanced_home, style="Settings.Inner.TFrame")
        advanced_keywords_bar.pack(anchor="e", pady=(0, 8))
        ttk.Button(
            advanced_keywords_bar,
            text="KEYWORDS",
            command=lambda: show_keywords_screen(),
        ).pack(side=RIGHT)
        parallel_frame = ttk.LabelFrame(
            advanced_home,
            text="Paralelismo",
            padding=(12, 8),
            style="Settings.TLabelframe",
        )
        parallel_frame.pack(fill=X, anchor="n")
        parallel_frame.columnconfigure(0, minsize=170)
        parallel_frame.columnconfigure(1, weight=1)
        columns = [model_sections, [parallel_frame]]
        (
            transcription_frame,
            history_frame,
            statement_frame,
            qualification_frame,
            extraction_frame,
        ) = model_sections

        police_frame = ttk.LabelFrame(
            police_tab,
            text="Policial",
            padding=(12, 8),
            style="Settings.TLabelframe",
        )
        police_frame.pack(fill=X, anchor="n")
        police_frame.columnconfigure(0, minsize=170)
        police_frame.columnconfigure(1, weight=1)

        def make_api_section(parent, title: str):
            section = ttk.LabelFrame(
                parent,
                text=title,
                padding=(12, 8),
                style="Settings.TLabelframe",
            )
            section.pack(fill=X, anchor="n", pady=(0, 8))
            section.columnconfigure(0, minsize=190)
            section.columnconfigure(1, weight=1)
            return section

        api_import_frame = ttk.Frame(api_tab, style="Settings.Inner.TFrame")
        api_import_frame.pack(anchor="e", pady=(0, 8))
        # Uma única seção para TODAS as chaves de modelo: transcrição e texto
        # juntas, na ordem pedida pelo usuário (Deepseek, xAI, Meta, ElevenLabs,
        # Deepgram, AssemblyAI, Alibaba). Labels exatas, sem alterações.
        api_models_frame = make_api_section(api_tab, "Modelos")
        api_imei_frame = make_api_section(api_tab, "IMEI CHECK")

        def add_api_field(section, row: int, label: str, variable: StringVar, help_text: str = ""):
            ttk.Label(section, text=label).grid(
                row=row, column=0, sticky="w", pady=5, padx=(0, 12)
            )
            entry = ttk.Entry(section, textvariable=variable, show="*", width=60)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            if help_text:
                create_tooltip(entry, help_text)
            return entry

        add_api_field(
            api_models_frame,
            0,
            "Deepseek",
            deepseek_api_key_var,
            "Obrigatória para selecionar modelos DeepSeek V4.",
        )
        add_api_field(
            api_models_frame,
            1,
            "xAI",
            grok_api_key_var,
            "Obrigatória para selecionar modelos da xAI em transcrição ou texto.",
        )
        add_api_field(
            api_models_frame,
            2,
            "Meta",
            metamuse_api_key_var,
            "Preencha para liberar o Meta Muse Voice na lista de transcrição.",
        )
        add_api_field(
            api_models_frame,
            3,
            "ElevenLabs",
            elevenlabs_api_key_var,
            "Preencha para liberar o Scribe v2 Realtime da ElevenLabs na lista de transcrição.",
        )
        add_api_field(
            api_models_frame,
            4,
            "Deepgram",
            deepgram_api_key_var,
            "Preencha para liberar o modelo Nova 3 do Deepgram na lista de transcrição.",
        )
        add_api_field(
            api_models_frame,
            5,
            "AssemblyAI",
            assemblyai_api_key_var,
            "Preencha para liberar o modelo AssemblyAI Universal-3.5 Pro na lista de transcrição.",
        )
        add_api_field(
            api_models_frame,
            6,
            "Alibaba",
            alibaba_api_key_var,
            "Preencha para liberar o Alibaba Fun ASR/Qwen na lista de transcrição.",
        )
        add_api_field(api_imei_frame, 0, "Chave API do IMEI Check", imei_api_key_var)

        api_key_variables = {
            "grok_api_key": grok_api_key_var,
            "deepseek_api_key": deepseek_api_key_var,
            "deepgram_api_key": deepgram_api_key_var,
            "assemblyai_api_key": assemblyai_api_key_var,
            "elevenlabs_api_key": elevenlabs_api_key_var,
            "metamuse_api_key": metamuse_api_key_var,
            "alibaba_api_key": alibaba_api_key_var,
            "imei_api_key": imei_api_key_var,
        }
        api_key_import_labels = {
            "grok_api_key": "xAI",
            "deepseek_api_key": "Deepseek",
            "deepgram_api_key": "Deepgram",
            "assemblyai_api_key": "AssemblyAI",
            "elevenlabs_api_key": "ElevenLabs",
            "metamuse_api_key": "Meta",
            "alibaba_api_key": "Alibaba",
            "imei_api_key": "ImeiCheck",
        }

        def import_api_keys():
            selected_path = filedialog.askopenfilename(
                parent=win,
                title="Importar chaves API",
                filetypes=(
                    ("Arquivos de texto", "*.txt"),
                    ("Todos os arquivos", "*.*"),
                ),
            )
            if not selected_path:
                return
            try:
                try:
                    content = Path(selected_path).read_text(encoding="utf-8-sig")
                except UnicodeDecodeError:
                    content = Path(selected_path).read_text(encoding="cp1252")
            except OSError as exc:
                messagebox.showerror(
                    "sig",
                    f"Não foi possível ler o arquivo selecionado:\n{exc}",
                    parent=win,
                )
                return

            imported = parse_api_keys_text(content)
            if not imported:
                messagebox.showwarning(
                    "Importar chaves API",
                    "Nenhuma chave API reconhecida foi encontrada no arquivo.",
                    parent=win,
                )
                return

            for field_name, api_key in imported.items():
                api_key_variables[field_name].set(api_key)
            imported_labels = [
                api_key_import_labels[field_name]
                for field_name in imported
            ]
            messagebox.showinfo(
                "Importar chaves API",
                "Chaves importadas: "
                + ", ".join(imported_labels)
                + ".\n\nClique em Salvar para manter as alterações.",
                parent=win,
            )

        ttk.Button(
            api_import_frame,
            text="IMPORTAR",
            command=import_api_keys,
        ).pack(side=RIGHT)

        cpu_count = max(1, os.cpu_count() or 1)
        # Valor padrão das duas slidebars: metade dos núcleos da CPU (n/2),
        # com arredondamento inteligente para números ímpares.
        default_parallel = default_parallelism(cpu_count)

        def parallel_scale(
            row: int,
            label: str,
            variable: IntVar,
            maximum: int,
            help_text: str,
        ):
            # Valor salvo fora da faixa (ou ausente) cai para o padrão n/2.
            if not (1 <= variable.get() <= maximum):
                variable.set(default_parallel)
            ttk.Label(parallel_frame, text=label).grid(
                row=row, column=0, sticky="w", pady=5, padx=(0, 12)
            )
            value_label = ttk.Label(parallel_frame, text=str(variable.get()), width=4)
            value_label.grid(row=row, column=2, sticky="w", pady=5, padx=(8, 0))

            def on_scale(value: str):
                try:
                    selected = int(round(float(str(value).replace(",", "."))))
                except (TypeError, ValueError):
                    selected = variable.get()
                selected = max(1, min(selected, maximum))
                variable.set(selected)
                value_label.configure(text=str(selected))

            scale = ttk.Scale(
                parallel_frame,
                from_=1,
                to=maximum,
                value=variable.get(),
                command=on_scale,
            )
            scale.grid(row=row, column=1, sticky="ew", pady=5)

            help_button = ttk.Button(
                parallel_frame,
                text="?",
                width=2,
                command=lambda: messagebox.showinfo(
                    f"{label}",
                    help_text,
                    parent=win,
                ),
            )
            help_button.grid(row=row, column=3, sticky="w", pady=5, padx=(8, 0))
            return scale

        # Conversões paralelas: 1..2n (n = núcleos da CPU); padrão n/2.
        conv_max = cpu_count * 2
        conv_help = (
            "Recomendado: metade dos núcleos da CPU (n/2).\n\n"
            "Cada conversão FFmpeg usa bastante CPU e leitura/escrita de disco. "
            "Paralelismo alto demais disputa recursos com o resto do sistema "
            "(e com a transcrição, quando roda em sequência), podendo até "
            "diminuir a velocidade total em vez de aumentar. "
            "Metade dos núcleos mantém a máquina responsiva e a conversão eficiente."
        )
        parallel_scale(0, "Conversões paralelas", conv_var, conv_max, conv_help)

        # Requisições paralelas: 1..16; padrão n/2.
        req_help = (
            "Recomendado: metade dos núcleos da CPU (n/2).\n\n"
            "Cada requisição de transcrição envia áudio e espera a resposta "
            "do servidor — o gargalo é a rede e o servidor, não a CPU local. "
            "Paralelismo alto demais satura a conexão e pode causar timeouts "
            "ou respostas instáveis. Metade dos núcleos dá o melhor equilíbrio "
            "entre velocidade e estabilidade."
        )
        parallel_scale(1, "Requisições paralelas", req_var, 16, req_help)

        # ── Tela de Keywords (aba Avançado) ──────────────────────────────
        # PERFIS: o usuário mantém várias listas nomeadas e escolhe a ativa nos
        # seletores "Keywords" das telas de Transcrição e Ocorrência. Cada
        # modelo continua montando o próprio parâmetro na requisição.
        keywords_page = ttk.Frame(advanced_tab, style="Settings.TFrame")
        keywords_profiles_edit: dict[str, list[str]] = {
            nome: list(termos)
            for nome, termos in keyword_profiles(self.settings).items()
        }
        keywords_hint_var = StringVar()
        keywords_profile_var = StringVar()
        keywords_profile_combo: ttk.Combobox | None = None

        def current_profile_name() -> str:
            return keywords_profile_var.get().strip()

        def current_items() -> list[str]:
            return keywords_profiles_edit.get(current_profile_name(), [])

        def set_current_items(termos: list[str]) -> None:
            nome = current_profile_name()
            if nome:
                keywords_profiles_edit[nome] = termos

        def keywords_hint() -> str:
            """Resumo HONESTO do que cada modelo vai receber (sem truncar calado)."""
            if not keywords_profiles_edit:
                return (
                    "Nenhum perfil criado. Clique em \"+ Perfil\" para nomear e "
                    "cadastrar termos — sem perfil ativo os modelos transcrevem sem viés."
                )
            nome = current_profile_name()
            if not nome:
                return "Nenhum perfil selecionado acima."
            termos = current_items()
            if not termos:
                return f"O perfil \"{nome}\" está vazio — os modelos transcrevem sem viés."
            ativo = keywords_selector_label(self.settings)
            marca = " (EM USO nas telas)" if nome == ativo else ""
            base = {"stt_keyword_profiles": {nome: list(termos)}, "stt_keyword_profile": nome}
            total = len(termos)
            deepgram = len(keywords_for_provider(base, "deepgram"))
            if deepgram < total:
                return (
                    f"Perfil \"{nome}\"{marca}: {total} termos. O Deepgram recebe só os "
                    f"primeiros {deepgram} (teto de 500 tokens); os demais modelos recebem "
                    f"os {total}. Mantenha os principais no topo — clique em ? para os limites."
                )
            return (
                f"Perfil \"{nome}\"{marca}: {total} de {MAX_STT_KEYWORDS} termos — todos os "
                f"modelos recebem os {total}, com até {MAX_STT_KEYWORD_LENGTH} caracteres "
                "cada. Clique em ? para os limites de cada modelo."
            )

        keywords_top = ttk.Frame(keywords_page, style="Settings.Inner.TFrame")
        keywords_top.pack(fill=X, pady=(0, 10))
        ttk.Button(
            keywords_top,
            text="\u2190  Voltar",
            command=lambda: show_advanced_home(),
        ).pack(side=LEFT)
        ttk.Label(
            keywords_top,
            text="Keywords — termos que os modelos devem reconhecer",
            style="Settings.TLabel",
        ).pack(side=LEFT, padx=(14, 0))
        self._make_help_marker(
            keywords_top, lambda: self._open_keywords_help(win)
        ).pack(side=LEFT, padx=(8, 0))

        keywords_profile_row = ttk.Frame(keywords_page, style="Settings.Inner.TFrame")
        keywords_profile_row.pack(fill=X, pady=(0, 8))
        ttk.Label(keywords_profile_row, text="Perfil:", style="Settings.TLabel").pack(side=LEFT)
        keywords_profile_combo = ttk.Combobox(
            keywords_profile_row,
            textvariable=keywords_profile_var,
            state="readonly",
            width=28,
        )
        keywords_profile_combo.pack(side=LEFT, padx=(6, 0))

        keywords_entry_row = ttk.Frame(keywords_page, style="Settings.Inner.TFrame")
        keywords_entry_row.pack(fill=X, pady=(0, 10))
        keyword_entry_var = StringVar()
        keyword_entry = ttk.Entry(keywords_entry_row, textvariable=keyword_entry_var, width=42)
        keyword_entry.pack(side=LEFT)

        keywords_table_frame = ttk.Frame(keywords_page, style="Settings.Inner.TFrame")
        keywords_table_frame.pack(fill=X, anchor="w")
        keywords_tree = ttk.Treeview(
            keywords_table_frame,
            columns=("ordem", "palavra"),
            show="headings",
            height=8,
            selectmode="browse",
        )
        keywords_tree.heading("ordem", text="N\u00ba")
        keywords_tree.heading("palavra", text="Keyword")
        keywords_tree.column("ordem", width=44, anchor="center", stretch=False)
        keywords_tree.column("palavra", width=300, anchor="w")
        keywords_scroll = ttk.Scrollbar(
            keywords_table_frame, orient="vertical", command=keywords_tree.yview
        )
        keywords_tree.configure(yscrollcommand=keywords_scroll.set)
        keywords_tree.pack(side=LEFT)
        keywords_scroll.pack(side=LEFT, fill=Y)

        def refresh_profile_combo(selecionar: str | None = None):
            nomes = list(keywords_profiles_edit)
            if keywords_profile_combo is not None:
                keywords_profile_combo.configure(values=nomes)
            alvo = selecionar if selecionar is not None else current_profile_name()
            if alvo not in nomes:
                alvo = nomes[0] if nomes else ""
            keywords_profile_var.set(alvo)
            refresh_keywords_table()

        def novo_perfil_nome_sugerido() -> str:
            base = DEFAULT_KEYWORD_PROFILE_NAME
            nome = base
            numero = 1
            while nome in keywords_profiles_edit:
                numero += 1
                nome = f"Lista {numero}"
            return nome

        def abrir_dialogo_nome(titulo: str, inicial: str, rotulo_ok: str, ao_confirmar):
            """Diálogo simples de nome (usado no '+ Perfil' e no Renomear)."""
            janela = Toplevel(win)
            janela.title(titulo)
            janela.configure(background="#f4f7f6")
            janela.resizable(False, False)
            janela.transient(win)
            quadro = ttk.Frame(janela, padding=12)
            quadro.pack(fill=BOTH, expand=True)
            entrada = ttk.Entry(quadro, width=34)
            entrada.insert(0, inicial)
            entrada.pack(fill=X, pady=(0, 8))
            ttk.Label(
                quadro,
                text=(
                    "O nome aparece no seletor \"Keywords:\" das telas de Transcrição "
                    "e Ocorrência.\nO perfil é salvo com os termos que você adicionar."
                ),
                justify="left",
            ).pack(anchor="w", pady=(0, 8))

            def aplicar():
                novo = entrada.get().strip()
                if not novo:
                    messagebox.showinfo("Keywords", "Digite um nome para o perfil.", parent=janela)
                    return
                if ao_confirmar(novo):
                    janela.destroy()

            botoes_nome = ttk.Frame(quadro)
            botoes_nome.pack(fill=X)
            ttk.Button(botoes_nome, text="Cancelar", command=janela.destroy).pack(
                side=LEFT, padx=(0, 8)
            )
            ttk.Button(botoes_nome, text=rotulo_ok, command=aplicar).pack(side=LEFT)
            entrada.bind("<Return>", lambda _event: aplicar())
            janela.grab_set()
            entrada.focus_set()
            entrada.select_range(0, "end")

        def new_profile():
            """+ Perfil: cria um perfil com o nome escolhido pelo usuário."""
            if len(keywords_profiles_edit) >= MAX_KEYWORD_PROFILES:
                messagebox.showinfo(
                    "Keywords",
                    f"O máximo é {MAX_KEYWORD_PROFILES} perfis.",
                    parent=win,
                )
                return

            def criar(novo: str) -> bool:
                if novo in keywords_profiles_edit:
                    messagebox.showinfo(
                        "Keywords", f'Já existe o perfil "{novo}".', parent=win
                    )
                    return False
                keywords_profiles_edit[novo] = []
                refresh_profile_combo(selecionar=novo)
                keyword_entry.focus_set()
                return True

            abrir_dialogo_nome("Novo perfil", novo_perfil_nome_sugerido(), "Criar", criar)

        def rename_profile():
            nome = current_profile_name()
            if not nome:
                messagebox.showinfo("Keywords", "Crie ou selecione um perfil primeiro.", parent=win)
                return

            def renomear(novo: str) -> bool:
                if novo != nome and novo in keywords_profiles_edit:
                    messagebox.showinfo(
                        "Keywords", f'Já existe o perfil "{novo}".', parent=win
                    )
                    return False
                if novo == nome:
                    return True
                termos = keywords_profiles_edit.pop(nome)
                # Preserva a ordem da lista renomeada.
                reordenado = {novo: termos}
                reordenado.update(keywords_profiles_edit)
                keywords_profiles_edit.clear()
                keywords_profiles_edit.update(reordenado)
                if str(self.settings.get("stt_keyword_profile") or "").strip() == nome:
                    self.settings["stt_keyword_profile"] = novo
                refresh_profile_combo(selecionar=novo)
                return True

            abrir_dialogo_nome("Renomear perfil", nome, "Renomear", renomear)

        def delete_profile():
            nome = current_profile_name()
            if not nome:
                messagebox.showinfo("Keywords", "Crie ou selecione um perfil primeiro.", parent=win)
                return
            if not messagebox.askyesno(
                "Excluir perfil",
                f'Excluir o perfil "{nome}" com {len(keywords_profiles_edit.get(nome, []))} termo(s)?',
                parent=win,
            ):
                return
            keywords_profiles_edit.pop(nome, None)
            if str(self.settings.get("stt_keyword_profile") or "").strip() == nome:
                self.settings["stt_keyword_profile"] = ""     # era o ativo: desliga
            refresh_profile_combo()

        ttk.Button(
            keywords_profile_row,
            text="+ Perfil",
            command=new_profile,
        ).pack(side=LEFT, padx=(8, 0))
        ttk.Button(
            keywords_profile_row,
            text="Renomear",
            command=rename_profile,
        ).pack(side=LEFT, padx=(6, 0))
        ttk.Button(
            keywords_profile_row,
            text="Excluir",
            command=delete_profile,
        ).pack(side=LEFT, padx=(6, 0))

        def refresh_keywords_table(select_index: int | None = None):
            keywords_tree.delete(*keywords_tree.get_children())
            termos = current_items()
            for index, term in enumerate(termos, start=1):
                keywords_tree.insert("", "end", iid=str(index), values=(index, term))
            if select_index is not None and 1 <= select_index <= len(termos):
                keywords_tree.selection_set(str(select_index))
                keywords_tree.see(str(select_index))
            keywords_hint_var.set(keywords_hint())

        def add_keyword():
            if not current_profile_name():
                messagebox.showinfo(
                    "Keywords",
                    "Crie um perfil primeiro (botão \"+ Perfil\").",
                    parent=win,
                )
                return
            term = keyword_entry_var.get().strip()
            if not term:
                messagebox.showinfo("Keywords", "Digite a palavra antes de adicionar.", parent=win)
                return
            if len(term) > MAX_STT_KEYWORD_LENGTH:
                messagebox.showinfo(
                    "Keywords",
                    f"Cada keyword pode ter no máximo {MAX_STT_KEYWORD_LENGTH} caracteres.\n\n"
                    "Esse é o limite do WebSocket (ElevenLabs e Meta Muse Voice), que é "
                    "menor que o do REST — usar o menor garante que o termo funcione "
                    "também na Ocorrência.",
                    parent=win,
                )
                return
            termos = current_items()
            if any(existing.casefold() == term.casefold() for existing in termos):
                messagebox.showinfo("Keywords", f'"{term}" já está nesta lista.', parent=win)
                return
            if len(termos) >= MAX_STT_KEYWORDS:
                messagebox.showinfo(
                    "Keywords",
                    f"A lista já tem o máximo de {MAX_STT_KEYWORDS} keywords.",
                    parent=win,
                )
                return
            set_current_items(termos + [term])
            keyword_entry_var.set("")
            refresh_keywords_table(select_index=len(termos) + 1)
            keyword_entry.focus_set()

        def remove_keyword():
            selection = keywords_tree.selection()
            if not selection:
                messagebox.showinfo(
                    "Keywords",
                    "Selecione na tabela a keyword que deseja excluir.",
                    parent=win,
                )
                return
            index = int(str(selection[0])) - 1
            termos = current_items()
            if not (0 <= index < len(termos)):
                return
            term = termos[index]
            if not messagebox.askyesno(
                "Excluir keyword",
                f'Excluir a keyword "{term}"?',
                parent=win,
            ):
                return
            set_current_items([t for pos, t in enumerate(termos) if pos != index])
            refresh_keywords_table(select_index=min(index + 1, len(termos) - 1))

        add_keyword_button = ttk.Button(
            keywords_entry_row,
            text="+",
            width=3,
            style="KeywordAdd.TButton",
            command=add_keyword,
        )
        add_keyword_button.pack(side=LEFT, padx=(8, 0))
        keyword_entry.bind("<Return>", lambda _event: add_keyword())

        keywords_actions = ttk.Frame(keywords_page, style="Settings.Inner.TFrame")
        keywords_actions.pack(fill=X, anchor="w", pady=(10, 0))
        ttk.Button(
            keywords_actions,
            text="\u2212",
            width=3,
            style="KeywordRemove.TButton",
            command=remove_keyword,
        ).pack(side=LEFT)
        ttk.Label(
            keywords_actions,
            text=(
                "Selecione um item e clique em \u2212 para excluir. O perfil em edição é o "
                "escolhido em \"Perfil\"; clique em Salvar para manter."
            ),
            style="Muted.TLabel",
        ).pack(side=LEFT, padx=(12, 0))
        ttk.Label(
            keywords_page,
            textvariable=keywords_hint_var,
            style="Muted.TLabel",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))
        refresh_profile_combo()

        def show_keywords_screen():
            advanced_home.pack_forget()
            keywords_page.pack(fill=BOTH, expand=True, anchor="n")
            keyword_entry.focus_set()

        def show_advanced_home():
            keywords_page.pack_forget()
            advanced_home.pack(fill=BOTH, expand=True, anchor="n")

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
            nonlocal transcription_labels, refreshing_transcription_servers
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
                and (
                    server["name"] != META_MUSE_API_NAME
                    or bool(metamuse_api_key_var.get().strip())
                )
                and (
                    server["name"] != ALIBABA_API_NAME
                    or bool(alibaba_api_key_var.get().strip())
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
            refreshing_transcription_servers = False

        def primary_server_changed(*_args):
            refresh_transcription_servers(transcription_labels.get(transcription_server_var.get()))
            refresh_chunk_visibility()

        chunk_size_row = transcription_server_row + 1
        chunk_controls = ttk.Frame(transcription_frame, style="Settings.Inner.TFrame")
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

        rest_controls = ttk.Frame(transcription_frame, style="Settings.Inner.TFrame")

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
            if selected_name == GROK_API_NAME:
                chunk_controls.grid_configure(row=chunk_size_row, column=1)
                rest_controls.grid_configure(row=chunk_size_row + 1, column=1, sticky="w")
                chunk_controls.grid()
                rest_controls.grid()
            else:
                chunk_controls.grid_remove()
                rest_controls.grid_remove()

        refresh_transcription_servers()
        transcription_server_var.trace_add("write", primary_server_changed)
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
                # IA-Proxy usa reasoning fixo: low para Grok e none para
                # DeepSeek. Os níveis avançados só ficam disponíveis nas
                # opções de acesso direto, com a respectiva API key.
                current_reasoning_frame.grid_remove()
                reasoning_var.set("none" if actual_model == DEEPSEEK_TEXT_NAME else "low")
                reasoning_display.set(reasoning_var.get())
                return
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

        def make_single_text_section(
            section_frame,
            *,
            model_var,
            reasoning_var,
            proxy_var,
            settings_model_key,
            settings_reasoning_key,
            settings_proxy_key,
            model_labels_holder,
            label_text,
        ):
            model_label = ttk.Label(section_frame, text=label_text)
            model_label.grid(row=0, column=0, sticky="w", pady=5, padx=(0, 12))
            model_combo = ttk.Combobox(
                section_frame, textvariable=model_var, state="readonly", width=44
            )
            model_combo.grid(row=0, column=1, sticky="ew", pady=5)

            proxy_model_frame = ttk.Frame(section_frame, style="Settings.Inner.TFrame")
            ttk.Label(
                proxy_model_frame,
                text="Modelo",
                width=12,
                anchor="w",
                style="Settings.TLabel",
            ).pack(side=LEFT, padx=(0, 10))
            proxy_display_var = StringVar(value=proxy_var.get())
            proxy_button = ttk.Menubutton(proxy_model_frame, textvariable=proxy_display_var, width=30)
            proxy_menu = tk.Menu(proxy_button, tearoff=False)
            proxy_button.configure(menu=proxy_menu)
            proxy_button.pack(side=LEFT)

            reasoning_frame = ttk.Frame(section_frame, style="Settings.Inner.TFrame")
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

            def refresh(preferred_name: str | None = None):
                available_models = [
                    model for model in read_text_models()
                    if (
                        model["name"] not in GROK_TEXT_API_NAMES
                        or plausible_xai_api_key(grok_api_key_var.get())
                    ) and (
                        model["name"] not in DEEPSEEK_API_NAMES
                        or plausible_deepseek_api_key(deepseek_api_key_var.get())
                    )
                ]
                model_labels_holder.clear()
                model_labels_holder.update({
                    (
                        model["name"]
                        if model["name"] == IA_PROXY_NAME
                        or model["name"] in GROK_TEXT_API_NAMES
                        or model["name"] in DEEPSEEK_API_NAMES
                        else f"{model['name']} ({model['parameters'].get('model', 'modelo não informado')})"
                    ): model["name"]
                    for model in available_models
                })
                model_combo.configure(values=list(model_labels_holder))
                target = (
                    preferred_name
                    or model_labels_holder.get(model_var.get(), "")
                    or str(self.settings.get(settings_model_key) or "")
                )
                target = fallback_text_model_for_missing_api_key(
                    target,
                    grok_api_key_var.get(),
                    deepseek_api_key_var.get(),
                )
                if target not in model_labels_holder.values():
                    target = (
                        SERVER_GEMMA_NAME
                        if SERVER_GEMMA_NAME in model_labels_holder.values()
                        else IA_PROXY_NAME
                    )
                label = next(
                    (item for item, name in model_labels_holder.items() if name == target),
                    next(iter(model_labels_holder), ""),
                )
                model_var.set(label)
                configure_menu(proxy_menu, proxy_var, proxy_display_var, proxy_model_options)
                refresh_reasoning_controls()

            def refresh_reasoning_controls(*_args):
                refresh_model_reasoning_controls(
                    model_labels_holder.get(model_var.get(), ""),
                    proxy_var,
                    proxy_model_frame,
                    proxy_menu,
                    proxy_display_var,
                    reasoning_var,
                    reasoning_frame,
                    reasoning_menu,
                    reasoning_display_var,
                    1,
                    2,
                )

            refresh()
            model_var.trace_add("write", refresh_reasoning_controls)
            proxy_var.trace_add("write", refresh_reasoning_controls)
            return {
                "labels": model_labels_holder,
                "refresh": refresh,
                "label": model_label,
                "combo": model_combo,
                "hideable": [model_label, model_combo, proxy_model_frame, reasoning_frame],
            }

        history_ui = make_single_text_section(
            history_frame,
            model_var=history_model_var,
            reasoning_var=history_reasoning_var,
            proxy_var=history_proxy_model_var,
            settings_model_key="history_model",
            settings_reasoning_key="history_reasoning",
            settings_proxy_key="history_proxy_model",
            model_labels_holder=history_model_labels,
            label_text="Modelo de histórico",
        )
        statement_ui = make_single_text_section(
            statement_frame,
            model_var=statement_model_var,
            reasoning_var=statement_reasoning_var,
            proxy_var=statement_proxy_model_var,
            settings_model_key="statement_model",
            settings_reasoning_key="statement_reasoning",
            settings_proxy_key="statement_proxy_model",
            model_labels_holder=statement_model_labels,
            label_text="Modelo de oitiva",
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
            proxy_model_frame = ttk.Frame(section_frame, style="Settings.Inner.TFrame")
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
            reasoning_frame = ttk.Frame(section_frame, style="Settings.Inner.TFrame")
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
                current = (
                    model_labels_holder.get(model_var.get(), "")
                    or str(self.settings.get(settings_model_key) or IA_PROXY_NAME)
                )
                target = fallback_text_model_for_missing_api_key(
                    current,
                    grok_api_key_var.get(),
                    deepseek_api_key_var.get(),
                )
                if target not in model_labels_holder.values():
                    target = (
                        SERVER_GEMMA_NAME
                        if SERVER_GEMMA_NAME in model_labels_holder.values()
                        else IA_PROXY_NAME
                    )
                target_label = next(
                    (label for label, name in model_labels_holder.items() if name == target),
                    next(iter(model_labels_holder), ""),
                )
                if model_var.get() != target_label:
                    model_var.set(target_label)
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

        def refresh_api_key_dependent_selectors(*_args):
            refresh_transcription_servers()
            history_ui["refresh"]()
            statement_ui["refresh"]()
            refresh_extraction_visibility()
            qualification_ui["refresh"]()

        for api_key_variable in (
            grok_api_key_var,
            deepseek_api_key_var,
            deepgram_api_key_var,
            assemblyai_api_key_var,
            elevenlabs_api_key_var,
        ):
            api_key_variable.trace_add("write", refresh_api_key_dependent_selectors)

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

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(6, 0))

        def save_and_close():
            selected_transcription = transcription_labels.get(transcription_server_var.get(), "")
            selected_history = history_ui["labels"].get(history_model_var.get(), "")
            selected_statement = statement_ui["labels"].get(statement_model_var.get(), "")
            api_key = grok_api_key_var.get().strip()
            deepseek_api_key = deepseek_api_key_var.get().strip()
            deepgram_api_key = deepgram_api_key_var.get().strip()
            assemblyai_api_key = assemblyai_api_key_var.get().strip()
            elevenlabs_api_key = elevenlabs_api_key_var.get().strip()
            metamuse_api_key = metamuse_api_key_var.get().strip()
            alibaba_api_key = alibaba_api_key_var.get().strip()
            selected_transcription = fallback_transcription_server_for_missing_api_key(
                selected_transcription,
                api_key,
                deepgram_api_key,
                assemblyai_api_key,
                elevenlabs_api_key,
                metamuse_api_key,
                alibaba_api_key,
            )
            selected_history = fallback_text_model_for_missing_api_key(
                selected_history,
                api_key,
                deepseek_api_key,
            )
            selected_statement = fallback_text_model_for_missing_api_key(
                selected_statement,
                api_key,
                deepseek_api_key,
            )
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
                selected_history,
                selected_statement,
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
            selected_parts_model_name = fallback_text_model_for_missing_api_key(
                selected_parts_model_name,
                api_key,
                deepseek_api_key,
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
            selected_qualification_model = fallback_text_model_for_missing_api_key(
                selected_qualification_model,
                api_key,
                deepseek_api_key,
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
                    "history_model": selected_history,
                    "history_reasoning": history_reasoning_var.get(),
                    "history_proxy_model": history_proxy_model_var.get(),
                    "statement_model": selected_statement,
                    "statement_reasoning": statement_reasoning_var.get(),
                    "statement_proxy_model": statement_proxy_model_var.get(),
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
                    "assemblyai_api_key": assemblyai_api_key,
                    "elevenlabs_api_key": elevenlabs_api_key,
                    "metamuse_api_key": metamuse_api_key,
                    "alibaba_api_key": alibaba_api_key,
                    "stt_keyword_profiles": {
                        nome: list(termos) for nome, termos in keywords_profiles_edit.items()
                    },
                    # Perfil ativo (escolhido no seletor das telas): entra no
                    # save porque o normalize parte dos defaults — sem esta
                    # linha, salvar as Configurações desligaria as keywords.
                    "stt_keyword_profile": str(self.settings.get("stt_keyword_profile") or ""),
                    "imei_api_key": imei_api_key,
                    "police_name": police_name,
                    "police_role": police_role,
                    "police_station": police_station,
                    "police_delegate": police_delegate,
                    "police_city": police_city,
                }
            )
            self._refresh_server_label()
            self._refresh_live_grok_controls()
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
                    child.configure(style="Settings.Inner.TFrame")
                normalize_settings_surface(child)

        all_settings_sections = [
            section
            for column_sections in columns
            for section in column_sections
        ] + [
            police_frame,
            api_models_frame,
            api_imei_frame,
        ]
        for section in all_settings_sections:
            normalize_settings_surface(section)

        def disable_settings_section(section):
            section.configure(style="Disabled.Settings.TLabelframe")

            def disable_children(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.LabelFrame):
                        child.configure(style="Disabled.Settings.TLabelframe")
                    elif isinstance(child, ttk.Label):
                        child.configure(style="Disabled.Settings.TLabel")
                    elif isinstance(child, ttk.Checkbutton):
                        child.configure(state="disabled", style="Disabled.Settings.TCheckbutton")
                    elif isinstance(child, (ttk.Entry, ttk.Combobox, ttk.Menubutton, ttk.Button)):
                        child.configure(state="disabled")
                    elif isinstance(child, ttk.Frame):
                        child.configure(style="Disabled.Settings.TFrame")
                    disable_children(child)

            disable_children(section)

        # A extração de partes está temporariamente fora do fluxo; a seção
        # permanece visível apenas para deixar claro que a opção está
        # indisponível, sem permitir alteração acidental.
        disable_settings_section(extraction_frame)
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
        """Abre a tela de status: 3 pingos por servidor (transcrição e texto).

        Coluna 1 = modelos de transcrição; coluna 2 = modelos de texto.
        Cada servidor recebe 3 pingos HTTP; a média é exibida em verde com
        "(Xms)" se respondeu, ou em vermelho com "(offline)". Os que
        responderam aparecem primeiro.
        """
        win = Toplevel(self.root)
        win.title("Status dos servidores")
        win.resizable(False, False)

        try:
            transcription_servers = read_transcription_servers()
        except Exception:
            transcription_servers = []
        try:
            text_models = read_text_models()
        except Exception:
            text_models = []

        def entry_display(name: str, url: str, parameters: dict) -> tuple[str, str]:
            model = str((parameters or {}).get("model", "") or "").strip()
            if name.casefold() == "servidor" and model:
                return f"{name} ({model})", url
            return name, url

        trans_entries = [
            entry_display(s.get("name", "?"), s.get("url", ""), s.get("parameters") or {})
            for s in transcription_servers
        ]
        text_entries = [
            entry_display(m.get("name", "?"), m.get("url", ""), m.get("parameters") or {})
            for m in text_models
        ]

        def measure(url: str) -> float | None:
            """3 handshakes TCP no host; devolve a média em ms, ou None se offline.

            Mede só o connect() (nível 4) — valor mais próximo do ping ICMP,
            sem o custo do processamento HTTP do servidor.
            """
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return None
            host = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            times = []
            for _ in range(3):
                start = time.perf_counter()
                try:
                    with socket.create_connection((host, port), timeout=2.0):
                        times.append((time.perf_counter() - start) * 1000.0)
                except Exception:
                    continue
            if not times:
                return None
            return sum(times) / len(times)

        results: dict[str, float | None] = {}
        all_entries = trans_entries + text_entries
        if all_entries:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(8, len(all_entries))
            ) as executor:
                future_map = {
                    executor.submit(measure, url): name
                    for name, url in all_entries
                }
                for future in concurrent.futures.as_completed(future_map, timeout=20):
                    name = future_map[future]
                    try:
                        results[name] = future.result()
                    except Exception:
                        results[name] = None

        def ordered(entries):
            online = [e for e in entries if results.get(e[0]) is not None]
            offline = [e for e in entries if results.get(e[0]) is None]
            return online + offline

        trans_ordered = ordered(trans_entries)
        text_ordered = ordered(text_entries)

        col_width = 620
        width = max(col_width * 2, 400)
        header_y = 18
        row_start = 48
        row_h = 28
        rows = max(len(trans_ordered), len(text_ordered), 1)
        height = row_start + rows * row_h + 16

        canvas = Canvas(win, width=width, height=height, highlightthickness=0, background="#000000")
        canvas.pack(fill=BOTH, expand=True)

        canvas.create_text(
            20,
            header_y,
            text="Modelos de transcrição",
            fill="#d6a22b",
            font=("Segoe UI Semibold", 12),
            anchor="w",
        )
        canvas.create_text(
            col_width + 20,
            header_y,
            text="Modelos de texto",
            fill="#d6a22b",
            font=("Segoe UI Semibold", 12),
            anchor="w",
        )

        def draw_column(entries, x):
            y = row_start
            for name, _url in entries:
                avg = results.get(name)
                if avg is None:
                    color = "#e74c3c"
                    suffix = "(offline)"
                elif avg < 1.0:
                    color = "#2ecc71"
                    suffix = "(<1ms)"
                else:
                    color = "#2ecc71"
                    suffix = f"({avg:.0f}ms)"
                canvas.create_text(
                    x,
                    y,
                    text=f"{name} {suffix}",
                    fill=color,
                    font=("Segoe UI", 11),
                    anchor="w",
                )
                y += row_h

        draw_column(trans_ordered, 20)
        draw_column(text_ordered, col_width + 20)

        win.geometry(f"{width}x{height}")
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
        if not self._sounddevice_has_input_device(sounddevice):
            self.microphone_available = False
            messagebox.showerror(
                "sig",
                "Nenhum microfone de entrada foi encontrado.\n"
                "Conecte um microfone e tente novamente.",
            )
            self.status_var.set("Nenhum microfone de entrada foi encontrado. Conecte um microfone e tente novamente.")
            return
        self.microphone_available = True
        self.settings = load_settings()
        self._refresh_live_grok_controls()
        multi_selected = self._selected_multi_transcription_model_names()
        primary = self.settings.get("transcription_server")
        secondary_name = next(
            (name for name in multi_selected if name != primary), None
        )
        secondary_settings = (
            settings_for_transcription_server(self.settings, secondary_name)
            if secondary_name
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
        if (
            is_metamuse_transcription(self.settings)
            or (secondary_settings is not None and is_metamuse_transcription(secondary_settings))
        ) and not self.settings.get("metamuse_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Meta Muse Voice nas configurações antes de iniciar.")
            return
        if (
            is_alibaba_transcription(self.settings)
            or (secondary_settings is not None and is_alibaba_transcription(secondary_settings))
        ) and not self.settings.get("alibaba_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Alibaba Cloud nas configurações antes de iniciar.")
            return
        self.live_stop_event.clear()
        self.live_abort_event.clear()
        self.live_ws_finalize_pending = False
        self.live_ws_finalize_started = None
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
        self.live_uses_metamuse_websocket = is_metamuse_transcription(self.settings) and not self.settings.get(
            "grok_rest_requests", False
        )
        self.live_uses_alibaba_websocket = is_alibaba_transcription(self.settings) and not self.settings.get(
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
        self.metamuse_ws_ready_event.clear()
        self.metamuse_ws_done_event.clear()
        self.metamuse_ws_lost_event.clear()
        self.metamuse_ws_intentional_close = False
        self.metamuse_ws_app = None
        self.alibaba_ws_ready_event.clear()
        self.alibaba_ws_done_event.clear()
        self.alibaba_ws_lost_event.clear()
        self.alibaba_ws_intentional_close = False
        self.alibaba_ws_app = None
        streaming_websocket = (
            self.live_uses_grok_websocket
            or self.live_uses_deepgram_websocket
            or self.live_uses_assemblyai_websocket
            or self.live_uses_elevenlabs_websocket
            or self.live_uses_metamuse_websocket
            or self.live_uses_alibaba_websocket
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
        # No streaming, o relógio e a gravação só começam ao conectar: o
        # worker preenche live_started_at no primeiro connect com sucesso.
        self.live_started_at = time.time() if not streaming_websocket else 0.0
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
                or self.live_uses_metamuse_websocket
                or self.live_uses_alibaba_websocket
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
            and not self.live_uses_metamuse_websocket
            and not self.live_uses_alibaba_websocket
        ):
            self.status_var.set("Ouvindo e transcrevendo ao vivo...")
        elif streaming_websocket:
            self.status_var.set("Gravando. Clique no botão verde para encerrar o websocket")
        if self.live_uses_alibaba_websocket:
            target = self._alibaba_live_capture_loop
        elif self.live_uses_metamuse_websocket:
            target = self._metamuse_live_capture_loop
        elif self.live_uses_elevenlabs_websocket:
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
        if self.live_uses_alibaba_websocket:
            # Parar é imediato: finish-task, fecha o socket e consolida
            # o texto acumulado na hora — sem esperar o task-finished.
            self.alibaba_ws_intentional_close = True
            self._begin_activity_step("live:ws_finalize", "Websocket encerrado.")
            self.live_ws_finalize_started = time.monotonic()
            self.live_ws_finalize_pending = True
            self.live_stop_event.set()
            app = self.alibaba_ws_app
            task_id = getattr(self, "alibaba_ws_task_id", "") or ""
            if app and task_id:
                try:
                    app.send(json.dumps(alibaba_ws_finish_task(task_id)))
                except Exception:
                    pass
            if app:
                try:
                    app.close()
                except Exception:
                    pass
            self._finish_alibaba_session()
            return
        if self.live_uses_metamuse_websocket:
            # Parar é imediato: avisa o servidor, fecha o socket e consolida
            # o texto acumulado na hora — sem esperar confirmação final.
            self.metamuse_ws_intentional_close = True
            self._begin_activity_step("live:ws_finalize", "Websocket encerrado.")
            self.live_ws_finalize_started = time.monotonic()
            self.live_ws_finalize_pending = True
            self.live_stop_event.set()
            app = self.metamuse_ws_app
            if app:
                try:
                    app.send(json.dumps({"type": "endStream"}))
                except Exception:
                    pass
                try:
                    app.close()
                except Exception:
                    pass
            self._finish_metamuse_session()
            return
        if self.live_uses_elevenlabs_websocket:
            # Parar é imediato: força o commit, fecha o socket e consolida
            # o texto acumulado na hora — sem esperar confirmação final.
            self.elevenlabs_ws_intentional_close = True
            self._begin_activity_step("live:ws_finalize", "Websocket encerrado.")
            self.live_ws_finalize_started = time.monotonic()
            self.live_ws_finalize_pending = True
            self.live_stop_event.set()
            app = self.elevenlabs_ws_app
            if app:
                try:
                    # Força a finalização com um chunk de silêncio commitado.
                    silence = base64.b64encode(bytes(3200)).decode("ascii")
                    app.send(json.dumps({
                        "message_type": "input_audio_chunk",
                        "audio_base_64": silence,
                        "commit": True,
                        "sample_rate": LIVE_SAMPLE_RATE,
                    }))
                except Exception:
                    pass
                try:
                    app.close()
                except Exception:
                    pass
            self.elevenlabs_ws_done_event.set()
            self.elevenlabs_ws_app = None
            self.live_uses_elevenlabs_websocket = False
            self._consolidate_live_text_now()
            return
        if self.live_uses_assemblyai_websocket:
            # Parar é imediato: avisa o servidor, fecha o socket e consolida
            # o texto acumulado na hora — sem esperar confirmação final.
            self.assemblyai_ws_intentional_close = True
            self._begin_activity_step("live:ws_finalize", "Websocket encerrado.")
            self.live_ws_finalize_started = time.monotonic()
            self.live_ws_finalize_pending = True
            self.live_stop_event.set()
            app = self.assemblyai_ws_app
            if app:
                try:
                    app.send(json.dumps({"type": "Terminate"}))
                except Exception:
                    pass
                try:
                    app.close()
                except Exception:
                    pass
            self.assemblyai_ws_done_event.set()
            self.assemblyai_ws_app = None
            self.live_uses_assemblyai_websocket = False
            self._consolidate_live_text_now()
            return
        if self.live_uses_deepgram_websocket:
            # Parar é imediato: avisa o servidor, fecha o socket e consolida
            # o texto acumulado na hora — sem esperar confirmação final.
            self.deepgram_ws_intentional_close = True
            self._begin_activity_step("live:ws_finalize", "Websocket encerrado.")
            self.live_ws_finalize_started = time.monotonic()
            self.live_ws_finalize_pending = True
            self.live_stop_event.set()
            app = self.deepgram_ws_app
            if app:
                try:
                    app.send(json.dumps({"type": "CloseStream"}))
                except Exception:
                    pass
                try:
                    app.close()
                except Exception:
                    pass
            self.deepgram_ws_done_event.set()
            self.deepgram_ws_app = None
            self.live_uses_deepgram_websocket = False
            self._consolidate_live_text_now()
            return
        if self.live_uses_grok_websocket:
            # Parar é imediato: avisa o servidor, fecha o socket e consolida
            # o texto acumulado na hora — sem esperar confirmação final.
            self.grok_ws_intentional_close = True
            self._begin_activity_step("live:ws_finalize", "Websocket encerrado.")
            self.live_ws_finalize_started = time.monotonic()
            self.live_ws_finalize_pending = True
            self.live_stop_event.set()
            app = self.grok_ws_app
            if app:
                try:
                    app.send(json.dumps({"type": "audio.done"}))
                except Exception:
                    pass
                try:
                    app.close()
                except Exception:
                    pass
            self.grok_ws_done_event.set()
            self.grok_ws_app = None
            self.live_uses_grok_websocket = False
            self._consolidate_live_text_now()
            return
        self._begin_activity_step("live:ws_finalize", "Encerrando. Consolidando transcrição")
        self.live_ws_finalize_started = time.monotonic()
        self.live_ws_finalize_pending = True
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

    def cancel_live_mic(self):
        if self.live_state == "idle":
            return
        self.live_stop_event.set()
        self.live_abort_event.set()
        self.live_recovery_cancel_event.set()
        self.live_audio_recovery_available = False
        self.live_output_finished = True
        self.live_ws_finalize_pending = False
        self._finish_ws_finalize_step()
        self._set_live_audio_recovery_visible(False)
        self.grok_ws_intentional_close = True
        self.deepgram_ws_intentional_close = True
        self.assemblyai_ws_intentional_close = True
        self.elevenlabs_ws_intentional_close = True
        self.metamuse_ws_intentional_close = True
        self.alibaba_ws_intentional_close = True
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
        if self.metamuse_ws_app:
            try:
                self.metamuse_ws_app.close(status=1000, reason="Cancelado")
            except Exception:
                pass
        self.metamuse_ws_app = None
        if self.alibaba_ws_app:
            try:
                self.alibaba_ws_app.close(status=1000, reason="Cancelado")
            except Exception:
                pass
        self.alibaba_ws_app = None
        self.live_uses_grok_websocket = False
        self.live_uses_deepgram_websocket = False
        self.live_uses_assemblyai_websocket = False
        self.live_uses_elevenlabs_websocket = False
        self.live_uses_metamuse_websocket = False
        self.live_uses_alibaba_websocket = False
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
        if not self.live_started_at:
            # Streaming ainda conectando: o relógio só dispara ao conectar.
            self.live_timer_var.set("00:00.000")
            self.root.after(200, self._tick_live_timer)
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
        for key, term in stt_provider_rules.keywords_query_params(self.settings, "grok"):
            query += f"&{key}={quote(term)}"
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
            if is_metamuse_transcription(settings):
                transcript = metamuse_rest_transcribe(
                    self.live_abort_event, settings, wav_path, raw_path
                )
            elif is_alibaba_transcription(settings):
                transcript = alibaba_rest_transcribe(
                    self.live_abort_event, settings, wav_path, raw_path
                )
            else:
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
            if is_metamuse_transcription(settings):
                transcript = metamuse_rest_transcribe(
                    self.live_abort_event, settings, wav_path, raw_path
                )
                if not transcript.strip():
                    raise RuntimeError("resposta vazia")
            elif is_alibaba_transcription(settings):
                transcript = alibaba_rest_transcribe(
                    self.live_abort_event,
                    settings,
                    wav_path,
                    raw_path,
                    self._alibaba_vocabulary_for(settings, ALIBABA_REST_MODEL),
                )
                if not transcript.strip():
                    raise RuntimeError("resposta vazia")
            else:
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

    def _consolidate_live_text_now(self):
        """Consolida o texto acumulado na hora (Parar imediato dos WS).

        Usado por todos os provedores de streaming: o Parar só consolida o
        que já chegou (inclui o payload de timestamps quando houver) — sem
        esperar confirmação final do servidor e sem requisição REST extra.
        """
        with self.live_lock:
            text = self.live_committed_text.strip() or self._current_live_text_locked().strip()
            self.live_committed_text = text
            self.live_draft_text = ""
        timestamped = (self.live_timestamped_transcript_text or "").strip()
        if not text:
            self._queue("status", "Transcrição ao vivo finalizada sem conteúdo.")
        self._queue("live_display", text)
        if timestamped:
            self._queue("live_payload", text, timestamped, True)
        self._finish_ws_finalize_step()
        self._finish_live_output()

    def _finish_metamuse_session(self):
        self.metamuse_ws_done_event.set()
        self.metamuse_ws_app = None
        self.live_uses_metamuse_websocket = False
        self._consolidate_live_text_now()

    def _finish_alibaba_session(self):
        self.alibaba_ws_done_event.set()
        self.alibaba_ws_app = None
        self.alibaba_ws_task_id = ""
        self.live_uses_alibaba_websocket = False
        self._consolidate_live_text_now()

    def _alibaba_live_capture_loop(self, settings: dict):
        try:
            import sounddevice as sd
            import websocket
        except Exception as exc:
            self._queue("live_error", f"Streaming do Alibaba indisponível: {exc}")
            return

        api_key = str(settings.get("alibaba_api_key") or "").strip()
        if not api_key:
            self._queue("live_error", "Insira a chave API do Alibaba Cloud nas configurações.")
            return

        task_id = uuid.uuid4().hex
        self.alibaba_ws_task_id = task_id
        # Hotwords: a lista pré-compilada é criada/retomada UMA vez por sessão
        # (antes de conectar), porque criar vale na hora, mas atualizar demora
        # até 5 min. Sem termos/chave, segue sem lista (transcrição normal).
        alibaba_vocabulary_id = self._alibaba_vocabulary_for(settings, ALIBABA_WS_MODEL)
        if alibaba_vocabulary_id:
            self._queue(
                "activity",
                f"Alibaba: lista de keywords pronta ({len(keywords_for_provider(settings, 'alibaba'))} termos).",
                "activity_step_done",
            )
        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        full_pcm_lock = threading.Lock()
        full_pcm = None

        def send_pcm(app, chunk: bytes) -> bool:
            try:
                app.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
            except Exception:
                return False
            return True

        def commit_live_text(text: str) -> None:
            clean = (text or "").strip()
            if not clean or self.alibaba_ws_done_event.is_set():
                return
            with self.live_lock:
                committed = self.live_committed_text.strip()
                if not committed:
                    self.live_committed_text = clean
                elif clean not in committed:
                    self.live_committed_text = f"{committed}\n{clean}"
                self.live_draft_text = ""
                display = self._current_live_text_locked()
            self._queue("live_display", display)

        def describe_error(event: dict) -> str:
            header = event.get("header") if isinstance(event, dict) else None
            header = header if isinstance(header, dict) else {}
            code = str(header.get("error_code") or "")
            message = str(header.get("error_message") or header.get("message") or "").strip()
            if code in ("InvalidApiKey", "Unauthorized", "Forbidden", "AccessDenied") or "401" in code or "403" in code:
                return ALIBABA_AUTH_ERROR
            if code == "Throttling" or "429" in code or "limit" in message.casefold():
                return "Alibaba Cloud: rate limit / limite de uso excedido. Aguarde e tente novamente."
            return message or f"erro {code or 'desconhecido'} do Alibaba"

        def on_open(_app):
            if _app is not self.alibaba_ws_app:
                return
            try:
                _app.send(json.dumps(alibaba_ws_run_task(task_id, self.settings, alibaba_vocabulary_id)))
            except Exception:
                self.alibaba_ws_lost_event.set()
                self._queue("status", "Reconectando: falha ao enviar o run-task do Alibaba.")

        def on_message(_app, raw_event):
            if _app is not self.alibaba_ws_app:
                return
            try:
                event = json.loads(raw_event)
            except Exception:
                self.alibaba_ws_lost_event.set()
                self._queue("status", "Reconectando: resposta inválida do Alibaba.")
                return
            if not isinstance(event, dict):
                return
            header = event.get("header") or {}
            event_type = str(header.get("event") or "") if isinstance(header, dict) else ""
            if event_type == "task-started":
                self.alibaba_ws_ready_event.set()
                self._queue("status", "Conectado ao Alibaba. Ouvindo e transcrevendo ao vivo...")
                return
            if event_type == "result-generated":
                # Segmentos: frase fechada (end_time) commita; parcial vira rascunho.
                text, is_final = alibaba_ws_sentence_text(event)
                if not text or self.alibaba_ws_done_event.is_set():
                    return
                if is_final:
                    commit_live_text(text)
                else:
                    with self.live_lock:
                        self.live_draft_text = text
                        display = self._current_live_text_locked()
                    self._queue("live_display", display)
                return
            if event_type == "task-finished":
                if not self.alibaba_ws_done_event.is_set():
                    self._finish_alibaba_session()
                return
            if event_type == "task-failed":
                self.alibaba_ws_lost_event.set()
                self._queue("status", f"Reconectando: {describe_error(event)}")
                return

        def on_error(_app, _error):
            if (
                _app is self.alibaba_ws_app
                and not self.alibaba_ws_intentional_close
                and not self.live_abort_event.is_set()
                and not self.alibaba_ws_done_event.is_set()
            ):
                self._queue("status", f"Erro do Alibaba: {_error}")
                self.alibaba_ws_lost_event.set()

        def on_close(_app, _status_code, _message):
            if _app is not self.alibaba_ws_app:
                return
            if self.alibaba_ws_intentional_close and not self.alibaba_ws_done_event.is_set():
                self._finish_alibaba_session()
                return
            if (
                not self.alibaba_ws_intentional_close
                and not self.live_abort_event.is_set()
                and not self.alibaba_ws_done_event.is_set()
            ):
                self._queue("status", f"Alibaba fechou a conexão (código {_status_code}): {_message}")
                self.alibaba_ws_lost_event.set()

        def connect() -> bool:
            previous = self.alibaba_ws_app
            self.alibaba_ws_app = None
            if previous:
                try:
                    previous.close()
                except Exception:
                    pass
            self.alibaba_ws_ready_event.clear()
            self.alibaba_ws_lost_event.clear()
            self._queue("params_block", "Parâmetros Alibaba", alibaba_ws_log_params(self.settings))
            hints = alibaba_language_hints(self.settings)
            self._queue(
                "status_silent",
                f"Parâmetros Alibaba: {ALIBABA_WS_MODEL} pcm 16kHz {hints if hints else 'auto'}",
            )
            # A credencial vai no handshake (header), nunca no log.
            app = websocket.WebSocketApp(
                ALIBABA_WEBSOCKET_URL,
                header=[f"Authorization: bearer {api_key}"],
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            self.alibaba_ws_app = app
            self.alibaba_ws_thread = threading.Thread(
                target=lambda: app.run_forever(ping_interval=30, ping_timeout=10),
                daemon=True,
            )
            self.alibaba_ws_thread.start()
            deadline = time.monotonic() + 15
            while not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                if self.alibaba_ws_ready_event.wait(0.1):
                    if not self.live_started_at:
                        self.live_started_at = time.time()
                    return True
                if self.alibaba_ws_lost_event.is_set() or time.monotonic() >= deadline:
                    return False
            return False

        def reconnect(attempt: int) -> bool:
            delay = min(8.0, 0.5 * (2 ** max(0, attempt - 1))) + random.uniform(0.0, 0.25)
            self._queue("status", f"Reconectando ao Alibaba ({attempt}/{GROK_RECONNECT_MAX_ATTEMPTS}) em {delay:.1f}s...")
            if self.live_abort_event.wait(delay) or self.live_stop_event.is_set():
                return False
            if not connect():
                return False
            self._queue("status", "Reconectou ao Alibaba; o áudio do intervalo foi descartado.")
            return True

        def audio_callback(indata, _frames, _time_info, _status):
            if self.live_stop_event.is_set() or self.live_abort_event.is_set():
                return
            chunk = bytes(indata)
            if not self.live_started_at:
                # Ainda conectando: nada é gravado antes da conexão.
                return
            if self.live_state == "paused":
                # Pausado: só silêncio para segurar a sessão; nada é registrado.
                try:
                    audio_queue.put_nowait(bytes(len(chunk)))
                except queue.Full:
                    pass
                return
            self._push_live_waveform_chunk(chunk)
            self._queue_secondary_audio(chunk)
            with full_pcm_lock:
                if full_pcm is not None:
                    full_pcm.write(chunk)
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
                    if not connected or self.alibaba_ws_lost_event.is_set():
                        reconnecting = connected or self.alibaba_ws_lost_event.is_set() or attempts > 0
                        attempts += 1
                        self._queue("status", "Reconectando ao streaming do Alibaba..." if reconnecting else "Conectando ao streaming do Alibaba...")
                        connected = reconnect(attempts) if reconnecting else connect()
                        if connected:
                            attempts = 0
                            continue
                        if attempts >= GROK_RECONNECT_MAX_ATTEMPTS:
                            self._queue("live_error", "Falhou: reconexão do Alibaba esgotada após 8 tentativas.")
                            return
                        continue
                    try:
                        chunk = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if not chunk:
                        continue
                    if self.live_state == "paused":
                        # Padding de silêncio: segura a sessão sem registrar nada.
                        if not send_pcm(self.alibaba_ws_app, chunk):
                            self.alibaba_ws_lost_event.set()
                            connected = False
                        continue
                    try:
                        if not send_pcm(self.alibaba_ws_app, chunk):
                            raise RuntimeError("envio falhou")
                    except Exception:
                        self.alibaba_ws_lost_event.set()
                        connected = False
        except Exception as exc:
            if not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                self._queue("live_error", f"Falhou: erro no microfone ao vivo: {exc}")
        finally:
            with full_pcm_lock:
                if full_pcm is not None:
                    full_pcm.close()
                    full_pcm = None

    def _metamuse_live_capture_loop(self, settings: dict):
        try:
            import sounddevice as sd
            import websocket
        except Exception as exc:
            self._queue("live_error", f"Streaming do Muse indisponível: {exc}")
            return

        api_key = str(settings.get("metamuse_api_key") or "").strip()
        if not api_key:
            self._queue("live_error", "Insira a chave API do Meta Muse Voice nas configurações.")
            return

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        buffered_pcm: deque[bytes] = deque()
        buffered_bytes = 0
        buffer_limit = pcm_bytes_for_millis(GROK_RECONNECT_BUFFER_MILLIS)
        buffer_lock = threading.Lock()
        full_pcm_lock = threading.Lock()
        full_pcm = None
        speaker_order: dict[str, int] = {}
        current_speaker: dict[str, str] = {"label": ""}

        def speaker_number(label: str) -> int:
            if label not in speaker_order:
                speaker_order[label] = len(speaker_order) + 1
            return speaker_order[label]

        def remember(chunk: bytes) -> None:
            nonlocal buffered_bytes
            with buffer_lock:
                buffered_pcm.append(chunk)
                buffered_bytes += len(chunk)
                while buffered_pcm and buffered_bytes > buffer_limit:
                    buffered_bytes -= len(buffered_pcm.popleft())

        def send_pcm(app, chunk: bytes) -> bool:
            try:
                app.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
            except Exception:
                return False
            return True

        def prefixed(text: str, label: str) -> str:
            clean = (text or "").strip()
            if self.live_grok_diarize and label:
                return f"Interlocutor {speaker_number(str(label))}: {clean}"
            return clean

        def commit_live_text(text: str) -> None:
            clean = (text or "").strip()
            if not clean or self.metamuse_ws_done_event.is_set():
                return
            with self.live_lock:
                committed = self.live_committed_text.strip()
                if not committed:
                    self.live_committed_text = clean
                elif clean not in committed:
                    self.live_committed_text = f"{committed}\n{clean}"
                self.live_draft_text = ""
                display = self._current_live_text_locked()
            self._queue("live_display", display)

        def on_open(_app):
            if _app is not self.metamuse_ws_app:
                return
            try:
                _app.send(json.dumps(metamuse_handshake_payload(api_key, self.live_grok_diarize, self.settings)))
            except Exception:
                self.metamuse_ws_lost_event.set()
                self._queue("status", "Reconectando: falha ao enviar o handshake do Muse.")

        def on_message(_app, raw_event):
            if _app is not self.metamuse_ws_app:
                return
            try:
                event = json.loads(raw_event)
            except Exception:
                self.metamuse_ws_lost_event.set()
                self._queue("status", "Reconectando: resposta inválida do Muse.")
                return
            if not isinstance(event, dict):
                return
            # A resposta do handshake é um struct sem "type" (só sessionId).
            if "type" not in event and "sessionId" in event:
                self.metamuse_ws_ready_event.set()
                self._queue("status", "Conectado ao Muse. Ouvindo e transcrevendo ao vivo...")
                return
            event_type = str(event.get("type") or "")
            if event_type == "transcript":
                # Parciais são cumulativas: cada uma substitui a anterior.
                text = str(event.get("transcript") or "").strip()
                if not text or self.metamuse_ws_done_event.is_set():
                    return
                if event.get("final"):
                    commit_live_text(prefixed(text, current_speaker["label"]))
                else:
                    with self.live_lock:
                        self.live_draft_text = prefixed(text, current_speaker["label"])
                        display = self._current_live_text_locked()
                    self._queue("live_display", display)
                return
            if event_type == "speaker":
                # Rotula o trecho ANTERIOR; letras (A, B, ...) viram
                # Interlocutor 1, 2, ... na ordem de aparição.
                label = str(event.get("label") or "").strip()
                if label:
                    current_speaker["label"] = label
                    speaker_number(label)
                return
            if event_type in ("speechStart", "speechEnd", "audioProgress"):
                return
            if event_type == "speechComplete":
                text = str(event.get("transcript") or "").strip()
                label = str(event.get("speaker") or "").strip() or current_speaker["label"]
                if text:
                    commit_live_text(prefixed(text, label))
                else:
                    with self.live_lock:
                        self.live_draft_text = ""
                if self.metamuse_ws_intentional_close and not self.metamuse_ws_done_event.is_set():
                    self._finish_metamuse_session()
                return
            if event_type == "error":
                self.metamuse_ws_lost_event.set()
                self._queue(
                    "status",
                    f"Reconectando: {str(event.get('message') or 'erro do Muse')}",
                )
                return

        def on_error(_app, _error):
            if (
                _app is self.metamuse_ws_app
                and not self.metamuse_ws_intentional_close
                and not self.live_abort_event.is_set()
                and not self.metamuse_ws_done_event.is_set()
            ):
                self._queue("status", f"Erro do Muse: {_error}")
                self.metamuse_ws_lost_event.set()

        def on_close(_app, _status_code, _message):
            if _app is not self.metamuse_ws_app:
                return
            if self.metamuse_ws_intentional_close and not self.metamuse_ws_done_event.is_set():
                self._finish_metamuse_session()
                return
            if (
                not self.metamuse_ws_intentional_close
                and not self.live_abort_event.is_set()
                and not self.metamuse_ws_done_event.is_set()
            ):
                self._queue("status", f"Muse fechou a conexão (código {_status_code}): {_message}")
                self.metamuse_ws_lost_event.set()

        def connect() -> bool:
            previous = self.metamuse_ws_app
            self.metamuse_ws_app = None
            if previous:
                try:
                    previous.close()
                except Exception:
                    pass
            self.metamuse_ws_ready_event.clear()
            self.metamuse_ws_lost_event.clear()
            preview = metamuse_handshake_payload("***", self.live_grok_diarize, self.settings)
            preview.pop("authorization", None)
            self._queue("status_silent", f"Parâmetros Muse: {json.dumps(preview, ensure_ascii=False)}")
            self._queue(
                "params_block",
                "Parâmetros Muse",
                metamuse_ws_log_params(self.settings, self.live_grok_diarize),
            )
            # Sem header de autenticação: a credencial vai no handshake JSON.
            app = websocket.WebSocketApp(
                META_MUSE_STT_WEBSOCKET_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            self.metamuse_ws_app = app
            self.metamuse_ws_thread = threading.Thread(
                target=lambda: app.run_forever(ping_interval=30, ping_timeout=10),
                daemon=True,
            )
            self.metamuse_ws_thread.start()
            deadline = time.monotonic() + 15
            while not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                if self.metamuse_ws_ready_event.wait(0.1):
                    if not self.live_started_at:
                        self.live_started_at = time.time()
                    return True
                if self.metamuse_ws_lost_event.is_set() or time.monotonic() >= deadline:
                    return False
            return False

        def reconnect(attempt: int) -> bool:
            delay = min(8.0, 0.5 * (2 ** max(0, attempt - 1))) + random.uniform(0.0, 0.25)
            self._queue("status", f"Reconectando ao Muse ({attempt}/{GROK_RECONNECT_MAX_ATTEMPTS}) em {delay:.1f}s...")
            if self.live_abort_event.wait(delay) or self.live_stop_event.is_set():
                return False
            if not connect():
                return False
            # Sem reenvio do buffer: o servidor derruba a sessão com ~5s de
            # backlog (código 1008), então o streaming recomeça do áudio atual.
            self._queue("status", "Reconectou ao Muse; o áudio do intervalo foi descartado.")
            return True

        def audio_callback(indata, _frames, _time_info, _status):
            if self.live_stop_event.is_set() or self.live_abort_event.is_set():
                return
            chunk = bytes(indata)
            if not self.live_started_at:
                # Ainda conectando: nada é gravado antes da conexão.
                return
            if self.live_state == "paused":
                # Pausado: alimenta o socket só com silêncio para a sessão não
                # cair por falta de ingresso; nada vai para a forma de onda,
                # o áudio secundário ou o integral.
                try:
                    audio_queue.put_nowait(bytes(len(chunk)))
                except queue.Full:
                    pass
                return
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
            bytes_per_second = LIVE_SAMPLE_RATE * LIVE_SAMPLE_WIDTH * LIVE_CHANNELS
            pace_started = time.monotonic()
            paced_bytes = 0
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
                    if not connected or self.metamuse_ws_lost_event.is_set():
                        reconnecting = connected or self.metamuse_ws_lost_event.is_set() or attempts > 0
                        attempts += 1
                        self._queue("status", "Reconectando ao streaming do Muse..." if reconnecting else "Conectando ao streaming do Muse...")
                        connected = reconnect(attempts) if reconnecting else connect()
                        if connected:
                            attempts = 0
                            pace_started = time.monotonic()
                            paced_bytes = 0
                            continue
                        if attempts >= GROK_RECONNECT_MAX_ATTEMPTS:
                            self._queue("live_error", "Falhou: reconexão do Muse esgotada após 8 tentativas.")
                            return
                        continue
                    try:
                        chunk = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if not chunk:
                        continue
                    if self.live_state == "paused":
                        # Padding de silêncio: segura a sessão sem registrar nada.
                        if send_pcm(self.metamuse_ws_app, chunk):
                            paced_bytes += len(chunk)
                        else:
                            self.metamuse_ws_lost_event.set()
                            connected = False
                        continue
                    try:
                        if not send_pcm(self.metamuse_ws_app, chunk):
                            raise RuntimeError("envio falhou")
                        # Pacing em tempo real: rajadas (reconexão) derrubam
                        # a sessão por backlog (1008); o microfone já é
                        # realtime, então em regime isto é no-op.
                        paced_bytes += len(chunk)
                        behind = pace_started + paced_bytes / bytes_per_second - time.monotonic()
                        if behind > 0:
                            time.sleep(min(behind, 1.0))
                    except Exception:
                        self.metamuse_ws_lost_event.set()
                        connected = False
        except Exception as exc:
            if not self.live_stop_event.is_set() and not self.live_abort_event.is_set():
                self._queue("live_error", f"Falhou: erro no microfone ao vivo: {exc}")
        finally:
            with full_pcm_lock:
                if full_pcm is not None:
                    full_pcm.close()
                    full_pcm = None

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
            try:
                app.send(payload)
            except Exception:
                return False
            return True

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
                # O Scribe v2 envia CADA frase finalizada como
                # committed_transcript (com o texto). Acumula no committed
                # para a transcricao nao se perder (so o draft ficaria).
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
            self._finish_ws_finalize_step()
            self._finish_live_output()

        def on_error(_app, _error):
            if (
                _app is self.elevenlabs_ws_app
                and not self.elevenlabs_ws_intentional_close
                and not self.live_abort_event.is_set()
                and not self.elevenlabs_ws_done_event.is_set()
            ):
                self._queue("status", f"Erro do Scribe: {_error}")
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
                self._queue("status", f"Scribe fechou a conexão (código {_status_code}): {_message}")
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
            query += "&vad_silence_threshold_secs=1.0"
            for key, term in stt_provider_rules.keywords_query_params(self.settings, "elevenlabs"):
                query += f"&{key}={quote(term)}"
            self._queue("status_silent", f"Parâmetros Scribe: {query}")
            self._queue(
                "params_block",
                "Parâmetros Scribe",
                urllib.parse.parse_qsl(query, keep_blank_values=True),
            )
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
                    if not self.live_started_at:
                        self.live_started_at = time.time()
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
            if not self.live_started_at:
                # Ainda conectando: nada é gravado antes da conexão.
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
                    self._finish_ws_finalize_step()
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
                self._finish_ws_finalize_step()
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
            # Keywords: `keyterms_prompt` recebe o array em JSON (um parâmetro).
            for key, value in stt_provider_rules.keywords_query_params(self.settings, "assemblyai"):
                query += f"&{key}={quote(value)}"
            diarize_param = assemblyai_ws_diarize_query(bool(self.live_grok_diarize))
            if diarize_param:
                query += f"&{diarize_param}"
            self._queue("status_silent", f"Parâmetros AssemblyAI: {query}")
            self._queue(
                "params_block",
                "Parâmetros AssemblyAI",
                urllib.parse.parse_qsl(query, keep_blank_values=True),
            )
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
                    if not self.live_started_at:
                        self.live_started_at = time.time()
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
            if not self.live_started_at:
                # Ainda conectando: nada é gravado antes da conexão.
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
                self._finish_ws_finalize_step()
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
            self._queue("status_silent", f"Parâmetros Deepgram: {query}")
            self._queue(
                "params_block",
                "Parâmetros Deepgram",
                urllib.parse.parse_qsl(query, keep_blank_values=True),
            )
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
                    if not self.live_started_at:
                        self.live_started_at = time.time()
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
            if not self.live_started_at:
                # Ainda conectando: nada é gravado antes da conexão.
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
                self._finish_ws_finalize_step()
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
            for key, term in stt_provider_rules.keywords_query_params(self.settings, "grok"):
                query += f"&{key}={quote(term)}"
            if self.live_grok_diarize:
                query += "&diarize=true"
            self._queue("status_silent", f"Parâmetros: {query}")
            self._queue(
                "params_block",
                "Parâmetros",
                urllib.parse.parse_qsl(query, keep_blank_values=True),
            )
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
                    if not self.live_started_at:
                        self.live_started_at = time.time()
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
            if not self.live_started_at:
                # Ainda conectando: nada é gravado antes da conexão.
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
                self._finish_ws_finalize_step()
                self._finish_live_output()
                return
            # A transcrição definitiva por REST (reupload do áudio integral) foi
            # removida do provedor primário: o texto final é o já acumulado das
            # janelas ao vivo. O modelo secundário (Granite) mantém a própria
            # requisição final em _transcribe_secondary_definitive.
            with self.live_lock:
                text = self.live_committed_text.strip() or self._current_live_text_locked().strip()
                self.live_committed_text = text
                self.live_draft_text = ""
            timestamped = (self.live_timestamped_transcript_text or "").strip()
            if not text:
                self._queue("status", "Transcrição ao vivo finalizada sem conteúdo.")
            self._queue("live_display", text)
            if timestamped:
                self._queue("live_payload", text, timestamped, True)
            self._finish_ws_finalize_step()
            self._finish_live_output()
        finally:
            try:
                if self.live_full_pcm_path:
                    self.live_full_pcm_path.unlink(missing_ok=True)
            except Exception:
                pass
            self.live_full_pcm_path = None

    def _finish_ws_finalize_step(self) -> None:
        """Encerra a etapa 'Websocket encerrado. Recebendo transcrição' na UI thread."""
        started = self.live_ws_finalize_started
        self._queue("activity_step_finish", "live:ws_finalize", time.monotonic() - started if started else 0.0)

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
        if not self.live_ws_finalize_pending:
            # Encerramento fora do fluxo do botão Parar (ex.: transcript.done
            # espontâneo do servidor): registra o tempo do ciclo ao vivo.
            elapsed = max(0.0, time.time() - (getattr(self, "live_started_at", 0.0) or time.time()))
            self._queue("status", f"Transcrição ao vivo finalizada ({elapsed:.1f}s)")

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
        if not self.live_secondary_done_event.is_set():
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
        # Capture a seleção feita na aba antes de recarregar as preferências;
        # essa seleção é local ao lote e não deve desaparecer no reload.
        multi_model_names = self._selected_multi_transcription_model_names()
        self.settings = load_settings()
        # Se o usuário nunca abriu o menu "Modelos" (vars vazias), vale a
        # seleção salva da Transcrição (padrão: servidor Granite NAR) — nunca
        # o modelo da aba Ocorrência, que é compartilhado no settings.
        if not multi_model_names:
            configured = self._default_transcription_model_name()
            if configured:
                multi_model_names = [configured]
        if not multi_model_names:
            messagebox.showinfo(
                "Modelos",
                "Selecione pelo menos um modelo de transcrição no botão 'Modelos' da aba Transcrição.",
            )
            return
        # Cópia do lote: é ELA que define o modelo e o idioma realmente usados
        # (o `transcription_server` é compartilhado com a aba Ocorrência).
        workflow_settings = self._transcription_batch_settings(multi_model_names)
        multi_transcription = len(multi_model_names) >= 2
        if is_grok_transcription(workflow_settings) and not workflow_settings.get("grok_api_key"):
            messagebox.showerror("sig", "Insira a chave API do Grok nas configurações antes de transcrever.")
            return
        if is_grok_transcription(workflow_settings) and self.send_zip_var.get():
            self.send_zip_var.set(False)
            self._refresh_zip_controls()
            self.status_var.set("Grok STT envia os arquivos individualmente por REST; o envio ZIP foi desativado.")
        if is_metamuse_transcription(workflow_settings) and self.send_zip_var.get():
            self.send_zip_var.set(False)
            self._refresh_zip_controls()
            self.status_var.set("Meta Muse Voice envia os arquivos individualmente por REST; o envio ZIP foi desativado.")
        if is_alibaba_transcription(workflow_settings) and self.send_zip_var.get():
            self.send_zip_var.set(False)
            self._refresh_zip_controls()
            self.status_var.set("Alibaba Fun ASR/Qwen envia os arquivos individualmente por REST; o envio ZIP foi desativado.")
        if multi_transcription and self.send_zip_var.get():
            self.send_zip_var.set(False)
            self._refresh_zip_controls()
            self.status_var.set("Multi model usa requisições individuais; o envio ZIP foi desativado.")
        self.cancel_event.clear()
        self.uploader = create_transcription_uploader(self.cancel_event, workflow_settings)
        self.uploaders = [self.uploader]
        self.running = True
        self.last_html_path = None
        self.progress_var.set(0)
        self._draw_action_button()
        self._draw_save_button()
        self._set_controls_state("disabled")
        self._set_activity_status("Preparando fila...", log=False)
        self._begin_activity_step("prepare", "Preparando fila")
        self._prepare_started = time.perf_counter()
        paths = list(self.selected_paths)
        mode = self.mode_var.get()
        convert_only = self.convert_only_var.get()
        vad_only = self.vad_only_var.get()
        vad_mode = self.vad_var.get()
        transcribe_after_convert = self.transcribe_after_convert_var.get()
        send_zip = self.send_zip_var.get() and not convert_only and not vad_only
        zip_level = self.zip_level_var.get()
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
        audio_dir = temp_dir / "audios"
        txt_dir = temp_dir / "txt"
        temp_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)
        txt_dir.mkdir(parents=True, exist_ok=True)

        # Arquivos menores entram primeiro para a fila começar a avançar rapidamente.
        paths = sorted(paths, key=lambda p: p.stat().st_size)
        stems = safe_stems(paths)
        jobs = []
        primary_server = selected_transcription_server(settings)
        selected_model_names = list(settings.get("_multi_transcription_models") or [])
        if settings.get("_multi_transcription") and len(selected_model_names) >= 2:
            transcription_model_names = selected_model_names
        else:
            transcription_model_names = [primary_server["name"]]
        multi_transcription = len(transcription_model_names) >= 2
        use_vad = vad_mode != "Off" and not convert_only
        for path in paths:
            stem = stems[path]
            job = AudioJob(
                original_path=path,
                original_name=path.name,
                stem=stem,
                mode=mode,
                txt_path=txt_dir / f"{stem}.txt",
                raw_path=raw_dir / f"{stem}.json",
                log_path=log_dir / f"{stem}.ffmpeg.log",
                model_name=transcription_model_names[0],
                model_names=transcription_model_names[1:],
                txt_paths=(
                    [txt_dir / f"{stem}.modelo_{i}.txt" for i in range(2, len(transcription_model_names) + 1)]
                    if multi_transcription
                    else []
                ),
                raw_paths=(
                    [raw_dir / f"{stem}.modelo_{i}.json" for i in range(2, len(transcription_model_names) + 1)]
                    if multi_transcription
                    else []
                ),
            )
            if use_vad or vad_only:
                # Todo VAD recebe exatamente WAV PCM 16 kHz, mono e 16-bit.
                job.mode = "ready"
                job.converted_path = audio_dir / f"{stem}.vad_entrada.wav"
                job.vad_output_path = audio_dir / f"{stem}.vad.wav"
            elif is_video_file(path):
                job.mode = "ready"
                job.converted_path = audio_dir / f"{stem}.wav"
            elif mode == "ready":
                job.converted_path = audio_dir / f"{stem}.wav"
            elif mode == "compact":
                job.converted_path = audio_dir / f"{stem}.ogg"
            else:
                job.upload_path = path
            jobs.append(job)

        # Lote com mais de um arquivo na aba Transcrição: não poluir o log com
        # cada comando FFmpeg nem com o resumo de cada arquivo — a linha viva
        # "Convertendo arquivos: N/M" já informa o progresso (regra do usuário).
        self._suppress_ffmpeg_command_log = len(jobs) > 1
        self._queue("activity_step_finish", "prepare", time.perf_counter() - getattr(self, "_prepare_started", time.perf_counter()))

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
                    self._queue("status_silent", "Convertido.")
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
        vad_started = time.perf_counter()

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
                    self._queue("tree_size", job.original_path, self._job_size_column_text(job))
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
            self._queue_phase_progress("Aplicando VAD", completed, len(eligible), "vad", vad_started)

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
            self._queue_phase_progress("Aplicando VAD", completed, len(eligible), "vad", vad_started)
        if all(job.error for job in eligible):
            raise RuntimeError("o VAD falhou em todos os arquivos")

    def _queue_phase_progress(self, label: str, done: int, total: int, phase_key: str | None = None, started: float | None = None):
        percent = int((done / max(total, 1) * 100) + 0.5)
        self._queue("progress", percent)
        now = time.perf_counter()
        throttles = getattr(self, "_phase_throttle", None)
        if throttles is None:
            throttles = {}
            self._phase_throttle = throttles
        if done < total and phase_key and now - throttles.get(phase_key, 0.0) < 0.1:
            return
        if phase_key:
            throttles[phase_key] = now
        if done >= total and started is not None:
            elapsed = time.perf_counter() - started
            message = f"{label}: {done}/{total} ({format_duration(elapsed)})"
            tag = "vad_total"
        else:
            message = f"{label}: {done}/{total} ({percent}%)"
            tag = None
        if phase_key:
            self._queue("activity_line", phase_key, message, tag)
            # Atualiza a barra de status sem repetir a linha no log (a linha viva
            # do log já mostra o progresso).
            self._queue("status_silent", message)
        else:
            self._queue("status", message)

    def _queue_pipeline_progress(self, converted_done: int, total: int, transcribed_done: int, convert_started: float, transcribe_started: float):
        convert_percent = int((converted_done / max(total, 1) * 100) + 0.5)
        transcribe_percent = int((transcribed_done / max(total, 1) * 100) + 0.5)
        current_percent = convert_percent if converted_done < total else transcribe_percent
        self._queue("progress", current_percent)
        if converted_done >= total:
            self._queue("activity_line", "convert", f"Convertendo arquivos: {converted_done}/{total} ({format_duration(time.perf_counter() - convert_started)})", "vad_total")
        else:
            self._queue("activity_line", "convert", f"Convertendo arquivos: {converted_done}/{total} ({convert_percent}%)", None)
        if transcribed_done >= total:
            self._queue("activity_line", "transcribe", f"Transcrevendo arquivos: {transcribed_done}/{total} ({format_duration(time.perf_counter() - transcribe_started)})", "vad_total")
        else:
            self._queue("activity_line", "transcribe", f"Transcrevendo arquivos: {transcribed_done}/{total} ({transcribe_percent}%)", None)

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
            model_names = list(settings.get("_multi_transcription_models") or [])
            if settings.get("_multi_transcription") and len(model_names) >= 2:
                valid = any(
                    not job_problem_reason_for_model(
                        job,
                        job_transcript_for_model(job, index),
                        index,
                    )
                    for index in range(1, min(3, len(model_names)) + 1)
                )
            else:
                valid = not job_problem_reason(job, job_transcript_text(job))
            if valid:
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
        if settings.get("_multi_transcription"):
            for index, name in enumerate(settings.get("_multi_transcription_models") or [], start=1):
                stats.append((f"Modelo {index}", str(name)))
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
        # Mede a conversão desde o início do lote (quando "Preparando fila"
        # apareceu) para o tempo mostrado bater com o relógio do log
        # (preparação + conversão), sem "sumir" com a preparação.
        convert_started = getattr(self, "_prepare_started", time.perf_counter())
        self._queue_phase_progress("Convertendo arquivos", done, total, "convert", convert_started)
        convert_workers = max(1, int(settings.get("convert_parallel") or 1))
        with concurrent.futures.ThreadPoolExecutor(max_workers=convert_workers) as executor:
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
                    self._queue("job", job.original_path, self._conversion_failure_status(exc))
                    self._queue("activity", f"{job.original_name}: {job.error}", "activity_step_error")
                done += 1
                self._queue_phase_progress("Convertendo arquivos", done, total, "convert", convert_started)

    def _run_pipelined_conversions_and_transcriptions(self, jobs: list[AudioJob], settings: dict):
        total = len(jobs)
        converted_done = 0
        transcribed_done = 0
        progress_lock = threading.Lock()
        converted_queue: queue.Queue = queue.Queue()
        sentinel = object()
        url = transcribe_url(settings)
        convert_started = time.perf_counter()
        transcribe_started = time.perf_counter()

        self._queue_pipeline_progress(converted_done, total, transcribed_done, convert_started, transcribe_started)

        def update_progress(convert_delta: int = 0, transcribe_delta: int = 0):
            nonlocal converted_done, transcribed_done
            with progress_lock:
                converted_done += convert_delta
                transcribed_done += transcribe_delta
                current_converted = converted_done
                current_transcribed = transcribed_done
            self._queue_pipeline_progress(current_converted, total, current_transcribed, convert_started, transcribe_started)

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
                self._queue("job", job.original_path, self._conversion_failure_status(exc))
                self._queue("activity", f"{job.original_name}: {job.error}", "activity_step_error")
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
                        self._transcribe_job(job, url, None, settings)
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

        transcribe_workers = max(1, int(settings.get("transcribe_parallel") or 1))
        convert_workers = max(1, int(settings.get("convert_parallel") or 1))
        with concurrent.futures.ThreadPoolExecutor(max_workers=transcribe_workers) as transcribe_executor:
            transcribe_futures = [
                transcribe_executor.submit(transcribe_worker)
                for _ in range(transcribe_workers)
            ]
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=convert_workers) as convert_executor:
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

    @staticmethod
    def _ffmpeg_error_reason(log_path: Path) -> str:
        """Extrai do log do FFmpeg um motivo curto e legível para a falha.

        Ex.: log com "Output file does not contain any stream" ->
        " — o arquivo não possui faixa de áudio".
        """
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        tail = lines[-40:]
        for line in tail:
            if "does not contain any stream" in line.lower():
                return " — o arquivo não possui faixa de áudio"
        error_hints = (
            "error", "invalid", "no such", "not found", "could not", "cannot",
            "failed", "unsupported", "permission", "does not contain",
        )
        for line in reversed(tail):
            low = line.lower()
            if any(hint in low for hint in error_hints):
                cleaned = re.sub(r"^\[[^\]]*\]\s*", "", line.strip()).strip()
                if cleaned:
                    return f" — {cleaned[:180]}"
        return ""

    @staticmethod
    def _conversion_failure_status(exc: Exception) -> str:
        """Status na coluna Status quando a conversão falha.

        Vídeo sem faixa de áudio vira "Sem audio" (o ffmpeg não tem o que
        converter); demais falhas seguem como "Erro na conversão".
        """
        if "não possui faixa de áudio" in str(exc):
            return "Sem audio"
        return "Erro na conversão"

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
            self._queue("tree_size", job.original_path, self._job_size_column_text(job))
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
            if not getattr(self, "_suppress_ffmpeg_command_log", False):
                self._queue("ffmpeg_command", format_ffmpeg_command_for_log(command))
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
            reason = self._ffmpeg_error_reason(job.log_path)
            raise RuntimeError(f"FFmpeg retornou código {process.returncode}{reason}")
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
        # O tamanho inicial -> final aparece na coluna Tamanho da tabela
        # (não mais no log nem na barra de status).
        self._queue("tree_size", job.original_path, self._job_size_column_text(job))
        # VAD removido da pipeline principal


    def _run_transcriptions(self, jobs: list[AudioJob], settings: dict):
        if settings.get("_multi_transcription") and len(settings.get("_multi_transcription_models") or []) >= 2:
            self._run_multi_transcriptions(jobs, settings)
            return
        candidates = [job for job in jobs if not job.error]
        total = len(candidates)
        if total == 0:
            return
        url = transcribe_url(settings)
        done = 0
        transcribe_started = time.perf_counter()
        self._queue_phase_progress("Transcrevendo arquivos", done, total, "transcribe", transcribe_started)

        def run_group(group: list[AudioJob], parallelism: int):
            nonlocal done
            if not group:
                return
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, parallelism)) as executor:
                future_map = {
                    executor.submit(self._transcribe_job, job, url, None, settings): job
                    for job in group
                }
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
                    self._queue_phase_progress("Transcrevendo arquivos", done, total, "transcribe", transcribe_started)

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
        model_names = list(settings.get("_multi_transcription_models") or [])
        if len(model_names) < 2:
            raise RuntimeError("O multi-modelo precisa de pelo menos dois modelos selecionados.")
        model_settings = [
            settings_for_transcription_server(settings, name)
            for name in model_names
        ]
        uploaders = [
            create_transcription_uploader(self.cancel_event, item_settings)
            for item_settings in model_settings
        ]
        self.uploaders = uploaders
        done = [0] * len(model_settings)
        progress_lock = threading.Lock()
        model_starts = [time.perf_counter()] * len(model_settings)
        model_labels = list(model_names)

        def update_progress(index: int):
            now = time.perf_counter()
            with progress_lock:
                done[index - 1] += 1
                snapshot = list(done)
            self._queue("progress", int((sum(snapshot) / (total * len(model_settings))) * 100 + 0.5))
            throttles = getattr(self, "_model_throttle", None)
            if throttles is None:
                throttles = {}
                self._model_throttle = throttles
            emit_lines = all(count >= total for count in snapshot) or now - throttles.get("all", 0.0) >= 0.1
            if not emit_lines:
                return
            throttles["all"] = now
            for model_index, count in enumerate(snapshot, start=1):
                label = model_labels[model_index - 1]
                if count >= total:
                    self._queue(
                        "activity_line",
                        f"model:{model_index}",
                        f"{label} {count}/{total} ({format_duration(time.perf_counter() - model_starts[model_index - 1])})",
                        "vad_total",
                    )
                else:
                    percent = int(count / max(total, 1) * 100 + 0.5)
                    self._queue("activity_line", f"model:{model_index}", f"{label} {count}/{total} ({percent}%)", None)

        for model_index, label in enumerate(model_labels, start=1):
            self._queue("activity_line", f"model:{model_index}", f"{label} 0/{total} (0%)", None)

        def job_attr(job: AudioJob, base: str, index: int):
            return audio_job_attr(job, base, index)

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
                            audio_job_set(job, "error", index, detail)
                            txt_path = job_attr(job, "txt_path", index)
                            if txt_path:
                                txt_path.write_text(detail, encoding="utf-8")
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

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(model_settings)) as executor:
            futures = [executor.submit(model_runner, index) for index in range(1, len(model_settings) + 1)]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        for job in candidates:
            errors = [
                audio_job_attr(job, "error", index)
                for index in range(1, len(model_settings) + 1)
            ]
            if all(errors):
                self._queue("job", job.original_path, "Erro nos modelos")
            elif any(errors):
                self._queue("job", job.original_path, "Transcrito parcialmente")
            else:
                self._queue("job", job.original_path, f"Transcrito nos {len(model_settings)} modelos")

    def _alibaba_vocabulary_for(self, settings: dict, target_model: str) -> str:
        """Lista pré-compilada de hotwords pronta para ESTE modelo ("" = sem).

        Usada tanto pelo arquivo (REST, Transcrição) quanto pelo WebSocket
        (Ocorrência) — cada modelo alvo tem o seu registro. Reaproveita a lista
        quando o modelo e os termos são os mesmos; cria outra quando mudam.
        Nunca derruba a transcrição: em erro devolve "" (o chamador segue sem
        hotwords) e o registro novo é persistido pela fila `settings_key`,
        gravada na UI thread.
        """
        termos = keywords_for_provider(settings, "alibaba")
        if not termos:
            return ""
        try:
            vocabulary_id = alibaba_ensure_vocabulary(settings, target_model, termos)
        except Exception as exc:
            self._queue("activity", f"Alibaba: falha ao preparar a lista de keywords ({exc}).", "warning")
            return ""
        if not vocabulary_id:
            self._queue(
                "activity",
                "Alibaba: não consegui preparar a lista de keywords; seguindo sem hotwords.",
                "warning",
            )
            return ""
        registros = alibaba_vocabulary_records(settings)
        atual = registros.get(target_model) or {}
        if atual.get("id") != vocabulary_id or atual.get("terms") != [str(t) for t in termos]:
            self._queue(
                "settings_key",
                "alibaba_vocabulary_by_model",
                alibaba_vocabulary_record_update(settings, target_model, vocabulary_id, termos),
            )
        return vocabulary_id

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
        raw_path = audio_job_attr(job, "raw_path", model_index)
        txt_path = audio_job_attr(job, "txt_path", model_index)
        if raw_path is None or txt_path is None:
            raise RuntimeError(f"arquivos de saída do modelo {model_index} não definidos")
        # AssemblyAI: áudios com 2 minutos ou mais vão pelo fluxo assíncrono
        # (v2/upload -> v2/transcript -> polling a cada 3s).
        if (
            is_assemblyai_transcription(request_settings)
            and probe_duration_ms(job.upload_path) >= 120000
        ):
            result = self._assemblyai_async_transcribe(job, request_settings)
            audio_job_set(job, "transcription", model_index, result)
            txt_path.write_text(result, encoding="utf-8")
            return
        # Meta Muse Voice: REST dedicado (multipart "request" + "audio").
        if is_metamuse_transcription(request_settings):
            transcript = metamuse_rest_transcribe(
                self.cancel_event, request_settings, job.upload_path, raw_path
            )
            result = transcript or "(sem transcrição)"
            audio_job_set(job, "transcription", model_index, result)
            txt_path.write_text(result, encoding="utf-8")
            return
        # Alibaba Fun ASR/Qwen: REST DashScope nativo (fun-asr-flash).
        if is_alibaba_transcription(request_settings):
            transcript = alibaba_rest_transcribe(
                self.cancel_event,
                request_settings,
                job.upload_path,
                raw_path,
                self._alibaba_vocabulary_for(request_settings, ALIBABA_REST_MODEL),
            )
            result = transcript or "(sem transcrição)"
            audio_job_set(job, "transcription", model_index, result)
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
        audio_job_set(job, "transcription", model_index, result)
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
        # Keywords: este fluxo monta o JSON na mão (v2/transcript), então precisa
        # incluir o `keyterms_prompt` explicitamente — sem isto, as keywords não
        # chegavam nos áudios de 2 minutos ou mais.
        termos = stt_provider_rules.keywords_for_provider(request_settings, "assemblyai")
        if termos:
            params["keyterms_prompt"] = list(termos)
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
                elif kind == "tree_size":
                    path, size_str = message[1], message[2]
                    item = self.tree_items.get(path)
                    if item:
                        values = list(self.tree.item(item, "values"))
                        if len(values) >= 2:
                            values[1] = size_str
                            self.tree.item(item, values=values)


                elif kind == "status":
                    self.status_var.set(message[1])
                elif kind == "status_silent":
                    self._set_activity_status(message[1], log=False)
                elif kind == "activity":
                    tag = message[2] if len(message) > 2 else None
                    self._append_activity_log(message[1], tag)
                elif kind == "params_block":
                    self._append_params_block(message[1], message[2])
                elif kind == "settings_key":
                    # Persistência pedida por um worker (ex.: vocabulary_id da
                    # Alibaba criado no loop ao vivo): grava na UI thread, que é
                    # quem mexe no settings.json.
                    self.settings[message[1]] = message[2]
                    self.settings = save_settings(self.settings)
                elif kind == "ffmpeg_command":
                    self._append_activity_log(
                        message[1],
                        "ffmpeg_command",
                        raw=True,
                    )
                elif kind == "activity_line":
                    key, text, tag = message[1], message[2], message[3] if len(message) > 3 else None
                    self._update_activity_line(key, text, tag)
                elif kind == "activity_step_finish":
                    key, elapsed = message[1], float(message[2])
                    self._finish_activity_step(key, elapsed)
                    if key == "live:ws_finalize":
                        self.live_ws_finalize_pending = False
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
                            selected_fields = self._live_qualification_selected_ids()
                            formatted = format_occurrence_qualification(
                                raw_result,
                                self.qualification_fields,
                                selected_fields,
                            )
                            if not formatted:
                                raise ValueError("a IA não devolveu informações utilizáveis")
                            self.last_live_qualification_text = formatted
                            self._set_live_editor(
                                "qualification",
                                formatted,
                                qualification_organized=True,
                            )
                            # O texto atual veio de uma organização (tag usada
                            # pelo 'Gerar documento'); guarda o JSON para o
                            # filtro por checkboxes.
                            self._last_live_qualification_fields = (
                                parse_qualification_json(
                                    raw_result,
                                    list(LIVE_QUALIFICATION_FIELD_IDS),
                                    self.qualification_fields,
                                )
                            )
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
                            self._qualification_organized_at = None
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
                        self._qualification_organized_at = None
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
                elif kind == "qrcode_shortened":
                    short = str(message[1])
                    self._finish_activity_step(
                        "qrcode:shorten",
                        time.perf_counter()
                        - getattr(self, "qrcode_shorten_started", time.perf_counter()),
                    )
                    self.qrcode_shorten_busy = False
                    self.qrcode_generate_button.configure(state="normal")
                    self.qrcode_shortened_var.set(short)
                    self.qrcode_shortened_row.pack(
                        fill=X, pady=(8, 0), before=self.qrcode_content
                    )
                    self.qrcode_shortened_copy_button.configure(state="normal")
                    self.qrcode_link_var.set(short)
                    self._generate_qrcode_now(short)
                elif kind == "qrcode_shorten_error":
                    detail = str(message[1])
                    self._finish_activity_step(
                        "qrcode:shorten",
                        time.perf_counter()
                        - getattr(self, "qrcode_shorten_started", time.perf_counter()),
                        error=detail,
                    )
                    self.qrcode_shorten_busy = False
                    self.qrcode_generate_button.configure(state="normal")
                elif kind == "update_available_sync":
                    state = dict(message[1])
                    self.available_update_sync = state
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


def main():
    root = Tk()
    app = SigApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
