#!/bin/bash
cd "/d/Projetos/SIG Windows"
PY="C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe"
"$PY" scripts/release.py release --version 20260817_005 --incremental > release_output_005.log 2>&1
status=$?
echo "RELEASE_EXIT=$status"
tail -10 release_output_005.log
exit $status
