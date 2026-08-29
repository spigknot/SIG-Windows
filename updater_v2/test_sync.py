"""Testes do manifesto de sincronização (schema 2) do updater.

Cobre o protocolo R2: canonical, assinatura e validação estrutural. A assinatura
é feita com a chave privada local quando
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
                "drive_id": "",
                "github_url": "https://pub-abb3913e7d83457bae19e41b1e4020cc.r2.dev/" + path,
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
            {
                "path": "../fora.txt",
                "sha256": "a" * 64,
                "size": 1,
                "drive_id": "",
                "github_url": "https://pub-abb3913e7d83457bae19e41b1e4020cc.r2.dev/fora.txt",
            }
        ]
        manifest = _make_manifest(files)
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        with self.assertRaises(UpdateError):
            validate_sync_manifest(manifest)

    def test_unknown_top_level_is_ignored(self):
        """Componente de top-level desconhecido NÃO rejeita o manifesto.

        Vacina forward-compat: uma release nova pode adicionar um runtime
        asset (ex.: ffprobe.exe) que esta versão do updater não conhece.
        Rejeitar o manifesto inteiro por causa dele travaria instalações
        antigas sem atualizar. A entrada desconhecida é ignorada; os
        obrigatórios seguem validados (testado em
        test_missing_essential_is_rejected).
        """
        files = _fake_files() + [
            {
                "path": "outra_pasta/x.txt",
                "sha256": "a" * 64,
                "size": 1,
                "drive_id": "",
                "github_url": "https://pub-abb3913e7d83457bae19e41b1e4020cc.r2.dev/outra_pasta/x.txt",
            }
        ]
        manifest = _make_manifest(files)
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        result = validate_sync_manifest(manifest)
        self.assertNotIn("outra_pasta/x.txt", result["files"])

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

    def test_missing_download_source_is_rejected(self):
        files = _fake_files({"sig.exe": {"drive_id": "", "github_url": ""}})
        manifest = _make_manifest(files)
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        with self.assertRaisesRegex(UpdateError, "URL de download"):
            validate_sync_manifest(manifest)

    def test_github_url_without_drive_id_is_accepted(self):
        if PRIVATE_KEY is None:
            self.skipTest("chave privada de teste indisponível")
        files = _fake_files(
            {"sig.exe": {"drive_id": "", "github_url": "https://github.com/spigknot/SIG-Windows/releases/download/20260815_017/sig.exe"}}
        )
        validated = validate_sync_manifest(_make_manifest(files))
        self.assertIn("github_url", validated["files"]["sig.exe"])

    def test_invalid_github_url_is_rejected(self):
        files = _fake_files(
            {"sig.exe": {"github_url": "https://evil.com/x/sig.exe"}}
        )
        manifest = _make_manifest(files)
        if PRIVATE_KEY is not None:
            manifest["signature"] = _sign(canonical_sync_manifest(manifest))
        with self.assertRaisesRegex(UpdateError, "URL de download"):
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


class SyncTransactionTests(unittest.TestCase):
    """FASE A4: transação por arquivo (substituição + remoção + rollback)."""

    def _make_install(self, files: dict[str, bytes]) -> str:
        temporary = tempfile.mkdtemp(prefix="sig-sync-txn-")
        self.addCleanup(lambda: __import__("shutil").rmtree(temporary, ignore_errors=True))
        target = Path(temporary)
        required = {
            "sig.exe": b"fixture-sig",
            "SigUpdater.exe": b"fixture-updater",
            "build-info.json": b'{"version": "20260814_010"}',
            "_internal/base_library.zip": b"fixture",
            "_internal/python311.dll": b"fixture",
            "_internal/vcruntime140.dll": b"fixture",
            "_internal/vcruntime140_1.dll": b"fixture",
            "_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll": b"fixture",
            "ffmpeg.exe": b"fixture",
            "ffplay.exe": b"fixture",
            "vad_worker.py": b"fixture",
            "vad_deps/fixture.txt": b"fixture",
        }
        required.update(files)
        for name, data in required.items():
            path = target / Path(*PurePosixPath(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return temporary

    def _make_staged(self, root: Path, files: dict[str, bytes]) -> Path:
        staged = root / "staged"
        for name, data in files.items():
            path = staged / Path(*PurePosixPath(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return staged

    def test_launch_failure_rolls_back_everything(self):
        import updater as updater_module

        target = Path(self._make_install(
            {"_internal/antiga.dll": b"velha", "prompts/velho.txt": b"velho"}
        ))
        root = target
        staged = self._make_staged(root, {"_internal/nova.dll": b"nova"})
        transaction = root / "txn"
        transaction.mkdir()
        log = root / "updater.log"
        with self.assertRaises(Exception):
            updater_module._apply_file_transaction(
                staged,
                target,
                transaction,
                startup_timeout=1,
                log_path=log,
                removals=["_internal/antiga.dll"],
            )
        # rollback: a antiga.dll voltou, a nova.dll não ficou, o sig original intacto
        self.assertTrue((target / "_internal" / "antiga.dll").is_file())
        self.assertEqual((target / "_internal" / "antiga.dll").read_bytes(), b"velha")
        self.assertFalse((target / "_internal" / "nova.dll").exists())
        self.assertEqual((target / "sig.exe").read_bytes(), b"fixture-sig")
        self.assertIn("Rollback concluído", log.read_text(encoding="utf-8", errors="replace"))

    def test_empty_transaction_is_rejected(self):
        import updater as updater_module

        target = Path(self._make_install({}))
        root = target
        staged = self._make_staged(root, {})
        transaction = root / "txn"
        transaction.mkdir()
        log = root / "updater.log"
        with self.assertRaisesRegex(UpdateError, "não contém arquivos"):
            updater_module._apply_file_transaction(
                staged, target, transaction, startup_timeout=1, log_path=log, removals=[]
            )

    def test_removal_only_rolls_back_removed_file(self):
        import updater as updater_module

        target = Path(self._make_install({"_internal/orfa.dll": b"orfa"}))
        root = target
        staged = self._make_staged(root, {})
        transaction = root / "txn"
        transaction.mkdir()
        log = root / "updater.log"
        with self.assertRaises(Exception):
            updater_module._apply_file_transaction(
                staged, target, transaction, startup_timeout=1, log_path=log, removals=["_internal/orfa.dll"]
            )
        self.assertEqual((target / "_internal" / "orfa.dll").read_bytes(), b"orfa")

    def test_atomic_move_falls_back_across_drives(self):
        import os as os_module

        import updater as updater_module

        root = Path(tempfile.mkdtemp(prefix="sig-sync-xdrive-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        source = root / "origem.bin"
        destination = root / "destino.bin"
        source.write_bytes(b"conteudo")

        def fake_replace(src, dst):
            error = OSError("cross-device")
            error.winerror = 17
            raise error

        original_replace = os_module.replace
        updater_module.os.replace = fake_replace
        self.addCleanup(lambda: setattr(updater_module.os, "replace", original_replace))
        updater_module._atomic_move(source, destination)
        self.assertEqual(destination.read_bytes(), b"conteudo")
        self.assertFalse(source.exists())


class SyncDownloadTests(unittest.TestCase):
    """FASE A3: download por arquivo com retry e validação de hash."""

    def _fake_open_r2(self, payload_factory):
        import updater

        original = updater._urlopen

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

        def fake(_request, timeout=60):
            calls["count"] += 1
            payload = next(sequence)
            if isinstance(payload, Exception):
                raise payload
            return _FakeResponse(payload)

        updater._urlopen = fake
        self.addCleanup(lambda: setattr(updater, "_urlopen", original))
        return calls

    def _entry(self, data: bytes) -> dict:
        import hashlib

        return {
            "drive_id": "",
            "github_url": "https://pub-abb3913e7d83457bae19e41b1e4020cc.r2.dev/sig.exe",
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }

    def test_download_writes_validated_file(self):
        data = b"conteudo do arquivo"
        calls = self._fake_open_r2(iter([data]))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "sig.exe"
            download_sync_file(self._entry(data), destination)
            self.assertEqual(destination.read_bytes(), data)
            self.assertFalse(Path(str(destination) + ".part").exists())
        self.assertEqual(calls["count"], 1)

    def test_divergent_hash_is_rejected(self):
        data = b"conteudo bom"
        calls = self._fake_open_r2(iter([b"conteudo adulterado"] * 3))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "sig.exe"
            with self.assertRaisesRegex(UpdateError, "após 3 tentativas"):
                download_sync_file(self._entry(data), destination)
            self.assertFalse(destination.exists())
        self.assertEqual(calls["count"], 3)

    def test_transient_failure_recovers_on_retry(self):
        data = b"arquivo certo"
        calls = self._fake_open_r2(iter([ConnectionError("rede caiu"), data]))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "sig.exe"
            download_sync_file(self._entry(data), destination)
            self.assertEqual(destination.read_bytes(), data)
        self.assertEqual(calls["count"], 2)

    def test_oversized_payload_is_rejected(self):
        data = b"pequeno"
        calls = self._fake_open_r2(iter([b"grande demais"] * 3))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "sig.exe"
            with self.assertRaises(UpdateError):
                download_sync_file(self._entry(data), destination)

    def test_progress_callback_reports_bytes(self):
        data = b"x" * 300_000
        calls = self._fake_open_r2(iter([data]))
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
