param(
    [string]$OutputFolder = "$env:USERPROFILE\Documents\RaterHubTracker",
    [switch]$LaunchEdgeIfNeeded,
    [double]$TargetMinutesPerQuestion = 5.5  # AHT target (5.5 min per spec for Severity tasks)
)

# -----------------------------
# Config
# -----------------------------
$RaterHubUrl   = 'https://raterhub.com/evaluation/rater'
$TabTitleHint  = 'Rater Hub'
$today         = Get-Date -Format 'yyyy-MM-dd'
$sessionId     = [guid]::NewGuid().ToString()

# Where AHK writes signals
$SignalFolder  = "C:\RaterHubTracker"
$SignalFile    = Join-Path $SignalFolder "signals.txt"

$csvPath       = Join-Path $OutputFolder ("RaterHub-{0}.csv" -f $today)
$htmlPath      = Join-Path $OutputFolder ("RaterHubSession-{0}-{1}.html" -f $today, (Get-Date -Format 'HHmmss'))

# -----------------------------
# Helpers
# -----------------------------
function Format-TimeMMSS($seconds) {
    $ts = [TimeSpan]::FromSeconds($seconds)
    return "{0:00}:{1:00}" -f [math]::Floor($ts.TotalMinutes), $ts.Seconds
}

function Add-QuestionRecord {
    param(
        [int]      $QuestionNumber,
        [datetime] $Start,
        [datetime] $End,
        [string]   $SessionId,
        [double]   $EffectiveSeconds
    )

    if ($EffectiveSeconds -lt 0) { $EffectiveSeconds = 0 }

    $duration = [TimeSpan]::FromSeconds($EffectiveSeconds)

    [PSCustomObject]@{
        Date             = $Start.ToString('yyyy-MM-dd')
        SessionId        = $SessionId
        QuestionNumber   = $QuestionNumber
        StartTime        = $Start.ToString('HH:mm:ss')
        EndTime          = $End.ToString('HH:mm:ss')
        DurationSeconds  = [math]::Round($EffectiveSeconds, 2)
        DurationMinutes  = [math]::Round($duration.TotalMinutes, 2)
    }
}

# -----------------------------
# Ensure folders & signal file
# -----------------------------
foreach ($folder in @($OutputFolder, $SignalFolder)) {
    if (-not (Test-Path $folder)) {
        New-Item -Path $folder -ItemType Directory -Force | Out-Null
    }
}

if (-not (Test-Path $SignalFile)) {
    New-Item -Path $SignalFile -ItemType File -Force | Out-Null
} else {
    Clear-Content -Path $SignalFile -ErrorAction SilentlyContinue
}

# -----------------------------
# Optionally launch Edge
# -----------------------------
if ($LaunchEdgeIfNeeded) {
    $edgeWithRater = Get-Process msedge -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like "*$TabTitleHint*" }

    if (-not $edgeWithRater) {
        Start-Process "msedge.exe" $RaterHubUrl
    }
}

Write-Host "RaterHub session tracker (hotkey-driven) started." -ForegroundColor Cyan
Write-Host "Session ID: $sessionId"
Write-Host "Signal file: $SignalFile"
Write-Host "Hotkeys:"
Write-Host "  Ctrl+Q         → NEXT question"
Write-Host "  Ctrl+Alt+Q     → PAUSE / RESUME"
Write-Host "  Ctrl+Shift+Q   → END session" -ForegroundColor Yellow
Write-Host ""

# -----------------------------
# Data structures
# -----------------------------
$questions = New-Object System.Collections.Generic.List[object]

$questionNumber       = 1
$questionStart        = Get-Date
$sessionEnded         = $false

# pause tracking
$isPaused             = $false
$pauseStart           = $null
$pauseOffsetSeconds   = 0.0   # accumulated paused time for current question

Write-Host ("Question {0} started at {1}" -f $questionNumber, $questionStart) -ForegroundColor Yellow

