param([string]$InDir, [string]$OutDir, [string]$Labels)
# chat 1, 11.11: draw labels on rendered views. ASCII-only script; texts come from a UTF-8 JSON file. Never overwrites.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$cfg = Get-Content -LiteralPath $Labels -Encoding UTF8 -Raw | ConvertFrom-Json
function Col([string]$hex) { return [System.Drawing.ColorTranslator]::FromHtml($hex) }
foreach ($p in $cfg.PSObject.Properties) {
    $src = Join-Path $InDir $p.Name
    $dst = Join-Path $OutDir $p.Value.out
    if (Test-Path -LiteralPath $dst) { Write-Output ("EXISTS, skipped: " + $dst); continue }
    $img = [System.Drawing.Image]::FromFile($src)
    $bmp = New-Object System.Drawing.Bitmap $img.Width, $img.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias
    $g.DrawImage($img, 0, 0, $img.Width, $img.Height)
    $img.Dispose()
    $font = New-Object System.Drawing.Font('Segoe UI', 21, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $fontT = New-Object System.Drawing.Font('Segoe UI', 24, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    foreach ($it in $p.Value.items) {
        if ($it.type -eq 'line') {
            $pen = New-Object System.Drawing.Pen (Col $it.color), ([single]$it.w)
            if ($it.dash) { $pen.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dash }
            $g.DrawLine($pen, [single]$it.x1, [single]$it.y1, [single]$it.x2, [single]$it.y2)
            $pen.Dispose()
        }
        elseif ($it.type -eq 'rect') {
            $pen = New-Object System.Drawing.Pen (Col $it.color), ([single]$it.w)
            $pen.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dash
            $g.DrawRectangle($pen, [single]$it.x1, [single]$it.y1, [single]($it.x2 - $it.x1), [single]($it.y2 - $it.y1))
            $pen.Dispose()
        }
        elseif ($it.type -eq 'dim') {
            $pen = New-Object System.Drawing.Pen (Col $it.color), 4
            $cap = New-Object System.Drawing.Drawing2D.AdjustableArrowCap 5, 6
            $pen.CustomStartCap = $cap; $pen.CustomEndCap = $cap
            $g.DrawLine($pen, [single]$it.x, [single]$it.y1, [single]$it.x, [single]$it.y2)
            $pen.Dispose()
        }
        elseif ($it.type -eq 'title') {
            $sz = $g.MeasureString($it.text, $fontT)
            $bg = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(235, 19, 49, 79))
            $g.FillRectangle($bg, [single]$it.x, [single]$it.y, $sz.Width + 16, $sz.Height + 8)
            $g.DrawString($it.text, $fontT, [System.Drawing.Brushes]::White, [single]($it.x + 8), [single]($it.y + 4))
            $bg.Dispose()
        }
        elseif ($it.type -eq 'label') {
            $c = Col $it.color
            $sz = $g.MeasureString($it.text, $font)
            $w = $sz.Width + 18; $h = $sz.Height + 10
            $cx = $it.x + $w / 2; $cy = $it.y + $h / 2
            # leader from the box edge point nearest to the anchor
            $ex = [Math]::Min([Math]::Max([double]$it.ax, [double]$it.x), [double]($it.x + $w))
            $ey = [Math]::Min([Math]::Max([double]$it.ay, [double]$it.y), [double]($it.y + $h))
            $pen = New-Object System.Drawing.Pen $c, 4
            $g.DrawLine($pen, [single]$ex, [single]$ey, [single]$it.ax, [single]$it.ay)
            $br = New-Object System.Drawing.SolidBrush $c
            $g.FillEllipse($br, [single]($it.ax - 7), [single]($it.ay - 7), 14, 14)
            $g.FillRectangle([System.Drawing.Brushes]::White, [single]$it.x, [single]$it.y, [single]$w, [single]$h)
            $g.DrawRectangle($pen, [single]$it.x, [single]$it.y, [single]$w, [single]$h)
            $g.DrawString($it.text, $font, $br, [single]($it.x + 9), [single]($it.y + 5))
            $pen.Dispose(); $br.Dispose()
        }
    }
    $g.Dispose()
    $bmp.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Output ("WROTE " + $dst)
}
