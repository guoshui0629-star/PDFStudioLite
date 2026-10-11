$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$OriginalPath = $env:PATH

if (-not (Test-Path -LiteralPath $Python)) {
    throw '未找到项目虚拟环境。'
}

Push-Location $ProjectRoot
try {
    & $Python -m pytest
    if ($LASTEXITCODE -ne 0) { throw '测试失败，已停止 V2 打包。' }
    $env:PATH = (($OriginalPath -split ';' | Where-Object {
        $_ -notmatch 'codex-primary-runtime[\\/]dependencies[\\/]native[\\/]poppler'
    }) -join ';')
    & $Python -m PyInstaller --noconfirm --clean --windowed --name 'PDFStudioLiteV2' --icon 'ui\assets\branding\pdf-toaster-app.ico' --add-data 'ui\assets;ui\assets' --runtime-hook 'scripts\pyi_rth_dll_paths.py' --collect-all pymupdf --collect-all pikepdf 'app\main.py'
    if ($LASTEXITCODE -ne 0) { throw 'V2 PyInstaller 打包失败。' }

    $Executable = Join-Path $ProjectRoot 'dist\PDFStudioLiteV2\PDFStudioLiteV2.exe'
    $SelfTest = Start-Process -FilePath $Executable -ArgumentList '--self-test' -Wait -PassThru
    if ($SelfTest.ExitCode -ne 0) { throw "V2 自检失败，退出码：$($SelfTest.ExitCode)。" }

    $ShortcutPath = Join-Path $ProjectRoot 'PDF Studio Lite V2.lnk'
    $Icon = Join-Path $ProjectRoot 'ui\assets\branding\pdf-toaster-app.ico'
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Executable
    $Shortcut.WorkingDirectory = Split-Path -Parent $Executable
    $Shortcut.IconLocation = "$Icon,0"
    $Shortcut.Description = 'PDF Studio Lite V2 Preview'
    $Shortcut.Save()
    Write-Host "V2 构建完成：$Executable"
    Write-Host "V2 快捷方式：$ShortcutPath"
}
finally {
    $env:PATH = $OriginalPath
    Pop-Location
}
