$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Executable = Join-Path $ProjectRoot 'dist\PDFStudioLite\PDFStudioLite.exe'
$Icon = Join-Path $ProjectRoot 'ui\assets\branding\pdf-toaster-app.ico'
$ShortcutPath = Join-Path $ProjectRoot 'PDF Studio Lite.lnk'

if (-not (Test-Path -LiteralPath $Executable)) {
    throw "未找到可执行文件：$Executable"
}
if (-not (Test-Path -LiteralPath $Icon)) {
    throw "未找到应用图标：$Icon"
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Executable
$Shortcut.WorkingDirectory = Split-Path -Parent $Executable
$Shortcut.IconLocation = "$Icon,0"
$Shortcut.Description = 'PDF Studio Lite — 本地 PDF 工具'
$Shortcut.Save()
Write-Host "快捷方式已更新：$ShortcutPath"
