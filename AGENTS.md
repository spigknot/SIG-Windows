# Instrucoes permanentes do SIG Windows

Estas regras sao o contexto universal do projeto. Detalhes de uma tarefa devem
ser carregados somente pelo roteamento em `docs/agents/README.md`.

## Ownership e fontes canonicas

- Prompts editaveis pertencem a `prompts/`; `src/assistant_prompts.py` apenas os
  carrega e monta as partes variaveis. Nao duplicar o texto dos prompts em
  codigo-fonte.
- Modelos Word editaveis pertencem a `modelos/`; nao sao empacotados no
  executavel — instalacao e updates (full/diff) entregam a pasta `modelos/`
  ao lado do aplicativo.
- O codigo-fonte e o contrato de comportamento sao a fonte de verdade. Nao
  editar `dist/`, artefatos gerados ou pacotes publicados como se fossem fonte.

## Invariantes de build e distribuicao

- O SIG deve continuar em modo `onedir`; o updater independente e o unico
  componente que pode usar `onefile`.
- Uma instalacao completa precisa manter o executavel, o runtime interno, o
  updater, os binarios FFmpeg, as dependencias VAD, os prompts e os modelos.
- Atualizacoes e releases so podem seguir o runbook canonico `UPDATE.md`. Nao
  improvisar canais, pacotes, manifests, versoes ou comandos de publicacao.
- Nao publicar executaveis avulsos quando o runbook exigir um pacote ou um
  manifesto; nao apagar a compatibilidade de instalacoes antigas sem instrução
  explicita.

## Seguranca e escopo

- Nunca gravar chaves de API, chaves privadas, configuracoes locais, caches ou
  dados de usuario no codigo, em prompts, no Git ou em artefatos publicados.
- Manter mudancas limitadas ao pedido e preservar alteracoes do usuario.
- Antes de declarar uma tarefa concluida, executar a verificacao adequada ao
  escopo e reportar falhas reais; nao inventar resultados.

## Roteamento de contexto

- Sempre: este arquivo e `docs/agents/README.md`.
- Prompts e interface: somente os arquivos de fonte envolvidos e os testes
  relacionados.
- Build, release, sincronizacao, instalador ou updater: ler `UPDATE.md` inteiro
  antes de executar qualquer comando operacional.
- Diagnostico de migracao antiga: ler tambem
  `docs/maintenance/release-history.md`, somente quando necessario.
- Handoff: `prompt_update.txt` e apenas um ponteiro; ele nao duplica o runbook.

## Gates canonicos

Para tarefas de entrega, os nomes dos gates sao `syntax`, `preflight`, `updater-v2-test` e
`ui-smoke`. Os comandos, versoes, caminhos, artefatos e criterios pertencem
exclusivamente a `UPDATE.md`.
