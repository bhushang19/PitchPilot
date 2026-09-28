"""Per-run logging: a run logger that writes to ``run.log`` and (optionally) Table.

Every run gets its own logger that fans out to:
  * a per-run ``run.log`` file in the run folder (always), and
  * a buffered Table handler that batch-writes records to Azure Table Storage when
    storage is enabled.

Verbosity is controlled by ``LOG_LEVEL`` (``config.log_level``). The core modules
just call ``logging.getLogger(__name__)``; attaching a run logger here routes those
records — via the root logger — into the per-run destinations for the duration of a
run, then detaches cleanly. The run folder only exists after exploration creates it,
so early records are buffered and replayed into ``run.log`` on
:meth:`RunLogger.bind_run_dir`.
"""

from __future__ import annotations

import logging
import logging.handlers
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import storage
from core.storage import StorageContext

_RUN_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(pp_stage)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


class _StageFilter(logging.Filter):
    """Injects the current run stage onto every record (mutated live by the worker)."""

    def __init__(self) -> None:
        super().__init__()
        self.stage = "queued"

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "pp_stage"):
            record.pp_stage = self.stage
        return True


class TableLogHandler(logging.Handler):
    """Buffers log records and batch-flushes them to Azure Table Storage."""

    def __init__(self, ctx: StorageContext, job_id: str, flush_threshold: int = 25) -> None:
        super().__init__()
        self._ctx = ctx
        self._job_id = job_id
        self._flush_threshold = flush_threshold
        self._buffer: list[dict[str, Any]] = []
        self._seq = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            with self._lock:
                self._seq += 1
                self._buffer.append(
                    {
                        "seq": self._seq,
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "level": record.levelname,
                        "logger": record.name,
                        "stage": getattr(record, "pp_stage", ""),
                        "message": record.getMessage(),
                    }
                )
                ready = len(self._buffer) >= self._flush_threshold
            if ready:
                self.flush()
        except Exception:  # never let logging raise into the app
            pass

    def flush(self) -> None:
        with self._lock:
            pending, self._buffer = self._buffer, []
        if pending:
            storage.write_log_batch(self._ctx, self._job_id, pending)


class RunLogger:
    """A run-scoped logging handle. Attach at run start, detach when the run settles."""

    def __init__(
        self,
        logger: logging.Logger,
        stage_filter: _StageFilter,
        formatter: logging.Formatter,
        level: int,
        memory_handler: logging.handlers.MemoryHandler,
        extra_handlers: list[logging.Handler],
    ) -> None:
        self._logger = logger
        self._stage_filter = stage_filter
        self._formatter = formatter
        self._level = level
        self._memory_handler = memory_handler
        self._file_handler: logging.Handler | None = None
        self._handlers: list[logging.Handler] = [memory_handler, *extra_handlers]

    def set_stage(self, stage: str) -> None:
        self._stage_filter.stage = stage

    def bind_run_dir(self, run_dir: str) -> None:
        """Create the per-run file handler and replay buffered records into it."""
        if self._file_handler is not None:
            return
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(Path(run_dir) / "run.log"), encoding="utf-8")
        file_handler.setLevel(self._level)
        file_handler.setFormatter(self._formatter)
        file_handler.addFilter(self._stage_filter)
        self._file_handler = file_handler
        root = logging.getLogger()
        # Live records now go to the file handler; the buffer only replays pre-bind records.
        root.addHandler(file_handler)
        self._handlers.append(file_handler)
        self._memory_handler.setTarget(file_handler)
        self._memory_handler.flush()
        root.removeHandler(self._memory_handler)
        self._handlers.remove(self._memory_handler)
        try:
            self._memory_handler.close()
        except Exception:
            pass

    def log(self, message: str, level: int = logging.INFO) -> None:
        self._logger.log(level, message)

    def info(self, message: str) -> None:
        self._logger.info(message)

    def close(self) -> None:
        root = logging.getLogger()
        for handler in self._handlers:
            try:
                handler.flush()
            except Exception:
                pass
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        root.removeFilter(self._stage_filter)


def _level_from_name(name: str) -> int:
    return getattr(logging, (name or "INFO").strip().upper(), logging.INFO)


def start_run_logger(config: Any, ctx: StorageContext, job_id: str) -> RunLogger:
    """Attach root handlers for one run and return the handle.

    Records from any ``logging.getLogger(__name__)`` in ``core``/``api`` propagate to
    the root logger, so these handlers capture the whole run. Call
    :meth:`RunLogger.bind_run_dir` once the run folder exists, and
    :meth:`RunLogger.close` when the run settles.
    """
    level = _level_from_name(getattr(config, "log_level", "INFO"))
    root = logging.getLogger()
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)

    stage_filter = _StageFilter()
    root.addFilter(stage_filter)
    formatter = logging.Formatter(_RUN_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Buffer records until the run folder exists; target is set in bind_run_dir.
    memory_handler = logging.handlers.MemoryHandler(
        capacity=10_000, flushLevel=logging.CRITICAL + 1, target=None
    )
    memory_handler.setLevel(level)
    memory_handler.addFilter(stage_filter)
    root.addHandler(memory_handler)

    extra: list[logging.Handler] = []
    if ctx.enabled:
        table_handler = TableLogHandler(ctx, job_id)
        table_handler.setLevel(level)
        table_handler.addFilter(stage_filter)
        root.addHandler(table_handler)
        extra.append(table_handler)

    return RunLogger(
        logging.getLogger("pitchpilot.run"), stage_filter, formatter, level, memory_handler, extra
    )
