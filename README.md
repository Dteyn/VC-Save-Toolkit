# VC Save Toolkit

> [!WARNING]
> There is a bug in the current version (0.5.0-rc1) which may prevent saves from from working correctly on Vice City VR standalone version. I'm aware of the issue and working on a fix. v0.5.0-rc2 will be released soon with a fix for this issue.

**VC Save Toolkit** is a desktop editor for *Grand Theft Auto: Vice City* save files. It can edit common player and world values, manage weapons and vehicles, inspect pickups and statistics, convert between supported save formats, and repair the persistent effects left behind by two of Vice City's irreversible pedestrian cheats.

VC Save Toolkit supports original PC saves, Steam saves, reVC-compatible saves, and Vice City VR saves.

> [!CAUTION]
> VC Save Toolkit is still beta software. Existing save files are backed up automatically before the toolkit overwrites them, but it is still a good idea to keep a separate copy of any save you care about.

## Supported save formats

| Format | Intended use |
| --- | --- |
| **Retail PC (CD / non-Steam)** | Original Windows `gta-vc.exe` save format |
| **Steam PC** | Original Steam PC release |
| **reVC-compatible format** | used by reVC-compatible builds |
| **Vice City VR** | Vice City VR save format |

A Vice City save with a recognized but unsupported layout may still open in **read-only** mode. This lets you inspect its basic information and file layout without risking a write to a format the toolkit does not understand well enough to edit.

Definitive Edition is not supported at this time.

## What can be edited?

The left sidebar divides an open save into eight sections:

| Section | What it contains |
| --- | --- |
| **Overview** | Save name, timestamp, detected format, checksum status, persistent-cheat warnings, and file layout |
| **Player** | Money, health, armour, maximum health/armour, and persistent player abilities |
| **World** | Player coordinates, in-game time, and weather |
| **Weapons** | Equipped weapon for each usable weapon slot, clip ammo, and total ammo |
| **Pickups** | All 336 saved pickup slots, with filtering and search |
| **Vehicles** | Hideout garage vehicles and parked-vehicle generators |
| **Gangs** | Gang weapon assignments |
| **Stats & progress** | Saved statistics and progress values |

Changes remain in the editor until you save them. The title bar and status badge show when the open file has unsaved edits.

## Installation

VC Save Toolkit runs from Python source and requires **Python 3.10 or newer**. PySide6 is the only runtime dependency and is installed by the included setup scripts.

### Windows

