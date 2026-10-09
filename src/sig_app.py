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
import traceback
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
from tkinter import BOTH, BOTTOM, END, LEFT, RIGHT, TOP, X, Y, BooleanVar, Canvas, IntVar, PhotoImage, StringVar, Text, Tk, Toplevel
from tkinter import filedialog, messagebox, ttk
from urllib.parse import quote, urlencode, urlparse

from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageTk
import pypdfium2 as pdfium

from assistant_prompts import (
    DEFAULT_HISTORY_SYSTEM_PROMPT,
    DEFAULT_QUALIFICATION_SYSTEM_PROMPT,
    DEFAULT_STATEMENT_TEMPLATE,
    history_user_prompt,
    qualification_user_prompt,
    statement_prompt,
    statement_user_prompt,
)
import diarias_protocolo
import diarias_mapa
import diarias_store
import diarias_workflow
import pdf_printing
import prompt_store
import qr_encoder
import smart_join_planner
import stt_provider_rules
from prompts_panel import PromptsPanel
from diarias_profiles_panel import DiariasProfilesPanel
from diarias_profiles import validate_diarias_profile
from ui_widgets import diarias_action_icon_image, tool_action_icon_image
from prompt_store import PROMPT_CONSTANTE_POR_SLOT as _PROMPT_CONSTANTE_POR_SLOT
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
    generate_diarias_requerimento,
    generate_diarias_requerimento_pdf,
    generate_declaracao_meios_proprios,
    generate_declaracao_meios_proprios_pdf,
    next_available_diarias_requerimento_path,
    next_available_diarias_declaracao_path,
    ensure_document_templates,
    prepare_diarias_requerimento,
    prepare_declaracao_meios_proprios,
    download_github_url,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/ui_widgets.py (codigo movido verbatim).
