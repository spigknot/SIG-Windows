# SIG Windows 20260814_002

Pacote completo para instalação nova ou reparo.

- Prévia do documento em zoom de 100% agora mostra o tamanho físico real de
  impressão (calibrada pelo DPI físico do monitor, via `GetDpiForMonitor`).
- Separador entre páginas da prévia com respiro: duas linhas em branco antes
  e duas depois do traço (apenas visual; o documento não muda).
- Atualizador sincronizado: modo independente (GUI) recompilado e hashes do
  artefato atualizados — o binário estava defasado em relação ao código-fonte.
- Novo `scripts/drive_upload.py` para publicação incremental via API do Drive.

> Instalação: extraia o ZIP e execute `sig.exe` (mantenha `_internal` ao lado).
> Atualização automática: use a incremental do Drive.
