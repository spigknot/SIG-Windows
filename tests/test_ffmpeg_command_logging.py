from __future__ import annotations

import os
import shlex
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import format_process_command  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
