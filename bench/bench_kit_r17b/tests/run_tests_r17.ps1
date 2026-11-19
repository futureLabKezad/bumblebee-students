# run_tests_r17.ps1 (Claude, 19.11.2026, набор r17 = r16 + В1.1 вместо В1 (решение владельца 19.11) + строка частоты детектора в шаге 03) - тесты НОВОГО в r17 на ПК, в песочнице. К дрону не подключается.
# Вместо ssh - подделка tests\fake_ssh_r13.cs (из r13, без изменений; сеть не открывает; для сквозных проверок подаёт скрипт Pi в WSL на поддельный «дом дрона» tests\r17_wsl_tree.sh).
# СТРАЖ (как в r13-r16): перед КАЖДЫМ запуском шага тест сам проверяет, что ssh, который найдёт BB-FindSsh, - подделка (путь, sha, метка BB_FAKE_SSH_R13_NO_NETWORK);
#   для 07 - ещё и в отдельном процессе powershell с тем же окружением. Иначе шаг НЕ запускается, тест - FAIL. Раздел G сам подменяет подделку заглушкой без метки и проверяет отказ.
# W: 09 и 15: aruco_detect.py - r2j / jd2 (POSEFIX_JD2) / В1.1 81daec90… (POSEFIX_V11); vpe_fix.py - r2j / 39027fbd… (POSEFIX_V11); метка по совпавшему sha; оба узла В1.1 одного варианта;
#    камера r2j / r2m_cam как в r14; 6 сочетаний {r2j, jd2, В1.1} × {r2j, r2m_cam}; смеси, старый В1 (с подсказкой «откат 49»), jd, jd3, чужие sha - СТОП.
# M: шаг 03 (run_measure.ps1) печатает «ЧАСТОТА ДЕТЕКТОРА: X кадр/с» из hz_all (без порога; примечание «≠ 6,1 — сказать владельцу») и строки «joint rms median» из журнала (vision_measure.sh: «joint» в фильтре); нет строк - громко «НЕ ЛЕТАТЬ». .cmd не менялся.
# E: 07 (не менялся) видит журналы пакета В1.1 (шаги 48/49). C: .cmd. K: r17 = копия r16 + только ожидаемые правки.
# Всё WSL - с nice -n 19 ionice -c3; тест и его дочерние процессы - с приоритетом Idle.
# Запуск: powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_tests_r17.ps1 [-Only W,M,E,G,C,K]. Итог: «ИТОГ r17: PASS n, FAIL m».
param([string[]]$Only = @())
$ErrorActionPreference = 'Stop'
$Only = @($Only | ForEach-Object { $_ -split ',' } | Where-Object { $_ -ne '' })   # -File передаёт «E,G» одной строкой
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
try { [Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'Idle' } catch { }
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$Run = Join-Path $T ('run_r17_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
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
$JD3 = 'afa99dde4eff02518780b0a2a9e36fba8ed89bbeee0a00cc5cfe8f6df849036a'   # jd3 в r16 НЕ допускается (решение чата 1)
$V1A = '890dafbfde99541a0742e26acc81e5f5a222390e7b8244e31fbbfc8f4ccc4338'; $V1V = '39027fbd32cb0c19cae951cb19e2c37001faafc68d2d15f0a69aad36428b1f70'   # В1 (r16): aruco в r17 НЕ допускается, vpe = vpe В1.1
$V11A = '81daec90eb32a61cccaefc623f9f685d8acbc402edcc7876140541be29c18472'   # aruco В1.1
$S03R16 = 'f8aee55cadfe83a2506fc10dfa98fe2b7b3aadbd8a937efdc71a86e0c520d906'; $SVMR16 = 'b5078eb302be5567b1a4b813b75e54a855fd3d1a02e1df78c662893c95c10b8f'   # 03_v_rukakh.cmd и pi\vision_measure.sh r16 (.cmd не меняется; vision_measure.sh в r17 = r16 + «joint» в фильтре журнала)
$S07R12 = 'a6af97877cc39b1f0de0cb98c1183ce8abc0f56af1ae1c4d83f7472a4a133b07'   # run_07_takeoff.ps1 r12 = r13 = r14 = r16 = r17 (блок 3c), не меняется

# ---------- песочница: копия набора без tests, out, _aside, proverka_* (её папка-родитель = «папка проекта» для 07) ----------
$SBP = Join-Path $Run 'sb'; $SB = Join-Path $SBP 'bench_kit_20261119_r17'
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
if ((Want 'W') -or (Want 'E')) {
    try {
        $kitW = (& wsl.exe -e wslpath -a ($Kit.Replace('\', '/')) | Out-String).Trim()
        $WB = (Wsl @('bash', '-c', 'mktemp -d /tmp/r17pc_XXXXXX')).Trim()
        $ti = Wsl @('bash', ($kitW + '/tests/r17_wsl_tree.sh'), 'init', $WB)
        $wslOk = ($ti -match ('TREE17_OK ' + [regex]::Escape($WB)))
        foreach ($m in [regex]::Matches($ti, '(?m)^(SHA_[A-Z0-9_]+) ([0-9a-f]{64})\s*$')) { $shaW[$m.Groups[1].Value] = $m.Groups[2].Value }
    } catch { $ti = $_.Exception.Message }
    Check 'W0' ('WSL: поддельный дом дрона из образов r2j, jd2, В1, В1.1, jd3, r2m_cam (/work, только чтение) в ' + $WB) $wslOk $ti
}
function Variant([string]$v, [string]$c) { $o = Wsl @('bash', ($kitW + '/tests/r17_wsl_tree.sh'), 'variant', $WB, $v, $c); return ($o -match ('VARIANT17_OK ' + $v + ' ' + $c + ' ')) }

# ======================= W: 09 и 15, вариант В1.1 (aruco_detect.py и vpe_fix.py; aruco В1 - СТОП) =======================
$r09v1 = $null; $r09mix = $null; $r09old = $null
if (Want 'W') {
    $lj = Join-Path $Run 'lists.txt'
    $ps = ". '" + (Join-Path $SB 'lib\bb_common.ps1') + "'; . '" + (Join-Path $SB 'lib\bb_lists.ps1') + "'; `$a = BL-ApplyJd2Alt '" + $SB + "' (BL-PyList '" + $SB + "'); `$b = BL-ApplyR2mPyAlt '" + $SB + "' (BL-ApplyV11Alt '" + $SB + "' `$a); [IO.File]::WriteAllText('" + $lj + "', ((`$a -join [char]10) + [char]10 + '=====' + [char]10 + (`$b -join [char]10)), (New-Object Text.UTF8Encoding(`$false)))"
    & powershell -NoProfile -ExecutionPolicy Bypass -Command $ps 2>&1 | Out-Null
    $lt = @('', ''); if (Test-Path -LiteralPath $lj) { $lt = [IO.File]::ReadAllText($lj) -split '=====' } else { Note 'W1: списки не построены - функции списков остановились (BB-Stop)' }
    $la = @($lt[0].Trim() -split "`n"); $lb = @($lt[1].Trim() -split "`n")
    Check 'W1' 'BL-ApplyV11Alt (после BL-ApplyJd2Alt, перед BL-ApplyR2mPyAlt): те же 10 узлов; aruco «66f061ec…,b89bfb43…,81daec90…» (В1 890dafbf нет), vpe «f0dc7c18…,39027fbd…», camera «r2j,r2m_cam»; остальные 7 байт в байт' ($lb.Count -eq 10 -and -not (($lb -join ' ').Contains($V1A)) -and ($lb -ccontains ($R2J + ',' + $JD2 + ',' + $V11A + '  aruco_detect.py')) -and ($lb -ccontains ($VPE + ',' + $V1V + '  vpe_fix.py')) -and ($lb -ccontains ($CAM + ',' + $CAMM + '  camera_fix.py')) -and @($lb | Where-Object { $_ -match ',' }).Count -eq 3 -and @(Compare-Object -CaseSensitive @($la | Where-Object { $_ -notmatch 'aruco_detect\.py|camera_fix\.py|vpe_fix\.py' }) @($lb | Where-Object { $_ -notmatch 'aruco_detect\.py|camera_fix\.py|vpe_fix\.py' })).Count -eq 0) ($lb -join ' | ')
    $tsv = Join-Path $SB 'image_r2j\POSEFIX_V11_20261119.tsv'
    $rows = @([IO.File]::ReadAllLines($tsv) | Where-Object { $_.Trim() -ne '' -and -not $_.StartsWith('#') })
    Check 'W2' 'список В1.1: ровно 2 строки «81daec90… TAB aruco_detect.py» и «39027fbd… TAB vpe_fix.py»; sha = install и src образа /work/jv11_20261119/image_r2jv11 (WSL); aruco не равен r2j, jd2, jd, jd3 и старому В1; старого списка В1 в image_r2j нет' ($rows.Count -eq 2 -and $rows[0] -ceq ($V11A + "`taruco_detect.py") -and $rows[1] -ceq ($V1V + "`tvpe_fix.py") -and $shaW['SHA_V11_ARUCO'] -ceq $V11A -and $shaW['SHA_V11_ARUCO_SRC'] -ceq $V11A -and $shaW['SHA_V11_VPE'] -ceq $V1V -and $shaW['SHA_V11_VPE_SRC'] -ceq $V1V -and $shaW['SHA_V1_ARUCO'] -ceq $V1A -and @($R2J, $JD2, $JD, $JD3, $V1A) -notcontains $V11A -and -not (Test-Path -LiteralPath (Join-Path $SB 'image_r2j\POSEFIX_V1_20261118.tsv')) -and $V1V -ne $VPE -and $shaW['SHA_JD3'] -ceq $JD3) (($shaW.Keys | ForEach-Object { $_ + '=' + $shaW[$_].Substring(0, 8) }) -join ' ')
    $pkv = Join-Path (Split-Path -Parent $Kit) 'drone_pkg_posefix_v1x_20261119'; if (-not (Test-Path -LiteralPath $pkv)) { $pkv = Join-Path $env:USERPROFILE 'Documents\Claude local\drone_pkg_posefix_v1x_20261119' }
    $pfa = @(Get-ChildItem -LiteralPath $pkv -Recurse -File -Filter 'aruco_detect.py' -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch 'fixture|_aside|tests' }); $pfv = @(Get-ChildItem -LiteralPath $pkv -Recurse -File -Filter 'vpe_fix.py' -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch 'fixture|_aside|tests' })
    if ($pfa.Count -gt 0 -or $pfv.Count -gt 0) { Check 'W2b' ('файлы пакета drone_pkg_posefix_v1x_20261119 (aruco ' + $pfa.Count + ', vpe ' + $pfv.Count + ') - sha = строки списка В1.1') ($pfa.Count -ge 1 -and $pfv.Count -ge 1 -and @($pfa | Where-Object { (Sha $_.FullName) -ne $V11A }).Count -eq 0 -and @($pfv | Where-Object { (Sha $_.FullName) -ne $V1V }).Count -eq 0) ((@($pfa) + @($pfv) | ForEach-Object { $_.FullName.Substring($pkv.Length + 1) + '=' + (Sha $_.FullName).Substring(0, 8) }) -join ' ') }
    else { Note 'W2b пропущен: в пакете drone_pkg_posefix_v1x_20261119 файлов aruco_detect.py / vpe_fix.py ещё нет (его строит другой помощник); sha сверены с образом (V2)' }
    $cn = Join-Path $Run 'canned_min.txt'; [IO.File]::WriteAllText($cn, "BB_RTPY ok=0 diff=0 missing=0`nBB_INSTALL_CHECK ok=0 diff=0 missing=0 noprefix=0 cpp_ok=0 cpp_diff=0 cpp_missing=0 bin_ok=0 bin_missing=0 stale=0`nBB_INSTALL_CHECK_DONE`n", $utf8n)
    Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_install.txt'), $cn)
    $o9 = New-OutDir 'v_gen09'; $r = Run-Ps 'run_install_check.ps1' $o9
    $g9 = @(Get-ChildItem -LiteralPath $o9 -Filter 'install_check_*.generated.sh'); $g9t = $(if ($g9.Count -eq 1) { [IO.File]::ReadAllText($g9[0].FullName) } else { '' })
    $caseL = 'case "$name" in aruco_detect.py) w=$(printf ''%s'' "$want" | cut -d, -f1-3); labs=",POSEFIX_JD2,POSEFIX_V11";; vpe_fix.py) w=$(printf ''%s'' "$want" | cut -d, -f1-2); labs=",POSEFIX_V11";; camera_fix.py) w=$(printf ''%s'' "$want" | cut -d, -f1-2); labs=",R2M_CAM";; *) w="${want%%,*}"; labs="";; esac'
    Check 'W3' '09: в скрипте для Pi строки «r2j,jd2,v11  aruco_detect.py» и «r2j,v1  vpe_fix.py»; метка по совпавшему sha (shalab; не больше 3 sha у aruco, 2 у vpe_fix и camera_fix, 1 у остальных); shalab и shamatch по одному разу, до цикла' ($g9.Count -eq 1 -and $g9t.Contains("`n" + $R2J + ',' + $JD2 + ',' + $V11A + '  aruco_detect.py' + "`n") -and $g9t.Contains("`n" + $VPE + ',' + $V1V + '  vpe_fix.py' + "`n") -and $g9t.Contains($caseL) -and $g9t.Contains('if lab=$(shalab "$got" "$w" "$labs"); then ok=$((ok+1));') -and ([regex]::Matches($g9t, '(?m)^shalab\(\) \{')).Count -eq 1 -and ([regex]::Matches($g9t, '(?m)^shamatch\(\) \{')).Count -eq 1 -and $g9t.IndexOf('shalab() {') -lt $g9t.IndexOf('while read -r want name; do')) ('code=' + $r.Code)
    Reset-Fake; $o15 = New-OutDir 'v_gen15'; $r = Run-Ps 'run_fingerprint.ps1' $o15
    $g15 = @(Get-ChildItem -LiteralPath $o15 -Filter 'fingerprint_bumblebee_*.generated.sh'); $g15t = $(if ($g15.Count -eq 1) { [IO.File]::ReadAllText($g15[0].FullName) } else { '' })
    Check 'W4' '15: в скрипте bumblebee строки aruco «r2j,jd2,v11» и vpe «r2j,v1», цикл PY_NODE с меткой по совпавшему sha' ($g15.Count -eq 1 -and $g15t.Contains("`n" + $R2J + ',' + $JD2 + ',' + $V11A + '  aruco_detect.py' + "`n") -and $g15t.Contains("`n" + $VPE + ',' + $V1V + '  vpe_fix.py' + "`n") -and $g15t.Contains(('  ' + $caseL)) -and $g15t.Contains('if lab=$(shalab "$got" "$w" "$labs"); then pok=$((pok+1));')) ''
    # плохой список В1 -> код 4, к дрону не обращались (09 и 15)
    $keep = [IO.File]::ReadAllText($tsv); $okA = $V11A + "`taruco_detect.py`n"; $okV = $V1V + "`tvpe_fix.py`n"
    $bads = @(
        @('только aruco', $okA), @('только vpe', $okV), @('третья строка', ($okA + $okV + $V11A + "`tcamera_fix.py`n")), @('две строки aruco', ($okA + $V1A + "`taruco_detect.py`n")),
        @('имя camera_fix.py вместо vpe_fix.py', ($okA + $V1V + "`tcamera_fix.py`n")), @('имя другим регистром', ($okA + $V1V + "`tVpe_fix.py`n")), @('имя с путём', ($V11A + "`tlib/bumblebee/aruco_detect.py`n" + $okV)),
        @('не 64 hex', ("XYZ`taruco_detect.py`n" + $okV)), @('заглавные', ($V11A.ToUpper() + "`taruco_detect.py`n" + $okV)), @('aruco В1 = r2j', ($R2J + "`taruco_detect.py`n" + $okV)),
        @('aruco В1 = jd2', ($JD2 + "`taruco_detect.py`n" + $okV)), @('vpe В1 = r2j', ($okA + $VPE + "`tvpe_fix.py`n")), @('три колонки', ($V11A + "`taruco_detect.py`tx`n" + $okV)), @('пустой', "# пусто`n")
    )
    foreach ($b in $bads) {
        [IO.File]::WriteAllText($tsv, $b[1], $utf8n)
        foreach ($s in @(@('09', 'run_install_check.ps1'), @('15', 'run_fingerprint.ps1'))) {
            Reset-Fake; $r = Run-Ps $s[1] (New-OutDir ('v_bad_' + [guid]::NewGuid().ToString('N').Substring(0, 6)))
            Check 'W5' ($s[0] + ': в списке В1.1 ' + $b[0] + ': код 4, к дрону не обращались') ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'СТОП') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
        }
    }
    $tsvAside = Join-Path $Run 'tsv_aside'; New-Item -ItemType Directory -Path $tsvAside | Out-Null; Move-Item -LiteralPath $tsv -Destination $tsvAside
    foreach ($s in @(@('09', 'run_install_check.ps1'), @('15', 'run_fingerprint.ps1'))) {
        Reset-Fake; $r = Run-Ps $s[1] (New-OutDir ('v_notsv_' + $s[0]))
        Check 'W5b' ($s[0] + ': нет файла списка В1.1 - код 4, к дрону не обращались') ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
    }
    [IO.File]::WriteAllText($tsv, $keep, $utf8n)
    $inst = Join-Path $SB 'image_r2j\INSTALL_SHA256_r2j.txt'; $keepInst = [IO.File]::ReadAllText($inst)
    [IO.File]::WriteAllText($inst, (((@([IO.File]::ReadAllLines($inst)) + @($VPE + '  vpe_fix.py')) -join "`n") + "`n"), $utf8n)
    foreach ($s in @(@('09', 'run_install_check.ps1'), @('15', 'run_fingerprint.ps1'))) {
        Reset-Fake; $r = Run-Ps $s[1] (New-OutDir ('v_inst_' + $s[0]))
        Check 'W5c' ($s[0] + ': две строки vpe_fix.py в списке узлов - код 4, к дрону не обращались') ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
    }
    [IO.File]::WriteAllText($inst, $keepInst, $utf8n)
    $ps2 = ". '" + (Join-Path $SB 'lib\bb_common.ps1') + "'; . '" + (Join-Path $SB 'lib\bb_lists.ps1') + "'; `$x = BL-ApplyV11Alt '" + $SB + "' (BL-PyList '" + $SB + "'); 'NOT_STOPPED'"
    $o2 = (& powershell -NoProfile -ExecutionPolicy Bypass -Command $ps2 2>&1 | Out-String); $c2 = $LASTEXITCODE
    Check 'W5d' 'BL-ApplyV11Alt без BL-ApplyJd2Alt (у aruco одно sha) - СТОП код 4: порядок r2j, jd2, В1.1 обязателен' ($c2 -eq 4 -and $o2 -notmatch 'NOT_STOPPED') ('code=' + $c2)
    Check 'W5e' 'после плохих списков списки песочницы восстановлены байт в байт' ((Sha $inst) -eq (Sha (Join-Path $Kit 'image_r2j\INSTALL_SHA256_r2j.txt')) -and (Sha $tsv) -eq (Sha (Join-Path $Kit 'image_r2j\POSEFIX_V11_20261119.tsv'))) ''
    # сквозная цепочка: 6 сочетаний, смеси и СТОП-случаи; числа меток POSEFIX_JD2 / POSEFIX_V1 / R2M_CAM в файле 09
    if ($wslOk) {
        $IA = 'INSTALL_FILE aruco_detect.py OK POSEFIX_V11'; $IV = 'INSTALL_FILE vpe_fix.py OK POSEFIX_V11'; $IJ2 = 'INSTALL_FILE aruco_detect.py OK POSEFIX_JD2'; $IC = 'INSTALL_FILE camera_fix.py OK R2M_CAM'; $RL = 'RT_FILE LAUNCH launch/bumblebee.launch.py OK R2M_CAM'
        $PV = 'POSEFIX_V11: на дроне В1.1 (детектор + vpe_fix)'; $P2 = 'POSEFIX_JD2: детектор меток варианта jd2'; $PM = 'R2M_CAM: камера варианта r2m_cam'; $MIX = 'только ОДИН из двух узлов варианта В1.1'; $OLD = 'на дроне стоит В1 (aruco_detect.py 890dafbf...), он больше не допускается - нужен откат 49'
        $cases = @(
            @('r2j', 'r2j', 0, @(('INSTALL_FILE aruco_detect.py OK' + "`n"), ('INSTALL_FILE vpe_fix.py OK' + "`n")), @('POSEFIX', 'R2M_CAM'), 0, 0, 0),
            @('jd2', 'r2j', 0, @($IJ2, $P2, ('INSTALL_FILE vpe_fix.py OK' + "`n")), @('POSEFIX_V11', 'R2M_CAM'), 1, 0, 0),
            @('v11', 'r2j', 0, @($IA, $IV, $PV), @('POSEFIX_JD2', 'R2M_CAM', $P2), 0, 2, 0),
            @('r2j', 'r2m', 0, @($IC, $RL, $PM), @('POSEFIX'), 0, 0, 2),
            @('jd2', 'r2m', 0, @($IJ2, $IC, $RL, $P2, $PM), @('POSEFIX_V11'), 1, 0, 2),
            @('v11', 'r2m', 0, @($IA, $IV, $IC, $RL, $PV, $PM), @('POSEFIX_JD2'), 0, 2, 2),
            @('v11_aruco', 'r2j', 5, @($IA, ('INSTALL_FILE vpe_fix.py OK' + "`n"), $MIX), @($PV), 0, 1, 0),
            @('jd2_vpe_v1', 'r2j', 5, @($IJ2, $IV, $MIX), @($PV), 1, 1, 0),
            @('v1_vpe', 'r2m', 5, @(('INSTALL_FILE aruco_detect.py OK' + "`n"), $IV, $MIX), @($PV), 0, 1, 2),
            @('v1', 'r2j', 5, @(('INSTALL_FILE aruco_detect.py DIFF got=' + $V1A + ' want=' + $R2J + ',' + $JD2 + ',' + $V11A), $IV, $OLD, 'СТОП'), @($PV), 0, 1, 0),
            @('v1', 'r2m', 5, @(('INSTALL_FILE aruco_detect.py DIFF got=' + $V1A + ' want='), $OLD), @($PV), 0, 1, 2),
            @('jd', 'r2j', 5, @(('INSTALL_FILE aruco_detect.py DIFF got=' + $JD + ' want=' + $R2J + ',' + $JD2 + ',' + $V11A), 'СТОП'), @('OK POSEFIX', $OLD), 0, 0, 0),
            @('jd3', 'r2j', 5, @(('INSTALL_FILE aruco_detect.py DIFF got=' + $JD3 + ' want=' + $R2J + ',' + $JD2 + ',' + $V11A)), @('OK POSEFIX', $OLD), 0, 0, 0),
            @('v11_mod', 'r2j', 5, @('INSTALL_FILE aruco_detect.py DIFF got=', $IV), @($OLD), 0, 1, 0),
            @('v11', 'cam_only', 5, @($IA, $IV, $IC, 'только ОДИН из двух файлов r2m_cam'), @(), 0, 2, 1)
        )
        foreach ($c in $cases) {
            $vok = Variant $c[0] $c[1]; Reset-Fake 'normal' ($WB + '/runner13.sh'); $o = New-OutDir ('v_chain09_' + $c[0] + '_' + $c[1]); $r = Run-Ps 'run_install_check.ps1' $o
            $f = @(Latest $o 'install_check_*.txt'); $ft = $(if ($f.Count -eq 1) { [IO.File]::ReadAllText($f[-1].FullName) -replace "`r`n", "`n" } else { '' }); $last = $(if ($ft) { @($ft.Trim() -split "`n")[-1].Trim() } else { '' })
            $both = $ft + "`n" + ($r.Console -replace "`r`n", "`n")
            $ok = $vok -and $r.Guard -and $r.Code -eq $c[2] -and $last -ceq $(if ($c[2] -eq 0) { '# VERDICT OK' } else { '# VERDICT NOT_OK' })
            $miss = @(); foreach ($m in $c[3]) { if (-not $both.Contains($m)) { $ok = $false; $miss += $m } }
            foreach ($m in $c[4]) { if ($both.Contains($m)) { $ok = $false; $miss += ('лишнее ' + $m) } }
            $nJ2 = ([regex]::Matches($ft, ' POSEFIX_JD2')).Count; $nV = ([regex]::Matches($ft, ' POSEFIX_V11')).Count; $nM = ([regex]::Matches($ft, ' R2M_CAM')).Count
            $ok = $ok -and $nJ2 -eq $c[5] -and $nV -eq $c[6] -and $nM -eq $c[7]
            Check 'W6' ('09 сквозная (WSL, ' + $c[0] + ' + ' + $c[1] + '): код ' + $c[2] + ', метки POSEFIX_JD2/POSEFIX_V11/R2M_CAM = ' + $c[5] + '/' + $c[6] + '/' + $c[7]) $ok ('variant=' + $vok + ' code=' + $r.Code + ' метки=' + $nJ2 + '/' + $nV + '/' + $nM + ' нет/лишнее: ' + ($miss -join ' ; ') + ' | ' + (($ft -split "`n" | Where-Object { $_ -match '^INSTALL_FILE (aruco|camera|vpe)|^RT_FILE.*(DIFF|R2M)|^BB_INSTALL_CHECK ' }) -join ' | '))
            if ($c[0] -eq 'v11' -and $c[1] -eq 'r2m' -and $ok) { $r09v1 = $f[-1].FullName }
            if ($c[0] -eq 'v1' -and $c[1] -eq 'r2j' -and $ok) { $r09old = $f[-1].FullName }
            if ($c[0] -eq 'jd2_vpe_v1' -and $ok) { $r09mix = $f[-1].FullName }
        }
        foreach ($c in @(@('v11', 'r2j', 0, 0, 2, 0), @('v11', 'r2m', 0, 0, 2, 2), @('jd2', 'r2m', 0, 1, 0, 2), @('v11_aruco', 'r2j', 5, 0, 1, 0), @('jd2_vpe_v1', 'r2j', 5, 1, 1, 0), @('v1', 'r2j', 5, 0, 1, 0), @('jd3', 'r2j', 5, 0, 0, 0), @('r2j', 'r2j', 0, 0, 0, 0))) {
            $vok = Variant $c[0] $c[1]; Reset-Fake 'normal' ($WB + '/runner13.sh'); $o = New-OutDir ('v_chain15_' + $c[0] + '_' + $c[1]); $r = Run-Ps 'run_fingerprint.ps1' $o
            $fb = @(Get-ChildItem -LiteralPath $o -Filter 'fingerprint_bumblebee_*.txt' | Where-Object { $_.Name -notmatch '\.raw\.|\.err\.' }); $fbt = $(if ($fb.Count -eq 1) { [IO.File]::ReadAllText($fb[0].FullName) } else { '' })
            $ok = $vok -and $r.Code -eq $c[2] -and $fbt -match $(if ($c[2] -eq 0) { '(?m)^# VERDICT OK' } else { '(?m)^# VERDICT NOT_OK' }) -and ([regex]::Matches($fbt, ' POSEFIX_JD2')).Count -eq $c[3] -and ([regex]::Matches($fbt, ' POSEFIX_V11')).Count -eq $c[4] -and ([regex]::Matches($fbt, ' R2M_CAM')).Count -eq $c[5]
            if ($c[0] -eq 'v11' -and $c[1] -eq 'r2j') { $ok = $ok -and $fbt.Contains('# PY_NODE aruco_detect.py OK POSEFIX_V11') -and $fbt.Contains('# PY_NODE vpe_fix.py OK POSEFIX_V11') -and $r.Console.Contains('PY_NODE vpe_fix.py OK POSEFIX_V11') }
            if ($c[0] -eq 'v1') { $ok = $ok -and $fbt.Contains('# PY_NODE aruco_detect.py DIFF got=' + $V1A + ' want=' + $R2J + ',' + $JD2 + ',' + $V11A) -and $r.Console.Contains('на дроне стоит В1 (aruco_detect.py 890dafbf...)') }
            if ($c[0] -eq 'v11_aruco' -or $c[0] -eq 'jd2_vpe_v1') { $ok = $ok -and $r.Console.Contains('POSEFIX_V11 только у ОДНОГО из двух узлов') }
            if ($c[0] -eq 'jd3') { $ok = $ok -and $fbt.Contains('# PY_NODE aruco_detect.py DIFF got=' + $JD3 + ' want=' + $R2J + ',' + $JD2 + ',' + $V11A) }
            Check 'W7' ('15 сквозная (WSL, ' + $c[0] + ' + ' + $c[1] + '): код ' + $c[2] + ', метки POSEFIX_JD2/POSEFIX_V11/R2M_CAM = ' + $c[3] + '/' + $c[4] + '/' + $c[5]) $ok ('variant=' + $vok + ' code=' + $r.Code + ' ' + (($fbt -split "`r?`n" | Where-Object { $_ -match '^# (VERDICT|PY_NODE .*(DIFF|MISSING|POSEFIX|R2M))' }) -join ' | '))
        }
        $null = Variant 'r2j' 'r2j'
    }
    $notTouched = @('run_bb_build.ps1', 'pi\bb_build.sh', 'pi\bb_build_precheck.sh', 'run_r6_install_check_cam.ps1', 'run_r6_fingerprint_cam.ps1', 'lib\bb_lists_r2jcam.ps1', 'run_r6_camverify.ps1', 'pi\r6_cam_verify.sh', 'run_r6_cost.ps1', 'pi\r6_cost_phase.sh', 'image_r2j\check_gates.ps1', 'image_r2j\image_install.sh', 'image_r2j\image_rollback.sh', 'image_r2j_cam\check_gates_r2j_cam.ps1', 'image_r2j_cam\run_r6_cam_install.ps1', 'run_07_takeoff.ps1', 'image_r2j\INSTALL_SHA256_r2j.txt', 'image_r2j_cam\INSTALL_SHA256_r2jcam.txt', 'image_r2j\image_manifest.final.tsv')
    $leak = @($notTouched | Where-Object { $t9 = [IO.File]::ReadAllText((Join-Path $SB $_)); $t9 -match 'BL-ApplyV11Alt|POSEFIX_V11|81daec90|39027fbd|890dafbf' })
    Check 'W8' 'сборка 13, 09c/15c, 22, 24a/24b, гейты и установка/откат 05/06/05c, 07, списки r2j и r2j_cam список В1.1 не берут' ($leak.Count -eq 0) ($leak -join ', ')
    Check 'W8b' 'jd3 не допускается: списка POSEFIX_JD3 и функции BL-ApplyJd3Alt нет; функции В1 (BL-ApplyV1Alt) и метки POSEFIX_V1 без «1» в скриптах Pi тоже нет' (-not (Test-Path -LiteralPath (Join-Path $SB 'image_r2j\POSEFIX_JD3_20261118.tsv')) -and -not ([IO.File]::ReadAllText((Join-Path $SB 'lib\bb_lists.ps1'))).Contains('BL-ApplyJd3Alt') -and -not ([IO.File]::ReadAllText((Join-Path $SB 'pi\install_check.sh'))).Contains('POSEFIX_JD3') -and -not ([IO.File]::ReadAllText((Join-Path $SB 'lib\bb_lists.ps1'))).Contains('function BL-ApplyV1Alt') -and -not ([regex]::IsMatch(([IO.File]::ReadAllText((Join-Path $SB 'pi\install_check.sh')) + [IO.File]::ReadAllText((Join-Path $SB 'pi\overlay_fingerprint.sh'))), 'POSEFIX_V1(?!1)'))) ''
}

# ======================= M: шаг 03 (run_measure.ps1) - «ЧАСТОТА ДЕТЕКТОРА» из hz_all и строки «joint rms median» (поправка по проверке review_v11_20261119) =======================
if (Want 'M') {
    $vmT = [IO.File]::ReadAllText((Join-Path $SB 'pi\vision_measure.sh')); $vm16 = $vmT.Replace("|process has died|joint'", "|process has died'")
    $vm16sha = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($utf8n.GetBytes($vm16))) -replace '-', '').ToLower()
    Check 'M0' '03_v_rukakh.cmd байт в байт как в r16 (03 будит детектор ровно как раньше - .cmd «МЕНЯЕТ ДРОН (косвенно)», wake 1); pi\vision_measure.sh отличается от r16 только словом «joint» в фильтре журнала (только чтение)' ((Sha (Join-Path $SB '03_v_rukakh.cmd')) -eq $S03R16 -and $vm16sha -eq $SVMR16 -and $vmT.Contains("|process has died|joint'") -and ([regex]::Matches($vmT, 'joint')).Count -eq 1) ((Sha (Join-Path $SB '03_v_rukakh.cmd')) + ' ' + $vm16sha)
    $vmExp = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($utf8n.GetBytes(($vmT -replace "`r`n", "`n")))) -replace '-', '').ToLower()
    $note = 'В1.1 проверялся в Gazebo при 6,1 кадр/с; любое число заметно ≠ 6,1 — сказать владельцу до полёта'; $noJ = 'НЕТ ДАННЫХ JOINT RMS = НЕ ЛЕТАТЬ ДО РЕШЕНИЯ ВЛАДЕЛЬЦА'
    $J1 = 'J aruco_detect: joint rms median 1.23 px (2 s, n=12)'; $J2 = 'J aruco_detect: MAP != FIELD? joint PnP rms median 3.10 px over 2 s (> 2.5)'
    # case: метка, hz_all ('' = нет markers_used), строки joint, ждём строку частоты, ждём «нет joint»
    $mcases = @(
        @('hand_center', '6.10', @($J1, $J2), '6,1', $false), @('hand_camera_over', '8.00', @($J1), '8,0', $false), @('hand_back8', '6.36', @($J1), '6,36', $false),
        @('hand_center', '6.10', @(), '6,1', $true), @('hand_center', '', @(), '', $true)
    )
    foreach ($mc in $mcases) {
        $raw = "META host bumblebee-20ec`nSUMMARY markers_msgs count=0 hz=0.00 gaps_over_0.5s=0 max_gap_s=0 start_delay_s=120 end_silence_s=120 top_gaps=-`nSUMMARY vision_pose /mavros/vision_pose/pose count=600 hz=5.00 gaps_over_0.5s=0 max_gap_s=0.3`n"
        if ($mc[1]) { $raw += "SUMMARY markers_used msgs=732 with_ge1=700 (95.6%) with_0=32 hz_all=" + $mc[1] + "`n" } else { $raw += "SUMMARY markers_used сообщений /aruco_detect/markers_used не было`n" }
        $raw += "META python_exit 0`nJ aruco_detect: detection ACTIVE`n"; foreach ($j in $mc[2]) { $raw += $j + "`n" }; $raw += "BB_BENCH_DONE rc=0`n"
        $cf = Join-Path $Run ('canned_measure_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt'); [IO.File]::WriteAllText($cf, $raw, $utf8n)
        Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_.txt'), $cf)
        $o = New-OutDir ('m_' + [guid]::NewGuid().ToString('N').Substring(0, 6))
        $r = Run-Ps 'run_measure.ps1' $o ('-Label ' + $mc[0] + ' -DurationSec 120 -Mode measure -Wake 1 -Place ' + $mc[0] + ' -CameraHeightCm 50')
        $sf = @(Get-ChildItem -LiteralPath $o -Filter ('bench_' + $mc[0] + '_*.summary.txt')); $st = $(if ($sf.Count -eq 1) { [IO.File]::ReadAllText($sf[0].FullName) } else { '' })
        $sent = @(Get-ChildItem -LiteralPath $FakeDir -Filter 'sent_*.sh')
        $callOk = ($r.Calls.Count -eq 2 -and $r.Calls[1] -match ('_ 120 ' + $mc[0] + ' measure 1\]') -and $sent.Count -eq 1 -and (Sha $sent[0].FullName) -eq $vmExp)
        $freqLines = @($st -split "`r?`n" | Where-Object { $_.StartsWith('ЧАСТОТА ДЕТЕКТОРА') })
        $freqOk = $(if ($mc[3]) { $freqLines.Count -eq 1 -and $freqLines[0] -ceq ('ЧАСТОТА ДЕТЕКТОРА: ' + $mc[3] + ' кадр/с (по /aruco_detect/markers_used)') } else { $freqLines.Count -eq 1 -and $freqLines[0].StartsWith('ЧАСТОТА ДЕТЕКТОРА: нет данных') })
        $jointOk = $st.Contains('JOINT RMS (строки детектора «joint rms median» за замер): ' + $mc[2].Count) -and @($mc[2] | Where-Object { -not $st.Contains('  ' + $_) }).Count -eq 0
        $noJOk = ($st.Contains($noJ) -eq $mc[4]) -and ($r.Console.Contains($noJ) -eq $mc[4])
        $ok = $r.Guard -and $r.Code -eq 0 -and $callOk -and $freqOk -and $st.Contains($note) -and $r.Console.Contains($note) -and $jointOk -and $noJOk -and -not $st.Contains('на дроне выше') -and -not $st.Contains('7,0')
        Check 'M1' ('03 на подделке (' + $mc[0] + ', hz_all=' + $(if ($mc[1]) { $mc[1] } else { 'нет' }) + ', строк joint ' + $mc[2].Count + '): код 0; ровно одна строка частоты' + $(if ($mc[3]) { ' «' + $mc[3] + ' кадр/с»' } else { ' «нет данных»' }) + ' (не markers_msgs и не vision_pose); примечание «≠ 6,1 — сказать владельцу» без порога 7; строки joint в итоге; «НЕТ ДАННЫХ JOINT RMS = НЕ ЛЕТАТЬ…» ' + $(if ($mc[4]) { 'ЕСТЬ (громко)' } else { 'нет' }) + '; на Pi ушёл vision_measure.sh r17 с теми же аргументами (wake как раньше)') $ok ('code=' + $r.Code + ' call=' + $callOk + ' freq=' + ($freqLines -join '|') + ' joint=' + $jointOk + ' noJ=' + $noJOk)
    }
    $raw = "META x`nSUMMARY markers_used msgs=732 with_ge1=700 (95.6%) with_0=32 hz_all=6.10`nBB_BENCH_DONE rc=0`n"; $cf = Join-Path $Run 'canned_measure_vib.txt'; [IO.File]::WriteAllText($cf, $raw, $utf8n)
    Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_.txt'), $cf); $o = New-OutDir 'm_vib'
    $r = Run-Ps 'run_measure.ps1' $o '-Label vib_test -DurationSec 60 -Mode vibration -Wake 0'
    $sf = @(Get-ChildItem -LiteralPath $o -Filter 'bench_vib_test_*.summary.txt'); $st = $(if ($sf.Count -eq 1) { [IO.File]::ReadAllText($sf[0].FullName) } else { '' })
    Check 'M2' 'другие шаги на run_measure.ps1 (не 03, метка не hand_*): строк «ЧАСТОТА ДЕТЕКТОРА», «JOINT RMS» и «НЕ ЛЕТАТЬ» нет - вывод как в r16' ($r.Guard -and $r.Code -eq 0 -and $sf.Count -eq 1 -and -not $st.Contains('ЧАСТОТА ДЕТЕКТОРА') -and -not $st.Contains('JOINT RMS') -and -not $st.Contains('НЕ ЛЕТАТЬ')) ('code=' + $r.Code)
}

