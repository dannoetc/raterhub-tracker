#Requires AutoHotkey v2.0+

; ---------------------------------------------------------------
; Configuration
; ---------------------------------------------------------------
signalFolder := "C:\RaterHubTracker"
signalFile   := signalFolder "\signals.txt"

; Ensure folder exists
if !DirExist(signalFolder) {
    DirCreate(signalFolder)
}

; Function to append command to signal file
LogRaterHubSignal(cmd) {
    global signalFile
    timestamp := FormatTime(A_Now, "yyyyMMddTHHmmss")
    line := cmd " " timestamp "`n"
    FileAppend(line, signalFile, "UTF-8")
}

; ---------------------------------------------------------------
; Hotkeys (active only when Edge is active)
; ---------------------------------------------------------------
#HotIf WinActive("ahk_exe msedge.exe")
; If you want to restrict further to the Rater Hub tab:
; #HotIf WinActive("Rater Hub", "ahk_exe msedge.exe")

; CTRL + Q → Next question
^q::{
    LogRaterHubSignal("NEXT")
}

; CTRL + SHIFT + Q → End session
^+q::{
    LogRaterHubSignal("EXIT")
}
#HotIf
