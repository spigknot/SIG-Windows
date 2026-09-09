"""Formatacao de texto para log e UI.

Responsabilidade unica: transformar dados em texto de log/rotulo.
Nao faz I/O, nao conhece Tkinter, nao chama rede.
Extraido de sig_app.py sem alteracao de comportamento."""

import os
import re
import shlex
import subprocess
from pathlib import Path, PurePosixPath


# Marca o bloco de comandos FFmpeg exibido no log das ferramentas. Um clique em
# qualquer linha do bloco copia todos os comandos, nao apenas a linha clicada.
FFMPEG_COMMAND_BLOCK_TAG = "ffmpeg_command_block"
def format_process_command(command: list[object]) -> str:
    """Renderiza a linha de comando exatamente como os argumentos do processo."""
    parts = [str(part) for part in command]
    return subprocess.list2cmdline(parts) if os.name == "nt" else shlex.join(parts)
def _log_path_basename(part: str) -> str:
    """Reduz um argumento que é caminho de arquivo ao nome base, apenas para a
    apresentação no log. Filtros/expressões (contêm ``=``) e valores simples
    (``16000``, ``pcm_s16le``, ``0.5``) ficam intactos.

    Ex.: "C:\\...\\audios\\audio.wav"  ->  "audio.wav"
    """
    if "=" in part:
        return part
    if ("\\" in part or "/" in part or os.path.isabs(part)) and (
        "." in Path(part).name or os.path.isabs(part)
    ):
        return Path(part).name or part
    return part
_NUMERIC_LOG_ARG_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_LOG_FILE_SUFFIX_RE = re.compile(r"^\.[A-Za-z0-9]{1,5}$")
def _log_generic_filename(part: str, generic_stem: str) -> str:
    """Reduz um argumento de arquivo ao nome genérico ``<generic_stem><ext>``,
    preservando a extensão original e descartando o nome real e o diretório.

    Ex.: "C:\\...\\videos\\nomedovideo.mp4"  ->  "input.mp4"  (ou "output.mp4")

    Argumentos que não são arquivos ficam intactos: filtros/expressões (contêm
    ``=``), opções (começam com ``-``), números (``0.5``, ``1.5``) e saídas
    especiais sem extensão (``pipe:1``, ``-``).
    """
    base = _log_path_basename(part)
    if not base or base.startswith("-") or "=" in base or _NUMERIC_LOG_ARG_RE.match(base):
        return base
    suffix = Path(base).suffix
    if not _LOG_FILE_SUFFIX_RE.match(suffix) or not Path(base).stem:
        return base
    return f"{generic_stem}{suffix}"
def _classify_ffmpeg_command_parts(command: list[object]) -> tuple[list[str], str, bool, int, set[int], int]:
    """Classifica um comando FFmpeg para exibição enxuta no log.

    Retorna (parts, nome do executável, é_ffmpeg, start, índices de entrada,
    índice da saída). Entradas: todo argumento que sucede imediatamente um
    ``-i``. Saída: o último argumento (o FFmpeg exige o destino no final da
    linha), exceto quando ele é uma das entradas, como nos comandos de sondagem.
    """
    parts = [str(part) for part in command]
    executable = parts[0]
    name = Path(executable).stem
    is_ffmpeg = name.lower() in ("ffmpeg", "ffplay", "ffprobe")
    start = 1 if is_ffmpeg else 0
    input_indices = {
        index + 1
        for index in range(start, len(parts))
        if parts[index] == "-i" and index + 1 < len(parts)
    }
    output_index = len(parts) - 1
    if output_index < start or output_index in input_indices:
        output_index = -1
    return parts, name, is_ffmpeg, start, input_indices, output_index
def _is_structural_probe(parts: list[str], output_index: int) -> bool:
    """Comando de colheita de informações não produz arquivo de saída: termina
    na própria entrada (``ffmpeg -hide_banner -i x``) ou em um sumidouro
    (``-f null -``, ``pipe:...``). Esses comandos são agrupados no log das
    ferramentas para não poluir a leitura dos comandos que alteram arquivos."""
    if output_index == -1:
        return True
    last = parts[output_index]
    return last == "-" or last.startswith("pipe:")
