from __future__ import annotations

import os
import shlex
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import SigApp, format_ffmpeg_command_for_log, format_process_command  # noqa: E402


class FfmpegCommandLoggingTests(unittest.TestCase):
    def test_command_formatter_preserves_argument_boundaries(self):
        command = [
            r"C:\SIG Windows\ffmpeg.exe",
            "-filter_complex",
            "[0:a]aresample=16000, aformat=sample_rates=16000[aout]",
            r"C:\arquivos de trabalho\saida.wav",
        ]
        expected = (
            subprocess.list2cmdline([str(part) for part in command])
            if os.name == "nt"
            else shlex.join([str(part) for part in command])
        )
        self.assertEqual(format_process_command(command), expected)

    def test_ffmpeg_display_omits_executable_path_and_extension(self):
        command = [
            r"D:\Projetos\SIG Windows\dist\ffmpeg.exe",
            "-hide_banner",
            "-i",
            r"C:\Users\Gustavo\Desktop\test\outros\a.mp4",
        ]
        rendered = format_ffmpeg_command_for_log(command)
        self.assertTrue(rendered.startswith("ffmpeg "), rendered)
        self.assertNotIn(".exe", rendered)
        self.assertNotIn(r"D:\Projetos", rendered)
        self.assertIn("-hide_banner", rendered)
        self.assertIn("a.mp4", rendered)
        self.assertNotIn(r"C:\Users\Gustavo", rendered)

    def test_ffmpeg_display_reduces_paths_but_keeps_quoting(self):
        command = [
            r"C:\SIG Windows\ffmpeg.exe",
            "-i",
            r"C:\arquivos de trabalho\entrada com espaços.mp4",
            "-t",
            "4",
            r"C:\arquivos de trabalho\saida com espaços.mp4",
        ]
        rendered = format_ffmpeg_command_for_log(command)
        self.assertTrue(rendered.startswith("ffmpeg "), rendered)
        # Os caminhos reduzem ao nome base, mas seguem citados corretamente.
        self.assertIn('"entrada com espaços.mp4"', rendered)
        self.assertIn('"saida com espaços.mp4"', rendered)
        self.assertNotIn(r"C:\arquivos de trabalho", rendered)

    def test_ffmpeg_display_ffplay_and_ffprobe(self):
        for exe in ("ffplay", "ffprobe"):
            command = [rf"C:\SIG Windows\{exe}.exe", "-version"]
            rendered = format_ffmpeg_command_for_log(command)
            self.assertTrue(rendered.startswith(f"{exe} "), rendered)
            self.assertNotIn(".exe", rendered)

    def test_ffmpeg_display_non_ffmpeg_command_uses_basename(self):
        command = [r"C:\SIG Windows\outro_tool.exe", "-i", r"C:\arquivo.mp4"]
        rendered = format_ffmpeg_command_for_log(command)
        self.assertTrue(rendered.startswith("outro_tool.exe"), rendered)
        self.assertIn("arquivo.mp4", rendered)
        self.assertNotIn(r"C:\SIG Windows", rendered)

    def test_ffmpeg_error_reason_no_audio_stream(self):
        # Vídeo sem faixa de áudio: o FFmpeg não gera nenhuma stream de saída.
        log = Path(self._tempdir) / "sem_audio.ffmpeg.log"
        log.write_text(
            "Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'D:\\\\x\\\\VID.mp4':\n"
            "  Stream #0:0[0x1](und): Video: h264 (Baseline), 480x848, 29.80 fps\n"
            "Output #0, wav, to 'C:\\\\Program Files\\\\SIG\\\\temp\\\\audios\\\\VID.wav':\n"
            "[out#0/wav @ 00000244f5ae2f00] Output file does not contain any stream\n"
            "Error opening output file C:\\\\Program Files\\\\SIG\\\\temp\\\\audios\\\\VID.wav.\n"
            "Error opening output files: Invalid argument\n",
            encoding="utf-8",
        )
        self.assertEqual(
            SigApp._ffmpeg_error_reason(log),
            " — o arquivo não possui faixa de áudio",
        )

    def test_ffmpeg_error_reason_generic(self):
        log = Path(self._tempdir) / "erro_generico.ffmpeg.log"
        log.write_text(
            "[out#0/mp4 @ 00000244f5ae2f00] Error opening output file: Invalid argument\n",
            encoding="utf-8",
        )
        reason = SigApp._ffmpeg_error_reason(log)
        self.assertIn("Invalid argument", reason)

    def test_ffmpeg_error_reason_missing_file(self):
        self.assertEqual(SigApp._ffmpeg_error_reason(Path(self._tempdir) / "nao_existe.log"), "")

    def test_conversion_failure_status_sem_audio(self):
        exc = RuntimeError("FFmpeg retornou código 1 — o arquivo não possui faixa de áudio")
        self.assertEqual(SigApp._conversion_failure_status(exc), "Sem audio")

    def test_conversion_failure_status_erro_geral(self):
        exc = RuntimeError("FFmpeg retornou código 1")
        self.assertEqual(SigApp._conversion_failure_status(exc), "Erro na conversão")

    def test_job_size_column_shows_original_only_before_conversion(self):
        from sig_app import AudioJob

        original = Path(self._tempdir) / "audio.mp3"
        original.write_bytes(b"x" * (2523 * 1024))
        job = AudioJob(original_path=original, original_name=original.name, stem="audio", mode="ready")
        self.assertEqual(SigApp._job_size_column_text(object.__new__(SigApp), job), "2523 KB")

    def test_job_size_column_shows_arrow_after_conversion(self):
        from sig_app import AudioJob

        original = Path(self._tempdir) / "audio.mp3"
        original.write_bytes(b"x" * (2523 * 1024))
        converted = Path(self._tempdir) / "audio.wav"
        converted.write_bytes(b"x" * (786 * 1024))
        job = AudioJob(original_path=original, original_name=original.name, stem="audio", mode="ready")
        job.upload_path = converted
        self.assertEqual(SigApp._job_size_column_text(object.__new__(SigApp), job), "2523 KB -> 786 KB")

    def test_job_size_column_no_arrow_when_same_size(self):
        from sig_app import AudioJob

        original = Path(self._tempdir) / "audio.mp3"
        original.write_bytes(b"x" * (100 * 1024))
        converted = Path(self._tempdir) / "audio.wav"
        converted.write_bytes(b"x" * (100 * 1024))
        job = AudioJob(original_path=original, original_name=original.name, stem="audio", mode="ready")
        job.upload_path = converted
        self.assertEqual(SigApp._job_size_column_text(object.__new__(SigApp), job), "100 KB")

    def setUp(self):
        import tempfile
        self._tempdir = tempfile.mkdtemp(prefix="sig_ffmpeg_log_")


if __name__ == "__main__":
    unittest.main()
