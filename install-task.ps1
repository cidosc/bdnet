param(
    [string]$At = '09:15',
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
$taskName = 'BDnet-DailySignIn'
$time = [datetime]::ParseExact($At, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture)

if (-not $PythonPath) {
    $localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython) {
        $PythonPath = $localPython
    } else {
        $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
    }
} else {
    $PythonPath = (Get-Command $PythonPath -ErrorAction Stop).Source
}

$runner = Join-Path $PSScriptRoot 'run.ps1'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -PythonPath "{1}"' -f $runner, $PythonPath
$action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -Hidden
$userId = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Output ('Registered {0}: daily at {1} (Windows local time), Python: {2}' -f $taskName, $At, $PythonPath)
