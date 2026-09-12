"""Catalogo de encoders de video e regra de escolha do encoder por tarefa.

O operador escolhe ONDE processar (GPU ou CPU); o app decide o encoder
concreto, ciente de: codec exigido pela tarefa (o do arquivo quando o objetivo
e preservar o codec), do que existe DE VERDADE na maquina (sondagem real) e do
custo de inicializacao da GPU em trechos curtos.

Regras (cada escolha devolve um MOTIVO, que vai para o log):
- CPU: nunca usa GPU.
- GPU: prefere o melhor encoder de hardware disponivel PARA O CODEC pedido e
  so cai no software quando (a) a GPU nao tem encoder daquele codec, (b) o
  usuario forcou no Avancado um encoder que nao passou na sondagem, ou (c) no
  modo automatico o trecho a reencodar e curto demais para a inicializacao da
  GPU compensar (medido: ~0,4-0,6s de inicializacao no NVENC).
- Nada de rebaixamento silencioso: fora do automatico um forcado indisponivel
  vira software COM aviso; falha de hardware em tempo de execucao repete a
  tarefa na CPU sem trocar a preferencia do usuario.
"""

from __future__ import annotations

from dataclasses import dataclass

ENCODER_PATH_GPU = "gpu"
ENCODER_PATH_CPU = "cpu"
ENCODER_ADVANCED_AUTO = "auto"

PATH_LABELS = {
    ENCODER_PATH_GPU: "GPU",
    ENCODER_PATH_CPU: "CPU",
}

# Trecho curto: abaixo disto a inicializacao da GPU (~0,4-0,6s medidos nesta
# maquina) nao compensa — o software entrega o mesmo tempo e arquivo menor.
SHORT_JOB_SECONDS = 3.0


@dataclass(frozen=True)
class EncoderOption:
    """Um encoder concreto do catalogo (uma combinacao familia x codec)."""

    key: str
    label: str
    path: str
    codec: str
    encoder: str
    priority: int


@dataclass(frozen=True)
class EncoderChoice:
    """Encoder escolhido + por que (o motivo vai para o log)."""

    option: EncoderOption
    reason: str


# Catálogo: só o que o ffmpeg empacotado realmente oferece hoje (h264/hevc),
# com os pares HEVC de cada familia (necessarios para preservar o codec da
# fonte). `priority` menor = preferido entre as GPUs.
CATALOG: tuple[EncoderOption, ...] = (
    EncoderOption("nvenc", "NVENC (NVIDIA)", ENCODER_PATH_GPU, "h264", "h264_nvenc", 10),
    EncoderOption("nvenc", "NVENC (NVIDIA)", ENCODER_PATH_GPU, "hevc", "hevc_nvenc", 10),
    EncoderOption("qsv", "QSV (Intel)", ENCODER_PATH_GPU, "h264", "h264_qsv", 20),
    EncoderOption("qsv", "QSV (Intel)", ENCODER_PATH_GPU, "hevc", "hevc_qsv", 20),
    EncoderOption("amf", "AMF (AMD)", ENCODER_PATH_GPU, "h264", "h264_amf", 30),
    EncoderOption("amf", "AMF (AMD)", ENCODER_PATH_GPU, "hevc", "hevc_amf", 30),
    EncoderOption("cpu", "CPU", ENCODER_PATH_CPU, "h264", "libx264", 100),
    EncoderOption("cpu", "CPU", ENCODER_PATH_CPU, "hevc", "libx265", 100),
    # Ultimo recurso: MPEG-4 Part 2 quando nao ha libx264 (compatibilidade).
    EncoderOption("cpu-mpeg4", "CPU (compativel)", ENCODER_PATH_CPU, "h264", "mpeg4", 200),
)

CODEC_ALIASES = {
    "h264": "h264",
    "avc": "h264",
    "avc1": "h264",
    "hevc": "hevc",
    "h265": "hevc",
    "hvc1": "hevc",
    "hev1": "hevc",
}


