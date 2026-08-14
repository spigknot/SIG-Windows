"""Testes do manifesto de sincronização (schema 2) do updater.

Cobre a FASE A1 do release/SYNC_BY_FILE.md: canonical, assinatura e
validação estrutural. A assinatura é feita com a chave privada local quando
disponível (round-trip real com a chave pública embutida no updater).
"""

from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))

from updater import (  # noqa: E402
    SYNC_MANIFEST_SCHEMA,
    SYNC_REQUIRED_FILES,
    UpdateError,
    canonical_sync_manifest,
    classify_sync_files,
    download_sync_file,
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


class SyncDownloadTests(unittest.TestCase):
    """FASE A3: download por arquivo com retry e validação de hash."""

    def _fake_open_drive(self, payload_factory):
        import updater

        original = updater._open_google_drive_download

        class _FakeResponse:
            def __init__(self, payload: bytes):
                self._payload = payload
                self._offset = 0

            def read(self, size=-1):
                if size < 0:
                    size = len(self._payload) - self._offset
                chunk = self._payload[self._offset : self._offset + size]
                self._offset += len(chunk)
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        calls = {"count": 0}
        sequence = payload_factory() if callable(payload_factory) else payload_factory

        def fake(drive_id):
            calls["count"] += 1
            payload = next(sequence)
            if isinstance(payload, Exception):
                raise payload
            return _FakeResponse(payload)

        updater._open_google_drive_download = fake
        self.addCleanup(lambda: setattr(updater, "_open_google_drive_download", original))
        return calls

    def _entry(self, data: bytes) -> dict:
        import hashlib

        return {
            "drive_id": "fake-id",
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }

    def test_download_writes_validated_file(self):
        data = b"conteudo do arquivo"
        calls = self._fake_open_drive(iter([data]))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "sig.exe"
            download_sync_file(self._entry(data), destination)
            self.assertEqual(destination.read_bytes(), data)
            self.assertFalse(Path(str(destination) + ".part").exists())
        self.assertEqual(calls["count"], 1)

    def test_divergent_hash_is_rejected(self):
        data = b"conteudo bom"
        calls = self._fake_open_drive(iter([b"conteudo adulterado"] * 3))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "sig.exe"
            with self.assertRaisesRegex(UpdateError, "após 3 tentativas"):
                download_sync_file(self._entry(data), destination)
            self.assertFalse(destination.exists())
        self.assertEqual(calls["count"], 3)

    def test_transient_failure_recovers_on_retry(self):
        data = b"arquivo certo"
        calls = self._fake_open_drive(iter([ConnectionError("rede caiu"), data]))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "sig.exe"
            download_sync_file(self._entry(data), destination)
            self.assertEqual(destination.read_bytes(), data)
        self.assertEqual(calls["count"], 2)

    def test_oversized_payload_is_rejected(self):
        data = b"pequeno"
        calls = self._fake_open_drive(iter([b"grande demais"] * 3))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "sig.exe"
            with self.assertRaises(UpdateError):
                download_sync_file(self._entry(data), destination)

    def test_progress_callback_reports_bytes(self):
        data = b"x" * 300_000
        calls = self._fake_open_drive(iter([data]))
        seen = []
        with tempfile.TemporaryDirectory() as temporary:
            download_sync_file(
                self._entry(data),
                Path(temporary) / "sig.exe",
                progress_callback=lambda done, total: seen.append((done, total)),
            )
        self.assertTrue(seen)
        self.assertEqual(seen[-1], (len(data), len(data)))


class SyncClassificationTests(unittest.TestCase):
    """FASE A2: classificação local contra o manifesto de sincronização."""

    def _make_target(self, files: dict[str, bytes]) -> str:
        import tempfile

        temporary = tempfile.mkdtemp(prefix="sig-sync-classify-")
        self.addCleanup(lambda: __import__("shutil").rmtree(temporary, ignore_errors=True))
        target = Path(temporary)
        for name, data in files.items():
            path = target / Path(*PurePosixPath(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return str(target)

    @staticmethod
    def _hash(data: bytes) -> str:
        import hashlib

        return hashlib.sha256(data).hexdigest()

    def _files(self, content: dict[str, bytes]) -> dict[str, dict]:
        return {
            name: {"sha256": self._hash(data), "size": len(data), "drive_id": f"id-{name}"}
            for name, data in content.items()
        }

    def test_identical_files_are_unchanged(self):
        content = {"sig.exe": b"sig", "_internal/base_library.zip": b"base"}
        target = self._make_target(content)
        result = classify_sync_files(Path(target), self._files(content))
        self.assertEqual(result["download"], [])
        self.assertEqual(result["remove"], [])
        self.assertEqual(result["unchanged"], 2)

    def test_missing_file_is_download(self):
        content = {"sig.exe": b"sig"}
        target = self._make_target({"sig.exe": b"sig"})
        files = self._files(content)
        files["_internal/base_library.zip"] = {
            "sha256": "a" * 64,
            "size": 4,
            "drive_id": "id-base",
        }
        result = classify_sync_files(Path(target), files)
        self.assertIn("_internal/base_library.zip", result["download"])

    def test_divergent_content_is_download(self):
        content = {"sig.exe": b"sig"}
        target = self._make_target({"sig.exe": b"VELHO"})
        result = classify_sync_files(Path(target), self._files(content))
        self.assertIn("sig.exe", result["download"])

    def test_divergent_size_is_download(self):
        content = {"sig.exe": b"sig"}
        target = self._make_target({"sig.exe": b"sig-exe-maior"})
        result = classify_sync_files(Path(target), self._files(content))
        self.assertIn("sig.exe", result["download"])

    def test_orphans_inside_managed_top_levels_are_removed(self):
        content = {"sig.exe": b"sig", "_internal/base_library.zip": b"base"}
        target = self._make_target(
            {
                "sig.exe": b"sig",
                "_internal/base_library.zip": b"base",
                "_internal/antiga.dll": b"velha",
                "prompts/velho.txt": b"velho",
            }
        )
        result = classify_sync_files(Path(target), self._files(content))
        self.assertEqual(
            sorted(result["remove"]),
            ["_internal/antiga.dll", "prompts/velho.txt"],
        )

    def test_unmanaged_files_are_not_removed(self):
        content = {"sig.exe": b"sig"}
        target = self._make_target(
            {"sig.exe": b"sig", "settings.json": b"usuario", "logs/run.log": b"x"}
        )
        result = classify_sync_files(Path(target), self._files(content))
        self.assertEqual(result["remove"], [])
