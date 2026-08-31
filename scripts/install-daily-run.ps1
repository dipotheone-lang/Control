# Register the daily run as a Windows scheduled task.
#
# Why PowerShell rather than schtasks alone: schtasks /SC DAILY /ST 07:00
# fires at 07:00 or not at all. On a laptop that is asleep at 07:00 the
# run is simply skipped, and under decision D-58 a skipped run is a class
# 1 alert nobody received. -StartWhenAvailable makes Windows run it at the
# next opportunity instead - the first moment the machine is awake.
#
# That does not make the route reliable, and D-58 does not pretend it
# does. It narrows the window from "the whole day was lost" to "the alert
# went out late". Late is worse than on time and far better than never.
#
# The task runs whether or not the machine is on mains power. The default
# is to skip on battery, which on a laptop means the alert depends on
# where the charger is.

param(
    [Parameter(Mandatory = $true)][string] $RepoRoot,
    [string] $TaskName = 'Control daily run',
    [string] $At = '07:00'
)

$ErrorActionPreference = 'Stop'

$runner = Join-Path $RepoRoot 'Run Control.cmd'
if (-not (Test-Path -LiteralPath $runner)) {
    throw "not found: $runner"
}

$action = New-ScheduledTaskAction -Execute 'cmd.exe' `
    -Argument ('/c "' + $runner + '" /scheduled') `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -Daily -At $At

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
$info = $task | Get-ScheduledTaskInfo

Write-Output ''
Write-Output ("  Registered: {0}" -f $task.TaskName)
Write-Output ("  Next run:   {0}" -f $info.NextRunTime)
Write-Output '  Missed runs are picked up when the machine next wakes,'
Write-Output '  and it runs on battery as well as on mains.'
