# SIG Windows

Aplicativo desktop do SIG para transcricao, processamento local com FFmpeg e ferramentas auxiliares.

## Codigo-fonte

- `src/sig_app.py`: interface e fluxos principais.
- `src/assistant_prompts.py`: prompts usados pelas ferramentas de texto.
- `src/vad_worker.py`: processamento local de VAD.
- `assets/`: imagens, icone e lista de nomes usada pelo aplicativo.
- `sig.spec`: configuracao do PyInstaller.

As chaves de API sao fornecidas pelo usuario nas configuracoes e nao fazem parte do codigo-fonte.

## Executavel completo

O pacote completo publicado nas releases inclui `sig.exe`, `SigUpdater.exe`, `ffmpeg.exe`, `ffplay.exe`, `_internal` e `vad_deps`. O executavel sozinho nao substitui esse pacote em uma instalacao nova.

## Compilacao

Com Python 3.11 e as dependencias `Pillow`, `sounddevice`, `websocket-client` e `pyinstaller` instaladas:

```powershell
pyinstaller --noconfirm --clean sig.spec
```

Para uma instalacao completa, copie tambem os binarios FFmpeg/FFplay e a pasta `vad_deps` para a pasta de distribuicao. O `SigUpdater.exe` e publicado como componente precompilado junto do pacote completo.

