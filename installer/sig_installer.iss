; SIG Windows — instalador (Inno Setup 6)
; Gerado pelo release.py com -DAppVersion=<versao>.
#ifndef AppVersion
  #define AppVersion "dev"
#endif

[Setup]
AppId={{B7E2C4A1-9F3D-4E6B-8C2A-5D1F9A7B3E6C}
AppName=SIG
AppVersion={#AppVersion}
AppPublisher=SIG
DefaultDirName={autopf}\SIG
DefaultGroupName=SIG
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release\generated\{#AppVersion}
OutputBaseFilename=sig_setup_{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\sig.exe
SetupLogging=yes

[Files]
; Arvore completa do package validado pelo release.py.
Source: "..\release\generated\{#AppVersion}\package\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Dirs]
; O app e o updater escrevem na pasta em runtime (temp/, updates) SEM admin.
Name: "{app}"; Permissions: users-modify

[Icons]
Name: "{autodesktop}\SIG"; Filename: "{app}\sig.exe"; WorkingDir: "{app}"; Comment: "SIG - transcricao policial"
Name: "{autoprograms}\SIG\SIG"; Filename: "{app}\sig.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\SigUpdater"; Filename: "{app}\SigUpdater.exe"; WorkingDir: "{app}"; Comment: "Atualizar ou reparar o SIG"
Name: "{autoprograms}\SIG\SigUpdater"; Filename: "{app}\SigUpdater.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\SIG\Desinstalar SIG"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\sig.exe"; Description: "Abrir o SIG agora"; Flags: nowait postinstall skipifsilent
