# compare_params.ps1 (Claude, 09.11.2026) - ТОЛЬКО ЧТЕНИЕ файлов на ПК. К дрону не подключается.
# Сравнивает события /parameter_events (из params_read.sh) с утверждённым набором: основа + одобренные правки.
# Коды выхода: 0 совпало полностью; 2 СТОП (есть отличия, Ж6); 3 сверка неполная; 4 ошибка (нет файла, отказ перезаписать).
# r11 (16.11.2026, решение владельца «Не стоп, только запись»): отличия только в CAL_GYRO0..3_XOFF/YOFF/ZOFF - не СТОП, а запись (блок «Гироскоп сдвинулся»);
#   если других отличий нет - код 0 и первая строка «=== СОВПАДАЕТ (гироскоп сдвинулся: N, запись): ...». Любое другое отличие, в том числе CAL_ACC*, - СТОП, как раньше.
param(
    [Parameter(Mandatory = $true)][string]$Events,
    [Parameter(Mandatory = $true)][string]$OutPrefix,
    [string]$Baseline,
    [string]$Approved,
    [string]$Profiles,
    [string]$Ignore,
    [string]$Registry,
    [switch]$AllowStreamFallback,
    [string]$Label = ''
)
$ErrorActionPreference = 'Stop'
$inv = [Globalization.CultureInfo]::InvariantCulture
$nsF = [Globalization.NumberStyles]::Float
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Baseline) { $Baseline = Join-Path $here 'baseline_20261104_1145.params' }
if (-not $Approved) { $Approved = Join-Path $here 'approved_changes.txt' }
if (-not $Profiles) { $Profiles = Join-Path $here 'profile_values.tsv' }
if (-not $Ignore)   { $Ignore   = Join-Path $here 'ignore_counters.txt' }
if (-not $Registry) {
    if ($env:BB_REGISTRY) { $Registry = $env:BB_REGISTRY }
    else { $Registry = Join-Path (Split-Path -Parent (Split-Path -Parent $here)) 'РЕЕСТР_НАСТРОЕК_ДРОНА.md' }
}
$utf8bom = New-Object Text.UTF8Encoding($true)

function Fail($msg) { Write-Host ("ОШИБКА: " + $msg) -ForegroundColor White -BackgroundColor DarkRed; exit 4 }

foreach ($f in @($Events, $Baseline, $Approved, $Profiles, $Ignore)) {
    if (-not (Test-Path -LiteralPath $f)) { Fail ("нет файла " + $f) }
}
$outReport = $OutPrefix + '_report.txt'
$outParams = $OutPrefix + '.params'
$outNow    = $OutPrefix + '_now.txt'
$outExtra  = $OutPrefix + '_extra.txt'
foreach ($f in @($outReport, $outParams, $outNow, $outExtra)) {
    if (Test-Path -LiteralPath $f) { Fail ("файл уже есть, не перезаписываю: " + $f) }
}

function Read-DataLines([string]$path) {
    $r = New-Object Collections.Generic.List[string[]]
    foreach ($l in [IO.File]::ReadLines($path)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        $r.Add($l.Split("`t"))
    }
    return , $r
}

