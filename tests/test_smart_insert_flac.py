import random
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from smart_insert_flac import crc, shift_crc, encode_number, rebase_frame, frame_header

class SmartInsertFlacTests(unittest.TestCase):
    def test_crc_table_matches_independent_bitwise_crc(self):
        data=random.Random(120).randbytes(8192)
        for bits,polynomial in ((8,7),(16,0x8005)):
            value=0
            for byte in data:
                value ^= byte << (bits-8)
                for _ in range(8):
                    value=((value<<1) ^ (polynomial if value & (1<<(bits-1)) else 0)) & ((1<<bits)-1)
            self.assertEqual(crc(data,bits,polynomial),value)

    def test_crc_delta_matches_complete_recalculation(self):
        # Verificação independente com CRC sobre o frame inteiro, incluindo
        # aumento/redução da quantidade de bytes do número de amostra.
        rng=random.Random(829)
        for old_number in (0,127,128,65536):
            prefix=b'\xff\xf8\x69\x08'+encode_number(old_number)+bytes([127])
            header=prefix+bytes([crc(prefix,8,7)])
            body=rng.randbytes(8192)
            frame=header+body+crc(header+body,16,0x8005).to_bytes(2,'big')
            for sample in (0,128,65536,1<<35):
                new,count=rebase_frame(frame,sample)
                _,end,_=frame_header(new)
                self.assertEqual(count,128)
                self.assertEqual(new[end:-2],body)
                self.assertEqual(crc(new,16,0x8005),0)
                self.assertEqual(new[1],0xf9)

    def test_shift_matches_zero_byte_crc(self):
        for length in (0,1,127,8192):
            a=crc(b'original header',16,0x8005)
            self.assertEqual(shift_crc(a,length),crc(b'original header'+bytes(length),16,0x8005))

    def test_invalid_frame_headers_are_rejected(self):
        for data in (b'',b'not a flac frame',b'\xff\xf8\x69\x08\xff\x01\x00\x00'):
            with self.assertRaises(ValueError):rebase_frame(data,0)

    def test_sample_number_limits_are_checked(self):
        for number in (-1,1<<36):
            with self.assertRaises(ValueError):encode_number(number)
