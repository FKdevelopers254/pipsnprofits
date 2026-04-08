import logging
import os
from logging import Handler, Formatter
from datetime import datetime
from zoneinfo import ZoneInfo

LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
TARGET_TZ = ZoneInfo("Europe/Athens")


class DailyRotatingFileHandler(Handler):
    """
    Very small rolling file handler that rotates by date using the TARGET_TZ (Europe/Athens).
    Keeps one file opened per process.
    """
    def __init__(self):
        super().__init__()
        self.current_date = None
        self.file_handler = None
        self.setFormatter(Formatter(
            '%(asctime)s - %(levelname)s - %(module)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S%z'
        ))

    def _get_file_name(self):
        now = datetime.now(TARGET_TZ)
        return os.path.join(LOG_DIR, f"{now.strftime('%Y-%m-%d')}.log")

    def emit(self, record):
        try:
            current_date = datetime.now(TARGET_TZ).date()
            if current_date != self.current_date:
                self._close_file()
                self.current_date = current_date
                filename = self._get_file_name()
                self.file_handler = open(filename, "a", encoding="utf-8")

            msg = self.format(record)
            if self.file_handler:
                self.file_handler.write(msg + "\n")
                self.file_handler.flush()
        except Exception:
            # Logging must not raise
            try:
                logging.getLogger(__name__).exception("Failed writing log")
            except Exception:
                pass

    def _close_file(self):
        if self.file_handler:
            try:
                self.file_handler.close()
            except Exception:
                pass
            self.file_handler = None

    def close(self):
        self._close_file()
        super().close()


def setup_logging(level: str = "INFO"):
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    for h in list(root.handlers):
        root.removeHandler(h)

    file_handler = DailyRotatingFileHandler()
    file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s'))
    root.addHandler(console)

    logging.getLogger(__name__).info("Logging initialized (level=%s)", level)
