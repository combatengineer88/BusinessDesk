; TDZIGNS LLC PhoenixLedger — per-user Windows Setup installer.
; Compiled by GitHub Actions on Windows using Inno Setup 6.
#ifndef BuildVersion
  #define BuildVersion "3.1.0"
#endif
#define AppTitle "PhoenixLedger"
#define AppExe "PhoenixLedger.exe"

[Setup]
AppId={{4B4A0178-9F74-42A0-B56D-26342AF6C801}
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
UsePreviousAppDir=no
UninstallDisplayIcon={app}\{#AppExe}
SetupLogging=yes
SetupIconFile=phoenixledger.ico

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
