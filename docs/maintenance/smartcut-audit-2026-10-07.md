# Auditoria do SmartCut — 07/10/2026

Este documento registra a implementação anterior às correções. Veja
`smartcut-corrections-2026-10-07.md` para o comportamento e a validação posteriores.

Escopo: analisar primeiro a ferramenta Cortar do SIG Windows, conforme a mudança
de estratégia do usuário, antes de reutilizar sua lógica no Smart Insert. Esta
etapa não altera o processamento de produção. A investigação do Smart Insert
ficou em espera; seus protótipos estão somente em `build/smartinsert_audit/`.

## Resultado

O SmartCut atual ainda não é uma base confiável para reutilização. Existem erros
reproduzidos no vídeo e não há implementação de corte parcial para áudio puro:
nesse caso o modo SmartCut recodifica todo o intervalo.

Foram executados **39 cenários com FFmpeg e FFprobe 8.0.1**, sendo 31 de vídeo e
8 de áudio. Todos terminaram sem erro de execução; isso não significou que o
conteúdo produzido estivesse correto. Os **23 testes existentes** de
`tests/test_ffmpeg_cut_modes.py` passaram; os testes de fluxo simulam a execução
dos comandos e não inspecionam a mídia final.

Artefatos locais, não versionados: `build/smartcut_audit/`. O diretório contém
`audit.py`, `refine.py`, `baseline.json`, `summary.json`, os arquivos sintéticos
de entrada, cada saída, `commands.json`, `result.json` e logs completos.

## Como foi verificado

- Vídeos sintéticos de 6 s, 128 × 72, com uma cor distinta por quadro. A
  identificação dos quadros usa a fonte já comprimida e decodificada como
  referência, portanto considera as alterações de cor do primeiro encode.
- H.264 e HEVC, 25 fps, com zero ou dois B-frames na fonte. Também 30000/1001,
  VFR, timestamp inicial de 5 s e um GOP maior que o intervalo escolhido.
- Cortes em keyframes, imediatamente antes/depois deles, bordas de 40 ms,
  intervalo inteiro e intervalo curto sem miolo copiável.
- Áudio AAC, MP3, Opus, Vorbis, FLAC, ALAC, PCM/WAV e WMA. As entradas são
  sintéticas; não foram utilizados dados de usuário nem aparelhos Android.
- FFprobe verificou streams, pacotes e timestamps decodificados. FFmpeg
  decodificou as saídas; a extração dos quadros usa `-fps_mode passthrough`
  para que o verificador não crie duplicações por sincronização automática.
- Critério de comparação de conteúdo: quadros da fonte com PTS no intervalo
  `[início, fim)`. Resultados diferentes desse critério incluem tanto erros
  graves quanto arredondamentos de um quadro em cortes recodificados curtos;
  a lista `wrong_video_content` não deve ser interpretada como uma contagem
  de falhas graves sem essa distinção.

## Defeitos confirmados

### 1. Áudio puro: SmartCut recodifica tudo

Em `src/ffmpeg_tools_panel.py`, `_cut_worker` encaminha ao
`_cut_video_smartcut` somente quando `is_video` é verdadeiro. Para áudio, o
ramo final escolhe um encoder e executa um único corte recodificado. Não existe
miolo em `-c:a copy`, nem montagem de bordas de áudio. Os oito codecs testados
seguiram esse caminho. A duração desses exemplos ficou correta ou próxima,
mas o benefício de evitar recodificação integral não existe.

Consequência para o Smart Insert: a implementação atual do SmartCut de vídeo
não resolve a precisão de cortes de áudio comprimido, o atraso do encoder ou
o padding de emendas. É necessário projetar uma implementação de áudio própria,
com suporte e limites definidos por codec/container.

### 2. O miolo em stream copy inclui quadros além do fim

`_smartcut_segment_arguments` limita os segmentos com `-t`, inclusive em
stream copy. Com B-frames, esse limite não seleciona exatamente os quadros
apresentados no intervalo. A montagem final com outro `-t` também não corrige
o conjunto de quadros, nem sua ordem.

| Entrada, pedido | Duração do container | Quadros decodificados | Conteúdo observado |
| --- | ---: | ---: | --- |
| H.264, 25 fps, 2 B-frames, 2–4 s | 2,102 s | 52, esperado 50 | inclui quadros 100 e 102, em 4,00 e 4,08 s da fonte |
| HEVC, 25 fps, 2 B-frames, 2–4 s | 2,142 s | 52, esperado 50 | inclui quadros 100 e 103, em 4,00 e 4,12 s da fonte |
| H.264, 25 fps, 2 B-frames, 1,4–4,6 s | 3,302 s | 81, esperado 80 | repetição, salto e retorno na emenda |

Exemplos correspondentes: diretórios
`baseline_source_libx264_25_2_50_0_2_4_aac`,
`baseline_source_libx265_25_2_50_0_2_4_aac` e
`baseline_source_libx264_25_2_50_0_1.4_4.6_aac`.

