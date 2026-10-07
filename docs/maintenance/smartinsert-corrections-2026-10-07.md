# Correções do Smart Insert — 07/10/2026

## Estratégia final

| Principal | Processamento |
| --- | --- |
| PCM inteiro ou float em WAV/RF64 | Copia os bytes do principal em limites exatos de amostras; codifica somente o inserido. |
| ALAC em M4A | Copia os pacotes fora da emenda; codifica o inserido e somente a região entre os pacotes que contêm o corte. |
| FLAC nativo | Copia os subframes fora da emenda; codifica o inserido e a borda; remonta headers, CRCs e STREAMINFO. |
| AAC, MP3, Opus, Vorbis, WMA e combinações ainda sem cópia parcial validada | Uma recodificação contínua com aviso na tela e motivo no log, conservando o efeito do Smart Insert. |

Planos com pacotes descontínuos são rejeitados para cópia parcial. WAV
incompatível usa compatibilização contínua com motivo explícito. Erros de
execução, cancelamento e falhas de validação não publicam uma saída parcial.

## Comportamento

- Ponto de inserção, janelas e duração são calculados em amostras, usando
  duração precisa da faixa. Prévia e exportação compartilham a lógica do filtro.
- Smart Insert aplica fades somente ao áudio inserido. Não reduz a duração
  total com sobreposição. Limita cada fade à metade do inserido.
- Zero segundo e Sem transição não aplicam fade ou crossfade.
- Reencode Completo conserva suas próprias opções: Fade in/out suaviza as
  extremidades sem sobreposição; crossfade sobrepõe cada emenda existente.
- Trechos menores que 1 ms são tratados conforme sua contagem real de amostras.
- A compatibilização preserva o codec de origem quando suportado, a taxa,
  os canais e a profundidade lossless. Os filtros usam double para preservar PCM32.
- Metadados de título são preservados nos caminhos lossless testados. FLAC
  descarta seek tables antigas e invalida o MD5 original; números de amostra
  contínuos permitem seek confiável sem reutilizar posições antigas.
- Montagem e validação ocorrem em diretório temporário; a publicação final
  ocorre somente depois de sucesso e da última verificação de cancelamento.

## Validação

Os testes nativos cobrem os oito codecs, os tempos 0/0,2/0,5/1 s, todas as
curvas oferecidas no Smart Insert, pontos no início, no fim, a uma amostra
do início e em fronteira de pacote. Também cobrem PCM32, PCM unsigned/float,
FLAC24 em 44,1 kHz, ALAC estéreo, metadados, CRC e seek do FLAC.

A saída lossless é comparada amostra por amostra com uma recodificação
contínua usando a mesma semântica do Smart Insert. Testes adicionais verificam
que prefixo/sufixo conservam as amostras originais e que os corpos FLAC
copiados conservam seus bytes comprimidos. WAV/RF64 é verificado também
com leitores independentes e fixtures de formatos/alinhamentos inválidos.
Há testes para publicação após validação e cancelamento, preservando saída anterior.

Resultados finais, com FFmpeg/FFprobe 8.0.1:

- `syntax`: PASS.
- Suíte completa de `tests/` e `updater_v2/`: 1.387 testes, zero falhas,
  zero erros e zero skips. Log integral: `build/smartinsert_audit/full-suite.txt`.
- Smart Insert: 124 exportações reais na suíte, sem avisos de timestamps
  não monotônicos. Todas as comparações lossless passaram.
- Verificação independente do ganho linear: PASS. Diferença máxima de
  0,0000300865 na escala normalizada (menos de uma unidade PCM16);
  prefixo e sufixo do principal permaneceram idênticos. Duas exportações extras.
- `ui-smoke`: PASS. `git diff --check` não apontou erros de whitespace.

Uma rodada anterior reprovou quatro casos porque o título ALAC desaparecia.
A correção mapeia metadados do principal explicitamente na junção, e tanto
os 44 casos afetados quanto a repetição da suíte completa passaram.

## Desempenho

O teste com principal de 600 s e inserido de 2,137 s mostrou cópia de
599,914667 s em ALAC (emenda de 85,333 ms) e 599,904 s em FLAC (emenda de
96 ms). PCM copia todos os 600 s do principal.

O custo da montagem FLAC foi reduzido com tabelas de CRC e avanço GF(2)
por bytes, sem recalcular o CRC sobre todo o corpo comprimido. Headers
nativos WAV/FLAC fornecem contagem exata e formato, evitando sondas externas
redundantes durante a validação dessas peças.

Medição final sem os demais testes concorrendo: principal mono de 3.600 s,
48 kHz, inserido de 2,137 s em 44,1 kHz, fade linear de 0,5 s. Duas
execuções por caminho; valores abaixo são medianas do tempo total, incluindo
sondagem, montagem e validação. A referência usa o mesmo codec e os mesmos
efeitos em recodificação contínua. As 12 exportações passaram nas verificações.

| Codec | Smart Insert | Contínuo | Razão contínuo/Smart |
| --- | ---: | ---: | ---: |
| PCM16/WAV | 1,167 s | 1,970 s | 1,69× |
| ALAC/M4A | 3,552 s | 8,388 s | 2,36× |
| FLAC | 3,682 s | 4,693 s | 1,27× |

Dados e comandos de reprodução: `build/smartinsert_audit/benchmark.py`,
`benchmark-3600-results.json` e `benchmark-3600-console.txt`. Os arquivos
de áudio sintéticos da medição foram removidos ao finalizar o teste.

Áudio mono simples é muito rápido de recodificar. Inicialização de processos,
sondagem e montagem podem neutralizar parte do ganho, mesmo com quase todo o
principal em cópia. A ferramenta não promete aceleração para todo arquivo;
a cópia parcial também evita perda de qualidade no principal. Os tempos são
medições locais, dependentes de conteúdo, tamanho, codec e máquina.
