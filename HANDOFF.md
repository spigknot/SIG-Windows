# SIG Windows: handoff técnico

## Fonte da verdade

Leia `AGENTS.md` e `UPDATE.md` antes de alterar, compilar ou publicar o app.
O código principal está em `src/sig_app.py`; o atualizador independente está
em `updater_v2/updater.py`.

## Atualizações

- O canal incremental vigente é o manifesto assinado `sync_manifest.json` no
  Cloudflare R2.
- Gere o package com `scripts/release.py release --version <versão> --incremental`.
- Publique somente o package com `scripts/sync_r2.py --package
  release/generated/<versão>/package --version <versão>`.
- Publique o pacote full e os instaladores como assets da release do GitHub.
- Google Drive, ZIP incremental antigo e scripts de upload antigos estão fora
  do fluxo e não devem voltar ao projeto.

## Estrutura de instalação

Uma instalação completa contém `sig.exe`, `SigUpdater.exe`, `_internal`,
`ffmpeg.exe`, `ffplay.exe`, `vad_worker.py`, `vad_deps`, `prompts` e `modelos`.
Não distribua somente `sig.exe`.

## Verificação

Use o Python 3.11 aprovado e execute os testes antes de publicar:

```powershell
python scripts\release.py tests
python scripts\release.py updater-v2-test --package-zip <pacote-full.zip> --updater <SigUpdater.exe>
```

Não versione `release/r2_config.json`, `release/update_private_key.pem`,
`settings.json`, caches, logs ou saídas de build.
