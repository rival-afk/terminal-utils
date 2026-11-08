#!/bin/sh
# install.sh — интерактивный установщик утилит из terminal-utils
#
# Использование:
#   curl -fsSL https://raw.githubusercontent.com/rival-afk/terminal-utils/main/install.sh | sh
#   curl -fsSL https://raw.githubusercontent.com/rival-afk/terminal-utils/main/install.sh | sh -s -- sua update
#   ./install.sh              # интерактивное меню
#   ./install.sh all          # установить всё без вопросов
#   ./install.sh sua ascii    # установить только указанные
#
# Переменные окружения:
#   INSTALL_DIR  — куда класть исполняемые файлы (по умолчанию ~/.local/bin)
#   APP_DIR      — куда класть данные/исходники ascii (по умолчанию ~/.local/share/terminal-utils)
#   BRANCH       — ветка репозитория (по умолчанию main)
set -eu

REPO="rival-afk/terminal-utils"
BRANCH="${BRANCH:-main}"
RAW_BASE="https://raw.githubusercontent.com/$REPO/$BRANCH"
ARCHIVE_URL="https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
APP_DIR="${APP_DIR:-$HOME/.local/share/terminal-utils}"

# Цвета (только если вывод в терминал)
if [ -t 1 ]; then
    C_BOLD='\033[1m'; C_GREEN='\033[32m'; C_YELLOW='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
else
    C_BOLD=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_OFF=''
fi
info()  { printf "%b==>%b %s\n" "$C_BOLD" "$C_OFF" "$*"; }
ok()    { printf "%b  ✓%b %s\n" "$C_GREEN" "$C_OFF" "$*"; }
warn()  { printf "%b  !%b %s\n" "$C_YELLOW" "$C_OFF" "$*" >&2; }
err()   { printf "%b  ✗%b %s\n" "$C_RED" "$C_OFF" "$*" >&2; }

need_cmd() {
    command -v "$1" >/dev/null 2>&1
}

download() { # download <url> <dest>
    if need_cmd curl; then
        curl -fsSL "$1" -o "$2"
    elif need_cmd wget; then
        wget -qO "$2" "$1"
    else
        err "нужен curl или wget для скачивания файлов."
        exit 1
    fi
}

TMP_DIR=""
cleanup() {
    if [ -n "$TMP_DIR" ]; then rm -rf "$TMP_DIR"; fi
    return 0
}
trap cleanup EXIT INT TERM
make_tmp() {
    TMP_DIR="$(mktemp -d)"
}

ensure_dirs() {
    mkdir -p "$INSTALL_DIR"
    if [ ! -w "$INSTALL_DIR" ]; then
        err "директория '$INSTALL_DIR' недоступна для записи."
        exit 1
    fi
}

# --- Установщики -------------------------------------------------------------

# Одиночный исполняемый файл из репозитория
install_file() { # install_file <имя>
    info "Скачиваю $1…"
    if ! download "$RAW_BASE/$1/$1" "$INSTALL_DIR/$1"; then
        err "не удалось скачать $RAW_BASE/$1/$1"
        return 1
    fi
    chmod 755 "$INSTALL_DIR/$1"
    ok "$1 установлен в $INSTALL_DIR/$1"
}

install_sua() {
    need_cmd python3 || { err "для sua нужен python3."; return 1; }
    install_file sua

    # Зависимость: cryptography
    if python3 -c 'import cryptography' >/dev/null 2>&1; then
        ok "python3-cryptography уже установлен"
    else
        info "Ставлю python-зависимость cryptography…"
        if python3 -m pip install --user -q cryptography 2>/dev/null; then
            ok "cryptography установлена (pip --user)"
        elif python3 -m pip install --user -q --break-system-packages cryptography 2>/dev/null; then
            ok "cryptography установлена (pip --user --break-system-packages)"
        else
            warn "не удалось установить cryptography автоматически."
            warn "поставь вручную: sudo apt install python3-cryptography"
        fi
    fi

    # Зависимость: tkinter (GUI)
    if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
        warn "не найден tkinter — GUI sua не откроется."
        warn "поставь вручную: sudo apt install python3-tk"
    fi
}