def format_ffmpeg_command_for_log(command: list[object]) -> str:
    """Renderiza o comando FFmpeg para o log de forma enxuta e objetiva: apenas
    ``ffmpeg`` + argumentos, com os arquivos de entrada reduzidos a
    ``input.<ext>`` e a saída a ``output.<ext>`` (sem diretórios e sem o nome
    real, mas preservando a extensão original). Somente a APRESENTAÇÃO muda —
    o comando efetivamente executado continua usando os caminhos e nomes reais.

    Ex.: ffmpeg -hide_banner -y -i input.mp3 -vn -ac 1 -ar 16000 -c:a pcm_s16le output.wav
    """
    if not command:
        return ""
    parts, name, is_ffmpeg, start, input_indices, output_index = _classify_ffmpeg_command_parts(command)
    display = [name] if is_ffmpeg else []
    for index in range(start, len(parts)):
        if index in input_indices:
            display.append(_log_generic_filename(parts[index], "input"))
        elif index == output_index:
            display.append(_log_generic_filename(parts[index], "output"))
        else:
            display.append(_log_path_basename(parts[index]))
    return subprocess.list2cmdline(display) if os.name == "nt" else shlex.join(display)
def _numbered_log_label(path_arg: str, category: str, labels: dict[str, str]) -> str:
    """Rótulo genérico com numeração POR ARQUIVO DISTINTO dentro da categoria.

    O primeiro arquivo de cada categoria não recebe número (``input.mp4``); os
    arquivos novos recebem a ordem de primeira aparição (``input2.mp4``,
    ``input3.avi``...) e arquivos repetidos mantêm o rótulo já atribuído. A
    contagem independe da extensão — o sufixo exibido é sempre o do próprio
    arquivo. Argumentos que não são arquivos ficam intactos (mesmas regras do
    ``_log_generic_filename``).
    """
    base = _log_path_basename(path_arg)
    if not base or base.startswith("-") or "=" in base or _NUMERIC_LOG_ARG_RE.match(base):
        return base
    suffix = Path(base).suffix
    if not _LOG_FILE_SUFFIX_RE.match(suffix) or not Path(base).stem:
        return base
    existing = labels.get(path_arg)
    if existing is not None:
        return existing
    ordinal = len(labels) + 1
    label = f"{category}{'' if ordinal == 1 else ordinal}{suffix}"
    labels[path_arg] = label
    return label
def format_ffmpeg_commands_for_log(
    commands: list[list[object]],
    probes: list[bool] | tuple[bool, ...] | None = None,
) -> list[tuple[str, bool]]:
    """Renderiza a sequência de comandos FFmpeg de uma execução das ferramentas.

    A numeração de arquivos é contínua entre os comandos e independente por
    categoria: entradas viram ``input.<ext>``/``input2.<ext>``/... e saídas
    ``output.<ext>``/``output2.<ext>``/... na ordem em que cada ARQUIVO
    (caminho real) aparece pela primeira vez. Assim, uma sonda por arquivo em
    uma junção com vários clipes vira ``input.mp4``, ``input2.mp4``, ... em vez
    de repetir ``input.mp4``.

    Retorna uma entrada por comando: ``(linha exibida, é_probe)``. Um comando é
    probe quando marcado no parâmetro ``probes`` ou quando não produz arquivo de
    saída (termina na entrada ou em sumidouro ``-``/``pipe:``) — o chamador usa
    essa flag para agrupar sondas consecutivas sem linha em branco.
    """
    input_labels: dict[str, str] = {}
    output_labels: dict[str, str] = {}
    entries: list[tuple[str, bool]] = []
    for index, command in enumerate(commands):
        if not command:
            continue
        parts, name, is_ffmpeg, start, input_indices, output_index = _classify_ffmpeg_command_parts(command)
        display = [name] if is_ffmpeg else []
        for part_index in range(start, len(parts)):
            if part_index in input_indices:
                display.append(_numbered_log_label(parts[part_index], "input", input_labels))
            elif part_index == output_index:
                display.append(_numbered_log_label(parts[part_index], "output", output_labels))
            else:
                display.append(_log_path_basename(parts[part_index]))
        rendered = subprocess.list2cmdline(display) if os.name == "nt" else shlex.join(display)
        flagged = bool(probes[index]) if probes else False
        entries.append((rendered, flagged or _is_structural_probe(parts, output_index)))
    return entries
def params_block_single_line(text: str) -> str:
    """Junta um bloco de parâmetros do log em uma só linha (p/ clipboard).

    Remove os timestamps de cada linha e ignora linhas em branco.
    """
    parts = []
    for line in str(text or "").splitlines():
        stripped = re.sub(r"^\d{2}:\d{2}:\d{2}\s+", "", line).strip()
        if stripped:
            parts.append(stripped)
    return " ".join(parts)
def format_ws_params_block(title: str, params) -> str:
    """Bloco de log com um parâmetro por linha (regra de visibilidade).

    `params` aceita dict ou lista de pares (a lista preserva chaves
    repetidas da query, ex.: secondary_languages).
    """
    items = params.items() if isinstance(params, dict) else params
    lines = [f"{title}:"]
    for key, value in items:
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)
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
