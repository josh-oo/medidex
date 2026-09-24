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
    log_queue = queue.Queue(-1)

    # Handler used by application threads (non-blocking enqueue)
    queue_handler = QueueHandler(log_queue)

    # Handler used by background listener (blocking I/O)
    log_path = os.path.join(DATABASE_VOLUME, "logs", log_path)
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(JsonFormatter())

    listener = QueueListener(log_queue, file_handler)
    listener.start()

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(queue_handler)

    # Ensure logs are flushed on shutdown
    atexit.register(listener.stop)
