"""Regras da vacina da oitiva, exercitadas sem rede (respostas escritas a mao).

`scripts/check_oitiva_prompt.py` chama o modelo de verdade; isso nao entra no
pytest (depende de rede e GPU). Mas o JULGAMENTO (`violacoes()`) nao pode
depender de o servidor estar no ar nem de o material escolhido exercitar a
regra: e aqui que cada regra e exercitada com uma resposta que a viola.

Regras cobertas (o que o prompt promete e o que ja falhou de verdade):
  - texto em UMA unica linha (a quebra depois de cada `;` que motivou a vacina);
  - `; ` com exatamente um espaco;
  - abertura fixa, no masculino para homem, com o trecho `/WhatsApp` literal
    (o modelo escrevia "intimada ... pelo telefone fornecido" para um homem);
  - sentencas atomicas iniciadas por "que" e ultima sentenca com ponto final;
  - voz formal ("declarante"/"depoente");
  - dados probatorios preservados (valores, objetos, suspeito) e nomes proprios
    em MAIUSCULAS.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_oitiva_prompt.py"


def _load_vaccine():
    """Importa o script da pasta sem executar o `main()`."""
    spec = importlib.util.spec_from_file_location("check_oitiva_prompt", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# Resposta CORRETA de referencia: uma linha, abertura masculina literal,
# sentencas atomicas, dados do material presentes e nomes em MAIUSCULAS.
BOOLA = (
    "que aceita ser intimado pelo telefone/WhatsApp fornecido; que é vítima dos fatos; "
    "que é pedreiro e estava trabalhando em uma obra em uma residência no local dos fatos, neste município de Taguaí; "
    "que a obra fica sem qualquer vigilância durante a noite; "
    "que nesta madrugada alguém entrou no local e furtou de dentro da obra um martelete e um radinho pequeno de pilha, de propriedade do declarante; "
    "que o autor pulou a madeira colocada para fechar a frente da obra; "
    "que a madeira tem mais de 2 metros de altura e possui cadeado; "
    "que ficaram marcas de pés na madeira por onde o autor pulou; "
    "que o martelete e o radinho estavam na sala do imóvel, cuja porta estava encostada; "
    "que o martelete vale R$ 925,00 (novecentos e vinte e cinco reais) e o radinho de pilha R$ 80,00 (oitenta reais); "
    "que conseguiu imagens de câmeras de segurança que gravaram o ocorrido; "
    "que nas imagens aparece o autor pulando a madeira; "
    "que imagina que o autor seja DIEGO \"RETRANQUINHA\", a quem já conhece na cidade; "
    "que ficou sabendo que DIEGO \"RETRANQUINHA\" está praticando vários furtos nos últimos dias em Taguaí."
)


class MaterialDaVacinaTest(unittest.TestCase):
    def setUp(self):
        self.vacina = _load_vaccine()

    def test_material_preserva_as_quebras_do_documento(self):
        """O material precisa chegar como chega no app: colado do BO, com as
        quebras de linha do documento. Normalizado numa linha unica, o defeito
        NAO se reproduz (medido: o modelo devolveu tudo numa linha) e a vacina
        vira decoracao."""
        self.assertIn("\n", self.vacina.MATERIAL)
        self.assertIn("DIEGO \"RETRANQUINHA\"", self.vacina.MATERIAL)
        self.assertIn("R$ 925,00", self.vacina.MATERIAL)

    def test_dados_obrigatorios_estao_no_material(self):
        """Cada dado que a vacina cobra na resposta existe no material -- sem
        isso a regra reprovaria o modelo por um dado que nunca foi fornecido."""
        for dado, motivo in self.vacina.DADOS_OBRIGATORIOS:
            self.assertIn(dado, self.vacina.MATERIAL, f"{dado!r} ({motivo}) fora do material")
        self.assertRegex(self.vacina.MATERIAL, self.vacina.ALTURA)

    def test_abertura_e_estrita_de_genero(self):
        """O material e de um homem: a vacina exige "intimado"."""
        self.assertIsNotNone(self.vacina.ABERTURA.match(BOOLA))
        self.assertIsNone(
            self.vacina.ABERTURA.match(BOOLA.replace("intimado", "intimada")),
            "a abertura feminina nao pode passar num material de homem",
        )


class ViolacoesTest(unittest.TestCase):
    """Cada regra que a vacina promete, com a resposta que a VIOLA."""

    def setUp(self):
        self.vacina = _load_vaccine()

    def _violacoes(self, texto: str) -> list[str]:
        return self.vacina.violacoes(texto)

    def test_resposta_correta_nao_viola_nada(self):
        self.assertEqual(self._violacoes(BOOLA), [])

    def test_quebra_de_linha_depois_do_ponto_e_virgula(self):
        texto = BOOLA.replace("; ", ";\n")
        problemas = self._violacoes(texto)
        self.assertTrue(
            any("quebra de linha" in p for p in problemas),
            f"a quebra de linha precisa ser reprovada; veio: {problemas}",
        )

    def test_ponto_e_virgula_sem_espaco(self):
        self.assertTrue(any("espaco" in p for p in self._violacoes(BOOLA.replace("; que", ";que"))))

    def test_abertura_sem_whatsapp(self):
        texto = BOOLA.replace("/WhatsApp", "")
        self.assertTrue(any("abertura" in p for p in self._violacoes(texto)))

    def test_abertura_no_feminino_para_homem(self):
        texto = BOOLA.replace("ser intimado", "ser intimada")
        self.assertTrue(any("abertura" in p for p in self._violacoes(texto)))

    def test_numero_de_telefone_na_abertura(self):
        texto = BOOLA.replace(
            "fornecido; que é vítima",
            "fornecido (11) 99999-8888; que é vítima",
        )
        self.assertTrue(any("digito" in p or "numero" in p for p in self._violacoes(texto)))

    def test_sentenca_sem_que(self):
        texto = BOOLA.replace("que a obra fica", "a obra fica")
        self.assertTrue(any("nao comeca com 'que'" in p for p in self._violacoes(texto)))

    def test_ultima_sentenca_sem_ponto_final(self):
        texto = BOOLA.rstrip(".")
        self.assertTrue(any("sem ponto final" in p for p in self._violacoes(texto)))

    def test_ponto_no_meio_do_texto(self):
        # "... durante a noite. que nesta madrugada ..." -- sentenca terminada
        # antes do fim (o prompt manda a ultima ser a unica com ponto final).
        texto = BOOLA.replace(
            "durante a noite; que nesta madrugada",
            "durante a noite. que nesta madrugada",
        )
        self.assertTrue(any("termina antes do fim" in p for p in self._violacoes(texto)))

    def test_sem_declarante_nem_depoente(self):
        texto = BOOLA.replace("de propriedade do declarante", "de sua propriedade")
        self.assertTrue(any("declarante" in p for p in self._violacoes(texto)))

    def test_dado_ausente(self):
        texto = BOOLA.replace(" R$ 80,00 (oitenta reais)", "")
        self.assertTrue(any("dado ausente" in p and "R$ 80,00" in p for p in self._violacoes(texto)))

    def test_altura_ausente(self):
        texto = BOOLA.replace("mais de 2 metros de altura", "de grande altura")
        self.assertTrue(any("altura" in p for p in self._violacoes(texto)))

    def test_nome_proprio_fora_de_maiusculas(self):
        texto = BOOLA.replace("DIEGO", "Diego")
        self.assertTrue(any("MAIUSCULAS" in p for p in self._violacoes(texto)))

    def test_resposta_vazia(self):
        self.assertTrue(any("vazia" in p for p in self._violacoes("")))

    def test_resposta_que_comeca_errada_e_termina_com_ponto_e_virgula(self):
        # Reproduz o defeito do modelo: terminava com ";." (ponto e virgula
        # seguido de ponto), criando uma sentenca fantasma depois do ';'.
        texto = BOOLA.rstrip(".") + ";."
        problemas = self._violacoes(texto)
        self.assertTrue(any("nao comeca com 'que'" in p for p in problemas))


if __name__ == "__main__":
    unittest.main()
