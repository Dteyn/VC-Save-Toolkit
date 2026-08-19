"""Editable fixed-size records stored in Vice City save blocks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag
import math
import struct

from .garage_data import (
    STORAGE_GROUP_COUNT, STORED_CARS_PER_GROUP, stored_car_raw_index,
)


PICKUP_TYPES = (
    "Empty", "Shop item", "Street pickup", "Collect once", "Timed once",
    "Slow timed once", "Collectible", "Shop item (sold out)", "Money",
    "Inactive mine", "Armed mine", "Inactive nautical mine",
    "Armed nautical mine", "Floating package", "Floating package (afloat)",
    "Slow street pickup", "Asset revenue", "Locked property",
    "Property for sale",
)

VEHICLE_NAMES = (
    "Landstalker", "Idaho", "Stinger", "Linerunner", "Perennial", "Sentinel", "Rio",
    "Firetruck", "Trashmaster", "Stretch", "Manana", "Infernus", "Voodoo", "Pony", "Mule",
    "Cheetah", "Ambulance", "FBI Washington", "Moonbeam", "Esperanto", "Taxi", "Washington",
    "Bobcat", "Mr Whoopee", "BF Injection", "Hunter", "Police", "Enforcer", "Securicar",
    "Banshee", "Predator", "Bus", "Rhino", "Barracks", "Cuban Hermes", "Chopper", "Angel",
    "Coach", "Cabbie", "Stallion", "Rumpo", "RC Bandit", "Romero's Hearse", "Packer",
    "Sentinel XS", "Admiral", "Squalo", "Sea Sparrow", "Pizza Boy", "Gang Burrito", "Airtrain",
    "Dead Dodo", "Speeder", "Reefer", "Tropic", "Flatbed", "Yankee", "Caddy", "Zebra Cab",
    "Top Fun", "Skimmer", "PCJ-600", "Faggio", "Freeway", "RC Baron", "RC Raider", "Glendale",
    "Oceanic", "Sanchez", "Sparrow", "Patriot", "Love Fist Limo", "Coast Guard", "Dinghy",
    "Hermes", "Sabre", "Sabre Turbo", "Phoenix", "Walton", "Regina", "Comet", "Deluxo",
    "Burrito", "Spand Express", "Marquis", "Baggage Handler", "Kaufman Cab", "Maverick",
    "VCN Maverick", "Rancher", "FBI Rancher", "Virgo", "Greenwood", "Jetmax", "Hotring Racer",
    "Sandking", "Blista Compact", "Police Maverick", "Boxville", "Benson", "Mesa Grande",
    "RC Goblin", "Hotring Racer A", "Hotring Racer B", "Bloodring Banger A",
    "Bloodring Banger B", "Vice Cheetah",
)


# Common Vice City pickup model names.
PICKUP_MODEL_NAMES = {
    259: "Brass knuckles",
    260: "Screwdriver",
    261: "Golf club",
    262: "Nightstick",
    263: "Knife",
    264: "Baseball bat",
    265: "Hammer",
    266: "Cleaver",
    267: "Machete",
    268: "Katana",
    269: "Chainsaw",
    270: "Grenade",
    271: "Tear gas",
    272: "Molotov",
    273: "Missile",
    274: "Colt .45",
    275: "Python",
    276: "Ruger",
    277: "Chrome shotgun",
    278: "SPAS-12",
    279: "Stubby shotgun",
    280: "M4",
    281: "Tec-9",
    282: "Uzi",
    283: "Ingram",
    284: "MP5",
    285: "Sniper rifle",
    286: "PSG-1",
    287: "Rocket launcher",
    288: "Flamethrower",
    289: "M60",
    290: "Minigun",
    291: "Detonator",
    292: "Camera",
    365: "Information marker",
    366: "Health",
    367: "Adrenaline",
    368: "Body armour",
    375: "Police bribe",
    376: "Bonus",
    382: "Camera pickup",
    383: "Rampage",
    405: "Gun box",
    406: "Locked property",
    407: "Property for sale",
    408: "Asset revenue",
    409: "Clothes",
    410: "Hidden package",
    411: "Save-game pickup",
    431: "Craig's package",
}


def pickup_model_name(model_id: int) -> str:
    return PICKUP_MODEL_NAMES.get(int(model_id), "Custom model")


def pickup_model_choices() -> tuple[tuple[str, int], ...]:
    return tuple(
        (f"{name} ({model_id})", model_id)
        for model_id, name in sorted(PICKUP_MODEL_NAMES.items(), key=lambda item: (item[1].casefold(), item[0]))
    )


RADIO_STATIONS = (
    "Wildstyle", "Flash FM", "K-Chat", "Fever 105", "V-Rock", "VCPR",
    "Radio Espantoso", "Emotion 98.3", "Wave 103", "User tracks",
)


def color_name(color_id: int) -> str:
    if color_id == -1:
        return "Random"
    groups = ((0, 9, "Neutral"), (10, 19, "Red"),
              (20, 29, "Orange"), (30, 39, "Yellow"), (40, 49, "Green"),
              (50, 59, "Blue"), (60, 69, "Purple"), (70, 79, "Grey"),
              (80, 89, "Light"), (90, 94, "Dark"))
    for first, last, name in groups:
        if first <= color_id <= last:
            return f"{color_id} — {name} shade {color_id - first + 1}"
    return f"{color_id} — Unknown"

GANG_NAMES = (
    "Cubans", "Haitians", "Streetwannabes", "Diaz's gang", "Security guards",
    "Bikers", "Vercetti gang", "Golfers", "Gang 9",
)

_STAT_ORDER = """PeopleKilledByPlayer PeopleKilledByOthers CarsExploded BoatsExploded
TyresPopped RoundsFiredByPlayer PedsKilledOfThisType HelisDestroyed ProgressMade
TotalProgressInGame KgsOfExplosivesUsed BulletsThatHit HeadsPopped WantedStarsAttained
WantedStarsEvaded TimesArrested TimesDied DaysPassed SafeHouseVisits Sprayings
MaximumJumpDistance MaximumJumpHeight MaximumJumpFlips MaximumJumpSpins BestStuntJump
NumberOfUniqueJumpsFound TotalNumberOfUniqueJumps MissionsGiven PassengersDroppedOffWithTaxi
MoneyMadeWithTaxi IndustrialPassed CommercialPassed SuburbanPassed PamphletMissionPassed
NoMoreHurricanes DistanceTravelledOnFoot DistanceTravelledByCar DistanceTravelledByBike
DistanceTravelledByBoat DistanceTravelledByGolfCart DistanceTravelledByHelicoptor
DistanceTravelledByPlane LivesSavedWithAmbulance CriminalsCaught FiresExtinguished
HighestLevelVigilanteMission HighestLevelAmbulanceMission HighestLevelFireMission PhotosTaken
NumberKillFrenziesPassed TotalNumberKillFrenzies TotalNumberMissions FlightTime TimesDrowned
SeagullsKilled WeaponBudget FashionBudget LoanSharks StoresKnockedOff MovieStunts Assassinations
PizzasDelivered GarbagePickups IceCreamSold TopShootingRangeScore ShootingRank LongestWheelie
LongestStoppie Longest2Wheel LongestWheelieDist LongestStoppieDist Longest2WheelDist
PropertyBudget AutoPaintingBudget PropertyDestroyed NumPropertyOwned BloodRingKills BloodRingTime
PropertyOwned HighestChaseValue FastestTimes HighestScores BestPositions KillsSinceLastCheckpoint
TotalLegitimateKills LastMissionPassedName CheatedCount FavoriteRadioStationList""".split()
_FLOAT_STATS = set("""ProgressMade TotalProgressInGame MaximumJumpDistance MaximumJumpHeight
DistanceTravelledOnFoot DistanceTravelledByCar DistanceTravelledByBike DistanceTravelledByBoat
DistanceTravelledByGolfCart DistanceTravelledByHelicoptor DistanceTravelledByPlane WeaponBudget
FashionBudget LoanSharks StoresKnockedOff MovieStunts Assassinations PizzasDelivered GarbagePickups
IceCreamSold TopShootingRangeScore ShootingRank LongestWheelieDist LongestStoppieDist
Longest2WheelDist PropertyBudget AutoPaintingBudget HighestChaseValue FavoriteRadioStationList""".split())
_STAT_COUNTS = {"PedsKilledOfThisType": 23, "PropertyOwned": 15,
                "FastestTimes": 23, "HighestScores": 5, "BestPositions": 1,
                "LastMissionPassedName": 8, "FavoriteRadioStationList": 10}


STAT_INDEX_LABELS = {
    "PedsKilledOfThisType": (
        "Player 1", "Player 2", "Player 3", "Player 4",
        "Civilian male", "Civilian female", "Police", "Cuban gang",
        "Haitian gang", "Streetwannabe gang", "Diaz's gang", "Security guards",
        "Bikers", "Vercetti gang", "Golfers", "Gang 9", "Emergency",
        "Firefighter", "Criminal", "Unused ped type 1", "Prostitute",
        "Special", "Unused ped type 2",
    ),
    "PropertyOwned": (
        "Malibu Club", "Print Works", "Film Studio", "Ice Cream Factory",
        "Sunshine Autos", "Kaufman Cabs", "Boatyard", "Pole Position Club",
        "3321 Vice Point", "Links View Apartment", "El Swanko Casa",
        "1102 Washington Street", "Ocean Heights Apartment", "Skumole Shack",
        "Hyman Condo",
    ),
    "FastestTimes": (
        "Alloy Wheels of Steel", "The Driver", "Dirt Ring", "RC Plane Race",
        "RC Car Race", "RC Helicopter Pickup", "Terminal Velocity", "Ocean Drive",
        "Border Run", "Capital Cruise", "Tour!", "V.C. Endurance",
        "Downtown Chopper Checkpoint", "Ocean Beach Chopper Checkpoint",
        "Vice Point Chopper Checkpoint", "Little Haiti Chopper Checkpoint",
        "PCJ Playground", "Trial by Dirt", "Test Track", "Cone Crazy",
        "Hotring", "Hotring lap", "Checkpoint Charlie",
    ),
    "HighestScores": (
        "Shooter — highest score", "Shooter — best hit percentage",
        "Drug deals made", "Keepie-Uppy beach ball", "Unused",
    ),
    "FavoriteRadioStationList": (
        "Wildstyle", "Flash FM", "K-Chat", "Fever 105", "V-Rock", "VCPR",
        "Radio Espantoso", "Emotion 98.3", "Wave 103", "User tracks",
    ),
}


def build_stat_schema():
    schema = []
    offset = 0
    for name in _STAT_ORDER:
        count = _STAT_COUNTS.get(name, 1)
        if name == "PropertyOwned":
            kind, size = "bool", count
        elif name == "LastMissionPassedName":
            kind, size = "text", count
        else:
            kind, size = ("float" if name in _FLOAT_STATS else "int"), count * 4
        if kind == "text":
            schema.append((name, offset, kind))
        else:
            for index in range(count):
                label = name if count == 1 else f"{name} [{index}]"
                schema.append((label, offset + index * (1 if kind == "bool" else 4), kind))
        offset += size
    if offset != 595:
        raise AssertionError(f"Stats schema is {offset} bytes, expected 595")
    return tuple(schema)


STAT_SCHEMA = build_stat_schema()


def friendly_stat_name(name: str) -> str:
    base, separator, index_text = name.partition(" [")
    words = []
    current = ""
    for character in base:
        if character.isupper() and current:
            words.append(current)
            current = character
        else:
            current += character
    if current:
        words.append(current)
    label = " ".join(words).replace("Helicoptor", "Helicopter")
    if not separator:
        return label
    try:
        index = int(index_text.rstrip("]"))
    except ValueError:
        return f"{label} [{index_text}"
    labels = STAT_INDEX_LABELS.get(base)
    if labels and 0 <= index < len(labels):
        if base == "FavoriteRadioStationList":
            return f"Favorite radio station list — {labels[index]} listening time"
        return f"{label} — {labels[index]}"
    return f"{label} [{index}]"


def read_stats(data: bytes | bytearray, start: int) -> list[tuple[str, object, str]]:
    values = []
    for name, offset, kind in STAT_SCHEMA:
        if kind == "int":
            value = struct.unpack_from("<i", data, start + offset)[0]
        elif kind == "float":
            value = struct.unpack_from("<f", data, start + offset)[0]
        elif kind == "bool":
            value = bool(data[start + offset])
        else:
            value = bytes(data[start + offset:start + offset + 8]).split(b"\0", 1)[0].decode("ascii", "replace")
        values.append((name, value, kind))
    return values


def write_stat(data: bytearray, start: int, name: str, value: object) -> None:
    matches = [(offset, kind) for field, offset, kind in STAT_SCHEMA if field == name]
    if not matches:
        raise ValueError(f"Unknown statistic: {name}")
    offset, kind = matches[0]
    if kind == "int":
        struct.pack_into("<i", data, start + offset, int(value))
    elif kind == "float":
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{friendly_stat_name(name)} must be finite.")
        struct.pack_into("<f", data, start + offset, number)
    elif kind == "bool":
        data[start + offset] = int(bool(value))
    else:
        raise ValueError("The last mission key is managed by the game and is read-only.")




class StoredCarFlags(IntFlag):
    """Named proof flags persisted in a hideout-garage stored-car record."""

    BULLETPROOF = 1 << 0
    FIREPROOF = 1 << 1
    EXPLOSIONPROOF = 1 << 2
    COLLISIONPROOF = 1 << 3
    MELEEPROOF = 1 << 4


STORED_CAR_KNOWN_FLAG_MASK = int(
    StoredCarFlags.BULLETPROOF
    | StoredCarFlags.FIREPROOF
    | StoredCarFlags.EXPLOSIONPROOF
    | StoredCarFlags.COLLISIONPROOF
    | StoredCarFlags.MELEEPROOF
)


def stored_car_flag_names(flags: int) -> list[str]:
    mapping = (
        (StoredCarFlags.BULLETPROOF, "Bulletproof"),
        (StoredCarFlags.FIREPROOF, "Fireproof"),
        (StoredCarFlags.EXPLOSIONPROOF, "Explosionproof"),
        (StoredCarFlags.COLLISIONPROOF, "Collisionproof"),
        (StoredCarFlags.MELEEPROOF, "Meleeproof"),
    )
    return [label for flag, label in mapping if flags & int(flag)]


def stored_car_flags_summary(flags: int) -> str:
    names = stored_car_flag_names(flags)
    unknown = (int(flags) & 0xFFFFFFFF) & ~STORED_CAR_KNOWN_FLAG_MASK
    if not names and not unknown:
        return "None"
    summary = " · ".join(names) if names else "No known flags"
    if unknown:
        summary += " · + unknown"
    return summary


@dataclass
class PickupRecord:
    slot: int
    position: tuple[float, float, float]
    revenue: float
    quantity: int
    model_id: int
    pickup_type: int
    removed: bool
    text_key: str


@dataclass
class CarGeneratorRecord:
    slot: int
    model_id: int
    position: tuple[float, float, float]
    angle: float
    color_1: int
    color_2: int
    force_spawn: bool
    alarm_chance: int
    lock_chance: int
    uses_remaining: int


@dataclass
class StoredCarRecord:
    garage: int
    slot: int
    model_id: int
    position: tuple[float, float, float]
    angles: tuple[float, float, float]
    flags: int
    color_1: int
    color_2: int
    radio: int
    bomb_type: int
    # None preserves the existing variation bytes.
    variation_a: int | None = None
    variation_b: int | None = None


@dataclass(frozen=True)
class GarageGeometry:
    garage: int
    corner: tuple[float, float]
    inf_z: float
    dir1: tuple[float, float]
    dir2: tuple[float, float]
    sup_z: float
    dir1_len: float
    dir2_len: float
    bounds: tuple[float, float, float, float]


@dataclass
class GangRecord:
    index: int
    weapon_1: int
    weapon_2: int


def finite(values) -> bool:
    return all(math.isfinite(value) for value in values)


def pickup_layout(profile: str) -> tuple[int, int, int, int, int, int, int]:
    if profile == "compatible52":
        # Compatible 32-bit save serialization is tightly packed after the two
        # pool-index fields: quantity@24, model@34, text@38, type@46, removed@47.
        return 52, 24, 34, 38, 46, 47, 16
    if profile == "pointer64":
        return 64, 32, 42, 46, 54, 55, 16
    raise ValueError(f"Unknown pickup profile: {profile}")


def read_pickups(data: bytes | bytearray, start: int, profile: str) -> list[PickupRecord]:
    stride, quantity_at, model_at, text_at, type_at, removed_at, revenue_at = pickup_layout(profile)
    records = []
    for slot in range(336):
        offset = start + slot * stride
        x, y, z = struct.unpack_from("<3f", data, offset)
        revenue = struct.unpack_from("<f", data, offset + revenue_at - 4)[0]
        quantity = struct.unpack_from("<I", data, offset + quantity_at)[0]
        model_id = struct.unpack_from("<h", data, offset + model_at)[0]
        text = bytes(data[offset + text_at:offset + text_at + 8]).split(b"\0", 1)[0].decode("ascii", "replace")
        pickup_type = data[offset + type_at]
        removed = bool(data[offset + removed_at])
        records.append(PickupRecord(slot, (x, y, z), revenue, quantity,
                                    model_id, pickup_type, removed, text))
    return records


def write_pickup(data: bytearray, start: int, profile: str, record: PickupRecord) -> None:
    if not finite((*record.position, record.revenue)):
        raise ValueError("Pickup coordinates and revenue must be finite.")
    if not 0 <= record.pickup_type < len(PICKUP_TYPES):
        raise ValueError("Invalid pickup type.")
    if not -32768 <= record.model_id <= 32767 or not 0 <= record.quantity <= 0xFFFFFFFF:
        raise ValueError("Pickup model or quantity is out of range.")
    stride, quantity_at, model_at, _, type_at, removed_at, revenue_at = pickup_layout(profile)
    offset = start + record.slot * stride
    struct.pack_into("<3f", data, offset, *record.position)
    struct.pack_into("<f", data, offset + revenue_at - 4, record.revenue)
    struct.pack_into("<I", data, offset + quantity_at, record.quantity)
    struct.pack_into("<h", data, offset + model_at, record.model_id)
    data[offset + type_at] = record.pickup_type
    data[offset + removed_at] = int(record.removed)


def read_car_generators(data: bytes | bytearray, start: int) -> list[CarGeneratorRecord]:
    count = struct.unpack_from("<I", data, start + 12)[0]
    count = min(count, 185)
    array = start + 28
    records = []
    for slot in range(count):
        offset = array + slot * 44
        model = struct.unpack_from("<i", data, offset)[0]
        position = struct.unpack_from("<3f", data, offset + 4)
        angle = struct.unpack_from("<f", data, offset + 16)[0]
        color_1, color_2 = struct.unpack_from("<2h", data, offset + 20)
        force, alarm, lock = struct.unpack_from("<3B", data, offset + 24)
        uses = struct.unpack_from("<H", data, offset + 40)[0]
        records.append(CarGeneratorRecord(slot, model, position, angle, color_1,
                                          color_2, bool(force), alarm, lock, uses))
    return records


def write_car_generator(data: bytearray, start: int, record: CarGeneratorRecord) -> None:
    if not finite((*record.position, record.angle)):
        raise ValueError("Car generator coordinates and angle must be finite.")
    if not -32768 <= record.color_1 <= 32767 or not -32768 <= record.color_2 <= 32767:
        raise ValueError("Vehicle colors are out of range.")
    offset = start + 28 + record.slot * 44
    struct.pack_into("<i3ff2h", data, offset, record.model_id, *record.position,
                     record.angle, record.color_1, record.color_2)
    struct.pack_into("<3B", data, offset + 24, int(record.force_spawn),
                     record.alarm_chance, record.lock_chance)
    struct.pack_into("<H", data, offset + 40, record.uses_remaining)


def _stored_car_layout(record_size: int) -> tuple[int, int]:
    """Return (flags width, colour offset) for one serialized CStoredCar.

    Retail/Win64 MSVC saves use a 40-byte record with the bitfield storage unit
    occupying bytes 28..31. Quest ARM64 follows the AAPCS64 bitfield ABI and
    places the six int8 fields immediately after the used flag byte, producing a
    36-byte record.
    """
    if record_size == 40:
        return 4, 32
    if record_size == 36:
        return 1, 29
    raise ValueError(f"Unsupported stored-car record size: {record_size}")


def read_stored_cars(
    data: bytes | bytearray, start: int, record_size: int = 40
) -> list[StoredCarRecord]:
    flags_width, colour_at = _stored_car_layout(record_size)
    array = start + 44
    records = []
    # File order is slot-major, then garage.
    for slot in range(STORED_CARS_PER_GROUP):
        for garage in range(STORAGE_GROUP_COUNT):
            offset = array + stored_car_raw_index(garage, slot) * record_size
            model = struct.unpack_from("<i", data, offset)[0]
            position = struct.unpack_from("<3f", data, offset + 4)
            angles = struct.unpack_from("<3f", data, offset + 16)
            if flags_width == 4:
                flags = struct.unpack_from("<I", data, offset + 28)[0] & 0x1F
            else:
                flags = data[offset + 28] & 0x1F
            color_1, color_2, radio, variation_a, variation_b, bomb = struct.unpack_from(
                "<6b", data, offset + colour_at
            )
            records.append(StoredCarRecord(garage, slot, model, position, angles,
                                           flags, color_1, color_2, radio, bomb,
                                           variation_a, variation_b))
    return sorted(records, key=lambda item: (item.garage, item.slot))


def write_stored_car(
    data: bytearray, start: int, record: StoredCarRecord, record_size: int = 40
) -> None:
    if not finite((*record.position, *record.angles)):
        raise ValueError("Stored-car coordinates and angles must be finite.")
    if not 0 <= record.flags <= 0x1F:
        raise ValueError("Stored-car protection flags must be between 0 and 31.")
    flags_width, colour_at = _stored_car_layout(record_size)
    offset = start + 44 + stored_car_raw_index(record.garage, record.slot) * record_size
    struct.pack_into("<i3f3f", data, offset, record.model_id, *record.position, *record.angles)
    if flags_width == 4:
        raw_flags = struct.unpack_from("<I", data, offset + 28)[0]
        struct.pack_into("<I", data, offset + 28, (raw_flags & ~0x1F) | (record.flags & 0x1F))
    else:
        data[offset + 28] = (data[offset + 28] & 0xE0) | (record.flags & 0x1F)
    struct.pack_into("<3b", data, offset + colour_at,
                     record.color_1, record.color_2, record.radio)
    if record.variation_a is not None:
        if not -128 <= record.variation_a <= 127:
            raise ValueError("Stored-car variation A is out of range.")
        struct.pack_into("<b", data, offset + colour_at + 3, record.variation_a)
    if record.variation_b is not None:
        if not -128 <= record.variation_b <= 127:
            raise ValueError("Stored-car variation B is out of range.")
        struct.pack_into("<b", data, offset + colour_at + 4, record.variation_b)
    struct.pack_into("<b", data, offset + colour_at + 5, record.bomb_type)


# Compatible saves store 32 fixed-size garage records after the 44-byte header
# and 48 stored-car records. Quest differs only in the standalone CStoredCar ABI.
_GARAGE_RECORD_SIZE = 168
_MAX_REASONABLE_GARAGE_DIMENSION = 200.0


def _safehouse_index_for_type(garage_type: int) -> int | None:
    if 16 <= garage_type <= 18:
        return garage_type - 16
    if 24 <= garage_type <= 32:
        return garage_type - 21
    return None


def read_hideout_garage_capacities(
    data: bytes | bytearray, start: int, garage_record_size: int = 168,
    stored_car_record_size: int = 40,
) -> dict[int, int]:
    """Read m_nMaxStoredCars from serialized hideout CGarage headers."""
    if garage_record_size not in (168, 184):
        return {}
    result: dict[int, int] = {}
    base = start + 44 + STORAGE_GROUP_COUNT * STORED_CARS_PER_GROUP * stored_car_record_size
    for index in range(32):
        offset = base + index * garage_record_size
        if offset + 3 > len(data):
            break
        safehouse = _safehouse_index_for_type(data[offset])
        if safehouse is not None:
            result[safehouse] = int(data[offset + 2])
    return result


def read_hideout_garage_geometries(
    data: bytes | bytearray, start: int, garage_record_size: int = 168,
    stored_car_record_size: int = 40,
) -> dict[int, GarageGeometry]:
    """Decode the persistent geometry fields for the 12 hideout garage types."""
    if garage_record_size not in (168, 184):
        return {}
    geometry_shift = 12 if garage_record_size == 184 else 0
    result: dict[int, GarageGeometry] = {}
    base = start + 44 + STORAGE_GROUP_COUNT * STORED_CARS_PER_GROUP * stored_car_record_size
    for index in range(32):
        offset = base + index * garage_record_size
        if offset + garage_record_size > len(data):
            break
        safehouse = _safehouse_index_for_type(data[offset])
        if safehouse is None:
            continue

        corner = struct.unpack_from("<2f", data, offset + 28 + geometry_shift)
        inf_z = struct.unpack_from("<f", data, offset + 36 + geometry_shift)[0]
        dir1 = struct.unpack_from("<2f", data, offset + 40 + geometry_shift)
        dir2 = struct.unpack_from("<2f", data, offset + 48 + geometry_shift)
        sup_z = struct.unpack_from("<f", data, offset + 56 + geometry_shift)[0]
        dir1_len = struct.unpack_from("<f", data, offset + 60 + geometry_shift)[0]
        dir2_len = struct.unpack_from("<f", data, offset + 64 + geometry_shift)[0]
        bounds = struct.unpack_from("<4f", data, offset + 68 + geometry_shift)
        values = (*corner, inf_z, *dir1, *dir2, sup_z, dir1_len, dir2_len, *bounds)
        if not finite(values):
            continue
        if not (0.1 < dir1_len <= _MAX_REASONABLE_GARAGE_DIMENSION and
                0.1 < dir2_len <= _MAX_REASONABLE_GARAGE_DIMENSION):
            continue
        if math.hypot(*dir1) < 0.1 or math.hypot(*dir2) < 0.1:
            continue
        result[safehouse] = GarageGeometry(
            safehouse, corner, inf_z, dir1, dir2, sup_z,
            dir1_len, dir2_len, bounds,
        )
    return result



def compact_color_name(color_id: int) -> str:
    """Return a compact vehicle-colour label."""
    if color_id == -1:
        return "Random (-1)"
    groups = ((0, 9, "Neutral"), (10, 19, "Red"), (20, 29, "Orange"),
              (30, 39, "Yellow"), (40, 49, "Green"), (50, 59, "Blue"),
              (60, 69, "Purple"), (70, 79, "Grey"), (80, 89, "Light"),
              (90, 94, "Dark"))
    for first, last, name in groups:
        if first <= color_id <= last:
            return f"{name} {color_id - first + 1} ({color_id})"
    return f"Unknown ({color_id})"


def read_gangs(data: bytes | bytearray, start: int) -> list[GangRecord]:
    records = []
    for index in range(9):
        offset = start + 8 + index * 24
        records.append(GangRecord(index, struct.unpack_from("<i", data, offset + 16)[0],
                                  struct.unpack_from("<i", data, offset + 20)[0]))
    return records


def write_gang(data: bytearray, start: int, record: GangRecord) -> None:
    if not 0 <= record.weapon_1 <= 36 or not 0 <= record.weapon_2 <= 36:
        raise ValueError("Gang weapons must be valid inventory weapon types.")
    offset = start + 8 + record.index * 24
    struct.pack_into("<2i", data, offset + 16, record.weapon_1, record.weapon_2)
