"""Game IDs and structure offsets for the supplied G4QE01 executable."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Cup:
    name: str
    mode: int
    offset: int
    teams: int
    rounds: int
    knockout: int = 0

    @property
    def trophy_bit(self):
        return self.mode - 1

    @property
    def match_count(self):
        return self.rounds + (2 if self.knockout else 0)


CUPS = (
    Cup("Mushroom Cup", 1, 0x0078, 4, 3),
    Cup("Flower Cup", 2, 0x025C, 6, 5),
    Cup("Star Cup", 3, 0x05E4, 8, 7),
    Cup("Bowser Cup", 4, 0x0B8C, 8, 7, 0x1134),
    Cup("Super Mushroom Cup", 5, 0x12B8, 4, 6),
    Cup("Super Flower Cup", 6, 0x1560, 6, 10),
    Cup("Super Star Cup", 7, 0x1ACC, 8, 14),
    Cup("Super Bowser Cup", 8, 0x23FC, 8, 14, 0x2D2C),
)
CUP_BY_MODE = {cup.mode: cup for cup in CUPS}
CAPTAINS = {
    0: "Daisy",
    1: "Donkey Kong",
    2: "Luigi",
    3: "Mario",
    4: "Peach",
    5: "Waluigi",
    6: "Wario",
    7: "Yoshi",
    8: "Super Team",
}
SIDEKICKS = {0: "Toad", 1: "Koopa Troopa", 2: "Hammer Bro", 3: "Birdo"}
STADIUMS = {
    0: "Pipeline Central",
    1: "The Palace",
    2: "Konga Coliseum",
    3: "The Underground",
    4: "Crater Field",
    5: "Bowser Stadium",
    6: "The Battle Dome",
}
# Curated AP challenges; these are not pairings enforced by the original game.
THEMED_SIDEKICKS = {(0, 3), (1, 2), (2, 1), (3, 0), (4, 0), (5, 2), (6, 1), (7, 3)}
THEMED_STADIUMS = {(0, 2), (1, 2), (2, 0), (3, 0), (4, 1), (5, 3), (6, 3), (7, 4)}
# (UserInfo-relative unsigned-short counter, bronze/silver/gold thresholds)
MILESTONES = {
    "Veteran": (0x1112, (25, 50, 100)),
    "Sniper": (0x1114, (75, 150, 300)),
    "Super Striker": (0x1116, (25, 50, 100)),
    "Tactician": (0x1118, (75, 150, 300)),
    "Paramedic": (0x111A, (250, 500, 1000)),
}
MEDALS = ("Bronze", "Silver", "Gold")
PLACEMENTS = ((3, "Top 3"), (2, "Top 2"), (1, "Champion"))
GOAL_LOCATION = "All Eight Battle Trophies"
PROTOCOL_VERSION = 6


def milestone_thresholds(name, options):
    """AP targets only; never change native counters, medals or save data."""
    percent = options.get("milestone_requirement_percent", 100)
    return tuple((value * percent + 99) // 100 for value in MILESTONES[name][1])
