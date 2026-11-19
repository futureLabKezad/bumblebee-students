# run_tests_r14.ps1 (Claude, 17.11.2026, набор r14 = r13 + камера r2m_cam в 09/15) - тесты НОВОГО в r14 на ПК, в песочнице. К дрону не подключается.
# Вместо ssh - подделка tests\fake_ssh_r13.cs (из r13, без изменений; сеть не открывает; для сквозных проверок подаёт скрипт Pi в WSL на поддельный «дом дрона» tests\r14_wsl_tree.sh).
# СТРАЖ (как в r13): перед КАЖДЫМ запуском шага тест сам проверяет, что ssh, который найдёт BB-FindSsh, - подделка (путь, sha, метка BB_FAKE_SSH_R13_NO_NETWORK);
#   для 07 - ещё и в отдельном процессе powershell с тем же окружением. Иначе шаг НЕ запускается, тест - FAIL. Раздел G сам подменяет подделку заглушкой без метки и проверяет отказ.
# R: 09 и 15 принимают камеру r2m_cam вторым значением только для camera_fix.py (e133481d…) и launch/bumblebee.launch.py (5c867929…), метка R2M_CAM; оба файла одного варианта;
#    сочетания с jd2 (r2j+r2j, jd2+r2j, r2j+r2m_cam, jd2+r2m_cam) допустимы; всё прочее строго; плохой список r2m_cam - код 4 без ssh.
# E: 07 (блок 3c из r12, без изменений) видит журналы пакета r2m_cam (шаги 44/45). C: .cmd. K: r14 = копия r13 + только ожидаемые правки.
# Всё WSL - с nice -n 19 ionice -c3; тест и его дочерние процессы - с пониженным приоритетом (BelowNormal).
# Запуск: powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_tests_r14.ps1 [-Only R,E,G,C,K]. Итог: «ИТОГ r14: PASS n, FAIL m».
param([string[]]$Only = @())
$ErrorActionPreference = 'Stop'
$Only = @($Only | ForEach-Object { $_ -split ',' } | Where-Object { $_ -ne '' })   # -File передаёт «E,G» одной строкой
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
try { [Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'BelowNormal' } catch { }
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$Run = Join-Path $T ('run_r14_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
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
$VPE = 'f0dc7c18f2fa24ffd7c9baffd92e8f3dd723c0521c27eedb4eeef408faa8642d'; $CAM = '4a15d6997ff14752e6228b5c55cbc4665428c692b305fc25eb0e8cc26d9e1310'; $CAMM = 'e133481dd3c46bb49691bd40716a08b3e2418e3ab80acc7118569c7a8d74d7e1'
$CAMJC = 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83'
$L2J = '62be01dbb13305bca321d538690252863dedadb8a376e65e54d9f6c15116bf15'; $L2M = '5c867929421f7b5fa4d8f4a6d4816258afe7d0d9e196c04a612ee9a97b4ca483'; $L2K = '05af46f88ebf8183473ff4bbc49d97cfc95368b5c546a9033d4cfcc5a8b15002'
$LMAIN = 'c11080f1daaf3eb7e0d849032e036cb971ed0f4cbb2dfc52f3f45c38027842dc'
$S07R12 = 'a6af97877cc39b1f0de0cb98c1183ce8abc0f56af1ae1c4d83f7472a4a133b07'   # run_07_takeoff.ps1 r12 = r13 = r14 (блок 3c), не меняется

# ---------- песочница: копия набора без tests, out, _aside, proverka_* (её папка-родитель = «папка проекта» для 07) ----------
$SBP = Join-Path $Run 'sb'; $SB = Join-Path $SBP 'bench_kit_20261117_r14'
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
# ---------- страж: ssh, который найдёт шаг, - подделка (как в r13) ----------
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
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $SB $script) + '" ' + $more) -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    Remove-Item Env:BB_KIT_OUT -ErrorAction SilentlyContinue
    return @{ Code = $p.ExitCode; Console = ([IO.File]::ReadAllText($so) + [IO.File]::ReadAllText($so + '.err')); Calls = @(Calls); Secs = 0; Guard = $true }
}
function New-OutDir([string]$name) { $o = Join-Path $Run ('out_' + $name); New-Item -ItemType Directory -Path $o -Force | Out-Null; return $o }
function Latest([string]$dir, [string]$filter) { return @(Get-ChildItem -LiteralPath $dir -File -Filter $filter | Where-Object { $_.Name -notmatch '\.generated\.|\.err\.txt$|\.raw\.txt$' } | Sort-Object LastWriteTime) }
function Wsl([string[]]$a) { $ErrorActionPreference = 'Continue'; return (& wsl.exe -e nice -n 19 ionice -c3 @a 2>&1 | Out-String) }
Check 'G0' ('страж: собранная подделка - первый ssh в PATH (в этом процессе и в отдельном powershell), sha ' + $script:FakeSha.Substring(0, 12) + '…, метка ' + $Marker + ' в файле') ((Guard-InProc) -eq '' -and (Guard-Child) -eq '') ((Guard-InProc) + ' | ' + (Guard-Child))

