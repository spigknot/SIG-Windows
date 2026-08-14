# SigUpdater

`SigUpdater.exe` is the source-controlled production updater for the SIG Windows
onedir installation. It preserves the command-line contract used by the app and
is rebuilt during every official release.

The legacy helper is preserved at:

`updater_v2\legacy\SigUpdater-legacy-20260806_004.exe`

The application copies the updater from the downloaded package to a temporary
path before closing. This lets an older installation migrate to the hardened
updater without depending on the helper it currently has installed.

Build it reproducibly with:

```powershell
.\updater_v2\build.ps1
```

Run source validation tests with:

```powershell
python scripts\release.py tests
```

Run the binary failure harness with:

```powershell
python scripts\release.py updater-v2-test
```

The existing CLI contract is preserved:

`--zip <package> --target <installation> --pid <SIG PID> --log <log>`

When opened without arguments, `SigUpdater.exe` starts its own graphical mode.
It relocates a copy of itself to `%LOCALAPPDATA%\sig\updater` before touching
the installation, so it can safely replace the installed updater too. In this
mode it can:

- download the signed incremental declared by the Drive manifest;
- install or repair from the latest full GitHub release;
- install the full package into an empty folder;
- close the SIG, apply the same transactional swap, validate startup and roll
  back automatically if the new build does not remain running.

The full GitHub asset must expose a SHA-256 digest through the Releases API.
Packages without a trusted digest are rejected before download.

The updater rejects unsafe ZIP paths, duplicate entries, symlinks, incomplete onedir
layouts, `g`, `_MEI`, nested `dist`, active processes and failed application
startup. It uses a same-volume transaction and restores the previous
installation if the new executable does not start.
