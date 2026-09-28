"""Vacina do prompt da oitiva: chama o modelo DE VERDADE e julga a resposta.

POR QUE ISTO EXISTE
-------------------
Os testes em `tests/` validam o CODIGO do app (o parser, a formatacao) com
respostas escritas a mao. Eles NAO pegam o defeito que ja aconteceu: o MODELO
respondendo errado. O caso concreto: o prompt manda separar cada fato por
ponto e virgula e seguir na MESMA linha, o modelo passou a quebrar a linha
depois de cada `;` -- e nenhum teste de codigo enxerga isso, porque o app so
imprime o texto que o modelo devolveu.

Por isso este script e uma "vacina" (mesma familia de
`scripts/check_qualification_prompt.py`): ele envia o prompt de sistema REAL
(`prompts/oitiva_system.txt`, tal como esta no disco) e o prompt de usuario
REAL (`prompts/oitiva_user.txt` + material fixo) para o modelo REAL e reprova
se a resposta violar qualquer regra que o prompt promete.

Nao faz parte do `pytest`: depende de rede e de GPU, e um release nao pode
quebrar porque o servidor estava offline. Por isso ele e manual.

USO
---
    python scripts/check_oitiva_prompt.py
    python scripts/check_oitiva_prompt.py --model "servidor (qwen2.5)" --runs 3
    python scripts/check_oitiva_prompt.py --model IA-Proxy --proxy-model deepseek-flash --runs 3
    python scripts/check_oitiva_prompt.py --url http://servidor:8401/v1/chat/completions
    python scripts/check_oitiva_prompt.py --outdir "%LOCALAPPDATA%/Temp/oitiva"

Saida: `PASS` / `FAIL` por execucao, o detalhe de cada regra violada e o
caminho do texto cru salvo em disco (para inspecao manual). Exit code 0 =
todas as execucoes ok; 1 = alguma regra violada; 2 = erro de ambiente
(modelo/servidor fora do ar).
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from assistant_prompts import (  # noqa: E402
    statement_prompt,
    statement_user_prompt,
)
from http_clients import TextModelClient  # noqa: E402
from providers import read_text_models  # noqa: E402
from text_models import (  # noqa: E402
    assistant_request_model_label,
    selected_text_model_for,
)

# Material fixo do teste (o caso real que expos a quebra de linha: furto do
# martelete e do radinho na obra do JOÃO BATISTA, em Taguaí). O texto vai
# EXATAMENTE como chega no app: colado do BO com as quebras de linha originais
# do documento -- foi assim que a resposta quebrou em producao. Um material
# normalizado numa linha unica NAO exercita o defeito (o modelo devolveu tudo
# numa linha), e documento que nao exercita a regra e documento inutil.
MATERIAL = "\n".join(
    (
        "Comparece nesta Delegacia de Polícia a vítima JOÃO BATISTA declarando que é pedreiro e está realizando uma",
        "obra em uma residência no local dos fatos, neste município de Taguaí. Informa que a obra fica sem qualquer vigilância",
        "durante a noite, não permanecendo ninguém no local. Relata que, nesta madrugada, alguém entrou no local e furtou",
        "do interior da obra um martelete e um radinho pequeno de pilha, ambos de propriedade da vítima. Para entrar no local,",
        "o autor do furto pulou uma madeira colocada para fechar a obra, que divide a rua do interior do imóvel; a madeira tem",
        "mais de 2 metros de altura e possui cadeado. Informa que não precisou de arrombamento para a entrada e que, para",
        "entrar sem pular, seria necessário ter a chave do cadeado que abre as madeiras que cercam a frente da obra. Relata",
        "que ficaram marcas de pés/esfregões na madeira por onde o autor pulou. O martelete e o radinho estavam no interior",
        "do imóvel, na sala, cuja porta estava encostada. O imóvel está fechado com muros nas laterais e no fundo, e com",
        "referida madeira cercando a parte da frente. O valor estimado do martelete é de R$ 925,00 (novecentos e vinte e cinco",
        "reais) e o do radinho de pilha é de R$ 80,00 (oitenta reais). Informa que conseguiu imagens de câmeras de segurança",
        "que gravaram o ocorrido durante a madrugada; as câmeras são da residência da frente o imóvel. Nas imagens,",
        "aparece o autor pulando a madeira que cerca a frente do imóvel. Após analisar as imagens, o declarante informa que",
        "imagina que o autor seja DIEGO \"RETRANQUINHA\", a quem já conhece na cidade. Informa que ficou sabendo que",
        "DIEGO \"RETRANQUINHA\" está praticando vários furtos nos últimos dias em Taguaí.",
    )
)

# Frase de abertura FIXA que a regra 1 do prompt promete. O material e de um
# HOMEM ("a vítima JOÃO BATISTA ... é pedreiro"), entao exige-se a forma
# masculina, sem numero de telefone no meio. A versao anterior do prompt so
# falava em "intimada" na regra 2 e o modelo escrevia "intimada" para homem em
# 3/3 execucoes -- por isso a checagem e estrita de genero.
ABERTURA = re.compile(
    r"^que aceita ser intimado pelo telefone/whatsapp fornecido;", re.IGNORECASE
)

# Dados que a regra 4 do prompt manda reproduzir ("reproduza rigorosamente
# todos os dados informados" + "nao omita a conclusao"). Se o ajuste do
# prompt fizer o modelo RESUMIR, isto reprova na hora.
DADOS_OBRIGATORIOS: tuple[tuple[str, str], ...] = (
    ("martelete", "o objeto furtado principal"),
    ("R$ 925,00", "o valor do martelete"),
    ("radinho", "o segundo objeto furtado"),
    ("R$ 80,00", "o valor do radinho"),
    ("madeira", "o obstaculo pulado pelo autor"),
    ("cadeado", "o cadeado da madeira"),
    ("câmeras", "as imagens de câmeras de segurança"),
    ("DIEGO", "o nome do suspeito (em MAIUSCULAS)"),
    ("RETRANQUINHA", "a alcunha do suspeito"),
    ("Taguaí", "o municipio dos fatos"),
)

# Numeros por extenso sao aceitos ("dois metros"); a altura e fato relevante.
ALTURA = re.compile(r"\b(?:2|dois)\s+metros\b", re.IGNORECASE)

# Nomes proprios precisam estar em MAIUSCULAS (regra 2). Formas em caixa
# mista denunciam a violacao.
NOME_MINUSCULO = re.compile(r"\bDiego\b|\bJo[ãa]o\b|\bBatista\b")


def violacoes(texto: str) -> list[str]:
    """Cada regra que o prompt promete e a resposta do modelo VIOLOU.

    Devolve strings legiveis (uma por defeito). Vazio = resposta integra.
    """
    problemas: list[str] = []
    corpo = texto.strip()

    # --- regra NOVA (a que originou a vacina): texto em UMA unica linha ---
    quebras = re.findall(r"\r\n|\r|\n", corpo)
    if quebras:
        amostra = " | ".join(
            m.group(0).replace("\n", "\\n").replace("\r", "\\r")
            for m in re.finditer(r".{0,24}(?:\r\n|\r|\n).{0,24}", corpo)
        )
        problemas.append(
            f"quebra de linha no texto ({len(quebras)} ocorrencia(s)): {amostra}"
        )
    if re.search(r";[^\s]", corpo):
        problemas.append("ponto e virgula sem o espaco seguinte")
    if re.search(r";\s{2,}", corpo):
        problemas.append("mais de um espaco depois do ponto e virgula")

    # --- regra 1: frase inicial fixa, sem numero de telefone ---
    primeira = corpo.split(";", 1)[0] + (";" if ";" in corpo else "")
    if not ABERTURA.match(corpo):
        problemas.append(f"abertura fora da frase fixa: {primeira[:120]!r}")
    if re.search(r"\d", primeira):
        problemas.append(f"numero de telefone/digito na abertura: {primeira[:120]!r}")

    # --- regra 3: sentencas atomicas "que ...;" na MESMA linha ---
    partes = corpo.split(";")
    sentencas = [p.strip() for p in partes]
    if sentencas and sentencas[-1] == "":
        sentencas.pop()
    if not sentencas:
        problemas.append("resposta vazia")
        return problemas
    for indice, sentenca in enumerate(sentencas):
        if not sentenca:
            problemas.append(f"sentenca vazia na posicao {indice + 1}")
            continue
        if not re.match(r"que\b", sentenca, re.IGNORECASE):
            problemas.append(f"sentenca {indice + 1} nao comeca com 'que': {sentenca[:80]!r}")
        if indice < len(sentencas) - 1 and re.search(r"[.!?]\s", sentenca + " "):
            problemas.append(f"sentenca {indice + 1} termina antes do fim: {sentenca[-60:]!r}")
        if indice == len(sentencas) - 1 and not sentenca.endswith("."):
            problemas.append(f"ultima sentenca sem ponto final: {sentenca[-60:]!r}")

    # --- regra 2: voz formal do depoimento ---
    # A pessoa fala de si como "o declarante"/"a declarante" (vítima/parente)
    # ou "o depoente"/"a depoente" (testemunha isenta).
    if not re.search(r"\b(declarante|depoente)\b", corpo, re.IGNORECASE):
        problemas.append("sem referencia formal a si mesma ('declarante'/'depoente')")

    # --- regra 4: dados informados preservados ---
    for dado, motivo in DADOS_OBRIGATORIOS:
        if dado not in corpo:
            problemas.append(f"dado ausente: {dado!r} ({motivo})")
    if not ALTURA.search(corpo):
        problemas.append("dado ausente: altura da madeira ('2 metros')")

    # --- regra 2: nomes proprios em MAIUSCULAS ---
    achado = NOME_MINUSCULO.search(corpo)
    if achado:
        problemas.append(f"nome proprio fora de MAIUSCULAS: {achado.group(0)!r}")

    return problemas


def main() -> int:
    ap = argparse.ArgumentParser(description="Vacina do prompt da oitiva (chama o modelo real).")
    ap.add_argument("--model", default="servidor (qwen2.5)", help="Nome exato em 'read_text_models'.")
    ap.add_argument(
        "--proxy-model",
        default=None,
        help="Modelo encaminhado quando --model e IA-Proxy (ex.: deepseek-flash, grok-latest).",
    )
    ap.add_argument("--url", default=None, help="Sobrescreve a URL do modelo (ex.: :8401).")
    ap.add_argument("--runs", type=int, default=1, help="Vezes que a requisicao e repetida.")
    ap.add_argument("--outdir", default=None, help="Pasta para salvar a resposta crua de cada execucao.")
    args = ap.parse_args()

    # A config e montada pela MESMA funcao que o app usa na tarefa de oitiva
    # (inclui o caminho IA-Proxy -> deepseek-flash/grok-latest), para a
    # requisicao do teste ser identica a requisicao real.
    nomes = {model["name"] for model in read_text_models()}
    if args.model not in nomes:
        print(f"FAIL: ambiente: modelo {args.model!r} nao existe em read_text_models().")
        return 2
    settings = {"statement_model": args.model}
    if args.proxy_model:
        settings["statement_proxy_model"] = args.proxy_model
        settings["ia_proxy_model"] = args.proxy_model
    modelo = dict(selected_text_model_for(settings, "statement"))
    if args.url:
        modelo["url"] = args.url
    modelo.setdefault("parameters", {})
    modelo["parameters"] = {**modelo["parameters"], "temperature": 0.0}

    outdir = Path(args.outdir) if args.outdir else Path(tempfile.mkdtemp(prefix="oitiva_check_"))
    outdir.mkdir(parents=True, exist_ok=True)

    client = TextModelClient(threading.Event())
    falhas_total = 0
    origem = assistant_request_model_label(modelo) + (
        f" @ {args.url}" if args.url else f" @ {modelo['url']}"
    )

    for tentativa in range(1, args.runs + 1):
        rotulo = f"execucao {tentativa}/{args.runs}"
        try:
            bruto = client.post(
                modelo,
                statement_prompt(None),
                statement_user_prompt(None, MATERIAL),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: {rotulo}: o modelo nao respondeu ({type(exc).__name__}: {exc}).")
            print("      O prompt nao e a causa: o servidor esta fora do ar ou o modelo mudou.")
            return 2
        arquivo = outdir / f"oitiva_{tentativa:02d}.txt"
        arquivo.write_text(bruto, encoding="utf-8")
        problemas = violacoes(bruto)
        linhas = len(re.findall(r"\r\n|\r|\n", bruto.strip()))
        print(
            f"{'FAIL' if problemas else 'PASS'}: {rotulo} "
            f"({len(bruto)} chars, {linhas} quebra(s) de linha, {bruto.count(';')} sentenca(s)) "
            f"-> {arquivo}"
        )
        if problemas:
            falhas_total += 1
            print(f"      {len(problemas)} regra(s) do prompt violada(s):")
            for p in problemas:
                print(f"      - {p}")

    print()
    if falhas_total:
        print(f"FAIL: {falhas_total} execucao(oes) com regra violada. O prompt precisa de ajuste.")
        return 1
    print(f"PASS: todas as {args.runs} execucao(oes) ok com {origem}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