# ---------- WSL: поддельный «дом дрона» ----------
$wslOk = $false; $WB = ''; $ti = ''; $shaW = @{}
if ((Want 'R') -or (Want 'E')) {
    try {
        $kitW = (& wsl.exe -e wslpath -a ($Kit.Replace('\', '/')) | Out-String).Trim()
        $WB = (Wsl @('bash', '-c', 'mktemp -d /tmp/r14pc_XXXXXX')).Trim()
        $ti = Wsl @('bash', ($kitW + '/tests/r14_wsl_tree.sh'), 'init', $WB)
        $wslOk = ($ti -match ('TREE14_OK ' + [regex]::Escape($WB)))
        foreach ($m in [regex]::Matches($ti, '(?m)^(SHA_[A-Z0-9_]+) ([0-9a-f]{64})\s*$')) { $shaW[$m.Groups[1].Value] = $m.Groups[2].Value }
    } catch { $ti = $_.Exception.Message }
    Check 'W0' ('WSL: поддельный дом дрона из образов r2j, jd2, r2m_cam (/work, только чтение) в ' + $WB) $wslOk $ti
}
function Variant([string]$v, [string]$c) { $o = Wsl @('bash', ($kitW + '/tests/r14_wsl_tree.sh'), 'variant', $WB, $v, $c); return ($o -match ('VARIANT14_OK ' + $v + ' ' + $c + ' ')) }

# ======================= R: 09 и 15, камера r2j ИЛИ r2m_cam =======================
$r09m = $null
if (Want 'R') {
    $lj = Join-Path $Run 'lists.txt'
    $ps = ". '" + (Join-Path $SB 'lib\bb_common.ps1') + "'; . '" + (Join-Path $SB 'lib\bb_lists.ps1') + "'; `$a = BL-ApplyJd2Alt '" + $SB + "' (BL-PyList '" + $SB + "'); `$b = BL-ApplyR2mPyAlt '" + $SB + "' `$a; `$c = BL-RtList '" + $SB + "'; `$d = BL-ApplyR2mRtAlt '" + $SB + "' `$c; [IO.File]::WriteAllText('" + $lj + "', ((`$a -join [char]10) + [char]10 + '=====' + [char]10 + (`$b -join [char]10) + [char]10 + '=====' + [char]10 + (`$c -join [char]10) + [char]10 + '=====' + [char]10 + (`$d -join [char]10)), (New-Object Text.UTF8Encoding(`$false)))"
    & powershell -NoProfile -ExecutionPolicy Bypass -Command $ps 2>&1 | Out-Null
    $lt = [IO.File]::ReadAllText($lj) -split '====='; $la = @($lt[0].Trim() -split "`n"); $lb = @($lt[1].Trim() -split "`n"); $lc = @($lt[2].Trim() -split "`n"); $ld = @($lt[3].Trim() -split "`n")
    Check 'R1' 'BL-ApplyR2mPyAlt (после BL-ApplyJd2Alt): те же 10 узлов, изменена ровно одна строка - «4a15d699…,e133481d…  camera_fix.py»; aruco_detect.py остаётся «r2j,jd2»; остальные 8 байт в байт' ($lb.Count -eq 10 -and @($lb | Where-Object { $_ -match ',' }).Count -eq 2 -and ($lb -ccontains ($CAM + ',' + $CAMM + '  camera_fix.py')) -and ($lb -ccontains ($R2J + ',' + $JD2 + '  aruco_detect.py')) -and ($lb -ccontains ($VPE + '  vpe_fix.py')) -and @(Compare-Object -CaseSensitive @($la | Where-Object { $_ -notmatch 'camera_fix\.py' }) @($lb | Where-Object { $_ -notmatch 'camera_fix\.py' })).Count -eq 0) ($lb -join ' | ')
    Check 'R2' 'BL-ApplyR2mRtAlt: те же 8 строк RT, изменена ровно одна - «62be01db…,5c867929…  LAUNCH  launch/bumblebee.launch.py»; остальные 6 launch и fcu_detect байт в байт' ($ld.Count -eq 8 -and @($ld | Where-Object { $_ -match ',' }).Count -eq 1 -and ($ld -ccontains ($L2J + ',' + $L2M + '  LAUNCH  launch/bumblebee.launch.py')) -and @(Compare-Object -CaseSensitive @($lc | Where-Object { $_ -notmatch 'bumblebee\.launch\.py' }) @($ld | Where-Object { $_ -notmatch 'bumblebee\.launch\.py' })).Count -eq 0) ($ld -join ' | ')
    $tsv = Join-Path $SB 'image_r2j\R2M_CAM_20261117.tsv'
    $rows = @([IO.File]::ReadAllLines($tsv) | Where-Object { $_.Trim() -ne '' -and -not $_.StartsWith('#') })
    $pk = Join-Path (Split-Path -Parent $Kit) 'drone_pkg_r2m_cam_20261117'; if (-not (Test-Path -LiteralPath $pk)) { $pk = Join-Path $env:USERPROFILE 'Documents\Claude local\drone_pkg_r2m_cam_20261117' }
    $src = Join-Path $pk 'dlya_naborov_09_15.txt'; $srcT = $(if (Test-Path -LiteralPath $src) { [IO.File]::ReadAllText($src) } else { '' })
    Check 'R3' 'список r2m_cam: ровно 2 строки «e133481d… PY camera_fix.py» и «5c867929… LAUNCH launch/bumblebee.launch.py»; sha = обе копии образа /work/image_r2m_cam_20261117 (install и src, WSL) и dlya_naborov_09_15.txt пакета' ($rows.Count -eq 2 -and $rows[0] -ceq ($CAMM + "`tPY`tcamera_fix.py") -and $rows[1] -ceq ($L2M + "`tLAUNCH`tlaunch/bumblebee.launch.py") -and $shaW['SHA_R2M_CAM'] -ceq $CAMM -and $shaW['SHA_R2M_CAM_SRC'] -ceq $CAMM -and $shaW['SHA_R2M_LAUNCH'] -ceq $L2M -and $shaW['SHA_R2M_LAUNCH_SRC'] -ceq $L2M -and $srcT.Contains($CAMM + '  camera_fix.py') -and $srcT.Contains($L2M + "`tLAUNCH`tlaunch/bumblebee.launch.py")) (($shaW.Keys | ForEach-Object { $_ + '=' + $shaW[$_].Substring(0, 8) }) -join ' ')
    $fc = Join-Path $pk 'files\camera_fix.py'; $fl = Join-Path $pk 'files\bumblebee.launch.py'
    Check 'R3b' 'файлы пакета drone_pkg_r2m_cam_20261117\files\camera_fix.py и bumblebee.launch.py есть и их sha = строки списка (то, что ставит 44, 09 r14 примет); sha r2m_cam не равны r2j' ((Test-Path -LiteralPath $fc) -and (Test-Path -LiteralPath $fl) -and (Sha $fc) -eq $CAMM -and (Sha $fl) -eq $L2M -and $CAMM -ne $CAM -and $L2M -ne $L2J) ''
    # сгенерированные скрипты Pi (без связи, ответ «дрона» - заглушка)
    $cn = Join-Path $Run 'canned_min.txt'; [IO.File]::WriteAllText($cn, "BB_RTPY ok=0 diff=0 missing=0`nBB_INSTALL_CHECK ok=0 diff=0 missing=0 noprefix=0 cpp_ok=0 cpp_diff=0 cpp_missing=0 bin_ok=0 bin_missing=0 stale=0`nBB_INSTALL_CHECK_DONE`n", $utf8n)
    Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_install.txt'), $cn)
    $o9 = New-OutDir 'r_gen09'; $r = Run-Ps 'run_install_check.ps1' $o9
    $g9 = @(Get-ChildItem -LiteralPath $o9 -Filter 'install_check_*.generated.sh'); $g9t = $(if ($g9.Count -eq 1) { [IO.File]::ReadAllText($g9[0].FullName) } else { '' })
    $caseLine = 'case "$name" in aruco_detect.py) w="$want"; lab=" POSEFIX_JD2";; camera_fix.py) w="$want"; lab=" R2M_CAM";; *) w="${want%%,*}"; lab="";; esac'
    $caseRt = 'case "$kind $path" in "LAUNCH launch/bumblebee.launch.py") w="$want"; lab=" R2M_CAM";; *) w="${want%%,*}"; lab="";; esac'
    Check 'R4' '09: в скрипте для Pi ровно 5 строк «sha,sha» (2 примера real, aruco jd2, camera r2m_cam, launch r2m_cam); метка по ИМЕНИ узла (aruco - POSEFIX_JD2, camera_fix - R2M_CAM, прочие - только первое sha) и по ПУТИ launch' ($g9.Count -eq 1 -and (CountPairs $g9t) -eq 5 -and $g9t.Contains("`n" + $CAM + ',' + $CAMM + '  camera_fix.py' + "`n") -and $g9t.Contains("`n" + $L2J + ',' + $L2M + '  LAUNCH  launch/bumblebee.launch.py' + "`n") -and $g9t.Contains($caseLine) -and $g9t.Contains($caseRt) -and ([regex]::Matches($g9t, 'shamatch\(\) \{')).Count -eq 1) ('code=' + $r.Code + ' pairs=' + (CountPairs $g9t))
    Reset-Fake; $o15 = New-OutDir 'r_gen15'; $r = Run-Ps 'run_fingerprint.ps1' $o15
    $g15 = @(Get-ChildItem -LiteralPath $o15 -Filter 'fingerprint_bumblebee_*.generated.sh'); $g15m = @(Get-ChildItem -LiteralPath $o15 -Filter 'fingerprint_mavros_*.generated.sh')
    $g15t = $(if ($g15.Count -eq 1) { [IO.File]::ReadAllText($g15[0].FullName) } else { '' }); $g15mt = $(if ($g15m.Count -eq 1) { [IO.File]::ReadAllText($g15m[0].FullName) } else { '' })
    Check 'R5' '15: в скрипте bumblebee 5 строк «sha,sha», метки по имени и пути; в скрипте MAVROS - ни одной «sha,sha»' ($g15.Count -eq 1 -and (CountPairs $g15t) -eq 5 -and $g15t.Contains($caseLine) -and $g15t.Contains($caseRt) -and $g15m.Count -eq 1 -and (CountPairs $g15mt) -eq 0) ('pairs=' + (CountPairs $g15t))
    # плохой список r2m_cam -> код 4, к дрону не обращались (09 и 15)
    $keep = [IO.File]::ReadAllText($tsv)
    $okPy = $CAMM + "`tPY`tcamera_fix.py`n"; $okLn = $L2M + "`tLAUNCH`tlaunch/bumblebee.launch.py`n"
    $bads = @(
        @('только строка PY', $okPy), @('только строка LAUNCH', $okLn),
        @('третья строка', ($okPy + $okLn + $JD2 + "`tPY`taruco_detect.py`n")),
        @('две строки PY', ($okPy + $CAMM + "`tPY`tcamera_fix.py`n")),
        @('PY с именем vpe_fix.py', ($CAMM + "`tPY`tvpe_fix.py`n" + $okLn)),
        @('LAUNCH с путём main_camera.launch.py', ($okPy + $L2M + "`tLAUNCH`tlaunch/main_camera.launch.py`n")),
        @('вид FCU', ($okPy + $L2M + "`tFCU`tlaunch/bumblebee.launch.py`n")),
        @('вид py строчными', ($CAMM + "`tpy`tcamera_fix.py`n" + $okLn)),
        @('sha camera = r2j', ($CAM + "`tPY`tcamera_fix.py`n" + $okLn)),
        @('sha launch = r2j', ($okPy + $L2J + "`tLAUNCH`tlaunch/bumblebee.launch.py`n")),
        @('не 64 hex', ("XYZ`tPY`tcamera_fix.py`n" + $okLn)),
        @('sha заглавными', ($CAMM.ToUpper() + "`tPY`tcamera_fix.py`n" + $okLn)),
        @('две колонки', ($CAMM + "`tcamera_fix.py`n" + $okLn)),
        @('пустой (только комментарии)', "# пусто`n")
    )
    foreach ($b in $bads) {
        [IO.File]::WriteAllText($tsv, $b[1], $utf8n)
        foreach ($s in @(@('09', 'run_install_check.ps1'), @('15', 'run_fingerprint.ps1'))) {
            Reset-Fake; $r = Run-Ps $s[1] (New-OutDir ('r_bad_' + [guid]::NewGuid().ToString('N').Substring(0, 6)))
            Check 'R6' ($s[0] + ': в списке r2m_cam ' + $b[0] + ': код 4, к дрону не обращались') ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'СТОП') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
        }
    }
    $tsvAside = Join-Path $Run 'tsv_aside'; New-Item -ItemType Directory -Path $tsvAside | Out-Null; Move-Item -LiteralPath $tsv -Destination $tsvAside
    foreach ($s in @(@('09', 'run_install_check.ps1'), @('15', 'run_fingerprint.ps1'))) {
        Reset-Fake; $r = Run-Ps $s[1] (New-OutDir ('r_notsv_' + $s[0]))
        Check 'R6b' ($s[0] + ': нет файла списка r2m_cam - код 4, к дрону не обращались') ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
    }
    [IO.File]::WriteAllText($tsv, $keep, $utf8n)
    # список узлов r2j с двумя строками camera_fix.py; список RT без строки bumblebee.launch.py -> код 4
    $inst = Join-Path $SB 'image_r2j\INSTALL_SHA256_r2j.txt'; $keepInst = [IO.File]::ReadAllText($inst)
    $rtl = Join-Path $SB 'image_r2j\RUNTIME_PY_r2j.tsv'; $keepRt = [IO.File]::ReadAllText($rtl)
    $badL = @(
        @('в списке узлов две строки camera_fix.py', $inst, ((@([IO.File]::ReadAllLines($inst)) + @($CAM + '  camera_fix.py')) -join "`n") + "`n"),
        @('в списке RT нет строки launch/bumblebee.launch.py', $rtl, ((@([IO.File]::ReadAllLines($rtl) | Where-Object { $_ -notmatch 'launch/bumblebee\.launch\.py' })) -join "`n") + "`n")
    )
    foreach ($b in $badL) {
        [IO.File]::WriteAllText($b[1], $b[2], $utf8n)
        foreach ($s in @(@('09', 'run_install_check.ps1'), @('15', 'run_fingerprint.ps1'))) {
            Reset-Fake; $r = Run-Ps $s[1] (New-OutDir ('r_lst_' + [guid]::NewGuid().ToString('N').Substring(0, 6)))
            Check 'R6c' ($s[0] + ': ' + $b[0] + ' - код 4, к дрону не обращались') ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'r2m_cam') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
        }
        [IO.File]::WriteAllText($inst, $keepInst, $utf8n); [IO.File]::WriteAllText($rtl, $keepRt, $utf8n)
    }
    Check 'R6d' 'после плохих списков списки песочницы восстановлены байт в байт (как в наборе)' ((Sha $inst) -eq (Sha (Join-Path $Kit 'image_r2j\INSTALL_SHA256_r2j.txt')) -and (Sha $rtl) -eq (Sha (Join-Path $Kit 'image_r2j\RUNTIME_PY_r2j.tsv')) -and (Sha $tsv) -eq (Sha (Join-Path $Kit 'image_r2j\R2M_CAM_20261117.tsv'))) ''
    # сквозная цепочка: ПК -> подделка ssh -> настоящий install_check.sh в WSL на доме дрона -> вердикт ПК
    if ($wslOk) {
        $ICam = 'INSTALL_FILE camera_fix.py OK R2M_CAM'; $RLn = 'RT_FILE LAUNCH launch/bumblebee.launch.py OK R2M_CAM'; $IJd = 'INSTALL_FILE aruco_detect.py OK POSEFIX_JD2'; $PcM = 'R2M_CAM: камера варианта r2m_cam вместо r2j'; $PcJ = 'POSEFIX_JD2: детектор меток варианта jd2'
        $cases = @(
            @('r2j', 'r2j', 0, 'r2j + r2j: код 0, # VERDICT OK, меток нет', @(('INSTALL_FILE camera_fix.py OK' + "`n"), ('RT_FILE LAUNCH launch/bumblebee.launch.py OK' + "`n")), @('R2M_CAM', 'POSEFIX_JD2'), 0, 0),
            @('jd2', 'r2j', 0, 'jd2 + r2j: код 0, только POSEFIX_JD2', @($IJd, $PcJ), @('R2M_CAM'), 1, 0),
            @('r2j', 'r2m', 0, 'r2j + r2m_cam: код 0, «camera_fix.py OK R2M_CAM» и «bumblebee.launch.py OK R2M_CAM», строка ПК R2M_CAM; POSEFIX_JD2 нет', @($ICam, $RLn, $PcM), @('POSEFIX_JD2'), 0, 2),
            @('jd2', 'r2m', 0, 'jd2 + r2m_cam: код 0, POSEFIX_JD2 и 2 R2M_CAM, обе строки ПК', @($IJd, $ICam, $RLn, $PcM, $PcJ), @(), 1, 2),
            @('jd2_real', 'r2m', 0, 'jd2 + r2m_cam + карта real: код 0, все три метки (1 POSEFIX_JD2, 2 R2M_CAM, 2 REAL_MAP)', @($IJd, $ICam, $RLn, 'flight_marker.py OK - REAL_MAP'), @(), 1, 2),
            @('r2j', 'cam_only', 5, 'camera_fix r2m_cam, а launch r2j: код 5, СТОП «только ОДИН из двух файлов r2m_cam»', @($ICam, 'только ОДИН из двух файлов r2m_cam'), @($RLn), 0, 1),
            @('jd2', 'launch_only', 5, 'jd2 + launch r2m_cam, а camera_fix r2j: код 5, СТОП «только ОДИН из двух»', @($RLn, 'только ОДИН из двух файлов r2m_cam'), @($ICam), 1, 1),
            @('r2j', 'cam_other', 5, 'чужой camera_fix (r2j_cam dabd5076) + launch r2m_cam: код 5, «camera_fix.py DIFF got=dabd5076 want=r2j,r2m_cam»', @(('INSTALL_FILE camera_fix.py DIFF got=' + $CAMJC + ' want=' + $CAM + ',' + $CAMM)), @(), -1, -1),
            @('r2j', 'launch_other', 5, 'camera_fix r2m_cam + чужой launch (r2k 05af46f8): код 5, «bumblebee.launch.py DIFF got=05af46f8 want=r2j,r2m_cam»', @(('RT_FILE LAUNCH launch/bumblebee.launch.py DIFF got=' + $L2K + ' want=' + $L2J + ',' + $L2M)), @(), -1, -1),
            @('r2j', 'cam_as_vpe', 5, 'camera_fix r2m_cam под именем vpe_fix.py: код 5, vpe_fix.py DIFF (у vpe_fix только r2j)', @(('INSTALL_FILE vpe_fix.py DIFF got=' + $CAMM + ' want=' + $VPE)), @('R2M_CAM'), -1, -1),
            @('r2j', 'launch_as_main', 5, 'launch r2m_cam под именем main_camera.launch.py: код 5, DIFF (поблажка только для bumblebee.launch.py)', @(('RT_FILE LAUNCH launch/main_camera.launch.py DIFF got=' + $L2M + ' want=' + $LMAIN)), @('R2M_CAM'), -1, -1),
            @('jd2_as_cam', 'r2j', 5, 'файл jd2 под именем camera_fix.py: код 5, DIFF want=r2j,r2m_cam (метка по имени, не «любой второй sha»)', @(('INSTALL_FILE camera_fix.py DIFF got=' + $JD2 + ' want=' + $CAM + ',' + $CAMM)), @('OK R2M_CAM', 'OK POSEFIX_JD2'), -1, -1),
            @('jd', 'r2m', 5, 'старый jd + r2m_cam: код 5, aruco DIFF (r2m_cam jd не открывает)', @(('INSTALL_FILE aruco_detect.py DIFF got=' + $JD + ' want=' + $R2J + ',' + $JD2)), @('OK POSEFIX_JD2'), -1, -1)
        )
        foreach ($c in $cases) {
            $vok = Variant $c[0] $c[1]; Reset-Fake 'normal' ($WB + '/runner13.sh'); $o = New-OutDir ('r_chain09_' + $c[0] + '_' + $c[1]); $r = Run-Ps 'run_install_check.ps1' $o
            $f = @(Latest $o 'install_check_*.txt'); $ft = $(if ($f.Count -eq 1) { [IO.File]::ReadAllText($f[-1].FullName) -replace "`r`n", "`n" } else { '' }); $last = $(if ($ft) { @($ft.Trim() -split "`n")[-1].Trim() } else { '' })
            $both = $ft + "`n" + ($r.Console -replace "`r`n", "`n")
            $ok = $vok -and $r.Guard -and $r.Code -eq $c[2] -and $last -ceq $(if ($c[2] -eq 0) { '# VERDICT OK' } else { '# VERDICT NOT_OK' })
            $miss = @(); foreach ($m in $c[4]) { if (-not $both.Contains($m)) { $ok = $false; $miss += $m } }
            foreach ($m in $c[5]) { if ($both.Contains($m)) { $ok = $false; $miss += ('лишнее ' + $m) } }
            if ($c[6] -ge 0) { $ok = $ok -and ([regex]::Matches($ft, ' POSEFIX_JD2')).Count -eq $c[6] -and ([regex]::Matches($ft, ' R2M_CAM')).Count -eq $c[7] }
            if ($c[0] -eq 'jd2_real') { $ok = $ok -and ([regex]::Matches($ft, ' REAL_MAP')).Count -eq 2 }
            Check 'R7' ('09 сквозная (WSL, ' + $c[0] + ' + ' + $c[1] + '): ' + $c[3]) $ok ('variant=' + $vok + ' code=' + $r.Code + ' last=' + $last + ' нет/лишнее: ' + ($miss -join ' ; ') + ' | ' + (($ft -split "`n" | Where-Object { $_ -match '^INSTALL_FILE|^RT_FILE.*(DIFF|MISSING|R2M)|^BB_INSTALL_CHECK ' }) -join ' | '))
            if ($c[0] -eq 'jd2' -and $c[1] -eq 'r2m' -and $ok) { $r09m = $f[-1].FullName }
        }
        foreach ($c in @(@('r2j', 'r2m', 0), @('jd2', 'r2m', 0), @('r2j', 'cam_only', 5), @('r2j', 'cam_other', 5), @('r2j', 'r2j', 0))) {
            $vok = Variant $c[0] $c[1]; Reset-Fake 'normal' ($WB + '/runner13.sh'); $o = New-OutDir ('r_chain15_' + $c[0] + '_' + $c[1]); $r = Run-Ps 'run_fingerprint.ps1' $o
            $fb = @(Get-ChildItem -LiteralPath $o -Filter 'fingerprint_bumblebee_*.txt' | Where-Object { $_.Name -notmatch '\.raw\.|\.err\.' }); $fbt = $(if ($fb.Count -eq 1) { [IO.File]::ReadAllText($fb[0].FullName) } else { '' })
            $vd = $(if ($c[2] -eq 0) { '(?m)^# VERDICT OK' } else { '(?m)^# VERDICT NOT_OK' })
            $ok = $vok -and $r.Code -eq $c[2] -and $fbt -match $vd
            $key = $c[0] + '+' + $c[1]
            switch ($key) {
                'r2j+r2m' { $ok = $ok -and $fbt.Contains('# PY_NODE camera_fix.py OK R2M_CAM') -and $fbt.Contains('# RT_FILE LAUNCH launch/bumblebee.launch.py OK R2M_CAM') -and ([regex]::Matches($fbt, ' R2M_CAM')).Count -eq 2 -and -not $fbt.Contains('POSEFIX_JD2') -and $r.Console.Contains('PY_NODE camera_fix.py OK R2M_CAM') }
                'jd2+r2m' { $ok = $ok -and ([regex]::Matches($fbt, ' R2M_CAM')).Count -eq 2 -and ([regex]::Matches($fbt, ' POSEFIX_JD2')).Count -eq 1 }
                'r2j+cam_only' { $ok = $ok -and $fbt.Contains('# PY_NODE camera_fix.py OK R2M_CAM') -and $r.Console.Contains('R2M_CAM только у ОДНОГО из двух файлов') }
                'r2j+cam_other' { $ok = $ok -and $fbt.Contains('# PY_NODE camera_fix.py DIFF got=' + $CAMJC + ' want=' + $CAM + ',' + $CAMM) }
                default { $ok = $ok -and -not $fbt.Contains('R2M_CAM') -and -not $fbt.Contains('POSEFIX_JD2') }
            }
            Check 'R8' ('15 сквозная (WSL, ' + $key + '): код ' + $c[2] + ', VERDICT ' + $(if ($c[2] -eq 0) { 'OK' } else { 'NOT_OK' }) + ', метки R2M_CAM/POSEFIX_JD2 как ожидается') $ok ('variant=' + $vok + ' code=' + $r.Code + ' ' + (($fbt -split "`r?`n" | Where-Object { $_ -match '^# (VERDICT|PY_NODE .*(DIFF|MISSING|R2M|POSEFIX)|RT_FILE .*(DIFF|R2M))' }) -join ' | '))
        }
        $null = Variant 'r2j' 'r2j'
    }
    $notTouched = @('run_bb_build.ps1', 'pi\bb_build.sh', 'pi\bb_build_precheck.sh', 'run_r6_install_check_cam.ps1', 'run_r6_fingerprint_cam.ps1', 'lib\bb_lists_r2jcam.ps1', 'run_r6_camverify.ps1', 'pi\r6_cam_verify.sh', 'run_r6_cost.ps1', 'pi\r6_cost_phase.sh', 'image_r2j\check_gates.ps1', 'image_r2j\image_install.sh', 'image_r2j\image_rollback.sh', 'image_r2j_cam\check_gates_r2j_cam.ps1', 'image_r2j_cam\run_r6_cam_install.ps1', 'run_07_takeoff.ps1', 'image_r2j\INSTALL_SHA256_r2j.txt', 'image_r2j\RUNTIME_PY_r2j.tsv', 'image_r2j_cam\INSTALL_SHA256_r2jcam.txt', 'image_r2j_cam\RUNTIME_PY_r2jcam.tsv', 'image_r2j\image_manifest.final.tsv')
    $leak = @($notTouched | Where-Object { $t9 = [IO.File]::ReadAllText((Join-Path $SB $_)); $t9 -match 'BL-ApplyR2m|BL-R2mRead|R2M_CAM|e133481d|5c867929' })
    Check 'R9' 'сборка 13, 09c/15c, 22, 24a/24b, гейты и установка/откат 05/06/05c, 07, списки r2j и r2j_cam список r2m_cam не берут (строго как в r13)' ($leak.Count -eq 0) ($leak -join ', ')
    Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_install.txt'), $cn)
    $o9c = New-OutDir 'r_gen09c'; $r = Run-Ps 'run_r6_install_check_cam.ps1' $o9c
    $g9c = @(Get-ChildItem -LiteralPath $o9c -Filter 'sverka_r2jcam_*.generated.sh'); $g9ct = $(if ($g9c.Count -eq 1) { [IO.File]::ReadAllText($g9c[0].FullName) } else { '' })
    Check 'R9b' '09c (вариант r2j_cam): в скрипте для Pi ни одной «sha,sha», camera_fix.py только dabd5076 - r2m_cam там даст DIFF (как в r13)' ($g9c.Count -eq 1 -and (CountPairs $g9ct) -eq 0 -and $g9ct.Contains("`n" + $CAMJC + '  camera_fix.py' + "`n") -and -not $g9ct.Contains($CAMM) -and -not $g9ct.Contains($L2M)) ('code=' + $r.Code)
}

# ======================= E: 07 (блок 3c без изменений) видит журналы пакета r2m_cam =======================
if (Want 'E') {
    $p07 = Join-Path $SB 'run_07_takeoff.ps1'
    $conf = Join-Path $SB 'takeoff.conf'; $gate = Join-Path $SB 'gates\TAKEOFF_APPROVED.txt'
    $cf = @{}; foreach ($l in [IO.File]::ReadAllLines($conf)) { $t9 = $l.Trim(); if ($t9 -eq '' -or $t9.StartsWith('#')) { continue }; $i = $t9.IndexOf('='); if ($i -gt 0) { $cf[$t9.Substring(0, $i).Trim()] = $t9.Substring($i + 1).Trim() } }
    [IO.File]::WriteAllText($gate, ("ШАГ=14`r`nВЗЛЁТ_РАЗРЕШИЛ=владелец`r`nДАТА=2026-11-17 тест`r`nСЛОВА_ВЛАДЕЛЬЦА=тест r14`r`nСКРИПТ_SHA256=" + $cf['SCRIPT_SHA256'] + "`r`nАРГУМЕНТЫ=`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
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
    function Run07([string]$o) { Reset-Fake 'normal' '' $badSha; return (Run-Ps 'run_07_takeoff.ps1' $o '-SafetyConfirmed NET-TWO-KILL-YES' -ChildGuard) }
    function Passed($r) { return ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -ge 2 -and $r.Console -match 'sha256 не равен' -and $r.Console -notmatch 'взлёт не разрешён' -and @($r.Calls | Where-Object { $_ -notmatch [regex]::Escape($Marker) }).Count -eq 0) }
    function Refused($r, [string]$what) { return ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'взлёт не разрешён' -and $r.Console -match 'ДО последней установки или отката пакета на дрон' -and $r.Console.Contains($what)) }
    Check 'E0' '07 r14 = run_07_takeoff.ps1 r13 = r12 байт в байт (sha a6af9787…, блок 3c не менялся)' ((Sha $p07) -eq $S07R12) (Sha $p07)
    $pk = 'drone_pkg_r2m_cam_20261117'
    Clear-Pkgs; $null = Pkg-File $pk 'r2m_cam_install_20261117_120000.log' 2; $r = Run07 (New-Out07 'e1_inst')
    Check 'E1' '07: журнал 44 (drone_pkg_r2m_cam_20261117\out\r2m_cam_install_*.log, имя как в run_r2m_cam.ps1) через 3 мин ПОСЛЕ 09 - код 4 до подделки ssh, с именем журнала' (Refused $r ($pk + '\out\r2m_cam_install_20261117_120000.log')) ('code=' + $r.Code + ' calls=' + $r.Calls.Count + ' ' + $r.Console)
    Clear-Pkgs; $null = Pkg-File $pk 'r2m_cam_rollback_20261117_120000.log' 2; $r = Run07 (New-Out07 'e2_rb')
    Check 'E2' '07: журнал 45 (откат r2m_cam) после 09 - код 4 до подделки' (Refused $r ($pk + '\out\r2m_cam_rollback_20261117_120000.log')) ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $null = Pkg-File $pk 'r2m_cam_install_20261117_070000.log' 30; $null = Pkg-File $pk 'r2m_cam_install_20261117_070000.txt' 2; $r = Run07 (New-Out07 'e3_sib')
    Check 'E3' '07: .log 44 старше 09, но вывод того же запуска (.txt) новее 09 - код 4' (Refused $r 'r2m_cam_install_20261117_070000.log') ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $null = Pkg-File $pk 'r2m_cam_install_20261117_070000.log' 30; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_install_20261117_070000.log' 40; $r = Run07 (New-Out07 'e4_older')
    Check 'E4' '07: журналы 44 и 42 (jd2) СТАРШЕ 09 - условия пройдены, 07 дошёл до подделки (все вызовы ssh с меткой подделки)' (Passed $r) ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $null = Pkg-File $pk 'r2m_cam_install_20261117_070000.log' 30; $null = Pkg-File 'drone_pkg_posefix_jd2_20261117' 'posefix_jd2_install_20261117_120000.log' 2; $r = Run07 (New-Out07 'e5_jd2late')
    Check 'E5' '07: 44 старше 09, а 42 (jd2) позже - код 4 с именем журнала jd2 (берётся самое позднее событие любого пакета)' (Refused $r 'posefix_jd2_install_20261117_120000.log') ('code=' + $r.Code + ' ' + $r.Console)
    if ($r09m) {
        Clear-Pkgs; $null = Pkg-File $pk 'r2m_cam_install_20261117_070000.log' 30
        $r = Run07 (New-Out07 'e6_real09' 5 5 $r09m); Check 'E6' '07: настоящий отчёт 09 r14 (jd2 + r2m_cam: POSEFIX_JD2 и 2 R2M_CAM, «# VERDICT OK»), сделан после 44 - условия пройдены (до подделки)' (Passed $r) ('code=' + $r.Code + ' ' + $r.Console)
        Clear-Pkgs; $null = Pkg-File $pk 'r2m_cam_install_20261117_120000.log' 2
        $r = Run07 (New-Out07 'e7_real09_late' 5 5 $r09m); Check 'E7' '07: тот же настоящий отчёт 09 r14, но журнал 44 позже него - код 4' (Refused $r 'r2m_cam_install_20261117_120000.log') ('code=' + $r.Code + ' ' + $r.Console)
    }
    elseif (-not (Want 'R')) { Note 'E6, E7 пропущены: раздел R (источник настоящего отчёта 09 r14) не запускался' }
    else { Check 'E6' 'нет настоящего отчёта 09 r14 jd2 + r2m_cam (R7 не прошёл)' $false '' }
    Clear-Pkgs; Move-Item -LiteralPath $gate -Destination (Join-Path $Run 'gate_aside_TAKEOFF_APPROVED.txt')
}

# ======================= G: страж сам отказывает, если ssh - не подделка (контроль, как в r13) =======================
if (Want 'G') {
    $stubSrc = 'using System; using System.IO; public static class StubSshNoMarker { public static int Main(string[] a) { File.AppendAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "stub_called.txt"), DateTime.Now.ToString("s") + Environment.NewLine); Console.Error.WriteLine("stub ssh"); return 255; } }'
    $stubDir = Join-Path $Run 'stub_bez_metki'; New-Item -ItemType Directory -Path $stubDir | Out-Null; $stubExe = Join-Path $stubDir 'ssh.exe'
    Add-Type -TypeDefinition $stubSrc -OutputAssembly $stubExe -OutputType ConsoleApplication
    $env:PATH = $stubDir + ';' + $FakeDir + ';' + $oldPath
    $og = New-OutDir 'g_path'; $r = Run-Ps 'run_07_takeoff.ps1' $og '-SafetyConfirmed NET-TWO-KILL-YES' -ChildGuard -GuardControl
    $env:PATH = $FakeDir + ';' + $oldPath
    Check 'G1' 'контроль стража: ssh-заглушка без метки стоит в PATH раньше подделки - страж отказал, run_07 НЕ запускался (заглушка не вызвана, out пуст)' ((-not $r.Guard) -and $r.Code -eq -1 -and $r.Console -match 'не подделка' -and -not (Test-Path -LiteralPath (Join-Path $stubDir 'stub_called.txt')) -and @(Get-ChildItem -LiteralPath $og -Force).Count -eq 0) ($r.Console)
    $fakeKeep = Join-Path $Run 'fake_keep_ssh.exe'; Copy-Item -LiteralPath $FakeExe -Destination $fakeKeep; Copy-Item -LiteralPath $stubExe -Destination $FakeExe -Force
    $og = New-OutDir 'g_swap'; $r = Run-Ps 'run_07_takeoff.ps1' $og '-SafetyConfirmed NET-TWO-KILL-YES' -ChildGuard -GuardControl
    Check 'G2' 'контроль стража: на месте подделки заглушка без метки (другой sha) - страж отказал, run_07 НЕ запускался' ((-not $r.Guard) -and $r.Code -eq -1 -and $r.Console -match 'sha ssh не равен' -and -not (Test-Path -LiteralPath (Join-Path $FakeDir 'stub_called.txt')) -and @(Get-ChildItem -LiteralPath $og -Force).Count -eq 0) ($r.Console)
    Copy-Item -LiteralPath $fakeKeep -Destination $FakeExe -Force
    Check 'G3' 'после контроля подделка возвращена: страж снова пропускает' ((Guard-InProc) -eq '' -and (Guard-Child) -eq '' -and (Sha $FakeExe) -eq $script:FakeSha) ''
    Check 'G4' 'страж за весь прогон не отказал ни разу, кроме двух контрольных (G1, G2)' ($script:guardRefusals -eq 0) ('отказов: ' + $script:guardRefusals)
}

# ======================= C: .cmd =======================
if (Want 'C') {
    $cmds = @(Get-ChildItem -LiteralPath $Kit -Filter '*.cmd' -File)
    $badCmd = @($cmds | Where-Object { $l = @([IO.File]::ReadAllLines($_.FullName, [Text.Encoding]::UTF8)); -not ($l.Count -ge 3 -and $l[0] -eq '@echo off' -and $l[2] -match '^echo (ТОЛЬКО ЧТЕНИЕ|МЕНЯЕТ ДРОН)') } | ForEach-Object { $_.Name })
    Check 'C1' ('все .cmd в корне набора (' + $cmds.Count + '): первая выводимая строка - ТОЛЬКО ЧТЕНИЕ или МЕНЯЕТ ДРОН; новых .cmd нет') ($badCmd.Count -eq 0 -and $cmds.Count -eq 32) ($badCmd -join ', ')
}

# ======================= K: r14 = копия r13 + ожидаемые правки =======================
if (Want 'K') {
    $r13 = Join-Path (Split-Path -Parent $Kit) 'bench_kit_20261117_r13'
    if (Test-Path -LiteralPath $r13) {
        $changed = @('lib\bb_lists.ps1', 'run_install_check.ps1', 'run_fingerprint.ps1', 'pi\install_check.sh', 'pi\overlay_fingerprint.sh', 'SHA256SUMS.txt')
        $r13f = @(Get-ChildItem -LiteralPath $r13 -Recurse -File | ForEach-Object { $_.FullName.Substring($r13.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and $_ -notmatch '^tests\\run_[^\\]+\\' })
        $miss = @(); $diff = @(); $same = 0
        foreach ($rel in $r13f) { $k = Join-Path $Kit $rel; if (-not (Test-Path -LiteralPath $k)) { $miss += $rel; continue }; if ((Sha $k) -ne (Sha (Join-Path $r13 $rel))) { if ($changed -notcontains $rel) { $diff += $rel } } else { $same++ } }
        Check 'K1' ('все файлы r13 есть в r14; изменены только ожидаемые 6 (bb_lists, 09, 15, install_check.sh, overlay_fingerprint.sh, SHA256SUMS), байт в байт одинаковых: ' + $same) ($miss.Count -eq 0 -and $diff.Count -eq 0) (($miss + $diff) -join ', ')
        $chg = @($changed | Where-Object { $_ -ne 'SHA256SUMS.txt' -and (Sha (Join-Path $Kit $_)) -ne (Sha (Join-Path $r13 $_)) })
        Check 'K1b' 'все 5 ожидаемых файлов действительно изменены' ($chg.Count -eq 5) ($chg -join ', ')
        $newOk = '^(README_r14\.md|DIFF_r13_r14\.txt|image_r2j\\R2M_CAM_20261117\.tsv|tests\\run_tests_r14\.ps1|tests\\run_tests_r14_pi\.sh|tests\\r14_wsl_tree\.sh|proverka_r14\\.+|tests\\run_[^\\]+\\.+)$'
        $new = @(Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object { $_.FullName.Substring($Kit.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and -not (Test-Path -LiteralPath (Join-Path $r13 $_)) -and $_ -notmatch $newOk })
        Check 'K2' 'новых файлов, кроме ожидаемых (README_r14, DIFF_r13_r14, список r2m_cam, тесты r14, proverka_r14), нет' ($new.Count -eq 0) ($new -join ', ')
        $rd = @('README.md', 'README_r11.md', 'README_r13.md', 'PROGRESS.md', 'run_07_takeoff.ps1', 'image_r2j\POSEFIX_JD2_20261117.tsv') | Where-Object { (Sha (Join-Path $Kit $_)) -ne (Sha (Join-Path $r13 $_)) }
        Check 'K5' 'README.md, README_r11, README_r13, PROGRESS.md, 07 и список jd2 не менялись (байт в байт как в r13)' (@($rd).Count -eq 0) (@($rd) -join ', ')
    }
    else { Check 'K0' 'папка r13 рядом не найдена: сравнение с r13 не сделано' $false $r13 }
    Check 'K3' 'gates\: TAKEOFF_APPROVED.txt и OVERLAY_*_APPROVED.txt нет; image_r2j\gates\S2_S3_PASSED.txt нет' (-not (Test-Path (Join-Path $Kit 'gates\TAKEOFF_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'gates\OVERLAY_MAVROS_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'gates\OVERLAY_BUMBLEBEE_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'image_r2j\gates\S2_S3_PASSED.txt'))) ''
    $outFiles = @(Get-ChildItem -LiteralPath (Join-Path $Kit 'out') -File -ErrorAction SilentlyContinue)
    Check 'K4' 'out\ набора r14 пуст (тесты пишут только в tests\run_r14_*)' ($outFiles.Count -eq 0) (($outFiles | ForEach-Object { $_.Name }) -join ', ')
}

$env:PATH = $oldPath
Note ''
Note ('WSL-песочница: ' + $WB + ' (не удалялась)')
Note ('ИТОГ r14: PASS ' + $script:pass + ', FAIL ' + $script:fail)
exit $script:fail
