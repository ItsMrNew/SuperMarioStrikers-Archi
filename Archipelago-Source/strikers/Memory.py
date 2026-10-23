"""Read-only achievement decoding, independent of Dolphin and Archipelago I/O."""

from dataclasses import dataclass
import struct

from .Data import CAPTAINS, CUPS, GOAL_LOCATION, MEDALS, MILESTONES, PLACEMENTS, SIDEKICKS, STADIUMS
from .Locations import CUP_WIN_BONUS_COUNT, sidekick_location, stadium_location
from .Data import milestone_thresholds

MANAGER_ADDRESS = 0x80374418
STATS_ADDRESS = 0x80374440
MANAGER_SIZE = 0x4C80
STATS_SIZE = 0x4C4
CURRENT_MODE_OFFSET = 0x4954
GAME_INFO_POINTERS_OFFSET = 0x10
STATS_ENDED_OFFSET = 0x4C2
MATCH_FORMAT = struct.Struct(">5i6h")
MATCH_SIZE = MATCH_FORMAT.size
USER_INFO = 0x2ED4
TROPHIES = USER_INFO + 0x4C
# Instructions verified in the bundled patched executable. The retail symbol
# map's absolute addresses are different; reject a mismatched build before I/O.
PATCH_SIGNATURES = {
    0x80005420: bytes.fromhex("3da0803761ad9660"),  # r13 = 0x80379660
    0x801837AC: bytes.fromhex("806dade0"),  # StatsTracker at r13 - 0x5220
    0x801837D4: bytes.fromhex("981f04c2"),  # mHasGameEnded at +0x4c2
}


def s32(data, offset):
    return struct.unpack_from(">i", data, offset)[0]


