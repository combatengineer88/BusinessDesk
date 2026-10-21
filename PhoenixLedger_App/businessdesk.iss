; TDZIGNS LLC PhoenixLedger — per-user Windows Setup installer.
; Compiled by GitHub Actions on Windows using Inno Setup 6.
#ifndef BuildVersion
  #define BuildVersion "2.9.12"
#endif
#define AppTitle "PhoenixLedger"
#define AppExe "PhoenixLedger.exe"

[Setup]
AppId={{D19D89FE-3899-4CBD-A6D6-81582D0324A4}
AppName={#AppTitle}
AppVersion={#BuildVersion}
AppPublisher=TDZIGNS LLC
AppPublisherURL=https://github.com/combatengineer88/BusinessDesk
DefaultDirName={localappdata}\Programs\PhoenixLedger
DefaultGroupName=PhoenixLedger
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=output
OutputBaseFilename=PhoenixLedger_Setup_{#BuildVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableDirPage=yes
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UninstallDisplayIcon={app}\{#AppExe}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\PhoenixLedger\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PhoenixLedger"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\PhoenixLedger"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch PhoenixLedger"; Flags: nowait postinstall skipifsilent

; PhoenixLedger stores all business records outside the installation folder:
; %LOCALAPPDATA%\PhoenixLedger\business.db (and associated user files).
; No [UninstallDelete] directive touches that data folder.
