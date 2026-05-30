import asyncio
import aiohttp
from typing import List, Dict, Optional
from config import PROGRESS_UPDATE_STEP
from utils import is_text_file

SOURCEFORGE_API_BASE = "https://sourceforge.net/rest"
HEADERS = {"Accept": "application/json"}
try:
    import os
    token = os.environ.get("SOURCEFORGE_TOKEN")
    if token:
        HEADERS["Authorization"] = f"Bearer {token}"
except:
    pass

def parse_sourceforge_url(url: str) -> tuple[Optional[str], Optional[str], str, str]:
    """
    Разбирает URL вида https://sourceforge.net/p/project/repo/ci/main/tree/path/
    Проект и репозиторий могут быть с подпроектами, но обычно p/<project>/<repo>
    """
    url = url.rstrip("/")
    # Ожидаем: https://sourceforge.net/p/<project>/<repo>/ci/<branch>/tree/<path>
    # Убираем https://sourceforge.net/p/
    rest = url.replace("https://sourceforge.net/p/", "")
    parts = rest.split("/")
    if len(parts) < 2:
        return None, None, "", ""
    project = parts[0]
    repo = parts[1]
    branch = "main"
    path = ""
    if "ci" in parts:
        ci_idx = parts.index("ci")
        if len(parts) > ci_idx + 1:
            branch = parts[ci_idx+1]
        if "tree" in parts:
            tree_idx = parts.index("tree")
            if tree_idx > ci_idx and len(parts) > tree_idx + 1:
                path = "/".join(parts[tree_idx+1:])
    return project, repo, path, branch


async def fetch_json_sourceforge(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        async with session.get(url, headers=HEADERS) as resp:
            resp.raise_for_status()
            return await resp.json()


async def get_recursive_tree_sf(session: aiohttp.ClientSession, project: str, repo: str, branch: str, path: str, sem: asyncio.Semaphore) -> List[dict]:
    """
    Загружает рекурсивно дерево SourceForge через /rest/p/<project>/<repo>/<branch>/tree/<path>?format=json
    Возвращает плоский список элементов с path, type (folder/file), size (для файлов).
    """
    all_items = []

    async def walk(current_path: str):
        url = f"{SOURCEFORGE_API_BASE}/p/{project}/{repo}/{branch}/tree/{current_path}"
        params = {"format": "json"}
        async with sem:
            async with session.get(url, headers=HEADERS, params=params) as resp:
                if resp.status == 404:
                    return
                resp.raise_for_status()
                data = await resp.json()
        # Ответ: { "name": "...", "type": "folder", "children": [...] } или файл
        # Для папки есть ключ "children"
        if isinstance(data, dict):
            if data.get("type") == "folder" and "children" in data:
                for child in data["children"]:
                    child_type = child.get("type")
                    child_name = child.get("name")
                    child_path = current_path + "/" + child_name if current_path else child_name
                    if child_type == "folder":
                        all_items.append({"path": child_path, "type": "dir", "size": 0})
                        await walk(child_path)
                    else:  # file
                        size = child.get("size", 0)
                        all_items.append({"path": child_path, "type": "file", "size": size})
            elif data.get("type") == "file":
                # Единичный файл на корневом пути
                all_items.append({"path": data["name"], "type": "file", "size": data.get("size", 0)})
        elif isinstance(data, list):
            # Иногда API может вернуть список
            for item in data:
                if item.get("type") == "folder":
                    all_items.append({"path": item["name"], "type": "dir", "size": 0})
                    await walk(item["name"])
                else:
                    all_items.append({"path": item["name"], "type": "file", "size": item.get("size", 0)})

    await walk(path)
    return all_items


def build_ascii_tree_sf(items: list) -> List[str]:
    tree = {}
    for it in items:
        parts = it["path"].split("/")
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                current[part] = {"__type": it["type"], "__size": it.get("size", 0), "__children": {}}
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


async def process_sourceforge(
    project: str,
    repo: str,
    path: str,
    branch: str,
    empty_mode: bool,
    ui,
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore
) -> str:
    ui.log(f"🌐 Загрузка дерева SourceForge {project}/{repo} (ветка {branch})...")
    items = await get_recursive_tree_sf(session, project, repo, branch, path, sem)
    if not items:
        ui.log(f"❌ Путь '{path}' не содержит файлов")
        return ""

    if empty_mode:
        empty_files = [it["path"] for it in items if it["type"] == "file" and it.get("size", -1) == 0]
        if not empty_files:
            ui.log("ℹ️ Пустые файлы не найдены.")
            return ""
        lines = [f"📄 Пустые файлы (размер 0) в {project}/{repo}:"]
        for f in sorted(empty_files):
            lines.append(f"  - {f}")
        ui.log(f"✓ Найдено {len(empty_files)} пустых файлов")
        return "\n".join(lines)

    ui.log("📁 Построение дерева...")
    ascii_lines = build_ascii_tree_sf(items)
    result = [f"📁 Структура репозитория {project}/{repo} (ветка {branch}):"]
    result.append(f"{repo}/")
    result.extend(ascii_lines)

    text_files = [it for it in items if it["type"] == "file" and is_text_file(it["path"])]
    if not text_files:
        result.append("\nℹ️ Текстовые файлы не найдены.")
        return "\n".join(result)

    ui.log(f"📄 Загрузка содержимого {len(text_files)} текстовых файлов...")
    total = len(text_files)
    contents = {}

    async def fetch_content(item):
        file_path = item["path"]
        url = f"{SOURCEFORGE_API_BASE}/p/{project}/{repo}/{branch}/raw/{file_path}"
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
