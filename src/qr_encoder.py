"""Gerador de QR Code autosuficiente para o SIG.

O modulo implementa a especificacao ISO/IEC 18004 no modo byte (8 bits),
que cobre links, textos em UTF-8 e qualquer conteudo binario. Ele depende
apenas da PIL, que ja faz parte do runtime do SIG, evitando a introducao de
uma biblioteca de terceiros no pacote PyInstaller.

Recursos:
    * Versoes 1 a 40, niveis de correcao L/M/Q/H.
    * Selecao automatica da menor versao capaz de armazenar o conteudo.
    * Avaliacao das 8 mascaras com a pontuacao de penalidade da norma.
    * Saida em PIL.Image e copia da imagem para a area de transferencia do
      Windows (CF_DIB + PNG), permitindo colar em Word, Paint, etc.
"""

from __future__ import annotations

import ctypes
import io
import os
import struct
import time
from typing import List, Sequence

from PIL import Image

MIN_VERSION = 1
MAX_VERSION = 40

# Bits de formato usados pela norma para cada nivel de correcao.
ECL_FORMAT_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}

# Codwords de correcao por bloco, indexados por nivel e versao (indice 0 = vazio).
_ECC_CODEWORDS_PER_BLOCK = {
    "L": [
        -1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28,
        30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30,
        30, 30, 30, 30, 30,
    ],
    "M": [
        -1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28,
        26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28,
        28, 28, 28, 28, 28,
    ],
    "Q": [
        -1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28,
        28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30,
        30, 30, 30, 30, 30,
    ],
    "H": [
        -1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28,
        28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30,
        30, 30, 30, 30, 30,
    ],
}

# Quantidade de blocos de correcao, indexados por nivel e versao.
_NUM_ERROR_CORRECTION_BLOCKS = {
    "L": [
        -1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9,
        10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25,
    ],
    "M": [
        -1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16,
        17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45,
        47, 49,
    ],
    "Q": [
        -1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20,
        23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62,
        65, 68,
    ],
    "H": [
        -1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25,
        25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70,
        74, 77, 81,
    ],
}

_PENALTY_N1 = 3
_PENALTY_N2 = 3
_PENALTY_N3 = 40
_PENALTY_N4 = 10

# Pillow 10 removeu as constantes diretas (Image.NEAREST); o fallback mantem o
# modulo compativel com as versoes antigas e novas da biblioteca.
_RESAMPLE_NEAREST = getattr(getattr(Image, "Resampling", Image), "NEAREST", 0)


class QrCapacityError(ValueError):
    """Conteudo maior do que o suportado pela maior versao do padrao."""


def _num_raw_data_modules(version: int) -> int:
    """Quantidade de modulos utilizaveis para dados, descontando funcoes."""
    result = (16 * version + 128) * version + 64
    if version >= 2:
        num_align = version // 7 + 2
        result -= (25 * num_align - 10) * num_align - 55
        if version >= 7:
            result -= 36
    return result


def _num_data_codewords(version: int, ecl: str) -> int:
    return (
        _num_raw_data_modules(version) // 8
        - _ECC_CODEWORDS_PER_BLOCK[ecl][version] * _NUM_ERROR_CORRECTION_BLOCKS[ecl][version]
    )


def _char_count_bits(version: int) -> int:
    """Tamanho do campo de contagem de caracteres no modo byte."""
    return 8 if version <= 9 else 16


def _alignment_pattern_positions(version: int) -> List[int]:
    if version == 1:
        return []
    num_align = version // 7 + 2
    step = 26 if version == 32 else (version * 4 + num_align * 2 + 1) // (num_align * 2 - 2) * 2
    size = version * 4 + 17
    result = [0] * num_align
    result[0] = 6
    position = size - 7
    for index in range(num_align - 1, 0, -1):
        result[index] = position
        position -= step
    return result


def _gf_multiply(x: int, y: int) -> int:
    """Multiplicacao no corpo finito GF(2^8) com polinomio primitivo 0x11D."""
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z & 0xFF


