# Instrucoes permanentes do SIG Windows

Estas regras sao obrigatorias para futuras alteracoes, compilacoes e publicacoes.

## Codigo-fonte e prompts

- Todos os prompts editáveis ficam em `prompts\`, um arquivo `.txt` por prompt:
  `historico_system.txt`, `historico_user.txt`, `oitiva_system.txt`,
  `oitiva_user.txt`, `partes_system.txt`, `qualificacao_system.txt` e
  `qualificacao_user.txt`.
- `src\assistant_prompts.py` deve permanecer apenas como carregador e montador das
  partes variáveis. Não voltar a colocar os textos completos dos prompts nesse
  módulo.
- O build empacota uma cópia em `_internal\prompts` e o pacote full também leva
  `prompts\` ao lado de `sig.exe`; a pasta externa tem prioridade para permitir
  edição sem recompilação.
- Os modelos Word editáveis ficam em `modelos\`, no mesmo nível de `prompts\`:
  `modelo_declaracoes.docx` e `modelo_depoimento.docx`. O build deve sempre
  empacotar ambos em `_internal\modelos`; em execução, a cópia externa ao lado
  do SIG tem prioridade e nunca deve ser sobrescrita se já existir.
- A cópia rica dos documentos deve exportar o DOCX pelo Word para RTF
  (`SaveAs2`, formato 6) e HTML filtrado (`SaveAs2`, formato 10). O RTF deve ir
  para o clipboard como bytes, sem passar por `Clipboard.GetData()` nem ser
  decodificado/recodificado como texto. O HTML deve respeitar o charset do
  arquivo de origem e ser convertido uma única vez para CF_HTML UTF-8 com
  offsets calculados em bytes. Sempre testar acentos como `mês`, `São Paulo`,
  `João`, `n°` e aspas tipográficas, além de negrito e justificação.

## Build do aplicativo

- O SIG Windows deve ser compilado em modo **onedir**.
- Nunca voltar para one-file/one-exe. O modo one-file extrai `python311.dll` para `_MEI...` e ja causou falhas em outros computadores.
- O executavel final deve ficar ao lado da pasta `_internal`:
  - `sig.exe`
  - `_internal\python311.dll`
- O `sig.spec` ja usa `COLLECT`. Nao remover essa etapa.
- Antes de cada publicacao, atualizar `APP_VERSION` em `src\sig_app.py` para a mesma versao do pacote gerado pelo `release.py` e do manifesto sync publicado.
- O PyInstaller e o `sounddevice` devem estar no mesmo ambiente Python.
- **Ambiente de build aprovado (por VERSOES, nao por caminho)**: Python `3.11.0` e PyInstaller `6.21.0` (o `release.py` verifica e falha com diagnostico se divergir). Nesta maquina ele costuma viver no venv do Hermes ou no fallback local `C:\Users\Gustavo\AppData\Local\Programs\Python\Python311\python.exe` — qualquer instalacao que reporte `sys.version_info[:3] == (3, 11, 0)` e `PyInstaller.__version__ == "6.21.0"` serve; os caminhos citados sao so exemplos locais.
- O Hermes pode atualizar/regenerar o ambiente dele. Antes de compilar, confirmar por versao (o gate faz isso); se o Python divergir (por exemplo, para `3.11.15`), usar outra instalacao `3.11.0` e nao trocar o hash aprovado do updater apenas por causa disso.
- Antes de compilar nesse ambiente, confirmar:
  `python -c "import sounddevice"`
- Tambem confirmar:
  `python -c "import websocket"`
- O build precisa incluir `sounddevice`, `_sounddevice_data` e as DLLs do PortAudio.
- O build precisa incluir o pacote `websocket-client`, importado pelo aplicativo como `websocket`.
- A prévia embutida dos documentos usa `pypdfium2`; o build precisa incluir
  `pypdfium2`, `pypdfium2_raw` e a DLL do PDFium fornecida pelo pacote.
- Depois de alterar a prévia, testar o fluxo DOCX -> PDF -> imagem com um dos
  modelos reais de `modelos\`, sem modificar o arquivo de modelo durante o teste.
- Testar o executavel abrindo por pelo menos alguns segundos e confirmar a existencia de:
  `_internal\python311.dll`
  `_internal\_sounddevice_data\portaudio-binaries\libportaudio64bit.dll`

## Pacote completo

Uma instalacao nova precisa conter, na mesma pasta:

- `sig.exe`
- `_internal\`
- `SigUpdater.exe`
- `ffmpeg.exe`
- `ffplay.exe`
- `vad_deps\`
- `vad_worker.py`

Nao colocar esses binarios grandes no historico normal do Git. Publicar o pacote completo como asset de uma release do GitHub.

## Atualizacao incremental (sync por arquivo)

- A rota vigente de atualização incremental é a sincronização por arquivo,
  publicada exclusivamente no Cloudflare R2 por `scripts\sync_r2.py` e consumida
  pelo `SigUpdater.exe`/SIG via `sync_manifest.json` (schema 2) assinado.

- Nunca publicar, consultar ou sincronizar atualizações pelo Google Drive.
- Manifesto: `sync_manifest.json` no R2, publicado sempre por `scripts\sync_r2.py`.
- Ciclo por release: `release.py release --version <v> --incremental` (gera
  package + `*_full.zip` + instaladores) -> `sync_r2.py --package
  release\generated\<v>\package --version <v>` -> `gh release create` com o
  pacote full e os instaladores.
- Cada arquivo do manifesto tem `github_url` público no R2; `drive_id` deve
  permanecer vazio por compatibilidade de assinatura e nunca é usado para baixar.
- A versao precisa ser consistente entre `APP_VERSION`, o pacote e o manifesto sync. Nunca publicar quando esses valores forem diferentes.
- Mesmo uma compilacao sem mudanca funcional precisa receber uma nova versao interna antes de ser publicada.
- O pacote ZIP incremental (schema 1, `latest.json`) foi APOSENTADO em 2026-08-15: o `latest.json` esta congelado na ultima versao que o tinha e serve apenas para instalacoes antigas chegarem ao sync. Nao publicar ZIP incremental novo, nao atualizar `latest.json` e nao descrever esse fluxo como atual.
- Nunca enviar `release\update_private_key.pem` ao GitHub ou ao R2.
- Nao publicar o mesmo artefato duas vezes: o sync sobe somente o que mudou (reusando IDs comprovadamente iguais) e o manifesto e atualizado no mesmo ID estavel.
- Depois do publish, conferir o manifesto sync pela API (`updater.fetch_sync_manifest()` deve apontar a versao nova).

## Seguranca

- Nunca gravar chaves de API no codigo-fonte, no executavel ou em releases.
- Nao publicar arquivos de configuracao, chaves privadas, `settings.json`, caches ou pastas temporarias.
- Se uma chave aparecer no historico publico, avisar o usuario para revoga-la e rotaciona-la.

## Verificacao antes de concluir

1. Confirmar que o SIG nao esta em execucao antes de substituir `dist\sig.exe` ou `_internal`.
2. Compilar em onedir.
3. Testar a abertura do executavel.
4. Conferir `python311.dll`, PortAudio e `sounddevice` no pacote.
5. Conferir a estrutura interna do ZIP.
6. Atualizar o manifesto e validar a assinatura.
7. Verificar no R2 a versão, o tamanho e o SHA-256 publicados.
8. Conferir no log do updater a linha `Atualização aplicada e validada`; nao considerar concluido apenas porque apareceu `SIG atualizado iniciado; aguardando validação`.
9. Abrir o SIG atualizado e conferir em Sobre que a versao exibida e a mesma do manifesto. Se a versao antiga continuar aparecendo, o `APP_VERSION` nao foi atualizado.
10. Confirmar que o SIG atualizado nao volta a oferecer a mesma versao imediatamente.

## Diagnostico do updater

- O updater independente `SigUpdater.exe` deve permanecer ao lado do SIG numa instalacao completa.
- Sem argumentos, `SigUpdater.exe` deve abrir sua interface grafica independente. Com `--zip`, `--target`, `--pid` e `--log`, deve preservar exatamente o contrato silencioso usado pelo SIG.
- Antes de alterar a pasta em que esta instalado, o modo independente deve copiar e executar a si proprio em `%LOCALAPPDATA%\sig\updater`. Nunca tentar sobrescrever o executavel do updater que estiver em execucao.
- O modo independente deve aceitar a sincronização apenas pelo manifesto assinado
  do R2 e conferir tamanho e SHA-256. O pacote full deve vir da release mais
  recente do GitHub e possuir digest SHA-256 publicado pela API.
- O modo independente deve ignorar uma sincronização cuja versão seja igual ou
  anterior à instalada; nunca oferecer novamente a mesma versão.
- O pacote full pode instalar em pasta vazia e reparar uma instalacao incompleta. Pastas nao vazias que nao sejam reconhecidas como SIG devem ser recusadas para nao substituir arquivos alheios.
- Tanto o modo chamado pelo SIG quanto o modo independente devem usar a mesma transacao, lock, validacao de startup e rollback. Nao criar um segundo caminho de copia simplificado.
- O updater deve ser compilado como `--onefile --windowed`; o SIG continua obrigatoriamente `onedir`.
- Erro `Failed to load Python DLL ... _MEI...` indica distribuicao one-file ou falha na extracao temporaria; reconstruir em onedir e incluir `_internal` no pacote.
- Se o log disser que `_internal` e `sig.exe` foram instalados, mas a versao nao mudou, verificar primeiro `APP_VERSION` antes de culpar a copia.
- Se o log parar em `aguardando validacao`, aguardar a linha final de validacao e conferir o processo; nao publicar outra tentativa sem diagnosticar.
- Testar o executavel instalado com o diretorio de trabalho apontando para a pasta que contem `ffmpeg.exe`, `ffplay.exe`, `vad_deps` e `_internal`.

## Gate oficial de build e release

- Nenhuma versao pode ser considerada concluida ou publicavel sem passar pelo comando oficial em `scripts\release.py`.
- A sequencia minima obrigatoria, executada no mesmo Python que contem PyInstaller, e:
  `python scripts\release.py preflight --quiet`
- O `preflight` executa, em ordem e com parada no primeiro erro, a suíte unitária,
  a validação do estado atual, `updater-v2-test` e `ui-smoke` (smoke test da interface).
  `--quiet` reduz somente as linhas PASS; falhas continuam visíveis.
- Para gerar uma release, usar somente:
  `python scripts\release.py release --version <APP_VERSION> --incremental`
- O modo `--incremental` faz o clean build, valida o ambiente e o artefato do
  updater, roda o harness e gera o package, o `*_full.zip` (asset da release
  GitHub) e os instaladores. A publicação do package no R2 é o passo seguinte,
  pelo `scripts\sync_r2.py`.
- Esse comando faz clean build isolado, verifica warnings criticos, inspeciona o executavel congelado, valida layout/dependencias, testa o updater real em pasta temporaria, cria o ZIP e assina o manifesto. Se uma etapa falhar, a release nao e aprovada.
- `--allow-same` existe somente para smoke test local da versao atual e nunca deve ser usado para publicar.
- O ZIP nunca deve ser criado manualmente a partir de `dist`. O `sig.exe` precisa vir do clean build desta execucao; os assets externos somente podem vir de um `--runtime-root` explicitamente escolhido e passam pelo gate de layout e pelo hash conhecido do `SigUpdater.exe`.
- O codigo-fonte de producao do `SigUpdater.exe` esta versionado em `updater_v2\updater.py`. Toda release deve recompila-lo em uma pasta limpa, validar seu hash em `scripts\updater_artifact.json` e executar o gate `updater-v2-test`, incluido no `preflight` e no harness do build limpo.
- O comando `updater-test` e legado e nao e um gate de release. Ele permanece apenas para diagnostico de compatibilidade quando for solicitado explicitamente.
- O updater e transacional: valida CRC, caminhos, duplicatas, tamanhos e arquivos essenciais antes da troca; usa diario, lock exclusivo, troca atomica por componentes, rollback e validacao de inicializacao.
- O SIG usa o `SigUpdater.exe` extraido do pacote quando ele existe. Isso permite migrar instalacoes antigas para o updater endurecido sem depender do helper possivelmente antigo que ja esta instalado.
- O helper legado esta preservado em `updater_v2\legacy\SigUpdater-legacy-20260806_004.exe` apenas para diagnostico historico; nao e fonte de novas releases.
