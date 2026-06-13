# 在桌面创建 LiveTrans 快捷方式
$projectDir = Split-Path $PSScriptRoot -Parent
$target = Join-Path $projectDir "start.bat"
$shortcutPath = [System.IO.Path]::Combine($env:USERPROFILE, "Desktop", "LiveTrans.lnk")

$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($shortcutPath)
$sc.TargetPath = $target
$sc.WorkingDirectory = $projectDir
$sc.Description = "LiveTrans 直播实时翻译"
$sc.Save()

Write-Host "快捷方式已创建: $shortcutPath"
