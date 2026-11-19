# bb_lists_r2jcam.ps1 (Claude, 12.11.2026, набор r6) - списки варианта «r2j + камера полных строк» (image_r2j_cam) для 09c, 15c, 05c/06c и 24a/24b.
# Подключается после lib\bb_common.ps1 и lib\bb_lists.ps1. Списки r2j (bb_lists.ps1) НЕ меняются: прежние 09 и 15 проверяют r2j как раньше.
# Сама ничего не запускает и к дрону не подключается.
function BLC-PyList([string]$here) {
    $p = Join-Path $here 'image_r2j_cam\INSTALL_SHA256_r2jcam.txt'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $o = New-Object Collections.Generic.List[string]
    foreach ($l in [IO.File]::ReadAllLines($p)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        if ($l -cnotmatch '^[0-9a-f]{64}\s+[A-Za-z0-9_.-]{1,60}$') { BB-Stop ('строка списка не «sha256  имя»: ' + $l) 4 }
        if ($l.Trim().EndsWith('.py')) { $o.Add(($l.Trim() -replace '\s+', '  ')) }
    }
    if ($o.Count -lt 1) { BB-Stop 'список python-узлов варианта пуст' 4 }
    if (@($o | Where-Object { $_ -ceq 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83  camera_fix.py' }).Count -ne 1) { BB-Stop 'в списке варианта camera_fix.py не dabd5076' 4 }
    return ,$o
}
function BLC-RtList([string]$here) {
    $p = Join-Path $here 'image_r2j_cam\RUNTIME_PY_r2jcam.tsv'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $o = New-Object Collections.Generic.List[string]
    foreach ($l in [IO.File]::ReadAllLines($p)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        $f = $l.Split("`t")
        if ($f.Count -ne 3 -or $f[0] -cnotmatch '^[0-9a-f]{64}$' -or $f[1] -cnotmatch '^(LAUNCH|FCU)$' -or $f[2] -cnotmatch '^[A-Za-z0-9_./-]{1,150}$' -or $f[2] -match '\.\.') { BB-Stop ('строка списка RT варианта не sha256 TAB LAUNCH|FCU TAB путь: ' + $l) 4 }
        $o.Add($f[0] + '  ' + $f[1] + '  ' + $f[2])
    }
    if ($o.Count -lt 2 -or @($o | Where-Object { $_ -match '  FCU  ' }).Count -ne 1) { BB-Stop 'в списке RT варианта должен быть ровно один FCU и launch-файлы' 4 }
    if (@($o | Where-Object { $_ -ceq '5f0954d82ba7b8034e169fa60c99edd8cd501921e923faa5f10f795ccf388294  LAUNCH  launch/bumblebee.launch.py' }).Count -ne 1) { BB-Stop 'в списке RT варианта bumblebee.launch.py не 5f0954d8' 4 }
    return ,$o
}
# Четыре места на Pi: путь от HOME TAB sha r2j TAB sha варианта -> строки «путь sha_r2j sha_cam» для pi\r6_cam_precheck.sh
function BLC-VarFiles([string]$here) {
    $p = Join-Path $here 'image_r2j_cam\VARIANT_FILES.tsv'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $o = New-Object Collections.Generic.List[string]
    foreach ($l in [IO.File]::ReadAllLines($p)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        $f = $l.Split("`t")
        if ($f.Count -ne 3 -or $f[0] -cnotmatch '^(ros2_ws|bench_ws)/[A-Za-z0-9_./-]{1,150}$' -or $f[0] -match '\.\.' -or $f[1] -cnotmatch '^[0-9a-f]{64}$' -or $f[2] -cnotmatch '^[0-9a-f]{64}$') { BB-Stop ('строка VARIANT_FILES.tsv не путь TAB sha TAB sha: ' + $l) 4 }
        $o.Add($f[0] + ' ' + $f[1] + ' ' + $f[2])
    }
    if ($o.Count -ne 4) { BB-Stop ('в VARIANT_FILES.tsv должно быть 4 места, а их ' + $o.Count) 4 }
    return ,$o
}
