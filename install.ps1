# install.ps1 — установщик утилит terminal-utils для Windows
#
# Использование:
#   irm https://raw.githubusercontent.com/rival-afk/terminal-utils/main/install.ps1 | iex
#   .\install.ps1              # интерактивное меню
#   .\install.ps1 all          # установить всё доступное
#   .\install.ps1 update ascii # установить выбранные утилиты
#
# Без вопросов (с аргументами) при запуске через iex:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/rival-afk/terminal-utils/main/install.ps1))) update ascii
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/rival-afk/terminal-utils/main/install.ps1))) all
#
# Переменные окружения:
#   INSTALL_DIR  - куда ставить исполняемые файлы (по умолчанию %USERPROFILE%\.local\bin)
#   APP_DIR      - куда ставить исходники/venv ascii (по умолчанию %USERPROFILE%\.local\share\terminal-utils)
#   BRANCH       - ветка репозитория (по умолчанию main)
#
# Не поддерживается на Windows:
#   sua          - требует Unix sudo (/proc, gsettings, системная тема GTK)
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Tools
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo       = 'rival-afk/terminal-utils'
$Branch     = if ($env:BRANCH)      { $env:BRANCH }      else { 'main' }
$RawBase    = "https://raw.githubusercontent.com/$Repo/$Branch"
$ArchiveUrl = "https://codeload.github.com/$Repo/zip/refs/heads/$Branch"
$InstallDir = if ($env:INSTALL_DIR) { $env:INSTALL_DIR } else { Join-Path $HOME '.local\bin' }
$AppDir     = if ($env:APP_DIR)     { $env:APP_DIR }     else { Join-Path $HOME '.local\share\terminal-utils' }

# --- вывод -------------------------------------------------------------------

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Warn($msg) { Write-Warning $msg }
function Fail($msg) { Write-Host "  ✗ $msg" -ForegroundColor Red }

# --- доступность python ------------------------------------------------------

function Get-PythonCommand {
    # Возвращает массив: exe + (необязательные) префиксные аргументы (py -3)
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @($python.Source) }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @($py.Source, '-3') }
    return $null
}

$script:PythonCmd = @(Get-PythonCommand)
$script:HasPython = $script:PythonCmd.Count -gt 0

# Путь для вставки в .cmd-файл (.cmd читается в OEM-кодировке,
# поэтому не-ASCII пути заменяем на 8.3 short path)
function Get-ShimPath([string]$Path) {
    if ($Path -notmatch '[^\x20-\x7E]') { return $Path }
    try {
        $fso = New-Object -ComObject Scripting.FileSystemObject
        if (Test-Path -LiteralPath $Path -PathType Container) {
            return $fso.GetFolder($Path).ShortPath
        }
        return $fso.GetFile($Path).ShortPath
    } catch {
        throw "Путь '$Path' содержит не-ASCII символы, а конвертация в 8.3 не удалась. Укажите ASCII-пути через INSTALL_DIR/APP_DIR."
    }
}

function ConvertTo-CmdLiteral([string]$s) {
    # Экранируем " для использования внутри кавычек в .cmd
    return $s -replace '"', '""'
}

function Write-CmdShim([string]$Dest, [string[]]$Command) {
    # Пишем .cmd в ASCII: все не-ASCII пути заменяем short path'ами
    $parts = foreach ($c in $Command) {
        if ($c -match '^[a-zA-Z]:\\.*' -or (Test-Path -LiteralPath $c -ErrorAction SilentlyContinue)) {
            '"' + (ConvertTo-CmdLiteral (Get-ShimPath $c)) + '"'
        } else {
            $c
        }
    }
    $content = "@echo off`r`n" + ($parts -join ' ') + " %*`r`n"
    [System.IO.File]::WriteAllText($Dest, $content, [System.Text.Encoding]::ASCII)
}

