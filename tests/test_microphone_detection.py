from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import SigApp  # noqa: E402


class FakeSoundDevice:
    def __init__(self, devices):
        self.devices = devices

    def query_devices(self):
        return self.devices


class MicrophoneDetectionTests(unittest.TestCase):
    def test_detects_any_device_with_input_channels(self):
        sounddevice = FakeSoundDevice(
            [
                {"name": "Saída", "max_input_channels": 0},
                {"name": "Microfone USB", "max_input_channels": 1},
            ]
        )
        self.assertTrue(SigApp._sounddevice_has_input_device(sounddevice))

    def test_portaudio_failure_is_treated_as_unavailable(self):
        class BrokenSoundDevice:
            def query_devices(self):
                raise RuntimeError("PortAudio indisponível")

        self.assertFalse(SigApp._sounddevice_has_input_device(BrokenSoundDevice()))


if __name__ == "__main__":
    unittest.main()
