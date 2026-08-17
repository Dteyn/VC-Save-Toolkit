"""Vice City save parser and writer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import math
from pathlib import Path
import struct

from .records import (
    CarGeneratorRecord, GangRecord, PickupRecord, StoredCarRecord,
    read_car_generators, read_gangs, read_pickups, read_stored_cars,
    read_hideout_garage_capacities, read_hideout_garage_geometries,
    write_car_generator, write_gang, write_pickup,
    write_stored_car, read_stats, write_stat,
)


class SaveFormatError(ValueError):
    """Raised for invalid or unsupported save data."""


@dataclass(frozen=True)
class SaveProfile:
    key: str
    name: str
    editable: bool
    detail: str
    player_info_size: int | None = None
    pickup_size: int | None = None
    cranes_size: int | None = None
    phone_size: int | None = None
    particle_stride: int | None = None
    script_path_header_size: int | None = None
    garage_record_size: int | None = None
    simple_variant: str = "retail"


STANDARD_PC_PROFILE = SaveProfile(
    "gta-vc-pc", "Retail PC (CD / non-Steam)", True,
    "Original retail Windows save format.",
    368, 17556, 1000, 2608, 132, 52, 168, "retail",
)
STEAM_PC_PROFILE = SaveProfile(
    "gta-vc-steam", "Steam PC", True,
    "Steam PC format with the extra Block 0 release marker.",
    368, 17556, 1000, 2608, 132, 52, 168, "steam",
)
EXTENDED_PC_PROFILE = SaveProfile(
    "vc-pc-extended", "reVC-compatible format", True,
    "32-bit reVC-compatible format with extended player information.",
    416, 17556, 1000, 2608, 132, 52, 168, "retail",
)
VICE_CITY_VR_PROFILE = SaveProfile(
    "vice-city-vr", "Vice City VR", True,
    "64-bit Vice City VR format with wider runtime records.",
    416, 21588, 1160, 4408, 152, 88, 184, "retail",
)
SUPPORTED_PROFILES = (
    STANDARD_PC_PROFILE, STEAM_PC_PROFILE, EXTENDED_PC_PROFILE, VICE_CITY_VR_PROFILE,
)
SUPPORTED_PROFILE_BY_KEY = {profile.key: profile for profile in SUPPORTED_PROFILES}
UNKNOWN_PROFILE = SaveProfile(
    "vc-unknown", "Vice City save (unclassified)", False,
    "Valid Vice City save with an unsupported block layout.",
)


BLOCK_NAMES = (
    "Simple variables + scripts", "Ped pool", "Garages", "Game logic",
    "Vehicle pool", "Object pool", "Paths", "Cranes", "Pickups",
    "Phone info", "Restart points", "Radar blips", "Zones", "Gang data",
    "Car generators", "Particle objects", "Audio script objects",
    "Script paths", "Player info", "Stats", "Set pieces", "Streaming",
    "Ped types",
)
SIMPLE_SIZE = 0xE4
DECLARED_SIZE = 201729
PLAYER_SAVE_SIZE = 1752
MAX_BLOCK_SIZE = 100_000

PED_TYPES_BLOCK_INDEX = 22
PED_TYPES_INNER_SIZE = 744
PED_TYPES_HEADER_SIZE = 8
PED_TYPE_RECORD_COUNT = 23
PED_TYPE_RECORD_SIZE = 32
PED_TYPE_THREATS_OFFSET = 24
PEDTYPE_CIVMALE = 4
PEDTYPE_SPECIAL = 21
PED_FLAG_PLAYER1 = 0x00000001
MAYHEM_THREAT_MASK = 0x000FFFFF

# Standard Vice City relationship values used to rebuild a table overwritten by
# FIGHTFIGHTFIGHT. The cheat destroys the previous values, so this is a stock
# restore rather than a byte-for-byte inverse.
STOCK_PED_THREATS = {
    4:  0x02900000,
    5:  0x02900000,
    6:  0x02900000,
    7:  0x0090FF00,
    8:  0x0090FE80,
    9:  0x0090FD80,
    10: 0x0090FB80,
    11: 0x0090F780,
    12: 0x0090EF80,
    13: 0x0090DF80,
    14: 0x0090BF80,
    15: 0x00907F80,
    16: 0x00800000,
    17: 0x00000000,
    18: 0x00B00040,
    19: 0x00000000,
    20: 0x02900000,
}

# Legitimate saves can contain mission-driven gang relationship changes. These
# variants were observed in the project's clean retail save corpus. Detection of
# NOBODYLIKESME therefore compares the table with the player-threat bit removed
# instead of requiring one fixed clean table.
_KNOWN_STOCK_PED_THREAT_PATTERNS = (
    tuple(STOCK_PED_THREATS[index] for index in range(PEDTYPE_CIVMALE, PEDTYPE_SPECIAL)),
    (
        0x02900000, 0x02900000, 0x02900000, 0x0090FE00, 0x0090BE01,
        0x0090DD80, 0x0090FB81, 0x0090F780, 0x0090EF80, 0x0090DD80,
        0x0090BF80, 0x00907F80, 0x00800000, 0x00000000, 0x00B00040,
        0x00000000, 0x02900000,
    ),
    (
        0x02900000, 0x02900000, 0x02900000, 0x0090FF00, 0x0090FE80,
        0x0090FD80, 0x0090FB81, 0x0090F780, 0x0090EF80, 0x0090DF80,
        0x0090BF80, 0x00907F80, 0x00800000, 0x00000000, 0x00B00040,
        0x00000000, 0x02900000,
    ),
    (
        0x02900000, 0x02900000, 0x02900000, 0x0090FE00, 0x0090BE01,
        0x0090FD80, 0x0090FB81, 0x0090F780, 0x0090EF80, 0x0090DF80,
        0x0090BF80, 0x00907F80, 0x00800000, 0x00000000, 0x00B00040,
        0x00000000, 0x02900000,
    ),
)
_KNOWN_NORMALIZED_PED_THREAT_PATTERNS = frozenset(
    tuple(value & ~PED_FLAG_PLAYER1 for value in pattern)
    for pattern in _KNOWN_STOCK_PED_THREAT_PATTERNS
)


class PedCheatState(Enum):
    NONE = "none"
    NOBODYLIKESME = "nobodylikesme"
    FIGHTFIGHTFIGHT = "fightfightfight"
    SUSPICIOUS = "suspicious"


@dataclass(frozen=True)
class PedCheatStatus:
    state: PedCheatState
    cheated_count: int
    player_hostile_everywhere: bool = False
    mayhem_subsumes_player_attack: bool = False

    @property
    def repairable(self) -> bool:
        return self.state in {PedCheatState.NOBODYLIKESME, PedCheatState.FIGHTFIGHTFIGHT}


@dataclass(frozen=True)
class Block:
    name: str
    offset: int
    size: int
    data_offset: int
    end: int
    inner_size: int | None = None


@dataclass
class PlayerValues:
    money: int
    health: float
    armour: float
    max_health: int
    max_armour: int
    position: tuple[float, float, float]
    infinite_sprint: bool
    fast_reload: bool
    fireproof: bool
    free_jail: bool
    free_hospital: bool
    drive_by: bool


@dataclass
class WorldValues:
    hour: int
    minute: int
    old_weather: int
    new_weather: int
    forced_weather: int


@dataclass
class WeaponValues:
    weapon_type: int
    ammo_clip: int
    ammo_total: int


def align4(value: int) -> int:
    return (value + 3) & ~3


def checksum(data: bytes | bytearray) -> int:
    return sum(data) & 0xFFFFFFFF


def _nested_block(inner: bytes) -> bytes:
    """Build one ordinary nested save block from its inner payload."""
    padded = inner + bytes(align4(len(inner)) - len(inner))
    outer = struct.pack("<I", len(inner)) + padded
    return struct.pack("<I", len(outer)) + outer


def _read_uint(data: bytes, offset: int, width: int) -> int:
    return int.from_bytes(data[offset:offset + width], "little", signed=False)


def _write_uint(data: bytearray, offset: int, width: int, value: int) -> None:
    maximum = (1 << (width * 8)) - 1
    data[offset:offset + width] = int(value & maximum).to_bytes(width, "little", signed=False)


def _convert_player_info(inner: bytes, target_size: int) -> bytes:
    if len(inner) not in (368, 416) or target_size not in (368, 416):
        raise SaveFormatError("Unsupported player-info conversion.")
    if target_size == len(inner):
        return bytes(inner)
    if target_size == 368:
        return bytes(inner[:368])
    return bytes(inner) + bytes(416 - len(inner))


def _convert_pickups(inner: bytes, target_size: int) -> bytes:
    """Convert the fixed pickup array between 32-bit-compatible and 64-bit layouts."""
    source_size = len(inner)
    if source_size == target_size:
        return bytes(inner)
    if source_size not in (17556, 21588) or target_size not in (17556, 21588):
        raise SaveFormatError("Unsupported pickup conversion.")

    source_stride = 52 if source_size == 17556 else 64
    target_stride = 52 if target_size == 17556 else 64
    result = bytearray(target_size)

    for slot in range(336):
        src = slot * source_stride
        dst = slot * target_stride
        # Position and revenue are identical in both layouts.
        result[dst:dst + 16] = inner[src:src + 16]
        if source_stride == 52:
            # Saved object references are pool indices, so widening them is lossless.
            _write_uint(result, dst + 16, 8, _read_uint(inner, src + 16, 4))
            _write_uint(result, dst + 24, 8, _read_uint(inner, src + 20, 4))
            result[dst + 32:dst + 36] = inner[src + 24:src + 28]  # quantity
            result[dst + 36:dst + 40] = inner[src + 28:src + 32]  # timer
            result[dst + 40:dst + 42] = inner[src + 32:src + 34]  # money speed
            result[dst + 42:dst + 44] = inner[src + 34:src + 36]  # model
            result[dst + 44:dst + 46] = inner[src + 36:src + 38]  # unique index
            result[dst + 46:dst + 54] = inner[src + 38:src + 46]  # text key
            result[dst + 54] = inner[src + 46]
            result[dst + 55] = inner[src + 47]
            result[dst + 56] = inner[src + 48]
        else:
            # Converting to a 32-bit save truncates only pool-index fields, which
            # are small integer handles in saved data rather than live pointers.
            p1 = _read_uint(inner, src + 16, 8)
            p2 = _read_uint(inner, src + 24, 8)
            if p1 > 0xFFFFFFFF or p2 > 0xFFFFFFFF:
                raise SaveFormatError("Pickup pool references cannot be represented in the selected 32-bit format.")
            _write_uint(result, dst + 16, 4, p1)
            _write_uint(result, dst + 20, 4, p2)
            result[dst + 24:dst + 28] = inner[src + 32:src + 36]
            result[dst + 28:dst + 32] = inner[src + 36:src + 40]
            result[dst + 32:dst + 34] = inner[src + 40:src + 42]
            result[dst + 34:dst + 36] = inner[src + 42:src + 44]
            result[dst + 36:dst + 38] = inner[src + 44:src + 46]
            result[dst + 38:dst + 46] = inner[src + 46:src + 54]
            result[dst + 46] = inner[src + 54]
            result[dst + 47] = inner[src + 55]
            result[dst + 48] = inner[src + 56]

    # Collected-pickup bookkeeping is the final 84 bytes in both layouts.
    source_tail = 336 * source_stride
    target_tail = 336 * target_stride
    result[target_tail:target_tail + 84] = inner[source_tail:source_tail + 84]
    return bytes(result)


def _convert_cranes(inner: bytes, target_size: int) -> bytes:
    """Re-encode eight crane records whose only structural difference is pointer width/alignment."""
    source_size = len(inner)
    if source_size == target_size:
        return bytes(inner)
    if source_size not in (1000, 1160) or target_size not in (1000, 1160):
        raise SaveFormatError("Unsupported crane conversion.")

    source_stride = 124 if source_size == 1000 else 144
    target_stride = 124 if target_size == 1000 else 144
    result = bytearray(target_size)
    result[:8] = inner[:8]  # crane count + military-crane collection mask
    source_base = 8
    target_base = 8
    for slot in range(8):
        src = source_base + slot * source_stride
        dst = target_base + slot * target_stride
        if source_stride == 124:
            _write_uint(result, dst + 0, 8, _read_uint(inner, src + 0, 4))
            _write_uint(result, dst + 8, 8, _read_uint(inner, src + 4, 4))
            result[dst + 16:dst + 116] = inner[src + 8:src + 108]
            _write_uint(result, dst + 120, 8, _read_uint(inner, src + 108, 4))
            result[dst + 128:dst + 132] = inner[src + 112:src + 116]
            result[dst + 132:dst + 139] = inner[src + 116:src + 123]
        else:
            refs = (_read_uint(inner, src, 8), _read_uint(inner, src + 8, 8),
                    _read_uint(inner, src + 120, 8))
            if any(value > 0xFFFFFFFF for value in refs):
                raise SaveFormatError("Crane pool references cannot be represented in the selected 32-bit format.")
            _write_uint(result, dst + 0, 4, refs[0])
            _write_uint(result, dst + 4, 4, refs[1])
            result[dst + 8:dst + 108] = inner[src + 16:src + 116]
            _write_uint(result, dst + 108, 4, refs[2])
            result[dst + 112:dst + 116] = inner[src + 128:src + 132]
            result[dst + 116:dst + 123] = inner[src + 132:src + 139]
    return bytes(result)


def _convert_phones(inner: bytes, target_size: int) -> bytes:
    """Re-encode phone records; transient message pointers are cleared across pointer widths."""
    source_size = len(inner)
    if source_size == target_size:
        return bytes(inner)
    if source_size not in (2608, 4408) or target_size not in (2608, 4408):
        raise SaveFormatError("Unsupported phone conversion.")

    source_stride = 52 if source_size == 2608 else 88
    target_stride = 52 if target_size == 2608 else 88
    result = bytearray(target_size)
    result[:8] = inner[:8]  # max phone count + script phone count
    for slot in range(50):
        src = 8 + slot * source_stride
        dst = 8 + slot * target_stride
        result[dst:dst + 12] = inner[src:src + 12]
        if source_stride == 52:
            # Six live text pointers are process-specific and cannot be translated
            # into another executable's address space; leave them null.
            result[dst + 64:dst + 68] = inner[src + 36:src + 40]
            _write_uint(result, dst + 72, 8, _read_uint(inner, src + 40, 4))
            result[dst + 80:dst + 84] = inner[src + 44:src + 48]
            result[dst + 84] = inner[src + 48]
        else:
            entity = _read_uint(inner, src + 72, 8)
            if entity > 0xFFFFFFFF:
                raise SaveFormatError("Phone entity reference cannot be represented in the selected 32-bit format.")
            result[dst + 36:dst + 40] = inner[src + 64:src + 68]
            _write_uint(result, dst + 40, 4, entity)
            result[dst + 44:dst + 48] = inner[src + 80:src + 84]
            result[dst + 48] = inner[src + 84]
    return bytes(result)


PARTICLE_RECORD_SIZES = (132, 152)
SCRIPT_PATH_HEADER_SIZES = (52, 88)
SCRIPT_PATH_NODE_SIZE = 20
STEAM_RELEASE_MARKER = -3


GARAGE_BLOCK_SIZE = 7876
GARAGE_PREFIX_SIZE = 1964
GARAGE_COUNT = 32
GARAGE_RECORD_SIZES = (168, 184)


def _garage_layout_score(inner: bytes, stride: int) -> int:
    """Score how many of the 32 garage headers look sane for a candidate stride."""
    if stride not in GARAGE_RECORD_SIZES or len(inner) != GARAGE_BLOCK_SIZE:
        return -1
    score = 0
    for index in range(GARAGE_COUNT):
        offset = GARAGE_PREFIX_SIZE + index * stride
        if offset + stride > len(inner):
            break
        garage_type = inner[offset]
        garage_state = inner[offset + 1]
        max_stored = inner[offset + 2]
        if garage_type <= 32 and garage_state <= 6 and max_stored <= 8:
            score += 1
    return score


def _garage_record_size_for_block(data: bytes | bytearray, block: "Block") -> int | None:
    if block.inner_size != GARAGE_BLOCK_SIZE:
        return None
    start = block.data_offset + 4
    inner = bytes(data[start:start + block.inner_size])
    scores = {stride: _garage_layout_score(inner, stride) for stride in GARAGE_RECORD_SIZES}
    perfect = [stride for stride, score in scores.items() if score == GARAGE_COUNT]
    return perfect[0] if len(perfect) == 1 else None


def _convert_garages(inner: bytes, source_stride: int, target_stride: int) -> bytes:
    """Convert the raw 32/64-bit CGarage array while preserving portable garage state."""
    if (source_stride not in GARAGE_RECORD_SIZES or target_stride not in GARAGE_RECORD_SIZES or
            len(inner) != GARAGE_BLOCK_SIZE):
        raise SaveFormatError("Unsupported garage conversion.")
    if source_stride == target_stride:
        return bytes(inner)

    result = bytearray(GARAGE_BLOCK_SIZE)
    # Global garage state and 48 CStoredCar records are pointer-width independent.
    result[:GARAGE_PREFIX_SIZE] = inner[:GARAGE_PREFIX_SIZE]
    for index in range(GARAGE_COUNT):
        src = GARAGE_PREFIX_SIZE + index * source_stride
        dst = GARAGE_PREFIX_SIZE + index * target_stride
        if source_stride == 184:
            # 64-bit raw CGarage -> retail 0xA8 record. Door/target pointer fields
            # and the embedded scratch stored-car record are zeroed. The loader
            # rebuilds the door/target pointers after loading.
            result[dst:dst + 12] = inner[src:src + 12]
            result[dst + 12:dst + 20] = bytes(8)
            result[dst + 20:dst + 27] = inner[src + 32:src + 39]
            result[dst + 27] = 0
            result[dst + 28:dst + 121] = inner[src + 40:src + 133]
            result[dst + 121:dst + 168] = bytes(47)
        else:
            # Retail 0xA8 -> 64-bit raw CGarage (0xB8). Runtime pointers are null and
            # the VR loader refreshes the door pointers after reading each record.
            result[dst:dst + 12] = inner[src:src + 12]
            result[dst + 12:dst + 32] = bytes(20)
            result[dst + 32:dst + 39] = inner[src + 20:src + 27]
            result[dst + 39] = 0
            result[dst + 40:dst + 133] = inner[src + 28:src + 121]
            result[dst + 133:dst + 184] = bytes(51)
    # Retail has 536 bytes of non-semantic tail; wide layout has 24. Keep all
    # remaining bytes deterministic rather than propagating work-buffer garbage.
    return bytes(result)


def _convert_particles(inner: bytes, target_stride: int) -> bytes:
    """Convert saved particle-object records between retail-compatible and 64-bit layouts."""
    if target_stride not in PARTICLE_RECORD_SIZES or len(inner) < 4:
        raise SaveFormatError("Unsupported particle-object conversion.")
    count = struct.unpack_from("<I", inner, 0)[0]
    record_count = count + 1  # The game reserves/saves one extra particle-object slot.
    source_payload = len(inner) - 4
    if record_count <= 0 or source_payload % record_count:
        raise SaveFormatError("The particle-object block has an unsupported size.")
    source_stride = source_payload // record_count
    if source_stride not in PARTICLE_RECORD_SIZES:
        raise SaveFormatError("The particle-object block uses an unsupported record size.")
    if source_stride == target_stride:
        return bytes(inner)

    result = bytearray(4 + record_count * target_stride)
    struct.pack_into("<I", result, 0, count)
    for index in range(record_count):
        src = 4 + index * source_stride
        dst = 4 + index * target_stride
        if source_stride == 152:
            # 64-bit raw CParticleObject:
            #   0..63 matrix floats
            #   64..71 matrix attachment pointer
            #   72 owner flag + alignment
            #   80..103 three live pointers
            #   104..151 persistent particle state
            result[dst:dst + 64] = inner[src:src + 64]
            result[dst + 64:dst + 68] = bytes(4)       # 32-bit attachment placeholder
            result[dst + 68] = inner[src + 72]         # matrix owner flag
            result[dst + 69:dst + 72] = bytes(3)
            result[dst + 72:dst + 84] = bytes(12)      # runtime/list pointers
            result[dst + 84:dst + 132] = inner[src + 104:src + 152]
        else:
            # Recreate the 64-bit raw layout with null live-pointer fields. The
            # loader rebuilds list/runtime ownership after loading.
            result[dst:dst + 64] = inner[src:src + 64]
            result[dst + 64:dst + 72] = bytes(8)
            result[dst + 72] = inner[src + 68]
            result[dst + 73:dst + 80] = bytes(7)
            result[dst + 80:dst + 104] = bytes(24)
            result[dst + 104:dst + 152] = inner[src + 84:src + 132]
    return bytes(result)


def _script_path_layout(inner: bytes, header_size: int) -> bool:
    """Return True when exactly three script paths consume *inner* with this header size."""
    if header_size not in SCRIPT_PATH_HEADER_SIZES:
        return False
    offset = 0
    try:
        for _ in range(3):
            if offset + header_size > len(inner):
                return False
            nodes = struct.unpack_from("<I", inner, offset)[0]
            if nodes > 100_000:
                return False
            offset += header_size + nodes * SCRIPT_PATH_NODE_SIZE
            if offset > len(inner):
                return False
    except struct.error:
        return False
    return offset == len(inner)


def _convert_script_paths(inner: bytes, target_header_size: int) -> bytes:
    """Convert the three script-path headers while preserving their 20-byte node arrays."""
    if target_header_size not in SCRIPT_PATH_HEADER_SIZES:
        raise SaveFormatError("Unsupported script-path conversion.")

    candidates = [size for size in SCRIPT_PATH_HEADER_SIZES if _script_path_layout(inner, size)]
    if len(candidates) != 1:
        raise SaveFormatError("Script-path block layout is not recognized.")
    source_header_size = candidates[0]
    if source_header_size == target_header_size:
        return bytes(inner)

    result = bytearray()
    offset = 0
    for _ in range(3):
        nodes = struct.unpack_from("<I", inner, offset)[0]
        src = offset
        if source_header_size == 88:
            header = bytearray(52)
            header[0:4] = inner[src:src + 4]              # node count
            header[4:8] = bytes(4)                       # node pointer placeholder
            header[8:28] = inner[src + 16:src + 36]      # lengths/speed/position/width/state
            for index in range(6):
                value = _read_uint(inner, src + 40 + index * 8, 8)
                if value > 0xFFFFFFFF:
                    raise SaveFormatError(
                        "A script-path object reference cannot be represented in the selected 32-bit format."
                    )
                _write_uint(header, 28 + index * 4, 4, value)
        else:
            header = bytearray(88)
            header[0:4] = inner[src:src + 4]
            header[4:16] = bytes(12)                     # alignment + 64-bit node pointer
            header[16:36] = inner[src + 8:src + 28]
            header[36:40] = bytes(4)
            for index in range(6):
                _write_uint(header, 40 + index * 8, 8, _read_uint(inner, src + 28 + index * 4, 4))

        result += header
        node_start = src + source_header_size
        node_end = node_start + nodes * SCRIPT_PATH_NODE_SIZE
        result += inner[node_start:node_end]
        offset = node_end
    return bytes(result)


def _simple_variant_from_block(block: bytes) -> str | None:
    """Identify retail-style vs Steam Block 0 by the script header position."""
    if len(block) < 4:
        return None
    size = struct.unpack_from("<I", block, 0)[0]
    if 4 + size > len(block):
        return None
    payload = block[4:4 + size]
    if len(payload) >= 0xEC and payload[0xE8:0xEC] == b"SCR\0":
        return "retail"
    if len(payload) >= 0xF0 and payload[0xEC:0xF0] == b"SCR\0":
        return "steam"
    # Synthetic/minimal fixtures may contain a zero-length script subblock.
    if (len(payload) >= 0xEC and
            struct.unpack_from("<i", payload, 0x54)[0] == STEAM_RELEASE_MARKER and
            struct.unpack_from("<I", payload, 0xE8)[0] == 0):
        return "steam"
    if len(payload) >= 0xE8 and struct.unpack_from("<I", payload, 0xE4)[0] == 0:
        return "retail"
    return None


def _convert_simple_variant(block: bytes, source_variant: str, target_variant: str) -> bytes:
    """Insert/remove Steam's extra Block 0 DWORD without changing script data."""
    if source_variant == target_variant:
        return bytes(block)
    if {source_variant, target_variant} != {"retail", "steam"}:
        raise SaveFormatError("Unsupported Block 0 release conversion.")
    if len(block) < 4:
        raise SaveFormatError("The simple-variable block is incomplete.")

    size = struct.unpack_from("<I", block, 0)[0]
    payload = bytearray(block[4:4 + size])
    if len(payload) != size:
        raise SaveFormatError("The simple-variable block has an invalid size.")

    if source_variant == "retail":
        if _simple_variant_from_block(block) != "retail":
            raise SaveFormatError("The source does not use the expected retail Block 0 layout.")
        payload[0x54:0x54] = struct.pack("<i", STEAM_RELEASE_MARKER)
    else:
        if _simple_variant_from_block(block) != "steam":
            raise SaveFormatError("The source does not use the expected Steam Block 0 layout.")
        del payload[0x54:0x58]

    return struct.pack("<I", len(payload)) + bytes(payload)


