# Gerenciador de Transcrições

## Objetivo

A navegação Transcrição → Transcrições substitui somente o conteúdo da
ferramenta e permite voltar sem perder a fila. A nova tela permite consultar,
renomear, juntar, visualizar e exportar tabelas de tarefas anteriores, além
de medir e limpar os temporários.

## Decisões e limites

- **Persistência local:** um JSON por tarefa em `%APPDATA%/sig/transcricoes/`,
  fora do diretório `temp/` e do executável. Usa escrita temporária seguida
  de substituição atômica. Nenhuma transcrição é publicada ou enviada a
  outro serviço pelo gerenciador.
- **Fonte dos registros:** jobs e estatísticas ao gerar o relatório normal ou
  ao cancelar a tarefa, independentemente da aceitação do HTML parcial. O
  snapshot parcial usa somente resultados em memória da execução atual,
  nunca TXT reaproveitado. Não guardar preferências nem chaves.
  A preservação automática começa com esta versão: execuções antigas que
  não foram registradas não podem ser recuperadas magicamente.
- **Interface:** histórico pesquisável à esquerda, prévia da tabela e texto
  completo por arquivo à direita, temporários no rodapé. Nome inicial inclui
  data, quantidade de arquivos e modelos; o usuário pode renomear.
- **Exportação:** HTML reutiliza o layout de `reporting.py`; CSV UTF-8 com BOM
  e separador `;` atende ao Excel sem acrescentar dependências de runtime.
  Prefixos de fórmula são escapados como texto, inclusive em nomes/modelos.
- **Junção:** união exata por nome de arquivo. Registros e colunas originais
  ficam intactos; uma nova tabela é persistida. Modelos repetidos recebem
  sufixos para não sobrescrever resultados. Arquivos ausentes ficam vazios.
  Nomes duplicados dentro de um mesmo registro bloqueiam a junção ambígua,
  em vez de descartar silenciosamente uma transcrição.
- **Temporários:** medição em worker, atualização dos widgets na thread Tk;
  limpeza requer confirmação e não é permitida enquanto há tarefa usando
  os temporários. Links/junctions são ignorados, e uma raiz reparse é
  recusada. Prévia de navegador fica em `temp/` e é removida ao excluir o
  registro. Histórico fica fora da limpeza.
- **Estados independentes:** desabilitar controles do lote não altera os
  estados de consulta/exportação do gerenciador nem libera o texto de prévia
  para edição.

## Donos

- `transcription_history.py`: persistência, junção, exportação e disco.
- `transcriptions_panel.py`: widgets, busca, seleção e ações.
- `sig_app.py`: navegação, eventos do worker, gravação ao concluir e integração.

## Fases e verificação

1. Persistência e junção sem Tk, com arquivos de teste isolados.
2. Interface com botões reais e confirmação antes de excluir/limpar.
3. Integração com a tarefa, ida/volta, estados durante execução, largura de
   aproximadamente 40% e coluna Status centralizada.
4. Gates `syntax` e `ui-smoke`, testes de contrato/integrados, rebuild pelo
   `scripts/build_dev.py` e conferência dos módulos no executável.

Vacinas: `tests/test_transcription_history.py` e
`tests/test_transcriptions_integration.py`. Capturas de demonstração usam
somente fixtures, não dados ou configurações do usuário.
