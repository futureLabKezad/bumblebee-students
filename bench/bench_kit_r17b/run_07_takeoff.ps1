# run_07_takeoff.ps1 (Claude, 10.11.2026) - ЗАГОТОВКА. МЕНЯЕТ ДРОН: ВЗЛЁТ, моторы запустятся скриптом полёта на Pi. Запускается ТОЛЬКО из 07_vzlet_zagotovka.cmd двойным щелчком владельца.
# Claude этот файл не запускает (правило 1 и решение владельца 10.11 «запуск скрипта - вариант 2»). Условия запуска проверяются здесь, до любого обращения к дрону:
#   takeoff.conf заполнен (путь и sha256 скрипта, без TBD); gates\TAKEOFF_APPROVED.txt создан чатом 1 после слов владельца о шаге 14 и называет тот же sha и те же аргументы (АРГУМЕНТЫ=); свободных параметров у .cmd нет;
#   свежая (не старше 30 мин) сверка настроек «СОВПАДАЕТ» из набора r4 (r11: или «СОВПАДАЕТ (гироскоп сдвинулся: N, запись)» - решение владельца 16.11); (21:50, S1) успешные 09 и 10 после последнего 16/17 или сборки, не старше 180 мин; подтверждения мер безопасности; отсчёт не меньше 10 с.
# 20:10 (решение чата 1): скрипт полёта берётся ИЗ ОВЕРЛЕЯ /home/lb/bench_ws/r2j/src/bumblebee/examples/ и перед отсчётом проверяется (только чтением), что drone.py, который он импортирует (sys.path.insert) и который лежит рядом, равен r2j (DRONE_PY_SHA256 в takeoff.conf); иначе код 4.
# r12 (17.11): успешная 09 должна быть ещё и позже последней установки/отката любого пакета drone_pkg_* (журналы <папка проекта>\drone_pkg_*\out\*.log), см. 3c.
# Коды выхода: 0 скрипт отработал (код 0 на Pi); 1 скрипт на Pi завершился с ошибкой или был прерван; 4 условия не выполнены, к дрону не обращались либо ошибка связи.
param(
    [Parameter(Mandatory = $true)][string]$SafetyConfirmed,
    [int]$CountdownSec = 10,
    [string]$ConfPath = '',
    [string]$MaxParamsAgeMin = '30'
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_lists.ps1')
BB-AssertPc
$defConf = Join-Path $here 'takeoff.conf'
$outDir = BB-OutDir $here
$bad = New-Object Collections.Generic.List[string]
function No([string]$s) { $script:bad.Add($s) }
if (-not $ConfPath) { $ConfPath = $defConf } elseif ([IO.Path]::GetFullPath($ConfPath) -ne [IO.Path]::GetFullPath($defConf)) { No 'takeoff.conf можно брать только рядом с этим скриптом (свободный путь не принимается).' }
$maxAge = 0.0; if (-not [double]::TryParse($MaxParamsAgeMin, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$maxAge) -or [double]::IsNaN($maxAge) -or $maxAge -gt 30 -or $maxAge -le 0) { No ('возраст сверки настроек можно задавать только от 0 до 30 минут, а не ' + $MaxParamsAgeMin) }

if ($CountdownSec -lt 10 -or $CountdownSec -gt 300) { No ('отсчёт должен быть от 10 до 300 секунд, а не ' + $CountdownSec) }
if ($SafetyConfirmed -ne 'NET-TWO-KILL-YES') { No 'не получены все четыре подтверждения мер безопасности (сетка, два человека, палец на выключателе, YES). Запускайте только через 07_vzlet_zagotovka.cmd.' }

# 1. takeoff.conf
$cfg = @{}
if (-not (Test-Path -LiteralPath $ConfPath)) { No ('нет takeoff.conf: ' + $ConfPath) }
else {
    foreach ($l in [IO.File]::ReadAllLines($ConfPath)) {
        $t = $l.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $i = $t.IndexOf('='); if ($i -gt 0) { $cfg[$t.Substring(0, $i).Trim()] = $t.Substring($i + 1).Trim() }
    }
    foreach ($k in 'SCRIPT_REMOTE_PATH', 'SCRIPT_SHA256', 'DRONE_PY_SHA256') {
        if (-not $cfg.ContainsKey($k) -or $cfg[$k] -eq '' -or $cfg[$k] -match 'TBD') { No ('в takeoff.conf не заполнено ' + $k + ' (TBD): скрипт полёта ещё не назначен.') }
    }
    if ($cfg.ContainsKey('SCRIPT_REMOTE_PATH') -and $cfg['SCRIPT_REMOTE_PATH'] -notmatch 'TBD' -and $cfg['SCRIPT_REMOTE_PATH'] -cnotmatch '^/home/lb/[A-Za-z0-9_./-]+\.py$') { No ('SCRIPT_REMOTE_PATH должен быть вида /home/lb/.../имя.py без пробелов и «..»: ' + $cfg['SCRIPT_REMOTE_PATH']) }
    if ($cfg.ContainsKey('SCRIPT_REMOTE_PATH') -and $cfg['SCRIPT_REMOTE_PATH'] -match '\.\.') { No 'в SCRIPT_REMOTE_PATH есть «..»' }
    if ($cfg.ContainsKey('DRONE_PY_SHA256') -and $cfg['DRONE_PY_SHA256'] -notmatch 'TBD' -and $cfg['DRONE_PY_SHA256'] -cnotmatch '^[0-9a-f]{64}$') { No 'DRONE_PY_SHA256 должен быть 64 символа 0-9a-f (sha256 drone.py образа r2j)' }
    if ($cfg.ContainsKey('SCRIPT_REMOTE_PATH') -and $cfg['SCRIPT_REMOTE_PATH'] -notmatch 'TBD' -and $cfg['SCRIPT_REMOTE_PATH'] -cnotmatch '^/home/lb/bench_ws/r2j/src/bumblebee/examples/') { No ('скрипт полёта должен лежать в оверлее /home/lb/bench_ws/r2j/src/bumblebee/examples/... (решение чата 1 20:10: иначе исправления r2j на дроне не сработают), а не ' + $cfg['SCRIPT_REMOTE_PATH']) }
    if ($cfg.ContainsKey('SCRIPT_SHA256') -and $cfg['SCRIPT_SHA256'] -notmatch 'TBD' -and $cfg['SCRIPT_SHA256'] -cnotmatch '^[0-9a-f]{64}$') { No 'SCRIPT_SHA256 должен быть 64 символа 0-9a-f' }
    if ($cfg.ContainsKey('SCRIPT_ARGS') -and $cfg['SCRIPT_ARGS'] -cnotmatch '^[A-Za-z0-9_. =:/-]*$') { No 'SCRIPT_ARGS содержит недопустимые знаки' }
}
# 2. разрешение на шаг 14
$ap = Join-Path $here 'gates\TAKEOFF_APPROVED.txt'
if (-not (Test-Path -LiteralPath $ap)) { No 'нет gates\TAKEOFF_APPROVED.txt: чат 1 создаёт его только после слов владельца о шаге 14 (взлёт).' }
else {
    $at = Get-Content -LiteralPath $ap -Encoding UTF8
    foreach ($k in 'ШАГ=14', 'ВЗЛЁТ_РАЗРЕШИЛ=владелец', 'СОЗДАЛ=чат 1') { if (-not ($at | Where-Object { $_.Trim() -eq $k })) { No ('в TAKEOFF_APPROVED.txt нет строки ' + $k) } }
    foreach ($k in 'ДАТА=', 'СЛОВА_ВЛАДЕЛЬЦА=') { if (-not ($at | Where-Object { $_.Trim().StartsWith($k) -and $_.Trim().Length -gt $k.Length })) { No ('в TAKEOFF_APPROVED.txt нет заполненной строки ' + $k + '...') } }
    if ($cfg.ContainsKey('DRONE_PY_SHA256') -and $cfg['DRONE_PY_SHA256'] -notmatch 'TBD' -and $cfg['DRONE_PY_SHA256'] -cnotmatch '^[0-9a-f]{64}$') { No 'DRONE_PY_SHA256 должен быть 64 символа 0-9a-f (sha256 drone.py образа r2j)' }
    if ($cfg.ContainsKey('SCRIPT_REMOTE_PATH') -and $cfg['SCRIPT_REMOTE_PATH'] -notmatch 'TBD' -and $cfg['SCRIPT_REMOTE_PATH'] -cnotmatch '^/home/lb/bench_ws/r2j/src/bumblebee/examples/') { No ('скрипт полёта должен лежать в оверлее /home/lb/bench_ws/r2j/src/bumblebee/examples/... (решение чата 1 20:10: иначе исправления r2j на дроне не сработают), а не ' + $cfg['SCRIPT_REMOTE_PATH']) }
    if ($cfg.ContainsKey('SCRIPT_SHA256') -and $cfg['SCRIPT_SHA256'] -notmatch 'TBD' -and -not ($at | Where-Object { $_.Trim() -ceq ('СКРИПТ_SHA256=' + $cfg['SCRIPT_SHA256']) })) { No 'sha256 скрипта в TAKEOFF_APPROVED.txt не совпадает с takeoff.conf' }
    $apArgsLine = $at | Where-Object { $_.Trim().StartsWith('АРГУМЕНТЫ=') } | Select-Object -First 1
    if ($null -eq $apArgsLine) { No 'в TAKEOFF_APPROVED.txt нет строки АРГУМЕНТЫ= (значение может быть пустым, но строка обязательна: аргументы скрипта привязаны к разрешению).' }
    else {
        $apArgs = $apArgsLine.Trim().Substring('АРГУМЕНТЫ='.Length).Trim(); $cfArgs = ''; if ($cfg.ContainsKey('SCRIPT_ARGS')) { $cfArgs = $cfg['SCRIPT_ARGS'] }
        if ($apArgs -cne $cfArgs) { No ('аргументы скрипта в takeoff.conf («' + $cfArgs + '») не равны АРГУМЕНТЫ в TAKEOFF_APPROVED.txt («' + $apArgs + '»): после одобрения аргументы менять нельзя.') }
    }
}
# 3. свежая сверка настроек
$rep = $null
$rps = @(Get-ChildItem -LiteralPath $outDir -Filter 'params_*_report.txt' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime)
if ($rps.Count -gt 0) { $rep = $rps[-1] }
if (-not $rep) { No 'нет сверки настроек (out\params_*_report.txt): сначала 01_snimok_do.cmd этого набора (r4-вый params_check.cmd напрямую не запускать: его отчёт ложится в другую папку).' }
else {
    $age = ((Get-Date) - $rep.LastWriteTime).TotalMinutes
    if ($age -gt $maxAge) { No ('последняя сверка настроек старая: ' + [int]$age + ' мин, нужна не старше ' + $MaxParamsAgeMin) }
    $first = Get-Content -LiteralPath $rep.FullName -Encoding UTF8 -TotalCount 1
    # r11 (решение владельца 16.11 «Не стоп, только запись»): кроме строгого «СОВПАДАЕТ» (как в r9) принимается только точный вид оценщика r11
    # «СОВПАДАЕТ (гироскоп сдвинулся: N, запись) ... других отличий нет (из таблицы MAVROS N, из запасного потока 0)»: отличались ТОЛЬКО CAL_GYRO0..3_XOFF/YOFF/ZOFF.
    if ($first -notmatch '^=== СОВПАДАЕТ: прочитано (\d+) из \1, отличий нет \(из таблицы MAVROS \1, из запасного потока 0\)' -and $first -notmatch '^=== СОВПАДАЕТ \(гироскоп сдвинулся: [1-9]\d*, запись\): прочитано (\d+) из \1, других отличий нет \(из таблицы MAVROS \1, из запасного потока 0\)') { No ('последняя сверка не «СОВПАДАЕТ полностью из таблицы MAVROS»: ' + $first) }
    if ([IO.File]::ReadAllText($rep.FullName) -match 'AllowStreamFallback') { No 'отчёт сверки сделан с -AllowStreamFallback, не годится' }
}
# 3b. (решение чата 1, 21:50, S1) свежие УСПЕШНЫЕ сверки 09 (что исполняется, install_check) и 10 (какой MAVROS, mavros_check) ПОСЛЕ последнего подключения/отключения оверлея (16/17), сборки/отката сборки (13, 14, 11, 12) или установки/отката образа (05, 05v, 06: out\install_r2j_*.log, rollback_r2j_*.log, install_camera_dabd5076_*.log); не старше 180 минут.
# Иначе скрипт r2j мог бы лететь на старом C++ из ros2_ws/install или на apt-MAVROS. Успех = последний файл сверки с последней строкой «# VERDICT OK» (её пишут 09 и 10 при коде 0).
$evt = @(Get-ChildItem -LiteralPath $outDir -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^(overlay_connect_|overlay_disconnect_|bb_build_|bb_aside_|mavros_build_|mavros_aside_|install_r2j_|rollback_r2j_|install_camera_dabd5076_)' -and $_.Name -notmatch '\.generated\.|\.err\.txt$' } | Sort-Object LastWriteTime)
$lastEvt = $null; if ($evt.Count -gt 0) { $lastEvt = $evt[-1] }
# 3c. r12 (17.11, замечание major проверки пакета позы): установки и откаты ПАКЕТОВ на дрон пишут журналы не сюда, а в out\ самих пакетов рядом с набором
# (папка проекта = папка над набором): drone_pkg_real_*, drone_pkg_posefix_*, drone_pkg_r2k_cam_* и любой другой drone_pkg_*. Событие = каждый *.log в <пакет>\out
# (и в out этого набора, если BB_KIT_OUT направил туда журналы пакетов: map_real_*, posefix_*, r2k_cam_*); его время = самое позднее LastWriteTime среди .log и файлов
# того же запуска (то же имя до .log: .txt, .err.txt, .host.txt ...). Успешная 09 должна быть ПОЗЖЕ последнего такого события. Папку пакета не прочитать - СТОП, а не «событий нет».
$pkgLast = $null
function PkgEvents([string]$dir, [string]$label, [string]$namePattern) {
    $files = @(Get-ChildItem -LiteralPath $dir -File -ErrorAction Stop)
    foreach ($lg in @($files | Where-Object { $_.Name -like '*.log' -and $_.Name -match $namePattern })) {
        $stem = $lg.Name.Substring(0, $lg.Name.Length - 4); $t = $lg.LastWriteTime
        foreach ($sib in @($files | Where-Object { $_.Name.StartsWith($stem + '.') })) { if ($sib.LastWriteTime -gt $t) { $t = $sib.LastWriteTime } }
        if ($null -eq $script:pkgLast -or $t -gt $script:pkgLast.Time) { $script:pkgLast = [pscustomobject]@{ Name = ($label + $lg.Name); Time = $t } }
    }
}
$projDir = Split-Path -Parent $here
try {
    foreach ($pd in @(Get-ChildItem -LiteralPath $projDir -Directory -Filter 'drone_pkg_*' -ErrorAction Stop | Where-Object { $_.Name -like 'drone_pkg_*' })) {
        $po = Join-Path $pd.FullName 'out'
        if (Test-Path -LiteralPath $po -PathType Container) { PkgEvents $po ($pd.Name + '\out\') '.' }
    }
    PkgEvents $outDir 'out\' '^(map_real_|posefix_|r2k_cam_)'
}
catch { No ('не удалось прочитать журналы пакетов drone_pkg_* в ' + $projDir + ' (' + $_.Exception.Message + '): нельзя проверить, что 09 сделана после установки пакета.') }
foreach ($kind in @(@('install_check', '09_sverka_install.cmd'), @('mavros_check', '10_mavros_versiya.cmd'))) {
    $chk = @(Get-ChildItem -LiteralPath $outDir -File -Filter ($kind[0] + '_*.txt') -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch '\.generated\.|\.err\.txt$|\.FAILED\.txt$' } | Sort-Object LastWriteTime)
    if ($chk.Count -eq 0) { No ('нет сверки ' + $kind[1] + ' (out\' + $kind[0] + '_*.txt): сделайте ее после последнего 16 или сборки.'); continue }
    $lastChk = $chk[-1]
    $vl = @([IO.File]::ReadAllLines($lastChk.FullName) | Where-Object { $_.Trim() -ne '' }); $lastLine = ''; if ($vl.Count -gt 0) { $lastLine = $vl[-1].Trim() }
    if ($lastLine -cne '# VERDICT OK') { No ('последняя сверка ' + $kind[1] + ' (' + $lastChk.Name + ') не успешна (нет «# VERDICT OK» последней строкой): на Pi исполняется не r2j или нет MAVROS bp02.'); continue }
    if (((Get-Date) - $lastChk.LastWriteTime).TotalMinutes -gt 180) { No ('последняя успешная сверка ' + $kind[1] + ' (' + $lastChk.Name + ') старше 180 минут: сделайте её заново.') }
    if ($lastEvt -and $lastChk.LastWriteTime -le $lastEvt.LastWriteTime) { No ('успешная сверка ' + $kind[1] + ' (' + $lastChk.Name + ') сделана ДО последнего подключения/отключения оверлея или сборки (' + $lastEvt.Name + '): сделайте ее заново.') }
    if ($kind[0] -eq 'install_check' -and $pkgLast -and $lastChk.LastWriteTime -le $pkgLast.Time) { No ('успешная сверка ' + $kind[1] + ' (' + $lastChk.Name + ', ' + $lastChk.LastWriteTime.ToString('dd.MM HH:mm:ss') + ') сделана ДО последней установки или отката пакета на дрон (' + $pkgLast.Name + ', ' + $pkgLast.Time.ToString('dd.MM HH:mm:ss') + '): сделайте 09 заново (r12, 3c).') }
}
if ($bad.Count -gt 0) {
    Write-Host ''
    Write-Host '  СТОП: взлёт не разрешён. К дрону не обращались. Не выполнены условия:  ' -ForegroundColor White -BackgroundColor Red
    foreach ($b in $bad) { Write-Host (' - ' + $b) }
    exit 4
}

# 4. дрон и скрипт на Pi
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$logFile = BB-NewOutFile $outDir ('takeoff_' + $stamp + '.log')
$ssh = BB-FindSsh
BB-TestDrone $ssh
$to = [IO.Path]::GetTempFileName(); $te = [IO.Path]::GetTempFileName()
try {
    $rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "sha256sum ' + $cfg['SCRIPT_REMOTE_PATH'] + '"') $to $te 30
    $o = Get-Content -LiteralPath $to -Raw -ErrorAction SilentlyContinue
    if ($rc -ne 0 -or $o -notmatch ('^' + $cfg['SCRIPT_SHA256'] + '\s')) { BB-Stop ('скрипт на Pi не найден или его sha256 не равен ожидаемому (код ' + $rc + '). Взлёт не начат. ' + $o) 4 }
}
finally { Remove-Item -LiteralPath $to, $te -ErrorAction SilentlyContinue }

# 4b (решение чата 1, 20:10): гейт drone.py. Скрипт полёта берёт drone.py из каталога своего sys.path.insert или из своей папки; все они должны быть РОВНО r2j (sha256 из takeoff.conf, DRONE_PY_SHA256). Только чтение. Иначе взлёт не начинается.
$genFg = BL-Generate (Join-Path $here 'pi\flight_gate.sh') @{ FGCFG = @(('SCRIPT=' + $cfg['SCRIPT_REMOTE_PATH']), ('WANT=' + $cfg['DRONE_PY_SHA256'])) } $outDir ('flight_gate_' + $stamp + '.generated.sh')
$fgo = [IO.Path]::GetTempFileName(); $fge = [IO.Path]::GetTempFileName()
try {
    $fgrc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + (BB-RemoteCommand $genFg @()) + '"') $fgo $fge 60
    $fgt = Get-Content -LiteralPath $fgo -Raw -ErrorAction SilentlyContinue
    if ($fgrc -ne 0 -or $fgt -notmatch 'BB_FG_DONE') { BB-Stop ('проверка drone.py на Pi не закончилась (код ' + $fgrc + '). Взлёт не начат. ' + $fgt) 4 }
    if ($fgt -notmatch '(?m)^BB_FG_RESULT OK\s*$') {
        $fgwhy = ([regex]::Match($fgt, '(?m)^BB_FG_RESULT (.*)$')).Groups[1].Value
        Write-Host ''; Write-Host '  СТОП: drone.py, который импортирует скрипт полёта, НЕ равен r2j. Взлёт не начат.  ' -ForegroundColor White -BackgroundColor Red
        foreach ($l in ($fgt -split "`r?`n")) { if ($l -match '^FG_') { Write-Host (' ' + $l) } }
        BB-Stop ('drone.py не r2j: ' + $fgwhy + '. Решает чат 1. Взлёт не начат.') 4
    }
}
finally { Remove-Item -LiteralPath $fgo, $fge -ErrorAction SilentlyContinue }
# 5. журнал и отсчёт
$hdr = @(("# takeoff " + (Get-Date).ToString("s")), ("# скрипт " + $cfg["SCRIPT_REMOTE_PATH"] + " sha256 " + $cfg["SCRIPT_SHA256"]), ("# аргументы: " + $cfg["SCRIPT_ARGS"]), ("# отсчёт " + $CountdownSec + " с"), ("# сверка настроек до: " + $rep.Name + " (" + $first + ")"), ("# разрешение: " + (Get-FileHash -LiteralPath $ap -Algorithm SHA256).Hash.ToLower()), ("# последнее событие пакета до 09 (r12, 3c): " + $(if ($pkgLast) { $pkgLast.Name + " " + $pkgLast.Time.ToString("s") } else { "нет" })))
[IO.File]::WriteAllLines($logFile, [string[]]$hdr, (BB-Utf8NoBom))
Write-Host ''
Write-Host '  ВЗЛЁТ: через несколько секунд на дроне запустится скрипт полёта и МОТОРЫ.  ' -ForegroundColor White -BackgroundColor Red
Write-Host '  Остановить: переключатель режима на пульте, CH8, Ctrl+C в этом окне. Палец на аварийном выключателе.  ' -ForegroundColor White -BackgroundColor Red
for ($i = $CountdownSec; $i -ge 1; $i--) { Write-Host ('  ' + $i + ' ...'); Start-Sleep -Seconds 1 }
Add-Content -LiteralPath $logFile -Value ((Get-Date).ToString('s') + ' запуск скрипта') -Encoding UTF8

# 6. запуск: ssh -tt, чтобы Ctrl+C дошёл до скрипта на Pi как SIGINT; вывод и на экран, и в журнал
$remoteLine = 'source /etc/profile.d/bumblebee-ros.sh 2>/dev/null; source /opt/ros/jazzy/setup.bash 2>/dev/null; cd /home/lb && python3 ' + $cfg['SCRIPT_REMOTE_PATH']
if ($cfg.ContainsKey('SCRIPT_ARGS') -and $cfg['SCRIPT_ARGS'] -ne '') { $remoteLine += ' ' + $cfg['SCRIPT_ARGS'] }
$argv = @('-tt', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3', $script:BB_DroneHost, $remoteLine)
$ErrorActionPreference = 'Continue'   # stderr ssh не должен обрывать скрипт
& $ssh.Source @argv 2>&1 | ForEach-Object { $line = [string]$_; Write-Host $line; Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8 }
$code = $LASTEXITCODE
Add-Content -LiteralPath $logFile -Value ((Get-Date).ToString('s') + ' скрипт завершился, код ssh ' + $code) -Encoding UTF8
Write-Host ''
Write-Host ('Журнал: ' + $logFile)
if ($code -eq 0) { exit 0 } else { exit 1 }