# ---------- основа ----------
$base = @{}          # имя -> @{T = текст значения; Ty = тип QGC}
$comp125 = 0
$c125 = @{}          # имя -> @{T; Ty} настроек компонента 125 из основы
foreach ($f in (Read-DataLines $Baseline)) {
    if ($f.Count -lt 5) { continue }
    if ($f[1] -eq '1') { $base[$f[2]] = @{ T = $f[3]; Ty = $f[4] } }
    elseif ($f[1] -eq '125') { $comp125++; $c125[$f[2]] = @{ T = $f[3]; Ty = $f[4] } }
}
# A-4 (r2): плагин param MAVROS 2.14 и bp02 фильтрует PARAM_VALUE только по номеру системы (SystemAndOk),
# компонент не проверяет. Имя, которое есть и у компонента 1, и у 125, может принести значение компонента 125.
$sharedNames = @($base.Keys | Where-Object { $c125.ContainsKey($_) } | Sort-Object)
$shared = @{}; foreach ($n in $sharedNames) { $shared[$n] = $true }
# ---------- одобренные правки ----------
$appr = @{}
foreach ($f in (Read-DataLines $Approved)) {
    if ($f.Count -ge 2) {
        $when = ''; if ($f.Count -ge 3) { $when = $f[2] }
        $who = ''; if ($f.Count -ge 4) { $who = $f[3] }
        $appr[$f[0]] = @{ T = $f[1]; When = $when; Who = $who }
    }
}
# ---------- реестр настроек (только чтение; ведёт чат 1) ----------
# Строки со статусом «поставлено» = одобрено и применено (добавляются к approved_changes.txt).
# Остальные, кроме «закрыто»: предлагается, ещё не на дроне (отдельная пометка в отчёте).
$proposed = @{}
$registryNote = ''
if (Test-Path -LiteralPath $Registry) {
    foreach ($l in [IO.File]::ReadLines($Registry)) {
        if (-not $l.StartsWith('|')) { continue }
        $c = @($l.Trim().Trim('|').Split('|') | ForEach-Object { $_.Trim() })
        if ($c.Count -lt 5 -or $c[0] -notmatch '^[A-Z][A-Z0-9_]+$') { continue }
        $st = $c[4]
        if ($st -match '^закрыто') { continue }
        if ($st -match '^поставлено') {
            if ($c[2] -match '^(-?\d+(?:[.,]\d+)?)') { $appr[$c[0]] = @{ T = ($Matches[1] -replace ',', '.'); When = 'реестр'; Who = 'РЕЕСТР: поставлено' } }
        }
        else { $proposed[$c[0]] = @{ Raw = $c[2]; St = $st } }
    }
}
else { $registryNote = 'Реестр не найден: ' + $Registry + '. Предложения не показаны.' }

# ---------- профили ----------
$prof = @{}          # имя -> список @{P = профиль; T = значение}
foreach ($f in (Read-DataLines $Profiles)) {
    if ($f.Count -ge 3) {
        if (-not $prof.ContainsKey($f[0])) { $prof[$f[0]] = New-Object Collections.Generic.List[object] }
        $prof[$f[0]].Add(@{ P = $f[1]; T = $f[2] })
    }
}
# ---------- счётчики ----------
$ign = @{}
foreach ($l in [IO.File]::ReadLines($Ignore)) { $t = $l.Trim(); if ($t -ne '' -and -not $t.StartsWith('#')) { $ign[$t] = $true } }

