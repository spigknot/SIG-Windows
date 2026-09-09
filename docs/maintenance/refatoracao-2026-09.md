# Refatoracao 2026-09 — modularizacao conservadora do `sig_app.py`

> Relatorio em linguagem simples, para pessoas e para agentes de IA que forem
> mexer no projeto depois. Escrito em 08/09/2026.
>
> Branch: `refactor/modularizacao-conservadora` (8 commits, ainda **nao** mesclada
> em `main`). Rollback = `git checkout main`.

## Em uma frase

O programa fazia tudo dentro de um unico arquivo gigante; agora esta dividido em
18 "gavetas" etiquetadas, cada uma cuidando de um assunto — e nada mudou para
quem usa o programa.

## Como era antes

`src/sig_app.py` tinha **21.838 linhas** misturando:

- desenho das telas (janelas, botoes, abas);
- regras de negocio (o que fazer com cada arquivo/transcricao);
- chamadas externas (Grok, Deepgram, Alibaba, MetaMuse, IMEI);
- como salvar e carregar configuracoes;
- geracao de Word/PDF, relatorios, logs, nomes e qualificacao.

Para achar qualquer coisa era preciso varrer milhares de linhas — e qualquer
alteracao podia atingir areas sem relacao com ela.

## Como ficou agora (numeros reais)

| | Antes | Depois |
| --- | --- | --- |
| Arquivo principal | `sig_app.py` com **21.838 linhas** | `sig_app.py` com **13.380 linhas** (−38%) |
| Arquivos de apoio | poucos | **18 modulos novos** (9.505 linhas) |
| Etiqueta por modulo | nao existia | docstring de responsabilidade em todos |
| Mapa de navegacao | nao existia | `docs/agents/module-map.md` |
| Trava contra a bagunca voltar | nao existia | **6 testes** em `tests/test_modularizacao_contrato.py` |
| Testes | 479 passando | **485 passando**, 0 falhas |
| Re-export da API historica | — | 18 blocos, **209 nomes** |

## As gavetas criadas

**Ambiente**

| Modulo | O que guarda |
| --- | --- |
| `app_env.py` | Nome do app, caminhos das configuracoes, host da maquina, opcoes de paralelismo por CPU |

**Dominio**

| Modulo | O que guarda |
| --- | --- |
| `domain_models.py` | O que e uma tarefa de audio (`AudioJob`), `Cancelled` e acessores |

**Configuracao**

| Modulo | O que guarda |
| --- | --- |
| `providers.py` | Catalogo de provedores STT/texto e valores padrao (`DEFAULT_SETTINGS`) |
| `settings_store.py` | Ler, normalizar e salvar `settings.json` |

**Integracoes (chamadas externas)**

| Modulo | O que guarda |
| --- | --- |
| `stt_clients.py` | Como falar com cada servico de transcricao (URLs, campos, WebSocket) |
| `http_clients.py` | Upload de arquivos e chamadas aos modelos de texto |
| `text_models.py` | Escolha do modelo de IA e leitura da resposta |
| `imei_lookup.py` | Consulta de IMEI e historico local |

**Processamento (sem rede)**

| Modulo | O que faz |
| --- | --- |
| `transcription_parsing.py` | Converte a resposta dos servicos em texto com tempos |
| `log_formatting.py` | Monta linhas de log e comandos do FFmpeg |
| `documents.py` | Gera DOCX a partir dos modelos Word, PDF e previa |
| `reporting.py` | Relatorios HTML (arquivo final e janela ao vivo) |
| `qualification.py` | Le e formata a qualificacao da ocorrencia |
| `name_database.py` | Extrai nomes proprios e compara por som |
| `media_files.py` | Extensoes e tipos de arquivo aceitos |
| `audio_io.py` | Captura ao vivo: PCM e gravacao de WAV |

**Interface (somente tela)**

