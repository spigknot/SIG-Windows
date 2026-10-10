# Mapa de modulos (onde vive cada responsabilidade)

Documento de navegacao para agentes de IA e pessoas. Regra de ouro: **cada
responsabilidade tem um unico dono**. Se voce precisa mudar um comportamento,
edite o modulo dono — nunca duplique logica em `sig_app.py`.

## Camadas (dependencia so aponta para baixo)

```
UI ............ sig_app.py, ffmpeg_tools_panel.py, ui_widgets.py, prompts_panel.py
Orquestracao .. sig_app.py (classe SigApp), vad_worker.py, batch_execution.py
Integracoes ... stt_clients.py, gemini_stt_client.py, http_clients.py,
                text_models.py, imei_lookup.py
Processamento . transcription_parsing.py, log_formatting.py, documents.py,
                reporting.py, qualification.py, name_database.py, audio_io.py,
                batch_errors.py, media_probe.py, diarias_protocolo.py,
                diarias_mapa.py
Config ........ providers.py, settings_store.py, prompt_store.py, diarias_profiles.py
Persistencia .. diarias_store.py
Dominio ....... domain_models.py
Ambiente ...... app_env.py
```

`domain_models`, `providers`, `settings_store`, `prompt_store`,
`transcription_parsing`, `text_models`, `http_clients`, `stt_clients`, `gemini_stt_client`,
`log_formatting`, `reporting`, `qualification`, `name_database`, `imei_lookup`,
`documents`, `media_files`, `audio_io`, `batch_errors`, `batch_execution` e
`app_env` **nao podem** importar `tkinter` nem `sig_app` (testado em
`tests/test_modularizacao_contrato.py`).

## Tabela de responsabilidades