# ---------- события с дрона ----------
$read = @{}          # имя -> @{K = 'i' или 'd'; V = double}
$script:cur = $null; $script:ty = 0; $script:iv = $null; $script:dv = $null; $script:bv = $null
function Add-Read {
    if ($null -eq $script:cur) { return }
    if ($script:ty -eq 1 -and $null -ne $script:bv) {
        $v = 0.0; if ($script:bv) { $v = 1.0 }
        $script:read[$script:cur] = @{ K = 'i'; V = $v }
    }
    elseif ($script:ty -eq 2 -and $null -ne $script:iv) { $script:read[$script:cur] = @{ K = 'i'; V = [double]$script:iv } }
    elseif ($script:ty -eq 3 -and $null -ne $script:dv) { $script:read[$script:cur] = @{ K = 'd'; V = $script:dv } }
}
$script:read = $read
$script:pullFailed = $false; $script:pullNotes = New-Object Collections.Generic.List[string]
$table = @{}         # таблица MAVROS (get_parameters): строки "P<TAB>имя<TAB>i|d<TAB>значение"
foreach ($line in [IO.File]::ReadLines($Events)) {
    if ($line.StartsWith("PULL`t")) { $pf2 = $line.Split("`t"); if ($pf2.Count -ge 3) { if ($pf2[1] -eq 'FAILED') { $script:pullFailed = $true }; $script:pullNotes.Add($pf2[1] + ': ' + $pf2[2]) }; continue }
    if ($line.StartsWith("P`t")) {
        $pf = $line.Split("`t")
        if ($pf.Count -ge 4 -and ($pf[2] -eq 'i' -or $pf[2] -eq 'd')) {
            try { $table[$pf[1]] = @{ K = $pf[2]; V = [double]::Parse($pf[3], $nsF, $inv) } } catch { }
        }
        continue
    }
    if ($line.StartsWith('E ')) { $line = $line.Substring(2) }   # поток событий (запасной источник) идёт с префиксом "E "
    if ($line -match '^\s*-\s*name:\s*(\S+)\s*$') {
        Add-Read
        $script:cur = $Matches[1]; $script:ty = 0; $script:iv = $null; $script:dv = $null; $script:bv = $null
        continue
    }
    if ($null -eq $script:cur) { continue }
    if ($line -match '^\s+type:\s*(\d+)') { $script:ty = [int]$Matches[1] }
    elseif ($line -match '^\s+integer_value:\s*(-?\d+)') { $script:iv = [long]$Matches[1] }
    elseif ($line -match '^\s+double_value:\s*(\S+)') { $script:dv = [double]::Parse($Matches[1], $nsF, $inv) }
    elseif ($line -match '^\s+bool_value:\s*(\S+)') { $script:bv = ($Matches[1] -eq 'true') }
    elseif ($line -match '^\S') { Add-Read; $script:cur = $null }
}
Add-Read
# итоговое чтение: таблица MAVROS главная, поток событий запасной
function SameKV($a, $b) {
    if ($a.K -eq 'i' -and $b.K -eq 'i') { return ([long][math]::Round($a.V) -eq [long][math]::Round($b.V)) }
    return ([single]$a.V -eq [single]$b.V)
}
$stream = $read
$read = @{}; $srcOf = @{}; $disagree = New-Object Collections.Generic.List[string]
foreach ($k in $stream.Keys) { $read[$k] = $stream[$k]; $srcOf[$k] = 'stream' }
foreach ($k in $table.Keys) {
    if ($stream.ContainsKey($k) -and -not (SameKV $stream[$k] $table[$k])) { $disagree.Add($k) }
    $read[$k] = $table[$k]; $srcOf[$k] = 'table'
}
$script:read = $read

function Parse-Num([string]$t) { return [double]::Parse($t, $nsF, $inv) }
# равенство значения с дрона и значения из текста: int32 - точно, float - как float32
function Same([string]$text, [string]$bType, $k, [double]$v) {
    $b = Parse-Num $text
    if ($bType -eq '6' -and $k -eq 'i') { return ([long][math]::Round($b) -eq [long][math]::Round($v)) }
    return ([single]$b -eq [single]$v)
}
function Fmt($k, [double]$v) {
    if ($k -eq 'i') { return ([long][math]::Round($v)).ToString($inv) }
    return ([single]$v).ToString('R', $inv)
}

$expectedNames = @($base.Keys | Sort-Object)
$diffs = New-Object Collections.Generic.List[string]
$counters = New-Object Collections.Generic.List[string]
$profileLeft = New-Object Collections.Generic.List[string]
$missing = New-Object Collections.Generic.List[string]
$approvedOk = New-Object Collections.Generic.List[string]
$unknown = New-Object Collections.Generic.List[string]   # A-4: общие имена с компонентом 125, значение отличается
$gyro = New-Object Collections.Generic.List[string]      # r11: сдвиг поправок гироскопа - запись, не СТОП
$gotCount = 0

