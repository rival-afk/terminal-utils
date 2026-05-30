import os

# Папка для сохранения результатов по умолчанию
DEFAULT_OUTPUT_DIR = os.path.expanduser("~") + "/projects/outputs"

# Расширения текстовых файлов (которые будем показывать)
TEXT_EXTENSIONS = {
    '.md', '.html', '.js', '.json', '.css', '.py', '.txt', '.xml',
    '.yaml', '.yml', '.csv', '.ts', '.jsx', '.tsx', '.vue', '.php',
    '.rb', '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.go', '.rs',
    '.swift', '.kt', '.rst', '.ini', '.cfg', '.conf', '.sh', '.bash',
    '.zsh', '.fish', '.ps1', '.bat', '.cmd', '.sql', '.r', '.m'
}

# Расширения заведомо бинарных файлов (не показываем содержимое)
BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg',
    '.mp4', '.mp3', '.avi', '.mov', '.wav', '.flac', '.ogg',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.rar', '.tar', '.gz', '.7z', '.bz2',
    '.exe', '.dll', '.so', '.dylib', '.bin', '.dat',
    '.deb', '.rpm', '.apk', '.ipa'
}

# Настройки GitHub API
GITHUB_API_BASE = "https://api.github.com"
GITHUB_MAX_CONCURRENT = 16          # одновременных запросов
GITHUB_SLEEP_ON_LIMIT = 60           # секунд при превышении лимита (403)

IGNORED_DIRS = {'.venv', '__pycache__', '.git', '.idea', 'node_modules', '.pytest_cache', '.mypy_cache', '.vscode'}
PROGRESS_UPDATE_STEP = 10
