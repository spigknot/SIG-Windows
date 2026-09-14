"""Vacina da seleção de área e dos ajustes do player FFmpeg (pedido de 12/09).

Regras do usuário que estes testes travam:
1. o quadro é desenhado com o botão esquerdo (traço fino amarelo), só dentro do vídeo;
2. ao soltar, a seleção fica exatamente sobre os pixels escolhidos e acompanha
   zoom/deslocamento e o redimensionamento da janela;
3. pode ser redimensionada pelos lados/cantos e apagada pelo botão direito
   ("Desfazer seleção");
4. o zoom out para no vídeo inteiro (1.0) e o zoom in vai até 5x;
5. velocidades disponíveis: 0.25x, 0.5x, 1x, 2x, 4x;
6. os títulos/subtítulos das abas foram removidos;
7. ao Executar com seleção, o app avisa a resolução n x m; OK recorta, Cancelar
   não executa.
"""

from __future__ import annotations

import ast
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ffmpeg_tools_panel import (  # noqa: E402
    CUT_MODE_COPY,
    CUT_MODE_REENCODE,
    PREVIEW_SELECTION_MIN_SIZE,
    PREVIEW_SPEED_VALUES,
    PREVIEW_ZOOM_MAX,
    PREVIEW_ZOOM_MIN,
    FfmpegToolsPanel,
    MediaProfile,
    PreviewSelection,
    selection_crop_label,
    VideoAcceleration,
    preview_drawn_size,
    preview_fraction_from_view,
    preview_view_rect,
    selection_crop_filter,
    selection_crop_pixels,
    selection_from_drag,
    selection_handle_at,
    selection_moved,
    selection_resized,
)

