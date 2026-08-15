# SIG Windows 20260814_012

Pacote completo para instalação nova ou reparo.

## Novo mecanismo principal de atualização: sincronização por arquivo

- O atualizador baixa um **manifesto assinado** com o hash de cada arquivo,
  compara com a instalação local e baixa **apenas o que mudou** (com
  progresso por arquivo na tela); arquivos que saíram do pacote são
  removidos automaticamente. Qualquer versão instalada converge para o
  estado atual.
- Instalações muito desatualizadas (>100 arquivos) recebem sugestão de usar
  o pacote completo.
- O incremental ZIP e o pacote completo do GitHub continuam disponíveis
  como contingência.

## Outras mudanças

- Checkboxes "Declarações"/"Depoimento" acima do botão "Gerar documento";
  botão centralizado no vão entre as caixas (vertical e horizontal).
- Caixa de qualificação com a mesma altura da prévia do documento
  (perfeitamente alinhadas).
- build_dev sincroniza `prompts/` e `modelos/` da raiz para `dist/`.

> Instalação: extraia o ZIP e execute `sig.exe` (mantenha `_internal` ao lado).
> Atualização: abra o `SigUpdater.exe` (Verificar → Atualizar).
