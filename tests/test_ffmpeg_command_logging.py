from __future__ import annotations

import os
import shlex
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import SigApp, format_ffmpeg_command_for_log, format_ffmpeg_commands_for_log, format_process_command  # noqa: E402


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
        self.assertIn("input.mp4", rendered)
        self.assertNotIn("a.mp4", rendered)
        self.assertNotIn(r"C:\Users\Gustavo", rendered)

    def test_ffmpeg_display_reduces_paths_but_keeps_quoting(self):
        command = [
            r"C:\SIG Windows\ffmpeg.exe",
            "-i",
            r"C:\arquivos de trabalho\entrada com espaços.mp4",
            "-af",
            "afftdn=nf=-25, aresample=16000",
            "-t",
            "4",
            r"C:\arquivos de trabalho\saida com espaços.mp4",
        ]
        rendered = format_ffmpeg_command_for_log(command)
        self.assertTrue(rendered.startswith("ffmpeg "), rendered)
        # Os arquivos viram input/output, mas os filtros seguem citados corretamente.
        self.assertIn("input.mp4", rendered)
        self.assertIn("output.mp4", rendered)
        self.assertIn('"afftdn=nf=-25, aresample=16000"', rendered)
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
        self.assertIn("input.mp4", rendered)
        self.assertNotIn("arquivo.mp4", rendered)
        self.assertNotIn(r"C:\SIG Windows", rendered)

    def test_ffmpeg_display_uses_generic_input_and_output_names(self):
        command = [
            r"C:\SIG Windows\ffmpeg.exe",
            "-hide_banner",
            "-y",
            "-i",
            r"C:\Users\Gustavo\Desktop\nomedovideo.mp4",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            r"C:\Users\Gustavo\Desktop\transcricao_final.wav",
        ]
        expected_parts = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            "input.mp4",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "output.wav",
        ]
        expected = (
            subprocess.list2cmdline(expected_parts)
            if os.name == "nt"
            else shlex.join(expected_parts)
        )
        self.assertEqual(format_ffmpeg_command_for_log(command), expected)

    def test_ffmpeg_display_preserves_original_extensions(self):
        cases = [
            (r"C:\videos\nomedovideo.mkv", r"C:\saida\resultado.mkv", "input.mkv", "output.mkv"),
            (r"C:\audios\entrevista.opus", r"C:\saida\qualquer_nome.opus", "input.opus", "output.opus"),
            (r"C:\videos\clipe.MP4", r"C:\saida\out.MP4", "input.MP4", "output.MP4"),
            (r"C:\videos\filme.mov", r"C:\saida\frame.png", "input.mov", "output.png"),
        ]
        for source, output, expected_input, expected_output in cases:
            with self.subTest(source=source, output=output):
                rendered = format_ffmpeg_command_for_log(
                    [r"C:\SIG Windows\ffmpeg.exe", "-i", source, "-c", "copy", output]
                )
                self.assertIn(expected_input, rendered)
                self.assertIn(expected_output, rendered)

    def test_ffmpeg_display_renames_every_input(self):
        command = [
            r"C:\SIG Windows\ffmpeg.exe",
            "-hide_banner",
            "-i",
            r"C:\midia\principal.mp4",
            "-i",
            r"C:\midia\inserido.wav",
            "-shortest",
            r"C:\midia\final.mp4",
        ]
        rendered = format_ffmpeg_command_for_log(command)
        self.assertIn("input.mp4", rendered)
        self.assertIn("input.wav", rendered)
        self.assertIn("output.mp4", rendered)
        self.assertNotIn("principal", rendered)
        self.assertNotIn("inserido", rendered)

    def test_ffmpeg_display_probe_command_keeps_the_input_as_input(self):
        # Comandos de sondagem terminam na entrada; ela nao deve virar "output".
        command = [r"C:\SIG Windows\ffmpeg.exe", "-hide_banner", "-i", r"C:\midia\video.mp4"]
        rendered = format_ffmpeg_command_for_log(command)
        self.assertIn("input.mp4", rendered)
        self.assertNotIn("output.mp4", rendered)

    def test_ffmpeg_display_keeps_special_outputs_untouched(self):
        for output in ("pipe:1", "-"):
            with self.subTest(output=output):
                command = [
                    r"C:\SIG Windows\ffmpeg.exe",
                    "-hide_banner",
                    "-i",
                    r"C:\midia\video.mp4",
                    "-f",
                    "rawvideo",
                    output,
                ]
                rendered = format_ffmpeg_command_for_log(command)
                self.assertIn("input.mp4", rendered)
                self.assertTrue(rendered.endswith(output), rendered)

    def test_ffmpeg_display_keeps_numeric_arguments_untouched(self):
        rendered = format_ffmpeg_command_for_log(
            [r"C:\SIG Windows\ffmpeg.exe", "-i", r"C:\midia\video.mp4", "-af", "atempo=1.5", r"C:\saida\final.mp4"]
        )
        self.assertIn("atempo=1.5", rendered)
        self.assertNotIn("output.5", rendered)

    def test_ffmpeg_display_does_not_mutate_the_executed_command(self):
        command = [
            r"C:\SIG Windows\ffmpeg.exe",
            "-i",
            r"C:\midia\nomedovideo.mp4",
            r"C:\saida\qualquer_nome.wav",
        ]
        snapshot = list(command)
        format_ffmpeg_command_for_log(command)
        self.assertEqual(command, snapshot)

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


