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
    installed_version,
    version_key,
    select_full_release_asset,
    validate_full_install_destination,
    validate_install_tree,
    validate_zip,
    verify_update_manifest_signature,
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

    def test_prompts_directory_is_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            root.mkdir()
            self._make_package(root)
            (root / "prompts").mkdir()
            (root / "prompts" / "historico_system.txt").write_text("prompt", encoding="utf-8")
            (root / "prompts" / "historico_user.txt").write_text("prompt", encoding="utf-8")
            validate_install_tree(root)
            zip_path = Path(temporary) / "package-with-prompts.zip"
            self._zip_directory(root, zip_path)
            validate_zip(zip_path)

    def test_models_directory_is_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            root.mkdir()
            self._make_package(root)
            (root / "modelos").mkdir()
            (root / "modelos" / "modelo_declaracoes.docx").write_bytes(b"fixture")
            validate_install_tree(root)
            zip_path = Path(temporary) / "package-with-models.zip"
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

    def test_current_incremental_manifest_signature_is_valid(self):
        manifest = __import__("json").loads(
            (ROOT / "release" / "latest.json").read_text(encoding="utf-8")
        )
        self.assertTrue(verify_update_manifest_signature(manifest))
        manifest["size"] = int(manifest["size"]) + 1
        self.assertFalse(verify_update_manifest_signature(manifest))

    def test_full_release_prefers_largest_trusted_zip(self):
        release = {
            "tag_name": "20260813_006",
            "assets": [
                {
                    "name": "source.zip",
                    "size": 100,
                    "digest": "sha256:" + "1" * 64,
                    "browser_download_url": "https://github.com/example/source.zip",
                },
                {
                    "name": "SIG-full.zip",
                    "size": 200,
                    "digest": "sha256:" + "2" * 64,
                    "browser_download_url": "https://github.com/example/full.zip",
                },
            ],
        }
        selected = select_full_release_asset(release)
        self.assertEqual(selected["zip_name"], "SIG-full.zip")
        self.assertEqual(selected["sha256"], "2" * 64)

    def test_full_release_rejects_untrusted_download_url(self):
        release = {
            "tag_name": "20260813_006",
            "assets": [{
                "name": "SIG-full.zip",
                "size": 200,
                "digest": "sha256:" + "2" * 64,
                "browser_download_url": "https://example.com/full.zip",
            }],
        }
        with self.assertRaisesRegex(UpdateError, "não confiável"):
            select_full_release_asset(release)

    def test_full_package_can_target_empty_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "new-install"
            validate_full_install_destination(target)
            self.assertTrue(target.is_dir())

    def test_full_package_rejects_unrelated_nonempty_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "documents"
            target.mkdir()
            (target / "personal.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(UpdateError, "não parece ser uma instalação"):
                validate_full_install_destination(target)

    def test_installed_version_reads_build_info(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / "build-info.json").write_text(
                '{"version":"20260813_010"}', encoding="utf-8"
            )
            self.assertEqual(installed_version(target), "20260813_010")

    def test_incremental_zip_rejects_runtime_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            root.mkdir()
            self._make_package(root)
            zip_path = Path(temporary) / "incremental-with-runtime.zip"
            self._zip_directory(root, zip_path)
            with self.assertRaisesRegex(UpdateError, "recursos de runtime"):
                validate_zip(zip_path, full=False)

    def test_version_key_orders_release_versions(self):
        self.assertLess(version_key("20260813_017"), version_key("20260813_018"))
        self.assertEqual(version_key("invalid"), (0, 0, 0))

    def _make_diff_zip(self, destination: Path, removidos: list[str], extras: dict[str, bytes] | None = None) -> None:
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("sig.exe", b"fixture-sig")
            archive.writestr("build-info.json", '{"version": "20260814_008"}')
            for name, data in (extras or {}).items():
                archive.writestr(name, data)
            archive.writestr(
                "removidos.txt",
                ("\n".join(removidos) + ("\n" if removidos else "")).encode(),
            )

    def test_diff_zip_is_recognized_and_validated(self):
        with tempfile.TemporaryDirectory() as temporary:
            zip_path = Path(temporary) / "diff.zip"
            self._make_diff_zip(
                zip_path,
                ["_internal/old.dll"],
                {"_internal/new.dll": b"novo"},
            )
            self.assertEqual(validate_zip(zip_path), "incremental-diff")

    def test_diff_zip_rejects_runtime_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            zip_path = Path(temporary) / "diff-bad.zip"
            self._make_diff_zip(zip_path, ["vad_worker.py"])
            with self.assertRaisesRegex(UpdateError, "asset de runtime"):
                validate_zip(zip_path)

    def test_diff_zip_rejects_traversal_in_removidos(self):
        with tempfile.TemporaryDirectory() as temporary:
            zip_path = Path(temporary) / "diff-bad.zip"
            self._make_diff_zip(zip_path, ["../fora.txt"])
            with self.assertRaises(UpdateError):
                validate_zip(zip_path)

    def test_diff_zip_rejects_runtime_files_inside(self):
        with tempfile.TemporaryDirectory() as temporary:
            zip_path = Path(temporary) / "diff-bad.zip"
            self._make_diff_zip(zip_path, [], {"ffmpeg.exe": b"big"})
            with self.assertRaisesRegex(UpdateError, "recursos de runtime"):
                validate_zip(zip_path)


class SyncTransactionLogTests(unittest.TestCase):
    """F4: o --sync-staged grava versão + run id por tentativa, distinguíveis
    mesmo com o mesmo updater.log anexado entre execuções."""

    def test_two_runs_share_log_but_are_distinguishable(self):
        import re
        import time
        from unittest import mock

        from updater import main as updater_main

        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "updater.log"
            target = Path(temporary) / "target"
            target.mkdir()
            staged = Path(temporary) / "staged"
            staged.mkdir()
            removals = Path(temporary) / "removidos.txt"
            removals.write_text("", encoding="utf-8")

            with mock.patch("updater.apply_sync_transaction") as apply_mock:
                with mock.patch("updater._validate_removidos_entries", return_value=[]):
                    first = updater_main(
                        ["--sync-staged", str(staged), "--sync-removals", str(removals),
                         "--sync-version", "20260816_002", "--target", str(target),
                         "--log", str(log_path)]
                    )
                    time.sleep(1.1)  # garante run id com segundo distinto
                    second = updater_main(
                        ["--sync-staged", str(staged), "--sync-removals", str(removals),
                         "--sync-version", "20260816_002", "--target", str(target),
                         "--log", str(log_path)]
                    )
            self.assertEqual(first, 0)
            self.assertEqual(second, 0)
            self.assertEqual(apply_mock.call_count, 2)
            text = log_path.read_text(encoding="utf-8")
            starts = re.findall(r"Início da aplicação sync v=(\S+) run=(\S+)\.", text)
            self.assertEqual(len(starts), 2)
            self.assertEqual(starts[0][0], "20260816_002")
            self.assertEqual(starts[1][0], "20260816_002")
            self.assertNotEqual(starts[0][1], starts[1][1], "run ids devem ser distintos")
            self.assertIn("Aplicação concluída sync v=20260816_002", text)

    def test_failure_logs_transaction_label(self):
        import re
        from unittest import mock

        from updater import main as updater_main

        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "updater.log"
            target = Path(temporary) / "target"
            target.mkdir()
            staged = Path(temporary) / "staged"
            staged.mkdir()

            with mock.patch("updater._validate_removidos_entries", return_value=[]):
                with mock.patch(
                    "updater.apply_sync_transaction",
                    side_effect=RuntimeError("falha simulada"),
                ):
                    code = updater_main(
                        ["--sync-staged", str(staged), "--sync-version", "v123",
                         "--target", str(target), "--log", str(log_path)]
                    )
            self.assertEqual(code, 2)
            text = log_path.read_text(encoding="utf-8")
            self.assertRegex(text, r"Início da aplicação sync v=v123 run=\S+\.")
            self.assertRegex(text, r"Falha na aplicação sync v=v123 run=\S+: falha simulada")


if __name__ == "__main__":
    unittest.main()
