# SIG Windows 20260814_013

Pacote completo para instalação nova ou reparo.

- Corrige a sincronização por arquivo para instalações em unidade de disco
  diferente do cache do atualizador (WinError 17): o movimento entre
  volumes agora copia e remove a origem quando o sistema não permite
  renomear entre unidades.
- Atualização principal pela sincronização por arquivo (manifesto assinado
  no Drive); incremental ZIP e pacote completo do GitHub seguem disponíveis
  como contingência.

> Instalação: extraia o ZIP e execute `sig.exe` (mantenha `_internal` ao lado).
> Atualização: abra o `SigUpdater.exe` (Verificar → Atualizar).
