# Sincronização por arquivo (mecanismo principal de atualização)

Design aprovado em 2026-08-14. O mecanismo de ZIP diff (INCREMENTAL_V2.md)
permanece como plano de contingência durante a transição e o pacote full do
GitHub continua disponível no updater ("just in case").

## Motivação

O diff por snapshot resolveu o tamanho (4,5 MB típico) mas tem uma base
rígida: quem está 2+ versões atrás pode receber um `_internal/` incompleto
(o diff N só carrega o que mudou entre N-1 e N). O sync por arquivo elimina
esse problema por construção: o estado canônico é a PASTA publicada, e o
cliente converge para ela de QUALQUER versão anterior.

## Modelo

- O Drive hospeda uma **pasta** com a build full solta (cada release publica
  apenas os arquivos novos/alterados na pasta; removidos saem da pasta).
- Um **manifesto assinado** (`sync_manifest.json`, schema 2) lista TODOS os
  arquivos com `path`, `sha256`, `size` e `drive_id` (para download direto).
- O updater, em qualquer versão instalada:
  1. baixa o manifesto e verifica a assinatura (mesmo esquema RSA do
     `latest.json`);
  2. compara a versão instalada com a do manifesto (nada a fazer se >=);
  3. escaneia a instalação: para cada path do manifesto, hash local →
     classifica em `igual` (pula), `diferente` (baixa), `ausente` (baixa);
  4. detecta órfãos: arquivos dentro dos top-levels gerenciados que não
     estão no manifesto → serão REMOVIDOS;
  5. baixa os arquivos necessários um a um (progresso por arquivo na UI),
     validando o sha256 de cada um contra o manifesto;
  6. aplica com a transação por arquivo (backup individual + journal +
     rollback + validação final + launch-verify) — reaproveita a lógica do
     `_apply_diff_transaction`;
  7. relança o app.

## Manifesto (schema 2)

```json
{
  "schema": 2,
  "version": "20260814_012",
  "created_at": "2026-08-14T20:00:00-0300",
  "files": [
    {"path": "sig.exe", "sha256": "...", "size": 4136033, "drive_id": "..."},
    {"path": "_internal/python311.dll", "sha256": "...", "size": 5971968, "drive_id": "..."}
  ],
  "signature": "base64..."
}
```

- `files` inclui TUDO do pacote completo (inclusive `ffmpeg.exe`,
  `ffplay.exe`, `vad_worker.py`, `vad_deps/*`) — o estado canônico é o
  pacote full; no dia-a-dia o hash local bate e nada é baixado.
- `signature` cobre o payload canônico (version + created_at + files) com a
  mesma chave privada e o mesmo esquema de verificação do `latest.json`.

## Regras e decisões

- **Instalação nova ou >100 arquivos a baixar**: o updater avisa e
  recomenda o pacote completo do GitHub (evita rate limit e downloads
  individuais demais).
- **Órfãos**: remoção limitada aos top-levels gerenciados
  (`sig.exe`, `SigUpdater.exe`, `_internal/`, `prompts/`, `modelos/`,
  `build-info.json`) — nunca arquivos fora do manifesto (settings, cache).
- **Regressão de versão pelo Drive deixa de existir** (a pasta é sempre a
  última); regressão continua possível pelo full do GitHub, que o updater
  já lista.
- **Coexistência**: durante a transição, o updater tenta o sync (schema 2)
  e cai para a incremental ZIP (schema 1) se o manifesto sync não existir.

## Fases de implementação

1. **FASE A — updater**: funções puras do manifesto (parse/validação/
   assinatura), classificação local (igual/diferente/ausente/órfãos),
   download por arquivo com retry, transação sync (reusa a transação do
   diff), integração na UI standalone (progresso por arquivo).
2. **FASE B — release.py/publicação**: upload da pasta no Drive (incremental
   por hash, reuso de `drive_id`), geração do `sync_manifest.json` assinado,
   publicação lado a lado com o `latest.json`.
3. **FASE C — UX e migração**: progresso por arquivo detalhado, lista do que
   será removido, fluxo do SIG consultando o sync, aposentadoria do ZIP diff
   quando o sync estiver estável.

