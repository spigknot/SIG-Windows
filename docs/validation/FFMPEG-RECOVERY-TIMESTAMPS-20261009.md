# FFmpeg: retomada, avisos e relógios — 2026-10-09

## Comportamento implementado

Cortar, extrair áudio, girar vídeo, juntar mídias, inserir áudio e limpar áudio registram opções e etapas concluídas. Ao reabrir o painel FFmpeg, uma tarefa interrompida pode ser retomada. As etapas prontas com saídas intactas são reutilizadas; a etapa interrompida é reiniciada. Mudança nos arquivos originais bloqueia a retomada. Conclusão e cancelamento limpam somente a pasta temporária pertencente à tarefa.

A validação de uma saída concluída passou a liberar o arquivo com aviso detalhado. Cancelamento, falha ao executar FFmpeg e ausência de saída completa continuam sendo erros. As verificações de intermediários continuam estritas, pois uma peça inadequada não deve contaminar as próximas etapas.

## Correções de mídia

- Leitura de início de container/faixa aceita timestamps negativos.
- SmartCut conserva o keyframe visível após preroll descartado e repara apenas o último GOP que depende de referência descartada.
- SmartJoin não trata FPS nominal diferente como incompatibilidade de corpo. Transição zero passa pelo planejamento de cópia, sem aplicar efeito. GOP final com referência oculta tem reparo local. O empate do perfil automático usa a taxa predominante para as emendas.
- Smart Insert aplica o deslocamento entre início da faixa e início do container. Pacotes parciais no início/fim geram apenas pequenas bordas recodificadas; o corpo continua em cópia. O EOF ALAC arredondado em até um milissegundo usa cauda/padding equivalente ao encode contínuo.
- A recodificação contínua de áudio continua reservada aos codecs em que as emendas não são confiáveis, com o motivo informado.
- A retomada cobre também conjuntos de segmentos produzidos na rotação paralela. A execução fecha os pipes dos processos para evitar vazamento de recursos.

## Evidência

- **40 testes** dos planejadores passaram.
- **8 testes** de persistência/retomada/avisos passaram. Incluem FFmpeg real: interrupção após as peças do SmartCut (retoma somente a montagem final), extração em lote após o primeiro arquivo e limpeza de áudio concluída antes da mensagem final.
- SmartCut: **10 testes, 51 exportações reais**, passaram; verificam quadros/conteúdo, VFR, H.264/HEVC, bordas, canais de áudio, rotação e precisão de amostras.
- Smart Insert: **10 testes, 130 exportações reais**, passaram; incluem transições zero/0,2/0,5/1 s, curvas, lossless e lossy, comparação com encode contínuo e ALAC com edit list/pacotes parciais.
- SmartJoin: **11 testes de mídia real**, passaram, incluindo FPS misto, transição zero, três tempos de transição, falta de áudio, GOP aberto HEVC e validação do decoder.
- **7 testes de controles da junção em Tk**, compilação Python dos fontes envolvidos e `git diff --check` passaram.

Os logs completos estão em `build/ffmpeg-hardening/`, fora do Git. Não foi gerado ou publicado pacote Windows nesta tarefa. A retomada das novas ferramentas requer tarefas iniciadas com o código atualizado; não inventa checkpoints para processamentos antigos que nunca os registraram.
