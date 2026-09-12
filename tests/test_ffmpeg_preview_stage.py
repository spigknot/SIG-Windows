"""Vacina do palco de prévia das ferramentas FFmpeg (pedido de 11/09).

Regras do usuário que estes testes travam:
1. o vídeo preenche TODO o espaço disponível da aba (sem perder a proporção);
2. o palco é um widget empacotado com altura própria — nunca fica em cima dos
   controles da ferramenta;
3. a roda do mouse dá zoom (para cima aproxima, para baixo afasta) e o arrasto
   com o botão esquerdo move o quadro ampliado.
"""

from __future__ import annotations

import ast
import random
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ffmpeg_tools_panel import (  # noqa: E402
    PREVIEW_DISPLAY_MAX_PIXELS,
    PREVIEW_RENDER_MAX_PIXELS,
    PREVIEW_STAGE_MIN_HEIGHT,
    PREVIEW_STAGE_MIN_WIDTH,
    PREVIEW_ZOOM_MAX,
    PREVIEW_ZOOM_MIN,
    FfmpegToolsPanel,
    MediaProfile,
    preview_clamped_offset,
    preview_drawn_size,
    preview_render_size,
    preview_stage_size,
    preview_view_rect,
    preview_zoom_offsets,
)

SOURCE = (ROOT / "src" / "ffmpeg_tools_panel.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def method_source(name: str) -> str:
    for node in ast.walk(TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(SOURCE, node) or ""
    raise AssertionError(f"método {name} não encontrado em ffmpeg_tools_panel.py")


class PreviewStageGeometryTests(unittest.TestCase):
    def test_stage_uses_all_width_when_it_fits(self):
        # 16:9 num espaço largo: encosta na LARGURA disponível (era o pedido da imagem).
        self.assertEqual(preview_stage_size(1200, 1000, 1920, 1080), (1200, 675))

    def test_stage_uses_all_height_when_width_does_not_fit(self):
        self.assertEqual(preview_stage_size(1200, 400, 1920, 1080), (711, 400))

    def test_stage_respects_portrait_media(self):
        self.assertEqual(preview_stage_size(1000, 800, 1080, 1920), (450, 800))

    def test_stage_defaults_to_16_9_without_media(self):
        self.assertEqual(preview_stage_size(1200, 1000, 0, 0), (1200, 675))

    def test_stage_never_exceeds_the_box_and_touches_an_edge(self):
        random.seed(11)
        for _ in range(400):
            available_width = random.randint(120, 2600)
            available_height = random.randint(80, 1400)
            media_width = random.choice([0, 640, 1280, 1920, 1080, 3840])
            media_height = random.choice([0, 360, 720, 1080, 1920, 2160])
            width, height = preview_stage_size(available_width, available_height, media_width, media_height)
            limit_width = max(PREVIEW_STAGE_MIN_WIDTH, available_width)
            limit_height = max(PREVIEW_STAGE_MIN_HEIGHT, available_height)
            self.assertGreaterEqual(width, PREVIEW_STAGE_MIN_WIDTH)
            self.assertGreaterEqual(height, PREVIEW_STAGE_MIN_HEIGHT)
            # O palco cabe na caixa; a única exceção é o tamanho MÍNIMO
            # utilizável (mídia retrato num espaço baixo e largo), que faz a aba
            # rolar em vez de encolher o player além do utilizável.
            if width > limit_width + 2:
                self.assertEqual(height, PREVIEW_STAGE_MIN_HEIGHT, (available_width, available_height))
            if height > limit_height + 2:
                self.assertEqual(width, PREVIEW_STAGE_MIN_WIDTH, (available_width, available_height))
                continue
            touches = abs(width - limit_width) <= 2 or abs(height - limit_height) <= 2
            self.assertTrue(
                touches or width == PREVIEW_STAGE_MIN_WIDTH or height == PREVIEW_STAGE_MIN_HEIGHT,
                (available_width, available_height, width, height),
            )

    def test_stage_keeps_the_media_proportion_inside_rounding(self):
        for media in ((1920, 1080), (1080, 1920), (1000, 1000), (640, 480)):
            width, height = preview_stage_size(900, 700, *media)
            self.assertAlmostEqual(width / height, media[0] / media[1], delta=0.02)

    def test_degenerate_box_falls_back_to_the_minimums(self):
        self.assertEqual(preview_stage_size(0, 0, 1920, 1080), (PREVIEW_STAGE_MIN_WIDTH, PREVIEW_STAGE_MIN_HEIGHT))


class PreviewZoomGeometryTests(unittest.TestCase):
    def test_fit_zoom_matches_the_stage(self):
        width, height, zoom = preview_drawn_size(983, 553, 1.0)
        self.assertEqual((width, height), (982, 552))
        self.assertEqual(zoom, 1.0)

    def test_zoom_one_step_grows_the_drawn_frame(self):
        width, height, zoom = preview_drawn_size(983, 553, 1.25)
        self.assertEqual((width, height), (1228, 690))
        self.assertAlmostEqual(zoom, 1.25)

    def test_drawn_dimensions_are_always_even(self):
        random.seed(7)
        for _ in range(200):
            stage_width = random.randint(100, 1800)
            stage_height = random.randint(80, 1000)
            zoom = random.uniform(PREVIEW_ZOOM_MIN, PREVIEW_ZOOM_MAX)
            width, height, _zoom = preview_drawn_size(stage_width, stage_height, zoom)
            self.assertEqual(width % 2, 0)
            self.assertEqual(height % 2, 0)
            self.assertGreaterEqual(width, 2)
            self.assertGreaterEqual(height, 2)

    def test_zoom_is_clamped_to_the_allowed_range(self):
        # Palco pequeno: o orçamento de pixels não interfere no limite de zoom.
        self.assertEqual(preview_drawn_size(400, 240, 99)[2], PREVIEW_ZOOM_MAX)
        self.assertEqual(preview_drawn_size(1000, 600, 0.01)[2], PREVIEW_ZOOM_MIN)

    def test_display_budget_caps_the_drawn_image(self):
        width, height, zoom = preview_drawn_size(1400, 788, PREVIEW_ZOOM_MAX)
        self.assertLess(width * height, PREVIEW_DISPLAY_MAX_PIXELS * 1.02)
        self.assertLess(zoom, PREVIEW_ZOOM_MAX)

    def test_pipeline_is_never_larger_than_the_budget(self):
        width, height = preview_render_size(3000, 1687, 0, 0)
        self.assertLessEqual(width * height, PREVIEW_RENDER_MAX_PIXELS)
        self.assertEqual((width, height), (1600, 900))

    def test_pipeline_never_upscales_above_the_source_resolution(self):
        self.assertEqual(preview_render_size(1200, 675, 640, 360), (640, 360))
        self.assertEqual(preview_render_size(982, 552, 1280, 720), (982, 552))

    def test_pipeline_matches_the_drawn_size_at_zoom(self):
        self.assertEqual(preview_render_size(1228, 690, 1280, 720), (1228, 690))

    def test_offsets_never_show_background_while_zoomed(self):
        self.assertEqual(preview_clamped_offset(983, 1228, -9999), -245)
        self.assertEqual(preview_clamped_offset(983, 1228, 50), 0)
        self.assertEqual(preview_clamped_offset(983, 500, -30), 0)
        for offset in range(-4000, 200, 137):
            value = preview_clamped_offset(983, 1228, offset)
            self.assertLessEqual(-245, value)
            self.assertLessEqual(value, 0)

    def test_smaller_frames_are_centered(self):
        self.assertEqual(preview_view_rect(983, 553, 786, 442, 0, 0), (98, 55))

    def test_zoomed_frame_uses_the_clamped_offset(self):
        self.assertEqual(preview_view_rect(983, 553, 1228, 690, 0, 0), (0, 0))
        self.assertEqual(preview_view_rect(983, 553, 1228, 690, -123, -69), (-123, -69))
        self.assertEqual(preview_view_rect(983, 553, 1228, 690, -9999, -9999), (-245, -137))

    def test_zoom_keeps_the_point_under_the_cursor(self):
        # Caso real medido no app (palco 983x553, roda no centro, 1.0 -> 1.25).
        offset_x, offset_y = preview_zoom_offsets(983, 553, 982, 552, 0.0, 0.0, 1228, 690, 491, 276)
        self.assertEqual((offset_x, offset_y), (-123.0, -69.0))

    def test_zoom_anchor_holds_for_random_positions(self):
        random.seed(3)
        for _ in range(300):
            stage_width = random.randint(400, 1600)
            stage_height = random.randint(300, 900)
            drawn_width, drawn_height, _ = preview_drawn_size(stage_width, stage_height, 1.0)
            zoomed_width, zoomed_height, _ = preview_drawn_size(stage_width, stage_height, 2.0)
            offset_x = preview_clamped_offset(stage_width, drawn_width, random.uniform(-500, 0))
            offset_y = preview_clamped_offset(stage_height, drawn_height, random.uniform(-500, 0))
            cursor_x = random.uniform(0, stage_width)
            cursor_y = random.uniform(0, stage_height)
            before_x, before_y = preview_view_rect(
                stage_width, stage_height, drawn_width, drawn_height, offset_x, offset_y
            )
            new_x, new_y = preview_zoom_offsets(
                stage_width, stage_height, drawn_width, drawn_height, offset_x, offset_y,
                zoomed_width, zoomed_height, cursor_x, cursor_y,
            )
            new_x = preview_clamped_offset(stage_width, zoomed_width, new_x)
            new_y = preview_clamped_offset(stage_height, zoomed_height, new_y)
            after_x, after_y = preview_view_rect(
                stage_width, stage_height, zoomed_width, zoomed_height, new_x, new_y
            )
            wanted_x = (cursor_x - before_x) / drawn_width
            got_x = (cursor_x - after_x) / zoomed_width
            wanted_y = (cursor_y - before_y) / drawn_height
            got_y = (cursor_y - after_y) / zoomed_height
            # Sem clamp, o ponto sob o cursor fica exatamente no lugar; com clamp
            # ele pode encostar na borda, mas nunca passa dela.
            self.assertLessEqual(abs(got_x - wanted_x), 0.06)
            self.assertLessEqual(abs(got_y - wanted_y), 0.06)

    def test_wheel_steps_follow_the_platform(self):
        steps = FfmpegToolsPanel._preview_wheel_steps
        self.assertEqual(steps(SimpleNamespace(delta=120, num=0)), 1.0)
        self.assertEqual(steps(SimpleNamespace(delta=-120, num=0)), -1.0)
        self.assertEqual(steps(SimpleNamespace(delta=-240, num=0)), -2.0)
        self.assertEqual(steps(SimpleNamespace(delta=0, num=4)), 1.0)
        self.assertEqual(steps(SimpleNamespace(delta=0, num=5)), -1.0)
        self.assertEqual(steps(SimpleNamespace(delta=0, num=0)), 0.0)

    def test_wheel_steps_survive_missing_tk_event_fields(self):
        # O Tk entrega '??' nos campos que não existem no evento real da roda —
        # era daí que vinha o "invalid literal for int() with base 10: '??'"
        # registrado no log ao rolar o mouse.
        steps = FfmpegToolsPanel._preview_wheel_steps
        self.assertEqual(steps(SimpleNamespace(num="??", delta=120)), 1.0)
        self.assertEqual(steps(SimpleNamespace(num="??", delta=-120)), -1.0)
        self.assertEqual(steps(SimpleNamespace(num="??", delta="??")), 0.0)
        self.assertEqual(steps(SimpleNamespace(num="??", delta=None)), 0.0)
        self.assertEqual(steps(SimpleNamespace(num="", delta="")), 0.0)
        self.assertEqual(steps(SimpleNamespace(delta=120)), 1.0)

    def test_rotated_media_swaps_the_stage_proportion(self):
        media = MediaProfile(10.0, False, 1920, 1080, "30", "1M", "128k", 48000, 2, "stereo")
        self.assertEqual(FfmpegToolsPanel._rotated_media_size(media, "transpose=1"), (1080, 1920))
        self.assertEqual(FfmpegToolsPanel._rotated_media_size(media, "transpose=2"), (1080, 1920))
        self.assertEqual(FfmpegToolsPanel._rotated_media_size(media, "hflip"), (1920, 1080))
        self.assertEqual(FfmpegToolsPanel._rotated_media_size(media, ""), (1920, 1080))


class PreviewReserveTests(unittest.TestCase):
    """O palco não pode comer a folga: os controles têm que continuar visíveis."""

    def test_padding_parsing_handles_tk_forms(self):
        from ffmpeg_tools_panel import (
            frame_vertical_padding,
            parse_tk_padding,
            vertical_padding_total,
        )

        self.assertEqual(parse_tk_padding(""), ())
        self.assertEqual(parse_tk_padding(6), (6,))
        self.assertEqual(parse_tk_padding((0, 12)), (0, 12))
        self.assertEqual(parse_tk_padding("{4 6}"), (4, 6))
        # O Tk entrega padding de frame assim (foi o que zerava o desconto do palco).
        self.assertEqual(parse_tk_padding("<pixel object: '12'>"), (12,))
        self.assertEqual(vertical_padding_total((0, 12)), 12)
        self.assertEqual(frame_vertical_padding("<pixel object: '12'>"), 24)
        self.assertEqual(frame_vertical_padding("{2 4 6 8}"), 8)

    def test_available_box_desconta_paddings(self):
        source = method_source("_preview_available_box")
        self.assertIn("vertical_padding_total", source)
        self.assertIn("frame_vertical_padding", source)
        # Não pode depender da altura do palco (laço de reencaixe com o Tk).
        self.assertNotIn("winfo_reqheight()) - int(holder.winfo_reqheight())", source)


class PreviewStageWiringTests(unittest.TestCase):
    def test_square_stage_is_gone(self):
        self.assertNotIn("_create_stable_preview", SOURCE)
        self.assertEqual(SOURCE.count("self._create_preview_stage("), 3)

    def test_stage_is_a_packed_widget_with_its_own_size(self):
        source = method_source("_create_preview_stage")
        self.assertIn("pack_propagate(False)", source)
        self.assertIn("holder.configure", method_source("_fit_preview_stage"))

    def test_stage_binds_wheel_and_drag(self):
        source = method_source("_create_preview_stage")
        for binding in ("<MouseWheel>", "<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>"):
            self.assertIn(binding, source)

    def test_wheel_zooms_and_never_scrolls_the_panel(self):
        source = method_source("_preview_wheel")
        self.assertIn("_preview_zoom_at", source)
        self.assertIn('return "break"', source)

    def test_pan_moves_the_frame_without_repainting(self):
        source = method_source("_preview_pan_move")
        self.assertIn("_preview_move_item", source)
        self.assertIn("_preview_can_pan", source)

    def test_mouse_buttons_are_split(self):
        # Esquerdo (e meio) arrastam o vídeo; o direito seleciona a área.
        source = method_source("_create_preview_stage")
        for binding in ("<ButtonPress-1>", "<ButtonPress-2>", "<ButtonPress-3>", "<B3-Motion>"):
            self.assertIn(binding, source)

    def test_stage_reserves_the_space_of_the_other_widgets(self):
        # O palco tem altura própria: o espaço dele é o que sobra dos controles,
        # então ele nunca é desenhado em cima deles.
        source = method_source("_preview_available_box")
        self.assertIn("winfo_children", source)
        self.assertIn("winfo_reqheight", source)
        self.assertIn("ffmpeg_scroll_canvas", source)

    def test_frames_are_rendered_at_the_view_size(self):
        source = method_source("_start_canvas_preview")
        self.assertIn("self._preview_pipeline_size(canvas)", source)
        self.assertNotIn("max(320, canvas.winfo_width())", source)

    def test_thumbnail_keeps_the_source_resolution(self):
        source = method_source("_show_video_thumbnail")
        self.assertIn("self.preview_stills[canvas]", source)
        self.assertIn("_paint_preview_view", source)
        self.assertNotIn(".thumbnail(", source)

    def test_live_frames_go_through_the_zoom_view(self):
        source = method_source("_render_canvas_frame")
        self.assertIn("self.preview_frames[canvas]", source)
        self.assertIn("_paint_preview_view", source)

    def test_native_player_is_skipped_when_zoomed(self):
        self.assertIn("_preview_view_is_fitted", method_source("_toggle_preview"))

    def test_new_media_resets_the_view(self):
        source = method_source("_activate_preview")
        self.assertIn("_reset_preview_view", source)
        self.assertIn("_rotated_media_size", source)

    def test_zoom_restarts_the_live_pipeline(self):
        source = method_source("_schedule_preview_restart")
        self.assertIn("PREVIEW_ZOOM_RESTART_MS", source)
        self.assertIn("_restart_canvas_preview", source)


if __name__ == "__main__":
    unittest.main()
