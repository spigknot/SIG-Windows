"""Testes do protocolo sync do SIG (src/sync_common.py) — incluindo PARIDADE
com a cópia embutida no updater (updater_v2/updater.py).

A duplicação é intencional (o updater é compilado à parte); estes testes são
a vacina que garante que as duas cópias nunca divergem.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "updater_v2"))

import sync_common  # noqa: E402
import updater as updater_module  # noqa: E402


def _fake_manifest_files() -> list[dict]:
    entries = []
    for path in sync_common.SYNC_REQUIRED_FILES:
        entries.append(
            {
                "path": path,
                "sha256": "a" * 64,
                "size": 123,
                "drive_id": "id-" + path.replace("/", "-"),
            }
        )
    return entries


def _manifest(**overrides) -> dict:
    manifest = {
        "schema": 2,
        "version": "20260814_012",
        "created_at": "2026-08-14T20:00:00-0300",
        "files": _fake_manifest_files(),
    }
    manifest.update(overrides)
    return manifest


class ParityTests(unittest.TestCase):
    def test_canonical_identical_to_updater(self):
        manifest = _manifest()
        self.assertEqual(
            sync_common.canonical_sync_manifest(manifest),
            updater_module.canonical_sync_manifest(manifest),
        )

    def test_canonical_identical_with_file_order_shuffled(self):
        manifest = _manifest()
        shuffled = _manifest(files=list(reversed(manifest["files"])))
        self.assertEqual(
            sync_common.canonical_sync_manifest(manifest),
            updater_module.canonical_sync_manifest(shuffled),
        )

    def test_validation_agrees_with_updater_on_valid_manifest(self):
        manifest = _manifest()
        # sem assinatura ambos falham igualmente
        with self.assertRaises(sync_common.SyncError):
            sync_common.validate_sync_manifest(manifest)
        with self.assertRaises(updater_module.UpdateError):
            updater_module.validate_sync_manifest(manifest)

    def test_validation_agrees_with_updater_on_bad_path(self):
        manifest = _manifest()
        manifest["files"] = manifest["files"] + [
            {"path": "malicioso/x.txt", "sha256": "a" * 64, "size": 1, "drive_id": "x"}
        ]
        with self.assertRaises(sync_common.SyncError):
            sync_common.validate_sync_manifest(manifest)
        with self.assertRaises(updater_module.UpdateError):
            updater_module.validate_sync_manifest(manifest)

    def test_classification_agrees_with_updater(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            content = {
                "sig.exe": b"sig",
                "_internal/base_library.zip": b"base",
                "_internal/orfao.txt": b"orfao",
            }
            for name, data in content.items():
                path = target / Path(*name.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            import hashlib

            files = {
                "sig.exe": {
                    "sha256": hashlib.sha256(b"sig").hexdigest(),
                    "size": 3,
                    "drive_id": "id1",
                },
                "_internal/base_library.zip": {
                    "sha256": hashlib.sha256(b"base").hexdigest(),
                    "size": 4,
                    "drive_id": "id2",
                },
            }
            expected = sync_common.classify_sync_files(target, files)
            actual = updater_module.classify_sync_files(target, files)
            self.assertEqual(actual, expected)
            self.assertEqual(actual["remove"], ["_internal/orfao.txt"])


class SigSyncCommonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._key = None
        key_path = ROOT / "release" / "update_private_key.pem"
        if key_path.is_file():
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            cls._key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
            cls._hashes = hashes
            cls._padding = padding

    def _sign(self, manifest: dict) -> dict:
        import base64

        if self._key is None:
            return manifest
        signature = self._key.sign(
            sync_common.canonical_sync_manifest(manifest),
            self._padding.PKCS1v15(),
            self._hashes.SHA256(),
        )
        manifest["signature"] = base64.b64encode(signature).decode("ascii")
        return manifest

    def test_sha256_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "f.bin"
            path.write_bytes(b"conteudo")
            import hashlib

            self.assertEqual(
                sync_common.sha256_file(path),
                hashlib.sha256(b"conteudo").hexdigest(),
            )

    def test_validate_rejects_invalid_version(self):
        with self.assertRaisesRegex(sync_common.SyncError, "versão"):
            sync_common.validate_sync_manifest(self._sign(_manifest(version="banana")))

    def test_validate_rejects_duplicate_path(self):
        manifest = _manifest()
        manifest["files"] = manifest["files"] + [manifest["files"][0]]
        with self.assertRaisesRegex(sync_common.SyncError, "duplicado"):
            sync_common.validate_sync_manifest(self._sign(manifest))

    def test_validate_rejects_missing_essential(self):
        manifest = _manifest()
        manifest["files"] = [entry for entry in manifest["files"] if entry["path"] != "sig.exe"]
        with self.assertRaisesRegex(sync_common.SyncError, "obrigatórios"):
            sync_common.validate_sync_manifest(self._sign(manifest))

    def test_classify_identical_and_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / "sig.exe").write_bytes(b"ok")
            import hashlib

            files = {
                "sig.exe": {
                    "sha256": hashlib.sha256(b"ok").hexdigest(),
                    "size": 2,
                    "drive_id": "id1",
                },
                "prompts/x.txt": {"sha256": "a" * 64, "size": 5, "drive_id": "id2"},
            }
            result = sync_common.classify_sync_files(target, files)
            self.assertEqual(result["unchanged"], 1)
            self.assertEqual(result["download"], ["prompts/x.txt"])
            self.assertEqual(result["remove"], [])


if __name__ == "__main__":
    unittest.main()
