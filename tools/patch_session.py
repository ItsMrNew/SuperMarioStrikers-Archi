"""Native client lease, save-load invalidation and front-end feedback."""

from tools.ppc import BEQ, BNE, BGT, BLR, d, mr

SESSION = 0x8038C790
SESSION_SIZE = 0x40
TEXT_BASE = 0x8038D100
TEXTS = (
    "Connect the Strikers client to your Archipelago slot.",
    "Archipelago ready.",
    "Wrong save for this Archipelago slot. Load the matching save or a fresh save.",
    "This save has old progress. Use a fresh save or /adoptsave confirm in the client.",
    "Return to the title or main menu so the client can bind this save.",
    "Update the Strikers client and Riivolution patch.",
    "This saved cup needs a locked captain or sidekick. Obtain their items or choose New Cup.",
)


def emit_session(a, hook, original_entry):
    def load(offset, register=12):
        a.load(32, register, SESSION + offset)

    # FrontEndTask::Run also executes in task state 4 (front-end menus), where
    # FrontEnd::Update is skipped. One tick per frame in menus and gameplay.
    # Only volatile registers change before replaying the original prologue.
    for label, address in (("lease_frame", 0x80170B78),):
        a.label(label)
        load(0)
        a.emit(d(11, 0, 12, 0))
        a.branch(label + "_native", condition=BEQ)
        a.emit(d(14, 12, 12, -1))
        a.address(11, SESSION)
        a.emit(d(36, 12, 11, 0), d(11, 0, 12, 0))
        a.branch(label + "_native", condition=BNE)
        a.emit(d(36, 12, 11, 4))  # expired => CONNECT
        a.label(label + "_native")
        original_entry(address)
        hook(address, (label, False))

    a.label("save_loaded")
    a.address(12, SESSION)
    a.emit(d(14, 0, 0, 0), d(36, 0, 12, 0), d(36, 0, 12, 4))
    a.emit(d(32, 11, 12, 12), d(14, 11, 11, 1), d(36, 11, 12, 12))
    original_entry(0x8017BDCC)
    hook(0x8017BDCC, ("save_loaded", False))

    a.label("loading_guard")
    load(0)
    a.emit(d(11, 0, 12, 0))
    a.branch("session_deny", condition=BEQ)
    original_entry(0x80095A18)
    hook(0x80095A18, ("loading_guard", False))

    # Block the four match/cup entries while allowing options/save loading.
    a.label("main_guard")
    a.emit(d(32, 0, 31, 0x228), d(10, 0, 0, 3))
    a.branch("main_guard_native", condition=BGT)
    load(0)
    a.emit(d(11, 0, 12, 0))
    a.branch("main_guard_native", condition=BNE)
    a.branch("session_deny", link=True)
    a.branch(0x800AA29C)
    a.label("main_guard_native")
    original_entry(0x800AA19C)
    hook(0x800AA19C, ("main_guard", False))

    # Refresh the selected cup after a mask update, without leaving the screen.
    # This point follows BaseSceneHandler::Update; f30 holds delta time.
    a.label("cup_refresh")
    a.address(12, SESSION)
    a.emit(d(32, 0, 12, 8), d(32, 11, 12, 16), 0x7C005800)  # cmpw r0,r11
    a.branch("cup_refresh_native", condition=BEQ)
    a.emit(d(36, 0, 12, 16), mr(3, 31))
    a.branch(0x800DAE8C, link=True)
    a.label("cup_refresh_native")
    original_entry(0x800DBA44)
    hook(0x800DBA44, ("cup_refresh", False))

    a.label("session_deny")
    load(4)
    a.emit(mr(0, 12))
    a.emit(d(10, 0, 0, 5))
    a.branch("session_text", condition=0x40810000)  # ble
    a.emit(d(14, 0, 0, 0))
    a.label("session_text")
    a.emit(d(7, 0, 0, 0x100))
    a.address(12, TEXT_BASE)
    a.emit(0x7C606214)  # add r3,r0,r12
    a.branch("message_popup")
    a.label("resume_deny")
    a.address(3, TEXT_BASE + 0x600)

    # A native one-button popup, with the normal OK callback/lifetime.
    a.label("message_popup")
    a.emit(d(37, 1, 1, -0x30), 0x7C0802A6, d(36, 0, 1, 0x34))
    a.emit(d(36, 30, 1, 0x28), d(36, 31, 1, 0x2C), mr(30, 3))
    a.emit(d(32, 3, 13, -0x5800), d(14, 4, 0, 27), d(14, 5, 0, 0), d(14, 6, 0, 0))
    a.branch(0x80095D3C, link=True)
    a.emit(mr(31, 3), d(14, 4, 0, 8))
    a.branch(0x800AC7F4, link=True)
    a.address(12, SESSION)
    a.emit(d(36, 31, 12, 20))
    a.emit(d(14, 12, 31, 0x1C))
    a.label("message_copy")
    a.emit(d(40, 0, 30, 0), d(44, 0, 12, 0), d(14, 30, 30, 2), d(14, 12, 12, 2))
    a.emit(d(11, 0, 0, 0))
    a.branch("message_copy", condition=BNE)
    a.emit(d(32, 0, 1, 0x34), d(32, 30, 1, 0x28), d(32, 31, 1, 0x2C))
    a.emit(0x7C0803A6, d(14, 1, 1, 0x30), BLR)

    # Native Create owns its allocated/localized string. Override only the
    # rendered pointer for our popup, keeping allocation/destruction intact.
    a.label("popup_text")
    load(20)
    a.emit(0x7C1F6000)  # cmpw r31,r12
    a.branch("popup_text_native", condition=BNE)
    a.emit(d(14, 4, 31, 0x1C), d(14, 0, 0, 0))
    a.address(12, SESSION)
    a.emit(d(36, 0, 12, 20))
    a.label("popup_text_native")
    a.branch(0x802107F8)
    hook(0x8009B834, ("popup_text", True))


def write_texts(section, base):
    for index, text in enumerate(TEXTS):
        data = (text + "\0").encode("utf-16-be")
        assert len(data) <= 0x100
        offset = TEXT_BASE + index * 0x100 - base
        section[offset : offset + len(data)] = data
