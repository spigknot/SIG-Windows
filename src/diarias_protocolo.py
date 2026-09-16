"""Protocolos da aba Diárias (mapa x requerimento) a partir do PDF de remessa.

Dono único da regra de extração: a UI (`sig_app.py`) só chama
`extract_protocolos_pdf` e preenche os campos; o parsing mora aqui para
ser testável sem Tkinter.

Formato do PDF (lista de remessa da Polícia Civil):
- o protocolo principal (mapa) é o primeiro número `NNNNNN/AAAA` depois do
  cabeçalho `PROTOCOLO ... DESPACHO`;
- o protocolo anexo (requerimento) vem em `Rel. (NNNNNN/AAAA)`.

Formato do PDF do talão (SISFROTA):
- a abertura (saída) vem em `ABERTURA DD/MM/AAAA HH:MM`;
- o fechamento (volta) vem em `FECHAMENTO DD/MM/AAAA HH:MM`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pypdfium2 as pdfium

_MAPA_RE = re.compile(r"PROTOCOLO\s+DESPACHO.*?(\d+/\d{4})", re.S)
_REQUERIMENTO_RE = re.compile(r"Rel\.\s*\((\d+/\d{4})\)")
_DATA_RECEBIDO_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}\s+Recebido Por")
_DATA_ENCERRADA_RE = re.compile(r"ENCERRADA EM:\s*(\d{2}/\d{2}/\d{4})")
_TALAO_ABERTURA_RE = re.compile(r"ABERTURA\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})")
_TALAO_FECHAMENTO_RE = re.compile(r"FECHAMENTO\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})")


def extract_protocol_numbers(text: str) -> tuple[str, str]:
    """Devolve `(mapa, requerimento)`; `""` onde o padrão não aparece."""
    mapa_match = _MAPA_RE.search(text or "")
    req_match = _REQUERIMENTO_RE.search(text or "")
    mapa = mapa_match.group(1) if mapa_match else ""
    requerimento = req_match.group(1) if req_match else ""
    return mapa, requerimento


def read_protocolo_pdf_text(path: str | Path) -> str:
    """Extrai o texto de todas as páginas do PDF (via pypdfium2)."""
    documento = pdfium.PdfDocument(str(path))
    try:
        paginas = []
        for pagina in documento:
            caixa_texto = pagina.get_textpage()
            try:
                paginas.append(caixa_texto.get_text_range())
            finally:
                caixa_texto.close()
        return "\n".join(paginas)
    finally:
        documento.close()


def extract_protocolos_pdf(path: str | Path) -> tuple[str, str]:
    """Lê o PDF do protocolo e devolve `(mapa, requerimento)`."""
    return extract_protocol_numbers(read_protocolo_pdf_text(path))


def extract_data_protocolo(text: str) -> str:
    """Data do protocolo: carimbo `Recebido Por`, com fallback em `ENCERRADA EM`."""
    recebido = _DATA_RECEBIDO_RE.search(text or "")
    if recebido:
        return recebido.group(1)
    encerrada = _DATA_ENCERRADA_RE.search(text or "")
    return encerrada.group(1) if encerrada else ""


def extract_protocolo_completo(path: str | Path) -> tuple[str, str, str]:
    """Lê o PDF do protocolo e devolve `(mapa, requerimento, data)`."""
    texto = read_protocolo_pdf_text(path)
    mapa, requerimento = extract_protocol_numbers(texto)
    return mapa, requerimento, extract_data_protocolo(texto)


def extract_talao_abertura_fechamento(text: str) -> tuple[str, str, str, str]:
    """Devolve `(data_abertura, hora_abertura, data_fechamento, hora_fechamento)`.

    A abertura é a saída e o fechamento é a volta; `""` onde o padrão
    não aparece.
    """
    abertura = _TALAO_ABERTURA_RE.search(text or "")
    fechamento = _TALAO_FECHAMENTO_RE.search(text or "")
    data_abertura, hora_abertura = abertura.groups() if abertura else ("", "")
    data_fechamento, hora_fechamento = (
        fechamento.groups() if fechamento else ("", "")
    )
    return data_abertura, hora_abertura, data_fechamento, hora_fechamento


def extract_talao_pdf(path: str | Path) -> tuple[str, str, str, str]:
    """Lê o PDF do talão e devolve os 4 campos (data/hora, abertura/fechamento)."""
    return extract_talao_abertura_fechamento(read_protocolo_pdf_text(path))
