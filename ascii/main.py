#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path
import aiohttp
from config import DEFAULT_OUTPUT_DIR, IGNORED_DIRS, PROGRESS_UPDATE_STEP
from local import process_local
from ui import ProgressUI
from utils import detect_platform
from github import parse_github_url, process_github
from gitlab import parse_gitlab_url, process_gitlab
from bitbucket import parse_bitbucket_url, process_bitbucket
from sourceforge import parse_sourceforge_url, process_sourceforge

async def async_main():
    from cli import parse_args
    args, path = parse_args()

    if not path and not getattr(args, 'pwd', False):
        print("Введите путь к локальной папке или URL репозитория")
        print("Поддерживаются: GitHub, GitLab, Bitbucket, SourceForge")
        print("Примеры:")
        print("  - Локальный: /home/user/projects")
        print("  - GitHub:    https://github.com/user/repo")
        print("  - GitLab:    https://gitlab.com/user/repo")
        print("  - Bitbucket: https://bitbucket.org/workspace/repo")
        print("  - SourceForge: https://sourceforge.net/p/project/repo/ci/main/tree/")
        path = input("Введите путь или URL: ").strip()

    if getattr(args, 'pwd', False):
        path = os.getcwd()

    # Определяем выходной файл
    if args.output:
        output_file = args.output
    else:
        suffix = "_empty" if args.empty else ""
        output_file = os.path.join(DEFAULT_OUTPUT_DIR, f"output{suffix}.txt")

    ui = ProgressUI(silent=args.silent)
    include_hidden = getattr(args, 'include_hidden', False)
    max_concurrent = getattr(args, 'max_concurrent', 16)

    platform = detect_platform(path) if path.startswith(('http://', 'https://')) else "local"
    result = ""

    if platform == "local":
        result = process_local(path, args.empty, ui, include_hidden=include_hidden)
    else:
        sem = asyncio.Semaphore(max_concurrent)
        async with aiohttp.ClientSession() as session:
            try:
                if platform == "github":
                    owner, repo, subpath, branch = parse_github_url(path)
                    if not owner:
                        ui.log("❌ Некорректный URL GitHub", error=True)
                        return
                    result = await process_github(owner, repo, subpath, branch, args.empty, ui, session, sem)
                elif platform == "gitlab":
                    owner, repo, subpath, branch = parse_gitlab_url(path)
                    if not owner:
                        ui.log("❌ Некорректный URL GitLab", error=True)
                        return
                    result = await process_gitlab(owner, repo, subpath, branch, args.empty, ui, session, sem)
                elif platform == "bitbucket":
                    workspace, repo, subpath, branch = parse_bitbucket_url(path)
                    if not workspace:
                        ui.log("❌ Некорректный URL Bitbucket", error=True)
                        return
                    result = await process_bitbucket(workspace, repo, subpath, branch, args.empty, ui, session, sem)
                elif platform == "sourceforge":
                    project, repo, subpath, branch = parse_sourceforge_url(path)
                    if not project:
                        ui.log("❌ Некорректный URL SourceForge", error=True)
                        return
                    result = await process_sourceforge(project, repo, subpath, branch, args.empty, ui, session, sem)
            except Exception as e:
                ui.log(f"❌ Ошибка: {e}", error=True)
                result = ""

    ui.finish_progress()

    if result:
        if not args.silent:
            print(result)
        save_to_file(result, output_file)
        print(f"\n✅ Результат сохранён в: {output_file}")
    else:
        ui.log("❌ Нет данных для сохранения.", error=True)

def save_to_file(content: str, filepath: str):
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"❌ Ошибка при сохранении: {e}")

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
