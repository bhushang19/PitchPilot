"""Persistent storage backends for run artifacts, logs, and job metadata.

Connection-string driven. When ``AZURE_STORAGE_CONNECTION_STRING`` is set (in the
process env / ``.env``), run artifacts sync to Azure Blob and logs + job metadata
go to Azure Table Storage. When it is absent, everything stays on the local disk
under ``output/`` and this module degrades to inert no-ops, so local development and
the existing behaviour are unchanged.

Runs always execute against a local working directory (the Playwright/filesystem
MCP and ffmpeg must write to a real disk). Blob is therefore a *sync target*: after
each stage the run folder is uploaded, and artifacts are served local-first with a
Blob fallback.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_log = logging.getLogger(__name__)

# Files that never need to leave the local machine (regeneratable / config noise).
_SYNC_SKIP_NAMES = {"pw-mcp-config.json"}
_SYNC_SKIP_SUFFIXES = {".tmp"}


@dataclass
class StorageContext:
    """Resolved storage handles for a process. Cheap to build; safe to share."""

    connection_string: str = ""
    blob_container_name: str = "pitchpilot-runs"
    table_logs_name: str = "pitchpilotlogs"
    table_jobs_name: str = "pitchpilotjobs"

    @property
    def enabled(self) -> bool:
        return bool((self.connection_string or "").strip())

    @classmethod
    def from_config(cls, config: Any) -> "StorageContext":
        return cls(
            connection_string=getattr(config, "storage_connection_string", "") or "",
            blob_container_name=getattr(config, "blob_container_name", "") or "pitchpilot-runs",
            table_logs_name=getattr(config, "table_logs_name", "") or "pitchpilotlogs",
            table_jobs_name=getattr(config, "table_jobs_name", "") or "pitchpilotjobs",
        )

    # --- lazily-created SDK clients (imported only when enabled) ---------------

    def blob_container(self):
        from azure.storage.blob import ContainerClient

        client = ContainerClient.from_connection_string(
            self.connection_string, self.blob_container_name
        )
        _ensure_container(client)
        return client

    def _table_client(self, name: str):
        from azure.data.tables import TableClient

        client = TableClient.from_connection_string(self.connection_string, name)
        _ensure_table(client)
        return client

    def logs_table(self):
        return self._table_client(self.table_logs_name)

    def jobs_table(self):
        return self._table_client(self.table_jobs_name)


def _ensure_container(client) -> None:
    try:
        client.create_container()
    except Exception:  # already exists / race — safe to ignore
        pass


def _ensure_table(client) -> None:
    try:
        client.create_table()
    except Exception:  # already exists / race — safe to ignore
        pass


# --- Blob artifact sync -------------------------------------------------------


def _blob_prefix(app_slug: str, run_id: str) -> str:
    return f"{app_slug}/{run_id}"


def _iter_run_files(run_dir: Path) -> Iterable[Path]:
    for path in run_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name in _SYNC_SKIP_NAMES or path.suffix.lower() in _SYNC_SKIP_SUFFIXES:
            continue
        yield path


def sync_run(ctx: StorageContext, run_dir: str | os.PathLike, app_slug: str, run_id: str) -> int:
    """Upload the run folder to Blob (overwriting changed files). Returns files synced.

    No-op (returns 0) when storage is disabled. Never raises to the caller; a failed
    sync must not break a run.
    """
    if not ctx.enabled:
        return 0
    root = Path(run_dir)
    if not root.is_dir():
        return 0
    try:
        container = ctx.blob_container()
    except Exception as exc:
        _log.warning("Blob sync skipped (container unavailable): %s", exc)
        return 0
    prefix = _blob_prefix(app_slug, run_id)
    synced = 0
    for path in _iter_run_files(root):
        rel = path.relative_to(root).as_posix()
        blob_name = f"{prefix}/{rel}"
        try:
            with path.open("rb") as fh:
                container.upload_blob(name=blob_name, data=fh, overwrite=True)
            synced += 1
        except Exception as exc:
            _log.warning("Blob upload failed for %s: %s", blob_name, exc)
    if synced:
        _log.debug("Synced %d file(s) to blob under %s", synced, prefix)
    return synced


def list_run_blobs(ctx: StorageContext, app_slug: str, run_id: str) -> list[str]:
    """Return the run's blob names relative to its ``<app_slug>/<run_id>/`` prefix."""
    if not ctx.enabled:
        return []
    prefix = _blob_prefix(app_slug, run_id) + "/"
    try:
        container = ctx.blob_container()
        return [
            blob.name[len(prefix) :]
            for blob in container.list_blobs(name_starts_with=prefix)
            if blob.name.startswith(prefix)
        ]
    except Exception as exc:
        _log.warning("Blob listing failed for %s: %s", prefix, exc)
        return []


def resolve_artifact(
    ctx: StorageContext,
    local_path: str | os.PathLike,
    app_slug: str,
    run_id: str,
    rel_name: str,
) -> tuple[str | None, bool]:
    """Return ``(path, is_temp)`` for an artifact, fetching from Blob if needed.

    Serves the on-disk file when it exists (``is_temp=False``). Otherwise, when storage
    is enabled, downloads the blob to a temp file and returns ``(temp_path, True)`` so
    the caller can delete it after serving. Returns ``(None, False)`` when the artifact
    cannot be found anywhere.
    """
    local = Path(local_path)
    if local.is_file():
        return str(local), False
    if not ctx.enabled:
        return None, False
    blob_name = f"{_blob_prefix(app_slug, run_id)}/{rel_name}"
    try:
        container = ctx.blob_container()
        downloader = container.download_blob(blob_name)
        suffix = Path(rel_name).suffix
        tmp = tempfile.NamedTemporaryFile(prefix="pp-artifact-", suffix=suffix, delete=False)
        try:
            downloader.readinto(tmp)
        finally:
            tmp.close()
        return tmp.name, True
    except Exception as exc:
        _log.debug("Artifact not in blob (%s): %s", blob_name, exc)
        return None, False


