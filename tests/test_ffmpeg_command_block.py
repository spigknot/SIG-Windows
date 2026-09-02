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
        self.first = "ffmpeg -hide_banner -y -i input.mkv -vn -ac 1 -ar 16000 -c:a pcm_s16le output.wav"
        self.second = "ffmpeg -hide_banner -y -i input.mkv -c copy output.mkv"
        self.third = "ffmpeg -hide_banner -i input.mp4"

    def tearDown(self):
        self.box.destroy()

    def _render(self, commands: list[str]) -> str:
        tracker = FfmpegTaskTracker(self.app, [])
        for command in commands:
            tracker.command(command)
        tracker._render()
        return self.box.get("1.0", "end-1c")

    def test_block_omits_directories_and_uses_generic_names(self):
        # A reducao a input./output. acontece em format_ffmpeg_command_for_log,
        # garantida aqui com um comando ja renderizado realistico.
        rendered = self._render([self.first, self.second])
        self.assertIn("input.mkv", rendered)
        self.assertIn("output.wav", rendered)
        self.assertIn("output.mkv", rendered)
        self.assertNotIn("C:\\", rendered)
        self.assertNotIn("\\Users\\", rendered)

    def test_multiple_commands_are_separated_by_a_blank_line(self):
        rendered = self._render([self.first, self.second, self.third])
        lines = rendered.splitlines()
        self.assertEqual(lines[0], "")
        self.assertEqual(lines[1], "Comandos FFmpeg:")
        self.assertEqual(lines[2], f"$ {self.first}")
        self.assertEqual(lines[3], "")
        self.assertEqual(lines[4], f"$ {self.second}")
        self.assertEqual(lines[5], "")
        self.assertEqual(lines[6], f"$ {self.third}")

    def test_single_command_has_no_extra_blank_line(self):
        rendered = self._render([self.first])
        self.assertEqual(
            rendered.splitlines(),
            ["", "Comandos FFmpeg:", f"$ {self.first}"],
        )

    def test_click_copies_every_command_of_the_block(self):
        self._render([self.first, self.second, self.third])
        handler = object.__new__(SigApp)
        handler.root = self.app.root
        self.assertTrue(handler._copy_ffmpeg_command_block(self.box))
        self.assertEqual(
            self.app.clipboard_text,
            "\n".join([self.first, self.second, self.third]),
        )

    def test_copy_drops_the_header_the_dollar_prefix_and_blank_lines(self):
        self._render([self.first, self.second])
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
        # Inclusive o cabecalho e a linha em branco: clicar em qualquer ponto
        # do bloco precisa copiar todos os comandos.
        self._render([self.first, self.second])
        # O Text do Tk sempre termina com uma quebra de linha extra (fantasma).
        total = int(float(self.box.index("end-1c"))) - 1
        self.assertEqual(total, 5)
        for line in range(1, total + 1):
            index = f"{line}.0"
            with self.subTest(line=line):
                self.assertIn(FFMPEG_COMMAND_BLOCK_TAG, self.box.tag_names(index))


if __name__ == "__main__":
    unittest.main()
