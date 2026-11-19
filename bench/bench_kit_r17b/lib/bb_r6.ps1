# bb_r6.ps1 (Claude, 12.11.2026, набор r6) - общие функции новых шагов r6 (19-24, 09c, 15c, 05c/06c). Подключается после lib\bb_common.ps1. Сама ничего не запускает и к дрону не подключается.
# Здесь же проверка файлов-разрешений из gates\ (их создаёт ТОЛЬКО чат 1 после слов владельца; Claude-сборщик их не создаёт) и правило «одно разрешение = один успешный запуск».

# Запуск скрипта Pi (через base64 в команде ssh, файлов на Pi не создаётся). Ответ: Code, Text, Out.
function R6-Remote($ssh, [string]$shPath, [string[]]$shArgs, [string]$outDir, [string]$name, [int]$timeoutSec) {
    $o = BB-NewOutFile $outDir ($name + '.txt'); $e = BB-NewOutFile $outDir ($name + '.err.txt')
    $remote = BB-RemoteCommand $shPath $shArgs
    $rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $o $e $timeoutSec
    $t = ''; if (Test-Path -LiteralPath $o) { $t = [IO.File]::ReadAllText($o) }
    $et = ''; if (Test-Path -LiteralPath $e) { $et = [IO.File]::ReadAllText($e) }
    return @{ Code = $rc; Text = $t; Out = $o; Err = $et }
}
# Строки вывода с префиксом (без самого префикса и пробела)
function R6-Lines([string]$text, [string]$prefix) {
    return @($text -split "`r?`n" | Where-Object { $_.StartsWith($prefix + ' ') } | ForEach-Object { $_.Substring($prefix.Length + 1) })
}
function R6-Sha([string]$path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLower() }
function R6-TextSha([string]$text) { return ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash((New-Object Text.UTF8Encoding($false)).GetBytes($text))) -replace '-', '').ToLower() }

# Файл-разрешение gates\<имя>. Обязательные строки: ПРАВКА=<id> (точно), ВЛАДЕЛЕЦ_СКАЗАЛ=да, ДАТА=..., СЛОВА_ВЛАДЕЛЬЦА=..., СОЗДАЛ=чат 1, плюс $extra (точные строки).
# Возвращает @{ Ok; Why; Sha }. Ничего не создаёт и не меняет.
function R6-Permission([string]$gatePath, [string]$id, [string[]]$extra = @()) {
    $why = New-Object Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $gatePath)) { return @{ Ok = $false; Why = ('нет файла-разрешения ' + $gatePath + ' (его создаёт только чат 1 после слов владельца)'); Sha = '' } }
    $lines = @([IO.File]::ReadAllLines($gatePath) | ForEach-Object { $_.Trim().TrimStart([char]0xFEFF) })
    $need = @(('ПРАВКА=' + $id), 'ВЛАДЕЛЕЦ_СКАЗАЛ=да', 'СОЗДАЛ=чат 1') + @($extra)
    foreach ($k in $need) { if (-not ($lines | Where-Object { $_ -ceq $k })) { $why.Add('нет строки «' + $k + '»') } }
    foreach ($k in 'ДАТА=', 'СЛОВА_ВЛАДЕЛЬЦА=') { if (-not ($lines | Where-Object { $_.StartsWith($k) -and $_.Length -gt $k.Length })) { $why.Add('нет заполненной строки ' + $k + '...') } }
    $pr = @($lines | Where-Object { $_.StartsWith('ПРАВКА=') })
    if ($pr.Count -ne 1) { $why.Add('строк ПРАВКА= должно быть ровно одна, а их ' + $pr.Count) }
    $sha = R6-Sha $gatePath
    if ($why.Count -gt 0) { return @{ Ok = $false; Why = ('файл-разрешение ' + (Split-Path $gatePath -Leaf) + ' не годится: ' + ($why -join '; ')); Sha = $sha } }
    return @{ Ok = $true; Why = ''; Sha = $sha }
}
# Разрешение одноразовое: если в out\ уже есть журнал УСПЕШНОГО запуска этого шага с тем же sha256 разрешения, отказ (нужно новое «да» владельца).
function R6-PermissionUsed([string]$outDir, [string]$logPrefix, [string]$sha, [string]$okMarker) {
    if (-not (Test-Path -LiteralPath $outDir)) { return $false }
    foreach ($f in @(Get-ChildItem -LiteralPath $outDir -File -Filter ($logPrefix + '*') -ErrorAction SilentlyContinue)) {
        $t = ''; try { $t = [IO.File]::ReadAllText($f.FullName) } catch { continue }
        if ($t.Contains('PERMISSION_SHA256=' + $sha) -and $t.Contains($okMarker)) { return $true }
    }
    return $false
}
# Самый свежий файл out\<filter> без .err/.generated/.FAILED
function R6-Latest([string]$outDir, [string]$filter) {
    if (-not (Test-Path -LiteralPath $outDir)) { return $null }
    $f = @(Get-ChildItem -LiteralPath $outDir -File -Filter $filter -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch '\.err\.txt$|\.generated\.|\.FAILED\.' } | Sort-Object LastWriteTime)
    if ($f.Count -eq 0) { return $null }
    return $f[-1]
}
# Последняя непустая строка файла (для «# VERDICT OK»)
function R6-LastLine([string]$path) {
    $l = @([IO.File]::ReadAllLines($path) | Where-Object { $_.Trim() -ne '' })
    if ($l.Count -eq 0) { return '' }
    return $l[-1].Trim()
}
# Файлы замера камеры полных строк в наборе (camera_fullrow\): sha256 по SHA256SUMS_camera_fullrow.txt и по ожидаемым суммам PI_PERF. Возвращает список «sha  имя».
function R6-CamFiles([string]$here) {
    $d = Join-Path $here 'camera_fullrow'
    $want = [ordered]@{
        'camera_fix.py'       = 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83'
        'bench_recorder.py'   = '08c2ccaca602804ad37e8d92929c4f0c4a6ea8687faef15b39be46d0a0e08fd2'
        'raw_layout_check.py' = '8a811032c3d9ab9d596771e9437eb2793ef043e3bd9ef44ad127b2492b2b39e1'
    }
    $sums = Join-Path $d 'SHA256SUMS_camera_fullrow.txt'
    if (-not (Test-Path -LiteralPath $sums)) { BB-Stop ('нет ' + $sums) 4 }
    $rows = @([IO.File]::ReadAllLines($sums) | Where-Object { $_.Trim() -ne '' })
    if ($rows.Count -ne 3) { BB-Stop ('в SHA256SUMS_camera_fullrow.txt должно быть 3 строки, а их ' + $rows.Count) 4 }
    $o = New-Object Collections.Generic.List[string]
    foreach ($k in $want.Keys) {
        $p = Join-Path $d $k
        if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет файла ' + $p) 4 }
        $h = R6-Sha $p
        if ($h -cne $want[$k]) { BB-Stop ('sha256 ' + $k + ' в наборе не тот: ' + $h + ' (ждали ' + $want[$k] + ')') 4 }
        if (-not ($rows | Where-Object { $_ -ceq ($want[$k] + '  ' + $k) })) { BB-Stop ('в SHA256SUMS_camera_fullrow.txt нет строки для ' + $k) 4 }
        $o.Add($want[$k] + '  ' + $k)
    }
    $o.Add((R6-Sha $sums) + '  SHA256SUMS_camera_fullrow.txt')
    return ,$o
}
# Время ПК для журналов
function R6-Now { return (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') }
