from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import SigApp  # noqa: E402


class UpdaterBootstrapTests(unittest.TestCase):
    def test_sync_launch_prefers_downloaded_updater(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = root / "installed"
            staged = root / "staged"
            installed.mkdir()
            staged.mkdir()
            (installed / "SigUpdater.exe").write_bytes(b"old-updater")
            (staged / "SigUpdater.exe").write_bytes(b"fixed-updater")
            removals = root / "removals.txt"
            removals.write_text("", encoding="utf-8")

            app = object.__new__(SigApp)
            app.root = mock.Mock()
            app._queue = mock.Mock()
            app._append_activity_log = mock.Mock()

            with mock.patch("sig_app.app_base_dir", return_value=installed), mock.patch(
                "sig_app.tempfile.gettempdir", return_value=str(root)
            ), mock.patch("sig_app.uuid.uuid4") as uuid4, mock.patch(
                "sig_app.subprocess.Popen"
            ) as popen:
                uuid4.return_value.hex = "bootstrap"
                app._launch_sync_update(staged, removals, "20260902_001")

            helper = root / "SigUpdater-bootstrap.exe"
            self.assertEqual(helper.read_bytes(), b"fixed-updater")
            self.assertEqual(Path(popen.call_args.args[0][0]), helper)
            app._queue.assert_not_called()

    def test_sync_launch_falls_back_to_installed_updater(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = root / "installed"
            staged = root / "staged"
            installed.mkdir()
            staged.mkdir()
            (installed / "SigUpdater.exe").write_bytes(b"installed-updater")
            removals = root / "removals.txt"
            removals.write_text("", encoding="utf-8")

            app = object.__new__(SigApp)
            app.root = mock.Mock()
            app._queue = mock.Mock()
            app._append_activity_log = mock.Mock()

            with mock.patch("sig_app.app_base_dir", return_value=installed), mock.patch(
                "sig_app.tempfile.gettempdir", return_value=str(root)
            ), mock.patch("sig_app.uuid.uuid4") as uuid4, mock.patch(
                "sig_app.subprocess.Popen"
            ):
                uuid4.return_value.hex = "fallback"
                app._launch_sync_update(staged, removals, "20260902_001")

            self.assertEqual(
                (root / "SigUpdater-fallback.exe").read_bytes(),
                b"installed-updater",
            )
            app._queue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
