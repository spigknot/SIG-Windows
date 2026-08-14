"""Testes do manifesto de sincronização (schema 2) do updater.

Cobre a FASE A1 do release/SYNC_BY_FILE.md: canonical, assinatura e
validação estrutural. A assinatura é feita com a chave privada local quando
disponível (round-trip real com a chave pública embutida no updater).
"""

from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from updater import (  # noqa: E402
    SYNC_MANIFEST_SCHEMA,
    SYNC_REQUIRED_FILES,
    UpdateError,
    canonical_sync_manifest,
    validate_sync_manifest,
    verify_sync_manifest_signature,
)

ROOT = Path(__file__).resolve().parents[1]

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    KEY_PATH = ROOT / "release" / "update_private_key.pem"
    if KEY_PATH.is_file():
        PRIVATE_KEY = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)

        def _sign(canonical: bytes) -> str:
            signature = PRIVATE_KEY.sign(canonical, padding.PKCS1v15(), hashes.SHA256())
            return base64.b64encode(signature).decode("ascii")

    else:
        PRIVATE_KEY = None
except ImportError:  # pragma: no cover
    PRIVATE_KEY = None


def _fake_files(overrides: dict | None = None) -> list[dict]:
    entries = []
    for path in SYNC_REQUIRED_FILES:
        entries.append(
            {
                "path": path,
                "sha256": "a" * 64,
                "size": 123,
                "drive_id": "fake-id-" + path.replace("/", "-"),
            }
        )
    for path, changes in (overrides or {}).items():
        for entry in entries:
            if entry["path"] == path:
                entry.update(changes)
                break
    return entries


def _make_manifest(files: list[dict], version: str = "20260814_012") -> dict:
    manifest = {
        "schema": SYNC_MANIFEST_SCHEMA,
        "version": version,
        "created_at": "2026-08-14T20:00:00-0300",
        "files": files,
    }
    if PRIVATE_KEY is not None:
        manifest["signature"] = _sign(canonical_sync_manifest(manifest))
    return manifest


class SyncManifestTests(unittest.TestCase):
    def test_valid_signed_manifest_passes(self):
        if PRIVATE_KEY is None:
            self.skipTest("chave privada de teste indisponível")
        validated = validate_sync_manifest(_make_manifest(_fake_files()))
        self.assertEqual(validated["version"], "20260814_012")
        self.assertIn("sig.exe", validated["files"])

    def test_tampered_payload_fails_signature(self):
        if PRIVATE_KEY is None:
            self.skipTest("chave privada de teste indisponível")
        manifest = _make_manifest(_fake_files())
        manifest["version"] = "20260814_013"
        self.assertFalse(verify_sync_manifest_signature(manifest))
        with self.assertRaisesRegex(UpdateError, "assinatura"):
            validate_sync_manifest(manifest)

    def test_tampered_file_entry_fails_signature(self):
        if PRIVATE_KEY is None:
            self.skipTest("chave privada de teste indisponível")
        manifest = _make_manifest(_fake_files())
        manifest["files"][0]["sha256"] = "b" * 64
        self.assertFalse(verify_sync_manifest_signature(manifest))

    def test_wrong_schema_is_rejected(self):
        manifest = _make_manifest(_fake_files())
        manifest["schema"] = 1
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        with self.assertRaisesRegex(UpdateError, "schema"):
            validate_sync_manifest(manifest)

    def test_invalid_version_is_rejected(self):
        manifest = _make_manifest(_fake_files(), version="banana")
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        with self.assertRaisesRegex(UpdateError, "versão"):
            validate_sync_manifest(manifest)

    def test_traversal_path_is_rejected(self):
        files = _fake_files() + [
            {"path": "../fora.txt", "sha256": "a" * 64, "size": 1, "drive_id": "x"}
        ]
        manifest = _make_manifest(files)
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        with self.assertRaises(UpdateError):
            validate_sync_manifest(manifest)

    def test_unknown_top_level_is_rejected(self):
        files = _fake_files() + [
            {"path": "outra_pasta/x.txt", "sha256": "a" * 64, "size": 1, "drive_id": "x"}
        ]
        manifest = _make_manifest(files)
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        with self.assertRaisesRegex(UpdateError, "desconhecido"):
            validate_sync_manifest(manifest)

    def test_invalid_hash_is_rejected(self):
        files = _fake_files({"sig.exe": {"sha256": "zz" * 32}})
        manifest = _make_manifest(files)
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        with self.assertRaisesRegex(UpdateError, "hash"):
            validate_sync_manifest(manifest)

    def test_duplicate_path_is_rejected(self):
        files = _fake_files() + [_fake_files()[0]]
        manifest = _make_manifest(files)
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        with self.assertRaisesRegex(UpdateError, "duplicado"):
            validate_sync_manifest(manifest)

    def test_missing_essential_is_rejected(self):
        files = [entry for entry in _fake_files() if entry["path"] != "sig.exe"]
        manifest = _make_manifest(files)
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        with self.assertRaisesRegex(UpdateError, "obrigatórios"):
            validate_sync_manifest(manifest)

    def test_missing_drive_id_is_rejected(self):
        files = _fake_files({"sig.exe": {"drive_id": ""}})
        manifest = _make_manifest(files)
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        with self.assertRaisesRegex(UpdateError, "drive_id"):
            validate_sync_manifest(manifest)

    def test_canonical_is_stable_regardless_of_file_order(self):
        files = _fake_files()
        manifest_a = _make_manifest(files)
        reversed_files = list(reversed(files))
        manifest_b = _make_manifest(reversed_files)
        self.assertEqual(
            canonical_sync_manifest(manifest_a),
            canonical_sync_manifest(manifest_b),
        )


if __name__ == "__main__":
    unittest.main()
