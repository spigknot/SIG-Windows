# SIG Windows 20260813_006

- Prompts externalizados em `prompts\` (um `.txt` por prompt), editáveis sem recompilar.
- Modelos Word editáveis em `modelos\` (`modelo_declaracoes.docx` e `modelo_depoimento.docx`).
- Geração de documentos de ocorrência a partir dos modelos, com números e datas por extenso.
- Cópia rica dos documentos: RTF (bytes direto) e HTML filtrado → CF_HTML UTF-8, com acentos e negrito preservados.
- Exportação do documento gerado para PDF pelo Word.
- Editor ao vivo de qualificação com campos personalizados e conversão para texto narrativo.
- Status honesto de conclusão do histórico e da extração de partes.
- Novos testes: assistente/status e modelos de documento.

Pacote full para instalação nova, incluindo runtime onedir, FFmpeg, VAD e SigUpdater.
