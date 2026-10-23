"""Goal selection shared by world generation and the emulator client."""

from .Data import CUPS, GOAL_LOCATION

CUSTOM_GOAL_LOCATION = "Goal Complete"
CUP_NAMES = frozenset(cup.name for cup in CUPS)


def included_cups(options):
    selected = options.get("included_cups", CUP_NAMES)
    return CUP_NAMES if selected == "all" or "all" in selected else set(selected)


def goal_location(options):
    if (
        options.get("goal", "battle_trophies") in ("battle_trophies", "all_eight_battle_trophies")
        and options.get("required_battle_trophies", 8) == 8
    ):
        return GOAL_LOCATION
    return CUSTOM_GOAL_LOCATION


def validate_options(options):
    included = included_cups(options)
    goal = options["goal"]
    if goal == "battle_trophies" and options["required_battle_trophies"] > len(included):
        raise ValueError("required_battle_trophies cannot exceed the number of included_cups")
    if goal == "selected_cups":
        required = set(options["required_cups"])
        if not required or not required <= included:
            raise ValueError("required_cups must be nonempty and contained in included_cups")


def goal_reached(options, trophies, wins, checked, active):
    """checked/active contain location IDs, with the goal already removed."""
    goal = options.get("goal", "battle_trophies")
    earned = {cup.name for cup in CUPS if trophies & (1 << cup.trophy_bit)}
    if goal in ("battle_trophies", "all_eight_battle_trophies"):
        return len(earned & included_cups(options)) >= options.get("required_battle_trophies", 8)
    if goal == "selected_cups":
        required = set(options.get("required_cups", ()))
        return bool(required) and required <= earned
    if goal == "match_wins":
        return wins >= options.get("required_match_wins", 25)
    if goal == "all_enabled_checks":
        return bool(active) and active <= checked
    return False
