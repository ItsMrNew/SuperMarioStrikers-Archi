from BaseClasses import Location
from .Goals import CUSTOM_GOAL_LOCATION, goal_location, included_cups

from .Data import (
    CAPTAINS,
    CUPS,
    GOAL_LOCATION,
    MEDALS,
    MILESTONES,
    PLACEMENTS,
    SIDEKICKS,
    STADIUMS,
    THEMED_SIDEKICKS,
    THEMED_STADIUMS,
)

LOCATION_ID_BASE = 0x535800
CUP_WIN_BONUS_COUNT = 5
CHARACTER_UNLOCKS = (("Super Team Unlocked", 3),)
cup_trophy_bits = {cup.name: cup.trophy_bit for cup in CUPS}
cup_match_counts = {cup.name: cup.match_count for cup in CUPS}


def sidekick_location(captain, sidekick):
    return f"Win with {CAPTAINS[captain]} + {SIDEKICKS[sidekick]}"


def stadium_location(captain, stadium):
    return f"Win with {CAPTAINS[captain]} at {STADIUMS[stadium]}"


location_table = {}


def add(name):
    location_table[name] = LOCATION_ID_BASE + len(location_table) + 1


# Keep these location IDs stable. Append new IDs outside this block.
legacy_cups = tuple(cup for cup in CUPS if not cup.knockout)
for cup in legacy_cups:
    for number in range(1, cup.match_count + 1):
        add(f"{cup.name} - Match {number}")
for name, _ in CHARACTER_UNLOCKS:
    add(name)
for cup in legacy_cups:
    for number in range(1, CUP_WIN_BONUS_COUNT + 1):
        add(f"{cup.name} - Cup Win Bonus {number}")

for cup in CUPS:
    if cup.knockout:
        for number in range(1, cup.match_count + 1):
            add(f"{cup.name} - Match {number}")
        for number in range(1, CUP_WIN_BONUS_COUNT + 1):
            add(f"{cup.name} - Cup Win Bonus {number}")
for cup in CUPS:
    for _, placement in PLACEMENTS:
        add(f"{cup.name} - {placement}")
for milestone in MILESTONES:
    for medal in MEDALS:
        add(f"{medal} {milestone} Trophy")
for captain in CAPTAINS.values():
    add(f"First Win - {captain}")
for stadium in STADIUMS.values():
    add(f"First Win at {stadium}")
for captain in range(8):
    for sidekick in SIDEKICKS:
        add(sidekick_location(captain, sidekick))
for captain in CAPTAINS:
    for stadium in STADIUMS:
        add(stadium_location(captain, stadium))
add(GOAL_LOCATION)
add(CUSTOM_GOAL_LOCATION)


def location_groups(options):
    """The same selected location set is used by generation and the client."""
    groups = {}
    captains = options.get("included_captains", "all")
    if captains == "all" or "all" in captains:
        captains = set(CAPTAINS.values())
    stadiums = options.get("included_stadiums", "all")
    if stadiums == "all" or "all" in stadiums:
        stadiums = set(STADIUMS.values())
    for cup in CUPS:
        if cup.name not in included_cups(options):
            continue
        names = (
            [f"{cup.name} - Match {i}" for i in range(1, cup.match_count + 1)]
            if options.get("cup_match_checks", True)
            else []
        )
        names += [
            f"{cup.name} - Cup Win Bonus {i}"
            for i in range(1, options.get("cup_win_bonus_count", CUP_WIN_BONUS_COUNT) + 1)
        ]
        if options.get("placement_checks", True):
            names += [f"{cup.name} - {label}" for _, label in PLACEMENTS]
        groups[cup.name] = names
    if options.get("milestone_checks", True):
        groups["Milestone Trophies"] = [
            f"{medal} {name} Trophy"
            for name in MILESTONES
            for medal in MEDALS[: options.get("milestone_max_tier", 2) + 1]
        ]
    if options.get("captain_win_checks", True):
        groups["Captain Wins"] = [
            f"First Win - {name}" for name in CAPTAINS.values() if name in captains
        ]
    if options.get("stadium_win_checks", True):
        groups["Stadium Wins"] = [
            f"First Win at {name}" for name in STADIUMS.values() if name in stadiums
        ]
    combos = options.get("combo_checks", 1)
    if combos:
        pairs = THEMED_SIDEKICKS if combos == 1 else {(c, s) for c in range(8) for s in SIDEKICKS}
        groups["Captain and Sidekick Wins"] = [
            sidekick_location(c, s)
            for c, s in sorted(pairs)
            if CAPTAINS[c] in captains
            and (
                combos != 3 or sidekick_location(c, s) in options.get("custom_sidekick_combos", [])
            )
        ]
        pairs = THEMED_STADIUMS if combos == 1 else {(c, s) for c in CAPTAINS for s in STADIUMS}
        groups["Captain and Stadium Wins"] = [
            stadium_location(c, s)
            for c, s in sorted(pairs)
            if CAPTAINS[c] in captains
            and STADIUMS[s] in stadiums
            and (combos != 3 or stadium_location(c, s) in options.get("custom_stadium_combos", []))
        ]
    if options.get("character_unlock_checks", False):
        groups["Character Unlocks"] = [name for name, _ in CHARACTER_UNLOCKS]
    groups["Goal"] = [goal_location(options)]
    return groups


class StrikersLocation(Location):
    game = "Super Mario Strikers"
