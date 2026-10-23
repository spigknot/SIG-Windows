"""Persistência local dos QR Codes e encurtamentos, sem dependências de UI."""

import json
import time

from app_env import qrcode_history_path


def read_qrcode_history_records() -> list[dict]:
    path = qrcode_history_path()
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        original = record.get("original_url")
        if not isinstance(original, str) or not original.strip():
            continue
        records.append({
            "time": record.get("time", 0),
            "original_url": original.strip(),
            "shortened_url": str(record.get("shortened_url") or "").strip(),
            "alias": str(record.get("alias") or "").strip(),
        })
    return records


def append_qrcode_history(original_url: str, shortened_url: str = "", alias: str = "") -> None:
    record = {
        "time": int(time.time() * 1000),
        "original_url": original_url.strip(),
        "shortened_url": shortened_url.strip(),
        "alias": alias.strip(),
    }
    path = qrcode_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def clear_qrcode_history() -> None:
    qrcode_history_path().write_text("", encoding="utf-8")
