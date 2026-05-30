import sys
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
from rich.text import Text
from rich import box
from typing import Optional, List
import time

class ProgressUI:
    """
    Менеджер интерфейса с прогресс-баром внизу и областью логов сверху.
    При тихом режиме (silent=True) ничего не выводит, кроме сообщений об ошибках.
    """
    def __init__(self, silent: bool = False):
        self.silent = silent
        self.console = Console(stderr=True) if silent else Console()
        self.logs: List[str] = []
        self.layout = None
        self.live = None
        self.progress = None
        self.task_id = None
        self._last_update = 0

        if not silent:
            self._setup_ui()

    def _setup_ui(self):
        """Инициализация rich-компонентов."""
        self.layout = Layout()
        self.layout.split_column(
            Layout(name="logs", ratio=4),
            Layout(name="progress", ratio=1)
        )

        # Прогресс
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console,
            transient=False
        )
        self.task_id = self.progress.add_task("Ожидание...", total=100)

        # Панель логов
        self._update_logs_panel()

        # Запускаем Live
        self.live = Live(self.layout, console=self.console, refresh_per_second=10, screen=False, transient=False)
        self.live.start()

    def _refresh(self):
        """Принудительное обновление интерфейса."""
        if self.live:
            self.live.refresh()

    def _update_logs_panel(self):
        """Обновляет верхнюю панель с логами."""
        if self.silent:
            return
        # Последние 20 строк для лучшей видимости
        recent_logs = self.logs[-20:] if len(self.logs) > 20 else self.logs
        content = "\n".join(recent_logs)
        panel = Panel(
            Text(content, overflow="fold"),
            title=" Логи ",
            border_style="blue",
            box=box.ROUNDED,
            height=15
        )
        self.layout["logs"].update(panel)

    def log(self, message: str, error: bool = False):
        """Добавляет сообщение в лог."""
        if self.silent:
            if error:
                print(message, file=sys.stderr)
        else:
            self.logs.append(message)
            self._update_logs_panel()
            self._refresh()

    def update_progress(self, description: str, progress: float):
        """Обновляет состояние прогресс-бара."""
        if self.silent:
            return
        self.progress.update(self.task_id, description=description, completed=progress)
        self.layout["progress"].update(self.progress)
        self._refresh()

    def finish_progress(self, description: str = "Готово"):
        """Завершает прогресс и останавливает Live."""
        if self.silent:
            return
        self.progress.update(self.task_id, description=description, completed=100)
        self.layout["progress"].update(self.progress)
        time.sleep(0.5)
        if self.live:
            self.live.stop()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if not self.silent and self.live:
            self.live.stop()
