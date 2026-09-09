"""Contrato da modularizacao (vacina permanente contra regressao estrutural).

Estes testes existem para impedir que a refatoracao se degrade com o tempo:

1. Re-export = mesmo objeto. Todo nome reexportado por sig_app tem de ser o
   MESMO objeto do modulo de origem (evita duas implementacoes paralelas).
2. Sem duplicata. sig_app nao pode voltar a definir, no topo, um nome que ja
   foi extraido para outro modulo.
3. Camadas. Modulos de dominio nao importam Tkinter nem sig_app (mantem a
   separacao UI / regra de negocio / rede / persistencia).
4. Docstring de responsabilidade em todo modulo extraido (navegacao por IA).
5. Settings: normalize_settings nao perde nem altera chave de DEFAULT_SETTINGS.
"""
import ast
import importlib
import os
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src"
sys.path.insert(0, str(SRC))

import sig_app  # noqa: E402

# Blocos de re-export gerados pela refatoracao: from <modulo> import (  # noqa: F401
_RE_BLOCO = re.compile(
    r"^from\s+(?P<modulo>[A-Za-z_][\w]*)\s+import\s+\(\s+#\s*noqa:\s*F401\s*$",
    re.MULTILINE,
)

# Modulos de dominio que NAO podem conhecer Tkinter nem o monolito de UI.
MODULOS_SEM_UI = [
    "app_env",
    "domain_models",
    "providers",
    "settings_store",
    "transcription_parsing",
    "text_models",
    "http_clients",
    "stt_clients",
    "log_formatting",
    "reporting",
    "qualification",
    "name_database",
    "imei_lookup",
    "documents",
    "media_files",
    "audio_io",
]

FONTE_SIG_APP = (SRC / "sig_app.py").read_text(encoding="utf-8")


def blocos_reexportados():
    """[(modulo, [nomes...]), ...] lidos do proprio sig_app.py."""
    blocos = []
    for m in _RE_BLOCO.finditer(FONTE_SIG_APP):
        modulo = m.group("modulo")
        resto = FONTE_SIG_APP[m.end():]
        corpo = resto.split(")", 1)[0]
        nomes = [
            linha.strip().rstrip(",")
            for linha in corpo.splitlines()
            if linha.strip() and not linha.strip().startswith("#")
        ]
        blocos.append((modulo, nomes))
    return blocos


class ReexportContractTest(unittest.TestCase):
    def test_existem_blocos_de_reexport(self):
        blocos = blocos_reexportados()
        self.assertGreaterEqual(len(blocos), 15, "esperava os blocos de re-export da refatoracao")

    def test_reexport_e_o_mesmo_objeto_do_modulo_de_origem(self):
        divergentes = []
        for modulo, nomes in blocos_reexportados():
            origem = importlib.import_module(modulo)
            for nome in nomes:
                if getattr(sig_app, nome, None) is not getattr(origem, nome, None):
                    divergentes.append(f"{modulo}.{nome}")
        self.assertEqual([], divergentes, "sig_app tem copia divergente destes nomes")

    def test_sig_app_nao_redefine_nomes_extraidos(self):
        definidos = set()
        for no in ast.parse(FONTE_SIG_APP).body:
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definidos.add(no.name)
            elif isinstance(no, ast.Assign):
                for alvo in no.targets:
                    if isinstance(alvo, ast.Name):
                        definidos.add(alvo.id)
        extraidos = {nome for _, nomes in blocos_reexportados() for nome in nomes}
        self.assertEqual(set(), definidos & extraidos, "implementacao duplicada em sig_app.py")


class CamadasTest(unittest.TestCase):
    def test_modulos_de_dominio_nao_importam_tkinter_nem_sig_app(self):
        problemas = []
        for modulo in MODULOS_SEM_UI:
            arvore = ast.parse((SRC / f"{modulo}.py").read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    for al in no.names:
                        if al.name.split(".")[0] in {"tkinter", "sig_app"}:
                            problemas.append(f"{modulo}: import {al.name}")
                elif isinstance(no, ast.ImportFrom):
                    raiz = (no.module or "").split(".")[0]
                    if raiz in {"tkinter", "sig_app"}:
                        problemas.append(f"{modulo}: from {no.module} import ...")
        self.assertEqual([], problemas, "camada de dominio nao pode depender da UI")

    def test_modulos_extraidos_declaram_responsabilidade(self):
        sem_docstring = []
        for modulo in MODULOS_SEM_UI + ["ui_widgets", "ffmpeg_tools_panel"]:
            arvore = ast.parse((SRC / f"{modulo}.py").read_text(encoding="utf-8"))
            if not ast.get_docstring(arvore):
                sem_docstring.append(modulo)
        self.assertEqual([], sem_docstring, "todo modulo extraido precisa de docstring de responsabilidade")


class SettingsRoundTripTest(unittest.TestCase):
    def test_normalize_settings_preserva_default_settings(self):
        padrao = dict(sig_app.DEFAULT_SETTINGS)
        normalizado = sig_app.normalize_settings(dict(padrao))
        faltando = sorted(k for k in padrao if k not in normalizado)
        self.assertEqual([], faltando, "normalize_settings perdeu chaves de DEFAULT_SETTINGS")
        alterados = {k: (padrao[k], normalizado[k]) for k in padrao if padrao[k] != normalizado[k]}
        self.assertEqual({}, alterados, "normalize_settings alterou defaults (round-trip instavel)")


if __name__ == "__main__":
    unittest.main()
