#!/bin/bash
set -e
cd "/d/Projetos/SIG Windows"
PY="C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe"
"$PY" scripts/release.py release --version 20260817_002 --incremental 2>&1 | tail -8
