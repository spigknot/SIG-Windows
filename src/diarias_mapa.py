"""Geração de mapas de diária a partir do modelo Excel (.xlsx)."""

from __future__ import annotations

import base64
import copy
import gc
import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import time as time_module
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from app_env import app_base_dir
from diarias_profiles import classe_padrao, format_profile_cargo, validate_diarias_profile


TEMPLATE_RELATIVE_PATH = Path("modelos") / "modelo_mapa.xlsx"
_B34_TEMPLATE_PREFIX = "_SIG_DIARIAS_B34_TEMPLATE_"
_EXCEL_EPOCH = date(1899, 12, 30)
_PORTUGUESE_MONTHS = (
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


@dataclass(frozen=True)
class DiariasMapaData:
    """Valores já validados e prontos para preencher o modelo."""

    total_vencimentos: float
    valor_ufesp: float
    data_ida: date
    data_volta: date
    horario_ida: time
    horario_volta: time
    data_protocolo: date
    protocolo_requerimento: str
    protocolo_mapa: str
    meios_proprios: bool
    menos_de_12_horas: bool
    mes_ano_ida: str
    indice_ufesp: float | None = None
    nome: str = ""
    rg: str = ""
    delegacia_oitiva: str = ""
    delegacia_perfil: str = ""
    padrao: str = ""
    cargo_classe: str = ""
    cpf: str = ""
    dados_bancarios: str = ""
    agencia: str = ""
    conta: str = ""
    cidade_plantao: str = ""


def _parse_date(value: str, label: str) -> date:
    try:
        return datetime.strptime(str(value or "").strip(), "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValueError(f"Confira a data de {label} no formato DD/MM/AAAA.") from exc


def _parse_time(value: str, label: str) -> time:
    raw = str(value or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Confira o horário de {label} no formato HH:MM.")


def _parse_brazilian_amount(value: str, label: str) -> float:
    raw = re.sub(r"[^\d,.-]", "", str(value or "").strip())
    if not raw or raw.count(",") > 1:
        raise ValueError(f"Informe o {label} usando um valor numérico válido.")
    if "," in raw:
        integer_part, decimal_part = raw.rsplit(",", 1)
        integer_part = integer_part.replace(".", "")
        if not integer_part or not integer_part.lstrip("-").isdigit() or not decimal_part.isdigit():
            raise ValueError(f"Informe o {label} usando um valor numérico válido.")
        normalized = f"{integer_part}.{decimal_part}"
    elif "." in raw:
        integer_part, decimal_part = raw.rsplit(".", 1)
        if len(decimal_part) in (1, 2) and integer_part.replace(".", "").lstrip("-").isdigit():
            normalized = f"{integer_part.replace('.', '')}.{decimal_part}"
        elif raw.replace(".", "").lstrip("-").isdigit():
            normalized = raw.replace(".", "")
        else:
            raise ValueError(f"Informe o {label} usando um valor numérico válido.")
    elif raw.lstrip("-").isdigit():
        normalized = raw
    else:
        raise ValueError(f"Informe o {label} usando um valor numérico válido.")

    try:
        amount = Decimal(normalized).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Informe o {label} usando um valor numérico válido.") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"Informe o {label} usando um valor numérico válido.")
    return float(amount)


def prepare_diarias_mapa(
    *,
    total_vencimentos: str,
    valor_ufesp: str,
    data_ida: str,
    horario_ida: str,
    data_volta: str,
    horario_volta: str,
    data_protocolo: str,
    protocolo_requerimento: str,
    protocolo_mapa: str,
    meios_proprios: bool,
    profile: Mapping[str, object] | None = None,
    oitiva_delegacia: str = "",
) -> DiariasMapaData:
    """Valida os campos e calcula os valores do mapa."""
    ida = _parse_date(data_ida, "ida do talão")
    volta = _parse_date(data_volta, "volta do talão")
    hora_ida = _parse_time(horario_ida, "ida do talão")
    hora_volta = _parse_time(horario_volta, "volta do talão")
    protocolo_data = _parse_date(data_protocolo, "protocolo")
    saida = datetime.combine(ida, hora_ida)
    retorno = datetime.combine(volta, hora_volta)
    if retorno < saida:
        raise ValueError("A volta do talão é anterior à ida.")

    protocolo_req = str(protocolo_requerimento or "").strip()
    protocolo_map = str(protocolo_mapa or "").strip()
    if not protocolo_req:
        raise ValueError("Extraia ou informe o protocolo do requerimento.")
    if not protocolo_map:
        raise ValueError("Extraia ou informe o protocolo do mapa.")

    profile_values = {}
    if profile is not None:
        selected = validate_diarias_profile(profile)
        profile_values = {
            "indice_ufesp": float(Decimal(selected["ufesp_index"].replace(",", "."))),
            "nome": selected["nome"].upper(),
            "rg": _format_profile_rg(selected["rg"]),
            "delegacia_oitiva": str(oitiva_delegacia or "").strip(),
            "delegacia_perfil": selected["delegacia"].upper(),
            "padrao": classe_padrao(selected["classe"]),
            "cargo_classe": format_profile_cargo(selected["cargo"], selected["classe"]),
            "cpf": _format_profile_cpf(selected["cpf"]),
            "dados_bancarios": f"001 / {selected['agencia']} / {selected['conta']}",
            "agencia": selected["agencia"],
            "conta": selected["conta"],
            "cidade_plantao": selected["cidade_plantao"],
        }

    return DiariasMapaData(
        total_vencimentos=_parse_brazilian_amount(
            total_vencimentos, "total de vencimentos do holerite"
        ),
        valor_ufesp=_parse_brazilian_amount(valor_ufesp, "valor da UFESP"),
        data_ida=ida,
        data_volta=volta,
        horario_ida=hora_ida,
        horario_volta=hora_volta,
        data_protocolo=protocolo_data,
        protocolo_requerimento=protocolo_req,
        protocolo_mapa=protocolo_map,
        meios_proprios=bool(meios_proprios),
        menos_de_12_horas=(retorno - saida) < timedelta(hours=12),
        mes_ano_ida=f"{_PORTUGUESE_MONTHS[ida.month - 1]}/{ida.year}",
        **profile_values,
    )


def _excel_date_serial(value: date) -> int:
    return (value - _EXCEL_EPOCH).days


def _excel_time_fraction(value: time) -> float:
    seconds = value.hour * 3600 + value.minute * 60 + value.second
    return seconds / 86400


def _format_profile_rg(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 9:
        base, check_digit = digits[:-1], digits[-1]
        return f"{base[:-6]}.{base[-6:-3]}.{base[-3:]}-{check_digit}"
    return str(value or "").strip()


def _format_profile_cpf(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return str(value or "").strip()


def _excel_cell_characters(cell, start: int, length: int):
    """Obtém Range.Characters via PROPERTYGET, como exige a API COM do Excel."""
    import pythoncom

    dispatch_id = cell._oleobj_.GetIDsOfNames("Characters")
    characters = cell._oleobj_.InvokeTypes(
        dispatch_id,
        0,
        pythoncom.DISPATCH_PROPERTYGET,
        (9, 0),
        ((12, 17), (12, 17)),
        start,
        length,
    )
    return _cache_free_excel_dispatch(characters)


def _shape_text_characters(text_range, start: int, length: int):
    """Obtém TextRange2.Characters com os tipos declarados no Office COM."""
    import pythoncom

    dispatch_id = text_range._oleobj_.GetIDsOfNames("Characters")
    characters = text_range._oleobj_.InvokeTypes(
        dispatch_id,
        0,
        pythoncom.DISPATCH_PROPERTYGET,
        (9, 0),
        ((3, 49), (3, 49)),
        start,
        length,
    )
    return _cache_free_excel_dispatch(characters)


def _replace_cell_marker(cell, marker: str, replacement: str) -> int:
    text = str(cell.Value2 or "")
    positions = [match.start() for match in re.finditer(re.escape(marker), text)]
    for position in reversed(positions):
        _excel_cell_characters(cell, position + 1, len(marker)).Text = replacement
    if marker in str(cell.Value2 or ""):
        raise RuntimeError(f"Não foi possível substituir a marca {marker} em {cell.Address}.")
    return len(positions)


def _replace_sheet_cell_markers(sheet, replacements: dict[str, str]) -> dict[str, int]:
    """Substitui tags em células com Characters para manter a fonte de cada trecho."""
    counts = {marker: 0 for marker in replacements}
    used = sheet.UsedRange
    rows, columns = int(used.Rows.Count), int(used.Columns.Count)
    values = used.Value2
    if rows == 1 and columns == 1:
        values = ((values,),)
    else:
        # Normaliza as variantes 1D/2D devolvidas pelo COM para linhas e
        # colunas, inclusive quando o UsedRange tem apenas uma coluna.
        if rows == 1 and (not values or not isinstance(values[0], (tuple, list))):
            values = (values,)
        else:
            values = tuple(
                tuple(row) if isinstance(row, (tuple, list)) else (row,)
                for row in values
            )
    first_row, first_column = int(used.Row), int(used.Column)
    for row_offset, row_values in enumerate(values):
        for column_offset, value in enumerate(row_values):
            if not isinstance(value, str) or "{{{" not in value:
                continue
            cell = sheet.Cells.Item(first_row + row_offset, first_column + column_offset)
            if cell.HasFormula:
                continue
            for marker, replacement in replacements.items():
                if marker in value:
                    counts[marker] += _replace_cell_marker(cell, marker, replacement)
                    value = str(cell.Value2 or "")
    return counts


def _replace_shape_markers(sheet, replacements: dict[str, str]) -> dict[str, int]:
    counts = {marker: 0 for marker in replacements}
    for shape_index in range(1, int(sheet.Shapes.Count) + 1):
        shape = sheet.Shapes.Item(shape_index)
        try:
            text_range = shape.TextFrame2.TextRange
            text = str(text_range.Text or "")
        except Exception:
            continue

        matches = []
        for marker, replacement in replacements.items():
            for position in re.finditer(re.escape(marker), text):
                matches.append((position.start(), marker, replacement))
                counts[marker] += 1
        for position, marker, replacement in sorted(matches, reverse=True):
            _shape_text_characters(text_range, position + 1, len(marker)).Text = replacement

        remaining = str(text_range.Text or "")
        for marker in replacements:
            if marker in remaining:
                raise RuntimeError(f"Não foi possível substituir a marca {marker} no verso.")
    return counts


def next_available_diarias_mapa_path(directory: Path, data_ida: date) -> Path:
    """Retorna `mapa_diaria_DD-MM-AAAA.xlsx`, numerando duplicatas."""
    directory = Path(directory)
    stem = f"mapa_diaria_{data_ida:%d-%m-%Y}"
    candidate = directory / f"{stem}.xlsx"
    suffix = 2
    while candidate.exists():
        candidate = directory / f"{stem}_{suffix}.xlsx"
        suffix += 1
    return candidate


def _prepare_mapa_template(template_path: Path, directory: Path) -> Path:
    """Recupera o texto rico de B34 guardado no próprio modelo com marcadores x.

    Os nomes ocultos guardam o texto editável e suas fontes, sem uma terceira
    planilha nem texto de modelo duplicado no código. Modelos antigos com tags
    continuam funcionando diretamente.
    """
    with zipfile.ZipFile(template_path) as source:
        sheet_path = "xl/worksheets/sheet1.xml"
        sheet_xml = source.read(sheet_path).decode("utf-8")
        cell_pattern = r'<c\b[^>]*\br="B34"(?:[^>]*?/>|[^>]*?>.*?</c>)'
        match = re.search(cell_pattern, sheet_xml, flags=re.DOTALL)
        if match is None:
            raise RuntimeError("A célula B34 não foi encontrada no modelo de mapa.")
        cell = ET.fromstring(match.group())
        if cell.get("t") == "s":
            index = int(cell.findtext("v"))
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            shared = ET.fromstring(source.read("xl/sharedStrings.xml")).findall("s:si", ns)
            value = "".join(shared[index].itertext())
        else:
            value = "".join(cell.itertext())
        if value.strip() != "x":
            return template_path
        workbook = ET.fromstring(source.read("xl/workbook.xml"))
        pieces = sorted((node.get("name"), node.text or "") for node in workbook.iter()
                        if (node.get("name") or "").startswith(_B34_TEMPLATE_PREFIX))
        if not pieces:
            raise RuntimeError("O modelo com x não contém o texto de preenchimento de B34.")
        try:
            encoded = "".join(text.strip().strip('"') for _name, text in pieces)
            rich_text = base64.b64decode(encoded, validate=True).decode("utf-8")
            if ET.fromstring(rich_text).tag != "is":
                raise ValueError("Texto rico inválido")
        except Exception as exc:
            raise RuntimeError("O texto de B34 guardado no modelo está inválido.") from exc
        opening = re.match(r'<c\b[^>]*>', match.group()).group()
        opening = re.sub(r'\bt="[^"]*"', 't="inlineStr"', opening)
        if 't="inlineStr"' not in opening:
            opening = opening[:-1] + ' t="inlineStr">'
        cell_xml = opening + rich_text + "</c>"
        prepared_sheet = sheet_xml[:match.start()] + cell_xml + sheet_xml[match.end():]
        prepared = directory / "modelo_mapa.xlsx"
        with zipfile.ZipFile(prepared, "w") as destination:
            for entry in source.infolist():
                destination.writestr(copy.copy(entry), prepared_sheet.encode("utf-8") if entry.filename == sheet_path else source.read(entry))
    return prepared


def _cache_free_excel_dispatch(dispatch, user_name=None):
    """Mantém métodos e objetos retornados pelo Excel fora do cache gen_py."""
    from win32com.client import dynamic

    def wrap(value, name=None, _result_clsid=None):
        return dynamic.Dispatch(value, name, createClass=ExcelDispatch)

    class ExcelDispatch(dynamic.CDispatch):
        def _wrap_dispatch_(self, value, userName=None, returnCLSID=None):
            return wrap(value, userName)

        def _make_method_(self, name):
            method = super()._make_method_(name)
            if method is not None:
                # pywin32 usa o Dispatch com cache nos métodos gerados, mesmo
                # quando o objeto pai foi aberto com despacho dinâmico.
                method.__func__.__globals__["Dispatch"] = wrap
            return method

    return wrap(dispatch, user_name)


def _create_excel_application():
    """Abre uma instância própria sem os wrappers gerados no cache gen_py.

    Um cache incompleto pode impedir DispatchEx de devolver uma instância de
    Excel que já iniciou. O despacho dinâmico também vale para seus filhos.
    """
    import pythoncom

    dispatch = pythoncom.CoCreateInstance(
        "Excel.Application", None,
        pythoncom.CLSCTX_LOCAL_SERVER, pythoncom.IID_IDispatch,
    )
    return _cache_free_excel_dispatch(dispatch, "Excel.Application")


def _replace_template_markers(sheet, replacements: dict[str, str]) -> dict[str, int]:
    counts = _replace_sheet_cell_markers(sheet, replacements)
    shape_counts = _replace_shape_markers(sheet, replacements)
    for marker, count in shape_counts.items():
        counts[marker] += count
    return counts


def _replace_verso_delegacia_heading(sheet, delegacia: str) -> int:
    """Atualiza o título fixo de delegacia em modelos sem a tag delegacia2."""
    shapes = getattr(sheet, "Shapes", None)
    if shapes is None:
        return 0
    for shape_index in range(1, int(shapes.Count) + 1):
        shape = shapes.Item(shape_index)
        try:
            text_range = shape.TextFrame2.TextRange
            text = str(text_range.Text or "")
        except Exception:
            continue
        first_line = text.replace("\r", "\n").split("\n", 1)[0]
        if re.match(r"^\s*DELEGACIA\b", first_line, flags=re.IGNORECASE):
            _shape_text_characters(text_range, 1, len(first_line)).Text = delegacia
            return 1
    return 0


def generate_diarias_mapa(destination: Path, values: DiariasMapaData) -> Path:
    """Gera o mapa como XLSX ou PDF a partir do modelo e dados da diária."""
    destination = Path(destination)
    template_path = app_base_dir() / TEMPLATE_RELATIVE_PATH
    if not template_path.is_file():
        raise FileNotFoundError(f"Modelo de mapa não encontrado: {template_path}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"Pasta para salvar o mapa não encontrada: {destination.parent}")
    extension = destination.suffix.casefold()
    if extension not in {".xlsx", ".pdf"}:
        raise ValueError("O mapa deve ser salvo no formato .xlsx ou .pdf.")
    export_pdf = extension == ".pdf"

    try:
        excel = _create_excel_application()
    except ImportError as exc:
        raise RuntimeError(
            "O componente de automação do Excel não está disponível neste aplicativo."
        ) from exc

    except Exception as exc:
        raise RuntimeError(
            f"Não foi possível iniciar o Microsoft Excel: {exc}"
        ) from exc

    workbook = None
    temporary_template = tempfile.TemporaryDirectory(prefix=".sig-mapa-modelo-", dir=str(destination.parent))
    temporary_destination = destination.with_name(
        f".{destination.stem}_{uuid.uuid4().hex}{extension}"
    )
    try:
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.EnableEvents = False
        try:
            excel.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
        except Exception:
            pass

        prepared_template = _prepare_mapa_template(template_path, Path(temporary_template.name))
        workbook = excel.Workbooks.Open(str(prepared_template), 0, True)
        limite = workbook.Worksheets.Item("Limite 50%")
        verso = workbook.Worksheets.Item("Verso")

        limite.Range("G16").Value2 = "PARTICULAR" if values.meios_proprios else "VIATURA"
        limite.Range("B16").Value2 = values.cidade_plantao.upper()
        limite.Range("V10").Value2 = values.valor_ufesp
        if getattr(values, "indice_ufesp", None) is not None:
            # Escreve apenas os campos fixos previstos no mapa novo. Value2
            # conserva os estilos aplicados às células no modelo.
            for address, value in (
                ("Z10", values.indice_ufesp),
                ("B8", values.nome.upper()),
                ("N8", values.rg),
                ("T8", values.delegacia_oitiva),
                ("B10", values.padrao),
                ("E10", values.cargo_classe),
                ("J28", values.cpf),
            ):
                limite.Range(address).Value2 = value
        limite.Range("K10").Value2 = values.total_vencimentos
        limite.Range("AC8").Value2 = _excel_date_serial(values.data_ida)
        limite.Range("J16").Value2 = values.data_ida.day
        limite.Range("L16").Value2 = values.data_volta.day
        limite.Range("K16").Value2 = _excel_time_fraction(values.horario_ida)
        limite.Range("M16").Value2 = _excel_time_fraction(values.horario_volta)
        limite.Range("C45").Value2 = _excel_date_serial(values.data_protocolo)
        if values.menos_de_12_horas:
            limite.Range("W16").Value2 = 1
            limite.Range("Z16").ClearContents()
        else:
            limite.Range("W16").ClearContents()
            limite.Range("Z16").Value2 = 1
        template_markers = {
            "{{{cidade_plantao}}}": values.cidade_plantao,
            "{{{agencia}}}": values.agencia,
            "{{{conta}}}": values.conta,
            "{{{data_ida}}}": values.mes_ano_ida,
            "{{{data protocolo}}}": values.data_protocolo.strftime("%d/%m/%Y"),
            "{{{data_protocolo}}}": values.data_protocolo.strftime("%d/%m/%Y"),
            "{{{protocolo_mapa}}}": values.protocolo_mapa,
            "{{{protocolo_requerimento}}}": values.protocolo_requerimento,
            "{{{delegacia2}}}": values.delegacia_perfil,
        }
        marker_counts = _replace_template_markers(limite, template_markers)
        verso.Range("A16").Value2 = values.protocolo_requerimento
        verso_markers = _replace_template_markers(verso, template_markers)
        for marker, count in verso_markers.items():
            marker_counts[marker] += count
        # O modelo distribuído ainda mantém estes dois trechos como texto
        # estático; os valores são atualizados enquanto ele não tiver as tags.
        if not marker_counts["{{{agencia}}}"] and not marker_counts["{{{conta}}}"]:
            limite.Range("T28").Value2 = values.dados_bancarios
        if not marker_counts["{{{delegacia2}}}"]:
            marker_counts["{{{delegacia2}}}"] = _replace_verso_delegacia_heading(
                verso, values.delegacia_perfil
            )
        required_tag_groups = (
            ("{{{cidade_plantao}}}",), ("{{{data_ida}}}",),
            ("{{{data protocolo}}}", "{{{data_protocolo}}}"),
            ("{{{protocolo_mapa}}}",),
        )
        missing = [group[0] for group in required_tag_groups
                   if not any(marker_counts[marker] for marker in group)]
        if missing:
            raise RuntimeError(
                "Marca(s) obrigatória(s) não encontrada(s) no modelo de mapa: "
                + ", ".join(missing)
            )

        if export_pdf:
            for worksheet in (limite, verso):
                worksheet.PageSetup.Zoom = False
                worksheet.PageSetup.FitToPagesWide = 1
                worksheet.PageSetup.FitToPagesTall = 1
            # O modelo pode estar em cálculo manual ou ter resultados em cache.
            # Reconstrói as dependências após preencher os dados e aguarda o Excel.
            excel.CalculateFullRebuild()
            calculation_deadline = time_module.monotonic() + 60
            while excel.CalculationState != 0:  # xlDone
                if time_module.monotonic() >= calculation_deadline:
                    raise RuntimeError(
                        "O Excel não concluiu o cálculo das fórmulas do mapa."
                    )
                time_module.sleep(0.1)
            workbook.ExportAsFixedFormat(0, str(temporary_destination))
        else:
            workbook.SaveAs(str(temporary_destination), 51)
        workbook.Close(SaveChanges=False)
        workbook = None
        if not temporary_destination.is_file() or temporary_destination.stat().st_size <= 0:
            raise RuntimeError("O Excel não criou o arquivo de mapa no destino escolhido.")
        os.replace(temporary_destination, destination)
        return destination
    except Exception as exc:
        temporary_destination.unlink(missing_ok=True)
        if isinstance(exc, (FileNotFoundError, FileExistsError, RuntimeError, ValueError)):
            raise
        raise RuntimeError(f"Falha ao preencher o modelo do mapa: {exc}") from exc
    finally:
        if workbook is not None:
            try:
                workbook.Close(SaveChanges=False)
            except Exception:
                pass
        try:
            excel.Quit()
        except Exception:
            pass
        workbook = None
        excel = None
        gc.collect()
        temporary_template.cleanup()