def u32(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def u16(data, offset):
    return struct.unpack_from(">H", data, offset)[0]


def valid_pointer(address, size):
    return address % 4 == 0 and 0x80000000 <= address <= 0x81800000 - size


@dataclass(frozen=True)
class Match:
    teams: tuple
    sidekicks: tuple
    stadium: int
    pads: tuple
    scores: tuple

    @classmethod
    def read(cls, data, offset=0):
        values = MATCH_FORMAT.unpack_from(data, offset)
        return cls(values[:2], values[2:4], values[4], values[5:9], values[9:11])

    @property
    def human_side(self):
        sides = set(self.pads) - {-1}
        return next(iter(sides)) if len(sides) == 1 and sides <= {0, 1} else None

    @property
    def valid(self):
        return (
            all(team in CAPTAINS for team in self.teams)
            and self.teams[0] != self.teams[1]
            and self.stadium in STADIUMS
            and all(pad in (-1, 0, 1) for pad in self.pads)
            and all(team == 8 or sk in SIDEKICKS for team, sk in zip(self.teams, self.sidekicks))
        )

    def completed_by(self, captain=None):
        # BasicGameInfo scores are written at match end, not on each goal.
        # Simulated CPU fixtures have no assigned human controller.
        side = self.human_side
        return (
            self.valid
            and side is not None
            and (captain is None or self.teams[side] == captain)
            and all(0 <= score <= 32767 for score in self.scores)
            and self.scores[0] != self.scores[1]
        )

    def win_locations(self, side):
        if not self.valid or side not in (0, 1):
            return set()
        captain, sidekick = self.teams[side], self.sidekicks[side]
        names = {
            f"First Win - {CAPTAINS[captain]}",
            f"First Win at {STADIUMS[self.stadium]}",
            stadium_location(captain, self.stadium),
        }
        if captain != 8:
            names.add(sidekick_location(captain, sidekick))
        return names


def placement_locations(cup, place):
    return {f"{cup.name} - {label}" for maximum, label in PLACEMENTS if 1 <= place <= maximum}


def saved_locations(data, options=None):
    """Recover completed fixtures, placements and trophies from one stable snapshot."""
    if len(data) != MANAGER_SIZE:
        return set()
    names = set()
    trophies = data[TROPHIES]

    def fixture(cup, offset, number, captain=None, place=None):
        match = Match.read(data, offset)
        if not match.completed_by(captain):
            return
        names.add(f"{cup.name} - Match {number}")
        side = match.human_side
        if match.scores[side] > match.scores[1 - side]:
            names.update(match.win_locations(side))
        if place is not None:
            names.update(placement_locations(cup, place))

    for cup in CUPS:
        captain = s32(data, cup.offset)
        if captain in CAPTAINS:
            for round_index in range(cup.rounds):
                for game in range(cup.teams // 2):
                    offset = cup.offset + 0x20 + (round_index * (cup.teams // 2) + game) * 0x20
                    fixture(cup, offset, round_index + 1, captain)
        if cup.knockout:
            captain = s32(data, cup.knockout)
            if captain in CAPTAINS:
                # Two semifinals and one final. Both semifinal losers tie for
                # third; we do not invent a third-place playoff.
                for game in range(2):
                    fixture(cup, cup.knockout + 0x20 + game * 0x20, cup.rounds + 1, captain, 3)
                fixture(cup, cup.knockout + 0x60, cup.rounds + 2, captain, 2)
            if cup.mode == 4:
                # The Super Team challenge reuses the final's fixture. The
                # original final is copied to this save field before replacement.
                fixture(cup, USER_INFO + 0x111C, cup.rounds + 2, place=2)

        spoil = USER_INFO + 0x50 + cup.trophy_bit * 0x218
        count = data[spoil + 0x208]
        if count <= 10:
            for record in range(count):
                entry = spoil + record * 0x34
                rank = struct.unpack_from(">b", data, entry + 0x28)[0]
                if s32(data, entry + 0x2C) not in CAPTAINS:
                    continue
                # Bowser knockout losses are stored as -2 (not runner-up).
                # Recover those from actual played fixtures above, never abs(-2).
                if 0 <= rank < cup.teams:
                    names.update(placement_locations(cup, rank + 1))

        if trophies & (1 << cup.trophy_bit):
            names.update(placement_locations(cup, 1))
            names.update(
                f"{cup.name} - Cup Win Bonus {i}" for i in range(1, CUP_WIN_BONUS_COUNT + 1)
            )

    if trophies & 8:
        names.add("Super Team Unlocked")
    if trophies == 0xFF:
        names.add(GOAL_LOCATION)
    for name, (offset, _) in MILESTONES.items():
        thresholds = milestone_thresholds(name, options or {})
        value = u16(data, USER_INFO + offset)
        names.update(
            f"{medal} {name} Trophy"
            for medal, threshold in zip(MEDALS, thresholds)
            if value >= threshold
        )
    return names


@dataclass(frozen=True)
class LiveMatch:
    identity: tuple
    match: Match
    ended: bool
    wins: tuple
    cup: bool = False


def read_friendly(read_bytes, manager, data, include_cups=False):
    """Stable single-human-team Grudge state, optionally including the eight cups.

    Co-op is allowed; training, custom tournaments and demos are excluded.
    """
    mode = s32(data, CURRENT_MODE_OFFSET)
    if mode not in (range(9) if include_cups else (0,)) or data[0x4959]:
        return None
    stats_ptr = u32(read_bytes(STATS_ADDRESS, 4), 0)
    if not valid_pointer(stats_ptr, STATS_SIZE):
        return None
    stats = read_bytes(stats_ptr, STATS_SIZE)
    if not data[0x4C38] and not stats[STATS_ENDED_OFFSET]:
        return None
    info_ptr = u32(stats, 0)
    if info_ptr != u32(data, GAME_INFO_POINTERS_OFFSET + mode * 4) or not valid_pointer(
        info_ptr, MATCH_SIZE
    ):
        return None
    raw = read_bytes(info_ptr, MATCH_SIZE)
    match = Match.read(raw)
    if not match.valid or match.human_side is None:
        return None
    # Reject a torn transition; winner counters are written before ended is set.
    if stats != read_bytes(stats_ptr, STATS_SIZE) or raw != read_bytes(info_ptr, MATCH_SIZE):
        return None
    identity = (
        manager,
        mode,
        stats_ptr,
        info_ptr,
        raw[:0x1C],
        u16(stats, 0x4B0),
        None if mode else u32(data, USER_INFO),
    )
    # Cup autosave can change mSaveID during the end event.
    wins = (u32(stats, 0x4B4), u32(stats, 0x4B8))
    return LiveMatch(identity, match, bool(stats[STATS_ENDED_OFFSET]), wins, bool(mode))


class FriendlyTracker:
    """Observe an actual end transition; a lead or an already-ended game is not a win."""

    def __init__(self):
        self.previous = None

    def observe(self, current):
        if current is None:
            self.previous = None
            return set()
        previous = self.previous
        self.previous = current
        if not current.ended:
            return set()
        if previous is None or previous.ended or previous.identity != current.identity:
            return set()
        delta = tuple(now - before for now, before in zip(current.wins, previous.wins))
        side = current.match.human_side
        if current.cup:
            if (
                current.match.completed_by()
                and current.match.scores[side] > current.match.scores[1 - side]
            ):
                return current.match.win_locations(side)
            return set()
        if delta == ((1, 0) if side == 0 else (0, 1)):
            return current.match.win_locations(side)
        return set()