# -----------------------------
# Main loop: watch for signals
# -----------------------------
while (-not $sessionEnded) {
    try {
        if (Test-Path $SignalFile) {
            $commands = Get-Content -Path $SignalFile -ErrorAction SilentlyContinue |
                        Where-Object { $_ -match '\S' }

            if ($commands -and $commands.Count -gt 0) {
                Clear-Content -Path $SignalFile -ErrorAction SilentlyContinue

                foreach ($cmdLine in $commands) {
                    $clean = ($cmdLine -split '\s+')[0].ToUpper()

                    switch ($clean) {
                        'PAUSE' {
                            if (-not $isPaused) {
                                $isPaused   = $true
                                $pauseStart = Get-Date
                                Write-Host "[SIGNAL] PAUSE → timing paused" -ForegroundColor DarkYellow
                            }
                            else {
                                # resume and accumulate paused time first
                                $pauseEnd = Get-Date
                                if ($pauseStart) {
                                    $pauseOffsetSeconds += ($pauseEnd - $pauseStart).TotalSeconds
                                }
                                $pauseStart = $null
                                $isPaused   = $false
                                Write-Host "[SIGNAL] PAUSE → resumed" -ForegroundColor DarkYellow
                            }
                        }

                        'NEXT' {
                            # If paused, auto-resume and close out pause time first
                            if ($isPaused -and $pauseStart) {
                                $pauseEnd = Get-Date
                                $pauseOffsetSeconds += ($pauseEnd - $pauseStart).TotalSeconds
                                $pauseStart = $null
                                $isPaused   = $false
                            }

                            $questionEnd   = Get-Date
                            $rawSeconds    = ($questionEnd - $questionStart).TotalSeconds
                            $effectiveSecs = $rawSeconds - $pauseOffsetSeconds

                            $record = Add-QuestionRecord -QuestionNumber $questionNumber `
                                                         -Start $questionStart `
                                                         -End $questionEnd `
                                                         -SessionId $sessionId `
                                                         -EffectiveSeconds $effectiveSecs
                            $questions.Add($record) | Out-Null

                            Write-Host ("[SIGNAL] NEXT → recorded Question {0}: {1} sec (active)" -f $questionNumber, $record.DurationSeconds) -ForegroundColor Green

                            # reset pause info for next question
                            $pauseOffsetSeconds = 0.0
                            $pauseStart         = $null
                            $isPaused           = $false

                            $questionNumber++
                            $questionStart = Get-Date
                            Write-Host ("Question {0} started at {1}" -f $questionNumber, $questionStart) -ForegroundColor Yellow
                        }

                        'EXIT' {
                            # finish current question then end session
                            if ($isPaused -and $pauseStart) {
                                $pauseEnd = Get-Date
                                $pauseOffsetSeconds += ($pauseEnd - $pauseStart).TotalSeconds
                                $pauseStart = $null
                                $isPaused   = $false
                            }

                            $questionEnd   = Get-Date
                            $rawSeconds    = ($questionEnd - $questionStart).TotalSeconds
                            $effectiveSecs = $rawSeconds - $pauseOffsetSeconds

                            $record = Add-QuestionRecord -QuestionNumber $questionNumber `
                                                         -Start $questionStart `
                                                         -End $questionEnd `
                                                         -SessionId $sessionId `
                                                         -EffectiveSeconds $effectiveSecs
                            $questions.Add($record) | Out-Null

                            Write-Host ("[SIGNAL] EXIT → recorded final Question {0}: {1} sec (active)" -f $questionNumber, $record.DurationSeconds) -ForegroundColor Green

                            $sessionEnded       = $true
                            $pauseOffsetSeconds = 0.0
                            $pauseStart         = $null
                            $isPaused           = $false
                        }

                        default {
                            Write-Host "[WARN] Unknown signal received: '$clean'" -ForegroundColor DarkYellow
                        }
                    }
                }
            }
        }
    }
    catch {
        Write-Host "[ERROR] $_" -ForegroundColor Red
    }

    Start-Sleep -Milliseconds 200
}

if ($questions.Count -eq 0) {
    Write-Host "No questions recorded; skipping CSV & HTML." -ForegroundColor Yellow
    return
}

# -----------------------------
# Persist to CSV
# -----------------------------
if (-not (Test-Path $csvPath)) {
    $questions | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
    Write-Host "Created new CSV: $csvPath" -ForegroundColor Cyan
} else {
    $questions | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8 -Append
    Write-Host "Appended to CSV: $csvPath" -ForegroundColor Cyan
}

# -----------------------------
# Metrics for dashboard
# -----------------------------
$totalQuestions = $questions.Count
$totalSeconds   = ($questions | Measure-Object -Property DurationSeconds -Sum).Sum
if (-not $totalSeconds) { $totalSeconds = 0 }

$avgSeconds = if ($totalQuestions -gt 0) { $totalSeconds / $totalQuestions } else { 0 }
$totalMinutes = [math]::Round($totalSeconds / 60, 2)

