"""Validacao real do SmartJoin hibrido (porta do Android) no Windows.

Roda o _join_worker com a checkbox SmartJoin + transicao xfade de 3s em dois
clipes de 30s (mesmos de test_media_ffmpeg) e confere:
  1. saida existe e dura ~57s (30+30-3)
  2. log contem "SmartJoin" e etapas de corpo/emenda (prova de que NAO
     reencodou o arquivo inteiro: ha etapa de copia de corpo)
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DIST = ROOT / "dist"
sys.path.insert(0, str(SRC))

from sig_app import FfmpegToolsPanel, VideoAcceleration, MediaProfile  # noqa: E402

FFMPEG = DIST / "ffmpeg.exe"
FFPROBE = DIST / "ffprobe.exe"


class FakeApp:
    def __init__(self) -> None:
        self.process_lock = threading.Lock()
        self.active_processes: set = set()
        self.logs: list[str] = []

    def _append_activity_log(self, message: str, tag: str = "", **kwargs) -> None:
        self.logs.append(f"[{tag}] {message}")


class FakeVar:
    def __init__(self, value) -> None:
        self._value = value

    def get(self):
        return self._value

    def set(self, value) -> None:
        self._value = value


class FakeRoot:
    def __init__(self) -> None:
        self._jobs = []

    def after(self, delay, callback, *args):
        self._jobs.append((delay, callback, args))

    def flush(self) -> None:
        jobs, self._jobs = self._jobs, []
        for _delay, cb, args in jobs:
            cb(*args)


def ensure_media() -> list[Path]:
    import subprocess
    media = ROOT / "test_media_ffmpeg"
    media.mkdir(parents=True, exist_ok=True)
    out_paths = []
    for name, has_video, audio_freq in (
        ("clipA_30s.mp4", True, "440"),
        ("clipB_30s.mp4", True, "660"),
    ):
        target = media / name
        if not (target.exists() and target.stat().st_size > 100_000):
            cmd = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y"]
            cmd += ["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=30",
                    "-f", "lavfi", "-i", f"sine=frequency={audio_freq}:sample_rate=44100:duration=30",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(target)]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, timeout=120)
            if res.returncode != 0:
                raise RuntimeError(res.stderr[-400:])
        out_paths.append(target)
    return out_paths


def probe_duration(path: Path) -> float:
    import subprocess
    res = subprocess.run(
        [str(FFPROBE), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, timeout=30,
    )
    out = (res.stdout or "").strip()
    return float(out) if out else -1.0


def make_panel() -> FfmpegToolsPanel:
    app = FakeApp()
    root = FakeRoot()
    out_dir = Path(tempfile.mkdtemp(prefix="sig_smart_join_"))
    panel = object.__new__(FfmpegToolsPanel)
    panel.app = app
    panel.root = root
    panel.running = False
    panel.cancel_event = threading.Event()
    panel.process_lock = threading.Lock()
    panel.current_process = None
    panel.output_dir = out_dir
    panel.status_var = FakeVar("")
    panel.progress_var = FakeVar(0)
    panel.max_progress_seen = 0
    panel.task_tracker = None
    panel.acceleration = VideoAcceleration("cpu", "CPU (fallback)", "libx264")
    panel.available_accelerations = [panel.acceleration]
    panel.selected_video_quality = "Média"
    panel.video_quality_var = FakeVar("Média")
    panel.worker_options: dict = {}
    panel._record_ffmpeg_command = lambda cmd, **kw: print("[cmd]", " ".join(str(c) for c in cmd), "\n")
    panel._set_running_ui = lambda _v: None
    panel._ffmpeg = lambda: FFMPEG
    panel._get_ffprobe = lambda: FFPROBE
    panel._append_log = app._append_activity_log
    # vars usadas pelo _join_worker
    panel.join_inputs = []
    panel.join_reencode_var = FakeVar(False)
    panel.join_smart_var = FakeVar(True)
    panel.join_seconds_var = FakeVar("3")
    panel.join_transition_var = FakeVar("Dissolver")
    panel.join_profile_var = FakeVar("Primeiro clipe")
    panel.join_stream_policy_var = FakeVar("Primeira faixa (MP4)")
    panel.join_audio_policy_var = FakeVar("Preservar áudio e preencher silêncio")
    panel.VIDEO_TRANSITION_CODES = FfmpegToolsPanel.VIDEO_TRANSITION_CODES
    return panel


def run_scenario(label: str, transition: str, seconds: str, clips: list[Path], expect_duration: float | None, expect_fail_contains: str | None = None) -> bool:
    """Roda um cenario do _join_worker com SmartJoin e valida saida/falha."""
    import glob
    panel = make_panel()
    panel.join_inputs = clips
    panel.worker_options.update({
        "join_reencode": False, "join_smart": True,
        "join_transition": transition, "join_seconds": seconds,
        "join_profile": "Primeiro clipe",
        "join_stream_policy": "Primeira faixa (MP4)",
        "join_audio_policy": "Preservar áudio e preencher silêncio",
    })
    print(f"\n=== {label} ===")
    erro: Exception | None = None
    try:
        panel._join_worker()
    except Exception as exc:  # noqa: BLE001
        erro = exc

    log_text = "\n".join(panel.app.logs)
    ok = True
    if expect_fail_contains is not None:
        # cenario deve FALHAR com o motivo esperado, SEM gerar saida
        if erro is None:
            print(f"FALHA: esperava erro contendo '{expect_fail_contains}' mas nao falhou")
            ok = False
        elif expect_fail_contains not in str(erro):
            print(f"FALHA: erro foi '{erro}', esperava conter '{expect_fail_contains}'")
            ok = False
        else:
            print(f"OK: falhou como esperado com: {erro}")
        return ok

    if erro is not None:
        print(f"FALHA: erro inesperado: {erro}")
        for line in panel.app.logs[-10:]:
            print("  log:", line[:200])
        return False

    outputs = sorted(glob.glob(str(panel.output_dir / "videos_juntos*.mp4")))
    if not outputs:
        print("FALHA: nenhum videos_juntos*.mp4 gerado")
        return False
    out = Path(outputs[-1])
    dur = probe_duration(out)
    print(f"Saida: {out.name}")
    print(f"Duracao: {dur:.3f}s (esperado ~{expect_duration}s)")
    ok_dur = abs(dur - expect_duration) <= 0.6 if expect_duration is not None else True
    has_smart = "SmartJoin" in log_text
    has_body_copy = "copiando corpo" in log_text.lower()
    print(f"Duracao OK: {ok_dur} | Log SmartJoin: {has_smart} | Corpo copiado: {has_body_copy}")
    for line in panel.app.logs[-8:]:
        print("  log:", line[:180])
    return ok_dur and has_smart and has_body_copy


def main() -> int:
    clips = ensure_media()
    results = [
        run_scenario("SmartJoin xfade 3s (2x30s)", "Dissolver", "3", clips, 57.0),
    ]
    # fade in/out -> soma (60s)
    results.append(run_scenario("SmartJoin fade in/out 3s (2x30s)", "Fade in/out", "3", clips, 60.0))
    # misto h264+mpeg4: o clipe mpeg4 (incompativel) e recodificado isoladamente,
    # o h264 continua em stream copy - comportamento fiel ao Android
    mpeg = make_mpeg4_clip()
    results.append(run_scenario(
        "SmartJoin misto h264+mpeg4 (incompativel recodificado sozinho)",
        "Dissolver", "1", [clips[0], mpeg],
        39.0,
    ))
    # inviavel: DOIS clipes mpeg4 -> o target escolhido e mpeg4, planner rejeita
    # (SmartJoin so suporta h264/hevc como codec do target)
    results.append(run_scenario(
        "SmartJoin inviavel (2x codec mpeg4)",
        "Dissolver", "3", [mpeg, mpeg],
        expect_duration=None,
        expect_fail_contains="não permite o SmartJoin seguro",
    ))
    ok_all = all(results)
    print(f"\nRESULTADO GERAL: {'OK' if ok_all else 'FALHA'} ({sum(results)}/{len(results)})")
    return 0 if ok_all else 1


def make_mpeg4_clip() -> Path:
    import subprocess
    media = ROOT / "test_media_ffmpeg"
    media.mkdir(parents=True, exist_ok=True)
    target = media / "clipMpeg4_10s.mp4"
    if not (target.exists() and target.stat().st_size > 50_000):
        cmd = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=10",
               "-f", "lavfi", "-i", "sine=frequency=600:sample_rate=44100:duration=10",
               "-c:v", "mpeg4", "-q:v", "5", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(target)]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, timeout=120)
        if res.returncode != 0:
            raise RuntimeError(res.stderr[-400:])
    return target


if __name__ == "__main__":
    sys.exit(main())
