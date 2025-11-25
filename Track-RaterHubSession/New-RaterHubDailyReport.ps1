param(
    [string]$InputFolder  = "$env:USERPROFILE\Documents\RaterHubTracker",
    [string]$OutputFolder = "$env:USERPROFILE\Documents\RaterHubTracker",
    [datetime]$Date       = (Get-Date),
    [double]$TargetMinutesPerQuestion = 5.5  # AHT target in minutes
)

# -----------------------------
# Helpers
# -----------------------------
function Format-TimeMMSS {
    param(
        [double]$Seconds
    )
    $ts = [TimeSpan]::FromSeconds($Seconds)
    return "{0:00}:{1:00}" -f [math]::Floor($ts.TotalMinutes), $ts.Seconds
}

function Get-PaceLabelAndScore {
    param(
        [double]$AvgSeconds,
        [double]$TargetMinutesPerQuestion
    )

    $targetSeconds = $TargetMinutesPerQuestion * 60
    $ratio = if ($targetSeconds -gt 0) { $AvgSeconds / $targetSeconds } else { 0 }

    if ($AvgSeconds -le 0) {
        return [PSCustomObject]@{
            PaceLabel = "No questions"
            PaceEmoji = "😴"
            Score     = 0
            Ratio     = 0
        }
    }

    if     ($ratio -lt 0.5) { $paceLabel = "way too fast (<50% of target)"; $paceEmoji = "⚡🐇" }
    elseif ($ratio -lt 0.7) { $paceLabel = "fast (50–70% of target)";       $paceEmoji = "🐇"   }
    elseif ($ratio -lt 0.9) { $paceLabel = "slightly fast";                 $paceEmoji = "🙂"   }
    elseif ($ratio -lt 1.1) { $paceLabel = "on target";                     $paceEmoji = "💜✅" }
    elseif ($ratio -lt 1.3) { $paceLabel = "a bit slow";                    $paceEmoji = "🐢"   }
    else                    { $paceLabel = "slow, consider picking up";     $paceEmoji = "🐌"   }

    $score = [math]::Round(
        [math]::Max(0, [math]::Min(100, 100 * [math]::Exp(-1.2 * [math]::Abs($ratio - 1))))
    )

    return [PSCustomObject]@{
        PaceLabel = $paceLabel
        PaceEmoji = $paceEmoji
        Score     = $score
        Ratio     = $ratio
    }
}

# -----------------------------
# Locate CSV for the target date
# -----------------------------
$dayKey  = $Date.ToString('yyyy-MM-dd')
$csvPath = Join-Path $InputFolder ("RaterHub-{0}.csv" -f $dayKey)

if (-not (Test-Path $csvPath)) {
    Write-Host "No CSV found for $dayKey at $csvPath" -ForegroundColor Yellow
    return
}

Write-Host "Building daily report from: $csvPath" -ForegroundColor Cyan

$rows = Import-Csv -Path $csvPath

if (-not $rows -or $rows.Count -eq 0) {
    Write-Host "CSV is empty; nothing to summarize." -ForegroundColor Yellow
    return
}

# Ensure numeric
foreach ($row in $rows) {
    $row.DurationSeconds = [double]$row.DurationSeconds
    $row.DurationMinutes = [double]$row.DurationMinutes
}

# -----------------------------
# Overall daily metrics
# -----------------------------
$totalQuestions = $rows.Count
$totalSeconds   = ($rows | Measure-Object -Property DurationSeconds -Sum).Sum
if (-not $totalSeconds) { $totalSeconds = 0 }

$avgSecondsDaily = if ($totalQuestions -gt 0) { $totalSeconds / $totalQuestions } else { 0 }
$totalMinutes    = [math]::Round($totalSeconds / 60, 2)
$avgDailyMMSS    = Format-TimeMMSS $avgSecondsDaily

$dailyPace = Get-PaceLabelAndScore -AvgSeconds $avgSecondsDaily -TargetMinutesPerQuestion $TargetMinutesPerQuestion

# -----------------------------
# Per-session metrics (within the day)
# -----------------------------
$sessionGroups = $rows | Group-Object -Property SessionId

$sessionSummaries = foreach ($group in $sessionGroups) {
    $sid     = $group.Name
    $qRows   = $group.Group
    $qCount  = $qRows.Count
    $secSum  = ($qRows | Measure-Object -Property DurationSeconds -Sum).Sum
    if (-not $secSum) { $secSum = 0 }
    $avgSec  = if ($qCount -gt 0) { $secSum / $qCount } else { 0 }

    $startTime = ($qRows | Sort-Object QuestionNumber | Select-Object -First 1).StartTime
    $endTime   = ($qRows | Sort-Object QuestionNumber | Select-Object -Last 1).EndTime

    $pace = Get-PaceLabelAndScore -AvgSeconds $avgSec -TargetMinutesPerQuestion $TargetMinutesPerQuestion

    [PSCustomObject]@{
        SessionId        = $sid
        QuestionCount    = $qCount
        TotalSeconds     = [math]::Round($secSum, 2)
        TotalMinutes     = [math]::Round($secSum / 60, 2)
        AvgSeconds       = [math]::Round($avgSec, 2)
        AvgMMSS          = Format-TimeMMSS $avgSec
        StartTime        = $startTime
        EndTime          = $endTime
        PaceLabel        = $pace.PaceLabel
        PaceEmoji        = $pace.PaceEmoji
        Score            = $pace.Score
        Ratio            = $pace.Ratio
    }
}

