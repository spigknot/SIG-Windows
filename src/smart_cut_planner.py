"""Intervalos de SmartCut em timestamps reais, sem arredondar bordas a um GOP."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    frames: int
    copy: bool
    leading: int = 0
    decode_delay: float = 0.0
    decode_seek: float = 0.0
    packet_start: int = 0


@dataclass(frozen=True)
class CutPlan:
    segments: tuple[Segment, ...]
    timestamps: tuple[float, ...]
    first_gap: float
    seek_offset: float
    max_gap: float


def plan(info: dict, start: float, end: float, fps: float) -> CutPlan:
    """Seleciona [start, end); corpos só encerram em fronteiras de GOP seguras.

    Em HEVC aberto, o CRA seguinte pode carregar imagens anteriores ao próprio
    keyframe. Elas pertencem à borda recodificada, não ao corpo em cópia.
    """
    if not all(math.isfinite(x) for x in (start, end, fps)) or fps <= 0 or start < 0 or end <= start:
        raise ValueError("Intervalo ou taxa de quadros inválidos.")
    packets = info.get("packets", [])
    streams = info.get("streams", [])
    if not packets or not streams:
        raise ValueError("Não foi possível identificar os quadros do vídeo.")
    origin = float(streams[0].get("start_time", 0))
    ordered = [float(p.get("pts_time", "nan")) - origin for p in packets]
    if any(not math.isfinite(t) for t in ordered):
        raise ValueError("O vídeo contém timestamps ausentes ou inválidos.")
    times = sorted(t for t, packet in zip(ordered, packets) if "D" not in packet.get("flags", "") and t >= -1e-6)
    if any(not math.isfinite(t) for t in times) or any(b - a < 1e-7 for a, b in zip(times, times[1:])):
        raise ValueError("O vídeo contém timestamps ausentes ou repetidos.")
    eps = 1e-6
    selected = tuple(t for t in times if start - eps <= t < end - eps)
    if not selected:
        raise ValueError("O intervalo não contém quadros; amplie o corte.")
    if not times:
        raise ValueError("O vídeo não contém quadros visíveis.")
    last_packet = next(packet for t, packet in zip(ordered, packets) if t == times[-1] and "D" not in packet.get("flags", ""))
    source_end = times[-1] + float(last_packet.get("duration_time") or 1 / fps)
    keys = [i for i, p in enumerate(packets) if "K" in p.get("flags", "")]
    safe_ends = []
    for n, i in enumerate(keys):
        nxt = keys[n + 1] if n + 1 < len(keys) else len(packets)
        group = ordered[i:nxt]
        delay = max(0.0, float(packets[i]["pts_time"]) - float(packets[i].get("dts_time", packets[i]["pts_time"])))
        if "D" not in packets[i].get("flags", ""):
            safe_ends.append((ordered[i], min(group), sum(t < ordered[i] - eps for t in group), delay))
    last_visible_index = max(i for i, (t, packet) in enumerate(zip(ordered, packets))
                             if "D" not in packet.get("flags", "") and t >= -eps)
    hidden_reference = next((i for i, packet in enumerate(packets)
                             if i < last_visible_index and "D" in packet.get("flags", "") and ordered[i] >= -eps), None)
    repair_start = None
    if hidden_reference is not None:
        group_start = max((i for i in keys if i <= hidden_reference), default=0)
        group_end = next((i for i in keys if i > group_start), len(packets))
        repair_start = max(0.0, min(ordered[group_start:group_end]))
    eligible = [k for k in safe_ends if selected[0] - eps <= k[0] < end - eps]
    body_start = eligible[0][0] if eligible else None
    body_end = None
    if body_start is not None:
        ends = [safe for key, safe, _, _ in safe_ends if key > body_start + eps and key <= end + eps]
        if end >= source_end - eps and repair_start is None:
            ends.append(source_end)
        elif repair_start is not None and end >= repair_start:
            ends = [boundary for boundary in ends if boundary <= repair_start + eps]
            ends.append(repair_start)
        if ends:
            body_end = max(ends)

    def segment(a, b, copy=False, leading=0, delay=0.0):
        count = sum(a - eps <= t < b - eps for t in selected)
        anchor = max((ordered[i] for i in keys if ordered[i] < a - eps), default=0.0)
        packet_start = next((i for i in keys if abs(ordered[i] - a) < eps and "D" not in packets[i].get("flags", "")), 0)
        return Segment(a, b, count, copy, leading, delay, anchor, packet_start)

    segments = []
    if body_end is not None and body_end > body_start + eps:
        if selected[0] < body_start - eps:
            segments.append(segment(selected[0], body_start))
        key = next(k for k in safe_ends if abs(k[0] - body_start) < eps)
        segments.append(segment(body_start, body_end, True, key[2], key[3]))
        if any(t >= body_end - eps for t in selected):
            segments.append(segment(body_end, min(end, source_end)))
    else:
        segments.append(segment(selected[0], min(end, source_end)))
    if any(s.frames <= 0 for s in segments) or sum(s.frames for s in segments) != len(selected):
        raise ValueError("Não foi possível dividir o intervalo em quadros seguros.")
    return CutPlan(tuple(segments), selected, max(0.0, selected[0] - start),
                   origin - float(info.get("format", {}).get("start_time", 0)),
                   max((b - a for a, b in zip(times, times[1:])), default=1 / fps))
