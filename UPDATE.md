# UPDATE.md — Procedimento completo de geração de nova versão (SIG Windows)

> Este documento é a FONTE DA VERDADE para gerar e publicar uma nova versão do SIG Windows.
> Siga EXATAMENTE esta ordem. Cada passo tem comandos literais, verificações e os
> pitfalls já vividos. Se um passo falhar, NÃO pule — resolva conforme a seção
> "Pitfalls e resolução".

---

## 0. Visão geral do fluxo

```
bump da versão → preflight → release.py (build + harness completo) → sync no R2 (diff) → commit + push → GitHub (full + instaladores)
```

- **Sync por arquivo (atualização automática)**: Cloudflare R2, SEMPRE no bucket `sig` (`https://pub-abb3913e7d83457bae19e41b1e4020cc.r2.dev`).
- **Download manual / reparo**: GitHub Releases (full.zip + instaladores).
- **Runtime assets** (`ffmpeg.exe`, `ffplay.exe`, `ffprobe.exe`, `vad_deps/`): copiados de `assets/`/`dist/` para o `package/` pelo `copy_runtime_assets()`; o `ffprobe.exe` (8.0.1, do mesmo build gyan.dev do ffmpeg) é usado pelo app para medir duração de forma rápida e precisa, com fallback para o parse do `ffmpeg -i`. São EXCLUÍDOS do diff incremental (`INCREMENTAL_EXCLUDED_TOP_LEVEL`) e entram no full/instalador.
- **`ffprobe.exe` NÃO entra no manifesto sync R2** (regra desde `20260829_002`): o `sync_r2.py` exclui `ffprobe.exe` do snapshot (`SYNC_EXCLUDED_TOP_LEVEL`) porque updaters ANTIGOS rejeitam componentes desconhecidos no manifesto — incluí-lo travaria instalações antigas sem atualizar. O ffprobe chega às máquinas pelo full.zip/instalador (instalações novas); as existentes usam o fallback `ffmpeg -i`. Remover a exclusão só quando todos os updaters em campo forem tolerantes a componentes novos (>= `20260829_002`).
- **Drive do Google**: APOSENTADO desde a versão `20260821_013`. Não publicar mais lá.
- O R2.dev é POR BUCKET: o URL de um objeto é `https://pub-<hash>.r2.dev/<path>` (SEM o bucket no path).
- O updater/app buscam o manifesto em `https://pub-<hash>.r2.dev/sync_manifest.json` (schema 2, assinado).

## 0.1 Contexto essencial

- **Repositório**: `D:\Projetos\SIG Windows` (Windows; o terminal é bash/MSYS — caminhos `C:/...` viram glob no `gh`, use `cd` no diretório e caminhos relativos `./arquivo`).
- **Python do build**: `C:\Users\Gustavo\AppData\Local\Programs\Python\Python311\python.exe` (Python `3.11.0` — o `release.py` valida por VERSÃO, não por caminho).
- **Versão nova**: a versão atual está em `APP_VERSION` em `src\sig_app.py`. Use a data real do dia no formato `YYYYMMDD_NNN`. Se a data for a mesma da versão atual, incremente apenas `NNN`; se o dia mudar, reinicie obrigatoriamente em `001` (ex.: `20260823_003` → `20260824_001`; no mesmo dia, `20260824_001` → `20260824_002`). Nunca continue a numeração do dia anterior.
- **Credenciais do R2** em `release\r2_config.json` e **chave privada do manifesto** em `release\update_private_key.pem` (ambos NUNCA commitar). O JSON local deve conter apenas as credenciais S3 da chave dedicada ao bucket `sig`; não reutilizar `bucket`/`public_base` de `sig-android` ou `tailmsg`.

## 0.2 Regras obrigatórias (não negociáveis)