# -----------------------------
# Sparkline for the day (all questions)
# -----------------------------
$maxSeconds = ($rows | Measure-Object -Property DurationSeconds -Maximum).Maximum
if ($maxSeconds -lt 1) { $maxSeconds = 1 }

$sparkBars = @()
for ($i = 0; $i -lt $rows.Count; $i++) {
    $q = $rows[$i]
    $h = [math]::Round(($q.DurationSeconds / $maxSeconds) * 100)
    if ($h -lt 3) { $h = 3 }
    $x = $i
    $y = 100 - $h
    $class = if ($q.DurationSeconds -eq $maxSeconds) { "bar max" } else { "bar" }
    $sparkBars += "<rect class='$class' x='$x' y='$y' width='0.8' height='$h' />"
}
$sparklineSvg = "<svg viewBox='0 0 $($rows.Count) 100' preserveAspectRatio='none' class='sparkline'>" +
                ($sparkBars -join "") +
                "</svg>"

# -----------------------------
# Build per-session HTML rows
# -----------------------------
$sessionRowsHtml = $sessionSummaries | Sort-Object StartTime | ForEach-Object {
    "<tr>
        <td>$($_.SessionId)</td>
        <td style='text-align:center;'>$($_.QuestionCount)</td>
        <td style='text-align:center;'>$($_.StartTime) – $($_.EndTime)</td>
        <td style='text-align:center;'>$($_.AvgMMSS)</td>
        <td style='text-align:center;'>$($_.TotalMinutes)</td>
        <td style='text-align:center;'>$($_.PaceEmoji)</td>
        <td style='text-align:center;'>$($_.Score)</td>
    </tr>"
} | Out-String

# -----------------------------
# Render HTML daily dashboard
# -----------------------------
if (-not (Test-Path $OutputFolder)) {
    New-Item -Path $OutputFolder -ItemType Directory -Force | Out-Null
}

$htmlPath = Join-Path $OutputFolder ("RaterHubDaily-{0}.html" -f $dayKey)

$html = @"
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>RaterHub Daily Summary - $dayKey</title>
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
            max-width: 1000px;
            margin: 0 auto;
        }

        .card {
            background: var(--card-bg);
            border-radius: 16px;
            border: 1px solid var(--border-subtle);
            box-shadow: 0 10px 30px rgba(0,0,0,0.05);
            padding: 24px 28px;
            margin-bottom: 18px;
        }

        h1 {
            font-size: 26px;
            margin: 0 0 6px;
            color: var(--accent-dark);
        }

        h2 {
            font-size: 18px;
            margin: 20px 0 8px;
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

        .footer-note {
            margin-top: 12px;
            font-size: 11px;
            color: var(--text-muted);
        }
    </style>
</head>
<body>
    <div class="container">

        <div class="card">
            <h1>RaterHub Daily Summary 💜</h1>
            <div class="subtitle">
                Date: <strong>$dayKey</strong> &mdash; All sessions combined.
            </div>

            <div class="summary-grid">
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
                    <div class="summary-value em">$avgDailyMMSS</div>
                    <div class="pace-label">Target: $TargetMinutesPerQuestion min</div>
                </div>

                <div class="summary-item">
                    <div class="summary-label">Daily Pace & Score</div>
                    <div class="summary-value">$($dailyPace.PaceEmoji) $($dailyPace.PaceLabel)</div>
                    <div class="pace-label">Score: $($dailyPace.Score) / 100</div>
                </div>
            </div>

            <div class="spark-wrapper">
                <div class="spark-header">Question Time Sparkline (all questions today)</div>
                $sparklineSvg
            </div>
        </div>

        <div class="card">
            <h2>Per-Session Breakdown</h2>
            <table>
                <thead>
                    <tr>
                        <th>Session ID</th>
                        <th># Questions</th>
                        <th>Window</th>
                        <th>Avg Time (mm:ss)</th>
                        <th>Total Minutes</th>
                        <th>Pace</th>
                        <th>Score</th>
                    </tr>
                </thead>
                <tbody>
                    $sessionRowsHtml
                </tbody>
            </table>

            <div class="footer-note">
                Each session’s pace and score are computed against an estimated target of $TargetMinutesPerQuestion minutes per question.
            </div>
        </div>

    </div>
</body>
</html>
"@

$html | Out-File -Path $htmlPath -Encoding UTF8
Write-Host "Daily HTML report written to: $htmlPath" -ForegroundColor Cyan
