"""Vacinas permanentes da aba Prompts (src/prompt_store.py).

Cobrem as regras decididas pelo dono em 29/09/2026:

1. O prompt `Padrão` NUNCA é sobrescrito (nem por save, nem por import, nem
   quando o id vem com acento ou caixa diferente).
2. `save_as` cria outro arquivo, preservando o `Padrão`.
3. Importar um `.txt` escolhe o slot certo e passa a usá-lo.
4. Customizado apagado cai no `Padrão` (o app nunca fica sem prompt).
5. Validação: vazio, acima de 64 KiB, marcador faltando.
6. O download do padrão é ALL-OR-NOTHING (um reprovado não grava nenhum).
7. O botão só grava quando o conteúdo do R2 é DIFERENTE — igual não baixa.
8. Baixar o padrão preserva os prompts customizados do usuário.
9. O `manifest.json` faz a decisão por hash (1 request) sem baixar prompts.
10. A subpasta `prompts_antigos/` do bucket é ignorada pelo download.
11. Os prompts gravam em %APPDATA%, nunca em `C:\\Program Files`.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import prompt_store  # noqa: E402
from prompt_store import (  # noqa: E402
    HISTORY_TRANSCRIPT_MARKER,
    PROMPT_DEFAULT_ID,
    PROMPT_SLOTS,
    QUALIFICATION_USER,
    ROOT_PROMPT_FILES,
    STATEMENT_HISTORY_MARKER,
    PromptStore,
    download_updates,
    prompts_dir,
    sanitize_id,
)


# Conteúdo mínimo válido por slot (marcador quando o slot exige).
VALID = {
    "historico_system.txt": "Você é um policial que redige o histórico.",
    "historico_user.txt": f"Gere o histórico.\n\n{HISTORY_TRANSCRIPT_MARKER}",
    "oitiva_system.txt": "Você faz a oitiva.",
    "oitiva_user.txt": f"Faça a oitiva.\n\n{STATEMENT_HISTORY_MARKER}",
    "qualificacao_system.txt": "Você qualifica.",
    "qualificacao_user.txt": f"Qualifique.\n\n{prompt_store.QUALIFICATION_RAW_MARKER}",
    "partes_system.txt": "Extraia as partes.",
    "partes_user_botao_historico.txt": f"Partes.\n\n{HISTORY_TRANSCRIPT_MARKER}",
    "partes_user_botao_detectar.txt": f"Partes.\n\n{STATEMENT_HISTORY_MARKER}",
}

BASE_FAKE = "https://exemplo.test/prompts"


class _Resposta:
    """Resposta mínima de `urlopen` para os testes de rede."""

    def __init__(self, data: bytes):
        self._data = data

    def read(self, _size=-1):
        data, self._data = self._data, b""
        return data

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _url_de(request) -> str:
    """`urlopen` recebe um `Request`: extrai a URL de verdade do objeto."""
    return getattr(request, "full_url", None) or str(request)


def faker_r2(arquivos: dict[str, str], manifest: dict | None = None):
    """Substitui a rede por um bucket R2 falso; devolve (contexto, pedidos).

    `manifest=None` simula o bucket sem `manifest.json` (o app compara o
    conteúdo baixado). Qualquer arquivo fora de `arquivos` responde 404.
    """
    pedidos: list[str] = []

    def urlopen(request, timeout=None):
        url = _url_de(request)
        pedidos.append(url)
        if url.endswith("/manifest.json"):
            if manifest is None:
                raise OSError("404 manifest.json")
            return _Resposta(json.dumps(manifest).encode("utf-8"))
        nome = url.rsplit("/", 1)[-1]
        if nome not in arquivos:
            raise OSError(f"404 {nome}")
        return _Resposta(arquivos[nome].encode("utf-8"))

    return patch.object(prompt_store.urllib.request, "urlopen", urlopen), pedidos


class StoreTestCase(unittest.TestCase):
    """Base: store novo em pasta temporária, limpo no fim de cada teste."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "Prompts"
        self.store = PromptStore(self.root, seed_reader=lambda name: VALID[name])
        self.store.ensure_layout()
        # Os testes de importação montam arquivos de exemplo; em `self.tmp`
        # para não sujar a raiz do repo.
        self.tmp = Path(temp.name)

    def baixar(self, arquivos=None, manifest=None, store=None, base=BASE_FAKE):
        """Roda o download contra o bucket falso; devolve (situação, mudanças, pedidos)."""
        contexto, pedidos = faker_r2(VALID if arquivos is None else arquivos, manifest)
        with contexto:
            situacao, mudancas = download_updates(
                store or self.store, base_url=base, files=ROOT_PROMPT_FILES
            )
        return situacao, mudancas, pedidos


