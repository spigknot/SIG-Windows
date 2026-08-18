# SIG Windows 20260817_010

## Limpeza de dependências

- Removida a dependência **websockets** do requirements.txt (nunca importada
  em nenhum módulo — o app usa o websocket-client). Build mais enxuto.

## GitHub limpo

- Releases antigas removidas do GitHub (SIG-Windows e SIG-Android): só a
  versão mais atual permanece em cada repositório.
