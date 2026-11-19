# make_sums_diff_r7.ps1 (Claude, 13.11.2026, набор r7) - пишет DIFF_r6_r7.txt (что добавлено, изменено, перенесено против r6, плюс diff -u текстов) и
# SHA256SUMS.txt (sha256 каждого файла набора, кроме самого SHA256SUMS.txt; формат «sha256  путь», пути через /, порядок по байтам).
# Основа r6 - _aside\SHA256SUMS_r6_copy.txt (sha256 7498ee24...). Ничего не перезаписывает (при наличии - отказ). Папки прогонов тестов tests\run_* в суммы не идут:
# перед запуском их нужно перенести из набора (скрипт откажет, если они есть). К дрону не обращается.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$kit = Split-Path -Parent $here
$sumsP = Join-Path $kit 'SHA256SUMS.txt'; $diffP = Join-Path $kit 'DIFF_r6_r7.txt'
foreach ($x in $sumsP, $diffP) { if (Test-Path -LiteralPath $x) { Write-Host ('уже есть ' + $x + ', не перезаписываю'); exit 4 } }
$runs = @(Get-ChildItem -LiteralPath (Join-Path $kit 'tests') -Directory -Filter 'run_*')
if ($runs.Count -gt 0) { Write-Host ('в tests есть папки прогонов (' + (($runs | ForEach-Object { $_.Name }) -join ', ') + '): перенесите их из набора'); exit 4 }
$pyc = @(Get-ChildItem -LiteralPath $kit -Recurse -Directory -Filter '__pycache__')
if ($pyc.Count -gt 0) { Write-Host ('в наборе есть __pycache__: ' + (($pyc | ForEach-Object { $_.FullName }) -join ', ')); exit 4 }
$r6p = Join-Path $kit '_aside\SHA256SUMS_r6_copy.txt'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $r6p).Hash.ToLower() -ne '7498ee2437fbf2aae97dfb6e02861d401fccd9b20589e87d85408c0af819afc4') { Write-Host 'список r6 в _aside не тот'; exit 4 }
$r6 = @{}; foreach ($l in [IO.File]::ReadAllLines($r6p)) { if ($l -match '^([0-9a-f]{64})  (.+)$') { $r6[$Matches[2]] = $Matches[1] } }
function RelOf([string]$full) { return ($full.Substring($kit.Length + 1) -replace '\\', '/') }
$files = @(Get-ChildItem -LiteralPath $kit -Recurse -File | ForEach-Object { RelOf $_.FullName } | Where-Object { $_ -ne 'SHA256SUMS.txt' -and $_ -ne 'DIFF_r6_r7.txt' })
$sha = @{}; foreach ($f in $files) { $sha[$f] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $kit ($f -replace '/', '\'))).Hash.ToLower() }
$added = @($files | Where-Object { -not $r6.ContainsKey($_) }); [Array]::Sort($added, [StringComparer]::Ordinal)
$changed = @($files | Where-Object { $r6.ContainsKey($_) -and $r6[$_] -ne $sha[$_] }); [Array]::Sort($changed, [StringComparer]::Ordinal)
$gone = @($r6.Keys | Where-Object { -not $sha.ContainsKey($_) -and $_ -ne 'SHA256SUMS.txt' })
$d = New-Object Collections.Generic.List[string]
$d.Add('# DIFF_r6_r7.txt (Claude, ' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + ' по часам ПК; proverka_r7\make_sums_diff_r7.ps1). Основа: r6, SHA256SUMS 7498ee24... (копия в _aside\SHA256SUMS_r6_copy.txt).')
$d.Add('# Файлов r6: ' + $r6.Count + '; в r7 без изменений: ' + ($r6.Count - $changed.Count - $gone.Count) + '; изменено: ' + $changed.Count + '; добавлено: ' + $added.Count + '; убрано: ' + $gone.Count + ' (SHA256SUMS.txt r6 перенесён в _aside, новый написан заново).')
$d.Add('ПЕРЕНЕСЁН SHA256SUMS.txt (r6, 7498ee24...) -> _aside/SHA256SUMS_r6_copy.txt')
foreach ($f in $changed) { $d.Add('ИЗМЕНЁН ' + $f + '  ' + $r6[$f] + ' -> ' + $sha[$f]) }
foreach ($f in $added) { $d.Add('ДОБАВЛЕН ' + $f + '  ' + $sha[$f]) }
foreach ($f in $gone) { $d.Add('УБРАН ' + $f + '  ' + $r6[$f]) }
$r6dir = Join-Path (Split-Path $kit) 'bench_kit_20261112_r6'
$bash = 'C:\Program Files\Git\usr\bin\diff.exe'
foreach ($f in $changed) {
    $d.Add(''); $d.Add('===== diff -u r6/' + $f + ' r7/' + $f)
    if (Test-Path -LiteralPath $bash) {
        $o = & $bash -u (Join-Path $r6dir ($f -replace '/', '\')) (Join-Path $kit ($f -replace '/', '\')) 2>&1 | Out-String
        $d.Add($o.TrimEnd())
    } else { $d.Add('(diff.exe не найден, сравнение только по sha256 выше)') }
}
[IO.File]::WriteAllText($diffP, (($d -join "`n") + "`n"), (New-Object Text.UTF8Encoding($false)))
$all = @($files) + @('DIFF_r6_r7.txt'); [Array]::Sort($all, [StringComparer]::Ordinal)
$sha['DIFF_r6_r7.txt'] = (Get-FileHash -Algorithm SHA256 -LiteralPath $diffP).Hash.ToLower()
[IO.File]::WriteAllText($sumsP, ((($all | ForEach-Object { $sha[$_] + '  ' + $_ }) -join "`n") + "`n"), (New-Object Text.UTF8Encoding($false)))
Write-Host ('DIFF_r6_r7.txt: изменено ' + $changed.Count + ', добавлено ' + $added.Count + ', убрано ' + $gone.Count)
Write-Host ('SHA256SUMS.txt: строк ' + $all.Count + ', sha256 ' + (Get-FileHash -Algorithm SHA256 -LiteralPath $sumsP).Hash.ToLower())
exit 0