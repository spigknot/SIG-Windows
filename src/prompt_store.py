"""Prompts editaveis do SIG: layout em disco, escolha do prompt em uso e
atualizacao do padrao pelo bucket R2.

Responsabilidade unica (docs/agents/module-map.md): a REGRA dos prompts de
historico, oitiva e qualificacao — onde cada arquivo mora, qual id esta em uso
em cada slot, como o `Padrao` e protegido, e como o padrao baixa do R2. A aba
`Prompts` de `sig_app.py` cuida so da UI e chama estas funcoes.

Nao importa `tkinter` nem `sig_app` (testado em tests/test_modularizacao_contrato.py).

Layout (raiz = %APPDATA%\\sig\\Prompts, sem permissao de escrita requerida):

    padrao/<arquivo>          padrao vigente (seed do app, trocado pelo R2)
    custom/<slot>/<id>.txt    prompts do usuario
    ativo.json                {"<slot>": "Padrao" | "<id>"}
    origem.json               sha256 do que foi baixado (evita rebaixar tudo)

O `Padrao` nunca e sobrescrito: `save_custom` recusa esse id e a UI desabilita o
botao Salvar nele. Editar o padrao e possivel apenas com `save_as` (outro
nome) ou importando outro `.txt`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterable


# ── id e marcadores ─────────────────────────────────────────────────────

#: Id do prompt padrao do app — o que o usuario ve como "Padrao" na lista.
PROMPT_DEFAULT_ID = "Padrao"

#: URL publico do bucket `prompts` no Cloudflare R2 (fonte: pasta `prompts/`).
R2_PROMPTS_BASE_URL = "https://pub-916eee09ee6c4c20ad6a51523e965071.r2.dev"

#: Teto de um prompt: os maiores hoje tem ~7 KiB, 64 KiB e folga generosa.
MAX_PROMPT_BYTES = 64 * 1024

#: o r2.dev bloqueia o UA padrao do urllib (HTTP 1010).
PUBLIC_UA = "SIG-Prompts/1.0 (+https://github.com/spigknot/SIG-Windows)"

#: Marcador que a requisicao de historico preenche com a transcricao.
HISTORY_TRANSCRIPT_MARKER = "{{conteudo_caixa_transcricao}}"

#: Marcador que a requisicao de oitiva preenche com o historico/material.
STATEMENT_HISTORY_MARKER = "{{{conteudo_caixa_historico}}}"

#: Marcador anterior da oitiva, ainda aceito na leitura.
STATEMENT_HISTORY_LEGACY_MARKER = (
    "{{{INSERIR_AQUI_O_CONTEUDO_DA_CAIXA_DE_TEXTO_DO_HISTORICO}}}"
)

#: Marcadores do prompt de usuario da qualificacao.
QUALIFICATION_RAW_MARKER = "{{{TEXTO_DA_CAIXA_AQUI}}}"
QUALIFICATION_EXTRA_MARKER = (
    "{{{INSERIR_AQUI_OUTROS_DADOS_FORNECIDOS_PELO_USUARIO_SEPARANDO_POR_VIRGULA+ESPAÇO}}}"
)


class PromptSlot:
    """Um prompt gerenciado pela tela: liga o arquivo ao rotulo e ao marcador.

    Os 6 slots sao os de historico, oitiva e qualificacao. Os prompts de
    `partes` continuam carregando de `prompts/` (fora do escopo da tela), mas
    sao baixados do R2 junto com os demais.
    """

    __slots__ = ("key", "file", "label", "required_markers", "user_markers")

    def __init__(
        self,
        key: str,
        file: str,
        label: str,
        required_markers: tuple[str, ...] = (),
        user_markers: tuple[str, ...] = (),
    ) -> None:
        self.key = key
        self.file = file
        self.label = label
        # Marcadores obrigatorios: sem eles o app chamaria o modelo com o
        # marcador cru no lugar do material.
        self.required_markers = required_markers
        # Marcadores que valem a pena inferir na importacao de um `.txt`.
        self.user_markers = user_markers

    @property
    def is_user(self) -> bool:
        return bool(self.required_markers)

    def __repr__(self) -> str:  # pragma: no cover - ajuda em asserts
        return f"PromptSlot({self.key!r})"


HISTORY_SYSTEM = PromptSlot("historico_system", "historico_system.txt", "Historico - sistema")
HISTORY_USER = PromptSlot(
    "historico_user",
    "historico_user.txt",
    "Historico - usuario",
    required_markers=(HISTORY_TRANSCRIPT_MARKER,),
    user_markers=(HISTORY_TRANSCRIPT_MARKER,),
)
STATEMENT_SYSTEM = PromptSlot("oitiva_system", "oitiva_system.txt", "Oitiva - sistema")
STATEMENT_USER = PromptSlot(
    "oitiva_user",
    "oitiva_user.txt",
    "Oitiva - usuario",
    required_markers=(STATEMENT_HISTORY_MARKER, STATEMENT_HISTORY_LEGACY_MARKER),
    user_markers=(STATEMENT_HISTORY_MARKER, STATEMENT_HISTORY_LEGACY_MARKER),
)
QUALIFICATION_SYSTEM = PromptSlot(
    "qualificacao_system", "qualificacao_system.txt", "Qualificacao - sistema"
)
QUALIFICATION_USER = PromptSlot(
    "qualificacao_user",
    "qualificacao_user.txt",
    "Qualificacao - usuario",
    required_markers=(QUALIFICATION_RAW_MARKER,),
    user_markers=(QUALIFICATION_RAW_MARKER,),
)

#: Slots da tela, na ordem em que aparecem na lista.
PROMPT_SLOTS: tuple[PromptSlot, ...] = (
    HISTORY_SYSTEM,
    HISTORY_USER,
    STATEMENT_SYSTEM,
    STATEMENT_USER,
    QUALIFICATION_SYSTEM,
    QUALIFICATION_USER,
)

#: Todos os `.txt` da RAIZ de `prompts/` (a subpasta `prompts_antigos/` e
#: ignorada): e o que o botao "baixar prompts atualizados" traz. Os de `partes`
#: vao junto para uso futuro da tela.
ROOT_PROMPT_FILES: tuple[str, ...] = tuple(slot.file for slot in PROMPT_SLOTS) + (
    "partes_system.txt",
    "partes_user_botao_historico.txt",
    "partes_user_botao_detectar.txt",
)

SLOTS_BY_KEY = {slot.key: slot for slot in PROMPT_SLOTS}

#: Qual constante de `assistant_prompts` cada slot alimenta. O app recarrega
#: essas constantes depois de uma escolha ou de um download, para a troca valer
#: na próxima requisição sem reiniciar.
PROMPT_CONSTANTE_POR_SLOT = {
    "historico_system": "DEFAULT_HISTORY_SYSTEM_PROMPT",
    "historico_user": "DEFAULT_HISTORY_USER_TEMPLATE",
    "oitiva_system": "DEFAULT_STATEMENT_TEMPLATE",
    "oitiva_user": "DEFAULT_STATEMENT_USER_TEMPLATE",
    "qualificacao_system": "DEFAULT_QUALIFICATION_SYSTEM_PROMPT",
    "qualificacao_user": "QUALIFICATION_USER_TEMPLATE",
}


def sanitize_id(raw: str) -> str:
    """Nome de arquivo seguro para um id de prompt."""
    value = re.sub(r"[^\w\- ]+", "_", str(raw or "").strip(), flags=re.UNICODE)
    value = re.sub(r"\s+", "_", value).strip("._")
    return value[:64]


def _fold(value: str) -> str:
    """Compara ids sem acento nem caixa: `Padrão`, `padrao` e `PADRAO` sao o mesmo."""
    decomposto = unicodedata.normalize("NFKD", str(value or ""))
    sem_acento = "".join(char for char in decomposto if not unicodedata.combining(char))
    return sem_acento.casefold()


def is_default_id(raw: str) -> bool:
    """`True` quando o id é o `Padrao` do app (o prompt protegido)."""
    return _fold(raw) == _fold(PROMPT_DEFAULT_ID)


# ── pasta do usuario ────────────────────────────────────────────────────

def prompts_dir() -> Path:
    """Raiz dos prompts do usuario — %APPDATA%\\sig\\Prompts.

    Fica fora de `C:\\Program Files` de proposito: la a escrita exige
    administracao e o botao de download levantaria UAC a cada uso.
    """
    base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return base / "sig" / "Prompts"


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _write_atomic(path: Path, text: str) -> None:
    """Grava por arquivo temporario + replace: uma falha deixa o anterior."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_text(text: str) -> str:
    """Texto do prompt em uma forma unica, para comparar e gravar.

    O mesmo prompt pode estar no disco com LF (a pasta `prompts/` do repo) e
    no R2 com CRLF (o que o Windows gravou). Sao o MESMO prompt — sem
    normalizar, o app diria "8 alterados" num PC recem instalado e reescreveria
    arquivo por arquivo sem mudar nada. Por isso a comparacao e a gravacao
    usam esta forma, e o `manifest.json` e calculado sobre ela.
    """
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


