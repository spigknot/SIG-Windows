# SIG Windows 20260817_001

Robustez do pipeline de build, publicação e atualização (reparo Better Harness).

## Novidades

- **Publicação sync transacional**: a retomada só reutiliza arquivo do Drive comprovadamente
  idêntico (tamanho + SHA-256 remoto) e o manifesto novo é publicado **antes** das remoções —
  uma falha no meio preserva o manifesto anterior íntegro e instalável.
- **Log de atualização correlacionado**: cada aplicação sync registra versão + identificador
  de tentativa (`sync v=<versão> run=<id>`) no início, sucesso e falha — diagnósticos de
  tentativas distintas ficam distinguíveis no mesmo log.
- **Ambiente de build blindado**: o gate oficial falha com diagnóstico acionável quando o
  Python/PyInstaller divergem do aprovado (3.11.0 / 6.21.0), e o `requirements.txt` fixa as
  versões de build, assinatura e publicação.
- **Docs alinhados à rota vigente**: AGENTS.md, README e HANDOFF descrevem a sincronização por
  arquivo como mecanismo atual e marcam o pacote ZIP como histórico.
- Instalador e conversões paralelas por núcleos seguem como na versão anterior.

Pacote full para instalação nova, incluindo runtime onedir, FFmpeg, VAD e SigUpdater.