SOURCE = (ROOT / "src" / "ffmpeg_tools_panel.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

SUBTITULOS_REMOVIDOS = (
    "Escolha entre corte preciso com reencode",
    "Extrai o primeiro áudio de um ou mais vídeos/áudios",
    "Gira a imagem, permite recortar o intervalo",
    "Junta arquivos do mesmo tipo",
    "Insere um segundo áudio no ponto escolhido",
    "Remove ruído e permite gerar áudio para transcrição",
)


def method_source(name: str) -> str:
    for node in ast.walk(TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(SOURCE, node) or ""
    raise AssertionError(f"método {name} não encontrado")


def painel_falso():
    panel = object.__new__(FfmpegToolsPanel)
    panel.preview_selections = {}
    panel.preview_selection_drag = {}
    panel.worker_options = {}
    return panel


class SelectionGeometryTests(unittest.TestCase):
    def test_drag_builds_a_normalized_rectangle(self):
        selecao = selection_from_drag((0.2, 0.3), (0.8, 0.9), 0.01, 0.01)
        self.assertIsNotNone(selecao)
        self.assertAlmostEqual(selecao.left, 0.2)
        self.assertAlmostEqual(selecao.top, 0.3)
        self.assertAlmostEqual(selecao.right, 0.8)
        self.assertAlmostEqual(selecao.bottom, 0.9)

    def test_drag_corners_in_any_direction(self):
        direta = selection_from_drag((0.2, 0.2), (0.7, 0.6), 0.01, 0.01)
        inversa = selection_from_drag((0.7, 0.6), (0.2, 0.2), 0.01, 0.01)
        self.assertEqual(direta, inversa)

    def test_drag_is_clamped_to_the_video(self):
        selecao = selection_from_drag((-0.5, -0.2), (1.8, 2.0), 0.01, 0.01)
        self.assertEqual((selecao.left, selecao.top, selecao.right, selecao.bottom), (0.0, 0.0, 1.0, 1.0))

    def test_tiny_drag_is_not_a_selection(self):
        self.assertIsNone(selection_from_drag((0.1, 0.1), (0.1, 0.1), 0.02, 0.02))
        self.assertIsNone(selection_from_drag((0.1, 0.1), (0.11, 0.5), 0.02, 0.02))

    def test_handles_of_all_sides_and_corners(self):
        rect = (100.0, 50.0, 300.0, 200.0)
        casos = {
            "nw": (100, 50), "ne": (300, 50), "sw": (100, 200), "se": (300, 200),
            "n": (200, 50), "s": (200, 200), "w": (100, 125), "e": (300, 125),
            "move": (200, 125),
        }
        for esperado, (x, y) in casos.items():
            self.assertEqual(selection_handle_at(rect, x, y), esperado, esperado)
        self.assertIsNone(selection_handle_at(rect, 1000, 1000))
        self.assertIsNone(selection_handle_at(rect, 200, 400))

    def test_resize_side_and_corner(self):
        selecao = PreviewSelection(0.2, 0.2, 0.8, 0.8)
        oeste = selection_resized(selecao, "w", 0.5, 0.0, 0.01, 0.01)
        self.assertAlmostEqual(oeste.left, 0.5)
        self.assertAlmostEqual(oeste.right, 0.8)
        nordeste = selection_resized(selecao, "ne", 0.95, 0.05, 0.01, 0.01)
        self.assertAlmostEqual(nordeste.right, 0.95)
        self.assertAlmostEqual(nordeste.top, 0.05)
        self.assertAlmostEqual(nordeste.left, 0.2)
        self.assertAlmostEqual(nordeste.bottom, 0.8)

    def test_resize_respects_the_minimum_and_the_frame(self):
        selecao = PreviewSelection(0.2, 0.2, 0.8, 0.8)
        # arrastar o lado oeste além do leste não inverte nem zera
        apertado = selection_resized(selecao, "w", 0.99, 0.0, 0.05, 0.05)
        self.assertLessEqual(apertado.width, 0.8)
        self.assertGreaterEqual(apertado.width, 0.05 - 1e-9)
        fora = selection_resized(selecao, "se", 9.0, 9.0, 0.01, 0.01)
        self.assertLessEqual(fora.right, 1.0)
        self.assertLessEqual(fora.bottom, 1.0)

    def test_move_keeps_the_selection_inside(self):
        selecao = PreviewSelection(0.2, 0.2, 0.6, 0.5)
        movida = selection_moved(selecao, 5.0, 5.0)
        self.assertAlmostEqual(movida.right, 1.0)
        self.assertAlmostEqual(movida.bottom, 1.0)
        self.assertAlmostEqual(movida.width, selecao.width)
        voltando = selection_moved(selecao, -5.0, -5.0)
        self.assertAlmostEqual(voltando.left, 0.0)
        self.assertAlmostEqual(voltando.top, 0.0)

    def test_view_rect_follows_zoom_and_pan(self):
        selecao = PreviewSelection(0.25, 0.5, 0.75, 1.0)
        # quadro 800x400 sem deslocamento: metade direita/inferior
        self.assertEqual(selecao.to_view(800, 400, 0.0, 0.0), (200.0, 200.0, 600.0, 400.0))
        # quadro ampliado (1600x800) e deslocado -100/-50: a seleção anda junto
        self.assertEqual(selecao.to_view(1600, 800, -100.0, -50.0), (300.0, 350.0, 1100.0, 750.0))

    def test_view_and_fraction_are_inverse(self):
        random.seed(5)
        for _ in range(200):
            stage_w = random.randint(200, 1600)
            stage_h = random.randint(150, 900)
            zoom = random.uniform(PREVIEW_ZOOM_MIN, PREVIEW_ZOOM_MAX)
            drawn_w, drawn_h, _ = preview_drawn_size(stage_w, stage_h, zoom)
            offset_x = random.uniform(drawn_w * -1, 0)
            offset_y = random.uniform(drawn_h * -1, 0)
            origin_x, origin_y = preview_view_rect(stage_w, stage_h, drawn_w, drawn_h, offset_x, offset_y)
            selecao = PreviewSelection(0.3, 0.4, 0.7, 0.9)
            rect = selecao.to_view(drawn_w, drawn_h, origin_x, origin_y)
            fracao = preview_fraction_from_view(rect[0], rect[1], drawn_w, drawn_h, origin_x, origin_y)
            self.assertAlmostEqual(fracao[0], selecao.left, places=3)
            self.assertAlmostEqual(fracao[1], selecao.top, places=3)

    def test_crop_pixels_are_even_and_inside(self):
        selecao = PreviewSelection(0.25, 0.25, 0.75, 0.75)
        crop = selection_crop_pixels(selecao, 1920, 1080)
        self.assertEqual(crop, (480, 270, 960, 540))
        self.assertEqual(crop[2] % 2, 0)
        self.assertEqual(crop[3] % 2, 0)

    def test_crop_pixels_clamp_to_the_frame(self):
        random.seed(9)
        for _ in range(200):
            selecao = PreviewSelection(
                random.uniform(-0.2, 0.9), random.uniform(-0.2, 0.9),
                random.uniform(0.0, 1.2), random.uniform(0.0, 1.2),
            )
            crop = selection_crop_pixels(selecao, 640, 360)
            if crop is None:
                continue
            x, y, largura, altura = crop
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertGreaterEqual(largura, 2)
            self.assertGreaterEqual(altura, 2)
            self.assertLessEqual(x + largura, 640)
            self.assertLessEqual(y + altura, 360)
            self.assertEqual(largura % 2, 0)
            self.assertEqual(altura % 2, 0)

    def test_crop_filter_text(self):
        self.assertEqual(selection_crop_filter((10, 20, 100, 50)), "crop=100:50:10:20")

    def test_crop_pixels_snap_an_odd_origin_down_to_the_even_grid(self):
        # F3/T05: pedir y=87 entregava a linha 86 (a grade de croma ajusta um
        # pixel para cima); alinhar para BAIXO faz o retangulo anunciado ser
        # exatamente o que sai no arquivo.
        selecao = PreviewSelection(100 / 1280, 87 / 720, (100 + 322) / 1280, (87 + 162) / 720)
        crop = selection_crop_pixels(selecao, 1280, 720)

        self.assertEqual(crop, (100, 86, 322, 162))
        for valor in crop:
            self.assertEqual(valor % 2, 0)

    def test_crop_label_matches_the_filter_numbers(self):
        # O rotulo usa os MESMOS numeros do filtro: promessa igual a entrega.
        crop = (100, 86, 322, 162)
        self.assertEqual(selection_crop_filter(crop), "crop=322:162:100:86")
        self.assertEqual(selection_crop_label(crop), "322 x 162 pixels a partir de (100, 86)")


class SelectionWiringTests(unittest.TestCase):
    def test_stage_binds_left_pan_and_right_selection(self):
        origem = method_source("_create_preview_stage")
        for binding in ("<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>", "<ButtonPress-2>"):
            self.assertIn(binding, origem)
        for binding in ("<ButtonPress-3>", "<B3-Motion>", "<ButtonRelease-3>"):
            self.assertIn(binding, origem)

    def test_selection_is_thin_and_yellow(self):
        origem = method_source("_draw_preview_selection")
        self.assertIn("PREVIEW_SELECTION_OUTLINE", origem)
        self.assertIn("width=PREVIEW_SELECTION_WIDTH", origem)

    def test_selection_is_redrawn_over_the_frame(self):
        self.assertIn("_draw_preview_selection", method_source("_paint_preview_view"))
        self.assertIn("_redraw_preview_selection", method_source("_preview_move_item"))
        self.assertIn("_draw_preview_selection", method_source("_paint_preview_view"))
        # zoom também redesenha (a seleção acompanha o zoom)
        self.assertIn("_paint_preview_view", method_source("_preview_zoom_at"))

    def test_context_menu_has_undo_item(self):
        origem = method_source("_preview_open_selection_menu")
        self.assertIn("Desfazer seleção", origem)
        self.assertIn("_clear_preview_selection", origem)
        # O menu só abre em clique PARADO (o arrasto direito desenha).
        self.assertIn("_preview_open_selection_menu", method_source("_preview_select_release"))

    def test_new_media_clears_the_selection(self):
        self.assertIn("_clear_preview_selection", method_source("_reset_preview_view"))
        self.assertIn("_clear_preview_selection", method_source("_preview_show_hint"))

    def test_drag_draws_within_the_video(self):
        origem = method_source("_preview_select_motion")
        self.assertIn('"draw"', origem)
        self.assertIn("selection_from_drag", origem)
        self.assertIn('"resize"', origem)
        self.assertIn("selection_resized", origem)
        self.assertIn('"move"', origem)
        self.assertIn("selection_moved", origem)

    def test_left_button_pans_and_right_draws(self):
        # Regra do usuário: esquerdo arrasta o vídeo, direito desenha o quadro.
        self.assertIn("_preview_pan_start", method_source("_preview_press"))
        self.assertIn("_preview_pan_move", method_source("_preview_motion"))
        self.assertIn("_preview_pan_end", method_source("_preview_release"))
        self.assertIn("selection_handle_at", method_source("_preview_select_press"))
        self.assertIn("_preview_open_selection_menu", method_source("_preview_select_release"))
        origem = method_source("_create_preview_stage")
        self.assertIn('"<B2-Motion>"', origem)
        self.assertNotIn("0x0001", method_source("_preview_press"))


class PlayerLimitsTests(unittest.TestCase):
    def test_speeds_are_the_five_values(self):
        self.assertEqual(PREVIEW_SPEED_VALUES, (0.25, 0.5, 1.0, 2.0, 4.0))
        self.assertIn("PREVIEW_SPEED_VALUES", method_source("_change_preview_speed"))

    def test_speed_walk_uses_the_short_list(self):
        panel = painel_falso()
        panel.preview_speed = 1.0
        panel.preview_speed_var = MagicMock()
        panel.preview_playing = False
        FfmpegToolsPanel._change_preview_speed(panel, 1)
        self.assertEqual(panel.preview_speed, 2.0)
        self.assertEqual(panel.preview_speed_var.set.call_args[0][0], "2x")
        FfmpegToolsPanel._change_preview_speed(panel, 1)
        self.assertEqual(panel.preview_speed, 4.0)
        FfmpegToolsPanel._change_preview_speed(panel, 1)
        self.assertEqual(panel.preview_speed, 4.0)
        for _ in range(4):
            FfmpegToolsPanel._change_preview_speed(panel, -1)
        self.assertEqual(panel.preview_speed, 0.25)
        FfmpegToolsPanel._change_preview_speed(panel, -1)
        self.assertEqual(panel.preview_speed, 0.25)
        self.assertEqual(panel.preview_speed_var.set.call_args[0][0], "0.25x")

    def test_zoom_out_stops_at_the_whole_video(self):
        self.assertEqual(PREVIEW_ZOOM_MIN, 1.0)
        # pedir menos que 1x devolve o enquadramento cheio (nada de encolher o vídeo)
        largura, altura, zoom = preview_drawn_size(800, 450, 0.2)
        self.assertEqual(zoom, 1.0)
        self.assertEqual((largura, altura), (800, 450))

    def test_zoom_in_goes_to_five(self):
        self.assertEqual(PREVIEW_ZOOM_MAX, 5.0)
        self.assertEqual(preview_drawn_size(400, 240, 99)[2], 5.0)
        self.assertEqual(preview_drawn_size(400, 240, 5.0)[:2], (2000, 1200))

    def test_titles_and_subtitles_removed(self):
        self.assertNotIn("_section_title", SOURCE)
        self.assertNotIn("Cortar áudio/vídeo", SOURCE)
        for texto in SUBTITULOS_REMOVIDOS:
            self.assertNotIn(texto, SOURCE, texto[:40])


class SelectionRotationTests(unittest.TestCase):
    """Girar/espelhar depois de selecionar: a seleção gira junto (mesmos pixels)."""

    def test_atoms_are_read_in_order(self):
        from ffmpeg_tools_panel import selection_filter_atoms

        self.assertEqual(selection_filter_atoms("transpose=1,hflip"), ["transpose=1", "hflip"])
        self.assertEqual(selection_filter_atoms(""), [])
        self.assertEqual(selection_filter_atoms("null"), [])
        self.assertEqual(selection_filter_atoms("transpose=2,vflip,hflip"), ["transpose=2", "vflip", "hflip"])

    def test_single_atom_mappings(self):
        from ffmpeg_tools_panel import selection_after_filter_atom

        selecao = PreviewSelection(0.1, 0.2, 0.4, 0.6)
        hflip = selection_after_filter_atom(selecao, "hflip")
        self.assertEqual((hflip.left, hflip.top, hflip.right, hflip.bottom), (0.6, 0.2, 0.9, 0.6))
        vflip = selection_after_filter_atom(selecao, "vflip")
        self.assertEqual((vflip.left, vflip.top, vflip.right, vflip.bottom), (0.1, 0.4, 0.4, 0.8))
        cw = selection_after_filter_atom(selecao, "transpose=1")
        self.assertEqual((cw.left, cw.top, cw.right, cw.bottom), (0.4, 0.1, 0.8, 0.4))
        ccw = selection_after_filter_atom(selecao, "transpose=2")
        self.assertEqual((ccw.left, ccw.top, ccw.right, ccw.bottom), (0.2, 0.6, 0.6, 0.9))

    def test_rotating_and_coming_back_restores_the_selection(self):
        from ffmpeg_tools_panel import selection_between_filters

        random.seed(13)
        for _ in range(200):
            selecao = PreviewSelection(
                random.uniform(0, 0.5), random.uniform(0, 0.5),
                random.uniform(0.5, 1.0), random.uniform(0.5, 1.0),
            )
            for giro in ("transpose=1", "transpose=2", "hflip", "vflip", "transpose=1,hflip"):
                ida = selection_between_filters(selecao, "", giro)
                volta = selection_between_filters(ida, giro, "")
                self.assertAlmostEqual(volta.left, selecao.left, places=6, msg=giro)
                self.assertAlmostEqual(volta.top, selecao.top, places=6, msg=giro)
                self.assertAlmostEqual(volta.right, selecao.right, places=6, msg=giro)
                self.assertAlmostEqual(volta.bottom, selecao.bottom, places=6, msg=giro)

    def test_crop_stays_over_the_same_pixels_after_rotating(self):
        from ffmpeg_tools_panel import selection_between_filters

        largura, altura = 1920, 1080
        selecao = PreviewSelection(0.25, 0.10, 0.75, 0.30)
        antes = selection_crop_pixels(selecao, largura, altura)
        self.assertEqual(antes, (480, 108, 960, 216))

        girada = selection_between_filters(selecao, "", "transpose=1")
        # a exibição gira: a seleção passa para a faixa que sobrou na vertical
        depois = selection_crop_pixels(girada, altura, largura)
        self.assertEqual(depois, (756, 480, 216, 960))

        # voltando a fração pelo giro inverso, cai exatamente na seleção original
        from ffmpeg_tools_panel import selection_after_filter_atom

        depois_fracoes = PreviewSelection(
            depois[0] / altura, depois[1] / largura,
            (depois[0] + depois[2]) / altura, (depois[1] + depois[3]) / largura,
        )
        volta = selection_after_filter_atom(depois_fracoes, "transpose=2")
        for atual, esperado in (
            (volta.left, selecao.left), (volta.top, selecao.top),
            (volta.right, selecao.right), (volta.bottom, selecao.bottom),
        ):
            self.assertAlmostEqual(atual, esperado, places=3)

    def test_absurd_angles_swap_the_expected_sides(self):
        from ffmpeg_tools_panel import selection_between_filters

        # 180 graus = hflip + vflip: a seleção vai para o canto oposto
        selecao = PreviewSelection(0.1, 0.2, 0.3, 0.4)
        meia_volta = selection_between_filters(selecao, "", "hflip,vflip")
        self.assertAlmostEqual(meia_volta.left, 0.7)
        self.assertAlmostEqual(meia_volta.top, 0.6)
        self.assertAlmostEqual(meia_volta.right, 0.9)
        self.assertAlmostEqual(meia_volta.bottom, 0.8)

    def test_rotate_tool_reexpresses_the_selection(self):
        origem = method_source("_refresh_rotate_thumbnail")
        self.assertIn("_rotate_selection_with_filters", origem)
        reexpressa = method_source("_rotate_selection_with_filters")
        self.assertIn("selection_between_filters", reexpressa)
        self.assertIn("preview_selection_filters", reexpressa)
        # a seleção guarda com que filtros foi desenhada e o corte esquece ao sair
        self.assertIn("_preview_remember_selection_filters", method_source("_preview_select_release"))
        self.assertIn("preview_selection_filters.pop", method_source("_clear_preview_selection"))


class SelectionWorkerTests(unittest.TestCase):
    @staticmethod
    def _profile():
        return MediaProfile(
            20.0, True, 1920, 1080, "30", "2M", "128k", 48000, 2, "stereo",
            True, 0, "aac", "h264", "yuv420p",
        )

    def test_cut_uses_the_crop_filter(self):
        panel = painel_falso()
        panel._append_log = MagicMock()
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = FfmpegToolsPanel._fmt_seconds
        panel._filter_for_profile = lambda filters, profile: FfmpegToolsPanel._filter_for_profile(panel, filters, profile)
        panel._video_args = lambda *_args, **_kwargs: ["-c:v", "libx264"]
        panel._execute_video = MagicMock()
        perfil = self._profile()
        panel._cut_video_precise(
            Path("entrada.mp4"), Path("saida.mp4"), 1.0, 5.0, perfil,
            copy_audio=False, crop=(100, 50, 640, 360),
        )
        build = panel._execute_video.call_args[0][1]
        comando = build(VideoAcceleration("cpu", "CPU", "libx264"))
        indice = comando.index("-vf")
        self.assertEqual(comando[indice + 1], "crop=640:360:100:50")
        self.assertTrue(any("Recorte por seleção" in str(chamada) for chamada in panel._append_log.call_args_list))

    def test_cut_without_selection_keeps_null_filter(self):
        panel = painel_falso()
        panel._append_log = MagicMock()
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = FfmpegToolsPanel._fmt_seconds
        panel._filter_for_profile = lambda filters, profile: FfmpegToolsPanel._filter_for_profile(panel, filters, profile)
        panel._video_args = lambda *_args, **_kwargs: ["-c:v", "libx264"]
        panel._execute_video = MagicMock()
        panel._cut_video_precise(Path("entrada.mp4"), Path("saida.mp4"), 1.0, 5.0, self._profile())
        comando = panel._execute_video.call_args[0][1](VideoAcceleration("cpu", "CPU", "libx264"))
        self.assertEqual(comando[comando.index("-vf") + 1], "null")

    def test_cut_worker_forces_precise_when_there_is_a_selection(self):
        panel = painel_falso()
        panel.cut_input = MagicMock()
        panel.cut_input.exists.return_value = True
        panel.cut_input.suffix = ".mp4"
        panel.cut_input.stem = "video"
        panel.cut_start_var = MagicMock(); panel.cut_start_var.get.return_value = "1"
        panel.cut_end_var = MagicMock(); panel.cut_end_var.get.return_value = "5"
        panel.cut_mode_var = MagicMock(); panel.cut_mode_var.get.return_value = CUT_MODE_COPY
        panel.cut_audio_policy_var = MagicMock(); panel.cut_audio_policy_var.get.return_value = "Precisão máxima (AAC)"
        panel.cut_stream_policy_var = MagicMock(); panel.cut_stream_policy_var.get.return_value = "Vídeo e áudio"
        panel.worker_options = {"cut_mode": CUT_MODE_COPY, "cut_crop": (10, 20, 100, 50)}
        panel._seconds = lambda value, *_args: float(value)
        panel._probe_media = lambda _path: self._profile()
        panel.output_dir = Path(".")
        panel._safe_output = lambda _directory, stem, extension: Path(f"{stem}{extension}")
        panel._append_log = MagicMock()
        panel._execute = MagicMock()
        panel._cut_video_precise = MagicMock()
        panel._cut_worker()
        panel._cut_video_precise.assert_called_once()
        self.assertEqual(panel._cut_video_precise.call_args.kwargs["crop"], (10, 20, 100, 50))
        panel._execute.assert_not_called()  # não copiou streams

    def test_rotate_appends_the_crop_after_the_rotation(self):
        panel = painel_falso()
        entrada = MagicMock()
        entrada.exists.return_value = True
        entrada.suffix = ".mp4"
        entrada.stem = "entrada"
        panel.rotate_input = entrada
        panel.rotate_degrees_var = MagicMock(); panel.rotate_degrees_var.get.return_value = "90"
        panel.rotate_hflip_var = MagicMock(); panel.rotate_hflip_var.get.return_value = False
        panel.rotate_vflip_var = MagicMock(); panel.rotate_vflip_var.get.return_value = False
        panel.rotate_metadata_var = MagicMock(); panel.rotate_metadata_var.get.return_value = True
        panel.rotate_start_var = MagicMock(); panel.rotate_start_var.get.return_value = "0"
        panel.rotate_end_var = MagicMock(); panel.rotate_end_var.get.return_value = "5"
        panel.rotate_parallel_var = MagicMock(); panel.rotate_parallel_var.get.return_value = False
        panel.rotate_segments_var = MagicMock(); panel.rotate_segments_var.get.return_value = ""
        panel.worker_options = {"rotate_crop": (5, 5, 200, 100)}
        panel._seconds = lambda value, *_args: float(value)
        panel._probe_media = lambda _path: self._profile()
        panel.output_dir = Path(".")
        panel._safe_output = lambda _directory, stem, extension: Path(f"{stem}{extension}")
        panel._append_log = MagicMock()
        panel._ffmpeg = lambda: Path("ffmpeg.exe")
        panel._fmt_seconds = FfmpegToolsPanel._fmt_seconds
        panel._rotated_media_size = FfmpegToolsPanel._rotated_media_size
        panel._filter_for_profile = lambda filters, profile: FfmpegToolsPanel._filter_for_profile(panel, filters, profile)
        panel._rotate_audio_args = lambda _media: ["-c:a", "copy"]
        panel._video_args = lambda *_args, **_kwargs: ["-c:v", "libx264"]
        panel._execute_video = MagicMock()
        panel._execute = MagicMock()
        panel._rotate_worker()
        panel._execute.assert_not_called()  # modo metadados não pode ser usado
        comando = panel._execute_video.call_args[0][1](VideoAcceleration("cpu", "CPU", "libx264"))
        filtro = comando[comando.index("-vf") + 1]
        self.assertEqual(filtro, "transpose=1,crop=200:100:5:5")


class SelectionConfirmTests(unittest.TestCase):
    def _panel(self, modo=CUT_MODE_REENCODE):
        panel = painel_falso()
        panel.cut_preview = object()
        panel.rotate_preview = object()
        panel.cut_media_profile = MediaProfile(10.0, True, 1920, 1080, "30", "1M", "128k", 48000, 2, "stereo")
        panel.rotate_media_profile = None
        panel.preview_selections = {panel.cut_preview: PreviewSelection(0.25, 0.25, 0.75, 0.75)}
        panel.cut_mode_var = MagicMock(); panel.cut_mode_var.get.return_value = modo
        panel.rotate_metadata_var = MagicMock(); panel.rotate_metadata_var.get.return_value = False
        panel.rotate_degrees_var = MagicMock(); panel.rotate_degrees_var.get.return_value = "0"
        panel.rotate_hflip_var = MagicMock(); panel.rotate_hflip_var.get.return_value = False
        panel.rotate_vflip_var = MagicMock(); panel.rotate_vflip_var.get.return_value = False
        panel._update_cut_controls = MagicMock()
        panel._cut_display_size = FfmpegToolsPanel._cut_display_size
        panel._rotated_media_size = FfmpegToolsPanel._rotated_media_size
        panel._preview_selection_crop = lambda canvas, w, h: FfmpegToolsPanel._preview_selection_crop(panel, canvas, w, h)
        panel._rotate_preview_filter = lambda: ''
        return panel

    def test_cancel_does_not_run(self):
        panel = self._panel()
        with patch("ffmpeg_tools_panel.messagebox.askokcancel", return_value=False) as aviso:
            self.assertFalse(panel._confirm_preview_selection("Cortar"))
        mensagem = aviso.call_args[0][1]
        self.assertIn("960 x 540", mensagem)
        self.assertIn("desc", mensagem)
        panel._update_cut_controls.assert_not_called()

    def test_ok_keeps_the_mode_and_returns_true(self):
        panel = self._panel()
        with patch("ffmpeg_tools_panel.messagebox.askokcancel", return_value=True):
            self.assertTrue(panel._confirm_preview_selection("Cortar"))
        panel._update_cut_controls.assert_not_called()

    def test_fast_mode_is_switched_to_precise(self):
        panel = self._panel(modo=CUT_MODE_COPY)
        with patch("ffmpeg_tools_panel.messagebox.askokcancel", return_value=True) as aviso:
            self.assertTrue(panel._confirm_preview_selection("Cortar"))
        panel.cut_mode_var.set.assert_called_once_with(CUT_MODE_REENCODE)
        panel._update_cut_controls.assert_called_once()
        self.assertIn("Reencode", aviso.call_args[0][1])

    def test_no_selection_skips_the_warning(self):
        panel = self._panel()
        panel.preview_selections = {}
        with patch("ffmpeg_tools_panel.messagebox.askokcancel", return_value=False) as aviso:
            self.assertTrue(panel._confirm_preview_selection("Cortar"))
        aviso.assert_not_called()

    def test_other_tools_are_not_affected(self):
        panel = self._panel()
        with patch("ffmpeg_tools_panel.messagebox.askokcancel") as aviso:
            self.assertTrue(panel._confirm_preview_selection("Extrair áudio"))
            self.assertTrue(panel._confirm_preview_selection("Limpar áudio"))
        aviso.assert_not_called()

    def test_run_current_tool_asks_before_capturing_options(self):
        self.assertIn("_confirm_preview_selection", method_source("run_current_tool"))
        self.assertIn("cut_crop", method_source("run_current_tool"))
        self.assertIn("rotate_crop", method_source("run_current_tool"))
        self.assertIn("PREVIEW_SELECTION_MIN_SIZE", SOURCE)


if __name__ == "__main__":
    unittest.main()
