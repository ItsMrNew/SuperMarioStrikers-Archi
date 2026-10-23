import asyncio
import json
from typing import Optional
from websockets.exceptions import ConnectionClosed

import dolphin_memory_engine

import Utils
from CommonClient import (
    ClientCommandProcessor,
    CommonContext,
    get_base_parser,
    gui_enabled,
    logger,
    server_loop,
)
from MultiServer import mark_raw
from NetUtils import ClientStatus

from .Items import CAPTAIN_ITEMS, CUP_ITEMS, SIDEKICK_ITEMS, item_flag_addresses, item_table
from .Data import CUPS, GOAL_LOCATION, PROTOCOL_VERSION
from .CupAccess import apply_cup_access
from .UnlockMemory import apply_unlocks, valid_patch
from .Session import CONNECT, READY, LEGACY_SAVE, BAD_PATCH, MESSAGES
from .SessionMemory import publish, validate_save, unchanged_save
from .Unlocks import goal_access, location_access, owned, randomized
from .Goals import goal_location, goal_reached
from .Progress import progress_lines
from .Locations import cup_match_counts, location_groups, location_table
from .Memory import (
    FriendlyTracker,
    MANAGER_ADDRESS,
    MANAGER_SIZE,
    PATCH_SIGNATURES,
    STATS_ADDRESS,
    STATS_SIZE,
    Match,
    read_friendly,
    s32,
    u32,
    valid_pointer,
    saved_locations,
    CURRENT_MODE_OFFSET,
    GAME_INFO_POINTERS_OFFSET,
    MATCH_SIZE,
    STATS_ENDED_OFFSET,
    TROPHIES,
)
from .Rewards import (
    BOOST_STORAGE_CATEGORY,
    BOOST_OWNER_KEY,
    MAX_COUNTER,
    rebase_restored_mailboxes,
    reconcile_boosts,
    settle_boosts,
)


GAME_ID = b"G4QE01"
AP_GOALLINK_MAGIC_ADDR = 0x80372DEC
AP_GOALLINK_REQUEST_ADDR = 0x80374428
AP_GOALLINK_MAGIC = 0x444C474B
AP_MAILBOX_MAGIC_ADDR = 0x80372DE8
AP_MAILBOX_SEQUENCE_ADDR = 0x8037441C
AP_MAILBOX_MODE_ADDR = 0x80374420
AP_MAILBOX_COMPLETED_ROUND_ADDR = 0x80374424
AP_MAILBOX_MAGIC = 0x5354524B
AP_POWERUP_BOOST_MAGIC_ADDR = 0x80372DF0
AP_POWERUP_BOOST_REQUEST_ADDR = 0x8037442C
AP_POWERUP_BOOST_APPLIED_ADDR = 0x80374430
AP_OPPONENT_POWERUP_REQUEST_ADDR = 0x80374434
AP_OPPONENT_POWERUP_APPLIED_ADDR = 0x80374438
AP_POWERUP_BOOST_MAGIC = 0x5055424B
# The native mailbox covers the six league cups; Bowser losses use StatsTracker.
CUP_MODE_TO_NAME = {cup.mode: cup.name for cup in CUPS if not cup.knockout}

ITEM_ID_TO_FLAG_ADDRESS = {
    item_table[item_name]: address + 0x620 for item_name, address in item_flag_addresses.items()
}
BOOST_MAILBOXES = (
    ("home", AP_POWERUP_BOOST_REQUEST_ADDR, AP_POWERUP_BOOST_APPLIED_ADDR),
    ("away", AP_OPPONENT_POWERUP_REQUEST_ADDR, AP_OPPONENT_POWERUP_APPLIED_ADDR),
)


def known_items(ctx):
    """Retain validated ownership through a network outage, never across slots."""
    if ctx.slot is None:
        return ctx.offline_items
    return ctx.items_received if ctx.item_history_received else ()


