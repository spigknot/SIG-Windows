"""Vacina dos modos de corte (SmartCut / Reencode Completo / Sem Reencode).

Regras do usuário que estes testes travam:
- as três opções, nessa ordem e com esses rótulos, com SmartCut como PADRÃO;
- o "?" ao lado do seletor explica os três modos;
- SmartCut = copia o miolo entre keyframes e reencoda só as bordas, com as
  bordas espelhando as características do trecho copiado;
- recorte por seleção força o Reencode Completo; sem keyframe útil, o SmartCut
  também cai no Reencode Completo (com aviso no log).
"""

from __future__ import annotations

import ast
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ffmpeg_tools_panel import (  # noqa: E402
    CUT_MODE_COPY,
    CUT_MODE_HELP,
    CUT_MODE_REENCODE,
    CUT_MODE_SMART,
    CUT_MODES,
    FfmpegToolsPanel,
    MediaProfile,
    VideoAcceleration,
    Cancelled,
)

SOURCE = (ROOT / "src" / "ffmpeg_tools_panel.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
TEMPORARIES = []


def tearDownModule():
    for temp in TEMPORARIES:
        temp.cleanup()


def method_source(name: str) -> str:
    for node in ast.walk(TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(SOURCE, node) or ""
    raise AssertionError(f"método {name} não encontrado")


def painel_smartcut():
    panel = object.__new__(FfmpegToolsPanel)
    panel.acceleration = VideoAcceleration("cpu", "CPU (libx264)", "libx264")
    panel.selected_video_quality = "Alta"
    panel.video_quality_var = MagicMock()
    panel.video_quality_var.get.return_value = "Alta"
    panel._test_temp = tempfile.TemporaryDirectory()
    TEMPORARIES.append(panel._test_temp)
    panel.output_dir = Path(panel._test_temp.name)
    panel.cancel_event = threading.Event()
    panel._ffmpeg = lambda: Path("ffmpeg.exe")
    panel._fmt_seconds = FfmpegToolsPanel._fmt_seconds
    panel._concat_escape = FfmpegToolsPanel._concat_escape
    panel._video_args = lambda *_a, **_k: ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
    panel._smart_join_acceleration_for_codec = lambda familia: panel.acceleration
    panel._smart_join_ts_bitstream = lambda familia: FfmpegToolsPanel._smart_join_ts_bitstream(panel, familia)
    panel._append_log = MagicMock()
    panel.keyframes = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    panel._get_ffprobe = lambda: Path("ffprobe.exe")
    def execute(command, *_args, **_kwargs):
        Path(command[-1]).touch()
    panel._execute = MagicMock(side_effect=execute)
    panel._smart_join_validate_piece = MagicMock()
    panel._smart_join_encoded_delay = lambda _p: 0.0
    panel._smart_join_validate_decoded_junction = MagicMock()
    panel._smartcut_validate_audio = MagicMock()
    def probe(path, packets=False, **_kwargs):
        stream = {"codec_name": "h264", "r_frame_rate": "25", "start_time": "0", "has_b_frames": 0}
        if str(path) == "entrada.mp4":
            times = [i / 25 for i in range(250)]
        else:
            cmd = next(c.args[0] for c in panel._execute.call_args_list if c.args[0][-1] == str(path))
            if "-f" in cmd and cmd[cmd.index("-f") + 1] == "concat":
                start = float(cmd[cmd.index("-ss") + 1]); end = start + float(cmd[cmd.index("-t") + 1])
                times = [i / 25 - start for i in range(250) if start - 1e-6 <= i / 25 < end - 1e-6]
            else:
                times = [i / 25 for i in range(int(cmd[cmd.index("-frames:v") + 1]))]
        return {"streams": [stream], "format": {"start_time": "0"}, "packets": [
            {"pts_time": str(t), "dts_time": str(t), "duration_time": ".04",
             "flags": "K" if t in panel.keyframes else "_"} for t in times]}
    panel._smart_join_probe = probe
    return panel


def midia(**kwargs):
    base = dict(
        duration=10.0, has_audio=True, width=1920, height=1080, fps="25", video_bitrate="2M",
        audio_bitrate="128k", audio_rate=48000, audio_channels=2, audio_layout="stereo",
        has_video=True, rotation=0, audio_codec="aac", video_codec="h264", pix_fmt="yuv420p",
        timebase="1/12800", sar="1:1",
    )
    base.update(kwargs)
    return MediaProfile(**base)


class CutModesTests(unittest.TestCase):
    def test_rotulos_e_ordem(self):
        self.assertEqual(CUT_MODES, (CUT_MODE_SMART, CUT_MODE_REENCODE, CUT_MODE_COPY))
        self.assertEqual(CUT_MODES, ("SmartCut", "Reencode Completo", "Sem Reencode"))
        self.assertIn("values=CUT_MODES", SOURCE)

    def test_padrao_e_smartcut(self):
        self.assertIn("StringVar(value=CUT_MODE_SMART)", SOURCE)

    def test_ajuda_do_selector(self):
        self.assertIn("SmartCut", CUT_MODE_HELP)
        self.assertIn("EXPERIMENTAL", CUT_MODE_HELP)
        self.assertIn("lento e preciso", CUT_MODE_HELP)
        self.assertIn("rápido e menos preciso", CUT_MODE_HELP)
        self.assertIn("cut_mode_help_button", method_source("_build_cut_tab"))
        self.assertIn("CUT_MODE_HELP", method_source("_show_cut_mode_help"))

    def test_apenas_sem_reencode_e_modo_de_copia(self):
        panel = object.__new__(FfmpegToolsPanel)
        for modo, esperado in ((CUT_MODE_SMART, False), (CUT_MODE_REENCODE, False), (CUT_MODE_COPY, True)):
            panel.cut_mode_var = MagicMock()
            panel.cut_mode_var.get.return_value = modo
            self.assertEqual(panel._cut_mode_is_copy(), esperado, modo)

    def test_gerador_de_encoder_ligado_nos_modos_que_reencodam(self):
        origem = method_source("_current_tool_uses_video_encoder")
        self.assertIn("_cut_mode_is_copy", origem)
        # SmartCut reencoda as bordas, então usa encoder; só o Sem Reencode não usa.


class SmartCutArgumentsTests(unittest.TestCase):
    def test_trecho_copiado_usa_stream_copy_e_ts(self):
        panel = painel_smartcut()
        comando = panel._smartcut_segment_arguments(
            Path("entrada.mp4"), Path("saida.ts"), 2.0, 2.0, midia(), "h264", reencode=False
        )
        self.assertIn("-c:v", comando)
        self.assertEqual(comando[comando.index("-c:v") + 1], "copy")
        self.assertIn("-f", comando)
        self.assertEqual(comando[comando.index("-f") + 1], "mpegts")
        self.assertIn("h264_mp4toannexb", comando)
        self.assertIn("+resend_headers+initial_discontinuity", comando)
        # seek ANTES do input (input seek) — com output seek o copy recua um GOP inteiro
        self.assertLess(comando.index("-ss"), comando.index("-i"))
        self.assertIn("-noautorotate", comando)

    def test_borda_espelha_as_caracteristicas_do_trecho_copiado(self):
        panel = painel_smartcut()
        media = midia(width=1280, height=720, fps="30000/1001", pix_fmt="yuv420p", sar="4:3")
        comando = panel._smartcut_segment_arguments(
            Path("entrada.mp4"), Path("saida.ts"), 1.4, 0.6, media, "h264", reencode=True
        )
        self.assertEqual(comando[comando.index("-pix_fmt") + 1], "yuv420p")
        self.assertNotIn("-r", comando)
        self.assertEqual(comando[comando.index("-fps_mode") + 1], "passthrough")
        self.assertIn("setsar=4/3", comando[comando.index("-vf") + 1])
        # F5: o trecho é SÓ VÍDEO — o áudio do SmartCut vem de uma passagem única
        # sobre a fonte, no mux final (costurar áudio por trecho acumulava atraso).
        self.assertIn("-an", comando)
        self.assertNotIn("-c:a", comando)
        self.assertNotIn("-ar", comando)

    def test_trecho_do_smartcut_nao_leva_audio(self):
        panel = painel_smartcut()
        comando = panel._smartcut_segment_arguments(
            Path("entrada.mp4"), Path("saida.ts"), 2.0, 2.0, midia(), "h264", reencode=False,
            audio_precise=False,
        )
        # F5: a política de áudio não se aplica mais aos trechos do SmartCut — o
        # trecho sai mudo e o áudio entra contínuo no mux final (sem emendas).
        self.assertIn("-an", comando)
        self.assertNotIn("-c:a", comando)

    def test_video_sem_audio_nao_mapeia_audio(self):
        panel = painel_smartcut()
        comando = panel._smartcut_segment_arguments(
            Path("entrada.mp4"), Path("saida.ts"), 2.0, 2.0, midia(has_audio=False), "h264", reencode=False
        )
        self.assertNotIn("0:a?", comando)
        self.assertIn("-an", comando)

    def test_codec_family(self):
        self.assertEqual(FfmpegToolsPanel._smartcut_codec_family(midia()), "h264")
        self.assertEqual(FfmpegToolsPanel._smartcut_codec_family(midia(video_codec="hevc")), "hevc")
        self.assertIsNone(FfmpegToolsPanel._smartcut_codec_family(midia(video_codec="vp9")))

    def test_encoder_das_bordas_tem_que_ser_do_mesmo_codec(self):
        panel = painel_smartcut()
        # libx264 para um arquivo H.264: compatível (é o caso normal)
        self.assertEqual(panel._smartcut_edge_encoder("h264").encoder, "libx264")
        # encoder de OUTRO codec (fallback mpeg4 do CPU) não serve para colar no miolo H.264
        panel._smart_join_acceleration_for_codec = lambda _f: VideoAcceleration("cpu", "CPU (fallback)", "mpeg4")
        self.assertIsNone(panel._smartcut_edge_encoder("h264"))
        # HEVC num arquivo H.264 também não
        panel._smart_join_acceleration_for_codec = lambda _f: VideoAcceleration("nvenc", "NVENC", "hevc_nvenc")
        self.assertIsNone(panel._smartcut_edge_encoder("h264"))
        # e o inverso: H.264 num arquivo HEVC não
        panel._smart_join_acceleration_for_codec = lambda _f: VideoAcceleration("nvenc", "NVENC", "h264_nvenc")
        self.assertIsNone(panel._smartcut_edge_encoder("hevc"))
        panel._smart_join_acceleration_for_codec = lambda _f: VideoAcceleration("nvenc", "NVENC", "hevc_nvenc")
        self.assertEqual(panel._smartcut_edge_encoder("hevc").encoder, "hevc_nvenc")

    def test_encoder_incompativel_cai_no_reencode_completo(self):
        panel = painel_smartcut()
        panel._smart_join_acceleration_for_codec = lambda _f: VideoAcceleration("cpu", "CPU (fallback)", "mpeg4")
        panel._cut_video_precise = MagicMock()
        panel._cut_video_smartcut(Path("entrada.mp4"), panel.output_dir / "saida.mp4", 1.4, 4.6, midia())
        panel._cut_video_precise.assert_called_once()
        panel._execute.assert_not_called()
        self.assertTrue(
            any("mesmo codec" in str(chamada) for chamada in panel._append_log.call_args_list)
        )


class SmartCutFlowTests(unittest.TestCase):
    def test_failed_validation_preserves_existing_output(self):
        panel = painel_smartcut()
        output = panel.output_dir / "saida.mp4"
        output.write_bytes(b"previous valid export")
        panel._smartcut_validate_audio.side_effect = RuntimeError("invalid audio")
        with self.assertRaisesRegex(RuntimeError, "invalid audio"):
            panel._cut_video_smartcut(Path("entrada.mp4"), output, 1.4, 4.6, midia())
        self.assertEqual(output.read_bytes(), b"previous valid export")
        self.assertEqual(list(panel.output_dir.iterdir()), [output])

    def test_cancel_after_mux_preserves_existing_output(self):
        panel = painel_smartcut()
        output = panel.output_dir / "saida.mp4"
        output.write_bytes(b"previous valid export")
        def cancel_after_mux(command, *_args, **_kwargs):
            Path(command[-1]).touch()
            if "-f" in command and command[command.index("-f") + 1] == "concat":
                panel.cancel_event.set()
        panel._execute.side_effect = cancel_after_mux
        with self.assertRaises(Cancelled):
            panel._cut_video_smartcut(Path("entrada.mp4"), output, 1.4, 4.6, midia())
        self.assertEqual(output.read_bytes(), b"previous valid export")
        self.assertEqual(list(panel.output_dir.iterdir()), [output])

    def test_tres_trechos_quando_ha_keyframes(self):
        panel = painel_smartcut()
        # [1.4, 4.6] com keyframes em 2,3,4 -> cabeça (1.4-2.0), miolo (2.0-4.0), cauda (4.0-4.6)
        panel._cut_video_smartcut(Path("entrada.mp4"), panel.output_dir / "saida.mp4", 1.4, 4.6, midia())
        comandos = [chamada[0][0] for chamada in panel._execute.call_args_list]
        self.assertEqual(len(comandos), 6)  # 2 bordas, 3 preparações TS, mux final
        rotulos = [chamada[0][1] for chamada in panel._execute.call_args_list]
        self.assertEqual(rotulos, ["Reencodando a borda inicial", "Reencodando a borda final",
                                  "Preparando a borda", "Copiando o miolo", "Preparando a borda", "Montando o arquivo final"])
        # o miolo é stream copy e o mux final copia o vídeo
        miolo = comandos[3]
        self.assertEqual(miolo[miolo.index("-c:v") + 1], "copy")
        final = comandos[-1]
        self.assertEqual(final[final.index("-c:v") + 1], "copy")
        self.assertIn("-f", final)
        self.assertEqual(final[final.index("-f") + 1], "concat")
        # a rotação volta no mux final
        self.assertIn("-display_rotation:v:0", final)
        # o corte fecha no tempo pedido
        self.assertIn("-t", final)
        self.assertEqual(final[final.index("-t") + 1], FfmpegToolsPanel._fmt_seconds(3.2))
        self.assertTrue(any("SmartCut:" in str(chamada) for chamada in panel._append_log.call_args_list))

    def test_concat_do_smartcut_pega_o_audio_da_fonte(self):
        # F5: o mux final monta o vídeo concatenado (entrada 1) com o áudio da
        # FONTE (entrada 0, com seek no início pedido) — uma passagem única, sem
        # emenda de áudio. Antes o áudio vinha dos trechos e acumulava ~20 ms por
        # emenda (medido: +60 ms num corte de duas emendas).
        panel = painel_smartcut()
        panel._cut_video_smartcut(Path("entrada.mp4"), panel.output_dir / "saida.mp4", 1.4, 4.6, midia())

        final = panel._execute.call_args_list[-1][0][0]
        self.assertEqual(final[final.index("-ss") + 1], FfmpegToolsPanel._fmt_seconds(1.4))
        self.assertIn("1:v:0", final)          # vídeo: o concat dos trechos
        self.assertIn("0:a?", final)           # áudio: a fonte, de uma vez
        # reencodado em AAC (o midia() deste arquivo não traz inventário por
        # faixa, então vale o fallback de faixa única; com inventário saem os
        # especificadores -c:a:0/-b:a:0, como no app)
        self.assertEqual(final[final.index("-c:a") + 1], "aac")
        self.assertNotIn("aac_adtstoasc", final)  # não há mais TS de áudio para costurar

    def test_sem_borda_quando_o_tempo_cai_no_keyframe(self):
        panel = painel_smartcut()
        panel._cut_video_smartcut(Path("entrada.mp4"), panel.output_dir / "saida.mp4", 2.0, 4.0, midia())
        rotulos = [chamada[0][1] for chamada in panel._execute.call_args_list]
        self.assertEqual(rotulos, ["Copiando o miolo", "Montando o arquivo final"])
        self.assertEqual(len(panel._execute.call_args_list), 2)

    def test_sem_keyframes_cai_no_reencode_completo(self):
        panel = painel_smartcut()
        panel.keyframes = []
        panel._cut_video_precise = MagicMock()
        panel._cut_video_smartcut(Path("entrada.mp4"), panel.output_dir / "saida.mp4", 1.4, 4.6, midia())
        panel._cut_video_precise.assert_called_once()
        self.assertTrue(
            any("Reencode Completo" in str(chamada) for chamada in panel._append_log.call_args_list)
        )

    def test_codec_incompativel_cai_no_reencode_completo(self):
        panel = painel_smartcut()
        panel._cut_video_precise = MagicMock()
        panel._cut_video_smartcut(Path("entrada.mp4"), panel.output_dir / "saida.mp4", 1.4, 4.6, midia(video_codec="vp9"))
        panel._cut_video_precise.assert_called_once()

    def test_apenas_um_keyframe_no_meio_nao_vale_smartcut(self):
        panel = painel_smartcut()
        panel.keyframes = [3.0]
        panel._cut_video_precise = MagicMock()
        panel._cut_video_smartcut(Path("entrada.mp4"), panel.output_dir / "saida.mp4", 1.4, 4.6, midia())
        panel._cut_video_precise.assert_called_once()

    def test_limpa_a_pasta_temporaria(self):
        self.assertIn("shutil.rmtree", method_source("_cut_video_smartcut"))
        self.assertIn("finally", method_source("_cut_video_smartcut"))


class CutWorkerDispatchTests(unittest.TestCase):
    def _worker(self, modo):
        panel = object.__new__(FfmpegToolsPanel)
        panel.cut_input = MagicMock()
        panel.cut_input.exists.return_value = True
        panel.cut_input.suffix = ".mp4"
        panel.cut_input.stem = "video"
        panel.cut_start_var = MagicMock(); panel.cut_start_var.get.return_value = "1"
        panel.cut_end_var = MagicMock(); panel.cut_end_var.get.return_value = "5"
        panel.cut_mode_var = MagicMock(); panel.cut_mode_var.get.return_value = modo
        panel.cut_audio_policy_var = MagicMock(); panel.cut_audio_policy_var.get.return_value = "Precisão máxima (AAC)"
        panel.cut_stream_policy_var = MagicMock(); panel.cut_stream_policy_var.get.return_value = "Vídeo e áudio"
        panel.worker_options = {"cut_mode": modo}
        panel._seconds = lambda valor, *_a: float(valor)
        panel._probe_media = lambda _p: midia()
        panel.output_dir = Path(".")
        panel._safe_output = lambda _d, stem, ext: Path(f"{stem}{ext}")
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = FfmpegToolsPanel._fmt_seconds
        panel._append_log = MagicMock()
        panel._execute = MagicMock()
        panel._cut_video_precise = MagicMock()
        panel._cut_video_smartcut = MagicMock()
        panel._worker_crop = lambda chave: None
        panel._cut_worker()
        return panel

    def test_smartcut_e_o_padrao(self):
        panel = self._worker(CUT_MODE_SMART)
        panel._cut_video_smartcut.assert_called_once()
        panel._cut_video_precise.assert_not_called()
        panel._execute.assert_not_called()

    def test_reencode_completo(self):
        panel = self._worker(CUT_MODE_REENCODE)
        panel._cut_video_precise.assert_called_once()
        panel._cut_video_smartcut.assert_not_called()

    def test_sem_reencode_copia_sem_reencodar(self):
        panel = self._worker(CUT_MODE_COPY)
        panel._execute.assert_called_once()
        panel._cut_video_precise.assert_not_called()
        panel._cut_video_smartcut.assert_not_called()
        comando = panel._execute.call_args[0][0]
        self.assertIn("copy", comando)

    def test_selecao_de_area_forca_reencode_completo(self):
        panel = object.__new__(FfmpegToolsPanel)
        panel.cut_input = MagicMock()
        panel.cut_input.exists.return_value = True
        panel.cut_input.suffix = ".mp4"
        panel.cut_input.stem = "video"
        panel.cut_start_var = MagicMock(); panel.cut_start_var.get.return_value = "1"
        panel.cut_end_var = MagicMock(); panel.cut_end_var.get.return_value = "5"
        panel.cut_mode_var = MagicMock(); panel.cut_mode_var.get.return_value = CUT_MODE_SMART
        panel.cut_audio_policy_var = MagicMock(); panel.cut_audio_policy_var.get.return_value = "Precisão máxima (AAC)"
        panel.cut_stream_policy_var = MagicMock(); panel.cut_stream_policy_var.get.return_value = "Vídeo e áudio"
        panel.worker_options = {"cut_mode": CUT_MODE_SMART, "cut_crop": (0, 0, 100, 100)}
        panel._seconds = lambda valor, *_a: float(valor)
        panel._probe_media = lambda _p: midia()
        panel.output_dir = Path(".")
        panel._safe_output = lambda _d, stem, ext: Path(f"{stem}{ext}")
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = FfmpegToolsPanel._fmt_seconds
        panel._append_log = MagicMock()
        panel._execute = MagicMock()
        panel._cut_video_precise = MagicMock()
        panel._cut_video_smartcut = MagicMock()
        panel._cut_worker()
        panel._cut_video_precise.assert_called_once()
        panel._cut_video_smartcut.assert_not_called()
        self.assertTrue(
            any("seleção de área" in str(chamada) for chamada in panel._append_log.call_args_list)
        )


if __name__ == "__main__":
    unittest.main()
