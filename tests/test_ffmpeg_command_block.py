"""Bloco de comandos FFmpeg exibido sob o botao executar das ferramentas."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import (  # noqa: E402
    FFMPEG_COMMAND_BLOCK_TAG,
    FfmpegTaskTracker,
    SigApp,
)

try:
    import tkinter as tk

    _root = tk.Tk()
    _root.withdraw()
    TK_AVAILABLE = True
except Exception:  # pragma: no cover - ambiente sem display
    TK_AVAILABLE = False


class _RootStub:
    """Substitui o root do app: nao agenda renders e captura a area de transferencia."""

    def __init__(self):
        self.clipboard: list[str] = []

    def after(self, _delay, _callback=None):
        return ""

    def clipboard_clear(self):
        self.clipboard.clear()

    def clipboard_append(self, text):
        self.clipboard.append(text)


class _AppStub:
    def __init__(self, box):
        self.activity_log = box
        self.root = _RootStub()

    @property
    def clipboard_text(self) -> str:
        return "".join(self.root.clipboard)


@unittest.skipUnless(TK_AVAILABLE, "tkinter indisponivel")
class FfmpegCommandBlockTests(unittest.TestCase):
    def setUp(self):
        self.box = tk.Text(_root, height=20, width=120)
        self.app = _AppStub(self.box)
        self.ffmpeg = r"C:\SIG Windows\ffmpeg.exe"
        self.main = r"C:\midia\principal.mp4"
        self.inserted = r"C:\midia\inserido.wav"
        self.output = r"C:\saida\resultado.mp4"
        # Comandos reais (cru, antes da formatacao de exibicao).
        self.render_cmd = [
            self.ffmpeg, "-hide_banner", "-y", "-i", self.main, "-i", self.inserted,
            "-shortest", self.output,
        ]
        self.probe_main = [self.ffmpeg, "-hide_banner", "-i", self.main]
        self.probe_inserted = [self.ffmpeg, "-hide_banner", "-i", self.inserted]
        self.probe_keyframes = [
            self.ffmpeg, "-hide_banner", "-skip_frame", "nokey", "-i", self.main,
            "-vf", "showinfo", "-an", "-f", "null", "-",
        ]
        self.first_piece = [
            self.ffmpeg, "-hide_banner", "-y", "-ss", "0", "-i", self.main,
            "-t", "3.000", "-c", "copy", r"C:\saida\000.m4a",
        ]
        self.second_piece = [
            self.ffmpeg, "-hide_banner", "-y", "-ss", "0", "-i", self.inserted,
            "-t", "2.000", "-c", "copy", r"C:\saida\001.m4a",
        ]

    def tearDown(self):
        self.box.destroy()

    def _render(self, entries: list[tuple[list[object], bool]]) -> str:
        tracker = FfmpegTaskTracker(self.app, [])
        for command, probe in entries:
            tracker.command(command, probe=probe)
        tracker._render()
        return self.box.get("1.0", "end-1c")

    def _lines(self, entries: list[tuple[list[object], bool]]) -> list[str]:
        return self._render(entries).splitlines()

    def test_consecutive_probes_are_grouped_without_blank_lines(self):
        lines = self._lines([(self.probe_main, True), (self.probe_inserted, True)])
        self.assertEqual(lines[0], "")
        self.assertEqual(lines[1], "Comandos FFmpeg:")
        self.assertEqual(lines[2], "$ ffmpeg -hide_banner -i input.mp4")
        # Segundo arquivo novo: numeração continua (sem linha em branco).
        self.assertEqual(lines[3], "$ ffmpeg -hide_banner -i input2.wav")
        self.assertEqual(len(lines), 4)

    def test_structural_probes_group_even_without_flag(self):
        # Sondas sem flag explícita (terminam na entrada ou em sumidouro) são
        # detectadas pela estrutura e agrupadas do mesmo jeito.
        lines = self._lines([(self.probe_keyframes, False), (self.probe_main, False)])
        self.assertEqual(lines[2], "$ ffmpeg -hide_banner -skip_frame nokey -i input.mp4 -vf showinfo -an -f null -")
        self.assertEqual(lines[3], "$ ffmpeg -hide_banner -i input.mp4")
        self.assertEqual(len(lines), 4)

    def test_real_command_after_probes_keeps_blank_separator(self):
        lines = self._lines([(self.probe_main, True), (self.render_cmd, False)])
        self.assertEqual(lines[2], "$ ffmpeg -hide_banner -i input.mp4")
        self.assertEqual(lines[3], "")
        self.assertEqual(
            lines[4],
            "$ ffmpeg -hide_banner -y -i input.mp4 -i input2.wav -shortest output.mp4",
        )

    def test_real_commands_keep_blank_separation(self):
        lines = self._lines([(self.first_piece, False), (self.second_piece, False)])
        self.assertEqual(lines[2], "$ ffmpeg -hide_banner -y -ss 0 -i input.mp4 -t 3.000 -c copy output.m4a")
        self.assertEqual(lines[3], "")
        self.assertEqual(lines[4], "$ ffmpeg -hide_banner -y -ss 0 -i input2.wav -t 2.000 -c copy output2.m4a")

    def test_single_command_has_no_extra_blank_line(self):
        lines = self._lines([(self.render_cmd, False)])
        self.assertEqual(
            lines,
            ["", "Comandos FFmpeg:", "$ ffmpeg -hide_banner -y -i input.mp4 -i input2.wav -shortest output.mp4"],
        )

    def test_click_copies_every_command_of_the_block(self):
        self._render([(self.probe_main, True), (self.probe_inserted, True), (self.render_cmd, False)])
        handler = object.__new__(SigApp)
        handler.root = self.app.root
        self.assertTrue(handler._copy_ffmpeg_command_block(self.box))
        self.assertEqual(
            self.app.clipboard_text,
            "\n".join(
                [
                    "ffmpeg -hide_banner -i input.mp4",
                    "ffmpeg -hide_banner -i input2.wav",
                    "ffmpeg -hide_banner -y -i input.mp4 -i input2.wav -shortest output.mp4",
                ]
            ),
        )

    def test_copy_drops_the_header_the_dollar_prefix_and_blank_lines(self):
        self._render([(self.probe_main, True), (self.render_cmd, False)])
        handler = object.__new__(SigApp)
        handler.root = self.app.root
        handler._copy_ffmpeg_command_block(self.box)
        copied = self.app.clipboard_text
        self.assertNotIn("Comandos FFmpeg", copied)
        self.assertNotIn("$ ", copied)
        self.assertEqual(copied.count("\n\n"), 0)
        self.assertTrue(copied.startswith("ffmpeg "), copied)

    def test_copy_without_a_block_is_a_noop(self):
        self.box.insert("end", "ffmpeg -hide_banner -i input.mp4\n")
        handler = object.__new__(SigApp)
        handler.root = self.app.root
        self.assertFalse(handler._copy_ffmpeg_command_block(self.box))
        self.assertEqual(self.app.clipboard_text, "")

    def test_every_line_of_the_block_shares_the_block_tag(self):
        # Probes agrupadas: 1 linha em branco inicial + cabecalho + 2 comandos.
        self._render([(self.probe_main, True), (self.probe_inserted, True)])
        # O Text do Tk sempre termina com uma quebra de linha extra (fantasma).
        total = int(float(self.box.index("end-1c"))) - 1
        self.assertEqual(total, 4)
        for line in range(1, total + 1):
            index = f"{line}.0"
            with self.subTest(line=line):
                self.assertIn(FFMPEG_COMMAND_BLOCK_TAG, self.box.tag_names(index))


if __name__ == "__main__":
    unittest.main()