class StrikersCommandProcessor(ClientCommandProcessor):
    @mark_raw
    def _cmd_missing(self, filter_text: str = "") -> bool:
        """List missing checks; the optional filter may contain spaces."""
        return super()._cmd_missing(filter_text)

    def _cmd_dolphin(self) -> None:
        if isinstance(self.ctx, StrikersContext):
            logger.info(f"Dolphin status: {self.ctx.dolphin_status}")

    def _cmd_adoptsave(self, confirmation: str = "") -> bool:
        """Explicitly bind an untagged save and credit its existing progress."""
        if confirmation.strip().lower() != "confirm":
            logger.info(
                "To migrate an unbound save and credit its existing achievements, return to the main menu and enter /adoptsave confirm. Use a fresh save for a fresh run."
            )
            return False
        if self.ctx.save_status != LEGACY_SAVE or not self.ctx.progress_key:
            logger.info(
                "No unbound save is awaiting adoption. Saves belonging to another slot cannot be adopted."
            )
            return False
        self.ctx.adopt_save_key = self.ctx.progress_key
        logger.info("Migration requested for this slot; waiting for a stable main-menu save.")
        return True

    def _cmd_progress(self) -> bool:
        """Show the goal, remaining challenges, AP milestone targets and queued rewards."""
        ctx = self.ctx
        if not ctx.protocol_supported or ctx.progress_key is None:
            logger.info("Connect to a supported Strikers slot to see its progress.")
            return False
        logger.info("Save: %s", MESSAGES[ctx.save_status])
        for line in progress_lines(
            ctx.slot_data,
            ctx.last_game_data,
            ctx.match_wins,
            ctx.observed_checks | ctx.locations_checked,
            completed=ctx.finished_game,
        ):
            logger.info(line)
        received = {item.item for item in known_items(ctx)}
        for kind, table in (
            ("captains", CAPTAIN_ITEMS),
            ("sidekicks", SIDEKICK_ITEMS),
            ("cups", CUP_ITEMS),
        ):
            if ctx.slot_data.get(f"randomize_{kind}"):
                available = [
                    name
                    for name in table
                    if owned(ctx.slot_data, kind, name, lambda item: item_table[item] in received)
                ]
                logger.info("Available %s: %s", kind, ", ".join(available))
        queue = Utils.persistent_load().get(BOOST_STORAGE_CATEGORY, {}).get(ctx.progress_key, {})
        logger.info(
            "Pending power-ups: %d player, %d opponent; outgoing Bowser DeathLinks: %d",
            queue.get("pending_home", 0),
            queue.get("pending_away", 0),
            ctx.pending_bowser_deaths,
        )
        return True


