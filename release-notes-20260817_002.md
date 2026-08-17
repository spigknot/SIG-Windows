# SIG Windows 20260817_002

Correção de atualização em instalações do instalador.

## Correção

- **Lock de atualização dentro da pasta do app**: em instalações em
  `C:\Program Files\SIG` (feitas pelo instalador), o lock da transação ficava
  no `Program Files` — pasta sem permissão de escrita do usuário — e a
  atualização falhava com `Permission denied` (o app fechava e não religava).
  Agora o lock fica dentro da pasta do SIG, que é gravável tanto na instalação
  Inno quanto na instalação portable. A atualização volta a aplicar e religar o
  app normalmente.
- Teste de regressão cobre a localização do lock (nunca no pai da pasta).

Pacote full para instalação nova e instalador seguem como antes.
