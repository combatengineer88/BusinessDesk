; TDZIGNS LLC BusinessDesk — per-user Windows Setup installer.
; Compiled by GitHub Actions on Windows using Inno Setup 6.
#ifndef BuildVersion
  #define BuildVersion "2.9.12"
#endif
#define AppTitle "TDZIGNS BusinessDesk"
#define AppExe "TDZIGNS_BusinessDesk.exe"

[Setup]
AppId={{D19D89FE-3899-4CBD-A6D6-81582D0324A4}
AppName={#AppTitle}
AppVersion={#BuildVersion}
AppPublisher=TDZIGNS LLC
AppPublisherURL=https://github.com/combatengineer88/BusinessDesk
DefaultDirName={localappdata}\Programs\TDZIGNS BusinessDesk
DefaultGroupName=TDZIGNS BusinessDesk
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=output
OutputBaseFilename=TDZIGNS_BusinessDesk_Setup_{#BuildVersion}
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
Source: "dist\TDZIGNS_BusinessDesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\TDZIGNS BusinessDesk"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\TDZIGNS BusinessDesk"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch TDZIGNS BusinessDesk"; Flags: nowait postinstall skipifsilent

; BusinessDesk stores all business records outside the installation folder:
; %LOCALAPPDATA%\BusinessDesk\business.db (and associated user files).
; No [UninstallDelete] directive touches that data folder.
