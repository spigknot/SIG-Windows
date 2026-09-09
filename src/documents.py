"""Geracao de documentos: DOCX a partir dos modelos Word, PDF (via Word) e previa.

Modelos em modelos/ (ao lado do executavel); templates sao baixados se faltarem.
Fluxo: generate_docx_from_template -> export_docx_to_pdf_with_word -> render_pdf_preview.
Sem Tkinter (a UI chama estas funcoes)."""

import hashlib
import html
import os
import pypdfium2 as pdfium
import re
import subprocess
import time
import urllib.request
import zipfile
from PIL import Image, ImageChops, ImageDraw, ImageOps
from app_env import app_base_dir
from pathlib import Path


DOCUMENT_TEMPLATE_NAMES = {
    "declarations": "modelo_declaracoes.docx",
    "deposition": "modelo_depoimento.docx",
}


def build_cf_html(html_text: str | bytes) -> bytes:
    """Build a Windows CF_HTML payload using UTF-8 byte offsets."""
    if isinstance(html_text, bytes):
        source_bytes = html_text.rstrip(b"\x00")
        charset_match = re.search(
            br"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)",
            source_bytes[:4096],
            flags=re.IGNORECASE,
        )
        source_encoding = (
            charset_match.group(1).decode("ascii", errors="replace")
            if charset_match
            else "utf-8"
        )
        try:
            raw_html = source_bytes.decode(source_encoding)
        except (LookupError, UnicodeDecodeError):
            raw_html = source_bytes.decode("utf-8", errors="replace")
    else:
        raw_html = html_text or ""
    raw_html = raw_html.replace("\x00", "").lstrip("\ufeff")
    html_start = raw_html.lower().find("<html")
    if html_start >= 0:
        raw_html = raw_html[html_start:]
    elif not raw_html.strip():
        raise RuntimeError("O Word não forneceu o conteúdo no formato HTML.")
    else:
        raw_html = f"<html><body>{raw_html}</body></html>"
    raw_html = re.sub(
        r"(charset\s*=\s*[\"']?)[A-Za-z0-9._-]+",
        r"\1utf-8",
        raw_html,
        count=1,
        flags=re.IGNORECASE,
    )

    start_marker = "<!--StartFragment-->"
    end_marker = "<!--EndFragment-->"
    if start_marker not in raw_html:
        body_match = re.search(r"<body\b[^>]*>", raw_html, flags=re.IGNORECASE)
        marker_at = body_match.end() if body_match else 0
        raw_html = raw_html[:marker_at] + start_marker + raw_html[marker_at:]
    if end_marker not in raw_html:
        body_end = raw_html.lower().rfind("</body>")
        marker_at = body_end if body_end >= 0 else len(raw_html)
        raw_html = raw_html[:marker_at] + end_marker + raw_html[marker_at:]

    html_bytes = raw_html.encode("utf-8")
    start_marker_bytes = start_marker.encode("ascii")
    end_marker_bytes = end_marker.encode("ascii")
    fragment_start_in_html = html_bytes.index(start_marker_bytes) + len(start_marker_bytes)
    fragment_end_in_html = html_bytes.index(end_marker_bytes, fragment_start_in_html)

    header_template = (
        "Version:1.0\r\n"
        "StartHTML:{start_html:010d}\r\n"
        "EndHTML:{end_html:010d}\r\n"
        "StartFragment:{start_fragment:010d}\r\n"
        "EndFragment:{end_fragment:010d}\r\n"
    )
    placeholder_header = header_template.format(
        start_html=0,
        end_html=0,
        start_fragment=0,
        end_fragment=0,
    ).encode("ascii")
    start_html = len(placeholder_header)
    end_html = start_html + len(html_bytes)
    header = header_template.format(
        start_html=start_html,
        end_html=end_html,
        start_fragment=start_html + fragment_start_in_html,
        end_fragment=start_html + fragment_end_in_html,
    ).encode("ascii")
    return header + html_bytes