class PadraoProtegidoTest(StoreTestCase):
    """Regras 1 e 2: o Padrão não pode ser sobrescrito; Salvar como cria outro."""

    def test_padrao_esta_semeado_e_lido(self):
        for slot in PROMPT_SLOTS:
            self.assertEqual(self.store.read(slot, PROMPT_DEFAULT_ID), VALID[slot.file])

    def test_save_custom_recusa_padrao(self):
        slot = PROMPT_SLOTS[0]
        erro = self.store.save_custom(slot, PROMPT_DEFAULT_ID, "TEXTO NOVO")
        self.assertIsNotNone(erro)
        self.assertIn("não pode ser sobrescrito", erro)
        self.assertEqual(self.store.read(slot, PROMPT_DEFAULT_ID), VALID[slot.file])

    def test_save_custom_recusa_padrao_com_caixa_e_acento(self):
        """`padrao`, `Padrão` e `PADRÃO` são o mesmo id protegido."""
        slot = PROMPT_SLOTS[0]
        for variante in ("padrao", "Padrão", "PADRÃO", "Padrão "):
            erro = self.store.save_custom(slot, variante, "TEXTO NOVO")
            self.assertIsNotNone(erro, variante)
        self.assertEqual(self.store.read(slot, PROMPT_DEFAULT_ID), VALID[slot.file])

    def test_import_text_recusa_padrao(self):
        erro = self.store.import_text(
            PROMPT_SLOTS[0], "padrao.txt", VALID["historico_system.txt"]
        )
        self.assertIsNotNone(erro)
        self.assertIn("Renomeie", erro)

    def test_save_as_cria_outro_arquivo_e_preserva_padrao(self):
        slot = PROMPT_SLOTS[0]
        self.assertIsNone(self.store.save_as(slot, "meu historico", "MEU TEXTO"))
        self.assertEqual(self.store.read(slot, "meu_historico"), "MEU TEXTO")
        self.assertEqual(self.store.read(slot, PROMPT_DEFAULT_ID), VALID[slot.file])
        self.assertTrue((self.root / "custom" / slot.key / "meu_historico.txt").is_file())

    def test_save_as_recusa_id_ja_existente(self):
        slot = PROMPT_SLOTS[0]
        self.store.save_as(slot, "duplicado", "PRIMEIRO")
        erro = self.store.save_as(slot, "duplicado", "SEGUNDO")
        self.assertIsNotNone(erro)
        self.assertEqual(self.store.read(slot, "duplicado"), "PRIMEIRO")

    def test_padrao_baixado_sobrevive_a_um_novo_build(self):
        """ensure_layout semeia só o que falta: o padrão do R2 não é sobrescrito."""
        (self.root / "padrao" / "historico_system.txt").write_text(
            "PADRAO DO R2", encoding="utf-8"
        )
        self.store.ensure_layout()
        self.assertEqual(
            self.store.read(PROMPT_SLOTS[0], PROMPT_DEFAULT_ID), "PADRAO DO R2"
        )


