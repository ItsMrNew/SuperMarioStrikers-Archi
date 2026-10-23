# Development

Player setup is in [README.txt](README.txt). The
[world reference](Archipelago-Source/strikers/README.md) describes YAML options
and check rules.

## Build and install

Run from the repository root with Python 3.12 or later:

```powershell
py -3.12 tools/build_release.py
```

The build creates `Archipelago/strikers.apworld`, `release-manifest.json` and a
distribution ZIP named using `world_version` in `archipelago.json`.
Archives use deterministic ordering and timestamps and exclude Python bytecode.

Close Dolphin and the Strikers client before installing:

```powershell
py -3.12 tools/install.py
```

For custom locations:

```powershell
py -3.12 tools/install.py --archipelago "C:/ProgramData/Archipelago" --dolphin-user "C:/path/to/Dolphin User"
```

The installer verifies every component against the manifest before copying,
backs up replaced files using their hashes and leaves game saves and controller
settings alone. `--check` verifies an installation without changing files.

## Source layout

| Module | Responsibility |
| --- | --- |
| `Data.py`, `Items.py`, `Locations.py` | Game definitions and stable item/location IDs |
| `Options.py`, `Goals.py`, `__init__.py` | YAML options, goals and world generation |
| `Unlocks.py`, `UnlockPatch.py` | Progression requirements and native ownership settings |
| `Session.py` | Save identity and connection state |
| `Memory.py` | Stable game snapshots and achievement decoding |
| `Rewards.py` | Power-up queue accounting |
| `Client.py` | Archipelago/Dolphin I/O, durable checks, rewards and DeathLink |
| `tools/patch_*.py`, `tools/ppc.py` | Guarded executable patch construction |

Keep item/location IDs, persisted storage keys and protocol fields stable.
Generated seeds use protocol 6; the client accepts protocols 2 through 6.
Build metadata and executable hash guards identify compatible inputs.

## Native patch

All absolute addresses refer to the bundled G4QE01 executable. Patch tools
check input hashes and instruction bytes before changing a binary; use separate
input and output files. The underlying game-patch source is not included.

- `patch_difficulty.py` skips the forced difficulty override at `0x8017AAD0`
  and `0x8017B760`, preserving the selected cup difficulty.
- `patch_cup_access.py` uses the skipped code block to apply the configured
  starting-cup access before the native qualification routine.
- `patch_unlocks.py` applies captain, sidekick and cup gates. The reserved
  text section starts at `0x8038B000` and is `0x3000` bytes long.
  Both OSInit arena paths reserve through `0x8038E000` before clearing memory.
- Ownership words start at `0x8038C704`: enabled categories, captain icon mask,
  sidekick icon mask and cup mask. Captain icon IDs differ from saved team IDs.
- The mutable session region is `0x8038C790–0x8038C7CF`. It contains lease frames,
  status, mask revision, save-load epoch, displayed revision and popup pointer.
  The integrity check excludes only declared mutable bytes.
- `RST6` identifies the section layout. The restoration manifest starts at
  section offset `0x2800`.

Native gates cover both roster grids, random selection, cup display and entry,
Super Team and saved cup resumes. CPU cup rosters stay unrestricted.
Lock settings do not award trophies or overwrite fixture records.

## Save and connection handling

`Session.py` stores an eight-byte seed/team/slot tag in UserInfo padding:
offsets `0x4E/0x4F`, `0x25–0x27` and `0x2D–0x2F`. Native save/load copies
the complete UserInfo and calculates its normal checksum. The save ID changes
on each save and cannot identify an AP slot.

Binding requires a stable title/main-menu snapshot with no active match.
Unbound saves with achievements require explicit adoption. A save tagged for
another slot is never adopted. Binding writes the magic last and checks the
complete snapshot.

`patch_session.py` ticks the 300-frame lease in `FrontEndTask::Run`
at `0x80170B78` and invalidates it in `SetMemoryCardData` at `0x8017BDCC`.
`FrontEnd::Update` does not run in menu task state 4 and cannot drive the lease.

The client verifies the save before publishing ownership, renewing the lease or
synchronizing game data. Network outages retain confirmed ownership for the same
slot while the client runs; changing slots clears it. Save loading immediately
clears native validation. Match entry requires validation, while an already
running match may finish. Cup descriptions refresh after ownership changes.

## Results and reward accounting

`Memory.py` decodes stable snapshots. Controller assignments distinguish human
fixtures from simulated ones. Live score leads and advancing round counters are
not completion signals. For Grudge, the client needs matching snapshots before
and after the win counter changes; it cannot reconstruct an unobserved result.

Observed checks and match-win counts persist per seed/team/slot. Cup fixtures and
the ten-entry history can recover retained results; starting new cups replaces
older records.

Reward processing waits for authoritative item history. Persisted `home` and
`away` queue keys mean player and opponent, including away-side humans.
Queue state is saved before publishing requests. A slot change settles the
outgoing owner's consumed units, withdraws its requests and rebases the incoming
queue. Restored request/applied counters are reconciled with stored consumption.
Identical restored counter values cannot be distinguished from unchanged ones.

Bowser loss identity and pending outgoing DeathLinks are stored together, so a
queued loss survives leaving results and restarting the client. Acknowledgments
use match identity rather than mutable scores or save IDs. Closed sockets retry.
DeathLink has no delivery receipt: a crash after sending but before persisting
the acknowledgment can repeat a send.

One client must own one Dolphin instance. Concurrent clients controlling the same
emulator are unsupported.

## Memory layout and sources

Structure definitions and result semantics come from the reconstructed source:

- [GameInfo.h](https://github.com/yannicksuter/smstrikers-decomp/blob/main/include/Game/GameInfo.h)
- [Cup.h](https://github.com/yannicksuter/smstrikers-decomp/blob/main/include/Game/DB/Cup.h)
- [BasicGameInfo.h](https://github.com/yannicksuter/smstrikers-decomp/blob/main/include/Game/DB/BasicGameInfo.h)
- [StatsTracker.h](https://github.com/yannicksuter/smstrikers-decomp/blob/main/include/Game/DB/StatsTracker.h)
- [StatsTracker.cpp](https://github.com/yannicksuter/smstrikers-decomp/blob/main/src/Game/DB/StatsTracker.cpp)
- [GameInfo.cpp](https://github.com/yannicksuter/smstrikers-decomp/blob/main/src/Game/GameInfo.cpp)

Use the patched executable's addresses, not the retail symbol map. Its `r13` is
`0x80379660`. GameInfoManager is at `0x80374418`; StatsTracker is at
`0x80374440` (load at `0x801837AC`, displacement `-0x5220`).
TrackWinner sets `mHasGameEnded` at StatsTracker offset `0x4C2`
(instruction `0x801837D4`). Runtime signatures guard these instructions.

GameInfoManager is `0x4C80` bytes. UserInfo starts at `+0x2ED4`; its trophy
bits are at `+0x4C`. Eight Spoil structures begin at UserInfo `+0x50`, with
`0x218` stride. Each stores up to ten `0x34`-byte CupRecords. Placement is a
signed byte at `+0x28`: ordinary placements are zero-based; `-2` means an
unspecified knockout loss.

BaseCup is `0x20` bytes followed by `0x20`-byte BasicGameInfo records.
League schedules contain `rounds * (teams / 2)` fixtures. Knockout<4> contains
two semifinals and a final. FinalScore is written at match end. Grudge completion
instead uses TrackWinner's per-side win counters and `mHasGameEnded`.
