# run_armcheck.ps1 (Claude, 10.11.2026) - ТОЛЬКО ЧТЕНИЕ. Проверка «дрон разоружён» через MAVROS (pi\arm_state.sh). Ничего не пишет на дрон.
# Вызывается из 07_vzlet_zagotovka.cmd перед чтением настроек после полёта. Коды выхода: 0 дрон на связи и разоружён (armed=false); 5 взведён или состояние неизвестно; 4 ошибка связи/скрипта.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$file = BB-NewOutFile $outDir ('bench_armcheck_' + $stamp + '.txt')
$errFile = BB-NewOutFile $outDir ('bench_armcheck_' + $stamp + '.err.txt')
$sh = Join-Path $here 'pi\arm_state.sh'
if (-not (Test-Path -LiteralPath $sh)) { BB-Stop ('нет файла ' + $sh) 4 }
$ssh = BB-FindSsh
BB-TestDrone $ssh
$remote = BB-RemoteCommand $sh @()
$rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $file $errFile 60
$raw = ''; if (Test-Path -LiteralPath $file) { $raw = [IO.File]::ReadAllText($file) }
if ($rc -ne 0 -or $raw -notmatch 'BB_ARM_STATE_DONE') { Write-Host ('  Состояние «взведён/нет» не прочитано (код ' + $rc + '). Считаю, что дрон может быть взведён.'); exit 5 }
if ($raw -match 'BB_ARM connected=true armed=false') { Write-Host '  Дрон на связи и разоружён (armed=false).'; exit 0 }
if ($raw -match 'armed=true') { Write-Host '  Дрон ВЗВЕДЁН (armed=true).' -ForegroundColor White -BackgroundColor Red; exit 5 }
Write-Host ('  Состояние неясно: ' + (($raw -split "`r?`n" | Where-Object { $_ -match '^BB_ARM ' } | Select-Object -First 1)) + '. Считаю, что дрон может быть взведён.')
exit 5