import asyncio
import aiohttp
from typing import List, Dict, Optional
from config import PROGRESS_UPDATE_STEP
from utils import is_text_file

BITBUCKET_API_BASE = "https://api.bitbucket.org/2.0"
HEADERS = {"Accept": "application/json"}
try:
    import os
    token = os.environ.get("BITBUCKET_TOKEN")
    if token:
        HEADERS["Authorization"] = f"Bearer {token}"
except:
    pass


def parse_bitbucket_url(url: str) -> tuple[Optional[str], Optional[str], str, str]:
    """Поддерживает https://bitbucket.org/workspace/repo/src/branch/path"""
    url = url.rstrip("/")
    branch = "main"
    path = ""
    if "/src/" in url:
        base, rest = url.split("/src/", 1)
        parts = rest.split("/", 1)
        branch = parts[0]
        if len(parts) > 1:
            path = parts[1]
    else:
        base = url
    # Из base убираем https://bitbucket.org/
    base = base.replace("https://bitbucket.org/", "")
    parts = base.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1], path, branch
    return None, None, "", ""


async def fetch_paginated(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore) -> List[dict]:
    """Загружает все страницы для Bitbucket API."""
    results = []
    while url:
        async with sem:
            async with session.get(url, headers=HEADERS) as resp:
                resp.raise_for_status()
                data = await resp.json()
                results.extend(data.get("values", []))
                url = data.get("next")
    return results


async def get_recursive_tree(session: aiohttp.ClientSession, workspace: str, repo: str, commit: str, path: str, sem: asyncio.Semaphore) -> List[dict]:
    """Рекурсивно загружает всё дерево, обходя папки."""
    all_items = []

    async def walk_dir(current_path: str):
        api_path = current_path.strip("/")
        url = f"{BITBUCKET_API_BASE}/repositories/{workspace}/{repo}/src/{commit}/{api_path}"
        items = await fetch_paginated(session, url, sem)
        for item in items:
            item_type = item.get("type")
            if item_type == "commit_directory":
                # Папка: рекурсивно загружаем
                all_items.append({"path": item["path"], "type": "dir", "size": 0})
                await walk_dir(item["path"])
            elif item_type == "commit_file":
                all_items.append({"path": item["path"], "type": "file", "size": item.get("size", 0)})
        # links: могут быть подпапки, но мы уже прошли

    await walk_dir(path if path else "")
    return all_items


def build_ascii_tree_bitbucket(items: list) -> List[str]:
    # items: dict с path, type, size; type: dir/file
    tree = {}
    for it in items:
        parts = it["path"].split("/")
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                current[part] = {"__type": "dir" if it["type"] == "dir" else "file", "__size": it.get("size", 0), "__children": {}}
            else:
                if part not in current:
                    current[part] = {"__type": "dir", "__size": 0, "__children": {}}
                current = current[part]["__children"]

    def _walk(d, prefix, is_last):
        lines = []
        items_sorted = sorted(d.items(), key=lambda x: (x[1]["__type"] != "dir", x[0].lower()))
        for idx, (name, info) in enumerate(items_sorted):
            connector = "└── " if idx == len(items_sorted)-1 else "├── "
            line = prefix + connector + name
            if info["__type"] == "dir":
                line += "/"
                lines.append(line)
                new_prefix = prefix + ("    " if idx == len(items_sorted)-1 else "│   ")
                lines.extend(_walk(info["__children"], new_prefix, idx == len(items_sorted)-1))
            else:
                lines.append(line)
        return lines

    return _walk(tree, "", True)


async def process_bitbucket(
    workspace: str,
    repo: str,
    path: str,
    branch: str,
    empty_mode: bool,
    ui,
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore
) -> str:
    ui.log(f"🌐 Загрузка дерева {workspace}/{repo} (ветка {branch})...")
    items = await get_recursive_tree(session, workspace, repo, branch, path, sem)
    if not items:
        ui.log(f"❌ Путь '{path}' не содержит файлов")
        return ""

    if empty_mode:
        empty_files = [it["path"] for it in items if it["type"] == "file" and it.get("size", -1) == 0]
        if not empty_files:
            ui.log("ℹ️ Пустые файлы не найдены.")
            return ""
        lines = [f"📄 Пустые файлы (размер 0) в {workspace}/{repo}:"]
        for f in sorted(empty_files):
            lines.append(f"  - {f}")
        ui.log(f"✓ Найдено {len(empty_files)} пустых файлов")
        return "\n".join(lines)

    ui.log("📁 Построение дерева...")
    ascii_lines = build_ascii_tree_bitbucket(items)
    result = [f"📁 Структура репозитория {workspace}/{repo} (ветка {branch}):"]
    result.append(f"{repo}/")
    result.extend(ascii_lines)

    text_files = [it for it in items if it["type"] == "file" and is_text_file(it["path"])]
    if not text_files:
        result.append("\nℹ️ Текстовые файлы не найдены.")
        return "\n".join(result)

    ui.log(f"📄 Загрузка содержимого {len(text_files)} текстовых файлов...")
    total = len(text_files)
    contents = {}

    async def fetch_content(fitem):
        file_path = fitem["path"]
        url = f"{BITBUCKET_API_BASE}/repositories/{workspace}/{repo}/src/{branch}/{file_path}"
        try:
            async with sem:
                async with session.get(url, headers=HEADERS) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        return file_path, text
                    else:
                        return file_path, f"[Ошибка загрузки: {resp.status}]"
        except Exception as e:
            return file_path, f"[Ошибка: {e}]"

    tasks = [asyncio.create_task(fetch_content(f)) for f in text_files]
    completed = 0
    for coro in asyncio.as_completed(tasks):
        p, c = await coro
        contents[p] = c
        completed += 1
        ui.update_progress(f"Загрузка файлов {completed}/{total}", (completed / total) * 100)

    ui.log(f"✓ Загружено {len(contents)} файлов")
    result.append("\n📄 Содержимое текстовых файлов:")
    for fp in sorted(contents.keys()):
        result.append(f"\nкод {fp}")
        result.append(content_trunc(contents[fp]))
    return "\n".join(result)

def content_trunc(content: str, max_len: int = 10000) -> str:
    if len(content) <= max_len:
        return content
    return content[:max_len] + f"\n\n... [файл обрезан, всего {len(content)} символов] ..."