class EscolhaDoPromptTest(StoreTestCase):
    """Regras 3 e 4: lista, marcação de em uso, importação e fallback."""

    def test_entries_comeca_com_padrao_em_cada_slot(self):
        for slot in PROMPT_SLOTS:
            primeira = next(entry for entry in self.store.entries() if entry.slot is slot)
            self.assertEqual(primeira.id, PROMPT_DEFAULT_ID)
            self.assertTrue(primeira.is_default)
            self.assertTrue(primeira.active)
            self.assertIn("Padrao", primeira.label)

    def test_entries_marca_o_prompt_em_uso(self):
        slot = PROMPT_SLOTS[1]
        self.store.save_custom(slot, "meu", VALID["historico_user.txt"])
        self.store.set_active(slot, "meu")
        linhas = [entry for entry in self.store.entries() if entry.slot is slot]
        self.assertEqual([entry.id for entry in linhas], [PROMPT_DEFAULT_ID, "meu"])
        self.assertFalse(linhas[0].active)
        self.assertTrue(linhas[1].active)
        self.assertIn("em uso", linhas[1].display_label)

    def test_set_active_recusa_prompt_inexistente(self):
        erro = self.store.set_active(PROMPT_SLOTS[0], "nao_existe")
        self.assertIsNotNone(erro)
        self.assertEqual(self.store.active_id(PROMPT_SLOTS[0]), PROMPT_DEFAULT_ID)

    def test_import_escolhe_o_slot_pelo_nome(self):
        arquivo = self.tmp / "oitiva_system.txt"
        arquivo.write_text("MEU SISTEMA DE OITIVA", encoding="utf-8")
        slot, erro = self.store.import_path(arquivo)
        self.assertIsNone(erro)
        self.assertEqual(slot.key, "oitiva_system")
        self.assertEqual(self.store.read_active(slot), "MEU SISTEMA DE OITIVA")

    def test_import_escolhe_o_slot_pelo_marcador(self):
        arquivo = self.tmp / "sem_nome.txt"
        arquivo.write_text(VALID["historico_user.txt"], encoding="utf-8")
        slot, erro = self.store.import_path(arquivo)
        self.assertIsNone(erro)
        self.assertEqual(slot.key, "historico_user")

    def test_import_de_arquivo_vazio_recusa(self):
        arquivo = self.tmp / "historico_system.txt"
        arquivo.write_text("   \n", encoding="utf-8")
        slot, erro = self.store.import_path(arquivo)
        self.assertIsNone(slot)
        self.assertIn("vazio", erro)

    def test_read_active_cai_no_padrao_quando_o_customizado_some(self):
        slot = PROMPT_SLOTS[2]
        self.store.save_custom(slot, "temporario", "SISTEMA TEMPORARIO")
        self.store.set_active(slot, "temporario")
        (self.root / "custom" / slot.key / "temporario.txt").unlink()
        self.assertEqual(self.store.read_active(slot), VALID["oitiva_system.txt"])

    def test_ativo_json_com_id_desconhecido_cai_no_padrao(self):
        (self.root / "ativo.json").write_text(
            json.dumps({"oitiva_system": "apagado"}), encoding="utf-8"
        )
        self.assertEqual(
            self.store.read_active(PROMPT_SLOTS[2]), VALID["oitiva_system.txt"]
        )


class ValidacaoTest(StoreTestCase):
    """Regra 5: o que impede um prompt de ser salvo."""

    def test_prompt_vazio_recusa(self):
        self.assertIn("vazio", self.store.validate(PROMPT_SLOTS[0], "   "))

    def test_prompt_acima_de_64_kib_recusa(self):
        grande = "A" * (prompt_store.MAX_PROMPT_BYTES + 1)
        self.assertIn("64 KiB", self.store.validate(PROMPT_SLOTS[0], grande))

    def test_user_sem_marcador_recusa(self):
        erro = self.store.validate(QUALIFICATION_USER, "Qualifique sem marcador nenhum.")
        self.assertIsNotNone(erro)
        self.assertIn("marcador", erro)

    def test_marcador_legado_da_oitiva_e_aceito(self):
        slot = next(s for s in PROMPT_SLOTS if s.key == "oitiva_user")
        self.assertIsNone(
            self.store.validate(
                slot, f"faça\n{prompt_store.STATEMENT_HISTORY_LEGACY_MARKER}"
            )
        )

    def test_system_nao_exige_marcador(self):
        self.assertIsNone(self.store.validate(PROMPT_SLOTS[0], "sem marcador nenhum"))