foreach ($n in $expectedNames) {
    if (-not $read.ContainsKey($n)) { $missing.Add($n); continue }
    $gotCount++
    $d = $read[$n]
    $b = $base[$n]
    $expT = $b.T; $src = 'основа'
    if ($appr.ContainsKey($n)) { $expT = $appr[$n].T; $src = 'одобрено ' + $appr[$n].When }
    $dtxt = Fmt $d.K $d.V
    if (Same $expT $b.Ty $d.K $d.V) {
        if ($appr.ContainsKey($n)) { $approvedOk.Add(("{0}: {1} (одобрено {2}; {3})" -f $n, $dtxt, $appr[$n].When, $appr[$n].Who)) }
        continue
    }
    # r11 (решение владельца 16.11 «Не стоп, только запись»): поправки гироскопа CAL_GYRO0..3_XOFF/YOFF/ZOFF PX4 переписывает сам (SENS_IMU_AUTOCAL) - запись, не СТОП.
    # Только эти 12 имён; CAL_ACC*, CAL_GYRO*_ID/PRIO/ROT и всё остальное - как раньше. Общие с компонентом 125 имена (CAL_GYRO0_*) - тоже запись, с пометкой.
    # r11b (чат 1, 16.11 после проверки): общие с компонентом 125 имена - как в r9, UNKNOWN (значение могло прийти не от автопилота).
    if (($n -cmatch '^CAL_GYRO[0-3]_[XYZ]OFF$') -and -not $shared.ContainsKey($n)) {
        $g125 = ''; if ($shared.ContainsKey($n)) { $g125 = '   [имя есть и у компонента 125: значение могло прийти от него]' }
        $gyro.Add(("{0}: ждали {1} ({2}), стало {3}{4}" -f $n, $expT, $src, $dtxt, $g125))
        continue
    }
    $tags = ''
    if ($prof.ContainsKey($n)) {
        $hit = @($prof[$n] | Where-Object { Same $_.T $b.Ty $d.K $d.V })
        if ($hit.Count -gt 0) {
            $names = ($hit | ForEach-Object { $_.P }) -join ', '
            $tags = '   <-- ЗНАЧЕНИЕ ПРОФИЛЯ СКРИПТОВ (' + $names + '): остаток профиля?'
        }
        else { $tags = '   [профильная настройка: скрипты её меняют]' }
    }
    $note = ''
    if ($proposed.ContainsKey($n)) {
        $note = '   [предлагается, ещё не на дроне: ' + $proposed[$n].Raw + ' (статус: ' + $proposed[$n].St + ')]'
        if ($proposed[$n].Raw -match '^(-?\d+(?:[.,]\d+)?)' -and (Same ($Matches[1] -replace ',', '.') $b.Ty $d.K $d.V)) { $note += '   <-- значение предложения УЖЕ на дроне, а в реестре нет статуса «поставлено»' }
    }
    if ($appr.ContainsKey($n)) { $note += '   [одобрена, ещё не применена; в основе было ' + $b.T + ']' }
    $line = ("{0}: на дроне {1}, ожидалось {2} ({3}){4}{5}" -f $n, $dtxt, $expT, $src, $tags, $note)
    if ($ign.ContainsKey($n)) { $counters.Add($line) }
    elseif ($shared.ContainsKey($n)) {
        # A-4: имя есть у компонентов 1 и 125, MAVROS не различает их. Это не СТОП, а UNKNOWN: значение не подтверждено.
        $c = $c125[$n]
        $rel = 'не равно ни значению компонента 1, ни компонента 125 из основы: проверить вручную'
        if (Same $c.T $c.Ty $d.K $d.V) { $rel = 'равно значению компонента 125 из основы (' + $c.T + '), то есть, скорее всего, это подмена компонентом 125' }
        $unknown.Add(("{0}: UNKNOWN: возможна подмена компонентом 125. На дроне {1}, ожидалось {2} ({3}); {4}{5}{6}" -f $n, $dtxt, $expT, $src, $rel, $tags, $note))
    }
    else { $diffs.Add($line) }
}