def _particle_stride_for_block(data: bytes | bytearray, block: "Block") -> int | None:
    if block.inner_size is None or block.inner_size < 4:
        return None
    start = block.data_offset + 4
    count = struct.unpack_from("<I", data, start)[0]
    record_count = count + 1
    payload = block.inner_size - 4
    if record_count and payload >= 0 and payload % record_count == 0:
        stride = payload // record_count
        if stride in PARTICLE_RECORD_SIZES:
            return stride
    return None


def _script_path_header_for_block(data: bytes | bytearray, block: "Block") -> int | None:
    if block.inner_size is None or block.inner_size == 0:
        return None
    start = block.data_offset + 4
    inner = bytes(data[start:start + block.inner_size])
    matches = [size for size in SCRIPT_PATH_HEADER_SIZES if _script_path_layout(inner, size)]
    return matches[0] if len(matches) == 1 else None


def _saved_vehicle_count(data: bytes | bytearray, block: "Block") -> int | None:
    if block.inner_size is None or block.inner_size < 12:
        return None
    start = block.data_offset + 4
    general, boats, bikes = struct.unpack_from("<III", data, start)
    return general + boats + bikes


def _padding_bytes(total: int) -> bytes:
    """Create parser-safe non-semantic padding occupying exactly *total* bytes."""
    if total == 0:
        return b""
    if total < 4 or total % 4:
        raise SaveFormatError("The converted save cannot be padded to its original container size.")
    chunks: list[bytes] = []
    remaining = total
    while remaining:
        chunk_total = min(remaining, MAX_BLOCK_SIZE + 4)
        chunk_total -= chunk_total % 4
        if remaining - chunk_total in (1, 2, 3):
            chunk_total -= 4
        if chunk_total < 4:
            raise SaveFormatError("The converted save has an invalid padding remainder.")
        payload_size = chunk_total - 4
        chunks.append(struct.pack("<I", payload_size) + bytes(payload_size))
        remaining -= chunk_total
    if len(chunks) > 4:
        raise SaveFormatError("The converted save would require too many padding blocks.")
    return b"".join(chunks)


