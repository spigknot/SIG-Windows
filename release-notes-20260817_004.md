# SIG Windows 20260817_004

## Novidades

- **Novo servidor de texto "servidor (gemma-4-26B-A4B-abliterated)"**: conversa
  com o llama.cpp local (http://servidor:8400, fallback http://avare:8400) usando
  o modelo `gemma4` com `enable_thinking=false`, temperature 0, seed 1, top_k 1,
  top_p 1. O `max_tokens` é calculado pelo próprio app: pergunta ao endpoint
  `/tokenize` do servidor (campo `content`) e aplica a margem 1.5 do template do
  chat — com fallback local (4 caracteres por token) quando o servidor não
  responde.

## Correções

- **NVENC não aparecia na aba FFmpeg**: o teste de detecção usava vídeo de 64×64,
  rejeitado pelas GPUs novas/drivers recentes ("frame dimension below minimum") —
  a 3060 Ti só listava CPU. O teste agora usa 256×256 e o NVENC (NVIDIA) aparece
  na lista de encoders.

## Ajustes

- Log do download da atualização: uma linha fixa por arquivo, atualizada no
  lugar até o verde (estilo FFmpeg), com a hora no início da linha.