class FfmpegCommandSequenceLoggingTests(unittest.TestCase):
    """Numeração por arquivo e agrupamento de sondas na sequência das ferramentas."""

    def setUp(self):
        self.ffmpeg = r"C:\SIG Windows\ffmpeg.exe"

    @staticmethod
    def _join(tokens: list[str]) -> str:
        return subprocess.list2cmdline(tokens) if os.name == "nt" else shlex.join(tokens)

    def render(self, commands, probes=None):
        return format_ffmpeg_commands_for_log(commands, probes)

    def test_probes_of_distinct_files_are_numbered_sequentially(self):
        entries = self.render(
            [
                [self.ffmpeg, "-hide_banner", "-i", r"C:\videos\um.mp4"],
                [self.ffmpeg, "-hide_banner", "-i", r"C:\videos\dois.mp4"],
                [self.ffmpeg, "-hide_banner", "-i", r"C:\videos\tres.mov"],
            ]
        )
        self.assertEqual(
            [text for text, _probe in entries],
            [
                self._join(["ffmpeg", "-hide_banner", "-i", "input.mp4"]),
                self._join(["ffmpeg", "-hide_banner", "-i", "input2.mp4"]),
                self._join(["ffmpeg", "-hide_banner", "-i", "input3.mov"]),
            ],
        )
        self.assertTrue(all(probe for _text, probe in entries))

    def test_input_numbering_is_positional_and_keeps_each_extension(self):
        command = [
            self.ffmpeg, "-hide_banner", "-y",
            "-i", r"C:\videos\a.avi", "-i", r"C:\videos\b.mp4",
            "-c", "copy", r"C:\saida\junto.mp4",
        ]
        text = self.render([command])[0][0]
        expected = self._join(
            ["ffmpeg", "-hide_banner", "-y", "-i", "input.avi", "-i", "input2.mp4", "-c", "copy", "output.mp4"]
        )
        self.assertEqual(text, expected)

    def test_reused_input_keeps_the_first_label_in_later_commands(self):
        main = r"C:\midia\principal.mp4"
        inserted = r"C:\midia\inserido.wav"
        commands = [
            [self.ffmpeg, "-hide_banner", "-i", main],
            [self.ffmpeg, "-hide_banner", "-y", "-i", main, "-i", inserted, "-shortest", r"C:\saida\resultado.mp4"],
        ]
        texts = [text for text, _probe in self.render(commands)]
        self.assertEqual(
            texts,
            [
                self._join(["ffmpeg", "-hide_banner", "-i", "input.mp4"]),
                self._join(
                    ["ffmpeg", "-hide_banner", "-y", "-i", "input.mp4", "-i", "input2.wav", "-shortest", "output.mp4"]
                ),
            ],
        )

    def test_outputs_are_numbered_across_commands_by_file(self):
        main = r"C:\midia\principal.mp4"
        commands = [
            [self.ffmpeg, "-hide_banner", "-y", "-ss", "0", "-i", main, "-t", "3.000", "-c", "copy", r"C:\saida\000.m4a"],
            [self.ffmpeg, "-hide_banner", "-y", "-ss", "0", "-i", main, "-t", "2.000", "-c", "copy", r"C:\saida\001.m4a"],
        ]
        texts = [text for text, _probe in self.render(commands)]
        self.assertEqual(
            texts,
            [
                self._join(["ffmpeg", "-hide_banner", "-y", "-ss", "0", "-i", "input.mp4", "-t", "3.000", "-c", "copy", "output.m4a"]),
                self._join(["ffmpeg", "-hide_banner", "-y", "-ss", "0", "-i", "input.mp4", "-t", "2.000", "-c", "copy", "output2.m4a"]),
            ],
        )

    def test_structural_probe_detection_without_flag(self):
        # Sondas não marcadas são detectadas pela estrutura (sem arquivo de saída).
        showinfo = [
            self.ffmpeg, "-hide_banner", "-skip_frame", "nokey", "-i", r"C:\videos\um.mp4",
            "-vf", "showinfo", "-an", "-f", "null", "-",
        ]
        real = [self.ffmpeg, "-hide_banner", "-y", "-i", r"C:\videos\um.mp4", "-c", "copy", r"C:\saida\final.mp4"]
        entries = self.render([showinfo, real])
        self.assertTrue(entries[0][1])
        self.assertFalse(entries[1][1])
        self.assertTrue(entries[0][0].endswith("-"))
        # O sumidouro "-" não vira "output" e não consome a numeração de saídas.
        self.assertNotIn("output", entries[0][0])
        self.assertIn("output.mp4", entries[1][0])
        self.assertNotIn("output2", entries[1][0])

    def test_explicit_probe_flag_marks_commands_that_write_a_file(self):
        # O flag explícito vence a heurística: um comando com saída de arquivo
        # marcado como probe não quebra o bloco agrupado.
        command = [self.ffmpeg, "-hide_banner", "-y", "-i", r"C:\videos\um.mp4", "-c", "copy", r"C:\saida\tmp.mp4"]
        entries = self.render([command], probes=[True])
        self.assertTrue(entries[0][1])

    def test_numbering_resets_between_independent_renders(self):
        first = self.render([[self.ffmpeg, "-hide_banner", "-i", r"C:\videos\um.mp4"]])
        second = self.render([[self.ffmpeg, "-hide_banner", "-i", r"C:\videos\dois.mp4"]])
        self.assertIn("input.mp4", first[0][0])
        self.assertIn("input.mp4", second[0][0])
        self.assertNotIn("input2", second[0][0])


if __name__ == "__main__":
    unittest.main()
