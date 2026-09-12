# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

param(
    [Parameter(Mandatory = $true)]
    [string]$ExactTitle
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class VadgrE2EWindow {
    public delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hwnd);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
    [DllImport("kernel32.dll")]
    public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")]
    public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool attach);
    [DllImport("user32.dll")]
    public static extern bool BringWindowToTop(IntPtr hwnd);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")]
    public static extern IntPtr SetFocus(IntPtr hwnd);

    public static IntPtr[] ExactVisibleTitle(string title) {
        var matches = new List<IntPtr>();
        EnumWindows(delegate(IntPtr hwnd, IntPtr ignored) {
            if (!IsWindowVisible(hwnd)) return true;
            int length = GetWindowTextLength(hwnd);
            if (length == 0) return true;
            var text = new StringBuilder(length + 1);
            GetWindowText(hwnd, text, text.Capacity);
            string caption = text.ToString();
            if (caption == title || caption == title + " - Google Chrome for Testing") {
                matches.Add(hwnd);
            }
            return true;
        }, IntPtr.Zero);
        return matches.ToArray();
    }
}
"@

$matches = @([VadgrE2EWindow]::ExactVisibleTitle($ExactTitle))
if ($matches.Count -ne 1) {
    throw "Expected exactly one visible window with the test title; found $($matches.Count)."
}

$target = [IntPtr]$matches[0]
if ([VadgrE2EWindow]::IsIconic($target)) {
    throw "The exact test window is minimized; refusing to alter its state."
}

$foreground = [VadgrE2EWindow]::GetForegroundWindow()
$currentThread = [VadgrE2EWindow]::GetCurrentThreadId()
$foregroundProcess = [uint32]0
$targetProcess = [uint32]0
$foregroundThread = [VadgrE2EWindow]::GetWindowThreadProcessId(
    $foreground, [ref]$foregroundProcess
)
$targetThread = [VadgrE2EWindow]::GetWindowThreadProcessId(
    $target, [ref]$targetProcess
)

$attachedForeground = $false
$attachedTarget = $false
try {
    if ($foregroundThread -ne 0 -and $foregroundThread -ne $currentThread) {
        $attachedForeground = [VadgrE2EWindow]::AttachThreadInput(
            $currentThread, $foregroundThread, $true
        )
    }
    if ($targetThread -ne 0 -and $targetThread -ne $currentThread) {
        $attachedTarget = [VadgrE2EWindow]::AttachThreadInput(
            $currentThread, $targetThread, $true
        )
    }
    [void][VadgrE2EWindow]::BringWindowToTop($target)
    [void][VadgrE2EWindow]::SetForegroundWindow($target)
    [void][VadgrE2EWindow]::SetFocus($target)
} finally {
    if ($attachedTarget) {
        [void][VadgrE2EWindow]::AttachThreadInput(
            $currentThread, $targetThread, $false
        )
    }
    if ($attachedForeground) {
        [void][VadgrE2EWindow]::AttachThreadInput(
            $currentThread, $foregroundThread, $false
        )
    }
}

$deadline = [DateTime]::UtcNow.AddSeconds(3)
while ([DateTime]::UtcNow -lt $deadline) {
    if ([VadgrE2EWindow]::GetForegroundWindow() -eq $target) { break }
    Start-Sleep -Milliseconds 50
}
if ([VadgrE2EWindow]::GetForegroundWindow() -ne $target) {
    throw "The exact test window did not become the verified foreground window."
}

[pscustomobject]@{
    focused = $true
    process_id = $targetProcess
    minimized = $false
} | ConvertTo-Json -Compress
