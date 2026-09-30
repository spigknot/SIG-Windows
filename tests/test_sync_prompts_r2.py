"""Vacinas do script de prompts do R2 (scripts/sync_prompts_r2.py).

Regras que não podem regredir:
* o APP baixa TODOS os `.txt` da RAIZ de `prompts/` (9: histórico, oitiva,
  qualificação e partes) e ignora a subpasta `prompts_antigos/`, que fica no
  bucket como backup;
* um prompt publicado sem o marcador que a requisição substitui quebraria o
  fluxo em silêncio, com o marcador cru indo para o modelo;
* o `manifest.json` bate com os bytes publicados — um manifesto envelhecido
  faria o app recusar uma versão nova.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_prompts_r2 as sync  # noqa: E402


class EscopoTest(unittest.TestCase):
    def test_escopo_de_download_do_app_e_a_raiz_inteira(self):
        """Decisao do dono: o botao baixa TODOS os .txt da pasta e ignora a subpasta."""
        self.assertEqual(
            (
                "historico_system.txt",
                "historico_user.txt",
                "oitiva_system.txt",
                "oitiva_user.txt",
                "qualificacao_system.txt",
                "qualificacao_user.txt",
                "partes_system.txt",
                "partes_user_botao_historico.txt",
                "partes_user_botao_detectar.txt",
            ),
            sync.APP_PROMPT_FILES,
        )
        self.assertFalse(any("/" in name for name in sync.APP_PROMPT_FILES))

    def test_marcador_da_qualificacao_e_exigido(self):
        """Sem o marcador, o app chamaria o modelo com o marcador cru."""
        self.assertIn(
            "marcador", sync.validate_prompt("qualificacao_user.txt", b"sem marcador")
        )
        self.assertEqual(
            "",
            sync.validate_prompt("qualificacao_user.txt", b"ok {{{TEXTO_DA_CAIXA_AQUI}}}"),
        )

    def test_manifesto_cobre_a_raiz_e_bate_com_o_que_sobe(self):
        """O manifesto e o que faz o app responder 'igual' em UM request.

        Se ele envelhecer, o app recusa uma versao nova: por isso tem de ser
        derivado dos mesmos bytes que o sync publica.
        """
        local = sync.collect_prompts(ROOT / "prompts")
        manifest = json.loads(sync.build_manifest(local))
        self.assertEqual(set(sync.APP_PROMPT_FILES), set(manifest["files"]))
        for name, digest in manifest["files"].items():
            self.assertEqual(sync.sha256_hex(local[name]), digest, name)
        # A subpasta e backup e nunca entra no manifesto.
        self.assertFalse(any(name.startswith("prompts_antigos/") for name in manifest["files"]))

    def test_upload_cobre_todos_os_txt_incluindo_a_subpasta(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in sync.APP_PROMPT_FILES:
                (root / name).write_text("A", encoding="utf-8")
            (root / "prompts_antigos").mkdir()
            (root / "prompts_antigos" / "oitiva_user.txt").write_text("B", encoding="utf-8")
            (root / "nao_e_txt.md").write_text("C", encoding="utf-8")

            files = sync.collect_prompts(root)

            self.assertEqual(
                set(sync.APP_PROMPT_FILES) | {"prompts_antigos/oitiva_user.txt"},
                set(files),
            )

    def test_prompts_do_app_ausentes_reprovam(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                sync.collect_prompts(Path(tmp))


class ValidacaoTest(unittest.TestCase):
    def test_reprova_vazio_e_marcador_ausente(self):
        self.assertNotEqual("", sync.validate_prompt("historico_system.txt", b""))
        self.assertIn("marcador", sync.validate_prompt("historico_user.txt", b"sem marcador"))
        self.assertIn("marcador", sync.validate_prompt("oitiva_user.txt", b"sem marcador"))
        self.assertEqual(
            "",
            sync.validate_prompt("historico_user.txt", b"ok {{conteudo_caixa_transcricao}}"),
        )
        self.assertEqual("", sync.validate_prompt("oitiva_user.txt", b"ok {{{conteudo_caixa_historico}}}"))

    def test_arquivo_da_subpasta_nao_exige_marcador(self):
        self.assertEqual("", sync.validate_prompt("prompts_antigos/historico_user.txt", b"backup antigo"))

    def test_reprova_utf8_invalido_etamanho(self):
        self.assertIn("UTF-8", sync.validate_prompt("historico_system.txt", b"\xc3\x28"))
        self.assertIn(
            "limite",
            sync.validate_prompt("historico_system.txt", b"a" * (sync.MAX_PROMPT_BYTES + 1)),
        )

    def test_os_quatro_prompts_da_pasta_aprovam(self):
        local = sync.collect_prompts(ROOT / "prompts")
        for name in sync.APP_PROMPT_FILES:
            self.assertEqual("", sync.validate_prompt(name, local[name]), name)


if __name__ == "__main__":
    unittest.main()
