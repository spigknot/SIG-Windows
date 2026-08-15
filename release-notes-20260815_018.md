# SIG Windows 20260815_018

Pacote completo para instalação nova ou reparo.

## Integração Deepgram Nova 3 (REST + WebSocket)

- Nova caixa "Chave API do Deepgram" e "Palavras-chave do Deepgram" nas
  configurações; chave preenchida libera o "Deepgram Nova 3" na lista de
  transcrição.
- REST: áudio direto (sem multipart) com header Token e parâmetros na URL.
- WebSocket: streaming ao vivo com parciais, acúmulo das falas finais,
  finalização via CloseStream + speech_final e reconexão com buffer de 8s.
- Palavras-chave (keyterm) para priorizar termos locais (ex.: Taguaí).
- Correções de campo: 401 na gravação do microfone, language duplicado na
  query do WS (400) e pronto via on_open (o Metadata demora ~12s).
