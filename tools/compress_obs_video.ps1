param(
    [string]$InputPath = "",
    [double]$ReviewMaxMB = 88.0,
    [double]$DiscordMaxMB = 9.3,
    [double]$ClipStartSec = -1.0,
    [double]$ClipDurationSec = 30.0,
    [string]$OutDir = "",
    [switch]$SkipDiscord,
    [switch]$SkipReview
)

$ErrorActionPreference = "Stop"

function Resolve-FFmpegTools {
    $ff = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
    $fp = (Get-Command ffprobe -ErrorAction SilentlyContinue).Source
    if ($ff -and (Test-Path -LiteralPath $ff) -and $fp -and (Test-Path -LiteralPath $fp)) {
        return @{ Ffmpeg = $ff; Ffprobe = $fp }
    }
    $pkg = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg*" -Filter "ffmpeg.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pkg) {
        $dir = $pkg.DirectoryName
        $ff2 = Join-Path $dir "ffmpeg.exe"
        $fp2 = Join-Path $dir "ffprobe.exe"
        if ((Test-Path -LiteralPath $ff2) -and (Test-Path -LiteralPath $fp2)) {
            return @{ Ffmpeg = $ff2; Ffprobe = $fp2 }
        }
    }
    foreach ($dir in @("C:\ffmpeg\bin", "C:\ProgramData\chocolatey\bin")) {
        $ff3 = Join-Path $dir "ffmpeg.exe"
        $fp3 = Join-Path $dir "ffprobe.exe"
        if ((Test-Path -LiteralPath $ff3) -and (Test-Path -LiteralPath $fp3)) {
            return @{ Ffmpeg = $ff3; Ffprobe = $fp3 }
        }
    }
    return $null
}

if (-not $InputPath -or -not (Test-Path -LiteralPath $InputPath)) {
    $vids = Get-ChildItem "$env:USERPROFILE\Videos" -Filter "*.mp4" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch '_review_|_discord_' } |
        Sort-Object LastWriteTime -Descending
    if ($vids -and $vids.Count -gt 0) {
        $InputPath = $vids[0].FullName
        Write-Output "Auto-selected latest recording: $InputPath"
    } else {
        Write-Error "No .mp4 found. Drag an MP4 onto Compress_For_Discord.bat / Compress_OBS_Video.bat or pass -InputPath."
        exit 1
    }
}

$InputPath = (Resolve-Path -LiteralPath $InputPath).Path
if (-not $OutDir) { $OutDir = Split-Path -Parent $InputPath }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$baseName = [System.IO.Path]::GetFileNameWithoutExtension($InputPath)

$tools = Resolve-FFmpegTools
if (-not $tools) {
    throw "FFmpeg not found. Run 'winget install -e --id Gyan.FFmpeg' first."
}
$ff = $tools.Ffmpeg
$fp = $tools.Ffprobe

# Probe exact duration, dimensions, and source FPS
$probeJson = (& $fp -v error -show_entries format=duration:stream=codec_type,width,height,r_frame_rate -of json $InputPath) | ConvertFrom-Json
$origSec = [double]$probeJson.format.duration
$vStream = $probeJson.streams | Where-Object { $_.codec_type -eq 'video' } | Select-Object -First 1
$srcW = [int]$vStream.width
$srcH = [int]$vStream.height
$hasAudio = ($probeJson.streams | Where-Object { $_.codec_type -eq 'audio' } | Measure-Object).Count -gt 0