def options_to_tuples(options: list[EncoderOption]) -> list[tuple]:
    """Serializa o catalogo sondado para atravessar a fronteira da UI thread."""
    return [
        (option.key, option.label, option.path, option.codec, option.encoder, option.priority)
        for option in options
    ]


def options_from_tuples(pairs) -> list[EncoderOption]:
    """Reconstroi as opcoes recebidas do worker (valores simples, sem Tk)."""
    opcoes: list[EncoderOption] = []
    for item in pairs or []:
        try:
            key, label, path, codec, encoder, priority = item
            opcoes.append(EncoderOption(str(key), str(label), str(path), str(codec), str(encoder), int(priority)))
        except (TypeError, ValueError):
            continue
    return opcoes


def normalize_codec(codec: str) -> str:
    """Codec do catalogo ('h264'/'hevc'); vazio quando nao ha par no catalogo."""
    return CODEC_ALIASES.get(str(codec or "").lower(), "")


def catalog_options(codec: str = "", path: str = "") -> list[EncoderOption]:
    """Opcoes do catalogo, filtradas por codec e/ou caminho (GPU/CPU)."""
    alvo = normalize_codec(codec) if codec else ""
    opcoes = [
        option for option in CATALOG
        if (not alvo or option.codec == alvo) and (not path or option.path == path)
    ]
    return sorted(opcoes, key=lambda option: (option.priority, option.encoder))


def available_keys(available: list[EncoderOption]) -> list[str]:
    """Familias (sem repetir) que passaram na sondagem, na ordem de preferencia."""
    vistos: list[str] = []
    for option in sorted(available, key=lambda item: item.priority):
        if option.path == ENCODER_PATH_GPU and option.key not in vistos:
            vistos.append(option.key)
    return vistos


def resolve_encoder(
    *,
    codec: str,
    path: str,
    available: list[EncoderOption],
    advanced: str = ENCODER_ADVANCED_AUTO,
    seconds: float = 0.0,
    short_job_seconds: float = SHORT_JOB_SECONDS,
) -> EncoderChoice | None:
    """Escolhe o encoder para UMA tarefa. None quando nao existe opcao viavel."""
    alvo = normalize_codec(codec) or "h264"
    viaveis = [option for option in available if option.codec == alvo]
    software = next((option for option in viaveis if option.path == ENCODER_PATH_CPU), None)

    if path == ENCODER_PATH_CPU:
        if software is None:
            return None
        return EncoderChoice(software, f"modo CPU escolhido pelo usuario ({software.encoder})")

    hardware = [option for option in viaveis if option.path == ENCODER_PATH_GPU]
    if advanced and advanced != ENCODER_ADVANCED_AUTO:
        forcado = next((option for option in hardware if option.key == advanced), None)
        if forcado is not None:
            return EncoderChoice(forcado, f"{forcado.label} forcado no Avancado")
        if software is None:
            return None
        return EncoderChoice(
            software,
            f"{advanced} nao passou na sondagem desta maquina; "
            f"usando CPU ({software.encoder})",
        )

    if not hardware:
        if software is None:
            return None
        return EncoderChoice(
            software,
            f"a GPU desta maquina nao tem encoder {alvo.upper()}; usando CPU ({software.encoder})",
        )

    preferido = hardware[0] if len(hardware) == 1 else min(hardware, key=lambda option: option.priority)
    if seconds and seconds < short_job_seconds and software is not None:
        return EncoderChoice(
            software,
            f"trecho curto de {seconds:.2f}s (< {short_job_seconds:g}s): a inicializacao da GPU "
            f"nao compensa; usando CPU ({software.encoder})",
        )
    return EncoderChoice(preferido, f"GPU disponivel para {alvo.upper()}: {preferido.label}")


def hevc_tag_arguments(encoder: str, suffix: str = ".mp4") -> list[str]:
    """Tag `hvc1` para HEVC em MP4 (sem ela alguns players nao abrem o arquivo)."""
    if not str(encoder or "").lower().startswith(("libx265", "hevc_")):
        return []
    if str(suffix or "").lower() not in (".mp4", ".mov", ".m4v"):
        return []
    return ["-tag:v", "hvc1"]
