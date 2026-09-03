"""Gerador de QR Code da aba "QR Code" (src/qr_encoder.py) e sua ligacao com
a tela principal (SigApp).

As matrizes abaixo sao valores conhecidos validados contra a especificacao
ISO/IEC 18004: cobrem a versao 1 (sem padrao de alinhamento), a versao 2 (com
padrao de alinhamento) e a versao 7 (bits de versao + varios blocos Reed-
Solomon, que exercitam a intercalacao dos codewords).
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import qr_encoder  # noqa: E402
import sig_app  # noqa: E402
from sig_app import SigApp  # noqa: E402

try:
    import tkinter as tk

    _root = tk.Tk()
    _root.withdraw()
    TK_AVAILABLE = True
except Exception:  # pragma: no cover - ambiente sem display
    TK_AVAILABLE = False


def _as_rows(text: str) -> tuple[str, ...]:
    return tuple(row.replace("#", "1").replace(".", "0") for row in text.split())


QR_V1_L_A = _as_rows(
    """
    #######..#.##.#######
    #.....#..###..#.....#
    #.###.#.##.##.#.###.#
    #.###.#..#.#..#.###.#
    #.###.#...#.#.#.###.#
    #.....#.....#.#.....#
    #######.#.#.#.#######
    ........##.##........
    ###.########.##...#..
    #.##....#.....#...##.
    .#.####..##.#...#...#
    .#.##...##....#...#..
    ..##.##.#...#.#.#.#.#
    ........#..#.#.#.#.#.
    #######.#.##.###.####
    #.....#.######.###...
    #.###.#.##.#.###.##.#
    #.###.#..##...#...##.
    #.###.#.##..#...#...#
    #.....#.#.....#...##.
    #######.###.#.#.#.###
    """
)

QR_V2_M_LINK = _as_rows(
    """
    #######....#..###.#######
    #.....#.##..###...#.....#
    #.###.#.#.#..#.##.#.###.#
    #.###.#.#...#..##.#.###.#
    #.###.#...#.#...#.#.###.#
    #.....#..####...#.#.....#
    #######.#.#.#.#.#.#######
    ........##..#.#..........
    #.....#.#..#...#.##..###.
    #.###..#.###.#.#...#####.
    ...#.#####.######..###.##
    ..#.#....#.#.#.#.##..#..#
    #.######...###.##.#.....#
    #..###...##....##..#...#.
    #....#####.##..#######.##
    #.#....#..##...#.#.#.##.#
    #.##..######....#####.#..
    ........###.###.#...#....
    #######..#.#....#.#.#...#
    #.....#...#.##.##...#..##
    #.###.#..##.#.#######.#.#
    #.###.#..#....#.#.#....##
    #.###.#..#.##...#....##.#
    #.....#..###..#.##.##...#
    #######.#.#..##.##...#..#
    """
)

QR_V7_H_LINK = _as_rows(
    """
    #######.##.#.#####.##...#.#...####..#.#######
    #.....#.##..#.###..##...####...#...#..#.....#
    #.###.#.#.#...####.###.#.##.##..##.#..#.###.#
    #.###.#...###..##.##.#.....#.#.#...##.#.###.#
    #.###.#..#.#.#####..#####..#.##...###.#.###.#
    #.....#.##.#.#.....##...####...#.#....#.....#
    #######.#.#.#.#.#.#.#.#.#.#.#.#.#.#.#.#######
    ........###...#.#..##...###..####.##.........
    ..###.#.##.###.###..#####.#...#...##.###..###
    ..####..##.#.##.#.###..##.##.##..#..##..###.#
    ##..####.#.#..###.#...##.#.##...###.#.###..#.
    ...#.#....###..#.###..##.##.#...##.##...#####
    ##.##.###.....###..#.#.#..######..##...#.#.#.
    .###.#.###.#.####..#....#.....####.###......#
    ##..#.#.#.##...##.#.......#.##.#########..##.
    .#.###.######.#..##...#########.##..#########
    #.###.####.####.##..##.#..#..##...##..#..#.##
    #.##...#.#.#####.#.##...#.#.###.##.###......#
    #.#.#.##.#.###.#...#.#..#.###.....###.#....#.
    .#.###.#...#..#....#.#..#########..########..
    .#..#####..#...####.#####.#....#....######.#.
    #...#...#.##.####.#.#...#.....####.##...##..#
    ..###.#.#.#.##.######.#.###...##..#.#.#.#..#.
    #####...#.###.#...###...#.#.#...##..#...###..
    #...#######..######.#####..##..#....######...
    ###....##..#.###...#..##....#.###..##..#.#..#
    .######..#.#.##.#.........##.#...###.#.#.#...
    .#...#..#.##.##...##.###..#...###.######..#..
    ###..#####.#.#....##......###.#...#.#...##...
    #..#...##....##.#...#.#..########..#..#..##.#
    #.##.##.#...####..#....##.##..##..##...#..##.
    .#.##..##.....#.##########.###..#.#####..###.
    #######.#.##.#.##.##....##...###.##..#.##...#
    ###......#.#.###..###.#.#.####.##..###...##.#
    ....#.###...#...#.#....#..#.#.#..##.##..#.##.
    .####....##.#.#.##.##.#.#....####.##..#.#####
    #..##.#####..#.#..#########.##.#..#.######...
    ........##.###.######...##..##..#...#...#.###
    #######..#...#..#...#.#.#..#..#..##.#.#.##.#.
    #.....#....#..###...#...#..##..##..##...###.#
    #.###.#.##.##..#..#.######..##.#.##.######.##
    #.###.#.#...####....###...##.#####.#....#.#..
    #.###.#.#..#...#........#.##.###..######.#.#.
    #.....#..###..#.....##.#..##....##.......##..
    #######........#.#.##.#####.#..#.##..##.##.#.
    """
)


class _CanvasStub:
    def __init__(self, size: int = 340):
        self.width = size
        self.height = size
        self.items: list[tuple] = []
        self.cleared = 0

    def __getitem__(self, key):
        return str(self.width) if key == "width" else str(self.height)

    def delete(self, *_args):
        self.cleared += 1
        self.items.clear()

    def create_image(self, *args, **kwargs):
        self.items.append((args, kwargs))

    def create_text(self, *args, **kwargs):
        self.items.append((args, kwargs))


class _VarStub:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class _ButtonStub:
    def __init__(self):
        self.state = "normal"
        self.configures: list[dict] = []

    def configure(self, **kwargs):
        self.configures.append(dict(kwargs))
        if "state" in kwargs:
            self.state = kwargs["state"]


class _MessageboxStub:
    """Registra as mensagens da tela sem abrir dialogos modais."""

    def __init__(self, answer: bool = True):
        self.calls: list[tuple[str, str, str]] = []
        self.answer = answer

    def showwarning(self, title, message, **_kwargs):
        self.calls.append(("warning", title, message))
        return "ok"

    def showerror(self, title, message, **_kwargs):
        self.calls.append(("error", title, message))
        return "ok"

    def askyesno(self, title, message, **_kwargs):
        self.calls.append(("askyesno", title, message))
        return self.answer


class _ActivityLogStub:
    """Registra as linhas escritas no log de atividade sem um widget Tk."""

    def __init__(self):
        self.lines: list[tuple[str, str | None]] = []
        self._tags: set[str] = set()
        self._state = "disabled"

    def configure(self, *, state: str | None = None, **_kwargs):
        if state is not None:
            self._state = state

    def tag_names(self):
        return self._tags

    def tag_configure(self, tag, **_kwargs):
        self._tags.add(tag)

    def insert(self, index, line, tag=None):
        self.lines.append((str(line), tag))

    def see(self, index):
        pass


class QrEncoderTests(unittest.TestCase):
    def test_version_1_matches_known_matrix(self):
        code = qr_encoder.QrCode.encode_text("A", "L")
        self.assertEqual(code.version, 1)
        self.assertEqual(code.size, 21)
        self.assertEqual(
            tuple("".join("1" if v else "0" for v in row) for row in code.get_matrix()),
            QR_V1_L_A,
        )

    def test_version_2_matches_known_matrix(self):
        code = qr_encoder.QrCode.encode_text("https://sig.local", "M")
        self.assertEqual(code.version, 2)
        self.assertEqual(code.size, 25)
        self.assertEqual(
            tuple("".join("1" if v else "0" for v in row) for row in code.get_matrix()),
            QR_V2_M_LINK,
        )

    def test_version_7_matches_known_matrix(self):
        code = qr_encoder.QrCode.encode_text(
            "https://www.tjsp.jus.br/consultas?codigo=1234567890&token=abcdef", "H"
        )
        self.assertEqual(code.version, 7)
        self.assertEqual(code.size, 45)
        self.assertEqual(
            tuple("".join("1" if v else "0" for v in row) for row in code.get_matrix()),
            QR_V7_H_LINK,
        )

    def test_utf8_text_is_encoded_as_bytes(self):
        code = qr_encoder.QrCode.encode_text("Relatório — çõé", "M")
        self.assertGreaterEqual(code.version, 1)
        self.assertEqual(
            qr_encoder.QrCode.encode_bytes("Relatório — çõé".encode("utf-8"), "M").get_matrix(),
            code.get_matrix(),
        )

    def test_picks_the_smallest_version_that_fits(self):
        self.assertEqual(qr_encoder.QrCode.encode_text("a", "H").version, 1)
        self.assertEqual(qr_encoder.QrCode.encode_text("a" * 14, "H").version, 2)
        self.assertGreater(
            qr_encoder.QrCode.encode_text("a" * 1200, "H").version,
            qr_encoder.QrCode.encode_text("a" * 1200, "L").version,
        )

    def test_content_above_the_limit_is_rejected(self):
        with self.assertRaises(qr_encoder.QrCapacityError):
            qr_encoder.QrCode.encode_text("a" * 5000, "L")

    def test_capacity_matches_the_standard_versions(self):
        # Limites oficiais de capacidade em modo byte (ISO/IEC 18004).
        self.assertEqual(qr_encoder.QrCode.encode_text("a" * 17, "L").version, 1)
        self.assertEqual(qr_encoder.QrCode.encode_text("a" * 18, "L").version, 2)
        self.assertEqual(qr_encoder.QrCode.encode_text("a" * 1273, "H").version, 40)
        self.assertEqual(qr_encoder.QrCode.encode_text("a" * 2953, "L").version, 40)
        with self.assertRaises(qr_encoder.QrCapacityError):
            qr_encoder.QrCode.encode_text("a" * 1274, "H")
        with self.assertRaises(qr_encoder.QrCapacityError):
            qr_encoder.QrCode.encode_text("a" * 2954, "L")

    def test_invalid_error_correction_level(self):
        with self.assertRaises(ValueError):
            qr_encoder.QrCode.encode_text("sig", "Z")

    def test_to_image_includes_the_quiet_zone(self):
        code = qr_encoder.QrCode.encode_text("https://sig.local", "M")
        image = code.to_image(scale=6, border=4)
        expected = (code.size + 8) * 6
        self.assertEqual((image.width, image.height), (expected, expected))
        # A margem branca precisa estar presente nos quatro cantos.
        for corner in ((0, 0), (expected - 1, 0), (0, expected - 1), (expected - 1, expected - 1)):
            self.assertEqual(image.getpixel(corner), (255, 255, 255), corner)

    def test_image_matches_the_matrix(self):
        code = qr_encoder.QrCode.encode_text("https://sig.local", "M")
        scale = 4
        image = code.to_image(scale=scale, border=4)
        matrix = code.get_matrix()
        for y in range(code.size):
            for x in range(code.size):
                pixel = image.getpixel(((x + 4) * scale, (y + 4) * scale))
                expected = (0, 0, 0) if matrix[y][x] else (255, 255, 255)
                self.assertEqual(pixel, expected, (x, y))


class QrClipboardTests(unittest.TestCase):
    def test_dib_header_describes_a_bottom_up_24_bit_bitmap(self):
        code = qr_encoder.QrCode.encode_text("https://sig.local", "M")
        image = code.to_image(scale=2, border=0)
        dib = qr_encoder._bitmap_to_dib(image)
        width, height = image.size
        row_size = ((width * 24 + 31) // 32) * 4
        header = dib[:40]
        self.assertEqual(
            struct.unpack("<IiiHHIIiiII", header),
            (40, width, height, 1, 24, 0, row_size * height, 0, 0, 0, 0),
        )
        self.assertEqual(len(dib), 40 + row_size * height)

    def test_dib_first_pixel_row_is_the_bottom_line(self):
        image = qr_encoder.QrCode.encode_text("https://sig.local", "M").to_image(scale=2, border=0)
        dib = qr_encoder._bitmap_to_dib(image)
        width, height = image.size
        row_size = ((width * 24 + 31) // 32) * 4
        first_row = dib[40:40 + row_size]
        bottom_left = image.getpixel((0, height - 1))
        # CF_DIB armazena BGR e a primeira linha e a de baixo da imagem.
        self.assertEqual(
            (first_row[0], first_row[1], first_row[2]),
            (bottom_left[2], bottom_left[1], bottom_left[0]),
        )

    def test_png_output_is_a_valid_png(self):
        image = qr_encoder.QrCode.encode_text("https://sig.local", "M").to_image(scale=3, border=2)
        data = qr_encoder.image_to_png_bytes(image)
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))


class QrRoundTripTests(unittest.TestCase):
    """Decodifica a matriz de modulos sem usar o proprio encoder para
    conferir Reed-Solomon e payload. Garante que qualquer leitor real
    (conforme a ISO/IEC 18004) consegue ler os QR Codes emitidos pelo SIG."""

    def _gf_mul(self, x, y):
        z = 0
        for i in range(7, -1, -1):
            z = (z << 1) ^ ((z >> 7) * 0x11D)
            z ^= ((y >> i) & 1) * x
        return z & 0xFF

    def _mask_bit(self, mask, x, y):
        if mask == 0:
            return (x + y) % 2 == 0
        if mask == 1:
            return y % 2 == 0
        if mask == 2:
            return x % 3 == 0
        if mask == 3:
            return (x + y) % 3 == 0
        if mask == 4:
            return (x // 3 + y // 2) % 2 == 0
        if mask == 5:
            return x * y % 2 + x * y % 3 == 0
        if mask == 6:
            return (x * y % 2 + x * y % 3) % 2 == 0
        return ((x + y) % 2 + x * y % 3) % 2 == 0

    def _function_map(self, version, size):
        is_fn = [[False] * size for _ in range(size)]
        for i in range(size):
            is_fn[6][i] = True
            is_fn[i][6] = True
        for (cx, cy) in ((3, 3), (size - 4, 3), (3, size - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        is_fn[y][x] = True
        positions = qr_encoder._alignment_pattern_positions(version)
        last = len(positions) - 1
        for i, px in enumerate(positions):
            for j, py in enumerate(positions):
                if (i == 0 and j == 0) or (i == 0 and j == last) or (i == last and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        is_fn[py + dy][px + dx] = True
        for y in range(6):
            is_fn[y][8] = True
        is_fn[7][8] = True
        is_fn[8][8] = True
        is_fn[8][7] = True
        for x in range(6):
            is_fn[8][x] = True
        for x in range(size - 8, size):
            is_fn[8][x] = True
        for y in range(size - 7, size):
            is_fn[y][8] = True
        is_fn[size - 8][8] = True
        if version >= 7:
            for i in range(18):
                a = size - 11 + i % 3
                b = i // 3
                is_fn[b][a] = True
                is_fn[a][b] = True
        return is_fn

    def _read_format(self, matrix):
        positions = [(8, i) for i in range(6)] + [(8, 7), (8, 8), (7, 8)]
        positions += [(14 - i, 8) for i in range(9, 15)]
        bits = 0
        for index, (x, y) in enumerate(positions):
            if matrix[y][x]:
                bits |= 1 << index
        raw = bits ^ 0x5412
        data = raw >> 10
        check = data
        for _ in range(10):
            check = (check << 1) ^ ((check >> 9) * 0x537)
        self.assertEqual(check & 0x3FF, raw & 0x3FF, "BCH dos bits de formato")
        ecl_value = data >> 3
        ecl = {1: "L", 0: "M", 3: "Q", 2: "H"}[ecl_value]
        return ecl, data & 0x07

    def _read_codewords(self, matrix, is_fn, size, mask):
        bits = []
        for right in range(size - 1, 0, -2):
            if right <= 6:
                right -= 1
            for vertical in range(size):
                for j in range(2):
                    x = right - j
                    upward = (right + 1) & 2 == 0
                    y = (size - 1 - vertical) if upward else vertical
                    if not is_fn[y][x]:
                        value = bool(matrix[y][x])
                        if self._mask_bit(mask, x, y):
                            value = not value
                        bits.append(1 if value else 0)
        total = len(bits) // 8 * 8
        return [int("".join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, total, 8)]

    def _deinterleave(self, codewords, version, ecl):
        num_blocks = qr_encoder._NUM_ERROR_CORRECTION_BLOCKS[ecl][version]
        ecc_len = qr_encoder._ECC_CODEWORDS_PER_BLOCK[ecl][version]
        raw = qr_encoder._num_raw_data_modules(version) // 8
        num_short = num_blocks - raw % num_blocks
        short_len = raw // num_blocks
        blocks = [[] for _ in range(num_blocks)]
        index = 0
        for i in range(short_len + 1):
            for j in range(num_blocks):
                if i == short_len - ecc_len and j < num_short:
                    continue
                blocks[j].append(codewords[index])
                index += 1
        return blocks, ecc_len

    def _zero_syndromes(self, block, ecc_len):
        for k in range(ecc_len):
            alpha = 1
            for _ in range(k):
                alpha = self._gf_mul(alpha, 2)
            acc = 0
            for value in block:
                acc = self._gf_mul(acc, alpha) ^ value
            if acc != 0:
                return False
        return True

    def _decode_payload(self, data_codewords, version):
        bits = "".join(f"{b:08b}" for b in data_codewords)
        mode = int(bits[:4], 2)
        self.assertEqual(mode, 0b0100, "modo byte")
        pos = 4
        count_bits = 8 if version <= 9 else 16
        length = int(bits[pos:pos + count_bits], 2)
        pos += count_bits
        payload = bytearray()
        for _ in range(length):
            payload.append(int(bits[pos:pos + 8], 2))
            pos += 8
        return bytes(payload)

    def test_decode_round_trip_and_reed_solomon_syndrome_zero(self):
        samples = [
            ("https://www.exemplo.com.br", "M"),
            ("https://a.co", "L"),
            ("link curto", "Q"),
            ("https://" + "x" * 300, "H"),
            ("https://" + "y" * 900, "M"),
            ("https://" + "z" * 1200, "H"),
        ]
        for text, ecl in samples:
            with self.subTest(text=text, ecl=ecl):
                code = qr_encoder.QrCode.encode_text(text, ecl)
                matrix = code.get_matrix()
                size = code.size
                read_ecl, read_mask = self._read_format(matrix)
                self.assertEqual(read_ecl, ecl)
                self.assertEqual(read_mask, code.mask)
                is_fn = self._function_map(code.version, size)
                codewords = self._read_codewords(matrix, is_fn, size, read_mask)
                blocks, ecc_len = self._deinterleave(codewords, code.version, ecl)
                for block in blocks:
                    self.assertTrue(
                        self._zero_syndromes(block, ecc_len),
                        "sindrome de Reed-Solomon nao zero",
                    )
                data = []
                for block in blocks:
                    data.extend(block[:len(block) - ecc_len])
                self.assertEqual(self._decode_payload(data, code.version), text.encode("utf-8"))

    def test_overflow_is_rejected_with_a_clear_error(self):
        with self.assertRaisesRegex(qr_encoder.QrCapacityError, "limite"):
            qr_encoder.QrCode.encode_text("a" * 5000, "H")


@unittest.skipUnless(TK_AVAILABLE, "tkinter indisponivel")
class QrCodeTabTests(unittest.TestCase):
    def setUp(self):
        self.messages = _MessageboxStub()
        self._original_messagebox = sig_app.messagebox
        sig_app.messagebox = self.messages
        self.clipboard: list[str] = []
        _root.clipboard_clear = lambda: self.clipboard.clear()
        _root.clipboard_append = lambda text: self.clipboard.append(text)
        _root.clipboard_get = lambda: self._clipboard_get()

    def tearDown(self):
        sig_app.messagebox = self._original_messagebox

    def _clipboard_get(self) -> str:
        if not self.clipboard:
            raise RuntimeError("clipboard vazia")
        return self.clipboard[-1]

    def _make_app(self) -> SigApp:
        app = object.__new__(SigApp)
        app.root = _root
        app.qrcode_link_var = _VarStub()
        app.qrcode_status_var = _VarStub()
        app.qrcode = None
        app.qrcode_photo = None
        app.qrcode_canvas = _CanvasStub()
        app.qrcode_copy_button = _ButtonStub()
        app.qrcode_link_entry = tk.Entry(_root)
        app.status_var = _VarStub()
        app._activity_status_suppressed = 0
        app.activity_log = _ActivityLogStub()
        return app

    def test_generate_renders_the_code_and_enables_copy(self):
        app = self._make_app()
        app.qrcode_link_var.set("https://sig.local")
        app.generate_qrcode()

        self.assertIsNotNone(app.qrcode)
        self.assertEqual(app.qrcode.version, 2)
        self.assertEqual(app.qrcode_copy_button.state, "normal")
        self.assertEqual(app.qrcode_canvas.cleared, 1)  # somente o desenho
        self.assertEqual(len(app.qrcode_canvas.items), 1)
        # Nenhum texto de versao abaixo do QR Code...
        self.assertEqual(app.qrcode_status_var.get(), "")
        # ...e o log de atividade recebe a confirmacao em verde.
        self.assertTrue(app.activity_log.lines[-1][0].endswith("QR Code solicitado\n"))
        self.assertEqual(app.activity_log.lines[-1][1], "activity_step_done")
        self.assertEqual(self.messages.calls, [])

    def test_generate_without_a_link_warns_and_keeps_the_state(self):
        app = self._make_app()
        app.generate_qrcode()
        self.assertIsNone(app.qrcode)
        self.assertEqual(app.qrcode_copy_button.configures, [])  # nunca habilitado
        self.assertEqual(self.messages.calls[0][0], "warning")
        self.assertTrue(
            app.activity_log.lines[-1][0].endswith("QR Code solicitado sem link\n")
        )
        self.assertEqual(app.activity_log.lines[-1][1], "warning")

    def test_content_above_the_limit_reports_an_error_keeps_the_last_code(self):
        app = self._make_app()
        app.qrcode_link_var.set("https://sig.local")
        app.generate_qrcode()
        drawn = app.qrcode_canvas.cleared

        app.qrcode_link_var.set("a" * 5000)
        app.generate_qrcode()
        self.assertEqual(app.qrcode.version, 2)  # mantem o ultimo codigo valido
        self.assertEqual(app.qrcode_canvas.cleared, drawn)
        self.assertEqual(self.messages.calls[-1][0], "error")

    def test_clear_resets_the_tab(self):
        app = self._make_app()
        app.qrcode_link_var.set("https://sig.local")
        app.generate_qrcode()
        app.qrcode_status_var.set("QR Code gerado.")
        app.clear_qrcode()

        self.assertIsNone(app.qrcode)
        self.assertIsNone(app.qrcode_photo)
        self.assertEqual(app.qrcode_link_var.get(), "")
        self.assertEqual(app.qrcode_copy_button.state, "disabled")
        self.assertEqual(app.qrcode_status_var.get(), "Cole um link e gere o QR Code.")

    def test_clear_keeps_everything_when_the_user_declines(self):
        app = self._make_app()
        app.qrcode_link_var.set("https://sig.local")
        app.generate_qrcode()
        self.messages.answer = False
        app.clear_qrcode()
        self.assertIsNotNone(app.qrcode)
        self.assertEqual(app.qrcode_link_var.get(), "https://sig.local")

    def test_paste_fills_the_link_box(self):
        app = self._make_app()
        self.clipboard.append("  https://sig.local  ")
        app.paste_qrcode_link()
        self.assertEqual(app.qrcode_link_var.get(), "https://sig.local")
        self.assertTrue(app.activity_log.lines[-1][0].endswith("Link colado\n"))
        self.assertEqual(app.activity_log.lines[-1][1], "activity_step_done")

    def test_paste_with_empty_clipboard_keeps_silence(self):
        app = self._make_app()
        app.paste_qrcode_link()
        self.assertEqual(app.qrcode_link_var.get(), "")
        self.assertEqual(app.activity_log.lines, [])

    def test_copy_logs_success_and_posts_the_image(self):
        app = self._make_app()
        app.qrcode_link_var.set("https://sig.local")
        app.generate_qrcode()
        app.activity_log.lines.clear()
        with patch("qr_encoder.copy_image_to_windows_clipboard") as copied:
            app.copy_qrcode_image()
        copied.assert_called_once()
        self.assertTrue(app.activity_log.lines[-1][0].endswith("QR Code copiado\n"))
        self.assertEqual(app.activity_log.lines[-1][1], "activity_step_done")

    def test_copy_without_a_code_warns(self):
        app = self._make_app()
        app.copy_qrcode_image()
        self.assertEqual(self.messages.calls[-1][0], "warning")
        self.assertTrue(
            app.activity_log.lines[-1][0].endswith("Gere o QR Code antes de copiar\n")
        )
        self.assertEqual(app.activity_log.lines[-1][1], "warning")

    def test_placeholder_is_drawn_on_an_empty_canvas(self):
        app = self._make_app()
        app._draw_qrcode_placeholder()
        self.assertEqual(len(app.qrcode_canvas.items), 1)
        self.assertIn("QR Code", app.qrcode_canvas.items[0][1]["text"])


if __name__ == "__main__":
    unittest.main()
