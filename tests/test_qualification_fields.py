"""Testes da formatação da qualificação da Ocorrência (caixa do documento).

Cobre a regressão vacinada: as checkboxes da engrenagem decidem quais campos
do JSON entram na caixa; RG/CPF aparecem logo após o nome com a sigla em
maiúsculas (RG: ... / CPF: ...); o default inclui RG mas não CPF.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sig_app import (  # noqa: E402
    LIVE_QUALIFICATION_DEFAULT_SELECTED,
    LIVE_QUALIFICATION_FIELD_IDS,
    format_occurrence_qualification,
    parse_qualification_json,
)

FIELD_ORDER = tuple(
    (field_id, field_id) for field_id in LIVE_QUALIFICATION_FIELD_IDS
)

SAMPLE = {
    "nome": "maicon cristiano fernandes",
    "rg": "48358237",
    "cpf": "123.456.789-00",
    "nascimento": "12/03/1990",
    "naturalidade": "Taguaí/SP",
    "profissao": "policial militar",
    "pai": "Adail Aparecido Fernandes",
    "mae": "Marina Rosa",
    "endereco": "Rua das Flores, 123",
    "bairro": "Centro",
    "cidade": "Taguaí",
    "telefone": "(14) 99999-0000",
}


def render(selected=None):
    return format_occurrence_qualification(
        json.dumps(SAMPLE, ensure_ascii=False),
        FIELD_ORDER,
        selected,
    )


class QualificationFieldSelectionTests(unittest.TestCase):
    def test_default_includes_rg_right_after_name(self):
        # Regressão vacinada: RG é o segundo item, logo após o NOME em
        # maiúsculas, com a sigla "RG:" em maiúsculas.
        text = render()
        self.assertTrue(text.startswith(
            "MAICON CRISTIANO FERNANDES, RG: 48358237,"
        ), text)

    def test_default_does_not_include_cpf(self):
        # CPF NÃO entra no default (só quando o usuário marcar a checkbox).
        self.assertNotIn("CPF:", render())

    def test_all_fields_include_cpf_after_rg(self):
        text = render(set(LIVE_QUALIFICATION_FIELD_IDS))
        self.assertIn("MAICON CRISTIANO FERNANDES, RG: 48358237, CPF: 123.456.789-00,", text)

    def test_cpf_sigla_uppercase(self):
        text = render({"nome", "cpf"})
        self.assertIn("CPF: 123.456.789-00", text)
        self.assertNotIn("cpf:", text)

    def test_rg_sigla_uppercase(self):
        text = render({"nome", "rg"})
        self.assertIn("RG: 48358237", text)
        self.assertNotIn("rg:", text)

    def test_subset_of_fields_only(self):
        text = render({"nome", "mae", "pai", "cidade"})
        self.assertEqual(
            text,
            "MAICON CRISTIANO FERNANDES, filho(a) de Marina Rosa e "
            "Adail Aparecido Fernandes, de nacionalidade Brasileira, "
            "na cidade de Taguaí.",
        )

    def test_omitted_fields_are_excluded(self):
        text = render({"nome", "telefone"})
        self.assertIn("MAICON CRISTIANO FERNANDES,", text)
        self.assertIn("Telefone: (14) 99999-0000", text)
        self.assertNotIn("filho(a)", text)
        self.assertNotIn("natural de", text)
        self.assertNotIn("residente", text)

    def test_nationality_always_present(self):
        # Nacionalidade Brasileira é fixa do modelo, independente das boxes.
        for selected in (None, {"nome"}, set(LIVE_QUALIFICATION_FIELD_IDS)):
            self.assertIn("de nacionalidade Brasileira", render(selected))

    def test_empty_text_without_fields(self):
        # Com nenhum campo selecionado sobra apenas a nacionalidade fixa do
        # modelo (não é campo do JSON, não tem checkbox).
        self.assertEqual(render(set()), "de nacionalidade Brasileira.")

    def test_default_selected_matches_documented_set(self):
        self.assertIn("nome", LIVE_QUALIFICATION_DEFAULT_SELECTED)
        self.assertIn("rg", LIVE_QUALIFICATION_DEFAULT_SELECTED)
        self.assertNotIn("cpf", LIVE_QUALIFICATION_DEFAULT_SELECTED)


class QualificationParseTests(unittest.TestCase):
    def test_parse_keeps_only_live_ids(self):
        payload = dict(SAMPLE)
        payload["estado_civil"] = "Casado"  # fora da lista live
        fields = parse_qualification_json(
            json.dumps(payload, ensure_ascii=False),
            list(LIVE_QUALIFICATION_FIELD_IDS),
            FIELD_ORDER,
        )
        self.assertNotIn("estado_civil", fields)
        self.assertIn("rg", fields)

    def test_parse_skips_empty_values(self):
        payload = dict(SAMPLE, rg="", cpf=None)
        fields = parse_qualification_json(
            json.dumps(payload, ensure_ascii=False),
            list(LIVE_QUALIFICATION_FIELD_IDS),
            FIELD_ORDER,
        )
        self.assertNotIn("rg", fields)
        self.assertNotIn("cpf", fields)


if __name__ == "__main__":
    unittest.main()
