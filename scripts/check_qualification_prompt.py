"""Vacina dos prompts editaveis: chama o modelo DE VERDADE e julga a resposta.

POR QUE ISTO EXISTE
-------------------
Os testes em `tests/` validam o CODIGO do app (o parser, a formatacao) com
respostas escritas a mao. Eles NAO pegam o defeito que ja aconteceu: o modelo
respondendo errado. O `parse_qualification_json` aceita CPF "345.123.456-78"
com pontos e devolve os pontos -- e isso esta CORRETO por contrato, porque o
parser nao deve mexer em numero. Quem falhou foi o MODELO. Nenhum teste de
codigo enxerga isso.

Por isso este script e uma "vacina": ele envia o prompt de sistema REAL
(`prompts/*.txt`, tal como esta no disco) para o modelo REAL e reprova se a
resposta violar qualquer regra que o prompt promete.

Nao faz parte do `pytest`: depende de rede e de GPU. Rodar aqui consome a
maquina, e um release nao pode quebrar porque o servidor estava offline.
Por isso ele e manual -- ver `docs/agents/README.md`.

USO
---
    python scripts/check_qualification_prompt.py
    python scripts/check_qualification_prompt.py --model "servidor (qwen2.5)" --runs 3
    python scripts/check_qualification_prompt.py --url http://servidor:8401/v1/chat/completions

Saida: `PASS` / `FAIL` por documento, e o detalhe de cada regra violada.
Exit code 0 = todos os documentos ok; 1 = alguma regra violada; 2 = erro de
ambiente (modelo/servidor fora do ar).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from assistant_prompts import (  # noqa: E402
    DEFAULT_QUALIFICATION_SYSTEM_PROMPT,
    qualification_user_prompt,
)
from http_clients import TextModelClient  # noqa: E402
from providers import read_text_models  # noqa: E402
from qualification import (  # noqa: E402
    LIVE_QUALIFICATION_FIELD_IDS,
    parse_qualification_json,
)

# Ordem e rotulos EXATAMENTE como o app monta `self.qualification_fields`
# (sig_app.py, sem methodo extra: o tuple e montado no __init__). Mantido
# aqui em vez de importado para o script rodar sem instanciar o Tkinter;
# `tests/test_check_qualification_prompt.py` falha se esta lista divergir
# do app -- e o mutation check garante que isso nao vira decoracao.
CAMPOS: tuple[tuple[str, str], ...] = (
    ("nome", "Nome Completo"),
    ("nascimento", "Data de Nascimento"),
    ("rg", "RG"),
    ("cpf", "CPF"),
    ("naturalidade", "Naturalidade"),
    ("sexo", "Sexo"),
    ("estado_civil", "Estado Civil"),
    ("profissao", "Profissão"),
    ("altura", "Altura"),
    ("pele", "Pele"),
    ("olhos", "Olhos"),
    ("cabelo", "Cabelo"),
    ("pai", "Pai"),
    ("mae", "Mãe"),
    ("instrucao", "Grau de Instrução"),
    ("endereco", "Endereço"),
    ("bairro", "Bairro"),
    ("cidade", "Cidade"),
    ("telefone", "Telefone"),
)
IDS = [field for field, _ in CAMPOS]

# O prompt promete capitalizar nomes, mas NAO as preposicoes que ligam o
# prenome ao sobrenome ("Alexandre De Camargo" e errado).
PREPOSICOES = r"\b(?:De|Do|Da|Dos|Das|E)\b"

# Grau de instrucao NAO e profissao. Sem esta lista avaccina nao pegaria
# o erro que o DeepSeek cometeu: "profissao": "Superior".
ESCOLAS = {
    "superior", "superior completo", "superior incompleto", "pos-graduacao",
    "ensino medio", "ensino medio completo", "medio", "medio completo",
    "ensino fundamental", "fundamental completo", "fundamental incompleto",
    "tecnico", "tecnico completo", "superior completo/tecnico",
}

# Documentos de teste fixos.
#
# BR3 e feito para exercitar as regras que JA FALHARAM em producao:
#   - CPF/RG COM PONTOS no texto (a regra manda apagar os pontos);
#   - sigla de logradouro "Av Dom Pedro II" (a regra manda escrever "Avenida");
#   - "Antonio" sem acento (a regra manda acentuar);
#   - "Carlos De Souza" com preposicao maiuscula (a regra manda minuiscula);
#   - "Grau instrucao: Superior" SEM linha de profissao (pega a copia de
#     escolaridade para o campo profissao).
#
# IMPORTANTE: este documento tem que trazer a SIGLA do logradouro. Um
# teste com "Rua das Palmeiras" ja escrito nao exercita a tabela de traducao
# -- e o mutation check pegou exatamente isso: com a tabela removida do
# prompt, a continuacao passando. Documento que nao exercita a regra e
# documento inutil.
BR3 = """Ficha de atendimento

