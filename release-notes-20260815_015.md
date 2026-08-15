# SIG Windows 20260815_015

Pacote completo para instalação nova ou reparo.

- Primeira publicação com o mecanismo de atualização por sincronização de
  arquivos ativo nos dois caminhos (botão do SIG e SigUpdater.exe).
- A atualização baixa apenas os arquivos alterados, com progresso por
  arquivo na tela, e aplica com rollback protegido. O incremental ZIP e o
  pacote completo do GitHub seguem disponíveis como contingência.

> Instalação: extraia o ZIP e execute `sig.exe` (mantenha `_internal` ao lado).
> Atualização: botão "Atualização: N arquivo(s)" no SIG, ou `SigUpdater.exe`.
