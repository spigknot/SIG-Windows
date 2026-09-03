"""Planejador puro do SmartJoin - espelho fiel do SmartJoinPlanner.kt (Android).

Os corpos elegiveis para stream copy sempre comecam e terminam em keyframes.
As lacunas entre o corte logico e esses keyframes viram margens da emenda
recodificada. Um clipe incompatível (ou com GOP grande demais) e recodificado
isoladamente, sem impedir que os demais continuem em stream copy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

EPSILON_SECONDS = 0.002
MAX_FPS_DELTA = 0.01
FIRST_KEYFRAME_TOLERANCE_SECONDS = 0.500
SUPPORTED_CODECS = {"h264", "hevc"}
SUPPORTED_PIXEL_FORMATS = {"yuv420p"}


@dataclass(frozen=True)
class VideoProfile:
    codec_family: str
    width: int
    height: int
    fps: float
    rotation_degrees: int
    pixel_format: Optional[str]
    sample_aspect_ratio: Optional[str]
    codec_profile: Optional[str]


@dataclass(frozen=True)
class Source:
    duration_seconds: float
    profile: VideoProfile
    keyframes_seconds: List[float]


@dataclass(frozen=True)
class ClipPlan:
    index: int
    copy_video: bool
    body_start_seconds: float
    body_end_seconds: float
    incompatibility_reason: Optional[str] = None

    @property
    def body_duration_seconds(self) -> float:
        return max(0.0, self.body_end_seconds - self.body_start_seconds)


@dataclass(frozen=True)
class JunctionPlan:
    index: int
    outgoing_bridge_start_seconds: float
    outgoing_transition_start_seconds: float
    outgoing_duration_seconds: float
    incoming_transition_end_seconds: float
    incoming_bridge_end_seconds: float


@dataclass(frozen=True)
class Plan:
    target_index: int
    target_profile: VideoProfile
    transition_seconds: float
    fade_in_out: bool
    clips: List[ClipPlan]
    junctions: List[JunctionPlan]
    ineligibility_reason: Optional[str] = None

    @property
    def can_smart_join(self) -> bool:
        return self.ineligibility_reason is None

    def expected_duration_seconds(self, source_duration_seconds: List[float]) -> float:
        total = sum(source_duration_seconds)
        if self.fade_in_out:
            return total
        return total - self.transition_seconds * len(self.junctions)


def _normalize_codec(value: str) -> str:
    text = value.strip().lower()
    if text in {"avc", "h.264", "h264"}:
        return "h264"
    if text in {"hevc", "h.265", "h265"}:
        return "hevc"
    return text


def _normalize_rotation(value: int) -> int:
    return ((value % 360) + 360) % 360


def _normalize_pixel_format(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _normalize_sar(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    return text if text else "1:1"


def _normalize_optional(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip().lower()
    return text if text else None


def video_incompatibility(base: VideoProfile, candidate: VideoProfile) -> Optional[str]:
    if _normalize_codec(base.codec_family) != _normalize_codec(candidate.codec_family):
        return "codec diferente"
    if base.width != candidate.width or base.height != candidate.height:
        return "resolução diferente"
    if abs(base.fps - candidate.fps) > MAX_FPS_DELTA:
        return "framerate diferente"
    if _normalize_rotation(base.rotation_degrees) != _normalize_rotation(candidate.rotation_degrees):
        return "rotação diferente"
    if _normalize_pixel_format(base.pixel_format) != _normalize_pixel_format(candidate.pixel_format):
        return "formato de pixel diferente"
    if _normalize_sar(base.sample_aspect_ratio) != _normalize_sar(candidate.sample_aspect_ratio):
        return "SAR/DAR diferente"
    base_profile = _normalize_optional(base.codec_profile)
    candidate_profile = _normalize_optional(candidate.codec_profile)
    if base_profile is not None and candidate_profile is not None and base_profile != candidate_profile:
        return "perfil do codec diferente"
    return None


def _previous_keyframe(keyframes: List[float], requested: float) -> Optional[float]:
    candidates = [k for k in keyframes if k <= requested + EPSILON_SECONDS]
    return max(candidates) if candidates else None


def _next_keyframe(keyframes: List[float], requested: float) -> Optional[float]:
    candidates = [k for k in keyframes if k + EPSILON_SECONDS >= requested]
    return min(candidates) if candidates else None


def choose_target_index(sources: List[Source]) -> int:
    if not sources:
        return 0

    def compat_sum(candidate: int) -> float:
        total = 0.0
        for index, source in enumerate(sources):
            if video_incompatibility(sources[candidate].profile, source.profile) is None:
                total += source.duration_seconds
        return total

    best_index = 0
    best_score = -1.0
    for candidate in range(len(sources)):
        score = compat_sum(candidate)
        # Kotlin: compareBy{score}.thenByDescending{it} -> em empate o MAIOR
        # indice e considerado MENOR (descending inverte); o max mantem o
        # menor indice.
        if score > best_score or (score == best_score and candidate < best_index):
            best_score = score
            best_index = candidate
    return best_index


def compatible_encoder_names(
    codec_family: str,
    selected_encoder_name: Optional[str],
    encoders: List[Tuple[str, str]],
) -> List[str]:
    codec = _normalize_codec(codec_family)
    candidates = sorted(
        {name for name, family in encoders if _normalize_codec(family) == codec},
        key=lambda name: (0 if name == selected_encoder_name else 1, name),
    )
    return candidates


def junction_duration_seconds(junction: JunctionPlan, fade_in_out: bool) -> float:
    """Duracao da bridge (emenda) recodificada, igual ao smartJoinBridgeDuration do Android."""
    outgoing = junction.outgoing_duration_seconds - junction.outgoing_bridge_start_seconds
    incoming = junction.incoming_bridge_end_seconds
    if fade_in_out:
        return outgoing + incoming
    return outgoing + incoming - junction.incoming_transition_end_seconds


def _rejected_plan(
    sources: List[Source],
    target_index: int,
    transition_seconds: float,
    fade_in_out: bool,
    reason: str,
) -> Plan:
    return Plan(
        target_index=target_index,
        target_profile=sources[target_index].profile,
        transition_seconds=transition_seconds,
        fade_in_out=fade_in_out,
        clips=[
            ClipPlan(index, False, 0.0, source.duration_seconds, reason)
            for index, source in enumerate(sources)
        ],
        junctions=[],
        ineligibility_reason=reason,
    )


def plan(
    sources: List[Source],
    transition_seconds: float,
    fade_in_out: bool,
) -> Plan:
    assert sources, "SmartJoin precisa de ao menos um clipe."
    safe_transition = max(0.0, transition_seconds)
    target_index = choose_target_index(sources)
    target = sources[target_index].profile

    unsupported_reason: Optional[str] = None
    if _normalize_codec(target.codec_family) not in SUPPORTED_CODECS:
        unsupported_reason = f"O codec {target.codec_family} não permite o SmartJoin seguro."
    elif _normalize_pixel_format(target.pixel_format) not in SUPPORTED_PIXEL_FORMATS:
        unsupported_reason = (
            f"O formato de pixel {target.pixel_format or 'desconhecido'} "
            "não pode ser reproduzido com segurança nas emendas."
        )
    elif len(sources) > 1 and any(
        source.duration_seconds <= safe_transition + EPSILON_SECONDS for source in sources
    ):
        unsupported_reason = "A transição ocupa todo o clipe mais curto."
    elif (
        len(sources) > 2
        and safe_transition > 0.0
        and any(
            safe_transition * 2.0 >= source.duration_seconds - EPSILON_SECONDS
            for source in sources[1:-1]
        )
    ):
        unsupported_reason = "As transições de entrada e saída se sobrepõem em um clipe intermediário."
    if unsupported_reason is not None:
        return _rejected_plan(
            sources, target_index, safe_transition, fade_in_out, unsupported_reason
        )

    copy_eligibility: List[Tuple[int, bool, Optional[str]]] = []
    for index, source in enumerate(sources):
        reason = video_incompatibility(target, source.profile)
        # MP4 com edit-list costuma expor o primeiro quadro de vídeo em
        # 100-200 ms, embora esse quadro já seja o primeiro IDR do stream.
        first_kf = source.keyframes_seconds[0] if source.keyframes_seconds else None
        starts_with_keyframe = (
            first_kf is not None and -EPSILON_SECONDS <= first_kf <= FIRST_KEYFRAME_TOLERANCE_SECONDS
        )
        eligible = reason is None and starts_with_keyframe
        if reason is None and not starts_with_keyframe:
            reason = "O primeiro quadro não é um keyframe utilizável."
        copy_eligibility.append((index, eligible, reason))

    def compute_clip_plan(index: int, copy_video: bool, reason: Optional[str]) -> Optional[ClipPlan]:
        source = sources[index]
        desired_start = 0.0 if (index == 0 or safe_transition <= EPSILON_SECONDS) else safe_transition
        desired_end = (
            source.duration_seconds
            if (index == len(sources) - 1 or safe_transition <= EPSILON_SECONDS)
            else source.duration_seconds - safe_transition
        )
        if not copy_video:
            return ClipPlan(index, False, desired_start, desired_end, reason)
        # Sem transição não há margem lógica na emenda: cada clipe precisa
        # contribuir desde o próprio início. Não aplique o primeiro keyframe
        # visível (edit-list), pois isso cortaria o começo dos clipes que
        # entram depois do primeiro.
        if safe_transition <= EPSILON_SECONDS or index == 0:
            body_start = 0.0
        else:
            body_start = _next_keyframe(source.keyframes_seconds, desired_start)
        if safe_transition <= EPSILON_SECONDS or index == len(sources) - 1:
            body_end = source.duration_seconds
        else:
            body_end = _previous_keyframe(source.keyframes_seconds, desired_end)
        if body_start is None or body_end is None or body_start > body_end + EPSILON_SECONDS:
            return None
        return ClipPlan(index, True, body_start, body_end, reason)

    clip_plans: List[ClipPlan] = []
    for index, (_, copy, reason) in enumerate(copy_eligibility):
        computed = compute_clip_plan(index, copy, reason)
        if computed is not None:
            clip_plans.append(computed)
        else:
            clip_plans.append(
                ClipPlan(
                    index=index,
                    copy_video=False,
                    body_start_seconds=0.0 if index == 0 else safe_transition,
                    body_end_seconds=(
                        sources[index].duration_seconds
                        if index == len(sources) - 1
                        else sources[index].duration_seconds - safe_transition
                    ),
                    incompatibility_reason="Os keyframes seguros se cruzam; este clipe será recodificado.",
                )
            )

    # Recalcular depois de desabilitar copy em clips com GOP esparso evita
    # sobreposição entre duas emendas adjacentes.
    clip_plans = [
        clip if clip.copy_video else compute_clip_plan(clip.index, False, clip.incompatibility_reason)
        for clip in clip_plans
    ]

    junctions: List[JunctionPlan] = []
    if safe_transition > EPSILON_SECONDS:
        for index in range(len(sources) - 1):
            outgoing = sources[index]
            junctions.append(
                JunctionPlan(
                    index=index,
                    outgoing_bridge_start_seconds=clip_plans[index].body_end_seconds,
                    outgoing_transition_start_seconds=outgoing.duration_seconds - safe_transition,
                    outgoing_duration_seconds=outgoing.duration_seconds,
                    incoming_transition_end_seconds=safe_transition,
                    incoming_bridge_end_seconds=clip_plans[index + 1].body_start_seconds,
                )
            )

    return Plan(
        target_index=target_index,
        target_profile=target,
        transition_seconds=safe_transition,
        fade_in_out=fade_in_out,
        clips=clip_plans,
        junctions=junctions,
    )
