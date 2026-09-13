"""Categorias curtas dos erros do lote (uma linha viva por TIPO de erro).

Regra do usuário (13/09): o log não pode ter uma linha vermelha por arquivo
(numa fila de 1405 arquivos isso polui a tela). Em vez disso, UMA linha viva por
tipo de erro, curta e objetiva, com o número de arquivos daquele tipo
atualizado em tempo real e o horário da PRIMEIRA ocorrência:

    11:39:00  233 arquivo(s) sem áudio (código 4294967274)
    11:39:15  12 arquivo(s) com erro no VAD

Sem Tkinter, sem rede, sem I/O: só a categorização (testável isolada). Os
rótulos são o que agrupa as contagens — duas falhas com o mesmo rótulo caem na
mesma linha.
"""

import re

# Rótulo genérico quando nenhuma causa conhecida casa.
FALHA_CONVERSAO = "com falha na conversão"
ERRO_TRANSCRICAO = "com erro na transcrição"
ERRO_VAD = "com erro no VAD"
ERRO_ZIP = "com erro no ZIP"

# Motivo extraído do log do FFmpeg -> rótulo curto. A ORDEM importa: o primeiro
# que casar vence (ex.: "does not contain any stream" antes das genéricas).
_CONVERSION_LABELS = (
    ("não possui faixa de áudio", "sem áudio"),
    ("does not contain any stream", "sem áudio"),
    ("does not contain stream", "sem áudio"),
    ("invalid data found", "com arquivo inválido"),
    ("could not find codec parameters", "com arquivo inválido"),
    ("no such file", "com arquivo não encontrado"),
    ("não encontrado", "com o FFmpeg ausente"),
    ("arquivo convertido não foi criado", "sem arquivo convertido"),
    ("arquivo para envio não definido", "sem arquivo para enviar"),
    ("convertido não foi criado", "sem arquivo convertido"),
    ("conversion failed", FALHA_CONVERSAO),
)


def error_code(message: str) -> str:
    """Código citado na mensagem (FFmpeg `código N` ou HTTP N) — ``''`` se não houver)."""
    texto = str(message or "")
    match = re.search(r"c[óo]digo\s+(-?\d+)", texto)
    if not match:
        match = re.search(r"\bHTTP\s+(\d{3})\b", texto)
    return match.group(1) if match else ""


def _com_codigo(rotulo: str, codigo: str) -> str:
    return f"{rotulo} (código {codigo})" if codigo else rotulo


def conversion_label(message: str) -> str:
    """Rótulo curto para uma falha de conversão (ex.: ``sem áudio (código 4294967274)``)."""
    texto = str(message or "")
    low = texto.casefold()
    for chave, rotulo in _CONVERSION_LABELS:
        if chave.casefold() in low:
            return _com_codigo(rotulo, error_code(texto))
    return _com_codigo(FALHA_CONVERSAO, error_code(texto))


def vad_label(_message: str = "") -> str:
    """Rótulo da falha de VAD: sempre o mesmo tipo (o motivo fica no arquivo .txt)."""
    return ERRO_VAD


def transcription_label(message: str, model: str = "") -> str:
    """Rótulo curto da falha de transcrição.

    `model` entra no rótulo somente quando o lote tem mais de um modelo (senão o
    próprio painel já diz qual é). O código HTTP ajuda a separar chave recusada,
    limite de uso e erro do servidor em linhas distintas.
    """
    texto = str(message or "")
    low = texto.casefold()
    detalhe = ""
    codigo = error_code(texto)
    if codigo and "http" in low:
        detalhe = f"HTTP {codigo}"
    elif "timed out" in low or "timeout" in low or "tempo esgotado" in low:
        detalhe = "tempo esgotado"
    elif "auth context expired" in low or "expirad" in low:
        detalhe = "chave expirada"
    elif "não definido" in low or "sem arquivo" in low:
        detalhe = "sem arquivo para enviar"
    partes = [parte for parte in (model, detalhe) if parte]
    sufixo = f" ({', '.join(partes)})" if partes else ""
    return f"{ERRO_TRANSCRICAO}{sufixo}"


def zip_label(_message: str = "") -> str:
    return ERRO_ZIP


def batch_error_text(count: int, label: str) -> str:
    """Linha do log: ``233 arquivo(s) sem áudio (código 4294967274)``."""
    return f"{int(count)} arquivo(s) {label}"


def batch_error_detail(count: int, label: str, items: list[str]) -> str:
    """Texto copiado ao clicar na linha vermelha: cabeçalho + arquivos do tipo."""
    linhas = [batch_error_text(count, label)]
    linhas.extend(str(item) for item in items if str(item or "").strip())
    return "\n".join(linhas)


# Rótulo do arquivo que já estava no formato pedido (linha NORMAL, sem vermelho).
PREPARATION_LABELS = {
    "pronto": "prontos",
    "compactado": "compactados",
}


def preparation_text(kind: str, count: int, total: int) -> str:
    """``13/50 arquivos já estavam prontos`` (só aparece se houver algum)."""
    plural = PREPARATION_LABELS.get(kind, f"{kind}s")
    return f"{int(count)}/{int(total)} arquivos já estavam {plural}"
