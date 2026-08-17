"""Safe local file output, automatic backups, and restore support."""

from __future__ import annotations

from datetime import datetime
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile

from .format import SaveFile


LOGGER = logging.getLogger(__name__)
BACKUP_FOLDER = "VC Save Toolkit Backups"
BACKUP_TIMESTAMP_RE = re.compile(r"_(\d{8}-\d{6})(?:-(\d+))?(?=\.[^.]+$)")


OUTPUT_SUFFIXES = {
    "gta-vc-pc": "retail-pc",
    "gta-vc-steam": "steam-pc",
    "vc-pc-extended": "revc-compatible",
    "vice-city-vr": "vice-city-vr",
}


def suggested_path(source: Path, target_profile_key: str | None = None,
                   source_profile_key: str | None = None) -> Path:
    extension = source.suffix or ".b"
    if target_profile_key and source_profile_key and target_profile_key != source_profile_key:
        tag = OUTPUT_SUFFIXES.get(target_profile_key, "converted")
        return source.with_name(f"{source.stem}-{tag}-edited{extension}")
    return source.with_name(f"{source.stem}-edited{extension}")


def backup_folder_for(destination: str | Path) -> Path:
    """Return the folder used for backups of a destination save."""
    destination = Path(destination)
    return destination.parent / BACKUP_FOLDER


def _next_backup_path(destination: Path) -> Path:
    folder = backup_folder_for(destination)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = folder / f"{destination.stem}_{stamp}{destination.suffix}"
    counter = 2
    while backup.exists():
        backup = folder / f"{destination.stem}_{stamp}-{counter}{destination.suffix}"
        counter += 1
    return backup


def create_backup_copy(destination: str | Path) -> Path:
    """Create a timestamped byte-for-byte backup of an existing save."""
    destination = Path(destination)
    if not destination.is_file():
        raise FileNotFoundError(f"Save does not exist: {destination}")
    backup = _next_backup_path(destination)
    shutil.copy2(destination, backup)
    LOGGER.info("Created backup: %s", backup)
    return backup


def backup_created_at(backup: str | Path) -> datetime | None:
    """Return the local wall-clock time encoded in a toolkit backup name."""
    match = BACKUP_TIMESTAMP_RE.search(Path(backup).name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def _backup_sort_key(path: Path) -> tuple[datetime, int, str]:
    match = BACKUP_TIMESTAMP_RE.search(path.name)
    created = backup_created_at(path) or datetime.min
    sequence = int(match.group(2)) if match and match.group(2) else 1
    return created, sequence, path.name.casefold()


def list_backups(destination: str | Path) -> list[Path]:
    """List backups belonging to a save, newest first."""
    destination = Path(destination)
    folder = backup_folder_for(destination)
    if not folder.is_dir():
        return []

    # Backups created by the toolkit use: stem_YYYYMMDD-HHMMSS[-N].suffix
    pattern = re.compile(
        rf"^{re.escape(destination.stem)}_\d{{8}}-\d{{6}}(?:-\d+)?{re.escape(destination.suffix)}$",
        re.IGNORECASE,
    )
    backups = [path for path in folder.iterdir() if path.is_file() and pattern.match(path.name)]
    backups.sort(key=_backup_sort_key, reverse=True)
    return backups


def _atomic_write_validated_bytes(data: bytes, destination: Path,
                                  expected_profile_key: str | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        verified = SaveFile.load(temporary)
        if expected_profile_key and verified.profile.key != expected_profile_key:
            raise ValueError(
                f"Output validated as {verified.profile.name}, not requested format {expected_profile_key}."
            )
        os.replace(temporary, destination)
        LOGGER.info("Wrote and verified save: %s (%d bytes, profile=%s)",
                    destination, len(data), verified.profile.key)
    except Exception:
        LOGGER.exception("Failed while writing output: %s", destination)
        temporary.unlink(missing_ok=True)
        raise


def save_safely(save: SaveFile, destination: str | Path,
                target_profile_key: str | None = None) -> Path | None:
    """Save atomically, always backing up an existing destination first.

    New files do not need a backup because no existing data is being replaced.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = save.export_bytes(target_profile_key)
    backup = create_backup_copy(destination) if destination.exists() else None
    _atomic_write_validated_bytes(data, destination, target_profile_key)
    return backup


def restore_backup(backup: str | Path, destination: str | Path) -> Path | None:
    """Restore an exact backup safely and preserve the file being replaced.

    The selected backup is validated as a Vice City save before replacement. If the
    destination exists, a fresh safety backup is made first so a restore can itself be
    undone through the same Restore Save workflow.
    """
    backup = Path(backup)
    destination = Path(destination)
    if not backup.is_file():
        raise FileNotFoundError(f"Backup does not exist: {backup}")

    # Validate before touching the destination.
    selected = SaveFile.load(backup)
    data = backup.read_bytes()
    safety_backup = create_backup_copy(destination) if destination.exists() else None
    _atomic_write_validated_bytes(data, destination, selected.profile.key)
    LOGGER.info("Restored backup %s to %s; safety backup=%s", backup, destination, safety_backup)
    return safety_backup
