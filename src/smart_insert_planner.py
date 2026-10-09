"""Plano de inserção por amostras, com emendas de cópia apenas em áudio lossless."""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class InsertPlan:
    rate: int
    main_samples: int
    inserted_samples: int
    insertion: int
    left: int
    right: int
    prefix_packets: int
    suffix_packets: int
    seek_offset: float = 0.0
    head_end: int = 0
    tail_start: int = 0

    @property
    def total_samples(self):
        return self.main_samples + self.inserted_samples


def audio_duration(info: dict, fallback: float) -> float:
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        raise ValueError("A mídia não contém áudio.")
    stream = streams[0]
    value = (float(Fraction(stream["time_base"]) * int(stream["duration_ts"]))
             if stream.get("duration_ts") is not None and stream.get("time_base") else
             float(stream.get("duration") or info.get("format", {}).get("duration") or fallback))
    if stream.get("codec_name") == "opus":
        # O granule position de Ogg inclui o pre-skip do decoder.
        skip = sum(int(s.get("skip_samples", 0)) for p in info.get("packets", [])[:1]
                   for s in p.get("side_data_list", []))
        value -= skip / int(stream.get("sample_rate") or 48000)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Não foi possível identificar a duração do áudio.")
    return value


def plan(info: dict, main_duration: float, inserted_duration: float, insertion: float, rate: int,
         minimum_bridge: int = 0) -> InsertPlan:
    if rate <= 0 or not all(math.isfinite(x) for x in (main_duration, inserted_duration, insertion)):
        raise ValueError("Duração ou ponto de inserção inválidos.")
    main = round(main_duration * rate)
    middle = round(inserted_duration * rate)
    cut = max(0, min(round(insertion * rate), main))
    if main <= 0 or middle <= 0:
        raise ValueError("O áudio não contém amostras suficientes.")
    packets = info.get("packets", [])
    stream = info["streams"][0]
    origin = float(stream.get("start_time") or 0)
    starts = [round((float(p["pts_time"]) - origin) * rate) for p in packets]
    ends = [a + round(float(p.get("duration_time") or 0) * rate) for a, p in zip(starts, packets)]
    end_tolerance = math.ceil(rate / 1000) if stream.get("codec_name") == "alac" else 0
    if (not starts or starts[0] > 0 or ends[-1] < main - end_tolerance or
        any(b <= a for a, b in zip(starts, ends)) or
        any(a != b for a, b in zip(ends[:-1], starts[1:]))):
        raise ValueError("Os pacotes não formam uma sequência contínua de amostras.")
    head = next((b for a,b in zip(starts,ends) if a < 0 < b), 0)
    tail = next((a for a,b in zip(starts,ends) if a < main < b), main)
    if ends[-1] < main:
        tail = starts[-1]
    head, tail = min(main, head), max(0, tail)
    boundaries = sorted({0, main, *(a for a in starts if 0 < a < main)})
    left = max(t for t in boundaries if t <= cut)
    right = min(t for t in boundaries if t >= cut)
    if cut < head:
        right = max(right, head)
    if cut > tail:
        left = min(left, tail)
    if minimum_bridge:
        if left == main and main - starts[-1] < minimum_bridge:
            left = starts[-1]
        if right - left + middle < minimum_bridge:
            if right < main:
                right = min(t for t in boundaries if t > right)
            elif left:
                left = max(t for t in boundaries if t < left)
    head, tail = min(head, left), max(tail, right)
    return InsertPlan(rate, main, middle, cut, left, right,
                      sum(head <= a < left and b <= main for a,b in zip(starts,ends)),
                      sum(right <= a and b <= tail for a,b in zip(starts,ends)),
                      origin - float(info.get("format", {}).get("start_time") or 0), head, tail)
