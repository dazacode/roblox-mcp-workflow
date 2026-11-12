param([string]$Out, [int]$Delay = 0)
if ($Delay -gt 0) { Start-Sleep -Seconds $Delay }
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class Win32Cap {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
  public static List<IntPtr> ForPid(uint pid) {
    var list = new List<IntPtr>();
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p); if (p == pid && IsWindowVisible(h)) list.Add(h); return true; }, IntPtr.Zero);
    return list;
  }
}
"@
$proc = Get-Process RobloxStudioBeta | Select-Object -First 1
$best = $null; $bestArea = 0
foreach ($h in [Win32Cap]::ForPid([uint32]$proc.Id)) {
  $r = New-Object Win32Cap+RECT
  [void][Win32Cap]::GetWindowRect($h, [ref]$r)
  $area = ($r.Right - $r.Left) * ($r.Bottom - $r.Top)
  if ($area -gt $bestArea) { $bestArea = $area; $best = $h; $br = $r }
}
if (-not $best) { "NO_WINDOW"; exit 1 }
$w = $br.Right - $br.Left; $h = $br.Bottom - $br.Top
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [Win32Cap]::PrintWindow($best, $hdc, 2)
$g.ReleaseHdc($hdc); $g.Dispose()
$sample = 0; $dark = 0
for ($x = 20; $x -lt $w; $x += [Math]::Max(1, [int]($w / 40))) { for ($y = 20; $y -lt $h; $y += [Math]::Max(1, [int]($h / 25))) { $c = $bmp.GetPixel($x, $y); $sample++; if (($c.R + $c.G + $c.B) -lt 30) { $dark++ } } }
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
"printwindow=$ok size=${w}x${h} darkFraction=" + [Math]::Round($dark / [Math]::Max(1, $sample), 2)