# значения профиля, которые уже лежат в основе
foreach ($n in ($prof.Keys | Sort-Object)) {
    if (-not $base.ContainsKey($n)) { continue }
    foreach ($p in $prof[$n]) {
        if (Same $base[$n].T $base[$n].Ty 'd' (Parse-Num $p.T)) {
            $profileLeft.Add(("{0} = {1}: значение профиля {2} уже в основе (это не новое отличие, но владелец должен это видеть)" -f $n, $base[$n].T, $p.P))
        }
    }
}

$extra = @($read.Keys | Where-Object { -not $base.ContainsKey($_) } | Sort-Object)
# r3 (O-4): общие имена, у которых в основе значения компонентов 1 и 125 РАВНЫ: совпадение с основой по ним не доказывает, что значение от компонента 1
$indist = @($sharedNames | Where-Object { $kk = 'd'; if ($base[$_].Ty -eq '6') { $kk = 'i' }; Same $c125[$_].T $base[$_].Ty $kk (Parse-Num $base[$_].T) })
$total = $expectedNames.Count

# ---------- вердикт ----------
$tableHit = @($expectedNames | Where-Object { $srcOf.ContainsKey($_) -and $srcOf[$_] -eq 'table' }).Count
$streamOnly = @($expectedNames | Where-Object { $srcOf.ContainsKey($_) -and $srcOf[$_] -eq 'stream' }).Count
$strictIncomplete = ($tableHit -lt $total) -and (-not $AllowStreamFallback)
$nowIncomplete = ''
if ($diffs.Count -gt 0) { $code = 2; $verdict = 'СТОП до решения владельца (Ж6): отличий от утверждённого набора: ' + $diffs.Count }
elseif ($missing.Count -gt 0) { $code = 3; $verdict = 'СВЕРКА НЕПОЛНАЯ: прочитано ' + $gotCount + ' из ' + $total + ' (таблица MAVROS ' + $tableHit + ', запасной поток ' + $streamOnly + '). Совпадение НЕ подтверждено. Повторить чтение.' }
elseif ($strictIncomplete) {
    $code = 3
    $verdict = 'СВЕРКА НЕПОЛНАЯ: в таблице MAVROS ' + $tableHit + ' из ' + $total + '; ещё ' + $streamOnly + ' значений только из запасного потока событий (он теряет события). Совпадение НЕ подтверждено. Повторить чтение.'
    $nowIncomplete = 'в таблице MAVROS ' + $tableHit + ' из ' + $total
}
elseif ($script:pullFailed) {
    $code = 3
    $verdict = 'НЕ ПОДТВЕРЖДЕНО: ParamPull вернул success=False, таблица MAVROS могла быть устаревшей. Прочитано ' + $gotCount + ' из ' + $total + '. Совпадение НЕ подтверждено. Повторить чтение.'
    $nowIncomplete = 'ParamPull не удался (success=False)'
}
elseif ($unknown.Count -gt 0) {
    $code = 3
    $verdict = 'НЕ ПОДТВЕРЖДЕНО (UNKNOWN): ' + $unknown.Count + ' имён есть и у компонента 1, и у компонента 125, MAVROS их не различает; значение могло прийти от компонента 125. Прочитано ' + $gotCount + ' из ' + $total + '. Совпадение НЕ подтверждено, а СТОП не объявлен: смотреть вручную.'
    $nowIncomplete = 'UNKNOWN у ' + $unknown.Count + ' имён (возможна подмена компонентом 125)'
}
elseif ($AllowStreamFallback -and $streamOnly -gt 0) {
    # A-6 (r2): отчёт с ключом -AllowStreamFallback не может начинаться со слова «СОВПАДАЕТ:», его не примет check_gates.ps1
    $code = 0
    $verdict = 'ЧЕРНОВИК, НЕ ДЛЯ ГЕЙТОВ (-AllowStreamFallback): отличий нет, прочитано ' + $gotCount + ' из ' + $total + ', но ' + $streamOnly + ' значений только из запасного потока (из таблицы MAVROS ' + $tableHit + ')'
}
elseif ($gyro.Count -gt 0) { $code = 0; $verdict = 'СОВПАДАЕТ (гироскоп сдвинулся: ' + $gyro.Count + ', запись): прочитано ' + $gotCount + ' из ' + $total + ', других отличий нет (из таблицы MAVROS ' + $tableHit + ', из запасного потока ' + $streamOnly + '); у ' + $indist.Count + ' имён значения компонентов 1 и 125 в основе равны, по ним компонент 1 не подтверждён' }
else { $code = 0; $verdict = 'СОВПАДАЕТ: прочитано ' + $gotCount + ' из ' + $total + ', отличий нет (из таблицы MAVROS ' + $tableHit + ', из запасного потока ' + $streamOnly + '); у ' + $indist.Count + ' имён значения компонентов 1 и 125 в основе равны, по ним компонент 1 не подтверждён' }