function Add-ToUserPath([string]$Dir) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @()
    if ($userPath) { $entries = $userPath -split ';' | Where-Object { $_ } }
    $normalized = $Dir.TrimEnd('\')
    $exists = $entries | Where-Object { $_.TrimEnd('\') -ieq $normalized }
    if ($exists) { return $false }
    $newPath = if ($userPath) { ($userPath.TrimEnd(';')) + ';' + $Dir } else { $Dir }
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    return $true
}

# --- скачивание --------------------------------------------------------------

function Download-File([string]$Url, [string]$Dest) {
    $oldProgress = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    try {
        Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing -ErrorAction Stop
    } finally {
        $ProgressPreference = $oldProgress
    }
}

# --- установка утилит --------------------------------------------------------

function Install-SingleFileTool([string]$Name) {
    if (-not $script:HasPython) {
        Fail "update требует Python 3 (winget install Python.Python.3.12)"
        return $false
    }
    Step "Установка ${Name}:"
    $toolDir = Join-Path $AppDir $Name
    New-Item -ItemType Directory -Force -Path $toolDir | Out-Null
    $source = Join-Path $toolDir $Name
    try {
        Download-File "$RawBase/$Name/$Name" $source
    } catch {
        Fail "Не удалось скачать $RawBase/$Name/$Name : $($_.Exception.Message)"
        return $false
    }
    $shim = Join-Path $InstallDir "$Name.cmd"
    Write-CmdShim $shim (@($script:PythonCmd) + @($source))
    Ok "$Name установлен в $shim"
    return $true
}

function Install-Ascii {
    if (-not $script:HasPython) {
        Fail "ascii требует Python 3 (winget install Python.Python.3.12)"
        return $false
    }
    Step "Установка ascii:"
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("terminal-utils-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
        $zip = Join-Path $tmp 'repo.zip'
        try {
            Download-File $ArchiveUrl $zip
        } catch {
            Fail "Не удалось скачать архив $ArchiveUrl : $($_.Exception.Message)"
            return $false
        }

        $tar = Get-Command tar -ErrorAction SilentlyContinue
        if ($tar) {
            & tar -xf $zip -C $tmp
            if ($LASTEXITCODE -ne 0) { Fail "tar не смог распаковать архив."; return $false }
        } else {
            Expand-Archive -Path $zip -DestinationPath $tmp -Force
        }

        $src = Get-ChildItem -Path $tmp -Directory |
            Where-Object { Test-Path (Join-Path $_.FullName 'ascii\main.py') } |
            Select-Object -First 1
        if (-not $src) {
            Fail "В архиве не найден пакет ascii."
            return $false
        }

        $dest = Join-Path $AppDir 'ascii'
        if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
        Copy-Item -Recurse (Join-Path $src.FullName 'ascii') $dest
        Ok "Исходники ascii скопированы в $dest"

        # venv + зависимости
        $venvPython = Join-Path $dest '.venv\Scripts\python.exe'
        $pythonExe = $script:PythonCmd[0]
        $pythonArgs = @()
        if ($script:PythonCmd.Length -gt 1) { $pythonArgs += $script:PythonCmd[1..($script:PythonCmd.Length - 1)] }

        $venvOk = $false
        try {
            & $pythonExe @pythonArgs -m venv (Join-Path $dest '.venv') | Out-Null
            if ($LASTEXITCODE -eq 0 -and (Test-Path $venvPython)) { $venvOk = $true }
        } catch {
            Warn "venv не создан: $($_.Exception.Message)"
            $venvOk = $false
        }

        $shimPython = $null
        if ($venvOk) {
            Step "Установка зависимостей в venv:"
            try {
                & $venvPython -m pip install -q -r (Join-Path $dest 'requirements.txt') | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    $shimPython = $venvPython
                    Ok "Зависимости установлены в venv"
                } else {
                    throw "pip вернул код $LASTEXITCODE"
                }
            } catch {
                Warn "Не удалось установить зависимости в venv, пробую pip --user: $($_.Exception.Message)"
                Remove-Item -Recurse -Force (Join-Path $dest '.venv') -ErrorAction SilentlyContinue
                $venvOk = $false
            }
        }
        if (-not $venvOk) {
            Step "Установка зависимостей через pip --user:"
            try {
                & $pythonExe @pythonArgs -m pip install --user -q -r (Join-Path $dest 'requirements.txt') | Out-Null
            } catch {
                Fail "Не удалось запустить pip: $($_.Exception.Message)"
                return $false
            }
            if ($LASTEXITCODE -eq 0) {
                $shimPython = $pythonExe
                $shimPrefix = $pythonArgs
                Ok "Зависимости установлены (pip --user)"
            } else {
                Fail "Не удалось установить зависимости (нужен python -m pip или venv)"
                return $false
            }
        }
        if (-not $shimPrefix) { $shimPrefix = @() }

        $shim = Join-Path $InstallDir 'ascii.cmd'
        Write-CmdShim $shim (@($shimPython) + $shimPrefix + @((Join-Path $dest 'ascii')))
        Ok "ascii установлен в $shim"
        return $true
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

function Install-Tool([string]$Name) {
    switch ($Name) {
        'update'   { return (Install-SingleFileTool 'update') }
        'pyreq'    { return (Install-SingleFileTool 'pyreq') }
        'ascii'    { return (Install-Ascii) }
        'sua'      { Fail "sua не поддерживается на Windows (требуется Unix sudo). Используйте Linux/macOS или WSL."; return $false }
        'all' {
            $ok = $true
            foreach ($t in 'update', 'ascii', 'pyreq') {
                if (-not (Install-Tool $t)) { $ok = $false }
            }
            Warn "sua пропущен: не поддерживается на Windows."
            return $ok
        }
        default    { Fail "Неизвестная утилита: '$Name' (допустимо: sua, update, ascii, pyreq, all)"; return $false }
    }
}

function Show-Menu {
    Write-Host ""
    Write-Host "Доступные утилиты:" -ForegroundColor Cyan
    Write-Host "  1) sua    — НЕ поддерживается на Windows (нужен Unix sudo)"
    Write-Host "  2) update — удалить файл и открыть заново в редакторе"
    Write-Host "  3) ascii  — визуализатор структуры папок и репозиториев (Python)"
    Write-Host "  4) pyreq  — requirements.txt из pip list в venv"
    Write-Host ""
    $reply = Read-Host "Что установить? Номера через пробел/запятую, 'all' — все, 'q' — отмена"
    return ($reply -replace ',', ' ') -split '\s+' | Where-Object { $_ }
}

function Map-Token([string]$Token) {
    switch ($Token) {
        '1'   { 'sua' }
        '2'   { 'update' }
        '3'   { 'ascii' }
        '4'   { 'pyreq' }
        'sua' { 'sua' }
        'update' { 'update' }
        'ascii'  { 'ascii' }
        'pyreq'  { 'pyreq' }
        'all'    { 'all' }
        { $_ -in 'q', 'quit', 'exit' } { 'quit' }
        default   { $null }
    }
}

function Show-Usage {
    Write-Host "Установка terminal-utils для Windows"
    Write-Host ""
    Write-Host "Использование:"
    Write-Host "  .\install.ps1                 интерактивное меню"
    Write-Host "  .\install.ps1 all             установить все утилиты"
    Write-Host "  .\install.ps1 update pyreq    установить выбранные"
    Write-Host ""
    Write-Host "Через iex с аргументами:"
    Write-Host "  & ([scriptblock]::Create((irm $RawBase/install.ps1))) update ascii"
    Write-Host "  & ([scriptblock]::Create((irm $RawBase/install.ps1))) all"
    Write-Host ""
    Write-Host "Переменные: INSTALL_DIR ($InstallDir), APP_DIR ($AppDir), BRANCH ($Branch)"
}

# --- main ----------------------------------------------------------------------

foreach ($arg in $Tools) {
    if ($arg -in '-h', '--help') { Show-Usage; return }
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

if (-not $Tools -or $Tools.Count -eq 0) {
    $tokens = Show-Menu
    if (-not $tokens) {
        Warn "Ничего не выбрано"
        $Tools = @()
    } else {
        $selected = foreach ($t in $tokens) {
            $mapped = Map-Token $t
            if ($null -eq $mapped) { Fail "Неизвестный выбор: '$t'" }
            elseif ($mapped -ne 'quit') { $mapped }
        }
        $Tools = @($selected)
        if ($Tools.Count -eq 0) { Step "Отмена." }
    }
}

$failed = $false
if ($Tools) {
    foreach ($tool in $Tools) {
        if ($tool -eq 'quit') { continue }
        if (-not (Install-Tool $tool)) { $failed = $true }
    }
}

# PATH: добавляем INSTALL_DIR в пользовательский PATH, если его там нет
try {
    if (Add-ToUserPath $InstallDir) {
        $env:Path = "$InstallDir;$env:Path"
        Ok "'$InstallDir' добавлен в пользовательский PATH (перезапустите терминал)"
    }
} catch {
    Warn "Не удалось обновить пользовательский PATH: $($_.Exception.Message)"
    Warn "Добавьте вручную: [Environment]::SetEnvironmentVariable('Path', `$env:Path + ';$InstallDir', 'User')"
}

Write-Host ""
if ($failed) {
    Fail "Установка завершена с ошибками."
    # Не вызываем exit в iex-сессии — он закроет PowerShell у пользователя
    if ($PSCommandPath) { exit 1 }
} else {
    Write-Host "Готово! Утилиты доступны в новых терминалах (update, ascii, pyreq)." -ForegroundColor Green
}