### 3. A margem de 50 ms altera o intervalo escolhido

`SMARTCUT_MIN_EDGE = 0.05` é usado tanto para admitir keyframes fora do
intervalo quanto para deixar de recodificar bordas pequenas. Isso admite
um miolo que começa antes do início solicitado ou termina depois do fim.

Exemplo: pedido **2,04–3,96 s**, que corresponde a 48 quadros a 25 fps, saiu
com 50 quadros, começando no quadro 50 (2 s) e terminando no 99 (3,96 s).
Pedido **2,001–3,999 s**, sem B-frames, saiu começando em 2 s, fora do intervalo.
Essa margem não pode representar precisão: a tolerância de comparação deve
ser apenas numérica, e bordas com quadros necessários não podem desaparecer
por serem curtas.

### 4. HEVC pode retornar quadros fora de ordem mesmo com DTS válidos

No HEVC de origem sem B-frames, corte **0–6 s**, o arquivo manteve 150 quadros,
mas a cauda recodificada voltou para trás durante a reprodução. FFprobe
confirmou PTS decodificados decrescentes, por exemplo **4,261 → 4,181 → 4,101 s**.
O último grupo de quadros identificado foi **143, 145, 149, 148, 147**.

Não basta casar o nome do codec e verificar os DTS dos pacotes. É preciso
controlar reordenação, parâmetros dos segmentos e fronteiras de GOP aberto,
e verificar a decodificação nas emendas. As correções recentes do SmartJoin
já abordam problemas dessa família, mas ainda não estão aplicadas ao SmartCut.

### 5. Timestamps e atraso AAC ampliam a duração declarada

Os segmentos e o mux final usam `-avoid_negative_ts make_zero`. Isso desloca
a linha do tempo para acomodar o atraso de decodificação e o priming AAC.
Mesmo no caso sem B-frames, pedido 2–4 s, os 50 quadros corretos iniciaram
em **0,021 s**, e o container terminou em **2,021333 s**. Com B-frames, o
deslocamento e os quadros adicionais aumentaram o erro para 102–142 ms nos
exemplos acima. `-t` no mux final não garante a duração anunciada no comentário.

### 6. A opção Copiar áudio é ignorada no SmartCut

A interface habilita a escolha, `_cut_worker` passa `audio_precise=False`,
mas `_cut_video_smartcut` sempre chama `_precise_audio_args`, que recodifica
em AAC. O log avisa que a política não se aplica, mas a escolha já foi
oferecida ao usuário. No cenário `1.4_4.6_copyaudio`, o comando final contém
`-c:a:0 aac`, e o resultado tem os mesmos problemas da variante AAC.

Os caminhos de fallback também não repassam a política de cópia para
`_cut_video_precise`, cujo padrão é `copy_audio=False`.

### 7. VFR precisa de planejamento pelos timestamps reais

O miolo é copiado com os timestamps da fonte, mas as bordas recebem `-r`.
Na fonte VFR testada, pedido 1,4–4,6 s, foram decodificados 66 quadros contra
64 da referência, com repetição/salto nas emendas; o container indicou 3,322 s.
Um aviso de conversão para taxa fixa não torna essa montagem coerente.

## Pontos adicionais da leitura

- A saída final é escrita diretamente no nome definitivo, sem validação antes
  da publicação. Erros de duração, quadros e decodificação passam como sucesso.
- Sem keyframes úteis ou com codec não suportado, há fallback automático para
  reencode completo, com log. Em cortes inteiramente dentro de um GOP isso
  pode ser inevitável para precisão de vídeo; deve ser distinguido dos casos
  em que existe miolo copiável e o planejamento simplesmente o descarta.
- A descoberta de keyframes decodifica com `-skip_frame nokey`; o processo só
  verifica cancelamento ao terminar. A sonda de pacotes usada pelo SmartJoin
  oferece uma base mais apropriada para planejamento e cancelamento.

## Ordem recomendada para a próxima implementação

1. Definir o intervalo por timestamps/quadros reais e por amostras no áudio.
2. Corrigir o vídeo reutilizando os mecanismos já verificados no SmartJoin:
   contagem explícita de pacotes, limites seguros de GOP aberto, durações no
   manifesto e tratamento da reordenação sem deslocar o PTS.
3. Honrar a política de áudio e validar a mídia em arquivo temporário antes
   de publicar. Manter os corpos em cópia; não esconder erros com fallback.
4. Implementar SmartCut de áudio por codec, verificando priming, padding,
   compatibilidade do bitstream e precisão das amostras. Só depois compartilhar
   essa lógica com o Smart Insert.
5. Acrescentar regressões com FFmpeg real: os mocks atuais são úteis para
   roteamento e argumentos, mas não comprovam duração nem fidelidade da mídia.

Interface gráfica, GPU e player do aplicativo não foram testados nesta etapa.
O diagnóstico usa o código real da ferramenta com execução nativa por CPU.
