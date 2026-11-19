# run_r6_camverify.ps1 (Claude, 12.11.2026, набор r6) - ТОЛЬКО ЧТЕНИЕ. Шаги 24a (-Mode cam) и 24b (-Mode r2j): «правка применилась?» после перезапуска стека.
# cam (после 05c и запуска службы): РАБОТАЮЩИЕ оба camera_fix исполняют файл с sha dabd5076 из префикса, который реально исполняется, и запущены ПОЗЖЕ последнего
#   изменения файла; launch в этом префиксе 5f0954d8; в журнале последнего запуска стека: full_rows=True у главной и False у второй, «full-row read: 384 ...»,
#   во всех строках stats главной «legacy frames 0» и всего полных кадров не меньше 600, нет «full-row read not possible», нет «process has died»,
#   camera_fix запускались ровно 2 раза (без перезапусков), нет ошибок camera_fix; служба active, NRestarts 0; журнал от текущего запуска (pid совпал).
# r2j (после отката 06c и запуска службы): оба camera_fix = 4a15d699, launch = 62be01db, в журнале нет full_rows и full-row, без смертей и перезапусков.
# Суммы берутся из image_r2j_cam\VARIANT_FILES.tsv (места install оверлея). Файл: out\cam_verify_<режим>_<время>.txt, последняя строка «# VERDICT OK/NOT_OK».
# Коды выхода: 0 применилась; 5 НЕ применилась или мало данных (смотреть причины); 4 ошибка связи, чужой ПК или дрон.
param([Parameter(Mandatory = $true)][ValidateSet('cam', 'r2j')][string]$Mode, [string]$Stamp = '')
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_lists.ps1')
. (Join-Path $here 'lib\bb_lists_r2jcam.ps1')
. (Join-Path $here 'lib\bb_r6.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
$vf = BLC-VarFiles $here
$camRow = @($vf | Where-Object { $_.StartsWith('bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix.py ') })
$lnRow = @($vf | Where-Object { $_.StartsWith('bench_ws/r2j/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py ') })
if ($camRow.Count -ne 1 -or $lnRow.Count -ne 1) { BB-Stop 'в VARIANT_FILES.tsv нет строк install оверлея для camera_fix.py и bumblebee.launch.py' 4 }
$idx = $(if ($Mode -eq 'cam') { 2 } else { 1 })
$wantCam = ($camRow[0] -split ' ')[$idx]; $wantLaunch = ($lnRow[0] -split ' ')[$idx]
if (-not $Stamp) { $Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss') } elseif ($Stamp -notmatch '^\d{8}_\d{6}$') { BB-Stop ('метка -Stamp не ГГГГММДД_ЧЧММСС: ' + $Stamp) 4 }   # -Stamp только для тестов; переменные PowerShell не различают регистр: $stamp = $Stamp
$sh = Join-Path $here 'pi\r6_cam_verify.sh'
$ssh = BB-FindSsh
foreach ($n in @(('cam_verify_' + $Mode + '_' + $Stamp + '.txt'), ('cam_verify_' + $Mode + '_' + $Stamp + '.err.txt'))) { $null = BB-NewOutFile $outDir $n }   # не перезаписывать: проверка ДО обращения к дрону
BB-TestDrone $ssh
Write-Host ('Проверяю, что работает ' + $(if ($Mode -eq 'cam') { 'камера полных строк (dabd5076)' } else { 'прежняя камера r2j (4a15d699)' }) + ' (только чтение) ...')
$r = R6-Remote $ssh $sh @($Mode) $outDir ('cam_verify_' + $Mode + '_' + $stamp) 90
if ($r.Code -ne 0 -or $r.Text -notmatch 'BB_R6CV_DONE') {
    $failed = $r.Out -replace '\.txt$', '.FAILED.txt'
    if (Test-Path -LiteralPath $r.Out) { Move-Item -LiteralPath $r.Out -Destination $failed }
    BB-Stop ('проверка не закончилась (код ssh ' + $r.Code + '). ' + $r.Err) 4
}
$t = $r.Text
$why = New-Object Collections.Generic.List[string]
function KV([string]$line, [string]$key) { $m = [regex]::Match($line, '(?:^| )' + [regex]::Escape($key) + '=(\S*)'); if ($m.Success) { return $m.Groups[1].Value } else { return $null } }
$svc = @(R6-Lines $t 'CV_SERVICE')
if ($svc.Count -ne 1 -or (KV $svc[0] 'active') -cne 'active') { $why.Add('служба bumblebee не active (' + ($svc -join ' ') + '): запустите её сами (sudo systemctl start bumblebee) и подождите 2 минуты') }
elseif ((KV $svc[0] 'nrestarts') -cne '0') { $why.Add('служба bumblebee перезапускалась сама (NRestarts=' + (KV $svc[0] 'nrestarts') + ')') }
$ln = @(R6-Lines $t 'CV_LAUNCH'); $lsha = ''; if ($ln.Count -eq 1) { $lsha = KV $ln[0] 'sha' }
if ($lsha -cne $wantLaunch) { $why.Add('launch-файл в исполняемом префиксе ' + $lsha + ', а ждали ' + $wantLaunch.Substring(0, 8) + '...') }
$procs = @(R6-Lines $t 'CV_PROC')
foreach ($node in 'main_camera_fix', 'second_camera_fix') {
    $p = @($procs | Where-Object { (KV $_ 'node') -ceq $node })
    if ($p.Count -ne 1) { $why.Add('процессов ' + $node + ': ' + $p.Count + ' (ждали ровно 1)'); continue }
    if ((KV $p[0] 'sha') -cne $wantCam) { $why.Add($node + ' исполняет файл с sha ' + (KV $p[0] 'sha') + ', а ждали ' + $wantCam.Substring(0, 8) + '... (правка не применилась)') }
    if ((KV $p[0] 'in_prefix') -cne 'yes') { $why.Add($node + ' запущен не из исполняемого префикса: ' + (KV $p[0] 'path')) }
    $se = KV $p[0] 'start_epoch'; $fc = KV $p[0] 'file_ctime'
    if ($se -notmatch '^\d+$' -or $fc -notmatch '^\d+$') { $why.Add($node + ': время запуска процесса или изменения файла не прочитано') }
    elseif ([long]$fc -gt [long]$se) { $why.Add($node + ': файл менялся ПОСЛЕ запуска процесса (процесс исполняет старый код): перезапустите стек') }
}
$cl = @(R6-Lines $t 'CV_LOG')
if ($cl.Count -ne 1 -or (KV $cl[0] 'access') -cne 'ok') { $why.Add('журнал /tmp/bumblebee.log прочитать нельзя: проверить нечем') }
elseif ((KV $cl[0] 'match') -cne 'yes') { $why.Add('журнал не от текущего запуска стека (pid ' + (KV $cl[0] 'launch_pid') + ' против MainPID ' + (KV $cl[0] 'mainpid') + ')') }
$sm = @(R6-Lines $t 'CV_START' | Where-Object { $_.StartsWith('main ') }); $ss = @(R6-Lines $t 'CV_START' | Where-Object { $_.StartsWith('second ') })
$fr = @(R6-Lines $t 'CV_FULLROW' | Where-Object { $_.StartsWith('main ') }); $fr2 = @(R6-Lines $t 'CV_FULLROW' | Where-Object { $_.StartsWith('second ') })
$stM = @(R6-Lines $t 'CV_STATS' | Where-Object { $_.StartsWith('main ') })
$died = @(R6-Lines $t 'CV_DIED'); $started = @(R6-Lines $t 'CV_CAMFIX_STARTED'); $errs = @(R6-Lines $t 'CV_ERRORS')
if ($sm.Count -ne 1 -or $ss.Count -ne 1 -or $fr.Count -ne 1 -or $fr2.Count -ne 1) { $why.Add('в ответе нет строк CV_START или CV_FULLROW') }
else {
    if ($Mode -eq 'cam') {
        if ((KV $sm[0] 'lines') -cne '1' -or (KV $sm[0] 'full_rows_true') -cne '1') { $why.Add('главная камера: строка запуска с full_rows=True не одна (' + $sm[0] + ')') }
        if ((KV $ss[0] 'lines') -cne '1' -or (KV $ss[0] 'full_rows_false') -cne '1') { $why.Add('вторая камера: строка запуска с full_rows=False не одна (' + $ss[0] + ')') }
        if ([int](KV $fr[0] 'read384') -lt 1) { $why.Add('нет строки «full-row read: 384 sensor rows at pitch 1600 -> 640x480» у главной') }
        if ((KV $fr[0] 'not_possible') -cne '0') { $why.Add('у главной есть «full-row read not possible» (' + (KV $fr[0] 'not_possible') + ')') }
        if ((KV $fr2[0] 'any') -cne '0') { $why.Add('вторая камера читает полные строки (должна быть False)') }
        if ($stM.Count -lt 1) { $why.Add('у главной ещё нет строки «camera_fix stats» (подождите 2 минуты после запуска службы и повторите)') }
        else {
            $sumFull = 0; $leg = 0
            foreach ($s in $stM) { $sumFull += [int](KV $s 'full'); if ((KV $s 'legacy') -cne '0') { $leg++ } }
            if ($leg -gt 0) { $why.Add('у главной в ' + $leg + ' строках stats legacy frames не 0') }
            if ($sumFull -lt 600) { $why.Add('у главной всего ' + $sumFull + ' полных кадров (нужно не меньше 600: подождите и повторите)') }
        }
    } else {
        if ((KV $sm[0] 'lines') -cne '1' -or (KV $sm[0] 'full_rows_true') -cne '0' -or (KV $sm[0] 'full_rows_false') -cne '0') { $why.Add('главная камера: строка запуска не прежняя (' + $sm[0] + ')') }
        if ((KV $ss[0] 'lines') -cne '1' -or (KV $ss[0] 'full_rows_true') -cne '0' -or (KV $ss[0] 'full_rows_false') -cne '0') { $why.Add('вторая камера: строка запуска не прежняя (' + $ss[0] + ')') }
        if ((KV $fr[0] 'any') -cne '0' -or (KV $fr2[0] 'any') -cne '0') { $why.Add('в журнале есть «full-row read» (работает не прежняя камера)') }
    }
}
if ($died.Count -ne 1 -or $died[0] -cne '0') { $why.Add('в журнале запуска «process has died»: ' + ($died -join ',')) }
if ($started.Count -ne 1 -or $started[0] -cne '2') { $why.Add('camera_fix запускались ' + ($started -join ',') + ' раз (ждали 2: перезапуски)') }
if ($errs.Count -ne 1 -or $errs[0] -cne '0') { $why.Add('строк ошибок camera_fix: ' + ($errs -join ',')) }
Write-Host ''
foreach ($l in ($t -split "`r?`n")) { if ($l -match '^(CV_SERVICE|CV_PREFIX|CV_LAUNCH|CV_PROC|CV_LOG|CV_START|CV_FULLROW|CV_STATS|CV_DIED|CV_CAMFIX_STARTED|CV_ERRORS|CV_BAD_LINE)') { Write-Host ('  ' + $l) } }
if ($why.Count -eq 0) {
    Add-Content -LiteralPath $r.Out -Value '# VERDICT OK' -Encoding UTF8
    Write-Host $(if ($Mode -eq 'cam') { 'ПРАВКА ПРИМЕНИЛАСЬ: работает камера полных строк (главная full_rows=True, вторая False), legacy frames 0, без перезапусков.' } else { 'ОТКАТ ПРИМЕНИЛСЯ: работает прежняя камера r2j, без перезапусков.' }) -ForegroundColor White -BackgroundColor DarkGreen
    Write-Host ('Файл: ' + $r.Out)
    exit 0
}
foreach ($w in $why) { Add-Content -LiteralPath $r.Out -Value ('# WHY ' + $w) -Encoding UTF8 }
Add-Content -LiteralPath $r.Out -Value '# VERDICT NOT_OK' -Encoding UTF8
Write-Host 'СТОП: правка НЕ подтверждена:' -ForegroundColor White -BackgroundColor Red
foreach ($w in $why) { Write-Host (' - ' + $w) }
Write-Host '  Ничего не чинить самому. Скажите Claude: решает чат 1 (откат - 06c после его разрешения).'
Write-Host ('Файл: ' + $r.Out)
exit 5
