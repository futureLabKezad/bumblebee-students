# run_r6_cam_install.ps1 (Claude, 12.11.2026, набор r6) - МЕНЯЕТ ДРОН. ЗАГОТОВКА: Claude её не запускает; двойной щелчок владельца по 05c_install_r2j_cam.cmd (-Mode install)
# или 06c_otkat_r2j_cam.cmd (-Mode rollback).
# install: ставит вариант «r2j + камера полных строк»: camera_fix.py dabd5076 и bumblebee.launch.py с full_rows (главная True, вторая False) и в src (~/ros2_ws/src, для будущих сборок),
#          и в install оверлея r2j (~/bench_ws/r2j/install/..., то, что реально исполняется; launch в install/share). Установщик - прежний ..\image_r2j\image_install.sh
#          (резерв старых файлов - в СВОЕЙ папке BACKUP_ROOT/r2j_cam/<метка>, проверка sha256 и режима на месте). До установки на Pi проверка только чтением (pi\r6_cam_precheck.sh install):
#          служба остановлена, оверлей r2j подключён и исполняется, 4 файла сейчас ровно r2j. После установки: 4 файла = вариант («файлы легли»);
#          что стек их ИСПОЛНЯЕТ, проверяет 24a после запуска службы владельцем.
# rollback: возвращает 4 файла r2j (4a15d699, 62be01db) из резерва ИМЕННО этой установки (в BACKUP_ROOT/r2j_cam, ищется по sha256 её манифеста) прежним
#          ..\image_r2j\image_rollback.sh с явной меткой; до отката: служба остановлена, 4 файла = вариант; после: 4 файла = r2j. Потом 24b.
# Своя папка резерва (правка 2 независимой проверки RV, 12.11): image_install.sh и image_rollback.sh получают не общий ..\image_r2j\image_target.conf, а его
#          копию out\cam_target_<режим>_<время>\image_target.conf с BACKUP_ROOT=<BACKUP_ROOT>/r2j_cam (DEST_ROOT тот же). Причина: 06_rollback_r2j.cmd r5 без метки
#          берёт самый новый резерв прямо в BACKUP_ROOT (image_rollback.sh стр. 27, только имена ГГГГММДД_ЧЧММСС); если бы резерв варианта лежал там же, 06 после 05c
#          откатил бы 4 файла варианта вместо образа r2j и написал «Готово». Подпапку r2j_cam он не видит. Та же папка - в BROOT для pi\r6_cam_precheck.sh.
# Журналы: out\install_r2j_cam_<R>.log и out\rollback_r2j_cam_<R>.log - их видит 07 как события (имена начинаются с install_r2j_ и rollback_r2j_):
# любая установка или откат варианта обесценивает прежние 09 и 10.
# Коды выхода: 0 готово; 1 условия не выполнены или не дошло до конца (причины выше).
param(
    [Parameter(Mandatory = $true)][ValidateSet('install', 'rollback')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$Confirmed
)
$ErrorActionPreference = 'Stop'
$ik = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $ik
. (Join-Path $root 'lib\bb_common.ps1')
. (Join-Path $root 'lib\bb_lists.ps1')
. (Join-Path $root 'lib\bb_lists_r2jcam.ps1')
. (Join-Path $root 'lib\bb_r6.ps1')
function Fail([string]$msg) { Write-Host ''; Write-Host ('  СТОП: ' + $msg + '  ') -ForegroundColor White -BackgroundColor DarkRed; exit 1 }
if ($env:COMPUTERNAME -ne $script:BB_ExpectPc) { Fail ('это не тот компьютер (' + $env:COMPUTERNAME + '), нужен ' + $script:BB_ExpectPc + '. Ничего не сделано.') }
if ($Confirmed -cne ('SERVICE-YES-' + $Mode)) { Fail 'нет подтверждений в окне. Запускайте только через 05c_install_r2j_cam.cmd или 06c_otkat_r2j_cam.cmd.' }
$outDir = BB-OutDir $root
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ik 'check_gates_r2j_cam.ps1') -Kit $ik -OutDir $outDir -Mode $Mode
if ($LASTEXITCODE -ne 0) { Fail 'условия не выполнены (причины выше). К дрону не обращались, ничего не изменено.' }
$gateName = $(if ($Mode -eq 'install') { 'R2J_CAM_APPROVED.txt' } else { 'OTKAT_R2J_CAM_APPROVED.txt' })
$permSha = R6-Sha (Join-Path $ik ('gates\' + $gateName))
$logPrefix = $(if ($Mode -eq 'install') { 'install_r2j_cam_' } else { 'rollback_r2j_cam_' })
$okMarker = $(if ($Mode -eq 'install') { 'BB_IMAGE_INSTALL_DONE' } else { 'BB_IMAGE_ROLLBACK_DONE' })
if (R6-PermissionUsed $outDir $logPrefix $permSha $okMarker) { Fail ('разрешение ' + $gateName + ' уже использовано успешным запуском (out\' + $logPrefix + '*). Нужно новое «да» владельца и новый файл от чата 1. К дрону не обращались.') }
$conf = Join-Path $root 'image_r2j\image_target.conf'
$broot = ((Get-Content -LiteralPath $conf -Encoding UTF8 | Where-Object { $_ -match '^BACKUP_ROOT=' } | Select-Object -First 1) -replace '^BACKUP_ROOT=', '').Trim()
$droot = ((Get-Content -LiteralPath $conf -Encoding UTF8 | Where-Object { $_ -match '^DEST_ROOT=' } | Select-Object -First 1) -replace '^DEST_ROOT=', '').Trim()
# sha256 манифеста в том виде, в каком его кладёт в резерв image_install.sh (без \r, без BOM, с переводом строки в конце)
$mb = [IO.File]::ReadAllBytes((Join-Path $ik 'image_manifest.final.tsv'))
$ms = (New-Object Text.UTF8Encoding($false)).GetString($mb).TrimStart([char]0xFEFF) -replace "`r", ''
if (-not $ms.EndsWith("`n")) { $ms += "`n" }
$manClean = R6-TextSha $ms
$vf = BLC-VarFiles $root
if ($broot -notmatch '^/[A-Za-z0-9_./-]+$' -or $broot -match '\.\.') { Fail ('BACKUP_ROOT не абсолютный путь из безопасных знаков: ' + $broot) }
if ($droot -cne '/home/lb') { Fail ('DEST_ROOT не /home/lb: ' + $droot) }
# своя копия image_target.conf: резерв варианта - в BACKUP_ROOT/r2j_cam (06 r5 его не видит); папка новая, ничего не перезаписывается, до обращения к дрону
$bcam = $broot.TrimEnd('/') + '/r2j_cam'
$camConfDir = Join-Path $outDir ('cam_target_' + $Mode + '_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
if (Test-Path -LiteralPath $camConfDir) { Fail ('папка уже есть, не перезаписываю: ' + $camConfDir + '. К дрону не обращались.') }
New-Item -ItemType Directory -Path $camConfDir | Out-Null
$camConf = Join-Path $camConfDir 'image_target.conf'
[IO.File]::WriteAllText($camConf, ('# image_target.conf варианта r2j_cam: копия ../image_r2j/image_target.conf, резерв варианта отдельно (run_r6_cam_install.ps1, ' + (R6-Now) + ')' + "`n" + 'DEST_ROOT=' + $droot + "`n" + 'BACKUP_ROOT=' + $bcam + "`n"), (BB-Utf8NoBom))
$camConfSha = R6-Sha $camConf
Write-Host ('Резерв варианта: ' + $bcam + ' (отдельно от резерва образа r2j; 06_rollback_r2j.cmd его не видит)')
$cpArgs = New-Object Collections.Generic.List[string]; $cpArgs.Add('BROOT=' + $bcam); $cpArgs.Add('MSHA=' + $manClean)
$genPre = BL-Generate (Join-Path $root 'pi\r6_cam_precheck.sh') @{ CAMVAR = $vf; CPARGS = $cpArgs } $outDir ('cam_precheck_' + $Mode + '_' + (Get-Date).ToString('yyyyMMdd_HHmmss') + '.generated.sh')
$ssh = BB-FindSsh
$scp = Get-Command scp -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $scp) { Fail 'scp не найден на этом ПК' }
BB-TestDrone $ssh
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$pre = R6-Remote $ssh $genPre @($Mode) $outDir ('cam_precheck_' + $Mode + '_' + $stamp) 90
foreach ($l in ($pre.Text -split "`r?`n")) { if ($l -match '^CP_') { Write-Host $l } }
if ($pre.Code -ne 0 -or $pre.Text -notmatch 'BB_R6CP_DONE' -or $pre.Text -notmatch '(?m)^CP_RESULT OK\s*$') { Fail ('проверка на Pi до ' + $(if ($Mode -eq 'install') { 'установки' } else { 'отката' }) + ' не прошла (строка CP_RESULT выше). На дроне ничего не изменено.') }
$label = ''
if ($Mode -eq 'rollback') {
    $cand = @(R6-Lines $pre.Text 'CP_BACKUP' | Where-Object { $_ -match ' match=1 rolled_back=0 complete=1$' } | ForEach-Object { ($_ -split ' ')[0] } | Sort-Object)
    if ($cand.Count -eq 0) { Fail ('на Pi нет полной неоткаченной резервной копии установки варианта (по sha256 её манифеста ' + $manClean.Substring(0, 12) + '...). Ничего не изменено, скажите Claude.') }
    $label = $cand[-1]
    if ($label -notmatch '^\d{8}_\d{6}$') { Fail ('метка резерва не ГГГГММДД_ЧЧММСС: ' + $label) }
    Write-Host ('Резерв установки варианта: ' + $label)
}
$R = [string](Get-Random -Minimum 100000 -Maximum 999999) + [string](Get-Random -Minimum 100000 -Maximum 999999)
$log = BB-NewOutFile $outDir ($logPrefix + $R + '.log')
[IO.File]::WriteAllText($log, ((R6-Now) + ' ' + $logPrefix.TrimEnd('_') + ', подтверждено в окне (SERVICE, YES)' + "`r`nPERMISSION_SHA256=" + $permSha + "`r`nMANIFEST_CLEAN_SHA256=" + $manClean + "`r`nBACKUP_ROOT_VARIANT=" + $bcam + "`r`nTARGET_CONF=" + $camConf + "`r`nTARGET_CONF_SHA256=" + $camConfSha + "`r`n"), (BB-Utf8NoBom))
function Log([string]$s) { Add-Content -LiteralPath $log -Value $s -Encoding UTF8 }
function RunNative($exe, [string]$argLine, [int]$timeoutSec) {
    $o = [IO.Path]::GetTempFileName(); $e = [IO.Path]::GetTempFileName()
    try { $rc = BB-RunSsh $exe $argLine $o $e $timeoutSec; $t = (Get-Content -LiteralPath $o -Raw -ErrorAction SilentlyContinue) + (Get-Content -LiteralPath $e -Raw -ErrorAction SilentlyContinue); Log ([string]$t); return @{ Code = $rc; Text = [string]$t } }
    finally { Remove-Item -LiteralPath $o, $e -ErrorAction SilentlyContinue }
}
$tmp = $(if ($Mode -eq 'install') { '/tmp/img_' + $R } else { '/tmp/imgrb_' + $R })
$h = RunNative $ssh ('-n -o BatchMode=yes -o ConnectTimeout=15 ' + $script:BB_DroneHost + ' "test $(hostname) = bumblebee-20ec && mkdir ' + $tmp + ' && echo HOST_OK"') 40
if ($h.Code -ne 0 -or $h.Text -notmatch 'HOST_OK') { Fail ('дрон не ответил, это не bumblebee-20ec или временная папка уже есть. Ничего не изменено. Журнал: ' + $log) }
if ($Mode -eq 'install') {
    $src = '"' + (Join-Path $ik 'payload') + '" "' + (Join-Path $ik 'image_manifest.final.tsv') + '" "' + $camConf + '" "' + (Join-Path $root 'image_r2j\image_install.sh') + '"'
    $c = RunNative $scp ('-r -o BatchMode=yes -o ConnectTimeout=15 ' + $src + ' ' + $script:BB_DroneHost + ':' + $tmp + '/') 120
    if ($c.Code -ne 0) { Fail ('копирование на дрон не удалось. Файлы не заменены. Журнал: ' + $log) }
    $i = RunNative $ssh ('-n -o BatchMode=yes -o ConnectTimeout=15 ' + $script:BB_DroneHost + ' "bash ' + $tmp + '/image_install.sh ' + $tmp + ' < /dev/null 2>&1"') 180
    Write-Host $i.Text
    if ($i.Text -notmatch 'BB_IMAGE_INSTALL_DONE') { Fail ('установка не дошла до конца (строки выше). Не взлетать. Скажите Claude; откат 06c_otkat_r2j_cam.cmd после разрешения чата 1. 06_rollback_r2j.cmd НЕ запускать (строка «Run 06_rollback_r2j.cmd» выше - из общего установщика r5): 06 откатывает образ r2j, а резерв варианта лежит в ' + $bcam + '. Журнал: ' + $log) }
    if ($i.Text -match 'BB_IMAGE_INSTALL_DONE (\d{8}_\d{6})') { Log ('VARIANT_BACKUP=' + $bcam + '/' + $Matches[1]) }
} else {
    $src = '"' + $camConf + '" "' + (Join-Path $root 'image_r2j\image_rollback.sh') + '"'
    $c = RunNative $scp ('-o BatchMode=yes -o ConnectTimeout=15 ' + $src + ' ' + $script:BB_DroneHost + ':' + $tmp + '/') 120
    if ($c.Code -ne 0) { Fail ('копирование на дрон не удалось. Ничего не изменено. Журнал: ' + $log) }
    $i = RunNative $ssh ('-n -o BatchMode=yes -o ConnectTimeout=15 ' + $script:BB_DroneHost + ' "bash ' + $tmp + '/image_rollback.sh ' + $tmp + ' ' + $label + ' < /dev/null 2>&1"') 180
    Write-Host $i.Text
    if ($i.Text -notmatch 'BB_IMAGE_ROLLBACK_DONE') { Fail ('откат не дошёл до конца (строки выше). Не взлетать. Скажите Claude. Журнал: ' + $log) }
}
# проверка «файлы легли» (только чтение)
$postMode = $(if ($Mode -eq 'install') { 'installed' } else { 'rolledback' })
$post = R6-Remote $ssh $genPre @($postMode) $outDir ('cam_precheck_' + $postMode + '_' + $stamp) 90
foreach ($l in ($post.Text -split "`r?`n")) { if ($l -match '^CP_(FILE|COUNT|RESULT)') { Write-Host $l; Log $l } }
if ($post.Code -ne 0 -or $post.Text -notmatch '(?m)^CP_RESULT OK\s*$') { Fail ('после ' + $(if ($Mode -eq 'install') { 'установки' } else { 'отката' }) + ' файлы на Pi НЕ те (строки выше). Не взлетать, службу не запускать, скажите Claude. Журнал: ' + $log) }
Log ('# ' + (R6-Now) + ' файлы на Pi проверены: ' + $postMode)
Write-Host ''
if ($Mode -eq 'install') {
    Write-Host 'Готово: файлы варианта легли (src и install оверлея r2j). Это ещё не значит, что стек их исполняет.' -ForegroundColor White -BackgroundColor DarkGreen
    Write-Host '  Дальше: запустите службу сами (sudo systemctl start bumblebee, пароль ваш), подождите 2 минуты, затем 24a_proverka_kamery_polnye_stroki.cmd.'
} else {
    Write-Host 'Готово: прежние файлы r2j вернулись (src и install оверлея r2j).' -ForegroundColor White -BackgroundColor DarkGreen
    Write-Host '  Дальше: запустите службу сами (sudo systemctl start bumblebee, пароль ваш), подождите 2 минуты, затем 24b_proverka_kamery_r2j.cmd, потом 09 и 10.'
    Write-Host '  Откаты r5 (17, 14, 12, 06) - только после успешного 24b; 06 - только с явной меткой резерва образа r2j (из out\install_r2j_<число>.log).'
}
Write-Host ('Журнал: ' + $log)
exit 0