# ======================= E: 07 (не менялся) видит журналы пакета В1.1 drone_pkg_posefix_v1x_20261119 (шаги 48/49) =======================
if (Want 'E') {
    $p07 = Join-Path $SB 'run_07_takeoff.ps1'
    $conf = Join-Path $SB 'takeoff.conf'; $gate = Join-Path $SB 'gates\TAKEOFF_APPROVED.txt'
    $cf = @{}; foreach ($l in [IO.File]::ReadAllLines($conf)) { $t9 = $l.Trim(); if ($t9 -eq '' -or $t9.StartsWith('#')) { continue }; $i = $t9.IndexOf('='); if ($i -gt 0) { $cf[$t9.Substring(0, $i).Trim()] = $t9.Substring($i + 1).Trim() } }
    [IO.File]::WriteAllText($gate, ("ШАГ=14`r`nВЗЛЁТ_РАЗРЕШИЛ=владелец`r`nДАТА=2026-11-18 тест`r`nСЛОВА_ВЛАДЕЛЬЦА=тест r17`r`nСКРИПТ_SHA256=" + $cf['SCRIPT_SHA256'] + "`r`nАРГУМЕНТЫ=`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
    $strict = '=== СОВПАДАЕТ: прочитано 1127 из 1127, отличий нет (из таблицы MAVROS 1127, из запасного потока 0) ==='
    function New-Out07([string]$name, [int]$age09 = 5, [int]$age10 = 5, [string]$from09 = '') {
        $o = New-OutDir ('e_' + $name)
        $rp = Join-Path $o 'params_bench_t_report.txt'; [IO.File]::WriteAllText($rp, $strict + "`r`n", $utf8)
        $c9 = Join-Path $o 'install_check_20261118_080000.txt'
        if ($from09) { Copy-Item -LiteralPath $from09 -Destination $c9 } else { [IO.File]::WriteAllText($c9, "BB_INSTALL_CHECK_DONE`r`n# VERDICT OK`r`n", $utf8) }
        (Get-Item -LiteralPath $c9).LastWriteTime = (Get-Date).AddMinutes(-$age09)
        $c10 = Join-Path $o 'mavros_check_20261118_080000.txt'; [IO.File]::WriteAllText($c10, "BB_DONE`r`n# VERDICT OK`r`n", $utf8); (Get-Item -LiteralPath $c10).LastWriteTime = (Get-Date).AddMinutes(-$age10)
        return $o
    }
    $script:asideN = 0
    function Clear-Pkgs { $script:asideN++; $a = Join-Path $Run ('pkg_aside_' + $script:asideN); foreach ($d in @(Get-ChildItem -LiteralPath $SBP -Directory | Where-Object { $_.Name -like 'drone_pkg_*' })) { if (-not (Test-Path $a)) { New-Item -ItemType Directory -Path $a | Out-Null }; Move-Item -LiteralPath $d.FullName -Destination $a } }
    function Pkg-File([string]$pkg, [string]$name, [double]$ageMin) { $d = Join-Path $SBP ($pkg + '\out'); New-Item -ItemType Directory -Force -Path $d | Out-Null; $f = Join-Path $d $name; [IO.File]::WriteAllText($f, "тест`r`n", $utf8); (Get-Item -LiteralPath $f).LastWriteTime = (Get-Date).AddMinutes(-$ageMin); return $f }
    $badSha = ('cd' * 32) + '  ' + $cf['SCRIPT_REMOTE_PATH']
    function Run07([string]$o) { Reset-Fake 'normal' '' $badSha; return (Run-Ps 'run_07_takeoff.ps1' $o '-SafetyConfirmed NET-TWO-KILL-YES' -ChildGuard) }
    function Passed($r) { return ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -ge 2 -and $r.Console -match 'sha256 не равен' -and $r.Console -notmatch 'взлёт не разрешён' -and @($r.Calls | Where-Object { $_ -notmatch [regex]::Escape($Marker) }).Count -eq 0) }
    function Refused($r, [string]$what) { return ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'взлёт не разрешён' -and $r.Console -match 'ДО последней установки или отката пакета на дрон' -and $r.Console.Contains($what)) }
    Check 'E0' '07 r17 = run_07_takeoff.ps1 r16 = r14 = r13 = r12 байт в байт (sha a6af9787…, ворота 07 не трогались)' ((Sha $p07) -eq $S07R12) (Sha $p07)
    $pk = 'drone_pkg_posefix_v1x_20261119'
    Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_install_20261118_120000.log' 2; $r = Run07 (New-Out07 'e1_inst')
    Check 'E1' '07: журнал 48 (drone_pkg_posefix_v1x_20261119\out\posefix_v1_install_*.log) через 3 мин ПОСЛЕ 09 - код 4 до подделки ssh, с именем журнала' (Refused $r ($pk + '\out\posefix_v1_install_20261118_120000.log')) ('code=' + $r.Code + ' calls=' + $r.Calls.Count + ' ' + $r.Console)
    Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_rollback_20261118_120000.log' 2; $r = Run07 (New-Out07 'e2_rb')
    Check 'E2' '07: журнал 49 (откат В1.1) после 09 - код 4 до подделки' (Refused $r ($pk + '\out\posefix_v1_rollback_20261118_120000.log')) ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_install_20261118_070000.log' 30; $null = Pkg-File $pk 'posefix_v1_install_20261118_070000.txt' 2; $r = Run07 (New-Out07 'e3_sib')
    Check 'E3' '07: .log 48 старше 09, но вывод того же запуска (.txt) новее 09 - код 4' (Refused $r 'posefix_v1_install_20261118_070000.log') ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_install_20261118_070000.log' 30; $null = Pkg-File 'drone_pkg_r2m_cam_20261117' 'r2m_cam_install_20261117_070000.log' 40; $r = Run07 (New-Out07 'e4_older')
    Check 'E4' '07: журналы 48 и 44 СТАРШЕ 09 - условия пройдены, 07 дошёл до подделки (все вызовы ssh с меткой подделки)' (Passed $r) ('code=' + $r.Code + ' ' + $r.Console)
    Clear-Pkgs; $o = New-Out07 'e5_kitout'; $f = Join-Path $o 'posefix_v1_install_20261118_120000.log'; [IO.File]::WriteAllText($f, "тест`r`n", $utf8); (Get-Item -LiteralPath $f).LastWriteTime = (Get-Date).AddMinutes(-2)
    $r = Run07 $o; Check 'E5' '07: журнал В1.1 попал в out набора (BB_KIT_OUT) и он новее 09 - код 4 (шаблон posefix_ его покрывает)' (Refused $r 'out\posefix_v1_install_20261118_120000.log') ('code=' + $r.Code + ' ' + $r.Console)
    if ($r09v1) {
        Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_install_20261118_070000.log' 30
        $r = Run07 (New-Out07 'e6_real09' 5 5 $r09v1); Check 'E6' '07: настоящий отчёт 09 r17 (В1.1 + r2m_cam: 2 POSEFIX_V11 и 2 R2M_CAM, «# VERDICT OK»), сделан после 48 - условия пройдены (до подделки)' (Passed $r) ('code=' + $r.Code + ' ' + $r.Console)
        Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_install_20261118_120000.log' 2
        $r = Run07 (New-Out07 'e7_real09_late' 5 5 $r09v1); Check 'E7' '07: тот же настоящий отчёт 09 r17, но журнал 48 позже него - код 4' (Refused $r 'posefix_v1_install_20261118_120000.log') ('code=' + $r.Code + ' ' + $r.Console)
    }
    elseif (-not (Want 'W')) { Note 'E6, E7, E8, E9 пропущены: раздел W (источник настоящих отчётов 09 r17) не запускался' }
    else { Check 'E6' 'нет настоящего отчёта 09 r17 В1.1 + r2m_cam (W6 не прошёл)' $false '' }
    if ($r09mix) {
        Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_install_20261118_070000.log' 30
        $r = Run07 (New-Out07 'e8_mix09' 5 5 $r09mix); Check 'E8' '07: настоящий отчёт 09 r17 со смесью (aruco jd2 + vpe В1.1, «# VERDICT NOT_OK») - код 4 до подделки, «не успешна»' ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'не успешна') ('code=' + $r.Code)
    }
    if ($r09old) {
        Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_install_20261118_070000.log' 30
        $r = Run07 (New-Out07 'e9_old09' 5 5 $r09old); Check 'E9' '07: настоящий отчёт 09 r17, когда на дроне старый В1 (aruco 890dafbf, «# VERDICT NOT_OK») - код 4 до подделки, «не успешна»' ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'не успешна') ('code=' + $r.Code)
    }
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

