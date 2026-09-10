"""Container entry point for the shared ingestion ARQ worker."""

import logging

from app.services.ingestion_worker import WorkerSettings

# ARQ's INFO formatter includes job argument reprs, including document bytes.
logging.getLogger("arq.worker").setLevel(logging.WARNING)


def worker_settings() -> type[WorkerSettings]:
    """Expose the configured worker for structural verification and tooling."""
    return WorkerSettings
