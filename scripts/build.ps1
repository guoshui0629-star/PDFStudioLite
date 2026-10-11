$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$OriginalPath = $env:PATH

if (-not (Test-Path -LiteralPath $Python)) {
    throw '未找到项目虚拟环境，请先创建 .venv 并安装 requirements.txt。'
}

Push-Location $ProjectRoot
try {
    & $Python -m pytest
    if ($LASTEXITCODE -ne 0) { throw '测试失败，已停止打包。' }
    # Codex may expose its bundled Poppler on PATH. Its ICU DLLs share names
    # with Windows system ICU but are ABI-incompatible with Qt 6, so never let
    # PyInstaller collect binaries from that external runtime.
    $env:PATH = (($OriginalPath -split ';' | Where-Object {
        $_ -notmatch 'codex-primary-runtime[\\/]dependencies[\\/]native[\\/]poppler'
    }) -join ';')
    & $Python -m PyInstaller --noconfirm --clean --windowed --name 'PDFStudioLite' --icon 'ui\assets\branding\pdf-toaster-app.ico' --add-data 'ui\assets;ui\assets' --runtime-hook 'scripts\pyi_rth_dll_paths.py' --collect-all pymupdf --collect-all pikepdf 'app\main.py'
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 打包失败。' }
    $Executable = Join-Path $ProjectRoot 'dist\PDFStudioLite\PDFStudioLite.exe'
    $SelfTest = Start-Process -FilePath $Executable -ArgumentList '--self-test' -Wait -PassThru
    if ($SelfTest.ExitCode -ne 0) { throw "打包程序自检失败，退出码：$($SelfTest.ExitCode)。" }
    & (Join-Path $PSScriptRoot 'create_shortcut.ps1')
    Write-Host "构建完成：$ProjectRoot\dist\PDFStudioLite\PDFStudioLite.exe"
}
finally {
    $env:PATH = $OriginalPath
    Pop-Location
}
