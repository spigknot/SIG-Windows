# Handoff técnico - SIG Windows

Este arquivo serve para entregar o projeto a outro agente de IA, especialmente ao Hermes Agent.

## Primeira ação obrigatória

Antes de analisar, editar, compilar, testar ou publicar qualquer coisa:

1. Leia integralmente `AGENTS.md`, na raiz deste projeto.
2. Trate todas as regras desse arquivo como obrigatórias.
3. Leia `README.md` para uma visão geral da estrutura.
4. Execute `git status --short` antes de tocar nos arquivos.
5. O worktree possui alterações legítimas ainda não consolidadas. Não use `git reset`, `git checkout --`, limpeza ampla ou qualquer comando que descarte mudanças existentes.

O projeto Windows fica em:

`D:\Projetos\SIG Windows`

Repositório remoto:

`https://github.com/spigknot/SIG-Windows.git`

Branch observada durante este handoff:

`agent/blindar-updater`

## Estado atual

- Nome do aplicativo: `sig`.
- Versão atual: `20260814_001`.
- `APP_VERSION` fica em `src\sig_app.py`.
- O `dist\sig.exe` e o executável do build aprovado contêm a versão `20260814_001`.
- A incremental `20260814_001.zip` foi publicada no Google Drive.
- O manifesto local `release\latest.json` corresponde ao manifesto publicado.
- Último ZIP incremental aprovado:
  - arquivo: `20260814_001.zip`;
  - tamanho: `37048048` bytes;
  - SHA-256: `3a95c91cc43bb9a3a12b0dc4f6cfe014279cc7649a325aeb18b467d01cd6ec80`;
  - Drive file ID: `1-RZzcePeOGIL8Cnpsf06qyJayctRzMRg`.
- Manifesto permanente no Drive:
  - file ID: `1Gompo26SsyhSdliBGNaedLhEfidB244E`.
- Pasta oficial das incrementais no Drive:
  - folder ID: `1-yrsmFu_lAe0dMPo4sK70QRYGqMFcHJK`.
- Build aprovado preservado localmente em:
  - `release\generated\20260814_001_retry3\package`;
  - `release\generated\20260814_001_retry3\20260814_001.zip`;
  - `release\generated\20260814_001_retry3\20260814_001_full.zip`.

## Arquitetura principal

### Aplicativo

