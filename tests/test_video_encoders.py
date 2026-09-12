"""Vacina do seletor GPU/CPU e do catalogo de encoders.

Regras do usuário que estes testes travam:
- o principal escolhe só ONDE processar (GPU/CPU); o app decide o encoder concreto;
- o Avançado (só no modo GPU) tem "Automático" e os encoders que passaram na sondagem;
- GPU é usada SEMPRE que possível: o fallback para CPU só acontece quando é
  necessário (GPU sem aquele codec, forçado indisponível, ou trecho curto demais
  para a inicialização da GPU compensar) — e sempre com motivo registrado;
- falha de hardware repete a tarefa na CPU SEM rebaixar a preferência do usuário;
- o codec do arquivo é preservado quando dá para reencodar (HEVC continua HEVC).
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from video_encoders import (  # noqa: E402
    CATALOG,
    ENCODER_ADVANCED_AUTO,
    ENCODER_PATH_CPU,
    ENCODER_PATH_GPU,
    SHORT_JOB_SECONDS,
    EncoderOption,
    catalog_options,
    hevc_tag_arguments,
    normalize_codec,
    options_from_tuples,
    options_to_tuples,
    resolve_encoder,
)
from ffmpeg_tools_panel import FfmpegToolsPanel  # noqa: E402  (regras do seletor)

SOURCE = (ROOT / "src" / "ffmpeg_tools_panel.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

GPU_H264 = EncoderOption("nvenc", "NVENC (NVIDIA)", ENCODER_PATH_GPU, "h264", "h264_nvenc", 10)
GPU_HEVC = EncoderOption("nvenc", "NVENC (NVIDIA)", ENCODER_PATH_GPU, "hevc", "hevc_nvenc", 10)
GPU2_H264 = EncoderOption("qsv", "QSV (Intel)", ENCODER_PATH_GPU, "h264", "h264_qsv", 20)
CPU_H264 = EncoderOption("cpu", "CPU", ENCODER_PATH_CPU, "h264", "libx264", 100)
CPU_HEVC = EncoderOption("cpu", "CPU", ENCODER_PATH_CPU, "hevc", "libx265", 100)
CPU_MPEG4 = EncoderOption("cpu-mpeg4", "CPU (compativel)", ENCODER_PATH_CPU, "h264", "mpeg4", 200)


def method_source(name: str) -> str:
    for node in ast.walk(TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(SOURCE, node) or ""
    raise AssertionError(f"metodo {name} nao encontrado")


class CatalogTests(unittest.TestCase):
    def test_catalogo_tem_os_pares_hevc(self):
        codigos = {(option.key, option.codec) for option in CATALOG}
        for familia in ("nvenc", "qsv", "amf"):
            self.assertIn((familia, "h264"), codigos)
            self.assertIn((familia, "hevc"), codigos)
        self.assertIn(("cpu", "h264"), codigos)
        self.assertIn(("cpu", "hevc"), codigos)

    def test_catalogo_so_tem_codecs_suportados_e_sem_repeticao(self):
        for option in CATALOG:
            self.assertIn(option.codec, ("h264", "hevc"), option)
            self.assertIn(option.path, (ENCODER_PATH_GPU, ENCODER_PATH_CPU), option)
        chaves = [(option.key, option.codec) for option in CATALOG]
        self.assertEqual(len(chaves), len(set(chaves)), "catalogo com par repetido")

    def test_gpu_preferida_na_ordem_de_prioridade(self):
        gpus = catalog_options(codec="h264", path=ENCODER_PATH_GPU)
        self.assertEqual([option.key for option in gpus], ["nvenc", "qsv", "amf"])

    def test_normalize_codec(self):
        self.assertEqual(normalize_codec("H264"), "h264")
        self.assertEqual(normalize_codec("h265"), "hevc")
        self.assertEqual(normalize_codec("hvc1"), "hevc")
        self.assertEqual(normalize_codec("vp9"), "")

    def test_serializacao_das_opcoes(self):
        opcoes = [GPU_H264, CPU_H264]
        self.assertEqual(options_from_tuples(options_to_tuples(opcoes)), opcoes)
        self.assertEqual(options_from_tuples([("x",)]), [])
        self.assertEqual(options_from_tuples(None), [])


class ResolveEncoderTests(unittest.TestCase):
    """GPU sempre que possível; CPU só quando é necessário (e sempre explicado)."""

    def test_gpu_para_trabalho_longo(self):
        escolha = resolve_encoder(codec="h264", path=ENCODER_PATH_GPU, available=[CPU_H264, GPU_H264], seconds=30.0)
        self.assertEqual(escolha.option.encoder, "h264_nvenc")

    def test_gpu_quando_a_duracao_e_desconhecida(self):
        escolha = resolve_encoder(codec="h264", path=ENCODER_PATH_GPU, available=[CPU_H264, GPU_H264])
        self.assertEqual(escolha.option.encoder, "h264_nvenc")

    def test_melhor_gpu_por_prioridade(self):
        escolha = resolve_encoder(codec="h264", path=ENCODER_PATH_GPU, available=[CPU_H264, GPU2_H264, GPU_H264], seconds=20.0)
        self.assertEqual(escolha.option.encoder, "h264_nvenc")

    def test_hevc_usa_o_par_hevc(self):
        gpu = resolve_encoder(codec="hevc", path=ENCODER_PATH_GPU, available=[CPU_HEVC, GPU_HEVC], seconds=20.0)
        self.assertEqual(gpu.option.encoder, "hevc_nvenc")
        cpu = resolve_encoder(codec="hevc", path=ENCODER_PATH_CPU, available=[CPU_H264, CPU_HEVC])
        self.assertEqual(cpu.option.encoder, "libx265")

    def test_cpu_escolhida_pelo_usuario(self):
        escolha = resolve_encoder(codec="h264", path=ENCODER_PATH_CPU, available=[CPU_H264, GPU_H264], seconds=30.0)
        self.assertEqual(escolha.option.encoder, "libx264")
        self.assertIn("CPU", escolha.reason)

    def test_trecho_curto_explica_a_ida_para_a_cpu(self):
        escolha = resolve_encoder(codec="h264", path=ENCODER_PATH_GPU, available=[CPU_H264, GPU_H264], seconds=0.6)
        self.assertEqual(escolha.option.encoder, "libx264")
        self.assertIn("curto", escolha.reason)
        self.assertIn(SHORT_JOB_SECONDS, (3.0,))

    def test_trecho_limite_ainda_usa_gpu(self):
        escolha = resolve_encoder(
            codec="h264", path=ENCODER_PATH_GPU, available=[CPU_H264, GPU_H264], seconds=SHORT_JOB_SECONDS
        )
        self.assertEqual(escolha.option.encoder, "h264_nvenc")

    def test_gpu_sem_o_codec_pedido_cai_na_cpu_com_motivo(self):
        escolha = resolve_encoder(codec="hevc", path=ENCODER_PATH_GPU, available=[GPU_H264, CPU_HEVC], seconds=30.0)
        self.assertEqual(escolha.option.encoder, "libx265")
        self.assertIn("nao tem encoder HEVC", escolha.reason)

    def test_forcado_no_avancado_e_respeitado(self):
        escolha = resolve_encoder(
            codec="h264", path=ENCODER_PATH_GPU, advanced="qsv",
            available=[GPU_H264, GPU2_H264, CPU_H264], seconds=0.4,
        )
        self.assertEqual(escolha.option.encoder, "h264_qsv")
        self.assertIn("forcado", escolha.reason)

    def test_forcado_indisponivel_avisa_e_vai_para_cpu(self):
        escolha = resolve_encoder(
            codec="h264", path=ENCODER_PATH_GPU, advanced="nvenc", available=[CPU_H264], seconds=30.0
        )
        self.assertEqual(escolha.option.encoder, "libx264")
        self.assertIn("nao passou na sondagem", escolha.reason)

    def test_sem_opcao_viavel_devolve_none(self):
        self.assertIsNone(resolve_encoder(codec="h264", path=ENCODER_PATH_CPU, available=[]))

    def test_ultimo_recurso_mpeg4_so_quando_nao_ha_libx264(self):
        escolha = resolve_encoder(codec="h264", path=ENCODER_PATH_CPU, available=[CPU_MPEG4])
        self.assertEqual(escolha.option.encoder, "mpeg4")


class HevcTagTests(unittest.TestCase):
    def test_tag_hvc1_no_mp4_com_hevc(self):
        self.assertEqual(hevc_tag_arguments("libx265", ".mp4"), ["-tag:v", "hvc1"])
        self.assertEqual(hevc_tag_arguments("hevc_nvenc", ".mp4"), ["-tag:v", "hvc1"])
        self.assertEqual(hevc_tag_arguments("libx264", ".mp4"), [])
        self.assertEqual(hevc_tag_arguments("libx265", ".mkv"), [])


class EncoderSelectorWiringTests(unittest.TestCase):
    def test_principal_tem_so_gpu_e_cpu(self):
        self.assertIn("values=(PATH_LABELS[ENCODER_PATH_GPU], PATH_LABELS[ENCODER_PATH_CPU])", SOURCE)
        self.assertIn("StringVar(value=PATH_LABELS[ENCODER_PATH_GPU])", SOURCE)

    def test_avancado_so_no_modo_gpu(self):
        origem = method_source("_refresh_encoder_advanced_controls")
        self.assertIn("ENCODER_PATH_GPU", origem)
        self.assertIn("pack_forget", origem)
        ajuda = method_source("_show_encoder_help")
        self.assertIn("Avançado", ajuda)
        # O texto cita o rotulo do automatico, o curto-circuito da GPU em trecho curto
        # e o aviso de que a falha de hardware cai na CPU com registro no log.
        self.assertIn("ENCODER_ADVANCED_AUTO_LABEL", ajuda)
        self.assertIn("curto", ajuda)
        self.assertIn("CPU", ajuda)

    def test_resolucao_acontece_na_ui_antes_da_worker(self):
        origem = method_source("run_current_tool")
        self.assertIn("_resolve_task_encoder", origem)
        self.assertIn("encoder_options", origem)
        worker = method_source("_worker_wrapper")
        self.assertIn("worker_acceleration", worker)
        resolucao = method_source("_resolve_task_encoder")
        self.assertIn("resolve_encoder", resolucao)
        self.assertIn("_log_encoder_choice", resolucao)

    def test_codec_da_tarefa_vem_do_arquivo(self):
        origem = method_source("_task_codec_and_seconds")
        self.assertIn("cut_media_profile", origem)
        self.assertIn("rotate_media_profile", origem)
        preservado = method_source("_preserved_codec")
        self.assertIn("normalize_codec", preservado)

    def test_falha_de_hardware_nao_rebaixa_a_escolha(self):
        origem = method_source("_execute_video")
        self.assertNotIn("self.acceleration = cpu_fallback", origem)
        self.assertIn("SOMENTE nesta tarefa", origem)
        self.assertIn("_cpu_encoder_for", origem)

    def test_cpu_do_fallback_respeita_o_codec(self):
        origem = method_source("_cpu_encoder_for")
        self.assertIn("hevc", origem)
        self.assertIn("ENCODER_PATH_CPU", origem)

    def test_hvc1_entra_nos_reencodes(self):
        self.assertIn("hevc_tag_arguments", method_source("_cut_video_precise"))
        self.assertIn("hevc_tag_arguments", SOURCE)

    def test_smartcut_resolve_o_encoder_por_trecho(self):
        origem = method_source("_cut_video_smartcut")
        self.assertIn("_smartcut_edge_encoder(codec_family, duracao)", origem)
        borda = method_source("_smartcut_edge_encoder")
        self.assertIn("resolve_encoder", borda)
        self.assertIn("seconds=segundos", borda)

    def test_avancado_lista_uma_entrada_por_vendor(self):
        """Bug relatado: NVENC aparecia duas vezes (h264 e hevc no catalogo)."""
        painel = FfmpegToolsPanel.__new__(FfmpegToolsPanel)
        painel.available_encoder_options = [GPU_H264, GPU_HEVC, CPU_H264, CPU_HEVC]
        self.assertEqual(
            painel._advanced_labels(),
            (painel.ENCODER_ADVANCED_AUTO_LABEL, "NVENC (NVIDIA)"),
        )
        painel.available_encoder_options = [GPU_H264, GPU_HEVC, GPU2_H264, CPU_H264]
        self.assertEqual(
            painel._advanced_labels(),
            (painel.ENCODER_ADVANCED_AUTO_LABEL, "NVENC (NVIDIA)", "QSV (Intel)"),
        )
        # escolher o vendor vale para qualquer codec (a tarefa decide o codec)
        painel.encoder_advanced_var = type("Var", (), {"get": lambda _s: "NVENC (NVIDIA)"})()
        self.assertEqual(painel._advanced_key(), "nvenc")
        painel.encoder_advanced_var = type("Var", (), {"get": lambda _s: painel.ENCODER_ADVANCED_AUTO_LABEL})()
        self.assertEqual(painel._advanced_key(), ENCODER_ADVANCED_AUTO)


if __name__ == "__main__":
    unittest.main()
