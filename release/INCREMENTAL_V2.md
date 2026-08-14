# Incremental v2 — diff por hash + updater condicional + reparo

Design aprovado em 2026-08-14. Implementação em andamento (versão de referência:
`20260814_007` publicada no formato v1).

## Motivação

A incremental v1 leva o pacote inteiro menos os 4 assets de runtime
(~37,5 MB). Medição real do pacote `20260814_007`:

| Componente | Tamanho | Muda entre versões? |
|---|---|---|
| `sig.exe` | 4,0 MB | Sempre (PYZ embutido no exe) |
| `_internal/` | 47 MB | Quase nunca (DLLs/pyd de dependências) |
| `SigUpdater.exe` | 11 MB | Raríssimo (só quando `updater_v2/` muda) |
| `prompts/` + `modelos/` | 54 KB | Às vezes |

Meta: incremental típica de **~4,1 MB** (redução de ~89%).

## Formato da incremental v2

ZIP contendo:

- `sig.exe` — sempre.
- `_internal/...` — **somente arquivos novos ou alterados** em relação ao
  snapshot da última versão publicada (hash por arquivo).
- `SigUpdater.exe` — **somente se o hash mudou** desde a última versão publicada.
- `prompts/`, `modelos/`, `build-info.json` — sempre (pequenos).
- `removidos.txt` — um caminho relativo por linha, indicando arquivos que
  existiam na versão anterior e não existem mais (ex.: `_internal/foo.dll`).

Excluídos de sempre (inalterado): `ffmpeg.exe`, `ffplay.exe`, `vad_worker.py`,
`vad_deps`.

A assinatura do manifesto (sha256 do ZIP) cobre tudo, incluindo `removidos.txt`.
O manifesto (`latest.json`) mantém schema 1 e os campos atuais; o updater
detecta o diff pela presença de `removidos.txt` dentro do ZIP.

### Fallback de segurança

Se não houver snapshot versionado da versão anterior (primeira incremental v2,
histórico ausente), a incremental é gerada no formato v1 (pacote completo sem
runtime) — nunca gera diff sem base conhecida.

## Snapshot versionado

`release/content_snapshot.json` (commitado no repo):

```json
{
  "20260814_007": {
    "files": {
      "sig.exe": {"sha256": "...", "size": 123},
      "_internal/python311.dll": {"sha256": "...", "size": 456}
    }
  }
}
```

- Gerado do pacote completo, excluindo os 4 top-levels de runtime.
- `release.py` lê a entrada da versão imediatamente anterior para difar.
- Após publicar, o snapshot novo é gravado no arquivo (pronto para commit
  junto com o resto da release). A próxima release difa contra ele.

## Updater (`updater_v2/updater.py`)

- `validate_zip` passa a retornar o tipo: `"full"` | `"incremental"` |
  `"incremental-diff"` (diff = sem runtime + `removidos.txt` presente).
- Pacote diff não precisa conter os arquivos essenciais dentro do ZIP; a
  validação estrutural acontece no **estado final** (o `_apply_transaction`
  já valida a árvore instalada e a inicialização).
- Nova transação de merge para diff:
  - backup individual por arquivo (preservando a estrutura: `backup/_internal/foo.dll`);
  - aplica os arquivos do staged por cima;
  - remove os caminhos de `removidos.txt`;
  - journal registra os paths individuais (rollback já opera por nome).
- `removidos.txt` passa pelas MESMAS regras de segurança de nomes do ZIP
  (sem absolutos, sem `..`, sem nomes reservados, sem os top-levels proibidos,
  sem `g`/`_MEI`/`dist`).

## Reparo pelo pacote full

- O updater standalone já baixa o full do GitHub (digest obrigatório) e aplica
  com rollback — rede de segurança universal existente.
- Novo flag `--repair`: abre a GUI do updater e dispara o fluxo "Instalar /
  reparar completo" automaticamente após a checagem (mantém a confirmação).
- O SIG ganha o botão "Reparar instalação" (janela Sobre): localiza o
  `SigUpdater.exe`, copia para `%TEMP%`, invoca com `--repair`, encerra o SIG.

## Gates e testes

- `release_validation.py`: validar `removidos.txt` (segurança de nomes,
  top-levels permitidos) e o layout do ZIP diff.
- `updater_v2/harness.py`: novos cenários — diff sobre instalação completa
  (novo presente, removido ausente, intactos preservados), removidos
  malicioso rejeitado, rollback de diff.
- `release.py tests`: builder do diff, snapshot e removidos.
- End-to-end manual: instalação simulada com pacote 007 → aplica diff → estado
  final conferido.

## Peças afetadas por mudanças de formato (CHECKLIST OBRIGATÓRIO)

Qualquer mudança no formato de pacote (diff, nomes, membros obrigatórios)
precisa atualizar TODAS estas peças + testes:

1. `scripts/release.py` — geração do pacote (create_incremental_diff_tree).
2. `updater_v2/updater.py` — validação e aplicação (`validate_zip`,
   `_apply_diff_transaction`).
3. **`src/sig_app.py` → `SigApp._validate_update_package_archive`** — a
   validação do download no lado do SIG (a PEÇA ESQUECIDA no bug do
   "componentes obrigatórios ausentes" de 2026-08-14: a incremental diff
   foi publicada sem atualizar esta validação, que continuou exigindo o
   conjunto completo v1).
4. `scripts/release_validation.py` — gates de build/layout.

Testes obrigatórios (já permanentes):
- `updater_v2/test_updater.py` — validação do updater (diff e v1).
- `tests/test_update_package_validation.py` — validação do SIG (diff e v1).
- Teste end-to-end do fluxo do CLIQUE (SIG baixa → valida → updater aplica)
  em qualquer mudança de formato — não basta testar o aplicador sozinho.

## Ordem de implementação

1. `release.py` — snapshot + diff + removidos + updater condicional.
2. `updater_v2/updater.py` — tipo diff, transação de merge, `--repair`.
3. `updater_v2/harness.py` — cenários novos.
4. `src/sig_app.py` — botão Reparar.
5. Validações, testes e end-to-end.
6. Publicação `20260814_008` (incremental no Drive + full no GitHub) quando o usuário pedir.
