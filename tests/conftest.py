"""Isolamento de estado entre os testes da suíte do SIG.

O motor do servidor STT local (`local_stt_engine`) vem de um estado de módulo
preenchido pela consulta a `/health`. Sem reset entre testes, um teste que
instancia o app ou simula o Nemotron deixa o global preenchido e contamina os
seguintes (campos do formulário, visibilidade do Timestamps). Cada teste
começa em **Granite** — o padrão histórico do app — e decide o seu motor
explicitamente quando precisa do Nemotron.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))


@pytest.fixture(autouse=True)
def _motor_local_limpo():
    """Zera o modelo anunciado antes e depois de cada teste."""
    from providers import set_local_granite_model_id

    set_local_granite_model_id("")
    yield
    set_local_granite_model_id("")
