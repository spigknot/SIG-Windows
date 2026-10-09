import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from ffmpeg_recovery import RecoveryJob
from ffmpeg_tools_panel import FfmpegToolsPanel, VideoAcceleration, Cancelled

FF,FP=shutil.which('ffmpeg'),shutil.which('ffprobe')

@unittest.skipUnless(FF and FP,'FFmpeg/FFprobe necessários')
class RecoveryIntegrationTests(unittest.TestCase):
    def panel(self,folder,job):
        p=object.__new__(FfmpegToolsPanel)
        p.output_dir=folder;p.recovery_job=job;p.cancel_event=threading.Event();p.task_tracker=None
        p.acceleration=VideoAcceleration('cpu','CPU','libx264');p.selected_video_quality='Alta';p.selected_video_speed='Equilibrada'
        p._ffmpeg=lambda:Path(FF);p._get_ffprobe=lambda:Path(FP);p._set_status=lambda *a:None
        p.process_lock=threading.Lock();p.app=SimpleNamespace(process_lock=threading.Lock(),active_processes=set())
        p.root=SimpleNamespace(after=lambda *a:None)
        p.commands=[];p.logs=[]
        p._record_ffmpeg_command=lambda command,**kwargs:p.commands.append(command) if not kwargs.get('probe') else None
        p._append_log=lambda text:p.logs.append(text)
        return p

    def test_batch_extraction_resumes_after_first_completed_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);sources=[]
            for index in range(2):
                source=root/f'input-{index}.wav';sources.append(source)
                subprocess.run([FF,'-v','error','-y','-f','lavfi','-i',f'sine=frequency={440+index*440}:sample_rate=48000:duration=1',str(source)],check=True,capture_output=True)
            job=RecoveryJob.create(root/'registry',{'output_dir':str(root)},sources)
            options=dict(extract_extension='wav',extract_start='',extract_end='',extract_rate='48000',extract_channels='1',extract_bitrate='128k')
            def configured(checkpoint):
                p=self.panel(root,checkpoint);p.extract_inputs=sources;p.worker_options=options
                for name in options:setattr(p,name+'_var',SimpleNamespace(get=lambda:None))
                return p
            first=configured(job);execute=first._execute
            def interrupted(command,*args,**kwargs):
                if len(first.commands)==1:raise RuntimeError('simulated process death')
                execute(command,*args,**kwargs)
            first._execute=interrupted
            with self.assertRaisesRegex(RuntimeError,'simulated'):first._extract_worker()
            resumed=configured(RecoveryJob.load(job.journal));resumed._extract_worker()
            self.assertEqual(1,len(resumed.commands));self.assertTrue(any('Retomada:' in line for line in resumed.logs))
            self.assertEqual(2,len(list(root.glob('*_audio*.wav'))))

    def test_finished_cleaning_survives_death_before_completion_message(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'input.wav'
            subprocess.run([FF,'-v','error','-y','-f','lavfi','-i','sine=sample_rate=48000:duration=1',str(source)],check=True,capture_output=True)
            job=RecoveryJob.create(root/'registry',{'output_dir':str(root)},[source])
            def configured(checkpoint):
                p=self.panel(root,checkpoint);p.clean_input=source;p.worker_options={'clean_mode':'equilibrado'}
                p.clean_mode_var=SimpleNamespace(get=lambda:'equilibrado');return p
            first=configured(job);execute=first._execute
            def interrupted(command,*args,**kwargs):
                execute(command,*args,**kwargs);raise RuntimeError('simulated process death')
            first._execute=interrupted
            with self.assertRaisesRegex(RuntimeError,'simulated'):first._clean_worker()
            resumed=configured(RecoveryJob.load(job.journal));resumed._clean_worker()
            self.assertEqual([],resumed.commands);self.assertEqual(1,len(list(root.glob('*_limpo*.wav'))))

    def test_killed_after_all_pieces_resumes_without_reencoding_them(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'input.mp4';output=root/'out.mp4'
            subprocess.run([FF,'-v','error','-y','-f','lavfi','-i','testsrc2=size=128x72:rate=25:duration=6',
                '-f','lavfi','-i','sine=sample_rate=48000:duration=6','-c:v','libx264','-g','50','-sc_threshold','0','-bf','2','-c:a','aac',str(source)],check=True,capture_output=True)
            job=RecoveryJob.create(root/'registry',{'output_dir':str(root)},[source]);p=self.panel(root,job)
            media=p._probe_media(source);execute=p._execute
            def interrupted(command,label,*args,**kwargs):
                if label=='Montando o arquivo final':raise RuntimeError('simulated process death')
                execute(command,label,*args,**kwargs)
            p._execute=interrupted
            with self.assertRaisesRegex(RuntimeError,'simulated'):
                p._cut_video_smartcut(source,output,1.4,4.6,media)
            self.assertTrue(list(job.work_root.rglob('*.ts')))
            resumed=self.panel(root,RecoveryJob.load(job.journal))
            resumed._cut_video_smartcut(source,output,1.4,4.6,media)
            self.assertEqual(len(resumed.commands),1)
            self.assertGreaterEqual(sum('Retomada:' in message for message in resumed.logs),4)
            info=json.loads(subprocess.run([FP,'-v','error','-select_streams','v:0','-show_streams','-of','json',str(output)],check=True,capture_output=True).stdout)
            self.assertEqual(int(info['streams'][0]['nb_frames']),80)
            resumed.recovery_job.finish('complete');self.assertTrue(output.is_file());self.assertFalse(job.work_root.exists())

    def test_complete_file_is_released_with_warning_but_missing_file_and_cancel_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);job=RecoveryJob.create(root/'registry',{'output_dir':str(root)},[]);p=self.panel(root,job)
            staged=job.directory('validation')/'out.wav';staged.write_bytes(b'complete')
            def divergent():raise RuntimeError('audio length 48001/48000 samples')
            p._validate_completed_output(staged,divergent)
            self.assertIn('48001/48000',p.logs[-1]);p._publish_completed_output(staged,root/'out.wav')
            self.assertTrue((root/'out.wav').exists())
            with self.assertRaises(RuntimeError):p._validate_completed_output(root/'missing.wav',divergent)
            p.cancel_event.set()
            with self.assertRaises(Cancelled):p._validate_completed_output(staged,divergent)
