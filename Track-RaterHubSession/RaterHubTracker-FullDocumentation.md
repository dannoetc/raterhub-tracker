
# RaterHub Time Tracker – Full Documentation

## 1. Overview

This setup lets you track how long each **RaterHub** question takes, without modifying the browser or the site:

- A **PowerShell 7** script runs in the background and records timing for each question.
- An **AutoHotkey v2** script listens for hotkeys while you’re in Edge and sends simple “signals” to PowerShell.
- The tracker:
  - Records **per-question active time** (excluding pauses).
  - Appends each question to a **daily CSV**.
  - Generates a per-session **HTML dashboard** with:
    - Question-by-question timing (mm:ss)
    - Cute purple bar visualizations
    - Sparkline across all questions in the session
    - AHT compared to a **5.5-minute target**
    - Emojis + per-session score.
- A separate **daily summary script** generates an **end-of-day HTML report** with:
  - Total questions
  - Total active time
  - Daily AHT vs 5.5-minute target
  - Sparkline for the whole day
  - Per-session breakdown (with scores and emojis)

> ⚠️ **Important:** The tracking script requires **PowerShell 7+** and **does not work in Windows PowerShell 5.1**. That’s intentional - no neat emojis in PowerShell 5.1. 

---

## 2. Components

There are three main pieces:

1. **RaterHubTracker.ps1**  
   - Live session tracker (timing + session HTML + daily CSV)
2. **New-RaterHubDailyReport.ps1**  
   - End-of-day summary (daily HTML report from CSV)
3. **RaterHubHotkeys.ahk (AutoHotkey v2)**  
   - Global hotkeys in Edge that send commands to PowerShell

### File locations (recommended)

- PowerShell scripts:
  - `C:\Scripts\RaterHubTracker.ps1`
  - `C:\Scripts\New-RaterHubDailyReport.ps1`
