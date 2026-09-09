"""Dataclasses de dominio e acessores do AudioJob.

AudioJob = um arquivo em processamento (conversao/VAD/transcricao).
Cancelled = excecao de cancelamento usada por uploaders/clientes HTTP.
NAO confundir com 'modelos de IA' (esses ficam em text_models/settings_store).
Sem Tkinter, sem rede, sem I/O."""

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


class Cancelled(Exception):
    pass
@dataclass
class AudioJob:
    original_path: Path
    original_name: str
    stem: str
    mode: str
    upload_path: Path | None = None
    converted_path: Path | None = None
    txt_path: Path | None = None
    raw_path: Path | None = None
    log_path: Path | None = None
    vad_output_path: Path | None = None
    vad_input_bytes: int = 0
    vad_output_bytes: int = 0
    vad_elapsed: float = 0.0
    vad_speech_duration: float = 0.0
    vad_total_duration: float = 0.0
    vad_error: str = ""
    conversion_elapsed: float = 0.0
    status: str = "Aguardando"
    transcription: str = ""
    error: str = ""
    model_name: str = "Modelo 1"
    # Multi-modelo SEM limite: listas paralelas (índice 0 = modelo 2).
    model_names: list[str] = field(default_factory=list)
    transcripts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    txt_paths: list[Path] = field(default_factory=list)
    raw_paths: list[Path] = field(default_factory=list)
def job_transcript_text(job: AudioJob) -> str:
    transcript = job.transcription
    if not transcript and job.txt_path and job.txt_path.exists():
        transcript = job.txt_path.read_text(encoding="utf-8", errors="replace")
    return transcript or ""
def job_problem_reason(job: AudioJob, transcript: str) -> str:
    clean = transcript.strip()
    if job.error:
        return "Erro na transcrição/conversão"
    if not clean:
        return "Transcrição vazia"
    sent_name = job.upload_path.name if job.upload_path else ""
    if sent_name:
        first_line = next((line.strip() for line in clean.splitlines() if line.strip()), "")
        if clean == sent_name or first_line == sent_name:
            return "Servidor retornou o nome do arquivo enviado"
    return ""
_JOB_LIST_PLURALS = {
    "transcription": "transcripts",
    "error": "errors",
    "txt_path": "txt_paths",
    "raw_path": "raw_paths",
    "model_name": "model_names",
}
def audio_job_attr(job: AudioJob, base: str, index: int):
    """Lê um atributo por modelo: índice 1 = campo principal; 2+ = lista (índice 0 = modelo 2)."""
    if index == 1:
        return getattr(job, base)
    values = getattr(job, _JOB_LIST_PLURALS.get(base, f"{base}s"))
    list_index = index - 2
    return values[list_index] if list_index < len(values) else None
def audio_job_set(job: AudioJob, base: str, index: int, value):
    """Grava um atributo por modelo, estendendo a lista quando necessário."""
    if index == 1:
        setattr(job, base, value)
        return
    values = getattr(job, _JOB_LIST_PLURALS.get(base, f"{base}s"))
    list_index = index - 2
    while len(values) <= list_index:
        values.append("" if base in ("transcription", "error") else None)
    values[list_index] = value
def job_transcript_for_model(job: AudioJob, model_index: int) -> str:
    if model_index == 1:
        return job_transcript_text(job)
    transcript = audio_job_attr(job, "transcription", model_index) or ""
    path = audio_job_attr(job, "txt_path", model_index)
    if not transcript and path and path.exists():
        transcript = path.read_text(encoding="utf-8", errors="replace")
    return transcript or ""
def job_problem_reason_for_model(job: AudioJob, transcript: str, model_index: int) -> str:
    clean = transcript.strip()
    error = audio_job_attr(job, "error", model_index) or ""
    if error:
        return "Erro na transcrição/conversão"
    if not clean:
        return "Transcrição vazia"
    sent_name = job.upload_path.name if job.upload_path else ""
    if sent_name:
        first_line = next((line.strip() for line in clean.splitlines() if line.strip()), "")
        if clean == sent_name or first_line == sent_name:
            return "Servidor retornou o nome do arquivo enviado"
    return ""
