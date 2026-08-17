# Relatório — Dependências não utilizadas (varredura 2026-08-17)

Análise: 30 arquivos .py (Windows) + 55 arquivos .kt (Android).
Nada foi removido — apenas o levantamento.

## Windows (`requirements.txt`)

### LIXO CONFIRMADO (nenhum import em nenhum arquivo)

| Dependência | Evidência |
|---|---|
| **websockets==15.0.1** | 0 imports em `src/`, `updater_v2/`, `scripts/`. O app usa só o `websocket-client` (o import `websocket`). Lixo real — pode remover. |

### Do toolchain de build (PyInstaller) — NÃO são lixo do app

| Dependência | Observação |
|---|---|
| altgraph==0.17.5 | interna do PyInstaller |
| pefile==2024.8.26 | interna do PyInstaller |
| pyinstaller-hooks-contrib==2026.6 | hooks do build |
| pywin32==311 / pywin32-ctypes==0.2.3 | usadas pelo PyInstaller no Windows (manifestos/icon) |

Essas 4 só existem porque o requirements também alimenta o ambiente do
PyInstaller. Removê-las NÃO muda o app (o PyInstaller as instala por conta),
mas é seguro deixar — é o toolchain, não o runtime.

### Confirmadas USADAS (os "falsos positivos" do nome)

- google-api-python-client etc. → o código importa `googleapiclient` (o sync_publish) ✓
- pillow → o import `PIL` ✓
- websocket-client → o import `websocket` ✓ (todos os WS)
- pypdfium2, numpy, onnxruntime, webrtcvad → imports diretos ✓

## Android (`app/build.gradle`)

### Redundante explícita (não é lixo puro)

| Dependência | Evidência |
|---|---|
| **com.arthenica:smart-exception-java:0.2.1** | O código não importa a classe — mas ela é **dependência transitiva do ffmpeg-kit** (`com.arthenica:ffmpeg-kit`), que o app usa pesado. Declará-la é redundante (o Gradle já a traz); remover a linha explícita é seguro e o APK não muda. |

### Confirmadas USADAS

- okhttp 4.10.0 (31 imports okhttp3 + okio) ✓
- junit, mockwebserver, org.json — usados nos 3 arquivos de teste ✓

## Conclusão

Remoção segura sugerida (2 itens):
1. `websockets==15.0.1` do requirements.txt (Windows) — lixo real.
2. `smart-exception-java` explícito do build.gradle (Android) — redundante
   (a transitiva do ffmpeg-kit cobre; APK final idêntico).

Nenhuma outra dependência sem uso foi encontrada.