## Peças afetadas por mudanças no protocolo (CHECKLIST OBRIGATÓRIO)

O protocolo vive em TRÊS lugares que mudam JUNTOS:

1. `updater_v2/updater.py` — cópia embutida no SigUpdater.exe (canonical,
   verificação, validação, classificação);
2. `src/sync_common.py` — cópia do SIG (mesmas funções, exceção SyncError);
3. `scripts/sync_publish.py` — geração/assinatura do manifesto.

`tests/test_sync_common.py` garante a PARIDADE entre (1) e (2) — alterar um
sem o outro quebra os testes. O fluxo do SIG (check → classificação →
download por arquivo → `--sync-staged` no updater) é coberto pelo teste
ad-hoc `hermes-verify-sig-sync` (check/down/launch com assinatura real).

## Estado da migração

- O botão de atualização do SIG usa o sync (arquivo por arquivo) como único
  mecanismo de atualização; o updater standalone mantém sync + full.
- **O ZIP incremental foi aposentado (2026-08-15)**: `release.py` não gera
  mais o ZIP diff (a incremental é publicada pelo `sync_publish.py`); o
  `latest.json` (schema 1) fica congelado na última versão que o tinha; o
  código do fluxo ZIP permanece no updater para instalações antigas em campo.

## Testes permanentes

- `updater_v2/test_sync.py` — manifesto, classificação, download, transação
  (27 testes);
- `updater_v2/test_updater.py` — fluxo ZIP/CLI (22 testes);
- `tests/test_sync_common.py` — protocolo do SIG + paridade com o updater
  (10 testes);
- `updater_v2/harness.py` — 9 cenários end-to-end com o exe real (full,
  diff, sync e rollbacks).
- Suite completa do `release.py tests`.

## MIGRAÇÃO PARA O CLOUDFLARE R2 (a pasta sync fora do Drive)

**Estado (2026-08-22)**: bucket `sig` criado; upload S3 funcionando; download
público via R2.dev funcionando. A migração substitui o Drive como fonte do
sync por arquivo (elimina o falso positivo de malware do Google).

- **Credenciais (SENSÍVEIS — NÃO commitar)**: `release/r2_config.json`
  (ignorado pelo git; contém account_id, access_key_id, secret_access_key,
  bucket, endpoint S3 e o public_base). Se faltar, gerar em
  Cloudflare → R2 → Manage R2 API Tokens → Account API Token
  (Object Read & Write, escopo: bucket `sig`).
- **Endpoint S3** (upload): `https://<account-id>.r2.cloudflarestorage.com`
- **Bucket**: `sig`
- **Domínio público** (download do updater): `https://pub-<hash>.r2.dev`
  — o R2.dev é POR BUCKET: o URL de um objeto é
  `https://pub-<hash>.r2.dev/<path>` (SEM o nome do bucket no path).
- **Exemplo testado**: upload de `build-info.json` + download
  `...r2.dev/build-info.json` = 200 com o User-Agent do updater.
- **Bloqueio 1010 do Cloudflare**: o acesso com UA de bot (urllib/Python)
  recebe o 1010; com o UA do updater (`SigUpdater/2.0...`) funciona — o
  updater já envia esse UA.

## Estado atual

- Full `20260814_013` no GitHub; incremental ZIP e sync manifest 013 no
  Drive. Mecanismo principal: sincronização por arquivo.

## PROCEDIMENTO DE PUBLICAÇÃO (passo a passo)

> ⚠️ **AQUI VIVEM OS PITFALLS. Leia antes de publicar — cada erro abaixo
> já aconteceu de verdade.**

### 1. Bump + build + gates

```bash
# bump de APP_VERSION em src/sig_app.py ANTES (o release.py exige --version == APP_VERSION)
# release-notes-<versao>.md + run_release_<versao>.sh (padrão do repo)
python scripts/release.py release --version <VERSAO> --incremental
```