from ui_widgets import (  # noqa: F401
    create_tooltip,
    describe_parallel_values,
    describe_step_values,
    MAGIC_WAND_ASSET,
    magic_wand_asset_image,
    magic_wand_image,
    nearest_value,
    NodeSlider,
    parallel_values,
    PreviewIconButton,
    step_values,
    workable_step,
)
from media_probe import audio_duration_seconds, wav_duration_seconds
from batch_errors import (
    batch_error_detail,
    batch_error_text,
    conversion_label,
    PREPARATION_LABELS,
    preparation_text,
    transcription_label,
    vad_label,
    zip_label,
)
from batch_execution import cancellable_executor, cancellable_join, iter_completed, split_balanced


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/media_files.py (codigo movido verbatim).
from media_files import (  # noqa: F401
    SUPPORTED_EXTENSIONS,
    VIDEO_EXTENSIONS,
    AUDIO_EXTENSIONS,
    MIME_TYPES,
    is_video_file,
    is_transcription_ready_wav,
    is_transcription_ready_compressed,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/reporting.py (codigo movido verbatim).
from reporting import (  # noqa: F401
    html_document,
    write_html_report,
    build_live_html,
    jobs_with_material,
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
    granite_sessions,
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
from text_tools import (  # noqa: F401
    ajustar_texto_oitiva,
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
    SERVER_QWEN_NAME,
    SERVER_QWEN_MODEL,
    SERVER_QWEN_URL,
    SERVER_QWEN_NAMES,
    LOCAL_SERVER_NAMES,
    TEXT_MODEL_LEGACY_NAMES,
    GROK_TEXT_API_NAMES,
    DEEPSEEK_API_NAMES,
    PARTS_EXTRACTION_LABELS,
    TEXT_TASK_KEYS,
    DEFAULT_SETTINGS,
    API_KEY_IMPORT_FIELDS,
    read_transcription_servers,
    read_text_models,
    selected_text_model_config,
    text_model_label,
    selected_transcription_server,
    transcription_server_label,
    parse_api_keys_text,
    fallback_text_model_for_missing_api_key,
    fallback_transcription_server_for_missing_api_key,
    is_realtime_only_transcription_server,
    is_local_granite_transcription_server,
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
    job_has_material,
    transcription_candidates,
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
    physical_cpu_count,
    vad_parallel_options,
)


# --- API historica: nomes reexportados dos modulos extraidos ---------------
# Implementacao real em src/log_formatting.py (codigo movido verbatim).
from log_formatting import (  # noqa: F401
    FFMPEG_COMMAND_BLOCK_TAG,
    BATCH_SUMMARY_SEPARATOR,
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
    format_audio_total,
    format_total_size,
    format_efficiency_line,
    format_server_progress,
    mode_label_from_value,
    format_ws_params_block,
    params_block_single_line,
    RAW_REQUEST_BOUNDARY,
    format_raw_request,
    format_raw_multipart,
    format_raw_request_line,
    format_raw_websocket_frame,
    format_raw_audio_label,
)


APP_VERSION = "20261008_003"


def _diarias_selected_output_path(filename, file_type, default_extension: str) -> Path:
    """Aplica a extensão do formato escolhido no diálogo Salvar como."""
    destination = Path(filename)
    selected_type = str(file_type.get() or "").casefold()
    is_pdf = ".pdf" in selected_type or destination.suffix.casefold() == ".pdf"
    extension = ".pdf" if is_pdf else default_extension
    if destination.suffix.casefold() != extension.casefold():
        destination = destination.with_suffix(extension)
    return destination


def _confirm_diarias_output_overwrite(parent, destination: Path) -> bool:
    if not destination.exists():
        return True
    return messagebox.askyesno(
        "Substituir arquivo?",
        f"Já existe um arquivo neste local:\n{destination}\n\nDeseja substituí-lo?",
        parent=parent,
    )


def _audio_file_size(path: Path) -> int | None:
    """Tamanho do áudio para o texto cru da requisição (None se ainda não há)."""
    try:
        return path.stat().st_size
    except OSError:
        return None





















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
# Tamanho (em pixels) do botao de icone QUADRADO da oitiva (varinha magica), so
# como FALLBACK: o tamanho real e medido em tela a cada posicionamento (ver
# `_position_live_statement_actions`). Medir em vez de fixar e obrigatorio: o
# `ttk` em pixels muda com o DPI/escala e o `width`/`height` sao em CARACTERES,
# entao um valor fixo fica torto em parte das maquinas. Sem rede, o menor valor
# plausivel (24 px) e usado so quando ainda nao ha botao de icone medido.
EDITOR_ICON_BUTTON_SIZE = 24
# Distância, em pixels, entre a BORDA DIREITA do botão "Recuperar" e a BORDA
# ESQUERDA da varinha mágica (pedido do usuário, 29/09: "distancie eles um
# pouco... tente usar 24 pixels"). Com a folga colada (o que o cálculo
# anterior fazia) os dois botões pareciam um só.
LIVE_WAND_RECOVER_GAP = 24
# Ícones (PNG em assets/) dos botões da linha de controles da aba Ocorrência:
# microfone vermelho (WS), microfone branco (REST) e pausar. Substituem os
# desenhos vetoriais que existiam no lugar (pedido do usuário, 12/09).
LIVE_ICON_SIZE = 36
LIVE_ICON_FILES = {
    "mic_vermelho": "assets/mic_vermelho.png",
    "mic_branco": "assets/mic_branco.png",
    "mic_pause": "assets/mic_pause.png",
}
# Amarelo do círculo do ícone de pausa (medido em assets/mic_pause.png): é a cor
# usada no estado "retomar", que desenha o mesmo círculo com o triângulo preto.
LIVE_PAUSE_CIRCLE_COLOR = "#fddd02"
# Preto do símbolo dentro dos ícones (as barras do pause).
LIVE_ICON_GLYPH_COLOR = "#000000"
GROK_RECONNECT_MAX_ATTEMPTS = 8
GROK_RECONNECT_BUFFER_MILLIS = 8000
IMEI_HISTORY_COLLAPSED_LIMIT = 10
# Imagem do QR Code copiada para a area de transferencia (botao Copiar da aba
# QR Code): escala por modulo 14 -> 4 (1/4 de cada lado — altura e largura —
# isto e, 1/16 dos pixels da imagem antiga; a divisao exata 14/4 = 3,5 nao
# existe em pixel inteiro e 4 preserva 4 px por modulo para a leitura) e SEM
# margem branca (border 4 -> 0) — pedido do usuario, 12/09. A previa no
# canvas nao muda.
QRCODE_COPY_SCALE = 4
QRCODE_COPY_BORDER = 0
# Tempo máximo que o worker espera a resposta do aviso "gerar relatório parcial?"
# depois do cancelamento (o usuário pode demorar; o limite só evita travar para
# sempre se a janela morrer — regra do usuário, 13/09).
PARTIAL_REPORT_WAIT_SECONDS = 600.0

























































































































































































































































































API_KEY_VISIBILITY_ICON_SIZE = 22
# Tamanho mínimo do desenho ao encolher o ícone para casar a altura do botão.
API_KEY_VISIBILITY_ICON_MIN_SIZE = 14
# Respiro entre o botão do olho e o botão IMPORTAR (não podem ficar encostados).
API_KEY_EYE_GAP = 10
# Cinza dos outros ícones desenhados pelo app (paste/copiar/gear).
API_KEY_VISIBILITY_ICON_COLOR = "#263735"
# Largura da coluna de rótulos da aba Chaves API. Os 190px originais existiam
# por causa do rótulo longo "Chave API do IMEI Check" (hoje "IMEI Check");
# com 98px — que ainda cabe no rótulo mais largo, "AssemblyAI" — os campos
# começam 92px mais à esquerda.
API_KEY_LABEL_COLUMN_WIDTH = 98
# Valor ANTIGO da mesma coluna: é a base do ganho de 25% medido pelos testes.
API_KEY_LABEL_COLUMN_LEGACY_WIDTH = 190
# Largura dos campos de chave EM CARACTERES (era 60). 76 = 60 * 1,25 arredondado
# PARA CIMA, porque a quantização em caracteres não dá 25% exatos: o Tk pede
# (caracteres * largura do caractere + padding), então 75 caracteres dariam
# 456px (24,6%). Em caracteres os 25% acompanham a fonte, portanto valem em
# qualquer DPI. Também é o que mantém a janela no tamanho atual: o Tk dimensiona
# a janela de Configurações pela requisição da aba ATIVA, e só estreitar a coluna
# de rótulos faria a janela encolher junto (medido: 366 → 428px, em vez de 462px).
API_KEY_ENTRY_WIDTH_CHARS = 76
# Valor ANTIGO da mesma largura em caracteres: base medida pelo teste da UI.
API_KEY_ENTRY_WIDTH_LEGACY_CHARS = 60
# Ganho mínimo exigido nos campos de chave (vacina da UI em scripts/ui_smoke.py).
API_KEY_FIELD_MIN_GROWTH = 1.25
# Padding horizontal do LabelFrame (12+12) + borda (2+2) de cada seção de
# chaves: é o que sobra entre a largura da seção e a coluna do rótulo + campo.
API_KEY_SECTION_HORIZONTAL_MARGIN = 28


def api_key_visibility_image(crossed: bool, size: int = API_KEY_VISIBILITY_ICON_SIZE) -> "Image.Image":
    """Ícone do botão de revelar/esconder as chaves API (aba Chaves API).

    `crossed=False` = olho aberto, que é o estado INICIAL (chaves mascaradas) e
    representa a ação "revelar"; `crossed=True` = olho cortado, exibido depois de
    revelar, quando a ação do botão passa a ser "esconder". Desenhado em 4x e
    reduzido (mesma técnica dos demais ícones) para as bordas ficarem limpas.
    """
    escala = 4
    # Desenho de referência em 22px; `proporcao` mantém a forma em outro tamanho.
    proporcao = size / API_KEY_VISIBILITY_ICON_SIZE
    image = Image.new("RGBA", (size * escala, size * escala), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = API_KEY_VISIBILITY_ICON_COLOR
    width = 2 * escala
    centro_x = centro_y = size / 2
    # As duas pálpebras são arcos da MESMA elipse: 200..340 desenha a de cima e
    # 20..160 a de baixo (ângulos do PIL crescem no sentido horário).
    palpebras = (
        (centro_x - 9 * proporcao) * escala,
        (centro_y - 7 * proporcao) * escala,
        (centro_x + 9 * proporcao) * escala,
        (centro_y + 7 * proporcao) * escala,
    )
    draw.arc(palpebras, start=200, end=340, fill=color, width=width)
    draw.arc(palpebras, start=20, end=160, fill=color, width=width)
    raio = 2.5 * proporcao
    draw.ellipse(
        (
            (centro_x - raio) * escala,
            (centro_y - raio) * escala,
            (centro_x + raio) * escala,
            (centro_y + raio) * escala,
        ),
        outline=color,
        width=width,
    )
    if crossed:
        # A diagonal de canto a canto é o que diferencia o "olho cortado".
        recuo = 3 * proporcao
        draw.line(
            (recuo * escala, recuo * escala, (size - recuo) * escala, (size - recuo) * escala),
            fill=color,
            width=width,
        )
    return image.resize((size, size), Image.Resampling.LANCZOS)


_LIVE_ICON_IMAGE_CACHE: dict = {}


def live_icon_image(kind: str, size: int = LIVE_ICON_SIZE) -> "Image.Image":
    """Ícone PNG da aba Ocorrência (`live_icons`), aberto e reduzido para `size`.

    Os três PNGs de `assets/` já são quadrados com o círculo encostando nas
    bordas (a margem transparente foi recortada na importação), então basta o
    LANCZOS preservando o canal alfa — a transparência em volta do círculo é o
    que deixa o botão parecer redondo sobre o fundo da aba. A imagem fica em
    cache: os botões são redesenhados a cada mudança de estado e abrir/reescalar
    um PNG de 256px toda vez seria desperdício.
    """
    chave = (kind, size)
    cacheada = _LIVE_ICON_IMAGE_CACHE.get(chave)
    if cacheada is not None:
        return cacheada
    with Image.open(resource_path(LIVE_ICON_FILES[kind])) as origem:
        image = origem.convert("RGBA")
    if image.size != (size, size):
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    _LIVE_ICON_IMAGE_CACHE[chave] = image
    return image


class SigApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("sig")
        self._install_error_reporter()
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
        # Fechando a janela: o aviso de relatório parcial é pulado (a UI para de
        # responder) — regra do usuário, 13/09.
        self._app_closing = False
        # Estado por execução do lote: linhas de erro agregadas por tipo, marcas
        # das linhas vivas e contadores de arquivos já prontos/compactados.
        self._run_sequence = 0
        self._batch_job_total = 0
        self._batch_error_entries: dict[str, dict] = {}
        self._error_line_raw: dict[str, str] = {}
        self._prep_counts: dict[str, dict] = {}
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
        # "Um modelo por vez" (padrão: DESMARCADA): flag do LOTE — não é
        # persistida em settings.json (mesmo padrão das outras checkboxes da
        # linha), então o app sempre abre com ela desmarcada.
        self.files_one_model_var = BooleanVar(master=self.root, value=False)
        self.files_language_label_var = StringVar(value="Idioma: pt")
        self.files_keywords_label_var = StringVar(master=self.root, value=f"Keywords: {KEYWORDS_OFF_LABEL}")
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
        self.diarias_holerite_path, holerite_filename = (
            diarias_store.load_holerite_pdf()
        )
        self.diarias_protocolo_path = ""
        self.diarias_talao_path = ""
        self.diarias_escala_path = ""
        self.diarias_escala_file_var = StringVar(master=self.root, value="")
        self.diarias_holerite_file_var = StringVar(
            master=self.root, value=holerite_filename
        )
        self.diarias_protocolo_file_var = StringVar(master=self.root, value="")
        self.diarias_talao_file_var = StringVar(master=self.root, value="")
        holerite_total, holerite_mes = diarias_store.load_holerite()
        self.diarias_ufesp_index_var = StringVar(
            master=self.root, value=diarias_store.load_ufesp_index()
        )
        self.diarias_ufesp_index_save_error_shown = False
        self.diarias_ufesp_index_var.trace_add(
            "write", self._save_diarias_ufesp_index_data
        )
        self.diarias_ufesp_var = StringVar(
            master=self.root, value=diarias_store.load_ufesp()
        )
        self.diarias_ufesp_save_error_shown = False
        self.diarias_ufesp_var.trace_add(
            "write", self._save_diarias_ufesp_data
        )
        self.diarias_holerite_total_var = StringVar(
            master=self.root, value=holerite_total
        )
        self.diarias_holerite_mes_var = StringVar(master=self.root, value=holerite_mes)
        self.diarias_holerite_save_error_shown = False
        self.diarias_holerite_total_var.trace_add(
            "write", self._save_diarias_holerite_data
        )
        self.diarias_holerite_mes_var.trace_add(
            "write", self._save_diarias_holerite_data
        )
        self.diarias_req_var = StringVar(master=self.root, value="")
        self.diarias_mapa_var = StringVar(master=self.root, value="")
        self.diarias_data_var = StringVar(master=self.root, value="")
        self.diarias_abertura_data_var = StringVar(master=self.root, value="")
        self.diarias_abertura_hora_var = StringVar(master=self.root, value="")
        self.diarias_fechamento_data_var = StringVar(master=self.root, value="")
        self.diarias_fechamento_hora_var = StringVar(master=self.root, value="")
        self.diarias_meios_proprios_var = BooleanVar(master=self.root, value=False)
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
        # Botão de ajuste da oitiva (uma linha só, "; " padrão).
        self.magic_wand_icon = self._make_magic_wand_icon()
        # PhotoImage dos ícones PNG dos botões da aba Ocorrência (o Tk não segura
        # a referência sozinho: o cache mantém as imagens vivas).
        self._live_icon_photos = {}
        self.document_copy_icon = self._make_document_action_icon("copy")
        self.document_save_icon = self._make_document_action_icon("save")
        self.document_view_icon = self._make_document_action_icon("preview")
        self._build_menu()
        self._build_ui()
        # Área dos prompts do usuário (%APPDATA%\sig\Prompts). Criada antes de
        # qualquer requisição para que `ensure_layout` semeie o padrão e a aba
        # Prompts já abra com a lista completa. `_reload_prompts` vem logo
        # atrás: a escolha do usuário tem de valer na PRIMEIRA requisição,
        # mesmo que ele nunca abra a aba Prompts nesta sessao.
        self.prompt_store = prompt_store.default_store()
        self.prompt_store.ensure_layout()
        # Atualizar o app tambem atualiza os prompts: o que veio no executavel
        # novo entra no `padrao/` sem o usuario clicar em "Baixar prompts".
        # `apply_padrao_do_app` so troca o que ainda era a versao anterior do
        # app, entao o que o usuario editou ou baixou do R2 fica intacto.
        self._prompts_atualizados_pelo_app = self.prompt_store.apply_padrao_do_app()
        self._reload_prompts()
        self.status_var.trace_add("write", lambda *_args: self._on_status_var_changed())
        self._refresh_server_label()
        self.root.after(100, self._poll_ui_queue)
        self.root.after(100, self._refresh_assistant_progress_clock)
        self.root.after(0, self._refresh_microphone_availability)
        self.root.after(1200, self._start_update_check)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.diarias_holerite_path and not re.fullmatch(
            r"(?:0[1-9]|1[0-2])/\d{4}", holerite_mes.strip()
        ):
            self.root.after_idle(self._migrate_saved_diarias_holerite_month)

    def _install_error_reporter(self):
        """Erro em callback do Tk vai para o log e para um arquivo de texto.

        O exe é `--windowed` (sem console) e o Tk engole a exceção depois de
        imprimi-la no stderr, que não existe: sem isso, um erro no MEIO da
        construção de uma janela deixa a janela pela metade em silêncio — foi
        assim que a ajuda do slider de Conversões derrubou as Configurações em
        PCs com poucos núcleos e o sintoma chegou como "menu colapsado", sem
        nenhuma pista. O arquivo fica na pasta de dados do usuário
        (%APPDATA%/sig/sig_erros.log), nunca na pasta do aplicativo — a pasta
        do app é sincronizada pelo updater.
        """
        try:
            self.root.report_callback_exception = self._report_callback_exception
        except Exception:
            pass

    def _report_callback_exception(self, exc_type, exc, tb) -> None:
        detalhe = "".join(traceback.format_exception(exc_type, exc, tb))
        resumo = f"Erro interno: {exc_type.__name__}: {exc}"
        try:
            caminho = settings_path().parent / "sig_erros.log"
            with caminho.open("a", encoding="utf-8") as arquivo:
                arquivo.write(
                    f"\n=== {datetime.now().isoformat(timespec='seconds')} "
                    f"(versao {APP_VERSION})\n"
                )
                arquivo.write(detalhe)
        except Exception:
            pass
        try:
            self._append_activity_log(f"{resumo} (detalhes em sig_erros.log)", "activity_step_error")
            self.status_var.set(resumo)
        except Exception:
            pass

    def _build_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        settings_surface = style.lookup("TLabelframe", "background") or "#dcdad5"
        style.configure("TFrame", background="#f4f7f6")
        style.configure("Diarias.Card.TFrame", background="#ffffff", relief="flat")
        style.configure(
            "Diarias.Title.TLabel", background="#f4f7f6", foreground="#10201f",
            font=("Segoe UI Semibold", 16),
        )
        style.configure(
            "Diarias.Section.TLabel", background="#ffffff", foreground="#193d32",
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "Diarias.Field.TLabel", background="#ffffff", foreground="#536565",
            font=("Segoe UI", 9),
        )
        style.configure(
            "Diarias.TCheckbutton",
            background="#ffffff",
            foreground="#1d2b2a",
            font=("Segoe UI", 9),
        )
        style.configure(
            "Diarias.File.TLabel", background="#ffffff", foreground="#667371",
            font=("Segoe UI", 9),
        )
        style.configure("Diarias.Pdf.TButton", padding=(8, 3), background="#eef6f1", foreground="#24583c", bordercolor="#cdded3", lightcolor="#eef6f1", darkcolor="#eef6f1")
        style.map("Diarias.Pdf.TButton", background=[("active", "#dcece2"), ("disabled", "#e9eeec")])
        style.configure(
            "Diarias.Reload.TButton", foreground="#1565d8", background="#ffffff", bordercolor="#d1dfd8", lightcolor="#ffffff", darkcolor="#ffffff", padding=(6, 3),
        )
        style.configure(
            "Diarias.Primary.TButton", foreground="#ffffff", background="#16833a",
            font=("Segoe UI Semibold", 10), padding=(14, 8),
        )
        style.map(
            "Diarias.Primary.TButton",
            background=[("active", "#116b30"), ("disabled", "#7ea98a")],
            foreground=[("disabled", "#f1f4f2")],
        )
        style.configure("Diarias.Output.TButton", foreground="#244a60", background="#ffffff", font=("Segoe UI Semibold", 10), padding=(12, 7))
        style.map("Diarias.Output.TButton", background=[("active", "#e7efef"), ("disabled", "#e9eeec")])
        style.configure("Diarias.Invalid.TEntry", fieldbackground="#fff1f0", bordercolor="#b42318")
        style.configure("Diarias.Invalid.TCombobox", fieldbackground="#fff1f0", bordercolor="#b42318")
        style.map("Diarias.Invalid.TCombobox", fieldbackground=[("readonly", "#fff1f0")])
        style.configure("Diarias.Invalid.TSpinbox", fieldbackground="#fff1f0", bordercolor="#b42318")
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
        # Botão quadrado da oitiva (varinha mágica): sem padding, para que
        # `-width`/`-height` em pixels caiam no quadrado exato 24x24.
        style.configure("SquareIcon.TButton", padding=0)
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

    def _make_magic_wand_icon(self, color="#16833a", star_color="#f2c200", escala=8):
        """Varinha mágica da oitiva: o ÍCONE DO USUÁRIO, reduzido ao botão.

        Pedido de 28/09: usar o desenho dele
        (`D:\\Projetos\\Icones\\varinha_03.png`, copiado para
        `assets/varinha_magica.png`), expondo o desenho INTEIRO dentro do botão
        e sem o ampliar.

        Como cabe inteiro: o botão tem 24 px e o PNG é quadrado com o desenho
        encostando nas bordas, então a imagem é só REDUZIDA
        (`magic_wand_asset_image`, que nunca amplia) e exibida sem corte. Se o
        arquivo faltar, cai no desenho vetorial (`magic_wand_image`) para o app
        não quebrar.
        """
        imagem = magic_wand_asset_image(resource_path(MAGIC_WAND_ASSET))
        if imagem is None:
            return ImageTk.PhotoImage(
                magic_wand_image(color=color, star_color=star_color, escala=escala),
                master=self.root,
            )
        return ImageTk.PhotoImage(imagem, master=self.root)

    def _make_api_key_visibility_icon(self, crossed: bool, size: int = API_KEY_VISIBILITY_ICON_SIZE):
        """PhotoImage do olho aberto (`crossed=False`) / cortado (`True`)."""
        return ImageTk.PhotoImage(api_key_visibility_image(crossed, size), master=self.root)

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

    @staticmethod
    def _make_square_icon_button(parent, image, tooltip, command):
        """Botao de icone QUADRADO, do mesmo tamanho dos botoes de icone.

        Medido em tela: os botoes Colar/Copiar/Limpar da faixa sao 42x24 px, e
        o `ttk::button` nao aceita `-height` (so `-width`, em pixels, e
        `-padding`). O quadrado e fechado por: `-width` em pixels, padding 0 e
        o `place` com `relheight`/altura imposta pelo chamador. Sem isto o
        botao sai 28x28 (icone de 20px + bordas), mais alto que a faixa.
        """
        size = EDITOR_ICON_BUTTON_SIZE
        button = ttk.Button(
            parent,
            image=image,
            style="SquareIcon.TButton",
            padding=0,
            command=command,
        )
        # `-width` em pixels: o ttk aceita valor inteiro como pixel.
        button.tk.call(button._w, "configure", "-width", size)
        button.configure(width=-size)
        # `tooltip` é OPCIONAL: a varinha mágica foi criada SEM dica ao passar
        # o mouse (pedido do usuário), e os demais botões continuam com a dica.
        if tooltip:
            create_tooltip(button, tooltip)
        return button

    @staticmethod
    def _size_recover_button(button, lado: int):
        """Deixa o botão "Recuperar" com a MESMA largura da varinha mágica.

        Pedido do usuário (29/09): "redimensiona os botões de recuperar
        transcrição/histórico/oitiva, use exatamente as mesmas dimensões dos
        botões de varinha mágica". Medido antes: o "Recuperar" saía 23x21 e a
        varinha 24x24 — dois tamanhos diferentes na mesma linha.

        O `ttk::button` só aceita `-width` (em pixels, quando inteiro) e
        `-padding`; a altura vem do `place`/layout. Por isso a largura vai por
        `-width` e a altura por `place` explícito, que o chamador aplica
        (aqui, em `_position_live_statement_actions`, que já posiciona a
        varinha na mesma linha).

        `lado` é MEDIDO (a altura real de um botão de ícone da faixa), nunca
        fixo: em pixels o Tk muda com o DPI/escala.
        """
        try:
            button.tk.call(button._w, "configure", "-width", lado)
            button.configure(width=-lado)
        except Exception:
            pass
        return button

    def _reload_prompts(self):
        """Faz o app usar o prompt escolhido na aba Prompts.

        `assistant_prompts` guarda os prompts como constantes lidas no
        import. Esta funcao as reescreve no lugar, para que a escolha (e o
        download do R2) valham na próxima requisicao sem reiniciar o SIG.

        E o que garante que a escolha valha depois de um REINICIO do app: o
        painel so chama isto quando o usuario mexe na tela. Por isso o
        startup do app tambem chama este metodo, e nao o painel.
        """
        import assistant_prompts

        for slot in prompt_store.PROMPT_SLOTS:
            texto = self.prompt_store.read_active(slot).strip()
            if not texto:
                continue
            setattr(assistant_prompts, _PROMPT_CONSTANTE_POR_SLOT[slot.key], texto)
        return True

    def _prompt_ativo(self, slot_key: str, padrao: str) -> str:
        """Texto em uso de um slot de prompt, com a escolha da aba aplicada.

        Le do store a cada uso: e a unica fonte que sobrevive a um reinicio do
        app (o `ativo.json`), enquanto a constante do modulo so e atualizada
        por `_reload_prompts`. O argumento `padrao` e a reserva para quando o
        store ainda nao tem nada gravado.
        """
        slot = prompt_store.SLOTS_BY_KEY.get(slot_key)
        if slot is None:
            return padrao
        try:
            texto = self.prompt_store.read_active(slot).strip()
        except Exception:  # noqa: BLE001 - nunca quebrar a requisicao por causa do prompt
            return padrao
        return texto or padrao

    def _prompt_oitiva_user_ativo(self, selected_name: str | None, material: str) -> str:
        """Prompt de USUARIO da oitiva, com o nome da parte e o historico."""
        import assistant_prompts

        template = self._prompt_ativo("oitiva_user", "")
        if not template:
            return assistant_prompts.statement_user_prompt(selected_name, material)
        name = (selected_name or "").strip() or "parte selecionada"
        return (
            template.replace("{{NOME_SELECIONADO}}", name)
            .replace(prompt_store.STATEMENT_HISTORY_MARKER, material.strip())
            .replace(prompt_store.STATEMENT_HISTORY_LEGACY_MARKER, material.strip())
            .strip()
        )

    def _prompt_user_ativo(self, slot_key: str, material: str) -> str:
        """Prompt de USUARIO do `historico_user`, com a transcricao atual.

        O template vem do store (a escolha da aba), nunca da constante do
        modulo: assim a escolha vale tambem depois de um reinicio do app.
        """
        import assistant_prompts

        template = self._prompt_ativo(slot_key, "")
        if not template:
            # Reserva: sem nada gravado, usa o que veio no executavel.
            return assistant_prompts.history_user_prompt(material)
        return assistant_prompts._fill_prompt_markers(
            template, material, "conteudo_caixa_transcricao"
        )

    def _prompt_qualificacao_ativo(self, field_ids: list[str], raw_text: str) -> str:
        """Prompt de USUARIO da qualificacao, com os IDs e o texto bruto."""
        import assistant_prompts

        template = self._prompt_ativo("qualificacao_user", "")
        if not template:
            return assistant_prompts.qualification_user_prompt(field_ids, raw_text)
        return assistant_prompts.qualification_prompt_with_template(
            template, field_ids, raw_text
        )

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

    def _activity_log_last_line_visible(self, box) -> bool:
        """A última linha do log está visível (usuário colado no fim)?

        Medido no Tk 8.6: com a vista colada no fim, o `dlineinfo` da última
        linha devolve a caixa dela; qualquer rolagem para cima — até uma única
        linha — devolve None. No log ainda não desenhado (log de uma janela
        oculta) não existe leitura em andamento: mantém a cauda pronta.
        """
        try:
            info = box.dlineinfo(box.index("end-1c linestart"))
        except tk.TclError:
            return True
        if info is not None:
            return True
        try:
            return not bool(box.winfo_ismapped())
        except tk.TclError:
            return True

    def _activity_log_follow_tail(self, box) -> bool:
        """Estado do acompanhamento do fim do log; medir ANTES de escrever.

        A escrita empurra a última linha para fora da vista, então a medição
        precisa vir antes dela. O estado fica guardado para o reancoramento em
        redimensionamentos (`_activity_log_on_configure`).
        """
        following = self._activity_log_last_line_visible(box)
        self._activity_log_tail_following = following
        return following

    def _scroll_activity_log_tail(self, box, follow: bool) -> None:
        """Único lugar que rola o log de atividade até o fim.

        Regra do usuário (13/09): a atualização NÃO pode mover a barra quando o
        usuário rolou para cima para ler — antes, cada atualização (inclusive a
        linha viva "Convertendo/Transcrevendo arquivos: N/M") puxava a vista
        para o fim e não dava para ler o log com o app trabalhando.
        """
        if not follow:
            return
        try:
            box.see("end")
        except tk.TclError:
            pass

    def _activity_log_on_configure(self, _event=None) -> None:
        """Redimensionar a janela não pode fazer o log parar de acompanhar."""
        box = getattr(self, "activity_log", None)
        if box is None or not getattr(self, "_activity_log_tail_following", True):
            return
        self._scroll_activity_log_tail(box, True)

    def _activity_log_on_user_scroll(self, _event=None) -> None:
        """Rolagem do usuário (roda do mouse): mede o novo estado depois dela."""
        root = getattr(self, "root", None)
        if root is None:
            return
        try:
            root.after_idle(self._activity_log_sync_tail_state)
        except tk.TclError:
            pass

    def _activity_log_sync_tail_state(self) -> None:
        box = getattr(self, "activity_log", None)
        if box is None or not box.winfo_exists():
            return
        self._activity_log_tail_following = self._activity_log_last_line_visible(box)

    def _activity_log_scrollbar_command(self, *args) -> None:
        """Comando da barra de rolagem: rola e reavalia o acompanhamento."""
        box = getattr(self, "activity_log", None)
        if box is None:
            return
        box.yview(*args)
        self._activity_log_tail_following = self._activity_log_last_line_visible(box)

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
        follow = self._activity_log_follow_tail(box)
        box.insert(END, f"{started_at}  {label}\n", "activity_step_running")
        box.mark_set(mark, "end-2l linestart")
        box.mark_gravity(mark, "left")
        self._scroll_activity_log_tail(box, follow)
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
            follow = self._activity_log_follow_tail(box)
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
            self._scroll_activity_log_tail(box, follow)
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
            # Fila pronta para iniciar (pedido de 13/09): "1405 arquivo(s) na
            # fila." fica verde no instante em que a linha é escrita — o mesmo
            # vale para a linha de remoção, que reporta o total na fila.
            r"arquivo\(s\) na fila",
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
        follow = self._activity_log_follow_tail(self.activity_log)
        for part in message.splitlines():
            line = f"{time.strftime('%H:%M:%S')}  {part}\n"
            self.activity_log.insert(END, line, tag or self._log_message_tag(part))
        self._scroll_activity_log_tail(self.activity_log, follow)
        self.activity_log.configure(state="disabled")

    def _run_scoped_activity_key(self, key: str) -> str:
        """Escopa a linha viva de fase pela EXECUÇÃO atual (correção de 16/09).

        As linhas vivas usam a tag `phase:<key>`; sem escopo, uma segunda
        execução do mesmo lote reusa a tag da anterior e o
        `_live_line_birth_stamp` lê o horário do texto ANTIGO: a linha nova
        nasce com o horário velho e a linha da execução anterior é apagada do
        lugar (é o bug do "Transcrevendo arquivos" fora de ordem cronológica no
        log). Com o escopo, cada execução tem as suas linhas — as antigas ficam
        no log como histórico, o mesmo princípio das linhas de erro/preparação
        (`r{n}err{m}`/`r{n}prep:{kind}`).
        """
        return f"r{int(getattr(self, '_run_sequence', 0))}:{key}"

    def _update_activity_line(
        self,
        key: str,
        message: str,
        tag: str | None = None,
        *,
        timestamp: str | None = None,
        in_place: bool = False,
    ):
        """Linha viva do activity log: atualiza a MESMA linha (por chave) sem criar novas.

        `timestamp` preserva o horário da PRIMEIRA ocorrência (linhas de erro e de
        "já estavam prontos"). Sem ele, o horário da linha viva também é o do
        NASCIMENTO dela: a atualização do texto não troca o HH:MM:SS (regra do
        usuário, 14/09) — o tempo decorrido aparece só no fechamento, entre
        parênteses. `in_place` reescreve a linha NO LUGAR em vez de jogá-la para
        o fim a cada atualização — sem isso, várias linhas vivas ao mesmo tempo
        (erros por tipo + progresso) ficariam trocando de posição.
        """
        box = getattr(self, "activity_log", None)
        if box is None or not box.winfo_exists():
            return
        box.configure(state="normal")
        if "vad_total" not in box.tag_names():
            box.tag_configure("vad_total", foreground="#0a7a2f")
        # A linha viva também pode receber a cor de sucesso: sem garantir a
        # tag aqui, a primeira linha do lote já nasceria sem cor (a tag só era
        # criada por `_append_activity_log`/`_begin_activity_step`).
        if "activity_step_done" not in box.tag_names():
            box.tag_configure("activity_step_done", foreground="#16833a")
        line_tag = f"phase:{key}"
        if timestamp is None:
            timestamp = self._live_line_birth_stamp(box, line_tag) or time.strftime("%H:%M:%S")
        line = f"{timestamp}  {message}\n"
        follow = self._activity_log_follow_tail(box)
        if in_place and self._replace_live_line(box, line_tag, line, tag):
            self._scroll_activity_log_tail(box, follow)
            box.configure(state="disabled")
            return
        try:
            box.delete(f"{line_tag}.first", f"{line_tag}.last")
        except tk.TclError:
            pass
        if tag:
            box.insert("end", line, (line_tag, tag))
        else:
            box.insert("end", line, line_tag)
        self._scroll_activity_log_tail(box, follow)
        box.configure(state="disabled")

    @staticmethod
    def _live_line_birth_stamp(box, line_tag: str) -> str:
        """Horário em que a linha viva NASCEU (o prefixo `HH:MM:SS` do texto).

        Preservá-lo é regra do usuário (14/09): `Criando ZIP para envio: 15/8910`
        nasce às 01:46:16 e continua mostrando 01:46:16 quando o texto passa para
        `2000/8910` — o tempo decorrido aparece só no fechamento (parênteses).
        Devolve "" quando a linha ainda não existe (linha nova = horário novo).
        """
        try:
            ranges = box.tag_ranges(line_tag)
        except tk.TclError:
            return ""
        if len(ranges) < 2:
            return ""
        try:
            texto = str(box.get(str(ranges[0]), str(ranges[-1])))
        except tk.TclError:
            return ""
        if len(texto) >= 8 and texto[2] == ":" and texto[5] == ":":
            return texto[:8]
        return ""

    def _replace_live_line(self, box, line_tag: str, text: str, tag: str | None) -> bool:
        """Reescreve a linha viva NO LUGAR usando a própria tag.

        `Text.replace` troca o texto do intervalo da tag e reaplica a tag no texto
        novo: a linha fica onde está (ordem estável) e a tag continua válida para
        a próxima atualização. Medições que descartaram as alternativas: `tag.first`
        levanta TclError depois de apagar o texto e a marca com "end-2l linestart"
        cai na linha errada quando há VÁRIAS linhas vivas (a atualização seguinte
        corrompia o log). Antes de existir texto com a tag, a linha é criada no fim
        (append) e a tag passa a valer.
        """
        try:
            ranges = box.tag_ranges(line_tag)
        except tk.TclError:
            return False
        if len(ranges) < 2:
            return False
        tags = (line_tag, tag) if tag else (line_tag,)
        try:
            # A lista de tags vai como UM argumento (tupla): o `replace` do Tk
            # aceita só uma lista e, com argumentos extras, o segundo vira TEXTO
            # no log (medido: "activity_step_error" aparecia dentro da linha).
            box.replace(str(ranges[0]), str(ranges[-1]), text, tags)
        except tk.TclError:
            return False
        return True

    def _register_batch_error(self, label: str, item: str = "") -> None:
        """Uma linha VERMELHA viva por TIPO de erro (regra do usuário, 13/09).

        Antes era uma linha por arquivo: numa fila de 1405 vídeos sem áudio o log
        virava uma parede vermelha e não dava mais para ler nada. A contagem e o
        horário da PRIMEIRA ocorrência ficam na mesma linha; clicar nela copia a
        lista de arquivos daquele tipo (o detalhe não se perde).
        """
        entries = getattr(self, "_batch_error_entries", None)
        if entries is None:
            entries = {}
            self._batch_error_entries = entries
        entry = entries.get(label)
        if entry is None:
            entry = {
                # Slug único por execução: sem isso o fallback por tag apagaria a
                # linha de erro de uma execução anterior (mesmo nome de tag).
                "slug": f"r{getattr(self, '_run_sequence', 0)}err{len(entries) + 1}",
                "count": 0,
                "started_at": time.strftime("%H:%M:%S"),
                "items": [],
            }
            entries[label] = entry
        entry["count"] += 1
        if item:
            entry["items"].append(str(item))
        raw = getattr(self, "_error_line_raw", None)
        if raw is None:
            raw = {}
            self._error_line_raw = raw
        raw[f"phase:{entry['slug']}"] = batch_error_detail(entry["count"], label, entry["items"])
        self._update_activity_line(
            entry["slug"],
            batch_error_text(entry["count"], label),
            "activity_step_error",
            timestamp=entry["started_at"],
            in_place=True,
        )

    def _register_preparation(self, kind: str, total: int) -> None:
        """Linha VERDE: "13/50 arquivos já estavam prontos".

        Só aparece quando existe algum arquivo já no formato pedido (regra do
        usuário, 13/09). O total é o da fila do lote. A cor é a de sucesso
        (`activity_step_done`, pedido do usuário, 27/09): arquivo já no formato
        pedido é um resultado bom, não um aviso.
        """
        if kind not in PREPARATION_LABELS:
            return
        counts = getattr(self, "_prep_counts", None)
        if counts is None:
            counts = {}
            self._prep_counts = counts
        entry = counts.get(kind)
        if entry is None:
            entry = {"count": 0, "started_at": time.strftime("%H:%M:%S"), "total": int(total or 0)}
            counts[kind] = entry
        entry["count"] += 1
        if total:
            entry["total"] = int(total)
        self._update_activity_line(
            f"r{getattr(self, '_run_sequence', 0)}prep:{kind}",
            preparation_text(kind, entry["count"], entry["total"]),
            "activity_step_done",
            timestamp=entry["started_at"],
            in_place=True,
        )

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
        # O HORÁRIO é o do NASCIMENTO da linha e não muda nas atualizações de
        # porcentagem (regra do usuário, 16/09: nenhuma linha de log troca o
        # HH:MM:SS depois de aparecer).
        horario = self._live_line_birth_stamp(box, line_tag) or time.strftime("%H:%M:%S")
        if display == "100%":
            line = f"{horario}  Baixando {path}\n"
        else:
            line = f"{horario}  Baixando {path} - {display}\n"
        follow = self._activity_log_follow_tail(box)
        try:
            box.delete(f"{line_tag}.first", f"{line_tag}.last")
        except tk.TclError:
            pass
        box.insert("end", line, (line_tag, tag or ()))
        if display == "100%" and tag:
            self._sync_file_marks.pop(path, None)
        self._scroll_activity_log_tail(box, follow)
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

    def _copy_error_line_text(self, block_tag: str) -> bool:
        """Copia o cabeçalho + a lista de arquivos de uma linha de erro agregada.

        É o que o clique numa linha vermelha de tipo de erro copia (para o
        detalhe por arquivo não se perder no log enxuto).
        """
        detail = (getattr(self, "_error_line_raw", None) or {}).get(block_tag)
        if not detail:
            return False
        self.root.clipboard_clear()
        self.root.clipboard_append(detail)
        return True

    def _copy_params_block(self, box, block_tag: str) -> bool:
        """Copia a requisição crua do bloco de parâmetros.

        O texto copiado é o da requisição montada (linha de pedido, headers e
        corpo com os parâmetros já prontos) — ver `format_raw_request`. O bloco
        só cai no resumo em uma linha quando o produtor não informou a
        requisição crua (compatibilidade com blocos antigos).
        """
        raw = getattr(self, "_params_block_raw", {}).get(block_tag)
        if not raw:
            ranges = box.tag_ranges(block_tag)
            if len(ranges) < 2:
                return False
            raw = params_block_single_line(box.get(str(ranges[0]), str(ranges[-1])))
        if not raw:
            return False
        self.root.clipboard_clear()
        self.root.clipboard_append(raw)
        return True

    def _append_params_block(self, title: str, params, raw_request: str = "") -> None:
        """Insere bloco de parâmetros: tudo amarelo + tag única do bloco.

        A tag única permite copiar a requisição inteira com um clique em
        qualquer linha do bloco (ver _activity_log_click); `raw_request` é o
        texto cru que vai para a área de transferência.
        """
        box = getattr(self, "activity_log", None)
        if box is None or not box.winfo_exists():
            return
        self._params_block_seq = int(getattr(self, "_params_block_seq", 0) or 0) + 1
        block_tag = f"{PARAMS_BLOCK_TAG_PREFIX}{self._params_block_seq}"
        if raw_request:
            blocks = getattr(self, "_params_block_raw", None)
            if blocks is None:
                blocks = {}
                self._params_block_raw = blocks
            blocks[block_tag] = raw_request
        if "warning" not in box.tag_names():
            box.tag_configure("warning", foreground="#a65300")
        text = format_ws_params_block(title, params)
        box.configure(state="normal")
        follow = self._activity_log_follow_tail(box)
        for part in text.splitlines():
            line = f"{time.strftime('%H:%M:%S')}  {part}\n"
            box.insert(END, line, ("warning", block_tag))
        self._scroll_activity_log_tail(box, follow)
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
            # Linha de erro AGREGADA: copia o cabeçalho + a lista de arquivos do
            # tipo (o detalhe por arquivo não fica mais no log — fica aqui).
            for tag in tags:
                if self._copy_error_line_text(tag):
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
        # A verificação automática do startup loga igual à manual (o log
        # mostra "Verificando atualizações" como se o usuário tivesse
        # clicado): abre a etapa e roda o worker em modo manual, então o
        # "Não tem!" e os erros também aparecem no log.
        if self.update_check_thread and self.update_check_thread.is_alive():
            return
        self._begin_activity_step("update:check", "Verificando atualizações")
        self._update_check_started = time.perf_counter()
        self.update_check_thread = threading.Thread(
            target=self._update_check_worker,
            args=(True,),
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
            outer,
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
        # Segue o fim do log enquanto o usuário não levar a barra para cima
        # (regra do usuário, 13/09: a atualização não pode mover a barra).
        self._activity_log_tail_following = True
        activity_scroll = ttk.Scrollbar(
            activity_box, orient="vertical", command=self._activity_log_scrollbar_command
        )
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
        # Rolagem do usuário (roda do mouse sobre o log ou sobre a barra) e o
        # redimensionamento da janela reavaliam o acompanhamento do fim.
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.activity_log.bind(sequence, self._activity_log_on_user_scroll, add="+")
        self.activity_log.bind("<Configure>", self._activity_log_on_configure, add="+")

        self.live_tab = ttk.Frame(self.tab_content, padding=(14, 2, 14, 14))
        self.files_tab = ttk.Frame(self.tab_content, padding=14)
        self.assistant_tab = ttk.Frame(self.tab_content, padding=14)
        self.imei_tab = ttk.Frame(self.tab_content, padding=14)
        self.ffmpeg_tab = ttk.Frame(self.tab_content, padding=14)
        self.qualification_tab = ttk.Frame(self.tab_content, padding=14)
        self.diarias_tab = ttk.Frame(self.tab_content, padding=14)
        self.qrcode_tab = ttk.Frame(self.tab_content, padding=14)
        self._build_diarias_section()

        # The live workflow intentionally keeps transcript, history and statement together,
        # matching the Android screen.  The old assistant frame remains internal only.
        live_frame = ttk.Frame(self.live_tab, width=900)
        live_frame.pack(fill=BOTH, expand=True, anchor="n")
        live_top = ttk.Frame(live_frame)
        live_top.pack(fill=X)
        self.live_top = live_top
        live_top.bind("<Configure>", self._on_live_top_configure, add="+")

        # Controles da linha do servidor local x controles dos provedores de
        # API. Tudo num container único e na ordem fixa (intervalo, timestamps,
        # diarização/idioma/keywords) para que omitir um membro NÃO precise de
        # `pack(before=...)`: o pack só reflui o que está visível — o `before`
        # apontando para um irmão oculto levanta TclError ("isn't packed").
        self.live_line_controls = ttk.Frame(live_top)
        self.live_line_controls.pack(side=LEFT)

        # Grupo "- t = +": intervalo de TEMPO das fatias REST do servidor STT
        # LOCAL (Granite NAR). Fica num frame próprio porque a visibilidade é
        # CONDICIONAL ao modelo escolhido (`_refresh_live_local_server_controls`)
        # — sem o frame, esconder o grupo exigiria esconder widget por widget e
        # a linha não fecharia à esquerda sozinha.
        self.live_interval_controls = ttk.Frame(self.live_line_controls)
        self.live_interval_minus = ttk.Button(
            self.live_interval_controls, text="-", width=3, command=lambda: self._change_live_interval(-1)
        )
        self.live_interval_minus.pack(side=LEFT)
        ttk.Label(self.live_interval_controls, text=" t =", style="Muted.TLabel").pack(side=LEFT, padx=(6, 2))
        self.live_interval_entry = ttk.Combobox(
            self.live_interval_controls,
            textvariable=self.live_interval_var,
            values=tuple(f"{value / 1000:.1f}" for value in LIVE_INTERVAL_VALUES_MS),
            width=5,
            justify="center",
            state="readonly",
        )
        self.live_interval_entry.pack(side=LEFT)
        self.live_interval_entry.bind("<<ComboboxSelected>>", lambda _event: self._apply_live_interval_entry())
        self.live_interval_plus = ttk.Button(
            self.live_interval_controls, text="+", width=3, command=lambda: self._change_live_interval(1)
        )
        self.live_interval_plus.pack(side=LEFT, padx=(6, 8))
        self.live_interval_controls.pack(side=LEFT)
        # Timestamps: só faz sentido nos provedores de API (o Granite NAR local
        # não devolve marcação por palavra) — a visibilidade segue o mesmo
        # refresh do grupo do intervalo.
        self.live_timestamps_check = ttk.Checkbutton(
            self.live_line_controls,
            text="Timestamps",
            variable=self.live_timestamps_var,
            command=self._toggle_live_timestamps,
            state="disabled",
        )
        self.live_timestamps_check.pack(side=LEFT, padx=(0, 10))
        self.live_grok_controls = ttk.Frame(self.live_line_controls)
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
        self.live_keywords_label_var = StringVar(master=self.root, value=f"Keywords: {KEYWORDS_OFF_LABEL}")
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
        # Varinha mágica: à DIREITA do "Recuperar" (pedido do usuário, 29/09).
        # Ajusta o texto da transcrição em uma linha só. Fica na faixa de botões
        # e NÃO dentro da caixa de texto: colocar dentro empurrava a caixa para
        # a direita e estragava o layout.
        self.live_transcript_wand_button = self._make_square_icon_button(
            self.live_transcript_actions,
            self.magic_wand_icon,
            None,
            lambda: self.adjust_live_statement_text("transcript"),
        )
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
        # Mesma varinha na coluna 2 (mesma posição: à direita do "Recuperar").
        self.live_transcript_wand_button_2 = self._make_square_icon_button(
            self.live_transcript_actions_2,
            self.magic_wand_icon,
            None,
            lambda: self.adjust_live_statement_text("transcript2"),
        )
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
            # Varinha mágica: à DIREITA do "Recuperar" (pedido do usuário,
            # 29/09). Ajusta o texto do histórico em uma linha só. Fica na faixa
            # de botões, e não dentro da caixa de texto (empurrava a caixa).
            wand_button = self._make_square_icon_button(
                actions,
                self.magic_wand_icon,
                None,
                lambda kind=suffix: self.adjust_live_statement_text(kind),
            )
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
            return recover_button, parts_button, parts_menu, statement_button, clear_button, wand_button, actions

        (
            self.live_history_recover_button,
            self.live_parts_button,
            self.live_parts_menu,
            self.live_statement_button,
            self.live_history_clear_button,
            self.live_history_wand_button,
            self.live_history_actions,
        ) = build_history_actions(
            self.live_history_primary_pane, "history", self.request_live_statement, self.live_assistant_part_var
        )
        (
            self.live_history_recover_button_2,
            self.live_parts_button_2,
            self.live_parts_menu_2,
            self.live_statement_button_2,
            self.live_history_clear_button_2,
            self.live_history_wand_button_2,
            self.live_history_actions_2,
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
            # Varinha mágica: à DIREITA do "Recuperar" (pedido do usuário,
            # 29/09). Ajusta o texto da oitiva em uma linha só.
            adjust_button = self._make_square_icon_button(
                actions,
                self.magic_wand_icon,
                None,
                lambda kind=suffix: self.adjust_live_statement_text(kind),
            )
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
            if suffix == "statement":
                self.live_statement_adjust_button = adjust_button
                self.live_statement_actions = actions
            else:
                self.live_statement_adjust_button_2 = adjust_button
                self.live_statement_actions_2 = actions
            actions.bind(
                "<Configure>",
                lambda _event: self.root.after_idle(self._position_live_statement_actions),
                add="+",
            )
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

        self._build_imei_tab()

        self.ffmpeg_tools = FfmpegToolsPanel(self.ffmpeg_tab, self)
        self._build_qualification_tab()
        self._build_qrcode_tab()

        file_top = ttk.Frame(self.files_tab)
        file_top.pack(fill=X)

        self.action_canvas = Canvas(file_top, width=74, height=74, highlightthickness=0, background="#f4f7f6")
        self.action_canvas.pack(side=RIGHT, padx=(16, 2))
        self.action_canvas.bind("<Button-1>", lambda _event: self.toggle_run())
        self.action_canvas.bind("<Configure>", lambda _event: self._draw_action_button())
        create_tooltip(self.action_canvas, "Executar ou cancelar a transcrição")
        self._draw_action_button()

        self.folder_canvas = Canvas(file_top, width=56, height=56, highlightthickness=0, background="#f4f7f6")
        self.folder_canvas.bind("<Button-1>", lambda _event: self._open_temp_folder())
        self.folder_canvas.bind("<Configure>", lambda _event: self._draw_folder_button())
        create_tooltip(self.folder_canvas, "Abrir pasta de saída")
        self._draw_folder_button()  # some ao limpar

        self.save_canvas = Canvas(file_top, width=56, height=56, highlightthickness=0, background="#f4f7f6")
        self.save_canvas.bind("<Button-1>", lambda _event: self.save_html_report())
        self.save_canvas.bind("<Configure>", lambda _event: self._draw_save_button())
        create_tooltip(self.save_canvas, "Salvar resultado da transcrição")
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

        # Checkbox "Um modelo por vez" (entre o botão "Modelos" e o seletor de
        # Idioma, regra do usuário 13/09): marcada, o lote NÃO manda os áudios
        # para os modelos ao mesmo tempo — a fila inteira vai para um modelo e
        # só depois de ele terminar o próximo começa. O HTML continua sendo
        # gerado uma única vez, no fim de TODOS os modelos.
        self.files_one_model_check = ttk.Checkbutton(
            options2,
            text="Um modelo por vez",
            variable=self.files_one_model_var,
        )
        self.files_one_model_check.pack(side=LEFT, padx=(12, 0))

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

    def _build_tool_styles(self) -> None:
        style = ttk.Style(self.root)
        style.configure("Tool.Title.TLabel", background="#f4f7f6", foreground="#193d32", font=("Segoe UI Semibold", 20))
        style.configure("Tool.Card.TFrame", background="#ffffff", bordercolor="#dce6df", relief="solid", borderwidth=1)
        style.configure("Tool.Result.TFrame", background="#edf6f0", bordercolor="#d5e5da", relief="solid", borderwidth=1)
        style.configure("Tool.Section.TLabel", background="#ffffff", foreground="#244d3a", font=("Segoe UI Semibold", 11))
        style.configure("Tool.Field.TLabel", background="#ffffff", foreground="#66766e", font=("Segoe UI", 9))
        style.configure("Tool.Text.TLabel", background="#ffffff", foreground="#344d42", font=("Segoe UI", 10))
        style.configure("Tool.Result.TLabel", background="#edf6f0", foreground="#315c48", font=("Segoe UI", 10))
        style.configure("Tool.Imei.TLabel", background="#edf6f0", foreground="#193d32", font=("Consolas", 22))
        style.configure("Tool.TEntry", padding=(8, 7), fieldbackground="#ffffff", bordercolor="#cbdad1")
        style.configure("Tool.TCheckbutton", background="#ffffff", foreground="#344d42", font=("Segoe UI", 10))
        style.map("Tool.TCheckbutton", background=[("active", "#ffffff")])
        style.configure("Tool.Primary.TButton", background="#216b4a", foreground="#ffffff",
                        bordercolor="#216b4a", lightcolor="#216b4a", darkcolor="#216b4a",
                        font=("Segoe UI Semibold", 10), padding=(12, 9))
        style.map("Tool.Primary.TButton", background=[("disabled", "#dce6df"), ("active", "#185638")],
                  foreground=[("disabled", "#83958a")])
        style.configure("Tool.Secondary.TButton", background="#f1f6f3", foreground="#315c48",
                        bordercolor="#d5e2d9", lightcolor="#f1f6f3", darkcolor="#f1f6f3",
                        font=("Segoe UI", 10), padding=(10, 6))
        style.map("Tool.Secondary.TButton", background=[("disabled", "#f0f3f1"), ("active", "#e1eee5")],
                  foreground=[("disabled", "#96a39a")])
        style.configure("Compact.Tool.Secondary.TButton", font=("Segoe UI", 9), padding=(7, 5))

    def _tool_icon_photo(self, kind: str, size: int = 24, *, enabled: bool = True, circular: bool = False, foreground: str | None = None):
        cache = getattr(self, "_tool_icon_photos", None)
        if cache is None:
            self._tool_icon_photos = cache = {}
        key = (kind, size, enabled, circular, foreground)
        if key not in cache:
            cache[key] = ImageTk.PhotoImage(tool_action_icon_image(
                kind, size, enabled=enabled, circular=circular, foreground=foreground), master=self.root)
        return cache[key]

    def _build_imei_tab(self) -> None:
        self._build_tool_styles()
        frame = ttk.Frame(self.imei_tab)
        frame.pack(fill=BOTH, expand=True)
        ttk.Label(frame, text="Consulta de IMEI", style="Tool.Title.TLabel").pack(anchor="w", pady=(4, 2))
        ttk.Label(frame, text="Identifique o aparelho pelo TAC e pelo número de série.",
                  style="Muted.TLabel").pack(anchor="w")
        self.imei_cards = cards = ttk.Frame(frame)
        cards.pack(fill=X, pady=(18, 0))
        cards.columnconfigure(0, weight=1, uniform="imei")
        cards.columnconfigure(1, weight=1, uniform="imei")
        self.imei_input_card = inputs = ttk.Frame(cards, style="Tool.Card.TFrame", padding=18)
        ttk.Label(inputs, text="Identificação", image=self._tool_icon_photo("phone"), compound=LEFT,
                  style="Tool.Section.TLabel").pack(anchor="w", pady=(0, 14))
        fields = ttk.Frame(inputs, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        fields.pack(fill=X)
        fields.columnconfigure(0, weight=1, uniform="numbers")
        fields.columnconfigure(1, weight=1, uniform="numbers")
        ttk.Label(fields, text="TAC · 8 dígitos", style="Tool.Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(fields, text="Série · 6 dígitos", style="Tool.Field.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 6))
        self.imei_tac_entry = ttk.Entry(fields, textvariable=self.imei_tac_var, font=("Consolas", 18),
                                       justify="center", width=1, style="Tool.TEntry")
        self.imei_tac_entry.grid(row=1, column=0, sticky="ew")
        self.imei_sn_entry = ttk.Entry(fields, textvariable=self.imei_sn_var, font=("Consolas", 18),
                                      justify="center", width=1, style="Tool.TEntry")
        self.imei_sn_entry.grid(row=1, column=1, sticky="ew", padx=(12, 0))
        note = ttk.Label(inputs, text="O cálculo do dígito e a consulta do modelo são automáticos.",
                         style="Tool.Field.TLabel", wraplength=260, justify="left")
        note.pack(fill=X, pady=(12, 0))
        inputs.bind("<Configure>", lambda event: note.configure(wraplength=max(120, event.width - 38)))
        self.imei_tac_var.trace_add("write", lambda *_args: self._update_imei_inputs())
        self.imei_sn_var.trace_add("write", lambda *_args: self._update_imei_inputs())
        self.imei_sn_entry.bind("<BackSpace>", self._imei_sn_backspace)
        create_tooltip(self.imei_tac_entry, "TAC de 8 dígitos. Você também pode colar os 14 primeiros dígitos do IMEI.")
        create_tooltip(self.imei_sn_entry, "Número de série de 6 dígitos.")

        self.imei_result_card = result = ttk.Frame(cards, style="Tool.Result.TFrame", padding=18)
        self.imei_result_details = details = ttk.Frame(result, style="Tool.Result.TFrame", relief="flat", borderwidth=0)
        details.pack(fill=X)
        ttk.Label(details, text="IMEI completo", style="Tool.Result.TLabel").pack(anchor="w")
        self.imei_full_var = StringVar(master=self.root, value="—")
        ttk.Label(details, textvariable=self.imei_full_var, style="Tool.Imei.TLabel").pack(anchor="w", pady=(7, 3))
        ttk.Label(details, textvariable=self.imei_result_var, style="Tool.Result.TLabel").pack(anchor="w")
        self.imei_copy_button = ttk.Button(result, text="Copiar IMEI", image=self._tool_icon_photo("copy"),
                                          compound=LEFT, style="Tool.Secondary.TButton", command=self.copy_full_imei,
                                          state="disabled")
        self.imei_copy_button.pack(fill=X, pady=(12, 0))
        cards.bind("<Configure>", lambda event: self._layout_imei_cards(event.width))
        self._layout_imei_cards(800)

        model = ttk.Label(frame, textvariable=self.imei_model_var, style="Muted.TLabel", justify="left", wraplength=600)
        model.pack(fill=X, pady=(12, 0))
        frame.bind("<Configure>", lambda event: model.configure(wraplength=max(200, event.width - 8)))
        self.imei_status_label = ttk.Label(frame, textvariable=self.imei_status_var, style="Muted.TLabel")
        self.imei_status_var.trace_add("write", lambda *_args: self._refresh_imei_status_visibility())
        self.imei_history_container = history = ttk.Frame(frame, style="Tool.Card.TFrame", padding=14)
        history.pack(fill=BOTH, expand=True, pady=(14, 0))
        header = ttk.Frame(history, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        header.pack(fill=X, pady=(0, 8))
        ttk.Label(header, text="Histórico", image=self._tool_icon_photo("history", 22), compound=LEFT,
                  style="Tool.Section.TLabel").pack(side=LEFT)
        actions = ttk.Frame(header, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        actions.pack(side=RIGHT)
        self.imei_toggle_button = ttk.Button(actions, textvariable=self.imei_toggle_var,
                                            image=self._tool_icon_photo("history", 20), compound=LEFT,
                                            style="Tool.Secondary.TButton", command=self.toggle_imei_history)
        self.imei_clear_history_button = ttk.Button(actions, text="Limpar histórico",
                                                   image=self._tool_icon_photo("clear", 20), compound=LEFT,
                                                   style="Tool.Secondary.TButton", command=self.clear_imei_history)
        self.imei_clear_history_button.pack(side=LEFT)
        history_body = ttk.Frame(history, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        history_body.pack(fill=BOTH, expand=True)
        self.imei_history_text = Text(history_body, width=1, height=5, wrap="word", font=("Segoe UI", 10),
                                      background="#ffffff", foreground="#344d42", relief="flat", borderwidth=0,
                                      padx=2, pady=6)
        scroll = ttk.Scrollbar(history_body, orient="vertical", command=self.imei_history_text.yview)
        self.imei_history_text.configure(yscrollcommand=scroll.set, state="disabled")
        self.imei_history_text.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        self.imei_history_text.tag_configure("empty", foreground="#86978d", justify="center")
        self.refresh_imei_history()
        self._refresh_imei_status_visibility()

    def _refresh_imei_status_visibility(self) -> None:
        if self.imei_status_var.get():
            self.imei_status_label.pack(anchor="w", pady=(2, 0), before=self.imei_history_container)
        else:
            self.imei_status_label.pack_forget()

    def _layout_imei_cards(self, width: int) -> None:
        columns = 2 if width >= 620 else 1
        if getattr(self, "_imei_card_columns", None) == columns:
            return
        self._imei_card_columns = columns
        self.imei_cards.columnconfigure(1, weight=1 if columns == 2 else 0)
        self.imei_input_card.grid(row=0, column=0, columnspan=1 if columns == 2 else 2,
                                  sticky="nsew", padx=(0, 12 if columns == 2 else 0))
        self.imei_result_card.grid(row=0 if columns == 2 else 1, column=1 if columns == 2 else 0,
                                   columnspan=1 if columns == 2 else 2, sticky="nsew",
                                   pady=(0, 0 if columns == 2 else 12))
        if columns == 1:
            self.imei_result_card.grid_configure(pady=(12, 0))
            self.imei_copy_button.pack(side=RIGHT, fill="none", padx=(16, 0), pady=0, before=self.imei_result_details)
        else:
            self.imei_copy_button.pack(side=TOP, fill=X, padx=0, pady=(12, 0), after=self.imei_result_details)


    def _build_qrcode_tab(self) -> None:
        """Formulário à esquerda e prévia quadrada que acompanha o espaço disponível."""
        self._build_tool_styles()
        frame = ttk.Frame(self.qrcode_tab)
        frame.pack(fill=BOTH, expand=True)
        ttk.Label(frame, text="QR Code", style="Tool.Title.TLabel").pack(anchor="w", pady=(4, 2))
        ttk.Label(frame, text="Transforme um link em uma imagem pronta para compartilhar.",
                  style="Muted.TLabel").pack(anchor="w")
        cards = ttk.Frame(frame)
        cards.pack(fill=BOTH, expand=True, pady=(18, 0))
        cards.grid_propagate(False)
        cards.rowconfigure(0, weight=1)
        cards.columnconfigure(0, weight=1, uniform="qrcode")
        cards.columnconfigure(1, weight=1, uniform="qrcode")
        form = ttk.Frame(cards, style="Tool.Card.TFrame", padding=18)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(form, text="Link de destino", style="Tool.Section.TLabel").pack(anchor="w", pady=(0, 12))
        self.qrcode_link_entry = ttk.Entry(form, textvariable=self.qrcode_link_var, font=("Segoe UI", 11),
                                           width=1, style="Tool.TEntry")
        self.qrcode_link_entry.pack(fill=X)
        self.qrcode_link_entry.bind("<Return>", lambda _event: self.generate_qrcode())
        link_actions = ttk.Frame(form, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        link_actions.pack(fill=X, pady=(10, 20))
        self.qrcode_paste_button = ttk.Button(link_actions, text="Colar", image=self._tool_icon_photo("paste", 22),
                                             compound=LEFT, style="Compact.Tool.Secondary.TButton", command=self.paste_qrcode_link)
        self.qrcode_paste_button.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        self.qrcode_clear_button = ttk.Button(link_actions, text="Limpar", image=self._tool_icon_photo("clear", 22),
                                             compound=LEFT, style="Compact.Tool.Secondary.TButton", command=self.clear_qrcode)
        self.qrcode_clear_button.pack(side=LEFT, fill=X, expand=True)
        ttk.Separator(form).pack(fill=X, pady=(0, 18))
        self.qrcode_shorten_check = ttk.Checkbutton(form, text="Encurtar link", variable=self.qrcode_shorten_var,
                                                   style="Tool.TCheckbutton", command=self._qrcode_shorten_toggled)
        self.qrcode_shorten_check.pack(anchor="w", pady=(0, 12))
        ttk.Label(form, text="Alias (opcional)", style="Tool.Field.TLabel").pack(anchor="w", pady=(0, 6))
        self.qrcode_alias_entry = ttk.Entry(form, textvariable=self.qrcode_alias_var, font=("Segoe UI", 10),
                                            width=1, style="Tool.TEntry", state="disabled")
        self.qrcode_alias_entry.pack(fill=X)
        self.qrcode_alias_entry.bind("<Return>", lambda _event: self.generate_qrcode())
        self.qrcode_form_actions = footer = ttk.Frame(form, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        footer.pack(side=BOTTOM, fill=X, pady=(24, 0))
        self.qrcode_generate_button = ttk.Button(footer, text="Gerar QR Code",
                                                 image=self._tool_icon_photo("qrcode", 24, foreground="#ffffff"), compound=LEFT,
                                                 style="Tool.Primary.TButton", command=self.generate_qrcode)
        self.qrcode_generate_button.pack(fill=X)
        status = ttk.Label(footer, textvariable=self.qrcode_status_var, style="Tool.Field.TLabel",
                           wraplength=260, justify="left")
        status.pack(fill=X, pady=(10, 0))
        form.bind("<Configure>", lambda event: status.configure(wraplength=max(120, event.width - 38)))

        self.qrcode_shortened_row = ttk.Frame(form, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        ttk.Label(self.qrcode_shortened_row, text="Link encurtado", style="Tool.Field.TLabel").pack(anchor="w", pady=(0, 6))
        shortened = ttk.Frame(self.qrcode_shortened_row, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        shortened.pack(fill=X)
        self.qrcode_shortened_entry = ttk.Entry(shortened, textvariable=self.qrcode_shortened_var, font=("Segoe UI", 10),
                                                state="readonly", width=1, style="Tool.TEntry")
        self.qrcode_shortened_entry.pack(side=LEFT, fill=X, expand=True)
        self.qrcode_shortened_copy_button = ttk.Button(shortened, image=self._tool_icon_photo("copy", 22),
                                                       style="Tool.Secondary.TButton", command=self.copy_shortened_link,
                                                       state="disabled")
        self.qrcode_shortened_copy_button.pack(side=LEFT, padx=(6, 0))
        create_tooltip(self.qrcode_shortened_copy_button, "Copiar link encurtado")

        self.qrcode_content = self.qrcode_preview_card = preview = ttk.Frame(cards, style="Tool.Card.TFrame", padding=18)
        preview.grid(row=0, column=1, sticky="nsew")
        self.qrcode_preview_heading = ttk.Label(preview, text="Prévia", style="Tool.Section.TLabel")
        self.qrcode_preview_heading.pack(anchor="w")
        self.qrcode_actions_frame = ttk.Frame(preview, style="Tool.Card.TFrame", relief="flat", borderwidth=0)
        self.qrcode_actions_frame.pack(side=BOTTOM, fill=X)
        self.qrcode_copy_button = ttk.Button(self.qrcode_actions_frame, text="Copiar imagem",
                                             image=self._tool_icon_photo("copy", 24), compound=LEFT,
                                             style="Tool.Secondary.TButton", command=self.copy_qrcode_image,
                                             state="disabled")
        self.qrcode_copy_button.pack(fill=X)
        self.qrcode_canvas = Canvas(preview, width=320, height=320, highlightthickness=0, borderwidth=0, background="#ffffff")
        self.qrcode_canvas.pack(anchor="center", expand=True, pady=(16, 16))
        preview.bind("<Configure>", lambda _event: self._fit_qrcode_preview())
        self._draw_qrcode_placeholder()
        self.root.after_idle(self._fit_qrcode_preview)

    def _fit_qrcode_preview(self) -> None:
        card = self.qrcode_preview_card
        if not card.winfo_ismapped():
            return
        size = max(180, min(420, card.winfo_width() - 40, card.winfo_height() - 132))
        if int(self.qrcode_canvas["width"]) != size:
            self.qrcode_canvas.configure(width=size, height=size)
            self._render_qrcode()

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
        # Preenche o quadro: maior escala INTEIRA que cabe na area de exibicao
        # e SEM margem branca (pedido do usuario, 12/09). O resto da divisao
        # fica so na centralizacao. Sem piso artificial alem do 1: versoes
        # altas (v23+) precisam de escala menor para nao cortar o QR Code.
        scale = max(1, canvas_size // code.size)
        image = code.to_image(scale=scale, border=0)
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
            qr_encoder.copy_image_to_windows_clipboard(
                self.qrcode.to_image(scale=QRCODE_COPY_SCALE, border=QRCODE_COPY_BORDER)
            )
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
                self._prompt_ativo("qualificacao_system", DEFAULT_QUALIFICATION_SYSTEM_PROMPT),
                self._prompt_qualificacao_ativo(field_ids, raw_text),
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

    # --- Aba Diárias: holerite + talão + protocolo
    def _build_diarias_section(self):
        """Cartões compactos de anexos e dados; ações individuais e conjuntas."""
        self.diarias_busy = False
        self.diarias_task = None
        self.diarias_job_events = queue.Queue()
        self.diarias_job_after = None
        if not hasattr(self, "diarias_escala_file_var"):
            self.diarias_escala_file_var = StringVar(master=self.root)
            self.diarias_escala_path = ""
        self.diarias_validation_var = StringVar(master=self.root)
        self.diarias_status_var = StringVar(master=self.root)
        self.diarias_field_entries = {}
        self.diarias_field_alerts = {}
        self.diarias_attachment_alerts = {}
        self.diarias_alert_icon = ImageTk.PhotoImage(diarias_action_icon_image("warning", 16), master=self.root)
        self.diarias_fields_warned = False
        self.diarias_attachment_buttons = []
        heading = ttk.Frame(self.diarias_tab)
        heading.pack(fill=X, pady=(0, 10))
        ttk.Label(heading, text="Diárias", style="Diarias.Title.TLabel").pack(anchor="w")
        ttk.Label(heading, text="Selecione o perfil, anexe os PDFs e confira os nove campos.", style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        profile_row = ttk.Frame(heading)
        profile_row.pack(fill=X, pady=(10, 0))
        ttk.Label(profile_row, text="Perfil").pack(side=LEFT, padx=(0, 8))
        self.diarias_profile_var = StringVar(master=self.root)
        self.diarias_profile_selector = ttk.Combobox(profile_row, textvariable=self.diarias_profile_var, state="readonly", width=22)
        self.diarias_profile_selector.pack(side=LEFT)
        self.diarias_profile_selector.bind("<<ComboboxSelected>>", self._select_diarias_profile)
        self.diarias_profile_alert = ttk.Label(profile_row, image=self.diarias_alert_icon)
        create_tooltip(self.diarias_profile_alert, "Confira o perfil selecionado e seus dados nas configurações.")
        self.diarias_configure_button = ttk.Button(profile_row, text="Configurar perfis", command=lambda: self.open_settings(police_subtab="Diárias"))
        self.diarias_configure_button.pack(side=LEFT, padx=(8, 0))
        self._refresh_diarias_profiles()
        ttk.Label(heading, textvariable=self.diarias_validation_var, foreground="#b42318", wraplength=820).pack(anchor="w", pady=(4, 0))

        footer = ttk.Frame(self.diarias_tab)
        footer.pack(side="bottom", fill=X, pady=(10, 0))
        ttk.Separator(footer).pack(fill=X, pady=(0, 8))
        self.diarias_individual_actions = ttk.Frame(footer)
        self.diarias_individual_actions.pack(fill=X)
        self.diarias_generate_button = ttk.Button(self.diarias_individual_actions, text="Gerar requerimento", style="Diarias.Primary.TButton", cursor="hand2", command=self._generate_diarias_requerimento)
        self.diarias_generate_map_button = ttk.Button(self.diarias_individual_actions, text="Gerar mapa", style="Diarias.Primary.TButton", cursor="hand2", command=self._generate_diarias_mapa)
        self.diarias_meios_proprios_button = ttk.Button(self.diarias_individual_actions, text="Gerar declaração Meios Próprios", style="Diarias.Primary.TButton", cursor="hand2", command=self._generate_diarias_meios_proprios)
        self.diarias_individual_buttons = [self.diarias_generate_button, self.diarias_generate_map_button, self.diarias_meios_proprios_button]
        self.diarias_batch_actions = ttk.Frame(footer)
        self.diarias_batch_actions.pack(fill=X, pady=(8, 0))
        self.diarias_action_icons = {kind: ImageTk.PhotoImage(diarias_action_icon_image(kind), master=self.root) for kind in ("office", "pdf", "print")}
        self.diarias_generate_bundle_button = ttk.Button(self.diarias_batch_actions, text="Gerar docx/xlsx", image=self.diarias_action_icons["office"], compound=LEFT, style="Diarias.Output.TButton", command=lambda: self._generate_diarias_bundle(pdf=False))
        self.diarias_generate_pdfs_button = ttk.Button(self.diarias_batch_actions, text="Gerar PDFs", image=self.diarias_action_icons["pdf"], compound=LEFT, style="Diarias.Output.TButton", command=lambda: self._generate_diarias_bundle(pdf=True))
        self.diarias_print_button = ttk.Button(self.diarias_batch_actions, text="Imprimir diária", image=self.diarias_action_icons["print"], compound=LEFT, style="Diarias.Output.TButton", command=self._print_diaria)
        self.diarias_batch_buttons = [self.diarias_generate_bundle_button, self.diarias_generate_pdfs_button, self.diarias_print_button]
        ttk.Label(footer, textvariable=self.diarias_status_var, style="Muted.TLabel", wraplength=820).pack(anchor="w", pady=(6, 0))

        def arrange_actions(_event=None):
            columns = 1 if footer.winfo_width() < 560 else 3
            for controls in (self.diarias_individual_buttons, self.diarias_batch_buttons):
                for index, button in enumerate(controls):
                    button.grid(row=index // columns, column=index % columns, sticky="w", padx=(0, 8), pady=(0, 4))
        footer.bind("<Configure>", arrange_actions)
        arrange_actions()

        viewport = ttk.Frame(self.diarias_tab)
        viewport.pack(fill=BOTH, expand=True)
        canvas = Canvas(viewport, highlightthickness=0, background="#f4f7f6", width=1)
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        def update_scrollbar(first, last):
            scrollbar.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                scrollbar.pack_forget()
            elif not scrollbar.winfo_manager():
                scrollbar.pack(before=canvas, side=RIGHT, fill=Y, padx=(8, 0))
        canvas.configure(yscrollcommand=update_scrollbar)
        body = ttk.Frame(canvas)
        body_window = canvas.create_window(0, 0, window=body, anchor="nw")
        self.diarias_sections = {}
        def arrange_cards(event):
            width = min(event.width, 900)
            canvas.itemconfigure(body_window, width=width)
            columns = 2 if width >= 760 else 1
            for column in (0, 1):
                body.columnconfigure(column, weight=1 if column < columns else 0, uniform="diarias" if column < columns else "")
            for index, card in enumerate(self.diarias_sections.values()):
                card.grid(row=index // columns, column=index % columns, sticky="new", padx=(0, 10 if columns == 2 and index % 2 == 0 else 0), pady=(0, 10))
        canvas.bind("<Configure>", arrange_cards)
        body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))

        def section(title, kind, file_var):
            card = ttk.Frame(body, style="Diarias.Card.TFrame", padding=(12, 10))
            self.diarias_sections[title] = card
            header = ttk.Frame(card, style="Diarias.Card.TFrame")
            header.pack(fill=X, pady=(0, 8 if kind != "escala" else 0))
            header.columnconfigure(1, weight=1)
            title_row = ttk.Frame(header, style="Diarias.Card.TFrame")
            title_row.grid(row=0, column=0, sticky="w")
            ttk.Label(title_row, text=title, style="Diarias.Section.TLabel").pack(side=LEFT)
            alert = ttk.Label(title_row, image=self.diarias_alert_icon, style="Diarias.Field.TLabel")
            self.diarias_attachment_alerts[kind] = alert
            create_tooltip(alert, f"Anexe o PDF de {title.lower()}.")
            filename = ttk.Label(header, textvariable=file_var, width=1, anchor="w", style="Diarias.File.TLabel")
            filename.grid(row=0, column=1, sticky="ew", padx=8)
            select = ttk.Button(header, text="Selecionar PDF", style="Diarias.Pdf.TButton", command=lambda: self._select_diarias_pdf(kind))
            select.grid(row=0, column=2)
            self.diarias_attachment_buttons.append(select)
            create_tooltip(select, f"Selecionar o PDF de {title.lower()}")
            if kind != "escala":
                reload_button = ttk.Button(header, text="⟳", width=3, style="Diarias.Reload.TButton", command=lambda: self._reload_diarias_pdf(kind))
                reload_button.grid(row=0, column=3, padx=(4, 0))
                self.diarias_attachment_buttons.append(reload_button)
                create_tooltip(reload_button, "Extrair novamente os dados do PDF")
            fields = ttk.Frame(card, style="Diarias.Card.TFrame")
            if kind != "escala":
                fields.pack(fill=X)
            return fields

        def field(parent, column, label, key, width=12):
            variable = getattr(self, f"diarias_{key}_var")
            label_row = ttk.Frame(parent, style="Diarias.Card.TFrame")
            label_row.grid(row=0, column=column, sticky="w", padx=(0, 8), pady=(0, 3))
            ttk.Label(label_row, text=label, style="Diarias.Field.TLabel").pack(side=LEFT)
            alert = ttk.Label(label_row, image=self.diarias_alert_icon, style="Diarias.Field.TLabel")
            self.diarias_field_alerts[key] = alert
            create_tooltip(alert, "Preencha este campo.")
            entry = ttk.Entry(parent, textvariable=variable, width=width)
            entry.grid(row=1, column=column, sticky="w", padx=(0, 8))
            self.diarias_field_entries[key] = entry
            variable.trace_add("write", self._update_diarias_required_fields)

        holerite = section("Holerite", "holerite", self.diarias_holerite_file_var)
        field(holerite, 0, "Total (R$)", "holerite_total", 18)
        field(holerite, 1, "Mês/ano", "holerite_mes", 10)
        self.diarias_month_warning_var = StringVar(master=self.root)
        self.diarias_month_warning_label = ttk.Label(holerite, textvariable=self.diarias_month_warning_var, style="Diarias.Field.TLabel", foreground="#b42318", wraplength=380)
        self.diarias_month_warning_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        for variable in (self.diarias_holerite_mes_var, self.diarias_abertura_data_var):
            variable.trace_add("write", self._update_diarias_month_warning)
        self._update_diarias_month_warning()
        talao = section("Talão", "talao", self.diarias_talao_file_var)
        field(talao, 0, "Ida · data", "abertura_data")
        field(talao, 1, "Hora", "abertura_hora", 7)
        field(talao, 2, "Volta · data", "fechamento_data")
        field(talao, 3, "Hora", "fechamento_hora", 7)
        self.diarias_meios_proprios_checkbox = ttk.Checkbutton(talao, text="Meios Próprios", variable=self.diarias_meios_proprios_var, style="Diarias.TCheckbutton")
        self.diarias_meios_proprios_checkbox.grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        protocolo = section("Protocolo", "protocolo", self.diarias_protocolo_file_var)
        field(protocolo, 0, "Requerimento", "req")
        field(protocolo, 1, "Mapa", "mapa")
        field(protocolo, 2, "Data", "data")
        section("Escala", "escala", self.diarias_escala_file_var)
        def scroll(event):
            if body.winfo_height() > canvas.winfo_height():
                canvas.yview_scroll((-1 if event.delta > 0 else 1) * max(1, abs(event.delta) // 120), "units")
            return "break"
        def bind_scroll(widget):
            widget.bind("<MouseWheel>", scroll, add="+")
            for child in widget.winfo_children():
                bind_scroll(child)
        bind_scroll(canvas)

    def _update_diarias_required_fields(self, *_trace_args):
        if not self.diarias_fields_warned:
            return
        missing = []
        for key, label in diarias_workflow.REQUIRED_FIELDS:
            empty = not getattr(self, f"diarias_{key}_var").get().strip()
            if empty:
                missing.append(label)
            entry = self.diarias_field_entries.get(key)
            if entry is not None:
                entry.configure(style="Diarias.Invalid.TEntry" if empty else "TEntry")
            alert = self.diarias_field_alerts.get(key)
            if alert is not None:
                if empty:
                    alert.pack(side=LEFT, padx=(4, 0))
                else:
                    alert.pack_forget()
        self.diarias_validation_var.set(diarias_workflow.MISSING_FIELDS_MESSAGE if missing else "")

    def _require_diarias_fields(self):
        fields = {key: getattr(self, f"diarias_{key}_var").get() for key, _label in diarias_workflow.REQUIRED_FIELDS}
        try:
            return diarias_workflow.validate_fields(fields)
        except ValueError:
            self.diarias_fields_warned = True
            if hasattr(self, "diarias_field_entries"):
                self._update_diarias_required_fields()
            if hasattr(self, "diarias_profile_selector") and not self.diarias_profile_var.get().strip():
                self._mark_diarias_profile_missing()
            raise

    def _prepare_diarias_bundle_ui(self):
        try:
            fields = self._require_diarias_fields()
            bundle = diarias_workflow.prepare_bundle(
                fields, profile=self._required_diarias_profile(),
                valor_ufesp=self.diarias_ufesp_var.get(),
                oitiva_delegacia=self.settings.get("police_station", ""),
                meios_proprios=self.diarias_meios_proprios_var.get(),
            )
        except ValueError as exc:
            self.diarias_validation_var.set(str(exc))
            self._append_activity_log(str(exc), "activity_step_warning")
            return None
        self.diarias_validation_var.set("")
        return bundle

    def _set_diarias_busy(self, busy):
        self.diarias_busy = busy
        controls = (self.diarias_individual_buttons + self.diarias_batch_buttons + self.diarias_attachment_buttons
                    + list(self.diarias_field_entries.values())
                    + [self.diarias_meios_proprios_checkbox, self.diarias_configure_button])
        for control in controls:
            control.configure(state="disabled" if busy else "normal")
        self.diarias_profile_selector.configure(state="disabled" if busy else "readonly")

    def _new_diarias_task(self, mode, bundle, directory, temporary=None):
        task_id = uuid.uuid4().hex
        label = "Preparando diária para impressão" if mode == "print" else "Gerando PDFs da diária" if mode == "pdf" else "Gerando documentos da diária"
        key = f"diarias:lote:{task_id}"
        task = {"id": task_id, "mode": mode, "bundle": bundle, "directory": Path(directory),
                "temporary": temporary, "key": key, "started": self._start_diarias_activity(key, label),
                "cancel": threading.Event(), "files": None, "printer": "", "accepted": False,
                "printing": False, "dialog": None, "printers": [], "printer_error": "", "copies": None, "generation_done": False}
        self.diarias_task = task
        self.diarias_status_var.set(label + "…")
        self._set_diarias_busy(True)
        return task

    def _start_diarias_bundle_worker(self, task):
        events, task_id = self.diarias_job_events, task["id"]
        def worker():
            initialized = False
            try:
                import pythoncom
                pythoncom.CoInitialize()
                initialized = True
                started = {}
                def progress(event, key, label, detail):
                    if event == "start":
                        started[key] = time.perf_counter()
                    events.put((task_id, "step", event, key, label, detail,
                                max(0.0, time.perf_counter() - started.get(key, time.perf_counter()))))
                files = diarias_workflow.generate_bundle(task["directory"], task["bundle"],
                    pdf=task["mode"] != "office", progress=progress, cancel=task["cancel"])
                events.put((task_id, "generated", files))
            except diarias_workflow.DiariasCancelled:
                events.put((task_id, "cancelled"))
            except Exception as exc:
                events.put((task_id, "failed", str(exc)))
            finally:
                if initialized:
                    pythoncom.CoUninitialize()
        threading.Thread(target=worker, daemon=True, name="Diarias-geracao").start()
        if self.diarias_job_after is None:
            self.diarias_job_after = self.root.after(80, self._poll_diarias_jobs)

    def _generate_diarias_bundle(self, *, pdf):
        if self.diarias_busy:
            return
        bundle = self._prepare_diarias_bundle_ui()
        if bundle is None:
            return
        chosen = filedialog.askdirectory(parent=self.root, title="Salvar PDFs da diária" if pdf else "Salvar documentos da diária",
            initialdir=str(diarias_store.load_output_directory()), mustexist=True)
        if not chosen:
            return
        try:
            diarias_store.save_output_directory(chosen)
        except (OSError, ValueError) as exc:
            self.diarias_validation_var.set(f"Não foi possível guardar a pasta escolhida: {exc}")
            return
        task = self._new_diarias_task("pdf" if pdf else "office", bundle, chosen)
        self._start_diarias_bundle_worker(task)

    def _print_diaria(self):
        if self.diarias_busy:
            return
        bundle = self._prepare_diarias_bundle_ui()
        if bundle is None:
            return
        attachments = {kind: getattr(self, f"diarias_{kind}_path", "") for kind in ("protocolo", "escala", "holerite")}
        try:
            diarias_workflow.validate_print_attachments(attachments)
        except diarias_workflow.MissingDiariasFields as exc:
            for field in exc.fields:
                kind = field.split(":", 1)[1]
                self.diarias_attachment_alerts[kind].pack(side=LEFT, padx=(4, 0))
            self.diarias_validation_var.set(str(exc))
            self._append_activity_log(str(exc), "activity_step_warning")
            return
        for kind in attachments:
            self._clear_diarias_attachment_alert(kind)
        temporary = tempfile.TemporaryDirectory(prefix="sig_diaria_print_")
        task = self._new_diarias_task("print", bundle, temporary.name, temporary)
        task["attachments"] = attachments
        self._open_diarias_printer_dialog(task)
        self._start_diarias_bundle_worker(task)
        events, task_id = self.diarias_job_events, task["id"]
        def find_printers():
            try:
                names, default = pdf_printing.list_printers()
                events.put((task_id, "printers", names, default))
            except Exception as exc:
                events.put((task_id, "printers_error", str(exc)))
        threading.Thread(target=find_printers, daemon=True, name="Diarias-impressoras").start()

    def _open_diarias_printer_dialog(self, task):
        win = Toplevel(self.root)
        task["dialog"] = win
        win.title("Imprimir diária")
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=20)
        frame.pack(fill=BOTH, expand=True)
        ttk.Label(frame, text="Imprimir diária", font=("Segoe UI Semibold", 14)).pack(anchor="w")
        ttk.Label(frame, text="Escolha a impressora e as vias enquanto os PDFs são preparados.", style="Muted.TLabel").pack(anchor="w", pady=(4, 14))
        task["printer_var"] = StringVar(master=win)
        task["dialog_status"] = StringVar(master=win, value="Preparando PDFs e procurando impressoras…")
        ttk.Label(frame, text="Impressora").pack(anchor="w", pady=(0, 4))
        task["printer_selector"] = ttk.Combobox(frame, textvariable=task["printer_var"], width=48, state="disabled")
        task["printer_selector"].pack(fill=X)

        quantities = ttk.Frame(frame)
        quantities.pack(fill=X, pady=(16, 14))
        quantities.columnconfigure(0, weight=1)
        ttk.Label(quantities, text="Documento", style="Muted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(quantities, text="Vias", style="Muted.TLabel").grid(row=0, column=1, sticky="w", pady=(0, 4))
        task["copy_vars"], task["copy_entries"], task["copy_alerts"] = {}, {}, {}
        task["copies_warned"] = False
        task["copies_error"] = ""
        rows = [row for row in diarias_workflow.PRINT_DOCUMENTS if row[0] != "declaracao" or task["bundle"].meios_proprios]
        for index, (key, label, default) in enumerate(rows, 1):
            ttk.Label(quantities, text=label).grid(row=index, column=0, sticky="w", padx=(0, 20), pady=3)
            variable = StringVar(master=win, value=str(default))
            task["copy_vars"][key] = variable
            entry = ttk.Spinbox(quantities, from_=1, to=99, width=5, textvariable=variable)
            entry.grid(row=index, column=1, sticky="w", pady=3)
            task["copy_entries"][key] = entry
            alert = ttk.Label(quantities, image=self.diarias_alert_icon)
            alert.grid(row=index, column=2, padx=(5, 0))
            alert.grid_remove()
            create_tooltip(alert, "Informe a quantidade de vias.")
            task["copy_alerts"][key] = alert
            variable.trace_add("write", lambda *_args, current=task: self._update_diarias_print_copies(current))

        ttk.Label(frame, textvariable=task["dialog_status"], wraplength=440).pack(anchor="w", pady=(0, 14))
        actions = ttk.Frame(frame)
        actions.pack(fill=X)
        task["cancel_button"] = ttk.Button(actions, text="Cancelar", command=lambda: self._cancel_diarias_print(task))
        task["cancel_button"].pack(side=RIGHT)
        task["ok_button"] = ttk.Button(actions, text="OK", style="Diarias.Primary.TButton", state="disabled", command=lambda: self._accept_diarias_printer(task))
        task["ok_button"].pack(side=RIGHT, padx=(0, 8))
        win.protocol("WM_DELETE_WINDOW", lambda: self._cancel_diarias_print(task))
        win.bind("<Escape>", lambda _event: self._cancel_diarias_print(task))
        win.bind("<Return>", lambda _event: self._accept_diarias_printer(task))
        win.transient(self.root)
        win.update_idletasks()
        x = max(0, self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_reqwidth()) // 2)
        y = max(0, self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_reqheight()) // 2)
        win.geometry(f"+{x}+{y}")
        win.grab_set()

    def _update_diarias_print_copies(self, task):
        if not task["copies_warned"]:
            return
        for key, variable in task["copy_vars"].items():
            value = variable.get().strip()
            valid = value.isascii() and value.isdigit() and 1 <= int(value) <= 99
            task["copy_entries"][key].configure(style="TSpinbox" if valid else "Diarias.Invalid.TSpinbox")
            if valid:
                task["copy_alerts"][key].grid_remove()
            else:
                task["copy_alerts"][key].grid()
        try:
            diarias_workflow.validate_print_copies({key: var.get() for key, var in task["copy_vars"].items()}, meios_proprios=task["bundle"].meios_proprios)
        except ValueError as exc:
            task["copies_error"] = str(exc)
            task["dialog_status"].set(str(exc))
        else:
            task["copies_error"] = ""
            task["dialog_status"].set(task["printer_error"] or ("PDFs prontos. Confirme em OK." if task["files"] is not None else "Os PDFs estão sendo preparados…"))

    def _accept_diarias_printer(self, task):
        selected = task["printer_var"].get()
        if selected not in task["printers"] or task["accepted"]:
            return
        try:
            copies = diarias_workflow.validate_print_copies(
                {key: variable.get() for key, variable in task["copy_vars"].items()},
                meios_proprios=task["bundle"].meios_proprios)
        except ValueError as exc:
            task["copies_warned"] = True
            self._update_diarias_print_copies(task)
            task["dialog_status"].set(str(exc))
            return
        task["printer"], task["accepted"], task["copies"] = selected, True, copies
        task["printer_selector"].configure(state="disabled")
        for entry in task["copy_entries"].values():
            entry.configure(state="disabled")
        task["ok_button"].configure(state="disabled")
        task["cancel_button"].configure(state="disabled")
        task["dialog_status"].set("Concluindo os PDFs antes de enviar à impressora…")
        self._submit_diarias_print(task)

    def _cancel_diarias_print(self, task):
        if task["accepted"]:
            return
        task["cancel"].set()
        win = task.get("dialog")
        if win is not None and win.winfo_exists():
            win.destroy()
        task["dialog"] = None
        self.diarias_status_var.set("Cancelando a preparação da diária…")
        if task["generation_done"]:
            self._finish_diarias_task(cancelled=True)

    def _submit_diarias_print(self, task):
        if task["files"] is None or not task["accepted"] or task["printing"]:
            return
        task["printing"] = True
        label = f"Enviando diária para {task['printer']}"
        task["print_started"] = self._start_diarias_activity(task["key"] + ":print", label)
        task["dialog_status"].set(label + "…")
        self.diarias_status_var.set(label + "…")
        events, task_id = self.diarias_job_events, task["id"]
        def worker():
            try:
                plan = diarias_workflow.build_print_plan(task["files"], task["attachments"], copies=task["copies"])
                result = pdf_printing.print_plan(task["printer"], plan, job_name=f"Diária {task['bundle'].fields['abertura_data']}")
                events.put((task_id, "printed", result))
            except Exception as exc:
                events.put((task_id, "print_error", str(exc)))
        threading.Thread(target=worker, daemon=True, name="Diarias-impressao").start()

    def _finish_diarias_task(self, *, error=None, cancelled=False, message=""):
        task = self.diarias_task
        if task is None:
            return
        if cancelled:
            self._finish_diarias_activity(task["key"], task["started"], suffix="- cancelado", tag="activity_step_warning")
            self.diarias_status_var.set("Impressão cancelada. Nenhum documento foi enviado.")
        elif error:
            self._finish_diarias_activity(task["key"], task["started"], error=error)
            self.diarias_status_var.set("A diária não foi concluída. Confira o log.")
            self.diarias_validation_var.set(error)
        else:
            self._finish_diarias_activity(task["key"], task["started"], suffix=message)
            self.diarias_status_var.set(message)
        win = task.get("dialog")
        if win is not None and win.winfo_exists():
            win.destroy()
        if task.get("temporary") is not None:
            try:
                task["temporary"].cleanup()
            except OSError as exc:
                self._append_activity_log(f"Limpeza dos arquivos temporários: {exc}", "activity_step_warning")
        self.diarias_task = None
        self._set_diarias_busy(False)

    def _poll_diarias_jobs(self):
        self.diarias_job_after = None
        while True:
            try:
                message = self.diarias_job_events.get_nowait()
            except queue.Empty:
                break
            task = self.diarias_task
            if task is None or message[0] != task["id"]:
                continue
            event = message[1]
            if event == "step":
                action, key, label, detail, elapsed = message[2:]
                activity_key = task["key"] + ":" + key
                if action == "start":
                    self._begin_activity_step(activity_key, label)
                    self.diarias_status_var.set(label + "…")
                else:
                    self._finish_activity_step(activity_key, elapsed, error=detail if action == "error" else None,
                                               suffix=f"- pronto: {detail}" if action == "finish" else None)
            elif event == "generated":
                task["files"], task["generation_done"] = message[2], True
                if task["cancel"].is_set():
                    self._finish_diarias_task(cancelled=True)
                elif task["mode"] == "print":
                    task["dialog_status"].set(task.get("copies_error") or task["printer_error"] or (
                        "PDFs prontos. Confira a impressora e as vias e confirme em OK." if task["printers"]
                        else "PDFs prontos. Procurando impressoras…"))
                    self.diarias_status_var.set("PDFs prontos para impressão.")
                    self._submit_diarias_print(task)
                else:
                    self._finish_diarias_task(message=f"{len(task['files'])} documentos salvos em {task['directory']}.")
            elif event == "cancelled":
                self._finish_diarias_task(cancelled=True)
            elif event == "failed":
                self._finish_diarias_task(error=message[2])
            elif event == "printers":
                if task["cancel"].is_set():
                    continue
                names, default = message[2:]
                task["printers"] = names
                task["printer_selector"].configure(values=names, state="readonly" if names else "disabled")
                task["printer_var"].set(default if default in names else names[0] if names else "")
                task["ok_button"].configure(state="normal" if names else "disabled")
                if not names:
                    task["printer_error"] = "Nenhuma impressora instalada. Cancele e configure uma impressora no Windows."
                    task["dialog_status"].set(task.get("copies_error") or task["printer_error"])
                elif task.get("copies_error"):
                    task["dialog_status"].set(task["copies_error"])
                elif task["files"] is None:
                    task["dialog_status"].set("Escolha a impressora e confira as vias. Os PDFs estão sendo preparados…")
                else:
                    task["dialog_status"].set("PDFs prontos. Confira a impressora e as vias e confirme em OK.")
            elif event == "printers_error":
                if not task["cancel"].is_set():
                    task["printer_error"] = "Não foi possível listar as impressoras: " + message[2]
                    task["dialog_status"].set(task["printer_error"])
            elif event == "printed":
                self._finish_diarias_activity(task["key"] + ":print", task["print_started"])
                self._finish_diarias_task(message=f"{message[2]['pages']} páginas enviadas à fila de {task['printer']}.")
            elif event == "print_error":
                self._finish_diarias_activity(task["key"] + ":print", task["print_started"], error=message[2])
                self._finish_diarias_task(error=message[2])
        if self.diarias_busy:
            self.diarias_job_after = self.root.after(80, self._poll_diarias_jobs)

    def _update_diarias_month_warning(self, *_trace_args):
        """Avisa na tela quando o mês/ano do holerite difere da ida do talão."""
        try:
            holerite = datetime.strptime(self.diarias_holerite_mes_var.get().strip(), "%m/%Y")
            ida = datetime.strptime(self.diarias_abertura_data_var.get().strip(), "%d/%m/%Y")
        except ValueError:
            differs = False
        else:
            differs = (holerite.year, holerite.month) != (ida.year, ida.month)
        self.diarias_month_warning_var.set(
            "Atenção: o mês do holerite difere do mês do talão." if differs else ""
        )
        if differs:
            self.diarias_month_warning_label.grid()
        else:
            self.diarias_month_warning_label.grid_remove()

    def _refresh_diarias_profiles(self):
        """Sincroniza a seleção da tela principal com os perfis persistidos."""
        self._diarias_profiles = diarias_store.list_diarias_profiles()
        active = diarias_store.load_active_diarias_profile_id()
        selected = next((p for p in self._diarias_profiles if p["id"] == active), None)
        self.diarias_profile_selector.configure(
            values=[p["profile_name"] for p in self._diarias_profiles],
        )
        self.diarias_profile_var.set(selected["profile_name"] if selected else "")
        if selected is not None and hasattr(self, "diarias_profile_alert"):
            self.diarias_profile_alert.pack_forget()
            self.diarias_profile_selector.configure(style="TCombobox")
        panel = getattr(self, "diarias_profiles_panel", None)
        if panel is not None and panel.parent.winfo_exists():
            panel.refresh()

    def _select_diarias_profile(self, _event=None):
        selected = next(
            (p for p in self._diarias_profiles if p["profile_name"] == self.diarias_profile_var.get()),
            None,
        )
        if selected is None:
            return
        started_at = self._start_diarias_activity("diarias:perfil", "Selecionando perfil de Diárias")
        try:
            diarias_store.select_diarias_profile(selected["id"])
        except (OSError, ValueError) as exc:
            self._finish_diarias_activity("diarias:perfil", started_at, error=str(exc))
            messagebox.showerror("Diárias", str(exc), parent=self.root)
        else:
            self._finish_diarias_activity("diarias:perfil", started_at)
        self._refresh_diarias_profiles()

    def _on_diarias_profiles_changed(self):
        started_at = self._start_diarias_activity("diarias:perfil", "Atualizando perfis de Diárias")
        self._refresh_diarias_profiles()
        self._finish_diarias_activity("diarias:perfil", started_at)

    def _mark_diarias_profile_missing(self):
        if hasattr(self, "diarias_profile_alert"):
            self.diarias_profile_selector.configure(style="Diarias.Invalid.TCombobox")
            self.diarias_profile_alert.pack(before=self.diarias_configure_button, side=LEFT, padx=(4, 0))

    def _clear_diarias_attachment_alert(self, kind):
        alert = getattr(self, "diarias_attachment_alerts", {}).get(kind)
        if alert is not None:
            alert.pack_forget()

    def _required_diarias_profile(self):
        profile = diarias_store.load_diarias_profile()
        if profile is None:
            SigApp._mark_diarias_profile_missing(self)
            raise diarias_workflow.MissingDiariasFields(("profile",))
        return validate_diarias_profile(profile)

    def _start_diarias_activity(self, key: str, label: str) -> float:
        """Abre uma linha de atividade para uma ação da aba Diárias."""
        started_at = time.perf_counter()
        self._begin_activity_step(key, label)
        return started_at

    def _finish_diarias_activity(
        self,
        key: str,
        started_at: float,
        *,
        error: str | None = None,
        suffix: str | None = None,
        tag: str | None = None,
    ) -> None:
        """Fecha a linha de Diárias com duração e estado final."""
        self._finish_activity_step(
            key,
            max(0.0, time.perf_counter() - started_at),
            error=error,
            suffix=suffix,
            tag=tag,
        )

    def _generate_diarias_requerimento(self):
        """Monta o DOCX com os dados preenchidos na aba Diárias."""
        activity_key = "diarias:gerar-requerimento"
        started_at = self._start_diarias_activity(
            activity_key, "Gerando requerimento de diária"
        )
        try:
            SigApp._require_diarias_fields(self)
            template_kind, replacements = prepare_diarias_requerimento(
                data_abertura=self.diarias_abertura_data_var.get(),
                hora_abertura=self.diarias_abertura_hora_var.get(),
                data_fechamento=self.diarias_fechamento_data_var.get(),
                hora_fechamento=self.diarias_fechamento_hora_var.get(),
                total_vencimentos=self.diarias_holerite_total_var.get(),
                data_protocolo=self.diarias_data_var.get(),
                protocolo_requerimento=self.diarias_req_var.get(),
                perfil=SigApp._required_diarias_profile(self),
            )
        except ValueError as exc:
            self._finish_diarias_activity(
                activity_key,
                started_at,
                suffix=f"- dados inválidos: {exc}",
                tag="activity_step_warning",
            )
            messagebox.showwarning("Diárias", str(exc), parent=self.root)
            return

        suggested_path = next_available_diarias_requerimento_path(
            Path.home() / "Desktop",
            template_kind,
            replacements["data_ida"],
        )
        file_type_var = StringVar(master=self.root)
        destination_file = filedialog.asksaveasfilename(
            parent=self.root,
            title="Salvar requerimento de diária",
            initialdir=str(suggested_path.parent),
            initialfile=suggested_path.name,
            defaultextension=".docx",
            filetypes=[
                ("Documento do Word (*.docx)", "*.docx"),
                ("PDF (*.pdf)", "*.pdf"),
            ],
            confirmoverwrite=False,
            typevariable=file_type_var,
        )
        if not destination_file:
            self._finish_diarias_activity(
                activity_key,
                started_at,
                suffix="- cancelado",
                tag="activity_step_warning",
            )
            return
        try:
            destination = _diarias_selected_output_path(
                destination_file, file_type_var, ".docx"
            )
            if not _confirm_diarias_output_overwrite(self.root, destination):
                self._finish_diarias_activity(
                    activity_key,
                    started_at,
                    suffix="- cancelado",
                    tag="activity_step_warning",
                )
                return
            if destination.suffix.casefold() == ".pdf":
                generate_diarias_requerimento_pdf(
                    template_kind, destination, replacements
                )
            else:
                generate_diarias_requerimento(
                    template_kind, destination, replacements
                )
        except Exception as exc:
            self._finish_diarias_activity(
                activity_key, started_at, error=str(exc)
            )
            messagebox.showerror(
                "Diárias",
                f"Não foi possível gerar o requerimento: {exc}",
                parent=self.root,
            )
            return

        self._finish_diarias_activity(
            activity_key,
            started_at,
            suffix=f"- salvo: {destination.name}",
        )
        tipo = "meia diária" if template_kind == "meia" else "diária inteira"
        messagebox.showinfo(
            "Diárias",
            f"Requerimento de {tipo} salvo em:\n{destination}",
            parent=self.root,
        )

    def _generate_diarias_mapa(self):
        """Gera o mapa de diária em Excel com os dados extraídos na aba."""
        activity_key = "diarias:gerar-mapa"
        started_at = self._start_diarias_activity(
            activity_key, "Gerando mapa de diária"
        )
        try:
            SigApp._require_diarias_fields(self)
            values = diarias_mapa.prepare_diarias_mapa(
                total_vencimentos=self.diarias_holerite_total_var.get(),
                valor_ufesp=self.diarias_ufesp_var.get(),
                data_ida=self.diarias_abertura_data_var.get(),
                horario_ida=self.diarias_abertura_hora_var.get(),
                data_volta=self.diarias_fechamento_data_var.get(),
                horario_volta=self.diarias_fechamento_hora_var.get(),
                data_protocolo=self.diarias_data_var.get(),
                protocolo_requerimento=self.diarias_req_var.get(),
                protocolo_mapa=self.diarias_mapa_var.get(),
                meios_proprios=self.diarias_meios_proprios_var.get(),
                profile=SigApp._required_diarias_profile(self),
                oitiva_delegacia=self.settings.get("police_station", ""),
            )
        except ValueError as exc:
            self._finish_diarias_activity(
                activity_key,
                started_at,
                suffix=f"- dados inválidos: {exc}",
                tag="activity_step_warning",
            )
            messagebox.showwarning("Diárias", str(exc), parent=self.root)
            return

        suggested_path = diarias_mapa.next_available_diarias_mapa_path(
            Path.home() / "Desktop", values.data_ida
        )
        file_type_var = StringVar(master=self.root)
        destination_file = filedialog.asksaveasfilename(
            parent=self.root,
            title="Salvar mapa de diária",
            initialdir=str(suggested_path.parent),
            initialfile=suggested_path.name,
            defaultextension=".xlsx",
            filetypes=[
                ("Pasta de trabalho do Excel (*.xlsx)", "*.xlsx"),
                ("PDF (*.pdf)", "*.pdf"),
            ],
            confirmoverwrite=False,
            typevariable=file_type_var,
        )
        if not destination_file:
            self._finish_diarias_activity(
                activity_key,
                started_at,
                suffix="- cancelado",
                tag="activity_step_warning",
            )
            return

        try:
            destination = _diarias_selected_output_path(
                destination_file, file_type_var, ".xlsx"
            )
            if not _confirm_diarias_output_overwrite(self.root, destination):
                self._finish_diarias_activity(
                    activity_key,
                    started_at,
                    suffix="- cancelado",
                    tag="activity_step_warning",
                )
                return
            diarias_mapa.generate_diarias_mapa(destination, values)
        except Exception as exc:
            self._finish_diarias_activity(
                activity_key, started_at, error=str(exc)
            )
            messagebox.showerror(
                "Diárias",
                f"Não foi possível gerar o mapa: {exc}",
                parent=self.root,
            )
            return

        self._finish_diarias_activity(
            activity_key,
            started_at,
            suffix=f"- salvo: {destination.name}",
        )
        messagebox.showinfo(
            "Diárias",
            f"Mapa salvo em:\n{destination}",
            parent=self.root,
        )

    def _generate_diarias_meios_proprios(self):
        """Gera a declaração de meios próprios com as datas do talão e do protocolo."""
        activity_key = "diarias:gerar-meios-proprios"
        started_at = self._start_diarias_activity(
            activity_key, "Gerando declaração de meios próprios"
        )
        data_ida = self.diarias_abertura_data_var.get()
        try:
            SigApp._require_diarias_fields(self)
            replacements = prepare_declaracao_meios_proprios(
                data_ida=data_ida,
                data_protocolo=self.diarias_data_var.get(),
                perfil=SigApp._required_diarias_profile(self),
            )
        except ValueError as exc:
            self._finish_diarias_activity(
                activity_key,
                started_at,
                suffix=f"- dados inválidos: {exc}",
                tag="activity_step_warning",
            )
            messagebox.showwarning("Diárias", str(exc), parent=self.root)
            return

        suggested_path = next_available_diarias_declaracao_path(
            Path.home() / "Desktop", data_ida
        )
        file_type_var = StringVar(master=self.root)
        destination_file = filedialog.asksaveasfilename(
            parent=self.root,
            title="Salvar declaração de meios próprios",
            initialdir=str(suggested_path.parent),
            initialfile=suggested_path.name,
            defaultextension=".docx",
            filetypes=[
                ("Documento do Word (*.docx)", "*.docx"),
                ("PDF (*.pdf)", "*.pdf"),
            ],
            confirmoverwrite=False,
            typevariable=file_type_var,
        )
        if not destination_file:
            self._finish_diarias_activity(
                activity_key,
                started_at,
                suffix="- cancelado",
                tag="activity_step_warning",
            )
            return
        try:
            destination = _diarias_selected_output_path(
                destination_file, file_type_var, ".docx"
            )
            if not _confirm_diarias_output_overwrite(self.root, destination):
                self._finish_diarias_activity(
                    activity_key,
                    started_at,
                    suffix="- cancelado",
                    tag="activity_step_warning",
                )
                return
            if destination.suffix.casefold() == ".pdf":
                generate_declaracao_meios_proprios_pdf(destination, replacements)
            else:
                generate_declaracao_meios_proprios(destination, replacements)
        except Exception as exc:
            self._finish_diarias_activity(
                activity_key, started_at, error=str(exc)
            )
            messagebox.showerror(
                "Diárias",
                f"Não foi possível gerar a declaração de meios próprios: {exc}",
                parent=self.root,
            )
            return

        self._finish_diarias_activity(
            activity_key,
            started_at,
            suffix=f"- salvo: {destination.name}",
        )
        messagebox.showinfo(
            "Diárias",
            f"Declaração de meios próprios salva em:\n{destination}",
            parent=self.root,
        )

    def _select_diarias_pdf(self, kind):
        """Abre o seletor de PDF e ja preenche os campos na hora."""
        titulos = {
            "holerite": "Selecionar o PDF do holerite",
            "protocolo": "Selecionar o PDF do protocolo",
            "talao": "Selecionar o PDF do talão",
            "escala": "Selecionar o PDF da escala",
        }
        selecionado = filedialog.askopenfilename(
            parent=self.root,
            title=titulos[kind],
            filetypes=(
                ("Arquivos PDF", "*.pdf"),
                ("Todos os arquivos", "*.*"),
            ),
        )
        if not selecionado:
            return
        if kind == "escala":
            key = "diarias:escala:anexar"
            started = self._start_diarias_activity(key, "Anexando escala")
            path = Path(selecionado)
            if path.suffix.casefold() != ".pdf" or not path.is_file():
                self._finish_diarias_activity(key, started, error="Selecione um arquivo PDF existente.")
                self.diarias_validation_var.set("A escala precisa ser um arquivo PDF.")
                return
            self.diarias_escala_path = str(path)
            self.diarias_escala_file_var.set(path.name)
            SigApp._clear_diarias_attachment_alert(self, kind)
            self._finish_diarias_activity(key, started, suffix=f"- anexado: {path.name}")
            return
        if kind == "holerite":
            self._attach_diarias_holerite_pdf(selecionado)
            return
        elif kind == "talao":
            self.diarias_talao_path = selecionado
            self.diarias_talao_file_var.set(Path(selecionado).name)
        else:
            self.diarias_protocolo_path = selecionado
            self.diarias_protocolo_file_var.set(Path(selecionado).name)
        SigApp._clear_diarias_attachment_alert(self, kind)
        self._reload_diarias_pdf(kind)

    def _attach_diarias_holerite_pdf(self, source_path):
        """Extrai e guarda uma cópia do holerite antes de torná-lo o anexo ativo."""
        activity_key = "diarias:holerite:anexar"
        started_at = self._start_diarias_activity(
            activity_key, "Lendo e anexando holerite"
        )
        try:
            total, mes = diarias_protocolo.extract_holerite_pdf(source_path)
            if not total or not mes:
                faltando = []
                if not total:
                    faltando.append("o total de vencimentos")
                if not mes:
                    faltando.append("o mês do holerite")
                self._finish_diarias_activity(
                    activity_key,
                    started_at,
                    suffix="- dados não encontrados: " + ", ".join(faltando),
                    tag="activity_step_warning",
                )
                messagebox.showwarning(
                    "Diárias",
                    "Não encontrei "
                    + " e ".join(faltando)
                    + " no PDF. O anexo e os dados salvos anteriormente foram mantidos; "
                    "confira o arquivo ou preencha os campos manualmente.",
                    parent=self.root,
                )
                return
            stored_path, display_name = diarias_store.attach_holerite_pdf(
                source_path, total, mes
            )
        except Exception as exc:
            self._finish_diarias_activity(
                activity_key, started_at, error=str(exc)
            )
            messagebox.showerror(
                "Diárias",
                f"Não foi possível ler ou guardar o holerite localmente: {exc}",
                parent=self.root,
            )
            return

        self.diarias_holerite_path = stored_path
        SigApp._clear_diarias_attachment_alert(self, "holerite")
        self.diarias_holerite_file_var.set(display_name)
        self.diarias_holerite_total_var.set(total)
        self.diarias_holerite_mes_var.set(mes)
        self._finish_diarias_activity(
            activity_key,
            started_at,
            suffix=f"- anexado: {display_name}",
        )

    def _reload_diarias_pdf(self, kind):
        """Reextrai do PDF e preenche os campos imediatamente."""
        titles = {
            "holerite": "holerite",
            "talao": "talão",
            "protocolo": "protocolo",
        }
        activity_key = f"diarias:{kind}:reextrair"
        label = f"Lendo dados do {titles.get(kind, kind)}"
        started_at = self._start_diarias_activity(activity_key, label)
        if kind == "holerite":
            caminho = self.diarias_holerite_path
        elif kind == "talao":
            caminho = self.diarias_talao_path
        else:
            caminho = self.diarias_protocolo_path
        if not caminho:
            self._finish_diarias_activity(
                activity_key,
                started_at,
                suffix="- PDF não selecionado",
                tag="activity_step_warning",
            )
            messagebox.showwarning(
                "Diárias",
                "Selecione primeiro o PDF.",
                parent=self.root,
            )
            return
        try:
            if kind == "holerite":
                total, mes = diarias_protocolo.extract_holerite_pdf(caminho)
                if not total or not mes:
                    faltando = []
                    if not total:
                        faltando.append("o total de vencimentos")
                    if not mes:
                        faltando.append("o mês do holerite")
                    self._finish_diarias_activity(
                        activity_key,
                        started_at,
                        suffix="- dados não encontrados: " + ", ".join(faltando),
                        tag="activity_step_warning",
                    )
                    messagebox.showwarning(
                        "Diárias",
                        "Não encontrei "
                        + " e ".join(faltando)
                        + " no PDF. Os dados salvos anteriormente foram mantidos; "
                        "confira o arquivo ou preencha os campos manualmente.",
                        parent=self.root,
                    )
                    return
                self.diarias_holerite_total_var.set(total)
                self.diarias_holerite_mes_var.set(mes)
                valores = (
                    ("o total de vencimentos", total),
                    ("o mês do holerite", mes),
                )
            elif kind == "talao":
                data_abertura, hora_abertura, data_fechamento, hora_fechamento = (
                    diarias_protocolo.extract_talao_pdf(caminho)
                )
                self.diarias_abertura_data_var.set(data_abertura)
                self.diarias_abertura_hora_var.set(hora_abertura)
                self.diarias_fechamento_data_var.set(data_fechamento)
                self.diarias_fechamento_hora_var.set(hora_fechamento)
                valores = (
                    ("a data de abertura", data_abertura),
                    ("o horário de abertura", hora_abertura),
                    ("a data de fechamento", data_fechamento),
                    ("o horário de fechamento", hora_fechamento),
                )
            else:
                mapa, requerimento, data = diarias_protocolo.extract_protocolo_completo(
                    caminho
                )
                self.diarias_req_var.set(requerimento)
                self.diarias_mapa_var.set(mapa)
                self.diarias_data_var.set(data)
                valores = (
                    ("o requerimento", requerimento),
                    ("o mapa", mapa),
                    ("a data do protocolo", data),
                )
        except Exception as exc:
            self._finish_diarias_activity(
                activity_key, started_at, error=str(exc)
            )
            messagebox.showerror(
                "Diárias",
                f"Não foi possível ler o PDF: {exc}",
                parent=self.root,
            )
            return
        faltando = [rotulo for rotulo, valor in valores if not valor]
        if faltando:
            self._finish_diarias_activity(
                activity_key,
                started_at,
                suffix="- dados não encontrados: " + ", ".join(faltando),
                tag="activity_step_warning",
            )
            messagebox.showwarning(
                "Diárias",
                "Não encontrei "
                + " e ".join(faltando)
                + " no PDF; confira o arquivo ou digite manualmente.",
                parent=self.root,
            )
            return
        self._finish_diarias_activity(activity_key, started_at)

    def _save_diarias_holerite_data(self, *_trace_args):
        """Persiste imediatamente os dois campos compartilhados no mês."""
        try:
            diarias_store.save_holerite(
                self.diarias_holerite_total_var.get(),
                self.diarias_holerite_mes_var.get(),
            )
        except Exception as exc:
            if not self.diarias_holerite_save_error_shown:
                self.diarias_holerite_save_error_shown = True
                messagebox.showerror(
                    "Di\u00e1rias",
                    f"Não foi possível salvar os dados do holerite localmente: {exc}",
                    parent=self.root,
                )
        else:
            self.diarias_holerite_save_error_shown = False

    def _migrate_saved_diarias_holerite_month(self):
        """Atualiza meses antigos lendo o holerite que já está salvo no perfil."""
        if re.fullmatch(
            r"(?:0[1-9]|1[0-2])/\d{4}",
            self.diarias_holerite_mes_var.get().strip(),
        ):
            return
        if not self.diarias_holerite_path:
            return
        try:
            _total, mes_ano = diarias_protocolo.extract_holerite_pdf(
                self.diarias_holerite_path
            )
        except Exception:
            return
        if re.fullmatch(r"(?:0[1-9]|1[0-2])/\d{4}", mes_ano):
            self.diarias_holerite_mes_var.set(mes_ano)

    def _save_diarias_ufesp_data(self, *_trace_args):
        """Persiste imediatamente o valor UFESP da aba Diárias."""
        try:
            diarias_store.save_ufesp(self.diarias_ufesp_var.get())
        except Exception as exc:
            if not self.diarias_ufesp_save_error_shown:
                self.diarias_ufesp_save_error_shown = True
                profile_panel = getattr(self, "diarias_profiles_panel", None)
                warning_parent = self.root
                if profile_panel is not None and profile_panel.parent.winfo_exists():
                    warning_parent = profile_panel.parent.winfo_toplevel()
                messagebox.showerror(
                    "Diárias",
                    f"Não foi possível salvar o valor UFESP localmente: {exc}",
                    parent=warning_parent,
                )
        else:
            self.diarias_ufesp_save_error_shown = False

    def _save_diarias_ufesp_index_data(self, *_trace_args):
        """Persiste imediatamente o índice UFESP da aba Diárias."""
        try:
            diarias_store.save_ufesp_index(self.diarias_ufesp_index_var.get())
        except Exception as exc:
            if not self.diarias_ufesp_index_save_error_shown:
                self.diarias_ufesp_index_save_error_shown = True
                messagebox.showerror(
                    "Diárias",
                    f"Não foi possível salvar o índice UFESP localmente: {exc}",
                    parent=self.root,
                )
        else:
            self.diarias_ufesp_index_save_error_shown = False

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
        if len(digits) != 14 and hasattr(self, "imei_full_var"):
            self.imei_full_var.set("—")
            self.imei_copy_button.configure(state="disabled")
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
        if hasattr(self, "imei_full_var"):
            self.imei_full_var.set(full_imei)
            self.imei_copy_button.configure(state="normal")
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
            text = "Nenhuma consulta registrada."
            self.imei_toggle_var.set("")
            self.imei_toggle_button.configure(state="disabled")
            self.imei_toggle_button.pack_forget()
        else:
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
                    self.imei_toggle_button.pack(side=LEFT, padx=(0, 8), before=self.imei_clear_history_button)
                self.imei_toggle_button.configure(state="normal")
            else:
                self.imei_toggle_var.set("")
                self.imei_toggle_button.pack_forget()
        self.imei_clear_history_button.configure(state="normal" if records else "disabled")
        self.imei_history_text.configure(state="normal")
        self.imei_history_text.delete("1.0", END)
        if text:
            self.imei_history_text.insert("1.0", text, () if records else ("empty",))
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
            # A varinha mágica é CENTRADA na própria faixa da oitiva, na MESMA
            # linha (y) e altura dos botões Colar/Copiar/Limpar. Ela não
            # disputa espaço com o botão "Oitiva", que vive na faixa de cima
            # (ao lado do "Histórico") e é posicionado por outro método.
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
        # A varinha se alinha ao "Oitiva", então só pode ser posicionada DEPOIS
        # que o "Oitiva" tem o seu `x` definitivo: o `place` e assíncrono e o
        # `winfo_x()` só vale depois do `update_idletasks`. Rodar aqui (e não
        # dentro do loop) cobre as duas colunas de uma vez.
        self._position_live_statement_actions()
        self._position_live_document_controls()
        self._position_live_document_preview()

    def _position_live_statement_actions(self):
        """Posiciona a varinha à DIREITA do "Recuperar" em TODAS as 3 faixas.

        Pedido do usuário (29/09): a varinha fica ao lado do "Recuperar" —
        transcrição, histórico e oitiva, as três caixas. Antes ela era
        centralizada na coluna do "Oitiva"/"Histórico" (ficava 54 px fora de
        linha, porque a faixa de ícones é mais larga que a do "Oitiva") e,
        numa tentativa anterior, dentro da caixa de texto (empurrava a caixa
        para a direita).

        A posição é COPIADA do "Recuperar" pelo mesmo motivo do `place` antigo:
        o `x` do `place` é o CENTRO do widget, enquanto `winfo_x()` é a BORDA
        esquerda, então usar `winfo_x()` errava meia largura. E o `place` do
        "Recuperar" é assíncrono — sem `update_idletasks` a posição lida ainda
        é a anterior (foi como o botão saiu 668 px → 11 px → 36 px de erro em
        três tentativas às cegas).
        """
        # (faixa, varinha, recuperar) das três caixas, coluna 1 e coluna 2.
        trincas = (
            (
                "live_transcript_actions",
                "live_transcript_wand_button",
                "live_recover_button",
            ),
            (
                "live_transcript_actions_2",
                "live_transcript_wand_button_2",
                "live_recover_button_2",
            ),
            (
                "live_statement_actions",
                "live_statement_adjust_button",
                "live_statement_recover_button",
            ),
            (
                "live_statement_actions_2",
                "live_statement_adjust_button_2",
                "live_statement_recover_button_2",
            ),
            (
                "live_history_actions",
                "live_history_wand_button",
                "live_history_recover_button",
            ),
            (
                "live_history_actions_2",
                "live_history_wand_button_2",
                "live_history_recover_button_2",
            ),
        )
        for faixa_nome, wand_nome, recover_nome in trincas:
            faixa = getattr(self, faixa_nome, None)
            wand = getattr(self, wand_nome, None)
            recover = getattr(self, recover_nome, None)
            if not (faixa and wand and recover):
                continue
            if not (faixa.winfo_exists() and wand.winfo_exists() and recover.winfo_exists()):
                continue
            faixa.update_idletasks()
            recover.update_idletasks()
            lado = self._live_icon_button_side(faixa, wand)
            # ITEM 2 do pedido (29/09): o "Recuperar" passa a ter as MESMAS
            # dimensões da varinha. Antes media 23x21 contra 24x24 da varinha.
            # A altura também é fixada por `place`, porque o `ttk::button` não
            # aceita `-height`; e o `place` do "Recuperar" é refeito aqui (ele
            # era `place(x=0, y=0, anchor="nw")`, no canto da faixa).
            self._size_recover_button(recover, lado)
            recover.update_idletasks()
            recover.place_forget()
            recover.place(x=0, y=faixa.winfo_height() / 2, width=lado, height=lado, anchor="w")
            recover.update_idletasks()
            # POSIÇÃO do "Recuperar": o `place` usa `anchor="w"`, então o `x`
            # é a BORDA ESQUERDA (0) e `place_info()["x"]` devolve esse 0 — não
            # o centro. Somar `largura/2` a ele dava 12 px de folga em vez de
            # 24. A referência correta é a posição JÁ MEDIDA do widget
            # (`winfo_x`, relativo à faixa, que é a mesma origem do `place`).
            # Deriva-se a borda direita e só então se aplica a folga.
            lado_recuperar = max(1, recover.winfo_width())
            borda_direita = recover.winfo_x() + lado_recuperar
            # DISTÂNCIA entre a BORDA DIREITA do "Recuperar" e a BORDA ESQUERDA
            # da varinha (pedido do usuário, 29/09: 24 px). Antes colavam
            # (folga de 1 px) e os dois botões pareciam um só.
            x = borda_direita + LIVE_WAND_RECOVER_GAP + (lado / 2)
            y = faixa.winfo_height() / 2
            wand.update_idletasks()
            wand.place_forget()
            wand.place(x=x, y=y, width=lado, height=lado, anchor="center")

    @staticmethod
    def _live_icon_button_side(actions, adjust_button) -> int:
        """Lado (px) do quadrado: a altura medida de um botão de ícone vizinho.

        A busca ignora a própria varinha e o rótulo de progresso, e cai no
        `EDITOR_ICON_BUTTON_SIZE` quando nenhum botão de ícone está realizado
        (coluna recolhida, por exemplo).
        """
        melhor = 0
        for child in actions.winfo_children():
            if child is adjust_button or child.winfo_class() != "TButton":
                continue
            if child.winfo_manager() != "pack":
                continue  # só os ícones da direita servem de referência
            altura = child.winfo_height()
            if altura > melhor:
                melhor = altura
        return melhor if melhor > 0 else EDITOR_ICON_BUTTON_SIZE

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
        history_request = self._prompt_user_ativo("historico_user", material)
        try:
            history_started = time.monotonic()
            try:
                history = client.post(
                    model_config,
                    self._prompt_ativo("historico_system", DEFAULT_HISTORY_SYSTEM_PROMPT),
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
        history_request = self._prompt_user_ativo("historico_user", material)
        try:
            started = time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_map = {
                    executor.submit(
                        client.post,
                        model,
                        self._prompt_ativo("historico_system", DEFAULT_HISTORY_SYSTEM_PROMPT),
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
                self._prompt_ativo("oitiva_system", DEFAULT_STATEMENT_TEMPLATE),
                self._prompt_oitiva_user_ativo(selected_name, material),
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
                        self._prompt_ativo("oitiva_system", DEFAULT_STATEMENT_TEMPLATE),
                        self._prompt_oitiva_user_ativo(selected_name, material),
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

    def _draw_transcription_action(self, canvas, kind: str, *, enabled: bool = True) -> None:
        width = canvas.winfo_width() if canvas.winfo_width() > 1 else canvas.winfo_reqwidth()
        height = canvas.winfo_height() if canvas.winfo_height() > 1 else canvas.winfo_reqheight()
        photo = self._tool_icon_photo(kind, min(width, height), enabled=enabled, circular=True)
        canvas.action_icon_photo = photo
        canvas.delete("all")
        canvas.create_image(width / 2, height / 2, image=photo)
        canvas.configure(cursor="hand2" if enabled else "arrow")

    def _draw_action_button(self):
        self._draw_transcription_action(self.action_canvas, "cancel" if self.running else "execute")

    def _draw_save_button(self):
        enabled = bool(self.last_html_path and self.last_html_path.exists())
        self._draw_transcription_action(self.save_canvas, "save", enabled=enabled)

    def _draw_folder_button(self):
        self.folder_canvas.delete("all")
        if getattr(self, "folder_button_visible", False):
            self._draw_transcription_action(self.folder_canvas, "folder")

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

    def _live_icon_photo(self, kind: str) -> "ImageTk.PhotoImage":
        """PhotoImage do ícone PNG, criado uma única vez por tipo."""
        photo = self._live_icon_photos.get(kind)
        if photo is None:
            photo = ImageTk.PhotoImage(live_icon_image(kind), master=self.root)
            self._live_icon_photos[kind] = photo
        return photo

    def _draw_canvas_icon(self, canvas, kind: str):
        """Desenha o ícone PNG centralizado no canvas do botão (44x44)."""
        canvas.delete("all")
        largura = canvas.winfo_reqwidth() or LIVE_ICON_SIZE
        altura = canvas.winfo_reqheight() or LIVE_ICON_SIZE
        canvas.create_image(largura / 2, altura / 2, image=self._live_icon_photo(kind))

    def _draw_live_mic_button(self):
        canvas = self.live_mic_canvas
        state = self.live_state
        if state == "finalizing":
            canvas.delete("all")
            canvas.create_oval(4, 4, 40, 40, fill="#d6dddd", outline="#879191", width=2)
            canvas.create_arc(16, 14, 28, 30, start=20, extent=300, outline="#5d6868", width=3, style="arc")
            return
        if state in ("listening", "paused"):
            canvas.delete("all")
            canvas.create_oval(4, 4, 40, 40, fill="#13201e", outline="#2c403d", width=2)
            canvas.create_line(15, 21, 20, 27, fill="#3ddc66", width=5, capstyle="round")
            canvas.create_line(20, 27, 30, 15, fill="#3ddc66", width=5, capstyle="round")
            return
        self._draw_canvas_icon(canvas, "mic_vermelho")

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
        normal_active = self.normal_recording
        if self.live_state not in ("listening", "paused") and not normal_active:
            canvas.delete("all")
            return
        is_paused = self.live_state == "paused" or (normal_active and self.normal_record_paused)
        if not is_paused:
            self._draw_canvas_icon(canvas, "mic_pause")
            return
        # Retomar: o mesmo círculo amarelo do ícone, com um triângulo preto (a
        # cor do símbolo dentro do PNG) — as duas faces do botão combinam.
        canvas.delete("all")
        canvas.create_oval(4, 4, 40, 40, fill=LIVE_PAUSE_CIRCLE_COLOR, outline="", width=0)
        canvas.create_polygon(17, 13, 17, 31, 31, 22, fill=LIVE_ICON_GLYPH_COLOR, outline="")

    def _draw_normal_live_mic_button(self):
        canvas = self.live_normal_mic_canvas
        if self.normal_recording:
            canvas.delete("all")
            canvas.create_oval(4, 4, 40, 40, fill="#3d1515", outline="#5a2424", width=2)
            canvas.create_line(15, 21, 20, 27, fill="#3ddc66", width=5, capstyle="round")
            canvas.create_line(20, 27, 30, 15, fill="#3ddc66", width=5, capstyle="round")
            return
        self._draw_canvas_icon(canvas, "mic_branco")

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
        # A varinha mágica NÃO é criada aqui: ela vive na FAIXA de botões de
        # cima, à direita do "Recuperar" (pedido do usuário, 29/09). Antes ela
        # ficava dentro da caixa de texto, o que EMPURRAVA a caixa para a
        # direita e estragava o layout — a caixa precisa ocupar a largura toda.
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

    def adjust_live_statement_text(self, kind: str):
        """Ajusta o texto da caixa em uma linha só (varinha mágica).

        Remove as quebras de linha e garante um único espaço depois de cada
        ponto e vírgula. Não reescreve, não resume e não inventa texto: só
        junta o que o modelo devolveu, que é o que o Termo de Declarações
        exige (um parágrafo corrido).

        O botão existe na transcrição, no histórico e na oitiva (pedido de
        29/09) — a função é a mesma, o que muda é o rótulo da mensagem.
        """
        if self.live_state != "idle" or self.assistant_busy:
            return
        atual = self._live_editor_value(kind)
        if not atual:
            return
        ajustado, mudou = ajustar_texto_oitiva(atual)
        rotulo = self._live_editor_label(kind)
        if not mudou:
            self._set_activity_status(
                f"A {rotulo} já está em uma linha (ajuste desnecessário).",
                log=False,
            )
            return
        self._set_live_editor(kind, ajustado)
        self._set_activity_status(f"{rotulo.capitalize()} ajustada em uma linha só.", log=False)

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
                self._prompt_ativo("qualificacao_system", DEFAULT_QUALIFICATION_SYSTEM_PROMPT),
                self._prompt_qualificacao_ativo(list(LIVE_QUALIFICATION_FIELD_IDS), raw_text),
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
            # Dentro do container da linha, empacotar sem `before` ACRESCENTA no
            # fim — e este frame é o membro mais à direita do grupo, então a
            # ordem original (intervalo, timestamps, idioma/keywords) é mantida.
            self.live_grok_controls.pack(side=LEFT)
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
        self._refresh_live_local_server_controls()
        interval_state = "disabled" if self.live_state != "idle" else "readonly"
        for widget in (self.live_interval_entry, self.live_interval_minus, self.live_interval_plus):
            widget.configure(state=interval_state)

    def _refresh_live_local_server_controls(self):
        """Visibilidade dos controles que só existem no servidor STT LOCAL.

        Regra do usuário (11/09): o controle "- t = +" (TEMPO — intervalo em
        segundos entre as fatias REST) e o "Timestamps" só aparecem quando o
        modelo de transcrição selecionado é o SERVIDOR LOCAL (Granite NAR):

        - Granite NAR: o grupo do intervalo aparece; "Timestamps" e todo o
          bloco Diarização/Idioma/Keywords (omitido em `_refresh_live_grok_controls`,
          que é quem decide a diarização) ficam ocultos;
        - qualquer provedor de API: o grupo do intervalo é OMITIDO e o
          "Timestamps" volta.

        Em ambos os casos o container da linha reflui sozinho, então o que
        sobra fica encostado à esquerda. Os controles dos MICROFONES ficam
        depois do `live_top_spacer` (que expande) e NUNCA se movem.
        """
        server = selected_transcription_server(self.settings)
        local = is_local_granite_transcription_server(server.get("name"))
        # 1) esconde o que não vale para o modelo escolhido (antes de mostrar o
        #    resto, para a ordem final não depender da ordem das chamadas);
        # 2) mostra o que vale. No container, `pack` sem `before` acrescenta no
        #    FIM: o "Timestamps" tem de voltar ANTES do bloco Diarização/Idioma/
        #    Keywords quando ele estiver visível (o `before` só é usado com um
        #    irmão EMPACOTADO — apontar para um oculto levanta TclError).
        if local:
            self.live_timestamps_var.set(False)
            self.live_timestamps_check.pack_forget()
            self.live_interval_controls.pack(side=LEFT)
            return
        self.live_interval_controls.pack_forget()
        if self.live_grok_controls.winfo_manager():
            self.live_timestamps_check.pack(
                side=LEFT, padx=(0, 10), before=self.live_grok_controls
            )
        else:
            self.live_timestamps_check.pack(side=LEFT, padx=(0, 10))

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
                muse_body = metamuse_rest_request_body(
                    bool(record_settings.get("diarize")), record_settings
                )
                self._queue(
                    "params_block",
                    "Parâmetros REST (Muse):",
                    muse_body,
                    format_raw_request(
                        "POST",
                        META_MUSE_STT_URL,
                        [
                            ("accept", "application/json"),
                            (
                                "Content-Type",
                                f"multipart/form-data; boundary={RAW_REQUEST_BOUNDARY}",
                            ),
                            ("Authorization", "Bearer ***"),
                        ],
                        format_raw_multipart(
                            RAW_REQUEST_BOUNDARY,
                            [
                                (
                                    "request",
                                    json.dumps(muse_body, ensure_ascii=False),
                                    "application/json",
                                )
                            ],
                            [("audio", wav_path.name, "audio/wav", _audio_file_size(wav_path))],
                        ),
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
                vocabulary_id = self._alibaba_vocabulary_for(self.settings, ALIBABA_REST_MODEL)
                rest_body = alibaba_rest_body(
                    "data:audio/wav;base64,"
                    + format_raw_audio_label(_audio_file_size(wav_path)),
                    self.settings,
                    vocabulary_id,
                )
                self._queue(
                    "params_block",
                    "Parâmetros REST (Alibaba):",
                    alibaba_rest_log_params(self.settings),
                    format_raw_request(
                        "POST",
                        ALIBABA_REST_URL,
                        [
                            ("accept", "application/json"),
                            ("Content-Type", "application/json"),
                            ("Authorization", "Bearer ***"),
                            ("X-DashScope-SSE", "disable"),
                        ],
                        json.dumps(rest_body, ensure_ascii=False),
                    ),
                )
                text = alibaba_rest_transcribe(
                    cancel,
                    self.settings.copy(),
                    wav_path,
                    wav_path.with_suffix(".raw"),
                    vocabulary_id,
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
                audio_size = _audio_file_size(wav_path)
                if getattr(self, "normal_record_deepgram", False):
                    self._queue(
                        "params_block",
                        "Parâmetros REST (Deepgram):",
                        urllib.parse.parse_qsl(
                            deepgram_query_string(record_settings), keep_blank_values=True
                        ),
                        format_raw_request(
                            "POST",
                            url,
                            [
                                ("accept", "application/json"),
                                ("Authorization", "Token ***"),
                                ("Content-Type", "audio/wav"),
                            ],
                            format_raw_audio_label(audio_size),
                        ),
                    )
                elif is_assemblyai_transcription(self.settings):
                    assemblyai_fields = transcription_form_fields(record_settings)
                    self._queue(
                        "params_block",
                        "Parâmetros REST (AssemblyAI):",
                        assemblyai_fields,
                        format_raw_request(
                            "POST",
                            url,
                            [
                                ("accept", "application/json"),
                                (
                                    "Content-Type",
                                    f"multipart/form-data; boundary={RAW_REQUEST_BOUNDARY}",
                                ),
                                ("Authorization", "***"),
                                ("X-AAI-Model", "u3-sync-pro"),
                            ],
                            format_raw_multipart(
                                RAW_REQUEST_BOUNDARY,
                                list(assemblyai_fields.items()),
                                [("audio", wav_path.name, "audio/wav", audio_size)],
                            ),
                        ),
                    )
                elif is_elevenlabs_transcription(self.settings):
                    rest_fields = {"model_id": "scribe_v2"}
                    rest_fields.update(transcription_form_fields(record_settings))
                    self._queue(
                        "params_block",
                        "Parâmetros REST (ElevenLabs):",
                        rest_fields,
                        format_raw_request(
                            "POST",
                            url,
                            [
                                ("accept", "application/json"),
                                (
                                    "Content-Type",
                                    f"multipart/form-data; boundary={RAW_REQUEST_BOUNDARY}",
                                ),
                                ("xi-api-key", "***"),
                            ],
                            format_raw_multipart(
                                RAW_REQUEST_BOUNDARY,
                                list(rest_fields.items()),
                                [("file", wav_path.name, "audio/wav", audio_size)],
                            ),
                        ),
                    )
            else:
                fields = {"language": self.normal_record_language, "format": "true", "filler_words": "false"}
                if self.normal_record_diarize:
                    fields["diarize"] = "true"
                url = GROK_STT_URL if grok else transcribe_url(self.settings)
                file_field = "file" if grok else "files"
                raw_headers = [
                    ("accept", "application/json"),
                    (
                        "Content-Type",
                        f"multipart/form-data; boundary={RAW_REQUEST_BOUNDARY}",
                    ),
                ]
                if grok:
                    raw_headers.append(("Authorization", "Bearer ***"))
                if grok:
                    self._queue(
                        "params_block",
                        "Parâmetros REST (Grok):",
                        dict(fields),
                        format_raw_request(
                            "POST",
                            url,
                            raw_headers,
                            format_raw_multipart(
                                RAW_REQUEST_BOUNDARY,
                                list(fields.items()),
                                [(file_field, wav_path.name, "audio/wav", _audio_file_size(wav_path))],
                            ),
                        ),
                    )
                else:
                    # Granite NAR: o servidor não usa query — os campos vão no
                    # multipart. O copiado vira a mesma leitura de uma linha.
                    self._queue(
                        "params_block",
                        "Parâmetros REST (servidor):",
                        dict(fields),
                        format_raw_request_line("POST", url, fields),
                    )
                uploader = GraniteUploader(
                    cancel,
                    fields,
                    {"Authorization": f"Bearer {self.settings['grok_api_key']}"} if grok else {},
                    file_field,
                )
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

    def _transcription_batch_settings(
        self, model_names: list[str], one_model_at_a_time: bool = False
    ) -> dict:
        """Cópia de settings do lote com o idioma traduzido por modelo.

        O seletor guarda uma opção única, mas cada provedor recebe o SEU valor
        (ex.: pt -> "pt-BR" no Deepgram e "pt" nos demais); o servidor local
        (Granite NAR) não recebe idioma nenhum. O settings.json e as
        preferências da aba Ocorrência não são tocados.

        O `transcription_server` da cópia passa a ser o PRIMEIRO modelo marcado:
        ele é compartilhado com a aba Ocorrência (e pode estar num modelo só de
        WebSocket), então sem isto o lote de um único modelo usaria o modelo
        da Ocorrência em vez do que está selecionado na Transcrição.

        `one_model_at_a_time` (checkbox "Um modelo por vez") entra como flag do
        LOTE (`_one_model_at_a_time`): com ela, o multi-modelo manda a fila
        inteira para um modelo e só depois passa para o próximo. Não vai para o
        settings.json.
        """
        batch = self.settings.copy()
        batch["_multi_transcription"] = bool(model_names)
        batch["_multi_transcription_models"] = list(model_names)
        batch["_one_model_at_a_time"] = bool(one_model_at_a_time)
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


    def open_settings(self, *, police_subtab=None):
        if getattr(self, "diarias_busy", False):
            return
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

        settings_tab_names = ("Modelos", "Policial", "Chaves API", "Prompts", "Avançado")
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

        # Tamanho da janela: o `resizable(False, False)` já está aplicado quando a
        # janela é mapeada pela PRIMEIRA vez — e isso acontece no MEIO da
        # construção (a medição do botão de olho chama `win.update_idletasks` com
        # o conteúdo ainda parcial, ~1 linha por aba). Num PC onde o gerenciador
        # de janelas não aceitou o crescimento posterior, as Configurações
        # ficaram presas nesse tamanho mínimo (relatado em 13/09 num i5-8400, sem
        # nenhum erro no log). Fixar a geometria no tamanho da aba ATIVA depois
        # de montar torna o resultado determinístico em qualquer máquina.
        janela_montada = {"pronta": False}

        def ajustar_janela_ao_conteudo() -> None:
            """Reaplica o tamanho NATURAL da janela (o do conteúdo da aba ativa).

            `geometry("")` devolve o dimensionamento ao pedido do Tk: a janela
            reassume o tamanho do conteúdo (em vez de ficar presa no tamanho do
            primeiro mapeamento) e o layout interno continua com as larguras
            naturais dos campos — fixar `WxH` explicitamente encolhia os campos
            de chave (medido: 462px -> 356px).
            """
            win.update_idletasks()
            win.geometry("")

        def select_settings_tab(name: str):
            for page in settings_tab_pages.values():
                page.pack_forget()
            settings_tab_pages[name].pack(fill=BOTH, expand=True)
            for tab_name, button in settings_tab_buttons.items():
                button.configure(
                    background=settings_active_bg if tab_name == name else settings_inactive_bg,
                    foreground=settings_active_fg if tab_name == name else settings_inactive_fg,
                )
            if janela_montada["pronta"]:
                ajustar_janela_ao_conteudo()

        for name, button in settings_tab_buttons.items():
            button.bind("<Button-1>", lambda _event, selected=name: select_settings_tab(selected))

        models_tab = settings_tab_pages["Modelos"]
        police_tab = settings_tab_pages["Policial"]
        api_tab = settings_tab_pages["Chaves API"]
        prompts_tab = settings_tab_pages["Prompts"]
        advanced_tab = settings_tab_pages["Avançado"]
        select_settings_tab("Modelos")

        conv_var = IntVar(value=self.settings["convert_parallel"])
        req_var = IntVar(value=self.settings["transcribe_parallel"])
        vad_var = IntVar(value=self.settings["vad_parallel"])
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
        # Aba Avançado: Paralelismo e, logo abaixo, a seção de Keywords (o
        # conteúdo que antes ficava numa tela separada atrás do botão KEYWORDS).
        parallel_frame = ttk.LabelFrame(
            advanced_tab,
            text="Paralelismo",
            padding=(12, 8),
            style="Settings.TLabelframe",
        )
        parallel_frame.pack(fill=X, anchor="n")
        # Coluna do rótulo estreita: o slider começa logo depois do texto, sem o
        # vão grande que existia quando a coluna reservava 170px.
        parallel_frame.columnconfigure(0, minsize=0)
        parallel_frame.columnconfigure(1, weight=1)
        columns = [model_sections, [parallel_frame]]
        (
            transcription_frame,
            history_frame,
            statement_frame,
            qualification_frame,
            extraction_frame,
        ) = model_sections

        police_subtab_bar = ttk.Frame(police_tab, style="Settings.Inner.TFrame")
        police_subtab_bar.pack(fill=X, pady=(0, 8))
        police_subtab_content = ttk.Frame(police_tab, style="Settings.Inner.TFrame")
        police_subtab_content.pack(fill=BOTH, expand=True)
        police_subtab_pages = {}
        police_subtab_buttons = {}
        for name in ("Oitiva", "Diárias"):
            police_subtab_pages[name] = ttk.Frame(police_subtab_content, style="Settings.Inner.TFrame")
            button = tk.Label(
                police_subtab_bar, text=name, width=12, height=1, borderwidth=1,
                relief="solid", font=settings_tab_font, cursor="hand2",
            )
            button.pack(side=LEFT, padx=(0 if not police_subtab_buttons else 4, 0))
            police_subtab_buttons[name] = button

        def select_police_subtab(name):
            for page in police_subtab_pages.values():
                page.pack_forget()
            police_subtab_pages[name].pack(fill=BOTH, expand=True)
            for label, button in police_subtab_buttons.items():
                button.configure(
                    background=settings_active_bg if label == name else settings_inactive_bg,
                    foreground=settings_active_fg if label == name else settings_inactive_fg,
                )
            if janela_montada["pronta"]:
                ajustar_janela_ao_conteudo()

        for name, button in police_subtab_buttons.items():
            button.bind("<Button-1>", lambda _event, label=name: select_police_subtab(label))
        select_police_subtab("Oitiva")
        self.diarias_profiles_panel = DiariasProfilesPanel(
            police_subtab_pages["Diárias"], ufesp_var=self.diarias_ufesp_var,
            on_change=self._on_diarias_profiles_changed,
            on_resize=lambda: ajustar_janela_ao_conteudo() if janela_montada["pronta"] else None,
        )
        # Expostos no diálogo para navegação e verificações da interface.
        win.police_subtab_pages = police_subtab_pages
        win.police_subtab_buttons = police_subtab_buttons
        win.diarias_profiles_panel = self.diarias_profiles_panel

        police_frame = ttk.LabelFrame(
            police_subtab_pages["Oitiva"],
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
            # Coluna do rótulo estreita (era 190px): é o que faz os campos
            # começarem mais à esquerda. O Tk nunca renderiza a coluna menor que
            # o rótulo mais largo dela, então nenhum rótulo é cortado.
            section.columnconfigure(0, minsize=API_KEY_LABEL_COLUMN_WIDTH)
            section.columnconfigure(1, weight=1)
            return section

        api_import_frame = ttk.Frame(api_tab, style="Settings.Inner.TFrame")
        api_import_frame.pack(anchor="e", pady=(0, 8))
        # Uma única seção para TODAS as chaves de modelo: transcrição e texto
        # juntas, na ordem pedida pelo usuário (Deepseek, xAI, Meta, ElevenLabs,
        # Deepgram, AssemblyAI, Alibaba). Labels exatas, sem alterações.
        api_models_frame = make_api_section(api_tab, "Modelos")
        api_imei_frame = make_api_section(api_tab, "IMEI CHECK")

        # Campos de chave da aba inteira (Modelos + IMEI CHECK): o botão de olho
        # mostra/esconde todos de uma vez.
        api_key_entries: list[ttk.Entry] = []

        def add_api_field(section, row: int, label: str, variable: StringVar, help_text: str = ""):
            ttk.Label(section, text=label).grid(
                row=row, column=0, sticky="w", pady=5, padx=(0, 12)
            )
            entry = ttk.Entry(
                section,
                textvariable=variable,
                show="*",
                width=API_KEY_ENTRY_WIDTH_CHARS,
            )
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            if help_text:
                create_tooltip(entry, help_text)
            api_key_entries.append(entry)
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
        add_api_field(api_imei_frame, 0, "IMEI Check", imei_api_key_var)

        # Botão de olho da aba (fica no topo, ao lado do IMPORTAR): revela as
        # chaves dos campos e, já reveladas, vira o olho cortado com a função de
        # esconder. A criação do botão em si fica logo depois do IMPORTAR, porque
        # a altura dele é a referência.
        api_keys_visible = False

        def build_api_key_icons(tamanho: int):
            return (
                self._make_api_key_visibility_icon(crossed=False, size=tamanho),
                self._make_api_key_visibility_icon(crossed=True, size=tamanho),
            )

        reveal_icon, hide_icon = build_api_key_icons(API_KEY_VISIBILITY_ICON_SIZE)

        def toggle_api_key_visibility():
            nonlocal api_keys_visible
            api_keys_visible = not api_keys_visible
            # `show=""` desliga a máscara do ttk.Entry (nunca `show=None`).
            for entry in api_key_entries:
                entry.configure(show="" if api_keys_visible else "*")
            eye_button.configure(image=hide_icon if api_keys_visible else reveal_icon)

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

        import_button = ttk.Button(
            api_import_frame,
            text="IMPORTAR",
            command=import_api_keys,
        )
        import_button.pack(side=RIGHT)

        # Botão do olho à ESQUERDA do IMPORTAR, com um respiro entre os dois e com
        # a MESMA ALTURA do botão de texto (pedido do usuário).
        eye_button = ttk.Button(
            api_import_frame,
            image=reveal_icon,
            width=3,
            command=toggle_api_key_visibility,
        )
        eye_button.pack(side=RIGHT, padx=(0, API_KEY_EYE_GAP))
        # O ícone é o único componente deste botão, então a diferença de altura
        # para o IMPORTAR se corrige encolhendo o desenho. É medido na hora (e não
        # fixado) porque o padding do tema `clam` muda com o DPI da tela.
        win.update_idletasks()
        sobra = eye_button.winfo_reqheight() - import_button.winfo_reqheight()
        if sobra > 0:
            ajustado = max(API_KEY_VISIBILITY_ICON_MIN_SIZE, API_KEY_VISIBILITY_ICON_SIZE - sobra)
            reveal_icon, hide_icon = build_api_key_icons(ajustado)
            eye_button.configure(image=hide_icon if api_keys_visible else reveal_icon)
        # O Tk não segura o PhotoImage sozinho: o atributo no botão mantém as
        # duas imagens vivas enquanto a janela existir (o toggle também as usa).
        eye_button.api_key_visibility_icons = (reveal_icon, hide_icon)
        create_tooltip(eye_button, "Mostrar ou esconder as chaves API.")

        # NÚCLEOS físicos (não threads): num Xeon 18c/36t o `os.cpu_count()`
        # devolve 36 e a escala 1..n sairia 1..36 — o usuário define a escala
        # pelos núcleos (18).
        cpu_count = max(1, physical_cpu_count())
        # Valor padrão das duas slidebars: metade dos núcleos da CPU (n/2),
        # com arredondamento inteligente para números ímpares.
        default_parallel = default_parallelism(cpu_count)

        def parallel_scale(
            row: int,
            label: str,
            variable: IntVar,
            valores: list[int],
            help_text: str,
        ):
            # Slider de NÓS (mesmo visual do TurboCore): um nó por opção, então o
            # valor salvo é encaixado no nó mais próximo.
            maximum = valores[-1]
            if not (1 <= variable.get() <= maximum):
                variable.set(nearest_value(default_parallel, valores))
            else:
                variable.set(nearest_value(variable.get(), valores))
            ttk.Label(parallel_frame, text=label).grid(
                row=row, column=0, sticky="w", pady=5, padx=(0, 8)
            )
            value_label = ttk.Label(parallel_frame, text=str(variable.get()), width=4)
            value_label.grid(row=row, column=2, sticky="w", pady=5, padx=(8, 0))

            def on_scale(value: str):
                try:
                    selected = int(round(float(str(value).replace(",", "."))))
                except (TypeError, ValueError):
                    selected = variable.get()
                selected = nearest_value(selected, valores)
                variable.set(selected)
                value_label.configure(text=str(selected))

            scale = NodeSlider(
                parallel_frame,
                values=valores,
                # Um nó a cada ~12px para os círculos não se encostarem. O teto
                # de 288px é MEDIDO: até ele a aba Avançado fica com 482px de
                # largura, igual à aba Modelos — quem dita o tamanho da janela
                # (518) é a maior aba, então o slider não pode passar disso ou a
                # janela cresceria ao clicar em Avançado (regressão de 10/09).
                length=max(170, min(288, 12 * len(valores))),
                command=on_scale,
            )
            scale.set(variable.get())
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

        # Conversões: as opções da máquina são 1, 2, 3, ..., n, 3n/2, 2n, 5n/2,
        # 3n, 7n/2, 4n (n + 6 opções) — ver `parallel_values`.
        conv_valores = parallel_values(cpu_count)
        conv_max = conv_valores[-1]
        conv_help = (
            "Recomendado: metade dos núcleos da CPU (n/2).\n\n"
            f"{describe_parallel_values(conv_valores, cpu_count)}\n\n"
            "Cada conversão FFmpeg usa bastante CPU e leitura/escrita de disco. "
            "Paralelismo alto demais disputa recursos com o resto do sistema "
            "(e com a transcrição, quando roda em sequência), podendo até "
            "diminuir a velocidade total em vez de aumentar. "
            "Metade dos núcleos mantém a máquina responsiva e a conversão eficiente."
        )
        parallel_scale(0, "Conversões", conv_var, conv_valores, conv_help)

        # Requisições: passo de 2 em 2, até 16 (regra do usuário de 31/08 — o
        # gargalo é a rede, não a CPU; a regra nova das opções vale só para as
        # Conversões até o usuário pedir o contrário).
        req_max = 16
        req_step = workable_step(2, req_max)
        req_valores = step_values(req_step, req_max)
        req_help = (
            "Recomendado: metade dos núcleos da CPU (n/2).\n\n"
            f"{describe_step_values(req_valores, req_step)}\n\n"
            "Cada requisição de transcrição envia áudio e espera a resposta "
            "do servidor — o gargalo é a rede e o servidor, não a CPU local. "
            "Paralelismo alto demais satura a conexão e pode causar timeouts "
            "ou respostas instáveis. Metade dos núcleos dá o melhor equilíbrio "
            "entre velocidade e estabilidade."
        )
        parallel_scale(1, "Requisições", req_var, req_valores, req_help)

        # VAD: TODOS os inteiros de 1 até n núcleos físicos (regra do usuário,
        # 13/09) — o VAD roda em processos separados e cada um usa UM núcleo,
        # então o valor é literalmente quantos núcleos o VAD ocupa.
        vad_valores = vad_parallel_options(cpu_count)
        vad_help = (
            "Recomendado: metade dos núcleos da CPU (n/2).\n\n"
            f"{len(vad_valores)} opções: 1, 2, 3, ..., {vad_valores[-1]} "
            f"(n = {cpu_count} núcleos físicos desta máquina).\n\n"
            "O VAD (Silero/WebRTC) é o único estágio que não paraleliza sozinho: "
            "ele roda em processos separados e cada processo usa UM núcleo — este "
            "número é quantos núcleos o VAD ocupa. Com 1, a fila é processada "
            "arquivo por arquivo (como sempre foi). Os arquivos são divididos "
            "entre os processos pelo tamanho, então o tempo total é o do ramo "
            "mais pesado; acima de metade dos núcleos o ganho costuma achatar "
            "(o disco passa a ser o gargalo)."
        )
        parallel_scale(2, "VAD", vad_var, vad_valores, vad_help)

        # ── Aba Prompts (entre Chaves API e Avançado) ────────────────────
        # O usuario escolhe, edita e baixa os prompts de histórico,
        # oitiva e qualificação. A regra vive em `prompt_store.py`; o painel é
        # só a interface. `_reload_prompts` recarrega as constantes do app para
        # que a escolha valha na próxima requisição, sem reiniciar o SIG.
        prompts_frame = ttk.Frame(
            prompts_tab,
            padding=(12, 8),
            style="Settings.Inner.TFrame",
        )
        prompts_frame.pack(fill=BOTH, expand=True, anchor="n")
        prompts_panel = PromptsPanel(
            prompts_frame,
            self.prompt_store,
            reload_consumer=self._reload_prompts,
            log_consumer=self._append_activity_log,
        )

        # PERFIS: o usuário mantém várias listas nomeadas e escolhe a ativa nos
        # seletores "Keywords" das telas de Transcrição e Ocorrência. Cada
        # modelo continua montando o próprio parâmetro na requisição.
        keywords_page = ttk.LabelFrame(
            advanced_tab,
            text="Keywords",
            padding=(12, 8),
            style="Settings.TLabelframe",
        )
        keywords_page.pack(fill=X, anchor="n", pady=(8, 0))
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

        # Botões dos perfis ACIMA do seletor (o usuário pediu nesta ordem:
        # primeiro as ações, depois o seletor de qual perfil está em edição).
        keywords_profiles_bar = ttk.Frame(keywords_page, style="Settings.Inner.TFrame")
        keywords_profiles_bar.pack(fill=X, pady=(0, 8))

        keywords_profile_row = ttk.Frame(keywords_page, style="Settings.Inner.TFrame")
        keywords_profile_row.pack(fill=X, pady=(0, 8))
        ttk.Label(keywords_profile_row, text="Perfil:", style="Settings.TLabel").pack(side=LEFT)
        keywords_profile_combo = ttk.Combobox(
            keywords_profile_row,
            textvariable=keywords_profile_var,
            state="readonly",
            width=24,
        )
        keywords_profile_combo.pack(side=LEFT, padx=(6, 0))
        # "?" no fim da linha: limites reais por modelo e aviso de falso
        # positivo (mesmo marcador discreto usado no VAD).
        self._make_help_marker(
            keywords_profile_row, lambda: self._open_keywords_help(win)
        ).pack(side=LEFT, padx=(10, 0))

        keywords_entry_row = ttk.Frame(keywords_page, style="Settings.Inner.TFrame")
        keywords_entry_row.pack(fill=X, pady=(0, 10))
        keyword_entry_var = StringVar()
        keyword_entry = ttk.Entry(keywords_entry_row, textvariable=keyword_entry_var, width=40)
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
        # Largura da coluna escolhida para a janela de Configurações voltar ao
        # tamanho inicial com a aba Avançado ativa (a tabela é a parte principal
        # desta seção e é ela que define a largura mínima).
        keywords_tree.column("palavra", width=392, anchor="w")
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
            keywords_profiles_bar,
            text="+ Perfil",
            command=new_profile,
        ).pack(side=LEFT)
        ttk.Button(
            keywords_profiles_bar,
            text="Renomear",
            command=rename_profile,
        ).pack(side=LEFT, padx=(6, 0))
        ttk.Button(
            keywords_profiles_bar,
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
                "Selecione um item e clique em \u2212 para excluir.\n"
                "O perfil em edição é o escolhido em \"Perfil\".\n"
                "Clique em Salvar para manter."
            ),
            style="Muted.TLabel",
            justify="left",
        ).pack(side=LEFT, padx=(12, 0))
        ttk.Label(
            keywords_page,
            textvariable=keywords_hint_var,
            style="Muted.TLabel",
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))
        refresh_profile_combo()

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
                # Rótulo vem de providers.text_model_label (fonte única): os
                # servidores locais aparecem como "servidor (gemma4)" e
                # "servidor (qwen2.5)", sem repetir o `model` entre parênteses.
                model_labels_holder.update({
                    text_model_label(model): model["name"]
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
            if self.diarias_profiles_panel.editing:
                select_settings_tab("Policial")
                select_police_subtab("Diárias")
                if not self.diarias_profiles_panel.save_profile():
                    return
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
                    "vad_parallel": vad_var.get(),
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
            prompts_frame,
            keywords_page,
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
        # Conteúdo completo: agora sim o tamanho da janela é fixado no conteúdo
        # da aba ativa (ver `ajustar_janela_ao_conteudo`).
        janela_montada["pronta"] = True
        if police_subtab in police_subtab_pages:
            select_settings_tab("Policial")
            select_police_subtab(police_subtab)
        ajustar_janela_ao_conteudo()
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
            self._queue(
                "params_block",
                "Parâmetros Alibaba",
                alibaba_ws_log_params(self.settings),
                format_raw_websocket_frame(
                    json.dumps(
                        alibaba_ws_run_task(task_id, self.settings, alibaba_vocabulary_id),
                        ensure_ascii=False,
                    )
                ),
            )
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
                format_raw_websocket_frame(
                    json.dumps(
                        metamuse_handshake_payload("***", self.live_grok_diarize, self.settings),
                        ensure_ascii=False,
                    )
                ),
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
                    # _finish_elevenlabs_session e uma funcao ANINHADA deste
                    # escopo (nao um metodo de SigApp): chamar via self. dava
                    # AttributeError e o texto final do Scribe se perdia no
                    # fechamento intencional.
                    _finish_elevenlabs_session()
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
                _finish_elevenlabs_session()
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
                format_raw_request_line("GET", f"{ELEVENLABS_WEBSOCKET_URL}?{query}"),
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
                format_raw_request_line("GET", f"{ASSEMBLYAI_WEBSOCKET_URL}?{query}"),
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
                format_raw_request_line("GET", f"{DEEPGRAM_STT_WEBSOCKET_URL}?{query}"),
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
                format_raw_request_line("GET", f"{GROK_STT_WEBSOCKET_URL}?{query}"),
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
        workflow_settings = self._transcription_batch_settings(
            multi_model_names, one_model_at_a_time=self.files_one_model_var.get()
        )
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
        # Cada execução tem o seu próprio conjunto de linhas vivas (erros por
        # tipo, arquivos já prontos): as antigas ficam no log como histórico.
        self._run_sequence = int(getattr(self, "_run_sequence", 0)) + 1
        self._batch_error_entries = {}
        self._error_line_raw = {}
        self._prep_counts = {}
        # Resumo do envio (bloco final do log): zerado a cada execução — o do
        # pipeline é medido no fim, e o das demais execuções no começo do envio.
        self._batch_totals = None
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
        # Total da fila: a linha "N/M arquivos já estavam prontos" usa este M.
        self._batch_job_total = len(jobs)
        self._queue("activity_step_finish", "prepare", time.perf_counter() - getattr(self, "_prepare_started", time.perf_counter()))

        try:
            zip_stats = None
            # Estado do poller do servidor Granite NAR (linha viva + resumo final).
            progresso_servidor: dict | None = None
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
                # No pipeline a transcrição começa JUNTO com a conversão: o
                # marcador do envio sai antes das linhas vivas do lote (os
                # números do resumo são medidos no fim, quando a conversão já
                # terminou).
                self._queue("activity", "Iniciando envio:", "vad_total")
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
                # "Iniciando envio:" marca o começo do envio; o bloco de resumo
                # fecha o log no fim (pedido do usuário, 16/09).
                self._begin_batch_send(jobs)
                progresso_servidor = self._start_server_progress(settings, self._batch_totals[0])
                try:
                    if send_zip:
                        zip_stats = self._run_zip_transcription(jobs, settings, temp_dir, raw_dir, zip_level)
                    else:
                        self._run_transcriptions(jobs, settings)
                finally:
                    self._finish_server_progress(progresso_servidor)
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
                self._begin_batch_send(jobs)
                progresso_servidor = self._start_server_progress(settings, self._batch_totals[0])
                try:
                    if send_zip:
                        zip_stats = self._run_zip_transcription(jobs, settings, temp_dir, raw_dir, zip_level)
                    else:
                        self._run_transcriptions(jobs, settings)
                finally:
                    self._finish_server_progress(progresso_servidor)
            if self.cancel_event.is_set():
                raise Cancelled()
            html_path = temp_dir / "transcricoes.html"
            stats = self._batch_report_stats(jobs, mode, settings, process_started, send_zip, zip_level, zip_stats)
            write_html_report(jobs, html_path, stats)
            self._queue("html_ready", str(html_path))
            # Bloco final (separador + estatísticas + separador) ANTES do
            # "Concluído" (pedido do usuário, 16/09).
            self._report_batch_summary(
                jobs,
                elapsed=time.perf_counter() - getattr(self, "_prepare_started", process_started),
                server=(progresso_servidor or {}).get("resumo"),
            )
            # Sem o caminho no log (pedido do usuário, 27/09): a pasta já é a
            # do temp e polui a leitura da linha final. O `html_ready` acima
            # continua guardando o caminho para o botão "Salvar HTML".
            self._queue("status", "Concluído. HTML gerado.")
            self._queue("progress", 100)
            self._show_folder_button(visible=True)
        except Cancelled:
            for job in jobs:
                if not job.transcription and not job.error:
                    # NÃO marca job.error: o relatório parcial sai só com o que já
                    # foi transcrito — o que nem começou não é "problema".
                    if job.txt_path:
                        job.txt_path.write_text("Cancelado pelo usuário.", encoding="utf-8")
                    self._queue("job", job.original_path, "Cancelado")
            self._queue("status", "Cancelado.")
            self._offer_partial_report(jobs, mode, settings, process_started, send_zip, zip_level, temp_dir)
        except Exception as exc:
            self._queue("status", f"Erro: {exc}")
        finally:
            self._queue("done")

    def _offer_partial_report(
        self,
        jobs: list[AudioJob],
        mode: str,
        settings: dict,
        process_started: float,
        send_zip: bool,
        zip_level: str,
        temp_dir: Path,
    ) -> None:
        """Oferece o relatório parcial do que já foi transcrito (regra do usuário, 13/09).

        O aviso é mostrado pela UI (o worker só espera a resposta); o HTML sai no
        MESMO caminho e formato do relatório normal, só com o material existente:
        os arquivos que nem começaram a ser transcritos não entram.
        """
        if getattr(self, "_app_closing", False):
            return
        model_count = 1
        if settings.get("_multi_transcription"):
            model_count = max(1, len(settings.get("_multi_transcription_models") or []) or 1)
        parciais = jobs_with_material(jobs, model_count)
        if not parciais:
            # Nada transcrito ainda: não há o que oferecer.
            return
        decisao: list[bool] = [False]
        pronto = threading.Event()
        self._queue("partial_report_offer", decisao, pronto)
        if not pronto.wait(timeout=PARTIAL_REPORT_WAIT_SECONDS):
            return
        if not decisao[0]:
            return
        html_path = temp_dir / "transcricoes.html"
        try:
            stats = self._batch_report_stats(
                parciais, mode, settings, process_started, send_zip, zip_level, None
            )
            write_html_report(parciais, html_path, stats)
        except Exception as exc:
            self._queue("status", f"Falha ao gerar o relatório parcial: {exc}")
            return
        self._queue("html_ready", str(html_path))
        self._queue("status", f"Relatório parcial gerado em {html_path}")
        self._show_folder_button(visible=True)

    def _batch_send_totals(
        self, jobs: list[AudioJob], *, probe=None
    ) -> tuple[int, float, int, int, int]:
        """(arquivos, segundos de áudio, bytes, sem duração, sem tamanho) do ENVIO.

        Só entram os arquivos que vão para a transcrição
        (`transcription_candidates`) e o tamanho é o do arquivo JÁ CONVERTIDO
        (`upload_path`, que já é a saída do VAD quando ele roda) — nunca o do
        original (pedido do usuário, 13/09). Duração pelo cabeçalho do WAV no
        caminho normal; o resto vai para a sonda externa em paralelo.
        """
        candidatos = transcription_candidates(jobs)
        segundos = 0.0
        total_bytes = 0
        sem_duracao = 0
        sem_tamanho = 0
        pendentes: list[AudioJob] = []
        medido_por_job: dict[int, float] = {}
        for job in candidatos:
            caminho = job.upload_path
            if caminho is None:
                sem_duracao += 1
                sem_tamanho += 1
                continue
            try:
                total_bytes += caminho.stat().st_size
            except OSError:
                sem_tamanho += 1
            duracao = wav_duration_seconds(caminho)
            if duracao is None:
                pendentes.append(job)
            else:
                segundos += duracao
                medido_por_job[id(job)] = duracao
        if pendentes:
            medidos = (probe or self._probe_durations)(pendentes)
            for job in pendentes:
                duracao = medidos.get(id(job))
                if duracao:
                    segundos += duracao
                    medido_por_job[id(job)] = float(duracao)
                else:
                    sem_duracao += 1
        # Áudio ANTES do VAD (pedido do usuário, 27/09). O total medido acima já
        # é o PÓS-VAD — com VAD ligado, `upload_path` passa a apontar para o WAV
        # filtrado (ver `accept_result`) — então o que o VAD removeu é
        # reconstituído a partir da duração original que o worker reportou.
        # Entra só o arquivo em que o VAD valeu de fato (o `upload_path` é a
        # saída do VAD): arquivo com erro/filtro vazio continua indo completo
        # e não pode ser contado como reduzido.
        removido_vad = 0.0
        for job in candidatos:
            if job.vad_output_path is None or job.upload_path != job.vad_output_path:
                continue
            duracao = medido_por_job.get(id(job))
            if duracao is not None and job.vad_total_duration > duracao:
                removido_vad += job.vad_total_duration - duracao
        self._batch_audio_before_vad = segundos + removido_vad if removido_vad > 0 else None
        return len(candidatos), segundos, total_bytes, sem_duracao, sem_tamanho

    def _probe_durations(self, jobs: list[AudioJob]) -> dict[int, float]:
        """Duração dos arquivos que NÃO são WAV (ffprobe/ffmpeg em paralelo).

        Sonda externa é CARA (~83 ms por arquivo com ffprobe, medido nesta
        máquina): roda com poucos workers e sempre na thread do worker — nunca na
        thread da UI. Sem ffprobe/ffmpeg no pacote, devolve nada (a linha de
        áudio sai em amarelo com a contagem de não medidos).
        """
        resultados: dict[int, float] = {}
        ffprobe = app_base_dir() / "ffprobe.exe"
        ffmpeg = app_base_dir() / "ffmpeg.exe"
        if not (ffprobe.exists() or ffmpeg.exists()):
            return resultados
        caminhos = {id(job): job.upload_path for job in jobs if job.upload_path is not None}
        if not caminhos:
            return resultados
        workers = min(8, max(2, (os.cpu_count() or 4) // 2))
        with cancellable_executor(workers) as executor:
            futuros = {
                executor.submit(
                    audio_duration_seconds, caminho, ffprobe=ffprobe, ffmpeg=ffmpeg
                ): chave
                for chave, caminho in caminhos.items()
            }
            for future in iter_completed(futuros, cancel_event=self.cancel_event):
                chave = futuros[future]
                try:
                    segundos = future.result()
                except Cancelled:
                    raise
                except Exception:
                    segundos = None
                if segundos:
                    resultados[chave] = float(segundos)
        return resultados

    def _begin_batch_send(self, jobs: list[AudioJob]) -> None:
        """Marca o INÍCIO do envio e mede o resumo que fecha o log no fim (16/09).

        O bloco de resumo (Total de arquivos / Total áudio / Tamanho total /
        Eficiência) passou a ser emitido DEPOIS da transcrição, entre
        separadores (pedido do usuário, 16/09) — aqui fica só o marcador
        "Iniciando envio:". Os números continuam sendo medidos aqui (arquivos JÁ
        convertidos, duração pelo cabeçalho do WAV) para a sonda de duração não
        atrasar o fecho do log no fim.
        """
        self._batch_totals = self._batch_send_totals(jobs)
        # Os MESMOS números do bloco final saem AQUI, antes do marcador: o
        # usuário vê o que vai ser enviado (quantos arquivos válidos, quanto de
        # áudio, quantos bytes) enquanto o envio só está começando — antes eles
        # só apareciam no fecho do log, com o lote já inteiro (27/09).
        self._queue_batch_totals_lines(self._batch_totals)
        self._queue("activity", "Iniciando envio:", "vad_total")

    def _queue_batch_totals_lines(
        self, totais: tuple[int, float, int, int, int], *, fechar: bool = True
    ) -> None:
        """As linhas de totais do envio, entre separadores (27/09).

            ==========
            Total de arquivos: 4004
            Total áudio: 9h18m02s
            Tamanho total: 1022.2 MB
            ==========

        `totais` vem de `_batch_send_totals`: só os arquivos VÁLIDOS (com erro
        de conversão ficam de fora), com a duração de cada áudio válido e o
        tamanho do que será ENVIADO (o WAV/OGG convertido, nunca o original).

        Mesma função nos dois lugares onde os totais aparecem (antes do envio e
        no fecho do log): o bloco final e estas linhas não podem divergir de
        formato — daí virarem uma função só. O separador de ABERTURA sai sempre
        daqui; o de FECHAMENTO é do chamador (`fechar`) porque no bloco final
        as eficiências vêm logo depois de "Tamanho total" e o separador delas
        só pode vir no fim (senão o bloco final, que já existia, mudava).

        Com o VAD ligado, o total de áudio medido já é o do WAV FILTRADO: a
        linha passa a mostrar o antes -> depois para deixar isso explícito
        (`Total áudio: 12m15s (VAD -> 10m40s)`). Sem VAD, nada muda.
        """
        total, segundos, tamanho, sem_duracao, sem_tamanho = totais
        self._queue("activity", BATCH_SUMMARY_SEPARATOR, None)
        self._queue("activity", f"Total de arquivos: {total}", "vad_total")
        antes_vad = getattr(self, "_batch_audio_before_vad", None)
        if antes_vad is not None and antes_vad > segundos:
            # O total do VAD é o do WAV FILTRADO: o número antes da seta é o
            # áudio que ENTROU no lote e o depois é o que vai ser transcrito.
            texto_audio = (
                f"Total áudio: {format_audio_total(antes_vad)} "
                f"(VAD -> {format_audio_total(segundos)})"
            )
        else:
            texto_audio = f"Total áudio: {format_audio_total(segundos)}"
        if sem_duracao:
            self._queue(
                "activity",
                f"{texto_audio} ({sem_duracao} arquivo(s) sem duração medível)",
                "warning",
            )
        else:
            self._queue("activity", texto_audio, "vad_total")
        texto_tamanho = f"Tamanho total: {format_total_size(tamanho)}"
        if sem_tamanho:
            self._queue(
                "activity",
                f"{texto_tamanho} ({sem_tamanho} arquivo(s) sem leitura)",
                "warning",
            )
        else:
            self._queue("activity", texto_tamanho, "vad_total")
        if fechar:
            self._queue("activity", BATCH_SUMMARY_SEPARATOR, None)

    def _report_batch_summary(
        self,
        jobs: list[AudioJob],
        *,
        elapsed: float,
        server: tuple[float, float] | None = None,
    ) -> None:
        """Bloco final do lote, entre separadores (pedido do usuário, 16/09).

            ==========
            Total de arquivos: 1
            Total áudio: 46m19s
            Tamanho total: 84.8 MB
            Eficiência geral: 30.2x (1min 32s)
            Eficiência do servidor: 46.2x (1min 0s)
            Eficiência da GPU: 46.6x (59.7s)
            ==========

        As três eficiências (segundos de áudio ÷ período):
        - geral    → tempo decorrido do clique no botão até o HTML pronto;
        - servidor → a sessão do servidor inteira (recebimento + processamento);
        - GPU      → só o processamento/inferência.
        As duas últimas só aparecem quando o modelo é o servidor Granite NAR e
        ele reportou os tempos reais (`GET /sessions`).
        """
        totais = getattr(self, "_batch_totals", None)
        if totais is None:
            # Pipeline (conversão e transcrição juntas) ou fallback: mede agora.
            totais = self._batch_send_totals(jobs)
        _total, segundos, _tamanho, _sem_duracao, _sem_tamanho = totais
        # As linhas de totais saem pela MESMA função do início do envio: um
        # formato só para os mesmos números, mesmo aparecendo duas vezes. Sem o
        # `fechar` porque aqui as eficiências vêm logo depois de "Tamanho
        # total" — o separador que fecha o bloco FINAL sai no fim, abaixo.
        self._queue_batch_totals_lines(totais, fechar=False)
        eficiencia = (segundos / elapsed) if (elapsed and elapsed > 0) else 0.0
        self._queue(
            "activity", format_efficiency_line("Eficiência geral", eficiencia, elapsed), "vad_total"
        )
        if server:
            audio_servidor, proc_servidor, sessao_servidor = (
                tuple(server) + (0.0, 0.0, 0.0)
            )[:3]
            if audio_servidor > 0 and sessao_servidor > 0:
                self._queue(
                    "activity",
                    format_efficiency_line(
                        "Eficiência do servidor", audio_servidor / sessao_servidor, sessao_servidor
                    ),
                    "vad_total",
                )
            if audio_servidor > 0 and proc_servidor > 0:
                self._queue(
                    "activity",
                    format_efficiency_line(
                        "Eficiência da GPU", audio_servidor / proc_servidor, proc_servidor
                    ),
                    "vad_total",
                )
        self._queue("activity", BATCH_SUMMARY_SEPARATOR, None)

    # ── Progresso real do servidor Granite NAR (GET /sessions) ───────────────

    # O servidor só responde no fim do job (no ZIP, horas de socket mudo) e o
    # log ficava parado; o /sessions devolve o progresso REAL ao vivo (medido em
    # 16/09: arquivos concluídos, áudio processado e tempo de GPU crescendo
    # durante o processamento). Nada disso existe nos provedores de API.
    SERVER_PROGRESS_INTERVAL = 5.0
    SERVER_PROGRESS_TIMEOUT = 5.0

    @staticmethod
    def _is_multi_transcription(settings: dict) -> bool:
        """True quando o lote vai para DOIS OU MAIS modelos ao mesmo tempo.

        Fonte única da condição: `_workflow`, `_run_transcriptions` e
        `_start_server_progress` precisam concordar. Quando discordaram, o
        poller do `/sessions` ligou no lote multi e imprimiu o progresso do
        Granite NAR como uma LINHA SEPARADA da linha do modelo 1 — o mesmo
        servidor duas vezes, com contadores diferentes do app (relatado pelo
        usuário, 27/09).
        """
        if not settings.get("_multi_transcription"):
            return False
        return len(settings.get("_multi_transcription_models") or []) >= 2

    def _start_server_progress(self, settings: dict, total: int) -> dict | None:
        """Liga a consulta ao /sessions durante o envio; None quando não se aplica.

        Só o servidor STT local (Granite NAR) tem o endpoint — em qualquer outro
        provedor a função devolve None: nenhuma linha nova e nenhuma requisição
        extra. No lote MULTI-MODELO também não liga: cada modelo já tem a sua
        linha viva ("servidor 1012/4004 (25%)") e o `/sessions` repetiria o
        Granite NAR com áudio e eficiência em outra linha (27/09).
        """
        if self._is_multi_transcription(settings):
            return None
        try:
            if not is_local_granite_transcription_server(settings.get("transcription_server")):
                return None
            url = transcribe_url(settings)
        except Exception:
            return None
        estado = {
            "url": url,
            "total": max(0, int(total or 0)),
            "stop": threading.Event(),
            "session_id": "",
            "baseline": [0, 0.0, 0.0],
            "linha": "",
            "publicada": False,
            "resumo": None,
            "thread": None,
        }
        thread = threading.Thread(
            target=self._server_progress_loop,
            args=(estado,),
            daemon=True,
            name="sig-server-progress",
        )
        estado["thread"] = thread
        thread.start()
        return estado

    def _server_progress_loop(self, estado: dict) -> None:
        """Loop do poller (thread de trabalho): nunca derruba o lote."""
        while not estado["stop"].is_set():
            try:
                _ip, sessao = granite_sessions(estado["url"], timeout=self.SERVER_PROGRESS_TIMEOUT)
            except Exception:
                sessao = None
            if sessao:
                try:
                    self._update_server_progress(estado, sessao)
                except Exception:
                    pass
            if estado["stop"].wait(self.SERVER_PROGRESS_INTERVAL):
                return

    def _update_server_progress(self, estado: dict, sessao: dict, *, final: bool = False) -> None:
        """Traduz a sessão do servidor na linha viva e guarda o resumo do fim."""
        session_id = str(sessao.get("session_id") or "")
        if session_id != estado["session_id"]:
            # Sessão nova (a da execução anterior já tinha terminado): zera a base.
            estado["session_id"] = session_id
            estado["baseline"] = [0, 0.0, 0.0]
        baseline_completos, baseline_audio, baseline_proc = estado["baseline"]
        try:
            completos = max(0, int(sessao.get("completed_files") or 0) - baseline_completos)
            audio = max(0.0, float(sessao.get("total_audio_seconds") or 0.0) - baseline_audio)
            proc = max(0.0, float(sessao.get("total_processing_seconds") or 0.0) - baseline_proc)
        except (TypeError, ValueError):
            return
        total = int(sessao.get("zip_total") or 0) or estado["total"]
        try:
            sessao_segundos = max(0.0, float(sessao.get("elapsed_seconds") or 0.0))
        except (TypeError, ValueError):
            sessao_segundos = 0.0
        # (áudio, processamento da GPU, duração da sessão no servidor) — as duas
        # últimas alimentam as linhas "do servidor"/"da GPU" do bloco final.
        estado["resumo"] = (audio, proc, sessao_segundos)
        # A linha viva leva a contagem + a eficiência, sem o tempo de áudio
        # (que repetiria o `Total áudio` do bloco final com outra unidade).
        texto = format_server_progress(completos, total, (audio / proc) if (proc > 0 and audio > 0) else None)
        if not final and texto == estado["linha"]:
            return
        estado["linha"] = texto
        estado["publicada"] = True
        self._queue("activity_line", "server", texto, "vad_total" if final else None)

    def _finish_server_progress(self, estado: dict | None) -> None:
        """Encerra o poller e fecha a linha viva em VERDE com os números finais.

        Faz UMA última leitura (o lote recém-terminado ainda é a nossa sessão) —
        é dela que sai a linha "Servidor:" do bloco de resumo, mesmo em lotes
        curtos que terminaram antes da primeira sondagem.
        """
        if not estado:
            return
        estado["stop"].set()
        thread = estado.get("thread")
        if thread is not None:
            thread.join(timeout=1.0)
        sessao = None
        try:
            _ip, sessao = granite_sessions(estado["url"], timeout=self.SERVER_PROGRESS_TIMEOUT)
        except Exception:
            sessao = None
        if sessao and (
            not estado["session_id"]
            or str(sessao.get("session_id") or "") == estado["session_id"]
        ):
            self._update_server_progress(estado, sessao, final=True)
        elif estado["publicada"]:
            self._queue("activity_line", "server", estado["linha"], "vad_total")

    # ── VAD ──────────────────────────────────────────────────────────

    def _note_vad_problem(self, job: AudioJob, detail: str) -> None:
        """Falha do VAD NÃO descarta o arquivo (regra do usuário, 13/09).

        O VAD é filtro, não requisito: o arquivo convertido segue para a
        transcrição como está, sem VAD. O motivo fica em `job.vad_error` e o log
        ganha UMA linha por tipo ("N arquivo(s) com erro no VAD") — antes era
        uma linha vermelha por arquivo E o arquivo ficava de fora da transcrição.
        """
        job.vad_error = str(detail or "erro não informado pelo worker")
        if job.upload_path is None and job.converted_path is not None:
            if job.converted_path.exists():
                job.upload_path = job.converted_path
        self._queue("job", job.original_path, "Erro no VAD")
        self._queue("batch_error", vad_label(job.vad_error), job.original_name)

    def _run_vad_on_jobs(self, jobs: list, vad_mode: str, settings: dict):
        """Gera WAVs filtrados e os define como arquivos de upload."""
        if vad_mode.startswith("Silero"):
            vad_type = "silero"
        elif vad_mode.startswith("WebRTC"):
            vad_type = "webrtc"
        else:
            return
        level = vad_mode.split("-")[-1].strip()
        # Nome legível da fase: a linha do log passa a dizer QUAL VAD e com
        # que agressividade (pedido do usuário, 27/09) — "Aplicando VAD: 80/100"
        # não dizia nada disso. `vad_type` é o nome interno do motor; aqui vai
        # o nome da TELA ("Silero"/"WebRTC") e o nível escolhido (0 a 3).
        nome_vad = "Silero" if vad_type == "silero" else "WebRTC"
        rotulo_vad = f"Aplicando {nome_vad} VAD ({level})"

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

        def _vad_weight(job) -> int:
            """Peso do ramo: bytes do WAV de entrada (∝ duração em PCM 16k mono)."""
            try:
                return job.converted_path.stat().st_size
            except OSError:
                return 0

        # FAN-OUT (13/09): um processo por núcleo escolhido na slider "VAD". Cada
        # worker é single-threaded (sessão ONNX com 1 thread), então N processos
        # usam N núcleos. Com 1, a fila inteira vai para um processo só, na
        # mesma ordem de sempre.
        parallel = max(1, int(settings.get("vad_parallel") or 1))
        parallel = min(parallel, len(eligible))
        if parallel <= 1:
            ramos = [eligible]
        else:
            # Divisão por PESO: o tempo total é o do ramo mais pesado.
            ramos = split_balanced(eligible, parallel, weight=_vad_weight)
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        output_events: queue.Queue = queue.Queue()
        workers: list[dict] = []
        for lote in ramos:
            payload = {
                "vad_type": vad_type,
                "level": level,
                "vad_deps": str(deps),
                "files": [
                    {"input": str(job.converted_path), "output": str(job.vad_output_path)}
                    for job in lote
                ],
            }
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
            ramo = {"process": process, "jobs": lote, "stderr": [], "payload": payload, "threads": []}
            workers.append(ramo)

            def read_stdout(process=process):
                assert process.stdout is not None
                for line in process.stdout:
                    output_events.put(line)
                output_events.put(None)

            def read_stderr(process=process, ramo=ramo):
                assert process.stderr is not None
                for line in process.stderr:
                    ramo["stderr"].append(line)

            for alvo in (read_stdout, read_stderr):
                thread = threading.Thread(target=alvo, daemon=True)
                thread.start()
                ramo["threads"].append(thread)

        jobs_by_input = {str(job.converted_path): job for job in eligible}
        ramo_por_input = {
            str(job.converted_path): ramo for ramo in workers for job in ramo["jobs"]
        }
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
                    self._note_vad_problem(job, "arquivo filtrado vazio")
            else:
                self._note_vad_problem(job, str(item.get("error", "erro não informado pelo worker")))
            completed += 1
            self._queue_phase_progress(rotulo_vad, completed, len(eligible), "vad", vad_started)

        def encerrar(process):
            """Encerra um worker do VAD: termina e, se preciso, mata."""
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

        try:
            for ramo in workers:
                assert ramo["process"].stdin is not None
                ramo["process"].stdin.write(json.dumps(ramo["payload"], ensure_ascii=False))
                ramo["process"].stdin.close()
            # Um stream fechado = um worker terminou (cada leitor enfileira None).
            streams_abertos = len(workers)
            while streams_abertos:
                if self.cancel_event.is_set():
                    for ramo in workers:
                        encerrar(ramo["process"])
                    raise Cancelled()
                try:
                    line = output_events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    streams_abertos -= 1
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
            for ramo in workers:
                ramo["process"].wait()
                for thread in ramo["threads"]:
                    thread.join(timeout=1)
        finally:
            with self.process_lock:
                for ramo in workers:
                    self.active_processes.discard(ramo["process"])

        for job in eligible:
            input_path = str(job.converted_path)
            if input_path in completed_inputs:
                continue
            ramo = ramo_por_input.get(input_path)
            detalhe = "".join(ramo["stderr"]).strip() if ramo else ""
            codigo = ramo["process"].returncode if ramo else None
            if diagnostics:
                detalhe = "\n".join([detalhe, *diagnostics]).strip()
            detail = detalhe or f"worker encerrado sem resultado (código {codigo})"
            self._note_vad_problem(job, detail)
            completed += 1
            self._queue_phase_progress(rotulo_vad, completed, len(eligible), "vad", vad_started)
        if eligible and all(job.vad_error for job in eligible):
            # VAD é filtro, não requisito: os arquivos seguem para a transcrição
            # sem VAD (regra do usuário, 13/09) — antes a fila inteira abortava.
            self._queue(
                "activity",
                "O VAD falhou em todos os arquivos; seguindo para a transcrição sem VAD.",
                "warning",
            )

    def _queue_phase_progress(
        self,
        label: str,
        done: int,
        total: int,
        phase_key: str | None = None,
        started: float | None = None,
        *,
        update_progress: bool = True,
    ):
        """Linha viva de fase (log) + barra de status, no padrão do lote.

        `update_progress=False` para quem tem o PRÓPRIO esquema de barra (o ZIP
        mapeia a criação para 0-30% e o resto para 35-98%): a linha viva do log
        e a barra de status continuam iguais, só o valor da barra de progresso
        não é sobrescrito.
        """
        percent = int((done / max(total, 1) * 100) + 0.5)
        if update_progress:
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

    def _queue_pipeline_progress(
        self,
        converted_done: int,
        convert_total: int,
        transcribed_done: int,
        transcribe_total: int,
        convert_started: float,
        transcribe_started: float,
    ):
        """Linhas do modo pipeline (conversão e transcrição ao mesmo tempo).

        Cada linha tem o SEU total: os dois caem conforme arquivos saem da fila
        (falha de conversão sai das duas; arquivo já pronto sai só da conversão,
        porque continua sendo transcrito) — regra do usuário, 13/09.
        """
        convert_percent = int((converted_done / max(convert_total, 1) * 100) + 0.5)
        transcribe_percent = int((transcribed_done / max(transcribe_total, 1) * 100) + 0.5)
        current_percent = convert_percent if converted_done < convert_total else transcribe_percent
        self._queue("progress", current_percent)
        if converted_done >= convert_total:
            self._queue("activity_line", "convert", f"Convertendo arquivos: {converted_done}/{convert_total} ({format_duration(time.perf_counter() - convert_started)})", "vad_total")
        else:
            self._queue("activity_line", "convert", f"Convertendo arquivos: {converted_done}/{convert_total} ({convert_percent}%)", None)
        if transcribed_done >= transcribe_total:
            self._queue("activity_line", "transcribe", f"Transcrevendo arquivos: {transcribed_done}/{transcribe_total} ({format_duration(time.perf_counter() - transcribe_started)})", "vad_total")
        else:
            self._queue("activity_line", "transcribe", f"Transcrevendo arquivos: {transcribed_done}/{transcribe_total} ({transcribe_percent}%)", None)

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
            self._queue("batch_error", zip_label(detail), job.original_name)

    def _run_zip_transcription(
        self,
        jobs: list[AudioJob],
        settings: dict,
        temp_dir: Path,
        raw_dir: Path,
        zip_level: str,
    ) -> list[tuple[str, str]]:
        candidates = transcription_candidates(jobs)
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
                self._queue("batch_error", conversion_label(job.error), job.original_name)
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
        # Linha VIVA no log (padrão das conversões/transcrições), NUNCA uma linha
        # por arquivo: numa fila de milhares o log virava uma parede (pedido do
        # usuário, 13/09). Fecha verde com o tempo ao terminar.
        self._queue_phase_progress(
            "Criando ZIP para envio", 0, len(zip_jobs), "zip", create_started, update_progress=False
        )
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
                    self._queue_phase_progress(
                        "Criando ZIP para envio",
                        index,
                        len(zip_jobs),
                        "zip",
                        create_started,
                        update_progress=False,
                    )
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
            send_message = f"Enviando ZIP ({format_bytes(zip_size)}) e aguardando resposta do servidor..."
            # PRETA enquanto espera (regra do usuário, 14/09): como linha viva
            # ela NÃO passa pela cor automática do log — no `status` o padrão
            # `^enviando` pintava de verde antes de o ZIP chegar.
            self._queue("activity_line", "zip_send", send_message, None)
            self._queue("status_silent", send_message)
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
            # Cancelar vale para a resposta inteira do servidor: não processar
            # (nem esperar) o que chegou depois do cancelamento.
            if self.cancel_event.is_set():
                raise Cancelled()
            if status != 200:
                preview = raw.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"HTTP {status}: {preview[:500]}")
            if not zipfile.is_zipfile(response_zip_path):
                preview = raw.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"o servidor não retornou um ZIP válido: {preview[:500]}")

            # ZIP recebido e válido: a linha do envio fecha VERDE com o tempo
            # percorrido entre parênteses (regra do usuário, 14/09).
            received_message = f"{send_message} ({format_duration(request_elapsed)})"
            self._queue("activity_line", "zip_send", received_message, "vad_total")
            self._queue("status_silent", received_message)

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
            process_started = time.perf_counter()
            # Mesmo padrão da criação: UMA linha viva que fecha verde com o
            # tempo — nunca uma linha por arquivo.
            self._queue_phase_progress(
                "Processando resposta ZIP", 0, len(zip_jobs), "zip_response", process_started, update_progress=False
            )
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
                self._queue_phase_progress(
                    "Processando resposta ZIP",
                    done,
                    len(zip_jobs),
                    "zip_response",
                    process_started,
                    update_progress=False,
                )
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
        base_total = len(jobs)
        done = 0
        # O total mostrado CAI a cada arquivo que sai da fila de verdade — falha de
        # conversão ou arquivo que já estava no formato pedido: "Convertendo
        # arquivos: 500/900 (55%)" (regra do usuário, 13/09). Com isso a linha
        # fecha em N/N exatamente quando tudo terminou (done = total - pendentes).
        excluidos = 0
        # Mede a conversão desde o início do lote (quando "Preparando fila"
        # apareceu) para o tempo mostrado bater com o relógio do log
        # (preparação + conversão), sem "sumir" com a preparação.
        convert_started = getattr(self, "_prepare_started", time.perf_counter())
        self._queue_phase_progress("Convertendo arquivos", done, base_total, "convert", convert_started)
        convert_workers = max(1, int(settings.get("convert_parallel") or 1))
        with cancellable_executor(convert_workers) as executor:
            future_map = {executor.submit(self._convert_job, job): job for job in jobs}
            for future in iter_completed(future_map, cancel_event=self.cancel_event):
                job = future_map[future]
                excluido = False
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
                    # Uma linha vermelha por TIPO de erro (com a contagem), não
                    # uma por arquivo (regra do usuário, 13/09).
                    self._queue("batch_error", conversion_label(job.error), job.original_name)
                    excluido = True
                if job.preparation:
                    # Já estava no formato pedido: não conta como conversão.
                    excluido = True
                if excluido:
                    excluidos += 1
                else:
                    done += 1
                self._queue_phase_progress(
                    "Convertendo arquivos", done, max(0, base_total - excluidos), "convert", convert_started
                )

    def _run_pipelined_conversions_and_transcriptions(self, jobs: list[AudioJob], settings: dict):
        base_total = len(jobs)
        converted_done = 0
        transcribed_done = 0
        # Arquivos que saem da fila de verdade: falha de conversão sai das DUAS
        # linhas (não vai para a transcrição); arquivo já no formato pedido sai só
        # da conversão (continua indo para a transcrição) — regra do usuário, 13/09.
        fora_da_conversao = 0
        fora_da_transcricao = 0
        progress_lock = threading.Lock()
        converted_queue: queue.Queue = queue.Queue()
        sentinel = object()
        url = transcribe_url(settings)
        convert_started = time.perf_counter()
        transcribe_started = time.perf_counter()

        self._queue_pipeline_progress(
            converted_done, base_total, transcribed_done, base_total, convert_started, transcribe_started
        )

        def update_progress(
            convert_delta: int = 0,
            transcribe_delta: int = 0,
            *,
            fora_da_conversao_agora: bool = False,
            fora_da_transcricao_agora: bool = False,
        ):
            nonlocal converted_done, transcribed_done, fora_da_conversao, fora_da_transcricao
            with progress_lock:
                converted_done += convert_delta
                transcribed_done += transcribe_delta
                if fora_da_conversao_agora:
                    fora_da_conversao += 1
                if fora_da_transcricao_agora:
                    fora_da_transcricao += 1
                current_converted = converted_done
                current_transcribed = transcribed_done
                total_convert = max(0, base_total - fora_da_conversao)
                total_transcribe = max(0, base_total - fora_da_transcricao)
            self._queue_pipeline_progress(
                current_converted,
                total_convert,
                current_transcribed,
                total_transcribe,
                convert_started,
                transcribe_started,
            )

        def convert_runner(job: AudioJob):
            if self.cancel_event.is_set():
                raise Cancelled()
            try:
                self._convert_job(job)
                self._queue("job", job.original_path, "Convertido")
                if job.preparation:
                    # Já estava no formato pedido: sai do total da conversão, mas
                    # segue para a transcrição.
                    update_progress(fora_da_conversao_agora=True)
                else:
                    update_progress(convert_delta=1)
                converted_queue.put(job)
            except Cancelled:
                raise
            except Exception as exc:
                job.error = f"ERRO conversão: {exc}"
                job.txt_path.write_text(job.error, encoding="utf-8")
                self._queue("job", job.original_path, self._conversion_failure_status(exc))
                self._queue("batch_error", conversion_label(job.error), job.original_name)
                update_progress(fora_da_conversao_agora=True, fora_da_transcricao_agora=True)

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
        with cancellable_executor(transcribe_workers) as transcribe_executor:
            transcribe_futures = [
                transcribe_executor.submit(transcribe_worker)
                for _ in range(transcribe_workers)
            ]
            try:
                with cancellable_executor(convert_workers) as convert_executor:
                    convert_futures = [convert_executor.submit(convert_runner, job) for job in jobs]
                    for future in iter_completed(convert_futures, cancel_event=self.cancel_event):
                        future.result()
                for _ in transcribe_futures:
                    converted_queue.put(sentinel)
                cancellable_join(converted_queue, cancel_event=self.cancel_event)
                for future in iter_completed(transcribe_futures, cancel_event=self.cancel_event):
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

        # Evita recodificar o que JÁ está no formato pedido: WAV PCM 16 kHz
        # mono/16-bit ("Enviar pronto") ou Ogg/Opus 16 kHz mono ("Enviar
        # compactado"). Cada caso alimenta a linha "N/M arquivos já estavam
        # prontos/compactados" no log (regra do usuário, 13/09).
        if job.mode == "ready" and is_transcription_ready_wav(job.original_path):
            self._stage_without_reencoding(job, "pronto", "Arquivo já pronto | sem recodificação")
            return
        if job.mode == "compact" and is_transcription_ready_compressed(job.original_path):
            self._stage_without_reencoding(job, "compactado", "Arquivo já compactado | sem recodificação")
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


    def _stage_without_reencoding(self, job: AudioJob, kind: str, preparation: str) -> None:
        """Encaminha o arquivo que já está no formato pedido, sem reencode.

        Link local quando dá (mesmo volume), cópia quando não dá. Marca
        `job.preparation` e avisa a UI para a linha "N/M arquivos já estavam
        prontos/compactados" (regra do usuário, 13/09).
        """
        started = time.perf_counter()
        job.converted_path.parent.mkdir(parents=True, exist_ok=True)
        if job.converted_path.exists():
            job.converted_path.unlink()
        try:
            os.link(job.original_path, job.converted_path)
            detail = "link local"
        except OSError:
            shutil.copy2(job.original_path, job.converted_path)
            detail = "cópia local"
        job.preparation = kind
        job.conversion_elapsed = time.perf_counter() - started
        job.upload_path = job.converted_path
        conversion_summary = (
            f"{preparation} ({detail}) | {format_bytes(job.original_path.stat().st_size)} | "
            f"{format_duration(job.conversion_elapsed)}"
        )
        if job.log_path:
            try:
                job.log_path.write_text(conversion_summary + "\n", encoding="utf-8")
            except OSError:
                pass
        self._queue("tree_size", job.original_path, self._job_size_column_text(job))
        self._queue("prep_count", kind, int(getattr(self, "_batch_job_total", 0) or 0))

    def _run_transcriptions(self, jobs: list[AudioJob], settings: dict):
        if settings.get("_multi_transcription") and len(settings.get("_multi_transcription_models") or []) >= 2:
            self._run_multi_transcriptions(jobs, settings)
            return
        candidates = transcription_candidates(jobs)
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
            with cancellable_executor(max(1, parallelism)) as executor:
                future_map = {
                    executor.submit(self._transcribe_job, job, url, None, settings): job
                    for job in group
                }
                for future in iter_completed(future_map, cancel_event=self.cancel_event):
                    job = future_map[future]
                    try:
                        future.result()
                        self._queue("job", job.original_path, "Transcrito")
                    except Cancelled:
                        raise
                    except Exception as exc:
                        job.error = f"ERRO transcrição: {exc}"
                        job.txt_path.write_text(job.error, encoding="utf-8")
                        self._queue("job", job.original_path, "Erro na transcrição")
                        self._queue("batch_error", transcription_label(str(exc)), job.original_name)
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
        candidates = transcription_candidates(jobs)
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
        # Relógio PRÓPRIO de cada modelo, CONGELADO no instante em que ele
        # termina: a linha verde não pode continuar contando por conta dos
        # outros modelos que ainda estão transcrevendo (bug relatado 13/09).
        model_end_times: list[float | None] = [None] * len(model_settings)
        model_reported = [False] * len(model_settings)
        model_labels = list(model_names)

        def update_progress(index: int):
            now = time.perf_counter()
            with progress_lock:
                done[index - 1] += 1
                snapshot = list(done)
                if snapshot[index - 1] >= total and model_end_times[index - 1] is None:
                    model_end_times[index - 1] = now - model_starts[index - 1]
            self._queue("progress", int((sum(snapshot) / (total * len(model_settings))) * 100 + 0.5))
            throttles = getattr(self, "_model_throttle", None)
            if throttles is None:
                throttles = {}
                self._model_throttle = throttles
            # Terminou AGORA e ainda não avisou: a linha verde dele é o único
            # aviso de conclusão e sai na hora, sem esperar o throttle.
            pending = [
                model_index
                for model_index, count in enumerate(snapshot, start=1)
                if count >= total and not model_reported[model_index - 1]
            ]
            emit_lines = bool(pending) or now - throttles.get("all", 0.0) >= 0.1
            if not emit_lines:
                return
            throttles["all"] = now
            for model_index, count in enumerate(snapshot, start=1):
                label = model_labels[model_index - 1]
                if count >= total:
                    # Linha FECHADA: escrita UMA única vez, com o tempo do
                    # próprio modelo — reescrever aqui faria o relógio continuar
                    # correndo enquanto os outros modelos transcrevem.
                    with progress_lock:
                        ja_avisado = model_reported[model_index - 1]
                        model_reported[model_index - 1] = True
                    if ja_avisado:
                        continue
                    end = model_end_times[model_index - 1]
                    if end is None:
                        end = now - model_starts[model_index - 1]
                    self._queue(
                        "activity_line",
                        f"model:{model_index}",
                        f"{label} {count}/{total} ({format_duration(end)})",
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
            # O relógio do modelo começa quando ELE começa de verdade — no modo
            # "um modelo por vez" o segundo só entra depois de o primeiro
            # terminar e não pode herdar o tempo da espera.
            model_starts[index - 1] = time.perf_counter()
            url = transcribe_url(current_settings)
            configured_parallelism = max(1, int(settings["transcribe_parallel"]))

            def run_group(group: list[AudioJob], parallelism: int):
                if not group:
                    return
                with cancellable_executor(max(1, parallelism)) as executor:
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
                    for future in iter_completed(future_map, cancel_event=self.cancel_event):
                        job = future_map[future]
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
                            self._queue(
                                "batch_error",
                                transcription_label(str(exc), model_labels[index - 1]),
                                job.original_name,
                            )
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

        if settings.get("_one_model_at_a_time"):
            # "Um modelo por vez" (checkbox da aba Transcrição): a fila INTEIRA
            # vai para o modelo da vez e só depois de ele terminar o próximo
            # começa — os modelos nunca ficam em voo ao mesmo tempo (cada um
            # mantém o paralelismo PRÓPRIO de requisições). O HTML do lote
            # continua saindo uma única vez, no fim de TODOS os modelos, em
            # `_workflow` — nada é gerado por modelo.
            for index in range(1, len(model_settings) + 1):
                if self.cancel_event.is_set():
                    raise Cancelled()
                model_runner(index)
        else:
            with cancellable_executor(len(model_settings)) as executor:
                futures = [executor.submit(model_runner, index) for index in range(1, len(model_settings) + 1)]
                for future in iter_completed(futures, cancel_event=self.cancel_event):
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
                    self._append_params_block(
                        message[1],
                        message[2],
                        message[3] if len(message) > 3 else "",
                    )
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
                    self._update_activity_line(self._run_scoped_activity_key(key), text, tag)
                elif kind == "batch_error":
                    label = message[1]
                    item = message[2] if len(message) > 2 else ""
                    self._register_batch_error(label, item)
                elif kind == "prep_count":
                    kind_label = message[1]
                    total = message[2] if len(message) > 2 else 0
                    self._register_preparation(kind_label, total)
                elif kind == "partial_report_offer":
                    # Aviso do relatório parcial (cancelamento): a decisão volta
                    # para o worker pelo Event, que é quem escreve o HTML.
                    decisao, pronto = message[1], message[2]
                    try:
                        decisao[0] = bool(
                            messagebox.askyesno(
                                "sig",
                                "Cancelado.\n\nDeseja gerar um relatório parcial (tabela HTML) "
                                "com o que já foi transcrito?",
                            )
                        )
                    finally:
                        pronto.set()
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
                        fill=X, pady=(16, 0), before=getattr(self, "qrcode_form_actions", None)
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
                        # Use the existing top padding and tab-bar gap. A placed
                        # widget does not resize the packed rows below it.
                        self.update_button.place(
                            relx=1.0, x=-18, y=0, anchor="ne"
                        )
                        # The tab bar is created after this button and may
                        # overlap it at higher DPI scales. Keep the button in
                        # the reserved header area and above that sibling.
                        self.update_button.tkraise()
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
        if getattr(self, "diarias_busy", False):
            messagebox.showinfo("Diárias", "Aguarde a geração ou o envio da diária terminar antes de fechar.", parent=self.root)
            return
        self._app_closing = True
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
    if len(sys.argv) == 3 and sys.argv[1] == "--sig-print-job":
        raise SystemExit(pdf_printing.execute_print_job_file(sys.argv[2]))
    root = Tk()
    app = SigApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
