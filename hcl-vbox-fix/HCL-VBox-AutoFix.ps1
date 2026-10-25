param(
    [string]$HclExe = "",
    [string]$VBoxManage = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogPath = Join-Path $ScriptDir "HCL-VBox-AutoFix.log"
try { Start-Transcript -Path $LogPath -Force | Out-Null } catch {}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Fail {
    param([string]$Message)
    Write-Host ""
    Write-Host "错误：$Message" -ForegroundColor Red
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}

function Remove-GenPyCache {
    param([string]$File)
    $cacheDir = Join-Path (Split-Path -Parent $File) "__pycache__"
    if (Test-Path $cacheDir) {
        $base = [IO.Path]::GetFileNameWithoutExtension($File)
        Get-ChildItem -LiteralPath $cacheDir -Filter "$base*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    }
}

function Patch-GenPyFile {
    param([string]$File)
    $text = [IO.File]::ReadAllText($File)
    if ($text -match 'if\s+aName\s*==\s*"headless"') {
        Remove-GenPyCache $File
        return "already"
    }

    $lines = [IO.File]::ReadAllLines($File)
    $out = New-Object System.Collections.Generic.List[string]
    $patched = $false

    for ($i = 0; $i -lt $lines.Length; $i++) {
        $line = $lines[$i]
        $out.Add($line)

        if (-not $patched -and $line -match '^(\s*)def\s+LaunchVMProcess\s*\(') {
            $defIndent = $Matches[1]
            $j = $i + 1
            while ($j -lt $lines.Length -and [string]::IsNullOrWhiteSpace($lines[$j])) { $j++ }
            if ($j -lt $lines.Length -and $lines[$j] -match '^(\s*)ret\s*=\s*self\._oleobj_\.InvokeTypes') {
                $bodyIndent = $Matches[1]
                $unit = "`t"
                if ($bodyIndent.Length -gt $defIndent.Length) { $unit = $bodyIndent.Substring($defIndent.Length) }
                $out.Add($bodyIndent + 'if aName == "headless":')
                $out.Add($bodyIndent + $unit + 'aName = "gui"')
                $patched = $true
            }
        }
    }

    if (-not $patched) { return "notfound" }

    $bak = $File + ".bak-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    Copy-Item -LiteralPath $File -Destination $bak -Force
    (Get-Item -LiteralPath $File).IsReadOnly = $false
    [IO.File]::WriteAllLines($File, [string[]]$out.ToArray(), (New-Object System.Text.UTF8Encoding($false)))
    Remove-GenPyCache $File
    return "patched"
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Fail "请以管理员身份运行。双击 HCL-VBox-AutoFix.cmd 会自动提权。" }

Write-Host "HCL + VirtualBox 一键修复" -ForegroundColor Green
Write-Host "适用：HCL 5.10.3 + VirtualBox 6.1.50"
Write-Host "默认目录：D:\HCL\HCL 和 D:\HCL\VirtualBox"
Write-Host "运行前请关闭 HCL 里的实验设备并保存配置。"
Write-Host ""
Read-Host "确认后按回车继续，按 Ctrl+C 取消"

Write-Step "检查安装路径"
if (-not $HclExe) {
    $hclCandidates = @(
        "D:\HCL\HCL\H3C Cloud Lab.exe",
        "C:\Program Files (x86)\HCL\H3C Cloud Lab.exe",
        "C:\Program Files\HCL\H3C Cloud Lab.exe"
    )
    foreach ($c in $hclCandidates) { if (Test-Path $c) { $HclExe = $c; break } }
}
if (-not $HclExe -or -not (Test-Path $HclExe)) { Fail "找不到 H3C Cloud Lab.exe。请确认 HCL 已安装，默认路径 D:\HCL\HCL。" }
Write-Host "HCL：$HclExe"

if (-not $VBoxManage) {
    $vboxCandidates = @(
        "D:\HCL\VirtualBox\VBoxManage.exe",
        "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe",
        "C:\Program Files (x86)\Oracle\VirtualBox\VBoxManage.exe"
    )
    foreach ($c in $vboxCandidates) { if (Test-Path $c) { $VBoxManage = $c; break } }
}
if (-not $VBoxManage -or -not (Test-Path $VBoxManage)) {
    $reg = Get-ItemProperty "HKLM:\SOFTWARE\Oracle\VirtualBox" -ErrorAction SilentlyContinue
    if ($reg -and $reg.InstallDir) {
        $candidate = Join-Path $reg.InstallDir.TrimEnd('\') "VBoxManage.exe"
        if (Test-Path $candidate) { $VBoxManage = $candidate }
    }
}
if (-not $VBoxManage -or -not (Test-Path $VBoxManage)) { Fail "找不到 VBoxManage.exe。请确认 VirtualBox 已安装。" }
Write-Host "VirtualBox：$VBoxManage"

$vboxVer = (& $VBoxManage --version 2>&1 | Out-String).Trim()
Write-Host "VirtualBox 版本：$vboxVer"
if ($vboxVer -notmatch '^6\.1\.') { Fail "当前 VirtualBox 是 $vboxVer。HCL 5.10.3 需要 6.1.x，7.x 的 COM 接口不兼容。请卸载后安装 6.1.50。" }
if ($vboxVer -notmatch '^6\.1\.50') { Write-Host "提示：本脚本在 6.1.50 上验证过；6.1.x 其他版本可以尝试，但建议 6.1.50。" -ForegroundColor Yellow }

try {
    $dg = Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard -ErrorAction Stop
    if ($dg.SecurityServicesRunning -contains 2) {
        Write-Host "警告：内存完整性（HVCI）已开启。VirtualBox 6.1.x 的驱动可能被拦，设备也可能起不来。建议先在 Windows 安全中心关闭内存完整性并重启。" -ForegroundColor Yellow
    }
} catch {}

Write-Step "设置 HCL 兼容性"
$layers = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
if (-not (Test-Path $layers)) { New-Item -Path $layers -Force | Out-Null }
Set-ItemProperty -Path $layers -Name $HclExe -Value "~ REGISTERAPPRESTART RUNASADMIN DPIUNAWARE"
Write-Host "已写入管理员和高 DPI 兼容标志。"

$vmFolder = Join-Path $env:USERPROFILE "VirtualBox VMs"
if (-not (Test-Path $vmFolder)) {
    New-Item -ItemType Directory -Path $vmFolder -Force | Out-Null
    Write-Host "已创建：$vmFolder"
}

Write-Step "关闭 HCL 和相关进程"
$procs = Get-Process | Where-Object { $_.ProcessName -match '^(H3C|HCL|Simware)' }
foreach ($p in $procs) {
    Write-Host "结束：$($p.ProcessName)"
    try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
}
Start-Sleep -Seconds 2

$GenPyRoot = Join-Path $env:LOCALAPPDATA "Temp\gen_py"
$GenPyPrefix = "D7569351-1750-46F0-936E-BD127D5BC264"

function Get-GenPyFiles {
    if (-not (Test-Path $GenPyRoot)) { return @() }
    return @(Get-ChildItem -Path $GenPyRoot -Recurse -File -Filter "$GenPyPrefix*.py" -ErrorAction SilentlyContinue)
}

$genPyFiles = Get-GenPyFiles
if (-not $genPyFiles -or $genPyFiles.Count -eq 0) {
    Write-Step "未找到 COM 包装，启动 HCL 生成"
    Start-Process -FilePath $HclExe | Out-Null
    $found = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        $genPyFiles = Get-GenPyFiles
        if ($genPyFiles -and $genPyFiles.Count -gt 0) { $found = $true; break }
    }
    if (-not $found) {
        Write-Host "HCL 已启动，但没有生成 COM 包装。" -ForegroundColor Yellow
        Write-Host "请在 HCL 里拖一台设备启动一次，失败后关闭 HCL，再重新运行本脚本。" -ForegroundColor Yellow
        try { Stop-Transcript | Out-Null } catch {}
        exit 2
    }
    Get-Process | Where-Object { $_.ProcessName -match '^(H3C|HCL|Simware)' } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    $genPyFiles = Get-GenPyFiles
}

Write-Step "修补 LaunchVMProcess"
$patchedCount = 0
$alreadyCount = 0
foreach ($f in $genPyFiles) {
    $result = Patch-GenPyFile $f.FullName
    if ($result -eq "patched") {
        Write-Host "已打补丁：$($f.FullName)" -ForegroundColor Green
        $patchedCount++
    } elseif ($result -eq "already") {
        Write-Host "补丁已存在：$($f.FullName)" -ForegroundColor Green
        $alreadyCount++
    } else {
        Write-Host "警告：文件里没有找到 LaunchVMProcess：$($f.FullName)" -ForegroundColor Yellow
    }
}
if ($patchedCount -eq 0 -and $alreadyCount -eq 0) { Fail "没有成功打补丁。请确认 VirtualBox 是 6.1.50，并先启动一次 HCL 生成包装。" }

Write-Step "完成"
Write-Host "打开 HCL，拖一台设备启动。"
Write-Host "每台设备会弹出一个 VirtualBox 窗口，最小化即可，不要关闭。"
Write-Host "日志：$LogPath"
try { Stop-Transcript | Out-Null } catch {}
