# Roteamento de contexto do agente

Este arquivo e estavel e curto. Ele define quando abrir documentos condicionais;
nao repete comandos, versoes, hashes, caminhos de maquina ou estado de release.

## Sempre carregar

1. `AGENTS.md`
2. Este arquivo

## Carregar somente quando a tarefa exigir

| Tarefa | Fonte adicional | Regra |
| --- | --- | --- |
| Alterar codigo, UI, prompts ou testes | arquivos de fonte envolvidos e testes relacionados | Nao carregar o runbook de release sem necessidade |
| Compilar, publicar, sincronizar, gerar instalador ou atualizar | `UPDATE.md` | Ler o runbook completo antes de executar comandos |
| Auditar ou ajustar saída de testes, build e publicação | `docs/agents/validation-output.md` | Usar o contrato quiet e manter diagnóstico completo em log |
| Diagnosticar migracao de instalacao antiga | `docs/maintenance/release-history.md` | Abrir somente quando o caso depender da transicao historica |
| Preparar handoff de release | `prompt_update.txt` | Usar apenas como ponteiro para as fontes canonicas |

## Regra de cache

O prefixo universal deve conter somente invariantes e roteamento. Conteudo
condicional deve ser acrescentado depois da selecao da tarefa. Nao copiar uma
segunda versao de um procedimento para outro arquivo.
