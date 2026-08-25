# Historico de transicao de distribuicao

Este documento e apenas para diagnostico de instalacoes antigas. Ele nao faz
parte do contexto universal nem do fluxo atual de release.

- `20260821_012`: sincronizacao pelo Drive e assets de executaveis no GitHub.
- `20260821_013`: versao-ponte; o aplicativo e o updater passaram a buscar o
  manifesto no R2, ainda com publicacao de migracao pelo fluxo antigo.
- `20260821_014` em diante: publicacao exclusiva pelo R2; o Drive ficou
  congelado na versao-ponte e o GitHub manteve o pacote full e instaladores.
- Durante a migracao, um PC antigo pode precisar passar pela versao-ponte antes
  de receber as versoes seguintes pelo canal atual.
