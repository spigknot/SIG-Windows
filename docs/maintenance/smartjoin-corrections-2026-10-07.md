# Correções e validação do SmartJoin — 07/10/2026

Foram corrigidos os defeitos de duração, quadros ausentes, áudio truncado, perfil ignorado, encoder de família incorreta, progresso e saída parcial descritos na [auditoria inicial](smartjoin-audit-2026-10-07.md). A intervenção está no código-fonte; não houve build, atualização ou publicação do executável.

## Comportamento entregue

Para três clipes de 6 segundos a 25 fps:

| Escolha | Resultado medido |
| --- | --- |
| Sem transição, arquivos compatíveis | Concatenação por cópia; 450 quadros, aproximadamente 18 s, com o arredondamento original do áudio/container |
| Fade in/out, 0,5 s | 18 s, 450 quadros; vídeo e áudio completos, sem sobreposição das durações |
| Fundir e outros nove efeitos sobrepostos, 0,5 s | 17 s, 425 quadros; vídeo e áudio completos |
| Preencher silêncio no clipe intermediário, sem efeito | 18 s, 450 quadros; todos os corpos de vídeo copiados, somente áudio processado |
| Gerar saída sem áudio, Fade in/out | 18 s, 450 quadros; nenhuma faixa de áudio |

Primeiro clipe, Maior resolução e Menor resolução participam do planejamento. Na reprodução com 320×180 seguido por dois clipes de 640×360, Primeiro/Menor agora entregam 320×180, e Maior entrega 640×360. Somente os clipes incompatíveis com o perfil selecionado são recodificados. Qualidade e velocidade escolhidas se aplicam às partes codificadas; partes copiadas preservam o vídeo original.

O resolvedor conserva a família H.264/HEVC e respeita a preferência CPU/GPU pelo catálogo sondado. Não usa MPEG-4 como encoder de uma emenda H.264, nem troca por CPU apenas porque a emenda é curta. As variantes GPU foram cobertas por testes do resolvedor, sem execução real de NVENC/QSV/AMF.

Todas as faixas (MKV) permanece disponível para cópia sem transição, com topologia compatível. Combinar essa opção com áudio ausente e preenchimento de silêncio é recusado com explicação: a pipeline de silêncio trabalha com uma faixa, e não pode descartar as demais ou entregar MP4 com extensão MKV silenciosamente.

## Como a velocidade foi preservada

- Seek antes da entrada e contagem exata dos quadros mantêm os keyframes necessários, sem incluir o GOP seguinte por um limite temporal aproximado.
- GOPs abertos HEVC têm seus quadros anteriores ao CRA tratados nas emendas. A reordenação dos quadros e o atraso de decodificação são ajustados às partes copiadas, com PTS preservados.
- As peças MPEG-TS têm duração explícita no manifesto. Peças muito pequenas recebem apenas pacotes nulos do container para serem reconhecidas corretamente; isso não acrescenta tempo ou conteúdo.
- O áudio da pipeline híbrida é montado a partir dos clipes originais e codificado uma única vez, incluindo fades, sobreposição e silêncio. Não há acumulação de atrasos AAC por peça.
- A análise lê pacotes de vídeo sem decodificar os corpos. Fontes repetidas reutilizam a análise. A validação decodifica somente as emendas e alguns quadros seguintes, além de verificar a contagem e continuidade dos pacotes finais e a duração do áudio.
- Não há fallback silencioso para recodificação completa. Um plano sem nenhum corpo copiável é recusado com motivo e indicação das opções disponíveis. GOP esparso recodifica apenas o clipe afetado quando o restante pode ser copiado.

