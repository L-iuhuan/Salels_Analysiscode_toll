<#
    版本号钩子脚本 —— bump_version.ps1

    用途：
        开发者每次改完流水线代码、push 之前，在流水线仓库工作区运行本脚本，
        把当前 commit 短哈希 + 时间戳写进 code/version.txt。
        客户端（KanbanRunner）同步代码后会读取并显示该版本，方便确认拿到的是最新代码。

    用法：
        手动运行（默认当前目录，需在流水线代码所在目录执行）：
            powershell -File tools\bump_version.ps1
        指定流水线代码目录：
            powershell -File tools\bump_version.ps1 -CodeDir .\code
        加入 git pre-push 钩子（.git/hooks/pre-push，内容二选一）：
            # 1) 直接在流水线代码目录执行
            powershell -File "%~dp0..\tools\bump_version.ps1" -CodeDir "%~dp0code"
            # 2) 或在仓库根目录执行
            powershell -File "$(git rev-parse --show-toplevel)\tools\bump_version.ps1" -CodeDir "$(git rev-parse --show-toplevel)\code"

    输出格式（写进 version.txt）：
        v<shorthash> @ yyyy-MM-dd HH:mm
        例：v3f2a9c1 @ 2026-08-14 11:30
        非 git 环境或取哈希失败时用 "nogit" 兜底。
#>
[CmdletBinding()]
param(
    [string]$CodeDir = "."
)

$ErrorActionPreference = "Stop"

# ── 1) 取 commit 短哈希（失败/非 git 仓库时用 nogit 兜底） ──
$shortHash = "nogit"
try {
    $hash = & git rev-parse --short HEAD 2>$null
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($hash)) {
        $shortHash = $hash.Trim()
    }
} catch {
    $shortHash = "nogit"
}

# ── 2) 组装版本串并写文件 ──
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
$version = "v{0} @ {1}" -f $shortHash, $stamp

if (-not (Test-Path -LiteralPath $CodeDir)) {
    New-Item -ItemType Directory -Path $CodeDir -Force | Out-Null
}
$target = Join-Path $CodeDir "version.txt"
# 用无 BOM 的 UTF-8 写入，避免客户端读到 \ufeff 前缀
[System.IO.File]::WriteAllText($target, $version + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))

# ── 3) 提示 ──
Write-Output ("已写入版本 {0} 到 {1}" -f $version, $target)
