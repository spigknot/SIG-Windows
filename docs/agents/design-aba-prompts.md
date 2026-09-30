# Design — aba Prompts (Configurações) + atualização pelo R2

Data: 29/09/2026 · Projeto: SIG Windows · Status: implementado

## 1. Problema

Os prompts de histórico, oitiva e qualificação eram carregados de arquivos
externos (`prompts/` ao lado do executável), sem nenhuma forma de o usuário
ver, editar, escolher ou trocar por uma versão mais nova sem instalar um app
novo.

## 2. Decisões do dono (29/09/2026)

| Tema | Decisão |
|---|---|
| Onde gravar | `%APPDATA%\sig\Prompts\` — `C:\Program Files` exige elevação (o instalador é `PrivilegesRequired=admin`) e o botão de download pediria UAC a cada uso. |
| Slots da tela | **Histórico, Oitiva e Qualificação** (6 arquivos: `system` + `user` de cada). |
| Escopo do download | Baixa **todos os `.txt` da raiz** de `prompts/` (9, incluindo os de `partes`, para uso futuro) e **ignora a subpasta** `prompts_antigos/`. |
| Só baixa se mudar | Se o conteúdo do R2 for **igual** ao local, o botão não baixa nem grava nada. |
| Padrão do app | Id `Padrão`, **nunca sobrescrevível**. Editar o Padrão só é possível com `SALVAR COMO` (outro nome) ou importando outro `.txt`. |
| Atualizar sem reinstalar | O botão baixa do bucket R2 `prompts` e substitui o padrão, preservando os customizados. |

## 3. Layout da pasta do usuário

```
%APPDATA%\sig\Prompts\
  padrao\<arquivo>          padrão vigente (seed do app, trocado pelo R2)
  custom\<slot>\<id>.txt    prompts do usuário
  ativo.json                {"historico_system": "Padrão" | "<id>", ...}
  origem.json               hashes do que foi baixado (evita rebaixar)
```

- `Padrão` é protegido: `save_custom` recusa o id.
- O download **só escreve em `padrao/`** — os customizados são preservados por construção.
- Leitura: `ativo.json` → `custom/`; em branco ou ausente → `padrao/`.

## 4. Núcleo testável (`src/prompt_store.py`, sem Tkinter)

- `PromptSlot` — os 6 slots gerenciados, com o marcador exigido.
- `PromptStore` — layout, migração, resolução do ativo, gravação, importação.
- `apply_defaults` — **all-or-nothing**: se um dos 9 reprovar, nada é gravado.
- `download_updates` — baixa os 9 da raiz, compara sha256 e **não escreve
  nada** quando o conjunto é idêntico ao local.
- `manifest.json` no bucket (gerado por `scripts/sync_prompts_r2.py`): quando
  presente, um GET só decide se há versão nova antes de baixar qualquer prompt.

### Por que o manifesto é gerado pelo sync

O manifesto é **derivado dos mesmos bytes que o sync publica** — nunca escrito
à mão. Um manifesto envelhecido é pior do que não tê-lo: o app leria
"já atualizado" e **não baixaria um prompt novo**, sem nenhum erro visível.
Por isso o `build_manifest` do script é a única fonte e um teste reprova se
ele divergir do que sobe.

## 5. Vacinas (`tests/test_prompt_store.py`)

Padrão protegido; `save_custom`; `save_as`; import; inferência de slot;
fallback `custom` → `Padrão`; validação por marcador/tamanho/vazio;
all-or-nothing do download; **"igual não baixa"**; preservação dos customizados
depois do download; parsing do manifesto; layout em `%APPDATA%`.

## 6. Fora de escopo

- Slots de `partes` na tela (baixam junto, mas não são editáveis aí).
- Exclusão de customizados pela tela.
