"""Declaração de meios próprios: perfil, datas, modelo externo e botão verde."""
from __future__ import annotations

import html
import sys
import tempfile
import tkinter as tk
import unittest
import zipfile
import xml.etree.ElementTree as ET
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
from diarias_profiles import PROFILE_FIELDS

PROFILE = {key: ("1" if key == "classe" else example) for key, _label, example in PROFILE_FIELDS}


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
                "data_ida": "31/12/2026",
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
        self.assertEqual("01/03/2027", replacements["data_ida"])
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
    def test_modelo_contem_as_novas_chaves(self):
        template = ROOT / "modelos" / MEIOS_PROPRIOS_TEMPLATE_NAME
        self.assertTrue(template.is_file(), "o modelo precisa estar em modelos/")
        texto = _texto_do_docx(template)
        chaves = sorted(
            {tripla or dupla for tripla, dupla in documents.WORD_MARKER_RE.findall(texto)}
        )
        self.assertEqual(sorted({"nome", "rg", "cpf", "cargo", "classe", "padrão", "delegacia", "estado_civil", "nascimento", "natural_de", "pai", "mae", "endereco", "cidade_plantao", "mes_e_ano", "data_ida", "cidade_atual", "data_protocolo"}), chaves)

    def test_gera_docx_real_sem_sobrar_marcador(self):
        replacements = prepare_declaracao_meios_proprios(
            data_ida="31/12/2026", data_protocolo="31/12/2026", perfil=PROFILE
        )
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "declaracao_meios_proprios.docx"
            changes = generate_declaracao_meios_proprios(destination, replacements)
            self.assertGreater(changes, 18)
            self.assertIsNone(zipfile.ZipFile(destination).testzip())
            texto = _texto_do_docx(destination)
            self.assertNotIn("{{", texto)
            self.assertIn("referente dezembro/2026", texto)
            self.assertIn("no dia 31/12/2026", texto)
            self.assertIn("Taguaí, 31 de dezembro de 2026", texto)

    def test_perfil_ocorrencias_e_fontes_do_modelo_sao_preservados(self):
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        template = ROOT / "modelos" / MEIOS_PROPRIOS_TEMPLATE_NAME
        with zipfile.ZipFile(template) as original:
            before = ET.fromstring(original.read("word/document.xml"))
        for pai in ("Antônio da Silva", ""):
            with self.subTest(pai=pai), tempfile.TemporaryDirectory() as temporary:
                values = prepare_declaracao_meios_proprios(data_ida="31/12/2026", data_protocolo="02/01/2027", perfil={**PROFILE, "pai": pai})
                output = Path(temporary) / "declaracao.docx"
                generate_declaracao_meios_proprios(output, values)
                with zipfile.ZipFile(output) as filled:
                    after = ET.fromstring(filled.read("word/document.xml"))
                props = lambda tree: [ET.tostring(pr) for pr in tree.findall(".//w:rPr", ns)]
                self.assertEqual(props(before), props(after))
                runs = after.findall(".//w:r", ns)
                text = lambda run: "".join(t.text or "" for t in run.findall("w:t", ns))
                names = [run for run in runs if PROFILE["nome"].upper() in text(run)]
                self.assertEqual(len(names), 2)
                self.assertIsNone(names[0].find("w:rPr/w:b", ns))
                self.assertIsNotNone(names[1].find("w:rPr/w:b", ns))
                plain = _texto_do_docx(output)
                self.assertIn(PROFILE["cargo"], plain)
                self.assertIn(PROFILE["cargo"].upper(), plain)
                self.assertIn("filho de " + (pai + " e de " if pai else "") + PROFILE["mae"], plain)
                self.assertIn("no dia 31/12/2026", plain)
                self.assertIn("Taguaí, 2 de janeiro de 2027", plain)
                self.assertNotIn("{{", plain)
                self.assertNotIn("}}", plain)
        for classe, padrao in (("1", "III"), ("2", "II"), ("3", "I"), ("Especial", "IV")):
            values = prepare_declaracao_meios_proprios(data_ida="31/12/2026", data_protocolo="31/12/2026", perfil={**PROFILE, "classe": classe})
            self.assertEqual(values["padrao"], f"Padrão {padrao}")
            self.assertEqual(values["padrão"], f"Padrão {padrao}")
            self.assertEqual(values["classe"], "Classe Especial" if classe == "Especial" else f"{classe}ª Classe")

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
        profile_patch = patch.object(sig_app.diarias_store, "load_diarias_profile", return_value=PROFILE)
        profile_patch.start()
        self.addCleanup(profile_patch.stop)
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
        for key, value in dict(holerite_total="10.817,23", holerite_mes="12/2026", abertura_data="31/12/2026",
                               abertura_hora="08:00", fechamento_data="31/12/2026", fechamento_hora="21:00",
                               req="215626/2026", mapa="215627/2026", data="31/12/2026").items():
            getattr(self.app, f"diarias_{key}_var").set(value)
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

    def test_clique_abre_salvar_com_nome_padrao_e_permite_nomear_arquivo(self):
        self.app.diarias_abertura_data_var.set("31/12/2026")
        self.app.diarias_data_var.set("31/12/2026")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "declaracao_escolhida.docx"
            output.write_bytes(b"arquivo existente para substituir")
            with patch.object(
                sig_app.filedialog, "asksaveasfilename", return_value=str(output)
            ) as ask, patch.object(
                sig_app.messagebox, "showinfo"
            ) as showinfo, patch.object(
                sig_app.messagebox, "showwarning"
            ) as showwarning, patch.object(
                sig_app.messagebox, "askyesno", return_value=True
            ) as confirm_overwrite:
                self._botao().invoke()
            ask.assert_called_once()
            confirm_overwrite.assert_called_once()
            self.assertEqual(
                next_available_diarias_declaracao_path(
                    Path.home() / "Desktop", "31/12/2026"
                ).name,
                ask.call_args.kwargs["initialfile"],
            )
            self.assertEqual(
                str(Path.home() / "Desktop"), ask.call_args.kwargs["initialdir"]
            )
            self.assertEqual(".docx", ask.call_args.kwargs["defaultextension"])
            self.assertFalse(ask.call_args.kwargs["confirmoverwrite"])
            self.assertTrue(showinfo.called, "o usuário precisa ver onde o arquivo foi salvo")
            self.assertFalse(showwarning.called)
            self.app._finish_diarias_activity.assert_called_once()
            self.assertTrue(output.is_file(), "a declaração precisa ser gravada")
            texto = _texto_do_docx(output)
            self.assertIn("referente dezembro/2026", texto)
            self.assertNotIn("{{", texto)
            self.assertIn("declaracao_escolhida.docx", showinfo.call_args.args[1])

    def test_declaracao_pode_ser_salva_em_pdf(self):
        self.app.diarias_abertura_data_var.set("31/12/2026")
        self.app.diarias_data_var.set("31/12/2026")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "declaracao_escolhida.docx"

            def choose_pdf(**options):
                options["typevariable"].set("PDF (*.pdf)")
                return str(destination)

            with patch.object(
                sig_app.filedialog, "asksaveasfilename", side_effect=choose_pdf
            ) as ask, patch.object(
                sig_app, "generate_declaracao_meios_proprios_pdf"
            ) as generate_pdf, patch.object(
                sig_app, "generate_declaracao_meios_proprios"
            ) as generate_docx, patch.object(
                sig_app.messagebox, "showinfo"
            ):
                self._botao().invoke()

            self.assertIn(("PDF (*.pdf)", "*.pdf"), ask.call_args.kwargs["filetypes"])
            self.assertEqual(destination.with_suffix(".pdf"), generate_pdf.call_args.args[0])
            generate_docx.assert_not_called()

    def test_exportacao_pdf_falha_sem_apagar_arquivo_existente(self):
        replacements = prepare_declaracao_meios_proprios(
            data_ida="31/12/2026", data_protocolo="31/12/2026", perfil=PROFILE
        )
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "declaracao.pdf"
            destination.write_bytes(b"pdf anterior")
            with patch.object(
                documents,
                "export_docx_to_pdf_with_word",
                side_effect=lambda _docx, pdf: Path(pdf).write_bytes(
                    b"%PDF-1.7\ndeclaracao"
                ),
            ):
                changes = documents.generate_declaracao_meios_proprios_pdf(
                    destination, replacements
                )
            self.assertGreater(changes, 18)
            self.assertEqual(b"%PDF-1.7\ndeclaracao", destination.read_bytes())
            destination.write_bytes(b"pdf valido anterior")
            with patch.object(
                documents,
                "export_docx_to_pdf_with_word",
                side_effect=RuntimeError("falha de conversão simulada"),
            ):
                with self.assertRaisesRegex(RuntimeError, "falha de conversão"):
                    documents.generate_declaracao_meios_proprios_pdf(
                        destination, replacements
                    )
            self.assertEqual(b"pdf valido anterior", destination.read_bytes())
            self.assertEqual([destination], list(destination.parent.iterdir()))

    def test_sem_perfil_mostra_aviso_generico_sem_abrir_salvar(self):
        self.app.diarias_abertura_data_var.set("31/12/2026")
        self.app.diarias_data_var.set("31/12/2026")
        with patch.object(sig_app.diarias_store, "load_diarias_profile", return_value=None), patch.object(sig_app.filedialog, "asksaveasfilename") as ask, patch.object(sig_app.messagebox, "showwarning") as warning:
            self._botao().invoke()
        ask.assert_not_called()
        warning.assert_called_once()
        self.assertEqual("Há campos sem preencher.", warning.call_args.args[1])

    def test_datas_invalidas_avisam_sem_perder_dados(self):
        self.app.diarias_abertura_data_var.set("")
        self.app.diarias_data_var.set("")
        with patch.object(sig_app.filedialog, "asksaveasfilename") as ask, patch.object(
            sig_app.messagebox, "showwarning"
        ) as showwarning:
            self._botao().invoke()
        ask.assert_not_called()
        self.assertEqual("Há campos sem preencher.", showwarning.call_args.args[1])
        self.app._finish_diarias_activity.assert_called_once()


if __name__ == "__main__":
    unittest.main()