- AutoHotkey script:
  - `C:\Scripts\RaterHubHotkeys.ahk` (or `%UserProfile%\Documents\AutoHotkey\`)

### Data/output locations

- **Signal file** (AHK → PowerShell):  
  - `C:\RaterHubTracker\signals.txt`
- **Per-session & daily data** (CSV + HTML reports, default):  
  - `Documents\RaterHubTracker\` in the user profile, e.g.  
    `C:\Users\<username>\Documents\RaterHubTracker\`

---

## 3. Prerequisites

### 3.1 Install PowerShell 7

You **must** run the scripts in PowerShell 7 (aka `pwsh`), not the built-in 5.1.

1. Download PowerShell 7 from the official site (MS Store or MSI).
2. After installation, you should have:
   - `C:\Program Files\PowerShell\7\pwsh.exe`
3. Open **PowerShell 7** and run:
   ```powershell
   $PSVersionTable.PSVersion
   ```
   You should see `Major = 7`.

> Tip: On Windows, you’ll typically have a “PowerShell 7 (x64)” start menu shortcut. Use that for testing.

---

### 3.2 Install AutoHotkey v2

1. Download AutoHotkey v2 from the official site.
2. Install, selecting **v2** (not v1).
3. Verify by creating a tiny test script:

   ```ahk
   #Requires AutoHotkey v2.0+
   MsgBox "AHK v2 is running!"
   ```

   - Save as `TestV2.ahk`.
   - Double-click it.
   - You should see the message box; the tray icon should show AHK v2 in “About”.

---

## 4. AutoHotkey v2 script (RaterHubHotkeys.ahk)

This script defines hotkeys that only work while **Microsoft Edge** is the active window:

- **Ctrl + Q** → Mark **NEXT** question  
- **Ctrl + Alt + Q** → **PAUSE / RESUME** timing for the current question  
- **Ctrl + Shift + Q** → **END** the current session  
- (Optional) **Ctrl + Win + D** → Generate a daily report.

### 4.1 Script content

```ahk
#Requires AutoHotkey v2.0+

; ---------------------------------------------------------------
; Configuration
; ---------------------------------------------------------------
signalFolder := "C:\RaterHubTracker"
signalFile   := signalFolder "\signals.txt"

if !DirExist(signalFolder) {
    DirCreate(signalFolder)
}

LogRaterHubSignal(cmd) {
    global signalFile
    timestamp := FormatTime(A_Now, "yyyyMMddTHHmmss")
    line := cmd " " timestamp "`n"
    FileAppend(line, signalFile, "UTF-8")
}

; ---------------------------------------------------------------
; Hotkeys (only when Edge is active)
; ---------------------------------------------------------------
#HotIf WinActive("ahk_exe msedge.exe")

; Ctrl+Q → NEXT
^q::{
    LogRaterHubSignal("NEXT")
}

; Ctrl+Alt+Q → PAUSE / RESUME toggle
^!q::{
    LogRaterHubSignal("PAUSE")
}

; Ctrl+Shift+Q → END session
^+q::{
    LogRaterHubSignal("EXIT")
}

#HotIf
```

> You can further restrict hotkeys to only the **RaterHub tab** by swapping  
> `#HotIf WinActive("ahk_exe msedge.exe")`  
> for something like:  
> `#HotIf WinActive("Rater Hub") and WinActive("ahk_exe msedge.exe")`  
> (tab titles can vary, so test it).

### 4.2 Running the AHK script

- Double-click `RaterHubHotkeys.ahk`.
- You should see the green “H” icon in the system tray.  
- While in Edge, pressing the hotkeys will write `NEXT`, `PAUSE`, and `EXIT` lines into `C:\RaterHubTracker\signals.txt`.

---

## 5. Live session tracker (RaterHubTracker.ps1)

This script:

- Listens for signals from AutoHotkey via `C:\RaterHubTracker\signals.txt`
- Tracks timing of each question as **active time only**:
  - Pauses (Ctrl+Alt+Q) are subtracted from the current question’s duration.
- Appends question records to a **daily CSV**:
  - `RaterHub-YYYY-MM-DD.csv`
- Generates a **per-session HTML report**:
  - `RaterHubSession-YYYY-MM-DD-HHMMSS.html`

### 5.1 Parameters

```powershell
param(
    [string]$OutputFolder = "$env:USERPROFILE\Documents\RaterHubTracker",
    [switch]$LaunchEdgeIfNeeded,
    [double]$TargetMinutesPerQuestion = 5.5
)
```

- **OutputFolder**  
  Where CSVs and HTML reports are stored.
- **LaunchEdgeIfNeeded**  
  If supplied, the script will launch Edge to the RaterHub URL if it doesn’t see a “Rater Hub” window.
- **TargetMinutesPerQuestion**  
  AHT target; default is `5.5` minutes.

### 5.2 How it works (flow)

1. Script starts:
   - Ensures `OutputFolder` and `C:\RaterHubTracker` exist.
   - Clears/creates `signals.txt`.
   - Optionally launches Edge to `https://raterhub.com/evaluation/rater`.
   - Starts **Question 1** immediately.
2. Main loop:
   - Every 200ms:
     - Reads `signals.txt`.
     - For each command:
       - `PAUSE`:
         - First `PAUSE` → mark start of pause (`isPaused = $true`).
         - Second `PAUSE` → mark end of pause; add that pause duration to a “paused seconds” accumulator for the current question.
       - `NEXT`:
         - If paused, auto-ends the pause and accumulate time.
         - Calculates active time = (now - questionStart - pausedSeconds).
         - Adds a new record to `$questions`.
         - Resets pause accumulator and starts the next question.
       - `EXIT`:
         - Same as `NEXT`, but **ends** the session after recording the final question.
   - Keeps running until `EXIT` is received.
3. After session end:
   - Appends `$questions` to the daily CSV (creating it if needed).
   - Calculates per-session metrics:
     - Total questions
     - Total active time
     - Average seconds per question
     - AHT vs `TargetMinutesPerQuestion`
     - Pace label + emoji
     - Session score (0–100)
   - Builds a purple HTML dashboard:
     - Summary card
     - Sparkline (SVG) of all question times in the session
     - Table of questions with mm:ss and bar chart per row

### 5.3 Running the tracker

> **Important:** Run in **PowerShell 7** (`pwsh`), not Windows PowerShell.

From PowerShell 7:

```powershell
cd C:\Scripts

# simplest run (uses defaults, doesn’t auto-launch Edge)
pwsh .\RaterHubTracker.ps1

# or auto-launch Edge to RaterHub
pwsh .\RaterHubTracker.ps1 -LaunchEdgeIfNeeded

# or override the AHT target
pwsh .\RaterHubTracker.ps1 -TargetMinutesPerQuestion 5.5
```

You’ll see console output like:

- “Question 1 started at …”
- “[SIGNAL] NEXT → recorded Question 1…”
- “[SIGNAL] PAUSE → timing paused/resumed…”
- etc.

### 5.4 Outputs

- **CSV (daily, appended each session)**  
  - `RaterHub-YYYY-MM-DD.csv`  
  - Columns:
    - `Date`
    - `SessionId`
    - `QuestionNumber`
    - `StartTime`
    - `EndTime`
    - `DurationSeconds`
    - `DurationMinutes`
- **Session HTML report**  
  - `RaterHubSession-YYYY-MM-DD-HHMMSS.html`  
  - Includes:
    - Session ID
    - Session window (first/last question)
    - Total questions
    - Total active time
    - AHT vs target
    - Pace emoji + score
    - Sparkline
    - Per-question breakdown table with mm:ss + bar chart

---

## 6. Daily summary script (New-RaterHubDailyReport.ps1)

This script reads the daily CSV and generates a **daily dashboard**.

### 6.1 Parameters

```powershell
param(
    [string]$InputFolder  = "$env:USERPROFILE\Documents\RaterHubTracker",
    [string]$OutputFolder = "$env:USERPROFILE\Documents\RaterHubTracker",
    [datetime]$Date       = (Get-Date),
    [double]$TargetMinutesPerQuestion = 5.5
)
```

- **InputFolder**  
  Folder containing `RaterHub-YYYY-MM-DD.csv`.
- **OutputFolder**  
  Where daily HTML summary is written.
- **Date**  
  Day to report on (defaults to today).
- **TargetMinutesPerQuestion**  
  Same concept as the session script.

### 6.2 What it does

Given `RaterHub-YYYY-MM-DD.csv`, it:

1. Loads all rows for that day.
2. Computes **daily overall metrics**:
   - Total questions
   - Total active time
   - Daily AHT (mm:ss)
   - Pace label + emoji + score vs target.
3. Computes **per-session metrics** by grouping on `SessionId`:
   - Number of questions per session
   - Session window (start/end)
   - Average per question (mm:ss)
   - Total minutes
   - Pace emoji + score.
4. Builds a **daily sparkline** over all questions for that day.
5. Generates a daily HTML report:
   - `RaterHubDaily-YYYY-MM-DD.html`.

### 6.3 Running manually

From PowerShell 7:

```powershell
cd C:\Scripts

# Daily report for today
pwsh .\New-RaterHubDailyReport.ps1

# Daily report for a specific date
pwsh .\New-RaterHubDailyReport.ps1 -Date '2025-11-25'

# Different target (if spec changes)
pwsh .\New-RaterHubDailyReport.ps1 -TargetMinutesPerQuestion 6.0
```

---

## 7. Automation options

### 7.1 Scheduled Task (end-of-day summary)

To auto-generate the daily HTML:

1. Open **Task Scheduler** → *Create Task…*
2. **General**:
   - Give it a name like “RaterHub Daily Report”.
3. **Triggers**:
   - New → Daily, at e.g. **23:55**.
4. **Actions**:
   - New → Program/script:
     ```text
     pwsh.exe
     ```
   - Arguments:
     ```text
     -ExecutionPolicy Bypass -File "C:\Scripts\New-RaterHubDailyReport.ps1"
     ```
5. Save.

Each night, `RaterHubDaily-YYYY-MM-DD.html` will be generated automatically.

### 7.2 AHK hotkey for daily report (optional)

If you prefer a “I’m done, press a key” flow, add to your AHK v2 script:

```ahk
; Ctrl+Win+D → Generate daily report for today
^#d::{
    Run 'pwsh.exe -ExecutionPolicy Bypass -File "C:\Scripts\New-RaterHubDailyReport.ps1"', , "Hide"
}
```

Now **Ctrl + Win + D** will kick off the daily summary.

---

## 8. Troubleshooting

### 8.1 No hotkeys working

- Check that AutoHotkey v2 is installed and running.
- Confirm the script has `#Requires AutoHotkey v2.0+`.
- Make sure Edge is the active window (hotkeys are scoped with `#HotIf WinActive("ahk_exe msedge.exe")`).

### 8.2 No signals appearing in `signals.txt`

- Confirm `C:\RaterHubTracker\signals.txt` exists.
- Press a hotkey (Ctrl+Q) and then open the file in Notepad; you should see lines like:
  ```text
  NEXT 20251125T203012
  ```

### 8.3 PowerShell script not reacting

- Make sure you’re running the script in **PowerShell 7** (`pwsh`), not 5.1.
- Check console output for `[ERROR]` or `[WARN]` messages.
- Ensure the `SignalFolder`/`SignalFile` paths in the PS script match those in the AHK script.

### 8.4 HTML looks broken

- Make sure the script wrote out an `.html` without being truncated.
- Try opening the HTML in Edge/Chrome instead of IE mode.

---

## 9. User-friendly quick start (for the rater)

1. Open **PowerShell 7**.
2. Run:
   ```powershell
   pwsh C:\Scripts\RaterHubTracker.ps1 -LaunchEdgeIfNeeded
   ```
3. Rate as normal in RaterHub:
   - When you finish a question → **Ctrl+Q**
   - When you need a break → **Ctrl+Alt+Q** (press again to resume)
   - When you’re done for the session → **Ctrl+Shift+Q**
4. Open the latest `RaterHubSession-*.html` in your `Documents\RaterHubTracker` folder to see your stats.
5. At the end of the day, either:
   - Let the scheduled task generate `RaterHubDaily-YYYY-MM-DD.html`, or
   - Run:
     ```powershell
     pwsh C:\Scripts\New-RaterHubDailyReport.ps1
     ```
   and open the daily summary HTML.