| Modulo | Responsabilidade unica | Nao colocar aqui |
| --- | --- | --- |
| `app_env.py` | Identidade do app, caminhos (`settings_path`, `app_base_dir`), host da maquina e opcoes de paralelismo por CPU | Leitura/escrita de dados, Tkinter |
| `domain_models.py` | `AudioJob`, `Cancelled` e acessores do job (`job_transcript_text`, `audio_job_attr`...) | Regras de UI, rede |
| `providers.py` | Catalogo de provedores STT/texto (nomes, URLs, modelos), `DEFAULT_SETTINGS`, `API_KEY_IMPORT_FIELDS`, selecao atual (`selected_*`), fallbacks e validacao de chaves | Persistencia em disco, Tkinter |
| `settings_store.py` | Persistencia de `settings.json`: `load_settings`, `normalize_settings`, `save_settings`, `clamp_int` | Catalogo de provedores (importa de `providers`) |
| `prompt_store.py` | Regra dos prompts de historico/oitiva/qualificacao: slots, layout em `%APPDATA%\sig\Prompts`, `Padrao` protegido, importacao e download do padrao no R2 (all-or-nothing, so grava se mudar) | Tkinter, widgets, rede do app (o download usa `urllib` direto) |
| `transcription_parsing.py` | `ParsedTranscription` e parsing de respostas STT (JSON/texto/timestamps) | Chamadas de rede |
| `text_models.py` | Selecao e parsing de modelos de texto de IA (`selected_text_model*`, `extract_*`) | HTTP (usa `http_clients`) |
| `http_clients.py` | `GraniteUploader` e `TextModelClient` (transporte HTTP, cancelamento) | Formato de cada provedor STT |
| `stt_clients.py` | Protocolo STT: URLs, form fields, deteccao de provedor, REST/WS (Alibaba, MetaMuse, Deepgram...) | UI e persistencia |
| `gemini_stt_client.py` | Gemini 3.5 Transcribe: Files/Interactions REST, protocolo Live WebSocket, configuração e cancelamento | UI, persistência de chaves |
| `log_formatting.py` | Formatacao de comandos FFmpeg e de parametros para log; `format_bytes`, `format_duration`, `format_audio_total` | Execucao de FFmpeg |
| `media_probe.py` | Duracao de midia: cabecalho do WAV (barato) e sonda externa `ffprobe`/`ffmpeg -i` (para o resumo antes do envio) | UI, contagem de lote |
| `batch_errors.py` | Rotulos curtos dos erros do lote (uma linha viva por TIPO de erro, com contagem) e texto das linhas "ja estavam prontos/compactados" | UI, contagem de estado |
| `batch_execution.py` | Orquestracao de futures do lote com cancelamento imediato (`cancellable_executor`, `iter_completed`, `cancellable_join`) e a divisao equilibrada da fila do VAD entre processos (`split_balanced`) | Regra de negocio, rede |
| `reporting.py` | HTML de relatorio e de status ao vivo (`html_document`, `write_html_report`, `build_live_html`) | Geracao de DOCX/PDF |
| `documents.py` | DOCX a partir dos modelos Word, PDF via Word, previa e clipboard | Regras de transcricao |
| `media_files.py` | Extensoes suportadas, MIME e deteccao de tipo (`is_video_file`) | Processamento de midia |
| `audio_io.py` | Conversao PCM <-> WAV da captura ao vivo | Captura/rede |
| `imei_lookup.py` | Consulta e historico de IMEI (JSON local) | UI |
| `name_database.py` | Base de nomes: extracao, normalizacao, chave fonetica | UI |
| `qualification.py` | Qualificacao de ocorrencias: parsing de JSON, labels, status | UI |
| `diarias_protocolo.py` | Extracao dos campos dos PDFs de protocolo, talão, holerite e mês/ano do cabeçalho da escala | UI, persistencia |
| `diarias_mapa.py` | Validação dos dados e preenchimento do modelo Excel de mapa de diária, preservando fontes, fórmulas e o formato `.xlsx` | UI, extração de PDFs |
| `diarias_workflow.py` | Nove campos obrigatórios, geração conjunta e plano de impressão (vias/ordem/duplex do mapa/primeira página da escala/talão condicionado a Meios Próprios) | UI, persistência |
| `pdf_printing.py` | Impressoras Windows e envio de PDFs ao GDI em processo isolado | Dados do perfil, Tkinter |
| `diarias_store.py` | Persistencia local dos perfis/seleção de Diárias, UFESP, pasta de saída e valores/PDFs ativos do holerite e da escala | Leitura de PDF, UI |
| `diarias_profiles.py` | Campos e validação dos perfis de Diárias, nomes e relação classe/padrão | UI, persistência |
| `diarias_profiles_panel.py` | Formulário, seletor e tabela dos perfis em Configurações → Policial → Diárias | Regras de documento, persistência em disco |
| `ui_widgets.py` | Widgets reutilizaveis (`create_tooltip`, `PreviewIconButton`) | Regra de negocio |
| `ffmpeg_tools_panel.py` | Aba FFmpeg: conversao, corte, juncao, aceleracao, player, linha do tempo | STT/transcricao |
| `ffmpeg_recovery.py` | Checkpoints locais, integridade de entradas e reutilização das etapas FFmpeg concluídas | UI, execução de FFmpeg |
| `smart_cut_planner.py` | Intervalos e fronteiras de GOP do SmartCut pelos timestamps dos pacotes | UI, execução de FFmpeg |
| `smart_insert_planner.py` | Duração e limites de pacotes/amostras do Smart Insert de áudio | UI, execução de FFmpeg |
| `smart_insert_flac.py` | Remontagem dos headers e metadados FLAC, preservando subframes comprimidos | UI, encode de áudio |
| `smart_insert_wave.py` | Montagem WAV/RF64 por cópia de bytes PCM com corte por amostra | UI, encode de áudio |
| `prompts_panel.py` | Aba Prompts: lista de selecao com id, caixa de texto, Salvar / Salvar como / Importar .txt / Baixar atualizados | A regra dos prompts (esta em `prompt_store`), rede |
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
- **Mudar os prompts do app** (slot, marcador, protecao do `Padrao`, download
  do R2): `prompt_store.py`; a tela e `prompts_panel.py`; a escolha e lida em
  `SigApp._prompt_ativo` (`sig_app.py`).
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

## Historico

- **2026-09**: modularizacao conservadora — `sig_app.py` de 21.838 para 13.380
  linhas; 18 modulos extraidos verbatim. Relatorio em linguagem simples (o que
  mudou, vantagens, provas e pendencias):
  `docs/maintenance/refatoracao-2026-09.md`.
- **2026-09**: aba Prompts — `prompt_store.py` (regra) e `prompts_panel.py`
  (tela) entram no mapa; o app le o prompt escolhido por
  `SigApp._prompt_ativo`. Design: `docs/agents/design-aba-prompts.md`.