$avgMMSS       = Format-TimeMMSS $avgSeconds
$targetSeconds = $TargetMinutesPerQuestion * 60
$ratio         = if ($targetSeconds -gt 0) { $avgSeconds / $targetSeconds } else { 0 }

# Pace label + emoji + score
if ($totalQuestions -eq 0) {
    $paceLabel = "No questions this session"
    $paceEmoji = "😴"
    $sessionScore = 0
}
else {
    if     ($ratio -lt 0.5) { $paceLabel = "way too fast (<50% of target)"; $paceEmoji = "⚡🐇" }
    elseif ($ratio -lt 0.7) { $paceLabel = "fast (50–70% of target)";       $paceEmoji = "🐇"   }
    elseif ($ratio -lt 0.9) { $paceLabel = "slightly fast";                 $paceEmoji = "🙂"   }
    elseif ($ratio -lt 1.1) { $paceLabel = "on target";                     $paceEmoji = "💜✅" }
    elseif ($ratio -lt 1.3) { $paceLabel = "a bit slow";                    $paceEmoji = "🐢"   }
    else                    { $paceLabel = "slow, consider picking up";     $paceEmoji = "🐌"   }

    # Smooth score centered at ratio=1, decays with distance
    $sessionScore = [math]::Round(
        [math]::Max(0, [math]::Min(100, 100 * [math]::Exp(-1.2 * [math]::Abs($ratio - 1))))
    )
}

# Sparkline for question times
$maxSeconds = ($questions | Measure-Object -Property DurationSeconds -Maximum).Maximum
if ($maxSeconds -lt 1) { $maxSeconds = 1 }

$sparkBars = @()
for ($i = 0; $i -lt $questions.Count; $i++) {
    $q = $questions[$i]
    $h = [math]::Round(($q.DurationSeconds / $maxSeconds) * 100)
    if ($h -lt 3) { $h = 3 }  # minimum visible bar
    $x = $i
    $y = 100 - $h
    $class = if ($q.DurationSeconds -eq $maxSeconds) { "bar max" } else { "bar" }
    $sparkBars += "<rect class='$class' x='$x' y='$y' width='0.8' height='$h' />"
}
$sparkBarsStr = ($sparkBars -join "")
$sparklineSvg = "<svg viewBox='0 0 $($questions.Count) 100' preserveAspectRatio='none' class='sparkline'>$sparkBarsStr</svg>"

# Build rows with mm:ss + bar
$rowsHtml = $questions | ForEach-Object {
    $mmss = Format-TimeMMSS $_.DurationSeconds
    $percent = [math]::Round(($_.DurationSeconds / $maxSeconds) * 100, 2)

    "<tr>
        <td>$($_.QuestionNumber)</td>
        <td>$($_.StartTime)</td>
        <td>$($_.EndTime)</td>
        <td>
            <div class='time-cell'>
                <span class='time-text'>$mmss</span>
                <div class='time-bar'>
                    <div class='time-bar-fill' style='width:$percent%;'></div>
                </div>
            </div>
        </td>
    </tr>"
} | Out-String

$sessionStart = ($questions | Select-Object -First 1).StartTime
$sessionEnd   = ($questions | Select-Object -Last 1).EndTime

