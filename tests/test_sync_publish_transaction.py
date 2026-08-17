"""F1: publicação sync idempotente/transacional.

Cobre: (a) a retomada só reutiliza arquivo remoto comprovadamente idêntico
(tamanho + sha256Checksum); (b) a ordem publish -> deletes — uma falha de
publicação preserva o manifesto anterior (nada é apagado antes).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import sync_publish  # noqa: E402


def _b64(hex_digest: str) -> str:
    return sync_publish.sha256_checksum_b64(hex_digest)


class RemoteMatchesTest(unittest.TestCase):
    ENTRY = {"size": 1234, "sha256": "ab" * 32}

    def test_identical_remote_is_reused(self):
        remote = {"id": "abc", "size": 1234, "sha256_checksum": _b64("ab" * 32)}
        self.assertTrue(sync_publish.remote_matches(remote, self.ENTRY))

    def test_divergent_size_is_not_reused(self):
        remote = {"id": "abc", "size": 999, "sha256_checksum": _b64("ab" * 32)}
        self.assertFalse(sync_publish.remote_matches(remote, self.ENTRY))

    def test_divergent_checksum_is_not_reused(self):
        remote = {"id": "abc", "size": 1234, "sha256_checksum": _b64("cd" * 32)}
        self.assertFalse(sync_publish.remote_matches(remote, self.ENTRY))

    def test_missing_checksum_is_not_reused(self):
        remote = {"id": "abc", "size": 1234, "sha256_checksum": ""}
        self.assertFalse(sync_publish.remote_matches(remote, self.ENTRY))

    def test_checksum_base64_format(self):
        # base64 do digest binário (não do hex em texto).
        import base64

        self.assertEqual(
            _b64("ab" * 32),
            base64.b64encode(bytes.fromhex("ab" * 32)).decode("ascii"),
        )


class _FakeFiles:
    """Registra a ordem das chamadas update/delete no service fake."""

    def __init__(self, fail_update: bool = False):
        self.calls: list[str] = []
        self.fail_update = fail_update
        self.deleted: list[str] = []

    def update(self, **kwargs):
        if self.fail_update:
            raise RuntimeError("publicação falhou (simulada)")
        self.calls.append("update")
        return type("Updated", (), {"execute": lambda _self: {"id": "manifest-id"}})()

    def get(self, **kwargs):
        import pathlib

        return type(
            "Got",
            (),
            {
                "execute": lambda _self: {
                    "id": "manifest-id",
                    "size": pathlib.Path(sync_publish.MANIFEST_PATH).stat().st_size,
                }
            },
        )()

    def delete(self, **kwargs):
        self.calls.append("delete")
        self.deleted.append(kwargs.get("fileId"))
        return type("Deleted", (), {"execute": lambda _self: None})()

    def list(self, **kwargs):
        return type("Listed", (), {"execute": lambda _self: {"files": [], "nextPageToken": ""}})()


class _FakeService:
    def __init__(self, files: _FakeFiles):
        self._files = files

    def files(self):
        return self._files


class _StateFile:
    def __init__(self):
        self.saved = None


class PublishOrderTest(unittest.TestCase):
    def _state(self):
        return {"files": {}, "sync_folder_id": "folder", "manifest_file_id": "old-manifest"}

    def test_publish_happens_before_deletes(self):
        files = _FakeFiles()
        service = _FakeService(files)
        # Neutraliza o save_state (escreve no disco do projeto) via monkeypatch.
        original_save = sync_publish.save_state
        sync_publish.save_state = lambda state: None
        try:
            manifest_id = sync_publish._finalize_publish(
                service,
                self._state(),
                previous={"removed.txt": {"drive_id": "old-id"}},
                to_delete=["removed.txt"],
                superseded_ids=["stale-id"],
                manifest={"schema": 2},
            )
        finally:
            sync_publish.save_state = original_save
        self.assertEqual(manifest_id, "manifest-id")
        self.assertEqual(files.calls[0], "update")
        self.assertIn("delete", files.calls)
        self.assertEqual(files.deleted, ["old-id", "stale-id"])

    def test_publish_failure_skips_deletes(self):
        files = _FakeFiles(fail_update=True)
        service = _FakeService(files)
        original_save = sync_publish.save_state
        sync_publish.save_state = lambda state: None
        try:
            with self.assertRaises(RuntimeError):
                sync_publish._finalize_publish(
                    service,
                    self._state(),
                    previous={"removed.txt": {"drive_id": "old-id"}},
                    to_delete=["removed.txt"],
                    superseded_ids=[],
                    manifest={"schema": 2},
                )
        finally:
            sync_publish.save_state = original_save
        # Nenhum delete: o manifesto anterior permanece íntegro.
        self.assertEqual(files.calls, [])
        self.assertEqual(files.deleted, [])


if __name__ == "__main__":
    unittest.main()
