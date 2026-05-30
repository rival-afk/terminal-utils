import argparse
import sys
import os

def parse_args() -> tuple[argparse.Namespace, str]:
    """Парсит аргументы командной строки и запрашивает путь интерактивно, если не указан."""
    parser = argparse.ArgumentParser(description="Визуализатор структуры директорий и поиск пустых файлов")
    parser.add_argument('-e', '--empty', action='store_true', help="Вывести только пустые файлы (размер 0)")
    parser.add_argument('-s', '--silent', action='store_true', help="Тихий режим (без прогресс-бара, результат только в файл)")
    parser.add_argument('-p', '--pwd', action='store_true', help="Использовать текущую директорию как путь")
    parser.add_argument('-o', '--output', type=str, help="Путь для сохранения результата (по умолчанию ~/projects/outputs/output.txt)")
    parser.add_argument('--include-hidden', action='store_true', help="Показывать скрытые файлы и папки (начинающиеся с точки)")
    parser.add_argument('--max-concurrent', type=int, default=16, help="Максимальное количество одновременных запросов для удалённых платформ")
    parser.add_argument('path', nargs='?', help="Путь к локальной папке или URL GitHub/GitLab/Bitbucket/SourceForge")
    args = parser.parse_args()

    # Если указан флаг --pwd, путь не нужен
    if args.pwd:
        return args, ""

    # Если путь не передан в аргументах, запрашиваем интерактивно
    if not args.path:
        return args, ""

    return args, args.path
