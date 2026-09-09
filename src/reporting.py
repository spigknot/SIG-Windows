"""Relatorios HTML (arquivo final e janela ao vivo).

Monta o documento a partir dos AudioJob; nao grava arquivos (quem chama escreve).
Sem Tkinter, sem rede."""

import html
import os
from domain_models import (
    AudioJob,
    job_problem_reason,
    job_problem_reason_for_model,
    job_transcript_for_model,
)
from pathlib import Path


def html_document(title: str, rows: list[str], headers: tuple[str, ...], stats: list[tuple[str, str]] | None = None) -> str:
    header_cells = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    stats_html = ""
    if stats:
        stats_html = (
            '<div class="stats">'
            + "".join(
                f"<span><strong>{html.escape(label)}:</strong> {html.escape(value)}</span>"
                for label, value in stats
            )
            + "</div>"
        )
    if not rows:
        rows = [
            "<tr>"
            f"<td colspan=\"{len(headers)}\">Nenhum item nesta tabela.</td>"
            "</tr>"
        ]
    # A 1ª coluna (nome do arquivo) reserva espaço fixo (20%); as demais
    # colunas de transcrição/modelo dividem igualmente o restante (larguras idênticas).
    n_content = max(1, len(headers) - 1)
    filename_width = 20
    content_width = (100.0 - filename_width) / n_content
    colgroup = (
        f'<colgroup><col style="width: {filename_width}%">'
        + "".join(f'<col style="width: {content_width:.2f}%">' for _ in range(n_content))
        + "</colgroup>"
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{
  font-family: Arial, sans-serif;
  background: #101417;
  color: #e8f4f2;
  margin: 24px;
}}
h1 {{ font-size: 24px; margin: 0 0 18px; }}
.stats {{
  color: #9aa9ad;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  font-size: 12px;
  margin: -6px 0 14px;
}}
.stats span {{ white-space: nowrap; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{
  border: 1px solid #334047;
  padding: 10px;
  vertical-align: top;
}}
th {{ background: #182127; text-align: left; }}
td:first-child {{
  font-family: Consolas, monospace;
  color: #9ee7ff;
  word-break: break-word;
}}
td {{ white-space: pre-wrap; line-height: 1.45; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
{stats_html}
<table>
{colgroup}
<thead><tr>{header_cells}</tr></thead>
<tbody>
{os.linesep.join(rows)}
</tbody>
</table>
</body>
</html>
"""


def write_html_report(jobs: list[AudioJob], html_path: Path, stats: list[tuple[str, str]] | None = None) -> Path:
    valid_rows: list[str] = []
    problem_rows: list[str] = []

    # O número de colunas vem dos modelos efetivamente registrados nos jobs,
    # e não de uma suposição fixa de dois modelos. Isso mantém o relatório
    # compatível com lotes antigos e permite 2 ou 3 modelos novos.
    model_names: list[str] = []
    for job in jobs:
        names = ([job.model_name] if job.model_name else []) + list(job.model_names)
        for name in names:
            name = str(name or "").strip()
            if name and name not in model_names:
                model_names.append(name)
    multi_model = len(model_names) > 1

    for job in jobs:
        transcripts = [job_transcript_for_model(job, index) for index in range(1, len(model_names) + 1)]
        problems = [
            job_problem_reason_for_model(job, transcript, index)
            for index, transcript in enumerate(transcripts, start=1)
        ]
        if multi_model:
            # Uma linha continua útil quando ao menos um modelo respondeu;
            # o retorno ausente fica marcado na coluna correspondente e é
            # detalhado também no relatório separado de problemas.
            if any(not problem for problem in problems):
                cells = [f"<td>{html.escape(job.original_name)}</td>"]
                cells.extend(
                    f"<td>{html.escape(transcript) if not problem else '<em>Falhou</em>'}</td>"
                    for transcript, problem in zip(transcripts, problems)
                )
                valid_rows.append("<tr>" + "".join(cells) + "</tr>")
            for index, (problem, transcript) in enumerate(zip(problems, transcripts), start=1):
                if not problem:
                    continue
                error = getattr(job, "error" if index == 1 else f"error_{index}", "")
                problem_rows.append(
                    "<tr>"
                    f"<td>{html.escape(job.original_name)}</td>"
                    f"<td>{html.escape(model_names[index - 1])}</td>"
                    f"<td>{html.escape(problem)}</td>"
                    f"<td>{html.escape(error or transcript or '(sem retorno)')}</td>"
                    "</tr>"
                )
            continue

        transcript = transcripts[0] if transcripts else ""
        problem = problems[0] if problems else job_problem_reason(job, transcript)
        if problem:
            details = job.error or transcript or "(sem retorno)"
            sent_name = job.upload_path.name if job.upload_path else "(não enviado)"
            problem_rows.append(
                "<tr>"
                f"<td>{html.escape(job.original_name)}</td>"
                f"<td>{html.escape(sent_name)}</td>"
                f"<td>{html.escape(problem)}</td>"
                f"<td>{html.escape(details)}</td>"
                "</tr>"
            )
        else:
            valid_rows.append(
                "<tr>"
                f"<td>{html.escape(job.original_name)}</td>"
                f"<td>{html.escape(transcript)}</td>"
                "</tr>"
            )

    headers = (
        ("Arquivo original", *model_names)
        if multi_model
        else ("Arquivo original", "Transcrição")
    )
    html_path.write_text(
        html_document("Transcrições", valid_rows, headers, stats),
        encoding="utf-8",
    )
    problem_path = html_path.with_name("transcricoes_com_problemas.html")
    problem_path.write_text(
        html_document(
            "Transcrições com problemas",
            problem_rows,
            (
                ("Arquivo original", "Modelo", "Motivo", "Retorno")
                if multi_model
                else ("Arquivo original", "Arquivo enviado", "Motivo", "Retorno")
            ),
            stats,
        ),
        encoding="utf-8",
    )
    return problem_path


def build_live_html(text: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Transcrição ao vivo</title>
<style>
body {{
  font-family: Arial, sans-serif;
  background: #101417;
  color: #e8f4f2;
  margin: 24px;
}}
h1 {{ font-size: 24px; margin: 0 0 18px; }}
.box {{
  border: 1px solid #334047;
  background: #182127;
  padding: 16px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}}
</style>
</head>
<body>
<h1>Transcrição ao vivo</h1>
<div class="box">{html.escape(text)}</div>
</body>
</html>
"""
