"""Publicação do Smart Insert: saída concluída, aviso e cancelamento.

Contrato atual (ver docs/validation/FFMPEG-RECOVERY-TIMESTAMPS-20261009.md):
- validação divergente de uma saída CONCLUÍDA não bloqueia: o operador recebe
  um aviso (log + messagebox agendado no root) e o arquivo é publicado;
- cancelamento durante a execução continua sendo erro (Cancelled) e o arquivo
  antigo é preservado;
- a pasta temporária da tarefa é limpa nos dois casos.
"""

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from domain_models import Cancelled
from ffmpeg_tools_panel import FfmpegToolsPanel, MediaProfile


class _RootStub:
    """Root de teste: registra callbacks de after() em vez de agendar renders."""

    def __init__(self):
        self.after_calls = []

    def after(self, delay, callback=None):
        self.after_calls.append((delay, callback))
        return 'after-id'


class SmartInsertPublicationTests(unittest.TestCase):
    @staticmethod
    def _profile():
        return MediaProfile(duration=1, width=0, height=0, fps=0, video_bitrate='', audio_bitrate='128k',
                            has_audio=True, audio_rate=48000, audio_channels=1, audio_layout='mono')

    def _panel(self, root, cancelled):
        panel = object.__new__(FfmpegToolsPanel)
        panel.cancel_event = threading.Event()
        panel.root = root
        panel._append_log = MagicMock()
        panel._insert_full_reencode_arguments = lambda *a, **kw: ['ffmpeg', str(a[2])]
        panel._insert_duration = lambda *a: 1
        panel._insert_audio_filter = lambda *a: ('', 96000)
        def execute(command, *args):
            Path(command[-1]).write_bytes(b'unvalidated output')
            if cancelled:
                panel.cancel_event.set()
        panel._execute = execute
        def validate(*args):
            if not cancelled:
                raise RuntimeError('invalid duration')
        panel._insert_validate = validate
        return panel

    def test_failed_validation_warns_and_releases_completed_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'existing.wav'
            output.write_bytes(b'original output')
            root_stub = _RootStub()
            panel = self._panel(root_stub, cancelled=False)
            panel._insert_render_continuous(root / 'main.wav', root / 'middle.wav', output,
                                            self._profile(), .5, 0, 'none', True)
            # Saída concluída é publicada mesmo com divergência de validação...
            self.assertEqual(output.read_bytes(), b'unvalidated output')
            # ...e o aviso é registrado no log e agendado na UI (root.after).
            self.assertTrue(
                any('Arquivo concluído com aviso' in str(chamada) and 'invalid duration' in str(chamada)
                    for chamada in panel._append_log.call_args_list)
            )
            self.assertEqual(len(root_stub.after_calls), 1)
            delay, aviso = root_stub.after_calls[0]
            self.assertEqual(delay, 0)
            with patch('ffmpeg_tools_panel.messagebox.showwarning') as showwarning:
                aviso()
            showwarning.assert_called_once()
            self.assertIn('invalid duration', showwarning.call_args[0][1])
            # Nenhum temporário da tarefa sobra na pasta.
            self.assertEqual(list(root.iterdir()), [output])

    def test_cancellation_preserves_existing_output_and_cleans_temporaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'existing.wav'
            output.write_bytes(b'original output')
            root_stub = _RootStub()
            panel = self._panel(root_stub, cancelled=True)
            with self.assertRaises(Cancelled):
                panel._insert_render_continuous(root / 'main.wav', root / 'middle.wav', output,
                                                self._profile(), .5, 0, 'none', True)
            # Cancelamento preserva o arquivo existente e não gera aviso.
            self.assertEqual(output.read_bytes(), b'original output')
            self.assertFalse(
                any('Arquivo concluído com aviso' in str(chamada)
                    for chamada in panel._append_log.call_args_list)
            )
            self.assertEqual(root_stub.after_calls, [])
            self.assertEqual(list(root.iterdir()), [output])
