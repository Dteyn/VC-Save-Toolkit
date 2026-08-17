"""Discover Vice City saves in a configured user-files folder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from .format import SaveFile, SaveFormatError


_SLOT_NAME = re.compile(r"^GTAVCsf(?P<slot>\d+)\.b$", re.IGNORECASE)
STANDARD_SAVE_SLOTS = tuple(range(1, 9))


@dataclass(frozen=True)
class DiscoveredSave:
    """Metadata used by the Save Selector without retaining an open SaveFile."""

    path: Path
    slot: int | None
    mission_name: str
    saved_at: datetime | None
    profile_name: str
    modified_at: datetime | None
    valid: bool
    error: str = ""

    @property
    def slot_label(self) -> str:
        return f"Slot {self.slot}" if self.slot is not None else "Other"


def slot_from_filename(path: str | Path) -> int | None:
    """Return the conventional GTAVCsfN slot number, if the name uses it."""

    match = _SLOT_NAME.match(Path(path).name)
    return int(match.group("slot")) if match else None


def save_path_for_slot(
    folder: str | Path, slot: int, records: list[DiscoveredSave] | None = None
) -> Path:
    """Return the existing path for a standard slot, or its canonical filename if empty."""

    if slot not in STANDARD_SAVE_SLOTS:
        raise ValueError(f"Save slot must be between {STANDARD_SAVE_SLOTS[0]} and {STANDARD_SAVE_SLOTS[-1]}.")
    root = Path(folder)
    if records is not None:
        for record in records:
            if record.slot == slot:
                return record.path
    return root / f"GTAVCsf{slot}.b"


def _modified_time(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def discover_saves(folder: str | Path) -> list[DiscoveredSave]:
    """Parse direct-child .b files and return selector metadata in slot order."""

    root = Path(folder)
    if not root.is_dir():
        return []

    candidates = [path for path in root.iterdir() if path.is_file() and path.suffix.casefold() == ".b"]
    candidates.sort(key=lambda path: (
        slot_from_filename(path) is None,
        slot_from_filename(path) if slot_from_filename(path) is not None else 10_000,
        path.name.casefold(),
    ))

    discovered: list[DiscoveredSave] = []
    for path in candidates:
        slot = slot_from_filename(path)
        modified = _modified_time(path)
        try:
            save = SaveFile.load(path)
        except (SaveFormatError, OSError, ValueError) as error:
            discovered.append(DiscoveredSave(
                path=path,
                slot=slot,
                mission_name="",
                saved_at=None,
                profile_name="Invalid / unsupported",
                modified_at=modified,
                valid=False,
                error=str(error),
            ))
            continue
        discovered.append(DiscoveredSave(
            path=path,
            slot=slot,
            mission_name=save.mission_name.strip() or "(unnamed save)",
            saved_at=save.timestamp,
            profile_name=save.profile.name,
            modified_at=modified,
            valid=True,
        ))
    return discovered
