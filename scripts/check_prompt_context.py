"""Validate the stable/conditional agent-context contract without exposing content."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "agents" / "prompt-context.json"

# These values belong in conditional task documents, not in the always-loaded
# prefix. The checker reports only metadata and line numbers on failure.
VOLATILE_PATTERNS = (
    re.compile(r"\bAPP_VERSION\b"),
    re.compile(r"\bPyInstaller\b", re.IGNORECASE),
    re.compile(r"\bPython\s+3(?:\.\d+){1,2}\b", re.IGNORECASE),
    re.compile(r"\b20\d{6}_\d{3}\b"),
    re.compile(r"\bYYYYMMDD(?:_NNN)?\b", re.IGNORECASE),
    re.compile(r"\b(?:sha256|md5)\b", re.IGNORECASE),
    re.compile(r"\b(?:sync_r2\.py|release\.py)\b", re.IGNORECASE),
    re.compile(r"\b(?:r2_config|update_private_key)\b", re.IGNORECASE),
    re.compile(r"\b(?:Cloudflare|Google\s+Drive|R2)\b", re.IGNORECASE),
    re.compile(r"\b(?:PID|processo|process)\b", re.IGNORECASE),
    re.compile(r"\b[A-Za-z]:[\\/]")
)


class ContextContractError(Exception):
    pass


def _load_manifest() -> dict:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContextContractError(f"manifest load failed: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ContextContractError("manifest schema must be 1")
    if not isinstance(data.get("static"), list) or not data["static"]:
        raise ContextContractError("manifest must define static segments")
    if not isinstance(data.get("conditional"), list):
        raise ContextContractError("manifest must define conditional segments")
    return data


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ContextContractError(f"path escapes repository: {relative}") from exc
    if not path.is_file():
        raise ContextContractError(f"context file not found: {relative}")
    return path


def _check_static(relative: str, max_bytes: int) -> tuple[int, str]:
    path = _resolve(relative)
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise ContextContractError(
            f"static segment exceeds {max_bytes} bytes: {relative} ({len(raw)})"
        )
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContextContractError(f"static segment is not UTF-8: {relative}") from exc
    for line_number, line in enumerate(content.splitlines(), start=1):
        for pattern in VOLATILE_PATTERNS:
            if pattern.search(line):
                raise ContextContractError(
                    f"volatile token in static segment {relative}:{line_number}"
                )
    return len(raw), hashlib.sha256(raw).hexdigest()


def validate() -> tuple[list[tuple[str, int, str]], int, int]:
    manifest = _load_manifest()
    static = manifest["static"]
    conditional = manifest["conditional"]
    static_paths = [item.get("path") for item in static]
    conditional_paths = [item.get("path") for item in conditional]
    if any(not isinstance(path, str) or not path for path in static_paths + conditional_paths):
        raise ContextContractError("every segment must have a relative path")
    if len(set(static_paths)) != len(static_paths):
        raise ContextContractError("duplicate static segment")
    if len(set(conditional_paths)) != len(conditional_paths):
        raise ContextContractError("duplicate conditional segment")
    overlap = set(static_paths) & set(conditional_paths)
    if overlap:
        raise ContextContractError(f"segment is both static and conditional: {sorted(overlap)[0]}")
    max_bytes = int(manifest.get("staticMaxBytes", 16000))
    if max_bytes <= 0:
        raise ContextContractError("staticMaxBytes must be positive")

    digests = []
    total = 0
    for item in static:
        if not isinstance(item.get("id"), str) or not item["id"]:
            raise ContextContractError("static segment must have an id")
        size, digest = _check_static(item["path"], max_bytes)
        digests.append((item["id"], size, digest))
        total += size
    for item in conditional:
        _resolve(item["path"])
        if not isinstance(item.get("when"), str) or not item["when"]:
            raise ContextContractError("conditional segment must define when")
    if total > max_bytes:
        raise ContextContractError(
            f"static prefix exceeds {max_bytes} bytes: {total}"
        )
    return digests, total, len(conditional)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="emit one compact result")
    args = parser.parse_args()
    try:
        digests, total, conditional_count = validate()
    except ContextContractError as exc:
        print(f"prompt-context FAIL: {exc}", file=sys.stderr)
        return 1

    combined = hashlib.sha256(
        "\n".join(f"{segment}:{size}:{digest}" for segment, size, digest in digests).encode()
    ).hexdigest()
    if args.quiet:
        print(
            f"prompt-context PASS static_bytes={total} "
            f"static_digest={combined} conditional_segments={conditional_count}"
        )
    else:
        print("prompt-context PASS")
        for segment, size, digest in digests:
            print(f"  {segment}: {size} bytes sha256={digest}")
        print(f"  combined_static_digest: {combined}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
