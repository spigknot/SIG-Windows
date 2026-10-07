# Auditoria do Smart Insert — 07/10/2026

Pedido: corrigir Inserir áudio, conservando a vantagem de copiar o principal
e codificar apenas a inserção/emenda quando isso produzir uma saída confiável.
O usuário autorizou recodificação contínua, com aviso, para os codecs em que
as emendas não forem confiáveis. Não houve build, publicação ou instalação.

## Reprodução

A matriz inicial exercitou 96 exportações: oito codecs (AAC, MP3, Opus,
Vorbis, WMA, PCM, ALAC e FLAC), duas modalidades, quatro tempos de efeito
(0, 0,2, 0,5 e 1 segundo), além de inserções próximas do início e no fim.
Os sinais sintéticos permitiram comparar a saída decodificada e localizar
repetições; a duração do cabeçalho, sozinha, não foi considerada prova.
Logs integrais e protótipos ficam em `build/smartinsert_audit/`, ignorado pelo Git.

Problemas encontrados:

- Cortes por pacote copiavam amostras também presentes na emenda recodificada.
  PCM e ALAC repetiam trechos e aumentavam a duração.
- Emendas de codecs com atraso, padding ou dependências entre frames não
  preservavam uma timeline confiável. Opus chegava a acrescentar aproximadamente
  149 ms; Vorbis produziu duração declarada próxima de 25 horas em um teste
  cuja timeline deveria ter aproximadamente 10 segundos.
- A concatenação convencional de FLAC reutilizava metadados/números de frames
  de peças independentes. Duração declarada, áudio decodificado e seek divergiam.
- A duração arredondada do banner do FFmpeg (8,14 em vez de 8,137 s) criava
  sobras no fim e alterava os limites dos filtros.
- Prévia e exportação limitavam o fade do Smart Insert de maneiras diferentes
  junto às extremidades. Sobras menores que 1 ms também eram desconsideradas.
- O fallback usava regras de crossfade do Reencode Completo, alterando o efeito
  escolhido no Smart Insert e encurtando a timeline.
- A escolha de encoder pela extensão trocava Opus por Vorbis e ALAC por AAC
  no caminho de recodificação. Normalização em float32 também perdia os bits
  inferiores de PCM32.
- O resultado final não era publicado por uma etapa atômica após validação.

## Alternativas investigadas

Um protótipo para AAC conservava pacotes e usava múltiplas entradas de edit
list no MP4 para remover os atrasos internos. O cabeçalho ficou correto, mas
a decodificação ainda gerava 1.472 amostras extras em 48 kHz (30,67 ms).
Essa solução não foi incorporada. Concatenar peças independentemente
codificadas e aceitar somente a duração declarada também foi rejeitado.

Para FLAC nativo, a remontagem foi implementada segundo as regras de blocos
variáveis, números de amostras, STREAMINFO e CRC do
[RFC 9639](https://www.rfc-editor.org/rfc/rfc9639.html). Os subframes comprimidos
copiados permanecem intactos. São alterados os headers, seus CRCs e os
metadados que dependem da timeline.

## Limites de precisão do codec

No Opus/Ogg, o granule final inclui pre-skip. No teste de 8,137 s, FFprobe
mostra 8,1435 s no container e o decoder entrega exatamente 390.576 amostras
em 48 kHz: 8,137 s. A aplicação desconta o pre-skip ao calcular a duração.

AAC e WMA podem expor padding ou granularidade do codec na decodificação
bruta. O teste WMA de entrada declarou 6,001 s e decodificou 5,973333 s.
A recodificação contínua evita atrasos adicionais nas emendas, mas não torna
WMA um formato de contagem exata de amostras. Os testes distinguem essas
limitações de repetições e atrasos introduzidos pela ferramenta.