$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
$rep = New-Object Collections.Generic.List[string]
$rep.Add('=== ' + $verdict + ' ===')
if ($diffs.Count -gt 0 -and ($missing.Count -gt 0 -or $strictIncomplete)) { $rep.Add('Кроме того, сверка неполная: прочитано ' + $gotCount + ' из ' + $total + ', из таблицы MAVROS ' + $tableHit + '.') }
$rep.Add('')
$rep.Add('Сверка настроек ' + $stamp + ' ' + $Label)
$rep.Add('События: ' + $Events)
$rep.Add('Основа: ' + $Baseline)
$rep.Add('Реестр настроек (только чтение): ' + $Registry)
$rep.Add('Одобренных правок (файл + реестр «поставлено»): ' + $appr.Count)
$rep.Add('Прочитано из основы (компонент 1): ' + $gotCount + ' из ' + $total)
$rep.Add('Источники: таблица MAVROS (get_parameters) ' + $tableHit + ', запасной поток событий ' + $streamOnly + ', нигде нет ' + $missing.Count + '. Расхождений таблица/поток: ' + $disagree.Count + '.')
if ($diffs.Count -gt 0 -and $unknown.Count -gt 0) { $rep.Add('Кроме того, UNKNOWN (возможна подмена компонентом 125): ' + $unknown.Count + ' имён.') }
if ($script:pullNotes.Count -gt 0) { $rep.Add('ParamPull: ' + ($script:pullNotes -join '; ')) } else { $rep.Add('ParamPull: в выводе нет сведений о результате (старый params_read.sh?)') }
if ($AllowStreamFallback) { $rep.Add('Режим: значения из запасного потока считаются прочитанными (-AllowStreamFallback). ЭТОТ ОТЧЁТ НЕ ПРОХОДИТ ГЕЙТЫ.') }
else { $rep.Add('Режим: совпадение подтверждается только если все значения из таблицы MAVROS (поток теряет события, F3).') }
if ($disagree.Count -gt 0) { $rep.Add('Таблица и поток дали разные значения (побеждает таблица): ' + (($disagree | Sort-Object | Select-Object -First 20) -join ', ')) }
$rep.Add('Всего имён от MAVROS: ' + $read.Count + ' (не в основе: ' + $extra.Count + ', справочно, в файле _extra.txt)')
$rep.Add('Не покрыто сверкой: ' + $comp125 + ' настроек компонента 125. Плагин param MAVROS (2.14 и bp02) фильтрует по номеру системы, а не компонента (код: фильтр SystemAndOk, plugin_filter.hpp). Общих имён у компонентов 1 и 125 в основе: ' + $sharedNames.Count + '; если их значение не совпало с основой, это UNKNOWN, не СТОП.')
if ($sharedNames.Count -gt 0) { $rep.Add($sharedNames.Count.ToString() + ' имён нельзя проверить по таблице MAVROS (компонент 125), из них ' + $indist.Count + ' с равными значениями — не доказано. Среди них калибровки, плата, фильтры IMU и датчик потока; в этом наборе их не меняем (решение чата 1: не блокировать). Примеры равных: ' + (($indist | Select-Object -First 8) -join ', ') + ' ...') }
$rep.Add('')
if ($diffs.Count -gt 0) {
    $rep.Add('--- ОТЛИЧИЯ: СТОП до решения владельца ---')
    foreach ($l in $diffs) { $rep.Add($l) }
    $rep.Add('')
}
if ($gyro.Count -gt 0) {
    $rep.Add('--- Гироскоп сдвинулся (запись, не стоп): ' + $gyro.Count + ' ---')
    foreach ($l in $gyro) { $rep.Add($l) }
    $rep.Add('Решение владельца 16.11: «Не стоп, только запись». Любое другое отличие, в том числе CAL_ACC*, - СТОП, как раньше.')
    $rep.Add('')
}
if ($unknown.Count -gt 0) {
    $rep.Add('--- UNKNOWN: ВОЗМОЖНА ПОДМЕНА КОМПОНЕНТОМ 125 (' + $unknown.Count + '), это НЕ СТОП и НЕ совпадение ---')
    foreach ($l in $unknown) { $rep.Add($l) }
    $rep.Add('Как проверить: значение компонента 1 можно увидеть только в QGC (Component 1), не в MAVROS. Ничего не менять без решения владельца.')
    $rep.Add('')
}
if ($missing.Count -gt 0) {
    $rep.Add('--- НЕ ПРОЧИТАНО (' + $missing.Count + ') ---')
    $shown = 0
    foreach ($n in $missing) { if ($shown -lt 60) { $rep.Add($n) }; $shown++ }
    if ($missing.Count -gt 60) { $rep.Add('... и ещё ' + ($missing.Count - 60)) }
    $rep.Add('')
}
if ($profileLeft.Count -gt 0) {
    $rep.Add('--- ЗНАЧЕНИЯ ПРОФИЛЕЙ, КОТОРЫЕ УЖЕ В ОСНОВЕ ---')
    foreach ($l in $profileLeft) { $rep.Add($l) }
    $rep.Add('')
}
$propLines = New-Object Collections.Generic.List[string]
foreach ($n in ($proposed.Keys | Sort-Object)) {
    if ($read.ContainsKey($n)) {
        $propLines.Add(("{0}: на дроне {1}, предлагается {2} (статус: {3})" -f $n, (Fmt $read[$n].K $read[$n].V), $proposed[$n].Raw, $proposed[$n].St))
    }
    else { $propLines.Add(("{0}: на дроне не прочитано, предлагается {1} (статус: {2})" -f $n, $proposed[$n].Raw, $proposed[$n].St)) }
}
if ($propLines.Count -gt 0) {
    $rep.Add('--- ПРЕДЛАГАЕТСЯ, ЕЩЁ НЕ НА ДРОНЕ (из реестра настроек; не отличия, пока на дроне основа) ---')
    foreach ($l in $propLines) { $rep.Add($l) }
    $rep.Add('')
}
if ($registryNote -ne '') { $rep.Add($registryNote); $rep.Add('') }
if ($approvedOk.Count -gt 0) {
    $rep.Add('--- ОДОБРЕННЫЕ ПРАВКИ, ПРИМЕНЕНЫ ---')
    foreach ($l in $approvedOk) { $rep.Add($l) }
    $rep.Add('')
}
if ($counters.Count -gt 0) {
    $rep.Add('--- СЧЁТЧИКИ (PX4 меняет сам, не СТОП) ---')
    foreach ($l in $counters) { $rep.Add($l) }
    $rep.Add('')
}

