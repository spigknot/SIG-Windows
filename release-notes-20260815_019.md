# SIG Windows 20260815_019

## Diarização ampliada (Deepgram + AssemblyAI)

A checkbox **Diarização** agora funciona nos três modelos com suporte:

- **Grok STT** (já existia): `diarize=true` + rótulos "Interlocutor N" por
  palavras.
- **Deepgram Nova 3**: `diarize=true` no REST e WebSocket; as palavras
  vêm com speaker e o app formata "Interlocutor N: ..." por falante.
- **AssemblyAI Universal-3.5 Pro**: `speaker_labels=true` no WebSocket;
  cada turno recebe o rótulo do falante ("Interlocutor N: ...").

A checkbox só aparece para os modelos que suportam diarização.

## Correções de fluxo

- Gravação do microfone branco agora usa o uploader correto também para
  AssemblyAI e ElevenLabs (antes caía no ramo manual sem os headers).

## Novos modelos nesta série (018 → 019)

- **AssemblyAI Universal-3.5 Pro** (018): REST via Sync API + WebSocket
  streaming (Begin/Turn/Termination, Terminate).
- **ElevenLabs Scribe v2 Realtime**: REST pré-gravado + WebSocket com
  áudio em JSON base64 (VAD commit), timestamps e keyterms.