MARCO ANTONIO DE SOUZA
Situação Criminal
Nada consta
Documentos de Identificação
RG: 22.333.444-5 / CPF: 123.456.789-09
Informações Pessoais
Sexo: Masculino
Naturalidade: ITAPEVA - SP
Idade: 05/03/1990 (36 anos)
Estado Civil: Solteiro
Grau instrução: Superior
Endereço
Av Dom Pedro II, 1500, apto 72, Jardim America, Itapeva, SP, CEP: 12345-678
Características Físicas
Altura: 1,75 m
Cor do cabelo: Castanhos
Cor dos olhos: Castanhos escuros
Cor da pele: Branca
Filiação
Carlos De Souza E Maria De Souza
Contato
Telefone: (11) 97777-6666
"""

DOCUMENTOS: dict[str, str] = {"br3": BR3}


def violacoes(campos: dict[str, str]) -> list[str]:
    """Cada regra que o prompt promete e a resposta do modelo VIOLOU.

    Devolve strings legiveis (uma por defeito). Vazio = resposta integra.
    Cobre formato E significado: o bug da "profissao" so aparece no bloco
    ESCOLAS, porque nao ha como um teste de formato pegar "Superior" como
    profissao -- e um valor bem formado, apenas errado.
    """
    problemas: list[str] = []

    # --- formato ---
    cpf = str(campos.get("cpf") or "").strip()
    if cpf and not re.fullmatch(r"\d{9}-\d{2}", cpf):
        problemas.append(f"cpf fora de 9 digitos + hifen: {cpf!r}")

    rg = str(campos.get("rg") or "").strip()
    if rg and "." in rg:
        problemas.append(f"rg com pontos: {rg!r}")

    endereco = str(campos.get("endereco") or "").strip()
    if endereco:
        # Sigla de logradouro no comeco (R, Av, Al, Rod, ...) em vez da
        # palavra por extenso que a regra 5 do prompt exige.
        if re.match(r"^(R|Av|Al|Rod|Estr|Trav|Vl)\.?\s", endereco, re.IGNORECASE):
            if not re.match(r"^(Rua|Avenida|Alameda|Rodovia|Estrada|Travessa|Vila)\s", endereco):
                problemas.append(f"logradouro nao expandido: {endereco!r}")
        if ", n\u00b0" not in endereco:
            problemas.append(f"endereco sem ', n\u00b0 N': {endereco!r}")
        if re.search(r"\bBairro\b", endereco, re.IGNORECASE):
            problemas.append(f"bairro dentro do endereco: {endereco!r}")

    cidade = str(campos.get("cidade") or "").strip()
    if cidade and not re.search(r"-\s*[A-Z]{2}$", cidade):
        problemas.append(f"cidade sem UF no fim: {cidade!r}")

    altura = str(campos.get("altura") or "").strip()
    if altura and not re.fullmatch(r"\d,\d{2}m", altura):
        problemas.append(f"altura fora de '1,88m': {altura!r}")

    est_civil = str(campos.get("estado_civil") or "").strip()
    if est_civil and re.search(r"[Aa]\)$", est_civil):
        problemas.append(f"estado civil com parentesco de genero: {est_civil!r}")

    for chave in ("nome", "pai", "mae", "endereco", "bairro", "cidade", "naturalidade"):
        valor = str(campos.get(chave) or "")
        achado = re.search(PREPOSICOES, valor)
        if achado:
            problemas.append(f"preposicao com maiuscula em {chave}: {valor!r} ({achado.group(0)})")

    # --- significado ---
    profissao = str(campos.get("profissao") or "").strip().casefold()
    instrucao = str(campos.get("instrucao") or "").strip().casefold()
    if profissao and profissao in ESCOLAS:
        problemas.append(f"profissao recebeu grau de instrucao: {campos.get('profissao')!r}")
    if profissao and instrucao and profissao == instrucao:
        problemas.append(f"profissao == instrucao: {profissao!r}")

    pai = str(campos.get("pai") or "").strip().casefold()
    mae = str(campos.get("mae") or "").strip().casefold()
    if pai and mae and (pai in mae or mae in pai):
        problemas.append(f"pai e mae com o mesmo nome: pai={pai!r} mae={mae!r}")

    return problemas


def main() -> int:
    ap = argparse.ArgumentParser(description="Vacina do prompt de qualificacao (chama o modelo real).")
    ap.add_argument("--model", default="servidor (qwen2.5)", help="Nome exato em 'read_text_models'.")
    ap.add_argument("--url", default=None, help="Sobrescreve a URL do modelo (ex.: :8401).")
    ap.add_argument("--runs", type=int, default=1, help="Vezes por documento (o modelo nao e deterministico).")
    ap.add_argument("--documentos", default="br3", help="IDs dos documentos a testar, separados por virgula.")
    args = ap.parse_args()

    try:
        modelo = dict(next(m for m in read_text_models() if m["name"] == args.model))
    except StopIteration:
        print(f"FAIL: ambiente: modelo {args.model!r} nao existe em read_text_models().")
        return 2
    if args.url:
        modelo["url"] = args.url
    modelo.setdefault("parameters", {})
    modelo["parameters"] = {**modelo["parameters"], "temperature": 0.0}

    client = TextModelClient(threading.Event())
    falhas_total = 0

    for nome in [d.strip() for d in args.documentos.split(",") if d.strip()]:
        texto = DOCUMENTOS.get(nome)
        if texto is None:
            print(f"FAIL: documento {nome!r} desconhecido (use: {', '.join(DOCUMENTOS)}).")
            return 2
        material = qualification_user_prompt(IDS, texto)
        for tentativa in range(1, args.runs + 1):
            rotulo = f"{nome}" if args.runs == 1 else f"{nome} #{tentativa}"
            try:
                bruto = client.post(modelo, DEFAULT_QUALIFICATION_SYSTEM_PROMPT, material)
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL: {rotulo}: o modelo nao respondeu ({type(exc).__name__}: {exc}).")
                print("      O prompt nao e a causa: o servidor esta fora do ar ou o modelo mudou.")
                return 2
            try:
                campos = parse_qualification_json(
                    bruto, list(LIVE_QUALIFICATION_FIELD_IDS), CAMPOS
                )
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL: {rotulo}: o modelo NAO devolveu JSON valido ({exc}).")
                print(f"      resposta crua: {bruto[:400]}")
                falhas_total += 1
                continue
            problemas = violacoes(campos)
            if problemas:
                falhas_total += 1
                print(f"FAIL: {rotulo}: {len(problemas)} regra(s) do prompt violada(s):")
                for p in problemas:
                    print(f"      - {p}")
            else:
                print(f"PASS: {rotulo} ({args.model}{' @ ' + args.url if args.url else ''})")

    print()
    if falhas_total:
        print(f"FAIL: {falhas_total} execucao(oes) com regra violada. O prompt precisa de ajuste.")
        return 1
    print(f"PASS: todos os documentos ok em {args.runs} execucao(oes) com {args.model}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
