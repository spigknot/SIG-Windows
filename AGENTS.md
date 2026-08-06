# Instrucoes permanentes do SIG Windows

Estas regras sao obrigatorias para futuras alteracoes, compilacoes e publicacoes.

## Build do aplicativo

- O SIG Windows deve ser compilado em modo **onedir**.
- Nunca voltar para one-file/one-exe. O modo one-file extrai `python311.dll` para `_MEI...` e ja causou falhas em outros computadores.
- O executavel final deve ficar ao lado da pasta `_internal`:
  - `sig.exe`
  - `_internal\python311.dll`
- O `sig.spec` ja usa `COLLECT`. Nao remover essa etapa.
- Antes de cada publicacao, atualizar `APP_VERSION` em `src\sig_app.py` para a mesma versao do ZIP e do `latest.json`.
- O PyInstaller e o `sounddevice` devem estar no mesmo ambiente Python. Ambiente usado nesta maquina:
  `C:\Users\Gustavo\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`
- Antes de compilar nesse ambiente, confirmar:
  `python -c "import sounddevice"`
- Tambem confirmar:
  `python -c "import websocket"`
- O build precisa incluir `sounddevice`, `_sounddevice_data` e as DLLs do PortAudio.
- O build precisa incluir o pacote `websocket-client`, importado pelo aplicativo como `websocket`.
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

## Atualizacao incremental pelo Drive

- Pasta sincronizada: `X:\Meu Drive\Updater\Sig`
- Pasta Drive: `1-yrsmFu_lAe0dMPo4sK70QRYGqMFcHJK`
- Manifesto: `latest.json`
- ID do manifesto: `1Gompo26SsyhSdliBGNaedLhEfidB244E`
- O ZIP incremental deve usar a proxima versao `YYYYMMDD_NNN.zip`.
- A versao precisa ser consistente em tres lugares: `APP_VERSION` em `src\sig_app.py`, `version` em `latest.json` e o nome do ZIP. Nunca publicar quando esses valores forem diferentes.
- Mesmo uma compilacao sem mudanca funcional precisa receber uma nova versao interna antes de ser publicada.
- Para uma instalacao onedir, o ZIP incremental deve conter na raiz `sig.exe` e `_internal\` juntos.
- Nunca publicar um ZIP contendo apenas um `sig.exe` quando a instalacao de destino for onedir.
- O ZIP deve ser montado a partir da compilacao recem-gerada, nunca de um `sig.exe` antigo que ja estava em `dist`.
- O manifesto deve conter `schema`, `version`, `zip_file_id`, `zip_name`, `sha256`, `size`, `created_at` e `signature`.
- Assinar usando `release\sign_manifest.py` e a chave privada local.
- Nunca enviar `release\update_private_key.pem` ao GitHub ou ao Drive.
- Depois de fazer upload, conferir se o ZIP e o `latest.json` sincronizaram na unidade X.
- Atualizar o manifesto existente no Drive; nao criar duas copias de `latest.json` nem reenviar o mesmo ZIP.

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
7. Verificar no Drive a versao, o tamanho e o SHA-256 publicados.
8. Conferir no log do updater a linha `Atualização aplicada e validada`; nao considerar concluido apenas porque apareceu `SIG atualizado iniciado; aguardando validação`.
9. Abrir o SIG atualizado e conferir em Sobre que a versao exibida e a mesma do manifesto. Se a versao antiga continuar aparecendo, o `APP_VERSION` nao foi atualizado.
10. Confirmar que o SIG atualizado nao volta a oferecer a mesma versao imediatamente.

## Diagnostico do updater

- O updater independente `SigUpdater.exe` deve permanecer ao lado do SIG numa instalacao completa.
- Erro `Failed to load Python DLL ... _MEI...` indica distribuicao one-file ou falha na extracao temporaria; reconstruir em onedir e incluir `_internal` no pacote.
- Se o log disser que `_internal` e `sig.exe` foram instalados, mas a versao nao mudou, verificar primeiro `APP_VERSION` antes de culpar a copia.
- Se o log parar em `aguardando validacao`, aguardar a linha final de validacao e conferir o processo; nao publicar outra tentativa sem diagnosticar.
- Testar o executavel instalado com o diretorio de trabalho apontando para a pasta que contem `ffmpeg.exe`, `ffplay.exe`, `vad_deps` e `_internal`.
