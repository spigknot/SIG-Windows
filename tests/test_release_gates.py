from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_validation import (  # noqa: E402
    REQUIRED_FULL_DIRECTORIES,
    REQUIRED_FULL_FILES,
    ValidationError,
    frozen_app_version,
    read_app_version,
    read_manifest,
    validate_frozen_dependencies,
    validate_build_info,
    validate_package_layout,
    validate_pyinstaller_warnings,
    validate_runtime_assets,
    validate_updater_artifact,
    validate_version_consistency,
)


class _FakePyz:
    def __init__(self, modules: set[str]):
        self.toc = {module: None for module in modules}


class _FakeReader:
    def __init__(self, modules: set[str]):
        self.modules = modules

    def open_embedded_archive(self, name: str):
        self.asserted_name = name
        return _FakePyz(self.modules)


class ReleaseGateTests(unittest.TestCase):
    def test_current_source_manifest_and_frozen_version_are_consistent(self):
        source_version = read_app_version(ROOT / "src/sig_app.py")
        manifest = {
            "version": source_version,
            "zip_name": f"{source_version}.zip",
        }
        validate_version_consistency(source_version, manifest, frozen_version=source_version)
        self.assertRegex(source_version, r"^\d{8}_\d{3}$")

    def test_historical_20260806_002_stale_app_version_is_rejected(self):
        manifest = {"version": "20260806_002", "zip_name": "20260806_002.zip"}
        with self.assertRaisesRegex(ValidationError, "APP_VERSION=20260805_001"):
            validate_version_consistency("20260805_001", manifest)

    def test_historical_zip_name_mismatch_is_rejected(self):
        manifest = {"version": "20260806_004", "zip_name": "20260806_002.zip"}
        with self.assertRaisesRegex(ValidationError, "nome do ZIP inconsistente"):
            validate_version_consistency("20260806_004", manifest)

    def _make_minimal_package(self, root: Path, missing: set[str] = set()) -> None:
        for relative in REQUIRED_FULL_FILES:
            if not any(relative == item or relative.startswith(item + "/") for item in missing):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
        for relative in REQUIRED_FULL_DIRECTORIES:
            if relative not in missing:
                (root / relative).mkdir(parents=True, exist_ok=True)

    def test_missing_sigupdater_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            self._make_minimal_package(package, {"SigUpdater.exe"})
            with self.assertRaisesRegex(ValidationError, "SigUpdater.exe"):
                validate_package_layout(package)

    def test_missing_internal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            self._make_minimal_package(package, {"_internal"})
            with self.assertRaisesRegex(ValidationError, "_internal"):
                validate_package_layout(package)

    def test_forbidden_g_and_mei_layouts_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            self._make_minimal_package(package)
            (package / "g").mkdir()
            with self.assertRaisesRegex(ValidationError, "pasta proibida g"):
                validate_package_layout(package)

    def test_missing_portaudio_is_rejected_from_frozen_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            (package / "sig.exe").write_bytes(b"fixture")
            modules = {"sounddevice", "_sounddevice", "_sounddevice_data", "websocket"}
            with patch(
                "PyInstaller.archive.readers.CArchiveReader",
                return_value=_FakeReader(modules),
            ):
                with self.assertRaisesRegex(ValidationError, "PortAudio"):
                    validate_frozen_dependencies(package)

    def test_missing_sounddevice_or_websocket_in_pyz_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            (package / "sig.exe").write_bytes(b"fixture")
            with patch(
                "PyInstaller.archive.readers.CArchiveReader",
                return_value=_FakeReader({"sounddevice", "_sounddevice", "_sounddevice_data"}),
            ):
                with self.assertRaisesRegex(ValidationError, "websocket"):
                    validate_frozen_dependencies(package)

    def test_critical_pyinstaller_warning_is_rejected_but_optional_warning_is_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            warning_path = Path(temporary) / "warn-sig.txt"
            warning_path.write_text("missing module named 'sounddevice' - imported by sig_app\n", encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "warnings críticos"):
                validate_pyinstaller_warnings(warning_path)
            warning_path.write_text("missing module named 'wsaccel' - optional\n", encoding="utf-8")
            validate_pyinstaller_warnings(warning_path)

    def test_updater_hash_gate_rejects_missing_or_changed_helper(self):
        metadata = ROOT / "scripts/updater_artifact.json"
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            with self.assertRaisesRegex(ValidationError, "SigUpdater.exe"):
                validate_updater_artifact(package, metadata)
            (package / "SigUpdater.exe").write_bytes(b"not-the-known-good-helper")
            with self.assertRaisesRegex(ValidationError, "artefato conhecido como bom"):
                validate_updater_artifact(package, metadata)

    def test_runtime_bundle_hash_gate_rejects_changed_dist_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            (runtime / "vad_deps").mkdir(parents=True)
            (runtime / "ffmpeg.exe").write_bytes(b"ffmpeg")
            (runtime / "ffplay.exe").write_bytes(b"ffplay")
            (runtime / "vad_deps" / "fixture.txt").write_text("fixture", encoding="utf-8")
            from release_validation import runtime_asset_fingerprint

            metadata = Path(temporary) / "runtime_artifact.json"
            metadata.write_text(
                json.dumps(runtime_asset_fingerprint(runtime)),
                encoding="utf-8",
            )
            validate_runtime_assets(runtime, metadata)
            altered = Path(temporary) / "altered-runtime-artifact.json"
            data = json.loads(metadata.read_text(encoding="utf-8"))
            data["files"]["ffplay.exe"]["sha256"] = "0" * 64
            altered.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "conteúdo antigo ou alterado"):
                validate_runtime_assets(runtime, altered)

    def test_fresh_build_marker_cannot_be_faked_by_old_dist(self):
        # A release package must carry build-info.json. This fixture represents
        # the old-dist situation: no marker from the current clean build exists.
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            (package / "sig.exe").write_bytes(b"old-dist")
            with self.assertRaisesRegex(ValidationError, "build-info.json"):
                validate_build_info(package, ROOT, "20260806_004")


if __name__ == "__main__":
    unittest.main()
