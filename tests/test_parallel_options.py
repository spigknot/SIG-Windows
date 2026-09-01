"""Verificação do paralelismo real: o valor escolhido na slidebar (configurações)
vira max_workers do ThreadPoolExecutor — converte/transcreve de fato N arquivos
ao mesmo tempo.

- _run_conversions usa settings["convert_parallel"] como max_workers.
- _run_transcriptions (fluxo normal, não-Grok) usa settings["transcribe_parallel"].
- O teste "ao vivo" mede o tempo de parede com jobs que dormem: N jobs com
  paralelismo P levam ~ceil(N/P) lotes.
"""
import concurrent.futures
import os
import queue
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sig_app import SigApp, AudioJob, cpu_parallel_options, default_parallelism  # noqa: E402


class CpuParallelOptionsTest(unittest.TestCase):
    # A fórmula antiga (n/2, n, 2n, 4n) ficou órfã no código após a mudança
    # para slidebars 1..2n, mas segue testada para não quebrar sem aviso.
    def test_six_cores(self):
        self.assertEqual(cpu_parallel_options(6), [3, 6, 12, 24])

    def test_xeon_eighteen_cores(self):
        self.assertEqual(cpu_parallel_options(18), [9, 18, 36, 72])


class DefaultParallelismTest(unittest.TestCase):
    """n/2 com tratamento inteligente para número ímpar de núcleos."""

    def test_single_core_never_zero(self):
        # n/2 = 0.5 -> nunca pode ser 0 (sem paralelismo quebraria o executor).
        self.assertEqual(default_parallelism(1), 1)

    def test_three_cores_rounds_up(self):
        # n/2 = 1.5 -> 2 (não 1, que perderia metade do poder).
        self.assertEqual(default_parallelism(3), 2)

    def test_five_cores_rounds_up(self):
        # n/2 = 2.5 -> 3.
        self.assertEqual(default_parallelism(5), 3)

    def test_even_cores_exact_half(self):
        self.assertEqual(default_parallelism(18), 9)
        self.assertEqual(default_parallelism(4), 2)
        self.assertEqual(default_parallelism(2), 1)


class ParallelExecutorTest(unittest.TestCase):
    """Prova que o número escolhido nas slidebars controla o paralelismo real."""

    def _app(self):
        app = object.__new__(SigApp)
        app.cancel_event = threading.Event()
        app._prepare_started = time.perf_counter()
        app._phase_throttle = None
        app._suppress_ffmpeg_command_log = False
        app.ui_queue = queue.Queue()
        return app

    def _capture_executor(self):
        captured = {}
        real_tpe = concurrent.futures.ThreadPoolExecutor

        def fake_tpe(max_workers=None, **kwargs):
            captured["max_workers"] = max_workers
            return real_tpe(max_workers=max_workers, **kwargs)

        return captured, fake_tpe

    def test_convert_parallel_becomes_executor_workers(self):
        captured, fake_tpe = self._capture_executor()
        with mock.patch.object(
            sig_app_module().concurrent.futures, "ThreadPoolExecutor", fake_tpe
        ):
            self._app()._run_conversions([], {"convert_parallel": 7})
        self.assertEqual(captured.get("max_workers"), 7)

    def test_transcribe_parallel_becomes_executor_workers(self):
        captured, fake_tpe = self._capture_executor()
        job = AudioJob(
            original_path=Path("a.wav"),
            original_name="a.wav",
            stem="a",
            mode="ready",
            upload_path=Path("a.wav"),
        )
        with mock.patch.object(
            sig_app_module().concurrent.futures, "ThreadPoolExecutor", fake_tpe
        ), mock.patch.object(SigApp, "_transcribe_job", return_value=None), mock.patch(
            "sig_app.transcribe_url", return_value="http://teste"
        ), mock.patch("sig_app.is_grok_transcription", return_value=False):
            self._app()._run_transcriptions(
                [job], {"transcribe_parallel": 5, "transcription_server": "servidor"}
            )
        self.assertEqual(captured.get("max_workers"), 5)

    def test_parallelism_wall_clock_proof(self):
        """N jobs com paralelismo P levam ~ceil(N/P) lotes de SLEEP segundos."""
        import tempfile

        sleep = 0.2
        tmp = Path(tempfile.mkdtemp(prefix="sig_par_test_"))
        jobs = []
        for i in range(8):
            path = tmp / f"a{i}.mp3"
            path.write_bytes(b"x" * 1024)
            jobs.append(
                AudioJob(
                    original_path=path,
                    original_name=path.name,
                    stem=f"a{i}",
                    mode="ready",
                    upload_path=path,
                )
            )
        with mock.patch.object(
            SigApp, "_convert_job", side_effect=lambda job: time.sleep(sleep)
        ):
            app = self._app()
            started = time.perf_counter()
            app._run_conversions(jobs, {"convert_parallel": 4})
            elapsed = time.perf_counter() - started
        # 8 jobs / 4 paralelos = 2 lotes (~0.4s). Folga ampla para CI lenta,
        # mas garante que NÃO rodou serial (8 lotes = ~1.6s).
        self.assertLess(elapsed, sleep * 5, f"conversão serial demais: {elapsed:.2f}s")


def sig_app_module():
    import sig_app

    return sig_app


if __name__ == "__main__":
    unittest.main()
