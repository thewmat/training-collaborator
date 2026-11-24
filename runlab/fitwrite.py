"""Minimal FIT encoder, used only to create synthetic demo data and test fixtures."""
import struct

from .fit import FIT_EPOCH

CRC_TABLE = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
             0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]

U8, U16, U32, ENUM = (0x02, "B", 1), (0x84, "H", 2), (0x86, "I", 4), (0x00, "B", 1)

MESSAGES = {
    "file_id": (0, [(0, ENUM), (1, U16), (2, U16), (4, U32)]),
    "device_info": (23, [(253, U32), (0, U8), (1, U8), (2, U16), (4, U16), (25, ENUM)]),
    "event": (21, [(253, U32), (0, ENUM), (1, ENUM)]),
    "record": (20, [(253, U32), (5, U32), (73, U32), (3, U8), (4, U8), (78, U32)]),
    "lap": (19, [(253, U32), (2, U32), (7, U32), (8, U32), (9, U32), (110, U32), (15, U8), (16, U8), (17, U8), (24, ENUM)]),
    "session": (18, [(253, U32), (2, U32), (7, U32), (8, U32), (9, U32), (5, ENUM), (6, ENUM), (16, U8), (17, U8)]),
}
INVALID = {"B": 0xFF, "H": 0xFFFF, "I": 0xFFFFFFFF}


def crc(data, c=0):
    for byte in data:
        tmp = CRC_TABLE[c & 0xF]; c = (c >> 4) & 0x0FFF; c = c ^ tmp ^ CRC_TABLE[byte & 0xF]
        tmp = CRC_TABLE[c & 0xF]; c = (c >> 4) & 0x0FFF; c = c ^ tmp ^ CRC_TABLE[(byte >> 4) & 0xF]
    return c


class Writer:
    def __init__(self):
        self.body = bytearray()
        self.local = {}

    def write(self, name, **values):
        gnum, fields = MESSAGES[name]
        if name not in self.local:
            lid = len(self.local)
            self.local[name] = lid
            self.body += bytes([0x40 | lid, 0, 0]) + struct.pack("<HB", gnum, len(fields))
            for num, (bt, _, size) in fields:
                self.body += bytes([num, size, bt])
        self.body += bytes([self.local[name]])
        for num, (_, fmt, _) in fields:
            v = values.get(str(num), values.get(f"f{num}"))
            self.body += struct.pack("<" + fmt, INVALID[fmt] if v is None else int(v))

    def bytes(self):
        header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(self.body), b".FIT")
        header += struct.pack("<H", crc(header))
        data = header + bytes(self.body)
        return data + struct.pack("<H", crc(data))


def ts(unix):
    return int(unix - FIT_EPOCH)
