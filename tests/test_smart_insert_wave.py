import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import smart_insert_wave as wav


class SmartInsertWaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def write_wave(self, name, samples, width=2):
        path = self.root / name
        with wave.open(str(path), 'wb') as handle:
            handle.setparams((1, width, 48000, 0, 'NONE', 'not compressed'))
            handle.writeframes(samples)
        return path

    def test_exact_copy_at_beginning_middle_and_end(self):
        original = struct.pack('<7h', -32768, -1234, -1, 0, 1, 1234, 32767)
        added = struct.pack('<3h', 200, -200, 900)
        main = self.write_wave('main.wav', original)
        middle = self.write_wave('middle.wav', added)
        for cut in (0, 1, 4, 7):
            out = self.root / f'{cut}.wav'
            wav.assemble(main, middle, out, cut, 10, lambda: None)
            with wave.open(str(out), 'rb') as handle:
                self.assertEqual(handle.getnframes(), 10)
                self.assertEqual(handle.readframes(10), original[:cut*2]+added+original[cut*2:])

    def test_odd_unsigned_pcm_data_has_valid_padding(self):
        main = self.write_wave('main.wav', b'\x00\x80\xff', 1)
        middle = self.write_wave('middle.wav', b'\x45\x93', 1)
        out = self.root / 'out.wav'
        wav.assemble(main, middle, out, 1, 5, lambda: None)
        with wave.open(str(out), 'rb') as handle:
            self.assertEqual(handle.readframes(5), b'\x00\x45\x93\x80\xff')
        self.assertEqual(out.stat().st_size-8, int.from_bytes(out.read_bytes()[4:8], 'little'))

    def test_rf64_and_extensible_sources_are_understood(self):
        fmt = struct.pack('<HHIIHHHHI', 0xfffe, 2, 48000, 288000, 6, 24, 22, 24, 3)
        fmt += bytes.fromhex('0100000000001000800000aa00389b71')
        data = bytes(range(30))
        extra = b'fmt '+struct.pack('<I', len(fmt))+fmt
        riff_size = 4+36+len(extra)+8+len(data)
        payload = b'RF64\xff\xff\xff\xffWAVE'
        payload += b'ds64'+struct.pack('<IQQQI', 28, riff_size, len(data), 5, 0)
        payload += extra+b'data\xff\xff\xff\xff'+data
        main = self.root/'rf64.wav'
        main.write_bytes(payload)
        self.assertEqual(wav.inspect(main).signature, (1,2,48000,6,24,24,0))
        out = self.root/'out.wav'
        wav.assemble(main,main,out,2,10,lambda:None)
        parsed = wav.inspect(out)
        self.assertEqual(out.read_bytes()[parsed.offset:parsed.offset+parsed.size],data[:12]+data+data[12:])

    def test_invalid_or_mismatched_inputs_are_rejected(self):
        main=self.write_wave('main.wav', bytes(12))
        middle=self.write_wave('middle.wav', bytes(9),1)
        with self.assertRaises(ValueError):
            wav.assemble(main,middle,self.root/'out.wav',2,15,lambda:None)
        main.write_bytes(main.read_bytes()[:-1])
        with self.assertRaises(ValueError):wav.inspect(main)

    def test_cancellation_stops_copy(self):
        main=self.write_wave('main.wav',bytes(100))
        def cancelled():raise InterruptedError('cancelled')
        with self.assertRaises(InterruptedError):
            wav.assemble(main,main,self.root/'out.wav',25,100,cancelled)


if __name__ == '__main__':
    unittest.main()
