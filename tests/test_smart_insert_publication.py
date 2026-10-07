import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from domain_models import Cancelled
from ffmpeg_tools_panel import FfmpegToolsPanel, MediaProfile


class SmartInsertPublicationTests(unittest.TestCase):
    def test_failed_validation_or_cancellation_preserves_existing_output(self):
        for cancelled in (False,True):
            with self.subTest(cancelled=cancelled), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                output=root/'existing.wav'
                output.write_bytes(b'original output')
                panel=object.__new__(FfmpegToolsPanel)
                panel.cancel_event=threading.Event()
                panel._insert_full_reencode_arguments=lambda *a,**kw: ['ffmpeg',str(a[2])]
                panel._insert_duration=lambda *a:1
                panel._insert_audio_filter=lambda *a: ('',96000)
                def execute(command,*args):
                    Path(command[-1]).write_bytes(b'unvalidated output')
                    if cancelled:panel.cancel_event.set()
                panel._execute=execute
                def validate(*args):
                    if not cancelled:raise RuntimeError('invalid duration')
                panel._insert_validate=validate
                profile=MediaProfile(duration=1,width=0,height=0,fps=0,video_bitrate='',audio_bitrate='128k',
                                     has_audio=True,audio_rate=48000,audio_channels=1,audio_layout='mono')
                with self.assertRaises(Cancelled if cancelled else RuntimeError):
                    panel._insert_render_continuous(root/'main.wav',root/'middle.wav',output,profile,.5,0,'none',True)
                self.assertEqual(output.read_bytes(),b'original output')
                self.assertEqual(list(root.iterdir()),[output])
