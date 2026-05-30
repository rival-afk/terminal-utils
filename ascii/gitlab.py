import asyncio
import aiohttp
from typing import List, Optional, Callable
from config import PROGRESS_UPDATE_STEP
from utils import is_text_file

GITLAB_API_BASE = "https://gitlab.com/api/v4"
HEADERS = {}
try:
    import os
    token = os.environ.get("GITLAB_TOKEN")
    if token:
        HEADERS["PRIVATE-TOKEN"] = token
except:
    pass


def parse_gitlab_url(url: str) -> tuple[Optional[str], Optional[str], str, str]:
    """Пример: https://gitlab.com/owner/repo/-/tree/branch/path"""
    url = url.rstrip("/")
    branch = "main"
    path = ""
    # Находим /-/tree/ или /-/blob/
    if "/-/tree/" in url:
        base, rest = url.split("/-/tree/", 1)
    elif "/-/blob/" in url:
        base, rest = url.split("/-/blob/", 1)
    else:
        base = url
        rest = ""
    if rest:
        parts = rest.split("/", 1)
        branch = parts[0]
        if len(parts) > 1:
            path = parts[1]
    # Из base извлекаем owner/repo
    base = base.replace("https://gitlab.com/", "")
    parts = base.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1], path, branch
    return None, None, "", ""


async def get_project_id(session: aiohttp.ClientSession, owner: str, repo: str, sem: asyncio.Semaphore) -> int:
    url = f"{GITLAB_API_BASE}/projects/{owner}%2F{repo}"
    async with sem:
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status == 404:
                raise ValueError(f"Проект {owner}/{repo} не найден на GitLab")
            resp.raise_for_status()
            data = await resp.json()
            return data["id"]


async def get_recursive_tree(session: aiohttp.ClientSession, project_id: int, branch: str, path: str, sem: asyncio.Semaphore) -> List[dict]:
    """Получает полное рекурсивное дерево для заданного пути."""
    per_page = 100
    page = 1
    all_items = []
    while True:
        params = {
            "ref": branch,
            "recursive": "true",
            "per_page": per_page,
            "page": page,
            "path": path if path else None
        }
        url = f"{GITLAB_API_BASE}/projects/{project_id}/repository/tree"
        async with sem:
            async with session.get(url, headers=HEADERS, params=params) as resp:
                if resp.status == 404:
                    # Если путь не найден, прерываем
                    return []
                resp.raise_for_status()
                items = await resp.json()
                if not items:
                    break
                all_items.extend(items)
                page += 1
    return all_items


def build_ascii_tree_gitlab(items: list, root_name: str = "") -> List[str]:
    """Строит дерево из плоского списка элементов GitLab API."""
    # Элементы: {path, type: 'tree'/'blob', size: ...} – size может отсутствовать
    tree = {}
    for item in items:
        parts = item['path'].split('/')
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                current[part] = {"__type": item['type'], "__size": item.get('size', 0), "__children": {}}
            else:
                if part not in current:
                    current[part] = {"__type": "tree", "__size": 0, "__children": {}}
                current = current[part]["__children"]

    def _walk(d, prefix, is_last):
        lines = []
        items_sorted = sorted(d.items(), key=lambda x: (x[1]["__type"] != "tree", x[0].lower()))
        for idx, (name, info) in enumerate(items_sorted):
            connector = "└── " if idx == len(items_sorted) - 1 else "├── "
            line = prefix + connector + name
            if info["__type"] == "tree":
                line += "/"
                lines.append(line)
                new_prefix = prefix + ("    " if idx == len(items_sorted) - 1 else "│   ")
                lines.extend(_walk(info["__children"], new_prefix, idx == len(items_sorted)-1))
            else:
                lines.append(line)
        return lines

    return _walk(tree, "", True)


async def process_gitlab(
    owner: str,
    repo: str,
    path: str,
    branch: str,
    empty_mode: bool,
    ui,
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore
) -> str:
    ui.log(f"🌐 Получение ID проекта {owner}/{repo}...")
    project_id = await get_project_id(session, owner, repo, sem)
    ui.log(f"🌐 Загрузка дерева (ветка {branch})...")
    items = await get_recursive_tree(session, project_id, branch, path, sem)
    if not items:
        ui.log(f"❌ Путь '{path}' не содержит файлов или не существует")
        return ""

    if empty_mode:
        empty_files = [it['path'] for it in items if it['type'] == 'blob' and it.get('size', -1) == 0]
        if not empty_files:
            ui.log("ℹ️ Пустые файлы не найдены.")
            return ""
        lines = [f"📄 Пустые файлы (размер 0) в {owner}/{repo}:"]
        for f in sorted(empty_files):
            lines.append(f"  - {f}")
        ui.log(f"✓ Найдено {len(empty_files)} пустых файлов")
        return "\n".join(lines)

    ui.log("📁 Построение дерева...")
    ascii_lines = build_ascii_tree_gitlab(items, repo)
    result = [f"📁 Структура репозитория {owner}/{repo} (ветка {branch}):"]
    result.append(f"{repo}/")
    result.extend(ascii_lines)

    text_blobs = [it for it in items if it['type'] == 'blob' and is_text_file(it['path'])]
    if not text_blobs:
        result.append("\nℹ️ Текстовые файлы не найдены.")
        return "\n".join(result)

    ui.log(f"📄 Загрузка содержимого {len(text_blobs)} текстовых файлов...")
    total = len(text_blobs)
    contents = {}

    async def fetch_content(blob):
        # Формат: /projects/:id/repository/files/:file_path/raw?ref=branch
        # file_path нужно URL-кодировать
        from urllib.parse import quote
        file_path_encoded = quote(blob['path'], safe='')
        url = f"{GITLAB_API_BASE}/projects/{project_id}/repository/files/{file_path_encoded}/raw?ref={branch}"
        try:
            async with sem:
                async with session.get(url, headers=HEADERS) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        return blob['path'], text
                    else:
                        return blob['path'], f"[Ошибка загрузки: {resp.status}]"
        except Exception as e:
            return blob['path'], f"[Ошибка: {e}]"

    tasks = [asyncio.create_task(fetch_content(b)) for b in text_blobs]
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