# ── rede ───────────────────────────────────────────────────────────────

def _urlopen(url: str, *, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": PUBLIC_UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(MAX_PROMPT_BYTES + 1)


def fetch_text(url: str, *, timeout: float = 30.0) -> str:
    """Baixa um prompt publico do R2, exigindo UTF-8 valido e o teto de tamanho."""
    data = _urlopen(url, timeout=timeout)
    if len(data) > MAX_PROMPT_BYTES:
        raise ValueError("resposta acima do limite de 64 KiB")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"resposta nao e UTF-8 valido ({exc})") from exc


def fetch_manifest(base_url: str = R2_PROMPTS_BASE_URL, *, timeout: float = 15.0) -> dict | None:
    """Le `manifest.json` do bucket, se existir. `None` quando nao houver.

    O manifesto carrega o sha256 de cada prompt: com ele o app decide se ha
    versao nova em UM request, em vez de baixar os 9 para descobrir que sao
    iguais. Ausente, o app cai na comparacao conteudo a conteudo.
    """
    try:
        raw = _urlopen(f"{base_url.rstrip('/')}/manifest.json", timeout=timeout)
        data = json.loads(raw.decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    files = data.get("files")
    if not isinstance(files, dict):
        return None
    digests = {
        str(name).replace("\\", "/").split("/")[-1]: str(digest).lower()
        for name, digest in files.items()
    }
    return {"digest": sha256_text(json.dumps(files, sort_keys=True)), "files": digests}


# ── store ──────────────────────────────────────────────────────────────

class PromptEntry:
    """Uma linha da lista da aba Prompts: um slot + um id."""

    __slots__ = ("slot", "id", "active")

    def __init__(self, slot: PromptSlot, id: str, active: bool) -> None:
        self.slot = slot
        self.id = id
        self.active = active

    @property
    def is_default(self) -> bool:
        return self.id == PROMPT_DEFAULT_ID

    @property
    def label(self) -> str:
        return f"{self.slot.label} - {'Padrao' if self.is_default else self.id}"

    @property
    def display_label(self) -> str:
        return f"{self.label} (em uso)" if self.active else self.label

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, PromptEntry)
            and (self.slot.key, self.id, self.active) == (other.slot.key, other.id, other.active)
        )

    def __repr__(self) -> str:  # pragma: no cover - ajuda em asserts
        return f"PromptEntry({self.slot.key!r}, {self.id!r}, active={self.active})"


