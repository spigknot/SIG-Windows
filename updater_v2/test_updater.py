from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from updater import (  # noqa: E402
    REQUIRED_DIRECTORIES,
    REQUIRED_UPDATE_FILES,
    REQUIRED_RUNTIME_FILES,
    UpdateError,
    validate_install_tree,
    validate_zip,
)


class UpdaterV2ValidationTests(unittest.TestCase):
    def _make_package(self, root: Path, missing: set[str] | None = None) -> None:
        missing = missing or set()
        for relative in REQUIRED_UPDATE_FILES + REQUIRED_RUNTIME_FILES:
            if any(relative == item or relative.startswith(item + "/") for item in missing):
                continue
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        for relative in REQUIRED_DIRECTORIES:
            if relative not in missing:
                (root / relative).mkdir(parents=True, exist_ok=True)
        (root / "vad_deps" / "fixture.txt").write_bytes(b"fixture")

    def _zip_directory(self, source: Path, destination: Path, extras: list[str] | None = None) -> None:
        with zipfile.ZipFile(destination, "w") as archive:
            for path in source.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(source).as_posix())
            for name in extras or []:
                archive.writestr(name, b"fixture")

    def test_complete_onedir_package_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            root.mkdir()
            self._make_package(root)
            validate_install_tree(root)
            zip_path = Path(temporary) / "package.zip"
            self._zip_directory(root, zip_path)
            validate_zip(zip_path)

    def test_missing_internal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            root.mkdir()
            self._make_package(root, {"_internal"})
            with self.assertRaisesRegex(UpdateError, "_internal"):
                validate_install_tree(root)

    def test_missing_portaudio_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            root.mkdir()
            self._make_package(root, {"_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll"})
            with self.assertRaisesRegex(UpdateError, "PortAudio"):
                validate_install_tree(root)

    def test_missing_updater_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            root.mkdir()
            self._make_package(root, {"SigUpdater.exe"})
            with self.assertRaisesRegex(UpdateError, "SigUpdater.exe"):
                validate_install_tree(root)

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            root.mkdir()
            self._make_package(root)
            zip_path = Path(temporary) / "traversal.zip"
            self._zip_directory(root, zip_path, ["../outside.txt"])
            with self.assertRaisesRegex(UpdateError, "caminho inseguro"):
                validate_zip(zip_path)

    def test_g_and_mei_are_rejected(self):
        for bad_name, expected in (("g/old.txt", "pasta proibida g"), ("_MEI123/old.txt", "_MEI")):
            with self.subTest(bad_name=bad_name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "package"
                root.mkdir()
                self._make_package(root)
                zip_path = Path(temporary) / "bad-layout.zip"
                self._zip_directory(root, zip_path, [bad_name])
                with self.assertRaisesRegex(UpdateError, expected):
                    validate_zip(zip_path)

    def test_duplicate_normalized_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            root.mkdir()
            self._make_package(root)
            zip_path = Path(temporary) / "duplicate.zip"
            self._zip_directory(root, zip_path, ["sig.exe"])
            with self.assertRaisesRegex(UpdateError, "entrada duplicada"):
                validate_zip(zip_path)

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            root.mkdir()
            self._make_package(root)
            zip_path = Path(temporary) / "symlink.zip"
            self._zip_directory(root, zip_path)
            link = zipfile.ZipInfo("link-to-outside")
            link.create_system = 3
            link.external_attr = 0o120777 << 16
            with zipfile.ZipFile(zip_path, "a") as archive:
                archive.writestr(link, b"../../outside")
            with self.assertRaisesRegex(UpdateError, "link simbólico"):
                validate_zip(zip_path)


if __name__ == "__main__":
    unittest.main()