install_update() {
    install_file update
    need_cmd python3 || { err "Для update нужен python3."; return 1; }
    if ! need_cmd nano && [ -z "$EDITOR" ]; then
        warn "Не найден nano и не задан EDITOR — задай EDITOR или поставь nano (sudo apt install nano)."
    fi
}

install_pyreq() {
    install_file pyreq
    need_cmd python3 || { err "Для pyreq нужен python3."; return 1; }
}

install_ascii() {
    need_cmd python3 || { err "для ascii нужен python3."; return 1; }
    need_cmd tar     || { err "для ascii нужен tar."; return 1; }

    info "Скачиваю архив репозитория…"
    make_tmp
    if ! download "$ARCHIVE_URL" "$TMP_DIR/repo.tar.gz"; then
        err "не удалось скачать архив $ARCHIVE_URL"
        return 1
    fi
    tar -xzf "$TMP_DIR/repo.tar.gz" -C "$TMP_DIR"

    src=""
    for d in "$TMP_DIR"/*/ascii; do
        [ -d "$d" ] && { src="$d"; break; }
    done
    if [ -z "$src" ]; then
        err "не удалось найти папку ascii в архиве."
        return 1
    fi

    mkdir -p "$APP_DIR"
    rm -rf "$APP_DIR/ascii"
    cp -R "$src" "$APP_DIR/ascii"
    ok "исходники ascii скопированы в $APP_DIR/ascii"

    # Зависимости: лучше venv, иначе pip --user
    PYBIN="python3"
    if python3 -m venv "$APP_DIR/ascii/.venv" >/dev/null 2>&1; then
        info "Ставлю зависимости в venv…"
        if "$APP_DIR/ascii/.venv/bin/pip" install -q -r "$APP_DIR/ascii/requirements.txt"; then
            PYBIN="$APP_DIR/ascii/.venv/bin/python"
            ok "зависимости установлены в venv"
        else
            warn "не удалось установить зависимости в venv, пробую pip --user…"
            rm -rf "$APP_DIR/ascii/.venv"
            python3 -m pip install --user -q -r "$APP_DIR/ascii/requirements.txt" \
                && ok "зависимости установлены (pip --user)" \
                || warn "не удалось установить зависимости — ascii может не запуститься (см. $APP_DIR/ascii/requirements.txt)"
        fi
    else
        info "venv недоступен, ставлю зависимости через pip --user…"
        python3 -m pip install --user -q -r "$APP_DIR/ascii/requirements.txt" \
            && ok "зависимости установлены (pip --user)" \
            || warn "не удалось установить зависимости — возможно, нужен python3-venv или python3-pip"
    fi

    # Лаунчер
    cat > "$INSTALL_DIR/ascii" <<EOF
#!/bin/sh
exec "$PYBIN" "$APP_DIR/ascii/ascii" "\$@"
EOF
    chmod 755 "$INSTALL_DIR/ascii"
    ok "ascii установлен в $INSTALL_DIR/ascii"
}

install_one() {
    case "$1" in
        sua)    install_sua ;;
        update) install_update ;;
        ascii)  install_ascii ;;
        pyreq)  install_pyreq ;;
        all)    install_sua; install_update; install_ascii; install_pyreq ;;
        *)      err "неизвестная утилита: '$1' (доступны: sua, update, ascii, pyreq, all)"; return 1 ;;
    esac
}

# --- Выбор утилит ------------------------------------------------------------

print_menu() {
    printf "\n%bДоступные утилиты:%b\n" "$C_BOLD" "$C_OFF"
    cat <<'EOF'
  1) sua    — sudo с GUI-окном подтверждения (Python + tkinter + cryptography)
  2) update — удаляет файл и открывает его заново в nano
  3) ascii  — визуализатор структуры директорий и репозиториев (Python)
  4) pyreq  — генерирует requirements.txt из pip list в venv
EOF
}

# Читаем ответ из /dev/tty, если он доступен (важно для «curl … | sh»),
# иначе из stdin.
read_reply() {
    if ( : < /dev/tty ) 2>/dev/null; then
        read -r REPLY < /dev/tty
    else
        read -r REPLY
    fi
}

pick_interactive() {
    print_menu
    printf "\nЧто установить? Номера через пробел/запятую (напр.: 1 3), 'all' — всё, 'q' — выход:\n> "
    read_reply || { echo; return 1; }
    # запятые → пробелы
    REPLY=$(printf '%s' "$REPLY" | tr ',' ' ')
    set -- $REPLY
    [ $# -eq 0 ] && { warn "ничего не выбрано"; exit 0; }

    selected=""
    for tok in "$@"; do
        case "$tok" in
            1) name=sua ;;
            2) name=update ;;
            3) name=ascii ;;
            4) name=pyreq ;;
            sua|update|ascii|pyreq|all) name=$tok ;;
            q|quit|exit) info "Выход."; exit 0 ;;
            *) err "непонятный выбор: '$tok'"; exit 1 ;;
        esac
        selected="$selected $name"
    done

    failed=0
    for name in $selected; do
        install_one "$name" || failed=1
    done
    return $failed
}

# --- main --------------------------------------------------------------------

usage() {
    cat <<EOF
Использование:
  $0 [утилиты...]

Примеры:
  $0                 интерактивное меню
  $0 all             установить все утилиты
  $0 sua pyreq       установить только указанные

Через curl:
  curl -fsSL https://raw.githubusercontent.com/$REPO/$BRANCH/install.sh | sh
  curl -fsSL https://raw.githubusercontent.com/$REPO/$BRANCH/install.sh | sh -s -- sua ascii

Переменные: INSTALL_DIR ($INSTALL_DIR), APP_DIR ($APP_DIR), BRANCH ($BRANCH)
EOF
}

for arg in "$@"; do
    case "$arg" in
        -h|--help) usage; exit 0 ;;
    esac
done

ensure_dirs

if [ $# -gt 0 ]; then
    failed=0
    for arg in "$@"; do
        install_one "$arg" || failed=1
    done
    [ "$failed" -eq 0 ] || exit 1
else
    pick_interactive
fi

# Добавление INSTALL_DIR в PATH (автоматически для bash/zsh/sh/fish)

# Добавляет строку в rc-файл, если такой строки ещё нет
add_path_line() { # add_path_line <путь к файлу> <строка>
    [ -f "$1" ] || return 1
    if ! grep -qsF "$2" "$1"; then
        printf '\n# >>> terminal-utils PATH >>>\n%s\n# <<< terminal-utils PATH <<<\n' "$2" >> "$1"
        ok "$1: добавлено '$2'"
        return 0
    fi
    return 1
}

setup_path() {
    case ":$PATH:" in
        *":$INSTALL_DIR:"*) ok "INSTALL_DIR уже в PATH"; return 0 ;;
    esac

    added=0

    # fish: fish_add_path пишет в universal variables, rc-файл не нужен
    if need_cmd fish; then
        if fish -c "fish_add_path -U '$INSTALL_DIR'" >/dev/null 2>&1; then
            ok "fish: '$INSTALL_DIR' добавлен в PATH (universal)"
            added=1
        else
            warn "Не удалось выполнить fish_add_path — добавь вручную: fish_add_path '$INSTALL_DIR'"
        fi
    fi

    # bash / zsh / sh-совместимые rc-файлы
    PATH_LINE="export PATH=\"$INSTALL_DIR:\$PATH\""
    add_path_line "$HOME/.bashrc"  "$PATH_LINE" && added=1
    add_path_line "$HOME/.zshrc"   "$PATH_LINE" && added=1
    add_path_line "$HOME/.profile" "$PATH_LINE" && added=1

    # Ни одного rc-файла нет — создаём ~/.profile
    if [ "$added" -eq 0 ] && ! need_cmd fish; then
        printf 'export PATH="%s:$PATH"\n' "$INSTALL_DIR" > "$HOME/.profile"
        ok "Создан $HOME/.profile с PATH"
        added=1
    fi

    if [ "$added" -eq 1 ]; then
        warn "Открой новое окно терминала или выполни: source ~/.bashrc (или zshrc/profile) — чтобы PATH применился."
    fi
}

setup_path

printf "\n%bГотово!%b Утилиты вызываются по имени (sua, update, ascii, pyreq).\n" "$C_GREEN" "$C_OFF"
