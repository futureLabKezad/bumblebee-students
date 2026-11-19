# backup_root_r7.ps1 (Claude, 13.11.2026, набор r7) - BACKUP_ROOT образа r2j: ОДНА строка «BACKUP_ROOT=...» в image_r2j\image_target.conf.
# Её читают 05 и 06 (на Pi через image_install.sh и image_rollback.sh) и 05c/06c (резерв варианта - BACKUP_ROOT/r2j_cam). Значение задаёт ТОЛЬКО владелец
# (11.11: «Решу у дрона»; предложение чата 1 - /home/lb/bb_backup, решает владелец). К дрону не обращается, сеть не нужна.
# Без ключей - ТОЛЬКО ЧТЕНИЕ: показывает строку и проверяет её. Код 0 = задано и годно; 1 = TBD (05, 05c и 06c откажут на ПК, 06 - на Pi до любых изменений);
#   2 = строк BACKUP_ROOT= не одна или значение негодно.
# -Set <путь> -OwnerWords "<слова владельца>": только если сейчас TBD; меняет ТОЛЬКО эту строку, остальные байты файла те же; прежний файл -
#   в _aside_conf_<время>\; запись (время по часам ПК, слова владельца, sha256 до и после) дописывается в BACKUP_ROOT_ЗАПИСЬ.txt. Код 0 записано; 2 отказ.
# Годное значение: абсолютный путь из латиницы, цифр, _ . - /; без «..», «//», «/» в конце, не короче двух уровней; не /tmp, /var/tmp, /run, /dev, /proc, /sys
#   (после перезагрузки резерв пропал бы или это не каталог данных); не DEST_ROOT и не внутри DEST_ROOT/ros2_ws или DEST_ROOT/bench_ws (13 копирует
#   ~/ros2_ws/src в сборку, в ~/bench_ws шаги сборки ждут своих каталогов). Те же знаки требует гейт варианта (check_gates_r2j_cam.ps1, стр. 36);
#   image_install.sh читает файл командой «.» в bash, поэтому другие знаки (пробел, ; $ и кавычки) опасны.
param([string]$Set = '', [string]$OwnerWords = '')
$ErrorActionPreference = 'Stop'
$ik = Split-Path -Parent $MyInvocation.MyCommand.Path
$conf = Join-Path $ik 'image_target.conf'
function Done([int]$code, [string]$msg) { Write-Host $msg; exit $code }
function Bad-Value([string]$v, [string]$dest) {
    if ($v -cnotmatch '^/[A-Za-z0-9_./-]+$') { return 'не абсолютный путь из латиницы, цифр, _ . - /' }
    if ($v.Contains('..') -or $v.Contains('//') -or $v.EndsWith('/')) { return 'есть «..», «//» или «/» в конце' }
    if (@($v.Split('/') | Where-Object { $_ -ne '' }).Count -lt 2) { return 'слишком короткий путь (нужно не меньше двух уровней, например /home/lb/...)' }
    foreach ($s in '/tmp', '/var/tmp', '/run', '/dev', '/proc', '/sys') { if ($v -ceq $s -or $v.StartsWith($s + '/')) { return ('внутри ' + $s + ': после перезагрузки резерв пропал бы или это не каталог данных') } }
    if ($dest -ne '') {
        if ($v -ceq $dest) { return 'равно DEST_ROOT' }
        foreach ($s in 'ros2_ws', 'bench_ws') { $d = $dest.TrimEnd('/') + '/' + $s; if ($v -ceq $d -or $v.StartsWith($d + '/')) { return ('внутри ' + $d + ': сборка 13 копирует ~/ros2_ws/src, в ~/bench_ws шаги сборки ждут своих каталогов') } }
    }
    return ''
}
if (-not (Test-Path -LiteralPath $conf)) { Done 2 ('СТОП: нет файла ' + $conf) }
$bytes = [IO.File]::ReadAllBytes($conf)
$text = (New-Object Text.UTF8Encoding($false)).GetString($bytes)
$lines = $text -split "`n"
$idx = @(); for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match '^BACKUP_ROOT=') { $idx += $i } }
$dl = @($lines | Where-Object { $_ -match '^DEST_ROOT=' })
$dest = ''; if ($dl.Count -eq 1) { $dest = ($dl[0] -replace '^DEST_ROOT=', '').Trim() }
if ($idx.Count -ne 1) { Done 2 ('СТОП: строк BACKUP_ROOT= в image_target.conf ' + $idx.Count + ', а должна быть ровно одна.') }
$cur = ($lines[$idx[0]] -replace '^BACKUP_ROOT=', '').Trim()
if ($Set -eq '') {
    Write-Host ('Строка: BACKUP_ROOT=' + $cur + '  (файл ' + $conf + ', sha256 ' + (Get-FileHash -Algorithm SHA256 -LiteralPath $conf).Hash.ToLower() + ')')
    if ($cur -eq '' -or $cur -match 'TBD') { Done 1 'BACKUP_ROOT не задан (TBD): 05, 05c и 06c откажут на ПК, 06 откажет на Pi до любых изменений. Задаёт чат 1 только по слову владельца: -Set <путь> -OwnerWords "<слова>".' }
    $why = Bad-Value $cur $dest
    if ($why -ne '') { Done 2 ('BACKUP_ROOT негоден: ' + $why) }
    Done 0 'BACKUP_ROOT задан и годен по правилам этого файла.'
}
if ($cur -ne 'TBD') { Done 2 ('СТОП: BACKUP_ROOT уже задан («' + $cur + '»). Менять только новым решением владельца и вручную, с записью. Ничего не изменено.') }
if ($OwnerWords.Trim().Length -lt 3) { Done 2 'СТОП: нужны слова владельца (-OwnerWords "..."). Ничего не изменено.' }
$why = Bad-Value $Set $dest
if ($why -ne '') { Done 2 ('СТОП: значение «' + $Set + '» негодно: ' + $why + '. Ничего не изменено.') }
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$aside = Join-Path $ik ('_aside_conf_' + $stamp)
if (Test-Path -LiteralPath $aside) { Done 2 ('СТОП: папка уже есть: ' + $aside + '. Ничего не изменено.') }
$shaBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $conf).Hash.ToLower()
$old = $lines[$idx[0]]
$cr = ''; if ($old.EndsWith("`r")) { $cr = "`r" }
$lines[$idx[0]] = 'BACKUP_ROOT=' + $Set + $cr
$newText = $lines -join "`n"
$newBytes = (New-Object Text.UTF8Encoding($false)).GetBytes($newText)
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF -and -not ($newBytes.Length -ge 3 -and $newBytes[0] -eq 0xEF)) { $newBytes = [byte[]](@(0xEF, 0xBB, 0xBF) + @($newBytes)) }
New-Item -ItemType Directory -Path $aside | Out-Null
Copy-Item -LiteralPath $conf -Destination (Join-Path $aside 'image_target.conf')
[IO.File]::WriteAllBytes($conf, $newBytes)
$after = (New-Object Text.UTF8Encoding($false)).GetString([IO.File]::ReadAllBytes($conf)) -split "`n"
$diff = @(); for ($i = 0; $i -lt [Math]::Max($after.Count, $lines.Count); $i++) { if ($i -ge $after.Count -or $i -ge ($text -split "`n").Count -or $after[$i] -cne ($text -split "`n")[$i]) { $diff += $i } }
if ($diff.Count -ne 1 -or $diff[0] -ne $idx[0]) { Copy-Item -LiteralPath (Join-Path $aside 'image_target.conf') -Destination $conf -Force; Done 2 'СТОП: после записи изменилась не одна строка - файл возвращён из копии. Скажите Claude.' }
$shaAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $conf).Hash.ToLower()
$rec = Join-Path $ik 'BACKUP_ROOT_ЗАПИСЬ.txt'
$entry = @('ВРЕМЯ_ПК=' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), 'BACKUP_ROOT=' + $Set, 'СЛОВА_ВЛАДЕЛЬЦА=' + $OwnerWords.Trim(), 'SHA256_ДО=' + $shaBefore, 'SHA256_ПОСЛЕ=' + $shaAfter, 'ПРЕЖНИЙ_ФАЙЛ=' + (Join-Path $aside 'image_target.conf'), 'ЗАПИСАЛ=чат 1 (backup_root_r7.ps1)', '')
[IO.File]::AppendAllText($rec, ($entry -join "`r`n") + "`r`n", (New-Object Text.UTF8Encoding($true)))
Write-Host ('Записано: BACKUP_ROOT=' + $Set + '. sha256 image_target.conf: было ' + $shaBefore + ', стало ' + $shaAfter + '. Запись: ' + $rec)
Write-Host 'Строка SHA256SUMS.txt набора для image_r2j/image_target.conf теперь не сходится - так и должно быть; новая сумма - в записи.'
exit 0