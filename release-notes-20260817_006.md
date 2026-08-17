# SIG Windows 20260817_006

## Correção do WebSocket do Scribe (ElevenLabs Realtime)

**Sintoma**: o modo ao vivo conectava e entrava em loop de reconexão
("Reconectando ao streaming do Scribe...") mesmo com o servidor respondendo.

**Causa raiz**: o websocket-client 1.9.0 mudou o retorno de `WebSocketApp.send`
— no sucesso ele retorna `None` (e levanta exceção na falha). O envio do Scribe
usava `bool(app.send(...))`, e `bool(None)` é `False` — ou seja, **todo envio
era tratado como falha**, disparando a reconexão em loop (o servidor até
recebia o áudio).

**Correção**: o envio agora usa try/except — sucesso sem exceção = `True`;
falha real (socket fechado) = `False`. Testado contra o servidor real: 30
blocos enviados com sucesso e sessão estável.

Também nesta versão: log do motivo de fechamento do Scribe (código + erro) no
terminal para diagnóstico futuro.