class DownloadTest(StoreTestCase):
    """Regras 6, 7 e 8: all-or-nothing, só grava se mudar, preserva custom."""

    def setUp(self) -> None:
        super().setUp()
        self.novos = dict(VALID)
        self.novos["historico_system.txt"] = "HISTORICO SYSTEM NOVO DO R2"

    def test_aplica_padrao_novo(self):
        situacao, mudancas, _ = self.baixar(self.novos)
        self.assertEqual(situacao, "atualizado")
        self.assertIn("historico_system.txt", mudancas)
        self.assertEqual(
            self.store.read(PROMPT_SLOTS[0], PROMPT_DEFAULT_ID),
            self.novos["historico_system.txt"],
        )

    def test_crlf_e_o_mesmo_prompt_nao_e_alteracao(self):
        """Regressao do bug real: o R2 tinha CRLF e o app tinha LF.

        O prompt e identico; sem normalizar, o app dizia "8 alterados" num PC
        recem instalado e reescrevia tudo sem mudar nada.
        """
        # `ensure_layout` so semeia os 6 slots; num PC novo as 3 de `partes`
        # tambem chegam (o build novo as traz no `padrao/`).
        for nome in ROOT_PROMPT_FILES:
            (self.root / "padrao" / nome).write_text(VALID[nome], encoding="utf-8")
        crlf = {nome: texto.replace("\n", "\r\n") for nome, texto in VALID.items()}
        situacao, mudancas, _ = self.baixar(crlf)
        self.assertEqual(situacao, "igual", "CRLF nao pode contar como alteracao")
        self.assertEqual(mudancas, [])
        # E nada foi reescrito no disco.
        for nome in ROOT_PROMPT_FILES:
            self.assertEqual((self.root / "padrao" / nome).read_text(encoding="utf-8"), VALID[nome])

    def test_primeiro_clique_com_padrao_ja_igual_diz_igual(self):
        """Regressao: num PC recem instalado o 1o clique nao pode dizer "atualizado".

        O app semeia `padrao/` a partir do executavel, entao o conteudo ja e o
        do R2. Como `origem.json` so existe DEPOIS do primeiro download, a
        comparacao por hash nao tinha com o que comparar: o 1o clique
        reportava 8 "alterados" sem alterar nada. A resposta correta e `igual`,
        decidido pelo CONTEUDO de `padrao/`, nao por um registro que ainda nao
        foi escrito.
        """
        # PC recem instalado: padrao/ semeado, sem origem.json.
        (self.root / "origem.json").unlink(missing_ok=True)
        for nome in ROOT_PROMPT_FILES:
            # As 3 de `partes` tambem entram: o app novo as semeia do executavel.
            (self.root / "padrao" / nome).write_text(VALID[nome], encoding="utf-8")
        digests = {nome: prompt_store.sha256_text(VALID[nome]) for nome in ROOT_PROMPT_FILES}
        situacao, mudancas, _ = self.baixar(VALID, manifest={"files": digests})
        self.assertEqual(situacao, "igual")
        self.assertEqual(mudancas, [])
        # E o app nao pode ter reescrito os arquivos: so o registro de origem.
        for nome in ROOT_PROMPT_FILES:
            self.assertEqual(
                (self.root / "padrao" / nome).read_text(encoding="utf-8"), VALID[nome]
            )
        # O proximo clique sai em UM request, ja com o registro gravado.
        situacao2, mudancas2, pedidos2 = self.baixar(VALID, manifest={"files": digests})
        self.assertEqual(situacao2, "igual")
        self.assertEqual(mudancas2, [])
        self.assertEqual(pedidos2, [f"{BASE_FAKE}/manifest.json"])

    def test_igual_nao_baixa_nem_grava(self):
        """Regra do dono: prompt igual no R2 não é baixado nem gravado."""
        self.store.apply_defaults(VALID, from_r2=True)
        alvo = self.root / "padrao" / "historico_system.txt"
        antes = alvo.read_text(encoding="utf-8")
        mtime = alvo.stat().st_mtime_ns
        situacao, mudancas, _ = self.baixar(VALID)
        self.assertEqual(situacao, "igual")
        self.assertEqual(mudancas, [])
        self.assertEqual(antes, alvo.read_text(encoding="utf-8"))
        self.assertEqual(mtime, alvo.stat().st_mtime_ns)

    def test_manifesto_igual_responde_sem_baixar_prompt(self):
        """Com manifesto, a decisão sai de UM request: nenhum prompt é lido."""
        digests = {nome: prompt_store.sha256_text(texto) for nome, texto in VALID.items()}
        self.store.apply_defaults(VALID, from_r2=True)
        situacao, mudancas, pedidos = self.baixar(VALID, manifest={"files": digests})
        self.assertEqual(situacao, "igual")
        self.assertEqual(mudancas, [])
        self.assertEqual(pedidos, [f"{BASE_FAKE}/manifest.json"])

    def test_manifesto_diferente_dispara_o_download(self):
        digests = {nome: "0" * 64 for nome in ROOT_PROMPT_FILES}
        situacao, mudancas, _ = self.baixar(self.novos, manifest={"files": digests})
        self.assertEqual(situacao, "atualizado")
        self.assertIn("historico_system.txt", mudancas)

    def test_um_prompt_reprovado_nao_grava_nada(self):
        """All-or-nothing: um marcador faltando deixa o padrão inteiro como estava."""
        ruins = dict(self.novos)
        ruins["historico_user.txt"] = "sem marcador nenhum"
        situacao, problemas, _ = self.baixar(ruins)
        self.assertEqual(situacao, "indisponivel")
        self.assertTrue(problemas)
        self.assertEqual(
            self.store.read(PROMPT_SLOTS[0], PROMPT_DEFAULT_ID), VALID["historico_system.txt"]
        )
        self.assertEqual(self.store.read_origins(), {})

    def test_arquivo_ausente_no_r2_nao_grava_nada(self):
        faltando = {nome: texto for nome, texto in self.novos.items() if nome != "oitiva_user.txt"}
        situacao, problemas, _ = self.baixar(faltando)
        self.assertEqual(situacao, "indisponivel")
        self.assertTrue(any("oitiva_user" in p for p in problemas))

    def test_preserva_prompts_customizados(self):
        """Regra do dono: o download substitui o padrão e preserva os customs."""
        slot = PROMPT_SLOTS[0]
        self.store.save_custom(slot, "meu_sistema", "MEU SISTEMA")
        self.store.set_active(slot, "meu_sistema")
        situacao, _, _ = self.baixar(self.novos)
        self.assertEqual(situacao, "atualizado")
        self.assertEqual(self.store.read(slot, "meu_sistema"), "MEU SISTEMA")
        self.assertEqual(self.store.active_id(slot), "meu_sistema")

    def test_customizado_preservado_tambem_quando_o_padrao_muda_de_versao(self):
        slot = PROMPT_SLOTS[1]
        self.store.save_custom(slot, "meu_user", VALID["historico_user.txt"])
        self.baixar(self.novos)
        self.assertIn(
            "meu_user", [entry.id for entry in self.store.entries() if entry.slot is slot]
        )


