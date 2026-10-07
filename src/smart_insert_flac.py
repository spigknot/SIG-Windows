"""Rebaseia headers FLAC sem decodificar ou recodificar os subframes.

RFC 9639, seções 8.2, 9.1 e 9.3. A montagem usa blocos variáveis e números
de amostras contínuos. CRC-16 é corrigido pela diferença entre os headers;
o corpo comprimido permanece intacto.
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=4)
def _crc_table(bits: int, polynomial: int) -> tuple[int, ...]:
    mask = (1 << bits) - 1
    table = []
    for byte in range(256):
        value = byte << (bits - 8)
        for _ in range(8):
            value = ((value << 1) ^ (polynomial if value & (1 << (bits - 1)) else 0)) & mask
        table.append(value)
    return tuple(table)


def crc(data: bytes, bits: int, polynomial: int) -> int:
    value = 0
    mask = (1 << bits) - 1
    table = _crc_table(bits, polynomial)
    for byte in data:
        value = ((value << 8) ^ table[(value >> (bits - 8)) ^ byte]) & mask
    return value


def _apply(matrix, value):
    result, bit = 0, 0
    while value:
        if value & 1:
            result ^= matrix[bit]
        value >>= 1
        bit += 1
    return result


def _zero_byte(value):
    for _ in range(8):
        value = ((value << 1) ^ (0x8005 if value & 0x8000 else 0)) & 0xffff
    return value


_SHIFTS = [tuple(_zero_byte(1 << i) for i in range(16))]
for _ in range(24):
    _SHIFTS.append(tuple(_apply(_SHIFTS[-1], v) for v in _SHIFTS[-1]))

# Transformações por byte: mesmo avanço GF(2), com duas consultas em vez
# de percorrer os bits de cada CRC em todos os frames copiados.
_BYTE_SHIFTS = tuple((tuple(_apply(matrix, v) for v in range(256)),
                      tuple(_apply(matrix, v << 8) for v in range(256))) for matrix in _SHIFTS)


def shift_crc(value: int, length: int) -> int:
    if length < 0 or length >= 1 << len(_SHIFTS):
        raise ValueError("Tamanho de frame FLAC inválido.")
    i = 0
    while length:
        if length & 1:
            low, high = _BYTE_SHIFTS[i]
            value = low[value & 255] ^ high[value >> 8]
        length >>= 1
        i += 1
    return value


def encode_number(value: int) -> bytes:
    if value < 0 or value >= 1 << 36:
        raise ValueError("Número de amostra FLAC fora do limite.")
    if value < 128:
        return bytes([value])
    n = next(n for n, limit in enumerate((11, 16, 21, 26, 31, 36), 2) if value < 1 << limit)
    suffix = []
    for _ in range(n - 1):
        suffix.append(0x80 | (value & 63))
        value >>= 6
    return bytes([((0xff << (8 - n)) & 0xff) | value, *reversed(suffix)])


def frame_header(frame: bytes) -> tuple[int, int, int]:
    if len(frame) < 8 or frame[0] != 0xff or frame[1] & 0xfe != 0xf8:
        raise ValueError("Sincronização FLAC inválida.")
    first = frame[4]
    if first == 255:
        raise ValueError("Número de frame FLAC inválido.")
    n = 1 if first < 128 else next((i for i in range(2, 8) if first & (0xff << (8 - i) & 0xff) == (0xff << (8 - i) & 0xff)
                                                 and (i == 7 or not first & (1 << (7 - i)))), 0)
    if not n or len(frame) < 4 + n + 3:
        raise ValueError("Número de frame FLAC inválido.")
    if any(v & 0xc0 != 0x80 for v in frame[5:4+n]):
        raise ValueError("Número de frame FLAC inválido.")
    extra = 4 + n
    block = frame[2] >> 4
    if block == 1:
        samples = 192
    elif 2 <= block <= 5:
        samples = 576 << (block - 2)
    elif block == 6:
        samples = frame[extra] + 1
        extra += 1
    elif block == 7:
        samples = int.from_bytes(frame[extra:extra+2], "big") + 1
        extra += 2
    elif block >= 8:
        samples = 256 << (block - 8)
    else:
        raise ValueError("Tamanho de bloco FLAC reservado.")
    sample_rate = frame[2] & 15
    extra += 1 if sample_rate == 12 else 2 if sample_rate in {13, 14} else 0
    if sample_rate == 15 or len(frame) < extra + 3 or crc(frame[:extra+1], 8, 7):
        raise ValueError("Header ou CRC-8 FLAC inválido.")
    return 4 + n, extra + 1, samples


def rebase_frame(frame: bytes, sample: int) -> tuple[bytes, int]:
    number_end, header_end, count = frame_header(frame)
    prefix = bytearray(frame[:4])
    prefix[1] |= 1
    prefix += encode_number(sample) + frame[number_end:header_end-1]
    header = bytes(prefix) + bytes([crc(prefix, 8, 7)])
    delta = crc(frame[:header_end], 16, 0x8005) ^ crc(header, 16, 0x8005)
    checksum = int.from_bytes(frame[-2:], "big") ^ shift_crc(delta, len(frame) - header_end - 2)
    return header + frame[header_end:-2] + checksum.to_bytes(2, "big"), count


def metadata(path: Path) -> list[tuple[int, bytes]]:
    blocks = []
    with path.open("rb") as source:
        if source.read(4) != b"fLaC":
            raise ValueError("O arquivo não é FLAC nativo.")
        while True:
            header = source.read(4)
            if len(header) != 4:
                raise ValueError("Metadados FLAC incompletos.")
            payload = source.read(int.from_bytes(header[1:], "big"))
            if len(payload) != int.from_bytes(header[1:], "big"):
                raise ValueError("Metadados FLAC incompletos.")
            blocks.append((header[0] & 127, payload))
            if header[0] & 128:
                break
    if not blocks or blocks[0][0] != 0 or len(blocks[0][1]) != 34:
        raise ValueError("STREAMINFO FLAC inválido.")
    return blocks


def assemble(parts: list[tuple[Path, list[dict]]], output: Path, main: Path, total: int, cancelled) -> None:
    if not 0 < total < 1 << 36:
        raise ValueError("Contagem de amostras FLAC fora do limite.")
    blocks = metadata(main)
    stream = bytearray(blocks[0][1])
    signature = int.from_bytes(stream[10:18], "big") >> 36
    stream[10:18] = ((signature << 36) | total).to_bytes(8, "big")
    stream[18:34] = bytes(16)  # MD5 desconhecido; não reutilizar o checksum da fonte.
    retained = [(0, bytes(stream)), *[(kind, data) for kind, data in blocks[1:] if kind in {4, 6}]]
    sample, sizes, counts = 0, [], []
    with output.open("wb") as destination:
        destination.write(b"fLaC")
        for i, (kind, data) in enumerate(retained):
            destination.write(bytes([kind | (128 if i == len(retained)-1 else 0)]) + len(data).to_bytes(3, "big") + data)
        for path, packets in parts:
            part_info = metadata(path)[0][1]
            if int.from_bytes(part_info[10:18], "big") >> 36 != signature:
                raise ValueError("As peças FLAC possuem taxas, canais ou profundidades diferentes.")
            with path.open("rb") as source:
                for packet in packets:
                    cancelled()
                    source.seek(int(packet["pos"]))
                    frame = source.read(int(packet["size"]))
                    if len(frame) != int(packet["size"]):
                        raise ValueError("Frame FLAC incompleto.")
                    frame, count = rebase_frame(frame, sample)
                    destination.write(frame)
                    sample += count
                    counts.append(count)
                    sizes.append(len(frame))
        if sample != total or any(n < 16 for n in counts[:-1]):
            raise ValueError("A montagem FLAC não preservou os blocos/amostras esperados.")
        stream[0:2] = max(16, min(counts)).to_bytes(2, "big")
        stream[2:4] = max(16, max(counts)).to_bytes(2, "big")
        stream[4:7] = min(sizes).to_bytes(3, "big")
        stream[7:10] = max(sizes).to_bytes(3, "big")
        destination.seek(8)
        destination.write(stream)
