"""Prompts editáveis do SIG.

Os arquivos externos têm prioridade para permitir ajustes sem recompilar o
aplicativo. Em uma instalação empacotada, a cópia dentro do `_internal` é o
fallback incluído pelo PyInstaller.
"""

from pathlib import Path
import sys


def _prompt_path(filename: str) -> Path:
    candidates = [
        Path(__file__).resolve().parent.parent / "prompts" / filename,
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).resolve().parent / "prompts" / filename)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "prompts" / filename)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Prompt '{filename}' não encontrado. Procurado em: {searched}")


def _read_prompt(filename: str) -> str:
    return _prompt_path(filename).read_text(encoding="utf-8").strip()


DEFAULT_PARTS_PROMPT = _read_prompt("partes_system.txt")
DEFAULT_PARTS_USER_HISTORY_TEMPLATE = _read_prompt("partes_user_botao_historico.txt")
DEFAULT_PARTS_USER_DETECT_TEMPLATE = _read_prompt("partes_user_botao_detectar.txt")
DEFAULT_QUALIFICATION_SYSTEM_PROMPT = _read_prompt("qualificacao_system.txt")
DEFAULT_HISTORY_SYSTEM_PROMPT = _read_prompt("historico_system.txt")
DEFAULT_HISTORY_USER_TEMPLATE = _read_prompt("historico_user.txt")
DEFAULT_STATEMENT_TEMPLATE = _read_prompt("oitiva_system.txt")
DEFAULT_STATEMENT_USER_TEMPLATE = _read_prompt("oitiva_user.txt")

QUALIFICATION_BASE_FIELD_IDS = {
    "nome",
    "nascimento",
    "rg",
    "cpf",
    "naturalidade",
    "sexo",
    "estado_civil",
    "profissao",
    "altura",
    "pele",
    "olhos",
    "cabelo",
    "pai",
    "mae",
    "instrucao",
    "endereco",
    "bairro",
    "cidade",
    "telefone",
}


def qualification_user_prompt(field_ids: list[str], raw_text: str) -> str:
    """Preenche o texto bruto e somente os IDs extras do prompt de qualificação."""
    template = _read_prompt("qualificacao_user.txt")
    extra_ids = []
    for field_id in field_ids:
        normalized = str(field_id).strip()
        if normalized and normalized not in QUALIFICATION_BASE_FIELD_IDS and normalized not in extra_ids:
            extra_ids.append(normalized)
    extra_suffix = f", {', '.join(extra_ids)}" if extra_ids else ""
    raw_value = raw_text.strip()
    return (
        template.replace(
            "{{{INSERIR_AQUI_OUTROS_DADOS_FORNECIDOS_PELO_USUARIO_SEPARANDO_POR_VIRGULA+ESPAÇO}}}",
            extra_suffix,
        )
        .replace("{{{TEXTO_DA_CAIXA_AQUI}}}", raw_value)
        .replace("{{FIELD_IDS}}", ", ".join(field_ids))
        .replace("{{RAW_TEXT}}", raw_value)
    )


def history_user_prompt(transcription: str) -> str:
    """Monta o prompt variável do histórico com a transcrição atual."""
    return DEFAULT_HISTORY_USER_TEMPLATE.replace(
        "{{conteudo_caixa_transcricao}}",
        transcription.strip(),
    ).strip()


def parts_user_prompt_from_transcription(transcription: str) -> str:
    """Monta o prompt do botão Histórico a partir da transcrição."""
    return DEFAULT_PARTS_USER_HISTORY_TEMPLATE.replace(
        "{{{conteudo_caixa_transcricao}}}",
        transcription.strip(),
    ).strip()


def parts_user_prompt_from_history(history: str) -> str:
    """Monta o prompt do botão Detectar a partir do histórico atual."""
    return DEFAULT_PARTS_USER_DETECT_TEMPLATE.replace(
        "{{{conteudo_caixa_historico}}}",
        history.strip(),
    ).strip()


def statement_prompt(selected_name: str | None) -> str:
    return DEFAULT_STATEMENT_TEMPLATE.replace("{{INSTRUCAO_PESSOA}}", "").strip()


def statement_user_prompt(selected_name: str | None, material: str) -> str:
    """Monta o prompt variável da oitiva com o histórico/transcrição atual."""
    name = (selected_name or "").strip() or "parte selecionada"
    return (
        DEFAULT_STATEMENT_USER_TEMPLATE
        .replace("{{NOME_SELECIONADO}}", name)
        .replace("{{{conteudo_caixa_historico}}}", material.strip())
        # Accept the previous marker too, so an older external prompt keeps
        # working while users migrate it to the new naming convention.
        .replace("{{{INSERIR_AQUI_O_CONTEUDO_DA_CAIXA_DE_TEXTO_DO_HISTORICO}}}", material.strip())
        .strip()
    )