| Modulo | O que faz |
| --- | --- |
| `ui_widgets.py` | Widgets reutilizaveis (tooltip, botao com icone) |
| `ffmpeg_tools_panel.py` | Aba FFmpeg: converter, cortar, juntar, player |

**Regra de dependencia:** a dependencia so aponta para baixo
(UI -> integracao -> processamento -> config -> dominio -> ambiente). Modulos de
dominio **nao podem** importar `tkinter` nem `sig_app` — verificado por teste.

## As vantagens

1. **Localizacao rapida.** "Relatorio" -> `reporting.py`; "log" ->
   `log_formatting.py`; "Word/PDF" -> `documents.py`; "provedor de STT" ->
   `stt_clients.py` + `providers.py`.
2. **Mudanca isolada.** Alterar o Word nao tem como atingir, por acidente, a
   transcricao ou o IMEI. Menos regressao.
3. **Arquivos menores.** Um modulo de ~500 linhas e lido inteiro; um de 21 mil e
   lido por amostragem — e ali nascem os bugs.
4. **Vacina permanente.** Os 6 testes falham se alguem duplicar codigo no
   monolito, fizer negocio depender de tela, apagar docstring de modulo ou
   quebrar o carregamento de configuracoes antigas.
5. **Navegacao para agentes.** `AGENTS.md` -> `docs/agents/module-map.md`
   (tabela modulo -> responsabilidade -> "nao colocar aqui" + receitas) e a
   docstring-guia no topo de `sig_app.py`.
6. **Zero impacto para o usuario final.** Nenhuma tela, botao, fluxo ou
   configuracao mudou.
7. **Sem magica.** Nenhuma abstracao nova, nenhuma camada indireta, nenhum
   framework: apenas arquivos com nomes claros, no estilo do projeto.

## O que NAO foi modificado (de proposito, por risco)

- Classe `SigApp` (UI principal, ~12,5 mil linhas);
- threads e filas de conversao/transcricao (concorrencia);
- ciclo de vida da janela e captura de audio ao vivo.

Essas partes tem comportamento sensivel a tempo; so devem ser movidas com
mapeamento e testes que provem equivalencia.

## Como foi provado que nada quebrou

1. **Codigo movido verbatim** — recortado e colado, nao reescrito.
2. **Verificacao de identidade contra o Git** — comparacao AST entre cada bloco
   movido e o original em `HEAD`: identico.
3. **485 testes passando** (479 do baseline + 6 novas vacinas), 0 falhas.
4. **Executavel recompilado e aberto** — `dist/sig.exe` gerado por
   `scripts/build_dev.py` e iniciado de verdade (processo vivo, ~70 MB), sem
   crash; encerrado em seguida.

## Pendencias

- [ ] Validacao manual do usuario: aba FFmpeg (converter/cortar/juntar/player),
      geracao de documento e uma transcricao curta. Os testes nao clicam na tela.
- [ ] Mesclar (ou nao) `refactor/modularizacao-conservadora` em `main`.
- [ ] Ferramenta AST de extracao esta em `%TEMP%\refactor_tool` (volatil); copiar
      para `scripts/` se novas extracoes forem feitas.
- [ ] Gate `ui-smoke` ainda nao executado.

## Anexo — contagem de linhas por modulo (08/09/2026)

```
13380  src/sig_app.py
 5355  src/ffmpeg_tools_panel.py
  630  src/documents.py
  554  src/stt_clients.py
  464  src/providers.py
  366  src/http_clients.py
  257  src/settings_store.py
  254  src/log_formatting.py
  246  src/transcription_parsing.py
  236  src/qualification.py
  220  src/reporting.py
  189  src/text_models.py
  176  src/name_database.py
  128  src/ui_widgets.py
  120  src/domain_models.py
  119  src/imei_lookup.py
   84  src/app_env.py
   67  src/media_files.py
   40  src/audio_io.py
```

Procedimento reutilizavel para novas extracoes: skill
`python-verbatim-module-extraction`.
