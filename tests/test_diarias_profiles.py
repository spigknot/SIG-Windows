"""Regras de perfis de Diárias e persistência isolada dos dados do policial."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import diarias_store
from diarias_profiles import (
    PROFILE_FIELDS,
    classe_padrao,
    format_profile_cargo,
    format_profile_name,
    validate_diarias_profile,
)


def valid_profile(**changes):
    values = {key: example for key, _label, example in PROFILE_FIELDS}
    values["classe"] = "1"
    values.update(changes)
    return values


class DiariasProfileRulesTest(unittest.TestCase):
    def test_nome2_preserva_acentos_hifens_e_particulas_portuguesas(self):
        self.assertEqual(
            format_profile_name("  JOÃO-DOMINGOS DA SILVA E DOS SANTOS  "),
            "João-Domingos da Silva e dos Santos",
        )
        self.assertEqual(format_profile_name("MARIA DE FÁTIMA D'ÁVILA"), "Maria de Fátima D'Ávila")
        self.assertEqual(format_profile_name("DE SOUZA"), "de Souza")

    def test_classe_e_cargo_cobrem_os_quatro_valores_aceitos(self):
        for classe, padrao in (("1", "III"), ("2", "II"), ("3", "I"), ("Especial", "IV")):
            with self.subTest(classe=classe):
                self.assertEqual(classe_padrao(classe), padrao)
                validated = validate_diarias_profile(valid_profile(classe=classe))
                self.assertEqual(validated["classe"], classe)
        self.assertEqual(format_profile_cargo("Investigador de Polícia", "2"),
                         "INVESTIGADOR DE POLÍCIA 2ª CLASSE")
        self.assertEqual(format_profile_cargo("Investigador de Polícia", "Especial"),
                         "INVESTIGADOR DE POLÍCIA CLASSE ESPECIAL")
        for classe in ("4", "especial", "III"):
            with self.subTest(invalid=classe), self.assertRaisesRegex(ValueError, "Classe"):
                validate_diarias_profile(valid_profile(classe=classe))

    def test_somente_pai_pode_ficar_em_branco(self):
        self.assertEqual(validate_diarias_profile(valid_profile(pai="   "))["pai"], "")
        for key, label, _example in PROFILE_FIELDS:
            if key == "pai":
                continue
            with self.subTest(field=key), self.assertRaises(ValueError) as raised:
                validate_diarias_profile(valid_profile(**{key: "  "}))
            self.assertIn(label, str(raised.exception))

    def test_nascimento_rejeita_datas_impossiveis_e_formato_incompleto(self):
        for value in ("31/02/1980", "29/02/2025", "1/12/1980", "1980-12-31", "31/12/0000"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Nascimento"):
                validate_diarias_profile(valid_profile(nascimento=value))
        self.assertEqual(validate_diarias_profile(valid_profile(nascimento="29/02/1980"))["nascimento"],
                         "29/02/1980")

    def test_indice_deve_ser_numerico_e_positivo(self):
        for value in ("0", "0,00", "-9", "NaN", "Infinity", "9a", "9,5,1"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Índice UFESP"):
                validate_diarias_profile(valid_profile(ufesp_index=value))
        for value in ("9", "9,5", "9.5"):
            with self.subTest(value=value):
                self.assertEqual(validate_diarias_profile(valid_profile(ufesp_index=value))["ufesp_index"],
                                 value)

    def test_metadados_nao_sao_campos_editaveis(self):
        validated = validate_diarias_profile(valid_profile(nome="  João da Silva  ", id="forjado"))
        self.assertEqual(validated["nome"], "João da Silva")
        self.assertNotIn("id", validated)
        with self.assertRaisesRegex(ValueError, "RG"):
            validate_diarias_profile(valid_profile(rg=1234))


class DiariasProfileStoreTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="sig_diarias_profiles_")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.settings_file = self.directory / "settings.json"
        self.settings_file.write_text('{"config_existente": true}', encoding="utf-8")
        patcher = patch.object(diarias_store, "settings_path", return_value=self.settings_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_criar_perfis_com_colisao_e_restaurar_selecao_do_disco(self):
        first = diarias_store.save_diarias_profile(valid_profile())
        second = diarias_store.save_diarias_profile(valid_profile())
        third = diarias_store.save_diarias_profile(valid_profile(nome="joão da silva"))
        self.assertEqual(first["profile_name"], "João da Silva")
        self.assertEqual(second["profile_name"], "João da Silva 2")
        self.assertEqual(third["profile_name"], "joão da silva 3")
        self.assertEqual(len({p["id"] for p in (first, second, third)}), 3)
        diarias_store.select_diarias_profile(first["id"])
        self.assertEqual(diarias_store.load_active_diarias_profile_id(), first["id"])
        self.assertEqual(diarias_store.load_diarias_profile(), first)
        self.assertEqual(diarias_store.list_diarias_profiles(), [first, second, third])
        persisted = json.loads((self.directory / "diarias_profiles.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["active_profile_id"], first["id"])
        self.assertEqual(persisted["profiles"], [first, second, third])
        self.assertEqual(self.settings_file.read_text(encoding="utf-8"), '{"config_existente": true}')

    def test_editar_preserva_id_e_outros_perfis(self):
        first = diarias_store.save_diarias_profile(valid_profile())
        second = diarias_store.save_diarias_profile(valid_profile(nome="Maria de Souza"))
        edited = diarias_store.save_diarias_profile(valid_profile(nome="Maria de Souza", pai=""), first["id"])
        self.assertEqual(edited["id"], first["id"])
        self.assertEqual(edited["profile_name"], "Maria de Souza 2")
        self.assertEqual(edited["pai"], "")
        self.assertEqual(diarias_store.load_diarias_profile(second["id"]), second)
        self.assertEqual(diarias_store.load_diarias_profile(), edited)
        edited["nome"] = "mudança só na memória"
        self.assertEqual(diarias_store.load_diarias_profile()["nome"], "Maria de Souza")

    def test_remover_ativo_seleciona_outro_e_ultimo_limpa_selecao(self):
        first = diarias_store.save_diarias_profile(valid_profile())
        second = diarias_store.save_diarias_profile(valid_profile(nome="Maria de Souza"))
        diarias_store.delete_diarias_profile(second["id"])
        self.assertEqual(diarias_store.load_diarias_profile(), first)
        diarias_store.delete_diarias_profile(first["id"])
        self.assertEqual(diarias_store.list_diarias_profiles(), [])
        self.assertEqual(diarias_store.load_active_diarias_profile_id(), "")
        self.assertIsNone(diarias_store.load_diarias_profile())

    def test_validacao_e_ids_inexistentes_nao_modificam_arquivo(self):
        saved = diarias_store.save_diarias_profile(valid_profile())
        path = self.directory / "diarias_profiles.json"
        before = path.read_bytes()
        actions = (
            lambda: diarias_store.save_diarias_profile(valid_profile(cpf="")),
            lambda: diarias_store.save_diarias_profile(valid_profile(), "missing"),
            lambda: diarias_store.select_diarias_profile("missing"),
            lambda: diarias_store.delete_diarias_profile("missing"),
        )
        for action in actions:
            with self.subTest(action=action), self.assertRaises(ValueError):
                action()
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(diarias_store.load_diarias_profile(), saved)

    def test_ufesp_padrao_preserva_valores_salvos(self):
        self.assertEqual(diarias_store.load_ufesp(), "38,42")
        diarias_store.save_holerite("10.817,23", "09/2026")
        self.assertEqual(diarias_store.load_ufesp(), "38,42")
        diarias_store.save_ufesp("40,00")
        self.assertEqual(diarias_store.load_ufesp(), "40,00")
        diarias_store.save_ufesp("")
        self.assertEqual(diarias_store.load_ufesp(), "")

    def test_ufesp_e_holerite_globais_sao_independentes_dos_perfis(self):
        diarias_store.save_ufesp("38,42")
        diarias_store.save_ufesp_index("7")
        diarias_store.save_holerite("10.817,23", "09/2026")
        source = self.directory / "entrada.pdf"
        source.write_bytes(b"%PDF-1.4\nexemplo")
        attachment = diarias_store.attach_holerite_pdf(source, "10.817,23", "09/2026")
        before = (self.directory / "diarias_holerite.json").read_bytes()
        profile = diarias_store.save_diarias_profile(valid_profile(ufesp_index="9"))
        diarias_store.delete_diarias_profile(profile["id"])
        self.assertEqual((self.directory / "diarias_holerite.json").read_bytes(), before)
        self.assertEqual(diarias_store.load_ufesp(), "38,42")
        self.assertEqual(diarias_store.load_holerite(), ("10.817,23", "09/2026"))
        self.assertEqual(diarias_store.load_holerite_pdf(), attachment)
        self.assertTrue(Path(attachment[0]).is_file())

    def test_arquivo_malformado_ou_selecao_orfa_nao_quebra_inicio(self):
        path = self.directory / "diarias_profiles.json"
        for data in ("{", "[]", '{"profiles": 42, "active_profile_id": "missing"}'):
            with self.subTest(data=data):
                path.write_text(data, encoding="utf-8")
                self.assertEqual(diarias_store.list_diarias_profiles(), [])
                self.assertIsNone(diarias_store.load_diarias_profile())
        valid = {**valid_profile(), "id": "valid-id", "profile_name": "João da Silva"}
        invalid = {**valid, "id": "invalid-id", "nascimento": "31/02/1980"}
        path.write_text(json.dumps({"profiles": [invalid, valid, valid], "active_profile_id": "missing"}),
                        encoding="utf-8")
        self.assertEqual(diarias_store.list_diarias_profiles(), [valid])
        self.assertEqual(diarias_store.load_active_diarias_profile_id(), "")


if __name__ == "__main__":
    unittest.main()
