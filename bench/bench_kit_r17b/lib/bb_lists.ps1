# bb_lists.ps1 (Claude, 10.11.2026, набор r2) - общие функции для шагов 13-17: чтение списков образа r2j и подстановка их в скрипты Pi вместо строк-маркеров. Сама ничего не запускает и к дрону не подключается.
# Подключается после lib\bb_common.ps1 через ". lib\bb_lists.ps1".
function BL-CppList([string]$here) {
    $p = Join-Path $here 'image_r2j\CPP_SOURCES_r2j.tsv'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $o = New-Object Collections.Generic.List[string]
    foreach ($l in [IO.File]::ReadAllLines($p)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        $f = $l.Split("`t")
        if ($f.Count -ne 3 -or $f[0] -cnotmatch '^[0-9a-f]{64}$' -or $f[1] -cnotmatch '^[A-Za-z0-9_./-]{1,150}$' -or $f[1] -match '\.\.' -or $f[2] -cnotmatch '^[R-]$') { BB-Stop ('строка списка C++ не sha256 TAB путь TAB R|-: ' + $l) 4 }
        $o.Add($f[0] + '  ' + $f[1] + '  ' + $f[2])
    }
    if ($o.Count -lt 1) { BB-Stop 'список C++ пуст' 4 }
    return ,$o
}
function BL-PyList([string]$here) {
    $p = Join-Path $here 'image_r2j\INSTALL_SHA256_r2j.txt'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $o = New-Object Collections.Generic.List[string]
    foreach ($l in [IO.File]::ReadAllLines($p)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        if ($l -cnotmatch '^[0-9a-f]{64}\s+[A-Za-z0-9_.-]{1,60}$') { BB-Stop ('строка списка не «sha256  имя»: ' + $l) 4 }
        if ($l.Trim().EndsWith('.py')) { $o.Add(($l.Trim() -replace '\s+', '  ')) }
    }
    if ($o.Count -lt 1) { BB-Stop 'список python-узлов пуст' 4 }
    return ,$o
}
function BL-MavrosSrcList([string]$here) {
    $p = Join-Path $here 'image_r2j\mavros_bp02_sources.tsv'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $o = New-Object Collections.Generic.List[string]
    foreach ($l in [IO.File]::ReadAllLines($p)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        $f = $l.Split("`t")
        if ($f.Count -lt 3 -or $f[2] -cnotmatch '^[0-9a-f]{64}$' -or $f[0] -cnotmatch '^[A-Za-z0-9_./-]{1,120}$' -or $f[0] -match '\.\.') { BB-Stop ('строка списка MAVROS не path TAB sha TAB sha: ' + $l) 4 }
        $o.Add($f[2] + '  ' + $f[0] + '  R')
    }
    if ($o.Count -ne 5) { BB-Stop ('в списке MAVROS должно быть 5 файлов, а их ' + $o.Count) 4 }
    return ,$o
}
# Launch-файлы и fcu_detect.py (решение чата 1 21:50, S2): sha256 TAB вид TAB путь -> «sha256  вид  путь». Вид LAUNCH или FCU.
function BL-RtList([string]$here) {
    $p = Join-Path $here 'image_r2j\RUNTIME_PY_r2j.tsv'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $o = New-Object Collections.Generic.List[string]
    foreach ($l in [IO.File]::ReadAllLines($p)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        $f = $l.Split("`t")
        if ($f.Count -ne 3 -or $f[0] -cnotmatch '^[0-9a-f]{64}$' -or $f[1] -cnotmatch '^(LAUNCH|FCU)$' -or $f[2] -cnotmatch '^[A-Za-z0-9_./-]{1,150}$' -or $f[2] -match '\.\.') { BB-Stop ('строка списка RT не sha256 TAB LAUNCH|FCU TAB путь: ' + $l) 4 }
        $o.Add($f[0] + '  ' + $f[1] + '  ' + $f[2])
    }
    if ($o.Count -lt 2 -or @($o | Where-Object { $_ -match '  FCU  ' }).Count -ne 1) { BB-Stop 'в списке RT должен быть ровно один FCU (fcu_detect.py) и launch-файлы' 4 }
    return ,$o
}
# r11 (16.11.2026): вторые допустимые sha256 примеров полёта карты real (image_r2j\EXAMPLES_REAL_20261116.tsv: sha256 TAB путь). Только для сверок «что стоит на дроне» - 09 и 15;
# сборка 13 их не берёт. Вход - список «sha256  путь  флаг» (BL-CppList или список run_install_check.ps1); выход - тот же список, где у путей из файла поле sha = «sha_r2j,sha_real».
function BL-ApplyRealAlt([string]$here, $list) {
    $p = Join-Path $here 'image_r2j\EXAMPLES_REAL_20261116.tsv'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $alt = @{}
    foreach ($l in [IO.File]::ReadAllLines($p)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        $f = $l.Split("`t")
        if ($f.Count -ne 2 -or $f[0] -cnotmatch '^[0-9a-f]{64}$' -or $f[1] -cnotmatch '^ros2_ws/src/bumblebee/examples/[A-Za-z0-9_./-]{1,100}\.py$' -or $f[1] -match '\.\.' -or $alt.ContainsKey($f[1])) { BB-Stop ('строка списка примеров real не «sha256 TAB ros2_ws/src/bumblebee/examples/....py» или путь повторяется: ' + $l) 4 }
        $alt[$f[1]] = $f[0]
    }
    $o = New-Object Collections.Generic.List[string]; $used = 0
    foreach ($e in $list) {
        $f = ([string]$e).Split([string[]]@('  '), [StringSplitOptions]::None)
        if ($f.Count -eq 3 -and $alt.ContainsKey($f[1])) {
            if ($f[2] -ne '-' -or $f[0] -cnotmatch '^[0-9a-f]{64}$') { BB-Stop ('пример real для строки, которая не «sha256  путь  -»: ' + $e) 4 }
            $o.Add($f[0] + ',' + $alt[$f[1]] + '  ' + $f[1] + '  ' + $f[2]); $used++
        }
        else { $o.Add([string]$e) }
    }
    if ($used -ne $alt.Count) { BB-Stop ('в ' + $p + ' есть путь, которого нет в списке C++ и примеров r2j (CPP_SOURCES_r2j.tsv)') 4 }
    return ,$o
}
# r13 (17.11.2026): второе допустимое sha256 детектора меток варианта jd2 (image_r2j\POSEFIX_JD2_20261117.tsv: sha256 TAB aruco_detect.py; пакет drone_pkg_posefix_jd2_20261117).
# Только для сверок «что стоит на дроне» - 09 и 15, по образцу BL-ApplyRealAlt. Вход - список python-узлов «sha256  имя» (BL-PyList или $py в run_install_check.ps1); выход - тот же список, где у aruco_detect.py
# поле sha = «sha_r2j,sha_jd2» (скрипт Pi помечает второе POSEFIX_JD2). Строго: в файле ровно одна строка, имя только aruco_detect.py, sha 64 hex, sha jd2 не равен r2j; в списке ровно одна строка
# aruco_detect.py; остальные узлы не меняются. Имена сравниваются с учётом регистра.
function BL-ApplyJd2Alt([string]$here, $list) {
    $p = Join-Path $here 'image_r2j\POSEFIX_JD2_20261117.tsv'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $altSha = $null; $altName = 'aruco_detect.py'; $rows = 0
    foreach ($l in [IO.File]::ReadAllLines($p)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        $f = $l.Split("`t"); $rows++
        if ($f.Count -ne 2 -or $f[0] -cnotmatch '^[0-9a-f]{64}$' -or $f[1] -cne $altName -or $rows -ne 1) { BB-Stop ('строка списка jd2 не «sha256 TAB aruco_detect.py» или строк больше одной: ' + $l) 4 }
        $altSha = $f[0]
    }
    if ($rows -ne 1 -or $null -eq $altSha) { BB-Stop ('в ' + $p + ' должна быть ровно одна строка (aruco_detect.py), а их ' + $rows) 4 }
    $o = New-Object Collections.Generic.List[string]; $used = 0
    foreach ($e in $list) {
        $f = ([string]$e).Split([string[]]@('  '), [StringSplitOptions]::None)
        if ($f.Count -eq 2 -and $f[1] -ceq $altName) {
            if ($f[0] -cnotmatch '^[0-9a-f]{64}$' -or $f[0] -ceq $altSha) { BB-Stop ('строка aruco_detect.py r2j не «sha256  aruco_detect.py» или sha jd2 равен sha r2j: ' + $e) 4 }
            $o.Add($f[0] + ',' + $altSha + '  ' + $f[1]); $used++
        }
        else { $o.Add([string]$e) }
    }
    if ($used -ne 1) { BB-Stop ('в списке python-узлов (INSTALL_SHA256_r2j.txt) нет ровно одной строки aruco_detect.py для jd2 (найдено ' + $used + ')') 4 }
    return ,$o
}
# r17 (19.11.2026; в r16 здесь был В1 - его aruco 890dafbf больше не допускается, решение владельца): вариант В1.1 - допустимые sha256 для aruco_detect.py и vpe_fix.py (image_r2j\POSEFIX_V11_20261119.tsv: sha256 TAB имя, ровно 2 строки; пакет drone_pkg_posefix_v1x_20261119).
# Только для 09 и 15, ПОСЛЕ BL-ApplyJd2Alt. Вход: у aruco_detect.py ровно «sha_r2j,sha_jd2», у vpe_fix.py ровно одно sha (r2j); выход: aruco «r2j,jd2,v11», vpe «r2j,v1» (vpe_fix В1.1 = vpe_fix В1 39027fbd; порядок важен: скрипт Pi
# ставит метку по совпавшему sha). Строго: в файле ровно 2 строки - aruco_detect.py и vpe_fix.py по одной (с учётом регистра), sha 64 hex, v11 не равен r2j (и jd2 у aruco); в списке ровно
# одна строка каждого узла; остальные узлы не меняются. Иначе код 4 до связи с дроном.
function BL-ApplyV11Alt([string]$here, $list) {
    $p = Join-Path $here 'image_r2j\POSEFIX_V11_20261119.tsv'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $alt = @{}; $rows = 0
    foreach ($l in [IO.File]::ReadAllLines($p)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        $f = $l.Split("`t"); $rows++
        if ($f.Count -ne 2 -or $f[0] -cnotmatch '^[0-9a-f]{64}$' -or ($f[1] -cne 'aruco_detect.py' -and $f[1] -cne 'vpe_fix.py') -or $rows -gt 2) { BB-Stop ('строка списка В1.1 не «sha256 TAB aruco_detect.py|vpe_fix.py» или строк больше двух: ' + $l) 4 }
        foreach ($k in @($alt.Keys)) { if ($k -ceq $f[1]) { BB-Stop ('в списке В1.1 узел повторяется: ' + $l) 4 } }
        $alt[$f[1]] = $f[0]
    }
    if ($rows -ne 2 -or $alt.Count -ne 2) { BB-Stop ('в ' + $p + ' должно быть ровно 2 строки (aruco_detect.py и vpe_fix.py), а их ' + $rows) 4 }
    $o = New-Object Collections.Generic.List[string]; $usedA = 0; $usedV = 0
    foreach ($e in $list) {
        $f = ([string]$e).Split([string[]]@('  '), [StringSplitOptions]::None)
        if ($f.Count -eq 2 -and $f[1] -ceq 'aruco_detect.py') {
            if ($f[0] -cnotmatch '^[0-9a-f]{64},[0-9a-f]{64}$') { BB-Stop ('строка aruco_detect.py не «sha_r2j,sha_jd2  aruco_detect.py» (сначала BL-ApplyJd2Alt): ' + $e) 4 }
            $two = $f[0].Split(','); $v = $alt['aruco_detect.py']
            if ($v -ceq $two[0] -or $v -ceq $two[1]) { BB-Stop ('sha В1.1 aruco_detect.py равен sha r2j или jd2: ' + $v) 4 }
            $o.Add($f[0] + ',' + $v + '  ' + $f[1]); $usedA++
        }
        elseif ($f.Count -eq 2 -and $f[1] -ceq 'vpe_fix.py') {
            $v = $alt['vpe_fix.py']
            if ($f[0] -cnotmatch '^[0-9a-f]{64}$' -or $f[0] -ceq $v) { BB-Stop ('строка vpe_fix.py r2j не «sha256  vpe_fix.py» или sha В1.1 vpe_fix.py равен sha r2j: ' + $e) 4 }
            $o.Add($f[0] + ',' + $v + '  ' + $f[1]); $usedV++
        }
        else { $o.Add([string]$e) }
    }
    if ($usedA -ne 1 -or $usedV -ne 1) { BB-Stop ('в списке python-узлов (INSTALL_SHA256_r2j.txt) нет ровно одной строки aruco_detect.py и одной vpe_fix.py для В1.1 (найдено ' + $usedA + ' и ' + $usedV + ')') 4 }
    return ,$o
}
# r14 (17.11.2026): вторые допустимые sha256 камеры варианта r2m_cam (image_r2j\R2M_CAM_20261117.tsv: sha256 TAB вид TAB имя; ровно 2 строки - «PY camera_fix.py» и «LAUNCH launch/bumblebee.launch.py»;
# пакет drone_pkg_r2m_cam_20261117, образ /work/image_r2m_cam_20261117). Только для сверок «что стоит на дроне» - 09 и 15, по образцу BL-ApplyJd2Alt. Строго: ровно эти 2 строки, sha 64 hex,
# sha r2m_cam не равен r2j, в списке ровно одна строка этого узла (пути); остальные строки не меняются. Скрипт Pi подписывает второе значение R2M_CAM (метка по имени узла и пути).
function BL-R2mRead([string]$here) {
    $p = Join-Path $here 'image_r2j\R2M_CAM_20261117.tsv'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $py = $null; $ln = $null; $rows = 0
    foreach ($l in [IO.File]::ReadAllLines($p)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        $f = $l.Split("`t"); $rows++
        if ($f.Count -ne 3 -or $f[0] -cnotmatch '^[0-9a-f]{64}$' -or $rows -gt 2) { BB-Stop ('строка списка r2m_cam не «sha256 TAB PY TAB camera_fix.py» / «sha256 TAB LAUNCH TAB launch/bumblebee.launch.py» или строк больше двух: ' + $l) 4 }
        if ($f[1] -ceq 'PY' -and $f[2] -ceq 'camera_fix.py' -and $null -eq $py) { $py = $f[0] }
        elseif ($f[1] -ceq 'LAUNCH' -and $f[2] -ceq 'launch/bumblebee.launch.py' -and $null -eq $ln) { $ln = $f[0] }
        else { BB-Stop ('строка списка r2m_cam: допускаются только «PY camera_fix.py» и «LAUNCH launch/bumblebee.launch.py», каждая один раз: ' + $l) 4 }
    }
    if ($rows -ne 2 -or $null -eq $py -or $null -eq $ln) { BB-Stop ('в ' + $p + ' должно быть ровно 2 строки (camera_fix.py и launch/bumblebee.launch.py), а их ' + $rows) 4 }
    return @{ PY = $py; LAUNCH = $ln }
}
# вход - список python-узлов «sha256  имя» (после BL-ApplyJd2Alt); у camera_fix.py поле sha = «sha_r2j,sha_r2m_cam»
function BL-ApplyR2mPyAlt([string]$here, $list) {
    $alt = (BL-R2mRead $here).PY; $name = 'camera_fix.py'
    $o = New-Object Collections.Generic.List[string]; $used = 0
    foreach ($e in $list) {
        $f = ([string]$e).Split([string[]]@('  '), [StringSplitOptions]::None)
        if ($f.Count -eq 2 -and $f[1] -ceq $name) {
            if ($f[0] -cnotmatch '^[0-9a-f]{64}$' -or $f[0] -ceq $alt) { BB-Stop ('строка camera_fix.py r2j не «sha256  camera_fix.py» или sha r2m_cam равен sha r2j: ' + $e) 4 }
            $o.Add($f[0] + ',' + $alt + '  ' + $f[1]); $used++
        }
        else { $o.Add([string]$e) }
    }
    if ($used -ne 1) { BB-Stop ('в списке python-узлов (INSTALL_SHA256_r2j.txt) нет ровно одной строки camera_fix.py для r2m_cam (найдено ' + $used + ')') 4 }
    return ,$o
}
# вход - список BL-RtList «sha256  вид  путь»; у LAUNCH launch/bumblebee.launch.py поле sha = «sha_r2j,sha_r2m_cam»
function BL-ApplyR2mRtAlt([string]$here, $list) {
    $alt = (BL-R2mRead $here).LAUNCH; $path = 'launch/bumblebee.launch.py'
    $o = New-Object Collections.Generic.List[string]; $used = 0
    foreach ($e in $list) {
        $f = ([string]$e).Split([string[]]@('  '), [StringSplitOptions]::None)
        if ($f.Count -eq 3 -and $f[1] -ceq 'LAUNCH' -and $f[2] -ceq $path) {
            if ($f[0] -cnotmatch '^[0-9a-f]{64}$' -or $f[0] -ceq $alt) { BB-Stop ('строка launch r2j не «sha256  LAUNCH  launch/bumblebee.launch.py» или sha r2m_cam равен sha r2j: ' + $e) 4 }
            $o.Add($f[0] + ',' + $alt + '  ' + $f[1] + '  ' + $f[2]); $used++
        }
        else { $o.Add([string]$e) }
    }
    if ($used -ne 1) { BB-Stop ('в списке RT (RUNTIME_PY_r2j.tsv) нет ровно одной строки LAUNCH launch/bumblebee.launch.py для r2m_cam (найдено ' + $used + ')') 4 }
    return ,$o
}
# sha256 скрипта висения hover r6 из image_r2j\required_shas.txt (HOVER_R6_SHA256): одна строка для подстановки вместо #@@HOVER@@ (r3, сверка hover в 13)
function BL-HoverSha([string]$here) {
    $p = Join-Path $here 'image_r2j\required_shas.txt'
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 }
    $o = New-Object Collections.Generic.List[string]
    foreach ($l in [IO.File]::ReadAllLines($p)) { if ($l -cmatch '^HOVER_R6_SHA256=([0-9a-f]{64})$') { $o.Add($Matches[1]) } }
    if ($o.Count -ne 1) { BB-Stop 'в required_shas.txt должна быть ровно одна строка HOVER_R6_SHA256=<64 hex>' 4 }
    return ,$o
}
# Подставляет списки (маркер -> строки) в текст скрипта Pi и пишет его в out без перезаписи. Возвращает путь файла.
function BL-Generate([string]$template, [hashtable]$lists, [string]$outDir, [string]$name) {
    if (-not (Test-Path -LiteralPath $template)) { BB-Stop ('нет файла ' + $template) 4 }
    $text = ([IO.File]::ReadAllText($template)) -replace "`r`n", "`n"
    foreach ($k in $lists.Keys) {
        $mk = '#@@' + $k + '@@' + "`n"
        if (-not $text.Contains($mk)) { BB-Stop ('в ' + (Split-Path $template -Leaf) + ' нет строки #@@' + $k + '@@') 4 }
        $body = ($lists[$k] -join "`n")
        if ($body -eq '') { $body = '# пусто' }
        $text = $text.Replace($mk, $body + "`n")
    }
    $gen = BB-NewOutFile $outDir $name
    [IO.File]::WriteAllText($gen, $text, (BB-Utf8NoBom))
    return $gen
}
