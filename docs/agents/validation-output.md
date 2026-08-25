# Contrato de saída dos gates

Este é o contrato único para preservar contexto durante testes, build e
publicação. `UPDATE.md` aponta para este arquivo; não replique contagens ou
formatos de saída em outros documentos.

## Modo quiet

- Sucesso: uma linha curta `PASS: <gate> ...` com somente versão, contagem ou
  digest indispensável para decidir o próximo passo.
- Falha: código diferente de zero, uma mensagem curta e o caminho do log
  completo. O terminal não deve despejar o log inteiro.
- Os logs completos ficam em `build/`, `release/generated/<versão>/` ou no
  caminho informado pelo comando. Eles não são material de commit.

## Comandos

```text
python scripts\release.py tests --quiet
python scripts\release.py validate --quiet
python scripts\release.py updater-v2-test --quiet
python scripts\release.py preflight --quiet
python scripts\release.py ui-smoke --quiet
python scripts\release.py syntax --quiet
python scripts\release.py release --version YYYYMMDD_NNN --incremental --quiet
python scripts\build_dev.py --quiet
.\updater_v2\build.ps1 -Quiet
python scripts\sync_r2.py --package release/generated/<versão>/package --version <versão> --quiet
```

Sem `--quiet`/`-Quiet`, o comando pode mostrar progresso e diagnóstico para
uso interativo. A saída verbosa não altera artefatos nem critérios de sucesso.

## Regras de validação

1. O silêncio em sucesso nunca pode transformar falha em sucesso.
2. Um wrapper que usa pipeline deve habilitar `pipefail` ou propagar
   explicitamente o código de saída do processo principal.
3. Um diagnóstico limitado deve preservar o arquivo integral para investigação.
4. Testes devem cobrir tanto o resumo quiet quanto a falha com log preservado.
5. O gate `python scripts\release.py syntax --quiet` roda antes dos testes e
   do harness caros e não deve virar dependência do runtime do SIG.
