"""Consulta de IMEI (API externa) e historico local em imei_history.txt.

Arquivo do historico: app_env.imei_history_path(). Sem Tkinter."""

import http.client
import json
import socket
import time
from app_env import imei_history_path
from urllib.parse import quote, urlparse


def compute_imei_luhn_digit(number_only_digits: str) -> int:
    digits = [int(char) for char in number_only_digits if char.isdigit()]
    total = 0
    length = len(digits)
    for index in range(length - 1, -1, -1):
        digit = digits[index]
        pos_from_right_if_check_appended = (length - index) + 1
        if pos_from_right_if_check_appended % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return (10 - (total % 10)) % 10


def read_imei_history_records() -> list[dict]:
    path = imei_history_path()
    if not path.exists() or path.stat().st_size == 0:
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def append_imei_history(record: dict):
    path = imei_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def find_imei_history_record(imei: str) -> dict | None:
    for record in reversed(read_imei_history_records()):
        if str(record.get("imei") or "") == imei:
            return record
    return None


def format_imei_model(record: dict) -> str:
    brand = str(record.get("brand") or "—")
    model = str(record.get("model") or "—")
    name = str(record.get("name") or "—")
    return f"Marca: {brand}\nModelo: {model} ({name})"


def format_imei_time(timestamp_ms) -> str:
    try:
        value = int(timestamp_ms)
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        return "Data indisponível"
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(value / 1000))


def format_imei_history_item(record: dict) -> str:
    return (
        f"{format_imei_time(record.get('time', 0))}\n"
        f"IMEI: {record.get('imei', '')}\n"
        f"{format_imei_model(record)}"
    )


def fetch_imei_info_record(imei: str, api_key: str) -> dict:
    url = (
        "https://alpha.imeicheck.com/api/free_with_key/modelBrandName"
        f"?key={quote(api_key)}&imei={quote(imei)}&format=json"
    )
    parsed = urlparse(url)
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    conn = connection_cls(parsed.netloc, timeout=30)
    try:
        conn.request("GET", path, headers={"accept": "application/json"})
        response = conn.getresponse()
        body = response.read()
    except (OSError, socket.timeout) as exc:
        raise ConnectionError("Cheque sua conexão") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass
    try:
        payload = json.loads(body.decode("utf-8", errors="replace") or "{}")
    except Exception as exc:
        raise ValueError("Erro ao processar resposta") from exc
    if not isinstance(payload, dict) or payload.get("status") != "succes":
        raise LookupError("Modelo não encontrado")
    obj = payload.get("object")
    if not isinstance(obj, dict):
        raise LookupError("Modelo não encontrado")
    return {
        "time": int(time.time() * 1000),
        "imei": imei,
        "brand": obj.get("brand") or "—",
        "model": obj.get("model") or "—",
        "name": obj.get("name") or "—",
    }
