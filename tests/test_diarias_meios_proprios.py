"""Declaração de meios próprios: datas por extenso, modelo embutido e botão verde.

O modelo `modelos/modelo_meios_proprios.docx` é o arquivo da Desktop convertido
para DOCX e incorporado ao app (a pasta `modelos/` é entregue ao lado do
executável). As chaves do modelo usam o formato de três chaves:

    {{{mes_e_ano}}}      -> "dezembro/2026"        (mês/ano da ida do talão)
    {{{data_ida}}}       -> "31 de dezembro de 2026" (ida do talão)
    {{{data_protocolo}}} -> "31 de dezembro de 2026" (data do protocolo)
"""
from __future__ import annotations

import html
import sys
import tempfile
import tkinter as tk
import unittest
import zipfile
from pathlib import Path
from tkinter import ttk
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import documents  # noqa: E402
import sig_app  # noqa: E402
from documents import (  # noqa: E402
    MEIOS_PROPRIOS_TEMPLATE_NAME,
    generate_declaracao_meios_proprios,
    next_available_diarias_declaracao_path,
    prepare_declaracao_meios_proprios,
)
from sig_app import SigApp  # noqa: E402


def _texto_do_docx(path: Path) -> str:
    """Texto puro do documento (junta as runs do Word e desescapa entidades)."""
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return html.unescape("".join(m.group(2) for m in documents.WORD_TEXT_RE.finditer(xml)))


class PrepareDeclaracaoMeiosPropriosTest(unittest.TestCase):
    def test_mes_ano_e_datas_por_extenso(self):
        self.assertEqual(
            {
                "mes_e_ano": "dezembro/2026",
                "data_ida": "31 de dezembro de 2026",
                "data_protocolo": "31 de dezembro de 2026",
            },
            prepare_declaracao_meios_proprios(
                data_ida="31/12/2026", data_protocolo="31/12/2026"
            ),
        )

    def test_dia_sem_zero_a_esquerda_e_meses_diferentes(self):
        replacements = prepare_declaracao_meios_proprios(
            data_ida="01/03/2027", data_protocolo="05/01/2027"
        )
        self.assertEqual("março/2027", replacements["mes_e_ano"])
        self.assertEqual("1 de março de 2027", replacements["data_ida"])
        self.assertEqual("5 de janeiro de 2027", replacements["data_protocolo"])

    def test_data_de_ida_invalida_reprova_apontando_o_talao(self):
        with self.assertRaisesRegex(ValueError, "Confira a data de ida do talão."):
            prepare_declaracao_meios_proprios(data_ida="", data_protocolo="31/12/2026")

    def test_data_do_protocolo_invalida_reprova_apontando_o_protocolo(self):
        with self.assertRaisesRegex(ValueError, "Confira a data do protocolo."):
            prepare_declaracao_meios_proprios(
                data_ida="31/12/2026", data_protocolo="31-12-2026"
            )