Gera em `release/generated/<VERSAO>/`: `package/` (a onedir full),
`<VERSAO>_full.zip`, `setup_sig_<VERSAO>.exe`, `online_setup_sig<VERSAO>.exe`.

> O `--incremental` **NÃO** corta a `vad_deps`/`ffmpeg` da `package/` — o estado
> canônico do Drive É o pacote completo (com vad_deps). Isso está correto.

### 2. Publicar o Drive (o comando que TODO MUNDO erra)

```bash
# ❌ ERRADO — passou a RAIZ: o Drive fica com package/_internal ANINHADO +
#    instaladores + full.zip na estrutura errada; o updater quebra.
python scripts/sync_publish.py --package release/generated/<VERSAO> --version <VERSAO>

# ✅ CORRETO — a pasta da build onedir (a onedir full solta) + o --github-tag:
#   o manifest adiciona o github_url no sig.exe/SigUpdater.exe → o updater
#   baixa esses do GitHub (previne o bloqueio de malware do Drive).
python scripts/sync_publish.py --package release/generated/<VERSAO>/package \
  --version <VERSAO> --github-tag <VERSAO>
```

- O sync sobe ~1800 arquivos (pasta completa) e o **cliente baixa só o diff**
  por hash — isso é o comportamento correto (não estranhar o número).
- Se você errou o caminho (a raiz), o Drive fica com a estrutura errada e é
  preciso **re-sincronizar com `.../package`** (outra rodada de upload).

### 3. Publicar o GitHub (release + regra "só a atual")

```bash
# A partir do diretório dos assets (o shell MSYS NÃO aceita C:/... — usa ./)
cd "release/generated/<VERSAO>"
gh release create <VERSAO> ./<VERSAO>_full.zip ./setup_sig_<VERSAO>.exe ./online_setup_sig<VERSAO>.exe \
  --repo spigknot/SIG-Windows --title "SIG Windows <VERSAO>" --notes "<descrição>"

# ✅ SEMPRE subir o sig.exe + SigUpdater.exe como ASSETS (estão na package/),
#    porque o --github-tag do sync aponta o updater para esses URLs do GitHub:
cd "release/generated/<VERSAO>/package"
gh release upload <VERSAO> ./sig.exe ./SigUpdater.exe --repo spigknot/SIG-Windows --clobber

# Se o create for interrompido no meio (upload lento), a release fica DRAFT.
# Este gh NÃO tem `gh release publish` — publique com:
gh release edit <VERSAO> --draft=false --repo spigknot/SIG-Windows

# Manter só a versão atual (regra do usuário):
gh release delete <VERSAO_ANTERIOR> --repo spigknot/SIG-Windows --yes
```

- **Caminhos do gh**: o shell do terminal é MSYS/zsh — `C:/Projetos/...` vira
  `no matches found`. Entre no diretório e use `./nome.ext`.

### 4. PORQUÊ subimos o sig.exe + SigUpdater.exe como assets (e o --github-tag)

O Google Drive **às vezes flagra os `.exe` PyInstaller como malware/spam**
(`reason: cannotDownloadAbusiveFile`), de forma arbitrária e imprevisível — já
aconteceu com o `SigUpdater.exe` (~11MB). Quando flagra, o download dá **404**
(público) / **403** (autenticado) — o updater falha exatamente nesse arquivo.

Por isso o fluxo normal **sempre** sobe `sig.exe` + `SigUpdater.exe` como assets
do GitHub + passa o `--github-tag` ao sync → o manifest aponta esses dois para o
GitHub (que não bloqueia), e o updater nunca depende do Drive para eles.

- **Verificação** (opcional): se o updater falhar com 404 num `.exe`, baixar do
  Drive `.../download?id=<drive_id>&export=download` — 200 = ok; 404 = bloqueado
  (refazer os passos 2 e 3).
- **Sintoma do bloqueio**: o updater baixa os arquivos e falha só no
  `sig.exe`/`SigUpdater.exe` com `HTTP Error 404`.

### 5. Fechar

```bash
# commit do content_snapshot.json + sync_manifest.json (o release pede):
git add -A && git commit -m "Publicacao <VERSAO>" && git push origin main
```