function Run-FFmpegEncode {
    param(
        [string]$OutName,
        [double]$TargetDecimalMB,
        [double]$StartSec,
        [double]$DurSec
    )

    $outPath = Join-Path $OutDir $OutName
    if (Test-Path -LiteralPath $outPath) { Remove-Item -LiteralPath $outPath -Force }

    if ($StartSec -lt 0) {
        $StartSec = if ($origSec -le 65.0) { 0.0 } else { 20.0 }
    }
    if ($StartSec -ge $origSec - 2.0) {
        $StartSec = [math]::Max(0.0, $origSec - [math]::Max(5.0, $DurSec))
    }
    $actualDur = if ($DurSec -le 0) { $origSec - $StartSec } else { [math]::Min($DurSec, $origSec - $StartSec) }
    $actualDur = [math]::Max(1.0, $actualDur)

    # Target decimal MB (1 MB = 1,000,000 bytes for strict Discord 10 MB compatibility)
    $targetBytes = $TargetDecimalMB * 1000000.0
    $audKbps = if ($actualDur -gt 360 -and $TargetDecimalMB -lt 30) { 64 } elseif ($TargetDecimalMB -ge 20 -or $actualDur -le 45) { 96 } else { 80 }
    if (-not $hasAudio) { $audKbps = 0 }

    $scaleFactor = 0.96
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        $totalBps = [math]::Floor(($targetBytes * 8.0 * $scaleFactor) / $actualDur)
        $vidKbps = [math]::Max(250, [int][math]::Floor($totalBps / 1000.0) - $audKbps)

        # Keep native 1080p for crisp PitWall/UI text down to 1500 kbps; cleanly step to 900p/720p on long low-bitrate squeezes
        $vfArgs = @()
        if ($srcH -gt 1080 -and $vidKbps -ge 1500) {
            $vfArgs = @("-vf", "scale=1920:1080:flags=lanczos")
        } elseif ($vidKbps -lt 650 -and $srcH -gt 720) {
            $vfArgs = @("-vf", "scale=1280:720:flags=lanczos")
        } elseif ($vidKbps -lt 1500 -and $srcH -gt 900) {
            $vfArgs = @("-vf", "scale=1600:900:flags=lanczos")
        }

        # Use 30fps cleanly for massive per-frame sharpness boost on HUD text & tarmac unless abundant >3.8 Mbps bitrate
        $fpsArgs = if ($vidKbps -ge 3800 -and $actualDur -le 45) { @() } else { @("-r", "30") }
        $preset = if ($actualDur -le 90.0) { "slow" } else { "fast" }
        $maxRate = [int][math]::Round($vidKbps * 1.45)
        $bufSize = [int][math]::Round($vidKbps * 2.10)

        $passLog = Join-Path $env:TEMP ("swooz_x264_" + [guid]::NewGuid().ToString("N"))
        $seekArgs = if ($StartSec -gt 0.05) { @("-ss", ("{0:F3}" -f $StartSec)) } else { @() }
        $durArgs = if ($DurSec -gt 0) { @("-t", ("{0:F3}" -f $actualDur)) } else { @() }

        Write-Output ("Encoding {0} ({1:N1}s @ {2}kbps vid + {3}kbps aud, preset={4}, target <={5:N2} MB)..." -f $OutName, $actualDur, $vidKbps, $audKbps, $preset, $TargetDecimalMB)

        $commonVid = @(
            "-c:v", "libx264", "-preset", $preset, "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-b:v", "${vidKbps}k", "-maxrate", "${maxRate}k", "-bufsize", "${bufSize}k",
            "-aq-mode", "2", "-aq-strength", "1.0", "-deblock", "-1:-1", "-bf", "3"
        ) + $vfArgs + $fpsArgs

        # Pass 1 (analysis only, no audio)
        $p1Args = @("-v", "error", "-y") + $seekArgs + @("-i", $InputPath) + $durArgs + $commonVid + @("-pass", "1", "-passlogfile", $passLog, "-an", "-f", "mp4", "NUL")
        & $ff @p1Args
        if ($LASTEXITCODE -ne 0) { throw "FFmpeg pass 1 failed ($LASTEXITCODE)" }

        # Pass 2 (final crisp MP4 with faststart metadata)
        $audArgs = if ($hasAudio) { @("-c:a", "aac", "-b:a", "${audKbps}k", "-ac", "2", "-ar", "48000") } else { @("-an") }
        $p2Args = @("-v", "error", "-y") + $seekArgs + @("-i", $InputPath) + $durArgs + $commonVid + @("-pass", "2", "-passlogfile", $passLog) + $audArgs + @("-movflags", "+faststart", $outPath)
        & $ff @p2Args
        if ($LASTEXITCODE -ne 0) { throw "FFmpeg pass 2 failed ($LASTEXITCODE)" }

        Remove-Item "${passLog}*" -Force -ErrorAction SilentlyContinue

        $bytes = (Get-Item -LiteralPath $outPath).Length
        $decMB = $bytes / 1000000.0
        $mib = $bytes / 1MB
        if ($decMB -le $TargetDecimalMB -or $attempt -eq 2) {
            Write-Output ("SAVED: {0} ({1:N2} MB decimal / {2:N2} MiB)" -f $outPath, $decMB, $mib)
            break
        }
        Write-Output ("Re-sizing pass ({0:N2} MB exceeded {1:N2} MB cap)..." -f $decMB, $TargetDecimalMB)
        $scaleFactor = $scaleFactor * (($TargetDecimalMB * 0.96) / $decMB)
    }
}

if (-not $SkipReview) {
    Run-FFmpegEncode -OutName "${baseName}_review_under90mb.mp4" -TargetDecimalMB $ReviewMaxMB -StartSec 0.0 -DurSec 0.0
}
if (-not $SkipDiscord) {
    Run-FFmpegEncode -OutName "${baseName}_discord_under10mb.mp4" -TargetDecimalMB $DiscordMaxMB -StartSec $ClipStartSec -DurSec $ClipDurationSec
}
