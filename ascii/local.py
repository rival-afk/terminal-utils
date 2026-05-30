import os
from utils import is_text_file
from config import IGNORED_DIRS, PROGRESS_UPDATE_STEP

def get_directory_structure(root_dir: str, prefix: str = "", include_hidden: bool = False, ui=None) -> list[str]:
    """Рекурсивно строит ASCII-дерево локальной директории."""
    result = []
    try:
        items = []
        for name in os.listdir(root_dir):
            path = os.path.join(root_dir, name)
            # Пропуск скрытых папок, если не задан include_hidden
            if not include_hidden and name.startswith('.') and os.path.isdir(path):
                continue
            if os.path.isdir(path):
                items.append((name, 'dir', path))
            else:
                if not include_hidden and name.startswith('.'):
                    continue
                items.append((name, 'file', path))

        items.sort(key=lambda x: (x[1] != 'dir', x[0].lower()))

        for i, (name, typ, path) in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            if typ == 'dir':
                if name in IGNORED_DIRS and not include_hidden:
                    result.append(prefix + connector + name + "/ [пропущено]")
                else:
                    result.append(prefix + connector + name + "/")
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    result.extend(get_directory_structure(path, new_prefix, include_hidden, ui))
            else:
                result.append(prefix + connector + name)
    except PermissionError:
        result.append(prefix + "└── [Доступ запрещен]")
    except Exception as e:
        result.append(prefix + f"└── [Ошибка: {e}]")

    if ui:
        ui.log(f"✓ Построено дерево директории: {os.path.basename(root_dir)}")
    return result


def get_file_content(filepath: str) -> str:
    """Читает содержимое текстового файла (пробует utf-8, затем cp1251)."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, 'r', encoding='cp1251') as f:
                return f.read()
        except:
            return "[Не удалось прочитать файл - бинарный или неизвестная кодировка]"
    except Exception as e:
        return f"[Ошибка чтения файла: {e}]"


def find_empty_files_local(root_dir: str, include_hidden: bool = False, ui=None) -> list[str]:
    """Ищет пустые файлы (размер 0) рекурсивно, возвращает относительные пути."""
    empty = []
    count = 0
    for root, dirs, files in os.walk(root_dir):
        if not include_hidden:
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith('.')]
        else:
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]  # всё равно исключаем стандартные игнорируемые
        for f in files:
            if not include_hidden and f.startswith('.'):
                continue
            path = os.path.join(root, f)
            try:
                if os.path.getsize(path) == 0:
                    rel = os.path.relpath(path, root_dir)
                    empty.append(rel)
                    count += 1
                    if ui and count % 100 == 0:
                        ui.log(f"🔍 Найдено пустых файлов: {count}")
            except OSError:
                pass
    if ui:
        ui.log(f"✓ Поиск пустых файлов завершён, найдено: {len(empty)}")
    return empty


def process_local(path: str, empty_mode: bool, ui, include_hidden: bool = False) -> str:
    """Обрабатывает локальную директорию: строит дерево или ищет пустые файлы, возвращает строку результата."""
    # Разворачиваем путь
    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    ui.log(f"📁 Обработка директории: {path}")

    if not os.path.exists(path):
        ui.log("❌ Указанный путь не существует!", error=True)
        return ""
    if not os.path.isdir(path):
        ui.log("❌ Указанный путь не является директорией!", error=True)
        return ""

    if empty_mode:
        ui.log("🔍 Поиск пустых файлов...")
        empty_files = find_empty_files_local(path, include_hidden, ui)
        if not empty_files:
            ui.log("ℹ️ Пустые файлы не найдены.")
            return ""
        lines = [f"📄 Пустые файлы (размер 0) в {path}:"]
        lines.extend(f"  - {f}" for f in empty_files)
        ui.log(f"✓ Найдено {len(empty_files)} пустых файлов")
        return "\n".join(lines)
    else:
        ui.log("📁 Построение дерева...")
        structure = get_directory_structure(path, include_hidden=include_hidden, ui=ui)
        result_lines = [f"📁 Структура директории {path}:"]
        dir_name = os.path.basename(path) or path
        result_lines.append(dir_name + "/")
        result_lines.extend(structure)
        ui.log(f"✓ Дерево построено, {len(structure)} элементов")

        # Собираем текстовые файлы
        ui.log("📄 Сбор текстовых файлов...")
        text_files = []
        for root, dirs, files in os.walk(path):
            if not include_hidden:
                dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith('.')]
            else:
                dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for f in files:
                if not include_hidden and f.startswith('.'):
                    continue
                if is_text_file(f):
                    text_files.append(os.path.join(root, f))

        ui.log(f"✓ Найдено {len(text_files)} текстовых файлов")

        if text_files:
            result_lines.append("\n📄 Содержимое текстовых файлов:")
            total = len(text_files)
            for i, fp in enumerate(text_files):
                if i % PROGRESS_UPDATE_STEP == 0:
                    ui.update_progress(f"Чтение файлов... {i+1}/{total}", (i+1)/total*100)
                content = get_file_content(fp)
                rel_path = os.path.relpath(fp, path)
                result_lines.append(f"\nкод {rel_path}")
                from utils import truncate_content
                result_lines.append(truncate_content(content))
            ui.log(f"✓ Прочитано {total} файлов")
        else:
            result_lines.append("\nℹ️ Текстовые файлы не найдены.")

        return "\n".join(result_lines)
