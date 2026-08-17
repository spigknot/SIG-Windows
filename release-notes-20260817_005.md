# SIG Windows 20260817_005

## Diagnóstico do WebSocket do Scribe (ElevenLabs Realtime)

O modo ao vivo (WebSocket) pode falhar ao conectar. Esta versão adiciona o
**motivo exato do fechamento da conexão** no log:

- `Scribe fechou a conexão (código X): <motivo>` — o código e a razão enviados
  pelo servidor (1000 = fechamento normal, 1006 = conexão interrompida, etc.).
- `Erro do Scribe: <detalhe>` — o erro real do transporte (DNS, TLS, handshake).

Com isso, o próximo teste do modo ao vivo mostra o motivo exato no terminal do
app, permitindo a correção definitiva.
