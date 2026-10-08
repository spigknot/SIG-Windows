"""FFprobe via componente interno compatível com o sync antigo."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from release import copy_runtime_assets
from sync_r2 import snapshot


class FfprobeDistributionTests(unittest.TestCase):
    def test_release_delivers_probe_in_known_sync_component(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            package = Path(directory) / "package"
            runtime.mkdir()
            package.mkdir()
            (runtime / "vad_deps").mkdir()
            for name in ("ffmpeg.exe", "ffplay.exe", "ffprobe.exe", "SigUpdater.exe"):
                (runtime / name).write_bytes(name.encode())
            copy_runtime_assets(runtime, package)
            files = snapshot(package)
            self.assertNotIn("ffprobe.exe", files)
            self.assertIn("_internal/tools/ffprobe.exe", files)
            self.assertEqual((package / "_internal/tools/ffprobe.exe").read_bytes(),
                             (runtime / "ffprobe.exe").read_bytes())
