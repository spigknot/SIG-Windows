# SIG Windows 20260814_010

Pacote completo para instalação nova ou reparo.

- Corrige o fluxo de atualização do SIG para aceitar a incremental por diff
  (formato com `removidos.txt`), eliminando o erro "componentes obrigatórios
  ausentes" ao baixar a atualização.
- Incremental 010 gerada por diff: 4,5 MB (redução de ~88% vs formato antigo).

> Instalação: extraia o ZIP e execute `sig.exe` (mantenha `_internal` ao lado).
> Atualização automática: incremental pelo Drive.