# ---------- строка для СЕЙЧАС_ОТ_ВАС ----------
if ($code -eq 2) {
    $first = (($diffs | ForEach-Object { $_.Split(':')[0] } | Select-Object -First 3) -join ', ')
    $now = 'СТОП: сверка настроек нашла отличий: ' + $diffs.Count + ' (' + $first + '). Ждать решения владельца, не лететь.'
}
elseif ($code -eq 3) {
    if ($unknown.Count -gt 0 -and $missing.Count -eq 0 -and -not $strictIncomplete) { $now = 'Сверка настроек: ' + $nowIncomplete + '. Не СТОП, но и не подтверждено; посмотреть отчёт.' }
    elseif ($nowIncomplete -ne '') { $now = 'Сверка настроек НЕ завершена: ' + $nowIncomplete + '. Повторить.' }
    else { $now = 'Сверка настроек НЕ завершена: прочитано ' + $gotCount + ' из ' + $total + '. Повторить.' }
}
elseif ($AllowStreamFallback -and $streamOnly -gt 0) { $now = 'ЧЕРНОВИК (-AllowStreamFallback): значения частично из запасного потока, это НЕ подтверждённое совпадение.' }
elseif ($gyro.Count -gt 0) { $now = 'Сверка настроек: совпадает, гироскоп сдвинулся у ' + $gyro.Count + ' (запись, не стоп: ' + (($gyro | ForEach-Object { $_.Split(':')[0] }) -join ', ') + '), прочитано ' + $gotCount + ' из ' + $total + '.' }
else { $now = 'Сверка настроек: совпадает, прочитано ' + $gotCount + ' из ' + $total + ' (по ' + $indist.Count + ' именам компонент 1 не подтверждён, значения 1 и 125 равны).' }

