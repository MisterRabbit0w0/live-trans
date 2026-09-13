#ifndef AppVersion
  #error AppVersion must be provided with /DAppVersion
#endif
#ifndef SourceDir
  #error SourceDir must point to the PyInstaller onedir output
#endif
#ifndef OutputDir
  #error OutputDir must point to the release artifact directory
#endif
#ifndef AppIcon
  #error AppIcon must point to the generated ICO
#endif

[Setup]
AppId={{A3C5CE66-4D76-47A5-A1BE-7483A13E9751}
AppName=LiveTrans
AppVersion={#AppVersion}
AppPublisher=MisterRabbit0w0
AppPublisherURL=https://github.com/MisterRabbit0w0/live-trans
AppSupportURL=https://github.com/MisterRabbit0w0/live-trans/issues
DefaultDirName={localappdata}\Programs\LiveTrans
DefaultGroupName=LiveTrans
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=LiveTrans-{#AppVersion}-windows-x64-setup
SetupIconFile={#AppIcon}
UninstallDisplayIcon={app}\LiveTrans.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=LiveTrans.exe
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LiveTrans"; Filename: "{app}\LiveTrans.exe"
Name: "{autodesktop}\LiveTrans"; Filename: "{app}\LiveTrans.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LiveTrans.exe"; Description: "Launch LiveTrans"; Flags: nowait postinstall skipifsilent

; User settings, logs and downloaded models are intentionally not uninstall targets.
