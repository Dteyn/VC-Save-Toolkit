"""Garage storage labels, capacity rules, and automatic vehicle placement."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Protocol


GAMEPLAY_GARAGE_NAMES = (
    "El Swanko Casa",
    "Hyman Condo (garage 1)",
    "Hyman Condo (garage 2)",
    "Hyman Condo (garage 3)",
    "Ocean Heights Apartment",
    "Links View Apartment",
    "Sunshine Autos (garage 1)",
    "Sunshine Autos (garage 2)",
    "Sunshine Autos (garage 3)",
    "Sunshine Autos (garage 4)",
    "Vercetti Estate",
)

STORAGE_GROUP_NAMES = GAMEPLAY_GARAGE_NAMES + ("Reserved storage group 12",)
STORAGE_GROUP_COUNT = 12
STORED_CARS_PER_GROUP = 4
TOTAL_STORED_CAR_RECORDS = STORAGE_GROUP_COUNT * STORED_CARS_PER_GROUP

STOCK_GARAGE_CAPACITIES = {
    0: 1,
    1: 4,
    2: 2,
    3: 2,
    4: 1,
    5: 1,
    6: 2,
    7: 2,
    8: 2,
    9: 2,
    10: 2,
}


@dataclass(frozen=True)
class GaragePlacementGeometry:
    corner: tuple[float, float]
    inf_z: float
    dir1: tuple[float, float]
    dir2: tuple[float, float]
    sup_z: float
    dir1_len: float
    dir2_len: float


# Stock geometry is a fallback for saves created before a property garage has
# been instantiated. When a serialized CGarage exists, its geometry is used.
STOCK_GARAGE_GEOMETRIES = {
    0: GaragePlacementGeometry((450.135986, 641.028992), 10.112000, (0.0, -1.0), (1.0, 0.0), 13.092000, 5.302979, 7.841003),
    1: GaragePlacementGeometry((-848.224976, 1303.119019), 10.421000, (-0.32545218, 0.94555855), (0.94574797, 0.32490119), 15.816000, 16.690645, 12.046556),
    2: GaragePlacementGeometry((-825.466003, 1311.499023), 10.537000, (-0.32506588, 0.94569141), (0.9456718, 0.32512289), 15.061000, 9.825607, 8.784239),
    3: GaragePlacementGeometry((-816.369995, 1314.689941), 10.582000, (0.94833815, 0.31726149), (-0.32200834, 0.94673687), 15.061000, 8.731030, 9.844413),
    4: GaragePlacementGeometry((27.143000, -1483.953979), 9.423000, (-0.9921847, 0.12477759), (-0.6566689, -0.75417894), 12.994000, 4.567698, 8.798955),
    5: GaragePlacementGeometry((303.997986, 400.717987), 12.025000, (-0.95373642, 0.30064416), (-0.2655037, 0.96410978), 16.044001, 5.558134, 10.233303),
    6: GaragePlacementGeometry((-981.653992, -802.265015), 6.325000, (-1.0, 0.0), (0.0, -1.0), 10.730000, 9.473022, 19.599976),
    7: GaragePlacementGeometry((-992.416016, -802.265015), 6.325000, (-1.0, 0.0), (0.0, -1.0), 10.730000, 9.472961, 19.599976),
    8: GaragePlacementGeometry((-1003.770996, -802.265015), 6.325000, (-1.0, 0.0), (0.0, -1.0), 10.730000, 9.473022, 19.599976),
    9: GaragePlacementGeometry((-1015.435974, -802.265015), 6.325000, (-1.0, 0.0), (0.0, -1.0), 10.730000, 9.473083, 19.599976),
    10: GaragePlacementGeometry((-362.119995, -550.213989), 11.722000, (0.0, 1.0), (1.0, 0.0), 15.160000, 10.729980, 9.000000),
}

# Resting vehicle-origin heights measured from the garage floor in known-good
# stock Vice City saves. The value is stable for a model regardless of garage.
MODEL_RESTING_Z_OFFSETS = {
    131: 0.848, 132: 0.791, 135: 0.870, 139: 0.891, 140: 0.775,
    141: 0.749, 142: 0.890, 143: 1.246, 145: 0.833, 150: 0.803, 152: 1.111,
    154: 0.974, 155: 1.604, 156: 0.833, 159: 0.896, 162: 1.242,
    164: 0.801, 168: 1.016, 169: 0.919, 172: 0.858, 175: 1.006, 178: 0.621,
    189: 1.255, 191: 0.570, 193: 0.567, 198: 0.674, 200: 1.306, 201: 0.900,
    205: 0.799, 206: 0.959, 207: 0.891, 208: 1.044, 210: 0.864,
    213: 1.061, 216: 1.178, 220: 1.124, 224: 0.885, 225: 1.548,
    226: 0.801, 230: 1.113, 232: 0.910, 233: 0.910, 234: 0.834,
    235: 0.747, 236: 0.814,
}

_BIKE_MODELS = {166, 178, 191, 192, 193, 198}
_HELICOPTER_MODELS = {155, 165, 177, 199, 217, 218, 227}
_TALL_VEHICLE_MODELS = {
    133, 137, 138, 143, 144, 146, 157, 161, 162, 163, 167, 173,
    185, 186, 189, 200, 213, 219, 220, 225, 228, 229, 230,
}
_VERTICAL_CLEARANCE = 0.08
_MIN_FORWARD_MAGNITUDE = 0.1

# Most stock garages face opposite the first/longest axis; Sunshine and the
# mansion face with it. Direction sign does not affect fit but gives a natural
# parked orientation.
_FORWARD_SIGN = {0: -1.0, 1: -1.0, 2: -1.0, 3: -1.0, 4: -1.0, 5: -1.0,
                 6: 1.0, 7: 1.0, 8: 1.0, 9: 1.0, 10: 1.0}


@dataclass(frozen=True)
class GaragePose:
    position: tuple[float, float, float]
    forward: tuple[float, float, float]
    source: str


class StoredCarLike(Protocol):
    garage: int
    slot: int
    position: tuple[float, float, float]
    angles: tuple[float, float, float]


class GarageGeometryLike(Protocol):
    corner: tuple[float, float]
    inf_z: float
    dir1: tuple[float, float]
    dir2: tuple[float, float]
    sup_z: float
    dir1_len: float
    dir2_len: float


def stored_car_raw_index(garage: int, slot: int) -> int:
    """Return the on-disk CStoredCar index (slot-major, then garage)."""
    if not 0 <= garage < STORAGE_GROUP_COUNT or not 0 <= slot < STORED_CARS_PER_GROUP:
        raise ValueError("Garage must be 0..11 and slot must be 0..3.")
    return slot * STORAGE_GROUP_COUNT + garage


def garage_slot_from_raw_index(raw_index: int) -> tuple[int, int]:
    if not 0 <= raw_index < TOTAL_STORED_CAR_RECORDS:
        raise ValueError("Stored-car raw index must be 0..47.")
    return raw_index % STORAGE_GROUP_COUNT, raw_index // STORAGE_GROUP_COUNT


def effective_garage_capacity(garage: int, saved_capacities: Mapping[int, int] | None = None) -> int:
    if not 0 <= garage < len(GAMEPLAY_GARAGE_NAMES):
        return 0
    if saved_capacities is not None and garage in saved_capacities:
        try:
            value = int(saved_capacities[garage])
        except (TypeError, ValueError):
            value = STOCK_GARAGE_CAPACITIES.get(garage, 0)
        return max(0, min(STORED_CARS_PER_GROUP, value))
    return STOCK_GARAGE_CAPACITIES.get(garage, 0)


def is_gameplay_garage_slot(garage: int, slot: int, saved_capacities: Mapping[int, int] | None = None) -> bool:
    return 0 <= slot < effective_garage_capacity(garage, saved_capacities)


def is_out_of_capacity_record(garage: int, slot: int, saved_capacities: Mapping[int, int] | None = None) -> bool:
    return not is_gameplay_garage_slot(garage, slot, saved_capacities)


def should_show_garage_record(garage: int, slot: int, occupied: bool,
                              saved_capacities: Mapping[int, int] | None = None) -> bool:
    return bool(occupied or is_gameplay_garage_slot(garage, slot, saved_capacities))


def normalize_xy(x: float, y: float) -> tuple[float, float]:
    length = math.hypot(x, y)
    if not math.isfinite(length) or length < 1e-6:
        return 1.0, 0.0
    return x / length, y / length


def normalize_forward(forward: tuple[float, float, float]) -> tuple[float, float, float]:
    nx, ny = normalize_xy(forward[0], forward[1])
    return nx, ny, 0.0


def has_useful_stored_pose(record: StoredCarLike) -> bool:
    x, y, z = record.position
    fx, fy, fz = record.angles
    if not all(math.isfinite(v) for v in (x, y, z, fx, fy, fz)):
        return False
    if abs(x) < 0.01 and abs(y) < 0.01:
        return False
    return math.hypot(fx, fy) >= _MIN_FORWARD_MAGNITUDE


def vehicle_resting_z_offset(model_id: int | None) -> float:
    """Return a safe vehicle-origin height above a garage floor."""
    if model_id in MODEL_RESTING_Z_OFFSETS:
        base = MODEL_RESTING_Z_OFFSETS[int(model_id)]
    elif model_id in _BIKE_MODELS:
        base = 0.70
    elif model_id in _HELICOPTER_MODELS:
        base = 1.60
    elif model_id in _TALL_VEHICLE_MODELS:
        base = 1.35
    else:
        base = 1.05
    return base + _VERTICAL_CLEARANCE


def _geometry_is_usable(geometry: GarageGeometryLike) -> bool:
    values = (*geometry.corner, geometry.inf_z, *geometry.dir1, *geometry.dir2,
              geometry.sup_z, geometry.dir1_len, geometry.dir2_len)
    return (
        all(math.isfinite(v) for v in values)
        and geometry.sup_z > geometry.inf_z + 1.0
        and 0.1 < geometry.dir1_len <= 200.0
        and 0.1 < geometry.dir2_len <= 200.0
        and math.hypot(*geometry.dir1) >= 0.1
        and math.hypot(*geometry.dir2) >= 0.1
    )


def _normalised_axes(geometry: GarageGeometryLike) -> tuple[tuple[float, float], tuple[float, float]]:
    return normalize_xy(*geometry.dir1), normalize_xy(*geometry.dir2)


def _point_fractions(geometry: GarageGeometryLike, x: float, y: float) -> tuple[float, float] | None:
    """Solve p = corner + u*dir1*len1 + v*dir2*len2."""
    d1, d2 = _normalised_axes(geometry)
    a = d1[0] * geometry.dir1_len
    b = d2[0] * geometry.dir2_len
    c = d1[1] * geometry.dir1_len
    d = d2[1] * geometry.dir2_len
    det = a * d - b * c
    if abs(det) < 1e-6:
        return None
    px = x - geometry.corner[0]
    py = y - geometry.corner[1]
    u = (px * d - b * py) / det
    v = (a * py - px * c) / det
    return u, v


def _retained_xy_is_safe(record: StoredCarLike, geometry: GarageGeometryLike) -> bool:
    if not has_useful_stored_pose(record):
        return False
    fractions = _point_fractions(geometry, record.position[0], record.position[1])
    if fractions is None:
        return False
    u, v = fractions
    return 0.08 <= u <= 0.92 and 0.08 <= v <= 0.92


def _slot_fractions(capacity: int, slot: int, geometry: GarageGeometryLike) -> tuple[float, float]:
    """Return (dir1 fraction, dir2 fraction) with generous wall/door margins."""
    major_is_dir1 = geometry.dir1_len >= geometry.dir2_len
    if capacity <= 1:
        major, minor = 0.52, 0.50
    elif capacity == 2:
        major = 0.56
        minor = (0.32, 0.68)[min(slot, 1)]
    else:
        grid = ((0.35, 0.32), (0.35, 0.68), (0.68, 0.32), (0.68, 0.68))
        major, minor = grid[min(slot, 3)]
    return (major, minor) if major_is_dir1 else (minor, major)


def _pose_from_geometry(garage: int, slot: int, capacity: int,
                        geometry: GarageGeometryLike, model_id: int | None) -> GaragePose | None:
    if not _geometry_is_usable(geometry) or not 0 <= slot < min(max(capacity, 0), STORED_CARS_PER_GROUP):
        return None
    d1, d2 = _normalised_axes(geometry)
    u, v = _slot_fractions(capacity, slot, geometry)
    x = geometry.corner[0] + d1[0] * geometry.dir1_len * u + d2[0] * geometry.dir2_len * v
    y = geometry.corner[1] + d1[1] * geometry.dir1_len * u + d2[1] * geometry.dir2_len * v

    requested_z = geometry.inf_z + vehicle_resting_z_offset(model_id)
    # Keep the origin comfortably below the saved garage ceiling. Tall vehicles
    # in physically small garages may still be unsuitable, but never start them
    # below the floor merely because a generic model offset was used.
    z = min(requested_z, geometry.sup_z - 0.55)
    z = max(z, geometry.inf_z + 0.45)

    major = d1 if geometry.dir1_len >= geometry.dir2_len else d2
    sign = _FORWARD_SIGN.get(garage, 1.0)
    forward = normalize_forward((major[0] * sign, major[1] * sign, 0.0))
    return GaragePose((x, y, z), forward, "garage_geometry")


def resolve_new_garage_vehicle_pose(
    record: StoredCarLike,
    geometries: Mapping[int, GarageGeometryLike] | None = None,
    model_id: int | None = None,
    capacity: int | None = None,
) -> GaragePose | None:
    """Resolve a model-aware pose for a new garage vehicle.

    Existing empty-record XY/heading data is reused when it still lies safely
    inside the garage, but Z is recalculated for the selected vehicle model.
    Otherwise the pose is derived from the serialized CGarage geometry. Stock
    geometry is only the fallback for garages not yet present in the save.
    """
    if not 0 <= record.garage < len(GAMEPLAY_GARAGE_NAMES):
        return None
    if capacity is None:
        capacity = STOCK_GARAGE_CAPACITIES.get(record.garage, 0)
    if not 0 <= record.slot < min(max(capacity, 0), STORED_CARS_PER_GROUP):
        return None

    geometry = None
    if geometries:
        geometry = geometries.get(record.garage)
    if geometry is None:
        geometry = STOCK_GARAGE_GEOMETRIES.get(record.garage)
    if geometry is None or not _geometry_is_usable(geometry):
        return None

    if _retained_xy_is_safe(record, geometry):
        z = min(geometry.inf_z + vehicle_resting_z_offset(model_id), geometry.sup_z - 0.55)
        z = max(z, geometry.inf_z + 0.45)
        return GaragePose(
            (record.position[0], record.position[1], z),
            normalize_forward(record.angles),
            "retained",
        )

    return _pose_from_geometry(record.garage, record.slot, capacity, geometry, model_id)


def placement_source_label(source: str) -> str:
    return {
        "retained": "Retained position",
        "garage_geometry": "Garage geometry",
    }.get(source, source.replace("_", " ").title())
