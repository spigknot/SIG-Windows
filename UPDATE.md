# UPDATE.md — Procedimento completo de geração de nova versão (SIG Windows)

> Este documento é a FONTE DA VERDADE para gerar e publicar uma nova versão do SIG Windows.
> Siga EXATAMENTE esta ordem. Cada passo tem comandos literais, verificações e os
> pitfalls já vividos. Se um passo falhar, NÃO pule — resolva conforme a seção
> "Pitfalls e resolução".

---

## 0. Visão geral do fluxo

```
bump da versão → release.py (build + harness 8/8) → sync no R2 (diff) → GitHub (full + instaladores) → commit
```

- **Sync por arquivo (atualização automática)**: Cloudflare R2 (`https://pub-abb3913e7d83457bae19e41b1e4020cc.r2.dev`).
- **Download manual / reparo**: GitHub Releases (full.zip + instaladores).
- **Drive do Google**: APOSENTADO desde a versão `20260821_013`. Não publicar mais lá.
- O R2.dev é POR BUCKET: o URL de um objeto é `https://pub-<hash>.r2.dev/<path>` (SEM o bucket no path).
- O updater/app buscam o manifesto em `https://pub-<hash>.r2.dev/sync_manifest.json` (schema 2, assinado).

## 0.1 Contexto essencial

- **Repositório**: `D:\Projetos\SIG Windows` (Windows; o terminal é bash/MSYS — caminhos `C:/...` viram glob no `gh`, use `cd` no diretório e caminhos relativos `./arquivo`).
- **Python do build**: `C:\Users\Gustavo\AppData\Local\Programs\Python\Python311\python.exe` (Python `3.11.0` — o `release.py` valida por VERSÃO, não por caminho).
- **Versão nova**: a versão atual está em `APP_VERSION` em `src\sig_app.py`. A nova versão é a PRÓXIMA no formato `YYYYMMDD_NNN` (mesma data, número seguinte; ex.: se está `20260821_014`, gere `20260821_015`).
- **Credenciais do R2** em `release\r2_config.json` e **chave privada do manifesto** em `release\update_private_key.pem` (ambos NUNCA commitar).

## 0.2 Regras obrigatórias (não negociáveis)

1. Nenhum processo `sig.exe` / `SigUpdater.exe` pode estar rodando durante o build (verifique e encerre antes — seção 1.2).
2. O `--package` do `sync_r2.py` DEVE apontar para a pasta `package/` — nunca a raiz `release/generated/<v>` (corrompe o manifesto — seção 4).
3. O sync é SOMENTE no Cloudflare R2. O Google Drive está APOSENTADO desde `20260821_013`.
4. No GitHub: subir SOMENTE o `full.zip` + `setup_sig_<v>.exe` + `online_setup_sig<v>.exe`. NUNCA subir `sig.exe`/`SigUpdater.exe` avulsos (eles são servidos pelo R2).
5. Deletar a release anterior (regra "só a versão atual"), EXCETO a versão-ponte `20260821_013` (seção 5).
6. NUNCA commitar: `release_*.log`, `sync_*.log`, `r2_config.json`, chaves privadas, `settings.json`. Remover os logs antes do `git add` (seção 6).
7. O harness deve terminar com `RELEASE_EXIT=0` e 12 PASS — QUALQUER `FAIL` impede a publicação. NÃO publicar release com FAIL.
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
   - Se faltar: Cloudflare → R2 → Manage R2 API Tokens → Account API Token (Object Read & Write, escopo: bucket `sig`).
4. **Chave privada do manifesto**: `release/update_private_key.pem` (usada pelo `sync_publish`/`sync_r2` para assinar o manifesto; NUNCA commitar).

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
"C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" scripts/release.py release --version YYYYMMDD_NNN --incremental
```

- Gera: `release/generated/YYYYMMDD_NNN/` (package + `*_full.zip` + `setup_sig_*.exe` + `online_setup_sig*.exe`).
- Roda o harness completo (8/8): build onedir, updater, diffs, sync, rollbacks.
- **Critério de sucesso**: `RELEASE_EXIT=0` + as linhas `PASS` do harness (12 PASS). NÃO é sucesso se houver qualquer `FAIL`.

### 3.1 SE o harness falhar com o SigUpdater

Erro típico: `FAIL: SigUpdater.exe não corresponde ao artefato conhecido como bom`.

Causa: o `release.py` recompila o `SigUpdater.exe` (PyInstaller determinístico) e o hash novo diverge dos metadatas quando o `updater.py` muda.

Resolução (sempre que o `updater.py` for alterado):

```bash
# 1. Recompilar o updater (determinístico — mesmo ambiente do release)
rm -rf /d/d/tmp/updater-rebuild && mkdir -p /d/d/tmp/updater-rebuild
SOURCE_DATE_EPOCH=946684800 PYTHONHASHSEED=0 "C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" -m PyInstaller \
  --noconfirm --clean --onefile --windowed --noupx --name SigUpdater \
  --distpath /d/d/tmp/updater-rebuild --workpath build/updater_v2 --specpath build/updater_v2 updater_v2/updater.py

# 2. Copiar para o bin de referência
cp /d/d/tmp/updater-rebuild/SigUpdater.exe updater_v2/bin/SigUpdater.exe

# 3. Atualizar os DOIS metadatas com o size + sha256 novos
#    (scripts/updater_artifact.json e updater_v2/artifact.json)
"C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" -c "import hashlib; print(len(open('updater_v2/bin/SigUpdater.exe','rb').read()), hashlib.sha256(open('updater_v2/bin/SigUpdater.exe','rb').read()).hexdigest())"

