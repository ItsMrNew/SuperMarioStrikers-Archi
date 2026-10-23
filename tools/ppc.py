"""Small PowerPC encoder for the guarded G4QE01 hooks (no compiler dependency)."""

import struct


def d(op, rt, ra, value):
    return op << 26 | rt << 21 | ra << 16 | (value & 0xFFFF)


def x(op, rt, ra, rb, xo, rc=0):
    return op << 26 | rt << 21 | ra << 16 | rb << 11 | xo << 1 | rc


class Assembler:
    def __init__(self, base):
        self.base = base
        self.words = []
        self.labels = {}
        self.fixups = []

    @property
    def pc(self):
        return self.base + len(self.words) * 4

    def label(self, name):
        self.labels[name] = self.pc

    def emit(self, *words):
        self.words.extend(words)

    def branch(self, target, link=False, condition=None):
        self.fixups.append((len(self.words), target, link, condition))
        self.emit(0)

    def address(self, reg, address):
        self.emit(d(15, reg, 0, (address + 0x8000) >> 16), d(14, reg, reg, address))

    def load(self, op, reg, address):
        self.emit(d(15, reg, 0, (address + 0x8000) >> 16), d(op, reg, reg, address))

    def finish(self):
        words = list(self.words)
        for index, target, link, condition in self.fixups:
            address = self.labels[target] if isinstance(target, str) else target
            delta = address - (self.base + index * 4)
            limit = 0x8000 if condition is not None else 0x2000000
            if delta % 4 or not -limit <= delta < limit:
                raise ValueError("Branch out of range")
            words[index] = (
                (0x48000000 | delta & 0x3FFFFFC)
                if condition is None
                else (condition | delta & 0xFFFC)
            ) | int(link)
        return struct.pack(f">{len(words)}I", *words)


BEQ, BNE, BLT, BGE, BGT, BLE = (
    0x41820000,
    0x40820000,
    0x41800000,
    0x40800000,
    0x41810000,
    0x40810000,
)
BLR = 0x4E800020


def mr(dst, src):
    return x(31, src, dst, src, 444)


def shift_right(dst, src, count):
    return x(31, src, dst, count, 536)


def shift_left(dst, src, count):
    return x(31, src, dst, count, 24)
