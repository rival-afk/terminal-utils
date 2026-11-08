# terminal-utils

Коллекция CLI-утилит.

## Утилиты

| Команда | Описание |
|---------|----------|
| `sua` | Аналог `sudo` с GUI-окном подтверждения. Показывает кто вызвал, команду, кнопки Разрешить/Отклонить, опция разрешить на день. Пароль не требуется. |
| `update` | Удаляет указанный файл и открывает его заново в редакторе (`$EDITOR`, иначе `nano` / `notepad` на Windows). Если файла нет — ищет похожие в той же директории. |
| `ascii` | Визуализатор структуры директорий. Поддерживает локальные папки и удалённые репозитории (GitHub, GitLab, Bitbucket, SourceForge). Строит дерево файлов и выводит содержимое текстовых файлов. |
| `pyreq` | Генерирует `requirements.txt` из текущего `pip list` в виртуальном окружении. |


## Установка

```bash
curl -fsSL https://raw.githubusercontent.com/rival-afk/terminal-utils/main/install.sh | sh
```

Скрипт покажет список утилит и спросит, что установить. Без вопросов:

```bash
curl -fsSL https://raw.githubusercontent.com/rival-afk/terminal-utils/main/install.sh | sh -s -- sua update
# или всё сразу:
curl -fsSL https://raw.githubusercontent.com/rival-afk/terminal-utils/main/install.sh | sh -s -- all
```

Исполняемые файлы ставятся в `~/.local/bin` (переопределяется переменной `INSTALL_DIR`), исходники `ascii` и его venv — в `~/.local/share/terminal-utils` (`APP_DIR`).

## Установка (Windows, PowerShell)

```powershell
irm https://raw.githubusercontent.com/rival-afk/terminal-utils/main/install.ps1 | iex
```

Без вопросов (с аргументами при запуске через `iex`):

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/rival-afk/terminal-utils/main/install.ps1))) update ascii pyreq
# или всё сразу:
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/rival-afk/terminal-utils/main/install.ps1))) all
```

Требуется Python 3 (`winget install Python.Python.3.12`). Файлы ставятся в `%USERPROFILE%\.local\bin` — лаунчеры `*.cmd` добавляются в пользовательский `PATH` автоматически (перезапустите терминал), исходники — в `%USERPROFILE%\.local\share\terminal-utils`. Переменные `INSTALL_DIR`, `APP_DIR`, `BRANCH` работают так же, как в шелл-установщике.

`sua` на Windows не поддерживается (нужен Unix `sudo`) — в списке установки она пропускается с предупреждением.

## Использование

```bash
# Добавить в PATH (если ещё не):
export PATH="$HOME/.local/bin:$PATH"
```

На Windows `PATH` обновляется установщиком автоматически. Ре-логин не нужен — достаточно нового окна терминала.

## Примечания

- `sua` впервые запустится с окном ввода пароля `sudo`, пароль шифруется (Fernet + машинно-зависимый ключ) и сохраняется в `~/.config/sua/`.
- `pyreq` запускает `pip` из активного venv и записывает зависимости в формате `>=`.
- `update` редактор по умолчанию берёт из `$EDITOR` (Windows: `notepad`).
