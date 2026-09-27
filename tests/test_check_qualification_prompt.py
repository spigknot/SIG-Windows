"""Os campos da vacina nao podem divergir do app.

`scripts/check_qualification_prompt.py` mantem uma copia local da lista de
campos (`CAMPOS`) porque o script roda sem instanciar o Tkinter. Essa copia
e um ponto de divergencia silencioso: se o app ganhar um campo, renomear um
rotulo ou mudar a ordem, a vacina continuaria "verificando" o contrato
antigo e nao daria erro nenhum.

O que este arquivo garante e o contrato entre o app e a vacina. O
`violacoes()` em si (CPF sem hifen, "Av" sem expandir, preposicao com
maiuscula, profissao = grau de instrucao) e exercitado abaixo com respostas
escritas a mao -- sem rede, sem GPU -- para que a regra nao dependa de o
modelo estar no ar nem do documento escolhido exercitar a regra.
"""
from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_qualification_prompt.py"
APP = ROOT / "src" / "sig_app.py"


def _load_vaccine():
    """Importa o script da pasta sem executar o `main()`."""
    spec = importlib.util.spec_from_file_location("check_qualification_prompt", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _app_qualification_fields() -> tuple[tuple[str, str], ...]:
    """Le `self.qualification_fields = (...)` do app por AST (sem Tkinter)."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t for t in node.targets if isinstance(t, ast.Attribute)]
        if not any(
            isinstance(t.value, ast.Name)
            and t.value.id == "self"
            and t.attr == "qualification_fields"
            for t in targets
        ):
            continue
        pares = []
        for element in node.value.elts:  # type: ignore[attr-defined]
            if not (isinstance(element, ast.Tuple) and len(element.elts) == 2):
                continue
            field_id, label = element.elts
            if isinstance(field_id, ast.Constant) and isinstance(label, ast.Constant):
                pares.append((str(field_id.value), str(label.value)))
        return tuple(pares)
    raise AssertionError("self.qualification_fields nao encontrado em sig_app.py")


class CamposDaVacinaTest(unittest.TestCase):
    def setUp(self):
        self.vacina = _load_vaccine()

    def test_campos_batem_com_o_app(self):
        self.assertEqual(
            list(self.vacina.CAMPOS),
            list(_app_qualification_fields()),
            "A lista CAMPOS da vacina divergiu de self.qualification_fields no app.",
        )

    def test_ids_derivam_de_campos(self):
        self.assertEqual(self.vacina.IDS, [f for f, _ in self.vacina.CAMPOS])

    def test_documento_exercita_as_regras_caras(self):
        """O BR3 precisa trazer a sigla e os pontos -- sem isso o mutation
        check passa com o prompt quebrado (ja aconteceu)."""
        doc = self.vacina.BR3
        self.assertRegex(doc, r"Av Dom Pedro II", "precisa da sigla de logradouro")
        self.assertIn("123.456.789-09", doc, "precisa de CPF com pontos")
        self.assertIn("22.333.444-5", doc, "precisa de RG com pontos")
        self.assertIn("ANTONIO", doc, "precisa de nome sem acento")
        self.assertRegex(doc, r"De Souza", "precisa de preposicao com maiuscula")
        self.assertIn("Grau instrução: Superior", doc, "precisa de escolaridade sem profissao")


class ViolacoesTest(unittest.TestCase):
    """Cada regra que a vacina promete, com a resposta que a VIOLA."""

    def setUp(self):
        self.vacina = _load_vaccine()
        self.base = {
            "nome": "Marcos Antonio de Souza",
            "cpf": "123456789-09",
            "rg": "22333444-5",
            "endereco": "Avenida Dom Pedro II, n° 1500, apto 72",
            "bairro": "Jardim America",
            "cidade": "Itapeva - SP",
            "naturalidade": "Itapeva - SP",
            "altura": "1,75m",
            "estado_civil": "Solteiro",
            "instrucao": "Superior",
        }

    def _violacoes(self, **overrides):
        campos = dict(self.base)
        campos.update(overrides)
        return self.vacina.violacoes(campos)

    def test_resposta_correta_nao_viola_nada(self):
        self.assertEqual(self._violacoes(), [])

    def test_cpf_sem_hifen(self):
        self.assertTrue(self._violacoes(cpf="12345678909"))

    def test_cpf_com_pontos(self):
        self.assertTrue(self._violacoes(cpf="123.456.789-09"))

    def test_rg_com_pontos(self):
        self.assertTrue(self._violacoes(rg="22.333.444-5"))

    def test_logradouro_nao_expandido(self):
        self.assertTrue(self._violacoes(endereco="Av Dom Pedro II, n° 1500, apto 72"))

    def test_endereco_sem_n_grau(self):
        self.assertTrue(self._violacoes(endereco="Avenida Dom Pedro II, 1500, apto 72"))

    def test_bairro_dentro_do_endereco(self):
        self.assertTrue(
            self._violacoes(endereco="Avenida Dom Pedro II, n° 1500, Bairro Jardim America")
        )

    def test_preposicao_com_maiuscula(self):
        self.assertTrue(self._violacoes(nome="Marcos Antonio De Souza"))

    def test_cidade_sem_uf(self):
        self.assertTrue(self._violacoes(cidade="Itapeva"))

    def test_altura_fora_do_formato(self):
        self.assertTrue(self._violacoes(altura="1,75 m"))

    def test_profissao_recebeu_grau_de_instrucao(self):
        # Erro de SIGNIFICADO: passa em qualquer teste de formato.
        self.assertTrue(self._violacoes(profissao="Superior"))

    def test_pai_e_mae_com_o_mesmo_nome(self):
        self.assertTrue(self._violacoes(pai="Maria de Souza", mae="Maria de Souza"))


if __name__ == "__main__":
    unittest.main()