class EscopoDoDownloadTest(StoreTestCase):
    """Regra 10: a subpasta é ignorada, mas a raiz inteira (com `partes`) desce."""

    def test_arquivos_da_raiz_incluem_partes_e_nao_a_subpasta(self):
        self.assertEqual(len(ROOT_PROMPT_FILES), 9)
        self.assertIn("partes_system.txt", ROOT_PROMPT_FILES)
        self.assertIn("partes_user_botao_historico.txt", ROOT_PROMPT_FILES)
        self.assertIn("partes_user_botao_detectar.txt", ROOT_PROMPT_FILES)
        self.assertFalse(any("/" in nome for nome in ROOT_PROMPT_FILES))

    def test_padrao_ignora_a_subpasta_do_bucket(self):
        self.store.apply_defaults(
            {**VALID, "prompts_antigos/historico_system.txt": "VELHO"}, from_r2=True
        )
        self.assertFalse((self.root / "padrao" / "prompts_antigos").exists())
        self.assertNotIn("prompts_antigos/historico_system.txt", self.store.read_origins())


class ApagarTest(StoreTestCase):
    """O `Padrao` nao pode ser apagado, e apagar o prompt em uso tambem nao."""

    def test_apagar_padrao_e_recusado(self):
        slot = PROMPT_SLOTS[0]
        for variante in (PROMPT_DEFAULT_ID, "padrao", "Padrão", "PADRÃO"):
            erro = self.store.delete_custom(slot, variante)
            self.assertIsNotNone(erro, variante)
            self.assertIn("não pode ser apagado", erro)
        # O arquivo do padrao continua no lugar.
        self.assertTrue((self.root / "padrao" / slot.file).is_file())
        self.assertEqual(self.store.read(slot, PROMPT_DEFAULT_ID), VALID[slot.file])

    def test_apagar_prompt_em_uso_e_recusado(self):
        """Se o slot ficasse sem prompt, a proxima requisicao quebraria."""
        slot = PROMPT_SLOTS[1]
        self.store.save_custom(slot, "em_uso", VALID["historico_user.txt"])
        self.store.set_active(slot, "em_uso")
        erro = self.store.delete_custom(slot, "em_uso")
        self.assertIsNotNone(erro)
        self.assertIn("está em uso", erro)
        self.assertTrue((self.root / "custom" / slot.key / "em_uso.txt").is_file())

    def test_apagar_prompt_customizado_apaga_e_some_da_lista(self):
        slot = PROMPT_SLOTS[1]
        self.store.save_custom(slot, "descartavel", VALID["historico_user.txt"])
        self.assertIn("descartavel", [e.id for e in self.store.entries() if e.slot is slot])
        self.assertIsNone(self.store.delete_custom(slot, "descartavel"))
        self.assertNotIn("descartavel", [e.id for e in self.store.entries() if e.slot is slot])
        self.assertFalse((self.root / "custom" / slot.key / "descartavel.txt").exists())

    def test_apagar_prompt_inexistente_recusa_sem_erro(self):
        erro = self.store.delete_custom(PROMPT_SLOTS[0], "nao_existe")
        self.assertIsNotNone(erro)
        self.assertIn("não existe", erro)

    def test_unset_active_devolve_o_padrao_sem_apagar_arquivo(self):
        """O caminho que a tela usa antes de apagar o prompt em uso."""
        slot = PROMPT_SLOTS[2]
        self.store.save_custom(slot, "sai", "SISTEMA QUE SAI")
        self.store.set_active(slot, "sai")
        self.store.unset_active(slot)
        self.assertEqual(self.store.active_id(slot), PROMPT_DEFAULT_ID)
        self.assertEqual(self.store.read_active(slot), VALID["oitiva_system.txt"])
        # O arquivo continua existindo: unset_active nao apaga nada.
        self.assertTrue((self.root / "custom" / slot.key / "sai.txt").is_file())
        # E agora ele pode ser apagado.
        self.assertIsNone(self.store.delete_custom(slot, "sai"))

    def test_unset_active_preserva_o_ativo_dos_outros_slots(self):
        um, dois = PROMPT_SLOTS[0], PROMPT_SLOTS[2]
        self.store.save_custom(um, "a", "A")
        self.store.save_custom(dois, "b", "B")
        self.store.set_active(um, "a")
        self.store.set_active(dois, "b")
        self.store.unset_active(dois)
        self.assertEqual(self.store.active_id(um), "a")
        self.assertEqual(self.store.active_id(dois), PROMPT_DEFAULT_ID)

    def test_unset_active_em_slot_ja_padrao_nao_faz_nada(self):
        self.store.unset_active(PROMPT_SLOTS[0])
        self.assertEqual(self.store.active_id(PROMPT_SLOTS[0]), PROMPT_DEFAULT_ID)

    def test_apagar_outro_slot_nao_derruba_o_ativo_deste(self):
        """Apagar em um slot nao mexe no prompt em uso de outro."""
        um, dois = PROMPT_SLOTS[0], PROMPT_SLOTS[2]
        self.store.save_custom(um, "guardar", "MEU")
        self.store.set_active(um, "guardar")
        self.store.save_custom(dois, "sai", "OUTRO")
        self.assertIsNone(self.store.delete_custom(dois, "sai"))
        self.assertEqual(self.store.active_id(um), "guardar")
        self.assertEqual(self.store.read_active(um), "MEU")


