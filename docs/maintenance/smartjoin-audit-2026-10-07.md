# Auditoria do SmartJoin — 07/10/2026

Este relatório registra o comportamento **antes das correções**. Os resultados após a intervenção estão em [Correções e validação do SmartJoin](smartjoin-corrections-2026-10-07.md).

O SmartJoin com transição não está entregando uma saída confiável. Há perda de vídeo, corte de áudio e casos em que o aplicativo informa sucesso apesar de faltar conteúdo. A concatenação por cópia com tempo zero funcionou nos arquivos compatíveis testados.

Esta tarefa foi uma investigação: nenhum código de produção foi alterado. As alterações preexistentes do usuário foram preservadas.

## Como foi testado

- Execução direta de `FfmpegToolsPanel._join_worker`, do planejador e dos geradores de comandos do código atual, com subprocessos FFmpeg reais. Apenas a interface Tk, o registro visual de progresso e o invólucro `_execute` foram substituídos por um executor que preserva comandos/logs e verifica o código de saída. Não foi um teste manual de clicar na janela nem do executável compilado.
- FFmpeg 8.0.1 e FFprobe locais. O FFmpeg usado no PATH tem exatamente o mesmo SHA-256 do `dist/ffmpeg.exe`: `74DB6C184A03DBA2BDFE23E1A1F41CF5A8385BC1DE6A7A1B26DB1DC541ABEF93`. `dist/` foi apenas consultado; não houve build ou publicação.
- 39 cenários de junção, 11 emendas executadas isoladamente e 6 recortes de corpos executados isoladamente. Arquivos sintéticos de 6 segundos, 25 fps, cores vermelho/verde/azul e tons 440/880/1320 Hz permitem identificar a ordem e o áudio de cada clipe. Foram incluídos resolução diferente, H.264/HEVC, B-frames, GOP esparso, áudio ausente, duas faixas, qualidade/velocidade e entradas inválidas.
- Verificação com FFprobe, decodificação completa, amostragem das cores, análise de áudio e timestamps dos quadros. Os testes existentes relacionados ao FFmpeg, SmartJoin, rotação e encoders também foram executados: **299 passaram**. Eles não detectam os defeitos de mídia reproduzidos aqui.
- Não foram exercitados NVENC/QSV/AMF, HDR real, VFR, legendas/anexos nem a interação manual da janela. Cor sólida comprova ordem, fades e lacunas temporais; não avalia qualidade perceptual em imagens complexas.

Os 39 cenários tiveram 14 retornos de sucesso e 25 erros. Isso não equivale a 14 resultados corretos: sete dos sucessos tinham vídeo/áudio faltando. Três erros eram rejeições esperadas (tempo negativo, tempo inválido e pixel format não suportado).

## O que o tempo de transição significa

Para três clipes de 6 s:

- Tempo zero: 18 s, concatenando sem efeito. O app já usa `-c copy` quando os arquivos são compatíveis.
- `Fade in/out` com 0,5 s: 18 s. Escurece os últimos 0,5 s de um clipe e clareia os primeiros 0,5 s do seguinte, sem sobrepor suas durações.
- `Fundir` e demais efeitos sobrepostos com 0,5 s: 17 s. Cada uma das duas emendas sobrepõe 0,5 s.

Esse contrato é explícito em `Plan.expected_duration_seconds` e na implementação dos filtros. Para áudio misto com tempo zero, preencher silêncio exige recodificação; o aplicativo faz isso e registra o motivo.

## Defeitos reproduzidos

### 1. Corte do corpo em stream copy perde quadros e pode gerar uma peça inválida — alta prioridade

Local: `src/ffmpeg_tools_panel.py`, `_smart_join_body_arguments`, linhas 6816–6821; integração em `_smart_join_execute`.

A função coloca `-ss` depois do input. Nos arquivos H.264 com B-frames testados, um corpo solicitado de 2 a 4 s não conserva o keyframe necessário e produz um TS que nem o FFprobe reconhece como stream utilizável. O corpo de 2 a 6 s conserva apenas 2 s de vídeo. O corpo sem seek, de 0 a 4 s, produz aproximadamente 4,16 s.

Isso foi confirmado separadamente, tanto com áudio quanto sem áudio. Não é causado apenas pela transição visual. Na junção de três clipes, o concat para ao encontrar a peça inválida; seu processo ainda retorna zero. O log contém `Impossible to open .../body_001.ts`.

- `Fade in/out`: **8,213333 s**, quando deveriam ser 18 s; o terceiro clipe azul não aparece.
- Todas as outras dez transições de 0,5 s: **7,724 s**, quando deveriam ser 17 s.
- Gerar saída sem áudio: **8,16 s**, quando deveriam ser 18 s.

O app detecta a duração incorreta nesses casos, mas deixa o MP4 parcial na pasta de saída.

### 2. Áudio é aparado antes do seek de saída e perde o trecho final — alta prioridade