# 4. Limpar o diretório parcial e RE-RODAR o release
rm -rf release/generated/YYYYMMDD_NNN release_*.log
```

## 4. Sync no Cloudflare R2 (o diff — só o que mudou)

```bash
"C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" scripts/sync_r2.py \
  --package release/generated/YYYYMMDD_NNN/package --version YYYYMMDD_NNN
```

- **O `--package` DEVE apontar para a pasta `package/`** (a onedir full solta) — NUNCA a raiz `release/generated/<v>` (isso quebrou o manifesto com `package/_internal` aninhado).
- O script: calcula o MD5 local, lista os ETags do R2 (1 chamada), sobe SÓ os que mudaram e publica o `sync_manifest.json` assinado.
- Saída esperada: `subir: N` (N pequeno — só o diff) + `sync_manifest.json publicado no R2`.
- **Verificação pós-sync** (obrigatória):

```bash
"C:/Users/Gustavo/AppData/Local/Programs/Python/Python311/python.exe" -c "
import sys; sys.path.insert(0, 'updater_v2'); import updater
m = updater.fetch_sync_manifest()
print('manifesto R2:', m['version'], len(m['files']), 'arquivos')
"
```

Deve imprimir a versão nova. Se falhar, o manifesto não foi publicado corretamente.

## 5. GitHub Releases (full + instaladores — SEM os executáveis avulsos)

```bash
cd "D:/Projetos/SIG Windows/release/generated/YYYYMMDD_NNN"
gh release create YYYYMMDD_NNN ./YYYYMMDD_NNN_full.zip ./setup_sig_YYYYMMDD_NNN.exe ./online_setup_sigYYYYMMDD_NNN.exe \
  --repo spigknot/SIG-Windows --title "SIG Windows YYYYMMDD_NNN" --notes "<descrição>"
```

- **NÃO** subir `sig.exe`/`SigUpdater.exe` como assets avulsos — eles são servidos pelo R2 (o `github_url` do manifesto aponta para o R2.dev).
- Se a release ficar em draft (upload interrompido): `gh release edit YYYYMMDD_NNN --draft=false`.
- **Regra "só a versão atual"**: deletar a release anterior EXCETO a versão-ponte
  `20260821_013` (MANTER no GitHub — os PCs antigos, ainda no Drive/sync antigo,
  baixam o `sig.exe`/`SigUpdater.exe` da `013` de lá durante a migração). A `013`
  pode ser deletada só quando não houver mais PCs na `012` ou anterior.
  ```bash
  gh release delete <VERSAO_ANTERIOR> --repo spigknot/SIG-Windows --yes
  ```

## 6. Commit e push

```bash
cd "D:/Projetos/SIG Windows"
rm -f release_*.log sync_*.log          # NUNCA commitar os logs
git add -A
git commit -m "Versao YYYYMMDD_NNN: <descrição curta>"
git push origin main
```

## 7. Verificação final (antes de declarar pronto)

1. O manifesto no R2 aponta a versão nova (o comando da seção 4).
2. A release do GitHub tem o full.zip + os 2 instaladores; a anterior foi deletada.
3. O `git status` limpo (sem logs, sem `r2_config.json`, sem chaves).
4. Teste real: atualizar uma instalação antiga pelo app (deve baixar o diff do R2 e relançar na versão nova) — o log do updater deve ter `Atualização aplicada e validada`.

## 8. Entrega (relatório final obrigatório)

Ao concluir, reportar APENAS valores reais das saídas dos comandos:

1. A versão publicada (`YYYYMMDD_NNN`).
2. O resultado do harness (número de PASS — esperado 12, com `RELEASE_EXIT=0`).
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
| `no matches found for C:/...` no `gh` | shell MSYS trata `C:/` como glob | `cd` no diretório e usar `./arquivo` |
| `SigUpdater.exe não corresponde ao artefato bom` | `updater.py` mudou e o hash do fresh divergiu | seção 3.1 (recompilar + atualizar os 2 metadatas) |
| Google bloqueia `.exe` como malware | Drive flagra PyInstaller (aposentado — R2 não bloqueia) | se o R2 algum dia bloquear: assets avulsos no GitHub + `--github-tag` |
| `[Erro: 13] Permission denied` no lock | updater sem admin / SIG aberto | fechar o SIG; executar o updater como Administrador |
| `HTTP 1010` no R2.dev | User-Agent de bot (urllib) | o updater/app usam o UA `SigUpdater/2.0 (+https://github.com/spigknot/SIG-Windows)` — nunca o UA do urllib |
| sync_r2 subindo 1791 arquivos | versão antiga do script (sem o diff) | usar o diff por ETag/MD5 (list_objects) — `subir: N` pequeno |
| `RequestTimeTooSkewed` no sync_r2 (`ListObjectsV2`) | relógio do Windows dessincronizado (serviço `w32time` parado; diferença >15 min vs servidor) | iniciar o serviço e sincronizar: `powershell -c "Start-Service w32time; w32tm /resync"` (com elevação); conferir com `date -u` vs `curl -sI https://api.cloudflare.com | grep -i ^date:` |
| O `release_*.log`/`sync_*.log` entram no commit | `git add -A` pegou os logs | `rm -f release_*.log sync_*.log` ANTES do `git add` |

---

## Contexto da transição (histórico)

- `20260821_012`: sync pelo Drive + `--github-tag` (assets dos executáveis no GitHub por causa do malware do Google).
- `20260821_013` (PONTE): updater/app passam a buscar o manifesto no R2; publicada ainda pelo Drive para as instalações antigas migrarem.
- `20260821_014` em diante: **publicação exclusiva pelo R2**; o Drive fica congelado na `013` (portão de entrada para versões antigas) e o GitHub só tem full + instaladores.
- Um PC antigo faz 2 atualizações em sequência na migração: `013` (ponte, via Drive) → `014+` (via R2).
