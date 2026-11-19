# run_r6_cost.ps1 (Claude, 12.11.2026, набор r6) - МЕНЯЕТ ДРОН: ВРЕМЕННО. ЗАГОТОВКА: Claude её не запускает; двойной щелчок владельца по 22_kamera_cena_A_C_A2.cmd.
# Цена камеры полных строк БЕЗ установки: фазы A -> C -> A2 процедуры PI_PERF (pi\r6_cost_phase.sh), потом проверка «стек как был» (pi\r6_cost_end.sh).
# Временные процессы на Pi (кандидат camera_fix в фазе C, стендовый детектор через ~/opencv47_venv/bin/python3, запись) - каждый под timeout, не дольше 4 минут;
# их выходы - НОВЫЕ темы (/main_camera/image_raw_full, /bench/...) и НОВЫЕ файлы в ~/bench_ws/camera_fullrow_r6/<время>/cost. Стек, его файлы, службы и PX4 не меняются.
# Условия до обращения к дрону: gates\CAM_COST_APPROVED.txt (ПРАВКА=22_kamera_cena; одно разрешение = один замер, создавший файлы на Pi);
#   успешный К-1 (out\k1_raw_layout_*.txt, последний, «# VERDICT OK», не старше 180 минут); числа рулетки (PI_PERF К-8: без них замер не судится).
# Пороги К-2…К-8 здесь НЕ применяются (их решает владелец): файл только записывает числа. Claude разбирает out\camera_cost_<время>_*.
# Коды выхода: 0 три фазы и проверка «стек как был» прошли (числа записаны); 5 фаза или проверка не прошли (смотреть файлы); 4 условия, связь, чужой ПК или дрон.
# Числа рулетки и ответ про приложение 22_kamera_cena_A_C_A2.cmd передаёт через переменные окружения BB_RULER_X, BB_RULER_Y, BB_RULER_H, BB_DASHBOARD
# (не в командной строке: так введённый текст не разбирается cmd.exe как команда).
param(
    [Parameter(Mandatory = $true)][string]$Confirmed,
    [string]$RulerX = $env:BB_RULER_X,
    [string]$RulerY = $env:BB_RULER_Y,
    [string]$RulerH = $env:BB_RULER_H,
    [string]$Dashboard = $env:BB_DASHBOARD,
    [string]$Stamp = ''
)
$ErrorActionPreference = 'Stop'
if ($null -eq $RulerX) { $RulerX = '' }; if ($null -eq $RulerY) { $RulerY = '' }; if ($null -eq $RulerH) { $RulerH = '' }; if ($null -eq $Dashboard) { $Dashboard = '' }
$RulerX = $RulerX.Trim(); $RulerY = $RulerY.Trim(); $RulerH = $RulerH.Trim(); $Dashboard = $Dashboard.Trim()
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_lists.ps1')
. (Join-Path $here 'lib\bb_r6.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
if ($Confirmed -cne 'COST-TEMP') { BB-Stop 'нет подтверждения в окне. Запускайте только через 22_kamera_cena_A_C_A2.cmd.' 4 }
foreach ($v in @(@('X', $RulerX), @('Y', $RulerY), @('высота', $RulerH))) { if ($v[1] -notmatch '^-?\d{1,3}([.,]\d)?$') { BB-Stop ('рулетка ' + $v[0] + ': нужно число сантиметров (например 12 или -3,5), а введено «' + $v[1] + '». К дрону не обращались.') 4 } }
if ($RulerH -match '^-' -or [double]($RulerH -replace ',', '.') -lt 10) { BB-Stop ('высота объектива над меткой ' + $RulerH + ' см: нужна положительная, не меньше 10 см. К дрону не обращались.') 4 }
if ($Dashboard -notmatch '^(?i)(Y|N)$') { BB-Stop 'про приложение нужно Y или N. К дрону не обращались.' 4 }
$perm = R6-Permission (Join-Path (Join-Path $here 'gates') 'CAM_COST_APPROVED.txt') '22_kamera_cena'
if (-not $perm.Ok) { BB-Stop ($perm.Why + '. К дрону не обращались.') 4 }
if (R6-PermissionUsed $outDir 'camera_cost_' $perm.Sha 'COST_START ') { BB-Stop 'разрешение CAM_COST_APPROVED.txt уже использовано (по нему замер уже шёл). Нужно новое «да» владельца и новый файл от чата 1. К дрону не обращались.' 4 }
$k1 = R6-Latest $outDir 'k1_raw_layout_*.txt'
if (-not $k1) { BB-Stop 'нет результата К-1 (out\k1_raw_layout_*.txt): сначала 21_kamera_K1_raskladka.cmd. К дрону не обращались.' 4 }
if ((R6-LastLine $k1.FullName) -cne '# VERDICT OK') { BB-Stop ('последний К-1 (' + $k1.Name + ') не ГОТОВО: цену не мерим (PI_PERF: без К1 ГОТОВО дальше не идти). К дрону не обращались.') 4 }
if (((Get-Date) - $k1.LastWriteTime).TotalMinutes -gt 180) { BB-Stop ('К-1 (' + $k1.Name + ') старше 180 минут: повторите 21 (новое разрешение). К дрону не обращались.') 4 }
$files = R6-CamFiles $here
if (-not $Stamp) { $Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss') } elseif ($Stamp -notmatch '^\d{8}_\d{6}$') { BB-Stop ('метка -Stamp не ГГГГММДД_ЧЧММСС: ' + $Stamp) 4 }   # -Stamp только для тестов; переменные PowerShell не различают регистр: $stamp = $Stamp
$dl = Join-Path $outDir ('camera_cost_' + $stamp)
if (Test-Path -LiteralPath $dl) { BB-Stop ('папка ' + $dl + ' уже есть, не перезаписываю') 4 }
$proto = BB-NewOutFile $outDir ('camera_cost_' + $stamp + '_protocol.txt')
[IO.File]::WriteAllText($proto, ("# протокол замера цены камеры (PI_PERF), " + (R6-Now) + "`r`nРУЛЕТКА_X_СМ=" + $RulerX + "`r`nРУЛЕТКА_Y_СМ=" + $RulerY + "`r`nРУЛЕТКА_ВЫСОТА_СМ=" + $RulerH + "`r`nПРИЛОЖЕНИЕ_ОТКРЫТО=" + $Dashboard.ToUpper() + "`r`nК1=" + $k1.Name + "`r`nPERMISSION_SHA256=" + $perm.Sha + "`r`n"), (BB-Utf8NoBom))
$genCi = BL-Generate (Join-Path $here 'pi\r6_cam_incoming.sh') @{ CAMFILES = $files } $outDir ('cam_incoming_' + $stamp + '.generated.sh')
$ssh = BB-FindSsh
foreach ($n in @(('cam_incoming_' + $Stamp + '.txt'), ('camera_cost_' + $Stamp + '_A.txt'), ('camera_cost_' + $Stamp + '_C.txt'), ('camera_cost_' + $Stamp + '_A2.txt'), ('camera_cost_' + $Stamp + '_end.txt'), ('camera_cost_' + $Stamp + '_summary.txt'))) { $null = BB-NewOutFile $outDir $n }   # не перезаписывать: проверка ДО обращения к дрону
BB-TestDrone $ssh
$ci = R6-Remote $ssh $genCi @() $outDir ('cam_incoming_' + $stamp) 60
if ($ci.Code -ne 0 -or $ci.Text -notmatch 'BB_R6CI_DONE') { BB-Stop ('проверка файлов замера на Pi не закончилась (код ' + $ci.Code + '). ' + $ci.Err) 4 }
$cs = (@(R6-Lines $ci.Text 'CI_STATE') -join '')
if ($cs -cne 'ok') { BB-Stop ('на Pi нет верных файлов замера (CI_STATE ' + $cs + '): сначала 21_kamera_K1_raskladka.cmd (он их кладёт). Ничего не запускалось.') 4 }
$phaseOk = @{}; $summ = @{}; $anyStarted = $false
foreach ($ph in 'A', 'C', 'A2') {
    Write-Host ''
    Write-Host ('Фаза ' + $ph + ': около 3 минут (30 с прогрев, 120 с запись). Дрон не трогать, свет не менять.') -ForegroundColor White -BackgroundColor DarkBlue
    $r = R6-Remote $ssh (Join-Path $here 'pi\r6_cost_phase.sh') @($stamp, $ph) $outDir ('camera_cost_' + $stamp + '_' + $ph) 330
    Add-Content -LiteralPath $r.Out -Value ('PERMISSION_SHA256=' + $perm.Sha) -Encoding UTF8
    foreach ($l in ($r.Text -split "`r?`n")) { if ($l -match '^(COST_START|COST_END|COST_RECORDER_RC|COST_CAMFIX_FULL|COST_LEFT|ФАЗА )') { Write-Host ('  ' + $l) } }
    if ($r.Text -match '(?m)^COST_START ') { $anyStarted = $true }
    $phaseOk[$ph] = ($r.Code -eq 0 -and $r.Text -match ('(?m)^ФАЗА ' + $ph + ' ГОТОВО: '))
    $js = @(R6-Lines $r.Text 'COST_SUMMARY_JSON')
    if ($js.Count -eq 1) { try { $summ[$ph] = $js[0] | ConvertFrom-Json } catch { } }
    if (-not $phaseOk[$ph]) { Write-Host ('  Фаза ' + $ph + ' НЕ ГОТОВО (код ' + $r.Code + '). Следующие фазы не начинаю.') -ForegroundColor White -BackgroundColor Red; break }
}
Write-Host ''
Write-Host 'Конец замера: проверяю, что стек как был (только чтение) ...'
$e = R6-Remote $ssh (Join-Path $here 'pi\r6_cost_end.sh') @($stamp) $outDir ('camera_cost_' + $stamp + '_end') 60
$endOk = ($e.Code -eq 0 -and $e.Text -match 'КАМЕРА: ЗАМЕР ЗАКОНЧЕН, СТЕК КАК БЫЛ — ГОТОВО')
foreach ($l in ($e.Text -split "`r?`n")) { if ($l -match '^(END_|КАМЕРА|КОНЕЦ)') { Write-Host ('  ' + $l) } }
if ($anyStarted) {
    New-Item -ItemType Directory -Path $dl | Out-Null
    $scp = Get-Command scp -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($scp) {
        $so = BB-NewOutFile $outDir ('camera_cost_' + $stamp + '_scp.txt'); $se = BB-NewOutFile $outDir ('camera_cost_' + $stamp + '_scp.err.txt')
        $rc = BB-RunSsh $scp ('-r -o BatchMode=yes -o ConnectTimeout=15 ' + $script:BB_DroneHost + ':/home/lb/bench_ws/camera_fullrow_r6/' + $stamp + '/cost "' + $dl + '"') $so $se 180
        if ($rc -ne 0) { Write-Host ('  Копия папки замера на ПК не удалась (код ' + $rc + '); на Pi она в ~/bench_ws/camera_fullrow_r6/' + $stamp + '/cost. Числа выше есть в файлах out\camera_cost_' + $stamp + '_*.txt.') -ForegroundColor Black -BackgroundColor Yellow }
    }
}
# Числа для Claude (без порогов): частоты, задержки, простой, CPU, температура
$sumFile = BB-NewOutFile $outDir ('camera_cost_' + $stamp + '_summary.txt')
$sl = New-Object Collections.Generic.List[string]
$sl.Add('# цена камеры полных строк, ' + (R6-Now) + '; пороги К-2…К-8 не применяются (решает владелец); протокол: ' + (Split-Path $proto -Leaf))
foreach ($ph in 'A', 'C', 'A2') {
    if (-not $summ.ContainsKey($ph)) { $sl.Add($ph + ': нет summary.json'); continue }
    $s = $summ[$ph]
    $mk = $s.topics.markers; $po = $s.topics.pose; $im = $s.topics.image
    $pr = $s.processes
    $sl.Add(('{0}: idle_all_cores={1}% markers_hz={2} pose_hz={3} image_hz={4} pose_lat_p50={5} p95={6} markers_lat_p50={7} p95={8} camfix_cpu={9} camfix_full_cpu={10} aruco_bench_cpu={11} temp_max={12} throttled_end={13}' -f $ph, $s.idle_pct_of_all_cores, $mk.hz, $po.hz, $im.hz, $po.latency_ms_p50, $po.latency_ms_p95, $mk.latency_ms_p50, $mk.latency_ms_p95, $pr.camfix.cpu_pct_of_one_core, $pr.camfix_full.cpu_pct_of_one_core, $pr.aruco_bench.cpu_pct_of_one_core, $s.temp_c_max, $s.throttled_end))
}
if ($summ.ContainsKey('A') -and $summ.ContainsKey('A2')) {
    $a = [double]$summ['A'].topics.markers.hz; $a2 = [double]$summ['A2'].topics.markers.hz
    if ($a -gt 0 -and $a2 -gt 0) { $sl.Add(('A и A2 по частоте markers расходятся на {0:N1} % (в PI_PERF больше 10 % = замер не судится; это предложение, решает владелец)' -f (100.0 * [Math]::Abs($a - $a2) / [Math]::Max($a, $a2)))) }
}
$sl.Add('# PHASES ' + (($phaseOk.Keys | Sort-Object | ForEach-Object { $_ + '=' + $phaseOk[$_] }) -join ' ') + ' END=' + $endOk)
$all3 = ($phaseOk['A'] -and $phaseOk['C'] -and $phaseOk['A2'])
$sl.Add('# VERDICT ' + $(if ($all3 -and $endOk) { 'MEASURED' } else { 'NOT_DONE' }))
[IO.File]::WriteAllText($sumFile, (($sl -join "`r`n") + "`r`n"), (BB-Utf8NoBom))
Write-Host ''
foreach ($l in $sl) { Write-Host $l }
if ($all3 -and $endOk) { Write-Host ('Готово: три фазы записаны, стек как был. Скажите Claude. Файлы: out\camera_cost_' + $stamp + '_*') -ForegroundColor White -BackgroundColor DarkGreen; exit 0 }
Write-Host ('  СТОП: замер не закончен как надо (фаза или проверка «стек как был» не прошли). Ничего не чинить, скажите Claude. Файлы: out\camera_cost_' + $stamp + '_*') -ForegroundColor White -BackgroundColor Red
exit 5
