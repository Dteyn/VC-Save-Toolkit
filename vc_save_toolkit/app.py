"""PySide6 user interface for VC Save Toolkit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import math
import secrets
from pathlib import Path
from typing import Callable
import sys
import time

try:
    from PySide6.QtCore import (QEventLoop, QRegularExpression, QSettings, QSize, QThread, QTimer, QUrl, Qt, Signal,
                              QtMsgType, qInstallMessageHandler)
    from PySide6.QtGui import (QAction, QActionGroup, QDesktopServices, QDoubleValidator, QDragEnterEvent, QGuiApplication,
                             QIcon, QDropEvent, QIntValidator, QPalette, QRegularExpressionValidator, QShortcut)
    from PySide6.QtWidgets import (
        QApplication, QAbstractItemView, QAbstractSpinBox, QCheckBox, QComboBox, QDoubleSpinBox,
        QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QLayout,
        QGroupBox, QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem,
        QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
        QStackedWidget, QStatusBar, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTabWidget, QSplitter,
        QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QLineEdit,
    )
except ImportError as error:  # Friendly failure when launched before installation.
    raise SystemExit("PySide6 is not installed. Run the platform install-requirements script or: python -m pip install -r requirements.txt") from error

from . import APP_AUTHOR, APP_NAME, APP_VERSION, GITHUB_ISSUES, GITHUB_REPO, ORGANIZATION_NAME
from .format import (PedCheatState, PlayerValues, SaveFile, SaveFormatError,
                     WeaponValues, WorldValues, SUPPORTED_PROFILE_BY_KEY)
from .io import backup_created_at, backup_folder_for, list_backups, restore_backup, save_safely, suggested_path
from .discovery import (DiscoveredSave, STANDARD_SAVE_SLOTS, discover_saves,
                        save_path_for_slot)
from .garage_data import (
    GAMEPLAY_GARAGE_NAMES, STORAGE_GROUP_NAMES, GaragePose, effective_garage_capacity,
    is_gameplay_garage_slot, is_out_of_capacity_record, placement_source_label,
    resolve_new_garage_vehicle_pose, should_show_garage_record, stored_car_raw_index,
)
from .logging_setup import configure_logging
from .records import (
    GANG_NAMES, PICKUP_TYPES, CarGeneratorRecord, GangRecord,
    PickupRecord, StoredCarRecord, StoredCarFlags, STORED_CAR_KNOWN_FLAG_MASK,
    stored_car_flags_summary, friendly_stat_name, pickup_model_name, pickup_model_choices,
    VEHICLE_NAMES, RADIO_STATIONS, color_name, compact_color_name,
)
from .themes import DARK, LIGHT
from .validation import parse_bool, parse_float, parse_int


LOGGER = logging.getLogger(__name__)


ASSET_DIR = Path(__file__).resolve().parent / "assets"
APP_ICON_PNG = ASSET_DIR / "vc_save_toolkit.png"


def application_icon_path() -> Path:
    """Return the packaged application icon."""
    return APP_ICON_PNG


WEAPON_NAMES = (
    "Unarmed", "Brass knuckles", "Screwdriver", "Golf club", "Nightstick",
    "Knife", "Baseball bat", "Hammer", "Cleaver", "Machete", "Katana",
    "Chainsaw", "Grenade", "Remote grenade", "Tear gas", "Molotov",
    "Rocket", "Colt .45", "Python", "Shotgun", "SPAS-12", "Stubby shotgun",
    "Tec-9", "Uzi", "Ingram", "MP5", "M4", "Ruger", "Sniper rifle",
    "Laser sniper", "Rocket launcher", "Flamethrower", "M60", "Minigun",
    "Detonator", "Helicopter cannon", "Camera",
)
SLOT_NAMES = ("Unarmed", "Melee", "Thrown", "Handgun", "Shotgun", "SMG",
              "Rifle", "Heavy", "Sniper", "Special")
SLOT_TYPES = (
    (0,), (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
    (0, 12, 13, 14, 15), (0, 17, 18), (0, 19, 20, 21),
    (0, 22, 23, 24, 25), (0, 26, 27), (0, 30, 31, 32, 33),
    (0, 28, 29), (0, 34, 36),
)
WEATHER_NAMES = ((-1, "Random"), (0, "Sunny"), (1, "Cloudy"),
                 (2, "Rainy"), (3, "Foggy"), (4, "Extra sunny"),
                 (5, "Hurricane"))


def choice_label(name: str, value: int) -> str:
    """Format a named numeric choice."""
    return f"{name} ({value})"



def alphabetical_choices(items):
    return sorted(items, key=lambda item: (str(item[0]).casefold(), int(item[1])))


def weapon_choices(ids=None):
    values = range(len(WEAPON_NAMES)) if ids is None else ids
    items = []
    for weapon_type in values:
        name = "Empty" if weapon_type == 0 else WEAPON_NAMES[weapon_type]
        items.append((choice_label(name, weapon_type), weapon_type))
    return alphabetical_choices(items)


def vehicle_choices():
    return alphabetical_choices([
        (choice_label(name, model_id), model_id)
        for model_id, name in enumerate(VEHICLE_NAMES, 130)
    ])


def color_choices():
    items = []
    for color_id in range(-1, 95):
        raw = color_name(color_id)
        if color_id == -1:
            semantic = "Random"
        else:
            semantic = raw.split(" — ", 1)[1] if " — " in raw else raw
        items.append((choice_label(semantic, color_id), color_id))
    return alphabetical_choices(items)


def radio_choices(include_default=True):
    items = [(choice_label(name, station), station) for station, name in enumerate(RADIO_STATIONS)]
    items.append((choice_label("Radio off", 10), 10))
    if include_default:
        items.append((choice_label("Default", -1), -1))
    return alphabetical_choices(items)


def configure_combo_popup(combo: QComboBox, desired_rows: int | None = None) -> QComboBox:
    rows = combo.count() if desired_rows is None else desired_rows
    visible_rows = max(1, min(int(rows), 30))
    combo.setMaxVisibleItems(visible_rows)
    view = combo.view()
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    view.setMinimumHeight(min(520, visible_rows * 24 + 6))
    for index in range(combo.count()):
        value = combo.itemData(index)
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            continue
        if combo.itemText(index).rstrip().endswith(f"({numeric})"):
            combo.setItemData(index, f"ID {numeric}", Qt.ItemDataRole.ToolTipRole)
    return combo


def set_combo_id_tooltip(combo: QComboBox) -> None:
    """Use the selected enum's numeric ID as the combo tooltip."""
    value = combo.currentData()
    try:
        combo.setToolTip(f"ID {int(value)}")
    except (TypeError, ValueError):
        combo.setToolTip("")


GARAGE_FLAG_INFO = (
    (
        StoredCarFlags.BULLETPROOF,
        "Bulletproof",
        "Stored flag 0x01",
    ),
    (
        StoredCarFlags.FIREPROOF,
        "Fireproof",
        "Stored flag 0x02",
    ),
    (
        StoredCarFlags.EXPLOSIONPROOF,
        "Explosionproof",
        "Stored flag 0x04",
    ),
    (
        StoredCarFlags.COLLISIONPROOF,
        "Collisionproof",
        "Stored flag 0x08",
    ),
    (
        StoredCarFlags.MELEEPROOF,
        "Meleeproof",
        "Stored flag 0x10",
    ),
)


class GarageVehicleDialog(QDialog):
    """Add or edit one stored garage vehicle."""

    def __init__(self, record: StoredCarRecord, location_label: str, adding: bool = False,
                 placement_source: str = "", auto_pose_resolver: Callable[[int], GaragePose | None] | None = None,
                 parent=None):
        super().__init__(parent)
        self.source_record = record
        self.adding = adding
        self.original_flags = 0 if adding else int(record.flags)
        self.auto_pose_resolver = auto_pose_resolver
        self._placement_source = placement_source
        self.setWindowTitle("Add Garage Vehicle" if adding else "Edit Garage Vehicle")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title = QLabel("Add vehicle to garage" if adding else "Edit stored vehicle")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        context = QLabel(location_label)
        context.setObjectName("muted")
        layout.addWidget(context)

        vehicle_box = QGroupBox("Vehicle")
        vehicle_form = QFormLayout(vehicle_box)
        vehicle_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(280)
        for label, model_id in vehicle_choices():
            self.model_combo.addItem(label, model_id)
        configure_combo_popup(self.model_combo, self.model_combo.count())
        model = record.model_id if record.model_id else 130
        self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(model)))
        set_combo_id_tooltip(self.model_combo)
        self.model_combo.currentIndexChanged.connect(lambda _=0: set_combo_id_tooltip(self.model_combo))
        vehicle_form.addRow("Model", self.model_combo)
        layout.addWidget(vehicle_box)

        appearance_box = QGroupBox("Appearance")
        appearance_form = QFormLayout(appearance_box)
        appearance_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.color_1 = QComboBox()
        self.color_2 = QComboBox()
        for label, color_id in color_choices():
            self.color_1.addItem(label, color_id)
            self.color_2.addItem(label, color_id)
        configure_combo_popup(self.color_1)
        configure_combo_popup(self.color_2)
        first_color = record.color_1 if not adding and -1 <= record.color_1 <= 94 else -1
        second_color = record.color_2 if not adding and -1 <= record.color_2 <= 94 else -1
        self.color_1.setCurrentIndex(max(0, self.color_1.findData(first_color)))
        self.color_2.setCurrentIndex(max(0, self.color_2.findData(second_color)))
        self.radio = QComboBox()
        for label, station in radio_choices(include_default=True):
            self.radio.addItem(label, station)
        configure_combo_popup(self.radio)
        radio = record.radio if not adding and -1 <= record.radio <= 10 else -1
        self.radio.setCurrentIndex(max(0, self.radio.findData(radio)))
        for combo in (self.color_1, self.color_2, self.radio):
            set_combo_id_tooltip(combo)
            combo.currentIndexChanged.connect(lambda _=0, c=combo: set_combo_id_tooltip(c))
        appearance_form.addRow("Primary colour", self.color_1)
        appearance_form.addRow("Secondary colour", self.color_2)
        appearance_form.addRow("Radio", self.radio)
        layout.addWidget(appearance_box)

        protection_box = QGroupBox("Protection")
        protection_layout = QGridLayout(protection_box)
        self.flag_boxes: list[tuple[StoredCarFlags, QCheckBox]] = []
        for index, (flag, label, tooltip) in enumerate(GARAGE_FLAG_INFO):
            box = QCheckBox(label)
            box.setChecked(bool(self.original_flags & int(flag)))
            box.setToolTip(tooltip)
            protection_layout.addWidget(box, index // 2, index % 2)
            self.flag_boxes.append((flag, box))
        layout.addWidget(protection_box)

        placement_summary = QGroupBox("Placement")
        placement_summary_layout = QVBoxLayout(placement_summary)
        if adding and placement_source:
            self.placement_label = QLabel(f"Automatic: {placement_source_label(placement_source)}")
        else:
            self.placement_label = QLabel("Existing saved position")
        self.placement_label.setObjectName("muted")
        placement_summary_layout.addWidget(self.placement_label)
        layout.addWidget(placement_summary)

        self.advanced_toggle = QPushButton("Advanced placement")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolTip("Show coordinates and heading.")
        layout.addWidget(self.advanced_toggle)

        self.placement_box = QGroupBox("Coordinates and heading")
        placement_form = QFormLayout(self.placement_box)
        placement_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.pos_x = decimal_spin(-10000.0, 10000.0, 3)
        self.pos_y = decimal_spin(-10000.0, 10000.0, 3)
        self.pos_z = decimal_spin(-10000.0, 10000.0, 3)
        self.pos_x.setValue(record.position[0])
        self.pos_y.setValue(record.position[1])
        self.pos_z.setValue(record.position[2])
        self.heading = decimal_spin(-180.0, 180.0, 1)
        ax, ay, _az = record.angles
        heading = math.degrees(math.atan2(ay, ax)) if math.hypot(ax, ay) > 0.001 else 0.0
        self.heading.setValue(heading)
        self.heading.setToolTip("Degrees: 0 = +X, 90 = +Y")
        self._advanced_dirty = False
        for control in (self.pos_x, self.pos_y, self.pos_z, self.heading):
            control.valueChanged.connect(self._mark_advanced_dirty)
        placement_form.addRow("X", self.pos_x)
        placement_form.addRow("Y", self.pos_y)
        placement_form.addRow("Z", self.pos_z)
        placement_form.addRow("Heading", self.heading)
        layout.addWidget(self.placement_box)
        self.placement_box.setVisible(False)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.setText("Advanced placement")
        self.advanced_toggle.toggled.connect(self._toggle_advanced_placement)
        if self.adding and self.auto_pose_resolver is not None:
            self.model_combo.currentIndexChanged.connect(self._automatic_model_changed)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add Vehicle" if adding else "Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_advanced_placement(self, shown: bool) -> None:
        self.placement_box.setVisible(shown)
        self.advanced_toggle.setText("Advanced placement")
        self.adjustSize()

    def _mark_advanced_dirty(self, *unused) -> None:
        self._advanced_dirty = True

    def _automatic_model_changed(self, *unused) -> None:
        if not self.adding or self.auto_pose_resolver is None or self._advanced_dirty:
            return
        pose = self.auto_pose_resolver(int(self.model_combo.currentData()))
        if pose is None:
            return
        self._placement_source = pose.source
        controls = (self.pos_x, self.pos_y, self.pos_z, self.heading)
        for control in controls:
            control.blockSignals(True)
        try:
            self.pos_x.setValue(pose.position[0])
            self.pos_y.setValue(pose.position[1])
            self.pos_z.setValue(pose.position[2])
            self.heading.setValue(math.degrees(math.atan2(pose.forward[1], pose.forward[0])))
        finally:
            for control in controls:
                control.blockSignals(False)
        self.placement_label.setText(f"Automatic: {placement_source_label(pose.source)}")

    def _flags(self) -> int:
        known = 0
        for flag, box in self.flag_boxes:
            if box.isChecked():
                known |= int(flag)
        unknown = 0 if self.adding else (self.original_flags & ~STORED_CAR_KNOWN_FLAG_MASK)
        return unknown | known

    def record(self) -> StoredCarRecord:
        model_id = int(self.model_combo.currentData())
        automatic_pose = None
        if self.adding and not self._advanced_dirty and self.auto_pose_resolver is not None:
            automatic_pose = self.auto_pose_resolver(model_id)
        if automatic_pose is not None:
            position = automatic_pose.position
            forward = automatic_pose.forward
        elif not self.adding and not self._advanced_dirty:
            position = self.source_record.position
            forward = self.source_record.angles
        else:
            radians = math.radians(self.heading.value())
            position = (self.pos_x.value(), self.pos_y.value(), self.pos_z.value())
            forward = (math.cos(radians), math.sin(radians), 0.0)
        color_1 = int(self.color_1.currentData())
        color_2 = int(self.color_2.currentData())
        radio = int(self.radio.currentData())
        # CStoredCar restores concrete uint8 colour/radio values. Resolve the
        # dialog's Random/Default sentinels before writing a new record.
        if self.adding:
            if color_1 < 0:
                color_1 = secrets.randbelow(95)
            if color_2 < 0:
                color_2 = secrets.randbelow(95)
            if radio < 0:
                radio = secrets.randbelow(10)
        return StoredCarRecord(
            self.source_record.garage, self.source_record.slot, model_id,
            position, forward, self._flags(),
            color_1, color_2, radio,
            0 if self.adding else self.source_record.bomb_type,
            -2 if self.adding else self.source_record.variation_a,
            -2 if self.adding else self.source_record.variation_b,
        )


class CompactNotice(QFrame):
    """Compact cross-format save notice."""

    def __init__(self):
        super().__init__()
        self.setObjectName("conversionNotice")
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)
        self.label = QLabel("")
        self.label.setObjectName("conversionNoticeText")
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.label)
        layout.addStretch()

    def set_message(self, title: str, body: str) -> None:
        self.label.setText(f"{title}: {body}")