1. Nenhum processo `sig.exe` / `SigUpdater.exe` pode estar rodando durante o build (verifique e encerre antes — seção 1.2).
2. O `--package` do `sync_r2.py` DEVE apontar para a pasta `package/` — nunca a raiz `release/generated/<v>` (corrompe o manifesto — seção 4).
3. O sync é SOMENTE no Cloudflare R2. O Google Drive está APOSENTADO desde `20260821_013`.
4. No GitHub: subir SOMENTE o `full.zip` + `setup_sig_<v>.exe` + `online_setup_sig<v>.exe`. NUNCA subir `sig.exe`/`SigUpdater.exe` avulsos (eles são servidos pelo R2).
5. Deletar a release anterior (regra "só a versão atual"), EXCETO a versão-ponte `20260821_013` (seção 6).
6. NUNCA commitar: `release_*.log`, `sync_*.log`, `r2_config.json`, chaves privadas, `settings.json`. Remover os logs antes do `git add` (seção 5).
7. O preflight e o harness devem terminar com código zero — QUALQUER `FAIL` impede a publicação. Em modo `--quiet`, cada comando produz um resumo curto; sem `--quiet`, o release mantém as linhas PASS detalhadas e os 9 cenários do harness. Consulte `docs/agents/validation-output.md` para o contrato de saída.
8. Não inventar resultados nem números: tudo que for reportado deve vir da saída real dos comandos.
9. Se QUALQUER etapa falhar: PARE imediatamente e reporte o erro exato (mensagem + o comando que falhou), sem tentar contornar por conta própria fora deste documento.
10. Ao terminar, revise e atualize este documento se algo divergiu (seção 9 — Manutenção do documento).

## 1. Pré-requisitos (antes de começar)

1. **Ambiente de build aprovado**: Python `3.11.0` + PyInstaller `6.21.0` (o `release.py` valida e falha com diagnóstico se divergir).
   - Verificar: `python -c "import sys, PyInstaller; print(sys.version_info[:3], PyInstaller.__version__)"`
   - Verificar também: `python -c "import sounddevice"` e `python -c "import websocket"`.
2. **Fechar o SIG**: nenhum processo `sig.exe` / `SigUpdater.exe` pode estar rodando (o build sobrescreve os executáveis).
   - Checar: `powershell -NoProfile -Command "Get-Process | ? { $_.ProcessName -match '^sig$' }"` (deve estar vazio).
3. **Credenciais do R2**: `release/r2_config.json` (NUNCA commitar; o `release/*` é ignorado pelo git).
   - Usar somente `endpoint`, `access_key_id` e `secret_access_key` da chave dedicada ao bucket `sig`; o sync deve permanecer no bucket `sig` e na URL `pub-abb3913e7d83457bae19e41b1e4020cc.r2.dev`.
   - Se faltar: Cloudflare → R2 → Manage R2 API Tokens → Account API Token (Object Read & Write, escopo: bucket `sig`).
4. **Chave privada do manifesto**: `release/update_private_key.pem` (usada pelo `sync_r2.py` para assinar o manifesto; NUNCA commitar).
5. **Gate rápido e contrato de contexto**: antes do preflight, executar
   `python scripts\release.py syntax --quiet` e
   `python scripts\check_prompt_context.py --quiet`. A verificacao confirma que
   a sintaxe Python está válida e que o prefixo estatico continua separado dos
   documentos condicionais sem divulgar conteudo de prompts, credenciais ou estado privado.

## 2. Bump da versão

Editar `src/sig_app.py`:

```python
APP_VERSION = "YYYYMMDD_NNN"   # ex.: 20260821_014
```

- Formato obrigatório: `\d{8}_\d{3}` (o harness e o updater validam).
- A versão DEVE ser a mesma em: `APP_VERSION`, o pacote gerado, o manifesto sync e o tag da release.

## 3. Release (build + harness)

```bash
cd "D:/Projetos/SIG Windows"
"C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" scripts/release.py preflight --quiet
"C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" scripts/release.py release --version YYYYMMDD_NNN --incremental --quiet
```

- Gera: `release/generated/YYYYMMDD_NNN/` (package + `*_full.zip` + `setup_sig_*.exe` + `online_setup_sig*.exe`).
- O `preflight` roda os testes unitários, a validação do estado atual, o `updater-v2-test` e `ui-smoke`, em ordem fail-fast.
- O comando `release` repete o preflight automaticamente antes do build limpo e depois roda o harness completo (9 cenários): build onedir, updater, diffs, sync e rollbacks.
- **Critério de sucesso**: preflight sem erro, código zero no release, pacote/manifesto válidos e harness completo. Em modo quiet, o resumo deve conter `PASS`; NÃO é sucesso se houver qualquer `FAIL`.

### 3.1 SE o harness falhar com o SigUpdater

Erro típico: `FAIL: SigUpdater.exe não corresponde ao artefato conhecido como bom`.

Causa: o `release.py` recompila o `SigUpdater.exe` e o hash novo diverge dos metadados. Isso pode ocorrer quando o `updater.py` muda ou quando o PyInstaller/Windows resolve novas DLLs de API Set, mesmo sem alteração no código do updater.

