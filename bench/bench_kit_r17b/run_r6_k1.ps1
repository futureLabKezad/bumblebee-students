# run_r6_k1.ps1 (Claude, 12.11.2026, набор r6) - МЕНЯЕТ ДРОН: ТОЛЬКО НОВЫЕ ФАЙЛЫ. ЗАГОТОВКА: Claude её не запускает; двойной щелчок владельца по 21_kamera_K1_raskladka.cmd.
# К-1 процедуры PI_PERF: раскладка кадра главной камеры (5 сырых кадров /main_camera/image_raw_yuv: step 1280, 614400 байт, нули при шаге 1600), pi\r6_k1.sh.
# На Pi появляются только НОВЫЕ папки: ~/bench_ws/incoming/camera_fullrow_r6 (3 файла замера и их SHA256SUMS; если папка уже есть и суммы верны - не копируется заново,
# если суммы не те - СТОП, ничего не перезаписывается) и ~/bench_ws/camera_fullrow_r6/<время>/K1 (кадр 0, картинки, meta.json). Стек, службы и PX4 не трогаются.
# Условия: gates\CAM_K1_APPROVED.txt (ПРАВКА=21_kamera_K1; создаёт только чат 1 после слов владельца; одно разрешение = один запуск, создавший файлы на Pi).
# На ПК: out\k1_raw_layout_<время>.txt (вывод, последняя строка «# VERDICT OK» если «RAW CHECK ГОТОВО»), out\k1_<время>\K1\ (копия папки с Pi).
# Коды выхода: 0 К-1 ГОТОВО; 5 К-1 НЕ ГОТОВО (раскладка не та или кадров нет: дальше 22 не делать); 4 условия, связь, чужой ПК или дрон.
param([Parameter(Mandatory = $true)][string]$Confirmed, [string]$Stamp = '')
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_lists.ps1')
. (Join-Path $here 'lib\bb_r6.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
if ($Confirmed -cne 'K1-NEWFILES') { BB-Stop 'нет подтверждения в окне. Запускайте только через 21_kamera_K1_raskladka.cmd.' 4 }
$perm = R6-Permission (Join-Path (Join-Path $here 'gates') 'CAM_K1_APPROVED.txt') '21_kamera_K1'
if (-not $perm.Ok) { BB-Stop ($perm.Why + '. К дрону не обращались.') 4 }
if (R6-PermissionUsed $outDir 'k1_raw_layout_' $perm.Sha 'K1_DIR ') { BB-Stop 'разрешение CAM_K1_APPROVED.txt уже использовано (по нему на Pi уже создавались файлы К-1). Нужно новое «да» владельца и новый файл от чата 1. К дрону не обращались.' 4 }
$files = R6-CamFiles $here
if (-not $Stamp) { $Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss') } elseif ($Stamp -notmatch '^\d{8}_\d{6}$') { BB-Stop ('метка -Stamp не ГГГГММДД_ЧЧММСС: ' + $Stamp) 4 }   # -Stamp только для тестов; переменные PowerShell не различают регистр: $stamp = $Stamp
$dl = Join-Path $outDir ('k1_' + $stamp)
if (Test-Path -LiteralPath $dl) { BB-Stop ('папка ' + $dl + ' уже есть, не перезаписываю') 4 }
$genCi = BL-Generate (Join-Path $here 'pi\r6_cam_incoming.sh') @{ CAMFILES = $files } $outDir ('cam_incoming_' + $stamp + '.generated.sh')
$ssh = BB-FindSsh
foreach ($n in @(('cam_incoming_' + $Stamp + '.txt'), ('k1_raw_layout_' + $Stamp + '.txt'), ('k1_raw_layout_' + $Stamp + '.err.txt'))) { $null = BB-NewOutFile $outDir $n }   # не перезаписывать: проверка ДО обращения к дрону
BB-TestDrone $ssh
$ci = R6-Remote $ssh $genCi @() $outDir ('cam_incoming_' + $stamp) 60
if ($ci.Code -ne 0 -or $ci.Text -notmatch 'BB_R6CI_DONE') { BB-Stop ('проверка папки файлов замера на Pi не закончилась (код ' + $ci.Code + '). ' + $ci.Err) 4 }
$state = @(R6-Lines $ci.Text 'CI_STATE')
if ($state.Count -ne 1) { BB-Stop 'нет строки CI_STATE' 4 }
if ($state[0] -cne 'absent' -and $state[0] -cne 'ok') { BB-Stop ('на Pi папка ~/bench_ws/incoming/camera_fullrow_r6 есть, но файлы не те (CI_STATE ' + $state[0] + '; ' + ((R6-Lines $ci.Text 'CI_FILE') -join '; ') + '). Ничего не перезаписываю: скажите Claude.') 4 }
$scp = Get-Command scp -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $scp) { BB-Stop 'scp не найден на этом ПК' 4 }
if ($state[0] -ceq 'absent') {
    Write-Host 'Копирую 3 файла замера и SHA256SUMS в НОВУЮ папку ~/bench_ws/incoming/camera_fullrow_r6 ...'
    $mk = R6-Remote $ssh (Join-Path $here 'pi\r6_cam_mkdir.sh') @() $outDir ('cam_mkdir_' + $stamp) 30
    if ($mk.Code -ne 0 -or $mk.Text -notmatch 'MKDIR_OK') { BB-Stop ('папка на Pi не создана (уже есть или нет прав): ' + $mk.Text + ' ' + $mk.Err + '. Ничего не скопировано.') 4 }
    $src = @('camera_fix.py', 'bench_recorder.py', 'raw_layout_check.py', 'SHA256SUMS_camera_fullrow.txt' | ForEach-Object { '"' + (Join-Path (Join-Path $here 'camera_fullrow') $_) + '"' })
    $so = BB-NewOutFile $outDir ('cam_scp_' + $stamp + '.txt'); $se = BB-NewOutFile $outDir ('cam_scp_' + $stamp + '.err.txt')
    $rc = BB-RunSsh $scp ('-o BatchMode=yes -o ConnectTimeout=15 ' + ($src -join ' ') + ' ' + $script:BB_DroneHost + ':/home/lb/bench_ws/incoming/camera_fullrow_r6/') $so $se 120
    if ($rc -ne 0) { BB-Stop ('копирование на Pi не удалось (код ' + $rc + '). ' + (Get-Content -LiteralPath $se -Raw -ErrorAction SilentlyContinue)) 4 }
    $ci2 = R6-Remote $ssh $genCi @() $outDir ('cam_incoming_after_' + $stamp) 60
    $st2 = (@(R6-Lines $ci2.Text 'CI_STATE') -join '')
    if ($ci2.Code -ne 0 -or $st2 -cne 'ok') { BB-Stop ('после копирования суммы на Pi не сходятся: ' + ((R6-Lines $ci2.Text 'CI_FILE') -join '; ') + '. Дальше не иду, скажите Claude.') 4 }
} else { Write-Host 'Файлы замера уже на Pi, суммы верны: не копирую.' }
Write-Host 'К-1: 5 сырых кадров главной камеры (только подписка, до 1 минуты) ...'
$r = R6-Remote $ssh (Join-Path $here 'pi\r6_k1.sh') @($stamp) $outDir ('k1_raw_layout_' + $stamp) 150
Add-Content -LiteralPath $r.Out -Value ('PERMISSION_SHA256=' + $perm.Sha) -Encoding UTF8
if ($r.Code -ne 0 -or $r.Text -notmatch 'BB_R6K1_DONE') {
    Add-Content -LiteralPath $r.Out -Value '# VERDICT NOT_OK' -Encoding UTF8
    BB-Stop ('К-1 не закончился (код ssh ' + $r.Code + '). ' + $r.Err + ' Файл: ' + $r.Out) 4
}
foreach ($l in ($r.Text -split "`r?`n")) { if ($l -match '^(K1_DIR|K1_THROTTLED_START|K1_TEMP_START|K1_PY_RC|K1_FRAME0|К1 |K1_OUT RAW CHECK|K1_OUT СТОП)') { Write-Host $l } }
$okK1 = ($r.Text -match '(?m)^К1 ГОТОВО ')
if ($r.Text -match '(?m)^K1_DIR ') {
    New-Item -ItemType Directory -Path $dl | Out-Null
    $so = BB-NewOutFile $outDir ('k1_scp_' + $stamp + '.txt'); $se = BB-NewOutFile $outDir ('k1_scp_' + $stamp + '.err.txt')
    $rc = BB-RunSsh $scp ('-r -o BatchMode=yes -o ConnectTimeout=15 ' + $script:BB_DroneHost + ':/home/lb/bench_ws/camera_fullrow_r6/' + $stamp + '/K1 "' + $dl + '"') $so $se 120
    if ($rc -ne 0) { Write-Host ('  Копия папки К-1 на ПК не удалась (код ' + $rc + '); на Pi она лежит в ~/bench_ws/camera_fullrow_r6/' + $stamp + '/K1. Скажите Claude.') -ForegroundColor Black -BackgroundColor Yellow }
}
if ($okK1) {
    Add-Content -LiteralPath $r.Out -Value '# VERDICT OK' -Encoding UTF8
    Write-Host 'К-1 ГОТОВО: раскладка кадра та, что ждали (step 1280, 614400 байт, нули при шаге 1600, 5 из 5).' -ForegroundColor White -BackgroundColor DarkGreen
    Write-Host ('Файл: ' + $r.Out + '; копия папки: ' + $dl)
    exit 0
}
Add-Content -LiteralPath $r.Out -Value '# VERDICT NOT_OK' -Encoding UTF8
Write-Host 'К-1 НЕ ГОТОВО: раскладка не та или кадров нет. Дальше 22 (цена) НЕ делать. Скажите Claude.' -ForegroundColor White -BackgroundColor Red
Write-Host ('Файл: ' + $r.Out)
exit 5
