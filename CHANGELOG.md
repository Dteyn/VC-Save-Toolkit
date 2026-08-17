# Changelog

## 0.5.0 — Initial release

### Save support

- Supports Retail PC (CD / non-Steam), Steam PC, reVC-compatible, and Vice City VR save layouts.
- Opens recognized but unclassified Vice City layouts in read-only mode.
- Preserves unknown save data during same-format edits where the toolkit does not own a field.
- Rejects invalid checksums and unsupported layouts before editing.

### Editing

- Edit player values, abilities, position, time, and weather.
- Edit weapons and ammunition.
- Edit pickups, parked vehicles, gang weapons, and saved statistics.
- Manage hideout garage vehicles with Add, Edit, and Remove controls.
- Uses capacity-aware, model-aware automatic placement for garage vehicles while retaining advanced placement controls.

### Save management and recovery

- Save Selector scans a configured Vice City save folder and displays detected saves with useful metadata.
- Save to Slot supports all eight standard Vice City save slots, including empty slots.
- Save As supports writing to a different file or location.
- Creates timestamped backups automatically before overwriting an existing save.
- Restore Save provides access to previous automatic backups and backs up the current destination before restoration.
- Restore Save shows separate backup Created and Modified timestamps in the user's local time.
- Uses validated temporary output and post-write verification before replacing an existing save.

### Format conversion

- Converts between supported save formats where the required binary layouts are mapped.
- Allows converted saves to be written with Save As or Save to Slot.
- Refuses cross-runtime conversions that contain unproven live vehicle-record translations.

### Persistent cheat repair

- Detects and repairs persistent FIGHTFIGHTFIGHT / Pedestrian Mayhem state.
- Detects and repairs persistent NOBODYLIKESME / Pedestrians Attack Player state.
- Reports unknown global pedestrian-hostility patterns without rewriting them automatically.

### Interface

- Configurable Save Folder with guidance for stock Vice City, reVC, and Vice City VR locations.
- Drag-and-drop save opening.
- Follow System, Light, and Dark appearance modes.
- Vice City-inspired application styling and icon using the Tabler device-floppy glyph.
- Validation messages identify specific invalid fields before saving.
- Unsaved-change prompts for Open, Close, Exit, and Restore workflows.

### Distribution

- Windows `.pyw` launcher for console-free startup.
- `requirements.txt` plus dependency-install scripts for Windows, Linux, and macOS.
- Release-build scripts for producing a clean GitHub release ZIP.