Resolução (sempre que o `updater.py` for alterado):

```bash
# 1. Recompilar o updater (determinístico — mesmo ambiente do release)
rm -rf /d/d/tmp/updater-rebuild && mkdir -p /d/d/tmp/updater-rebuild
SOURCE_DATE_EPOCH=946684800 PYTHONHASHSEED=0 "C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" -m PyInstaller \
  --noconfirm --clean --onefile --windowed --noupx --name SigUpdater \
  --distpath /d/d/tmp/updater-rebuild --workpath build/updater_v2 --specpath build/updater_v2 updater_v2/updater.py

# 2. Copiar para o bin de referência
cp /d/d/tmp/updater-rebuild/SigUpdater.exe updater_v2/bin/SigUpdater.exe

# 2b. O preflight também valida a instalação de referência em dist/; manter
#     nela o mesmo updater recém-recompilado antes de repetir os gates
cp /d/d/tmp/updater-rebuild/SigUpdater.exe dist/SigUpdater.exe

# 3. Após revisar e aprovar a nova composição de dependências, atualizar os DOIS metadados com o size + sha256 novos
#    O source_sha256 permanece igual quando updater_v2/updater.py não mudou.
#    (scripts/updater_artifact.json e updater_v2/artifact.json)
"C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" -c "import hashlib; print(len(open('updater_v2/bin/SigUpdater.exe','rb').read()), hashlib.sha256(open('updater_v2/bin/SigUpdater.exe','rb').read()).hexdigest())"

# 4. Limpar o diretório parcial e RE-RODAR o release
rm -rf release/generated/YYYYMMDD_NNN release_*.log
```

## 4. Sync no Cloudflare R2 (o diff — só o que mudou)

```bash
"C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" scripts/sync_r2.py \
  --package release/generated/YYYYMMDD_NNN/package --version YYYYMMDD_NNN --quiet
```

- **O `--package` DEVE apontar para a pasta `package/`** (a onedir full solta) — NUNCA a raiz `release/generated/<v>` (isso quebrou o manifesto com `package/_internal` aninhado).
- O script: calcula o MD5 local, lista os ETags do R2 (1 chamada), sobe SÓ os que mudaram e publica o `sync_manifest.json` assinado.
- Saída quiet esperada: uma linha `PASS: sync-r2` com versão, quantidade enviada, quantidade inalterada e manifesto. Sem `--quiet`, a saída mostra `subir: N` (N pequeno — só o diff) e o progresso.
- **Verificação pós-sync** (obrigatória):

```bash
"C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" -c "
import sys; sys.path.insert(0, 'updater_v2'); import updater
m = updater.fetch_sync_manifest()
print('manifesto R2:', m['version'], len(m['files']), 'arquivos')
"
```

Deve imprimir a versão nova. Se falhar, o manifesto não foi publicado corretamente.

## 5. Commit e push

```bash
cd "D:/Projetos/SIG Windows"
rm -f release_*.log sync_*.log          # NUNCA commitar os logs
git add -A
git commit -m "Versao YYYYMMDD_NNN: <descrição curta>"
git push origin main
```

## 6. GitHub Releases (full + instaladores — SEM os executáveis avulsos)

Arquivos grandes NÃO devem ser passados junto do `gh release create`: se a
janela do terminal for encerrada durante o upload, o GitHub pode deixar uma
release parcial ou um endpoint de upload inválido. Primeiro crie somente os
metadados da release; depois envie cada asset em um comando separado e aguarde
o exit code zero de cada comando.

```bash
cd "D:/Projetos/SIG Windows/release/generated/YYYYMMDD_NNN"
gh release create YYYYMMDD_NNN \
  --repo spigknot/SIG-Windows --title "SIG Windows YYYYMMDD_NNN" --notes "<descrição>"
gh release upload YYYYMMDD_NNN ./YYYYMMDD_NNN_full.zip \
  --repo spigknot/SIG-Windows
gh release upload YYYYMMDD_NNN ./setup_sig_YYYYMMDD_NNN.exe \
  --repo spigknot/SIG-Windows
gh release upload YYYYMMDD_NNN ./online_setup_sigYYYYMMDD_NNN.exe \
  --repo spigknot/SIG-Windows
gh release view YYYYMMDD_NNN --repo spigknot/SIG-Windows --json tagName,url,assets
```

