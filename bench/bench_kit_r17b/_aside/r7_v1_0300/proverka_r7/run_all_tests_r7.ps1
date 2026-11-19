# run_all_tests_r7.ps1 (Claude, 13.11.2026, набор r7) - прогон ВСЕХ тестов набора на r7 по одному (один поток): тесты r5 (стенд, Pi, образ), тесты r6 (ПК и Pi)
# без единой правки и новые тесты r7 (ПК и Pi). К дрону не подключается: все тесты на подделках. Процессы тестов - с приоритетом ниже обычного; всё, что идёт
# в WSL, - через обёртку wsl.exe r6 (proverka_r6\wsl_nice_wrapper.cs): дистрибутив Ubuntu-24.04, nice -n 19 ionice -c3 (рядом работает Симулятор).
# -WslSandbox: папка WSL для песочниц тестов Pi (по умолчанию /tmp). Итоги - proverka_r7\tests_r7_svodka.txt (при наличии - отказ, не перезаписывает),
# вывод каждого - proverka_r7\tests_<имя>_console.txt. После прогона - проверка, что во всех журналах подделок ssh вызывался только как подделка.
param([string]$WslSandbox = '/tmp', [string[]]$Only = @())
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$kit = Split-Path -Parent $here
$sv = Join-Path $here 'tests_r7_svodka.txt'
if (Test-Path -LiteralPath $sv) { Write-Host ('уже есть ' + $sv + ', не перезаписываю'); exit 4 }
$names = @('r5_bench', 'r5_pi', 'r5_image', 'r6_pc', 'r6_pi', 'r7_pc', 'r7_pi')
foreach ($n in $names) { $c = Join-Path $here ('tests_' + $n + '_console.txt'); if (Test-Path -LiteralPath $c) { Write-Host ('уже есть ' + $c + ', не перезаписываю'); exit 4 } }
$wd = Join-Path ([IO.Path]::GetTempPath()) ('bb_r7_wslnice_' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $wd | Out-Null
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $kit 'proverka_r6\wsl_nice_wrapper.cs'))) -OutputAssembly (Join-Path $wd 'wsl.exe') -OutputType ConsoleApplication
$env:PATH = $wd + ';' + $env:PATH
# python в WSL не пишет __pycache__ в папки набора (тесты r5 Pi кладут tests\pystub в PYTHONPATH; иначе K4 r7 увидит лишние файлы)
$env:PYTHONDONTWRITEBYTECODE = '1'; $env:WSLENV = 'PYTHONDONTWRITEBYTECODE/u' + $(if ($env:WSLENV) { ':' + $env:WSLENV } else { '' })
$lines = New-Object Collections.Generic.List[string]
$lines.Add('# прогон тестов r7, начало ' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + ' (часы ПК); обёртка wsl: ' + (Join-Path $wd 'wsl.exe'))
function Run-One([string]$name, [string]$file, [string]$argLine) {
    $so = Join-Path $wd ($name + '.out.txt'); $se = Join-Path $wd ($name + '.err.txt')
    $t0 = Get-Date
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $file + '" ' + $argLine) -PassThru -NoNewWindow -RedirectStandardOutput $so -RedirectStandardError $se
    $null = $p.Handle
    try { $p.PriorityClass = 'BelowNormal' } catch { }
    $p.WaitForExit()
    $txt = [IO.File]::ReadAllText($so)
    $it = @($txt -split "`r?`n" | Where-Object { $_ -match '^ИТОГ' }) | Select-Object -Last 1
    $nf = @($txt -split "`r?`n" | Where-Object { $_ -match '^FAIL ' })
    $script:lines.Add(('{0}: код {1}, {2}, {3:N0} с' -f $name, $p.ExitCode, $it, ((Get-Date) - $t0).TotalSeconds))
    foreach ($f in $nf) { $script:lines.Add('  ' + $f) }
    Copy-Item -LiteralPath $so -Destination (Join-Path $here ('tests_' + $name + '_console.txt'))
}
function Run-Wsl([string]$name, [string]$rel) {
    $t0 = Get-Date
    $kw = (& wsl.exe wslpath -a ($kit.Replace('\', '/'))).Trim()
    $o = & wsl.exe -e bash ($kw + '/' + $rel) $WslSandbox 2>&1 | Out-String
    $rc = $LASTEXITCODE
    [IO.File]::WriteAllText((Join-Path $here ('tests_' + $name + '_console.txt')), $o, (New-Object Text.UTF8Encoding($false)))
    $it = @($o -split "`r?`n" | Where-Object { $_ -match '^ИТОГ' }) | Select-Object -Last 1
    $script:lines.Add(('{0}: код {1}, {2}, {3:N0} с' -f $name, $rc, $it, ((Get-Date) - $t0).TotalSeconds))
    foreach ($f in @($o -split "`r?`n" | Where-Object { $_ -match '^FAIL ' })) { $script:lines.Add('  ' + $f) }
}
$all = [ordered]@{
    'r5_bench' = (Join-Path $kit 'tests\run_tests_bench.ps1')
    'r5_pi'    = (Join-Path $kit 'tests\run_tests_pi.ps1')
    'r5_image' = (Join-Path $kit 'tests\run_tests_image.ps1')
    'r6_pc'    = (Join-Path $kit 'tests\run_tests_r6.ps1')
}
foreach ($k in $all.Keys) { if ($Only.Count -eq 0 -or $Only -contains $k) { Run-One $k $all[$k] '' } }
if ($Only.Count -eq 0 -or $Only -contains 'r6_pi') { Run-Wsl 'r6_pi' 'tests/run_tests_r6_pi.sh' }
if ($Only.Count -eq 0 -or $Only -contains 'r7_pc') { Run-One 'r7_pc' (Join-Path $kit 'tests\run_tests_r7.ps1') '' }
if ($Only.Count -eq 0 -or $Only -contains 'r7_pi') { Run-Wsl 'r7_pi' 'tests/run_tests_r7_pi.sh' }
# настоящий ssh не вызывался: каждый запуск шага печатает «ssh: <путь>» (BB-FindSsh) - во всех выводах прогонов путь только ...\tests\run_*\fake\ssh.exe;
# в журналах подделок (calls.log, у подделок с полем exe=) - тоже; упоминаний системного OpenSSH в выводах нет
$paths = @(); $exes = @(); $sys = 0
foreach ($c in @(Get-ChildItem -LiteralPath (Join-Path $kit 'tests') -Recurse -File -Include '*console.txt' -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match '\\tests\\run_' })) { foreach ($l in [IO.File]::ReadAllLines($c.FullName)) { if ($l -match '^ssh: (.+\.exe)\s*$') { $paths += $Matches[1] } } }
foreach ($cl in @(Get-ChildItem -LiteralPath (Join-Path $kit 'tests') -Recurse -File -Filter 'calls.log' -ErrorAction SilentlyContinue)) { foreach ($l in [IO.File]::ReadAllLines($cl.FullName)) { if ($l -match ' exe=(.+?\\ssh\.exe) ') { $exes += $Matches[1] } } }
foreach ($c in @(Get-ChildItem -LiteralPath $here -File -Filter 'tests_*_console.txt')) { if ([IO.File]::ReadAllText($c.FullName) -match '(?i)System32\\OpenSSH') { $sys++ } }
$badExe = @(@($paths) + @($exes) | Where-Object { $_ -notmatch '\\tests\\run_[^\\]+\\fake\\ssh\.exe$' } | Sort-Object -Unique)
$lines.Add(('ssh в выводах запусков шагов: {0} строк «ssh: путь»; в журналах подделок: {1}; не подделка: {2}; упоминаний System32\OpenSSH в выводах тестов: {3}' -f $paths.Count, $exes.Count, $badExe.Count, $sys))
if ($paths.Count -eq 0) { $lines.Add('  ВНИМАНИЕ: строк «ssh: путь» не найдено - проверка ничего не доказала') }
foreach ($b in $badExe) { $lines.Add('  НЕ ПОДДЕЛКА: ' + $b) }$lines.Add('# конец ' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))
[IO.File]::WriteAllText($sv, (($lines -join "`r`n") + "`r`n"), (New-Object Text.UTF8Encoding($false)))
$lines | ForEach-Object { Write-Host $_ }