# SIG Windows 20260816_002

## Novidades

- **Conversões paralelas por núcleos**: as opções agora seguem o processador —
  n/2, n, 2n e 4n núcleos (ex.: 6 núcleos → 3, 6, 12, 24; Xeon de 18 → 9, 18, 36, 72).
  O valor salvo fora das opções é ajustado para o número de núcleos.
- **Instalador oficial** (novo asset): `sig_setup_20260816_002.exe` instala o app na
  pasta escolhida (padrão `C:\Program Files\SIG`) e cria atalhos na área de trabalho
  e no menu iniciar para o SIG e para o SigUpdater, além do desinstalador.

Pacote full para instalação nova, incluindo runtime onedir, FFmpeg, VAD e SigUpdater.