As decisões de seek, concat e timestamps seguem a [documentação do FFmpeg](https://ffmpeg.org/ffmpeg-all.html). A saída híbrida usa um arquivo temporário e só aparece com o nome final depois da validação. Falha ou cancelamento limpa os temporários e preserva um arquivo anterior.

Uma comparação local, com a mesma máquina, CPU libx264, qualidade Alta, velocidade Equilibrada e Fade in/out de 0,5 s, mediu:

| Entrada sintética em movimento, 1280×720/25 fps | Reencode Completo | SmartJoin, incluindo análise/validação | Vídeo copiado |
| --- | --- | --- | --- |
| Três clipes de 20 s, total 60 s | 5,36 s | 6,77 s | 52 s |
| Três clipes de 120 s, total 360 s | 28,34 s | 15,11 s | 352 s |

No exemplo de seis minutos, o híbrido levou aproximadamente 53% do tempo da recodificação completa (1,88×). No exemplo curto, iniciar processos e validar as emendas custou mais que o ganho de cópia. São medições únicas com mídia sintética, não promessa de ganho universal. Não foi introduzida troca automática de estratégia para esconder essa diferença. Os dois resultados híbridos decodificaram sem avisos e mantiveram exatamente 60/360 s.

## Validação real

A matriz original de **39 cenários** foi repetida: **35 saídas válidas e quatro rejeições esperadas**, sem falhas inesperadas. As quatro rejeições são tempo negativo, texto inválido, NaN e perfil HEVC 10-bit não suportado nas emendas. Todas as 35 saídas decodificaram integralmente sem avisos. Os testes usam FFmpeg 8.0.1/FFprobe locais, em CPU, com execução das funções de produção e um executor headless no lugar da interface Tk.

Além da matriz, testes de integração verificam as 11 transições, duração/contagem de quadros, áudio até o fim, silêncio, ausência de áudio, três perfis de saída, GOP esparso, HEVC em movimento com igualdade dos quadros copiados, taxa racional 30000/1001 e pixels não quadrados. Os testes de unidade cobrem comandos, perfil, validações, resolvedor de encoder e limpeza da saída em falhas.

Resultado conclusivo: **317 testes de unidade e sete testes de integração passaram**, totalizando 324 testes pertinentes. O log combinado de 323 testes passou antes da última proteção de Todas as faixas; depois dessa proteção, a suíte de unidade foi repetida com o novo teste, passando os 317. Sintaxe dos arquivos envolvidos e `git diff --check` também passaram.

Os experimentos adicionais com taxa racional produziram 360 quadros em 12,012 s, mantendo 30000/1001; SAR 4:3 produziu 300 quadros em 12 s, mantendo a proporção de pixel. O teste HEVC em movimento produziu 300 quadros em 12 s, preservando exatamente os quadros amostrados dos corpos copiados e a ordem de decodificação.

Evidências locais, fora do Git:

- `build/smartjoin_audit/fixed_matrix/results.json`: opções, comandos, logs e inspeção das 39 execuções após a correção.
- `build/smartjoin_audit/fixed-matrix-complete.log`: matriz completa; `FAILURES []`.
- `build/smartjoin_audit/relevant-tests-final.log`: suíte pertinente ao FFmpeg, SmartJoin, encoders e rotação.
- `build/smartjoin_audit/unit-tests-final.log`: 317 testes de unidade após a última proteção de faixas.
- `build/smartjoin_audit/precision-probe.log` e `precision/results.json`: experimentos adicionais de FPS racional/SAR.
- `build/smartjoin_audit/benchmark/timing.json` e `benchmark_long/timing.json`: comparação local de tempo com recodificação completa.
- `tests/test_smart_join_pipeline.py` e `tests/test_smart_join_ffmpeg_integration.py`: reproduções automatizadas mantidas no projeto.

Não foi validada a interação manual da janela nem o executável empacotado. GPU real, HDR/10-bit, VFR complexo e topologias com legendas/anexos não foram certificados. Durações que não caibam em quadros inteiros são arredondadas na timeline com tolerância de aproximadamente um quadro; transições menores que meio quadro são tratadas como ausência de efeito, com mensagem no log. Transições excessivas continuam limitadas ao intervalo seguro, também com mensagem.

Uma tentativa adicional de descobrir todos os testes do projeto foi interrompida sem concluir; não é apresentada como aprovação da suíte completa. A validação conclusiva usa a suíte pertinente ao escopo e os experimentos de mídia acima. Alterações preexistentes em outros módulos foram preservadas.