def _rs_compute_divisor(degree: int) -> List[int]:
    """Polinomio gerador de Reed-Solomon com o grau pedido."""
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_multiply(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_multiply(root, 0x02)
    return result


def _rs_compute_remainder(data: Sequence[int], divisor: Sequence[int]) -> List[int]:
    result = [0] * len(divisor)
    for value in data:
        factor = value ^ result.pop(0)
        result.append(0)
        for i in range(len(divisor)):
            result[i] ^= _gf_multiply(divisor[i], factor)
    return result


class _BitBuffer:
    __slots__ = ("bits",)

    def __init__(self) -> None:
        self.bits: List[int] = []

    def append(self, value: int, length: int) -> None:
        for i in reversed(range(length)):
            self.bits.append((value >> i) & 1)

    def __len__(self) -> int:
        return len(self.bits)


class QrCode:
    """Matriz de modulos de um QR Code ja mascarada e finalizada."""

    def __init__(self, version: int, ecl: str, data: bytes) -> None:
        if not MIN_VERSION <= version <= MAX_VERSION:
            raise ValueError(f"Versao de QR invalida: {version}")
        if ecl not in ECL_FORMAT_BITS:
            raise ValueError(f"Nivel de correcao invalido: {ecl}")

        self.version = version
        self.ecl = ecl
        self.size = version * 4 + 17

        codewords = self._build_codewords(version, ecl, data)
        self.modules = [[False] * self.size for _ in range(self.size)]
        self.is_function = [[False] * self.size for _ in range(self.size)]
        self._draw_function_patterns()
        all_codewords = self._add_ecc_and_interleave(version, ecl, codewords)
        self._draw_codewords(all_codewords)
        self.mask = self._choose_best_mask()
        self._apply_mask(self.mask)
        self._draw_format_bits(self.mask)

    # ------------------------------------------------------------------
    # Codificacao dos dados
    # ------------------------------------------------------------------
    @staticmethod
    def _build_codewords(version: int, ecl: str, data: bytes) -> List[int]:
        capacity_bits = _num_data_codewords(version, ecl) * 8
        buffer = _BitBuffer()
        buffer.append(0b0100, 4)  # modo byte
        buffer.append(len(data), _char_count_bits(version))
        for byte in data:
            buffer.append(byte, 8)

        buffer.append(0, min(4, capacity_bits - len(buffer)))
        buffer.append(0, (8 - len(buffer) % 8) % 8)

        pad_byte = 0xEC
        while len(buffer) < capacity_bits:
            buffer.append(pad_byte, 8)
            pad_byte ^= 0xEC ^ 0x11

        bits = buffer.bits
        return [
            int("".join(str(bit) for bit in bits[index:index + 8]), 2)
            for index in range(0, len(bits), 8)
        ]

    @staticmethod
    def _add_ecc_and_interleave(version: int, ecl: str, data: List[int]) -> List[int]:
        num_blocks = _NUM_ERROR_CORRECTION_BLOCKS[ecl][version]
        block_ecc_len = _ECC_CODEWORDS_PER_BLOCK[ecl][version]
        raw_codewords = _num_raw_data_modules(version) // 8
        num_short_blocks = num_blocks - raw_codewords % num_blocks
        short_block_len = raw_codewords // num_blocks

        blocks: List[List[int]] = []
        divisor = _rs_compute_divisor(block_ecc_len)
        offset = 0
        block_len = short_block_len + 1
        for index in range(num_blocks):
            data_len = short_block_len - block_ecc_len + (0 if index < num_short_blocks else 1)
            chunk = list(data[offset:offset + data_len])
            offset += data_len
            # Os blocos curtos recebem um byte de preenchimento para que todos
            # tenham o mesmo comprimento durante a intercalacao.
            block = chunk + [0] * (block_len - data_len - block_ecc_len)
            block += _rs_compute_remainder(chunk, divisor)
            blocks.append(block)

        # Intercala os codewords: todos os dados primeiro, depois a correcao.
        # O byte de preenchimento dos blocos curtos e ignorado.
        skip_index = short_block_len - block_ecc_len
        result: List[int] = []
        for i in range(block_len):
            for j in range(num_blocks):
                if i != skip_index or j >= num_short_blocks:
                    result.append(blocks[j][i])
        return result

    # ------------------------------------------------------------------
    # Desenho dos padroes de funcao
    # ------------------------------------------------------------------
    def _set_function_module(self, x: int, y: int, dark: bool) -> None:
        self.modules[y][x] = dark
        self.is_function[y][x] = True

    def _draw_function_patterns(self) -> None:
        size = self.size
        for i in range(size):
            self._set_function_module(6, i, i % 2 == 0)
            self._set_function_module(i, 6, i % 2 == 0)

        self._draw_finder_pattern(3, 3)
        self._draw_finder_pattern(size - 4, 3)
        self._draw_finder_pattern(3, size - 4)

        positions = _alignment_pattern_positions(self.version)
        last = len(positions) - 1
        for i, pos_x in enumerate(positions):
            for j, pos_y in enumerate(positions):
                is_corner = (
                    (i == 0 and j == 0)
                    or (i == 0 and j == last)
                    or (i == last and j == 0)
                )
                if not is_corner:
                    self._draw_alignment_pattern(pos_x, pos_y)

        self._draw_format_bits(0)  # bits temporarios, refeitos apos a mascara
        self._draw_version_bits()

    def _draw_finder_pattern(self, x: int, y: int) -> None:
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                distance = max(abs(dx), abs(dy))
                xx, yy = x + dx, y + dy
                if 0 <= xx < self.size and 0 <= yy < self.size:
                    self._set_function_module(xx, yy, distance != 2 and distance != 4)

    def _draw_alignment_pattern(self, x: int, y: int) -> None:
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                self._set_function_module(x + dx, y + dy, max(abs(dx), abs(dy)) != 1)

    def _draw_format_bits(self, mask: int) -> None:
        data = ECL_FORMAT_BITS[self.ecl] << 3 | mask
        remainder = data
        for _ in range(10):
            remainder = (remainder << 1) ^ ((remainder >> 9) * 0x537)
        bits = (data << 10 | remainder) ^ 0x5412

        for i in range(6):
            self._set_function_module(8, i, (bits >> i) & 1 != 0)
        self._set_function_module(8, 7, (bits >> 6) & 1 != 0)
        self._set_function_module(8, 8, (bits >> 7) & 1 != 0)
        self._set_function_module(7, 8, (bits >> 8) & 1 != 0)
        for i in range(9, 15):
            self._set_function_module(14 - i, 8, (bits >> i) & 1 != 0)

        size = self.size
        for i in range(8):
            self._set_function_module(size - 1 - i, 8, (bits >> i) & 1 != 0)
        for i in range(8, 15):
            self._set_function_module(8, size - 15 + i, (bits >> i) & 1 != 0)
        self._set_function_module(8, size - 8, True)  # modulo sempre escuro

    def _draw_version_bits(self) -> None:
        if self.version < 7:
            return
        remainder = self.version
        for _ in range(12):
            remainder = (remainder << 1) ^ ((remainder >> 11) * 0x1F25)
        bits = self.version << 12 | remainder
        size = self.size
        for i in range(18):
            bit = (bits >> i) & 1 != 0
            a = size - 11 + i % 3
            b = i // 3
            self._set_function_module(a, b, bit)
            self._set_function_module(b, a, bit)

    def _draw_codewords(self, data: Sequence[int]) -> None:
        size = self.size
        index = 0
        total_bits = len(data) * 8
        for right in range(size - 1, 0, -2):
            if right <= 6:
                right -= 1
            for vertical in range(size):
                for j in range(2):
                    x = right - j
                    upward = (right + 1) & 2 == 0
                    y = (size - 1 - vertical) if upward else vertical
                    if not self.is_function[y][x] and index < total_bits:
                        self.modules[y][x] = (data[index >> 3] >> (7 - (index & 7))) & 1 != 0
                        index += 1

    # ------------------------------------------------------------------
    # Mascaras
    # ------------------------------------------------------------------
    def _mask_bit(self, mask: int, x: int, y: int) -> bool:
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
        if mask == 7:
            return ((x + y) % 2 + x * y % 3) % 2 == 0
        raise ValueError(f"Mascara invalida: {mask}")

    def _apply_mask(self, mask: int) -> None:
        for y in range(self.size):
            row = self.modules[y]
            function_row = self.is_function[y]
            for x in range(self.size):
                if not function_row[x] and self._mask_bit(mask, x, y):
                    row[x] = not row[x]


    def _choose_best_mask(self) -> int:
        best_mask = 0
        best_penalty = None
        for mask in range(8):
            self._draw_format_bits(mask)
            self._apply_mask(mask)
            penalty = self._penalty_score()
            if best_penalty is None or penalty < best_penalty:
                best_penalty = penalty
                best_mask = mask
            self._apply_mask(mask)
        return best_mask

    # ------------------------------------------------------------------
    # Pontuacao de penalidade
    # ------------------------------------------------------------------
    @staticmethod
    def _finder_penalty_add_history(run_length: int, history: List[int]) -> None:
        if history[0] == 0:
            run_length += 1  # borda clara antes do primeiro trecho
        history.pop()
        history.insert(0, run_length)

    @staticmethod
    def _finder_penalty_count_patterns(history: Sequence[int]) -> int:
        n = history[1]
        core = (
            n > 0
            and history[2] == n
            and history[3] == n * 3
            and history[4] == n
            and history[5] == n
        )
        return (
            (1 if core and history[0] >= n * 4 and history[6] >= n else 0)
            + (1 if core and history[6] >= n * 4 and history[0] >= n else 0)
        )

    def _finder_penalty_terminate_and_count(
        self, current_run_color: bool, current_run_length: int, history: List[int]
    ) -> int:
        if current_run_color:
            self._finder_penalty_add_history(current_run_length, history)
            current_run_length = 0
        current_run_length += self.size  # borda clara depois do ultimo trecho
        self._finder_penalty_add_history(current_run_length, history)
        return self._finder_penalty_count_patterns(history)

    def _penalty_score(self) -> int:
        size = self.size
        modules = self.modules
        result = 0

        # Regra 1 e 3 nas linhas.
        for y in range(size):
            run_color = False
            run_length = 0
            history = [0] * 7
            for x in range(size):
                if modules[y][x] == run_color:
                    run_length += 1
                    if run_length == 5:
                        result += _PENALTY_N1
                    elif run_length > 5:
                        result += 1
                else:
                    self._finder_penalty_add_history(run_length, history)
                    if not run_color:
                        result += self._finder_penalty_count_patterns(history) * _PENALTY_N3
                    run_color = modules[y][x]
                    run_length = 1
            result += (
                self._finder_penalty_terminate_and_count(run_color, run_length, history)
                * _PENALTY_N3
            )

        # Regra 1 e 3 nas colunas.
        for x in range(size):
            run_color = False
            run_length = 0
            history = [0] * 7
            for y in range(size):
                if modules[y][x] == run_color:
                    run_length += 1
                    if run_length == 5:
                        result += _PENALTY_N1
                    elif run_length > 5:
                        result += 1
                else:
                    self._finder_penalty_add_history(run_length, history)
                    if not run_color:
                        result += self._finder_penalty_count_patterns(history) * _PENALTY_N3
                    run_color = modules[y][x]
                    run_length = 1
            result += (
                self._finder_penalty_terminate_and_count(run_color, run_length, history)
                * _PENALTY_N3
            )

        # Regra 2: blocos 2x2 da mesma cor.
        for y in range(size - 1):
            row = modules[y]
            next_row = modules[y + 1]
            for x in range(size - 1):
                if row[x] == row[x + 1] == next_row[x] == next_row[x + 1]:
                    result += _PENALTY_N2

        # Regra 4: equilibrio entre modulos claros e escuros.
        dark = sum(1 for row in modules for value in row if value)
        total = size * size
        ratio = (abs(dark * 20 - total * 10) + total - 1) // total - 1
        result += ratio * _PENALTY_N4
        return result

    # ------------------------------------------------------------------
    # Saida
    # ------------------------------------------------------------------
    def get_matrix(self) -> List[List[bool]]:
        """Copia da matriz de modulos (True = escuro)."""
        return [list(row) for row in self.modules]

    def to_image(
        self,
        scale: int = 8,
        border: int = 4,
        dark: tuple = (0, 0, 0),
        light: tuple = (255, 255, 255),
    ) -> Image.Image:
        if scale < 1:
            raise ValueError("A escala precisa ser maior ou igual a 1.")
        if border < 0:
            raise ValueError("A margem nao pode ser negativa.")
        matrix = Image.new("L", (self.size, self.size))
        matrix.putdata([0 if value else 255 for row in self.modules for value in row])
        # O redimensionamento preserva os modulos quadrados sem suavizar bordas.
        scaled = matrix.resize(
            (self.size * scale, self.size * scale),
            _RESAMPLE_NEAREST,
        )
        total = (self.size + border * 2) * scale
        canvas = Image.new("L", (total, total), 255)
        canvas.paste(scaled, (border * scale, border * scale))
        mask = canvas.point(lambda value: 255 if value == 0 else 0)
        image = Image.new("RGB", (total, total), light)
        image.paste(dark, (0, 0), mask)
        return image

    @staticmethod
    def encode_text(text: str, ecl: str = "M") -> "QrCode":
        return QrCode.encode_bytes((text or "").encode("utf-8"), ecl)

    @staticmethod
    def encode_bytes(data: bytes, ecl: str = "M") -> "QrCode":
        ecl = (ecl or "M").upper()
        if ecl not in ECL_FORMAT_BITS:
            raise ValueError(f"Nivel de correcao invalido: {ecl}")
        payload = bytes(data or b"")
        for version in range(MIN_VERSION, MAX_VERSION + 1):
            capacity_bits = _num_data_codewords(version, ecl) * 8
            needed_bits = 4 + _char_count_bits(version) + len(payload) * 8
            if needed_bits <= capacity_bits:
                return QrCode(version, ecl, payload)
        capacity_bits = _num_data_codewords(MAX_VERSION, ecl) * 8
        max_bytes = (capacity_bits - 4 - _char_count_bits(MAX_VERSION)) // 8
        raise QrCapacityError(
            "Conteúdo longo demais para caber em um QR Code (limite de "
            f"{max_bytes} bytes no nível {ecl})."
        )


# ----------------------------------------------------------------------
# Area de transferencia do Windows
# ----------------------------------------------------------------------
_CF_DIB = 8
_GMEM_MOVEABLE = 0x0002


def _bitmap_to_dib(image: Image.Image) -> bytes:
    """Converte a imagem em um DIB de 24 bits (formato CF_DIB)."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    row_size = ((width * 24 + 31) // 32) * 4
    pixel_size = row_size * height
    header = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,  # altura positiva = linhas de baixo para cima
        1,
        24,
        0,
        pixel_size,
        0,
        0,
        0,
        0,
    )
    raw = rgb.tobytes()
    rows = []
    for y in range(height - 1, -1, -1):
        start = y * width * 3
        source = raw[start:start + width * 3]
        line = bytearray(row_size)
        line[0:width * 3:3] = source[2::3]  # azul
        line[1:width * 3:3] = source[1::3]  # verde
        line[2:width * 3:3] = source[0::3]  # vermelho
        rows.append(bytes(line))
    return header + b"".join(rows)


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def copy_image_to_windows_clipboard(image: Image.Image) -> None:
    """Copia a imagem para a area de transferencia (CF_DIB + PNG)."""
    if os.name != "nt":
        raise RuntimeError("A copia de imagem esta disponivel somente no Windows.")

    dib = _bitmap_to_dib(image)
    png = image_to_png_bytes(image)

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.CloseClipboard.restype = ctypes.c_bool
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.RegisterClipboardFormatW.argtypes = [ctypes.c_wchar_p]
    user32.RegisterClipboardFormatW.restype = ctypes.c_uint
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p

    for _attempt in range(40):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.1)
    else:
        raise ctypes.WinError(ctypes.get_last_error())

    def put(format_id: int, data: bytes) -> None:
        memory = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
        if not memory:
            raise ctypes.WinError(ctypes.get_last_error())
        target = kernel32.GlobalLock(memory)
        if not target:
            kernel32.GlobalFree(memory)
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.memmove(target, data, len(data))
        kernel32.GlobalUnlock(memory)
        if not user32.SetClipboardData(format_id, memory):
            kernel32.GlobalFree(memory)
            raise ctypes.WinError(ctypes.get_last_error())

    try:
        if not user32.EmptyClipboard():
            raise ctypes.WinError(ctypes.get_last_error())
        put(_CF_DIB, dib)
        png_format = user32.RegisterClipboardFormatW("PNG")
        if png_format:
            put(png_format, png)
    finally:
        user32.CloseClipboard()
