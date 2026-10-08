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
- **`ffprobe.exe` na raiz NÃO entra no manifesto sync R2** (regra desde `20260829_002`): o `sync_r2.py` exclui esse componente do snapshot (`SYNC_EXCLUDED_TOP_LEVEL`) porque updaters ANTIGOS rejeitam componentes desconhecidos no manifesto. Para entregar a sonda necessária ao SmartJoin também às instalações existentes, `copy_runtime_assets()` inclui uma cópia em `_internal/tools/ffprobe.exe`, dentro de um componente já conhecido e sincronizado pelos updaters antigos. O app procura primeiro na raiz e depois nesse caminho interno. Manter a exclusão da raiz enquanto houver updaters antigos em campo. O fallback `ffmpeg -i` continua disponível para duração simples, mas não substitui a leitura de pacotes e quadros do SmartJoin.
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
5. Manter o histórico de releases no GitHub: NUNCA deletar releases anteriores (regra vigente desde `20260907` — seção 6).
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
   - Checar: `tasklist //FI "IMAGENAME eq sig.exe"` e `tasklist //FI "IMAGENAME eq SigUpdater.exe"` (as duas respostas vazias/"Nenhuma tarefa" = ok).
   - **Verificado em 20260913_004**: um `sig.exe` rodando de OUTRA pasta (ex.: a instalação em `C:\Program Files\SIG`) **não** bloqueia o build nem o harness — a checagem `_wait_for_processes` do updater só considera bloqueador o `sig.exe` cujo caminho de imagem é o MESMO do alvo do teste (instância do próprio pacote em teste, ex.: rodando de dentro do `dist/`/pacote validado). Nesse caso o app do usuário pode permanecer aberto (comprovado: `dist/sig.exe` permaneceu vivo por 12s com o app instalado aberto e o `release`+harness 9/9 passou). A regra de encerrar continua valendo para instâncias do PRÓPRIO alvo.
   - **NÃO** usar `powershell -Command "Get-Process | ? { $_.ProcessName -match '^sig$' }"`: no terminal bash/MSYS o `$_` é expandido pelo próprio bash e o comando chega quebrado ao PowerShell (pitfall na tabela abaixo).
3. **Credenciais do R2**: `release/r2_config.json` (NUNCA commitar; o `release/*` é ignorado pelo git).
   - Usar somente `endpoint`, `access_key_id` e `secret_access_key` da chave dedicada ao bucket `sig`; o sync deve permanecer no bucket `sig` e na URL `pub-abb3913e7d83457bae19e41b1e4020cc.r2.dev`.
   - Se faltar: Cloudflare → R2 → Manage R2 API Tokens → Account API Token (Object Read & Write, escopo: bucket `sig`).
4. **Chave privada do manifesto**: `release/update_private_key.pem` (usada pelo `sync_r2.py` para assinar o manifesto; NUNCA commitar).
5. **Gate rápido e contrato de contexto**: antes do preflight, executar
   `python scripts\release.py syntax --quiet` e
   `python scripts\check_prompt_context.py --quiet`. A verificacao confirma que
   a sintaxe Python está válida e que o prefixo estatico continua separado dos
   documentos condicionais sem divulgar conteudo de prompts, credenciais ou estado privado.
6. **Binário de referência do updater**: o gate `updater-v2-test` (dentro do
   preflight) valida `updater_v2/bin/SigUpdater.exe` contra
   `updater_v2/artifact.json`. Esse `.exe` é ignorado pelo git (`*.exe`) e pode
   não existir numa pasta recém-limpa — nesse caso, se o
   `dist/SigUpdater.exe` tiver o mesmo size+sha256 do `artifact.json`, basta
   copiá-lo para `updater_v2/bin/`; se divergir, seguir a seção 3.1 completa.

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
- **`release` deve rodar em BACKGROUND, nunca em foreground.** O tempo depende dos testes de exportação reais e do harness: a execução `20261007_001` levou aproximadamente 29 min nesta máquina (incluindo o preflight interno, o build e os 9 cenários do harness). Um foreground pode expirar e matar o processo antes do fim — mas o `release/generated/<v>/` e o `content_snapshot.json` podem já registrar a versão, então a repetição da MESMA versão é recusada. Ver seção 3.2.
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

### 3.2 SE o `release` for interrompido por timeout do terminal

Sintoma: o `release --version <v>` estoura o limite do foreground e morre no
meio, MAS `release/generated/<v>/` ja tem os 4 artefatos e
`release/content_snapshot.json` ja lista `<v>`. O harness nao chegou ao fim.

