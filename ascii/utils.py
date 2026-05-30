import os
from config import TEXT_EXTENSIONS, BINARY_EXTENSIONS

def is_text_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    if ext in TEXT_EXTENSIONS:
        return True
    if ext in BINARY_EXTENSIONS:
        return False
    try:
        with open(filename, 'rb') as f:
            chunk = f.read(1024)
            if b'\0' in chunk:
                return False
    except:
        pass
    return True

def truncate_content(content: str, max_len: int = 10000) -> str:
    if len(content) <= max_len:
        return content
    return content[:max_len] + f"\n\n... [файл обрезан, всего {len(content)} символов] ..."

def detect_platform(url: str) -> str:
    """Определяет платформу по URL: github, gitlab, bitbucket, sourceforge, local."""
    if url.startswith("https://github.com"):
        return "github"
    if url.startswith("https://gitlab.com"):
        return "gitlab"
    if url.startswith("https://bitbucket.org"):
        return "bitbucket"
    if url.startswith("https://sourceforge.net"):
        return "sourceforge"
    return "local"
