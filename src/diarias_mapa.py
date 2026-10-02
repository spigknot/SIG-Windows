"""Geração de mapas de diária a partir do modelo Excel (.xlsx)."""

from __future__ import annotations

import gc
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app_env import app_base_dir


TEMPLATE_RELATIVE_PATH = Path("modelos") / "modelo_mapa.xlsx"
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
    )


def _excel_date_serial(value: date) -> int:
    return (value - _EXCEL_EPOCH).days


def _excel_time_fraction(value: time) -> float:
    seconds = value.hour * 3600 + value.minute * 60 + value.second
    return seconds / 86400


def _excel_cell_characters(cell, start: int, length: int):
    """Obtém Range.Characters via PROPERTYGET, como exige a API COM do Excel."""
    import pythoncom
    from win32com.client import Dispatch

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
    return Dispatch(characters)


def _shape_text_characters(text_range, start: int, length: int):
    """Obtém TextRange2.Characters com os tipos declarados no Office COM."""
    import pythoncom
    from win32com.client import Dispatch

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
    return Dispatch(characters)


def _replace_cell_marker(cell, marker: str, replacement: str) -> int:
    text = str(cell.Value2 or "")
    positions = [match.start() for match in re.finditer(re.escape(marker), text)]
    for position in reversed(positions):
        _excel_cell_characters(cell, position + 1, len(marker)).Text = replacement
    if marker in str(cell.Value2 or ""):
        raise RuntimeError(f"Não foi possível substituir a marca {marker} em {cell.Address}.")
    return len(positions)


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


def generate_diarias_mapa(destination: Path, values: DiariasMapaData) -> Path:
    """Preenche uma cópia do modelo com Excel, preservando seu layout e estilos."""
    destination = Path(destination)
    template_path = app_base_dir() / TEMPLATE_RELATIVE_PATH
    if not template_path.is_file():
        raise FileNotFoundError(f"Modelo de mapa não encontrado: {template_path}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"Pasta para salvar o mapa não encontrada: {destination.parent}")
    if destination.exists():
        raise FileExistsError(f"O arquivo de destino já existe: {destination}")
    if destination.suffix.casefold() != ".xlsx":
        raise ValueError("O mapa deve ser salvo no formato .xlsx.")

    try:
        from win32com.client import DispatchEx
    except ImportError as exc:
        raise RuntimeError(
            "O componente de automação do Excel não está disponível neste aplicativo."
        ) from exc

    try:
        excel = DispatchEx("Excel.Application")
    except Exception as exc:
        raise RuntimeError(
            "Não foi possível iniciar o Microsoft Excel. Confira se ele está instalado."
        ) from exc

    workbook = None
    temporary_destination = destination.with_name(
        f".{destination.stem}_{uuid.uuid4().hex}.xlsx"
    )
    try:
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.EnableEvents = False
        try:
            excel.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
        except Exception:
            pass

        workbook = excel.Workbooks.Open(str(template_path), 0, True)
        limite = workbook.Worksheets.Item("Limite 50%")
        verso = workbook.Worksheets.Item("Verso")

        limite.Range("K10").Value2 = values.total_vencimentos
        limite.Range("G16").Value2 = "PARTICULAR" if values.meios_proprios else "VIATURA"
        limite.Range("V10").Value2 = values.valor_ufesp
        limite.Range("AC8").Value2 = _excel_date_serial(values.data_ida)
        # O modelo identifica essas colunas como DIA; mês/ano fica em AC8.
        limite.Range("J16").Value2 = values.data_ida.day
        limite.Range("L16").Value2 = values.data_volta.day
        limite.Range("K16").Value2 = _excel_time_fraction(values.horario_ida)
        limite.Range("M16").Value2 = _excel_time_fraction(values.horario_volta)
        if values.menos_de_12_horas:
            limite.Range("W16").Value2 = 1
            limite.Range("Z16").ClearContents()
        else:
            limite.Range("W16").ClearContents()
            limite.Range("Z16").Value2 = 1
        limite.Range("C45").Value2 = _excel_date_serial(values.data_protocolo)

        if _replace_cell_marker(limite.Range("B34"), "{{{data_ida}}}", values.mes_ano_ida) == 0:
            raise RuntimeError("A marca {{{data_ida}}} não foi encontrada na célula B34 do modelo.")

        verso.Range("A16").Value2 = values.protocolo_requerimento
        marker_counts = _replace_shape_markers(
            verso,
            {
                "{{{data_protocolo}}}": values.data_protocolo.strftime("%d/%m/%Y"),
                "{{{protocolo_mapa}}}": values.protocolo_mapa,
            },
        )
        missing = [marker for marker, count in marker_counts.items() if count == 0]
        if missing:
            raise RuntimeError(
                "Marca(s) não encontrada(s) na planilha Verso: " + ", ".join(missing)
            )

        workbook.SaveAs(str(temporary_destination), 51)
        workbook.Close(SaveChanges=False)
        workbook = None
        if not temporary_destination.is_file():
            raise RuntimeError("O Excel não criou o arquivo de mapa no destino escolhido.")
        temporary_destination.rename(destination)
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
