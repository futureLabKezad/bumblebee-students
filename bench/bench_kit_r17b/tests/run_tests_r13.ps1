# run_tests_r13.ps1 (Claude, 17.11.2026, набор r13 = r11 + jd2 в 09/15 + блок 3c шага 07 из r12) - тесты НОВОГО в r13 на ПК, в песочнице. К дрону не подключается.
# Вместо ssh - подделка tests\fake_ssh_r13.cs (сеть не открывает; для сквозных проверок подаёт скрипт Pi в WSL на поддельный «дом дрона» tests\r13_wsl_tree.sh из образов в /work, только чтение).
# СТРАЖ (требование чата 1): перед КАЖДЫМ запуском шага тест сам проверяет, что ssh, который найдёт BB-FindSsh (Get-Command ssh, первый в PATH), - это подделка:
#   путь = <прогон>\fake\ssh.exe, sha256 = sha собранной подделки, в файле есть метка BB_FAKE_SSH_R13_NO_NETWORK. Для 07 то же проверяется ещё и в отдельном процессе powershell
#   с тем же окружением, что получит run_07_takeoff.ps1. Иначе шаг НЕ запускается, тест - FAIL. Раздел G сам подменяет подделку заглушкой без метки и проверяет отказ до вызова.
# J: 09 и 15 принимают детектор меток jd2 (b89bfb43…) вторым значением только для aruco_detect.py, метка POSEFIX_JD2; остальное строго (как r11); плохой список jd2 - код 4 без ssh.
# E: 07 (блок 3c из r12): 09 должна быть строго позже последнего журнала любого drone_pkg_*\out\*.log и журналов пакетов в out набора; настоящий отчёт 09 r13 с POSEFIX_JD2.
# C: .cmd. K: r13 = копия r11 + только ожидаемые правки (r11 и r12 рядом читаются, не меняются).
# Всё WSL - с nice -n 19 ionice -c3 (в WSL идут серии Gazebo); тест и его дочерние процессы - с пониженным приоритетом (BelowNormal).
# Запуск: powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_tests_r13.ps1 [-Only J,E,G,C,K]. Итог: «ИТОГ r13: PASS n, FAIL m».
param([string[]]$Only = @())
$ErrorActionPreference = 'Stop'
$Only = @($Only | ForEach-Object { $_ -split ',' } | Where-Object { $_ -ne '' })   # -File передаёт «E,G» одной строкой
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
try { [Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'BelowNormal' } catch { }
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$Run = Join-Path $T ('run_r13_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $Run | Out-Null
$Log = Join-Path $Run 'results.txt'
$utf8 = New-Object Text.UTF8Encoding($true); $utf8n = New-Object Text.UTF8Encoding($false)
$script:pass = 0; $script:fail = 0
function Note([string]$s) { Write-Host $s; [IO.File]::AppendAllText($Log, $s + "`r`n", $utf8) }
function Check([string]$id, [string]$what, [bool]$ok, [string]$info = '') { if ($ok) { $script:pass++; Note ("PASS $id $what") } else { $script:fail++; Note ("FAIL $id $what  $info") } }
function Sha([string]$p) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower() }
function Want([string]$s) { return ($Only.Count -eq 0 -or $Only -contains $s) }
function CountPairs([string]$t) { return ([regex]::Matches($t, '[0-9a-f]{64},[0-9a-f]{64}')).Count }
if ($env:COMPUTERNAME -ne 'DESKTOP-H5CPN8E') { Note ('ВНИМАНИЕ: имя ПК ' + $env:COMPUTERNAME + ', шаги рассчитаны на DESKTOP-H5CPN8E') }
Remove-Item Env:BB_REGISTRY -ErrorAction SilentlyContinue; Remove-Item Env:BB_KIT_OUT -ErrorAction SilentlyContinue
$R2J = '66f061ecc14445de5901cee8d4dfcd59be98fcaa697b97cbf939a89bd0be9bd3'; $JD2 = 'b89bfb4327a184f5327ae83fa1e84752f0a2deac2a5a6ea5744bbb857072a915'; $JD = 'c1891f2aed397d403ff4214e02f819a439e7607e5dd0078b1e680f9628840996'
$VPE = 'f0dc7c18f2fa24ffd7c9baffd92e8f3dd723c0521c27eedb4eeef408faa8642d'; $CAM = '4a15d6997ff14752e6228b5c55cbc4665428c692b305fc25eb0e8cc26d9e1310'
$L2J = '62be01dbb13305bca321d538690252863dedadb8a376e65e54d9f6c15116bf15'; $L2K = '05af46f88ebf8183473ff4bbc49d97cfc95368b5c546a9033d4cfcc5a8b15002'; $L2JCAM = '5f0954d82ba7b8034e169fa60c99edd8cd501921e923faa5f10f795ccf388294'
$S07R12 = 'a6af97877cc39b1f0de0cb98c1183ce8abc0f56af1ae1c4d83f7472a4a133b07'   # run_07_takeoff.ps1 набора r12 (блок 3c), переносится байт в байт

# ---------- песочница: копия набора без tests, out, _aside, proverka_* (её папка-родитель = «папка проекта» для 07) ----------
$SBP = Join-Path $Run 'sb'; $SB = Join-Path $SBP 'bench_kit_20261117_r13'
Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Kit.Length + 1)
    if ($rel -like 'tests\*' -or $rel -like 'out\*' -or $rel -like '_aside\*' -or $rel -like 'proverka_*' -or $rel -eq 'SHA256SUMS.txt') { return }
    $dest = Join-Path $SB $rel; New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null; Copy-Item -LiteralPath $_.FullName -Destination $dest
}
New-Item -ItemType Directory -Force -Path (Join-Path $SB 'out') | Out-Null
$FakeDir = Join-Path $Run 'fake'; New-Item -ItemType Directory -Path $FakeDir | Out-Null
$FakeExe = Join-Path $FakeDir 'ssh.exe'
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_ssh_r13.cs'))) -OutputAssembly $FakeExe -OutputType ConsoleApplication
$script:FakeSha = Sha $FakeExe
$Marker = 'BB_FAKE_SSH_R13_NO_NETWORK'
$oldPath = $env:PATH; $env:PATH = $FakeDir + ';' + $oldPath
$env:BB_NO_PAUSE = '1'
# ---------- страж: ssh, который найдёт шаг, - подделка ----------
function Has-Marker([string]$p) { $l1 = [Text.Encoding]::GetEncoding(28591); $hay = $l1.GetString([IO.File]::ReadAllBytes($p)); $needle = $l1.GetString([Text.Encoding]::Unicode.GetBytes($Marker)); return $hay.Contains($needle) }
function Guard-Why([string]$src) {
    if (-not $src) { return 'ssh не найден' }
    if ($src -ne $FakeExe) { return ('первый ssh в PATH - не подделка этого прогона: ' + $src) }
    if ((Sha $src) -ne $script:FakeSha) { return ('sha ssh не равен sha собранной подделки: ' + $src) }
    if (-not (Has-Marker $src)) { return ('в ssh нет метки ' + $Marker + ': ' + $src) }
    return ''
}
function Guard-InProc { $c = Get-Command ssh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1; return (Guard-Why $(if ($c) { $c.Source } else { '' })) }
function Guard-Child {
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes('$c = Get-Command ssh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { [Console]::Out.Write($c.Source) }'))
    # отдельный процесс с тем же окружением (PATH), что получит шаг; пустой stdin и -NonInteractive - чтобы дочерний powershell не ждал ввода
    $gi = Join-Path $Run 'guard_empty_stdin.txt'; if (-not (Test-Path -LiteralPath $gi)) { [IO.File]::WriteAllText($gi, '') }
    $go = Join-Path $Run ('guard_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.txt')
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -NonInteractive -EncodedCommand ' + $enc) -NoNewWindow -PassThru -RedirectStandardInput $gi -RedirectStandardOutput $go -RedirectStandardError ($go + '.err')
    $null = $p.Handle
    if (-not $p.WaitForExit(60000)) { try { Stop-Process -Id $p.Id -Force } catch { }; return 'страж: дочерний powershell не ответил за 60 с' }
    $src = ([IO.File]::ReadAllText($go)).Trim()
    return (Guard-Why $src)
}
$script:guardRefusals = 0
function Reset-Fake([string]$mode = 'normal', [string]$exec = '', [string]$shaOut = '') {
    $aside = Join-Path $Run ('fake_state_' + [guid]::NewGuid().ToString('N').Substring(0, 8)); $moved = $false
    foreach ($f in @(Get-ChildItem -LiteralPath $FakeDir -File | Where-Object { $_.Name -notlike 'ssh.*' })) { if (-not $moved) { New-Item -ItemType Directory -Path $aside | Out-Null; $moved = $true }; Move-Item -LiteralPath $f.FullName -Destination $aside }
    [IO.File]::WriteAllText((Join-Path $FakeDir 'mode.txt'), $mode)
    if ($exec) { [IO.File]::WriteAllText((Join-Path $FakeDir 'exec_wsl.txt'), $exec) }
    if ($shaOut) { [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), $shaOut) }
}
function Calls { $cl = Join-Path $FakeDir 'calls.log'; if (Test-Path -LiteralPath $cl) { return @(Get-Content -LiteralPath $cl -Encoding UTF8) } else { return @() } }
function Run-Ps([string]$script, [string]$outDir, [string]$more = '', [switch]$ChildGuard, [switch]$GuardControl) {
    $why = Guard-InProc
    if (-not $why -and $ChildGuard) { $why = Guard-Child }
    if ($why) {
        if (-not $GuardControl) { $script:guardRefusals++; Check 'GUARD' ('страж: ' + $script + ' НЕ запущен - ' + $why) $false '' }
        return @{ Code = -1; Console = ('SSH_GUARD ' + $why); Calls = @(Calls); Secs = 0; Guard = $false }
    }
    if ($outDir) { $env:BB_KIT_OUT = $outDir }
    $so = Join-Path $Run ('c_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.txt')
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $SB $script) + '" ' + $more) -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $sw.Stop(); Remove-Item Env:BB_KIT_OUT -ErrorAction SilentlyContinue
    return @{ Code = $p.ExitCode; Console = ([IO.File]::ReadAllText($so) + [IO.File]::ReadAllText($so + '.err')); Calls = @(Calls); Secs = $sw.Elapsed.TotalSeconds; Guard = $true }
}
function New-OutDir([string]$name) { $o = Join-Path $Run ('out_' + $name); New-Item -ItemType Directory -Path $o -Force | Out-Null; return $o }
function Latest([string]$dir, [string]$filter) { return @(Get-ChildItem -LiteralPath $dir -File -Filter $filter | Where-Object { $_.Name -notmatch '\.generated\.|\.err\.txt$|\.raw\.txt$' } | Sort-Object LastWriteTime) }
function Wsl([string[]]$a) { $ErrorActionPreference = 'Continue'; return (& wsl.exe -e nice -n 19 ionice -c3 @a 2>&1 | Out-String) }
Check 'G0' ('страж: собранная подделка - первый ssh в PATH (в этом процессе и в отдельном powershell), sha ' + $script:FakeSha.Substring(0, 12) + '…, метка ' + $Marker + ' в файле') ((Guard-InProc) -eq '' -and (Guard-Child) -eq '') ((Guard-InProc) + ' | ' + (Guard-Child))

