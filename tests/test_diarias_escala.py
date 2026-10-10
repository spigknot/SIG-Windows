"""Persistência da escala: cópia local, edição do mês e troca segura do anexo."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import diarias_store


class EscalaStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        storage = patch.object(diarias_store, "settings_path", return_value=self.directory / "usuario" / "settings.json")
        storage.start()
        self.addCleanup(storage.stop)
        self.source = self.directory / "escala_original.pdf"
        self.source.write_bytes(b"escala original")

    def test_reabre_a_copia_e_mes_mesmo_apos_mover_o_original(self):
        stored, name = diarias_store.attach_escala_pdf(self.source, "10/2026")
        self.source.unlink()
        self.assertEqual(diarias_store.load_escala(), (stored, name, "10/2026"))
        self.assertEqual(Path(stored).read_bytes(), b"escala original")
        diarias_store.save_escala_month("11/2026")
        self.assertEqual(diarias_store.load_escala(), (stored, name, "11/2026"))
        Path(stored).unlink()
        self.assertEqual(diarias_store.load_escala(), ("", "", ""))

    def test_falha_na_gravacao_preserva_o_anexo_anterior(self):
        first = diarias_store.attach_escala_pdf(self.source, "10/2026")
        self.source.write_bytes(b"escala nova")
        with patch.object(diarias_store, "_write_escala_data", side_effect=OSError("falha simulada")):
            with self.assertRaisesRegex(OSError, "falha simulada"):
                diarias_store.attach_escala_pdf(self.source, "11/2026")
        self.assertEqual(diarias_store.load_escala(), (*first, "10/2026"))
        self.assertEqual(list(Path(first[0]).parent.iterdir()), [Path(first[0])])
        self.assertEqual(Path(first[0]).read_bytes(), b"escala original")

    def test_troca_de_escala_remove_so_a_copia_antiga(self):
        first, _ = diarias_store.attach_escala_pdf(self.source, "10/2026")
        second, name = diarias_store.attach_escala_pdf(self.source, "11/2026")
        self.assertFalse(Path(first).exists())
        self.assertTrue(self.source.is_file())
        self.assertEqual(diarias_store.load_escala(), (second, name, "11/2026"))


if __name__ == "__main__":
    unittest.main()
