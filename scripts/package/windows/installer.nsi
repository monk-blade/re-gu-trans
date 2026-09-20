; re-gu-trans Windows installer (NSIS)
;
; Wraps the same payload/plugin/install.ps1 used by the .zip kit: this
; installer just stages those files under Program Files and then invokes
; install.ps1 (the actual Weasel deployment logic lives there, not here).
;
; Built by build_exe.sh, which first runs build_zip.sh to produce
; dist/windows-zip/{payload,plugin,install.ps1,install.bat,README.txt} and
; passes that directory in as -DSRC_DIR.

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef SRC_DIR
  !error "SRC_DIR must be defined (dist/windows-zip)"
!endif

Name "re-gu-trans ${VERSION}"
OutFile "re-gu-trans-${VERSION}-windows-x64-setup.exe"
InstallDir "$PROGRAMFILES64\re-gu-trans"
InstallDirRegKey HKLM "Software\re-gu-trans" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

!include "MUI2.nsh"

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install" SecInstall
  SetOutPath "$INSTDIR"
  File /r "${SRC_DIR}\payload"
  File /r "${SRC_DIR}\plugin"
  File "${SRC_DIR}\install.ps1"
  File "${SRC_DIR}\README.txt"

  WriteRegStr HKLM "Software\re-gu-trans" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\re-gu-trans" \
    "DisplayName" "re-gu-trans ${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\re-gu-trans" \
    "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\re-gu-trans" \
    "DisplayVersion" "${VERSION}"
  WriteUninstaller "$INSTDIR\uninstall.exe"

  DetailPrint "Deploying into Weasel (install.ps1)..."
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\install.ps1"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION|MB_OK \
      "install.ps1 exited with code $0.$\r$\n$\r$\nMake sure Weasel (小狼毫) is installed, then re-run this installer, or run install.ps1 manually from $INSTDIR."
  ${EndIf}
SectionEnd

Section "Uninstall"
  nsExec::ExecToLog 'powershell -NoProfile -Command "Get-Process -Name WeaselServer,WeaselDeployer,WeaselTSF -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"'
  RMDir /r "$INSTDIR\payload"
  RMDir /r "$INSTDIR\plugin"
  Delete "$INSTDIR\install.ps1"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\re-gu-trans"
  DeleteRegKey HKLM "Software\re-gu-trans"
SectionEnd
