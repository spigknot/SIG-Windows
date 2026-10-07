"""Inserção real: precisão, cópia dos corpos, fades, codec e seek do FLAC."""
from __future__ import annotations
import json
import array
import wave
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from ffmpeg_tools_panel import FfmpegToolsPanel

FF, FP=shutil.which('ffmpeg'),shutil.which('ffprobe')
class Var:
    def __init__(self,value):self.value=value
    def get(self):return self.value
class Timeline:
    def __init__(self,insertion):self.insertion=insertion

@unittest.skipUnless(FF and FP,'FFmpeg/FFprobe não disponíveis')
class SmartInsertFfmpegIntegrationTests(unittest.TestCase):
    @classmethod
    def run_command(cls,command):
        result=subprocess.run(list(map(str,command)),capture_output=True,timeout=120)
        if result.returncode:
            raise AssertionError(result.stderr.decode('utf-8','replace')[-2500:])
        return result

    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='sig-smartinsert-')
        cls.directory=Path(cls.temp.name)
        cls.count=0
        cls.sources={}
        for codec,extension in (('pcm_s16le','.wav'),('alac','.m4a'),('flac','.flac'),('aac','.m4a'),
                                ('libmp3lame','.mp3'),('libopus','.ogg'),('libvorbis','.ogg'),('wmav2','.wma')):
            path=cls.directory/(codec+extension)
            command=[FF,'-v','error','-y','-f','lavfi','-i','aevalsrc=0.1*sin(2*PI*440*t)+0.01*t:s=48000:d=6',
                     '-c:a',codec,'-metadata','title=Smart Insert reference']
            if codec in {'aac','libmp3lame','libopus','libvorbis','wmav2'}:command+=['-b:a','128k']
            cls.run_command(command+[path]);cls.sources[codec]=path
        cls.inserted=cls.directory/'inserted.wav'
        cls.run_command([FF,'-v','error','-y','-f','lavfi','-i','sine=frequency=880:sample_rate=44100:duration=2.137',
                         '-c:a','pcm_s16le',cls.inserted])

    @classmethod
    def tearDownClass(cls):
        print(f'Smart Insert: {cls.count} exportações reais concluídas.')
        cls.temp.cleanup()

    def probe(self,path,packets=False):
        command=[FP,'-v','error','-show_streams','-show_format','-of','json']
        if packets:command+=['-select_streams','a:0','-show_packets','-show_data_hash','sha256']
        return json.loads(self.run_command(command+[path]).stdout)

    def pcm(self,path):
        return self.run_command([FF,'-v','error','-i',path,'-map','0:a:0','-f','f64le','-']).stdout

    def insert(self,source,position=3.123456,seconds=0,transition='Linear',smart=True,reference=False):
        directory=Path(tempfile.mkdtemp(dir=self.directory))
        p=object.__new__(FfmpegToolsPanel)
        p.output_dir=directory;p.cancel_event=threading.Event()
        p._ffmpeg=lambda:Path(FF);p._get_ffprobe=lambda:Path(FP)
        p._record_ffmpeg_command=lambda *a,**kw:None
        p._set_status=lambda *a:None
        logs=[];commands=[]
        p._append_log=lambda message:logs.append(message)
        def execute(command,*a,**kw):
            commands.append(command)
            result=self.run_command(command)
            self.assertNotIn('Non-monotonic',result.stderr.decode('utf-8','replace'))
        p._execute=execute
        p.insert_main_input=source;p.insert_secondary_input=self.inserted;p.insert_timeline=Timeline(position)
        p.worker_options=dict(insert_smart=smart,insert_reencode=not smart,insert_transition=transition,insert_seconds=str(seconds))
        for key,value in p.worker_options.items():setattr(p,key+'_var',Var(value))
        if reference:
            profile=p._insert_probe_profile(source)
            output=directory/('reference'+source.suffix)
            p._insert_render_continuous(source,self.inserted,output,profile,position,seconds,p.insert_transition_code(transition),True)
        else:
            p._insert_worker()
            output=next(directory.glob('*_com_audio.*'))
        type(self).count+=1
        self.assertEqual(list(directory.iterdir()),[output])
        return output,self.probe(output),commands,logs

    def test_zero_and_three_fade_durations_all_codecs(self):
        for codec,source in self.sources.items():
            for seconds in (0,.2,.5,1):
                with self.subTest(codec=codec,seconds=seconds):
                    output,info,commands,logs=self.insert(source,seconds=seconds)
                    if codec == 'libopus':
                        # Ogg inclui 312 amostras de pre-skip no granule final;
                        # a duração apresentada/decodificada precisa ser exata.
                        self.assertEqual(len(self.pcm(output))//8,round(8.137*48000))
                        from smart_insert_planner import audio_duration
                        self.assertAlmostEqual(audio_duration(self.probe(output,True),0),8.137,delta=1/48000)
                    else:
                        self.assertAlmostEqual(float(info['format']['duration']),8.137,delta=.085 if codec=='wmav2' else .002)
                    self.assertEqual(info['streams'][0]['codec_name'],{'libmp3lame':'mp3','libopus':'opus','libvorbis':'vorbis'}.get(codec,codec))
                    effects=[arg for c in commands for arg in c if 'afade=' in arg or 'acrossfade=' in arg]
                    self.assertFalse(any('acrossfade=' in arg for arg in effects))
                    self.assertEqual(bool(effects),seconds>0)
                    if codec in {'pcm_s16le','alac','flac'}:
                        self.assertEqual(info['format']['tags']['title'],'Smart Insert reference')
                        reference,*_=self.insert(source,seconds=seconds,reference=True)
                        self.assertEqual(self.pcm(output),self.pcm(reference))
                        self.assertFalse(any('recodificação contínua' in line for line in logs))
                        if codec=='flac':
                            self.assertEqual(sum('-c:a' in c and c[c.index('-c:a')+1]=='flac' for c in commands),1)
                            self.assertFalse(any('concat' in c for c in commands))
                    else:
                        self.assertTrue(any('recodificação contínua' in line for line in logs))

    def test_lossless_start_end_and_small_edges_match_continuous_reference(self):
        for codec in ('pcm_s16le','alac','flac'):
            source=self.sources[codec]
            for position in (0,1/48000,.03,4096/48000,6):
                with self.subTest(codec=codec,position=position):
                    output,*_=self.insert(source,position,seconds=.5)
                    reference,*_=self.insert(source,position,seconds=.5,reference=True)
                    self.assertEqual(self.pcm(output),self.pcm(reference))

    def test_all_offered_smart_curves_are_valid(self):
        for label in FfmpegToolsPanel.insert_transition_labels(True):
            with self.subTest(label=label):
                output,info,commands,_=self.insert(self.sources['pcm_s16le'],seconds=.2,transition=label)
                self.assertAlmostEqual(float(info['format']['duration']),8.137,delta=.00001)
                self.assertFalse(any('acrossfade=' in arg for c in commands for arg in c))

    def test_full_crossfade_and_fade_in_out_have_expected_duration(self):
        source=self.sources['pcm_s16le']
        for seconds in (0,.2,.5,1):
            for transition in ('Crossfade linear','Fade in/out'):
                with self.subTest(seconds=seconds,transition=transition):
                    output,info,*_=self.insert(source,seconds=seconds,transition=transition,smart=False)
                    expected=8.137-(2*seconds if transition=='Crossfade linear' else 0)
                    self.assertAlmostEqual(float(info['format']['duration']),expected,delta=.00001)

    def test_flac_crc_seek_and_copied_payloads(self):
        source=self.sources['flac']
        output,info,commands,_=self.insert(source)
        decoded=self.run_command([FF,'-v','error','-err_detect','crccheck','-i',output,'-f','null','-'])
        self.assertEqual(decoded.stderr,b'')
        self.assertEqual(info['format']['tags']['title'],'Smart Insert reference')
        reference=self.pcm(output)
        for point in (.1,3.1,5.7,7.8):
            raw=self.run_command([FF,'-v','error','-ss',str(point),'-i',output,'-t','0.1','-f','f64le','-']).stdout
            self.assertEqual(raw,reference[round(point*48000)*8:round((point+.1)*48000)*8])
        # O body comprimido deve permanecer idêntico; só os headers mudam.
        import smart_insert_flac
        src_info=self.probe(source,True);out_info=self.probe(output,True)
        def payloads(path,packets):
            result=set()
            with path.open('rb') as handle:
                for packet in packets:
                    handle.seek(int(packet['pos']));frame=handle.read(int(packet['size']))
                    _,end,_=smart_insert_flac.frame_header(frame)
                    result.add(frame[end:-2])
            return result
        original=payloads(source,src_info['packets'])
        actual=payloads(output,out_info['packets'])
        self.assertGreaterEqual(len(original&actual),len(original)-1)

    def test_pcm32_and_flac24_preserve_samples_and_depth(self):
        source=self.directory/'pcm32.wav'
        values=array.array('i',(((n*15485863) % (1<<31))-(1<<30) for n in range(96000)))
        with wave.open(str(source),'wb') as handle:
            handle.setparams((1,4,48000,0,'NONE','not compressed'))
            handle.writeframes(values.tobytes())
        flac=self.directory/'flac24_44100.flac'
        self.run_command([FF,'-v','error','-y','-i',source,'-ar','44100','-c:a','flac','-sample_fmt','s32',
                          '-bits_per_raw_sample','24',flac])
        for src in (source,flac):
            with self.subTest(source=src.name):
                output,info,*_=self.insert(src,position=.713456)
                reference,*_=self.insert(src,position=.713456,reference=True)
                self.assertEqual(self.pcm(output),self.pcm(reference))
                rate=int(info['streams'][0]['sample_rate'])
                raw=self.pcm(src);actual=self.pcm(output)
                cut=round(.713456*rate);middle=round(2.137*rate)
                self.assertEqual(actual[:cut*8],raw[:cut*8])
                self.assertEqual(actual[(cut+middle)*8:],raw[cut*8:])
                if src==flac:self.assertEqual(info['streams'][0]['bits_per_raw_sample'],'24')

    def test_stereo_alac_preserves_channel_format(self):
        source=self.directory/'stereo.m4a'
        self.run_command([FF,'-v','error','-y','-f','lavfi','-i',
                          'aevalsrc=0.1*sin(2*PI*440*t)|0.1*sin(2*PI*1200*t):s=48000:d=6',
                          '-c:a','alac',source])
        output,info,*_=self.insert(source,seconds=.5)
        reference,*_=self.insert(source,seconds=.5,reference=True)
        self.assertEqual(self.pcm(output),self.pcm(reference))
        self.assertEqual(info['streams'][0]['channels'],2)

    def test_full_crossfade_with_submillisecond_neighbors(self):
        for position in (1/48000, 20/48000, 6-20/48000):
            with self.subTest(position=position):
                output,info,*_=self.insert(self.sources['pcm_s16le'],position,seconds=.5,
                                           transition='Crossfade linear',smart=False)
                fade=round(min(position,6-position)/2*48000)
                expected=round(8.137*48000)-2*fade
                self.assertEqual(len(self.pcm(output))//8,expected)
                self.assertAlmostEqual(float(info['format']['duration']),expected/48000,delta=1/48000)

    def test_unsigned_and_floating_pcm_preserve_main_samples(self):
        for codec in ('pcm_u8','pcm_f32le','pcm_f64le'):
            with self.subTest(codec=codec):
                source=self.directory/(codec+'.wav')
                self.run_command([FF,'-v','error','-y','-i',self.sources['pcm_s16le'],'-c:a',codec,source])
                output,info,commands,logs=self.insert(source,seconds=.5)
                reference,*_=self.insert(source,seconds=.5,reference=True)
                self.assertEqual(self.pcm(output),self.pcm(reference))
                self.assertEqual(info['streams'][0]['codec_name'],codec)
                self.assertTrue(any('somente o áudio inserido foi recodificado' in line for line in logs))
