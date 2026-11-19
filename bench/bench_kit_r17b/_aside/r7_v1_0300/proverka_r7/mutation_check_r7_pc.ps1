# mutation_check_r7_pc.ps1 (Claude, 13.11.2026, набор r7) - «у тестов есть зубы»: на КОПИИ набора r7 портит по одному месту и проверяет, что
# tests\run_tests_r7.ps1 ловит порчу ровно в ожидаемых проверках. Сам набор не меняет. К дрону не обращается (тесты - на подделке ssh).
# Копия: <Work>\bench_kit_20261113_r7 (без tests\run_* и out\), рядом пустые заглушки kit_20261109_r4\params_check\params_check.cmd и папка
# bench_kit_20261112_r6 (их проверяют R1 и R2). Сначала прогон копии без порчи (M0: ждём FAIL 0). Итог - в -Report (не перезаписывается).
param([Parameter(Mandatory = $true)][string]$Work, [Parameter(Mandatory = $true)][string]$Report)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$kit = Split-Path -Parent $here
if (Test-Path -LiteralPath $Work) { Write-Host ('уже есть ' + $Work + ', не перезаписываю'); exit 4 }
if (Test-Path -LiteralPath $Report) { Write-Host ('уже есть ' + $Report + ', не перезаписываю'); exit 4 }
$cp = Join-Path $Work 'bench_kit_20261113_r7'
New-Item -ItemType Directory -Path $cp | Out-Null
Get-ChildItem -LiteralPath $kit -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($kit.Length + 1)
    if ($rel -match '^tests\\run_r[0-9a-z_]*_\d{8}|^tests\\run_[a-z]_\d{8}|^out\\') { return }
    $d = Join-Path $cp $rel; New-Item -ItemType Directory -Force -Path (Split-Path $d) | Out-Null; Copy-Item -LiteralPath $_.FullName -Destination $d
}
New-Item -ItemType Directory -Path (Join-Path $cp 'out') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Work 'kit_20261109_r4\params_check') | Out-Null
[IO.File]::WriteAllText((Join-Path $Work 'kit_20261109_r4\params_check\params_check.cmd'), "rem заглушка для теста R1`r`n")
New-Item -ItemType Directory -Path (Join-Path $Work 'bench_kit_20261112_r6') | Out-Null
$lines = New-Object Collections.Generic.List[string]
$lines.Add('# mutation_check_r7_pc.ps1 -Work ' + $Work + ': начало ' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + ' по часам ПК')
function RunTests([string]$name) {
    $so = Join-Path $Work ($name + '_console.txt')
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $cp 'tests\run_tests_r7.ps1') + '"') -NoNewWindow -PassThru -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $null = $p.Handle; try { $p.PriorityClass = 'BelowNormal' } catch { }
    $p.WaitForExit()
    $txt = [IO.File]::ReadAllText($so)
    $fails = @($txt -split "`r?`n" | Where-Object { $_ -match '^FAIL ' } | ForEach-Object { ($_ -split ' ')[1] } | Sort-Object -Unique)
    $it = @($txt -split "`r?`n" | Where-Object { $_ -match '^ИТОГ' }) | Select-Object -Last 1
    return @{ Fails = $fails; Itog = $it }
}
function Spoil([string]$rel, [string]$from, [string]$to, [int]$need = 1) {
    $f = Join-Path $cp $rel
    $t = [IO.File]::ReadAllText($f)
    $n = ([regex]::Matches($t, [regex]::Escape($from))).Count
    if ($n -lt $need) { throw ('порча не легла: «' + $from + '» в ' + $rel + ' найдено ' + $n) }
    $enc = New-Object Text.UTF8Encoding(([IO.File]::ReadAllBytes($f))[0] -eq 0xEF)
    [IO.File]::WriteAllText($f, $t.Replace($from, $to), $enc)
    return ('порча: ' + $rel + ' («' + $from.Substring(0, [Math]::Min(60, $from.Length)) + '…», мест ' + $n + ')')
}
$base = RunTests 'M0'
$lines.Add('MUT M0 (без порчи): ' + $base.Itog + '; FAIL: ' + (($base.Fails) -join ', '))
$ok = ($base.Fails.Count -eq 0)
$muts = @(
    @{ id = 'M1'; what = 'детектор молчит, а шаг идёт дальше (нет НЕ ПРОВЕРЕНО при msgs=0; фаза rec сама откажет без удачной проверки, поэтому ловит N5)'; want = @('N5'); do = { Spoil 'run_r7_metki.ps1' 'if ($m0 -eq 0) {' 'if ($m0 -lt 0) {' } },
    @{ id = 'M2'; what = 'номер не 0 не считается ложным'; want = @('N10', 'N12'); do = { Spoil 'run_r7_metki.ps1' 'if ([int]$Matches[1] -eq 0) { $seen0 = $true }' 'if ([int]$Matches[1] -ge 0) { $seen0 = $true }' } },
    @{ id = 'M3'; what = 'фаза rec запускается без «< nul» (PowerShell мог бы съесть ответы окна)'; want = @('N2'); do = { Spoil '25_metki_nomera.cmd' '-Phase rec -Stamp %STAMP% -Cm %2 < nul' '-Phase rec -Stamp %STAMP% -Cm %2' } },
    @{ id = 'M4'; what = 'нет отказа перезаписи до обращения к дрону'; want = @('N18', 'N20'); do = { Spoil 'run_r7_metki.ps1' '{ $null = BB-NewOutFile $outDir $n }   # не перезаписывать' '{ }   # не перезаписывать' } },
    @{ id = 'M5'; what = 'нет сверки числа строк MN_MSG с msgs'; want = @('N15'); do = { Spoil 'run_r7_metki.ps1' 'if ($nMsg -ne $msgs)' 'if ($false)' } },
    @{ id = 'M6'; what = 'BACKUP_ROOT в /tmp принимается'; want = @('B4', 'B5', 'B6', 'B7'); do = { Spoil 'image_r2j\backup_root_r7.ps1' "foreach (`$s in '/tmp', '/var/tmp'" "foreach (`$s in '/nonexistent', '/var/tmp'" } },
    @{ id = 'M7'; what = 'BACKUP_ROOT вписан в набор без слова владельца'; want = @('B1', 'B3', 'B6', 'B9', 'G1', 'G2', 'G3', 'G6', 'G7', 'K3'); do = { Spoil 'image_r2j\image_target.conf' 'BACKUP_ROOT=TBD' 'BACKUP_ROOT=/home/lb/bb_backup' } },
    @{ id = 'M8'; what = 'в манифесте и payload нет state_link.h (файл r2j, нужна пересборка)'; want = @('P1', 'P3', 'P12', 'P13', 'P19', 'P22'); do = {
        $m = Join-Path $cp 'image_r2j\image_manifest.final.tsv'; $x = [IO.File]::ReadAllText($m)
        $row = ([regex]::Match($x, '(?m)^ros2_ws/src/bumblebee/src/cpp/state_link\.h\t[0-9a-f]{64}\n')).Value; if (-not $row) { throw 'нет строки state_link.h' }
        [IO.File]::WriteAllText($m, $x.Replace($row, ''), (New-Object Text.UTF8Encoding($false)))
        Remove-Item -LiteralPath (Join-Path $cp 'image_r2j\payload\ros2_ws\src\bumblebee\src\cpp\state_link.h'); 'порча: строка и файл state_link.h убраны' } },
    @{ id = 'M9'; what = 'fcu_detect.py образа (прежний) положен в payload и манифест'; want = @('P1', 'P2', 'P3', 'P5', 'P12', 'G1', 'G2', 'G3', 'G4', 'B8'); do = {
        $src = Join-Path '\\wsl.localhost\Ubuntu-24.04\work\fixed_image_r2j_20261111' 'src\bumblebee\scripts\fcu_detect.py'; $dst = Join-Path $cp 'image_r2j\payload\ros2_ws\src\bumblebee\scripts\fcu_detect.py'
        New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null; Copy-Item -LiteralPath $src -Destination $dst
        $m = Join-Path $cp 'image_r2j\image_manifest.final.tsv'; [IO.File]::AppendAllText($m, ('ros2_ws/src/bumblebee/scripts/fcu_detect.py' + "`t" + (Get-FileHash -Algorithm SHA256 -LiteralPath $dst).Hash.ToLower() + "`n"), (New-Object Text.UTF8Encoding($false))); 'порча: fcu_detect.py добавлен' } }
)
foreach ($mu in $muts) {
    $snap = Join-Path $Work ('snap_' + $mu.id); Copy-Item -LiteralPath (Join-Path $cp 'image_r2j') -Destination $snap -Recurse
    $files = @('run_r7_metki.ps1', '25_metki_nomera.cmd'); foreach ($f in $files) { Copy-Item -LiteralPath (Join-Path $cp $f) -Destination (Join-Path $Work ('snap_' + $mu.id + '_' + $f)) }
    $desc = & $mu.do
    $r = RunTests $mu.id
    $new = @($r.Fails | Where-Object { $_ -notin $base.Fails })
    $missing = @($mu.want | Where-Object { $_ -notin $new }); $extra = @($new | Where-Object { $_ -notin $mu.want })
    $res = $(if ($new.Count -gt 0 -and $missing.Count -eq 0 -and $extra.Count -eq 0) { 'поймано' } elseif ($new.Count -gt 0) { 'поймано, но не там' } else { 'НЕ ПОЙМАНО' })
    if ($res -ne 'поймано') { $ok = $false }
    $lines.Add('MUT ' + $mu.id + ' (' + $mu.what + '): ' + $res + '; FAIL: ' + ($new -join ', ') + $(if ($missing.Count) { '; ждали ещё: ' + ($missing -join ', ') } else { '' }) + $(if ($extra.Count) { '; лишние: ' + ($extra -join ', ') } else { '' }) + '  [' + $desc + ']')
    Remove-Item -LiteralPath (Join-Path $cp 'image_r2j') -Recurse -Force; Copy-Item -LiteralPath $snap -Destination (Join-Path $cp 'image_r2j') -Recurse
    foreach ($f in $files) { Copy-Item -LiteralPath (Join-Path $Work ('snap_' + $mu.id + '_' + $f)) -Destination (Join-Path $cp $f) -Force }
}
$lines.Add('# конец ' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + '; ИТОГ: ' + $(if ($ok) { 'все порчи пойманы ровно в ожидаемых проверках, без порчи FAIL 0' } else { 'ЕСТЬ НЕПОЙМАННЫЕ или лишние - смотреть строки выше' }))
[IO.File]::WriteAllText($Report, (($lines -join "`r`n") + "`r`n"), (New-Object Text.UTF8Encoding($true)))
$lines | ForEach-Object { Write-Host $_ }
if ($ok) { exit 0 } else { exit 1 }