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
6. Imports: nenhum modulo de src/ usa nome global sem importar/definir (evita
   NameError tardio, como o ctypes que faltou em documents.py); nenhum
   `from <modulo do projeto> import <nome>` aponta para nome inexistente;
   nenhum `<modulo>.<attr>` aponta para atributo inexistente; nenhuma funcao
   aninhada e acessada como atributo (`self.helper()`).
"""
import ast
import builtins
import importlib
import os
import re
import symtable
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


# Nomes que existem em tempo de execucao mas nao aparecem como definidos na
# tabela de simbolos do modulo.
_DUNDERS_DE_RUNTIME = frozenset(
    {
        "__file__",
        "__name__",
        "__doc__",
        "__package__",
        "__loader__",
        "__spec__",
        "__builtins__",
    }
)


def nomes_globais_nao_definidos(caminho):
    """Nomes usados como globais que o modulo nao importa nem define.

    Um `import` deixado para tras na extracao de um modulo so quebra em
    runtime, com NameError, no caminho que usa o nome (foi assim que ctypes
    faltou em documents.py e derrubou a copia formatada da ocorrencia). A
    leitura aqui e estatica, via symtable: enxerga o modulo inteiro sem
    executa-lo.
    """
    tabela = symtable.symtable(caminho.read_text(encoding="utf-8"), str(caminho), "exec")
    definidos = set()
    usados = set()

    def visitar(escopo):
        escopo_de_modulo = escopo.get_type() == "module"
        for simbolo in escopo.get_symbols():
            nome = simbolo.get_name()
            if not escopo_de_modulo and not simbolo.is_global():
                continue
            define_no_escopo = (
                simbolo.is_assigned()
                or simbolo.is_imported()
                or simbolo.is_namespace()
                or simbolo.is_parameter()
            )
            if define_no_escopo:
                definidos.add(nome)
            elif simbolo.is_referenced():
                usados.add(nome)
        for filho in escopo.get_children():
            visitar(filho)

    visitar(tabela)
    conhecidos = definidos | set(dir(builtins)) | _DUNDERS_DE_RUNTIME
    return sorted(usados - conhecidos)


# Codigo real do produto varrido pelas checagens estruturais abaixo.
PASTAS_VARRIDAS = ("src", "scripts")


def _alvos(alvo, destino):
    if isinstance(alvo, ast.Name):
        destino.add(alvo.id)
    elif isinstance(alvo, (ast.Tuple, ast.List)):
        for elemento in alvo.elts:
            _alvos(elemento, destino)
    elif isinstance(alvo, ast.Starred):
        _alvos(alvo.value, destino)


def nomes_de_topo(caminho):
    """Todo nome alcancavel como `modulo.nome` (inclui membros de classe)."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nomes.add(no.name)
        elif isinstance(no, ast.Import):
            for al in no.names:
                nomes.add(al.asname or al.name.split(".")[0])
        elif isinstance(no, ast.ImportFrom):
            for al in no.names:
                if al.name != "*":
                    nomes.add(al.asname or al.name)
        elif isinstance(no, ast.Assign):
            for t in no.targets:
                _alvos(t, nomes)
        elif isinstance(no, (ast.AnnAssign, ast.AugAssign)):
            _alvos(no.target, nomes)
        elif isinstance(no, (ast.For, ast.AsyncFor)):
            _alvos(no.target, nomes)
        elif isinstance(no, (ast.With, ast.AsyncWith)):
            for item in no.items:
                if item.optional_vars is not None:
                    _alvos(item.optional_vars, nomes)
        elif isinstance(no, ast.ExceptHandler) and no.name:
            nomes.add(no.name)
    return nomes


def modulos_do_projeto():
    """nome do modulo -> caminho, para os .py de PASTAS_VARRIDAS."""
    mapa = {}
    for pasta in PASTAS_VARRIDAS:
        for caminho in sorted((RAIZ / pasta).glob("*.py")):
            mapa[caminho.stem] = caminho
    return mapa


def import_nome_inexistente(caminho, modulos):
    """`from <modulo do projeto> import <nome>` que nao existe no modulo."""
    problemas = []
    for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
        if not isinstance(no, ast.ImportFrom) or no.level:
            continue
        raiz = (no.module or "").split(".")[0]
        if raiz not in modulos:
            continue
        definidos = nomes_de_topo(modulos[raiz])
        for al in no.names:
            if al.name != "*" and al.name not in definidos:
                problemas.append(f"{caminho.name}:{no.lineno} from {no.module} import {al.name}")
    return problemas