# --- Job metadata table -------------------------------------------------------


def _sanitize_key(value: str) -> str:
    # Table keys forbid / \ # ? and control chars; keep it conservative.
    bad = "/\\#?\t\n\r"
    return "".join("-" if ch in bad else ch for ch in (value or "")) or "unknown"


def upsert_job(ctx: StorageContext, app_slug: str, run_id: str, data: dict[str, Any]) -> None:
    """Upsert one job-metadata row (PartitionKey=app_slug, RowKey=run_id). No-op if disabled."""
    if not ctx.enabled:
        return
    entity: dict[str, Any] = {
        "PartitionKey": _sanitize_key(app_slug),
        "RowKey": _sanitize_key(run_id),
    }
    for key, value in data.items():
        if value is None:
            continue
        entity[key] = value if isinstance(value, (str, int, float, bool)) else str(value)
    try:
        table = ctx.jobs_table()
        table.upsert_entity(entity)
    except Exception as exc:
        _log.warning("Job metadata upsert failed for %s/%s: %s", app_slug, run_id, exc)


def query_jobs(ctx: StorageContext) -> list[dict[str, Any]]:
    """Return all job-metadata rows as plain dicts. Empty list if disabled/unavailable."""
    if not ctx.enabled:
        return []
    try:
        table = ctx.jobs_table()
        return [dict(entity) for entity in table.list_entities()]
    except Exception as exc:
        _log.warning("Job metadata query failed: %s", exc)
        return []


def get_job_meta(ctx: StorageContext, app_slug: str, run_id: str) -> dict[str, Any] | None:
    """Return one job-metadata row, or None if absent/disabled."""
    if not ctx.enabled:
        return None
    try:
        table = ctx.jobs_table()
        return dict(table.get_entity(_sanitize_key(app_slug), _sanitize_key(run_id)))
    except Exception as exc:
        _log.debug("Job metadata not found for %s/%s: %s", app_slug, run_id, exc)
        return None


# --- Log records table --------------------------------------------------------


def _seq_row_key(seq: int) -> str:
    # Zero-padded so RowKey sorts chronologically within a partition.
    return f"{seq:012d}"


def write_log_batch(ctx: StorageContext, job_id: str, records: list[dict[str, Any]]) -> None:
    """Batch-write buffered log records for one job. No-op if disabled."""
    if not ctx.enabled or not records:
        return
    from azure.data.tables import TransactionOperation

    partition = _sanitize_key(job_id)
    entities = []
    for rec in records:
        entity = {
            "PartitionKey": partition,
            "RowKey": _seq_row_key(int(rec["seq"])),
            "ts": rec.get("ts") or datetime.now(timezone.utc).isoformat(),
            "level": rec.get("level", ""),
            "logger": rec.get("logger", ""),
            "stage": rec.get("stage", ""),
            "message": rec.get("message", ""),
        }
        entities.append((TransactionOperation.UPSERT, entity))
    try:
        table = ctx.logs_table()
        # Table transactions cap at 100 ops per batch.
        for start in range(0, len(entities), 100):
            table.submit_transaction(entities[start : start + 100])
    except Exception as exc:
        _log.warning("Log batch write failed for job %s: %s", job_id, exc)


def query_logs(ctx: StorageContext, job_id: str) -> list[dict[str, Any]]:
    """Return log records for one job, ordered oldest-first. Empty if disabled/unavailable."""
    if not ctx.enabled:
        return []
    try:
        table = ctx.logs_table()
        rows = table.query_entities(
            "PartitionKey eq @pk", parameters={"pk": _sanitize_key(job_id)}
        )
        records = [
            {
                "ts": row.get("ts", ""),
                "level": row.get("level", ""),
                "logger": row.get("logger", ""),
                "stage": row.get("stage", ""),
                "message": row.get("message", ""),
            }
            for row in rows
        ]
        records.sort(key=lambda r: r["ts"])
        return records
    except Exception as exc:
        _log.warning("Log query failed for job %s: %s", job_id, exc)
        return []


# --- Local .log parsing (fallback for the logs endpoint) ----------------------

_LOCAL_LOCK = threading.Lock()


def parse_local_log(run_dir: str | os.PathLike) -> list[dict[str, Any]]:
    """Parse a run's local ``run.log`` into records matching the Table shape."""
    path = Path(run_dir) / "run.log"
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    with _LOCAL_LOCK, path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            # Format: "<ts> <LEVEL> <logger> [stage] message"
            parts = line.split(" ", 3)
            if len(parts) < 4:
                records.append({"ts": "", "level": "", "logger": "", "stage": "", "message": line})
                continue
            ts, level, logger, rest = parts
            stage = ""
            message = rest
            if rest.startswith("[") and "]" in rest:
                stage = rest[1 : rest.index("]")]
                message = rest[rest.index("]") + 1 :].lstrip()
            records.append(
                {"ts": ts, "level": level, "logger": logger, "stage": stage, "message": message}
            )
    return records
