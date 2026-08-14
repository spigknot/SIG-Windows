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
    REQUIRED_INCREMENTAL_DIRECTORIES,
    REQUIRED_INCREMENTAL_FILES,
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
from release import latest_generated_full_package, load_updater_harness  # noqa: E402


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
    def test_updater_harness_is_loaded_from_repository_root(self):
        run_updater_test = load_updater_harness(ROOT)
        self.assertTrue(callable(run_updater_test))

    def test_latest_generated_full_package_ignores_incomplete_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            older = root / "release" / "generated" / "20260812_001"
            newer_incomplete = root / "release" / "generated" / "20260813_001"
            older.mkdir(parents=True)
            newer_incomplete.mkdir(parents=True)
            valid_zip = older / "20260812_001.zip"
            invalid_zip = newer_incomplete / "20260813_001.zip"
            valid_zip.write_bytes(b"valid")
            invalid_zip.write_bytes(b"incomplete")
            (older / "package" / "vad_deps").mkdir(parents=True)

            self.assertEqual(latest_generated_full_package(root), valid_zip)

    def test_latest_generated_full_package_requires_runtime_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "release" / "generated" / "20260813_001"
            candidate.mkdir(parents=True)
            (candidate / "20260813_001.zip").write_bytes(b"incomplete")

            with self.assertRaisesRegex(ValidationError, "nenhum pacote full validado"):
                latest_generated_full_package(root)

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

    def test_incremental_layout_excludes_runtime_and_keeps_update_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            for relative in REQUIRED_INCREMENTAL_FILES:
                path = package / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            for relative in REQUIRED_INCREMENTAL_DIRECTORIES:
                (package / relative).mkdir(parents=True, exist_ok=True)
            validate_package_layout(package, full=False)
            (package / "ffmpeg.exe").write_bytes(b"runtime")
            with self.assertRaisesRegex(ValidationError, "recursos de runtime proibidos"):
                validate_package_layout(package, full=False)

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
            modules = {
                "pypdfium2",
                "pypdfium2_raw",
                "sounddevice",
                "_sounddevice",
                "_sounddevice_data",
                "websocket",
            }
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

    def test_missing_pdfium_is_rejected_from_frozen_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            (package / "sig.exe").write_bytes(b"fixture")
            portaudio = (
                package
                / "_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll"
            )
            portaudio.parent.mkdir(parents=True)
            portaudio.write_bytes(b"fixture")
            modules = {
                "pypdfium2",
                "pypdfium2_raw",
                "sounddevice",
                "_sounddevice",
                "_sounddevice_data",
                "websocket",
            }
            with patch(
                "PyInstaller.archive.readers.CArchiveReader",
                return_value=_FakeReader(modules),
            ):
                with self.assertRaisesRegex(ValidationError, "PDFium"):
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

    def test_runtime_bundle_hash_ignores_only_python_caches(self):
        from release_validation import runtime_asset_fingerprint

        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime"
            dependency = runtime / "vad_deps" / "package"
            dependency.mkdir(parents=True)
            (runtime / "ffmpeg.exe").write_bytes(b"ffmpeg")
            (runtime / "ffplay.exe").write_bytes(b"ffplay")
            (dependency / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            expected = runtime_asset_fingerprint(runtime)

            cache = dependency / "__pycache__"
            cache.mkdir()
            (cache / "module.cpython-311.pyc").write_bytes(b"regenerable")
            (dependency / "legacy.pyo").write_bytes(b"regenerable")
            self.assertEqual(expected, runtime_asset_fingerprint(runtime))

            (dependency / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
            self.assertNotEqual(expected, runtime_asset_fingerprint(runtime))

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