class SaveFile:
    """A byte-preserving view of one supported Vice City save."""

    def __init__(self, data: bytes, source: Path | None = None):
        self.source = source
        self._original = bytes(data)
        self._data = bytearray(data)
        self.blocks: list[Block] = []
        self.padding_blocks: list[Block] = []
        self._parse()
        self.profile = self._detect_profile()

    @classmethod
    def load(cls, path: str | Path) -> "SaveFile":
        source = Path(path)
        try:
            return cls(source.read_bytes(), source)
        except OSError as error:
            raise SaveFormatError(f"Could not read the save: {error}") from error

    @property
    def changed(self) -> bool:
        return self._data != self._original

    @property
    def raw(self) -> bytes:
        return bytes(self._data)

    @property
    def mission_name(self) -> str:
        return self._data[4:52].decode("utf-16le", errors="replace").split("\0", 1)[0]

    @property
    def timestamp(self) -> datetime | None:
        year, month, _, day, hour, minute, second, _ = struct.unpack_from("<8H", self._data, 52)
        try:
            return datetime(year, month, day, hour, minute, second)
        except ValueError:
            return None

    @property
    def quick_save_type(self) -> int:
        return struct.unpack_from("<I", self._data, 0x44)[0] >> 24

    @property
    def stored_checksum(self) -> int:
        return struct.unpack_from("<I", self._data, len(self._data) - 4)[0]

    def _parse(self) -> None:
        if len(self._data) < 256:
            raise SaveFormatError("The file is too small to be a supported Vice City save.")
        expected = checksum(self._data[:-4])
        if expected != self.stored_checksum:
            raise SaveFormatError(
                f"Checksum mismatch (stored {self.stored_checksum}, calculated {expected})."
            )
        offset = 0
        for name in BLOCK_NAMES:
            block = self._read_block(offset, name)
            self.blocks.append(block)
            offset = block.end
        while offset < len(self._data) - 4:
            block = self._read_block(offset, f"Padding {len(self.padding_blocks) + 1}")
            self.padding_blocks.append(block)
            offset = block.end
            if len(self.padding_blocks) > 4:
                raise SaveFormatError("The save contains too many padding blocks.")
        if offset != len(self._data) - 4:
            raise SaveFormatError("The block table does not end at the checksum.")
        first = self.blocks[0]
        if first.size < SIMPLE_SIZE + 4:
            raise SaveFormatError("The simple-variable block is incomplete.")
        declared = struct.unpack_from("<I", self._data, 0x44)[0] & 0x00FFFFFF
        if declared != DECLARED_SIZE:
            raise SaveFormatError(f"Unsupported declared save size: {declared}.")
        ped = self.blocks[1]
        player = self.blocks[18]
        if ped.inner_size is None or player.inner_size is None:
            raise SaveFormatError("Required nested blocks are missing.")

    def _detect_profile(self) -> SaveProfile:
        pickup_size = self.blocks[8].inner_size
        player_size = self.blocks[18].inner_size
        cranes_size = self.blocks[7].inner_size
        phone_size = self.blocks[9].inner_size
        simple_piece = bytes(self._data[self.blocks[0].offset:self.blocks[0].end])
        simple_variant = _simple_variant_from_block(simple_piece)
        particle_stride = _particle_stride_for_block(self._data, self.blocks[15])
        script_path_header = _script_path_header_for_block(self._data, self.blocks[17])
        garage_record_size = _garage_record_size_for_block(self._data, self.blocks[2])
        common_edit_signature = (
            self.blocks[1].inner_size == 1795 and
            self.blocks[2].inner_size == 7876 and
            self.blocks[13].inner_size == 224 and
            self.blocks[14].inner_size == 8168 and
            self.blocks[19].inner_size == 595
        )
        if common_edit_signature:
            signature = (player_size, pickup_size, cranes_size, phone_size)
            for profile in SUPPORTED_PROFILES:
                if signature != (profile.player_info_size, profile.pickup_size,
                                 profile.cranes_size, profile.phone_size):
                    continue
                if simple_variant is not None and simple_variant != profile.simple_variant:
                    continue
                if particle_stride is not None and particle_stride != profile.particle_stride:
                    continue
                if script_path_header is not None and script_path_header != profile.script_path_header_size:
                    continue
                if garage_record_size is not None and garage_record_size != profile.garage_record_size:
                    continue
                return profile
        return UNKNOWN_PROFILE

    def _read_block(self, offset: int, name: str) -> Block:
        checksum_offset = len(self._data) - 4
        if offset + 4 > checksum_offset:
            raise SaveFormatError(f"{name} has no size field.")
        size = struct.unpack_from("<I", self._data, offset)[0]
        if size > MAX_BLOCK_SIZE:
            raise SaveFormatError(f"{name} is unreasonably large ({size} bytes).")
        end = offset + 4 + align4(size)
        if end > checksum_offset:
            raise SaveFormatError(f"{name} extends beyond the end of the save.")
        inner = None
        if name in BLOCK_NAMES and name != BLOCK_NAMES[0]:
            if size < 4:
                raise SaveFormatError(f"{name} has no nested size field.")
            inner = struct.unpack_from("<I", self._data, offset + 4)[0]
            if 4 + align4(inner) > size:
                raise SaveFormatError(f"{name} has an invalid nested size.")
        return Block(name, offset, size, offset + 4, end, inner)

    def _player_ped_offset(self) -> int:
        block = self.blocks[1]
        inner = block.data_offset + 4
        count = struct.unpack_from("<i", self._data, inner)[0]
        if count != 1:
            raise SaveFormatError("This save does not contain exactly one editable player record.")
        record = inner + 4
        ped_type = struct.unpack_from("<I", self._data, record)[0]
        if ped_type != 0 or block.inner_size != 1795:
            raise SaveFormatError("The player record uses an unsupported layout.")
        return record + 10

    def _player_info_offset(self) -> int:
        block = self.blocks[18]
        if block.inner_size not in (368, 416):
            raise SaveFormatError("The player-info block uses an unsupported layout.")
        return block.data_offset + 4

    def _require_editable(self) -> None:
        if not self.profile.editable:
            raise SaveFormatError(
                f"{self.profile.name} is recognized but not approved for editing. "
                "No changes were written."
            )

    def player(self) -> PlayerValues:
        ped = self._player_ped_offset()
        info = self._player_info_offset()
        position = struct.unpack_from("<3f", self._data, ped + 52)
        health, armour = struct.unpack_from("<2f", self._data, ped + 852)
        return PlayerValues(
            money=struct.unpack_from("<i", self._data, info)[0],
            health=health,
            armour=armour,
            max_health=self._data[info + 30],
            max_armour=self._data[info + 31],
            position=position,
            infinite_sprint=bool(self._data[info + 27]),
            fast_reload=bool(self._data[info + 28]),
            fireproof=bool(self._data[info + 29]),
            free_jail=bool(self._data[info + 32]),
            free_hospital=bool(self._data[info + 33]),
            drive_by=bool(self._data[info + 34]),
        )

    def _simple_shift(self) -> int:
        piece = bytes(self._data[self.blocks[0].offset:self.blocks[0].end])
        return 4 if _simple_variant_from_block(piece) == "steam" else 0

    def world(self) -> WorldValues:
        base = self.blocks[0].data_offset
        shift = self._simple_shift()
        return WorldValues(
            hour=self._data[base + 0x5C + shift],
            minute=self._data[base + 0x60 + shift],
            old_weather=struct.unpack_from("<h", self._data, base + 0x88 + shift)[0],
            new_weather=struct.unpack_from("<h", self._data, base + 0x8C + shift)[0],
            forced_weather=struct.unpack_from("<h", self._data, base + 0x90 + shift)[0],
        )

    def weapons(self) -> list[WeaponValues]:
        start = self._player_ped_offset() + 1032
        result = []
        for slot in range(10):
            weapon_type, _, clip, total = struct.unpack_from("<4i", self._data, start + slot * 24)
            result.append(WeaponValues(weapon_type, clip, total))
        return result

    def set_player(self, values: PlayerValues) -> None:
        self._require_editable()
        if not -1_000_000_000 <= values.money <= 999_999_999:
            raise ValueError("Money must be between -1,000,000,000 and 999,999,999.")
        floats = (*values.position, values.health, values.armour)
        if not all(math.isfinite(value) for value in floats):
            raise ValueError("Player values must be finite numbers.")
        if not 0 <= values.health <= 1000 or not 0 <= values.armour <= 1000:
            raise ValueError("Health and armour must be between 0 and 1000.")
        if not 0 <= values.max_health <= 255 or not 0 <= values.max_armour <= 255:
            raise ValueError("Maximum health and armour must be between 0 and 255.")
        ped = self._player_ped_offset()
        info = self._player_info_offset()
        old_position = struct.unpack_from("<3f", self._data, ped + 52)
        position_changed = any(
            not math.isclose(old, new, rel_tol=0.0, abs_tol=0.0005)
            for old, new in zip(old_position, values.position)
        )
        if position_changed:
            struct.pack_into("<3f", self._data, ped + 52, *values.position)
            camera = self.blocks[0].data_offset + 0x48
            struct.pack_into("<3f", self._data, camera, *values.position)
        old_health, old_armour = struct.unpack_from("<2f", self._data, ped + 852)
        if not math.isclose(old_health, values.health, rel_tol=0.0, abs_tol=0.0005):
            struct.pack_into("<f", self._data, ped + 852, values.health)
        if not math.isclose(old_armour, values.armour, rel_tol=0.0, abs_tol=0.0005):
            struct.pack_into("<f", self._data, ped + 856, values.armour)
        struct.pack_into("<i", self._data, info, values.money)
        struct.pack_into("<i", self._data, info + 15, values.money)
        for offset, value in ((27, values.infinite_sprint), (28, values.fast_reload),
                              (29, values.fireproof), (32, values.free_jail),
                              (33, values.free_hospital), (34, values.drive_by)):
            self._data[info + offset] = int(value)
        self._data[info + 30] = values.max_health
        self._data[info + 31] = values.max_armour
        self._refresh_checksum()

    def set_world(self, values: WorldValues) -> None:
        self._require_editable()
        if not 0 <= values.hour <= 23 or not 0 <= values.minute <= 59:
            raise ValueError("Choose a valid time.")
        if not all(-1 <= value <= 255 for value in
                   (values.old_weather, values.new_weather, values.forced_weather)):
            raise ValueError("Weather values must be between -1 and 255.")
        base = self.blocks[0].data_offset
        shift = self._simple_shift()
        self._data[base + 0x5C + shift] = values.hour
        self._data[base + 0x60 + shift] = values.minute
        struct.pack_into("<h", self._data, base + 0x88 + shift, values.old_weather)
        struct.pack_into("<h", self._data, base + 0x8C + shift, values.new_weather)
        struct.pack_into("<h", self._data, base + 0x90 + shift, values.forced_weather)
        self._refresh_checksum()

    def set_weapons(self, weapons: list[WeaponValues]) -> None:
        self._require_editable()
        if len(weapons) != 10:
            raise ValueError("Exactly ten weapon slots are required.")
        start = self._player_ped_offset() + 1032
        for slot, weapon in enumerate(weapons):
            if not 0 <= weapon.weapon_type <= 36:
                raise ValueError(f"Weapon slot {slot + 1} has an invalid weapon type.")
            if not 0 <= weapon.ammo_clip <= 99999 or not 0 <= weapon.ammo_total <= 999999:
                raise ValueError(f"Weapon slot {slot + 1} has invalid ammunition.")
            offset = start + slot * 24
            old_type = struct.unpack_from("<i", self._data, offset)[0]
            if old_type == weapon.weapon_type:
                # State, timer, rotation flag, and alignment bytes belong to the
                # running game. Ammo-only edits must leave them alone.
                struct.pack_into("<2i", self._data, offset + 8,
                                 weapon.ammo_clip, weapon.ammo_total)
            else:
                struct.pack_into("<5iB3x", self._data, offset, weapon.weapon_type, 0,
                                 weapon.ammo_clip, weapon.ammo_total, 0, 0)
        self._refresh_checksum()

    def pickups(self) -> list[PickupRecord]:
        block = self.blocks[8]
        profiles = {17556: "compatible52", 21588: "pointer64"}
        if block.inner_size not in profiles:
            raise SaveFormatError("The pickup block uses an unsupported layout.")
        return read_pickups(self._data, block.data_offset + 4, profiles[block.inner_size])

    def set_pickup(self, record: PickupRecord) -> None:
        self._require_editable()
        block = self.blocks[8]
        profiles = {17556: "compatible52", 21588: "pointer64"}
        if block.inner_size not in profiles:
            raise SaveFormatError("The pickup block uses an unsupported layout.")
        write_pickup(self._data, block.data_offset + 4, profiles[block.inner_size], record)
        self._refresh_checksum()

    def car_generators(self) -> list[CarGeneratorRecord]:
        block = self.blocks[14]
        if block.inner_size != 8168:
            raise SaveFormatError("The car-generator block uses an unsupported layout.")
        return read_car_generators(self._data, block.data_offset + 4)

    def set_car_generator(self, record: CarGeneratorRecord) -> None:
        self._require_editable()
        write_car_generator(self._data, self.blocks[14].data_offset + 4, record)
        self._refresh_checksum()

    def stored_cars(self) -> list[StoredCarRecord]:
        block = self.blocks[2]
        if block.inner_size != 7876:
            raise SaveFormatError("The garage block uses an unsupported layout.")
        return read_stored_cars(self._data, block.data_offset + 4)

    def hideout_garage_geometries(self):
        """Serialized hideout CGarage geometry keyed by storage group."""
        block = self.blocks[2]
        if block.inner_size != 7876:
            raise SaveFormatError("The garage block uses an unsupported layout.")
        stride = _garage_record_size_for_block(self._data, block)
        if stride is None:
            raise SaveFormatError("The garage record layout could not be identified.")
        return read_hideout_garage_geometries(self._data, block.data_offset + 4, stride)


    def hideout_garage_capacities(self) -> dict[int, int]:
        """Saved m_nMaxStoredCars values keyed by hideout storage group."""
        block = self.blocks[2]
        if block.inner_size != 7876:
            raise SaveFormatError("The garage block uses an unsupported layout.")
        stride = _garage_record_size_for_block(self._data, block)
        if stride is None:
            raise SaveFormatError("The garage record layout could not be identified.")
        return read_hideout_garage_capacities(self._data, block.data_offset + 4, stride)

    def set_stored_car(self, record: StoredCarRecord) -> None:
        self._require_editable()
        write_stored_car(self._data, self.blocks[2].data_offset + 4, record)
        self._refresh_checksum()

    def gangs(self) -> list[GangRecord]:
        block = self.blocks[13]
        if block.inner_size != 224:
            raise SaveFormatError("The gang block uses an unsupported layout.")
        return read_gangs(self._data, block.data_offset + 4)

    def set_gang(self, record: GangRecord) -> None:
        self._require_editable()
        write_gang(self._data, self.blocks[13].data_offset + 4, record)
        self._refresh_checksum()

    def _ped_types_payload_offset(self) -> int:
        block = self.blocks[PED_TYPES_BLOCK_INDEX]
        if block.inner_size != PED_TYPES_INNER_SIZE:
            raise SaveFormatError("The Ped types block uses an unsupported layout.")
        payload = block.data_offset + 4
        if self._data[payload:payload + 4] != b"PTP\0":
            raise SaveFormatError("The Ped types block has an invalid PTP signature.")
        declared = struct.unpack_from("<I", self._data, payload + 4)[0]
        if declared != PED_TYPES_INNER_SIZE - PED_TYPES_HEADER_SIZE:
            raise SaveFormatError("The Ped types block has an unexpected payload size.")
        return payload

    def ped_type_threats(self) -> tuple[int, ...]:
        """Return the 23 serialized CPedType threat masks."""
        payload = self._ped_types_payload_offset()
        return tuple(
            struct.unpack_from(
                "<I",
                self._data,
                payload + PED_TYPES_HEADER_SIZE + index * PED_TYPE_RECORD_SIZE + PED_TYPE_THREATS_OFFSET,
            )[0]
            for index in range(PED_TYPE_RECORD_COUNT)
        )

    def cheated_count(self) -> int:
        """Return the aggregate cheat-use statistic without interpreting it."""
        for name, value, _kind in self.stats():
            if name == "CheatedCount":
                return int(value)
        raise SaveFormatError("The cheat-use statistic is missing from the Stats block.")

    def detect_persistent_ped_cheats(self) -> PedCheatStatus:
        """Detect persistent pedestrian-hostility signatures in the Ped types block."""
        threats = self.ped_type_threats()
        affected = tuple(threats[index] for index in range(PEDTYPE_CIVMALE, PEDTYPE_SPECIAL))
        cheated_count = self.cheated_count()

        if all(value == MAYHEM_THREAT_MASK for value in affected):
            return PedCheatStatus(
                PedCheatState.FIGHTFIGHTFIGHT, cheated_count, True, True
            )

        player_hostile_everywhere = all(value & PED_FLAG_PLAYER1 for value in affected)
        if player_hostile_everywhere:
            normalized = tuple(value & ~PED_FLAG_PLAYER1 for value in affected)
            if normalized in _KNOWN_NORMALIZED_PED_THREAT_PATTERNS:
                return PedCheatStatus(
                    PedCheatState.NOBODYLIKESME, cheated_count, True, False
                )
            return PedCheatStatus(
                PedCheatState.SUSPICIOUS, cheated_count, True, False
            )

        return PedCheatStatus(PedCheatState.NONE, cheated_count, False, False)

    def repair_nobodylikesme(self) -> None:
        """Remove the global player-threat bit added by NOBODYLIKESME."""
        self._require_editable()
        status = self.detect_persistent_ped_cheats()
        if status.state != PedCheatState.NOBODYLIKESME:
            raise SaveFormatError("NOBODYLIKESME is not detected in this save.")
        payload = self._ped_types_payload_offset()
        for index in range(PEDTYPE_CIVMALE, PEDTYPE_SPECIAL):
            offset = payload + PED_TYPES_HEADER_SIZE + index * PED_TYPE_RECORD_SIZE + PED_TYPE_THREATS_OFFSET
            value = struct.unpack_from("<I", self._data, offset)[0]
            struct.pack_into("<I", self._data, offset, value & ~PED_FLAG_PLAYER1)
        self._refresh_checksum()

    def repair_fightfightfight(self) -> None:
        """Restore standard Vice City threats after FIGHTFIGHTFIGHT overwrote them."""
        self._require_editable()
        status = self.detect_persistent_ped_cheats()
        if status.state != PedCheatState.FIGHTFIGHTFIGHT:
            raise SaveFormatError("FIGHTFIGHTFIGHT is not detected in this save.")
        payload = self._ped_types_payload_offset()
        for index, value in STOCK_PED_THREATS.items():
            offset = payload + PED_TYPES_HEADER_SIZE + index * PED_TYPE_RECORD_SIZE + PED_TYPE_THREATS_OFFSET
            struct.pack_into("<I", self._data, offset, value)
        self._refresh_checksum()

    def repair_persistent_ped_cheat(self) -> PedCheatState:
        """Repair the exact persistent pedestrian cheat currently detected."""
        state = self.detect_persistent_ped_cheats().state
        if state == PedCheatState.NOBODYLIKESME:
            self.repair_nobodylikesme()
        elif state == PedCheatState.FIGHTFIGHTFIGHT:
            self.repair_fightfightfight()
        else:
            raise SaveFormatError("No exact repairable pedestrian cheat signature is detected.")
        return state

    def stats(self) -> list[tuple[str, object, str]]:
        block = self.blocks[19]
        if block.inner_size != 595:
            raise SaveFormatError("The stats block uses an unsupported layout.")
        return read_stats(self._data, block.data_offset + 4)

    def set_stat(self, name: str, value: object) -> None:
        self._require_editable()
        write_stat(self._data, self.blocks[19].data_offset + 4, name, value)
        self._refresh_checksum()

    def _refresh_checksum(self) -> None:
        struct.pack_into("<I", self._data, len(self._data) - 4, checksum(self._data[:-4]))

    @staticmethod
    def export_profiles() -> tuple[SaveProfile, ...]:
        return SUPPORTED_PROFILES

    def export_bytes(self, target_profile_key: str | None = None) -> bytes:
        """Return a validated copy encoded for any supported output profile."""
        self._require_editable()
        target_key = target_profile_key or self.profile.key
        try:
            target = SUPPORTED_PROFILE_BY_KEY[target_key]
        except KeyError as error:
            raise SaveFormatError(f"Unknown output format: {target_key}") from error
        if target.key == self.profile.key:
            return self.validated_bytes()

        crosses_vr_boundary = (
            (self.profile.key == VICE_CITY_VR_PROFILE.key) !=
            (target.key == VICE_CITY_VR_PROFILE.key)
        )
        vehicle_count = _saved_vehicle_count(self._data, self.blocks[4])
        if crosses_vr_boundary and vehicle_count:
            raise SaveFormatError(
                "This save contains live saved vehicle records whose 32/64-bit conversion is not "
                "yet proven safe. Save in the same runtime family or remove/finish the mission state "
                "that created those records before converting."
            )

        converted: dict[int, bytes] = {}
        garage = self.blocks[2]
        assert garage.inner_size is not None and target.garage_record_size is not None
        garage_start = garage.data_offset + 4
        garage_inner = bytes(self._data[garage_start:garage_start + garage.inner_size])
        source_garage_size = self.profile.garage_record_size
        if source_garage_size is not None and source_garage_size != target.garage_record_size:
            converted[2] = _nested_block(_convert_garages(
                garage_inner, source_garage_size, target.garage_record_size
            ))

        for index, converter, target_size in (
            (7, _convert_cranes, target.cranes_size),
            (8, _convert_pickups, target.pickup_size),
            (9, _convert_phones, target.phone_size),
            (18, _convert_player_info, target.player_info_size),
        ):
            block = self.blocks[index]
            assert block.inner_size is not None and target_size is not None
            inner_start = block.data_offset + 4
            inner = bytes(self._data[inner_start:inner_start + block.inner_size])
            converted[index] = _nested_block(converter(inner, target_size))

        particle = self.blocks[15]
        assert particle.inner_size is not None and target.particle_stride is not None
        particle_start = particle.data_offset + 4
        if particle.inner_size:
            converted[15] = _nested_block(_convert_particles(
                bytes(self._data[particle_start:particle_start + particle.inner_size]),
                target.particle_stride,
            ))
        else:
            converted[15] = bytes(self._data[particle.offset:particle.end])

        paths = self.blocks[17]
        assert paths.inner_size is not None and target.script_path_header_size is not None
        path_start = paths.data_offset + 4
        if paths.inner_size:
            converted[17] = _nested_block(_convert_script_paths(
                bytes(self._data[path_start:path_start + paths.inner_size]),
                target.script_path_header_size,
            ))
        else:
            converted[17] = bytes(self._data[paths.offset:paths.end])

        pieces: list[bytes] = []
        for index, block in enumerate(self.blocks):
            if index in converted:
                piece = converted[index]
            else:
                piece = bytes(self._data[block.offset:block.end])
            if index == 0 and self.profile.simple_variant != target.simple_variant:
                piece = _convert_simple_variant(
                    piece, self.profile.simple_variant, target.simple_variant
                )
            pieces.append(piece)
        core = b"".join(pieces)

        # Real PC/VR saves reserve a generous non-semantic padding area. Keep the
        # source container length when possible; synthetic/minimal files may grow.
        source_without_checksum = len(self._data) - 4
        target_without_checksum = max(source_without_checksum, len(core))
        padding = _padding_bytes(target_without_checksum - len(core))
        rebuilt = bytearray(core + padding)
        rebuilt += struct.pack("<I", checksum(rebuilt))

        result = SaveFile(bytes(rebuilt))
        if result.profile.key != target.key:
            raise SaveFormatError(
                f"Converted output validated as {result.profile.name}, not {target.name}."
            )

        # Verify the user-facing state that the toolkit preserves.
        if result.player() != self.player() or result.world() != self.world() or result.weapons() != self.weapons():
            raise SaveFormatError("Converted output did not preserve player/world/weapon state.")
        if result.pickups() != self.pickups():
            raise SaveFormatError("Converted output did not preserve pickup state.")
        if result.car_generators() != self.car_generators() or result.stored_cars() != self.stored_cars():
            raise SaveFormatError("Converted output did not preserve persistent vehicle state.")
        if result.gangs() != self.gangs() or result.stats() != self.stats():
            raise SaveFormatError("Converted output did not preserve gang/statistics state.")
        return bytes(rebuilt)

    def validated_bytes(self) -> bytes:
        data = bytes(self._data)
        SaveFile(data)
        return data
