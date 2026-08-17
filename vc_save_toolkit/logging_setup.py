"""Per-launch application logging."""

from __future__ import annotations

import logging
from pathlib import Path
import platform
import sys
import tempfile

from . import APP_NAME, APP_VERSION

LOG_FILENAME = "VC Save Toolkit.log"


def _candidate_log_directories() -> list[Path]:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    else:
        candidates.append(Path(sys.argv[0]).resolve().parent)
    candidates.append(Path.cwd())
    candidates.append(Path(tempfile.gettempdir()) / "VC Save Toolkit")

    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def configure_logging() -> Path:
    """Create a fresh log file for this launch and configure root logging."""
    log_path: Path | None = None
    last_error: OSError | None = None
    for directory in _candidate_log_directories():
        try:
            directory.mkdir(parents=True, exist_ok=True)
            candidate = directory / LOG_FILENAME
            with candidate.open("w", encoding="utf-8") as stream:
                stream.write("")
            log_path = candidate
            break
        except OSError as error:
            last_error = error

    if log_path is None:
        raise OSError(f"Could not create the application log: {last_error}")

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(log_path, mode="w", encoding="utf-8")],
        force=True,
    )
    logging.getLogger(__name__).info("%s v%s starting", APP_NAME, APP_VERSION)
    logging.getLogger(__name__).info("Python %s", sys.version.replace("\n", " "))
    logging.getLogger(__name__).info("Platform: %s", platform.platform())
    logging.getLogger(__name__).info("Working directory: %s", Path.cwd())
    logging.getLogger(__name__).info("Arguments: %r", sys.argv)
    logging.getLogger(__name__).info("Log file: %s", log_path)
    return log_path
