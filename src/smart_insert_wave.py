"""Monta WAV/RF64 por cópia de bytes PCM; o principal não passa por encoder."""
from __future__ import annotations
import struct
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class WaveData:
    fmt: bytes
    offset: int
    size: int
    align: int
    floating: bool
    signature: tuple
    metadata: bytes

def inspect(path: Path) -> WaveData:
    fmt, data, info, data64 = None, None, b"", None
    size = path.stat().st_size
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12 or header[:4] not in {b"RIFF", b"RF64"} or header[8:] != b"WAVE":
            raise ValueError("WAV não possui estrutura RIFF/RF64 suportada.")
        while handle.tell() + 8 <= size:
            kind, length = struct.unpack("<4sI", handle.read(8))
            if length == 0xffffffff:
                if kind != b"data" or data64 is None:
                    raise ValueError("Tamanho RF64 não identificado.")
                length = data64
            position = handle.tell()
            if position + length > size:
                raise ValueError("WAV contém chunk truncado.")
            if kind == b"ds64":
                payload = handle.read(min(length, 28))
                if len(payload) < 28:
                    raise ValueError("ds64 incompleto.")
                data64 = struct.unpack("<QQQI", payload)[1]
            elif kind == b"fmt ":
                if length > 65536:
                    raise ValueError("Formato WAV inválido.")
                fmt = handle.read(length)
            elif kind == b"data":
                if data is not None:
                    raise ValueError("WAV com múltiplos chunks de áudio exige compatibilização.")
                data = position, length
            elif kind == b"LIST" and length <= 1 << 20:
                payload = handle.read(length)
                if payload[:4] == b"INFO":
                    info += chunk(kind, payload)
            handle.seek(position + length + (length & 1))
    if fmt is None or len(fmt) < 16 or data is None:
        raise ValueError("WAV sem formato ou dados.")
    tag, channels, rate, byte_rate, align, bits = struct.unpack("<HHIIHH", fmt[:16])
    valid, mask = bits, 0
    if tag == 0xfffe:
        if len(fmt) < 40 or fmt[26:40] != b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71":
            raise ValueError("Subformato WAVEFORMATEXTENSIBLE não suportado.")
        valid, mask = struct.unpack("<HI", fmt[18:24])
        tag = int.from_bytes(fmt[24:26], "little")
    if (tag not in {1, 3} or not channels or not rate or not 1 <= bits <= 64 or not align or
        (tag == 3 and bits not in {32, 64}) or align != channels * ((bits + 7) // 8) or
        byte_rate != rate * align or data[1] % align):
        raise ValueError("Formato ou alinhamento PCM inválido.")
    if channels <= 2:
        mask = 0  # A ordem padrão mono/estéreo independe do uso do GUID.
    return WaveData(fmt, *data, align, tag == 3, (tag, channels, rate, align, bits, valid, mask), info)

def chunk(kind: bytes, payload: bytes) -> bytes:
    return kind + len(payload).to_bytes(4, "little") + payload + bytes(len(payload) & 1)

def assemble(main: Path, inserted: Path, output: Path, insertion: int, total: int, cancelled) -> None:
    first, middle = inspect(main), inspect(inserted)
    if first.signature != middle.signature:
        raise ValueError("Os trechos WAV possuem formatos PCM diferentes.")
    if not 0 <= insertion * first.align <= first.size or total * first.align != first.size + middle.size:
        raise ValueError("A contagem de amostras WAV mudou.")
    data_size = first.size + middle.size
    extra = chunk(b"fmt ", first.fmt) + first.metadata
    if first.floating:
        extra += chunk(b"fact", min(total, 0xffffffff).to_bytes(4, "little"))
    riff_size = 4 + len(extra) + 8 + data_size + (data_size & 1)
    rf64 = riff_size > 0xffffffff
    with output.open("wb") as destination:
        destination.write((b"RF64" if rf64 else b"RIFF") + (0xffffffff if rf64 else riff_size).to_bytes(4, "little") + b"WAVE")
        if rf64:
            destination.write(chunk(b"ds64", struct.pack("<QQQI", riff_size + 36, data_size, total, 0)))
        destination.write(extra)
        destination.write(b"data" + (0xffffffff if rf64 else data_size).to_bytes(4, "little"))
        for path, start, length in ((main,first.offset,insertion*first.align),
                                    (inserted,middle.offset,middle.size),
                                    (main,first.offset+insertion*first.align,first.size-insertion*first.align)):
            with path.open("rb") as source:
                source.seek(start)
                while length:
                    cancelled()
                    block = source.read(min(1 << 20, length))
                    if not block:
                        raise ValueError("Trecho PCM incompleto.")
                    destination.write(block)
                    length -= len(block)
        if data_size & 1:
            destination.write(b"\0")
