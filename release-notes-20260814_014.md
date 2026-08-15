# SIG Windows 20260814_014

Pacote completo para instalação nova ou reparo.

## Atualização por sincronização de arquivos também no botão do SIG

- O botão de atualização do SIG agora consulta o manifesto assinado, baixa
  **apenas os arquivos que mudaram** (com progresso por arquivo no próprio
  botão) e aplica com rollback protegido. O incremental ZIP continua como
  contingência quando o manifesto de sincronização não estiver disponível.

> Instalação: extraia o ZIP e execute `sig.exe` (mantenha `_internal` ao lado).
> Atualização: botão "Atualização: N arquivo(s)" no SIG, ou `SigUpdater.exe`.
