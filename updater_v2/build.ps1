param(
    [string]$Python = "C:\Users\Gustavo\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe",
    [string]$Output = "",
    [long]$SourceDateEpoch = 946684800,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python de build não encontrado: $Python"
}

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $root "updater_v2\bin"
}
$work = Join-Path $root "build\updater_v2"
New-Item -ItemType Directory -Force -Path $Output | Out-Null
if (Test-Path -LiteralPath $work) {
    Remove-Item -LiteralPath $work -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $work | Out-Null
$logPath = Join-Path $work "pyinstaller.log"

$previousSourceDateEpoch = [Environment]::GetEnvironmentVariable("SOURCE_DATE_EPOCH", "Process")
$previousPythonHashSeed = [Environment]::GetEnvironmentVariable("PYTHONHASHSEED", "Process")
$env:SOURCE_DATE_EPOCH = [string]$SourceDateEpoch
$env:PYTHONHASHSEED = "0"
try {
    $pyinstallerArgs = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--noupx",
        "--name", "SigUpdater",
        "--distpath", $Output,
        "--workpath", $work,
        "--specpath", $work,
        (Join-Path $PSScriptRoot "updater.py")
    )
    if ($Quiet) {
        $pyinstallerArgs = @("-m", "PyInstaller", "--log-level", "WARN") + $pyinstallerArgs[2..($pyinstallerArgs.Length - 1)]
        & $Python @pyinstallerArgs *> $logPath
    }
    else {
        & $Python @pyinstallerArgs
    }
    if ($LASTEXITCODE -ne 0) {
        if ($Quiet) {
            throw "PyInstaller falhou com código $LASTEXITCODE; consulte $logPath"
        }
        throw "PyInstaller falhou com código $LASTEXITCODE"
    }

    $artifact = Join-Path $Output "SigUpdater.exe"
    if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
        throw "PyInstaller não produziu $artifact"
    }
    if ($Quiet) {
        $size = (Get-Item -LiteralPath $artifact).Length
        $hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash
        Write-Host "PASS: SigUpdater.exe size=$size sha256=$hash"
    }
    else {
        Write-Host "PASS: $artifact"
        Get-FileHash -LiteralPath $artifact -Algorithm SHA256
    }
}
finally {
    if ($null -eq $previousSourceDateEpoch) {
        Remove-Item Env:\SOURCE_DATE_EPOCH -ErrorAction SilentlyContinue
    }
    else {
        $env:SOURCE_DATE_EPOCH = $previousSourceDateEpoch
    }
    if ($null -eq $previousPythonHashSeed) {
        Remove-Item Env:\PYTHONHASHSEED -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONHASHSEED = $previousPythonHashSeed
    }
}
