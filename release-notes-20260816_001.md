# SIG Windows 20260816_001

Paridade STT com o app Android (idioma, diarização e AssemblyAI assíncrona).

## Novidades

- **Seletor de idioma por provedor** — opções `multi` / idioma padrão / en / es / `custom` com
  persistência independente por modelo (Deepgram padrão pt-BR; AssemblyAI, ElevenLabs e Grok
  padrão pt). O diálogo "custom" aceita um ou mais códigos separados por vírgula, valida contra
  a lista oficial de cada provedor (sem fechar com código inválido) e tem o botão "?" com a
  lista completa.
- **Parâmetros de idioma idênticos ao Android**: Deepgram `language=` (REST e WS);
  AssemblyAI REST `language_code`/`language_detection` e WS `language_codes` repetido;
  ElevenLabs REST `language_code` e WS `language_code`+`secondary_languages`; Grok `language`
  (multi/custom com vários omitem o parâmetro).
- **Diarização por provedor**: Deepgram `diarize_model=latest` (o `diarize=true` foi removido);
  AssemblyAI `speaker_labels=true`+`punctuate=true` no REST e `speaker_labels=true` no WS;
  ElevenLabs REST `diarize=true` (WS não envia); Grok `diarize=true` no form e na query do WS.
- **AssemblyAI assíncrona**: arquivos com 2 minutos ou mais vão por upload → submit →
  consulta a cada 3 segundos, com o estado na árvore de arquivos e cancelamento respeitado.

## Interno

- Novo módulo `src/stt_provider_rules.py` com as regras de idioma/diarização por provedor
  (espelho exato do Android) + 26 testes novos; suíte total 163/163.
- O fluxo ao vivo (WebSocket) dos quatro provedores passou a usar as mesmas regras.

Pacote full para instalação nova, incluindo runtime onedir, FFmpeg, VAD e SigUpdater.