# ======================= K: r17 = копия r16 + ожидаемые правки =======================
if (Want 'K') {
    $r14 = Join-Path (Split-Path -Parent $Kit) 'bench_kit_20261118_r16'   # имя переменной из r16, здесь это r16
    if (Test-Path -LiteralPath $r14) {
        $changed = @('lib\bb_lists.ps1', 'run_install_check.ps1', 'run_fingerprint.ps1', 'pi\install_check.sh', 'pi\overlay_fingerprint.sh', 'run_measure.ps1', 'pi\vision_measure.sh', 'SHA256SUMS.txt')
        $movedAside = @('image_r2j\POSEFIX_V1_20261118.tsv')   # перенесён в _aside\r16_POSEFIX_V1_20261118.tsv
        $r14f = @(Get-ChildItem -LiteralPath $r14 -Recurse -File | ForEach-Object { $_.FullName.Substring($r14.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and $_ -notmatch '^tests\\run_[^\\]+\\' })
        $miss = @(); $diff = @(); $same = 0
        foreach ($rel in $r14f) { $k = Join-Path $Kit $rel; if ($movedAside -contains $rel) { if (-not (Test-Path -LiteralPath (Join-Path $Kit '_aside\r16_POSEFIX_V1_20261118.tsv')) -or (Test-Path -LiteralPath $k)) { $miss += ($rel + ' (не перенесён в _aside)') }; continue }; if (-not (Test-Path -LiteralPath $k)) { $miss += $rel; continue }; if ((Sha $k) -ne (Sha (Join-Path $r14 $rel))) { if ($changed -notcontains $rel) { $diff += $rel } } else { $same++ } }
        Check 'K1' ('все файлы r16 есть в r17 (список В1 перенесён в _aside); изменены только ожидаемые 8 (bb_lists, 09, 15, install_check.sh, overlay_fingerprint.sh, run_measure.ps1, vision_measure.sh, SHA256SUMS), байт в байт одинаковых: ' + $same) ($miss.Count -eq 0 -and $diff.Count -eq 0) (($miss + $diff) -join ', ')
        $chg = @($changed | Where-Object { $_ -ne 'SHA256SUMS.txt' -and (Sha (Join-Path $Kit $_)) -ne (Sha (Join-Path $r14 $_)) })
        Check 'K1b' 'все 7 ожидаемых файлов действительно изменены' ($chg.Count -eq 7) ($chg -join ', ')
        $newOk = '^(README_r17\.md|DIFF_r16_r17\.txt|image_r2j\\POSEFIX_V11_20261119\.tsv|_aside\\r16_POSEFIX_V1_20261118\.tsv|tests\\run_tests_r17\.ps1|tests\\run_tests_r17_pi\.sh|tests\\r17_wsl_tree\.sh|proverka_r17\\.+|tests\\run_[^\\]+\\.+)$'
        $new = @(Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object { $_.FullName.Substring($Kit.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and -not (Test-Path -LiteralPath (Join-Path $r14 $_)) -and $_ -notmatch $newOk })
        Check 'K2' 'новых файлов, кроме ожидаемых (README_r17, DIFF_r16_r17, список В1.1, старый список В1 в _aside, тесты r17, proverka_r17), нет' ($new.Count -eq 0) ($new -join ', ')
        $rd = @('README.md', 'README_r13.md', 'README_r14.md', 'README_r16.md', 'PROGRESS.md', 'run_07_takeoff.ps1', '03_v_rukakh.cmd', 'image_r2j\POSEFIX_JD2_20261117.tsv', 'image_r2j\R2M_CAM_20261117.tsv') | Where-Object { (Sha (Join-Path $Kit $_)) -ne (Sha (Join-Path $r14 $_)) }
        Check 'K5' 'README, README_r13/r14/r16, PROGRESS.md, 07, 03_v_rukakh.cmd и списки jd2 и r2m_cam не менялись (байт в байт как в r16)' (@($rd).Count -eq 0) (@($rd) -join ', ')
    }
    else { Check 'K0' 'папка r16 рядом не найдена: сравнение с r16 не сделано' $false $r14 }
    Check 'K3' 'gates\: TAKEOFF_APPROVED.txt и OVERLAY_*_APPROVED.txt нет; image_r2j\gates\S2_S3_PASSED.txt нет' (-not (Test-Path (Join-Path $Kit 'gates\TAKEOFF_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'gates\OVERLAY_MAVROS_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'gates\OVERLAY_BUMBLEBEE_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'image_r2j\gates\S2_S3_PASSED.txt'))) ''
    $outFiles = @(Get-ChildItem -LiteralPath (Join-Path $Kit 'out') -File -ErrorAction SilentlyContinue)
    Check 'K4' 'out\ набора r17 пуст (тесты пишут только в tests\run_r17_*)' ($outFiles.Count -eq 0) (($outFiles | ForEach-Object { $_.Name }) -join ', ')
}

$env:PATH = $oldPath
Note ''
Note ('WSL-песочница: ' + $WB + ' (не удалялась)')
Note ('ИТОГ r17: PASS ' + $script:pass + ', FAIL ' + $script:fail)
exit $script:fail
