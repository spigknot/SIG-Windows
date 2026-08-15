# SIG Windows 20260815_017

Pacote completo para instalação nova ou reparo.

- Download da atualização em **paralelo** (4 arquivos por vez) com linhas
  vivas no log: cada arquivo mostra a porcentagem atualizando a cada 100ms
  e fica verde ao concluir.
- Botão de atualização enxuto: mostra apenas a fase ("Baixando arquivos...",
  "Reiniciando..."); os detalhes ficam no log.
- Os executáveis (`sig.exe` e `SigUpdater.exe`) também são anexados aqui
  como assets, usados pela sincronização quando o Drive bloquear o download.

> Instalação: extraia o ZIP e execute `sig.exe` (mantenha `_internal` ao lado).
> Atualização: botão "Atualizar" no SIG, ou `SigUpdater.exe`.
