"""Seed configuration, item ownership and AP reachability for optional unlocks."""

from .Data import CAPTAINS, CUPS, SIDEKICKS
from .Goals import included_cups
from .Items import CAPTAIN_ITEMS, CUP_ITEMS, SIDEKICK_ITEMS, STADIUM_ITEMS


def randomized(options):
    return any(
        options.get(f"randomize_{kind}", False) for kind in ("captains", "sidekicks", "cups")
    )


def starting(options, kind):
    defaults = {"captains": ("Mario", "Luigi"), "sidekicks": ("Toad",), "cups": ("Mushroom Cup",)}
    result = set(options.get(f"starting_{kind}", defaults[kind]))
    if kind == "cups":
        groups = options.get("starting_cup_unlocks", 0)
        result.update(cup.name for cup in CUPS if groups & (1 if cup.mode <= 4 else 2))
    return result


def progression_items(options):
    if not randomized(options):
        return set()
    # These stadiums and Super Team can otherwise depend on a locked cup.
    result = set(STADIUM_ITEMS.values())
    result.add("Super Team Unlock")
    for kind, table in (
        ("captains", CAPTAIN_ITEMS),
        ("sidekicks", SIDEKICK_ITEMS),
        ("cups", CUP_ITEMS),
    ):
        if options.get(f"randomize_{kind}"):
            result.update(
                item for name, item in table.items() if name not in starting(options, kind)
            )
            result.difference_update(table[name] for name in starting(options, kind))
    return result


def validate_unlocks(options, count):
    for kind, minimum in (("captains", 2), ("sidekicks", 1), ("cups", 1)):
        if options.get(f"randomize_{kind}") and len(starting(options, kind)) < minimum:
            raise ValueError(f"randomize_{kind} requires at least {minimum} starting {kind}")
    required = len(progression_items(options))
    if required > count:
        raise ValueError(
            f"Unlock randomisation needs {required} item locations, but only {count} are enabled. "
            "Enable more checks or add more starting unlocks."
        )


def owned(options, kind, name, has):
    table = {"captains": CAPTAIN_ITEMS, "sidekicks": SIDEKICK_ITEMS, "cups": CUP_ITEMS}[kind]
    if options.get(f"randomize_{kind}"):
        return name in starting(options, kind) or has(table[name])
    if kind == "captains" and name == "Super Team" and randomized(options):
        return has("Super Team Unlock")
    return True


def location_access(options, name, has):
    """Conservative item requirements; Grudge Match provides all roster win checks."""
    if not randomized(options):
        return True

    def cup_access(cup):
        return owned(options, "cups", cup, has)

    for cup in CUPS:
        if name.startswith(cup.name + " - "):
            return cup_access(cup.name)
    if name == "Super Team Unlocked":
        return cup_access("Bowser Cup")
    if name.endswith(" Trophy"):
        return any(cup_access(cup.name) for cup in CUPS)
    for captain in CAPTAINS.values():
        if name == f"First Win - {captain}" or name.startswith(f"Win with {captain} "):
            if not owned(options, "captains", captain, has):
                return False
    for sidekick in SIDEKICKS.values():
        if name.endswith(" + " + sidekick) and not owned(options, "sidekicks", sidekick, has):
            return False
    for stadium, item in STADIUM_ITEMS.items():
        if name.endswith(" at " + stadium) and not has(item):
            return False
    return True


def goal_access(options, names, has):
    if not randomized(options):
        return True
    goal = options.get("goal", "battle_trophies")

    def cup_access(cup):
        return owned(options, "cups", cup, has)

    if goal == "battle_trophies":
        return sum(cup_access(cup) for cup in included_cups(options)) >= options.get(
            "required_battle_trophies", 8
        )
    if goal == "selected_cups":
        return all(cup_access(cup) for cup in options["required_cups"])
    if goal == "all_enabled_checks":
        return all(location_access(options, name, has) for name in names)
    return True