class CaminhoTest(unittest.TestCase):
    """Regra 11: grava em %APPDATA%, nunca em `C:\\Program Files`."""

    def test_prompts_dir_vive_no_appdata(self):
        caminho = prompts_dir()
        self.assertEqual(caminho.parent.name, "sig")
        self.assertEqual(caminho.name, "Prompts")
        self.assertNotIn("Program Files", " ".join(caminho.parts))
        self.assertTrue(str(caminho).startswith(str(Path(os.environ["APPDATA"]))))

    def test_sanitize_id_nao_deja_sair_da_pasta(self):
        # Separadores de caminho viram "_", e as partes ".." somem no strip.
        for bruto in ("historico/../malicious", "..\\..\\escape", "a/b\\c"):
            limpo = sanitize_id(bruto)
            self.assertNotIn("/", limpo)
            self.assertNotIn("\\", limpo)
            self.assertNotIn("..", limpo)
        self.assertEqual(sanitize_id("historico/../malicious"), "historico_malicious")

    def test_sanitize_id_aceita_acentos_e_espacos(self):
        self.assertEqual(sanitize_id("  oitiva do réu  "), "oitiva_do_réu")
        self.assertEqual(sanitize_id("a" * 200), "a" * 64)


if __name__ == "__main__":
    unittest.main()