Local: `_smart_join_audio_window_filter`, linhas 6720–6739, usado por `_smart_join_body_arguments` antes do `-ss` de saída.

O filtro faz `atrim=duration=<duração do corpo>` desde o começo da fonte e zera seus timestamps. Em seguida, o `-ss` de saída ainda descarta os primeiros `<início do corpo>` segundos. Portanto o áudio perde tempo adicional; se início e duração forem iguais, nenhum áudio chega ao encoder.

- No clipe intermediário recodificado de um vídeo de 3 s com GOP esparso, o plano pede início 1 s e duração 1 s. O filtro reduz o áudio a 1 s e o seek descarta esse 1 s. FFmpeg falha com `Could not open encoder before EOF` / `Nothing was written into output file`.
- Mesmo sem B-frames, três clipes geram **450 quadros**, mas a trilha de áudio tem apenas **16,122667 s**, enquanto o vídeo tem **18,096 s**. O app informa sucesso.

O tratamento de seek, trim e timestamps precisa definir uma única janela da fonte para vídeo e áudio, incluindo o silêncio sintetizado quando uma fonte não possui áudio. Alterar apenas a concatenação não corrige esse defeito.

### 3. A validação de duração aprova saídas com congelamento e áudio curto — alta prioridade

Local: `_smart_join_execute`, linhas 7278–7286, e `_get_duration_only`.

A checagem atual compara apenas a duração do container com o total esperado, tolerando 0,35 s. Uma lacuna nos timestamps pode manter essa duração mesmo depois de perder quadros.

Reprodução com dois clipes distintos de 6 s, H.264, 25 fps e `Fade in/out` 0,5 s:

- Retorno: **sucesso** e mensagem `SmartJoin concluído: 12.00s`.
- Container: **12,235333 s**.
- Vídeo: **252 quadros**, contra 300 esperados; duração de stream **12,213333 s**.
- Salto de timestamp de **8,222 s para 10,293333 s**, uma lacuna de **2,071333 s**; a reprodução precisa manter o último quadro durante esse intervalo.
- Áudio: **10,24 s**, terminando aproximadamente 2 s antes do vídeo.

O mesmo defeito passou na qualidade Econômica/Rápida, Máxima/Máxima qualidade e com HEVC. Misturar codecs também retornou sucesso: 402 quadros em vez de 450, uma lacuna de 2,098 s e áudio aproximadamente 2 s menor.

É necessário validar peças e continuidade temporal, além de comparar as durações de vídeo e áudio. Um retorno zero do concat e uma duração total próxima não comprovam integridade. Uma falha deve impedir que o arquivo parcial seja apresentado como uma saída válida.

### 4. O perfil escolhido pelo usuário é ignorado — alta prioridade

Locais: `_update_join_controls`, linha 3113; `_join_worker`, linhas 6500–6541; `smart_join_planner.choose_target_index`; `_smart_join_execute`, linhas 7136 e 7165.

A interface permite escolher o perfil no SmartJoin com transição. O worker calcula e registra o perfil solicitado, mas não o passa ao planejador. O planejador escolhe o grupo compatível de maior duração.

Reprodução: primeiro clipe 320×180; segundo e terceiro 640×360, todos com 6 s:

| Escolha | Esperado | Perfil efetivamente usado |
| --- | --- | --- |
| Primeiro clipe | 320×180 | 640×360 |
| Maior resolução | 640×360 | 640×360 |
| Menor resolução (sem upscale) | 320×180 | 640×360 |

Os três casos usam o segundo clipe como target. No primeiro caso o log promete 320×180, mas o MP4 parcial e as emendas são 640×360. A escolha `Menor resolução (sem upscale)` também amplia o primeiro clipe. Isso é uma divergência independente da falha de duração.

O perfil selecionado precisa participar do planejamento. Caso preservar esse perfil impeça qualquer ganho de stream copy, o aplicativo deve explicar essa limitação ao usuário em vez de trocar o perfil silenciosamente.

### 5. O fallback MPEG-4 é considerado compatível com H.264 — prioridade média

Local: `_smart_join_acceleration_for_codec`, linha 6775.

A condição aceita um encoder cujo nome começa com `mpeg4` para o target H.264. Ao forçar o fallback MPEG-4 existente no código, a emenda é MPEG-4, mas `_smart_join_ts_arguments` tenta aplicar `h264_mp4toannexb`. A preparação da emenda falha.

Esse teste exercita um caminho de fallback por código; não comprova que esse encoder estava disponível no combo da máquina. O resolvedor precisa conservar a família do codec e recorrer a `libx264` quando necessário.

### Observações menores