def set_windows_document_clipboard(
    rtf: bytes,
    html_text: str | bytes,
    plain_text: str,
) -> None:
    if os.name != "nt":
        raise RuntimeError("A cópia formatada está disponível somente no Windows.")
    if not rtf:
        raise RuntimeError("O Word não forneceu o conteúdo no formato RTF.")

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
        memory = kernel32.GlobalAlloc(0x0002, len(data))
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
        rtf_format = user32.RegisterClipboardFormatW("Rich Text Format")
        html_format = user32.RegisterClipboardFormatW("HTML Format")
        put(rtf_format, rtf.rstrip(b"\0") + b"\0")
        put(html_format, build_cf_html(html_text) + b"\0")
        put(13, plain_text.encode("utf-16-le") + b"\0\0")
    finally:
        user32.CloseClipboard()


def export_docx_to_pdf_with_word(document_path: Path, output_path: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("A exportação fiel para PDF está disponível somente no Windows.")
    document_path = Path(document_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    script = r"""
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
$doNotSaveChanges = 0
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($env:SIG_PDF_SOURCE, $false, $true)
    $document.ExportAsFixedFormat($env:SIG_PDF_OUTPUT, 17)
    $document.Close([ref]$doNotSaveChanges)
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    $document = $null
    $word.Quit([ref]$doNotSaveChanges)
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
    $word = $null
} finally {
    if ($null -ne $document) {
        try { $document.Close([ref]$doNotSaveChanges) } catch {}
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) } catch {}
    }
    if ($null -ne $word) {
        try { $word.Quit([ref]$doNotSaveChanges) } catch {}
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) } catch {}
    }
}
"""
    env = os.environ.copy()
    env.update(
        {
            "SIG_PDF_SOURCE": str(document_path),
            "SIG_PDF_OUTPUT": str(output_path),
        }
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Sta", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "falha desconhecida").strip()
        raise RuntimeError(detail)
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError("O Word não gerou o arquivo PDF.")


def _crop_preview_page_to_content(
    page: Image.Image,
    *,
    horizontal_padding: int = 4,
    vertical_padding: int = 14,
) -> Image.Image:
    """Remove apenas o espaço em branco VERTICAL, mantendo a página inteira.

    A largura completa da página é preservada (nada de crop horizontal): a
    prévia precisa mostrar o documento COM as bordas — margens esquerda E
    direita. O crop vertical elimina o vazio acima/abaixo do conteúdo.
    """
    white = Image.new("RGB", page.size, (255, 255, 255))
    difference = ImageChops.difference(page, white).convert("L")
    # Ignore PDF rasterization noise in the white page background, but retain
    # antialiased text and thin document lines.
    mask = difference.point(lambda value: 255 if value > 8 else 0)
    bounds = mask.getbbox()
    mask.close()
    difference.close()
    white.close()
    if not bounds:
        cropped = page
    else:
        # Mantém a largura TOTAL da página (x=0 até page.width); usa o bbox
        # apenas para cortar o vazio vertical.
        _left, top, _right, bottom = bounds
        cropped = page.crop((0, top, page.width, bottom))
    if cropped is not page:
        page.close()
    # Keep roughly one blank text line above and below each page.
    padded = ImageOps.expand(
        cropped,
        border=(max(0, horizontal_padding), max(0, vertical_padding)),
        fill="#ffffff",
    )
    if padded is not cropped:
        cropped.close()
    return padded


def _window_physical_dpi(root) -> int:
    """DPI físico (painel) do monitor que contém a janela principal.

    O Windows virtualiza o DPI em 96 para processos não-DPI-aware, mas o
    painel real do monitor tem outro valor (ex.: 102 PPI em 21,5" Full HD).
    Para o zoom de 100% da prévia mostrar o documento no tamanho físico de
    impressão, a renderização precisa usar o DPI real do painel — medido
    diretamente via GetDpiForMonitor(MDT_RAW_DPI), que não é virtualizado.
    """
    if os.name != "nt":
        return 96
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        shcore = ctypes.windll.shcore
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        dpi_x = wintypes.UINT()
        dpi_y = wintypes.UINT()
        # MDT_RAW_DPI = 2: valor físico real do painel, ignorando a
        # virtualização de DPI do sistema.
        if shcore.GetDpiForMonitor(monitor, 2, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
            if dpi_x.value:
                return int(dpi_x.value)
    except Exception:
        pass
    return 96


def render_pdf_preview(
    pdf_path: Path,
    output_path: Path,
    zoom_percent: int,
    dpi: int = 96,
) -> tuple[int, list[tuple[int, int]]]:
    """Render pages and return their vertical ranges in the preview image."""
    zoom = max(25, min(200, int(zoom_percent)))
    document = pdfium.PdfDocument(str(Path(pdf_path).resolve()))
    pages: list[Image.Image] = []
    try:
        # Com o DPI físico do painel, 100% corresponde ao tamanho real de
        # impressão: um texto de 15,1 cm no papel ocupa 15,1 cm na tela.
        scale = (dpi / 72) * (zoom / 100)
        for page_index in range(len(document)):
            page = document[page_index]
            bitmap = None
            try:
                bitmap = page.render(scale=scale)
                rendered_page = bitmap.to_pil().convert("RGB").copy()
                pages.append(
                    _crop_preview_page_to_content(
                        rendered_page,
                        # Keep only about 0.2 cm of white breathing room at
                        # 100% (the preview is calibrated to physical size).
                        horizontal_padding=max(2, round(2 * zoom / 100)),
                        vertical_padding=max(2, round(2 * zoom / 100)),
                    )
                )
            finally:
                if bitmap is not None:
                    bitmap.close()
                page.close()
    finally:
        document.close()
    if not pages:
        raise RuntimeError("O PDF não contém páginas para visualizar.")
    # Keep only the rendered document in the preview image. The page's blank
    # printable margin is removed per page before this composite is built.
    # A separação entre páginas ganha respiro: duas linhas em branco antes e
    # duas depois do traço central, para evidenciar a divisão das páginas.
    line_spacing = max(4, round(16 * (dpi / 96) * (zoom / 100)))
    separator_height = line_spacing * 4 + 1
    width = max(page.width for page in pages)
    height = sum(page.height for page in pages) + separator_height * (len(pages) - 1)
    preview = Image.new("RGB", (width, height), "#ffffff")
    separator_draw = ImageDraw.Draw(preview)
    page_regions: list[tuple[int, int]] = []
    y = 0
    for page_index, page in enumerate(pages):
        x = 0
        page_start = y
        preview.paste(page, (x, y))
        y += page.height
        page_regions.append((page_start, y))
        if page_index < len(pages) - 1:
            y += line_spacing * 2
            separator_draw.line(
                (0, y, width - 1, y),
                fill="#aeb8b5",
                width=1,
            )
            y += 1 + line_spacing * 2
        page.close()
    del separator_draw
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    preview.save(output_path, format="PNG", optimize=True)
    preview.close()
    return len(pages), page_regions


PORTUGUESE_MONTHS = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)
PORTUGUESE_CARDINALS = {
    0: "zero", 1: "um", 2: "dois", 3: "três", 4: "quatro",
    5: "cinco", 6: "seis", 7: "sete", 8: "oito", 9: "nove",
    10: "dez", 11: "onze", 12: "doze", 13: "treze", 14: "quatorze",
    15: "quinze", 16: "dezesseis", 17: "dezessete", 18: "dezoito",
    19: "dezenove", 20: "vinte", 30: "trinta", 40: "quarenta",
    50: "cinquenta", 60: "sessenta", 70: "setenta", 80: "oitenta",
    90: "noventa", 100: "cem", 200: "duzentos", 300: "trezentos",
    400: "quatrocentos", 500: "quinhentos", 600: "seiscentos",
    700: "setecentos", 800: "oitocentos", 900: "novecentos",
    1000: "mil", 2000: "dois mil",
}


def portuguese_number_words(value: int) -> str:
    value = int(value)
    if value in PORTUGUESE_CARDINALS:
        return PORTUGUESE_CARDINALS[value]
    if not 0 <= value <= 9999:
        return str(value)
    if value >= 1000:
        thousands, remainder = divmod(value, 1000)
        prefix = "mil" if thousands == 1 else f"{portuguese_number_words(thousands)} mil"
        return prefix if remainder == 0 else f"{prefix} e {portuguese_number_words(remainder)}"
    if value > 100:
        hundreds, remainder = divmod(value, 100)
        prefix = "cento" if hundreds == 1 else PORTUGUESE_CARDINALS[hundreds * 100]
        return prefix if remainder == 0 else f"{prefix} e {portuguese_number_words(remainder)}"
    tens, remainder = divmod(value, 10)
    prefix = PORTUGUESE_CARDINALS[tens * 10]
    return prefix if remainder == 0 else f"{prefix} e {PORTUGUESE_CARDINALS[remainder]}"


WORD_PARAGRAPH_RE = re.compile(r"<w:p(?:\s[^>]*)?>.*?</w:p>", re.DOTALL)
WORD_TEXT_RE = re.compile(r"(<w:t(?:\s[^>]*)?>)(.*?)(</w:t>)", re.DOTALL)
WORD_FLOW_BREAK_RE = re.compile(
    r"<w:(?:br|cr|tab|lastRenderedPageBreak)\b",
    re.IGNORECASE,
)


def _replace_word_paragraph_markers(
    paragraph_xml: str,
    replacements: dict[str, str],
) -> tuple[str, int]:
    matches = list(WORD_TEXT_RE.finditer(paragraph_xml))
    if not matches:
        return paragraph_xml, 0
    text_values = [html.unescape(match.group(2)) for match in matches]
    aliases = []
    for marker, replacement in replacements.items():
        aliases.extend(
            (
                (f"{{{{{marker}}}}}", replacement),
                (f"{{{{{{{marker}}}}}}}", replacement),
            )
        )
    aliases.sort(key=lambda item: len(item[0]), reverse=True)
    changed = 0
    while True:
        joined = "".join(text_values)
        match = None
        for marker, replacement in aliases:
            offset = joined.find(marker)
            if offset >= 0 and (match is None or offset > match[0]):
                match = (offset, marker, str(replacement or ""))
        if match is None:
            break
        start, marker, replacement = match
        end = start + len(marker)
        spans = []
        cursor = 0
        for node_text in text_values:
            spans.append((cursor, cursor + len(node_text)))
            cursor += len(node_text)
        first_index = next(
            index for index, (node_start, node_end) in enumerate(spans)
            if node_start <= start < node_end
        )
        last_position = max(start, end - 1)
        last_index = next(
            index for index, (node_start, node_end) in enumerate(spans)
            if node_start <= last_position < node_end
        )
        first_start, _first_end = spans[first_index]
        last_start, _last_end = spans[last_index]
        prefix = text_values[first_index][: start - first_start]
        suffix = text_values[last_index][end - last_start :]
        preceding_character = joined[start - 1 : start] if start else ""
        following_character = joined[end : end + 1]
        preceding_is_adjacent = True
        if preceding_character and start == first_start:
            previous_index = next(
                (
                    index
                    for index in range(first_index - 1, -1, -1)
                    if text_values[index]
                ),
                None,
            )
            if previous_index is not None:
                bridge = paragraph_xml[
                    matches[previous_index].end() : matches[first_index].start()
                ]
                preceding_is_adjacent = not WORD_FLOW_BREAK_RE.search(bridge)
        following_is_adjacent = True
        if following_character and end - last_start == len(text_values[last_index]):
            next_index = next(
                (
                    index
                    for index in range(last_index + 1, len(text_values))
                    if text_values[index]
                ),
                None,
            )
            if next_index is not None:
                bridge = paragraph_xml[
                    matches[last_index].end() : matches[next_index].start()
                ]
                following_is_adjacent = not WORD_FLOW_BREAK_RE.search(bridge)
        if (
            preceding_is_adjacent
            and preceding_character.isalnum()
            and replacement[:1].isalnum()
        ):
            replacement = " " + replacement
        if (
            following_is_adjacent
            and replacement[-1:].isalnum()
            and following_character.isalnum()
        ):
            replacement += " "
        if first_index == last_index:
            text_values[first_index] = prefix + replacement + suffix
        else:
            text_values[first_index] = prefix + replacement
            for index in range(first_index + 1, last_index):
                text_values[index] = ""
            text_values[last_index] = suffix
        changed += 1
    if changed == 0:
        return paragraph_xml, 0
    pieces = []
    previous_end = 0
    for match, value in zip(matches, text_values):
        pieces.append(paragraph_xml[previous_end:match.start()])
        opening_tag = match.group(1)
        if (value[:1].isspace() or value[-1:].isspace()) and "xml:space=" not in opening_tag:
            opening_tag = opening_tag[:-1] + ' xml:space="preserve">'
        pieces.append(opening_tag)
        pieces.append(html.escape(value, quote=False))
        pieces.append(match.group(3))
        previous_end = match.end()
    pieces.append(paragraph_xml[previous_end:])
    return "".join(pieces), changed


def generate_docx_from_template(
    template_path: Path,
    output_path: Path,
    replacements: dict[str, str],
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_changes = 0
    unresolved: list[str] = []
    with zipfile.ZipFile(template_path, "r") as source:
        with zipfile.ZipFile(output_path, "w") as destination:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                    try:
                        xml_text = data.decode("utf-8")
                    except UnicodeDecodeError:
                        xml_text = ""
                    if xml_text and "<w:t" in xml_text:
                        changes = 0

                        def replace_paragraph(match):
                            nonlocal changes
                            updated, count = _replace_word_paragraph_markers(
                                match.group(0),
                                replacements,
                            )
                            changes += count
                            return updated

                        xml_text = WORD_PARAGRAPH_RE.sub(replace_paragraph, xml_text)
                        if changes:
                            data = xml_text.encode("utf-8")
                            total_changes += changes
                        remaining_text = "".join(
                            html.unescape(match.group(2))
                            for match in WORD_TEXT_RE.finditer(xml_text)
                        )
                        unresolved.extend(
                            marker
                            for marker in re.findall(r"\{\{\{?[^{}]+\}\}\}?", remaining_text)
                            if marker not in unresolved
                        )
                destination.writestr(item, data)
    if unresolved:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("Marcadores sem valor no modelo: " + ", ".join(unresolved))
    if total_changes == 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("O modelo não contém marcadores reconhecidos.")
    return total_changes


def ensure_document_templates() -> dict[str, Path]:
    """Resolve os modelos Word na pasta externa ``modelos/`` (ao lado do app).

    Os modelos NÃO vão mais empacotados dentro do executável: a instalação e
    os updates full/diff entregam a pasta ``modelos/`` ao lado do ``sig.exe``.
    Se faltarem, a instalação/atualização está incompleta.
    """
    external_dir = app_base_dir() / "modelos"
    external_dir.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, Path] = {}
    for template_kind, filename in DOCUMENT_TEMPLATE_NAMES.items():
        external_path = external_dir / filename
        if not external_path.exists():
            raise FileNotFoundError(
                f"Modelo não encontrado: {external_path}\n"
                "Os modelos são entregues pela instalação/atualização do SIG. "
                "Execute uma atualização ou use 'Reparar instalação'."
            )
        resolved[template_kind] = external_path
    return resolved


def download_github_url(url: str, destination: Path, progress_callback=None) -> str:
    """Baixa um arquivo de uma URL do GitHub releases, devolvendo o sha256."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SigUpdater/2.0 (+https://github.com/spigknot/SIG-Windows)"},
    )
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            output.write(chunk)
            digest.update(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total)
    return digest.hexdigest()
