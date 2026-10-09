import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ffmpeg_recovery import RecoveryJob


class RecoveryTests(unittest.TestCase):
    def test_parallel_split_is_reused_only_with_every_completed_segment(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            job=RecoveryJob.create(root/"registry",{"output_dir":str(root)},[])
            directory=job.directory("rotate")
            command=["ffmpeg","-f","segment",str(directory/"part_%05d.mkv")]
            first=directory/"part_00000.mkv";second=directory/"part_00001.mkv"
            job.begin_step(command);first.write_bytes(b"first");second.write_bytes(b"second")
            self.assertFalse(job.can_reuse(command));job.complete_step(command)
            self.assertTrue(RecoveryJob.load(job.journal).can_reuse(command))
            first.unlink();self.assertFalse(job.can_reuse(command))

    def test_restart_reuses_only_completed_unchanged_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            source.write_bytes(b"source")
            job = RecoveryJob.create(root / "registry", {"output_dir": str(root)}, [source])
            output = job.directory("cut") / "body.ts"
            command = ["ffmpeg", "-i", str(source), str(output)]
            job.begin_step(command)
            output.write_bytes(b"half")
            restarted = RecoveryJob.load(job.journal)
            self.assertFalse(restarted.can_reuse(command))
            output.write_bytes(b"complete")
            restarted.complete_step(command)
            restarted = RecoveryJob.load(job.journal)
            self.assertTrue(restarted.can_reuse(command))
            output.write_bytes(b"changed")
            self.assertFalse(restarted.can_reuse(command))

    def test_source_changes_and_invalid_root_prevent_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.wav"
            source.write_bytes(b"source")
            job = RecoveryJob.create(root / "registry", {"output_dir": str(root)}, [source])
            source.write_bytes(b"modified")
            with self.assertRaises(ValueError):
                RecoveryJob.load(job.journal)
            job.state["inputs"] = {}
            job.state["work_root"] = str(root.parent)
            job.save()
            with self.assertRaises(ValueError):
                RecoveryJob.load(job.journal)

    def test_completion_cleans_only_owned_work_and_preserves_final_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            final = root / "final.mp4"
            final.write_bytes(b"final")
            job = RecoveryJob.create(root / "registry", {"output_dir": str(root)}, [])
            chosen = job.allocate("output", lambda: final)
            self.assertEqual(chosen, RecoveryJob.load(job.journal).allocate("output", lambda: root / "other"))
            self.assertEqual([job.journal], RecoveryJob.pending(root / "registry"))
            job.finish("complete")
            self.assertFalse(job.work_root.exists())
            self.assertTrue(final.exists())
            self.assertEqual([], RecoveryJob.pending(root / "registry"))
