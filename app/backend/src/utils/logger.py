import logging
import json
import queue
import atexit
from logging.handlers import QueueHandler, QueueListener

import os

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")

# ---------- JSON Formatter ----------
class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": record.created,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "payload": getattr(record, "payload", None),
        })

# ---------- Logging Setup ----------
def setup_logging(log_path: str):
    root_logger = logging.getLogger()
    # Imported by several modules: set up once, or every line is written as often.
    if any(isinstance(handler, QueueHandler) for handler in root_logger.handlers):
        return

    log_queue = queue.Queue(-1)

    # Handler used by application threads (non-blocking enqueue)
    queue_handler = QueueHandler(log_queue)

    # Handler used by background listener (blocking I/O)
    log_path = os.path.join(DATABASE_VOLUME, "logs", log_path)
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(JsonFormatter())

    # Warnings and errors also go to the console (docker logs), with their traceback (QueueHandler puts it in the
    # message): a failing background task
    # (e.g. the embedding of reports) is seen there, not only in the file of the volume.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))

    listener = QueueListener(log_queue, file_handler, console_handler, respect_handler_level=True)
    listener.start()

    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(queue_handler)

    # Ensure logs are flushed on shutdown
    atexit.register(listener.stop)
