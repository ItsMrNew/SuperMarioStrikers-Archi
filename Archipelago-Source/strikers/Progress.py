"""Human-readable progress from the client's last stable game snapshot."""

from .Data import CUPS, MEDALS, MILESTONES, milestone_thresholds
from .Goals import goal_location, included_cups
from .Locations import location_groups, location_table
from .Memory import TROPHIES, USER_INFO, u16


def progress_lines(options, data, wins, checked, *, completed=False):
    groups = location_groups(options)
    goal = options.get("goal", "battle_trophies")
    goal_id = location_table[goal_location(options)]
    active = {location_table[name] for names in groups.values() for name in names} - {goal_id}
    done = len(active & checked)
    lines = [f"Goal: {goal.replace('_', ' ')}" + (" — completed" if completed else "")]
    if goal == "match_wins":
        lines.append(f"Match wins: {wins}/{options.get('required_match_wins', 25)}")
    elif goal in ("battle_trophies", "all_eight_battle_trophies", "selected_cups"):
        if data is None:
            lines.append("Cup trophies: waiting for a stable Dolphin save snapshot")
        else:
            earned = {cup.name for cup in CUPS if data[TROPHIES] & (1 << cup.trophy_bit)}
            required = (
                set(options.get("required_cups", []))
                if goal == "selected_cups"
                else included_cups(options)
            )
            target = (
                len(required)
                if goal == "selected_cups"
                else options.get("required_battle_trophies", 8)
            )
            lines.append(f"Cup trophies: {len(earned & required)}/{target}")
            remaining = [cup.name for cup in CUPS if cup.name in required - earned]
            if remaining and len(earned & required) < target:
                label = (
                    "Required cups remaining"
                    if goal == "selected_cups"
                    else "Available trophies remaining"
                )
                lines.append(f"{label}: {', '.join(remaining)}")
    lines.append(
        f"Checks: {done}/{len(active)} ({len(active) - done} remaining, excluding the goal)"
    )
    for group, names in groups.items():
        if group != "Goal" and names:
            count = sum(location_table[name] in checked for name in names)
            if count < len(names):
                lines.append(f"  {group}: {count}/{len(names)}")
    if data is not None and options.get("milestone_checks", True):
        for name, (offset, _) in MILESTONES.items():
            value = u16(data, USER_INFO + offset)
            for medal, threshold in list(zip(MEDALS, milestone_thresholds(name, options)))[
                : options.get("milestone_max_tier", 2) + 1
            ]:
                if location_table[f"{medal} {name} Trophy"] not in checked:
                    lines.append(f"  Next {name}: {value}/{threshold} ({medal}, AP target)")
                    break
    lines.append(
        "Use /missing with a cup, captain, stadium or trophy name to list individual checks."
    )
    return lines
