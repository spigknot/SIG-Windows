# SIG Windows 20260817_003

Correção do travamento da atualização em instalações do instalador.

## Correção

- **Transações do updater em pasta gravável**: a transação temporária da
  atualização era criada no diretório pai da instalação — em
  `C:\Program Files\SIG` o pai (`C:\Program Files`) não é gravável pelo usuário
  e a criação da pasta temporária TRAVAVA, deixando a atualização presa em
  "Aplicando a sincronização com rollback protegido" (o app fechava e não
  religava). As transações agora vivem em `%LOCALAPPDATA%\sig\updater\transactions`
  (sempre gravável, Inno e portable). A atualização volta a aplicar e religar o
  app normalmente — inclusive sem abrir como administrador.

Pacote full para instalação nova e instalador seguem como antes.