- **NÃO** subir `sig.exe`/`SigUpdater.exe` como assets avulsos — eles são servidos pelo R2 (o `github_url` do manifesto aponta para o R2.dev).
- A verificação final deve mostrar exatamente os três assets permitidos: o
  `full.zip` e os dois instaladores. Se um upload falhar, pare, preserve o
  diagnóstico e não exclua a release anterior até corrigir a release atual.
- Se a release ficar em draft (upload interrompido): `gh release edit YYYYMMDD_NNN --draft=false`.
- **Regra "só a versão atual"**: deletar a release anterior EXCETO a versão-ponte
  `20260821_013` (MANTER no GitHub — os PCs antigos, ainda no Drive/sync antigo,
  baixam o `sig.exe`/`SigUpdater.exe` da `013` de lá durante a migração). A `013`
  pode ser deletada só quando não houver mais PCs na `012` ou anterior.
  ```bash
  gh release delete <VERSAO_ANTERIOR> --repo spigknot/SIG-Windows --yes
  ```

## 7. Verificação final (antes de declarar pronto)

1. O manifesto no R2 aponta a versão nova (o comando da seção 4).
2. A release do GitHub tem o full.zip + os 2 instaladores; a anterior foi deletada.
3. O `git status` limpo (sem logs, sem `r2_config.json`, sem chaves).
4. Teste real: atualizar uma instalação antiga pelo app (deve baixar o diff do R2 e relançar na versão nova) — o log do updater deve ter `Atualização aplicada e validada`.

## 8. Entrega (relatório final obrigatório)

Ao concluir, reportar APENAS valores reais das saídas dos comandos:

1. A versão publicada (`YYYYMMDD_NNN`).
2. O resultado do preflight e do harness (resumo `PASS` e código zero; a contagem real de cenários vem da saída do comando).
3. Quantos arquivos subiram no R2 (`subir: N` — deve ser um número pequeno, o diff).
4. O link da release do GitHub.
5. O hash do commit (`git rev-parse HEAD`).

Se QUALQUER etapa falhar: PARE imediatamente e reporte o erro exato (mensagem + o comando que falhou), sem tentar contornar por conta própria fora deste documento.

## 9. Manutenção do documento (obrigatório)

Ao terminar, revise este `UPDATE.md`: se QUALQUER passo divergir do que foi
documentado, ou se você encontrou um pitfall novo (erro, atalho, detalhe de
ambiente), ATUALIZE este documento para refletir a realidade e inclua o
pitfall na tabela de resolução — no mesmo commit da versão. Este documento é
a fonte da verdade e deve evoluir com a prática.

---

## Pitfalls e resolução (já vividos — não repetir)

