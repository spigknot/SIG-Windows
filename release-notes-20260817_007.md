# SIG Windows 20260817_007

Pacote de correções do modo ao vivo do Scribe (ElevenLabs Realtime).

## Correções

- **WebSocket em loop de reconexão**: o websocket-client 1.9.0 passou a
  retornar `None` no envio bem-sucedido, e o app tratava `bool(None)` como
  falha — todo chunk parecia falhar e a conexão reconectava em loop.
  O envio agora usa try/except (sucesso = sem exceção).

- **Texto se perdendo (só a última frase)**: o Scribe v2 envia cada frase
  finalizada como `committed_transcript` (o app só acumulava `final_transcript`,
  que o v2 não envia no fluxo VAD). O `committed_transcript` agora acumula no
  texto — a transcrição cresce frase a frase e nada se perde.

- **Finalização lenta (~30s)**: a espera pela confirmação final do servidor
  era de 20s (e depois 10s). Como o VAD do servidor já commita as frases
  durante as pausas, o silêncio final não gera novo `committed` — o app
  esperava à toa. Agora espera 3s e finaliza com o texto completo recebido.

- **`include_timestamps=true` removido**: era enviado hardcoded na query,
  mesmo sem o recurso de horários habilitado no app.

- **Diagnóstico**: o log agora mostra o código/motivo do fechamento do
  WebSocket ("Scribe fechou a conexão (código X): ...") para futuras falhas.