# ---------- файл .params в формате QGC ----------
$pl = New-Object Collections.Generic.List[string]
$pl.Add('# Настройки, прочитанные через MAVROS ' + $stamp + ' (компонент 1). Прочитано ' + $read.Count + ' имён.')
$pl.Add('# Vehicle-Id Component-Id Name Value Type')
foreach ($n in ($read.Keys | Sort-Object)) {
    $d = $read[$n]
    $ty = '9'; if ($d.K -eq 'i') { $ty = '6' }
    $pl.Add(("1`t1`t{0}`t{1}`t{2}" -f $n, (Fmt $d.K $d.V), $ty))
}

[IO.File]::WriteAllLines($outParams, $pl, $utf8bom)
[IO.File]::WriteAllLines($outExtra, [string[]]$extra, $utf8bom)
[IO.File]::WriteAllLines($outReport, $rep, $utf8bom)
[IO.File]::WriteAllText($outNow, $now + "`r`n", $utf8bom)

# ---------- на экран ----------
if ($code -eq 0) { Write-Host ('  ' + $verdict + '  ') -ForegroundColor White -BackgroundColor DarkGreen }
elseif ($code -eq 2) {
    Write-Host '' ; Write-Host '  ##########################################################' -ForegroundColor White -BackgroundColor Red
    Write-Host '  ###   СТОП до решения владельца   (Ж6)                    ###' -ForegroundColor White -BackgroundColor Red
    Write-Host ('  ###   отличий: ' + $diffs.Count + ' ' * 40) -ForegroundColor White -BackgroundColor Red
    Write-Host '  ##########################################################' -ForegroundColor White -BackgroundColor Red
}
else { Write-Host ('  ' + $verdict + '  ') -ForegroundColor Black -BackgroundColor Yellow }
foreach ($l in $rep) { Write-Host $l }
Write-Host ''
Write-Host ('Отчёт:  ' + $outReport)
Write-Host ('Файл настроек: ' + $outParams)
Write-Host ('Строка для СЕЙЧАС_ОТ_ВАС: ' + $outNow)
exit $code
