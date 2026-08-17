# SIG Windows 20260817_009

## Log de download com uma linha por arquivo

O log da atualização agora mostra **uma linha fixa por arquivo**, editada no
lugar a cada atualização de porcentagem (padrão do log do FFmpeg) — antes,
cada porcentagem criava uma linha nova e o log acumulava dezenas de linhas.

Ao concluir, a linha fica **verde** com o nome do arquivo.

## Segurança (Android) — referência

- Chaves de API removidas do APK do Android (AssemblyAI, ElevenLabs e IMEI
  check): os campos agora nascem vazios e são digitados nas configurações.
