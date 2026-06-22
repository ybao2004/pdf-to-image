#define AppVer "0.0.7"

[Setup]
AppName=PDF to Image
AppVersion={#AppVer}
DefaultDirName={autopf}\PDF to Image
DefaultGroupName=PDF to Image
OutputBaseFilename=PDF to Image {#AppVer} - Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
SetupIconFile=app_icon.ico
CloseApplications=force
RestartApplications=no
ChangesAssociations=yes

[Languages]
Name: "vietnamese"; MessagesFile: "Vietnamese.isl"

[Files]
Source: "dist\PDF to Image\PDF to Image.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\PDF to Image\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\PDF to Image"; Filename: "{app}\PDF to Image.exe"; IconFilename: "{app}\app_icon.ico"
Name: "{autodesktop}\PDF to Image"; Filename: "{app}\PDF to Image.exe"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon; Check: Not FileExists(ExpandConstant('{autodesktop}\PDF to Image.lnk'))

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng ngoài màn hình Desktop (nếu chưa có)"; GroupDescription: "Tùy chọn thêm:"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PDFtoImageService"; ValueData: """{app}\PDF to Image.exe"" --action background"; Flags: uninsdeletevalue

; Recreate the cascade menu
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage"; ValueType: string; ValueName: "MUIVerb"; ValueData: "PDF to Image"; Flags: uninsdeletekey
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\app_icon.ico"
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage"; ValueType: string; ValueName: "SubCommands"; ValueData: ""
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"

Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd1"; ValueType: string; ValueData: "Tạo ảnh tại đây"
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd1"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\app_icon.ico"
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd1"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd1\command"; ValueType: string; ValueData: """{app}\PDF to Image.exe"" --client --action create_here --files ""%1"""

Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd2"; ValueType: string; ValueData: "Tạo ảnh vào thư mục riêng"
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd2"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\app_icon.ico"
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd2"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd2\command"; ValueType: string; ValueData: """{app}\PDF to Image.exe"" --client --action create_individual --files ""%1"""

Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd3"; ValueType: string; ValueData: "Tạo ảnh vào chung thư mục '#_pdf to image'"
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd3"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\app_icon.ico"
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd3"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCR; Subkey: "SystemFileAssociations\.pdf\shell\PDFtoImage\shell\cmd3\command"; ValueType: string; ValueData: """{app}\PDF to Image.exe"" --client --action create_combined --files ""%1"""

Root: HKCR; Subkey: "Directory\shell\PDFtoImageFolder"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\app_icon.ico"; Flags: uninsdeletekey
Root: HKCR; Subkey: "Directory\shell\PDFtoImageFolder"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKCR; Subkey: "Directory\shell\PDFtoImageFolder"; ValueType: string; ValueData: "PDF to Image: Chuyển đổi tất cả PDF trong thư mục này"
Root: HKCR; Subkey: "Directory\shell\PDFtoImageFolder\command"; ValueType: string; ValueData: """{app}\PDF to Image.exe"" --client --action create_individual --files ""%1"""

[Run]
Filename: "{app}\PDF to Image.exe"; Description: "Khởi động PDF to Image ngay bây giờ"; Flags: nowait postinstall skipifsilent

[InstallDelete]
Type: files; Name: "{commonstartup}\PDF to Image Service.lnk"
Type: files; Name: "{userstartup}\PDF to Image Service.lnk"

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im ""PDF to Image.exe"""; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}"






