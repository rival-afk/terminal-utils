import asyncio
import aiohttp
from typing import List, Dict, Optional, Callable
from config import GITHUB_API_BASE, GITHUB_MAX_CONCURRENT, GITHUB_SLEEP_ON_LIMIT
from utils import is_text_file

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}
try:
    import os
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        HEADERS["Authorization"] = f"Bearer {token}"
except:
    pass


def parse_github_url(url: str) -> tuple[Optional[str], Optional[str], str, str]:
    """Разбирает URL GitHub вида https://github.com/owner/repo[/tree/branch[/path]]"""
    url = url.rstrip("/")
    branch = "main"
    path = ""
    if "/tree/" in url:
        base, rest = url.split("/tree/", 1)
        parts = rest.split("/", 1)
        branch = parts[0]
        if len(parts) > 1:
            path = parts[1]
    else:
        base = url
    owner_repo = base.replace("https://github.com/", "").split("/")
    if len(owner_repo) >= 2:
        return owner_repo[0], owner_repo[1], path, branch
    return None, None, "", ""


async def fetch_json(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore) -> dict:
    """Запрос к API GitHub с учётом rate limit."""
    async with sem:
        for attempt in range(3):
            try:
                async with session.get(url, headers=HEADERS) as resp:
                    if resp.status == 403 and "rate limit" in await resp.text():
                        await asyncio.sleep(GITHUB_SLEEP_ON_LIMIT)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except Exception as e:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)


async def get_recursive_tree(session: aiohttp.ClientSession, owner: str, repo: str, branch: str, sem: asyncio.Semaphore) -> dict:
    """Получает полное рекурсивное дерево через Git Trees API."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    return await fetch_json(session, url, sem)


def build_ascii_tree(nodes: list, root_path: str = "") -> List[str]:
    """
    Строит список строк ASCII-дерева из плоского списка узлов Git-дерева.
    nodes: список dict с ключами 'path', 'type' (tree/blob), 'size' (может быть !=0).
    """
    # Фильтруем только те, что начинаются с root_path (если задан)
    if root_path:
        root_path = root_path.strip("/")
        if root_path:
            prefix_len = len(root_path) + 1
            nodes = [n for n in nodes if n['path'].startswith(root_path + "/") or n['path'] == root_path]
            # обрезаем root_path из начала пути
            for n in nodes:
                n['path'] = n['path'][prefix_len:] if n['path'] != root_path else "."
    else:
        prefix_len = 0

    # Строим дерево из оставшихся путей
    tree = {}
    for n in nodes:
        parts = n['path'].split("/")
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # Лист или папка (tree)
                current[part] = {"__type": n['type'], "__size": n.get('size', 0), "__children": {}}
            else:
                if part not in current:
                    current[part] = {"__type": "tree", "__size": 0, "__children": {}}
                current = current[part]["__children"]

    def _walk(d: dict, prefix: str, is_last: bool) -> List[str]:
        lines = []
        items = sorted(d.items(), key=lambda x: (x[1]["__type"] != "tree", x[0].lower()))
        for idx, (name, info) in enumerate(items):
            connector = "└── " if idx == len(items) - 1 else "├── "
            line = prefix + connector + name
            if info["__type"] == "tree":
                line += "/"
                lines.append(line)
                new_prefix = prefix + ("    " if idx == len(items) - 1 else "│   ")
                lines.extend(_walk(info["__children"], new_prefix, idx == len(items) - 1))
            else:
                lines.append(line)
        return lines

    return _walk(tree, "", True)


async def process_github(
    owner: str,
    repo: str,
    path: str,
    branch: str,
    empty_mode: bool,
    ui,
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore
) -> str:
    """Основная функция обработки GitHub репозитория."""
    ui.log(f"🌐 Загрузка дерева репозитория {owner}/{repo} (ветка {branch})...")
    tree_data = await get_recursive_tree(session, owner, repo, branch, sem)
    if "tree" not in tree_data:
        raise ValueError("Не удалось получить дерево репозитория")

    nodes = tree_data["tree"]
    # Фильтруем по нужному пути, если задан
    if path:
        path_norm = path.strip("/")
        nodes = [n for n in nodes if n['path'].startswith(path_norm + "/") or n['path'] == path_norm]
        if not nodes:
            ui.log(f"❌ Путь '{path}' не найден в репозитории")
            return ""

    if empty_mode:
        # Только пустые файлы (size == 0)
        empty_files = [n['path'] for n in nodes if n['type'] == 'blob' and n.get('size', -1) == 0]
        if not empty_files:
            ui.log("ℹ️ Пустые файлы не найдены.")
            return ""
        lines = [f"📄 Пустые файлы (размер 0) в {owner}/{repo}:"]
        for f in sorted(empty_files):
            lines.append(f"  - {f}")
        ui.log(f"✓ Найдено {len(empty_files)} пустых файлов")
        return "\n".join(lines)

    # Обычный режим: ASCII-дерево + содержимое текстовых файлов
    ui.log("📁 Построение дерева...")
    ascii_lines = build_ascii_tree(nodes, path)
    result = [f"📁 Структура репозитория {owner}/{repo} (ветка {branch}):"]
    result.append(f"{repo}/")
    result.extend(ascii_lines)

    # Собираем текстовые файлы (blob) для загрузки содержимого
    text_blobs = [n for n in nodes if n['type'] == 'blob' and is_text_file(n['path'])]
    if not text_blobs:
        result.append("\nℹ️ Текстовые файлы не найдены.")
        return "\n".join(result)

    ui.log(f"📄 Загрузка содержимого {len(text_blobs)} текстовых файлов...")
    total = len(text_blobs)
    contents = {}
    # Готовим задачи с семафором
    async def fetch_content(blob):
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{blob['path']}?ref={branch}"
        try:
            data = await fetch_json(session, url, sem)
            # GitHub возвращает содержимое в base64
            import base64
            content = base64.b64decode(data['content']).decode('utf-8', errors='replace')
            return blob['path'], content
        except UnicodeDecodeError:
            # бинарный, но мы уже отфильтровали, на всякий случай
            return blob['path'], "[Не удалось декодировать]"
        except Exception as e:
            return blob['path'], f"[Ошибка загрузки: {e}]"

    tasks = [asyncio.create_task(fetch_content(blob)) for blob in text_blobs]
    completed_count = 0
    for coro in asyncio.as_completed(tasks):
        path_, content_ = await coro
        contents[path_] = content_
        completed_count += 1
        ui.update_progress(f"Загрузка файлов {completed_count}/{total}", (completed_count / total) * 100)

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
