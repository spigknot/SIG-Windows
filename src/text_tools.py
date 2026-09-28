"""Ajuste automatico do texto da oitiva: uma linha unica e "; " padrao.

POR QUE ISTO EXISTE
-------------------
O prompt da oitiva manda o modelo responder com as sentencas separadas por
ponto e virgula. Medido no modelo real, ele quase sempre acerta a linha, mas
JA ACONTECEU (com outro prompt) de voltar uma quebra de linha depois de cada
`;` -- a oitiva chega na tela partida em varias linhas, e a quebra nao serve
para nada ali: o Termo de Declaracoes e um paragrafo corrido.

Instead of fighting the model in the prompt (que ja se provou fragil: no
qwen 7B qualquer palavra nova desloca o comportamento inteiro), o app corrige
o texto no lugar, sob demanda do usuario: um clique na varinha magica e o texto
inteiro fica em uma linha so, com exatamente um espaco depois de cada `;`.

O QUE O AJUSTE FAZ (e o que ele NAO faz)
---------------------------------------
FAZ:
  - remove toda quebra de linha (LF, CRLF ou CR), virando um espaco;
  - garante exatamente UM espaco depois de cada ponto e virgula;
  - garante UM espaco entre as sentencas e a palavra "que" seguinte;
  - nao mexe no conteudo: nenhuma palavra, valor ou nome e alterado.

NAO FAZ (deliberadamente):
  - nao cria nem remove ponto e virgula (a pontuacao e do modelo);
  - nao troca ";" por "." nem mexe na ultima sentenca;
  - nao reescreve, nao resume e nao inventa texto.

CONTRATO
--------
`ajustar_texto_oitiva(texto)` e uma funcao PURA: sem Tkinter, sem rede, sem
acesso a arquivo. A UI so a chama e troca o texto da caixa. Isso deixa o
comportamento testavel em `tests/test_text_tools.py` sem levantar janela.
"""
from __future__ import annotations

import re

# Quebras de linha: LF, CRLF e CR. O texto vindo do modelo ja passou por
# `extract_text_model_output().strip()`, mas texto colado pelo usuario ou
# recuperado de um arquivo tambem pode trazer \r.
_QUEBRA_DE_LINHA = re.compile(r"\r\n|\r|\n")

# Depois do ponto e virgula: quebra de linha, espacos e tabs sao todos
# "separador" e viram UM unico espaco. `\s` ja cobre \r, \n, tab e espaco.
_ESPACOS_APOS_PONTO_E_VIRGULA = re.compile(r";[ \t\r\n]*")

# Espaco antes do ponto e virgula e apenas cosmetico; NAO e exigido pelo
# contrato do Termo ("que conhece os envolvidos;"), entao nao e normalizado --
# mexer nisso mudaria o texto do documento sem necessidade.


def ajustar_texto_oitiva(texto: str) -> tuple[str, bool]:
    """Coloca a oitiva em uma linha unica com "; " padrao.

    Devolve ``(texto_ajustado, mudou)`` -- ``mudou`` False significa que o
    texto ja estava correto (nada foi reescrito, o app nao mexe no texto do
    usuario sem necessidade).
    """
    original = str(texto or "")
    if not original.strip():
        return "", False

    # 1. Toda quebra de linha vira um unico espaco. Isto e o que resolve o
    #    defeito relatado: "... informado;\nque estava no local..." vira
    #    "... informado; que estava no local...".
    ajustado = _QUEBRA_DE_LINHA.sub(" ", original)

    # 2. Depois de cada ponto e virgula, exatamente um espaco.
    ajustado = _ESPACOS_APOS_PONTO_E_VIRGULA.sub("; ", ajustado)

    # 3. As sentencas ficam separadas por UM espaco, sem espaco duplo antes do
    #    ponto e virgula (sobrevive a quebras com espacos ao redor).
    ajustado = re.sub(r" {2,}", " ", ajustado)

    # 4. Tira o espaco que sobraria na fronteira da quebra removida, sem criar
    #    espaco duplo com o passo 3.
    ajustado = ajustado.strip()

    return ajustado, ajustado != original
