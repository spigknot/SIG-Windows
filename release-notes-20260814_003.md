# SIG Windows 20260814_003

Pacote completo para instalação nova ou reparo.

- Configurações reorganizadas em duas colunas:
  - Coluna 1: Policial, Chaves API, Transcrição e Paralelismo.
  - Coluna 2: Histórico, Oitiva, Extração de partes e Qualificação.
- A seção genérica Texto foi removida; cada tarefa agora tem seus próprios
  modelos: Histórico e Oitiva com dois modelos e raciocínio cada; Extração de
  partes e Qualificação com um modelo e raciocínio.
- Checkbox "Requisições REST" alinhada ao seletor de modelo na Transcrição.
- Prévia do documento: a caixa agora abraça o documento com margens laterais
  mínimas e ganhou contorno fino; o zoom e o salvamento não geram mais linhas
  no log de atividade.

> Instalação: extraia o ZIP e execute `sig.exe` (mantenha `_internal` ao lado).
> Atualização automática: use a incremental do Drive.
