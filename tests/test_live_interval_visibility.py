"""Controles exclusivos do servidor STT LOCAL na tela de Ocorrência (vacina).

Pedido do usuário (11/09):

1. os botões de diminuir/aumentar do "t =" — que é TEMPO (o intervalo em
   segundos entre as fatias REST da transcrição ao vivo), não temperatura — só
   aparecem quando o modelo de transcrição selecionado é o SERVIDOR LOCAL
   (Granite NAR);
2. com o Granite NAR, o resto da linha (Timestamps, Diarização, os dois "?",
   Idioma e Keywords) some junto: a linha fica só com o intervalo, e o que
   sobra fica encostado à esquerda;
3. os controles dos MICROFONES nunca se movem.

Este arquivo trava:

- a REGRA (`is_local_granite_transcription_server`), varrendo o catálogo real
  de servidores — provedor novo entra no teste sozinho;
- o COMPORTAMENTO de `_refresh_live_local_server_controls`, chamado com widgets
  falsos que registram `pack`/`pack_forget` (sem Tk, sem janela) — é o que
  prova que o grupo aparece/some por modelo e que o "Timestamps" volta ANTES do
  bloco de idioma/keywords (o `before=` só pode apontar para um irmão
  empacotado: apontar para um oculto levanta TclError, e é por isso que o
  container da linha existe);
- a ESTRUTURA que faz a omissão funcionar de uma vez: os três widgets do grupo
  nascem dentro de `live_interval_controls`, e intervalo/timestamps/keywords
  vivem no mesmo container (`live_line_controls`), cujos microfones ficam
  FORA, depois do `live_top_spacer`.

O teste de PIXEL (nada se move fora da linha de controles) vive no
`scripts/ui_smoke.py`, que precisa da janela mapeada.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from providers import (  # noqa: E402
    ALIBABA_API_NAME,
    ASSEMBLYAI_API_NAME,
    DEEPGRAM_API_NAME,
    ELEVENLABS_API_NAME,
    GROK_API_NAME,
    LOCAL_GRANITE_SERVER_NAME,
    LOCAL_GRANITE_STT_MODEL,
    META_MUSE_API_NAME,
    is_local_granite_transcription_server,
    read_transcription_servers,
)
from sig_app import DEFAULT_SETTINGS, SigApp  # noqa: E402

FONTE_SIG_APP = (RAIZ / "src" / "sig_app.py").read_text(encoding="utf-8")
ARVORE_SIG_APP = ast.parse(FONTE_SIG_APP)

SERVIDORES_DE_API = (
    GROK_API_NAME,
    DEEPGRAM_API_NAME,
    ASSEMBLYAI_API_NAME,
    ELEVENLABS_API_NAME,
    META_MUSE_API_NAME,
    ALIBABA_API_NAME,
)

WIDGETS_DO_GRUPO = ("live_interval_minus", "live_interval_entry", "live_interval_plus")
MEMBROS_DO_CONTAINER = ("live_interval_controls", "live_timestamps_check", "live_grok_controls")
COLUNAS_DE_MICROFONE = ("live_normal_mic_column", "live_pause_column", "live_mic_column")


def _funcao(nome: str) -> ast.FunctionDef:
    for node in ast.walk(ARVORE_SIG_APP):
        if isinstance(node, ast.FunctionDef) and node.name == nome:
            return node
    raise AssertionError(f"funcao {nome} nao encontrada em sig_app.py")


def _masters_do_build_ui() -> dict[str, str]:
    """Mapa atributo -> master com que o widget foi criado dentro de _build_ui."""
    masters: dict[str, str] = {}
    for node in ast.walk(_funcao("_build_ui")):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        alvo = node.targets[0]
        if not (
            isinstance(alvo, ast.Attribute)
            and isinstance(alvo.value, ast.Name)
            and alvo.value.id == "self"
        ):
            continue
        valor = node.value
        fabrica = getattr(valor, "func", None)
        if not isinstance(valor, ast.Call) or not isinstance(fabrica, ast.Attribute):
            continue
        if fabrica.attr not in {"Frame", "Button", "Checkbutton", "Combobox", "Label", "Menubutton", "Canvas"}:
            continue
        masters[alvo.attr] = ast.unparse(valor.args[0]) if valor.args else "<sem master>"
    return masters


class _WidgetFalso:
    """Widget de mentira: registra pack/pack_forget e finge estar gerenciado."""

    def __init__(self, gerenciado: bool = True):
        self.gerenciado = "pack" if gerenciado else ""
        self.chamadas: list[tuple[str, dict]] = []

    def pack(self, **kwargs):
        self.chamadas.append(("pack", kwargs))
        self.gerenciado = "pack"

    def pack_forget(self):
        self.chamadas.append(("pack_forget", {}))
        self.gerenciado = ""

    def winfo_manager(self):
        return self.gerenciado

    def nomes(self) -> list[str]:
        return [nome for nome, _kwargs in self.chamadas]


class _VarFalsa:
    def __init__(self, valor: bool = True):
        self.valor = valor

    def set(self, valor):
        self.valor = valor

    def get(self):
        return self.valor


class _AppFalsa:
    """Objeto mínimo para chamar o refresh sem construir a interface."""

    def __init__(self, servidor: str, grok_visivel: bool = True):
        self.settings = {"transcription_server": servidor}
        self.live_interval_controls = _WidgetFalso(gerenciado=False)
        self.live_timestamps_check = _WidgetFalso(gerenciado=not grok_visivel)
        self.live_timestamps_var = _VarFalsa(True)
        self.live_grok_controls = _WidgetFalso(gerenciado=grok_visivel)

    def aplicar(self):
        SigApp._refresh_live_local_server_controls(self)
        return self


class RegraDoServidorLocalTest(unittest.TestCase):
    """Quem possui os controles exclusivos (intervalo e Timestamps)."""

    def test_servidor_local_e_reconhecido_pelo_nome_e_pelo_modelo(self):
        self.assertTrue(is_local_granite_transcription_server(LOCAL_GRANITE_SERVER_NAME))
        self.assertTrue(is_local_granite_transcription_server(LOCAL_GRANITE_STT_MODEL))
        self.assertTrue(is_local_granite_transcription_server(f"  {LOCAL_GRANITE_SERVER_NAME}  "))

    def test_provedores_de_api_nao_tem_os_controles(self):
        for nome in SERVIDORES_DE_API:
            with self.subTest(servidor=nome):
                self.assertFalse(is_local_granite_transcription_server(nome))

    def test_todos_os_servidores_de_api_do_catalogo_ficam_sem_os_controles(self):
        """A varredura vem do PRÓPRIO catálogo: provedor novo não escapa."""
        for servidor in read_transcription_servers():
            nome = servidor["name"]
            if nome == LOCAL_GRANITE_SERVER_NAME:
                self.assertTrue(is_local_granite_transcription_server(nome))
                continue
            with self.subTest(servidor=nome):
                self.assertFalse(is_local_granite_transcription_server(nome))

    def test_entradas_vazias_ou_desconhecidas_nao_habilitam_os_controles(self):
        for valor in ("", "   ", None, "servidor-remoto", "servidor local", "granite"):
            with self.subTest(valor=valor):
                self.assertFalse(is_local_granite_transcription_server(valor))

    def test_o_padrao_das_configuracoes_e_o_servidor_local(self):
        self.assertEqual(DEFAULT_SETTINGS["transcription_server"], LOCAL_GRANITE_SERVER_NAME)
        self.assertTrue(
            is_local_granite_transcription_server(DEFAULT_SETTINGS["transcription_server"])
        )


class ComportamentoDoRefreshTest(unittest.TestCase):
    """O que o refresh faz com o grupo do intervalo e com o Timestamps."""

    def test_servidor_local_mostra_o_intervalo(self):
        app = _AppFalsa(LOCAL_GRANITE_SERVER_NAME).aplicar()
        self.assertEqual(["pack"], app.live_interval_controls.nomes())
        self.assertEqual("pack", app.live_interval_controls.gerenciado)

    def test_servidor_local_esconde_o_timestamps_e_desliga_o_checkbox(self):
        app = _AppFalsa(LOCAL_GRANITE_SERVER_NAME).aplicar()
        self.assertEqual(["pack_forget"], app.live_timestamps_check.nomes())
        self.assertEqual("", app.live_timestamps_check.gerenciado)
        self.assertFalse(app.live_timestamps_var.get())

    def test_provedores_de_api_escondem_o_intervalo(self):
        for nome in SERVIDORES_DE_API:
            with self.subTest(servidor=nome):
                app = _AppFalsa(nome).aplicar()
                self.assertEqual(["pack_forget"], app.live_interval_controls.nomes())
                self.assertEqual("", app.live_interval_controls.gerenciado)

    def test_provedores_de_api_mostram_o_timestamps(self):
        for nome in SERVIDORES_DE_API:
            with self.subTest(servidor=nome):
                app = _AppFalsa(nome).aplicar()
                self.assertEqual(["pack"], app.live_timestamps_check.nomes())
                self.assertEqual("pack", app.live_timestamps_check.gerenciado)

    def test_o_timestamps_volta_antes_do_bloco_de_idioma_e_keywords(self):
        """Sem o `before`, o pack acrescenta no fim e a ordem da linha inverte."""
        app = _AppFalsa(GROK_API_NAME).aplicar()
        _nome, kwargs = app.live_timestamps_check.chamadas[0]
        self.assertIs(kwargs.get("before"), app.live_grok_controls)
        self.assertEqual(kwargs.get("side"), "left")

    def test_o_timestamps_volta_sem_before_quando_o_bloco_de_api_esta_oculto(self):
        """`before` apontando para irmão NÃO empacotado levanta TclError."""
        app = _AppFalsa(GROK_API_NAME, grok_visivel=False).aplicar()
        _nome, kwargs = app.live_timestamps_check.chamadas[0]
        self.assertNotIn("before", kwargs)

    def test_alternar_local_e_api_deixa_o_estado_consistente(self):
        app = _AppFalsa(LOCAL_GRANITE_SERVER_NAME, grok_visivel=False).aplicar()
        app.live_timestamps_var.set(True)
        app.settings["transcription_server"] = DEEPGRAM_API_NAME
        app.live_grok_controls.gerenciado = "pack"  # o bloco de API volta antes
        app.aplicar()
        self.assertEqual("", app.live_interval_controls.gerenciado)
        self.assertEqual("pack", app.live_timestamps_check.gerenciado)
        _nome, kwargs = app.live_timestamps_check.chamadas[-1]
        self.assertIs(kwargs.get("before"), app.live_grok_controls)

    def test_o_refresh_dos_controles_reaplica_a_visibilidade(self):
        """Toda recarga de settings (abrir, salvar, iniciar) passa por aqui."""
        chamadas = [
            ast.unparse(node)
            for node in ast.walk(_funcao("_refresh_live_grok_controls"))
            if isinstance(node, ast.Call)
        ]
        self.assertIn("self._refresh_live_local_server_controls()", chamadas)


class EstruturaDaTelaTest(unittest.TestCase):
    """A linha é um container só: omitir um membro reflui o que sobra."""

    def setUp(self):
        self.masters = _masters_do_build_ui()

    def test_o_grupo_inteiro_nasce_no_frame_proprio(self):
        for nome in WIDGETS_DO_GRUPO:
            with self.subTest(widget=nome):
                self.assertIn(nome, self.masters, f"{nome} nao foi criado em _build_ui")
                self.assertEqual(self.masters[nome], "self.live_interval_controls")

    def test_o_container_da_linha_fica_na_linha_de_controles(self):
        self.assertEqual(self.masters.get("live_line_controls"), "live_top")

    def test_os_membros_da_linha_estao_no_container(self):
        for nome in MEMBROS_DO_CONTAINER:
            with self.subTest(widget=nome):
                self.assertEqual(self.masters.get(nome), "self.live_line_controls")

    def test_os_controles_dos_microfones_ficam_fora_do_container(self):
        for nome in (*COLUNAS_DE_MICROFONE, "live_top_spacer"):
            with self.subTest(widget=nome):
                self.assertEqual(self.masters.get(nome), "live_top")

    def test_a_visibilidade_usa_a_regra_compartilhada_do_servidor_local(self):
        fonte = ast.get_source_segment(
            FONTE_SIG_APP, _funcao("_refresh_live_local_server_controls")
        )
        self.assertIsNotNone(fonte)
        self.assertIn("is_local_granite_transcription_server", fonte)
        # Nada de lista de nomes/strings soltas decidindo a visibilidade.
        self.assertNotIn('== "servidor"', fonte)
        self.assertIn("live_timestamps_check.pack_forget()", fonte)

    def test_o_intervalo_continua_com_a_lista_de_tempos(self):
        """O grupo é de TEMPO: os valores seguem vindo de LIVE_INTERVAL_VALUES_MS."""
        fonte = ast.get_source_segment(FONTE_SIG_APP, _funcao("_build_ui"))
        self.assertIn("LIVE_INTERVAL_VALUES_MS", fonte)
        self.assertIn("_change_live_interval", fonte)


if __name__ == "__main__":
    unittest.main()