- A entrada `nan` é aceita pelo parsing de `float` e chega ao filtro FFmpeg, gerando erro técnico em vez de `Tempo de transição inválido`. Faltam validações de finitude.
- Os limiares de ausência de transição divergem: o worker usa 0,001 s e o planejador 0,002 s. Com 0,0015 s o worker entra no SmartJoin híbrido, mas o planner não cria emendas. É uma inconsistência marginal, sem relevância perceptual no teste.
- O total de etapas conta uma etapa por corpo, embora corpos incompatíveis usem duas (encode + remux). Pode subestimar o total do progresso; não foi validado visualmente na janela.

## Resultados por opção

| Opção/cenário | Resultado observado |
| --- | --- |
| 11 transições, três clipes, 0,5 s | Todas falham no pipeline integrado por perda de conteúdo; Fade in/out 8,21 s, demais 7,72 s |
| As mesmas 11 emendas isoladas | Todas executam e decodificam sem avisos; 4,022 s para fade sequencial, 3,542 s para sobreposição. O problema principal está nos corpos/montagem |
| Tempo zero, vídeo compatível, MP4 | Correto: 18,021333 s, 450 quadros, ordem vermelho → verde → azul |
| Tempo zero, dois clipes distintos | Correto: 12,021333 s |
| Todas as faixas, MKV, tempo zero | Preservou duas faixas de áudio: 12,021 s. Legendas/anexos não foram incluídos nos fixtures |
| Primeira faixa, MP4, com transição | Seleciona uma faixa, mas aprova vídeo incompleto e áudio curto |
| Preencher silêncio, com transição | Pipeline falha, inclusive quando o primeiro clipe é silencioso |
| Preencher silêncio, tempo zero | Correto: recodificação anunciada, 18,032 s e 450 quadros; o intervalo do clipe verde fica silencioso |
| Gerar saída sem áudio | Áudio realmente ausente, mas vídeo incompleto: 8,16 s com três clipes; 10,16 s com dois |
| Três políticas de perfil | Primeiro/Menor ignorados; Maior coincide com o target automático |
| Transição excessiva (10 s) | Tempo reduzido para 2,94 s com aviso; ainda falha no pipeline de corpos |
| GOP esparso intermediário | Plano recodifica apenas o corpo necessário, mas o áudio vazio provoca falha do encoder |
| Econômica/Rápida e Máxima/Máxima qualidade | Comandos respeitam CRF/preset escolhidos; saídas aprovadas têm perda de quadros/áudio |
| HEVC | Codec HEVC/hvc1 preservado, mas sucesso com vídeo/áudio faltando |
| Misturar H.264 e HEVC | Usa H.264 dominante e recodifica o incompatível, mas aprova saída com lacuna e áudio curto |
| Vídeo sem B-frames | Preserva os 450 quadros; áudio continua curto e o app aprova |
| Somente áudio, Fade in/out | Correto quanto à duração: 12,032 s; sem sobreposição |
| Somente áudio, tempo zero | Concatenação por cópia: 12,021333 s |
| Tempo negativo / texto inválido / HEVC 10-bit | Rejeições esperadas, sem converter silenciosamente |

As durações com pequenas diferenças de centésimos incluem timestamps e arredondamento dos encoders/containers. Esses desvios não justificam os segundos de conteúdo perdido.

## Evidências e reprodução local

Pasta: `build/smartjoin_audit/`. Os scripts não são testes unitários nem gates de release; são experimentos locais, fora do runtime do produto.

- `audit.py`, `extra.py`: fixtures e os 39 cenários; executam as funções de produção.
- `results.json`, `extra/results.json`: opções, comandos, logs, streams e análise da mídia.
- `diagnose.py`, `isolated_results.json`: seis cortes isolados que reproduzem a perda dos corpos.
- `bridges.py`, `bridges_results.json`, `isolated_bridges/`: reprodução das 11 transições isoladamente.
- `frame_gaps.json`: lacunas medidas nos timestamps dos quadros.
- `audio_only_results.json`: inspeção específica das saídas que só contêm áudio.
- `unit-tests.log`: resultado integral dos 299 testes existentes.
- `transition_00/videos_juntos.mp4`: exemplo de saída parcial (18 s esperados, 8,21 s reais).
- `extra/two_distinct/videos_juntos.mp4`: exemplo que o app aprova apesar de perder conteúdo.
- `zero_mp4/videos_juntos.mp4`: referência correta de concatenação com cópia.

Os experimentos usam CPU e geram arquivos sintéticos na própria pasta. Para repetir: `python build/smartjoin_audit/audit.py`, depois `python build/smartjoin_audit/extra.py`, `python build/smartjoin_audit/diagnose.py` e `python build/smartjoin_audit/bridges.py`. Não executam release, build, updater nem acessam mídias do usuário.

Prioridade de correção: alinhar a janela de vídeo/áudio nos corpos; validar peças, timestamps e streams; respeitar o perfil selecionado; impedir sobra de saída parcial em falhas; ajustar o resolvedor de codec. Em seguida, repetir os experimentos e transformar as reproduções relevantes em testes de integração com FFmpeg real.