1. Download the release ZIP and **extract it to a folder**. Do not run the toolkit from inside the ZIP.
2. Install [Python 3](https://www.python.org/downloads/) if you do not already have Python 3.10 or newer.
3. Run `install-requirements.bat` once.
4. Double-click `vc_save_toolkit.pyw` to start the program.

The `.pyw` launcher prevents an extra console window from appearing on Windows.

### Linux

From a terminal in the extracted folder:

```bash
./install-requirements-linux.sh
python3 vc_save_toolkit.pyw
```

If the install script is not executable, run:

```bash
chmod +x install-requirements-linux.sh
```

### macOS

Run `install-requirements-macos.command`, then launch the toolkit from Terminal with:

```bash
python3 vc_save_toolkit.pyw
```

If needed, the dependency can also be installed manually on any platform:

```bash
python -m pip install -r requirements.txt
```

## Opening a save

The easiest way to open a save is **Save Selector**.

1. Start VC Save Toolkit.
2. Click **Save Selector** or press `Ctrl+O`.
3. On first use, choose the folder where your version of Vice City stores its saves.
4. Double-click a supported save, or select it and click **Open Selected**.

The selector reads each `.b` file in the chosen folder and shows useful information such as the save slot, mission/save name, in-game save time, detected format, filename, and file modification time.

The usual save locations are:

**Original `gta-vc.exe`:**

```text
Documents\GTA Vice City User Files
```

**reVC / Vice City VR:**

```text
<game folder>\userfiles
```

You can change this at any time from **Settings > Save Folder**.

For a save stored somewhere else, use **File > Browse for Save File** or press `Ctrl+Shift+O`. You can also drag a single `.b` save file directly onto the VC Save Toolkit window.

## Editing a save

Once a save opens, use the sidebar to move between sections. Most fields can be edited directly. Tables use drop-down lists or typed values where appropriate.

A few useful examples:

- Change money, health, armour, or player abilities from **Player**.
- Move the player or change the time/weather from **World**.
- Change equipped weapons and ammunition from **Weapons**.
- Search saved pickups by slot, type, model name, or ID from **Pickups**.
- Add, edit, or remove vehicles in hideout garages from **Vehicles**.
- Change gang weapon assignments from **Gangs**.
- Search and edit saved statistics from **Stats & progress**.

### Reverting changes

Use **Edit > Revert Current Page** to discard edits on the section you are viewing, or **Edit > Revert All Edits** to return the whole editor to the state it was in when the save was last opened or saved.

## Garage vehicles

The **Vehicles > Hideout garages** page shows the gameplay garage slots available in the save.

To add a vehicle:

1. Select an empty garage slot.
2. Click **Add Vehicle**.
3. Choose the vehicle, colours, protection options, and radio station.
4. Leave **Advanced placement** off unless you specifically want to enter your own coordinates and heading.
5. Click **Add Vehicle**.

For normal garage slots, the toolkit calculates a conservative parking position from the garage geometry and the selected vehicle model. This avoids needing to work out coordinates by hand for ordinary edits.

Double-click an occupied slot, or select it and choose **Edit Vehicle**, to change an existing stored vehicle. Use **Remove Vehicle** to clear it.

If a save contains an occupied stored-car record outside the garage's normal capacity, the toolkit labels it as nonstandard data rather than silently discarding it.

The **Parked vehicles** tab is separate and edits the game's saved car-generator records rather than hideout storage.

## Repairing persistent pedestrian cheats

Vice City has two cheats whose effects can remain stored in a save after the cheat itself is no longer active:

- **FIGHTFIGHTFIGHT** - Pedestrian Mayhem
- **NOBODYLIKESME** - Pedestrians Attack Player

When VC Save Toolkit recognizes one of these saved states, a **Persistent cheat effect** warning appears on the **Overview** page.

Use the **Repair** button shown there to remove the saved effect. For FIGHTFIGHTFIGHT, the toolkit restores the standard Vice City pedestrian threat relationships. For NOBODYLIKESME, it removes the player-threat flag while keeping the other saved threat flags intact.

The game's general cheat-use counter is **not** reset. That counter records overall cheat usage and does not identify which specific cheat caused the persistent effect.

If the toolkit finds a globally hostile pedestrian table that does not match a known stock cheat pattern, it reports the condition but does not rewrite it automatically.

## Saving your changes

### Save

Choose **Save** or press `Ctrl+S` to write changes back to the currently open file when the selected **Output** format matches the source format.

Before an existing save is replaced, VC Save Toolkit automatically creates a timestamped copy in:

```text
VC Save Toolkit Backups
```

This backup folder is created beside the save being written. Automatic backups cannot be disabled.

### Save to Slot

**Save to Slot** lets you write the current save directly into one of the game's eight standard save slots in your configured Save Folder. If a Save Folder is not set yet, the toolkit will prompt you to choose one.

The slot picker shows whether each slot is empty, occupied, the current save, or unreadable, along with the save/mission name, in-game save time, and detected format where available.

1. Choose **Save to Slot** from the toolbar or **File > Save to Slot**.
2. Select the destination slot.
3. Click **Save to Selected Slot**.
4. If the slot already contains a save, confirm that you want to replace it.

An existing destination is backed up automatically before it is replaced. If the selected **Output** format differs from the source format, Save to Slot can also be used for conversion as long as you choose a different destination slot.

### Save As

Choose **Save As** or press `Ctrl+Shift+S` when you want to:

- keep the original save untouched;
- write the edited save under another filename;
- save to another folder; or
- convert the save to another supported format.

If the destination file already exists, it is backed up before being replaced. A brand-new destination does not need a backup because there is no previous file to preserve.

## Converting between save formats

The strip near the top of the window shows the detected **Source** format and an **Output** format selector.

To convert a save:

1. Open the source save.
2. Choose the desired format from **Output**.
3. Choose **Save As** to select a filename and folder, or **Save to Slot** to write directly to another standard slot in your configured save folder.
4. Confirm the destination.
5. Test the converted save in the intended game/build before replacing your normal save.

VC Save Toolkit verifies the newly written file before it replaces the destination.

Some cross-runtime conversions are intentionally blocked when the save contains a record that does not yet have a proven safe translation between the 32-bit and 64-bit layouts. If the toolkit refuses one of these conversions, the save itself is not necessarily damaged; that particular conversion is simply not considered safe yet.

## Restoring a backup

If an edit causes trouble in-game:

1. Open **File > Restore Save**.
2. Choose one of the timestamped backups for that save.
3. Confirm the restore.

The Restore Save window shows two timestamps in your local time:

- **Created** - when VC Save Toolkit created the backup.
- **Modified** - the original save file's modified time preserved in that backup.

Backups are listed by backup creation time, newest first.

Before restoring an older backup, the toolkit makes another backup of the file currently at the destination. That means a restore can itself be undone if you picked the wrong version.

If no save is currently open, **Restore Save** asks you which save you want to restore first.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Open Save Selector |
| `Ctrl+Shift+O` | Browse for a save file |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+W` | Close the current save |
| `Ctrl+Q` | Exit |
| `Ctrl+1`  `Ctrl+8` | Switch between sidebar sections |
| `Ctrl+Alt+R` | Revert all edits |

## Appearance

Use **View > Appearance** to choose:

- **Follow System**
- **Light**
- **Dark**

If the interface layout becomes awkward after resizing or moving panels, use **View > Reset Window Layout**.

## Troubleshooting

### Save Selector does not show my saves

Check **Settings > Save Folder** and make sure it points directly to the folder containing the `.b` files. You can still use **Browse for Save File** to open a save elsewhere.

### A save opens as read-only

The file looks like a valid Vice City save, but its block layout does not match one of the editable formats listed above. VC Save Toolkit will allow inspection but will not write changes to it.

### Editing is disabled because of a checksum mismatch

The save failed its integrity check. VC Save Toolkit will not edit it while the stored checksum is invalid. Keep the original file and include it with a bug report if you believe the save should be valid.

### The toolkit refuses a conversion

Some saved runtime records cannot yet be translated safely between every supported format. The conversion is blocked rather than guessing and producing a questionable save.

### Saving fails

Make sure the save or destination folder is writable and that another program is not locking the file. Closing Vice City before editing its saves is recommended.

VC Save Toolkit creates a fresh log each time it starts. Use **Help > Open Log File** to open the current log when diagnosing a problem.

## Reporting problems

Bug reports and problematic saves are welcome at the [GitHub issue tracker](https://github.com/Dteyn/VC-Save-Toolkit/issues).

Useful details to include:

- VC Save Toolkit version;
- the detected save format;
- what you changed;
- what you expected to happen;
- what actually happened;
- the current log file from **Help > Open Log File**; and
- a copy of the affected save, if you are comfortable sharing it.

For general project information, visit the [VC Save Toolkit repository](https://github.com/Dteyn/VC-Save-Toolkit).

## License

VC Save Toolkit is released under the **MIT License**. See [`LICENSE`](LICENSE) for the full text.

The application icon incorporates the **device-floppy** glyph from [Tabler Icons](https://tabler.io/icons). See [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) for details.

You are visitor: ![Page views](https://dteyn-rad-page.netlify.app/.netlify/functions/pageviews?repo=VC-Save-Toolkit)
