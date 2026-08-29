from __future__ import annotations

import os
import shlex
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import format_ffmpeg_command_for_log, format_process_command  # noqa: E402


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
        self.assertIn(r"C:\Users\Gustavo\Desktop\test\outros\a.mp4", rendered)

    def test_ffmpeg_display_keeps_paths_after_executable(self):
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
        # Caminhos/argumentos subsequentes continuam citados corretamente.
        self.assertIn(r'"C:\arquivos de trabalho\entrada com espaços.mp4"', rendered)
        self.assertIn(r'"C:\arquivos de trabalho\saida com espaços.mp4"', rendered)

    def test_ffmpeg_display_ffplay_and_ffprobe(self):
        for exe in ("ffplay", "ffprobe"):
            command = [rf"C:\SIG Windows\{exe}.exe", "-version"]
            rendered = format_ffmpeg_command_for_log(command)
            self.assertTrue(rendered.startswith(f"{exe} "), rendered)
            self.assertNotIn(".exe", rendered)

    def test_ffmpeg_display_non_ffmpeg_command_keeps_executable(self):
        command = [r"C:\SIG Windows\outro_tool.exe", "-i", r"C:\arquivo.mp4"]
        rendered = format_ffmpeg_command_for_log(command)
        self.assertTrue(rendered.startswith(r'"C:\SIG Windows\outro_tool.exe"'), rendered)


if __name__ == "__main__":
    unittest.main()