def atributo_inexistente(caminho, modulos):
    """`<modulo importado>.<attr>` que o modulo nao expoe."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    aliases = {}
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for al in no.names:
                raiz = al.name.split(".")[0]
                if raiz in modulos:
                    aliases[al.asname or raiz] = raiz
    problemas = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Attribute) or no.attr.startswith("__"):
            continue
        if not isinstance(no.value, ast.Name):
            continue
        modulo = aliases.get(no.value.id)
        if modulo and no.attr not in nomes_de_topo(modulos[modulo]):
            problemas.append(f"{caminho.name}:{no.lineno} {no.value.id}.{no.attr}")
    return problemas


def funcao_aninhada_como_metodo(caminho):
    """Funcao aninhada acessada como atributo de outro objeto.

    `self.helper()` nao acha um `def helper()` do escopo pai: o nome e um local
    (closure), nunca um atributo da instancia -> AttributeError em runtime.
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    problemas = []
    for funcao in ast.walk(arvore):
        if not isinstance(funcao, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        locais = {
            no.name
            for no in ast.walk(funcao)
            if no is not funcao and isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for classe in ast.walk(funcao):
            if isinstance(classe, ast.ClassDef):
                for item in classe.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        locais.discard(item.name)
        classes_locais = {no.name for no in ast.walk(funcao) if isinstance(no, ast.ClassDef)}
        if not locais:
            continue
        for no in ast.walk(funcao):
            if not isinstance(no, ast.Attribute) or no.attr not in locais:
                continue
            if isinstance(no.value, ast.Name) and no.value.id in classes_locais:
                continue
            problemas.append(
                f"{caminho.name}:{no.lineno} {ast.unparse(no.value)}.{no.attr}"
                f" (local de {funcao.name})"
            )
    return problemas


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


class ImportsDeModuloTest(unittest.TestCase):
    """Vacina: nome global usado sem o import correspondente no modulo.

    Bug vivido: ao extrair `documents.py` do monolito, o `import ctypes` do
    topo de sig_app.py nao veio junto; o botao "Copiar" da aba Ocorrencia
    falhava com `name 'ctypes' is not defined`, visivel so em runtime.
    """

    def test_todo_nome_global_usado_esta_definido_no_modulo(self):
        problemas = [
            f"{caminho.name}: {nome}"
            for caminho in sorted(SRC.glob("*.py"))
            for nome in nomes_globais_nao_definidos(caminho)
        ]
        self.assertEqual(
            [],
            problemas,
            "estes modulos usam nome que nao importam nem definem "
            "(NameError em runtime): traga o import do topo do sig_app.py",
        )

    def test_from_modulo_local_importa_nome_existente(self):
        modulos = modulos_do_projeto()
        problemas = [
            problema
            for pasta in PASTAS_VARRIDAS
            for caminho in sorted((RAIZ / pasta).glob("*.py"))
            for problema in import_nome_inexistente(caminho, modulos)
        ]
        self.assertEqual([], problemas, "import de nome que o modulo nao define (ImportError em runtime)")

    def test_atributo_de_modulo_importado_existe(self):
        # Ex.: `documents.set_windows_document_clipboard` apos renomear a
        # funcao no modulo (o import sobrevive, o uso quebra no runtime).
        modulos = modulos_do_projeto()
        problemas = [
            problema
            for pasta in PASTAS_VARRIDAS
            for caminho in sorted((RAIZ / pasta).glob("*.py"))
            for problema in atributo_inexistente(caminho, modulos)
        ]
        self.assertEqual([], problemas, "atributo inexistente no modulo importado")

    def test_funcao_aninhada_nao_e_chamada_como_metodo(self):
        # Bug vivido no Scribe (ElevenLabs): `self._finish_elevenlabs_session()`
        # para uma funcao aninhada da mesma funcao -> AttributeError e o texto
        # final da transcricao ao vivo era perdido no fechamento intencional.
        problemas = [
            problema
            for pasta in PASTAS_VARRIDAS
            for caminho in sorted((RAIZ / pasta).glob("*.py"))
            for problema in funcao_aninhada_como_metodo(caminho)
        ]
        self.assertEqual([], problemas, "funcao aninhada acessada como atributo (nao existe na instancia)")


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