**Nao e para repetir `<v>`** — o `release.py` exige versao estritamente maior.
O que decide o caminho e o manifesto do R2:

```bash
"C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" -c "
import sys; sys.path.insert(0, 'updater_v2'); import updater
print('manifesto R2:', updater.fetch_sync_manifest()['version'])
"
```

- **R2 ainda na versao ANTERIOR (o sync nunca rodou)**: nada foi publicado.
  `rm -rf release/generated/<v>`, bumpar para `NNN+1` e rodar o release
  **em background**. Snapshot antes/depois prova que o pacote e do fonte:
  `sha256sum src/*.py scripts/*.py updater_v2/*.py > antes.txt` antes do build e
  `sha256sum -c antes.txt` depois (todas as linhas `OK`).
- **R2 ja na versao `<v>`**: publicada. Nao refazer build; seguir so o que
  faltou (sync/GitHub).

Antes de encerrar processo, identificar: `wmic process where
"ProcessId=<pid>" get ProcessId,CommandLine` — no ambiente do agente ha
`python.exe` do proprio Hermes, que NAO deve ser morto.

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
  diagnóstico e corrija a release atual (reenvie o asset faltante); nunca
  delete releases anteriores.
- Se a release ficar em draft (upload interrompido): `gh release edit YYYYMMDD_NNN --draft=false`.
- **Histórico de releases (regra vigente desde `20260907`)**: MANTER todas as
  releases anteriores no GitHub — NUNCA deletar a release anterior. Isso inclui
  a versão-ponte `20260821_013` (os PCs antigos, ainda no Drive/sync antigo,
  baixam o `sig.exe`/`SigUpdater.exe` da `013` de lá durante a migração; ela
  pode ser deletada só quando não houver mais PCs na `012` ou anterior).
  A regra antiga "só a versão atual" (`gh release delete <VERSAO_ANTERIOR>`)
  está REVOGADA e não deve mais ser executada.

## 7. Verificação final (antes de declarar pronto)