class PromptStore:
    """Layout dos prompts do usuario e resolucao do prompt em uso por slot.

    `seed_reader` devolve o texto do padrao que veio com o app (a pasta
    `prompts/` ao lado do executavel): e a semente de `padrao/`, usada so
    quando o usuario ainda nao baixou uma versao nova do R2.
    """

    def __init__(self, root: Path | None = None, seed_reader: Callable[[str], str | None] | None = None) -> None:
        self.root = Path(root) if root is not None else prompts_dir()
        self._seed_reader = seed_reader

    # ── layout ────────────────────────────────────────────────────────

    @property
    def _padrao_dir(self) -> Path:
        return self.root / "padrao"

    @property
    def _active_file(self) -> Path:
        return self.root / "ativo.json"

    @property
    def _origin_file(self) -> Path:
        return self.root / "origem.json"

    def _custom_dir(self, slot: PromptSlot) -> Path:
        return self.root / "custom" / slot.key

    def _custom_file(self, slot: PromptSlot, id: str) -> Path:
        return self._custom_dir(slot) / f"{sanitize_id(id)}.txt"

    def ensure_layout(self) -> None:
        """Cria o layout e semeia `padrao/` com o que veio no app. Idempotente.

        Semeia apenas arquivo AUSENTE: um `padrao/` ja baixado do R2 nao e
        sobrescrito pela versao do executavel.
        """
        self._padrao_dir.mkdir(parents=True, exist_ok=True)
        (self.root / "custom").mkdir(parents=True, exist_ok=True)
        for slot in PROMPT_SLOTS:
            self._custom_dir(slot).mkdir(parents=True, exist_ok=True)
            target = self._padrao_dir / slot.file
            if target.is_file():
                continue
            seed = self._read_seed(slot.file)
            if seed is not None:
                _write_atomic(target, seed)

    def _read_seed(self, file: str) -> str | None:
        if self._seed_reader is not None:
            try:
                return self._seed_reader(file)
            except Exception:  # noqa: BLE001 - semente ausente nao e erro fatal
                return None
        return None

    # ── leitura ───────────────────────────────────────────────────────

    def _read_actives(self) -> dict[str, str]:
        data = _read_text(self._active_file)
        if not data:
            return {}
        try:
            loaded = json.loads(data)
        except ValueError:
            return {}
        if not isinstance(loaded, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in loaded.items()
            if isinstance(value, str) and value.strip()
        }

    def _write_actives(self, actives: dict[str, str]) -> None:
        _write_atomic(
            self._active_file,
            json.dumps(actives, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def read_origins(self) -> dict[str, str]:
        """Hashes do ultimo `padrao/` baixado do R2 (vazio se nunca baixou)."""
        data = _read_text(self._origin_file)
        if not data:
            return {}
        try:
            loaded = json.loads(data)
        except ValueError:
            return {}
        if not isinstance(loaded, dict):
            return {}
        return {str(k): str(v).lower() for k, v in loaded.items() if isinstance(v, str)}

    def _write_origins(self, origins: dict[str, str]) -> None:
        _write_atomic(
            self._origin_file,
            json.dumps(origins, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def active_id(self, slot: PromptSlot) -> str:
        """Id em uso no slot (`Padrao` quando nada foi escolhido)."""
        return self._read_actives().get(slot.key, PROMPT_DEFAULT_ID)

    def read_padrao(self, slot: PromptSlot) -> str:
        """Conteudo do padrao do slot: `padrao/`, com a semente do app de reserva."""
        text = _read_text(self._padrao_dir / slot.file)
        if text and text.strip():
            return text
        seed = self._read_seed(slot.file)
        return seed or ""

    def read_padrao_file(self, name: str) -> str:
        """Conteudo de um arquivo de `padrao/` pelo nome (mesmo dos de `partes`).

        Sai na forma canonica (LF): o que estiver em CRLF no disco e o mesmo
        prompt, e comparar direto diria que mudou.
        """
        return canonical_text(_read_text(self._padrao_dir / name) or "")

    def read(self, slot: PromptSlot, id: str) -> str:
        """Conteudo de um prompt pelo id (`Padrao` resolve para `padrao/`)."""
        if id == PROMPT_DEFAULT_ID:
            return self.read_padrao(slot)
        text = _read_text(self._custom_file(slot, id))
        return text or ""

    def read_active(self, slot: PromptSlot) -> str:
        """Prompt que o app envia no slot: o escolhido, ou o padrao em branco."""
        return self.read(slot, self.active_id(slot)).strip() or self.read_padrao(slot)

    def entries(self) -> list[PromptEntry]:
        """Todas as linhas da tela: de cada slot, o `Padrao` e depois os customs.

        A lista sai sempre com o `Padrao` primeiro em cada slot — e a entrada
        que o app nunca deixa sobrescrever.
        """
        actives = self._read_actives()
        rows: list[PromptEntry] = []
        for slot in PROMPT_SLOTS:
            active = actives.get(slot.key, PROMPT_DEFAULT_ID)
            rows.append(PromptEntry(slot, PROMPT_DEFAULT_ID, active == PROMPT_DEFAULT_ID))
            custom_dir = self._custom_dir(slot)
            names: list[str] = []
            try:
                children = sorted(custom_dir.iterdir(), key=lambda item: item.name.casefold())
            except OSError:
                children = []
            for path in children:
                if path.is_file() and path.suffix.lower() == ".txt" and path.stem.strip():
                    names.append(path.stem)
            rows.extend(PromptEntry(slot, name, active == name) for name in names)
        return rows

    # ── escrita ───────────────────────────────────────────────────────

    def set_active(self, slot: PromptSlot, id: str) -> str | None:
        """Marca qual prompt o slot passa a usar; `None` quando gravou."""
        cleaned = sanitize_id(id)
        if not cleaned:
            return "Dê um nome válido para o prompt."
        if id != PROMPT_DEFAULT_ID and not self._custom_file(slot, id).is_file():
            return f"O prompt '{id}' não existe em {slot.label}."
        actives = self._read_actives()
        actives[slot.key] = id
        self._write_actives(actives)
        return None

    def save_custom(self, slot: PromptSlot, raw_id: str, text: str, *, overwrite: bool = True) -> str | None:
        """Grava um prompt do usuario; `None` quando gravou, senao o motivo.

        `overwrite=False` recusa id ja existente (botao SALVAR COMO). O id
        `Padrao` e sempre recusado: o padrao do app nao pode ser sobrescrito.
        """
        id = sanitize_id(raw_id)
        if not id:
            return "Dê um nome válido para o prompt."
        if is_default_id(id):
            return (
                "O prompt Padrão não pode ser sobrescrito; "
                "use Salvar como com outro nome."
            )
        error = self.validate(slot, text)
        if error:
            return error
        target = self._custom_file(slot, id)
        if target.is_file() and not overwrite:
            return f"Já existe um prompt chamado '{id}' em {slot.label}."
        _write_atomic(target, text)
        return None

    def save_as(self, slot: PromptSlot, raw_id: str, text: str) -> str | None:
        """Cria um id novo com o texto da caixa (botao SALVAR COMO)."""
        return self.save_custom(slot, raw_id, text, overwrite=False)

    def import_text(self, slot: PromptSlot, file_name: str, text: str, *, activate: bool = True) -> str | None:
        """Grava um `.txt` escolhido pelo usuario no slot e deixa em uso."""
        base = str(file_name or "").replace("\\", "/").split("/")[-1]
        id = sanitize_id(base.rsplit(".", 1)[0]) or "importado"
        if is_default_id(id):
            return "Renomeie o arquivo: 'Padrão' é o id do prompt padrão."
        error = self.save_custom(slot, id, text, overwrite=True)
        if error:
            return error
        if activate:
            return self.set_active(slot, id)
        return None

    def import_path(self, path: Path | str, slot: PromptSlot | None = None) -> tuple[PromptSlot | None, str | None]:
        """Importa um arquivo do disco; deduz o slot do nome e dos marcadores."""
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return None, f"Não foi possível ler o arquivo: {exc}"
        if not text.strip():
            return None, "O arquivo está vazio."
        target = slot or self.infer_slot(path.name, text)
        if target is None:
            return None, (
                "Não foi possível identificar para qual uso serve este prompt.\n"
                "Escolha o uso (Histórico, Oitiva ou Qualificação) e importe de novo."
            )
        return target, self.import_text(target, path.name, text)

    def infer_slot(self, file_name: str, text: str = "") -> PromptSlot | None:
        """Slot de um arquivo: pelo nome, depois pelos marcadores do conteudo."""
        base = sanitize_id(str(file_name or "").rsplit(".", 1)[0]).casefold()
        for slot in PROMPT_SLOTS:
            if slot.key.casefold() == base:
                return slot
        content = text or ""
        for slot in PROMPT_SLOTS:
            if any(marker in content for marker in slot.user_markers):
                return slot
        if "user" in base or "usuario" in base:
            return HISTORY_USER
        if "historico" in base or "history" in base:
            return HISTORY_SYSTEM
        if "oitiva" in base or "statement" in base:
            return STATEMENT_SYSTEM
        if "qualificacao" in base:
            return QUALIFICATION_SYSTEM
        return None

    # ── validacao ─────────────────────────────────────────────────────

    def validate(self, slot: PromptSlot, text: str) -> str | None:
        """`None` quando o texto serve para o slot; senao o motivo (para a tela)."""
        if not str(text or "").strip():
            return "o prompt está vazio"
        if len(text.encode("utf-8")) > MAX_PROMPT_BYTES:
            return f"o prompt passa de {MAX_PROMPT_BYTES // 1024} KiB"
        if slot.required_markers:
            if not any(marker in text for marker in slot.required_markers):
                return f"falta o marcador {slot.required_markers[0]}"
        return None

    def validate_defaults(self, files: dict[str, str]) -> str | None:
        """Valida o conjunto inteiro do download antes de gravar qualquer coisa."""
        missing = [name for name in ROOT_PROMPT_FILES if name not in files]
        if missing:
            return f"download incompleto: falta {', '.join(missing)}"
        for slot in PROMPT_SLOTS:
            error = self.validate(slot, files[slot.file])
            if error:
                return f"{slot.label}: {error}"
        return None

    # ── padrao do app ─────────────────────────────────────────────────

    def apply_defaults(self, files: dict[str, str], *, from_r2: bool = False) -> str | None:
        """Troca o padrao pelos textos baixados. **All-or-nothing**.

        Se um dos prompts reprovar, NADA e gravado: um download parcial
        deixaria o padrao com metade nova e metade antiga. Os prompts do
        usuario nao sao tocados — so `padrao/` e o registro de origem mudam.

        Arquivo cujo conteudo ja e igual NAO e reescrito: a data de
        modificacao de um prompt intocado e a prova de que o app nao mexeu
        nele, e um download idempotente nao pode deixar rastro.
        """
        error = self.validate_defaults(files)
        if error:
            return error
        self._padrao_dir.mkdir(parents=True, exist_ok=True)
        for name in ROOT_PROMPT_FILES:
            target = self._padrao_dir / name
            canonico = canonical_text(files[name])
            if target.is_file() and canonical_text(_read_text(target) or "") == canonico:
                continue
            _write_atomic(target, canonico)
        if from_r2:
            self._write_origins(
                {name: sha256_text(canonical_text(files[name])) for name in ROOT_PROMPT_FILES}
            )
        return None

    def is_same_as_origin(self, manifest_files: dict[str, str] | None) -> bool | None:
        """`True` quando o R2 ja e o que esta em `padrao/`.

        O manifesto do bucket so serve de atalho: quando o `origem.json` bate,
        nenhum prompt precisa ser lido. O registro sozinho NAO decide — num
        PC recem instalado ele ainda nao existe, e ai o R2 e igual ao
        executavel. Por isso, sem registro que prove a igualdade, devolvemos
        `None` e o chamador compara o conteudo de `padrao/` com o do R2.
        """
        if not manifest_files:
            return None
        origins = self.read_origins()
        if not origins:
            return None
        for name in ROOT_PROMPT_FILES:
            remote = manifest_files.get(name)
            if not remote:
                return False
            if origins.get(name) != remote:
                return False
        return True

    def is_same_content(self, remote: dict[str, str]) -> bool:
        """`True` quando cada prompt de `padrao/` ja e igual ao que veio do R2.

        Esta e a comparacao de verdade: nao depende de nenhum registro em
        disco, entao responde certo tambem na primeira execucao do app. Os
        arquivos de `partes` entram no conjunto mesmo nao tendo slot na tela,
        porque o app novo os traz junto no `padrao/`.
        """
        for name in ROOT_PROMPT_FILES:
            if self.read_padrao_file(name) != remote.get(name):
                return False
        return True


def changed_names(local: Iterable[str], remote: Iterable[str]) -> list[str]:
    """Nomes que diferem entre dois conjuntos — mensagem curta para a tela."""
    return sorted(set(remote) - set(local))


# ── API consumida por sig_app.py ───────────────────────────────────────

def default_store() -> PromptStore:
    """Store do usuario com a semente do app (a pasta `prompts/` do executavel)."""
    return PromptStore(prompts_dir(), seed_reader=read_bundled_prompt)


def read_bundled_prompt(file: str) -> str | None:
    """Le um prompt que veio com o app (a pasta `prompts/` do executavel).

    Mesma ordem de prioridade de `assistant_prompts._prompt_path`: a pasta ao
    lado do executavel primeiro, depois a copia embutida pelo PyInstaller.
    """
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "prompts" / file)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "prompts" / file)
    candidates.append(Path(__file__).resolve().parents[1] / "prompts" / file)
    for candidate in candidates:
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return None
    return None


def download_updates(
    store: PromptStore,
    *,
    base_url: str = R2_PROMPTS_BASE_URL,
    files: Iterable[str] = ROOT_PROMPT_FILES,
    timeout: float = 30.0,
) -> tuple[str, list[str]]:
    """Baixa o padrao do R2 e grava **somente se o conteudo for diferente**.

    Devolve `(situacao, mudancas)`, com situacao em:
    `atualizado` (gravou), `igual` (nao gravou nada — ja estava atualizado),
    `indisponivel` (faltou arquivo ou rede falhou).

    Regra do dono: prompt igual no R2 nao e baixado. O `manifest.json` da
    atalho para o caso comum (quando `origem.json` prova a igualdade, nenhum
    prompt e lido); nos demais casos a decisao sai do CONTEUDO de `padrao/`
    comparado com o do R2 — inclusive na primeira execucao do app, em que o
    registro ainda nao existe mas o conteudo ja e o mesmo.
    """
    wanted = tuple(files)
    manifest = fetch_manifest(base_url, timeout=min(timeout, 15.0))
    if manifest is not None:
        # Atalho: o registro em disco prova que o `padrao/` atual ja veio do
        # R2 e nao foi mexido. Nenhum prompt e lido.
        if store.is_same_as_origin(manifest["files"]) is True:
            return "igual", []

    downloaded: dict[str, str] = {}
    for name in wanted:
        try:
            downloaded[name] = fetch_text(f"{base_url.rstrip('/')}/{name}", timeout=timeout)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return "indisponivel", [f"{name}: {exc}"]

    unchanged = [
        name
        for name, text in downloaded.items()
        if store.read_padrao_file(name) == canonical_text(text)
    ]
    changed = [name for name in wanted if name not in unchanged]
    error = store.apply_defaults(downloaded, from_r2=True)
    if error:
        return "indisponivel", [error]
    if not changed:
        # Nada difere do que ja estava em `padrao/`. O app so registra a
        # origem (para o proximo clique sair em UM request) e nao toca nos
        # arquivos: o usuario ve "ja atualizado", nunca "8 alterados".
        return "igual", []
    return "atualizado", changed