| Sintoma | Causa | Resolução |
|---|---|---|
| `componente desconhecido no manifesto: <v>_full.zip` | o `--package` apontou para a raiz (subiu o full.zip no manifesto) | usar `--package .../package`; re-publicar o sync |
| `componente desconhecido no manifesto de sincronização: ffprobe.exe` (usuário com app antigo não atualiza) | o manifesto R2 ganhou um componente que updaters antigos não conhecem e a validação antiga REJEITAVA o manifesto inteiro | corrigir `validate_sync_manifest` para IGNORAR componentes desconhecidos (vacina forward-compat, src + updater); tirar o componente novo de `SYNC_REQUIRED_FILES`/`SYNC_MANAGED_TOP_LEVELS` (manter em ALLOWED); excluir o componente do snapshot no `sync_r2.py` (`SYNC_EXCLUDED_TOP_LEVEL`) e distribuí-lo pelo full/instalador; release nova |
| `no matches found for C:/...` no `gh` | shell MSYS trata `C:/` como glob | `cd` no diretório e usar `./arquivo` |
| `SigUpdater.exe não corresponde ao artefato bom` | `updater.py` mudou ou PyInstaller/Windows incluiu novas DLLs de API Set e o hash do fresh divergiu | revisar a composição, seguir a seção 3.1 e atualizar os 2 metadados; manter a validação exata por hash |
| O preflight continua acusando `SigUpdater.exe` depois de atualizar `updater_v2/bin` | a validação padrão também compara `dist/SigUpdater.exe`, que permaneceu com o binário anterior | copiar o mesmo rebuild determinístico para `dist/SigUpdater.exe` e repetir o preflight |
| A tag da release aponta para o commit anterior | `gh release create` foi executado antes do commit/push, então a tag foi criada a partir do `origin/main` antigo | executar as seções 5 e 6 nessa ordem; se a release já existir, retargetear a tag para o commit publicado com `git push origin +<COMMIT>:refs/tags/<VERSAO>` e verificar o SHA |
| Runtime assets exigem `ffprobe.exe` mas ele não está no pacote | `runtime_artifact.json`/`REQUIRED_RUNTIME_FILES`/`SYNC_REQUIRED_FILES` sem a entrada; ou `assets/` sem o binário | adicionar `ffprobe.exe` nas 3 listas e no `runtime_artifact.json` (sha256+size) e copiar o binário do mesmo build gyan.dev do ffmpeg para `assets/` e `dist/` |
| Google bloqueia `.exe` como malware | Drive flagra PyInstaller (aposentado — R2 não bloqueia) | se o R2 algum dia bloquear: assets avulsos no GitHub + `--github-tag` |
| `[Erro: 13] Permission denied` no lock | updater sem admin / SIG aberto | fechar o SIG; executar o updater como Administrador |
| `HTTP 1010` no R2.dev | User-Agent de bot (urllib) | o updater/app usam o UA `SigUpdater/2.0 (+https://github.com/spigknot/SIG-Windows)` — nunca o UA do urllib |
| Sync aparece em outro bucket | configuração de credenciais trouxe `bucket`/`public_base` de outro projeto | usar somente as credenciais S3 e manter o destino fixo `bucket = sig` e `https://pub-abb3913e7d83457bae19e41b1e4020cc.r2.dev` |
| sync_r2 subindo 1791 arquivos | versão antiga do script (sem o diff) | usar o diff por ETag/MD5 (list_objects) — `subir: N` pequeno |
| `RequestTimeTooSkewed` no sync_r2 (`ListObjectsV2`) | relógio do Windows dessincronizado (serviço `w32time` parado; diferença >15 min vs servidor) | iniciar o serviço e sincronizar: `powershell -c "Start-Service w32time; w32tm /resync"` (com elevação); conferir com `date -u` vs `curl -sI https://api.cloudflare.com | grep -i ^date:` |
| `SignatureDoesNotMatch` no `ListObjectsV2` | `release/r2_config.json` usa um par de credenciais S3 incompatível, antigo ou de outro token/bucket | gerar um novo token S3 para o bucket `sig`, substituir o par `access_key_id` + `secret_access_key` localmente e manter o endpoint S3 e `bucket: sig`; nunca usar o token da API ou a URL pública `.r2.dev` como credencial |
| `gh release create` interrompido durante upload grande; release parcial, URL `untagged-*` ou `HTTP 404` em `uploads.github.com` | assets grandes foram enviados junto da criação e o processo terminou antes de concluir todos os uploads | confirmar a situação com `gh release list/view`; se a release estiver parcial, excluí-la com sua tag órfã, recriar sem assets e enviar o full e os dois instaladores separadamente, aguardando cada comando |
| O `release_*.log`/`sync_*.log` entram no commit | `git add -A` pegou os logs | `rm -f release_*.log sync_*.log` ANTES do `git add` |
| Documentos indicam gates diferentes para o updater | O contrato antigo usava `updater-test`, enquanto o updater atual tem metadados v2 | usar `python scripts/release.py preflight --quiet`; o gate oficial é `updater-v2-test` |
| Release criado sem suíte ou smoke test | O build antigo validava o pacote e o updater, mas não encadeava todos os gates de operador | deixar o `preflight` fail-fast rodar antes do build; publicar somente após o smoke test da UI |
| Versão publicada com a data do dia anterior | A sequência foi incrementada sem comparar `YYYYMMDD` com a data atual | usar a data real do dia e reiniciar `NNN` em `001` sempre que o dia mudar |
| Saída quiet diferente entre gates | cada script tratava `--quiet` de forma isolada e o preflight deixava escapar linhas internas | seguir `docs/agents/validation-output.md`; sucesso em uma linha, falha com caminho do log e código não zero |
| Wrapper reporta sucesso após falha do release | pipeline Bash para `tail` sem `pipefail` | usar `set -euo pipefail` ou propagar o exit code do `release.py` |

---

## Contexto historico opcional

O historico da migracao de distribuicao foi separado em
`docs/maintenance/release-history.md`. Leia-o somente para diagnosticar uma
instalacao antiga; ele nao faz parte do procedimento atual nem deve ser
carregado como contexto universal.
