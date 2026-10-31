param(
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$logDirectory = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logPath = Join-Path $logDirectory ((Get-Date -Format 'yyyy-MM-dd') + '.log')

try {
    if (-not $PythonPath) {
        $localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $localPython) {
            $PythonPath = $localPython
        } else {
            $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
        }
    }
    $PythonPath = (Get-Command $PythonPath -ErrorAction Stop).Source
    $env:PYTHONIOENCODING = 'utf-8'
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

    # Windows PowerShell 5.1 represents native stderr as ErrorRecord objects.
    $ErrorActionPreference = 'Continue'
    & $PythonPath -u (Join-Path $PSScriptRoot 'du.py') 2>&1 |
        ForEach-Object { '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:sszzz'), $_ } |
        Out-File -LiteralPath $logPath -Encoding utf8 -Append -ErrorAction Stop
    $exitCode = $LASTEXITCODE
} catch {
    '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:sszzz'), $_ |
        Out-File -LiteralPath $logPath -Encoding utf8 -Append
    $exitCode = 1
}

exit $exitCode
