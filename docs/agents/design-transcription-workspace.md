# Aba Transcrição: espaço de trabalho integrado

## Objetivo
Exibir a fila do lote, o histórico persistente e o conteúdo da tarefa selecionada
na mesma aba, sem substituir a ferramenta por outra tela.

## Escolha de layout
- Controles de entrada e opções permanecem no topo, em toda a largura.
- À esquerda, cartão **Arquivos para transcrever**, com a tabela estreita já
  aprovada. Preservar a redução de Arquivo original/Status e o espaço economizado.
- À direita, **Sessões** no topo esquerdo do gerenciador e a tabela de
  transcrições por modelo no topo direito. Data permanece com 120 px; Nome usa
  metade de sua largura anterior. A seção encolhe pelo espaço economizado e a
  tabela de transcrições recebe esse espaço, sem rolagem horizontal em Sessões.
- O texto completo ocupa a largura do gerenciador abaixo das duas tabelas;
  as divisórias permitem ajustar altura e largura sem esconder os controles.
- O título **Arquivos para transcrever** usa o mesmo estilo/fonte de Sessões.
  O contador da fila fica na mesma linha, à direita do título, sem consumir
  altura da tabela; o valor completo continua disponível em tooltip.
- Temporários ficam no rodapé esquerdo, alinhados à tabela da fila.
- **Juntar** fica no cabeçalho de Sessões, alinhado à direita. Renomear e Excluir
  ficam no menu de contexto; clicar em uma sessão não selecionada seleciona-a,
  enquanto clicar em uma sessão da multisseleção preserva os alvos da junção.
- As células da tabela de transcrições mostram balões com o valor completo,
  usando o mesmo estilo dos tooltips do aplicativo; textos longos têm rolagem.
  Busca e bloco de metadados redundantes não ocupam espaço no gerenciador.
- Raio, disquete, pasta e progresso permanecem no rodapé global, nas posições
  já aprovadas. Remover os botões de navegação Transcrições/Voltar.

A seção de sessões conserva somente data/nome e ações compactas, liberando a
maior largura para comparar resultados. O texto completo abaixo permite ler
sem reduzir a área de comparação a uma coluna estreita na janela mínima.

## Contratos preservados
`TranscriptionsPanel` continua dono de widgets e ações; `transcription_history`
continua dono da persistência/exportação. Nenhuma migração dos dados é necessária.
O gerenciador fica fora do bloqueio recursivo de controles do lote; limpar
`temp/` continua exigindo que todas as tarefas do aplicativo estejam ociosas.
Atualizar o histórico ao entrar na aba e após `history_saved`, mantendo seleção
e ações. O texto da prévia permanece somente leitura.

## Verificação
### Refinamentos de densidade e leitura por modelo
- Os quatro cabeçalhos usam Tool.Section.TLabel e Segoe UI Semibold 10; os
  contadores são informação secundária na mesma linha dos títulos.
- Arquivo original na prévia passa de 220 para 132 px (-40%); os modelos
  repartem o restante da largura disponível igualmente, inclusive após resize.
  Apenas uma quantidade excepcional de modelos pode exigir rolagem horizontal.
- A altura padrão da leitura passa de 220 para 110 e a do topo de 300 para
  410, transferindo diretamente o espaço economizado para as tabelas. As
  divisórias permanecem ajustáveis e não são reinicializadas a cada evento.
- O título da leitura contém o nome completo do arquivo selecionado; mantém
  uma linha de altura e um tooltip, evitando que nomes longos reduzam a leitura.
- Seletores mutuamente exclusivos Todos/por modelo ficam acima do texto e
  têm rolagem horizontal quando necessário. Todos usa os delimitadores pedidos,
  títulos somente dos modelos e textos entre aspas; um modelo mostra o texto
  integral puro. A troca de arquivo preserva o filtro; a troca de sessão inicia
  em Todos. Refresh de sessão intacta preserva filtro e posição de leitura.
- As três tabelas usam branco/#f4f7f6, como Policial/Diárias, sem alterar a
  implementação de Diárias. Recalcular a paridade ao remover itens da fila.
- Temporários mantém o rodapé esquerdo e as mesmas proteções de limpeza, em
  um cartão compacto: título/atualizar no topo e uso/limpar na segunda linha.
  Usar nomes curtos nas ações e tooltips, sem modificar raio/disquete/progresso.

Testes com o SigApp completo e armazenamento isolado: simultaneidade das três
tabelas; proporções da fila em aumento/redução da janela; janela mínima
1220x820; ações de histórico/exportação/temporários sem recorte; atualização
após salvar e retornar de outra aba; ajuste das divisórias; independência dos
estados durante/final do lote. Executar syntax/ui-smoke e reconstruir pelo
runbook UPDATE.md. Inspecionar captura real em tamanho mínimo e amplo.
