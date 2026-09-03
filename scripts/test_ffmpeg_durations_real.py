"""Harness de teste real do SIG Windows FFmpeg tools.

Exercita os workers REAIS do FfmpegToolsPanel (sig_app.py) contra o
ffmpeg.exe/ffprobe.exe do dist/ (os mesmos binarios que o sig.exe usa),
gera saidas e mede a duracao com ffprobe, comparando com o esperado.
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

from sig_app import FfmpegToolsPanel, VideoAcceleration  # noqa: E402

FFMPEG = DIST / "ffmpeg.exe"
FFPROBE = DIST / "ffprobe.exe"
assert FFMPEG.exists(), f"ffmpeg nao encontrado em {FFMPEG}"
assert FFPROBE.exists(), f"ffprobe nao encontrado em {FFPROBE}"


class FakeApp:
    """Minimo suficiente para os workers (self.app.process_lock/active_processes/_append_activity_log)."""

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
        self._jobs: list = []

    def after(self, delay, callback, *args):
        # executa imediatamente, mas nunca na thread do worker (UI-thread only)
        self._jobs.append((delay, callback, args))

    def flush(self) -> None:
        jobs, self._jobs = self._jobs, []
        for _delay, callback, args in jobs:
            callback(*args)


def make_panel(**overrides) -> FfmpegToolsPanel:
    """Constroi um FfmpegToolsPanel instrumentado (padrao dos testes unitarios)."""
    app = FakeApp()
    root = FakeRoot()
    out_dir = Path(overrides.pop("output_dir", tempfile.mkdtemp(prefix="sig_ffmpeg_test_")))

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

    # helper stubs que dependem de UI nao existente
    panel._record_ffmpeg_command = lambda _cmd, **kw: None
    panel._set_running_ui = lambda _v: None
    # aponta os binarios para o dist/ (mesmos do sig.exe)
    panel._ffmpeg = lambda: FFMPEG
    panel._get_ffprobe = lambda: FFPROBE

    # vars default que os workers consultam
    default_vars = {
        "join_reencode_var": FakeVar(False),
        "join_smart_var": FakeVar(False),
        "join_seconds_var": FakeVar("3"),
        "join_transition_var": FakeVar("Dissolver"),
        "join_profile_var": FakeVar("Primeiro clipe"),
        "join_stream_policy_var": FakeVar("Primeira faixa (MP4)"),
        "join_audio_policy_var": FakeVar("Preservar áudio e preencher silêncio"),
        "cut_mode_var": FakeVar("Preciso (reencodar)"),
        "cut_start_var": FakeVar("5"),
        "cut_end_var": FakeVar("20"),
        "cut_audio_policy_var": FakeVar("Precisão máxima (AAC)"),
        "cut_stream_policy_var": FakeVar("Vídeo e áudio"),
        "extract_extension_var": FakeVar("wav"),
        "extract_start_var": FakeVar(""),
        "extract_end_var": FakeVar(""),
        "extract_rate_var": FakeVar("16000"),
        "extract_channels_var": FakeVar("1"),
        "extract_bitrate_var": FakeVar("128k"),
        "rotate_degrees_var": FakeVar("90"),
        "rotate_start_var": FakeVar(""),
        "rotate_end_var": FakeVar(""),
        "rotate_metadata_var": FakeVar(False),
        "rotate_hflip_var": FakeVar(False),
        "rotate_vflip_var": FakeVar(False),
        "rotate_parallel_var": FakeVar(False),
        "rotate_segments_var": FakeVar(""),
        "insert_transition_var": FakeVar("Sem transição"),
        "insert_seconds_var": FakeVar("0"),
        "insert_reencode_var": FakeVar(False),
        "insert_smart_var": FakeVar(False),
        "clean_mode_var": FakeVar("equilibrado"),
        "clean_output_profile_var": FakeVar("Transcrição (mono, 16 kHz)"),
    }
    for name, value in default_vars.items():
        if not hasattr(panel, name):
            setattr(panel, name, value)

    # opcoes por worker (worker_options tem prioridade sobre as vars)
    panel.worker_options.update(overrides)
    return panel


def run_worker(panel: FfmpegToolsPanel, worker_name: str, inputs: list[Path], extra_options: dict | None = None) -> None:
    """Configura inputs e roda o worker."""
    if extra_options:
        panel.worker_options.update(extra_options)

    worker = getattr(panel, worker_name)
    # cada worker le campos especificos
    if worker_name == "_join_worker":
        panel.join_inputs = inputs
    elif worker_name == "_join_audio_worker":
        panel.join_inputs = inputs
    elif worker_name == "_cut_worker":
        panel.cut_input = inputs[0]
    elif worker_name == "_extract_worker":
        panel.extract_inputs = inputs
    elif worker_name == "_rotate_worker":
        panel.rotate_input = inputs[0]
    elif worker_name == "_insert_worker":
        panel.insert_main_input = inputs[0]
        panel.insert_secondary_input = inputs[1]
        # timeline fake com .insertion (respeita um timeline ja definido)
        if getattr(panel, "insert_timeline", None) is None:
            class FakeTimeline:
                insertion = 10.0
            panel.insert_timeline = FakeTimeline()
    elif worker_name == "_clean_worker":
        panel.clean_input = inputs[0]

    worker()


def probe_duration(path: Path) -> float:
    import subprocess
    res = subprocess.run(
        [str(FFPROBE), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        timeout=30,
    )
    out = (res.stdout or "").strip()
    return float(out) if out else -1.0


def ensure_media() -> tuple[Path, Path, Path]:
    """Garante que as midias de teste (30s exatos) existam, gerando-as com o
    ffmpeg do dist/ quando ausentes."""
    import subprocess
    media = ROOT / "test_media_ffmpeg"
    media.mkdir(parents=True, exist_ok=True)
    clip_a = media / "clipA_30s.mp4"
    clip_b = media / "clipB_30s.mp4"
    aud_a = media / "audA_30s.m4a"

    def gen(target: Path, video_freq: str | None, audio_freq: str, label: str) -> None:
        if target.exists() and target.stat().st_size > 100_000:
            return
        cmd = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y"]
        if video_freq:
            cmd += ["-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration=30",
                    "-f", "lavfi", "-i", f"sine=frequency={audio_freq}:sample_rate=44100:duration=30",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(target)]
        else:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency={audio_freq}:sample_rate=44100:duration=30",
                    "-c:a", "aac", "-b:a", "96k", "-shortest", str(target)]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, timeout=120)
        if res.returncode != 0 or not target.exists():
            raise RuntimeError(f"falha ao gerar midia {label}: {res.stderr[-400:]}")

    gen(clip_a, "30", "440", "clipA")
    gen(clip_b, "30", "660", "clipB")
    gen(aud_a, None, "880", "audA")
    return clip_a, clip_b, aud_a


def find_latest_output(panel: FfmpegToolsPanel, suffix: str) -> Path | None:
    candidates = sorted(panel.output_dir.glob(f"*{suffix}*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def expect(label: str, actual: float, expected: float, tolerance: float = 0.2) -> tuple[bool, str]:
    ok = abs(actual - expected) <= tolerance
    status = "OK " if ok else "FAIL"
    detail = f"{label}: saida={actual:.3f}s esperado={expected:.3f}s (tol {tolerance}s)"
    return ok, f"[{status}] {detail}"


def main() -> None:
    clip_a, clip_b, aud_a = ensure_media()

    results: list[tuple[bool, str]] = []
    summaries: list[str] = []

    # ============================================================
    # 1. JUNTAR VIDEOS - sem reencodar (concat) -> 60s
    # ============================================================
    p = make_panel()
    run_worker(p, "_join_worker", [clip_a, clip_b],
               extra_options={"join_reencode": False, "join_smart": False,
                              "join_transition": "Sem transição", "join_seconds": "0"})
    out = find_latest_output(p, "videos_juntos")
    assert out, "join concat sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Juntar vídeos sem reencodar (concat, 2x30s)", dur, 60.0)
    results.append((ok, msg)); summaries.append(f"JUNTAR concat sem transicao -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 2. JUNTAR VIDEOS - Reencode completo + xfade 3s -> 57s
    # ============================================================
    p = make_panel()
    run_worker(p, "_join_worker", [clip_a, clip_b],
               extra_options={"join_reencode": True, "join_smart": False,
                              "join_transition": "Dissolver", "join_seconds": "3"})
    out = find_latest_output(p, "videos_juntos")
    assert out, "join xfade sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Juntar vídeos Reencode + xfade 3s (2x30s)", dur, 57.0)
    results.append((ok, msg)); summaries.append(f"JUNTAR reencode xfade 3s -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 3. JUNTAR VIDEOS - Reencode + Fade in/out 3s -> 60s (fade nao subtrai)
    # ============================================================
    p = make_panel()
    run_worker(p, "_join_worker", [clip_a, clip_b],
               extra_options={"join_reencode": True, "join_smart": False,
                              "join_transition": "Fade in/out", "join_seconds": "3"})
    out = find_latest_output(p, "videos_juntos")
    assert out, "join fade sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Juntar vídeos Reencode + Fade in/out 3s (2x30s)", dur, 60.0)
    results.append((ok, msg)); summaries.append(f"JUNTAR reencode fade 3s -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 4. CORTAR video preciso 5..20s -> 15s
    # ============================================================
    p = make_panel()
    run_worker(p, "_cut_worker", [clip_a],
               extra_options={"cut_start": "5", "cut_end": "20",
                              "cut_mode": "Preciso (reencodar)"})
    out = find_latest_output(p, "_cortado")
    assert out, "corte sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Cortar vídeo preciso 5-20s", dur, 15.0)
    results.append((ok, msg)); summaries.append(f"CORTAR preciso 5-20s -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 5. EXTRAIR audio (sem trim) -> 30s
    # ============================================================
    p = make_panel()
    run_worker(p, "_extract_worker", [clip_a],
               extra_options={"extract_extension": "wav", "extract_rate": "16000",
                              "extract_channels": "1", "extract_bitrate": "128k",
                              "extract_start": "", "extract_end": ""})
    out = find_latest_output(p, "_audio")
    assert out, "extract sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Extrair áudio do vídeo 30s", dur, 30.0)
    results.append((ok, msg)); summaries.append(f"EXTRAIR audio 30s -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 6. GIRAR video 90 graus (reencode, sem trim) -> 30s
    # ============================================================
    p = make_panel()
    run_worker(p, "_rotate_worker", [clip_a],
               extra_options={"rotate_degrees": "90", "rotate_metadata": False,
                              "rotate_hflip": False, "rotate_vflip": False,
                              "rotate_parallel": False,
                              "rotate_start": "0", "rotate_end": "30"})
    out = find_latest_output(p, "_girado")
    assert out, "rotate sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Girar vídeo 90° (reencode)", dur, 30.0)
    results.append((ok, msg)); summaries.append(f"GIRAR 90 reencode -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 7. LIMPAR audio -> 30s
    # ============================================================
    p = make_panel()
    run_worker(p, "_clean_worker", [aud_a],
               extra_options={"clean_mode": "equilibrado"})
    out = find_latest_output(p, "_limpo")
    assert out, "clean sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Limpar áudio 30s (afftdn)", dur, 30.0)
    results.append((ok, msg)); summaries.append(f"LIMPAR audio -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 8. INSERIR audio (copy/sem reencode, ponto 10s, sem transicao) -> 60s
    # ============================================================
    p = make_panel()
    run_worker(p, "_insert_worker", [aud_a, aud_a],
               extra_options={"insert_transition": "Sem transição", "insert_seconds": "0",
                              "insert_reencode": False, "insert_smart": False})
    out = find_latest_output(p, "_com_audio")
    assert out, "insert sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Inserir áudio 30s em 30s (sem transição)", dur, 60.0)
    results.append((ok, msg)); summaries.append(f"INSERIR audio (copy, sem transicao) -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 9. INSERIR audio Reencode Completo + crossfade Linear 2s no MEIO (t=10)
    #    -> 2 fronteiras (10s + 20s do main e 30s do insert), cada uma subtrai 2s
    #    saida = 30 + 30 - 2 - 2 = 56s
    # ============================================================
    p = make_panel()
    # FakeTimeline com insertion=10.0 no run_worker -> main dividido em [0,10]+[10,30]
    run_worker(p, "_insert_worker", [aud_a, aud_a],
               extra_options={"insert_transition": "Linear", "insert_seconds": "2",
                              "insert_reencode": True, "insert_smart": False})
    out = find_latest_output(p, "_com_audio")
    assert out, "insert crossfade sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Inserir áudio crossfade Linear 2s no meio (30+30-2-2)", dur, 56.0)
    results.append((ok, msg)); summaries.append(f"INSERIR audio reencode crossfade 2s meio -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 9b. INSERIR audio Reencode Completo + crossfade Linear 2s no INICIO (t=0)
    #    -> 1 fronteira (main inteiro + insert), subtrai 2s -> 58s
    # ============================================================
    p = make_panel()
    class FakeTimelineStart:
        insertion = 0.0
    p.insert_timeline = FakeTimelineStart()
    run_worker(p, "_insert_worker", [aud_a, aud_a],
               extra_options={"insert_transition": "Linear", "insert_seconds": "2",
                              "insert_reencode": True, "insert_smart": False})
    out = find_latest_output(p, "_com_audio")
    assert out, "insert crossfade inicio sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Inserir áudio crossfade Linear 2s no início (30+30-2)", dur, 58.0)
    results.append((ok, msg)); summaries.append(f"INSERIR audio reencode crossfade 2s inicio -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 10. JUNTAR AUDIOS sem reencodar (concat) 2x30s -> 60s
    # ============================================================
    p = make_panel()
    run_worker(p, "_join_worker", [aud_a, aud_a],
               extra_options={"join_reencode": False, "join_smart": False,
                              "join_transition": "Sem transição", "join_seconds": "0"})
    out = find_latest_output(p, "audios_juntos")
    assert out, "join audio sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Juntar áudios sem reencodar (concat, 2x30s)", dur, 60.0)
    results.append((ok, msg)); summaries.append(f"JUNTAR AUDIOS concat -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 11. JUNTAR AUDIOS Reencode + crossfade Linear 2s -> 58s
    # ============================================================
    p = make_panel()
    run_worker(p, "_join_worker", [aud_a, aud_a],
               extra_options={"join_reencode": True, "join_smart": False,
                              "join_transition": "Linear", "join_seconds": "2"})
    out = find_latest_output(p, "audios_juntos")
    assert out, "join audio xfade sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Juntar áudios Reencode + crossfade 2s (2x30s)", dur, 58.0)
    results.append((ok, msg)); summaries.append(f"JUNTAR AUDIOS reencode crossfade 2s -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 12. GIRAR VIDEO somente metadados 90 (sem trim) -> 30s
    # ============================================================
    p = make_panel()
    run_worker(p, "_rotate_worker", [clip_a],
               extra_options={"rotate_degrees": "90", "rotate_metadata": True,
                              "rotate_hflip": False, "rotate_vflip": False,
                              "rotate_parallel": False,
                              "rotate_start": "0", "rotate_end": "30"})
    out = find_latest_output(p, "_girado")
    assert out, "rotate metadata sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Girar vídeo 90° metadados (sem trim)", dur, 30.0)
    results.append((ok, msg)); summaries.append(f"GIRAR metadata 90 -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 13. GIRAR VIDEO reencode 90 com TRIM 5..20 -> 15s
    # ============================================================
    p = make_panel()
    run_worker(p, "_rotate_worker", [clip_a],
               extra_options={"rotate_degrees": "90", "rotate_metadata": False,
                              "rotate_hflip": False, "rotate_vflip": False,
                              "rotate_parallel": False,
                              "rotate_start": "5", "rotate_end": "20"})
    out = find_latest_output(p, "_girado_cortado")
    assert out, "rotate trim sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Girar vídeo 90° com trim 5-20s", dur, 15.0)
    results.append((ok, msg)); summaries.append(f"GIRAR reencode trim 5-20 -> {dur:.3f}s")
    print(msg)

    # ============================================================
    # 14. CORTE RAPIDO (stream copy) 5..20 -> ~15s
    # ============================================================
    p = make_panel()
    run_worker(p, "_cut_worker", [clip_a],
               extra_options={"cut_start": "5", "cut_end": "20",
                              "cut_mode": "Rápido (sem reencodar)"})
    out = find_latest_output(p, "_cortado")
    assert out, "corte rapido sem saida"
    dur = probe_duration(out)
    ok, msg = expect("Cortar vídeo rápido (copy) 5-20s", dur, 15.0, tolerance=0.5)
    results.append((ok, msg)); summaries.append(f"CORTAR rapido 5-20 -> {dur:.3f}s")
    print(msg)

    print("\n" + "=" * 60)
    total_ok = sum(1 for ok, _ in results if ok)
    print(f"RESUMO: {total_ok}/{len(results)} cenários OK")
    for ok, msg in results:
        print(("  PASS  " if ok else "  **FAIL** ") + msg)

    # salva o resultado cru da execucao (nao sobrescreve o relatorio do repo)
    report = Path(tempfile.gettempdir()) / f"sig_ffmpeg_durations_{int(time.time())}.txt"
    lines = [
        "RESULTADO DA EXECUCAO - DURACOES DE SAIDA FFMPEG (SIG Windows)",
        f"Gerado por: {Path(__file__).name} em {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "Metodo: workers reais de sig_app.py + ffmpeg.exe/ffprobe.exe do dist/",
        "Midias: clipA_30s.mp4, clipB_30s.mp4, audA_30s.m4a (30.000s cada)",
        "",
        *[f"{'PASS' if ok else 'FAIL'}: {msg}" for ok, msg in results],
        "",
        f"Total: {total_ok}/{len(results)} OK",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResultado cru salvo: {report}")

    return 0 if total_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
