# Mapa de modulos (onde vive cada responsabilidade)

Documento de navegacao para agentes de IA e pessoas. Regra de ouro: **cada
responsabilidade tem um unico dono**. Se voce precisa mudar um comportamento,
edite o modulo dono — nunca duplique logica em `sig_app.py`.

## Camadas (dependencia so aponta para baixo)

```
UI ............ sig_app.py, ffmpeg_tools_panel.py, ui_widgets.py
Orquestracao .. sig_app.py (classe SigApp), vad_worker.py
Integracoes ... stt_clients.py, http_clients.py, text_models.py, imei_lookup.py
Processamento . transcription_parsing.py, log_formatting.py, documents.py,
                reporting.py, qualification.py, name_database.py, audio_io.py
Config ........ providers.py, settings_store.py
Dominio ....... domain_models.py
Ambiente ...... app_env.py
```

`domain_models`, `providers`, `settings_store`, `transcription_parsing`,
`text_models`, `http_clients`, `stt_clients`, `log_formatting`, `reporting`,
`qualification`, `name_database`, `imei_lookup`, `documents`, `media_files`,
`audio_io` e `app_env` **nao podem** importar `tkinter` nem `sig_app`
(testado em `tests/test_modularizacao_contrato.py`).

## Tabela de responsabilidades

| Modulo | Responsabilidade unica | Nao colocar aqui |
| --- | --- | --- |
| `app_env.py` | Identidade do app, caminhos (`settings_path`, `app_base_dir`), host da maquina e opcoes de paralelismo por CPU | Leitura/escrita de dados, Tkinter |
| `domain_models.py` | `AudioJob`, `Cancelled` e acessores do job (`job_transcript_text`, `audio_job_attr`...) | Regras de UI, rede |
| `providers.py` | Catalogo de provedores STT/texto (nomes, URLs, modelos), `DEFAULT_SETTINGS`, `API_KEY_IMPORT_FIELDS`, selecao atual (`selected_*`), fallbacks e validacao de chaves | Persistencia em disco, Tkinter |
| `settings_store.py` | Persistencia de `settings.json`: `load_settings`, `normalize_settings`, `save_settings`, `clamp_int` | Catalogo de provedores (importa de `providers`) |
| `transcription_parsing.py` | `ParsedTranscription` e parsing de respostas STT (JSON/texto/timestamps) | Chamadas de rede |
| `text_models.py` | Selecao e parsing de modelos de texto de IA (`selected_text_model*`, `extract_*`) | HTTP (usa `http_clients`) |
| `http_clients.py` | `GraniteUploader` e `TextModelClient` (transporte HTTP, cancelamento) | Formato de cada provedor STT |
| `stt_clients.py` | Protocolo STT: URLs, form fields, deteccao de provedor, REST/WS (Alibaba, MetaMuse, Deepgram...) | UI e persistencia |
| `log_formatting.py` | Formatacao de comandos FFmpeg e de parametros para log; `format_bytes`, `format_duration` | Execucao de FFmpeg |
| `reporting.py` | HTML de relatorio e de status ao vivo (`html_document`, `write_html_report`, `build_live_html`) | Geracao de DOCX/PDF |
| `documents.py` | DOCX a partir dos modelos Word, PDF via Word, previa e clipboard | Regras de transcricao |
| `media_files.py` | Extensoes suportadas, MIME e deteccao de tipo (`is_video_file`) | Processamento de midia |
| `audio_io.py` | Conversao PCM <-> WAV da captura ao vivo | Captura/rede |
| `imei_lookup.py` | Consulta e historico de IMEI (JSON local) | UI |
| `name_database.py` | Base de nomes: extracao, normalizacao, chave fonetica | UI |
| `qualification.py` | Qualificacao de ocorrencias: parsing de JSON, labels, status | UI |
| `ui_widgets.py` | Widgets reutilizaveis (`create_tooltip`, `PreviewIconButton`) | Regra de negocio |
| `ffmpeg_tools_panel.py` | Aba FFmpeg: conversao, corte, juncao, aceleracao, player, linha do tempo | STT/transcricao |
| `sig_app.py` | UI principal (`SigApp`), abas/dialogs e orquestracao; `main()` | Implementacao de dominio (reexporta dos modulos) |

## Receitas rapidas

- **Adicionar/alterar provedor STT**: constantes e defaults em `providers.py`;
  form fields e transporte em `stt_clients.py`; parsing em
  `transcription_parsing.py`; regras de idioma em `stt_provider_rules.py`.
- **Adicionar uma configuracao**: chave + default em `DEFAULT_SETTINGS`
  (`providers.py`); normalizacao em `settings_store.normalize_settings`;
  campo na aba Configuracoes em `sig_app.py`.
- **Mudar formato de log de comando FFmpeg**: `log_formatting.py`.
- **Mudar texto de relatorio/status**: `reporting.py`.
- **Mudar modelo Word / PDF**: `documents.py` (+ pasta `modelos/`).
- **Onde esta o estado da UI**: atributos de `SigApp` em `sig_app.py`; o
  estado dos jobs em `domain_models.AudioJob`; tarefas em lote em
  `ffmpeg_tools_panel.FfmpegTaskTracker`.

## Contrato de re-export (nao quebrar)

`sig_app.py` mantem blocos `from <modulo> import (...)  # noqa: F401` logo apos
os imports locais. Eles existem para que `from sig_app import X` continue
funcionando (testes e codigo historico). Sao verificados por:

- `tests/test_modularizacao_contrato.py::ReexportContractTest` — o nome
  reexportado e o **mesmo objeto** do modulo de origem e nao ha duplicata;
- `tests/test_modularizacao_contrato.py::CamadasTest` — camadas nao se
  misturam;
- `tests/test_modularizacao_contrato.py::SettingsRoundTripTest` — nenhum
  default de settings se perde.

Ao extrair codigo novo de `sig_app.py`, repita o padrao: mover verbatim,
adicionar re-export, rodar a suite completa.