# -----------------------------
# HTML dashboard (purple, sparkline, emojis)
# -----------------------------
$html = @"
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>RaterHub Session Report - $today</title>
    <style>
        :root {
            --bg-main: #f7f3ff;
            --card-bg: #ffffff;
            --accent: #6c5ce7;
            --accent-soft: #a29bfe;
            --accent-dark: #4834d4;
            --accent-light: #dcd2ff;
            --text-main: #2d2440;
            --text-muted: #6c657e;
            --border-subtle: #e4ddff;
            --table-header: #f0e9ff;
        }

        body {
            margin: 0;
            padding: 24px;
            font-family: "Segoe UI", Arial, sans-serif;
            background: radial-gradient(circle at top left, #fce1ff 0, #f7f3ff 40%, #ffffff 100%);
            color: var(--text-main);
        }

        .container {
            max-width: 980px;
            margin: 0 auto;
        }

        .card {
            background: var(--card-bg);
            border-radius: 16px;
            border: 1px solid var(--border-subtle);
            box-shadow: 0 10px 30px rgba(0,0,0,0.05);
            padding: 24px 28px;
        }

        h1 {
            font-size: 26px;
            margin: 0 0 6px;
            color: var(--accent-dark);
        }

        .subtitle {
            font-size: 13px;
            color: var(--text-muted);
            margin-bottom: 14px;
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 14px;
            margin: 18px 0 16px;
        }

        .summary-item {
            padding: 10px 12px;
            border-radius: 10px;
            background: #faf8ff;
            border: 1px solid #ece4ff;
        }

        .summary-label {
            font-size: 11px;
            text-transform: uppercase;
            color: var(--text-muted);
            letter-spacing: 0.06em;
        }

        .summary-value {
            margin-top: 4px;
            font-size: 15px;
            font-weight: bold;
            color: var(--accent-dark);
        }

        .summary-value.em {
            color: var(--accent);
        }

        .pace-label {
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 4px;
        }

        .spark-wrapper {
            margin: 10px 0 18px;
            padding: 10px 12px;
            border-radius: 10px;
            background: #fbf9ff;
            border: 1px dashed #e0d6ff;
        }

        .spark-header {
            font-size: 12px;
            text-transform: uppercase;
            color: var(--text-muted);
            letter-spacing: 0.08em;
            margin-bottom: 4px;
        }

        .sparkline {
            width: 100%;
            height: 40px;
        }

        .sparkline rect.bar {
            fill: var(--accent-soft);
        }

        .sparkline rect.bar.max {
            fill: var(--accent-dark);
        }

        table {
            border-collapse: collapse;
            width: 100%;
            font-size: 13px;
        }

        th, td {
            border: 1px solid var(--border-subtle);
            padding: 6px 8px;
        }

        th {
            background: var(--table-header);
            color: var(--accent-dark);
            font-weight: 600;
            font-size: 12px;
        }

        tbody tr:nth-child(even) {
            background: #fbf9ff;
        }

        tbody tr:hover {
            background: #f3ecff;
        }

        .time-cell {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .time-text {
            font-weight: 600;
            color: var(--accent-dark);
            width: 52px;
            text-align: right;
            font-family: Consolas, monospace;
        }

        .time-bar {
            flex-grow: 1;
            height: 10px;
            border-radius: 6px;
            background: var(--accent-light);
            overflow: hidden;
        }

        .time-bar-fill {
            height: 100%;
            background: var(--accent);
            border-radius: 6px;
        }

        .footer-note {
            margin-top: 16px;
            font-size: 11px;
            color: var(--text-muted);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>RaterHub Session Report 💜</h1>
            <div class="subtitle">
                Generated on <strong>$today</strong>. Each bar represents one question’s active time (pauses excluded).
            </div>

            <div class="summary-grid">
                <div class="summary-item">
                    <div class="summary-label">Session ID</div>
                    <div class="summary-value">$sessionId</div>
                </div>

                <div class="summary-item">
                    <div class="summary-label">Session Window</div>
                    <div class="summary-value">$sessionStart – $sessionEnd</div>
                </div>

                <div class="summary-item">
                    <div class="summary-label">Total Questions</div>
                    <div class="summary-value em">$totalQuestions</div>
                </div>

                <div class="summary-item">
                    <div class="summary-label">Total Active Time</div>
                    <div class="summary-value">$totalMinutes min</div>
                </div>

                <div class="summary-item">
                    <div class="summary-label">Average per Question</div>
                    <div class="summary-value em">$avgMMSS</div>
                    <div class="pace-label">Target: $TargetMinutesPerQuestion min</div>
                </div>

                <div class="summary-item">
                    <div class="summary-label">Session Pace & Score</div>
                    <div class="summary-value">$paceEmoji $paceLabel</div>
                    <div class="pace-label">Score: $sessionScore / 100</div>
                </div>
            </div>

            <div class="spark-wrapper">
                <div class="spark-header">Question Time Sparkline</div>
                $sparklineSvg
            </div>

            <h2 style="color: var(--accent-dark); margin-top: 24px;">Per-Question Breakdown</h2>

            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Start</th>
                        <th>End</th>
                        <th>Time (mm:ss) + Visual</th>
                    </tr>
                </thead>
                <tbody>
                    $rowsHtml
                </tbody>
            </table>

            <div class="footer-note">
                AHT is compared against an estimated target of $TargetMinutesPerQuestion minutes per question (current Severity-task expectation).
            </div>
        </div>
    </div>
</body>
</html>
"@

$html | Out-File -FilePath $htmlPath -Encoding UTF8
Write-Host "HTML report written to: $htmlPath" -ForegroundColor Cyan
Write-Host "RaterHub session tracker finished." -ForegroundColor Cyan
