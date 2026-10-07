# Correções do SmartCut — 07/10/2026

Esta etapa corrige a ferramenta Cortar do SIG Windows. A análise original está
em `smartcut-audit-2026-10-07.md`; seus resultados descrevem o código anterior.
O Smart Insert continua aguardando a conclusão desta base de corte.

## Comportamento entregue

- O vídeo seleciona os quadros da fonte em `[início, fim)`, preservando seus
  timestamps, inclusive em VFR. Apenas bordas necessárias são recodificadas;
  GOPs completos continuam em cópia. Bordas abaixo de 50 ms não desaparecem.
- O planejamento considera B-frames e imagens anteriores ao CRA de HEVC aberto.
  A cópia limita o número de pacotes e a montagem alinha o atraso de decodificação.
  Um índice de seek impreciso é corrigido por cópia baseada nos índices dos
  pacotes, sem recodificar o miolo.
- As bordas mantêm codec, formato de pixels, SAR e sinalização de cor disponível.
  A rotação volta na montagem final. HEVC usa `hev1` para permitir parâmetros
  distintos entre bordas e corpo.
- O áudio do vídeo vem da fonte em uma passagem contínua. A política de precisão
  recodifica em AAC, mantém as faixas e seus formatos e preserva atrasos como
  silêncio. A política de cópia realmente copia o áudio e conserva sua limitação
  de precisão aos pacotes.
- SmartCut e Reencode Completo de áudio puro usam o mesmo corte por amostras e
  o mesmo encoder. Não há ganho de cópia parcial nesse caso. A interface explica
  isso e lembra que recodificar áudio costuma ser muito mais leve que vídeo.
- O Reencode Completo de vídeo também respeita os timestamps e limites de
  apresentação, permitindo comparar seu áudio com o do SmartCut.
- As saídas são preparadas em diretório temporário, validadas e só depois
  publicadas. Falha ou cancelamento preserva a saída anterior e limpa as peças.

Fallback integral de vídeo é explícito no log: codec sem suporte a emendas,
ausência de FFprobe, intervalo sem GOP completo copiável ou encoder incompatível
com o codec da fonte. Recorte de área também exige recodificar o vídeo inteiro.
Falha de validação não dispara recodificação integral silenciosa.

## Verificação com mídia real

`tests/test_smart_cut_ffmpeg_integration.py` usa FFmpeg/FFprobe locais e fontes
sintéticas, sem dados de usuário. Verifica conteúdo dos quadros após decodificação,
ordem e duração, igualdade do PCM entre modos, ausência de avisos do decoder e
ausência de temporários publicados.

Casos: H.264/HEVC com zero/dois B-frames; intervalo inteiro; cortes em keyframe e
imediatamente antes/depois; bordas curtas; intervalo sem miolo copiável; VFR;
origem temporal não zero; duas faixas de áudio com taxas/canais diferentes;
áudio atrasado; vídeo sem áudio; rotação; HEVC de 10 bits com sinalização BT.2020/PQ.

Áudio puro: AAC, MP3, Opus, Vorbis, FLAC, ALAC, PCM/WAV e WMA. Os oito codecs
produziram PCM idêntico entre SmartCut e Reencode Completo. PCM/WAV também foi
comparado diretamente com a fatia de amostras da fonte.

Codec com perdas ainda pode ter padding do último pacote ao decodificar; a
igualdade verificada é entre as saídas dos dois modos, não uma promessa de
identidade com a fonte comprimida. Vídeo continua limitado aos quadros existentes
na fonte; sua borda recodificada pode ter perda normal do encoder.

Medição local em CPU, fontes sintéticas H.264 a 25 fps, incluindo planejamento,
montagem e validação: corte de 57,2 s em 1920 × 1080 copiou **1.400/1.430 quadros**
e recodificou somente **30** nas bordas. SmartCut levou **5,63 s**, contra **9,95 s**
do Reencode Completo. O corte de 27,2 s em 1280 × 720 copiou **650/680 quadros**,
mas levou **3,78 s**, contra **3,51 s** do integral. Os dois produziram as durações
e contagens esperadas. O custo fixo de sondagem, processos e validação pode eliminar
o ganho em vídeos leves. São medições desta máquina, com a suíte em execução,
não uma garantia de velocidade para toda mídia; logs `benchmark*.txt`.

## Transição zero e três durações

Cortar não oferece transição. A comparação solicitada foi adicionada ao SmartJoin,
que oferece esse controle: `0`, `0,2`, `0,5` e `1` segundo, com **Fade in/out** e
**Fundir**. Três clipes de 6 s resultam em:

| Transição | 0 s | 0,2 s | 0,5 s | 1 s |
| --- | ---: | ---: | ---: | ---: |
| Fade in/out | 18 s | 18 s | 18 s | 18 s |
| Fundir | 18 s | 17,6 s | 17 s | 16 s |

Zero não aplica `afade`, `acrossfade` nem `xfade` e não recodifica vídeo. O teste
revelou deslocamento de aproximadamente 21 ms causado pelo priming AAC no concat;
os timestamps do vídeo foram rebaseados mantendo os pacotes em cópia.

## Evidências locais

Logs e protótipos ignorados pelo Git ficam em `build/smartcut_audit/`, incluindo
`unit-final.txt`, `focused-tests.txt`, `zero-tests.txt`, `full-suite.txt`,
`full-summary.txt` e `ui-smoke.txt`. O log focused registra a falha intermediária
do zero; `zero-tests.txt` registra a correção aprovada.

Verificação final: **1.359 testes passaram**, sem falhas, erros ou skips, em
286,64 s. A suíte usa a mesma descoberta de `tests/` e `updater_v2/` do comando
canônico, com runner local em `build/` para preservar o diagnóstico integral.
Inclui os dez testes nativos do SmartCut com **51 exportações reais**, os testes
nativos do SmartJoin e a matriz de oito combinações de tempo/efeito. Os gates
canônicos **syntax** e **ui-smoke** passaram. `git diff --check` também passou.

Encoders por GPU não foram exercitados com mídia real; os testes de integração
usam CPU. O smoke verifica a construção da interface, sem revisão visual de
reprodução num player. Nenhuma compilação, publicação ou instalação foi feita.