1. O manifesto no R2 aponta a versão nova (o comando da seção 4).
2. A release do GitHub tem o full.zip + os 2 instaladores; as releases anteriores foram mantidas.
3. O `git status` limpo (sem logs, sem `r2_config.json`, sem chaves).
4. Teste real: atualizar uma instalação antiga pelo app (deve baixar o diff do R2 e relançar na versão nova) — o log do updater deve ter `Atualização aplicada e validada`.
   - Sem tocar na instalação do usuário: `python scripts/verify_real_update.py` copia
     `C:\Program Files\SIG` para `%TEMP%\sig_real_update_test`, valida a assinatura do
     manifesto do R2, baixa o diff pelo mesmo caminho do app (`validate_sync_manifest` +
     `classify_sync_files` + `download_github_url`, com sha256 conferido), roda o
     `SigUpdater.exe` real contra a cópia e confere `Atualização aplicada e validada.`,
     a versão final e que a instalação de origem e o `settings.json` não mudaram;
     termina com `RESULTADO: PASS` (exit 0). Requer o SIG fechado — o updater relança o
     app da cópia e o script o encerra no fim.

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
| `FFprobe não foi encontrado; não é possível validar o SmartJoin` após atualização automática | instalações antigas não recebem o componente `ffprobe.exe` da raiz pelo sync | gerar a release com a cópia `_internal/tools/ffprobe.exe` feita por `copy_runtime_assets()`; conferir que esse caminho entra no snapshot sync e que o SmartJoin o encontra sem o binário na raiz; manter a validação de emendas e a cópia parcial de vídeo |
| `componente desconhecido no manifesto: <v>_full.zip` | o `--package` apontou para a raiz (subiu o full.zip no manifesto) | usar `--package .../package`; re-publicar o sync |
| `o manifesto de sincronização não cobre componentes obrigatórios: modelos/<modelo>.docx` | o código passou a exigir um modelo, mas o manifesto publicado no R2 ainda representa uma versão anterior sem esse arquivo | incluir o modelo em `modelos/`, gerar a nova versão pelo fluxo canônico e sincronizar o pacote gerado para o R2; validar o manifesto publicado antes de encerrar |
| `preflight` falha com `marcador sumiu da UI` após renomear os campos de Diárias | o teste de wiring ainda espera rótulos antigos ou o placeholder removido | atualizar as expectativas do teste para os rótulos e ações atuais da UI; repetir `syntax`, `check_prompt_context` e `preflight` antes do release |
| `componente desconhecido no manifesto de sincronização: ffprobe.exe` (usuário com app antigo não atualiza) | o manifesto R2 ganhou um componente que updaters antigos não conhecem e a validação antiga REJEITAVA o manifesto inteiro | corrigir `validate_sync_manifest` para IGNORAR componentes desconhecidos (vacina forward-compat, src + updater); tirar o componente novo de `SYNC_REQUIRED_FILES`/`SYNC_MANAGED_TOP_LEVELS` (manter em ALLOWED); excluir o componente do snapshot no `sync_r2.py` (`SYNC_EXCLUDED_TOP_LEVEL`) e distribuí-lo pelo full/instalador; release nova |
| `D:\tmp\updater-rebuild` já contém um `SigUpdater.exe` e não pode ser limpo com segurança | sobrou uma saída de compilação anterior no diretório temporário documentado | preservar o arquivo anterior e usar um `--distpath` temporário novo e exclusivo para a compilação; manter estáveis os caminhos `--workpath` e `--specpath`, depois copiar o binário e atualizar os metadados |
| `no matches found for C:/...` no `gh` | shell MSYS trata `C:/` como glob | `cd` no diretório e usar `./arquivo` |
| O check de processos da seção 1.2 cospe `O termo '/d/Projetos/SIG' não é reconhecido como nome de cmdlet` dezenas de vezes | o terminal é bash/MSYS e o `$_` dentro das aspas DUPLAS foi expandido pelo bash (`$_` = último argumento do comando anterior) antes de chegar ao PowerShell — o `-match '^sig$'` também virou outra coisa | usar `tasklist //FI "IMAGENAME eq sig.exe"` e `tasklist //FI "IMAGENAME eq SigUpdater.exe"` (a barra DUPLA escapa o `/FI` do MSYS); quando o comando realmente precisar de `$_`, proteger com aspas SIMPLES |
| `ERRO: Argumento/opção inválido - '//FI'` no check de processos (a forma recomendada acima FALHA) | neste bash/MSYS a barra dupla não é convertida para `/FI` — o `taskkill //PID` tem o mesmo problema | usar `tasklist \| grep -iE "sig.exe\|SigUpdater"` (vazio = ok) e, para encerrar, `powershell -Command "Stop-Process -Id <pid> -Force"`; conferir também `tasklist \| grep -iE "ffmpeg\|ffplay"` — se estiver vazio, o app está OCIOSO e pode ser fechado com segurança antes do build |
| Logs de release "sumiram" do repositório | os comandos foram executados com `> "$LOCALAPPDATA/Temp/<nome>.log" 2>&1` (necessário para ler a saída quiet sem estourar o terminal) | nada a fazer: o `rm -f release_*.log sync_*.log` da seção 5 vira no-op; conferir mesmo assim com `git status --short` antes do `git add -A` |
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
| `release.py release` segue ativo por mais de ~10 min e o stderr registra callbacks Tkinter após a janela de smoke test ser destruída | o release repete o preflight, executa exportações reais com FFmpeg e depois roda o harness; os callbacks aparecem no stderr após o encerramento da janela, mas na execução `20261007_001` não impediram o `PASS` final (aprox. 29 min no total) | manter em BACKGROUND e aguardar o exit code e o resumo final; enquanto estiver ativo, confirmar que os subprocessos ou arquivos temporários avançam. Não publicar sem `PASS` e código zero. Se o processo terminar com falha, seguir a regra fail-fast e reportar o erro exato |
| O `release.py release` estoura o timeout do terminal e morre no meio, mas `release/generated/<v>/` ja tem os 4 artefatos | o processo foi iniciado em foreground e morreu antes de concluir; o pacote, o snapshot e os instaladores podem já ter sido gerados | rodar o `release` em BACKGROUND; conferir o manifesto do R2 para saber se algo foi publicado (secao 3.2). R2 na versao anterior => `rm -rf release/generated/<v>` e bumpar `NNN+1` (a mesma versao e recusada pelo snapshot). R2 ja em `<v>`: ja foi publicada; seguir so sync/GitHub |
| `git status -sb` mostra `ahead 1` logo apos o push, mas `ls-remote` esta correto | a referencia local `origin/main` esta desatualizada (o push por URL nao atualiza o remote-tracking) | `git fetch <url> main:refs/remotes/origin/main` e reavaliar; comparar sempre `ls-remote` vs `git rev-parse HEAD`, nunca o `status -sb` sozinho |
| O `release_*.log`/`sync_*.log` entram no commit | `git add -A` pegou os logs | `rm -f release_*.log sync_*.log` ANTES do `git add` |
| `FAIL: não foi possível inspecionar dependências congeladas: "No entry named 'PYZ.pyz' found in the archive!"` no preflight | o `dist/sig.exe` foi gerado por outro interpreter/PyInstaller (tipicamente o `python` do PATH no terminal do Hermes = venv do Hermes, Python 3.11.15 + PyInstaller 6.10.0), que embute o PYZ com o nome `PYZ-00.pyz`; o validador exige `PYZ.pyz` (PyInstaller 6.21.0) | rebuildar o `dist/` com o interpreter do build (`"C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" scripts/build_dev.py --quiet`) e repetir o preflight; nunca rodar `build_dev.py`/PyInstaller com o `python` do PATH |
| Documentos indicam gates diferentes para o updater | O contrato antigo usava `updater-test`, enquanto o updater atual tem metadados v2 | usar `python scripts/release.py preflight --quiet`; o gate oficial é `updater-v2-test` |
| Release criado sem suíte ou smoke test | O build antigo validava o pacote e o updater, mas não encadeava todos os gates de operador | deixar o `preflight` fail-fast rodar antes do build; publicar somente após o smoke test da UI |
| Versão publicada com a data do dia anterior | A sequência foi incrementada sem comparar `YYYYMMDD` com a data atual | usar a data real do dia e reiniciar `NNN` em `001` sempre que o dia mudar |
| `FAIL: release <v> não é posterior à versão publicada <v>` ao refazer a MESMA versão | a versão já foi publicado no R2 (o `sync_r2.py` rodou) e o `release.py` exige versão ESTRITAMENTE maior que a do manifesto — refazer o build da mesma versão (ex.: corrigir o pacote depois de um build com o fonte alterado) esbarra nisso | publicar a versão SEGUINTE (`NNN+1`): o conteúdo é o mesmo e o manifesto passa a apontar o número novo; NUNCA tentar "despublicar" o R2. Antes de gerar o pacote, conferir que o fonte parou de mudar e tirar um snapshot (`sha256sum src/*.py scripts/*.py updater_v2/*.py > antes.txt`) para PROVAR, depois do build, que o pacote corresponde ao fonte (`sha256sum -c antes.txt`) |
| Saída quiet diferente entre gates | cada script tratava `--quiet` de forma isolada e o preflight deixava escapar linhas internas | seguir `docs/agents/validation-output.md`; sucesso em uma linha, falha com caminho do log e código não zero |
| Wrapper reporta sucesso após falha do release | pipeline Bash para `tail` sem `pipefail` | usar `set -euo pipefail` ou propagar o exit code do `release.py` |
| `verify_real_update.py` termina com `RESULTADO: FAIL` e o updater loga `a transação não contém arquivos para aplicar` | a instalação de origem JÁ está na versão publicada no R2 (o próprio app do usuário se atualizou, ou o teste rodou duas vezes) — o diff fica vazio e o updater recusa aplicar uma transação vazia | testar contra uma origem de uma versão ANTERIOR: `cp -r release/generated/<v_anterior>/package "$LOCALAPPDATA/Temp/origem"` e rodar `python scripts/verify_real_update.py --install "$LOCALAPPDATA/Temp/origem" --work "$LOCALAPPDATA/Temp/sig_verify"` (a cópia é somente leitura e a instalação real não é tocada). Evidência de sucesso: `Atualização aplicada e validada.` no trecho do updater |
| Harness falha porque o SIG atualizado encerra com código 0, e o rollback confirma outro `sig.exe` em execução | havia um processo do SIG sobrevivente antes do gate; a instância lançada pelo harness encerrou normalmente por já existir outra instância | confirmar e encerrar todos os processos `sig.exe`/`SigUpdater.exe` imediatamente antes do preflight e novamente antes do release, conforme a seção 1.2. **O bloqueio é por caminho de imagem**: um `sig.exe` de outra pasta (instalação em `Program Files\SIG`) NÃO é bloqueador e pode ficar aberto (verificado no `20260913_004`) — fechar só as instâncias do próprio alvo em teste |
| `ui-smoke` falha com `image "pyimageN" doesn't exist` somente depois da suíte completa | ícones `ImageTk.PhotoImage` foram criados sem `master`, podendo ficar associados a um interpretador Tk anterior destruído pelos testes | criar toda `PhotoImage` da interface com `master=self.root`; manter o smoke no final do preflight para validar a sequência real dos gates |
| `ui-smoke` falha com `can't read "PY_VARnn": no such variable` somente no preflight (avulso passa) | mesma família da linha acima: os `StringVar` do app são criados sem `master`, então ficam no `_default_root` do Tkinter — e a suíte unittest (in-process, que cria/destrói `Tk()` em testes de UI) deixa esse default apontando para outro interpretador; `root.getvar(nome)` falha mesmo com o objeto Python válido | ler o valor pelo OBJETO Python (`app.x_var.get()`), nunca por `root.getvar(cget("textvariable"))`, nos checks do smoke; e criar `StringVar`/`BooleanVar` novos com `master=self.root`. O smoke roda in-process no preflight (mesmo processo da suíte), o que explica o efeito só aparecer lá |
| `FAIL: UI smoke: o log ganhou/perdeu linhas: [... 'Verificando atualizações']` | o check de 13/09 (`_check_batch_log_lines`) exigia o log inteiro com EXATAMENTE 4 linhas, mas o app continua escrevendo sozinho durante os `root.update()` do próprio check (a linha "Verificando atualizações" nasce de um `after` do app e é drenada da fila naquele instante) — corrida que falhava de vez em quando | contar só as linhas DO LOTE (filtro por conteúdo: `arquivo(s)` + `Convertendo arquivos`); regra geral do smoke: localizar/validar linhas por CONTEÚDO, nunca exigir o log inteiro nem usar "última linha" |
| `FAIL: release <v> não é posterior à versão publicada <v>` depois de um release INTERROMPIDO (mesmo sem o `sync_r2.py` nunca ter rodado) | o `release.py` grava `release/content_snapshot.json` LOGO no começo do build, antes do harness; se o processo for morto no meio (ex.: terminal/aba encerrada), o snapshot já registra a versão e a repetição da MESMA versão é recusada | conferir o manifesto do R2 para saber se a versão foi publicada de verdade: **manifesto ANTIGO = nada saiu**, então só limpar o parcial (`rm -rf release/generated/<v>`) e publicar a versão SEGUINTE (`NNN+1`); **manifesto JÁ na versão = publicada**, seguir só o que faltou (sync/GitHub). Não existe "despublicar" |
| `git rev-parse <VERSAO>` falha com exit 128 logo depois de `gh release create --target main` | a tag foi criada no GitHub mas ainda NÃO foi baixada para o repositório local; `git rev-parse` só conhece refs locais | não é erro de release: conferir o SHA da tag direto na API (`gh api repos/spigknot/SIG-Windows/git/ref/tags/<VERSAO> --jq '.object.sha'`) e comparar com `git rev-parse HEAD`; para o uso local, `git fetch --tags` |
| O `verify_real_update.py` é rápido demais e o app instalado continua numa versão antiga | o próprio app do usuário se atualiza sozinho pelo menu (ou o teste rodou antes da sync); a instalação de origem já estava na versão do R2, o diff fica vazio e o updater recusa aplicar a transação vazia | copiar explicitamente o pacote de uma versão ANTERIOR para usar de origem (`cp -r release/generated/<v_anterior>/package "$LOCALAPPDATA/Temp/origem"`) e rodar `python scripts/verify_real_update.py --install "$LOCALAPPDATA/Temp/origem" --work "$LOCALAPPDATA/Temp/sig_verify"`; conferir no relatório `RESULTADO: PASS`, `Atualização aplicada e validada.` e `versao da instalacao de origem (intacta)` |
| `release.py release` sai com código 0 mas `release/generated/<v>/` só tem `package/` e o zip — sem `*_full.zip` nem os 2 instaladores | o comando foi executado SEM a flag `--incremental` (a seção 3 traz `release --version <v> --incremental --quiet`); sem ela o passo de empacotamento/instaladores é pulado e a seção 6 não tem o que subir | repetir a seção 3 EXATAMENTE como está (com `--incremental`); conferir `ls release/generated/<v>/` esperando os 4 itens (`package`, `<v>_full.zip`, `setup_sig_<v>.exe`, `online_setup_sig<v>.exe`) ANTES do sync e do GitHub |
| Botão da UI "funciona" nos testes e quebra em runtime com `AttributeError: 'SigApp' object has no attribute '<nome>'` | o `command` do botão chamava um nome DIFERENTE do método real; build e pytest não pegam nada disso porque o nome só é resolvido no clique | o gate `ui-smoke` não cobre clique em botão: para defeito de UI, medir/executar de verdade (`winfo_width/height/rooty` numa janela REALIZADA + `button.invoke()`) e registrar a vacina em `tests/`. Regra: nenhum botão novo sem teste que o ACIONE |
| Botão verde `Atualizar` aparece parcialmente coberto pela barra de abas | em escalas de tela maiores, o botão posicionado no cabeçalho pode sobrepor a barra; como ela é criada depois, fica acima dele na ordem de empilhamento | depois de posicionar o botão, chamar `tkraise()` para trazê-lo à frente sem alterar as linhas empacotadas nem deslocar o conteúdo |
| Botão quadrado/alinado sai torto dependendo de onde o teste roda (24 px num processo, 30 px na suíte completa) | o `width`/`height` do ttk é em CARACTERES, `-height` não existe no `ttk::button`, e o Tk em pixels muda com o DPI/escala do processo | nunca fixar o lado em número: MEDIR a altura de um botão de ícone vizinho e usar como lado do quadrado; `place(x=width/2, y=0, width=lado, height=lado, anchor="n")`. E `anchor="n"` (centro vertical no topo) alinha com os botões empacotados — `anchor="nw"` deixa o botão alguns pixels ABAIXO |
| `git push` devolve exit 0, imprime NADA e o remoto NÃO recebe o commit (pelo `credential-helper-selector`/`credential-manager` do Windows) | o gerenciador de credenciais abre um prompt de autenticação INVISÍVEL (a janela não aparece no terminal do Hermes), segura ~59 s e o processo morre no timeout — sem erro e sem enviar nada; pior, `ls-remote` mostra o remoto antigo e parece que o push "falhou", mas ele nem chegou a tentar | fazer o push com o token do `gh`, que já está autenticado: `TOKEN=$(gh auth token) && git -c credential.helper= -c core.askPass=true push "https://x-access-token:${TOKEN}@github.com/spigknot/SIG-Windows.git" main:main`. Confirmar SEMPRE com `git ls-remote origin main` vs `git rev-parse HEAD`. No terminal interativo do usuário o `git push` comum funciona; o problema é do ambiente do agente |
| Botão posicionado "ao lado" de outro sai com a distância pedida pela METADE (12 px em vez de 24) | `place(x=..., anchor="center")` posiciona o CENTRO do widget, então a borda direita é `x + largura/2`; somar a meia-largura de novo dá a metade da folga. E se o widget de referência for reposicionado com `anchor="w"`, o `x` do place deixa de ser o centro e vira a borda esquerda, invalidando a conta | derivar a borda a partir da posição JÁ MEDIDA (`winfo_x()`, na mesma origem do `place`) e só então aplicar a folga; travar com um teste que meça a distância real entre as BORDAS dos dois widgets com tolerância de ~2 px, senão o erro passa silencioso (o botão continua clicável, só torto) |
| Botão novo dentro de um `Text`/`Frame` com `pack` NA FAIXA: o `place` do botão é ignorado e ele sai esticado (ex.: 26x150 em vez de 24x24) | um widget tem UM gerenciador de geometria: o `pack` aplicado DEPOIS sobrescreve o `place` (e o `fill=Y` estica a altura) | nunca aplicar `pack` e `place` no mesmo widget; se precisar dos dois, use um CONTAINER: `pack` no container (reservando a largura/espaço) e `place` dentro dele para posicionar; travar com `assertEqual("place", botao.winfo_manager())` no teste de UI |
| Botão da coluna "2" mede 1x1 e o teste acusa desalinhamento falso | a coluna 2 (`live_*_secondary_pane`, e o `live_transcript_actions_2`) é criada mas SÓ é exibida por `_refresh_multi_text_layout`, que cobre histórico e oitiva — a TRANCRIÇÃO 2 nunca é exibida; sem isso os containers ficam `viewable=0` e reportam 1x1, e qualquer medição dela é mentira | ligar a coluna de verdade no teste antes de medir (`app.multi_text_secondary = True; app.multi_text_model_var.set(True); app._refresh_multi_text_layout()`), ou aceitar 1x1 como "recolhida" e pular a asserção. Não "consertar" a transcrição 2: é comportamento antigo, fora do escopo da UI |

---

## Contexto historico opcional

O historico da migracao de distribuicao foi separado em
`docs/maintenance/release-history.md`. Leia-o somente para diagnosticar uma
instalacao antiga; ele nao faz parte do procedimento atual nem deve ser
carregado como contexto universal.
