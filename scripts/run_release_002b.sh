#!/bin/bash
set -euo pipefail
cd "/d/Projetos/SIG Windows"
PY="C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe"
VERSION="${1:?Uso: scripts/run_release_002b.sh YYYYMMDD_NNN}"
"$PY" scripts/release.py release --version "$VERSION" --incremental --quiet 2>&1 | tail -8
