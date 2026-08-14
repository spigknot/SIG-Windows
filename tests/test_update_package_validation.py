"""Testes permanentes da validação do pacote de atualização do SIG.

Cobre o bug de 2026-08-14: a validação do download (formato diff vs formato
antigo) ficou desatualizada quando a incremental virou diff, rejeitando
pacotes válidos com "componentes obrigatórios ausentes".

Regra: QUALQUER mudança no formato de pacote precisa passar por aqui E pelo
updater (updater_v2/test_updater.py) — veja release/INCREMENTAL_V2.md,
seção "Peças afetadas por mudanças de formato".
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import sig_app  # noqa: E402


class UpdatePackageValidationTests(unittest.TestCase):
    """Exercita SigApp._validate_update_package_archive (estático, sem GUI)."""

    V1_REQUIRED = {
        "sig.exe",
        "_internal/base_library.zip",
        "_internal/python311.dll",
        "_internal/vcruntime140.dll",
        "_internal/vcruntime140_1.dll",
        "_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll",
        "SigUpdater.exe",
    }

    def _write_zip(self, destination: Path, members: dict[str, bytes]) -> None:
        with zipfile.ZipFile(destination, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)

    def _validate(self, members: dict[str, bytes], staging: Path):
        zip_path = staging.parent / "package.zip"
        self._write_zip(zip_path, members)
        sig_app.SigApp._validate_update_package_archive(zip_path, staging)
        return zip_path

    def test_diff_package_with_empty_removidos_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            staging.mkdir()
            self._validate(
                {
                    "sig.exe": b"sig",
                    "build-info.json": '{"version": "20260814_010"}',
                    "removidos.txt": b"",
                },
                staging,
            )
            self.assertTrue((staging / "sig.exe").is_file())
            self.assertTrue((staging / "removidos.txt").is_file())
            self.assertEqual((staging / "removidos.txt").stat().st_size, 0)

    def test_diff_package_with_removals_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            staging.mkdir()
            self._validate(
                {
                    "sig.exe": b"sig",
                    "build-info.json": '{"version": "20260814_010"}',
                    "removidos.txt": b"_internal/old.dll\n",
                    "_internal/new.dll": b"novo",
                },
                staging,
            )
            self.assertTrue((staging / "_internal" / "new.dll").is_file())

    def test_diff_package_without_removidos_txt_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            staging.mkdir()
            with self.assertRaisesRegex(RuntimeError, "componentes obrigatórios ausentes"):
                self._validate(
                    {
                        "sig.exe": b"sig",
                        "build-info.json": '{"version": "20260814_010"}',
                    },
                    staging,
                )

    def test_v1_package_is_still_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            staging.mkdir()
            members = {name: b"fixture" for name in self.V1_REQUIRED}
            self._validate(members, staging)
            self.assertTrue((staging / "_internal" / "python311.dll").is_file())

    def test_v1_package_missing_essential_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            staging.mkdir()
            members = {name: b"fixture" for name in self.V1_REQUIRED}
            members.pop("_internal/python311.dll")
            with self.assertRaisesRegex(RuntimeError, "componentes obrigatórios ausentes"):
                self._validate(members, staging)

    def test_traversal_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            staging.mkdir()
            members = {
                "sig.exe": b"sig",
                "build-info.json": '{"version": "20260814_010"}',
                "removidos.txt": b"",
                "../fora.txt": b"bad",
            }
            with self.assertRaisesRegex(RuntimeError, "entrada inválida"):
                self._validate(members, staging)

    def test_diff_without_essentials_does_not_demand_them(self):
        """O núcleo do bug: diff não carrega DLLs essenciais e ainda assim passa."""
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            staging.mkdir()
            self._validate(
                {
                    "sig.exe": b"sig",
                    "build-info.json": '{"version": "20260814_010"}',
                    "removidos.txt": b"",
                },
                staging,
            )
            # Nada de python311.dll/portaudio no ZIP — e a validação não exige.


if __name__ == "__main__":
    unittest.main()
