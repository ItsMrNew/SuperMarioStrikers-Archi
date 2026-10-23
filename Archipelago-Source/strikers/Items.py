from BaseClasses import Item

from .Data import CAPTAINS, CUPS, SIDEKICKS


ITEM_ID_BASE = 0x535400

# These are the unlock flags present in the North American G4QE01 executable.
# The Dolphin client reapplies each received unlock while the game is running.
item_flag_addresses = {
    "Konga Unlock": 0x80373DE8,
    "Yoshi Unlock": 0x80373DE9,
    "Forbidden Stadium Unlock": 0x80373DEA,
    "Super Stadium Unlock": 0x80373DEB,
    "Super Team Unlock": 0x80373DEC,
    "All Strikers Unlock": 0x80373DED,
    "Tilt Control Cheat": 0x80373DEE,
    "Goalie Control Cheat": 0x80373DEF,
    "Unlimited Cheat": 0x80373DF0,
    "Shells Cheat": 0x80373DF1,
    "Enhance Cheat": 0x80373DF2,
    "Giant Cheat": 0x80373DF3,
    "Explosive Cheat": 0x80373DF4,
    "Freezing Cheat": 0x80373DF5,
}

CHEAT_UNLOCKS = frozenset(
    name for name in item_flag_addresses if name.endswith("Cheat") or name == "All Strikers Unlock"
)

item_table = {
    **{name: ITEM_ID_BASE + index for index, name in enumerate(item_flag_addresses, start=1)},
    "Nothing": ITEM_ID_BASE + 0x20,
    "Victory": ITEM_ID_BASE + 0x21,
    "Power-Up Boost": ITEM_ID_BASE + 0x22,
    "Double Power-Up Boost": ITEM_ID_BASE + 0x23,
    "Power-Up Boost Trap": ITEM_ID_BASE + 0x24,
}

CAPTAIN_ITEMS = {name: f"{name} Captain Unlock" for name in CAPTAINS.values()}
CAPTAIN_ITEMS["Super Team"] = "Super Team Unlock"
SIDEKICK_ITEMS = {name: f"{name} Sidekick Unlock" for name in SIDEKICKS.values()}
CUP_ITEMS = {cup.name: f"{cup.name} Unlock" for cup in CUPS}
STADIUM_ITEMS = {
    "Konga Coliseum": "Konga Unlock",
    "Crater Field": "Yoshi Unlock",
    "Bowser Stadium": "Forbidden Stadium Unlock",
    "The Battle Dome": "Super Stadium Unlock",
}
# Append IDs. Super Team keeps its original flag-item ID.
item_table.update(
    {
        name: ITEM_ID_BASE + 0x30 + index
        for index, name in enumerate(
            [name for name in CAPTAIN_ITEMS.values() if name != "Super Team Unlock"]
            + list(SIDEKICK_ITEMS.values())
            + list(CUP_ITEMS.values())
        )
    }
)

powerup_item_units = {
    "Power-Up Boost": (1, 0),
    "Double Power-Up Boost": (2, 0),
    "Power-Up Boost Trap": (0, 2),
}


class StrikersItem(Item):
    game = "Super Mario Strikers"
