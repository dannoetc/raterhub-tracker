param(
    [string]$OutputFolder = "$env:USERPROFILE\Documents\RaterHubTracker",
    [switch]$LaunchEdgeIfNeeded
)

# -----------------------------
# Config
# -----------------------------
$RaterHubUrl   = 'https://raterhub.com/evaluation/rater'
$TabTitleHint  = 'Rater Hub'   # adjust if needed
$today         = Get-Date -Format 'yyyy-MM-dd'
$sessionId     = [guid]::NewGuid().ToString()

# Where AHK writes signals
$SignalFolder  = "C:\RaterHubTracker"
$SignalFile    = Join-Path $SignalFolder "signals.txt"

$csvPath       = Join-Path $OutputFolder ("RaterHub-{0}.csv" -f $today)
$htmlPath      = Join-Path $OutputFolder ("RaterHubSession-{0}-{1}.html" -f $today, (Get-Date -Format 'HHmmss'))

# -----------------------------
# Ensure folders exist
# -----------------------------
foreach ($folder in @($OutputFolder, $SignalFolder)) {
    if (-not (Test-Path $folder)) {
        New-Item -Path $folder -ItemType Directory -Force | Out-Null
    }
}

# Ensure signal file exists and is empty
if (-not (Test-Path $SignalFile)) {
    New-Item -Path $SignalFile -ItemType File -Force | Out-Null
} else {
    Clear-Content -Path $SignalFile -ErrorAction SilentlyContinue
}

# -----------------------------
# Optionally launch Edge to RaterHub
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
Write-Host "Use AHK hotkeys to record NEXT/EXIT events." -ForegroundColor Yellow

# -----------------------------
# Data structure for captured questions
# -----------------------------
$questions = New-Object System.Collections.Generic.List[object]

$questionNumber = 1
$questionStart  = Get-Date
$sessionEnded   = $false

Write-Host ("Question {0} started at {1}" -f $questionNumber, $questionStart) -ForegroundColor Yellow

function Add-QuestionRecord {
    param(
        [int]      $QuestionNumber,
        [datetime] $Start,
        [datetime] $End,
        [string]   $SessionId
    )

    $duration = $End - $Start

    [PSCustomObject]@{
        Date             = $Start.ToString('yyyy-MM-dd')
        SessionId        = $SessionId
        QuestionNumber   = $QuestionNumber
        StartTime        = $Start.ToString('HH:mm:ss')
        EndTime          = $End.ToString('HH:mm:ss')
        DurationSeconds  = [math]::Round($duration.TotalSeconds, 2)
        DurationMinutes  = [math]::Round($duration.TotalMinutes, 2)
    }
}