class StrikersContext(CommonContext):
    command_processor = StrikersCommandProcessor
    game = "Super Mario Strikers"
    items_handling = 0b111

    def __init__(self, server_address: Optional[str], password: Optional[str]):
        super().__init__(server_address, password)
        self.dolphin_status = "Waiting for Dolphin"
        self.finished_game = False
        self.slot_data: dict = {}
        self.death_link_enabled = False
        self.deathlink_last_mailbox_sequence: Optional[int] = None
        self.pending_deathlink_goals = 0
        self.deathlink_wait_reason = None
        self.protocol_supported = False
        self.item_history_received = False
        self.friendly_tracker = FriendlyTracker()
        self.last_bowser_result = None
        self.bowser_result_dirty = False
        self.pending_bowser_deaths = 0
        self.deathlink_lock = asyncio.Lock()
        self.progress_key = None
        self.observed_checks = set()
        self.active_checks = set()
        self.progress_dirty = False
        self.check_lock = asyncio.Lock()
        self.match_wins = 0
        self.wins_dirty = False
        self.last_game_data = None
        self.save_status = CONNECT
        self.save_token = None
        self.adopt_save_key = None
        self.offline_items = ()

    def on_package(self, cmd: str, args: dict) -> None:
        super().on_package(cmd, args)
        if cmd == "Connected":
            # Connected and the initial ReceivedItems can arrive separately.
            # An empty pre-sync list is not evidence that saved rewards vanished.
            self.item_history_received = False
            self.slot_data = args.get("slot_data") or {}
            self.protocol_supported = self.slot_data.get("protocol_version") in (
                2,
                3,
                4,
                5,
                PROTOCOL_VERSION,
            )
            if not self.protocol_supported:
                logger.error(
                    "This client requires a Strikers protocol 2–6 seed. Game synchronization is disabled."
                )
                return
            self.active_checks = {
                location_table[name]
                for names in location_groups(self.slot_data).values()
                for name in names
            }
            seed = getattr(self, "server_seed_name", None) or self.seed_name
            if not seed:
                self.protocol_supported = False
                logger.error(
                    "The server did not provide a seed identity; synchronization is disabled."
                )
                return
            key = json.dumps([seed, self.team, self.slot], separators=(",", ":"))
            if key != self.progress_key:
                self.offline_items = ()
                self.save_status = CONNECT
                self.save_token = None
                self.adopt_save_key = None
                self.remember_bowser_result(self.last_bowser_result)
                self.progress_key = key
                self.last_game_data = None
                self.progress_dirty = False
                self.friendly_tracker = FriendlyTracker()
                self.match_wins = (
                    Utils.persistent_load().get("strikers_match_wins_v3", {}).get(key, 0)
                )
                self.wins_dirty = False
                death_state = (
                    Utils.persistent_load().get("strikers_bowser_deathlink_v1", {}).get(key)
                )
                saved_result = (
                    death_state.get("result")
                    if death_state is not None
                    else Utils.persistent_load().get("strikers_bowser_result_v2", {}).get(key)
                )
                self.pending_bowser_deaths = death_state.get("pending", 0) if death_state else 0
                self.last_bowser_result = (
                    tuple(saved_result)
                    if isinstance(saved_result, (list, tuple))
                    and len(saved_result) == 3
                    and all(isinstance(value, int) for value in saved_result)
                    else None
                )
                self.bowser_result_dirty = False
                self.finished_game = False
                self.deathlink_last_mailbox_sequence = None
                self.pending_deathlink_goals = 0
                saved = Utils.persistent_load().get("strikers_checks_v2", {}).get(key, [])
                self.observed_checks = {
                    value for value in saved if isinstance(value, int)
                } & self.active_checks
            self.death_link_enabled = bool(self.slot_data.get("death_link", False))
            Utils.async_start(self.update_death_link(self.death_link_enabled))
            Utils.async_start(self.flush_checks())
        elif cmd == "ReceivedItems":
            if args.get("index") == 0:
                self.item_history_received = True
            if self.item_history_received:
                self.offline_items = tuple(self.items_received)

    async def record_checks(self, names) -> None:
        found = {
            location_table[name] for name in names if name in location_table
        } & self.active_checks
        if not found <= self.observed_checks:
            self.observed_checks.update(found)
            self.progress_dirty = True
        await self.flush_checks()

    def remember_bowser_result(self, result, *, loss=False) -> None:
        if result != self.last_bowser_result:
            self.last_bowser_result = result
            if loss:
                self.pending_bowser_deaths += 1
            self.bowser_result_dirty = True
        if self.bowser_result_dirty and self.progress_key is not None:
            # Preserve the acknowledgement through client restarts. Retain the
            # in-memory acknowledgement if storage fails, then retry the write.
            Utils.persistent_store(
                "strikers_bowser_deathlink_v1",
                self.progress_key,
                {
                    "result": list(result) if result is not None else None,
                    "pending": self.pending_bowser_deaths,
                },
            )
            self.bowser_result_dirty = False

    async def flush_bowser_deaths(self) -> None:
        """Deliver persisted losses even after leaving the result or restarting Dolphin."""
        async with self.deathlink_lock:
            self.remember_bowser_result(self.last_bowser_result)
            if not self.protocol_supported or not self.death_link_enabled or self.slot is None:
                return
            while self.pending_bowser_deaths:
                owner = self.progress_key
                try:
                    await self.send_death("Super Mario Strikers: lost a Bowser cup match")
                except (OSError, ConnectionClosed):
                    # Keep observing matches while the server is disconnected.
                    return
                if owner != self.progress_key:
                    # Connected can select another seed while the socket write
                    # yields. Acknowledge the outgoing seed, never debit the new one.
                    previous = dict(Utils.persistent_load()["strikers_bowser_deathlink_v1"][owner])
                    previous["pending"] -= 1
                    Utils.persistent_store("strikers_bowser_deathlink_v1", owner, previous)
                    return
                self.pending_bowser_deaths -= 1
                self.bowser_result_dirty = True
                self.remember_bowser_result(self.last_bowser_result)

    async def flush_checks(self) -> None:
        async with self.check_lock:
            if not self.protocol_supported or self.progress_key is None:
                return
            if self.wins_dirty:
                Utils.persistent_store("strikers_match_wins_v3", self.progress_key, self.match_wins)
                self.wins_dirty = False
            if self.progress_dirty:
                # Persist before delivery. Retain the dirty flag on write failure
                # so a transient Grudge result is retried instead of forgotten.
                Utils.persistent_store(
                    "strikers_checks_v2", self.progress_key, sorted(self.observed_checks)
                )
                self.progress_dirty = False
            pending = self.observed_checks - self.locations_checked
            if pending:
                if self.slot is not None:
                    await self.check_locations(pending)
                # CommonClient resends local checks on reconnection.
                self.locations_checked.update(pending)
                logger.info("Recorded %d new Strikers location(s)", len(pending))
            if (
                location_table[goal_location(self.slot_data)] in self.observed_checks
                and not self.finished_game
            ):
                if (
                    self.slot is not None
                    and self.server
                    and self.server.socket.open
                    and not self.server.socket.closed
                ):
                    await self.send_msgs(
                        [{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]
                    )
                    self.finished_game = True

    def on_deathlink(self, data: dict) -> None:
        source = data.get("source", "another player")
        logger.info("Received DeathLink from %s; applying a goal against", source)
        # The game-side score penalty is queued for the Dolphin loop to apply
        # once a cup match is active.
        self.pending_deathlink_goals += 1
        super().on_deathlink(data)

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(True)
        await self.get_username()
        await self.send_connect()

    async def send_death(self, death_text: str = "") -> None:
        # CommonClient.send_msgs silently returns when disconnected. A result
        # must remain unacknowledged in that case so it can be retried.
        if not self.server or not self.server.socket.open or self.server.socket.closed:
            raise ConnectionError("DeathLink is waiting for an open server connection")
        await super().send_death(death_text)


def read_u32(address: int) -> int:
    return int.from_bytes(dolphin_memory_engine.read_bytes(address, 4), "big")


async def check_deathlink_cup_losses(ctx: StrikersContext) -> None:
    if not ctx.death_link_enabled or ctx.slot is None:
        return

    mailbox = read_cup_mailbox()
    if mailbox is None:
        return

    cup_name, completed_count, is_loss, sequence = mailbox
    previous_sequence = ctx.deathlink_last_mailbox_sequence
    if sequence == previous_sequence:
        return
    if previous_sequence is not None and sequence < previous_sequence:
        ctx.deathlink_last_mailbox_sequence = sequence
        return

    logger.info(
        "Cup result observed: %s match %d (%s)",
        cup_name,
        completed_count,
        "loss" if is_loss else "not a loss",
    )
    if not is_loss:
        ctx.deathlink_last_mailbox_sequence = sequence
        return

    # Sequence identifies the result, even when replaying the same cup round.
    # Leave it unacknowledged if sending raises so the next poll can retry.
    await ctx.send_death("Super Mario Strikers: lost a cup match")
    ctx.deathlink_last_mailbox_sequence = sequence
    if read_u32(AP_MAILBOX_SEQUENCE_ADDR) == sequence:
        completed_raw = read_u32(AP_MAILBOX_COMPLETED_ROUND_ADDR)
        if completed_raw & 0x80000000:
            dolphin_memory_engine.write_bytes(
                AP_MAILBOX_COMPLETED_ROUND_ADDR,
                (completed_raw & 0x7FFFFFFF).to_bytes(4, "big"),
            )
    logger.info("Sent DeathLink for losing %s match %d", cup_name, completed_count)


def read_cup_mailbox() -> Optional[tuple[str, int, bool, int]]:
    sequence_before = read_u32(AP_MAILBOX_SEQUENCE_ADDR)
    mailbox_mode = read_u32(AP_MAILBOX_MODE_ADDR)
    completed_raw = read_u32(AP_MAILBOX_COMPLETED_ROUND_ADDR)
    sequence_after = read_u32(AP_MAILBOX_SEQUENCE_ADDR)
    if (
        read_u32(AP_MAILBOX_MAGIC_ADDR) != AP_MAILBOX_MAGIC
        or sequence_before == 0
        or sequence_before != sequence_after
        or mailbox_mode not in CUP_MODE_TO_NAME
    ):
        return None
    cup_name = CUP_MODE_TO_NAME[mailbox_mode]
    completed_count = completed_raw & 0x7FFFFFFF
    if not 1 <= completed_count <= cup_match_counts[cup_name]:
        return None
    return cup_name, completed_count, bool(completed_raw & 0x80000000), sequence_before


async def apply_deathlink_goal_against(ctx: StrikersContext) -> None:
    pending = ctx.pending_deathlink_goals
    if not ctx.death_link_enabled or pending <= 0:
        return
    if read_u32(AP_GOALLINK_MAGIC_ADDR) != AP_GOALLINK_MAGIC:
        if ctx.deathlink_wait_reason != "missing goal-event Riivolution patch":
            logger.warning(
                "Received DeathLink goal is waiting for the updated Strikers Riivolution patch"
            )
            ctx.deathlink_wait_reason = "missing goal-event Riivolution patch"
        return

    request_count = read_u32(AP_GOALLINK_REQUEST_ADDR)
    if request_count + pending > MAX_COUNTER:
        logger.warning("DeathLink goal mailbox is full; leaving the received goal queued")
        return
    dolphin_memory_engine.write_bytes(
        AP_GOALLINK_REQUEST_ADDR, (request_count + pending).to_bytes(4, "big")
    )
    ctx.pending_deathlink_goals = 0
    ctx.deathlink_wait_reason = None
    logger.info("Queued %d DeathLink goal(s) for the game's normal goal event", pending)


async def apply_received_items(ctx: StrikersContext) -> None:
    if ctx.slot is None or not ctx.item_history_received:
        return

    for network_item in ctx.items_received:
        address = ITEM_ID_TO_FLAG_ADDRESS.get(network_item.item)
        if address is None:
            continue
        if dolphin_memory_engine.read_byte(address) == 0:
            dolphin_memory_engine.write_bytes(address, b"\x01")

    # Keep persistent accounting independent of the emulator I/O. The persisted
    # storage keys "home"/"away" mean player/opponent, not fixed pitch sides.
    storage = Utils.persistent_load().get(BOOST_STORAGE_CATEGORY, {})
    previous = storage.get(ctx.progress_key, {})
    baseline = previous
    applied_counts = None
    if read_u32(AP_POWERUP_BOOST_MAGIC_ADDR) == AP_POWERUP_BOOST_MAGIC:
        applied_counts = {channel: read_u32(applied) for channel, _, applied in BOOST_MAILBOXES}
        request_counts = {channel: read_u32(request) for channel, request, _ in BOOST_MAILBOXES}
        owner = storage.get(BOOST_OWNER_KEY)
        if owner is None or owner == ctx.progress_key:
            baseline = rebase_restored_mailboxes(previous, applied_counts, request_counts)
        if owner is not None and owner != ctx.progress_key:
            # Withdraw the outgoing seed's unconsumed requests before changing
            # ownership, then settle any final acknowledgements to that seed.
            for channel, request_addr, _ in BOOST_MAILBOXES:
                dolphin_memory_engine.write_bytes(
                    request_addr, applied_counts[channel].to_bytes(4, "big")
                )
            applied_counts = {channel: read_u32(applied) for channel, _, applied in BOOST_MAILBOXES}
            outgoing = storage.get(owner, {})
            outgoing_baseline = rebase_restored_mailboxes(outgoing, applied_counts, request_counts)
            settled = settle_boosts(outgoing_baseline, applied_counts)
            if settled != outgoing:
                Utils.persistent_store(BOOST_STORAGE_CATEGORY, owner, settled)
            baseline = dict(previous)
            for channel, _, _ in BOOST_MAILBOXES:
                baseline[f"last_applied_{channel}"] = None
    saved = reconcile_boosts(baseline, ctx.items_received, applied_counts)

    # Commit accounting/ownership before publishing new consumable requests.
    # A crash or failed disk write must not deliver an unrecorded first reward.
    if saved != previous:
        Utils.persistent_store(BOOST_STORAGE_CATEGORY, ctx.progress_key, saved)
    if applied_counts is not None and storage.get(BOOST_OWNER_KEY) != ctx.progress_key:
        Utils.persistent_store(BOOST_STORAGE_CATEGORY, BOOST_OWNER_KEY, ctx.progress_key)
    if applied_counts is not None:
        for channel, request_addr, _ in BOOST_MAILBOXES:
            desired = applied_counts[channel] + saved[f"pending_{channel}"]
            if desired <= MAX_COUNTER and read_u32(request_addr) != desired:
                dolphin_memory_engine.write_bytes(request_addr, desired.to_bytes(4, "big"))


async def check_expansion_locations(ctx: StrikersContext) -> None:
    if ctx.save_token is not None and not unchanged_save(
        dolphin_memory_engine.read_bytes, ctx.progress_key, ctx.save_token
    ):
        ctx.friendly_tracker = FriendlyTracker()
        return
    manager = read_u32(MANAGER_ADDRESS)
    if not valid_pointer(manager, MANAGER_SIZE):
        return
    data = dolphin_memory_engine.read_bytes(manager, MANAGER_SIZE)
    # Save loading and tournament transitions can replace multiple fields. Do
    # not decode a mixture of two states, or carry results across save loads.
    if data != dolphin_memory_engine.read_bytes(manager, MANAGER_SIZE):
        return
    if manager != read_u32(MANAGER_ADDRESS):
        return
    ctx.last_game_data = data
    names = saved_locations(data, ctx.slot_data)
    names.discard(GOAL_LOCATION)
    current = read_friendly(dolphin_memory_engine.read_bytes, manager, data, include_cups=True)
    wins = ctx.friendly_tracker.observe(current)
    names.update(wins)
    if wins and ctx.slot_data.get("goal") == "match_wins":
        ctx.match_wins += 1
        ctx.wins_dirty = True
        logger.info(
            "Match wins: %d / %d", ctx.match_wins, ctx.slot_data.get("required_match_wins", 25)
        )
    goal_name = goal_location(ctx.slot_data)
    if randomized(ctx.slot_data):
        # AP 0.6.8 omits ReceivedItems when the inventory is empty, even for
        # Sync. Starting checks must work before the very first reward arrives.
        # Do not trust a previous connection's items before the index-zero packet.
        received = {item.item for item in known_items(ctx)}

        def has(item):
            return item_table[item] in received

        names = {name for name in names if location_access(ctx.slot_data, name, has)}
    active = ctx.active_checks - {location_table[goal_name]}
    checked = ctx.observed_checks | ctx.locations_checked | {location_table[name] for name in names}
    enabled_names = [name for name, code in location_table.items() if code in active]
    can_goal = not randomized(ctx.slot_data) or goal_access(ctx.slot_data, enabled_names, has)
    if can_goal and goal_reached(ctx.slot_data, data[TROPHIES], ctx.match_wins, checked, active):
        names.add(goal_name)
    await ctx.record_checks(names)
    await check_bowser_deathlink(ctx, manager, data)


async def check_bowser_deathlink(ctx: StrikersContext, manager: int, data: bytes) -> None:
    # The supplied game-side mailbox only publishes the original six cups.
    if (
        ctx.progress_key is None
        or not ctx.death_link_enabled
        or s32(data, CURRENT_MODE_OFFSET) not in (4, 8)
    ):
        return
    mode = s32(data, CURRENT_MODE_OFFSET)
    stats_ptr = read_u32(STATS_ADDRESS)
    if not valid_pointer(stats_ptr, STATS_SIZE):
        return
    stats = dolphin_memory_engine.read_bytes(stats_ptr, STATS_SIZE)
    if not stats[STATS_ENDED_OFFSET]:
        ctx.remember_bowser_result(None)
        return
    info_ptr = u32(stats, 0)
    if info_ptr != u32(data, GAME_INFO_POINTERS_OFFSET + mode * 4) or not valid_pointer(
        info_ptr, MATCH_SIZE
    ):
        return
    raw = dolphin_memory_engine.read_bytes(info_ptr, MATCH_SIZE)
    match = Match.read(raw)
    if (
        not match.completed_by()
        or stats != dolphin_memory_engine.read_bytes(stats_ptr, STATS_SIZE)
        or raw != dolphin_memory_engine.read_bytes(info_ptr, MATCH_SIZE)
    ):
        return
    # Scores/counters can change during result processing, and autosave changes
    # mSaveID afterward. Neither identifies a new match attempt. The ended flag
    # above resets this identity when another match starts.
    key = (manager, mode, info_ptr)
    if key == ctx.last_bowser_result:
        ctx.remember_bowser_result(key)
        await ctx.flush_bowser_deaths()
        return
    side = match.human_side
    ctx.remember_bowser_result(key, loss=match.scores[side] < match.scores[1 - side])
    await ctx.flush_bowser_deaths()


async def dolphin_sync_task(ctx: StrikersContext) -> None:
    logger.info(
        "Starting Super Mario Strikers Dolphin connector. Use /progress for goals and /dolphin for status."
    )

    while not ctx.exit_event.is_set():
        try:
            await ctx.flush_bowser_deaths()
            if not dolphin_memory_engine.is_hooked():
                ctx.last_game_data = None
                ctx.friendly_tracker = FriendlyTracker()
                dolphin_memory_engine.hook()

            if not dolphin_memory_engine.is_hooked():
                ctx.dolphin_status = "Dolphin not found; retrying"
                await asyncio.sleep(3)
                continue

            game_id = dolphin_memory_engine.read_bytes(0x80000000, 6)
            if game_id != GAME_ID:
                ctx.last_game_data = None
                ctx.dolphin_status = f"Wrong game loaded ({game_id!r}); expected G4QE01"
                dolphin_memory_engine.un_hook()
                await asyncio.sleep(3)
                continue

            if any(
                dolphin_memory_engine.read_bytes(address, len(expected)) != expected
                for address, expected in PATCH_SIGNATURES.items()
            ):
                ctx.dolphin_status = (
                    "Wrong executable; enable the bundled StrikersAP Riivolution patch"
                )
                await asyncio.sleep(3)
                continue

            read, write = dolphin_memory_engine.read_bytes, dolphin_memory_engine.write_bytes
            if not valid_patch(read):
                ctx.save_status = BAD_PATCH
                ctx.save_token = None
                ctx.last_game_data = None
                ctx.dolphin_status = MESSAGES[BAD_PATCH]
                await asyncio.sleep(3)
                continue
            key = ctx.progress_key if ctx.protocol_supported else None
            status, token = validate_save(
                read, write, key, adopt=bool(key and ctx.adopt_save_key == key)
            )
            if status != ctx.save_status:
                logger.info("Save: %s", MESSAGES[status])
                ctx.friendly_tracker = FriendlyTracker()
            ctx.save_status, ctx.save_token = status, token
            ctx.dolphin_status = MESSAGES[status]
            if status != READY:
                publish(read, write, status)
                ctx.last_game_data = None
                await asyncio.sleep(0.15)
                continue
            ctx.adopt_save_key = None
            if not apply_unlocks(
                dolphin_memory_engine.read_bytes,
                dolphin_memory_engine.write_bytes,
                ctx.slot_data,
                known_items(ctx),
            ):
                publish(read, write, BAD_PATCH)
                ctx.dolphin_status = MESSAGES[BAD_PATCH]
                await asyncio.sleep(3)
                continue
            if not apply_cup_access(
                dolphin_memory_engine.read_bytes,
                dolphin_memory_engine.write_bytes,
                ctx.slot_data.get("starting_cup_unlocks", 0),
            ):
                publish(read, write, BAD_PATCH)
                ctx.dolphin_status = "Starting cup unlocks require the supplied Riivolution patch; install it and boot the game again"
                await asyncio.sleep(3)
                continue
            if not unchanged_save(read, key, token):
                publish(read, write, CONNECT)
                continue
            publish(read, write, READY, ready=True)
            await apply_deathlink_goal_against(ctx)
            await check_deathlink_cup_losses(ctx)
            await apply_received_items(ctx)
            if ctx.protocol_supported and ctx.progress_key is not None:
                await check_expansion_locations(ctx)
            await asyncio.sleep(0.15)
        except Exception:
            ctx.last_game_data = None
            logger.exception("Dolphin connection failed; retrying")
            ctx.dolphin_status = "Dolphin connection lost; retrying"
            dolphin_memory_engine.un_hook()
            await asyncio.sleep(3)


def main(*args: str) -> None:
    Utils.init_logging("Super Mario Strikers Client")

    async def run(connect: Optional[str], password: Optional[str]) -> None:
        ctx = StrikersContext(connect, password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        await asyncio.sleep(1)

        dolphin_task = asyncio.create_task(dolphin_sync_task(ctx), name="DolphinSync")
        await ctx.exit_event.wait()
        ctx.server_address = None
        ctx.watcher_event.set()
        await ctx.shutdown()
        await dolphin_task

    parser = get_base_parser(description="Super Mario Strikers Archipelago client")
    parsed_args = parser.parse_args(args)
    asyncio.run(run(parsed_args.connect, parsed_args.password))
