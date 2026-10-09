import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smart_insert_planner import plan, audio_duration

def info(rate=48000):
    return {"streams": [{"codec_type": "audio", "codec_name": "alac", "sample_rate": str(rate),
                         "start_time": "0", "duration_ts": 12000, "time_base": f"1/{rate}"}],
            "packets": [{"pts_time": str(n/rate), "duration_time": str(4000/rate)} for n in (0,4000,8000)]}

class SmartInsertPlannerTests(unittest.TestCase):
    def test_borders_are_sample_accurate(self):
        p = plan(info(), .25, .1, .123456, 48000)
        self.assertEqual((p.insertion,p.left,p.right,p.prefix_packets,p.suffix_packets), (5926,4000,8000,1,1))
        self.assertEqual(p.total_samples,16800)

    def test_packet_boundary_needs_only_inserted_audio(self):
        p = plan(info(),.25,.1,4000/48000,48000)
        self.assertEqual(p.left,p.right)

    def test_endpoints_copy_all_main_packets(self):
        for point in (0,.25):
            p = plan(info(),.25,.1,point,48000)
            self.assertEqual(p.prefix_packets+p.suffix_packets,3)

    def test_gap_or_duplicate_is_rejected(self):
        for value in ('0.1','0'):
            sample = info()
            sample['packets'][1]['pts_time']=value
            with self.assertRaises(ValueError):plan(sample,.25,.1,.12,48000)

    def test_exact_duration_does_not_use_banner_rounding(self):
        self.assertEqual(audio_duration(info(),.3),.25)

    def test_opus_duration_excludes_preskip(self):
        sample=info()
        sample['streams'][0].update(codec_name='opus',duration_ts=12312)
        sample['packets'][0]['side_data_list']=[{'skip_samples':312}]
        self.assertEqual(audio_duration(sample,.3),.25)

    def test_nonfinite_time_is_rejected(self):
        for value in (float('nan'),float('inf')):
            with self.assertRaises(ValueError):plan(info(),.25,.1,value,48000)

    def test_flac_tiny_internal_bridge_includes_a_main_packet(self):
        p=plan(info(),.25,1/48000,4000/48000,48000,16)
        self.assertGreaterEqual(p.right-p.left+p.inserted_samples,16)

    def test_negative_and_shifted_clocks_keep_copy_and_correct_seek_origin(self):
        for origin, container in ((-2,-2), (5,4.5), (0,.2)):
            sample=info();sample['streams'][0]['start_time']=str(origin)
            sample['format']={'start_time':str(container)}
            for packet in sample['packets']:packet['pts_time']=str(float(packet['pts_time'])+origin)
            result=plan(sample,.25,.1,.12,48000)
            self.assertEqual(result.prefix_packets,1)
            self.assertAlmostEqual(result.seek_offset,origin-container)

    def test_partial_first_and_last_packets_encode_only_small_edges(self):
        sample=info()
        sample['packets']=[{'pts_time':str(n/48000),'duration_time':str(4000/48000)} for n in (-1000,3000,7000,11000)]
        for point in (0,.12,.25):
            result=plan(sample,.25,.1,point,48000)
            self.assertGreaterEqual(result.left,0);self.assertLessEqual(result.right,12000)
            self.assertEqual(result.head_end+(result.left-result.head_end)+(result.right-result.left)+
                             (result.tail_start-result.right)+(12000-result.tail_start),12000)
            self.assertEqual((result.prefix_packets+result.suffix_packets)*4000,
                             result.left-result.head_end+result.tail_start-result.right)
