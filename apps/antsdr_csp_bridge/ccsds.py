"""
Utilitas CCSDS: ASM, pseudo-randomizer (CCSDS 131.0-B), CRC-16 FECF,
pembuat/pengurai TM Transfer Frame dan pembaca panjang TC Transfer Frame.
"""
from __future__ import annotations

import struct

ASM = bytes.fromhex("1ACFFC1D")


def _pn_sequence(n: int) -> bytes:
    """PN CCSDS h(x) = x^8+x^7+x^5+x^3+1, seed semua 1 -> FF 48 0E C0 9A ..."""
    reg = [1] * 8
    out = bytearray()
    for _ in range(n):
        byte = 0
        for _ in range(8):
            bit = reg[0]
            byte = (byte << 1) | bit
            fb = reg[0] ^ reg[3] ^ reg[5] ^ reg[7]
            reg = reg[1:] + [fb]
        out.append(byte)
    return bytes(out)


_PN = _pn_sequence(2048)


def randomize(data: bytes) -> bytes:
    """XOR dengan PN; fungsi yang sama dipakai untuk derandomize."""
    if len(data) > len(_PN):
        raise ValueError("frame terlalu panjang untuk tabel PN")
    return bytes(a ^ b for a, b in zip(data, _PN))


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16-CCITT (poly 0x1021, init 0xFFFF) untuk FECF CCSDS."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def fecf_ok(frame: bytes) -> bool:
    return len(frame) > 2 and crc16_ccitt(frame[:-2]) == struct.unpack(">H", frame[-2:])[0]


# ------------------------------------------------------------ TM Transfer Frame
def build_tm_frame(data: bytes, scid: int, vcid: int = 0, mcfc: int = 0, vcfc: int = 0,
                   frame_len: int = 223, with_fecf: bool = True, fill: int = 0x55) -> bytes:
    """
    TM Transfer Frame (CCSDS 132.0-B) panjang tetap.
    Header 6 byte + data field (+ FECF 2 byte). Data dipad dengan `fill`.
    """
    dfl = frame_len - 6 - (2 if with_fecf else 0)
    if len(data) > dfl:
        raise ValueError(f"data {len(data)} B > data field {dfl} B")
    w1 = (0 << 14) | ((scid & 0x3FF) << 4) | ((vcid & 0x7) << 1) | 0  # OCF flag 0
    # data field status: sec hdr 0, sync flag 1 (VCA), order 0, seg len id 11, FHP 0x7FF
    dfs = (0 << 15) | (1 << 14) | (0 << 13) | (0b11 << 11) | 0x7FF
    hdr = struct.pack(">HBBH", w1, mcfc & 0xFF, vcfc & 0xFF, dfs)
    frame = hdr + data + bytes([fill]) * (dfl - len(data))
    if with_fecf:
        frame += struct.pack(">H", crc16_ccitt(frame))
    return frame


def parse_tm_header(frame: bytes) -> dict:
    w1, mcfc, vcfc, dfs = struct.unpack(">HBBH", frame[:6])
    return {"version": w1 >> 14, "scid": (w1 >> 4) & 0x3FF, "vcid": (w1 >> 1) & 0x7,
            "ocf": w1 & 1, "mcfc": mcfc, "vcfc": vcfc, "dfs": dfs}


# ------------------------------------------------------------ TC Transfer Frame
def tc_frame_length(header5: bytes) -> int:
    """Panjang total TC Transfer Frame (CCSDS 232.0-B) dari 5 byte header."""
    _, w2 = struct.unpack(">HH", header5[:4])
    return (w2 & 0x3FF) + 1


def build_tc_frame(data: bytes, scid: int, vcid: int = 0, seq: int = 0,
                   bypass: bool = True, with_fecf: bool = True) -> bytes:
    length = 5 + len(data) + (2 if with_fecf else 0)
    if length > 1024:
        raise ValueError("TC frame maksimum 1024 byte")
    w1 = (0 << 14) | ((1 if bypass else 0) << 13) | (0 << 12) | (scid & 0x3FF)
    w2 = ((vcid & 0x3F) << 10) | ((length - 1) & 0x3FF)
    frame = struct.pack(">HHB", w1, w2, seq & 0xFF) + data
    if with_fecf:
        frame += struct.pack(">H", crc16_ccitt(frame))
    return frame