# ---------- WSL: поддельный «дом дрона» ----------
$wslOk = $false; $WB = ''; $ti = ''; $shaW = @{}
if ((Want 'J') -or (Want 'E')) {
    try {
        $kitW = (& wsl.exe -e wslpath -a ($Kit.Replace('\', '/')) | Out-String).Trim()
        $WB = (Wsl @('bash', '-c', 'mktemp -d /tmp/r13pc_XXXXXX')).Trim()
        $ti = Wsl @('bash', ($kitW + '/tests/r13_wsl_tree.sh'), 'init', $WB)
        $wslOk = ($ti -match ('TREE13_OK ' + [regex]::Escape($WB)))
        foreach ($m in [regex]::Matches($ti, '(?m)^(SHA_[A-Z0-9_]+) ([0-9a-f]{64})\s*$')) { $shaW[$m.Groups[1].Value] = $m.Groups[2].Value }
    } catch { $ti = $_.Exception.Message }
    Check 'W0' ('WSL: поддельный дом дрона из образа r2j и детекторов jd2/jd (/work, только чтение) в ' + $WB) $wslOk $ti
}
function Variant([string]$v) { $o = Wsl @('bash', ($kitW + '/tests/r13_wsl_tree.sh'), 'variant', $WB, $v); return ($o -match ('VARIANT13_OK ' + $v + ' ')) }

# ======================= J: 09 и 15, aruco_detect.py r2j ИЛИ jd2 =======================
$r09jd2 = $null; $r09jd = $null
if (Want 'J') {
    $lj = Join-Path $Run 'lists_py.txt'
    $ps = ". '" + (Join-Path $SB 'lib\bb_common.ps1') + "'; . '" + (Join-Path $SB 'lib\bb_lists.ps1') + "'; `$a = BL-PyList '" + $SB + "'; `$b = BL-ApplyJd2Alt '" + $SB + "' (BL-PyList '" + $SB + "'); [IO.File]::WriteAllText('" + $lj + "', ((`$a -join [char]10) + [char]10 + '=====' + [char]10 + (`$b -join [char]10)), (New-Object Text.UTF8Encoding(`$false)))"
    & powershell -NoProfile -ExecutionPolicy Bypass -Command $ps 2>&1 | Out-Null
    $lt = [IO.File]::ReadAllText($lj) -split '====='; $la = @($lt[0].Trim() -split "`n"); $lb = @($lt[1].Trim() -split "`n")
    Check 'J1' 'BL-PyList без изменений: 10 python-узлов «sha256  имя», ни одной строки с запятой, aruco_detect.py = r2j 66f061ec' ($la.Count -eq 10 -and @($la | Where-Object { $_ -match ',' }).Count -eq 0 -and ($la -ccontains ($R2J + '  aruco_detect.py'))) ($la -join ' | ')
    Check 'J2' 'BL-ApplyJd2Alt: те же 10 строк, изменена ровно одна - «66f061ec…,b89bfb43…  aruco_detect.py»; остальные 9 байт в байт как в BL-PyList (vpe_fix.py f0dc7c18, camera_fix.py 4a15d699 - только r2j)' ($lb.Count -eq 10 -and @($lb | Where-Object { $_ -match ',' }).Count -eq 1 -and ($lb -ccontains ($R2J + ',' + $JD2 + '  aruco_detect.py')) -and ($lb -ccontains ($VPE + '  vpe_fix.py')) -and ($lb -ccontains ($CAM + '  camera_fix.py')) -and @(Compare-Object -CaseSensitive @($la | Where-Object { $_ -notmatch 'aruco_detect\.py' }) @($lb | Where-Object { $_ -notmatch 'aruco_detect\.py' })).Count -eq 0) ($lb -join ' | ')
    $tsv = Join-Path $SB 'image_r2j\POSEFIX_JD2_20261117.tsv'
    $rows = @([IO.File]::ReadAllLines($tsv) | Where-Object { $_.Trim() -ne '' -and -not $_.StartsWith('#') })
    Check 'J3' 'список jd2: ровно 1 строка «b89bfb43… TAB aruco_detect.py»; sha = обе копии образа /work/c6_fix_20261117/image_r2jd2 (install и src), прочитано в WSL' ($rows.Count -eq 1 -and $rows[0] -ceq ($JD2 + "`taruco_detect.py") -and $shaW['SHA_JD2'] -ceq $JD2 -and $shaW['SHA_JD2_SRC'] -ceq $JD2) ('WSL: ' + $shaW['SHA_JD2'] + ' / ' + $shaW['SHA_JD2_SRC'])
    $pkgF = Join-Path (Split-Path -Parent $Kit) 'drone_pkg_posefix_jd2_20261117\files\jd2\aruco_detect.py'
    if (-not (Test-Path -LiteralPath $pkgF)) { $pkgF = Join-Path $env:USERPROFILE 'Documents\Claude local\drone_pkg_posefix_jd2_20261117\files\jd2\aruco_detect.py' }
    Check 'J3b' 'файл пакета drone_pkg_posefix_jd2_20261117\files\jd2\aruco_detect.py есть и его sha = строка списка jd2 (то, что ставит пакет, 09 r13 примет)' ((Test-Path -LiteralPath $pkgF) -and (Sha $pkgF) -eq $JD2) ($pkgF + ' ' + $(if (Test-Path -LiteralPath $pkgF) { Sha $pkgF } else { 'нет' }))
    Check 'J3c' 'контроль подделок: детектор r2j в образе = 66f061ec, старый jd (/work/c6_fix_20261117/image_r2jd) = c1891f2a, jd2 не равен ни r2j, ни jd' ($shaW['SHA_R2J'] -ceq $R2J -and $shaW['SHA_JD'] -ceq $JD -and $JD2 -ne $R2J -and $JD2 -ne $JD) (($shaW.Keys | ForEach-Object { $_ + '=' + $shaW[$_] }) -join ' ')
    # сгенерированные скрипты Pi (без связи, ответ «дрона» - заглушка)
    $cn = Join-Path $Run 'canned_min.txt'; [IO.File]::WriteAllText($cn, "BB_RTPY ok=0 diff=0 missing=0`nBB_INSTALL_CHECK ok=0 diff=0 missing=0 noprefix=0 cpp_ok=0 cpp_diff=0 cpp_missing=0 bin_ok=0 bin_missing=0 stale=0`nBB_INSTALL_CHECK_DONE`n", $utf8n)
    Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_install.txt'), $cn)
    $o9 = New-OutDir 'j_gen09'; $r = Run-Ps 'run_install_check.ps1' $o9
    $g9 = @(Get-ChildItem -LiteralPath $o9 -Filter 'install_check_*.generated.sh'); $g9t = $(if ($g9.Count -eq 1) { [IO.File]::ReadAllText($g9[0].FullName) } else { '' })
    $iSha = $g9t.IndexOf('shamatch() {'); $iList = $g9t.IndexOf('while read -r want name; do')
    $others = @($la | Where-Object { $_ -notmatch 'aruco_detect\.py' } | Where-Object { -not $g9t.Contains($_ + "`n") })
    Check 'J4' '09: в скрипте для Pi ровно 3 строки «sha,sha» (2 примера карты real из r11 + детектор jd2), строка «66f061ec…,b89bfb43…  aruco_detect.py», остальные 9 узлов как в r11; launch строго (ни одной «sha,sha» у RT); shamatch определена один раз и ДО цикла узлов; цикл узлов - через shamatch с меткой POSEFIX_JD2; метка REAL_MAP на месте' ($g9.Count -eq 1 -and (CountPairs $g9t) -eq 3 -and $g9t.Contains("`n" + $R2J + ',' + $JD2 + '  aruco_detect.py' + "`n") -and $g9t.Contains("`n" + $L2J + '  LAUNCH  launch/bumblebee.launch.py' + "`n") -and $others.Count -eq 0 -and ([regex]::Matches($g9t, 'shamatch\(\) \{')).Count -eq 1 -and $iSha -gt 0 -and $iSha -lt $iList -and $g9t.Contains('if shamatch "$got" "$want"; then ok=$((ok+1)); vmark=""; [ "$got" = "${want%%,*}" ] || vmark=" POSEFIX_JD2"; echo "INSTALL_FILE $name OK$vmark"') -and $g9t.Contains('vmark=" REAL_MAP"') -and $g9t.Contains('if [ "$got" = "$want" ]; then rtok=$((rtok+1));')) ('code=' + $r.Code + ' pairs=' + (CountPairs $g9t) + ' others=' + ($others -join ','))
    Reset-Fake; $o15 = New-OutDir 'j_gen15'; $r = Run-Ps 'run_fingerprint.ps1' $o15
    $g15 = @(Get-ChildItem -LiteralPath $o15 -Filter 'fingerprint_bumblebee_*.generated.sh'); $g15m = @(Get-ChildItem -LiteralPath $o15 -Filter 'fingerprint_mavros_*.generated.sh')
    $g15t = $(if ($g15.Count -eq 1) { [IO.File]::ReadAllText($g15[0].FullName) } else { '' }); $g15mt = $(if ($g15m.Count -eq 1) { [IO.File]::ReadAllText($g15m[0].FullName) } else { '' })
    $iSha = $g15t.IndexOf('shamatch() {'); $iList = $g15t.IndexOf('while read -r want name; do')
    Check 'J5' '15: в скрипте bumblebee 3 строки «sha,sha» (из них детектор jd2), shamatch один раз и до цикла узлов, цикл PY_NODE с меткой POSEFIX_JD2; в скрипте MAVROS - ни одной «sha,sha»' ($g15.Count -eq 1 -and (CountPairs $g15t) -eq 3 -and $g15t.Contains("`n" + $R2J + ',' + $JD2 + '  aruco_detect.py' + "`n") -and ([regex]::Matches($g15t, 'shamatch\(\) \{')).Count -eq 1 -and $iSha -gt 0 -and $iSha -lt $iList -and $g15t.Contains('if shamatch "$got" "$want"; then pok=$((pok+1)); vmark=""; [ "$got" = "${want%%,*}" ] || vmark=" POSEFIX_JD2"; echo "PY_NODE $name OK$vmark"') -and $g15m.Count -eq 1 -and (CountPairs $g15mt) -eq 0) ('pairs=' + (CountPairs $g15t))
    # плохой список jd2 -> код 4, к дрону не обращались (09 и 15)
    $keep = [IO.File]::ReadAllText($tsv)
    $bads = @(
        @('имя vpe_fix.py вместо aruco_detect.py', ($JD2 + "`tvpe_fix.py`n")),
        @('имя с путём lib/bumblebee/aruco_detect.py', ($JD2 + "`tlib/bumblebee/aruco_detect.py`n")),
        @('имя другим регистром Aruco_detect.py', ($JD2 + "`tAruco_detect.py`n")),
        @('две строки aruco_detect.py (jd2 и jd)', ($JD2 + "`taruco_detect.py`n" + $JD + "`taruco_detect.py`n")),
        @('вторая строка с другим именем', ($JD2 + "`taruco_detect.py`n" + $JD2 + "`tcamera_fix.py`n")),
        @('не 64 hex', ("XYZ`taruco_detect.py`n")),
        @('sha заглавными буквами', ($JD2.ToUpper() + "`taruco_detect.py`n")),
        @('sha из 63 знаков', ($JD2.Substring(1) + "`taruco_detect.py`n")),
        @('sha jd2 = sha r2j', ($R2J + "`taruco_detect.py`n")),
        @('пустой (только комментарии)', "# пусто`n"),
        @('три колонки', ($JD2 + "`taruco_detect.py`textra`n")),
        @('пробелы вместо TAB', ($JD2 + "  aruco_detect.py`n"))
    )
    foreach ($b in $bads) {
        [IO.File]::WriteAllText($tsv, $b[1], $utf8n)
        foreach ($s in @(@('09', 'run_install_check.ps1'), @('15', 'run_fingerprint.ps1'))) {
            Reset-Fake; $r = Run-Ps $s[1] (New-OutDir ('j_bad_' + [guid]::NewGuid().ToString('N').Substring(0, 6)))
            Check 'J6' ($s[0] + ': в списке jd2 ' + $b[0] + ': код 4, к дрону не обращались') ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'СТОП') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
        }
    }
    $tsvAside = Join-Path $Run 'tsv_aside'; New-Item -ItemType Directory -Path $tsvAside | Out-Null; Move-Item -LiteralPath $tsv -Destination $tsvAside
    foreach ($s in @(@('09', 'run_install_check.ps1'), @('15', 'run_fingerprint.ps1'))) {
        Reset-Fake; $r = Run-Ps $s[1] (New-OutDir ('j_notsv_' + $s[0]))
        Check 'J6b' ($s[0] + ': нет файла списка jd2 - код 4, к дрону не обращались') ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
    }
    [IO.File]::WriteAllText($tsv, $keep, $utf8n)
    # список python-узлов r2j с двумя строками aruco_detect.py или без неё -> код 4
    $inst = Join-Path $SB 'image_r2j\INSTALL_SHA256_r2j.txt'; $keepInst = [IO.File]::ReadAllText($inst); $instRows = @([IO.File]::ReadAllLines($inst))
    $badInst = @(
        @('две строки aruco_detect.py', ((@($instRows) + @($R2J + '  aruco_detect.py')) -join "`n") + "`n"),
        @('нет строки aruco_detect.py', ((@($instRows | Where-Object { $_ -notmatch 'aruco_detect\.py' })) -join "`n") + "`n")
    )
    foreach ($b in $badInst) {
        [IO.File]::WriteAllText($inst, $b[1], $utf8n)
        foreach ($s in @(@('09', 'run_install_check.ps1'), @('15', 'run_fingerprint.ps1'))) {
            Reset-Fake; $r = Run-Ps $s[1] (New-OutDir ('j_inst_' + [guid]::NewGuid().ToString('N').Substring(0, 6)))
            Check 'J6c' ($s[0] + ': в списке узлов r2j ' + $b[0] + ': код 4, к дрону не обращались (нужна ровно одна строка aruco_detect.py)') ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'aruco_detect\.py') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
        }
    }
    [IO.File]::WriteAllText($inst, $keepInst, $utf8n)
    Check 'J6d' 'после плохих списков списки песочницы восстановлены байт в байт (как в наборе)' ((Sha $inst) -eq (Sha (Join-Path $Kit 'image_r2j\INSTALL_SHA256_r2j.txt')) -and (Sha $tsv) -eq (Sha (Join-Path $Kit 'image_r2j\POSEFIX_JD2_20261117.tsv'))) ''
    # сквозная цепочка: ПК -> подделка ssh -> настоящий install_check.sh в WSL на доме дрона -> вердикт ПК
    if ($wslOk) {
        $cases = @(
            @('r2j', 0, 'детектор r2j: код 0, # VERDICT OK, метки POSEFIX_JD2 нет', @('INSTALL_FILE aruco_detect.py OK' + "`n"), @('POSEFIX_JD2')),
            @('jd2', 0, 'детектор jd2: код 0, # VERDICT OK, «INSTALL_FILE aruco_detect.py OK POSEFIX_JD2», vpe_fix.py OK без метки, строка ПК «POSEFIX_JD2: детектор меток варианта jd2 вместо r2j»', @('INSTALL_FILE aruco_detect.py OK POSEFIX_JD2', 'INSTALL_FILE vpe_fix.py OK' + "`n", 'POSEFIX_JD2: детектор меток варианта jd2 вместо r2j'), @('REAL_MAP', 'R2K_CAM')),
            @('jd2_real', 0, 'jd2 + карта real: код 0, # VERDICT OK, обе метки (1 POSEFIX_JD2, 2 REAL_MAP)', @('INSTALL_FILE aruco_detect.py OK POSEFIX_JD2', 'flight_marker.py OK - REAL_MAP', 'flight_marker_loop.py OK - REAL_MAP', 'POSEFIX_JD2: детектор меток варианта jd2'), @()),
            @('jd', 5, 'старый детектор jd (c1891f2a): код 5, СТОП, «DIFF got=c1891f2a want=r2j,jd2»', @(('INSTALL_FILE aruco_detect.py DIFF got=' + $JD + ' want=' + $R2J + ',' + $JD2), 'СТОП'), @('OK POSEFIX_JD2')),
            @('jd2_as_vpe', 5, 'файл jd2 под именем vpe_fix.py: код 5, СТОП, vpe_fix.py DIFF (want только r2j), aruco_detect.py r2j OK без метки', @(('INSTALL_FILE vpe_fix.py DIFF got=' + $JD2 + ' want=' + $VPE), 'INSTALL_FILE aruco_detect.py OK' + "`n"), @('POSEFIX_JD2')),
            @('jd2_as_cam', 5, 'файл jd2 под именем camera_fix.py: код 5, СТОП, camera_fix.py DIFF', @(('INSTALL_FILE camera_fix.py DIFF got=' + $JD2 + ' want=' + $CAM)), @('POSEFIX_JD2')),
            @('jd2_r2k', 5, 'jd2 + launch r2k (05af46f8): код 5 - r13 r2k НЕ принимает (как r11), aruco_detect.py при этом OK POSEFIX_JD2', @(('RT_FILE LAUNCH launch/bumblebee.launch.py DIFF got=' + $L2K + ' want=' + $L2J), 'INSTALL_FILE aruco_detect.py OK POSEFIX_JD2'), @('R2K_CAM')),
            @('jd2_r2jcam', 5, 'jd2 + launch r2j_cam: код 5 (строгость launch из r11)', @(('RT_FILE LAUNCH launch/bumblebee.launch.py DIFF got=' + $L2JCAM + ' want=' + $L2J)), @()),
            @('jd2_fcu_old', 5, 'jd2 + прежний fcu_detect.py: код 5, как в r11', @('RT_FILE FCU ros2_ws/src/bumblebee/scripts/fcu_detect.py DIFF got='), @())
        )
        foreach ($c in $cases) {
            $vok = Variant $c[0]; Reset-Fake 'normal' ($WB + '/runner13.sh'); $o = New-OutDir ('j_chain09_' + $c[0]); $r = Run-Ps 'run_install_check.ps1' $o
            $f = @(Latest $o 'install_check_*.txt'); $ft = $(if ($f.Count -eq 1) { [IO.File]::ReadAllText($f[-1].FullName) -replace "`r`n", "`n" } else { '' }); $last = $(if ($ft) { @($ft.Trim() -split "`n")[-1].Trim() } else { '' })
            $both = $ft + "`n" + ($r.Console -replace "`r`n", "`n")
            $ok = $vok -and $r.Guard -and $r.Code -eq $c[1] -and $last -ceq $(if ($c[1] -eq 0) { '# VERDICT OK' } else { '# VERDICT NOT_OK' })
            $miss = @(); foreach ($m in $c[3]) { if (-not $both.Contains($m)) { $ok = $false; $miss += $m } }
            foreach ($m in $c[4]) { if ($both.Contains($m)) { $ok = $false; $miss += ('лишнее ' + $m) } }
            if ($c[0] -eq 'jd2') { $ok = $ok -and ([regex]::Matches($ft, ' POSEFIX_JD2')).Count -eq 1 }
            if ($c[0] -eq 'jd2_real') { $ok = $ok -and ([regex]::Matches($ft, ' REAL_MAP')).Count -eq 2 -and ([regex]::Matches($ft, ' POSEFIX_JD2')).Count -eq 1 }
            Check 'J7' ('09 сквозная (WSL, ' + $c[0] + '): ' + $c[2]) $ok ('variant=' + $vok + ' code=' + $r.Code + ' last=' + $last + ' нет/лишнее: ' + ($miss -join ' ; ') + ' | ' + (($ft -split "`n" | Where-Object { $_ -match '^INSTALL_FILE|^RT_FILE.*(DIFF|MISSING)|^BB_INSTALL_CHECK |^CPP_SRC.*(DIFF|MISSING)' }) -join ' | '))
            if ($c[0] -eq 'jd2' -and $ok) { $r09jd2 = $f[-1].FullName }
            if ($c[0] -eq 'jd' -and $ok) { $r09jd = $f[-1].FullName }
        }
        foreach ($c in @('jd2', 'jd', 'jd2_as_vpe', 'jd2_real', 'r2j')) {
            $vok = Variant $c; Reset-Fake 'normal' ($WB + '/runner13.sh'); $o = New-OutDir ('j_chain15_' + $c); $r = Run-Ps 'run_fingerprint.ps1' $o
            $fb = @(Get-ChildItem -LiteralPath $o -Filter 'fingerprint_bumblebee_*.txt' | Where-Object { $_.Name -notmatch '\.raw\.|\.err\.' }); $fbt = $(if ($fb.Count -eq 1) { [IO.File]::ReadAllText($fb[0].FullName) } else { '' })
            $info = ('variant=' + $vok + ' code=' + $r.Code + ' ' + (($fbt -split "`r?`n" | Where-Object { $_ -match '^# (VERDICT|PY_NODE .*(DIFF|MISSING|POSEFIX))' }) -join ' | '))
            switch ($c) {
                'jd2' { Check 'J8' '15 сквозная (WSL, jd2): код 0, отпечатки bumblebee «# VERDICT OK», «PY_NODE aruco_detect.py OK POSEFIX_JD2» в файле и на экране, vpe_fix.py без метки; MAVROS не собран - пропущен' ($vok -and $r.Code -eq 0 -and $fbt -match '(?m)^# VERDICT OK' -and $fbt.Contains('# PY_NODE aruco_detect.py OK POSEFIX_JD2') -and ([regex]::Matches($fbt, 'POSEFIX_JD2')).Count -eq 1 -and $r.Console.Contains('PY_NODE aruco_detect.py OK POSEFIX_JD2') -and $fbt -match '(?m)^# PY_NODE vpe_fix\.py OK\r?$' -and $r.Console -match 'mavros: оверлей не собран') $info }
                'jd' { Check 'J8' '15 сквозная (WSL, jd): код 5, «# VERDICT NOT_OK», «PY_NODE aruco_detect.py DIFF got=c1891f2a… want=r2j,jd2»' ($vok -and $r.Code -eq 5 -and $fbt -match '(?m)^# VERDICT NOT_OK' -and $fbt.Contains('# PY_NODE aruco_detect.py DIFF got=' + $JD + ' want=' + $R2J + ',' + $JD2) -and -not $fbt.Contains('OK POSEFIX_JD2')) $info }
                'jd2_as_vpe' { Check 'J8' '15 сквозная (WSL, jd2 под именем vpe_fix.py): код 5, «# VERDICT NOT_OK», PY_NODE vpe_fix.py DIFF' ($vok -and $r.Code -eq 5 -and $fbt -match '(?m)^# VERDICT NOT_OK' -and $fbt.Contains('# PY_NODE vpe_fix.py DIFF got=' + $JD2 + ' want=' + $VPE)) $info }
                'jd2_real' { Check 'J8' '15 сквозная (WSL, jd2 + карта real): код 0, «# VERDICT OK», метки POSEFIX_JD2 и 2 REAL_MAP в файле' ($vok -and $r.Code -eq 0 -and $fbt -match '(?m)^# VERDICT OK' -and $fbt.Contains('# PY_NODE aruco_detect.py OK POSEFIX_JD2') -and ([regex]::Matches($fbt, ' REAL_MAP')).Count -eq 2) $info }
                default { Check 'J8' '15 сквозная (WSL, r2j): код 0, «# VERDICT OK», метки POSEFIX_JD2 нет' ($vok -and $r.Code -eq 0 -and $fbt -match '(?m)^# VERDICT OK' -and -not $fbt.Contains('POSEFIX_JD2') -and -not $r.Console.Contains('POSEFIX_JD2')) $info }
            }
        }
        $null = Variant 'r2j'
    }
    # кто ещё смотрит sha aruco_detect.py: список jd2 они не берут (строго как в r11)
    $notTouched = @('run_bb_build.ps1', 'pi\bb_build.sh', 'pi\bb_build_precheck.sh', 'run_r6_install_check_cam.ps1', 'run_r6_fingerprint_cam.ps1', 'lib\bb_lists_r2jcam.ps1', 'run_r6_camverify.ps1', 'pi\r6_cam_verify.sh', 'run_r6_cost.ps1', 'pi\r6_cost_phase.sh', 'image_r2j\check_gates.ps1', 'image_r2j\image_install.sh', 'image_r2j\image_rollback.sh', 'image_r2j_cam\check_gates_r2j_cam.ps1', 'image_r2j_cam\run_r6_cam_install.ps1', 'run_07_takeoff.ps1', 'image_r2j\INSTALL_SHA256_r2j.txt', 'image_r2j_cam\INSTALL_SHA256_r2jcam.txt', 'image_r2j\PAYLOAD_SOURCES_r2j.tsv', 'image_r2j\image_manifest.final.tsv')
    $leak = @($notTouched | Where-Object { $t9 = [IO.File]::ReadAllText((Join-Path $SB $_)); $t9 -match 'BL-ApplyJd2Alt|POSEFIX_JD2|b89bfb43' })
    Check 'J9' 'сборка 13, 09c/15c, 22, 24a/24b, гейты и установка/откат 05/06/05c, 07, списки r2j и r2j_cam список jd2 не берут (строго как в r11)' ($leak.Count -eq 0) ($leak -join ', ')
    Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_install.txt'), $cn)
    $o9c = New-OutDir 'j_gen09c'; $r = Run-Ps 'run_r6_install_check_cam.ps1' $o9c
    $g9c = @(Get-ChildItem -LiteralPath $o9c -Filter 'sverka_r2jcam_*.generated.sh'); $g9ct = $(if ($g9c.Count -eq 1) { [IO.File]::ReadAllText($g9c[0].FullName) } else { '' })
    Check 'J9b' '09c (вариант r2j_cam): в скрипте для Pi ни одной строки «sha,sha», aruco_detect.py только r2j 66f061ec - детектор jd2 там даст DIFF (как в r11)' ($g9c.Count -eq 1 -and (CountPairs $g9ct) -eq 0 -and $g9ct.Contains("`n" + $R2J + '  aruco_detect.py' + "`n") -and -not $g9ct.Contains($JD2)) ('code=' + $r.Code + ' generated=' + $g9c.Count)
}

# ======================= E: 07, блок 3c из r12 (журналы пакетов drone_pkg_*) =======================
if (Want 'E') {
    $p07 = Join-Path $SB 'run_07_takeoff.ps1'; $t07 = [IO.File]::ReadAllText($p07)
    $conf = Join-Path $SB 'takeoff.conf'; $gate = Join-Path $SB 'gates\TAKEOFF_APPROVED.txt'
    $cf = @{}; foreach ($l in [IO.File]::ReadAllLines($conf)) { $t9 = $l.Trim(); if ($t9 -eq '' -or $t9.StartsWith('#')) { continue }; $i = $t9.IndexOf('='); if ($i -gt 0) { $cf[$t9.Substring(0, $i).Trim()] = $t9.Substring($i + 1).Trim() } }
    [IO.File]::WriteAllText($gate, ("ШАГ=14`r`nВЗЛЁТ_РАЗРЕШИЛ=владелец`r`nДАТА=2026-11-17 тест`r`nСЛОВА_ВЛАДЕЛЬЦА=тест r13`r`nСКРИПТ_SHA256=" + $cf['SCRIPT_SHA256'] + "`r`nАРГУМЕНТЫ=`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
    $strict = '=== СОВПАДАЕТ: прочитано 1127 из 1127, отличий нет (из таблицы MAVROS 1127, из запасного потока 0) ==='
    function New-Out07([string]$name, [int]$age09 = 5, [int]$age10 = 5, [string]$from09 = '') {
        $o = New-OutDir ('e_' + $name)
        $rp = Join-Path $o 'params_bench_t_report.txt'; [IO.File]::WriteAllText($rp, $strict + "`r`n", $utf8)
        $c9 = Join-Path $o 'install_check_20261117_080000.txt'
        if ($from09) { Copy-Item -LiteralPath $from09 -Destination $c9 } else { [IO.File]::WriteAllText($c9, "BB_INSTALL_CHECK_DONE`r`n# VERDICT OK`r`n", $utf8) }
        (Get-Item -LiteralPath $c9).LastWriteTime = (Get-Date).AddMinutes(-$age09)
        $c10 = Join-Path $o 'mavros_check_20261117_080000.txt'; [IO.File]::WriteAllText($c10, "BB_DONE`r`n# VERDICT OK`r`n", $utf8); (Get-Item -LiteralPath $c10).LastWriteTime = (Get-Date).AddMinutes(-$age10)
        return $o
    }
    $script:asideN = 0
    function Clear-Pkgs { $script:asideN++; $a = Join-Path $Run ('pkg_aside_' + $script:asideN); foreach ($d in @(Get-ChildItem -LiteralPath $SBP -Directory | Where-Object { $_.Name -like 'drone_pkg_*' })) { if (-not (Test-Path $a)) { New-Item -ItemType Directory -Path $a | Out-Null }; Move-Item -LiteralPath $d.FullName -Destination $a } }
    function Pkg-File([string]$pkg, [string]$name, [double]$ageMin) { $d = Join-Path $SBP ($pkg + '\out'); New-Item -ItemType Directory -Force -Path $d | Out-Null; $f = Join-Path $d $name; [IO.File]::WriteAllText($f, "тест`r`n", $utf8); (Get-Item -LiteralPath $f).LastWriteTime = (Get-Date).AddMinutes(-$ageMin); return $f }
    $badSha = ('cd' * 32) + '  ' + $cf['SCRIPT_REMOTE_PATH']
    # 07 запускается только после стража (в этом процессе и в отдельном powershell); подделка отвечает на «sha256sum» чужой суммой - 07 останавливается до взлёта
    function Run07([string]$o) { Reset-Fake 'normal' '' $badSha; return (Run-Ps 'run_07_takeoff.ps1' $o '-SafetyConfirmed NET-TWO-KILL-YES' -ChildGuard) }
    function Passed($r) { return ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -ge 2 -and $r.Console -match 'sha256 не равен' -and $r.Console -notmatch 'взлёт не разрешён' -and @($r.Calls | Where-Object { $_ -notmatch [regex]::Escape($Marker) }).Count -eq 0) }
    function Refused($r, [string]$what) { return ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'взлёт не разрешён' -and $r.Console -match 'ДО последней установки или отката пакета на дрон' -and $r.Console.Contains($what)) }
    Check 'E0' '07 r13 = run_07_takeoff.ps1 r12 байт в байт (r11 + блок 3c, sha a6af9787…); условия r11 на месте, 3c только для 09' ((Sha $p07) -eq $S07R12 -and $t07.Contains("`$_.Name -match '^(overlay_connect_|overlay_disconnect_|bb_build_|bb_aside_|mavros_build_|mavros_aside_|install_r2j_|rollback_r2j_|install_camera_dabd5076_)'") -and $t07.Contains("if (`$kind[0] -eq 'install_check' -and `$pkgLast -and `$lastChk.LastWriteTime -le `$pkgLast.Time)") -and $t07.Contains("-Filter 'drone_pkg_*'")) (Sha $p07)
    Clear-Pkgs; $r = Run07 (New-Out07 'e1_none'); Check 'E1' '07: пакетов рядом нет - условия пройдены, 07 дошёл до подделки (сверка sha, отказ только из-за sha); все вызовы ssh - с меткой подделки' (Passed $r) ('code=' + $r.Code + ' calls=' + $r.Calls.Count + ' ' + $r.Console)
    $ev = @(
        @('E2', 'drone_pkg_posefix_jd2_20261117', 'posefix_jd2_install_20261117_120000.log', 'установка jd2 (42)'),
        @('E3', 'drone_pkg_posefix_jd2_20261117', 'posefix_jd2_rollback_20261117_120000.log', 'откат jd2 (43)'),
        @('E4', 'drone_pkg_posefix_20261117', 'posefix_install_20261117_120000.log', 'установка posefix (40)'),
        @('E5', 'drone_pkg_posefix_20261117', 'posefix_rollback_20261117_120000.log', 'откат posefix (41)'),
        @('E6', 'drone_pkg_real_20261117', 'map_real_install_20261117_120000.log', 'установка карты real (30)'),
        @('E7', 'drone_pkg_real_20261117', 'map_real_rollback_20261117_120000.log', 'откат карты real (31)'),
        @('E8', 'drone_pkg_r2k_cam_20261117', 'r2k_cam_install_20261117_120000.log', 'установка r2k_cam (50)'),
        @('E9', 'drone_pkg_future_20261120', 'x_install_20261120_120000.log', 'будущий пакет drone_pkg_* (не из списка)')
    )
    foreach ($e in $ev) {
        Clear-Pkgs; $null = Pkg-File $e[1] $e[2] 2; $r = Run07 (New-Out07 $e[0])
        Check $e[0] ('07: ' + $e[3] + ' через 3 мин ПОСЛЕ 09 - код 4 до подделки ssh, причина «09 сделана ДО … пакета» с именем журнала') (Refused $r ($e[1] + '\out\' + $e[2])) ('code=' + $r.Code + ' calls=' + $r.Calls.Count + ' ' + $r.Console)
    }
    Clear-Pkgs; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_install_20261117_070000.log' 30; $null = Pkg-File 'drone_pkg_posefix_20261117' 'posefix_install_20261117_070000.log' 40; $null = Pkg-File 'drone_pkg_real_20261117' 'map_real_install_20261117_070000.log' 50
    $r = Run07 (New-Out07 'e10_older'); Check 'E10' '07: журналы трёх пакетов СТАРШЕ 09 - условия пройдены (до подделки)' (Passed $r) ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_install_20261117_070000.log' 30; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_install_20261117_070000.txt' 2
    $r = Run07 (New-Out07 'e11_sib'); Check 'E11' '07: .log пакета старше 09, но вывод того же запуска (.txt) новее 09 - код 4 (время события = самый поздний файл запуска)' (Refused $r 'drone_pkg_posefix_jd2_20261117\out\posefix_jd2_install_20261117_070000.log') ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'README.md' 1; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_note.txt' 1
    $r = Run07 (New-Out07 'e12_nolog'); Check 'E12' '07: в out пакета новее 09 только файлы без журнала .log - не событие, условия пройдены' (Passed $r) ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $o = New-Out07 'e13_eq'; $f9 = Join-Path $o 'install_check_20261117_080000.txt'; $lg = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_install_20261117_080000.log' 0; (Get-Item -LiteralPath $lg).LastWriteTime = (Get-Item -LiteralPath $f9).LastWriteTime
    $r = Run07 $o; Check 'E13' '07: журнал пакета с тем же временем, что 09 - код 4 (09 должна быть строго позже)' (Refused $r 'posefix_jd2_install_20261117_080000.log') ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $o = New-Out07 'e14_kitout'; $f = Join-Path $o 'posefix_jd2_install_20261117_120000.log'; [IO.File]::WriteAllText($f, "тест`r`n", $utf8); (Get-Item -LiteralPath $f).LastWriteTime = (Get-Date).AddMinutes(-2)
    $r = Run07 $o; Check 'E14' '07: журнал пакета jd2 попал в out набора (BB_KIT_OUT) и он новее 09 - код 4' (Refused $r 'out\posefix_jd2_install_20261117_120000.log') ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $o = New-Out07 'e15_takeofflog'; $f = Join-Path $o 'takeoff_20261117_120000.log'; [IO.File]::WriteAllText($f, "тест`r`n", $utf8); (Get-Item -LiteralPath $f).LastWriteTime = (Get-Date).AddMinutes(-2)
    $r = Run07 $o; Check 'E15' '07: свой журнал взлёта takeoff_*.log в out новее 09 - не событие пакета, условия пройдены' (Passed $r) ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_install_20261117_120000.log' 10
    $r = Run07 (New-Out07 'e16_10old' 5 20); Check 'E16' '07: 09 после пакета, 10 (MAVROS) до пакета - условия пройдены (пакеты MAVROS не трогают)' (Passed $r) ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_install_20261117_120000.log' 10
    $r = Run07 (New-Out07 'e17_old09' 20 5); Check 'E17' '07: 10 после пакета, а 09 до него - код 4' (Refused $r 'posefix_jd2_install_20261117_120000.log') ('code=' + $r.Code + ' ' + $r.Console)
    if ($r09jd2) {
        Clear-Pkgs; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_install_20261117_070000.log' 30
        $r = Run07 (New-Out07 'e18_real09' 5 5 $r09jd2); Check 'E18' '07: настоящий отчёт 09 r13 со строкой POSEFIX_JD2 (из J7, «# VERDICT OK»), сделан после установки jd2 - условия пройдены (до подделки)' (Passed $r) ('code=' + $r.Code + ' ' + $r.Console)
        Clear-Pkgs; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_install_20261117_120000.log' 2
        $r = Run07 (New-Out07 'e19_real09_late' 5 5 $r09jd2); Check 'E19' '07: тот же настоящий отчёт 09 r13, но журнал установки jd2 позже него - код 4' (Refused $r 'posefix_jd2_install_20261117_120000.log') ('code=' + $r.Code + ' ' + $r.Console)
    }
    elseif (-not (Want 'J')) { Note 'E18, E19 пропущены: раздел J (источник настоящего отчёта 09 r13) не запускался' }
    else { Check 'E18' 'нет настоящего отчёта 09 r13 с jd2 (J7 jd2 не прошёл)' $false '' }
    if ($r09jd) {
        Clear-Pkgs; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_install_20261117_070000.log' 30
        $r = Run07 (New-Out07 'e20_jd09' 5 5 $r09jd); Check 'E20' '07: настоящий отчёт 09 r13 со старым детектором jd («# VERDICT NOT_OK») - код 4 до подделки, «не успешна»' ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'не успешна') ('code=' + $r.Code + ' ' + $r.Console)
    }
    elseif (-not (Want 'J')) { Note 'E20 пропущен: раздел J (источник настоящего отчёта 09 r13) не запускался' }
    else { Check 'E20' 'нет настоящего отчёта 09 r13 с jd (J7 jd не прошёл)' $false '' }
    Clear-Pkgs; Move-Item -LiteralPath $gate -Destination (Join-Path $Run 'gate_aside_TAKEOFF_APPROVED.txt')
}

# ======================= G: страж сам отказывает, если ssh - не подделка (контроль) =======================
if (Want 'G') {
    $stubSrc = 'using System; using System.IO; public static class StubSshNoMarker { public static int Main(string[] a) { File.AppendAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "stub_called.txt"), DateTime.Now.ToString("s") + Environment.NewLine); Console.Error.WriteLine("stub ssh"); return 255; } }'
    $stubDir = Join-Path $Run 'stub_bez_metki'; New-Item -ItemType Directory -Path $stubDir | Out-Null; $stubExe = Join-Path $stubDir 'ssh.exe'
    Add-Type -TypeDefinition $stubSrc -OutputAssembly $stubExe -OutputType ConsoleApplication
    $gate = Join-Path $SB 'gates\TAKEOFF_APPROVED.txt'
    # 1) заглушка без метки раньше подделки в PATH
    $env:PATH = $stubDir + ';' + $FakeDir + ';' + $oldPath
    $og = New-OutDir 'g_path'; $r = Run-Ps 'run_07_takeoff.ps1' $og '-SafetyConfirmed NET-TWO-KILL-YES' -ChildGuard -GuardControl
    $env:PATH = $FakeDir + ';' + $oldPath
    $okG1 = (-not $r.Guard) -and $r.Code -eq -1 -and $r.Console -match 'не подделка' -and -not (Test-Path -LiteralPath (Join-Path $stubDir 'stub_called.txt')) -and @(Get-ChildItem -LiteralPath $og -Force).Count -eq 0
    Check 'G1' 'контроль стража: «настоящий» ssh-заглушка без метки стоит в PATH раньше подделки - страж отказал, run_07 НЕ запускался (заглушка не вызывалась, out пуст)' $okG1 ($r.Console)
    # 2) подделку подменили заглушкой на том же месте
    $fakeKeep = Join-Path $Run 'fake_keep_ssh.exe'; Copy-Item -LiteralPath $FakeExe -Destination $fakeKeep; Copy-Item -LiteralPath $stubExe -Destination $FakeExe -Force
    $og = New-OutDir 'g_swap'; $r = Run-Ps 'run_07_takeoff.ps1' $og '-SafetyConfirmed NET-TWO-KILL-YES' -ChildGuard -GuardControl
    $okG2 = (-not $r.Guard) -and $r.Code -eq -1 -and $r.Console -match 'sha ssh не равен' -and -not (Test-Path -LiteralPath (Join-Path $FakeDir 'stub_called.txt')) -and @(Get-ChildItem -LiteralPath $og -Force).Count -eq 0
    Check 'G2' 'контроль стража: на месте подделки лежит заглушка без метки (другой sha) - страж отказал, run_07 НЕ запускался' $okG2 ($r.Console)
    Copy-Item -LiteralPath $fakeKeep -Destination $FakeExe -Force
    Check 'G3' 'после контроля подделка возвращена: страж снова пропускает (sha и метка на месте)' ((Guard-InProc) -eq '' -and (Guard-Child) -eq '' -and (Sha $FakeExe) -eq $script:FakeSha) ''
    Check 'G4' 'страж за весь прогон не отказал ни разу, кроме двух контрольных (G1, G2)' ($script:guardRefusals -eq 0) ('отказов: ' + $script:guardRefusals)
}

# ======================= C: .cmd =======================
if (Want 'C') {
    $cmds = @(Get-ChildItem -LiteralPath $Kit -Filter '*.cmd' -File)
    $badCmd = @($cmds | Where-Object { $l = @([IO.File]::ReadAllLines($_.FullName, [Text.Encoding]::UTF8)); -not ($l.Count -ge 3 -and $l[0] -eq '@echo off' -and $l[2] -match '^echo (ТОЛЬКО ЧТЕНИЕ|МЕНЯЕТ ДРОН)') } | ForEach-Object { $_.Name })
    Check 'C1' ('все .cmd в корне набора (' + $cmds.Count + '): первая выводимая строка - ТОЛЬКО ЧТЕНИЕ или МЕНЯЕТ ДРОН; шага 26 (r12) нет') ($badCmd.Count -eq 0 -and $cmds.Count -eq 32 -and @($cmds | Where-Object { $_.Name -like '26_*' }).Count -eq 0) ($badCmd -join ', ')
}

# ======================= K: r13 = копия r11 + ожидаемые правки =======================
if (Want 'K') {
    $r11 = Join-Path (Split-Path -Parent $Kit) 'bench_kit_20261116_r11'
    if (Test-Path -LiteralPath $r11) {
        $changed = @('lib\bb_lists.ps1', 'run_install_check.ps1', 'run_fingerprint.ps1', 'pi\install_check.sh', 'pi\overlay_fingerprint.sh', 'run_07_takeoff.ps1', 'SHA256SUMS.txt')
        $r11f = @(Get-ChildItem -LiteralPath $r11 -Recurse -File | ForEach-Object { $_.FullName.Substring($r11.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and $_ -notmatch '^tests\\run_[^\\]+\\' })
        $miss = @(); $diff = @(); $same = 0
        foreach ($rel in $r11f) { $k = Join-Path $Kit $rel; if (-not (Test-Path -LiteralPath $k)) { $miss += $rel; continue }; if ((Sha $k) -ne (Sha (Join-Path $r11 $rel))) { if ($changed -notcontains $rel) { $diff += $rel } } else { $same++ } }
        Check 'K1' ('все файлы r11 есть в r13; изменены только ожидаемые 7 (bb_lists, 09, 15, install_check.sh, overlay_fingerprint.sh, 07, SHA256SUMS), байт в байт одинаковых: ' + $same) ($miss.Count -eq 0 -and $diff.Count -eq 0) (($miss + $diff) -join ', ')
        $chg = @($changed | Where-Object { $_ -ne 'SHA256SUMS.txt' -and (Sha (Join-Path $Kit $_)) -ne (Sha (Join-Path $r11 $_)) })
        Check 'K1b' 'все 6 ожидаемых файлов действительно изменены' ($chg.Count -eq 6) ($chg -join ', ')
        $newOk = '^(README_r13\.md|DIFF_r11_r13\.txt|image_r2j\\POSEFIX_JD2_20261117\.tsv|tests\\run_tests_r13\.ps1|tests\\run_tests_r13_pi\.sh|tests\\r13_wsl_tree\.sh|tests\\fake_ssh_r13\.cs|proverka_r13\\.+|tests\\run_[^\\]+\\.+)$'
        $new = @(Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object { $_.FullName.Substring($Kit.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and -not (Test-Path -LiteralPath (Join-Path $r11 $_)) -and $_ -notmatch $newOk })
        Check 'K2' 'новых файлов, кроме ожидаемых (README_r13, DIFF_r11_r13, список jd2, тесты r13, proverka_r13), нет' ($new.Count -eq 0) ($new -join ', ')
        $rd = @('README.md', 'README_r9.md', 'README_r11.md', 'PROGRESS.md') | Where-Object { (Sha (Join-Path $Kit $_)) -ne (Sha (Join-Path $r11 $_)) }
        Check 'K5' 'README.md, README_r9, README_r11 и PROGRESS.md не менялись (байт в байт как в r11)' (@($rd).Count -eq 0) (@($rd) -join ', ')
    }
    else { Check 'K0' 'папка r11 рядом не найдена: сравнение с r11 не сделано' $false $r11 }
    $r2kLeft = @('image_r2j\LAUNCH_R2K_CAM_20261117.tsv', '26_zamer_zaderzhki.cmd', 'run_26_latency.ps1', 'pi\latency_live.sh', 'README_r12.md') | Where-Object { Test-Path -LiteralPath (Join-Path $Kit $_) }
    Check 'K6' 'из r12 взят только блок 3c 07: списка r2k, шага 26, README_r12 в r13 нет; в lib\bb_lists.ps1 нет BL-ApplyR2kAlt, в скриптах Pi нет R2K_CAM' (@($r2kLeft).Count -eq 0 -and -not ([IO.File]::ReadAllText((Join-Path $Kit 'lib\bb_lists.ps1')).Contains('BL-ApplyR2kAlt')) -and -not ([IO.File]::ReadAllText((Join-Path $Kit 'pi\install_check.sh')) + [IO.File]::ReadAllText((Join-Path $Kit 'pi\overlay_fingerprint.sh'))).Contains('R2K_CAM')) (@($r2kLeft) -join ', ')
    Check 'K3' 'gates\: TAKEOFF_APPROVED.txt и OVERLAY_*_APPROVED.txt нет; image_r2j\gates\S2_S3_PASSED.txt нет' (-not (Test-Path (Join-Path $Kit 'gates\TAKEOFF_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'gates\OVERLAY_MAVROS_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'gates\OVERLAY_BUMBLEBEE_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'image_r2j\gates\S2_S3_PASSED.txt'))) ''
    $outFiles = @(Get-ChildItem -LiteralPath (Join-Path $Kit 'out') -File -ErrorAction SilentlyContinue)
    Check 'K4' 'out\ набора r13 пуст (тесты пишут только в tests\run_r13_*)' ($outFiles.Count -eq 0) (($outFiles | ForEach-Object { $_.Name }) -join ', ')
}

$env:PATH = $oldPath
Note ''
Note ('WSL-песочница: ' + $WB + ' (не удалялась)')
Note ('ИТОГ r13: PASS ' + $script:pass + ', FAIL ' + $script:fail)
exit $script:fail
