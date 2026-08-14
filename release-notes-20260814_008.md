# SIG Windows 20260814_008

Pacote completo para instalação nova ou reparo.

## Incremental v2 — atualização por diff

- A incremental agora viaja apenas com o que mudou desde a versão anterior
  (diff por hash de arquivo) + `removidos.txt` com o que saiu. Tamanho típico
  caiu de ~37,5 MB para ~4–15 MB.
- `SigUpdater.exe` só é incluído quando o updater muda.
- O updater aplica o diff com backup individual por arquivo, rollback
  automático e validação de inicialização (harness de falhas 7/7).

## Novidades do app

- Botão **Reparar instalação**: baixa o pacote completo mais recente do
  GitHub e reinstala por cima (rollback automático em caso de falha).
- Correções anteriores já incluídas (painel de tarefa única, fluxo
  "Qualificando e gerando documento", log sem "0%", botão Visualizar com
  janela de zoom 100%, prévia com tamanho físico real).

## Notas

- Instalação: extraia o ZIP e execute `sig.exe` (mantenha `_internal` ao lado).
- Atualização automática: incremental pelo Drive.