class FolderSettingsDialog(QDialog):
    """Configure the folder that contains Vice City save files."""

    def __init__(self, settings: QSettings, current_save: Path | None = None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.current_save = current_save
        self.setWindowTitle("Save Folder")
        self.setModal(True)
        self.setMinimumWidth(720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Vice City save folder")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        intro = QLabel("Choose the folder containing your Vice City .b save files.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        locations = QGroupBox("Where are my saves?")
        locations_layout = QVBoxLayout(locations)
        stock_help = QLabel(
            "<b>Stock gta-vc.exe:</b> choose <code>Documents\\GTA Vice City User Files</code>."
        )
        stock_help.setTextFormat(Qt.TextFormat.RichText)
        stock_help.setWordWrap(True)
        revc_help = QLabel(
            "<b>reVC / Vice City VR:</b> choose the <code>userfiles</code> folder inside the game installation folder."
        )
        revc_help.setTextFormat(Qt.TextFormat.RichText)
        revc_help.setWordWrap(True)
        locations_layout.addWidget(stock_help)
        locations_layout.addWidget(revc_help)
        layout.addWidget(locations)

        form_box = QGroupBox("Configured location")
        form = QGridLayout(form_box)
        form.setColumnStretch(1, 1)

        self.save_folder_edit = QLineEdit(str(settings.value("save_folder", "") or ""))
        self.save_folder_edit.setPlaceholderText("No save folder configured")
        self.save_folder_edit.setClearButtonEnabled(True)
        save_browse = QPushButton("Browse…")
        save_open = QPushButton("Open Folder")
        save_browse.clicked.connect(lambda: self._browse(self.save_folder_edit, "Choose Vice City save folder"))
        save_open.clicked.connect(lambda: self._open(self.save_folder_edit))
        form.addWidget(QLabel("Save folder"), 0, 0)
        form.addWidget(self.save_folder_edit, 0, 1)
        form.addWidget(save_browse, 0, 2)
        form.addWidget(save_open, 0, 3)

        stock_folder = Path.home() / "Documents" / "GTA Vice City User Files"
        if stock_folder.is_dir():
            use_stock = QPushButton("Use Stock Save Folder")
            use_stock.clicked.connect(lambda: self.save_folder_edit.setText(str(stock_folder)))
            form.addWidget(use_stock, 1, 1, 1, 2)

        if current_save is not None:
            use_current = QPushButton("Use Current Save Folder")
            use_current.clicked.connect(lambda: self.save_folder_edit.setText(str(current_save.parent)))
            form.addWidget(use_current, 2, 1, 1, 2)

        layout.addWidget(form_box)

        self.validation_label = QLabel("")
        self.validation_label.setObjectName("warningText")
        self.validation_label.setWordWrap(True)
        layout.addWidget(self.validation_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _clean_path(text: str) -> Path | None:
        text = text.strip()
        return Path(text).expanduser() if text else None

    def _browse(self, edit: QLineEdit, title: str) -> None:
        start = edit.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, title, start)
        if selected:
            edit.setText(selected)

    def _open(self, edit: QLineEdit) -> None:
        path = self._clean_path(edit.text())
        if path and path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.validation_label.setText("Choose an existing folder before opening it.")

    def _save(self) -> None:
        save_folder = self._clean_path(self.save_folder_edit.text())
        if save_folder is not None and not save_folder.is_dir():
            self.validation_label.setText("Save folder does not exist or is not a folder.")
            return
        self.settings.setValue("save_folder", str(save_folder) if save_folder else "")
        self.accept()


class SaveSelectorDialog(QDialog):
    """Browse supported saves discovered in the configured save folder."""

    def __init__(self, folder: Path, current_save: Path | None = None, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.current_save = current_save
        self.selected_path: Path | None = None
        self.request_settings = False
        self.browse_other = False
        self._records: list[DiscoveredSave] = []
        self.setWindowTitle("Save Selector")
        self.setModal(True)
        self.resize(980, 520)
        self.setMinimumSize(780, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Save Selector")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        intro = QLabel("Select a Vice City save found in your configured save folder.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        folder_row = QHBoxLayout()
        folder_caption = QLabel("Save folder:")
        folder_caption.setObjectName("mutedText")
        folder_row.addWidget(folder_caption)
        self.folder_label = QLabel(str(folder))
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.folder_label.setToolTip(str(folder))
        folder_row.addWidget(self.folder_label, 1)
        change_button = QPushButton("Change Save Folder…")
        change_button.clicked.connect(self._change_folder)
        folder_row.addWidget(change_button)
        layout.addLayout(folder_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("Slot", "Save / mission", "Saved", "Format", "File", "Modified"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        layout.addWidget(self.table, 1)

        self.status = QLabel("")
        self.status.setObjectName("mutedText")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        controls = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        browse = QPushButton("Browse for Save File…")
        browse.clicked.connect(self._browse_other)
        controls.addWidget(refresh)
        controls.addWidget(browse)
        controls.addStretch()
        self.open_button = QPushButton("Open Selected")
        self.open_button.setObjectName("primary")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        controls.addWidget(self.open_button)
        controls.addWidget(close_button)
        layout.addLayout(controls)

        self.refresh()

    @staticmethod
    def _date_text(value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S") if value else "—"

    def refresh(self) -> None:
        self._records = discover_saves(self.folder)
        self.table.setRowCount(0)
        selected_row = -1
        for record in self._records:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                record.slot_label,
                record.mission_name if record.valid else "Could not read save",
                self._date_text(record.saved_at),
                record.profile_name,
                record.path.name,
                self._date_text(record.modified_at),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, str(record.path))
                if not record.valid:
                    item.setToolTip(record.error)
                self.table.setItem(row, column, item)
            if self.current_save is not None:
                try:
                    if record.path.resolve() == self.current_save.resolve():
                        selected_row = row
                except OSError:
                    pass

        valid_count = sum(1 for record in self._records if record.valid)
        invalid_count = len(self._records) - valid_count
        if not self._records:
            self.status.setText("No .b saves found in this folder.")
        elif invalid_count:
            saves = (
                "No saves found" if valid_count == 0
                else "1 save found" if valid_count == 1
                else f"{valid_count} saves found"
            )
            unreadable = (
                "1 file could not be read" if invalid_count == 1
                else f"{invalid_count} files could not be read"
            )
            self.status.setText(f"{saves}; {unreadable}.")
        else:
            self.status.setText("1 save found." if valid_count == 1 else f"{valid_count} saves found.")

        if selected_row >= 0:
            self.table.selectRow(selected_row)
        elif valid_count:
            for row, record in enumerate(self._records):
                if record.valid:
                    self.table.selectRow(row)
                    break
        self._selection_changed()

    def _selected_record(self) -> DiscoveredSave | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._records):
            return None
        return self._records[row]

    def _selection_changed(self) -> None:
        record = self._selected_record()
        self.open_button.setEnabled(bool(record and record.valid))

    def _double_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._records) and self._records[row].valid:
            self.table.selectRow(row)
            self._open_selected()

    def _open_selected(self) -> None:
        record = self._selected_record()
        if record is None or not record.valid:
            return
        self.selected_path = record.path
        self.accept()

    def _change_folder(self) -> None:
        self.request_settings = True
        self.reject()

    def _browse_other(self) -> None:
        self.browse_other = True
        self.reject()


class SaveSlotDialog(QDialog):
    """Choose one of Vice City's standard save slots in the configured folder."""

    def __init__(self, folder: Path, output_format: str, current_save: Path | None = None, parent=None):
        super().__init__(parent)
        self.folder = Path(folder)
        self.current_save = current_save
        self.output_format = output_format
        self.selected_slot: int | None = None
        self.selected_path: Path | None = None
        self.selected_record: DiscoveredSave | None = None
        self._records = discover_saves(self.folder)
        self._records_by_slot: dict[int, DiscoveredSave] = {}
        for record in self._records:
            if record.slot in STANDARD_SAVE_SLOTS and record.slot not in self._records_by_slot:
                self._records_by_slot[record.slot] = record

        self.setWindowTitle("Save to Slot")
        self.setModal(True)
        self.resize(820, 480)
        self.setMinimumSize(700, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Save to another slot")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        intro = QLabel(
            "Choose one of Vice City's eight save slots. Existing saves are backed up automatically before replacement."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        folder_label = QLabel(f"Save folder: {self.folder}")
        folder_label.setObjectName("mutedText")
        folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder_label.setToolTip(str(self.folder))
        layout.addWidget(folder_label)

        format_label = QLabel(f"Output format: {self.output_format}")
        format_label.setObjectName("mutedText")
        layout.addWidget(format_label)

        self.table = QTableWidget(len(STANDARD_SAVE_SLOTS), 5)
        self.table.setHorizontalHeaderLabels(("Slot", "Status", "Save / mission", "Saved", "Format"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        layout.addWidget(self.table, 1)

        controls = QHBoxLayout()
        controls.addStretch()
        self.save_button = QPushButton("Save to Selected Slot")
        self.save_button.setObjectName("primary")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._accept_selection)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        controls.addWidget(self.save_button)
        controls.addWidget(cancel_button)
        layout.addLayout(controls)

        self._populate()

    @staticmethod
    def _date_text(value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S") if value else "—"

    def _is_current(self, path: Path) -> bool:
        if self.current_save is None:
            return False
        try:
            return path.resolve() == self.current_save.resolve()
        except OSError:
            return path == self.current_save

    def _populate(self) -> None:
        preferred_row = -1
        fallback_row = -1
        current_row = -1
        for row, slot in enumerate(STANDARD_SAVE_SLOTS):
            record = self._records_by_slot.get(slot)
            destination = save_path_for_slot(self.folder, slot, self._records)
            is_current = self._is_current(destination)

            if record is None:
                status = "Empty"
                mission = "—"
                saved = "—"
                profile = "—"
                if preferred_row < 0:
                    preferred_row = row
            elif is_current:
                status = "Current save"
                mission = record.mission_name if record.valid else "Could not read save"
                saved = self._date_text(record.saved_at)
                profile = record.profile_name
                current_row = row
            elif record.valid:
                status = "Occupied"
                mission = record.mission_name
                saved = self._date_text(record.saved_at)
                profile = record.profile_name
            else:
                status = "Unreadable"
                mission = "Could not read save"
                saved = "—"
                profile = record.profile_name

            if fallback_row < 0 and not is_current:
                fallback_row = row

            values = (f"Slot {slot}", status, mission, saved, profile)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, slot)
                item.setToolTip(record.error if record is not None and not record.valid else str(destination))
                self.table.setItem(row, column, item)

        row_to_select = preferred_row if preferred_row >= 0 else fallback_row
        if row_to_select < 0:
            row_to_select = current_row if current_row >= 0 else 0
        self.table.selectRow(row_to_select)
        self._selection_changed()

    def _selection_changed(self) -> None:
        self.save_button.setEnabled(self.table.currentRow() >= 0)

    def _double_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(STANDARD_SAVE_SLOTS):
            self.table.selectRow(row)
            self._accept_selection()

    def _accept_selection(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(STANDARD_SAVE_SLOTS):
            return
        slot = STANDARD_SAVE_SLOTS[row]
        self.selected_slot = slot
        self.selected_record = self._records_by_slot.get(slot)
        self.selected_path = save_path_for_slot(self.folder, slot, self._records)
        self.accept()


class BetaNoticeDialog(QDialog):
    """One-time beta notice shown on first launch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} — Beta")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        message = QLabel(f"{APP_NAME} is beta software. Keep a separate copy of any important saves.")
        message.setWordWrap(True)
        layout.addWidget(message)

        backup = QLabel("A timestamped backup is created automatically whenever an existing save is overwritten.")
        backup.setWordWrap(True)
        layout.addWidget(backup)

        recovery = QLabel("Use File > Restore Save… to restore an automatic backup.")
        recovery.setWordWrap(True)
        layout.addWidget(recovery)

        issues = QLabel(
            f'Found a problem? Report it on <a href="https://{GITHUB_ISSUES}">GitHub Issues</a>.'
        )
        issues.setWordWrap(True)
        issues.setOpenExternalLinks(True)
        issues.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(issues)

        buttons = QDialogButtonBox()
        issues_button = buttons.addButton("Open GitHub Issues", QDialogButtonBox.ButtonRole.ActionRole)
        continue_button = buttons.addButton("Continue", QDialogButtonBox.ButtonRole.AcceptRole)
        continue_button.setDefault(True)
        issues_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(f"https://{GITHUB_ISSUES}"))
        )
        continue_button.clicked.connect(self.accept)
        layout.addWidget(buttons)


class RestoreSaveDialog(QDialog):
    """Choose one of the automatic backups for a save."""

    def __init__(self, target: Path, parent=None):
        super().__init__(parent)
        self.target = Path(target)
        self.selected_backup: Path | None = None
        self.setWindowTitle("Restore Save")
        self.setModal(True)
        self.resize(860, 430)
        self.setMinimumSize(720, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Restore a previous save")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        target_label = QLabel(f"Save: {self.target}")
        target_label.setObjectName("muted")
        target_label.setWordWrap(True)
        target_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(target_label)

        note = QLabel(
            "Choose a backup to restore. The current save will be backed up again before it is replaced."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Backup", "Created", "Modified", "Size"))
        self.table.horizontalHeaderItem(1).setToolTip("When VC Save Toolkit created the backup. Local time.")
        self.table.horizontalHeaderItem(2).setToolTip("The save file's modified time preserved in the backup. Local time.")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("muted")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        buttons = QDialogButtonBox()
        folder_button = buttons.addButton("Open Backup Folder", QDialogButtonBox.ButtonRole.ActionRole)
        self.restore_button = buttons.addButton("Restore Selected Backup", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_button = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        folder_button.clicked.connect(self._open_backup_folder)
        self.restore_button.clicked.connect(self._accept_selected)
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(buttons)

        self._populate()
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(lambda *_: self._accept_selected())
        self._selection_changed()

    def _populate(self) -> None:
        backups = list_backups(self.target)
        self.table.setRowCount(len(backups))
        for row, backup in enumerate(backups):
            stat = backup.stat()
            created_at = backup_created_at(backup)
            created = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "Unknown"
            modified = datetime.fromtimestamp(stat.st_mtime).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            size = f"{stat.st_size / 1024:.1f} KB"
            name_item = QTableWidgetItem(backup.name)
            name_item.setData(Qt.ItemDataRole.UserRole, str(backup))
            name_item.setToolTip(str(backup))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(created))
            self.table.setItem(row, 2, QTableWidgetItem(modified))
            self.table.setItem(row, 3, QTableWidgetItem(size))
        folder = backup_folder_for(self.target)
        self.empty_label.setToolTip(str(folder))
        if backups:
            self.table.selectRow(0)
            count = len(backups)
            self.empty_label.setText("1 backup found." if count == 1 else f"{count} backups found.")
        else:
            self.empty_label.setText(f"No backups were found for {self.target.name}.")

    def _selection_changed(self) -> None:
        self.restore_button.setEnabled(bool(self.table.selectionModel().selectedRows()))

    def _accept_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        self.selected_backup = Path(item.data(Qt.ItemDataRole.UserRole))
        self.accept()

    def _open_backup_folder(self) -> None:
        folder = backup_folder_for(self.target)
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


@dataclass
class LoadedSaveData:
    path: Path
    save: SaveFile
    player: PlayerValues | None
    world: WorldValues | None
    weapons: list[WeaponValues] | None
    pickups: list[PickupRecord] | None
    generators: list[CarGeneratorRecord] | None
    stored_cars: list[StoredCarRecord] | None
    gangs: list[GangRecord] | None
    stats: list[tuple[str, object, str]] | None


class SaveLoadThread(QThread):
    """Parse and decode a save without blocking the GUI event loop."""

    progress = Signal(int, str)
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self) -> None:
        started = time.perf_counter()
        try:
            LOGGER.info("Opening save: %s", self.path)
            self.progress.emit(5, "Reading file and validating checksum…")
            save = SaveFile.load(self.path)
            self.progress.emit(20, f"Detected {save.profile.name}")
            if not save.profile.editable:
                LOGGER.warning("Opened recognized but read-only layout: %s", save.profile.key)
                self.progress.emit(88, "Preparing file layout…")
                self.loaded.emit(LoadedSaveData(
                    self.path, save, None, None, None, None, None, None, None, None
                ))
                return
            player = save.player()
            world = save.world()
            weapons = save.weapons()
            self.progress.emit(38, "Reading player, world, and weapons…")
            pickups = save.pickups()
            self.progress.emit(55, "Reading pickup records…")
            generators = save.car_generators()
            stored_cars = save.stored_cars()
            self.progress.emit(70, "Reading persistent vehicles and garages…")
            gangs = save.gangs()
            self.progress.emit(80, "Reading gang data…")
            stats = save.stats()
            self.progress.emit(88, "Reading statistics and progress…")
            payload = LoadedSaveData(
                self.path, save, player, world, weapons, pickups, generators,
                stored_cars, gangs, stats,
            )
            LOGGER.info(
                "Parsed save in %.3fs | profile=%s | bytes=%d | pickups=%d | generators=%d | cars=%d | stats=%d",
                time.perf_counter() - started, save.profile.key, len(save.raw), len(pickups),
                len(generators), len(stored_cars), len(stats),
            )
            self.loaded.emit(payload)
        except Exception as error:
            LOGGER.exception("Failed to open save: %s", self.path)
            self.failed.emit(str(error))


class ChoiceDelegate(QStyledItemDelegate):
    """Combo-box editor for numeric choices."""

    def __init__(self, options: list[tuple[str, int]], parent=None, display_labels: dict[int, str] | None = None,
                 tooltip_labels: dict[int, str] | None = None):
        super().__init__(parent)
        self.options = options
        self.display_labels = display_labels or {}
        self.tooltip_labels = tooltip_labels or {}

    def paint(self, painter, option, index):  # Qt API name.
        clipped = QStyleOptionViewItem(option)
        clipped.rect = option.rect.adjusted(0, 0, -16, 0)
        super().paint(painter, clipped, index)
        if index.flags() & Qt.ItemFlag.ItemIsEditable:
            painter.save()
            painter.setPen(option.palette.color(QPalette.ColorRole.PlaceholderText))
            painter.drawText(option.rect.adjusted(0, 0, -5, 0),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "▾")
            painter.restore()

    def createEditor(self, parent, option, index):  # Qt API name.
        editor = QComboBox(parent)
        for label, value in self.options:
            editor.addItem(label, value)
        configure_combo_popup(editor, len(self.options))
        set_combo_id_tooltip(editor)
        editor.currentIndexChanged.connect(lambda _=0: set_combo_id_tooltip(editor))
        def commit_and_close(*_):
            self.commitData.emit(editor)
            self.closeEditor.emit(editor)
        editor.activated.connect(commit_and_close)
        return editor

    def setEditorData(self, editor, index):  # Qt API name.
        value = index.data(Qt.ItemDataRole.UserRole)
        found = editor.findData(value)
        if found < 0:
            editor.insertItem(0, index.data(Qt.ItemDataRole.DisplayRole), value)
            found = 0
        editor.setCurrentIndex(found)

    def setModelData(self, editor, model, index):  # Qt API name.
        value = editor.currentData()
        display = self.display_labels.get(int(value), editor.currentText()) if value is not None else editor.currentText()
        model.setData(index, display, Qt.ItemDataRole.DisplayRole)
        model.setData(index, value, Qt.ItemDataRole.UserRole)
        if value is None:
            tooltip = editor.currentText()
        else:
            numeric = int(value)
            tooltip = self.tooltip_labels.get(numeric, f"ID {numeric}")
        model.setData(index, tooltip, Qt.ItemDataRole.ToolTipRole)


class PickupModelDelegate(ChoiceDelegate):
    """Pickup model editor with custom int16 ID support."""

    def createEditor(self, parent, option, index):  # Qt API name.
        editor = QComboBox(parent)
        editor.setEditable(True)
        editor.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for label, value in self.options:
            editor.addItem(label, value)
        configure_combo_popup(editor, len(self.options))
        set_combo_id_tooltip(editor)
        editor.currentIndexChanged.connect(lambda _=0: set_combo_id_tooltip(editor))
        validator = QIntValidator(-32768, 32767, editor.lineEdit())
        editor.lineEdit().setValidator(validator)
        editor.lineEdit().setPlaceholderText("Choose a model or type an ID")
        return editor

    def setEditorData(self, editor, index):  # Qt API name.
        value = int(index.data(Qt.ItemDataRole.UserRole))
        found = editor.findData(value)
        if found >= 0:
            editor.setCurrentIndex(found)
        else:
            editor.setEditText(str(value))

    def setModelData(self, editor, model, index):  # Qt API name.
        value = editor.currentData()
        if value is None or editor.currentText().strip() != editor.itemText(editor.currentIndex()).strip():
            text = editor.currentText().strip()
            try:
                value = parse_int(text, -32768, 32767)
            except ValueError:
                return
        value = int(value)
        display = choice_label(pickup_model_name(value), value)
        model.setData(index, display, Qt.ItemDataRole.DisplayRole)
        model.setData(index, value, Qt.ItemDataRole.UserRole)
        model.setData(index, f"ID {value}", Qt.ItemDataRole.ToolTipRole)


STAT_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 20
ORIGINAL_TOOLTIP_ROLE = int(Qt.ItemDataRole.UserRole) + 21
EXACT_VALUE_ROLE = int(Qt.ItemDataRole.UserRole) + 22
ORIGINAL_VALUE_ROLE = int(Qt.ItemDataRole.UserRole) + 23
GARAGE_RECORD_INDEX_ROLE = int(Qt.ItemDataRole.UserRole) + 24


class NumberDelegate(QStyledItemDelegate):
    """Numeric table-cell editor."""

    def __init__(self, kind: str, minimum: int | None = None, maximum: int | None = None, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.minimum = minimum
        self.maximum = maximum

    def createEditor(self, parent, option, index):  # Qt API name.
        editor = QLineEdit(parent)
        if self.kind == "float":
            validator = QDoubleValidator(-3.4e38, 3.4e38, 9, editor)
            validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
            editor.setValidator(validator)
        elif self.kind == "uint32":
            editor.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,10}"), editor))
        else:
            low = -2147483648 if self.minimum is None else max(-2147483648, int(self.minimum))
            high = 2147483647 if self.maximum is None else min(2147483647, int(self.maximum))
            editor.setValidator(QIntValidator(low, high, editor))
        return editor

    def setEditorData(self, editor, index):  # Qt API name.
        exact = index.data(EXACT_VALUE_ROLE)
        editor.setText(str(index.data(Qt.ItemDataRole.DisplayRole) if exact is None else exact))
        editor.selectAll()

    def setModelData(self, editor, model, index):  # Qt API name.
        text = editor.text().strip()
        if self.kind == "float":
            value = float(text)
            model.setData(index, value, EXACT_VALUE_ROLE)
            model.setData(index, f"{value:.3f}", Qt.ItemDataRole.DisplayRole)
        else:
            value = int(text)
            model.setData(index, value, EXACT_VALUE_ROLE)
            model.setData(index, str(value), Qt.ItemDataRole.DisplayRole)


class StatsValueDelegate(QStyledItemDelegate):
    """Type-aware stats editor."""

    def createEditor(self, parent, option, index):  # Qt API name.
        kind = index.data(STAT_KIND_ROLE)
        if kind == "bool":
            editor = QComboBox(parent)
            editor.addItem("No", 0)
            editor.addItem("Yes", 1)
            return editor
        editor = QLineEdit(parent)
        if kind == "int":
            editor.setValidator(QIntValidator(-2147483648, 2147483647, editor))
        elif kind == "float":
            validator = QDoubleValidator(-3.4e38, 3.4e38, 9, editor)
            validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
            editor.setValidator(validator)
        return editor

    def setEditorData(self, editor, index):  # Qt API name.
        kind = index.data(STAT_KIND_ROLE)
        if kind == "bool":
            text = str(index.data(Qt.ItemDataRole.DisplayRole) or "").strip().lower()
            value = 1 if text in {"1", "yes", "true", "on"} else 0
            editor.setCurrentIndex(editor.findData(value))
        else:
            exact = index.data(EXACT_VALUE_ROLE)
            editor.setText(str(index.data(Qt.ItemDataRole.DisplayRole) if exact is None else exact))
            editor.selectAll()

    def setModelData(self, editor, model, index):  # Qt API name.
        kind = index.data(STAT_KIND_ROLE)
        if kind == "bool":
            model.setData(index, editor.currentText(), Qt.ItemDataRole.DisplayRole)
        elif kind == "float":
            value = float(editor.text().strip())
            model.setData(index, value, EXACT_VALUE_ROLE)
            model.setData(index, f"{value:.3f}", Qt.ItemDataRole.DisplayRole)
        elif kind == "int":
            value = int(editor.text().strip())
            model.setData(index, value, EXACT_VALUE_ROLE)
            model.setData(index, str(value), Qt.ItemDataRole.DisplayRole)
        else:
            model.setData(index, editor.text().strip(), Qt.ItemDataRole.DisplayRole)


@dataclass
class ValidationIssue:
    table: QTableWidget
    row: int
    column: int
    label: str
    message: str


def spin(minimum: int, maximum: int) -> QSpinBox:
    widget = QSpinBox()
    widget.setRange(minimum, maximum)
    widget.setMinimumWidth(150)
    widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
    return widget


def decimal_spin(minimum: float, maximum: float, decimals: int = 3) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setMinimumWidth(150)
    widget.setDecimals(decimals)
    widget.setSingleStep(1.0)
    widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
    return widget


def page_header(title: str, subtitle: str = "") -> tuple[QLabel, QLabel | None]:
    heading = QLabel(title)
    heading.setObjectName("pageTitle")
    if not subtitle:
        return heading, None
    description = QLabel(subtitle)
    description.setObjectName("pageSubtitle")
    description.setWordWrap(True)
    return heading, description


class MainWindow(QMainWindow):
    def __init__(self, initial_path: str | None = None, log_path: Path | None = None):
        super().__init__()
        self.save: SaveFile | None = None
        self.current_path: Path | None = None
        self.ui_dirty = False
        self._loading_form = False
        self._load_thread: SaveLoadThread | None = None
        self._initial_path = initial_path
        self._opened_raw: bytes | None = None
        self._ped_cheat_status = None
        self.log_path = log_path
        self.current_theme = "dark"
        self.current_appearance = "dark"
        self._empty_icon = QIcon()
        self.settings = QSettings(ORGANIZATION_NAME, APP_NAME)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(application_icon_path())))
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)
        self._build_ui()
        self._build_menu()
        self._connect_dirty_signals()
        self._connect_system_appearance()
        self._set_loaded(False)
        saved_appearance = str(self.settings.value("appearance", "dark"))
        self.apply_appearance(saved_appearance, initial=True)
        geometry = self.settings.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value("splitter_state")
        if splitter_state:
            self.body_splitter.restoreState(splitter_state)
        self.sidebar.setVisible(True)
        self._restore_table_layouts()
        QTimer.singleShot(0, self._show_beta_notice_if_needed)
        if initial_path:
            QTimer.singleShot(0, lambda: self.open_path(Path(initial_path)))

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(56)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 7, 16, 7)
        top_layout.setSpacing(10)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand = QLabel(APP_NAME)
        brand.setObjectName("brandTitle")
        self.file_state = QLabel("No save open")
        self.file_state.setObjectName("fileState")
        self.file_state.setMinimumWidth(120)
        self.file_state.setMaximumWidth(430)
        self.file_state.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.file_state.setAccessibleName("Current save status")
        brand_text.addWidget(brand)
        brand_text.addWidget(self.file_state)
        top_layout.addLayout(brand_text, 1)

        self.state_badge = QLabel("No save")
        self.state_badge.setObjectName("stateBadge")
        self.state_badge.setProperty("state", "idle")
        self.state_badge.setMinimumWidth(142)
        self.state_badge.setMaximumWidth(142)
        self.state_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(self.state_badge)

        self.open_button = QPushButton("Save Selector…")
        self.open_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.open_button.setAccessibleName("Open the Vice City Save Selector")
        self.open_button.clicked.connect(self.choose_open)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("primary")
        self.save_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.save_button.setAccessibleName("Save current Vice City save")
        self.save_button.clicked.connect(self.save_current)
        self.save_slot_button = QPushButton("Save to Slot…")
        self.save_slot_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.save_slot_button.setAccessibleName("Save into another Vice City save slot")
        self.save_slot_button.clicked.connect(self.save_to_slot)
        self.save_as_button = QPushButton("Save As…")
        self.save_as_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.save_as_button.setAccessibleName("Save Vice City save as another file")
        self.save_as_button.clicked.connect(self.choose_save)
        top_layout.addWidget(self.open_button)
        top_layout.addWidget(self.save_button)
        top_layout.addWidget(self.save_slot_button)
        top_layout.addWidget(self.save_as_button)
        root_layout.addWidget(top_bar)

        self.format_strip = QFrame()
        self.format_strip.setObjectName("formatStrip")
        self.format_strip.setFixedHeight(44)
        format_layout = QHBoxLayout(self.format_strip)
        format_layout.setContentsMargins(16, 6, 16, 6)
        format_layout.setSpacing(9)

        source_caption = QLabel("Source:")
        source_caption.setObjectName("contextLabel")
        format_layout.addWidget(source_caption)
        self.source_format_value = QLabel("No save open")
        self.source_format_value.setObjectName("sourceFormatPill")
        self.source_format_value.setMinimumWidth(150)
        self.source_format_value.setMaximumWidth(280)
        format_layout.addWidget(self.source_format_value)

        separator = QLabel("•")
        separator.setObjectName("muted")
        format_layout.addWidget(separator)
        output_caption = QLabel("Output:")
        output_caption.setObjectName("contextLabel")
        format_layout.addWidget(output_caption)
        self.output_format_combo = QComboBox()
        self.output_format_combo.setObjectName("formatCombo")
        self.output_format_combo.setMinimumWidth(210)
        self.output_format_combo.setMaximumWidth(320)
        self.output_format_combo.setFixedHeight(32)
        self.output_format_combo.setPlaceholderText("Choose output format")
        self.output_format_combo.setAccessibleName("Output save format")
        self.output_format_combo.setAccessibleDescription("Format used by Save, Save As, and Save to Slot.")
        output_caption.setBuddy(self.output_format_combo)
        format_tooltips = {
            "gta-vc-pc": "Original 32-bit retail PC format.",
            "gta-vc-steam": "Steam PC format with its Block 0 marker.",
            "vc-pc-extended": "reVC-compatible 32-bit format.",
            "vice-city-vr": "Vice City VR 64-bit format.",
        }
        for profile in sorted(SaveFile.export_profiles(), key=lambda item: item.name.casefold()):
            self.output_format_combo.addItem(profile.name, profile.key)
            index = self.output_format_combo.count() - 1
            self.output_format_combo.setItemData(
                index, format_tooltips.get(profile.key, profile.detail), Qt.ItemDataRole.ToolTipRole
            )
        self.output_format_combo.currentIndexChanged.connect(self._output_format_changed)
        format_layout.addWidget(self.output_format_combo)

        separator2 = QLabel("•")
        separator2.setObjectName("muted")
        format_layout.addWidget(separator2)
        self.integrity_context = QLabel("No save open")
        self.integrity_context.setObjectName("integrityIdle")
        self.integrity_context.setAccessibleName("Save integrity status")
        format_layout.addWidget(self.integrity_context)
        format_layout.addStretch()
        root_layout.addWidget(self.format_strip)

        self.conversion_notice = CompactNotice()
        self.conversion_notice.hide()
        root_layout.addWidget(self.conversion_notice)

        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body_splitter.setChildrenCollapsible(False)
        self.body_splitter.setHandleWidth(6)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(185)
        self.sidebar.setMaximumWidth(275)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(10, 14, 10, 12)
        side_layout.setSpacing(7)
        nav_label = QLabel("SECTIONS")
        nav_label.setObjectName("sidebarLabel")
        side_layout.addWidget(nav_label)

        self.nav = QListWidget()
        self.nav.setObjectName("navigation")
        self.nav.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.nav.setAccessibleName("Save workspace")
        self.nav.setAccessibleDescription("Arrow keys or Ctrl+1 through Ctrl+8 switch sections.")
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        navigation = (
            "Overview", "Player", "World", "Weapons", "Pickups",
            "Vehicles", "Gangs", "Stats & progress",
        )
        for label in navigation:
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(185, 36))
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        side_layout.addWidget(self.nav, 1)

        build_label = QLabel(f"v{APP_VERSION}")
        build_label.setObjectName("muted")
        build_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side_layout.addWidget(build_label)
        self.body_splitter.addWidget(self.sidebar)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("workspace")
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._summary_tab(), "Summary")
        self.tabs.addTab(self._player_tab(), "Player")
        self.tabs.addTab(self._world_tab(), "World")
        self.tabs.addTab(self._weapons_tab(), "Weapons")
        self.tabs.addTab(self._pickups_tab(), "Pickups")
        self.tabs.addTab(self._vehicles_tab(), "Vehicles")
        self.tabs.addTab(self._gangs_tab(), "Gangs")
        self.tabs.addTab(self._stats_tab(), "Stats & progress")
        self.nav.currentRowChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self._sync_navigation)
        self.tabs.currentChanged.connect(lambda index: self.settings.setValue("last_page", index))
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.addWidget(self.tabs)
        self.processing_page = self._processing_page()
        self.workspace_stack.addWidget(self.processing_page)
        self.body_splitter.addWidget(self.workspace_stack)
        self.body_splitter.setStretchFactor(0, 0)
        self.body_splitter.setStretchFactor(1, 1)
        self.body_splitter.setSizes([210, 970])
        root_layout.addWidget(self.body_splitter, 1)

        self.setCentralWidget(root)
        status = QStatusBar()
        status.setSizeGripEnabled(False)
        status.setAccessibleName("Application status")
        self.setStatusBar(status)

    def _processing_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(70, 70, 70, 70)
        layout.addStretch(2)
        card = QFrame()
        card.setObjectName("card")
        card.setMaximumWidth(650)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(12)
        self.processing_title = QLabel("Opening save…")
        self.processing_title.setObjectName("pageTitle")
        self.processing_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.processing_file = QLabel("")
        self.processing_file.setObjectName("muted")
        self.processing_file.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.processing_file.setWordWrap(True)
        self.processing_detail = QLabel("Preparing…")
        self.processing_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.processing_detail.setWordWrap(True)
        self.processing_bar = QProgressBar()
        self.processing_bar.setAccessibleName("Save opening progress")
        self.processing_bar.setRange(0, 100)
        self.processing_bar.setValue(0)
        self.processing_bar.setTextVisible(True)
        card_layout.addWidget(self.processing_title)
        card_layout.addWidget(self.processing_file)
        card_layout.addSpacing(4)
        card_layout.addWidget(self.processing_bar)
        card_layout.addWidget(self.processing_detail)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(card)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch(3)
        return page

    def _summary_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("overviewScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAccessibleName("Overview")

        page = QWidget()
        page.setObjectName("overviewContent")
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(page)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(12)

        heading, _ = page_header("Overview")
        layout.addWidget(heading)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        details = QGroupBox("Save details")
        details.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        form = QFormLayout(details)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)
        self.summary_path = QLabel("No save open")
        self.summary_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary_path.setWordWrap(True)
        self.summary_name = QLabel("—")
        self.summary_time = QLabel("—")
        self.summary_type = QLabel("—")
        self.summary_profile = QLabel("—")
        self.summary_profile.setWordWrap(True)
        self.summary_checksum = QLabel("—")
        self.summary_checksum.setObjectName("statusGood")
        form.addRow("File", self.summary_path)
        form.addRow("Save name", self.summary_name)
        form.addRow("Saved", self.summary_time)
        form.addRow("Save type", self.summary_type)
        form.addRow("Format", self.summary_profile)
        form.addRow("Integrity", self.summary_checksum)
        columns.addWidget(details, 3)

        save_box = QGroupBox("Save")
        save_box.setMinimumWidth(300)
        save_layout = QVBoxLayout(save_box)
        save_layout.setSpacing(8)
        self.summary_output_format = QLabel("No output format selected")
        self.summary_output_format.setObjectName("statusGood")
        self.summary_output_format.setWordWrap(True)
        self.export_help = QLabel("Open a save to begin.")
        self.export_help.setObjectName("muted")
        self.export_help.setWordWrap(True)
        self.summary_action_button = QPushButton("Save Selector…")
        self.summary_action_button.setObjectName("primary")
        self.summary_action_button.clicked.connect(self._summary_primary_action)
        save_layout.addWidget(self.summary_output_format)
        save_layout.addWidget(self.export_help)
        save_layout.addStretch()
        save_layout.addWidget(self.summary_action_button)
        columns.addWidget(save_box, 2)
        layout.addLayout(columns)

        self.cheat_box = QGroupBox("Persistent cheat effect")
        cheat_layout = QVBoxLayout(self.cheat_box)
        cheat_layout.setSpacing(8)
        self.cheat_name = QLabel("")
        self.cheat_name.setObjectName("warningText")
        self.cheat_name.setWordWrap(True)
        self.cheat_detail = QLabel("")
        self.cheat_detail.setWordWrap(True)
        self.cheat_counter = QLabel("")
        self.cheat_counter.setObjectName("muted")
        cheat_buttons = QHBoxLayout()
        self.cheat_repair_button = QPushButton("Repair…")
        self.cheat_repair_button.setObjectName("primary")
        self.cheat_repair_button.clicked.connect(self._repair_persistent_ped_cheat)
        self.cheat_info_button = QPushButton("Details…")
        self.cheat_info_button.clicked.connect(self._show_persistent_ped_cheat_info)
        cheat_buttons.addWidget(self.cheat_repair_button)
        cheat_buttons.addWidget(self.cheat_info_button)
        cheat_buttons.addStretch()
        cheat_layout.addWidget(self.cheat_name)
        cheat_layout.addWidget(self.cheat_detail)
        cheat_layout.addWidget(self.cheat_counter)
        cheat_layout.addLayout(cheat_buttons)
        self.cheat_box.hide()
        layout.addWidget(self.cheat_box)

        self.conversion_box = QGroupBox("Read-only layout")
        conversion_layout = QVBoxLayout(self.conversion_box)
        warning = QLabel("This layout is read-only.")
        warning.setObjectName("warningText")
        warning.setWordWrap(True)
        conversion_layout.addWidget(warning)
        self.conversion_box.hide()
        layout.addWidget(self.conversion_box)

        self.file_layout_toggle = QPushButton("▸ File Layout")
        self.file_layout_toggle.setObjectName("sectionToggle")
        self.file_layout_toggle.setCheckable(True)
        self.file_layout_toggle.toggled.connect(self._toggle_file_layout)
        layout.addWidget(self.file_layout_toggle)

        self.file_layout_box = QGroupBox("File Layout")
        file_layout = QVBoxLayout(self.file_layout_box)
        self.block_table = QTableWidget(0, 4)
        self.block_table.setAccessibleName("Save file layout table")
        self.block_table.setToolTip("Outer size includes the block wrapper; inner size is the payload.")
        self.block_table.setHorizontalHeaderLabels(("Block", "Offset", "Outer size", "Inner size"))
        self.block_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.block_table.setMinimumHeight(300)
        self.block_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._polish_table(self.block_table)
        file_layout.addWidget(self.block_table)
        self.file_layout_box.hide()
        layout.addWidget(self.file_layout_box)
        layout.addStretch()

        scroll.setWidget(page)
        return scroll

    def _toggle_file_layout(self, checked: bool) -> None:
        self.file_layout_toggle.setText("▾ File Layout" if checked else "▸ File Layout")
        self.file_layout_box.setVisible(bool(checked))

    def _refresh_persistent_ped_cheat(self) -> None:
        if not self.save:
            self._ped_cheat_status = None
            self.cheat_box.hide()
            return
        try:
            status = self.save.detect_persistent_ped_cheats()
        except SaveFormatError:
            self._ped_cheat_status = None
            self.cheat_box.hide()
            return

        self._ped_cheat_status = status
        if status.state == PedCheatState.NONE:
            self.cheat_box.hide()
            return

        if status.state == PedCheatState.FIGHTFIGHTFIGHT:
            self.cheat_name.setText("Pedestrian Mayhem (FIGHTFIGHTFIGHT)")
            self.cheat_detail.setText("The saved pedestrian threat table was replaced by the mayhem cheat.")
            self.cheat_repair_button.setText("Restore Standard Behaviour…")
            self.cheat_repair_button.setVisible(True)
            self.cheat_repair_button.setEnabled(bool(self.save.profile.editable))
        elif status.state == PedCheatState.NOBODYLIKESME:
            self.cheat_name.setText("Pedestrians Attack Player (NOBODYLIKESME)")
            self.cheat_detail.setText("The player-threat flag is set across the normal pedestrian types.")
            self.cheat_repair_button.setText("Repair…")
            self.cheat_repair_button.setVisible(True)
            self.cheat_repair_button.setEnabled(bool(self.save.profile.editable))
        else:
            self.cheat_name.setText("Non-standard pedestrian hostility")
            self.cheat_detail.setText(
                "All normal pedestrian types are hostile to the player, but the pattern does not match a known stock cheat. No automatic repair is available."
            )
            self.cheat_repair_button.setVisible(False)

        self.cheat_counter.setText(f"Cheat-use counter: {status.cheated_count}")
        self.cheat_box.show()

    def _show_persistent_ped_cheat_info(self) -> None:
        status = self._ped_cheat_status
        if not status:
            return
        if status.state == PedCheatState.FIGHTFIGHTFIGHT:
            text = (
                "FIGHTFIGHTFIGHT overwrites the saved pedestrian relationship table. "
                "Repair restores standard Vice City threat relationships. "
                "Once mayhem is active, the saved table cannot show whether NOBODYLIKESME was used beforehand."
            )
        elif status.state == PedCheatState.NOBODYLIKESME:
            text = (
                "NOBODYLIKESME adds the player-threat bit to each affected pedestrian type. "
                "Repair removes that bit and leaves the other threat bits unchanged. "
                "A mission or mod that deliberately used the same bit cannot be distinguished from the cheat."
            )
        else:
            text = (
                "This save has global player hostility but does not exactly match a known stock Vice City cheat pattern. "
                "VC Save Toolkit will preserve it rather than guess at a repair."
            )
        QMessageBox.information(
            self, "Persistent pedestrian behaviour",
            f"{text}\n\nCheat-use counter: {status.cheated_count}. The counter is not changed by repair."
        )

    def _repair_persistent_ped_cheat(self) -> None:
        if not self.save or not self.save.profile.editable:
            return
        status = self.save.detect_persistent_ped_cheats()
        if not status.repairable:
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        if status.state == PedCheatState.FIGHTFIGHTFIGHT:
            box.setWindowTitle("Restore pedestrian behaviour?")
            box.setText("Restore standard Vice City pedestrian relationships?")
            box.setInformativeText(
                "This restores the stock pedestrian threat table. Any custom relationships that existed before the cheat cannot be recovered."
            )
            repair_label = "Restore Standard Behaviour"
        else:
            box.setWindowTitle("Repair pedestrian hostility?")
            box.setText("Remove the persistent NOBODYLIKESME effect?")
            box.setInformativeText(
                "This clears the player-threat bit and leaves the other threat flags unchanged."
            )
            repair_label = "Repair"
        repair_button = box.addButton(repair_label, QMessageBox.ButtonRole.AcceptRole)
        cancel_button = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel_button)
        box.exec()
        if box.clickedButton() is not repair_button:
            return

        try:
            repaired = self.save.repair_persistent_ped_cheat()
            SaveFile(self.save.raw, self.current_path)
        except SaveFormatError as error:
            QMessageBox.critical(self, "Repair failed", str(error))
            return

        self.ui_dirty = True
        self.summary_checksum.setText(f"Valid · {self.save.stored_checksum}")
        self._refresh_persistent_ped_cheat()
        self._update_window_state()
        label = "Pedestrian Mayhem" if repaired == PedCheatState.FIGHTFIGHTFIGHT else "Pedestrians Attack Player"
        self.statusBar().showMessage(f"{label} repaired. Save to write the change.", 6000)

    def _player_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)
        heading, _ = page_header("Player")
        layout.addWidget(heading)
        basics = QGroupBox("Vitals and money")
        form = QFormLayout(basics)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.money = spin(-1_000_000_000, 999_999_999)
        if hasattr(self.money, "setGroupSeparatorShown"):
            self.money.setGroupSeparatorShown(True)
        self.health = decimal_spin(0, 1000, 2)
        self.armour = decimal_spin(0, 1000, 2)
        self.max_health = spin(0, 255)
        self.max_armour = spin(0, 255)
        for label, widget in (("Money", self.money), ("Health", self.health),
                              ("Armour", self.armour), ("Maximum health", self.max_health),
                              ("Maximum armour", self.max_armour)):
            form.addRow(label, widget)
        layout.addWidget(basics)
        abilities = QGroupBox("Abilities")
        ability_layout = QGridLayout(abilities)
        self.ability_boxes = []
        for index, text in enumerate(("Infinite sprint", "Fast reload", "Fireproof",
                                      "Free hospital visits", "Free jail visits", "Drive-by allowed")):
            box = QCheckBox(text)
            self.ability_boxes.append(box)
            ability_layout.addWidget(box, index // 2, index % 2)
        layout.addWidget(abilities)
        layout.addStretch()
        return page

    def _world_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)
        heading, _ = page_header("World")
        layout.addWidget(heading)
        position = QGroupBox("Player position")
        position_form = QFormLayout(position)
        position_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.pos_x = decimal_spin(-100000, 100000)
        self.pos_y = decimal_spin(-100000, 100000)
        self.pos_z = decimal_spin(-100000, 100000)
        position_form.addRow("X coordinate", self.pos_x)
        position_form.addRow("Y coordinate", self.pos_y)
        position_form.addRow("Z coordinate", self.pos_z)
        layout.addWidget(position)
        world = QGroupBox("Time and weather")
        world_form = QFormLayout(world)
        world_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.hour = spin(0, 23)
        self.minute = spin(0, 59)
        self.old_weather = self._weather_combo(False)
        self.new_weather = self._weather_combo(False)
        self.forced_weather = self._weather_combo(True)
        self.forced_weather.setToolTip("-1 = not forced")
        for label, widget in (("Hour", self.hour), ("Minute", self.minute),
                              ("Previous weather", self.old_weather),
                              ("Current weather", self.new_weather),
                              ("Forced weather", self.forced_weather)):
            world_form.addRow(label, widget)
        layout.addWidget(world)
        layout.addStretch()
        return page

    def _weather_combo(self, allow_random: bool) -> QComboBox:
        combo = QComboBox()
        items = [
            (choice_label(name, value), value)
            for value, name in WEATHER_NAMES
            if value != -1 or allow_random
        ]
        for label, value in alphabetical_choices(items):
            combo.addItem(label, value)
        configure_combo_popup(combo, combo.count())
        set_combo_id_tooltip(combo)
        combo.currentIndexChanged.connect(lambda _=0: set_combo_id_tooltip(combo))
        return combo

    def _weapons_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(12)
        heading, _ = page_header("Weapons")
        layout.addWidget(heading)
        self.weapon_slot_indices = tuple(range(1, 10))
        self.weapon_table = QTableWidget(len(self.weapon_slot_indices), 3)
        self.weapon_table.setHorizontalHeaderLabels(("Weapon", "Clip ammo", "Total ammo"))
        self.weapon_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._polish_table(self.weapon_table, show_row_header=True)
        self.weapon_combos = []
        for row, slot_index in enumerate(self.weapon_slot_indices):
            self.weapon_table.setVerticalHeaderItem(row, QTableWidgetItem(SLOT_NAMES[slot_index]))
            combo = QComboBox()
            for label, weapon_type in weapon_choices(SLOT_TYPES[slot_index]):
                combo.addItem(label, weapon_type)
            configure_combo_popup(combo, combo.count())
            set_combo_id_tooltip(combo)
            combo.currentIndexChanged.connect(lambda _=0, c=combo: set_combo_id_tooltip(c))
            combo.currentIndexChanged.connect(lambda _=0, r=row: self._update_weapon_row_state(r))
            self.weapon_table.setCellWidget(row, 0, combo)
            self.weapon_combos.append(combo)
            clip = spin(0, 99999)
            total = spin(0, 999999)
            self.weapon_table.setCellWidget(row, 1, clip)
            self.weapon_table.setCellWidget(row, 2, total)
        layout.addWidget(self.weapon_table)
        return page

    def _update_weapon_row_state(self, row: int) -> None:
        if row < 0 or row >= len(self.weapon_combos):
            return
        enabled = int(self.weapon_combos[row].currentData() or 0) != 0
        self.weapon_table.cellWidget(row, 1).setEnabled(enabled)
        self.weapon_table.cellWidget(row, 2).setEnabled(enabled)

    def _pickups_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(10)
        heading, subtitle = page_header("Pickups", "336 pickup slots · empty slots hidden by default.")
        layout.addWidget(heading)
        if subtitle:
            layout.addWidget(subtitle)
        controls = QHBoxLayout()
        filter_label = QLabel("Show")
        self.pickup_filter = QComboBox()
        self.pickup_filter.addItem("Active pickups", -1)
        self.pickup_filter.addItem("All 336 slots (including empty)", -2)
        pickup_filter_types = sorted(
            ((name, value) for value, name in enumerate(PICKUP_TYPES[1:], 1)),
            key=lambda item: (item[0].casefold(), item[1]),
        )
        for name, value in pickup_filter_types:
            self.pickup_filter.addItem(f"{name} - ID {value}", value)
            index = self.pickup_filter.count() - 1
            self.pickup_filter.setItemData(index, f"ID {value}", Qt.ItemDataRole.ToolTipRole)
        configure_combo_popup(self.pickup_filter)
        self.pickup_filter.currentIndexChanged.connect(self._filter_pickups)
        filter_label.setBuddy(self.pickup_filter)
        self.pickup_filter.setAccessibleName("Pickup type filter")
        controls.addWidget(filter_label)
        controls.addWidget(self.pickup_filter)
        self.pickup_search = QLineEdit()
        self.pickup_search.setPlaceholderText("Search slot, type, model name, or ID…")
        self.pickup_search.setClearButtonEnabled(True)
        self.pickup_search.setMaximumWidth(300)
        self.pickup_search.setAccessibleName("Search pickups")
        self.pickup_search.setAccessibleDescription("Filters the pickup table.")
        self.pickup_search.textChanged.connect(self._filter_pickups)
        controls.addWidget(self.pickup_search)
        controls.addStretch()
        layout.addLayout(controls)
        self.pickup_status = QLabel("")
        self.pickup_status.setObjectName("muted")
        self.pickup_status.setWordWrap(True)
        layout.addWidget(self.pickup_status)
        self.pickup_table = QTableWidget(0, 9)
        self.pickup_table.setAccessibleName("Saved pickups table")
        self.pickup_table.setHorizontalHeaderLabels(
            ("Slot", "Type", "Model ID", "Quantity", "X", "Y", "Z", "Revenue", "Removed"))
        pickup_header = self.pickup_table.horizontalHeader()
        pickup_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        pickup_header.setStretchLastSection(False)
        self._polish_table(self.pickup_table)
        for column, width in enumerate((55, 210, 90, 100, 125, 125, 115, 105, 90)):
            self.pickup_table.setColumnWidth(column, width)
        pickup_type_options = alphabetical_choices([
            (choice_label(name, value), value)
            for value, name in enumerate(PICKUP_TYPES)
        ])
        pickup_type_display = {value: choice_label(name, value) for value, name in enumerate(PICKUP_TYPES)}
        pickup_type_tooltips = {value: f"ID {value}" for value in range(len(PICKUP_TYPES))}
        self.pickup_table.setItemDelegateForColumn(
            1, ChoiceDelegate(
                pickup_type_options, self.pickup_table,
                display_labels=pickup_type_display,
                tooltip_labels=pickup_type_tooltips,
            )
        )
        self.pickup_table.setItemDelegateForColumn(
            2, PickupModelDelegate(list(pickup_model_choices()), self.pickup_table)
        )
        self.pickup_table.setItemDelegateForColumn(3, NumberDelegate("uint32", 0, 0xFFFFFFFF, self.pickup_table))
        for column in (4, 5, 6, 7):
            self.pickup_table.setItemDelegateForColumn(column, NumberDelegate("float", parent=self.pickup_table))
        self.pickup_table.setItemDelegateForColumn(8, ChoiceDelegate([("No", 0), ("Yes", 1)], self.pickup_table))
        layout.addWidget(self.pickup_table)
        return page

    def _vehicles_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(12)
        heading, _ = page_header("Vehicles")
        layout.addWidget(heading)

        self.vehicle_tabs = QTabWidget()

        generator_page = QWidget()
        generator_layout = QVBoxLayout(generator_page)
        self.generator_table = QTableWidget(0, 11)
        self.generator_table.setAccessibleName("Persistent parked vehicles table")
        self.generator_table.setHorizontalHeaderLabels(
            ("Slot", "Model", "X", "Y", "Z", "Angle", "Color 1", "Color 2", "Force", "Alarm %", "Lock %")
        )
        gen_header = self.generator_table.horizontalHeader()
        gen_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._polish_table(self.generator_table)
        for column, width in enumerate((55, 180, 110, 110, 100, 100, 115, 115, 80, 85, 85)):
            self.generator_table.setColumnWidth(column, width)
        vehicle_options = vehicle_choices()
        color_options = color_choices()
        compact_colors = {color_id: compact_color_name(color_id) for color_id in range(-1, 95)}
        self.generator_table.setItemDelegateForColumn(1, ChoiceDelegate(vehicle_options, self.generator_table))
        for column in (2, 3, 4, 5):
            self.generator_table.setItemDelegateForColumn(column, NumberDelegate("float", parent=self.generator_table))
        self.generator_table.setItemDelegateForColumn(6, ChoiceDelegate(color_options, self.generator_table, compact_colors))
        self.generator_table.setItemDelegateForColumn(7, ChoiceDelegate(color_options, self.generator_table, compact_colors))
        self.generator_table.setItemDelegateForColumn(8, ChoiceDelegate([("No", 0), ("Yes", 1)], self.generator_table))
        self.generator_table.setItemDelegateForColumn(9, NumberDelegate("int", 0, 255, self.generator_table))
        self.generator_table.setItemDelegateForColumn(10, NumberDelegate("int", 0, 255, self.generator_table))
        generator_layout.addWidget(self.generator_table)

        garage_page = QWidget()
        garage_layout = QVBoxLayout(garage_page)
        garage_filter_row = QHBoxLayout()
        garage_filter_row.addWidget(QLabel("Garage"))
        self.garage_selector = QComboBox()
        self.garage_selector.setAccessibleName("Hideout garage selector")
        self.garage_selector.addItem("All garages", -1)
        for label, index in alphabetical_choices([(name, index) for index, name in enumerate(GAMEPLAY_GARAGE_NAMES)]):
            self.garage_selector.addItem(label, index)
        configure_combo_popup(self.garage_selector)
        preferred = int(self.settings.value("garage_filter", 0) or 0)
        self.garage_selector.setCurrentIndex(max(0, self.garage_selector.findData(preferred)))
        self.garage_selector.currentIndexChanged.connect(self._garage_filter_changed)
        garage_filter_row.addWidget(self.garage_selector)
        garage_filter_row.addStretch()
        garage_layout.addLayout(garage_filter_row)

        self.garage_anomaly_note = QLabel("")
        self.garage_anomaly_note.setObjectName("warningText")
        self.garage_anomaly_note.setWordWrap(True)
        self.garage_anomaly_note.setVisible(False)
        garage_layout.addWidget(self.garage_anomaly_note)

        garage_actions = QHBoxLayout()
        garage_actions.setSpacing(8)
        self.add_garage_vehicle_button = QPushButton("Add Vehicle…")
        self.edit_garage_vehicle_button = QPushButton("Edit Vehicle…")
        self.remove_garage_vehicle_button = QPushButton("Remove Vehicle")
        self.add_garage_vehicle_button.clicked.connect(self.add_selected_garage_vehicle)
        self.edit_garage_vehicle_button.clicked.connect(self.edit_selected_garage_vehicle)
        self.remove_garage_vehicle_button.clicked.connect(self.remove_selected_garage_vehicle)
        garage_actions.addWidget(self.add_garage_vehicle_button)
        garage_actions.addWidget(self.edit_garage_vehicle_button)
        garage_actions.addWidget(self.remove_garage_vehicle_button)
        self.garage_selection_hint = QLabel("Select a garage slot.")
        self.garage_selection_hint.setObjectName("muted")
        garage_actions.addWidget(self.garage_selection_hint)
        garage_actions.addStretch()
        garage_layout.addLayout(garage_actions)

        self.garage_table = QTableWidget(0, 7)
        self.garage_table.setAccessibleName("Hideout garage vehicle slots")
        self.garage_table.setHorizontalHeaderLabels(
            ("Garage", "Slot", "Vehicle", "Primary", "Secondary", "Protection", "Radio")
        )
        garage_header = self.garage_table.horizontalHeader()
        garage_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._polish_table(self.garage_table)
        self.garage_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.garage_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.garage_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for column, width in enumerate((190, 55, 200, 110, 110, 210, 150)):
            self.garage_table.setColumnWidth(column, width)
        self.garage_table.itemSelectionChanged.connect(self._garage_selection_changed)
        self.garage_table.cellDoubleClicked.connect(self._garage_row_double_clicked)
        garage_layout.addWidget(self.garage_table)

        self.vehicle_tabs.addTab(garage_page, "Hideout garages")
        self.vehicle_tabs.addTab(generator_page, "Parked vehicles")
        self.vehicle_tabs.currentChanged.connect(self._vehicle_tab_changed)
        layout.addWidget(self.vehicle_tabs)
        return page

    def _gangs_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(12)
        heading, _ = page_header("Gangs")
        layout.addWidget(heading)
        self.visible_gang_indices = tuple(range(8))
        self.gang_table = QTableWidget(len(self.visible_gang_indices), 3)
        self.gang_table.setHorizontalHeaderLabels(("Gang", "Weapon 1", "Weapon 2"))
        gang_header = self.gang_table.horizontalHeader()
        gang_header.setMinimumSectionSize(190)
        gang_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._polish_table(self.gang_table)
        self.gang_combos = []
        for row, gang_index in enumerate(self.visible_gang_indices):
            item = QTableWidgetItem(GANG_NAMES[gang_index])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.gang_table.setItem(row, 0, item)
            row_combos = []
            for column in (1, 2):
                combo = QComboBox()
                for label, weapon_type in weapon_choices():
                    combo.addItem(label, weapon_type)
                configure_combo_popup(combo)
                set_combo_id_tooltip(combo)
                combo.currentIndexChanged.connect(lambda _=0, c=combo: set_combo_id_tooltip(c))
                self.gang_table.setCellWidget(row, column, combo)
                row_combos.append(combo)
            self.gang_combos.append(row_combos)
        layout.addWidget(self.gang_table)
        return page

    def _stats_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(10)
        heading, _ = page_header("Stats & progress")
        layout.addWidget(heading)
        note = QLabel("Editing a mission-progress stat here does not replay the mission's other world or script effects.")
        note.setObjectName("warningText")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.stats_search = QLineEdit()
        self.stats_search.setAccessibleName("Search statistics")
        self.stats_search.setAccessibleDescription("Filter statistics by name.")
        self.stats_search.setPlaceholderText("Search statistics, properties, jumps, missions…")
        self.stats_search.setClearButtonEnabled(True)
        self.stats_search.textChanged.connect(self._filter_stats)
        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        search_row.addWidget(self.stats_search, 1)
        self.stats_status = QLabel("0 statistics")
        self.stats_status.setObjectName("mutedText")
        self.stats_status.setMinimumWidth(150)
        self.stats_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        search_row.addWidget(self.stats_status)
        layout.addLayout(search_row)
        self.stats_table = QTableWidget(0, 3)
        self.stats_table.setAccessibleName("Saved statistics table")
        self.stats_table.setHorizontalHeaderLabels(("Statistic", "Value", "Stored as"))
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.stats_table.itemChanged.connect(self._table_item_changed)
        self.stats_table.setItemDelegateForColumn(1, StatsValueDelegate(self.stats_table))
        self._polish_table(self.stats_table)
        layout.addWidget(self.stats_table)
        return page

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.open_action = QAction("&Save Selector…", self, shortcut="Ctrl+O", triggered=self.choose_open)
        self.browse_open_action = QAction("&Browse for Save File…", self, shortcut="Ctrl+Shift+O", triggered=self.choose_open_file)
        self.save_action = QAction("&Save", self, shortcut="Ctrl+S", triggered=self.save_current)
        self.save_as_action = QAction("Save &As…", self, shortcut="Ctrl+Shift+S", triggered=self.choose_save)
        self.save_slot_action = QAction("Save to S&lot…", self, triggered=self.save_to_slot)
        self.save_slot_action.setToolTip("Save into one of the eight slots in the configured Save Folder.")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.browse_open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addAction(self.save_slot_action)
        file_menu.addSeparator()
        self.restore_action = QAction("&Restore Save…", self, triggered=self.restore_save)
        self.restore_action.setToolTip("Restore a previous automatic backup.")
        file_menu.addAction(self.restore_action)
        file_menu.addSeparator()
        self.close_action = QAction("&Close Save", self, shortcut="Ctrl+W", triggered=self.close_current_save)
        exit_action = QAction("E&xit", self, shortcut="Ctrl+Q", triggered=self.close)
        file_menu.addAction(self.close_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        self.revert_page_action = QAction("Revert Current &Page", self, triggered=self.revert_current_page)
        edit_menu.addAction(self.revert_page_action)
        self.revert_action = QAction("&Revert All Edits…", self, shortcut="Ctrl+Alt+R", triggered=self.revert_all_edits)
        edit_menu.addAction(self.revert_action)

        view_menu = self.menuBar().addMenu("&View")
        self.page_shortcuts: list[QShortcut] = []
        for index in range(8):
            shortcut = QShortcut(f"Ctrl+{index + 1}", self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(lambda i=index: self._activate_page(i, focus_workspace=True))
            self.page_shortcuts.append(shortcut)

        appearance_menu = view_menu.addMenu("&Appearance")
        self.appearance_group = QActionGroup(self)
        self.appearance_group.setExclusive(True)
        self.appearance_actions: dict[str, QAction] = {}
        for mode, label in (("system", "Follow System"), ("light", "Light"), ("dark", "Dark")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, m=mode: self.apply_appearance(m))
            self.appearance_group.addAction(action)
            appearance_menu.addAction(action)
            self.appearance_actions[mode] = action

        view_menu.addSeparator()
        view_menu.addAction(QAction("Reset Window &Layout", self, triggered=self.reset_window_layout))

        settings_menu = self.menuBar().addMenu("&Settings")
        settings_menu.addAction(QAction("Save &Folder…", self, triggered=self.show_folder_settings))

        help_menu = self.menuBar().addMenu("&Help")
        if self.log_path:
            help_menu.addAction(QAction("Open &Log File", self, triggered=self.open_log_file))
            help_menu.addSeparator()
        help_menu.addAction(QAction("Open &GitHub Repository", self, triggered=self.open_github))
        help_menu.addAction(QAction("Report an &Issue…", self, triggered=self.open_github_issues))
        help_menu.addSeparator()
        help_menu.addAction(QAction("Beta &Information…", self, triggered=self.show_beta_notice))
        help_menu.addAction(QAction("&About", self, triggered=self.show_about))

    def _activate_page(self, index: int, focus_workspace: bool = False) -> None:
        if index < 0 or index >= self.tabs.count() or not self.tabs.isTabEnabled(index):
            self.statusBar().showMessage("That section is unavailable for the current save.", 2500)
            return
        self.nav.setCurrentRow(index)
        self.tabs.setCurrentIndex(index)
        if focus_workspace:
            QTimer.singleShot(0, self._focus_workspace)

    def _focus_workspace(self) -> None:
        page = self.tabs.currentWidget()
        if not page:
            return
        for widget in page.findChildren(QWidget):
            policy = widget.focusPolicy()
            if widget.isVisible() and widget.isEnabled() and (policy & Qt.FocusPolicy.TabFocus):
                widget.setFocus(Qt.FocusReason.ShortcutFocusReason)
                return

    def reset_window_layout(self) -> None:
        self.resize(1180, 760)
        self.sidebar.setVisible(True)
        self.body_splitter.setSizes([210, max(770, self.width() - 210)])
        for key in ("pickup_header", "generator_header", "garage_header", "stats_header"):
            self.settings.remove(key)
        self.settings.remove("vehicle_tab_key")
        self._apply_default_table_widths()
        if hasattr(self, "vehicle_tabs"):
            self.vehicle_tabs.setCurrentIndex(0)
        self.statusBar().showMessage("Layout reset.", 2500)

    def _vehicle_tab_changed(self, index: int) -> None:
        if not hasattr(self, "vehicle_tabs"):
            return
        key = "garages" if index == 0 else "parked"
        self.settings.setValue("vehicle_tab_key", key)

    def _apply_default_table_widths(self) -> None:
        defaults = (
            ("pickup_table", (55, 210, 90, 100, 125, 125, 115, 105, 90)),
            ("generator_table", (55, 180, 110, 110, 100, 100, 115, 115, 80, 85, 85)),
            ("garage_table", (190, 55, 200, 110, 110, 210, 150)),
            ("stats_table", (360, 220, 120)),
        )
        for attribute, widths in defaults:
            table = getattr(self, attribute, None)
            if table is None:
                continue
            for column, width in enumerate(widths):
                if column < table.columnCount():
                    table.setColumnWidth(column, width)

    def _save_table_layouts(self) -> None:
        for key, attribute in (
            ("pickup_header", "pickup_table"),
            ("generator_header", "generator_table"),
            ("garage_header", "garage_table"),
            ("stats_header", "stats_table"),
        ):
            table = getattr(self, attribute, None)
            if table is not None:
                self.settings.setValue(key, table.horizontalHeader().saveState())
        if hasattr(self, "vehicle_tabs"):
            self._vehicle_tab_changed(self.vehicle_tabs.currentIndex())

    def _restore_table_layouts(self) -> None:
        self._apply_default_table_widths()
        for key, attribute in (
            ("pickup_header", "pickup_table"),
            ("generator_header", "generator_table"),
            ("garage_header", "garage_table"),
            ("stats_header", "stats_table"),
        ):
            table = getattr(self, attribute, None)
            state = self.settings.value(key)
            if table is not None and state is not None:
                try:
                    table.horizontalHeader().restoreState(state)
                except Exception:
                    LOGGER.warning("Could not restore table layout: %s", key, exc_info=True)
        if hasattr(self, "vehicle_tabs"):
            tab_key = str(self.settings.value("vehicle_tab_key", "garages") or "garages")
            if tab_key not in ("garages", "parked"):
                tab_key = "garages"
                self.settings.setValue("vehicle_tab_key", tab_key)
            self.vehicle_tabs.setCurrentIndex(0 if tab_key == "garages" else 1)

    def _connect_system_appearance(self) -> None:
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._system_color_scheme_changed)

    @staticmethod
    def _system_theme() -> str:
        hints = QGuiApplication.styleHints()
        try:
            scheme = hints.colorScheme()
            name = getattr(scheme, "name", "")
            if callable(name):
                name = name()
            name = str(name or scheme).lower()
            if "dark" in name:
                return "dark"
            if "light" in name:
                return "light"
        except Exception:
            pass
        window = QApplication.palette().color(QPalette.ColorRole.Window)
        return "dark" if window.lightness() < 128 else "light"

    def _system_color_scheme_changed(self, *unused) -> None:
        if self.current_appearance != "system":
            return
        resolved = self._system_theme()
        self.apply_theme(resolved, force=True)
        self._update_system_appearance_label()
        self.statusBar().showMessage(f"Appearance: {resolved.title()}.", 3000)

    def _update_system_appearance_label(self) -> None:
        if hasattr(self, "appearance_actions") and "system" in self.appearance_actions:
            self.appearance_actions["system"].setText(f"Follow System ({self._system_theme().title()})")

    def apply_appearance(self, appearance: str, initial: bool = False) -> None:
        appearance = appearance if appearance in {"system", "light", "dark"} else "dark"
        self.current_appearance = appearance
        resolved = self._system_theme() if appearance == "system" else appearance
        changed = resolved != self.current_theme
        self.apply_theme(resolved, initial=initial)
        self.settings.setValue("appearance", appearance)
        if hasattr(self, "appearance_actions"):
            action = self.appearance_actions.get(appearance)
            if action:
                action.setChecked(True)
        self._update_system_appearance_label()
        if not initial and appearance == "system" and not changed:
            self.statusBar().showMessage(f"Following system appearance: {resolved.title()}.", 3000)

    def _set_file_state_text(self, text: str) -> None:
        self._file_state_full = text
        self._refresh_file_state_text()

    def _refresh_file_state_text(self) -> None:
        if not hasattr(self, "file_state"):
            return
        full = getattr(self, "_file_state_full", self.file_state.text())
        available = max(140, min(430, self.width() // 3))
        self.file_state.setMaximumWidth(available)
        self.file_state.setText(self.file_state.fontMetrics().elidedText(full, Qt.TextElideMode.ElideMiddle, max(80, available - 8)))
        self.file_state.setToolTip(full)

    def _refresh_dirty_from_ui(self) -> None:
        if not self.save or not self.current_path or self._opened_raw is None or not self.save.profile.editable:
            self.ui_dirty = False
            self._update_window_state()
            return
        direct_save_change = self.save.raw != self._opened_raw
        if self._validate_form(mark_cells=False):
            self.ui_dirty = True
            self._update_window_state()
            return
        snapshot = SaveFile(self._opened_raw, self.current_path)
        current = self.save
        try:
            self.save = snapshot
            self._apply_form()
        finally:
            self.save = current
        self.ui_dirty = direct_save_change or snapshot.raw != self._opened_raw
        self._update_window_state()

    def revert_current_page(self) -> None:
        if not self.save or not self.current_path or self._opened_raw is None or not self.save.profile.editable:
            return
        page = self.tabs.currentIndex()
        if page == 0:
            self.statusBar().showMessage("Overview has no editable values.", 2500)
            return
        source = SaveFile(self._opened_raw, self.current_path)
        self._loading_form = True
        try:
            if page == 1:
                player = source.player()
                self.money.setValue(player.money)
                self.health.setValue(player.health)
                self.armour.setValue(player.armour)
                self.max_health.setValue(player.max_health)
                self.max_armour.setValue(player.max_armour)
                self.pos_x.setValue(player.position[0])
                self.pos_y.setValue(player.position[1])
                self.pos_z.setValue(player.position[2])
                for box, value in zip(self.ability_boxes, (player.infinite_sprint, player.fast_reload,
                                                            player.fireproof, player.free_hospital,
                                                            player.free_jail, player.drive_by)):
                    box.setChecked(value)
            elif page == 2:
                world = source.world()
                self.hour.setValue(world.hour)
                self.minute.setValue(world.minute)
                for combo, value in ((self.old_weather, world.old_weather),
                                     (self.new_weather, world.new_weather),
                                     (self.forced_weather, world.forced_weather)):
                    combo.setCurrentIndex(max(0, combo.findData(value)))
            elif page == 3:
                source_weapons = source.weapons()
                for row, slot_index in enumerate(self.weapon_slot_indices):
                    weapon = source_weapons[slot_index]
                    combo = self.weapon_combos[row]
                    index = combo.findData(weapon.weapon_type)
                    combo.setCurrentIndex(index if index >= 0 else 0)
                    self.weapon_table.cellWidget(row, 1).setValue(weapon.ammo_clip)
                    self.weapon_table.cellWidget(row, 2).setValue(weapon.ammo_total)
                    self._update_weapon_row_state(row)
            elif page == 4:
                self._populate_pickups(source.pickups())
            elif page == 5:
                self._populate_generators(source.car_generators())
                self._populate_garages(source.stored_cars())
            elif page == 6:
                for gang in source.gangs():
                    if gang.index >= len(self.gang_combos):
                        continue
                    combo1, combo2 = self.gang_combos[gang.index]
                    combo1.setCurrentIndex(max(0, combo1.findData(gang.weapon_1)))
                    combo2.setCurrentIndex(max(0, combo2.findData(gang.weapon_2)))
            elif page == 7:
                self._populate_stats(source.stats())
        finally:
            self._loading_form = False
        self._clear_validation_marks()
        self._refresh_dirty_from_ui()
        self.statusBar().showMessage("Page reverted.", 3500)

    def revert_all_edits(self) -> None:
        if not self.save or not self.current_path or not self.save.profile.editable or self._opened_raw is None:
            return
        changed_since_open = self.ui_dirty or self.save.raw != self._opened_raw
        if not changed_since_open:
            self.statusBar().showMessage("There are no edits to revert.", 2500)
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Revert all edits?")
        box.setText("Discard all edits since the last save?")
        revert_button = box.addButton("Revert", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel_button)
        box.exec()
        if box.clickedButton() is not revert_button:
            return
        restored = SaveFile(self._opened_raw, self.current_path)
        self.save = restored
        self._loading_form = True
        try:
            self._populate(
                restored.player(), restored.world(), restored.weapons(), restored.pickups(),
                restored.car_generators(), restored.stored_cars(), restored.gangs(), restored.stats(),
            )
        finally:
            self._loading_form = False
        self.ui_dirty = False
        self._clear_validation_marks()
        self._update_window_state()
        self.statusBar().showMessage("All edits reverted.", 4000)
        LOGGER.info("Reverted toolkit session to originally opened save: %s", self.current_path)

    def _polish_table(self, table: QTableWidget, show_row_header: bool = False) -> None:
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.verticalHeader().setDefaultSectionSize(30)
        table.verticalHeader().setVisible(show_row_header)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def _sync_navigation(self, index: int) -> None:
        if self.nav.currentRow() != index:
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(index)
            self.nav.blockSignals(False)

    def _set_nav_enabled(self, index: int, enabled: bool) -> None:
        item = self.nav.item(index)
        if item:
            flags = item.flags()
            if enabled:
                item.setFlags(flags | Qt.ItemIsEnabled)
            else:
                item.setFlags(flags & ~Qt.ItemIsEnabled)
        if hasattr(self, "page_shortcuts") and 0 <= index < len(self.page_shortcuts):
            self.page_shortcuts[index].setEnabled(enabled)

    def _selected_output_profile(self):
        if not hasattr(self, "output_format_combo"):
            return None
        key = str(self.output_format_combo.currentData() or "")
        return SUPPORTED_PROFILE_BY_KEY.get(key)

    def _output_format_changed(self, *unused) -> None:
        profile = self._selected_output_profile()
        if hasattr(self, "summary_output_format"):
            self.summary_output_format.setText(profile.name if profile else "Choose a format above.")
        self._update_export_help()
        self._update_window_state()

    def _update_export_help(self, *unused) -> None:
        self.conversion_notice.hide()
        if not self.save:
            self.export_help.setText("Open a save to begin.")
            return
        if not self.save.profile.editable:
            self.export_help.setText("Read-only layout.")
            return
        target = self._selected_output_profile()
        if not target:
            self.export_help.setText("Choose an output format above.")
        elif target.key == self.save.profile.key:
            self.export_help.setText("Save in place. Automatic backup before overwrite.")
        else:
            self.export_help.setText(f"Save As or Save to Slot will create {target.name} output.")
            self.conversion_notice.set_message(
                "Format conversion",
                f"{self.save.profile.name} → {target.name}; choose Save As or Save to Slot.",
            )
            self.conversion_notice.show()

    def _set_state_badge(self, text: str, state: str) -> None:
        if not hasattr(self, "state_badge"):
            return
        self.state_badge.setText(text)
        self.state_badge.setProperty("state", state)
        self.state_badge.style().unpolish(self.state_badge)
        self.state_badge.style().polish(self.state_badge)

    def _update_window_state(self) -> None:
        base_title = APP_NAME
        if not self.save or not self.current_path:
            self.setWindowTitle(base_title)
            self._set_file_state_text("No save open")
            self._set_state_badge("No save", "idle")
            self.integrity_context.setText("No save open")
            self.integrity_context.setObjectName("integrityIdle")
            self.integrity_context.style().unpolish(self.integrity_context)
            self.integrity_context.style().polish(self.integrity_context)
            self.save_as_button.setEnabled(False)
            if hasattr(self, "revert_action"):
                self.revert_action.setEnabled(False)
            return

        dirty = self.ui_dirty
        marker = " *" if dirty else ""
        self.setWindowTitle(f"{APP_NAME} — {self.current_path.name}{marker}")
        self._set_file_state_text(self.current_path.name)
        if dirty:
            self._set_state_badge("Edited", "edited")
        elif not self.save.profile.editable:
            self._set_state_badge("Read-only", "readonly")
        else:
            self._set_state_badge("Ready", "ready")
        self.integrity_context.setText("Checksum valid")
        self.integrity_context.setObjectName("integrityGood")
        self.integrity_context.style().unpolish(self.integrity_context)
        self.integrity_context.style().polish(self.integrity_context)

        editable = self.save.profile.editable
        self.save_button.setText("Save" if editable else "Saving Disabled")
        self.summary_action_button.setText("Save" if editable else "View File Layout")
        if hasattr(self, "save_action"):
            self.save_action.setText("&Save")
        if hasattr(self, "revert_action"):
            self.revert_action.setEnabled(
                editable and self._opened_raw is not None and (dirty or self.save.raw != self._opened_raw)
            )


    def _connect_dirty_signals(self) -> None:
        spins = (self.money, self.health, self.armour, self.max_health,
                 self.max_armour, self.pos_x, self.pos_y, self.pos_z,
                 self.hour, self.minute)
        for widget in spins:
            widget.valueChanged.connect(self._mark_dirty)
        for box in self.ability_boxes:
            box.toggled.connect(self._mark_dirty)
        for combo in self.weapon_combos:
            combo.currentIndexChanged.connect(self._mark_dirty)
        for combo in (self.old_weather, self.new_weather, self.forced_weather):
            combo.currentIndexChanged.connect(self._mark_dirty)
        for row in self.gang_combos:
            for combo in row:
                combo.currentIndexChanged.connect(self._mark_dirty)
        for table in (self.pickup_table, self.generator_table):
            table.itemChanged.connect(self._table_item_changed)
        for row in range(self.weapon_table.rowCount()):
            self.weapon_table.cellWidget(row, 1).valueChanged.connect(self._mark_dirty)
            self.weapon_table.cellWidget(row, 2).valueChanged.connect(self._mark_dirty)

    def _mark_dirty(self, *unused) -> None:
        if not self._loading_form and self.save and self.save.profile.editable:
            self.ui_dirty = True
            self._update_window_state()

    def _table_item_changed(self, *unused) -> None:
        self._mark_dirty()

    @staticmethod
    def _parse_int_item(table: QTableWidget, row: int, column: int, label: str,
                        minimum: int, maximum: int) -> ValidationIssue | None:
        item = table.item(row, column)
        exact = item.data(EXACT_VALUE_ROLE) if item else None
        text = str(exact if exact is not None else (item.text().strip() if item else ""))
        try:
            parse_int(text, minimum, maximum)
        except ValueError as error:
            return ValidationIssue(table, row, column, label, str(error))
        return None

    @staticmethod
    def _parse_float_item(table: QTableWidget, row: int, column: int, label: str) -> ValidationIssue | None:
        item = table.item(row, column)
        exact = item.data(EXACT_VALUE_ROLE) if item else None
        text = str(exact if exact is not None else (item.text().strip() if item else ""))
        try:
            parse_float(text)
        except ValueError as error:
            return ValidationIssue(table, row, column, label, str(error))
        return None

    def _clear_validation_marks(self) -> None:
        for table in (self.pickup_table, self.generator_table, self.stats_table):
            for row in range(table.rowCount()):
                for column in range(table.columnCount()):
                    item = table.item(row, column)
                    if not item:
                        continue
                    original_tip = item.data(ORIGINAL_TOOLTIP_ROLE)
                    if original_tip is not None:
                        item.setToolTip(str(original_tip))
                        item.setData(ORIGINAL_TOOLTIP_ROLE, None)
                        item.setIcon(self._empty_icon)

    def _mark_validation_issue(self, issue: ValidationIssue) -> None:
        item = issue.table.item(issue.row, issue.column)
        if not item:
            return
        if item.data(ORIGINAL_TOOLTIP_ROLE) is None:
            item.setData(ORIGINAL_TOOLTIP_ROLE, item.toolTip())
        existing = str(item.data(ORIGINAL_TOOLTIP_ROLE) or "")
        item.setToolTip(issue.message + (f"\n\n{existing}" if existing else ""))
        item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical))

    def _validate_form(self, mark_cells: bool = False) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        # Pickups: model=int16, quantity=uint32, coordinates/revenue=float.
        for row in range(self.pickup_table.rowCount()):
            model_item = self.pickup_table.item(row, 2)
            model_issue = None
            try:
                parse_int(str(model_item.data(Qt.ItemDataRole.UserRole) if model_item else ""), -32768, 32767)
            except ValueError as error:
                model_issue = ValidationIssue(self.pickup_table, row, 2, f"Pickup slot {row} · Model ID", str(error))
            checks = (
                model_issue,
                self._parse_int_item(self.pickup_table, row, 3, f"Pickup slot {row} · Quantity", 0, 0xFFFFFFFF),
                self._parse_float_item(self.pickup_table, row, 4, f"Pickup slot {row} · X"),
                self._parse_float_item(self.pickup_table, row, 5, f"Pickup slot {row} · Y"),
                self._parse_float_item(self.pickup_table, row, 6, f"Pickup slot {row} · Z"),
                self._parse_float_item(self.pickup_table, row, 7, f"Pickup slot {row} · Revenue"),
            )
            issues.extend(issue for issue in checks if issue)
        for row in range(self.generator_table.rowCount()):
            for column, name in ((2, "X"), (3, "Y"), (4, "Z"), (5, "Angle")):
                issue = self._parse_float_item(self.generator_table, row, column, f"Parked vehicle row {row + 1} · {name}")
                if issue:
                    issues.append(issue)
            for column, name in ((9, "Alarm chance"), (10, "Lock chance")):
                issue = self._parse_int_item(self.generator_table, row, column, f"Parked vehicle row {row + 1} · {name}", 0, 255)
                if issue:
                    issues.append(issue)
        for row, (name, _original, kind) in enumerate(getattr(self, "stat_records", [])):
            if kind == "text":
                continue
            item = self.stats_table.item(row, 1)
            text = item.text().strip() if item else ""
            issue = None
            label = f"{friendly_stat_name(name)}"
            if kind == "int":
                issue = self._parse_int_item(self.stats_table, row, 1, label, -2147483648, 2147483647)
            elif kind == "float":
                issue = self._parse_float_item(self.stats_table, row, 1, label)
            else:
                try:
                    parse_bool(text)
                except ValueError as error:
                    issue = ValidationIssue(self.stats_table, row, 1, label, str(error))
            if issue:
                issues.append(issue)
        if mark_cells:
            self._clear_validation_marks()
            for issue in issues:
                self._mark_validation_issue(issue)
        return issues

    def _show_validation_status(self, issues: list[ValidationIssue]) -> None:
        if not issues:
            return
        first = issues[0]
        count = len(issues)
        self.statusBar().showMessage(
            f"Fix {count} {'error' if count == 1 else 'errors'} before saving · {first.label}: {first.message}", 7000
        )

    def _focus_validation_issue(self, issue: ValidationIssue) -> None:
        page_for_table = {
            self.pickup_table: 4,
            self.generator_table: 5,
            self.stats_table: 7,
        }
        page = page_for_table.get(issue.table)
        if page is not None:
            self.tabs.setCurrentIndex(page)
        issue.table.setCurrentCell(issue.row, issue.column)
        item = issue.table.item(issue.row, issue.column)
        if item:
            issue.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
            issue.table.editItem(item)
        issue.table.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _set_loaded(self, loaded: bool) -> None:
        self.tabs.setTabEnabled(0, True)
        self._set_nav_enabled(0, True)
        editable = bool(self.save and self.save.profile.editable)
        for index in range(1, self.tabs.count()):
            enabled = loaded and editable
            self.tabs.setTabEnabled(index, enabled)
            self._set_nav_enabled(index, enabled)
        self.save_button.setEnabled(loaded and editable)
        self.save_slot_button.setEnabled(loaded and editable)
        self.save_as_button.setEnabled(loaded and editable)
        self.summary_action_button.setEnabled(True)
        self.save_action.setEnabled(loaded and editable)
        if hasattr(self, "save_as_action"):
            self.save_as_action.setEnabled(loaded and editable)
        if hasattr(self, "save_slot_action"):
            self.save_slot_action.setEnabled(loaded and editable)
        self.output_format_combo.setEnabled(loaded and editable)
        self.close_action.setEnabled(loaded)
        if hasattr(self, "revert_action"):
            self.revert_action.setEnabled(False)
        if hasattr(self, "revert_page_action"):
            self.revert_page_action.setEnabled(loaded and editable)
        if not loaded:
            self.nav.setCurrentRow(0)
            self._opened_raw = None
            self.summary_path.setText("No save open")
            self.summary_name.setText("—")
            self.summary_time.setText("—")
            self.summary_type.setText("—")
            self.summary_profile.setText("—")
            self.summary_checksum.setText("—")
            self.output_format_combo.blockSignals(True)
            self.output_format_combo.setCurrentIndex(-1)
            self.output_format_combo.blockSignals(False)
            self.source_format_value.setText("No save open")
            self.summary_output_format.setText("No output format selected")
            self.conversion_box.hide()
            self.conversion_notice.hide()
            self._ped_cheat_status = None
            self.cheat_box.hide()
            if hasattr(self, "file_layout_toggle"):
                self.file_layout_toggle.setChecked(False)
            self.summary_action_button.setText("Save Selector…")
        self._update_export_help()
        self._update_window_state()

    def _summary_primary_action(self) -> None:
        if self.save and self.save.profile.editable:
            self.save_current()
        elif self.save:
            self.nav.setCurrentRow(0)
            self.tabs.setCurrentIndex(0)
            self.file_layout_toggle.setChecked(True)
        else:
            self.choose_open()

    def _configured_save_directory(self) -> Path | None:
        value = str(self.settings.value("save_folder", "") or "").strip()
        if not value:
            return None
        path = Path(value).expanduser()
        return path if path.is_dir() else None

    @staticmethod
    def _stock_save_directory() -> Path:
        return Path.home() / "Documents" / "GTA Vice City User Files"

    def _selector_save_directory(self) -> Path | None:
        configured = self._configured_save_directory()
        if configured is not None:
            return configured
        stock = self._stock_save_directory()
        return stock if stock.is_dir() else None

    def _preferred_save_directory(self) -> str:
        configured = self._configured_save_directory()
        if configured is not None:
            return str(configured)
        stock = self._stock_save_directory()
        if stock.is_dir():
            return str(stock)
        recent = str(self.settings.value("last_open_directory", "") or "").strip()
        if recent and Path(recent).is_dir():
            return recent
        return ""

    def show_folder_settings(self) -> bool:
        dialog = FolderSettingsDialog(self.settings, self.current_path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        save_folder = self._configured_save_directory()
        if save_folder is not None:
            self.statusBar().showMessage(f"Save folder set to {save_folder}", 5000)
        else:
            self.statusBar().showMessage("Save folder setting cleared.", 3500)
        return True

    def choose_open(self) -> None:
        """Open the Save Selector, using the configured or recognized stock save folder."""
        if self._load_thread and self._load_thread.isRunning():
            return

        while True:
            folder = self._selector_save_directory()
            if folder is None:
                prompt = QMessageBox(self)
                prompt.setIcon(QMessageBox.Icon.Information)
                prompt.setWindowTitle("Set your Vice City save folder")
                prompt.setText("The Save Selector needs to know where Vice City stores your saves.")
                prompt.setInformativeText(
                    "Stock gta-vc.exe: Documents\\GTA Vice City User Files\n\n"
                    "reVC / Vice City VR: the userfiles folder inside the game installation folder."
                )
                set_folder = prompt.addButton("Set Save Folder…", QMessageBox.ButtonRole.AcceptRole)
                browse_file = prompt.addButton("Browse for Save File…", QMessageBox.ButtonRole.ActionRole)
                cancel = prompt.addButton(QMessageBox.StandardButton.Cancel)
                prompt.setDefaultButton(set_folder)
                prompt.exec()
                if prompt.clickedButton() is set_folder:
                    if self.show_folder_settings():
                        continue
                    return
                if prompt.clickedButton() is browse_file:
                    self.choose_open_file()
                return

            dialog = SaveSelectorDialog(folder, self.current_path, self)
            result = dialog.exec()
            if result == QDialog.DialogCode.Accepted and dialog.selected_path is not None:
                if self._confirm_unsaved("open"):
                    self.open_path(dialog.selected_path)
                return
            if dialog.request_settings:
                if self.show_folder_settings():
                    continue
                return
            if dialog.browse_other:
                self.choose_open_file()
            return

    def choose_open_file(self) -> None:
        """Open a save through the traditional file picker."""
        if self._load_thread and self._load_thread.isRunning():
            return
        start_dir = self._preferred_save_directory()
        name, _ = QFileDialog.getOpenFileName(
            self, "Open a Vice City save", start_dir, "Vice City saves (*.b);;All files (*)"
        )
        if not name:
            return
        if self._confirm_unsaved("open"):
            self.open_path(Path(name))

    def _set_loading_ui(self, active: bool, path: Path | None = None) -> None:
        self.nav.setEnabled(not active)
        self.open_button.setEnabled(not active)
        self.output_format_combo.setEnabled(False if active else bool(self.save and self.save.profile.editable))
        if hasattr(self, "open_action"):
            self.open_action.setEnabled(not active)
        if hasattr(self, "browse_open_action"):
            self.browse_open_action.setEnabled(not active)
        if active:
            self.save_button.setEnabled(False)
            self.save_slot_button.setEnabled(False)
            self.save_as_button.setEnabled(False)
            self.save_action.setEnabled(False)
            if hasattr(self, "save_as_action"):
                self.save_as_action.setEnabled(False)
            if hasattr(self, "save_slot_action"):
                self.save_slot_action.setEnabled(False)
            self.close_action.setEnabled(False)
            self.processing_title.setText("Opening save…")
            self.processing_file.setText(str(path) if path else "")
            self.processing_bar.setValue(0)
            self.processing_detail.setText("Preparing…")
            self.workspace_stack.setCurrentWidget(self.processing_page)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            self.workspace_stack.setCurrentWidget(self.tabs)
            QApplication.restoreOverrideCursor()
            self._set_loaded(bool(self.save))

    def _set_load_progress(self, value: int, message: str) -> None:
        self.processing_bar.setValue(max(0, min(100, value)))
        self.processing_detail.setText(message)

    def open_path(self, path: Path) -> None:
        if self._load_thread and self._load_thread.isRunning():
            return
        path = Path(path)
        self._set_loading_ui(True, path)
        self.statusBar().showMessage(f"Opening {path.name}…")
        thread = SaveLoadThread(path, self)
        self._load_thread = thread
        thread.progress.connect(self._set_load_progress)
        thread.loaded.connect(self._finish_open)
        thread.failed.connect(self._open_failed)
        thread.finished.connect(self._load_thread_finished)
        thread.start()

    def _load_thread_finished(self) -> None:
        if self._load_thread:
            self._load_thread.deleteLater()
        self._load_thread = None

    def _finish_open(self, payload: LoadedSaveData) -> None:
        started = time.perf_counter()
        try:
            self.save = payload.save
            self.current_path = payload.path
            self._opened_raw = bytes(payload.save.raw)
            self.source_format_value.setText(payload.save.profile.name)
            self.source_format_value.setToolTip(
                payload.save.profile.detail
            )
            self.output_format_combo.blockSignals(True)
            source_index = self.output_format_combo.findData(payload.save.profile.key)
            self.output_format_combo.setCurrentIndex(source_index if source_index >= 0 else -1)
            self.output_format_combo.blockSignals(False)
            self._set_load_progress(90, "Building the editor view…")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            if payload.save.profile.editable:
                assert payload.player is not None and payload.world is not None
                assert payload.weapons is not None and payload.pickups is not None
                assert payload.generators is not None and payload.stored_cars is not None
                assert payload.gangs is not None and payload.stats is not None
                self._populate(
                    payload.player, payload.world, payload.weapons, payload.pickups,
                    payload.generators, payload.stored_cars, payload.gangs, payload.stats,
                )
            else:
                self._populate_read_only()
            self.ui_dirty = False
            self._set_profile_editing(payload.save.profile.editable)
            self.settings.setValue("last_open_directory", str(payload.path.parent))
            self._set_load_progress(100, "Ready")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            self._set_loading_ui(False)
            last_page = int(self.settings.value("last_page", 0) or 0)
            if not (0 <= last_page < self.tabs.count()) or not self.tabs.isTabEnabled(last_page):
                last_page = 0
            self.nav.setCurrentRow(last_page)
            self.tabs.setCurrentIndex(last_page)
            self._output_format_changed()
            self._update_window_state()
            elapsed = time.perf_counter() - started
            LOGGER.info("Built editor view in %.3fs for %s", elapsed, payload.path)
            self.statusBar().showMessage(f"Opened · {payload.save.profile.name}", 6000)
        except Exception as error:
            LOGGER.exception("Failed while building the editor view for %s", payload.path)
            self.save = None
            self.current_path = None
            self._opened_raw = None
            self._set_loading_ui(False)
            self._show_open_error(str(error))

    def _open_failed(self, message: str) -> None:
        self._set_loading_ui(False)
        self._show_open_error(message)

    def _show_open_error(self, message: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        if "Checksum mismatch" in message:
            box.setWindowTitle("Checksum mismatch")
            box.setText("Editing is disabled for this save.")
            detail = message
        else:
            box.setWindowTitle("Couldn't open save")
            box.setText("This file is not a supported Vice City save.")
            detail = message
        if self.log_path:
            detail += f"\n\nLog: {self.log_path}"
        box.setInformativeText(detail)
        box.setStandardButtons(QMessageBox.StandardButton.Close)
        box.exec()
        self.statusBar().showMessage("Couldn't open save.", 7000)

    def _populate_overview(self) -> None:
        assert self.save and self.current_path
        self.summary_path.setText(str(self.current_path))
        self.summary_name.setText(self.save.mission_name or "Unnamed save")
        timestamp = self.save.timestamp
        self.summary_time.setText(timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Unknown")
        quick = self.save.quick_save_type
        self.summary_type.setText("Normal save" if quick == 0 else f"Quick-save type {quick}")
        self.summary_profile.setText(f"{self.save.profile.name} — {self.save.profile.detail}")
        self.summary_checksum.setText(f"Valid · {self.save.stored_checksum}")

        rows = self.save.blocks + self.save.padding_blocks
        self.block_table.setUpdatesEnabled(False)
        try:
            self.block_table.setRowCount(len(rows))
            for row, block in enumerate(rows):
                values = (
                    block.name, f"0x{block.offset:05X}", str(block.size),
                    "—" if block.inner_size is None else str(block.inner_size),
                )
                for column, value in enumerate(values):
                    self.block_table.setItem(row, column, QTableWidgetItem(value))
        finally:
            self.block_table.setUpdatesEnabled(True)
        self._refresh_persistent_ped_cheat()

    def _populate_read_only(self) -> None:
        assert self.save and self.current_path
        self._loading_form = True
        try:
            self._populate_overview()
        finally:
            self._loading_form = False

    def _populate(self, player: PlayerValues, world: WorldValues,
                  weapons: list[WeaponValues], pickups: list[PickupRecord],
                  generators: list[CarGeneratorRecord], stored_cars: list[StoredCarRecord],
                  gangs: list[GangRecord], stats: list[tuple[str, object, str]]) -> None:
        assert self.save and self.current_path
        self._loading_form = True
        try:
            self.money.setValue(player.money)
            self.health.setValue(player.health)
            self.armour.setValue(player.armour)
            self.max_health.setValue(player.max_health)
            self.max_armour.setValue(player.max_armour)
            self.pos_x.setValue(player.position[0])
            self.pos_y.setValue(player.position[1])
            self.pos_z.setValue(player.position[2])
            for box, value in zip(self.ability_boxes, (player.infinite_sprint, player.fast_reload,
                                                        player.fireproof, player.free_hospital,
                                                        player.free_jail, player.drive_by)):
                box.setChecked(value)
            self.hour.setValue(world.hour)
            self.minute.setValue(world.minute)
            for combo, value in ((self.old_weather, world.old_weather),
                                 (self.new_weather, world.new_weather),
                                 (self.forced_weather, world.forced_weather)):
                combo.setCurrentIndex(max(0, combo.findData(value)))
            for row, slot_index in enumerate(self.weapon_slot_indices):
                weapon = weapons[slot_index]
                combo = self.weapon_combos[row]
                index = combo.findData(weapon.weapon_type)
                combo.setCurrentIndex(index if index >= 0 else 0)
                self.weapon_table.cellWidget(row, 1).setValue(weapon.ammo_clip)
                self.weapon_table.cellWidget(row, 2).setValue(weapon.ammo_total)
                self._update_weapon_row_state(row)

            self._set_load_progress(92, "Building pickup table…")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            self._populate_pickups(pickups)
            self._set_load_progress(95, "Building vehicle and garage tables…")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            self._populate_generators(generators)
            self._populate_garages(stored_cars)
            for gang in gangs:
                if gang.index >= len(self.gang_combos):
                    continue
                combo1, combo2 = self.gang_combos[gang.index]
                combo1.setCurrentIndex(max(0, combo1.findData(gang.weapon_1)))
                combo2.setCurrentIndex(max(0, combo2.findData(gang.weapon_2)))

            self._set_load_progress(97, "Building statistics and file layout…")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            self._populate_stats(stats)
            self._populate_overview()
        finally:
            self._loading_form = False

    def _item(self, value, editable: bool = True) -> QTableWidgetItem:
        text = f"{value:.9g}" if isinstance(value, float) else str(value)
        item = QTableWidgetItem(text)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _numeric_item(self, value: int | float, editable: bool = True, decimals: int = 3) -> QTableWidgetItem:
        text = f"{value:.{decimals}f}" if isinstance(value, float) else str(value)
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setData(EXACT_VALUE_ROLE, value)
        item.setData(ORIGINAL_VALUE_ROLE, value)
        if isinstance(value, float):
            item.setToolTip(f"Displayed: {text}\nStored value: {value:.9g}")
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    @staticmethod
    def _numeric_value(table: QTableWidget, row: int, column: int):
        item = table.item(row, column)
        if not item:
            raise ValueError("Missing numeric table value.")
        exact = item.data(EXACT_VALUE_ROLE)
        if exact is not None:
            return exact
        return item.text().strip()

    def _choice_item(self, label: str, value: int) -> QTableWidgetItem:
        item = QTableWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, value)
        if label.rstrip().endswith(f"({value})"):
            item.setToolTip(f"ID {value}")
        return item

    @staticmethod
    def _vehicle_label(model_id: int, allow_empty: bool = False) -> str:
        if allow_empty and model_id == 0:
            return "Empty slot"
        index = model_id - 130
        if 0 <= index < len(VEHICLE_NAMES):
            return choice_label(VEHICLE_NAMES[index], model_id)
        return choice_label("Custom model", model_id)

    @staticmethod
    def _radio_label(value: int) -> str:
        if value == -1:
            return choice_label("Default", value)
        if 0 <= value < len(RADIO_STATIONS):
            return choice_label(RADIO_STATIONS[value], value)
        if value == 10:
            return choice_label("Radio off", value)
        return choice_label("Unknown", value)

    def _populate_pickups(self, records: list[PickupRecord]) -> None:
        self.pickup_records = records
        self.pickup_table.setUpdatesEnabled(False)
        try:
            self.pickup_table.setRowCount(len(self.pickup_records))
            for row, record in enumerate(self.pickup_records):
                self.pickup_table.setItem(row, 0, self._numeric_item(record.slot, False, 0))
                type_name = PICKUP_TYPES[record.pickup_type] if 0 <= record.pickup_type < len(PICKUP_TYPES) else "Custom type"
                type_item = self._choice_item(choice_label(type_name, record.pickup_type), record.pickup_type)
                type_item.setToolTip(f"ID {record.pickup_type}")
                self.pickup_table.setItem(row, 1, type_item)
                model_item = self._choice_item(choice_label(pickup_model_name(record.model_id), record.model_id), record.model_id)
                model_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.pickup_table.setItem(row, 2, model_item)
                self.pickup_table.setItem(row, 3, self._numeric_item(record.quantity, True, 0))
                for column, value in enumerate(record.position, 4):
                    self.pickup_table.setItem(row, column, self._numeric_item(value, True, 3))
                self.pickup_table.setItem(row, 7, self._numeric_item(record.revenue, True, 3))
                self.pickup_table.setItem(row, 8, self._choice_item("Yes" if record.removed else "No", int(record.removed)))
        finally:
            self.pickup_table.setUpdatesEnabled(True)
        self._filter_pickups()

    def _filter_pickups(self) -> None:
        wanted = self.pickup_filter.currentData()
        query = self.pickup_search.text().strip().lower() if hasattr(self, "pickup_search") else ""
        active = 0
        visible = 0
        for row in range(self.pickup_table.rowCount()):
            type_item = self.pickup_table.item(row, 1)
            actual = int(type_item.data(Qt.ItemDataRole.UserRole)) if type_item else 0
            if actual != 0:
                active += 1
            hidden = (wanted == -1 and actual == 0) or (isinstance(wanted, int) and wanted >= 0 and actual != wanted)
            if not hidden and query:
                slot = self.pickup_table.item(row, 0).text().lower()
                type_text = type_item.text().lower() if type_item else ""
                model = self.pickup_table.item(row, 2).text().lower()
                hidden = query not in slot and query not in type_text and query not in model
            self.pickup_table.setRowHidden(row, hidden)
            if not hidden:
                visible += 1
        if active:
            self.pickup_status.setText(f"Showing {visible} rows · {active} active · {self.pickup_table.rowCount()} total slots.")
        else:
            self.pickup_status.setText("No active pickups. Select ‘All 336 slots’ to inspect empty slots.")

    def _set_profile_editing(self, editable: bool) -> None:
        for index in range(1, self.tabs.count()):
            self.tabs.setTabEnabled(index, editable)
            self._set_nav_enabled(index, editable)
        self.conversion_box.setVisible(not editable)
        if not editable and self.tabs.currentIndex() > 0:
            self.nav.setCurrentRow(0)
            self.tabs.setCurrentIndex(0)

    def _populate_generators(self, records: list[CarGeneratorRecord]) -> None:
        self.generator_records = records
        self.generator_table.setUpdatesEnabled(False)
        try:
            self.generator_table.setRowCount(len(records))
            for row, record in enumerate(records):
                self.generator_table.setItem(row, 0, self._numeric_item(record.slot, False, 0))
                self.generator_table.setItem(row, 1, self._choice_item(self._vehicle_label(record.model_id), record.model_id))
                for column, value in enumerate((*record.position, record.angle), 2):
                    self.generator_table.setItem(row, column, self._numeric_item(value, True, 3))
                c1 = self._choice_item(compact_color_name(record.color_1), record.color_1)
                c1.setToolTip(f"ID {record.color_1}")
                c2 = self._choice_item(compact_color_name(record.color_2), record.color_2)
                c2.setToolTip(f"ID {record.color_2}")
                self.generator_table.setItem(row, 6, c1)
                self.generator_table.setItem(row, 7, c2)
                self.generator_table.setItem(row, 8, self._choice_item("Yes" if record.force_spawn else "No", int(record.force_spawn)))
                self.generator_table.setItem(row, 9, self._numeric_item(record.alarm_chance, True, 0))
                self.generator_table.setItem(row, 10, self._numeric_item(record.lock_chance, True, 0))
        finally:
            self.generator_table.setUpdatesEnabled(True)

    def _populate_garages(self, records: list[StoredCarRecord]) -> None:
        self.garage_records = list(records)
        try:
            self.garage_capacities = self.save.hideout_garage_capacities() if self.save else {}
        except SaveFormatError:
            self.garage_capacities = {}
        self._refresh_garage_table()

    def _garage_filter_changed(self, *unused) -> None:
        if hasattr(self, "garage_selector"):
            self.settings.setValue("garage_filter", int(self.garage_selector.currentData() or 0))
        if hasattr(self, "garage_records"):
            self._refresh_garage_table()

    def _garage_capacity(self, garage: int) -> int:
        return effective_garage_capacity(garage, getattr(self, "garage_capacities", {}))

    def _is_gameplay_garage_slot(self, record: StoredCarRecord) -> bool:
        return is_gameplay_garage_slot(
            record.garage, record.slot, getattr(self, "garage_capacities", {})
        )

    def _garage_record_location(self, record: StoredCarRecord) -> str:
        label = STORAGE_GROUP_NAMES[record.garage]
        if self._is_gameplay_garage_slot(record):
            return f"{label} · slot {record.slot + 1}"
        raw_index = stored_car_raw_index(record.garage, record.slot)
        return f"{label} · stored-car record {raw_index}"

    def _refresh_garage_table(self, select_record_index: int | None = None) -> None:
        if not hasattr(self, "garage_table"):
            return
        wanted = int(self.garage_selector.currentData()) if hasattr(self, "garage_selector") and self.garage_selector.currentData() is not None else 0
        capacities = getattr(self, "garage_capacities", {})
        records = getattr(self, "garage_records", [])
        indices = [
            index for index, record in enumerate(records)
            if (wanted == -1 or record.garage == wanted)
            and should_show_garage_record(record.garage, record.slot, bool(record.model_id), capacities)
        ]
        anomalous = [
            record for record in records
            if record.model_id and is_out_of_capacity_record(record.garage, record.slot, capacities)
        ]
        if anomalous:
            count = len(anomalous)
            suffix = "record" if count == 1 else "records"
            text = f"{count} nonstandard stored-car {suffix} found outside normal garage capacity. These records are preserved."
            if wanted != -1 and any(record.garage != wanted for record in anomalous):
                text += " Choose All garages to inspect all of them."
            self.garage_anomaly_note.setText(text)
            self.garage_anomaly_note.setVisible(True)
        else:
            self.garage_anomaly_note.clear()
            self.garage_anomaly_note.setVisible(False)
        self.garage_table.setUpdatesEnabled(False)
        try:
            self.garage_table.setRowCount(len(indices))
            self.garage_table.setColumnHidden(0, wanted != -1)
            selected_row = -1
            for row, record_index in enumerate(indices):
                record = self.garage_records[record_index]
                garage_item = self._item(STORAGE_GROUP_NAMES[record.garage], False)
                garage_item.setData(GARAGE_RECORD_INDEX_ROLE, record_index)
                self.garage_table.setItem(row, 0, garage_item)
                gameplay_slot = is_gameplay_garage_slot(record.garage, record.slot, capacities)
                slot_text = str(record.slot + 1) if gameplay_slot else "Extra record"
                slot_item = self._item(slot_text, False)
                slot_item.setData(GARAGE_RECORD_INDEX_ROLE, record_index)
                if not gameplay_slot:
                    raw_index = stored_car_raw_index(record.garage, record.slot)
                    if record.garage >= len(GAMEPLAY_GARAGE_NAMES):
                        slot_item.setToolTip(f"Physical stored-car record {raw_index} in reserved storage group 12.")
                    else:
                        slot_item.setToolTip(
                            f"Physical stored-car record {raw_index}; garage capacity is {self._garage_capacity(record.garage)}."
                        )
                self.garage_table.setItem(row, 1, slot_item)
                vehicle_text = self._vehicle_label(record.model_id, True) if record.model_id else "Empty slot"
                vehicle_item = self._item(vehicle_text, False)
                vehicle_item.setData(GARAGE_RECORD_INDEX_ROLE, record_index)
                if record.model_id:
                    vehicle_item.setToolTip(f"ID {record.model_id}")
                self.garage_table.setItem(row, 2, vehicle_item)
                if record.model_id:
                    c1 = self._item(compact_color_name(record.color_1), False)
                    c1.setToolTip(f"ID {record.color_1}")
                    c2 = self._item(compact_color_name(record.color_2), False)
                    c2.setToolTip(f"ID {record.color_2}")
                    protection = self._item(stored_car_flags_summary(record.flags), False)
                    protection.setToolTip(f"Flags: 0x{record.flags & 0xFFFFFFFF:08X}")
                    radio = self._item(self._radio_label(record.radio), False)
                    radio.setToolTip(f"ID {record.radio}")
                else:
                    c1 = self._item("—", False)
                    c2 = self._item("—", False)
                    protection = self._item("—", False)
                    radio = self._item("—", False)
                for column, item in ((3, c1), (4, c2), (5, protection), (6, radio)):
                    item.setData(GARAGE_RECORD_INDEX_ROLE, record_index)
                    self.garage_table.setItem(row, column, item)
                if select_record_index == record_index:
                    selected_row = row
        finally:
            self.garage_table.setUpdatesEnabled(True)
        if selected_row >= 0:
            self.garage_table.selectRow(selected_row)
        else:
            self.garage_table.clearSelection()
        self._garage_selection_changed()

    def _selected_garage_record_index(self) -> int | None:
        selected = self.garage_table.selectionModel().selectedRows() if self.garage_table.selectionModel() else []
        if not selected:
            return None
        row = selected[0].row()
        item = self.garage_table.item(row, 1) or self.garage_table.item(row, 0)
        if not item:
            return None
        value = item.data(GARAGE_RECORD_INDEX_ROLE)
        return int(value) if value is not None else None

    def _garage_geometries(self):
        if not self.save:
            return {}
        try:
            return self.save.hideout_garage_geometries()
        except SaveFormatError:
            return {}

    def _resolved_new_garage_pose(self, record: StoredCarRecord, model_id: int = 130):
        return resolve_new_garage_vehicle_pose(
            record, self._garage_geometries(), model_id=model_id,
            capacity=self._garage_capacity(record.garage),
        )

    def _garage_selection_changed(self) -> None:
        record_index = self._selected_garage_record_index()
        editable = bool(self.save and self.save.profile.editable)
        record = self.garage_records[record_index] if record_index is not None and 0 <= record_index < len(getattr(self, "garage_records", [])) else None
        empty = bool(record is not None and record.model_id == 0)
        occupied = bool(record is not None and record.model_id != 0)
        gameplay_slot = bool(record is not None and self._is_gameplay_garage_slot(record))
        pose = self._resolved_new_garage_pose(record) if empty and gameplay_slot and record is not None else None
        can_add = editable and empty and gameplay_slot and pose is not None
        self.add_garage_vehicle_button.setEnabled(can_add)
        self.edit_garage_vehicle_button.setEnabled(editable and occupied)
        self.remove_garage_vehicle_button.setEnabled(editable and occupied)
        if record is None:
            self.garage_selection_hint.setText("Select a garage slot.")
        elif empty and pose is not None:
            self.garage_selection_hint.setText(f"Empty · {placement_source_label(pose.source)}")
        elif empty:
            self.garage_selection_hint.setText("No automatic placement")
        elif not gameplay_slot:
            self.garage_selection_hint.setText("Nonstandard stored-car record · outside garage capacity")
        else:
            self.garage_selection_hint.setText(stored_car_flags_summary(record.flags))

    def _garage_row_double_clicked(self, row: int, column: int) -> None:
        self.garage_table.selectRow(row)
        record_index = self._selected_garage_record_index()
        if record_index is None:
            return
        if self.garage_records[record_index].model_id:
            self.edit_selected_garage_vehicle()
        else:
            self.add_selected_garage_vehicle()

    def _record_for_new_garage_vehicle(
        self, record: StoredCarRecord
    ) -> tuple[StoredCarRecord, str]:
        if not self._is_gameplay_garage_slot(record):
            raise SaveFormatError("This stored-car record is outside the garage's capacity.")
        pose = self._resolved_new_garage_pose(record, 130)
        if pose is not None:
            base = StoredCarRecord(
                record.garage, record.slot, 0, pose.position, pose.forward,
                0, 0, 0, -1, 0, -2, -2,
            )
            return base, pose.source
        raise SaveFormatError("No automatic placement is available for this garage slot.")

    def add_selected_garage_vehicle(self) -> None:
        if not self.save or not self.save.profile.editable:
            return
        record_index = self._selected_garage_record_index()
        if record_index is None:
            self.statusBar().showMessage("Select an empty garage slot first.", 2500)
            return
        current = self.garage_records[record_index]
        if current.model_id:
            self.edit_selected_garage_vehicle()
            return
        try:
            base, placement_source = self._record_for_new_garage_vehicle(current)
        except SaveFormatError as error:
            self.statusBar().showMessage(str(error), 3500)
            return
        dialog = GarageVehicleDialog(
            base, self._garage_record_location(current), adding=True,
            placement_source=placement_source,
            auto_pose_resolver=lambda model_id: self._resolved_new_garage_pose(current, model_id),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.record()
        self.garage_records[record_index] = updated
        self._refresh_garage_table(record_index)
        self._mark_dirty()
        LOGGER.info(
            "Garage vehicle added | garage=%d slot=%d model=%d placement=%s",
            updated.garage, updated.slot, updated.model_id,
            placement_source,
        )

    def edit_selected_garage_vehicle(self) -> None:
        if not self.save or not self.save.profile.editable:
            return
        record_index = self._selected_garage_record_index()
        if record_index is None:
            self.statusBar().showMessage("Select a stored garage vehicle first.", 2500)
            return
        current = self.garage_records[record_index]
        if not current.model_id:
            self.add_selected_garage_vehicle()
            return
        dialog = GarageVehicleDialog(current, self._garage_record_location(current), adding=False, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.record()
        if updated == current:
            return
        self.garage_records[record_index] = updated
        self._refresh_garage_table(record_index)
        self._mark_dirty()
        LOGGER.info("Garage vehicle edited | garage=%d slot=%d model=%d", updated.garage, updated.slot, updated.model_id)

    def remove_selected_garage_vehicle(self) -> None:
        if not self.save or not self.save.profile.editable:
            return
        record_index = self._selected_garage_record_index()
        if record_index is None:
            return
        current = self.garage_records[record_index]
        if not current.model_id:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Remove garage vehicle?")
        location = self._garage_record_location(current)
        box.setText(f"Remove {self._vehicle_label(current.model_id)} from {location}?")
        box.setInformativeText("Stored placement data is kept.")
        remove_button = box.addButton("Remove Vehicle", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel_button)
        box.exec()
        if box.clickedButton() is not remove_button:
            return
        self.garage_records[record_index] = StoredCarRecord(
            current.garage, current.slot, 0, current.position, current.angles, current.flags,
            current.color_1, current.color_2, current.radio, current.bomb_type, current.variation_a, current.variation_b
        )
        self._refresh_garage_table(record_index)
        self._mark_dirty()
        LOGGER.info("Garage vehicle removed | garage=%d slot=%d old_model=%d", current.garage, current.slot, current.model_id)

    def _populate_stats(self, stats: list[tuple[str, object, str]]) -> None:
        self.stat_records = stats
        self.stats_table.setRowCount(len(stats))
        for row, (name, value, kind) in enumerate(stats):
            label = self._item(friendly_stat_name(name), False)
            label.setData(Qt.UserRole, name)
            self.stats_table.setItem(row, 0, label)
            if kind == "bool":
                value_item = self._item("Yes" if bool(value) else "No", True)
            elif kind == "float":
                value_item = self._numeric_item(float(value), True, 3)
            elif kind == "int":
                value_item = self._numeric_item(int(value), True, 0)
            else:
                value_item = self._item(value, False)
            value_item.setData(STAT_KIND_ROLE, kind)
            self.stats_table.setItem(row, 1, value_item)
            kind_label = {"int": "Whole number", "float": "Decimal",
                          "bool": "Boolean", "text": "Game key"}[kind]
            self.stats_table.setItem(row, 2, self._item(kind_label, False))
        self._filter_stats()

    def _filter_stats(self) -> None:
        text = self.stats_search.text().strip().lower()
        visible = 0
        total = self.stats_table.rowCount()
        for row in range(total):
            label = self.stats_table.item(row, 0).text().lower()
            hidden = bool(text) and text not in label
            self.stats_table.setRowHidden(row, hidden)
            if not hidden:
                visible += 1
        if hasattr(self, "stats_status"):
            self.stats_status.setText(f"Showing {visible} of {total}")

    def _apply_form(self) -> None:
        if not self.save:
            return
        abilities = [box.isChecked() for box in self.ability_boxes]
        self.save.set_player(PlayerValues(
            self.money.value(), self.health.value(), self.armour.value(),
            self.max_health.value(), self.max_armour.value(),
            (self.pos_x.value(), self.pos_y.value(), self.pos_z.value()),
            abilities[0], abilities[1], abilities[2], abilities[4], abilities[3], abilities[5],
        ))
        self.save.set_world(WorldValues(self.hour.value(), self.minute.value(),
                                        int(self.old_weather.currentData()),
                                        int(self.new_weather.currentData()),
                                        int(self.forced_weather.currentData())))
        weapons = list(self.save.weapons())
        for row, slot_index in enumerate(self.weapon_slot_indices):
            combo = self.weapon_combos[row]
            weapon_type = int(combo.currentData())
            clip = self.weapon_table.cellWidget(row, 1).value() if weapon_type else 0
            total = self.weapon_table.cellWidget(row, 2).value() if weapon_type else 0
            weapons[slot_index] = WeaponValues(weapon_type, clip, total)
        self.save.set_weapons(weapons)
        for row, original in enumerate(self.pickup_records):
            record = PickupRecord(
                original.slot,
                tuple(float(self._numeric_value(self.pickup_table, row, column)) for column in (4, 5, 6)),
                float(self._numeric_value(self.pickup_table, row, 7)),
                int(self._numeric_value(self.pickup_table, row, 3)),
                int(self.pickup_table.item(row, 2).data(Qt.ItemDataRole.UserRole)),
                int(self.pickup_table.item(row, 1).data(Qt.ItemDataRole.UserRole)),
                bool(int(self.pickup_table.item(row, 8).data(Qt.ItemDataRole.UserRole))),
                original.text_key,
            )
            if record != original:
                self.save.set_pickup(record)
        for row, original in enumerate(self.generator_records):
            record = CarGeneratorRecord(
                original.slot, int(self.generator_table.item(row, 1).data(Qt.ItemDataRole.UserRole)),
                tuple(float(self._numeric_value(self.generator_table, row, column)) for column in (2, 3, 4)),
                float(self._numeric_value(self.generator_table, row, 5)),
                int(self.generator_table.item(row, 6).data(Qt.ItemDataRole.UserRole)),
                int(self.generator_table.item(row, 7).data(Qt.ItemDataRole.UserRole)),
                bool(int(self.generator_table.item(row, 8).data(Qt.ItemDataRole.UserRole))),
                int(self._numeric_value(self.generator_table, row, 9)),
                int(self._numeric_value(self.generator_table, row, 10)), original.uses_remaining,
            )
            if record != original:
                self.save.set_car_generator(record)
        original_cars = self.save.stored_cars()
        for index, record in enumerate(self.garage_records):
            if record != original_cars[index]:
                self.save.set_stored_car(record)
        original_gangs = self.save.gangs()
        for index in self.visible_gang_indices:
            original = original_gangs[index]
            record = GangRecord(index, int(self.gang_combos[index][0].currentData()),
                                int(self.gang_combos[index][1].currentData()))
            if record != original:
                self.save.set_gang(record)
        for row, (name, original, kind) in enumerate(self.stat_records):
            if kind == "text":
                continue
            item = self.stats_table.item(row, 1)
            text = item.text().strip()
            if kind == "int":
                exact = item.data(EXACT_VALUE_ROLE)
                value = int(text if exact is None else exact)
            elif kind == "float":
                exact = item.data(EXACT_VALUE_ROLE)
                value = float(text if exact is None else exact)
            else:
                value = parse_bool(text)
            if value != original:
                self.save.set_stat(name, value)

    def show_beta_notice(self) -> None:
        BetaNoticeDialog(self).exec()

    def _show_beta_notice_if_needed(self) -> None:
        key = "beta_notice_acknowledged"
        if bool(self.settings.value(key, False, type=bool)):
            return
        self.show_beta_notice()
        self.settings.setValue(key, True)

    def restore_save(self) -> None:
        target = self.current_path
        if target is None:
            start = self._preferred_save_directory()
            name, _ = QFileDialog.getOpenFileName(
                self, "Choose a save to restore", start, "Vice City saves (*.b);;All files (*)"
            )
            if not name:
                return
            target = Path(name)

        dialog = RestoreSaveDialog(target, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_backup is None:
            return

        if self.current_path and target.resolve() == self.current_path.resolve() and self.ui_dirty:
            unsaved = QMessageBox(self)
            unsaved.setIcon(QMessageBox.Icon.Warning)
            unsaved.setWindowTitle("Discard unsaved edits?")
            unsaved.setText(f"{target.name} has unsaved edits.")
            unsaved.setInformativeText("Unsaved edits will be discarded.")
            discard_button = unsaved.addButton(
                "Discard Edits and Continue", QMessageBox.ButtonRole.DestructiveRole
            )
            cancel_button = unsaved.addButton(QMessageBox.StandardButton.Cancel)
            unsaved.setDefaultButton(cancel_button)
            unsaved.exec()
            if unsaved.clickedButton() is not discard_button:
                return

        backup = dialog.selected_backup
        prompt = QMessageBox(self)
        prompt.setIcon(QMessageBox.Icon.Warning)
        prompt.setWindowTitle("Restore this backup?")
        prompt.setText(f"Restore {target.name} from {backup.name}?")
        restore_button = prompt.addButton("Restore Save", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = prompt.addButton(QMessageBox.StandardButton.Cancel)
        prompt.setDefaultButton(cancel_button)
        prompt.exec()
        if prompt.clickedButton() is not restore_button:
            return

        try:
            safety_backup = restore_backup(backup, target)
        except (ValueError, SaveFormatError, OSError) as error:
            LOGGER.exception("Could not restore %s to %s", backup, target)
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("Couldn't restore save")
            box.setText(str(error))
            detail = "The save was not replaced."
            if self.log_path:
                detail += f"\n\nLog: {self.log_path}"
            box.setInformativeText(detail)
            box.setStandardButtons(QMessageBox.StandardButton.Close)
            box.exec()
            return

        if self.current_path and target.resolve() == self.current_path.resolve():
            try:
                self._reload_saved_baseline(target)
            except (ValueError, SaveFormatError, OSError) as error:
                LOGGER.exception("Restore succeeded but UI reload failed for %s", target)
                QMessageBox.warning(
                    self, "Save restored",
                    f"The backup was restored, but the file could not be reloaded in the editor:\n{error}"
                )
                return
        elif self.save is None:
            self.open_path(target)

        LOGGER.info("Restore completed: backup=%s destination=%s safety_backup=%s", backup, target, safety_backup)
        self.statusBar().showMessage("Save restored.", 6000)

    def _reload_saved_baseline(self, destination: Path) -> None:
        refreshed = SaveFile.load(destination)
        self.save = refreshed
        self.current_path = destination
        self._opened_raw = bytes(refreshed.raw)
        self.source_format_value.setText(refreshed.profile.name)
        self.source_format_value.setToolTip(
            refreshed.profile.detail
        )
        self.output_format_combo.blockSignals(True)
        target_index = self.output_format_combo.findData(refreshed.profile.key)
        self.output_format_combo.setCurrentIndex(target_index if target_index >= 0 else -1)
        self.output_format_combo.blockSignals(False)
        self._populate(
            refreshed.player(), refreshed.world(), refreshed.weapons(), refreshed.pickups(),
            refreshed.car_generators(), refreshed.stored_cars(), refreshed.gangs(), refreshed.stats(),
        )
        self.ui_dirty = False
        self._clear_validation_marks()
        self._update_export_help()
        self._update_window_state()

    def _show_save_error(self, error: Exception, hint: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Couldn't save")
        box.setText(str(error))
        detail = hint
        if self.log_path:
            detail += f"\n\nLog: {self.log_path}"
        box.setInformativeText(detail)
        box.setStandardButtons(QMessageBox.StandardButton.Close)
        box.exec()


    def save_current(self) -> bool:
        if not self.save or not self.current_path or not self.save.profile.editable:
            return False
        target = self._selected_output_profile()
        if not target:
            QMessageBox.warning(self, "Choose an output format", "Choose an output format first.")
            return False
        if target.key != self.save.profile.key:
            self.statusBar().showMessage(f"Choose a destination for {target.name}.", 3500)
            return self.choose_save()
        if not self.ui_dirty:
            self.statusBar().showMessage("No changes to save.", 2500)
            return True

        issues = self._validate_form(mark_cells=True)
        if issues:
            self._show_validation_status(issues)
            self._focus_validation_issue(issues[0])
            return False

        destination = self.current_path
        try:
            LOGGER.info(
                "Saving in place: path=%s profile=%s backup=%s",
                destination, target.key, True,
            )
            self._apply_form()
            backup = save_safely(
                self.save, destination, target.key
            )
            self._reload_saved_baseline(destination)
        except (ValueError, SaveFormatError, OSError) as error:
            LOGGER.exception("Could not save in place to %s", destination)
            self._show_save_error(
                error, "Check that the file or folder is writable and not locked by another program."
            )
            return False

        if backup:
            message = f"Saved · Backup: {backup.name}"
        else:
            message = "Saved"
        self.statusBar().showMessage(message, 7000)
        return True

    def save_to_slot(self) -> bool:
        if not self.save or not self.current_path or not self.save.profile.editable:
            return False
        target = self._selected_output_profile()
        if not target:
            QMessageBox.warning(self, "Choose an output format", "Choose an output format first.")
            return False

        folder = self._configured_save_directory()
        if folder is None:
            prompt = QMessageBox(self)
            prompt.setIcon(QMessageBox.Icon.Information)
            prompt.setWindowTitle("Set a Save Folder")
            prompt.setText("Save to Slot uses your configured Save Folder.")
            set_folder = prompt.addButton("Set Save Folder…", QMessageBox.ButtonRole.AcceptRole)
            cancel_button = prompt.addButton(QMessageBox.StandardButton.Cancel)
            prompt.setDefaultButton(set_folder)
            prompt.exec()
            if prompt.clickedButton() is not set_folder:
                return False
            if not self.show_folder_settings():
                return False
            folder = self._configured_save_directory()
            if folder is None:
                return False

        issues = self._validate_form(mark_cells=True)
        if issues:
            self._show_validation_status(issues)
            self._focus_validation_issue(issues[0])
            return False

        dialog = SaveSlotDialog(folder, target.name, self.current_path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        if dialog.selected_slot is None or dialog.selected_path is None:
            return False

        slot = dialog.selected_slot
        destination = dialog.selected_path
        try:
            same_destination = destination.resolve() == self.current_path.resolve()
        except OSError:
            same_destination = destination == self.current_path

        if same_destination:
            if target.key != self.save.profile.key:
                QMessageBox.information(
                    self,
                    "Choose another slot",
                    "Format conversion requires a different destination slot or Save As location.",
                )
                return False
            return self.save_current()

        if destination.exists():
            prompt = QMessageBox(self)
            prompt.setIcon(QMessageBox.Icon.Warning)
            prompt.setWindowTitle(f"Replace Slot {slot}?")
            record = dialog.selected_record
            if record is not None and record.valid:
                prompt.setText(f'Slot {slot} contains "{record.mission_name}".')
            else:
                prompt.setText(f"Slot {slot} already contains a save file.")
            prompt.setInformativeText("A backup of the existing save will be created automatically before replacement.")
            replace_button = prompt.addButton(f"Replace Slot {slot}", QMessageBox.ButtonRole.DestructiveRole)
            cancel_button = prompt.addButton(QMessageBox.StandardButton.Cancel)
            prompt.setDefaultButton(cancel_button)
            prompt.exec()
            if prompt.clickedButton() is not replace_button:
                return False

        try:
            LOGGER.info(
                "Save to slot: source=%s destination=%s slot=%s source_profile=%s target_profile=%s backup=%s",
                self.current_path, destination, slot, self.save.profile.key, target.key, True,
            )
            if self.ui_dirty:
                self._apply_form()
            backup = save_safely(self.save, destination, target.key)
            self._reload_saved_baseline(destination)
        except (ValueError, SaveFormatError, OSError) as error:
            LOGGER.exception("Could not save to Slot %s at %s", slot, destination)
            self._show_save_error(
                error, "Check that the Save Folder is writable and the destination is not locked by another program."
            )
            return False

        message = f"Saved to Slot {slot}"
        if backup:
            message += f" · Backup: {backup.name}"
        self.statusBar().showMessage(message, 6000)
        return True

    def choose_save(self) -> bool:
        if not self.save or not self.current_path or not self.save.profile.editable:
            return False
        target = self._selected_output_profile()
        if not target:
            QMessageBox.warning(self, "Choose an output format", "Choose an output format first.")
            return False

        issues = self._validate_form(mark_cells=True)
        if issues:
            self._show_validation_status(issues)
            self._focus_validation_issue(issues[0])
            return False

        default = suggested_path(self.current_path, target.key, self.save.profile.key)
        configured_save_folder = self._configured_save_directory()
        if configured_save_folder is not None:
            default = configured_save_folder / default.name

        while True:
            name, _ = QFileDialog.getSaveFileName(
                self, f"Save as {target.name}", str(default), "Vice City saves (*.b);;All files (*)"
            )
            if not name:
                return False
            destination = Path(name)
            destination_existed = destination.exists()
            if not destination_existed:
                break

            prompt = QMessageBox(self)
            prompt.setIcon(QMessageBox.Icon.Warning)
            prompt.setWindowTitle("A file already exists here")
            prompt.setText(f"Replace {destination.name}?")
            prompt.setInformativeText("A backup of the existing file will be created automatically before replacement.")
            replace_button = prompt.addButton("Replace", QMessageBox.ButtonRole.DestructiveRole)
            another_button = prompt.addButton("Choose Another Name…", QMessageBox.ButtonRole.ActionRole)
            cancel_button = prompt.addButton(QMessageBox.StandardButton.Cancel)
            prompt.setDefaultButton(cancel_button)
            prompt.exec()
            clicked = prompt.clickedButton()
            if clicked is another_button:
                default = destination
                continue
            if clicked is not replace_button:
                return False
            break

        try:
            LOGGER.info(
                "Save As: source=%s destination=%s source_profile=%s target_profile=%s backup=%s",
                self.current_path, destination, self.save.profile.key, target.key, True,
            )
            if self.ui_dirty:
                self._apply_form()
            backup = save_safely(
                self.save, destination, target.key
            )
            self._reload_saved_baseline(destination)
        except (ValueError, SaveFormatError, OSError) as error:
            LOGGER.exception("Could not complete Save As to %s", destination)
            self._show_save_error(
                error, "Try another folder or check that the destination is writable and not locked by another program."
            )
            return False

        if backup:
            message = f"Saved: {destination.name} · Backup: {backup.name}"
        else:
            message = f"Saved: {destination.name}"
        self.statusBar().showMessage(message, 6000)
        return True

    def _confirm_unsaved(self, action: str) -> bool:
        if not self.save or not self.ui_dirty:
            return True
        filename = self.current_path.name if self.current_path else "the current save"
        variants = {
            "exit": ("Save edits before exiting?", "Save and Exit", "Exit Without Saving"),
            "open": ("Save edits before opening another file?", "Save and Open", "Discard Edits and Open"),
            "close": ("Save edits before closing this save?", "Save and Close", "Discard Edits and Close"),
        }
        title, save_label, discard_label = variants.get(
            action, ("Save unsaved edits?", "Save", "Discard Edits")
        )

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(f"{filename} has unsaved edits.")
        save_button = box.addButton(save_label, QMessageBox.ButtonRole.AcceptRole)
        discard_button = box.addButton(discard_label, QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(save_button)
        box.setEscapeButton(cancel_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_button:
            return self.save_current()
        if clicked is discard_button:
            return True
        return False

    def close_current_save(self) -> None:
        if not self.save:
            return
        if not self._confirm_unsaved("close"):
            return
        self.save = None
        self.current_path = None
        self._opened_raw = None
        self.ui_dirty = False
        self._set_loaded(False)
        self.statusBar().showMessage("Save closed.", 3000)

    def apply_theme(self, theme: str, initial: bool = False, force: bool = False) -> None:
        theme = "dark" if theme == "dark" else "light"
        if not initial and not force and theme == self.current_theme:
            return
        started = time.perf_counter()
        self.setUpdatesEnabled(False)
        try:
            self.setStyleSheet(DARK if theme == "dark" else LIGHT)
            self.current_theme = theme
        finally:
            self.setUpdatesEnabled(True)
            self.update()
        elapsed = time.perf_counter() - started
        LOGGER.info("Theme switched to %s in %.3fs", theme, elapsed)
        if not initial:
            label = self.current_appearance.title() if self.current_appearance != "system" else f"System ({theme})"
            self.statusBar().showMessage(f"{label} appearance applied.", 2500)

    def open_log_file(self) -> None:
        if self.log_path and self.log_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path)))

    def open_github(self) -> None:
        QDesktopServices.openUrl(QUrl(f"https://{GITHUB_REPO}"))

    def open_github_issues(self) -> None:
        QDesktopServices.openUrl(QUrl(f"https://{GITHUB_ISSUES}"))

    def show_about(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(f"About {APP_NAME}")
        box.setText(f"{APP_NAME} v{APP_VERSION}")
        box.setInformativeText(
            f"Author: {APP_AUTHOR}\n"
            f"GitHub: {GITHUB_REPO}\n"
            f"Issues: {GITHUB_ISSUES}\n"
            "License: MIT"
        )
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def closeEvent(self, event) -> None:  # Qt API name.
        if self._load_thread and self._load_thread.isRunning():
            event.ignore()
            self.statusBar().showMessage("A save is still being processed.", 3000)
            return
        if not self._confirm_unsaved("exit"):
            event.ignore()
            return
        self.settings.setValue("window_geometry", self.saveGeometry())
        self.settings.setValue("splitter_state", self.body_splitter.saveState())
        self.settings.setValue("last_page", self.tabs.currentIndex())
        self._save_table_layouts()
        event.accept()

    def resizeEvent(self, event) -> None:  # Qt API name.
        super().resizeEvent(event)
        self._refresh_file_state_text()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._load_thread and self._load_thread.isRunning():
            return
        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return
        path = Path(urls[0].toLocalFile())
        if path.suffix.lower() != ".b" or not path.is_file():
            self.statusBar().showMessage("Drop a Vice City .b save file to open it.", 2500)
            return
        self.statusBar().showMessage(f"Drop to open {path.name}")
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # Qt API name.
        self.statusBar().clearMessage()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if len(urls) != 1:
            return
        path = Path(urls[0].toLocalFile())
        if path.suffix.lower() != ".b" or not path.is_file():
            self.statusBar().showMessage("That file is not a Vice City .b save.", 3500)
            return
        if self._confirm_unsaved("open"):
            self.open_path(path)
            event.acceptProposedAction()


def _install_qt_logger() -> None:
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def qt_message_handler(mode, context, message):
        location = ""
        if context and getattr(context, "file", None):
            location = f" ({context.file}:{getattr(context, 'line', 0)})"
        LOGGER.log(levels.get(mode, logging.INFO), "Qt: %s%s", message, location)

    qInstallMessageHandler(qt_message_handler)


def _install_exception_logger() -> None:
    previous_hook = sys.excepthook

    def log_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            previous_hook(exc_type, exc_value, exc_traceback)
            return
        LOGGER.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        previous_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = log_exception


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    log_path = configure_logging()
    _install_exception_logger()
    _install_qt_logger()
    # Qt requires the scale-factor rounding policy to be configured before
    # QApplication creates the underlying QGuiApplication instance.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(arguments)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setWindowIcon(QIcon(str(application_icon_path())))
    app.setStyle("Fusion")
    LOGGER.info("Qt/PySide runtime initialized")
    initial = arguments[1] if len(arguments) > 1 else None
    window = MainWindow(initial, log_path)
    window.show()
    result = app.exec()
    LOGGER.info("Application exiting with code %s", result)
    return result