class ModeloMeiosPropriosTest(unittest.TestCase):
    def test_modelo_incorporado_tem_exatamente_as_tres_chaves(self):
        template = ROOT / "modelos" / MEIOS_PROPRIOS_TEMPLATE_NAME
        self.assertTrue(template.is_file(), "o modelo precisa estar em modelos/")
        texto = _texto_do_docx(template)
        chaves = sorted(
            {tripla or dupla for tripla, dupla in documents.WORD_MARKER_RE.findall(texto)}
        )
        self.assertEqual(["data_ida", "data_protocolo", "mes_e_ano"], chaves)

    def test_gera_docx_real_sem_sobrar_marcador(self):
        replacements = prepare_declaracao_meios_proprios(
            data_ida="31/12/2026", data_protocolo="31/12/2026"
        )
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "declaracao_meios_proprios.docx"
            changes = generate_declaracao_meios_proprios(destination, replacements)
            self.assertEqual(3, changes)
            self.assertIsNone(zipfile.ZipFile(destination).testzip())
            texto = _texto_do_docx(destination)
            self.assertNotIn("{{", texto)
            self.assertIn("referente dezembro/2026", texto)
            self.assertIn("no dia 31 de dezembro de 2026", texto)
            self.assertIn("Taguaí, 31 de dezembro de 2026", texto)

    def test_modelo_ausente_aponta_a_atualizacao(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(documents, "app_base_dir", return_value=Path(temporary)):
                with self.assertRaisesRegex(FileNotFoundError, "Modelo não encontrado"):
                    generate_declaracao_meios_proprios(
                        Path(temporary) / "saida.docx", {"mes_e_ano": "x"}
                    )

    def test_proximo_nome_livre_na_pasta(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            first = next_available_diarias_declaracao_path(directory, "31/12/2026")
            self.assertEqual("declaracao_meios_proprios_31-12-2026.docx", first.name)
            first.write_bytes(b"x")
            second = next_available_diarias_declaracao_path(directory, "31/12/2026")
            self.assertEqual("declaracao_meios_proprios_31-12-2026_2.docx", second.name)


class BotaoMeiosPropriosTest(unittest.TestCase):
    """Exercita o botão verde de ponta a ponta na seção real de Diárias."""

    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.root.geometry("1260x960")
        self.app = SigApp.__new__(SigApp)
        self.app.root = self.root
        self.app.diarias_tab = ttk.Frame(self.root, padding=14)
        self.app.diarias_tab.pack(fill="both", expand=True)
        self.app._select_diarias_pdf = Mock()
        self.app._reload_diarias_pdf = Mock()
        self.app._generate_diarias_requerimento = Mock()
        self.app._start_diarias_activity = Mock(return_value=0.0)
        self.app._finish_diarias_activity = Mock()
        for name in ("ufesp_index", "ufesp", "holerite_file", "holerite_total",
                     "holerite_mes", "talao_file", "abertura_data", "abertura_hora",
                     "fechamento_data", "fechamento_hora", "protocolo_file", "req",
                     "mapa", "data"):
            setattr(self.app, f"diarias_{name}_var", tk.StringVar(master=self.root))
        self.app.diarias_meios_proprios_var = tk.BooleanVar(master=self.root, value=False)
        with patch.object(tk, "_default_root", self.root):
            self.app._build_style()
        self.app._build_diarias_section()
        self.root.update()

    def _botao(self):
        return getattr(self.app, "diarias_meios_proprios_button", None)

    def test_botao_verde_no_rodape_junto_do_requerimento(self):
        button = self._botao()
        self.assertIsNotNone(button, "o botão da declaração precisa existir")
        self.assertEqual("Gerar declaração Meios Próprios", button["text"])
        self.assertEqual(button.master, self.app.diarias_generate_button.master)
        style = ttk.Style(self.root)
        self.assertEqual("#16833a", style.lookup(button["style"], "background"))
        self.assertEqual("#ffffff", style.lookup(button["style"], "foreground"))
        self.assertEqual("normal", str(button["state"]))

    def test_clique_gera_o_docx_na_pasta_escolhida(self):
        self.app.diarias_abertura_data_var.set("31/12/2026")
        self.app.diarias_data_var.set("31/12/2026")
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(
                sig_app.filedialog, "askdirectory", return_value=temporary
            ) as ask, patch.object(
                sig_app.messagebox, "showinfo"
            ) as showinfo, patch.object(
                sig_app.messagebox, "showwarning"
            ) as showwarning:
                self._botao().invoke()
            ask.assert_called_once()
            self.assertTrue(showinfo.called, "o usuário precisa ver onde o arquivo foi salvo")
            self.assertFalse(showwarning.called)
            self.app._finish_diarias_activity.assert_called_once()
            output = Path(temporary) / "declaracao_meios_proprios_31-12-2026.docx"
            self.assertTrue(output.is_file(), "a declaração precisa ser gravada")
            texto = _texto_do_docx(output)
            self.assertIn("referente dezembro/2026", texto)
            self.assertNotIn("{{", texto)
            self.assertIn("declaracao_meios_proprios_31-12-2026.docx", showinfo.call_args.args[1])

    def test_datas_invalidas_avisam_sem_perder_dados(self):
        self.app.diarias_abertura_data_var.set("")
        self.app.diarias_data_var.set("")
        with patch.object(sig_app.filedialog, "askdirectory") as ask, patch.object(
            sig_app.messagebox, "showwarning"
        ) as showwarning:
            self._botao().invoke()
        ask.assert_not_called()
        self.assertEqual("Confira a data de ida do talão.", showwarning.call_args.args[1])
        self.app._finish_diarias_activity.assert_called_once()


if __name__ == "__main__":
    unittest.main()