- `src\sig_app.py`: interface Tkinter e fluxos principais do aplicativo.
- `src\assistant_prompts.py`: carregamento dos prompts e substituição dos marcadores variáveis.
- `src\vad_worker.py`: processamento VAD em processo separado.
- `sig.spec`: configuração PyInstaller onedir.
- `assets\`: imagens, ícone e recursos estáticos.
- `requirements.txt`: dependências Python necessárias para desenvolvimento e build.

### Prompts editáveis

Os prompts de produção ficam em arquivos externos dentro de `prompts\`:

- `historico_system.txt`;
- `historico_user.txt`;
- `oitiva_system.txt`;
- `oitiva_user.txt`;
- `partes_system.txt`;
- `partes_user_botao_historico.txt`;
- `partes_user_botao_detectar.txt`;
- `qualificacao_system.txt`;
- `qualificacao_user.txt`.

Não volte a embutir esses textos completos em `src\assistant_prompts.py`. O módulo Python deve apenas carregar os arquivos, preencher marcadores e montar as mensagens.

### Modelos Word

Os modelos editáveis ficam em `modelos\`:

- `modelo_declaracoes.docx`;
- `modelo_depoimento.docx`.

O aplicativo substitui marcadores `{{{...}}}` preservando a formatação existente. A pasta externa ao lado de `sig.exe` tem prioridade sobre a cópia interna empacotada.

O fluxo de documento inclui:

- organização da qualificação por IA;
- preenchimento do DOCX correspondente;
- prévia embutida por PDF/PDFium;
- cópia rica para a área de transferência;
- salvamento em DOCX ou PDF.

Preserve negrito, justificação, tabulações, acentos e formatação dos modelos. A cópia rica usa RTF em bytes e HTML filtrado convertido uma única vez para CF_HTML UTF-8.

## Funcionalidades relevantes

As abas principais atuais incluem:

- `Ocorrência`;
- `Transcrição`;
- `Qualificação`;
- `IMEI`;
- `FFmpeg`.

### Ocorrência

Fluxo integrado para:

- captura de microfone;
- streaming STT do Grok por WebSocket;
- gravação tradicional e requisições REST;
- servidores Granite;
- timestamps quando a resposta do Grok os fornece;
- waveform em tempo real;
- histórico;
- extração de partes;
- oitiva;
- qualificação;
- geração de declaração ou depoimento com os modelos DOCX.

Existe suporte a multi model no Windows. Não transportar essa exigência automaticamente para o Android.

### Transcrição de arquivos

- Seleção de arquivos ou pasta.
- Áudio e vídeo.
- Conversão para WAV ou OGG/Opus, envio sem conversão e extração obrigatória de áudio de vídeos.
- Conversões e requisições paralelas.
- VAD opcional.
- Envio tradicional ou lote ZIP.
- Relatórios HTML, incluindo separação de falhas.
- Nomes originais devem permanecer no relatório, mesmo quando o arquivo enviado é temporário.
- Para Grok, arquivos grandes têm redução dinâmica do paralelismo.

### Qualificação

- Extrai dados cadastrais em JSON por IA.
- Formata a resposta para exibição usando rótulos amigáveis.
- Checkboxes controlam os IDs pedidos e a exibição dos campos.
- Campo `Outros dados` aceita atributos extras separados por vírgula.
- Não inventar dados ausentes e não exibir campos como `Não informado`.

### FFmpeg

Ferramentas atuais incluem corte, extração, giro, junção, inserção e limpeza de áudio, além dos fluxos de áudio/vídeo já implementados.

Preserve:

- detecção de encoder e aceleração de hardware;
- seletor de qualidade;
- players embutidos;
- progresso individual de processos paralelos;
- Smart Join/Smart Insert;
- preservação das características da mídia sempre que aplicável;
- logs de progresso no painel lateral.

## Configurações e modelos

As configurações guardam paralelismo, chaves de API, modelos de transcrição, modelos de texto, extração de partes e dados do policial.

Regras de segurança:

- chaves são fornecidas pelo usuário;
- nunca colocar chaves reais no código, testes, documentação, Git ou releases;
- modelos condicionados por chave só aparecem quando a chave correspondente é plausível/válida segundo a regra já implementada;
- IA-Proxy usa o backend principal e o fallback configurado no código;
- preservar os formatos de requisição já consolidados para xAI, DeepSeek e IA-Proxy.

## Comportamento recente do log

O painel de log usa etapas atualizáveis. Uma ação começa com uma única linha branca/cinza, por exemplo:

`23:53:35  Histórico requisitado`

Ao terminar com sucesso, a mesma linha deve ser modificada no lugar, receber a cor verde e apenas ganhar o tempo:

`23:53:35  Histórico requisitado (3.5s)`

Não adicionar `OK` e não criar uma segunda linha de conclusão.

Em caso de erro, a mesma linha deve ficar vermelha, manter o texto da ação e mostrar o erro. O mecanismo está em `src\sig_app.py`, nos métodos `_begin_activity_step`, `_finish_activity_step`, `_set_activity_status` e `_compact_activity_message`.

As atividades integradas incluem histórico, partes, oitiva, qualificação, documento, preview, cópia e salvamento. Evite reintroduzir mensagens duplicadas pelo `status_var`.

## Build obrigatório

O SIG é obrigatoriamente PyInstaller `onedir`:

- `sig.exe` deve ficar ao lado de `_internal\`;
- `_internal\python311.dll` deve existir;
- nunca compilar o SIG como one-file;
- `SigUpdater.exe` é a exceção e continua one-file/windowed.

### Ambiente reproduzível

O Hermes pode atualizar o próprio runtime. Durante a geração da versão `20260814_001`, o ambiente Hermes mudou de Python `3.11.0` para `3.11.15`, alterando o hash do updater e acionando corretamente o gate de segurança.

Ambiente compatível e aprovado nesta máquina:

`C:\Users\Gustavo\AppData\Local\Programs\Python\Python311\python.exe`

Versões aprovadas para o updater atual:

- Python `3.11.0`;
- PyInstaller `6.21.0`.

Antes de compilar, confirme:

```powershell
& 'C:\Users\Gustavo\AppData\Local\Programs\Python\Python311\python.exe' --version
& 'C:\Users\Gustavo\AppData\Local\Programs\Python\Python311\python.exe' -c "import PyInstaller, sounddevice, websocket, pypdfium2; print(PyInstaller.__version__)"
```

Não atualize `scripts\updater_artifact.json` apenas porque um novo runtime produziu outro hash. Uma migração de Python/PyInstaller deve ser uma tarefa separada, testada e deliberadamente aprovada.

## Testes e gates

Use o gate oficial `scripts\release.py`. Leia as regras completas em `AGENTS.md` antes de executar.

Comandos básicos:

```powershell
$sigPython = 'C:\Users\Gustavo\AppData\Local\Programs\Python\Python311\python.exe'
& $sigPython -m py_compile src\sig_app.py
& $sigPython scripts\release.py tests
& $sigPython scripts\release.py validate
& $sigPython scripts\release.py updater-test
```

Para gerar a próxima incremental, atualize primeiro `APP_VERSION` e use o padrão `YYYYMMDD_NNN`:

```powershell
& $sigPython scripts\release.py release --version <VERSAO> --incremental
```

O comando gera um clean build, recompila o updater, valida o onedir e cria:

- `<VERSAO>.zip`, incremental para o Drive;
- `<VERSAO>_full.zip`, pacote completo local para release do GitHub.

Na versão `20260814_001`, passaram:

- compilação do código;
- 51 testes automatizados;
- validação de versão e layout;
- dependências congeladas `sounddevice`, `websocket` e PortAudio;
- validação do `SigUpdater.exe` conhecido;
- harness do updater com instalação onedir e rollback.

## Publicação

### Incremental

- Enviar exclusivamente pela API do Google Drive.
- Não usar a unidade montada `X:` para publicar.
- Fazer um único upload do ZIP.
- Atualizar o arquivo `latest.json` existente pelo ID; não criar outro manifesto.
- Conferir via API o ID, nome e tamanho após o upload.
- Assinar o manifesto com a chave privada local.
- Nunca publicar `release\update_private_key.pem`.

### Full

- O pacote full é destinado a instalações novas e reparos extremos.
- Publicar como asset de release no GitHub quando solicitado.
- Não enviar o full para a pasta de incrementais do Drive.
- Não versionar no Git os binários grandes do runtime.

## Updater

O código-fonte fica em `updater_v2\updater.py`.

Características que devem ser preservadas:

- interface independente quando aberto sem argumentos;
- modo silencioso chamado pelo SIG;
- cópia própria para `%LOCALAPPDATA%\sig\updater` antes de alterar a instalação;
- validação de assinatura, tamanho e SHA-256;
- transação com lock e diário;
- rollback quando o SIG atualizado não inicia;
- rejeição de path traversal, links, `_MEI`, estruturas `g` e pacotes incompletos;
- incremental pelo Drive e full pelo GitHub;
- não oferecer novamente uma versão igual ou anterior à instalada.

O hash aprovado do updater fica em:

- `scripts\updater_artifact.json`;
- `updater_v2\artifact.json`.

## Worktree existente

No momento deste handoff, há arquivos modificados, removidos e novos ainda não consolidados. Eles representam trabalho real do usuário e de sessões anteriores.

Entre eles estão:

- alterações em `src\sig_app.py` e `src\assistant_prompts.py`;
- reorganização dos prompts;
- alterações no updater e nos gates de release;
- alterações em testes;
- alterações em `AGENTS.md`, `README.md`, `requirements.txt` e `sig.spec`.

Não conclua que arquivos novos são descartáveis apenas por estarem sem rastreamento. Em especial, os novos prompts e `tests\test_assistant_prompts.py` são necessários.

Antes de editar um arquivo já modificado, leia o diff e trabalhe em cima dele. Não reverta mudanças que não sejam claramente suas.

## Próximo agente

Ao assumir uma nova tarefa:

1. Leia `AGENTS.md` inteiro.
2. Leia este `HANDOFF.md` inteiro.
3. Execute `git status --short` e inspecione os diffs relacionados à tarefa.
4. Confirme `APP_VERSION` e `release\latest.json`.
5. Faça alterações localizadas.
6. Rode os testes proporcionais ao risco.
7. Só gere/publice uma versão quando o usuário pedir explicitamente.
8. Nunca considere uma release concluída sem validar o pacote e conferir o Drive.