# -----------------------------
# Main loop: watch for signals from AHK
# -----------------------------
while (-not $sessionEnded) {
    try {
        if (Test-Path $SignalFile) {
            $commands = Get-Content -Path $SignalFile -ErrorAction SilentlyContinue |
                        Where-Object { $_ -match '\S' }

            if ($commands -and $commands.Count -gt 0) {
                # Clear the file so we don't reprocess these commands
                Clear-Content -Path $SignalFile -ErrorAction SilentlyContinue

                foreach ($cmdLine in $commands) {
                    $clean = ($cmdLine -split '\s+')[0].ToUpper()

                    switch ($clean) {
                        'NEXT' {
                            # End current question and start next
                            $questionEnd = Get-Date
                            $record = Add-QuestionRecord -QuestionNumber $questionNumber `
                                                         -Start $questionStart `
                                                         -End $questionEnd `
                                                         -SessionId $sessionId
                            $questions.Add($record) | Out-Null
                            Write-Host ("[SIGNAL] NEXT → recorded Question {0}: {1} seconds" -f $questionNumber, $record.DurationSeconds) -ForegroundColor Green

                            $questionNumber++
                            $questionStart = Get-Date
                            Write-Host ("Question {0} started at {1}" -f $questionNumber, $questionStart) -ForegroundColor Yellow
                        }
                        'EXIT' {
                            # End current question and end session
                            $questionEnd = Get-Date
                            $record = Add-QuestionRecord -QuestionNumber $questionNumber `
                                                         -Start $questionStart `
                                                         -End $questionEnd `
                                                         -SessionId $sessionId
                            $questions.Add($record) | Out-Null
                            Write-Host ("[SIGNAL] EXIT → recorded final Question {0}" -f $questionNumber) -ForegroundColor Green

                            $sessionEnded = $true
                        }
                        default {
                            # Ignore unknown commands for now
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

# -----------------------------
# Persist to CSV (per-day file)
# -----------------------------
if ($questions.Count -gt 0) {
    if (-not (Test-Path $csvPath)) {
        $questions | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
        Write-Host "Created new CSV: $csvPath" -ForegroundColor Cyan
    }
    else {
        $questions | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8 -Append
        Write-Host "Appended to CSV: $csvPath" -ForegroundColor Cyan
    }
}
else {
    Write-Host "No questions recorded; skipping CSV & HTML." -ForegroundColor Yellow
    return
}

# -----------------------------
# Generate HTML report for this session
# -----------------------------
$totalQuestions = $questions.Count
$totalSeconds   = ($questions | Measure-Object -Property DurationSeconds -Sum).Sum
$avgSeconds     = if ($totalQuestions -gt 0) { [math]::Round($totalSeconds / $totalQuestions, 2) } else { 0 }
$totalMinutes   = [math]::Round($totalSeconds / 60, 2)

$rowsHtml = $questions | ForEach-Object {
    "<tr>
        <td>$($_.QuestionNumber)</td>
        <td>$($_.StartTime)</td>
        <td>$($_.EndTime)</td>
        <td style='text-align:right;'>$($_.DurationSeconds)</td>
        <td style='text-align:right;'>$($_.DurationMinutes)</td>
    </tr>"
} | Out-String

$sessionStart = ($questions | Select-Object -First 1).StartTime
$sessionEnd   = ($questions | Select-Object -Last 1).EndTime

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
            --text-main: #2d2440;
            --text-muted: #6c657e;
            --border-subtle: #e4ddff;
            --table-header: #f0e9ff;
            --danger: #e17055;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            padding: 24px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
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
            box-shadow:
                0 10px 30px rgba(0, 0, 0, 0.05),
                0 0 0 1px rgba(255, 255, 255, 0.8);
            padding: 24px 28px;
        }

        h1 {
            font-size: 26px;
            margin: 0 0 8px 0;
            display: flex;
            align-items: center;
            gap: 10px;
            color: var(--accent-dark);
        }

        h1 span.badge {
            font-size: 11px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            padding: 2px 8px;
            border-radius: 999px;
            border: 1px solid var(--accent-soft);
            background: #f9f6ff;
            color: var(--accent-dark);
        }

        h2 {
            font-size: 18px;
            margin: 24px 0 8px;
            color: var(--accent-dark);
        }

        .subtitle {
            margin-bottom: 18px;
            font-size: 13px;
            color: var(--text-muted);
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 14px;
            margin-top: 8px;
        }

        .summary-item {
            padding: 10px 12px;
            border-radius: 10px;
            background: #faf8ff;
            border: 1px solid #ece4ff;
        }

        .summary-label {
            font-size: 11px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 4px;
        }

        .summary-value {
            font-size: 15px;
            font-weight: 600;
            color: var(--accent-dark);
        }

        .summary-value.em {
            color: var(--accent);
        }

        .summary-value.warn {
            color: var(--danger);
        }

        table {
            border-collapse: collapse;
            width: 100%;
            margin-top: 10px;
            font-size: 13px;
        }

        th, td {
            border: 1px solid var(--border-subtle);
            padding: 6px 8px;
            text-align: left;
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

        td.num {
            text-align: right;
            font-variant-numeric: tabular-nums;
        }

        .footer-note {
            margin-top: 14px;
            font-size: 11px;
            color: var(--text-muted);
        }

        .chip {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            background: #fbefff;
            color: var(--accent-dark);
            font-size: 11px;
            margin-left: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>
                RaterHub Session Report
                <span class="badge">Daily Tracker</span>
            </h1>
            <div class="subtitle">
                A quick snapshot of this rating session. Generated on <strong>$today</strong>.
            </div>

            <div class="summary-grid">
                <div class="summary-item">
                    <div class="summary-label">Session ID</div>
                    <div class="summary-value">$sessionId</div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">Session Window</div>
                    <div class="summary-value">
                        $sessionStart &ndash; $sessionEnd
                    </div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">Total Questions</div>
                    <div class="summary-value em">$totalQuestions</div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">Total Time</div>
                    <div class="summary-value">
                        $totalSeconds sec ($totalMinutes min)
                    </div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">Average Time / Question</div>
                    <div class="summary-value em">$avgSeconds sec</div>
                </div>
            </div>

            <h2>Per-Question Detail<span class="chip">Time spent per prompt</span></h2>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Start</th>
                        <th>End</th>
                        <th>Seconds</th>
                        <th>Minutes</th>
                    </tr>
                </thead>
                <tbody>
                    $rowsHtml
                </tbody>
            </table>

            <div class="footer-note">
                Tip: Shorter average times with consistent quality usually mean you're in a good flow. 💜
            </div>
        </div>
    </div>
</body>
</html>
"@

$html | Out-File -FilePath $htmlPath -Encoding UTF8
Write-Host "HTML report written to: $htmlPath" -ForegroundColor Cyan
Write-Host "RaterHub session tracker finished." -ForegroundColor Cyan


$html | Out-File -FilePath $htmlPath -Encoding UTF8
Write-Host "HTML report written to: $htmlPath" -ForegroundColor Cyan
Write-Host "RaterHub session tracker finished." -ForegroundColor Cyan
