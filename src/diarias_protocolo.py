"""Leitura dos PDFs usados na aba Diárias.

Dono único das regras de extração: a UI (`sig_app.py`) chama as funções deste
módulo e preenche os campos; o parsing mora aqui para ser testável sem Tkinter.

Formato do PDF (lista de remessa da Polícia Civil):
- o protocolo principal (mapa) é o primeiro número `NNNNNN/AAAA` depois do
  cabeçalho `PROTOCOLO ... DESPACHO`;
- o protocolo anexo (requerimento) vem em `Rel. (NNNNNN/AAAA)`.

Formato do PDF do talão (SISFROTA):
- a abertura (saída) vem em `ABERTURA DD/MM/AAAA HH:MM`;
- o fechamento (volta) vem em `FECHAMENTO DD/MM/AAAA HH:MM`.

Formato do PDF do holerite:
- o total vem abaixo do rótulo `Total Vencimentos`;
- o mês vem do valor sob o rótulo `Data Pagamento`.
"""

from __future__ import annotations

from datetime import datetime
import re
from pathlib import Path

import pypdfium2 as pdfium

_MAPA_RE = re.compile(r"PROTOCOLO\s+DESPACHO.*?(\d+/\d{4})", re.S)
_REQUERIMENTO_RE = re.compile(r"Rel\.\s*\((\d+/\d{4})\)")
_DATA_RECEBIDO_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}\s+Recebido Por")
_DATA_ENCERRADA_RE = re.compile(r"ENCERRADA EM:\s*(\d{2}/\d{2}/\d{4})")
_TALAO_ABERTURA_RE = re.compile(r"ABERTURA\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})")
_TALAO_FECHAMENTO_RE = re.compile(r"FECHAMENTO\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})")
_HOLERITE_TOTAL_LABEL_RE = re.compile(r"\bTotal\s+(Vencimentos)\b", re.I)
_HOLERITE_PAGAMENTO_LABEL_RE = re.compile(r"\bData\s+Pagamento\b", re.I)
_HOLERITE_AMOUNT_RE = re.compile(r"(?<!\d)(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?!\d)")
_DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
_MESES_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


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


def _label_bbox(text_page, text: str, pattern: re.Pattern, group: int = 0):
    """Retorna a caixa do texto de um rótulo na página PDF, se encontrado."""
    match = pattern.search(text or "")
    if not match:
        return None

    start, end = match.span(group)
    boxes = [text_page.get_charbox(index) for index in range(start, end)]
    if not boxes:
        return None
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _text_below_label(text_page, bbox, *, vertical_gap: float) -> str:
    """Extrai a célula alinhada abaixo do rótulo no layout do holerite."""
    left, bottom, right, _top = bbox
    return text_page.get_text_bounded(
        left - 5,
        bottom - vertical_gap,
        right + 5,
        bottom - 2,
    )


def _extract_holerite_page(text_page, text: str) -> tuple[str, str]:
    """Extrai o vencimento e a data de pagamento da primeira página aplicável."""
    text_page.count_chars()
    total_bbox = _label_bbox(text_page, text, _HOLERITE_TOTAL_LABEL_RE, group=1)
    payment_bbox = _label_bbox(text_page, text, _HOLERITE_PAGAMENTO_LABEL_RE)

    total = ""
    if total_bbox:
        value_text = _text_below_label(text_page, total_bbox, vertical_gap=24)
        amount_match = _HOLERITE_AMOUNT_RE.search(value_text)
        total = amount_match.group(0) if amount_match else ""

    month = ""
    if payment_bbox:
        date_text = _text_below_label(text_page, payment_bbox, vertical_gap=14)
        date_match = _DATE_RE.search(date_text)
        if date_match:
            try:
                pagamento = datetime.strptime(date_match.group(1), "%d/%m/%Y")
            except ValueError:
                pagamento = None
            if pagamento:
                month = _MESES_PT[pagamento.month - 1]

    return total, month


def extract_holerite_pdf(path: str | Path) -> tuple[str, str]:
    """Lê o PDF e devolve `(total_vencimentos, mes_do_pagamento)`.

    Os campos ficam em colunas distintas do documento. A extração usa a posição
    de cada rótulo e lê a célula logo abaixo dele, evitando confundir os valores
    de vencimentos, descontos e líquido a receber.
    """
    documento = pdfium.PdfDocument(str(path))
    total = ""
    month = ""
    try:
        for pagina in documento:
            text_page = pagina.get_textpage()
            try:
                text = text_page.get_text_range()
                page_total, page_month = _extract_holerite_page(text_page, text)
            finally:
                text_page.close()
            total = total or page_total
            month = month or page_month
            if total and month:
                break
    finally:
        documento.close()
    return total, month
