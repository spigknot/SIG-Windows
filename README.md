# SIG Windows

Aplicativo desktop do SIG para transcricao, processamento local com FFmpeg e ferramentas auxiliares.

## Codigo-fonte

- `src/sig_app.py`: interface e fluxos principais.
- `prompts/`: um arquivo `.txt` editável para cada prompt usado pelas ferramentas de texto.
- `modelos/`: modelos Word editáveis usados para gerar declarações e depoimentos.
- `src/assistant_prompts.py`: carregador dos prompts e montagem das partes variáveis.
- `src/vad_worker.py`: processamento local de VAD.
- `assets/`: imagens, icone e lista de nomes usada pelo aplicativo.
- `sig.spec`: configuracao do PyInstaller.

As chaves de API sao fornecidas pelo usuario nas configuracoes e nao fazem parte do codigo-fonte.

Os prompts podem ser ajustados diretamente nos arquivos de `prompts/`. Em uma instalação
empacotada, a pasta fica ao lado de `sig.exe`; a cópia em `_internal/prompts` é mantida como
fallback para instalações que não tenham a pasta externa.

Os modelos `modelo_declaracoes.docx` e `modelo_depoimento.docx` seguem a mesma regra:
a pasta externa `modelos/` tem prioridade, enquanto `_internal/modelos` preserva uma
cópia de segurança para instalações e atualizações.

## Pacotes

As releases do GitHub sempre incluem um pacote **full** para instalação do zero:
`sig.exe`, `SigUpdater.exe`, `ffmpeg.exe`, `ffplay.exe`, `_internal`, `vad_deps` e `vad_worker.py`.

As atualizações automáticas do aplicativo usam a **sincronização por arquivo** publicada no Google Drive: o `sync_manifest.json` assinado (schema 2) lista cada arquivo com `sha256`, `size`, `drive_id` e `github_url`; o SIG e o `SigUpdater.exe` baixam somente o que mudou e convergem de qualquer versão. A publicação é feita exclusivamente por `scripts/sync_publish.py`. O pacote ZIP incremental (schema 1) foi aposentado e permanece apenas como compatibilidade para instalações antigas.

## Compilacao

Com Python 3.11 e as dependencias `Pillow`, `sounddevice`, `websocket-client`, `cryptography` e `pyinstaller` instaladas, use o gate oficial:

```powershell
python scripts\release.py tests
python scripts\release.py updater-v2-test --package-zip <pacote-full.zip> --updater <SigUpdater.exe>
python scripts\release.py release --version <APP_VERSION> --incremental
```

O comando de release faz um build onedir limpo, recompila o updater a partir de `updater_v2/updater.py`, valida as dependências e gera o pacote incremental para o Drive, além de preservar o pacote full como `<versão>_full.zip` para a release do GitHub. Para uma instalação completa, não use apenas o `sig.exe`.
